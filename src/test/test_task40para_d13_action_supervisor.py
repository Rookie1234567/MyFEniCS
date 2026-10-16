from __future__ import annotations

import contextlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "docs/task40para_phi90_mesh_modes_direct/scripts/d13_saved_field_port_action_only_supervisor.py"
)
CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "docs/task40para_phi90_mesh_modes_direct/outcomes/records/d13_saved_field_port_action_only_contract_v3.json"
)
SPEC = importlib.util.spec_from_file_location("task40_d13_action_supervisor", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _worker_command(repo: Path, interpreter: Path, contract: Path, output: Path) -> list[str]:
    worker = repo / "docs/task40para_phi90_mesh_modes_direct/scripts/d13_saved_field_port_action_only.py"
    return [
        "mpiexec", "-n", "1", "numactl", "--interleave=0,1", "taskset", "-c", "24",
        str(interpreter), str(worker), "--contract", str(contract), "--output", str(output),
    ]


def test_supervisor_wrapper_binds_existing_host_floor_guard_and_watchdog(tmp_path, monkeypatch):
    import benchmarks.subreaper_watchdog as watchdog
    import src.io.native_capacity_profile as profiles
    from src.runners import native_capacity

    repo = SCRIPT.resolve().parents[3]
    shared_python = Path("/qualified/shared/bin/python")
    monkeypatch.setenv("TASK40_SHARED_VENV_ROOT", "/qualified/shared")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    contract_path = CONTRACT.resolve()
    output_path = tmp_path / "report.json"
    command = _worker_command(repo, shared_python, contract_path, output_path)
    contract = json.loads(contract_path.read_text())
    assert contract_path.name == "d13_saved_field_port_action_only_contract_v3.json"
    # The on-disk v3 artifact keeps the worker's already-supported v2 payload schema.
    assert contract["schema"] == "task40.d13.saved-field-port-action-only-contract.v2"
    reviewed = contract["fresh_and_supervision"]["supervision"]
    assert "supervision" not in contract
    assert reviewed["stop_on_global_swap"] is False
    MODULE._validate_worker_command(command, contract_path, output_path, contract)

    with pytest.raises(ValueError, match="rank-local NUMA/CPU24"):
        wrong = list(command)
        wrong[4] = "--interleave=0,1,2"
        MODULE._validate_worker_command(wrong, contract_path, output_path, contract)

    facts = {
        "resources": {
            "resource_stop_policy": "host_available_floor_v1",
            "minimum_available_bytes": 64 * 1024**3,
        }
    }
    monkeypatch.setattr(profiles, "native_profile_facts", lambda _identity: facts)
    guard_calls = []

    @contextlib.contextmanager
    def fake_guard(profile, *, memory_policy):
        guard_calls.append((profile, memory_policy))
        yield repo, {"native_capacity_heavy_lock": "/canonical/host/lock"}

    monkeypatch.setattr(native_capacity, "native_capacity_guard", fake_guard)
    watchdog_calls = []

    def fake_supervise(argv, directory, **kwargs):
        watchdog_calls.append((argv, directory, kwargs))
        return {
            "classification": "COMPLETED",
            "leader_exit_code": 0,
            "descendants_cleared": True,
            "remaining_child_pids": [],
            "resource_stop_policy": "host_available_floor_v1",
            "rss_hard_limit_bytes": None,
            "sampled_process_tree_rss_peak_bytes": 123456,
            "minimum_available_bytes": 64 * 1024**3,
            "launch_envelope": {"effective_available_bytes": 100 * 1024**3},
            "swap_policy": "observe_only",
            "job_swap_activity": "HOST_FLOOR_OBSERVE_ONLY_no_task_or_global_swap_observed",
            "pss_sampling_policy": "disabled_by_profile",
            "elapsed_seconds": 1.25,
        }

    monkeypatch.setattr(watchdog, "supervise", fake_supervise)
    supervision_path = tmp_path / "supervision.json"
    result = MODULE.run_supervised(
        command,
        watchdog_directory=tmp_path / "watchdog",
        supervision_output_path=supervision_path,
        contract=contract,
    )

    assert guard_calls == [(profiles.TASK40_PHI90_D13_Y2_P6_DIRECT_PROFILE, "interleave_nodes0_1")]
    assert len(watchdog_calls) == 1
    seen_command, seen_directory, options = watchdog_calls[0]
    assert seen_command == command
    assert seen_directory == tmp_path / "watchdog"
    assert options["wall_seconds"] is None and options["solve_seconds"] is None
    assert options["resource_stop_policy"] == "host_available_floor_v1"
    assert options["minimum_available_bytes"] == reviewed["minimum_available_bytes"] == 64 * 1024**3
    assert options["rss_hard_limit_bytes"] is None and options["rss_warning_bytes"] is None
    assert options["stop_on_global_swap"] is False
    assert options["pss_sampling_policy"] == reviewed["pss_sampling_policy"] == "disabled_by_profile"
    assert result["descendants_cleared"] is True
    assert result["rss_hard_limit_bytes"] is None
    saved = json.loads(supervision_path.read_text())
    assert result["schema"] == "task40.d13.saved-field-port-action-only-supervision.v2"
    assert saved == result
    assert saved["classification"] == "COMPLETED"
    assert saved["minimum_available_bytes"] == 64 * 1024**3
    assert saved["sample_interval_seconds"] == reviewed["sample_interval_seconds"]
