#!/usr/bin/env python3
"""Hash-bound V20 stage inputs and a thin, clocked user-service driver."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runners.workflow_timebase import (  # noqa: E402
    CONSERVATIVE_REALTIME,
    checked_interval,
    clock_sample,
)


ARTIFACT_ROOT = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v20_wsl"
)
CAMPAIGN_RELATIVE = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/"
    "campaign_window_v19.json"
)
CAMPAIGN_SHA256 = "b1591b7cf03b79aaf0820d352e636bdb79a6800bb19489eba92375cb73cbe6b0"
RUNTIME_PREFIX_RELATIVE = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix"
)
ABI_RECEIPT_RELATIVE = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/"
    "continuation_attempt4/abi_receipt.json"
)
QUALIFIED_JIT_RELATIVE = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w9_wsl/"
    "window_qualification_jit"
)
V20_INPUTS = {
    "task40extra_v20_p6_y_orbit_e2_reference_v1": (
        Path("input/task40extra_0p7nm_engineering/nonseparable_e2_p6_reference_v20.dat"),
        {"full"},
    ),
    "task40extra_v20_p6_y_orbit_target_original_ny8_v1": (
        Path(
            "input/task40extra_0p7nm_engineering/"
            "target_original_ny8_resource_pilot_v20.dat"
        ),
        {
            "geometry_inventory",
            "local_port_components",
            "build_and_symbolic",
            "one_q_numeric",
        },
    ),
}
STAGE_PREFIXES = {
    "preflight": ["preflight"],
    "geometry_inventory": ["preflight", "geometry_inventory"],
    "local_port_components": [
        "preflight",
        "geometry_inventory",
        "local_port_components",
    ],
    "build_and_symbolic": ["preflight"],
    "one_q_numeric": ["preflight"],
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _unified_cgroup_membership(pid: int | str = "self") -> str | None:
    try:
        lines = Path(f"/proc/{pid}/cgroup").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        fields = line.split(":", 2)
        if len(fields) == 3 and fields[0] == "0":
            return fields[2]
    return None


def _read_case(path: Path) -> tuple[str, dict[str, Any]]:
    raw = path.read_text(encoding="utf-8")
    return raw, tomllib.loads(raw)


def render_stage_input(canonical_text: str, stop_stage: str) -> str:
    """Change only the V20 execution stop-stage line in a canonical .dat."""

    matches = list(
        re.finditer(
            r'(?m)^task40_execution_stop_stage = "([a-z_]+)"\s*$',
            canonical_text,
        )
    )
    if len(matches) != 1 or matches[0].group(1) != "preflight":
        raise ValueError("canonical V20 input must contain exactly one preflight stop-stage line")
    replaced = canonical_text[: matches[0].start(1)] + stop_stage + canonical_text[matches[0].end(1) :]
    original_data = tomllib.loads(canonical_text)
    changed_data = tomllib.loads(replaced)
    original_data["execution"]["task40_execution_stop_stage"] = stop_stage
    if original_data != changed_data:
        raise ValueError("stage input changes fields beyond execution.task40_execution_stop_stage")
    return replaced


def prepare_stage_inputs(repo_root: Path = ROOT) -> dict[str, Any]:
    artifact_root = repo_root / ARTIFACT_ROOT
    stage_root = artifact_root / "stage_inputs"
    stage_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, str]] = []
    for profile, (canonical_relative, stages) in V20_INPUTS.items():
        canonical = repo_root / canonical_relative
        canonical_bytes = canonical.read_bytes()
        canonical_text = canonical_bytes.decode("utf-8")
        canonical_data = tomllib.loads(canonical_text)
        if canonical_data.get("solver", {}).get("preconditioner") != profile:
            raise ValueError(f"canonical input/profile mismatch: {canonical_relative}")
        if canonical_data.get("execution", {}).get("task40_execution_stop_stage") != "preflight":
            raise ValueError(f"canonical input is no longer the preflight authority: {canonical_relative}")
        for stop_stage in ("preflight", *sorted(stages)):
            if stop_stage == "preflight":
                staged_bytes = canonical_bytes
                destination = canonical
            else:
                staged_bytes = render_stage_input(canonical_text, stop_stage).encode("utf-8")
                destination = stage_root / stop_stage / canonical.name
                destination.parent.mkdir(parents=True, exist_ok=True)
            relative_destination = destination.relative_to(repo_root)
            if stop_stage != "preflight":
                ignored = subprocess.run(
                    ["git", "check-ignore", "-q", str(relative_destination)],
                    cwd=repo_root,
                    check=False,
                )
                if ignored.returncode != 0:
                    raise RuntimeError(f"stage input destination is not git-ignored: {relative_destination}")
                if destination.exists():
                    if destination.read_bytes() != staged_bytes:
                        raise FileExistsError(f"refusing to replace different stage input: {destination}")
                else:
                    with destination.open("xb") as stream:
                        stream.write(staged_bytes)
                        stream.flush()
                        os.fsync(stream.fileno())
            records.append(
                {
                    "profile": profile,
                    "stop_stage": stop_stage,
                    "canonical_path": str(canonical_relative),
                    "canonical_sha256": _sha256_bytes(canonical_bytes),
                    "stage_input_path": str(relative_destination),
                    "stage_input_sha256": _sha256_bytes(staged_bytes),
                }
            )

    campaign = repo_root / CAMPAIGN_RELATIVE
    if _sha256_file(campaign) != CAMPAIGN_SHA256:
        raise ValueError("the existing V19 fixed campaign window SHA differs from V20 authority")
    manifest = {
        "schema": "task40extra.review_v20_stage_input_manifest.v1",
        "canonical_inputs_unchanged": True,
        "campaign_window_path": str(CAMPAIGN_RELATIVE),
        "campaign_window_sha256": CAMPAIGN_SHA256,
        "stage_inputs": records,
        "launch_command": (
            "bash scripts/run_case_in_user_service.sh <stage_input.dat> "
            "--task40-v10-campaign-window "
            "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/"
            "campaign_window_v19.json"
        ),
    }
    manifest_path = stage_root / "stage_input_manifest.json"
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"
    if manifest_path.exists() and manifest_path.read_bytes() != encoded:
        raise FileExistsError(f"refusing to replace a different stage input manifest: {manifest_path}")
    if not manifest_path.exists():
        with manifest_path.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    command_lines = [
        "# Task40 V20 staged-input commands; run only after source freeze",
        "",
        "Each input keeps the canonical basename and changes only `execution.task40_execution_stop_stage`;",
        "the canonical input remains at its original path. Hashes are in `stage_input_manifest.json`.",
        "The local-port command completes preflight, geometry inventory, then local/port components in one run.",
        "The E2 full command is registered but remains conditional on the existing campaign deadline and resource gates.",
        "build_and_symbolic and one_q_numeric target inputs are registered but remain refused: the canonical authorization flag is false, so both stop after preflight.",
        "",
        "",
    ]
    for row in records:
        command_lines.append(
            "bash scripts/run_case_in_user_service.sh "
            f"{row['stage_input_path']} --task40-v10-campaign-window "
            f"{CAMPAIGN_RELATIVE}"
        )
    commands_path = stage_root / "stage_commands.md"
    commands_text = "\n".join(command_lines) + "\n"
    if commands_path.exists() and commands_path.read_text(encoding="utf-8") != commands_text:
        raise FileExistsError(f"refusing to replace a different stage command package: {commands_path}")
    if not commands_path.exists():
        with commands_path.open("x", encoding="utf-8") as stream:
            stream.write(commands_text)
            stream.flush()
            os.fsync(stream.fileno())
    manifest["manifest_path"] = str(manifest_path.relative_to(repo_root))
    manifest["commands_path"] = str(commands_path.relative_to(repo_root))
    return manifest


def _append_clock_event(
    events: list[dict[str, Any]],
    label: str,
    event_log: Path,
    identity: dict[str, Any],
) -> dict[str, Any]:
    event = {
        "label": label,
        "sample": clock_sample(include_boot_id=True),
        "identity": identity,
    }
    events.append(event)
    with event_log.open("ab") as stream:
        stream.write(json.dumps(event, sort_keys=True, separators=(",", ":")).encode() + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    return event["sample"]


def _write_json_fsync(path: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"
    with path.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def _set_first_failure(
    record: dict[str, Any], kind: str, message: str, returncode: int | None = None
) -> None:
    if "first_failure" not in record:
        record["first_failure"] = {
            "kind": kind,
            "message": message,
            "returncode": returncode,
        }


def _parse_run_case_result(stdout: str) -> dict[str, Any]:
    """Find the launcher-result object emitted by run_case, ignoring other lines."""

    required = {"run_directory", "manifest", "summary", "result_classification"}
    decoder = json.JSONDecoder()
    found: dict[str, Any] | None = None
    for start, char in enumerate(stdout):
        if char != "{":
            continue
        try:
            payload, _end = decoder.raw_decode(stdout[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and required.issubset(payload):
            found = payload
    if found is None:
        raise ValueError("run_case stdout contains no launcher result object")
    return found


def _intervals(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    intervals: list[dict[str, Any]] = []
    errors: list[str] = []
    boot_ids = {event["sample"].get("boot_id") for event in events}
    if len(boot_ids) != 1 or None in boot_ids:
        errors.append("clock samples have missing or mixed boot_id values")
    for left, right in zip(events, events[1:]):
        try:
            interval = checked_interval(
                left["sample"],
                right["sample"],
                policy=CONSERVATIVE_REALTIME,
            )
            intervals.append(
                {
                    "from": left["label"],
                    "to": right["label"],
                    **interval,
                }
            )
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            errors.append(f"{left['label']}->{right['label']}: {type(exc).__name__}: {exc}")
    return intervals, errors


def _activation_environment(
    repo_root: Path, runtime_prefix: Path, abi_receipt: Path, jit_cache: Path
) -> tuple[dict[str, str], str, int, str]:
    command = (
        'set -euo pipefail; cd -- "$1"; '
        'source scripts/task40_fresh_c1/activate_local_wsl_complex.sh "$2" "$3" "$4"; '
        'env -0'
    )
    argv = [
        "/usr/bin/bash",
        "-lc",
        command,
        "task40-v20-activation",
        str(repo_root),
        str(runtime_prefix),
        str(abi_receipt),
        str(jit_cache),
    ]
    completed = subprocess.run(argv, cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    environment: dict[str, str] = {}
    for item in completed.stdout.split(b"\0"):
        if item and b"=" in item:
            key, value = item.split(b"=", 1)
            environment[key.decode()] = value.decode(errors="surrogateescape")
    return (
        environment,
        " ".join(argv),
        int(completed.returncode),
        completed.stderr.decode("utf-8", errors="replace"),
    )


def _abi_preflight(
    runtime_prefix: Path, environment: dict[str, str], repo_root: Path
) -> tuple[list[str], int, str, str]:
    snippet = r'''
import json, pathlib, sys
import numpy as np
from petsc4py import PETSc
from mpi4py import MPI
import petsc4py, slepc4py, dolfinx, mpi4py
prefix = pathlib.Path(sys.argv[1]).resolve()
assert pathlib.Path(sys.executable).resolve().is_relative_to(prefix)
assert np.dtype(PETSc.ScalarType) == np.dtype(np.complex128)
assert np.dtype(PETSc.IntType) == np.dtype(np.int32)
assert MPI.COMM_WORLD.Get_size() == 1
modules = (petsc4py, slepc4py, dolfinx, mpi4py)
for module in modules:
    assert pathlib.Path(module.__file__).resolve().is_relative_to(prefix)
print(json.dumps({
    "python": sys.executable,
    "scalar_type": str(np.dtype(PETSc.ScalarType)),
    "int_type": str(np.dtype(PETSc.IntType)),
    "mpi_size": MPI.COMM_WORLD.Get_size(),
    "abi_module_paths": {m.__name__: m.__file__ for m in modules},
}))
'''
    argv = [str(runtime_prefix / "bin/python"), "-c", snippet, str(runtime_prefix)]
    completed = subprocess.run(
        argv,
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
    )
    return argv, int(completed.returncode), completed.stdout, completed.stderr


def _parse_case_arguments(case_args: list[str]) -> tuple[Path, Path, str, dict[str, Any]]:
    if not case_args:
        raise ValueError("V20 service requires a .dat input")
    input_path = Path(case_args[0]).resolve()
    text, data = _read_case(input_path)
    del text
    profile = str(data.get("solver", {}).get("preconditioner", ""))
    case = V20_INPUTS.get(profile)
    if case is None:
        raise ValueError("service V20 branch received a non-V20 profile")
    canonical_relative, supported_stages = case
    stop_stage = str(data.get("execution", {}).get("task40_execution_stop_stage", ""))
    if stop_stage not in supported_stages | {"preflight"}:
        raise ValueError(f"unsupported user-service stop stage for {profile}: {stop_stage}")
    campaign: Path | None = None
    for index, arg in enumerate(case_args):
        if arg == "--task40-v10-campaign-window" and index + 1 < len(case_args):
            campaign = Path(case_args[index + 1])
        elif arg.startswith("--task40-v10-campaign-window="):
            campaign = Path(arg.split("=", 1)[1])
    if campaign is None:
        raise ValueError("V20 service route requires the existing fixed campaign window")
    return input_path, campaign, stop_stage, data


def _run_case_output_checker(packet_path: Path, runtime_prefix: Path) -> list[str]:
    return [
        str(runtime_prefix / "bin/python"),
        "-m",
        "src.runners.task40_v10_output_checker",
        str(packet_path),
        "--expected-channel-count",
        "700",
    ]


def _run_required_checker_supervision(request: dict[str, Any]) -> dict[str, Any]:
    """Run the checker under the fixed Task40 watchdog gates in a qualified child."""

    from benchmarks.subreaper_watchdog import PHYSICAL_MEMORY_PRESSURE_POLICY, supervise
    from src.io.physical_intermediate_profile import profile_facts
    from src.runners.physical_v14_budget import V14_TIME_POLICY_ENFORCE

    command = [str(value) for value in request["command"]]
    checker_kind = str(request["checker_kind"])
    evidence_directory = Path(request["evidence_directory"])
    runtime_prefix = Path(request["runtime_prefix"])
    environment = dict(os.environ)
    activation_marker = environment.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION")
    if request.get("activation_marker") != activation_marker:
        raise RuntimeError("required checker supervisor activation identity differs")
    numeric_environment = request.get("numeric_environment", {})
    if not isinstance(numeric_environment, dict):
        raise RuntimeError("required checker supervisor numeric environment is malformed")
    allowed_numeric_settings = {
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    }
    if not set(numeric_environment) <= allowed_numeric_settings:
        raise RuntimeError("required checker supervisor request has unsupported environment fields")
    for key, value in numeric_environment.items():
        if environment.get(key) != value:
            raise RuntimeError(f"required checker supervisor setting differs: {key}")
    tree_accounting_root_pid = int(request["service_parent_pid"])
    service_cgroup_membership = str(request["service_cgroup_membership"])
    repo_root = Path(request["repo_root"])
    campaign_window = Path(request["campaign_window"])
    campaign_sha256 = str(request["campaign_sha256"])
    campaign_accounting = Path(request["campaign_accounting"])
    source_state = dict(request["source_state"])
    profile = str(request["profile"])

    if environment.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("required checker supervisor lacks qualified activation")
    if not os.path.samefile(sys.executable, runtime_prefix / "bin/python"):
        raise RuntimeError("required checker supervisor is not using the qualified interpreter")

    resources = profile_facts(profile)["resources"]
    if resources.get("watchdog_memory_policy") != PHYSICAL_MEMORY_PRESSURE_POLICY:
        raise ValueError("V20 checker watchdog policy differs from the qualified physical-pressure policy")
    workflow_limit_seconds = float(resources["workflow_seconds"])
    watchdog_directory = evidence_directory / "required_checker_watchdog"
    worker_environment = dict(environment)
    worker_environment.update(
        {
            "TASK40_V10_CAMPAIGN_WINDOW": str(campaign_window),
            "TASK40_V10_CAMPAIGN_WINDOW_SHA256": campaign_sha256,
            "TASK40_V10_CAMPAIGN_ACCOUNTING": str(campaign_accounting),
            "PHYSICAL_WATCHDOG_MEMORY_POLICY": str(
                resources["watchdog_memory_policy"]
            ),
            "PHYSICAL_WATCHDOG_PSS_POLICY": str(resources["pss_sampling_policy"]),
            "XDG_CACHE_HOME": str(
                (repo_root / QUALIFIED_JIT_RELATIVE).resolve()
            ),
        }
    )
    watchdog_summary = supervise(
        command,
        watchdog_directory,
        wall_seconds=workflow_limit_seconds,
        grace_seconds=30.0,
        hard_stop_immediate=True,
        timebase_guard=True,
        timebase_policy=CONSERVATIVE_REALTIME,
        time_policy=V14_TIME_POLICY_ENFORCE,
        memory_policy=str(resources["watchdog_memory_policy"]),
        pss_sampling_policy=str(resources["pss_sampling_policy"]),
        tree_cap_bytes=int(resources["process_tree_rss_cap_bytes"]),
        allow_physical_pressure_tree_cap=True,
        require_job_cgroup_zero_swap=True,
        campaign_window_path=campaign_window,
        campaign_window_sha256=campaign_sha256,
        campaign_accounting_path=campaign_accounting,
        worker_environment=worker_environment,
        source_state=source_state,
        tree_accounting_root_pid=tree_accounting_root_pid,
    )
    summary_path = evidence_directory / "required_checker_watchdog_summary.json"
    _write_json_fsync(summary_path, watchdog_summary)
    raw_output = watchdog_directory / "worker.log"
    if raw_output.is_file():
        raw_path = evidence_directory / "required_checker_output.raw.txt"
        with raw_path.open("xb") as stream:
            stream.write(raw_output.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        raw_text = raw_path.read_text(encoding="utf-8", errors="replace")
    else:
        raw_path = None
        raw_text = ""
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        payload = None
    complete = bool(
        watchdog_summary.get("classification") == "COMPLETED"
        and watchdog_summary.get("leader_exit_code") == 0
        and watchdog_summary.get("descendants_cleared") is True
    )
    exit_code = watchdog_summary.get("leader_exit_code")
    return_code = 0 if complete else (
        int(exit_code) if type(exit_code) is int and exit_code != 0 else 2
    )
    details = {
        "kind": checker_kind,
        "command": command,
        "watchdog_directory": str(watchdog_directory),
        "watchdog_summary_path": str(summary_path),
        "raw_output_path": None if raw_path is None else str(raw_path),
        "raw_output_sha256": None if raw_path is None else _sha256_file(raw_path),
        "watchdog_classification": watchdog_summary.get("classification"),
        "leader_exit_code": exit_code,
        "returncode": return_code,
        "payload": payload if isinstance(payload, dict) else None,
        "supervision": {
            "profile_workflow_limit_seconds": workflow_limit_seconds,
            "campaign_closeout_reserve_seconds": int(
                resources["campaign_closeout_reserve_seconds"]
            ),
            "campaign_window_sha256": campaign_sha256,
            "campaign_accounting_path": str(campaign_accounting),
            "memory_policy": resources["watchdog_memory_policy"],
            "pss_sampling_policy": resources["pss_sampling_policy"],
            "process_tree_rss_cap_bytes": resources["process_tree_rss_cap_bytes"],
            "zero_swap_required": True,
            "service_cgroup_membership": service_cgroup_membership,
            "process_tree_root_pid": tree_accounting_root_pid,
            "process_tree_scope_includes_user_service_parent": True,
            "process_tree_cleanup_required": True,
        },
    }
    return {
        "return_code": return_code,
        "payload": details["payload"],
        "details": details,
    }


def _supervise_required_checker(
    *,
    command: list[str],
    checker_kind: str,
    evidence_directory: Path,
    runtime_prefix: Path,
    environment: dict[str, str],
    repo_root: Path,
    campaign_window: Path,
    campaign_sha256: str,
    campaign_accounting: Path,
    source_state: dict[str, Any],
    profile: str,
    events: list[dict[str, Any]],
    event_log: Path,
    event_identity: dict[str, Any],
) -> tuple[int, dict[str, Any] | None, dict[str, Any]]:
    """Launch the watchdog from the qualified interpreter, away from the -S parent."""

    if environment.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("V20 user-service did not receive the qualified activation marker")
    request_path = evidence_directory / "required_checker_supervision_request.json"
    response_path = evidence_directory / "required_checker_supervision_response.json"
    stdout_path = evidence_directory / "required_checker_supervisor_stdout.raw.txt"
    stderr_path = evidence_directory / "required_checker_supervisor_stderr.raw.txt"
    service_parent_pid = os.getpid()
    service_cgroup_membership = _unified_cgroup_membership(service_parent_pid)
    if service_cgroup_membership is None:
        raise RuntimeError("V20 service parent has no readable unified-cgroup identity")
    numeric_setting_names = (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    )
    request = {
        "command": command,
        "checker_kind": checker_kind,
        "evidence_directory": str(evidence_directory),
        "runtime_prefix": str(runtime_prefix),
        "activation_marker": environment.get(
            "_MYFENICS_WSL_QUALIFIED_ACTIVATION"
        ),
        "numeric_environment": {
            key: environment[key]
            for key in numeric_setting_names
            if key in environment
        },
        "service_parent_pid": service_parent_pid,
        "service_cgroup_membership": service_cgroup_membership,
        "repo_root": str(repo_root),
        "campaign_window": str(campaign_window),
        "campaign_sha256": campaign_sha256,
        "campaign_accounting": str(campaign_accounting),
        "source_state": source_state,
        "profile": profile,
        "response_path": str(response_path),
    }
    _write_json_fsync(request_path, request)
    supervisor_command = [
        str(runtime_prefix / "bin/python"),
        str(Path(__file__).resolve()),
        "supervise-required-checker",
        "--request",
        str(request_path),
    ]
    child = subprocess.run(
        supervisor_command,
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
    )
    for path, content in ((stdout_path, child.stdout), (stderr_path, child.stderr)):
        with path.open("xb") as stream:
            stream.write(content.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
    if child.returncode != 0 or not response_path.is_file():
        raise RuntimeError(
            "qualified required-checker supervisor failed "
            f"(returncode={child.returncode}): "
            f"{child.stderr[-4000:] or child.stdout[-4000:]}"
        )
    response = json.loads(response_path.read_text(encoding="utf-8"))
    if not isinstance(response, dict) or not isinstance(response.get("details"), dict):
        raise RuntimeError("qualified required-checker supervisor returned an invalid receipt")
    _append_clock_event(
        events, "required_checker_finished", event_log, event_identity
    )
    details = dict(response["details"])
    details["qualified_supervisor"] = {
        "command": supervisor_command,
        "returncode": int(child.returncode),
        "activation_marker": environment.get(
            "_MYFENICS_WSL_QUALIFIED_ACTIVATION"
        ),
        "request_path": str(request_path),
        "request_sha256": _sha256_file(request_path),
        "response_path": str(response_path),
        "response_sha256": _sha256_file(response_path),
        "stdout_path": str(stdout_path),
        "stdout_sha256": _sha256_file(stdout_path),
        "stderr_path": str(stderr_path),
        "stderr_sha256": _sha256_file(stderr_path),
    }
    payload = response.get("payload")
    return int(response["return_code"]), (
        payload if isinstance(payload, dict) else None
    ), details


def _run_required_checker_supervision_request(request_path: Path) -> int:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    runtime_prefix = Path(request["runtime_prefix"])
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("required checker supervisor child lacks qualified activation")
    if not os.path.samefile(sys.executable, runtime_prefix / "bin/python"):
        raise RuntimeError("required checker supervisor child interpreter identity differs")
    if int(request["service_parent_pid"]) != os.getppid():
        raise RuntimeError("required checker supervisor lost its user-service parent identity")
    if request["service_cgroup_membership"] != _unified_cgroup_membership():
        raise RuntimeError("required checker supervisor moved out of the user-service cgroup")
    response = _run_required_checker_supervision(request)
    _write_json_fsync(Path(request["response_path"]), response)
    return 0


def _campaign_accounting_path_from_manifest(
    run_manifest: dict[str, Any],
    *,
    expected_window_sha256: str,
    expected_accounting_path: Path,
    expected_run_id: str,
    expected_profile: str,
) -> Path:
    """Validate this V20 case's identity and its fixed campaign ledger."""

    campaign_evidence = run_manifest.get("task40_v20_campaign")
    if not isinstance(campaign_evidence, dict):
        raise ValueError("run manifest has no Task40 V20 campaign accounting identity")
    solver = run_manifest.get("solver")
    if (
        run_manifest.get("run_id") != expected_run_id
        or not isinstance(solver, dict)
        or solver.get("preconditioner") != expected_profile
    ):
        raise ValueError("run manifest does not match the requested Task40 V20 case/profile")
    accounting_path = Path(str(campaign_evidence.get("accounting_path", ""))).resolve()
    if (
        campaign_evidence.get("window_sha256") != expected_window_sha256
        or accounting_path != expected_accounting_path.resolve()
        or not accounting_path.is_file()
    ):
        raise ValueError(
            "run manifest Task40 V20 campaign window/accounting identity is invalid"
        )
    return accounting_path


def _checker_numerical_output_directory(
    run_directory: Path, declared_numerical_output: Path
) -> Path:
    """Locate the actual packet/footer root emitted for this run."""

    candidates = (declared_numerical_output.resolve(), run_directory.resolve())
    for candidate in candidates:
        if (candidate / "v10_candidate_official_output.json").is_file():
            return candidate
    for candidate in candidates:
        if (candidate / "v20_partial_result.json").is_file():
            return candidate
    return candidates[0]


def _official_checker_passed(returncode: int, payload: Any) -> bool:
    """The checker CLI's authoritative success marker is status=PASS."""

    return bool(
        returncode == 0 and isinstance(payload, dict) and payload.get("status") == "PASS"
    )


def _check_partial_result(
    *,
    input_path: Path,
    summary_path: Path,
    manifest_path: Path,
    numerical_output: Path,
    expected_stop_stage: str,
) -> dict[str, Any]:
    """Check a raw stage footer; explicitly never promote it to a full result."""

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    _, input_data = _read_case(input_path)
    partial_path = numerical_output / "v20_partial_result.json"
    if not partial_path.is_file():
        return {
            "schema": "task40extra.review_v20_partial_stage_checker.v1",
            "status": "NO_PARTIAL_FOOTER",
            "checker_passed": False,
            "official_result": False,
            "full_pass": False,
            "run_summary_result_classification": run_summary.get("result_classification"),
            "run_summary_path": str(summary_path),
            "raw_output_directory": str(numerical_output),
            "error": "no official packet or V20 partial footer exists; preserve run/watchdog raw evidence",
        }
    partial = json.loads(partial_path.read_text(encoding="utf-8"))
    expected_completed = STAGE_PREFIXES.get(expected_stop_stage)
    if expected_stop_stage == "full" and manifest.get("mesh_id") == "TARGET_ORIGINAL_NY8":
        expected_completed = ["preflight"]
    checks = {
        "run_id_matches": partial.get("run_id") == manifest.get("run_id"),
        "source_sha_matches": partial.get("source_sha") == manifest.get("source_sha"),
        "input_sha_matches": partial.get("input_sha256") == manifest.get("input_sha256"),
        "physical_model_sha_matches": partial.get("physical_model_sha256")
        == manifest.get("physical_model_sha256"),
        "requested_stage_matches": partial.get("requested_stop_stage") == expected_stop_stage,
        "official_result_false": partial.get("official_result") is False,
        "completed_stages_expected": (
            expected_completed is None or partial.get("completed_stages") == expected_completed
        ),
    }
    if expected_stop_stage in {"build_and_symbolic", "one_q_numeric"}:
        checks["target_heavy_authorization_remains_false"] = (
            input_data.get("execution", {}).get("task40_target_heavy_authorized") is False
        )
    if "geometry_inventory" in (partial.get("completed_stages") or []):
        checks["geometry_artifact_present"] = (
            numerical_output / "v20_geometry_inventory.json"
        ).is_file()
    if "local_port_components" in (partial.get("completed_stages") or []):
        checks["local_components_artifact_present"] = (
            numerical_output / "v20_local_port_components.json"
        ).is_file()
    status = str(partial.get("status", ""))
    checks["partial_status_not_full_pass"] = status != "PASS" and partial.get("official_result") is not True
    checker_passed = all(checks.values())
    return {
        "schema": "task40extra.review_v20_partial_stage_checker.v1",
        "status": "PARTIAL_RECEIPT_CHECKED" if checker_passed else "PARTIAL_RECEIPT_INVALID",
        "checker_passed": checker_passed,
        "official_result": False,
        "full_pass": False,
        "scientific_partial_status": status,
        "requested_stop_stage": expected_stop_stage,
        "partial_result_path": str(partial_path),
        "partial_result_sha256": _sha256_file(partial_path),
        "run_summary_result_classification": run_summary.get("result_classification"),
        "checks": checks,
        "errors": [key for key, passed in checks.items() if not passed],
        "raw_evidence_preserved": True,
    }


def _check_partial_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--numerical-output", type=Path, required=True)
    parser.add_argument("--stop-stage", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = _check_partial_result(
        input_path=args.input,
        summary_path=args.summary,
        manifest_path=args.manifest,
        numerical_output=args.numerical_output,
        expected_stop_stage=args.stop_stage,
    )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["checker_passed"] else 2


def run_service(
    *,
    unit: str,
    runtime_prefix: Path,
    abi_receipt: Path,
    jit_cache: Path,
    case_args: list[str],
    repo_root: Path = ROOT,
) -> int:
    if case_args and case_args[0] == "--":
        case_args = case_args[1:]
    input_path, campaign_path, stop_stage, data = _parse_case_arguments(case_args)
    canonical_relative, _supported = V20_INPUTS[data["solver"]["preconditioner"]]
    canonical_path = repo_root / canonical_relative
    canonical_text = canonical_path.read_text(encoding="utf-8")
    if input_path != canonical_path:
        expected_text = render_stage_input(canonical_text, stop_stage)
        if input_path.name != canonical_path.name or input_path.read_text(encoding="utf-8") != expected_text:
            raise ValueError("stage input is not an exact same-basename, one-field variant of the canonical input")
        if not input_path.is_relative_to((repo_root / ARTIFACT_ROOT / "stage_inputs").resolve()):
            raise ValueError("noncanonical V20 stage input must live in the ignored stage_inputs artifact")
    elif stop_stage != "preflight":
        raise ValueError("canonical V20 inputs are immutable preflight inputs")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", unit):
        raise ValueError("invalid systemd user-service unit name")
    fixed_campaign = repo_root / CAMPAIGN_RELATIVE
    if campaign_path.resolve() != fixed_campaign.resolve() or _sha256_file(fixed_campaign) != CAMPAIGN_SHA256:
        raise ValueError("V20 service must use the unchanged fixed V19 campaign window")
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=repo_root, text=True).strip()
    source_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=repo_root, text=True)
    if branch != "task40extra_0p7nm_engineering" or dirty.strip():
        raise RuntimeError("V20 user-service requires the frozen Task40 branch and clean source")

    evidence_directory = repo_root / ARTIFACT_ROOT / "service_runs" / unit
    evidence_directory.mkdir(parents=True, exist_ok=False)
    events: list[dict[str, Any]] = []
    event_log = evidence_directory / "outer_clock_events.jsonl"
    record: dict[str, Any] = {
        "schema": "task40extra.review_v20_user_service_workflow.v1",
        "unit": unit,
        "branch": branch,
        "source_sha": source_sha,
        "working_tree_clean": True,
        "input_path": str(input_path),
        "input_sha256": _sha256_file(input_path),
        "canonical_input_path": str(canonical_path),
        "canonical_input_sha256": _sha256_file(canonical_path),
        "physical_model_sha256": None,
        "stop_stage": stop_stage,
        "campaign_window_path": str(fixed_campaign),
        "campaign_window_sha256": CAMPAIGN_SHA256,
        "abi_receipt_path": str(abi_receipt),
        "abi_receipt_sha256": _sha256_file(abi_receipt),
        "qualified_jit_cache": str(jit_cache),
        "run_case_argv": [str(runtime_prefix / "bin/python"), "scripts/run_case.py", *case_args],
        "evidence_directory": str(evidence_directory),
    }
    event_identity = {
        key: record[key]
        for key in (
            "unit",
            "branch",
            "source_sha",
            "input_path",
            "input_sha256",
            "canonical_input_sha256",
            "campaign_window_sha256",
            "abi_receipt_sha256",
            "stop_stage",
        )
    }
    record["outer_clock_events_path"] = str(event_log)
    _append_clock_event(
        events, "user_service_parent_before_activation", event_log, event_identity
    )
    run_case_code: int | None = None
    checker_code: int | None = None
    checker_kind: str | None = None
    try:
        _append_clock_event(events, "activation_started", event_log, event_identity)
        environment, activation_command, activation_code, activation_stderr = _activation_environment(
            repo_root, runtime_prefix, abi_receipt, jit_cache
        )
        _append_clock_event(events, "activation_finished", event_log, event_identity)
        record["activation_command"] = activation_command
        record["activation_returncode"] = activation_code
        if activation_stderr:
            activation_stderr_path = evidence_directory / "activation_stderr.raw.txt"
            activation_stderr_path.write_text(activation_stderr, encoding="utf-8")
            record["activation_stderr_path"] = str(activation_stderr_path)
            record["activation_stderr_sha256"] = _sha256_file(activation_stderr_path)
        if activation_code != 0:
            raise RuntimeError(
                "qualified activation failed: " + activation_stderr[-4000:]
            )
        if environment.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
            raise RuntimeError("V20 user-service did not receive the qualified activation marker")

        abi_command, abi_code, abi_stdout, abi_stderr = _abi_preflight(
            runtime_prefix, environment, repo_root
        )
        _append_clock_event(events, "abi_preflight_finished", event_log, event_identity)
        record["abi_preflight_command"] = abi_command
        record["abi_preflight_returncode"] = abi_code
        for label, value in (("stdout", abi_stdout), ("stderr", abi_stderr)):
            path = evidence_directory / f"abi_preflight_{label}.raw.txt"
            path.write_text(value, encoding="utf-8")
            record[f"abi_preflight_{label}_sha256"] = _sha256_file(path)
        if abi_code != 0:
            raise RuntimeError(
                "qualified ABI preflight failed: " + abi_stderr[-4000:]
            )
        abi = json.loads(abi_stdout)
        record["abi_preflight"] = abi

        _append_clock_event(events, "run_case_started", event_log, event_identity)
        case_command = record["run_case_argv"]
        run_case_result = subprocess.run(
            case_command,
            cwd=repo_root,
            env=environment,
            capture_output=True,
            text=True,
        )
        run_case_code = int(run_case_result.returncode)
        _append_clock_event(events, "run_case_finished", event_log, event_identity)
        (evidence_directory / "run_case_stdout.raw.txt").write_text(
            run_case_result.stdout, encoding="utf-8"
        )
        (evidence_directory / "run_case_stderr.raw.txt").write_text(
            run_case_result.stderr, encoding="utf-8"
        )
        record["run_case_stdout_path"] = str(evidence_directory / "run_case_stdout.raw.txt")
        record["run_case_stderr_path"] = str(evidence_directory / "run_case_stderr.raw.txt")
        record["run_case_returncode"] = run_case_code
        record["run_case_stdout_sha256"] = _sha256_file(evidence_directory / "run_case_stdout.raw.txt")
        record["run_case_stderr_sha256"] = _sha256_file(evidence_directory / "run_case_stderr.raw.txt")
        if run_case_code != 0:
            _set_first_failure(
                record,
                "run_case_failed",
                f"run_case returned {run_case_code}",
                run_case_code,
            )
        run_case_payload = _parse_run_case_result(run_case_result.stdout)
        summary_path = Path(str(run_case_payload["summary"])).resolve()
        manifest_path = Path(str(run_case_payload["manifest"])).resolve()
        run_directory = Path(str(run_case_payload["run_directory"])).resolve()
        run_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        run_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        numerical_output = _checker_numerical_output_directory(
            run_directory,
            Path(str(run_summary["numerical_output_directory"])),
        )
        record.update(
            run_directory=str(run_directory),
            run_summary_path=str(summary_path),
            run_manifest_path=str(manifest_path),
            physical_model_sha256=run_manifest.get("physical_model_sha256"),
            input_sha256_from_manifest=run_manifest.get("input_sha256"),
            run_case_result_classification=run_case_payload.get("result_classification"),
        )

        _append_clock_event(events, "required_checker_started", event_log, event_identity)
        packet_path = numerical_output / "v10_candidate_official_output.json"
        if packet_path.is_file():
            checker_kind = "task40_v10_independent_output_checker"
            checker_command = _run_case_output_checker(packet_path, runtime_prefix)
        else:
            checker_kind = "task40_v20_partial_receipt_checker"
            checker_output = evidence_directory / "partial_checker_result.json"
            checker_command = [
                str(runtime_prefix / "bin/python"),
                "scripts/task40_v20_service_workflow.py",
                "check-partial",
                "--input",
                str(input_path),
                "--summary",
                str(summary_path),
                "--manifest",
                str(manifest_path),
                "--numerical-output",
                str(numerical_output),
                "--stop-stage",
                stop_stage,
                "--output",
                str(checker_output),
            ]
            record["partial_checker_result_path"] = str(checker_output)
        campaign_accounting = _campaign_accounting_path_from_manifest(
            run_manifest,
            expected_window_sha256=CAMPAIGN_SHA256,
            expected_accounting_path=fixed_campaign.with_name(
                "campaign_accounting_v10.jsonl"
            ),
            expected_run_id=str(data["run_id"]),
            expected_profile=str(data["solver"]["preconditioner"]),
        )
        checker_code, checker_payload, checker_details = _supervise_required_checker(
            command=checker_command,
            checker_kind=checker_kind,
            evidence_directory=evidence_directory,
            runtime_prefix=runtime_prefix,
            environment=environment,
            repo_root=repo_root,
            campaign_window=fixed_campaign,
            campaign_sha256=CAMPAIGN_SHA256,
            campaign_accounting=campaign_accounting,
            source_state={"branch": branch, "source_sha": source_sha, "clean": True},
            profile=str(data["solver"]["preconditioner"]),
            events=events,
            event_log=event_log,
            event_identity=event_identity,
        )
        record["required_checker_command"] = checker_command
        record["required_checker"] = checker_details
        record["required_checker_returncode"] = checker_code
        record["required_checker_payload"] = checker_payload
        if checker_kind == "task40_v10_independent_output_checker":
            checker_passed = _official_checker_passed(checker_code, checker_payload)
        else:
            checker_passed = bool(
                checker_code == 0
                and isinstance(checker_payload, dict)
                and checker_payload.get("checker_passed") is True
                and checker_payload.get("full_pass") is False
            )
            partial_status = (
                checker_payload.get("scientific_partial_status")
                if isinstance(checker_payload, dict)
                else None
            )
            record["reported_partial_stage_status"] = partial_status
            if checker_passed and partial_status == "failed":
                _set_first_failure(
                    record,
                    "scientific_partial_stage_failed",
                    "partial receipt is identity-valid but its scientific stage status is failed",
                    checker_code,
                )
        record["required_checker_passed"] = checker_passed
        record["required_checker_kind"] = checker_kind
        record["official_result"] = bool(
            checker_kind == "task40_v10_independent_output_checker" and checker_passed
        )
        record["partial_footer_cannot_promote_to_full_pass"] = (
            checker_kind == "task40_v20_partial_receipt_checker"
            and isinstance(checker_payload, dict)
            and checker_payload.get("official_result") is False
            and checker_payload.get("full_pass") is False
        )
        if record.get("official_result"):
            record["workflow_classification"] = "OFFICIAL_PACKET_RECHECKED"
        elif record.get("required_checker_passed"):
            record["workflow_classification"] = "PARTIAL_RECEIPT_RECHECKED"
        else:
            record["workflow_classification"] = "CHECKER_FAILED_RAW_EVIDENCE_RETAINED"
            _set_first_failure(
                record,
                "required_checker_failed",
                "required checker did not complete with its exact passing receipt",
                checker_code,
            )
    except Exception as exc:  # retain a complete outer receipt for wrapper failures
        record["workflow_error"] = {"type": type(exc).__name__, "message": str(exc)}
        record["workflow_classification"] = "WORKFLOW_OR_CHECKER_FAILED_RAW_EVIDENCE_RETAINED"
        _set_first_failure(record, "workflow_exception", str(exc))
    finally:
        try:
            _append_clock_event(
                events, "user_service_parent_finished", event_log, event_identity
            )
        except Exception as exc:
            record["clock_persistence_error"] = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            _set_first_failure(record, "clock_persistence_failed", str(exc))
        intervals, clock_errors = _intervals(events)
        record["clock_samples"] = events
        record["nonoverlapping_parent_intervals"] = intervals
        record["clock_errors"] = clock_errors
        record["outer_clock_passed"] = bool(
            not clock_errors
            and not record.get("clock_persistence_error")
            and len(intervals) == len(events) - 1
        )
        if not record["outer_clock_passed"]:
            _set_first_failure(
                record,
                "outer_clock_failed",
                "; ".join(clock_errors) or "parent clock event persistence was incomplete",
            )
        record["workflow_complete"] = bool(
            not record.get("first_failure")
            and not record.get("workflow_error")
            and record.get("outer_clock_passed") is True
            and run_case_code == 0
            and checker_code == 0
            and record.get("required_checker_passed") is True
        )
        output_path = evidence_directory / "outer_workflow_record.json"
        _write_json_fsync(output_path, record)
    if record.get("workflow_complete") is True:
        return 0
    if checker_code not in (None, 0):
        return int(checker_code)
    if run_case_code not in (None, 0):
        return int(run_case_code)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare-inputs")
    service_parser = subparsers.add_parser("run-service")
    service_parser.add_argument("--unit", required=True)
    service_parser.add_argument("--runtime-prefix", type=Path, required=True)
    service_parser.add_argument("--abi-receipt", type=Path, required=True)
    service_parser.add_argument("--jit-cache", type=Path, required=True)
    service_parser.add_argument("case_args", nargs=argparse.REMAINDER)
    partial_parser = subparsers.add_parser("check-partial")
    partial_parser.add_argument("--input", type=Path, required=True)
    partial_parser.add_argument("--summary", type=Path, required=True)
    partial_parser.add_argument("--manifest", type=Path, required=True)
    partial_parser.add_argument("--numerical-output", type=Path, required=True)
    partial_parser.add_argument("--stop-stage", required=True)
    partial_parser.add_argument("--output", type=Path, required=True)
    supervisor_parser = subparsers.add_parser(
        "supervise-required-checker", help=argparse.SUPPRESS
    )
    supervisor_parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "supervise-required-checker":
        return _run_required_checker_supervision_request(args.request)
    if args.command == "prepare-inputs":
        print(json.dumps(prepare_stage_inputs(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "check-partial":
        result = _check_partial_result(
            input_path=args.input,
            summary_path=args.summary,
            manifest_path=args.manifest,
            numerical_output=args.numerical_output,
            expected_stop_stage=args.stop_stage,
        )
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["checker_passed"] else 2
    return run_service(
        unit=args.unit,
        runtime_prefix=args.runtime_prefix.resolve(),
        abi_receipt=args.abi_receipt.resolve(),
        jit_cache=args.jit_cache.resolve(),
        case_args=list(args.case_args),
    )


if __name__ == "__main__":
    raise SystemExit(main())
