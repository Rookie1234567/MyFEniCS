"""Opt-in receiver for the existing fresh-C1 W0 component, without a fork.

The mathematical worker and independent checker are unchanged Git objects.
This receiver owns the local window, activation, source cache, lock and full
terminal/launcher/worker process tree. It does not grant W1/W2 qualification.
"""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
import tomllib

from src.runners.frozen_source_snapshot import materialize, sha256

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "benchmarks/cases/fresh_c1_receiver/dependencies.json"
WINDOW = ROOT / "tmp/task42extra/w0_receiver/window_record.json"
ARTIFACTS = ROOT / "benchmarks/artifacts/task42extra/w0_receiver"
DEPENDENCY = "d4b6ed6b6cb2a0431cb75bba9d8fc74dc9d9e382"
INPUT_SHA = "6654ec211efbc6112f3ccba13ad67ff3a97cdbc471bdd48e39f891819f51a41e"
WORKER_SHA = "324d59624b8cb7837d7dc0251e60cc060b292dccea05002d07710d6c205318bf"
PREFIX = "/home/fenics/.local/share/mamba/task40extra_w0_root/envs/task40extra_w0_5be1210"
HARD = 3 * 2**30


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, indent=2, allow_nan=False, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def set_own_low_priority():
    """Lower only this launcher; its terminal and children inherit it."""
    nice = max(10, os.getpriority(os.PRIO_PROCESS, 0))
    os.setpriority(os.PRIO_PROCESS, 0, nice)
    subprocess.run(["ionice", "-c", "3", "-p", str(os.getpid())], check=True)
    return {"pid": os.getpid(), "nice": os.getpriority(os.PRIO_PROCESS, 0), "io_policy": "idle"}


def bind_own_terminal_core(terminal, cpu, *, proc_root=Path("/proc")):
    """Bind the identity-verified isolated parent, never another project."""
    server, pane = terminal["server"], terminal["pane"]
    if pane["pid"] != os.getpid() or server["pid"] != os.getppid():
        raise ValueError("terminal is not this receiver's pane and parent")
    for identity in (server, pane):
        proc = proc_root / str(identity["pid"])
        fields = (proc / "stat").read_text().rsplit(")", 1)[1].split()
        if int(fields[19]) != identity["start_ticks"] or proc.stat().st_uid != os.getuid():
            raise ValueError("terminal PID/start/owner identity changed")
    arguments = (proc_root / str(server["pid"]) / "cmdline").read_bytes().split(b"\0")
    expected = os.fsencode(terminal["socket"])
    if not any(a == b"-S" and b == expected for a, b in zip(arguments, arguments[1:])):
        raise ValueError("isolated terminal socket identity differs")
    nice = max(10, os.getpriority(os.PRIO_PROCESS, server["pid"]))
    os.setpriority(os.PRIO_PROCESS, server["pid"], nice)
    subprocess.run(["ionice", "-c", "3", "-p", str(server["pid"])], check=True)
    os.sched_setaffinity(server["pid"], {int(cpu)})
    return {"server_pid": server["pid"], "server_start_ticks": server["start_ticks"],
            "server_affinity": sorted(os.sched_getaffinity(server["pid"])),
            "server_nice": os.getpriority(os.PRIO_PROCESS, server["pid"]),
            "pane_pid": pane["pid"], "pane_affinity": sorted(os.sched_getaffinity(0)),
            "neighbor_changes": 0}


def load_receiver(path):
    raw = Path(path).read_bytes()
    if not raw.startswith(b"receiver_schema = "):
        return None
    record = tomllib.loads(raw.decode())
    expected = {"receiver_schema", "component", "mode", "dependency_commit", "input_sha256"}
    if record.get("mode") == "saved_check":
        expected.add("worker_report_sha256")
        if record.get("worker_report_sha256") != WORKER_SHA:
            raise ValueError("saved checker requires the unique frozen completed worker")
        if "repair_attempt" in record:
            expected.add("repair_attempt")
            if record["repair_attempt"] != 2:
                raise ValueError("only the qualified second checker launch is admitted")
    if set(record) != expected or record["receiver_schema"] != 1:
        raise ValueError("receiver input schema/fields mismatch")
    if (record["component"] != "fresh_c1_same80_p6"
            or record["dependency_commit"] != DEPENDENCY
            or record["input_sha256"] != INPUT_SHA
            or record["mode"] not in {"control_smoke", "w0", "saved_check"}):
        raise ValueError("only the frozen W0 component/control input is admitted")
    return {**record, "path": str(Path(path).resolve()),
            "sha256": hashlib.sha256(raw).hexdigest()}


def remaining(window, now=None):
    if (window.get("schema") != "task42extra.w0-receiver-window.v1"
            or window.get("budget_seconds") != 14400
            or window.get("old_main_window_reset") is not False):
        raise ValueError("new receiver window identity is missing")
    now = time.monotonic() if now is None else now
    return float(window["deadline_monotonic"]) - now


def native_command(bundle, run, deadline, control, *, saved_check=False):
    """Activation and execution use one shell; no FE imports in the receiver."""
    receipt = run / "abi_receipt.json"
    quote = shlex.quote
    command = (
        "set -euo pipefail\n"
        "unset PYTHONPATH PYTHONHOME LD_PRELOAD LD_LIBRARY_PATH PETSC_DIR PETSC_ARCH SLEPC_DIR SLEPC_ARCH\n"
        f"export PATH={quote(PREFIX + '/bin')}:$PATH\n"
        "export UCX_TLS=self OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1\n"
        "export CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1\n"
        f"export TMPDIR={quote(str(run / 'tmp'))} TMP={quote(str(run / 'tmp'))} TEMP={quote(str(run / 'tmp'))}\n"
        f"export XDG_CACHE_HOME={quote(str(run / 'jit'))}\n"
        f"cd {quote(str(bundle))}\n"
        f"python scripts/task40_fresh_c1/qualify_imports_only.py --record {quote(str(receipt))} --runtime-profile native_linux\n"
        f"source scripts/task40_fresh_c1/activate_native_complex.sh {quote(PREFIX)} {quote(str(receipt))} {quote(str(run / 'jit'))}\n"
    )
    if saved_check:
        command += (
            f"exec python -B {quote(str(ROOT / 'src/runners/saved_component_checker.py'))} "
            f"--frozen-source {quote(str(bundle))} --producer {quote(str(ARTIFACTS / 'w0'))} "
            f"--output-dir {quote(str(run))} --abi-receipt {quote(str(receipt))} "
            f"--worker-sha256 {WORKER_SHA}"
        )
    else:
        command += (
            "exec python -B -m benchmarks.run_fresh_c1_p6_component --supervised "
            f"--output-dir {quote(str(run))} --abi-receipt {quote(str(receipt))} "
            f"--total-deadline-utc {quote(deadline)}" + (" --control-smoke" if control else "")
        )
    return ["/bin/bash", "-c", command]


def launch_receiver(spec):
    """Complete component and checker serially under the original raw gates."""
    from benchmarks.subreaper_watchdog import supervise
    from src.runners.feinn_resources import Health, admission, envelope, stable_window

    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise ValueError("receiver requires a clean implementation commit")
    window = json.loads(WINDOW.read_text())
    left = remaining(window)
    if left <= 600:
        raise TimeoutError("receiver delivery/save reserve reached")
    manifest = json.loads(MANIFEST.read_text())
    if manifest["commit"] != DEPENDENCY:
        raise ValueError("dependency commit changed")
    if not Path(PREFIX, "bin/python").is_file():
        raise RuntimeError("frozen independent native prefix is unavailable")
    lock_path = ROOT / "tmp/task42extra/numerical.lock"
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        mode = spec["mode"]
        name = mode + ("_repair_02" if spec.get("repair_attempt") == 2 else "")
        run = ARTIFACTS / name
        if run.exists():
            raise ValueError("receiver stage already started; reconnect, do not restart")
        if name == "w0":
            control = json.loads((ARTIFACTS / "control_smoke/receiver_result.json").read_text())
            if control["component_status"] != "CONTROL_SMOKE_PASS_NO_FE" or not control["cleared"]:
                raise ValueError("full-tree control smoke must pass before real W0")
        if mode == "saved_check":
            producer = ARTIFACTS / "w0"
            original = json.loads((producer / "worker_supervisor_summary.json").read_text())
            if (sha256(producer / "worker_report.json") != WORKER_SHA
                    or original.get("classification") != "COMPLETED"
                    or original.get("descendants_cleared") is not True
                    or original.get("remaining_child_pids") != []):
                raise ValueError("only the frozen complete, cleared worker can be checked again")
            if spec.get("repair_attempt") == 2:
                prior = ARTIFACTS / "saved_check"
                failed = ROOT / "tmp/task42extra/durable/w0-receiver-saved_check"
                if (any((prior / "raw").iterdir()) or (prior / "abi_receipt.json").exists()
                        or (prior / "checker_events.jsonl").exists()
                        or "No audited unoccupied physical core" not in (failed / "launcher.log").read_text()):
                    raise ValueError("second checker launch requires the preserved pre-numeric admission failure")
        run.mkdir(parents=True)
        for folder in ("raw", "logs", "jit", "tmp", "supervision"):
            (run / folder).mkdir()
        origin = time.monotonic()
        facts = admission(HARD, compensate_self=True)
        priority = set_own_low_priority()
        os.sched_setaffinity(0, {facts["cpu"]})
        atomic_json(run / "receiver_admission.json", facts)
        proof = ROOT / "tmp/task42extra/durable" / ("w0-receiver-" + name) / "terminal_identity.json"
        terminal = json.loads(proof.read_text())
        policy = bind_own_terminal_core(terminal, facts["cpu"])
        atomic_json(run / "receiver_process_policy.json", {"launcher": priority, "terminal": policy})
        stable_window(run, HARD)
        bundle = ARTIFACTS / ("source_" + sha256(MANIFEST)[:16])
        source = materialize(ROOT, MANIFEST, bundle)
        source_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        binding = {"receiver_source_sha": source_sha, "dependency_source_sha": DEPENDENCY,
                   "dependency_manifest_sha256": sha256(MANIFEST), "dependency_files": len(source["files"]),
                   "input": spec, "window": window, "terminal_identity_sha256": sha256(proof),
                   "numerical_source_rewritten": False, "new_clone_or_worktree": False,
                   "old_main_window_reset": False, "NN_used": False, "official_results": False}
        atomic_json(run / "receiver_binding.json", binding)
        health = Health(run, HARD, facts["neighbor_processes"])
        inherited_health = health

        def guarded_health():
            result = dict(inherited_health())
            if remaining(window) <= 600:
                result["stop_reason"] = "RECEIVER_DELIVERY_SAVE_RESERVE"
            return result

        command = native_command(bundle, run, window["deadline_utc"], name == "control_smoke",
                                 saved_check=mode == "saved_check")
        wall = remaining(window) - 600
        if mode == "saved_check":
            prefix = json.loads((ARTIFACTS / "w0/checker_supervisor_summary.json").read_text())["elapsed_seconds"]
            # Prior bootstrap had no numerical work; charge a conservative bound
            # rather than treating its lost stage timer as free.
            if spec.get("repair_attempt") == 2:
                prefix += 600
            wall = min(wall, 4500 - prefix - (time.monotonic() - origin))
        environment = {**os.environ, "PHYSICAL_WATCHDOG_PARENT_PID": str(os.getpid())}
        summary = supervise(command, run / "receiver_supervision", wall_seconds=wall,
                            interval=.25, grace_seconds=2, worker_environment=environment,
                            rss_hard_limit_bytes=HARD, rss_warning_bytes=HARD - 128 * 2**20,
                            memory_envelope_provider=lambda: envelope(HARD), health_check=guarded_health,
                            stop_on_global_swap=True, include_pss=False,
                            sampled_root_identity=terminal["server"])
        atomic_json(run / "receiver_supervisor_summary.json", summary)
        path = run / "run_summary.json"
        component = json.loads(path.read_text()) if path.is_file() else {}
        result = {"schema": "task42extra.w0-receiver-result.v1", **binding,
                  "component_status": component.get("status", "NOT_RETAINED"),
                  "receiver_classification": summary["classification"],
                  "receiver_exit_code": summary["leader_exit_code"],
                  "cleared": summary["descendants_cleared"] and not summary["remaining_child_pids"],
                  "elapsed_seconds": time.monotonic() - origin,
                  "sampled_process_tree_rss_peak_bytes": summary["sampled_process_tree_rss_peak_bytes"],
                  "sampled_process_tree_swap_peak_bytes": summary["sampled_process_tree_swap_peak_bytes"],
                  "worker_and_checker_walls_included": True, "official_results": False}
        atomic_json(run / "receiver_result.json", result)
        return result


def durable_launch(spec):
    from src.runners.durable_terminal import launch_tmux
    from src.runners.feinn_resources import admission

    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise ValueError("receiver durable launch requires a clean implementation commit")
    namespace = "w0-receiver-" + spec["mode"] + ("_repair_02" if spec.get("repair_attempt") == 2 else "")
    directory = ROOT / "tmp/task42extra/durable" / namespace
    if (directory / "launch.json").exists():
        raise ValueError("receiver already launched; reconnect to the same job")
    set_own_low_priority()
    facts = admission(HARD)
    os.sched_setaffinity(0, {facts["cpu"]})
    directory.mkdir(parents=True, exist_ok=True)
    atomic_json(directory / "prelaunch_admission.json", facts)
    command = ["/bin/bash", "-c", "source scripts/activate_task42extra.sh pure && exec python scripts/run_case.py "
               + shlex.quote(str(Path(spec["path"]).relative_to(ROOT)))]
    return launch_tmux(directory, "task42extra-" + namespace,
                       command, ROOT, management_supervised=True)
