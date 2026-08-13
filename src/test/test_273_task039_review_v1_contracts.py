from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks.task039_review_v1_contracts import (
    TASK039_M480_PROGRESS_ROWS,
    _identity_sha256,
    _resolved_physics_identity,
    audit_m960_trace,
    check_m480_hybrid_iterative,
    compare_full3d_grid_views,
    diagnose_h_paths,
    mesh_resource_preflight,
)
from benchmarks.task039_memory_telemetry import (
    TASK039_E10_STAGE_ORDER,
    task039_e10_ledger,
)
from benchmarks.run_direct_memory_forensics import _latest_stage
from benchmarks.task037c_robustness import profile_record
from src.io import load_and_resolve
from src.io.input_validation import task039_profile_errors
from src.runners.task039_hybrid_iterative import (
    _RESIDUAL_KEYS,
    make_task039_hybrid_iterative_profile,
)


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("name", "mesh_target_nm"),
    (
        ("p6h7p5", 7.5),
        ("p6h6", 6.0),
        ("p6h5", 5.0),
    ),
)
def test_task039_full3d_direct_grid_profiles_are_finite_and_exact(
    name: str, mesh_target_nm: float
) -> None:
    specification = load_and_resolve(
        ROOT / f"input/official/task039/5nm_{name}_full3d_direct_mpi8.dat"
    )
    assert specification.method["kind"] == "full3d_direct"
    assert specification.execution["mpi_size"] == 8
    assert specification.discretization["mesh_target_nm"] == mesh_target_nm
    assert specification.execution["warning_memory_gib"] == 170.0
    assert specification.execution["terminate_memory_gib"] == 195.0
    assert specification.execution["require_zero_swap"] is True
    assert specification.output["export_canonical_vectors"] is True


def test_task039_grid_budget_rejects_old_limit_and_h10_stays_legacy() -> None:
    grid = load_and_resolve(
        ROOT / "input/official/task039/5nm_p6h5_full3d_direct_mpi8.dat"
    ).as_jsonable()
    grid["execution"]["terminate_memory_gib"] = 220.0
    assert any(
        path == "execution.terminate_memory_gib"
        for path, _message in task039_profile_errors(grid)
    )

    h10 = load_and_resolve(
        ROOT / "input/official/task039/5nm_p6h10_full3d_direct_mpi8.dat"
    ).as_jsonable()
    h10["execution"]["warning_memory_gib"] = 170.0
    assert any(
        path == "execution.warning_memory_gib"
        for path, _message in task039_profile_errors(h10)
    )


@pytest.mark.parametrize("mpi_size", (8, 1))
def test_task039_m480_iterative_solver_only_profiles_are_frozen(mpi_size: int) -> None:
    path = ROOT / (
        "input/official/task039/5nm_p6h10_hybrid_iterative_"
        f"m480_solver_only_mpi{mpi_size}.dat"
    )
    specification = load_and_resolve(path)
    assert task039_profile_errors(specification.as_jsonable()) == []
    assert specification.method["requested_modes_per_direction"] == 480
    assert specification.execution["mpi_size"] == mpi_size
    if mpi_size == 1:
        assert specification.execution["warning_memory_gib"] == 45.0
        assert specification.execution["terminate_memory_gib"] == 48.0
    assert specification.solver["restart"] == 90
    assert specification.solver["max_iterations"] == 6000
    assert specification.solver["relative_tolerance"] == 5.0e-9
    assert specification.solver["initial_guess"] == "zero"


def _mode_keys() -> list[tuple[str, int, int, str]]:
    return [("bottom", index, 0, "s") for index in range(300)] + [
        ("top", index, 0, "s") for index in range(304)
    ]


def _grid_view() -> dict[str, object]:
    keys = _mode_keys()
    return {
        "physical_model_sha256": "a" * 64,
        "physics_except_mesh_identity": "task039-fixed-physics-v1",
        "resolved_physics_identity_sha256": "r" * 64,
        "equation_identity": {
            "geometry": {"domain": "fixed"},
            "materials": {"material": "task39"},
            "incidence": {"wavelength_nm": 5.0, "grazing_deg": 10.0},
            "boundary": {"vertical": "dtn_port"},
            "discretization": {"mesh_target_nm": 10.0, "nedelec_degree": 6},
            "method_equation": {
                "bottom_interface_nm": 10.0,
                "top_interface_nm": 110.0,
                "requested_modes_per_direction": 480,
                "propagation_model": "full3d_uniform_cg",
                "traction_model": "full3d_one_cell_exact_schur",
            },
        },
        "equation_identity_sha256": "e" * 64,
        "method_solver_identity": {
            "method": {"kind": "full3d_direct"},
            "solver": {"linear_solver": "direct"},
        },
        "mode_keys": keys,
        "orders": {
            key: {"power_ratio": 1.0e-4, "outgoing_amplitude": 0.01 + 0j}
            for key in keys
        },
        "observables": {
            "R_total": 0.9,
            "T_total": 0.001,
            "A_balance": 0.099,
            "A_volume": 0.099,
        },
        "closure": 1.0e-8,
        "coordinates": {
            name: np.asarray(values, dtype=np.float64)
            for name, values in {
                "x_nm": [0.0, 1.0],
                "y_nm": [0.0, 1.0],
                "z_nm": [10.0, 30.0, 60.0, 90.0, 110.0],
            }.items()
        },
        "fields": {
            "E_V_per_m": np.ones((5, 2, 2, 3), dtype=np.complex128),
            "H_A_per_m": np.ones((5, 2, 2, 3), dtype=np.complex128) * 2,
        },
    }


def test_task039_grid_comparison_has_exact_modes_and_mandatory_strong_gates() -> None:
    left = _grid_view()
    right = deepcopy(left)
    result = compare_full3d_grid_views(left, right)
    assert result["pass"] is True
    assert result["mode_keys_exact"] is True
    assert result["significant_order_count"] == 604
    assert len(result["significant_rows"]) == 604
    assert result["mandatory_pass"] is True
    assert result["strong_pass"] is True
    assert result["fields"]["E_V_per_m"]["strong_pass"] is True
    assert result["fields"]["E_V_per_m"]["absolute_l2"] == 0.0

    right["orders"][_mode_keys()[0]]["power_ratio"] = 0.001
    failed = compare_full3d_grid_views(left, right)
    assert failed["pass"] is False
    assert failed["order_failures"][0]["key"] == ["bottom", 0, 0, "s"]
    strong_only = deepcopy(left)
    strong_only["observables"]["R_total"] += 5.0e-5
    strong_result = compare_full3d_grid_views(left, strong_only)
    assert strong_result["pass"] is True
    assert strong_result["observables"]["R_total"]["mandatory_pass"] is True
    assert strong_result["observables"]["R_total"]["strong_pass"] is False
    assert strong_result["observables"]["R_total"]["mandatory_status"] == "pass"
    assert strong_result["observables"]["R_total"]["strong_status"] == "fail"
    assert strong_result["mandatory_pass"] is True
    assert strong_result["strong_pass"] is False
    order_strong_only = deepcopy(left)
    order_strong_only["orders"][_mode_keys()[0]]["power_ratio"] = 1.0002e-4
    order_result = compare_full3d_grid_views(left, order_strong_only)
    assert order_result["pass"] is True
    assert order_result["order_mandatory_pass"] is True
    assert order_result["order_strong_pass"] is False
    different_grid_sha = deepcopy(left)
    different_grid_sha["physical_model_sha256"] = "b" * 64
    same_physics = compare_full3d_grid_views(left, different_grid_sha)
    assert same_physics["pass"] is True
    assert same_physics["physical_model_exact"] is False
    different_physics = deepcopy(different_grid_sha)
    different_physics["physics_except_mesh_identity"] = "different-physics"
    assert compare_full3d_grid_views(left, different_physics)["pass"] is False


def test_task039_resolved_identity_excludes_only_mesh_target() -> None:
    resolved = {
        "geometry": {"domain": "fixed"},
        "materials": {"grating": "fixed"},
        "incidence": {"theta": 80.0, "phi": 0.0},
        "boundary": {"floquet": "fixed"},
        "method": {"kind": "full3d_direct", "requested_modes_per_direction": 604},
        "solver": {"assembly": "static_condensed"},
        "discretization": {"mesh_target_nm": 10.0, "nedelec_degree": 6},
    }
    inventory = {
        "keys": [
            dict(zip(("side", "m", "n", "polarization"), key)) for key in _mode_keys()
        ]
    }
    coarse = deepcopy(resolved)
    coarse["discretization"]["mesh_target_nm"] = 7.5
    assert _resolved_physics_identity(
        resolved, inventory
    ) == _resolved_physics_identity(coarse, inventory)
    changed_material = deepcopy(coarse)
    changed_material["materials"]["grating"] = "different"
    assert _resolved_physics_identity(
        resolved, inventory
    ) != _resolved_physics_identity(changed_material, inventory)


def _m480_record(reference: dict[str, object]) -> dict[str, object]:
    profile = make_task039_hybrid_iterative_profile(480, 8)
    keys = _mode_keys()
    inventory = {
        "keys": [dict(zip(("side", "m", "n", "polarization"), key)) for key in keys]
    }
    residuals = dict.fromkeys(_RESIDUAL_KEYS, 1.0e-10)
    progress = [
        {
            "iteration": iteration,
            **residuals,
            "diagnostic": {"status": "available"},
            "pc_apply_count": iteration + 1,
            "bottom_action_apply_count": iteration + 2,
            "top_action_apply_count": iteration + 3,
            "elapsed_seconds": float(iteration),
        }
        for iteration in (*TASK039_M480_PROGRESS_ROWS[:-1], 1200)
        if iteration <= 1200
    ]
    source_sha = "a" * 40
    qualification = {
        key: True
        for key in (
            "numerical_pass",
            "release_pass",
            "recovery_pass",
            "physics_pass",
            "lifecycle_pass",
            "source_after_pass",
            "final_release_pass",
            "cfg_audit_pass",
            "mode_identity_pass",
            "integration_performance_pass",
            "error_free",
        )
    }
    return {
        "record_schema": profile.record_schema,
        "status": "online_candidate_pass_awaiting_offline_checker",
        "online_pass": True,
        "ordinary_default_changed": False,
        "explicit_opt_in": True,
        "source": {
            "before": {
                "commit_sha": source_sha,
                "tracked_source_dirty": False,
                "stable_and_clean_before": True,
            },
            "after": {
                "head": source_sha,
                "clean": True,
                "matches_verified_clean_sha": True,
            },
        },
        "profile": profile_record(profile),
        "authority_bindings": {
            "explicit_profile": {
                "profile_id": profile.profile_id,
                "requested_modes": 480,
                "mpi_size": 8,
            }
        },
        "qualification": qualification,
        "linear": {
            "reason": 1,
            "iterations": 1200,
            "postsolve_residuals": residuals,
            "history": progress,
            "release": {"pass": True},
        },
        "recovery": {
            "recovery_pass": True,
            "reports": {
                side: {
                    "external_q": {
                        "auxiliary_relative_residual": 1.0e-11,
                        "pass": True,
                    }
                }
                for side in ("bottom", "top")
            },
        },
        "physics": {
            "traction": {
                "bottom": {"relative_dual": 1.0e-10},
                "top": {"relative_dual": 1.0e-10},
            },
            "interface_continuity": {"bottom": {}, "top": {}},
            "own_grid": {"status": "measured"},
            "canonical": {"bottom": {}, "top": {}},
            "own_physics_pass": True,
            "canonical_pass": True,
            "physics_pass": True,
            "port_power": {"R_total": 0.9, "T_total": 0.001},
            "absorption": {"A_balance": 0.099, "A_volume_total": 0.099},
            "energy": {"closure": 1.0e-8},
            "external_orders": [
                dict(zip(("side", "m", "n", "polarization"), key)) for key in keys
            ],
        },
        "external_mode_inventory": inventory,
        "mode_identity": {
            side: {
                "keys": [key for key in keys if key[0] == side],
                "pass": True,
                "keys_unique": True,
                "beta_finite": True,
            }
            for side in ("bottom", "top")
        },
        "final_release": {"pass": True},
    }


def test_task039_m480_solver_only_contract_blocks_full3d_qualification() -> None:
    reference = _grid_view()
    reference["equation_identity_sha256"] = _identity_sha256(
        reference["equation_identity"]
    )
    direct_reference = {
        **reference,
        "canonical": {
            "active_trace": np.ones(8, dtype=np.complex128),
            "full_fe": np.ones(8, dtype=np.complex128),
        },
    }
    comparison_payload = {
        **reference,
        "canonical": {
            "active_trace": np.ones(8, dtype=np.complex128),
            "full_fe": np.ones(8, dtype=np.complex128),
        },
    }
    comparison_payload["method_solver_identity"] = {
        "method": {"kind": "hybrid_iterative"},
        "solver": {"linear_solver": "fgmres"},
    }
    direct_reference["method_solver_identity"] = {
        "method": {"kind": "hybrid_direct"},
        "solver": {"linear_solver": "direct"},
    }
    outer_resource = {
        "status": "measured",
        "zero_swap_observed": True,
        "process_tree_peak_swap_mb": 0,
    }
    result = check_m480_hybrid_iterative(
        _m480_record(reference),
        direct_reference,
        resource_authority=outer_resource,
        comparison_payload=comparison_payload,
    )
    assert result["pass"] is True
    assert result["production_validation_allowed"] is False
    assert result["full3d_qualified"] is False
    assert result["comparison"]["identity_contract"] == "same_equation"
    assert result["comparison"]["method_solver_identity"]["exact"] is False
    assert result["progress_rows"][0]["pc_apply_count"] == 1
    assert result["progress_rows"][0]["bottom_action_apply_count"] == 2
    assert result["progress_rows"][0]["top_action_apply_count"] == 3
    assert result["progress_rows"][0]["elapsed_seconds"] == 0.0

    bad = _m480_record(reference)
    bad["linear"]["postsolve_residuals"]["top_true_relative_residual"] = 1.0e-8
    assert (
        check_m480_hybrid_iterative(
            bad,
            direct_reference,
            resource_authority=outer_resource,
            comparison_payload=comparison_payload,
        )["pass"]
        is False
    )
    changed_equation = deepcopy(comparison_payload)
    changed_equation["equation_identity"]["materials"]["material"] = "changed"
    assert (
        check_m480_hybrid_iterative(
            _m480_record(reference),
            direct_reference,
            resource_authority=outer_resource,
            comparison_payload=changed_equation,
        )["pass"]
        is False
    )


def test_task039_m480_checker_accepts_minimal_online_builder_shape() -> None:
    reference = _grid_view()
    reference["equation_identity_sha256"] = _identity_sha256(
        reference["equation_identity"]
    )
    record = _m480_record(reference)
    assert "operator_contract" not in record
    assert "solver_authority" not in record
    assert "integration_pass" not in record["physics"]
    direct_reference = {
        **reference,
        "canonical": {
            "active_trace": np.ones(8, dtype=np.complex128),
            "full_fe": np.ones(8, dtype=np.complex128),
        },
    }
    comparison_payload = {
        **direct_reference,
        "canonical": {
            "active_trace": np.ones(8, dtype=np.complex128),
            "full_fe": np.ones(8, dtype=np.complex128),
        },
    }
    comparison_payload["method_solver_identity"] = {
        "method": {"kind": "hybrid_iterative"},
        "solver": {"linear_solver": "fgmres"},
    }
    direct_reference["method_solver_identity"] = {
        "method": {"kind": "hybrid_direct"},
        "solver": {"linear_solver": "direct"},
    }
    result = check_m480_hybrid_iterative(
        record,
        direct_reference,
        resource_authority={
            "status": "measured",
            "zero_swap_observed": True,
            "process_tree_peak_swap_mb": 0,
        },
        comparison_payload=comparison_payload,
    )
    assert result["pass"] is True


def _h_path() -> dict[str, object]:
    z = [9.0, 10.0, 30.0, 60.0, 90.0, 110.0, 111.0]
    return {
        "coordinates": {
            "x_nm": np.arange(2.0),
            "y_nm": np.arange(2.0),
            "z_nm": np.asarray(z),
        },
        "plane_roles": [
            "bottom_element_safe_offset",
            "interface_bottom",
            "lower_reference",
            "middle_reference",
            "upper_reference",
            "interface_top",
            "top_element_safe_offset",
        ],
        "offset_provenance": {
            "source": "mesh_element_interior",
            "bottom": {
                "role": "bottom_element_safe_offset",
                "element_id": "bottom-cell-0",
                "distance_from_interface_nm": 1.0,
            },
            "top": {
                "role": "top_element_safe_offset",
                "element_id": "top-cell-0",
                "distance_from_interface_nm": 1.0,
            },
        },
        "fields": {
            "E_V_per_m": np.ones((7, 2, 2, 3), dtype=np.complex128),
            "H_A_per_m": np.ones((7, 2, 2, 3), dtype=np.complex128),
        },
        "flux": np.ones(len(z)),
        "energy": np.ones(len(z)),
    }


def test_task039_h_diagnostic_requires_complete_analytic_curl_path() -> None:
    native, curl_e, full3d = _h_path(), _h_path(), _h_path()
    curl_e["curl_source"] = "complete_reconstructed_field_analytic_or_fe"
    result = diagnose_h_paths(native, curl_e, full3d)
    assert result["pass"] is True
    assert result["coordinates_exact"] is True
    assert result["diagnostic_complete"] is True
    assert result["numeric_gate_pass"] is True
    component = result["comparisons"]["native_vs_curlE"]["H_A_per_m"][
        "per_plane_component"
    ][0][0]
    assert component["mandatory_threshold"] == 1.0e-2
    assert component["strong_threshold"] == 5.0e-3
    assert "phase_sensitive_complex_error" in component
    assert result["classification_evidence"]["both_full_comparisons_fail"] is False
    assert result["classification"] == "M480_H_DISCREPANCY_UNRESOLVED"
    native["fields"]["H_A_per_m"][0, 0, 0, 0] = 2.0
    assert (
        diagnose_h_paths(native, curl_e, full3d)["classification"]
        == "M480_H_RECOVERY_OR_POSTPROCESS_DEFECT"
    )
    native["fields"]["H_A_per_m"][0, 0, 0, 0] = 1.0
    curl_e["fields"]["H_A_per_m"][0, 0, 0, 0] = 2.0
    assert diagnose_h_paths(native, curl_e, full3d)["pass"] is False
    native["fields"]["H_A_per_m"][0, 0, 0, 0] = 2.0
    curl_e["fields"]["H_A_per_m"][0, 0, 0, 0] = 2.0
    assert (
        diagnose_h_paths(native, curl_e, full3d)["classification"]
        == "M480_H_DERIVATIVE_MODAL_TRUNCATION_NOT_CONVERGED"
    )
    with pytest.raises(ValueError, match="complete reconstructed"):
        diagnose_h_paths(native, _h_path(), full3d)


def _m960_payload() -> dict[str, object]:
    identity = np.eye(3, dtype=np.complex128)
    history = {
        m: {
            "raw_forward_error": 1.0e-13,
            "backward_error_eta": 1.0e-15,
            "dimension": 3,
            "dynamic_backward_error_limit": 100 * np.finfo(np.complex128).eps * 3,
            "representation_error": 1.0e-13,
            "finite": True,
            "sign_order_exact": True,
        }
        for m in (120, 240, 480)
    }
    return {
        "raw_negative_overlap": identity.copy(),
        "canonical_negative_overlap": identity.copy(),
        "surface_gram": identity.copy(),
        "canonical_mapping": identity.copy(),
        "repeat_raw_overlap": identity.copy(),
        "repeat_surface_gram": identity.copy(),
        "repeat_canonical_mapping": identity.copy(),
        "repeat_canonical_negative_overlap": identity.copy(),
        "column_keys": [["bottom", i, 0, "s"] for i in range(3)],
        "raw_forward_error": 1.0e-13,
        "representation_error": 1.0e-13,
        "column_sign_order_exact": True,
        "historical_sign_order_exact": True,
        "historical_m0_mminus1_valid": True,
        "raw_artifact_exact": True,
        "historical_m_modes": history,
        "degenerate_groups": [
            {
                "indices": [0, 1, 2],
                "keys": [["bottom", i, 0, "s"] for i in range(3)],
            }
        ],
    }


def test_task039_m960_trace_audit_recomputes_backward_error_without_relaxing_gate() -> (
    None
):
    result = audit_m960_trace(_m960_payload())
    assert result["pass"] is True
    assert result["dimension"] == 3
    reported_only = _m960_payload()
    reported_only["raw_forward_error"] = 1.0e-8
    reported_only["representation_error"] = 1.0e-8
    assert audit_m960_trace(reported_only)["pass"] is True
    bad = _m960_payload()
    bad["raw_negative_overlap"][0, 1] = 1.0e-8
    bad["canonical_negative_overlap"][0, 2] = 1.0e-8
    assert audit_m960_trace(bad)["pass"] is False
    norm_case = _m960_payload()
    norm_case["raw_negative_overlap"] = np.eye(3, dtype=np.complex128)
    norm_case["raw_negative_overlap"][0, 1] = 1.0e-12
    norm_case["raw_negative_overlap"][0, 2] = 1.0e-12
    norm_result = audit_m960_trace(norm_case)
    expected_eta = 2.0e-12 / (
        np.linalg.norm(norm_case["raw_negative_overlap"], np.inf)
        + np.linalg.norm(norm_case["surface_gram"], np.inf)
        * np.linalg.norm(norm_case["canonical_mapping"], np.inf)
        + np.finfo(np.complex128).tiny
    )
    assert norm_result["backward_error_eta"] == pytest.approx(expected_eta)
    assert norm_result["worst_column"] in norm_result["worst_column_group"]["indices"]


def test_task039_fine_stage_event_is_visible_to_existing_watchdog_reader(tmp_path):
    path = tmp_path / "memory_stages.jsonl"
    path.write_text(
        json.dumps(
            {
                "stage": "positive_qep_solve_peak",
                "schema": "task039.e10-stage-event.v1",
                "detail": {"marker_semantics": "peak derived from interval samples"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert _latest_stage(path) == ("positive_qep_solve_peak", "unknown")


def test_task039_e10_ledger_preserves_measured_and_missing_classifications() -> None:
    ledger = task039_e10_ledger(
        [
            {
                "stage": "local_fe_dtn_systems_ready",
                "status": "measured",
                "peak_rss_mib": 10.0,
            }
        ],
        object_capacity={"status": "derived", "classification": "derived_capacity"},
    )
    assert tuple(ledger["order"]) == TASK039_E10_STAGE_ORDER
    assert len(ledger["order"]) == 18
    assert ledger["nodes"]["local_fe_dtn_systems_ready"]["status"] == "measured"
    assert ledger["nodes"]["qep_matrices_ready"]["status"] == "not_available"
    assert ledger["object_capacity"]["classification"] == "derived_capacity"
    ordered = task039_e10_ledger(
        [
            {"stage": "selected_biorthogonal_bases_ready"},
            {"stage": "canonical_negative_traces_ready"},
            {"stage": "projection_matrices_ready"},
            {"stage": "traction_matrices_ready"},
            {"stage": "local_fe_dtn_systems_ready"},
        ]
    )
    assert (
        ordered["nodes"]["local_fe_dtn_systems_ready"]["stage"]
        == "local_fe_dtn_systems_ready"
    )
    with pytest.raises(ValueError, match="duplicate"):
        task039_e10_ledger(
            [
                {"stage": "mesh_spaces_ready"},
                {"stage": "mesh_spaces_ready"},
            ]
        )
    with pytest.raises(ValueError, match="out-of-order"):
        task039_e10_ledger(
            [
                {"stage": "projection_matrices_ready"},
                {"stage": "canonical_negative_traces_ready"},
            ]
        )


def test_task039_e10_runner_is_opt_in_and_releases_before_final_markers() -> None:
    source = (ROOT / "benchmarks/run_task032_phase6_augmented.py").read_text(
        encoding="utf-8"
    )
    assert 'canonical_export_prefix != "task039_direct"' in source
    destroy = source.index("operators.destroy()")
    canonical = source.index('"canonical_negative_traces_ready"')
    projection = source.index('"projection_matrices_ready"')
    released = source.index('"all_modal_qep_temporaries_released"')
    cleanup = source.index('"final_cleanup"')
    assert canonical < projection
    assert destroy < released < cleanup


def _capacity_snapshot(**updates: object) -> dict[str, object]:
    snapshot = {
        "input_identity_exact": True,
        "capacity_snapshot_status": "available",
        "symbolic_status": "not_available",
        "analysis_status": "not_available",
        "disk_sufficient": True,
        "cells": 252,
        "full_fe_dofs": 173802,
        "active_trace_rows": 51192,
        "assembled_rows": 51796,
        "assembled_nnz_estimate": 42913900,
        "dynamic_inventory_count": 604,
        "dynamic_inventory_keys_exact": True,
        "predicted_factor_nnz": 217041864,
        "predicted_process_tree_peak_range_gib": [190.0, 191.0],
        "available_memory_gib": 228.0,
        "disk_free_gib": 500.0,
        "disk_required_gib": 100.0,
    }
    snapshot.update(updates)
    return snapshot


def test_task039_mesh_preflight_keeps_h5_prediction_separate_from_hard_stop() -> None:
    result = mesh_resource_preflight(
        5.0,
        selected_limit_gib=228.0657501220703,
        predicted_peak_gib=180.0,
        capacity_snapshot=_capacity_snapshot(
            symbolic_status="pass",
            analysis_status="pass",
            h10_measured=True,
            h7p5_measured=True,
            h6_measured=True,
            available_memory_gib=228.0657501220703,
            factor_bytes=100.0,
            workspace_bytes=10.0,
            predicted_process_tree_peak_range_gib=[179.0, 180.0],
        ),
    )
    assert result["effective_hard_gib"] == 195.0
    assert result["mesh_gate"]["pass"] is True
    assert result["h5_extra_gate"]["pass"] is True
    h7p5 = mesh_resource_preflight(
        7.5,
        selected_limit_gib=228.0,
        predicted_peak_gib=191.0,
        capacity_snapshot=_capacity_snapshot(),
    )
    assert h7p5["mesh_gate"]["pass"] is True
    assert h7p5["h5_extra_gate"]["status"] == "not_applicable"
    assert h7p5["evidence"]["symbolic_analysis"]["classification"] == "not_available"
    assert (
        h7p5["evidence"]["symbolic_analysis"]["status"] == "nonblocking_not_available"
    )
    conflict = mesh_resource_preflight(
        5.0,
        selected_limit_gib=228.0,
        predicted_peak_gib=179.0,
        capacity_snapshot=_capacity_snapshot(
            symbolic_status="pass",
            analysis_status="pass",
            h10_measured=True,
            h7p5_measured=True,
            h6_measured=True,
            factor_bytes=100.0,
            workspace_bytes=10.0,
        ),
    )
    assert conflict["mesh_gate"]["prediction"]["explicit_matches_upper"] is False
    assert conflict["all_pass"] is False
    assert (
        mesh_resource_preflight(7.5, selected_limit_gib=228.0, capacity_snapshot={})[
            "mesh_gate"
        ]["pass"]
        is False
    )
    not_ready = mesh_resource_preflight(
        7.5,
        selected_limit_gib=228.0,
        predicted_peak_gib=196.0,
        capacity_snapshot=_capacity_snapshot(
            predicted_process_tree_peak_range_gib=[196.0, 197.0]
        ),
    )
    assert not_ready["mesh_gate"]["pass"] is False
    assert (
        mesh_resource_preflight(5.0, selected_limit_gib=228.0, swap_mib=1.0)[
            "swap_pass"
        ]
        is False
    )
    disk_failure = mesh_resource_preflight(
        7.5,
        selected_limit_gib=228.0,
        capacity_snapshot=_capacity_snapshot(
            disk_free_gib=50.0,
            disk_required_gib=100.0,
            predicted_process_tree_peak_range_gib=[190.0, 191.0],
        ),
    )
    assert disk_failure["evidence"]["disk_sufficient"]["pass"] is False
    assert disk_failure["evidence"]["disk_sufficient"]["classification"] == "measured"
