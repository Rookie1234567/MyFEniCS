"""Classify Task44 service startup and persisted completion receipts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_TERMINAL_STATES = {"inactive", "failed", "unknown", ""}


def _int_value(value: Any, minimum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _identity_matches(
    identity: Mapping[str, Any] | None,
    *,
    unit: str,
    cap_bytes: int,
    cpu_affinity: Sequence[int],
) -> bool:
    if not isinstance(identity, Mapping):
        return False
    expected_cpus = sorted(set(cpu_affinity))
    return bool(
        identity.get("service_unit") == unit
        and identity.get("active_state") == "active"
        and _int_value(identity.get("main_pid"), 2)
        and _int_value(identity.get("main_pid_start_ticks"), 1)
        and isinstance(identity.get("invocation_id"), str)
        and bool(identity.get("invocation_id"))
        and isinstance(identity.get("control_group"), str)
        and bool(identity.get("control_group"))
        and identity.get("memory_max_bytes") == cap_bytes
        and identity.get("memory_swap_max_bytes") == 0
        and identity.get("restart") == "no"
        and identity.get("kill_mode") == "control-group"
        and identity.get("cpu_affinity") == expected_cpus
        and identity.get("actual_process_cpu_affinity") == expected_cpus
    )


def _parse_cpu_set(value: Any) -> list[int] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    result: set[int] = set()
    try:
        for token in value.replace(",", " ").split():
            if "-" in token:
                low, high = (int(part) for part in token.split("-", 1))
                if high < low:
                    return None
                result.update(range(low, high + 1))
            else:
                result.add(int(token))
    except ValueError:
        return None
    return sorted(result)


def classify_service_startup(
    active_state: str,
    identity: Mapping[str, Any] | None,
    summary: Mapping[str, Any] | None,
    *,
    unit: str,
    cap_bytes: int,
    cpu_affinity: Sequence[int],
) -> str:
    """Return startup_pending, active_identity_ready, identity_invalid, completed, or failed."""
    if active_state == "active":
        if identity is None:
            return "startup_pending"
        return (
            "active_identity_ready"
            if _identity_matches(
                identity, unit=unit, cap_bytes=cap_bytes, cpu_affinity=cpu_affinity
            )
            else "identity_invalid"
        )
    terminal = active_state in _TERMINAL_STATES
    if not _identity_matches(
        identity, unit=unit, cap_bytes=cap_bytes, cpu_affinity=cpu_affinity
    ) or not isinstance(summary, Mapping):
        return "failed" if terminal else "startup_pending"
    task44 = summary.get("task44_service")
    guard = task44.get("service_gate_start") if isinstance(task44, Mapping) else None
    service = guard.get("service") if isinstance(guard, Mapping) else None
    if not isinstance(service, Mapping) or not isinstance(guard, Mapping):
        return "failed" if terminal else "startup_pending"
    identity_matches_summary = (
        summary.get("classification") == "COMPLETED"
        and task44.get("service_unit") == unit
        and guard.get("stop") is False
        and not guard.get("failures")
        and service.get("unit") == unit
        and service.get("main_pid") == identity.get("main_pid")
        and service.get("invocation_id") == identity.get("invocation_id")
        and service.get("control_group") == identity.get("control_group")
        and service.get("memory_max_bytes") == cap_bytes
        and service.get("cgroup_memory_max_bytes") == cap_bytes
        and service.get("swap_max_bytes") == 0
        and service.get("cgroup_swap_max_bytes") == 0
        and service.get("swap_current_bytes") == 0
        and _parse_cpu_set(service.get("cpu_affinity")) == sorted(set(cpu_affinity))
    )
    if identity_matches_summary:
        return "completed"
    return "failed" if terminal else "startup_pending"
