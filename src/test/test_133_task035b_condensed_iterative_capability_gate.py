"""Tests for the Task035b condensed trace iterative capability gate."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from benchmarks.task035b_condensed_iterative_capability_gate import (
    DEFAULT_OUTPUT,
    ROOT,
    _code_capability,
    _derived_factor_removal_envelope,
    _load_authority,
    _measured_direct_baseline,
    _resolve_output,
    _write_json_exclusive,
    build_capability_gate,
)


def _stopped_capability() -> dict:
    return {
        "petsc_hypre_available": False,
        "public_solver_profile_is_direct_only": True,
        "default_ksp_type": "preonly",
        "default_pc_type": "lu",
        "raw_petsc_option_override_technically_possible": True,
        "raw_override_preserves_correct_iterative_provenance": False,
        "dedicated_condensed_iterative_hook_exists": False,
        "iterative_residual_history_contract_exists": False,
        "factor_free_inventory_contract_exists": False,
        "hypre_preconditioner_available": False,
        "candidate_capability_pass": False,
        "reason": "fixture",
    }


def test_direct_authority_measurements_recompute_exactly() -> None:
    record, _authority = _load_authority(ROOT)
    measured = _measured_direct_baseline(record)

    assert measured["full3d_equivalent_dofs"] == 74_890
    assert measured["active_trace_rows"] == 16_800
    assert measured["dtn_auxiliary_rows"] == 80
    assert measured["matrix_rows"] == 16_880
    assert measured["matrix_nnz_used"] == 9_195_812
    assert measured["matrix_nnz_allocated"] == 9_484_580
    assert measured["matrix_nnz_unneeded"] == 288_768
    assert measured["matrix_mallocs"] == 0
    assert measured["matrix_maximum_row_width"] == 965
    assert measured["factor_solver_type"] == "mumps"
    assert measured["factor_nnz"] == 27_916_600
    assert measured["process_tree_peak_gib"] == pytest.approx(
        5.802860260009766
    )
    assert measured["process_tree_swap_mb"] == 0.0
    assert measured["full_explicit_true_residual"] <= 1.0e-9


def test_factor_removal_envelope_keeps_measured_and_derived_separate() -> None:
    record, _authority = _load_authority(ROOT)
    measured = _measured_direct_baseline(record)
    derived = _derived_factor_removal_envelope(record, measured)

    assert derived["semantics"] == "derived_not_measured"
    assert derived["exact_factor_only_peak_contribution"] is None
    assert derived["factor_storage_estimate_bytes"] == 670_133_448
    assert derived["factor_storage_estimate_gib"] == pytest.approx(
        0.6241104081273079
    )
    assert derived["derived_stage_peak_delta_gib"] == pytest.approx(
        2.8490829467773438
    )
    assert derived["factor_only_peak_reduction_upper_bound_gib"] is None
    assert derived[
        "factor_only_peak_reduction_upper_bound_status"
    ] == "unknown_from_non_simultaneous_stage_maxima"
    assert derived["iterative_peak"] is None
    assert "Neither value is a measured or predicted iterative peak" in derived[
        "upper_bound_warning"
    ]


def test_live_code_capability_distinguishes_default_from_typed_opt_in() -> None:
    capability = _code_capability()
    assert capability["petsc_hypre_available"] is False
    assert capability["public_solver_profile_is_direct_only"] is True
    assert capability["public_solver_profile_semantics"] == (
        "ordinary_default_direct_mumps_with_explicit_research_opt_in"
    )
    assert capability["default_ksp_type"] == "preonly"
    assert capability["default_pc_type"] == "lu"
    assert capability[
        "raw_petsc_option_override_technically_possible"
    ] is True
    assert capability[
        "raw_override_preserves_correct_iterative_provenance"
    ] is False
    assert capability["dedicated_condensed_iterative_hook_exists"] is True
    assert capability["iterative_residual_history_contract_exists"] is True
    assert capability["factor_free_inventory_contract_exists"] is True
    assert capability["typed_explicit_research_opt_in_exists"] is True
    assert (
        capability["typed_profile_name"]
        == "fgmres_dtn_trace_deflation"
    )
    assert capability["selected_profile_requires_hypre"] is False
    assert capability[
        "hypre_unavailable_but_not_required_for_selected_profile"
    ] is True
    assert all(capability["capability_checks"].values())
    assert capability["candidate_capability_pass"] is True


def test_gate_is_valid_controlled_stop_without_iterative_pde() -> None:
    record, authority = _load_authority(ROOT)
    gate = build_capability_gate(
        record=record,
        authority=authority,
        source_identity={"commit_sha": "a" * 40},
        environment_identity={"checks": {"fixture": True}},
        code_capability=_stopped_capability(),
    )

    assert gate["status"] == "capability_stop_not_run"
    assert gate["pass"] is True
    assert gate["classification"] == "controlled_stop_before_iterative_pde"
    assert gate["pde"]["formal_screen_run_count"] == 0
    assert gate["pde"]["mpi8_gmres_started"] is False
    assert gate["pde"]["matrix_reassembled"] is False
    assert gate["pde"]["factorization_started"] is False
    assert gate["future_unique_screen_gate"]["restart"] == 30
    assert gate["future_unique_screen_gate"]["max_iterations"] == 200
    assert gate["future_unique_screen_gate"][
        "minimum_residual_reduction_decades"
    ] == 3.0
    assert gate["future_unique_screen_gate"][
        "ksp_norm_type"
    ] == "unpreconditioned"
    assert gate["future_unique_screen_gate"][
        "terminal_explicit_reduced_system_relative_residual_max"
    ] == 1.0e-3
    assert gate["future_unique_screen_gate"][
        "terminal_explicit_residual_definition"
    ] == "||b_reduced - A_reduced x||_2 / ||b_reduced||_2"
    assert gate["future_unique_screen_gate"][
        "process_tree_peak_gib_max"
    ] == 5.2
    assert gate["future_unique_screen_gate"][
        "factor_matrix_must_not_exist"
    ] is True
    assert gate["qualification"]["evidence_valid"] is True
    assert gate["qualification"]["iterative_capability_pass"] is False
    assert gate["qualification"]["formal_iterative_screen_pass"] is False
    assert gate["qualification"]["iterative_candidate"] is False
    assert gate["decision"]["ordinary_default_changed"] is False


def test_direct_authority_row_drift_fails_closed() -> None:
    record, _authority = _load_authority(ROOT)
    drifted = copy.deepcopy(record)
    drifted["candidate"]["matrix_stats"]["matrix_rows"] += 1
    with pytest.raises(ValueError, match="rows do not close"):
        _measured_direct_baseline(drifted)


def test_output_is_exclusive_and_case095_scoped(tmp_path: Path) -> None:
    resolved = _resolve_output(DEFAULT_OUTPUT)
    assert resolved.name == "condensed_trace_iterative_capability_gate.json"
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
