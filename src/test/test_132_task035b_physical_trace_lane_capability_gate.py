"""Tests for the Task035b physical selective-trace capability gate."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from benchmarks.task035b_physical_trace_lane_capability_gate import (
    DEFAULT_OUTPUT,
    ROOT,
    _load_authorities,
    _mesh_budget,
    _recompute_local_algebra,
    _resolve_output,
    _write_json_exclusive,
    build_capability_gate,
)


def _local_algebra() -> dict:
    return {
        "retained_local_dimension": 750,
        "enriched_local_dimension": 882,
        "retained_local_trace_dimension": 300,
        "enriched_local_trace_dimension": 432,
        "missing_local_trace_dimension": 132,
        "edge_block_count": 12,
        "edge_block_dimension": 1,
        "face_block_count": 6,
        "face_block_dimension": 20,
        "recomputed_complement_rank": 132,
        "recomputed_complement_nullity": 0,
        "recomputed_reference_riesz_rank": 132,
        "recomputed_reference_riesz_nullity": 0,
        "rank_nullity_closure_pass": True,
        "reference_entity_riesz_pass": True,
        "physical_mesh_riesz": False,
    }


def _inverse_audit() -> dict:
    return {
        "p6_trace_p5_interior": {
            "dimension": 672,
            "curl_rank": 492,
            "curl_nullity": 180,
            "expected_gradient_dimension": 281,
            "missing_gradient_modes": 101,
            "rank_plus_nullity_closes": True,
            "exact_sequence_pass": False,
            "pde_authorized": False,
        },
        "p6_trace_p4_interior": {
            "dimension": 540,
            "curl_rank": 445,
            "curl_nullity": 95,
            "expected_gradient_dimension": 244,
            "missing_gradient_modes": 149,
            "rank_plus_nullity_closes": True,
            "exact_sequence_pass": False,
            "pde_authorized": False,
        },
    }


def test_sha_bound_authorities_build_a_fail_closed_gate() -> None:
    records, authorities = _load_authorities(ROOT)
    gate = build_capability_gate(
        records=records,
        authority_evidence=authorities,
        source_identity={"commit_sha": "a" * 40},
        environment_identity={"checks": {"fixture": True}},
        local_algebra=_local_algebra(),
        inverse_audit=_inverse_audit(),
    )

    assert gate["status"] == "capability_stop_not_run"
    assert gate["pass"] is True
    assert gate["candidate_count"] == 0
    assert gate["candidate_authorized"] is False
    assert gate["pde_run_count"] == 0
    assert gate["pde_authorized"] is False
    assert gate["ordinary_default_changed"] is False
    assert gate["execution_scope"]["subset_selected"] is False
    assert gate["decision"]["next_pde_authorized"] is False
    assert gate["qualification"]["evidence_valid"] is True


def test_mesh_budgets_are_recomputed_from_structured_entities() -> None:
    records, _authorities = _load_authorities(ROOT)
    h14 = _mesh_budget(records["fixed_h14"])
    h13 = _mesh_budget(records["fixed_h13"])

    assert h14["axis_cells"] == [6, 2, 11]
    assert h14["fixed_dofs"] == 82_315
    assert h14["global_edges"] == 615
    assert h14["global_faces"] == 496
    assert h14["full_trace_increment"] == 10_535
    assert h14["recomputed_global_p6_dofs"] == 92_850
    assert h14["available_headroom"] == 7_685
    assert h14["full_trace_over_limit_by"] == 2_850
    assert h14["full_trace_fits"] is False

    assert h13["axis_cells"] == [6, 2, 12]
    assert h13["fixed_dofs"] == 89_740
    assert h13["global_edges"] == 668
    assert h13["global_faces"] == 540
    assert h13["full_trace_increment"] == 11_468
    assert h13["recomputed_global_p6_dofs"] == 101_208
    assert h13["available_headroom"] == 260
    assert h13["full_trace_over_limit_by"] == 11_208
    assert h13["full_trace_fits"] is False


def test_channel_and_proxy_semantics_do_not_authorize_lane_b() -> None:
    records, authorities = _load_authorities(ROOT)
    gate = build_capability_gate(
        records=records,
        authority_evidence=authorities,
        source_identity={},
        environment_identity={},
        local_algebra=_local_algebra(),
        inverse_audit=_inverse_audit(),
    )
    discriminator = gate["global_h14_discriminator_audit"]
    assert discriminator["scalar_pass"] is True
    assert discriminator["selected_field_interface_pass"] is True
    assert discriminator["significant_power_pass_count"] == 9
    assert discriminator["significant_complex_amplitude_pass_count"] == 12
    assert discriminator["all_12_power_pass"] is False
    assert discriminator["all_12_complex_amplitude_pass"] is True
    assert discriminator["formal_candidate_eligible"] is False
    assert discriminator["selective_trace_lane_physically_supported"] is False

    proxy = gate["h15_adjoint_proxy_audit"]
    assert proxy["goal_count"] == 16
    assert proxy["actual_hermitian_adjoint_solves_available"] is True
    assert proxy["exact_full_dual_recovery_available"] is True
    assert proxy["coefficient_proxy_periodic_components_available"] is True
    assert proxy["actual_enriched_residual_available"] is False
    assert proxy["residual_weighted"] is False
    assert proxy["actual_dwr_indicator"] is False
    assert proxy["lane_b_selection_authorized"] is False


def test_local_complement_and_reference_riesz_are_full_rank() -> None:
    audit = _recompute_local_algebra()
    assert audit["retained_local_dimension"] == 750
    assert audit["enriched_local_dimension"] == 882
    assert audit["missing_local_trace_dimension"] == 132
    assert audit["edge_block_count"] == 12
    assert audit["edge_block_dimension"] == 1
    assert audit["face_block_count"] == 6
    assert audit["face_block_dimension"] == 20
    assert audit["recomputed_complement_rank"] == 132
    assert audit["recomputed_complement_nullity"] == 0
    assert audit["recomputed_reference_riesz_rank"] == 132
    assert audit["recomputed_reference_riesz_nullity"] == 0
    assert audit["rank_nullity_closure_pass"] is True
    assert audit["physical_mesh_riesz"] is False


def test_mesh_budget_rejects_dof_drift() -> None:
    records, _authorities = _load_authorities(ROOT)
    drifted = copy.deepcopy(records["fixed_h14"])
    drifted["candidate"]["num_nedelec_dofs"] += 1
    with pytest.raises(ValueError, match="increment does not close"):
        _mesh_budget(drifted)


def test_missing_authority_evidence_fails_closed() -> None:
    records, authorities = _load_authorities(ROOT)
    incomplete = dict(authorities)
    incomplete.pop("fixed_h13")
    with pytest.raises(
        RuntimeError,
        match="all_authorities_sha_bound",
    ):
        build_capability_gate(
            records=records,
            authority_evidence=incomplete,
            source_identity={},
            environment_identity={},
            local_algebra=_local_algebra(),
            inverse_audit=_inverse_audit(),
        )


def test_local_algebra_drift_fails_closed() -> None:
    records, authorities = _load_authorities(ROOT)
    drifted = _local_algebra()
    drifted["face_block_dimension"] = 21
    with pytest.raises(
        RuntimeError,
        match="local_algebra_matches_sha_bound_authority",
    ):
        build_capability_gate(
            records=records,
            authority_evidence=authorities,
            source_identity={},
            environment_identity={},
            local_algebra=drifted,
            inverse_audit=_inverse_audit(),
        )


def test_output_is_exclusive_and_case095_scoped(tmp_path: Path) -> None:
    resolved = _resolve_output(DEFAULT_OUTPUT)
    assert resolved.name == "physical_trace_lane_capability_gate.json"
    assert "095_high_order_local_hp_resource_envelope/records" in str(
        resolved
    )
    with pytest.raises(ValueError, match="must remain in Case095 records"):
        _resolve_output(tmp_path / "outside.json")

    output = tmp_path / "record.json"
    payload = {"status": "capability_stop_not_run", "pass": True}
    _write_json_exclusive(output, payload)
    assert json.loads(output.read_text(encoding="utf-8")) == payload
    with pytest.raises(FileExistsError):
        _write_json_exclusive(output, payload)
