from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.io import load_and_resolve


ROOT = Path(__file__).resolve().parents[2]
INPUT_ROOT = ROOT / "input/task40extra_0p7nm_engineering"
V20_INPUTS = (
    "nonseparable_e2_p6_reference_v20.dat",
    "target_original_ny8_resource_pilot_v20.dat",
)


@pytest.mark.parametrize("filename", V20_INPUTS)
def test_v20_dat_profile_facts_and_checker_inventory_use_registry(filename):
    from src.io.physical_intermediate_profile import profile_facts
    from src.runners.task40_v10_output_checker import _registered_v15_profile_inventory
    from src.solvers.task40_v10_p6_periodic_profile import TASK40_P6_PERIODIC_PROFILES
    from src.solvers.task40_v20_registry import TASK40_V20_CASES_BY_PROFILE

    payload = load_and_resolve(INPUT_ROOT / filename).as_jsonable()
    profile = payload["solver"]["preconditioner"]
    case = TASK40_V20_CASES_BY_PROFILE[profile]
    facts = profile_facts(profile)
    periodic = TASK40_P6_PERIODIC_PROFILES[profile]
    inventory = _registered_v15_profile_inventory(profile)

    assert payload["run_id"] == case.run_id == facts["run_id"]
    assert facts["stage"] == case.solver_stage
    assert facts["input_path"] == case.input_path
    assert facts["gates"]["task40_mesh_id"] == case.mesh_id
    assert payload["execution"]["task40_execution_stop_stage"] == "preflight"
    assert payload["derived"]["physical_intermediate_profile"] == facts
    assert inventory["identity"] == profile
    assert inventory["q_count"] == periodic.q_count
    assert inventory["q_port_counts"] == tuple(periodic.q_port_counts)


@pytest.mark.parametrize("filename", V20_INPUTS)
def test_v20_worker_contract_accepts_exact_registered_case(filename):
    from src.io.physical_intermediate_profile import profile_facts
    from src.runners import task40_v10_worker
    from src.runners.physical_v14_budget import V14_TIME_POLICY_ENFORCE
    from src.solvers.task40_v20_registry import TASK40_V20_CASES_BY_PROFILE

    payload = load_and_resolve(INPUT_ROOT / filename).as_jsonable()
    profile = payload["solver"]["preconditioner"]
    case = TASK40_V20_CASES_BY_PROFILE[profile]
    window_sha = "a" * 64
    runtime = SimpleNamespace(
        stage=case.solver_stage,
        campaign_context={
            "read_only": True,
            "window_path": "fixed-window.json",
            "window_sha256": window_sha,
            "accounting_path": "accounting.json",
        },
        shared_budget={"campaign_window_sha256": window_sha},
        workflow_reserved_seconds=1000.0,
        require_zero_swap=True,
        _ledger_path=None,
        time_policy=V14_TIME_POLICY_ENFORCE,
    )
    contract = task40_v10_worker._candidate_contract(
        payload,
        profile_facts(profile),
        runtime,
        profile_identity=profile,
    )
    assert contract["checks"] and all(contract["checks"].values())
    assert contract["schema"] == "task40extra.review_v20_one_q_p6_reference_worker_contract.v1"

    payload["run_id"] = "unreviewed_v20_run"
    with pytest.raises(ValueError, match="worker contract failed"):
        task40_v10_worker._candidate_contract(
            payload,
            profile_facts(profile),
            runtime,
            profile_identity=profile,
        )


def test_v17_profile_cannot_inherit_v20_one_q_scope():
    from src.io.physical_intermediate_profile import (
        TASK40_V17_P6_B0_PROFILE,
        profile_facts,
    )
    from src.runners import task40_v10_worker
    from src.runners.physical_v14_budget import V14_TIME_POLICY_ENFORCE

    payload = load_and_resolve(INPUT_ROOT / "b0_p6_reference_v17.dat").as_jsonable()
    payload["solver"]["task40_factor_lifecycle_strategy"] = "ONE_Q_REFACTOR_V19"
    facts = profile_facts(TASK40_V17_P6_B0_PROFILE)
    window_sha = "b" * 64
    runtime = SimpleNamespace(
        stage=payload["solver"]["stage"],
        campaign_context={
            "read_only": True,
            "window_path": "fixed-window.json",
            "window_sha256": window_sha,
            "accounting_path": "accounting.json",
        },
        shared_budget={"campaign_window_sha256": window_sha},
        workflow_reserved_seconds=1000.0,
        require_zero_swap=True,
        _ledger_path=None,
        time_policy=V14_TIME_POLICY_ENFORCE,
    )
    with pytest.raises(ValueError, match="does not support"):
        task40_v10_worker._candidate_contract(
            payload,
            facts,
            runtime,
            profile_identity=TASK40_V17_P6_B0_PROFILE,
        )


@pytest.mark.parametrize("filename", V20_INPUTS)
def test_v20_dispatcher_calls_only_the_staged_adapter(filename, monkeypatch, tmp_path):
    from src.runners import task038_full3d_iterative, task40_v20_stage_runner
    from src.solvers.task40_v20_registry import TASK40_V20_CASES_BY_PROFILE

    payload = load_and_resolve(INPUT_ROOT / filename).as_jsonable()
    profile = payload["solver"]["preconditioner"]
    case = TASK40_V20_CASES_BY_PROFILE[profile]
    captured = {}

    def fake_stage(resolved, run_directory, *, source_sha):
        captured.update(
            run_id=resolved["run_id"],
            profile=resolved["solver"]["preconditioner"],
            stage=resolved["execution"]["task40_execution_stop_stage"],
            run_directory=run_directory,
            source_sha=source_sha,
        )
        return {"status": "staged_fixture"}

    monkeypatch.setattr(task40_v20_stage_runner, "run_task40_v20_stage", fake_stage)
    result = task038_full3d_iterative.run_full3d_iterative(
        payload, tmp_path, source_sha="f" * 40
    )
    assert result == {"status": "staged_fixture"}
    assert captured == {
        "run_id": case.run_id,
        "profile": case.profile,
        "stage": "preflight",
        "run_directory": tmp_path,
        "source_sha": "f" * 40,
    }


@pytest.mark.parametrize("stop_stage", ["full", "build_and_symbolic", "one_q_numeric"])
def test_original_target_unapproved_heavy_stages_stop_before_geometry(
    stop_stage, monkeypatch, tmp_path
):
    from src.runners import task40_v20_stage_runner
    from src.solvers.task40_v20_registry import TASK40_V20_CASES_BY_PROFILE

    payload = load_and_resolve(
        INPUT_ROOT / "target_original_ny8_resource_pilot_v20.dat"
    ).as_jsonable()
    profile = payload["solver"]["preconditioner"]
    case = TASK40_V20_CASES_BY_PROFILE[profile]
    payload["execution"]["task40_execution_stop_stage"] = stop_stage
    preflight = {
        "run_id": case.run_id,
        "case_profile": profile,
        "source_sha": "f" * 40,
        "input_sha256": "a" * 64,
        "physical_model_sha256": "b" * 64,
        "resources": {"scope": "fixture"},
    }
    monkeypatch.setattr(
        task40_v20_stage_runner,
        "_preflight",
        lambda *_args, **_kwargs: (preflight, None, None),
    )
    monkeypatch.setattr(
        "src.geometry.task40_v20_geometry.build_v20_geometry_inventory",
        lambda *_args, **_kwargs: pytest.fail("full-field stop must precede geometry work"),
    )

    result = task40_v20_stage_runner.run_task40_v20_stage(
        payload, tmp_path, source_sha="f" * 40
    )

    assert result["status"] == "controlled_stop"
    assert result["summary"]["official_result"] is False
    assert result["summary"]["completed_stages"] == ["preflight"]
    assert result["summary"]["full_field_release_allowed"] is False
    if stop_stage in {"build_and_symbolic", "one_q_numeric"}:
        assert result["summary"]["target_heavy_authorized"] is False


def test_v20_resource_snapshot_labels_current_process_cgroup(monkeypatch):
    from benchmarks import task034_wsl_resources
    from src.runners import task40_v20_stage_runner

    monkeypatch.setattr(
        task034_wsl_resources,
        "cgroup_snapshot",
        lambda _pid: {
            "path": "/init.scope",
            "readable": True,
            "dedicated_job_cgroup": False,
            "memory_current_bytes": 1234,
            "memory_peak_bytes": 5678,
            "memory_limit_bytes": None,
            "swap_current_bytes": 0,
        },
    )
    snapshot = task40_v20_stage_runner._resource_snapshot()
    cgroup = snapshot["current_process_cgroup"]
    assert cgroup["path"] == "/init.scope"
    assert cgroup["dedicated_job_cgroup"] is False
    assert cgroup["memory_current_bytes"] == 1234
    assert "task-specific only when dedicated_job_cgroup is true" in cgroup["sample_scope"]
    assert "not a simultaneous process-tree peak" in snapshot["scope"]



def _copy_current_campaign_snapshot(tmp_path):
    import hashlib
    import json

    from src.runners.task40_v10_campaign import CAMPAIGN_ACCOUNTING_NAME

    source = ROOT / (
        "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/"
        "campaign_window_v19.json"
    )
    accounting = source.parent / CAMPAIGN_ACCOUNTING_NAME
    if not source.is_file() or not accounting.is_file():
        pytest.skip("the active fixed Task40 campaign artifacts are unavailable")
    payload = source.read_bytes()
    window_sha256 = hashlib.sha256(payload).hexdigest()
    window_copy = tmp_path / "campaign_window_fixture.json"
    window_copy.write_bytes(payload)

    with accounting.open("rb") as stream:
        stream.seek(0, 2)
        end = stream.tell()
        block_size = 65536
        while True:
            start = max(0, end - block_size)
            stream.seek(start)
            tail = stream.read()
            lines = [line for line in tail.splitlines() if line]
            if start == 0 or len(lines) >= 2:
                break
            block_size *= 2
    record_line = lines[-1]
    record = json.loads(record_line)
    assert record["campaign_window_sha256"] == window_sha256
    (tmp_path / CAMPAIGN_ACCOUNTING_NAME).write_bytes(record_line + b"\n")
    return window_copy, window_sha256


@pytest.mark.parametrize("filename", V20_INPUTS)
def test_v20_run_case_reaches_real_launcher_before_worker(
    filename, monkeypatch, tmp_path
):
    """Run the public route and real launcher, then stop at the no-FE worker boundary."""

    from scripts import run_case
    from src.runners import task038_launcher
    from src.solvers.task40_v20_registry import TASK40_V20_CASES_BY_PROFILE

    campaign_window, campaign_sha256 = _copy_current_campaign_snapshot(tmp_path)
    real_launcher = task038_launcher.launch_specification
    reached = {}

    class WorkerBoundaryReached(RuntimeError):
        pass

    def contract_probe_launcher(specification, **kwargs):
        return real_launcher(specification, contract_probe=True, **kwargs)

    def stop_before_worker(plan, specification, run_directory, **_kwargs):
        manifest = json.loads((run_directory / "run_manifest.json").read_text())
        reached.update(
            run_id=specification.identity["run_id"],
            profile=specification.solver["preconditioner"],
            stop_stage=specification.execution["task40_execution_stop_stage"],
            contract_probe=plan.contract_probe,
            campaign=manifest.get("task40_v20_campaign"),
            budget=manifest.get("task40_v20_budget_admission"),
        )
        raise WorkerBoundaryReached

    def temporary_run_directory(specification, _timestamp=None):
        path = tmp_path / specification.identity["run_id"]
        path.mkdir()
        return path

    monkeypatch.setattr(task038_launcher, "launch_specification", contract_probe_launcher)
    monkeypatch.setattr(task038_launcher, "_run_worker", stop_before_worker)
    monkeypatch.setattr(task038_launcher, "_timestamp_directory", temporary_run_directory)

    with pytest.raises(WorkerBoundaryReached):
        run_case.main([
            str(INPUT_ROOT / filename),
            "--task40-v10-campaign-window",
            str(campaign_window),
        ])

    case = next(
        case
        for case in TASK40_V20_CASES_BY_PROFILE.values()
        if case.run_id == reached["run_id"]
    )
    assert reached["profile"] == case.profile
    assert reached["stop_stage"] == "preflight"
    assert reached["contract_probe"] is True
    assert reached["campaign"]["window_sha256"] == campaign_sha256
    assert reached["campaign"]["effective_window_scope"] == (
        "shared_V20_fixed_deadline_and_remaining_budget"
    )
    assert reached["budget"]["model_id"] == case.model_id
    assert reached["budget"]["run_id"] == case.run_id
    assert reached["budget"]["profile"] == case.profile
    assert reached["budget"]["solver_stage"] == case.solver_stage
    assert reached["budget"]["execution_stop_stage"] == "preflight"
    assert reached["budget"]["campaign_window_sha256"] == campaign_sha256
    assert reached["budget"]["configured_stage_budget"]["workflow_seconds"] > 0
    assert reached["budget"]["configured_stage_budget"]["solve_seconds"] > 0


@pytest.mark.parametrize(
    ("filename", "stop_stage"),
    [
        ("target_original_ny8_resource_pilot_v20.dat", "local_port_components"),
        ("nonseparable_e2_p6_reference_v20.dat", "full"),
    ],
)
def test_v20_staged_input_selects_requested_stage_through_real_launcher_without_worker(
    filename, stop_stage, monkeypatch, tmp_path
):
    """Exercise the public route and launcher while stopping before any FE worker."""

    from scripts import run_case
    from scripts.task40_v20_service_workflow import render_stage_input
    from src.runners import task038_launcher

    canonical = INPUT_ROOT / filename
    stage_input = tmp_path / "stage_inputs" / stop_stage / canonical.name
    stage_input.parent.mkdir(parents=True)
    stage_input.write_text(
        render_stage_input(canonical.read_text(encoding="utf-8"), stop_stage),
        encoding="utf-8",
    )
    assert stage_input.name == canonical.name
    campaign_window, campaign_sha256 = _copy_current_campaign_snapshot(tmp_path)
    real_launcher = task038_launcher.launch_specification
    reached = {}

    class WorkerBoundaryReached(RuntimeError):
        pass

    def contract_probe_launcher(specification, **kwargs):
        return real_launcher(specification, contract_probe=True, **kwargs)

    def stop_before_worker(plan, specification, run_directory, **_kwargs):
        manifest = json.loads((run_directory / "run_manifest.json").read_text())
        reached.update(
            run_id=specification.identity["run_id"],
            profile=specification.solver["preconditioner"],
            stop_stage=specification.execution["task40_execution_stop_stage"],
            contract_probe=plan.contract_probe,
            campaign=manifest.get("task40_v20_campaign"),
            budget=manifest.get("task40_v20_budget_admission"),
        )
        raise WorkerBoundaryReached

    def temporary_run_directory(specification, _timestamp=None):
        path = tmp_path / "runs" / specification.identity["run_id"]
        path.mkdir(parents=True)
        return path

    monkeypatch.setattr(task038_launcher, "launch_specification", contract_probe_launcher)
    monkeypatch.setattr(task038_launcher, "_run_worker", stop_before_worker)
    monkeypatch.setattr(task038_launcher, "_timestamp_directory", temporary_run_directory)

    with pytest.raises(WorkerBoundaryReached):
        run_case.main(
            [
                str(stage_input),
                "--task40-v10-campaign-window",
                str(campaign_window),
            ]
        )

    assert reached["stop_stage"] == stop_stage
    assert reached["contract_probe"] is True
    assert reached["campaign"]["window_sha256"] == campaign_sha256
    assert reached["budget"]["execution_stop_stage"] == stop_stage
    assert reached["budget"]["campaign_window_sha256"] == campaign_sha256


def test_user_service_wrapper_routes_v20_to_clocked_workflow_without_starting_service(
    tmp_path,
):
    import os
    import subprocess

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "systemd_run_argv.bin"
    fake_systemd_run = fake_bin / "systemd-run"
    fake_systemd_run.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\0' \"$@\" > \"$CAPTURE_SYSTEMD_ARGV\"\n",
        encoding="utf-8",
    )
    fake_systemd_run.chmod(0o755)
    environment = dict(os.environ)
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    environment["CAPTURE_SYSTEMD_ARGV"] = str(capture)
    result = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts/run_case_in_user_service.sh"),
            str(INPUT_ROOT / "target_original_ny8_resource_pilot_v20.dat"),
            "--task40-v10-campaign-window",
            str(ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/campaign_window_v19.json"),
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    argv = capture.read_bytes().decode().split("\0")
    argv_text = " ".join(argv)
    assert "MemoryMax=16G" in argv_text
    assert "MemorySwapMax=0" in argv_text
    assert "runtime_prefix/bin/python -S scripts/task40_v20_service_workflow.py run-service" in argv_text
    assert "--runtime-prefix" in argv_text
    assert "--abi-receipt" in argv_text
    assert "--jit-cache" in argv_text
    assert "target_original_ny8_resource_pilot_v20.dat" in argv_text


def test_v20_service_accepts_only_the_official_checker_pass_marker():
    from scripts.task40_v20_service_workflow import _official_checker_passed

    assert _official_checker_passed(0, {"status": "PASS"}) is True
    assert _official_checker_passed(0, {"passed": True}) is False
    assert _official_checker_passed(0, {"status": "REJECTED"}) is False
    assert _official_checker_passed(1, {"status": "PASS"}) is False


def test_v20_service_reads_campaign_identity_from_v20_run_manifest(tmp_path):
    from scripts.task40_v20_service_workflow import (
        _campaign_accounting_path_from_manifest,
    )

    accounting = tmp_path / "campaign_accounting.jsonl"
    accounting.write_text("{}\n", encoding="utf-8")
    manifest = {
        "task40_v20_campaign": {
            "accounting_path": str(accounting),
            "window_sha256": "a" * 64,
        }
    }

    assert _campaign_accounting_path_from_manifest(manifest, "a" * 64) == accounting


def test_v20_service_rejects_legacy_campaign_field_for_v20_run():
    from scripts.task40_v20_service_workflow import (
        _campaign_accounting_path_from_manifest,
    )

    with pytest.raises(ValueError, match="Task40 V20 campaign accounting identity"):
        _campaign_accounting_path_from_manifest(
            {"task40_v10_campaign": {"accounting_path": "ignored"}}, "a" * 64
        )


def test_v20_service_reads_the_actual_run_case_launcher_result_object():
    import json

    from scripts.task40_v20_service_workflow import _parse_run_case_result

    launcher_result = {
        "run_directory": "/tmp/run",
        "manifest": "/tmp/run/run_manifest.json",
        "summary": "/tmp/run/run_summary.json",
        "result_classification": "worker_exit0",
        "exit_status": 0,
        "resource_authority": {"classification": "COMPLETED"},
    }
    stdout = "launcher notice\n" + json.dumps(
        launcher_result, sort_keys=True, separators=(",", ":")
    ) + "\n"
    assert _parse_run_case_result(stdout) == launcher_result


def test_v20_required_checker_reuses_campaign_subreaper_limits(
    monkeypatch, tmp_path
):
    import json

    from benchmarks import subreaper_watchdog
    from scripts.task40_v20_service_workflow import _supervise_required_checker

    observed = {}
    output = {"status": "PASS"}

    def fake_supervise(command, directory, **kwargs):
        observed.update(command=command, directory=directory, kwargs=kwargs)
        directory.mkdir(parents=True)
        (directory / "worker.log").write_text(json.dumps(output), encoding="utf-8")
        return {
            "classification": "COMPLETED",
            "leader_exit_code": 0,
            "descendants_cleared": True,
        }

    monkeypatch.setattr(subreaper_watchdog, "supervise", fake_supervise)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    event_log = evidence / "clock.jsonl"
    event_log.touch()
    events = []
    return_code, payload, details = _supervise_required_checker(
        command=["python", "-m", "checker"],
        checker_kind="task40_v10_independent_output_checker",
        evidence_directory=evidence,
        runtime_prefix=ROOT / "qualified-python",
        environment={"_MYFENICS_WSL_QUALIFIED_ACTIVATION": "1"},
        repo_root=ROOT,
        campaign_window=ROOT / "fixed-window.json",
        campaign_sha256="a" * 64,
        campaign_accounting=ROOT / "campaign-accounting.jsonl",
        source_state={"branch": "task40extra_0p7nm_engineering", "clean": True},
        profile="task40extra_v20_p6_y_orbit_target_original_ny8_v1",
        events=events,
        event_log=event_log,
        event_identity={"source_sha": "b" * 40},
    )

    assert return_code == 0
    assert payload == output
    assert observed["kwargs"]["wall_seconds"] == 86400.0
    assert observed["kwargs"]["campaign_window_sha256"] == "a" * 64
    assert observed["kwargs"]["require_job_cgroup_zero_swap"] is True
    assert observed["kwargs"]["allow_physical_pressure_tree_cap"] is True
    assert observed["kwargs"]["tree_cap_bytes"] == 16 * 1024**3
    assert observed["kwargs"]["campaign_window_path"] == ROOT / "fixed-window.json"
    assert observed["kwargs"]["campaign_accounting_path"] == ROOT / "campaign-accounting.jsonl"
    assert details["supervision"]["campaign_closeout_reserve_seconds"] == 600
    assert details["supervision"]["process_tree_cleanup_required"] is True
    assert events[-1]["label"] == "required_checker_finished"
    assert event_log.read_text(encoding="utf-8").count("required_checker_finished") == 1


@pytest.mark.parametrize("filename", V20_INPUTS)
def test_v20_run_case_real_launcher_rejects_run_identity_near_miss(
    filename, monkeypatch, tmp_path, capsys
):
    from dataclasses import replace

    from scripts import run_case
    from src.runners import task038_launcher, task40_v10_campaign

    real_launcher = task038_launcher.launch_specification
    called = {}

    def alter_then_call_real_launcher(specification, **kwargs):
        identity = dict(specification.identity)
        identity["run_id"] = str(identity["run_id"]) + "_near_miss"
        altered = replace(specification, identity=identity)
        called["run_id"] = altered.identity["run_id"]
        return real_launcher(altered, contract_probe=True, **kwargs)

    monkeypatch.setattr(
        task038_launcher, "launch_specification", alter_then_call_real_launcher
    )
    monkeypatch.setattr(
        task40_v10_campaign,
        "load_fixed_campaign_window",
        lambda *_args, **_kwargs: pytest.fail(
            "an unregistered V20 identity reached campaign loading"
        ),
    )

    return_code = run_case.main([
        str(INPUT_ROOT / filename),
        "--task40-v10-campaign-window",
        str(tmp_path / "must-not-be-read.json"),
    ])
    captured = capsys.readouterr()
    assert return_code == 2
    assert called["run_id"].endswith("_near_miss")
    assert "Task40 V20 run/profile/model/stage/strategy/stop-stage identity is not registered" in captured.err
