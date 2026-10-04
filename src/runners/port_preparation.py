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


class PreparationHealth:
    def __init__(self, folder, neighbors, namespace):
        self.shared = SharedHealth(folder, neighbors)
        self.namespace, self.folder = namespace, folder

    def __call__(self):
        row = dict(self.shared())
        if self.namespace == "v37":
            own = [ROOT / "tmp/task042/v37", ROOT / "benchmarks/artifacts/task042/v37"]
            own.extend((ROOT / "results/task042").glob("task042_v37_*"))
            size = inventory_paths(own, ROOT)["bytes"]
            row["new_preparation_bytes"] = size
            if size > 512 * 2**20:
                row["stop_reason"] = "RESOURCE_CONTROLLED_STOP"
        return row


def context(namespace):
    if namespace == "v37":
        from src.solvers import boundary_witness_scope as scope

        return scope.window, scope.ARTIFACT, scope.PLAN, scope.implementation_hashes
    if namespace != "v36":
        raise ValueError("explicit preparation namespace")
    return window, ARTIFACT, PLAN, implementation_hashes


def storage(reserve=0, *, namespace="v36", cleanup=False):
    _, artifact, _, _ = context(namespace)
    own = [ROOT / ("tmp/task042/" + namespace), artifact]
    own.extend((ROOT / "results/task042").glob("task042_" + namespace + "_*"))
    new = inventory_paths(own, ROOT)["bytes"]
    total = inventory_paths([ROOT / "benchmarks/artifacts/task042"], ROOT)["bytes"]
    free = __import__("shutil").disk_usage(ROOT).free
    if (
        (new + reserve > 512 * 2**20 and not cleanup)
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


def require_component_gate(*, namespace="v36"):
    window, _, _, implementation_hashes = context(namespace)
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


def launch(
    specification=None, *, command=None, phase=None, attempt=None, namespace="v36"
):
    if specification is not None:
        namespace = specification.derived.get("preparation_scope", "v36")
    window, ARTIFACT, PLAN, implementation_hashes = context(namespace)
    started = time.monotonic()
    window.require_ready()
    role = phase if specification is None else specification.derived["stage"]
    if role in ("COMPONENT", "PATCH", "CAPACITY"):
        require_component_gate(namespace=namespace)
        if namespace == "v36":
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
    storage(
        32 * 2**20,
        namespace=namespace,
        cleanup=(namespace == "v37" and role == "archive"),
    )
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
            "stage": namespace.upper() + "-" + role,
            "scope": namespace,
            "window": window.snapshot(),
            "implementation_hashes": hashes,
            "shared_workstation": True,
            "environment_mode": os.environ.get("TASK042_ENV_MODE"),
            "cpu": baseline["cpu"],
            "planned_bytes": 6 * 2**30
            if role in ("COMPONENT", "PATCH", "CAPACITY")
            else 2 * 2**30,
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
                namespace,
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
            rss_hard_limit_bytes=(
                8 if role in ("COMPONENT", "PATCH", "CAPACITY") else 2
            )
            * 2**30,
            rss_warning_bytes=(6 if role in ("COMPONENT", "PATCH", "CAPACITY") else 1)
            * 2**30,
            memory_envelope_provider=shared_envelope,
            include_pss=False,
            source_state=state,
            worker_environment={
                "TASK042_WATCHDOG_PARENT_PID": str(os.getpid()),
                "TASK042_V36_AUX_DIRECTORY": str(folder),
                "TASK042_PREPARATION_SCOPE": namespace,
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            health_check=(
                SharedHealth(folder, baseline["neighbor_processes"])
                if role == "archive"
                else PreparationHealth(
                    folder, baseline["neighbor_processes"], namespace
                )
            ),
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
        storage(namespace=namespace)
        return result


def worker(folder, namespace="v36"):
    window, ARTIFACT, _plan, implementation_hashes = context(namespace)
    window.guard_worker_parent()
    state = json.loads((folder / "run_manifest.json").read_text())
    if (
        state["source_sha"]
        != subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        or state["implementation_hashes"] != implementation_hashes()
    ):
        raise RuntimeError("V36 active source changed")
    role = state["stage"].removeprefix(namespace.upper() + "-")
    artifact = ARTIFACT / folder.name
    artifact.mkdir(parents=True, exist_ok=False)
    began = time.monotonic()
    result = {"status": "FAILED", "stage": role, "source_sha": state["source_sha"]}
    try:
        if namespace == "v37":
            from src.solvers.target_boundary_witness import execute
        else:
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
        worker(Path(sys.argv[2]).resolve(), sys.argv[3] if len(sys.argv) > 3 else "v36")
        return 0
    if sys.argv[1] == "--aux":
        result = launch(
            command=sys.argv[4:],
            phase=sys.argv[2],
            attempt=sys.argv[3],
            namespace=os.environ.get("TASK042_PREPARATION_SCOPE", "v36"),
        )
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
