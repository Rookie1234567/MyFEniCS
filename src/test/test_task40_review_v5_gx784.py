"""Focused V5 identity, fixed-key, residual, and count-only ledger contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks import check_task40_review_v5_gx784 as checker
from benchmarks import run_task40_v5_target_ledger as target_ledger
from benchmarks import subreaper_watchdog
from src.geometry.task40_nonseparable_plan import TASK40_GX784_RUN_ID
from src.io import InputError, load_and_resolve
from src.io.input_validation import simulation_config_3d_from_normalized
from src.io.physical_intermediate_profile import profile_facts
from src.postprocessing.task40_saved_field_h_comparison import (
    _comparison_axis_union,
    _exact_axis_union,
    _exact_axis_union_many,
    union_axis_points,
)
from src.runners import task038_launcher as launcher
from src.runners import workflow_timebase


ROOT = Path(__file__).resolve().parents[2]
GX784_INPUT = ROOT / (
    "input/task40extra_0p7nm_engineering/"
    "nonseparable_gx784_p6_q4_review_v5.dat"
)
GX560_INPUT = ROOT / (
    "input/task40extra_0p7nm_engineering/"
    "nonseparable_gx560_p6_q4_manual_m2_v3.dat"
)


def _solver_summary(*, post_release_residual: float = 5.0e-7) -> dict:
    final = 5.0e-7
    residuals = {
        "native_identity_relative": 3.0e-11,
        "internal_residual_relative": 4.0e-12,
        "schur_port_identity_relative": 2.0e-12,
        "port_residual_relative": 3.0e-12,
        "strict_zero_slave_storage": True,
    }
    return {
        "final_residual": {"explicit_relative_residual": final},
        "post_release_final_residual": {
            "explicit_relative_residual": post_release_residual,
            "release_facts": {
                "p6": {"released_after_final_residual": True},
                "p4": {"released_after_final_residual": True},
            },
        },
        "gates": {
            "independent_final_explicit_relative_residual": final,
            "post_release_final_explicit_relative_residual": post_release_residual,
            "post_release_residual_gate": True,
            "authority_limited_checks_pass": True,
        },
        "release_after_final_residual": True,
        "x2_retained_final": {
            "complete_field_saved": True,
            "saved_before_field_evaluation": True,
            "residuals": residuals,
        },
    }


def test_frozen_significant_modes_are_reloaded_and_exactly_value_checked():
    payload = json.loads(checker.FROZEN_KEYS_PATH.read_text(encoding="utf-8"))
    keys = [list(row) for row in payload["frozen_baseline"]["selected_keys"]]
    loaded = checker._load_frozen_significant_keys(keys)

    assert len(loaded) == 11
    changed = [list(row) for row in keys]
    changed[0] = [changed[0][0], -3, changed[0][2], changed[0][3]]
    with pytest.raises(ValueError, match="differ from the frozen channel-study"):
        checker._load_frozen_significant_keys(changed)


def test_post_release_native_residual_over_limit_holds_all_comparisons(
    tmp_path: Path,
):
    solver_path = tmp_path / "worker_summary.json"
    solver_path.write_text(
        json.dumps(_solver_summary(post_release_residual=2.0e-6)),
        encoding="utf-8",
    )
    payload = {
        "schema": "task40extra.review-v5.gx784-paired-comparison.v1",
        "solver_evidence": {
            "path": str(solver_path),
            "sha256": hashlib.sha256(solver_path.read_bytes()).hexdigest(),
        },
    }

    result = checker.check_payload(payload)

    assert result["classification"] == (
        "solver_or_recovery_gate_not_passed_comparison_held"
    )
    assert result["comparison_status"] == "held"
    assert result["solver_gate"][
        "post_release_explicit_relative_A6_true_residual"
    ] == 2.0e-6
    assert any("post-release full A6 residual" in item for item in result["failure_reasons"])


def test_target_ledger_reuses_workspace_formulas_and_actual_auto_count():
    mode_count = 32_060
    record = target_ledger._target_resource_ledger(mode_count, {"status": "fixture"})
    vectors = record["outer_vector_and_scratch_inventory"]
    retained_rows = 3_094_272 + mode_count

    assert vectors["retained_rows_with_actual_auto_M"] == retained_rows
    assert vectors["fgmres_basis_groups"]["Krylov_basis_vectors"]["count"] == 33
    assert vectors["fgmres_basis_groups"]["preconditioned_basis_vectors"]["count"] == 33
    assert vectors["additional_work_vectors"]["count"] == 8
    assert vectors["total_krylov_vector_count"] == 74
    assert vectors["total_outer_krylov_bytes"] == 74 * retained_rows * 16
    assert vectors["retained_full_scratch_bytes"] == (
        24 * 10_228_620 * 16 + 10 * retained_rows * 16
    )

    local = record["local_450_432_single_instance_inventory"]
    assert local["one_raw_full_local_tensor"]["shape"] == [882, 882]
    assert local["one_interior_block_and_in_place_dense_LU_storage"]["bytes"] == (
        450 * 450 * 16
    )
    assert local["one_schur_block"]["bytes"] == 432 * 432 * 16
    assert local["one_recovery_operator"]["bytes"] == 450 * 432 * 16
    assert record["remaining_local_and_factor_unknowns"][
        "actual_sparse_lu_fill_bytes_by_q"
    ].startswith("unknown")


def test_target_mode_identity_hash_binds_material_incidence_and_ports():
    specification = load_and_resolve(GX784_INPUT)
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    target = target_ledger._target_config(cfg)
    identity = target_ledger._target_mode_physical_identity(target)

    assert identity["wavelength_nm"] == 0.7
    assert identity["geometry"]["period_x_nm"] == 50.0
    assert identity["geometry"]["period_y_nm"] == 25.0
    assert identity["incidence"]["grazing_angle_deg"] == pytest.approx(1.0)
    assert identity["incidence"]["azimuth_deg"] == 0.0
    assert identity["ports"]["top"]["reference_plane_z_nm"] == 130.0
    assert identity["ports"]["bottom"]["reference_plane_z_nm"] == -10.0
    assert "internal grating/notch geometry does not enter" in identity["scope"]
    assert target_ledger._canonical_sha256(identity) == target_ledger._canonical_sha256(
        target_ledger._target_mode_physical_identity(target)
    )


def test_legacy_pair_axis_metadata_is_unchanged_and_v5_uses_three_source_union():
    from types import SimpleNamespace

    first = SimpleNamespace(
        axes=(
            np.asarray([0.0, 0.5, 1.0]),
            np.asarray([-1.0, 0.0, 1.0]),
            np.asarray([0.0, 0.5, 1.0]),
        )
    )
    second = SimpleNamespace(
        axes=(
            np.asarray([0.0, 0.25, 0.75, 1.0]),
            np.asarray([-1.0, -0.5, 0.5, 1.0]),
            np.asarray([0.0, 1.0]),
        )
    )
    third = SimpleNamespace(
        axes=(
            np.asarray([0.0, 0.125, 0.5, 1.0]),
            np.asarray([-1.0, 0.0, 0.25, 1.0]),
            np.asarray([0.0, 0.25, 0.75, 1.0]),
        )
    )

    axes, legacy_facts = _exact_axis_union(first, second)
    expected_facts = []
    for name, left, right in zip(("x", "y", "z"), first.axes, second.axes, strict=True):
        union, facts = union_axis_points(left, right)
        expected_facts.append({**facts, "axis": name})
        np.testing.assert_array_equal(union, axes[len(expected_facts) - 1])
    assert legacy_facts == expected_facts
    pair_axes, pair_facts = _comparison_axis_union(first, second)
    assert pair_facts == legacy_facts
    for actual, expected in zip(pair_axes, axes, strict=True):
        np.testing.assert_array_equal(actual, expected)

    triple_axes, triple_facts = _exact_axis_union_many((first, second, third))
    assert triple_facts[0]["source_point_counts"] == [3, 4, 4]
    assert triple_facts[0]["union_point_count"] == len(triple_axes[0])
    assert 0.125 in triple_axes[0]
    assert 0.25 in triple_axes[0]


def _mock_formal_launch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    input_path: Path,
    *,
    time_policy: str,
) -> tuple[dict, dict, dict]:
    specification = load_and_resolve(input_path)
    run_directory = tmp_path / specification.identity["run_id"]
    captures: dict[str, dict] = {"reservation": {}, "watchdog": {}}
    service_cgroup = Path(
        "/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/"
        "app.slice/myfenics-case-review-v5-mock.service"
    )

    def timestamp_directory(*_args, **_kwargs):
        run_directory.mkdir(parents=True, exist_ok=False)
        return run_directory

    def reserve(_repo_root, _run_directory, **kwargs):
        captures["reservation"].update(kwargs)
        workflow_seconds = float(kwargs["stage_budget"]["workflow_seconds"])
        return {
            "path": str(tmp_path / "shared_workflow_ledger.json"),
            "stage": kwargs["stage"],
            "attempt_index": 0,
            "reserved_seconds": workflow_seconds,
            "time_policy": kwargs["time_policy"],
        }

    def fake_supervise(argv, watchdog_path, **kwargs):
        captures["watchdog"].update(kwargs)
        captures["watchdog"]["argv"] = list(argv)
        captures["watchdog"]["directory"] = str(watchdog_path)
        return {
            "leader_exit_code": 0,
            "classification": "COMPLETED",
            "job_swap_activity": "zero_supported_by_zero_global_activity",
            "global_swap_activity": {"delta": {"pswpout": 0}},
            "launch_envelope": {"effective_total_bytes": 64 * 1024**3},
            "memory_scope": "dedicated subreaper plus every descendant",
            "samples": 12,
            "process_tree_samples": 12,
            "process_tree_swap_gate_enforced": True,
            "global_swap_gate_enforced": False,
            "process_tree_all_status_readable": True,
            "process_tree_identity_coverage": "complete",
            "observed_child_identity_coverage": "complete",
            "sampled_process_tree_swap_peak_bytes": 0,
            "descendants_cleared": True,
        }

    monkeypatch.setattr(launcher, "_timestamp_directory", timestamp_directory)
    monkeypatch.setattr(launcher, "_reserve_task40_0p7nm_budget", reserve)
    monkeypatch.setattr(launcher, "_settle_v14_shared_budget", lambda *_a, **_k: None)
    monkeypatch.setattr(launcher, "current_cgroup_path", lambda: service_cgroup)
    monkeypatch.setattr(
        launcher,
        "_physical_source_gate",
        lambda *_a, **_k: {
            "source_sha": "a" * 40,
            "tracked_and_nonignored_untracked_clean": True,
        },
    )
    monkeypatch.setattr(launcher, "_task40_swap_qualification", lambda _authority: {
        "policy": "require_zero_swap",
        "status": "qualified_zero",
        "process_tree_peak_swap_bytes": 0,
    })
    monkeypatch.setattr(
        launcher,
        "build_execution_plan",
        lambda *_a, **_k: type(
            "Plan", (), {"adapter_available": True, "argv": ("mock-worker",)}
        )(),
    )
    monkeypatch.setattr(subreaper_watchdog, "supervise", fake_supervise)
    result = launcher.launch_specification(
        specification,
        source_sha="a" * 40,
        v14_time_policy=time_policy,
    )
    return result, captures, specification


def test_gx784_full_launcher_chain_enforces_v5_deadline_and_watchdog_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    result, captured, specification = _mock_formal_launch(
        monkeypatch, tmp_path, GX784_INPUT, time_policy="enforce"
    )

    assert specification.identity["run_id"] == TASK40_GX784_RUN_ID
    reservation = captured["reservation"]
    watchdog = captured["watchdog"]
    assert reservation["time_policy"] == "enforce"
    assert reservation["stage"] == "Q4_ORIGINAL"
    assert reservation["stage_budget"] == {
        "workflow_seconds": 172800.0,
        "solve_seconds": 172800.0,
    }
    assert reservation["service_cgroup_path"].name.startswith("myfenics-case-")
    assert watchdog["time_policy"] == "enforce"
    assert watchdog["timebase_guard"] is True
    assert watchdog["timebase_policy"] == "conservative_realtime"
    assert 0 < watchdog["wall_seconds"] <= 172800.0
    assert 0 < watchdog["solve_seconds"] <= 172800.0
    assert watchdog["memory_policy"] == profile_facts(
        specification.solver["preconditioner"]
    )["resources"]["watchdog_memory_policy"]
    assert watchdog["pss_sampling_policy"] == "disabled_by_profile"
    assert result["time_policy"] == "enforce"
    assert result["time_observations"]["workflow_limit_seconds"] == 172800.0
    assert result["time_observations"]["reservation_seconds"] == 172800.0
    manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    assert manifest["effective_watchdog_authority"]["wall_reference_seconds"] == watchdog[
        "wall_seconds"
    ]

    with pytest.raises(InputError, match="requires --v14-time-policy enforce"):
        launcher.launch_specification(
            load_and_resolve(GX784_INPUT),
            source_sha="b" * 40,
            v14_time_policy="observe_only",
        )


def test_old_task40_profile_keeps_43200_second_observe_only_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    result, captured, specification = _mock_formal_launch(
        monkeypatch, tmp_path, GX560_INPUT, time_policy="observe_only"
    )

    assert specification.identity["run_id"] != TASK40_GX784_RUN_ID
    assert captured["reservation"]["stage_budget"]["workflow_seconds"] == 43200.0
    assert captured["reservation"]["time_policy"] == "observe_only"
    assert captured["watchdog"]["time_policy"] == "observe_only"
    assert captured["watchdog"]["wall_seconds"] == 43200.0
    assert result["time_policy"] == "observe_only"
    assert result["time_observations"]["workflow_limit_seconds"] == 43200.0
    with pytest.raises(InputError, match="cell-condensed profiles require"):
        launcher.launch_specification(
            load_and_resolve(GX560_INPUT),
            source_sha="c" * 40,
            v14_time_policy="enforce",
        )


def _v5_shared_ledger(root: Path, *, elapsed: float = 1000.0) -> Path:
    from src.geometry.task40_nonseparable_plan import (
        TASK40_GX784_WORKFLOW_BUDGET_SECONDS,
    )

    ledger_path = (
        root
        / "benchmarks/artifacts/task40extra_0p7nm_engineering/"
        / "task40_nonseparable_0p7nm"
        / TASK40_GX784_RUN_ID
        / "shared_workflow_ledger.json"
    )
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text(
        json.dumps(
            {
                "schema": "task40extra.nonseparable-0p7nm.shared-workflow-ledger.v1",
                "batch_identity": TASK40_GX784_RUN_ID,
                "total_budget_seconds": TASK40_GX784_WORKFLOW_BUDGET_SECONDS,
                "elapsed_seconds": elapsed,
                "conservative_allowance_seconds": 0.0,
                "policy_debits": [],
                "stages": {
                    "Q4_ORIGINAL": {
                        "active_attempt": None,
                        "attempts": [{
                            "source_sha": "a" * 40,
                            "settled_seconds": elapsed,
                            "status": "worker_exit0",
                        }],
                    }
                },
                "time_contract": {
                    "hard_limit_seconds": TASK40_GX784_WORKFLOW_BUDGET_SECONDS,
                    "policy": "enforce",
                    "scope": (
                        "Task40 Review V5 Gx784 run_case workflow from the first launcher "
                        "workflow clock start through field recovery and official output"
                    ),
                    "batch_clock_start_semantics": "first attempt workflow_clock_start",
                    "retry_cost_is_cumulative": True,
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return ledger_path


def test_v5_postprocess_time_is_charged_to_the_same_cumulative_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    start = {"monotonic": 1000.0, "boottime": 1000.0, "utc_ns": 10**12}
    reservation_sample = {
        "monotonic": 1001.0,
        "boottime": 1001.0,
        "utc_ns": 10**12 + 1_000_000_000,
    }
    monkeypatch.setattr(
        workflow_timebase, "clock_sample", lambda: dict(reservation_sample)
    )
    end = {
        "monotonic": 1012.0,
        "boottime": 1013.0,
        "utc_ns": 10**12 + 14_500_000_000,
    }
    ledger_path = _v5_shared_ledger(tmp_path)
    lease = launcher._reserve_task40_v5_postprocess_budget(
        tmp_path,
        source_sha="b" * 40,
        run_directory=tmp_path / "postprocess-attempt1",
        workflow_clock_start=start,
    )
    assert lease["reserved_seconds"] == 171799.0
    settled = launcher._settle_task40_v5_postprocess_budget(
        lease,
        status="POSTPROCESS_WATCHDOG_PASS",
        watchdog_summary_path=None,
        parent_clock_end=end,
    )

    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    attempt = ledger["stages"]["V5_POSTPROCESS"]["attempts"][0]
    assert attempt["settled_seconds"] == 14.5
    assert attempt["actual_elapsed_monotonic_seconds"] == 12.0
    assert attempt["actual_elapsed_boottime_seconds"] == 13.0
    assert attempt["conservative_clock_charge_seconds"] == 14.5
    assert settled["effective_budget_after_settlement"]["measured_elapsed_seconds"] == 1014.5
    assert settled["effective_budget_after_settlement"]["remaining_seconds"] == 171785.5


def test_v5_postprocess_allows_only_hash_bound_bug_replay_without_refunding_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    start = {"monotonic": 2000.0, "boottime": 2000.0, "utc_ns": 2 * 10**12}
    middle = {
        "monotonic": 2007.0,
        "boottime": 2007.0,
        "utc_ns": 2 * 10**12 + 7_000_000_000,
    }
    end = {
        "monotonic": 2015.0,
        "boottime": 2015.0,
        "utc_ns": 2 * 10**12 + 15_000_000_000,
    }
    reservation_sample = {
        "monotonic": 2001.0,
        "boottime": 2001.0,
        "utc_ns": 2 * 10**12 + 1_000_000_000,
    }
    monkeypatch.setattr(
        workflow_timebase, "clock_sample", lambda: dict(reservation_sample)
    )
    ledger_path = _v5_shared_ledger(tmp_path, elapsed=1000.0)
    first = launcher._reserve_task40_v5_postprocess_budget(
        tmp_path,
        source_sha="b" * 40,
        run_directory=tmp_path / "postprocess-attempt1",
        workflow_clock_start=start,
    )
    failed_watchdog = tmp_path / "watchdog_implementation_failure.json"
    failed_watchdog.write_text(
        json.dumps({"classification": "WORKER_FAILED", "leader_exit_code": 2}),
        encoding="utf-8",
    )
    launcher._settle_task40_v5_postprocess_budget(
        first,
        status="POSTPROCESS_WORKER_FAILED_OR_CONTROLLED_STOP",
        watchdog_summary_path=failed_watchdog,
        parent_clock_end=middle,
    )
    reservation_sample.update(middle)
    evidence = {
        "schema": "task40extra.review-v5.postprocess-bug-replay.v1",
        "classification": "IMPLEMENTATION_BUG",
        "run_id": TASK40_GX784_RUN_ID,
        "stage": "V5_POSTPROCESS",
        "allowed_repeat_count": 1,
        "prior_attempt_source_sha": "b" * 40,
        "fixed_source_sha": "c" * 40,
        "prior_shared_ledger_sha256": hashlib.sha256(
            ledger_path.read_bytes()
        ).hexdigest(),
        "bug_and_fix": "fixture: corrected one mapping-key error",
        "supporting_evidence": [{"path": "attempt1/raw.json", "sha256": "d" * 64}],
    }
    second = launcher._reserve_task40_v5_postprocess_budget(
        tmp_path,
        source_sha="c" * 40,
        run_directory=tmp_path / "postprocess-attempt2",
        workflow_clock_start=middle,
        implementation_bug_replay=evidence,
    )
    assert second["replay"] is True
    assert second["reserved_seconds"] == 171793.0
    launcher._settle_task40_v5_postprocess_budget(
        second,
        status="POSTPROCESS_WATCHDOG_PASS",
        watchdog_summary_path=None,
        parent_clock_end=end,
    )
    final = json.loads(ledger_path.read_text(encoding="utf-8"))
    attempts = final["stages"]["V5_POSTPROCESS"]["attempts"]
    assert [row["settled_seconds"] for row in attempts] == [7.0, 8.0]
    assert final["elapsed_seconds"] == 1015.0
    assert final["total_budget_seconds"] == 172800.0

    ledger_after_two = ledger_path.read_bytes()
    third_evidence = dict(evidence)
    third_evidence["prior_shared_ledger_sha256"] = hashlib.sha256(
        ledger_after_two
    ).hexdigest()
    with pytest.raises(InputError, match="single local repair replay"):
        launcher._reserve_task40_v5_postprocess_budget(
            tmp_path,
            source_sha="e" * 40,
            run_directory=tmp_path / "postprocess-attempt3",
            workflow_clock_start=end,
            implementation_bug_replay=third_evidence,
        )
    assert ledger_path.read_bytes() == ledger_after_two


def test_v5_completed_negative_comparison_cannot_be_replayed_as_an_implementation_bug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    start = {"monotonic": 3000.0, "boottime": 3000.0, "utc_ns": 3 * 10**12}
    finish = {
        "monotonic": 3005.0,
        "boottime": 3005.0,
        "utc_ns": 3 * 10**12 + 5_000_000_000,
    }
    monkeypatch.setattr(workflow_timebase, "clock_sample", lambda: dict(start))
    ledger_path = _v5_shared_ledger(tmp_path)
    first = launcher._reserve_task40_v5_postprocess_budget(
        tmp_path,
        source_sha="b" * 40,
        run_directory=tmp_path / "postprocess-negative-result",
        workflow_clock_start=start,
    )
    completed_checker = tmp_path / "watchdog_completed_negative.json"
    completed_checker.write_text(
        json.dumps({"classification": "COMPLETED", "leader_exit_code": 0}),
        encoding="utf-8",
    )
    launcher._settle_task40_v5_postprocess_budget(
        first,
        status="POSTPROCESS_WATCHDOG_PASS",
        watchdog_summary_path=completed_checker,
        parent_clock_end=finish,
    )
    before = ledger_path.read_bytes()
    evidence = {
        "schema": "task40extra.review-v5.postprocess-bug-replay.v1",
        "classification": "IMPLEMENTATION_BUG",
        "run_id": TASK40_GX784_RUN_ID,
        "stage": "V5_POSTPROCESS",
        "allowed_repeat_count": 1,
        "prior_attempt_source_sha": "b" * 40,
        "fixed_source_sha": "c" * 40,
        "prior_shared_ledger_sha256": hashlib.sha256(before).hexdigest(),
        "bug_and_fix": "this claim must not convert a completed negative comparison into a replay",
        "supporting_evidence": [{"path": "negative_checker.json", "sha256": "e" * 64}],
    }
    with pytest.raises(InputError, match="replay evidence is invalid"):
        launcher._reserve_task40_v5_postprocess_budget(
            tmp_path,
            source_sha="c" * 40,
            run_directory=tmp_path / "postprocess-not-authorized",
            workflow_clock_start=finish,
            implementation_bug_replay=evidence,
        )
    assert ledger_path.read_bytes() == before
