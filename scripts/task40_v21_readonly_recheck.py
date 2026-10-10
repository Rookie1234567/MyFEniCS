"""Read-only V21 receipts for historical E2 evidence and V20 stage outcomes."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


V20_STAGE_ORDER = (
    "preflight",
    "geometry_inventory",
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


def validate_stage_receipt_semantics(
    receipt: Mapping[str, Any],
    *,
    expected_stage: str,
    heavy_authorized: bool | None,
    output_directory: str | Path | None = None,
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
