from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RECORDS = (
    ROOT
    / "benchmarks"
    / "cases"
    / "095_high_order_local_hp_resource_envelope"
    / "records"
)


def _record(name: str) -> dict:
    return json.loads((RECORDS / name).read_text(encoding="utf-8"))


def test_h15_direct_rank_study_establishes_measured_not_theoretical_floor() -> None:
    record = _record("h15_direct_mpi1_2_4_8_resource_floor_v1.json")
    rows = record["measurements"]

    assert record["pass"] is True
    assert record["candidate_promotion"] is False
    assert [row["mpi_size"] for row in rows] == [1, 2, 4, 8]
    assert all(row["status"].endswith("_pass") for row in rows)
    assert all(row["full_explicit_true_residual"] <= 1.0e-9 for row in rows)
    assert all(row["max_process_tree_swap_mb"] == 0.0 for row in rows)
    assert [row["max_process_tree_rss_gib"] for row in rows] == sorted(
        row["max_process_tree_rss_gib"] for row in rows
    )
    interpretation = record["interpretation"]
    assert interpretation["best_observed_direct_memory_point"] == "MPI1"
    assert interpretation["not_claimed_as_theoretical_minimum"] is True
    assert interpretation["mpi8_over_mpi1_rss_ratio"] > 3.6
    assert record["ordinary_default_changed"] is False


def test_h15_warm_cache_preserves_hits_but_fails_resource_target() -> None:
    record = _record("h15_condensed_cache_cold_warm_mpi8_v1.json")
    cold = record["cold"]
    warm = record["warm"]
    comparison = record["comparison"]

    assert record["pass"] is False
    assert cold["condensed_class_cache"]["constructions"] == 110
    assert warm["condensed_class_cache"]["hits"] == 110
    assert warm["condensed_class_cache"]["constructions"] == 0
    assert warm["condensed_class_cache"]["local_schur_seconds"] == 0.0
    assert comparison["cache_numerical_closure_pass"] is True
    assert comparison["cold_build_2x_target_pass"] is True
    assert comparison["cold_build_25_30_second_preferred_target_pass"] is True
    assert comparison["warm_build_10_second_preferred_target_pass"] is False
    assert comparison["warm_memory_target_pass"] is False
    assert warm["max_process_tree_rss_gib"] > cold["max_process_tree_rss_gib"]
    assert record["root_cause"]["warm_minus_cold_projection_unique_mib"] > 497.0
    assert record["decision"]["historical_cache_deleted"] is False
    assert record["ordinary_default_changed"] is False


def test_h15_factor_free_profiles_are_preserved_accuracy_negatives() -> None:
    record = _record("h15_factor_free_iterative_mpi8_v1.json")
    profiles = record["profiles"]

    assert record["pass"] is False
    assert [row["profile"] for row in profiles] == [
        "gmres_jacobi",
        "fgmres_asm_ilu",
    ]
    assert all(row["iterations"] == 200 for row in profiles)
    assert all(row["official_result"] is False for row in profiles)
    assert all(row["R_total"] is None for row in profiles)
    assert all(row["full_recovered_true_residual"] > 0.8 for row in profiles)
    assert all(row["global_direct_factor_nnz"] == 0 for row in profiles)
    assert all(
        row["mumps_symbolic_or_numeric_created"] is False for row in profiles
    )
    assert all(row["max_process_tree_swap_mb"] == 0.0 for row in profiles)
    assert record["decision"]["jacobi_and_asm_ilu_lane_closed"] is True
    assert record["decision"]["matrix_free_not_started"] is True
    assert (
        record["artifact_semantics_caveat"]["historical_files_deleted"] is False
    )
    assert record["ordinary_default_changed"] is False


def test_iterative_failed_output_caveat_disqualifies_stale_port_files() -> None:
    record = _record("condensed_iterative_failed_output_caveat_v1.json")
    runs = record["runs"]

    assert record["status"] == "historical_evidence_caveat"
    assert record["historical_artifacts_retained"] is True
    assert len(runs) == 2
    assert all(row["watchdog_status"].startswith("controlled_negative") for row in runs)
    assert all(row["stale_port_file_semantics"]["official"] is False for row in runs)
    assert all(len(row["watchdog_summary_sha256"]) == 64 for row in runs)
    assert all(len(row["solve_summary_sha256"]) == 64 for row in runs)
    assert all(len(row["port_power_sha256"]) == 64 for row in runs)
    authority = record["authority_rule"]
    assert authority["failed_run_port_power_is_official"] is False
    assert authority["failed_run_complex_amplitudes_are_official"] is False
    assert authority["do_not_use_for_accuracy_or_hybrid_closure"] is True
    corrective = record["corrective_action"]
    assert corrective["new_iterative_exception_type"] == (
        "CondensedIterativeSolveFailure"
    )
    assert corrective["nonconverged_port_files_persisted"] is False
    assert corrective["direct_path_semantics_changed"] is False
    assert record["ordinary_default_changed"] is False
