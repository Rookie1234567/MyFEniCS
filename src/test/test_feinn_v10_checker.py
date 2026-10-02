"""Independent negative evidence fixtures; no PDE or optimizer replay."""

from copy import deepcopy
import json
import pytest

from benchmarks.check_task42extra_v10 import (
    benchmark_gates,
    compact_write,
    derivative_gate,
    training,
)
from benchmarks.check_task42extra_v9 import load


def fixture_row():
    metric = {"relative": 0.0}
    return dict(
        c=metric,
        directions=[
            dict(
                JVP=metric,
                VJP=metric,
                real_adjoint=0.0,
                families={key: metric for key in ("edge", "face", "interior")},
            )
            for _ in range(3)
        ],
        K=metric,
        gradient=metric,
        K_symmetry=0.0,
        K_energy_pair=0.0,
        batch={"c": metric, "JVP": metric, "VJP": metric},
        cache_rejection_reuses=True,
        cache_acceptance_invalidates=True,
        buffer_invalidates=True,
        mu_only_reuse=True,
        recovery_rebuilt=True,
        recovery_JVP=metric,
        cache={"resident_bytes": 1024},
        proposal=dict(
            direction=metric,
            pred=metric,
            ared=metric,
            old_seconds=100.0,
            new_seconds=70.0,
        ),
        passed=True,
    )


def test_loss_and_hot_kernel_speed_cannot_promote_failed_equivalence():
    assert derivative_gate(fixture_row(), require_proposal=True)
    for key in ("proposal", "cache_acceptance_invalidates"):
        bad = deepcopy(fixture_row())
        if key == "proposal":
            bad[key]["ared"] = {"relative": 1e-6}
        else:
            bad[key] = False
        with pytest.raises(ValueError, match="DERIVATIVE_SAVED_GATE_DIFFERS"):
            derivative_gate(bad, require_proposal=True)


def test_benchmark_requires_complete_setup_and_all_four_route_medians():
    states = {
        key: fixture_row()
        for key in ("plain_gn", "phase_gn", "plain_fit_gn", "phase_fit_gn")
    }
    result = dict(states={}, samples=[])
    order = [
        (-1, "old_AD"),
        (-1, "cached"),
        (0, "old_AD"),
        (0, "cached"),
        (1, "cached"),
        (1, "old_AD"),
        (2, "old_AD"),
        (2, "cached"),
    ]
    for key in states:
        result["states"][key] = dict(speedup_including_build_release=1.4, passed=True)
        for repeat, kind in order:
            result["samples"].append(
                dict(
                    state=key,
                    repeat=repeat,
                    implementation=kind,
                    warmup=repeat == -1,
                    K_count=16,
                    seed=4211001,
                    cache_bytes=1024,
                    build_seconds=10,
                    gradient_seconds=10,
                    K16_seconds=40,
                    release_seconds=1,
                    total_seconds=98 if kind == "old_AD" else 70,
                )
            )
    assert all(x["passed"] for x in benchmark_gates(states, result).values())
    bad = deepcopy(result)
    bad["samples"][1]["total_seconds"] = 59
    with pytest.raises(ValueError, match="PERFORMANCE_TIMER_SCOPE"):
        benchmark_gates(states, bad)
    bad = deepcopy(result)
    for sample in bad["samples"]:
        if sample["state"] == "phase_gn" and sample["implementation"] == "cached":
            sample["total_seconds"] = 90
    bad["states"]["phase_gn"]["speedup_including_build_release"] = 98 / 90
    with pytest.raises(ValueError, match="PERFORMANCE_SAVED_GATE_DIFFERS"):
        benchmark_gates(states, bad)


def test_actual_frozen_route_rejects_label_and_cumulative_count_corruption():
    item = load("v10_plain_cached_gn")
    value, _ = training(item)
    assert value["new_accepted_outer"] == 14
    for key in ("reference_used_for_training", "cumulative_counts"):
        bad = deepcopy(item)
        if key == "cumulative_counts":
            bad["result"][key]["K"] += 1
        else:
            bad["result"][key] = True
        with pytest.raises(ValueError, match="LABEL_BOUNDARY|COUNTS_NOT_INHERITED"):
            training(bad)


def test_resource_export_keeps_saved_counters_and_unsubmitted_work_distinct():
    value, _ = training(load("v10_phase_resource_freeze"))
    assert value["retained_resource_export"] and value["original_PT_unmodified"]
    assert (
        value["new_accepted_outer"] == 21
        and value["accepted_updates_this_attempt"] == 0
    )
    assert value["saved_boundary_counts"]["K"] == 813
    assert value["counts"]["K"] == 834
    assert value["Gram_factor"] is None and value["Gsolve_count"] is None
    assert value["new_K_after_last_accepted_boundary"] == 21


def test_full_K_histories_cannot_be_duplicated_as_compact_json(tmp_path, monkeypatch):
    import benchmarks.check_task42extra_v10 as checker

    monkeypatch.setattr(checker, "RECORDS", tmp_path)
    compact_write("small.json", {"truth": "NOT_RETAINED"})
    assert json.loads((tmp_path / "small.json").read_text())["truth"] == "NOT_RETAINED"
    with pytest.raises(ValueError, match="COMPACT_JSON_EXCEEDS_200_KIB"):
        compact_write("large.json", {"large": "x" * 205000})
    assert not (tmp_path / "large.json").exists()
