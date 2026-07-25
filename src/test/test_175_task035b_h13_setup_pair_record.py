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
    / "h13_canonical_orientation_symbolic_numeric_cold_warm_mpi8_v1.json"
)


def test_h13_cold_warm_pair_is_setup_authority_not_accuracy_pass() -> None:
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    identity = record["identity"]
    cold = record["cold"]
    warm = record["warm"]
    comparison = record["comparison"]
    decision = record["scope_and_decision"]

    assert record["pass"] is True
    assert record["candidate_promotion"] is False
    assert record["ordinary_default_changed"] is False
    assert record["source"]["execution_source_sha"] == (
        "a20b8b404f66b983596326c912a88fb8be3b255c"
    )
    assert record["source"]["clean_and_stable_for_both_runs"] is True

    assert identity["geometry"] == "Task034 fixed rectangular block grating"
    assert identity["h_nm"] == 13.0
    assert identity["mesh_cells_resolved"] == [6, 2, 12]
    assert identity["mpi_size"] == 8
    assert identity["full3d_equivalent_dofs"] == 89_740
    assert identity["full3d_equivalent_dofs"] <= 90_000
    assert identity["full3d_equivalent_dof_margin"] == 260
    assert identity["active_rows_with_dtn"] == 20_120
    assert identity["matrix_nnz_used"] == 11_014_172
    assert identity["matrix_maximum_nnz_per_row"] == 965
    assert identity["factor_nnz"] == 35_746_600
    assert identity["raw_petsc_options_used"] is False

    for run in (cold, warm):
        assert run["formal_profile_pass"] is True
        assert run["all_profile_checks_pass"] is True
        assert run["physics"]["full_explicit_true_residual"] <= 1.0e-9
        assert run["resource"]["max_process_tree_swap_mb"] == 0.0
        assert run["matrix"]["active_rows"] == 20_120
        assert run["matrix"]["nnz_used"] == 11_014_172
        assert run["matrix"]["factor_nnz"] == 35_746_600
        assert run["mumps"]["event_split_status"] == (
            "measured_symbolic_numeric_split"
        )
        assert run["canonical_orientation"][
            "trace_interior_block_diagonal_proven"
        ] is True
        assert run["canonical_orientation"][
            "inactive_or_postzero_rows_created"
        ] is False
        assert len(run["artifacts"]) == 6
        assert all(len(item["sha256"]) == 64 for item in run["artifacts"])

    assert cold["cache"]["raw_tensor_misses"] == 6
    assert cold["cache"]["condensed_class_misses"] == 122
    assert warm["cache"]["fixed_trace_element_hit_on_all_ranks"] is True
    assert warm["cache"]["raw_tensor_hits"] == 6
    assert warm["cache"]["condensed_class_hits"] == 130
    assert warm["cache"]["dtn_rank_bundle_hits"] == 8
    assert warm["cache"]["dtn_reduced_bundle_restores"] == 320
    assert comparison["cold_to_warm_non_ksp_speedup"] > 2.8
    assert comparison["cold_non_ksp_at_or_below_30_seconds_pass"] is True
    assert comparison["warm_non_ksp_below_10_seconds_pass"] is True
    assert comparison["cold_warm_rows_nnz_and_factor_nnz_identical"] is True
    assert comparison["max_cold_warm_physics_abs_delta"] < 1.0e-12
    assert comparison["zero_swap_both_runs"] is True
    assert comparison["h13_over_h15_factor_nnz_ratio"] > (
        comparison["h13_over_h15_matrix_nnz_ratio"]
    )

    assert decision["setup_targets_pass"] is True
    assert decision["h13_within_90000_full3d_equivalent_dof_gate"] is True
    assert decision["twelve_of_twelve_gate_claimed"] is False
    assert decision["not_a_12_of_12_candidate"] is True
    assert decision["hybrid_promotion_allowed"] is False
    assert decision["candidate_promotion"] is False
