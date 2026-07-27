from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path

from benchmarks.task035d_nested_p_dwr_checker import (
    _expected_inventory,
    task035d_nested_p_dwr_report_gate,
)


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_PATH = (
    ROOT
    / "benchmarks"
    / "cases"
    / "095_high_order_local_hp_resource_envelope"
    / "records"
    / "significant_channel_reference_v1.json"
)


def _residual_gate() -> dict:
    return {
        "schema_version": "task035d.primal-residual-gate.v1",
        "pass": True,
        "reduced_trace_dtn_relative_residual": 1.0e-12,
        "full_explicit_true_relative_residual": 2.0e-12,
    }


def _port_audit() -> dict:
    return {
        "schema_version": (
            "task035d.variable-p-trace-only-port-operator.v1"
        ),
        "pass": True,
        "checks": {
            "trace_only": True,
            "content_hashes": True,
        },
        "trace_functional_count": 25,
        "removed_active_interior_over_threshold_max": 0.5,
        "acceptance_threshold_max_abs": 5.0e-12,
        "auxiliary_interior_columns_allocated": False,
        "interior_degree_may_affect_port_operator": False,
        "external_operator_content_sha256": "a" * 64,
        "external_rhs_content_sha256": "b" * 64,
        "content_identity_is_partition_bound": True,
        "content_identity_requires_same_mpi_ownership": True,
    }


def _passing_fixture(authority: dict) -> dict:
    channels, goal_labels = _expected_inventory(authority)
    goal_metadata = {}
    for row in authority["channels"]:
        channel = row["channel"]
        for quantity in (
            "power",
            "amplitude_real",
            "amplitude_imag",
        ):
            label = (
                f"{'R' if channel['side'] == 'top' else 'T'}_"
                f"m{int(channel['m'])}_n{int(channel['n'])}_"
                f"{channel['polarization']}_{quantity}"
            )
            goal_metadata[label] = {
                "side": channel["side"],
                "m": int(channel["m"]),
                "n": int(channel["n"]),
                "polarization": channel["polarization"],
                "quantity": quantity,
                "label": label,
            }
    zero_cells = [
        {
            "canonical_leaf": leaf,
            "complex_pairing": [0.0, 0.0],
        }
        for leaf in range(134)
    ]
    goals = {
        label: {
            "pass": True,
            "goal": goal_metadata[label],
            "value_a": 0.0,
            "value_b": 0.0,
            "actual_goal_delta_a_minus_b": 0.0,
            "signed_dwr_estimate": 0.0,
            "signed_goal_closure_error": 0.0,
            "goal_closure_limit": (
                8.0 * 512.0 * math.ulp(1.0)
            ),
            "unit_adjoint_residual_error_bound": 0.0,
            "unexplained_residual_pairing_bound": 0.0,
            "unexplained_residual_complex_pairing": [0.0, 0.0],
            "unit_adjoint_goal_scalar": [1.0, 0.0],
            "global_complex_pairing": [0.0, 0.0],
            "components": {
                "cell_total": {"complex_pairing": [0.0, 0.0]}
            },
            "cell_contributions": zero_cells,
        }
        for label in goal_labels
    }
    basis_channels = {
        label: {
            "pass": True,
            "adjoint_residual": {
                "relative_residual": 1.0e-12,
                "residual_norm": 0.0,
            },
        }
        for label in channels
    }
    basis_goals = {
        label: {
            "pass": True,
            "scaled_adjoint_residual": {
                "relative_residual": 2.0e-12
            },
        }
        for label in goal_labels
    }
    cell_records = [
        {
            "canonical_leaf": leaf,
            "interior_degree_changed": leaf < 32,
            "identity_checks": {"same_trace": True},
            "unchanged_cell_zero_delta_pass": True,
        }
        for leaf in range(134)
    ]
    port_a = _port_audit()
    port_b = deepcopy(port_a)
    return {
        "schema_version": "task035d.variable-p-nested-live-dwr.v1",
        "pass": True,
        "controlled_negative": False,
        "significant_channel_authority": {
            "selected_goal_set_complete_by_frozen_authority": True
        },
        "primal_endpoints": {
            "coarse_residual_gate": _residual_gate(),
            "enriched_residual_gate": _residual_gate(),
            "state_delta_l2_norm": 0.0,
        },
        "residual_partition": {
            "pass": True,
            "effective_residual_l2_norm": 0.0,
            "component_residual_l2_norm_sum": 0.0,
            "component_l2_norms": {
                "coarse_solver_residual": 0.0,
                "cell_total": 0.0,
                "port": 0.0,
                "auxiliary": 0.0,
                "enriched_solver_correction": 0.0,
            },
            "unexplained_residual_l2_norm": 0.0,
            "unexplained_residual_relative": 0.0,
            "unexplained_residual_limit": 5.0e-12,
            "unexplained_residual_added_back_as_component": False,
        },
        "external_partition": {
            "zero_delta_derived_from_independent_port_identity": True,
            "coarse_port_operator_audit": port_b,
            "enriched_port_operator_audit": port_a,
            "direct_rhs_a_minus_b_l2_norm": 0.0,
            "rhs_a_l2_norm": 0.0,
            "rhs_b_l2_norm": 0.0,
            "direct_rhs_a_minus_b_scale": 1.0e-30,
            "direct_rhs_a_minus_b_limit": 5.0e-12,
            "port_l2_norm": 0.0,
            "auxiliary_l2_norm": 0.0,
        },
        "cell_residuals": {
            "global_cell_count": 134,
            "interior_degree_changed_cell_count": 32,
            "dense_schur_persisted": False,
            "records": cell_records,
        },
        "unit_channel_adjoint_basis": {
            "pass": True,
            "channels": basis_channels,
            "goals": basis_goals,
        },
        "goal_dwr": {
            "pass": True,
            "goals": goals,
        },
    }


def test_checker_recomputes_passing_raw_evidence() -> None:
    authority = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    report = _passing_fixture(authority)
    gate = task035d_nested_p_dwr_report_gate(report, authority)
    assert gate["pass"] is True
    assert gate["recomputed_channel_count"] == 12
    assert gate["recomputed_goal_count"] == 36


def test_checker_rejects_stored_pass_with_bad_closure_or_inventory() -> None:
    authority = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    report = _passing_fixture(authority)
    first_label = next(iter(report["goal_dwr"]["goals"]))
    report["goal_dwr"]["goals"][first_label][
        "signed_dwr_estimate"
    ] = 1.0
    closure_gate = task035d_nested_p_dwr_report_gate(
        report,
        authority,
    )
    assert closure_gate["pass"] is False
    assert "all_goal_closures_recomputed" in closure_gate["failures"]

    report = _passing_fixture(authority)
    report["goal_dwr"]["goals"].pop(first_label)
    inventory_gate = task035d_nested_p_dwr_report_gate(
        report,
        authority,
    )
    assert inventory_gate["pass"] is False
    assert "goal_inventory_exact" in inventory_gate["failures"]


def test_checker_rejects_stored_pass_with_unqualified_port_roundoff() -> None:
    authority = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    report = _passing_fixture(authority)
    report["external_partition"]["coarse_port_operator_audit"][
        "removed_active_interior_over_threshold_max"
    ] = 1.01
    gate = task035d_nested_p_dwr_report_gate(report, authority)
    assert gate["pass"] is False
    assert "port_identity_recomputed" in gate["failures"]


def test_checker_recomputes_all_numeric_limits() -> None:
    authority = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))

    report = _passing_fixture(authority)
    first_label = next(iter(report["goal_dwr"]["goals"]))
    report["goal_dwr"]["goals"][first_label][
        "goal_closure_limit"
    ] = 1.0
    goal_gate = task035d_nested_p_dwr_report_gate(
        report,
        authority,
    )
    assert goal_gate["pass"] is False
    assert "all_goal_closures_recomputed" in goal_gate["failures"]

    report = _passing_fixture(authority)
    report["residual_partition"]["unexplained_residual_limit"] = 1.0
    partition_gate = task035d_nested_p_dwr_report_gate(
        report,
        authority,
    )
    assert partition_gate["pass"] is False
    assert (
        "residual_partition_recomputed"
        in partition_gate["failures"]
    )

    report = _passing_fixture(authority)
    report["external_partition"]["direct_rhs_a_minus_b_limit"] = 1.0
    rhs_gate = task035d_nested_p_dwr_report_gate(
        report,
        authority,
    )
    assert rhs_gate["pass"] is False
    assert "port_identity_recomputed" in rhs_gate["failures"]

    report = _passing_fixture(authority)
    report["external_partition"][
        "direct_rhs_a_minus_b_scale"
    ] = 1.0
    report["external_partition"][
        "direct_rhs_a_minus_b_limit"
    ] = 5.0e-12 + 5.0e-11
    joint_rhs_gate = task035d_nested_p_dwr_report_gate(
        report,
        authority,
    )
    assert joint_rhs_gate["pass"] is False
    assert (
        "port_identity_recomputed"
        in joint_rhs_gate["failures"]
    )
