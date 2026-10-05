"""Resume ONLY V28's already admitted consumer, before any numeric worker.

Keeps sample 24, its physical core, original one-run/hash/clock and all costs.
Completes the required PSI window and targeted quota tests, then calls the
original run_case/receiver/watchdog. No extra admission or numeric producer.
"""

import json
import os
from pathlib import Path
import runpy
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.io.finite_json import atomic_json  # noqa: E402
from src.io.w1_evidence import file_receipt, check_file, validate_A  # noqa: E402
from src.io.w1_receiver_contract import load_w1  # noqa: E402
from src.io.w1_versioned_input import digest  # noqa: E402
from src.runners.w1_component_receiver import RECEIVER_FILES, remaining  # noqa: E402


def install_same_stage_admission(module, admission, pressure):
    """Patch the actual locally imported provider, not unused receiver attributes."""
    module.admit = admission
    module.stable = pressure


def main():
    spec = load_w1(sys.argv[1])
    if spec["stage"] != "bundle_consume" or spec["w1_receiver_schema"] != 2:
        raise ValueError("ONLY_V28_PREWORKER_CONSUMER_RECOVERY")
    namespace = "w1-receiver-" + Path(spec["output_root"]).name + "-bundle_consume"
    folder = ROOT / "tmp/task42extra/durable" / namespace
    run = Path(spec["output_root"]) / spec["stage"]
    saved = run.with_name("bundle_consume_setup_failure_1")
    context_path = folder / "preworker_resume_context.json"
    window = json.loads(Path(spec["window_path"]).read_text())
    remaining(window)
    os.environ["TASK42EXTRA_DURABLE_NAMESPACE"] = namespace
    tested = sys.argv[2:] in (["--finish-tested"], ["--continue-tested"])
    if tested:
        context = json.loads(context_path.read_text())
        facts = json.loads(check_file(context["facts"], ROOT).read_text())
        q = Path(spec["output_root"]) / "quota_recovery_qualification"
        validate_A(
            context["qualification_path"], {p: digest(ROOT / p) for p in RECEIVER_FILES}
        )
        pressure = json.loads((q / "pressure_stable_window.json").read_text())
        if pressure.get("passed") is not True or pressure["observed_seconds"] < 60:
            raise ValueError("EXISTING_COMPLETED_PRESSURE_REQUIRED")
        clock = json.loads((folder / "launch_clock.json").read_text())
        ledger = json.loads(
            (Path(spec["window_path"]).parent / "resource_samples.json").read_text()
        )
        if (
            context["input_sha256"] != spec["input_sha256"]
            or clock["input_sha256"] != spec["input_sha256"]
            or context["window_sha256"] != digest(spec["window_path"])
            or clock["window_sha256"] != digest(spec["window_path"])
            or ledger["admission_samples"] != 24
            or ledger["foreground_wait_seconds"] > 900
            or time.monotonic() - clock["origin_monotonic"] >= 3600 - 150
        ):
            raise ValueError("SAME_STAGE_CLOCK_GRANT_OR_WAIT_CHANGED")
        if sys.argv[2:] == ["--finish-tested"]:
            from src.runners.durable_terminal import launch_tmux
            from src.runners.fresh_component_receiver import set_own_low_priority

            failed = json.loads((run / "receiver_failure.json").read_text())
            previous = json.loads((folder / "terminal_identity.json").read_text())
            retained = run.with_name("bundle_consume_setup_failure_2")
            proof = folder / "preworker_finish_context.json"
            if (
                failed["reason"] != "W1_SHARED_RESOURCE_SAMPLES_OR_WAIT_EXHAUSTED"
                or failed["native_worker_started"] is not False
                or (run / "binding.json").exists()
                or (run / "supervisor_summary.json").exists()
                or retained.exists()
                or proof.exists()
                or any(
                    Path("/proc", str(previous[k]["pid"])).exists()
                    for k in ("server", "pane")
                )
                or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)
            ):
                raise ValueError("NOT_THE_SINGLE_TESTED_PREWORKER_IMPORT_FIX")
            run.rename(retained)
            atomic_json(
                proof,
                dict(
                    schema="w1-tested-same-stage-import-finish.v28",
                    prior_context=file_receipt(context_path),
                    prior_context_source_is_historical_git_blob=True,
                    prior_source_commit="a16180c05cf5f5217aa01edc78a33c4c095b1eda",
                    current_source=file_receipt(Path(__file__)),
                    actual_qualification=file_receipt(context["qualification_path"]),
                    completed_pressure=file_receipt(q / "pressure_stable_window.json"),
                    failed=file_receipt(retained / "receiver_failure.json"),
                    original_clock=file_receipt(folder / "launch_clock.json"),
                    current_source_sha=subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], text=True
                    ).strip(),
                    existing_sample_number=24,
                    fresh_admission_or_pressure_claimed=False,
                    numerical_consumer_ever_started=False,
                    preparation_monotonic=time.monotonic(),
                ),
            )
            for name in (
                "launch.json",
                "job.sh",
                "terminal_identity.json",
                "launcher.log",
            ):
                old = folder / name
                if old.exists():
                    old.rename(folder / ("before_import_fix_" + name))
            set_own_low_priority()
            os.sched_setaffinity(0, {facts["cpu"]})
            command = [
                "/bin/bash",
                "-c",
                "source scripts/activate_task42extra.sh pure && exec python -B "
                + shlex.quote(str(Path(__file__).resolve()))
                + " "
                + shlex.quote(spec["path"])
                + " --continue-tested",
            ]
            result = launch_tmux(
                folder,
                "task42extra-" + namespace,
                command,
                ROOT,
                management_supervised=True,
                allowed_scope=previous["allowed_scope"],
            )
            print(
                json.dumps(
                    {k: result[k] for k in ("socket", "session", "output", "scope")}
                )
            )
            return
    if len(sys.argv) == 2:
        from src.runners.durable_terminal import launch_tmux
        from src.runners.fresh_component_receiver import set_own_low_priority

        failed = json.loads((run / "receiver_failure.json").read_text())
        facts = json.loads((run / "admission.json").read_text())
        clock = json.loads((folder / "launch_clock.json").read_text())
        previous = json.loads((folder / "terminal_identity.json").read_text())
        ledger = json.loads(
            (Path(spec["window_path"]).parent / "resource_samples.json").read_text()
        )
        sample = next(e for e in reversed(ledger["events"]) if e["kind"] == "admission")
        if (
            failed["reason"] != "W1_SHARED_RESOURCE_SAMPLES_OR_WAIT_EXHAUSTED"
            or failed["native_worker_started"] is not False
            or (run / "binding.json").exists()
            or (run / "supervisor_summary.json").exists()
            or ledger["admission_samples"] != 24
            or ledger["foreground_wait_seconds"] > 839
            or sample["observation_path"] != str(run / "admission_observation.json")
            or facts["cpu"] not in facts["candidate_cpus"]
            or time.monotonic() - failed["failed_monotonic"] > 900
            or clock["input_sha256"] != spec["input_sha256"]
            or clock["window_sha256"] != digest(spec["window_path"])
        ):
            raise ValueError("NOT_THE_UNUSED_APPROVED_24TH_STAGE_ADMISSION")
        if any(
            Path("/proc", str(previous[k]["pid"])).exists() for k in ("server", "pane")
        ):
            raise ValueError("OLD_TERMINAL_STILL_ACTIVE")
        if saved.exists() or context_path.exists():
            raise ValueError("PREWORKER_RECOVERY_ALREADY_ATTEMPTED")
        if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
            raise ValueError("CLEAN_IMPLEMENTATION_REQUIRED")
        run.rename(saved)  # Preserve the complete failure, never delete or overwrite.
        context = dict(
            schema="w1-unused-admission-resume.v28",
            input_sha256=spec["input_sha256"],
            window_sha256=digest(spec["window_path"]),
            original_clock=file_receipt(folder / "launch_clock.json"),
            facts=file_receipt(saved / "admission.json"),
            failed=file_receipt(saved / "receiver_failure.json"),
            cpu=facts["cpu"],
            physical_core_already_admitted=True,
            fresh_sample_claimed=False,
            sample_number=24,
            no_numeric_worker_previously_started=True,
            source=file_receipt(Path(__file__)),
            preparation_monotonic=time.monotonic(),
            qualification_path=str(
                Path(spec["window_path"]).parent / "P0_qualification_admission_fix.json"
            ),
        )
        atomic_json(context_path, context)
        for name in ("launch.json", "job.sh", "terminal_identity.json", "launcher.log"):
            old = folder / name
            if old.exists():
                old.rename(folder / ("before_quota_fix_" + name))
        set_own_low_priority()
        os.sched_setaffinity(0, {facts["cpu"]})
        command = [
            "/bin/bash",
            "-c",
            "source scripts/activate_task42extra.sh pure && exec python -B "
            + shlex.quote(str(Path(__file__).resolve()))
            + " "
            + shlex.quote(spec["path"])
            + " --continue",
        ]
        result = launch_tmux(
            folder,
            "task42extra-" + namespace,
            command,
            ROOT,
            management_supervised=True,
            allowed_scope=previous["allowed_scope"],
        )
        print(
            json.dumps({k: result[k] for k in ("socket", "session", "output", "scope")})
        )
        return
    if sys.argv[2:] not in (["--continue"], ["--continue-tested"]):
        raise ValueError("UNKNOWN_CONTINUATION")
    from benchmarks.subreaper_watchdog import supervise
    from src.runners.feinn_resources import envelope, Health
    from src.runners.fresh_component_receiver import (
        bind_own_terminal_core,
        set_own_low_priority,
    )
    from src.runners.w1_admission_budget import stable
    from src.runners import w1_admission_budget as quota_provider
    from src.io import w1_receiver_contract as contract

    context = json.loads(context_path.read_text())
    facts = json.loads(check_file(context["facts"], ROOT).read_text())
    terminal = json.loads((folder / "terminal_identity.json").read_text())
    os.sched_setaffinity(0, {facts["cpu"]})
    set_own_low_priority()
    bind_own_terminal_core(terminal, facts["cpu"])
    q = Path(spec["output_root"]) / "quota_recovery_qualification"
    if tested:
        check_file(
            json.loads((folder / "preworker_finish_context.json").read_text())[
                "current_source"
            ],
            ROOT,
        )
        delta = Path(spec["output_root"]) / "import_fix_qualification"
        delta.mkdir()
        check = supervise(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "src/test/test_w1_preworker_resume.py",
                "--junitxml=" + str(delta / "junit.xml"),
            ],
            delta / "supervision",
            wall_seconds=120,
            interval=0.25,
            grace_seconds=2,
            rss_hard_limit_bytes=2 * 2**30,
            rss_warning_bytes=1879048192,
            sampled_root_identity=terminal["server"],
            memory_envelope_provider=lambda: envelope(2 * 2**30),
            health_check=Health(
                delta,
                2 * 2**30,
                facts["neighbor_processes"],
                artifact_root=ROOT / "benchmarks/artifacts/task42extra/w1_receiver/v28",
                artifact_cap_bytes=16 * 2**30,
            ),
            stop_on_global_swap=False,
            timebase_guard=True,
        )
        atomic_json(delta / "summary.json", check)
        if (
            check["classification"] != "COMPLETED"
            or check["leader_exit_code"] != 0
            or not check["descendants_cleared"]
        ):
            raise ValueError("IMPORT_WIRING_REGRESSION_FAILED")
    if not tested:
        q.mkdir()
        pressure = stable(
            spec, q, 2 * 2**30
        )  # The one required new 60s PSI window, charged normally.
    # The finish continues the same prepared stage; no second PSI/test window.
    if not tested:
        summary = supervise(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "src/test/test_w1_versioned_input.py",
                "--junitxml=" + str(q / "junit.xml"),
            ],
            q / "supervision",
            wall_seconds=600,
            interval=0.25,
            grace_seconds=2,
            rss_hard_limit_bytes=2 * 2**30,
            rss_warning_bytes=1879048192,
            sampled_root_identity=terminal["server"],
            memory_envelope_provider=lambda: envelope(2 * 2**30),
            health_check=Health(
                q,
                2 * 2**30,
                facts["neighbor_processes"],
                artifact_root=ROOT / "benchmarks/artifacts/task42extra/w1_receiver/v28",
                artifact_cap_bytes=16 * 2**30,
            ),
            stop_on_global_swap=False,
            timebase_guard=True,
        )
        atomic_json(q / "summary.json", summary)
        if summary["classification"] != "COMPLETED" or summary["leader_exit_code"] != 0:
            raise ValueError("QUOTA_REPAIR_TARGETED_TESTS_FAILED")
        inherited = ROOT / "tmp/task42extra/w1_receiver/v27/P0_qualification.json"
        old = json.loads(inherited.read_text())
        files = {p: digest(ROOT / p) for p in RECEIVER_FILES}
        atomic_json(
            context["qualification_path"],
            dict(
                schema="w1-P0-delta-qualification.v28",
                scope="PURE_LOGIC_DELTA_ONLY",
                receiver_files=files,
                inherited_qualification=file_receipt(inherited),
                changed_receiver_files={
                    p: h for p, h in files.items() if old["receiver_files"].get(p) != h
                },
                junit=file_receipt(q / "junit.xml"),
                supervision=file_receipt(q / "summary.json"),
                test_source_files=[
                    file_receipt(ROOT / "src/test/test_w1_versioned_input.py")
                ],
                source_sha=subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], text=True
                ).strip(),
                scientific_scope="PURE_LOGIC_ONLY_NOT_FE_QUALIFICATION",
            ),
        )
    original_load = contract.load_w1
    used = False

    def effective_load(path):
        value = original_load(path)
        if value and value["input_sha256"] == context["input_sha256"]:
            value["A_qualification_path"] = context["qualification_path"]
            value["preworker_resume_context"] = file_receipt(context_path)
            if tested:
                value["preworker_finish_context"] = file_receipt(
                    folder / "preworker_finish_context.json"
                )
        return value

    def same_admitted_stage(s, directory, hard, *, inner=False, scope=None):
        nonlocal used
        if (
            used
            or not inner
            or hard != 2 * 2**30
            or s["input_sha256"] != context["input_sha256"]
        ):
            raise ValueError("NOT_THE_SAME_ADMITTED_PREWORKER_STAGE")
        used = True
        atomic_json(Path(directory) / "admission_observation.json", facts)
        return facts

    def same_completed_pressure(s, directory, hard):
        if s["input_sha256"] != context["input_sha256"] or hard != 2 * 2**30:
            raise ValueError("NOT_THE_SAME_COMPLETED_PSI_WINDOW")
        atomic_json(
            Path(directory) / "pressure_stable_window.json",
            json.loads((q / "pressure_stable_window.json").read_text()),
        )
        return pressure

    contract.load_w1 = effective_load
    install_same_stage_admission(
        quota_provider, same_admitted_stage, same_completed_pressure
    )
    sys.argv = [str(ROOT / "scripts/run_case.py"), spec["path"]]
    runpy.run_path(str(ROOT / "scripts/run_case.py"), run_name="__main__")


if __name__ == "__main__":
    main()
