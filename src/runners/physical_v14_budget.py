"""Shared accounting for the reviewed V14 workflow ledger.

The measured workflow clock and administrative policy charges are deliberately
kept in separate fields.  All V14 callers use this reader so an
infrastructure-recovery reservation cannot disappear when the launcher,
worker, and finalizer inspect the same ledger at different times.
"""

from __future__ import annotations

import math
from typing import Any, Mapping


def _finite_nonnegative(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"V14 budget field {field!r} must be a number")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"V14 budget field {field!r} must be finite and non-negative")
    return result


def read_v14_effective_budget(ledger: Mapping[str, Any]) -> dict[str, Any]:
    """Return effective budget facts without mutating measured elapsed time.

    ``elapsed_seconds`` is measured workflow time only.  Non-refundable
    administrative charges live in ``policy_debits``; bounded conservative
    allowances have their own field.  Active reservations are reported
    separately.  The current worker's own reservation is part of
    ``active_reservations_seconds``; callers that need a worker-local clock
    must use the lease reservation rather than subtracting it a second time.
    """

    total = _finite_nonnegative(
        ledger.get("total_budget_seconds"), field="total_budget_seconds"
    )
    measured = _finite_nonnegative(
        ledger.get("elapsed_seconds"), field="elapsed_seconds"
    )
    conservative_allowance = _finite_nonnegative(
        ledger.get("conservative_allowance_seconds", 0.0),
        field="conservative_allowance_seconds",
    )
    raw_debits = ledger.get("policy_debits", [])
    if not isinstance(raw_debits, list):
        raise ValueError("V14 policy_debits must be a list")
    policy_debits: list[dict[str, Any]] = []
    policy_total = 0.0
    for index, raw in enumerate(raw_debits):
        if not isinstance(raw, Mapping):
            raise ValueError(f"V14 policy debit {index} is not an object")
        seconds = _finite_nonnegative(
            raw.get("seconds"), field=f"policy_debits[{index}].seconds"
        )
        entry = dict(raw)
        entry["seconds"] = seconds
        policy_debits.append(entry)
        policy_total += seconds

    active_reservations = 0.0
    active_attempts: list[dict[str, Any]] = []
    stages = ledger.get("stages", {})
    if not isinstance(stages, Mapping):
        raise ValueError("V14 ledger stages must be an object")
    for stage, raw_stage in stages.items():
        if not isinstance(raw_stage, Mapping):
            raise ValueError(f"V14 stage {stage!r} is not an object")
        active_index = raw_stage.get("active_attempt")
        if active_index is None:
            continue
        if isinstance(active_index, bool) or not isinstance(active_index, int):
            raise ValueError(f"V14 stage {stage!r} active_attempt is invalid")
        attempts = raw_stage.get("attempts", [])
        if not isinstance(attempts, list) or not 0 <= active_index < len(attempts):
            raise ValueError(f"V14 stage {stage!r} active attempt is missing")
        attempt = attempts[active_index]
        if not isinstance(attempt, Mapping):
            raise ValueError(f"V14 stage {stage!r} active attempt is not an object")
        reserved = _finite_nonnegative(
            attempt.get("reserved_seconds"),
            field=f"stages.{stage}.attempts[{active_index}].reserved_seconds",
        )
        active_reservations += reserved
        active_attempts.append(
            {
                "stage": str(stage),
                "attempt_index": active_index,
                "reserved_seconds": reserved,
                "recovery_id": attempt.get("recovery_id"),
            }
        )

    budget_used = measured + policy_total + conservative_allowance
    remaining = total - budget_used - active_reservations
    return {
        "total_budget_seconds": total,
        "measured_elapsed_seconds": measured,
        "policy_debit_seconds": policy_total,
        "conservative_allowance_seconds": conservative_allowance,
        "budget_used_seconds": budget_used,
        "active_reservations_seconds": active_reservations,
        "remaining_seconds": remaining,
        "policy_debits": policy_debits,
        "active_attempts": active_attempts,
        "elapsed_seconds_semantics": "measured_workflow_time_only",
    }


__all__ = ["read_v14_effective_budget"]
