from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.task40_v21_readonly_recheck import (
    recompute_admission_gate,
    validate_stage_receipt_semantics,
)


def _q_csr_inventory() -> dict[str, dict[str, object]]:
    return {
        str(q): {
            "shape": [44_380 if q == 0 else 44_480] * 2,
            "nnz": 24_000_000 + q,
            "csr_sha256": f"{q + 1:064x}",
        }
        for q in range(4)
    }


_CLEANUP_PASS = {
    "status": "PASS",
    "native_owners_released": True,
    "process_descendants_cleared": True,
    "temporary_stage_objects_released": True,
}


def _receipt(outcome: str) -> tuple[dict[str, object], bool | None]:
    stage = "build_and_symbolic"
    prefix = ["preflight", "geometry_inventory", "local_port_components"]
    receipt: dict[str, object] = {
        "schema": "task40extra.review_v20_partial_result.v2",
        "outcome": outcome,
        "requested_stop_stage": stage,
        "official_result": False,
        "artifact_hashes": {},
        "cleanup": {"status": "UNKNOWN"},
        "q_coverage": {"status": "UNKNOWN"},
    }
    if outcome == "AUTH_NOT_GRANTED":
        receipt.update(
            attempted_stages=["preflight"],
            completed_stages=["preflight"],
            q_coverage={"status": "NOT_RUN"},
            cleanup={"status": "NOT_RUN"},
        )
        return receipt, False
    if outcome == "RESOURCE_CONTROLLED_STOP":
        receipt.update(
            attempted_stages=[*prefix, stage],
            completed_stages=prefix,
            resource_gate={"classification": "RESOURCE_CONTROLLED_STOP"},
            cleanup=dict(_CLEANUP_PASS),
        )
        return receipt, True
    if outcome == "STAGE_COMPLETED":
        inventory = _q_csr_inventory()
        stage_result = {
            "completed_stage": stage,
            "all_q_symbolic_covered": True,
            "numeric_factor_build_attempt_count": 0,
            "q_csr_inventory": inventory,
        }
        receipt.update(
            attempted_stages=[*prefix, stage],
            completed_stages=[*prefix, stage],
            artifact_hashes={
                "task40_v10_p6_candidate_summary.json": {
                    "path": "task40_v10_p6_candidate_summary.json",
                    "sha256": "d" * 64,
                }
            },
            stage_result=stage_result,
            q_coverage={
                "status": "KNOWN",
                "all_q_symbolic_covered": True,
                "q_csr_inventory": inventory,
            },
            cleanup=dict(_CLEANUP_PASS),
        )
        return receipt, True
    receipt.update(
        attempted_stages=[*prefix, stage],
        completed_stages=prefix,
        failed_stage=stage,
        error={"type": "RuntimeError", "message": "fixture failure"},
    )
    return receipt, True


def _v22_receipt(outcome: str) -> tuple[dict[str, object], bool]:
    source_sha = "a" * 40
    input_sha = "b" * 64
    physical_sha = "c" * 64
    q_coverage = {
        "status": "NOT_RUN",
        "expected_q_count": 8,
        "built_q_count": 0,
    }
    probe: dict[str, object] = {
        "schema": "task40extra.review_v22_target_operator_probe.v1",
        "status": "PASS_ALL_MODE_B_D_STREAM_WITH_Q_UNBUILT",
        "source_sha": source_sha,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "mode_manifest_sha256": "d" * 64,
        "expected_q_count": 8,
        "built_q_count": 0,
        "q_csr_created": False,
        "factor_created": False,
        "ksp_created": False,
        "pde_solved": False,
        "official_result": False,
        "mode_coverage_target": {
            "expected_mode_count": 32_060,
            "expected_by_side": {"bottom": 16_030, "top": 16_030},
        },
        "p6_space": {
            "cell_count": 30_464,
            "cell_dof_dimension": 882,
            "global_storage_rows": 20_181_348,
            "global_independent_rows": 19_897_344,
            "interior_rows_per_cell": 450,
            "trace_rows_per_cell": 432,
        },
        "descriptor": {
            "staged_input_sha256": input_sha,
            "physical_model_sha256": physical_sha,
            "mode_manifest_sha256": "d" * 64,
            "ordered_mode_key_sha256": "e" * 64,
            "saved_mesh_xdmf_sha256": "f" * 64,
            "saved_mesh_h5_sha256": "1" * 64,
            "saved_boundary_mapping_sha256": "2" * 64,
            "actual_cell_dofmap_sha256": "3" * 64,
            "global_mpc_identity": {
                "global_storage_rows": 20_181_348,
                "global_independent_rows": 19_897_344,
                "owned_slave_count": 284_004,
                "slave_rows_sha256": "4" * 64,
                "master_local_indices_sha256": "5" * 64,
                "coefficients_sha256": "6" * 64,
                "offsets_sha256": "7" * 64,
                "coefficient_count": 284_004,
                "offset_count": 0,
                "mpc_finalized": True,
            },
        },
        "operator_witness": {
            "mode_coverage": {
                "expected": 32_060,
                "completed": 32_060,
                "completed_by_side": {"bottom": 16_030, "top": 16_030},
            },
            "B_alpha": {
                "mode_count": 32_060,
                "mode_count_by_side": {"bottom": 16_030, "top": 16_030},
            },
            "native_882_row_calibration_by_side": {
                side: {
                    "status": "MEASURED_NATIVE_882_ROW_SAME_RULE_PATH_CONSISTENCY",
                    "independent_reference": False,
                    "B_interior_relative": 1e-12,
                    "D_x_relative": 1e-12,
                }
                for side in ("bottom", "top")
            },
            "generated_p6_api_witness": {
                "status": "PASS_GENERATED_FACTORY_AND_BOUNDED_Q_TILES",
                "P6CellCondensedAction_factory_connected": True,
                "row_tile_q_consumer_connected": True,
                "independent_saved_full_row_packet_reference": {
                    "status": "PASS_HASH_BOUND_SAVED_DEGREE60_FULL_ROW_B_D_PACKETS",
                    "quadrature_degree_by_side": {"bottom": 60, "top": 60},
                    "full_local_rows_by_side": {"bottom": 882, "top": 882},
                    "independent_B_D_construction_by_side": {
                        "bottom": True,
                        "top": True,
                    },
                    "B_relative_to_live_native_by_side": {
                        "bottom": 1e-14,
                        "top": 1e-14,
                    },
                    "D_relative_to_live_native_by_side": {
                        "bottom": 1e-14,
                        "top": 1e-14,
                    },
                    "mode_indices_by_side": {"bottom": 1, "top": 0},
                    "actual_cell_ids_by_side": {"bottom": 1, "top": 0},
                    "actual_class_ids_by_side": {"bottom": "c00", "top": "c01"},
                    "packet_npz_sha256_by_side": {
                        "bottom": "8" * 64,
                        "top": "9" * 64,
                    },
                },
                "same_cell_s_p_crossmode": {
                    "consumed_by_local_q11_tile": True,
                    "Hhat_only_s_p_projection": [[{"real": 1.0, "imag": 0.0}]],
                    "full_q11_s_p_projection": [[{"real": 1.0, "imag": 0.0}]],
                },
                "local_q_row_tile_consumer": {
                    "trace_only_selector": True,
                    "same_cell_s_p_port_only_selector": True,
                    "Hhat_only_projection_recorded_independently": True,
                    "full_port_port_tile_recorded": True,
                },
            },
            "all_q_csr_factor_ksp_and_full_field": "NOT_RUN",
        },
        "q_coverage": dict(q_coverage),
    }
    receipt: dict[str, object] = {
        "schema": "task40extra.review_v20_partial_result.v2",
        "outcome": outcome,
        "requested_stop_stage": "target_operator_probe",
        "official_result": False,
        "source_sha": source_sha,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "artifact_hashes": {},
        "q_coverage": dict(q_coverage),
        "cleanup": {"status": "UNKNOWN", "reason": "native lifecycle not observed"},
        "target_operator_probe": probe,
    }
    if outcome == "AUTH_NOT_GRANTED":
        receipt.update(
            attempted_stages=["preflight"],
            completed_stages=["preflight"],
        )
        return receipt, False
    if outcome == "RESOURCE_CONTROLLED_STOP":
        receipt.update(
            attempted_stages=["preflight", "geometry_inventory"],
            completed_stages=["preflight"],
            blocked_task_stage="geometry_inventory",
            resource_gate={"classification": "RESOURCE_CONTROLLED_STOP"},
        )
        return receipt, True
    if outcome == "STAGE_COMPLETED":
        receipt.update(
            attempted_stages=["preflight", "geometry_inventory", "target_operator_probe"],
            completed_stages=["preflight", "geometry_inventory", "target_operator_probe"],
            stage_result={"completed_stage": "target_operator_probe"},
        )
        return receipt, True
    probe["status"] = "FAILED"
    probe["failure_message"] = "fixture ordinary failure"
    receipt.update(
        attempted_stages=["preflight", "geometry_inventory", "target_operator_probe"],
        completed_stages=["preflight", "geometry_inventory"],
        failed_stage="target_operator_probe",
        failure_message="fixture ordinary failure",
    )
    return receipt, True


def test_e2_admission_recomputes_both_byte_gates():
    result = recompute_admission_gate(
        {
            "current_process_tree_rss_bytes": 10_079_617_024,
            "requested_additional_bytes": 486_803_844,
            "requested_workspace_bytes": 486_803_844,
            "future_all_q_and_transform_reserve_bytes": 2_481_665_040,
            "fixed_future_workspace_headroom_bytes": 134_217_728,
            "dynamic_launch_cap_bytes": 13_519_601_664,
        }
    )
    assert result["projected_process_tree_rss_bytes"] == 13_669_107_480
    assert result["total_rss_deficit_bytes"] == 149_505_816
    assert result["incremental_required_bytes"] == 3_589_490_456
    assert result["incremental_headroom_bytes"] == 3_439_984_640
    assert result["incremental_deficit_bytes"] == 149_505_816
    assert result["both_inequalities_pass"] is False


@pytest.mark.parametrize(
    ("outcome", "expected_pass"),
    [
        ("AUTH_NOT_GRANTED", True),
        ("RESOURCE_CONTROLLED_STOP", True),
        ("STAGE_COMPLETED", True),
        ("STAGE_FAILED", True),
    ],
)
def test_stage_receipt_state_semantics_cover_authorize_stop_complete_and_fail(
    outcome, expected_pass
):
    receipt, authorized = _receipt(outcome)
    checks = validate_stage_receipt_semantics(
        receipt, expected_stage="build_and_symbolic", heavy_authorized=authorized
    )
    assert all(checks.values()) is expected_pass


@pytest.mark.parametrize(
    ("outcome", "authorized"),
    [
        ("AUTH_NOT_GRANTED", False),
        ("RESOURCE_CONTROLLED_STOP", True),
        ("STAGE_FAILED", True),
        ("STAGE_COMPLETED", True),
    ],
)
def test_v22_receipt_prefix_and_state_semantics(outcome, authorized):
    receipt, operator_authorized = _v22_receipt(outcome)
    assert operator_authorized is authorized
    checks = validate_stage_receipt_semantics(
        receipt,
        expected_stage="target_operator_probe",
        heavy_authorized=False,
        operator_probe_authorized=operator_authorized,
    )
    assert all(checks.values()), checks


def test_v22_completion_recomputes_raw_coverage_fe_mpc_and_native_gates():
    receipt, authorized = _v22_receipt("STAGE_COMPLETED")
    checks = validate_stage_receipt_semantics(
        receipt,
        expected_stage="target_operator_probe",
        heavy_authorized=False,
        operator_probe_authorized=authorized,
    )
    assert all(checks.values()), checks

    probe = receipt["target_operator_probe"]
    probe["operator_witness"]["native_882_row_calibration_by_side"]["top"][
        "D_x_relative"
    ] = 2e-10
    tampered = validate_stage_receipt_semantics(
        receipt,
        expected_stage="target_operator_probe",
        heavy_authorized=False,
        operator_probe_authorized=authorized,
    )
    assert tampered["v22_both_native_error_gates_recomputed"] is False
    probe["operator_witness"]["generated_p6_api_witness"][
        "same_cell_s_p_crossmode"
    ]["consumed_by_local_q11_tile"] = False
    tampered_crossmode = validate_stage_receipt_semantics(
        receipt,
        expected_stage="target_operator_probe",
        heavy_authorized=False,
        operator_probe_authorized=authorized,
    )
    assert tampered_crossmode["v22_generated_factory_and_q_consumer_connected"] is False


def test_v22_wrong_q_count_is_rejected_for_partial_receipt():
    receipt, authorized = _v22_receipt("RESOURCE_CONTROLLED_STOP")
    receipt["q_coverage"]["expected_q_count"] = 4
    checks = validate_stage_receipt_semantics(
        receipt,
        expected_stage="target_operator_probe",
        heavy_authorized=False,
        operator_probe_authorized=authorized,
    )
    assert checks["v22_q_inventory_explicit"] is False


def test_stage_complete_binds_q_hashes_to_candidate_summary_and_cleanup(tmp_path):
    receipt, authorized = _receipt("STAGE_COMPLETED")
    artifact = tmp_path / "task40_v10_p6_candidate_summary.json"
    artifact.write_text("candidate", encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    receipt["artifact_hashes"] = {
        artifact.name: {"path": artifact.name, "sha256": digest}
    }
    checks = validate_stage_receipt_semantics(
        receipt,
        expected_stage="build_and_symbolic",
        heavy_authorized=authorized,
        output_directory=tmp_path,
    )
    assert checks["artifact_hashes_well_formed_and_bound"] is True
    assert checks["q_csr_hashes_complete"] is True
    assert checks["q_csr_inventory_matches_stage_result"] is True
    assert checks["q_csr_inventory_bound_to_candidate_summary"] is True
    artifact.write_text("tampered", encoding="utf-8")
    tampered = validate_stage_receipt_semantics(
        receipt,
        expected_stage="build_and_symbolic",
        heavy_authorized=authorized,
        output_directory=tmp_path,
    )
    assert tampered["artifact_hashes_well_formed_and_bound"] is False


def test_heavy_stage_with_unknown_cleanup_is_not_checker_pass():
    receipt, authorized = _receipt("STAGE_COMPLETED")
    receipt["cleanup"] = {"status": "UNKNOWN", "reason": "fixture lacks cleanup proof"}
    checks = validate_stage_receipt_semantics(
        receipt, expected_stage="build_and_symbolic", heavy_authorized=authorized
    )
    assert checks["heavy_cleanup_proved"] is False
    assert all(check for key, check in checks.items() if key != "heavy_cleanup_proved")


def test_service_partial_checker_accepts_auth_denial_without_claiming_stage_run(tmp_path):
    import json

    from scripts.task40_v20_service_workflow import _check_partial_result
    from src.io import load_and_resolve

    root = Path(__file__).resolve().parents[2]
    input_path = root / (
        "input/task40extra_0p7nm_engineering/target_original_ny8_resource_pilot_v20.dat"
    )
    payload = load_and_resolve(input_path).as_jsonable()
    input_sha = hashlib.sha256(input_path.read_bytes()).hexdigest()
    physical_sha = payload["provenance"]["physical_model_sha256"]
    run_id = payload["run_id"]
    source_sha = "e" * 40
    manifest_path = tmp_path / "run_manifest.json"
    summary_path = tmp_path / "run_summary.json"
    output_path = tmp_path / "output"
    output_path.mkdir()
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "source_sha": source_sha,
                "input_sha256": input_sha,
                "physical_model_sha256": physical_sha,
            }
        ),
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps({"run_id": run_id, "result_classification": "CONTROLLED_STOP"}),
        encoding="utf-8",
    )
    (output_path / "v20_partial_result.json").write_text(
        json.dumps(
            {
                "schema": "task40extra.review_v20_partial_result.v2",
                "status": "controlled_stop",
                "outcome": "AUTH_NOT_GRANTED",
                "run_id": run_id,
                "source_sha": source_sha,
                "input_sha256": input_sha,
                "physical_model_sha256": physical_sha,
                "requested_stop_stage": "build_and_symbolic",
                "attempted_stages": ["preflight"],
                "completed_stages": ["preflight"],
                "official_result": False,
                "artifact_hashes": {},
                "q_coverage": {"status": "NOT_RUN"},
                "cleanup": {"status": "NOT_RUN"},
            }
        ),
        encoding="utf-8",
    )
    result = _check_partial_result(
        input_path=input_path,
        summary_path=summary_path,
        manifest_path=manifest_path,
        numerical_output=output_path,
        expected_stop_stage="build_and_symbolic",
    )
    assert result["status"] == "PARTIAL_RECEIPT_CHECKED"
    assert result["checker_passed"] is True
    assert result["official_result"] is False


def test_completed_q0_numeric_receipt_requires_all_q_symbolic_and_exactly_one_factor():
    inventory = _q_csr_inventory()
    receipt: dict[str, object] = {
        "schema": "task40extra.review_v20_partial_result.v2",
        "outcome": "STAGE_COMPLETED",
        "requested_stop_stage": "one_q_numeric",
        "attempted_stages": [
            "preflight",
            "geometry_inventory",
            "local_port_components",
            "one_q_numeric",
        ],
        "completed_stages": [
            "preflight",
            "geometry_inventory",
            "local_port_components",
            "one_q_numeric",
        ],
        "official_result": False,
        "artifact_hashes": {
            "task40_v10_p6_candidate_summary.json": {
                "path": "task40_v10_p6_candidate_summary.json",
                "sha256": "a" * 64,
            }
        },
        "cleanup": dict(_CLEANUP_PASS),
        "q_coverage": {"status": "KNOWN", "q_csr_inventory": inventory},
        "stage_result": {
            "completed_stage": "one_q_numeric",
            "all_q_symbolic_covered": True,
            "selected_q": 0,
            "numeric_factor_build_attempt_count": 1,
            "q_csr_inventory": inventory,
        },
    }
    checks = validate_stage_receipt_semantics(
        receipt, expected_stage="one_q_numeric", heavy_authorized=True
    )
    assert all(checks.values())
    receipt["stage_result"]["selected_q"] = 1
    checks = validate_stage_receipt_semantics(
        receipt, expected_stage="one_q_numeric", heavy_authorized=True
    )
    assert checks["selected_q_is_zero"] is False


@pytest.mark.parametrize(
    ("worker_result", "failure", "expected_outcome"),
    [
        (
            {
                "passed": True,
                "status": "controlled_stop",
                "summary": {
                    "result_classification": "CONTROLLED_STOP_AT_REQUESTED_V20_STAGE",
                    "v20_stage_result": {
                        "completed_stage": "build_and_symbolic",
                        "all_q_symbolic_covered": True,
                        "numeric_factor_build_attempt_count": 0,
                        "q_csr_inventory": _q_csr_inventory(),
                    },
                },
            },
            None,
            "STAGE_COMPLETED",
        ),
        (
            {
                "passed": False,
                "status": "controlled_stop",
                "summary": {
                    "result_classification": "RESOURCE_CONTROLLED_STOP",
                    "error": {"type": "V14ResourceStop", "message": "gate rejected"},
                },
            },
            None,
            "RESOURCE_CONTROLLED_STOP",
        ),
        (None, RuntimeError("fixture worker failure"), "STAGE_FAILED"),
    ],
)
def test_stage_runner_emits_receipt_for_worker_success_resource_stop_and_error(
    tmp_path, worker_result, failure, expected_outcome
):
    from src.runners.task40_v20_stage_runner import _worker_stage_receipt

    receipt = _worker_stage_receipt(
        tmp_path,
        preflight={
            "run_id": "fixture",
            "case_profile": "fixture_profile",
            "source_sha": "1" * 40,
            "input_sha256": "2" * 64,
            "physical_model_sha256": "3" * 64,
        },
        requested_stage="build_and_symbolic",
        completed_prefix=["preflight", "geometry_inventory", "local_port_components"],
        target_heavy_authorized=True,
        worker_result=worker_result,
        failure=failure,
    )
    assert receipt["outcome"] == expected_outcome
    assert receipt["attempted_stages"][-1] == "build_and_symbolic"
    assert receipt["official_result"] is False
    assert (tmp_path / "v20_partial_result.json").is_file()
    if expected_outcome == "STAGE_COMPLETED":
        assert receipt["completed_stages"][-1] == "build_and_symbolic"
        assert receipt["q_coverage"]["status"] == "KNOWN"
    elif expected_outcome == "RESOURCE_CONTROLLED_STOP":
        assert "build_and_symbolic" not in receipt["completed_stages"]
        assert receipt["resource_gate"]["type"] == "V14ResourceStop"
        assert receipt["cleanup"]["status"] == "UNKNOWN"
        assert receipt["q_coverage"]["status"] == "UNKNOWN"
    else:
        assert receipt["failed_stage"] == "build_and_symbolic"
        assert receipt["error"]["type"] == "RuntimeError"
    if expected_outcome == "STAGE_COMPLETED":
        checks = validate_stage_receipt_semantics(
            receipt,
            expected_stage="build_and_symbolic",
            heavy_authorized=True,
            output_directory=tmp_path,
        )
        assert checks["heavy_cleanup_proved"] is False
