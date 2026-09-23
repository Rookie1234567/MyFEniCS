"""V28 opt-in profile routing and observe-only launcher contract."""

import hashlib
import json
from pathlib import Path

import pytest

from src.io import load_and_resolve
from src.io.input_loader import InputError
from src.io.physical_intermediate_profile import (
    FUSED_KERNEL_PROFILE,
    PHYSICAL_MEMORY_POLICY_V23,
    profile_facts,
)
from src.io.run_specification import thaw
from src.runners import task038_full3d_iterative as dispatch
from src.runners import task038_launcher as launcher


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "input/task39extra/v28_fused_kernel_original_h7p5.dat"


def test_v28_profile_resolves_and_dispatches_only_q4(monkeypatch, tmp_path, capsys):
    specification = load_and_resolve(INPUT)
    facts = profile_facts(FUSED_KERNEL_PROFILE)
    payload = specification.as_jsonable()
    assert specification.solver["preconditioner"] == FUSED_KERNEL_PROFILE
    assert specification.identity["run_id"] == (
        "task39extra_v28_fused_kernel_original_h7p5"
    )
    assert specification.geometry["model_variant"] == "original"
    assert specification.discretization["mesh_axis_cell_counts"] == (9, 5, 22)
    assert specification.execution["require_zero_swap"] is False
    assert facts["fused_a6_volume"] is True
    assert facts["shared_tensor_contractions"] is False
    assert facts["a6_shared_tensor_contractions"] is False
    assert facts["h6_shared_tensor_contractions"] is False
    assert facts["route_selection"]["fused_component_volume"] is True
    assert facts["route_selection"]["shared_contractions"] is False
    assert facts["route_selection"]["a6_shared_contractions"] is False
    assert facts["route_selection"]["h6_shared_contractions"] is False
    assert facts["thread_selection"]["status"] == "SELECTED_SINGLE_CORE"
    assert "whole-lifecycle peak neutrality" in facts["thread_selection"][
        "selection_reason"
    ]
    assert facts["resources"]["time_policy"] == "observe_only"
    assert facts["resources"]["swap_policy"] == "observe_only"
    assert facts["resources"]["require_observe_only"] is True
    assert facts["resources"]["watchdog_memory_policy"] == (
        PHYSICAL_MEMORY_POLICY_V23
    )
    assert payload["derived"]["physical_intermediate_profile"] == thaw(facts)

    from scripts.run_case import main as run_case_main

    assert run_case_main(
        [str(INPUT), "--validate-only", "--v14-time-policy", "observe_only"]
    ) == 0
    capsys.readouterr()

    worker = {}

    def fake_worker(resolved_payload, run_directory, **kwargs):
        worker.update(kwargs)
        worker["payload"] = resolved_payload
        worker["run_directory"] = run_directory
        return {"mock_worker": True}

    from src.runners import physical_dual_cell_condensed_lowmem_v20 as lowmem

    monkeypatch.setattr(
        lowmem, "_run_physical_dual_cell_condensed_lowmem", fake_worker
    )
    assert dispatch.run_full3d_iterative(
        payload, tmp_path / "worker", source_sha="s" * 40
    ) == {"mock_worker": True}
    assert worker["profile_identity"] == FUSED_KERNEL_PROFILE
    assert worker["allowed_stages"] == ("Q4_ORIGINAL",)
    assert worker["batch_identity"] == (
        "review_v26_fused_A6_H6_optional_setup_threads"
    )
    assert worker["summary_schema"] == (
        "task039extra.v28.fused-kernel.worker-summary.v1"
    )
    assert worker["require_zero_swap"] is False
    assert worker["payload"]["geometry"]["model_variant"] == "original"


def test_v28_launcher_keeps_real_memory_gate_and_observes_swap(
    monkeypatch, tmp_path
):
    specification = load_and_resolve(INPUT)
    run_directory = tmp_path / "launcher-run"

    def timestamp_directory(*_args, **_kwargs):
        run_directory.mkdir()
        return run_directory

    reservation = {}
    real_reserve_v28 = launcher._reserve_v28_fused_kernel_budget

    def reserve_v28(_repo_root, run_directory, **kwargs):
        result = real_reserve_v28(
            tmp_path / "temporary-repository",
            run_directory,
            **kwargs,
        )
        reservation.update(result)
        return result

    monkeypatch.setattr(launcher, "_timestamp_directory", timestamp_directory)
    monkeypatch.setattr(launcher, "_reserve_v28_fused_kernel_budget", reserve_v28)
    monkeypatch.setattr(
        launcher,
        "current_cgroup_path",
        lambda: Path(
            "/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/"
            "app.slice/myfenics-case-test.service"
        ),
    )
    monkeypatch.setattr(
        launcher,
        "_physical_source_gate",
        lambda *_args, **_kwargs: {
            "source_sha": "a" * 40,
            "tracked_and_nonignored_untracked_clean": True,
        },
    )
    from benchmarks import subreaper_watchdog

    observed = {}

    def fake_supervise(argv, *_args, **kwargs):
        observed["argv"] = list(argv)
        observed["kwargs"] = dict(kwargs)
        return {
            "leader_exit_code": 0,
            "classification": "COMPLETED",
            "job_swap_activity": "observed_process_tree_swap",
            "launch_envelope": {},
            "memory_scope": "synthetic mock process tree",
            "process_tree_swap_gate_enforced": False,
            "global_swap_gate_enforced": False,
            "sampled_process_tree_swap_peak_bytes": 1,
        }

    monkeypatch.setattr(subreaper_watchdog, "supervise", fake_supervise)
    result = launcher.launch_specification(
        specification, source_sha="a" * 40, v14_time_policy="observe_only"
    )
    assert reservation["time_policy"] == "observe_only"
    assert observed["kwargs"]["allow_swap_observation"] is True
    assert observed["kwargs"]["stop_on_global_swap"] is False
    assert observed["kwargs"]["memory_policy"] == PHYSICAL_MEMORY_POLICY_V23
    assert observed["kwargs"]["worker_environment"][
        "PHYSICAL_WATCHDOG_MEMORY_POLICY"
    ] == PHYSICAL_MEMORY_POLICY_V23
    assert result["swap_gate_enforced"] is False
    assert result["result_classification"] == "worker_exit0"
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert manifest["swap_policy"] == "observe_only"
    assert manifest["require_zero_swap"] is False


def test_v28_foreground_launch_is_rejected_before_creating_run_or_ledger(
    monkeypatch,
):
    specification = load_and_resolve(INPUT)
    monkeypatch.setattr(
        launcher, "current_cgroup_path", lambda: Path("/sys/fs/cgroup/init.scope")
    )

    def unexpected_timestamp(*_args, **_kwargs):
        pytest.fail("V28 foreground rejection must happen before run creation")

    monkeypatch.setattr(launcher, "_timestamp_directory", unexpected_timestamp)
    with pytest.raises(InputError, match="systemd user app.slice cgroup"):
        launcher.launch_specification(
            specification,
            source_sha="a" * 40,
            v14_time_policy="observe_only",
        )


def test_v28_user_service_cgroup_requires_existing_user_app_unit():
    is_service = launcher._is_v28_user_service_cgroup
    assert is_service(
        Path(
            "/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/"
            "app.slice/myfenics-case-test.service"
        )
    )
    assert not is_service(Path("/sys/fs/cgroup/init.scope"))
    assert not is_service(
        Path(
            "/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/"
            "app.slice/other-case.service"
        )
    )
    assert not is_service(
        Path(
            "/sys/fs/cgroup/system.slice/myfenics-case-test.service"
        )
    )


def test_v28_startup_scope_recovery_is_hash_bound_and_one_shot(tmp_path):
    repo_root = tmp_path
    fixed_input = repo_root / "input/task39extra/v28_fused_kernel_original_h7p5.dat"
    fixed_input.parent.mkdir(parents=True)
    fixed_input.write_bytes(INPUT.read_bytes())
    input_sha = hashlib.sha256(fixed_input.read_bytes()).hexdigest()
    old_source_sha = launcher.V28_STARTUP_SCOPE_FAILED_SOURCE_SHA
    fixed_source_sha = "b" * 40
    run_directory = repo_root / launcher.V28_STARTUP_SCOPE_RUN_RELATIVE
    run_directory.mkdir(parents=True)
    (run_directory / "input_sha256.txt").write_text(input_sha + "\n")
    elapsed_settled = 338.8901043349492
    summary = {
        "run_id": "task39extra_v28_fused_kernel_original_h7p5",
        "status": "finished",
        "result_classification": "USER_CONTROLLED_STOP",
        "output_directory": str(run_directory),
        "resource_authority": {
            "classification": "USER_CONTROLLED_STOP",
            "descendants_cleared": True,
            "remaining_child_pids": [],
            "source_state": {"source_sha": old_source_sha},
        },
    }
    summary_bytes = json.dumps(summary, sort_keys=True).encode("utf-8")
    summary_path = run_directory / "run_summary.json"
    summary_path.write_bytes(summary_bytes)
    scope = {
        "schema": "task39extra.v28.launch-scope-classification.v1",
        "observed_run_root": str(run_directory.relative_to(repo_root)),
        "observed_run_root_absolute": str(run_directory),
        "source_sha": old_source_sha,
        "input_sha256": input_sha,
        "raw_run_summary": "run_summary.json",
        "raw_run_summary_sha256": hashlib.sha256(summary_bytes).hexdigest(),
        "raw_classification_preserved": "USER_CONTROLLED_STOP",
        "execution_classification": "CONTROLLED_STOP_STARTUP_SCOPE_INVALID",
        "observed_cgroup_path": "/init.scope",
        "numerical_iteration_result": None,
    }
    scope_path = run_directory / "launch_scope_classification.json"
    scope_bytes = json.dumps(scope, sort_keys=True).encode("utf-8")
    scope_path.write_bytes(scope_bytes)

    ledger_path = (
        repo_root
        / "benchmarks/artifacts/task39extra/fused_operator_speed_v28/"
        "review_v26_fused_A6_H6_optional_setup_threads/shared_workflow_ledger.json"
    )
    ledger_path.parent.mkdir(parents=True)
    first_attempt = {
        "attempt": 1,
        "source_sha": old_source_sha,
        "run_directory": str(run_directory),
        "status": "USER_CONTROLLED_STOP",
        "watchdog_classification": "USER_CONTROLLED_STOP",
        "actual_elapsed_seconds": elapsed_settled,
        "settled_seconds": elapsed_settled,
        "replay": False,
    }
    ledger = {
        "schema": "task039extra.v28.fused-kernel.shared-workflow-ledger.v1",
        "batch_identity": "review_v26_fused_A6_H6_optional_setup_threads",
        "total_budget_seconds": 43200.0,
        "elapsed_seconds": elapsed_settled,
        "conservative_allowance_seconds": 0.0,
        "policy_debits": [],
        "fresh_worker_count": 1,
        "source_attempts": [
            {"stage": "Q4_ORIGINAL", "source_sha": old_source_sha, "attempt": 1}
        ],
        "stages": {
            "Q4_ORIGINAL": {
                "attempts": [first_attempt],
                "active_attempt": None,
            }
        },
        "unique_bug_replay_count": 0,
        "allowed_stages": ["Q4_ORIGINAL"],
    }
    ledger_path.write_text(json.dumps(ledger, sort_keys=True))
    service_cgroup_path = Path(
        "/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/"
        "app.slice/myfenics-case-test.service"
    )

    scope["observed_cgroup_path"] = "/sys/fs/cgroup/init.scope"
    scope_path.write_text(json.dumps(scope, sort_keys=True))
    unchanged_ledger = ledger_path.read_bytes()

    def reserve(source_sha, output_name):
        return launcher._reserve_v28_fused_kernel_budget(
            repo_root,
            tmp_path / output_name,
            source_sha=source_sha,
            stage="Q4_ORIGINAL",
            stage_budget={"workflow_seconds": 43200.0},
            workflow_clock_start={"monotonic": 1.0},
            service_cgroup_path=service_cgroup_path,
            time_policy="observe_only",
        )

    with pytest.raises(InputError, match="not bound to the preserved stopped attempt"):
        reserve(fixed_source_sha, "rejected-run")
    assert ledger_path.read_bytes() == unchanged_ledger

    scope_path.write_bytes(scope_bytes)
    reservation = reserve(fixed_source_sha, "accepted-run")
    assert reservation["replay"] is True
    assert reservation["replay_evidence"]["classification"] == (
        "CONTROLLED_STOP_STARTUP_SCOPE_INVALID"
    )
    assert reservation["replay_evidence"]["raw_summary_sha256"] == hashlib.sha256(
        summary_bytes
    ).hexdigest()
    assert reservation["replay_evidence"]["scope_evidence_sha256"] == hashlib.sha256(
        scope_bytes
    ).hexdigest()
    saved = json.loads(ledger_path.read_text())
    saved_attempts = saved["stages"]["Q4_ORIGINAL"]["attempts"]
    assert saved["unique_bug_replay_count"] == 1
    assert len(saved_attempts) == 2
    assert saved_attempts[0]["status"] == "USER_CONTROLLED_STOP"
    assert saved_attempts[0]["actual_elapsed_seconds"] == elapsed_settled
    assert saved_attempts[1]["replay_evidence"]["input_sha256"] == input_sha

    saved_attempts[1]["status"] = "CONTROLLED_STOP"
    saved["stages"]["Q4_ORIGINAL"]["active_attempt"] = None
    ledger_path.write_text(json.dumps(saved, sort_keys=True))
    used_ledger = ledger_path.read_bytes()
    with pytest.raises(InputError, match="exhausted its one repair replay"):
        reserve("c" * 40, "second-replay")
    assert ledger_path.read_bytes() == used_ledger
