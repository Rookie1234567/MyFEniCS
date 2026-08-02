from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import dolfinx_mpc
import numpy as np
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from ..common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    SimulationConfig3D,
    qualify_stage4_full3d_assembly_backend,
    resolve_stage4_full3d_assembly_backend,
)
from ..common.modes_3d import (
    PortMode3D,
    incoming_maxwell_companions,
    outgoing_port_modes_3d,
)
from ..constraints.floquet_3d import DoubleFloquet3DData, build_double_floquet_mpc
from ..geometry.hybrid_local_mesh import HybridLocalMesh, HybridLocalSide, build_hybrid_local_mesh
from .common_3d_forms import _build_variational_forms
from .common_3d_solve import _create_nedelec_space, _petsc_matrix_stats
from .dtn_port_3d import (
    _ReusableSurfaceComponentAssembler,
    _assemble_mpc_vector,
    _assemble_unconstrained_vector,
    _augmented_vec_from_base,
    _combine_owned_entries,
    _copy_base_matrix_to_augmented,
    _deferred_preallocation_matrix_stats,
    _dtn_n0_trace_alias_preflight,
    _dtn_surface_quadrature_degree,
    _incident_projection_onto_top_mode,
    _incident_top_traction_form,
    _local_augmented_dtn_coupling_stats,
    _mode_projection_denominator,
    _owned_cells_adjacent_to_facet_tag,
    _traction_vector,
    _vec_nonzero_owned_entries,
)
from .hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from .hybrid_local_static_condensation import (
    HybridLocalStaticCondensation,
    bind_hybrid_local_static_condensation,
)


def _replicated_dense_columns(matrix: PETSc.Mat) -> np.ndarray:
    """Gather one distributed dense matrix collectively, preserving columns."""

    first, last = map(int, matrix.getOwnershipRange())
    packets = matrix.getComm().tompi4py().allgather(
        (
            first,
            last,
            np.asarray(
                matrix.getDenseArray(readonly=True), dtype=np.complex128
            ).copy(),
        )
    )
    rows, columns = map(int, matrix.getSize())
    result = np.empty((rows, columns), dtype=np.complex128)
    covered = np.zeros(rows, dtype=bool)
    for start, stop, values in packets:
        result[int(start) : int(stop), :] = values
        covered[int(start) : int(stop)] = True
    if not np.all(covered):
        raise RuntimeError("Dense Schur action ownership did not close.")
    return result


@dataclass
class HybridLocalDtnSystem:
    """One terminal FEM block including only its external Fourier-DtN port."""

    side: HybridLocalSide
    cfg: SimulationConfig3D
    local_mesh: HybridLocalMesh
    V: Any
    floquet_data: DoubleFloquet3DData
    bilinear_form: Any
    linear_form: Any
    A: PETSc.Mat
    b: PETSc.Vec
    n_fe: int
    n_external_aux: int
    external_modes: list[PortMode3D]
    incident_projections: np.ndarray
    base_matrix_stats: dict[str, Any]
    augmented_matrix_stats: dict[str, Any]
    coupling_stats: dict[str, Any]
    dtn_quadrature_degree: int
    assembly_backend_requested: str = "standard_full"
    assembly_backend_actual: str = "standard_full"
    assembly_backend_qualification: dict[str, Any] | None = None
    static_condensation: HybridLocalStaticCondensation | None = None
    full_fe_rhs: PETSc.Vec | None = None
    full_fe_rows: int | None = None
    _destroyed: bool = field(default=False, init=False, repr=False)

    @property
    def global_size(self) -> int:
        return int(self.n_fe + self.n_external_aux)

    @property
    def physical_full_size(self) -> int:
        return int(
            (self.full_fe_rows if self.full_fe_rows is not None else self.n_fe)
            + self.n_external_aux
        )

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.A.destroy()
        self.b.destroy()
        if self.full_fe_rhs is not None:
            self.full_fe_rhs.destroy()
        self._destroyed = True


@dataclass
class HybridLocalOneSidedSchurAction:
    """Column action of one physical-endcap Schur complement on H."""

    A_HH: PETSc.Mat
    A_Hc: PETSc.Mat
    A_cH: PETSc.Mat
    A_cc: PETSc.Mat
    factor: PETSc.KSP
    retained_indices: np.ndarray
    complement_indices: np.ndarray
    retained_rows: int
    complement_rows: int
    external_auxiliary_rows: int
    canonical_sign: complex
    dense_interface_square_formed: bool = False
    _destroyed: bool = False

    @staticmethod
    def _replicated_values(vector: PETSc.Vec) -> np.ndarray:
        first, last = map(int, vector.getOwnershipRange())
        packets = vector.getComm().tompi4py().allgather(
            (
                first,
                last,
                np.asarray(
                    vector.getArray(readonly=True), dtype=np.complex128
                ).copy(),
            )
        )
        values = np.empty(int(vector.getSize()), dtype=np.complex128)
        covered = np.zeros(len(values), dtype=bool)
        for start, stop, local_values in packets:
            values[int(start) : int(stop)] = local_values
            covered[int(start) : int(stop)] = True
        if not np.all(covered):
            raise RuntimeError("One-sided Schur action ownership did not close.")
        return values

    def apply_trace_columns(self, values: np.ndarray) -> np.ndarray:
        """Apply canonical ``S_H`` to a small collection of H-trace columns."""

        columns = np.asarray(values, dtype=np.complex128)
        if columns.ndim == 1:
            columns = columns.reshape(-1, 1)
        if columns.ndim != 2 or columns.shape[0] != self.retained_rows:
            raise ValueError(
                "One-sided Schur columns must have shape "
                f"({self.retained_rows}, n), got {columns.shape}."
            )
        if self._destroyed:
            raise RuntimeError("The one-sided Schur action has been destroyed.")

        dense_trace = None
        complement_rhs = None
        complement_solution = None
        trace_action = None
        correction = None
        try:
            first, last = map(int, self.A_HH.getOwnershipRangeColumn())
            dense_trace = PETSc.Mat().createDense(
                size=((last - first, self.retained_rows), columns.shape[1]),
                comm=self.A_HH.getComm(),
            )
            dense_trace.getDenseArray()[:, :] = columns[first:last, :]
            dense_trace.assemble()
            complement_rhs = self.A_cH.matMult(dense_trace)
            complement_solution = complement_rhs.duplicate(copy=False)
            self.factor.matSolve(complement_rhs, complement_solution)
            if int(self.factor.getConvergedReason()) < 0:
                raise RuntimeError(
                    "The one-sided Schur complement solve did not converge."
                )
            trace_action = self.A_HH.matMult(dense_trace)
            correction = self.A_Hc.matMult(complement_solution)
            trace_action.axpy(PETSc.ScalarType(-1.0), correction)
            return self.canonical_sign * _replicated_dense_columns(trace_action)
        finally:
            for obj in (
                correction,
                trace_action,
                complement_solution,
                complement_rhs,
                dense_trace,
            ):
                if obj is not None:
                    obj.destroy()

    def condense_rhs_columns(self, values: np.ndarray) -> np.ndarray:
        """Return canonical ``f_H = sign*(B_H-A_Hc A_cc^-1 B_c)``."""

        columns = np.asarray(values, dtype=np.complex128)
        global_rows = self.retained_rows + self.complement_rows
        if columns.ndim == 1:
            columns = columns.reshape(-1, 1)
        if columns.ndim != 2 or columns.shape[0] != global_rows:
            raise ValueError(
                "One-sided RHS columns must have shape "
                f"({global_rows}, n), got {columns.shape}."
            )
        if self._destroyed:
            raise RuntimeError("The one-sided Schur action has been destroyed.")

        complement_rhs = self.A_cc.createVecLeft()
        complement_solution = self.A_cc.createVecRight()
        retained_rhs = self.A_HH.createVecLeft()
        correction = self.A_Hc.createVecLeft()
        result = np.empty((self.retained_rows, columns.shape[1]), dtype=np.complex128)
        try:
            c_first, c_last = map(int, complement_rhs.getOwnershipRange())
            h_first, h_last = map(int, retained_rhs.getOwnershipRange())
            for column in range(columns.shape[1]):
                complement_rhs.getArray()[:] = np.asarray(
                    columns[self.complement_indices[c_first:c_last], column],
                    dtype=PETSc.ScalarType,
                )
                complement_rhs.assemble()
                retained_rhs.getArray()[:] = np.asarray(
                    columns[self.retained_indices[h_first:h_last], column],
                    dtype=PETSc.ScalarType,
                )
                retained_rhs.assemble()
                self.factor.solve(complement_rhs, complement_solution)
                if int(self.factor.getConvergedReason()) < 0:
                    raise RuntimeError(
                        "The one-sided Schur RHS solve did not converge."
                    )
                self.A_Hc.mult(complement_solution, correction)
                retained_rhs.axpy(PETSc.ScalarType(-1.0), correction)
                result[:, column] = (
                    self.canonical_sign * self._replicated_values(retained_rhs)
                )
        finally:
            for obj in (
                correction,
                retained_rhs,
                complement_solution,
                complement_rhs,
            ):
                obj.destroy()
        return result

    def recover_augmented_columns(
        self, trace_values: np.ndarray, rhs_values: np.ndarray
    ) -> np.ndarray:
        """Recover ``[g_H, c]`` from a trace and the original augmented RHS."""

        traces = np.asarray(trace_values, dtype=np.complex128)
        rhs = np.asarray(rhs_values, dtype=np.complex128)
        if traces.ndim == 1:
            traces = traces[:, None]
        if rhs.ndim == 1:
            rhs = rhs[:, None]
        global_rows = self.retained_rows + self.complement_rows
        if (
            traces.ndim != 2
            or traces.shape[0] != self.retained_rows
            or rhs.ndim != 2
            or rhs.shape[0] != global_rows
            or rhs.shape[1] != traces.shape[1]
        ):
            raise ValueError(
                "Augmented recovery columns must have matching shapes "
                f"({self.retained_rows}, n) and ({global_rows}, n)."
            )
        if self._destroyed:
            raise RuntimeError("The one-sided Schur action has been destroyed.")

        trace = self.A_HH.createVecRight()
        complement_rhs = self.A_cc.createVecLeft()
        coupling = self.A_cc.createVecLeft()
        complement_solution = self.A_cc.createVecRight()
        result = np.empty((global_rows, traces.shape[1]), dtype=np.complex128)
        try:
            h_first, h_last = map(int, trace.getOwnershipRange())
            c_first, c_last = map(int, complement_rhs.getOwnershipRange())
            for column in range(traces.shape[1]):
                trace.getArray()[:] = np.asarray(
                    traces[h_first:h_last, column], dtype=PETSc.ScalarType
                )
                trace.assemble()
                complement_rhs.getArray()[:] = np.asarray(
                    rhs[self.complement_indices[c_first:c_last], column],
                    dtype=PETSc.ScalarType,
                )
                complement_rhs.assemble()
                self.A_cH.mult(trace, coupling)
                complement_rhs.axpy(PETSc.ScalarType(-1.0), coupling)
                self.factor.solve(complement_rhs, complement_solution)
                if int(self.factor.getConvergedReason()) < 0:
                    raise RuntimeError(
                        "The one-sided augmented recovery solve did not converge."
                    )
                result[self.retained_indices, column] = traces[:, column]
                result[self.complement_indices, column] = self._replicated_values(
                    complement_solution
                )
        finally:
            for obj in (
                complement_solution,
                coupling,
                complement_rhs,
                trace,
            ):
                obj.destroy()
        return result

    def apply_trace_hermitian_columns(self, values: np.ndarray) -> np.ndarray:
        """Apply the canonical Hermitian Schur action with the same factor."""

        columns = np.asarray(values, dtype=np.complex128)
        if columns.ndim == 1:
            columns = columns.reshape(-1, 1)
        if columns.ndim != 2 or columns.shape[0] != self.retained_rows:
            raise ValueError(
                "Hermitian Schur columns must have shape "
                f"({self.retained_rows}, n)."
            )
        if self._destroyed:
            raise RuntimeError("The one-sided Schur action has been destroyed.")
        retained_input = self.A_HH.createVecLeft()
        retained_action = self.A_HH.createVecRight()
        complement_rhs = self.A_Hc.createVecRight()
        transpose_rhs = self.A_cc.createVecRight()
        transpose_solution = self.A_cc.createVecLeft()
        correction = self.A_cH.createVecRight()
        result = np.empty_like(columns)
        try:
            first, last = map(int, retained_input.getOwnershipRange())
            for column in range(columns.shape[1]):
                retained_input.getArray()[:] = np.asarray(
                    columns[first:last, column], dtype=PETSc.ScalarType
                )
                retained_input.assemble()
                self.A_HH.multHermitian(retained_input, retained_action)
                self.A_Hc.multHermitian(retained_input, complement_rhs)
                transpose_rhs.getArray()[:] = np.conj(
                    complement_rhs.getArray(readonly=True)
                )
                transpose_rhs.assemble()
                self.factor.solveTranspose(transpose_rhs, transpose_solution)
                if int(self.factor.getConvergedReason()) < 0:
                    raise RuntimeError(
                        "The Hermitian Schur complement solve did not converge."
                    )
                transpose_solution.getArray()[:] = np.conj(
                    transpose_solution.getArray(readonly=True)
                )
                transpose_solution.assemble()
                self.A_cH.multHermitian(transpose_solution, correction)
                retained_action.axpy(PETSc.ScalarType(-1.0), correction)
                result[:, column] = np.conj(self.canonical_sign) * (
                    self._replicated_values(retained_action)
                )
        finally:
            for obj in (
                correction,
                transpose_solution,
                transpose_rhs,
                complement_rhs,
                retained_action,
                retained_input,
            ):
                obj.destroy()
        return result

    def destroy(self) -> None:
        if self._destroyed:
            return
        for obj in (
            self.factor,
            self.A_cc,
            self.A_cH,
            self.A_Hc,
            self.A_HH,
        ):
            obj.destroy()
        self._destroyed = True


def build_hybrid_local_one_sided_schur_action(
    system: HybridLocalDtnSystem,
    h_active_rows: np.ndarray,
    canonical_sign: complex,
) -> HybridLocalOneSidedSchurAction:
    """Factor the non-H complement without forming a dense H square."""

    from .one_cell_discrete_bloch import _factor, _partition_sparse_matrix

    retained = np.asarray(h_active_rows, dtype=PETSc.IntType)
    if len(retained) != 1200 or len(np.unique(retained)) != len(retained):
        raise ValueError("The retained H trace must contain 1200 unique rows.")
    if np.any(retained < 0) or np.any(retained >= system.global_size):
        raise ValueError("The retained H trace contains an out-of-range row.")
    sign = complex(canonical_sign)
    if sign not in {1.0 + 0.0j, -1.0 + 0.0j}:
        raise ValueError("canonical_sign must be +1 or -1.")
    complement = np.setdiff1d(
        np.arange(system.global_size, dtype=PETSc.IntType),
        retained,
        assume_unique=True,
    )
    if len(retained) + len(complement) != system.global_size:
        raise RuntimeError("Retained and complement rows do not cover the system.")
    auxiliary = np.arange(
        system.global_size - system.n_external_aux,
        system.global_size,
        dtype=PETSc.IntType,
    )
    if not np.all(np.isin(auxiliary, complement)):
        raise RuntimeError("The Schur complement omitted external auxiliary rows.")

    A_HH, A_Hc, A_cH, A_cc = _partition_sparse_matrix(
        system.A, retained, complement
    )
    factor = None
    try:
        factor = _factor(A_cc)
        return HybridLocalOneSidedSchurAction(
            A_HH=A_HH,
            A_Hc=A_Hc,
            A_cH=A_cH,
            A_cc=A_cc,
            factor=factor,
            retained_indices=retained.copy(),
            complement_indices=complement.copy(),
            retained_rows=len(retained),
            complement_rows=len(complement),
            external_auxiliary_rows=system.n_external_aux,
            canonical_sign=sign,
        )
    except Exception:
        for obj in (factor, A_cc, A_cH, A_Hc, A_HH):
            if obj is not None:
                obj.destroy()
        raise


@dataclass(frozen=True)
class HybridLocalIncomingLoadColumns:
    """Incoming companions and their net augmented active RHS columns."""

    companions: tuple[PortMode3D, ...]
    projection: np.ndarray
    traction_active: np.ndarray
    augmented_rhs: np.ndarray


@dataclass
class HybridLocalFullMatrixSolveAction:
    """Borrow one local augmented matrix and reuse a single MUMPS factor."""

    matrix: PETSc.Mat
    factor: PETSc.KSP
    rows: int
    _destroyed: bool = False

    def solve_columns(self, values: np.ndarray) -> np.ndarray:
        columns = np.asarray(values, dtype=np.complex128)
        if columns.ndim == 1:
            columns = columns.reshape(-1, 1)
        if columns.ndim != 2 or columns.shape[0] != self.rows:
            raise ValueError(
                f"Local full RHS columns must have shape ({self.rows}, n)."
            )
        if self._destroyed:
            raise RuntimeError("The local full-matrix solve action was destroyed.")
        rhs = self.matrix.createVecLeft()
        solution = self.matrix.createVecRight()
        result = np.empty_like(columns)
        try:
            first, last = map(int, rhs.getOwnershipRange())
            all_rows = np.arange(self.rows, dtype=PETSc.IntType)
            for column in range(columns.shape[1]):
                rhs.getArray()[:] = np.asarray(
                    columns[first:last, column], dtype=PETSc.ScalarType
                )
                rhs.assemble()
                self.factor.solve(rhs, solution)
                if int(self.factor.getConvergedReason()) < 0:
                    raise RuntimeError("The local full-matrix solve did not converge.")
                result[:, column] = np.asarray(
                    solution.getValues(all_rows), dtype=np.complex128
                )
        finally:
            solution.destroy()
            rhs.destroy()
        return result

    def solve_hermitian_columns(self, values: np.ndarray) -> np.ndarray:
        """Solve ``A^H z = values`` through conjugated transpose solves."""

        columns = np.asarray(values, dtype=np.complex128)
        if columns.ndim == 1:
            columns = columns.reshape(-1, 1)
        if columns.ndim != 2 or columns.shape[0] != self.rows:
            raise ValueError(
                f"Local Hermitian RHS columns must have shape ({self.rows}, n)."
            )
        if self._destroyed:
            raise RuntimeError("The local full-matrix solve action was destroyed.")
        rhs = self.matrix.createVecRight()
        solution = self.matrix.createVecLeft()
        result = np.empty_like(columns)
        try:
            first, last = map(int, rhs.getOwnershipRange())
            all_rows = np.arange(self.rows, dtype=PETSc.IntType)
            for column in range(columns.shape[1]):
                rhs.getArray()[:] = np.conj(columns[first:last, column])
                rhs.assemble()
                self.factor.solveTranspose(rhs, solution)
                if int(self.factor.getConvergedReason()) < 0:
                    raise RuntimeError("The local Hermitian solve did not converge.")
                result[:, column] = np.conj(
                    np.asarray(solution.getValues(all_rows), dtype=np.complex128)
                )
        finally:
            solution.destroy()
            rhs.destroy()
        return result

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.factor.destroy()
        self._destroyed = True


def build_hybrid_local_full_matrix_solve_action(
    system: HybridLocalDtnSystem,
) -> HybridLocalFullMatrixSolveAction:
    """Factor one borrowed augmented local matrix without copying it."""

    from .one_cell_discrete_bloch import _factor

    return HybridLocalFullMatrixSolveAction(
        matrix=system.A,
        factor=_factor(system.A),
        rows=system.global_size,
    )


def build_hybrid_local_incoming_load_columns(
    system: HybridLocalDtnSystem,
) -> HybridLocalIncomingLoadColumns:
    """Build ``P_in``, physical traction columns, and net active RHS."""

    static = system.static_condensation
    if static is None:
        raise RuntimeError("Incoming load columns require static condensation.")
    outgoing = system.external_modes
    companions = incoming_maxwell_companions(outgoing, system.cfg)
    count = len(outgoing)
    projection = np.zeros((count, count), dtype=np.complex128)
    area = (system.cfg.x_max - system.cfg.x_min) * (
        system.cfg.y_max - system.cfg.y_min
    )
    z_physical = (
        system.cfg.physical_z_min
        if system.side == "bottom"
        else system.cfg.physical_z_max
    )
    for row, out_mode in enumerate(outgoing):
        phase_out = np.exp(1j * out_mode.k_vector[2] * z_physical)
        denominator = _mode_projection_denominator(out_mode, system.cfg)
        for column, in_mode in enumerate(companions):
            if (out_mode.m, out_mode.n) != (in_mode.m, in_mode.n):
                continue
            phase_in = np.exp(1j * in_mode.k_vector[2] * z_physical)
            projection[row, column] = (
                area
                * np.vdot(out_mode.e_vector[:2], in_mode.e_vector[:2])
                * phase_in
                * np.conj(phase_out)
                / denominator
            )

    assemblers = tuple(
        _ReusableSurfaceComponentAssembler(
            system.V,
            system.local_mesh.mesh_data,
            system.local_mesh.external_facet_tag,
            component,
            quadrature_degree=system.dtn_quadrature_degree,
        )
        for component in (0, 1)
    )
    traction_active = np.empty((system.n_fe, count), dtype=np.complex128)
    for column, companion in enumerate(companions):
        components = tuple(
            assembler.assemble_unconstrained_vector(companion)
            for assembler in assemblers
        )
        full = components[0].copy()
        reduced = None
        try:
            traction = _traction_vector(companion, system.cfg)
            full.scale(PETSc.ScalarType(traction[0]))
            full.axpy(PETSc.ScalarType(traction[1]), components[1])
            reduced = static.reduce_surface_vector(full, role="load_column")
            traction_active[:, column] = (
                HybridLocalOneSidedSchurAction._replicated_values(reduced)[
                    : system.n_fe
                ]
            )
        finally:
            if reduced is not None:
                reduced.destroy()
            full.destroy()
            for vector in components:
                vector.destroy()

    augmented_rhs = np.zeros(
        (system.global_size, count), dtype=np.complex128
    )
    auxiliary_input = system.A.createVecRight()
    operator_action = system.A.createVecLeft()
    try:
        auxiliary_rows = np.arange(
            system.n_fe, system.global_size, dtype=PETSc.IntType
        )
        for column in range(count):
            auxiliary_input.set(PETSc.ScalarType(0.0))
            auxiliary_input.setValues(auxiliary_rows, projection[:, column])
            auxiliary_input.assemble()
            system.A.mult(auxiliary_input, operator_action)
            operator_values = HybridLocalOneSidedSchurAction._replicated_values(
                operator_action
            )
            augmented_rhs[: system.n_fe, column] = (
                traction_active[:, column] + operator_values[: system.n_fe]
            )
    finally:
        operator_action.destroy()
        auxiliary_input.destroy()
    return HybridLocalIncomingLoadColumns(
        companions=companions,
        projection=projection,
        traction_active=traction_active,
        augmented_rhs=augmented_rhs,
    )


def _assemble_one_sided_external_dtn(
    *,
    cfg: SimulationConfig3D,
    side: HybridLocalSide,
    local_mesh: HybridLocalMesh,
    V,
    floquet_data: DoubleFloquet3DData,
    bilinear_form,
    linear_form,
    assembly_backend_audit: dict[str, Any],
    assembly_backend_qualification: dict[str, Any],
) -> tuple[
    PETSc.Mat,
    PETSc.Vec,
    list[PortMode3D],
    np.ndarray,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    int,
    HybridLocalStaticCondensation | None,
    PETSc.Vec | None,
    int,
]:
    """Assemble the existing Stage-4 auxiliary DtN algebra on one outer face."""

    comm = local_mesh.mesh.comm
    modes = [mode for mode in outgoing_port_modes_3d(cfg) if mode.side == side]
    if not modes:
        raise RuntimeError(f"Task32 {side} local block selected zero external DtN modes.")
    n_aux = len(modes)
    quadrature_degree = _dtn_surface_quadrature_degree(cfg, modes)
    static_requested = (
        assembly_backend_audit["actual"]
        == ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
    )
    static_condensation = None
    full_fe_rhs = None
    A_base = None
    b_base = None
    if static_requested:
        condensed = build_unconstrained_assembly_time_condensation(
            fem.form(bilinear_form),
            V,
            local_mesh.mesh_data.cell_tags,
            mpc=floquet_data.mpc,
            appended_global_rows=n_aux,
            appended_support_owned_cell_groups=(
                _owned_cells_adjacent_to_facet_tag(
                    local_mesh.mesh_data,
                    local_mesh.external_facet_tag,
                ),
            ),
            appended_support_group_by_row=tuple(0 for _mode in modes),
            defer_final_assembly=True,
        )
        static_condensation = bind_hybrid_local_static_condensation(
            condensed=condensed,
            bilinear_form=bilinear_form,
            floquet_data=floquet_data,
            assembly_backend_requested=str(
                assembly_backend_audit["requested"]
            ),
            assembly_backend_actual=str(assembly_backend_audit["actual"]),
            external_auxiliary_rows=n_aux,
        )
        A_aug = condensed.matrix
        n_fe = int(condensed.active_rows)
        base_stats = _deferred_preallocation_matrix_stats(
            A_aug,
            condensed.build_audit["trace_preallocation"],
        )
        full_fe_rhs = _assemble_unconstrained_vector(linear_form)
        b_aug = static_condensation.reduce_surface_vector(
            full_fe_rhs,
            role="load_column",
        )
        full_fe_rows = int(condensed.full_rows)
    else:
        A_base = dolfinx_mpc.assemble_matrix(
            fem.form(bilinear_form),
            floquet_data.mpc,
            bcs=None,
        )
        A_base.assemble()
        b_base = _assemble_mpc_vector(linear_form, floquet_data.mpc)
        n_fe = int(A_base.getSize()[0])
        base_stats = _petsc_matrix_stats(A_base)
        A_aug = _copy_base_matrix_to_augmented(A_base, n_aux, comm)
        b_aug = _augmented_vec_from_base(b_base, n_aux, comm)
        full_fe_rows = n_fe

    if side == "top" and complex(cfg.incident_amplitude) != 0.0j:
        incident_form = _incident_top_traction_form(
            V,
            local_mesh.mesh_data,
            cfg,
        )
        incident_vec = (
            _assemble_unconstrained_vector(incident_form)
            if static_condensation is not None
            else _assemble_mpc_vector(incident_form, floquet_data.mpc)
        )
        try:
            if static_condensation is not None:
                reduced_incident = static_condensation.reduce_surface_vector(
                    incident_vec,
                    role="load_column",
                )
                incident_rows, incident_values = _vec_nonzero_owned_entries(
                    reduced_incident
                )
                reduced_incident.destroy()
                if full_fe_rhs is None:
                    raise RuntimeError(
                        "Hybrid static condensation lost its full FE RHS."
                    )
                full_fe_rhs.axpy(PETSc.ScalarType(1.0), incident_vec)
            else:
                incident_rows, incident_values = _vec_nonzero_owned_entries(
                    incident_vec
                )
            if len(incident_rows):
                b_aug.setValues(
                    incident_rows,
                    incident_values,
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
        finally:
            incident_vec.destroy()

    surface_assemblers = (
        _ReusableSurfaceComponentAssembler(
            V,
            local_mesh.mesh_data,
            local_mesh.external_facet_tag,
            0,
            quadrature_degree=quadrature_degree,
        ),
        _ReusableSurfaceComponentAssembler(
            V,
            local_mesh.mesh_data,
            local_mesh.external_facet_tag,
            1,
            quadrature_degree=quadrature_degree,
        ),
    )
    trace_alias_preflight = _dtn_n0_trace_alias_preflight(
        modes,
        {
            (side, 0): surface_assemblers[0],
            (side, 1): surface_assemblers[1],
        },
        floquet_data.mpc,
        enabled=bool(cfg.dtn_y_invariant_n0_alias_preflight),
        overlap_tolerance=float(cfg.dtn_trace_alias_overlap_tolerance),
    )
    component_key: tuple[int, int, complex] | None = None
    component_right_entries = None
    component_left_entries = None
    component_full_vectors: tuple[PETSc.Vec, PETSc.Vec] | None = None
    component_interior_bilinear: np.ndarray | None = None
    traction_rows_local = 0
    projection_cols_local = 0
    incident_projections: list[complex] = []
    matrix_insert_mode = (
        PETSc.InsertMode.ADD_VALUES
        if static_condensation is not None
        else PETSc.InsertMode.INSERT_VALUES
    )
    matrix_row_start, matrix_row_end = A_aug.getOwnershipRange()
    for aux_index, mode in enumerate(modes):
        key = (int(mode.m), int(mode.n), complex(mode.k_vector[2]))
        if key != component_key or component_right_entries is None:
            if component_full_vectors is not None:
                for vector in component_full_vectors:
                    vector.destroy()
                component_full_vectors = None
            if static_condensation is not None:
                component_full_vectors = tuple(
                    assembler.assemble_unconstrained_vector(mode)
                    for assembler in surface_assemblers
                )
                right_vectors = tuple(
                    static_condensation.reduce_surface_vector(
                        vector,
                        role="load_column",
                    )
                    for vector in component_full_vectors
                )
                left_vectors = tuple(
                    static_condensation.reduce_surface_vector(
                        vector,
                        role="row_functional",
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
                component_interior_bilinear = (
                    static_condensation.interior_cross_block(
                        component_full_vectors,
                        component_full_vectors,
                    )
                )
            else:
                component_right_entries = tuple(
                    assembler.assemble_entries(mode, floquet_data.mpc)
                    for assembler in surface_assemblers
                )
                component_left_entries = component_right_entries
                component_interior_bilinear = None
            component_key = key
        if component_left_entries is None:
            raise RuntimeError("Hybrid external DtN left component cache is missing.")
        traction = _traction_vector(mode, cfg)
        projection_cols, projection_values = _combine_owned_entries(
            component_left_entries,
            (mode.e_vector[0], mode.e_vector[1]),
            comm=comm,
        )
        traction_rows, traction_values = _combine_owned_entries(
            component_right_entries,
            (traction[0], traction[1]),
            comm=comm,
        )
        aux_global = n_fe + aux_index
        incident_projection = _incident_projection_onto_top_mode(mode, cfg)
        incident_projections.append(incident_projection)

        if len(traction_rows):
            traction_rows_local += int(len(traction_rows))
            A_aug.setValues(
                traction_rows,
                np.asarray([aux_global], dtype=PETSc.IntType),
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
            and full_fe_rhs is not None
            and component_full_vectors is not None
        ):
            for coefficient, vector in zip(
                traction[:2],
                component_full_vectors,
                strict=True,
            ):
                full_fe_rhs.axpy(
                    PETSc.ScalarType(
                        -incident_projection * coefficient
                    ),
                    vector,
                )
        if len(projection_cols):
            projection_cols_local += int(len(projection_cols))
            denominator = _mode_projection_denominator(mode, cfg)
            A_aug.setValues(
                np.asarray([aux_global], dtype=PETSc.IntType),
                projection_cols,
                (-np.conj(projection_values) / denominator).reshape(
                    (1, len(projection_cols))
                ),
                addv=matrix_insert_mode,
            )
        auxiliary_diagonal = 1.0 + 0.0j
        if component_interior_bilinear is not None:
            electric = np.asarray(mode.e_vector[:2], dtype=np.complex128)
            traction_xy = np.asarray(traction[:2], dtype=np.complex128)
            auxiliary_diagonal -= complex(
                np.vdot(
                    electric,
                    component_interior_bilinear @ traction_xy,
                )
                / _mode_projection_denominator(mode, cfg)
            )
        if matrix_row_start <= aux_global < matrix_row_end:
            A_aug.setValue(
                aux_global,
                aux_global,
                PETSc.ScalarType(auxiliary_diagonal),
                addv=matrix_insert_mode,
            )

    if component_full_vectors is not None:
        for vector in component_full_vectors:
            vector.destroy()
    A_aug.assemble()
    b_aug.assemble()
    traction_rows = int(comm.allreduce(traction_rows_local, op=MPI.SUM))
    projection_cols = int(comm.allreduce(projection_cols_local, op=MPI.SUM))
    coupling_stats = _local_augmented_dtn_coupling_stats(
        n_fe=n_fe,
        n_aux=n_aux,
        traction_rows_total=traction_rows,
        ell_cols_total=projection_cols,
    )
    coupling_stats.update(
        {
            "external_side": side,
            "external_facet_tag": int(local_mesh.external_facet_tag),
            "internal_interface_facet_tag": int(local_mesh.interface_facet_tag),
            "external_traction_rows_total": traction_rows,
            "external_projection_cols_total": projection_cols,
            "internal_interface_dtn_coupling_inserted": False,
            "assembly_backend_requested": assembly_backend_audit[
                "requested"
            ],
            "assembly_backend_actual": assembly_backend_audit["actual"],
            "assembly_backend_qualification": (
                assembly_backend_qualification
            ),
            "static_condensation": (
                static_condensation.metadata.to_dict()
                if static_condensation is not None
                else None
            ),
            "dtn_trace_alias_preflight": trace_alias_preflight,
        }
    )
    augmented_stats = _petsc_matrix_stats(A_aug)
    if A_base is not None:
        A_base.destroy()
    if b_base is not None:
        b_base.destroy()
    return (
        A_aug,
        b_aug,
        modes,
        np.asarray(incident_projections, dtype=np.complex128),
        base_stats,
        augmented_stats,
        coupling_stats,
        quadrature_degree,
        static_condensation,
        full_fe_rhs,
        full_fe_rows,
    )


def assemble_hybrid_local_dtn_system(
    cfg: SimulationConfig3D,
    side: HybridLocalSide,
    *,
    bottom_interface_z_nm: float = 10.0,
    top_interface_z_nm: float = 110.0,
    local_mesh_override: HybridLocalMesh | None = None,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    log=None,
) -> HybridLocalDtnSystem:
    """Build one terminal FEM matrix with one external DtN port.

    The reviewed Task32 decomposition remains the default.  Task33 may pass a
    symmetric alternative pair explicitly when measuring the local-FEM versus
    modal-buffer trade-off.
    """

    if cfg.stage4_dtn_assembly.lower() != "auxiliary":
        raise NotImplementedError("Task32 direct baseline requires auxiliary external DtN.")
    if cfg.use_pml:
        raise ValueError("Task32 external DtN local blocks require use_pml=False.")
    assembly_backend_audit = resolve_stage4_full3d_assembly_backend(
        cfg,
        apply=True,
    )
    assembly_backend_qualification = (
        qualify_stage4_full3d_assembly_backend(
            cfg,
            assembly_backend_audit,
        )
    )
    if log is not None:
        log(
            "Hybrid local assembly backend "
            f"requested={assembly_backend_audit['requested']} "
            f"actual={assembly_backend_audit['actual']} "
            "qualification="
            f"{assembly_backend_qualification['status']}"
        )
    if local_mesh_override is not None:
        if local_mesh_override.side != side:
            raise ValueError("The local mesh override side does not match the request.")
        local_mesh = local_mesh_override
    else:
        local_mesh = build_hybrid_local_mesh(
            cfg,
            side,
            bottom_interface_z_nm=bottom_interface_z_nm,
            top_interface_z_nm=top_interface_z_nm,
            comm=comm,
        )
    V = _create_nedelec_space(local_mesh.mesh, cfg)
    floquet_data = build_double_floquet_mpc(V, local_mesh.mesh_data, cfg, log)
    a, L = _build_variational_forms(
        local_mesh.mesh,
        local_mesh.mesh_data,
        cfg,
        V,
        field_formulation="total_field_dtn_port",
        incident_field=None,
    )
    (
        A,
        b,
        modes,
        incident_projections,
        base_stats,
        augmented_stats,
        coupling_stats,
        quadrature_degree,
        static_condensation,
        full_fe_rhs,
        full_fe_rows,
    ) = _assemble_one_sided_external_dtn(
        cfg=cfg,
        side=side,
        local_mesh=local_mesh,
        V=V,
        floquet_data=floquet_data,
        bilinear_form=a,
        linear_form=L,
        assembly_backend_audit=assembly_backend_audit,
        assembly_backend_qualification=assembly_backend_qualification,
    )
    return HybridLocalDtnSystem(
        side=side,
        cfg=cfg,
        local_mesh=local_mesh,
        V=V,
        floquet_data=floquet_data,
        bilinear_form=a,
        linear_form=L,
        A=A,
        b=b,
        n_fe=int(A.getSize()[0] - len(modes)),
        n_external_aux=len(modes),
        external_modes=modes,
        incident_projections=incident_projections,
        base_matrix_stats=base_stats,
        augmented_matrix_stats=augmented_stats,
        coupling_stats=coupling_stats,
        dtn_quadrature_degree=quadrature_degree,
        assembly_backend_requested=str(assembly_backend_audit["requested"]),
        assembly_backend_actual=str(assembly_backend_audit["actual"]),
        assembly_backend_qualification=assembly_backend_qualification,
        static_condensation=static_condensation,
        full_fe_rhs=full_fe_rhs,
        full_fe_rows=full_fe_rows,
    )
