"""V27 profile wiring, observe-only launch, and original-case preservation."""

import json
from pathlib import Path
from types import SimpleNamespace

from src.io import load_and_resolve
from src.io.physical_intermediate_profile import (
    PHYSICAL_MEMORY_POLICY_V23,
    WORKINGSET_SETUP_PROFILE,
    profile_facts,
)
from src.io.run_specification import thaw
from src.runners import task038_full3d_iterative as dispatch
from src.runners import task038_launcher as launcher


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "input/task39extra/v27_workingset_p6_setup_original_h7p5.dat"


def test_interface_balanced_apply_uses_single_source_and_returns_owned_result():
    from src.solvers.physical_interface_balanced import InterfaceBalancedCoupling

    source = SimpleNamespace(array=[1.0])
    owned_result = object()
    calls = []

    class BalancedAction:
        def apply(self, value):
            calls.append(value)
            return owned_result

    coupling = object.__new__(InterfaceBalancedCoupling)
    coupling.coarse_calls = []
    coupling._last_repair_vectors = []
    coupling._pc_apply_sequence = 0
    coupling.balanced = BalancedAction()

    assert coupling.apply(source) is owned_result
    assert calls == [source]
    assert coupling._pc_apply_sequence == 1


def test_v27_mock_end_to_end_observes_swap_but_keeps_memory_pressure_gates(
    monkeypatch, tmp_path, capsys
):
    specification = load_and_resolve(INPUT)
    facts = profile_facts(WORKINGSET_SETUP_PROFILE)
    payload = specification.as_jsonable()
    assert specification.solver["preconditioner"] == WORKINGSET_SETUP_PROFILE
    assert specification.identity["run_id"] == (
        "task39extra_v27_workingset_p6_setup_original_h7p5"
    )
    assert specification.identity["comparison_group"] == (
        "review_v25_workingset_and_p6_setup"
    )
    assert specification.geometry["model_variant"] == "original"
    assert specification.geometry.get("cell_notch") is None
    assert specification.discretization["mesh_axis_cell_counts"] == (9, 5, 22)
    assert specification.execution["require_zero_swap"] is False
    assert facts["resources"]["require_zero_swap"] is False
    assert facts["resources"]["swap_policy"] == "observe_only"
    assert facts["resources"]["time_policy"] == "observe_only"
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
        return {"mock_worker": True}

    from src.runners import physical_dual_cell_condensed_lowmem_v20 as lowmem

    monkeypatch.setattr(lowmem, "_run_physical_dual_cell_condensed_lowmem", fake_worker)
    assert dispatch.run_full3d_iterative(
        payload, tmp_path / "worker", source_sha="s" * 40
    ) == {"mock_worker": True}
    assert worker["profile_identity"] == WORKINGSET_SETUP_PROFILE
    assert worker["allowed_stages"] == ("Q4_ORIGINAL",)
    assert worker["batch_identity"] == "review_v25_workingset_and_p6_setup"
    assert worker["summary_schema"] == (
        "task039extra.v27.workingset-p6-setup.worker-summary.v1"
    )
    assert worker["summary_filename"] == (
        "physical_dual_condensed_workingset_p6_setup_v27_summary.json"
    )
    assert worker["predecessor_by_stage"]["Q4_ORIGINAL"]["original_only"] is True
    assert worker["require_zero_swap"] is False
    assert worker["payload"]["geometry"]["model_variant"] == "original"

    run_directory = tmp_path / "launcher-run"
    old_v26_ledger = (
        ROOT
        / "benchmarks/artifacts/task39extra/setup_efficiency_v26/"
        "shared_workflow_ledger.json"
    )
    old_v26_ledger_before = (
        old_v26_ledger.read_bytes() if old_v26_ledger.exists() else None
    )

    def timestamp_directory(*_args, **_kwargs):
        run_directory.mkdir()
        return run_directory

    reservation = {}
    real_reserve_v27 = launcher._reserve_v27_workingset_setup_budget

    def reserve_v27(_repo_root, run_directory, **kwargs):
        result = real_reserve_v27(
            tmp_path / "temporary-repository",
            run_directory,
            **kwargs,
        )
        reservation.update(result)
        return result

    monkeypatch.setattr(launcher, "_timestamp_directory", timestamp_directory)
    monkeypatch.setattr(launcher, "_reserve_v27_workingset_setup_budget", reserve_v27)
    monkeypatch.setattr(
        launcher,
        "_physical_source_gate",
        lambda *_args, **_kwargs: {
            "source_sha": "a" * 40,
            "tracked_and_nonignored_untracked_clean": True,
        },
    )
    from benchmarks import subreaper_watchdog

    watchdog = {}

    def fake_supervise(argv, *_args, **kwargs):
        watchdog["argv"] = list(argv)
        watchdog["kwargs"] = dict(kwargs)
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
    assert reservation["path"].startswith(str(tmp_path / "temporary-repository"))
    assert reservation["prerequisite"]["original_only"] is True
    assert watchdog["kwargs"]["allow_swap_observation"] is True
    assert watchdog["kwargs"]["stop_on_global_swap"] is False
    assert watchdog["kwargs"]["time_policy"] == "observe_only"
    assert watchdog["kwargs"]["memory_policy"] == PHYSICAL_MEMORY_POLICY_V23
    assert "-m" in watchdog["argv"]
    assert watchdog["argv"][watchdog["argv"].index("-m") + 1] == (
        "src.runners.task038_input_worker"
    )
    assert "--expected-adapter" in watchdog["argv"]
    assert watchdog["argv"][watchdog["argv"].index("--expected-adapter") + 1] == (
        "task038.full3d_iterative"
    )
    assert (
        watchdog["kwargs"]["worker_environment"][
            "PHYSICAL_WATCHDOG_MEMORY_POLICY"
        ]
        == PHYSICAL_MEMORY_POLICY_V23
    )
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert manifest["swap_policy"] == "observe_only"
    assert manifest["require_zero_swap"] is False
    assert result["result_classification"] == "worker_exit0"
    assert result["swap_gate_enforced"] is False
    assert (
        old_v26_ledger.read_bytes() if old_v26_ledger.exists() else None
    ) == old_v26_ledger_before
