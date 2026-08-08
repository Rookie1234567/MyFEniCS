"""Standalone H5b local inverse over the retained H2b action.

The exact one-sided operator is borrowed from ``HybridLocalDtnActionSystem``.
Only the preconditioner owns assembled local slab matrices, ILU(0) factors,
the PC context, and the outer KSP.  The borrowed action system is never
destroyed here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.geometry.tetra_mesh_audit import owned_cell_geometry

from .hybrid_local_dtn_action import HybridLocalDtnActionSystem
from .physical_slab_two_level import (
    DistributedPhysicalSlabSmoother,
    build_owner_local_slab_plan,
)


H5_COORDINATE_AXIS = 0
H5_NUM_SLABS = 6
H5_OVERLAP_FRACTION = 0.125
H5_INTERPOLATION = "partition"
H5_ILU_LEVELS = 0
H5_RESTART = 30
H5_MAX_IT = 300
H5_RTOL = 1.0e-10
H5_ATOL = 0.0
H5_TRUE_RESIDUAL_LIMIT = 1.0e-8
H5_PRECONDITIONER_PROFILE = "h5_six_slab_ilu0"
R3_PRECONDITIONER_PROFILE = "v1_whole_endcap_ilu0"

__all__ = (
    "H5_ATOL",
    "H5_COORDINATE_AXIS",
    "H5_ILU_LEVELS",
    "H5_INTERPOLATION",
    "H5_MAX_IT",
    "H5_NUM_SLABS",
    "H5_OVERLAP_FRACTION",
    "H5_RESTART",
    "H5_RTOL",
    "H5_TRUE_RESIDUAL_LIMIT",
    "H5_PRECONDITIONER_PROFILE",
    "R3_PRECONDITIONER_PROFILE",
    "HybridWholeEndcapFixedSmootherAction",
    "HybridLocalIterativeInverse",
    "HybridLocalIterativeInverseResult",
    "build_hybrid_local_iterative_inverse",
    "build_hybrid_whole_endcap_fixed_smoother_action",
)


def _max_over_comm(comm: MPI.Comm, value: float) -> float:
    return float(comm.allreduce(float(value), op=MPI.MAX))


def _relative_residual(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    solution: PETSc.Vec,
    residual: PETSc.Vec,
) -> float:
    operator.mult(solution, residual)
    residual.scale(PETSc.ScalarType(-1.0))
    residual.axpy(PETSc.ScalarType(1.0), rhs)
    return float(residual.norm()) / max(float(rhs.norm()), 1.0e-30)


def _axis_interval(mesh: Any, coordinate_axis: int) -> tuple[float, float]:
    records = owned_cell_geometry(mesh)
    comm = mesh.comm
    local_min = (
        min(float(np.min(record.coordinates[:, coordinate_axis])) for record in records)
        if records
        else np.inf
    )
    local_max = (
        max(float(np.max(record.coordinates[:, coordinate_axis])) for record in records)
        if records
        else -np.inf
    )
    axis_min = float(comm.allreduce(local_min, op=MPI.MIN))
    axis_max = float(comm.allreduce(local_max, op=MPI.MAX))
    if (
        not np.isfinite(axis_min)
        or not np.isfinite(axis_max)
        or not axis_min < axis_max
    ):
        raise RuntimeError("H5 local mesh has no finite coordinate-axis interval")
    return axis_min, axis_max


def _build_profile_smoother(
    action_system: HybridLocalDtnActionSystem,
    condensed: Any,
    preconditioner_profile: str,
) -> tuple[Any, DistributedPhysicalSlabSmoother]:
    """Build one fixed owner-local plan and its factor-only smoother."""

    num_slabs = (
        H5_NUM_SLABS if preconditioner_profile == H5_PRECONDITIONER_PROFILE else 1
    )
    overlap_fraction = (
        H5_OVERLAP_FRACTION
        if preconditioner_profile == H5_PRECONDITIONER_PROFILE
        else 0.0
    )
    axis_min, axis_max = _axis_interval(
        action_system.local_mesh.mesh,
        H5_COORDINATE_AXIS,
    )
    plan = build_owner_local_slab_plan(
        condensed,
        action_system.local_mesh.mesh,
        domain_z=(axis_min, axis_max),
        num_slabs=num_slabs,
        overlap_fraction=overlap_fraction,
        coordinate_axis=H5_COORDINATE_AXIS,
    )
    smoother = DistributedPhysicalSlabSmoother.from_owner_local_plan(
        condensed,
        plan,
        ilu_levels=H5_ILU_LEVELS,
        interpolation=H5_INTERPOLATION,
        two_step_action_operator=None,
    )
    return plan, smoother


class _H5AdditiveSchwarzPcContext:
    """Minimal PETSc Python-PC bridge; the smoother remains the sole owner."""

    def __init__(self, smoother: DistributedPhysicalSlabSmoother) -> None:
        self.smoother: DistributedPhysicalSlabSmoother | None = smoother

    def apply(self, _pc: PETSc.PC, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self.smoother is None:
            raise RuntimeError("H5 additive-Schwarz context has been destroyed")
        self.smoother.solve(source, target)


@dataclass
class HybridLocalIterativeInverseResult:
    """One H5 standalone solve result; ``solution`` is owned by this result."""

    solution: PETSc.Vec
    iterations: int
    converged_reason: int
    reported_relative_residual: float
    true_relative_residual: float
    block_relative_residuals: dict[str, float]
    setup_seconds: float
    solve_seconds: float
    apply_seconds: float
    stationary_correction_residuals: dict[int, float]
    diagnostics: dict[str, Any]
    _destroyed: bool = field(default=False, init=False, repr=False)

    def destroy(self) -> None:
        if not self._destroyed:
            self.solution.destroy()
            self._destroyed = True


class HybridLocalIterativeInverse:
    """Right-FGMRES with one partition-of-unity ASM apply per PC call."""

    def __init__(
        self,
        action_system: HybridLocalDtnActionSystem,
        *,
        operator_override: PETSc.Mat | None = None,
        operator_identity: str = "complete_hybrid_action",
        preconditioner_profile: str = H5_PRECONDITIONER_PROFILE,
    ) -> None:
        self.action_system = action_system
        if operator_override is None:
            if operator_identity != "complete_hybrid_action":
                raise ValueError(
                    "default inverse requires the complete action identity"
                )
            self.operator = action_system.A
            self.external_dtn_correction = "included"
        else:
            if operator_identity != "fine_action_F_only":
                raise ValueError(
                    "operator overrides must identify the borrowed F action"
                )
            self.operator = operator_override
            self.external_dtn_correction = "excluded"
        self.operator_identity = operator_identity
        if preconditioner_profile not in {
            H5_PRECONDITIONER_PROFILE,
            R3_PRECONDITIONER_PROFILE,
        }:
            raise ValueError(
                "unknown local inverse preconditioner profile: "
                f"{preconditioner_profile}"
            )
        self.preconditioner_profile = preconditioner_profile
        self.condensed = action_system.static_condensation.condensed
        if self.operator.getType() != "python":
            raise ValueError("H5 exact local operator must be a MatPython action")
        if self.operator.getSize() != action_system.A.getSize():
            raise ValueError("iterative inverse operator must match the action size")
        if self.condensed.matrix is not None:
            raise ValueError("H5 action condensation must not retain a global matrix")
        if action_system.inventory.get("global_A_materialized") is not False:
            raise ValueError("H5 action inventory reports a materialized global A")
        if action_system.inventory.get("direct_factor_count") != 0:
            raise ValueError("H5 candidate cannot own a direct factor")

        self._destroyed = False
        self.factors_released = False
        self.factor_count_before_destroy: int | None = None
        self.factor_count_after_destroy: int | None = None
        setup_started = perf_counter()
        self.plan, self.smoother = _build_profile_smoother(
            action_system,
            self.condensed,
            preconditioner_profile,
        )
        self._pc_context = _H5AdditiveSchwarzPcContext(self.smoother)
        self.ksp = PETSc.KSP().create(self.operator.getComm())
        self.ksp.setOperators(self.operator)
        self.ksp.setType(PETSc.KSP.Type.FGMRES)
        self.ksp.setGMRESRestart(H5_RESTART)
        self.ksp.setPCSide(PETSc.PC.Side.RIGHT)
        self.ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        self.ksp.setTolerances(
            rtol=H5_RTOL,
            atol=H5_ATOL,
            max_it=H5_MAX_IT,
        )
        pc = self.ksp.getPC()
        pc.setType(PETSc.PC.Type.PYTHON)
        pc.setPythonContext(self._pc_context)
        self.ksp.setUp()
        self.setup_seconds = _max_over_comm(
            self.operator.getComm().tompi4py(),
            perf_counter() - setup_started,
        )

    def _stationary_correction_diagnostic(
        self,
        rhs: PETSc.Vec,
    ) -> dict[int, float]:
        solution = rhs.duplicate()
        residual = rhs.duplicate()
        correction = rhs.duplicate()
        solution.set(0.0)
        values: dict[int, float] = {}
        try:
            for apply_number in range(1, 9):
                _relative_residual(self.operator, rhs, solution, residual)
                correction.set(0.0)
                self.smoother.solve(residual, correction)
                solution.axpy(PETSc.ScalarType(1.0), correction)
                if apply_number in (1, 2, 4, 8):
                    values[apply_number] = _relative_residual(
                        self.operator,
                        rhs,
                        solution,
                        residual,
                    )
        finally:
            correction.destroy()
            residual.destroy()
            solution.destroy()
        return values

    def solve(
        self,
        rhs: PETSc.Vec | None = None,
    ) -> HybridLocalIterativeInverseResult:
        if self._destroyed:
            raise RuntimeError("H5 local inverse has been destroyed")
        rhs = self.action_system.b if rhs is None else rhs
        if rhs.getSize() != self.operator.getSize()[1]:
            raise ValueError("H5 RHS does not match the action operator")
        solution = rhs.duplicate()
        solution.set(0.0)
        residual = rhs.duplicate()
        comm = self.operator.getComm().tompi4py()
        apply_before = self.smoother.apply_count
        apply_elapsed_before = self.smoother.apply_elapsed_s
        solve_started = perf_counter()
        try:
            self.ksp.solve(rhs, solution)
            solve_seconds = _max_over_comm(comm, perf_counter() - solve_started)
            reported = float(self.ksp.getResidualNorm()) / max(
                float(rhs.norm()),
                1.0e-30,
            )
            true_relative = _relative_residual(
                self.operator,
                rhs,
                solution,
                residual,
            )
            stationary = self._stationary_correction_diagnostic(rhs)
            apply_seconds = _max_over_comm(
                comm,
                self.smoother.apply_elapsed_s - apply_elapsed_before,
            )
            diagnostics = self._diagnostics()
            diagnostics["stationary_correction_residuals"] = stationary
            diagnostics["reported_residual_is_monitor"] = True
            diagnostics["explicit_true_residual_recomputed"] = True
            diagnostics["pc_apply_count_for_solve_and_diagnostic"] = int(
                self.smoother.apply_count - apply_before
            )
            diagnostics["apply_seconds_scope"] = "solve_plus_stationary_diagnostic"
            return HybridLocalIterativeInverseResult(
                solution=solution,
                iterations=int(self.ksp.getIterationNumber()),
                converged_reason=int(self.ksp.getConvergedReason()),
                reported_relative_residual=float(reported),
                true_relative_residual=float(true_relative),
                block_relative_residuals={"active": float(true_relative)},
                setup_seconds=float(self.setup_seconds),
                solve_seconds=float(solve_seconds),
                apply_seconds=float(apply_seconds),
                stationary_correction_residuals=stationary,
                diagnostics=diagnostics,
            )
        except Exception:
            solution.destroy()
            raise
        finally:
            residual.destroy()

    def _diagnostics(self) -> dict[str, Any]:
        smoother = self.smoother.diagnostics
        factor_rows = int(smoother["global_factor_rows"])
        factor_nnz = int(smoother["global_stored_factor_nnz"])
        scalar_bytes = np.dtype(PETSc.ScalarType).itemsize
        integer_bytes = np.dtype(PETSc.IntType).itemsize
        factor_payload = int(
            factor_nnz * (scalar_bytes + integer_bytes)
            + (factor_rows + 16) * integer_bytes
        )
        return {
            "operator": {
                "matrix_type": str(self.operator.getType()),
                "identity": self.operator_identity,
                "external_dtn_correction": self.external_dtn_correction,
                "matrix_free": True,
                "global_A_materialized": False,
                "global_size": int(self.operator.getSize()[0]),
                "local_size": [int(value) for value in self.operator.getLocalSize()],
            },
            "configuration": {
                "preconditioner_profile": self.preconditioner_profile,
                "coordinate_axis": H5_COORDINATE_AXIS,
                "num_slabs": len(self.plan.coordinate_intervals),
                "overlap_fraction": (
                    H5_OVERLAP_FRACTION
                    if self.preconditioner_profile == H5_PRECONDITIONER_PROFILE
                    else 0.0
                ),
                "interpolation": H5_INTERPOLATION,
                "ilu_levels": H5_ILU_LEVELS,
                "factor_only": True,
                "one_apply_per_pc_apply": True,
                "two_step_action_operator": None,
                "outer_solver": "right_fgmres",
                "restart": H5_RESTART,
                "max_it": H5_MAX_IT,
                "rtol": H5_RTOL,
                "atol": H5_ATOL,
                "true_residual_limit": H5_TRUE_RESIDUAL_LIMIT,
            },
            "rows": int(self.operator.getSize()[0]),
            "source_matrix_nnz": int(smoother["global_factor_nnz"]),
            "factor_nnz": factor_nnz,
            "factor_csr_payload_estimate_bytes": factor_payload,
            "factor_csr_payload_estimate_formula": (
                "factor_nnz*(scalar_bytes+integer_bytes)+(factor_rows+16)*integer_bytes"
            ),
            "factor_csr_payload_estimate_scalar_bytes": scalar_bytes,
            "factor_csr_payload_estimate_integer_bytes": integer_bytes,
            "assembly_payload": {
                "max_sender_payload_bytes": int(smoother["max_sender_payload_bytes"]),
                "max_owner_payload_bytes": int(smoother["max_owner_payload_bytes"]),
            },
            "partition_audit": {
                "axis_interval": [
                    float(self.plan.coordinate_intervals[0][0]),
                    float(self.plan.coordinate_intervals[-1][1]),
                ],
                "slab_owners": list(self.plan.slab_owners),
                "slab_row_counts": list(self.plan.slab_row_counts),
                "coordinate_axis": int(self.plan.coordinate_axis),
                "coordinate_intervals": [
                    [float(low), float(high)]
                    for low, high in self.plan.coordinate_intervals
                ],
                "interpolation": H5_INTERPOLATION,
                "partition_weight_sum_error": smoother.get(
                    "partition_weight_sum_error"
                ),
                "partition_weight_min": smoother.get("partition_weight_min"),
                "partition_weight_max": smoother.get("partition_weight_max"),
            },
            "smoother": smoother,
            "no_direct_fallback": True,
            "lifecycle": {
                "candidate_direct_factor_count": 0,
                "factor_count_before_destroy": int(smoother["global_subdomain_count"]),
                "factor_only_storage": True,
                "factors_released": self.factors_released,
                "factor_count_after_destroy": self.factor_count_after_destroy,
            },
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.factor_count_before_destroy = int(
            self.smoother.diagnostics["global_subdomain_count"]
        )
        ksp = self.ksp
        self.ksp = None
        if ksp is not None:
            ksp.destroy()
        self._pc_context.smoother = None
        self.smoother.destroy()
        self.factor_count_after_destroy = 0
        self.factors_released = True
        self._destroyed = True


class HybridWholeEndcapFixedSmootherAction:
    """One fixed R3 whole-endcap ILU(0) action without a PETSc KSP."""

    operator_identity = "whole_endcap_ilu0_fixed_smoother"
    preconditioner_profile = R3_PRECONDITIONER_PROFILE

    def __init__(self, action_system: HybridLocalDtnActionSystem) -> None:
        self.action_system = action_system
        self.operator = action_system.A
        if self.operator.getType() != "python":
            raise ValueError("fixed whole-endcap action requires a MatPython operator")
        if action_system.static_condensation.condensed.matrix is not None:
            raise ValueError("fixed whole-endcap action cannot retain a global matrix")
        if action_system.inventory.get("global_A_materialized") is not False:
            raise ValueError(
                "fixed whole-endcap action reports a materialized global A"
            )
        if action_system.inventory.get("direct_factor_count") != 0:
            raise ValueError("fixed whole-endcap action cannot own a direct factor")
        self.condensed = action_system.static_condensation.condensed
        setup_started = perf_counter()
        self.plan, self.smoother = _build_profile_smoother(
            action_system,
            self.condensed,
            R3_PRECONDITIONER_PROFILE,
        )
        self.setup_seconds = _max_over_comm(
            self.operator.getComm().tompi4py(),
            perf_counter() - setup_started,
        )
        self._destroyed = False
        self.factor_count_before_destroy: int | None = None
        self.factor_count_after_destroy: int | None = None
        self.factors_released = False
        self._smoother_snapshot: dict[str, Any] | None = None

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("fixed whole-endcap smoother has been destroyed")
        self.smoother.solve(source, target)

    @property
    def diagnostics(self) -> dict[str, Any]:
        smoother = (
            self._smoother_snapshot
            if self._smoother_snapshot is not None
            else self.smoother.diagnostics
        )
        factor_rows = int(smoother["global_factor_rows"])
        factor_nnz = int(smoother["global_stored_factor_nnz"])
        scalar_bytes = np.dtype(PETSc.ScalarType).itemsize
        integer_bytes = np.dtype(PETSc.IntType).itemsize
        payload = int(
            factor_nnz * (scalar_bytes + integer_bytes)
            + (factor_rows + 16) * integer_bytes
        )
        factor_count = int(smoother["global_subdomain_count"])
        return {
            "operator_identity": self.operator_identity,
            "preconditioner_profile": self.preconditioner_profile,
            "base_factor_count": factor_count,
            "factor_count": factor_count,
            "factor_rows": factor_rows,
            "source_matrix_nnz": int(smoother["global_factor_nnz"]),
            "factor_nnz": factor_nnz,
            "factor_csr_payload_estimate_bytes": payload,
            "factor_csr_payload_estimate_formula": (
                "factor_nnz*(scalar_bytes+integer_bytes)+(factor_rows+16)*integer_bytes"
            ),
            "ksp_created": False,
            "apply_count": int(smoother["one_level_apply_count"]),
            "setup_seconds": float(self.setup_seconds),
            "smoother": dict(smoother),
            "lifecycle": {
                "candidate_direct_factor_count": 0,
                "factor_count_before_destroy": (
                    factor_count
                    if self.factor_count_before_destroy is None
                    else self.factor_count_before_destroy
                ),
                "factor_count_after_destroy": self.factor_count_after_destroy,
                "factors_released": bool(self.factors_released),
            },
            "destroyed": bool(self._destroyed),
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._smoother_snapshot = dict(self.smoother.diagnostics)
        self.factor_count_before_destroy = int(
            self._smoother_snapshot["global_subdomain_count"]
        )
        self.smoother.destroy()
        local_after = int(self.smoother.diagnostics["rank_local_factor_count"])
        self.factor_count_after_destroy = int(
            self.operator.getComm().tompi4py().allreduce(local_after, op=MPI.SUM)
        )
        self.factors_released = self.factor_count_after_destroy == 0
        self._destroyed = True


def build_hybrid_local_iterative_inverse(
    action_system: HybridLocalDtnActionSystem,
    *,
    operator_override: PETSc.Mat | None = None,
    operator_identity: str = "complete_hybrid_action",
    preconditioner_profile: str = H5_PRECONDITIONER_PROFILE,
) -> HybridLocalIterativeInverse:
    """Build the local inverse without owning ``action_system`` or its operator."""

    return HybridLocalIterativeInverse(
        action_system,
        operator_override=operator_override,
        operator_identity=operator_identity,
        preconditioner_profile=preconditioner_profile,
    )


def build_hybrid_whole_endcap_fixed_smoother_action(
    action_system: HybridLocalDtnActionSystem,
) -> HybridWholeEndcapFixedSmootherAction:
    """Build the non-KSP R3 whole-endcap fixed smoother action."""

    return HybridWholeEndcapFixedSmootherAction(action_system)
