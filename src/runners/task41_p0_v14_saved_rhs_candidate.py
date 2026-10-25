"""Run the bounded V14 same-LU RHS candidate on hash-bound saved arrays."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Mapping

import numpy as np

from src.runners.task41_p0_contract import sha256_file
from src.runners.task41_p0_v4_volume_only_audit import (
    TASK41_P0_V11_METADATA_ACTIVE_ROW,
    TASK41_P0_V11_METADATA_ORIGINAL_ROW,
)
from src.runners.task41_p0_v14_candidate_io import (
    V14_CANDIDATE_REPORT_SCHEMA,
    V14_CELLS,
    V14_COLUMNS,
    V14_SOURCE_WINDOW_SHA256,
    load_v14_saved_candidate_inputs,
    v14_matrix_identity_token,
)
from src.solvers.hcurl_assembly_time_condensation import project_internal_rhs_same_lu

V14_EVIDENCE_LIMIT_BYTES = 16 * 1024**2


def _atomic_npy(path: Path, value: np.ndarray) -> dict[str, Any]:
    if path.exists():
        raise FileExistsError(f"V14 candidate evidence already exists: {path.name}")
    temporary = path.with_name(f".{path.name}.tmp")
    if temporary.exists():
        raise FileExistsError(f"V14 candidate temporary evidence already exists: {temporary.name}")
    with temporary.open("xb") as stream:
        np.save(stream, np.asarray(value), allow_pickle=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return {
        "path": str(path),
        "name": path.name,
        "shape": list(np.asarray(value).shape),
        "dtype": str(np.asarray(value).dtype),
        "bytes": int(path.stat().st_size),
        "sha256": sha256_file(path),
    }


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> str:
    if path.exists():
        raise FileExistsError(f"V14 candidate JSON already exists: {path.name}")
    temporary = path.with_name(f".{path.name}.tmp")
    if temporary.exists():
        raise FileExistsError(f"V14 candidate temporary JSON already exists: {temporary.name}")
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    with temporary.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return sha256_file(path)


def _json_scalar(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def execute_candidate_rhs(
    *,
    output_dir: Path,
    label: str,
    factor: tuple[np.ndarray, np.ndarray],
    actual_trace_interior: np.ndarray,
    internal_rhs: np.ndarray,
    actual_internal_matrix: np.ndarray,
    matrix_identity: str,
    evidence_budget: list[int],
    expected_initial: np.ndarray,
) -> dict[str, Any]:
    """Call the production core and durably persist every callback before continuing."""
    if not label or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in label):
        raise ValueError("V14 candidate label contains unsafe filename characters")
    event_log = output_dir / f"{label}_steps.jsonl"
    if event_log.exists():
        raise FileExistsError(f"V14 candidate event log already exists: {event_log.name}")
    array_records: list[dict[str, Any]] = []
    initial_z_ref: dict[str, Any] | None = None
    initial_z_value: np.ndarray | None = None
    with event_log.open("x", encoding="utf-8") as events:
        def persist(record: Mapping[str, Any]) -> None:
            nonlocal initial_z_ref, initial_z_value
            saved: dict[str, Any] = {"event": str(record.get("event"))}
            for field in (
                "solved", "correction", "z_before", "residual", "delta", "z_after"
            ):
                value = record.get(field)
                if value is None:
                    continue
                if (
                    record.get("event") == "initial" and field == "solved"
                    and expected_initial is not None
                    and not np.array_equal(value, expected_initial)
                ):
                    raise ValueError(f"V14 {label} initial z does not equal the frozen saved z_b")
                if not isinstance(value, np.ndarray):
                    raise TypeError(f"V14 core callback field {field} is not an ndarray")
                filename = f"{label}_{record.get('event')}_{record.get('step', 0)}_{field}.npy"
                ref = _atomic_npy(output_dir / filename, value)
                if record.get("event") == "initial" and field == "solved":
                    initial_z_ref = ref
                    initial_z_value = np.asarray(value, dtype=np.complex128).copy()
                saved[field] = ref
                array_records.append(ref)
                evidence_budget[0] += int(ref["bytes"])
                if evidence_budget[0] > V14_EVIDENCE_LIMIT_BYTES:
                    raise RuntimeError("V14 candidate evidence exceeded the 16 MiB package cap")
            for key in (
                "step", "stop_reason", "initial_getrs_count", "correction_getrs_count",
                "getrs_count", "residual_evaluation_count", "initial_getrs_seconds",
                "correction_getrs_seconds", "residual_seconds", "update_seconds",
            ):
                if key in record:
                    saved[key] = _json_scalar(record[key])
            events.write(json.dumps(saved, sort_keys=True, allow_nan=False) + "\n")
            events.flush()
            os.fsync(events.fileno())

        z, correction, timing = project_internal_rhs_same_lu(
            factor,
            actual_trace_interior,
            internal_rhs,
            refinement_max_steps=2,
            actual_internal_matrix=actual_internal_matrix,
            actual_internal_matrix_identity=matrix_identity,
            factor_matrix_identity=matrix_identity,
            step_callback=persist,
        )
    if initial_z_ref is None or initial_z_value is None:
        raise RuntimeError(f"V14 {label} core callback omitted the initial same-LU solution")
    return {
        "label": label,
        "initial_z": initial_z_value,
        "initial_z_ref": initial_z_ref,
        "final_z": np.asarray(z, dtype=np.complex128),
        "returned_correction": np.asarray(correction, dtype=np.complex128),
        "timing": timing,
        "event_log": {
            "path": str(event_log),
            "bytes": int(event_log.stat().st_size),
            "sha256": sha256_file(event_log),
        },
        "callback_arrays": array_records,
    }


def _identity_token(source: Mapping[str, Any], cell: int) -> str:
    return v14_matrix_identity_token(source, cell)


def run_v14_saved_candidate(
    *,
    source: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output = Path(output_dir).resolve()
    if not output.is_relative_to(source["results_root"]):
        raise ValueError("V14 candidate output must stay under the Task41 results root")
    output.mkdir(parents=True, exist_ok=False)
    evidence_budget = [0]
    cell_order = tuple(int(value) for value in source.get("cell_order", V14_CELLS))
    columns = tuple(int(value) for value in source.get("columns", V14_COLUMNS))
    stage = str(source.get("stage", "initial_screen"))
    state_rows = list(source.get("state_rows") or [
        {"column": column, "state": "j0" if column == 0 else "j3"}
        for column in columns
    ])
    marker = {
        "schema": "task41.p0.v14.saved_same_lu_rhs_candidate_started.v1",
        "stage": stage,
        "consumer_contract_sha256": source["consumer_contract_sha256"],
        "consumer_window_sha256": source["consumer_window_sha256"],
        "producer_report_sha256": source["producer_report_sha256"],
        "star_producer_report_sha256": source.get("star_producer_report_sha256"),
        "official_result": False,
    }
    _atomic_json(output / "candidate_started.json", marker)
    rhs_results: dict[tuple[int, int], dict[str, Any]] = {}
    getrs_total = 0
    core_started = time.perf_counter()
    for column in columns:
        for cell in cell_order:
            local = source["cells"][cell]
            term = local["column_terms"][column]
            identity = _identity_token(source, cell)
            result = execute_candidate_rhs(
                output_dir=output,
                label=f"cell{cell}_column{column}",
                factor=(local["LU"], local["pivots"]),
                actual_trace_interior=local["J"],
                internal_rhs=term["b_i"],
                actual_internal_matrix=local["K"],
                matrix_identity=identity,
                evidence_budget=evidence_budget,
                expected_initial=term.get("old_z_b"),
            )
            projection = np.asarray(
                local["trace_expansion"].conj().T @ result["returned_correction"],
                dtype=np.complex128,
            ).reshape(-1)
            baseline_correction = np.asarray(
                -(local["J"] @ result["initial_z"]), dtype=np.complex128
            )
            baseline_projection = np.asarray(
                local["trace_expansion"].conj().T @ baseline_correction,
                dtype=np.complex128,
            ).reshape(-1)
            projection_ref = _atomic_npy(
                output / f"cell{cell}_column{column}_projected_active.npy", projection
            )
            final_z_ref = _atomic_npy(
                output / f"cell{cell}_column{column}_final_z.npy", result["final_z"]
            )
            correction_ref = _atomic_npy(
                output / f"cell{cell}_column{column}_returned_correction.npy",
                result["returned_correction"],
            )
            evidence_budget[0] += projection_ref["bytes"] + final_z_ref["bytes"] + correction_ref["bytes"]
            if evidence_budget[0] > V14_EVIDENCE_LIMIT_BYTES:
                raise RuntimeError("V14 candidate evidence exceeded the 16 MiB package cap")
            rhs_results[(cell, column)] = {
                "cell_index": cell,
                "column": column,
                "matrix_identity": identity,
                "b_i": term["b_i_ref"],
                "old_z_b": term.get("old_z_b_ref"),
                "baseline_mode": (
                    "same_run_initial_core_solve"
                    if term.get("old_z_b") is None else "accepted_saved_v11_same_lu_initial"
                ),
                "baseline_z": result["initial_z_ref"],
                "actual_coordinate_sha256": local["actual_coordinate_sha256"],
                "oriented_tensor": local["tensor_ref"],
                "interior_lu": local["lu_ref"],
                "initial_and_step_log": result["event_log"],
                "callback_arrays": result["callback_arrays"],
                "final_z": final_z_ref,
                "returned_correction": correction_ref,
                "projected_active": projection_ref,
                "timing": result["timing"],
                "baseline_projected_active": baseline_projection,
            }
            getrs_total += int(result["timing"].get("getrs_count", 0))

    column_summaries: list[dict[str, Any]] = []
    for state_row in state_rows:
        column = int(state_row["column"])
        state = str(state_row["state"])
        if column not in columns:
            raise ValueError(f"V14 state row refers to unselected column {column}")
        extension = stage == "saved_star_extension"
        y = (
            source["y_by_column_state"][(column, state)]
            if extension else source["y_by_column"][column]
        )
        base_g = complex(source["b_t_by_column"][column])
        candidate_g = complex(source["b_t_by_column"][column])
        baseline_terms: list[complex] = []
        candidate_terms: list[complex] = []
        action_sources: list[dict[str, Any]] = []
        for cell in cell_order:
            local = source["cells"][cell]
            term = local["column_terms"][column]
            if extension:
                action_term = term["state_terms"][state]
                action_ref = action_term["s_action_ref"]
                baseline_projected = rhs_results[(cell, column)]["baseline_projected_active"]
            else:
                action_ref = term["s_action_ref"]
                baseline_projected = np.asarray(
                    local["trace_expansion"].conj().T @ term["old_correction"],
                    dtype=np.complex128,
                ).reshape(-1)
            new_ref = rhs_results[(cell, column)]["projected_active"]
            new_active = np.load(new_ref["path"], mmap_mode="r", allow_pickle=False)
            baseline_piece = complex(baseline_projected[local["target_active_position"]])
            candidate_piece = complex(new_active[local["target_active_position"]])
            baseline_terms.append(baseline_piece)
            candidate_terms.append(candidate_piece)
            base_g += baseline_piece
            candidate_g += candidate_piece
            action_sources.append(action_ref)
        if not extension and base_g != source["baseline_g_by_column"][column]:
            raise ValueError(
                f"V14 column {column} array-derived production-order g differs from the frozen V11 baseline"
            )
        column_summaries.append({
            "column": column,
            "state": state,
            "state_pair": "j0_j3_shared_b_i" if extension else "single_saved_v11_state",
            "selected_original_row": int(source.get("target_original_row", TASK41_P0_V11_METADATA_ORIGINAL_ROW)),
            "selected_active_row": int(source.get("target_active_row", TASK41_P0_V11_METADATA_ACTIVE_ROW)),
            "incident_cell_order": list(cell_order),
            "base_b_t": [float(source["b_t_by_column"][column].real), float(source["b_t_by_column"][column].imag)],
            "base_b_t_source": source["b_t_ref_by_column"][column],
            "b_alpha_row_used_once": [float(source["b_alpha_by_column"][column].real), float(source["b_alpha_by_column"][column].imag)],
            "b_alpha_sources": source["b_alpha_refs_by_column"][column],
            "y_cell_s_action_sources": action_sources,
            "saved_y": [float(y.real), float(y.imag)],
            "baseline_g_replayed_cell_order": [float(base_g.real), float(base_g.imag)],
            "candidate_g_actual_returned_correction_cell_order": [float(candidate_g.real), float(candidate_g.imag)],
            "baseline_d": [float((y - base_g).real), float((y - base_g).imag)],
            "candidate_d": [float((y - candidate_g).real), float((y - candidate_g).imag)],
            "baseline_cell_terms": [[float(v.real), float(v.imag)] for v in baseline_terms],
            "candidate_cell_terms": [[float(v.real), float(v.imag)] for v in candidate_terms],
        })
    elapsed = float(time.perf_counter() - core_started)
    if getrs_total > 12:
        raise RuntimeError("V14 bounded saved candidate exceeded its twelve-GETRS gate")
    report = {
        "schema": V14_CANDIDATE_REPORT_SCHEMA,
        "status": "CANDIDATE_PRODUCED_PENDING_INDEPENDENT_CHECK",
        "classification": "SAVED_SAME_LU_RHS_CANDIDATE_NOT_YET_QUALIFIED",
        "official_result": False,
        "scientific_qualified": False,
        "consumer_contract_path": str(source["consumer_contract_path"]),
        "consumer_contract_sha256": source["consumer_contract_sha256"],
        "consumer_window_sha256": source["consumer_window_sha256"],
        "producer_report_path": str(source["producer_report_path"]),
        "producer_report_sha256": source["producer_report_sha256"],
        "star_producer_report_path": source.get("star_producer_report_path"),
        "star_producer_report_sha256": source.get("star_producer_report_sha256"),
        "accepted_checker_path": str(source["accepted_checker_path"]),
        "accepted_checker_sha256": source["accepted_checker_sha256"],
        "accepted_receipt_path": str(source["accepted_receipt_path"]),
        "accepted_receipt_sha256": source["accepted_receipt_sha256"],
        "donor_summary_path": str(source["donor_summary_path"]),
        "donor_summary_sha256": source["donor_summary_sha256"],
        "donor_contract_sha256": source["donor_contract_sha256"],
        "donor_manifest_sha256": source["donor_manifest_sha256"],
        "producer_window_sha256": V14_SOURCE_WINDOW_SHA256,
        "scope": {
            "stage": stage,
            "cells": list(cell_order),
            "columns": list(columns),
            "states": sorted({str(item["state"]) for item in state_rows}),
            "state_rows": [{"column": int(item["column"]), "state": str(item["state"])} for item in state_rows],
            "rhs_count": len(cell_order) * len(columns),
            "max_correction_steps": 2,
            "max_initial_screen_getrs_count": 12,
            "conditional_star_coverage_registered": stage == "initial_screen",
            "prior_stage_reused": source.get("prior_stage_reused"),
            "star_cell_identities": source.get("star_cell_identities"),
            "full_owner": False,
        },
        "getrs_count": getrs_total,
        "elapsed_seconds_includes_step_persistence": elapsed,
        "candidate_rhs": [
            {
                key: value for key, value in rhs_results[(cell, column)].items()
                if key != "baseline_projected_active"
            }
            for cell in cell_order for column in columns
        ],
        "production_order_rows": column_summaries,
        "new_evidence_bytes": evidence_budget[0],
        "raw_evidence_retained": True,
    }
    report_path = output / "task41_p0_v14_saved_rhs_candidate.json"
    report_sha = _atomic_json(report_path, report)
    return {"path": str(report_path), "sha256": report_sha, "payload": report}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--consumer-contract", required=True, type=Path)
    parser.add_argument("--consumer-contract-sha256", required=True)
    parser.add_argument("--producer-report", required=True, type=Path)
    parser.add_argument("--producer-report-sha256", required=True)
    parser.add_argument("--accepted-checker", required=True, type=Path)
    parser.add_argument("--accepted-checker-sha256", required=True)
    parser.add_argument("--accepted-receipt", required=True, type=Path)
    parser.add_argument("--accepted-receipt-sha256", required=True)
    parser.add_argument("--donor-summary", required=True, type=Path)
    parser.add_argument("--donor-summary-sha256", required=True)
    parser.add_argument("--donor-contract", required=True, type=Path)
    parser.add_argument("--donor-contract-sha256", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--loader-only", action="store_true")
    parser.add_argument("--v14-saved-star-extension", action="store_true")
    parser.add_argument("--v8-star-report", type=Path)
    parser.add_argument("--v8-star-report-sha256")
    parser.add_argument("--prior-candidate-report", type=Path)
    parser.add_argument("--prior-candidate-report-sha256")
    parser.add_argument("--prior-checker", type=Path)
    parser.add_argument("--prior-checker-sha256")
    parser.add_argument("--prior-decimal-report", type=Path)
    parser.add_argument("--prior-decimal-report-sha256")
    parser.add_argument("--prior-service-receipt", type=Path)
    parser.add_argument("--prior-service-receipt-sha256")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    source = load_v14_saved_candidate_inputs(
        repo_root=args.repo_root,
        consumer_contract_path=args.consumer_contract,
        consumer_contract_sha256=args.consumer_contract_sha256,
        producer_report_path=args.producer_report,
        producer_report_sha256=args.producer_report_sha256,
        accepted_checker_path=args.accepted_checker,
        accepted_checker_sha256=args.accepted_checker_sha256,
        accepted_receipt_path=args.accepted_receipt,
        accepted_receipt_sha256=args.accepted_receipt_sha256,
        donor_summary_path=args.donor_summary,
        donor_summary_sha256=args.donor_summary_sha256,
        donor_contract_path=args.donor_contract,
        donor_contract_sha256=args.donor_contract_sha256,
    )
    extension_values = (
        args.v8_star_report, args.v8_star_report_sha256,
        args.prior_candidate_report, args.prior_candidate_report_sha256,
        args.prior_checker, args.prior_checker_sha256,
        args.prior_decimal_report, args.prior_decimal_report_sha256,
        args.prior_service_receipt, args.prior_service_receipt_sha256,
    )
    if args.v14_saved_star_extension:
        if any(value is None for value in extension_values):
            raise ValueError("V14 star extension requires every V8/prior-stage path and SHA binding")
        from src.runners.task41_p0_v14_candidate_io import load_v14_saved_star_extension_inputs
        source = load_v14_saved_star_extension_inputs(
            source=source,
            v8_star_report_path=args.v8_star_report,
            v8_star_report_sha256=args.v8_star_report_sha256,
            prior_candidate_report_path=args.prior_candidate_report,
            prior_candidate_report_sha256=args.prior_candidate_report_sha256,
            prior_checker_path=args.prior_checker,
            prior_checker_sha256=args.prior_checker_sha256,
            prior_decimal_report_path=args.prior_decimal_report,
            prior_decimal_report_sha256=args.prior_decimal_report_sha256,
            prior_service_receipt_path=args.prior_service_receipt,
            prior_service_receipt_sha256=args.prior_service_receipt_sha256,
        )
    elif any(value is not None for value in extension_values):
        raise ValueError("V14 star extension evidence requires its explicit mode flag")
    if args.loader_only:
        print(json.dumps({
            "status": "LOADER_ONLY_VALIDATED",
            "stage": source.get("stage", "initial_screen"),
            "cell_order": list(source.get("cell_order", V14_CELLS)),
            "columns": list(source.get("columns", V14_COLUMNS)),
            "state_rows": source.get("state_rows"),
            "prior_stage_reused": source.get("prior_stage_reused"),
            "star_cell_identities": source.get("star_cell_identities"),
            "getrs_invoked": 0,
        }, sort_keys=True))
        return 0
    result = run_v14_saved_candidate(source=source, output_dir=args.output_dir)
    print(json.dumps({key: value for key, value in result.items() if key != "payload"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
