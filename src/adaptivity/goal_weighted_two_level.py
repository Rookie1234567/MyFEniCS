"""Goal-weighted enriched residual localization for Task035.

This research estimator lifts the solved p2 field and its DtN auxiliary modal
amplitudes into the actual p3 augmented system, forms the true algebraic
residual ``r_3=b_3-A_3 x_2^3``, and weights it with an actual p3 discrete
adjoint.  Spatial marking distributes the non-negative algebraic products
``|conj(z_i) r_i|`` over the incident tetrahedra of each Nedelec degree of
freedom.  It is intentionally labelled an algebraic/hierarchical DWR
localization rather than a strong cell/face residual estimator.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import time
from typing import Any

import numpy as np
import ufl
from mpi4py import MPI
from petsc4py import PETSc

from dolfinx import fem, la
from dolfinx.fem import petsc as fem_petsc

from .dtn_goal_adjoint import (
    build_dtn_power_goal_gradient,
    evaluate_actual_dtn_power_adjoints,
    solve_hermitian_discrete_adjoint,
)
from .cell_indicator_snapshot import build_cell_indicator_snapshot
from src.solvers.dtn_port_3d import _assign_fe_solution_from_augmented
from .global_two_level_r5 import (
    _global_dorfler_mark,
    _require_official_summary,
    localize_global_two_level_correction,
)
from src.geometry.tetra_mesh_audit import (
    canonical_owned_cell_ids,
    geometry_key_sha256,
)


TINY = np.finfo(float).tiny


def _interpolate_to_enriched(
    coarse_field: fem.Function,
    enriched_space,
    *,
    padding: float = 1.0e-10,
) -> fem.Function:
    tdim = enriched_space.mesh.topology.dim
    cell_map = enriched_space.mesh.topology.index_map(tdim)
    cells = np.arange(
        cell_map.size_local + cell_map.num_ghosts,
        dtype=np.int32,
    )
    interpolation_data = fem.create_interpolation_data(
        enriched_space,
        coarse_field.function_space,
        cells,
        padding=float(padding),
    )
    result = fem.Function(enriched_space, name="E_coarse_lifted_to_enriched")
    result.interpolate_nonmatching(coarse_field, cells, interpolation_data)
    result.x.scatter_forward()
    return result


def _lift_to_augmented_state(
    field: fem.Function,
    auxiliary_values: np.ndarray,
    *,
    floquet_data,
    template: PETSc.Vec,
) -> PETSc.Vec:
    """Homogenize MPC slaves and copy a full FE field into augmented rows."""

    space = field.function_space
    index_map = space.dofmap.index_map
    block_size = int(space.dofmap.index_map_bs)
    if block_size != 1:
        raise NotImplementedError("Task035 Nedelec augmented lift expects block size 1")
    reduced_field = fem.Function(space, name="E_coarse_reduced_for_residual")
    reduced_field.x.array[:] = field.x.array
    reduced_field.x.scatter_forward()
    floquet_data.mpc.homogenize(reduced_field)

    result = template.duplicate()
    result.set(PETSc.ScalarType(0.0))
    owned_count = int(index_map.size_local)
    local_dofs = np.arange(owned_count, dtype=np.int32)
    global_dofs = np.asarray(index_map.local_to_global(local_dofs), dtype=np.int64)
    if len(global_dofs):
        result.setValues(
            np.asarray(global_dofs, dtype=PETSc.IntType),
            np.asarray(
                reduced_field.x.array[:owned_count], dtype=PETSc.ScalarType
            ),
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
    n_fe = int(index_map.size_global)
    auxiliary = np.asarray(auxiliary_values, dtype=np.complex128)
    indices = np.arange(n_fe, n_fe + len(auxiliary), dtype=np.int64)
    row_start, row_end = result.getOwnershipRange()
    owned = (indices >= row_start) & (indices < row_end)
    if np.any(owned):
        result.setValues(
            np.asarray(indices[owned], dtype=PETSc.IntType),
            np.asarray(auxiliary[owned], dtype=PETSc.ScalarType),
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
    result.assemble()
    return result


def build_enriched_discrete_residual(
    coarse_field: fem.Function,
    coarse_auxiliary_values: np.ndarray,
    *,
    enriched_field: fem.Function,
    enriched_linear_system: dict[str, Any],
    enriched_floquet_data,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Form the actual p3 residual of a lifted solved p2 state."""

    lifted_field = _interpolate_to_enriched(
        coarse_field, enriched_field.function_space
    )
    lifted_state = _lift_to_augmented_state(
        lifted_field,
        coarse_auxiliary_values,
        floquet_data=enriched_floquet_data,
        template=enriched_linear_system["x"],
    )
    matrix = enriched_linear_system["A"]
    right_hand_side = enriched_linear_system["b"]
    residual = right_hand_side.copy()
    action = right_hand_side.duplicate()
    matrix.mult(lifted_state, action)
    residual.axpy(PETSc.ScalarType(-1.0), action)
    rhs_norm = float(right_hand_side.norm())
    residual_norm = float(residual.norm())
    enriched_residual = right_hand_side.copy()
    matrix.mult(enriched_linear_system["x"], enriched_residual)
    enriched_residual.axpy(PETSc.ScalarType(-1.0), right_hand_side)
    report = {
        "actual_enriched_matrix_residual": True,
        "coarse_lift": "DOLFINx nonmatching Nedelec interpolation plus MPC homogenize",
        "coarse_auxiliary_amplitudes_lifted": int(
            len(coarse_auxiliary_values)
        ),
        "residual_norm": residual_norm,
        "residual_relative_to_rhs": residual_norm / max(rhs_norm, TINY),
        "enriched_solution_relative_residual_recomputed": float(
            enriched_residual.norm() / max(rhs_norm, TINY)
        ),
    }
    action.destroy()
    lifted_state.destroy()
    enriched_residual.destroy()
    return residual, report


def localize_algebraic_dwr_products(
    residual: PETSc.Vec,
    adjoint: PETSc.Vec,
    space,
    *,
    theta: float,
) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    """Distribute ``|conj(z_i) r_i|`` over incident owned cells."""

    msh = space.mesh
    comm = msh.comm
    tdim = msh.topology.dim
    cell_map = msh.topology.index_map(tdim)
    dof_map = space.dofmap.index_map
    if int(space.dofmap.index_map_bs) != 1:
        raise NotImplementedError("Task035 DWR localization expects block size 1")
    row_start, row_end = residual.getOwnershipRange()
    dof_start, dof_end = dof_map.local_range
    if row_start != dof_start or row_end < dof_end:
        raise RuntimeError("augmented FE row ownership does not match the space")

    residual_owned = np.asarray(
        residual.getArray(readonly=True), dtype=np.complex128
    )
    adjoint_owned = np.asarray(
        adjoint.getArray(readonly=True), dtype=np.complex128
    )
    owned_dofs = int(dof_map.size_local)
    fe_products = np.abs(
        np.conj(adjoint_owned[:owned_dofs])
        * residual_owned[:owned_dofs]
    )
    auxiliary_products_local = float(
        np.sum(
            np.abs(
                np.conj(adjoint_owned[owned_dofs:])
                * residual_owned[owned_dofs:]
            )
        )
    )

    carrier = fem.Function(space, name="absolute_algebraic_dwr_product")
    carrier.x.array[:] = 0.0
    carrier.x.array[:owned_dofs] = fe_products
    carrier.x.scatter_forward()
    incidence_carrier = fem.Function(
        space, name="global_incident_owned_cell_count"
    )
    incidence_carrier.x.array[:] = 0.0
    for cell in range(cell_map.size_local):
        incidence_carrier.x.array[space.dofmap.cell_dofs(cell)] += 1.0
    incidence_carrier.x.scatter_reverse(la.InsertMode.add)
    incidence_carrier.x.scatter_forward()
    incidence = incidence_carrier.x.array.real

    owned_cells = np.arange(cell_map.size_local, dtype=np.int32)
    if any(
        np.any(incidence[space.dofmap.cell_dofs(int(cell))] <= 0.0)
        for cell in owned_cells
    ):
        raise RuntimeError("an owned-cell dof has zero global incidence")
    cell_values = np.asarray(
        [
            float(
                np.sum(
                    carrier.x.array[space.dofmap.cell_dofs(int(cell))].real
                    / incidence[space.dofmap.cell_dofs(int(cell))]
                )
            )
            for cell in owned_cells
        ],
        dtype=np.float64,
    )
    (
        canonical_cell_ids,
        geometry_records,
        global_keys,
    ) = canonical_owned_cell_ids(msh)
    record_by_local = {
        record.local_index: record for record in geometry_records
    }
    marked_canonical, marking = _global_dorfler_mark(
        comm,
        canonical_cell_ids,
        cell_values,
        theta=float(theta),
    )
    marked_canonical_set = set(int(value) for value in marked_canonical)
    local_marked_global = [
        record_by_local[int(cell)].global_index
        for cell, canonical_id in zip(
            owned_cells, canonical_cell_ids, strict=True
        )
        if int(canonical_id) in marked_canonical_set
    ]
    marked_global = sorted(
        value
        for packet in comm.allgather(local_marked_global)
        for value in packet
    )
    marked_keys = [global_keys[index] for index in marked_canonical]
    fe_product_sum = float(
        comm.allreduce(float(np.sum(fe_products)), op=MPI.SUM)
    )
    auxiliary_product_sum = float(
        comm.allreduce(auxiliary_products_local, op=MPI.SUM)
    )
    cell_sum = float(
        comm.allreduce(float(np.sum(cell_values)), op=MPI.SUM)
    )
    signed_dwr = complex(adjoint.dot(residual))
    mesh_geometry_sha256 = geometry_key_sha256(global_keys)
    localization = {
        "estimator": "actual_adjoint_enriched_algebraic_residual_DWR",
        "formal_strong_cell_face_residual": False,
        "localization": (
            "absolute algebraic conj(z_i)*r_i distributed over incident "
            "Nedelec cells; auxiliary products reported separately"
        ),
        "global_signed_dwr_real": float(signed_dwr.real),
        "global_signed_dwr_imag": float(signed_dwr.imag),
        "global_dwr_absolute": float(abs(signed_dwr.real)),
        "global_complex_pairing_magnitude_diagnostic": float(
            abs(signed_dwr)
        ),
        "fe_absolute_product_sum": fe_product_sum,
        "auxiliary_absolute_product_sum": auxiliary_product_sum,
        "cell_absolute_product_sum": cell_sum,
        "cell_distribution_relative_closure": float(
            abs(cell_sum - fe_product_sum) / max(fe_product_sum, TINY)
        ),
        "owned_cell_contribution_count": int(cell_map.size_global),
        "finite_nonnegative_cell_contributions": bool(
            np.all(np.isfinite(cell_values)) and np.all(cell_values >= 0.0)
        ),
        "marking": marking,
        "marked_global_cell_ids": marked_global,
        "marked_canonical_cell_ids": marked_canonical.tolist(),
        "marked_geometry_sha256": geometry_key_sha256(marked_keys),
        "mesh_geometry_sha256": mesh_geometry_sha256,
        "cell_indicator_snapshot": build_cell_indicator_snapshot(
            comm,
            canonical_cell_ids,
            cell_values,
            indicator_name=(
                "actual_adjoint_enriched_algebraic_residual_DWR"
            ),
            mesh_geometry_sha256=mesh_geometry_sha256,
        ),
        "partition_independent_marking_identity": (
            "sorted canonical quantized cell geometry"
        ),
    }
    return localization, canonical_cell_ids, cell_values


def localize_physical_adjoint_weighted_correction(
    coarse_field: fem.Function,
    enriched_field: fem.Function,
    adjoint: PETSc.Vec,
    *,
    floquet_data,
    num_auxiliary_dofs: int,
    theta: float,
) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    """Localize a complex H(curl) correction/physical-adjoint pairing."""

    space = enriched_field.function_space
    msh = space.mesh
    comm = msh.comm
    tdim = msh.topology.dim
    cell_map = msh.topology.index_map(tdim)
    lifted = _interpolate_to_enriched(coarse_field, space)
    correction = fem.Function(space, name="E_p_enriched_correction")
    correction.x.array[:] = enriched_field.x.array - lifted.x.array
    correction.x.scatter_forward()
    adjoint_field = _assign_fe_solution_from_augmented(
        adjoint,
        floquet_data,
        int(num_auxiliary_dofs),
    )
    adjoint_field.name = "physical_DtN_goal_adjoint"

    scalar_space = fem.functionspace(msh, ("DG", 0))
    test = ufl.TestFunction(scalar_space)
    cell_diameter = ufl.CellDiameter(msh)
    pairing_density = ufl.inner(correction, adjoint_field) + cell_diameter**2 * ufl.inner(
        ufl.curl(correction), ufl.curl(adjoint_field)
    )
    vector = fem_petsc.assemble_vector(
        fem.form(ufl.inner(pairing_density, test) * ufl.dx)
    )
    vector.ghostUpdate(
        addv=PETSc.InsertMode.ADD_VALUES,
        mode=PETSc.ScatterMode.REVERSE,
    )
    values = np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
    owned_cells = np.arange(cell_map.size_local, dtype=np.int32)
    owned_scalar_dofs = int(scalar_space.dofmap.index_map.size_local)
    complex_cells = np.empty(len(owned_cells), dtype=np.complex128)
    for index, cell in enumerate(owned_cells):
        dofs = scalar_space.dofmap.cell_dofs(int(cell))
        if len(dofs) != 1 or int(dofs[0]) >= owned_scalar_dofs:
            vector.destroy()
            raise RuntimeError("DG0 cell/dof ownership is not one-to-one")
        complex_cells[index] = values[int(dofs[0])]
    vector.destroy()
    cell_values = np.abs(complex_cells).astype(np.float64)

    (
        canonical_cell_ids,
        geometry_records,
        global_keys,
    ) = canonical_owned_cell_ids(msh)
    record_by_local = {
        record.local_index: record for record in geometry_records
    }
    marked_canonical, marking = _global_dorfler_mark(
        comm,
        canonical_cell_ids,
        cell_values,
        theta=float(theta),
    )
    marked_canonical_set = set(int(value) for value in marked_canonical)
    local_marked_global = [
        record_by_local[int(cell)].global_index
        for cell, canonical_id in zip(
            owned_cells, canonical_cell_ids, strict=True
        )
        if int(canonical_id) in marked_canonical_set
    ]
    marked_global = sorted(
        value
        for packet in comm.allgather(local_marked_global)
        for value in packet
    )
    marked_keys = [global_keys[index] for index in marked_canonical]
    complex_sum = complex(comm.allreduce(np.sum(complex_cells), op=MPI.SUM))
    absolute_sum = float(
        comm.allreduce(float(np.sum(cell_values)), op=MPI.SUM)
    )
    mesh_geometry_sha256 = geometry_key_sha256(global_keys)
    return {
        "estimator": "physical_adjoint_weighted_two_level_Hcurl_pairing",
        "formal_strong_cell_face_residual": False,
        "localization": (
            "absolute per-cell integral of <E_p3-I(E_p2),z> + "
            "h_K^2<curl correction,curl z> with reconstructed physical adjoint"
        ),
        "actual_global_enriched_residual_DWR_reported_separately": True,
        "complex_cell_pairing_sum_real": float(complex_sum.real),
        "complex_cell_pairing_sum_imag": float(complex_sum.imag),
        "absolute_cell_pairing_sum": absolute_sum,
        "finite_nonnegative_cell_contributions": bool(
            np.all(np.isfinite(cell_values)) and np.all(cell_values >= 0.0)
        ),
        "owned_cell_contribution_count": int(cell_map.size_global),
        "marking": marking,
        "marked_global_cell_ids": marked_global,
        "marked_canonical_cell_ids": marked_canonical.tolist(),
        "marked_geometry_sha256": geometry_key_sha256(marked_keys),
        "mesh_geometry_sha256": mesh_geometry_sha256,
        "cell_indicator_snapshot": build_cell_indicator_snapshot(
            comm,
            canonical_cell_ids,
            cell_values,
            indicator_name=(
                "physical_adjoint_weighted_two_level_Hcurl_pairing"
            ),
            mesh_geometry_sha256=mesh_geometry_sha256,
        ),
        "partition_independent_marking_identity": (
            "canonical cell geometry plus assembled physical FE cell forms"
        ),
    }, canonical_cell_ids, cell_values


def _marked_overlap(left: list[int], right: list[int]) -> dict[str, Any]:
    left_set = set(int(value) for value in left)
    right_set = set(int(value) for value in right)
    intersection = left_set & right_set
    union = left_set | right_set
    return {
        "intersection_count": len(intersection),
        "union_count": len(union),
        "jaccard": float(len(intersection) / max(len(union), 1)),
        "left_contained_fraction": float(
            len(intersection) / max(len(left_set), 1)
        ),
        "right_contained_fraction": float(
            len(intersection) / max(len(right_set), 1)
        ),
    }


def _tolerance_normalized_multi_goal_values(
    indicators: dict[str, np.ndarray],
    tolerances: dict[str, float],
) -> np.ndarray:
    """Combine independent R/T indicators using accepted component errors."""

    required_goals = ("R_total", "T_total")
    required_tolerances = (*required_goals, "A_volume_total")
    if any(goal not in indicators for goal in required_goals):
        raise ValueError("tolerance-normalized DWR requires R_total and T_total")
    arrays = {
        goal: np.asarray(indicators[goal], dtype=np.float64)
        for goal in required_goals
    }
    if (
        arrays["R_total"].ndim != 1
        or arrays["T_total"].shape != arrays["R_total"].shape
        or any(
            not np.all(np.isfinite(values)) or np.any(values < 0.0)
            for values in arrays.values()
        )
    ):
        raise ValueError("multi-goal cell indicators must be aligned and nonnegative")
    if any(
        goal not in tolerances
        or not np.isfinite(float(tolerances[goal]))
        or float(tolerances[goal]) <= 0.0
        for goal in required_tolerances
    ):
        raise ValueError("multi-goal tolerances must be finite and positive")
    return np.hypot(
        arrays["R_total"] / float(tolerances["R_total"]),
        arrays["T_total"] / float(tolerances["T_total"]),
    )


def _marker_report_from_local_values(
    msh,
    canonical_cell_ids: np.ndarray,
    cell_values: np.ndarray,
    *,
    theta: float,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Build one partition-independent marker report from owned-cell values."""

    ids = np.asarray(canonical_cell_ids, dtype=np.int64)
    values = np.asarray(cell_values, dtype=np.float64)
    cell_map = msh.topology.index_map(msh.topology.dim)
    if (
        ids.ndim != 1
        or values.shape != ids.shape
        or len(ids) != int(cell_map.size_local)
        or not np.all(np.isfinite(values))
        or np.any(values < 0.0)
    ):
        raise ValueError("marker values must cover all owned cells and be nonnegative")
    marked_canonical, marking = _global_dorfler_mark(
        msh.comm,
        ids,
        values,
        theta=float(theta),
    )
    marked_set = set(int(value) for value in marked_canonical)
    canonical_from_geometry, records, ordered_keys = (
        canonical_owned_cell_ids(msh)
    )
    if not np.array_equal(ids, canonical_from_geometry):
        raise ValueError(
            "marker canonical cell IDs do not match the current mesh geometry"
        )
    record_by_local = {record.local_index: record for record in records}
    owned_cells = np.arange(cell_map.size_local, dtype=np.int32)
    local_marked_global = [
        record_by_local[int(cell)].global_index
        for cell, canonical_id in zip(owned_cells, ids, strict=True)
        if int(canonical_id) in marked_set
    ]
    marked_global = sorted(
        value
        for packet in msh.comm.allgather(local_marked_global)
        for value in packet
    )
    local_marked_keys = [
        record_by_local[int(cell)].key
        for cell, canonical_id in zip(owned_cells, ids, strict=True)
        if int(canonical_id) in marked_set
    ]
    marked_keys = [
        key for packet in msh.comm.allgather(local_marked_keys) for key in packet
    ]
    mesh_geometry_sha256 = geometry_key_sha256(ordered_keys)
    return {
        **metadata,
        "finite_nonnegative_cell_contributions": True,
        "cell_contribution_sum": float(
            msh.comm.allreduce(float(np.sum(values)), op=MPI.SUM)
        ),
        "marking": marking,
        "marked_global_cell_ids": marked_global,
        "marked_canonical_cell_ids": marked_canonical.tolist(),
        "marked_geometry_sha256": geometry_key_sha256(marked_keys),
        "mesh_geometry_sha256": mesh_geometry_sha256,
        "cell_indicator_snapshot": build_cell_indicator_snapshot(
            msh.comm,
            ids,
            values,
            indicator_name=str(
                metadata.get("combination", "combined_goal_indicator")
            ),
            mesh_geometry_sha256=mesh_geometry_sha256,
        ),
        "partition_independent_marking_identity": (
            "sorted canonical quantized cell geometry"
        ),
    }


def run_target_goal_weighted_two_level(
    out_dir: Path,
    *,
    coarse_degree: int = 2,
    enriched_degree: int = 3,
    h_nm: float = 50.0,
    theta: float = 0.5,
    polarization_kind: str = "s",
    mesh_cell_type: str = "tetrahedron",
    progress_observer=None,
    mesh_data_override=None,
) -> dict[str, Any]:
    """Compare actual R/T DWR marking with R5 on one solved p2/p3 pair."""

    from src.common.config_3d import target_stage4_config
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )
    from src.adaptivity.target_r5_adaptive_cycles import (
        task034_best_available_observable_reference,
        task034_observable_control,
    )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    captures: dict[str, Any] = {}
    started = time.perf_counter()
    normalization_reference = task034_best_available_observable_reference()
    normalization_control = task034_observable_control("p4_h7p5")
    multi_goal_tolerances = {
        name: abs(
            normalization_control["observables"][name]
            - normalization_reference["observables"][name]
        )
        for name in ("R_total", "T_total", "A_volume_total")
    }
    multi_goal_authority = {
        "definition": (
            "absolute component error of structured p4/h7.5 against the "
            "p4/h5 best available discrete reference"
        ),
        "reference_key": normalization_reference["key"],
        "control_key": normalization_control["key"],
        "record_path": normalization_reference["record_path"],
        "record_sha256": normalization_reference["record_sha256"],
        "absolute_error_tolerances": multi_goal_tolerances,
        "independent_adjoint_goals": ["R_total", "T_total"],
        "separate_strict_adjoint_goal": "R00_total",
        "A_volume_total_treatment": (
            "audited in the post-solve R/T/A vector; no third adjoint because "
            "qualified fields enforce R+T+A_volume=1 and an independent "
            "A_volume goal gradient is not implemented"
        ),
    }

    def progress(stage: str, status: str) -> None:
        if progress_observer is not None:
            progress_observer(stage, status)

    def config(degree: int):
        base = target_stage4_config(degree=degree, h_nm=h_nm)
        return replace(
            base,
            case_name=f"task035_goal_dwr_p{degree}_h{h_nm:g}".replace(
                ".", "p"
            ),
            polarization_kind=polarization_kind,
            custom_polarization=None,
            mesh_cell_type=mesh_cell_type,
            matrix_diagnostics_assemble_only=False,
            matrix_diagnostics_factorization_only=False,
            full3d_reference_export=False,
            direct_release_base_after_augmentation=True,
            unique_output=False,
        )

    def coarse_observer(**state) -> None:
        context = state["dtn_result"]["goal_context"]
        captures["coarse"] = {
            "field": state["field"],
            "auxiliary_values": np.asarray(
                context["auxiliary_values"], dtype=np.complex128
            ).copy(),
        }

    progress("goal_dwr_coarse_solve", "begin")
    coarse_summary = run_stage4b_block_grating_3d_case(
        config(int(coarse_degree)),
        out_dir / f"coarse_p{coarse_degree}",
        solution_observer=coarse_observer,
        mesh_data_override=mesh_data_override,
    )
    _require_official_summary(coarse_summary, "goal-DWR coarse")
    progress("goal_dwr_coarse_solve", "end")

    def enriched_observer(**state) -> None:
        captures["enriched_field"] = state["field"]
        residual, residual_report = build_enriched_discrete_residual(
            captures["coarse"]["field"],
            captures["coarse"]["auxiliary_values"],
            enriched_field=state["field"],
            enriched_linear_system=state["linear_system"],
            enriched_floquet_data=state["floquet_data"],
        )
        localizations: dict[str, Any] = {}
        local_arrays: dict[str, tuple[np.ndarray, np.ndarray]] = {}

        adjoints = evaluate_actual_dtn_power_adjoints(
            linear_system=state["linear_system"],
            dtn_result=state["dtn_result"],
            config=state["config"],
            communicator=state["field"].function_space.mesh.comm,
            official_summary=state["summary"],
        )
        enriched_context = state["dtn_result"]["goal_context"]
        midpoint_context = {
            **enriched_context,
            "auxiliary_values": 0.5
            * (
                captures["coarse"]["auxiliary_values"]
                + np.asarray(
                    enriched_context["auxiliary_values"],
                    dtype=np.complex128,
                )
            ),
        }
        for goal in ("R00_total", "R_total", "T_total"):
            gradient, gradient_metadata = build_dtn_power_goal_gradient(
                state["linear_system"]["x"],
                state["config"],
                midpoint_context,
                goal=goal,
            )
            adjoint, solve_report = solve_hermitian_discrete_adjoint(
                state["linear_system"]["A"],
                state["linear_system"]["ksp"],
                gradient,
                template=state["linear_system"]["x"],
            )
            report, ids, values = localize_physical_adjoint_weighted_correction(
                captures["coarse"]["field"],
                state["field"],
                adjoint,
                floquet_data=state["floquet_data"],
                num_auxiliary_dofs=len(
                    enriched_context["auxiliary_values"]
                ),
                theta=float(theta),
            )
            signed_dwr = complex(adjoint.dot(residual))
            report["global_signed_dwr_real"] = float(signed_dwr.real)
            report["global_signed_dwr_imag"] = float(signed_dwr.imag)
            report["global_dwr_absolute"] = float(abs(signed_dwr.real))
            report["adjoint_linearization"] = (
                "exact quadratic segment-average gradient at (a_p2+a_p3)/2"
            )
            report["gradient"] = gradient_metadata
            report["adjoint_solve"] = solve_report
            localizations[goal] = report
            local_arrays[goal] = (ids, values)
            adjoint.destroy()
            gradient.destroy()
        r00_ids, _r00_values = local_arrays["R00_total"]
        r_ids, r_values = local_arrays["R_total"]
        t_ids, t_values = local_arrays["T_total"]
        if (
            not np.array_equal(r00_ids, r_ids)
            or not np.array_equal(r_ids, t_ids)
        ):
            residual.destroy()
            raise RuntimeError("R00/R/T DWR local cell identities differ")
        r_sum = float(
            state["field"].function_space.mesh.comm.allreduce(
                float(np.sum(r_values)), op=MPI.SUM
            )
        )
        t_sum = float(
            state["field"].function_space.mesh.comm.allreduce(
                float(np.sum(t_values)), op=MPI.SUM
            )
        )
        msh = state["field"].function_space.mesh
        relative_values = (
            r_values / max(r_sum, TINY) + t_values / max(t_sum, TINY)
        )
        relative_report = _marker_report_from_local_values(
            msh,
            r_ids,
            relative_values,
            theta=float(theta),
            metadata={
                "combination": "eta_R/sum(eta_R) + eta_T/sum(eta_T)",
                "normalization": "per-goal global indicator mass",
            },
        )
        tolerance_values = _tolerance_normalized_multi_goal_values(
            {"R_total": r_values, "T_total": t_values},
            multi_goal_tolerances,
        )
        tolerance_report = _marker_report_from_local_values(
            msh,
            r_ids,
            tolerance_values,
            theta=float(theta),
            metadata={
                "combination": (
                    "sqrt((eta_R/tol_R)^2 + (eta_T/tol_T)^2)"
                ),
                "normalization": "accepted structured p4/h7.5 component errors",
                "normalization_authority": multi_goal_authority,
            },
        )
        captures["dwr"] = {
            "residual": residual_report,
            "adjoint_qualification": adjoints,
            "goals": localizations,
            "rejected_localization": {
                "name": "absolute constrained-algebraic conj(z_i)*r_i dof-star distribution",
                "decision": "controlled_negative_partition_dependent",
                "reason": (
                    "global DWR/effectivity were stable but serial/MPI2 cell ranks "
                    "differed because constrained algebraic coordinates are partition dependent"
                ),
                "replacement": "reconstructed physical-adjoint Hcurl cell form",
            },
            "combined_relative_R_T": relative_report,
            "tolerance_normalized_R_T": tolerance_report,
        }
        residual.destroy()

    progress("goal_dwr_enriched_solve_and_adjoint", "begin")
    enriched_summary = run_stage4b_block_grating_3d_case(
        config(int(enriched_degree)),
        out_dir / f"enriched_p{enriched_degree}",
        solution_observer=enriched_observer,
        mesh_data_override=mesh_data_override,
    )
    _require_official_summary(enriched_summary, "goal-DWR enriched")
    progress("goal_dwr_enriched_solve_and_adjoint", "end")
    r5 = localize_global_two_level_correction(
        captures["coarse"]["field"],
        captures["enriched_field"],
        theta=float(theta),
    )
    dwr = captures["dwr"]
    goal_deltas = {
        goal: float(enriched_summary[goal] - coarse_summary[goal])
        for goal in ("R00_total", "R_total", "T_total")
    }
    for goal, delta in goal_deltas.items():
        estimate = dwr["goals"][goal]["global_dwr_absolute"]
        dwr["goals"][goal]["actual_coarse_to_enriched_goal_change"] = delta
        dwr["goals"][goal]["absolute_effectivity"] = float(
            estimate / max(abs(delta), TINY)
        )
        dwr["goals"][goal]["signed_goal_change_closure"] = float(
            dwr["goals"][goal]["global_signed_dwr_real"] - delta
        )
    dwr["marked_overlap_with_R5"] = {
        goal: _marked_overlap(
            dwr["goals"][goal]["marked_global_cell_ids"],
            r5["marked_global_cell_ids"],
        )
        for goal in ("R_total", "T_total")
    }
    dwr["marked_overlap_with_R5"]["R00_total"] = _marked_overlap(
        dwr["goals"]["R00_total"]["marked_global_cell_ids"],
        r5["marked_global_cell_ids"],
    )
    dwr["marked_overlap_with_R5"]["combined_relative_R_T"] = _marked_overlap(
        dwr["combined_relative_R_T"]["marked_global_cell_ids"],
        r5["marked_global_cell_ids"],
    )
    dwr["marked_overlap_with_R5"]["tolerance_normalized_R_T"] = _marked_overlap(
        dwr["tolerance_normalized_R_T"]["marked_global_cell_ids"],
        r5["marked_global_cell_ids"],
    )
    passed = bool(
        dwr["adjoint_qualification"]["pass"]
        and dwr["residual"]["enriched_solution_relative_residual_recomputed"]
        <= 1.0e-9
        and all(
            dwr["goals"][goal]["finite_nonnegative_cell_contributions"]
            and dwr["goals"][goal]["marking"]["captured_fraction"]
            >= float(theta) - 1.0e-12
            and abs(dwr["goals"][goal]["absolute_effectivity"] - 1.0)
            <= 1.0e-8
            and abs(
                dwr["goals"][goal]["signed_goal_change_closure"]
            )
            <= 1.0e-9
            for goal in ("R00_total", "R_total", "T_total")
        )
        and all(
            dwr[name]["finite_nonnegative_cell_contributions"]
            and dwr[name]["marking"]["captured_fraction"]
            >= float(theta) - 1.0e-12
            and bool(dwr[name]["marked_geometry_sha256"])
            for name in ("combined_relative_R_T", "tolerance_normalized_R_T")
        )
    )
    return {
        "schema_version": "task035.target-goal-weighted-two-level.v1",
        "status": (
            "target_goal_weighted_two_level_pass"
            if passed
            else "target_goal_weighted_two_level_fail"
        ),
        "pass": passed,
        "canonical": False,
        "production_qualified": False,
        "ordinary_default_changed": False,
        "target_identity": {
            "wavelength_nm": 13.5,
            "grazing_angle_deg": 10.0,
            "polarization": polarization_kind.upper(),
            "geometry": "Task034 fixed rectangular block grating",
            "mesh_backend": f"boundary-fitted conforming {mesh_cell_type}",
            "h_nm": float(h_nm),
        },
        "coarse": {
            "h_nm": float(h_nm),
            "degree": int(coarse_degree),
            "summary": coarse_summary,
        },
        "enriched": {
            "h_nm": float(h_nm),
            "degree": int(enriched_degree),
            "summary": enriched_summary,
        },
        "goal_changes": goal_deltas,
        "DWR": dwr,
        "R5_control": r5,
        "elapsed_seconds": float(
            MPI.COMM_WORLD.allreduce(time.perf_counter() - started, op=MPI.MAX)
        ),
    }


__all__ = [
    "_marker_report_from_local_values",
    "_tolerance_normalized_multi_goal_values",
    "build_enriched_discrete_residual",
    "localize_algebraic_dwr_products",
    "localize_physical_adjoint_weighted_correction",
    "run_target_goal_weighted_two_level",
]
