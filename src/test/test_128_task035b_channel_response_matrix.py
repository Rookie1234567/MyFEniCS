"""Tests for the Task035b 12-channel response-direction postprocessor."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

import benchmarks.task035b_channel_response_matrix as response_module
from benchmarks.task035b_channel_response_matrix import (
    DEFAULT_AUTHORITIES,
    EXPECTED_BRANCH,
    LANE_ORDER,
    ROOT,
    SOURCE_FILES,
    _load_authorities,
    _validated_source,
    build_channel_response_evidence,
    main,
)
from src.adaptivity.channel_response_matrix import (
    normalized_error_vector,
    reference_channel_contract,
    topology_resource_row,
)


def _qualified_source() -> dict[str, object]:
    sha = "a" * 40
    return {
        "commit_sha": sha,
        "verified_clean_sha": sha,
        "branch": EXPECTED_BRANCH,
        "tracked_source_dirty": False,
        "stable_and_clean_before": True,
        "status_before": "",
        "head_after_sha": sha,
        "branch_after": EXPECTED_BRANCH,
        "status_after_before_record_write": "",
        "stable_and_clean_after": True,
        "checks": {
            "fixture_before": True,
            "fixture_after": True,
        },
    }


def _source_hashes() -> dict[str, str]:
    return {path: "b" * 64 for path in SOURCE_FILES}


@pytest.fixture(scope="module")
def actual_authorities():
    return _load_authorities(ROOT, DEFAULT_AUTHORITIES)


@pytest.fixture(scope="module")
def actual_evidence(actual_authorities):
    authorities, manifest = actual_authorities
    return build_channel_response_evidence(
        authorities=authorities,
        authority_manifest=manifest,
        source=_qualified_source(),
        source_file_sha256=_source_hashes(),
    )


def test_actual_response_matrix_is_complete_and_finite(actual_evidence):
    evidence = actual_evidence
    assert evidence["pass"] is True
    assert evidence["execution_contract"] == {
        "pure_postprocess": True,
        "pde_solve_count": 0,
        "mesh_build_count": 0,
        "matrix_assembly_count": 0,
        "factorization_count": 0,
        "mpi_launch_count": 0,
        "ordinary_default_changed": False,
        "thresholds_relaxed": False,
        "irregular_geometry_run": False,
        "formal_candidate_eligible": False,
    }
    analysis = evidence["response_analysis"]
    assert len(analysis["channel_order"]) == 12
    assert analysis["error_matrix"]["lane_order"] == [
        "fixed_h15_seed",
        *LANE_ORDER,
    ]
    assert len(analysis["error_matrix"]["power_signed_12_by_lane"]) == 12
    assert all(
        len(row) == 6
        for row in analysis["error_matrix"]["power_signed_12_by_lane"]
    )
    assert len(
        analysis["seed_relative_response_matrix"][
            "complex_signed_12_by_lane"
        ]
    ) == 12
    assert analysis["seed_metrics"]["power_pass_count_recomputed"] == 6
    assert (
        analysis["seed_metrics"][
            "complex_amplitude_pass_count_recomputed"
        ]
        == 7
    )
    power_svd = analysis["directionality"]["power_response_svd"]
    amplitude_svd = analysis["directionality"][
        "complex_amplitude_response_svd"
    ]
    assert power_svd["matrix_shape"] == [12, 5]
    assert amplitude_svd["matrix_shape"] == [12, 5]
    assert len(power_svd["singular_values"]) == 5
    assert len(amplitude_svd["singular_values"]) == 5
    restricted = analysis["z_h13_remaining_failure_subspace"]
    assert restricted["selected_channel_labels"] == [
        "T(-4,0)_s",
        "R(-5,0)_s",
        "R(-4,0)_s",
    ]
    assert restricted["effective_rank"] == {
        "power_at_95_percent_energy": 1,
        "power_at_99_percent_energy": 2,
        "complex_at_95_percent_energy": 2,
        "complex_at_99_percent_energy": 3,
    }


def test_actual_findings_separate_positive_and_negative_lanes(
    actual_evidence,
):
    findings = actual_evidence["findings"]
    assert findings[
        "best_measured_individual_lane_by_joint_normalized_l2"
    ] == "z_h13"
    assert findings["worthwhile_individual_followups"] == [
        "z_h14",
        "z_h13",
    ]
    assert set(findings["unsupported_or_negligible_individual_lanes"]) == {
        "x_only",
        "y_only",
        "dtn_buffer1",
    }
    assert findings["worthwhile_linearized_pair_discriminators"] == []
    assert findings["z_h13_remaining_failure_subspace_conclusion"][
        "power_effectively_low_rank_at_99_percent"
    ] is True
    assert findings["z_h13_remaining_failure_subspace_conclusion"][
        "complex_effectively_low_rank_at_99_percent"
    ] is False
    assert findings["z_h13_pair_projection_conclusion"][
        "any_supported_pair"
    ] is False
    assert len(findings["unsupported_or_noncomposable_pairs"]) == 10
    metrics = {
        row["lane"]: row
        for row in actual_evidence["response_analysis"]["lane_metrics"]
    }
    assert metrics["z_h13"]["power_pass_count_recomputed"] == 10
    assert metrics["z_h13"][
        "complex_amplitude_pass_count_recomputed"
    ] == 10
    assert metrics["x_only"]["classification"] == (
        "not_supported_as_standalone_lane"
    )
    assert metrics["y_only"][
        "power_response_alignment_to_ideal_correction"
    ]["value"] < 0.0
    assert metrics["dtn_buffer1"]["classification"] == "not_worth_repeat"


def test_topology_resource_marginals_use_measured_authorities(
    actual_evidence,
):
    rows = {
        row["lane"]: row
        for row in actual_evidence[
            "topology_rows_nnz_factor_peak_marginals"
        ]
    }
    assert rows["fixed_h15_seed"]["active_rows"] == 16880
    assert rows["fixed_h15_seed"]["matrix_nnz_used"] == 9195812
    assert rows["fixed_h15_seed"]["factor_nnz"] == 27916600
    assert rows["z_h13"]["axis_cells"] == [6, 2, 12]
    assert rows["z_h13"]["full3d_equivalent_dofs"] == 89740
    assert rows["z_h13"]["full3d_equivalent_dof_headroom"] == 260
    assert rows["z_h13"]["within_full3d_equivalent_dof_limit"] is True
    assert rows["x_only"]["axis_cells"] == [7, 2, 10]
    assert rows["y_only"]["axis_cells"] == [6, 3, 10]
    assert rows["dtn_buffer1"]["active_rows"] == 17140
    assert rows["y_only"]["marginal_to_fixed_h15_seed"][
        "peak_directly_comparable"
    ] is False
    assert rows["z_h14"]["marginal_to_fixed_h15_seed"][
        "peak_directly_comparable"
    ] is True


def test_nonfinite_channel_input_fails_closed(actual_authorities):
    authorities, _ = actual_authorities
    contract = reference_channel_contract(
        authorities["significant_reference_v1"]
    )
    channels = copy.deepcopy(
        authorities["z_h14"]["diffraction_channel_comparison"]["channels"]
    )
    channels[0]["candidate_power_ratio"] = float("nan")
    with pytest.raises(ValueError, match="must be finite"):
        normalized_error_vector(contract, channels, lane="nan_lane")


def test_missing_factor_inventory_fails_closed(actual_authorities):
    authorities, _ = actual_authorities
    record = copy.deepcopy(authorities["z_h14"])
    record["candidate"]["stage4_dtn_factor_inventory"] = None
    with pytest.raises(ValueError, match="factor inventory"):
        topology_resource_row(
            lane="broken",
            record=record,
            result_field="candidate",
            seed_row=None,
        )


def test_authority_sha_mismatch_fails_before_analysis():
    definitions = {
        name: dict(definition)
        for name, definition in DEFAULT_AUTHORITIES.items()
    }
    definitions["z_h14"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="z_h14 SHA256 mismatch"):
        _load_authorities(ROOT, definitions)


def test_source_identity_fails_closed_on_wrong_branch():
    source = _qualified_source()
    source["branch"] = "master"
    with pytest.raises(ValueError, match="source identity is unqualified"):
        _validated_source(source)


def test_cli_uses_exclusive_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source_before = _qualified_source()
    for key in (
        "head_after_sha",
        "branch_after",
        "status_after_before_record_write",
        "stable_and_clean_after",
    ):
        source_before.pop(key)
    source_before["checks"] = {"fixture_before": True}
    source_after = {
        "head_after_sha": source_before["commit_sha"],
        "branch_after": EXPECTED_BRANCH,
        "status_after_before_record_write": "",
        "stable_and_clean_after": True,
        "checks": {"fixture_after": True},
    }
    monkeypatch.setattr(
        response_module,
        "_verified_source_identity",
        lambda _root, _sha: dict(source_before),
    )
    reverify_calls = 0

    def reverify(_root, _source):
        nonlocal reverify_calls
        reverify_calls += 1
        return dict(source_after)

    monkeypatch.setattr(
        response_module,
        "_reverify_source_before_write",
        reverify,
    )
    monkeypatch.setattr(
        response_module,
        "_source_file_sha256",
        lambda _root: _source_hashes(),
    )
    output = tmp_path / "response.json"
    arguments = [
        "--verified-clean-sha",
        "a" * 40,
        "--output",
        str(output),
    ]
    assert main(arguments) == 0
    assert reverify_calls == 2
    original_sha = hashlib.sha256(output.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        main(arguments)
    assert reverify_calls == 4
    assert hashlib.sha256(output.read_bytes()).hexdigest() == original_sha
