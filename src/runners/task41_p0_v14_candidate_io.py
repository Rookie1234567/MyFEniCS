"""Narrow V14 reader for the accepted V11 two-cell saved producer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from scipy.sparse import csr_matrix

from src.runners.task41_p0_contract import (
    TASK41_B0_V14_SAVED_RHS_CANDIDATE_SCOPE,
    TASK41_P0_CONTRACT_SCHEMA,
    TASK41_MODEL_ID,
    require_task41_p0_contract,
    load_task41_p0_fixed_window,
    sha256_file,
)
from src.runners.task41_p0_v4_volume_only_audit import (
    TASK41_P0_V11_METADATA_ACTIVE_ROW,
    TASK41_P0_V11_METADATA_ORIGINAL_ROW,
    TASK41_P0_V11_SELECTED_CELLS,
)
from src.solvers.task41_v4_volume_only_audit import (
    TASK41_V4_DONOR_MANIFEST_SHA256,
    TASK41_V4_FULL_STORAGE_ROWS,
)

V14_SOURCE_WINDOW_SHA256 = "4fc153c4e0526a21eb01aa3d6e5c774af7c74a849a3461b676e7ffdf214debc6"
V14_V11_REPORT_SHA256 = "2463e322ea72160bfcca7f3345d149ab20e5b017982f1f9ed55010df0afa9876"
V14_ACCEPTED_CHECKER_SHA256 = "cdbd2a0a8d6ae62b61ad1a45b8bd4f62dae4c69ebb1f0f7923205ac85e4c3739"
V14_ACCEPTED_RECEIPT_SHA256 = "0b28a0f2b57aa17d515627097978a5470c7787ca9c61b15c07a0d25b14ae217f"
V14_DONOR_CONTRACT_SHA256 = "9e312f86cdd6b15fff9015faf4fb7dce19043fa3798a3f35cf2e57f79149713c"
V14_DONOR_MANIFEST_SHA256 = TASK41_V4_DONOR_MANIFEST_SHA256
V14_CANDIDATE_REPORT_SCHEMA = "task41.p0.v14.saved_same_lu_rhs_candidate.v1"
V14_CANDIDATE_CHECK_SCHEMA = "task41.p0.v14.saved_same_lu_rhs_candidate_independent_check.v1"
V14_CELLS = tuple(int(value) for value in TASK41_P0_V11_SELECTED_CELLS)
V14_COLUMNS = (0, 1)


def _results_root(repo_root: Path) -> Path:
    return (repo_root / "results" / TASK41_MODEL_ID).resolve(strict=True)


def _checked_path(path: str | Path, *, root: Path, label: str, must_exist: bool = True) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=must_exist)
    if not resolved.is_relative_to(root):
        raise ValueError(f"V14 {label} escaped the Task41 results root")
    return resolved


def _read_json(path: Path, *, expected_sha256: str | None, max_bytes: int, label: str) -> dict[str, Any]:
    if path.stat().st_size > max_bytes:
        raise ValueError(f"V14 {label} exceeds its bounded JSON size")
    digest = sha256_file(path)
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError(f"V14 {label} hash differs")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"V14 {label} must be a JSON object")
    return value


def load_hash_bound_npy(
    ref: Any, *, root: Path, label: str, required_dtype: str | None = None
) -> np.ndarray:
    if not isinstance(ref, Mapping):
        raise ValueError(f"V14 {label} array reference is malformed")
    raw_path = Path(str(ref.get("path", "")))
    path = (raw_path if raw_path.is_absolute() else root / raw_path).resolve(strict=True)
    digest = ref.get("sha256")
    if (
        not path.is_relative_to(root.resolve(strict=True))
        or not isinstance(digest, str)
        or path.stat().st_size != ref.get("bytes")
        or sha256_file(path) != digest
    ):
        raise ValueError(f"V14 {label} saved array path/size/hash differs")
    value = np.load(path, mmap_mode="r", allow_pickle=False)
    if list(value.shape) != ref.get("shape") or str(value.dtype) != ref.get("dtype"):
        raise ValueError(f"V14 {label} saved array shape/dtype differs")
    if required_dtype is not None and str(value.dtype) != required_dtype:
        raise ValueError(f"V14 {label} saved array has the wrong dtype")
    if value.dtype.hasobject:
        raise ValueError(f"V14 {label} object arrays are forbidden")
    return value


def _complex_pair(value: Any, label: str) -> complex:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or any(isinstance(part, bool) or not isinstance(part, (int, float)) for part in value)
    ):
        raise ValueError(f"V14 {label} is not a serialized complex pair")
    result = complex(float(value[0]), float(value[1]))
    if not np.isfinite(result.real) or not np.isfinite(result.imag):
        raise ValueError(f"V14 {label} is non-finite")
    return result


def load_v14_saved_candidate_inputs(
    *,
    repo_root: str | Path,
    consumer_contract_path: str | Path,
    consumer_contract_sha256: str,
    producer_report_path: str | Path,
    producer_report_sha256: str,
    accepted_checker_path: str | Path,
    accepted_checker_sha256: str,
    accepted_receipt_path: str | Path,
    accepted_receipt_sha256: str,
    donor_summary_path: str | Path,
    donor_summary_sha256: str,
    donor_contract_path: str | Path,
    donor_contract_sha256: str,
    check_current_source: bool = True,
    require_clean_source: bool = True,
) -> dict[str, Any]:
    """Load only the four accepted V11 cell RHSs and their original K/J/LU."""
    root = Path(repo_root).resolve(strict=True)
    results_root = _results_root(root)
    consumer_path = Path(consumer_contract_path).resolve(strict=True)
    consumer, consumer_digest = require_task41_p0_contract(
        consumer_path,
        expected_sha256=consumer_contract_sha256,
        current_root=root,
        check_current_source=check_current_source,
        require_clean_source=require_clean_source,
        case_id="B0",
    )
    if consumer.get("execution_scope") != TASK41_B0_V14_SAVED_RHS_CANDIDATE_SCOPE:
        raise ValueError("V14 consumer contract does not bind the bounded same-LU candidate scope")
    window = load_task41_p0_fixed_window(consumer, current_root=root, require_current_boot=False)
    if window.sha256 == V14_SOURCE_WINDOW_SHA256:
        raise ValueError("V14 consumer window must be distinct from the expired V11 producer window")

    report_path = _checked_path(producer_report_path, root=results_root, label="V11 producer report")
    checker_path = _checked_path(accepted_checker_path, root=results_root, label="accepted checker")
    receipt_path = _checked_path(accepted_receipt_path, root=results_root, label="accepted service receipt")
    summary_path = _checked_path(donor_summary_path, root=results_root, label="donor summary")
    if report_path.name != "task41_p0_v11_selected_trace_candidate_replay.json":
        raise ValueError("V14 producer report name differs from the accepted V11 replay")
    if producer_report_sha256 != V14_V11_REPORT_SHA256:
        raise ValueError("V14 V11 producer report hash is not the frozen V12 producer")
    if accepted_checker_sha256 != V14_ACCEPTED_CHECKER_SHA256:
        raise ValueError("V14 accepted V11 checker hash differs from the frozen producer chain")
    if accepted_receipt_sha256 != V14_ACCEPTED_RECEIPT_SHA256:
        raise ValueError("V14 accepted service receipt hash differs from the frozen producer chain")
    if donor_contract_sha256 != V14_DONOR_CONTRACT_SHA256:
        raise ValueError("V14 donor contract hash differs from the frozen V11 source")
    report = _read_json(
        report_path, expected_sha256=producer_report_sha256, max_bytes=64 * 1024**2,
        label="V11 producer report",
    )
    checker = _read_json(
        checker_path, expected_sha256=accepted_checker_sha256, max_bytes=16 * 1024**2,
        label="accepted V11 checker",
    )
    receipt = _read_json(
        receipt_path, expected_sha256=accepted_receipt_sha256, max_bytes=16 * 1024**2,
        label="accepted V11 service receipt",
    )
    if (
        report.get("schema") != "task41.p0.v11.selected_trace_star_candidate_replay_receipt.v1"
        or report.get("status") != "COMPLETED_LOCAL_CANDIDATE_REPLAY"
        or report.get("consumer_window_sha256") != V14_SOURCE_WINDOW_SHA256
        or report.get("donor_contract_sha256") != V14_DONOR_CONTRACT_SHA256
        or report.get("donor_manifest_sha256") != V14_DONOR_MANIFEST_SHA256
        or checker.get("schema") != "task41.p0.v11.selected_trace_star_saved_array_independent_check.v1"
        or checker.get("classification") != "INDEPENDENT_SAVED_ARRAY_CHECK_COMPLETED"
        or checker.get("check_completed") is not True
        or checker.get("candidate_passed") is not None
        or checker.get("scientific_qualified") is not False
        or checker.get("official_result") is not False
        or checker.get("candidate_report_sha256") != producer_report_sha256
        or receipt.get("candidate_report_sha256") != producer_report_sha256
    ):
        raise ValueError("V14 V11 producer/checker identities or negative science classification differ")
    checker_binding = receipt.get("candidate_replay_saved_array_checker")
    if (
        not isinstance(checker_binding, Mapping)
        or checker_binding.get("status") != "COMPLETED_READ_ONLY"
        or checker_binding.get("result_path") != str(checker_path)
        or checker_binding.get("result_sha256") != accepted_checker_sha256
    ):
        raise ValueError("V14 V11 accepted service receipt does not bind the explicit checker path/hash")

    donor_contract_path = Path(donor_contract_path).resolve(strict=True)
    donor_contract, donor_contract_digest = require_task41_p0_contract(
        donor_contract_path,
        expected_sha256=donor_contract_sha256,
        current_root=root,
        check_current_source=False,
        require_clean_source=False,
        case_id="B0",
    )
    _ = donor_contract
    if sha256_file(summary_path) != donor_summary_sha256:
        raise ValueError("V14 donor summary hash differs")
    summary = _read_json(
        summary_path, expected_sha256=donor_summary_sha256, max_bytes=16 * 1024**2,
        label="donor summary",
    )
    recovery = summary.get("b0_recovery_evidence")
    manifest_ref = recovery.get("manifest") if isinstance(recovery, Mapping) else None
    if not isinstance(manifest_ref, Mapping) or manifest_ref.get("sha256") != V14_DONOR_MANIFEST_SHA256:
        raise ValueError("V14 donor summary does not bind the frozen V4 recovery manifest")
    raw_manifest = Path(str(manifest_ref.get("path", "")))
    manifest_path = (raw_manifest if raw_manifest.is_absolute() else summary_path.parent / raw_manifest).resolve(strict=True)
    if (
        not manifest_path.is_relative_to(summary_path.parent.resolve(strict=True))
        or manifest_path.stat().st_size != manifest_ref.get("bytes")
        or sha256_file(manifest_path) != V14_DONOR_MANIFEST_SHA256
    ):
        raise ValueError("V14 donor manifest path/size/hash differs")
    manifest = _read_json(
        manifest_path, expected_sha256=V14_DONOR_MANIFEST_SHA256,
        max_bytes=16 * 1024**2, label="donor manifest",
    )
    columns_manifest = manifest.get("columns")
    if manifest.get("full_storage_rows") != TASK41_V4_FULL_STORAGE_ROWS or not isinstance(columns_manifest, list) or len(columns_manifest) != 2:
        raise ValueError("V14 donor manifest layout differs")

    replay = report.get("v11_selected_trace_candidate_replay")
    metadata_path = _checked_path(
        str(replay.get("metadata_report_path", "")) if isinstance(replay, Mapping) else "",
        root=results_root, label="V11 metadata report",
    )
    metadata_sha = replay.get("metadata_report_sha256") if isinstance(replay, Mapping) else None
    metadata_report = _read_json(
        metadata_path, expected_sha256=metadata_sha, max_bytes=64 * 1024**2,
        label="V11 metadata report",
    )
    metadata = metadata_report.get("selected_trace_star_metadata_only")
    metadata_cells = metadata.get("selected_cells") if isinstance(metadata, Mapping) else None
    report_cells = replay.get("cells") if isinstance(replay, Mapping) else None
    report_columns = replay.get("columns") if isinstance(replay, Mapping) else None
    if (
        replay.get("schema") != "task41.p0.v11.selected_trace_star_candidate_replay.v1"
        or replay.get("status") != "COMPLETED_LOCAL_CANDIDATE_REPLAY"
        or replay.get("scientific_qualified") is not False
        or replay.get("incident_cell_order") != list(V14_CELLS)
        or not isinstance(metadata_cells, list)
        or [item.get("cell_index") for item in metadata_cells] != list(V14_CELLS)
        or not isinstance(report_cells, list)
        or [item.get("cell_index") for item in report_cells] != list(V14_CELLS)
        or not isinstance(report_columns, list)
        or len(report_columns) != 2
    ):
        raise ValueError("V14 accepted V11 cell/column scope differs")

    b_t_by_column: dict[int, complex] = {}
    b_t_ref_by_column: dict[int, Any] = {}
    b_alpha_by_column: dict[int, complex] = {}
    b_alpha_refs_by_column: dict[int, dict[str, Any]] = {}
    for column_index, column in enumerate(columns_manifest):
        artifacts = column.get("artifacts") if isinstance(column, Mapping) else None
        if not isinstance(artifacts, Mapping):
            raise ValueError(f"V14 donor column {column_index} artifacts are malformed")
        donor_root = summary_path.parent.resolve(strict=True)
        native = load_hash_bound_npy(
            artifacts.get("native_rhs"), root=donor_root,
            label=f"donor column {column_index}/native_rhs", required_dtype="complex128",
        )
        beta_rows = load_hash_bound_npy(
            artifacts.get("b_alpha_rows"), root=donor_root,
            label=f"donor column {column_index}/b_alpha_rows", required_dtype="int64",
        )
        beta_values = load_hash_bound_npy(
            artifacts.get("b_alpha_values"), root=donor_root,
            label=f"donor column {column_index}/b_alpha_values", required_dtype="complex128",
        )
        if (
            native.shape != (TASK41_V4_FULL_STORAGE_ROWS,)
            or beta_rows.ndim != 1 or beta_values.shape != beta_rows.shape
            or (beta_rows.size and (np.any(beta_rows < 0) or np.any(beta_rows >= native.size)))
            or not np.isfinite(beta_values).all()
        ):
            raise ValueError(f"V14 donor column {column_index} RHS/B-alpha layout differs")
        selected_beta = beta_values[beta_rows == TASK41_P0_V11_METADATA_ORIGINAL_ROW]
        if selected_beta.size > 1:
            raise ValueError(f"V14 donor column {column_index} has duplicate selected B-alpha rows")
        b_t_by_column[column_index] = complex(native[TASK41_P0_V11_METADATA_ORIGINAL_ROW])
        b_t_ref_by_column[column_index] = artifacts.get("native_rhs")
        beta = complex(selected_beta[0]) if selected_beta.size else 0.0 + 0.0j
        b_alpha_by_column[column_index] = beta
        b_alpha_refs_by_column[column_index] = {
            "rows": artifacts.get("b_alpha_rows"),
            "values": artifacts.get("b_alpha_values"),
        }
        reported_beta = _complex_pair(
            report_columns[column_index].get("B_alpha_selected_original_row_applied_once"),
            f"column{column_index}/reported_B_alpha_crosscheck",
        )
        if reported_beta != beta:
            raise ValueError(f"V14 column {column_index} B-alpha array does not exactly match its report cross-check")

    candidate_by_cell: dict[int, dict[str, Any]] = {}
    metadata_by_cell = {int(item["cell_index"]): item for item in metadata_cells}
    report_by_cell = {int(item["cell_index"]): item for item in report_cells}
    for cell in V14_CELLS:
        meta = metadata_by_cell[cell]
        record = report_by_cell[cell]
        refs = record.get("candidate_artifacts")
        arrays = meta.get("arrays")
        if not isinstance(refs, Mapping) or not isinstance(arrays, Mapping):
            raise ValueError(f"V14 cell {cell} source references are malformed")
        interior = np.asarray(load_hash_bound_npy(arrays.get("interior_positions"), root=metadata_path.parent.resolve(strict=True), label=f"cell{cell}/interior_positions"), dtype=np.int64)
        trace = np.asarray(load_hash_bound_npy(arrays.get("trace_positions"), root=metadata_path.parent.resolve(strict=True), label=f"cell{cell}/trace_positions"), dtype=np.int64)
        active_ids = np.asarray(load_hash_bound_npy(arrays.get("active_ids"), root=metadata_path.parent.resolve(strict=True), label=f"cell{cell}/active_ids"), dtype=np.int64)
        expansion_data = np.asarray(load_hash_bound_npy(arrays.get("trace_expansion_data"), root=metadata_path.parent.resolve(strict=True), label=f"cell{cell}/trace_expansion_data"), dtype=np.complex128)
        expansion_indices = np.asarray(load_hash_bound_npy(arrays.get("trace_expansion_indices"), root=metadata_path.parent.resolve(strict=True), label=f"cell{cell}/trace_expansion_indices"), dtype=np.int32)
        expansion_indptr = np.asarray(load_hash_bound_npy(arrays.get("trace_expansion_indptr"), root=metadata_path.parent.resolve(strict=True), label=f"cell{cell}/trace_expansion_indptr"), dtype=np.int32)
        if (
            interior.ndim != 1 or trace.ndim != 1 or active_ids.ndim != 1
            or np.intersect1d(interior, trace).size
            or not np.array_equal(np.sort(np.r_[interior, trace]), np.arange(interior.size + trace.size))
            or not np.array_equal(np.sort(active_ids), active_ids)
            or not np.isfinite(expansion_data).all()
        ):
            raise ValueError(f"V14 cell {cell} trace/interior maps are invalid")
        expansion = csr_matrix(
            (expansion_data, expansion_indices, expansion_indptr),
            shape=(trace.size, active_ids.size),
        )
        if not expansion.has_canonical_format:
            raise ValueError(f"V14 cell {cell} trace expansion is not canonical")
        target = np.flatnonzero(active_ids == TASK41_P0_V11_METADATA_ACTIVE_ROW)
        if target.size != 1:
            raise ValueError(f"V14 cell {cell} target active row is not unique")
        tensor = load_hash_bound_npy(refs.get("oriented_tensor"), root=report_path.parent.resolve(strict=True), label=f"cell{cell}/oriented_tensor", required_dtype="complex128")
        lu = load_hash_bound_npy(refs.get("interior_lu"), root=report_path.parent.resolve(strict=True), label=f"cell{cell}/interior_lu", required_dtype="complex128")
        pivots = load_hash_bound_npy(refs.get("interior_lu_pivots"), root=report_path.parent.resolve(strict=True), label=f"cell{cell}/interior_lu_pivots", required_dtype="int32")
        dim = interior.size + trace.size
        if tensor.shape != (dim, dim) or lu.shape != (interior.size, interior.size) or pivots.shape != (interior.size,):
            raise ValueError(f"V14 cell {cell} matrix/LU/pivot dimensions differ")
        if record.get("actual_coordinate_sha256") != meta.get("actual_coordinate_sha256"):
            raise ValueError(f"V14 cell {cell} coordinate identity differs")
        candidate_by_cell[cell] = {
            "cell_index": cell,
            "cell_tag": record.get("cell_tag"),
            "actual_coordinate_sha256": record.get("actual_coordinate_sha256"),
            "interior_positions": interior,
            "trace_positions": trace,
            "active_ids": active_ids,
            "trace_expansion": expansion,
            "target_active_position": int(target[0]),
            "K": np.asarray(tensor[np.ix_(interior, interior)], dtype=np.complex128),
            "J": np.asarray(tensor[np.ix_(trace, interior)], dtype=np.complex128),
            "LU": lu,
            "pivots": pivots,
            "tensor_ref": refs.get("oriented_tensor"),
            "lu_ref": refs.get("interior_lu"),
            "column_terms": {},
        }
    for column_index, report_column in enumerate(report_columns):
        incident = report_column.get("incident_cell_terms")
        if not isinstance(incident, list) or [item.get("cell_index") for item in incident] != list(V14_CELLS):
            raise ValueError(f"V14 column {column_index} incident cell order differs")
        y = _complex_pair(report_column.get("replayed_y9"), f"column{column_index}/replayed_y9")
        baseline_g = _complex_pair(report_column.get("replayed_g9_same_lu"), f"column{column_index}/replayed_g9_same_lu")
        for item in incident:
            cell = int(item["cell_index"])
            artifacts = item.get("artifacts")
            if not isinstance(artifacts, Mapping):
                raise ValueError(f"V14 cell{cell}/column{column_index} input artifacts are missing")
            artifact_root = report_path.parent.resolve(strict=True)
            b_i = load_hash_bound_npy(artifacts.get("native_rhs_interior"), root=artifact_root, label=f"cell{cell}/column{column_index}/native_rhs_interior", required_dtype="complex128")
            old_z_b = load_hash_bound_npy(artifacts.get("same_lu_z_b"), root=artifact_root, label=f"cell{cell}/column{column_index}/same_lu_z_b", required_dtype="complex128")
            old_correction = load_hash_bound_npy(artifacts.get("same_lu_minus_Jz_b"), root=artifact_root, label=f"cell{cell}/column{column_index}/same_lu_minus_Jz_b", required_dtype="complex128")
            old_projected = load_hash_bound_npy(artifacts.get("same_lu_projected_active"), root=artifact_root, label=f"cell{cell}/column{column_index}/same_lu_projected_active", required_dtype="complex128")
            s_action = load_hash_bound_npy(artifacts.get("S_action"), root=artifact_root, label=f"cell{cell}/column{column_index}/S_action", required_dtype="complex128")
            s_projected = load_hash_bound_npy(artifacts.get("S_projected_active"), root=artifact_root, label=f"cell{cell}/column{column_index}/S_projected_active", required_dtype="complex128")
            local = candidate_by_cell[cell]
            if (
                b_i.shape != (local["K"].shape[0],)
                or old_z_b.shape != b_i.shape
                or old_correction.shape != (local["J"].shape[0],)
                or s_action.shape != (local["J"].shape[0],)
                or old_projected.shape != (local["active_ids"].size,)
                or s_projected.shape != old_projected.shape
                or not np.array_equal(old_correction, -(local["J"] @ old_z_b))
                or not np.array_equal(old_projected, np.asarray(local["trace_expansion"].conj().T @ old_correction, dtype=np.complex128).reshape(-1))
                or not np.array_equal(s_projected, np.asarray(local["trace_expansion"].conj().T @ s_action, dtype=np.complex128).reshape(-1))
            ):
                raise ValueError(f"V14 cell{cell}/column{column_index} saved z_b/correction/S projection differs")
            local["column_terms"][column_index] = {
                "b_i": b_i,
                "b_i_ref": artifacts.get("native_rhs_interior"),
                "old_z_b": old_z_b,
                "old_z_b_ref": artifacts.get("same_lu_z_b"),
                "old_correction": old_correction,
                "old_correction_ref": artifacts.get("same_lu_minus_Jz_b"),
                "old_projected_active": old_projected,
                "old_projected_active_ref": artifacts.get("same_lu_projected_active"),
                "s_action": s_action,
                "s_action_ref": artifacts.get("S_action"),
                "s_projected_active": s_projected,
                "s_projected_active_ref": artifacts.get("S_projected_active"),
            }
    y_by_column: dict[int, complex] = {}
    baseline_g_by_column: dict[int, complex] = {}
    for column_index, report_column in enumerate(report_columns):
        y = 0.0 + 0.0j
        g = b_t_by_column[column_index]
        for cell in V14_CELLS:
            local = candidate_by_cell[cell]
            term = local["column_terms"][column_index]
            y += complex(term["s_projected_active"][local["target_active_position"]])
            g += complex(term["old_projected_active"][local["target_active_position"]])
        y += b_alpha_by_column[column_index]
        if (
            y != _complex_pair(report_column.get("replayed_y9"), f"column{column_index}/replayed_y9")
            or g != _complex_pair(report_column.get("replayed_g9_same_lu"), f"column{column_index}/replayed_g9_same_lu")
        ):
            raise ValueError(f"V14 column {column_index} array-derived y/g differs exactly from the V11 report")
        y_by_column[column_index] = y
        baseline_g_by_column[column_index] = g
    return {
        "repo_root": root,
        "results_root": results_root,
        "consumer_contract": consumer,
        "consumer_contract_path": consumer_path,
        "consumer_contract_sha256": consumer_digest,
        "consumer_window_sha256": window.sha256,
        "producer_report_path": report_path,
        "producer_report_sha256": producer_report_sha256,
        "accepted_checker_path": checker_path,
        "accepted_checker_sha256": accepted_checker_sha256,
        "accepted_receipt_path": receipt_path,
        "accepted_receipt_sha256": accepted_receipt_sha256,
        "donor_summary_path": summary_path,
        "donor_summary_sha256": donor_summary_sha256,
        "donor_contract_path": donor_contract_path,
        "donor_contract_sha256": donor_contract_digest,
        "donor_manifest_sha256": V14_DONOR_MANIFEST_SHA256,
        "metadata_report_path": metadata_path,
        "metadata_report_sha256": str(metadata_sha),
        "b_t_by_column": b_t_by_column,
        "b_t_ref_by_column": b_t_ref_by_column,
        "b_alpha_by_column": b_alpha_by_column,
        "b_alpha_refs_by_column": b_alpha_refs_by_column,
        "y_by_column": y_by_column,
        "baseline_g_by_column": baseline_g_by_column,
        "report_columns": report_columns,
        "cells": candidate_by_cell,
    }
