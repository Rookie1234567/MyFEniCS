"""Thin Type=exec Task041 V2 boundary.

One ignored job JSON is shared by ``parent --config`` and
``finalize --config``.  The parent delegates to the reviewed supervisor; the
ExecStopPost finalizer hashes fixed closed files and owns the one ledger
update.  No MPI launcher, numerical environment, artifact copy, retry, or
second resource gate is implemented here.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from benchmarks.task034_wsl_resources import resource_authority_sample
from benchmarks.task041_balh_workflow import task041_schur_speed_v2_contract
from src.io.input_validation import task041_balh_phase_limits_for_model
from src.runners import task041_supervisor as supervisor

PROFILE = "task041_schur_speed_v2"
LEDGER_OWNER = "service_finalizer"
LAUNCH_SCHEMA = "task041.service.launch.v1"
PARENT_SCHEMA = "task041.service.parent_summary.v1"
FINALIZER_SCHEMA = "task041.service.finalizer_summary.v1"
GROUP_FIELDS = {
    "shared_S0_S1_S3": "shared_S0_S1_S3_used_seconds",
    "S2": "S2_used_seconds",
    "S4": "S4_used_seconds",
}
FIXED_ARTIFACTS = (
    "memory_stages.jsonl",
    "markers.jsonl",
    "log/public_command_stdout.txt",
    "summary.json",
    "service_parent_summary.json",
    "launch_manifest.json",
)
SYSTEMD_FIELDS = (
    "MainPID",
    "InvocationID",
    "ControlGroup",
    "ExecMainStartTimestampMonotonic",
)


class Task041ServiceError(RuntimeError):
    """A missing or contradictory fixed service boundary record."""


def _read_job_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    if not path.is_absolute():
        raise Task041ServiceError("Task041 service config must be an absolute path")
    payload = supervisor._read_json(path)
    try:
        unit = payload["unit"]
        model_id = payload["model_id"]
        source_sha = payload["source_sha"]
        ledger_path = Path(payload["ledger_path"])
        supervision_root = Path(payload["supervision_root"])
    except (KeyError, TypeError) as exc:
        raise Task041ServiceError("Task041 service config has missing fixed fields") from exc
    if not isinstance(unit, str) or not unit:
        raise Task041ServiceError("Task041 service config has no unit")
    if not supervisor._valid_sha(source_sha, 40):
        raise Task041ServiceError("Task041 service source_sha is not a Git SHA")
    if not ledger_path.is_absolute() or not supervision_root.is_absolute():
        raise Task041ServiceError("Task041 service paths must be absolute")
    if not isinstance(model_id, str):
        raise Task041ServiceError("Task041 service config has no model_id")
    return payload


def _representative_rhs_probe_binding(
    command: list[str], scope: str
) -> dict[str, str] | None:
    flag = "--task041-rhs-probe"
    positions = [index for index, value in enumerate(command) if value == flag]
    if scope == "representative_rhs":
        if len(positions) != 1 or positions[0] + 1 >= len(command):
            raise Task041ServiceError(
                "representative RHS service command must bind one probe manifest"
            )
        path = Path(command[positions[0] + 1])
        if not path.is_absolute():
            raise Task041ServiceError(
                "representative RHS service probe manifest must be absolute"
            )
        return {"path": str(path), "sha256": supervisor._sha256_file(path)}
    if positions:
        raise Task041ServiceError(
            "formal service command must not bind a representative RHS probe"
        )
    return None


def _systemd_identity(unit: str) -> dict[str, str]:
    completed = subprocess.run(
        [
            "systemctl",
            "--user",
            "show",
            unit,
            "--no-pager",
            f"--property={','.join(SYSTEMD_FIELDS)}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise Task041ServiceError(
            f"systemd identity query failed for {unit}: {completed.stderr}"
        )
    values: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator and key in SYSTEMD_FIELDS:
            values[key] = value
    return values


def _proc_identity(pid: int) -> tuple[int, str]:
    text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    end = text.rfind(")")
    fields = text[end + 2 :].split()
    if len(fields) <= 19:
        raise Task041ServiceError(f"cannot read /proc/{pid}/stat starttime")
    for line in Path(f"/proc/{pid}/cgroup").read_text(encoding="utf-8").splitlines():
        hierarchy, separator, path = line.partition("::")
        if separator and hierarchy == "0":
            return int(fields[19]), path
    raise Task041ServiceError(f"cannot read cgroup v2 path for PID {pid}")


def _cgroup_members(control_group: str) -> list[int] | None:
    if not isinstance(control_group, str) or not control_group.startswith("/"):
        return None
    path = Path("/sys/fs/cgroup") / control_group.lstrip("/") / "cgroup.procs"
    try:
        return sorted(int(value) for value in path.read_text(encoding="ascii").split())
    except (OSError, ValueError):
        return None


def _parent_unit_identity(unit: str) -> dict[str, Any]:
    pid = os.getpid()
    fields = _systemd_identity(unit)
    try:
        main_pid = int(fields["MainPID"])
        start_us = int(fields["ExecMainStartTimestampMonotonic"])
    except (KeyError, ValueError) as exc:
        raise Task041ServiceError("systemd unit has no usable MainPID/start monotonic") from exc
    invocation = os.environ.get("INVOCATION_ID")
    if main_pid != pid:
        raise Task041ServiceError(f"systemd MainPID {main_pid} is not parent PID {pid}")
    if not invocation or fields.get("InvocationID") != invocation:
        raise Task041ServiceError("systemd InvocationID does not match the inherited ID")
    if start_us <= 0:
        raise Task041ServiceError("systemd ExecMainStartTimestampMonotonic is zero")
    control_group = fields.get("ControlGroup", "")
    pid_starttime, proc_group = _proc_identity(pid)
    if not control_group or proc_group != control_group:
        raise Task041ServiceError(f"systemd ControlGroup {control_group!r} does not match /proc {proc_group!r}")
    return {
        "unit": unit, "main_pid": pid, "parent_pid": os.getppid(),
        "pid_starttime_ticks": pid_starttime, "invocation_id": invocation,
        "control_group": control_group, "proc_control_group": proc_group,
        "systemd_fields": fields, "unit_start_monotonic_ns": start_us * 1000,
    }


def _budget_and_charged(
    contract: Mapping[str, Any], ledger: Mapping[str, Any], elapsed: float
) -> tuple[dict[str, Any], dict[str, Any]]:
    phase_group = str(contract["active_consumer_phase"])
    phase_used = supervisor._task041_v2_group_used(ledger, phase_group)
    batch_used = float(ledger["batch_used_compute_wall_seconds"])
    phase_limit = float(contract["phase_budgets_seconds"][phase_group])
    batch_limit = float(contract["batch_budget_seconds"])
    available = max(
        0.0,
        min(phase_limit - phase_used, batch_limit - batch_used),
    )
    snapshot = {
        "phase_group": phase_group,
        "phase_used_before_seconds": phase_used,
        "batch_used_before_seconds": batch_used,
        "phase_limit_seconds": phase_limit,
        "batch_limit_seconds": batch_limit,
        "available_before_unit_seconds": available,
        "basis": "min(phase_limit-phase_used,batch_limit-batch_used)",
    }
    charged = dict(ledger)
    charged[GROUP_FIELDS[phase_group]] = phase_used + elapsed
    charged["batch_used_compute_wall_seconds"] = batch_used + elapsed
    charged["used_compute_wall_seconds"] = float(
        ledger["used_compute_wall_seconds"]
    ) + elapsed
    return snapshot, charged


def _sparse_sample_factory() -> Any:
    from src.runners.task038_launcher import _task041_sparse_smaps_sample_factory

    return _task041_sparse_smaps_sample_factory(
        resource_authority_sample,
        time.monotonic,
        interval=30.0,
    )


def run_service_parent(config_path: str | Path) -> dict[str, Any]:
    config = _read_job_config(config_path)
    contract = task041_schur_speed_v2_contract(
        str(config["model_id"]), scope=config.get("scope")
    )
    phase_limits = dict(
        task041_balh_phase_limits_for_model(str(config["model_id"]), "consumer")
    )
    phase_limits["min_cgroup_ancestor_headroom_bytes"] = phase_limits[
        "min_memavailable_bytes"
    ]
    if phase_limits["swap_limit_bytes"] != 0:
        raise Task041ServiceError("Task041 service requires job swap limit zero")
    ledger_path, ledger = supervisor._load_task041_compute_wall_ledger(
        Path(config["ledger_path"])
    )
    identity = _parent_unit_identity(str(config["unit"]))
    unit_elapsed = max(
        0.0,
        (time.monotonic_ns() - int(identity["unit_start_monotonic_ns"])) / 1e9,
    )
    snapshot, charged = _budget_and_charged(contract, ledger, unit_elapsed)
    root = Path(config["supervision_root"])
    probe_binding = _representative_rhs_probe_binding(
        list(config["public_command"]), contract["scope"]
    )
    launch = {
        "schema": LAUNCH_SCHEMA,
        "config_path": str(Path(config_path)),
        "unit": config["unit"],
        "model_id": config["model_id"],
        "source_sha": config["source_sha"],
        "parent_pid": identity["main_pid"],
        "invocation_id": identity["invocation_id"],
        "ledger_path": str(ledger_path),
        "supervision_root": str(root),
        "global_swap_baseline": dict(config["global_swap_baseline"]),
        "profile_id": PROFILE,
        "scope": contract["scope"],
        "representative_rhs_probe": probe_binding,
        "ledger_owner": LEDGER_OWNER,
        "service_identity": dict(identity),
        "budget_snapshot_before": dict(snapshot),
        "startup_elapsed_seconds": unit_elapsed,
    }
    public = supervisor.run_task041_supervised_public_command(
        list(config["public_command"]),
        root,
        profile_contract=contract,
        ledger_snapshot=charged,
        resource_limits=phase_limits,
        environment=dict(os.environ),
        sample_factory=_sparse_sample_factory(),
        repository_root=Path(__file__).resolve().parents[2],
        global_swap_baseline=dict(config["global_swap_baseline"]),
        launch_manifest=launch,
    )
    members = _cgroup_members(str(identity["control_group"]))
    phase = public.get("phase_result")
    public_return = (
        phase.get("returncode") if isinstance(phase, Mapping) else public.get("exit_status")
    )
    public_ok = public.get("status") == "completed" and public_return == 0
    membership_ok = members == [int(identity["main_pid"])]
    parent_summary = {
        "schema": PARENT_SCHEMA,
        "status": "pre_exit_ok" if public_ok and membership_ok else "pre_exit_failed",
        "public_supervision_completed": public_ok,
        "public_result_classification": public.get("result_classification"),
        "public_exit_status": public_return,
        "supervision_root": str(root),
        "ledger_owner": LEDGER_OWNER,
        "ledger_update": "deferred_to_service_finalizer",
        "nested_phase_wall_seconds": (
            phase.get("wall_seconds") if isinstance(phase, Mapping) else None
        ),
        "used_after": "pending",
        "pre_exit_membership": {
            "members": members,
            "expected_main_pid": int(identity["main_pid"]),
            "pass": membership_ok,
        },
        "public_summary_path": str(root / "summary.json"),
        "parent_wall_seconds_from_unit_start": max(
            0.0,
            (time.monotonic_ns() - int(identity["unit_start_monotonic_ns"]))
            / 1e9,
        ),
    }
    supervisor._write_json(root / "service_parent_summary.json", parent_summary)
    return parent_summary


def hash_closed_root(root: str | Path, output: str | Path) -> dict[str, Any]:
    root_path = Path(root)
    artifacts: dict[str, Any] = {}
    all_present = True
    for relative in FIXED_ARTIFACTS:
        path = root_path / relative
        if not path.is_file():
            all_present = False
            artifacts[relative] = {"status": "missing"}
            continue
        try:
            artifacts[relative] = {
                "status": "hashed",
                "bytes": path.stat().st_size,
                "sha256": supervisor._sha256_file(path),
            }
        except OSError as exc:
            all_present = False
            artifacts[relative] = {"status": "hash_error", "error": str(exc)}
    result = {
        "schema": "task041.service.closed_artifact_hashes.v1",
        "root": str(root_path),
        "artifacts": artifacts,
        "pass": all_present,
    }
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    supervisor._write_json(output_path, result)
    return result


def _terminal_capture() -> dict[str, Any]:
    values = {
        name: os.environ.get(name)
        for name in ("SERVICE_RESULT", "EXIT_CODE", "EXIT_STATUS", "INVOCATION_ID")
    }
    available = all(isinstance(values[name], str) and values[name] for name in values)
    normal_exit = (
        available
        and values["SERVICE_RESULT"] == "success"
        and values["EXIT_CODE"] == "exited"
        and values["EXIT_STATUS"] == "0"
    )
    return {
        **values,
        "available": available,
        "normal_exit": normal_exit,
    }


def _read_closed_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, "missing"
    try:
        return supervisor._read_json(path), None
    except supervisor.Task041SupervisorError as exc:
        return None, str(exc)


def _record_unit_wall(
    config: Mapping[str, Any],
    contract: Mapping[str, Any],
    root: Path,
    seconds: float,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        ledger_path, current_ledger = supervisor._load_task041_compute_wall_ledger(
            Path(config["ledger_path"])
        )
        result = supervisor._write_task041_compute_wall_ledger(
            ledger_path,
            used_before=current_ledger,
            current_seconds=max(0.0, float(seconds)),
            run_directory=root,
            phase_seconds={"service_unit_wall_seconds": max(0.0, float(seconds))},
            limit_seconds=float(contract["batch_budget_seconds"]),
            profile_id=PROFILE,
            phase_group=str(contract["active_consumer_phase"]),
        )
        return result, None
    except (
        OSError,
        KeyError,
        TypeError,
        ValueError,
        supervisor.Task041SupervisorError,
    ) as exc:
        return None, str(exc)


def _run_post_hash(
    root: Path,
    finalizer_root: Path,
    contract: Mapping[str, Any],
    phase_limits: Mapping[str, Any],
    launch: Mapping[str, Any],
    remaining: float,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if remaining <= 0.0:
        return (
            {
                "status": "not_started",
                "reason": "no verified post-I/O budget remains",
                "returncode": None,
            },
            None,
        )
    log_root = finalizer_root / "log"
    log_root.mkdir(parents=True, exist_ok=True)
    post_root = finalizer_root / "post_io_phase"
    partial: dict[str, Any] = {}
    command = [
        sys.executable,
        "-m",
        "src.runners.task041_service",
        "hash",
        "--root",
        str(root),
        "--output",
        str(finalizer_root / "artifact_hashes.json"),
    ]
    try:
        result = supervisor._run_phase(
            "post_io",
            command,
            post_root,
            log_root=log_root,
            environment=dict(os.environ),
            repository_root=Path(__file__).resolve().parents[2],
            workflow_started=time.monotonic(),
            popen_factory=subprocess.Popen,
            sample_factory=_sparse_sample_factory(),
            terminate_factory=supervisor.terminate_process_tree,
            monotonic=time.monotonic,
            sleep=time.sleep,
            poll_interval=0.25,
            memory_stages_path=finalizer_root / "post_memory_stages.jsonl",
            marker_path=finalizer_root / "post_markers.jsonl",
            warning_memory_bytes=int(phase_limits["warning_memory_bytes"]),
            hard_memory_bytes=int(phase_limits["hard_memory_bytes"]),
            process_tree_rss_warning_bytes=int(contract["warning_memory_bytes"]),
            process_tree_rss_cap_bytes=int(contract["memory_cap_bytes"]),
            timeout_seconds=max(1, int(remaining)),
            phase_elapsed_timeout=True,
            sample_root_pid=os.getpid(),
            min_memavailable_bytes=int(phase_limits["min_memavailable_bytes"]),
            min_cgroup_ancestor_headroom_bytes=int(
                phase_limits["min_cgroup_ancestor_headroom_bytes"]
            ),
            cumulative_compute_used_seconds=0.0,
            cumulative_compute_limit_seconds=remaining,
            global_swap_baseline=dict(launch["global_swap_baseline"]),
            partial_phase_results=partial,
            enforce_time_stops=True,
        )
        return result, None
    except supervisor.Task041SupervisorError as exc:
        return (
            partial.get("post_io", {
                "phase": "post_io",
                "returncode": None,
                "partial": True,
            }),
            {
                "type": type(exc).__name__,
                "message": str(exc),
                "stage": exc.stage,
                "classification": exc.classification,
            },
        )


def run_service_finalize(config_path: str | Path) -> dict[str, Any]:
    config = _read_job_config(config_path)
    contract = task041_schur_speed_v2_contract(
        str(config["model_id"]), scope=config.get("scope")
    )
    probe_binding = _representative_rhs_probe_binding(
        list(config["public_command"]), contract["scope"]
    )
    root = Path(config["supervision_root"])
    finalizer_root = root / "finalizer"
    finalizer_root.mkdir(parents=True, exist_ok=False)
    terminal = _terminal_capture()
    launch_path = root / "launch_manifest.json"

    if not launch_path.is_file():
        unit_fields: dict[str, str] = {}
        unit_error = None
        start_ns: int | None = None
        try:
            unit_fields = _systemd_identity(str(config["unit"]))
            start_us = int(unit_fields["ExecMainStartTimestampMonotonic"])
            if start_us > 0 and terminal["INVOCATION_ID"] == unit_fields.get("InvocationID"):
                start_ns = start_us * 1000
        except (OSError, KeyError, ValueError, Task041ServiceError) as exc:
            unit_error = str(exc)
        elapsed = (
            max(0.0, (time.monotonic_ns() - start_ns) / 1e9)
            if start_ns is not None
            else None
        )
        ledger_result = None
        ledger_error = None
        if start_ns is not None:
            ledger_result, ledger_error = _record_unit_wall(
                config, contract, root, elapsed or 0.0
            )
        result = {
            "schema": FINALIZER_SCHEMA,
            "status": "failed",
            "result_classification": "launch_manifest_missing",
            "checks": {
                "launch_manifest": False,
                "unit_start_proven": start_ns is not None,
                "ledger_written": ledger_result is not None,
            },
            "service_terminal": terminal,
            "unit_lookup": {"fields": unit_fields, "error": unit_error},
            "timing": {"unit_start_monotonic_ns": start_ns, "unit_elapsed_seconds": elapsed},
            "supervision_root": str(root),
            "ledger": {
                "owner": LEDGER_OWNER,
                "status": "written" if ledger_result is not None else "not_written",
                "error": ledger_error,
                "reason": (
                    None
                    if ledger_result is not None
                    else "launch start not bound or ledger write failed"
                ),
                "used_after": (
                    ledger_result.get("used_compute_wall_seconds")
                    if isinstance(ledger_result, Mapping)
                    else "pending"
                ),
            },
        }
        supervisor._write_json(finalizer_root / "finalizer_summary.json", result)
        return result

    try:
        launch = supervisor._read_json(launch_path)
        expected = {
            "unit": config["unit"],
            "model_id": config["model_id"],
            "source_sha": config["source_sha"],
            "ledger_path": str(config["ledger_path"]),
            "supervision_root": str(root),
            "profile_id": PROFILE,
            "scope": contract["scope"],
            "representative_rhs_probe": probe_binding,
            "ledger_owner": LEDGER_OWNER,
        }
        if any(launch.get(name) != value for name, value in expected.items()):
            raise Task041ServiceError("launch manifest does not match frozen job config")
        if launch.get("global_swap_baseline") != config["global_swap_baseline"]:
            raise Task041ServiceError("launch manifest swap baseline does not match config")
        launch_identity = launch["service_identity"]
        budget = launch["budget_snapshot_before"]
        if not isinstance(launch_identity, Mapping) or not isinstance(budget, Mapping):
            raise Task041ServiceError("launch manifest identity/budget is incomplete")
        start_ns = launch_identity["unit_start_monotonic_ns"]
        if not isinstance(start_ns, int) or start_ns <= 0:
            raise Task041ServiceError("launch manifest unit start is not measured")
    except (KeyError, TypeError, Task041ServiceError) as exc:
        result = {
            "schema": FINALIZER_SCHEMA,
            "status": "failed",
            "result_classification": "launch_manifest_invalid",
            "checks": {"launch_manifest": False},
            "service_terminal": terminal,
            "launch_manifest": {"path": str(launch_path), "error": str(exc)},
            "ledger": {"owner": LEDGER_OWNER, "status": "not_written"},
        }
        supervisor._write_json(finalizer_root / "finalizer_summary.json", result)
        return result

    phase_limits = dict(
        task041_balh_phase_limits_for_model(str(config["model_id"]), "consumer")
    )
    phase_limits["min_cgroup_ancestor_headroom_bytes"] = phase_limits[
        "min_memavailable_bytes"
    ]
    parent, parent_error = _read_closed_json(root / "service_parent_summary.json")
    public, public_error = _read_closed_json(root / "summary.json")
    invocation_matches = terminal["INVOCATION_ID"] == launch.get("invocation_id")
    unit_elapsed = max(0.0, (time.monotonic_ns() - start_ns) / 1e9)
    available = min(
        float(budget["phase_limit_seconds"])
        - float(budget["phase_used_before_seconds"]),
        float(budget["batch_limit_seconds"])
        - float(budget["batch_used_before_seconds"]),
    )
    post_remaining = max(0.0, available - unit_elapsed)
    post_result: dict[str, Any] = {"status": "not_started", "returncode": None}
    post_error: dict[str, Any] | None = None
    ledger_result: dict[str, Any] | None = None
    ledger_error: str | None = None
    post_members: list[int] | None = None
    full_wall = unit_elapsed
    try:
        try:
            post_result, post_error = _run_post_hash(
                root, finalizer_root, contract, phase_limits, launch, post_remaining
            )
        except (OSError, KeyError, TypeError, ValueError) as exc:
            post_error = {"type": type(exc).__name__, "message": str(exc)}
            post_result = {"status": "failed", "returncode": None, "partial": True}
    finally:
        post_members = _cgroup_members(str(launch_identity.get("control_group", "")))
        full_wall = max(0.0, (time.monotonic_ns() - start_ns) / 1e9)
        ledger_result, ledger_error = _record_unit_wall(
            config, contract, root, full_wall
        )

    artifacts, artifacts_error = _read_closed_json(
        finalizer_root / "artifact_hashes.json"
    )
    pre_members = None
    if isinstance(parent, Mapping):
        pre = parent.get("pre_exit_membership")
        if isinstance(pre, Mapping):
            pre_members = pre.get("members")
    pre_clean = pre_members == [int(launch["parent_pid"])]
    public_phase = public.get("phase_result") if isinstance(public, Mapping) else None
    public_ok = bool(
        isinstance(public, Mapping)
        and public.get("status") == "completed"
        and isinstance(public_phase, Mapping)
        and public_phase.get("returncode") == 0
    )
    post_ok = bool(
        post_error is None
        and post_result.get("termination_reason") is None
        and post_result.get("partial") is not True
        and post_result.get("process_group_gone") is True
        and post_result.get("returncode") == 0
        and not supervisor._phase_resource_failure(post_result)
    )
    artifact_ok = bool(
        isinstance(artifacts, Mapping) and artifacts.get("pass") is True
    )
    checks = {
        "service_terminal_normal": terminal["normal_exit"],
        "invocation_matches": invocation_matches,
        "parent_summary_present": parent is not None,
        "pre_exit_members_clean": pre_clean,
        "public_result_completed": public_ok,
        "post_cgroup_finalizer_only": post_members == [os.getpid()],
        "post_hash_phase_completed": post_ok,
        "closed_artifacts_hashed": artifact_ok,
        "ledger_written": ledger_result is not None,
    }
    reasons = [name for name, passed in checks.items() if not passed]
    result = {
        "schema": FINALIZER_SCHEMA,
        "status": "completed" if not reasons else "failed",
        "result_classification": "service_complete" if not reasons else "service_boundary_failure",
        "checks": checks,
        "reasons": reasons,
        "service_terminal": terminal,
        "launch_manifest": {"path": str(launch_path)},
        "parent_summary": {
            "path": str(root / "service_parent_summary.json"),
            "present": parent is not None,
            "read_error": parent_error,
            "pre_exit_members": pre_members,
        },
        "public_summary": {
            "path": str(root / "summary.json"),
            "present": public is not None,
            "read_error": public_error,
            "completed": public_ok,
        },
        "timing": {
            "unit_start_monotonic_ns": start_ns,
            "unit_elapsed_seconds": full_wall,
            "post_remaining_seconds": post_remaining,
            "basis": "min(phase_limit-phase_used,batch_limit-batch_used)-unit_elapsed",
        },
        "post_io": {
            "root": str(finalizer_root),
            "result": post_result,
            "error": post_error,
            "cgroup_members_after_post": post_members,
        },
        "closed_artifact_hashes": {
            "path": str(finalizer_root / "artifact_hashes.json"),
            "pass": artifact_ok,
            "read_error": artifacts_error,
        },
        "ledger": {
            "owner": LEDGER_OWNER,
            "status": "written" if ledger_result is not None else "not_written",
            "error": ledger_error,
            "used_after": (
                ledger_result.get("used_compute_wall_seconds")
                if isinstance(ledger_result, Mapping)
                else "pending"
            ),
        },
    }
    supervisor._write_json(finalizer_root / "finalizer_summary.json", result)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="task041_service")
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ("parent", "finalize"):
        subparser = subparsers.add_parser(action)
        subparser.add_argument("--config", required=True)
    hasher = subparsers.add_parser("hash")
    hasher.add_argument("--root", required=True)
    hasher.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.action == "parent":
            result = run_service_parent(args.config)
            return 0 if result["status"] == "pre_exit_ok" else 3
        if args.action == "finalize":
            result = run_service_finalize(args.config)
            return 0 if result["status"] == "completed" else 3
        result = hash_closed_root(args.root, args.output)
        return 0 if result["pass"] else 3
    except (Task041ServiceError, supervisor.Task041SupervisorError) as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
