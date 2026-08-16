"""Research-only W18A nested auxiliary action contract.

W18A uses ``B = S + T`` as the outer auxiliary action, where ``S`` is the
fixed beta=1 shifted volume action and ``T`` is the same matrix-free DtN80
action.  Its right PC is the existing fixed40 ``S`` cycle with the direct
beta=1 local patch PC.  The shared W16B solver remains the only Krylov
implementation; this module only supplies the fixed wiring and scalar/hash
Gate.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import math
from pathlib import Path
from typing import Any

from . import hcurl_m6b_w16_global_shifted_inner_pc as _w16


__all__ = (
    "W18A_SCHEMA",
    "W18A_INNER_SCHEMA",
    "W18A_OUTER_STEPS",
    "W18A_CHECKPOINTS",
    "W18A_RHO1_ANCHOR",
    "W18A_RHO1_LIMIT",
    "W18A_RHO2_LIMIT",
    "W18A_INNER_TRUE_RESIDUAL_LIMIT",
    "W18A_RELATIVE_IDENTITY_LIMIT",
    "W18A_CLOSURE_LIMIT",
    "W18A_PREDICTED_LIVE_SET_BYTES",
    "W18A_PREDICTED_LIVE_SET_LIMIT_BYTES",
    "W18A_WATCHDOG_LIMIT_BYTES",
    "W18A_ACTION_COUNTS",
    "W18A_FIXED_IDENTITY",
    "W18A_ARCHITECTURE",
    "W18A_LIFECYCLE",
    "run_w18a_outer2",
    "evaluate_w18a_action_gate",
)


W18A_SCHEMA = "task037.extra.h2b.w18a.nested-auxiliary.v1"
W18A_INNER_SCHEMA = _w16.W16B_INNER_SCHEMA
W18A_OUTER_STEPS = _w16.W16B_MAX_STEPS
W18A_CHECKPOINTS = _w16.W16B_CHECKPOINTS
W18A_RHO1_ANCHOR = _w16.W16B_RHO1_ANCHOR
W18A_RHO1_LIMIT = _w16.W16B_RHO1_LIMIT
W18A_RHO2_LIMIT = 0.85
W18A_INNER_TRUE_RESIDUAL_LIMIT = _w16.W16A_INNER_TRUE_RESIDUAL_LIMIT
W18A_RELATIVE_IDENTITY_LIMIT = _w16.W16A_RELATIVE_IDENTITY_LIMIT
W18A_CLOSURE_LIMIT = _w16.W16A_CLOSURE_LIMIT
W18A_PREDICTED_LIVE_SET_BYTES = 1_734_993_014
W18A_PREDICTED_LIVE_SET_LIMIT_BYTES = 1_750_000_000
W18A_WATCHDOG_LIMIT_BYTES = 1_950_000_000

W18A_ACTION_COUNTS = {
    "outer_auxiliary_action_count": 8,
    "outer_pc_apply_count": 4,
    "inner_global_shifted_action_count": 172,
    "local_pc_apply_count": 160,
    "local_exact_shifted_action_count": 160,
    "shifted_action_total_count": 340,
    "auxiliary_dtn_action_count": 8,
    "physical_volume_action_count": 4,
    "physical_dtn_action_count": 4,
    "total_dtn_action_count": 12,
}

W18A_FIXED_IDENTITY = {
    "outer_operator": "shifted_volume_plus_matrix_free_dtn80",
    "inner_operator": "shifted_volume_only",
    "inner_algorithm": "fgmres_right_shifted_beta1_composed_fixed20_plus20",
    "right_pc": _w16.W16A_AUXILIARY_PC,
    "beta": 1.0,
    "outer_steps": W18A_OUTER_STEPS,
    "outer_checkpoints": list(W18A_CHECKPOINTS),
    "auxiliary_dtn_used": True,
    "projected_range_used": False,
    "b0_used": False,
    "m3y_used": False,
    "beta_scan": False,
    "physical_operator": "beta0_volume_plus_matrix_free_dtn80",
    "physical_ksp_used": False,
    "pde_used": False,
    "official_rta": False,
}

W18A_ARCHITECTURE = {
    "fine_space": "uncondensed_fullspace",
    "global_matrix_materialized": False,
    "augmented_matrix_materialized": False,
    "global_condensed_schur_materialized": False,
    "static_condensation": False,
    "static_condensed_operator_used": False,
    "trace_slab": False,
    "trace_slab_pc_used": False,
    "slab_factors": 0,
    "physical_ksp_used": False,
    "pde_used": False,
    "official_rta": False,
}

W18A_LIFECYCLE = {
    "outer_basis_disk_backed": True,
    "inner_basis_disk_backed": True,
    "release_between_outer_steps": False,
    "shared_dtn_instance_count": 1,
}


def run_w18a_outer2(
    shifted_action: Callable[[Any], Any],
    dtn_action: Callable[[Any], Any],
    local_pc: Callable[[Any], Any],
    rhs: Any,
    scratch_dir: str | Path,
    observer: Callable[[Mapping[str, Any]], None] | None = None,
) -> tuple[Any, Any]:
    """Run the fixed outer-2 ``B=S+T`` screen through the W16B solver."""

    def outer_action(values: Any) -> Any:
        return shifted_action(values) + dtn_action(values)

    return _w16.run_w16b_outer2(
        outer_action,
        shifted_action,
        local_pc,
        rhs,
        scratch_dir,
        observer=observer,
    )


def _finite_bounded(value: Any, limit: float | None = None) -> bool:
    if type(value) not in (int, float):
        return False
    number = float(value)
    return bool(
        math.isfinite(number)
        and number >= 0.0
        and (limit is None or number <= limit)
    )


def _mapping_matches(value: Any, expected: Mapping[str, Any]) -> bool:
    if not isinstance(value, Mapping):
        return False
    return all(
        key in value
        and type(value[key]) is type(expected_value)
        and value[key] == expected_value
        for key, expected_value in expected.items()
    )


def _hash_valid(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _outer_audit_valid(audit: Any) -> bool:
    return _mapping_matches(
        audit,
        {
            "algorithm": "right_flexible_gmres",
            "max_steps": W18A_OUTER_STEPS,
            "iterations": W18A_OUTER_STEPS,
            "checkpoint_iterations": list(W18A_CHECKPOINTS),
            "checkpoint_count": 2,
            "observer_count": 2,
            "action_count": 4,
            "pc_count": 2,
            "initial_action_count": 0,
            "mmap": False,
            "basis_in_memory": False,
            "checkpoint_set_complete": True,
        },
    )


def _inner_record_valid(record: Any) -> bool:
    if not _mapping_matches(
        record,
        {
            "schema": W18A_INNER_SCHEMA,
            "algorithm": "fgmres_right_shifted_beta1_composed_fixed20_plus20",
            "finite": True,
        },
    ):
        return False
    return _finite_bounded(record.get("final_relative_residual"))


def _checkpoint_valid(checkpoint: Any, iteration: int) -> bool:
    if not isinstance(checkpoint, Mapping):
        return False
    return bool(
        checkpoint.get("iteration") == iteration
        and type(checkpoint.get("finite")) is bool
        and checkpoint["finite"] is True
        and _hash_valid(checkpoint.get("solution_sha256"))
        and _hash_valid(checkpoint.get("action_sha256"))
        and _finite_bounded(checkpoint.get("true_relative_residual"))
        and _finite_bounded(
            checkpoint.get("solution_relative_difference"),
            W18A_RELATIVE_IDENTITY_LIMIT,
        )
        and _finite_bounded(
            checkpoint.get("action_relative_difference"),
            W18A_RELATIVE_IDENTITY_LIMIT,
        )
    )


def _measurement_valid(measurement: Any, iteration: int) -> bool:
    if not _mapping_matches(
        measurement,
        {"schema": W18A_SCHEMA, "checkpoint": iteration, "finite": True},
    ):
        return False
    return bool(
        _finite_bounded(measurement.get("rho"))
        and _finite_bounded(
            measurement.get("normal_closure"), W18A_CLOSURE_LIMIT
        )
        and _finite_bounded(
            measurement.get("projection_orthogonality"), W18A_CLOSURE_LIMIT
        )
    )


def _repeat_structure_valid(run: Any) -> bool:
    if not isinstance(run, Mapping):
        return False
    try:
        checkpoints = run["checkpoints"]
        measurements = run["measurements"]
        records = run["inner_records"]
        return bool(
            type(run["repeat_index"]) is int
            and _outer_audit_valid(run["outer_audit"])
            and isinstance(records, Sequence)
            and not isinstance(records, (str, bytes))
            and len(records) == 2
            and all(_inner_record_valid(item) for item in records)
            and isinstance(checkpoints, Mapping)
            and set(checkpoints) == {"1", "2"}
            and all(
                _checkpoint_valid(checkpoints[str(iteration)], iteration)
                for iteration in W18A_CHECKPOINTS
            )
            and isinstance(measurements, Mapping)
            and set(measurements) == {"1", "2"}
            and all(
                _measurement_valid(measurements[str(iteration)], iteration)
                for iteration in W18A_CHECKPOINTS
            )
        )
    except (KeyError, TypeError, ValueError):
        return False


def evaluate_w18a_action_gate(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute the W18A scalar/hash action Gate without filesystem access."""

    names = (
        "schema",
        "fixed_identity",
        "outer_audits",
        "inner_residual",
        "outer_auxiliary_residual",
        "finite",
        "repeat_identity",
        "measurements",
        "action_counts",
        "architecture",
        "lifecycle",
        "prediction",
    )
    checks = {name: False for name in names}
    if not isinstance(summary, Mapping):
        return {"pass": False, "checks": checks, "problems": list(names)}
    try:
        checks["schema"] = summary["schema"] == W18A_SCHEMA
        checks["fixed_identity"] = _mapping_matches(
            summary["fixed_identity"], W18A_FIXED_IDENTITY
        )
        runs = summary["repeats"]
        checks["outer_audits"] = (
            isinstance(runs, Sequence)
            and not isinstance(runs, (str, bytes))
            and len(runs) == 2
            and [run["repeat_index"] for run in runs] == [1, 2]
            and all(_repeat_structure_valid(run) for run in runs)
        )
        records = [record for run in runs for record in run["inner_records"]]
        checks["inner_residual"] = bool(
            checks["outer_audits"]
            and all(
                _finite_bounded(
                    record["final_relative_residual"],
                    W18A_INNER_TRUE_RESIDUAL_LIMIT,
                )
                for record in records
            )
        )
        checks["outer_auxiliary_residual"] = bool(
            checks["outer_audits"]
            and all(
                _finite_bounded(
                    run["checkpoints"]["2"]["true_relative_residual"],
                    W18A_INNER_TRUE_RESIDUAL_LIMIT,
                )
                for run in runs
            )
        )
        checks["finite"] = bool(
            checks["outer_audits"]
            and all(
                record["finite"]
                and run["checkpoints"][str(iteration)]["finite"]
                and run["measurements"][str(iteration)]["finite"]
                for run in runs
                for record in run["inner_records"]
                for iteration in W18A_CHECKPOINTS
            )
        )
        first, second = runs
        checks["repeat_identity"] = bool(
            checks["outer_audits"]
            and all(
                first["checkpoints"][str(iteration)][key]
                == second["checkpoints"][str(iteration)][key]
                for iteration in W18A_CHECKPOINTS
                for key in ("solution_sha256", "action_sha256")
            )
            and all(
                first["checkpoints"][str(iteration)][key] <= W18A_RELATIVE_IDENTITY_LIMIT
                and second["checkpoints"][str(iteration)][key]
                <= W18A_RELATIVE_IDENTITY_LIMIT
                for iteration in W18A_CHECKPOINTS
                for key in ("solution_relative_difference", "action_relative_difference")
            )
            and all(
                abs(
                    first["measurements"][str(iteration)][key]
                    - second["measurements"][str(iteration)][key]
                )
                <= W18A_RELATIVE_IDENTITY_LIMIT
                for iteration in W18A_CHECKPOINTS
                for key in ("rho", "normal_closure", "projection_orthogonality")
            )
        )
        checks["measurements"] = bool(
            checks["outer_audits"]
            and all(
                abs(
                    run["measurements"]["1"]["rho"] - W18A_RHO1_ANCHOR
                )
                <= W18A_RHO1_LIMIT
                and run["measurements"]["2"]["rho"] <= W18A_RHO2_LIMIT
                for run in runs
            )
            and all(
                _finite_bounded(
                    run["measurements"][str(iteration)]["normal_closure"],
                    W18A_CLOSURE_LIMIT,
                )
                and _finite_bounded(
                    run["measurements"][str(iteration)][
                        "projection_orthogonality"
                    ],
                    W18A_CLOSURE_LIMIT,
                )
                for run in runs
                for iteration in W18A_CHECKPOINTS
            )
        )
        checks["action_counts"] = _mapping_matches(
            summary["action_counts"], W18A_ACTION_COUNTS
        )
        checks["architecture"] = _mapping_matches(
            summary["architecture"], W18A_ARCHITECTURE
        )
        checks["lifecycle"] = _mapping_matches(
            summary["lifecycle"], W18A_LIFECYCLE
        )
        prediction = summary["prediction"]
        checks["prediction"] = _mapping_matches(
            prediction,
            {
                "bytes": W18A_PREDICTED_LIVE_SET_BYTES,
                "limit_bytes": W18A_PREDICTED_LIVE_SET_LIMIT_BYTES,
                "watchdog_limit_bytes": W18A_WATCHDOG_LIMIT_BYTES,
                "derived_not_measured": True,
                "swap_bytes": 0,
            },
        ) and prediction["bytes"] <= prediction["limit_bytes"]
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    return {
        "pass": bool(all(checks.values())),
        "checks": checks,
        "problems": sorted(
            name for name, passed in checks.items() if not passed
        ),
    }
