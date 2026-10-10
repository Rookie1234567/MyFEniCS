from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct

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
                    "status": "MEASURED_RAW_PACKET_AND_PRODUCTION_SUPPORT_PATH_CONSISTENCY",
                    "independent_reference": False,
                    "production_B_relative": 1e-12,
                    "production_D_relative": 1e-12,
                    "production_D_vector_relative": 1e-12,
                    "production_B_path_consistency_only": True,
                    "production_B_reference_domain": "direct MPC/two-filter support union",
                    "production_D_reference_domain": "full-field production action",
                    "production_B_support_mismatch_count": 0,
                    "production_D_support_mismatch_count": 0,
                    "production_D_path_consistency_only": True,
                    "production_B_support_digest": {
                        "direct_rows_sha256": "8" * 64,
                        "grouped_rows_sha256": "9" * 64,
                        "direct_values_sha256": "a" * 64,
                        "grouped_values_sha256": "b" * 64,
                    },
                    "production_D_support_digest": {
                        "direct_rows_sha256": "c" * 64,
                        "grouped_rows_sha256": "d" * 64,
                        "direct_values_sha256": "e" * 64,
                        "grouped_values_sha256": "f" * 64,
                    },
                    # The historical raw-vs-filtered metric is retained as a
                    # diagnostic and must not substitute for the same-domain gate.
                    "B_interior_relative": 1e-12,
                    "raw_B_interior_vs_filtered_relative": 1.0,
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
        "production_support": {
            "direct_filtered_support_qualification": {
                "status": "MATCHED_ON_TWO_CALIBRATED_MODES",
                "production_exact_qualification": "PARTIAL",
                "support_mismatch_count_by_side": {
                    "bottom": {"B": 0, "D": 0},
                    "top": {"B": 0, "D": 0},
                },
            }
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


def _v23_receipt(
    tmp_path: Path,
    *,
    run_id: str = "task40-v23-fixture",
    source_sha: str = "a" * 40,
    input_sha: str = "b" * 64,
    physical_sha: str = "c" * 64,
) -> tuple[dict[str, object], str]:
    from src.runners.task40_v10_campaign import TASK40_V23_CAMPAIGN_SHA256
    import numpy as np
    from scipy import sparse
    from src.solvers.task40_v22_operator_probe import _sparse_csr_sha256

    def complex_hash(value: complex) -> str:
        return hashlib.sha256(struct.pack("<dd", value.real, value.imag)).hexdigest()

    def float_hash(value: float) -> str:
        return hashlib.sha256(struct.pack("<d", value)).hexdigest()

    c_value = 2.0 + 0.0j
    d_value = 0.0 + 3.0j
    h_value = 1.0
    q_map = sparse.csr_matrix(np.asarray([[1.0 + 0.0j]], dtype=np.complex128))
    q_map_sha = _sparse_csr_sha256(q_map)
    mode_key = [0, "bottom", 1, 2, "s"]
    b_rows = np.asarray([5], dtype=np.int64)
    b_values = np.asarray([c_value], dtype=np.complex128)
    d_rows = np.asarray([5], dtype=np.int64)
    d_raw = np.asarray([-d_value], dtype=np.complex128)
    original_h_identity = "e" * 64
    oracle_path = tmp_path / "v23_selected_mode_production_B_D_H.npz"
    with oracle_path.open("wb") as stream:
        np.savez(
            stream,
            mode_key_json=np.asarray(json.dumps(mode_key, separators=(",", ":"))),
            B_rows=b_rows,
            B_values=b_values,
            D_rows=d_rows,
            D_values=d_raw,
            H_p=np.asarray([h_value], dtype=np.float64),
            original_H_identity_sha256=np.asarray(original_h_identity),
        )
    oracle_sha = hashlib.sha256(oracle_path.read_bytes()).hexdigest()
    readback_path = tmp_path / "v23_selected_q_projection_readback.npz"
    with readback_path.open("wb") as stream:
        np.savez(
            stream,
            q_map_data=q_map.data,
            q_map_indices=q_map.indices,
            q_map_indptr=q_map.indptr,
            q_map_shape=np.asarray(q_map.shape, dtype=np.int64),
            q_map_support_global_rows=np.asarray([5], dtype=np.int64),
            selected_q_trace_rows=np.asarray([0], dtype=np.int64),
            candidate_B_support=np.asarray([c_value], dtype=np.complex128),
            oracle_B_support=np.asarray([c_value], dtype=np.complex128),
            candidate_D_support=np.asarray([d_raw[0]], dtype=np.complex128),
            oracle_D_support=np.asarray([d_raw[0]], dtype=np.complex128),
            candidate_C_direct=np.asarray([c_value], dtype=np.complex128),
            oracle_C_direct=np.asarray([c_value], dtype=np.complex128),
            candidate_minus_D_direct=np.asarray([d_value], dtype=np.complex128),
            oracle_minus_D_direct=np.asarray([d_value], dtype=np.complex128),
            candidate_H_original=np.asarray([h_value], dtype=np.float64),
            oracle_H_original=np.asarray([h_value], dtype=np.float64),
            original_H_p=np.asarray([h_value], dtype=np.float64),
            selected_mode_key_json=np.asarray(
                json.dumps(mode_key, separators=(",", ":"))
            ),
        )
    readback_sha = hashlib.sha256(readback_path.read_bytes()).hexdigest()
    array_hash = lambda value: hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()
    tile = {
        "row_global_q": 0,
        "column_global_q": 0,
        "q_port_alias_column": 0,
        "I_trace_q_rows": [0],
        "J_port_q_column": 0,
        "q_trace_map_shape": [1, 1],
        "q_trace_map_nnz": 1,
        "q_trace_map_sha256": q_map_sha,
        "mode_key": mode_key,
        "candidate_vs_independent_oracle_relative_errors": {
            "C_direct": 0.0,
            "minus_D_direct": 0.0,
            "H_original": 0.0,
            "limit_each": 1.0e-11,
        },
        "contributions": {
            "C_direct": {
                "shape": [1, 1],
                "I": [5],
                "J": [0],
                "values": [{"real": 2.0, "imag": 0.0}],
                "oracle_values": [{"real": 2.0, "imag": 0.0}],
                "relative_error": 0.0,
                "limit": 1.0e-11,
                "candidate_values_sha256": complex_hash(c_value),
                "oracle_values_sha256": complex_hash(c_value),
            },
            "minus_D_direct": {
                "shape": [1, 1],
                "I": [0],
                "J": [5],
                "values": [{"real": 0.0, "imag": 3.0}],
                "oracle_values": [{"real": 0.0, "imag": 3.0}],
                "relative_error": 0.0,
                "limit": 1.0e-11,
                "candidate_values_sha256": complex_hash(d_value),
                "oracle_values_sha256": complex_hash(d_value),
            },
            "H_original": {
                "shape": [1, 1],
                "I": [0],
                "J": [0],
                "value": {"real": h_value, "imag": 0.0},
                "oracle_value": {"real": h_value, "imag": 0.0},
                "relative_error": 0.0,
                "limit": 1.0e-11,
                "candidate_values_sha256": float_hash(h_value),
                "oracle_values_sha256": float_hash(h_value),
            },
            "volume": {"status": "PARTIAL_NOT_RUN"},
        },
        "frozen_B_D_H_oracle": {
            "artifact_path": oracle_path.name,
            "artifact_sha256": oracle_sha,
            "B_values_sha256": array_hash(b_values),
            "D_values_sha256": array_hash(d_raw),
        },
    }
    tile_sha = hashlib.sha256(
        json.dumps(tile, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    q_child = {
        "schema": "task40extra.review_v23_original_ny8_selected_q_port_tile.v1",
        "status": "PASS_REAL_ORIGINAL_NY8_Q_PORT_TILE",
        "official_result": False,
        "run_id": run_id,
        "source_sha": source_sha,
        "input_sha256": input_sha,
        "target_physical_model_sha256": physical_sha,
        "campaign_before": {"window_sha256": TASK40_V23_CAMPAIGN_SHA256},
        "campaign_after": {"window_sha256": TASK40_V23_CAMPAIGN_SHA256},
        "original_H_p_identity": {"identity_sha256": original_h_identity},
        "expected_q_count": 8,
        "full_q_matrix_coverage": "0/8",
        "factor_count": 0,
        "ksp_created": False,
        "pde_solved": False,
        "official_R_T_A_created": False,
        "selected_q_port_tile_built": True,
        "q_tile": tile,
        "q_tile_sha256": tile_sha,
        "production_oracle_artifact_path": oracle_path.name,
        "production_oracle_artifact_sha256": oracle_sha,
        "q_projection_readback_artifact": {
            "artifact_path": readback_path.name,
            "artifact_sha256": readback_sha,
            "q_trace_map_shape": [1, 1],
            "q_trace_map_nnz": 1,
            "q_trace_map_sha256": q_map_sha,
            "selected_q_trace_rows_sha256": hashlib.sha256(
                np.asarray([0], dtype=np.int32).tobytes()
            ).hexdigest(),
        },
        "complete_q_matrices": "0/8",
        "volume_qualification": "PARTIAL_NOT_RUN",
        "artifact_path": "v23_reference_q_port_tile.json",
    }
    q_path = tmp_path / q_child["artifact_path"]
    q_path.write_text(json.dumps(q_child, sort_keys=True), encoding="utf-8")
    q_sha = hashlib.sha256(q_path.read_bytes()).hexdigest()
    q_child["artifact_sha256"] = q_sha
    artifact_hashes = {
        q_path.name: {"path": q_path.name, "sha256": q_sha},
        oracle_path.name: {"path": oracle_path.name, "sha256": oracle_sha},
        readback_path.name: {"path": readback_path.name, "sha256": readback_sha},
    }
    q_coverage = {
        "status": "PARTIAL_REAL_Q_PORT_TILE",
        "expected_q_count": 8,
        "built_q_count": 0,
        "full_q_matrix_coverage": "0/8",
        "selected_q_port_tile": q_path.name,
        "selected_q_port_tile_sha256": q_sha,
        "volume_qualification": "PARTIAL_NOT_RUN",
    }
    probe = {
        "schema": "task40extra.review_v23_compact_boundary_operator_probe.v1",
        "status": "PASS_ALL_MODE_B_D_STREAM_WITH_PARTIAL_Q_PORT_TILE",
        "run_id": run_id,
        "source_sha": source_sha,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "campaign_window": {
            "campaign_version": "V23",
            "window_sha256": TASK40_V23_CAMPAIGN_SHA256,
            "read_only": True,
        },
        "expected_q_count": 8,
        "v23_selected_q_port_tile": q_child,
        "operator_witness": {
            "mode_coverage": {
                "expected": 32_060,
                "completed": 32_060,
                "completed_by_side": {"bottom": 16_030, "top": 16_030},
            }
        },
    }
    receipt = {
        "schema": "task40extra.review_v20_partial_result.v2",
        "outcome": "STAGE_COMPLETED",
        "requested_stop_stage": "target_operator_probe",
        "official_result": False,
        "run_id": run_id,
        "source_sha": source_sha,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "attempted_stages": ["preflight", "geometry_inventory", "target_operator_probe"],
        "completed_stages": ["preflight", "geometry_inventory", "target_operator_probe"],
        "partial_stages": [],
        "failed_stage": None,
        "blocked_task_stage": None,
        "expected_q_count": 8,
        "built_q_count": 0,
        "q_coverage": q_coverage,
        "cleanup": {"status": "UNKNOWN"},
        "stage_result": {"completed_stage": "target_operator_probe"},
        "target_operator_probe": probe,
        "artifact_hashes": artifact_hashes,
    }
    return receipt, TASK40_V23_CAMPAIGN_SHA256


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


def test_v23_checker_binds_nested_q_tile_and_recomputes_c_d_h_values(tmp_path):
    receipt, campaign_sha = _v23_receipt(tmp_path)
    checks = validate_stage_receipt_semantics(
        receipt,
        expected_stage="target_operator_probe",
        heavy_authorized=False,
        operator_probe_authorized=True,
        expected_q_count=8,
        expected_campaign_window_sha256=campaign_sha,
        output_directory=tmp_path,
    )
    assert all(checks.values()), checks

    contribution = receipt["target_operator_probe"]["v23_selected_q_port_tile"][
        "q_tile"
    ]["contributions"]["C_direct"]
    contribution["values"][0]["real"] = 2.5
    tampered = validate_stage_receipt_semantics(
        receipt,
        expected_stage="target_operator_probe",
        heavy_authorized=False,
        operator_probe_authorized=True,
        expected_q_count=8,
        expected_campaign_window_sha256=campaign_sha,
        output_directory=tmp_path,
    )
    assert tampered["C_direct_candidate_oracle_hashes_recomputed"] is False
    assert tampered["C_direct_relative_error_recomputed_under_limit"] is False
    assert tampered["v23_q_tile_hash_and_contribution_errors_recomputed"] is False


def test_v23_checker_accepts_planned_handoff_with_durable_partial_mode_prefix(tmp_path):
    receipt, campaign_sha = _v23_receipt(tmp_path)
    receipt["outcome"] = "PLANNED_HANDOFF"
    receipt["completed_stages"] = ["preflight", "geometry_inventory"]
    receipt["partial_stages"] = ["target_operator_probe"]
    receipt["stage_result"] = None
    receipt["planned_handoff"] = {
        "status": "PLANNED_SUFFIX_HANDOFF",
        "classification": "PLANNING_ONLY_NOT_A_RESOURCE_OR_NUMERICAL_STOP",
        "suffix_marked_complete": False,
    }
    probe = receipt["target_operator_probe"]
    probe["status"] = "PLANNED_SCAN_HANDOFF_WITH_PARTIAL_Q_PORT_TILE"
    probe["partial_mode_coverage"] = {
        "expected_mode_count": 32_060,
        "completed_mode_count": 128,
        "completed_by_side": {"bottom": 64, "top": 64},
        "stream_prefix_sha256": "f" * 64,
    }
    probe["latest_mode_checkpoint"] = {"checkpoint_json_path": "checkpoint.json"}
    probe["planned_handoff"] = dict(receipt["planned_handoff"])
    checks = validate_stage_receipt_semantics(
        receipt,
        expected_stage="target_operator_probe",
        heavy_authorized=False,
        operator_probe_authorized=True,
        expected_q_count=8,
        expected_campaign_window_sha256=campaign_sha,
        output_directory=tmp_path,
    )
    assert all(checks.values()), checks


def test_service_partial_checker_binds_v23_manifest_and_campaign(tmp_path):
    from scripts.task40_v20_service_workflow import _check_partial_result
    from src.io import load_and_resolve
    from src.runners.task40_v10_campaign import (
        TASK40_V23_CAMPAIGN_SHA256,
        TASK40_V23_CAMPAIGN_WINDOW,
    )

    root = Path(__file__).resolve().parents[2]
    input_path = root / (
        "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v20_wsl/"
        "stage_inputs/target_operator_probe/target_original_ny8_operator_probe_v22.dat"
    )
    input_sha = hashlib.sha256(input_path.read_bytes()).hexdigest()
    payload = load_and_resolve(input_path).as_jsonable()
    physical_sha = payload["provenance"]["physical_model_sha256"]
    output = tmp_path / "numerical-output"
    output.mkdir()
    receipt, _ = _v23_receipt(
        output,
        run_id=payload["run_id"],
        source_sha="f" * 40,
        input_sha=input_sha,
        physical_sha=physical_sha,
    )
    geometry_path = output / "v20_geometry_inventory.json"
    geometry_path.write_text("{}\n", encoding="utf-8")
    receipt["artifact_hashes"][geometry_path.name] = {
        "path": geometry_path.name,
        "sha256": hashlib.sha256(geometry_path.read_bytes()).hexdigest(),
    }
    (output / "v20_partial_result.json").write_text(
        json.dumps(receipt, sort_keys=True), encoding="utf-8"
    )
    campaign_path = (root / TASK40_V23_CAMPAIGN_WINDOW).resolve()
    accounting_path = campaign_path.with_name("campaign_accounting_v10.jsonl")
    manifest = {
        "run_id": payload["run_id"],
        "source_sha": "f" * 40,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "solver": {"preconditioner": payload["solver"]["preconditioner"]},
        "task40_v20_campaign": {
            "window_path": str(campaign_path),
            "window_sha256": TASK40_V23_CAMPAIGN_SHA256,
            "accounting_path": str(accounting_path),
        },
    }
    manifest_path = tmp_path / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    summary_path = tmp_path / "run_summary.json"
    summary_path.write_text(
        json.dumps({"run_id": payload["run_id"], "result_classification": "stage_completed"}),
        encoding="utf-8",
    )
    checked = _check_partial_result(
        input_path=input_path,
        summary_path=summary_path,
        manifest_path=manifest_path,
        numerical_output=output,
        expected_stop_stage="target_operator_probe",
    )
    assert checked["checker_passed"] is True, checked

    manifest["task40_v20_campaign"]["window_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    tampered = _check_partial_result(
        input_path=input_path,
        summary_path=summary_path,
        manifest_path=manifest_path,
        numerical_output=output,
        expected_stop_stage="target_operator_probe",
    )
    assert tampered["checker_passed"] is False
    assert tampered["checks"]["v23_manifest_campaign_window_and_accounting_bind"] is False


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
        "production_D_vector_relative"
    ] = 2e-10
    tampered = validate_stage_receipt_semantics(
        receipt,
        expected_stage="target_operator_probe",
        heavy_authorized=False,
        operator_probe_authorized=authorized,
    )
    assert tampered["v22_both_native_error_gates_recomputed"] is False

    mismatch_receipt, mismatch_authorized = _v22_receipt("STAGE_COMPLETED")
    mismatch_probe = mismatch_receipt["target_operator_probe"]
    mismatch_native = mismatch_probe["operator_witness"][
        "native_882_row_calibration_by_side"
    ]
    mismatch_native["top"]["production_D_support_mismatch_count"] = 2
    mismatch_qualification = mismatch_probe["production_support"][
        "direct_filtered_support_qualification"
    ]
    mismatch_qualification["status"] = "PARTIAL_SUPPORT_MISMATCH"
    mismatch_qualification["support_mismatch_count_by_side"]["top"]["D"] = 2
    mismatch_checks = validate_stage_receipt_semantics(
        mismatch_receipt,
        expected_stage="target_operator_probe",
        heavy_authorized=False,
        operator_probe_authorized=mismatch_authorized,
    )
    assert mismatch_checks["v22_direct_filtered_support_exactness_remains_partial"] is True
    mismatch_qualification["production_exact_qualification"] = "EXACT"
    mislabeled_checks = validate_stage_receipt_semantics(
        mismatch_receipt,
        expected_stage="target_operator_probe",
        heavy_authorized=False,
        operator_probe_authorized=mismatch_authorized,
    )
    assert mislabeled_checks["v22_direct_filtered_support_exactness_remains_partial"] is False

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


@pytest.mark.parametrize("expected_q_count", [4, 8])
def test_q_csr_checker_uses_profile_q_count_and_rejects_missing_or_illegal_keys(
    expected_q_count,
):
    receipt, authorized = _receipt("STAGE_COMPLETED")
    valid = {
        str(q): {"csr_sha256": f"{q + 1:064x}"}
        for q in range(expected_q_count)
    }
    receipt["stage_result"]["q_csr_inventory"] = valid
    receipt["q_coverage"]["q_csr_inventory"] = valid
    for inventory, expected in (
        (valid, True),
        ({key: value for key, value in valid.items() if key != str(expected_q_count - 1)}, False),
        ({**valid, str(expected_q_count): {"csr_sha256": "f" * 64}}, False),
    ):
        receipt["stage_result"]["q_csr_inventory"] = inventory
        receipt["q_coverage"]["q_csr_inventory"] = inventory
        checks = validate_stage_receipt_semantics(
            receipt,
            expected_stage="build_and_symbolic",
            heavy_authorized=authorized,
            expected_q_count=expected_q_count,
        )
        assert checks["q_csr_hashes_complete"] is expected
