"""Inline MPI1 supervisor for the Task041 producer/consumer workflow.

The public process only validates the resolved input and supervises two fresh
MPI1 children.  Numerical assembly remains in the existing Task041 workers.
"""

from __future__ import annotations

import hashlib
import json
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
    TASK041_MODEL_ID,
    TASK041_RUN_ID,
    task041_profile_errors,
)
from src.io.resolved_config import resolved_config_sha256

TASK041_BRANCH = "codex/20260902-task41-mpi1-shortwave-hybrid-capacity"
TASK041_INPUT = "input/official/task041/5nm_p6h4_m480_mpi1.dat"
TASK041_MODE_COUNT = 480
TASK041_MPI_SIZE = 1
TASK041_WARNING_MEMORY_BYTES = 192 * 2**30
TASK041_HARD_MEMORY_BYTES = 256 * 2**30
TASK041_TIMEOUT_SECONDS = 172800
TASK041_REQUIRED_THREADS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)

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


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


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
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


def _numeric(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _sample_record(
    authority: Mapping[str, Any], phase: str, elapsed: float
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
    memory = _numeric(authority.get("memory_authority_bytes"))
    rss = _numeric(process_tree.get("rss_bytes"))
    process_swap = _numeric(process_tree.get("swap_bytes"))
    dedicated_swap = 0
    if job_cgroup.get("dedicated_job_cgroup") is True:
        dedicated_swap = _numeric(job_cgroup.get("swap_current_bytes")) or 0
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
        "phase": phase,
        "elapsed_seconds": float(elapsed),
        "memory_authority_bytes": memory,
        "job_no_swap": authority.get("job_no_swap"),
        "process_tree_rss_bytes": rss,
        "process_tree_swap_bytes": process_swap,
        "dedicated_cgroup_swap_bytes": dedicated_swap,
        "swap_bytes": swap,
        "pss_bytes": pss,
        "uss_bytes": uss,
        "all_status_readable": process_tree.get("all_status_readable"),
    }


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
) -> dict[str, Any]:
    if phase_root.exists():
        raise Task041SupervisorError(
            f"{phase} run directory must be fresh: {phase_root}",
            classification="task041_implementation_failure",
            stage=f"{phase}_root_preflight",
        )
    phase_started = monotonic()
    samples: list[dict[str, Any]] = []
    warning_reached = False
    termination_reason: str | None = None
    termination: dict[str, Any] | None = None
    process: Any | None = None
    cleanup_attempted = False
    group_gone = False
    stdout_path = log_root / f"{phase}_stdout.txt"
    try:
        _append_jsonl(
            marker_path,
            {"stage": f"{phase}_started", "wall_seconds": phase_started - workflow_started},
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
            while True:
                returncode = process.poll()
                now = monotonic()
                if returncode is not None:
                    break
                authority = sample_factory(process.pid)
                record = _sample_record(
                    authority, phase, now - workflow_started
                )
                if record["all_status_readable"] is not True:
                    raise Task041SupervisorError(
                        f"{phase} process-tree sample is not fully readable",
                        classification="task041_resource_sample_failure",
                        stage=f"{phase}_resource_sample",
                    )
                samples.append(record)
                _append_jsonl(memory_stages_path, record)
                memory = record["memory_authority_bytes"]
                warning_reached = warning_reached or memory >= TASK041_WARNING_MEMORY_BYTES
                if memory >= TASK041_HARD_MEMORY_BYTES:
                    termination_reason = "absolute_memory_limit"
                elif record["swap_bytes"] > 0 or record["job_no_swap"] is not True:
                    termination_reason = "swap_detected"
                elif now - workflow_started >= TASK041_TIMEOUT_SECONDS:
                    termination_reason = "wall_timeout"
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

        before_rss = samples[-1]["process_tree_rss_bytes"] if samples else None
        after_rss = 0
        rss_drop = {
            "before_process_tree_rss_bytes": before_rss,
            "after_process_tree_rss_bytes": after_rss,
            "process_group_gone": group_gone,
            "pass": bool(isinstance(before_rss, int) and after_rss < before_rss),
        }
        _append_jsonl(
            marker_path,
            {
                "stage": f"{phase}_finished",
                "wall_seconds": monotonic() - workflow_started,
                "returncode": returncode,
                "termination_reason": termination_reason,
                "rss_drop": rss_drop,
            },
        )
    except Exception:
        if process is not None and not cleanup_attempted:
            try:
                gone = bool(process_group_gone(process.pid))
            except Exception:  # noqa: BLE001 - failed liveness probe requires cleanup
                gone = False
            if not gone:
                cleanup_attempted = True
                _terminate_and_verify(process, terminate_factory, process_group_gone)
        raise

    def _peak(name: str) -> int:
        values = [row[name] for row in samples if isinstance(row.get(name), int)]
        return max(values, default=0)

    return {
        "phase": phase,
        "argv": list(argv),
        "stdout": str(stdout_path),
        "returncode": returncode,
        "wall_seconds": monotonic() - phase_started,
        "sample_count": len(samples),
        "warning_reached": warning_reached,
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
    }


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


def _outer_mpi_launch_identity() -> dict[str, Any]:
    size = _outer_mpi_size()
    rank = _outer_mpi_rank()
    markers = {
        "OMPI_COMM_WORLD_SIZE": os.environ.get("OMPI_COMM_WORLD_SIZE"),
        "OMPI_COMM_WORLD_RANK": os.environ.get("OMPI_COMM_WORLD_RANK"),
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
    failures: list[str] = []
    try:
        failures.extend(
            f"{field}: {message}"
            for field, message in task041_profile_errors(snapshot)
        )
    except Exception as exc:  # noqa: BLE001 - malformed input is fail-closed
        failures.append(f"Task041 profile validation failed: {exc}")
    expected_input = (repository_root / TASK041_INPUT).resolve()
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
        "model_id": TASK041_MODEL_ID,
        "run_id": TASK041_RUN_ID,
        "input_sha256": specification.input_sha256,
        "physical_model_sha256": specification.physical_model_sha256,
        "resolved_config_sha256": resolved_sha,
        "requested_modes": TASK041_MODE_COUNT,
        "mpi_size": TASK041_MPI_SIZE,
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
        "model_id": TASK041_MODEL_ID,
        "run_id": TASK041_RUN_ID,
        "mode_count": TASK041_MODE_COUNT,
        "mpi_size": TASK041_MPI_SIZE,
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


def _consumer_result(
    consumer_root: Path, *, process_group_gone: bool | None = None
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
    lifecycle_gate = (
        isinstance(lifecycle, Mapping)
        and lifecycle.get("setup_released") is True
        and lifecycle.get("rss_drop_pass") is True
        and lifecycle.get("rss_marker_emitted") is True
    )
    marker_gate = isinstance(observed, list) and "final_cleanup_complete" in observed
    complete = bool(
        worker_classification == "TASK041_CONSUMER_PASS"
        and summary.get("status") == "task041_consumer_completed"
        and isinstance(gates, Mapping)
        and gates.get("pass") is True
        and lifecycle_gate
        and process_group_gone is True
        and marker_gate
    )
    if complete:
        classification = "worker_exit0"
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
    }


def _phase_resource_failure(phase_result: Mapping[str, Any]) -> bool:
    return phase_result.get("termination_reason") in {
        "absolute_memory_limit",
        "swap_detected",
        "wall_timeout",
    }


def _phase_resource_classification(
    phase_result: Mapping[str, Any],
) -> str | None:
    return {
        "absolute_memory_limit": "memory_terminate",
        "swap_detected": "swap_policy_violation",
        "wall_timeout": "timeout",
    }.get(str(phase_result.get("termination_reason")))


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
) -> dict[str, Any]:
    """Run the two fresh Task041 MPI1 children from the public MPI1 process."""

    root = Path(run_directory).resolve()
    repository_root = Path(__file__).resolve().parents[2]
    started = monotonic()
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
        outer_mpi_identity = _outer_mpi_launch_identity()
        outer_mpi_size = outer_mpi_identity["mpi_size"]
        identity = _validate_specification(specification, repository_root)
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
        python_entry = Path(os.path.abspath(python_executable or sys.executable))
        producer_root = root / "producer"
        producer_command_module = _task041_builders()
        producer_argv = _mpiexec_argv(
            producer_command_module["mode_prep"](
                python_entry,
                repository_root / TASK041_INPUT,
                producer_root,
                source_sha,
            ),
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
        packet = _validate_producer_packet(
            producer_root, specification, source_sha, identity
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
                "source_sha": source_sha,
                "identity": {
                    "mode_count": packet["identity"].get("mode_count"),
                    "mpi_size": packet["identity"].get("mpi_size"),
                    "external_keys": packet["identity"].get("external_keys"),
                },
                "packet_manifest_sha256": packet["manifest_sha256"],
            },
        )
        if producer_result.get("rss_drop", {}).get("pass") is not True:
            raise Task041SupervisorError(
                "producer process-group/RSS handoff gate failed",
                classification="task041_producer_lifecycle_failure",
                stage="producer_handoff",
            )
        consumer_root = root / "consumer"
        consumer_argv = _mpiexec_argv(
            producer_command_module["consumer"](
                python_entry,
                repository_root / TASK041_INPUT,
                Path(packet["manifest"]),
                producer_root / "packet_identity.json",
                packet["manifest_sha256"],
                consumer_root,
                source_sha,
            ),
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
        )
        result["phase_results"]["consumer"] = consumer_result
        consumer_exit = consumer_result.get("returncode")
        if consumer_exit != 0:
            try:
                consumer_status = _consumer_result(
                    consumer_root,
                    process_group_gone=consumer_result.get("process_group_gone") is True,
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
            (root / "factor_inventory.json").write_bytes(factor_source.read_bytes())
        else:
            if not isinstance(factor_inventory, Mapping):
                factor_inventory = {"status": "not_available"}
            _write_json(root / "factor_inventory.json", factor_inventory)
        result["status"] = "completed"
        result["workflow_status"] = "completed"
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
        phases = list(result["phase_results"].values())
        total_wall_seconds = max(0.0, monotonic() - started)
        result["wall_seconds"] = total_wall_seconds
        result["workflow_peak"] = {
            "memory_authority_bytes": max(
                (int(phase.get("peak_memory_authority_bytes", 0)) for phase in phases),
                default=0,
            ),
            "process_tree_rss_bytes": max(
                (int(phase.get("peak_process_tree_rss_bytes", 0)) for phase in phases),
                default=0,
            ),
            "pss_bytes": max(
                (int(phase.get("peak_pss_bytes", 0)) for phase in phases),
                default=0,
            ),
            "uss_bytes": max(
                (int(phase.get("peak_uss_bytes", 0)) for phase in phases),
                default=0,
            ),
            "swap_bytes": max(
                (int(phase.get("peak_swap_bytes", 0)) for phase in phases),
                default=0,
            ),
            "semantics": "max(producer, consumer), never sum",
        }
        result["resource_authority"] = {
            "status": "measured" if phases else "not_sampled",
            "warning_memory_bytes": TASK041_WARNING_MEMORY_BYTES,
            "hard_memory_bytes": TASK041_HARD_MEMORY_BYTES,
            "swap_limit_bytes": 0,
            "swap_semantics": "max(process-tree VmSwap, dedicated job cgroup swap.current)",
            "workflow_peak": result["workflow_peak"],
            "total_wall_seconds": total_wall_seconds,
            "wall_seconds": total_wall_seconds,
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
                }
                for name, phase in result["phase_results"].items()
            },
        }
        if environment_snapshot is not None:
            result.setdefault("environment", environment_snapshot)
            _write_json(root / "environment.json", environment_snapshot)
        if git_identity is not None:
            result.setdefault("git", git_identity)
        if git_identity is not None and "git_after" not in result:
            result["git_after"] = {"status": "not_reached"}
        factor_source = root / "consumer" / "factor_inventory.json"
        if factor_source.is_file():
            (root / "factor_inventory.json").write_bytes(factor_source.read_bytes())
        log_root = root / "numerical_output" / "log"
        for name in ("memory_stages.jsonl", "memory_stage_markers.jsonl"):
            log_path = log_root / name
            if log_path.is_file():
                (root / name).write_bytes(log_path.read_bytes())
        _write_json(root / "resource_summary.json", result["resource_authority"])
        _write_json(root / "workflow_summary.json", result)
        _write_json(root / "supervisor_summary.json", result)
    return result


def _child_environment() -> dict[str, str]:
    from benchmarks.task041_exact_side_workflow import task041_inner_mpi_environment

    return task041_inner_mpi_environment(os.environ)


def _task041_builders() -> dict[str, Callable[..., list[str]]]:
    from benchmarks.task041_exact_side_workflow import (
        build_task041_consumer_command,
        build_task041_mode_prep_command,
    )

    return {
        "mode_prep": build_task041_mode_prep_command,
        "consumer": build_task041_consumer_command,
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
]
