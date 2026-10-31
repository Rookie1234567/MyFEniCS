"""Classify Task44 service startup and persisted completion receipts."""

from __future__ import annotations

import os
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_TERMINAL_STATES = {"inactive", "failed", "unknown", ""}
_CGROUP_IDENTITY_ROUNDS = 6


def _read_cgroup_process_ids(cgroup_root: Path) -> set[int]:
    process_files = sorted(cgroup_root.rglob("cgroup.procs"))
    if not process_files:
        raise RuntimeError(f"no cgroup.procs files under {cgroup_root}")
    return {
        int(value)
        for path in process_files
        for value in path.read_text(encoding="ascii").split()
    }


def _read_process_identity(pid: int, proc_root: Path = Path("/proc")) -> dict[str, Any]:
    process_root = proc_root / str(pid)
    stat = (process_root / "stat").read_text(encoding="ascii")
    fields = stat[stat.rfind(")") + 2 :].split()
    if len(fields) <= 19:
        raise ValueError(f"short /proc/{pid}/stat record")
    state = fields[0]
    parent_pid = int(fields[1])
    start_ticks = int(fields[19])
    command_line = (
        (process_root / "cmdline")
        .read_bytes()
        .replace(b"\0", b" ")
        .decode("utf-8", errors="replace")
        .strip()
    )
    return {
        "pid": pid,
        "parent_pid": parent_pid,
        "state": state,
        "start_ticks": start_ticks,
        "command_line": command_line,
    }


def _observe_process_affinity(
    pid: int,
    expected_cpus: set[int],
    cgroup_root: Path,
    proc_root: Path,
) -> dict[str, Any]:
    observation: dict[str, Any] = {
        "pid": pid,
        "cgroup_path": str(cgroup_root),
        "expected_cpu_affinity": sorted(expected_cpus),
        "affinity_samples": [],
    }
    try:
        members_before = _read_cgroup_process_ids(cgroup_root)
        identity_before = _read_process_identity(pid, proc_root)
    except (OSError, ValueError, RuntimeError) as exc:
        observation.update({"status": "identity_unreadable", "error": str(exc)})
        return observation
    if pid not in members_before:
        observation.update({"status": "transient_identity", "reason": "pid_not_in_initial_cgroup_membership"})
        return observation

    try:
        affinity = sorted(os.sched_getaffinity(pid))
    except (ProcessLookupError, PermissionError, OSError) as exc:
        try:
            members_after = _read_cgroup_process_ids(cgroup_root)
            identity_after = _read_process_identity(pid, proc_root)
        except (OSError, ValueError, RuntimeError):
            members_after, identity_after = set(), None
        if pid not in members_after or (
            identity_after is not None
            and identity_after["start_ticks"] != identity_before["start_ticks"]
        ):
            observation.update({
                "status": "transient_identity",
                "identity_before": identity_before,
                "identity_after": identity_after,
                "member_pids_before": sorted(members_before),
                "member_pids_after": sorted(members_after),
                "reason": "pid_exited_or_was_reused_during_affinity_read",
            })
        else:
            observation.update({
                "status": "affinity_unreadable",
                "identity": identity_before,
                "error": str(exc),
            })
        return observation

    sample = {
        "timestamp_monotonic_ns": time.monotonic_ns(),
        "identity": identity_before,
        "cpu_affinity": affinity,
    }
    observation["affinity_samples"].append(sample)
    try:
        identity_after = _read_process_identity(pid, proc_root)
        members_after = _read_cgroup_process_ids(cgroup_root)
    except (OSError, ValueError, RuntimeError) as exc:
        observation.update({"status": "identity_unreadable", "error": str(exc)})
        return observation
    if (
        identity_after["start_ticks"] != identity_before["start_ticks"]
        or pid not in members_after
    ):
        observation.update({
            "status": "transient_identity",
            "identity_before": identity_before,
            "identity_after": identity_after,
            "member_pids_before": sorted(members_before),
            "member_pids_after": sorted(members_after),
            "reason": "pid_exited_or_was_reused_during_affinity_read",
        })
        return observation

    observation["identity"] = identity_after
    if affinity == sorted(expected_cpus):
        observation["status"] = "stable_match"
        return observation

    # A wrong affinity is actionable only after the same PID/start-tick remains
    # in this cgroup and a second scheduler query confirms the mismatch.
    time.sleep(0.01)
    try:
        confirm_members_before = _read_cgroup_process_ids(cgroup_root)
        confirm_identity_before = _read_process_identity(pid, proc_root)
        confirm_affinity = sorted(os.sched_getaffinity(pid))
        confirm_identity_after = _read_process_identity(pid, proc_root)
        confirm_members_after = _read_cgroup_process_ids(cgroup_root)
    except (ProcessLookupError, PermissionError, OSError, ValueError, RuntimeError) as exc:
        observation.update({
            "status": "transient_identity",
            "reason": "process_disappeared_during_mismatch_confirmation",
            "identity": identity_after,
            "confirmation_error": str(exc),
        })
        return observation
    observation["affinity_samples"].append({
        "timestamp_monotonic_ns": time.monotonic_ns(),
        "identity": confirm_identity_before,
        "cpu_affinity": confirm_affinity,
    })
    still_same_member = (
        pid in confirm_members_before
        and pid in confirm_members_after
        and confirm_identity_before["start_ticks"] == identity_after["start_ticks"]
        and confirm_identity_after["start_ticks"] == identity_after["start_ticks"]
    )
    if not still_same_member:
        observation.update({
            "status": "transient_identity",
            "identity_before_confirmation": confirm_identity_before,
            "identity_after_confirmation": confirm_identity_after,
            "member_pids_before_confirmation": sorted(confirm_members_before),
            "member_pids_after_confirmation": sorted(confirm_members_after),
            "reason": "pid_exited_or_was_reused_before_mismatch_confirmation",
        })
    elif confirm_affinity == sorted(expected_cpus):
        observation["status"] = "affinity_unstable"
        observation["reason"] = "same_process_affinity_changed_between_confirmations"
    else:
        observation["status"] = "stable_mismatch"
    return observation


def observe_cgroup_cpu_affinity(
    cgroup_root: str | Path,
    expected_cpus: Sequence[int],
    *,
    proc_root: str | Path = "/proc",
) -> dict[str, Any]:
    """Verify current cgroup process affinities without trusting bare PIDs.

    A process is only reported as an actionable mismatch when two scheduler
    reads are bound to the same start tick and the PID remains in this exact
    cgroup. Processes that disappear or are replaced during observation are
    recorded as transient and retried when they remain members.
    """
    root = Path(cgroup_root)
    proc_path = Path(proc_root)
    expected = set(expected_cpus)
    observations: list[dict[str, Any]] = []
    accepted: dict[int, dict[str, Any]] = {}
    try:
        pending = _read_cgroup_process_ids(root)
    except (OSError, ValueError, RuntimeError) as exc:
        return {
            "stop": True,
            "reason": "cgroup_membership_unreadable",
            "cgroup_path": str(root),
            "error": str(exc),
            "expected_cpu_affinity": sorted(expected),
            "observations": observations,
        }
    initial_members = sorted(pending)
    unresolved: set[int] = set()
    # Short-lived compiler children can enter the service cgroup while startup
    # is being inspected. Give their identities a few more bounded retries;
    # unresolved members still fail closed below.
    for _round in range(_CGROUP_IDENTITY_ROUNDS):
        for pid in sorted(pending):
            observation = _observe_process_affinity(pid, expected, root, proc_path)
            observations.append(observation)
            if observation["status"] != "transient_identity":
                accepted[pid] = observation
        try:
            current_members = _read_cgroup_process_ids(root)
        except (OSError, ValueError, RuntimeError) as exc:
            return {
                "stop": True,
                "reason": "cgroup_membership_unreadable",
                "cgroup_path": str(root),
                "error": str(exc),
                "expected_cpu_affinity": sorted(expected),
                "member_pids_initial": initial_members,
                "observations": observations,
            }
        for pid in list(accepted):
            observation = accepted[pid]
            if pid not in current_members:
                accepted.pop(pid)
                observations.append({
                    "pid": pid,
                    "status": "transient_identity",
                    "cgroup_path": str(root),
                    "reason": "pid_no_longer_in_final_cgroup_membership",
                    "previous_status": observation["status"],
                    "identity": observation.get("identity"),
                })
                continue
            try:
                current_identity = _read_process_identity(pid, proc_path)
            except (OSError, ValueError, RuntimeError) as exc:
                observation.update({"status": "affinity_unreadable", "error": str(exc)})
                continue
            recorded_identity = observation.get("identity")
            if (
                recorded_identity is not None
                and current_identity["start_ticks"] != recorded_identity["start_ticks"]
            ):
                accepted.pop(pid)
                observations.append({
                    "pid": pid,
                    "status": "transient_identity",
                    "cgroup_path": str(root),
                    "reason": "pid_reused_before_final_membership_check",
                    "identity_before": recorded_identity,
                    "identity_after": current_identity,
                })
        pending = current_members - set(accepted)
        unresolved = set(pending)
        if not pending:
            break

    try:
        final_members = _read_cgroup_process_ids(root)
    except (OSError, ValueError, RuntimeError) as exc:
        final_members = set()
        unresolved = set(initial_members)
        membership_error = str(exc)
    else:
        membership_error = None
        unresolved = final_members - set(accepted)
    for pid in sorted(unresolved):
        observations.append({
            "pid": pid,
            "status": "membership_unstable",
            "cgroup_path": str(root),
            "reason": "active_cgroup_process_identity_did_not_stabilize",
        })

    active_observations = [
        observation
        for pid, observation in accepted.items()
        if pid in final_members
    ]
    mismatches = [
        observation
        for observation in active_observations
        if observation["status"] in {"stable_mismatch", "affinity_unstable"}
    ]
    unreadable = [
        observation
        for observation in active_observations
        if observation["status"] in {"identity_unreadable", "affinity_unreadable"}
    ]
    failures = [
        f"service_pid_affinity_mismatch:{row['pid']}"
        for row in mismatches
    ] + [
        f"service_pid_affinity_unreadable:{row['pid']}"
        for row in unreadable
    ] + [
        f"service_pid_identity_unstable:{pid}"
        for pid in sorted(unresolved)
    ]
    return {
        "stop": bool(failures or membership_error),
        "reason": "MONITORING_FAILED" if failures or membership_error else None,
        "failures": failures,
        "cgroup_path": str(root),
        "expected_cpu_affinity": sorted(expected),
        "member_pids_initial": initial_members,
        "member_pids_final": sorted(final_members),
        "service_pid_affinities": {
            str(row["pid"]): row.get("affinity_samples", [{}])[-1].get("cpu_affinity")
            for row in active_observations
            if row["status"] in {"stable_match", "stable_mismatch", "affinity_unstable"}
        },
        "mismatch_processes": mismatches,
        "observations": observations,
        **({"cgroup_membership_error": membership_error} if membership_error else {}),
    }


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
        and identity.get("system_call_filter") == "~sched_setaffinity"
        and identity.get("system_call_error_number") in {"EPERM", "1"}
        and isinstance(identity.get("sched_setaffinity_filter_test"), Mapping)
        and identity["sched_setaffinity_filter_test"].get("status") == "pass"
        and identity["sched_setaffinity_filter_test"].get("errno") == "EPERM"
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
        and service.get("system_call_filter") == identity.get("system_call_filter")
        and service.get("system_call_error_number") == identity.get("system_call_error_number")
        and _parse_cpu_set(service.get("cpu_affinity")) == sorted(set(cpu_affinity))
    )
    if identity_matches_summary:
        return "completed"
    return "failed" if terminal else "startup_pending"
