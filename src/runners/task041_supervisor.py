"""Public MPI1 supervisor for the Task041 producer/consumer workflow.

The public process remains outer MPI1.  Legacy inputs use MPI1 children and
shortwave inputs use MPI8 children.  Numerical assembly remains in the
existing Task041 workers.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from itertools import pairwise
from pathlib import Path
from typing import Any

from benchmarks.task034_wsl_resources import resource_authority_sample
from benchmarks.watchdog_process_control import (
    terminate_process_tree,
    worker_process_group_popen_kwargs,
)
from src.io.execution_plan import TASK041_PUBLIC_SUPERVISOR_ADAPTER
from src.io.input_validation import (
    TASK041_BALH_2NM_MODEL_ID,
    TASK041_BALH_CANDIDATE_MODEL_IDS,
    TASK041_BALH_MODEL_IDS,
    TASK041_BALH_MPI_SIZE,
    TASK041_MODEL_ID,
    TASK041_RUN_ID,
    TASK041_SHORTWAVE_MODEL_IDS,
    TASK041_SHORTWAVE_MPI_SIZE,
    TASK041_SHORTWAVE_WORKFLOW_LIMITS,
    task041_balh_case,
    task041_balh_diagnostic_output_enabled,
    task041_balh_phase_limits_for_model,
    task041_balh_profile_errors,
    task041_balh_service_contract,
    task041_balh_timeout_scope,
    task041_balh_workflow_limits,
    task041_profile_errors,
    task041_shortwave_case,
    task041_shortwave_phase_limits,  # noqa: F401 - preserve the reviewed public helper
    task041_shortwave_phase_limits_for_model,
    task041_shortwave_profile_errors,
    task041_shortwave_timeout_scope,
    task041_shortwave_workflow_limits,
)
from src.io.resolved_config import resolved_config_sha256

TASK041_BRANCH = "codex/20260902-task41-mpi1-shortwave-hybrid-capacity"
TASK041_INPUT = "input/official/task041/5nm_p6h4_m480_mpi1.dat"
TASK041_MODE_COUNT = 480
TASK041_MPI_SIZE = 1
TASK041_WARNING_MEMORY_BYTES = 192 * 2**30
TASK041_HARD_MEMORY_BYTES = 256 * 2**30
TASK041_TIMEOUT_SECONDS = 172800
TASK041_SHORTWAVE_WARNING_MEMORY_BYTES = TASK041_SHORTWAVE_WORKFLOW_LIMITS[
    "warning_memory_bytes"
]
TASK041_SHORTWAVE_HARD_MEMORY_BYTES = TASK041_SHORTWAVE_WORKFLOW_LIMITS[
    "hard_memory_bytes"
]
TASK041_SHORTWAVE_TIMEOUT_SECONDS = TASK041_SHORTWAVE_WORKFLOW_LIMITS[
    "timeout_seconds"
]
TASK041_TERMINAL_SAMPLE_GRACE_SECONDS = 0.25
TASK041_TERMINAL_SAMPLE_TRANSITION_BUDGET_SECONDS = 30.0
TASK041_REQUIRED_THREADS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)
TASK041_CUMULATIVE_COMPUTE_WALL_SECONDS = 172800.0
TASK041_COMPUTE_WALL_LEDGER_NAME = "task041_compute_wall_ledger.json"

PopenFactory = Callable[..., Any]
SampleFactory = Callable[[int], dict[str, Any]]
TerminateFactory = Callable[[Any], dict[str, Any]]
Clock = Callable[[], float]


class Task041SupervisorError(RuntimeError):
    """A classified preflight, handoff, resource, or worker failure."""

    def __init__(self, message: str, *, classification: str, stage: str):
        super().__init__(message)
        self.classification = classification
        self.stage = stage


def _valid_sha(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and value == value.lower()
        and all(char in "0123456789abcdef" for char in value)
    )


def _runtime_limits_for_identity(identity: Mapping[str, Any]) -> dict[str, Any]:
    model_id = identity.get("model_id")
    if model_id == TASK041_MODEL_ID:
        if identity.get("requested_modes") != TASK041_MODE_COUNT or identity.get(
            "mpi_size"
        ) != TASK041_MPI_SIZE:
            raise Task041SupervisorError(
                "validated Task041 v1 identity has unexpected M/MPI",
                classification="task041_identity_failure",
                stage="runtime_limits",
            )
        return {
            "warning_memory_bytes": TASK041_WARNING_MEMORY_BYTES,
            "hard_memory_bytes": TASK041_HARD_MEMORY_BYTES,
            "swap_limit_bytes": 0,
            "timeout_seconds": TASK041_TIMEOUT_SECONDS,
        }
    if model_id in TASK041_SHORTWAVE_MODEL_IDS:
        case = task041_shortwave_case(str(model_id))
        if (
            case is None
            or identity.get("requested_modes") != case["mode_count"]
            or identity.get("mpi_size") != TASK041_SHORTWAVE_MPI_SIZE
        ):
            raise Task041SupervisorError(
                "validated Task041 shortwave identity has unexpected M/MPI",
                classification="task041_identity_failure",
                stage="runtime_limits",
            )
        return dict(task041_shortwave_workflow_limits(str(model_id)))
    if model_id in TASK041_BALH_MODEL_IDS:
        case = task041_balh_case(str(model_id))
        if (
            case is None
            or identity.get("requested_modes") != case["mode_count"]
            or identity.get("mpi_size") != TASK041_BALH_MPI_SIZE
        ):
            raise Task041SupervisorError(
                "validated Task041 side BAL_H identity has unexpected M/MPI",
                classification="task041_identity_failure",
                stage="runtime_limits",
            )
        return dict(task041_balh_workflow_limits(str(model_id)))
    raise Task041SupervisorError(
        f"runtime limits require a validated Task041 identity, got {model_id!r}",
        classification="task041_identity_failure",
        stage="runtime_limits",
    )


def _task041_consumer_time_stop_enforced(
    *,
    balh: bool,
    disable_time_stop: bool,
    phase_limits: Mapping[str, Any],
) -> bool:
    """Combine the legacy BAL_H override with the case phase policy."""

    if not balh:
        return True
    consumer_limits = phase_limits.get("consumer", {})
    return bool(
        not disable_time_stop
        and consumer_limits.get("time_stop_enforced", True)
    )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, sort_keys=True, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Task041SupervisorError(
            f"cannot read JSON {path}: {exc}",
            classification="task041_implementation_failure",
            stage="artifact_read",
        ) from exc
    if not isinstance(payload, Mapping):
        raise Task041SupervisorError(
            f"JSON artifact is not an object: {path}",
            classification="task041_implementation_failure",
            stage="artifact_read",
        )
    return dict(payload)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_task041_supervision_record(
    record_path: str | Path,
    *,
    profile_id: str,
    model_id: str,
    source_sha: str,
    scope: str,
    representative_rhs_probe: Mapping[str, Any] | None,
    side_setup_schedule: str | None = None,
    comparison_mode: str | None = None,
) -> dict[str, Any]:
    path = Path(record_path)
    if not path.is_absolute():
        raise Task041SupervisorError(
            "Task041 supervision record must be an absolute path",
            classification="task041_identity_failure",
            stage="supervision_record",
        )
    path = path.resolve()
    payload = _read_json(path)
    invocation_id = os.environ.get("INVOCATION_ID")
    parent_pid = os.getppid()
    if not isinstance(invocation_id, str) or not invocation_id:
        raise Task041SupervisorError(
            "Task041 supervision requires a non-empty inherited INVOCATION_ID",
            classification="task041_identity_failure",
            stage="supervision_record",
        )
    expected = {
        "profile_id": profile_id,
        "model_id": model_id,
        "source_sha": source_sha,
        "scope": scope,
        "ledger_owner": "service_finalizer",
        "parent_pid": parent_pid,
        "invocation_id": invocation_id,
    }
    if side_setup_schedule is not None:
        expected["side_setup_schedule"] = side_setup_schedule
    if comparison_mode is not None:
        expected["comparison_mode"] = comparison_mode
    if isinstance(payload.get("parent_pid"), bool) or not isinstance(
        payload.get("parent_pid"), int
    ):
        raise Task041SupervisorError(
            "Task041 supervision record parent_pid must be an integer",
            classification="task041_identity_failure",
            stage="supervision_record",
        )
    for field, value in expected.items():
        if field not in payload or payload[field] != value:
            raise Task041SupervisorError(
                f"Task041 supervision record {field} does not match the current public process",
                classification="task041_identity_failure",
                stage="supervision_record",
            )
    if (
        "representative_rhs_probe" not in payload
        or payload["representative_rhs_probe"] != representative_rhs_probe
    ):
        raise Task041SupervisorError(
            "Task041 supervision record representative_rhs_probe does not match the current public process",
            classification="task041_identity_failure",
            stage="supervision_record",
        )
    ledger_value = payload.get("ledger_path")
    if not isinstance(ledger_value, str) or not Path(ledger_value).is_absolute():
        raise Task041SupervisorError(
            "Task041 supervision record ledger_path must be absolute",
            classification="task041_identity_failure",
            stage="supervision_record",
        )
    return {
        "path": str(path),
        "sha256": _sha256_file(path),
        "profile_id": profile_id,
        "model_id": model_id,
        "source_sha": source_sha,
        "scope": scope,
        "representative_rhs_probe": representative_rhs_probe,
        "side_setup_schedule": side_setup_schedule,
        "comparison_mode": comparison_mode,
        "parent_pid": parent_pid,
        "invocation_id": expected["invocation_id"],
        "ledger_path": str(Path(ledger_value).resolve()),
        "outer_owner": "service_finalizer",
        "ledger_owner": "service_finalizer",
    }


def _copy_file_bounded(source: Path, destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with source.open("rb") as source_stream, temporary.open("wb") as target:
            while chunk := source_stream.read(1024 * 1024):
                target.write(chunk)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


def _numeric(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _resource_authority_kind(authority: Mapping[str, Any]) -> str | None:
    process_tree = authority.get("process_tree")
    if (
        isinstance(process_tree, Mapping)
        and process_tree.get("all_status_readable") is True
    ):
        return "process_tree"
    job_cgroup = authority.get("job_cgroup")
    if not isinstance(job_cgroup, Mapping):
        return None
    if (
        job_cgroup.get("dedicated_job_cgroup") is True
        and job_cgroup.get("readable") is True
        and _numeric(job_cgroup.get("memory_current_bytes")) is not None
        and _numeric(job_cgroup.get("swap_current_bytes")) is not None
    ):
        return "dedicated_cgroup_fallback"
    return None


def _sample_record(
    authority: Mapping[str, Any],
    phase: str,
    elapsed: float,
    *,
    authority_kind: str | None = None,
) -> dict[str, Any]:
    process_tree = authority.get("process_tree")
    if not isinstance(process_tree, Mapping):
        process_tree = {}
    smaps = process_tree.get("smaps")
    if not isinstance(smaps, Mapping):
        smaps = {}
    job_cgroup = authority.get("job_cgroup")
    if not isinstance(job_cgroup, Mapping):
        job_cgroup = {}
    host_memory = authority.get("host_memory")
    if not isinstance(host_memory, Mapping):
        host_memory = {}
    global_swap = authority.get("global_swap")
    if not isinstance(global_swap, Mapping):
        global_swap = {}
    global_vmstat = authority.get("wsl_vm_global_swap_diagnostic")
    if not isinstance(global_vmstat, Mapping):
        global_vmstat = {}
    authority_kind = authority_kind or _resource_authority_kind(authority)
    memory = _numeric(authority.get("memory_authority_bytes"))
    cgroup_memory = _numeric(job_cgroup.get("memory_current_bytes"))
    rss = _numeric(process_tree.get("rss_bytes"))
    process_swap = _numeric(process_tree.get("swap_bytes"))
    dedicated_swap = _numeric(job_cgroup.get("swap_current_bytes"))
    host_memavailable = _numeric(host_memory.get("mem_available_bytes"))
    host_memtotal = _numeric(host_memory.get("mem_total_bytes"))
    global_swap_used = _numeric(global_swap.get("used_bytes"))
    global_pswpin = _numeric(global_vmstat.get("pswpin_pages"))
    global_pswpout = _numeric(global_vmstat.get("pswpout_pages"))
    pid_rss = {
        str(pid): int(value)
        for pid, value in (
            process_tree.get("rss_by_pid_bytes", {})
            if isinstance(process_tree.get("rss_by_pid_bytes"), Mapping)
            else {}
        ).items()
        if _numeric(value) is not None
    }
    pid_swap = {
        str(pid): int(value)
        for pid, value in (
            process_tree.get("swap_by_pid_bytes", {})
            if isinstance(process_tree.get("swap_by_pid_bytes"), Mapping)
            else {}
        ).items()
        if _numeric(value) is not None
    }
    common = {
        "sample_elapsed_seconds": float(elapsed),
        "host_memavailable_bytes": host_memavailable,
        "host_memtotal_bytes": host_memtotal,
        "cgroup_memory_current_bytes": cgroup_memory,
        "cgroup_memory_peak_bytes": _numeric(job_cgroup.get("memory_peak_bytes")),
        "cgroup_memory_limit_bytes": _numeric(job_cgroup.get("memory_limit_bytes")),
        "cgroup_memory_limit_state": job_cgroup.get("memory_limit_state"),
        "cgroup_memory_headroom_bytes": _numeric(
            job_cgroup.get("memory_headroom_bytes")
        ),
        "cgroup_ancestor_hard_limit_bytes": _numeric(
            job_cgroup.get("ancestor_hard_limit_bytes")
        ),
        "cgroup_ancestor_hard_limit_state": job_cgroup.get(
            "ancestor_hard_limit_state"
        ),
        "cgroup_ancestor_memory_headroom_bytes": _numeric(
            job_cgroup.get("ancestor_memory_headroom_bytes")
        ),
        "cgroup_ancestor_memory": job_cgroup.get("ancestor_memory", []),
        "cgroup_ancestor_limit_states": sorted(
            {
                row.get("memory_limit_state")
                for row in job_cgroup.get("ancestor_memory", [])
                if isinstance(row, Mapping)
                and row.get("memory_limit_state") is not None
            }
        ),
        "cgroup_scope_semantics": job_cgroup.get("scope_semantics"),
        "cgroup_dedicated_job_cgroup": job_cgroup.get("dedicated_job_cgroup"),
        "global_swap_used_bytes": global_swap_used,
        "global_swap_readable": global_swap.get("readable"),
        "global_pswpin_pages": global_pswpin,
        "global_pswpout_pages": global_pswpout,
        "process_tree_pids": list(process_tree.get("pids", ())),
        "process_tree_rss_by_pid_bytes": pid_rss,
        "process_tree_swap_by_pid_bytes": pid_swap,
    }
    if authority_kind == "dedicated_cgroup_fallback":
        if cgroup_memory is None or dedicated_swap is None:
            raise Task041SupervisorError(
                f"{phase} dedicated cgroup fallback is incomplete",
                classification="task041_implementation_failure",
                stage=f"{phase}_resource_sample",
            )
        memory = max(memory or 0, cgroup_memory)
        return {
            **common,
            "phase": phase,
            "elapsed_seconds": float(elapsed),
            "authority_kind": authority_kind,
            "memory_authority_bytes": memory,
            "memory_authority_source": (
                "max(existing memory_authority_bytes, dedicated cgroup memory.current)"
            ),
            "job_no_swap": dedicated_swap == 0,
            "process_tree_rss_bytes": None,
            "process_tree_swap_bytes": None,
            "dedicated_cgroup_memory_bytes": cgroup_memory,
            "dedicated_cgroup_swap_bytes": dedicated_swap,
            "swap_bytes": dedicated_swap,
            "swap_authority_source": "dedicated cgroup swap.current",
            "pss_bytes": None,
            "uss_bytes": None,
            "all_status_readable": False,
        }
    if authority_kind != "process_tree":
        raise Task041SupervisorError(
            f"{phase} resource sample has no complete authority",
            classification="task041_implementation_failure",
            stage=f"{phase}_resource_sample",
        )
    if job_cgroup.get("dedicated_job_cgroup") is not True or dedicated_swap is None:
        dedicated_swap = 0
    pss = _numeric(smaps.get("pss_bytes"))
    uss = _numeric(smaps.get("uss_bytes"))
    if memory is None or rss is None or process_swap is None:
        raise Task041SupervisorError(
            f"{phase} resource sample lacks memory_authority/process-tree fields",
            classification="task041_implementation_failure",
            stage=f"{phase}_resource_sample",
        )
    swap = max(process_swap, dedicated_swap)
    return {
        **common,
        "phase": phase,
        "elapsed_seconds": float(elapsed),
        "authority_kind": authority_kind,
        "memory_authority_bytes": memory,
        "memory_authority_source": "existing memory_authority_bytes",
        "job_no_swap": authority.get("job_no_swap"),
        "process_tree_rss_bytes": rss,
        "process_tree_swap_bytes": process_swap,
        "dedicated_cgroup_memory_bytes": cgroup_memory,
        "dedicated_cgroup_swap_bytes": dedicated_swap,
        "swap_bytes": swap,
        "swap_authority_source": "max(process-tree VmSwap, dedicated cgroup swap.current)",
        "pss_bytes": pss,
        "uss_bytes": uss,
        "all_status_readable": process_tree.get("all_status_readable"),
    }


def _cgroup_ancestor_headroom_unmeasured(
    record: Mapping[str, Any],
) -> bool:
    """Return whether a visible finite ancestor limit lacks current usage."""

    states = record.get("cgroup_ancestor_limit_states")
    visible_states = set(states) if isinstance(states, list) else set()
    aggregate_state = record.get("cgroup_ancestor_hard_limit_state")
    current_limit_state = record.get("cgroup_memory_limit_state")
    current_limit_visible = bool(
        isinstance(record.get("cgroup_memory_limit_bytes"), int)
        or current_limit_state == "finite"
    )
    if current_limit_visible and (
        not isinstance(record.get("cgroup_memory_current_bytes"), int)
        or not isinstance(record.get("cgroup_memory_headroom_bytes"), int)
    ):
        return True
    finite_visible = bool(
        isinstance(record.get("cgroup_ancestor_hard_limit_bytes"), int)
        or "finite" in visible_states
        or aggregate_state in {"finite", "partially_unreadable"}
    )
    if not finite_visible:
        return False
    if aggregate_state == "partially_unreadable":
        return True
    rows = record.get("cgroup_ancestor_memory")
    finite_rows = (
        [
            row
            for row in rows
            if isinstance(row, Mapping)
            and row.get("memory_limit_state") == "finite"
        ]
        if isinstance(rows, list)
        else []
    )
    if not finite_rows:
        return not isinstance(
            record.get("cgroup_ancestor_memory_headroom_bytes"), int
        )
    return any(
        not isinstance(row.get("memory_current_bytes"), int)
        or not isinstance(row.get("memory_headroom_bytes"), int)
        for row in finite_rows
    )


def _process_group_gone(pid: int) -> bool:
    if os.name != "posix":
        return True
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def _terminate_and_verify(
    process: Any,
    terminate_factory: TerminateFactory,
    process_group_gone: Callable[[int], bool],
) -> dict[str, Any]:
    termination = terminate_factory(process)
    process.wait()
    if not process_group_gone(process.pid):
        raise Task041SupervisorError(
            f"process group for pid {process.pid} survived termination",
            classification="task041_lifecycle_failure",
            stage="process_group_cleanup",
        )
    return termination


def _run_phase(
    phase: str,
    argv: list[str],
    phase_root: Path,
    *,
    log_root: Path,
    environment: Mapping[str, str],
    repository_root: Path,
    workflow_started: float,
    popen_factory: PopenFactory,
    sample_factory: SampleFactory,
    terminate_factory: TerminateFactory,
    monotonic: Clock,
    sleep: Callable[[float], None],
    poll_interval: float,
    memory_stages_path: Path,
    marker_path: Path,
    process_group_gone: Callable[[int], bool] = _process_group_gone,
    warning_memory_bytes: int = TASK041_WARNING_MEMORY_BYTES,
    hard_memory_bytes: int = TASK041_HARD_MEMORY_BYTES,
    process_tree_rss_warning_bytes: int | None = None,
    process_tree_rss_cap_bytes: int | None = None,
    timeout_seconds: float | None = TASK041_TIMEOUT_SECONDS,
    phase_elapsed_timeout: bool = False,
    sample_root_pid: int | None = None,
    min_memavailable_bytes: int | None = None,
    min_cgroup_ancestor_headroom_bytes: int | None = None,
    cumulative_compute_used_seconds: float = 0.0,
    cumulative_compute_limit_seconds: float | None = None,
    global_swap_baseline: Mapping[str, Any] | None = None,
    partial_phase_results: dict[str, Any] | None = None,
    enforce_time_stops: bool = True,
) -> dict[str, Any]:
    if phase_root.exists():
        raise Task041SupervisorError(
            f"{phase} run directory must be fresh: {phase_root}",
            classification="task041_implementation_failure",
            stage=f"{phase}_root_preflight",
        )
    phase_started = monotonic()
    sample_count = 0
    smaps_complete_sample_count = 0
    pss_uss_missing_sample_count = 0
    last_sample: dict[str, Any] | None = None
    peak_values: dict[str, int] = {}
    minimum_values: dict[str, int] = {}
    pid_peaks: dict[str, int] = {}
    global_peak_used: int | None = None
    global_max_used_delta: int | None = None
    global_max_pswpin_delta: int | None = None
    global_max_pswpout_delta: int | None = None
    sample_time_previous: float | None = None
    sample_gap_count = 0
    sample_gap_min: float | None = None
    sample_gap_max: float | None = None
    sample_gap_total = 0.0
    cgroup_ancestor_limit_states: set[str] = set()
    before_rss: int | None = None
    warning_reached = False
    process_tree_rss_warning_reached = False
    termination_reason: str | None = None
    termination: dict[str, Any] | None = None
    process: Any | None = None
    cleanup_attempted = False
    group_gone = False
    sampling_root_pid = None if sample_root_pid is None else int(sample_root_pid)
    baseline = None if global_swap_baseline is None else dict(global_swap_baseline)
    worker_process_group_pid: int | None = None
    phase_end_sample: dict[str, Any] | None = None

    def _authority_complete_for_profile(
        authority: Mapping[str, Any] | None,
        authority_kind: str | None,
    ) -> bool:
        if authority_kind is None:
            return False
        if process_tree_rss_cap_bytes is None:
            return True
        process_tree = authority.get("process_tree") if authority else None
        return bool(
            authority_kind == "process_tree"
            and isinstance(process_tree, Mapping)
            and isinstance(process_tree.get("rss_bytes"), int)
        )

    def _phase_limit_record() -> dict[str, Any]:
        limits: dict[str, Any] = {
            "warning_memory_bytes": warning_memory_bytes,
            "hard_memory_bytes": hard_memory_bytes,
            "swap_limit_bytes": 0,
            "timeout_seconds": timeout_seconds,
            "min_memavailable_bytes": min_memavailable_bytes,
            "min_cgroup_ancestor_headroom_bytes": (
                min_cgroup_ancestor_headroom_bytes
            ),
            "cumulative_compute_limit_seconds": cumulative_compute_limit_seconds,
        }
        if process_tree_rss_warning_bytes is not None:
            limits["process_tree_rss_warning_bytes"] = (
                process_tree_rss_warning_bytes
            )
        if process_tree_rss_cap_bytes is not None:
            limits["process_tree_rss_cap_bytes"] = process_tree_rss_cap_bytes
        return limits

    def _record_sample(record: dict[str, Any], *, running: bool = False) -> None:
        nonlocal before_rss
        nonlocal last_sample, sample_count
        nonlocal smaps_complete_sample_count, pss_uss_missing_sample_count
        nonlocal sample_time_previous, sample_gap_count
        nonlocal sample_gap_min, sample_gap_max, sample_gap_total
        nonlocal global_peak_used, global_max_used_delta
        nonlocal global_max_pswpin_delta, global_max_pswpout_delta

        sample_count += 1
        last_sample = record
        for name in (
            "memory_authority_bytes",
            "process_tree_rss_bytes",
            "pss_bytes",
            "uss_bytes",
            "process_tree_swap_bytes",
            "dedicated_cgroup_swap_bytes",
            "swap_bytes",
            "cgroup_memory_peak_bytes",
        ):
            value = record.get(name)
            if isinstance(value, int):
                peak_values[name] = max(peak_values.get(name, value), value)
        for name in (
            "host_memavailable_bytes",
            "cgroup_memory_headroom_bytes",
            "cgroup_ancestor_memory_headroom_bytes",
        ):
            value = record.get(name)
            if isinstance(value, int):
                minimum_values[name] = min(minimum_values.get(name, value), value)
        if running:
            value = record.get("process_tree_rss_bytes")
            if (
                record.get("authority_kind") == "process_tree"
                and isinstance(value, int)
                and value > 0
            ):
                before_rss = value
        values = record.get("process_tree_rss_by_pid_bytes")
        if isinstance(values, Mapping):
            for pid, value in values.items():
                if isinstance(value, int):
                    pid_peaks[str(pid)] = max(pid_peaks.get(str(pid), 0), value)
        value = record.get("global_swap_used_bytes")
        if isinstance(value, int):
            global_peak_used = (
                value if global_peak_used is None else max(global_peak_used, value)
            )
        for name, current in (
            ("global_swap_used_bytes_delta", global_max_used_delta),
            ("global_pswpin_pages_delta", global_max_pswpin_delta),
            ("global_pswpout_pages_delta", global_max_pswpout_delta),
        ):
            value = record.get(name)
            if isinstance(value, int):
                current = value if current is None else max(current, value)
            if name == "global_swap_used_bytes_delta":
                global_max_used_delta = current
            elif name == "global_pswpin_pages_delta":
                global_max_pswpin_delta = current
            else:
                global_max_pswpout_delta = current
        if isinstance(record.get("pss_bytes"), int) and isinstance(
            record.get("uss_bytes"), int
        ):
            smaps_complete_sample_count += 1
        if record.get("pss_bytes") is None or record.get("uss_bytes") is None:
            pss_uss_missing_sample_count += 1
        state = record.get("cgroup_ancestor_hard_limit_state")
        if isinstance(state, str):
            cgroup_ancestor_limit_states.add(state)
        sample_time = record.get("sample_elapsed_seconds")
        if isinstance(sample_time, (int, float)) and math.isfinite(float(sample_time)):
            sample_time = float(sample_time)
            if sample_time_previous is not None and sample_time >= sample_time_previous:
                gap = sample_time - sample_time_previous
                sample_gap_count += 1
                sample_gap_total += gap
                sample_gap_min = gap if sample_gap_min is None else min(sample_gap_min, gap)
                sample_gap_max = gap if sample_gap_max is None else max(sample_gap_max, gap)
            sample_time_previous = sample_time

    def _annotate_sample(
        record: dict[str, Any], *, sample_role: str, worker_pid: int
    ) -> dict[str, Any]:
        nonlocal baseline
        record["sample_role"] = sample_role
        record["sample_root_pid"] = (
            worker_pid if sampling_root_pid is None else sampling_root_pid
        )
        record["worker_process_group_pid"] = worker_pid
        record["worker_process_group_gone"] = bool(
            sample_role == "phase_end_public_root"
        )
        if baseline is None:
            baseline = {
                name: record.get(name)
                for name in (
                    "global_swap_used_bytes",
                    "global_pswpin_pages",
                    "global_pswpout_pages",
                )
                if isinstance(record.get(name), int)
            }
        for name in (
            "global_swap_used_bytes",
            "global_pswpin_pages",
            "global_pswpout_pages",
        ):
            value = record.get(name)
            initial = baseline.get(name) if baseline is not None else None
            record[f"{name}_delta"] = (
                None
                if not isinstance(value, int) or not isinstance(initial, int)
                else max(0, value - initial)
            )
        return record

    def _resource_termination_reason(
        record: Mapping[str, Any], now: float
    ) -> str | None:
        memory = record.get("memory_authority_bytes")
        process_tree_rss = record.get("process_tree_rss_bytes")
        if not isinstance(memory, int) or memory >= hard_memory_bytes:
            return "absolute_memory_limit"
        if process_tree_rss_cap_bytes is not None and not isinstance(
            process_tree_rss, int
        ):
            return "process_tree_rss_unmeasured"
        if (
            process_tree_rss_cap_bytes is not None
            and process_tree_rss >= process_tree_rss_cap_bytes
        ):
            return "process_tree_rss_limit"
        if (
            min_memavailable_bytes is not None
            and not isinstance(record.get("host_memavailable_bytes"), int)
        ):
            return "memavailable_unmeasured"
        if (
            min_cgroup_ancestor_headroom_bytes is not None
            and _cgroup_ancestor_headroom_unmeasured(record)
        ):
            return "cgroup_headroom_unmeasured"
        if record["swap_bytes"] > 0 or record["job_no_swap"] is not True:
            return "swap_detected"
        if (
            min_memavailable_bytes is not None
            and isinstance(record.get("host_memavailable_bytes"), int)
            and record["host_memavailable_bytes"] < min_memavailable_bytes
        ):
            return "memavailable_floor"
        if (
            min_cgroup_ancestor_headroom_bytes is not None
            and isinstance(
                record.get("cgroup_ancestor_memory_headroom_bytes"), int
            )
            and record["cgroup_ancestor_memory_headroom_bytes"]
            < min_cgroup_ancestor_headroom_bytes
        ):
            return "cgroup_headroom_floor"
        if (
            enforce_time_stops
            and cumulative_compute_limit_seconds is not None
            and cumulative_compute_used_seconds + (now - phase_started)
            >= cumulative_compute_limit_seconds
        ):
            return "cumulative_wall_timeout"
        if enforce_time_stops and timeout_seconds is not None and (
            (now - phase_started)
            if phase_elapsed_timeout
            else (now - workflow_started)
        ) >= timeout_seconds:
            return "wall_timeout"
        return None

    stdout_path = log_root / f"{phase}_stdout.txt"
    try:
        _append_jsonl(
            marker_path,
            {
                "stage": f"{phase}_started",
                "wall_seconds": phase_started - workflow_started,
                "workflow_started_monotonic_seconds": workflow_started,
                "clock": "CLOCK_MONOTONIC",
            },
        )
        with stdout_path.open("w", encoding="utf-8") as stdout:
            process = popen_factory(
                list(argv),
                shell=False,
                cwd=repository_root,
                env=dict(environment),
                stdout=stdout,
                stderr=subprocess.STDOUT,
                text=True,
                **worker_process_group_popen_kwargs(),
            )
            worker_process_group_pid = int(process.pid)
            while True:
                returncode = process.poll()
                now = monotonic()
                if returncode is not None:
                    break
                sample_pid = (
                    process.pid if sampling_root_pid is None else sampling_root_pid
                )
                authority = sample_factory(sample_pid)
                authority_kind = (
                    _resource_authority_kind(authority)
                    if isinstance(authority, Mapping)
                    else None
                )
                if not _authority_complete_for_profile(authority, authority_kind):
                    if sample_count:
                        transition_deadline = (
                            now + TASK041_TERMINAL_SAMPLE_TRANSITION_BUDGET_SECONDS
                        )
                        while not _authority_complete_for_profile(
                            authority, authority_kind
                        ):
                            returncode = process.poll()
                            if returncode is not None:
                                break
                            now = monotonic()
                            remaining = transition_deadline - now
                            if remaining <= 0.0:
                                raise Task041SupervisorError(
                                    f"{phase} resource authorities are incomplete",
                                    classification="task041_resource_sample_failure",
                                    stage=f"{phase}_resource_sample",
                                )
                            sleep(min(TASK041_TERMINAL_SAMPLE_GRACE_SECONDS, remaining))
                            returncode = process.poll()
                            if returncode is not None:
                                break
                            now = monotonic()
                            if now >= transition_deadline:
                                raise Task041SupervisorError(
                                    f"{phase} resource authorities are incomplete",
                                    classification="task041_resource_sample_failure",
                                    stage=f"{phase}_resource_sample",
                                )
                            authority = sample_factory(sample_pid)
                            authority_kind = (
                                _resource_authority_kind(authority)
                                if isinstance(authority, Mapping)
                                else None
                            )
                        if returncode is not None:
                            break
                    else:
                        returncode = process.poll()
                        if returncode is None:
                            sleep(TASK041_TERMINAL_SAMPLE_GRACE_SECONDS)
                            returncode = process.poll()
                            if returncode is None:
                                now = monotonic()
                                authority = sample_factory(sample_pid)
                                authority_kind = (
                                    _resource_authority_kind(authority)
                                    if isinstance(authority, Mapping)
                                    else None
                                )
                                if not _authority_complete_for_profile(
                                    authority, authority_kind
                                ):
                                    returncode = process.poll()
                        if returncode is not None:
                            break
                        if not _authority_complete_for_profile(
                            authority, authority_kind
                        ):
                            raise Task041SupervisorError(
                                f"{phase} resource authorities are incomplete",
                                classification="task041_resource_sample_failure",
                                stage=f"{phase}_resource_sample",
                            )
                record = _sample_record(
                    authority,
                    phase,
                    now - workflow_started,
                    authority_kind=authority_kind,
                )
                record = _annotate_sample(
                    record,
                    sample_role="phase_running",
                    worker_pid=process.pid,
                )
                _record_sample(record, running=True)
                _append_jsonl(memory_stages_path, record)
                memory = record["memory_authority_bytes"]
                process_tree_rss = record.get("process_tree_rss_bytes")
                if isinstance(memory, int):
                    warning_reached = (
                        warning_reached or memory >= warning_memory_bytes
                    )
                if process_tree_rss_warning_bytes is not None and isinstance(
                    process_tree_rss, int
                ):
                    process_tree_rss_warning_reached = (
                        process_tree_rss_warning_reached
                        or process_tree_rss >= process_tree_rss_warning_bytes
                    )
                termination_reason = _resource_termination_reason(record, now)
                if termination_reason is not None:
                    cleanup_attempted = True
                    termination = _terminate_and_verify(
                        process, terminate_factory, process_group_gone
                    )
                    break
                sleep(poll_interval)
            returncode = process.wait()

        group_gone = bool(process_group_gone(process.pid))
        if not group_gone:
            cleanup_attempted = True
            termination = _terminate_and_verify(
                process, terminate_factory, process_group_gone
            )
            group_gone = True
            raise Task041SupervisorError(
                f"{phase} process group lingered after normal exit",
                classification="task041_lifecycle_failure",
                stage=f"{phase}_process_group_linger",
            )

        if sampling_root_pid is not None:
            post_authority = sample_factory(sampling_root_pid)
            post_kind = (
                _resource_authority_kind(post_authority)
                if isinstance(post_authority, Mapping)
                else None
            )
            if post_kind is None:
                if (
                    process_tree_rss_cap_bytes is not None
                    and termination_reason is None
                ):
                    termination_reason = "process_tree_rss_unmeasured"
                raise Task041SupervisorError(
                    f"{phase} public launcher root could not be sampled after worker exit",
                    classification="task041_resource_sample_failure",
                    stage=f"{phase}_resource_sample",
                )
            if process_tree_rss_cap_bytes is not None and not _authority_complete_for_profile(
                post_authority, post_kind
            ):
                if termination_reason is None:
                    termination_reason = "process_tree_rss_unmeasured"
                raise Task041SupervisorError(
                    f"{phase} public launcher root resource authority is incomplete",
                    classification="task041_resource_sample_failure",
                    stage=f"{phase}_resource_sample",
                )
            post_now = monotonic()
            phase_end_sample = _annotate_sample(
                _sample_record(
                    post_authority,
                    phase,
                    post_now - workflow_started,
                    authority_kind=post_kind,
                ),
                sample_role="phase_end_public_root",
                worker_pid=process.pid,
            )
            _record_sample(phase_end_sample)
            _append_jsonl(memory_stages_path, phase_end_sample)
            post_reason = (
                _resource_termination_reason(phase_end_sample, post_now)
                if process_tree_rss_cap_bytes is not None
                else None
            )
            if post_reason is not None:
                if termination_reason is None:
                    termination_reason = post_reason
                raise Task041SupervisorError(
                    f"{phase} terminal resource gate failed: {post_reason}",
                    classification="task041_resource_sample_failure",
                    stage=f"{phase}_resource_sample",
                )

        after_rss = (
            phase_end_sample.get("process_tree_rss_bytes")
            if phase_end_sample is not None
            else 0
        )
        rss_drop = {
            "before_process_tree_rss_bytes": before_rss,
            "after_process_tree_rss_bytes": after_rss,
            "process_group_gone": group_gone,
            "measurement_scope": (
                "public_launcher_root_after_worker_group_exit"
                if phase_end_sample is not None
                else "legacy_worker_group_process_tree"
            ),
            "pass": bool(isinstance(before_rss, int) and after_rss < before_rss),
        }
        finished_at = monotonic()
        phase_wall_seconds = finished_at - phase_started
        workflow_wall_seconds = finished_at - workflow_started
        phase_record_limits = _phase_limit_record()
        _append_jsonl(
            marker_path,
            {
                "stage": f"{phase}_finished",
                "wall_seconds": workflow_wall_seconds,
                "phase_wall_seconds": phase_wall_seconds,
                "timeout_scope": "phase" if phase_elapsed_timeout else "workflow",
                "time_stop_enforced": bool(enforce_time_stops),
                "limits": phase_record_limits,
                "returncode": returncode,
                "termination_reason": termination_reason,
                "rss_drop": rss_drop,
            },
        )
    except Exception:
        try:
            if process is not None and not cleanup_attempted:
                try:
                    gone = bool(process_group_gone(process.pid))
                except Exception:  # noqa: BLE001 - failed liveness probe requires cleanup
                    gone = False
                if not gone:
                    cleanup_attempted = True
                    termination = _terminate_and_verify(
                        process, terminate_factory, process_group_gone
                    )
        finally:
            if partial_phase_results is not None and process is not None:
                try:
                    final_group_gone = bool(process_group_gone(process.pid))
                except Exception:  # noqa: BLE001 - final liveness is diagnostic
                    final_group_gone = False
                finished_at = monotonic()
                phase_wall_seconds = max(0.0, finished_at - phase_started)
                partial_phase_results[phase] = {
                    "phase": phase,
                    "argv": list(argv),
                    "stdout": str(stdout_path),
                    "returncode": process.poll(),
                    "wall_seconds": phase_wall_seconds,
                    "phase_wall_seconds": phase_wall_seconds,
                    "workflow_wall_seconds": max(
                        0.0, finished_at - workflow_started
                    ),
                    "limits": _phase_limit_record(),
                    "time_stop_enforced": bool(enforce_time_stops),
                    "sample_count": sample_count,
                    "warning_reached": warning_reached,
                    "process_tree_rss_warning_reached": (
                        process_tree_rss_warning_reached
                    ),
                    "last_sample": last_sample,
                    "termination_reason": termination_reason or "phase_exception",
                    "termination": termination,
                    "cleanup_attempted": cleanup_attempted,
                    "process_group_gone": final_group_gone,
                    "worker_process_group_pid": worker_process_group_pid,
                    "sample_root_pid": (
                        sampling_root_pid or worker_process_group_pid
                    ),
                    "sample_root_scope": (
                        "public_launcher_and_all_descendants"
                        if sampling_root_pid is not None
                        else "worker_process_group_tree"
                    ),
                    "resource_source": "current_invocation_partial",
                    "partial": True,
                }
        raise

    def _peak(name: str) -> int | None:
        return peak_values.get(name)

    def _minimum(name: str) -> int | None:
        return minimum_values.get(name)

    sample_gap_mean = (
        sample_gap_total / sample_gap_count if sample_gap_count else None
    )

    return {
        "phase": phase,
        "argv": list(argv),
        "stdout": str(stdout_path),
        "returncode": returncode,
        "wall_seconds": phase_wall_seconds,
        "phase_wall_seconds": phase_wall_seconds,
        "workflow_wall_seconds": workflow_wall_seconds,
        "timeout_scope": "phase" if phase_elapsed_timeout else "workflow",
        "time_stop_enforced": bool(enforce_time_stops),
        "limits": phase_record_limits,
        "sample_count": sample_count,
        "smaps_complete_sample_count": smaps_complete_sample_count,
        "resource_sampling_semantics": (
            "RSS/VmSwap and dedicated cgroup memory/swap are sampled every poll; "
            "PSS/USS are sparse diagnostics."
        ),
        "sampling": {
            "configured_poll_interval_seconds": float(poll_interval),
            "rss_swap_interval_seconds": float(poll_interval),
            "sample_timestamp_basis": "monotonic workflow elapsed seconds",
            "sample_timestamp_gap_seconds": {
                "count": sample_gap_count,
                "min": sample_gap_min,
                "max": sample_gap_max,
                "mean": sample_gap_mean,
            },
            "pss_uss_interval_seconds": getattr(
                sample_factory, "smaps_interval_seconds", None
            ),
            "pss_uss_semantics": "sparse; missing samples remain not_measured",
            "pss_uss_missing_sample_count": pss_uss_missing_sample_count,
        },
        "warning_reached": warning_reached,
        "process_tree_rss_warning_reached": process_tree_rss_warning_reached,
        "termination_reason": termination_reason,
        "termination": termination,
        "process_group_gone": group_gone,
        "rss_drop": rss_drop,
        "peak_memory_authority_bytes": _peak("memory_authority_bytes"),
        "peak_process_tree_rss_bytes": _peak("process_tree_rss_bytes"),
        "peak_pss_bytes": _peak("pss_bytes"),
        "peak_uss_bytes": _peak("uss_bytes"),
        "peak_process_tree_swap_bytes": _peak("process_tree_swap_bytes"),
        "peak_dedicated_cgroup_swap_bytes": _peak(
            "dedicated_cgroup_swap_bytes"
        ),
        "peak_swap_bytes": _peak("swap_bytes"),
        "swap_semantics": "max(process-tree VmSwap, dedicated job cgroup swap.current)",
        "sample_root_pid": (
            sampling_root_pid
            if sampling_root_pid is not None
            else worker_process_group_pid
        ),
        "sample_root_scope": (
            "public_launcher_and_all_descendants"
            if sampling_root_pid is not None
            else "worker_process_group_tree"
        ),
        "worker_process_group_pid": worker_process_group_pid,
        "worker_process_group_gone": group_gone,
        "phase_end_sample": phase_end_sample,
        "last_sample": last_sample,
        "process_tree_pid_peak_rss_bytes": pid_peaks,
        "minimum_host_memavailable_bytes": _minimum("host_memavailable_bytes"),
        "minimum_cgroup_memory_headroom_bytes": _minimum(
            "cgroup_memory_headroom_bytes"
        ),
        "minimum_cgroup_ancestor_memory_headroom_bytes": _minimum(
            "cgroup_ancestor_memory_headroom_bytes"
        ),
        "cgroup_ancestor_limit_states": sorted(cgroup_ancestor_limit_states),
        "cgroup_history_peak_bytes": _peak("cgroup_memory_peak_bytes"),
        "global_swap": {
            "baseline_used_bytes": (
                baseline.get("global_swap_used_bytes")
                if baseline is not None
                else None
            ),
            "peak_used_bytes": global_peak_used,
            "new_used_bytes": global_max_used_delta,
            "pswpin_delta_pages": global_max_pswpin_delta,
            "pswpout_delta_pages": global_max_pswpout_delta,
            "semantics": "shared-host diagnostic; not the job swap authority",
        },
    }


def run_task041_supervised_public_command(
    command: list[str],
    supervision_root: str | Path,
    *,
    profile_contract: Mapping[str, Any],
    ledger_snapshot: Mapping[str, Any],
    resource_limits: Mapping[str, Any],
    environment: Mapping[str, str],
    sample_factory: SampleFactory,
    repository_root: str | Path | None = None,
    popen_factory: PopenFactory = subprocess.Popen,
    terminate_factory: TerminateFactory = terminate_process_tree,
    monotonic: Clock = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    process_group_gone: Callable[[int], bool] = _process_group_gone,
    global_swap_baseline: Mapping[str, Any] | None = None,
    poll_interval: float = 0.25,
    launch_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Supervise one public command with an independent outer evidence root.

    The caller supplies already validated profile, ledger, resource limits, and
    child environment.  This narrow wrapper intentionally does not construct
    the numerical child environment or copy the child's output files.
    """

    profile_id = profile_contract["profile_id"]
    model_id = profile_contract["model_id"]
    case_runtime_contract = task041_balh_service_contract(str(model_id))
    is_case_runtime = bool(
        case_runtime_contract is not None
        and profile_contract.get("contract_kind")
        == "task041_registered_case_service"
        and profile_id == case_runtime_contract["profile_id"]
        and profile_contract.get("compute_wall_unlimited") is True
    )
    if profile_id != "task041_schur_speed_v2" and not is_case_runtime:
        raise Task041SupervisorError(
            "Task041 supervised public command has an unsupported contract",
            classification="task041_identity_failure",
            stage="supervised_public_profile",
        )
    if not is_case_runtime and model_id not in TASK041_BALH_CANDIDATE_MODEL_IDS:
        raise Task041SupervisorError(
            "Task041 supervised public command is limited to BAL_H candidates",
            classification="task041_identity_failure",
            stage="supervised_public_profile",
        )
    active_phase = profile_contract["active_consumer_phase"]
    if is_case_runtime:
        phase_budget = profile_contract["phase_budgets_seconds"][active_phase]
        batch_budget = profile_contract["batch_budget_seconds"]
        phase_used = float(
            ledger_snapshot.get("used_compute_wall_seconds", 0.0)
        )
        batch_used = phase_used
        phase_remaining = None
        batch_remaining = None
        effective_remaining = None
    else:
        phase_budget = float(profile_contract["phase_budgets_seconds"][active_phase])
        batch_budget = float(profile_contract["batch_budget_seconds"])
        batch_used = float(ledger_snapshot["batch_used_compute_wall_seconds"])
        phase_used = _task041_v2_group_used(ledger_snapshot, active_phase)
        phase_remaining = max(0.0, phase_budget - phase_used)
        batch_remaining = max(0.0, batch_budget - batch_used)
        effective_remaining = min(phase_remaining, batch_remaining)

    warning_memory_bytes = resource_limits["warning_memory_bytes"]
    hard_memory_bytes = resource_limits["hard_memory_bytes"]
    swap_limit_bytes = resource_limits["swap_limit_bytes"]
    if swap_limit_bytes != 0:
        raise Task041SupervisorError(
            "Task041 supervised public command requires the zero-swap contract",
            classification="task041_identity_failure",
            stage="supervised_public_limits",
        )
    rss_warning_bytes = profile_contract["warning_memory_bytes"]
    rss_cap_bytes = profile_contract["memory_cap_bytes"]

    root = Path(supervision_root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    log_root = root / "log"
    log_root.mkdir()
    launch_manifest_path: Path | None = None
    spawn_command = list(command)
    if launch_manifest is not None:
        if "--task041-supervision-record" in spawn_command:
            raise Task041SupervisorError(
                "supervised public command must not predefine its launch manifest path",
                classification="task041_identity_failure",
                stage="supervised_public_manifest",
            )
        launch_manifest_path = root / "launch_manifest.json"
        _write_json(launch_manifest_path, launch_manifest)
        spawn_command.extend(
            ["--task041-supervision-record", str(launch_manifest_path)]
        )
    repository = (
        Path(repository_root).resolve()
        if repository_root is not None
        else Path(__file__).resolve().parents[2]
    )
    started = monotonic()
    phase_result: dict[str, Any] | None = None
    partial_phase_results: dict[str, Any] = {}
    result = {
        "schema": "task041.supervised_public_command.v1",
        "status": "failed",
        "result_classification": None,
        "exit_status": None,
        "supervision_root": str(root),
        "command": spawn_command,
        "profile_id": profile_id,
        "model_id": model_id,
        "budget": {
            "phase_group": active_phase,
            "phase_budget_seconds": phase_budget,
            "phase_used_before_seconds": phase_used,
            "phase_remaining_seconds": phase_remaining,
            "batch_budget_seconds": batch_budget,
            "batch_used_before_seconds": batch_used,
            "batch_remaining_seconds": batch_remaining,
            "effective_remaining_seconds": effective_remaining,
            "basis": (
                "registered case ledger; no elapsed wall stop"
                if is_case_runtime
                else "min(phase_remaining_seconds, batch_remaining_seconds)"
            ),
        },
        "limits": {
            "warning_memory_bytes": warning_memory_bytes,
            "hard_memory_bytes": hard_memory_bytes,
            "swap_limit_bytes": swap_limit_bytes,
            "process_tree_rss_warning_bytes": rss_warning_bytes,
            "process_tree_rss_cap_bytes": rss_cap_bytes,
            "min_memavailable_bytes": resource_limits[
                "min_memavailable_bytes"
            ],
            "min_cgroup_ancestor_headroom_bytes": resource_limits[
                "min_cgroup_ancestor_headroom_bytes"
            ],
        },
        "environment_threads": {
            name: environment.get(name) for name in TASK041_REQUIRED_THREADS
        },
        "service_cgroup_cleanup": "not_checked_by_POSIX_phase_helper",
        "phase_result": None,
    }
    if launch_manifest_path is not None:
        result["launch_manifest"] = {
            "path": str(launch_manifest_path),
            "sha256": _sha256_file(launch_manifest_path),
            "outer_owner": launch_manifest.get("outer_owner"),
            "ledger_owner": launch_manifest.get("ledger_owner"),
        }
    if effective_remaining is not None and effective_remaining <= 0.0:
        result.update(
            {
                "result_classification": "cumulative_wall_timeout",
                "error": {
                    "type": "Task041SupervisorError",
                    "message": "no verified V2 budget remains before public launch",
                    "stage": "supervised_public_budget",
                },
                "prestart_stop": True,
            }
        )
        _write_json(root / "summary.json", result)
        return result
    try:
        phase_result = _run_phase(
            "public_command",
            spawn_command,
            root / "public_command_phase",
            log_root=log_root,
            environment=dict(environment),
            repository_root=repository,
            workflow_started=started,
            popen_factory=popen_factory,
            sample_factory=sample_factory,
            terminate_factory=terminate_factory,
            monotonic=monotonic,
            sleep=sleep,
            poll_interval=poll_interval,
            memory_stages_path=root / "memory_stages.jsonl",
            marker_path=root / "markers.jsonl",
            process_group_gone=process_group_gone,
            warning_memory_bytes=warning_memory_bytes,
            hard_memory_bytes=hard_memory_bytes,
            process_tree_rss_warning_bytes=rss_warning_bytes,
            process_tree_rss_cap_bytes=rss_cap_bytes,
            timeout_seconds=effective_remaining,
            phase_elapsed_timeout=not is_case_runtime,
            sample_root_pid=os.getpid(),
            min_memavailable_bytes=resource_limits["min_memavailable_bytes"],
            min_cgroup_ancestor_headroom_bytes=resource_limits[
                "min_cgroup_ancestor_headroom_bytes"
            ],
            cumulative_compute_used_seconds=phase_used,
            cumulative_compute_limit_seconds=(
                None if effective_remaining is None else phase_used + effective_remaining
            ),
            global_swap_baseline=global_swap_baseline,
            partial_phase_results=partial_phase_results,
            enforce_time_stops=(
                not is_case_runtime
                or profile_contract["time_stop"]["consumer_enforced"]
            ),
        )
        resource_failure = _phase_resource_failure(phase_result)
        if resource_failure:
            classification = _phase_resource_classification(phase_result)
            result_status = "failed"
            result_classification = classification or "task041_resource_failure"
            exit_status = phase_result.get("returncode")
        else:
            result_status = (
                "completed" if phase_result.get("returncode") == 0 else "failed"
            )
            result_classification = (
                "worker_exit0"
                if phase_result.get("returncode") == 0
                else "task041_public_command_nonzero"
            )
            exit_status = phase_result.get("returncode")
        result.update(
            {
                "status": result_status,
                "result_classification": result_classification,
                "exit_status": exit_status,
                "phase_result": phase_result,
            }
        )
    except Task041SupervisorError as exc:
        phase_result = partial_phase_results.get("public_command")
        phase_classification = (
            _phase_resource_classification(phase_result)
            if isinstance(phase_result, Mapping)
            else None
        )
        result.update(
            {
                "result_classification": phase_classification or exc.classification,
                "exit_status": (
                    phase_result.get("returncode")
                    if isinstance(phase_result, Mapping)
                    else None
                ),
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "stage": exc.stage,
                },
                "phase_result": phase_result,
            }
        )
    _write_json(root / "summary.json", result)
    return result


def _git_identity(repository_root: Path, source_sha: str) -> dict[str, Any]:
    def run_git(*args: str) -> str:
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=repository_root,
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise Task041SupervisorError(
                f"local git identity probe failed: {exc}",
                classification="task041_implementation_failure",
                stage="git_identity",
            ) from exc
        return completed.stdout.strip()

    head = run_git("rev-parse", "HEAD")
    branch = run_git("branch", "--show-current")
    status = run_git("status", "--porcelain", "--untracked-files=all")
    if head != source_sha:
        raise Task041SupervisorError(
            f"HEAD {head} does not match source SHA {source_sha}",
            classification="task041_identity_failure",
            stage="git_identity",
        )
    if branch != TASK041_BRANCH:
        raise Task041SupervisorError(
            f"branch {branch} does not match {TASK041_BRANCH}",
            classification="task041_identity_failure",
            stage="git_identity",
        )
    if status:
        raise Task041SupervisorError(
            "Task041 worktree is not clean before child launch",
            classification="task041_identity_failure",
            stage="git_identity",
        )
    return {
        "head": head,
        "branch": branch,
        "source_sha": source_sha,
        "worktree_clean": True,
        "status_scope": "nonignored+untracked",
    }


def _environment_snapshot(repository_root: Path) -> dict[str, Any]:
    entry = Path(os.path.abspath(sys.executable))
    target = entry.resolve()
    prefix = Path(sys.prefix).resolve()
    repo_venv = (repository_root / ".venv").resolve()
    failures: list[str] = []
    if os.environ.get("MYFENICS_NATIVE_COMPLEX_ENV") != "1":
        failures.append("MYFENICS_NATIVE_COMPLEX_ENV must equal 1")
    if repo_venv not in entry.parents:
        failures.append("sys.executable entry must be inside repository .venv")
    if prefix != repo_venv:
        failures.append("sys.prefix must resolve to repository .venv")
    threads = {name: os.environ.get(name) for name in TASK041_REQUIRED_THREADS}
    if any(value != "1" for value in threads.values()):
        failures.append("all Task041 mathematical thread controls must equal 1")
    snapshot = {
        "native_marker": os.environ.get("MYFENICS_NATIVE_COMPLEX_ENV"),
        "python_entry": str(entry),
        "python_resolved_target": str(target),
        "sys_prefix": str(prefix),
        "threads": threads,
        "platform": platform.platform(),
    }
    if failures:
        raise Task041SupervisorError(
            "; ".join(failures),
            classification="task041_identity_failure",
            stage="environment_identity",
        )
    return snapshot


def _outer_mpi_size() -> int:
    from mpi4py import MPI

    return int(MPI.COMM_WORLD.size)


def _outer_mpi_rank() -> int:
    from mpi4py import MPI

    return int(MPI.COMM_WORLD.rank)


def _outer_mpi_launch_identity(
    performance_profile: str | None = None,
    *,
    registered_model_id: str | None = None,
) -> dict[str, Any]:
    size = _outer_mpi_size()
    rank = _outer_mpi_rank()
    markers = {
        "OMPI_COMM_WORLD_SIZE": os.environ.get("OMPI_COMM_WORLD_SIZE"),
        "OMPI_COMM_WORLD_RANK": os.environ.get("OMPI_COMM_WORLD_RANK"),
    }
    if registered_model_id is not None:
        if registered_model_id != TASK041_BALH_2NM_MODEL_ID:
            raise Task041SupervisorError(
                "native public singleton is limited to the registered 2 nm case",
                classification="task041_identity_failure",
                stage="outer_mpi_identity",
            )
        if performance_profile is not None:
            raise Task041SupervisorError(
                "registered 2 nm native singleton cannot use a high-level performance profile",
                classification="task041_identity_failure",
                stage="outer_mpi_identity",
            )
        native_singleton = True
    elif performance_profile is not None:
        from benchmarks.task041_balh_workflow import (
            TASK041_SCHUR_SPEED_V2_PROFILE,
        )

        if performance_profile != TASK041_SCHUR_SPEED_V2_PROFILE:
            raise Task041SupervisorError(
                "unsupported Task041 performance profile",
                classification="task041_identity_failure",
                stage="outer_mpi_identity",
            )
        native_singleton = True
    else:
        native_singleton = False
    if native_singleton:
        failures: list[str] = []
        if size != TASK041_MPI_SIZE:
            failures.append(f"MPI.COMM_WORLD.size must be 1, got {size}")
        if rank != 0:
            failures.append(f"MPI.COMM_WORLD.rank must be 0, got {rank}")
        for name, value in markers.items():
            if value is not None:
                failures.append(
                    f"{name} must be absent for native public singleton, got {value!r}"
                )
        if failures:
            raise Task041SupervisorError(
                "; ".join(failures),
                classification="task041_identity_failure",
                stage="outer_mpi_identity",
            )
        return {
            "launcher": "native_python_singleton",
            "markers": markers,
            "mpi_size": size,
            "mpi_rank": rank,
            "launched_via_mpiexec": False,
            "native_public_singleton": True,
            "qualification": "native_public_singleton",
        }
    expected = {
        "OMPI_COMM_WORLD_SIZE": str(size),
        "OMPI_COMM_WORLD_RANK": str(rank),
    }
    failures: list[str] = []
    if size != TASK041_MPI_SIZE:
        failures.append(f"MPI.COMM_WORLD.size must be 1, got {size}")
    if rank != 0:
        failures.append(f"MPI.COMM_WORLD.rank must be 0, got {rank}")
    for name, expected_value in expected.items():
        if markers[name] != expected_value:
            failures.append(
                f"{name} must equal {expected_value!r}, got {markers[name]!r}"
            )
    if failures:
        raise Task041SupervisorError(
            "; ".join(failures),
            classification="task041_identity_failure",
            stage="outer_mpi_identity",
        )
    return {
        "launcher": "OpenMPI",
        "markers": markers,
        "mpi_size": size,
        "mpi_rank": rank,
        "launched_via_mpiexec": True,
    }


def _validate_specification(specification: Any, repository_root: Path) -> dict[str, Any]:
    snapshot = specification.as_jsonable()
    model_id = str(snapshot.get("model_id", ""))
    if model_id == TASK041_MODEL_ID:
        profile_validator = task041_profile_errors
        case = None
        expected_input = (repository_root / TASK041_INPUT).resolve()
        expected_run_id = TASK041_RUN_ID
        expected_modes = TASK041_MODE_COUNT
        expected_mpi_size = TASK041_MPI_SIZE
    elif model_id in TASK041_BALH_MODEL_IDS:
        case = task041_balh_case(model_id)
        if case is None:
            raise Task041SupervisorError(
                "Task041 side BAL_H case contract is unavailable",
                classification="task041_identity_failure",
                stage="input_identity",
            )
        profile_validator = task041_balh_profile_errors
        expected_input = (repository_root / str(case["input"])).resolve()
        expected_run_id = str(case["run_id"])
        expected_modes = int(case["mode_count"])
        expected_mpi_size = TASK041_BALH_MPI_SIZE
    elif model_id in TASK041_SHORTWAVE_MODEL_IDS:
        case = task041_shortwave_case(model_id)
        if case is None:
            raise Task041SupervisorError(
                "Task41 shortwave case contract is unavailable",
                classification="task041_identity_failure",
                stage="input_identity",
            )
        profile_validator = task041_shortwave_profile_errors
        expected_input = (repository_root / str(case["input"])).resolve()
        expected_run_id = str(case["run_id"])
        expected_modes = int(case["mode_count"])
        expected_mpi_size = TASK041_SHORTWAVE_MPI_SIZE
    else:
        raise Task041SupervisorError(
            f"unsupported Task041 supervisor model_id {model_id!r}",
            classification="task041_identity_failure",
            stage="input_identity",
        )
    failures: list[str] = []
    try:
        failures.extend(
            f"{field}: {message}"
            for field, message in profile_validator(snapshot)
        )
    except Exception as exc:  # noqa: BLE001 - malformed input is fail-closed
        failures.append(f"Task041 profile validation failed: {exc}")
    actual_input = Path(specification.source_path).resolve()
    if actual_input != expected_input:
        failures.append(
            f"input_path: observed={actual_input!s}, expected={expected_input!s}"
        )
    if not _valid_sha(specification.input_sha256, 64):
        failures.append("input_sha256 is not a valid SHA256")
    if not _valid_sha(specification.physical_model_sha256, 64):
        failures.append("physical_model_sha256 is not a valid SHA256")
    try:
        resolved_sha = resolved_config_sha256(specification)
    except Exception as exc:  # noqa: BLE001 - identity validation boundary
        failures.append(f"resolved config identity unavailable: {exc}")
        resolved_sha = None
    if not _valid_sha(resolved_sha, 64):
        failures.append("resolved_config_sha256 is not a valid SHA256")
    if failures:
        raise Task041SupervisorError(
            "Task041 profile rejected: " + "; ".join(failures),
            classification="task041_identity_failure",
            stage="input_identity",
        )
    return {
        "model_id": model_id,
        "run_id": expected_run_id,
        "input_sha256": specification.input_sha256,
        "physical_model_sha256": specification.physical_model_sha256,
        "resolved_config_sha256": resolved_sha,
        "requested_modes": expected_modes,
        "mpi_size": expected_mpi_size,
    }


def _initial_artifacts(root: Path) -> None:
    (root / "numerical_output" / "log").mkdir(parents=True, exist_ok=True)
    for name in ("memory_stages.jsonl", "memory_stage_markers.jsonl"):
        (root / name).touch()
    _write_json(root / "environment.json", {"status": "not_available"})
    _write_json(root / "mpi_environment.json", {"status": "not_available"})
    _write_json(root / "resource_summary.json", {"status": "not_sampled"})
    _write_json(root / "factor_inventory.json", {"status": "not_run"})
    _write_json(root / "selected_mode_manifest.json", {"status": "not_available"})
    _write_json(root / "external_mode_manifest.json", {"status": "not_available"})


def _mpiexec_argv(argv: list[str], mpiexec_command: str | None) -> list[str]:
    if mpiexec_command:
        argv[0] = str(mpiexec_command)
    return argv


def _packet_directory_inventory(packet_root: Path) -> dict[str, int]:
    file_count = 0
    total_bytes = 0
    for path in packet_root.rglob("*"):
        if path.is_file():
            file_count += 1
            total_bytes += path.stat().st_size
    return {"file_count": file_count, "bytes": total_bytes}


def _validate_producer_packet(
    producer_root: Path,
    specification: Any,
    source_sha: str,
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    summary_path = producer_root / "mode_prep_summary.json"
    summary = _read_json(summary_path)
    if summary.get("source_sha") != source_sha:
        raise Task041SupervisorError(
            "producer source SHA does not match the public identity",
            classification="task041_producer_validation_failure",
            stage="producer_packet",
        )
    if summary.get("classification") != "TASK041_MODE_PREP_PACKET_READY":
        raise Task041SupervisorError(
            "producer did not report TASK041_MODE_PREP_PACKET_READY",
            classification="task041_producer_failure",
            stage="producer_packet",
        )
    cleanup = summary.get("cleanup")
    if not isinstance(cleanup, Mapping) or cleanup.get("producer_scope_released") is not True:
        raise Task041SupervisorError(
            "producer cleanup scope was not released",
            classification="task041_producer_lifecycle_failure",
            stage="producer_packet",
        )
    identity_path = producer_root / "packet_identity.json"
    manifest_path = producer_root / "selected_mode_packet" / "manifest.json"
    if not identity_path.is_file() or not manifest_path.is_file():
        raise Task041SupervisorError(
            "producer packet identity or manifest is missing",
            classification="task041_producer_validation_failure",
            stage="producer_packet",
        )
    packet_identity = _read_json(identity_path)
    actual_manifest_sha = _sha256_file(manifest_path)
    packet = summary.get("packet")
    declared_manifest_sha = packet.get("manifest_sha256") if isinstance(packet, Mapping) else None
    if declared_manifest_sha != actual_manifest_sha:
        raise Task041SupervisorError(
            "producer packet manifest SHA mismatch",
            classification="task041_producer_validation_failure",
            stage="producer_packet",
        )
    expected = {
        "source_sha": source_sha,
        "input_sha256": specification.input_sha256,
        "physical_sha256": specification.physical_model_sha256,
        "resolved_sha256": identity["resolved_config_sha256"],
        "model_id": identity["model_id"],
        "run_id": identity["run_id"],
        "mode_count": identity["requested_modes"],
        "mpi_size": identity["mpi_size"],
    }
    identity_checks = {
        "source_sha": packet_identity.get("source_sha"),
        "input_sha256": packet_identity.get("input_sha256"),
        "physical_sha256": packet_identity.get("physical_sha256"),
        "resolved_sha256": packet_identity.get("resolved_sha256"),
        "model_id": packet_identity.get("model_id"),
        "run_id": packet_identity.get("run_id"),
        "mode_count": packet_identity.get("mode_count"),
        "mpi_size": packet_identity.get("mpi_size"),
    }
    if identity_checks != expected:
        raise Task041SupervisorError(
            f"producer packet identity mismatch: {identity_checks!r}",
            classification="task041_producer_validation_failure",
            stage="producer_packet",
        )
    packet_inventory = _packet_directory_inventory(manifest_path.parent)
    compact_manifest = {
        "schema": "task041.public.selected_mode_manifest.v1",
        "path": str(manifest_path.relative_to(producer_root.parent)),
        "sha256": actual_manifest_sha,
        "bytes": manifest_path.stat().st_size,
        "packet_directory_bytes": packet_inventory["bytes"],
        "packet_directory_file_count": packet_inventory["file_count"],
        "packet_directory": {
            "path": str(manifest_path.parent.relative_to(producer_root.parent)),
            **packet_inventory,
        },
        "identity": packet_identity,
        "source_sha": source_sha,
    }
    return {
        "summary": summary,
        "identity": packet_identity,
        "manifest": str(manifest_path),
        "manifest_sha256": actual_manifest_sha,
        "manifest_bytes": manifest_path.stat().st_size,
        "packet_directory": packet_inventory,
        "packet_directory_bytes": packet_inventory["bytes"],
        "packet_directory_file_count": packet_inventory["file_count"],
        "compact_manifest": compact_manifest,
    }


def _artifact_metadata(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": _sha256_file(path),
        "bytes": path.stat().st_size,
    }


def _rank_pid_affinity_artifact(phase_root: Path) -> dict[str, Any]:
    path = phase_root / "rank_pid_affinity.json"
    if not path.is_file():
        return {
            "status": "not_measured",
            "path": str(path),
            "records": [],
        }
    payload = _read_json(path)
    records = payload.get("records")
    return {
        "status": payload.get("status", "measured"),
        "path": str(path),
        "sha256": _sha256_file(path),
        "bytes": path.stat().st_size,
        "phase": payload.get("phase"),
        "source_sha": payload.get("source_sha"),
        "mpi_size": payload.get("mpi_size"),
        "records": records if isinstance(records, list) else [],
    }


def _task041_representative_immutable_binding(
    summary: Mapping[str, Any],
    binding: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Validate the fixed probe/source/packet contract shared by both checkers."""

    from benchmarks.task041_balh_workflow import (
        _TASK041_REPRESENTATIVE_RHS_EXPECTED,
        TASK041_REPRESENTATIVE_RHS_COUNT,
        TASK041_REPRESENTATIVE_RHS_SCOPE,
    )

    failures: list[str] = []
    checks: dict[str, Any] = {}
    expected_entries = binding.get("entries") if isinstance(binding, Mapping) else None
    expected_by_ordinal: dict[int, Mapping[str, Any]] = {}
    if not isinstance(expected_entries, list):
        failures.append("fixed_probe_binding_mismatch")
        expected_entries = []
    else:
        for entry in expected_entries:
            ordinal = entry.get("ordinal") if isinstance(entry, Mapping) else None
            if type(ordinal) is not int or ordinal in expected_by_ordinal:
                failures.append("fixed_probe_binding_mismatch")
                continue
            expected_by_ordinal[ordinal] = entry
    expected_signature = (
        tuple(
            (
                str(entry.get("side")),
                str(entry.get("branch")),
                entry.get("audit_index"),
                entry.get("formal_column"),
                entry.get("branch_ordinal"),
            )
            for entry in expected_entries
            if isinstance(entry, Mapping)
        )
        if expected_entries
        and all(isinstance(entry, Mapping) for entry in expected_entries)
        else ()
    )
    budget = binding.get("budget") if isinstance(binding, Mapping) else None
    checks["fixed_binding"] = bool(
        isinstance(binding, Mapping)
        and binding.get("scope") == TASK041_REPRESENTATIVE_RHS_SCOPE
        and len(expected_entries) == TASK041_REPRESENTATIVE_RHS_COUNT
        and set(expected_by_ordinal) == set(range(TASK041_REPRESENTATIVE_RHS_COUNT))
        and expected_signature == _TASK041_REPRESENTATIVE_RHS_EXPECTED
        and isinstance(budget, Mapping)
        and budget.get("group") == "shared_S0_S1_S3"
    )
    if not checks["fixed_binding"]:
        failures.append("fixed_probe_binding_mismatch")

    manifest_path = binding.get("path") if isinstance(binding, Mapping) else None
    manifest_sha = binding.get("sha256") if isinstance(binding, Mapping) else None
    if isinstance(manifest_path, str) and _valid_sha(manifest_sha, 64):
        try:
            checks["probe_manifest_hash"] = (
                Path(manifest_path).is_file()
                and _sha256_file(Path(manifest_path)) == manifest_sha
            )
        except OSError:
            checks["probe_manifest_hash"] = False
    else:
        checks["probe_manifest_hash"] = False
    if not checks["probe_manifest_hash"]:
        failures.append("probe_manifest_hash_mismatch")

    source_audit = binding.get("source_audit") if isinstance(binding, Mapping) else None
    if isinstance(source_audit, Mapping):
        source_path = source_audit.get("rhs_audit_path")
        source_sha = source_audit.get("rhs_audit_sha256")
        if isinstance(source_path, str) and _valid_sha(source_sha, 64):
            try:
                checks["source_audit_hash"] = (
                    Path(source_path).is_file()
                    and _sha256_file(Path(source_path)) == source_sha
                )
            except OSError:
                checks["source_audit_hash"] = False
        else:
            checks["source_audit_hash"] = False
    else:
        checks["source_audit_hash"] = False
    if not checks["source_audit_hash"]:
        failures.append("source_audit_hash_mismatch")

    probe_summary = summary.get("representative_rhs_probe")
    checks["summary_probe_binding"] = bool(
        isinstance(probe_summary, Mapping)
        and probe_summary.get("path") == manifest_path
        and probe_summary.get("sha256") == manifest_sha
        and probe_summary.get("scope") == TASK041_REPRESENTATIVE_RHS_SCOPE
        and probe_summary.get("budget_group") == "shared_S0_S1_S3"
    )
    if not checks["summary_probe_binding"]:
        failures.append("summary_probe_binding_mismatch")

    packet_binding = (
        binding.get("packet_binding") if isinstance(binding, Mapping) else None
    )
    packet_summary = summary.get("packet")
    expected_packet_sha = (
        packet_binding.get("packet_manifest_sha256")
        if isinstance(packet_binding, Mapping)
        else None
    )
    expected_identity_path = (
        packet_binding.get("packet_identity")
        if isinstance(packet_binding, Mapping)
        else None
    )
    identity_summary = summary.get("identity")
    checks["source_and_packet_identity"] = bool(
        _valid_sha(summary.get("source_sha"), 40)
        and isinstance(identity_summary, Mapping)
        and identity_summary.get("source_sha") == summary.get("source_sha")
        and identity_summary.get("model_id")
        == "task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8"
        and identity_summary.get("mode_count") == 480
        and identity_summary.get("mpi_size") == 8
        and isinstance(packet_summary, Mapping)
        and packet_summary.get("manifest_sha256") == expected_packet_sha
        and packet_summary.get("identity") == expected_identity_path
        and isinstance(packet_binding, Mapping)
        and _valid_sha(packet_binding.get("packet_identity_sha256"), 64)
    )
    if not checks["source_and_packet_identity"]:
        failures.append("source_or_packet_identity_mismatch")
    packet_identity_sha = (
        packet_binding.get("packet_identity_sha256")
        if isinstance(packet_binding, Mapping)
        else None
    )
    if isinstance(expected_identity_path, str) and _valid_sha(packet_identity_sha, 64):
        try:
            checks["packet_identity_hash"] = (
                Path(expected_identity_path).is_file()
                and _sha256_file(Path(expected_identity_path)) == packet_identity_sha
            )
        except OSError:
            checks["packet_identity_hash"] = False
    else:
        checks["packet_identity_hash"] = False
    if not checks["packet_identity_hash"]:
        failures.append("packet_identity_hash_mismatch")

    return {
        "checks": checks,
        "failures": failures,
        "expected_entries": expected_entries,
        "expected_by_ordinal": expected_by_ordinal,
        "expected_signature": expected_signature,
        "packet_binding": packet_binding,
        "expected_packet_sha": expected_packet_sha,
        "expected_identity_path": expected_identity_path,
    }


def _validate_representative_rhs_result(
    consumer_root: Path,
    summary: Mapping[str, Any],
    binding: Mapping[str, Any],
    *,
    process_group_gone: bool | None,
    expected_side_setup_schedule: str | None = None,
) -> dict[str, Any]:
    """Independently validate the fixed finite-response worker evidence."""

    from benchmarks.task041_balh_workflow import (
        TASK041_REPRESENTATIVE_RHS_COUNT,
        TASK041_REPRESENTATIVE_RHS_SCOPE,
        TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
    )

    binding_evidence = _task041_representative_immutable_binding(
        summary, binding
    )
    failures = list(binding_evidence["failures"])
    checks = dict(binding_evidence["checks"])
    expected_by_ordinal = binding_evidence["expected_by_ordinal"]
    expected_packet_sha = binding_evidence["expected_packet_sha"]

    raw_path = consumer_root / "numerical_output" / "representative_rhs_audits.jsonl"
    raw_by_ordinal: dict[int, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    raw_errors: list[str] = []
    if not raw_path.is_file():
        failures.append("representative_rhs_audits_missing")
    else:
        try:
            with raw_path.open(encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        raw_errors.append(f"line_{line_number}_invalid_json")
                        continue
                    if not isinstance(row, Mapping):
                        raw_errors.append(f"line_{line_number}_not_object")
                        continue
                    audit = row.get("audit")
                    ordinal = (
                        audit.get("representative_ordinal")
                        if isinstance(audit, Mapping)
                        else None
                    )
                    if not isinstance(ordinal, int) or isinstance(ordinal, bool):
                        raw_errors.append(f"line_{line_number}_missing_ordinal")
                        continue
                    if ordinal in raw_by_ordinal:
                        raw_errors.append(f"ordinal_{ordinal}_duplicated")
                        continue
                    if isinstance(audit, Mapping):
                        raw_by_ordinal[ordinal] = (row, audit)
                    else:
                        raw_errors.append(f"line_{line_number}_missing_audit")
        except OSError as exc:
            raw_errors.append(f"read_error:{type(exc).__name__}")
    if raw_errors:
        failures.extend(raw_errors)

    def audit_failures(
        entry: Mapping[str, Any], row: Mapping[str, Any], audit: Mapping[str, Any]
    ) -> list[str]:
        local: list[str] = []
        for field in ("side", "phase"):
            expected = entry["side"] if field == "side" else "representative_rhs"
            if row.get(field) != expected:
                local.append(f"{field}_binding")
        for field in (
            "representative_ordinal",
            "source_audit_index",
            "formal_column",
            "branch_ordinal",
        ):
            expected_field = {
                "representative_ordinal": "ordinal",
                "source_audit_index": "audit_index",
                "formal_column": "formal_column",
                "branch_ordinal": "branch_ordinal",
            }[field]
            if audit.get(field) != entry[expected_field]:
                local.append(f"{field}_binding")
        if audit.get("status") != "KSP_CONVERGED":
            local.append("status")
        if not isinstance(audit.get("reason"), int) or isinstance(
            audit.get("reason"), bool
        ) or audit["reason"] <= 0:
            local.append("reason")
        if audit.get("ksp_positive") is not True:
            local.append("ksp_positive")
        if audit.get("explicit_true_target_reached") is not True:
            local.append("explicit_true_target_reached")
        residual = audit.get("relative_residual")
        if (
            isinstance(residual, bool)
            or not isinstance(residual, (int, float))
            or not math.isfinite(float(residual))
            or float(residual) < 0.0
            or float(residual) > 1.0e-2
        ):
            local.append("relative_residual")
        rhs_norm = audit.get("rhs_norm")
        if (
            isinstance(rhs_norm, bool)
            or not isinstance(rhs_norm, (int, float))
            or not math.isfinite(float(rhs_norm))
            or float(rhs_norm) < 0.0
        ):
            local.append("rhs_norm")
        residual_norm = audit.get("residual_norm")
        if (
            isinstance(residual_norm, bool)
            or not isinstance(residual_norm, (int, float))
            or not math.isfinite(float(residual_norm))
            or float(residual_norm) < 0.0
        ):
            local.append("residual_norm")
        elif (
            isinstance(rhs_norm, (int, float))
            and not isinstance(rhs_norm, bool)
            and math.isfinite(float(rhs_norm))
        ):
            recomputed_relative = (
                float(residual_norm) / float(rhs_norm)
                if float(rhs_norm) > 0.0
                else float(residual_norm)
            )
            if (
                not math.isfinite(recomputed_relative)
                or recomputed_relative < 0.0
                or recomputed_relative > 1.0e-2
            ):
                local.append("recomputed_relative_residual")
        if audit.get("ksp_max_it") != 128 or audit.get("ksp_rtol") != 1.0e-2:
            local.append("ksp_contract")
        delta = audit.get("counts", {}).get("delta")
        for name in ("pc", "Q", "H6", "A6", "P", "PH_audit", "p4_backsolve"):
            value = delta.get(name) if isinstance(delta, Mapping) else None
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                local.append(f"count_{name}")
        return local

    checks["raw_audits"] = {"count": len(raw_by_ordinal), "expected": 8}
    for ordinal, entry in expected_by_ordinal.items():
        pair = raw_by_ordinal.get(ordinal)
        if pair is None:
            failures.append(f"raw_ordinal_{ordinal}_missing")
            continue
        row, audit = pair
        local_failures = audit_failures(entry, row, audit)
        failures.extend(f"ordinal_{ordinal}_{item}" for item in local_failures)
    if len(raw_by_ordinal) != TASK041_REPRESENTATIVE_RHS_COUNT:
        failures.append("raw_audit_count_mismatch")

    setup = summary.get("setup")
    admission = setup.get("admission_audit") if isinstance(setup, Mapping) else None
    global_identity = (
        admission.get("global_operator_identity")
        if isinstance(admission, Mapping)
        else None
    )
    checks["admission_gate"] = bool(
        isinstance(admission, Mapping)
        and admission.get("pass") is True
        and isinstance(global_identity, Mapping)
        and global_identity.get("pass") is True
    )
    if not checks["admission_gate"]:
        failures.append("admission_gate")

    representative = summary.get("representative_rhs")
    summary_records = (
        representative.get("entries") if isinstance(representative, Mapping) else None
    )
    summary_by_ordinal: dict[int, Mapping[str, Any]] = {}
    if isinstance(summary_records, list):
        for record in summary_records:
            if isinstance(record, Mapping) and isinstance(record.get("ordinal"), int):
                summary_by_ordinal[int(record["ordinal"])] = record
    checks["summary_records"] = {
        "count": len(summary_by_ordinal),
        "expected": TASK041_REPRESENTATIVE_RHS_COUNT,
    }
    for ordinal, entry in expected_by_ordinal.items():
        record = summary_by_ordinal.get(ordinal)
        if record is None:
            failures.append(f"summary_ordinal_{ordinal}_missing")
            continue
        if (
            record.get("side") != entry["side"]
            or record.get("branch") != entry["branch"]
            or record.get("audit_index") != entry["audit_index"]
            or record.get("formal_column") != entry["formal_column"]
            or record.get("branch_ordinal") != entry["branch_ordinal"]
            or record.get("status") != "completed"
        ):
            failures.append(f"summary_ordinal_{ordinal}_binding")
        raw_pair = raw_by_ordinal.get(ordinal)
        record_audit = record.get("audit")
        if raw_pair is None or not isinstance(record_audit, Mapping):
            failures.append(f"summary_ordinal_{ordinal}_audit_missing")
        else:
            for field in (
                "status",
                "reason",
                "relative_residual",
                "rhs_norm",
                "residual_norm",
                "ksp_max_it",
                "ksp_rtol",
            ):
                if record_audit.get(field) != raw_pair[1].get(field):
                    failures.append(f"summary_ordinal_{ordinal}_{field}_mismatch")
        artifact = record.get("artifact")
        rank_shards = record.get("rank_shards")
        if not isinstance(artifact, Mapping) or not _valid_sha(
            artifact.get("manifest_sha256"), 64
        ):
            failures.append(f"summary_ordinal_{ordinal}_artifact_manifest")
        if not isinstance(rank_shards, list) or {
            shard.get("rank")
            for shard in rank_shards
            if isinstance(shard, Mapping)
        } != set(range(8)):
            failures.append(f"summary_ordinal_{ordinal}_rank_shards")
        else:
            for shard in rank_shards:
                if not isinstance(shard, Mapping) or not _valid_sha(
                    shard.get("owned_rhs_sha256"), 64
                ) or not _valid_sha(shard.get("owned_response_sha256"), 64):
                    failures.append(f"summary_ordinal_{ordinal}_owned_hash")
                if not isinstance(shard, Mapping) or shard.get("dtype") != "complex128":
                    failures.append(f"summary_ordinal_{ordinal}_dtype")
                if not isinstance(shard, Mapping) or shard.get(
                    "packet_manifest_sha256"
                ) != expected_packet_sha:
                    failures.append(f"summary_ordinal_{ordinal}_packet_manifest")
        artifact_failures: list[str] = []
        response_manifest: Mapping[str, Any] | None = None
        response_manifest_path: Path | None = None
        response_manifest_sha: str | None = None
        if not isinstance(artifact, Mapping):
            artifact_failures.append("artifact_missing")
        else:
            manifest_value = artifact.get("manifest")
            response_manifest_sha = artifact.get("manifest_sha256")
            if not isinstance(manifest_value, str) or not manifest_value:
                artifact_failures.append("artifact_manifest_path")
            else:
                response_manifest_path = Path(manifest_value)
                if not response_manifest_path.is_file():
                    artifact_failures.append("artifact_manifest_missing")
                else:
                    try:
                        actual_manifest_sha = _sha256_file(response_manifest_path)
                        if actual_manifest_sha != response_manifest_sha:
                            artifact_failures.append("artifact_manifest_hash")
                        response_manifest_sha = actual_manifest_sha
                        loaded_manifest = json.loads(
                            response_manifest_path.read_text(encoding="utf-8")
                        )
                        if isinstance(loaded_manifest, Mapping):
                            response_manifest = loaded_manifest
                        else:
                            artifact_failures.append("artifact_manifest_object")
                    except (OSError, json.JSONDecodeError):
                        artifact_failures.append("artifact_manifest_read")
            artifact_identity_sha = artifact.get("identity_sha256")
            if not _valid_sha(artifact_identity_sha, 64):
                artifact_failures.append("artifact_identity_hash")
        if response_manifest is not None and response_manifest_path is not None:
            manifest_identity = response_manifest.get("identity")
            manifest_identity_sha = response_manifest.get("identity_sha256")
            if not isinstance(manifest_identity, Mapping):
                artifact_failures.append("artifact_identity_missing")
            else:
                try:
                    canonical_identity = json.dumps(
                        manifest_identity, sort_keys=True, separators=(",", ":")
                    ).encode("utf-8")
                    computed_identity_sha = hashlib.sha256(canonical_identity).hexdigest()
                except (TypeError, ValueError):
                    computed_identity_sha = None
                if (
                    not _valid_sha(manifest_identity_sha, 64)
                    or computed_identity_sha != manifest_identity_sha
                    or manifest_identity_sha != artifact.get("identity_sha256")
                ):
                    artifact_failures.append("artifact_identity_binding")
                if (
                    manifest_identity.get("schema")
                    != "task041.representative_rhs.response_identity.v1"
                    or manifest_identity.get("source_sha")
                    != summary.get("source_sha")
                    or manifest_identity.get("probe_manifest_sha256")
                    != binding.get("sha256")
                    or manifest_identity.get("packet_manifest_sha256")
                    != expected_packet_sha
                    or manifest_identity.get("ordinal") != ordinal
                    or manifest_identity.get("side") != entry["side"]
                    or manifest_identity.get("formal_column")
                    != entry["formal_column"]
                    or manifest_identity.get("branch_ordinal")
                    != entry["branch_ordinal"]
                ):
                    artifact_failures.append("artifact_identity_scope")
            manifest_shards = response_manifest.get("shards")
            manifest_ranks = (
                {
                    int(shard["rank"])
                    for shard in manifest_shards
                    if isinstance(shard, Mapping) and "rank" in shard
                }
                if isinstance(manifest_shards, list)
                else set()
            )
            if (
                response_manifest.get("schema") != "myfenics.full3d.pre_recovery_packet.v1"
                or response_manifest.get("rank_count") != 8
                or not isinstance(manifest_shards, list)
                or len(manifest_shards) != 8
                or manifest_ranks != set(range(8))
            ):
                artifact_failures.append("artifact_shard_layout")
            manifest_by_rank = {
                int(shard["rank"]): shard
                for shard in manifest_shards
                if isinstance(shard, Mapping) and "rank" in shard
            } if isinstance(manifest_shards, list) else {}
            expected_start = 0
            for rank in sorted(manifest_by_rank):
                shard = manifest_by_rank[rank]
                ownership = shard.get("ownership_range")
                size = shard.get("size")
                shard_path_value = shard.get("path")
                try:
                    start, end = (int(value) for value in ownership)
                    shard_size = int(size)
                except (TypeError, ValueError):
                    artifact_failures.append(f"artifact_shard_{rank}_layout")
                    continue
                if start != expected_start or end < start or end - start != shard_size:
                    artifact_failures.append(f"artifact_shard_{rank}_ownership")
                expected_start = end
                if not isinstance(shard_path_value, str) or not _valid_sha(
                    shard.get("sha256"), 64
                ):
                    artifact_failures.append(f"artifact_shard_{rank}_metadata")
                    continue
                shard_path = response_manifest_path.parent / shard_path_value
                if shard_path.parent != response_manifest_path.parent or not shard_path.is_file():
                    artifact_failures.append(f"artifact_shard_{rank}_missing")
                else:
                    try:
                        if _sha256_file(shard_path) != shard["sha256"]:
                            artifact_failures.append(f"artifact_shard_{rank}_hash")
                    except OSError:
                        artifact_failures.append(f"artifact_shard_{rank}_read")
            if response_manifest.get("global_size") != expected_start:
                artifact_failures.append("artifact_global_size")
            if not isinstance(rank_shards, list) or len(rank_shards) != 8:
                artifact_failures.append("rank_shards_count")
            else:
                rank_records_by_rank = {
                    int(shard["rank"]): shard
                    for shard in rank_shards
                    if isinstance(shard, Mapping) and "rank" in shard
                }
                if set(rank_records_by_rank) != set(range(8)):
                    artifact_failures.append("rank_shards_binding_ranks")
                for rank, rank_record in rank_records_by_rank.items():
                    manifest_shard = manifest_by_rank.get(rank)
                    if manifest_shard is None:
                        continue
                    if (
                        rank_record.get("ownership_range")
                        != manifest_shard.get("ownership_range")
                        or rank_record.get("local_size") != manifest_shard.get("size")
                        or rank_record.get("packet_shard_path")
                        != manifest_shard.get("path")
                        or rank_record.get("packet_shard_sha256")
                        != manifest_shard.get("sha256")
                        or rank_record.get("response_packet_manifest_sha256")
                        != response_manifest_sha
                    ):
                        artifact_failures.append(f"rank_{rank}_artifact_binding")
        if artifact_failures:
            failures.extend(
                f"summary_ordinal_{ordinal}_{item}" for item in artifact_failures
            )

    setup_inventory = (
        setup.get("candidate_inventory") if isinstance(setup, Mapping) else None
    )
    setup_schedule = (
        setup.get("side_setup_schedule") if isinstance(setup, Mapping) else None
    )
    summary_schedule = summary.get("side_setup_schedule")
    sequential_schedule = (
        expected_side_setup_schedule == TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
    )
    checks["schedule_binding"] = (
        setup_schedule == expected_side_setup_schedule
        and summary_schedule == expected_side_setup_schedule
    )
    if not checks["schedule_binding"]:
        failures.append("side_setup_schedule_binding")

    matrix = summary.get("matrix_inventory")
    after_p4 = (
        matrix.get("p4_factor_count_after_cleanup")
        if isinstance(matrix, Mapping)
        else None
    )
    after_nested = (
        matrix.get("nested_iterative_ksp_count_after_cleanup")
        if isinstance(matrix, Mapping)
        else None
    )
    common_inventory = bool(
        isinstance(matrix, Mapping)
        and matrix.get("qep_calls") == 0
        and matrix.get("consumer_qep_required") is False
        and matrix.get("p6_factor_count") == 0
        and matrix.get("global_direct_factor_count") == 0
        and isinstance(after_p4, Mapping)
        and set(after_p4) == {"bottom", "top"}
        and all(value == 0 for value in after_p4.values())
        and isinstance(after_nested, Mapping)
        and set(after_nested) == {"bottom", "top"}
        and all(value == 0 for value in after_nested.values())
    )
    if sequential_schedule:
        sequential_evidence = _task041_sequential_lifecycle_evidence(
            consumer_root,
            setup if isinstance(setup, Mapping) else None,
            expected_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        )
        checks["sequential_markers"] = {
            "path": sequential_evidence["path"],
            "errors": sequential_evidence["errors"],
            "lifecycle_count": len(sequential_evidence["boundaries"]),
            "identity_count": len(sequential_evidence["identities"]),
            "cleanup_count": len(sequential_evidence["cleanup"]),
            "lifecycle_time_order": sequential_evidence["boundary_time_pass"],
            "lifecycle_counts": sequential_evidence["boundary_counts_pass"],
            "created": sequential_evidence["created"],
            "peaks": sequential_evidence["peaks"],
            "identity_values_and_order": (
                sequential_evidence["identity_values_pass"]
                and sequential_evidence["identity_order_pass"]
            ),
            "identity_lifecycle_order": sequential_evidence[
                "identity_order_pass"
            ],
            "summary_counts": sequential_evidence["summary_counts_pass"],
            "cleanup_values": sequential_evidence["cleanup_pass"],
        }
        checks["sequential_lifecycle"] = sequential_evidence["pass"] is True
        if not checks["sequential_lifecycle"]:
            failures.extend(
                f"sequential_lifecycle:{error}"
                for error in sequential_evidence.get(
                    "errors", ["lifecycle_invalid"]
                )
            )
        checks["component_inventory"] = bool(
            common_inventory
            and isinstance(matrix, Mapping)
            and matrix.get("p4_factor_count_at_setup") is None
            and matrix.get("nested_iterative_ksp_count_at_setup") is None
            and isinstance(setup_inventory, Mapping)
            and setup_inventory.get("component_cleanup_pass") is True
            and checks["sequential_lifecycle"]
        )
    else:
        checks["component_inventory"] = bool(
            common_inventory
            and isinstance(matrix, Mapping)
            and matrix.get("p4_factor_count_at_setup") == 2
            and matrix.get("nested_iterative_ksp_count_at_setup") == 2
        )
    if not checks["component_inventory"]:
        failures.append("component_inventory_gate")

    lifecycle = summary.get("lifecycle")
    observed = summary.get("markers", {}).get("observed")
    checks["cleanup_and_scope"] = bool(
        isinstance(lifecycle, Mapping)
        and lifecycle.get("setup_released") is True
        and lifecycle.get("representative_rhs_cleanup_pass") is True
        and lifecycle.get("rss_marker_emitted") is True
        and isinstance(observed, list)
        and {"bottom_construction_cleanup", "top_construction_cleanup", "final_cleanup_complete"}
        <= set(observed)
        and (
            not sequential_schedule
            or "both_side_actions_ready" not in set(observed)
        )
        and process_group_gone is True
        and summary.get("gates", {}).get("pass") is False
        and summary.get("official_rta", {}).get("status") == "not_run"
        and isinstance(summary.get("formal"), Mapping)
        and summary["formal"].get("status") == "not_run"
    )
    if not checks["cleanup_and_scope"]:
        failures.append("cleanup_or_not_run_scope_gate")
    return {
        "pass": not failures,
        "scope": TASK041_REPRESENTATIVE_RHS_SCOPE,
        "raw_path": str(raw_path),
        "checks": checks,
        "failures": failures,
    }


def _task041_sequential_lifecycle_evidence(
    consumer_root: Path,
    setup: Mapping[str, Any] | None,
    *,
    expected_schedule: str,
) -> dict[str, Any]:
    """Read the fixed sequential lifecycle evidence shared by component modes."""

    errors: list[str] = []
    marker_path = consumer_root / "markers.jsonl"
    lifecycle: list[dict[str, Any]] = []
    identities: list[dict[str, Any]] = []
    cleanup: list[dict[str, Any]] = []
    if not marker_path.is_file():
        errors.append("markers_missing")
    else:
        try:
            with marker_path.open(encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    try:
                        marker = json.loads(line)
                    except json.JSONDecodeError:
                        errors.append(f"marker_line_{line_number}_invalid_json")
                        continue
                    if not isinstance(marker, Mapping):
                        errors.append(f"marker_line_{line_number}_not_object")
                        continue
                    detail = marker.get("detail")
                    if not isinstance(detail, Mapping):
                        continue
                    stage = marker.get("stage")
                    boundary = detail.get("lifecycle_boundary")
                    if isinstance(boundary, Mapping) and (
                        detail.get("substage") == "side_lifecycle"
                        or stage
                        in {
                            "bottom_factor_ready",
                            "top_factor_ready",
                            "bottom_construction_cleanup",
                            "top_construction_cleanup",
                        }
                    ):
                        lifecycle.append(
                            {
                                "boundary": dict(boundary),
                                "line_number": line_number,
                                "wall_seconds": marker.get("wall_seconds"),
                            }
                        )
                    if detail.get("substage") == "global_identity":
                        identity = detail.get("identity_check")
                        if isinstance(identity, Mapping):
                            identities.append(
                                {
                                    "check": dict(identity),
                                    "line_number": line_number,
                                }
                            )
                    if stage in {
                        "bottom_construction_cleanup",
                        "top_construction_cleanup",
                    }:
                        diagnostics = detail.get("diagnostics")
                        if isinstance(diagnostics, Mapping):
                            cleanup.append(
                                {
                                    "side": detail.get("side")
                                    or str(stage).split("_", 1)[0],
                                    "diagnostics": dict(diagnostics),
                                    "line_number": line_number,
                                }
                            )
        except OSError as exc:
            errors.append(f"markers_read_{type(exc).__name__}")

    expected_boundaries = [
        (side, event)
        for side in ("bottom", "top")
        for event in ("before_build", "ready", "before_release", "released")
    ]
    boundaries = [row["boundary"] for row in lifecycle]
    boundary_keys = [(row.get("side"), row.get("event")) for row in boundaries]

    def live_counts(boundary: Mapping[str, Any]) -> dict[str, Any] | None:
        live = boundary.get("live")
        by_side = live.get("by_side") if isinstance(live, Mapping) else None
        if not isinstance(by_side, Mapping):
            return None
        p4 = 0
        nested = 0
        live_side_count = 0
        for side, values in by_side.items():
            if not isinstance(side, str) or not isinstance(values, Mapping):
                return None
            p4_value = values.get("p4_factor_count")
            nested_value = values.get("nested_iterative_ksp_count")
            if (
                type(p4_value) is not int
                or p4_value < 0
                or type(nested_value) is not int
                or nested_value < 0
            ):
                return None
            p4 += p4_value
            nested += nested_value
            live_side_count += int(p4_value > 0 or nested_value > 0)
        return {
            "by_side": by_side,
            "live_side_count": live_side_count,
            "p4_factor": p4,
            "nested_iterative_ksp": nested,
            "component": p4 + nested,
        }

    raw_created = {
        "side_inverse": 0,
        "p4_factor": 0,
        "nested_iterative_ksp": 0,
    }
    raw_peaks = {
        "side_inverse": 0,
        "p4_factor": 0,
        "nested_iterative_ksp": 0,
        "component": 0,
    }
    boundary_counts_pass = len(boundaries) == len(expected_boundaries)
    boundary_time_values = [row.get("wall_seconds") for row in lifecycle]
    boundary_time_pass = bool(
        len(boundary_time_values) == 8
        and all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and float(value) >= 0.0
            for value in boundary_time_values
        )
        and all(
            float(left) <= float(right)
            for left, right in pairwise(boundary_time_values)
        )
    )
    if not boundary_time_pass:
        errors.append("lifecycle_time_order")
    for boundary in boundaries:
        counts = live_counts(boundary)
        if counts is None:
            boundary_counts_pass = False
            continue
        live = boundary.get("live")
        if (
            not isinstance(live, Mapping)
            or live.get("live_side_count") != counts["live_side_count"]
            or live.get("live_component_counts")
            != {
                "p4_factor": counts["p4_factor"],
                "nested_iterative_ksp": counts["nested_iterative_ksp"],
            }
            or live.get("live_component_count_sum") != counts["component"]
        ):
            boundary_counts_pass = False
        raw_peaks["side_inverse"] = max(
            raw_peaks["side_inverse"], counts["live_side_count"]
        )
        raw_peaks["p4_factor"] = max(
            raw_peaks["p4_factor"], counts["p4_factor"]
        )
        raw_peaks["nested_iterative_ksp"] = max(
            raw_peaks["nested_iterative_ksp"], counts["nested_iterative_ksp"]
        )
        raw_peaks["component"] = max(raw_peaks["component"], counts["component"])
        event = boundary.get("event")
        if event == "ready":
            created = boundary.get("created_at_boundary")
            if not isinstance(created, Mapping) or any(
                type(created.get(name)) is not int or created.get(name) != 1
                for name in raw_created
            ):
                boundary_counts_pass = False
            else:
                for name in raw_created:
                    raw_created[name] += created[name]
        if event in {"before_build", "released"} and (
            counts["live_side_count"] != 0 or counts["component"] != 0
        ):
            boundary_counts_pass = False
        if event in {"ready", "before_release"} and (
            counts["live_side_count"] != 1
            or counts["p4_factor"] != 1
            or counts["nested_iterative_ksp"] != 1
            or len(counts["by_side"]) != 1
            or set(counts["by_side"]) != {boundary.get("side")}
        ):
            boundary_counts_pass = False
    if not boundary_counts_pass:
        errors.append("lifecycle_counts")

    expected_identity_labels = [
        f"{side}_{event}"
        for side in ("bottom", "top")
        for event in (
            "before_build",
            "after_admission",
            "before_release",
            "after_release",
        )
    ]

    def identity_values_pass(value: Any) -> bool:
        if not isinstance(value, Mapping) or value.get("pass") is not True:
            return False
        for name in (
            "action_relative",
            "rhs_relative",
            "source_unchanged_relative",
        ):
            item = value.get(name)
            if (
                not isinstance(item, (int, float))
                or isinstance(item, bool)
                or not math.isfinite(float(item))
                or float(item) < 0.0
                or float(item) > 1.0e-12
            ):
                return False
        return True

    identity_labels = [row["check"].get("label") for row in identities]
    side_setup = setup.get("side_setup") if isinstance(setup, Mapping) else None
    summary_identity = (
        side_setup.get("global_identity_checks")
        if isinstance(side_setup, Mapping)
        else None
    )
    identity_values_passed = bool(
        len(identities) == 8
        and identity_labels == expected_identity_labels
        and all(identity_values_pass(row["check"]) for row in identities)
        and isinstance(summary_identity, Mapping)
        and set(summary_identity) == set(expected_identity_labels)
        and all(
            summary_identity.get(label) == identities[index]["check"]
            for index, label in enumerate(expected_identity_labels)
        )
    )
    if not identity_values_passed:
        errors.append("global_identity_values")

    lifecycle_lines = {
        (row["boundary"].get("side"), row["boundary"].get("event")): row[
            "line_number"
        ]
        for row in lifecycle
    }
    identity_lines = {
        row["check"].get("label"): row["line_number"] for row in identities
    }
    identity_order_pass = True
    for side in ("bottom", "top"):
        ordered = (
            identity_lines.get(f"{side}_before_build"),
            lifecycle_lines.get((side, "before_build")),
            lifecycle_lines.get((side, "ready")),
            identity_lines.get(f"{side}_after_admission"),
            identity_lines.get(f"{side}_before_release"),
            lifecycle_lines.get((side, "before_release")),
            lifecycle_lines.get((side, "released")),
            identity_lines.get(f"{side}_after_release"),
        )
        if not all(type(value) is int for value in ordered) or not all(
            left < right for left, right in pairwise(ordered)
        ):
            identity_order_pass = False
    if not identity_order_pass:
        errors.append("global_identity_lifecycle_order")

    summary_boundaries = (
        side_setup.get("lifecycle_boundaries")
        if isinstance(side_setup, Mapping)
        else None
    )
    summary_after = (
        setup.get("side_diagnostics_after_destroy")
        if isinstance(setup, Mapping)
        else None
    )
    cleanup_sides = [row.get("side") for row in cleanup]
    cleanup_pass = bool(
        len(cleanup) == 2
        and cleanup_sides == ["bottom", "top"]
        and isinstance(summary_after, Mapping)
        and set(summary_after) == {"bottom", "top"}
        and all(
            isinstance(row.get("diagnostics"), Mapping)
            and row["diagnostics"].get("destroyed") is True
            and type(row["diagnostics"].get("p4_factor_count")) is int
            and row["diagnostics"].get("p4_factor_count") == 0
            and type(row["diagnostics"].get("nested_iterative_ksp_count")) is int
            and row["diagnostics"].get("nested_iterative_ksp_count") == 0
            and summary_after.get(row["side"]) == row["diagnostics"]
            for row in cleanup
        )
    )
    if not cleanup_pass:
        errors.append("side_cleanup_evidence")
    summary_count_payloads = [side_setup]
    if isinstance(setup, Mapping):
        summary_count_payloads.append(setup.get("candidate_inventory"))

    def summary_counts_match(value: Any) -> bool:
        return isinstance(value, Mapping) and all(
            value.get(field) == expected
            for field, expected in (
                ("p4_factor_created_total", raw_created["p4_factor"]),
                (
                    "nested_iterative_ksp_created_total",
                    raw_created["nested_iterative_ksp"],
                ),
                ("total_created", raw_created["side_inverse"]),
                ("p4_factor_simultaneously_live_peak", raw_peaks["p4_factor"]),
                (
                    "nested_iterative_ksp_simultaneously_live_peak",
                    raw_peaks["nested_iterative_ksp"],
                ),
                ("simultaneously_live_peak", raw_peaks["side_inverse"]),
                ("simultaneously_live_component_peak", raw_peaks["component"]),
            )
        )

    summary_counts_pass = all(
        summary_counts_match(payload) for payload in summary_count_payloads
    )
    if not summary_counts_pass:
        errors.append("lifecycle_summary_counts")
    lifecycle_pass = bool(
        not errors
        and boundary_keys == expected_boundaries
        and isinstance(summary_boundaries, list)
        and boundaries == summary_boundaries
        and raw_created
        == {
            "side_inverse": 2,
            "p4_factor": 2,
            "nested_iterative_ksp": 2,
        }
        and raw_peaks
        == {
            "side_inverse": 1,
            "p4_factor": 1,
            "nested_iterative_ksp": 1,
            "component": 2,
        }
        and isinstance(side_setup, Mapping)
        and side_setup.get("side_setup_schedule") == expected_schedule
        and side_setup.get("order") == ["bottom", "top"]
    )
    if not lifecycle_pass and "lifecycle_order" not in errors:
        errors.append("sequential_lifecycle_contract")
    return {
        "pass": lifecycle_pass,
        "path": str(marker_path),
        "errors": errors,
        "boundaries": boundaries,
        "boundary_keys": boundary_keys,
        "boundary_time_pass": boundary_time_pass,
        "boundary_counts_pass": boundary_counts_pass,
        "identities": identities,
        "identity_values_pass": identity_values_passed,
        "identity_order_pass": identity_order_pass,
        "cleanup": cleanup,
        "cleanup_pass": cleanup_pass,
        "created": raw_created,
        "peaks": raw_peaks,
        "summary_counts_pass": summary_counts_pass,
    }


def _validate_common_layout_equivalence_result(
    consumer_root: Path,
    summary: Mapping[str, Any],
    binding: Mapping[str, Any] | None,
    *,
    expected_side_setup_schedule: str | None,
) -> dict[str, Any]:
    """Validate common-layout evidence without trusting worker summary flags."""

    import numpy as np

    from benchmarks.task041_balh_workflow import (
        _TASK041_REPRESENTATIVE_RHS_EXPECTED,
        TASK041_REPRESENTATIVE_RHS_COUNT,
        TASK041_REPRESENTATIVE_RHS_SCOPE,
        TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
    )

    categories: dict[str, list[str]] = {
        "PAIRING_SETUP_FAILURE": [],
        "NUMERICAL_GATE_FAIL": [],
        "ACTION_EQUIVALENCE_FAIL": [],
        "RESPONSE_SENSITIVITY_UNRESOLVED": [],
    }
    checks: dict[str, Any] = {}

    def add(category: str, message: str) -> None:
        categories[category].append(message)

    def numeric(value: Any) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        )

    def nonnegative(value: Any) -> bool:
        return numeric(value) and float(value) >= 0.0

    def same_number(left: Any, right: Any) -> bool:
        if not numeric(left) or not numeric(right):
            return False
        left_value = float(left)
        right_value = float(right)
        if left_value == right_value:
            return True
        scale = max(abs(left_value), abs(right_value))
        return scale > 0.0 and abs(left_value - right_value) / scale <= 1.0e-12

    def strict_ratio(numerator: float, denominator: float) -> float | None:
        if (
            not math.isfinite(numerator)
            or not math.isfinite(denominator)
            or numerator < 0.0
            or denominator < 0.0
        ):
            return None
        if denominator == 0.0:
            return 0.0 if numerator == 0.0 else None
        return numerator / denominator

    def array_sha(array: Any) -> str:
        value = np.asarray(array)
        if value.size == 0:
            return hashlib.sha256(b"").hexdigest()
        digest = hashlib.sha256()
        if value.flags.c_contiguous:
            view = memoryview(value).cast("B")
            try:
                digest.update(view)
            finally:
                view.release()
        else:
            iterator = np.nditer(
                value,
                flags=["external_loop", "buffered"],
                op_flags=["readonly"],
                buffersize=8192,
            )
            for chunk in iterator:
                digest.update(np.asarray(chunk).tobytes(order="C"))
        return digest.hexdigest()

    common = summary.get("common_layout_equivalence")
    common_map = common if isinstance(common, Mapping) else None
    if common_map is None:
        add("PAIRING_SETUP_FAILURE", "common_layout_equivalence_missing")

    binding_evidence = _task041_representative_immutable_binding(
        summary, binding
    )
    for failure in binding_evidence["failures"]:
        add("PAIRING_SETUP_FAILURE", f"immutable:{failure}")
    expected_entries = binding_evidence["expected_entries"]
    expected_by_ordinal = binding_evidence["expected_by_ordinal"]
    expected_signature = binding_evidence["expected_signature"]
    packet_binding = binding_evidence["packet_binding"]
    expected_packet_sha = binding_evidence["expected_packet_sha"]
    binding_ok = bool(
        expected_side_setup_schedule == TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
        and isinstance(binding, Mapping)
        and binding.get("scope") == TASK041_REPRESENTATIVE_RHS_SCOPE
        and binding.get("comparison_mode") in (None, "common_layout_equivalence")
        and isinstance(expected_entries, list)
        and len(expected_entries) == TASK041_REPRESENTATIVE_RHS_COUNT
        and expected_signature == _TASK041_REPRESENTATIVE_RHS_EXPECTED
    )
    checks["mode_binding"] = binding_ok
    if not binding_ok:
        add("PAIRING_SETUP_FAILURE", "mode_or_manifest_binding")

    source_manifest = (
        common_map.get("source_manifest") if common_map is not None else None
    )
    source_binding_ok = bool(
        binding_evidence["checks"]["probe_manifest_hash"]
        and isinstance(source_manifest, Mapping)
        and isinstance(binding, Mapping)
        and source_manifest.get("path") == binding.get("path")
        and source_manifest.get("sha256") == binding.get("sha256")
        and source_manifest.get("scope") == TASK041_REPRESENTATIVE_RHS_SCOPE
    )
    checks["source_manifest"] = source_binding_ok
    if not source_binding_ok:
        add("PAIRING_SETUP_FAILURE", "source_manifest_binding")

    summary_packet = summary.get("packet")
    packet_binding_ok = bool(
        binding_evidence["checks"]["source_and_packet_identity"]
        and isinstance(packet_binding, Mapping)
        and _valid_sha(expected_packet_sha, 64)
        and isinstance(summary_packet, Mapping)
        and summary_packet.get("manifest_sha256") == expected_packet_sha
        and common_map is not None
        and common_map.get("packet_binding") == packet_binding
    )
    checks["packet_binding"] = packet_binding_ok
    if not packet_binding_ok:
        add("PAIRING_SETUP_FAILURE", "producer_packet_binding")

    variant_binding = (
        summary.get("setup", {}).get("variant_binding")
        if isinstance(summary.get("setup"), Mapping)
        else None
    )
    expected_variant_binding = {
        "source_module": "src.solvers.physical_balanced_same_mesh_transfer",
        "variants": {
            "legacy": {
                "owner_resolution": (
                    "src.solvers.physical_balanced_same_mesh_transfer."
                    "_resolve_owner_candidates"
                ),
                "cell_adjoint": (
                    "src.solvers.physical_balanced_same_mesh_transfer."
                    "SameMeshHcurlOwnerTransfer._apply_adjoint_into_impl"
                ),
                "adjoint_kernel": "explicit_matrix_conjugate_transpose",
            },
            "optimized": {
                "owner_resolution": (
                    "src.solvers.physical_balanced_same_mesh_transfer."
                    "_resolve_owner_candidates_batched"
                ),
                "cell_adjoint": (
                    "src.solvers.physical_balanced_same_mesh_transfer."
                    "_apply_conjugate_transpose_vector"
                ),
                "adjoint_kernel": "conjugate_transpose_identity",
            },
        },
    }
    variant_binding_pass = True
    if not isinstance(variant_binding, Mapping):
        variant_binding_pass = False
    else:
        for side in ("bottom", "top"):
            record = variant_binding.get(side)
            if not isinstance(record, Mapping):
                variant_binding_pass = False
                add("PAIRING_SETUP_FAILURE", f"{side}_variant_binding_missing")
                continue
            if (
                record.get("source_module")
                != expected_variant_binding["source_module"]
                or record.get("source_sha") != summary.get("source_sha")
                or record.get("variants") != expected_variant_binding["variants"]
            ):
                variant_binding_pass = False
                add("PAIRING_SETUP_FAILURE", f"{side}_variant_binding_mismatch")
    checks["variant_binding"] = variant_binding_pass

    pair_path = consumer_root / "numerical_output" / (
        "common_layout_equivalence_pairs.jsonl"
    )
    pairs: dict[int, Mapping[str, Any]] = {}
    if pair_path.is_file():
        try:
            with pair_path.open(encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        add(
                            "PAIRING_SETUP_FAILURE",
                            f"pair_line_{line_number}_invalid_json",
                        )
                        continue
                    if not isinstance(row, Mapping) or type(row.get("ordinal")) is not int:
                        add(
                            "PAIRING_SETUP_FAILURE",
                            f"pair_line_{line_number}_record",
                        )
                        continue
                    ordinal = int(row["ordinal"])
                    if ordinal not in expected_by_ordinal:
                        add(
                            "PAIRING_SETUP_FAILURE",
                            f"pair_ordinal_{ordinal}_unknown",
                        )
                    elif ordinal in pairs:
                        add(
                            "PAIRING_SETUP_FAILURE",
                            f"pair_ordinal_{ordinal}_duplicated",
                        )
                    else:
                        pairs[ordinal] = row
        except OSError as exc:
            add("PAIRING_SETUP_FAILURE", f"pair_read_{type(exc).__name__}")
    else:
        add("PAIRING_SETUP_FAILURE", "pair_records_missing")
    for ordinal in expected_by_ordinal:
        if ordinal not in pairs:
            add("PAIRING_SETUP_FAILURE", f"pair_ordinal_{ordinal}_missing")
    checks["pair_records"] = {
        "path": str(pair_path),
        "count": len(pairs),
        "expected": TASK041_REPRESENTATIVE_RHS_COUNT,
    }

    def metadata_array(value: Any, label: str) -> bool:
        if not isinstance(value, Mapping):
            add("PAIRING_SETUP_FAILURE", f"{label}_metadata_missing")
            return False
        if not isinstance(value.get("name"), str):
            add("PAIRING_SETUP_FAILURE", f"{label}_name")
            return False
        if not _valid_sha(value.get("sha256"), 64):
            add("PAIRING_SETUP_FAILURE", f"{label}_sha")
            return False
        if not isinstance(value.get("hash_status"), str) or not value[
            "hash_status"
        ].startswith("measured"):
            add("PAIRING_SETUP_FAILURE", f"{label}_hash_not_measured")
            return False
        shape = value.get("shape")
        nbytes = value.get("nbytes")
        return_value = (
            isinstance(shape, list)
            and all(type(item) is int and item >= 0 for item in shape)
            and type(nbytes) is int
            and nbytes >= 0
        )
        if not return_value:
            add("PAIRING_SETUP_FAILURE", f"{label}_shape_or_bytes")
        return return_value

    required_held_objects = (
        "side_A",
        "side_inverse",
        "p4_factor",
        "research_factor",
        "p4_matrix",
        "p4_factor_ksp",
        "p4_factor_matrix",
        "nested_ksp",
        "h6",
        "h6_matrix",
        "mesh",
        "side_system",
    )

    def held_object(value: Any, label: str) -> bool:
        if not isinstance(value, Mapping):
            add("PAIRING_SETUP_FAILURE", f"{label}_held_object_missing")
            return False
        if label.endswith("p4_factor_ksp") and value.get("live") is False:
            # factor_only_storage deliberately destroys this KSP and retains
            # the factor matrix.  Validate that explicit terminal record
            # before the generic live-object identity requirement below.
            if (
                value.get("reason") != "factor_only_storage"
                or value.get("python_id") is not None
                or value.get("handle") is not None
                or value.get("petsc_handle") is not None
                or value.get("cpp_object") is not None
            ):
                add("PAIRING_SETUP_FAILURE", f"{label}_not_live")
                return False
            return True
        if label.endswith("p4_factor_matrix") and value.get("live") is False:
            # A factor-only run is valid only when the retained factor matrix
            # is still represented by its real PETSc identity.  The writer
            # omits ``live`` for a live PETSc object; an explicit false record
            # is therefore a failed retention claim, not a fallback state.
            add("PAIRING_SETUP_FAILURE", f"{label}_not_live")
            return False
        if not isinstance(value.get("kind"), str):
            add("PAIRING_SETUP_FAILURE", f"{label}_held_object_kind")
            return False
        if not any(
            key in value and value.get(key) is not None
            for key in ("python_id", "petsc_handle", "handle", "cpp_object")
        ):
            add("PAIRING_SETUP_FAILURE", f"{label}_held_object_identity")
            return False
        if label.endswith("p4_factor_ksp") and value.get("live") not in (
            None,
            True,
        ):
            add("PAIRING_SETUP_FAILURE", f"{label}_live_unknown")
            return False
        if label.endswith("nested_ksp") and (
            value.get("live") is False
            or not any(
                key in value and value.get(key) is not None
                for key in ("petsc_handle", "handle", "cpp_object")
            )
        ):
            add("PAIRING_SETUP_FAILURE", f"{label}_handle_missing")
            return False
        return True

    def communicator(value: Any, label: str, expected_rank: int) -> bool:
        if not isinstance(value, Mapping):
            add("PAIRING_SETUP_FAILURE", f"{label}_communicator_missing")
            return False
        valid = all(
            type(value.get(field)) is int and int(value[field]) >= 0
            for field in ("rank", "size", "fortran_handle")
        )
        valid = valid and value.get("rank") == expected_rank and value.get("size") == 8
        if not valid:
            add("PAIRING_SETUP_FAILURE", f"{label}_communicator_shape")
        return valid

    def validate_layout(side: str) -> dict[str, Any] | None:
        path = layout_root / f"{side}_layout.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            add("PAIRING_SETUP_FAILURE", f"{side}_layout_read")
            return None
        if not isinstance(payload, Mapping):
            add("PAIRING_SETUP_FAILURE", f"{side}_layout_record")
            return None
        by_rank = payload.get("by_rank")
        instance = payload.get("layout_instance_id")
        audit_identity_path = (
            consumer_root / "numerical_output" / "common_layout_equivalence_audits.jsonl"
        ).resolve()
        expected_instance = hashlib.sha256(
            f"{audit_identity_path}|{side}|task041.common_layout_equivalence.layout.v1".encode()
        ).hexdigest()
        valid = (
            payload.get("schema")
            == "task041.common_layout_equivalence.layout.v1"
            and payload.get("side") == side
            and payload.get("comm_size") == 8
            and isinstance(instance, str)
            and bool(instance)
            and isinstance(by_rank, list)
            and len(by_rank) == 8
            and all(isinstance(row, Mapping) for row in by_rank)
            and [row.get("rank") for row in by_rank] == list(range(8))
            and _valid_sha(payload.get("layout_identity_sha256"), 64)
            and instance == expected_instance
        )
        if valid:
            try:
                canonical = json.dumps(
                    by_rank, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
                valid = hashlib.sha256(canonical).hexdigest() == payload[
                    "layout_identity_sha256"
                ]
            except (TypeError, ValueError):
                valid = False
        if not valid:
            add("PAIRING_SETUP_FAILURE", f"{side}_layout_shape_or_canonical_sha")
        required = (
            "communicator",
            "communicators",
            "ownership_range",
            "ownership",
            "held_objects",
            "dofmaps",
            "mesh_layout",
            "mpc_layout",
            "layout_arrays",
            "transfer_identity",
            "operator_identity",
        )
        if isinstance(by_rank, list):
            for row_number, row in enumerate(by_rank):
                if not isinstance(row, Mapping):
                    continue
                row_valid = True
                row_instance = row.get("layout_instance_id")
                if row_instance != instance:
                    add("PAIRING_SETUP_FAILURE", f"{side}_rank_{row_number}_instance")
                    row_valid = False
                for field in required:
                    if field not in row:
                        add(
                            "PAIRING_SETUP_FAILURE",
                            f"{side}_rank_{row_number}_{field}_missing",
                        )
                        row_valid = False
                row_valid = communicator(
                    row.get("communicator"),
                    f"{side}_rank_{row_number}_outer",
                    row_number,
                ) and row_valid
                communicators = row.get("communicators")
                if isinstance(communicators, Mapping):
                    for name in ("outer", "transfer", "side_operator", "inverse"):
                        row_valid = communicator(
                            communicators.get(name),
                            f"{side}_rank_{row_number}_{name}",
                            row_number,
                        ) and row_valid
                    compare = communicators.get("compare")
                    if not isinstance(compare, Mapping) or set(compare) != {
                        "outer_transfer",
                        "transfer_side_operator",
                        "side_operator_inverse",
                    } or any(
                        type(value) is not int or value not in (0, 1)
                        for value in compare.values()
                    ):
                        add(
                            "PAIRING_SETUP_FAILURE",
                            f"{side}_rank_{row_number}_communicator_compare",
                        )
                        row_valid = False
                else:
                    add(
                        "PAIRING_SETUP_FAILURE",
                        f"{side}_rank_{row_number}_communicators",
                    )
                    row_valid = False
                held = row.get("held_objects")
                if isinstance(held, Mapping):
                    for name in required_held_objects:
                        row_valid = held_object(
                            held.get(name),
                            f"{side}_rank_{row_number}_{name}",
                        ) and row_valid
                else:
                    row_valid = False
                mesh_layout = row.get("mesh_layout")
                if isinstance(mesh_layout, Mapping):
                    for name in (
                        "geometry",
                        "geometry_dofmap",
                        "cell_permutation_info",
                    ):
                        row_valid = metadata_array(
                            mesh_layout.get(name),
                            f"{side}_rank_{row_number}_{name}",
                        ) and row_valid
                else:
                    add(
                        "PAIRING_SETUP_FAILURE",
                        f"{side}_rank_{row_number}_mesh_layout",
                    )
                    row_valid = False
                mpc_layout = row.get("mpc_layout")
                if isinstance(mpc_layout, Mapping):
                    for mpc_name in ("fine", "coarse"):
                        mpc = mpc_layout.get(mpc_name)
                        if not isinstance(mpc, Mapping):
                            add(
                                "PAIRING_SETUP_FAILURE",
                                f"{side}_rank_{row_number}_{mpc_name}_mpc",
                            )
                            row_valid = False
                            continue
                        for name in ("slaves", "coefficients", "offsets"):
                            row_valid = metadata_array(
                                mpc.get(name),
                                f"{side}_rank_{row_number}_{mpc_name}_{name}",
                            ) and row_valid
                        if not _valid_sha(mpc.get("masters_links_sha256"), 64):
                            add(
                                "PAIRING_SETUP_FAILURE",
                                f"{side}_rank_{row_number}_{mpc_name}_masters",
                            )
                            row_valid = False
                else:
                    add(
                        "PAIRING_SETUP_FAILURE",
                        f"{side}_rank_{row_number}_mpc_layout",
                    )
                    row_valid = False
                layout_arrays = row.get("layout_arrays")
                if not isinstance(layout_arrays, list) or not layout_arrays:
                    add(
                        "PAIRING_SETUP_FAILURE",
                        f"{side}_rank_{row_number}_layout_arrays",
                    )
                    row_valid = False
                else:
                    for index, array in enumerate(layout_arrays):
                        row_valid = metadata_array(
                            array,
                            f"{side}_rank_{row_number}_layout_array_{index}",
                        ) and row_valid
                if not isinstance(row.get("transfer_identity"), Mapping):
                    add(
                        "PAIRING_SETUP_FAILURE",
                        f"{side}_rank_{row_number}_transfer_identity",
                    )
                    row_valid = False
                elif "owner_row_authority" not in row["transfer_identity"]:
                    add(
                        "PAIRING_SETUP_FAILURE",
                        f"{side}_rank_{row_number}_owner_row_authority",
                    )
                    row_valid = False
                if not isinstance(row.get("operator_identity"), Mapping):
                    add(
                        "PAIRING_SETUP_FAILURE",
                        f"{side}_rank_{row_number}_operator_identity",
                    )
                    row_valid = False
                if not isinstance(row.get("ownership"), Mapping) or not isinstance(
                    row.get("dofmaps"), Mapping
                ):
                    add(
                        "PAIRING_SETUP_FAILURE",
                        f"{side}_rank_{row_number}_ownership_or_dofmaps",
                    )
                    row_valid = False
                if not row_valid:
                    valid = False
        if not valid:
            return None
        return dict(payload)

    layout_root = consumer_root / "numerical_output" / "common_layout_equivalence"
    layouts: dict[str, Mapping[str, Any]] = {}
    for side in ("bottom", "top"):
        payload = validate_layout(side)
        if payload is not None:
            layouts[side] = payload
    checks["layout_files"] = {
        side: {
            "path": str(layout_root / f"{side}_layout.json"),
            "layout_identity_sha256": payload.get("layout_identity_sha256"),
            "layout_instance_id": payload.get("layout_instance_id"),
        }
        for side, payload in layouts.items()
    }

    audit_path = consumer_root / "numerical_output" / (
        "common_layout_equivalence_audits.jsonl"
    )
    raw_audits: dict[tuple[int, str], tuple[Mapping[str, Any], Mapping[str, Any], int]] = {}
    if audit_path.is_file():
        try:
            with audit_path.open(encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        add(
                            "PAIRING_SETUP_FAILURE",
                            f"audit_line_{line_number}_invalid_json",
                        )
                        continue
                    if not isinstance(row, Mapping) or not isinstance(
                        row.get("audit"), Mapping
                    ):
                        add(
                            "PAIRING_SETUP_FAILURE",
                            f"audit_line_{line_number}_record",
                        )
                        continue
                    audit = row["audit"]
                    ordinal = audit.get("representative_ordinal")
                    variant = audit.get("comparison_variant")
                    if type(ordinal) is not int or variant not in {
                        "legacy",
                        "optimized",
                    }:
                        add(
                            "PAIRING_SETUP_FAILURE",
                            f"audit_line_{line_number}_key",
                        )
                        continue
                    key = (int(ordinal), str(variant))
                    if ordinal not in expected_by_ordinal:
                        add("PAIRING_SETUP_FAILURE", f"audit_{key}_unknown")
                    elif key in raw_audits:
                        add("PAIRING_SETUP_FAILURE", f"audit_{key}_duplicated")
                    else:
                        raw_audits[key] = (row, audit, line_number)
        except OSError as exc:
            add("PAIRING_SETUP_FAILURE", f"audit_read_{type(exc).__name__}")
    else:
        add("PAIRING_SETUP_FAILURE", "common_audits_missing")
    expected_audit_keys = {
        (ordinal, variant)
        for ordinal in expected_by_ordinal
        for variant in ("legacy", "optimized")
    }
    for key in expected_audit_keys - set(raw_audits):
        add("PAIRING_SETUP_FAILURE", f"audit_{key}_missing")
    if set(raw_audits) != expected_audit_keys:
        add("PAIRING_SETUP_FAILURE", "audit_key_set")
    checks["audits"] = {
        "path": str(audit_path),
        "count": len(raw_audits),
        "expected": 16,
    }

    def check_ksp_contract(audit: Mapping[str, Any], label: str) -> bool:
        contract = audit.get("ksp_contract")
        if not isinstance(contract, Mapping):
            add("PAIRING_SETUP_FAILURE", f"{label}_ksp_contract_missing")
            return False
        if contract.get("collective_pass") is not True:
            add("NUMERICAL_GATE_FAIL", f"{label}_ksp_collective")
        actual = contract.get("actual")
        if not isinstance(actual, Mapping):
            add("PAIRING_SETUP_FAILURE", f"{label}_ksp_actual_missing")
            return False
        expected_actual = {
            "type": "fgmres",
            "pc_type": "python",
            "pc_side_label": "RIGHT",
            "norm_type_label": "UNPRECONDITIONED",
            "restart": 32,
            "rtol": 1.0e-2,
            "atol": 0.0,
            "max_it": 128,
            "initial_guess_nonzero": False,
        }
        for field, expected in expected_actual.items():
            actual_value = actual.get(field)
            if field in {"rtol", "atol"}:
                equal = same_number(actual_value, expected)
            else:
                equal = actual_value == expected
            if not equal:
                add("NUMERICAL_GATE_FAIL", f"{label}_ksp_{field}")
        for field in ("pc_side", "norm_type"):
            if type(actual.get(field)) is not int:
                add("NUMERICAL_GATE_FAIL", f"{label}_ksp_{field}_enum")
            expected_value = (
                contract.get("expected", {}).get(field)
                if isinstance(contract.get("expected"), Mapping)
                else None
            )
            if type(expected_value) is not int or actual.get(field) != expected_value:
                add("NUMERICAL_GATE_FAIL", f"{label}_ksp_{field}_value")
        recorded_checks = contract.get("checks")
        if not isinstance(recorded_checks, Mapping):
            add("PAIRING_SETUP_FAILURE", f"{label}_ksp_checks_missing")
        else:
            recorded_fields = (
                "type",
                "pc_type",
                "pc_side",
                "norm_type",
                "restart",
                "rtol",
                "atol",
                "max_it",
                "initial_guess_nonzero",
            )
            for field in recorded_fields:
                if recorded_checks.get(field) is not True:
                    add("NUMERICAL_GATE_FAIL", f"{label}_ksp_check_{field}")
        history = audit.get("iteration_history")
        if not isinstance(history, list) or len(history) > 129:
            add("PAIRING_SETUP_FAILURE", f"{label}_history_missing_or_long")
        elif any(
            not isinstance(item, Mapping)
            or type(item.get("iteration")) is not int
            or item["iteration"] < 0
            or item["iteration"] > 128
            for item in history
        ):
            add("NUMERICAL_GATE_FAIL", f"{label}_history_iteration")
        else:
            for index, item in enumerate(history):
                reported = item.get("reported_residual")
                if isinstance(reported, str):
                    if reported not in {"nan", "inf", "-inf"}:
                        add(
                            "PAIRING_SETUP_FAILURE",
                            f"{label}_history_{index}_residual_type",
                        )
                    else:
                        add(
                            "NUMERICAL_GATE_FAIL",
                            f"{label}_history_{index}_nonfinite",
                        )
                elif not numeric(reported) or float(reported) < 0.0:
                    add(
                        "NUMERICAL_GATE_FAIL",
                        f"{label}_history_{index}_residual",
                    )
        return True

    def check_raw_audit(
        ordinal: int,
        variant: str,
        entry: Mapping[str, Any],
        row: Mapping[str, Any],
        audit: Mapping[str, Any],
    ) -> None:
        label = f"ordinal_{ordinal}_{variant}"
        if row.get("phase") != "common_layout_equivalence":
            add("PAIRING_SETUP_FAILURE", f"{label}_phase")
        if row.get("side") != entry.get("side"):
            add("PAIRING_SETUP_FAILURE", f"{label}_side")
        for field, expected in (
            ("representative_ordinal", ordinal),
            ("source_audit_index", entry.get("audit_index")),
            ("formal_column", entry.get("formal_column")),
            ("branch_ordinal", entry.get("branch_ordinal")),
            ("comparison_variant", variant),
            ("execution_variant", variant),
        ):
            if audit.get(field) != expected:
                add("PAIRING_SETUP_FAILURE", f"{label}_{field}")
        required = (
            "status",
            "reason",
            "iterations",
            "ksp_positive",
            "explicit_true_target_reached",
            "rhs_norm",
            "residual_norm",
            "relative_residual",
            "ksp_rtol",
            "ksp_max_it",
            "ksp_contract",
            "iteration_history",
        )
        missing = [field for field in required if field not in audit]
        for field in missing:
            add("PAIRING_SETUP_FAILURE", f"{label}_{field}_missing")
        check_ksp_contract(audit, label)
        rhs_norm = audit.get("rhs_norm")
        residual_norm = audit.get("residual_norm")
        raw_relative = audit.get("relative_residual")
        if not nonnegative(rhs_norm):
            add("NUMERICAL_GATE_FAIL", f"{label}_rhs_norm")
        if not nonnegative(residual_norm):
            add("NUMERICAL_GATE_FAIL", f"{label}_residual_norm")
        if not nonnegative(raw_relative):
            add("NUMERICAL_GATE_FAIL", f"{label}_relative_residual")
        if nonnegative(rhs_norm) and nonnegative(residual_norm):
            recomputed = strict_ratio(float(residual_norm), float(rhs_norm))
            if recomputed is None or recomputed > 1.0e-2:
                add("NUMERICAL_GATE_FAIL", f"{label}_recomputed_residual_gate")
            elif not same_number(raw_relative, recomputed):
                add("NUMERICAL_GATE_FAIL", f"{label}_relative_residual_mismatch")
        if not same_number(audit.get("ksp_rtol"), 1.0e-2):
            add("NUMERICAL_GATE_FAIL", f"{label}_rtol")
        if audit.get("ksp_max_it") != 128:
            add("NUMERICAL_GATE_FAIL", f"{label}_max_it")
        iterations = audit.get("iterations")
        if type(iterations) is not int or iterations < 0 or iterations > 128:
            add("NUMERICAL_GATE_FAIL", f"{label}_iterations")
        if rhs_norm == 0.0:
            zero_ok = (
                audit.get("status") == "ZERO_RHS_EXACT"
                and audit.get("reason") is None
                and audit.get("ksp_positive") is False
                and audit.get("explicit_true_target_reached") is True
                and iterations == 0
            )
            if not zero_ok:
                add("NUMERICAL_GATE_FAIL", f"{label}_zero_rhs_contract")
        else:
            nonzero_ok = (
                audit.get("status") == "KSP_CONVERGED"
                and type(audit.get("reason")) is int
                and audit.get("reason") > 0
                and audit.get("ksp_positive") is True
                and audit.get("explicit_true_target_reached") is True
            )
            if not nonzero_ok:
                add("NUMERICAL_GATE_FAIL", f"{label}_solve_status")
        counts = audit.get("counts")
        delta = counts.get("delta") if isinstance(counts, Mapping) else None
        for field in ("pc", "Q", "H6", "A6", "P", "PH_audit", "p4_backsolve"):
            value = delta.get(field) if isinstance(delta, Mapping) else None
            if type(value) is not int or value < 0:
                add("PAIRING_SETUP_FAILURE", f"{label}_count_{field}")
            elif rhs_norm != 0.0 and value <= 0:
                add("NUMERICAL_GATE_FAIL", f"{label}_count_{field}_zero")
        if row.get("status") != audit.get("status") or row.get("reason") != audit.get(
            "reason"
        ):
            add("PAIRING_SETUP_FAILURE", f"{label}_row_summary_mismatch")

    for ordinal, entry in expected_by_ordinal.items():
        for variant in ("legacy", "optimized"):
            raw = raw_audits.get((ordinal, variant))
            if raw is not None:
                check_raw_audit(ordinal, variant, entry, raw[0], raw[1])

    def check_c3_facts(value: Mapping[str, Any], label: str) -> bool:
        facts_ok = True
        input_hashes = value.get("input_hashes")
        if not isinstance(input_hashes, Mapping):
            add("PAIRING_SETUP_FAILURE", f"{label}_input_hashes")
            return False
        for variant in ("legacy", "optimized"):
            record = input_hashes.get(variant)
            facts = record.get("last_action_facts") if isinstance(record, Mapping) else None
            if not isinstance(facts, Mapping):
                add("PAIRING_SETUP_FAILURE", f"{label}_{variant}_last_action_facts")
                facts_ok = False
                continue
            coupling = facts.get("coupling_last_apply_facts")
            balance = (
                coupling.get("initial", {}).get("balance")
                if isinstance(coupling, Mapping)
                and isinstance(coupling.get("initial"), Mapping)
                else None
            )
            if not isinstance(balance, Mapping):
                add("PAIRING_SETUP_FAILURE", f"{label}_{variant}_balance_facts")
                facts_ok = False
            else:
                balance_norm = balance.get("norm")
                operation_scale = balance.get("operation_scale")
                balance_relative = balance.get("relative")
                balance_limit = balance.get("limit")
                recomputed_balance = (
                    float(balance_norm)
                    / max(float(operation_scale), np.finfo(float).tiny)
                    if nonnegative(balance_norm) and nonnegative(operation_scale)
                    else None
                )
                balance_ok = bool(
                    recomputed_balance is not None
                    and math.isfinite(recomputed_balance)
                    and nonnegative(balance_relative)
                    and same_number(balance_limit, 1.0e-8)
                    and same_number(balance_relative, recomputed_balance)
                    and recomputed_balance <= 1.0e-8
                )
                if not balance_ok:
                    add("NUMERICAL_GATE_FAIL", f"{label}_{variant}_balance_gate")
                    facts_ok = False
            p4_solve = facts.get("p4_last_solve")
            if not isinstance(p4_solve, Mapping):
                add("PAIRING_SETUP_FAILURE", f"{label}_{variant}_p4_facts")
                facts_ok = False
                continue
            rhs_norm = p4_solve.get("rhs_norm")
            residual_norm = p4_solve.get("residual_norm")
            physical_residual_norm = p4_solve.get("physical_residual_norm")
            tolerance = p4_solve.get("residual_tolerance")
            relative = p4_solve.get("relative_residual")
            physical_relative = p4_solve.get("physical_relative_residual")
            backsolve_count = p4_solve.get("backsolve_count")
            refinement_count = p4_solve.get("refinement_count")
            same_factor_refinement = p4_solve.get("same_factor_refinement")
            recomputed = (
                strict_ratio(float(residual_norm), float(rhs_norm))
                if nonnegative(rhs_norm) and nonnegative(residual_norm)
                else None
            )
            backsolve_ok = bool(
                type(backsolve_count) is int
                and 1 <= backsolve_count <= 3
                and type(refinement_count) is int
                and 0 <= refinement_count <= 2
                and backsolve_count == refinement_count + 1
                and same_factor_refinement is (backsolve_count > 1)
            )
            p4_ok = bool(
                p4_solve.get("status") == "passed"
                and nonnegative(rhs_norm)
                and nonnegative(residual_norm)
                and nonnegative(physical_residual_norm)
                and same_number(residual_norm, physical_residual_norm)
                and nonnegative(tolerance)
                and same_number(tolerance, 1.0e-10)
                and recomputed is not None
                and nonnegative(relative)
                and nonnegative(physical_relative)
                and same_number(relative, recomputed)
                and same_number(physical_relative, recomputed)
                and recomputed <= 1.0e-10
                and backsolve_ok
            )
            if not p4_ok:
                add("NUMERICAL_GATE_FAIL", f"{label}_{variant}_p4_gate")
                facts_ok = False
        return facts_ok

    def check_c3_action(
        side: str,
        group: str,
        value: Any,
    ) -> None:
        label = f"{side}_{group}"
        if not isinstance(value, Mapping):
            add("PAIRING_SETUP_FAILURE", f"{label}_missing")
            return
        threshold = 1.0e-8 if group == "PC" else 1.0e-11
        if not same_number(value.get("threshold"), threshold):
            add("PAIRING_SETUP_FAILURE", f"{label}_threshold")
        absolute = value.get("absolute")
        legacy_norm = value.get("legacy_norm")
        optimized_norm = value.get("optimized_norm")
        if not nonnegative(absolute) or not nonnegative(legacy_norm) or not nonnegative(
            optimized_norm
        ):
            add("NUMERICAL_GATE_FAIL", f"{label}_norm")
        else:
            relative = strict_ratio(
                float(absolute),
                max(float(legacy_norm), float(optimized_norm)),
            )
            if relative is None:
                add("NUMERICAL_GATE_FAIL", f"{label}_zero_denominator")
            elif not same_number(value.get("relative"), relative):
                add("NUMERICAL_GATE_FAIL", f"{label}_relative_recompute")
            elif relative > threshold:
                add("ACTION_EQUIVALENCE_FAIL", f"{label}_relative_gate")
        if value.get("finite") is not True:
            add("NUMERICAL_GATE_FAIL", f"{label}_finite")
        if value.get("input_unchanged") is not True:
            add("PAIRING_SETUP_FAILURE", f"{label}_input_changed")
        facts_ok = check_c3_facts(value, label) if group == "PC" else True
        independently_pass = bool(
            value.get("finite") is True
            and value.get("input_unchanged") is True
            and facts_ok
            and nonnegative(absolute)
            and nonnegative(legacy_norm)
            and nonnegative(optimized_norm)
            and strict_ratio(
                float(absolute),
                max(float(legacy_norm), float(optimized_norm)),
            )
            is not None
            and strict_ratio(
                float(absolute),
                max(float(legacy_norm), float(optimized_norm)),
            )
            <= threshold
        )
        if value.get("pass") is not independently_pass:
            add("PAIRING_SETUP_FAILURE", f"{label}_pass_summary")
        input_hashes = value.get("input_hashes")
        if not isinstance(input_hashes, Mapping):
            add("PAIRING_SETUP_FAILURE", f"{label}_input_hashes")
        else:
            for variant in ("legacy", "optimized"):
                record = input_hashes.get(variant)
                if not isinstance(record, Mapping):
                    add("PAIRING_SETUP_FAILURE", f"{label}_{variant}_input_hashes")
                    continue
                before = record.get("before")
                after = record.get("after")
                if (
                    not isinstance(before, Mapping)
                    or not isinstance(after, Mapping)
                    or record.get("unchanged") is not True
                    or before != after
                ):
                    add(
                        "PAIRING_SETUP_FAILURE",
                        f"{label}_{variant}_input_unchanged",
                    )

    setup = summary.get("setup")
    setup_map = setup if isinstance(setup, Mapping) else None
    admission = (
        setup_map.get("admission_audit") if setup_map is not None else None
    )
    admission_map = admission if isinstance(admission, Mapping) else None
    sides = admission_map.get("sides") if admission_map is not None else None
    if not isinstance(sides, Mapping) or set(sides) != {"bottom", "top"}:
        add("PAIRING_SETUP_FAILURE", "admission_sides")
    else:
        for side in ("bottom", "top"):
            side_admission = sides.get(side)
            if not isinstance(side_admission, Mapping):
                add("PAIRING_SETUP_FAILURE", f"{side}_admission_missing")
                continue
            original = side_admission.get("admission")
            if not isinstance(original, Mapping) or original.get("pass") is not True:
                add("NUMERICAL_GATE_FAIL", f"{side}_admission_gate")
            side_pc = side_admission.get("balanced_pc")
            if not isinstance(side_pc, Mapping):
                add("PAIRING_SETUP_FAILURE", f"{side}_balanced_pc_missing")
            else:
                for group in ("P", "PH", "PC"):
                    check_c3_action(side, group, side_pc.get(group))
    lifecycle = _task041_sequential_lifecycle_evidence(
        consumer_root,
        setup_map,
        expected_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
    )
    checks["sequential_lifecycle"] = lifecycle
    if lifecycle.get("pass") is not True:
        for error in lifecycle.get("errors", ["lifecycle_invalid"]):
            add("PAIRING_SETUP_FAILURE", f"lifecycle:{error}")

    global_identity = (
        admission_map.get("global_operator_identity")
        if admission_map is not None
        else None
    )
    raw_identity_checks = {
        row["check"].get("label"): row["check"]
        for row in lifecycle.get("identities", [])
        if isinstance(row, Mapping)
        and isinstance(row.get("check"), Mapping)
        and isinstance(row["check"].get("label"), str)
    }
    recorded_identity_checks = (
        global_identity.get("checks")
        if isinstance(global_identity, Mapping)
        else None
    )
    identity_contract_ok = bool(
        isinstance(global_identity, Mapping)
        and isinstance(recorded_identity_checks, Mapping)
        and set(recorded_identity_checks) == set(raw_identity_checks)
        and all(
            recorded_identity_checks.get(label) == check
            for label, check in raw_identity_checks.items()
        )
        and global_identity.get("threshold") == 1.0e-12
        and global_identity.get("pass") is True
        and lifecycle.get("identity_values_pass") is True
    )
    if not identity_contract_ok:
        add("NUMERICAL_GATE_FAIL", "global_identity_raw_checks")
    checks["global_identity"] = {
        "recorded": global_identity,
        "raw_check_count": len(raw_identity_checks),
        "pass": identity_contract_ok,
    }

    matrix = summary.get("matrix_inventory")
    after_p4 = matrix.get("p4_factor_count_after_cleanup") if isinstance(
        matrix, Mapping
    ) else None
    after_nested = (
        matrix.get("nested_iterative_ksp_count_after_cleanup")
        if isinstance(matrix, Mapping)
        else None
    )
    matrix_ok = bool(
        isinstance(matrix, Mapping)
        and matrix.get("qep_calls") == 0
        and matrix.get("consumer_qep_required") is False
        and matrix.get("p6_factor_count") == 0
        and matrix.get("global_direct_factor_count") == 0
        and isinstance(after_p4, Mapping)
        and set(after_p4) == {"bottom", "top"}
        and all(type(value) is int and value == 0 for value in after_p4.values())
        and isinstance(after_nested, Mapping)
        and set(after_nested) == {"bottom", "top"}
        and all(
            type(value) is int and value == 0 for value in after_nested.values()
        )
    )
    checks["matrix_cleanup"] = matrix_ok
    if not matrix_ok:
        add("PAIRING_SETUP_FAILURE", "matrix_or_component_cleanup")
    candidate_inventory = (
        setup_map.get("candidate_inventory") if setup_map is not None else None
    )
    candidate_ok = bool(
        isinstance(candidate_inventory, Mapping)
        and candidate_inventory.get("p6_factor_count") == 0
        and candidate_inventory.get("global_direct_factor_count") == 0
        and candidate_inventory.get("modal_block") == "representative_rhs_only"
        and candidate_inventory.get("approximate_preconditioner_only") is True
    )
    if not candidate_ok:
        add("PAIRING_SETUP_FAILURE", "common_candidate_inventory")

    def read_packet_metadata(
        label: str,
        artifact: Any,
        expected_identity: Mapping[str, Any],
        rank_records: Any = None,
    ) -> dict[str, Any] | None:
        ok = True

        def bad(reason: str) -> None:
            nonlocal ok
            ok = False
            add("PAIRING_SETUP_FAILURE", f"{label}:{reason}")

        if not isinstance(artifact, Mapping):
            bad("artifact_missing")
            return None
        manifest_value = artifact.get("manifest")
        expected_manifest_sha = artifact.get("manifest_sha256")
        if not isinstance(manifest_value, str) or not _valid_sha(
            expected_manifest_sha, 64
        ):
            bad("manifest_reference")
            return None
        manifest_path = Path(manifest_value)
        try:
            manifest_bytes = manifest_path.read_bytes()
            manifest = json.loads(manifest_bytes)
        except (OSError, json.JSONDecodeError):
            bad("manifest_read")
            return None
        if not isinstance(manifest, Mapping):
            bad("manifest_record")
            return None
        actual_manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
        if actual_manifest_sha != expected_manifest_sha:
            bad("manifest_hash")
        identity = manifest.get("identity")
        identity_sha = manifest.get("identity_sha256")
        try:
            identity_bytes = json.dumps(
                identity, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            actual_identity_sha = hashlib.sha256(identity_bytes).hexdigest()
        except (TypeError, ValueError):
            actual_identity_sha = None
        if (
            not isinstance(identity, Mapping)
            or identity != dict(expected_identity)
            or not _valid_sha(identity_sha, 64)
            or actual_identity_sha != identity_sha
            or identity_sha != artifact.get("identity_sha256")
        ):
            bad("identity")
        if artifact.get("schema") not in (None, manifest.get("schema")):
            bad("artifact_schema")
        shards = manifest.get("shards")
        shard_by_rank: dict[int, Mapping[str, Any]] = {}
        if not isinstance(shards, list) or len(shards) != 8:
            bad("shard_count")
        else:
            for row in shards:
                rank = row.get("rank") if isinstance(row, Mapping) else None
                if type(rank) is not int or rank in shard_by_rank:
                    bad("shard_ranks")
                    continue
                shard_by_rank[rank] = row
        if set(shard_by_rank) != set(range(8)):
            bad("shard_rank_set")
        if (
            manifest.get("schema") != "myfenics.full3d.pre_recovery_packet.v1"
            or manifest.get("rank_count") != 8
        ):
            bad("packet_schema")
        expected_start = 0
        shard_meta: dict[int, dict[str, Any]] = {}
        for rank in range(8):
            shard = shard_by_rank.get(rank)
            if shard is None:
                continue
            ownership = shard.get("ownership_range")
            size = shard.get("size")
            if (
                not isinstance(ownership, list)
                or len(ownership) != 2
                or any(type(value) is not int for value in ownership)
                or type(size) is not int
                or size < 0
            ):
                bad(f"rank_{rank}_ownership")
                continue
            start, end = (int(value) for value in ownership)
            if start != expected_start or end < start or end - start != size:
                bad(f"rank_{rank}_ownership_contiguity")
            expected_start = end
            shard_path_value = shard.get("path")
            shard_path = (
                manifest_path.parent / shard_path_value
                if isinstance(shard_path_value, str)
                else None
            )
            if (
                shard_path is None
                or Path(shard_path_value).is_absolute()
                or ".." in Path(shard_path_value).parts
                or not _valid_sha(shard.get("sha256"), 64)
                or not shard_path.is_file()
            ):
                bad(f"rank_{rank}_shard_metadata")
                continue
            try:
                if _sha256_file(shard_path) != shard["sha256"]:
                    bad(f"rank_{rank}_shard_hash")
            except OSError:
                bad(f"rank_{rank}_shard_read")
            shard_meta[rank] = {
                "ownership": (start, end),
                "size": size,
                "path": shard_path,
                "path_value": shard_path_value,
                "sha256": shard["sha256"],
            }
        if type(manifest.get("global_size")) is not int or expected_start != int(
            manifest.get("global_size", -1)
        ):
            bad("global_size")
        rank_record_by_rank: dict[int, Mapping[str, Any]] = {}
        if rank_records is not None:
            if not isinstance(rank_records, list) or len(rank_records) != 8:
                bad("rank_records_count")
            else:
                for record in rank_records:
                    rank = record.get("rank") if isinstance(record, Mapping) else None
                    if type(rank) is not int or rank in rank_record_by_rank:
                        bad("rank_records_ranks")
                        continue
                    rank_record_by_rank[rank] = record
                if set(rank_record_by_rank) != set(range(8)):
                    bad("rank_records_rank_set")
                for rank in range(8):
                    record = rank_record_by_rank.get(rank)
                    shard = shard_meta.get(rank)
                    if record is None or shard is None:
                        continue
                    if (
                        record.get("ownership_range") != list(shard["ownership"])
                        or record.get("local_size") != shard["size"]
                        or record.get("packet_shard_path") != shard["path_value"]
                        or record.get("packet_shard_sha256") != shard["sha256"]
                        or record.get("response_packet_manifest_sha256")
                        != actual_manifest_sha
                        or record.get("packet_manifest_sha256")
                        != expected_identity.get("packet_manifest_sha256")
                        or record.get("dtype") != "complex128"
                        or record.get("rhs_unchanged") is not True
                        or not _valid_sha(record.get("owned_rhs_sha256"), 64)
                        or not _valid_sha(record.get("owned_response_sha256"), 64)
                        or not _valid_sha(record.get("rhs_before_sha256"), 64)
                        or not _valid_sha(record.get("rhs_after_sha256"), 64)
                        or record.get("rhs_before_sha256")
                        != record.get("rhs_after_sha256")
                    ):
                        bad(f"rank_{rank}_record_binding")
        if not ok:
            return {
                "ok": False,
                "manifest": manifest,
                "shards": shard_meta,
                "rank_records": rank_record_by_rank,
            }
        return {
            "ok": True,
            "manifest": manifest,
            "shards": shard_meta,
            "rank_records": rank_record_by_rank,
        }

    def read_rank_arrays(
        packet: Mapping[str, Any],
        rank: int,
        label: str,
    ) -> tuple[Any, Any] | None:
        shard = packet["shards"].get(rank)
        if not isinstance(shard, Mapping):
            add("PAIRING_SETUP_FAILURE", f"{label}_rank_{rank}_metadata")
            return None
        try:
            with np.load(shard["path"], allow_pickle=False) as arrays:
                if set(arrays.files) != {"solution", "rhs"}:
                    add("PAIRING_SETUP_FAILURE", f"{label}_rank_{rank}_keys")
                    return None
                solution = np.asarray(arrays["solution"])
                rhs = np.asarray(arrays["rhs"])
                if (
                    solution.ndim != 1
                    or rhs.ndim != 1
                    or solution.shape != rhs.shape
                    or solution.dtype != np.dtype("complex128")
                    or rhs.dtype != np.dtype("complex128")
                    or solution.size != shard["size"]
                    or not np.isfinite(solution).all()
                    or not np.isfinite(rhs).all()
                ):
                    add("PAIRING_SETUP_FAILURE", f"{label}_rank_{rank}_arrays")
                    return None
                record = packet["rank_records"].get(rank)
                if record is not None and (
                    array_sha(rhs) != record["owned_rhs_sha256"]
                    or array_sha(solution) != record["owned_response_sha256"]
                    or array_sha(rhs) != record["rhs_before_sha256"]
                    or array_sha(rhs) != record["rhs_after_sha256"]
                ):
                    add("PAIRING_SETUP_FAILURE", f"{label}_rank_{rank}_array_hash")
                    return None
                return solution, rhs
        except (OSError, KeyError, ValueError, EOFError):
            add("PAIRING_SETUP_FAILURE", f"{label}_rank_{rank}_read")
            return None

    def compare_reported_number(
        comparison: Mapping[str, Any],
        field: str,
        value: float | None,
    ) -> None:
        if value is None or not same_number(comparison.get(field), value):
            add("RESPONSE_SENSITIVITY_UNRESOLVED", f"{field}_reported_mismatch")

    computed_pairs: list[dict[str, Any]] = []
    for ordinal, entry in expected_by_ordinal.items():
        pair = pairs.get(ordinal)
        if pair is None:
            continue
        side = entry.get("side")
        layout = layouts.get(side)
        pair_identity_ok = True
        instance = layout.get("layout_instance_id") if layout else None
        layout_sha = layout.get("layout_identity_sha256") if layout else None
        if (
            pair.get("side") != side
            or pair.get("scope") != TASK041_REPRESENTATIVE_RHS_SCOPE
            or pair.get("comparison_mode") != "common_layout_equivalence"
            or pair.get("pairing_scope") != "same_live_layout"
            or pair.get("run_layout_epoch") != instance
            or pair.get("layout_instance_id") != instance
            or pair.get("layout_identity_sha256") != layout_sha
        ):
            pair_identity_ok = False
            add("PAIRING_SETUP_FAILURE", f"ordinal_{ordinal}_pair_identity")
        for layout_field in ("before_layout", "after_layout"):
            value = pair.get(layout_field)
            if (
                not isinstance(value, Mapping)
                or value.get("layout_identity_sha256") != layout_sha
            ):
                pair_identity_ok = False
                add("PAIRING_SETUP_FAILURE", f"ordinal_{ordinal}_{layout_field}")
        expected_first = "legacy" if ordinal % 2 == 0 else "optimized"
        expected_order = [
            expected_first,
            "optimized" if expected_first == "legacy" else "legacy",
        ]
        if pair.get("variant_order") != expected_order:
            pair_identity_ok = False
            add("PAIRING_SETUP_FAILURE", f"ordinal_{ordinal}_variant_order")
        variants = pair.get("variants")
        if not isinstance(variants, Mapping) or set(variants) != {
            "legacy",
            "optimized",
        }:
            pair_identity_ok = False
            add("PAIRING_SETUP_FAILURE", f"ordinal_{ordinal}_variants")
        if not pair_identity_ok:
            continue

        base_identity = {
            "schema": "task041.common_layout_equivalence.response_identity.v1",
            "scope": TASK041_REPRESENTATIVE_RHS_SCOPE,
            "comparison_mode": "common_layout_equivalence",
            "pairing_scope": "same_live_layout",
            "run_layout_epoch": instance,
            "layout_instance_id": instance,
            "source_sha": summary.get("source_sha"),
            "probe_manifest_sha256": binding.get("sha256")
            if isinstance(binding, Mapping)
            else None,
            "packet_manifest_sha256": expected_packet_sha,
            "layout_identity_sha256": layout_sha,
            "ordinal": ordinal,
            "side": side,
            "formal_column": entry.get("formal_column"),
            "branch_ordinal": entry.get("branch_ordinal"),
        }
        variant_metadata: dict[str, dict[str, Any]] = {}
        variant_ok = True
        for variant in ("legacy", "optimized"):
            record = variants[variant]
            if not isinstance(record, Mapping):
                add("PAIRING_SETUP_FAILURE", f"ordinal_{ordinal}_{variant}_record")
                variant_ok = False
                continue
            variant_identity = dict(base_identity)
            variant_identity["variant"] = variant
            metadata = read_packet_metadata(
                f"ordinal_{ordinal}_{variant}",
                record.get("artifact"),
                variant_identity,
                record.get("rank_shards"),
            )
            if metadata is None or metadata.get("ok") is not True:
                variant_ok = False
            else:
                variant_metadata[variant] = metadata
        comparison = pair.get("comparison")
        if (
            not isinstance(comparison, Mapping)
            or not isinstance(comparison.get("diagnostic_packets"), Mapping)
            or set(comparison["diagnostic_packets"])
            != {"response_and_action", "residual_pair"}
        ):
            add("PAIRING_SETUP_FAILURE", f"ordinal_{ordinal}_diagnostic_packet_keys")
            variant_ok = False
        if not variant_ok:
            continue

        diagnostic_identity = {
            key: value
            for key, value in base_identity.items()
            if key != "schema"
        }
        diagnostics = comparison["diagnostic_packets"]
        action_packet = read_packet_metadata(
            f"ordinal_{ordinal}_action_delta",
            diagnostics.get("response_and_action"),
            {
                "schema": "task041.common_layout_equivalence.comparison_diagnostic.v1",
                **diagnostic_identity,
                "kind": "response_and_action_delta",
            },
        )
        residual_packet = read_packet_metadata(
            f"ordinal_{ordinal}_residual_pair",
            diagnostics.get("residual_pair"),
            {
                "schema": "task041.common_layout_equivalence.comparison_diagnostic.v1",
                **diagnostic_identity,
                "kind": "legacy_and_optimized_residual",
            },
        )
        if (
            action_packet is None
            or residual_packet is None
            or action_packet.get("ok") is not True
            or residual_packet.get("ok") is not True
        ):
            continue

        legacy_meta = variant_metadata["legacy"]
        optimized_meta = variant_metadata["optimized"]
        arrays_ok = True
        rhs_sq = old_sq = new_sq = delta_sq = 0.0
        for rank in range(8):
            old_values = read_rank_arrays(
                legacy_meta, rank, f"ordinal_{ordinal}_legacy"
            )
            new_values = read_rank_arrays(
                optimized_meta, rank, f"ordinal_{ordinal}_optimized"
            )
            if old_values is None or new_values is None:
                arrays_ok = False
                continue
            old_solution, old_rhs = old_values
            new_solution, new_rhs = new_values
            if (
                legacy_meta["shards"][rank]["ownership"]
                != optimized_meta["shards"][rank]["ownership"]
                or not np.array_equal(old_rhs, new_rhs)
            ):
                add("PAIRING_SETUP_FAILURE", f"ordinal_{ordinal}_rank_{rank}_rhs_layout")
                arrays_ok = False
            rhs_sq += float(np.vdot(old_rhs, old_rhs).real)
            old_sq += float(np.vdot(old_solution, old_solution).real)
            new_sq += float(np.vdot(new_solution, new_solution).real)
            delta = new_solution - old_solution
            delta_sq += float(np.vdot(delta, delta).real)
            del delta, old_solution, old_rhs, new_solution, new_rhs
        if not arrays_ok:
            continue

        action_sq = residual_old_sq = residual_new_sq = residual_diff_sq = 0.0
        for rank in range(8):
            old_values = read_rank_arrays(
                legacy_meta, rank, f"ordinal_{ordinal}_legacy_action"
            )
            new_values = read_rank_arrays(
                optimized_meta, rank, f"ordinal_{ordinal}_optimized_action"
            )
            action_values = read_rank_arrays(
                action_packet, rank, f"ordinal_{ordinal}_action"
            )
            if old_values is None or new_values is None or action_values is None:
                arrays_ok = False
                continue
            old_solution, old_rhs = old_values
            new_solution, new_rhs = new_values
            action_solution, action_rhs = action_values
            if (
                not np.array_equal(action_solution, new_solution - old_solution)
                or not np.array_equal(old_rhs, new_rhs)
                or legacy_meta["shards"][rank]["ownership"]
                != action_packet["shards"][rank]["ownership"]
            ):
                add("PAIRING_SETUP_FAILURE", f"ordinal_{ordinal}_rank_{rank}_action")
                arrays_ok = False
            action_sq += float(np.vdot(action_rhs, action_rhs).real)
            del (
                old_solution,
                old_rhs,
                new_solution,
                new_rhs,
                action_solution,
                action_rhs,
            )
        if not arrays_ok:
            continue

        for rank in range(8):
            residual_values = read_rank_arrays(
                residual_packet, rank, f"ordinal_{ordinal}_residual"
            )
            if residual_values is None:
                arrays_ok = False
                continue
            legacy_residual, optimized_residual = residual_values
            if (
                residual_packet["shards"][rank]["ownership"]
                != legacy_meta["shards"][rank]["ownership"]
            ):
                add("PAIRING_SETUP_FAILURE", f"ordinal_{ordinal}_rank_{rank}_residual")
                arrays_ok = False
            residual_difference = optimized_residual - legacy_residual
            residual_old_sq += float(np.vdot(legacy_residual, legacy_residual).real)
            residual_new_sq += float(
                np.vdot(optimized_residual, optimized_residual).real
            )
            residual_diff_sq += float(
                np.vdot(residual_difference, residual_difference).real
            )
            del (
                legacy_residual,
                optimized_residual,
                residual_difference,
            )
        if not arrays_ok:
            continue

        rhs_norm = math.sqrt(rhs_sq)
        legacy_norm = math.sqrt(old_sq)
        optimized_norm = math.sqrt(new_sq)
        delta_norm = math.sqrt(delta_sq)
        action_norm = math.sqrt(action_sq)
        e_x = strict_ratio(delta_norm, max(legacy_norm, optimized_norm))
        e_A = strict_ratio(action_norm, rhs_norm)
        legacy_residual_norm = math.sqrt(residual_old_sq)
        optimized_residual_norm = math.sqrt(residual_new_sq)
        residual_difference_norm = math.sqrt(residual_diff_sq)
        residual_denominator = max(legacy_residual_norm, optimized_residual_norm)
        residual_difference_relative = strict_ratio(
            residual_difference_norm,
            residual_denominator,
        )
        for variant in ("legacy", "optimized"):
            raw = raw_audits.get((ordinal, variant))
            if raw is None:
                continue
            audit = raw[1]
            if not same_number(audit.get("rhs_norm"), rhs_norm):
                add(
                    "NUMERICAL_GATE_FAIL",
                    f"ordinal_{ordinal}_{variant}_rhs_norm_packet_mismatch",
                )
            raw_residual = audit.get("residual_norm")
            packet_residual = (
                legacy_residual_norm
                if variant == "legacy"
                else optimized_residual_norm
            )
            if not same_number(raw_residual, packet_residual):
                add(
                    "NUMERICAL_GATE_FAIL",
                    f"ordinal_{ordinal}_{variant}_residual_packet_mismatch",
                )
            recomputed = strict_ratio(packet_residual, rhs_norm)
            if recomputed is None or recomputed > 1.0e-2:
                add(
                    "NUMERICAL_GATE_FAIL",
                    f"ordinal_{ordinal}_{variant}_packet_residual_gate",
                )
            if not same_number(audit.get("relative_residual"), recomputed):
                add(
                    "NUMERICAL_GATE_FAIL",
                    f"ordinal_{ordinal}_{variant}_packet_relative_mismatch",
                )

        if (
            not numeric(e_x)
            or not numeric(e_A)
            or e_x > 1.0e-8
            or e_A > 1.0e-8
        ):
            add("RESPONSE_SENSITIVITY_UNRESOLVED", f"ordinal_{ordinal}_response_gate")
        if not isinstance(comparison, Mapping):
            add("RESPONSE_SENSITIVITY_UNRESOLVED", f"ordinal_{ordinal}_comparison")
        else:
            if not same_number(comparison.get("threshold_e_x"), 1.0e-8):
                add("PAIRING_SETUP_FAILURE", f"ordinal_{ordinal}_threshold_e_x")
            if not same_number(comparison.get("threshold_e_A"), 1.0e-8):
                add("PAIRING_SETUP_FAILURE", f"ordinal_{ordinal}_threshold_e_A")
            compare_reported_number(comparison, "e_x_absolute", delta_norm)
            compare_reported_number(comparison, "e_x", e_x)
            compare_reported_number(comparison, "e_A_absolute", action_norm)
            compare_reported_number(comparison, "e_A", e_A)
            compare_reported_number(comparison, "rhs_norm", rhs_norm)
            response_norms = comparison.get("response_norms")
            if not isinstance(response_norms, Mapping):
                add("RESPONSE_SENSITIVITY_UNRESOLVED", f"ordinal_{ordinal}_response_norms")
            else:
                compare_reported_number(response_norms, "legacy", legacy_norm)
                compare_reported_number(response_norms, "optimized", optimized_norm)
                compare_reported_number(
                    response_norms,
                    "denominator",
                    max(legacy_norm, optimized_norm),
                )
            residual_norms = comparison.get("residual_norms")
            if not isinstance(residual_norms, Mapping):
                add("RESPONSE_SENSITIVITY_UNRESOLVED", f"ordinal_{ordinal}_residual_norms")
            else:
                compare_reported_number(
                    residual_norms, "legacy", legacy_residual_norm
                )
                compare_reported_number(
                    residual_norms, "optimized", optimized_residual_norm
                )
                compare_reported_number(
                    residual_norms,
                    "denominator",
                    residual_denominator,
                )
            compare_reported_number(
                comparison,
                "residual_difference_norm",
                residual_difference_norm,
            )
            compare_reported_number(
                comparison,
                "residual_difference_relative",
                residual_difference_relative,
            )
            independent_pass = bool(
                numeric(e_x)
                and numeric(e_A)
                and e_x <= 1.0e-8
                and e_A <= 1.0e-8
            )
            if comparison.get("finite") is not True:
                add("RESPONSE_SENSITIVITY_UNRESOLVED", f"ordinal_{ordinal}_finite")
            if comparison.get("pass") is not independent_pass:
                add("RESPONSE_SENSITIVITY_UNRESOLVED", f"ordinal_{ordinal}_pass")
            if comparison.get("operator_scope") != "side_A":
                add("PAIRING_SETUP_FAILURE", f"ordinal_{ordinal}_operator_scope")

        pair_audits = pair.get("audits")
        if not isinstance(pair_audits, Mapping):
            add("PAIRING_SETUP_FAILURE", f"ordinal_{ordinal}_audits")
        else:
            for variant in ("legacy", "optimized"):
                raw = raw_audits.get((ordinal, variant))
                recorded = pair_audits.get(variant)
                if raw is None or not isinstance(recorded, Mapping):
                    add("PAIRING_SETUP_FAILURE", f"ordinal_{ordinal}_{variant}_audit_binding")
                    continue
                for field in (
                    "status",
                    "reason",
                    "iterations",
                    "rhs_norm",
                    "residual_norm",
                    "relative_residual",
                    "execution_variant",
                    "representative_ordinal",
                    "source_audit_index",
                    "formal_column",
                    "branch_ordinal",
                ):
                    if recorded.get(field) != raw[1].get(field):
                        add(
                            "PAIRING_SETUP_FAILURE",
                            f"ordinal_{ordinal}_{variant}_{field}_binding",
                        )
                variant_record = pair["variants"].get(variant)
                if not isinstance(variant_record, Mapping) or not isinstance(
                    variant_record.get("audit"), Mapping
                ):
                    add(
                        "PAIRING_SETUP_FAILURE",
                        f"ordinal_{ordinal}_{variant}_variant_audit",
                    )
                elif variant_record["audit"] != recorded:
                    add(
                        "PAIRING_SETUP_FAILURE",
                        f"ordinal_{ordinal}_{variant}_variant_audit_binding",
                    )

        computed_pairs.append(
            {
                "ordinal": ordinal,
                "side": side,
                "rhs_norm": rhs_norm,
                "legacy_response_norm": legacy_norm,
                "optimized_response_norm": optimized_norm,
                "e_x_absolute": delta_norm,
                "e_x": e_x,
                "e_A_absolute": action_norm,
                "e_A": e_A,
                "legacy_residual_norm": legacy_residual_norm,
                "optimized_residual_norm": optimized_residual_norm,
                "residual_difference_norm": residual_difference_norm,
                "residual_difference_relative": residual_difference_relative,
            }
        )

    summary_entries = common_map.get("entries") if common_map is not None else None
    summary_by_ordinal: dict[int, Mapping[str, Any]] = {}
    if not isinstance(summary_entries, list) or len(summary_entries) != 8:
        add("PAIRING_SETUP_FAILURE", "summary_common_entries")
    elif all(isinstance(item, Mapping) for item in summary_entries):
        for record in summary_entries:
            ordinal = record.get("ordinal")
            if type(ordinal) is not int or ordinal in summary_by_ordinal:
                add("PAIRING_SETUP_FAILURE", "summary_entry_key")
            else:
                summary_by_ordinal[ordinal] = record
    else:
        add("PAIRING_SETUP_FAILURE", "summary_entry_record")
    for ordinal, pair in pairs.items():
        record = summary_by_ordinal.get(ordinal)
        if record is None:
            add("PAIRING_SETUP_FAILURE", f"summary_ordinal_{ordinal}_missing")
            continue
        for field in (
            "side",
            "branch",
            "audit_index",
            "formal_column",
            "branch_ordinal",
            "status",
            "scope",
            "comparison_mode",
            "pairing_scope",
            "run_layout_epoch",
            "layout_instance_id",
            "layout_identity_sha256",
        ):
            if record.get(field) != pair.get(field):
                add("PAIRING_SETUP_FAILURE", f"summary_ordinal_{ordinal}_{field}")
        if set(record.get("variants", {})) != {"legacy", "optimized"}:
            add("PAIRING_SETUP_FAILURE", f"summary_ordinal_{ordinal}_variants")

    checks["summary_entries"] = {
        "count": len(summary_by_ordinal),
        "expected": TASK041_REPRESENTATIVE_RHS_COUNT,
    }
    checks["computed_pairs"] = computed_pairs
    checks["category_failures"] = categories
    checks["schedule"] = bool(
        common_map is not None
        and common_map.get("scope") == TASK041_REPRESENTATIVE_RHS_SCOPE
        and common_map.get("comparison_mode") == "common_layout_equivalence"
        and common_map.get("pairing_scope") == "same_live_layout"
        and expected_side_setup_schedule == TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
    )
    if not checks["schedule"]:
        add("PAIRING_SETUP_FAILURE", "common_scope_binding")
    if common_map is not None and (
        common_map.get("status") != "completed"
        or common_map.get("expected_count") != 8
        or common_map.get("completed_count") != 8
        or common_map.get("apply_count") != 16
    ):
        add("PAIRING_SETUP_FAILURE", "common_completion_counts")

    failures = [
        f"{category}:{reason}"
        for category in (
            "PAIRING_SETUP_FAILURE",
            "NUMERICAL_GATE_FAIL",
            "ACTION_EQUIVALENCE_FAIL",
            "RESPONSE_SENSITIVITY_UNRESOLVED",
        )
        for reason in categories[category]
    ]
    classification = next(
        (
            category
            for category in (
                "PAIRING_SETUP_FAILURE",
                "NUMERICAL_GATE_FAIL",
                "ACTION_EQUIVALENCE_FAIL",
                "RESPONSE_SENSITIVITY_UNRESOLVED",
            )
            if categories[category]
        ),
        None,
    )
    checks["category_failures"] = categories
    return {
        "pass": not any(categories.values()),
        "scope": TASK041_REPRESENTATIVE_RHS_SCOPE,
        "comparison_mode": "common_layout_equivalence",
        "failure_classification": classification,
        "checks": checks,
        "category_failures": categories,
        "failures": failures,
    }

def _consumer_result(
    consumer_root: Path,
    *,
    process_group_gone: bool | None = None,
    representative_rhs_binding: Mapping[str, Any] | None = None,
    expected_side_setup_schedule: str | None = None,
    expected_comparison_mode: str | None = None,
    expected_diagnostic_output: bool = False,
    expected_diagnostic_model_id: str | None = None,
) -> dict[str, Any]:
    summary_path = consumer_root / "consumer_summary.json"
    if not summary_path.is_file():
        factor_path = consumer_root / "factor_inventory.json"
        factor_inventory: Any = (
            {"artifact": _artifact_metadata(factor_path)}
            if factor_path.is_file()
            else {"status": "not_available"}
        )
        return {
            "complete": False,
            "classification": "task041_consumer_summary_missing",
            "summary_artifact": None,
            "factor_inventory": factor_inventory,
        }
    summary = _read_json(summary_path)
    markers = summary.get("markers")
    observed = markers.get("observed", []) if isinstance(markers, Mapping) else []
    lifecycle = summary.get("lifecycle")
    gates = summary.get("gates")
    worker_classification = summary.get("classification")
    diagnostic_policy = summary.get("diagnostic_output_policy")
    diagnostic_output = summary.get("diagnostic_output")
    diagnostic_qualification = summary.get("qualification")
    official_rta = summary.get("official_rta")
    common_scope = expected_comparison_mode == "common_layout_equivalence"
    common_failure_classes = {
        "PAIRING_SETUP_FAILURE",
        "NUMERICAL_GATE_FAIL",
        "ACTION_EQUIVALENCE_FAIL",
        "RESPONSE_SENSITIVITY_UNRESOLVED",
    }
    worker_common_failure = bool(
        common_scope
        and isinstance(worker_classification, str)
        and worker_classification in common_failure_classes
    )
    representative_scope = (
        representative_rhs_binding is not None and not common_scope
    )
    representative_validation = (
        _validate_representative_rhs_result(
            consumer_root,
            summary,
            representative_rhs_binding,
            process_group_gone=process_group_gone,
            expected_side_setup_schedule=expected_side_setup_schedule,
        )
        if representative_rhs_binding is not None and not common_scope
        else None
    )
    common_validation = (
        _validate_common_layout_equivalence_result(
            consumer_root,
            summary,
            representative_rhs_binding,
            expected_side_setup_schedule=expected_side_setup_schedule,
        )
        if common_scope and not worker_common_failure
        else None
    )
    balh_consumer = str(summary.get("schema", "")).startswith(
        "task041.side_balh."
    )
    regular_lifecycle_gate = (
        isinstance(lifecycle, Mapping)
        and lifecycle.get("setup_released") is True
        and (
            balh_consumer
            or lifecycle.get("rss_drop_pass") is True
        )
        and lifecycle.get("rss_marker_emitted") is True
    )
    representative_lifecycle_gate = (
        isinstance(lifecycle, Mapping)
        and lifecycle.get("setup_released") is True
        and lifecycle.get("representative_rhs_cleanup_pass") is True
        and lifecycle.get("rss_marker_emitted") is True
    )
    lifecycle_gate = (
        representative_lifecycle_gate
        if representative_scope or common_scope
        else regular_lifecycle_gate
    )
    marker_gate = isinstance(observed, list) and "final_cleanup_complete" in observed
    cleanup = summary.get("cleanup")
    cleanup_gate = isinstance(cleanup, Mapping) and cleanup.get("pass") is True
    summary_identity = summary.get("identity")
    diagnostic_model_registered = bool(
        isinstance(expected_diagnostic_model_id, str)
        and task041_balh_diagnostic_output_enabled(expected_diagnostic_model_id)
    )
    diagnostic_identity_gate = bool(
        expected_diagnostic_output is True
        and diagnostic_model_registered
        and isinstance(summary_identity, Mapping)
        and summary_identity.get("model_id") == expected_diagnostic_model_id
        and isinstance(diagnostic_policy, Mapping)
        and diagnostic_policy.get("enabled") is True
        and diagnostic_policy.get("model_id") == expected_diagnostic_model_id
    )
    diagnostic_gates_gate = bool(
        isinstance(gates, Mapping)
        and gates.get("pass") is False
        and isinstance(gates.get("authority_identity"), Mapping)
        and gates["authority_identity"].get("pass") is True
        and gates.get("grid_E_H_evidence_pass") is True
        and gates.get("external_diffraction_channels_pass") is True
        and gates.get("external_key_binding_pass") is True
        and gates.get("external_orders_key_binding_pass") is True
    )
    diagnostic_rta_gate = bool(
        isinstance(official_rta, Mapping)
        and official_rta.get("status") == "measured_diagnostic"
        and official_rta.get("qualified") is False
        and all(
            isinstance(official_rta.get(name), (int, float))
            and not isinstance(official_rta.get(name), bool)
            and math.isfinite(float(official_rta[name]))
            for name in ("R", "T", "A", "A_volume")
        )
    )
    diagnostic_complete = bool(
        diagnostic_identity_gate
        and worker_classification == "DIAGNOSTIC_RESULT_AVAILABLE"
        and summary.get("status") == "completed_with_diagnostics"
        and isinstance(diagnostic_output, Mapping)
        and diagnostic_output.get("result_available") is True
        and summary.get("qualification_status") == "unqualified"
        and isinstance(diagnostic_qualification, Mapping)
        and diagnostic_qualification.get("pass") is False
        and diagnostic_gates_gate
        and diagnostic_rta_gate
        and lifecycle_gate
        and cleanup_gate
        and process_group_gone is True
        and marker_gate
    )
    representative_complete = bool(
        representative_scope
        and worker_classification == "TASK041_REPRESENTATIVE_RHS_COMPLETED"
        and summary.get("status") == "task041_representative_rhs_completed"
        and representative_validation is not None
        and representative_validation.get("pass") is True
        and lifecycle_gate
        and process_group_gone is True
        and marker_gate
    )
    regular_complete = bool(
        not representative_scope
        and not common_scope
        and worker_classification == "TASK041_CONSUMER_PASS"
        and summary.get("status") == "task041_consumer_completed"
        and isinstance(gates, Mapping)
        and gates.get("pass") is True
        and regular_lifecycle_gate
        and process_group_gone is True
        and marker_gate
    )
    common_complete = bool(
        common_scope
        and worker_classification == "COMMON_LAYOUT_EQUIVALENCE_PASS"
        and summary.get("status") == "task041_common_layout_equivalence_completed"
        and common_validation is not None
        and common_validation.get("pass") is True
        and isinstance(gates, Mapping)
        and gates.get("pass") is False
        and lifecycle_gate
        and process_group_gone is True
        and marker_gate
    )
    complete = (
        representative_complete
        or common_complete
        or regular_complete
        or diagnostic_complete
    )
    if diagnostic_complete:
        classification = "DIAGNOSTIC_RESULT_AVAILABLE"
    elif complete:
        classification = "worker_exit0"
    elif worker_common_failure:
        classification = str(worker_classification)
    elif common_scope:
        classification = (
            common_validation.get("failure_classification")
            if isinstance(common_validation, Mapping)
            else None
        ) or worker_classification or "PAIRING_SETUP_FAILURE"
    elif representative_scope:
        classification = "task041_representative_rhs_validation_failure"
    elif worker_classification != "TASK041_CONSUMER_PASS":
        classification = worker_classification or "task041_consumer_summary_invalid"
    else:
        classification = "task041_consumer_lifecycle_failure"
    factor_path = consumer_root / "factor_inventory.json"
    factor_inventory: Any = summary.get("factor_inventory")
    if factor_path.is_file():
        factor_inventory = {"artifact": _artifact_metadata(factor_path)}
    elif not isinstance(factor_inventory, Mapping):
        factor_inventory = {"status": "not_available"}
    summary_artifact = _artifact_metadata(summary_path)
    return {
        "complete": complete,
        "classification": classification,
        "worker_classification": worker_classification,
        "status": summary.get("status"),
        "failure_evidence": summary.get("failure_evidence"),
        "summary_artifact": summary_artifact,
        "summary_path": summary_artifact["path"],
        "summary_sha256": summary_artifact["sha256"],
        "summary_bytes": summary_artifact["bytes"],
        "gates": gates,
        "lifecycle": lifecycle,
        "matrix_inventory": summary.get("matrix_inventory", {}),
        "factor_inventory": factor_inventory,
        "markers": {"observed": observed},
        "official_rta": summary.get("official_rta", {"status": "not_available"}),
        "diagnostic_result_available": diagnostic_complete,
        "diagnostic_output": diagnostic_output,
        "diagnostic_output_policy": diagnostic_policy,
        "qualification_status": summary.get("qualification_status"),
        "process_group_gone": process_group_gone,
        "lifecycle_gate": lifecycle_gate,
        "representative_validation": representative_validation,
        "common_validation": common_validation,
        "completion_scope": (
            "representative_rhs"
            if common_scope
            else "representative_rhs"
            if representative_complete
            else "formal"
        ),
    }


def _phase_resource_failure(phase_result: Mapping[str, Any]) -> bool:
    return phase_result.get("termination_reason") in {
        "absolute_memory_limit",
        "process_tree_rss_unmeasured",
        "process_tree_rss_limit",
        "cgroup_headroom_floor",
        "cgroup_headroom_unmeasured",
        "memavailable_floor",
        "memavailable_unmeasured",
        "swap_detected",
        "cumulative_wall_timeout",
        "wall_timeout",
    }


def _phase_resource_classification(
    phase_result: Mapping[str, Any],
) -> str | None:
    return {
        "absolute_memory_limit": "memory_terminate",
        "process_tree_rss_unmeasured": "process_tree_rss_unmeasured",
        "process_tree_rss_limit": "process_tree_rss_limit",
        "cgroup_headroom_floor": "cgroup_headroom_floor",
        "cgroup_headroom_unmeasured": "cgroup_headroom_unmeasured",
        "memavailable_floor": "memavailable_floor",
        "memavailable_unmeasured": "memavailable_unmeasured",
        "swap_detected": "swap_policy_violation",
        "cumulative_wall_timeout": "cumulative_wall_timeout",
        "wall_timeout": "timeout",
    }.get(str(phase_result.get("termination_reason")))


def _wall_seconds(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value >= 0.0 else None


def _load_task041_compute_wall_ledger(
    ledger_path: Path,
) -> tuple[Path, dict[str, Any]]:
    if not ledger_path.is_file():
        raise Task041SupervisorError(
            f"Task041 compute wall ledger is required but missing: {ledger_path}",
            classification="task041_identity_failure",
            stage="workflow_wall_budget",
        )
    payload = _read_json(ledger_path)
    used = _wall_seconds(payload.get("used_compute_wall_seconds"))
    if used is None:
        raise Task041SupervisorError(
            f"Task041 compute wall ledger has no finite used value: {ledger_path}",
            classification="task041_identity_failure",
            stage="workflow_wall_budget",
        )
    source_records = payload.get("source_records")
    if not isinstance(source_records, list):
        source_records = []
    if not source_records:
        for name in ("measured", "derived_upper_bound"):
            section = payload.get(name)
            if isinstance(section, Mapping) and isinstance(
                section.get("records"), list
            ):
                source_records.extend(section["records"])
    loaded = dict(payload)
    loaded["used_compute_wall_seconds"] = used
    loaded["used_status"] = str(payload.get("used_status", "derived"))
    loaded["basis"] = payload.get("basis", "explicit compact ledger")
    loaded["source_records"] = source_records
    return ledger_path, loaded


def _task041_v2_group_used(
    ledger: Mapping[str, Any], phase_group: str
) -> float:
    field = {
        "shared_S0_S1_S3": "shared_S0_S1_S3_used_seconds",
        "S2": "S2_used_seconds",
        "S4": "S4_used_seconds",
    }.get(phase_group)
    if field is None:
        raise ValueError(f"unknown Task041 V2 phase group: {phase_group!r}")
    value = _wall_seconds(ledger.get(field))
    if value is not None:
        return value
    phase_scope = str(ledger.get("phase_scope", ""))
    shared_scope = {"S0/S1/S3", "shared_S0_S1_S3"}
    if (phase_group == "shared_S0_S1_S3" and phase_scope in shared_scope) or (
        phase_group != "shared_S0_S1_S3" and phase_scope == phase_group
    ):
        return float(ledger["used_compute_wall_seconds"])
    return 0.0


def _write_task041_compute_wall_ledger(
    ledger_path: Path,
    *,
    used_before: Mapping[str, Any],
    current_seconds: float,
    run_directory: Path,
    phase_seconds: Mapping[str, float] | None = None,
    limit_seconds: float | None = None,
    profile_id: str | None = None,
    phase_group: str | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    before = float(used_before["used_compute_wall_seconds"])
    current_seconds = max(0.0, float(current_seconds))
    total = before + current_seconds
    previous_status = str(used_before.get("used_status", ""))
    status = (
        previous_status
        if previous_status.startswith("derived")
        else "measured"
    )
    measured = used_before.get("measured")
    current_record = {
        "path": str(run_directory),
        "seconds": current_seconds,
        "status": "measured",
        "current_invocation": True,
        "phase_seconds": (
            dict(phase_seconds) if phase_seconds is not None else None
        ),
    }
    if profile_id is not None:
        if previous_status == "measured_plus_conservative_upper_bound":
            status = previous_status
        if phase_group is None:
            phase_names = tuple(phase_seconds or {})
            if len(phase_names) == 1:
                phase_group = phase_names[0]
                if phase_group in {"S0", "S1", "S3"}:
                    phase_group = "shared_S0_S1_S3"
        if phase_group not in {"shared_S0_S1_S3", "S2", "S4"}:
            raise ValueError(
                "Task041 V2 ledger update requires one explicit phase group"
            )
        from benchmarks.task041_balh_workflow import (
            TASK041_SCHUR_SPEED_V2_BATCH_BUDGET_SECONDS,
            TASK041_SCHUR_SPEED_V2_S0_S1_S3_BUDGET_SECONDS,
            TASK041_SCHUR_SPEED_V2_S2_BUDGET_SECONDS,
            TASK041_SCHUR_SPEED_V2_S4_BUDGET_SECONDS,
        )

        phase_budgets = {
            "shared_S0_S1_S3": TASK041_SCHUR_SPEED_V2_S0_S1_S3_BUDGET_SECONDS,
            "S2": TASK041_SCHUR_SPEED_V2_S2_BUDGET_SECONDS,
            "S4": TASK041_SCHUR_SPEED_V2_S4_BUDGET_SECONDS,
        }
        shared_used = _task041_v2_group_used(
            used_before, "shared_S0_S1_S3"
        )
        s2_used = _task041_v2_group_used(used_before, "S2")
        s4_used = _task041_v2_group_used(used_before, "S4")
        if phase_group == "shared_S0_S1_S3":
            shared_used += current_seconds
        elif phase_group == "S2":
            s2_used += current_seconds
        else:
            s4_used += current_seconds
        batch_used = shared_used + s2_used + s4_used
        limit = float(
            limit_seconds
            if limit_seconds is not None
            else TASK041_SCHUR_SPEED_V2_BATCH_BUDGET_SECONDS
        )
        current_record["profile_id"] = profile_id
        current_record["phase_group"] = phase_group
        current_record["phase_budget_seconds"] = phase_budgets[phase_group]
        payload = dict(used_before)
        payload.update(
            {
                "schema": used_before.get(
                    "schema", "task041.compute_wall_ledger.v2"
                ),
                "profile_id": profile_id,
                "budget_limit_seconds": limit,
                "batch_budget_seconds": limit,
                "phase_budgets_seconds": phase_budgets,
                "shared_S0_S1_S3_used_seconds": shared_used,
                "S2_used_seconds": s2_used,
                "S4_used_seconds": s4_used,
                "batch_used_compute_wall_seconds": batch_used,
                "used_compute_wall_seconds": batch_used,
                "used_status": status,
                "last_phase_group": phase_group,
                "source_records": [
                    *list(used_before.get("source_records", [])),
                    current_record,
                ],
                "phase_remaining_seconds": {
                    name: max(0.0, budget - used)
                    for name, budget, used in (
                        (
                            "shared_S0_S1_S3",
                            phase_budgets["shared_S0_S1_S3"],
                            shared_used,
                        ),
                        ("S2", phase_budgets["S2"], s2_used),
                        ("S4", phase_budgets["S4"], s4_used),
                    )
                },
                "remaining_budget_seconds": max(0.0, limit - batch_used),
                "remaining_status": (
                    "derived_from_measured_and_conservative_upper_bound"
                    if status == "measured_plus_conservative_upper_bound"
                    else "derived_from_current_and_prior_records"
                ),
            }
        )
        _write_json(ledger_path, payload)
        return payload
    if isinstance(measured, Mapping):
        measured = dict(measured)
        measured_seconds = _wall_seconds(measured.get("seconds"))
        measured["seconds"] = (
            (measured_seconds if measured_seconds is not None else 0.0)
            + current_seconds
        )
        measured_records = measured.get("records")
        measured["records"] = [
            *(
                measured_records
                if isinstance(measured_records, list)
                else []
            ),
            current_record,
        ]
    if case_id is not None:
        if case_id != TASK041_BALH_2NM_MODEL_ID or profile_id is not None:
            raise ValueError("unsupported Task041 registered-case ledger identity")
        current_record["case_id"] = case_id
        payload = dict(used_before)
        payload.update(
            {
                "schema": used_before.get(
                    "schema", "task041.compute_wall_ledger.v1"
                ),
                "case_id": case_id,
                "profile_id": None,
                "limit_seconds": None,
                "budget_limit_seconds": None,
                "batch_budget_seconds": None,
                "used_compute_wall_seconds": total,
                "used_status": status,
                "measured": measured,
                "source_records": [
                    *list(used_before.get("source_records", [])),
                    current_record,
                ],
                "remaining_budget_seconds": None,
                "remaining_status": "not_applicable_unlimited_case",
                "budget_semantics": (
                    "independent registered 2 nm case accounting; "
                    "no elapsed wall stop"
                ),
            }
        )
        _write_json(ledger_path, payload)
        return payload
    payload = {
        "schema": "task041.compute_wall_ledger.v1",
        "limit_seconds": TASK041_CUMULATIVE_COMPUTE_WALL_SECONDS,
        "used_compute_wall_seconds": total,
        "used_status": status,
        "basis": used_before.get("basis"),
        "initial_batch_allowance": used_before.get("initial_batch_allowance"),
        "derived_allowance_margin_seconds": used_before.get(
            "derived_allowance_margin_seconds"
        ),
        "measured": measured,
        "derived_upper_bound": used_before.get("derived_upper_bound"),
        "source_records": [
            *list(used_before.get("source_records", [])),
            current_record,
        ],
    }
    _write_json(ledger_path, payload)
    return payload


def run_task041_public_supervisor(
    specification: Any,
    *,
    source_sha: str,
    run_directory: str | Path,
    python_executable: str | Path | None = None,
    mpiexec_command: str | None = None,
    popen_factory: PopenFactory = subprocess.Popen,
    sample_factory: SampleFactory = resource_authority_sample,
    terminate_factory: TerminateFactory = terminate_process_tree,
    monotonic: Clock = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    poll_interval: float = 0.25,
    process_group_gone: Callable[[int], bool] = _process_group_gone,
    producer_packet_root: str | Path | None = None,
    legacy_native_packet_descriptor: str | Path | None = None,
    compute_wall_ledger_path: str | Path | None = None,
    disable_time_stop: bool = False,
    performance_profile: str | None = None,
    task041_supervision_record: str | Path | None = None,
    task041_rhs_probe_manifest: str | Path | None = None,
    task041_side_setup_schedule: str | None = None,
    task041_comparison_mode: str | None = None,
) -> dict[str, Any]:
    """Run one Task041 consumer, optionally reusing a completed BAL_H producer."""

    root = Path(run_directory).resolve()
    repository_root = Path(__file__).resolve().parents[2]
    started = monotonic()
    public_launcher_pid = os.getpid()
    result: dict[str, Any] = {
        "schema": "task041.public.supervisor.v1",
        "adapter": TASK041_PUBLIC_SUPERVISOR_ADAPTER,
        "run_directory": str(root),
        "source_sha": source_sha,
        "status": "not_started",
        "workflow_status": "not_started",
        "result_classification": "task041_not_run",
        "exit_status": None,
        "limits": {
            "warning_memory_bytes": TASK041_WARNING_MEMORY_BYTES,
            "hard_memory_bytes": TASK041_HARD_MEMORY_BYTES,
            "swap_limit_bytes": 0,
            "timeout_seconds": TASK041_TIMEOUT_SECONDS,
        },
        "phase_results": {},
        "resource_authority": {"status": "not_sampled"},
    }
    git_identity: dict[str, Any] | None = None
    environment_snapshot: dict[str, Any] | None = None
    packet: dict[str, Any] | None = None
    runtime_limits = {
        "warning_memory_bytes": TASK041_WARNING_MEMORY_BYTES,
        "hard_memory_bytes": TASK041_HARD_MEMORY_BYTES,
        "swap_limit_bytes": 0,
        "timeout_seconds": TASK041_TIMEOUT_SECONDS,
    }
    phase_limits: dict[str, dict[str, Any]] = {}
    compute_wall_ledger: dict[str, Any] | None = None
    global_swap_baseline: dict[str, Any] | None = None
    balh = False
    legacy_native = False
    performance_contract: dict[str, Any] | None = None
    case_runtime_contract: dict[str, Any] | None = None
    representative_rhs_binding: dict[str, Any] | None = None
    compute_wall_limit_seconds = TASK041_CUMULATIVE_COMPUTE_WALL_SECONDS
    compute_wall_phase_limit_seconds = TASK041_CUMULATIVE_COMPUTE_WALL_SECONDS
    compute_wall_phase_group: str | None = None
    compute_wall_phase_used_seconds = 0.0
    compute_wall_enforced_limit_seconds = TASK041_CUMULATIVE_COMPUTE_WALL_SECONDS
    supervision_binding: dict[str, Any] | None = None
    expected_diagnostic_output = False
    expected_diagnostic_model_id: str | None = None
    producer_root = root / "producer"
    try:
        if not root.is_dir():
            raise Task041SupervisorError(
                f"launcher bootstrap root is missing: {root}",
                classification="task041_implementation_failure",
                stage="root_preflight",
            )
        _initial_artifacts(root)
        if not _valid_sha(source_sha, 40):
            raise Task041SupervisorError(
                "source_sha is not a lowercase 40-character SHA",
                classification="task041_identity_failure",
                stage="source_identity",
            )
        identity = _validate_specification(specification, repository_root)
        if identity["model_id"] == TASK041_BALH_2NM_MODEL_ID:
            outer_mpi_identity = _outer_mpi_launch_identity(
                registered_model_id=TASK041_BALH_2NM_MODEL_ID
            )
        elif performance_profile is not None:
            outer_mpi_identity = _outer_mpi_launch_identity(performance_profile)
        else:
            outer_mpi_identity = _outer_mpi_launch_identity()
        outer_mpi_size = outer_mpi_identity["mpi_size"]
        expected_diagnostic_output = task041_balh_diagnostic_output_enabled(
            str(identity["model_id"])
        )
        expected_diagnostic_model_id = (
            str(identity["model_id"]) if expected_diagnostic_output else None
        )
        runtime_limits = _runtime_limits_for_identity(identity)
        result["limits"] = dict(runtime_limits)
        shortwave = identity["model_id"] in TASK041_SHORTWAVE_MODEL_IDS
        balh = identity["model_id"] in TASK041_BALH_MODEL_IDS
        if balh and identity["model_id"] == TASK041_BALH_2NM_MODEL_ID:
            registered_contract = task041_balh_service_contract(
                str(identity["model_id"])
            )
            if registered_contract is None:
                raise Task041SupervisorError(
                    "registered 2 nm service contract is unavailable",
                    classification="task041_identity_failure",
                    stage="service_contract",
                )
            case_runtime_contract = dict(registered_contract)
            compute_wall_limit_seconds = None
            compute_wall_phase_limit_seconds = None
            compute_wall_enforced_limit_seconds = None
        legacy_native = legacy_native_packet_descriptor is not None
        if balh:
            from benchmarks.task041_balh_workflow import (
                TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
                task041_balh_time_stop_override_record,
            )

            if disable_time_stop and (
                identity["model_id"] != TASK041_BALH_5NM_CANDIDATE_MODEL_ID
                or producer_packet_root is None
                and not legacy_native
            ):
                raise Task041SupervisorError(
                    "time-stop override requires a reused 5 nm BAL_H candidate",
                    classification="task041_identity_failure",
                    stage="time_stop_override",
                )
            if case_runtime_contract is not None:
                result["time_stop_policy"] = dict(
                    case_runtime_contract["time_stop"]
                )
                result["time_stop_policy"].update(
                    {
                        "model_id": identity["model_id"],
                        "run_id": identity.get("run_id"),
                        "source_sha": source_sha,
                        "scope": "registered_2nm_case",
                    }
                )
            else:
                result["time_stop_override"] = (
                    task041_balh_time_stop_override_record(disable_time_stop)
                    | {
                        "model_id": identity["model_id"],
                        "run_id": identity.get("run_id"),
                        "source_sha": source_sha,
                        "origin": "run_case_cli",
                    }
                )
        elif disable_time_stop:
            raise Task041SupervisorError(
                "time-stop override is limited to Task041 BAL_H profiles",
                classification="task041_identity_failure",
                stage="time_stop_override",
            )
        if producer_packet_root is not None and not balh:
            raise Task041SupervisorError(
                "producer packet reuse is enabled only for Task041 side BAL_H profiles",
                classification="task041_identity_failure",
                stage="producer_reuse_contract",
            )
        if legacy_native:
            from benchmarks.task041_legacy_native_packet import (
                task041_legacy_native_profile,
            )

            if producer_packet_root is not None or not task041_legacy_native_profile(
                specification
            ):
                raise Task041SupervisorError(
                    "legacy native packet import requires the Task041 5 nm M480 MPI8 profile",
                    classification="task041_identity_failure",
                    stage="producer_reuse_contract",
                )
        if performance_profile is not None:
            if not balh or identity["model_id"] not in TASK041_BALH_CANDIDATE_MODEL_IDS:
                raise Task041SupervisorError(
                    "task041_schur_speed_v2 is limited to Task041 BAL_H candidates",
                    classification="task041_identity_failure",
                    stage="performance_profile",
                )
            from benchmarks.task041_balh_workflow import (
                TASK041_REPRESENTATIVE_RHS_SCOPE,
                TASK041_SCHUR_SPEED_V2_PROFILE,
                task041_schur_speed_v2_contract,
            )

            if performance_profile != TASK041_SCHUR_SPEED_V2_PROFILE:
                raise Task041SupervisorError(
                    "unsupported Task041 performance profile",
                    classification="task041_identity_failure",
                    stage="performance_profile",
                )
            if producer_packet_root is None and not legacy_native:
                raise Task041SupervisorError(
                    "task041_schur_speed_v2 requires a reused BAL_H candidate packet",
                    classification="task041_identity_failure",
                    stage="performance_profile",
                )
            if disable_time_stop:
                raise Task041SupervisorError(
                    "performance profile and time-stop override are mutually exclusive",
                    classification="task041_identity_failure",
                    stage="performance_profile",
                )
            try:
                performance_contract = task041_schur_speed_v2_contract(
                    str(identity["model_id"]),
                    scope=(
                        TASK041_REPRESENTATIVE_RHS_SCOPE
                        if task041_rhs_probe_manifest is not None
                        else None
                    ),
                    side_setup_schedule=task041_side_setup_schedule,
                    comparison_mode=task041_comparison_mode,
                )
            except ValueError as exc:
                raise Task041SupervisorError(
                    str(exc),
                    classification="task041_identity_failure",
                    stage="performance_profile",
                ) from exc
            compute_wall_limit_seconds = float(
                performance_contract["batch_budget_seconds"]
            )
            compute_wall_phase_group = str(
                performance_contract["active_consumer_phase"]
            )
            compute_wall_phase_limit_seconds = float(
                performance_contract["active_consumer_budget_seconds"]
            )
        elif (
            task041_side_setup_schedule is not None
            or task041_comparison_mode is not None
        ):
            raise Task041SupervisorError(
                "Task041 comparison options require task041_schur_speed_v2",
                classification="task041_identity_failure",
                stage="performance_profile",
            )
        if task041_rhs_probe_manifest is not None:
            if (
                performance_contract is None
                or identity["model_id"] != TASK041_BALH_5NM_CANDIDATE_MODEL_ID
                or disable_time_stop
            ):
                raise Task041SupervisorError(
                    "representative RHS probe requires the reused 5 nm task041_schur_speed_v2 candidate",
                    classification="task041_identity_failure",
                    stage="representative_rhs_probe",
                )
            from benchmarks.task041_balh_workflow import (
                load_task041_representative_rhs_manifest,
            )

            try:
                representative_rhs_binding = (
                    load_task041_representative_rhs_manifest(
                        task041_rhs_probe_manifest
                    )
                )
            except (OSError, TypeError, ValueError) as exc:
                raise Task041SupervisorError(
                    f"invalid representative RHS manifest: {exc}",
                    classification="task041_identity_failure",
                    stage="representative_rhs_probe",
                ) from exc
            if (
                performance_contract["scope"]
                != representative_rhs_binding["scope"]
                or performance_contract["budget_group"]
                != representative_rhs_binding["budget"]["group"]
            ):
                raise Task041SupervisorError(
                    "representative RHS scope does not match the V2 budget contract",
                    classification="task041_identity_failure",
                    stage="representative_rhs_probe",
                )
            result["representative_rhs_probe"] = {
                "path": representative_rhs_binding["path"],
                "sha256": representative_rhs_binding["sha256"],
                "scope": representative_rhs_binding["scope"],
                "purpose": representative_rhs_binding["purpose"],
                "budget_group": performance_contract["budget_group"],
            }
        if task041_supervision_record is not None:
            supervision_contract = performance_contract or case_runtime_contract
            if supervision_contract is None:
                raise Task041SupervisorError(
                    "supervision record requires a registered Task041 contract",
                    classification="task041_identity_failure",
                    stage="supervision_record",
                )
            supervision_binding = _load_task041_supervision_record(
                task041_supervision_record,
                profile_id=supervision_contract["profile_id"],
                model_id=identity["model_id"],
                source_sha=source_sha,
                scope=supervision_contract["scope"],
                representative_rhs_probe=(
                    {
                        "path": representative_rhs_binding["path"],
                        "sha256": representative_rhs_binding["sha256"],
                    }
                    if representative_rhs_binding is not None
                    else None
                ),
                side_setup_schedule=supervision_contract.get(
                    "side_setup_schedule"
                ),
                comparison_mode=supervision_contract.get("comparison_mode"),
            )
            if compute_wall_ledger_path is not None and Path(
                compute_wall_ledger_path
            ).resolve() != Path(supervision_binding["ledger_path"]).resolve():
                raise Task041SupervisorError(
                    "supervision record ledger_path conflicts with explicit ledger path",
                    classification="task041_identity_failure",
                    stage="supervision_record",
                )
            compute_wall_ledger_path = supervision_binding["ledger_path"]
            result["supervision_record"] = supervision_binding
            result["ledger_owner"] = "service_finalizer"
        timeout_scope = "workflow"
        if shortwave or balh:
            phase_limits = {
                phase: dict(
                    task041_balh_phase_limits_for_model(identity["model_id"], phase)
                    if balh
                    else task041_shortwave_phase_limits_for_model(
                        identity["model_id"], phase
                    )
                )
                for phase in ("producer", "consumer")
            }
            result["phase_limits"] = phase_limits
            timeout_scope = (
                task041_balh_timeout_scope(identity["model_id"])
                if balh
                else task041_shortwave_timeout_scope(identity["model_id"])
            )
        if performance_contract is not None:
            active_timeout = int(performance_contract["active_consumer_budget_seconds"])
            runtime_limits = dict(runtime_limits)
            runtime_limits.update(
                {
                    "swap_limit_bytes": int(
                        performance_contract["swap_limit_bytes"]
                    ),
                    "process_tree_rss_warning_bytes": int(
                        performance_contract["warning_memory_bytes"]
                    ),
                    "process_tree_rss_cap_bytes": int(
                        performance_contract["memory_cap_bytes"]
                    ),
                    "memory_cap_source": performance_contract["memory_gate_source"],
                }
            )
            runtime_limits["timeout_seconds"] = active_timeout
            phase_limits["consumer"] = dict(phase_limits["consumer"])
            phase_limits["consumer"].update(
                {
                    "swap_limit_bytes": int(
                        performance_contract["swap_limit_bytes"]
                    ),
                    "process_tree_rss_warning_bytes": int(
                        performance_contract["warning_memory_bytes"]
                    ),
                    "process_tree_rss_cap_bytes": int(
                        performance_contract["memory_cap_bytes"]
                    ),
                    "memory_cap_source": performance_contract["memory_gate_source"],
                }
            )
            phase_limits["consumer"]["timeout_seconds"] = active_timeout
            result["limits"] = dict(runtime_limits)
            result["phase_limits"] = phase_limits
            result["performance_profile"] = performance_contract
            if performance_contract.get("side_setup_schedule") is not None:
                result["side_setup_schedule"] = performance_contract[
                    "side_setup_schedule"
                ]
            if performance_contract.get("comparison_mode") is not None:
                result["comparison_mode"] = performance_contract[
                    "comparison_mode"
                ]
        if case_runtime_contract is not None:
            runtime_limits = dict(runtime_limits)
            runtime_limits.update(
                {
                    "warning_memory_bytes": int(
                        case_runtime_contract["warning_memory_bytes"]
                    ),
                    "hard_memory_bytes": int(
                        case_runtime_contract["memory_cap_bytes"]
                    ),
                    "swap_limit_bytes": int(
                        case_runtime_contract["swap_limit_bytes"]
                    ),
                    "process_tree_rss_warning_bytes": int(
                        case_runtime_contract["warning_memory_bytes"]
                    ),
                    "process_tree_rss_cap_bytes": int(
                        case_runtime_contract["memory_cap_bytes"]
                    ),
                    "memory_cap_source": case_runtime_contract[
                        "memory_gate_source"
                    ],
                    "timeout_seconds": None,
                    "time_stop_enforced": False,
                }
            )
            phase_limits["consumer"] = dict(phase_limits["consumer"])
            phase_limits["consumer"].update(
                {
                    "process_tree_rss_warning_bytes": int(
                        case_runtime_contract["warning_memory_bytes"]
                    ),
                    "process_tree_rss_cap_bytes": int(
                        case_runtime_contract["memory_cap_bytes"]
                    ),
                    "memory_cap_source": case_runtime_contract[
                        "memory_gate_source"
                    ],
                    "timeout_seconds": None,
                    "time_stop_enforced": False,
                }
            )
            result["limits"] = dict(runtime_limits)
            result["phase_limits"] = phase_limits
            result["service_contract"] = case_runtime_contract
        if balh:
            if compute_wall_ledger_path is None:
                raise Task041SupervisorError(
                    "Task041 BAL_H requires an explicit compute wall ledger path",
                    classification="task041_identity_failure",
                    stage="workflow_wall_budget",
                )
            compute_wall_ledger_path, compute_wall_ledger = (
                _load_task041_compute_wall_ledger(
                    Path(compute_wall_ledger_path).resolve()
                )
            )
            used_before = float(
                compute_wall_ledger["used_compute_wall_seconds"]
            )
            if case_runtime_contract is not None:
                compute_wall_phase_used_seconds = used_before
                compute_wall_budget = {
                    "limit_seconds": None,
                    "used_before_seconds": used_before,
                    "used_before_status": compute_wall_ledger["used_status"],
                    "remaining_seconds": None,
                    "ledger_path": str(compute_wall_ledger_path),
                    "basis": compute_wall_ledger.get(
                        "budget_semantics",
                        "independent registered 2 nm case ledger; "
                        "no elapsed wall stop",
                    ),
                    "time_stop_enforced": False,
                    "case_id": case_runtime_contract["case_id"],
                }
            else:
                if compute_wall_phase_group is not None:
                    compute_wall_phase_used_seconds = _task041_v2_group_used(
                        compute_wall_ledger, compute_wall_phase_group
                    )
                else:
                    compute_wall_phase_used_seconds = used_before
                batch_remaining = max(
                    0.0, compute_wall_limit_seconds - used_before
                )
                phase_remaining = max(
                    0.0,
                    compute_wall_phase_limit_seconds
                    - compute_wall_phase_used_seconds,
                )
                remaining = max(
                    0.0,
                    min(batch_remaining, phase_remaining),
                )
                compute_wall_enforced_limit_seconds = (
                    compute_wall_phase_used_seconds + remaining
                    if performance_contract is not None
                    else compute_wall_limit_seconds
                )
                compute_wall_budget = {
                    "limit_seconds": compute_wall_limit_seconds,
                    "used_before_seconds": used_before,
                    "used_before_status": compute_wall_ledger["used_status"],
                    "remaining_seconds": remaining,
                    "ledger_path": str(compute_wall_ledger_path),
                    "basis": compute_wall_ledger["basis"],
                    "initial_batch_allowance": compute_wall_ledger.get(
                        "initial_batch_allowance"
                    ),
                    "derived_allowance_margin_seconds": compute_wall_ledger.get(
                        "derived_allowance_margin_seconds"
                    ),
                }
                if performance_contract is not None:
                    compute_wall_budget.update(
                        {
                            "phase_limit_seconds": compute_wall_phase_limit_seconds,
                            "phase_group": compute_wall_phase_group,
                            "phase_used_before_seconds": compute_wall_phase_used_seconds,
                            "batch_remaining_seconds": batch_remaining,
                            "phase_remaining_seconds": phase_remaining,
                            "enforced_limit_seconds": compute_wall_enforced_limit_seconds,
                            "remaining_basis": "min(phase_remaining_seconds, batch_remaining_seconds)",
                        }
                    )
            result["compute_wall_budget"] = compute_wall_budget
            if (
                case_runtime_contract is None
                and remaining <= 0.0
                and not disable_time_stop
            ):
                raise Task041SupervisorError(
                    "Task041 cumulative compute wall budget is exhausted",
                    classification="cumulative_wall_timeout",
                    stage="workflow_wall_budget",
                )
        git_identity = _git_identity(repository_root, source_sha)
        environment_snapshot = _environment_snapshot(repository_root)
        result["identity"] = identity
        if expected_diagnostic_output:
            result["diagnostic_output_policy"] = {
                "enabled": True,
                "model_id": expected_diagnostic_model_id,
                "source": "validated_public_specification",
            }
        result["outer_mpi_size"] = outer_mpi_size
        result["outer_mpi_identity"] = outer_mpi_identity
        result["git"] = git_identity
        result["git_before"] = git_identity
        result["environment"] = environment_snapshot
        child_environment = _child_environment()
        _write_json(root / "environment.json", environment_snapshot)
        _write_json(
            root / "mpi_environment.json",
            {
                "sanitized": True,
                "shell": False,
                "cwd": str(repository_root),
                "outer_mpi_size": outer_mpi_size,
                "outer_mpi_identity": outer_mpi_identity,
                "removed_prefixes": ["OMPI_", "PMIX_", "PMI_"],
                "removed_variables": ["DISPLAY", "XAUTHORITY"],
                "thread_controls": {
                    name: child_environment[name] for name in TASK041_REQUIRED_THREADS
                },
            },
        )
        if balh:
            preflight_authority = sample_factory(public_launcher_pid)
            preflight_kind = (
                _resource_authority_kind(preflight_authority)
                if isinstance(preflight_authority, Mapping)
                else None
            )
            preflight = _sample_record(
                preflight_authority,
                "preflight",
                monotonic() - started,
                authority_kind=preflight_kind,
            )
            preflight.update(
                {
                    "sample_role": "preflight_public_root",
                    "sample_root_pid": public_launcher_pid,
                    "worker_process_group_pid": None,
                    "worker_process_group_gone": None,
                }
            )
            result["resource_preflight"] = preflight
            _append_jsonl(
                root / "numerical_output" / "log" / "memory_stages.jsonl",
                preflight,
            )
            process_tree_rss_cap = runtime_limits.get(
                "process_tree_rss_cap_bytes"
            )
            if process_tree_rss_cap is not None:
                process_tree_rss = preflight.get("process_tree_rss_bytes")
                if not isinstance(process_tree_rss, int):
                    raise Task041SupervisorError(
                        "Task041 process-tree RSS is not measurable at BAL_H preflight",
                        classification="task041_resource_sample_failure",
                        stage="workflow_resource_preflight",
                    )
                if process_tree_rss >= process_tree_rss_cap:
                    raise Task041SupervisorError(
                        "Task041 process-tree RSS cap reached at BAL_H preflight",
                        classification="memory_terminate",
                        stage="workflow_resource_preflight",
                    )
            global_swap_baseline = {
                name: preflight.get(name)
                for name in (
                    "global_swap_used_bytes",
                    "global_pswpin_pages",
                    "global_pswpout_pages",
                )
                if isinstance(preflight.get(name), int)
            }
            minimum_available = phase_limits["producer"].get(
                "min_memavailable_bytes"
            )
            if (
                isinstance(minimum_available, int)
                and not isinstance(preflight.get("host_memavailable_bytes"), int)
            ):
                raise Task041SupervisorError(
                    "Task041 MemAvailable is not measurable at BAL_H preflight",
                    classification="memavailable_unmeasured",
                    stage="workflow_resource_preflight",
                )
            if (
                isinstance(minimum_available, int)
                and preflight["host_memavailable_bytes"] < minimum_available
            ):
                raise Task041SupervisorError(
                    "Task041 MemAvailable is below the BAL_H preflight floor",
                    classification="memavailable_floor",
                    stage="workflow_resource_preflight",
                )
            if (
                isinstance(minimum_available, int)
                and _cgroup_ancestor_headroom_unmeasured(preflight)
            ):
                raise Task041SupervisorError(
                    "Task041 visible cgroup ancestor headroom is not measurable at BAL_H preflight",
                    classification="cgroup_headroom_unmeasured",
                    stage="workflow_resource_preflight",
                )
            if (
                isinstance(minimum_available, int)
                and isinstance(
                    preflight.get("cgroup_ancestor_memory_headroom_bytes"), int
                )
                and preflight["cgroup_ancestor_memory_headroom_bytes"]
                < minimum_available
            ):
                raise Task041SupervisorError(
                    "Task041 visible cgroup ancestor headroom is below the BAL_H preflight floor",
                    classification="cgroup_headroom_floor",
                    stage="workflow_resource_preflight",
                )
        python_entry = Path(os.path.abspath(python_executable or sys.executable))
        if producer_packet_root is not None:
            producer_root = Path(producer_packet_root).resolve()
        producer_command_module = _task041_builders()
        if legacy_native:
            from benchmarks.task041_legacy_native_packet import (
                validate_task041_legacy_native_packet,
            )

            packet = validate_task041_legacy_native_packet(
                legacy_native_packet_descriptor,
                specification,
                source_sha,
            )
            producer_root = Path(packet["producer_root"]).resolve()
            producer_command = None
        elif balh:
            producer_command = producer_command_module["balh_mode_prep"](
                python_entry,
                specification,
                producer_root,
                source_sha,
            )
        elif shortwave:
            producer_command = producer_command_module["shortwave_mode_prep"](
                python_entry,
                specification,
                producer_root,
                source_sha,
            )
        else:
            producer_command = producer_command_module["mode_prep"](
                python_entry,
                repository_root / TASK041_INPUT,
                producer_root,
                source_sha,
            )
        if legacy_native:
            result["workflow_status"] = "producer_reused"
            producer_result = dict(packet["producer_phase"])
            producer_result.update(
                {
                    "phase": "producer",
                    "status": "inherited_legacy_native_phase",
                    "phase_invocation": "not_run_in_current_invocation",
                    "reused": True,
                    "resource_source": "inherited_legacy_native_worker_tree",
                    "producer_resource_qualified": packet[
                        "producer_resource_qualified"
                    ],
                    "supervisor_summary": None,
                    "supervisor_summary_sha256": None,
                    "packet_origin": packet[
                        "legacy_binding"
                    ]["origin"],
                }
            )
            result["producer_reuse"] = {
                "status": "validated_legacy_native_packet",
                "producer_root": str(producer_root),
                "descriptor": packet["descriptor"],
                "resource_qualified": packet["producer_resource_qualified"],
                "phase_status": "inherited_not_run",
                "resource": packet["producer_resource"],
            }
        elif producer_packet_root is not None:
            from benchmarks.task041_balh_workflow import (
                validate_balh_producer_packet,
            )

            result["workflow_status"] = "producer_reused"
            packet = validate_balh_producer_packet(
                producer_root,
                specification,
                source_sha,
                require_public_supervisor_summary=True,
            )
            producer_result = dict(packet["producer_phase"])
            producer_result.update(
                {
                    "phase": "producer",
                    "status": "inherited_public_supervisor_phase",
                    "phase_invocation": "not_run_in_current_invocation",
                    "reused": True,
                    "resource_source": "inherited_public_supervisor_summary",
                    "producer_resource_qualified": packet[
                        "producer_resource_qualified"
                    ],
                    "supervisor_summary": packet[
                        "producer_supervisor_summary"
                    ],
                    "supervisor_summary_sha256": packet[
                        "producer_supervisor_summary_sha256"
                    ],
                }
            )
            result["producer_reuse"] = {
                "status": "validated_inherited_producer",
                "producer_root": str(producer_root),
                "supervisor_summary": packet["producer_supervisor_summary"],
                "supervisor_summary_sha256": packet[
                    "producer_supervisor_summary_sha256"
                ],
                "resource_qualified": packet["producer_resource_qualified"],
                "phase_status": "inherited_not_run",
            }
        else:
            producer_argv = _mpiexec_argv(
                producer_command,
                mpiexec_command,
            )
            result["workflow_status"] = "producer_running"
            producer_result = _run_phase(
                "producer",
                producer_argv,
                producer_root,
                log_root=root / "numerical_output" / "log",
                environment=child_environment,
                repository_root=repository_root,
                workflow_started=started,
                popen_factory=popen_factory,
                sample_factory=sample_factory,
                terminate_factory=terminate_factory,
                monotonic=monotonic,
                sleep=sleep,
                poll_interval=poll_interval,
                memory_stages_path=root
                / "numerical_output"
                / "log"
                / "memory_stages.jsonl",
                marker_path=root
                / "numerical_output"
                / "log"
                / "memory_stage_markers.jsonl",
                process_group_gone=process_group_gone,
                warning_memory_bytes=(
                    phase_limits.get("producer", runtime_limits)["warning_memory_bytes"]
                ),
                hard_memory_bytes=(
                    phase_limits.get("producer", runtime_limits)["hard_memory_bytes"]
                ),
                timeout_seconds=(
                    phase_limits.get("producer", runtime_limits)["timeout_seconds"]
                ),
                phase_elapsed_timeout=timeout_scope == "phase",
                sample_root_pid=public_launcher_pid if balh else None,
                min_memavailable_bytes=(
                    phase_limits.get("producer", {}).get("min_memavailable_bytes")
                    if balh
                    else None
                ),
                min_cgroup_ancestor_headroom_bytes=(
                    phase_limits.get("producer", {}).get("min_memavailable_bytes")
                    if balh
                    else None
                ),
                cumulative_compute_used_seconds=(
                    float(compute_wall_ledger["used_compute_wall_seconds"])
                    if balh and compute_wall_ledger is not None
                    else 0.0
                ),
                cumulative_compute_limit_seconds=(
                    compute_wall_limit_seconds if balh else None
                ),
                global_swap_baseline=global_swap_baseline if balh else None,
                partial_phase_results=result["phase_results"],
                enforce_time_stops=True,
            )
        producer_result["rank_pid_affinity"] = _rank_pid_affinity_artifact(
            producer_root
        )
        result["phase_results"]["producer"] = producer_result
        if _phase_resource_failure(producer_result):
            raise Task041SupervisorError(
                f"producer stopped by {producer_result['termination_reason']}",
                classification=str(_phase_resource_classification(producer_result)),
                stage="producer_resource",
            )
        if producer_result.get("returncode") != 0:
            raise Task041SupervisorError(
                f"producer exited with {producer_result.get('returncode')}",
                classification="task041_producer_failure",
                stage="producer_exit",
            )
        if not legacy_native and producer_result.get("process_group_gone") is not True:
            raise Task041SupervisorError(
                "inherited producer phase lacks a completed process-group record",
                classification="task041_producer_lifecycle_failure",
                stage="producer_handoff",
            )
        if (
            producer_packet_root is None
            and not balh
            and producer_result.get("rss_drop", {}).get("pass") is not True
        ):
            raise Task041SupervisorError(
                "Task041 producer did not release its measured process-tree RSS",
                classification="task041_producer_lifecycle_failure",
                stage="producer_handoff",
            )
        if producer_packet_root is None and not legacy_native and balh:
            from benchmarks.task041_balh_workflow import (
                validate_balh_producer_packet,
            )

            packet = validate_balh_producer_packet(
                producer_root, specification, source_sha
            )
        elif producer_packet_root is None and not legacy_native:
            packet = _validate_producer_packet(
                producer_root, specification, source_sha, identity
            )
        if representative_rhs_binding is not None:
            packet_binding = representative_rhs_binding["packet_binding"]
            packet_identity_file = Path(
                packet.get("identity_path", producer_root / "packet_identity.json")
            )
            if (
                packet_binding["packet_manifest_sha256"]
                != packet["manifest_sha256"]
                or packet_binding["packet_identity_sha256"]
                != _sha256_file(packet_identity_file)
            ):
                raise Task041SupervisorError(
                    "representative RHS probe packet binding does not match the loaded packet",
                    classification="task041_identity_failure",
                    stage="representative_rhs_probe",
                )
            result["representative_rhs_probe"].update(
                {
                    "packet_manifest_sha256": packet["manifest_sha256"],
                    "packet_identity_sha256": packet_binding[
                        "packet_identity_sha256"
                    ],
                    "entries": representative_rhs_binding["entries"],
                    "source_audit": representative_rhs_binding["source_audit"],
                }
            )
        worker_environment = packet["summary"].get("environment")
        if isinstance(worker_environment, Mapping):
            worker_fields = (
                "marker",
                "native_marker",
                "python",
                "python_entry",
                "python_resolved_target",
                "sys_prefix",
                "petsc_scalar_type",
                "petsc_int_type",
                "packages",
                "threads",
                "platform",
            )
            environment_snapshot["worker"] = {
                key: worker_environment[key]
                for key in worker_fields
                if key in worker_environment
            }
            result["environment"] = environment_snapshot
            _write_json(root / "environment.json", environment_snapshot)
        _write_json(root / "selected_mode_manifest.json", packet["compact_manifest"])
        _write_json(
            root / "external_mode_manifest.json",
            {
                "schema": "task041.public.external_mode_manifest.v1",
                "source": "selected_mode_packet_identity",
                "source_sha": packet.get("producer_source_sha", source_sha),
                "identity": {
                    "mode_count": packet["identity"].get("mode_count"),
                    "mpi_size": packet["identity"].get("mpi_size"),
                    "external_keys": packet["identity"].get("external_keys"),
                },
                "packet_manifest_sha256": packet["manifest_sha256"],
            },
        )
        consumer_root = root / "consumer"
        packet_identity_path = Path(
            packet.get("identity_path", producer_root / "packet_identity.json")
        )
        if balh:
            if identity["model_id"] in TASK041_BALH_CANDIDATE_MODEL_IDS:
                consumer_command = producer_command_module["balh_candidate_consumer"](
                    python_entry,
                    specification,
                    Path(packet["manifest"]),
                    packet_identity_path,
                    packet["manifest_sha256"],
                    consumer_root,
                    source_sha,
                    packet.get("producer_source_sha"),
                    packet_origin=packet.get("packet_origin"),
                    legacy_native_binding=packet.get("legacy_native_binding"),
                    disable_time_stop=disable_time_stop,
                    performance_profile=performance_profile,
                    task041_rhs_probe_manifest=(
                        representative_rhs_binding["path"]
                        if representative_rhs_binding is not None
                        else None
                    ),
                    side_setup_schedule=(
                        performance_contract.get("side_setup_schedule")
                        if performance_contract is not None
                        else None
                    ),
                    comparison_mode=(
                        performance_contract.get("comparison_mode")
                        if performance_contract is not None
                        else None
                    ),
                )
            else:
                consumer_command = producer_command_module["balh_exact_consumer"](
                    python_entry,
                    specification,
                    Path(packet["manifest"]),
                    packet_identity_path,
                    packet["manifest_sha256"],
                    consumer_root,
                    source_sha,
                    packet.get("producer_source_sha"),
                    packet_origin=packet.get("packet_origin"),
                    legacy_native_binding=packet.get("legacy_native_binding"),
                )
        elif shortwave:
            consumer_command = producer_command_module["shortwave_consumer"](
                python_entry,
                specification,
                Path(packet["manifest"]),
                packet_identity_path,
                packet["manifest_sha256"],
                consumer_root,
                source_sha,
            )
        else:
            consumer_command = producer_command_module["consumer"](
                python_entry,
                repository_root / TASK041_INPUT,
                Path(packet["manifest"]),
                packet_identity_path,
                packet["manifest_sha256"],
                consumer_root,
                source_sha,
            )
        consumer_argv = _mpiexec_argv(
            consumer_command,
            mpiexec_command,
        )
        result["workflow_status"] = "consumer_running"
        consumer_result = _run_phase(
            "consumer",
            consumer_argv,
            consumer_root,
            log_root=root / "numerical_output" / "log",
            environment=child_environment,
            repository_root=repository_root,
            workflow_started=started,
            popen_factory=popen_factory,
            sample_factory=sample_factory,
            terminate_factory=terminate_factory,
            monotonic=monotonic,
            sleep=sleep,
            poll_interval=poll_interval,
            memory_stages_path=root
            / "numerical_output"
            / "log"
            / "memory_stages.jsonl",
            marker_path=root
            / "numerical_output"
            / "log"
            / "memory_stage_markers.jsonl",
            process_group_gone=process_group_gone,
            warning_memory_bytes=(
                phase_limits.get("consumer", runtime_limits)["warning_memory_bytes"]
            ),
            hard_memory_bytes=(
                phase_limits.get("consumer", runtime_limits)["hard_memory_bytes"]
            ),
            process_tree_rss_warning_bytes=(
                phase_limits.get("consumer", {}).get(
                    "process_tree_rss_warning_bytes"
                )
                if performance_contract is not None
                or case_runtime_contract is not None
                else None
            ),
            process_tree_rss_cap_bytes=(
                phase_limits.get("consumer", {}).get(
                    "process_tree_rss_cap_bytes"
                )
                if performance_contract is not None
                or case_runtime_contract is not None
                else None
            ),
            timeout_seconds=(
                phase_limits.get("consumer", runtime_limits)["timeout_seconds"]
            ),
            phase_elapsed_timeout=(
                timeout_scope == "phase" and case_runtime_contract is None
            ),
            sample_root_pid=public_launcher_pid if balh else None,
            min_memavailable_bytes=(
                phase_limits.get("consumer", {}).get("min_memavailable_bytes")
                if balh
                else None
            ),
            min_cgroup_ancestor_headroom_bytes=(
                phase_limits.get("consumer", {}).get("min_memavailable_bytes")
                if balh
                else None
            ),
            cumulative_compute_used_seconds=(
                compute_wall_phase_used_seconds
                if performance_contract is not None
                or case_runtime_contract is not None
                else (
                    (
                        float(compute_wall_ledger["used_compute_wall_seconds"])
                        + _wall_seconds(producer_result.get("phase_wall_seconds"))
                    )
                    if balh
                    and compute_wall_ledger is not None
                    and producer_result.get("reused") is not True
                    and _wall_seconds(producer_result.get("phase_wall_seconds"))
                    is not None
                    else (
                        float(compute_wall_ledger["used_compute_wall_seconds"])
                        if balh and compute_wall_ledger is not None
                        else 0.0
                    )
                )
            ),
            cumulative_compute_limit_seconds=(
                compute_wall_enforced_limit_seconds
                if performance_contract is not None
                else None
                if case_runtime_contract is not None
                else compute_wall_limit_seconds
                if balh
                else None
            ),
            global_swap_baseline=global_swap_baseline if balh else None,
            partial_phase_results=result["phase_results"],
            enforce_time_stops=_task041_consumer_time_stop_enforced(
                balh=balh,
                disable_time_stop=disable_time_stop,
                phase_limits=phase_limits,
            ),
        )
        consumer_result["rank_pid_affinity"] = _rank_pid_affinity_artifact(
            consumer_root
        )
        result["phase_results"]["consumer"] = consumer_result
        consumer_exit = consumer_result.get("returncode")
        if consumer_exit != 0:
            try:
                consumer_status = _consumer_result(
                    consumer_root,
                    process_group_gone=consumer_result.get("process_group_gone") is True,
                    expected_side_setup_schedule=(
                        performance_contract.get("side_setup_schedule")
                        if performance_contract is not None
                        else None
                    ),
                    expected_comparison_mode=(
                        performance_contract.get("comparison_mode")
                        if performance_contract is not None
                        else None
                    ),
                    **(
                        {"representative_rhs_binding": representative_rhs_binding}
                        if representative_rhs_binding is not None
                        else {}
                    ),
                    **(
                        {
                            "expected_diagnostic_output": True,
                            "expected_diagnostic_model_id": expected_diagnostic_model_id,
                        }
                        if expected_diagnostic_output
                        else {}
                    ),
                )
            except Task041SupervisorError as exc:
                consumer_status = {
                    "complete": False,
                    "classification": "task041_consumer_process_failure",
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                }
                factor_path = consumer_root / "factor_inventory.json"
                if factor_path.is_file():
                    consumer_status["factor_inventory"] = {
                        "artifact": _artifact_metadata(factor_path)
                    }
            result["consumer"] = consumer_status
            resource_classification = _phase_resource_classification(consumer_result)
            worker_classification = consumer_status.get("worker_classification")
            if resource_classification is not None:
                classification = resource_classification
            elif (
                isinstance(worker_classification, str)
                and worker_classification not in {
                    "TASK041_CONSUMER_PASS",
                    "worker_exit0",
                }
            ):
                classification = worker_classification
            else:
                classification = "task041_consumer_process_failure"
            consumer_status["classification"] = classification
            result["exit_status"] = consumer_exit
            raise Task041SupervisorError(
                f"consumer exited with {consumer_exit}",
                classification=classification,
                stage="consumer_exit",
            )
        if _phase_resource_failure(consumer_result):
            raise Task041SupervisorError(
                f"consumer stopped by {consumer_result['termination_reason']}",
                classification=str(_phase_resource_classification(consumer_result)),
                stage="consumer_resource",
            )
        try:
            consumer_status = _consumer_result(
                consumer_root,
                process_group_gone=consumer_result.get("process_group_gone") is True,
                expected_side_setup_schedule=(
                    performance_contract.get("side_setup_schedule")
                    if performance_contract is not None
                    else None
                ),
                expected_comparison_mode=(
                    performance_contract.get("comparison_mode")
                    if performance_contract is not None
                    else None
                ),
                **(
                    {"representative_rhs_binding": representative_rhs_binding}
                    if representative_rhs_binding is not None
                    else {}
                ),
                **(
                    {
                        "expected_diagnostic_output": True,
                        "expected_diagnostic_model_id": expected_diagnostic_model_id,
                    }
                    if expected_diagnostic_output
                    else {}
                ),
            )
        except Task041SupervisorError as exc:
            consumer_status = {
                "complete": False,
                "classification": exc.classification,
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            }
            factor_path = consumer_root / "factor_inventory.json"
            if factor_path.is_file():
                consumer_status["factor_inventory"] = {
                    "artifact": _artifact_metadata(factor_path)
                }
            result["consumer"] = consumer_status
            result["exit_status"] = consumer_exit
            raise Task041SupervisorError(
                "consumer summary could not be validated",
                classification=exc.classification,
                stage="consumer_result",
            ) from exc
        result["consumer"] = consumer_status
        representative_completion = (
            consumer_status.get("completion_scope") == "representative_rhs"
        )
        diagnostic_completion = bool(
            consumer_status.get("diagnostic_result_available") is True
            and consumer_status.get("classification")
            == "DIAGNOSTIC_RESULT_AVAILABLE"
        )
        if not consumer_status["complete"]:
            result["exit_status"] = consumer_exit
            raise Task041SupervisorError(
                "consumer result did not satisfy the complete Task041 contract",
                classification=str(consumer_status["classification"]),
                stage="consumer_result",
            )
        try:
            git_identity_after = _git_identity(repository_root, source_sha)
        except Task041SupervisorError as exc:
            result["git_after"] = {
                "status": "failed",
                "classification": exc.classification,
                "stage": exc.stage,
            }
            raise
        result["git_after"] = git_identity_after
        factor_inventory = consumer_status.get("factor_inventory", {})
        factor_source = consumer_root / "factor_inventory.json"
        if factor_source.is_file():
            _copy_file_bounded(factor_source, root / "factor_inventory.json")
        else:
            if not isinstance(factor_inventory, Mapping):
                factor_inventory = {"status": "not_available"}
            _write_json(root / "factor_inventory.json", factor_inventory)
        result["status"] = (
            "completed_with_diagnostics"
            if diagnostic_completion
            else "representative_rhs_completed"
            if representative_completion
            else "completed"
        )
        result["workflow_status"] = result["status"]
        if diagnostic_completion:
            result["qualification_status"] = "unqualified"
            result["diagnostic_output"] = consumer_status.get("diagnostic_output")
        result["result_classification"] = "worker_exit0"
        result["exit_status"] = 0
    except Task041SupervisorError as exc:
        result["status"] = "failed"
        result["workflow_status"] = f"failed_at_{exc.stage}"
        result["result_classification"] = exc.classification
        result["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "stage": exc.stage,
        }
    except Exception as exc:  # noqa: BLE001 - preserve supervisor failure evidence
        result["status"] = "failed"
        result["workflow_status"] = "failed_at_unexpected"
        result["result_classification"] = "task041_implementation_failure"
        result["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "stage": "unexpected",
        }
    finally:
        if balh:
            phase_roots = {
                "producer": producer_root,
                "consumer": root / "consumer",
            }
            for phase_name, phase_root in phase_roots.items():
                phase_result = result["phase_results"].get(phase_name)
                if (
                    isinstance(phase_result, dict)
                    and "rank_pid_affinity" not in phase_result
                ):
                    phase_result["rank_pid_affinity"] = _rank_pid_affinity_artifact(
                        phase_root
                    )
        phases = list(result["phase_results"].values())
        current_phases = [
            phase for phase in phases if phase.get("reused") is not True
        ]
        total_wall_seconds = max(0.0, monotonic() - started)
        result["wall_seconds"] = total_wall_seconds

        def _phase_peak(phase: Mapping[str, Any], field: str) -> int | None:
            value = phase.get(field)
            return int(value) if isinstance(value, int) else None

        def _aggregate_peak(field: str) -> int | None:
            values = [
                peak
                for phase in current_phases
                if (peak := _phase_peak(phase, field)) is not None
            ]
            return max(values) if values else None

        resource_peak_fields = {
            "memory_authority_bytes": "peak_memory_authority_bytes",
            "process_tree_rss_bytes": "peak_process_tree_rss_bytes",
            "pss_bytes": "peak_pss_bytes",
            "uss_bytes": "peak_uss_bytes",
            "swap_bytes": "peak_swap_bytes",
        }
        qualification_peak_fields = (
            "peak_memory_authority_bytes",
            "peak_process_tree_rss_bytes",
            "peak_swap_bytes",
        )

        def _phase_resource_qualified(phase: Mapping[str, Any]) -> bool:
            return bool(
                isinstance(phase.get("sample_count"), int)
                and phase["sample_count"] > 0
                and phase.get("process_group_gone") is True
                and all(
                    isinstance(phase.get(field), int)
                    for field in qualification_peak_fields
                )
                and phase.get("termination_reason")
                not in {
                    "absolute_memory_limit",
                    "process_tree_rss_unmeasured",
                    "process_tree_rss_limit",
                    "cgroup_headroom_floor",
                    "cgroup_headroom_unmeasured",
                    "memavailable_floor",
                    "memavailable_unmeasured",
                    "swap_detected",
                    "cumulative_wall_timeout",
                    "wall_timeout",
                }
            )

        def _phase_resource_values(phase: Mapping[str, Any]) -> dict[str, Any]:
            return {
                name: phase.get(field)
                for name, field in resource_peak_fields.items()
            }

        producer_phase = result["phase_results"].get("producer", {})
        consumer_phase = result["phase_results"].get("consumer", {})
        producer_qualified = (
            producer_phase.get("producer_resource_qualified") is True
            if producer_phase.get("reused") is True
            else _phase_resource_qualified(producer_phase)
        )
        consumer_qualified = _phase_resource_qualified(consumer_phase)
        derived_common_envelope: dict[str, Any]
        if producer_qualified and consumer_qualified:
            producer_values = _phase_resource_values(producer_phase)
            consumer_values = _phase_resource_values(consumer_phase)
            envelope_peak: dict[str, int | None] = {}
            measurement_status: dict[str, str] = {}
            for name in resource_peak_fields:
                producer_value = producer_values[name]
                consumer_value = consumer_values[name]
                if isinstance(producer_value, int) and isinstance(consumer_value, int):
                    envelope_peak[name] = max(producer_value, consumer_value)
                    measurement_status[name] = "measured"
                else:
                    envelope_peak[name] = None
                    measurement_status[name] = "not_measured"
            derived_common_envelope = {
                "status": "derived",
                "semantics": "max(producer, consumer) per measured resource quantity",
                "peak": envelope_peak,
                "measurement_status": measurement_status,
                "producer": {
                    "values": producer_values,
                    "qualified": producer_qualified,
                    "resource_source": producer_phase.get(
                        "resource_source", "current_invocation"
                    ),
                    "supervisor_summary": producer_phase.get("supervisor_summary"),
                    "supervisor_summary_sha256": producer_phase.get(
                        "supervisor_summary_sha256"
                    ),
                },
                "consumer": {
                    "values": consumer_values,
                    "qualified": consumer_qualified,
                    "resource_source": consumer_phase.get(
                        "resource_source", "current_invocation"
                    ),
                    "run_directory": str(root),
                },
            }
        else:
            derived_common_envelope = {
                "status": "unqualified",
                "semantics": "complete producer/consumer envelope not proven",
                "peak": None,
                "measurement_status": {
                    name: "not_measured" for name in resource_peak_fields
                },
                "producer": {
                    "values": _phase_resource_values(producer_phase),
                    "qualified": producer_qualified,
                    "resource_source": producer_phase.get(
                        "resource_source", "current_invocation"
                    ),
                    "supervisor_summary": producer_phase.get("supervisor_summary"),
                    "supervisor_summary_sha256": producer_phase.get(
                        "supervisor_summary_sha256"
                    ),
                },
                "consumer": {
                    "values": _phase_resource_values(consumer_phase),
                    "qualified": consumer_qualified,
                    "resource_source": consumer_phase.get(
                        "resource_source", "current_invocation"
                    ),
                    "run_directory": str(root),
                },
            }

        result["workflow_peak"] = {
            "memory_authority_bytes": _aggregate_peak("peak_memory_authority_bytes"),
            "process_tree_rss_bytes": _aggregate_peak("peak_process_tree_rss_bytes"),
            "pss_bytes": _aggregate_peak("peak_pss_bytes"),
            "uss_bytes": _aggregate_peak("peak_uss_bytes"),
            "swap_bytes": _aggregate_peak("peak_swap_bytes"),
            "semantics": "current invocation measured phases only",
        }
        current_phase_seconds: dict[str, float] = {}
        for name, phase in result["phase_results"].items():
            if phase.get("reused") is True:
                continue
            seconds = _wall_seconds(phase.get("phase_wall_seconds"))
            if seconds is not None:
                current_phase_seconds[str(phase.get("phase", name))] = seconds
        current_compute_seconds = (
            sum(current_phase_seconds.values()) if current_phase_seconds else None
        )
        result["compute_wall_seconds"] = current_compute_seconds
        if balh and compute_wall_ledger is not None:
            budget = result.get("compute_wall_budget")
            if not isinstance(budget, dict):
                budget = {
                    "limit_seconds": compute_wall_limit_seconds,
                    "used_before_seconds": compute_wall_ledger[
                        "used_compute_wall_seconds"
                    ],
                    "used_before_status": compute_wall_ledger["used_status"],
                    "ledger_path": str(compute_wall_ledger_path),
                    "basis": compute_wall_ledger["basis"],
                    "initial_batch_allowance": compute_wall_ledger.get(
                        "initial_batch_allowance"
                    ),
                    "derived_allowance_margin_seconds": compute_wall_ledger.get(
                        "derived_allowance_margin_seconds"
                    ),
                }
            if supervision_binding is not None:
                budget.update(
                    {
                        "nested_phase_wall_seconds": current_compute_seconds,
                        "current_invocation_seconds": current_compute_seconds,
                        "current_invocation_status": (
                            "measured_nested_phase"
                            if current_compute_seconds is not None
                            else "not_measured_no_phase"
                        ),
                        "used_after": "pending",
                        "used_after_seconds": None,
                        "used_after_status": "pending",
                        "remaining_after_seconds": None,
                        "remaining_after_status": "pending",
                        "ledger_update": "deferred_to_service_finalizer",
                        "ledger_owner": "service_finalizer",
                    }
                )
                result.update(
                    {
                        "nested_phase_wall_seconds": current_compute_seconds,
                        "ledger_update": "deferred_to_service_finalizer",
                        "used_after": "pending",
                    }
                )
            elif current_compute_seconds is not None:
                updated_ledger = _write_task041_compute_wall_ledger(
                    compute_wall_ledger_path,
                    used_before=compute_wall_ledger,
                    current_seconds=current_compute_seconds,
                    run_directory=root,
                    phase_seconds=current_phase_seconds,
                    limit_seconds=compute_wall_limit_seconds,
                    profile_id=performance_profile,
                    phase_group=compute_wall_phase_group,
                    case_id=(
                        case_runtime_contract["case_id"]
                        if case_runtime_contract is not None
                        else None
                    ),
                )
                budget_update = {
                    "current_invocation_seconds": current_compute_seconds,
                    "current_invocation_status": "measured",
                    "used_after_seconds": updated_ledger[
                        "used_compute_wall_seconds"
                    ],
                    "used_after_status": updated_ledger["used_status"],
                    "remaining_after_seconds": (
                        None
                        if case_runtime_contract is not None
                        else max(
                            0.0,
                            compute_wall_limit_seconds
                            - updated_ledger["used_compute_wall_seconds"],
                        )
                    ),
                    "ledger_update": "current_phase_wall_appended",
                }
                if performance_contract is not None:
                    phase_used_after = _task041_v2_group_used(
                        updated_ledger, compute_wall_phase_group
                    )
                    phase_remaining_after = updated_ledger.get(
                        "phase_remaining_seconds", {}
                    ).get(compute_wall_phase_group)
                    batch_remaining_after = max(
                        0.0,
                        compute_wall_limit_seconds
                        - updated_ledger["used_compute_wall_seconds"],
                    )
                    budget_update.update(
                        {
                            "phase_used_after_seconds": phase_used_after,
                            "phase_remaining_after_seconds": phase_remaining_after,
                            "batch_remaining_after_seconds": batch_remaining_after,
                            "remaining_after_seconds": min(
                                value
                                for value in (
                                    phase_remaining_after,
                                    batch_remaining_after,
                                )
                                if isinstance(value, (int, float))
                            ),
                            "remaining_after_basis": (
                                "min(phase_remaining_after_seconds, "
                                "batch_remaining_after_seconds)"
                            ),
                        }
                    )
                budget.update(budget_update)
            else:
                used_before = float(
                    compute_wall_ledger["used_compute_wall_seconds"]
                )
                budget_update = {
                    "current_invocation_seconds": None,
                    "current_invocation_status": "not_measured_no_phase",
                    "used_after_seconds": used_before,
                    "used_after_status": compute_wall_ledger["used_status"],
                    "remaining_after_seconds": (
                        None
                        if case_runtime_contract is not None
                        else max(
                            0.0,
                            compute_wall_limit_seconds - used_before,
                        )
                    ),
                    "ledger_update": "not_appended_no_phase_completed",
                }
                if performance_contract is not None:
                    batch_remaining_after = max(
                        0.0,
                        compute_wall_limit_seconds - used_before,
                    )
                    phase_remaining_after = max(
                        0.0,
                        compute_wall_phase_limit_seconds
                        - compute_wall_phase_used_seconds,
                    )
                    budget_update.update(
                        {
                            "phase_used_after_seconds": compute_wall_phase_used_seconds,
                            "phase_remaining_after_seconds": phase_remaining_after,
                            "batch_remaining_after_seconds": batch_remaining_after,
                            "remaining_after_seconds": min(
                                phase_remaining_after, batch_remaining_after
                            ),
                            "remaining_after_basis": (
                                "min(phase_remaining_after_seconds, "
                                "batch_remaining_after_seconds)"
                            ),
                        }
                    )
                budget.update(budget_update)
            result["compute_wall_budget"] = budget
        reused_producer = any(phase.get("reused") is True for phase in phases)
        current_measured_phase = any(
            phase.get("reused") is not True
            and isinstance(phase.get("sample_count"), int)
            and phase.get("sample_count", 0) > 0
            for phase in phases
        )
        resource_authority = {
            "status": (
                "measured_with_inherited_producer"
                if reused_producer and current_measured_phase
                else "measured"
                if current_measured_phase
                else "inherited_only"
                if reused_producer
                else "not_sampled"
            ),
            "warning_memory_bytes": runtime_limits["warning_memory_bytes"],
            "hard_memory_bytes": runtime_limits["hard_memory_bytes"],
            "swap_limit_bytes": runtime_limits["swap_limit_bytes"],
            "timeout_seconds": runtime_limits["timeout_seconds"],
            "workflow_limits": dict(runtime_limits),
            "swap_semantics": "max(process-tree VmSwap, dedicated job cgroup swap.current)",
            "workflow_peak": result["workflow_peak"],
            "total_wall_seconds": total_wall_seconds,
            "wall_seconds": total_wall_seconds,
            "compute_wall_seconds": current_compute_seconds,
            "compute_wall_semantics": (
                "sum of current non-reused producer/consumer phase wall; "
                "MPI phase wall counted once and read/wait outside phases excluded"
            ),
            "time_stop_override": result.get("time_stop_override"),
            "phase_sampling": {
                name: phase.get("sampling")
                for name, phase in result["phase_results"].items()
            },
            "phase_peaks": {
                name: {
                    "memory_authority_bytes": phase.get("peak_memory_authority_bytes"),
                    "process_tree_rss_bytes": phase.get("peak_process_tree_rss_bytes"),
                    "pss_bytes": phase.get("peak_pss_bytes"),
                    "uss_bytes": phase.get("peak_uss_bytes"),
                    "process_tree_swap_bytes": phase.get(
                        "peak_process_tree_swap_bytes"
                    ),
                    "dedicated_cgroup_swap_bytes": phase.get(
                        "peak_dedicated_cgroup_swap_bytes"
                    ),
                    "swap_bytes": phase.get("peak_swap_bytes"),
                    "cgroup_memory_headroom_bytes": phase.get(
                        "minimum_cgroup_memory_headroom_bytes"
                    ),
                    "cgroup_ancestor_memory_headroom_bytes": phase.get(
                        "minimum_cgroup_ancestor_memory_headroom_bytes"
                    ),
                    "cgroup_history_peak_bytes": phase.get(
                        "cgroup_history_peak_bytes"
                    ),
                    "sample_root_pid": phase.get("sample_root_pid"),
                    "sample_root_scope": phase.get("sample_root_scope"),
                    "worker_process_group_pid": phase.get(
                        "worker_process_group_pid"
                    ),
                    "worker_process_group_gone": phase.get(
                        "worker_process_group_gone"
                    ),
                    "rank_pid_affinity": phase.get("rank_pid_affinity"),
                }
                for name, phase in result["phase_results"].items()
            },
            "derived_common_producer_envelope": derived_common_envelope,
        }
        if balh:
            preflight = result.get("resource_preflight", {})
            if not isinstance(preflight, Mapping):
                preflight = {}

            def _int_values(values: list[Any]) -> list[int]:
                return [value for value in values if isinstance(value, int)]

            runtime_memavailable = _int_values(
                [
                    phase.get("minimum_host_memavailable_bytes")
                    for phase in current_phases
                ]
            )
            observed_memavailable = _int_values(
                [preflight.get("host_memavailable_bytes"), *runtime_memavailable]
            )
            memavailable_floor = phase_limits.get("producer", {}).get(
                "min_memavailable_bytes"
            )
            memavailable_missing = bool(
                not isinstance(preflight.get("host_memavailable_bytes"), int)
                or any(
                    phase.get("termination_reason") == "memavailable_unmeasured"
                    for phase in current_phases
                )
            )
            resource_authority["memavailable"] = {
                "floor_bytes": memavailable_floor,
                "preflight_bytes": preflight.get("host_memavailable_bytes"),
                "minimum_runtime_bytes": (
                    min(runtime_memavailable) if runtime_memavailable else None
                ),
                "minimum_observed_bytes": (
                    min(observed_memavailable) if observed_memavailable else None
                ),
                "status": (
                    "partially_measured"
                    if memavailable_missing and observed_memavailable
                    else "not_measured"
                    if memavailable_missing or not observed_memavailable
                    else "measured"
                ),
                "missing_required_measurement": memavailable_missing,
                "pass": (
                    False
                    if memavailable_missing
                    else None
                    if not observed_memavailable
                    or not isinstance(memavailable_floor, int)
                    else all(value >= memavailable_floor for value in observed_memavailable)
                ),
                "semantics": "host MemAvailable reserve; shared-host diagnostic",
            }
            runtime_cgroup_headroom = _int_values(
                [
                    phase.get("minimum_cgroup_ancestor_memory_headroom_bytes")
                    for phase in current_phases
                ]
            )
            observed_cgroup_headroom = _int_values(
                [
                    preflight.get("cgroup_ancestor_memory_headroom_bytes"),
                    *runtime_cgroup_headroom,
                ]
            )
            preflight_states = preflight.get("cgroup_ancestor_limit_states", [])
            cgroup_states = (
                list(preflight_states)
                if isinstance(preflight_states, list)
                else []
            )
            cgroup_states.append(
                preflight.get("cgroup_ancestor_hard_limit_state")
            )
            for phase in current_phases:
                phase_states = phase.get("cgroup_ancestor_limit_states", [])
                if isinstance(phase_states, list):
                    cgroup_states.extend(phase_states)
            cgroup_states = sorted({state for state in cgroup_states if state})
            cgroup_finite_seen = "finite" in cgroup_states
            cgroup_measurement_missing = bool(
                _cgroup_ancestor_headroom_unmeasured(preflight)
                or any(
                    phase.get("termination_reason")
                    == "cgroup_headroom_unmeasured"
                    or _cgroup_ancestor_headroom_unmeasured(phase)
                    for phase in current_phases
                )
            )
            cgroup_missing_finite = (
                cgroup_measurement_missing
                or cgroup_finite_seen
                and not observed_cgroup_headroom
            )
            cgroup_headroom_reserve = phase_limits.get("producer", {}).get(
                "min_memavailable_bytes"
            )
            resource_authority["cgroup"] = {
                "scope_semantics": preflight.get("cgroup_scope_semantics"),
                "dedicated_job_cgroup": preflight.get(
                    "cgroup_dedicated_job_cgroup"
                ),
                "visible_ancestor_limit_states": cgroup_states,
                "preflight_ancestor_memory": preflight.get(
                    "cgroup_ancestor_memory", []
                ),
                "ancestor_headroom_reserve_bytes": cgroup_headroom_reserve,
                "preflight_ancestor_headroom_bytes": preflight.get(
                    "cgroup_ancestor_memory_headroom_bytes"
                ),
                "minimum_runtime_ancestor_headroom_bytes": (
                    min(runtime_cgroup_headroom)
                    if runtime_cgroup_headroom
                    else None
                ),
                "minimum_observed_ancestor_headroom_bytes": (
                    min(observed_cgroup_headroom)
                    if observed_cgroup_headroom
                    else None
                ),
                "status": (
                    "partially_measured"
                    if cgroup_missing_finite
                    else "measured"
                    if observed_cgroup_headroom
                    else "not_measured"
                ),
                "missing_required_measurement": cgroup_measurement_missing,
                "pass": (
                    False
                    if cgroup_measurement_missing
                    else None
                    if not observed_cgroup_headroom
                    or not isinstance(cgroup_headroom_reserve, int)
                    else all(
                        value >= cgroup_headroom_reserve
                        for value in observed_cgroup_headroom
                    )
                ),
                "history_peak_bytes": max(
                    (
                        phase.get("cgroup_history_peak_bytes")
                        for phase in current_phases
                        if isinstance(phase.get("cgroup_history_peak_bytes"), int)
                    ),
                    default=None,
                ),
                "history_semantics": (
                    "visible cgroup memory.peak history; not the job process-tree peak"
                ),
                "missing_finite_headroom_is": (
                    "not_measured" if cgroup_missing_finite else None
                ),
            }
            phase_global_swap = [
                phase.get("global_swap", {}) for phase in current_phases
            ]
            global_peak_values = _int_values(
                [
                    preflight.get("global_swap_used_bytes"),
                    *[
                        row.get("peak_used_bytes")
                        for row in phase_global_swap
                        if isinstance(row, Mapping)
                    ],
                ]
            )
            global_new_values = _int_values(
                [
                    row.get("new_used_bytes")
                    for row in phase_global_swap
                    if isinstance(row, Mapping)
                ]
            )
            resource_authority["global_swap"] = {
                "baseline_used_bytes": (
                    global_swap_baseline.get("global_swap_used_bytes")
                    if global_swap_baseline is not None
                    else preflight.get("global_swap_used_bytes")
                ),
                "peak_used_bytes": max(global_peak_values, default=None),
                "new_activity_bytes": max(global_new_values, default=None),
                "preexisting_activity_semantics": (
                    "baseline global swap is recorded separately from this invocation"
                ),
                "job_swap_peak_bytes": result["workflow_peak"].get("swap_bytes"),
                "vmstat_deltas": {
                    "pswpin_pages": max(
                        _int_values(
                            [
                                row.get("pswpin_delta_pages")
                                for row in phase_global_swap
                                if isinstance(row, Mapping)
                            ]
                        ),
                        default=None,
                    ),
                    "pswpout_pages": max(
                        _int_values(
                            [
                                row.get("pswpout_delta_pages")
                                for row in phase_global_swap
                                if isinstance(row, Mapping)
                            ]
                        ),
                        default=None,
                    ),
                },
                "semantics": "shared-host diagnostic; job swap authority remains process tree/cgroup",
            }
        if phase_limits:
            resource_authority["phase_limits"] = {
                phase: dict(limits) for phase, limits in phase_limits.items()
            }
        result["resource_authority"] = resource_authority
        if environment_snapshot is not None:
            result.setdefault("environment", environment_snapshot)
            _write_json(root / "environment.json", environment_snapshot)
        if git_identity is not None:
            result.setdefault("git", git_identity)
        if git_identity is not None and "git_after" not in result:
            result["git_after"] = {"status": "not_reached"}
        factor_source = root / "consumer" / "factor_inventory.json"
        if factor_source.is_file():
            _copy_file_bounded(factor_source, root / "factor_inventory.json")
        log_root = root / "numerical_output" / "log"
        for name in ("memory_stages.jsonl", "memory_stage_markers.jsonl"):
            log_path = log_root / name
            if log_path.is_file():
                _copy_file_bounded(log_path, root / name)
        _write_json(root / "resource_summary.json", result["resource_authority"])
        _write_json(root / "workflow_summary.json", result)
        _write_json(root / "supervisor_summary.json", result)
    return result


def _child_environment() -> dict[str, str]:
    from benchmarks.task041_exact_side_workflow import task041_inner_mpi_environment

    return task041_inner_mpi_environment(os.environ)


def _task041_builders() -> dict[str, Callable[..., list[str]]]:
    from benchmarks.task041_balh_workflow import (
        build_task041_balh_candidate_consumer_command,
        build_task041_balh_exact_consumer_command,
        build_task041_balh_mode_prep_command,
    )
    from benchmarks.task041_exact_side_workflow import (
        build_task041_consumer_command,
        build_task041_mode_prep_command,
        build_task041_shortwave_consumer_command,
        build_task041_shortwave_mode_prep_command,
    )

    return {
        "mode_prep": build_task041_mode_prep_command,
        "consumer": build_task041_consumer_command,
        "shortwave_mode_prep": build_task041_shortwave_mode_prep_command,
        "shortwave_consumer": build_task041_shortwave_consumer_command,
        "balh_mode_prep": build_task041_balh_mode_prep_command,
        "balh_exact_consumer": build_task041_balh_exact_consumer_command,
        "balh_candidate_consumer": build_task041_balh_candidate_consumer_command,
    }


__all__ = [
    "TASK041_HARD_MEMORY_BYTES",
    "TASK041_INPUT",
    "TASK041_MODE_COUNT",
    "TASK041_MPI_SIZE",
    "TASK041_PUBLIC_SUPERVISOR_ADAPTER",
    "TASK041_TIMEOUT_SECONDS",
    "TASK041_WARNING_MEMORY_BYTES",
    "Task041SupervisorError",
    "run_task041_public_supervisor",
    "run_task041_supervised_public_command",
]
