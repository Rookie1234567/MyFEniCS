"""Run the bounded saved-field diagnostic under Task40's existing host supervisor."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    os.replace(temporary, path)


def _validate_worker_command(command: list[str], contract_path: Path, output_path: Path, contract: dict) -> None:
    repo = Path(__file__).resolve().parents[3]
    expected_worker = (repo / "docs/task40para_phi90_mesh_modes_direct/scripts/d13_saved_field_port_action_only.py").resolve()
    if len(command) != 14 or command[:8] != ["mpiexec", "-n", "1", "numactl", "--interleave=0,1", "taskset", "-c", "24"]:
        raise ValueError("worker command must use MPI1 and the reviewed rank-local NUMA/CPU24 prefix")
    python_index = 8
    worker_index = 9
    if Path(command[python_index]).resolve() != (Path(os.environ["TASK40_SHARED_VENV_ROOT"]) / "bin/python").resolve():
        raise ValueError("worker command interpreter is not the read-only qualified Task40 shared Python")
    if Path(command[worker_index]).resolve() != expected_worker:
        raise ValueError("worker command does not point to the bound action-only worker")
    tail = command[worker_index + 1 :]
    if tail != ["--contract", str(contract_path), "--output", str(output_path)]:
        raise ValueError("worker command arguments differ from the bound contract/output")
    expected_sha = contract.get("worker_script_sha256")
    if expected_sha != _sha256(expected_worker):
        raise ValueError("worker command script SHA differs from the action-only contract")


def run_supervised(command: list[str], *, watchdog_directory: Path,
                   supervision_output_path: Path, contract: dict[str, Any]) -> dict[str, Any]:
    """Acquire the canonical Task40 lock and supervise through existing RSS/host-floor code."""
    from benchmarks.subreaper_watchdog import supervise
    from src.io.native_capacity_profile import (
        TASK40_PHI90_D13_Y2_P6_DIRECT_PROFILE,
        native_profile_facts,
    )
    from src.runners.native_capacity import native_capacity_guard

    resource_facts = native_profile_facts(TASK40_PHI90_D13_Y2_P6_DIRECT_PROFILE)["resources"]
    if resource_facts.get("resource_stop_policy") != "host_available_floor_v1":
        raise ValueError("Task40 diagnostic supervisor requires the existing host-floor policy")
    minimum_available = int(resource_facts["minimum_available_bytes"])
    reviewed = contract["fresh_and_supervision"]["supervision"]
    if reviewed.get("stop_on_global_swap") is not False:
        raise ValueError("action-only supervision must explicitly retain observe-only global swap")
    if reviewed.get("minimum_available_bytes") != minimum_available:
        raise ValueError("contract host-floor differs from the frozen Task40 Y2 profile")
    if reviewed.get("rss_hard_cap_bytes") is not None or reviewed.get("rss_warning_bytes") is not None:
        raise ValueError("host-floor action-only supervision cannot add an RSS cap or warning")
    if reviewed.get("wall_seconds") is not None or reviewed.get("solve_seconds") is not None:
        raise ValueError("action-only supervision does not add a time limit")
    if reviewed.get("pss_sampling_policy") != "disabled_by_profile":
        raise ValueError("action-only host-floor supervision must disable PSS")

    with native_capacity_guard(
        TASK40_PHI90_D13_Y2_P6_DIRECT_PROFILE,
        memory_policy="interleave_nodes0_1",
    ) as (_root, isolation):
        summary = supervise(
            command,
            watchdog_directory,
            wall_seconds=None,
            interval=float(reviewed["sample_interval_seconds"]),
            grace_seconds=float(reviewed["cleanup_grace_seconds"]),
            cache_path=Path(os.environ["XDG_CACHE_HOME"]),
            solve_seconds=None,
            hard_stop_immediate=True,
            timebase_guard=False,
            stop_on_global_swap=False,
            resource_stop_policy="host_available_floor_v1",
            rss_hard_limit_bytes=None,
            rss_warning_bytes=None,
            startup_headroom_bytes=None,
            minimum_available_bytes=minimum_available,
            pss_sampling_policy="disabled_by_profile",
        )
    envelope = summary.get("launch_envelope", {})
    if summary.get("resource_stop_policy") != "host_available_floor_v1" or summary.get("rss_hard_limit_bytes") is not None:
        raise RuntimeError("watchdog returned a resource contract different from Task40 host-floor")
    if summary.get("descendants_cleared") is not True or summary.get("remaining_child_pids"):
        raise RuntimeError("existing Task40 supervisor did not clear the child process tree")
    result = {
        "schema": "task40.d13.saved-field-port-action-only-supervision.v2",
        "classification": summary["classification"],
        "leader_exit_code": summary["leader_exit_code"],
        "descendants_cleared": summary["descendants_cleared"],
        "remaining_child_pids": summary["remaining_child_pids"],
        "resource_stop_policy": summary["resource_stop_policy"],
        "rss_hard_limit_bytes": summary["rss_hard_limit_bytes"],
        "rss_peak_bytes": summary["sampled_process_tree_rss_peak_bytes"],
        "minimum_available_bytes": summary["minimum_available_bytes"],
        "launch_effective_available_bytes": envelope.get("effective_available_bytes"),
        "swap_policy": summary["swap_policy"],
        "job_swap_activity": summary["job_swap_activity"],
        "pss_sampling_policy": summary["pss_sampling_policy"],
        "sample_interval_seconds": reviewed["sample_interval_seconds"],
        "elapsed_seconds": summary["elapsed_seconds"],
        "watchdog_summary_path": str(watchdog_directory / "summary.json"),
        "watchdog_resources_path": str(watchdog_directory / "resources.jsonl"),
        "native_capacity_isolation": isolation,
        "supervisor_contract": "Task40 native_capacity_guard plus benchmarks.subreaper_watchdog.supervise; no RSS cap, timeout, or swap kill",
    }
    _write_json(supervision_output_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--supervision-output", required=True, type=Path)
    parser.add_argument("--watchdog-directory", required=True, type=Path)
    parser.add_argument("--worker-command-json", required=True)
    args = parser.parse_args()
    contract_path = args.contract.resolve()
    output_path = args.output.resolve()
    supervision_output_path = args.supervision_output.resolve()
    contract = json.loads(contract_path.read_text())
    command = json.loads(args.worker_command_json)
    if not isinstance(command, list) or any(not isinstance(token, str) for token in command):
        raise ValueError("worker-command-json must be a JSON string array")
    _validate_worker_command(command, contract_path, output_path, contract)
    result = run_supervised(
        command,
        watchdog_directory=args.watchdog_directory.resolve(),
        supervision_output_path=supervision_output_path,
        contract=contract,
    )
    print(json.dumps(result, sort_keys=True, allow_nan=False), flush=True)
    if result["classification"] == "COMPLETED" and result["leader_exit_code"] == 0:
        return 0
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
