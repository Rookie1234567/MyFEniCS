"""Component-only adapter reusing the established admission and subreaper.

Each phase has a new output directory. Completed immutable phases are consumed
through a hash-bound pointer; a failed phase is not a completed checkpoint.
No V35 cross-launch numerical continuation is claimed.
"""

import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

from benchmarks.subreaper_watchdog import supervise
from src.io.port_preparation import ARTIFACT, PLAN, ROOT, read_stage
from src.runners.diagnostic_storage import inventory_paths
from src.runners.task042_shared import SharedHealth, audit, shared_envelope, write_json
from src.solvers.port_preparation_window import implementation_hashes, window


def storage(reserve=0):
    own = [ROOT / "tmp/task042/v36", ARTIFACT]
    own.extend((ROOT / "results/task042").glob("task042_v36_*"))
    new = inventory_paths(own, ROOT)["bytes"]
    total = inventory_paths([ROOT / "benchmarks/artifacts/task042"], ROOT)["bytes"]
    free = __import__("shutil").disk_usage(ROOT).free
    if (
        new + reserve > 512 * 2**20
        or total + reserve > 20 * 2**30
        or free < 50 * 2**30 + reserve
    ):
        raise MemoryError("V36 new512MiB/task20GiB/free50GiB storage reserve")
    return {
        "new_bytes": new,
        "task_artifact_bytes": total,
        "free_bytes": free,
        "reserve_bytes": reserve,
    }


def require_component_gate():
    q = json.loads((window.TMP / "qualification.json").read_text())
    if q["status"] != "PASSED" or q["implementation_hashes"] != implementation_hashes():
        raise ValueError("V36 final implementation focused qualification missing")
    receipt = Path(q["receipt_path"]).resolve()
    if (
        not receipt.is_relative_to(window.TMP)
        or hashlib.sha256(receipt.read_bytes()).hexdigest() != q["receipt_sha256"]
    ):
        raise ValueError("V36 qualification receipt hash")
    result = json.loads((receipt.parent / "summary.json").read_text())
    if (
        result["classification"] != "COMPLETED"
        or result["leader_exit_code"] != 0
        or not result["descendants_cleared"]
    ):
        raise ValueError("V36 qualification supervision failed")
    return q


def launch(specification=None, *, command=None, phase=None, attempt=None):
    started = time.monotonic()
    window.require_ready()
    role = phase if specification is None else specification.derived["stage"]
    if role == "COMPONENT":
        require_component_gate()
        read_stage("INVENTORY")
    if specification is not None:
        if ARTIFACT.joinpath(role + ".json").exists():
            raise ValueError(
                "V36 completed phase already published; reuse pointer, no restart"
            )
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        )
        if status:
            raise RuntimeError("V36 formal component/preparation requires clean source")
    seconds = window.remaining(role)
    if seconds <= 5:
        raise RuntimeError("V36 phase paid wall exhausted")
    source = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if specification is None:
        folder = window.TMP / ("aux_" + phase + "_" + attempt)
    else:
        from datetime import datetime, timezone

        folder = (
            ROOT
            / "results/task042"
            / (
                specification.identity["run_id"]
                + "_"
                + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            )
        )
    folder.mkdir(parents=True, exist_ok=False)
    storage(32 * 2**20)
    with (ROOT / "tmp/task042/task042_shared.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        baseline = window.admission(
            audit,
            receipt_path=folder / "admission.json",
            observed_activity=True,
            input_path=str(specification.source_path)
            if specification
            else str(command),
        )
        os.sched_setaffinity(0, {baseline["cpu"]})
        os.nice(10)
        subprocess.run(["ionice", "-c", "3", "-p", str(os.getpid())], check=True)
        write_json(folder / "resource_baseline.json", baseline)
        hashes = implementation_hashes()
        state = {
            "source_sha": source,
            "stage": "V36-" + role,
            "window": window.snapshot(),
            "implementation_hashes": hashes,
            "shared_workstation": True,
            "environment_mode": os.environ.get("TASK042_ENV_MODE"),
            "cpu": baseline["cpu"],
            "planned_bytes": 6 * 2**30 if role == "COMPONENT" else 2 * 2**30,
            "new_volume_action_count": 0,
            "new_factor_count": 0,
        }
        if specification is not None:
            write_json(folder / "resolved_config.json", specification.as_jsonable())
            (folder / "input_original.dat").write_bytes(specification.raw_input_bytes)
            state.update(
                input_sha256=specification.input_sha256,
                physical_sha256=specification.physical_model_sha256,
                plan_sha256=hashlib.sha256(PLAN.read_bytes()).hexdigest(),
            )
            (folder / "source_sha.txt").write_text(source + "\n")
            command = [
                sys.executable,
                "-m",
                "src.runners.port_preparation",
                "--worker",
                str(folder),
            ]
        write_json(folder / "run_manifest.json", state)
        window.begin(role, folder, source)
        result = supervise(
            command,
            folder / "supervision",
            wall_seconds=seconds,
            interval=0.5,
            timebase_guard=True,
            hard_stop_immediate=True,
            rss_hard_limit_bytes=(8 if role == "COMPONENT" else 2) * 2**30,
            rss_warning_bytes=(6 if role == "COMPONENT" else 1) * 2**30,
            memory_envelope_provider=shared_envelope,
            include_pss=False,
            source_state=state,
            worker_environment={
                "TASK042_WATCHDOG_PARENT_PID": str(os.getpid()),
                "TASK042_V36_AUX_DIRECTORY": str(folder),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            health_check=SharedHealth(folder, baseline["neighbor_processes"]),
            stop_on_global_swap=False,
        )
        result.update(
            stage=role,
            directory=str(folder),
            launch_wall_seconds=time.monotonic() - started,
            shared_workstation=True,
        )
        write_json(
            folder / ("summary.json" if specification is None else "run_summary.json"),
            result,
        )
        window.settle(result, folder)
        if (
            specification is None
            and result["classification"] == "COMPLETED"
            and result["leader_exit_code"] == 0
            and role == "pre"
        ):
            write_json(
                window.TMP / "qualification.json",
                {
                    "status": "PASSED",
                    "implementation_hashes": implementation_hashes(),
                    "receipt_path": str(folder / "tests.json"),
                    "receipt_sha256": hashlib.sha256(
                        (folder / "tests.json").read_bytes()
                    ).hexdigest(),
                },
            )
        storage()
        return result


def worker(folder):
    window.guard_worker_parent()
    state = json.loads((folder / "run_manifest.json").read_text())
    if (
        state["source_sha"]
        != subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        or state["implementation_hashes"] != implementation_hashes()
    ):
        raise RuntimeError("V36 active source changed")
    role = state["stage"].removeprefix("V36-")
    artifact = ARTIFACT / folder.name
    artifact.mkdir(parents=True, exist_ok=False)
    began = time.monotonic()
    result = {"status": "FAILED", "stage": role, "source_sha": state["source_sha"]}
    try:
        from src.solvers.port_component_study import execute

        os.environ["TASK042_RUN_SOURCE"] = state["source_sha"]
        result = execute(role, artifact, state)
    except BaseException as exc:
        result["error"] = repr(exc)
        traceback.print_exc()
        raise
    finally:
        result.update(
            stage=role,
            source_sha=state["source_sha"],
            elapsed_worker_seconds=time.monotonic() - began,
            input_sha256=state["input_sha256"],
            physical_contract_sha256=state["physical_sha256"],
        )
        write_json(artifact / "result.json", result)
        if result["status"] != "FAILED":
            write_json(
                ARTIFACT / (role + ".json"),
                {
                    "path": str(artifact / "result.json"),
                    "sha256": hashlib.sha256(
                        (artifact / "result.json").read_bytes()
                    ).hexdigest(),
                },
            )


def main():
    if sys.argv[1] == "--worker":
        worker(Path(sys.argv[2]).resolve())
        return 0
    if sys.argv[1] == "--aux":
        result = launch(command=sys.argv[4:], phase=sys.argv[2], attempt=sys.argv[3])
        print(
            json.dumps(
                {
                    "directory": result["directory"],
                    "classification": result["classification"],
                    "seconds": result["elapsed_seconds"],
                    "exit_code": result["leader_exit_code"],
                }
            )
        )
        return (
            0
            if result["classification"] == "COMPLETED"
            and result["leader_exit_code"] == 0
            else 1
        )
    raise ValueError("V36 worker/foreground supervised auxiliary only")


if __name__ == "__main__":
    sys.exit(main())
