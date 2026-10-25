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
    TASK41_B0_V14_RHS_REFINEMENT_STRATEGY,
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
V14_V8_STAR_REPORT_SHA256 = "1bdd07ac38bce95d58a153bacdca0de6cf5941d08d2706dc127e8b00d8e2764f"
V14_V8_STAR_CELLS = (23352, 23493)
V14_V8_STAR_ACTIVE_ROW = 4_766_937
V14_V8_STAR_ORIGINAL_ROW = 15_440_235
V14_V8_STAR_IDENTITIES = {
    23352: {
        "cell_tag": 2,
        "permutation": 4680,
        "coordinate_sha256": "00be22d015fe207dd28a8c246380144e51b8ba2d7a3ff63562dfca38b65024e6",
        "selected_local_trace_row": 375,
    },
    23493: {
        "cell_tag": 1,
        "permutation": 0,
        "coordinate_sha256": "0fbdca58aeb8061e226f1c298a610bbd63f2f43fa15a6830afd3fa435a667ca6",
        "selected_local_trace_row": 75,
    },
}


def v14_matrix_identity_token(source: Mapping[str, Any], cell: int) -> str:
    local = source["cells"][cell]
    if "matrix_identity" in local:
        return str(local["matrix_identity"])
    identity = {
        "producer_report_sha256": source.get(
            "star_producer_report_sha256", source["producer_report_sha256"]
        ),
        "cell_index": int(cell),
        "actual_coordinate_sha256": local["actual_coordinate_sha256"],
        "oriented_tensor_sha256": local["tensor_ref"]["sha256"],
        "interior_lu_sha256": local["lu_ref"]["sha256"],
    }
    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()


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


def _v14_refinement_binding(consumer: Mapping[str, Any]) -> tuple[str, int]:
    """Resolve the immutable V14 v1 or explicit v2 RHS refinement binding."""

    if consumer.get("execution_scope") != TASK41_B0_V14_SAVED_RHS_CANDIDATE_SCOPE:
        raise ValueError(
            "V14 consumer contract does not bind the bounded same-LU candidate scope"
        )
    numerical_strategy = consumer.get("numerical_strategy", {})
    historical_v1_strategy = {
        "schema": "task41.p0.b0.internal_rhs_strategy.v1",
        "internal_rhs_strategy": "same_lu_rhs_solve",
    }
    refined_v2_strategy = {
        "schema": "task41.p0.b0.internal_rhs_strategy.v2",
        "internal_rhs_strategy": "same_lu_rhs_solve",
        "refinement_strategy": TASK41_B0_V14_RHS_REFINEMENT_STRATEGY,
        "refinement_max_steps": 2,
    }
    if not isinstance(numerical_strategy, Mapping):
        raise ValueError("V14 consumer contract has no numerical strategy binding")
    if dict(numerical_strategy) == historical_v1_strategy:
        # Existing V14 v1 contracts are immutable evidence. The exact scope
        # already bound the fixed algorithm before the v2 field was added.
        return (
            TASK41_B0_V14_SAVED_RHS_CANDIDATE_SCOPE["initial_screen"]["refinement"],
            TASK41_B0_V14_SAVED_RHS_CANDIDATE_SCOPE["initial_screen"][
                "refinement_max_steps"
            ],
        )
    if dict(numerical_strategy) == refined_v2_strategy:
        return (
            str(numerical_strategy["refinement_strategy"]),
            int(numerical_strategy["refinement_max_steps"]),
        )
    raise ValueError(
        "V14 consumer contract does not bind the fixed two-step production core"
    )


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
    refinement_strategy, refinement_max_steps = _v14_refinement_binding(consumer)
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
    native_rhs_arrays_by_column: dict[int, np.ndarray] = {}
    b_alpha_rows_by_column: dict[int, np.ndarray] = {}
    b_alpha_values_by_column: dict[int, np.ndarray] = {}
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
        native_rhs_arrays_by_column[column_index] = native
        b_alpha_rows_by_column[column_index] = beta_rows
        b_alpha_values_by_column[column_index] = beta_values
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
        "refinement_strategy": str(refinement_strategy),
        "refinement_max_steps": int(refinement_max_steps),
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
        "native_rhs_arrays_by_column": native_rhs_arrays_by_column,
        "b_alpha_rows_by_column": b_alpha_rows_by_column,
        "b_alpha_values_by_column": b_alpha_values_by_column,
        "b_alpha_by_column": b_alpha_by_column,
        "b_alpha_refs_by_column": b_alpha_refs_by_column,
        "y_by_column": y_by_column,
        "baseline_g_by_column": baseline_g_by_column,
        "report_columns": report_columns,
        "cells": candidate_by_cell,
    }

def _v14_required_report(path: str | Path, *, root: Path, expected_sha256: str, label: str) -> tuple[Path, dict[str, Any]]:
    resolved = _checked_path(path, root=root, label=label)
    report = _read_json(resolved, expected_sha256=expected_sha256, max_bytes=16 * 1024**2, label=label)
    return resolved, report


def _v14_star_prior_stage(
    *,
    source: Mapping[str, Any],
    candidate_report_path: str | Path,
    candidate_report_sha256: str,
    prior_checker_path: str | Path,
    prior_checker_sha256: str,
    prior_decimal_path: str | Path,
    prior_decimal_sha256: str,
    prior_receipt_path: str | Path,
    prior_receipt_sha256: str,
) -> dict[str, Any]:
    results_root = Path(source["results_root"]).resolve(strict=True)
    window_sha = str(source["consumer_window_sha256"])
    window_root = (
        results_root / "task41_p0_saved_diagnostics_6h" / window_sha
    ).resolve(strict=True)
    supplied = {
        "candidate": candidate_report_path,
        "checker": prior_checker_path,
        "decimal": prior_decimal_path,
        "receipt": prior_receipt_path,
    }
    digests = {
        "candidate": candidate_report_sha256,
        "checker": prior_checker_sha256,
        "decimal": prior_decimal_sha256,
        "receipt": prior_receipt_sha256,
    }
    labels = {
        "candidate": "prior V14 candidate",
        "checker": "prior V14 independent checker",
        "decimal": "prior V14 Decimal checker",
        "receipt": "prior V14 service receipt",
    }
    loaded: dict[str, tuple[Path, dict[str, Any]]] = {}
    for key, raw_path in supplied.items():
        path = _checked_path(raw_path, root=results_root, label=labels[key])
        if not path.is_relative_to(window_root):
            raise ValueError(f"V14 prior {key} is outside the authorized fixed window")
        digest = digests[key]
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"V14 prior {key} SHA-256 binding is malformed")
        loaded[key] = _v14_required_report(
            path, root=results_root, expected_sha256=digest, label=labels[key]
        )

    candidate_path, candidate = loaded["candidate"]
    checker_path, checker = loaded["checker"]
    decimal_path, decimal = loaded["decimal"]
    receipt_path, receipt = loaded["receipt"]
    candidate_scope = candidate.get("scope")
    if not isinstance(candidate_scope, Mapping):
        raise ValueError("V14 prior candidate scope is malformed")
    consumer_sha = candidate.get("consumer_contract_sha256")
    prior_consumer_path = Path(str(candidate.get("consumer_contract_path", ""))).resolve(strict=True)
    repo_root = Path(source["repo_root"]).resolve(strict=True)
    if not prior_consumer_path.is_relative_to(repo_root):
        raise ValueError("V14 prior consumer contract escaped the repository root")
    prior_consumer_contract, prior_consumer_digest = require_task41_p0_contract(
        prior_consumer_path,
        expected_sha256=consumer_sha,
        current_root=repo_root,
        check_current_source=False,
        require_clean_source=False,
        case_id="B0",
    )
    prior_consumer_window = load_task41_p0_fixed_window(
        prior_consumer_contract, current_root=repo_root, require_current_boot=False
    )
    review_contract_path = Path(str(decimal.get("review_contract_path", ""))).resolve(strict=True)
    review_contract_sha = decimal.get("review_contract_sha256")
    if not review_contract_path.is_relative_to(repo_root):
        raise ValueError("V14 prior Decimal review contract escaped the repository root")
    review_contract, review_digest = require_task41_p0_contract(
        review_contract_path,
        expected_sha256=review_contract_sha,
        current_root=repo_root,
        check_current_source=False,
        require_clean_source=False,
        case_id="B0",
    )
    review_window = load_task41_p0_fixed_window(
        review_contract, current_root=repo_root, require_current_boot=False
    )
    authorized_window_path = Path(
        str(source["consumer_contract"].get("window", {}).get("path", ""))
    ).resolve(strict=True)
    if (
        prior_consumer_contract.get("execution_scope") != TASK41_B0_V14_SAVED_RHS_CANDIDATE_SCOPE
        or prior_consumer_window.sha256 != window_sha
        or Path(prior_consumer_window.path).resolve() != authorized_window_path
        or review_contract.get("execution_scope") != TASK41_B0_V14_SAVED_RHS_CANDIDATE_SCOPE
        or review_digest != receipt.get("contract_sha256")
        or review_window.sha256 != window_sha
        or Path(review_window.path).resolve() != authorized_window_path
        or review_contract.get("source", {}).get("sha") == prior_consumer_contract.get("source", {}).get("sha")
    ):
        raise ValueError("V14 prior/review contracts are not distinct-source bindings to the authorized fixed window")
    if (
        candidate.get("schema") != V14_CANDIDATE_REPORT_SCHEMA
        or candidate.get("status") != "CANDIDATE_PRODUCED_PENDING_INDEPENDENT_CHECK"
        or candidate.get("consumer_window_sha256") != window_sha
        or candidate.get("producer_report_sha256") != source["producer_report_sha256"]
        or candidate_scope.get("stage") != "initial_screen"
        or candidate_scope.get("cells") != list(V14_CELLS)
        or candidate_scope.get("columns") != list(V14_COLUMNS)
        or candidate.get("getrs_count") != 12
        or checker.get("schema") != V14_CANDIDATE_CHECK_SCHEMA
        or checker.get("status") != "INCONCLUSIVE"
        or checker.get("check_completed") is not True
        or checker.get("candidate_passed") is not None
        or checker.get("candidate_report_path") != str(candidate_path)
        or checker.get("candidate_report_sha256") != candidate_report_sha256
        or checker.get("consumer_contract_sha256") != consumer_sha
        or checker.get("consumer_window_sha256") != window_sha
        or decimal.get("schema") != "task41.p0.v14.saved_rhs_decimal_residual_recheck.v1"
        or decimal.get("status") != "LOCAL_CANDIDATE_PASS"
        or decimal.get("candidate_passed") is not True
        or decimal.get("check_completed") is not True
        or decimal.get("official_result") is not False
        or decimal.get("scientific_qualified") is not False
        or decimal.get("conditional_star_coverage_unlocked") is not True
        or decimal.get("full_owner_unlocked") is not False
        or decimal.get("rhs_count") != 4
        or decimal.get("state_count") != 8
        or decimal.get("rows_per_state") != 450
        or decimal.get("candidate_report_path") != str(candidate_path)
        or decimal.get("candidate_report_sha256") != candidate_report_sha256
        or decimal.get("consumer_contract_path") != str(prior_consumer_path)
        or decimal.get("consumer_contract_sha256") != consumer_sha
        or decimal.get("prior_independent_check_path") != str(checker_path)
        or decimal.get("prior_independent_check_sha256") != prior_checker_sha256
        or decimal.get("review_contract_sha256") != review_digest
        or decimal.get("review_contract_path") != str(review_contract_path)
        or decimal.get("review_contract_path") != receipt.get("contract_path")
        or decimal.get("fixed_window_sha256") != window_sha
        or decimal.get("getrs_invoked") != 0
        or decimal.get("getrs_added") != 0
        or receipt.get("schema") != "task41.p0.saved_output_service_receipt.v1"
        or receipt.get("status") != "completed"
        or receipt.get("result_classification") != "V14_DECIMAL_SUPPLEMENTAL_PASS"
        or receipt.get("window_sha256") != window_sha
        or receipt.get("v14_candidate_passed") is not True
        or receipt.get("full_owner_unlocked") is not False
        or receipt.get("official_result") is not False
        or receipt.get("scientific_qualified") is not False
        or receipt.get("v14_saved_candidate_report_path") != str(candidate_path)
        or receipt.get("v14_saved_candidate_report_sha256") != candidate_report_sha256
        or receipt.get("v14_prior_independent_check_path") != str(checker_path)
        or receipt.get("v14_prior_independent_check_sha256") != prior_checker_sha256
        or receipt.get("v14_decimal_residual_check_path") != str(decimal_path)
        or receipt.get("v14_decimal_residual_check_sha256") != prior_decimal_sha256
    ):
        raise ValueError("V14 prior candidate/checker/receipt chain is not a completed same-window pass")
    return {
        "candidate_path": str(candidate_path),
        "candidate_sha256": candidate_report_sha256,
        "checker_path": str(checker_path),
        "checker_sha256": prior_checker_sha256,
        "decimal_path": str(decimal_path),
        "decimal_sha256": prior_decimal_sha256,
        "service_receipt_path": str(receipt_path),
        "service_receipt_sha256": prior_receipt_sha256,
        "candidate_status": candidate["status"],
        "independent_checker_status": checker["status"],
        "decimal_status": decimal["status"],
        "prior_consumer_contract_sha256": prior_consumer_digest,
        "decimal_review_contract_sha256": decimal["review_contract_sha256"],
        "candidate_passed_by_decimal": True,
        "getrs_reused": int(candidate["getrs_count"]),
        "new_getrs_for_reuse": 0,
        "cells_reused": list(V14_CELLS),
        "columns_reused": list(V14_COLUMNS),
    }


def load_v14_saved_star_extension_inputs(
    *,
    source: Mapping[str, Any],
    v8_star_report_path: str | Path,
    v8_star_report_sha256: str,
    prior_candidate_report_path: str | Path,
    prior_candidate_report_sha256: str,
    prior_checker_path: str | Path,
    prior_checker_sha256: str,
    prior_decimal_report_path: str | Path,
    prior_decimal_report_sha256: str,
    prior_service_receipt_path: str | Path,
    prior_service_receipt_sha256: str,
) -> dict[str, Any]:
    """Parameterize the V14 reader for the two V8 saved stars without inventing historical z0."""
    root = Path(source["results_root"]).resolve(strict=True)
    prior = _v14_star_prior_stage(
        source=source,
        candidate_report_path=prior_candidate_report_path,
        candidate_report_sha256=prior_candidate_report_sha256,
        prior_checker_path=prior_checker_path,
        prior_checker_sha256=prior_checker_sha256,
        prior_decimal_path=prior_decimal_report_path,
        prior_decimal_sha256=prior_decimal_report_sha256,
        prior_receipt_path=prior_service_receipt_path,
        prior_receipt_sha256=prior_service_receipt_sha256,
    )
    report_path, report = _v14_required_report(
        v8_star_report_path, root=root, expected_sha256=V14_V8_STAR_REPORT_SHA256,
        label="V8 selected-star producer report",
    )
    if (
        v8_star_report_sha256 != V14_V8_STAR_REPORT_SHA256
        or report.get("schema") != "task41.p0.v8.selected_trace_star_audit_receipt.v1"
        or report.get("status") != "COMPLETED_SELECTED_TRACE_STAR_AUDIT"
    ):
        raise ValueError("V14 V8 saved-star producer identity or status differs")
    metadata = report.get("selected_trace_star_metadata")
    audit = report.get("selected_trace_star_audit")
    replay = audit.get("p3_production_row_replay") if isinstance(audit, Mapping) else None
    selected_cells = metadata.get("selected_cells") if isinstance(metadata, Mapping) else None
    if (
        not isinstance(metadata, Mapping)
        or metadata.get("schema") != "task41.p0.v8.selected_trace_star_metadata.v1"
        or metadata.get("incident_cell_order") != list(V14_V8_STAR_CELLS)
        or metadata.get("selected_active_row") != V14_V8_STAR_ACTIVE_ROW
        or metadata.get("selected_original_row") != V14_V8_STAR_ORIGINAL_ROW
        or not isinstance(selected_cells, list)
        or [int(item.get("cell_index", -1)) for item in selected_cells] != list(V14_V8_STAR_CELLS)
        or not isinstance(audit, Mapping)
        or audit.get("status") != "COMPLETED_SELECTED_TRACE_STAR_AUDIT"
        or not isinstance(replay, Mapping)
        or replay.get("status") != "COMPLETED_LOCAL_ROW_REPLAY"
        or replay.get("selected_active_row") != V14_V8_STAR_ACTIVE_ROW
        or replay.get("selected_original_row") != V14_V8_STAR_ORIGINAL_ROW
        or replay.get("complete_incident_cell_coverage") is not True
    ):
        raise ValueError("V14 V8 saved-star row/cell identity differs")
    persisted = report.get("persisted_evidence_arrays")
    if not isinstance(persisted, list):
        raise ValueError("V14 V8 persisted array manifest is missing")
    arrays_by_name: dict[str, Mapping[str, Any]] = {}
    for ref in persisted:
        if not isinstance(ref, Mapping) or not isinstance(ref.get("name"), str) or ref["name"] in arrays_by_name:
            raise ValueError("V14 V8 persisted array manifest has malformed/duplicate names")
        arrays_by_name[str(ref["name"])] = ref

    def array(name: str, *, label: str, dtype: str | None = None) -> np.ndarray:
        ref = arrays_by_name.get(name)
        if not isinstance(ref, Mapping):
            raise ValueError(f"V14 V8 saved-star array is missing: {name}")
        return load_hash_bound_npy(ref, root=root, label=label, required_dtype=dtype)

    local_records = audit.get("local_numeric_cell_identity_and_artifacts")
    local_by_cell = {
        int(item.get("cell_index", -1)): item
        for item in local_records if isinstance(item, Mapping)
    } if isinstance(local_records, list) else {}
    cells: dict[int, dict[str, Any]] = {}
    state_names = ("j0", "j3")
    for item in selected_cells:
        cell = int(item["cell_index"])
        expected = V14_V8_STAR_IDENTITIES[cell]
        local_record = local_by_cell.get(cell)
        if (
            item.get("cell_tag") != expected["cell_tag"]
            or item.get("cell_permutation") != expected["permutation"]
            or item.get("actual_coordinate_sha256") != expected["coordinate_sha256"]
            or item.get("selected_local_trace_rows") != [expected["selected_local_trace_row"]]
            or not isinstance(local_record, Mapping)
            or local_record.get("tag") != expected["cell_tag"]
            or local_record.get("permutation_and_direction") != expected["permutation"]
            or local_record.get("actual_geometry_coordinates_sha256") != expected["coordinate_sha256"]
        ):
            raise ValueError(f"V14 V8 saved-star cell{cell} tag/direction/coordinate identity differs")
        map_refs = metadata["cell_artifacts"][str(cell)]["arrays"]
        map_arrays: dict[str, np.ndarray] = {}
        for name in (
            "interior_positions", "trace_positions", "trace_original_rows", "active_ids",
            "trace_expansion_data", "trace_expansion_indices", "trace_expansion_indptr",
            "selected_local_trace_rows", "selected_trace_coefficients",
        ):
            ref = map_refs.get(name)
            if not isinstance(ref, Mapping) or arrays_by_name.get(ref.get("name")) != ref:
                raise ValueError(f"V14 V8 cell{cell} {name} map is not bound by its producer manifest")
            map_arrays[name] = load_hash_bound_npy(
                ref, root=root, label=f"V8 cell{cell}/{name}",
                required_dtype="complex128" if name in {"trace_expansion_data", "selected_trace_coefficients"}
                else None,
            )
        interior = np.asarray(map_arrays["interior_positions"], dtype=np.int64)
        trace = np.asarray(map_arrays["trace_positions"], dtype=np.int64)
        active_ids = np.asarray(map_arrays["active_ids"], dtype=np.int64)
        local_rows = np.asarray(map_arrays["selected_local_trace_rows"], dtype=np.int64)
        selected_coefficients = np.asarray(map_arrays["selected_trace_coefficients"], dtype=np.complex128)
        dim = int(interior.size + trace.size)
        if (
            interior.shape != (450,) or trace.shape != (432,) or dim != 882
            or np.intersect1d(interior, trace).size
            or not np.array_equal(np.sort(np.r_[interior, trace]), np.arange(dim))
            or active_ids.shape != (432,) or not np.array_equal(np.sort(active_ids), active_ids)
            or map_arrays["trace_original_rows"].shape != (432,)
            or local_rows.shape != (1,)
            or int(local_rows[0]) != expected["selected_local_trace_row"]
            or map_arrays["trace_original_rows"][local_rows[0]] != V14_V8_STAR_ORIGINAL_ROW
            or selected_coefficients.shape != (1,)
            or selected_coefficients[0] != 1.0 + 0.0j
        ):
            raise ValueError(f"V14 V8 cell{cell} true interior/trace partition or target row differs")
        target = np.flatnonzero(active_ids == V14_V8_STAR_ACTIVE_ROW)
        if target.size != 1:
            raise ValueError(f"V14 V8 cell{cell} active target row is not unique")
        expansion = csr_matrix(
            (
                np.asarray(map_arrays["trace_expansion_data"], dtype=np.complex128),
                np.asarray(map_arrays["trace_expansion_indices"], dtype=np.int32),
                np.asarray(map_arrays["trace_expansion_indptr"], dtype=np.int32),
            ),
            shape=(trace.size, active_ids.size),
        )
        if (
            not expansion.has_canonical_format
            or expansion.indptr.shape != (trace.size + 1,)
            or not np.array_equal(expansion[local_rows[0], :].toarray().reshape(-1), np.eye(1, active_ids.size, int(target[0]), dtype=np.complex128).reshape(-1))
        ):
            raise ValueError(f"V14 V8 cell{cell} selected trace row does not map to the frozen active target")
        tensor_name = f"task41_p0_v8_selected_cell{cell}_candidate_oriented_tensor"
        lu_name = f"task41_p0_v8_selected_cell{cell}_candidate_interior_lu"
        pivots_name = f"task41_p0_v8_selected_cell{cell}_candidate_interior_lu_pivots"
        tensor = array(tensor_name, label=f"V8 cell{cell}/candidate oriented tensor", dtype="complex128")
        lu = array(lu_name, label=f"V8 cell{cell}/candidate interior LU", dtype="complex128")
        pivots = array(pivots_name, label=f"V8 cell{cell}/candidate interior pivots", dtype="int32")
        tensor_ref = arrays_by_name[tensor_name]
        lu_ref = arrays_by_name[lu_name]
        pivots_ref = arrays_by_name[pivots_name]
        if tensor.shape != (dim, dim) or lu.shape != (interior.size, interior.size) or pivots.shape != (interior.size,):
            raise ValueError(f"V14 V8 cell{cell} candidate tensor/LU/pivot dimensions differ")
        identity_payload = {
            "producer_report_sha256": V14_V8_STAR_REPORT_SHA256,
            "cell_index": cell,
            "coordinate_sha256": expected["coordinate_sha256"],
            "tensor_sha256": tensor_ref["sha256"],
            "interior_lu_sha256": lu_ref["sha256"],
            "pivots_sha256": pivots_ref["sha256"],
            "interior_positions_sha256": map_refs["interior_positions"]["sha256"],
            "trace_positions_sha256": map_refs["trace_positions"]["sha256"],
        }
        matrix_identity = hashlib.sha256(
            json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode("ascii")
        ).hexdigest()
        local = {
            "cell_index": cell,
            "cell_tag": expected["cell_tag"],
            "permutation": expected["permutation"],
            "actual_coordinate_sha256": expected["coordinate_sha256"],
            "interior_positions": interior,
            "trace_positions": trace,
            "active_ids": active_ids,
            "trace_expansion": expansion,
            "target_active_position": int(target[0]),
            "K": np.asarray(tensor[np.ix_(interior, interior)], dtype=np.complex128),
            "J": np.asarray(tensor[np.ix_(trace, interior)], dtype=np.complex128),
            "LU": lu,
            "pivots": pivots,
            "tensor_ref": tensor_ref,
            "lu_ref": lu_ref,
            "pivots_ref": pivots_ref,
            "matrix_identity": matrix_identity,
            "column_terms": {},
        }
        for column in V14_COLUMNS:
            state_terms: dict[str, dict[str, Any]] = {}
            reference_b_i: np.ndarray | None = None
            for state in state_names:
                prefix = f"task41_p0_v8_selected_cell{cell}_col{column}_{state}"
                b_i_name = f"{prefix}_input_b_i"
                s_action_name = f"{prefix}_candidate_S_action"
                b_i = array(b_i_name, label=f"V8 cell{cell}/column{column}/{state} input b_i", dtype="complex128")
                s_action = array(s_action_name, label=f"V8 cell{cell}/column{column}/{state} candidate S_action", dtype="complex128")
                if b_i.shape != (interior.size,) or s_action.shape != (trace.size,):
                    raise ValueError(f"V14 V8 cell{cell}/column{column}/{state} saved RHS/action shape differs")
                if reference_b_i is None:
                    reference_b_i = b_i
                elif not np.array_equal(reference_b_i, b_i):
                    raise ValueError(f"V14 V8 cell{cell}/column{column} j0/j3 b_i is not bitwise equal")
                state_terms[state] = {
                    "b_i": b_i,
                    "b_i_ref": arrays_by_name[b_i_name],
                    "s_action": s_action,
                    "s_action_ref": arrays_by_name[s_action_name],
                }
            local["column_terms"][column] = {
                "b_i": reference_b_i,
                "b_i_ref": state_terms["j0"]["b_i_ref"],
                "old_z_b": None,
                "old_z_b_ref": None,
                "state_terms": state_terms,
            }
        cells[cell] = local

    target_row = V14_V8_STAR_ORIGINAL_ROW
    updated = dict(source)
    updated.update({
        "stage": "saved_star_extension",
        "cell_order": V14_V8_STAR_CELLS,
        "columns": V14_COLUMNS,
        "state_rows": [
            {"column": column, "state": state}
            for column in V14_COLUMNS for state in state_names
        ],
        "target_active_row": V14_V8_STAR_ACTIVE_ROW,
        "target_original_row": target_row,
        "star_producer_report_path": str(report_path),
        "star_producer_report_sha256": V14_V8_STAR_REPORT_SHA256,
        "star_cell_identities": [
            {
                "cell_index": cell,
                **V14_V8_STAR_IDENTITIES[cell],
                "tensor_sha256": cells[cell]["tensor_ref"]["sha256"],
                "interior_lu_sha256": cells[cell]["lu_ref"]["sha256"],
                "pivots_sha256": cells[cell]["pivots_ref"]["sha256"],
                "matrix_identity": cells[cell]["matrix_identity"],
            }
            for cell in V14_V8_STAR_CELLS
        ],
        "prior_stage_reused": prior,
        "cells": cells,
    })
    b_t_by_column = {}
    b_t_ref_by_column = dict(source["b_t_ref_by_column"])
    b_alpha_by_column = {}
    b_alpha_refs_by_column = dict(source["b_alpha_refs_by_column"])
    for column in V14_COLUMNS:
        native = source["native_rhs_arrays_by_column"][column]
        beta_rows = source["b_alpha_rows_by_column"][column]
        beta_values = source["b_alpha_values_by_column"][column]
        if target_row >= native.size or np.any(beta_rows < 0) or np.any(beta_rows >= native.size):
            raise ValueError(f"V14 V8 target row {target_row} is outside the donor storage")
        selected = beta_values[beta_rows == target_row]
        if selected.size > 1:
            raise ValueError(f"V14 V8 target row {target_row} has duplicate B-alpha entries")
        b_t_by_column[column] = complex(native[target_row])
        b_alpha_by_column[column] = complex(selected[0]) if selected.size else 0.0 + 0.0j
    updated["b_t_by_column"] = b_t_by_column
    updated["b_t_ref_by_column"] = b_t_ref_by_column
    updated["b_alpha_by_column"] = b_alpha_by_column
    updated["b_alpha_refs_by_column"] = b_alpha_refs_by_column
    y_by_column_state: dict[tuple[int, str], complex] = {}
    for state_row in updated["state_rows"]:
        column = int(state_row["column"])
        state = str(state_row["state"])
        y = 0.0 + 0.0j
        for cell in V14_V8_STAR_CELLS:
            local = cells[cell]
            term = local["column_terms"][column]["state_terms"][state]
            projected = np.asarray(
                local["trace_expansion"].conj().T @ term["s_action"], dtype=np.complex128
            ).reshape(-1)
            y += complex(projected[local["target_active_position"]])
        y += updated["b_alpha_by_column"][column]
        y_by_column_state[(column, state)] = y
    updated["y_by_column_state"] = y_by_column_state
    return updated
