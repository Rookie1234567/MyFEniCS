"""Small Task38 provenance launcher and resource classification loop."""

from __future__ import annotations

import os
import platform
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from benchmarks.task034_wsl_resources import (
    cgroup_snapshot,
    resource_authority_sample,
    wsl_memory_snapshot,
)
from benchmarks.watchdog_process_control import (
    terminate_process_tree,
    worker_process_group_popen_kwargs,
)

from src.io.execution_plan import (
    CONTRACT_PROBE_ADAPTER,
    ExecutionPlan,
    build_execution_plan,
    method_adapter_identity,
)
from src.io.input_loader import InputError
from src.io.input_validation import task039_model_id_matches
from src.io.resolved_config import canonical_json_bytes, write_resolved_config
from src.io.run_specification import RunSpecification


PopenFactory = Callable[..., Any]
SampleFactory = Callable[[int], dict[str, Any]]
TerminateFactory = Callable[[Any], dict[str, Any]]


def task039_resource_ledger(
    actual_available_gib: float,
    *,
    observed_process_tree_gib: float,
    observed_swap_gib: float,
    available_classification: str = "measured",
) -> dict[str, Any]:
    """Return the Task39 resource decision using the existing launcher sample."""

    available = float(actual_available_gib)
    observed = float(observed_process_tree_gib)
    swap = float(observed_swap_gib)
    if (
        not math.isfinite(available)
        or available <= 0.0
        or not math.isfinite(observed)
        or observed < 0.0
        or not math.isfinite(swap)
        or swap < 0.0
    ):
        raise ValueError("Task39 resource samples must be finite and non-negative")
    if available_classification not in {"measured", "estimated"}:
        raise ValueError("available_classification must be measured or estimated")
    hard_stop = min(220.0, 0.90 * available)
    stop_reason = None
    if swap > 0.0:
        stop_reason = "swap_policy_violation"
    elif observed >= hard_stop:
        stop_reason = "memory_hard_stop"
    return {
        "warning_memory_gib": {
            "value": 180.0,
            "classification": "contract",
        },
        "hard_stop_memory_gib": {
            "value": hard_stop,
            "classification": "derived",
            "source_classification": available_classification,
        },
        "actual_available_gib": {
            "value": available,
            "classification": available_classification,
        },
        "observed_process_tree_gib": {
            "value": observed,
            "classification": "measured",
        },
        "observed_swap_gib": {
            "value": swap,
            "classification": "measured",
        },
        "stop": stop_reason is not None,
        "stop_reason": stop_reason,
    }


def _task039_memory_budget() -> dict[str, Any]:
    """Read the finite WSL/cgroup capacity used by the Task39 hard stop."""

    memory = wsl_memory_snapshot()
    cgroup = cgroup_snapshot("self")
    candidates: list[tuple[str, int]] = []
    total = memory.get("mem_total_bytes")
    if isinstance(total, int) and total > 0:
        candidates.append(("wsl_mem_total", total))
    cgroup_limit = cgroup.get("memory_limit_bytes")
    if isinstance(cgroup_limit, int) and cgroup_limit > 0:
        candidates.append(("cgroup_memory_max", cgroup_limit))
    if not candidates:
        raise InputError(
            "Task39 resource preflight cannot read a finite WSL/cgroup memory limit"
        )
    source_name, limit_bytes = min(candidates, key=lambda item: item[1])
    actual_limit_gib = limit_bytes / 1024**3
    ledger = task039_resource_ledger(
        actual_limit_gib,
        observed_process_tree_gib=0.0,
        observed_swap_gib=0.0,
        available_classification="measured",
    )
    ledger.pop("observed_process_tree_gib", None)
    ledger.pop("observed_swap_gib", None)
    ledger.pop("stop", None)
    ledger.pop("stop_reason", None)
    ledger["source"] = {
        "selected": source_name,
        "wsl_mem_total_bytes": total,
        "cgroup_memory_max_bytes": cgroup_limit,
        "classification": "measured",
    }
    ledger["configured_terminate_memory_gib"] = 220.0
    ledger["effective_terminate_memory_gib"] = ledger["hard_stop_memory_gib"]["value"]
    return ledger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_sha(cwd: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InputError(f"cannot determine git source SHA: {exc}") from exc
    value = completed.stdout.strip()
    if (
        len(value) != 40
        or value.lower() != value
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise InputError("git source SHA is not a complete 40-character commit")
    return value


def _validate_source_sha(value: str) -> str:
    if (
        len(value) != 40
        or value.lower() != value
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise InputError(
            "source SHA must be a complete 40-character lowercase hex value"
        )
    return value


def _environment_identity() -> dict[str, Any]:
    return {
        "python_executable": os.path.abspath(sys.executable),
        "platform": platform.platform(),
        "qualified_activation": os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION"),
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_bytes(canonical_json_bytes(value) + b"\n")


def _write_text_hash(path: Path, value: str) -> None:
    path.write_text(value + "\n", encoding="ascii")


def _timestamp_directory(
    specification: RunSpecification, timestamp: str | None
) -> Path:
    parent = Path(specification.expected_output_parent).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    name = timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    directory = parent / name
    try:
        directory.mkdir()
    except FileExistsError as exc:
        raise InputError(f"Task38 output collision: {directory}") from exc
    return directory


def _base_manifest(
    specification: RunSpecification,
    *,
    run_directory: Path,
    source_sha: str,
    adapter_identity: str,
    start_time: str,
    resolved_sha: str,
) -> dict[str, Any]:
    snapshot = specification.as_jsonable()
    manifest = {
        "model_id": snapshot["model_id"],
        "run_id": snapshot["run_id"],
        "comparison_group": snapshot["comparison_group"],
        "method": snapshot["method"]["kind"],
        "solver": snapshot["solver"],
        "mpi_size": snapshot["execution"]["mpi_size"],
        "requested_modes": snapshot["method"].get("requested_modes_per_direction"),
        "input_path": str(specification.source_path),
        "input_sha256": specification.input_sha256,
        "physical_model_sha256": specification.physical_model_sha256,
        "source_sha": source_sha,
        "environment": _environment_identity(),
        "resolved_config_sha256": resolved_sha,
        "start_time": start_time,
        "end_time": None,
        "exit_status": None,
        "result_classification": "not_run",
        "status": "launching",
        "output_directory": str(run_directory),
        "numerical_output_directory": str(run_directory / "numerical_output"),
        "resolved_method_adapter": adapter_identity,
    }
    material_provenance = snapshot["derived"].get("material_provenance")
    if material_provenance is not None:
        manifest["material_provenance"] = material_provenance
    external_mode_inventory = snapshot["derived"].get("external_mode_inventory")
    if external_mode_inventory is not None:
        manifest["external_mode_inventory"] = external_mode_inventory
    return manifest


def _initial_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "launching",
        "result_classification": "not_run",
        "exit_status": None,
        "run_id": manifest["run_id"],
        "output_directory": manifest["output_directory"],
        "numerical_output_directory": manifest["numerical_output_directory"],
        "resource_authority": {"status": "not_sampled"},
    }


def _write_bootstrap(
    specification: RunSpecification,
    run_directory: Path,
    *,
    source_sha: str,
    adapter_identity: str,
    start_time: str,
) -> tuple[dict[str, Any], str]:
    resolved_sha = write_resolved_config(
        specification, run_directory / "resolved_config.json"
    )
    (run_directory / "input_original.dat").write_bytes(specification.raw_input_bytes)
    _write_text_hash(run_directory / "input_sha256.txt", specification.input_sha256)
    _write_text_hash(
        run_directory / "physical_model_sha256.txt",
        specification.physical_model_sha256,
    )
    _write_text_hash(run_directory / "source_sha.txt", source_sha)
    manifest = _base_manifest(
        specification,
        run_directory=run_directory,
        source_sha=source_sha,
        adapter_identity=adapter_identity,
        start_time=start_time,
        resolved_sha=resolved_sha,
    )
    _write_json(run_directory / "run_manifest.json", manifest)
    _write_json(run_directory / "run_summary.json", _initial_summary(manifest))
    return manifest, resolved_sha


def _authority_readable(authority: dict[str, Any]) -> bool:
    process_tree = authority.get("process_tree", {})
    return bool(process_tree.get("all_status_readable"))


def _swap_bytes(authority: dict[str, Any]) -> int:
    process_tree = authority.get("process_tree", {})
    cgroup = authority.get("job_cgroup", {})
    dedicated_swap = (
        int(cgroup.get("swap_current_bytes") or 0)
        if cgroup.get("dedicated_job_cgroup")
        else 0
    )
    return max(
        int(process_tree.get("swap_bytes") or 0),
        dedicated_swap,
    )


def _run_worker(
    plan: ExecutionPlan,
    specification: RunSpecification,
    run_directory: Path,
    *,
    popen_factory: PopenFactory,
    sample_factory: SampleFactory,
    terminate_factory: TerminateFactory,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    poll_interval: float,
) -> dict[str, Any]:
    execution = specification.execution
    warning_limit = float(execution["warning_memory_gib"]) * 1024**3
    terminate_limit = float(execution["terminate_memory_gib"]) * 1024**3
    task039_budget = None
    model_id = str(specification.identity.get("model_id", ""))
    method = str(specification.method.get("kind", ""))
    requested_modes = specification.method.get("requested_modes_per_direction")
    if task039_model_id_matches(method, model_id, requested_modes):
        task039_budget = _task039_memory_budget()
        warning_limit = 180.0 * 1024**3
        terminate_limit = (
            float(task039_budget["effective_terminate_memory_gib"]) * 1024**3
        )
    timeout = float(execution["timeout_seconds"])
    sample_count = 0
    peak_authority = 0
    peak_process_tree = 0
    peak_swap = 0
    zero_swap_observed = True
    warning_triggered = False
    termination: dict[str, Any] | None = None
    classification: str | None = None
    started = monotonic()
    stdout_path = run_directory / "worker_stdout.txt"
    with stdout_path.open("w", encoding="utf-8") as stdout:
        process = popen_factory(
            list(plan.argv),
            shell=False,
            cwd=Path(__file__).resolve().parents[2],
            stdout=stdout,
            stderr=subprocess.STDOUT,
            text=True,
            **worker_process_group_popen_kwargs(),
        )
        while True:
            authority = sample_factory(process.pid)
            if _authority_readable(authority):
                sample_count += 1
                memory = int(authority.get("memory_authority_bytes") or 0)
                process_tree_rss = int(
                    authority.get("process_tree", {}).get("rss_bytes") or 0
                )
                swap_bytes = _swap_bytes(authority)
                peak_authority = max(peak_authority, memory)
                peak_process_tree = max(peak_process_tree, process_tree_rss)
                peak_swap = max(peak_swap, swap_bytes)
                zero_swap_observed = zero_swap_observed and swap_bytes == 0
                warning_triggered = warning_triggered or memory >= warning_limit
                if execution["require_zero_swap"] and swap_bytes > 0:
                    termination = terminate_factory(process)
                    classification = "swap_policy_violation"
                elif memory >= terminate_limit:
                    termination = terminate_factory(process)
                    classification = "memory_terminate"
            if classification is not None:
                break
            if process.poll() is not None:
                break
            if monotonic() - started >= timeout:
                termination = terminate_factory(process)
                classification = "timeout"
                break
            sleep(poll_interval)
        if process.poll() is None:
            process.wait()
        exit_status = process.poll()

    if classification is None:
        if exit_status == 0 and plan.contract_probe:
            classification = "contract_probe_pass"
        else:
            classification = "worker_exit0" if exit_status == 0 else "worker_nonzero"
    resource_authority = {
        "status": "measured" if sample_count else "not_available",
        "sample_count": sample_count,
        "warning_triggered": warning_triggered,
        "process_tree_peak_rss_mb": peak_process_tree / 1024**2,
        "memory_authority_peak_mb": peak_authority / 1024**2,
        "process_tree_peak_swap_mb": peak_swap / 1024**2,
        "require_zero_swap": execution["require_zero_swap"],
        "zero_swap_observed": zero_swap_observed if sample_count else None,
    }
    if task039_budget is not None:
        resource_authority["task039_memory_budget"] = task039_budget
    return {
        "exit_status": exit_status,
        "result_classification": classification,
        "termination": termination,
        "resource_authority": resource_authority,
    }


def launch_specification(
    specification: RunSpecification,
    *,
    source_sha: str | None = None,
    timestamp: str | None = None,
    contract_probe: bool = False,
    python_executable: str | Path | None = None,
    mpiexec_command: str | None = None,
    popen_factory: PopenFactory = subprocess.Popen,
    sample_factory: SampleFactory = resource_authority_sample,
    terminate_factory: TerminateFactory = terminate_process_tree,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    poll_interval: float = 0.25,
) -> dict[str, Any]:
    """Launch one resolved input or fail closed before numerical execution."""

    source = _validate_source_sha(
        source_sha
        if source_sha is not None
        else _source_sha(Path(__file__).resolve().parents[2])
    )
    adapter = (
        CONTRACT_PROBE_ADAPTER
        if contract_probe
        else method_adapter_identity(
            str(specification.method["kind"]),
            str(specification.identity.get("model_id", "")),
        )
    )
    run_directory = _timestamp_directory(specification, timestamp)
    start_time = _now()
    manifest, _resolved_sha = _write_bootstrap(
        specification,
        run_directory,
        source_sha=source,
        adapter_identity=adapter,
        start_time=start_time,
    )
    plan = build_execution_plan(
        specification,
        run_directory,
        source_sha=source,
        python_executable=python_executable,
        mpiexec_command=mpiexec_command,
        adapter_identity=adapter,
        contract_probe=contract_probe,
    )
    if not plan.adapter_available:
        result = {
            "exit_status": None,
            "result_classification": "adapter_unavailable",
            "resource_authority": {"status": "not_sampled"},
        }
    else:
        try:
            result = _run_worker(
                plan,
                specification,
                run_directory,
                popen_factory=popen_factory,
                sample_factory=sample_factory,
                terminate_factory=terminate_factory,
                monotonic=monotonic,
                sleep=sleep,
                poll_interval=poll_interval,
            )
        except OSError as exc:
            result = {
                "exit_status": None,
                "result_classification": "worker_launch_error",
                "error": str(exc),
                "resource_authority": {"status": "not_sampled"},
            }
    end_time = _now()
    manifest.update(
        {
            "end_time": end_time,
            "exit_status": result["exit_status"],
            "result_classification": result["result_classification"],
            "status": "finished",
        }
    )
    summary = {
        "status": "finished",
        "run_id": manifest["run_id"],
        "output_directory": str(run_directory),
        "numerical_output_directory": str(run_directory / "numerical_output"),
        **result,
    }
    _write_json(run_directory / "run_manifest.json", manifest)
    _write_json(run_directory / "run_summary.json", summary)
    return {
        "run_directory": str(run_directory),
        "manifest": str(run_directory / "run_manifest.json"),
        "summary": str(run_directory / "run_summary.json"),
        **result,
    }


__all__ = ["launch_specification"]
