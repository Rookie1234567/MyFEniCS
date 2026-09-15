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
from pathlib import Path
from typing import Any

from benchmarks.task034_wsl_resources import resource_authority_sample
from benchmarks.watchdog_process_control import (
    terminate_process_tree,
    worker_process_group_popen_kwargs,
)
from src.io.execution_plan import TASK041_PUBLIC_SUPERVISOR_ADAPTER
from src.io.input_validation import (
    TASK041_BALH_CANDIDATE_MODEL_IDS,
    TASK041_BALH_MODEL_IDS,
    TASK041_BALH_MPI_SIZE,
    TASK041_MODEL_ID,
    TASK041_RUN_ID,
    TASK041_SHORTWAVE_MODEL_IDS,
    TASK041_SHORTWAVE_MPI_SIZE,
    TASK041_SHORTWAVE_WORKFLOW_LIMITS,
    task041_balh_case,
    task041_balh_phase_limits_for_model,
    task041_balh_profile_errors,
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


def _runtime_limits_for_identity(identity: Mapping[str, Any]) -> dict[str, int]:
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
    timeout_seconds: int = TASK041_TIMEOUT_SECONDS,
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
        if enforce_time_stops and (
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
    if profile_id != "task041_schur_speed_v2":
        raise Task041SupervisorError(
            "Task041 supervised public command requires task041_schur_speed_v2",
            classification="task041_identity_failure",
            stage="supervised_public_profile",
        )
    if model_id not in TASK041_BALH_CANDIDATE_MODEL_IDS:
        raise Task041SupervisorError(
            "Task041 supervised public command is limited to BAL_H candidates",
            classification="task041_identity_failure",
            stage="supervised_public_profile",
        )
    active_phase = profile_contract["active_consumer_phase"]
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
            "basis": "min(phase_remaining_seconds, batch_remaining_seconds)",
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
    if effective_remaining <= 0.0:
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
            phase_elapsed_timeout=True,
            sample_root_pid=os.getpid(),
            min_memavailable_bytes=resource_limits["min_memavailable_bytes"],
            min_cgroup_ancestor_headroom_bytes=resource_limits[
                "min_cgroup_ancestor_headroom_bytes"
            ],
            cumulative_compute_used_seconds=phase_used,
            cumulative_compute_limit_seconds=phase_used + effective_remaining,
            global_swap_baseline=global_swap_baseline,
            partial_phase_results=partial_phase_results,
            enforce_time_stops=True,
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
) -> dict[str, Any]:
    size = _outer_mpi_size()
    rank = _outer_mpi_rank()
    markers = {
        "OMPI_COMM_WORLD_SIZE": os.environ.get("OMPI_COMM_WORLD_SIZE"),
        "OMPI_COMM_WORLD_RANK": os.environ.get("OMPI_COMM_WORLD_RANK"),
    }
    if performance_profile is not None:
        from benchmarks.task041_balh_workflow import (
            TASK041_SCHUR_SPEED_V2_PROFILE,
        )

        if performance_profile != TASK041_SCHUR_SPEED_V2_PROFILE:
            raise Task041SupervisorError(
                "unsupported Task041 performance profile",
                classification="task041_identity_failure",
                stage="outer_mpi_identity",
            )
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


def _validate_representative_rhs_result(
    consumer_root: Path,
    summary: Mapping[str, Any],
    binding: Mapping[str, Any],
    *,
    process_group_gone: bool | None,
) -> dict[str, Any]:
    """Independently validate the fixed finite-response worker evidence."""

    from benchmarks.task041_balh_workflow import (
        _TASK041_REPRESENTATIVE_RHS_EXPECTED,
        TASK041_REPRESENTATIVE_RHS_COUNT,
        TASK041_REPRESENTATIVE_RHS_SCOPE,
    )

    failures: list[str] = []
    checks: dict[str, Any] = {}
    expected_entries = binding.get("entries")
    expected_by_ordinal: dict[int, Mapping[str, Any]] = {}
    if isinstance(expected_entries, list):
        for entry in expected_entries:
            if isinstance(entry, Mapping) and isinstance(entry.get("ordinal"), int):
                expected_by_ordinal[int(entry["ordinal"])] = entry
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
        if isinstance(expected_entries, list)
        and all(isinstance(entry, Mapping) for entry in expected_entries)
        else ()
    )
    budget = binding.get("budget")
    checks["fixed_binding"] = bool(
        binding.get("scope") == TASK041_REPRESENTATIVE_RHS_SCOPE
        and len(expected_by_ordinal) == TASK041_REPRESENTATIVE_RHS_COUNT
        and expected_signature == _TASK041_REPRESENTATIVE_RHS_EXPECTED
        and isinstance(budget, Mapping)
        and budget.get("group") == "shared_S0_S1_S3"
    )
    if not checks["fixed_binding"]:
        failures.append("fixed_probe_binding_mismatch")

    manifest_path = binding.get("path")
    manifest_sha = binding.get("sha256")
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

    source_audit = binding.get("source_audit")
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
        and probe_summary.get("path") == binding.get("path")
        and probe_summary.get("sha256") == binding.get("sha256")
        and probe_summary.get("scope") == TASK041_REPRESENTATIVE_RHS_SCOPE
        and probe_summary.get("budget_group") == "shared_S0_S1_S3"
    )
    if not checks["summary_probe_binding"]:
        failures.append("summary_probe_binding_mismatch")

    packet_binding = binding.get("packet_binding")
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
    if isinstance(expected_identity_path, str) and _valid_sha(
        packet_binding.get("packet_identity_sha256") if isinstance(packet_binding, Mapping) else None,
        64,
    ):
        try:
            checks["packet_identity_hash"] = (
                Path(expected_identity_path).is_file()
                and _sha256_file(Path(expected_identity_path))
                == packet_binding["packet_identity_sha256"]
            )
        except OSError:
            checks["packet_identity_hash"] = False
    else:
        checks["packet_identity_hash"] = False
    if not checks["packet_identity_hash"]:
        failures.append("packet_identity_hash_mismatch")

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

    matrix = summary.get("matrix_inventory")
    after_p4 = matrix.get("p4_factor_count_after_cleanup") if isinstance(matrix, Mapping) else None
    after_nested = (
        matrix.get("nested_iterative_ksp_count_after_cleanup")
        if isinstance(matrix, Mapping)
        else None
    )
    checks["component_inventory"] = bool(
        isinstance(matrix, Mapping)
        and matrix.get("qep_calls") == 0
        and matrix.get("consumer_qep_required") is False
        and matrix.get("p4_factor_count_at_setup") == 2
        and matrix.get("nested_iterative_ksp_count_at_setup") == 2
        and matrix.get("p6_factor_count") == 0
        and matrix.get("global_direct_factor_count") == 0
        and isinstance(after_p4, Mapping)
        and set(after_p4) == {"bottom", "top"}
        and all(value == 0 for value in after_p4.values())
        and isinstance(after_nested, Mapping)
        and set(after_nested) == {"bottom", "top"}
        and all(value == 0 for value in after_nested.values())
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


def _consumer_result(
    consumer_root: Path,
    *,
    process_group_gone: bool | None = None,
    representative_rhs_binding: Mapping[str, Any] | None = None,
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
    representative_scope = representative_rhs_binding is not None
    representative_validation = (
        _validate_representative_rhs_result(
            consumer_root,
            summary,
            representative_rhs_binding,
            process_group_gone=process_group_gone,
        )
        if representative_rhs_binding is not None
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
        representative_lifecycle_gate if representative_scope else regular_lifecycle_gate
    )
    marker_gate = isinstance(observed, list) and "final_cleanup_complete" in observed
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
        and worker_classification == "TASK041_CONSUMER_PASS"
        and summary.get("status") == "task041_consumer_completed"
        and isinstance(gates, Mapping)
        and gates.get("pass") is True
        and regular_lifecycle_gate
        and process_group_gone is True
        and marker_gate
    )
    complete = representative_complete or regular_complete
    if complete:
        classification = "worker_exit0"
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
        "process_group_gone": process_group_gone,
        "lifecycle_gate": lifecycle_gate,
        "representative_validation": representative_validation,
        "completion_scope": (
            "representative_rhs" if representative_complete else "formal"
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
    representative_rhs_binding: dict[str, Any] | None = None
    compute_wall_limit_seconds = TASK041_CUMULATIVE_COMPUTE_WALL_SECONDS
    compute_wall_phase_limit_seconds = TASK041_CUMULATIVE_COMPUTE_WALL_SECONDS
    compute_wall_phase_group: str | None = None
    compute_wall_phase_used_seconds = 0.0
    compute_wall_enforced_limit_seconds = TASK041_CUMULATIVE_COMPUTE_WALL_SECONDS
    supervision_binding: dict[str, Any] | None = None
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
        outer_mpi_identity = (
            _outer_mpi_launch_identity(performance_profile)
            if performance_profile is not None
            else _outer_mpi_launch_identity()
        )
        outer_mpi_size = outer_mpi_identity["mpi_size"]
        identity = _validate_specification(specification, repository_root)
        runtime_limits = _runtime_limits_for_identity(identity)
        result["limits"] = dict(runtime_limits)
        shortwave = identity["model_id"] in TASK041_SHORTWAVE_MODEL_IDS
        balh = identity["model_id"] in TASK041_BALH_MODEL_IDS
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
            if performance_contract is None:
                raise Task041SupervisorError(
                    "supervision record requires task041_schur_speed_v2",
                    classification="task041_identity_failure",
                    stage="supervision_record",
                )
            supervision_binding = _load_task041_supervision_record(
                task041_supervision_record,
                profile_id=performance_contract["profile_id"],
                model_id=identity["model_id"],
                source_sha=source_sha,
                scope=performance_contract["scope"],
                representative_rhs_probe=(
                    {
                        "path": representative_rhs_binding["path"],
                        "sha256": representative_rhs_binding["sha256"],
                    }
                    if representative_rhs_binding is not None
                    else None
                ),
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
            if remaining <= 0.0 and not disable_time_stop:
                raise Task041SupervisorError(
                    "Task041 cumulative compute wall budget is exhausted",
                    classification="cumulative_wall_timeout",
                    stage="workflow_wall_budget",
                )
        git_identity = _git_identity(repository_root, source_sha)
        environment_snapshot = _environment_snapshot(repository_root)
        result["identity"] = identity
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
                else None
            ),
            process_tree_rss_cap_bytes=(
                phase_limits.get("consumer", {}).get(
                    "process_tree_rss_cap_bytes"
                )
                if performance_contract is not None
                else None
            ),
            timeout_seconds=(
                phase_limits.get("consumer", runtime_limits)["timeout_seconds"]
            ),
            phase_elapsed_timeout=timeout_scope == "phase",
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
                else compute_wall_limit_seconds
                if balh
                else None
            ),
            global_swap_baseline=global_swap_baseline if balh else None,
            partial_phase_results=result["phase_results"],
            enforce_time_stops=not disable_time_stop if balh else True,
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
                    **(
                        {"representative_rhs_binding": representative_rhs_binding}
                        if representative_rhs_binding is not None
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
                **(
                    {"representative_rhs_binding": representative_rhs_binding}
                    if representative_rhs_binding is not None
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
            "representative_rhs_completed" if representative_completion else "completed"
        )
        result["workflow_status"] = (
            "representative_rhs_completed"
            if representative_completion
            else "completed"
        )
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
                )
                budget_update = {
                    "current_invocation_seconds": current_compute_seconds,
                    "current_invocation_status": "measured",
                    "used_after_seconds": updated_ledger[
                        "used_compute_wall_seconds"
                    ],
                    "used_after_status": updated_ledger["used_status"],
                    "remaining_after_seconds": max(
                        0.0,
                        compute_wall_limit_seconds
                        - updated_ledger["used_compute_wall_seconds"],
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
                    "remaining_after_seconds": max(
                        0.0,
                        compute_wall_limit_seconds - used_before,
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
