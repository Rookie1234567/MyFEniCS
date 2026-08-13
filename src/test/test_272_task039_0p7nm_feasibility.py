"""Focused pure-component contracts for the Task39 0.7 nm audit."""

import math
from pathlib import Path

import pytest

from benchmarks.task039_0p7nm_feasibility import (
    _render_markdown,
    build_task039_0p7nm_audit,
)


ROOT = Path(__file__).resolve().parents[2]


def test_task039_0p7nm_air_inventory_and_component_boundaries():
    record = build_task039_0p7nm_audit(ROOT, source_sha="a" * 40)
    air = record["air_side_inventory"]
    assert air["count"] == 16030
    assert air["spatial_count"] == 8015
    assert air["polarization_counts"] == {"top": {"P": 8015, "S": 8015}}
    assert air["rayleigh_warning_count"] == 0
    assert air["near_cutoff_status"] == "not_separately_defined_by_authority"
    assert air["nonpropagating_count"] == 0
    assert "spatial_mn" not in air
    assert air["m_bounds"] == [-141, 1]
    assert air["n_bounds"] == [-35, 35]
    assert air["zero_order_retained"] is True
    assert air["key_sha256"] == (
        "28cf61cebf8656b207a5128cc98dda4e0bfcaad4cdb1fe1b784b33bcacd14e4d"
    )
    assert air["material_status"] == "0P7NM_MATERIAL_INPUT_INCOMPLETE"
    assert air["full_pde_allowed"] is False
    assert air["full_pde_error"] == "0P7NM_MATERIAL_INPUT_INCOMPLETE"

    scenario_a = record["fe_scenarios"]["A_accuracy_qualified_h_over_lambda"]
    assert scenario_a["status"] == "not_instantiated"
    assert scenario_a["estimates"] == "insufficient_fit_points"

    scenario_b = record["fe_scenarios"]["B_p6_h1"]
    assert scenario_b["measured_fit_points"] == 1
    assert scenario_b["cells"] == 252000
    assert scenario_b["full_fe_dofs"] == 173802000
    assert scenario_b["global_active_trace_rows"] == 51192000
    assert scenario_b["endcap_surface_trace_rows_per_side"] == 842400
    assert scenario_b["budget"]["factor_lower_exceeds_256_gib"] is True
    assert scenario_b["factor_nnz_range"] == [217041864000, 2170418640000]
    assert scenario_b["budget"]["global_W_exceeds_effective_hard_stop"] is True
    assert (
        scenario_b["external"]["hybrid_known_air_endcap_W_bytes_lower_bound"]
        == scenario_b["external"]["hybrid_endcap_per_side"]["W_bytes_complex128"]
    )
    assert (
        scenario_b["external"][
            "hybrid_known_air_endcap_if_substrate_equal_air_example_bytes"
        ]
        == 2 * (scenario_b["external"]["hybrid_endcap_per_side"]["W_bytes_complex128"])
    )
    assert scenario_b["external"]["global_trace"]["W_GiB_complex128"] > 12000
    assert scenario_b["external"]["hybrid_endcap_per_side"]["W_GiB_complex128"] > 200
    endcap = scenario_b["external"]["hybrid_endcap_per_side"]
    assert endcap["O_N3_time_relative_to_604_channels"] == pytest.approx(
        18693.4625, rel=1e-6
    )
    assert endcap["K_factor_time_seconds"]["status"] == "not_established"
    two_side = scenario_b["external"]["hybrid_two_endcap_W_status"]
    assert two_side["authority"] == "not_established"
    assert two_side["status"] == "pending_substrate_material"
    assert two_side["conditional_equal_air_example_bytes"] == 432117504000
    assert two_side["classification"] == "conditional_example_not_authority"
    resident = scenario_b["external"][
        "hybrid_known_air_endcap_resident_W_plus_K_LU_GiB_range"
    ]
    assert resident[0] == pytest.approx(205.049, abs=0.01)
    assert resident[1] == pytest.approx(208.878, abs=0.01)
    assert (
        resident[0] < record["resource_budget"]["effective_hard_stop_gib"] < resident[1]
    )
    assert (
        scenario_b["external"][
            "hybrid_known_air_endcap_upper_exceeds_effective_hard_stop"
        ]
        is True
    )

    names = set(record["classification"])
    assert {
        "0P7NM_MATERIAL_INPUT_INCOMPLETE",
        "0P7NM_FE_FACTOR_OR_CACHE_EXCEEDS_256GIB_BUDGET",
        "0P7NM_REQUIRES_EXTERNAL_DTN_WOODBURY_REDESIGN",
        "0P7NM_REQUIRES_INTERNAL_MODAL_SCHUR_REDESIGN",
        "0P7NM_CONVERGENCE_RISK_UNRESOLVED",
    } <= names
    assert record["production_validation_allowed"] is False
    assert record["full_pde"]["launch_error"] == "0P7NM_MATERIAL_INPUT_INCOMPLETE"
    assert record["evidence_boundary"]["ignored_raw_read"] is False
    accepted = record["internal_modal_models"]["accepted_13p5_M120_models"]
    lower_bound = record["internal_modal_models"]["failed_5nm_M960_lower_bound_models"]
    assert accepted["M_proportional_to_1_over_lambda"]["seed_M"] == 120
    assert lower_bound["M_proportional_to_1_over_lambda"]["seed_M"] == 960
    assert lower_bound["M_proportional_to_1_over_lambda"]["seed_label"].endswith(
        "lower_bound_only"
    )
    accepted_row = accepted["M_proportional_to_1_over_lambda"]
    assert accepted_row["basis_bytes_estimate"] == math.ceil(
        accepted_row["anchor_basis_bytes_M480_h10"]
        * (accepted_row["M_estimate"] / 480)
        * accepted_row["h1_surface_scale_h_minus_2"]
    )
    assert accepted_row["h1_surface_scale_h_minus_2"] == 100
    assert "h1 engineering estimate" in accepted_row["scaling_assumption"]
    assert record["convergence"]["accepted_13p5"]["iterations_min"] == 1771
    assert record["convergence"]["accepted_13p5"]["iterations_max"] == 3945
    detail = record["external_dtn_woodbury"]["classification_detail"]
    assert detail["full3d_global_W"]["classification"] == (
        "illustrative_not_hybrid_authority"
    )
    assert detail["hybrid_two_endcap_W"]["classification"].endswith("REDESIGN")
    assert detail["hybrid_two_endcap_W"]["status"] == "pending_substrate_material"
    assert detail["hybrid_two_endcap_W"]["conservative_upper_below_hard_stop"] is False
    markdown = _render_markdown(record)
    assert "18,693" in markdown
    assert "not_established" in markdown
    assert "402.44" in markdown
    assert "conditional" in markdown


def test_task039_0p7nm_does_not_claim_a_plausible_current_architecture():
    record = build_task039_0p7nm_audit(ROOT, source_sha="b" * 40)
    assert "CURRENT_ARCHITECTURE_PLAUSIBLE" not in set(record["classification"])
    assert record["internal_modal_models"]["five_nm_M_robust_h10"] == "not_established"
    assert record["internal_modal_models"]["M960_status"].startswith("failed")
    assert record["convergence"]["hybrid_iterative_task39"]["status"] == "not_run"
    assert record["convergence"]["0p7nm_iteration_range"] == "unbounded/not_established"
