"""Small Task38 provenance launcher and resource classification loop."""

from __future__ import annotations

import json
import os
import platform
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any, Callable, Mapping

from benchmarks.task034_wsl_resources import (
    cgroup_snapshot,
    resource_authority_sample,
    wsl_memory_snapshot,
)
from benchmarks.watchdog_process_control import (
    terminate_process_tree,
    worker_process_group_popen_kwargs,
)
from benchmarks.task039_memory_telemetry import (
    task039_h5_hybrid_direct_formal_profile,
    task039_h5_hybrid_iterative_formal_profile,
    task039_read_new_markers,
    task039_v3_2d_formal_profile,
    task039_v4_h4_hybrid_direct_formal_profile,
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
V5_H4_BLR_SIDE_SETUP_PEAK_LIMIT_GIB = 59.7638938904
V6_H4_POST_COMPACTION_SETUP_PEAK_LIMIT_GIB = 42.019652939
V6_H4_POST_COMPACTION_SETUP_HARD_STOP_BYTES = 45118258790
V7_H4_EXACT_SIDE_LIMIT_SETUP_PEAK_LIMIT_GIB = 84.039305878
V7_H4_EXACT_SIDE_LIMIT_SETUP_HARD_STOP_BYTES = 90236517581
V7_H4_EXACT_SIDE_FULL_FORMAL_HARD_STOP_BYTES = 100262797312
V7_H4_EXACT_SIDE_FULL_FORMAL_DEFAULT_TIMEOUT_SECONDS = 21600
V7_H4_EXACT_SIDE_FULL_FORMAL_EXTENSION_TIMEOUT_SECONDS = 28800
V6_H4_PORT_MODAL_CONSTRUCTION_LIMIT_GIB = 22.0
V6_H4_PORT_MODAL_CONSTRUCTION_HARD_STOP_BYTES = 23622320128
V7_STREAMED_PETROV_HARD_STOP_BYTES = 100262797312
V7_STREAMED_PETROV_CONSUMER_HARD_STOP_BYTES = 90236517581
V8_H4_LAYER_BLOCK_RECONSTRUCTION_HARD_STOP_BYTES = 224000000000


def _v5_h4_blr_candidate_interval_peak(
    memory_stages_path: Path,
    process_samples_path: Path,
    side: str,
    *,
    marker_prefix: str = "v5_blr_candidate",
    begin_suffix: str = "setup_begin",
    end_suffix: str = "setup_end",
    begin_stage: str | None = None,
    end_stage: str | None = None,
    limit_gib: float = V5_H4_BLR_SIDE_SETUP_PEAK_LIMIT_GIB,
) -> dict[str, Any]:
    begin_stage = (
        begin_stage
        if begin_stage is not None
        else f"{marker_prefix}_{side}_{begin_suffix}"
    )
    end_stage = (
        end_stage if end_stage is not None else f"{marker_prefix}_{side}_{end_suffix}"
    )
    stage_rows: dict[str, dict[str, Any]] = {}
    if not memory_stages_path.is_file() or not process_samples_path.is_file():
        return {
            "status": "not_available",
            "peak_process_tree_rss_gib": None,
            "limit_gib": limit_gib,
            "pass": False,
            "reason": "missing_stage_or_process_tree_samples",
        }
    with memory_stages_path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            stage = row.get("stage")
            if stage in (begin_stage, end_stage):
                stage_rows[stage] = row
    begin = stage_rows.get(begin_stage, {}).get("sample_elapsed_seconds")
    end = stage_rows.get(end_stage, {}).get("sample_elapsed_seconds")
    if (
        not isinstance(begin, (int, float))
        or not isinstance(end, (int, float))
        or float(end) < float(begin)
        or stage_rows[begin_stage].get("sample_status") != "measured"
        or stage_rows[end_stage].get("sample_status") != "measured"
    ):
        return {
            "status": "not_available",
            "peak_process_tree_rss_gib": None,
            "limit_gib": limit_gib,
            "pass": False,
            "reason": "begin_or_end_sample_elapsed_missing",
        }
    samples = []
    with process_samples_path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            elapsed = row.get("elapsed_seconds")
            rss = row.get("rss_bytes")
            if (
                isinstance(elapsed, (int, float))
                and isinstance(rss, int)
                and row.get("sample_status") == "measured"
                and float(begin) <= float(elapsed) <= float(end)
            ):
                samples.append(row)
    if not samples:
        return {
            "status": "not_available",
            "peak_process_tree_rss_gib": None,
            "limit_gib": limit_gib,
            "pass": False,
            "reason": "no_process_tree_sample_in_closed_interval",
            "begin_sample_elapsed_seconds": float(begin),
            "end_sample_elapsed_seconds": float(end),
        }
    peak_bytes = max(int(row["rss_bytes"]) for row in samples)
    peak_gib = peak_bytes / 1024**3
    return {
        "status": "measured",
        "begin_sample_elapsed_seconds": float(begin),
        "end_sample_elapsed_seconds": float(end),
        "sample_count": len(samples),
        "peak_process_tree_rss_bytes": peak_bytes,
        "peak_process_tree_rss_gib": peak_gib,
        "limit_gib": limit_gib,
        "pass": bool(peak_gib <= limit_gib),
        "time_basis": "parent_process_tree_sample_elapsed_seconds",
    }


def _v6_post_compaction_resource_authority(
    memory_stages_path: Path,
    process_samples_path: Path,
    object_ledger_path: Path,
    *,
    input_absolute_terminate_memory_bytes: int | None,
    effective_absolute_terminate_memory_bytes: int,
    setup_limit_gib: float,
    outer_ready_limit_gib: float,
    poll_interval_seconds: float,
) -> dict[str, Any]:
    """Summarize V6 parent samples and finalizer fields without guessing."""

    stage_rows: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    try:
        with memory_stages_path.open(encoding="utf-8") as stream:
            stage_rows = [json.loads(line) for line in stream]
        with process_samples_path.open(encoding="utf-8") as stream:
            samples = [json.loads(line) for line in stream]
    except (OSError, json.JSONDecodeError):
        stage_rows = []
        samples = []

    measured_samples = [
        row
        for row in samples
        if row.get("sample_status") == "measured"
        and isinstance(row.get("rss_bytes"), int)
        and isinstance(row.get("swap_bytes"), int)
    ]
    if measured_samples:
        peak_rss = max(int(row["rss_bytes"]) for row in measured_samples)
        peak_swap = max(int(row["swap_bytes"]) for row in measured_samples)
        overall = {
            "status": "measured",
            "peak_process_tree_rss_bytes": peak_rss,
            "peak_process_tree_rss_gib": peak_rss / 1024**3,
            "peak_swap_bytes": peak_swap,
            "zero_swap": peak_swap == 0,
            "pass": bool(peak_rss / 1024**3 <= setup_limit_gib),
        }
        swap = {
            "status": "measured",
            "peak_swap_bytes": peak_swap,
            "zero_swap": peak_swap == 0,
            "pass": peak_swap == 0,
        }
    else:
        overall = {
            "status": "not_available",
            "peak_process_tree_rss_bytes": None,
            "peak_process_tree_rss_gib": None,
            "peak_swap_bytes": None,
            "zero_swap": None,
            "pass": False,
        }
        swap = {
            "status": "not_available",
            "peak_swap_bytes": None,
            "zero_swap": None,
            "pass": False,
        }

    outer_rows = [
        row
        for row in stage_rows
        if row.get("stage") == "outer_ksp_setup_ready"
        and row.get("sample_status") == "measured"
        and isinstance(row.get("rss_bytes"), int)
    ]
    if len(outer_rows) == 1:
        outer_rss = int(outer_rows[0]["rss_bytes"])
        outer_ready = {
            "status": "measured",
            "sample_elapsed_seconds": outer_rows[0].get("sample_elapsed_seconds"),
            "process_tree_rss_bytes": outer_rss,
            "process_tree_rss_gib": outer_rss / 1024**3,
            "limit_gib": outer_ready_limit_gib,
            "pass": bool(outer_rss / 1024**3 <= outer_ready_limit_gib),
        }
    else:
        outer_ready = {
            "status": "not_available",
            "sample_elapsed_seconds": None,
            "process_tree_rss_bytes": None,
            "process_tree_rss_gib": None,
            "limit_gib": outer_ready_limit_gib,
            "pass": False,
        }

    lifecycle = {
        "status": "not_available",
        "factor_count_after_final_cleanup": None,
        "packet_qep_refs_released": None,
        "pass": False,
    }
    try:
        ledger = json.loads(object_ledger_path.read_text(encoding="utf-8"))
        objects = ledger.get("objects", {})
        action_details = objects.get("exact_side_factors", {}).get("details", {})
        counts = action_details.get("factor_count_after_cleanup")
        qep_released = all(
            objects.get(name, {}).get("destroyed") is True
            for name in ("qep_matrices", "selected_basis")
        )
        if (
            isinstance(counts, Mapping)
            and all(
                isinstance(counts.get(side), int) and counts.get(side) == 0
                for side in ("bottom", "top")
            )
            and all(name in objects for name in ("qep_matrices", "selected_basis"))
        ):
            lifecycle = {
                "status": "measured",
                "factor_count_after_final_cleanup": {
                    side: int(counts[side]) for side in ("bottom", "top")
                },
                "packet_qep_refs_released": qep_released,
                "pass": qep_released,
                "source": "memory_object_ledger",
            }
    except (OSError, json.JSONDecodeError, AttributeError):
        pass

    complete = all(
        item["status"] == "measured" for item in (overall, outer_ready, swap, lifecycle)
    )
    return {
        "status": "measured" if complete else "not_available",
        "input_absolute_terminate_memory_bytes": input_absolute_terminate_memory_bytes,
        "effective_absolute_terminate_memory_bytes": effective_absolute_terminate_memory_bytes,
        "effective_hard_stop_memory_gib": effective_absolute_terminate_memory_bytes
        / 1024**3,
        "process_tree_termination_enforced": True,
        "poll_interval_seconds": poll_interval_seconds,
        "setup_peak_limit_gib": setup_limit_gib,
        "outer_ready_peak_limit_gib": outer_ready_limit_gib,
        "overall_process_tree": overall,
        "outer_ksp_setup_ready": outer_ready,
        "swap": swap,
        "final_lifecycle": lifecycle,
        "resource_pass": bool(
            complete
            and overall["pass"]
            and outer_ready["pass"]
            and swap["pass"]
            and lifecycle["pass"]
        ),
    }


def task039_resource_ledger(
    actual_available_gib: float,
    *,
    observed_process_tree_gib: float,
    observed_swap_gib: float,
    available_classification: str = "measured",
    configured_warning_gib: float = 180.0,
    configured_terminate_gib: float = 220.0,
    absolute_terminate_memory_bytes: int | None = None,
) -> dict[str, Any]:
    """Return the Task39 resource decision using the existing launcher sample."""

    available = float(actual_available_gib)
    observed = float(observed_process_tree_gib)
    swap = float(observed_swap_gib)
    configured_warning = float(configured_warning_gib)
    configured_terminate = float(configured_terminate_gib)
    if absolute_terminate_memory_bytes is not None and (
        isinstance(absolute_terminate_memory_bytes, bool)
        or not isinstance(absolute_terminate_memory_bytes, int)
        or absolute_terminate_memory_bytes <= 0
    ):
        raise ValueError("absolute termination must be a positive integer byte count")
    if (
        not math.isfinite(available)
        or available <= 0.0
        or not math.isfinite(observed)
        or observed < 0.0
        or not math.isfinite(swap)
        or swap < 0.0
        or not math.isfinite(configured_warning)
        or configured_warning < 0.0
        or not math.isfinite(configured_terminate)
        or configured_terminate <= 0.0
    ):
        raise ValueError("Task39 resource samples must be finite and non-negative")
    if available_classification not in {"measured", "estimated"}:
        raise ValueError("available_classification must be measured or estimated")
    absolute_terminate_gib = (
        None
        if absolute_terminate_memory_bytes is None
        else absolute_terminate_memory_bytes / 1024**3
    )
    hard_stop = (
        min(configured_terminate, 0.90 * available)
        if absolute_terminate_gib is None
        else absolute_terminate_gib
    )
    stop_reason = None
    if swap > 0.0:
        stop_reason = "swap_policy_violation"
    elif (
        observed >= hard_stop
        if absolute_terminate_gib is None
        else observed * 1024**3 >= absolute_terminate_memory_bytes
    ):
        stop_reason = "memory_hard_stop"
    ledger = {
        "warning_memory_gib": {
            "value": configured_warning,
            "classification": "contract",
        },
        "hard_stop_memory_gib": {
            "value": hard_stop,
            "classification": "contract"
            if absolute_terminate_memory_bytes is not None
            else "derived",
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
        "configured_warning_memory_gib": configured_warning,
        "configured_terminate_memory_gib": configured_terminate,
        "effective_terminate_memory_gib": hard_stop,
        "stop": stop_reason is not None,
        "stop_reason": stop_reason,
    }
    if absolute_terminate_memory_bytes is not None:
        ledger.update(
            {
                "memory_termination_policy": "absolute_bytes",
                "configured_critical_memory_gib": configured_terminate,
                "critical_checkpoint_crossed": observed >= configured_terminate,
                "absolute_terminate_memory_bytes": absolute_terminate_memory_bytes,
                "effective_hard_stop_memory_bytes": absolute_terminate_memory_bytes,
            }
        )
    return ledger


def _task039_memory_budget(
    execution: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
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
    configured_warning = (
        180.0 if execution is None else float(execution["warning_memory_gib"])
    )
    configured_terminate = (
        220.0 if execution is None else float(execution["terminate_memory_gib"])
    )
    absolute_terminate_memory_bytes = (
        None if execution is None else execution.get("absolute_terminate_memory_bytes")
    )
    ledger = task039_resource_ledger(
        actual_limit_gib,
        observed_process_tree_gib=0.0,
        observed_swap_gib=0.0,
        available_classification="measured",
        configured_warning_gib=configured_warning,
        configured_terminate_gib=configured_terminate,
        absolute_terminate_memory_bytes=absolute_terminate_memory_bytes,
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
    specification_payload = specification.as_jsonable()
    solver_payload = specification_payload.get("solver", {})
    formal_direct_v2_h5 = task039_h5_hybrid_direct_formal_profile(specification_payload)
    formal_iterative_v2_h5 = task039_h5_hybrid_iterative_formal_profile(
        specification_payload
    )
    formal_v2_h5 = formal_direct_v2_h5 or formal_iterative_v2_h5
    formal_v3_2d = task039_v3_2d_formal_profile(specification_payload)
    formal_v4_h4 = (
        method == "full3d_direct"
        and solver_payload.get("direct_factor_lifecycle") == "release_before_recovery"
    )
    formal_v4_h4_hybrid = task039_v4_h4_hybrid_direct_formal_profile(
        specification_payload
    )
    formal_v5_h4_setup = (
        getattr(plan, "method", "") == "task039_v5_h4_exact_side_setup_only"
    )
    formal_v5_h4_blr = (
        getattr(plan, "method", "") == "task039_v5_h4_mumps_blr_side_component"
    )
    formal_v5_h4_fixed_budget = (
        getattr(plan, "method", "") == "task039_v5_h4_fixed_budget_bottom_component"
    )
    formal_v6_h4_setup = (
        getattr(plan, "method", "") == "task039_v6_h4_post_compaction_setup_only"
    )
    formal_v7_h4_setup = (
        getattr(plan, "method", "") == "task039_v7_h4_exact_side_limit_setup_only"
    )
    formal_v7_h4_full = (
        getattr(plan, "method", "") == "task039_v7_h4_exact_side_full_formal"
    )
    formal_v6_h4_port_modal = (
        getattr(plan, "method", "") == "task039_v6_h4_port_modal_bottom_component"
    )
    formal_v7_streamed_producer = (
        getattr(plan, "method", "") == "task039_v7_streamed_bottom_basis_producer"
    )
    formal_v7_streamed_consumer = (
        getattr(plan, "method", "") == "task039_v7_streamed_bottom_petrov_consumer"
    )
    formal_v8_layer_block = (
        getattr(plan, "method", "") == "task039_v8_h4_layer_block_reconstruction"
    )
    formal_telemetry = (
        formal_v2_h5
        or formal_v3_2d
        or formal_v4_h4
        or formal_v4_h4_hybrid
        or formal_v5_h4_setup
        or formal_v5_h4_blr
        or formal_v5_h4_fixed_budget
        or formal_v6_h4_setup
        or formal_v7_h4_setup
        or formal_v7_h4_full
        or formal_v6_h4_port_modal
        or formal_v7_streamed_producer
        or formal_v7_streamed_consumer
        or formal_v8_layer_block
    )
    if task039_model_id_matches(method, model_id, requested_modes):
        task039_budget = _task039_memory_budget(execution)
        warning_limit = float(task039_budget["configured_warning_memory_gib"]) * 1024**3
        absolute_terminate_memory_bytes = task039_budget.get(
            "absolute_terminate_memory_bytes"
        )
        if absolute_terminate_memory_bytes is None:
            terminate_limit = (
                float(task039_budget["effective_terminate_memory_gib"]) * 1024**3
            )
            critical_limit = None
        else:
            if not math.isfinite(poll_interval) or poll_interval > 0.25:
                raise InputError(
                    "absolute byte termination requires poll_interval <= 0.25 seconds"
                )
            terminate_limit = float(absolute_terminate_memory_bytes)
            critical_limit = (
                float(task039_budget["configured_critical_memory_gib"]) * 1024**3
            )
    else:
        absolute_terminate_memory_bytes = None
        critical_limit = None
    if formal_v6_h4_setup:
        absolute_terminate_memory_bytes = V6_H4_POST_COMPACTION_SETUP_HARD_STOP_BYTES
        terminate_limit = float(absolute_terminate_memory_bytes)
    if formal_v7_h4_setup:
        absolute_terminate_memory_bytes = V7_H4_EXACT_SIDE_LIMIT_SETUP_HARD_STOP_BYTES
        terminate_limit = float(absolute_terminate_memory_bytes)
    if formal_v7_h4_full:
        absolute_terminate_memory_bytes = V7_H4_EXACT_SIDE_FULL_FORMAL_HARD_STOP_BYTES
        terminate_limit = float(absolute_terminate_memory_bytes)
    if formal_v6_h4_port_modal:
        absolute_terminate_memory_bytes = V6_H4_PORT_MODAL_CONSTRUCTION_HARD_STOP_BYTES
        terminate_limit = float(absolute_terminate_memory_bytes)
    if formal_v7_streamed_producer:
        absolute_terminate_memory_bytes = V7_STREAMED_PETROV_HARD_STOP_BYTES
        terminate_limit = float(absolute_terminate_memory_bytes)
    if formal_v7_streamed_consumer:
        absolute_terminate_memory_bytes = V7_STREAMED_PETROV_CONSUMER_HARD_STOP_BYTES
        terminate_limit = float(absolute_terminate_memory_bytes)
    timeout = float(execution["timeout_seconds"])
    if formal_v7_h4_full:
        timeout = float(V7_H4_EXACT_SIDE_FULL_FORMAL_DEFAULT_TIMEOUT_SECONDS)
    full_outer_entered = False
    full_initial_residual: float | None = None
    full_min_residual: float | None = None
    full_extension_used = False
    full_timeout_decision: dict[str, Any] | None = (
        {"status": "pending"} if formal_v7_h4_full else None
    )
    sample_count = 0
    peak_authority = 0
    peak_process_tree = 0
    peak_swap = 0
    zero_swap_observed = True
    warning_triggered = False
    critical_checkpoint_crossed = False
    critical_checkpoint_first_bytes = None
    peak_pss = None
    peak_uss = None
    smaps_attempted_sample_count = 0
    smaps_complete_sample_count = 0
    termination: dict[str, Any] | None = None
    classification: str | None = None
    formal_samples_path = (
        run_directory / "numerical_output" / "process_tree_samples.jsonl"
    )
    formal_stages_path = run_directory / "numerical_output" / "memory_stages.jsonl"
    formal_markers_path = (
        run_directory / "numerical_output" / "memory_stage_markers.raw.jsonl"
    )
    formal_progress_path = run_directory / "numerical_output" / "progress_3d.jsonl"
    formal_object_ledger_path = (
        run_directory / "numerical_output" / "memory_object_ledger.json"
    )
    formal_sample_stream = None
    formal_stage_stream = None
    formal_marker_offset = 0
    formal_aligned_stage_count = 0
    formal_written_sample_count = 0
    formal_last_sample: dict[str, Any] | None = None

    def _formal_sample(authority: Mapping[str, Any], elapsed: float) -> dict[str, Any]:
        process_tree = authority.get("process_tree", {})
        smaps = process_tree.get("smaps")
        pss = uss = None
        if isinstance(smaps, Mapping) and smaps.get("complete") is True:
            if isinstance(smaps.get("pss_bytes"), int):
                pss = smaps["pss_bytes"]
            if isinstance(smaps.get("uss_bytes"), int):
                uss = smaps["uss_bytes"]
        rss = process_tree.get("rss_bytes")
        rss = rss if isinstance(rss, int) else None
        swap = _swap_bytes(dict(authority))
        return {
            "schema": "task039.v2-process-tree-sample.v1",
            "timestamp_utc": _now(),
            "elapsed_seconds": elapsed,
            "pid": process_tree.get("root_pid"),
            "memory_authority_bytes": authority.get("memory_authority_bytes"),
            "rss_bytes": rss,
            "pss_bytes": pss,
            "uss_bytes": uss,
            "swap_bytes": swap,
            "sample_status": (
                "measured" if _authority_readable(dict(authority)) else "not_available"
            ),
        }

    def _align_formal_markers(sample: dict[str, Any] | None) -> None:
        nonlocal formal_marker_offset, formal_aligned_stage_count
        nonlocal full_outer_entered, full_initial_residual, full_min_residual
        if (
            not (
                formal_direct_v2_h5
                or formal_v4_h4
                or formal_v4_h4_hybrid
                or formal_v5_h4_setup
                or formal_v5_h4_blr
                or formal_v5_h4_fixed_budget
                or formal_v6_h4_setup
                or formal_v7_h4_setup
                or formal_v7_h4_full
                or formal_v6_h4_port_modal
                or formal_v7_streamed_producer
                or formal_v7_streamed_consumer
                or formal_v8_layer_block
            )
            or formal_stage_stream is None
        ):
            return
        marker_source = formal_progress_path if formal_v4_h4 else formal_markers_path
        markers, formal_marker_offset = task039_read_new_markers(
            marker_source, formal_marker_offset
        )
        for marker in markers:
            if formal_v7_h4_full:
                marker_stage = marker.get("stage")
                if marker_stage in {
                    "outer_solve_begin",
                    "outer_solve_progress",
                    "outer_solve_ready",
                }:
                    full_outer_entered = True
                detail = marker.get("detail")
                details = [detail]
                if isinstance(detail, Mapping):
                    details.extend(
                        detail.get(name) for name in ("solve", "postsolve", "residuals")
                    )
                for candidate in details:
                    if not isinstance(candidate, Mapping):
                        continue
                    value = candidate.get("multimetric_max_true_residual")
                    if isinstance(value, (int, float)) and math.isfinite(float(value)):
                        residual = float(value)
                        if full_initial_residual is None:
                            full_initial_residual = residual
                        full_min_residual = (
                            residual
                            if full_min_residual is None
                            else min(full_min_residual, residual)
                        )
                        break
            stage_index = marker.get("stage_index")
            if (
                formal_v4_h4
                or formal_v5_h4_setup
                or formal_v5_h4_blr
                or formal_v5_h4_fixed_budget
                or formal_v6_h4_setup
                or formal_v7_h4_setup
                or formal_v7_h4_full
                or formal_v6_h4_port_modal
                or formal_v7_streamed_producer
                or formal_v7_streamed_consumer
                or formal_v8_layer_block
            ) and stage_index is None:
                stage_index = formal_aligned_stage_count
            row = {
                "schema": "task039.v2-memory-stage-alignment.v1",
                "stage": marker.get("stage"),
                "status": marker.get("status"),
                "stage_index": stage_index,
                "marker_elapsed_seconds": marker.get("elapsed_seconds"),
                "sample_elapsed_seconds": (
                    None if sample is None else sample.get("elapsed_seconds")
                ),
                "marker_sample_delta_seconds": (
                    None
                    if sample is None
                    else float(sample["elapsed_seconds"])
                    - float(marker["elapsed_seconds"])
                ),
                "rss_bytes": None if sample is None else sample.get("rss_bytes"),
                "pss_bytes": None if sample is None else sample.get("pss_bytes"),
                "uss_bytes": None if sample is None else sample.get("uss_bytes"),
                "swap_bytes": None if sample is None else sample.get("swap_bytes"),
                "sample_status": (
                    "not_available" if sample is None else sample.get("sample_status")
                ),
                "marker_detail": marker.get("detail"),
                "object_capacity": marker.get("object_capacity"),
            }
            formal_stage_stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            formal_stage_stream.flush()
            formal_aligned_stage_count += 1

    started = monotonic()
    stdout_path = run_directory / "worker_stdout.txt"
    if formal_telemetry:
        formal_samples_path.parent.mkdir(parents=True, exist_ok=True)
        formal_samples_path.unlink(missing_ok=True)
        formal_sample_stream = formal_samples_path.open("a", encoding="utf-8")
        if (
            formal_direct_v2_h5
            or formal_v4_h4
            or formal_v4_h4_hybrid
            or formal_v5_h4_setup
            or formal_v5_h4_blr
            or formal_v5_h4_fixed_budget
            or formal_v6_h4_setup
            or formal_v7_h4_setup
            or formal_v7_h4_full
            or formal_v6_h4_port_modal
            or formal_v7_streamed_producer
            or formal_v7_streamed_consumer
            or formal_v8_layer_block
        ):
            formal_stages_path.unlink(missing_ok=True)
            formal_stage_stream = formal_stages_path.open("a", encoding="utf-8")
    try:
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
                if formal_telemetry:
                    formal_written_sample_count += 1
                    formal_last_sample = _formal_sample(
                        authority, monotonic() - started
                    )
                    formal_sample_stream.write(
                        json.dumps(formal_last_sample, ensure_ascii=False) + "\n"
                    )
                    formal_sample_stream.flush()
                    _align_formal_markers(formal_last_sample)
                process_tree = authority.get("process_tree", {})
                smaps = process_tree.get("smaps")
                if isinstance(smaps, dict):
                    smaps_attempted_sample_count += 1
                    if smaps.get("complete") is True:
                        pss = smaps.get("pss_bytes")
                        uss = smaps.get("uss_bytes")
                        if isinstance(pss, int) and isinstance(uss, int):
                            smaps_complete_sample_count += 1
                            peak_pss = pss if peak_pss is None else max(peak_pss, pss)
                            peak_uss = uss if peak_uss is None else max(peak_uss, uss)
                if _authority_readable(authority):
                    sample_count += 1
                    memory = int(authority.get("memory_authority_bytes") or 0)
                    process_tree_rss = int(process_tree.get("rss_bytes") or 0)
                    swap_bytes = _swap_bytes(authority)
                    peak_authority = max(peak_authority, memory)
                    peak_process_tree = max(peak_process_tree, process_tree_rss)
                    peak_swap = max(peak_swap, swap_bytes)
                    zero_swap_observed = zero_swap_observed and swap_bytes == 0
                    warning_triggered = warning_triggered or memory >= warning_limit
                    if (
                        critical_limit is not None
                        and memory >= critical_limit
                        and not critical_checkpoint_crossed
                    ):
                        critical_checkpoint_crossed = True
                        critical_checkpoint_first_bytes = memory
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
                    if formal_v7_h4_full and not full_extension_used:
                        residual_decreased = bool(
                            full_initial_residual is not None
                            and full_min_residual is not None
                            and full_min_residual < full_initial_residual
                        )
                        extension_allowed = bool(
                            sample_count > 0
                            and full_outer_entered
                            and peak_process_tree
                            < V7_H4_EXACT_SIDE_FULL_FORMAL_HARD_STOP_BYTES
                            and peak_swap == 0
                            and residual_decreased
                        )
                        if extension_allowed:
                            timeout = float(
                                V7_H4_EXACT_SIDE_FULL_FORMAL_EXTENSION_TIMEOUT_SECONDS
                            )
                            full_extension_used = True
                            full_timeout_decision = {
                                "status": "extended_once",
                                "default_timeout_seconds": (
                                    V7_H4_EXACT_SIDE_FULL_FORMAL_DEFAULT_TIMEOUT_SECONDS
                                ),
                                "effective_timeout_seconds": int(timeout),
                                "outer_entered": True,
                                "peak_process_tree_rss_bytes": peak_process_tree,
                                "peak_below_direct": True,
                                "zero_swap": True,
                                "initial_multimetric_max_true_residual": full_initial_residual,
                                "minimum_multimetric_max_true_residual": full_min_residual,
                                "objective_residual_decreased": True,
                            }
                            continue
                        full_timeout_decision = {
                            "status": "not_extended",
                            "default_timeout_seconds": (
                                V7_H4_EXACT_SIDE_FULL_FORMAL_DEFAULT_TIMEOUT_SECONDS
                            ),
                            "effective_timeout_seconds": int(timeout),
                            "outer_entered": full_outer_entered,
                            "peak_process_tree_rss_bytes": peak_process_tree,
                            "peak_below_direct": (
                                peak_process_tree
                                < V7_H4_EXACT_SIDE_FULL_FORMAL_HARD_STOP_BYTES
                            ),
                            "zero_swap": peak_swap == 0,
                            "initial_multimetric_max_true_residual": full_initial_residual,
                            "minimum_multimetric_max_true_residual": full_min_residual,
                            "objective_residual_decreased": residual_decreased,
                            "reason": "conditional_extension_gate_not_met",
                        }
                    termination = terminate_factory(process)
                    classification = "timeout"
                    break
                sleep(poll_interval)
            if process.poll() is None:
                process.wait()
            exit_status = process.poll()
        _align_formal_markers(formal_last_sample)
        if formal_v7_h4_full and full_timeout_decision is not None:
            if full_timeout_decision.get("status") == "pending":
                status = (
                    "not_needed_process_exit"
                    if classification is None
                    else f"not_reached_due_to_{classification}"
                )
                full_timeout_decision = {
                    "status": status,
                    "default_timeout_seconds": (
                        V7_H4_EXACT_SIDE_FULL_FORMAL_DEFAULT_TIMEOUT_SECONDS
                    ),
                    "effective_timeout_seconds": int(timeout),
                    "classification": classification,
                    "outer_entered": full_outer_entered,
                    "initial_multimetric_max_true_residual": full_initial_residual,
                    "minimum_multimetric_max_true_residual": full_min_residual,
                }
    finally:
        if formal_sample_stream is not None:
            formal_sample_stream.close()
        if formal_stage_stream is not None:
            formal_stage_stream.close()
    if (
        formal_v2_h5
        or formal_v4_h4
        or formal_v4_h4_hybrid
        or formal_v5_h4_setup
        or formal_v5_h4_blr
        or formal_v5_h4_fixed_budget
        or formal_v6_h4_setup
        or formal_v7_h4_setup
        or formal_v7_h4_full
        or formal_v6_h4_port_modal
        or formal_v7_streamed_producer
        or formal_v7_streamed_consumer
        or formal_v8_layer_block
    ) and not formal_object_ledger_path.exists():
        _write_json(
            formal_object_ledger_path,
            {
                "schema": "task039.memory-object-ledger.v1",
                "status": "not_available",
                "classification": "worker_did_not_persist_record",
                "objects": {},
            },
        )

    if classification is None:
        if exit_status == 0 and plan.contract_probe:
            classification = "contract_probe_pass"
        elif exit_status == 0 and plan.task039_trace_audit:
            classification = "task039_trace_capture_complete"
        else:
            classification = "worker_exit0" if exit_status == 0 else "worker_nonzero"
    blr_intervals = None
    if formal_v5_h4_blr:
        blr_intervals = {
            side: _v5_h4_blr_candidate_interval_peak(
                formal_stages_path, formal_samples_path, side
            )
            for side in ("bottom", "top")
        }
        measured = [
            item for item in blr_intervals.values() if item.get("status") == "measured"
        ]
        overall = {
            "status": "measured" if len(measured) == 2 else "not_available",
            "peak_process_tree_rss_gib": (
                max(item["peak_process_tree_rss_gib"] for item in measured)
                if len(measured) == 2
                else None
            ),
            "limit_gib": V5_H4_BLR_SIDE_SETUP_PEAK_LIMIT_GIB,
            "pass": (
                all(item["pass"] for item in measured) if len(measured) == 2 else False
            ),
            "time_basis": "parent_process_tree_sample_elapsed_seconds",
        }
        blr_intervals["overall"] = overall
    fixed_budget_intervals = None
    fixed_budget_overall = None
    if formal_v5_h4_fixed_budget:
        setup_interval = _v5_h4_blr_candidate_interval_peak(
            formal_stages_path,
            formal_samples_path,
            "bottom",
            marker_prefix="v5_fixed_budget_candidate",
        )
        online_interval = _v5_h4_blr_candidate_interval_peak(
            formal_stages_path,
            formal_samples_path,
            "bottom",
            marker_prefix="v5_fixed_budget_candidate",
            begin_suffix="online_begin",
            end_suffix="online_end",
        )
        online_interval["gate_role"] = "evidence_only_not_advancement_gate"
        online_interval["limit_gib"] = None
        online_interval["pass"] = None
        fixed_budget_intervals = {
            "setup": setup_interval,
            "online": online_interval,
        }
        measured = [
            item
            for item in fixed_budget_intervals.values()
            if item.get("status") == "measured"
        ]
        fixed_budget_overall = {
            "status": "measured" if len(measured) == 2 else "not_available",
            "peak_process_tree_rss_gib": (
                max(item["peak_process_tree_rss_gib"] for item in measured)
                if len(measured) == 2
                else None
            ),
            "limit_gib": None,
            "pass": None,
            "gate_role": "evidence_only_not_advancement_gate",
            "time_basis": "parent_process_tree_sample_elapsed_seconds",
        }
    port_modal_resource = None
    if formal_v6_h4_port_modal:
        construction_interval = _v5_h4_blr_candidate_interval_peak(
            formal_stages_path,
            formal_samples_path,
            "bottom",
            begin_stage="v6_port_modal_bottom_construction_begin",
            end_stage="v6_port_modal_bottom_construction_end",
            limit_gib=V6_H4_PORT_MODAL_CONSTRUCTION_LIMIT_GIB,
        )
        retained_interval = _v5_h4_blr_candidate_interval_peak(
            formal_stages_path,
            formal_samples_path,
            "bottom",
            begin_stage="v6_port_modal_bottom_retained_apply_state_ready",
            end_stage="v6_port_modal_bottom_cleanup",
            limit_gib=16.0,
        )
        intervals = {
            "construction": construction_interval,
            "retained": retained_interval,
        }
        measured = [
            item for item in intervals.values() if item.get("status") == "measured"
        ]
        overall = {
            "status": "measured" if len(measured) == 2 else "not_available",
            "peak_process_tree_rss_gib": (
                max(item["peak_process_tree_rss_gib"] for item in measured)
                if len(measured) == 2
                else None
            ),
            "limit_gib": None,
            "pass": (
                all(item["pass"] for item in measured) if len(measured) == 2 else False
            ),
            "gate_role": "construction_and_retained_resource_gate",
            "time_basis": "parent_process_tree_sample_elapsed_seconds",
        }
        port_modal_resource = {
            "construction": construction_interval,
            "retained": retained_interval,
            "overall": overall,
            "gate_basis": "separate_parent_closed_intervals",
            "construction_limit_gib": V6_H4_PORT_MODAL_CONSTRUCTION_LIMIT_GIB,
            "retained_limit_gib": 16.0,
            "effective_hard_stop_bytes": V6_H4_PORT_MODAL_CONSTRUCTION_HARD_STOP_BYTES,
        }
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
        if absolute_terminate_memory_bytes is not None:
            resource_authority.update(
                {
                    "memory_termination_policy": "absolute_bytes",
                    "configured_critical_memory_gib": task039_budget[
                        "configured_critical_memory_gib"
                    ],
                    "critical_checkpoint_crossed": critical_checkpoint_crossed,
                    "critical_checkpoint_first_bytes": critical_checkpoint_first_bytes,
                    "absolute_terminate_memory_bytes": absolute_terminate_memory_bytes,
                    "effective_hard_stop_memory_gib": (
                        absolute_terminate_memory_bytes / 1024**3
                    ),
                    "poll_interval_seconds": poll_interval,
                }
            )
        resource_authority.update(
            {
                "peak_pss_mb": (None if peak_pss is None else peak_pss / 1024**2),
                "peak_uss_mb": (None if peak_uss is None else peak_uss / 1024**2),
                "smaps_attempted_sample_count": smaps_attempted_sample_count,
                "smaps_complete_sample_count": smaps_complete_sample_count,
                "telemetry_status": (
                    "not_measured"
                    if smaps_attempted_sample_count == 0
                    else (
                        "measured" if smaps_complete_sample_count > 0 else "incomplete"
                    )
                ),
                "peak_semantics": (
                    "per-metric simultaneous process-tree peak across complete "
                    "smaps samples; RSS/PSS/USS peaks may occur at different samples"
                ),
            }
        )
    if formal_v2_h5:
        resource_authority["v2_h5_formal_telemetry"] = {
            "raw_marker_path": (
                None if formal_iterative_v2_h5 else str(formal_markers_path)
            ),
            "process_tree_samples_path": str(formal_samples_path),
            "memory_stages_path": str(formal_stages_path),
            "memory_object_ledger_path": str(formal_object_ledger_path),
            "sample_count": sample_count,
            "process_tree_sample_count": formal_written_sample_count,
            "aligned_stage_count": formal_aligned_stage_count,
            "stage_source": (
                "worker_existing_memory_stages"
                if formal_iterative_v2_h5
                else "launcher_marker_alignment"
            ),
        }
    if formal_v4_h4:
        resource_authority["v4_h4_formal_telemetry"] = {
            "raw_marker_path": str(formal_progress_path),
            "progress_path": str(formal_progress_path),
            "process_tree_samples_path": str(formal_samples_path),
            "memory_stages_path": str(formal_stages_path),
            "memory_object_ledger_path": str(formal_object_ledger_path),
            "sample_count": sample_count,
            "process_tree_sample_count": formal_written_sample_count,
            "aligned_stage_count": formal_aligned_stage_count,
            "stage_source": "launcher_marker_alignment",
        }
    if formal_v4_h4_hybrid:
        resource_authority["v4_h4_hybrid_direct_formal_telemetry"] = {
            "raw_marker_path": str(formal_markers_path),
            "process_tree_samples_path": str(formal_samples_path),
            "memory_stages_path": str(formal_stages_path),
            "memory_object_ledger_path": str(formal_object_ledger_path),
            "sample_count": sample_count,
            "process_tree_sample_count": formal_written_sample_count,
            "aligned_stage_count": formal_aligned_stage_count,
            "stage_source": "launcher_marker_alignment",
        }
    if formal_v5_h4_setup:
        resource_authority["v5_h4_setup_only_telemetry"] = {
            "raw_marker_path": str(formal_markers_path),
            "process_tree_samples_path": str(formal_samples_path),
            "memory_stages_path": str(formal_stages_path),
            "memory_object_ledger_path": str(formal_object_ledger_path),
            "sample_count": sample_count,
            "process_tree_sample_count": formal_written_sample_count,
            "aligned_stage_count": formal_aligned_stage_count,
            "stage_source": "launcher_marker_alignment",
        }
    if formal_v5_h4_blr:
        resource_authority["v5_h4_blr_side_component_telemetry"] = {
            "raw_marker_path": str(formal_markers_path),
            "process_tree_samples_path": str(formal_samples_path),
            "memory_stages_path": str(formal_stages_path),
            "memory_object_ledger_path": str(formal_object_ledger_path),
            "sample_count": sample_count,
            "process_tree_sample_count": formal_written_sample_count,
            "aligned_stage_count": formal_aligned_stage_count,
            "stage_source": "launcher_marker_alignment",
        }
        resource_authority["v5_h4_blr_side_component_resource_authority"] = {
            "candidate_setup_intervals": blr_intervals,
            "gate_basis": "closed_begin_end_parent_sample_interval",
        }
    if formal_v5_h4_fixed_budget:
        resource_authority["v5_h4_fixed_budget_bottom_component_telemetry"] = {
            "raw_marker_path": str(formal_markers_path),
            "process_tree_samples_path": str(formal_samples_path),
            "memory_stages_path": str(formal_stages_path),
            "memory_object_ledger_path": str(formal_object_ledger_path),
            "sample_count": sample_count,
            "process_tree_sample_count": formal_written_sample_count,
            "aligned_stage_count": formal_aligned_stage_count,
            "stage_source": "launcher_marker_alignment",
        }
        resource_authority["v5_h4_fixed_budget_bottom_component_resource_authority"] = {
            "candidate_setup_interval": (
                None
                if fixed_budget_intervals is None
                else fixed_budget_intervals["setup"]
            ),
            "online_interval": (
                None
                if fixed_budget_intervals is None
                else fixed_budget_intervals["online"]
            ),
            "overall": fixed_budget_overall,
            "top": "not_run_by_bottom_only_contract",
            "gate_basis": "candidate_setup_interval_only",
            "online_and_overall_role": "evidence_only_not_advancement_gate",
        }
    if formal_v6_h4_setup:
        v6_resource = _v6_post_compaction_resource_authority(
            formal_stages_path,
            formal_samples_path,
            formal_object_ledger_path,
            input_absolute_terminate_memory_bytes=(
                None
                if task039_budget is None
                else task039_budget.get("absolute_terminate_memory_bytes")
            ),
            effective_absolute_terminate_memory_bytes=(
                int(absolute_terminate_memory_bytes)
                if absolute_terminate_memory_bytes is not None
                else V6_H4_POST_COMPACTION_SETUP_HARD_STOP_BYTES
            ),
            setup_limit_gib=V6_H4_POST_COMPACTION_SETUP_PEAK_LIMIT_GIB,
            outer_ready_limit_gib=35.0,
            poll_interval_seconds=poll_interval,
        )
        resource_authority["v6_h4_post_compaction_setup_telemetry"] = {
            "raw_marker_path": str(formal_markers_path),
            "process_tree_samples_path": str(formal_samples_path),
            "memory_stages_path": str(formal_stages_path),
            "memory_object_ledger_path": str(formal_object_ledger_path),
            "sample_count": sample_count,
            "process_tree_sample_count": formal_written_sample_count,
            "aligned_stage_count": formal_aligned_stage_count,
            "stage_source": "launcher_marker_alignment",
            "method_override": {
                "input_absolute_terminate_memory_bytes": (
                    v6_resource["input_absolute_terminate_memory_bytes"]
                ),
                "effective_absolute_terminate_memory_bytes": (
                    v6_resource["effective_absolute_terminate_memory_bytes"]
                ),
                "effective_hard_stop_memory_gib": (
                    v6_resource["effective_hard_stop_memory_gib"]
                ),
                "process_tree_termination_enforced": True,
            },
            "gate_contract": {
                "setup_peak_limit_gib": V6_H4_POST_COMPACTION_SETUP_PEAK_LIMIT_GIB,
                "outer_ready_peak_limit_gib": 35.0,
                "setup_marker_sequence": "V5_H4_SETUP_ONLY_MARKERS",
                "outer_ready_marker": "outer_ksp_setup_ready",
                "gate_role": "v6_setup_only",
            },
            "absolute_terminate_memory_bytes": (
                V6_H4_POST_COMPACTION_SETUP_HARD_STOP_BYTES
            ),
            "require_zero_swap": True,
            "poll_interval_seconds": poll_interval,
            "authority": v6_resource,
        }
    if formal_v7_h4_setup:
        v7_resource = _v6_post_compaction_resource_authority(
            formal_stages_path,
            formal_samples_path,
            formal_object_ledger_path,
            input_absolute_terminate_memory_bytes=(
                None
                if task039_budget is None
                else task039_budget.get("absolute_terminate_memory_bytes")
            ),
            effective_absolute_terminate_memory_bytes=(
                V7_H4_EXACT_SIDE_LIMIT_SETUP_HARD_STOP_BYTES
            ),
            setup_limit_gib=V7_H4_EXACT_SIDE_LIMIT_SETUP_PEAK_LIMIT_GIB,
            outer_ready_limit_gib=V7_H4_EXACT_SIDE_LIMIT_SETUP_PEAK_LIMIT_GIB,
            poll_interval_seconds=poll_interval,
        )
        resource_authority["v7_h4_exact_side_limit_setup_telemetry"] = {
            "raw_marker_path": str(formal_markers_path),
            "process_tree_samples_path": str(formal_samples_path),
            "memory_stages_path": str(formal_stages_path),
            "memory_object_ledger_path": str(formal_object_ledger_path),
            "sample_count": sample_count,
            "process_tree_sample_count": formal_written_sample_count,
            "aligned_stage_count": formal_aligned_stage_count,
            "stage_source": "launcher_marker_alignment",
            "method_override": {
                "input_absolute_terminate_memory_bytes": (
                    v7_resource["input_absolute_terminate_memory_bytes"]
                ),
                "effective_absolute_terminate_memory_bytes": (
                    v7_resource["effective_absolute_terminate_memory_bytes"]
                ),
                "effective_hard_stop_memory_gib": (
                    v7_resource["effective_hard_stop_memory_gib"]
                ),
                "process_tree_termination_enforced": True,
            },
            "gate_contract": {
                "setup_peak_limit_gib": V7_H4_EXACT_SIDE_LIMIT_SETUP_PEAK_LIMIT_GIB,
                "outer_ready_peak_limit_gib": V7_H4_EXACT_SIDE_LIMIT_SETUP_PEAK_LIMIT_GIB,
                "setup_marker_sequence": "V5_H4_SETUP_ONLY_MARKERS",
                "outer_ready_marker": "outer_ksp_setup_ready",
                "gate_role": "v7_lane_a_exact_side_setup_only",
            },
            "absolute_terminate_memory_bytes": (
                V7_H4_EXACT_SIDE_LIMIT_SETUP_HARD_STOP_BYTES
            ),
            "require_zero_swap": True,
            "poll_interval_seconds": poll_interval,
            "authority": v7_resource,
        }
    if formal_v7_h4_full:
        full_resource = _v6_post_compaction_resource_authority(
            formal_stages_path,
            formal_samples_path,
            formal_object_ledger_path,
            input_absolute_terminate_memory_bytes=(
                execution.get("absolute_terminate_memory_bytes")
                if isinstance(execution.get("absolute_terminate_memory_bytes"), int)
                else None
            ),
            effective_absolute_terminate_memory_bytes=(
                V7_H4_EXACT_SIDE_FULL_FORMAL_HARD_STOP_BYTES
            ),
            setup_limit_gib=V7_H4_EXACT_SIDE_FULL_FORMAL_HARD_STOP_BYTES / 1024**3,
            outer_ready_limit_gib=V7_H4_EXACT_SIDE_FULL_FORMAL_HARD_STOP_BYTES
            / 1024**3,
            poll_interval_seconds=poll_interval,
        )
        full_resource["timeout_policy"] = {
            "default_seconds": V7_H4_EXACT_SIDE_FULL_FORMAL_DEFAULT_TIMEOUT_SECONDS,
            "conditional_extension_seconds": (
                V7_H4_EXACT_SIDE_FULL_FORMAL_EXTENSION_TIMEOUT_SECONDS
            ),
            "decision": full_timeout_decision,
            "hard_stop_bytes": V7_H4_EXACT_SIDE_FULL_FORMAL_HARD_STOP_BYTES,
            "peak_process_tree_rss_bytes": peak_process_tree,
            "peak_swap_bytes": peak_swap,
            "zero_swap": bool(sample_count and peak_swap == 0),
        }
        full_resource["no_saving_gate"] = {
            "hard_stop_bytes": V7_H4_EXACT_SIDE_FULL_FORMAL_HARD_STOP_BYTES,
            "peak_process_tree_rss_bytes": peak_process_tree,
            "peak_below_direct": bool(
                peak_process_tree < V7_H4_EXACT_SIDE_FULL_FORMAL_HARD_STOP_BYTES
            ),
            "zero_swap": bool(sample_count and peak_swap == 0),
            "outer_entered": full_outer_entered,
            "status": "measured" if sample_count else "not_available",
        }
        resource_authority["v7_h4_exact_side_full_formal_telemetry"] = {
            "raw_marker_path": str(formal_markers_path),
            "process_tree_samples_path": str(formal_samples_path),
            "memory_stages_path": str(formal_stages_path),
            "memory_object_ledger_path": str(formal_object_ledger_path),
            "sample_count": sample_count,
            "process_tree_sample_count": formal_written_sample_count,
            "aligned_stage_count": formal_aligned_stage_count,
            "stage_source": "launcher_marker_alignment",
            "method_override": {
                "input_absolute_terminate_memory_bytes": full_resource[
                    "input_absolute_terminate_memory_bytes"
                ],
                "effective_absolute_terminate_memory_bytes": (
                    V7_H4_EXACT_SIDE_FULL_FORMAL_HARD_STOP_BYTES
                ),
                "effective_hard_stop_memory_gib": (
                    V7_H4_EXACT_SIDE_FULL_FORMAL_HARD_STOP_BYTES / 1024**3
                ),
                "process_tree_termination_enforced": True,
            },
            "gate_contract": {
                "matched_direct_hard_stop_bytes": (
                    V7_H4_EXACT_SIDE_FULL_FORMAL_HARD_STOP_BYTES
                ),
                "outer_ready_required": True,
                "swap_required": 0,
                "no_saving_gate": "peak_below_direct_before_any_extension",
            },
            "authority": full_resource,
        }
    if formal_v6_h4_port_modal:
        resource_authority["v6_h4_port_modal_bottom_component_telemetry"] = {
            "raw_marker_path": str(formal_markers_path),
            "process_tree_samples_path": str(formal_samples_path),
            "memory_stages_path": str(formal_stages_path),
            "memory_object_ledger_path": str(formal_object_ledger_path),
            "sample_count": sample_count,
            "process_tree_sample_count": formal_written_sample_count,
            "aligned_stage_count": formal_aligned_stage_count,
            "stage_source": "launcher_marker_alignment",
            "method_override": {
                "input_absolute_terminate_memory_bytes": (
                    None
                    if task039_budget is None
                    else task039_budget.get("absolute_terminate_memory_bytes")
                ),
                "effective_absolute_terminate_memory_bytes": (
                    V6_H4_PORT_MODAL_CONSTRUCTION_HARD_STOP_BYTES
                ),
                "effective_hard_stop_memory_gib": (
                    V6_H4_PORT_MODAL_CONSTRUCTION_LIMIT_GIB
                ),
                "process_tree_termination_enforced": True,
            },
            "require_zero_swap": True,
            "poll_interval_seconds": poll_interval,
            "authority": port_modal_resource,
        }
    if formal_v7_streamed_producer:
        resource_authority["v7_h4_streamed_bottom_producer_telemetry"] = {
            "raw_marker_path": str(formal_markers_path),
            "process_tree_samples_path": str(formal_samples_path),
            "memory_stages_path": str(formal_stages_path),
            "memory_object_ledger_path": str(formal_object_ledger_path),
            "sample_count": sample_count,
            "process_tree_sample_count": formal_written_sample_count,
            "aligned_stage_count": formal_aligned_stage_count,
            "stage_source": "launcher_marker_alignment",
            "method_override": {
                "input_absolute_terminate_memory_bytes": (
                    None
                    if task039_budget is None
                    else task039_budget.get("absolute_terminate_memory_bytes")
                ),
                "effective_absolute_terminate_memory_bytes": (
                    V7_STREAMED_PETROV_HARD_STOP_BYTES
                ),
                "effective_hard_stop_memory_gib": (
                    V7_STREAMED_PETROV_HARD_STOP_BYTES / 1024**3
                ),
                "process_tree_termination_enforced": True,
            },
            "gate_contract": {
                "peak_process_tree_rss_bytes_strictly_below": (
                    V7_STREAMED_PETROV_HARD_STOP_BYTES
                ),
                "swap_required": 0,
                "exact_spool_opened": False,
                "holdout_opened": False,
            },
            "absolute_terminate_memory_bytes": V7_STREAMED_PETROV_HARD_STOP_BYTES,
            "require_zero_swap": True,
            "poll_interval_seconds": poll_interval,
            "authority": "parent_process_tree_samples",
        }
    if formal_v7_streamed_consumer:
        consumer_setup_interval = _v5_h4_blr_candidate_interval_peak(
            formal_stages_path,
            formal_samples_path,
            "bottom",
            begin_stage="v7_streamed_bottom_consumer_setup_begin",
            end_stage="v7_streamed_bottom_consumer_setup_end",
            limit_gib=V7_H4_EXACT_SIDE_LIMIT_SETUP_PEAK_LIMIT_GIB,
        )
        resource_authority["v7_h4_streamed_bottom_consumer_telemetry"] = {
            "raw_marker_path": str(formal_markers_path),
            "process_tree_samples_path": str(formal_samples_path),
            "memory_stages_path": str(formal_stages_path),
            "memory_object_ledger_path": str(formal_object_ledger_path),
            "sample_count": sample_count,
            "process_tree_sample_count": formal_written_sample_count,
            "aligned_stage_count": formal_aligned_stage_count,
            "stage_source": "launcher_marker_alignment",
            "method_override": {
                "input_absolute_terminate_memory_bytes": (
                    None
                    if task039_budget is None
                    else task039_budget.get("absolute_terminate_memory_bytes")
                ),
                "effective_absolute_terminate_memory_bytes": (
                    V7_STREAMED_PETROV_CONSUMER_HARD_STOP_BYTES
                ),
                "effective_hard_stop_memory_gib": (
                    V7_STREAMED_PETROV_CONSUMER_HARD_STOP_BYTES / 1024**3
                ),
                "process_tree_termination_enforced": True,
            },
            "gate_contract": {
                "candidate_setup_peak_limit_gib": (
                    V7_H4_EXACT_SIDE_LIMIT_SETUP_PEAK_LIMIT_GIB
                ),
                "swap_required": 0,
                "exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
                "top": "not_run_by_bottom_consumer_contract",
            },
            "absolute_terminate_memory_bytes": (
                V7_STREAMED_PETROV_CONSUMER_HARD_STOP_BYTES
            ),
            "require_zero_swap": True,
            "poll_interval_seconds": poll_interval,
            "candidate_setup_interval": consumer_setup_interval,
            "overall_process_tree_peak_bytes": peak_process_tree,
            "overall_process_tree_peak_gib": peak_process_tree / 1024**3,
            "overall_peak_swap_bytes": peak_swap,
            "authority": "parent_process_tree_samples",
        }
    if formal_v8_layer_block:
        v8_hard_stop = int(
            absolute_terminate_memory_bytes
            or V8_H4_LAYER_BLOCK_RECONSTRUCTION_HARD_STOP_BYTES
        )
        resource_authority["v8_h4_layer_block_reconstruction_telemetry"] = {
            "raw_marker_path": str(formal_markers_path),
            "process_tree_samples_path": str(formal_samples_path),
            "memory_stages_path": str(formal_stages_path),
            "memory_object_ledger_path": str(formal_object_ledger_path),
            "sample_count": sample_count,
            "process_tree_sample_count": formal_written_sample_count,
            "aligned_stage_count": formal_aligned_stage_count,
            "stage_source": "launcher_marker_alignment",
            "method": "task039_v8_h4_layer_block_reconstruction",
            "profile": "task039.v8.h4.layer_block_reconstruction.v1",
            "method_override": {
                "input_absolute_terminate_memory_bytes": (
                    None
                    if task039_budget is None
                    else task039_budget.get("absolute_terminate_memory_bytes")
                ),
                "effective_absolute_terminate_memory_bytes": v8_hard_stop,
                "process_tree_termination_enforced": True,
            },
            "gate_contract": {
                "action_relative_error_limit": 1.0e-12,
                "repeat_relative_error_limit": 1.0e-13,
                "linearity_relative_error_limit": 1.0e-13,
                "require_exact_row_coverage_and_nnz_partition": True,
                "require_long_range_nnz": 0,
                "require_half_bandwidth": 1,
                "exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "qep_count": 0,
                "outer_ksp_count": 0,
                "swap_required": 0,
            },
            "absolute_terminate_memory_bytes": v8_hard_stop,
            "require_zero_swap": True,
            "poll_interval_seconds": poll_interval,
            "authority": "parent_process_tree_samples",
        }
    if formal_v3_2d:
        resource_authority["v3_2d_formal_telemetry"] = {
            "process_tree_samples_path": str(formal_samples_path),
            "sample_count": sample_count,
            "process_tree_sample_count": formal_written_sample_count,
            "stage_aligned_status": "not_applicable_2d_reference",
            "sample_semantics": (
                "launcher-owned process-tree RSS/PSS/USS/swap samples; "
                "the V3 2D reference has no stage marker contract"
            ),
        }
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
    task039_trace_audit: bool = False,
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
    task039_profile = task039_model_id_matches(
        str(specification.method["kind"]),
        str(specification.identity.get("model_id", "")),
        specification.method.get("requested_modes_per_direction"),
    )
    effective_sample_factory = sample_factory
    if task039_profile and sample_factory is resource_authority_sample:
        effective_sample_factory = partial(
            resource_authority_sample,
            include_smaps=True,
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
        task039_trace_audit=task039_trace_audit,
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
                sample_factory=effective_sample_factory,
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
        except Exception as exc:
            result = {
                "exit_status": None,
                "result_classification": "launcher_failure",
                "error": str(exc),
                "error_type": type(exc).__name__,
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
