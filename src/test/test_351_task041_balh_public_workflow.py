"""Focused public-contract tests for the Task041 side-BAL_H profiles."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks.task041_balh_workflow import (
    build_task041_balh_candidate_consumer_command,
    build_task041_balh_exact_consumer_command,
    build_task041_balh_mode_prep_command,
    task041_balh_consumer_identity_binding,
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
from src.runners.task041_supervisor import (
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
    monkeypatch.setattr(
        supervisor,
        "_consumer_result",
        lambda consumer_root, process_group_gone: {
            "complete": True,
            "classification": "worker_exit0",
            "worker_classification": "TASK041_CONSUMER_PASS",
            "process_group_gone": process_group_gone,
            "factor_inventory": {},
        },
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
    monkeypatch.setattr(
        supervisor,
        "_consumer_result",
        lambda consumer_root, process_group_gone: {
            "complete": True,
            "classification": "worker_exit0",
            "worker_classification": "TASK041_CONSUMER_PASS",
            "process_group_gone": process_group_gone,
            "factor_inventory": {},
        },
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
