"""Research-only fixed beta=1 shifted inner cycle for W16A.

The auxiliary operator is the existing shifted volume-only beta=1 operator.
The physical beta=0 volume-plus-DtN measurement belongs to the later worker;
this module only wraps the existing disk-backed flexible-GMRES implementation
and evaluates its small scalar/hash contract.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import math
from pathlib import Path
from typing import Any

import numpy as np

from .disk_backed_flexible_gmres import (
    DiskBackedFlexibleGMRES,
    DiskBackedFlexibleGMRESResult,
)


__all__ = (
    "W16A_AUXILIARY_BETA",
    "W16A_AUXILIARY_OPERATOR",
    "W16A_AUXILIARY_PC",
    "W16A_CHECKPOINTS",
    "W16A_CLOSURE_LIMIT",
    "W16A_INNER_SCHEMA",
    "W16A_INNER_TRUE_RESIDUAL_LIMIT",
    "W16A_MAX_STEPS",
    "W16A_PREDICTED_LIVE_SET_BYTES",
    "W16A_PREDICTED_LIVE_SET_LIMIT_BYTES",
    "W16A_RELATIVE_IDENTITY_LIMIT",
    "W16A_RHO_LIMIT",
    "W16A_SCHEMA",
    "W16A_SCRATCH_PER_RUN_BYTES",
    "W16A_SCRATCH_TWO_RUN_TOTAL_BYTES",
    "W16A_SCRATCH_IS_DISK_NOT_RSS",
    "W16A_WATCHDOG_LIMIT_BYTES",
    "evaluate_w16a_global_shifted_gate",
    "run_w16a_fixed20",
)


W16A_SCHEMA = "task037.extra.h2b.w16a.global-shifted-inner.v1"
W16A_INNER_SCHEMA = "task037.extra.h2b.w16a.inner-fixed20.v1"
W16A_AUXILIARY_OPERATOR = "shifted_volume_only"
W16A_AUXILIARY_PC = "direct_beta1_shifted_row_complete_local_patch"
W16A_AUXILIARY_BETA = 1.0
W16A_MAX_STEPS = 20
W16A_CHECKPOINTS = (20,)
W16A_INNER_TRUE_RESIDUAL_LIMIT = 1.0e-2
W16A_RELATIVE_IDENTITY_LIMIT = 1.0e-13
W16A_RHO_LIMIT = 0.90
W16A_CLOSURE_LIMIT = 1.0e-11
W16A_VECTOR_BYTES = 173_802 * np.dtype(np.complex128).itemsize
W16A_SCRATCH_PER_RUN_BYTES = (
    W16A_MAX_STEPS + 1 + W16A_MAX_STEPS
) * W16A_VECTOR_BYTES
W16A_SCRATCH_TWO_RUN_TOTAL_BYTES = 2 * W16A_SCRATCH_PER_RUN_BYTES
W16A_SCRATCH_IS_DISK_NOT_RSS = True
W16A_BASE_LIVE_SET_BYTES = 1_698_273_595
W16A_AUXILIARY_VECTOR_BYTES = 15 * W16A_VECTOR_BYTES
W16A_PREDICTED_LIVE_SET_BYTES = (
    W16A_BASE_LIVE_SET_BYTES + W16A_AUXILIARY_VECTOR_BYTES
)
W16A_PREDICTED_LIVE_SET_LIMIT_BYTES = 1_750_000_000
W16A_WATCHDOG_LIMIT_BYTES = 1_950_000_000


def run_w16a_fixed20(
    action: Callable[[np.ndarray], np.ndarray],
    pc: Callable[[np.ndarray], np.ndarray],
    rhs: np.ndarray,
    scratch_dir: str | Path,
    observer: Callable[[Mapping[str, Any]], None] | None = None,
) -> DiskBackedFlexibleGMRESResult:
    """Run exactly one zero-start right-FGMRES W16A auxiliary cycle.

    ``DiskBackedFlexibleGMRES`` remains the sole implementation of Arnoldi,
    two-pass MGS, checkpoint reconstruction, and disk-backed basis storage.
    This wrapper intentionally exposes no iteration, restart, beta, or
    tolerance controls.
    """

    solver = DiskBackedFlexibleGMRES(
        action,
        pc,
        max_steps=W16A_MAX_STEPS,
        checkpoints=W16A_CHECKPOINTS,
    )
    return solver.solve(rhs, scratch_dir=scratch_dir, observer=observer)


def _finite_bounded(value: Any, limit: float | None = None) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number >= 0.0 and (
        limit is None or number <= limit
    )


def _fixed20_inner_audit(audit: Mapping[str, Any]) -> bool:
    if not isinstance(audit, Mapping):
        return False
    try:
        v_basis = audit["v_basis"]
        z_basis = audit["z_basis"]
        return (
            audit["algorithm"] == "right_flexible_gmres"
            and audit["rows"] == W16A_VECTOR_BYTES // 16
            and audit["dtype"] == "complex128"
            and audit["max_steps"] == W16A_MAX_STEPS
            and audit["iterations"] == W16A_MAX_STEPS
            and audit["checkpoint_iterations"] == [20]
            and audit["checkpoint_count"] == 1
            and audit["observer_count"] == 1
            and audit["action_count"] == 21
            and audit["pc_count"] == 20
            and audit["initial_action_count"] == 0
            and audit["orthogonalization_passes"] == 2
            and audit["mmap"] is False
            and audit["basis_in_memory"] is False
            and audit["scratch_bytes"] == W16A_SCRATCH_PER_RUN_BYTES
            and audit["scratch_mmap"] is False
            and audit["scratch_basis_in_memory"] is False
            and audit["checkpoint_set_complete"] is True
            and audit["bounded_full_vector_gate"] is True
            and isinstance(audit["scratch_paths"], Mapping)
            and isinstance(audit["scratch_paths"]["v_basis"], str)
            and bool(audit["scratch_paths"]["v_basis"])
            and isinstance(audit["scratch_paths"]["z_basis"], str)
            and bool(audit["scratch_paths"]["z_basis"])
            and v_basis["capacity"] == 21
            and v_basis["written_count"] == 21
            and v_basis["write_count"] == 21
            and v_basis["allocated_bytes"] == 21 * W16A_VECTOR_BYTES
            and v_basis["mmap"] is False
            and z_basis["capacity"] == 20
            and z_basis["written_count"] == 20
            and z_basis["write_count"] == 20
            and z_basis["allocated_bytes"] == 20 * W16A_VECTOR_BYTES
            and z_basis["mmap"] is False
        )
    except (KeyError, IndexError, TypeError, ValueError):
        return False


def _fixed20_record(record: Mapping[str, Any]) -> bool:
    if not isinstance(record, Mapping):
        return False
    try:
        return (
            record["schema"] == W16A_INNER_SCHEMA
            and record["algorithm"] == "fgmres_right_shifted_beta1_fixed20"
            and record["iterations"] == 20
            and record["checkpoint_iteration"] == 20
            and record["action_count"] == 21
            and record["pc_apply_count_delta"] == 20
            and record["observer_count"] == 1
            and record["initial_action_count"] == 0
            and type(record["run_index"]) is int
            and record["run_index"] in (1, 2)
            and record["finite"] is True
            and isinstance(record["solution_sha256"], str)
            and bool(record["solution_sha256"])
        )
    except (KeyError, TypeError, ValueError):
        return False


def _identity_gate(identity: Mapping[str, Any]) -> bool:
    if not isinstance(identity, Mapping):
        return False
    try:
        return (
            identity["finite"] is True
            and identity["dtype"] == "complex128"
            and identity["shape_equal"] is True
            and identity["sha256_equal"] is True
            and _finite_bounded(
                identity["relative_difference"], W16A_RELATIVE_IDENTITY_LIMIT
            )
        )
    except (KeyError, TypeError, ValueError):
        return False


def _measurement_gate(measurement: Mapping[str, Any]) -> bool:
    if not isinstance(measurement, Mapping):
        return False
    try:
        return (
            measurement["schema"] == W16A_SCHEMA
            and measurement["finite"] is True
            and measurement["repeat_exact"] is True
            and _finite_bounded(measurement["rho"], W16A_RHO_LIMIT)
            and _finite_bounded(
                measurement["normal_closure"], W16A_CLOSURE_LIMIT
            )
            and _finite_bounded(
                measurement["projection_orthogonality"], W16A_CLOSURE_LIMIT
            )
        )
    except (KeyError, TypeError, ValueError):
        return False


def evaluate_w16a_global_shifted_gate(
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute the narrow W16A scalar/hash Gate from recorded evidence.

    The evaluator accepts only the fixed beta=1 shifted-volume/direct-local-PC
    identity.  It does not infer missing fields or trust a producer ``pass``
    flag.  Physical action measurements are included as the later worker's
    two rank-one records; no action or solver is executed here.
    """

    check_names = (
        "schema",
        "fixed_identity",
        "inner_audits",
        "inner_records",
        "inner_residual",
        "z_identity",
        "p_identity",
        "measurements",
        "action_counts",
        "architecture",
        "lifecycle",
        "prediction",
    )
    checks = {name: False for name in check_names}
    if not isinstance(summary, Mapping):
        return {
            "pass": False,
            "checks": checks,
            "problems": list(check_names),
        }

    try:
        checks["schema"] = summary["schema"] == W16A_SCHEMA

        identity = summary["fixed_identity"]
        checks["fixed_identity"] = (
            isinstance(identity, Mapping)
            and identity["operator"] == W16A_AUXILIARY_OPERATOR
            and type(identity["beta"]) is float
            and identity["beta"] == W16A_AUXILIARY_BETA
            and identity["right_pc"] == W16A_AUXILIARY_PC
            and identity["auxiliary_dtn_used"] is False
            and identity["projected_range_used"] is False
            and identity["b0_used"] is False
            and identity["m3y_used"] is False
            and identity["range_store_used"] is False
        )

        inner_audits = summary["inner_audits"]
        checks["inner_audits"] = (
            isinstance(inner_audits, Sequence)
            and not isinstance(inner_audits, (str, bytes))
            and len(inner_audits) == 2
            and all(_fixed20_inner_audit(audit) for audit in inner_audits)
            and inner_audits[0]["scratch_paths"]["v_basis"]
            != inner_audits[1]["scratch_paths"]["v_basis"]
            and inner_audits[0]["scratch_paths"]["z_basis"]
            != inner_audits[1]["scratch_paths"]["z_basis"]
        )
        records = summary["inner_records"]
        checks["inner_records"] = (
            isinstance(records, Sequence)
            and not isinstance(records, (str, bytes))
            and len(records) == 2
            and all(_fixed20_record(record) for record in records)
            and [record["run_index"] for record in records] == [1, 2]
            and records[0]["rhs_sha256"] == records[1]["rhs_sha256"]
        )
        checks["inner_residual"] = (
            checks["inner_records"]
            and all(
                _finite_bounded(
                    record["true_residual"], W16A_INNER_TRUE_RESIDUAL_LIMIT
                )
                for record in records
            )
        )
        checks["z_identity"] = _identity_gate(summary["z_identity"])
        checks["p_identity"] = _identity_gate(summary["p_identity"])

        measurements = summary["measurements"]
        checks["measurements"] = (
            isinstance(measurements, Sequence)
            and not isinstance(measurements, (str, bytes))
            and len(measurements) == 2
            and all(_measurement_gate(measurement) for measurement in measurements)
        )
        action_audit = summary["action_audit"]
        checks["action_counts"] = (
            isinstance(action_audit, Mapping)
            and action_audit["global_shifted_action_count"] == 42
            and action_audit["local_pc_apply_count"] == 40
            and action_audit["local_exact_shifted_volume_action_count"] == 40
            and action_audit["shifted_action_total_count"] == 82
            and action_audit["physical_action_count"] == 2
            and action_audit["physical_dtn_action_count"] == 2
        )

        architecture = summary["architecture"]
        checks["architecture"] = (
            isinstance(architecture, Mapping)
            and architecture["fine_space"] == "uncondensed_fullspace"
            and architecture["physical_operator"]
            == "beta0_volume_plus_matrix_free_dtn80"
            and architecture["auxiliary_dtn_used"] is False
            and architecture["global_matrix_materialized"] is False
            and architecture["augmented_matrix_materialized"] is False
            and architecture["condensation"] is False
            and architecture["static_condensation"] is False
            and architecture["trace_slab"] is False
            and architecture["slab_factors"] == 0
            and architecture["physical_ksp_used"] is False
            and architecture["pde_used"] is False
            and architecture["official_rta"] is False
        )

        lifecycle = summary["lifecycle"]
        checks["lifecycle"] = (
            isinstance(lifecycle, Mapping)
            and lifecycle["events"] == [
                "auxiliary_constructed",
                "inner_apply_1",
                "inner_apply_2",
                "auxiliary_released",
                "physical_constructed",
                "physical_apply_1",
                "physical_apply_2",
                "physical_released",
            ]
            and lifecycle["auxiliary_physical_overlap"] is False
            and lifecycle["release_between_inner_runs"] is False
        )

        prediction = summary["prediction"]
        checks["prediction"] = (
            isinstance(prediction, Mapping)
            and prediction["bytes"] == W16A_PREDICTED_LIVE_SET_BYTES
            and prediction["limit_bytes"] == W16A_PREDICTED_LIVE_SET_LIMIT_BYTES
            and prediction["watchdog_limit_bytes"] == W16A_WATCHDOG_LIMIT_BYTES
            and prediction["bytes"] <= prediction["limit_bytes"]
            and prediction["derived_not_measured"] is True
            and prediction["per_run_scratch_bytes"] == W16A_SCRATCH_PER_RUN_BYTES
            and prediction["two_run_scratch_bytes"]
            == W16A_SCRATCH_TWO_RUN_TOTAL_BYTES
            and prediction["scratch_is_disk_not_rss"] is True
            and prediction["swap_bytes"] == 0
        )
    except (KeyError, IndexError, TypeError, ValueError):
        pass

    return {
        "pass": bool(all(checks.values())),
        "checks": checks,
        "problems": sorted(name for name, passed in checks.items() if not passed),
    }
