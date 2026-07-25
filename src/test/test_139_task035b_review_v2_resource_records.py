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


def test_rank_partition_warm_cache_negative_is_preserved() -> None:
    record = _record(
        "h15_condensed_cache_rank_partition_controlled_negative_v1.json"
    )
    cold = record["cold"]
    warm = record["warm"]
    root_cause = record["root_cause"]

    assert record["pass"] is False
    assert cold["status"].endswith("_pass")
    assert warm["status"] == "controlled_negative_direct_setup_profile"
    assert warm["official_physics_result"] is True
    assert warm["full_explicit_true_residual"] <= 1.0e-9
    assert warm["raw_tensor_cache_hits"] == 6
    assert warm["condensed_class_cache_hits"] == 4
    assert warm["condensed_class_constructions"] == 110
    assert warm["warm_heap_trim"]["succeeded_on_all_ranks"] is True
    assert warm["warm_heap_trim"]["sum_rss_released_mb"] > 1300.0
    assert record["comparison"]["projection_alias_memory_defect_fixed"] is True
    assert record["comparison"]["warm_build_10_second_preferred_target_pass"] is False
    assert root_cause["cold_condensed_manifest_count"] == 110
    assert root_cause["rank_independent_logical_identity_count"] == 106
    assert root_cause["logical_identities_present_on_two_cold_ranks"] == 4
    assert record["decision"]["historical_artifacts_deleted"] is False
    assert record["decision"]["candidate_promotion"] is False
    assert record["ordinary_default_changed"] is False


def test_rank_independent_warm_cache_reuses_every_condensed_class() -> None:
    record = _record(
        "h15_condensed_cache_rank_independent_cold_warm_mpi8_v2.json"
    )
    cold = record["cold"]
    warm = record["warm"]
    comparison = record["comparison"]

    assert record["pass"] is True
    assert cold["formal_profile_pass"] is True
    assert warm["formal_profile_pass"] is True
    assert cold["same_job_cross_rank_reuse_count"] == 4
    assert cold["condensed_class_constructions"] == 106
    assert cold["unique_condensed_manifests"] == 106
    assert warm["raw_tensor_cache_hits"] == 6
    assert warm["raw_tensor_cache_misses"] == 0
    assert warm["condensed_class_cache_hits"] == 110
    assert warm["condensed_class_cache_misses"] == 0
    assert warm["condensed_class_constructions"] == 0
    assert warm["projection_alias_restore_count"] == 110
    assert cold["full_explicit_true_residual"] <= 1.0e-9
    assert warm["full_explicit_true_residual"] <= 1.0e-9
    assert comparison["warm_all_condensed_classes_hit_without_recompute"]
    assert comparison["cold_build_25_to_30_second_preferred_target_pass"]
    assert comparison["cold_to_warm_build_speedup"] >= 2.0
    assert comparison["warm_build_10_second_preferred_target_pass"] is False
    assert 0.0 < comparison["warm_build_preferred_target_miss_seconds"] < 0.1
    assert comparison["zero_swap_both_runs"] is True
    assert record["decision"]["historical_rank_partition_negative_preserved"]
    assert record["decision"]["candidate_promotion"] is False
    assert record["ordinary_default_changed"] is False


def test_canonical_orientation_pair_is_setup_authority_not_accuracy_pass() -> None:
    record = _record(
        "h15_canonical_orientation_symbolic_numeric_cold_warm_mpi8_v1.json"
    )
    identity = record["identity"]
    cold = record["cold"]
    warm = record["warm"]
    comparison = record["comparison"]
    decision = record["scope_and_decision"]

    assert record["pass"] is True
    assert record["candidate_promotion"] is False
    assert record["ordinary_default_changed"] is False
    assert record["source"]["commit_sha"] == (
        "ce8ae56ef5732b3bb035d57bebfd66ddf4caccb7"
    )
    assert record["source"]["clean_full_sha_gate"] is True
    assert identity["mpi_size"] == 8
    assert identity["full3d_equivalent_dofs"] == 74890
    assert identity["active_rows_with_dtn"] == 16880
    assert identity["raw_petsc_options_used"] is False

    for run in (cold, warm):
        mumps = run["mumps"]
        assert run["formal_profile_pass"] is True
        assert run["full_explicit_true_residual"] <= 1.0e-9
        assert run["max_process_tree_swap_mb"] == 0.0
        assert mumps["event_split_status"] == "measured_symbolic_numeric_split"
        assert mumps["symbolic_count_per_rank"] == [1] * 8
        assert mumps["numeric_count_per_rank"] == [1] * 8
        assert mumps["symbolic_seconds_max"] > 0.0
        assert mumps["numeric_seconds_max"] > 0.0
        assert (
            mumps["symbolic_seconds_max"] + mumps["numeric_seconds_max"]
            <= mumps["combined_ksp_setup_wall_seconds"]
        )
        assert len(mumps["collective_rank_payload_sha256"]) == 64
        canonical = run["canonical_orientation"]
        assert canonical["used_set_equals_qualified_set"] is True
        assert canonical["inactive_or_postzero_rows_created"] is False
        assert len(run["artifacts"]) == 4
        assert all(len(item["sha256"]) == 64 for item in run["artifacts"])

    assert cold["cache"]["raw_tensor_misses"] == 6
    assert cold["cache"]["condensed_class_misses"] == 115
    assert warm["cache"]["raw_tensor_hits"] == 6
    assert warm["cache"]["condensed_class_hits"] == 119
    assert warm["cache"]["dtn_rank_bundle_hits"] == 8
    assert comparison["cold_warm_rows_and_nnz_identical"] is True
    assert comparison["cold_non_ksp_2x_target_pass"] is True
    assert comparison["cold_non_ksp_at_or_below_30_seconds_pass"] is True
    assert comparison["warm_non_ksp_below_10_seconds_pass"] is True
    assert comparison["warm_speed_ratio_previous_over_current"] < 1.0
    assert decision["setup_targets_pass"] is True
    assert decision["twelve_of_twelve_gate_claimed"] is False
    assert decision["not_a_12_of_12_candidate"] is True
