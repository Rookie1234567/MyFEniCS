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
        if self.namespace in ("v37", "v38", "v39", "v40", "v41", "v42"):
            own = [
                ROOT / ("tmp/task042/" + self.namespace),
                ROOT / ("benchmarks/artifacts/task042/" + self.namespace),
            ]
            own.extend(
                (ROOT / "results/task042").glob("task042_" + self.namespace + "_*")
            )
            size = inventory_paths(own, ROOT)["bytes"]
            row["new_preparation_bytes"] = size
            limit = (
                40 * 2**30
                if self.namespace == "v42"
                else (2048 if self.namespace in ("v39", "v40", "v41") else 512) * 2**20
            )
            if size > limit:
                row["stop_reason"] = "RESOURCE_CONTROLLED_STOP"
            if self.namespace in ("v39", "v40"):
                jit = ROOT / ("tmp/task042/" + self.namespace + "/formal/xdg/fenics")
                jit_bytes = inventory_paths([jit], ROOT)["bytes"]
                row["new_native_jit_bytes"] = jit_bytes
                if jit_bytes > 1536 * 2**20:
                    row["stop_reason"] = "RESOURCE_CONTROLLED_STOP"
        return row


FE_ROLES = (
    "COMPONENT",
    "PATCH",
    "CAPACITY",
    "BRIDGE",
    "LAYOUT",
    "ORACLE",
    "ADAPTER",
    "COUPLED",
)


def context(namespace):
    if namespace == "v42":
        from src.solvers import distributed_volume_scope as scope

        return scope.window, scope.ARTIFACT, scope.PLAN, scope.implementation_hashes
    if namespace == "v41":
        from src.solvers import native_entity_scope as scope

        return scope.window, scope.ARTIFACT, scope.PLAN, scope.implementation_hashes
    if namespace == "v40":
        from src.solvers import native_recovery_scope as scope

        return scope.window, scope.ARTIFACT, scope.PLAN, scope.implementation_hashes
    if namespace == "v39":
        from src.solvers import native_integration_scope as scope

        return scope.window, scope.ARTIFACT, scope.PLAN, scope.implementation_hashes
    if namespace == "v38":
        from src.solvers import boundary_structure_scope as scope

        return scope.window, scope.ARTIFACT, scope.PLAN, scope.implementation_hashes
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
    limit = (
        40 * 2**30
        if namespace == "v42"
        else (2048 if namespace in ("v39", "v40", "v41") else 512) * 2**20
    )
    task_limit = (64 if namespace == "v42" else 20) * 2**30
    free_limit = (100 if namespace == "v42" else 50) * 2**30
    if (
        (new + reserve > limit and not cleanup)
        or total + reserve > task_limit
        or free < free_limit + reserve
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


def diagnosed_phase_repair(namespace, role, previous, plan):
    if namespace in ("v39", "v40"):
        return previous["status"] in (
            "NATIVE_ADAPTER_NOT_QUALIFIED",
            "COUPLED_INTERFACE_NOT_QUALIFIED",
            "NATIVE_RECOVERY_NOT_QUALIFIED",
        )
    if namespace == "v41" and role == "ROUTING":
        repair = plan.get("diagnosed_routing_replay", {})
        return (
            previous["status"] == "TARGET_BOUNDARY_OWNER_ROUTING_NOT_QUALIFIED"
            and repair.get("failed_source") == previous["source_sha"]
            and repair.get("root_cause") == "frozen_adjoint_wrong_input"
            and repair.get("evidence_path") is not None
            and hashlib.sha256(Path(repair["evidence_path"]).read_bytes()).hexdigest()
            == repair.get("evidence_sha256")
        )
    return False


def launch(
    specification=None, *, command=None, phase=None, attempt=None, namespace="v36"
):
    if specification is not None:
        namespace = specification.derived.get("preparation_scope", "v36")
    window, ARTIFACT, PLAN, implementation_hashes = context(namespace)
    started = time.monotonic()
    window.require_ready()
    role = phase if specification is None else specification.derived["stage"]
    is_fe = role in FE_ROLES or (namespace == "v40" and specification is not None)
    if namespace == "v41":
        from src.solvers.native_entity_scope import NATIVE

        is_fe = role in NATIVE
    if namespace == "v42":
        from src.solvers.distributed_volume_scope import NATIVE

        is_fe = role in NATIVE
    if is_fe or (namespace in ("v41", "v42") and specification is not None):
        require_component_gate(namespace=namespace)
        if namespace == "v36":
            read_stage("INVENTORY")
    if specification is not None:
        if ARTIFACT.joinpath(role + ".json").exists():
            pointer = ARTIFACT.joinpath(role + ".json")
            previous = json.loads(pointer.read_text())
            prior_result = json.loads(
                __import__("pathlib").Path(previous["path"]).read_text()
            )
            if not diagnosed_phase_repair(
                namespace, role, prior_result, json.loads(PLAN.read_text())
            ):
                raise ValueError(
                    "completed qualified phase already published; reuse pointer, no restart"
                )
            # This allows only a diagnosed repair of a nonqualified phase.
            # Its result/arrays/source remain immutable and the superseded
            # pointer is saved beside the new run before publication.
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        )
        if status:
            raise RuntimeError("V36 formal component/preparation requires clean source")
    seconds = window.remaining(role)
    if specification is not None and namespace in ("v41", "v42"):
        seconds = min(seconds, float(specification.execution["timeout_seconds"]))
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
    if (
        specification is not None
        and namespace in ("v39", "v40")
        and ARTIFACT.joinpath(role + ".json").exists()
    ):
        (folder / "superseded_partial_pointer.json").write_bytes(
            ARTIFACT.joinpath(role + ".json").read_bytes()
        )
    storage(
        (1024 if namespace == "v42" else 32) * 2**20,
        namespace=namespace,
        cleanup=(namespace in ("v37", "v40") and role == "archive"),
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
        ranks = (
            int(specification.execution["mpi_size"]) if specification is not None else 1
        )
        cpus = [baseline["cpu"]]
        if namespace in ("v41", "v42"):
            cpus, used = [], set()
            for t in baseline["topology"]:
                key = (t["socket"], t["core"])
                if t["cpu"] in baseline["candidate_cpus"] and key not in used:
                    cpus.append(t["cpu"])
                    used.add(key)
                if len(cpus) == ranks:
                    break
            if len(cpus) != ranks:
                write_json(
                    window.TMP / "resource_wait.json",
                    {
                        "next_probe_monotonic": time.monotonic() + 120,
                        "cause": "insufficient distinct audited physical cores for ranks",
                    },
                )
                raise RuntimeError("V41 per-rank CPU/SMT admission rejected")
        os.sched_setaffinity(0, set(cpus))
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
            "rank_cpus": cpus,
            "MPI_size": ranks,
            "planned_bytes": 6 * 2**30 if is_fe else 2 * 2**30,
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
            if namespace in ("v41", "v42") and ranks > 1:
                command = ["mpiexec", "--bind-to", "none", "-n", str(ranks), *command]
        write_json(folder / "run_manifest.json", state)
        window.begin(role, folder, source)
        result = supervise(
            command,
            folder / "supervision",
            wall_seconds=seconds,
            interval=0.5,
            timebase_guard=True,
            hard_stop_immediate=True,
            rss_hard_limit_bytes=(8 if is_fe else 2) * 2**30,
            rss_warning_bytes=(6 if is_fe else 1) * 2**30,
            memory_envelope_provider=shared_envelope,
            include_pss=False,
            source_state=state,
            worker_environment={
                "TASK042_WATCHDOG_PARENT_PID": str(os.getpid()),
                "TASK042_V36_AUX_DIRECTORY": str(folder),
                "TASK042_PREPARATION_SCOPE": namespace,
                "TASK042_RANK_CPUS": ",".join(map(str, cpus)),
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
    if namespace in ("v41", "v42"):
        from src.solvers.native_entity_scope import guard_entity_worker

        guard_entity_worker(window)
    else:
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
    if namespace in ("v41", "v42"):
        from mpi4py import MPI

        comm = MPI.COMM_WORLD
        if comm.rank == 0:
            artifact.mkdir(parents=True, exist_ok=False)
        comm.barrier()
    else:
        artifact.mkdir(parents=True, exist_ok=False)
    began = time.monotonic()
    result = {"status": "FAILED", "stage": role, "source_sha": state["source_sha"]}
    try:
        if namespace == "v42":
            from src.solvers.distributed_volume_study import execute
        elif namespace == "v41":
            from src.solvers.native_entity_study import execute
        elif namespace == "v40":
            from src.solvers.native_recovery_study import execute
        elif namespace == "v39":
            from src.solvers.native_integration_study import execute
        elif namespace == "v38":
            from src.solvers.boundary_structure_study import execute
        elif namespace == "v37":
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
        result_path = artifact / (
            "result.json"
            if namespace not in ("v41", "v42") or comm.rank == 0
            else f"result_rank{comm.rank}.json"
        )
        write_json(result_path, result)
        if (
            namespace in ("v41", "v42")
            and comm.size > 1
            and result["status"] == "FAILED"
        ):
            # Keep the failed rank's result, then terminate only this MPI job
            # instead of waiting in MPI_Finalize with blocked peers.
            comm.Abort(1)
        if result["status"] != "FAILED" and (
            namespace not in ("v41", "v42") or comm.rank == 0
        ):
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
