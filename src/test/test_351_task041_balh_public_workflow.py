"""Focused public-contract tests for the Task041 side-BAL_H profiles."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks import task041_balh_workflow
from benchmarks.task041_balh_workflow import (
    TASK041_REPRESENTATIVE_RHS_SCOPE,
    TASK041_SCHUR_SPEED_V2_PROFILE,
    TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
    build_task041_balh_candidate_consumer_command,
    build_task041_balh_exact_consumer_command,
    build_task041_balh_mode_prep_command,
    task041_balh_consumer_identity_binding,
    task041_schur_speed_v2_contract,
    validate_balh_producer_packet,
)
from benchmarks.task041_exact_side_workflow import _task041_case_contract
from scripts import run_case
from src.io.execution_plan import (
    TASK041_PUBLIC_SUPERVISOR_ADAPTER,
    build_execution_plan,
    method_adapter_available,
    method_adapter_identity,
)
from src.io.input_loader import InputError
from src.io.input_validation import load_and_resolve, task041_balh_profile_errors
from src.io.resolved_config import resolved_config_sha256
from src.runners import task041_supervisor as supervisor
from src.runners.task041_supervisor import (
    _validate_representative_rhs_result,
    _validate_specification,
    run_task041_public_supervisor,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BALH_INPUTS = sorted(
    (REPOSITORY_ROOT / "input/official/task041/side_balh").glob("*.dat")
)


def _specification(path: Path):
    specification = load_and_resolve(path)
    assert task041_balh_profile_errors(specification.as_jsonable()) == []
    return specification


def test_task041_balh_dat_contracts_and_public_identity():
    assert len(BALH_INPUTS) == 4
    for path in BALH_INPUTS:
        specification = _specification(path)
        model_id = str(specification.identity["model_id"])
        assert method_adapter_identity("hybrid_iterative", model_id) == (
            TASK041_PUBLIC_SUPERVISOR_ADAPTER
        )
        assert method_adapter_available("hybrid_iterative", model_id)
        plan = build_execution_plan(
            specification,
            REPOSITORY_ROOT / "results" / "ignored_test351_plan",
            source_sha="a" * 40,
        )
        assert plan.adapter_identity == TASK041_PUBLIC_SUPERVISOR_ADAPTER
        identity = _validate_specification(specification, REPOSITORY_ROOT)
        assert identity["requested_modes"] in {120, 480}
        assert identity["mpi_size"] == 8
        contract = _task041_case_contract(
            specification.as_jsonable(), 8, phase="consumer"
        )
        assert contract["balh"] is True
        assert contract["shortwave"] is False
        assert contract["limits"]["swap_limit_bytes"] == 0


def test_task041_balh_public_commands_select_one_consumer():
    for path in BALH_INPUTS:
        specification = _specification(path)
        mode_prep = build_task041_balh_mode_prep_command(
            "python",
            specification,
            REPOSITORY_ROOT / "results" / "ignored_test351_mode_prep",
            "a" * 40,
        )
        assert mode_prep.count("--phase") == 1
        assert mode_prep[mode_prep.index("--phase") + 1] == "mode-prep"
        route = str(specification.identity["model_id"]).split("_")[2]
        packet_manifest = REPOSITORY_ROOT / "results" / "producer" / "manifest.json"
        packet_identity = REPOSITORY_ROOT / "results" / "producer" / "identity.json"
        if "exact" in path.name:
            command = build_task041_balh_exact_consumer_command(
                "python",
                specification,
                packet_manifest,
                packet_identity,
                "b" * 64,
                REPOSITORY_ROOT / "results" / "ignored_test351_consumer",
                "c" * 40,
                "a" * 40,
            )
            assert route == "exact"
            assert command[command.index("--phase") + 1] == "consumer"
        else:
            command = build_task041_balh_candidate_consumer_command(
                "python",
                specification,
                packet_manifest,
                packet_identity,
                "b" * 64,
                REPOSITORY_ROOT / "results" / "ignored_test351_consumer",
                "c" * 40,
                "a" * 40,
            )
            assert route == "balh"
            assert command[command.index("--phase") + 1] == "candidate-consumer"
        assert command.count("--phase") == 1
        assert "--phase" in command
        assert not ("consumer" in command and "candidate-consumer" in command)


def test_task041_schur_speed_v2_profile_is_explicit_and_candidate_only(
    tmp_path: Path, monkeypatch
):
    from benchmarks import task041_balh_workflow

    candidate_path = (
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/13p5nm_p6h10_m120_mpi8_balh.dat"
    )
    candidate = _specification(candidate_path)
    candidate_model = str(candidate.identity["model_id"])
    contract = task041_schur_speed_v2_contract(candidate_model)
    assert contract["profile_id"] == TASK041_SCHUR_SPEED_V2_PROFILE
    assert contract["phase_budgets_seconds"] == {
        "shared_S0_S1_S3": 21600.0,
        "S2": 7200.0,
        "S4": 172800.0,
    }
    assert contract["batch_budget_seconds"] == 201600.0
    assert contract["active_consumer_phase"] == "S2"
    assert contract["memory_cap_bytes"] == 9159106560
    assert contract["warning_memory_bytes"] == int(9159106560 * 0.9)
    assert contract["memory_gate_source"] == "simultaneous_process_tree_rss"
    assert contract["producer"] == {
        "mode": "reused",
        "invocation": "not_run",
        "time_stop_enforced": True,
        "qep": "not_run",
    }

    supervision_record = (tmp_path / "launch_manifest.json").resolve()
    captured = {}

    def fake_launch(specification, **kwargs):
        captured["model_id"] = specification.identity["model_id"]
        captured["kwargs"] = kwargs
        return {"result_classification": "worker_exit0"}

    monkeypatch.setattr("src.runners.task038_launcher.launch_specification", fake_launch)
    assert run_case.main(
        [
            str(candidate_path),
            "--producer-packet-root",
            str(tmp_path / "producer"),
            "--task041-performance-profile",
            TASK041_SCHUR_SPEED_V2_PROFILE,
            "--task041-supervision-record",
            str(supervision_record),
        ]
    ) == 0
    assert captured["model_id"] == candidate_model
    assert captured["kwargs"]["performance_profile"] == (
        TASK041_SCHUR_SPEED_V2_PROFILE
    )
    assert captured["kwargs"]["disable_time_stop"] is False
    assert captured["kwargs"]["task041_supervision_record"] == supervision_record

    command = build_task041_balh_candidate_consumer_command(
        "python",
        candidate,
        tmp_path / "manifest.json",
        tmp_path / "identity.json",
        "b" * 64,
        tmp_path / "worker",
        "c" * 40,
        "a" * 40,
        performance_profile=TASK041_SCHUR_SPEED_V2_PROFILE,
    )
    assert "--task041-performance-profile" in command
    worker_args = command[command.index("--worker") :]
    parsed_worker_args = task041_balh_workflow._parser().parse_args(worker_args)
    assert parsed_worker_args.task041_performance_profile == (
        TASK041_SCHUR_SPEED_V2_PROFILE
    )

    exact = _specification(
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/13p5nm_p6h10_m120_mpi8_exact.dat"
    )
    with pytest.raises(ValueError, match="BAL_H candidate"):
        task041_schur_speed_v2_contract(str(exact.identity["model_id"]))
    with pytest.raises(ValueError, match="unsupported Task041 performance profile"):
        build_task041_balh_candidate_consumer_command(
            "python",
            candidate,
            tmp_path / "manifest.json",
            tmp_path / "identity.json",
            "b" * 64,
            tmp_path / "worker",
            "c" * 40,
            "a" * 40,
            performance_profile="not-a-profile",
        )


def test_task041_sequential_component_opt_in_is_bound_and_formal_rejected(
    tmp_path: Path, monkeypatch
):
    candidate_path = (
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/5nm_p6h4_m480_mpi8_balh.dat"
    )
    candidate = _specification(candidate_path)
    candidate_model = str(candidate.identity["model_id"])
    probe_manifest = (
        REPOSITORY_ROOT
        / "docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/records/"
        "task041_representative_rhs_v1.json"
    )
    legacy_descriptor = (
        REPOSITORY_ROOT
        / "results/task041_side_balh_component_audit/"
        "task041_h3b_legacy_native_packet_descriptor.json"
    )
    captured = []

    def fake_launch(specification, **kwargs):
        captured.append((specification, kwargs))
        return {"result_classification": "worker_exit0"}

    monkeypatch.setattr(
        "src.runners.task038_launcher.launch_specification", fake_launch
    )
    opt_in_argv = [
        str(candidate_path),
        "--legacy-native-packet-descriptor",
        str(legacy_descriptor),
        "--task041-performance-profile",
        TASK041_SCHUR_SPEED_V2_PROFILE,
        "--task041-rhs-probe",
        str(probe_manifest),
        "--task041-side-setup-schedule",
        TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
    ]
    assert run_case.main(opt_in_argv) == 0
    assert captured[-1][1]["performance_profile"] == (
        TASK041_SCHUR_SPEED_V2_PROFILE
    )
    assert captured[-1][1]["task041_rhs_probe_manifest"] == probe_manifest
    assert captured[-1][1]["task041_side_setup_schedule"] == (
        TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
    )

    contract = task041_schur_speed_v2_contract(
        candidate_model,
        scope=TASK041_REPRESENTATIVE_RHS_SCOPE,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
    )
    assert contract["scope"] == TASK041_REPRESENTATIVE_RHS_SCOPE
    assert contract["side_setup_schedule"] == (
        TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
    )
    assert contract["budget_group"] == "shared_S0_S1_S3"
    command = build_task041_balh_candidate_consumer_command(
        str(Path(sys.executable)),
        candidate,
        tmp_path / "packet_manifest.json",
        tmp_path / "packet_identity.json",
        "b" * 64,
        tmp_path / "worker",
        "c" * 40,
        "a" * 40,
        performance_profile=TASK041_SCHUR_SPEED_V2_PROFILE,
        task041_rhs_probe_manifest=probe_manifest,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
    )
    worker_args = command[command.index("--worker") :]
    parsed = task041_balh_workflow._parser().parse_args(worker_args)
    assert parsed.task041_performance_profile == TASK041_SCHUR_SPEED_V2_PROFILE
    assert parsed.task041_rhs_probe == str(probe_manifest)
    assert parsed.task041_side_setup_schedule == (
        TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
    )

    captured.clear()
    formal_argv = [
        str(candidate_path),
        "--legacy-native-packet-descriptor",
        str(legacy_descriptor),
        "--task041-performance-profile",
        TASK041_SCHUR_SPEED_V2_PROFILE,
    ]
    assert run_case.main(formal_argv) == 0
    assert captured[-1][1]["task041_side_setup_schedule"] is None
    assert run_case.main(
        [
            *formal_argv,
            "--task041-side-setup-schedule",
            TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        ]
    ) == 2
    assert run_case.main(
        [
            str(candidate_path),
            "--legacy-native-packet-descriptor",
            str(legacy_descriptor),
            "--task041-rhs-probe",
            str(probe_manifest),
            "--task041-side-setup-schedule",
            TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        ]
    ) == 2


def test_task041_balh_module_help_executes_public_worker_entrypoint():
    result = subprocess.run(
        [sys.executable, "-m", "benchmarks.task041_balh_workflow", "--help"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "usage:" in output
    assert "--worker" in output
    assert "--phase" in output


def test_task041_balh_identity_keeps_producer_and_consumer_distinct():
    exact = _specification(
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/13p5nm_p6h10_m120_mpi8_exact.dat"
    )
    candidate = _specification(
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/13p5nm_p6h10_m120_mpi8_balh.dat"
    )
    from benchmarks.task041_balh_workflow import build_task041_balh_packet_identity

    producer_identity = build_task041_balh_packet_identity(
        exact, exact.as_jsonable(), "a" * 40, resolved_config_sha256(exact)
    )
    binding = task041_balh_consumer_identity_binding(
        producer_identity, candidate, "b" * 40
    )
    assert binding["pass"] is True
    assert binding["producer_identity"] == producer_identity
    assert binding["consumer_identity"]["source_sha"] == "b" * 40
    assert binding["consumer_identity"]["input_sha256"] == candidate.input_sha256
    assert binding["consumer_identity"]["resolved_sha256"] == resolved_config_sha256(
        candidate
    )
    assert binding["consumer_identity"]["physical_sha256"] == (
        candidate.physical_model_sha256
    )
    assert binding["producer_identity"]["input_sha256"] != binding[
        "consumer_identity"
    ]["input_sha256"]

    bad_external = copy.deepcopy(producer_identity)
    bad_external["external_keys"]["count"] += 1
    with pytest.raises(ValueError, match="external_keys"):
        task041_balh_consumer_identity_binding(bad_external, candidate, "b" * 40)

    bad_physics = copy.deepcopy(producer_identity)
    bad_physics["physical_contract"]["discretization"]["mesh_target_nm"] = 4.0
    with pytest.raises(ValueError, match="physical_contract"):
        task041_balh_consumer_identity_binding(bad_physics, candidate, "b" * 40)

    bad_mpi = copy.deepcopy(producer_identity)
    bad_mpi["mpi_size"] = 1
    with pytest.raises(ValueError, match="mpi_size"):
        task041_balh_consumer_identity_binding(bad_mpi, candidate, "b" * 40)

    with pytest.raises(ValueError, match="source SHA"):
        task041_balh_consumer_identity_binding(producer_identity, candidate, "bad")


def test_task041_balh_ordinary_hybrid_cannot_opt_into_balh_pc(tmp_path: Path):
    legacy_input = REPOSITORY_ROOT / "input/official/grazing1_phi0_hybrid_iterative_m120_mpi8.dat"
    from src.runners.task038_launcher import launch_specification

    ordinary = load_and_resolve(legacy_input)
    with pytest.raises(InputError, match="producer-packet-root"):
        launch_specification(
            ordinary,
            source_sha="a" * 40,
            producer_packet_root=tmp_path / "not_allowed",
        )
    text = legacy_input.read_text(encoding="utf-8")
    modified = tmp_path / legacy_input.name
    modified.write_text(
        text.replace(
            "hybrid_block_ldu_ilu0_dtn_woodbury",
            "hybrid_block_ldu_balh_side_inverse",
        ),
        encoding="utf-8",
    )
    with pytest.raises(InputError, match=r"solver\.preconditioner"):
        load_and_resolve(modified)


def test_task041_balh_scripts_run_case_reaches_public_launcher(monkeypatch):
    path = REPOSITORY_ROOT / "input/official/task041/side_balh/13p5nm_p6h10_m120_mpi8_exact.dat"
    captured = {}

    def fake_launch(specification, **kwargs):
        captured["model_id"] = specification.identity["model_id"]
        captured["kwargs"] = kwargs
        return {"result_classification": "worker_exit0"}

    monkeypatch.setattr("src.runners.task038_launcher.launch_specification", fake_launch)
    assert run_case.main([str(path)]) == 0
    assert captured["model_id"] == "task041_13p5nm_exact_side_hybrid_iterative_p6h10_m120_mpi8"
    assert captured["kwargs"]["producer_packet_root"] is None


def test_task041_balh_time_stop_override_is_forwarded_only_to_5nm_candidate(
    tmp_path, monkeypatch
):
    captured = {}
    from benchmarks import task041_balh_workflow

    def fake_launch(specification, **kwargs):
        captured["model_id"] = specification.identity["model_id"]
        captured["kwargs"] = kwargs
        return {"result_classification": "worker_exit0"}

    monkeypatch.setattr("src.runners.task038_launcher.launch_specification", fake_launch)
    five_nm_candidate = (
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/5nm_p6h4_m480_mpi8_balh.dat"
    )
    packet_root = tmp_path / "producer"
    assert run_case.main(
        [
            str(five_nm_candidate),
            "--producer-packet-root",
            str(packet_root),
            "--task041-balh-candidate-disable-time-stop",
        ]
    ) == 0
    assert captured["model_id"] == "task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8"
    assert captured["kwargs"]["disable_time_stop"] is True
    assert captured["kwargs"]["producer_packet_root"] == packet_root
    worker_command = build_task041_balh_candidate_consumer_command(
        "python",
        _specification(five_nm_candidate),
        tmp_path / "manifest.json",
        tmp_path / "identity.json",
        "d" * 64,
        tmp_path / "worker",
        "c" * 40,
        "a" * 40,
        disable_time_stop=True,
    )
    assert "--task041-balh-candidate-disable-time-stop" in worker_command
    worker_args = worker_command[worker_command.index("--worker") :]
    parsed_worker_args = task041_balh_workflow._parser().parse_args(worker_args)
    assert parsed_worker_args.task041_balh_candidate_disable_time_stop is True

    shortwave_candidate = next(
        path for path in BALH_INPUTS if "13p5nm" in path.name and "balh" in path.name
    )
    assert run_case.main(
        [
            str(shortwave_candidate),
            "--producer-packet-root",
            str(packet_root),
            "--task041-balh-candidate-disable-time-stop",
        ]
    ) == 2


def test_task041_balh_worker_time_override_keeps_memory_and_swap_gates(monkeypatch):
    from benchmarks import task041_exact_side_workflow as worker

    limits = {"hard_memory_bytes": 1000, "timeout_seconds": 43200}
    monkeypatch.setattr(worker.time, "monotonic", lambda: 43201.0)
    worker._check_resource(
        {"memory_authority_bytes": 100, "job_no_swap": True},
        0.0,
        limits,
        enforce_time_stop=False,
    )
    with pytest.raises(worker.Task041ModePrepError, match="hard RSS"):
        worker._check_resource(
            {"memory_authority_bytes": 1000, "job_no_swap": True},
            0.0,
            limits,
            enforce_time_stop=False,
        )
    with pytest.raises(worker.Task041ModePrepError, match="swap"):
        worker._check_resource(
            {"memory_authority_bytes": 100, "job_no_swap": False},
            0.0,
            limits,
            enforce_time_stop=False,
        )


def test_task041_balh_early_identity_failure_keeps_error_classification(tmp_path):
    specification = _specification(
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/13p5nm_p6h10_m120_mpi8_exact.dat"
    )
    run_root = tmp_path / "early_identity_failure"
    run_root.mkdir()
    result = run_task041_public_supervisor(
        specification,
        source_sha="bad",
        run_directory=run_root,
        compute_wall_ledger_path=tmp_path / "unused_ledger.json",
    )
    assert result["result_classification"] == "task041_identity_failure"
    assert result["error"]["type"] == "Task041SupervisorError"
    assert "UnboundLocalError" not in result["error"]["message"]


def test_task041_balh_public_fresh_phases_share_cumulative_budget(
    tmp_path: Path, monkeypatch
):
    candidate = _specification(
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/13p5nm_p6h10_m120_mpi8_balh.dat"
    )
    from benchmarks import task041_balh_workflow
    from src.runners import task041_supervisor as supervisor

    ledger_path = tmp_path / "compute_wall_ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "schema": "task041.compute_wall_ledger.v1",
                "limit_seconds": 172800.0,
                "used_compute_wall_seconds": 10.0,
                "used_status": "measured",
                "basis": "test-local BALH fresh-phase ledger",
                "measured": {"status": "measured", "seconds": 10.0, "records": []},
                "derived": {"status": "not_measured", "seconds": None},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    phase_calls = []
    popen_calls = []
    real_run_phase = supervisor._run_phase

    class FakeProcess:
        next_pid = 532000

        def __init__(self):
            self.pid = FakeProcess.next_pid
            FakeProcess.next_pid += 1
            self.poll_count = 0

        def poll(self):
            self.poll_count += 1
            return None if self.poll_count == 1 else 0

        def wait(self):
            return 0

    def fake_popen(argv, **kwargs):
        del kwargs
        popen_calls.append(list(argv))
        return FakeProcess()

    def fake_sample(_pid):
        return {
            "memory_authority_bytes": 100,
            "job_no_swap": True,
            "host_memory": {"mem_available_bytes": 2**40},
            "process_tree": {
                "rss_bytes": 100,
                "swap_bytes": 0,
                "all_status_readable": True,
                "smaps": {"pss_bytes": 80, "uss_bytes": 60},
            },
            "job_cgroup": {
                "dedicated_job_cgroup": False,
                "swap_current_bytes": 0,
                "ancestor_hard_limit_state": "max_or_unlimited",
                "ancestor_memory": [
                    {"memory_limit_state": "max_or_unlimited"}
                ],
            },
        }

    def fake_run_phase(phase, argv, phase_root, **kwargs):
        phase_calls.append(
            {
                "phase": phase,
                "cumulative_compute_used_seconds": kwargs[
                    "cumulative_compute_used_seconds"
                ],
            }
        )
        return real_run_phase(
            phase,
            argv,
            phase_root,
            **kwargs,
        )

    identity = candidate.as_jsonable()

    def fake_validate(producer_root, specification, source_sha):
        del specification
        manifest = producer_root / "selected_mode_packet" / "manifest.json"
        return {
            "summary": {"environment": {}},
            "identity": identity,
            "identity_path": str(producer_root / "packet_identity.json"),
            "manifest": str(manifest),
            "manifest_sha256": "c" * 64,
            "compact_manifest": {
                "path": str(manifest),
                "sha256": "c" * 64,
                "identity": identity,
            },
            "producer_source_sha": source_sha,
        }

    monkeypatch.setattr(supervisor, "_run_phase", fake_run_phase)
    monkeypatch.setattr(
        supervisor,
        "_outer_mpi_launch_identity",
        lambda: {
            "mpi_size": 1,
            "mpi_rank": 0,
            "markers": {"OMPI_COMM_WORLD_SIZE": "1", "OMPI_COMM_WORLD_RANK": "0"},
        },
    )
    monkeypatch.setattr(
        supervisor,
        "_git_identity",
        lambda repository_root, source_sha: {
            "head": source_sha,
            "branch": supervisor.TASK041_BRANCH,
            "source_sha": source_sha,
            "worktree_clean": True,
        },
    )
    monkeypatch.setattr(
        supervisor,
        "_environment_snapshot",
        lambda repository_root: {"native_marker": "1", "platform": "test"},
    )
    monkeypatch.setattr(
        supervisor,
        "_child_environment",
        lambda: {name: "1" for name in supervisor.TASK041_REQUIRED_THREADS},
    )
    monkeypatch.setattr(
        supervisor,
        "_task041_builders",
        lambda: {
            "balh_mode_prep": lambda *_args: ["mode-prep"],
            "balh_candidate_consumer": lambda *_args, **_kwargs: [
                "candidate-consumer"
            ],
        },
    )
    monkeypatch.setattr(task041_balh_workflow, "validate_balh_producer_packet", fake_validate)
    observed_schedules = []

    def fake_consumer_result(
        consumer_root, process_group_gone, expected_side_setup_schedule=None
    ):
        observed_schedules.append(expected_side_setup_schedule)
        assert expected_side_setup_schedule is None
        return {
            "complete": True,
            "classification": "worker_exit0",
            "worker_classification": "TASK041_CONSUMER_PASS",
            "process_group_gone": process_group_gone,
            "factor_inventory": {},
        }

    monkeypatch.setattr(
        supervisor,
        "_consumer_result",
        fake_consumer_result,
    )

    source_sha = "e" * 40
    fresh_run = tmp_path / "fresh_public_run"
    fresh_run.mkdir()
    result = supervisor.run_task041_public_supervisor(
        candidate,
        source_sha=source_sha,
        run_directory=fresh_run,
        compute_wall_ledger_path=ledger_path,
        python_executable="python",
        popen_factory=fake_popen,
        sample_factory=fake_sample,
        process_group_gone=lambda _pid: True,
        sleep=lambda _seconds: None,
    )
    assert result["result_classification"] == "worker_exit0"
    assert len(popen_calls) == 2
    assert observed_schedules == [None]
    producer_seconds = result["phase_results"]["producer"]["phase_wall_seconds"]
    assert phase_calls[0]["cumulative_compute_used_seconds"] == pytest.approx(10.0)
    assert phase_calls[1]["cumulative_compute_used_seconds"] == pytest.approx(
        10.0 + producer_seconds
    )
    budget = result["compute_wall_budget"]
    assert budget["used_before_seconds"] == pytest.approx(10.0)
    assert budget["used_after_seconds"] == pytest.approx(
        10.0 + result["compute_wall_seconds"]
    )
    assert result["phase_results"]["producer"].get("reused") is not True


def test_task041_balh_reused_public_producer_starts_only_one_consumer(
    tmp_path: Path, monkeypatch
):
    exact = _specification(
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/13p5nm_p6h10_m120_mpi8_exact.dat"
    )
    candidate = _specification(
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/13p5nm_p6h10_m120_mpi8_balh.dat"
    )
    from benchmarks.task041_balh_workflow import build_task041_balh_packet_identity
    from src.runners import task041_supervisor as supervisor

    producer_source_sha = "a" * 40
    consumer_source_sha = "b" * 40
    producer_identity = build_task041_balh_packet_identity(
        exact, exact.as_jsonable(), producer_source_sha, resolved_config_sha256(exact)
    )
    old_run = tmp_path / "producer_public_run"
    producer_root = old_run / "producer"
    packet_root = producer_root / "selected_mode_packet"
    packet_root.mkdir(parents=True)
    manifest_path = packet_root / "manifest.json"
    manifest_path.write_text("{\"manifest\":true}\n", encoding="utf-8")
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    (producer_root / "packet_identity.json").write_text(
        json.dumps(producer_identity, sort_keys=True) + "\n", encoding="utf-8"
    )
    (producer_root / "mode_prep_summary.json").write_text(
        json.dumps(
            {
                "classification": "TASK041_MODE_PREP_PACKET_READY",
                "source_sha": producer_source_sha,
                "cleanup": {"producer_scope_released": True},
                "packet": {"manifest_sha256": manifest_sha},
                "environment": {"platform": "test"},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    producer_phase = {
        "returncode": 0,
        "process_group_gone": True,
        "termination_reason": None,
        "rss_drop": {"pass": True, "before_process_tree_rss_bytes": 123},
        "sample_count": 2,
        "limits": {"timeout_seconds": 10},
        "timeout_scope": "phase",
        "phase_wall_seconds": 2.0,
        "workflow_wall_seconds": 2.0,
        "peak_memory_authority_bytes": 300,
        "peak_process_tree_rss_bytes": 290,
        "peak_process_tree_swap_bytes": 0,
        "peak_dedicated_cgroup_swap_bytes": 0,
        "peak_swap_bytes": 0,
    }
    supervisor_identity = {
        "model_id": producer_identity["model_id"],
        "run_id": producer_identity["run_id"],
        "input_sha256": producer_identity["input_sha256"],
        "resolved_config_sha256": producer_identity["resolved_sha256"],
        "physical_model_sha256": producer_identity["physical_sha256"],
        "requested_modes": producer_identity["mode_count"],
        "mpi_size": producer_identity["mpi_size"],
    }
    (old_run / "supervisor_summary.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "result_classification": "task041_consumer_stage_failure",
                "source_sha": producer_source_sha,
                "identity": supervisor_identity,
                "phase_results": {"producer": producer_phase},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (old_run / "selected_mode_manifest.json").write_text(
        json.dumps(
            {
                "path": str(manifest_path.resolve()),
                "sha256": manifest_sha,
                "identity": producer_identity,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    packet = validate_balh_producer_packet(
        producer_root,
        candidate,
        consumer_source_sha,
        require_public_supervisor_summary=True,
    )
    assert packet["producer_resource_qualified"] is True
    assert Path(packet["compact_manifest"]["path"]).is_absolute()
    assert Path(packet["producer_supervisor_summary"]).resolve() == (
        old_run / "supervisor_summary.json"
    ).resolve()

    popen_calls: list[list[str]] = []

    class FakeProcess:
        pid = 531351

        def __init__(self):
            self._poll_count = 0

        def poll(self):
            self._poll_count += 1
            return None if self._poll_count == 1 else 0

        def wait(self):
            return 0

    def fake_popen(argv, **kwargs):
        del kwargs
        popen_calls.append(list(argv))
        return FakeProcess()

    def fake_sample(_pid):
        return {
            "memory_authority_bytes": 200,
            "job_no_swap": True,
            "host_memory": {"mem_available_bytes": 2**40},
            "process_tree": {
                "all_status_readable": True,
                "rss_bytes": 190,
                "swap_bytes": 0,
                "smaps": {"pss_bytes": 170, "uss_bytes": 160},
            },
            "job_cgroup": {
                "dedicated_job_cgroup": True,
                "readable": True,
                "memory_current_bytes": 200,
                "swap_current_bytes": 0,
                "ancestor_hard_limit_state": "max_or_unlimited",
                "ancestor_memory_headroom_bytes": None,
                "ancestor_memory": [
                    {
                        "memory_limit_state": "max_or_unlimited",
                        "memory_current_bytes": 200,
                        "memory_headroom_bytes": None,
                    }
                ],
            },
        }

    monkeypatch.setattr(
        supervisor,
        "_outer_mpi_launch_identity",
        lambda: {
            "mpi_size": 1,
            "mpi_rank": 0,
            "markers": {"OMPI_COMM_WORLD_SIZE": "1", "OMPI_COMM_WORLD_RANK": "0"},
        },
    )
    monkeypatch.setattr(
        supervisor,
        "_git_identity",
        lambda repository_root, source_sha: {
            "head": source_sha,
            "branch": supervisor.TASK041_BRANCH,
            "source_sha": source_sha,
            "worktree_clean": True,
        },
    )
    monkeypatch.setattr(
        supervisor,
        "_environment_snapshot",
        lambda repository_root: {"native_marker": "1", "platform": "test"},
    )
    monkeypatch.setattr(
        supervisor,
        "_child_environment",
        lambda: {name: "1" for name in supervisor.TASK041_REQUIRED_THREADS},
    )
    observed_schedules = []

    def fake_consumer_result(
        consumer_root, process_group_gone, expected_side_setup_schedule=None
    ):
        observed_schedules.append(expected_side_setup_schedule)
        assert expected_side_setup_schedule is None
        return {
            "complete": True,
            "classification": "worker_exit0",
            "worker_classification": "TASK041_CONSUMER_PASS",
            "process_group_gone": process_group_gone,
            "factor_inventory": {},
        }

    monkeypatch.setattr(
        supervisor,
        "_consumer_result",
        fake_consumer_result,
    )

    candidate_run = tmp_path / "candidate_public_run"
    candidate_run.mkdir()
    ledger_path = tmp_path / "compute_wall_ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "schema": "task041.compute_wall_ledger.v1",
                "limit_seconds": 172800.0,
                "used_compute_wall_seconds": 0.0,
                "used_status": "measured",
                "basis": "test-local BALH mock ledger",
                "measured": {"status": "measured", "seconds": 0.0, "records": []},
                "derived": {"status": "not_measured", "seconds": None},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    result = supervisor.run_task041_public_supervisor(
        candidate,
        source_sha=consumer_source_sha,
        run_directory=candidate_run,
        compute_wall_ledger_path=ledger_path,
        python_executable="python",
        producer_packet_root=producer_root,
        popen_factory=fake_popen,
        sample_factory=fake_sample,
        process_group_gone=lambda _pid: True,
        sleep=lambda _: None,
    )
    assert result["result_classification"] == "worker_exit0"
    assert len(popen_calls) == 1
    assert observed_schedules == [None]
    assert popen_calls[0][popen_calls[0].index("--phase") + 1] == "candidate-consumer"
    assert result["phase_results"]["producer"]["reused"] is True
    assert result["phase_results"]["producer"]["returncode"] == 0
    assert result["phase_results"]["producer"]["process_group_gone"] is True
    assert result["resource_authority"]["status"] == "measured_with_inherited_producer"
    envelope = result["resource_authority"]["derived_common_producer_envelope"]
    assert envelope["status"] == "derived"
    assert envelope["peak"]["memory_authority_bytes"] == 300
    assert envelope["peak"]["pss_bytes"] is None
    assert envelope["peak"]["uss_bytes"] is None
    assert envelope["measurement_status"]["pss_bytes"] == "not_measured"
    assert envelope["measurement_status"]["uss_bytes"] == "not_measured"
    assert envelope["producer"]["values"]["memory_authority_bytes"] == 300
    assert result["resource_authority"]["workflow_peak"]["memory_authority_bytes"] == 200
    assert envelope["producer"]["supervisor_summary_sha256"] == hashlib.sha256(
        (old_run / "supervisor_summary.json").read_bytes()
    ).hexdigest()
    summary = json.loads(
        (tmp_path / "candidate_public_run" / "supervisor_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["resource_authority"]["workflow_peak"]["memory_authority_bytes"] == 200
    reused_budget = result["compute_wall_budget"]
    consumer_wall = result["phase_results"]["consumer"]["phase_wall_seconds"]
    assert reused_budget["used_before_seconds"] == pytest.approx(0.0)
    assert reused_budget["current_invocation_seconds"] == pytest.approx(
        consumer_wall
    )
    assert reused_budget["used_after_seconds"] == pytest.approx(consumer_wall)
    assert reused_budget["used_after_seconds"] < producer_phase["phase_wall_seconds"]

    incomplete_summary = json.loads(
        (old_run / "supervisor_summary.json").read_text(encoding="utf-8")
    )
    del incomplete_summary["phase_results"]["producer"][
        "peak_process_tree_rss_bytes"
    ]
    (old_run / "supervisor_summary.json").write_text(
        json.dumps(incomplete_summary, sort_keys=True) + "\n", encoding="utf-8"
    )
    incomplete_packet = validate_balh_producer_packet(
        producer_root,
        candidate,
        consumer_source_sha,
        require_public_supervisor_summary=True,
    )
    assert incomplete_packet["producer_resource_qualified"] is False
    assert incomplete_packet["producer_phase"]["peak_process_tree_rss_bytes"] is None


def _write_representative_result_fixture(tmp_path: Path):
    from benchmarks.task041_balh_workflow import (
        _TASK041_REPRESENTATIVE_RHS_EXPECTED,
        TASK041_REPRESENTATIVE_RHS_SCOPE,
    )

    root = tmp_path / "representative_consumer"
    output = root / "numerical_output"
    output.mkdir(parents=True)
    source_sha = "c" * 40
    probe_path = tmp_path / "representative_rhs.json"
    probe_path.write_text('{"fixed":true}\n', encoding="utf-8")
    probe_sha = hashlib.sha256(probe_path.read_bytes()).hexdigest()
    packet_manifest_sha = "d" * 64
    packet_identity_path = tmp_path / "packet_identity.json"
    packet_identity_path.write_text('{"packet":"fixed"}\n', encoding="utf-8")
    packet_identity_sha = hashlib.sha256(packet_identity_path.read_bytes()).hexdigest()
    entries = [
        dict(zip(("ordinal", "side", "branch", "audit_index", "formal_column", "branch_ordinal"), (ordinal, *values)))
        for ordinal, values in enumerate(_TASK041_REPRESENTATIVE_RHS_EXPECTED)
    ]
    count_delta = dict.fromkeys(
        ("pc", "Q", "H6", "A6", "P", "PH_audit", "p4_backsolve"), 1
    )
    raw_rows, result_entries = [], []
    for entry in entries:
        ordinal = entry["ordinal"]
        audit = {
            **{key: entry[value] for key, value in {
                "representative_ordinal": "ordinal",
                "source_audit_index": "audit_index",
                "formal_column": "formal_column",
                "branch_ordinal": "branch_ordinal",
            }.items()},
            "status": "KSP_CONVERGED",
            "reason": 2,
            "ksp_positive": True,
            "explicit_true_target_reached": True,
            "relative_residual": 1.0e-3,
            "rhs_norm": 1.0,
            "residual_norm": 1.0e-3,
            "ksp_max_it": 128,
            "ksp_rtol": 1.0e-2,
            "counts": {"delta": count_delta},
        }
        raw_rows.append({"phase": "representative_rhs", "side": entry["side"], "audit": audit})
        response_dir = root / "response" / str(ordinal)
        response_dir.mkdir(parents=True)
        shards = []
        for rank in range(8):
            name = f"rank{rank:04d}.npz"
            payload = f"response-{ordinal}-{rank}".encode()
            path = response_dir / name
            path.write_bytes(payload)
            shards.append({
                "rank": rank, "path": name,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size": 1, "ownership_range": [rank, rank + 1],
            })
        response_identity = {
            "schema": "task041.representative_rhs.response_identity.v1",
            "source_sha": source_sha,
            "probe_manifest_sha256": probe_sha,
            "packet_manifest_sha256": packet_manifest_sha,
            "ordinal": ordinal, "side": entry["side"],
            "formal_column": entry["formal_column"],
            "branch_ordinal": entry["branch_ordinal"],
        }
        identity_sha = hashlib.sha256(
            json.dumps(response_identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        response_manifest_path = response_dir / "manifest.json"
        response_manifest_path.write_text(
            json.dumps({
                "schema": "myfenics.full3d.pre_recovery_packet.v1",
                "identity": response_identity, "identity_sha256": identity_sha,
                "rank_count": 8, "global_size": 8, "shards": shards,
                "metadata": {},
            }, sort_keys=True) + "\n", encoding="utf-8"
        )
        response_manifest_sha = hashlib.sha256(response_manifest_path.read_bytes()).hexdigest()
        result_entries.append({
            **entry, "status": "completed", "audit": audit,
            "artifact": {
                "manifest": str(response_manifest_path),
                "manifest_sha256": response_manifest_sha,
                "identity_sha256": identity_sha,
            },
            "rank_shards": [
                {
                    "rank": shard["rank"], "ownership_range": shard["ownership_range"],
                    "local_size": 1, "dtype": "complex128",
                    "owned_rhs_sha256": hashlib.sha256(
                        f"rhs-{ordinal}-{shard['rank']}".encode()
                    ).hexdigest(),
                    "owned_response_sha256": shard["sha256"],
                    "packet_manifest_sha256": packet_manifest_sha,
                    "packet_shard_path": shard["path"],
                    "packet_shard_sha256": shard["sha256"],
                    "response_packet_manifest_sha256": response_manifest_sha,
                }
                for shard in shards
            ],
        })
    raw_path = output / "representative_rhs_audits.jsonl"
    raw_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in raw_rows),
        encoding="utf-8",
    )
    binding = {
        "path": str(probe_path), "sha256": probe_sha,
        "scope": TASK041_REPRESENTATIVE_RHS_SCOPE,
        "budget": {"group": "shared_S0_S1_S3"}, "entries": entries,
        "source_audit": {
            "rhs_audit_path": str(raw_path),
            "rhs_audit_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        },
        "packet_binding": {
            "packet_manifest_sha256": packet_manifest_sha,
            "packet_identity": str(packet_identity_path),
            "packet_identity_sha256": packet_identity_sha,
        },
    }
    summary = {
        "schema": "task041.side_balh.candidate_consumer.v1",
        "source_sha": source_sha,
        "status": "task041_representative_rhs_completed",
        "classification": "TASK041_REPRESENTATIVE_RHS_COMPLETED",
        "representative_rhs_probe": {
            "path": str(probe_path), "sha256": probe_sha,
            "scope": TASK041_REPRESENTATIVE_RHS_SCOPE,
            "budget_group": "shared_S0_S1_S3",
        },
        "identity": {
            "source_sha": source_sha,
            "model_id": "task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8",
            "mode_count": 480, "mpi_size": 8,
        },
        "packet": {"manifest_sha256": packet_manifest_sha, "identity": str(packet_identity_path)},
        "setup": {"admission_audit": {"pass": True, "global_operator_identity": {"pass": True}}},
        "representative_rhs": {"entries": result_entries},
        "matrix_inventory": {
            "qep_calls": 0, "consumer_qep_required": False,
            "p4_factor_count_at_setup": 2, "nested_iterative_ksp_count_at_setup": 2,
            "p6_factor_count": 0, "global_direct_factor_count": 0,
            "p4_factor_count_after_cleanup": {"bottom": 0, "top": 0},
            "nested_iterative_ksp_count_after_cleanup": {"bottom": 0, "top": 0},
        },
        "lifecycle": {
            "setup_released": True, "representative_rhs_cleanup_pass": True,
            "rss_marker_emitted": True,
        },
        "markers": {"observed": [
            "bottom_construction_cleanup", "top_construction_cleanup", "final_cleanup_complete"
        ]},
        "gates": {"pass": False}, "official_rta": {"status": "not_run"},
        "formal": {"status": "not_run"},
    }
    return root, summary, binding, raw_path


def _sequential_live(side: str, p4: int, nested: int) -> dict[str, object]:
    by_side = (
        {side: {"p4_factor_count": p4, "nested_iterative_ksp_count": nested}}
        if p4 or nested
        else {}
    )
    return {
        "by_side": by_side,
        "live_side_count": int(bool(p4 or nested)),
        "live_component_counts": {
            "p4_factor": p4,
            "nested_iterative_ksp": nested,
        },
        "live_component_count_sum": p4 + nested,
    }


def _add_sequential_lifecycle_fixture(
    root: Path, summary: dict[str, object]
) -> Path:
    boundaries: list[dict[str, object]] = []
    identity_checks: dict[str, dict[str, object]] = {}
    marker_rows: list[dict[str, object]] = []
    elapsed = 0.0

    for side in ("bottom", "top"):
        diagnostics = {
            "destroyed": True,
            "p4_factor_count": 0,
            "nested_iterative_ksp_count": 0,
        }
        events = (
            ("identity", "before_build", "system_setup_stage", 0, 0),
            ("boundary", "before_build", "system_setup_stage", 0, 0),
            ("boundary", "ready", f"{side}_factor_ready", 1, 1),
            ("identity", "after_admission", "system_setup_stage", 0, 0),
            ("identity", "before_release", "system_setup_stage", 0, 0),
            ("boundary", "before_release", "system_setup_stage", 1, 1),
            (
                "boundary",
                "released",
                f"{side}_construction_cleanup",
                0,
                0,
            ),
            ("identity", "after_release", "system_setup_stage", 0, 0),
        )
        for kind, event, stage, p4, nested in events:
            elapsed += 0.1
            if kind == "identity":
                label = f"{side}_{event}"
                check = {
                    "label": label,
                    "action_relative": 0.0,
                    "rhs_relative": 0.0,
                    "source_unchanged_relative": 0.0,
                    "pass": True,
                }
                identity_checks[label] = check
                marker_rows.append(
                    {
                        "stage": stage,
                        "wall_seconds": elapsed,
                        "detail": {
                            "side": side,
                            "substage": "global_identity",
                            "identity_check": check,
                        },
                    }
                )
                continue
            boundary: dict[str, object] = {
                "side": side,
                "event": event,
                "schedule": TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
                "clock": "CLOCK_MONOTONIC",
                "live": _sequential_live(side, p4, nested),
            }
            if event == "ready":
                boundary["created_at_boundary"] = {
                    "side_inverse": 1,
                    "p4_factor": 1,
                    "nested_iterative_ksp": 1,
                }
            detail: dict[str, object] = {
                "side": side,
                "substage": "side_lifecycle",
                "lifecycle_boundary": boundary,
            }
            if event == "released":
                detail["diagnostics"] = diagnostics
            boundaries.append(boundary)
            marker_rows.append(
                {"stage": stage, "wall_seconds": elapsed, "detail": detail}
            )

    marker_path = root / "markers.jsonl"
    marker_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in marker_rows),
        encoding="utf-8",
    )
    setup_counts = {
        "p4_factor_created_total": 2,
        "nested_iterative_ksp_created_total": 2,
        "total_created": 2,
        "p4_factor_simultaneously_live_peak": 1,
        "nested_iterative_ksp_simultaneously_live_peak": 1,
        "simultaneously_live_peak": 1,
        "simultaneously_live_component_peak": 2,
        "component_cleanup_pass": True,
    }
    setup = summary["setup"]
    assert isinstance(setup, dict)
    setup["side_setup_schedule"] = TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
    setup["side_setup"] = {
        "side_setup_schedule": TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        "order": ["bottom", "top"],
        "lifecycle_boundaries": boundaries,
        "global_identity_checks": identity_checks,
        **setup_counts,
    }
    setup["candidate_inventory"] = dict(setup_counts)
    setup["side_diagnostics_after_destroy"] = {
        "bottom": {
            "destroyed": True,
            "p4_factor_count": 0,
            "nested_iterative_ksp_count": 0,
        },
        "top": {
            "destroyed": True,
            "p4_factor_count": 0,
            "nested_iterative_ksp_count": 0,
        },
    }
    summary["side_setup_schedule"] = TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
    matrix = summary["matrix_inventory"]
    assert isinstance(matrix, dict)
    matrix["p4_factor_count_at_setup"] = None
    matrix["nested_iterative_ksp_count_at_setup"] = None
    summary["markers"] = {
        "observed": [
            "bottom_construction_cleanup",
            "top_construction_cleanup",
            "final_cleanup_complete",
        ]
    }
    return marker_path


@pytest.mark.parametrize(
    "mutation", [None, "residual", "nan", "key", "shard", "cleanup"]
)
def test_representative_rhs_result_requires_fixed_raw_and_shard_binding(
    tmp_path, mutation
):
    root, summary, binding, raw_path = _write_representative_result_fixture(tmp_path)
    if mutation == "residual":
        rows = [json.loads(line) for line in raw_path.read_text().splitlines()]
        rows[0]["audit"]["residual_norm"] = 0.1
        rows[0]["audit"]["pass"] = True
        raw_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        binding["source_audit"]["rhs_audit_sha256"] = hashlib.sha256(
            raw_path.read_bytes()
        ).hexdigest()
    elif mutation == "nan":
        rows = [json.loads(line) for line in raw_path.read_text().splitlines()]
        rows[0]["audit"]["residual_norm"] = float("nan")
        rows[0]["audit"]["pass"] = True
        raw_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        binding["source_audit"]["rhs_audit_sha256"] = hashlib.sha256(
            raw_path.read_bytes()
        ).hexdigest()
    elif mutation == "key":
        rows = [json.loads(line) for line in raw_path.read_text().splitlines()]
        rows[0]["audit"]["formal_column"] += 1
        raw_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        binding["source_audit"]["rhs_audit_sha256"] = hashlib.sha256(
            raw_path.read_bytes()
        ).hexdigest()
    elif mutation == "shard":
        artifact = summary["representative_rhs"]["entries"][0]["artifact"]
        Path(artifact["manifest"]).with_name("rank0000.npz").write_bytes(b"tampered")
    elif mutation == "cleanup":
        summary["lifecycle"]["representative_rhs_cleanup_pass"] = False
    result = _validate_representative_rhs_result(
        root, summary, binding, process_group_gone=True
    )
    assert result["pass"] is (mutation is None)
    if mutation == "residual":
        assert any(
            "recomputed_relative_residual" in failure
            for failure in result["failures"]
        )
    elif mutation == "nan":
        assert any(
            failure.endswith("residual_norm") for failure in result["failures"]
        )


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "release",
        "overlap",
        "order",
        "summary_counts",
        "schedule",
        "identity",
        "identity_order",
    ],
)
def test_representative_sequential_lifecycle_is_raw_and_bound(tmp_path, mutation):
    root, summary, binding, _raw_path = _write_representative_result_fixture(tmp_path)
    marker_path = _add_sequential_lifecycle_fixture(root, summary)
    if mutation in {"release", "overlap"}:
        rows = [json.loads(line) for line in marker_path.read_text().splitlines()]
        for row in rows:
            boundary = row.get("detail", {}).get("lifecycle_boundary")
            if not isinstance(boundary, dict):
                continue
            if mutation == "release" and (
                boundary.get("side"), boundary.get("event")
            ) == ("bottom", "released"):
                boundary["live"] = _sequential_live("bottom", 1, 1)
            if mutation == "overlap" and (
                boundary.get("side"), boundary.get("event")
            ) == ("top", "ready"):
                boundary["live"] = {
                    "by_side": {
                        "bottom": {
                            "p4_factor_count": 1,
                            "nested_iterative_ksp_count": 1,
                        },
                        "top": {
                            "p4_factor_count": 1,
                            "nested_iterative_ksp_count": 1,
                        },
                    },
                    "live_side_count": 2,
                    "live_component_counts": {
                        "p4_factor": 2,
                        "nested_iterative_ksp": 2,
                    },
                    "live_component_count_sum": 4,
                }
        marker_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        for row in rows:
            boundary = row.get("detail", {}).get("lifecycle_boundary")
            if not isinstance(boundary, dict):
                continue
            for expected in summary["setup"]["side_setup"]["lifecycle_boundaries"]:
                if (
                    expected["side"], expected["event"]
                ) == (boundary.get("side"), boundary.get("event")):
                    expected["live"] = copy.deepcopy(boundary["live"])
    elif mutation == "order":
        rows = [json.loads(line) for line in marker_path.read_text().splitlines()]
        rows[1], rows[2] = rows[2], rows[1]
        marker_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
    elif mutation == "summary_counts":
        summary["setup"]["side_setup"]["simultaneously_live_peak"] = 2
    elif mutation == "identity":
        rows = [json.loads(line) for line in marker_path.read_text().splitlines()]
        for row in rows:
            check = row.get("detail", {}).get("identity_check")
            if isinstance(check, dict) and check.get("label") == (
                "bottom_after_admission"
            ):
                check["action_relative"] = 2.0e-12
        marker_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        summary_check = summary["setup"]["side_setup"]["global_identity_checks"][
            "bottom_after_admission"
        ]
        summary_check["action_relative"] = 2.0e-12
    elif mutation == "identity_order":
        rows = [json.loads(line) for line in marker_path.read_text().splitlines()]
        after_release = next(
            index
            for index, row in enumerate(rows)
            if row.get("detail", {}).get("identity_check", {}).get("label")
            == "bottom_after_release"
        )
        rows.insert(
            next(
                index
                for index, row in enumerate(rows)
                if row.get("stage") == "bottom_construction_cleanup"
            ),
            rows.pop(after_release),
        )
        marker_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )

    expected_schedule = (
        None if mutation == "schedule" else TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
    )
    result = _validate_representative_rhs_result(
        root,
        summary,
        binding,
        process_group_gone=True,
        expected_side_setup_schedule=expected_schedule,
    )
    assert result["pass"] is (mutation is None)
    if mutation is None:
        assert result["checks"]["sequential_lifecycle"] is True
    elif mutation == "identity":
        assert result["checks"]["sequential_markers"][
            "identity_values_and_order"
        ] is False
    elif mutation == "identity_order":
        assert result["checks"]["sequential_markers"][
            "identity_lifecycle_order"
        ] is False


def test_formal_mode_does_not_accept_representative_summary(tmp_path):
    root, summary, binding, _raw_path = _write_representative_result_fixture(tmp_path)
    (root / "consumer_summary.json").write_text(
        json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8"
    )
    representative_result = supervisor._consumer_result(
        root, process_group_gone=True, representative_rhs_binding=binding
    )
    assert representative_result["complete"] is True
    result = supervisor._consumer_result(root, process_group_gone=True)
    assert result["complete"] is False
    assert result["completion_scope"] == "formal"
