"""H1R.1a correctness and contract tests for the single-cell diagnostics."""

from __future__ import annotations

from copy import deepcopy

import pytest

from benchmarks.task033_case090_pde_core import (
    attach_evidence_sha256,
    evidence_sha256_is_valid,
)
from benchmarks.run_task037_extra_h1r import (
    H1R_DIRECT_BACKEND_IDENTITY,
    H1R_DEGREES,
    H1R_PAYLOAD_LIMIT_BYTES,
    P6_DENSE_CLASS_BYTES,
    _parser,
    evaluate_h1r1_qualification,
    run_cell_action_microbenchmark,
)


@pytest.mark.parametrize("degree", [2, 3])
def test_dense_cell_paths_and_rank_one_action_contract(degree: int):
    result = run_cell_action_microbenchmark(
        degree,
        include_rank_one_action=degree == 2,
    )
    current = result["a_current_dense_reassembly"]
    cached = result["b_cached_dense_diagnostic"]

    assert result["material_tags"] == [1, 2]
    assert result["active_cell_tag"] == 1
    element_identity = result["class_identity"]["element"]
    assert element_identity["basix_hash"] > 0
    assert element_identity["basix_family"] == "N1E"
    assert element_identity["basix_map_type"] == "covariantPiola"
    assert current["finite"] is True
    assert cached["finite"] is True
    assert current["deterministic"] is True
    assert cached["deterministic"] is True
    assert current["relative_error_vs_dense_authority"] <= 1.0e-13
    assert cached["relative_error_vs_dense_authority"] <= 1.0e-13
    assert result["a_b_relative_error"] <= 1.0e-13

    expected_apply_count = 1 + result["repeats"]
    assert current["apply_count"] == expected_apply_count
    assert current["tabulation_count"] == expected_apply_count
    assert current["orientation_count"] == expected_apply_count
    assert current["gemv_count"] == expected_apply_count
    assert cached["apply_count"] == expected_apply_count
    assert cached["tabulation_count"] == 1
    assert cached["orientation_count"] == 1
    assert cached["gemv_count"] == expected_apply_count

    assert current["cell_tensor_scratch_count"] == 1
    assert current["cell_tensor_scratch_reused"] is True
    assert current["retained_cell_dense_matrix_count"] == 0
    assert current["exact_class_cached_dense_tensor_count"] == 0
    assert cached["cell_tensor_scratch_count"] == 0
    assert cached["cell_tensor_scratch_reused"] is False
    assert cached["retained_cell_dense_matrix_count"] == 1
    assert cached["exact_class_cached_dense_tensor_count"] == 1

    breakdown_fields = {
        "tabulation_seconds",
        "orientation_seconds",
        "gemv_seconds",
    }
    for path in (current, cached):
        assert set(path["first_apply_breakdown_seconds"]) == breakdown_fields
        assert set(path["median_repeated_breakdown_seconds"]) == breakdown_fields
        assert set(path["setup_breakdown_seconds"]) == {
            "tabulation_seconds",
            "orientation_seconds",
        }
        assert all(
            value >= 0.0
            for value in path["first_apply_breakdown_seconds"].values()
        )
        assert all(
            value >= 0.0
            for value in path["median_repeated_breakdown_seconds"].values()
        )
    assert cached["first_apply_breakdown_seconds"]["tabulation_seconds"] == 0.0
    assert cached["first_apply_breakdown_seconds"]["orientation_seconds"] == 0.0
    assert cached["median_repeated_breakdown_seconds"]["tabulation_seconds"] == 0.0
    assert cached["median_repeated_breakdown_seconds"]["orientation_seconds"] == 0.0
    assert current["touched_bytes_estimate_formula"].startswith(
        "6*tensor_bytes + 2*vector_bytes"
    )
    assert cached["touched_bytes_estimate_formula"].startswith(
        "tensor_bytes + 2*vector_bytes"
    )

    assert cached["diagnostic_only"] is True
    assert cached["h_refinement_scalability"] == "not_claimed"
    assert cached["eligible_for_H2"] is False
    assert current["global_matrix_materialized"] is False
    assert cached["global_matrix_materialized"] is False
    assert current["retained_bytes"] > 0
    assert cached["retained_bytes"] > 0
    assert current["touched_bytes_estimated"] > 0
    assert cached["touched_bytes_estimated"] > 0

    if degree == 2:
        direct = result["c_rank_one_direct_action"]
        assert direct["qualification_scope"] == "single_cell_H1R1_only"
        assert direct["eligible_for_H1R2"] == (
            "not_evaluated_until_p6_gate"
        )
        assert direct["backend_identity"] == (
            "dolfinx.fem.assemble_vector(existing ndarray, rank-one form)"
        )
        assert direct["form_rank"] == 1
        assert direct["coefficient_count"] == 1
        assert direct["kernel_output_local_rows"] == result["nloc"]
        assert direct["output_shape"] == [result["nloc"]]
        assert direct["finite"] is True
        assert direct["deterministic"] is True
        assert direct["relative_error_vs_dense_authority"] <= 1.0e-11
        assert direct["apply_count"] == 1 + result["repeats"]
        assert direct["retained_bytes"] == (
            sum(direct["retained_numeric_payload_components"].values())
        )
        assert direct["retained_payload_per_exact_class_bytes"] == (
            direct["retained_bytes"]
        )
        assert direct["retained_bytes"] < 16 * 1024**2
        assert direct["last_packed_coefficient_bytes"] > 0
        assert direct["per_apply_packed_coefficient_temporary"] is True
        assert direct["dense_cell_tensor_materialized_per_apply"] is False
        assert direct["retained_dense_cell_tensor_count"] == 0
        assert direct["cell_tensor_scratch_count"] == 0
        assert direct["global_matrix_materialized"] is False
        assert direct["ordinary_default_changed"] is False
        assert direct["touched_bytes_estimate_formula"].startswith(
            "coefficient_function_local_array_bytes + output_buffer_bytes + "
        )


def test_p6_dense_class_payload_is_a_contract_only():
    assert P6_DENSE_CLASS_BYTES == 12_446_784
    assert P6_DENSE_CLASS_BYTES < 16 * 1024**2


def _synthetic_h1r1_record():
    nloc_by_degree = {2: 54, 3: 144, 4: 300, 6: 882}
    measurements = []
    for degree in H1R_DEGREES:
        nloc = nloc_by_degree[degree]
        a_seconds = 4.0 if degree == 6 else 1.0
        c_seconds = 0.5 if degree == 6 else 0.1
        measurements.append(
            {
                "degree": degree,
                "nloc": nloc,
                "a_current_dense_reassembly": {
                    "median_repeated_apply_seconds": a_seconds,
                },
                "b_cached_dense_diagnostic": {
                    "diagnostic_only": True,
                    "h_refinement_scalability": "not_claimed",
                    "eligible_for_H2": False,
                    "median_repeated_apply_seconds": 0.01,
                },
                "c_rank_one_direct_action": {
                    "qualification_scope": "single_cell_H1R1_only",
                    "backend_identity": H1R_DIRECT_BACKEND_IDENTITY,
                    "form_rank": 1,
                    "coefficient_count": 1,
                    "apply_count": 1 + 4,
                    "relative_error_vs_dense_authority": 0.0,
                    "finite": True,
                    "deterministic": True,
                    "dense_cell_tensor_materialized_per_apply": False,
                    "retained_dense_cell_tensor_count": 0,
                    "cell_tensor_scratch_count": 0,
                    "global_matrix_materialized": False,
                    "retained_payload_per_exact_class_bytes": 4096,
                    "last_packed_coefficient_shapes": [[nloc]],
                    "last_packed_coefficient_entry_count": nloc,
                    "last_packed_coefficient_bytes": nloc * 16,
                    "per_apply_bounded_temporary_bytes": nloc * 16,
                    "per_apply_packed_coefficient_temporary": True,
                    "ordinary_default_changed": False,
                    "median_repeated_apply_seconds": c_seconds,
                },
            }
        )
    return {
        "schema": "task037_extra_h1r1.raw.v1",
        "source_identity": {
            "source_at_start": {
                "source_commit_full_sha": "a" * 40,
                "tracked_source_dirty": False,
                "source_worktree_dirty": False,
                "nonignored_untracked_paths": [],
                "worktree_status_porcelain": [],
                "git_error": None,
            },
            "source_at_end": {
                "source_commit_full_sha": "a" * 40,
                "tracked_source_dirty": False,
                "source_worktree_dirty": False,
                "nonignored_untracked_paths": [],
                "worktree_status_porcelain": [],
                "git_error": None,
            },
            "stable_clean": True,
        },
        "measurements": measurements,
        "H2_locked": True,
        "MPI1_memory_target_evaluated": False,
    }


def test_h1r1_pure_qualification_pass_and_evidence_hash():
    record = attach_evidence_sha256(_synthetic_h1r1_record())
    result = evaluate_h1r1_qualification(record)
    assert evidence_sha256_is_valid(record)
    assert result["status"] == "pass"
    assert result["pass"] is True
    assert result["degrees_exact"] is True
    assert result["p6_speedup"] == 8.0
    assert result["eligible_for_H1R2"] is True


@pytest.mark.parametrize(
    "mutation",
    (
        "degrees",
        "source_dirty",
        "source_sha",
        "relative_error",
        "finite",
        "deterministic",
        "dense_tensor",
        "retained_dense",
        "scratch",
        "global_matrix",
        "payload",
        "packed_shape",
        "packed_closure",
        "b_diagnostic",
        "backend_identity",
        "form_rank",
        "apply_count",
        "payload_zero",
        "negative_timing",
        "p6_speedup",
    ),
)
def test_h1r1_qualification_rejects_minimal_gate_mutations(mutation: str):
    record = deepcopy(_synthetic_h1r1_record())
    if mutation == "degrees":
        record["measurements"][-1]["degree"] = 5
    elif mutation == "source_dirty":
        record["source_identity"]["stable_clean"] = True
        record["source_identity"]["source_at_start"][
            "source_worktree_dirty"
        ] = True
    elif mutation == "source_sha":
        record["source_identity"]["stable_clean"] = True
        record["source_identity"]["source_at_end"]["source_commit_full_sha"] = (
            "b" * 40
        )
    elif mutation == "relative_error":
        record["measurements"][0]["c_rank_one_direct_action"][
            "relative_error_vs_dense_authority"
        ] = 2.0e-11
    elif mutation == "finite":
        record["measurements"][0]["c_rank_one_direct_action"]["finite"] = False
    elif mutation == "deterministic":
        record["measurements"][0]["c_rank_one_direct_action"][
            "deterministic"
        ] = False
    elif mutation == "dense_tensor":
        record["measurements"][0]["c_rank_one_direct_action"][
            "dense_cell_tensor_materialized_per_apply"
        ] = True
    elif mutation == "retained_dense":
        record["measurements"][0]["c_rank_one_direct_action"][
            "retained_dense_cell_tensor_count"
        ] = 1
    elif mutation == "scratch":
        record["measurements"][0]["c_rank_one_direct_action"][
            "cell_tensor_scratch_count"
        ] = 1
    elif mutation == "global_matrix":
        record["measurements"][0]["c_rank_one_direct_action"][
            "global_matrix_materialized"
        ] = True
    elif mutation == "payload":
        record["measurements"][0]["c_rank_one_direct_action"][
            "retained_payload_per_exact_class_bytes"
        ] = H1R_PAYLOAD_LIMIT_BYTES + 1
    elif mutation == "packed_shape":
        record["measurements"][0]["c_rank_one_direct_action"][
            "last_packed_coefficient_shapes"
        ] = [[1, 54, 54]]
    elif mutation == "packed_closure":
        record["measurements"][0]["c_rank_one_direct_action"][
            "last_packed_coefficient_entry_count"
        ] = 55
    elif mutation == "b_diagnostic":
        record["measurements"][0]["b_cached_dense_diagnostic"][
            "diagnostic_only"
        ] = False
    elif mutation == "backend_identity":
        record["measurements"][0]["c_rank_one_direct_action"][
            "backend_identity"
        ] = "dense fallback"
    elif mutation == "form_rank":
        record["measurements"][0]["c_rank_one_direct_action"]["form_rank"] = 2
    elif mutation == "apply_count":
        record["measurements"][0]["c_rank_one_direct_action"]["apply_count"] = 1
    elif mutation == "payload_zero":
        record["measurements"][0]["c_rank_one_direct_action"][
            "retained_payload_per_exact_class_bytes"
        ] = 0
    elif mutation == "negative_timing":
        record["measurements"][3]["a_current_dense_reassembly"][
            "median_repeated_apply_seconds"
        ] = -4.0
    elif mutation == "p6_speedup":
        record["measurements"][3]["c_rank_one_direct_action"][
            "median_repeated_apply_seconds"
        ] = 1.1
    result = evaluate_h1r1_qualification(record)
    assert result["status"] == "gate_failed"
    assert result["pass"] is False
    assert result["problems"]
    if mutation == "p6_speedup":
        assert record["measurements"][3]["b_cached_dense_diagnostic"][
            "median_repeated_apply_seconds"
        ] < record["measurements"][3]["c_rank_one_direct_action"][
            "median_repeated_apply_seconds"
        ]
        assert result["per_degree_checks"]["6"]["b_checks"][
            "diagnostic_only"
        ] is True
        assert result["per_degree_checks"]["6"][
            "p6_speedup_gate_pass"
        ] is False


def test_h1r1_cli_has_fixed_scope_without_degree_or_repeat_options():
    args = _parser().parse_args(["run", "--output", "/tmp/h1r1.json"])
    assert args.command == "run"
    assert args.output.name == "h1r1.json"
    with pytest.raises(SystemExit):
        _parser().parse_args(
            ["run", "--output", "/tmp/h1r1.json", "--degree", "6"]
        )
    with pytest.raises(SystemExit):
        _parser().parse_args(
            ["run", "--output", "/tmp/h1r1.json", "--repeat", "8"]
        )
