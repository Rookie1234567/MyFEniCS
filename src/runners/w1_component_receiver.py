"""Explicit W1 lifecycle; reuse durable supervision, never W0 numerical work."""

import datetime
import fcntl
import json
import os
from pathlib import Path
import shlex
import subprocess
import time

from src.io.w1_receiver_contract import MATH_COMMIT, ROOT, digest, validate_originals
from src.runners.fresh_component_receiver import (
    PREFIX,
    atomic_json,
    bind_own_terminal_core,
    set_own_low_priority,
)
from src.runners.frozen_source_snapshot import materialize

RECEIVER_FILES = [
    "src/io/w1_receiver_contract.py",
    "src/runners/w1_component_receiver.py",
    "src/runners/w1_component_payload.py",
    "src/solvers/w1_boundary_components.py",
    "src/solvers/analytic_face_ports.py",
    "src/solvers/interval_facet_moments.py",
    "benchmarks/portable_facet_oracle.py",
]
CHARGES = ROOT / "tmp/task42extra/w1_receiver/numerical_charges.json"


def charged_seconds(entries, now):
    """Unfinished charges stay conservative; another namespace is not free."""
    return sum(
        row.get("elapsed_seconds", max(0, now - row["origin_monotonic"]))
        for row in entries
    )


def remaining(window, *, now=None, utc_now=None):
    if (
        window.get("schema") != "task42extra.w1-receiver-window.v1"
        or window.get("budget_seconds") != 14400
        or window.get("numerical_and_checker_budget_seconds") != 7200
        or window.get("delivery_reserve_seconds") != 1800
        or window.get("old_windows_not_reset") is not True
    ):
        raise ValueError("W1_WINDOW_BUDGET_IDENTITY")
    now = time.monotonic() if now is None else now
    utc_now = (
        datetime.datetime.now(datetime.timezone.utc) if utc_now is None else utc_now
    )
    left = window["deadline_monotonic"] - now
    utc_left = (
        datetime.datetime.fromisoformat(window["deadline_utc"]) - utc_now
    ).total_seconds()
    if abs(left - utc_left) > 5:
        raise RuntimeError("TIMEBASE_INCONSISTENCY")
    return min(left, utc_left)


def prerequisite(stage, output, spec=None):
    if stage == "control":
        return
    control = json.loads((output / "control/receiver_result.json").read_text())
    if (
        not control.get("cleared")
        or control.get("component_status")
        != "CONTROL_NATIVE_BOUNDARY_PASS_NO_VOLUME_FE"
    ):
        raise ValueError("W1_CONTROL_GATE_REQUIRED")
    if stage.startswith("p"):
        p1 = json.loads((output / "boundary_check/component_result.json").read_text())
        if p1.get("status") != "P1_Q60_FULL_MODE_PASS" or not p1.get(
            "coverage_complete"
        ):
            raise ValueError("W1_P1_FULL_MODE_GATE_REQUIRED")
    if stage.endswith("_check"):
        producer = output / stage.removesuffix("_check")
        status = json.loads((producer / "receiver_result.json").read_text())
        if not status.get("cleared") or status.get("receiver_exit_code") != 0:
            raise ValueError("W1_FROZEN_CLEARED_PRODUCER_REQUIRED")
        if spec is not None:
            producer_binding = json.loads((producer / "binding.json").read_text())
            for key in (
                "manifest_path",
                "ledger_path",
                "math_commit",
                "quadrature_degree",
                "coordinate_convention",
                "ledger_translation_nm",
                "output_root",
            ):
                if producer_binding["contract"][key] != spec[key]:
                    raise ValueError("W1_PRODUCER_CHECKER_INPUT_MISMATCH:" + key)


def native_command(bundle, run, binding):
    quote = shlex.quote
    receipt = run / "abi_receipt.json"
    command = (
        "set -euo pipefail\n"
        "unset PYTHONPATH PYTHONHOME LD_PRELOAD LD_LIBRARY_PATH PETSC_DIR PETSC_ARCH SLEPC_DIR SLEPC_ARCH\n"
        f"export PATH={quote(PREFIX + '/bin')}:$PATH\n"
        "export UCX_TLS=self OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1\n"
        "export CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1\n"
        f"export TMPDIR={quote(str(run / 'tmp'))} TMP={quote(str(run / 'tmp'))} TEMP={quote(str(run / 'tmp'))}\n"
        f"export XDG_CACHE_HOME={quote(str(run / 'jit'))}\n"
        f"cd {quote(str(bundle))}\n"
        f"python scripts/task40_fresh_c1/qualify_imports_only.py --record {quote(str(receipt))} --runtime-profile native_linux\n"
        f"source scripts/task40_fresh_c1/activate_native_complex.sh {quote(PREFIX)} {quote(str(receipt))} {quote(str(run / 'jit'))}\n"
        f"exec python -B {quote(str(ROOT / 'src/runners/w1_component_payload.py'))} "
        f"--frozen-source {quote(str(bundle))} --binding {quote(str(binding))}"
    )
    return ["/bin/bash", "-c", command]


def launch_w1(spec):
    from benchmarks.subreaper_watchdog import supervise
    from src.runners.feinn_resources import Health, admission, envelope, stable_window

    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise ValueError("W1_REQUIRES_CLEAN_IMPLEMENTATION_COMMIT")
    window = json.loads(Path(spec["window_path"]).read_text())
    if remaining(window) <= 1950:
        raise TimeoutError("W1_DELIVERY_SAVE_RESERVE")
    output = Path(spec["output_root"])
    output.mkdir(parents=True, exist_ok=True)
    stage = spec["stage"]
    namespace = "w1-receiver-" + output.name + "-" + stage
    durable = ROOT / "tmp/task42extra/durable" / namespace
    clock = json.loads((durable / "launch_clock.json").read_text())
    if clock["input_sha256"] != spec["input_sha256"] or clock[
        "window_sha256"
    ] != digest(spec["window_path"]):
        raise ValueError("W1_LAUNCH_CLOCK_INPUT_BINDING")
    origin = clock["origin_monotonic"]
    run = output / stage
    lock_path = ROOT / "tmp/task42extra/numerical.lock"
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if run.exists():
            raise ValueError("W1_STAGE_ALREADY_STARTED_RECONNECT_DO_NOT_REPEAT")
        run.mkdir()
        for folder in ("tmp", "jit"):
            (run / folder).mkdir()
        original = validate_originals(spec)
        if not original["received"] and stage != "control":
            result = {
                "component_status": original["status"],
                "original_inputs": original,
                "receiver_exit_code": 0,
                "cleared": True,
                "worker_started": False,
                "elapsed_seconds": time.monotonic() - origin,
            }
            atomic_json(run / "receiver_result.json", result)
            return result
        prerequisite(stage, output, spec)
        charges = (
            json.loads(CHARGES.read_text())
            if CHARGES.exists()
            else {"window_sha256": digest(spec["window_path"]), "entries": []}
        )
        if charges["window_sha256"] != digest(spec["window_path"]):
            raise ValueError("W1_CHARGE_WINDOW_CHANGED")
        numeric_used = charged_seconds(charges["entries"], time.monotonic())
        if sum(row["stage"] == stage for row in charges["entries"]) >= 3:
            raise ValueError("W1_MAXIMUM_THREE_LIFECYCLES_PER_AFFECTED_CASE")
        charge = {"stage": stage, "output": str(run), "origin_monotonic": origin}
        charges["entries"].append(charge)
        atomic_json(CHARGES, charges)
        hard = 2 * 2**30 if stage == "control" else 16 * 2**30
        priority = set_own_low_priority()
        facts = admission(hard, compensate_self=True)
        os.sched_setaffinity(0, {facts["cpu"]})
        terminal = json.loads(
            (
                ROOT / "tmp/task42extra/durable" / namespace / "terminal_identity.json"
            ).read_text()
        )
        terminal_policy = bind_own_terminal_core(terminal, facts["cpu"])
        atomic_json(run / "admission.json", facts)
        atomic_json(
            run / "process_policy.json",
            {"launcher": priority, "terminal": terminal_policy},
        )
        stable_window(run, hard)
        manifest_path = Path(spec["source_manifest_path"])
        manifest = json.loads(manifest_path.read_text())
        if manifest["commit"] != MATH_COMMIT:
            raise ValueError("W1_FROZEN_DEPENDENCY_COMMIT")
        bundle = (
            ROOT
            / "benchmarks/artifacts/task42extra/w1_receiver"
            / ("source_" + digest(manifest_path)[:16])
        )
        materialize(ROOT, manifest_path, bundle)
        stage_cap = (
            min(remaining(window) - 1800, 7200 - numeric_used)
            if stage != "control"
            else min(900, remaining(window) - 1800)
        )
        # Setup, import and stable admission belong to the same stage clock.
        stage_deadline = origin + stage_cap
        if stage_deadline - time.monotonic() <= 150:
            raise TimeoutError("W1_SETUP_CONSUMED_SAVE_RESERVE")
        source_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        contract = {
            k: spec[k]
            for k in (
                "manifest_path",
                "ledger_path",
                "math_commit",
                "quadrature_degree",
                "output_root",
                "input_sha256",
                "coordinate_convention",
                "ledger_translation_nm",
            )
        }
        binding = {
            "schema": "task42extra.w1-binding.v1",
            "spec": spec,
            "contract": contract,
            "original_inputs": original,
            "receiver_source_sha": source_sha,
            "math_source_sha": MATH_COMMIT,
            "receiver_files": {p: digest(ROOT / p) for p in RECEIVER_FILES},
            "contract_source_manifest_path": str(manifest_path),
            "source_manifest_sha256": digest(manifest_path),
            "window": window,
            "stage": stage,
            "run_path": str(run),
            "stage_deadline_monotonic": stage_deadline,
            "numeric_inherited_seconds": numeric_used,
            "old_main_window_reset": False,
            "new_clone_or_worktree": False,
        }
        atomic_json(run / "binding.json", binding)
        health = Health(run, hard, facts["neighbor_processes"])

        def guarded_health():
            value = dict(health())
            try:
                if (
                    remaining(window) <= 1800
                    or time.monotonic() >= stage_deadline - 150
                ):
                    value["stop_reason"] = "W1_DELIVERY_SAVE_RESERVE"
            except RuntimeError:
                value["stop_reason"] = "TIMEBASE_INCONSISTENCY"
            new_bytes = sum(
                p.stat().st_size
                for p in (ROOT / "benchmarks/artifacts/task42extra/w1_receiver").rglob(
                    "*"
                )
                if p.is_file()
            )
            if new_bytes > 8 * 2**30:
                value["stop_reason"] = "W1_NEW_ARTIFACT_CAP_8GIB"
            return value

        summary = supervise(
            native_command(bundle, run, run / "binding.json"),
            run / "supervision",
            wall_seconds=stage_deadline - time.monotonic(),
            interval=0.25,
            grace_seconds=2,
            worker_environment={
                **os.environ,
                "PHYSICAL_WATCHDOG_PARENT_PID": str(os.getpid()),
            },
            rss_hard_limit_bytes=hard,
            rss_warning_bytes=(1879048192 if stage == "control" else 12 * 2**30),
            memory_envelope_provider=lambda: envelope(hard),
            health_check=guarded_health,
            stop_on_global_swap=True,
            include_pss=False,
            sampled_root_identity=terminal["server"],
        )
        atomic_json(run / "supervisor_summary.json", summary)
        path = run / "component_result.json"
        component = json.loads(path.read_text()) if path.exists() else {}
        result = {
            "schema": "task42extra.w1-receiver-result.v1",
            "receiver_source_sha": source_sha,
            "math_source_sha": MATH_COMMIT,
            "binding_sha256": digest(run / "binding.json"),
            "component_status": component.get("status", "NOT_RETAINED"),
            "receiver_classification": summary["classification"],
            "receiver_exit_code": summary["leader_exit_code"],
            "cleared": summary["descendants_cleared"]
            and not summary["remaining_child_pids"],
            "elapsed_seconds": time.monotonic() - origin,
            "sampled_process_tree_rss_peak_bytes": summary[
                "sampled_process_tree_rss_peak_bytes"
            ],
            "sampled_process_tree_swap_peak_bytes": summary[
                "sampled_process_tree_swap_peak_bytes"
            ],
            "PDE_solved": False,
            "official_results": False,
        }
        atomic_json(run / "receiver_result.json", result)
        charge["elapsed_seconds"] = time.monotonic() - origin
        charge["classification"] = result["receiver_classification"]
        charge["cleared"] = result["cleared"]
        atomic_json(CHARGES, charges)
        return result


def durable_w1(spec, *, launch_origin=None):
    from src.runners.durable_terminal import launch_tmux
    from src.runners.feinn_resources import admission

    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise ValueError("W1_DURABLE_REQUIRES_CLEAN_IMPLEMENTATION_COMMIT")
    remaining(json.loads(Path(spec["window_path"]).read_text()))
    namespace = "w1-receiver-" + Path(spec["output_root"]).name + "-" + spec["stage"]
    directory = ROOT / "tmp/task42extra/durable" / namespace
    if (directory / "launch.json").exists():
        raise ValueError("W1_ALREADY_LAUNCHED_RECONNECT")
    set_own_low_priority()
    hard = 2 * 2**30 if spec["stage"] == "control" else 16 * 2**30
    facts = admission(hard)
    os.sched_setaffinity(0, {facts["cpu"]})
    directory.mkdir(parents=True, exist_ok=True)
    atomic_json(
        directory / "launch_clock.json",
        {
            "origin_monotonic": time.monotonic()
            if launch_origin is None
            else launch_origin,
            "input_sha256": spec["input_sha256"],
            "window_sha256": digest(spec["window_path"]),
        },
    )
    atomic_json(directory / "prelaunch_admission.json", facts)
    command = [
        "/bin/bash",
        "-c",
        "source scripts/activate_task42extra.sh pure && exec python scripts/run_case.py "
        + shlex.quote(spec["path"]),
    ]
    return launch_tmux(
        directory, "task42extra-" + namespace, command, ROOT, management_supervised=True
    )
