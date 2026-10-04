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


def load_receiver(path):
    raw = Path(path).read_bytes()
    if not raw.startswith(b"receiver_schema = "):
        return None
    record = tomllib.loads(raw.decode())
    expected = {"receiver_schema", "component", "mode", "dependency_commit", "input_sha256"}
    if set(record) != expected or record["receiver_schema"] != 1:
        raise ValueError("receiver input schema/fields mismatch")
    if (record["component"] != "fresh_c1_same80_p6"
            or record["dependency_commit"] != DEPENDENCY
            or record["input_sha256"] != INPUT_SHA
            or record["mode"] not in {"control_smoke", "w0"}):
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


def native_command(bundle, run, deadline, control):
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
        "exec python -B -m benchmarks.run_fresh_c1_p6_component --supervised "
        f"--output-dir {quote(str(run))} --abi-receipt {quote(str(receipt))} "
        f"--total-deadline-utc {quote(deadline)}"
        + (" --control-smoke" if control else "")
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
        name = spec["mode"]
        run = ARTIFACTS / name
        if run.exists():
            raise ValueError("receiver stage already started; reconnect, do not restart")
        if name == "w0":
            control = json.loads((ARTIFACTS / "control_smoke/receiver_result.json").read_text())
            if control["component_status"] != "CONTROL_SMOKE_PASS_NO_FE" or not control["cleared"]:
                raise ValueError("full-tree control smoke must pass before real W0")
        run.mkdir(parents=True)
        for folder in ("raw", "logs", "jit", "tmp", "supervision"):
            (run / folder).mkdir()
        origin = time.monotonic()
        facts = admission(HARD)
        os.sched_setaffinity(0, {facts["cpu"]})
        atomic_json(run / "receiver_admission.json", facts)
        stable_window(run, HARD)
        bundle = ARTIFACTS / ("source_" + sha256(MANIFEST)[:16])
        source = materialize(ROOT, MANIFEST, bundle)
        proof = ROOT / "tmp/task42extra/durable" / ("w0-receiver-" + name) / "terminal_identity.json"
        terminal = json.loads(proof.read_text())
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

        command = native_command(bundle, run, window["deadline_utc"], name == "control_smoke")
        summary = supervise(command, run / "receiver_supervision", wall_seconds=remaining(window) - 600,
                            interval=.25, grace_seconds=2, worker_environment=dict(os.environ),
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

    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise ValueError("receiver durable launch requires a clean implementation commit")
    namespace = "w0-receiver-" + spec["mode"]
    command = ["/bin/bash", "-c", "source scripts/activate_task42extra.sh pure && exec python scripts/run_case.py "
               + shlex.quote(str(Path(spec["path"]).relative_to(ROOT)))]
    return launch_tmux(ROOT / "tmp/task42extra/durable" / namespace, "task42extra-" + namespace,
                       command, ROOT, management_supervised=True)
