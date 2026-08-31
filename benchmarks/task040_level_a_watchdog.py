"""Thin Task040 Level-A process-tree watchdog."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmarks.task034_wsl_resources import resource_authority_sample
from benchmarks.task040_level_a import (
    TASK040_LEVEL_A_HARD_STOP_BYTES as _TASK040_LEVEL_A_HARD_STOP_BYTES,
)
from benchmarks.task040_level_a import (
    TASK040_LEVEL_A_MPI_SIZE,
    TASK040_LEVEL_A_THREADS,
    TASK040_LEVEL_A_TIMEOUT_SECONDS,
    TASK040_V1_1_SCALAR_KRYLOV_FLAG,
    TASK040_V1_2_INTERFACE_SCHUR_FLAG,
    TASK040_V2_INTERFACE_PACKET_CONSUMER_FLAG,
    TASK040_V2_INTERFACE_PACKET_PRODUCER_FLAG,
    TASK040_V3_2_COUPLED_INTERFACE_FLAG,
    TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_FLAG,
    TASK040_V5_FRESH_BARE_F_AUTHORITY_FLAG,
    TASK040_V5_ROUTE_C_FLAG,
    TASK040_V6_2_INTERFACE_SCHUR_FLAG,
    V7_MOVING_PML_FULL_STATE_FLAG,
    V7_SCALE_NORMALIZED_IDENTITY_FLAG,
    V8_ADAPTIVE_HARD_STOP_BYTES,
    V8_ADAPTIVE_ONE_APPLY_TARGET_SECONDS,
    V8_ADAPTIVE_PREFERRED_MEMORY_BYTES,
    V8_ADAPTIVE_SCHWARZ_ONLY_FLAG,
    V8_ADAPTIVE_SETUP_TARGET_SECONDS,
    V8_ADAPTIVE_TIMEOUT_SECONDS,
    V8_FULL_SPECTRUM_ONE_APPLY_TARGET_SECONDS,
    V8_FULL_SPECTRUM_ONLY_FLAG,
    V8_FULL_SPECTRUM_SETUP_TARGET_SECONDS,
    V8_FULL_SPECTRUM_TIMEOUT_SECONDS,
    V8_FULL_SPECTRUM_TRANSFORM_TARGET_SECONDS,
    build_task040_level_a_plan,
)
from benchmarks.watchdog_process_control import (
    terminate_process_tree,
    worker_process_group_popen_kwargs,
)

ROOT = Path(__file__).resolve().parents[1]
TASK040_LEVEL_A_HARD_STOP_BYTES = _TASK040_LEVEL_A_HARD_STOP_BYTES
SAMPLE_INTERVAL_SECONDS = 0.5
HEARTBEAT_SECONDS = 60.0
SWAP_LIMIT_BYTES = 0
V8_RESOURCE_UNAVAILABLE_CLASSIFICATION = (
    "FULL_SPECTRUM_CURRENT_IMPLEMENTATION_RESOURCE_UNAVAILABLE"
)
V8_ADAPTIVE_RESOURCE_UNAVAILABLE_CLASSIFICATION = (
    "ADAPTIVE_IMPEDANCE_STAGE_A_RESOURCE_UNAVAILABLE"
)
_TERMINAL_CLEANUP_STAGES = frozenset(
    {
        "cleanup",
        "v4_identity_stop",
        "v5_route_c_cleanup",
        "v6_2_cleanup",
        "v7_moving_pml_cleanup",
        "v8_full_spectrum_cleanup_complete",
        "v8_adaptive_cleanup_complete",
    }
)
THREAD_ENV = {
    "OMP_NUM_THREADS": str(TASK040_LEVEL_A_THREADS),
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "BLIS_NUM_THREADS": "1",
    "PYTHONUNBUFFERED": "1",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _worker_command(plan: dict[str, Any]) -> list[str]:
    run_directory = Path(plan["run_directory"])
    worker_directory = Path(plan["worker_run_directory"])
    command = [
        "mpiexec",
        "-n",
        str(TASK040_LEVEL_A_MPI_SIZE),
        sys.executable,
        "-m",
        "benchmarks.task040_level_a",
        "--input",
        plan["input"],
        "--exact-spool-root",
        plan["exact_spool_root"],
        "--run-directory",
        str(worker_directory),
        "--source-sha",
        plan["source_sha"],
        "--memory-stages",
        str(run_directory / "memory_stages.jsonl"),
        "--memory-markers",
        str(run_directory / "memory_stage_markers.raw.jsonl"),
    ]
    if plan.get("scalar_krylov") is True:
        command.append(TASK040_V1_1_SCALAR_KRYLOV_FLAG)
    if plan.get("interface_schur") is True:
        command.append(TASK040_V1_2_INTERFACE_SCHUR_FLAG)
    if plan.get("packet_producer") is True:
        command.append(TASK040_V2_INTERFACE_PACKET_PRODUCER_FLAG)
    if plan.get("v4_exact_authority_compatibility") is True:
        command.append(TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_FLAG)
    if plan.get("v5_fresh_bare_f_authority") is True:
        command.append(TASK040_V5_FRESH_BARE_F_AUTHORITY_FLAG)
        command.extend(("--watchdog-enabled", "--bottom-route-only"))
    if plan.get("v5_route_c") is True:
        command.append(TASK040_V5_ROUTE_C_FLAG)
        command.extend(("--watchdog-enabled", "--bottom-route-only"))
    if plan.get("v8_adaptive_schwarz_only") is True:
        command.append(V8_ADAPTIVE_SCHWARZ_ONLY_FLAG)
    elif plan.get("v8_full_spectrum_only") is True:
        command.append(V8_FULL_SPECTRUM_ONLY_FLAG)
    elif plan.get("v7_moving_pml_full_state") is True:
        command.append(V7_MOVING_PML_FULL_STATE_FLAG)
    elif plan.get("v7_scale_normalized_identity") is True:
        command.append(V7_SCALE_NORMALIZED_IDENTITY_FLAG)
    elif plan.get("v6_2_interface_schur") is True:
        command.append(TASK040_V6_2_INTERFACE_SCHUR_FLAG)
    if plan.get("v8_adaptive_schwarz_only") is True or plan.get(
        "v8_full_spectrum_only"
    ) is True or plan.get(
        "v7_moving_pml_full_state"
    ) is True or plan.get(
        "v7_scale_normalized_identity"
    ) is True or plan.get(
        "v6_2_interface_schur"
    ) is True:
        command.extend(
            (
                "--watchdog-hard-stop-bytes",
                str(plan["watchdog"]["hard_stop_bytes"]),
                "--watchdog-enabled",
                "--bottom-route-only",
            )
        )
    if plan.get("coupled_interface") is True:
        command.extend(
            [
                TASK040_V3_2_COUPLED_INTERFACE_FLAG,
                "--interface-packet-root",
                str(plan["interface_packet_root"]),
            ]
        )
    elif plan.get("packet_consumer") is True:
        command.extend(
            [
                TASK040_V2_INTERFACE_PACKET_CONSUMER_FLAG,
                "--interface-packet-root",
                str(plan["interface_packet_root"]),
            ]
        )
    return command


def build_task040_level_a_watchdog_plan(
    *,
    input_path: str | Path,
    exact_spool_root: str | Path,
    run_directory: str | Path,
    source_sha: str,
    scalar_krylov: bool = False,
    interface_schur: bool = False,
    packet_producer: bool = False,
    packet_consumer: bool = False,
    coupled_interface: bool = False,
    v4_exact_authority_compatibility: bool = False,
    v5_fresh_bare_f_authority: bool = False,
    v5_route_c: bool = False,
    v6_2_interface_schur: bool = False,
    v7_scale_normalized_identity: bool = False,
    v7_moving_pml_full_state: bool = False,
    v8_full_spectrum_only: bool = False,
    v8_adaptive_schwarz_only: bool = False,
    interface_packet_root: str | Path | None = None,
) -> dict[str, Any]:
    plan = build_task040_level_a_plan(
        input_path=input_path,
        exact_spool_root=exact_spool_root,
        run_directory=run_directory,
        source_sha=source_sha,
        scalar_krylov=scalar_krylov,
        interface_schur=interface_schur,
        packet_producer=packet_producer,
        packet_consumer=packet_consumer,
        coupled_interface=coupled_interface,
        v4_exact_authority_compatibility=v4_exact_authority_compatibility,
        v5_fresh_bare_f_authority=v5_fresh_bare_f_authority,
        v5_route_c=v5_route_c,
        v6_2_interface_schur=v6_2_interface_schur,
        v7_scale_normalized_identity=v7_scale_normalized_identity,
        v7_moving_pml_full_state=v7_moving_pml_full_state,
        v8_full_spectrum_only=v8_full_spectrum_only,
        v8_adaptive_schwarz_only=v8_adaptive_schwarz_only,
        interface_packet_root=interface_packet_root,
    )
    worker_directory = Path(plan["run_directory"]) / "worker"
    if packet_producer:
        plan["packet_root"] = str(worker_directory / "interface_packet")
    plan["watchdog"] = {
        "sample_interval_seconds": SAMPLE_INTERVAL_SECONDS,
        "heartbeat_seconds": HEARTBEAT_SECONDS,
        "absolute_terminate_memory_bytes": plan["absolute_terminate_memory_bytes"],
        "swap_limit_bytes": SWAP_LIMIT_BYTES,
        "process_group": True,
        "terminate_entire_process_group": True,
        "resource_authority": "task034_wsl_resources.resource_authority_sample",
    }
    if v5_fresh_bare_f_authority:
        plan["watchdog"].update(
            {
                "preferred_memory_bytes": int(plan["preferred_memory_bytes"]),
                "warning_memory_bytes": int(plan["warning_memory_bytes"]),
                "hard_stop_bytes": int(plan["absolute_terminate_memory_bytes"]),
                "process_tree_watchdog_enabled": True,
                "bottom_route_only": True,
            }
        )
    elif packet_producer:
        plan["watchdog"]["preferred_memory_bytes"] = int(plan["preferred_memory_bytes"])
    elif v5_route_c:
        plan["watchdog"].update(
            {
                "hard_stop_bytes": int(plan["absolute_terminate_memory_bytes"]),
                "timeout_seconds": int(plan["timeout_seconds"]),
                "route_c_resource_policy": "45_gib_hard_line_swap0",
                "bottom_route_only": True,
                "process_tree_watchdog_enabled": True,
            }
        )
    elif (
        v8_adaptive_schwarz_only
        or v8_full_spectrum_only
        or v7_moving_pml_full_state
        or v7_scale_normalized_identity
        or v6_2_interface_schur
    ):
        plan["watchdog"].update(
            {
                "hard_stop_bytes": int(plan["absolute_terminate_memory_bytes"]),
                "swap_limit_bytes": 0,
                "timeout_seconds": int(plan["timeout_seconds"]),
                "process_tree_watchdog_enabled": True,
                "bottom_route_only": True,
                "numeric_allgather": False,
                "full_interface_replica_per_rank": False,
            }
        )
        if v8_adaptive_schwarz_only:
            plan["watchdog"].update(
                {
                    "v8_adaptive_schwarz_only": True,
                    "preferred_memory_bytes": V8_ADAPTIVE_PREFERRED_MEMORY_BYTES,
                    "hard_stop_bytes": V8_ADAPTIVE_HARD_STOP_BYTES,
                    "timeout_seconds": V8_ADAPTIVE_TIMEOUT_SECONDS,
                    "setup_target_seconds": V8_ADAPTIVE_SETUP_TARGET_SECONDS,
                    "one_apply_target_seconds": (
                        V8_ADAPTIVE_ONE_APPLY_TARGET_SECONDS
                    ),
                    "source_order": list(plan["source_order"]),
                    "mandatory_checkpoints": list(plan["mandatory_checkpoints"]),
                    "conditional_checkpoints": [],
                    "cleanup_stage": "v8_adaptive_cleanup_complete",
                    "numeric_allgather": False,
                    "full_interface_replica_per_rank": False,
                }
            )
        elif v8_full_spectrum_only:
            plan["watchdog"].update(
                {
                    "v8_full_spectrum_only": True,
                    "minimum_mem_available_bytes": int(
                        plan["minimum_mem_available_bytes"]
                    ),
                    "preferred_memory_bytes": int(plan["preferred_memory_bytes"]),
                    "setup_target_seconds": V8_FULL_SPECTRUM_SETUP_TARGET_SECONDS,
                    "transform_target_seconds": V8_FULL_SPECTRUM_TRANSFORM_TARGET_SECONDS,
                    "one_apply_target_seconds": V8_FULL_SPECTRUM_ONE_APPLY_TARGET_SECONDS,
                    "timeout_seconds": V8_FULL_SPECTRUM_TIMEOUT_SECONDS,
                    "source_order": list(plan["source_order"]),
                    "mandatory_checkpoints": list(plan["mandatory_checkpoints"]),
                    "conditional_checkpoints": list(plan["conditional_checkpoints"]),
                    "metadata_only_descriptor_gather": True,
                    "root_metadata_gather": True,
                    "numeric_allgather": False,
                    "full_interface_replica_per_rank": False,
                }
            )
        elif v7_moving_pml_full_state:
            plan["watchdog"].update(
                {
                    "v7_moving_pml_full_state": True,
                    "source_order": list(plan["source_order"]),
                    "mandatory_checkpoints": list(plan["mandatory_checkpoints"]),
                    "fixed_configuration": dict(plan["fixed_configuration"]),
                    "pml_profile": "quadratic",
                    "integrated_attenuation": 6.0,
                    "numeric_allgather": False,
                    "full_interface_replica_per_rank": False,
                }
            )
        elif v7_scale_normalized_identity:
            plan["watchdog"].update(
                {
                    "v7_identity_preferred_memory_bytes": int(
                        plan["preferred_memory_bytes"]
                    ),
                    "v7_identity_target_seconds": int(
                        plan["identity_target_seconds"]
                    ),
                    "v7_identity_hard_seconds": int(
                        plan["identity_hard_seconds"]
                    ),
                    "v7_scale_normalized_identity": True,
                    "root_metadata_gather": bool(plan["root_metadata_gather"]),
                    "metadata_only_descriptor_gather": bool(
                        plan["metadata_only_descriptor_gather"]
                    ),
                }
            )
        else:
            plan["watchdog"].update(
                {
                    "minimum_mem_available_bytes": int(
                        plan["minimum_mem_available_bytes"]
                    ),
                    "minimum_disk_free_bytes": int(
                        plan["minimum_disk_free_bytes"]
                    ),
                    "v6_2_identity_only": False,
                    "v6_2_exact_qualification": True,
                    "same_process_exact_lifecycle": True,
                    "root_metadata_gather": True,
                    "support_metadata_replicated": True,
                }
            )
    plan["worker_run_directory"] = str(worker_directory)
    plan["worker_argv"] = _worker_command(plan)
    plan["runner_reuse"] = {
        "task040_worker": "benchmarks/task040_level_a.py",
        "process_control": "benchmarks.watchdog_process_control",
        "system_and_source": "Task039 h4 bottom APIs",
    }
    return plan


def _latest_stage(path: Path) -> tuple[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "process_start", "waiting_for_progress"
    for line in reversed(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        return str(payload.get("stage", "unknown")), str(
            payload.get("status", "unknown")
        )
    return "process_start", "waiting_for_progress"


def _v8_active_stage_timeout(
    stage: str,
    stage_elapsed_seconds: float,
    total_elapsed_seconds: float,
) -> dict[str, Any]:
    """Apply only the V8 active-stage limits and the total wall limit."""

    if float(total_elapsed_seconds) >= V8_FULL_SPECTRUM_TIMEOUT_SECONDS:
        return {
            "active": True,
            "timed_out": True,
            "kind": "total",
            "limit_seconds": float(V8_FULL_SPECTRUM_TIMEOUT_SECONDS),
            "classification": V8_RESOURCE_UNAVAILABLE_CLASSIFICATION,
        }
    if stage.endswith("_one_apply_begin"):
        limit = float(V8_FULL_SPECTRUM_ONE_APPLY_TARGET_SECONDS)
        kind = "one_apply"
    elif stage == "v8_full_spectrum_group2_factor_ready":
        limit = 2.0 * V8_FULL_SPECTRUM_TRANSFORM_TARGET_SECONDS
        kind = "transform_or_symbol"
    elif (
        stage == "process_start"
        or stage == "v8_full_spectrum_preflight"
        or stage == "v8_full_spectrum_system_ready"
        or "_factor_ready" in stage
    ):
        limit = 2.0 * V8_FULL_SPECTRUM_SETUP_TARGET_SECONDS
        kind = "setup_or_factor"
    elif "transform_ready" in stage or stage.endswith("_symbol_ready"):
        limit = 2.0 * V8_FULL_SPECTRUM_TRANSFORM_TARGET_SECONDS
        kind = "transform_or_symbol"
    else:
        return {
            "active": False,
            "timed_out": False,
            "kind": None,
            "limit_seconds": None,
            "classification": None,
        }
    elapsed = float(stage_elapsed_seconds)
    return {
        "active": True,
        "timed_out": elapsed > limit,
        "kind": kind,
        "limit_seconds": limit,
        "classification": (
            V8_RESOURCE_UNAVAILABLE_CLASSIFICATION if elapsed > limit else None
        ),
    }


def _v8_adaptive_active_stage_timeout(
    stage: str,
    stage_elapsed_seconds: float,
    total_elapsed_seconds: float,
) -> dict[str, Any]:
    """Return the fixed Stage-A marker timeout without changing old V8."""

    if float(total_elapsed_seconds) >= V8_ADAPTIVE_TIMEOUT_SECONDS:
        limit = float(V8_ADAPTIVE_TIMEOUT_SECONDS)
        kind = "total"
    elif stage.endswith("_one_apply_begin"):
        limit = float(V8_ADAPTIVE_ONE_APPLY_TARGET_SECONDS)
        kind = "one_apply"
    elif stage in {
        "process_start",
        "v8_adaptive_preflight",
        "v8_adaptive_system_ready",
        "v8_adaptive_factor_ready",
    }:
        limit = float(V8_ADAPTIVE_SETUP_TARGET_SECONDS)
        kind = "setup_or_factor"
    else:
        return {
            "active": False,
            "timed_out": False,
            "kind": None,
            "limit_seconds": None,
            "classification": None,
        }
    elapsed = float(
        total_elapsed_seconds if kind == "total" else stage_elapsed_seconds
    )
    return {
        "active": True,
        "timed_out": elapsed > limit,
        "kind": kind,
        "limit_seconds": limit,
        "classification": (
            V8_ADAPTIVE_RESOURCE_UNAVAILABLE_CLASSIFICATION
            if elapsed > limit
            else None
        ),
    }


def _v8_adaptive_swap_authority_sample(
    authority: dict[str, Any], *, terminal_excluded: bool
) -> dict[str, Any]:
    """Evaluate one adaptive swap sample, including the scoped zero fallback."""

    if terminal_excluded:
        return {
            "counted": False,
            "authority_readable": True,
            "swap_zero": True,
            "fallback_used": False,
            "semantics": "terminal_teardown_excluded",
        }
    process_tree = authority.get("process_tree", {})
    cgroup = authority.get("job_cgroup", {})
    process_complete = bool(process_tree.get("all_status_readable"))
    process_swap = process_tree.get("swap_bytes")
    dedicated = bool(cgroup.get("dedicated_job_cgroup"))
    cgroup_readable = bool(cgroup.get("readable"))
    cgroup_swap = cgroup.get("swap_current_bytes")
    if process_complete:
        cgroup_ok = (
            not dedicated
            or (cgroup_readable and cgroup_swap == SWAP_LIMIT_BYTES)
        )
        readable = process_swap == SWAP_LIMIT_BYTES and cgroup_ok
        return {
            "counted": True,
            "authority_readable": readable,
            "swap_zero": readable,
            "fallback_used": False,
            "semantics": (
                "complete_process_tree_vm_swap"
                if readable
                else "complete_process_tree_or_dedicated_cgroup_invalid"
            ),
        }
    fallback = (
        not dedicated
        and cgroup_readable
        and cgroup_swap == SWAP_LIMIT_BYTES
    )
    return {
        "counted": True,
        "authority_readable": fallback,
        "swap_zero": fallback,
        "fallback_used": fallback,
        "semantics": (
            "nonterminal_incomplete_process_tree_non_dedicated_cgroup_zero_upper_bound"
            if fallback
            else "incomplete_process_tree_swap_authority_unavailable"
        ),
    }


def _terminal_teardown_sample_excluded(
    *,
    post_sample_return_code: int | None,
    process_tree: dict[str, Any],
    run_summary_path: Path,
    latest_stage: str,
    latest_stage_status: str,
) -> bool:
    """Recognize only the post-cleanup ``/proc`` teardown race.

    A worker that is still live, or whose run summary/terminal cleanup stage is
    not complete, remains an authoritative telemetry failure when its process
    tree is unreadable.  The caller performs RSS and swap limits independently
    before accepting this exclusion.
    """
    return bool(
        post_sample_return_code is None
        and run_summary_path.is_file()
        and latest_stage in _TERMINAL_CLEANUP_STAGES
        and latest_stage_status == "complete"
        and process_tree.get("pids")
        and process_tree.get("all_status_readable") is False
    )


def _terminal_teardown_termination_reason(
    *,
    rss_bytes: int,
    swap_bytes: int,
    dedicated_swap_bytes: int | None,
    hard_stop_bytes: int,
) -> str:
    """Apply resource limits before accepting a natural teardown exit."""
    if rss_bytes >= hard_stop_bytes:
        return "absolute_memory_limit"
    if swap_bytes > SWAP_LIMIT_BYTES or (
        dedicated_swap_bytes is not None
        and dedicated_swap_bytes > SWAP_LIMIT_BYTES
    ):
        return "swap_detected"
    return "natural_exit"


def _write_jsonl(stream: Any, payload: dict[str, Any]) -> None:
    stream.write(json.dumps(payload, sort_keys=True) + "\n")
    stream.flush()


def _worker_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(THREAD_ENV)
    return environment


def run_task040_level_a_watchdog(plan: dict[str, Any]) -> int:
    run_directory = Path(plan["run_directory"])
    if run_directory.exists():
        raise FileExistsError(f"Task040 run directory already exists: {run_directory}")
    run_directory.mkdir(parents=True, exist_ok=False)
    stages_path = run_directory / "memory_stages.jsonl"
    markers_path = run_directory / "memory_stage_markers.raw.jsonl"
    timeline_path = run_directory / "process_tree_samples.jsonl"
    stdout_path = run_directory / "worker_stdout.txt"
    summary_path = run_directory / "watchdog_summary.json"
    worker_directory = Path(plan["worker_run_directory"])
    run_summary = worker_directory / "run_summary.json"
    if worker_directory.exists():
        raise FileExistsError(
            f"Task040 worker output directory already exists: {worker_directory}"
        )
    command = list(plan["worker_argv"])
    hard_stop_bytes = int(plan["absolute_terminate_memory_bytes"])
    timeout_seconds = int(plan.get("timeout_seconds", TASK040_LEVEL_A_TIMEOUT_SECONDS))
    adaptive_enabled = bool(plan.get("v8_adaptive_schwarz_only"))
    v8_enabled = bool(plan.get("v8_full_spectrum_only")) or adaptive_enabled
    last_stage = "process_start"
    last_stage_status = "waiting_for_progress"
    stage_started = time.monotonic()
    started = time.monotonic()
    sample_count = 0
    terminal_teardown_excluded_count = 0
    peak_rss_bytes = 0
    peak_swap_bytes = 0
    all_status_readable = True
    dedicated_cgroup_present = False
    dedicated_cgroup_swap_readable = True
    peak_dedicated_cgroup_swap_bytes = 0
    adaptive_swap_authority_readable = True
    adaptive_swap_sample_count = 0
    adaptive_swap_fallback_count = 0
    previous_heartbeat = -HEARTBEAT_SECONDS
    termination_reason = "natural_exit"
    process_control: dict[str, Any] = {}
    v5_thresholds_enabled = bool(plan.get("v5_fresh_bare_f_authority"))
    route_c_enabled = bool(plan.get("v5_route_c"))
    threshold_observation_count = 0
    resource_thresholds: dict[str, Any] = {}
    v8_timeout_decision: dict[str, Any] | None = None
    v8_completed = False
    if v5_thresholds_enabled:
        resource_thresholds = {
            "preferred": {
                "bytes": int(plan["preferred_memory_bytes"]),
                "crossed": False,
                "first_sample": None,
                "first_elapsed_seconds": None,
            },
            "warning": {
                "bytes": int(plan["warning_memory_bytes"]),
                "crossed": False,
                "first_sample": None,
                "first_elapsed_seconds": None,
            },
            "hard_stop": {
                "bytes": int(plan["absolute_terminate_memory_bytes"]),
                "crossed": False,
                "first_sample": None,
                "first_elapsed_seconds": None,
            },
        }

    def observe_v5_thresholds(rss_bytes: int, elapsed: float) -> None:
        nonlocal threshold_observation_count
        if not v5_thresholds_enabled:
            return
        threshold_observation_count += 1
        for threshold in resource_thresholds.values():
            if not threshold["crossed"] and int(rss_bytes) >= int(threshold["bytes"]):
                threshold["crossed"] = True
                threshold["first_sample"] = threshold_observation_count
                threshold["first_elapsed_seconds"] = float(elapsed)

    with (
        stdout_path.open("w", encoding="utf-8") as stdout,
        timeline_path.open("w", encoding="utf-8") as timeline,
    ):
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=_worker_environment(),
            stdout=stdout,
            stderr=subprocess.STDOUT,
            text=True,
            **worker_process_group_popen_kwargs(),
        )
        while True:
            elapsed = time.monotonic() - started
            return_code = process.poll()
            if return_code is not None:
                termination_reason = "natural_exit"
                process_control = terminate_process_tree(process)
                break
            authority = resource_authority_sample(process.pid, include_smaps=False)
            process_tree = authority["process_tree"]
            rss_bytes = int(process_tree["rss_bytes"])
            swap_bytes = int(process_tree["swap_bytes"])
            observe_v5_thresholds(rss_bytes, elapsed)
            job_cgroup = authority["job_cgroup"]
            has_cgroup = bool(job_cgroup["dedicated_job_cgroup"])
            live_sample = bool(process_tree.get("pids"))
            post_sample_return_code = process.poll()
            process_exited_during_sample = post_sample_return_code is not None
            peak_rss_bytes = max(peak_rss_bytes, rss_bytes)
            peak_swap_bytes = max(peak_swap_bytes, swap_bytes)
            dedicated_cgroup_present = dedicated_cgroup_present or has_cgroup
            dedicated_swap = None
            if has_cgroup:
                dedicated_swap = job_cgroup["swap_current_bytes"]
                if dedicated_swap is not None:
                    peak_dedicated_cgroup_swap_bytes = max(
                        peak_dedicated_cgroup_swap_bytes, int(dedicated_swap)
                    )
            stage, status = _latest_stage(stages_path)
            last_stage_status = status
            if stage != last_stage:
                last_stage = stage
                stage_started = time.monotonic()
            completed_cleanup_teardown = _terminal_teardown_sample_excluded(
                post_sample_return_code=post_sample_return_code,
                process_tree=process_tree,
                run_summary_path=run_summary,
                latest_stage=stage,
                latest_stage_status=status,
            )
            terminal_teardown_excluded = (
                process_exited_during_sample or completed_cleanup_teardown
            )
            if adaptive_enabled:
                swap_sample = _v8_adaptive_swap_authority_sample(
                    authority, terminal_excluded=terminal_teardown_excluded
                )
                if swap_sample["counted"]:
                    adaptive_swap_sample_count += 1
                    adaptive_swap_authority_readable = (
                        adaptive_swap_authority_readable
                        and bool(swap_sample["authority_readable"])
                    )
                    if swap_sample["fallback_used"]:
                        adaptive_swap_fallback_count += 1
            authoritative_sample = live_sample and not terminal_teardown_excluded
            if authoritative_sample:
                sample_count += 1
                all_status_readable = all_status_readable and bool(
                    process_tree["all_status_readable"]
                )
                if has_cgroup:
                    dedicated_cgroup_swap_readable = (
                        dedicated_cgroup_swap_readable and dedicated_swap is not None
                    )
            elif terminal_teardown_excluded:
                terminal_teardown_excluded_count += 1
            row = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": elapsed,
                "stage": stage,
                "stage_status": status,
                "rss_bytes": rss_bytes,
                "swap_bytes": swap_bytes,
                "resource_authority": authority,
                "authoritative_sample": authoritative_sample,
                "terminal_teardown_excluded": terminal_teardown_excluded,
                "sample_process_alive_before": True,
                "sample_process_alive_after": not terminal_teardown_excluded,
                "post_sample_return_code": post_sample_return_code,
            }
            _write_jsonl(timeline, row)
            if elapsed - previous_heartbeat >= HEARTBEAT_SECONDS:
                print(
                    "Task040 watchdog heartbeat "
                    f"elapsed={elapsed:.1f}s stage={stage} "
                    f"rss_gib={rss_bytes / 2**30:.3f} swap_bytes={swap_bytes}",
                    flush=True,
                )
                previous_heartbeat = elapsed
            if terminal_teardown_excluded:
                termination_reason = _terminal_teardown_termination_reason(
                    rss_bytes=rss_bytes,
                    swap_bytes=swap_bytes,
                    dedicated_swap_bytes=dedicated_swap,
                    hard_stop_bytes=hard_stop_bytes,
                )
                if process_exited_during_sample or termination_reason != "natural_exit":
                    process_control = terminate_process_tree(process)
                    break
                if elapsed >= timeout_seconds:
                    termination_reason = "wall_timeout"
                    process_control = terminate_process_tree(process)
                    break
                time.sleep(SAMPLE_INTERVAL_SECONDS)
                continue
            if not authoritative_sample:
                if elapsed >= timeout_seconds:
                    termination_reason = "wall_timeout"
                    process_control = terminate_process_tree(process)
                    break
                time.sleep(SAMPLE_INTERVAL_SECONDS)
                continue
            if rss_bytes >= hard_stop_bytes:
                termination_reason = "absolute_memory_limit"
            elif (
                swap_bytes > SWAP_LIMIT_BYTES
                or peak_dedicated_cgroup_swap_bytes > SWAP_LIMIT_BYTES
            ):
                termination_reason = "swap_detected"
            elif return_code is not None:
                termination_reason = "natural_exit"
            elif elapsed >= timeout_seconds:
                if v8_enabled:
                    v8_timeout_decision = (
                        _v8_adaptive_active_stage_timeout
                        if adaptive_enabled
                        else _v8_active_stage_timeout
                    )(
                        stage,
                        time.monotonic() - stage_started,
                        elapsed,
                    )
                termination_reason = "wall_timeout"
            elif v8_enabled:
                v8_timeout_decision = (
                    _v8_adaptive_active_stage_timeout
                    if adaptive_enabled
                    else _v8_active_stage_timeout
                )(
                    stage,
                    time.monotonic() - stage_started,
                    elapsed,
                )
                if v8_timeout_decision["timed_out"]:
                    termination_reason = (
                        "wall_timeout"
                        if v8_timeout_decision["kind"] == "total"
                        else "v8_marker_target_exceeded"
                    )
                else:
                    time.sleep(SAMPLE_INTERVAL_SECONDS)
                    continue
            else:
                time.sleep(SAMPLE_INTERVAL_SECONDS)
                continue
            process_control = terminate_process_tree(process)
            break

    elapsed_seconds = time.monotonic() - started
    swap_authority_readable = all_status_readable and (
        not dedicated_cgroup_present or dedicated_cgroup_swap_readable
    )
    summary = {
        "schema": "task040.level_a.watchdog.v1",
        "method": plan["method"],
        "source_sha": plan["source_sha"],
        "command": command,
        "termination_reason": termination_reason,
        "return_code": process.returncode,
        "process_control": process_control,
        "elapsed_seconds": elapsed_seconds,
        "sample_count": sample_count,
        "authoritative_sample_count": sample_count,
        "terminal_teardown_excluded_count": terminal_teardown_excluded_count,
        "peak_rss_bytes": peak_rss_bytes,
        "peak_swap_bytes": peak_swap_bytes,
        "peak_dedicated_cgroup_swap_bytes": peak_dedicated_cgroup_swap_bytes,
        "hard_stop_bytes": hard_stop_bytes,
        "timeout_seconds": timeout_seconds,
        "all_status_readable": all_status_readable,
        "dedicated_cgroup_present": dedicated_cgroup_present,
        "dedicated_cgroup_swap_readable": (
            dedicated_cgroup_swap_readable if dedicated_cgroup_present else None
        ),
        "swap_authority_readable": swap_authority_readable,
        "run_summary_present": run_summary.is_file(),
        "run_summary_sha256": _sha256(run_summary) if run_summary.is_file() else None,
        "artifact_hashes": {
            path.name: _sha256(path)
            for path in (stages_path, markers_path, timeline_path, stdout_path)
            if path.is_file()
        },
    }
    if adaptive_enabled:
        cleanup_complete = False
        local_gate_pass: bool | None = None
        if run_summary.is_file():
            try:
                cleanup_payload = json.loads(run_summary.read_text(encoding="utf-8"))
                cleanup_complete = bool(
                    cleanup_payload.get("cleanup", {}).get("status") == "complete"
                )
                if "local_gate_pass" in cleanup_payload:
                    local_gate_pass = bool(cleanup_payload["local_gate_pass"])
            except (OSError, json.JSONDecodeError):
                cleanup_complete = False
        adaptive_workflow_completed = bool(
            termination_reason == "natural_exit"
            and process.returncode == 0
            and run_summary.is_file()
            and cleanup_complete
            and last_stage == "v8_adaptive_cleanup_complete"
            and last_stage_status == "complete"
        )
        resource_stop = termination_reason in {
            "absolute_memory_limit",
            "swap_detected",
            "wall_timeout",
            "v8_marker_target_exceeded",
        }
        preferred_peak_pass = peak_rss_bytes <= V8_ADAPTIVE_PREFERRED_MEMORY_BYTES
        swap_gate = bool(
            adaptive_swap_authority_readable
            and peak_swap_bytes == SWAP_LIMIT_BYTES
            and peak_dedicated_cgroup_swap_bytes == SWAP_LIMIT_BYTES
        )
        resource_gate = bool(preferred_peak_pass and swap_gate)
        if resource_stop:
            adaptive_classification = V8_ADAPTIVE_RESOURCE_UNAVAILABLE_CLASSIFICATION
        elif adaptive_workflow_completed and not resource_gate:
            adaptive_classification = "ADAPTIVE_STAGE_A_RESOURCE_NEGATIVE"
        elif adaptive_workflow_completed and local_gate_pass is False:
            adaptive_classification = "ADAPTIVE_STAGE_A_NUMERICAL_LOCAL_GATE_NEGATIVE"
        elif (
            adaptive_workflow_completed
            and local_gate_pass is True
            and resource_gate
        ):
            adaptive_classification = "ADAPTIVE_STAGE_A_VIABILITY_PASS"
        else:
            adaptive_classification = "requires_result_adjudication"
        summary.update(
            {
                "v8_adaptive_workflow_completed": adaptive_workflow_completed,
                "v8_adaptive_viability_pass": bool(
                    adaptive_workflow_completed
                    and local_gate_pass is True
                    and resource_gate
                ),
                "v8_adaptive_local_gate": (
                    local_gate_pass
                    if local_gate_pass is not None
                    else "pending_runner_result"
                ),
                "v8_adaptive_resource_gate": resource_gate,
                "preferred_peak_pass": preferred_peak_pass,
                "swap_gate": swap_gate,
                "adaptive_swap_authority_readable": (
                    adaptive_swap_authority_readable
                ),
                "adaptive_swap_sample_count": adaptive_swap_sample_count,
                "adaptive_swap_fallback_count": adaptive_swap_fallback_count,
                "adaptive_swap_authority_semantics": (
                    "complete process-tree VmSwap; nonterminal incomplete tree "
                    "may use readable non-dedicated cgroup memory.swap.current==0 "
                    "as a superset zero upper bound; terminal teardown excluded"
                ),
                "latest_stage": last_stage,
                "latest_stage_status": last_stage_status,
                "resource_classification": adaptive_classification,
                "final_resource_classification": adaptive_classification,
                "v8_adaptive_stage_timeout": v8_timeout_decision,
                "v8_adaptive_resource_limits": {
                    "setup_no_marker_seconds": V8_ADAPTIVE_SETUP_TARGET_SECONDS,
                    "one_apply_hard_seconds": V8_ADAPTIVE_ONE_APPLY_TARGET_SECONDS,
                    "total_wall_seconds": V8_ADAPTIVE_TIMEOUT_SECONDS,
                    "preferred_memory_bytes": V8_ADAPTIVE_PREFERRED_MEMORY_BYTES,
                    "hard_stop_bytes": V8_ADAPTIVE_HARD_STOP_BYTES,
                    "swap_limit_bytes": SWAP_LIMIT_BYTES,
                },
            }
        )
    elif v8_enabled:
        v8_completed = bool(
            termination_reason == "natural_exit"
            and process.returncode == 0
            and last_stage == "v8_full_spectrum_cleanup_complete"
            and last_stage_status == "complete"
        )
        resource_stop = termination_reason in {
            "absolute_memory_limit",
            "swap_detected",
            "wall_timeout",
            "v8_marker_target_exceeded",
        }
        v8_resource_classification = (
            "v8_completed"
            if v8_completed
            else (
                V8_RESOURCE_UNAVAILABLE_CLASSIFICATION
                if resource_stop
                else "requires_result_adjudication"
            )
        )
        summary.update(
            {
                "v8_completed": v8_completed,
                "latest_stage": last_stage,
                "latest_stage_status": last_stage_status,
                "resource_classification": v8_resource_classification,
                "final_resource_classification": v8_resource_classification,
                "v8_stage_timeout": v8_timeout_decision,
                "v8_resource_limits": {
                    "setup_or_factor_no_marker_seconds": (
                        2 * V8_FULL_SPECTRUM_SETUP_TARGET_SECONDS
                    ),
                    "transform_or_symbol_no_marker_seconds": (
                        2 * V8_FULL_SPECTRUM_TRANSFORM_TARGET_SECONDS
                    ),
                    "one_apply_hard_seconds": (
                        V8_FULL_SPECTRUM_ONE_APPLY_TARGET_SECONDS
                    ),
                    "total_wall_seconds": V8_FULL_SPECTRUM_TIMEOUT_SECONDS,
                },
            }
        )
    if v5_thresholds_enabled:
        peak = int(peak_rss_bytes)
        if peak >= int(plan["absolute_terminate_memory_bytes"]):
            resource_classification = "hard_stop_threshold_crossed"
        elif peak >= int(plan["warning_memory_bytes"]):
            resource_classification = "warning_threshold_crossed"
        elif peak >= int(plan["preferred_memory_bytes"]):
            resource_classification = "preferred_threshold_crossed"
        else:
            resource_classification = "within_preferred_threshold"
        summary.update(
            {
                "preferred_memory_bytes": int(plan["preferred_memory_bytes"]),
                "warning_memory_bytes": int(plan["warning_memory_bytes"]),
                "hard_stop_bytes": int(plan["absolute_terminate_memory_bytes"]),
                "resource_thresholds": resource_thresholds,
                "resource_threshold_observation_count": threshold_observation_count,
                "resource_classification": resource_classification,
                "final_resource_classification": resource_classification,
            }
        )
    elif route_c_enabled:
        route_c_hard_stop = int(plan["absolute_terminate_memory_bytes"])
        if termination_reason == "absolute_memory_limit":
            resource_classification = "route_c_hard_stop_threshold_crossed"
        elif termination_reason == "swap_detected":
            resource_classification = "route_c_swap_blocked"
        elif termination_reason == "wall_timeout":
            resource_classification = "route_c_wall_timeout"
        else:
            resource_classification = "route_c_within_45_gib_hard_line"
        summary.update(
            {
                "route_c_hard_stop_bytes": route_c_hard_stop,
                "route_c_swap_limit_bytes": SWAP_LIMIT_BYTES,
                "route_c_timeout_seconds": TASK040_LEVEL_A_TIMEOUT_SECONDS,
                "route_c_resource_classification": resource_classification,
                "resource_classification": resource_classification,
                "final_resource_classification": resource_classification,
                "route_c_hard_stop_crossed": bool(peak_rss_bytes >= route_c_hard_stop),
                "route_c_peak_memory_bytes": int(peak_rss_bytes),
            }
        )
    elif plan.get("packet_producer") is True:
        summary["preferred_memory_bytes"] = int(plan["preferred_memory_bytes"])
    final_swap_authority_readable = (
        adaptive_swap_authority_readable
        if adaptive_enabled
        else swap_authority_readable
    )
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    completed_gate = (
        adaptive_workflow_completed
        if adaptive_enabled
        else v8_completed
        if v8_enabled
        else (process.returncode == 0 and termination_reason == "natural_exit")
    )
    return (
        0
        if (
            completed_gate
            and run_summary.is_file()
            and final_swap_authority_readable
            and peak_swap_bytes == SWAP_LIMIT_BYTES
            and peak_dedicated_cgroup_swap_bytes == SWAP_LIMIT_BYTES
        )
        else 2
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--input", required=True)
    parser.add_argument("--exact-spool-root", required=True)
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument(TASK040_V1_1_SCALAR_KRYLOV_FLAG, action="store_true")
    parser.add_argument(TASK040_V1_2_INTERFACE_SCHUR_FLAG, action="store_true")
    parser.add_argument(TASK040_V2_INTERFACE_PACKET_PRODUCER_FLAG, action="store_true")
    parser.add_argument(TASK040_V2_INTERFACE_PACKET_CONSUMER_FLAG, action="store_true")
    parser.add_argument(TASK040_V3_2_COUPLED_INTERFACE_FLAG, action="store_true")
    parser.add_argument(
        TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_FLAG, action="store_true"
    )
    parser.add_argument(TASK040_V5_FRESH_BARE_F_AUTHORITY_FLAG, action="store_true")
    parser.add_argument(TASK040_V5_ROUTE_C_FLAG, action="store_true")
    parser.add_argument(TASK040_V6_2_INTERFACE_SCHUR_FLAG, action="store_true")
    parser.add_argument(V7_SCALE_NORMALIZED_IDENTITY_FLAG, action="store_true")
    parser.add_argument(V7_MOVING_PML_FULL_STATE_FLAG, action="store_true")
    parser.add_argument(V8_FULL_SPECTRUM_ONLY_FLAG, action="store_true")
    parser.add_argument(V8_ADAPTIVE_SCHWARZ_ONLY_FLAG, action="store_true")
    parser.add_argument("--watchdog-enabled", action="store_true")
    parser.add_argument("--bottom-route-only", action="store_true")
    parser.add_argument("--interface-packet-root")
    args = parser.parse_args(argv)
    if args.v5_route_c and not (
        args.watchdog_enabled and args.bottom_route_only
    ):
        parser.error(
            "Route C requires --watchdog-enabled and --bottom-route-only"
        )
    if args.v6_2_interface_schur and not (
        args.watchdog_enabled and args.bottom_route_only
    ):
        parser.error(
            "V6-2 interface Schur requires --watchdog-enabled and --bottom-route-only"
        )
    if args.v8_adaptive_schwarz_only and not (
        args.watchdog_enabled and args.bottom_route_only
    ):
        parser.error(
            "V8 adaptive route requires --watchdog-enabled and --bottom-route-only"
        )
    plan = build_task040_level_a_watchdog_plan(
        input_path=args.input,
        exact_spool_root=args.exact_spool_root,
        run_directory=args.run_directory,
        source_sha=args.source_sha,
        scalar_krylov=args.v1_1_scalar_krylov,
        interface_schur=args.v1_2_interface_schur,
        packet_producer=args.v2_interface_packet_producer,
        packet_consumer=args.v2_interface_packet_consumer,
        coupled_interface=args.v3_2_coupled_interface,
        v4_exact_authority_compatibility=args.v4_exact_authority_compatibility,
        v5_fresh_bare_f_authority=args.v5_fresh_bare_f_authority,
        v5_route_c=args.v5_route_c,
        v6_2_interface_schur=args.v6_2_interface_schur,
        v7_scale_normalized_identity=args.v7_scale_normalized_identity,
        v7_moving_pml_full_state=args.v7_moving_pml_full_state,
        v8_full_spectrum_only=args.v8_full_spectrum_only,
        v8_adaptive_schwarz_only=args.v8_adaptive_schwarz_only,
        interface_packet_root=args.interface_packet_root,
    )
    if args.dry_run:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    return run_task040_level_a_watchdog(plan)


if __name__ == "__main__":
    raise SystemExit(main())
