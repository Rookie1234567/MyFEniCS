"""Focused V5 identity, fixed-key, residual, and count-only ledger contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from dataclasses import replace
import sys
import time

import numpy as np
import pytest

from benchmarks import check_task40_review_v5_gx784 as checker
from benchmarks import run_task40_v5_target_ledger as target_ledger
from benchmarks import subreaper_watchdog
from benchmarks import run_task40_v5_postprocess_service as postprocess_service
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
    with pytest.raises(InputError, match="local repair replay"):
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


def test_v5_first_launcher_reservation_resolves_clock_and_settles_real_elapsed(
    tmp_path: Path,
):
    from src.geometry.task40_nonseparable_plan import (
        TASK40_COMPARISON_GROUP,
        TASK40_GX784_WORKFLOW_BUDGET_SECONDS,
    )

    start = workflow_timebase.clock_sample()
    lease = launcher._reserve_task40_0p7nm_budget(
        tmp_path,
        tmp_path / "run-attempt1",
        source_sha="a" * 40,
        stage="Q4_ORIGINAL",
        stage_budget={
            "workflow_seconds": TASK40_GX784_WORKFLOW_BUDGET_SECONDS,
            "solve_seconds": TASK40_GX784_WORKFLOW_BUDGET_SECONDS,
        },
        workflow_clock_start=start,
        time_policy=launcher.V14_TIME_POLICY_ENFORCE,
        run_id=TASK40_GX784_RUN_ID,
        comparison_group=TASK40_COMPARISON_GROUP,
        service_cgroup_path=Path(
            "/user.slice/user-1000.slice/user@1000.service/app.slice/"
            "myfenics-case-v5-reserve-test.service"
        ),
    )
    ledger_path = Path(lease["path"])
    reserved = json.loads(ledger_path.read_text(encoding="utf-8"))
    attempt = reserved["stages"]["Q4_ORIGINAL"]["attempts"][0]
    assert lease["replay"] is False
    assert attempt["reserved_seconds"] <= TASK40_GX784_WORKFLOW_BUDGET_SECONDS
    assert attempt["workflow_clock_start"] == start

    end = workflow_timebase.clock_sample()
    interval = workflow_timebase.checked_interval(
        start, end, policy=workflow_timebase.CONSERVATIVE_REALTIME
    )
    launcher._settle_v14_shared_budget(
        lease,
        status="TEST_SETTLED",
        authority=None,
        parent_interval=interval,
        parent_clock_end=end,
    )
    settled = json.loads(ledger_path.read_text(encoding="utf-8"))
    settled_attempt = settled["stages"]["Q4_ORIGINAL"]["attempts"][0]
    assert settled["stages"]["Q4_ORIGINAL"]["active_attempt"] is None
    assert settled_attempt["settled_seconds"] == pytest.approx(
        interval["budget_seconds"]
    )
    assert settled["elapsed_seconds"] == pytest.approx(
        interval["budget_seconds"]
    )


def test_v5_preledger_bug_charge_seeds_shared_clock_and_spends_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from src.geometry.task40_nonseparable_plan import (
        TASK40_COMPARISON_GROUP,
        TASK40_GX784_WORKFLOW_BUDGET_SECONDS,
    )

    input_path = tmp_path / (
        "input/task40extra_0p7nm_engineering/"
        "nonseparable_gx784_p6_q4_review_v5.dat"
    )
    input_path.parent.mkdir(parents=True)
    input_path.write_bytes(b"isolated Gx784 input identity")
    log_path = tmp_path / "benchmarks/artifacts/user_services/preledger-failure.log"
    log_path.parent.mkdir(parents=True)
    failure_signature = "NameError: name 'CONSERVATIVE_REALTIME' is not defined"
    log_path.write_text(f"Traceback\n{failure_signature}\n", encoding="utf-8")
    evidence_dir = tmp_path / (
        "benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5"
    )
    evidence_dir.mkdir(parents=True)
    original_path = evidence_dir / "preledger_implementation_bug_attempt.json"
    original = {
        "schema": "task40extra.review-v5.preledger-implementation-bug-attempt.v1",
        "classification": "IMPLEMENTATION_BUG",
        "run_id": TASK40_GX784_RUN_ID,
        "stage": "Q4_ORIGINAL",
        "failed_source_sha": "a" * 40,
        "fixed_source_sha": None,
        "input_path": str(input_path),
        "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "service_unit": "myfenics-case-v5-preledger-failure.service",
        "service_invocation_id": "3" * 32,
        "service_exit_status": 1,
        "service_main_status": "failed",
        "service_exec_start_monotonic_ns": 618257280235,
        "service_exec_exit_monotonic_ns": 618257469280,
        "elapsed_charge_seconds": 0.000189045,
        "elapsed_charge_basis": "initial mistakenly labelled ns receipt",
        "failure_signature": failure_signature,
        "failure_log_path": str(log_path),
        "failure_log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
        "numerical_worker_started": False,
        "watchdog_started": False,
        "fe_mesh_or_space_built": False,
        "assembly_factorization_or_pde_calls": False,
        "task_scope_swap": "no numerical worker existed",
        "authorized_repeat_count": 1,
        "preserved_utc": "2026-10-03T07:36:30Z",
    }
    original_bytes = (json.dumps(original, indent=2, sort_keys=True) + "\n").encode()
    original_path.write_bytes(original_bytes)
    monkeypatch.setattr(
        launcher,
        "TASK40_V5_PRELEDGER_ORIGINAL_RECORD_SHA256",
        hashlib.sha256(original_bytes).hexdigest(),
    )
    corrected = dict(original)
    corrected.update(
        {
            "schema": "task40extra.review-v5.preledger-implementation-bug-attempt.v2",
            "supersedes_original_path": str(original_path),
            "supersedes_original_sha256": hashlib.sha256(original_bytes).hexdigest(),
            "service_exec_start_monotonic_usec": original.pop(
                "service_exec_start_monotonic_ns"
            ),
            "service_exec_exit_monotonic_usec": original.pop(
                "service_exec_exit_monotonic_ns"
            ),
            "superseded_elapsed_charge_seconds": 0.000189045,
            "elapsed_charge_seconds": 0.189045,
            "elapsed_charge_basis": (
                "systemd Monotonic timestamp properties are usec; full service leader "
                "lifetime is a conservative upper bound only, not total preparation or PDE time"
            ),
            "allowed_repeat_count": 1,
            "timing_correction_utc": "2026-10-03T07:37:00Z",
            "fixed_source_sha": launcher.TASK40_V5_PRELEDGER_FIXED_SOURCE_SHA,
        }
    )
    corrected.pop("service_exec_start_monotonic_ns")
    corrected.pop("service_exec_exit_monotonic_ns")
    corrected_path = evidence_dir / "preledger_implementation_bug_attempt_corrected.json"
    corrected_path.write_text(
        json.dumps(corrected, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    start = workflow_timebase.clock_sample()
    lease = launcher._reserve_task40_0p7nm_budget(
        tmp_path,
        tmp_path / "run-corrected-replay",
        source_sha=launcher.TASK40_V5_PRELEDGER_FIXED_SOURCE_SHA,
        stage="Q4_ORIGINAL",
        stage_budget={
            "workflow_seconds": TASK40_GX784_WORKFLOW_BUDGET_SECONDS,
            "solve_seconds": TASK40_GX784_WORKFLOW_BUDGET_SECONDS,
        },
        workflow_clock_start=start,
        time_policy=launcher.V14_TIME_POLICY_ENFORCE,
        run_id=TASK40_GX784_RUN_ID,
        comparison_group=TASK40_COMPARISON_GROUP,
        service_cgroup_path=Path(
            "/user.slice/user-1000.slice/user@1000.service/app.slice/"
            "myfenics-case-v5-corrected-replay.service"
        ),
    )
    ledger_path = Path(lease["path"])
    reserved = json.loads(ledger_path.read_text(encoding="utf-8"))
    attempt = reserved["stages"]["Q4_ORIGINAL"]["attempts"][0]
    assert reserved["elapsed_seconds"] == pytest.approx(0.189045)
    assert reserved["unique_bug_replay_count"] == 1
    assert reserved["preledger_implementation_bug_replays"][0][
        "evidence_sha256"
    ] == hashlib.sha256(corrected_path.read_bytes()).hexdigest()
    assert attempt["bug_replay_count_before"] == 1
    assert attempt["reserved_seconds"] <= TASK40_GX784_WORKFLOW_BUDGET_SECONDS - 0.189045
    assert lease["task40_batch_replay_accounting"]["selected_bug_replay_limit"] == 0

    end = workflow_timebase.clock_sample()
    interval = workflow_timebase.checked_interval(
        start, end, policy=workflow_timebase.CONSERVATIVE_REALTIME
    )
    launcher._settle_v14_shared_budget(
        lease,
        status="TEST_SETTLED",
        authority=None,
        parent_interval=interval,
        parent_clock_end=end,
    )
    settled = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert settled["elapsed_seconds"] == pytest.approx(
        0.189045 + interval["budget_seconds"]
    )
    assert settled["unique_bug_replay_count"] == 1


def _copy_real_task40_v5_history_for_v6_test(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Copy the genuine settled ledger and hash-bound pre-ledger evidence."""
    artifact_root = repo_root / "benchmarks/artifacts/task40extra_0p7nm_engineering"
    source_artifact_root = ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering"
    copied_evidence_dir = artifact_root / "target_ledger_v5"
    copied_evidence_dir.mkdir(parents=True)
    old_original = source_artifact_root / "target_ledger_v5/preledger_implementation_bug_attempt.json"
    old_corrected = source_artifact_root / "target_ledger_v5/preledger_implementation_bug_attempt_corrected.json"
    original = json.loads(old_original.read_text(encoding="utf-8"))
    corrected = json.loads(old_corrected.read_text(encoding="utf-8"))
    old_input = ROOT / "input/task40extra_0p7nm_engineering/nonseparable_gx784_p6_q4_review_v5.dat"
    copied_input = repo_root / "input/task40extra_0p7nm_engineering/nonseparable_gx784_p6_q4_review_v5.dat"
    copied_input.parent.mkdir(parents=True)
    shutil.copyfile(old_input, copied_input)
    source_log = Path(corrected["failure_log_path"])
    copied_log = artifact_root / "user_services" / source_log.name
    copied_log.parent.mkdir(parents=True)
    shutil.copyfile(source_log, copied_log)
    copied_original = copied_evidence_dir / old_original.name
    copied_corrected = copied_evidence_dir / old_corrected.name
    original.update(input_path=str(copied_input), failure_log_path=str(copied_log))
    original_bytes = (json.dumps(original, indent=2, sort_keys=True) + "\n").encode()
    copied_original.write_bytes(original_bytes)
    original_sha = hashlib.sha256(original_bytes).hexdigest()
    monkeypatch.setattr(launcher, "TASK40_V5_PRELEDGER_ORIGINAL_RECORD_SHA256", original_sha)
    corrected.update(
        input_path=str(copied_input),
        failure_log_path=str(copied_log),
        supersedes_original_path=str(copied_original),
        supersedes_original_sha256=original_sha,
    )
    copied_corrected.write_text(
        json.dumps(corrected, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    ledger_source = (
        source_artifact_root / "task40_nonseparable_0p7nm" / TASK40_GX784_RUN_ID
        / "shared_workflow_ledger.json"
    )
    ledger_path = (
        artifact_root / "task40_nonseparable_0p7nm" / TASK40_GX784_RUN_ID
        / "shared_workflow_ledger.json"
    )
    ledger_path.parent.mkdir(parents=True)
    ledger = json.loads(ledger_source.read_text(encoding="utf-8"))
    old_corrected_path = str(old_corrected.resolve())
    new_entry_paths = {
        "evidence_path": str(copied_corrected.resolve()),
        "evidence_sha256": hashlib.sha256(copied_corrected.read_bytes()).hexdigest(),
        "original_evidence_path": str(copied_original.resolve()),
        "original_evidence_sha256": original_sha,
        "failure_log_path": str(copied_log.resolve()),
    }

    def rebind(value):
        if isinstance(value, dict):
            if value.get("evidence_path") == old_corrected_path:
                value.update(new_entry_paths)
            for child in value.values():
                rebind(child)
        elif isinstance(value, list):
            for child in value:
                rebind(child)

    rebind(ledger)
    ledger_path.write_text(
        json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return ledger_path


def test_v6_real_ledger_authorization_worker_and_ready_postprocess_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Exercise V6's one-shot chain against copied history with non-FE leaves."""
    from src.geometry.task40_nonseparable_plan import (
        TASK40_COMPARISON_GROUP,
        TASK40_GX784_WORKFLOW_BUDGET_SECONDS,
    )

    repo_root = tmp_path / "copied-repository"
    repo_root.mkdir()
    ledger_path = _copy_real_task40_v5_history_for_v6_test(repo_root, monkeypatch)
    initial_ledger_sha = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    old_ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    preserved_q4 = json.loads(json.dumps(old_ledger["stages"]["Q4_ORIGINAL"]["attempts"][0]))
    preserved_post = json.loads(json.dumps(old_ledger["stages"]["V5_POSTPROCESS"]["attempts"][0]))
    assert old_ledger["elapsed_seconds"] == pytest.approx(4.619253995631944)
    assert old_ledger["unique_bug_replay_count"] == 1

    spec = load_and_resolve(GX784_INPUT)
    source_sha = "d" * 40
    service_cgroup = Path(
        "/user.slice/user-1000.slice/user@1000.service/app.slice/"
        "myfenics-case-task40-v6-control-chain.service"
    )
    run_directory = repo_root / "results/gx784-v6-control-chain"
    control_leaf = r'''
import json, sys
from pathlib import Path
blocked=("dolfinx", "basix", "petsc4py", "slepc4py", "mpi4py")
def guard():
    bad=[name for name in sys.modules if name.startswith(blocked)]
    assert not bad, bad
guard()
from src.io.physical_intermediate_profile import profile_facts
from src.runners.physical_dual_cell_condensed_lowmem_v20 import _resolve_v20_worker_time_contract
from src.runners.physical_p4_schur_v14 import _V14Runtime, _v14_conditional_time_stop_decision
out=Path(sys.argv[1]); source=sys.argv[2]; root=Path(sys.argv[3])
resolved=json.loads((out/"resolved_config.json").read_text())
profile=resolved["solver"]["preconditioner"]
runtime=_V14Runtime(out,"Q4_ORIGINAL",profile_facts(profile),root=root,source_sha=source,
 batch_identity=resolved["run_id"],evidence_prefix="v6_control")
policy=_resolve_v20_worker_time_contract(resolved,runtime,profile=profile,stage="Q4_ORIGINAL")
resources=runtime.contract["resources"]; limit=float(policy["hard_limit_seconds"])
workflow=runtime.workflow_reserved_seconds
ordinary=_v14_conditional_time_stop_decision(solve_elapsed=31.0,workflow_elapsed=31.0,
 solve_limit=limit,workflow_limit=workflow,time_policy=runtime.time_policy)
edge=_v14_conditional_time_stop_decision(solve_elapsed=0.0,workflow_elapsed=workflow,
 solve_limit=limit,workflow_limit=workflow,time_policy=runtime.time_policy)
assert runtime.shared_budget["total_budget_seconds"]==172800.0
assert 0 < workflow <= 172800.0 and policy["effective_time_policy"]=="enforce"
assert resources["stage_budgets"]["Q4_ORIGINAL"]["workflow_seconds"]==172800.0
assert resources["pc_hard_seconds"]==172800.0
assert ordinary["reason"] is None and edge["reason"]=="workflow_budget_reached"
assert edge["workflow_time_gate"]["exceeded"] is True
guard()
(out/"v6_control_chain.json").write_text(json.dumps({"status":"passed",
 "shared_total_seconds":runtime.shared_budget["total_budget_seconds"],
 "workflow_reserved_seconds":workflow,"pc_hard_seconds":resources["pc_hard_seconds"],
 "ordinary_31_second_reason":ordinary["reason"],"zero_boundary_reason":edge["reason"],
 "fe_modules_loaded":[]} ,sort_keys=True)+"\n")
'''
    original_plan_builder = launcher.build_execution_plan

    def sentinel_plan_builder(specification, output, **kwargs):
        plan = original_plan_builder(specification, output, **kwargs)
        return replace(
            plan,
            argv=(sys.executable, "-c", control_leaf, str(Path(output).resolve()), source_sha, str(repo_root)),
        )

    monkeypatch.setattr(launcher, "__file__", str(repo_root / "src/runners/task038_launcher.py"))
    monkeypatch.setattr(launcher, "build_execution_plan", sentinel_plan_builder)
    monkeypatch.setattr(
        launcher,
        "_physical_source_gate",
        lambda _root, sha: {"source_sha": sha, "tracked_and_nonignored_untracked_clean": True},
    )
    monkeypatch.setattr(launcher, "current_cgroup_path", lambda: service_cgroup)
    monkeypatch.setattr(launcher, "_timestamp_directory", lambda *_a, **_k: (run_directory.mkdir(parents=True), run_directory)[1])
    real_supervise = subreaper_watchdog.supervise
    supervised_calls = []

    def observed_supervise(command, directory, **kwargs):
        supervised_calls.append({"command": list(command), "directory": str(directory), **kwargs})
        return real_supervise(command, directory, **kwargs)

    monkeypatch.setattr(subreaper_watchdog, "supervise", observed_supervise)
    launch = launcher.launch_specification(
        spec, source_sha=source_sha, v14_time_policy=launcher.V14_TIME_POLICY_ENFORCE
    )
    assert Path(launch["manifest"]).is_file()
    assert len(supervised_calls) == 1
    control_record = json.loads((run_directory / "v6_control_chain.json").read_text())
    assert control_record["status"] == "passed" and control_record["fe_modules_loaded"] == []
    assert launch["resource_authority"]["classification"] == "COMPLETED"

    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    q4 = ledger["stages"]["Q4_ORIGINAL"]["attempts"]
    assert len(q4) == 2 and q4[0] == preserved_q4
    assert q4[1]["replay"] is False
    assert q4[1]["review_authorization"]["authorization_id"] == launcher.TASK40_V6_AUTHORIZATION_ID
    assert ledger["unique_bug_replay_count"] == 1
    assert ledger["stages"]["V5_POSTPROCESS"]["attempts"][0] == preserved_post
    assert len(ledger["review_authorizations"]) == 1
    assert ledger["review_authorizations"][0]["consumed"] is True
    assert ledger["review_authorizations"][0]["previous_shared_ledger_sha256"] == initial_ledger_sha

    with pytest.raises(InputError):
        launcher._reserve_task40_0p7nm_budget(
            repo_root, repo_root / "results/duplicate-authorization", source_sha=source_sha,
            stage="Q4_ORIGINAL",
            stage_budget={"workflow_seconds": TASK40_GX784_WORKFLOW_BUDGET_SECONDS,
                          "solve_seconds": TASK40_GX784_WORKFLOW_BUDGET_SECONDS},
            workflow_clock_start=workflow_timebase.clock_sample(),
            time_policy=launcher.V14_TIME_POLICY_ENFORCE, run_id=TASK40_GX784_RUN_ID,
            comparison_group=TASK40_COMPARISON_GROUP, service_cgroup_path=service_cgroup,
            input_sha256=spec.input_sha256, physical_model_sha256=spec.physical_model_sha256,
        )

    manifest_path = run_directory / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(status="finished", result_classification="worker_exit0", exit_status=0)
    manifest.setdefault("physical_model_sha256", spec.physical_model_sha256)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (run_directory / "run_summary.json").write_text(json.dumps({
        "run_id": manifest["run_id"], "status": manifest["status"],
        "result_classification": manifest["result_classification"],
        "exit_status": manifest["exit_status"],
    }, indent=2, sort_keys=True) + "\n")
    worker_path = run_directory / postprocess_service.WORKER_SUMMARY_NAME
    worker_path.write_text(json.dumps({
        "schema":"task40extra.nonseparable-0p7nm.p6q4.worker-summary.v1",
        "source_sha":source_sha,"profile":"task40extra_0p7nm_p6trace_p4_reference_metric_v2",
        "status":"PASS","result_classification":manifest["result_classification"],**_solver_summary(),
    }, indent=2, sort_keys=True) + "\n")
    archive = run_directory / "x2_retained_vectors.testbin"
    archive.write_bytes(b"nonempty no-FE retained vector test archive")
    packet = {"identity":{"source_sha":source_sha,
              "physical_model_sha256":spec.physical_model_sha256},
              "arrays":{"path":str(archive),"sha256":hashlib.sha256(archive.read_bytes()).hexdigest()}}
    (run_directory / "x2_retained_final.json").write_text(json.dumps(packet,indent=2,sort_keys=True)+"\n")

    monkeypatch.setattr(postprocess_service, "ROOT", repo_root)
    post_source_sha = source_sha
    monkeypatch.setattr(postprocess_service, "_git_facts", lambda: ("task40extra_0p7nm_engineering", post_source_sha))
    failure_message = "RuntimeError: injected V6 parent-side implementation failure"

    def fail_before_supervisor():
        raise RuntimeError(failure_message.split(": ", 1)[1])

    failed = postprocess_service._run(
        run_directory, None, worker_command_override=[sys.executable, "-c", "pass"],
        pre_supervise_hook=fail_before_supervisor,
    )
    assert failed["status"] == "POSTPROCESS_PARENT_FAILED"
    assert failed["error"] == failure_message and failed["worker_started"] is False
    assert failed["watchdog_summary"] is None and len(supervised_calls) == 1
    failed_result = Path(failed["pre_settlement_result_path"])
    failed_sha = hashlib.sha256(failed_result.read_bytes()).hexdigest()
    assert failed_sha == failed["pre_settlement_result_sha256"]
    assert not Path(failed["watchdog_directory"]).exists()
    ledger_before_repair = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    post_source_sha = "e" * 40
    replay = {
        "schema":"task40extra.review-v6.postprocess-parent-bug-replay.v1",
        "classification":"IMPLEMENTATION_BUG","authorization_id":launcher.TASK40_V6_AUTHORIZATION_ID,
        "review_commit_sha":launcher.TASK40_V6_REVIEW_COMMIT_SHA,"run_id":TASK40_GX784_RUN_ID,
        "stage":"V5_POSTPROCESS","allowed_repeat_count":1,"prior_attempt":2,
        "prior_attempt_source_sha":source_sha,"fixed_source_sha":post_source_sha,
        "prior_shared_ledger_sha256":ledger_before_repair,
        "pre_settlement_result_path":str(failed_result.resolve()),
        "pre_settlement_result_sha256":failed_sha,"failure_signature":failure_message,
        "bug_and_fix":"Removed the injected parent-side startup failure before watchdog or worker launch.",
        "supporting_evidence":[{"path":str(failed_result.resolve()),"sha256":failed_sha}],
    }
    evidence_path = run_directory / "postprocess_v5/attempt2/implementation_bug_replay.json"
    evidence_path.write_text(json.dumps(replay,indent=2,sort_keys=True)+"\n")
    monkeypatch.setattr(postprocess_service,"_git_facts",lambda:("task40extra_0p7nm_engineering",post_source_sha))
    checker_leaf = r'''
import hashlib,json,sys
from pathlib import Path
blocked=("dolfinx","basix","petsc4py","slepc4py","mpi4py")
def guard():
 bad=[name for name in sys.modules if name.startswith(blocked)]; assert not bad,bad
guard()
from benchmarks import check_task40_review_v5_gx784 as checker
root=Path(sys.argv[1]); comparison=root/"postprocess_v5/attempt3/gx784_pair_comparisons.json"
checker_path=comparison.with_name("gx784_independent_check.json")
solver=json.loads((root/"task40extra_nonseparable_0p7nm_p6q4_summary.json").read_text())
solver["final_residual"]["explicit_relative_residual"]=2.0e-6
solver_path=root/"postprocess_v5/attempt3/sentinel_failed_solver_summary.json"
solver_path.write_text(json.dumps(solver,sort_keys=True)+"\n")
payload={"schema":"task40extra.review-v5.gx784-paired-comparison.v1",
 "solver_evidence":{"path":str(solver_path),"sha256":hashlib.sha256(solver_path.read_bytes()).hexdigest()}}
comparison.parent.mkdir(parents=True,exist_ok=True)
comparison.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
checked=checker.check_payload(payload)
checked["source_result_path"]=str(comparison)
checked["source_result_sha256"]=hashlib.sha256(comparison.read_bytes()).hexdigest()
checker_path.write_text(json.dumps(checked,indent=2,sort_keys=True)+"\n")
assert checked["status"]=="failed" and checked["independently_recomputed"] is True
assert checked["classification"]=="solver_or_recovery_gate_not_passed_comparison_held"
guard()
'''
    completed = postprocess_service._run(
        run_directory, evidence_path,
        worker_command_override=[sys.executable,"-c",checker_leaf,str(run_directory)],
        pre_supervise_hook=lambda: time.sleep(0.2),
    )
    assert len(supervised_calls) == 2
    assert completed["status"] == "POSTPROCESS_WORKER_COMPLETED"
    assert completed["watchdog_summary"]["classification"] == "COMPLETED"
    assert completed["watchdog_summary"]["leader_exit_code"] == 0
    assert completed["workflow_elapsed_at_supervise_start_seconds"] > 0.2
    assert completed["actual_supervisor_wall_seconds"] < completed["watchdog_wall_seconds_reserved_at_lease"]
    assert completed["accuracy_pass"] is False
    assert completed["accuracy_classification"] == "solver_or_recovery_gate_not_passed_comparison_held"
    final = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert final["stages"]["Q4_ORIGINAL"]["attempts"][0] == preserved_q4
    assert final["stages"]["V5_POSTPROCESS"]["attempts"][0] == preserved_post
    assert final["stages"]["V5_POSTPROCESS"]["attempts"][1]["status"] == "POSTPROCESS_PARENT_FAILED"
    assert final["stages"]["V5_POSTPROCESS"]["attempts"][1]["pre_settlement_result_sha256"] == failed_sha
    assert final["stages"]["V5_POSTPROCESS"]["attempts"][2]["replay"] is True
    assert final["stages"]["V5_POSTPROCESS"]["attempts"][2]["implementation_bug_replay"]["authorization_id"] == launcher.TASK40_V6_AUTHORIZATION_ID
    final_post_attempt = final["stages"]["V5_POSTPROCESS"]["attempts"][2]
    assert final_post_attempt["settled_seconds"] == pytest.approx(
        final_post_attempt["settled_interval"]["budget_seconds"]
        + final_post_attempt["settlement_finalization_interval"]["budget_seconds"]
    )
    assert final_post_attempt["conservative_clock_charge_seconds"] == pytest.approx(
        final_post_attempt["settled_seconds"]
    )
    assert final_post_attempt["actual_elapsed_seconds"] == pytest.approx(
        final_post_attempt["actual_elapsed_monotonic_seconds"]
    )
    assert final_post_attempt["actual_elapsed_boottime_seconds"] >= 0.0
    assert final["unique_bug_replay_count"] == 1
    assert final["elapsed_seconds"] + final["conservative_allowance_seconds"] < TASK40_GX784_WORKFLOW_BUDGET_SECONDS
