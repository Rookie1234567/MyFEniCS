"""Read-only V21 receipts for historical E2 evidence and V20 stage outcomes."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping


V20_STAGE_ORDER = (
    "preflight",
    "geometry_inventory",
    "target_operator_probe",
    "local_port_components",
    "build_and_symbolic",
    "one_q_numeric",
    "full",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def recompute_admission_gate(gate: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute both admission inequalities from stored inputs, without PETSc."""

    current = int(gate["current_process_tree_rss_bytes"])
    additional = int(gate["requested_additional_bytes"])
    workspace = int(gate["requested_workspace_bytes"])
    future = int(gate["future_all_q_and_transform_reserve_bytes"])
    fixed = int(gate["fixed_future_workspace_headroom_bytes"])
    cap = int(gate["dynamic_launch_cap_bytes"])
    projected = current + additional + workspace + future + fixed
    incremental = additional + workspace + future + fixed
    headroom = cap - current
    return {
        "equation": "R_live + Delta_payload + W_conversion + R_future + H_fixed <= C_dynamic",
        "current_process_tree_rss_bytes": current,
        "requested_additional_payload_bytes": additional,
        "requested_conversion_workspace_bytes": workspace,
        "future_co_resident_reserve_bytes": future,
        "fixed_workspace_headroom_bytes": fixed,
        "projected_process_tree_rss_bytes": projected,
        "dynamic_launch_cap_bytes": cap,
        "total_rss_deficit_bytes": max(projected - cap, 0),
        "incremental_required_bytes": incremental,
        "incremental_headroom_bytes": headroom,
        "incremental_deficit_bytes": max(incremental - headroom, 0),
        "both_inequalities_pass": projected <= cap and incremental <= headroom,
    }


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _finite_nonnegative_below(value: Any, limit: float) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= limit
    )


def _v22_completed_probe_checks(
    receipt: Mapping[str, Any], probe: Mapping[str, Any]
) -> dict[str, bool]:
    """Recompute a V22 completion from bound raw coverage, FE/MPC, and error fields."""

    descriptor = probe.get("descriptor")
    descriptor = descriptor if isinstance(descriptor, Mapping) else {}
    p6_space = probe.get("p6_space")
    p6_space = p6_space if isinstance(p6_space, Mapping) else {}
    mpc = descriptor.get("global_mpc_identity")
    mpc = mpc if isinstance(mpc, Mapping) else {}
    witness = probe.get("operator_witness")
    witness = witness if isinstance(witness, Mapping) else {}
    coverage = witness.get("mode_coverage")
    coverage = coverage if isinstance(coverage, Mapping) else {}
    expected_by_side = {"bottom": 16_030, "top": 16_030}
    native = witness.get("native_882_row_calibration_by_side")
    native = native if isinstance(native, Mapping) else {}
    generated = witness.get("generated_p6_api_witness")
    generated = generated if isinstance(generated, Mapping) else {}
    independent_packets = generated.get("independent_saved_full_row_packet_reference")
    independent_packets = (
        independent_packets if isinstance(independent_packets, Mapping) else {}
    )
    crossmode = generated.get("same_cell_s_p_crossmode")
    crossmode = crossmode if isinstance(crossmode, Mapping) else {}
    q_consumer = generated.get("local_q_row_tile_consumer")
    q_consumer = q_consumer if isinstance(q_consumer, Mapping) else {}
    coverage_target = probe.get("mode_coverage_target")
    coverage_target = coverage_target if isinstance(coverage_target, Mapping) else {}

    hashes = (
        descriptor.get("mode_manifest_sha256"),
        descriptor.get("ordered_mode_key_sha256"),
        descriptor.get("saved_mesh_xdmf_sha256"),
        descriptor.get("saved_mesh_h5_sha256"),
        descriptor.get("saved_boundary_mapping_sha256"),
        descriptor.get("actual_cell_dofmap_sha256"),
        mpc.get("slave_rows_sha256"),
        mpc.get("master_local_indices_sha256"),
        mpc.get("coefficients_sha256"),
        mpc.get("offsets_sha256"),
    )
    receipt_source = receipt.get("source_sha")
    probe_source = probe.get("source_sha")
    receipt_input = receipt.get("input_sha256")
    probe_input = probe.get("input_sha256")
    receipt_physical = receipt.get("physical_model_sha256")
    probe_physical = probe.get("physical_model_sha256")

    full_rows = 20_181_348
    independent_rows = 19_897_344
    calibration_passed = set(native) == {"bottom", "top"} and all(
        isinstance(native.get(side), Mapping)
        and native[side].get("status")
        == "MEASURED_RAW_PACKET_AND_PRODUCTION_SUPPORT_PATH_CONSISTENCY"
        and native[side].get("independent_reference") is False
        and _finite_nonnegative_below(native[side].get("production_B_relative"), 1e-10)
        and _finite_nonnegative_below(native[side].get("production_D_relative"), 1e-10)
        and _finite_nonnegative_below(
            native[side].get("production_D_vector_relative"), 1e-10
        )
        and native[side].get("production_B_path_consistency_only") is True
        and isinstance(native[side].get("production_B_reference_domain"), str)
        and isinstance(native[side].get("production_D_reference_domain"), str)
        and isinstance(native[side].get("production_B_support_digest"), Mapping)
        and native[side].get("production_D_path_consistency_only") is True
        and isinstance(native[side].get("production_D_support_digest"), Mapping)
        and all(
            _is_sha256(native[side]["production_B_support_digest"].get(name))
            for name in (
                "direct_rows_sha256",
                "grouped_rows_sha256",
                "direct_values_sha256",
                "grouped_values_sha256",
            )
        )
        and all(
            _is_sha256(native[side]["production_D_support_digest"].get(name))
            for name in (
                "direct_rows_sha256",
                "grouped_rows_sha256",
                "direct_values_sha256",
                "grouped_values_sha256",
            )
        )
        and isinstance(native[side].get("production_B_support_mismatch_count"), int)
        and not isinstance(native[side].get("production_B_support_mismatch_count"), bool)
        and isinstance(native[side].get("production_D_support_mismatch_count"), int)
        and not isinstance(native[side].get("production_D_support_mismatch_count"), bool)
        for side in ("bottom", "top")
    )
    direct_support_qualification = probe.get("production_support")
    direct_support_qualification = (
        direct_support_qualification
        if isinstance(direct_support_qualification, Mapping)
        else {}
    ).get("direct_filtered_support_qualification")
    direct_support_qualification = (
        direct_support_qualification
        if isinstance(direct_support_qualification, Mapping)
        else {}
    )
    support_mismatch_counts_valid = set(native) == {"bottom", "top"}
    recomputed_support_mismatches: dict[str, dict[str, int]] = {}
    for side in ("bottom", "top"):
        side_record = native.get(side)
        side_record = side_record if isinstance(side_record, Mapping) else {}
        b_mismatch = side_record.get("production_B_support_mismatch_count")
        d_mismatch = side_record.get("production_D_support_mismatch_count")
        if not all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in (b_mismatch, d_mismatch)
        ):
            support_mismatch_counts_valid = False
        else:
            recomputed_support_mismatches[side] = {"B": b_mismatch, "D": d_mismatch}
    support_mismatch_detected = any(
        count > 0
        for side_counts in recomputed_support_mismatches.values()
        for count in side_counts.values()
    )
    expected_support_qualification_status = (
        "PARTIAL_SUPPORT_MISMATCH"
        if support_mismatch_detected
        else "MATCHED_ON_TWO_CALIBRATED_MODES"
    )
    support_exactness_remains_partial = (
        support_mismatch_counts_valid
        and direct_support_qualification.get("production_exact_qualification") == "PARTIAL"
        and direct_support_qualification.get("status")
        == expected_support_qualification_status
        and direct_support_qualification.get("support_mismatch_count_by_side")
        == recomputed_support_mismatches
    )
    independent_packet_passed = (
        independent_packets.get("status")
        == "PASS_HASH_BOUND_SAVED_DEGREE60_FULL_ROW_B_D_PACKETS"
        and independent_packets.get("quadrature_degree_by_side")
        == {"bottom": 60, "top": 60}
        and independent_packets.get("full_local_rows_by_side")
        == {"bottom": 882, "top": 882}
        and independent_packets.get("independent_B_D_construction_by_side")
        == {"bottom": True, "top": True}
        and set(independent_packets.get("mode_indices_by_side", {}))
        == {"bottom", "top"}
        and set(independent_packets.get("actual_cell_ids_by_side", {}))
        == {"bottom", "top"}
        and set(independent_packets.get("actual_class_ids_by_side", {}))
        == {"bottom", "top"}
        and set(independent_packets.get("packet_npz_sha256_by_side", {}))
        == {"bottom", "top"}
        and set(independent_packets.get("B_relative_to_live_native_by_side", {}))
        == {"bottom", "top"}
        and set(independent_packets.get("D_relative_to_live_native_by_side", {}))
        == {"bottom", "top"}
        and all(
            _is_sha256(independent_packets["packet_npz_sha256_by_side"][side])
            and _finite_nonnegative_below(
                independent_packets["B_relative_to_live_native_by_side"][side], 1e-10
            )
            and _finite_nonnegative_below(
                independent_packets["D_relative_to_live_native_by_side"][side], 1e-10
            )
            and isinstance(independent_packets["mode_indices_by_side"][side], int)
            and not isinstance(independent_packets["mode_indices_by_side"][side], bool)
            and isinstance(independent_packets["actual_cell_ids_by_side"][side], int)
            and not isinstance(independent_packets["actual_cell_ids_by_side"][side], bool)
            and isinstance(independent_packets["actual_class_ids_by_side"][side], str)
            and independent_packets["actual_class_ids_by_side"][side] != "UNAVAILABLE"
            for side in ("bottom", "top")
        )
    )
    b_alpha = witness.get("B_alpha")
    b_alpha = b_alpha if isinstance(b_alpha, Mapping) else {}
    return {
        "v22_source_input_physical_bindings_match": (
            isinstance(receipt_source, str)
            and len(receipt_source) == 40
            and all(char in "0123456789abcdef" for char in receipt_source)
            and probe_source == receipt_source
            and probe_input == receipt_input
            and probe_physical == receipt_physical
            and descriptor.get("staged_input_sha256") == receipt_input
            and descriptor.get("physical_model_sha256") == receipt_physical
            and descriptor.get("mode_manifest_sha256") == probe.get("mode_manifest_sha256")
        ),
        "v22_saved_mesh_dofmap_and_mpc_identity_complete": (
            p6_space.get("cell_count") == 30_464
            and p6_space.get("cell_dof_dimension") == 882
            and p6_space.get("global_storage_rows") == full_rows
            and p6_space.get("global_independent_rows") == independent_rows
            and p6_space.get("interior_rows_per_cell") == 450
            and p6_space.get("trace_rows_per_cell") == 432
            and mpc.get("global_storage_rows") == full_rows
            and mpc.get("global_independent_rows") == independent_rows
            and mpc.get("owned_slave_count") == full_rows - independent_rows
            and mpc.get("mpc_finalized") is True
            and mpc.get("coefficient_count", 0) > 0
            and isinstance(mpc.get("offset_count"), int)
            and not isinstance(mpc.get("offset_count"), bool)
            and mpc["offset_count"] >= 0
            and all(_is_sha256(value) for value in hashes)
        ),
        "v22_mode_coverage_recomputed": (
            coverage.get("expected") == 32_060
            and coverage.get("completed") == 32_060
            and coverage.get("completed_by_side") == expected_by_side
            and coverage_target.get("expected_mode_count") == 32_060
            and coverage_target.get("expected_by_side") == expected_by_side
            and b_alpha.get("mode_count") == 32_060
            and b_alpha.get("mode_count_by_side") == expected_by_side
        ),
        "v22_both_native_error_gates_recomputed": calibration_passed,
        "v22_direct_filtered_support_exactness_remains_partial": (
            support_exactness_remains_partial
        ),
        "v22_independent_saved_full_row_packets_bound": independent_packet_passed,
        "v22_generated_factory_and_q_consumer_connected": (
            generated.get("status") == "PASS_GENERATED_FACTORY_AND_BOUNDED_Q_TILES"
            and generated.get("P6CellCondensedAction_factory_connected") is True
            and generated.get("row_tile_q_consumer_connected") is True
            and crossmode.get("consumed_by_local_q11_tile") is True
            and isinstance(crossmode.get("Hhat_only_s_p_projection"), list)
            and isinstance(crossmode.get("full_q11_s_p_projection"), list)
            and q_consumer.get("trace_only_selector") is True
            and q_consumer.get("same_cell_s_p_port_only_selector") is True
            and q_consumer.get("Hhat_only_projection_recorded_independently") is True
            and q_consumer.get("full_port_port_tile_recorded") is True
            and independent_packet_passed
        ),
        "v22_q_factor_ksp_and_full_field_still_unbuilt": (
            probe.get("expected_q_count") == 8
            and probe.get("built_q_count") == 0
            and probe.get("q_csr_created") is False
            and probe.get("factor_created") is False
            and probe.get("ksp_created") is False
            and probe.get("pde_solved") is False
            and witness.get("all_q_csr_factor_ksp_and_full_field") == "NOT_RUN"
        ),
    }


def validate_stage_receipt_semantics(
    receipt: Mapping[str, Any],
    *,
    expected_stage: str,
    heavy_authorized: bool | None,
    output_directory: str | Path | None = None,
    operator_probe_authorized: bool | None = None,
) -> dict[str, bool]:
    """Check the four v2 partial outcomes; none can be promoted to a full result."""

    attempted = receipt.get("attempted_stages")
    completed = receipt.get("completed_stages")
    attempted = attempted if isinstance(attempted, list) else []
    completed = completed if isinstance(completed, list) else []
    order = {name: index for index, name in enumerate(V20_STAGE_ORDER)}

    def ordered_known(values: list[Any]) -> bool:
        return (
            all(isinstance(name, str) and name in order for name in values)
            and len(values) == len(set(values))
            and values == sorted(values, key=order.__getitem__)
        )

    outcome = receipt.get("outcome")
    checks = {
        "schema_v2": receipt.get("schema") == "task40extra.review_v20_partial_result.v2",
        "requested_stage_matches": receipt.get("requested_stop_stage") == expected_stage,
        "official_result_false": receipt.get("official_result") is False,
        "stage_lists_known_ordered": ordered_known(attempted) and ordered_known(completed),
        "completed_is_attempted_subset": all(stage in attempted for stage in completed),
        "outcome_supported": outcome
        in {"AUTH_NOT_GRANTED", "RESOURCE_CONTROLLED_STOP", "STAGE_COMPLETED", "STAGE_FAILED"},
    }
    artifact_hashes = receipt.get("artifact_hashes")
    artifact_hashes = artifact_hashes if isinstance(artifact_hashes, Mapping) else {}
    artifact_bindings_valid = True
    for name, item in artifact_hashes.items():
        if not isinstance(item, Mapping):
            artifact_bindings_valid = False
            break
        relative_path = Path(str(item.get("path", "")))
        digest = item.get("sha256")
        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            artifact_bindings_valid = False
            break
        if output_directory is not None:
            bound_path = Path(output_directory).resolve() / relative_path
            if not bound_path.is_file() or _sha256_file(bound_path) != digest:
                artifact_bindings_valid = False
                break
    q_coverage = receipt.get("q_coverage")
    q_coverage = q_coverage if isinstance(q_coverage, Mapping) else {}
    cleanup = receipt.get("cleanup")
    cleanup = cleanup if isinstance(cleanup, Mapping) else {}
    cleanup_passed = (
        cleanup.get("status") == "PASS"
        and cleanup.get("native_owners_released") is True
        and cleanup.get("process_descendants_cleared") is True
        and cleanup.get("temporary_stage_objects_released") is True
    )
    checks.update(
        {
            "artifact_hashes_well_formed_and_bound": artifact_bindings_valid,
            "q_coverage_state_explicit": q_coverage.get("status")
            in {"KNOWN", "UNKNOWN", "NOT_RUN"},
            "cleanup_state_explicit": cleanup.get("status")
            in {"PASS", "FAILED", "UNKNOWN", "NOT_RUN"},
        }
    )
    if expected_stage == "target_operator_probe":
        allowed_v22_stages = ["preflight", "geometry_inventory", "target_operator_probe"]
        attempted_prefix = attempted == allowed_v22_stages[: len(attempted)]
        completed_prefix = completed == allowed_v22_stages[: len(completed)]
        probe_facts = receipt.get("target_operator_probe")
        probe_facts = probe_facts if isinstance(probe_facts, Mapping) else {}
        blocked_task_stage = receipt.get("blocked_task_stage")
        checks.update(
            {
                "operator_probe_authorization_matches_outcome": (
                    operator_probe_authorized is (outcome != "AUTH_NOT_GRANTED")
                ),
                "heavy_authorization_remains_false": heavy_authorized is False,
                "v22_stage_prefix_order": attempted_prefix and completed_prefix,
                "v22_attempted_contains_only_registered_stages": all(
                    stage in allowed_v22_stages for stage in attempted
                ),
                "v22_completed_is_attempted_prefix": completed
                == attempted[: len(completed)],
                "v22_q_inventory_explicit": (
                    q_coverage.get("status") == "NOT_RUN"
                    and q_coverage.get("expected_q_count") == 8
                    and q_coverage.get("built_q_count") == 0
                ),
            }
        )
        if outcome == "AUTH_NOT_GRANTED":
            checks.update(
                {
                    "v22_authorization_denial_safe_prefix": (
                        operator_probe_authorized is False
                        and "target_operator_probe" not in attempted
                        and attempted == completed
                    ),
                    "v22_q_not_built": q_coverage.get("built_q_count") == 0,
                }
            )
        elif outcome == "RESOURCE_CONTROLLED_STOP":
            checks.update(
                {
                    "v22_resource_stage_is_partial": (
                        blocked_task_stage in {"geometry_inventory", "target_operator_probe"}
                        and blocked_task_stage in attempted
                        and blocked_task_stage not in completed
                    ),
                    "v22_resource_gate_present": isinstance(receipt.get("resource_gate"), Mapping),
                    "v22_resource_prefix_exact": attempted
                    == [*completed, blocked_task_stage],
                }
            )
        elif outcome == "STAGE_COMPLETED":
            stage_result = receipt.get("stage_result")
            stage_result = stage_result if isinstance(stage_result, Mapping) else {}
            checks.update(
                {
                    "v22_probe_stage_completed": attempted == allowed_v22_stages
                    and completed == allowed_v22_stages,
                    "v22_stage_marker_matches": stage_result.get("completed_stage")
                    == "target_operator_probe",
                    "v22_probe_status_passed": probe_facts.get("status")
                    == "PASS_ALL_MODE_B_D_STREAM_WITH_Q_UNBUILT",
                    "v22_q_remains_unbuilt": q_coverage.get("built_q_count") == 0,
                }
            )
            checks.update(_v22_completed_probe_checks(receipt, probe_facts))
        elif outcome == "STAGE_FAILED":
            failed_stage = receipt.get("failed_stage")
            checks.update(
                {
                    "v22_failed_stage_is_attempted_and_incomplete": (
                        failed_stage in {"geometry_inventory", "target_operator_probe"}
                        and failed_stage in attempted
                        and failed_stage not in completed
                    ),
                    "v22_failure_follows_exact_prefix": attempted
                    == [*completed, failed_stage],
                    "v22_failure_evidence_present": bool(
                        receipt.get("failure_message") or probe_facts.get("failure_message")
                    ),
                }
            )
        return checks

    if outcome == "AUTH_NOT_GRANTED":
        checks.update(
            {
                "authorization_denial_stopped_at_safe_prefix": (
                    attempted == completed
                    and "preflight" in completed
                    and expected_stage not in attempted
                    and all(order[name] < order[expected_stage] for name in attempted)
                ),
                "heavy_authorization_false": (
                    heavy_authorized is False
                    if expected_stage in {"build_and_symbolic", "one_q_numeric", "full"}
                    else True
                ),
                "q_coverage_not_run": q_coverage.get("status") == "NOT_RUN",
                "cleanup_not_run": cleanup.get("status") == "NOT_RUN",
            }
        )
    elif outcome == "RESOURCE_CONTROLLED_STOP":
        checks.update(
            {
                "resource_stage_was_attempted": expected_stage in attempted,
                "resource_stage_not_marked_complete": expected_stage not in completed,
                "resource_attempt_follows_completed_prefix": attempted
                == [*completed, expected_stage],
                "resource_gate_evidence_present": isinstance(receipt.get("resource_gate"), dict),
                "heavy_authorization_true": (
                    heavy_authorized is True
                    if expected_stage in {"build_and_symbolic", "one_q_numeric", "full"}
                    else True
                ),
                "resource_q_coverage_recorded": q_coverage.get("status") == "KNOWN"
                or q_coverage.get("status") == "UNKNOWN",
                "heavy_cleanup_proved": cleanup_passed,
            }
        )
    elif outcome == "STAGE_COMPLETED":
        stage_result = receipt.get("stage_result")
        stage_result = stage_result if isinstance(stage_result, Mapping) else {}
        checks.update(
            {
                "completed_stage_was_attempted": expected_stage in attempted,
                "requested_stage_marked_complete": expected_stage in completed,
                "completed_stage_matches_attempted_prefix": attempted == completed,
                "worker_stage_marker_matches": stage_result.get("completed_stage")
                == expected_stage,
                "heavy_authorization_true": (
                    heavy_authorized is True
                    if expected_stage in {"build_and_symbolic", "one_q_numeric", "full"}
                    else True
                ),
                "q_coverage_unknown_or_known": q_coverage.get("status")
                in {"KNOWN", "UNKNOWN", "NOT_RUN"},
            }
        )
        if expected_stage in {"build_and_symbolic", "one_q_numeric"}:
            q_inventory = q_coverage.get("q_csr_inventory")
            checks["all_q_symbolic_coverage_proved"] = (
                stage_result.get("all_q_symbolic_covered") is True
            )
            checks["q_csr_hashes_complete"] = (
                q_coverage.get("status") == "KNOWN"
                and isinstance(q_inventory, Mapping)
                and len(q_inventory) == 4
                and set(q_inventory) == {"0", "1", "2", "3"}
                and all(
                    isinstance(row, Mapping)
                    and isinstance(row.get("csr_sha256"), str)
                    and len(row["csr_sha256"]) == 64
                    and all(char in "0123456789abcdef" for char in row["csr_sha256"])
                    for row in q_inventory.values()
                )
            )
            checks["q_csr_inventory_matches_stage_result"] = (
                isinstance(stage_result.get("q_csr_inventory"), Mapping)
                and dict(q_inventory or {}) == dict(stage_result["q_csr_inventory"])
            )
            checks["q_csr_inventory_bound_to_candidate_summary"] = any(
                item.get("path") == "task40_v10_p6_candidate_summary.json"
                for item in artifact_hashes.values()
                if isinstance(item, Mapping)
            )
            checks["heavy_cleanup_proved"] = cleanup_passed
        else:
            checks["q_assembly_not_claimed"] = q_coverage.get("status") == "NOT_RUN"
        if expected_stage == "build_and_symbolic":
            checks["no_numeric_factor_claim"] = stage_result.get(
                "numeric_factor_build_attempt_count"
            ) == 0
        elif expected_stage == "one_q_numeric":
            checks["selected_q_is_zero"] = stage_result.get("selected_q") == 0
            checks["one_numeric_build_only"] = stage_result.get(
                "numeric_factor_build_attempt_count"
            ) == 1
    elif outcome == "STAGE_FAILED":
        failure = receipt.get("error") or receipt.get("failure_message")
        checks.update(
            {
                "failed_stage_was_attempted": expected_stage in attempted,
                "failed_stage_not_marked_complete": expected_stage not in completed,
                "failed_stage_follows_completed_prefix": attempted
                == [*completed, expected_stage],
                "failed_stage_identity_matches": receipt.get("failed_stage") == expected_stage,
                "failure_evidence_present": bool(failure),
                "heavy_authorization_true": (
                    heavy_authorized is True
                    if expected_stage in {"build_and_symbolic", "one_q_numeric", "full"}
                    else True
                ),
                "q_coverage_state_does_not_claim_missing_data": q_coverage.get("status")
                in {"KNOWN", "UNKNOWN", "NOT_RUN"},
            }
        )
    return checks


def _read_resource_gate(candidate_summary: Mapping[str, Any]) -> dict[str, Any]:
    error = candidate_summary.get("error")
    message = error.get("message") if isinstance(error, Mapping) else None
    marker = "Task40 V12 two-boundary memory admission failed: "
    if not isinstance(message, str) or marker not in message:
        raise ValueError("candidate summary does not contain the recorded E2 resource admission")
    payload = ast.literal_eval(message.split(marker, 1)[1])
    if not isinstance(payload, dict):
        raise ValueError("E2 admission evidence is not a mapping")
    return payload


def recheck_e2_run(run_directory: str | Path) -> dict[str, Any]:
    """Recompute the E2 raw-evidence stop and hashes; never write into the run directory."""

    run_dir = Path(run_directory).resolve()
    manifest_path = run_dir / "run_manifest.json"
    summary_path = run_dir / "run_summary.json"
    candidate_path = run_dir / "task40_v10_p6_candidate_summary.json"
    row_inventory_path = run_dir / "v20_one_q_row_tile_p6_reference_inventory.json"
    events_path = run_dir / "v20_one_q_row_tile_p6_reference_events.jsonl"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    row_inventory = json.loads(row_inventory_path.read_text(encoding="utf-8"))

    event_counts: Counter[str] = Counter()
    q_ready: dict[str, Any] | None = None
    admission: dict[str, Any] | None = None
    event_lines = 0
    event_hash = hashlib.sha256()
    with events_path.open("rb") as stream:
        for raw_line in stream:
            event_hash.update(raw_line)
            event_lines += 1
            event = json.loads(raw_line)
            kind = event.get("event")
            if not isinstance(kind, str):
                raise ValueError("E2 event log contains a record without a string event type")
            event_counts[kind] += 1
            if kind == "task40_v17_q_csr_all_ready":
                if q_ready is not None:
                    raise ValueError("E2 event log contains duplicate all-q CSR completion events")
                q_ready = event
            elif kind == "task40_v19_one_q_admission_request":
                if admission is not None:
                    raise ValueError("E2 event log contains duplicate first-q symbolic requests")
                admission = event

    if q_ready is None or admission is None:
        raise ValueError("E2 raw events omit the all-q CSR completion or first symbolic admission")
    q_facts = q_ready["facts"]
    owner = q_facts["q_matrix_owner_inventory"]
    by_block = owner["by_block"]
    q_rows = []
    for q in range(4):
        row = by_block[str(q)]
        stored = int(row["stored_slots"])
        nnz = int(row["numeric_nonzero_entries"])
        zero = int(row["exact_zero_slots_retained"])
        rows = int(row["shape"][0])
        itemsize_payload = stored * (16 + 4) + (rows + 1) * 4
        q_rows.append(
            {
                "q": q,
                "shape": row["shape"],
                "stored_slots": stored,
                "numeric_nonzero_entries": nnz,
                "exact_zero_slots_retained": zero,
                "visible_csr_payload_bytes": int(row["visible_csr_payload_bytes"]),
                "payload_formula_recomputed_bytes": itemsize_payload,
                "payload_formula_matches": itemsize_payload
                == int(row["visible_csr_payload_bytes"]),
                "slot_count_matches": stored == nnz + zero,
            }
        )
    total_stored = sum(row["stored_slots"] for row in q_rows)
    total_nnz = sum(row["numeric_nonzero_entries"] for row in q_rows)
    total_zero = sum(row["exact_zero_slots_retained"] for row in q_rows)
    total_payload = sum(row["visible_csr_payload_bytes"] for row in q_rows)

    admission_facts = admission["facts"]
    gate = _read_resource_gate(candidate)
    gate_recomputed = recompute_admission_gate(gate)
    expected_event_gates = {
        "additional_payload_matches": int(admission_facts["additional_payload_bytes"])
        == int(gate["requested_additional_bytes"]),
        "workspace_matches": int(admission_facts["workspace_bytes"])
        == int(gate["requested_workspace_bytes"]),
        "future_reserve_matches": int(admission_facts["future_co_resident_reserve_bytes"])
        == int(gate["future_all_q_and_transform_reserve_bytes"]),
        "stop_is_q0_symbolic_admission": admission_facts.get("q") == 0
        and admission_facts.get("stage") == "symbolic_admission",
        "all_q_csr_was_retained": admission_facts.get("all_q_source_csr_retained") is True,
        "symbolic_all_q_not_yet_covered": admission_facts.get(
            "all_q_symbolic_covered_before_numeric"
        ) is False,
    }
    footer_path = run_dir / "v20_partial_result.json"
    official_output_path = run_dir / "v10_candidate_official_output.json"
    checks = {
        "run_identity_matches": manifest.get("run_id") == run_summary.get("run_id")
        == candidate.get("run_id", manifest.get("run_id")),
        "candidate_source_matches_manifest": candidate.get("source_sha")
        == manifest.get("source_sha"),
        "all_four_q_csr_recorded": q_facts.get("all_four_q_matrices") is True
        and q_facts.get("all_q_matrices") is True
        and q_facts.get("q_count") == 4
        and set(by_block) == {"0", "1", "2", "3"},
        "q_csr_payload_arithmetic_matches": all(
            row["payload_formula_matches"] and row["slot_count_matches"] for row in q_rows
        ),
        "q_csr_aggregate_matches_owner_inventory": total_payload
        == int(owner["unique_array_backings"]["unique_backing_bytes"])
        and total_stored
        == sum(int(row["stored_slots"]) for row in by_block.values())
        and total_nnz + total_zero == total_stored,
        "event_gate_inputs_match_worker_error": all(expected_event_gates.values()),
        "resource_admission_recomputed_as_stop": not gate_recomputed["both_inequalities_pass"]
        and gate_recomputed["total_rss_deficit_bytes"] == 149_505_816
        and gate_recomputed["incremental_deficit_bytes"] == 149_505_816,
        "worker_classification_preserved": candidate.get("result_classification")
        == "RESOURCE_CONTROLLED_STOP"
        and candidate.get("status") == "CONTROLLED_STOP"
        and candidate.get("official_result") is False,
        "outer_failure_preserved": manifest.get("exit_status") == 4
        and manifest.get("result_classification") == "WORKER_FAILED"
        and run_summary.get("exit_status") == 4
        and run_summary.get("result_classification") == "WORKER_FAILED",
        "historical_footer_absence_preserved": not footer_path.exists(),
        "official_output_not_created": not official_output_path.exists(),
        "event_counts_match_expected": event_lines == 97_311
        and event_counts["task40_v17_q_csr_all_ready"] == 1
        and event_counts["task40_v19_one_q_admission_request"] == 1
        and event_counts["v10_strict_allocation_admission"] == 32_433
        and event_counts["v10_strict_allocation_admission_complete"] == 32_432,
    }
    return {
        "schema": "task40extra.review_v21_e2_readonly_recheck.v1",
        "status": "E2_PARTIAL_RESOURCE_STOP_RECHECKED"
        if all(checks.values())
        else "E2_PARTIAL_RECHECK_INVALID",
        "checker_passed": all(checks.values()),
        "official_result": False,
        "run_identity": {
            "run_id": manifest.get("run_id"),
            "source_sha": manifest.get("source_sha"),
            "input_sha256": manifest.get("input_sha256"),
            "physical_model_sha256": manifest.get("physical_model_sha256"),
            "exit_status": manifest.get("exit_status"),
            "outer_result_classification": manifest.get("result_classification"),
        },
        "raw_artifacts": {
            "run_directory": str(run_dir),
            "run_manifest_sha256": _sha256_file(manifest_path),
            "run_summary_sha256": _sha256_file(summary_path),
            "candidate_summary_sha256": _sha256_file(candidate_path),
            "row_inventory_sha256": _sha256_file(row_inventory_path),
            "events_path": str(events_path),
            "events_sha256": event_hash.hexdigest(),
            "events_bytes": events_path.stat().st_size,
            "events_line_count": event_lines,
            "input_path": manifest.get("input_path"),
            "input_sha256_readback": _sha256_file(Path(manifest["input_path"]))
            if Path(str(manifest.get("input_path", ""))).is_file()
            else None,
            "partial_footer_path": str(footer_path),
            "partial_footer_exists": footer_path.exists(),
        },
        "saved_event_counts": dict(sorted(event_counts.items())),
        "all_q_csr": {
            "q_count": q_facts.get("q_count"),
            "q_matrices": q_rows,
            "total_stored_slots": total_stored,
            "total_numeric_nonzero_entries": total_nnz,
            "total_exact_zero_slots_retained": total_zero,
            "unique_backing_bytes": owner["unique_array_backings"]["unique_backing_bytes"],
            "zero_cleanup": owner["zero_cleanup"],
            "per_q_csr_content_hashes": "UNKNOWN_NOT_PERSISTED_IN_THE_SAVED_EVENT_RECORD",
        },
        "first_symbolic_admission": {
            "q": admission_facts.get("q"),
            "stage": admission_facts.get("stage"),
            "event_inputs": {
                "additional_payload_bytes": admission_facts.get("additional_payload_bytes"),
                "workspace_bytes": admission_facts.get("workspace_bytes"),
                "future_co_resident_reserve_bytes": admission_facts.get(
                    "future_co_resident_reserve_bytes"
                ),
            },
            "gate_recomputed": gate_recomputed,
            "worker_gate_inputs": {
                key: gate.get(key)
                for key in (
                    "requested_additional_bytes",
                    "requested_workspace_bytes",
                    "future_all_q_and_transform_reserve_bytes",
                    "fixed_future_workspace_headroom_bytes",
                    "current_process_tree_rss_bytes",
                    "dynamic_launch_cap_bytes",
                    "projected_process_tree_rss_bytes",
                    "total_rss_inequality_passed",
                    "incremental_headroom_inequality_passed",
                )
            },
        },
        "historical_outcomes": {
            "worker_status": candidate.get("status"),
            "worker_result_classification": candidate.get("result_classification"),
            "old_partial_checker_status": "NO_PARTIAL_FOOTER"
            if not footer_path.exists()
            else "FOOTER_PRESENT_REQUIRES_ORIGINAL_CHECKER",
            "old_partial_checker_passed": False if not footer_path.exists() else None,
            "numeric_factor": "NOT_RUN",
            "KSP": "NOT_RUN",
            "field": "NOT_RUN",
            "official_R_T_A": "NOT_RUN",
            "cleanup_status": "UNKNOWN_NO_VERIFIABLE_NATIVE_OWNER_AND_DESCENDANT_FOOTER",
        },
        "checks": checks,
        "errors": [name for name, passed in checks.items() if not passed]
        + [name for name, passed in expected_event_gates.items() if not passed],
        "read_only": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    receipt = recheck_e2_run(args.run_directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": receipt["status"], "errors": receipt["errors"]}, sort_keys=True))
    return 0 if receipt["checker_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
