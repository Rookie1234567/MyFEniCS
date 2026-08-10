"""Fixed whole-endcap ILU(0) action for the Hybrid local operator."""

from __future__ import annotations

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


WHOLE_ENDCAP_COORDINATE_AXIS = 0
WHOLE_ENDCAP_NUM_SLABS = 1
WHOLE_ENDCAP_OVERLAP_FRACTION = 0.0
WHOLE_ENDCAP_INTERPOLATION = "partition"
WHOLE_ENDCAP_ILU_LEVELS = 0
WHOLE_ENDCAP_PRECONDITIONER_PROFILE = "whole_endcap_ilu0"

__all__ = (
    "WHOLE_ENDCAP_COORDINATE_AXIS",
    "WHOLE_ENDCAP_NUM_SLABS",
    "WHOLE_ENDCAP_OVERLAP_FRACTION",
    "WHOLE_ENDCAP_INTERPOLATION",
    "WHOLE_ENDCAP_ILU_LEVELS",
    "WHOLE_ENDCAP_PRECONDITIONER_PROFILE",
    "HybridWholeEndcapFixedSmootherAction",
    "build_hybrid_whole_endcap_fixed_smoother_action",
)


def _max_over_comm(comm: MPI.Comm, value: float) -> float:
    return float(comm.allreduce(float(value), op=MPI.MAX))


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
        raise RuntimeError("whole-endcap mesh has no finite coordinate-axis interval")
    return axis_min, axis_max


def _build_profile_smoother(
    action_system: HybridLocalDtnActionSystem,
    condensed: Any,
) -> tuple[Any, DistributedPhysicalSlabSmoother]:
    axis_min, axis_max = _axis_interval(
        action_system.local_mesh.mesh,
        WHOLE_ENDCAP_COORDINATE_AXIS,
    )
    plan = build_owner_local_slab_plan(
        condensed,
        action_system.local_mesh.mesh,
        domain_z=(axis_min, axis_max),
        num_slabs=WHOLE_ENDCAP_NUM_SLABS,
        overlap_fraction=WHOLE_ENDCAP_OVERLAP_FRACTION,
        coordinate_axis=WHOLE_ENDCAP_COORDINATE_AXIS,
    )
    smoother = DistributedPhysicalSlabSmoother.from_owner_local_plan(
        condensed,
        plan,
        ilu_levels=WHOLE_ENDCAP_ILU_LEVELS,
        interpolation=WHOLE_ENDCAP_INTERPOLATION,
        two_step_action_operator=None,
    )
    return plan, smoother


class HybridWholeEndcapFixedSmootherAction:
    """One fixed whole-endcap ILU(0) action without a PETSc KSP."""

    operator_identity = "whole_endcap_ilu0_fixed_smoother"
    preconditioner_profile = WHOLE_ENDCAP_PRECONDITIONER_PROFILE

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


def build_hybrid_whole_endcap_fixed_smoother_action(
    action_system: HybridLocalDtnActionSystem,
) -> HybridWholeEndcapFixedSmootherAction:
    """Build the non-KSP whole-endcap fixed smoother action."""

    return HybridWholeEndcapFixedSmootherAction(action_system)
