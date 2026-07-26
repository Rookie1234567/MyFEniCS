"""Task035d adapter from p6 Stage-4 forms to a true variable-p trace system."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

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
        active = project_p6_dual_to_active_full(
            self.transfer,
            p6_vector,
        )
        try:
            return condense_variable_p_active_vector_to_trace(
                self.system,
                active,
                side=side,
            )
        finally:
            active.destroy()

    def interior_cross_bilinear(
        self,
        left_p6: PETSc.Vec,
        right_p6: PETSc.Vec,
    ) -> complex:
        left_active = project_p6_dual_to_active_full(
            self.transfer,
            left_p6,
        )
        right_active = project_p6_dual_to_active_full(
            self.transfer,
            right_p6,
        )
        try:
            return variable_p_cell_interior_schur_bilinear(
                self.system,
                left_active,
                right_active,
            )
        finally:
            left_active.destroy()
            right_active.destroy()

    def recover(
        self,
        reduced_solution: PETSc.Vec,
        p6_full_rhs: PETSc.Vec,
    ) -> VariablePRecoveredSolution:
        active_rhs = project_p6_dual_to_active_full(
            self.transfer,
            p6_full_rhs,
        )
        active_solution = recover_variable_p_active_full_vector(
            self.system,
            reduced_solution,
            active_full_rhs=active_rhs,
        )
        try:
            field, field_audit = recover_active_full_to_p6_field(
                self.transfer,
                active_solution,
            )
        except Exception:
            active_solution.destroy()
            active_rhs.destroy()
            raise
        return VariablePRecoveredSolution(
            field=field,
            active_full_solution=active_solution,
            active_full_rhs=active_rhs,
            audit={
                "schema_version": (
                    "task035d.variable-p-solution-recovery.v1"
                ),
                "status": "variable_p_full_field_recovery_pass",
                "pass": True,
                "active_full_rows": self.system.entity_map.active_rows,
                "active_trace_rows": self.system.active_trace_rows,
                "p6_storage_rows": self.transfer.audit["p6_global_rows"],
                "field_recovery": field_audit,
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
        reduced_norm = float(residual.norm())
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
        local_interior_sq = 0.0
        local_interior_max = 0.0
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
            local_interior_sq += float(np.vdot(action, action).real)
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
        local_aux_rhs_sq = _last_rank_aux_norm_squared(
            reduced_rhs,
            active_rows=self.system.active_trace_rows,
            appended_rows=self.system.appended_rows,
            comm=comm,
        )
        rhs_norm = float(
            np.sqrt(
                recovered.active_full_rhs.norm() ** 2
                + comm.allreduce(local_aux_rhs_sq, op=MPI.SUM)
            )
        )
        local_aux_solution_sq = _last_rank_aux_norm_squared(
            reduced_solution,
            active_rows=self.system.active_trace_rows,
            appended_rows=self.system.appended_rows,
            comm=comm,
        )
        solution_norm = float(
            np.sqrt(
                recovered.active_full_solution.norm() ** 2
                + comm.allreduce(
                    local_aux_solution_sq,
                    op=MPI.SUM,
                )
            )
        )
        return {
            "linear_system_rhs_norm": rhs_norm,
            "linear_system_solution_norm": solution_norm,
            "linear_system_residual_norm": full_norm,
            "linear_system_relative_residual": (
                full_norm / max(rhs_norm, 1.0e-30)
            ),
            "reduced_trace_dtn_residual_norm": reduced_norm,
            "eliminated_cell_interior_residual_norm": interior_norm,
            "eliminated_cell_interior_max_abs_residual": interior_max,
            "full_operator_residual_method": (
                "explicit variable-p reduced trace+DtN Mat action plus "
                "LU-reconstructed action on every eliminated active "
                "cell-interior equation"
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


def _last_rank_aux_norm_squared(
    vector: PETSc.Vec,
    *,
    active_rows: int,
    appended_rows: int,
    comm: Any,
) -> float:
    if comm.rank != comm.size - 1 or not appended_rows:
        return 0.0
    values = np.asarray(
        vector.getValues(
            np.arange(
                active_rows,
                active_rows + appended_rows,
                dtype=PETSc.IntType,
            )
        ),
        dtype=np.complex128,
    )
    return float(np.vdot(values, values).real)


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
