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
from src.io.finite_json import atomic_json
from src.io.w1_evidence import (
    scientific_identity,
    seal_stage,
    validate_stage,
    validate_P1_summary,
    validate_A,
)
from src.runners.fresh_component_receiver import (
    PREFIX,
    bind_own_terminal_core,
    set_own_low_priority,
)
from src.runners.frozen_source_snapshot import materialize

RECEIVER_FILES = [
    "src/io/w1_recovery_commit.py",
    "src/runners/w1_admission_scope.py",
    "src/runners/w1_admission_budget.py",
    "src/runners/feinn_resources.py",
    "src/runners/task042_shared.py",
    "src/runners/durable_terminal.py",
    "src/runners/fresh_component_receiver.py",
    "benchmarks/subreaper_watchdog.py",
    "benchmarks/task034_wsl_resources.py",
    "benchmarks/task038_full3d_jit_staging.py",
    "src/runners/workflow_timebase.py",
    "src/runners/frozen_source_snapshot.py",
    "src/io/task042_profile.py",
    "scripts/launch_task42extra_durable.py",
    "scripts/run_case.py",
    "scripts/activate_task42extra.sh",
    "src/io/w1_reproduced_input.py",
    "src/runners/w1_input_recovery.py",
    "src/io/finite_json.py",
    "src/io/w1_evidence.py",
    "src/solvers/w1_saved_equations.py",
    "src/solvers/w1_local_export_patch.py",
    "src/io/w1_receiver_contract.py",
    "src/runners/w1_component_receiver.py",
    "src/runners/w1_component_payload.py",
    "src/solvers/w1_boundary_components.py",
    "src/solvers/analytic_face_ports.py",
    "src/solvers/interval_facet_moments.py",
    "benchmarks/portable_facet_oracle.py",
]


def charged_seconds(entries, now):
    """Unfinished charges stay conservative; another namespace is not free."""
    return sum(
        row.get("elapsed_seconds", max(0, now - row["origin_monotonic"]))
        for row in entries
    )


def remaining(window, *, now=None, utc_now=None):
    budget = (
        10800
        if window.get("schema")
        in {
            "task42extra.w1-receiver-B-window.v26",
            "task42extra.w1-receiver-RB-window.v26",
            "task42extra.w1-receiver-P0RB-window.v27",
        }
        else 14400
    )
    if (
        window.get("schema")
        not in (
            "task42extra.w1-receiver-window.v1",
            "task42extra.w1-receiver-B-window.v26",
            "task42extra.w1-receiver-RB-window.v26",
            "task42extra.w1-receiver-P0RB-window.v27",
        )
        or window.get("budget_seconds") != budget
        or window.get("numerical_and_checker_budget_seconds") != 7200
        or window.get("delivery_reserve_seconds") != 1800
        or (
            window.get("old_windows_not_reset") is not True
            and window.get("old_v26_window_preserved") is not True
        )
        or (
            window.get("schema") == "task42extra.w1-receiver-P0RB-window.v27"
            and (
                window.get("P0_budget_seconds") != 1800
                or window.get("R_stage_budget_seconds") != 900
                or window.get("admission_samples_limit") != 12
                or window.get("foreground_wait_limit_seconds") != 300
            )
        )
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
    if window["schema"] == "task42extra.w1-receiver-P0RB-window.v27":
        interval = window["deadline_monotonic"] - window["origin_monotonic"]
        utc_interval = (
            datetime.datetime.fromisoformat(window["deadline_utc"])
            - datetime.datetime.fromisoformat(window["T0_utc"])
        ).total_seconds()
        if abs(interval - 10800) > 0.01 or abs(utc_interval - 10800) > 0.01:
            raise ValueError("W1_NEW_WINDOW_EXACT_10800S_BINDING")
    return min(left, utc_left)


def prerequisite(stage, output, spec=None):
    if stage in {"control", "input_recovery"}:
        return
    if spec is None:
        raise ValueError("W1_P1_FULL_SCIENTIFIC_BINDING_REQUIRED")
    original = validate_originals(spec)
    identity = scientific_identity(
        {
            "contract": {
                k: spec[k]
                for k in (
                    "manifest_path",
                    "ledger_path",
                    "math_commit",
                    "quadrature_degree",
                    "output_root",
                    "coordinate_convention",
                    "ledger_translation_nm",
                )
            },
            "original_inputs": original,
            "receiver_files": {p: digest(ROOT / p) for p in RECEIVER_FILES},
            "math_source_sha": MATH_COMMIT,
            "source_manifest_sha256": digest(spec["source_manifest_path"]),
            "window_sha256": digest(spec["window_path"]),
        }
    )

    def previous(name):
        return Path(spec.get("prerequisite_paths", {}).get(name, output / name))

    control = validate_stage(
        previous("control"),
        identity=identity,
        statuses={"CONTROL_NATIVE_BOUNDARY_PASS_NO_VOLUME_FE"},
        expected_stage="control",
    )
    if control.get("native_control_complete") is not True:
        raise ValueError("W1_CONTROL_GATE_REQUIRED")
    if stage.startswith("p"):
        validate_stage(
            previous("boundary"),
            identity=identity,
            statuses={"BOUNDARY_WORKER_PASS_PENDING_CHECKER"},
            expected_stage="boundary",
        )
        p1 = validate_stage(
            previous("boundary_check"),
            identity=identity,
            statuses={"P1_Q60_FULL_MODE_PASS"},
            expected_stage="boundary_check",
        )
        validate_P1_summary(p1)
    if stage.endswith("_check"):
        producer = previous(stage.removesuffix("_check"))
        validate_stage(
            producer,
            identity=identity,
            statuses={
                "BOUNDARY_WORKER_PASS_PENDING_CHECKER",
                "P2_LOCAL_WORKER_COMPLETED_PENDING_CHECKER",
            },
            expected_stage=stage.removesuffix("_check"),
        )
        if spec is not None:
            producer_binding = json.loads((producer / "binding.json").read_text())
            for key in (
                "manifest_path",
                "ledger_path",
                "math_commit",
                "quadrature_degree",
                "coordinate_convention",
                "ledger_translation_nm",
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
    """Preserve errors and setup charges even before the watchdog starts."""
    try:
        return _launch_w1(spec)
    except Exception as error:
        run = Path(spec["output_root"]) / spec["stage"]
        if run.is_dir():
            atomic_json(
                run / "receiver_failure.json",
                {
                    "schema": "w1-receiver-failure.v27",
                    "exception": type(error).__name__,
                    "reason": str(error),
                    "failed_monotonic": time.monotonic(),
                    "native_worker_started": (run / "supervisor_summary.json").exists(),
                    "historical_tree_peak": "NOT_RETAINED_BEFORE_WATCHDOG"
                    if not (run / "supervisor_summary.json").exists()
                    else "SEE_SUMMARY",
                    "final_input_marker_not_authorized_by_failure": True,
                },
            )
        path = Path(spec["window_path"]).parent / (
            "numerical_charges_" + digest(spec["window_path"])[:16] + ".json"
        )
        if path.exists():
            charges = json.loads(path.read_text())
            for row in charges["entries"]:
                if row["output"] == str(run) and "elapsed_seconds" not in row:
                    row.update(
                        elapsed_seconds=time.monotonic() - row["origin_monotonic"],
                        classification="RECEIVER_EXCEPTION",
                        reason=str(error),
                    )
            atomic_json(path, charges)
        raise


def compute_stage_deadline(window, origin, numeric_used, stage, *, now=None):
    now = time.monotonic() if now is None else now
    cap = 900 if stage in {"input_recovery", "control"} else 7200
    deadline = min(
        origin + cap, window["deadline_monotonic"] - 1800, origin + 7200 - numeric_used
    )
    if (
        window["schema"] == "task42extra.w1-receiver-RB-window.v26"
        and stage == "input_recovery"
    ):
        deadline = min(deadline, window["origin_monotonic"] + 1800)
    if deadline - now <= 150:
        raise TimeoutError("W1_STAGE_SHARED_OR_SAVE_BUDGET_INSUFFICIENT")
    return deadline


def _launch_w1(spec):
    from benchmarks.subreaper_watchdog import supervise
    from src.runners.feinn_resources import Health, envelope
    from src.runners.w1_admission_budget import admit, stable

    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise ValueError("W1_REQUIRES_CLEAN_IMPLEMENTATION_COMMIT")
    if "A_qualification_path" not in spec:
        raise ValueError("W1_A_QUALIFICATION_REQUIRED")
    validate_A(
        spec["A_qualification_path"], {p: digest(ROOT / p) for p in RECEIVER_FILES}
    )
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
        if not original["received"] and stage not in {"control", "input_recovery"}:
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
        charge_path = Path(spec["window_path"]).parent / (
            "numerical_charges_" + digest(spec["window_path"])[:16] + ".json"
        )
        charges = (
            json.loads(charge_path.read_text())
            if charge_path.exists()
            else {"window_sha256": digest(spec["window_path"]), "entries": []}
        )
        if charges["window_sha256"] != digest(spec["window_path"]):
            raise ValueError("W1_CHARGE_WINDOW_CHANGED")
        numeric_used = charged_seconds(charges["entries"], time.monotonic())
        if sum(row["stage"] == stage for row in charges["entries"]) >= 3:
            raise ValueError("W1_MAXIMUM_THREE_LIFECYCLES_PER_AFFECTED_CASE")
        charge = {"stage": stage, "output": str(run), "origin_monotonic": origin}
        charges["entries"].append(charge)
        atomic_json(charge_path, charges)
        hard = 2 * 2**30 if stage in {"control", "input_recovery"} else 16 * 2**30
        priority = set_own_low_priority()
        terminal = json.loads(
            (
                ROOT / "tmp/task42extra/durable" / namespace / "terminal_identity.json"
            ).read_text()
        )
        scope = terminal.get("allowed_scope")
        if window["schema"] == "task42extra.w1-receiver-P0RB-window.v27":
            previous = json.loads((durable / "prelaunch_admission.json").read_text())
            if (
                scope is None
                or scope != previous.get("allowed_scope")
                or clock.get("allowed_scope_sha256") != scope["body_sha256"]
            ):
                raise ValueError("W1_INNER_ALLOWED_SCOPE_BINDING")
        # Validate this live server/pane/socket before widening only the search.
        bind_own_terminal_core(terminal, min(os.sched_getaffinity(0)))
        facts = admit(spec, run, hard, inner=True, scope=scope)
        os.sched_setaffinity(0, {facts["cpu"]})
        terminal_policy = bind_own_terminal_core(terminal, facts["cpu"])
        atomic_json(run / "admission.json", facts)
        atomic_json(
            run / "process_policy.json",
            {"launcher": priority, "terminal": terminal_policy},
        )
        stable(spec, run, hard)
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
        stage_deadline = compute_stage_deadline(window, origin, numeric_used, stage)
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
            "window_sha256": digest(spec["window_path"]),
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
            rss_warning_bytes=(
                1879048192 if stage in {"control", "input_recovery"} else 12 * 2**30
            ),
            memory_envelope_provider=lambda: envelope(hard),
            health_check=guarded_health,
            stop_on_global_swap=False,
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
            "worker_started": True,
            "official_results": False,
        }
        if (
            stage == "input_recovery"
            and component.get("status") == "BITWISE_REPRODUCED_INPUT_PENDING_RECEIPT"
            and summary["classification"] == "COMPLETED"
        ):
            from src.io.w1_recovery_commit import commit_recovery

            result = commit_recovery(run, spec, window, result)
        elif path.exists():
            atomic_json(run / "evidence.json", seal_stage(run))
            result["evidence_sha256"] = digest(run / "evidence.json")
        atomic_json(run / "receiver_result.json", result)
        charge["elapsed_seconds"] = time.monotonic() - origin
        charge["classification"] = result["receiver_classification"]
        charge["cleared"] = result["cleared"]
        atomic_json(charge_path, charges)
        return result


def durable_w1(spec, *, launch_origin=None):
    from src.runners.durable_terminal import launch_tmux
    from src.runners.w1_admission_budget import admit
    from src.runners.w1_admission_scope import capture_scope

    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise ValueError("W1_DURABLE_REQUIRES_CLEAN_IMPLEMENTATION_COMMIT")
    original = validate_originals(spec)
    if "A_qualification_path" not in spec:
        raise ValueError("W1_A_QUALIFICATION_REQUIRED")
    if "A_qualification_path" in spec:
        if not original["received"] and spec["stage"] != "input_recovery":
            return {
                "scope": "B_NOT_STARTED_INPUT_UNAVAILABLE",
                "socket": None,
                "session": None,
                "output": None,
            }
        validate_A(
            spec["A_qualification_path"], {p: digest(ROOT / p) for p in RECEIVER_FILES}
        )
        prepare_B_window(spec, original, launch_origin=launch_origin)
    remaining(json.loads(Path(spec["window_path"]).read_text()))
    namespace = "w1-receiver-" + Path(spec["output_root"]).name + "-" + spec["stage"]
    directory = ROOT / "tmp/task42extra/durable" / namespace
    if (directory / "launch.json").exists():
        raise ValueError("W1_ALREADY_LAUNCHED_RECONNECT")
    set_own_low_priority()
    hard = 2 * 2**30 if spec["stage"] in {"control", "input_recovery"} else 16 * 2**30
    directory.mkdir(parents=True, exist_ok=True)
    facts = admit(spec, directory, hard)
    scope = capture_scope(facts)
    facts["allowed_scope"] = scope
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
            "allowed_scope_sha256": scope["body_sha256"],
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
        directory,
        "task42extra-" + namespace,
        command,
        ROOT,
        management_supervised=True,
        allowed_scope=scope,
    )


def stage_cap(window_left, numerical_used, stage):
    return min(
        window_left - 1800,
        7200 - numerical_used,
        900 if stage in {"control", "input_recovery"} else 7200,
    )


def prepare_B_window(spec, original, *, launch_origin=None):
    path = Path(spec["window_path"])
    if path.exists():
        old = json.loads(path.read_text())
        remaining(old)
        if old.get("schema") == "task42extra.w1-receiver-P0RB-window.v27":
            completion = json.loads((path.parent / "P0_complete.json").read_text())
            if (
                completion.get("window_sha256") != digest(path)
                or completion.get("P0_elapsed_seconds", 1801) > 1800
                or completion.get("qualification_sha256")
                != digest(spec["A_qualification_path"])
            ):
                raise ValueError("W1_P0_COMPLETE_TIME_SOURCE_BINDING")
            if spec["stage"] == "input_recovery":
                if original["received"]:
                    raise ValueError("W1_R_ALREADY_GENERATED_DO_NOT_REPEAT")
                return
        if old.get("schema") in {
            "task42extra.w1-receiver-RB-window.v26",
            "task42extra.w1-receiver-P0RB-window.v27",
        }:
            if spec["stage"] == "input_recovery":
                if time.monotonic() >= old["origin_monotonic"] + 1800 - 150:
                    raise TimeoutError("W1_R_WIRING_DEADLINE")
                return
            frozen = json.loads(
                Path(
                    old.get("input_binding_file", path.parent / "P0_R_B_inputs.json")
                ).read_text()
            )
            if (
                frozen.get("window_sha256") != digest(path)
                or frozen.get("original_inputs") != original
                or frozen.get("A_qualification_sha256")
                != digest(spec["A_qualification_path"])
            ):
                raise ValueError("W1_RB_IMMUTABLE_INPUT_BINDING")
            return
        if old.get("original_inputs") != original or old.get(
            "A_qualification_sha256"
        ) != digest(spec["A_qualification_path"]):
            raise ValueError("W1_B_WINDOW_INPUT_OR_QUALIFICATION_CHANGED")
        return
    if not original["received"]:
        raise ValueError("W1_B_REAL_ORIGINALS_REQUIRED")
    now = time.monotonic()
    origin = now if launch_origin is None else launch_origin
    utc = datetime.datetime.now(datetime.timezone.utc)
    window = {
        "schema": "task42extra.w1-receiver-B-window.v26",
        "budget_seconds": 10800,
        "numerical_and_checker_budget_seconds": 7200,
        "delivery_reserve_seconds": 1800,
        "old_windows_not_reset": True,
        "T0_utc": (utc - datetime.timedelta(seconds=now - origin)).isoformat(),
        "deadline_utc": (
            utc + datetime.timedelta(seconds=10800 - (now - origin))
        ).isoformat(),
        "deadline_monotonic": origin + 10800,
        "original_inputs": original,
        "A_qualification_sha256": digest(spec["A_qualification_path"]),
        "external_wait_not_claimed_within_14400s": True,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation; no prior window can be reset by a repeat launch.
    with path.open("x") as out:
        json.dump(window, out, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
