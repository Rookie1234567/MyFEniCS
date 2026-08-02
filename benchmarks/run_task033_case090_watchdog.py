from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Mapping

from benchmarks.task033_case090_pde_core import (
    CASE_ID,
    MPI_SIZES,
    WATCHDOG_SCHEMA_VERSION,
    attach_evidence_sha256,
    inspect_tracked_source,
    validate_watchdog_summary,
    write_json_object,
)
from benchmarks.task034_wsl_resources import (
    effective_memory_limit,
    resource_authority_sample,
)
from benchmarks.watchdog_process_control import (
    terminate_process_tree,
    worker_process_group_popen_kwargs,
)


ROOT = Path(__file__).resolve().parents[1]
GIB = 1024**3
MAX_EFFECTIVE_MEMORY_BYTES = 14 * GIB
WARNING_SCALE = 11.5 / 14.0
TERMINATION_SCALE = 13.0 / 14.0


def _run_status(
    failures: list[str], *, development: bool
) -> tuple[str, bool, bool]:
    """Return status and qualification flags without changing formal semantics."""

    if development:
        return "unqualified_development_probe", False, not failures
    return ("passed" if not failures else "failed"), not failures, not failures


def _read_nonnegative_integer(path: Path) -> int | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
        if value.lower() == "max":
            return None
        result = int(value)
    except (OSError, TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _cgroup_value(names: tuple[str, ...]) -> tuple[int | None, str | None]:
    roots = (Path("/sys/fs/cgroup"), Path("/sys/fs/cgroup/memory"))
    for root in roots:
        for name in names:
            path = root / name
            value = _read_nonnegative_integer(path)
            if value is not None:
                return value, str(path)
    return None, None


def _cgroup_limit() -> tuple[int | None, str | None, str]:
    for path in (
        Path("/sys/fs/cgroup/memory.max"),
        Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
    ):
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if raw.lower() == "max":
            return None, str(path), "unbounded"
        try:
            value = int(raw)
        except ValueError:
            return None, str(path), "unreadable"
        if value <= 0:
            return None, str(path), "unreadable"
        return value, str(path), "finite"
    return None, None, "unreadable"


def _proc_meminfo() -> dict[str, int]:
    result: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            name, raw = line.split(":", 1)
            fields = raw.strip().split()
            if fields:
                result[name] = int(fields[0]) * 1024
    except (OSError, TypeError, ValueError):
        return {}
    return result


def _linux_process_tree_rss(root_pid: int) -> tuple[int, int]:
    parent_by_pid: dict[int, int] = {}
    rss_by_pid: dict[int, int] = {}
    page_size = int(os.sysconf("SC_PAGE_SIZE"))
    try:
        proc_entries = list(Path("/proc").iterdir())
    except OSError:
        return 0, 0
    for entry in proc_entries:
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text(encoding="utf-8")
            close = stat.rfind(")")
            fields = stat[close + 2 :].split()
            parent_by_pid[int(entry.name)] = int(fields[1])
            statm = (entry / "statm").read_text(encoding="utf-8").split()
            rss_by_pid[int(entry.name)] = int(statm[1]) * page_size
        except (OSError, IndexError, TypeError, ValueError):
            continue
    descendants = {int(root_pid)}
    changed = True
    while changed:
        changed = False
        for pid, parent in parent_by_pid.items():
            if parent in descendants and pid not in descendants:
                descendants.add(pid)
                changed = True
    live = [pid for pid in descendants if pid in rss_by_pid]
    return sum(rss_by_pid[pid] for pid in live), len(live)


def _portable_process_tree_rss(root_pid: int) -> tuple[int, int]:
    if Path("/proc").is_dir():
        return _linux_process_tree_rss(root_pid)
    try:
        import psutil

        process = psutil.Process(root_pid)
        processes = [process, *process.children(recursive=True)]
        rss = sum(item.memory_info().rss for item in processes if item.is_running())
        return int(rss), len(processes)
    except Exception:
        return 0, 0


def _is_wsl_runtime() -> bool:
    try:
        release = Path("/proc/sys/kernel/osrelease").read_text(
            encoding="utf-8"
        )
    except OSError:
        return False
    return "microsoft" in release.lower()


def sample_memory(root_pid: int, *, worker_alive: bool) -> dict[str, Any]:
    sample_root_pid = (
        int(root_pid)
        if worker_alive and int(root_pid) > 0
        else os.getpid()
    )
    if not _is_wsl_runtime():
        worker_rss, live_workers = _portable_process_tree_rss(sample_root_pid)
        cgroup_current, cgroup_current_source = _cgroup_value(
            ("memory.current", "memory.usage_in_bytes")
        )
        cgroup_limit, cgroup_limit_source, cgroup_limit_state = _cgroup_limit()
        swap_current, swap_source = _cgroup_value(("memory.swap.current",))
        if swap_current is None:
            memsw_current, memsw_source = _cgroup_value(
                ("memory.memsw.usage_in_bytes",)
            )
            if memsw_current is not None and cgroup_current is not None:
                swap_current = max(0, memsw_current - cgroup_current)
                swap_source = f"{memsw_source} minus {cgroup_current_source}"
        meminfo = _proc_meminfo()
        if swap_current is None and meminfo:
            swap_current = max(
                0, meminfo.get("SwapTotal", 0) - meminfo.get("SwapFree", 0)
            )
            swap_source = "/proc/meminfo SwapTotal-SwapFree"
        host_available = meminfo.get("MemAvailable")
        return {
            "monotonic_seconds": time.monotonic(),
            "worker_alive": bool(worker_alive),
            "live_worker_process_count": int(live_workers),
            "worker_tree_rss_sum_bytes": int(worker_rss),
            "cgroup_memory_current_bytes": cgroup_current,
            "observed_memory_bytes": int(max(worker_rss, cgroup_current or 0)),
            "swap_current_bytes": swap_current,
            "host_available_memory_bytes": host_available,
            "sources": {
                "cgroup_memory_current": cgroup_current_source,
                "cgroup_memory_limit": cgroup_limit_source,
                "swap_current": swap_source,
            },
            "cgroup_memory_limit_bytes": cgroup_limit,
            "cgroup_memory_limit_state": cgroup_limit_state,
            "resource_authority_mode": "legacy_finite_cgroup_14g",
        }

    authority = resource_authority_sample(sample_root_pid)
    process_tree = authority["process_tree"]
    cgroup = authority["job_cgroup"]
    memory = effective_memory_limit()
    cgroup_limit, cgroup_limit_source, cgroup_limit_state = _cgroup_limit()
    dedicated = cgroup.get("dedicated_job_cgroup") is True
    if not dedicated:
        cgroup_limit = cgroup.get("memory_limit_bytes")
        cgroup_limit_source = cgroup.get("path")
        cgroup_limit_state = (
            "not_dedicated_unbounded_or_unreadable_diagnostic_only"
        )
    dedicated_swap = cgroup.get("swap_current_bytes") if dedicated else None
    process_tree_swap = process_tree.get("swap_bytes")
    job_swap = (
        max(int(process_tree_swap), int(dedicated_swap or 0))
        if isinstance(process_tree_swap, int)
        and (dedicated_swap is None or isinstance(dedicated_swap, int))
        else None
    )
    return {
        "monotonic_seconds": time.monotonic(),
        "worker_alive": bool(worker_alive),
        "live_worker_process_count": len(process_tree.get("pids") or ()),
        "worker_tree_rss_sum_bytes": process_tree.get("rss_bytes"),
        "process_tree_swap_bytes": process_tree_swap,
        "process_tree_all_status_readable": process_tree.get(
            "all_status_readable"
        ),
        "cgroup_memory_current_bytes": cgroup.get("memory_current_bytes"),
        "cgroup_memory_is_dedicated_job_authority": dedicated,
        "dedicated_cgroup_swap_current_bytes": dedicated_swap,
        "observed_memory_bytes": authority.get("memory_authority_bytes"),
        "swap_current_bytes": job_swap,
        "host_available_memory_bytes": memory.get("mem_available_bytes"),
        "sources": {
            "cgroup_memory_current": cgroup.get("path"),
            "cgroup_memory_limit": cgroup_limit_source,
            "swap_current": (
                "process-tree VmSwap plus dedicated job cgroup swap"
            ),
        },
        "cgroup_memory_limit_bytes": cgroup_limit,
        "cgroup_memory_limit_state": cgroup_limit_state,
        "resource_authority_mode": "task034_wsl_effective_limit",
        "resource_authority_semantics": authority.get(
            "memory_authority_semantics"
        ),
        "formal_swap_semantics": authority.get("formal_swap_semantics"),
        "task034_effective_limit": memory,
        "wsl_vm_global_swap_diagnostic": authority.get(
            "wsl_vm_global_swap_diagnostic"
        ),
    }

def build_preflight(sample: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    mode = sample.get("resource_authority_mode")
    if mode == "task034_wsl_effective_limit":
        failures: list[str] = []
        memory = sample.get("task034_effective_limit")
        memory = memory if isinstance(memory, dict) else {}
        effective = memory.get("effective_limit_bytes")
        warning = memory.get("warning_bytes")
        termination = memory.get("termination_bytes")
        host_available = sample.get("host_available_memory_bytes")
        swap_current = sample.get("swap_current_bytes")
        observed = sample.get("observed_memory_bytes")
        if not isinstance(effective, int) or effective <= 0:
            failures.append("Task034 WSL effective memory limit is unreadable")
        if not isinstance(warning, int) or not isinstance(termination, int):
            failures.append("Task034 WSL warning/termination thresholds are unreadable")
        if not isinstance(host_available, int) or host_available <= 0:
            failures.append("preflight host available memory is unreadable")
        if not isinstance(observed, int) or observed < 0:
            failures.append("preflight process-tree memory authority is unreadable")
        if sample.get("process_tree_all_status_readable") is not True:
            failures.append("preflight process-tree status authority is unreadable")
        if not isinstance(swap_current, int) or swap_current < 0:
            failures.append("preflight job swap authority is unreadable")
        elif swap_current != 0:
            failures.append("preflight job swap authority is nonzero")
        return (
            {
                "passed": not failures,
                "resource_authority_mode": mode,
                "cgroup_memory_limit_state": sample.get(
                    "cgroup_memory_limit_state"
                ),
                "cgroup_memory_limit_bytes": sample.get(
                    "cgroup_memory_limit_bytes"
                ),
                "cgroup_memory_current_bytes": sample.get(
                    "cgroup_memory_current_bytes"
                ),
                "cgroup_memory_is_dedicated_job_authority": sample.get(
                    "cgroup_memory_is_dedicated_job_authority"
                ),
                "host_available_memory_bytes": host_available,
                "swap_current_bytes": swap_current,
                "effective_memory_bytes": effective,
                "effective_memory_definition": memory.get("formula"),
                "warning_threshold_bytes": warning,
                "termination_threshold_bytes": termination,
                "warning_scale": 0.80,
                "termination_scale": 0.95,
                "task034_effective_limit": memory,
                "failures": failures,
            },
            failures,
        )

    failures = []
    limit = sample.get("cgroup_memory_limit_bytes")
    limit_state = sample.get("cgroup_memory_limit_state")
    cgroup_current = sample.get("cgroup_memory_current_bytes")
    host_available = sample.get("host_available_memory_bytes")
    swap_current = sample.get("swap_current_bytes")
    if limit_state == "unbounded":
        failures.append("preflight container memory limit is unbounded")
    elif limit_state != "finite" or not isinstance(limit, int) or limit <= 0:
        failures.append("preflight container memory limit is unreadable")
    if not isinstance(cgroup_current, int) or cgroup_current < 0:
        failures.append("preflight cgroup memory.current is unreadable")
    if not isinstance(host_available, int) or host_available <= 0:
        failures.append("preflight host available memory is unreadable")
    if not isinstance(swap_current, int) or swap_current < 0:
        failures.append("preflight swap current is unreadable")
    elif swap_current != 0:
        failures.append("preflight swap current is nonzero")
    effective = (
        min(limit, host_available, MAX_EFFECTIVE_MEMORY_BYTES)
        if not failures
        and isinstance(limit, int)
        and isinstance(host_available, int)
        else None
    )
    warning = int(effective * WARNING_SCALE) if effective is not None else None
    termination = (
        int(effective * TERMINATION_SCALE) if effective is not None else None
    )
    return (
        {
            "passed": not failures,
            "resource_authority_mode": "legacy_finite_cgroup_14g",
            "cgroup_memory_limit_state": limit_state,
            "cgroup_memory_limit_bytes": limit,
            "cgroup_memory_current_bytes": cgroup_current,
            "host_available_memory_bytes": host_available,
            "swap_current_bytes": swap_current,
            "effective_memory_bytes": effective,
            "effective_memory_definition": (
                "min(finite container limit, preflight host available, 14 GiB)"
            ),
            "warning_threshold_bytes": warning,
            "termination_threshold_bytes": termination,
            "warning_scale": WARNING_SCALE,
            "termination_scale": TERMINATION_SCALE,
            "failures": failures,
        },
        failures,
    )

def watchdog_decision(
    sample: dict[str, Any],
    *,
    preflight: dict[str, Any],
    elapsed_seconds: float,
    wall_timeout_seconds: float,
) -> dict[str, Any]:
    """Return the immediate control decision for one live sample."""

    mode = preflight.get("resource_authority_mode")
    required = [
        "worker_tree_rss_sum_bytes",
        "observed_memory_bytes",
        "swap_current_bytes",
        "host_available_memory_bytes",
    ]
    if mode != "task034_wsl_effective_limit":
        required.extend(
            ["cgroup_memory_current_bytes", "cgroup_memory_limit_bytes"]
        )
    for field in required:
        if not isinstance(sample.get(field), int) or sample[field] < 0:
            return {
                "warning": False,
                "terminate": True,
                "trigger": "authority_unreadable",
                "detail": field,
            }
    if mode == "task034_wsl_effective_limit":
        if sample.get("process_tree_all_status_readable") is not True:
            return {
                "warning": False,
                "terminate": True,
                "trigger": "authority_unreadable",
                "detail": "process_tree_status",
            }
        if sample.get("cgroup_memory_is_dedicated_job_authority") is True and not isinstance(
            sample.get("dedicated_cgroup_swap_current_bytes"), int
        ):
            return {
                "warning": False,
                "terminate": True,
                "trigger": "authority_unreadable",
                "detail": "dedicated_cgroup_swap",
            }
    elif sample.get("cgroup_memory_limit_state") != "finite":
        return {
            "warning": False,
            "terminate": True,
            "trigger": "authority_unreadable",
            "detail": "cgroup_memory_limit",
        }
    if sample["swap_current_bytes"] != 0:
        return {
            "warning": False,
            "terminate": True,
            "trigger": "nonzero_swap",
            "detail": str(sample["swap_current_bytes"]),
        }
    if elapsed_seconds >= wall_timeout_seconds:
        return {
            "warning": False,
            "terminate": True,
            "trigger": "wall_timeout",
            "detail": str(wall_timeout_seconds),
        }
    observed = int(sample["observed_memory_bytes"])
    termination = int(preflight["termination_threshold_bytes"])
    warning = int(preflight["warning_threshold_bytes"])
    if observed >= termination:
        return {
            "warning": True,
            "terminate": True,
            "trigger": "memory_termination_threshold",
            "detail": str(observed),
        }
    return {
        "warning": observed >= warning,
        "terminate": False,
        "trigger": "memory_warning_threshold" if observed >= warning else None,
        "detail": str(observed) if observed >= warning else None,
    }


def _natural_exit_after_process_tree_sample(
    process: subprocess.Popen[Any],
    decision: Mapping[str, Any],
) -> int | None:
    """Return an exit code only for a /proc teardown race.

    A process-tree sample can begin while ``mpiexec`` is alive and lose one
    rank's ``/proc/<pid>/status`` while that rank exits naturally. Re-polling
    is intentionally restricted to this authority failure: unreadable status
    while the worker remains live still fails closed.
    """

    if (
        decision.get("trigger") != "authority_unreadable"
        or decision.get("detail") != "process_tree_status"
    ):
        return None
    polled = process.poll()
    if polled is not None:
        return int(polled)
    try:
        return int(process.wait(timeout=0.10))
    except subprocess.TimeoutExpired:
        return None


def _readable_process_tree_resample(
    process: subprocess.Popen[Any],
    decision: Mapping[str, Any],
    first_sample: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Take one immediate status resample for the narrowly defined race."""

    if (
        decision.get("trigger") != "authority_unreadable"
        or decision.get("detail") != "process_tree_status"
    ):
        return None
    sample = sample_memory(process.pid, worker_alive=True)
    if sample.get("process_tree_all_status_readable") is not True:
        return None
    sample["observed_memory_bytes"] = max(
        int(first_sample["observed_memory_bytes"]),
        int(sample["observed_memory_bytes"]),
    )
    sample["swap_current_bytes"] = max(
        int(first_sample["swap_current_bytes"]),
        int(sample["swap_current_bytes"]),
    )
    sample["process_tree_resample_conservative_carry_forward"] = True
    sample["sample_kind"] = "worker_resample"
    return sample


def _git_ignored(path: Path) -> bool:
    try:
        completed = subprocess.run(
            ["git", "check-ignore", "--quiet", str(Path(path).resolve())],
            cwd=ROOT,
            check=False,
        )
    except OSError:
        return False
    return completed.returncode == 0


def summarize_samples(
    samples: list[dict[str, Any]],
    *,
    raw_output: Path,
    summary_output: Path,
    preflight: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    resource_mode = (
        preflight.get("resource_authority_mode")
        if isinstance(preflight, dict)
        else None
    )
    task034_wsl = resource_mode == "task034_wsl_effective_limit"
    if len(samples) < 2:
        failures.append("watchdog requires at least two samples")

    def integers(name: str) -> list[int]:
        return [
            int(sample[name])
            for sample in samples
            if isinstance(sample.get(name), int) and sample[name] >= 0
        ]

    worker_rss = integers("worker_tree_rss_sum_bytes")
    cgroup_current = integers("cgroup_memory_current_bytes")
    observed = integers("observed_memory_bytes")
    limits = integers("cgroup_memory_limit_bytes")
    host_available = integers("host_available_memory_bytes")
    swap = integers("swap_current_bytes")
    process_tree_swap = integers("process_tree_swap_bytes")
    required_series = [
        ("worker tree RSS", worker_rss),
        ("observed memory", observed),
        ("host available memory", host_available),
        ("swap current", swap),
    ]
    if task034_wsl:
        required_series.append(("process-tree swap", process_tree_swap))
    else:
        required_series.extend(
            [
                ("cgroup memory.current", cgroup_current),
                ("cgroup/container limit", limits),
            ]
        )
    for label, values in required_series:
        if len(values) != len(samples):
            failures.append(f"{label} was not available for every sample")
    limit_states = [sample.get("cgroup_memory_limit_state") for sample in samples]
    if not task034_wsl:
        if any(state == "unbounded" for state in limit_states):
            failures.append("cgroup/container limit was unbounded during sampling")
        elif any(state != "finite" for state in limit_states):
            failures.append("cgroup/container limit authority was unreadable during sampling")
    nonzero_swap_count = sum(value != 0 for value in swap)
    if nonzero_swap_count:
        failures.append("swap current was nonzero during one or more samples")
    required_authorities = [
        "worker_tree_rss_sum_bytes",
        "observed_memory_bytes",
        "host_available_memory_bytes",
        "swap_current_bytes",
    ]
    if task034_wsl:
        required_authorities.extend(
            ["process_tree_swap_bytes", "process_tree_all_status_readable"]
        )
    else:
        required_authorities.extend(
            ["cgroup_memory_current_bytes", "cgroup_memory_limit_bytes"]
        )
    authority_unreadable_count = sum(
        any(
            (
                sample.get(field) is not True
                if field == "process_tree_all_status_readable"
                else not isinstance(sample.get(field), int) or sample[field] < 0
            )
            for field in required_authorities
        )
        for sample in samples
        if (
            sample.get("process_tree_exit_race_observed") is not True
            and sample.get("process_tree_status_resample_succeeded") is not True
        )
    )
    initial_swap = swap[0] if swap else None
    final_swap = swap[-1] if swap else None
    peak_swap = max(swap) if swap else None
    swap_growth = (
        max(0, peak_swap - initial_swap)
        if peak_swap is not None and initial_swap is not None
        else None
    )
    limit = min(limits) if limits else None
    observed_peak = max(observed) if observed else None
    if preflight is None and samples:
        preflight, preflight_failures = build_preflight(samples[0])
        failures.extend(preflight_failures)
    effective = preflight.get("effective_memory_bytes") if preflight else None
    warning_threshold = preflight.get("warning_threshold_bytes") if preflight else None
    termination_threshold = (
        preflight.get("termination_threshold_bytes") if preflight else None
    )
    if (
        isinstance(observed_peak, int)
        and isinstance(termination_threshold, int)
        and observed_peak >= termination_threshold
    ):
        failures.append("observed memory reached the scaled termination threshold")
    raw_ignored = _git_ignored(raw_output)
    summary_ignored = _git_ignored(summary_output)
    if not raw_ignored:
        failures.append("raw watchdog JSONL is not git-ignored")
    if not summary_ignored:
        failures.append("watchdog summary JSON is not git-ignored")
    sources: dict[str, list[str]] = {}
    for name in ("cgroup_memory_current", "cgroup_memory_limit", "swap_current"):
        sources[name] = sorted(
            {
                str(sample.get("sources", {}).get(name))
                for sample in samples
                if isinstance(sample.get("sources"), dict)
                and sample["sources"].get(name) is not None
            }
        )
    return (
        {
            "sample_count": len(samples),
            "worker_tree_rss_peak_bytes": max(worker_rss) if worker_rss else None,
            "cgroup_memory_current_peak_bytes": (
                max(cgroup_current) if cgroup_current else None
            ),
            "observed_memory_peak_bytes": observed_peak,
            "observed_memory_definition": (
                "max(process-tree RSS, dedicated job cgroup memory.current when present)"
                if task034_wsl
                else "max(live worker process-tree RSS sum, cgroup memory.current) per sample"
            ),
            "resource_authority_mode": resource_mode,
            "process_tree_swap_peak_bytes": (
                max(process_tree_swap) if process_tree_swap else None
            ),
            "dedicated_job_cgroup_observed": any(
                sample.get("cgroup_memory_is_dedicated_job_authority") is True
                for sample in samples
            ),
            "cgroup_memory_limit_bytes": limit,
            "cgroup_memory_limit_state": (
                "not_dedicated_unbounded_or_unreadable_diagnostic_only"
                if task034_wsl
                and not any(
                    sample.get("cgroup_memory_is_dedicated_job_authority") is True
                    for sample in samples
                )
                else "finite"
                if limit_states and all(state == "finite" for state in limit_states)
                else "unbounded"
                if "unbounded" in limit_states
                else "unreadable"
            ),
            "effective_memory_bytes": effective,
            "warning_threshold_bytes": warning_threshold,
            "termination_threshold_bytes": termination_threshold,
            "host_available_memory_min_bytes": (
                min(host_available) if host_available else None
            ),
            "swap_current_initial_bytes": initial_swap,
            "swap_current_final_bytes": final_swap,
            "swap_current_peak_bytes": peak_swap,
            "swap_current_delta_bytes": swap_growth,
            "swap_current_net_delta_bytes": (
                final_swap - initial_swap
                if final_swap is not None and initial_swap is not None
                else None
            ),
            "nonzero_swap_sample_count": nonzero_swap_count,
            "authority_unreadable_sample_count": authority_unreadable_count,
            "raw_output": str(Path(raw_output).resolve()),
            "raw_output_ignored_by_git": raw_ignored,
            "summary_output_ignored_by_git": summary_ignored,
            "sources": sources,
        },
        failures,
    )


def run_watchdog(args: argparse.Namespace) -> int:
    development = bool(args.development_dirty_probe)
    command = list(args.worker_command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("watchdog worker command is empty", file=sys.stderr)
        return 2
    raw_output = Path(args.raw_output).resolve()
    summary_output = Path(args.summary_output).resolve()
    if development:
        development_root = (ROOT / "benchmarks" / "artifacts" / "task036" / "direct_d1b").resolve()
        if development_root not in raw_output.parents or development_root not in summary_output.parents:
            print(
                "development probe outputs must be under benchmarks/artifacts/task036/direct_d1b",
                file=sys.stderr,
            )
            return 2
    raw_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    source_at_start = inspect_tracked_source(ROOT)
    samples: list[dict[str, Any]] = []
    preflight_sample = sample_memory(-1, worker_alive=False)
    preflight, preflight_failures = build_preflight(preflight_sample)
    if source_at_start.source_commit_full_sha is None:
        preflight_failures.append("preflight HEAD is unreadable")
    elif not development and source_at_start.tracked_source_dirty:
        preflight_failures.append("preflight tracked source is not clean/identified")
    if development:
        cap_bytes = int(float(args.development_memory_cap_gib) * GIB)
        native_effective = preflight.get("effective_memory_bytes")
        native_warning = preflight.get("warning_threshold_bytes")
        native_termination = preflight.get("termination_threshold_bytes")
        if not all(
            isinstance(value, int) and value > 0
            for value in (native_effective, native_warning, native_termination)
        ):
            preflight_failures.append("development native memory thresholds are unreadable")
        else:
            effective = min(native_effective, cap_bytes)
            termination = min(native_termination, cap_bytes)
            warning = min(native_warning, int(0.9 * termination))
            preflight.update(
                {
                    "development_mode": True,
                    "native_effective_memory_bytes": native_effective,
                    "native_warning_threshold_bytes": native_warning,
                    "native_termination_threshold_bytes": native_termination,
                    "development_memory_cap_bytes": cap_bytes,
                    "effective_memory_bytes": effective,
                    "warning_threshold_bytes": warning,
                    "termination_threshold_bytes": termination,
                    "warning_scale": warning / effective,
                    "termination_scale": termination / effective,
                }
            )
        preflight["development_memory_cap_gib"] = float(
            args.development_memory_cap_gib
        )
    preflight["failures"] = list(preflight_failures)
    preflight["passed"] = not preflight_failures
    preflight_sample["sample_kind"] = "preflight"
    samples.append(preflight_sample)
    process: subprocess.Popen[Any] | None = None
    warning_triggered = False
    warning_first_observed_bytes: int | None = None
    termination_trigger: str | None = None
    termination_detail: str | None = None
    controlled_termination = False
    cleanup: dict[str, Any] | None = None
    started = time.monotonic()
    with raw_output.open("w", encoding="utf-8") as raw_stream:
        raw_stream.write(
            json.dumps(preflight_sample, ensure_ascii=False, allow_nan=False) + "\n"
        )
        raw_stream.flush()
        if preflight_failures:
            termination_trigger = "preflight_failed"
            termination_detail = "; ".join(preflight_failures)
        else:
            popen_options: dict[str, Any] = {
                "cwd": ROOT,
                **worker_process_group_popen_kwargs(),
            }
            try:
                process = subprocess.Popen(command, **popen_options)
            except OSError as exc:
                termination_trigger = "worker_launch_failed"
                termination_detail = f"{type(exc).__name__}: {exc}"
        try:
            while process is not None:
                return_code = process.poll()
                sample = sample_memory(
                    process.pid, worker_alive=return_code is None
                )
                sample["sample_kind"] = "worker"
                sample["elapsed_seconds"] = time.monotonic() - started
                decision: dict[str, Any] | None = None
                if return_code is None:
                    decision = watchdog_decision(
                        sample,
                        preflight=preflight,
                        elapsed_seconds=float(sample["elapsed_seconds"]),
                        wall_timeout_seconds=float(args.wall_timeout_seconds),
                    )
                    exit_race_code = _natural_exit_after_process_tree_sample(
                        process, decision
                    )
                    if exit_race_code is not None:
                        sample["process_tree_exit_race_observed"] = True
                        sample["worker_exit_code_observed_after_sample"] = int(
                            exit_race_code
                        )
                        return_code = int(exit_race_code)
                    elif (
                        decision.get("trigger") == "authority_unreadable"
                        and decision.get("detail") == "process_tree_status"
                        and development
                    ):
                        sample["process_tree_status_resample_attempted"] = True
                        resampled = _readable_process_tree_resample(
                            process, decision, sample
                        )
                        if resampled is not None:
                            resampled["elapsed_seconds"] = time.monotonic() - started
                            sample["process_tree_status_resample_succeeded"] = True
                            samples.append(sample)
                            raw_stream.write(
                                json.dumps(
                                    sample, ensure_ascii=False, allow_nan=False
                                )
                                + "\n"
                            )
                            raw_stream.flush()
                            sample = resampled
                            decision = watchdog_decision(
                                sample,
                                preflight=preflight,
                                elapsed_seconds=float(sample["elapsed_seconds"]),
                                wall_timeout_seconds=float(args.wall_timeout_seconds),
                            )
                        else:
                            sample["process_tree_status_resample_succeeded"] = False
                samples.append(sample)
                raw_stream.write(
                    json.dumps(sample, ensure_ascii=False, allow_nan=False) + "\n"
                )
                raw_stream.flush()
                if return_code is not None:
                    break
                assert decision is not None
                if decision["warning"] and not warning_triggered:
                    warning_triggered = True
                    warning_first_observed_bytes = int(sample["observed_memory_bytes"])
                    print(
                        "Case090 watchdog warning: observed memory reached "
                        f"{warning_first_observed_bytes} bytes (threshold "
                        f"{preflight['warning_threshold_bytes']}).",
                        file=sys.stderr,
                        flush=True,
                    )
                if decision["terminate"]:
                    termination_trigger = str(decision["trigger"])
                    termination_detail = str(decision["detail"])
                    controlled_termination = True
                    cleanup = terminate_process_tree(
                        process, grace_seconds=float(args.termination_grace_seconds)
                    )
                    break
                time.sleep(float(args.sample_interval))
        except KeyboardInterrupt:
            termination_trigger = "external_interrupt"
            termination_detail = "KeyboardInterrupt"
            if process is not None and process.poll() is None:
                controlled_termination = True
                cleanup = terminate_process_tree(
                    process, grace_seconds=float(args.termination_grace_seconds)
                )
        except BaseException as primary_error:
            if process is not None and process.poll() is None:
                try:
                    terminate_process_tree(
                        process,
                        grace_seconds=float(args.termination_grace_seconds),
                    )
                except Exception as cleanup_error:
                    primary_error.add_note(
                        "worker process-group cleanup also failed: "
                        f"{type(cleanup_error).__name__}: {cleanup_error}"
                    )
            raise
        final_sample = sample_memory(
            process.pid if process is not None else -1,
            worker_alive=False,
        )
        final_sample["sample_kind"] = "final"
        final_sample["elapsed_seconds"] = time.monotonic() - started
        samples.append(final_sample)
        raw_stream.write(
            json.dumps(final_sample, ensure_ascii=False, allow_nan=False) + "\n"
        )
        raw_stream.flush()
    source_at_end = inspect_tracked_source(ROOT)
    sampling, failures = summarize_samples(
        samples,
        raw_output=raw_output,
        summary_output=summary_output,
        preflight=preflight,
    )
    failures = [*preflight_failures, *failures]
    if termination_trigger is not None:
        failures.append(
            f"watchdog control trigger {termination_trigger}: {termination_detail}"
        )
    worker_return_code = process.returncode if process is not None else None
    if process is not None and worker_return_code != 0 and not controlled_termination:
        failures.append(f"worker exited with code {worker_return_code}")
    start_sha = source_at_start.source_commit_full_sha
    source_unchanged = (
        isinstance(start_sha, str)
        and start_sha == source_at_end.source_commit_full_sha
        and source_at_start.worktree_status_porcelain
        == source_at_end.worktree_status_porcelain
    )
    source_clean = (
        source_unchanged
        and not source_at_start.tracked_source_dirty
        and not source_at_end.tracked_source_dirty
    )
    if not source_unchanged:
        failures.append("tracked source was dirty or changed during watchdog run")
    status, memory_qualified, checks_satisfied = _run_status(
        failures, development=development
    )
    qualification = {
        "memory_summary_qualified": memory_qualified,
        "requires_zero_swap_every_sample": True,
        "requires_finite_container_limit": (
            preflight.get("resource_authority_mode")
            != "task034_wsl_effective_limit"
        ),
        "resource_authority_mode": preflight.get("resource_authority_mode"),
        "warning_scale": preflight.get("warning_scale"),
        "termination_scale": preflight.get("termination_scale"),
    }
    if development:
        qualification.update(
            {
                "memory_summary_qualified": False,
                "watchdog_checks_satisfied": checks_satisfied,
                "development_dirty_probe": True,
            }
        )
    payload = attach_evidence_sha256(
        {
            "schema_version": WATCHDOG_SCHEMA_VERSION,
            "record_type": "external_shard_memory_watchdog",
            "case_id": CASE_ID,
            "status": status,
            "identity": {
                "mpi_size": int(args.mpi_size),
                "source_commit_full_sha": start_sha,
                "source_commit_at_end_full_sha": source_at_end.source_commit_full_sha,
                "tracked_source_dirty_at_start": source_at_start.tracked_source_dirty,
                "tracked_source_dirty_at_end": source_at_end.tracked_source_dirty,
                "source_worktree_dirty_at_start": source_at_start.tracked_source_dirty,
                "source_worktree_dirty_at_end": source_at_end.tracked_source_dirty,
                "worktree_status_porcelain_at_start": list(
                    source_at_start.worktree_status_porcelain
                ),
                "worktree_status_porcelain_at_end": list(
                    source_at_end.worktree_status_porcelain
                ),
                "nonignored_untracked_paths_at_start": list(
                    source_at_start.nonignored_untracked_paths
                ),
                "nonignored_untracked_paths_at_end": list(
                    source_at_end.nonignored_untracked_paths
                ),
                "source_cleanliness_semantics": (
                    "tracked changes plus all nonignored untracked paths; ignored artifacts excluded"
                ),
                "source_clean_and_stable": source_clean,
                "source_unchanged_during_run": source_unchanged,
                "development_dirty_probe": development,
            },
            "worker": {
                "command": command,
                "launched": process is not None,
                "pid": process.pid if process is not None else None,
                "exit_code": worker_return_code,
            },
            "preflight": preflight,
            "sampling": {
                "sample_interval_seconds": float(args.sample_interval),
                **sampling,
            },
            "control": {
                "wall_timeout_seconds": float(args.wall_timeout_seconds),
                "termination_grace_seconds": float(args.termination_grace_seconds),
                "warning_triggered": warning_triggered,
                "warning_first_observed_bytes": warning_first_observed_bytes,
                "termination_trigger": termination_trigger,
                "termination_detail": termination_detail,
                "wall_timeout_triggered": termination_trigger == "wall_timeout",
                "controlled_termination": controlled_termination,
                "process_tree_cleanup": cleanup,
                "threshold_rule": (
                    "warning=min(native warning, 0.90*effective termination); "
                    "termination=min(native termination, development cap); "
                    f"cap_bytes={preflight.get('development_memory_cap_bytes')}"
                    if development
                    else "Task034 effective=min(user 220 GiB, 0.85*WSL total, "
                    "MemAvailable-24 GiB); warning=0.80*effective; "
                    "terminate=0.95*effective"
                    if preflight.get("resource_authority_mode")
                    == "task034_wsl_effective_limit"
                    else "effective=min(container limit, preflight host available, 14 GiB); "
                    "warning=effective*(11.5/14); terminate=effective*(13/14)"
                ),
            },
            "qualification": qualification,
            "failures": failures,
        }
    )
    write_json_object(summary_output, payload)
    validation = (
        []
        if development
        else validate_watchdog_summary(
            payload,
            expected_mpi_size=int(args.mpi_size),
            expected_source_sha=start_sha,
        )
    )
    print(
        f"wrote {summary_output} status={payload['status']} "
        f"samples={sampling['sample_count']} validation_errors={len(validation)}"
    )
    return 0 if not failures and not validation else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one Case090 MPI shard under an external process-tree/cgroup "
            "memory and swap watchdog."
        )
    )
    parser.add_argument("--mpi-size", type=int, required=True)
    parser.add_argument("--development-dirty-probe", action="store_true")
    parser.add_argument("--development-memory-cap-gib", type=float)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--sample-interval", type=float, default=1.0)
    parser.add_argument("--wall-timeout-seconds", type=float, default=86400.0)
    parser.add_argument("--termination-grace-seconds", type=float, default=5.0)
    parser.add_argument("worker_command", nargs=argparse.REMAINDER)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if int(args.mpi_size) <= 0:
        print("--mpi-size must be a positive integer", file=sys.stderr)
        return 2
    if not args.development_dirty_probe and int(args.mpi_size) not in MPI_SIZES:
        print(
            f"formal --mpi-size must be one of {MPI_SIZES}",
            file=sys.stderr,
        )
        return 2
    cap = args.development_memory_cap_gib
    if args.development_dirty_probe:
        if cap is None or not math.isfinite(float(cap)) or float(cap) <= 0.0:
            print(
                "--development-dirty-probe requires a finite positive "
                "--development-memory-cap-gib",
                file=sys.stderr,
            )
            return 2
        if int(float(cap) * GIB) <= 0:
            print("--development-memory-cap-gib is too small", file=sys.stderr)
            return 2
    elif cap is not None:
        print(
            "--development-memory-cap-gib requires --development-dirty-probe",
            file=sys.stderr,
        )
        return 2
    if not 0.05 <= float(args.sample_interval) <= 60.0:
        print("--sample-interval must be between 0.05 and 60 seconds", file=sys.stderr)
        return 2
    if float(args.wall_timeout_seconds) <= 0.0:
        print("--wall-timeout-seconds must be positive", file=sys.stderr)
        return 2
    if not 0.1 <= float(args.termination_grace_seconds) <= 60.0:
        print("--termination-grace-seconds must be between 0.1 and 60", file=sys.stderr)
        return 2
    return run_watchdog(args)


if __name__ == "__main__":
    raise SystemExit(main())
