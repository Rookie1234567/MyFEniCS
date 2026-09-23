"""V28 opt-in profile routing and observe-only launcher contract."""

import json
from pathlib import Path

from src.io import load_and_resolve
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
