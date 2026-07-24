from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import ufl
from mpi4py import MPI
from petsc4py import PETSc

import dolfinx_mpc
from dolfinx import fem
from dolfinx.fem import petsc as fem_petsc
from dolfinx.la.petsc import _ghost_update, create_vector

from ..common.config_3d import SimulationConfig3D
from ..common.modes_3d import (
    PortMode3D,
    incident_power_3d,
    mode_power,
    outgoing_port_modes_3d,
)
from ..constraints.floquet_3d import DoubleFloquet3DData
from .common_3d_solve import (
    DirectSolveFailure,
    _petsc_factor_inventory,
    _petsc_matrix_stats,
)
from .common_3d_utils import _write_progress_event
from .hcurl_cell_static_condensation import (
    build_explicit_cell_static_condensation,
    build_floquet_independent_trace_system,
    expand_floquet_independent_trace_solution,
    owned_hcurl_cell_interior_dofs,
    recover_full_solution,
)
from .hcurl_assembly_time_condensation import (
    AssemblyTimeCondensedSystem,
    build_unconstrained_assembly_time_condensation,
    cell_interior_schur_bilinear,
    condense_unconstrained_vector_to_active_trace,
    recover_owned_cell_interiors,
)
from .mpc_form_action import MpcFormActionContext
from .solve_vector_maxwell import _json_default


DTN_PORT_MODAL_POWER_SOURCE = "dtn_port_modal_amplitudes"
DTN_PORT_MODAL_REFERENCE = (
    "top=physical_z_max; bottom=physical_z_min; bottom lossy power uses boundary-plane phase attenuation"
)


def _complex_text(value: complex) -> str:
    number = complex(value)
    return f"{number.real:.16e}{number.imag:+.16e}j"


def _idx(values) -> np.ndarray:
    """PETSc index arrays must match the PETSc build's integer width."""

    if isinstance(values, np.ndarray):
        return np.asarray(values, dtype=PETSc.IntType)
    return np.fromiter(values, dtype=PETSc.IntType)


def _deferred_preallocation_matrix_stats(
    matrix,
    preallocation: dict[str, Any],
) -> dict[str, Any]:
    """Describe planned preallocation before the sole final assembly."""

    rows, cols = matrix.getSize()
    local_rows, local_cols = matrix.getLocalSize()
    row_ownership = matrix.getOwnershipRange()
    column_ownership = matrix.getOwnershipRangeColumn()
    allocated = int(preallocation["preallocated_structural_nnz"])
    return {
        "matrix_rows": int(rows),
        "matrix_cols": int(cols),
        "matrix_nnz_used": None,
        "matrix_nnz_allocated": None,
        "matrix_nnz_unneeded": None,
        "matrix_mallocs": None,
        "matrix_type": matrix.getType(),
        "matrix_local_rows": int(local_rows),
        "matrix_local_cols": int(local_cols),
        "matrix_row_ownership_range": list(map(int, row_ownership)),
        "matrix_column_ownership_range": list(
            map(int, column_ownership)
        ),
        "matrix_average_nnz_per_row": None,
        "matrix_maximum_nnz_per_row": None,
        "matrix_average_allocated_nnz_per_row": None,
        "matrix_memory_bytes": None,
        "matrix_memory_mb": None,
        "matrix_memory_estimate_bytes": None,
        "matrix_memory_estimate_mb": None,
        "matrix_norm_frobenius": None,
        "matrix_norm_infinity": None,
        "matrix_preallocated_structural_nnz_planned": float(allocated),
        "matrix_average_preallocated_nnz_per_row_planned": (
            float(allocated) / float(rows) if rows else 0.0
        ),
        "matrix_stats_measurement_status": "derived_pre_final_assembly",
        "matrix_stats_semantics": (
            "exact base constrained-cell graph plus a support-safe DtN "
            "upper bound; measured allocation and numerical NNZ are "
            "deferred until the sole augmented-matrix final assembly"
        ),
    }


def _as_ufl_vector(values: np.ndarray, phase):
    return ufl.as_vector(tuple(PETSc.ScalarType(value) * phase for value in values))


def _surface_vector_form(V, mesh_data, tag: int, vector: np.ndarray, phase):
    v = ufl.TestFunction(V)
    ds = ufl.Measure("ds", domain=mesh_data.mesh, subdomain_data=mesh_data.facet_tags)
    return ufl.inner(_as_ufl_vector(vector, phase), v) * ds(tag)


def _assemble_mpc_form_vector(linear_form, mpc) -> PETSc.Vec:
    vec = dolfinx_mpc.assemble_vector(linear_form, mpc)
    vec.ghostUpdate(addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE)
    vec.ghostUpdate(addv=PETSc.InsertMode.INSERT_VALUES, mode=PETSc.ScatterMode.FORWARD)
    return vec


def _assemble_unconstrained_form_vector(linear_form) -> PETSc.Vec:
    vec = fem_petsc.assemble_vector(linear_form)
    vec.ghostUpdate(
        addv=PETSc.InsertMode.ADD_VALUES,
        mode=PETSc.ScatterMode.REVERSE,
    )
    vec.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    return vec


def _assemble_mpc_vector(linear_form, mpc, *, quadrature_degree: int | None = None) -> PETSc.Vec:
    form_options: dict[str, int] = {}
    if quadrature_degree is not None:
        form_options["quadrature_degree"] = int(quadrature_degree)
    return _assemble_mpc_form_vector(fem.form(linear_form, form_compiler_options=form_options), mpc)


def _assemble_unconstrained_vector(
    linear_form,
    *,
    quadrature_degree: int | None = None,
) -> PETSc.Vec:
    form_options: dict[str, int] = {}
    if quadrature_degree is not None:
        form_options["quadrature_degree"] = int(quadrature_degree)
    return _assemble_unconstrained_form_vector(
        fem.form(
            linear_form,
            form_compiler_options=form_options,
        )
    )


def _vec_nonzero_owned_entries(vec: PETSc.Vec, *, relative_tol: float = 1.0e-13) -> tuple[np.ndarray, np.ndarray]:
    start, end = vec.getOwnershipRange()
    values = np.asarray(vec.getArray(readonly=True), dtype=np.complex128)
    if values.size == 0:
        return _idx([]), np.asarray([], dtype=np.complex128)
    cutoff = max(1.0e-30, relative_tol * float(np.max(np.abs(values))))
    nz = np.flatnonzero(np.abs(values) > cutoff)
    return (_idx(np.arange(start, end, dtype=np.int64)[nz]), values[nz].copy())


def _combine_owned_entries(
    component_entries: tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]],
    coefficients: tuple[complex, complex],
    *,
    relative_tol: float = 1.0e-13,
) -> tuple[np.ndarray, np.ndarray]:
    row_blocks: list[np.ndarray] = []
    value_blocks: list[np.ndarray] = []
    for (rows, values), coefficient in zip(component_entries, coefficients):
        coefficient = complex(coefficient)
        if len(rows) == 0 or abs(coefficient) <= 0.0:
            continue
        row_blocks.append(rows)
        value_blocks.append(PETSc.ScalarType(coefficient) * values)
    if not row_blocks:
        return _idx([]), np.asarray([], dtype=np.complex128)

    rows_all = np.concatenate(row_blocks).astype(PETSc.IntType, copy=False)
    values_all = np.concatenate(value_blocks).astype(np.complex128, copy=False)
    order = np.argsort(rows_all, kind="mergesort")
    rows_sorted = rows_all[order]
    values_sorted = values_all[order]
    unique_rows, first = np.unique(rows_sorted, return_index=True)
    summed_values = np.add.reduceat(values_sorted, first)
    cutoff = max(1.0e-30, relative_tol * float(np.max(np.abs(summed_values))))
    keep = np.abs(summed_values) > cutoff
    return _idx(unique_rows[keep]), summed_values[keep].copy()


def _active_trace_values_from_augmented(
    x_aug: PETSc.Vec,
    condensed: AssemblyTimeCondensedSystem,
) -> np.ndarray:
    """Collect the small independent trace vector on every rank."""

    comm = condensed.matrix.getComm().tompi4py()
    local_active = len(
        condensed.trace_constraints.owned_active_original_dofs
    )
    local_values = np.asarray(
        x_aug.getArray(readonly=True)[:local_active],
        dtype=np.complex128,
    ).copy()
    packets = comm.allgather(local_values)
    active = (
        np.concatenate(packets)
        if packets
        else np.empty(0, dtype=np.complex128)
    )
    if active.shape != (condensed.active_rows,):
        raise RuntimeError(
            "distributed active trace solution does not close globally"
        )
    return active


def _assign_fe_solution_from_assembly_time_condensation(
    x_aug: PETSc.Vec,
    condensed: AssemblyTimeCondensedSystem,
    floquet_data: DoubleFloquet3DData,
    full_rhs: PETSc.Vec,
) -> tuple[Any, PETSc.Vec, dict[str, Any]]:
    """Recover cell interiors without allocating the full global matrix."""

    recovery_started = time.perf_counter()
    active = _active_trace_values_from_augmented(x_aug, condensed)
    recovered = recover_owned_cell_interiors(
        condensed,
        active,
        full_rhs=full_rhs,
    )
    mpc = floquet_data.mpc
    E_total = fem.Function(mpc.function_space, name="E_total")
    index_map = E_total.function_space.dofmap.index_map
    block_size = E_total.function_space.dofmap.index_map_bs
    x_fe = create_vector([(index_map, block_size)])
    x_fe.set(PETSc.ScalarType(0.0))
    owned_active = (
        condensed.trace_constraints.owned_active_original_dofs
    )
    if len(owned_active):
        active_ids = _idx(
            condensed.trace_constraints.original_to_active[int(original)]
            for original in owned_active
        )
        x_fe.setValues(
            owned_active,
            active[active_ids],
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
    local_recovered = 0
    for original_rows, values in recovered:
        x_fe.setValues(
            original_rows,
            np.asarray(values, dtype=PETSc.ScalarType),
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
        local_recovered += len(original_rows)
    x_fe.assemble()
    _ghost_update(
        x_fe,
        PETSc.InsertMode.INSERT,
        PETSc.ScatterMode.FORWARD,
    )  # type: ignore[arg-type]
    fem_petsc.assign(x_fe, E_total)
    mpc.homogenize(E_total)
    mpc.backsubstitution(E_total)
    E_total.x.scatter_forward()
    comm = E_total.function_space.mesh.comm
    return E_total, x_fe, {
        "schema_version": (
            "task035b.assembly-time-cell-condensation-recovery.v1"
        ),
        "status": "full_field_recovered_without_full_global_matrix",
        "recovered_interior_rows": int(
            comm.allreduce(local_recovered, op=MPI.SUM)
        ),
        "full_global_matrix_allocated": False,
        "full_trace_matrix_allocated": False,
        "total_recovery_seconds": float(
            comm.allreduce(
                time.perf_counter() - recovery_started,
                op=MPI.MAX,
            )
        ),
    }


def _assembly_time_full_operator_residual(
    bilinear_form,
    floquet_data: DoubleFloquet3DData,
    embedded_fe_solution: PETSc.Vec,
    reduced_matrix: PETSc.Mat,
    reduced_rhs: PETSc.Vec,
    reduced_solution: PETSc.Vec,
    condensed: AssemblyTimeCondensedSystem,
    full_rhs: PETSc.Vec,
) -> dict[str, Any]:
    """Audit all eliminated FE equations without allocating the full matrix."""

    reduced = _linear_residual(
        reduced_matrix,
        reduced_rhs,
        reduced_solution,
    )
    context = MpcFormActionContext(
        bilinear_form,
        floquet_data.mpc,
        reference=None,
    )
    action = embedded_fe_solution.duplicate()
    action.set(PETSc.ScalarType(0.0))
    try:
        context.mult(
            None,  # type: ignore[arg-type]
            embedded_fe_solution,
            action,
        )
        local_interior_sq = 0.0
        local_interior_max = 0.0
        for cell in condensed.cell_recovery_maps:
            values = np.asarray(
                action.getValues(cell.interior_original_dofs),
                dtype=np.complex128,
            )
            values -= np.asarray(
                full_rhs.getValues(cell.interior_original_dofs),
                dtype=np.complex128,
            )
            values = (
                condensed.interior_residual_projection_by_class[
                    cell.class_key
                ]
                @ values
            )
            local_interior_sq += float(np.vdot(values, values).real)
            local_interior_max = max(
                local_interior_max,
                float(np.max(np.abs(values), initial=0.0)),
            )
        comm = reduced_matrix.getComm().tompi4py()
        interior_norm = float(
            np.sqrt(comm.allreduce(local_interior_sq, op=MPI.SUM))
        )
        interior_max = float(
            comm.allreduce(local_interior_max, op=MPI.MAX)
        )
        reduced_norm = float(
            reduced["linear_system_residual_norm"] or 0.0
        )
        full_norm = float(np.hypot(reduced_norm, interior_norm))
        local_aux_rhs_sq = 0.0
        if comm.rank == comm.size - 1 and condensed.appended_rows:
            aux_start = condensed.active_rows
            aux_rhs = np.asarray(
                reduced_rhs.getValues(
                    _idx(
                        range(
                            aux_start,
                            aux_start + condensed.appended_rows,
                        )
                    )
                ),
                dtype=np.complex128,
            )
            local_aux_rhs_sq = float(np.vdot(aux_rhs, aux_rhs).real)
        rhs_norm = float(
            np.sqrt(
                full_rhs.norm() ** 2
                + comm.allreduce(local_aux_rhs_sq, op=MPI.SUM)
            )
        )

        local_aux_sq = 0.0
        if comm.rank == comm.size - 1 and condensed.appended_rows:
            aux_start = condensed.active_rows
            aux_values = np.asarray(
                reduced_solution.getValues(
                    _idx(
                        range(
                            aux_start,
                            aux_start + condensed.appended_rows,
                        )
                    )
                ),
                dtype=np.complex128,
            )
            local_aux_sq = float(np.vdot(aux_values, aux_values).real)
        auxiliary_norm_sq = float(
            comm.allreduce(local_aux_sq, op=MPI.SUM)
        )
        full_solution_norm = float(
            np.sqrt(
                embedded_fe_solution.norm() ** 2
                + auxiliary_norm_sq
            )
        )
        return {
            "linear_system_rhs_norm": rhs_norm,
            "linear_system_solution_norm": full_solution_norm,
            "linear_system_residual_norm": full_norm,
            "linear_system_relative_residual": (
                full_norm / max(rhs_norm, 1.0e-30)
            ),
            "reduced_trace_dtn_residual_norm": reduced_norm,
            "eliminated_cell_interior_residual_norm": interior_norm,
            "eliminated_cell_interior_max_abs_residual": interior_max,
            "full_operator_residual_method": (
                "explicit reduced trace+DtN Mat action combined with "
                "matrix-free dolfinx_mpc UFL action projected onto every "
                "active eliminated cell-interior test space, including "
                "condensed full-space RHS"
            ),
            "full_global_matrix_allocated_for_residual": False,
            "full_trace_matrix_allocated_for_residual": False,
        }
    finally:
        action.destroy()
        context.destroy()


def _set_scalar_constant(constant: fem.Constant, value: complex) -> None:
    scalar = PETSc.ScalarType(value)
    try:
        constant.value[...] = scalar
    except Exception:
        constant.value = scalar


class _ReusableSurfaceComponentAssembler:
    """Cache one port surface form and update only the Fourier phase constants."""

    def __init__(
        self,
        V,
        mesh_data,
        tag: int,
        component: int,
        *,
        quadrature_degree: int | None = None,
    ):
        if component not in {0, 1}:
            raise ValueError("Stage-4 DtN port component assembly only supports x/y tangential components.")
        self.alpha = fem.Constant(mesh_data.mesh, PETSc.ScalarType(0.0))
        self.gamma = fem.Constant(mesh_data.mesh, PETSc.ScalarType(0.0))
        self.kz = fem.Constant(mesh_data.mesh, PETSc.ScalarType(0.0))
        x = ufl.SpatialCoordinate(mesh_data.mesh)
        phase = ufl.exp(
            PETSc.ScalarType(1j) * self.alpha * x[0]
            + PETSc.ScalarType(1j) * self.gamma * x[1]
            + PETSc.ScalarType(1j) * self.kz * x[2]
        )
        vector = [PETSc.ScalarType(0.0), PETSc.ScalarType(0.0), PETSc.ScalarType(0.0)]
        vector[component] = phase
        v = ufl.TestFunction(V)
        ds = ufl.Measure("ds", domain=mesh_data.mesh, subdomain_data=mesh_data.facet_tags)
        form_options: dict[str, int] = {}
        if quadrature_degree is not None:
            form_options["quadrature_degree"] = int(quadrature_degree)
        self.form = fem.form(
            ufl.inner(ufl.as_vector(tuple(vector)), v) * ds(tag),
            form_compiler_options=form_options,
        )

    def assemble_entries(self, mode: PortMode3D, mpc) -> tuple[np.ndarray, np.ndarray]:
        _set_scalar_constant(self.alpha, mode.alpha)
        _set_scalar_constant(self.gamma, mode.gamma)
        _set_scalar_constant(self.kz, mode.k_vector[2])
        vec = _assemble_mpc_form_vector(self.form, mpc)
        try:
            return _vec_nonzero_owned_entries(vec)
        finally:
            vec.destroy()

    def assemble_unconstrained_vector(self, mode: PortMode3D) -> PETSc.Vec:
        _set_scalar_constant(self.alpha, mode.alpha)
        _set_scalar_constant(self.gamma, mode.gamma)
        _set_scalar_constant(self.kz, mode.k_vector[2])
        return _assemble_unconstrained_form_vector(self.form)


def _copy_base_matrix_to_augmented(
    A_base: PETSc.Mat,
    n_aux: int,
    comm: MPI.Intracomm,
    *,
    on_allocated: Callable[[], None] | None = None,
) -> PETSc.Mat:
    n_fe = A_base.getSize()[0]
    local_fe_rows = A_base.getOwnershipRange()[1] - A_base.getOwnershipRange()[0]
    local_aug_rows = local_fe_rows + (n_aux if comm.rank == comm.size - 1 else 0)
    A_aug = PETSc.Mat().createAIJ(
        size=((local_aug_rows, n_fe + n_aux), (local_aug_rows, n_fe + n_aux)),
        comm=comm,
    )
    A_aug.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)
    if on_allocated is not None:
        on_allocated()
    row_start, row_end = A_base.getOwnershipRange()
    for row in range(row_start, row_end):
        cols, values = A_base.getRow(row)
        if len(cols):
            A_aug.setValues(_idx([row]), _idx(cols), values)
    return A_aug


def _local_augmented_dtn_coupling_stats(
    *,
    n_fe: int,
    n_aux: int,
    traction_rows_total: int,
    ell_cols_total: int,
) -> dict[str, Any]:
    """Summarize the sparse auxiliary DtN block shape.

    The auxiliary formulation should add one sparse column and one sparse row
    per mode, not a dense all-to-all FEM trace block.
    """

    coupling_nnz = int(traction_rows_total + ell_cols_total + n_aux)
    return {
        "dtn_auxiliary_block_is_dense": False,
        "dtn_auxiliary_dof_count": int(n_aux),
        "dtn_auxiliary_fem_dof_count": int(n_fe),
        "dtn_auxiliary_coupling_nnz_estimate": coupling_nnz,
        "dtn_auxiliary_average_coupling_nnz_per_mode": float(coupling_nnz / max(n_aux, 1)),
        "dtn_auxiliary_dense_block_equivalent_nnz": int(n_aux * max(n_fe, 1) * 2 + n_aux),
    }


def _augmented_vec_from_base(b_base: PETSc.Vec, n_aux: int, comm: MPI.Intracomm) -> PETSc.Vec:
    n_fe = b_base.getSize()
    local_fe_rows = b_base.getOwnershipRange()[1] - b_base.getOwnershipRange()[0]
    local_aug_rows = local_fe_rows + (n_aux if comm.rank == comm.size - 1 else 0)
    b_aug = PETSc.Vec().createMPI((local_aug_rows, n_fe + n_aux), comm=comm)
    row_start, row_end = b_base.getOwnershipRange()
    values = np.asarray(b_base.getArray(readonly=True), dtype=np.complex128)
    if values.size:
        b_aug.setValues(
            _idx(np.arange(row_start, row_end, dtype=np.int64)),
            values,
            addv=PETSc.InsertMode.ADD_VALUES,
        )
    return b_aug


def _outward_normal(side: str) -> np.ndarray:
    if side == "top":
        return np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
    if side == "bottom":
        return np.asarray((0.0, 0.0, -1.0), dtype=np.float64)
    raise ValueError("side must be 'top' or 'bottom'.")


def _mode_boundary_z(mode: PortMode3D, cfg: SimulationConfig3D) -> float:
    return float(cfg.physical_z_max if mode.side == "top" else cfg.physical_z_min)


def _mode_boundary_phase(mode: PortMode3D, cfg: SimulationConfig3D) -> complex:
    return complex(np.exp(1j * complex(mode.k_vector[2]) * _mode_boundary_z(mode, cfg)))


def _mode_projection_denominator(mode: PortMode3D, cfg: SimulationConfig3D) -> float:
    area = (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)
    phase = _mode_boundary_phase(mode, cfg)
    return float(area * mode.electric_tangential_norm_sq * abs(phase) ** 2)


def _mode_power_at_boundary(mode: PortMode3D, cfg: SimulationConfig3D, amplitude: complex) -> float:
    e_at_boundary = complex(amplitude) * _mode_boundary_phase(mode, cfg) * mode.e_vector
    return mode_power(mode.k_vector, e_at_boundary, cfg, _outward_normal(mode.side))


def _mode_carries_outward_power(mode: PortMode3D) -> bool:
    """Return whether the selected mode carries positive real power at its finite port."""

    return bool(mode.power_per_unit_amplitude > 0.0)


def _traction_vector(mode: PortMode3D, cfg: SimulationConfig3D) -> np.ndarray:
    del cfg
    curl_vector = 1j * np.cross(mode.k_vector, mode.e_vector)
    return np.cross(curl_vector, _outward_normal(mode.side))


def _incident_projection_onto_top_mode(mode: PortMode3D, cfg: SimulationConfig3D) -> complex:
    if mode.side != "top" or mode.m != 0 or mode.n != 0:
        return 0.0 + 0.0j
    denominator = _mode_projection_denominator(mode, cfg)
    incident_e = complex(cfg.incident_amplitude) * np.asarray(cfg.polarization_vector, dtype=np.complex128)
    tangential_overlap = np.vdot(mode.e_vector[:2], incident_e[:2])
    phase = np.exp(1j * (cfg.kz - mode.k_vector[2]) * cfg.physical_z_max)
    area = (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)
    return complex(area * tangential_overlap * phase / denominator)


def _incident_top_traction_form(V, mesh_data, cfg: SimulationConfig3D):
    x = ufl.SpatialCoordinate(mesh_data.mesh)
    k_inc = np.asarray(cfg.wavevector, dtype=np.complex128)
    e_inc = complex(cfg.incident_amplitude) * np.asarray(cfg.polarization_vector, dtype=np.complex128)
    traction = np.cross(1j * np.cross(k_inc, e_inc), np.asarray((0.0, 0.0, 1.0), dtype=np.float64))
    phase = ufl.exp(
        PETSc.ScalarType(1j * k_inc[0]) * x[0]
        + PETSc.ScalarType(1j * k_inc[1]) * x[1]
        + PETSc.ScalarType(1j * k_inc[2]) * x[2]
    )
    return _surface_vector_form(V, mesh_data, cfg.tags.z_max, traction, phase)


def _dtn_surface_quadrature_degree(cfg: SimulationConfig3D, modes: list[PortMode3D]) -> int:
    """Choose a quadrature degree for oscillatory DtN surface projections.

    The port forms contain Fourier factors exp(i alpha x + i gamma y), not just
    polynomials.  Default UFL quadrature is too low for p=2 EUV cases where the
    automatically selected propagating orders can change phase rapidly within a
    single surface cell.  A deterministic moderately high rule keeps the
    auxiliary DtN block from losing rank in MPI while avoiding a user-facing
    option explosion at this stage.
    """

    configured = getattr(cfg, "stage4_dtn_quadrature_degree", None)
    if configured is not None:
        return max(1, int(configured))
    max_order = max((max(abs(mode.m), abs(mode.n)) for mode in modes), default=0)
    return int(max(10, 2 * int(cfg.nedelec_degree) + max_order + 6))


def _use_zero_order_local_robin_dtn(cfg: SimulationConfig3D) -> bool:
    """Use the 2D-like local DtN sanity branch for normal-incidence order 0."""

    transverse_scale = max(abs(cfg.k0 * complex(cfg.n_air)), 1.0)
    normal_incidence = (
        abs(complex(cfg.kx)) <= 1.0e-12 * transverse_scale and abs(complex(cfg.ky)) <= 1.0e-12 * transverse_scale
    )
    return cfg.stage4_dtn_order_policy.lower() == "zero_order" and normal_incidence


def _mode_projection_from_solution(
    E_total,
    mode: PortMode3D,
    mesh_data,
    cfg: SimulationConfig3D,
    *,
    quadrature_degree: int | None,
) -> complex:
    """Project a solved total field onto one port mode on its boundary face."""

    tag = cfg.tags.z_max if mode.side == "top" else cfg.tags.z_min
    x = ufl.SpatialCoordinate(mesh_data.mesh)
    phase = ufl.exp(
        PETSc.ScalarType(1j * mode.alpha) * x[0]
        + PETSc.ScalarType(1j * mode.gamma) * x[1]
        + PETSc.ScalarType(1j * mode.k_vector[2]) * x[2]
    )
    reference = _as_ufl_vector(mode.e_vector, phase)
    ds = ufl.Measure("ds", domain=mesh_data.mesh, subdomain_data=mesh_data.facet_tags)
    form_options: dict[str, int] = {}
    if quadrature_degree is not None:
        form_options["quadrature_degree"] = int(quadrature_degree)
    local = fem.assemble_scalar(fem.form(ufl.inner(E_total, reference) * ds(tag), form_compiler_options=form_options))
    total = mesh_data.mesh.comm.allreduce(local, op=MPI.SUM)
    denominator = _mode_projection_denominator(mode, cfg)
    return complex(total / denominator)


def _surface_scalar(
    expression,
    mesh_data,
    tag: int,
    *,
    quadrature_degree: int | None,
) -> complex:
    ds = ufl.Measure("ds", domain=mesh_data.mesh, subdomain_data=mesh_data.facet_tags)
    form_options: dict[str, int] = {}
    if quadrature_degree is not None:
        form_options["quadrature_degree"] = int(quadrature_degree)
    local = fem.assemble_scalar(fem.form(expression * ds(tag), form_compiler_options=form_options))
    return complex(mesh_data.mesh.comm.allreduce(local, op=MPI.SUM))


def _surface_diagnostics(
    E_total,
    mesh_data,
    cfg: SimulationConfig3D,
    *,
    quadrature_degree: int | None,
) -> dict[str, Any]:
    """Return direct z-port measure diagnostics for the zero-order sanity branch."""

    fdim = mesh_data.mesh.topology.dim - 1
    facet_index_map = mesh_data.mesh.topology.index_map(fdim)
    owned_facet_limit = facet_index_map.size_local
    diagnostics: dict[str, Any] = {}
    one = fem.Constant(mesh_data.mesh, PETSc.ScalarType(1.0))
    e_t = ufl.as_vector((E_total[0], E_total[1], PETSc.ScalarType(0.0)))
    for side, tag in (("top", cfg.tags.z_max), ("bottom", cfg.tags.z_min)):
        tagged_facets = np.asarray(mesh_data.facet_tags.find(tag), dtype=np.int32)
        owned_count_local = int(np.count_nonzero(tagged_facets < owned_facet_limit))
        owned_count = int(mesh_data.mesh.comm.allreduce(owned_count_local, op=MPI.SUM))
        area = _surface_scalar(one, mesh_data, tag, quadrature_degree=quadrature_degree)
        energy = _surface_scalar(ufl.inner(e_t, e_t), mesh_data, tag, quadrature_degree=quadrature_degree)
        diagnostics[f"stage4_dtn_{side}_facet_count_owned_global"] = owned_count
        diagnostics[f"stage4_dtn_{side}_surface_area_nm2"] = float(np.real(area))
        diagnostics[f"stage4_dtn_{side}_Et_l2_integral"] = float(np.real(energy))
        diagnostics[f"stage4_dtn_{side}_Et_l2_mean"] = float(np.real(energy) / max(float(np.real(area)), 1.0e-30))
    return diagnostics


def _owned_cells_adjacent_to_facet_tag(mesh_data, tag: int) -> np.ndarray:
    """Return locally owned cells touching a tagged exterior facet."""

    msh = mesh_data.mesh
    tdim = msh.topology.dim
    fdim = tdim - 1
    msh.topology.create_connectivity(fdim, tdim)
    facet_to_cell = msh.topology.connectivity(fdim, tdim)
    if facet_to_cell is None:
        raise RuntimeError("facet-to-cell connectivity is unavailable")
    owned_cells = int(msh.topology.index_map(tdim).size_local)
    tagged_facets = np.asarray(
        mesh_data.facet_tags.find(int(tag)),
        dtype=np.int32,
    )
    cells = [
        int(cell)
        for facet in tagged_facets
        for cell in facet_to_cell.links(int(facet))
        if 0 <= int(cell) < owned_cells
    ]
    return np.asarray(sorted(set(cells)), dtype=np.int32)


def _zero_order_local_robin_forms(a, L, V, mesh_data, cfg: SimulationConfig3D):
    """Build the normal-incidence order-0 DtN form used as a hard sanity path.

    The H(curl) integration-by-parts identity contributes
    ``+ int_boundary (n x curl(E)) . v``.  For a top incident downward wave and
    outgoing top/bottom zero-order modes, this gives the same sign convention
    as the validated 2D port sanity path: ``q=-i beta`` and top source
    ``-2 i beta E_inc,t``.
    """

    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    x = ufl.SpatialCoordinate(mesh_data.mesh)
    ds = ufl.Measure("ds", domain=mesh_data.mesh, subdomain_data=mesh_data.facet_tags)

    beta_top = cfg.k0 * complex(cfg.n_air)
    beta_bottom = cfg.k0 * complex(cfg.substrate_index)
    q_top = PETSc.ScalarType(-1j * beta_top)
    q_bottom = PETSc.ScalarType(-1j * beta_bottom)
    v_t = ufl.as_vector((v[0], v[1], PETSc.ScalarType(0.0)))
    q_top_u_t = ufl.as_vector((q_top * u[0], q_top * u[1], PETSc.ScalarType(0.0)))
    q_bottom_u_t = ufl.as_vector((q_bottom * u[0], q_bottom * u[1], PETSc.ScalarType(0.0)))
    a_local = a + ufl.inner(q_top_u_t, v_t) * ds(cfg.tags.z_max) + ufl.inner(q_bottom_u_t, v_t) * ds(cfg.tags.z_min)

    k_inc = np.asarray(cfg.wavevector, dtype=np.complex128)
    incident_e = complex(cfg.incident_amplitude) * np.asarray(cfg.polarization_vector, dtype=np.complex128)
    source_vec = np.asarray(
        (
            -2j * beta_top * incident_e[0],
            -2j * beta_top * incident_e[1],
            0.0 + 0.0j,
        ),
        dtype=np.complex128,
    )
    phase = ufl.exp(
        PETSc.ScalarType(1j * k_inc[0]) * x[0]
        + PETSc.ScalarType(1j * k_inc[1]) * x[1]
        + PETSc.ScalarType(1j * k_inc[2]) * x[2]
    )
    L_local = L + ufl.inner(_as_ufl_vector(source_vec, phase), v) * ds(cfg.tags.z_max)
    return a_local, L_local


def _solve_zero_order_local_robin_dtn(
    *,
    a,
    L,
    V,
    mesh_data,
    cfg: SimulationConfig3D,
    floquet_data: DoubleFloquet3DData,
    petsc_options: dict[str, Any],
    out_dir: Path,
    log,
    started: float | None = None,
) -> dict[str, Any]:
    """Solve the normal-incidence zero-order DtN port as a local Robin problem."""

    comm = mesh_data.mesh.comm
    stage_start = time.perf_counter()
    timing_details: dict[str, float | int | bool | str] = {
        "stage4_dtn_zero_order_local_robin": True,
    }
    modes = outgoing_port_modes_3d(cfg)
    if len(modes) != 4:
        raise RuntimeError(f"zero_order local DtN expects exactly four modes: top/bottom x/y. Got {len(modes)} modes.")
    dtn_quadrature_degree = _dtn_surface_quadrature_degree(cfg, modes)
    timing_details["stage4_dtn_surface_quadrature_degree"] = int(dtn_quadrature_degree)
    if log is not None:
        log("Stage-4 DtN using zero-order local Robin sanity branch")
        log(f"Stage-4 DtN surface quadrature degree = {dtn_quadrature_degree}")

    t0 = time.perf_counter()
    a_local, L_local = _zero_order_local_robin_forms(a, L, V, mesh_data, cfg)
    E_total = fem.Function(floquet_data.mpc.function_space, name="E_total")
    if cfg.matrix_diagnostics_assemble_only:
        A_diag = dolfinx_mpc.assemble_matrix(fem.form(a_local), floquet_data.mpc, bcs=[])
        A_diag.assemble()
        b_diag = _assemble_mpc_vector(L_local, floquet_data.mpc)
        x_diag = b_diag.duplicate()
        x_diag.set(PETSc.ScalarType(0.0))
        ksp = PETSc.KSP().create(comm)
        ksp.setOptionsPrefix(f"stage4_3d_zero_order_dtn_{cfg.case_name}_")
        ksp.setOperators(A_diag)
        opts = PETSc.Options()
        opts.prefixPush(f"stage4_3d_zero_order_dtn_{cfg.case_name}_")
        for key, value in petsc_options.items():
            opts[key] = value
        ksp.setFromOptions()
        for key in petsc_options.keys():
            del opts[key]
        opts.prefixPop()
        matrix_stats_after_setup = _petsc_matrix_stats(A_diag)
        _write_progress_event(
            out_dir,
            comm,
            stage="stage4_dtn_zero_order_matrix_assembled",
            status="end",
            started=started,
            dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
            constraints=floquet_data.num_constraints,
            matrix_stats=matrix_stats_after_setup,
            petsc_options=petsc_options,
        )
        timing_details["stage4_dtn_zero_order_linear_problem_setup_seconds"] = float(
            comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
        )
        solver_info = {
            "solver_backend": "dolfinx_mpc assembled zero-order local 3D DtN/Robin ports",
            "assemble_only": True,
            "num_auxiliary_dofs": 0,
            "num_fem_dofs_after_mpc": int(A_diag.getSize()[0]),
            "num_total_augmented_dofs": int(A_diag.getSize()[0]),
            "explicit_chac_constructed": False,
            "dtn_auxiliary_dense_block_constructed": False,
            "dtn_base_matrix_stats": None,
            "dtn_augmented_matrix_stats_after_finalize": None,
            "dtn_auxiliary_block_stats": {
                "dtn_auxiliary_block_is_dense": False,
                "dtn_auxiliary_dof_count": 0,
                "dtn_auxiliary_coupling_nnz_estimate": 0,
            },
            "stage4_dtn_assembly_seconds": float(comm.allreduce(time.perf_counter() - stage_start, op=MPI.MAX)),
            "ksp_converged_reason": 0,
            "ksp_iterations": 0,
            "actual_ksp_type": ksp.getType(),
            "actual_pc_type": ksp.getPC().getType(),
            "actual_pc_factor_solver_type": None,
            **timing_details,
        }
        try:
            solver_info["actual_pc_factor_solver_type"] = ksp.getPC().getFactorSolverType()
        except Exception:
            solver_info["actual_pc_factor_solver_type"] = None
        return {
            "E_total": E_total,
            "solver_info": solver_info,
            "port_metrics": {
                "R_total": None,
                "T_total": None,
                "R_plus_T": None,
                "A_balance": None,
                "diffraction_total_power_source": "assemble_only_skipped",
                **_port_mode_count_metrics(modes),
            },
            "A": A_diag,
            "b": b_diag,
            "x": x_diag,
            "ksp": ksp,
            "problem": None,
        }

    problem = dolfinx_mpc.LinearProblem(
        a_local,
        L_local,
        floquet_data.mpc,
        bcs=[],
        u=E_total,
        petsc_options_prefix=f"stage4_3d_zero_order_dtn_{cfg.case_name}_",
        petsc_options=petsc_options,
    )
    timing_details["stage4_dtn_zero_order_linear_problem_setup_seconds"] = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    )

    t0 = time.perf_counter()
    _write_progress_event(
        out_dir,
        comm,
        stage="stage4_dtn_zero_order_solve",
        status="begin",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        petsc_options=petsc_options,
    )
    try:
        E_total = problem.solve()
    except PETSc.Error as exc:
        raise DirectSolveFailure(
            "PETSc direct LU failed during Stage-4 zero-order DtN KSPSolve.",
            failure_stage="stage4_dtn_zero_order_solve",
            petsc_error=exc,
            A=problem.A,
            b=problem.b,
            x=problem.x,
            ksp=problem.solver,
            solver_backend="dolfinx_mpc.LinearProblem with zero-order local 3D DtN/Robin ports",
            timing_details=timing_details,
            extra_summary={
                "solver_info": {
                    "num_auxiliary_dofs": 0,
                    "dtn_base_matrix_stats": None,
                    "dtn_augmented_matrix_stats_after_finalize": None,
                    "dtn_auxiliary_block_stats": {
                        "dtn_auxiliary_block_is_dense": False,
                        "dtn_auxiliary_dof_count": 0,
                        "dtn_auxiliary_coupling_nnz_estimate": 0,
                    },
                }
            },
        ) from exc
    E_total.x.scatter_forward()
    timing_details["stage4_dtn_zero_order_linear_solve_seconds"] = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    )
    _write_progress_event(
        out_dir,
        comm,
        stage="stage4_dtn_zero_order_solve",
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        matrix_stats=_petsc_matrix_stats(problem.A),
        petsc_options=petsc_options,
    )

    t0 = time.perf_counter()
    modal_values = np.asarray(
        [
            _mode_projection_from_solution(
                E_total,
                mode,
                mesh_data,
                cfg,
                quadrature_degree=dtn_quadrature_degree,
            )
            for mode in modes
        ],
        dtype=np.complex128,
    )
    incident_projections = [_incident_projection_onto_top_mode(mode, cfg) for mode in modes]
    timing_details["stage4_dtn_zero_order_projection_seconds"] = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    )
    port_metrics = _port_power_metrics(cfg, modes, modal_values, incident_projections)
    port_metrics.update(
        _surface_diagnostics(
            E_total,
            mesh_data,
            cfg,
            quadrature_degree=dtn_quadrature_degree,
        )
    )
    port_metrics["stage4_dtn_zero_order_modal_values"] = [complex(value) for value in modal_values]
    port_metrics["stage4_dtn_zero_order_incident_projections"] = [complex(value) for value in incident_projections]
    port_metrics.update(timing_details)
    port_metrics["dtn_port_power_metric_note"] = (
        "Stage-4 zero_order dtn_port R/T is computed from direct boundary projections "
        "after solving the local Robin/DtN total-field problem."
    )
    _write_port_outputs(out_dir, cfg, modes, modal_values, incident_projections, port_metrics, comm)

    solver_info = {
        "solver_backend": "dolfinx_mpc.LinearProblem with zero-order local 3D DtN/Robin ports",
        "num_auxiliary_dofs": 0,
        "num_fem_dofs_after_mpc": int(problem.A.getSize()[0]),
        "num_total_augmented_dofs": int(problem.A.getSize()[0]),
        "explicit_chac_constructed": False,
        "dtn_auxiliary_dense_block_constructed": False,
        "dtn_base_matrix_stats": None,
        "dtn_augmented_matrix_stats_after_finalize": None,
        "dtn_auxiliary_block_stats": {
            "dtn_auxiliary_block_is_dense": False,
            "dtn_auxiliary_dof_count": 0,
            "dtn_auxiliary_coupling_nnz_estimate": 0,
        },
        "stage4_dtn_assembly_seconds": float(comm.allreduce(time.perf_counter() - stage_start, op=MPI.MAX)),
        "ksp_converged_reason": int(problem.solver.getConvergedReason()),
        "ksp_iterations": int(problem.solver.getIterationNumber()),
        "actual_ksp_type": problem.solver.getType(),
        "actual_pc_type": problem.solver.getPC().getType(),
        "actual_pc_factor_solver_type": None,
        **timing_details,
        **_linear_residual(problem.A, problem.b, problem.x),
    }
    try:
        solver_info["actual_pc_factor_solver_type"] = problem.solver.getPC().getFactorSolverType()
    except Exception:
        solver_info["actual_pc_factor_solver_type"] = None
    return {
        "E_total": E_total,
        "solver_info": solver_info,
        "port_metrics": port_metrics,
        "A": problem.A,
        "b": problem.b,
        "x": problem.x,
        "ksp": problem.solver,
        "problem": problem,
    }


def _solve_augmented_system(
    A_aug: PETSc.Mat,
    b_aug: PETSc.Vec,
    petsc_options: dict[str, Any],
    prefix: str,
    *,
    out_dir: Path | None = None,
    comm: MPI.Intracomm | None = None,
    started: float | None = None,
    dofs: int | None = None,
    constraints: int | None = None,
    matrix_stats: dict[str, Any] | None = None,
    factorization_only: bool = False,
) -> tuple[PETSc.Vec, PETSc.KSP, dict[str, Any]]:
    progress_comm = comm if comm is not None else A_aug.getComm()
    if out_dir is not None:
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="before_ksp_create",
            status="begin",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
        )
    ksp = PETSc.KSP().create(A_aug.getComm())
    ksp.setOptionsPrefix(prefix)
    ksp.setOperators(A_aug)
    opts = PETSc.Options()
    opts.prefixPush(prefix)
    for key, value in petsc_options.items():
        opts[key] = value
    ksp.setFromOptions()
    for key in petsc_options.keys():
        del opts[key]
    opts.prefixPop()
    x_aug = b_aug.duplicate()
    if out_dir is not None:
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="stage4_dtn_augmented_ksp_setup",
            status="begin",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
        )
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="before_ksp_setup",
            status="begin",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
        )
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="during_ksp_setup_peak",
            status="active",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
            extra={"stage_semantics": "external sampler labels samples while KSPSetUp is running"},
        )
    setup_started = time.perf_counter()
    try:
        ksp.setUp()
    except PETSc.Error as exc:
        raise DirectSolveFailure(
            "PETSc direct LU failed during Stage-4 augmented DtN KSPSetUp/LU factorization.",
            failure_stage="stage4_dtn_augmented_ksp_setup",
            petsc_error=exc,
            A=A_aug,
            b=b_aug,
            x=x_aug,
            ksp=ksp,
            solver_backend="PETSc augmented auxiliary Fourier-DtN port with dolfinx_mpc Floquet constraints",
        ) from exc
    setup_seconds = float(progress_comm.allreduce(time.perf_counter() - setup_started, op=MPI.MAX))
    factor_inventory = _petsc_factor_inventory(ksp)
    if out_dir is not None:
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="stage4_dtn_augmented_ksp_setup",
            status="end",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
        )
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="after_ksp_setup_factorized",
            status="end",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
            extra={
                "ksp_setup_seconds": setup_seconds,
                "factor_inventory": factor_inventory,
            },
        )
    if factorization_only:
        x_aug.set(PETSc.ScalarType(0.0))
        return (
            x_aug,
            ksp,
            {
                "ksp_setup_seconds": setup_seconds,
                "ksp_solve_seconds": None,
                "factor_inventory": factor_inventory,
                "factorization_only": True,
            },
        )
    if out_dir is not None:
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="stage4_dtn_augmented_solve",
            status="begin",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
        )
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="before_ksp_solve",
            status="begin",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
        )
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="during_ksp_solve_peak",
            status="active",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
            extra={"stage_semantics": "external sampler labels samples while KSPSolve is running"},
        )
    solve_started = time.perf_counter()
    try:
        ksp.solve(b_aug, x_aug)
    except PETSc.Error as exc:
        raise DirectSolveFailure(
            "PETSc direct LU failed during Stage-4 augmented DtN KSPSolve.",
            failure_stage="stage4_dtn_augmented_solve",
            petsc_error=exc,
            A=A_aug,
            b=b_aug,
            x=x_aug,
            ksp=ksp,
            solver_backend="PETSc augmented auxiliary Fourier-DtN port with dolfinx_mpc Floquet constraints",
        ) from exc
    solve_seconds = float(progress_comm.allreduce(time.perf_counter() - solve_started, op=MPI.MAX))
    if out_dir is not None:
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="stage4_dtn_augmented_solve",
            status="end",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
        )
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="after_ksp_solve",
            status="end",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
            extra={"ksp_solve_seconds": solve_seconds},
        )
    return (
        x_aug,
        ksp,
        {
            "ksp_setup_seconds": setup_seconds,
            "ksp_solve_seconds": solve_seconds,
            "factor_inventory": factor_inventory,
        },
    )


def _assign_fe_solution_from_augmented(
    x_aug: PETSc.Vec,
    floquet_data: DoubleFloquet3DData,
    n_aux: int,
):
    mpc = floquet_data.mpc
    E_total = fem.Function(mpc.function_space, name="E_total")
    index_map = E_total.function_space.dofmap.index_map
    block_size = E_total.function_space.dofmap.index_map_bs

    # Mirror dolfinx_mpc.LinearProblem.solve(): use a PETSc vector with the
    # original MPC function-space layout, ghost-update it, then let
    # fem.petsc.assign populate the Function.  Hand-copying into
    # E_total.x.array is fragile in MPI once the augmented DtN system appends
    # auxiliary rows on the final rank.
    x_fe = create_vector([(index_map, block_size)])
    row_start, row_end = x_fe.getOwnershipRange()
    if row_end > row_start:
        rows = _idx(np.arange(row_start, row_end, dtype=np.int64))
        x_fe.setValues(rows, x_aug.getValues(rows), addv=PETSc.InsertMode.INSERT_VALUES)
    x_fe.assemble()
    _ghost_update(x_fe, PETSc.InsertMode.INSERT, PETSc.ScatterMode.FORWARD)  # type: ignore[arg-type]
    fem_petsc.assign(x_fe, E_total)
    mpc.homogenize(E_total)
    mpc.backsubstitution(E_total)
    E_total.x.scatter_forward()
    x_fe.destroy()
    if n_aux == 0:
        return E_total
    return E_total


def _gather_auxiliary_values(x_aug: PETSc.Vec, n_fe: int, n_aux: int, comm: MPI.Intracomm) -> np.ndarray:
    values = np.zeros(n_aux, dtype=np.complex128)
    owner_rank = comm.size - 1
    if comm.rank == owner_rank and n_aux:
        values[:] = x_aug.getValues(_idx(np.arange(n_fe, n_fe + n_aux, dtype=np.int64)))
    values = comm.bcast(values, root=owner_rank)
    return np.asarray(values, dtype=np.complex128)


def _linear_residual(A: PETSc.Mat, b: PETSc.Vec, x: PETSc.Vec) -> dict[str, float | None]:
    try:
        residual = b.duplicate()
        A.mult(x, residual)
        residual.axpy(PETSc.ScalarType(-1.0), b)
        rhs_norm = float(b.norm())
        residual_norm = float(residual.norm())
        return {
            "linear_system_rhs_norm": rhs_norm,
            "linear_system_solution_norm": float(x.norm()),
            "linear_system_residual_norm": residual_norm,
            "linear_system_relative_residual": residual_norm / max(rhs_norm, 1.0e-30),
        }
    except Exception:
        return {
            "linear_system_rhs_norm": None,
            "linear_system_solution_norm": None,
            "linear_system_residual_norm": None,
            "linear_system_relative_residual": None,
        }


def _write_port_outputs(
    out_dir: Path,
    cfg: SimulationConfig3D,
    modes: list[PortMode3D],
    aux_values: np.ndarray,
    incident_projections: list[complex],
    metrics: dict[str, Any],
    comm: MPI.Intracomm,
) -> None:
    rows: list[dict[str, Any]] = []
    for idx, (mode, aux_value, inc_proj) in enumerate(zip(modes, aux_values, incident_projections)):
        outgoing_amplitude = complex(aux_value - inc_proj) if mode.side == "top" else complex(aux_value)
        power_carrying = _mode_carries_outward_power(mode)
        modal_power = _mode_power_at_boundary(mode, cfg, outgoing_amplitude)
        power = modal_power / metrics["incident_power_code_units"]
        direction = "outgoing_up" if mode.side == "top" else "outgoing_down"
        medium = "air" if mode.side == "top" else "substrate"
        rows.append(
            {
                "auxiliary_index": idx,
                "side": mode.side,
                "direction": direction,
                "medium": medium,
                "m": mode.m,
                "n": mode.n,
                "order_m": mode.m,
                "order_n": mode.n,
                "polarization": mode.polarization,
                "alpha": mode.alpha,
                "gamma": mode.gamma,
                "beta": mode.beta,
                "kz": mode.vertical_sign * mode.beta,
                "vertical_sign": mode.vertical_sign,
                "propagating": mode.propagating,
                "power_carrying": power_carrying,
                "rayleigh_warning": mode.rayleigh_warning,
                "refractive_index": mode.refractive_index,
                "auxiliary_amplitude_total_projection": complex(aux_value),
                "incident_projection": complex(inc_proj),
                "outgoing_amplitude": outgoing_amplitude,
                "boundary_phase": _mode_boundary_phase(mode, cfg),
                "outgoing_amplitude_at_boundary": outgoing_amplitude * _mode_boundary_phase(mode, cfg),
                "modal_power_code_units": float(modal_power),
                "power_ratio": float(power),
                "power_source": DTN_PORT_MODAL_POWER_SOURCE,
                "R": float(power) if mode.side == "top" and power_carrying else 0.0,
                "T": float(power) if mode.side == "bottom" and power_carrying else 0.0,
            }
        )
    if comm.rank != 0:
        return
    payload = {"metrics": metrics, "orders": rows}
    port_payload = {
        "method": "port",
        "role": "primary",
        "status": "ok",
        "power_source": DTN_PORT_MODAL_POWER_SOURCE,
        "reference": DTN_PORT_MODAL_REFERENCE,
        "reference_planes": {
            "top_z": float(cfg.physical_z_max),
            "bottom_z": float(cfg.physical_z_min),
            "top_reference": "physical_z_max",
            "bottom_reference": "physical_z_min",
        },
        "R_total": metrics["R_total"],
        "R00_total": metrics["R00_total"],
        "R00_s": metrics["R00_s"],
        "R00_p": metrics["R00_p"],
        "T_total": metrics["T_total"],
        "A_balance": metrics["A_balance"],
        "R_plus_T": metrics["R_plus_T"],
        "R_total_dtn_port_modal": metrics["R_total_dtn_port_modal"],
        "T_total_dtn_port_modal": metrics["T_total_dtn_port_modal"],
        "A_balance_dtn_port_modal": metrics["A_balance_dtn_port_modal"],
        "R_plus_T_dtn_port_modal": metrics["R_plus_T_dtn_port_modal"],
        "R_plus_T_plus_A_volume_dtn_port_modal": metrics.get("R_plus_T_plus_A_volume_dtn_port_modal"),
        "energy_closure_error_dtn_port_modal_volume": metrics.get("energy_closure_error_dtn_port_modal_volume"),
        "incident_power_code_units": metrics["incident_power_code_units"],
        "stage4_dtn_order_policy": cfg.stage4_dtn_order_policy,
        "stage4_dtn_assembly": cfg.stage4_dtn_assembly,
        "modal_amplitude_convention": metrics["dtn_port_modal_amplitude_convention"],
        "orders": rows,
        "note": metrics.get("dtn_port_power_metric_note"),
    }
    (out_dir / "port_power.json").write_text(
        json.dumps(port_payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    (out_dir / "dtn_port_power_metrics_3d.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    (out_dir / "dtn_port_diffraction_orders_3d.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    csv_rows = [
        {key: _complex_text(value) if isinstance(value, complex) else value for key, value in row.items()}
        for row in rows
    ]
    with (out_dir / "dtn_port_diffraction_orders_3d.csv").open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(csv_rows[0].keys()) if csv_rows else ["side", "m", "n"])
        writer.writeheader()
        writer.writerows(csv_rows)
    with (out_dir / "port_power.csv").open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(csv_rows[0].keys()) if csv_rows else ["side", "m", "n"])
        writer.writeheader()
        writer.writerows(csv_rows)
    amplitudes = [
        {
            "auxiliary_index": idx,
            "side": mode.side,
            "direction": "outgoing_up" if mode.side == "top" else "outgoing_down",
            "medium": "air" if mode.side == "top" else "substrate",
            "m": mode.m,
            "n": mode.n,
            "order_m": mode.m,
            "order_n": mode.n,
            "polarization": mode.polarization,
            "beta": mode.beta,
            "kz": mode.vertical_sign * mode.beta,
            "propagating": mode.propagating,
            "auxiliary_amplitude_total_projection": complex(aux_values[idx]),
            "incident_projection": complex(incident_projections[idx]),
            "outgoing_amplitude": complex(aux_values[idx] - incident_projections[idx])
            if mode.side == "top"
            else complex(aux_values[idx]),
            "boundary_phase": _mode_boundary_phase(mode, cfg),
            "outgoing_amplitude_at_boundary": (
                complex(aux_values[idx] - incident_projections[idx]) if mode.side == "top" else complex(aux_values[idx])
            )
            * _mode_boundary_phase(mode, cfg),
        }
        for idx, mode in enumerate(modes)
    ]
    (out_dir / "dtn_auxiliary_amplitudes_3d.json").write_text(
        json.dumps(amplitudes, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


def _port_power_metrics(
    cfg: SimulationConfig3D,
    modes: list[PortMode3D],
    aux_values: np.ndarray,
    incident_projections: list[complex],
) -> dict[str, Any]:
    incident_power = incident_power_3d(cfg)
    rows_by_side = {"top": 0, "bottom": 0}
    R_total = 0.0
    T_total = 0.0
    R00_by_polarization: dict[str, float] = {}
    for mode, aux_value, inc_proj in zip(modes, aux_values, incident_projections):
        rows_by_side[mode.side] += 1
        outgoing_amplitude = complex(aux_value - inc_proj) if mode.side == "top" else complex(aux_value)
        if not _mode_carries_outward_power(mode):
            continue
        power = _mode_power_at_boundary(mode, cfg, outgoing_amplitude) / incident_power
        if mode.side == "top":
            R_total += float(power)
            if mode.m == 0 and mode.n == 0:
                R00_by_polarization[mode.polarization] = (
                    R00_by_polarization.get(mode.polarization, 0.0)
                    + float(power)
                )
        else:
            T_total += float(power)
    R00_total = float(sum(R00_by_polarization.values()))
    return {
        "R_total": float(R_total),
        "R00_total": R00_total,
        "R00_s": float(R00_by_polarization.get("s", 0.0)),
        "R00_p": float(R00_by_polarization.get("p", 0.0)),
        "R00_by_polarization": R00_by_polarization,
        "T_total": float(T_total),
        "R_plus_T": float(R_total + T_total),
        "A_balance": float(1.0 - R_total - T_total),
        "R_total_dtn_port_modal": float(R_total),
        "T_total_dtn_port_modal": float(T_total),
        "R_plus_T_dtn_port_modal": float(R_total + T_total),
        "A_balance_dtn_port_modal": float(1.0 - R_total - T_total),
        "R_plus_T_plus_A_volume": None,
        "R_plus_T_plus_A_volume_dtn_port_modal": None,
        "energy_closure_error_dtn_port_modal_volume": None,
        "power_source": DTN_PORT_MODAL_POWER_SOURCE,
        "diffraction_total_power_source": DTN_PORT_MODAL_POWER_SOURCE,
        "dtn_port_modal_reference": DTN_PORT_MODAL_REFERENCE,
        "dtn_port_top_reference_z": float(cfg.physical_z_max),
        "dtn_port_bottom_reference_z": float(cfg.physical_z_min),
        "dtn_port_modal_amplitude_convention": (
            "auxiliary unknown a_j is the total-field port projection. "
            "top outgoing amplitude = a_j - incident_projection_j; "
            "bottom outgoing amplitude = a_j. Power uses boundary-plane "
            "outgoing amplitude after applying boundary_phase."
        ),
        "dtn_port_power_metric_note": (
            "Stage-4 dtn_port R/T is computed directly from auxiliary outgoing modal amplitudes "
            "on the finite top and bottom port faces. Selected modes with positive outward real-Poynting "
            "flux contribute even when a below-critical lossy mode retains propagating=false; lossless "
            "evanescent modes carry zero modal power."
        ),
        "incident_power_code_units": float(incident_power),
        "stage4_dtn_order_policy": cfg.stage4_dtn_order_policy,
        "stage4_dtn_assembly": cfg.stage4_dtn_assembly,
        "dtn_port_mode_count": int(len(modes)),
        "dtn_port_top_mode_count": int(rows_by_side["top"]),
        "dtn_port_bottom_mode_count": int(rows_by_side["bottom"]),
        "dtn_port_propagating_mode_count": int(sum(1 for mode in modes if mode.propagating)),
        "dtn_port_rayleigh_warning_count": int(sum(1 for mode in modes if mode.rayleigh_warning)),
        "port_power_file": "port_power.json",
        "dtn_port_power_metrics_file": "dtn_port_power_metrics_3d.json",
        "dtn_port_orders_json": "dtn_port_diffraction_orders_3d.json",
        "dtn_port_orders_csv": "dtn_port_diffraction_orders_3d.csv",
        "port_power_csv": "port_power.csv",
        "dtn_auxiliary_amplitudes_file": "dtn_auxiliary_amplitudes_3d.json",
    }


def _port_mode_count_metrics(modes: list[PortMode3D]) -> dict[str, int]:
    rows_by_side = {"top": 0, "bottom": 0}
    for mode in modes:
        rows_by_side[mode.side] += 1
    return {
        "dtn_port_mode_count": int(len(modes)),
        "dtn_port_top_mode_count": int(rows_by_side["top"]),
        "dtn_port_bottom_mode_count": int(rows_by_side["bottom"]),
        "dtn_port_propagating_mode_count": int(sum(1 for mode in modes if mode.propagating)),
        "dtn_port_rayleigh_warning_count": int(sum(1 for mode in modes if mode.rayleigh_warning)),
    }


def solve_stage4_dtn_port_total_field(
    *,
    a,
    L,
    V,
    mesh_data,
    cfg: SimulationConfig3D,
    floquet_data: DoubleFloquet3DData,
    petsc_options: dict[str, Any],
    out_dir: Path,
    log,
    started: float | None = None,
) -> dict[str, Any]:
    """Solve the Stage-4 total-field problem with 3D Fourier-DtN ports."""

    if cfg.stage4_dtn_assembly.lower() != "auxiliary":
        raise NotImplementedError("Stage-4 3D DtN v1 supports only stage4_dtn_assembly='auxiliary'.")
    if cfg.use_pml:
        raise ValueError("stage4_boundary_model='dtn_port' requires use_pml=False.")
    if floquet_data is None:
        raise ValueError("stage4_boundary_model='dtn_port' requires x/y Floquet constraints.")
    if cfg.stage4_cell_static_condensation and (
        cfg.matrix_diagnostics_assemble_only
        or cfg.matrix_diagnostics_factorization_only
    ):
        raise ValueError(
            "Task035b cell static condensation requires a complete solve; "
            "assemble-only/factorization-only diagnostics are unsupported."
        )
    if (
        cfg.stage4_floquet_slave_elimination
        and not cfg.stage4_cell_static_condensation
    ):
        raise ValueError(
            "Task035b Floquet slave elimination currently requires "
            "stage4_cell_static_condensation=True."
        )
    if cfg.stage4_assembly_time_cell_static_condensation and (
        not cfg.stage4_cell_static_condensation
        or not cfg.stage4_floquet_slave_elimination
    ):
        raise ValueError(
            "assembly-time cell condensation directly builds the Floquet-"
            "independent trace system and requires both Task035b flags"
        )
    if cfg.stage4_regionwise_interior_p and (
        not cfg.stage4_assembly_time_cell_static_condensation
        or not cfg.nedelec_reduced_trace_enabled
        or cfg.stage_case != "stage4_block_grating"
        or cfg.geometry_kind != "rectangular_block_grating"
    ):
        raise ValueError(
            "Task035b regionwise interior-p requires the fixed rectangular "
            "target, a reduced-trace element, and assembly-time condensation"
        )
    if _use_zero_order_local_robin_dtn(cfg):
        return _solve_zero_order_local_robin_dtn(
            a=a,
            L=L,
            V=V,
            mesh_data=mesh_data,
            cfg=cfg,
            floquet_data=floquet_data,
            petsc_options=petsc_options,
            out_dir=out_dir,
            log=log,
            started=started,
        )

    comm = mesh_data.mesh.comm
    stage_start = time.perf_counter()
    timing_details: dict[str, float | int] = {}
    modes = outgoing_port_modes_3d(cfg)
    n_aux = len(modes)
    if n_aux == 0:
        raise RuntimeError("Stage-4 DtN selected zero port modes.")
    dtn_quadrature_degree = _dtn_surface_quadrature_degree(cfg, modes)
    timing_details["stage4_dtn_surface_quadrature_degree"] = int(
        dtn_quadrature_degree
    )
    assembly_time_system = None
    assembly_time_full_rhs = None

    t0 = time.perf_counter()
    if cfg.stage4_assembly_time_cell_static_condensation:
        regionwise_element = None
        regionwise_low_compiled_form = None
        if cfg.stage4_regionwise_interior_p:
            import basix.ufl

            from ..adaptivity.hcurl_regionwise_p import (
                create_reduced_trace_hcurl_element,
            )

            regionwise_element = create_reduced_trace_hcurl_element(
                cfg.nedelec_trace_degree_resolved,
                cfg.nedelec_interior_degree_resolved,
                cfg.stage4_regionwise_low_interior_degree_resolved,
            )
            low_space = fem.functionspace(
                mesh_data.mesh,
                basix.ufl.wrap_element(regionwise_element.low_element),
            )
            low_test = ufl.TestFunction(low_space)
            low_trial = ufl.TrialFunction(low_space)
            arguments = a.arguments()
            if len(arguments) != 2:
                raise ValueError(
                    "regionwise-p requires a bilinear form with two arguments"
                )
            low_form = ufl.replace(
                a,
                {
                    arguments[0]: low_test,
                    arguments[1]: low_trial,
                },
            )
            regionwise_low_compiled_form = fem.form(low_form)
        assembly_time_system = (
            build_unconstrained_assembly_time_condensation(
                fem.form(a),
                V,
                mesh_data.cell_tags,
                mpc=floquet_data.mpc,
                appended_global_rows=n_aux,
                appended_support_owned_cell_groups=(
                    _owned_cells_adjacent_to_facet_tag(
                        mesh_data,
                        cfg.tags.z_max,
                    ),
                    _owned_cells_adjacent_to_facet_tag(
                        mesh_data,
                        cfg.tags.z_min,
                    ),
                ),
                appended_support_group_by_row=tuple(
                    0 if mode.side == "top" else 1 for mode in modes
                ),
                defer_final_assembly=True,
                regionwise_element=regionwise_element,
                regionwise_low_compiled_form=(
                    regionwise_low_compiled_form
                ),
                regionwise_high_canonical_cell_ids=(
                    cfg.stage4_regionwise_high_canonical_cell_ids
                ),
                regionwise_mesh_geometry_sha256=(
                    cfg.stage4_regionwise_mesh_geometry_sha256
                ),
            )
        )
        A_base = None
        A_aug = assembly_time_system.matrix
        n_fe = int(assembly_time_system.active_rows)
        base_matrix_stats = _deferred_preallocation_matrix_stats(
            A_aug,
            assembly_time_system.build_audit["trace_preallocation"],
        )
        base_matrix_lifecycle = (
            "preallocated_values_pending_augmented_final_assembly"
        )
        timing_details.update(
            {
                f"stage4_dtn_assembly_time_{key}": value
                for key, value in assembly_time_system.build_audit.items()
                if key.endswith("_seconds")
            }
        )
    else:
        A_base = dolfinx_mpc.assemble_matrix(
            fem.form(a),
            floquet_data.mpc,
            bcs=None,
        )
        A_base.assemble()
        A_aug = None
        n_fe = A_base.getSize()[0]
        base_matrix_stats = _petsc_matrix_stats(A_base)
        base_matrix_lifecycle = "assembled"
    _write_progress_event(
        out_dir,
        comm,
        stage="stage4_dtn_base_matrix_assembled",
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        matrix_stats=base_matrix_stats,
        petsc_options=petsc_options,
        extra={
            "stage4_dtn_base_matrix_lifecycle": base_matrix_lifecycle,
        },
    )
    _write_progress_event(
        out_dir,
        comm,
        stage="after_base_matrix_assembly",
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        matrix_stats=base_matrix_stats,
        petsc_options=petsc_options,
        extra={
            "stage4_dtn_base_matrix_lifecycle": base_matrix_lifecycle,
        },
    )
    timing_details["stage4_dtn_base_matrix_assembly_seconds"] = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    )

    t0 = time.perf_counter()
    if assembly_time_system is not None:
        full_b_base = _assemble_unconstrained_vector(L)
        assembly_time_full_rhs = full_b_base
        b_aug = condense_unconstrained_vector_to_active_trace(
            assembly_time_system,
            full_b_base,
            side="right",
        )
        b_base = None
    else:
        full_b_base = _assemble_mpc_vector(L, floquet_data.mpc)
        b_base = full_b_base
        b_aug = None
    timing_details["stage4_dtn_base_rhs_assembly_seconds"] = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    )

    _write_progress_event(
        out_dir,
        comm,
        stage="after_dtn_mode_enumeration",
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        petsc_options=petsc_options,
        extra={"stage4_dtn_num_auxiliary_dofs": int(n_aux)},
    )
    if log is not None:
        log(f"Stage-4 DtN selected auxiliary port modes = {n_aux}")
        log(
            f"Stage-4 DtN top/bottom mode count = {sum(m.side == 'top' for m in modes)} / {sum(m.side == 'bottom' for m in modes)}"
        )
        log(f"Stage-4 DtN matrix base rows = {n_fe}")
        log(f"Stage-4 DtN surface quadrature degree = {dtn_quadrature_degree}")

    t0 = time.perf_counter()
    if assembly_time_system is None:
        if A_base is None or b_base is None:
            raise RuntimeError("ordinary DtN base matrix lifecycle is invalid")
        A_aug = _copy_base_matrix_to_augmented(
            A_base,
            n_aux,
            comm,
            on_allocated=lambda: _write_progress_event(
                out_dir,
                comm,
                stage="after_augmented_matrix_allocation",
                status="end",
                started=started,
                dofs=int(
                    V.dofmap.index_map.size_global
                    * V.dofmap.index_map_bs
                ),
                constraints=floquet_data.num_constraints,
                petsc_options=petsc_options,
                extra={"stage4_dtn_num_auxiliary_dofs": int(n_aux)},
            ),
        )
        b_aug = _augmented_vec_from_base(b_base, n_aux, comm)
    else:
        _write_progress_event(
            out_dir,
            comm,
            stage="after_augmented_matrix_allocation",
            status="end",
            started=started,
            dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
            constraints=floquet_data.num_constraints,
            petsc_options=petsc_options,
            extra={
                "stage4_dtn_num_auxiliary_dofs": int(n_aux),
                "assembly_time_final_augmented_matrix": True,
                "base_to_augmented_matrix_copy_performed": False,
            },
        )
    _write_progress_event(
        out_dir,
        comm,
        stage="after_base_matrix_copy",
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        petsc_options=petsc_options,
        extra={"stage4_dtn_num_auxiliary_dofs": int(n_aux)},
    )
    timing_details["stage4_dtn_augmented_block_copy_seconds"] = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    ) if assembly_time_system is None else 0.0
    if (
        cfg.direct_release_base_after_augmentation
        and assembly_time_system is None
    ):
        if A_base is None or b_base is None:
            raise RuntimeError("ordinary DtN base release state is invalid")
        A_base.destroy()
        b_base.destroy()
        A_base = None
        b_base = None
        _write_progress_event(
            out_dir,
            comm,
            stage="after_base_matrix_release",
            status="end",
            started=started,
            dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
            constraints=floquet_data.num_constraints,
            petsc_options=petsc_options,
            extra={
                "direct_release_base_after_augmentation": True,
                "released_objects": ["A_base", "b_base"],
            },
        )
    elif assembly_time_system is not None:
        _write_progress_event(
            out_dir,
            comm,
            stage="after_base_matrix_release",
            status="end",
            started=started,
            dofs=int(
                V.dofmap.index_map.size_global
                * V.dofmap.index_map_bs
            ),
            constraints=floquet_data.num_constraints,
            petsc_options=petsc_options,
            extra={
                "direct_release_base_after_augmentation": True,
                "released_objects": [],
                "base_matrix_was_never_allocated": True,
                "base_to_augmented_matrix_copy_performed": False,
            },
        )

    t0 = time.perf_counter()
    if assembly_time_system is not None:
        if assembly_time_full_rhs is None:
            raise RuntimeError("assembly-time full RHS was not initialized")
        incident_traction_vec = _assemble_unconstrained_vector(
            _incident_top_traction_form(V, mesh_data, cfg)
        )
        reduced_incident = condense_unconstrained_vector_to_active_trace(
            assembly_time_system,
            incident_traction_vec,
            side="right",
        )
        inc_rows, inc_values = _vec_nonzero_owned_entries(
            reduced_incident
        )
        assembly_time_full_rhs.axpy(
            PETSc.ScalarType(1.0),
            incident_traction_vec,
        )
        reduced_incident.destroy()
        incident_traction_vec.destroy()
    else:
        incident_traction_vec = _assemble_mpc_vector(
            _incident_top_traction_form(V, mesh_data, cfg),
            floquet_data.mpc,
        )
        inc_rows, inc_values = _vec_nonzero_owned_entries(
            incident_traction_vec
        )
        incident_traction_vec.destroy()
    if len(inc_rows):
        b_aug.setValues(inc_rows, inc_values, addv=PETSc.InsertMode.ADD_VALUES)
    timing_details["stage4_dtn_incident_source_vector_seconds"] = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    )

    incident_projections: list[complex] = []
    surface_assemblers = {
        ("top", 0): _ReusableSurfaceComponentAssembler(
            V, mesh_data, cfg.tags.z_max, 0, quadrature_degree=dtn_quadrature_degree
        ),
        ("top", 1): _ReusableSurfaceComponentAssembler(
            V, mesh_data, cfg.tags.z_max, 1, quadrature_degree=dtn_quadrature_degree
        ),
        ("bottom", 0): _ReusableSurfaceComponentAssembler(
            V, mesh_data, cfg.tags.z_min, 0, quadrature_degree=dtn_quadrature_degree
        ),
        ("bottom", 1): _ReusableSurfaceComponentAssembler(
            V, mesh_data, cfg.tags.z_min, 1, quadrature_degree=dtn_quadrature_degree
        ),
    }
    component_key: tuple[str, int, int, complex] | None = None
    component_right_entries: (
        tuple[
            tuple[np.ndarray, np.ndarray],
            tuple[np.ndarray, np.ndarray],
        ]
        | None
    ) = None
    component_left_entries: (
        tuple[
            tuple[np.ndarray, np.ndarray],
            tuple[np.ndarray, np.ndarray],
        ]
        | None
    ) = None
    component_full_vectors: tuple[PETSc.Vec, PETSc.Vec] | None = None
    component_interior_bilinear: np.ndarray | None = None
    unique_surface_orders = 0
    component_vector_assemblies = 0
    component_vector_cache_hits = 0
    modal_vector_assembly_seconds_local = 0.0
    modal_block_insert_seconds_local = 0.0
    traction_rows_total_local = 0
    ell_cols_total_local = 0
    matrix_insert_mode = (
        PETSc.InsertMode.ADD_VALUES
        if assembly_time_system is not None
        else PETSc.InsertMode.INSERT_VALUES
    )
    matrix_row_start, matrix_row_end = A_aug.getOwnershipRange()
    modal_loop_start = time.perf_counter()
    for aux_index, mode in enumerate(modes):
        mode_key = (mode.side, int(mode.m), int(mode.n), complex(mode.k_vector[2]))
        if mode_key != component_key or component_right_entries is None:
            t_component = time.perf_counter()
            if assembly_time_system is not None:
                if component_full_vectors is not None:
                    for vector in component_full_vectors:
                        vector.destroy()
                component_full_vectors = (
                    surface_assemblers[
                        (mode.side, 0)
                    ].assemble_unconstrained_vector(mode),
                    surface_assemblers[
                        (mode.side, 1)
                    ].assemble_unconstrained_vector(mode),
                )
                right_vectors = tuple(
                    condense_unconstrained_vector_to_active_trace(
                        assembly_time_system,
                        vector,
                        side="right",
                    )
                    for vector in component_full_vectors
                )
                left_vectors = tuple(
                    condense_unconstrained_vector_to_active_trace(
                        assembly_time_system,
                        vector,
                        side="left",
                    )
                    for vector in component_full_vectors
                )
                component_right_entries = tuple(
                    _vec_nonzero_owned_entries(vector)
                    for vector in right_vectors
                )
                component_left_entries = tuple(
                    _vec_nonzero_owned_entries(vector)
                    for vector in left_vectors
                )
                for vector in (*right_vectors, *left_vectors):
                    vector.destroy()
                component_interior_bilinear = np.asarray(
                    [
                        [
                            cell_interior_schur_bilinear(
                                assembly_time_system,
                                left,
                                right,
                            )
                            for right in component_full_vectors
                        ]
                        for left in component_full_vectors
                    ],
                    dtype=np.complex128,
                )
            else:
                component_right_entries = (
                    surface_assemblers[
                        (mode.side, 0)
                    ].assemble_entries(mode, floquet_data.mpc),
                    surface_assemblers[
                        (mode.side, 1)
                    ].assemble_entries(mode, floquet_data.mpc),
                )
                component_left_entries = component_right_entries
                component_interior_bilinear = None
            modal_vector_assembly_seconds_local += time.perf_counter() - t_component
            component_key = mode_key
            unique_surface_orders += 1
            component_vector_assemblies += 2
        else:
            component_vector_cache_hits += 1

        if component_left_entries is None:
            raise RuntimeError("DtN left component cache is unavailable")
        traction_vector = _traction_vector(mode, cfg)
        ell_cols, ell_values = _combine_owned_entries(
            component_left_entries,
            (mode.e_vector[0], mode.e_vector[1]),
        )
        traction_rows, traction_values = _combine_owned_entries(
            component_right_entries,
            (traction_vector[0], traction_vector[1]),
        )
        aux_global = n_fe + aux_index
        denominator = _mode_projection_denominator(mode, cfg)
        incident_projection = _incident_projection_onto_top_mode(mode, cfg)
        incident_projections.append(incident_projection)

        t_insert = time.perf_counter()
        if len(traction_rows):
            traction_rows_total_local += int(len(traction_rows))
            A_aug.setValues(
                traction_rows,
                _idx([aux_global]),
                (-traction_values).reshape((len(traction_rows), 1)),
                addv=matrix_insert_mode,
            )
            if incident_projection != 0.0:
                b_aug.setValues(
                    traction_rows,
                    -traction_values * incident_projection,
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
        if (
            incident_projection != 0.0
            and assembly_time_full_rhs is not None
            and component_full_vectors is not None
        ):
            for coefficient, vector in zip(
                traction_vector[:2],
                component_full_vectors,
                strict=True,
            ):
                assembly_time_full_rhs.axpy(
                    PETSc.ScalarType(
                        -incident_projection * coefficient
                    ),
                    vector,
                )

        if len(ell_cols):
            ell_cols_total_local += int(len(ell_cols))
            A_aug.setValues(
                _idx([aux_global]),
                ell_cols,
                (-np.conj(ell_values) / denominator).reshape((1, len(ell_cols))),
                addv=matrix_insert_mode,
            )
        auxiliary_diagonal = 1.0 + 0.0j
        if component_interior_bilinear is not None:
            electric = np.asarray(
                mode.e_vector[:2],
                dtype=np.complex128,
            )
            traction = np.asarray(
                traction_vector[:2],
                dtype=np.complex128,
            )
            auxiliary_diagonal -= complex(
                np.vdot(
                    electric,
                    component_interior_bilinear @ traction,
                )
                / denominator
            )
        if matrix_row_start <= aux_global < matrix_row_end:
            A_aug.setValue(
                aux_global,
                aux_global,
                PETSc.ScalarType(auxiliary_diagonal),
                addv=matrix_insert_mode,
            )
        modal_block_insert_seconds_local += time.perf_counter() - t_insert

        if log is not None and (aux_index + 1) % 50 == 0:
            elapsed = comm.allreduce(time.perf_counter() - stage_start, op=MPI.MAX)
            log(
                f"Stage-4 DtN prepared {aux_index + 1}/{n_aux} auxiliary modes "
                f"in {elapsed:.3f} seconds; unique surface orders = {unique_surface_orders}"
            )

    if component_full_vectors is not None:
        for vector in component_full_vectors:
            vector.destroy()

    timing_details["stage4_dtn_modal_loop_seconds"] = float(
        comm.allreduce(time.perf_counter() - modal_loop_start, op=MPI.MAX)
    )
    timing_details["stage4_dtn_modal_vector_assembly_seconds"] = float(
        comm.allreduce(modal_vector_assembly_seconds_local, op=MPI.MAX)
    )
    timing_details["stage4_dtn_modal_block_insert_seconds"] = float(
        comm.allreduce(modal_block_insert_seconds_local, op=MPI.MAX)
    )
    timing_details["stage4_dtn_unique_surface_orders"] = int(comm.allreduce(unique_surface_orders, op=MPI.MAX))
    timing_details["stage4_dtn_component_vector_assemblies"] = int(
        comm.allreduce(component_vector_assemblies, op=MPI.MAX)
    )
    timing_details["stage4_dtn_component_vector_cache_hits"] = int(
        comm.allreduce(component_vector_cache_hits, op=MPI.MAX)
    )
    traction_rows_total = int(comm.allreduce(traction_rows_total_local, op=MPI.SUM))
    ell_cols_total = int(comm.allreduce(ell_cols_total_local, op=MPI.SUM))
    dtn_auxiliary_block_stats = _local_augmented_dtn_coupling_stats(
        n_fe=n_fe,
        n_aux=n_aux,
        traction_rows_total=traction_rows_total,
        ell_cols_total=ell_cols_total,
    )
    if log is not None:
        log(
            "Stage-4 DtN modal cache summary: "
            f"unique surface orders = {timing_details['stage4_dtn_unique_surface_orders']}, "
            f"x/y component vector assemblies = {timing_details['stage4_dtn_component_vector_assemblies']}, "
            f"polarization cache hits = {timing_details['stage4_dtn_component_vector_cache_hits']}"
        )
        log(f"Stage-4 DtN base matrix nnz = {base_matrix_stats.get('matrix_nnz_used')}")
        log(
            f"Stage-4 DtN auxiliary coupling nnz estimate = {dtn_auxiliary_block_stats['dtn_auxiliary_coupling_nnz_estimate']}"
        )

    _write_progress_event(
        out_dir,
        comm,
        stage="after_dtn_coupling_insert",
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        petsc_options=petsc_options,
        extra={
            "stage4_dtn_num_auxiliary_dofs": int(n_aux),
            "dtn_auxiliary_block_stats": dtn_auxiliary_block_stats,
        },
    )

    t0 = time.perf_counter()
    A_aug.assemble()
    b_aug.assemble()
    augmented_matrix_stats_after_finalize = _petsc_matrix_stats(A_aug)
    timing_details["stage4_dtn_augmented_matrix_finalize_seconds"] = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    )
    _write_progress_event(
        out_dir,
        comm,
        stage="stage4_dtn_augmented_matrix_finalized",
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        matrix_stats=augmented_matrix_stats_after_finalize,
        petsc_options=petsc_options,
        extra={"stage4_dtn_num_auxiliary_dofs": int(n_aux)},
    )

    if cfg.matrix_diagnostics_assemble_only:
        x_aug = b_aug.duplicate()
        ksp = PETSc.KSP().create(A_aug.getComm())
        ksp.setOptionsPrefix(f"stage4_3d_dtn_{cfg.case_name}_")
        ksp.setOperators(A_aug)
        opts = PETSc.Options()
        opts.prefixPush(f"stage4_3d_dtn_{cfg.case_name}_")
        for key, value in petsc_options.items():
            opts[key] = value
        ksp.setFromOptions()
        for key in petsc_options.keys():
            del opts[key]
        opts.prefixPop()
        E_total = fem.Function(floquet_data.mpc.function_space, name="E_total")
        solver_info = {
            "solver_backend": "PETSc augmented auxiliary Fourier-DtN port with dolfinx_mpc Floquet constraints",
            "assemble_only": True,
            "num_auxiliary_dofs": int(n_aux),
            "num_fem_dofs_after_mpc": int(n_fe),
            "num_total_augmented_dofs": int(n_fe + n_aux),
            "stage4_dtn_assembly_seconds": float(comm.allreduce(time.perf_counter() - stage_start, op=MPI.MAX)),
            "ksp_converged_reason": 0,
            "ksp_iterations": 0,
            "actual_ksp_type": ksp.getType(),
            "actual_pc_type": ksp.getPC().getType(),
            "actual_pc_factor_solver_type": None,
            "dtn_base_matrix_stats": base_matrix_stats,
            "dtn_augmented_matrix_stats_after_finalize": augmented_matrix_stats_after_finalize,
            "dtn_auxiliary_block_stats": dtn_auxiliary_block_stats,
            "explicit_chac_constructed": False,
            "dtn_auxiliary_dense_block_constructed": False,
            **timing_details,
        }
        return {
            "E_total": E_total,
            "A": A_aug,
            "b": b_aug,
            "x": x_aug,
            "ksp": ksp,
            "solver_info": solver_info,
            "port_metrics": {
                "R_total": None,
                "T_total": None,
                "R_plus_T": None,
                "A_balance": None,
                "diffraction_total_power_source": "assemble_only_skipped",
                **_port_mode_count_metrics(modes),
            },
        }

    condensed_system = None
    condensed_matrix_stats = None
    independent_trace_system = None
    independent_trace_matrix_stats = None
    condensation_recovery = None
    solve_A = A_aug
    solve_b = b_aug
    solve_dofs = (
        int(assembly_time_system.active_rows + n_aux)
        if assembly_time_system is not None
        else int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs)
    )
    solve_prefix = (
        f"stage4_3d_dtn_assembly_time_condensed_{cfg.case_name}_"
        if assembly_time_system is not None
        else f"stage4_3d_dtn_{cfg.case_name}_"
    )
    if (
        cfg.stage4_cell_static_condensation
        and assembly_time_system is None
    ):
        condensation_started = time.perf_counter()
        _write_progress_event(
            out_dir,
            comm,
            stage="stage4_dtn_cell_static_condensation",
            status="begin",
            started=started,
            dofs=solve_dofs,
            constraints=floquet_data.num_constraints,
            matrix_stats=augmented_matrix_stats_after_finalize,
            petsc_options=petsc_options,
        )
        condensed_system = build_explicit_cell_static_condensation(
            A_aug,
            b_aug,
            owned_hcurl_cell_interior_dofs(V),
        )
        condensed_matrix_stats = _petsc_matrix_stats(condensed_system.matrix)
        timing_details["stage4_dtn_cell_static_condensation_build_seconds"] = (
            float(
                comm.allreduce(
                    time.perf_counter() - condensation_started,
                    op=MPI.MAX,
                )
            )
        )
        solve_A = condensed_system.matrix
        solve_b = condensed_system.rhs
        solve_dofs = int(condensed_system.trace_rows)
        solve_prefix = f"stage4_3d_dtn_cell_condensed_{cfg.case_name}_"
        _write_progress_event(
            out_dir,
            comm,
            stage="stage4_dtn_cell_static_condensation",
            status="end",
            started=started,
            dofs=solve_dofs,
            constraints=floquet_data.num_constraints,
            matrix_stats=condensed_matrix_stats,
            petsc_options=petsc_options,
            extra={
                "cell_static_condensation": condensed_system.build_audit,
            },
        )
        if cfg.stage4_floquet_slave_elimination:
            independent_started = time.perf_counter()
            dofmap = V.dofmap
            if int(dofmap.index_map_bs) != 1:
                raise NotImplementedError(
                    "Floquet slave elimination requires scalar-blocked H(curl)"
                )
            local_slaves = np.unique(
                np.asarray(
                    floquet_data.local_slave_dofs,
                    dtype=np.int64,
                )
            )
            owned_slaves = local_slaves[
                (local_slaves >= 0)
                & (local_slaves < int(dofmap.index_map.size_local))
            ]
            owned_slave_original_dofs = (
                owned_slaves + int(dofmap.index_map.local_range[0])
            ).astype(PETSc.IntType)
            independent_trace_system = (
                build_floquet_independent_trace_system(
                    condensed_system.matrix,
                    condensed_system.rhs,
                    owned_slave_original_dofs=owned_slave_original_dofs,
                    original_to_trace=condensed_system.original_to_trace,
                )
            )
            independent_trace_matrix_stats = _petsc_matrix_stats(
                independent_trace_system.matrix
            )
            timing_details[
                "stage4_dtn_floquet_slave_elimination_build_seconds"
            ] = float(
                comm.allreduce(
                    time.perf_counter() - independent_started,
                    op=MPI.MAX,
                )
            )
            solve_A = independent_trace_system.matrix
            solve_b = independent_trace_system.rhs
            solve_dofs = int(independent_trace_system.active_rows)
            solve_prefix = (
                f"stage4_3d_dtn_cell_condensed_floquet_independent_"
                f"{cfg.case_name}_"
            )
            _write_progress_event(
                out_dir,
                comm,
                stage="stage4_dtn_floquet_slave_elimination",
                status="end",
                started=started,
                dofs=solve_dofs,
                constraints=floquet_data.num_constraints,
                matrix_stats=independent_trace_matrix_stats,
                petsc_options=petsc_options,
                extra={
                    "floquet_slave_elimination": (
                        independent_trace_system.build_audit
                    ),
                },
            )

    t0 = time.perf_counter()
    try:
        solve_x, ksp, ksp_telemetry = _solve_augmented_system(
            solve_A,
            solve_b,
            petsc_options,
            solve_prefix,
            out_dir=out_dir,
            comm=comm,
            started=started,
            dofs=solve_dofs,
            constraints=floquet_data.num_constraints,
            matrix_stats=(
                independent_trace_matrix_stats
                if independent_trace_matrix_stats is not None
                else condensed_matrix_stats
                if condensed_matrix_stats is not None
                else augmented_matrix_stats_after_finalize
            ),
            factorization_only=cfg.matrix_diagnostics_factorization_only,
        )
    except DirectSolveFailure as exc:
        exc.timing_details.update(timing_details)
        exc.extra_summary.setdefault("solver_info", {})
        exc.extra_summary["solver_info"].update(
            {
                "num_auxiliary_dofs": int(n_aux),
                "dtn_base_matrix_stats": base_matrix_stats,
                "dtn_augmented_matrix_stats_after_finalize": augmented_matrix_stats_after_finalize,
                "dtn_auxiliary_block_stats": dtn_auxiliary_block_stats,
                "cell_static_condensation": (
                    None
                    if condensed_system is None
                    else condensed_system.build_audit
                ),
                "dtn_condensed_matrix_stats": condensed_matrix_stats,
                "dtn_floquet_independent_matrix_stats": (
                    independent_trace_matrix_stats
                ),
                "floquet_slave_elimination": (
                    None
                    if independent_trace_system is None
                    else independent_trace_system.build_audit
                ),
                "assembly_time_cell_static_condensation": (
                    None
                    if assembly_time_system is None
                    else assembly_time_system.build_audit
                ),
            }
        )
        raise
    setup_and_solve_seconds = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    )
    if cfg.matrix_diagnostics_factorization_only:
        timing_details["stage4_dtn_factorization_seconds"] = setup_and_solve_seconds
        E_total = fem.Function(floquet_data.mpc.function_space, name="E_total")
        solver_info = {
            "solver_backend": "PETSc augmented auxiliary Fourier-DtN port with dolfinx_mpc Floquet constraints",
            "assemble_only": False,
            "factorization_only": True,
            "num_auxiliary_dofs": int(n_aux),
            "num_fem_dofs_after_mpc": int(n_fe),
            "num_total_augmented_dofs": int(n_fe + n_aux),
            "stage4_dtn_assembly_seconds": float(
                comm.allreduce(time.perf_counter() - stage_start, op=MPI.MAX)
            ),
            "ksp_converged_reason": 0,
            "ksp_iterations": 0,
            "actual_ksp_type": ksp.getType(),
            "actual_pc_type": ksp.getPC().getType(),
            "actual_pc_factor_solver_type": None,
            "dtn_base_matrix_stats": base_matrix_stats,
            "dtn_augmented_matrix_stats_after_finalize": augmented_matrix_stats_after_finalize,
            "dtn_auxiliary_block_stats": dtn_auxiliary_block_stats,
            "explicit_chac_constructed": False,
            "dtn_auxiliary_dense_block_constructed": False,
            **ksp_telemetry,
            **timing_details,
        }
        try:
            solver_info["actual_pc_factor_solver_type"] = (
                ksp.getPC().getFactorSolverType()
            )
        except Exception:
            solver_info["actual_pc_factor_solver_type"] = None
        return {
            "E_total": E_total,
            "A": A_aug,
            "b": b_aug,
            "x": solve_x,
            "ksp": ksp,
            "solver_info": solver_info,
            "port_metrics": {
                "R_total": None,
                "T_total": None,
                "R_plus_T": None,
                "A_balance": None,
                "diffraction_total_power_source": (
                    "factorization_only_skipped_solve"
                ),
                **_port_mode_count_metrics(modes),
            },
        }
    timing_details["stage4_dtn_linear_solve_seconds"] = setup_and_solve_seconds

    assembly_time_field = None
    embedded_fe_solution = None
    if assembly_time_system is not None:
        if assembly_time_full_rhs is None:
            raise RuntimeError(
                "assembly-time recovery requires the full-space RHS"
            )
        recovery_started = time.perf_counter()
        (
            assembly_time_field,
            embedded_fe_solution,
            condensation_recovery,
        ) = (
            _assign_fe_solution_from_assembly_time_condensation(
                solve_x,
                assembly_time_system,
                floquet_data,
                assembly_time_full_rhs,
            )
        )
        x_aug = solve_x
        timing_details[
            "stage4_dtn_cell_static_condensation_recovery_seconds"
        ] = float(
            comm.allreduce(
                time.perf_counter() - recovery_started,
                op=MPI.MAX,
            )
        )
    elif condensed_system is not None:
        recovery_started = time.perf_counter()
        expanded_trace_solution = (
            expand_floquet_independent_trace_solution(
                condensed_system.rhs,
                independent_trace_system,
                solve_x,
            )
            if independent_trace_system is not None
            else None
        )
        x_aug, condensation_recovery = recover_full_solution(
            A_aug,
            b_aug,
            condensed_system,
            (
                expanded_trace_solution
                if expanded_trace_solution is not None
                else solve_x
            ),
        )
        if expanded_trace_solution is not None:
            expanded_trace_solution.destroy()
        timing_details["stage4_dtn_cell_static_condensation_recovery_seconds"] = (
            float(
                comm.allreduce(
                    time.perf_counter() - recovery_started,
                    op=MPI.MAX,
                )
            )
        )
    else:
        x_aug = solve_x

    if (
        assembly_time_system is not None
        and embedded_fe_solution is not None
    ):
        residual_started = time.perf_counter()
        linear_residual = _assembly_time_full_operator_residual(
            a,
            floquet_data,
            embedded_fe_solution,
            A_aug,
            b_aug,
            x_aug,
            assembly_time_system,
            assembly_time_full_rhs,
        )
        embedded_fe_solution.destroy()
        embedded_fe_solution = None
        assembly_time_full_rhs.destroy()
        assembly_time_full_rhs = None
        timing_details[
            "stage4_dtn_matrix_free_full_residual_seconds"
        ] = float(
            comm.allreduce(
                time.perf_counter() - residual_started,
                op=MPI.MAX,
            )
        )
    else:
        linear_residual = _linear_residual(A_aug, b_aug, x_aug)
    _write_progress_event(
        out_dir,
        comm,
        stage="after_true_residual",
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        matrix_stats=augmented_matrix_stats_after_finalize,
        petsc_options=petsc_options,
        extra={"linear_system_relative_residual": linear_residual.get("linear_system_relative_residual")},
    )

    t0 = time.perf_counter()
    E_total = (
        assembly_time_field
        if assembly_time_field is not None
        else _assign_fe_solution_from_augmented(
            x_aug,
            floquet_data,
            n_aux,
        )
    )
    timing_details["stage4_dtn_solution_backsubstitution_seconds"] = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    )
    _write_progress_event(
        out_dir,
        comm,
        stage="after_fe_field_reconstruction",
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        petsc_options=petsc_options,
    )
    _write_progress_event(
        out_dir,
        comm,
        stage="after_augmented_matrix_finalize",
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        matrix_stats=augmented_matrix_stats_after_finalize,
        petsc_options=petsc_options,
    )
    aux_values = _gather_auxiliary_values(x_aug, n_fe, n_aux, comm)
    port_metrics = _port_power_metrics(cfg, modes, aux_values, incident_projections)
    port_metrics.update(timing_details)
    _write_port_outputs(out_dir, cfg, modes, aux_values, incident_projections, port_metrics, comm)
    _write_progress_event(
        out_dir,
        comm,
        stage="after_official_rta",
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        petsc_options=petsc_options,
        extra={
            "R_total": port_metrics.get("R_total"),
            "T_total": port_metrics.get("T_total"),
        },
    )

    cell_static_condensation_audit = None
    if condensed_system is not None:
        cell_static_condensation_audit = {
            **condensed_system.build_audit,
            "condensed_matrix_stats": condensed_matrix_stats,
            "floquet_independent_matrix_stats": (
                independent_trace_matrix_stats
            ),
            "floquet_slave_elimination": (
                None
                if independent_trace_system is None
                else independent_trace_system.build_audit
            ),
            "recovery": condensation_recovery,
            "full_explicit_true_residual": linear_residual,
            "same_full_operator_used_for_recovery_and_residual": True,
            "ordinary_default_changed": False,
        }
    elif assembly_time_system is not None:
        cell_static_condensation_audit = {
            **assembly_time_system.build_audit,
            "condensed_matrix_stats": (
                augmented_matrix_stats_after_finalize
            ),
            "floquet_independent_matrix_stats": (
                augmented_matrix_stats_after_finalize
            ),
            "floquet_slave_elimination": (
                assembly_time_system.trace_constraints.build_audit
            ),
            "recovery": condensation_recovery,
            "full_operator_true_residual": linear_residual,
            "full_explicit_true_residual": linear_residual,
            "true_residual_semantics": (
                "exact physically reduced C_t^H Schur C_t plus DtN "
                "operator residual; full FE matrix deliberately not allocated"
            ),
            "same_full_operator_used_for_recovery_and_residual": False,
            "ordinary_default_changed": False,
        }
    solver_info = {
        "solver_backend": (
            "PETSc assembly-time exact cell-interior trace Schur + direct "
            "Floquet-independent insertion + auxiliary Fourier-DtN port"
            if assembly_time_system is not None
            else
            "PETSc exact cell-interior trace Schur + auxiliary Fourier-DtN "
            "port with dolfinx_mpc Floquet constraints"
            if condensed_system is not None
            else "PETSc augmented auxiliary Fourier-DtN port with "
            "dolfinx_mpc Floquet constraints"
        ),
        "num_auxiliary_dofs": int(n_aux),
        "num_original_fem_dofs": int(
            V.dofmap.index_map.size_global * V.dofmap.index_map_bs
        ),
        "num_fem_dofs_after_mpc": int(
            V.dofmap.index_map.size_global * V.dofmap.index_map_bs
        ),
        "num_active_trace_dofs": (
            None
            if assembly_time_system is None
            else int(assembly_time_system.active_rows)
        ),
        "num_total_augmented_dofs": int(n_fe + n_aux),
        "num_active_condensed_dofs": (
            int(assembly_time_system.active_rows + n_aux)
            if assembly_time_system is not None
            else None
            if condensed_system is None
            else int(condensed_system.trace_rows)
        ),
        "stage4_cell_static_condensation": bool(
            condensed_system is not None
            or assembly_time_system is not None
        ),
        "stage4_assembly_time_cell_static_condensation": bool(
            assembly_time_system is not None
        ),
        "stage4_floquet_slave_elimination": bool(
            independent_trace_system is not None
            or assembly_time_system is not None
        ),
        "cell_static_condensation": cell_static_condensation_audit,
        "stage4_dtn_assembly_seconds": float(comm.allreduce(time.perf_counter() - stage_start, op=MPI.MAX)),
        "ksp_converged_reason": int(ksp.getConvergedReason()),
        "ksp_iterations": int(ksp.getIterationNumber()),
        "actual_ksp_type": ksp.getType(),
        "actual_pc_type": ksp.getPC().getType(),
        "actual_pc_factor_solver_type": None,
        "dtn_base_matrix_stats": base_matrix_stats,
        "dtn_augmented_matrix_stats_after_finalize": augmented_matrix_stats_after_finalize,
        "dtn_condensed_matrix_stats": (
            augmented_matrix_stats_after_finalize
            if assembly_time_system is not None
            else condensed_matrix_stats
        ),
        "dtn_floquet_independent_matrix_stats": (
            augmented_matrix_stats_after_finalize
            if assembly_time_system is not None
            else independent_trace_matrix_stats
        ),
        "dtn_auxiliary_block_stats": dtn_auxiliary_block_stats,
        "explicit_chac_constructed": False,
        "dtn_auxiliary_dense_block_constructed": False,
        **ksp_telemetry,
        **timing_details,
        **linear_residual,
    }
    try:
        solver_info["actual_pc_factor_solver_type"] = ksp.getPC().getFactorSolverType()
    except Exception:
        solver_info["actual_pc_factor_solver_type"] = None

    if condensed_system is not None:
        if independent_trace_system is not None:
            returned_A = independent_trace_system.matrix
            returned_b = independent_trace_system.rhs
            condensed_system.destroy()
        else:
            returned_A = condensed_system.matrix
            returned_b = condensed_system.rhs
        returned_x = solve_x
        A_aug.destroy()
        b_aug.destroy()
        x_aug.destroy()
    else:
        returned_A = A_aug
        returned_b = b_aug
        returned_x = x_aug

    return {
        "E_total": E_total,
        "A": returned_A,
        "b": returned_b,
        "x": returned_x,
        "ksp": ksp,
        "solver_info": solver_info,
        "port_metrics": port_metrics,
        "goal_context": {
            "num_fem_dofs_after_mpc": int(n_fe),
            "modes": modes,
            "auxiliary_values": aux_values,
            "incident_projections": incident_projections,
            "normalization": "finite-port outgoing modal power / incident power",
        },
    }
