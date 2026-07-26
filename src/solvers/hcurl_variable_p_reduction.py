"""Task035d adapter from p6 Stage-4 forms to a true variable-p trace system."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy import sparse
from scipy.sparse import linalg as sparse_linalg

from src.adaptivity.variable_p_degree_plan import (
    VariablePCellDegreePlan,
    load_variable_p_cell_degree_plan,
)
from src.adaptivity.variable_p_periodic_orbits import (
    build_variable_p_periodic_constraint_map,
)
from src.adaptivity.variable_p_transfer import (
    VariablePGlobalTransfer,
    build_variable_p_global_transfer,
    project_p6_dual_to_active_full,
    recover_active_full_to_p6_field,
)

from .hcurl_variable_p_assembly import (
    VariablePCondensedTraceSystem,
    build_variable_p_condensed_trace_system_from_compiled_form,
    condense_variable_p_active_vector_to_trace,
    recover_variable_p_active_full_vector,
    variable_p_cell_interior_schur_bilinear,
)


@dataclass(frozen=True)
class VariablePRecoveredSolution:
    """Recovered p6 storage field and active-space residual inputs."""

    field: Any
    active_full_solution: PETSc.Vec
    active_full_rhs: PETSc.Vec
    active_auxiliary_interior_action: PETSc.Vec | None
    audit: dict[str, Any]


@dataclass
class VariablePAssemblyTimeReduction:
    """One physically reduced variable-p Full3D operator."""

    system: VariablePCondensedTraceSystem
    transfer: VariablePGlobalTransfer
    degree_plan: VariablePCellDegreePlan
    build_audit: dict[str, Any]

    def destroy(self) -> None:
        self.system.destroy()

    def reduce_p6_vector(
        self,
        p6_vector: PETSc.Vec,
        *,
        side: str,
    ) -> PETSc.Vec:
        active = self.project_p6_vector(p6_vector)
        try:
            return self.reduce_active_vector(active, side=side)
        finally:
            active.destroy()

    def project_p6_vector(self, p6_vector: PETSc.Vec) -> PETSc.Vec:
        """Project one p6 dual vector into the true active full space."""

        return project_p6_dual_to_active_full(
            self.transfer,
            p6_vector,
        )

    def reduce_active_vector(
        self,
        active_full_vector: PETSc.Vec,
        *,
        side: str,
    ) -> PETSc.Vec:
        """Condense an already projected active vector."""

        return condense_variable_p_active_vector_to_trace(
            self.system,
            active_full_vector,
            side=side,
        )

    def enforce_trace_only_active_functional(
        self,
        active_full_vector: PETSc.Vec,
        *,
        role: str,
        relative_tolerance: float = 5.0e-12,
        absolute_tolerance: float = 1.0e-12,
    ) -> dict[str, Any]:
        """Validate and remove roundoff-only interior boundary entries.

        N1curl cell-interior functions have exactly zero tangential trace.
        A boundary functional must therefore have no active cell-interior
        entries.  FFCx quadrature may leave roundoff-sized values; accepting
        them into only part of the auxiliary Schur algebra would be
        inconsistent, so this gate validates and zeros them before any
        condensation, RHS accumulation, or recovery.
        """

        if active_full_vector.getSize() != self.system.entity_map.active_rows:
            raise ValueError("trace-only functional has the wrong size")
        row_start, row_end = map(
            int,
            active_full_vector.getOwnershipRange(),
        )
        values = active_full_vector.getArray()
        split = min(
            max(self.system.entity_map.active_trace_rows - row_start, 0),
            row_end - row_start,
        )
        local_trace_max = float(
            np.max(np.abs(values[:split]), initial=0.0)
        )
        local_interior_max = float(
            np.max(np.abs(values[split:]), initial=0.0)
        )
        local_interior_sq = float(
            np.vdot(values[split:], values[split:]).real
        )
        comm = self.system.entity_map.mesh.comm
        trace_max = float(
            comm.allreduce(local_trace_max, op=MPI.MAX)
        )
        interior_max = float(
            comm.allreduce(local_interior_max, op=MPI.MAX)
        )
        interior_norm = float(
            np.sqrt(comm.allreduce(local_interior_sq, op=MPI.SUM))
        )
        threshold = max(
            float(absolute_tolerance),
            float(relative_tolerance) * trace_max,
        )
        if interior_max > threshold:
            raise RuntimeError(
                f"{role} is not a trace-only N1curl functional: "
                f"interior_max={interior_max:.6e}, "
                f"threshold={threshold:.6e}"
            )
        values[split:] = PETSc.ScalarType(0.0)
        active_full_vector.assemble()
        return {
            "schema_version": (
                "task035d.variable-p-trace-only-functional.v1"
            ),
            "status": "trace_only_functional_roundoff_removed",
            "pass": True,
            "role": str(role),
            "active_trace_max_abs": trace_max,
            "removed_active_interior_max_abs": interior_max,
            "removed_active_interior_norm": interior_norm,
            "acceptance_threshold": threshold,
            "structural_reason": (
                "N1curl cell-interior basis has zero tangential trace"
            ),
            "auxiliary_dense_interior_schur_required": False,
            "ordinary_default_changed": False,
        }

    def interior_cross_bilinear(
        self,
        left_p6: PETSc.Vec,
        right_p6: PETSc.Vec,
    ) -> complex:
        left_active = self.project_p6_vector(left_p6)
        right_active = self.project_p6_vector(right_p6)
        try:
            return self.interior_cross_bilinear_active(
                left_active,
                right_active,
            )
        finally:
            left_active.destroy()
            right_active.destroy()

    def interior_cross_bilinear_active(
        self,
        left_active_full: PETSc.Vec,
        right_active_full: PETSc.Vec,
    ) -> complex:
        """Evaluate an interior Schur term from projected active vectors."""

        return variable_p_cell_interior_schur_bilinear(
            self.system,
            left_active_full,
            right_active_full,
        )

    def recover(
        self,
        reduced_solution: PETSc.Vec,
        p6_full_rhs: PETSc.Vec | None,
        *,
        active_full_rhs_override: PETSc.Vec | None = None,
        auxiliary_interior_columns_local: np.ndarray | None = None,
        auxiliary_values: np.ndarray | None = None,
    ) -> VariablePRecoveredSolution:
        if active_full_rhs_override is None:
            if p6_full_rhs is None:
                raise ValueError(
                    "recovery requires a p6 or active full RHS"
                )
            active_rhs = project_p6_dual_to_active_full(
                self.transfer,
                p6_full_rhs,
            )
            rhs_source = "projected_p6_full_rhs"
        else:
            if (
                active_full_rhs_override.getSize()
                != self.system.entity_map.active_rows
            ):
                raise ValueError("active full RHS override has the wrong size")
            active_rhs = active_full_rhs_override.copy()
            rhs_source = "preprojected_active_full_rhs"
        auxiliary_action = _active_auxiliary_interior_action(
            self.system,
            active_rhs,
            columns_local=auxiliary_interior_columns_local,
            auxiliary_values=auxiliary_values,
        )
        effective_rhs = active_rhs
        if auxiliary_action is not None:
            effective_rhs = active_rhs.copy()
            effective_rhs.axpy(PETSc.ScalarType(1.0), auxiliary_action)
        try:
            active_solution = recover_variable_p_active_full_vector(
                self.system,
                reduced_solution,
                active_full_rhs=effective_rhs,
            )
        except Exception:
            if effective_rhs is not active_rhs:
                effective_rhs.destroy()
            active_rhs.destroy()
            if auxiliary_action is not None:
                auxiliary_action.destroy()
            raise
        if effective_rhs is not active_rhs:
            effective_rhs.destroy()
        try:
            field, field_audit = recover_active_full_to_p6_field(
                self.transfer,
                active_solution,
            )
        except Exception:
            active_solution.destroy()
            active_rhs.destroy()
            if auxiliary_action is not None:
                auxiliary_action.destroy()
            raise
        auxiliary_norm = (
            0.0
            if auxiliary_action is None
            else float(auxiliary_action.norm())
        )
        return VariablePRecoveredSolution(
            field=field,
            active_full_solution=active_solution,
            active_full_rhs=active_rhs,
            active_auxiliary_interior_action=auxiliary_action,
            audit={
                "schema_version": (
                    "task035d.variable-p-solution-recovery.v2"
                ),
                "status": "variable_p_full_field_recovery_pass",
                "pass": True,
                "active_full_rows": self.system.entity_map.active_rows,
                "active_trace_rows": self.system.active_trace_rows,
                "p6_storage_rows": self.transfer.audit["p6_global_rows"],
                "field_recovery": field_audit,
                "auxiliary_interior_action_included": (
                    auxiliary_action is not None
                ),
                "auxiliary_interior_action_norm": auxiliary_norm,
                "active_full_rhs_source": rhs_source,
                "full_p6_global_matrix_allocated": False,
                "ordinary_default_changed": False,
            },
        )

    def full_active_residual(
        self,
        reduced_matrix: PETSc.Mat,
        reduced_rhs: PETSc.Vec,
        reduced_solution: PETSc.Vec,
        recovered: VariablePRecoveredSolution,
    ) -> dict[str, Any]:
        """Audit reduced and every eliminated active-interior equation."""

        residual = reduced_matrix.createVecLeft()
        reduced_matrix.mult(reduced_solution, residual)
        residual.axpy(PETSc.ScalarType(-1.0), reduced_rhs)
        reduced_norm = _reduced_trace_auxiliary_norm(
            self.system,
            residual,
            trace_kind="dual",
        )
        residual.destroy()

        active_solution = _global_values(
            recovered.active_full_solution,
            self.system.entity_map.active_rows,
            self.system.entity_map.mesh.comm,
        )
        active_rhs = _global_values(
            recovered.active_full_rhs,
            self.system.entity_map.active_rows,
            self.system.entity_map.mesh.comm,
        )
        auxiliary_action = (
            np.zeros_like(active_rhs)
            if recovered.active_auxiliary_interior_action is None
            else _global_values(
                recovered.active_auxiliary_interior_action,
                self.system.entity_map.active_rows,
                self.system.entity_map.mesh.comm,
            )
        )
        local_interior_sq = 0.0
        local_interior_max = 0.0
        local_interior_rhs_sq = 0.0
        local_interior_solution_sq = 0.0
        for recovery in self.system.cell_recovery:
            cell = recovery.cell
            local_trace = active_solution[cell.trace_rows]
            local_interior = active_solution[cell.interior_rows]
            homogeneous = (
                self.system.interior_from_trace_by_class[
                    recovery.class_key
                ]
                @ local_trace
            )
            delta = local_interior - homogeneous
            action = _lu_factor_matrix_action(
                self.system.interior_lu_by_class[recovery.class_key],
                delta,
            )
            action -= active_rhs[cell.interior_rows]
            action -= auxiliary_action[cell.interior_rows]
            local_interior_sq += float(np.vdot(action, action).real)
            local_rhs = active_rhs[cell.interior_rows]
            local_interior_rhs_sq += float(
                np.vdot(local_rhs, local_rhs).real
            )
            local_interior_solution_sq += float(
                np.vdot(local_interior, local_interior).real
            )
            local_interior_max = max(
                local_interior_max,
                float(np.max(np.abs(action), initial=0.0)),
            )
        comm = self.system.entity_map.mesh.comm
        interior_norm = float(
            np.sqrt(comm.allreduce(local_interior_sq, op=MPI.SUM))
        )
        interior_max = float(
            comm.allreduce(local_interior_max, op=MPI.MAX)
        )
        full_norm = float(np.hypot(reduced_norm, interior_norm))
        reduced_rhs_norm = _reduced_trace_auxiliary_norm(
            self.system,
            reduced_rhs,
            trace_kind="dual",
        )
        interior_rhs_norm = float(
            np.sqrt(
                comm.allreduce(local_interior_rhs_sq, op=MPI.SUM)
            )
        )
        rhs_norm = float(
            np.hypot(reduced_rhs_norm, interior_rhs_norm)
        )
        reduced_solution_norm = _reduced_trace_auxiliary_norm(
            self.system,
            reduced_solution,
            trace_kind="primal",
        )
        interior_solution_norm = float(
            np.sqrt(
                comm.allreduce(
                    local_interior_solution_sq,
                    op=MPI.SUM,
                )
            )
        )
        solution_norm = float(
            np.hypot(reduced_solution_norm, interior_solution_norm)
        )
        return {
            "linear_system_rhs_norm": rhs_norm,
            "linear_system_solution_norm": solution_norm,
            "linear_system_residual_norm": full_norm,
            "linear_system_relative_residual": (
                full_norm / max(rhs_norm, 1.0e-30)
            ),
            "reduced_trace_dtn_rhs_norm": reduced_rhs_norm,
            "reduced_trace_dtn_relative_residual": (
                reduced_norm / max(reduced_rhs_norm, 1.0e-30)
            ),
            "reduced_trace_dtn_residual_norm": reduced_norm,
            "eliminated_cell_interior_rhs_norm": interior_rhs_norm,
            "eliminated_cell_interior_residual_norm": interior_norm,
            "eliminated_cell_interior_max_abs_residual": interior_max,
            "auxiliary_interior_action_included": (
                recovered.active_auxiliary_interior_action is not None
            ),
            "full_operator_residual_method": (
                "exact block-Gaussian transformed residual: explicit "
                "variable-p reduced trace+DtN Mat action plus "
                "LU-reconstructed action on every eliminated active "
                "cell-interior equation"
                + (
                    ", including the solved auxiliary DtN column action"
                    if recovered.active_auxiliary_interior_action
                    is not None
                    else (
                        "; the trace-only port gate makes auxiliary "
                        "cell-interior columns structurally zero"
                    )
                )
            ),
            "linear_system_norm_definition": (
                "constraint-induced norm of [reduced trace+DtN equations, "
                "eliminated active-interior equations]; dual trace uses "
                "(C^H C)^-1, primal trace uses C^H C, and the RHS uses "
                "the same block-Gaussian transformed coordinates"
            ),
            "residual_space": (
                "true exact-sequence active variable-p test space"
            ),
            "p6_complement_residual_is_error_estimator_not_solver_gate": True,
            "full_p6_global_matrix_allocated_for_residual": False,
            "ordinary_default_changed": False,
        }


def _global_values(
    vector: PETSc.Vec,
    expected: int,
    comm: Any,
) -> np.ndarray:
    values = np.concatenate(
        comm.allgather(
            np.asarray(
                vector.getArray(readonly=True),
                dtype=np.complex128,
            ).copy()
        )
    )
    if values.shape != (expected,):
        raise RuntimeError("distributed active vector does not close")
    return values


def _reduced_trace_auxiliary_norm(
    system: VariablePCondensedTraceSystem,
    vector: PETSc.Vec,
    *,
    trace_kind: str,
) -> float:
    """Return the full trace-constraint invariant reduced vector norm."""

    if trace_kind not in {"dual", "primal"}:
        raise ValueError("reduced trace norm must be primal or dual")
    expected = system.active_trace_rows + system.appended_rows
    values = _global_values(
        vector,
        expected,
        system.entity_map.mesh.comm,
    )
    trace = values[: system.active_trace_rows]
    auxiliary = values[system.active_trace_rows :]
    trace_sq = 0.0
    constraints = system.trace_constraints
    if constraints is None:
        trace_sq = float(np.vdot(trace, trace).real)
    elif hasattr(constraints, "component_gram"):
        gram = constraints.component_gram
        expected_shape = (
            system.active_trace_rows,
            system.active_trace_rows,
        )
        if gram.shape != expected_shape:
            raise RuntimeError(
                "physical trace component Gram has the wrong shape"
            )
        if trace_kind == "primal":
            gram_action = gram @ trace
        elif sparse.issparse(gram):
            gram_action = sparse_linalg.spsolve(
                sparse.csc_matrix(gram),
                trace,
            )
        else:
            gram_action = np.linalg.solve(
                np.asarray(gram),
                trace,
            )
        if not np.all(np.isfinite(gram_action)):
            raise RuntimeError(
                "physical trace component Gram action is non-finite"
            )
        if trace_kind == "dual":
            residual = gram @ gram_action - trace
            relative = float(
                np.linalg.norm(residual)
                / max(np.linalg.norm(trace), 1.0)
            )
            if relative > 5.0e-11:
                raise RuntimeError(
                    "physical trace component Gram solve failed: "
                    f"{relative:.6e}"
                )
        contribution = np.vdot(trace, gram_action)
        if (
            abs(float(contribution.imag))
            > 5.0e-11 * max(abs(float(contribution.real)), 1.0)
            or float(contribution.real) < -5.0e-11
        ):
            raise RuntimeError(
                "physical trace component Gram norm is not positive real"
            )
        trace_sq = max(float(contribution.real), 0.0)
    else:
        seen = np.zeros(system.active_trace_rows, dtype=np.int8)
        blocks_by_root: dict[
            tuple[int, int],
            list[Any],
        ] = {}
        for block in constraints.entity_blocks.values():
            blocks_by_root.setdefault(
                (int(block.dimension), int(block.root_entity)),
                [],
            ).append(block)
        for blocks in blocks_by_root.values():
            rows = np.asarray(
                blocks[0].independent_rows,
                dtype=np.int64,
            )
            gram = np.zeros(
                (len(rows), len(rows)),
                dtype=np.complex128,
            )
            for block in blocks:
                if not np.array_equal(
                    rows,
                    block.independent_rows,
                ):
                    raise RuntimeError(
                        "one periodic orbit has inconsistent row identity"
                    )
                expansion = np.asarray(
                    block.full_from_independent,
                    dtype=np.complex128,
                )
                gram += expansion.conj().T @ expansion
            block_values = trace[rows]
            if trace_kind == "primal":
                contribution = np.vdot(
                    block_values,
                    gram @ block_values,
                )
            else:
                contribution = np.vdot(
                    block_values,
                    np.linalg.solve(gram, block_values),
                )
            trace_sq += float(contribution.real)
            seen[rows] += 1
        if not np.all(seen == 1):
            raise RuntimeError(
                "periodic entity blocks do not partition trace coordinates"
            )
    auxiliary_sq = float(np.vdot(auxiliary, auxiliary).real)
    return float(np.sqrt(max(trace_sq + auxiliary_sq, 0.0)))


def _lu_factor_matrix_action(
    factor: tuple[np.ndarray, np.ndarray],
    values: np.ndarray,
) -> np.ndarray:
    """Apply the original matrix represented by SciPy ``lu_factor``."""

    lu, pivots = factor
    dimension = int(lu.shape[0])
    lower = np.tril(lu, k=-1) + np.eye(
        dimension,
        dtype=lu.dtype,
    )
    upper = np.triu(lu)
    permuted = lower @ (upper @ values)
    permutation = np.arange(dimension)
    for row, pivot in enumerate(pivots):
        permutation[[row, int(pivot)]] = permutation[
            [int(pivot), row]
        ]
    return np.ascontiguousarray(
        permuted[np.argsort(permutation)]
    )


def _active_auxiliary_interior_action(
    system: VariablePCondensedTraceSystem,
    template: PETSc.Vec,
    *,
    columns_local: np.ndarray | None,
    auxiliary_values: np.ndarray | None,
) -> PETSc.Vec | None:
    """Build ``sum_j t_i,j a_j`` without global auxiliary-column storage."""

    if columns_local is None and auxiliary_values is None:
        return None
    if columns_local is None or auxiliary_values is None:
        raise ValueError(
            "auxiliary interior columns and values must be supplied together"
        )
    columns = np.asarray(columns_local, dtype=np.complex128)
    values = np.asarray(auxiliary_values, dtype=np.complex128)
    if columns.ndim != 2 or values.ndim != 1:
        raise ValueError("auxiliary interior data has the wrong rank")
    row_start, row_end = map(int, template.getOwnershipRange())
    interior_start = max(row_start, system.entity_map.active_trace_rows)
    local_interior_rows = max(0, row_end - interior_start)
    if columns.shape != (local_interior_rows, len(values)):
        raise ValueError(
            "local auxiliary interior columns have the wrong shape"
        )
    if not np.all(np.isfinite(columns)) or not np.all(np.isfinite(values)):
        raise ValueError("auxiliary interior data contains non-finite values")
    action = template.duplicate()
    action.set(PETSc.ScalarType(0.0))
    if local_interior_rows:
        local = action.getArray()
        offset = interior_start - row_start
        local[offset:] = columns @ values
    action.assemble()
    return action


def build_variable_p_assembly_time_reduction(
    compiled_p6_form: Any,
    p6_space: Any,
    cell_tags: Any,
    *,
    degree_plan_path: str,
    phase_x: complex,
    phase_y: complex,
    appended_global_rows: int = 0,
    appended_support_owned_cell_groups: tuple[np.ndarray, ...] = (),
    appended_support_group_by_row: tuple[int, ...] = (),
    defer_final_assembly: bool = False,
) -> VariablePAssemblyTimeReduction:
    """Build one hash-bound Task035d p4/p5/p6 reduction."""

    degree_plan = load_variable_p_cell_degree_plan(
        p6_space.mesh,
        degree_plan_path,
    )
    if degree_plan.entity_map.active_rows > 90_000:
        raise RuntimeError(
            "Task035d variable-p candidate exceeds the fail-closed "
            "90,000 active FE DoF gate; use the standard/static backend "
            "for a global-p control"
        )
    periodic = build_variable_p_periodic_constraint_map(
        degree_plan.entity_map,
        axes=("x", "y"),
        phase_x=complex(phase_x),
        phase_y=complex(phase_y),
    )
    transfer = build_variable_p_global_transfer(
        degree_plan.entity_map,
        p6_space,
    )
    system = (
        build_variable_p_condensed_trace_system_from_compiled_form(
            compiled_p6_form,
            p6_space,
            cell_tags,
            degree_plan.entity_map,
            periodic_constraints=periodic,
            appended_global_rows=appended_global_rows,
            appended_support_owned_cell_groups=(
                appended_support_owned_cell_groups
            ),
            appended_support_group_by_row=(
                appended_support_group_by_row
            ),
            defer_final_assembly=defer_final_assembly,
        )
    )
    audit = {
        "schema_version": "task035d.variable-p-assembly-reduction.v1",
        "status": "variable_p_assembly_time_reduction_built",
        "pass": True,
        "degree_plan": dict(degree_plan.audit),
        "periodic_constraints": dict(periodic.audit),
        "global_transfer": dict(transfer.audit),
        "condensed_system": dict(system.build_audit),
        "actual_conforming_active_fe_dofs": (
            degree_plan.entity_map.active_rows
        ),
        "active_fe_dof_gate_limit": 90_000,
        "active_fe_dof_gate_pass": (
            degree_plan.entity_map.active_rows <= 90_000
        ),
        "full_p6_global_matrix_allocated": False,
        "inactive_p6_rows_globally_numbered": False,
        "ordinary_default_changed": False,
    }
    system.build_audit["variable_p_reduction"] = audit
    return VariablePAssemblyTimeReduction(
        system=system,
        transfer=transfer,
        degree_plan=degree_plan,
        build_audit=audit,
    )


__all__ = [
    "VariablePAssemblyTimeReduction",
    "VariablePRecoveredSolution",
    "build_variable_p_assembly_time_reduction",
]
