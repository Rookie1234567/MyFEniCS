"""Contract tests for the Task035b h15 thread/memory evidence audit."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RECORD = (
    ROOT
    / "benchmarks"
    / "cases"
    / "095_high_order_local_hp_resource_envelope"
    / "records"
    / "h15_solve_thread_memory_semantics_audit_v1.json"
)


def _record() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_audit_is_hash_bound_without_rerunning_or_promoting_a_candidate() -> None:
    record = _record()
    authority = record["authority"]
    sources = authority["evidence_sources"]

    assert record["pass"] is True
    assert record["heavy_pde_rerun"] is False
    assert record["candidate_promotion"] is False
    assert record["ordinary_default_changed"] is False
    assert len(authority["formal_run_commit_sha"]) == 40
    assert [source["mpi_size"] for source in sources] == [1, 2, 4, 8]
    for source in sources:
        for field in ("watchdog", "timeline", "worker_result"):
            evidence = source[field]
            assert evidence["path"].startswith("benchmarks/artifacts/task035b/")
            assert len(evidence["sha256"]) == 64


def test_ksp_threads_are_distinct_from_the_large_postprocess_pool() -> None:
    record = _record()
    rows = record["measurements"]

    assert [
        row["worker_rank_threads_during_ksp_max"] for row in rows
    ] == [3, 6, 12, 24]
    assert [
        row["process_tree_threads_during_ksp_max"] for row in rows
    ] == [6, 9, 15, 27]
    assert [
        row["worker_rank_threads_overall_max"] for row in rows
    ] == [3, 6, 200, 400]
    assert [
        row["large_postprocess_pool_observed"] for row in rows
    ] == [False, False, True, True]

    for row in rows[2:]:
        pool = row["large_pool_first_sample"]
        state = row["large_pool_per_rank_thread_state"]
        assert pool["threads_per_rank"] == 50
        assert state["futex_do_wait"] == 47
        assert pool["worker_rank_cpu_core_equivalents"] < (
            row["worker_rank_threads_overall_max"]
        )

    attribution = record["thread_attribution"]
    assert attribution["mumps_or_blas_extra_worker_pool_observed_during_ksp"] is False
    assert attribution["exact_native_thread_owner_proven"] is False
    assert "most recent progress event" in attribution["sticky_stage_caveat"]


def test_memory_metrics_keep_their_scopes_and_do_not_create_a_false_floor() -> None:
    record = _record()
    rows = record["measurements"]

    for row in rows:
        factor = row["factor_peak"]
        assert factor["stage"] == "after_ksp_solve"
        assert factor["process_tree_rss_mb"] > row[
            "postprocess_max_process_tree_rss_mb"
        ]
        assert factor["process_tree_rss_mb"] > factor[
            "worker_rank_pss_sum_mb"
        ]
        assert factor["worker_rank_pss_sum_mb"] >= factor[
            "worker_rank_uss_sum_mb"
        ]
        assert row["max_process_tree_swap_mb"] == 0.0
        assert row["cgroup"]["path"] == "/init.scope"
        assert row["cgroup"]["dedicated_job_cgroup"] is False
        assert row["native_numpy_ledger_retained_rank_sum_bytes"] < row[
            "native_numpy_ledger_rank_sum_bytes"
        ]
        assert row["recovery_lifecycle_after_rank_sum_bytes"] < row[
            "recovery_lifecycle_before_rank_sum_bytes"
        ]

    interpretation = record["memory_interpretation"]
    assert interpretation[
        "factor_peak_before_large_postprocess_pool_for_all_rank_counts"
    ] is True
    assert interpretation["large_thread_pool_sets_observed_direct_memory_peak"] is False
    assert interpretation["large_thread_pool_memory_contribution_quantified"] is False
    assert interpretation["cgroup_is_job_memory_authority"] is False
    assert interpretation["native_numpy_ledger_is_process_memory"] is False
    assert interpretation["best_observed_direct_memory_point"] == "MPI1"
    assert interpretation[
        "best_observed_is_theoretical_or_software_floor"
    ] is False
    assert interpretation[
        "five_point_eight_to_six_point_four_gib_is_a_floor"
    ] is False


def test_linkage_hypothesis_remains_explicitly_bounded() -> None:
    record = _record()
    linkage = record["current_linkage_cross_check"]
    definitions = record["measurement_definitions"]

    assert linkage["scope"].endswith("not_historical_run_provenance")
    assert linkage["vtk_common_core_dependency_observed"] == "libtbb.so.12"
    assert "libtbb" in linkage["mumps_direct_dependency_not_observed"]
    assert "libgomp" in linkage["mumps_direct_dependency_not_observed"]
    assert "do not prove ownership" in linkage["limitation"]
    assert "not a count of simultaneously active" in definitions[
        "worker_rank_kernel_threads"
    ]
    assert "not a dedicated job cgroup" in definitions["cgroup"]
    assert record["limitations"]
