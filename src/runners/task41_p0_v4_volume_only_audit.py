"""Supervised Task41 V4 volume-only extraction and RHS attribution worker."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import shutil
from pathlib import Path
import sys
from time import perf_counter
import math
from typing import Any, Mapping

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TASK41_P0_V4_SOURCE_REPORT_SHA256 = (
    "09e96eb8c9d52b4cf0c29570fd8df3c1f820bc208104d91edd102978dfc9c4d5"
)
TASK41_P0_V4_VOLUME_ONLY_RECEIPT_SHA256 = (
    "90e65f40343f2e933e203af5ffa1292ca533b77e70f5af97e25d34b89b69a05d"
)
TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256 = (
    "a47eb7a8795b5af542c23ae45915588d89c962d1af1bb8360b8a9d42f1e7c031"
)
TASK41_P0_V5_REFERENCE_CELLS = (26762, 26897)
TASK41_P0_V6_PREFIX_CELLS = (26762, 26897, 0, 1, 2, 5, 6, 7505)
TASK41_P0_V6_LOCAL_SCREEN = 1.0e-11
TASK41_P0_V4_SELECTED_ACTIVE_ROW = 5_458_716
TASK41_P0_V4_SELECTED_ORIGINAL_ROW = 17_692_332
TASK41_P0_V8_SELECTED_ACTIVE_ROW = 4_766_937
TASK41_P0_V8_V7_INDEX_SHA256 = (
    "59237641d681a48220afa6662c57df4ebfad7a9340054630a614d1cda7a8c621"
)
TASK41_P0_V8_V6_INDEX_SHA256 = (
    "fc0786e823ee7acb40d1f3833568409f47fb854d189fde4def889d84050cd907"
)
TASK41_P0_V8_V6_REPORT_SHA256 = (
    "72c01eb9a7780ba86a7d8b8de6cfc1fd25e04fead2170788a5f492cd12ebd06e"
)
TASK41_P0_V8_V7_CONSUMER_SOURCE_SHA = "184822fa7ec5cd2af33a6ff39b5c6e7e5641cab6"
TASK41_P0_V8_V6_PRODUCER_SOURCE_SHA = "210fbbf271faa14c62ac30153b80332d0e645982"
TASK41_P0_V8_V6_ARRAY_PAYLOAD_BYTES = 4_514_199_336
TASK41_P0_V8_PRIOR_ARRAY_BYTES = 14_622_146_704
TASK41_P0_V8_V7_ARRAY_SHA256 = {
    "task41_p0_v7_attribution_col0_j0_corrected_full_closure": "b8e01f2aa0b3497a4094c809ededf7b18cd34ba056dfe8679901831e0f555966",
    "task41_p0_v7_attribution_col0_j0_corrected_volume_closure": "dc722dccf3b80e374b488026ec54adddc26b4c36e536cccc25b06ae5f5eac045",
    "task41_p0_v7_attribution_col0_j3_corrected_full_closure": "6f489cdcbe1ac3bd4bdbe5e63488993fd61af0e685e2e3d9d075870fc92ae363",
    "task41_p0_v7_attribution_col0_j3_corrected_volume_closure": "c6def8084dddbc33d223071c6d54483dbf9450052e83ca6eac97cee47c612e3a",
    "task41_p0_v7_attribution_col1_j0_corrected_full_closure": "ea35cfaf104013401845ee8246fbe14319c7153f1b5fa57a9cb02b713b284fc9",
    "task41_p0_v7_attribution_col1_j0_corrected_volume_closure": "5340d84a86b2848ff8337f85ef310a41e2082531a3a73179de75a1a2115132b8",
    "task41_p0_v7_attribution_col1_j3_corrected_full_closure": "1fe9e1125d187fe2c4007eae50456d3a591b6dcfd3790d2783fe1a0942c42ba2",
    "task41_p0_v7_attribution_col1_j3_corrected_volume_closure": "54bc113c027b5538c3fed6fe3bbfb5e8d46358360100a98733d700d975d0d8e2",
}
TASK41_P0_V5_POSTBUILD_SAFETY_FACTOR = 1.10
TASK41_P0_V5_PREFIX_MINIMUM_SECONDS = 600.0
TASK41_P0_V5_TERMINATION_RESERVE_SECONDS = 300.0


def _v6_screen_metrics(candidate: np.ndarray, reference: np.ndarray) -> dict[str, Any]:
    left = np.asarray(candidate, dtype=np.complex128)
    right = np.asarray(reference, dtype=np.complex128)
    if left.shape != right.shape or not np.isfinite(left).all() or not np.isfinite(right).all():
        raise ValueError("V6 local comparison arrays must be finite and have matching shapes")
    difference = left - right
    absolute = float(np.linalg.norm(difference.ravel()))
    relative = absolute / max(
        float(np.linalg.norm(right.ravel())), np.finfo(np.float64).tiny
    )
    maximum = float(np.max(np.abs(difference), initial=0.0))
    return {
        "status": "PASS" if relative <= TASK41_P0_V6_LOCAL_SCREEN else "FAIL",
        "relative_frobenius": relative,
        "absolute_frobenius": absolute,
        "max_abs": maximum,
        "relative_limit": TASK41_P0_V6_LOCAL_SCREEN,
    }


def _v6_saved_local_action_diagnostic(
    reference_action: np.ndarray,
    candidate_action: np.ndarray,
    *,
    frozen_denominators: tuple[float, ...],
    column_index: int,
    trace_positions: np.ndarray,
    active_ids: np.ndarray,
    trace_expansion: Any,
    selected_active_row: int,
) -> dict[str, Any]:
    if not 0 <= column_index < len(frozen_denominators):
        raise ValueError(
            "V6 saved action column index is outside the frozen denominator table: "
            f"{column_index}"
        )
    frozen_denominator = float(frozen_denominators[column_index])
    if not np.isfinite(frozen_denominator) or frozen_denominator <= 0.0:
        raise ValueError("V6 frozen action denominator must be finite and positive")
    reference = np.asarray(reference_action, dtype=np.complex128)
    candidate = np.asarray(candidate_action, dtype=np.complex128)
    difference = _v6_screen_metrics(candidate, reference)
    trace = np.asarray(trace_positions, dtype=np.int64)
    active = np.asarray(active_ids, dtype=np.int64)
    target_locations = np.flatnonzero(active == int(selected_active_row))
    if target_locations.size > 1:
        raise ValueError("V6 selected active row is duplicated in a cell trace map")
    if target_locations.size:
        weights = np.asarray(
            trace_expansion.getcol(int(target_locations[0])).toarray(),
            dtype=np.complex128,
        ).reshape(-1)
        reference_row = complex(np.vdot(weights, reference[trace]))
        candidate_row = complex(np.vdot(weights, candidate[trace]))
    else:
        reference_row = candidate_row = 0.0 + 0.0j
    return {
        "full_local_action": difference,
        "full_local_action_difference_over_frozen_denominator": (
            difference["absolute_frobenius"] / frozen_denominator
        ),
        "full_local_action_scale_check": "diagnostic_only",
        "frozen_denominator": frozen_denominator,
        "selected_active_row": int(selected_active_row),
        "selected_row_reference": [reference_row.real, reference_row.imag],
        "selected_row_candidate": [candidate_row.real, candidate_row.imag],
        "selected_row_difference_over_frozen_denominator": (
            abs(candidate_row - reference_row) / frozen_denominator
        ),
        "selected_row_scale_check": "diagnostic_only",
    }


def _v6_reconstruct_oriented_tensor(
    blocks: Mapping[str, np.ndarray],
    interior_positions: np.ndarray,
    trace_positions: np.ndarray,
    dimension: int,
) -> np.ndarray:
    interior = np.asarray(interior_positions, dtype=np.int64)
    trace = np.asarray(trace_positions, dtype=np.int64)
    if (
        interior.ndim != 1
        or trace.ndim != 1
        or np.intersect1d(interior, trace).size
        or np.unique(np.concatenate((interior, trace))).size != dimension
        or not np.array_equal(
            np.sort(np.concatenate((interior, trace))), np.arange(dimension)
        )
    ):
        raise ValueError("V6 interior/trace positions do not partition the local tensor")
    expected = {
        "K": (len(interior), len(interior)),
        "G": (len(interior), len(trace)),
        "J": (len(trace), len(interior)),
        "L": (len(trace), len(trace)),
    }
    if any(np.asarray(blocks[name]).shape != shape for name, shape in expected.items()):
        raise ValueError("V6 saved actual block has the wrong local shape")
    result = np.empty((dimension, dimension), dtype=np.complex128)
    result[np.ix_(interior, interior)] = np.asarray(blocks["K"])
    result[np.ix_(interior, trace)] = np.asarray(blocks["G"])
    result[np.ix_(trace, interior)] = np.asarray(blocks["J"])
    result[np.ix_(trace, trace)] = np.asarray(blocks["L"])
    if not np.isfinite(result).all():
        raise ValueError("V6 reconstructed V4 actual tensor contains non-finite values")
    return result


def _v6_condense_blocks(blocks: Mapping[str, np.ndarray]) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    from scipy.linalg import lu_solve

    from src.solvers.hcurl_assembly_time_condensation import _strict_local_lu

    K = np.asarray(blocks["K"], dtype=np.complex128)
    G = np.asarray(blocks["G"], dtype=np.complex128)
    J = np.asarray(blocks["J"], dtype=np.complex128)
    L = np.asarray(blocks["L"], dtype=np.complex128)
    factor, strict_residual = _strict_local_lu(K)
    R = -lu_solve(factor, G)
    adjoint_solution = lu_solve(factor, J.conj().T, trans=2)
    T = -adjoint_solution.conj().T
    S = L + J @ R
    return {"R": R, "T": T, "S": S}, {
        "strict_lu_identity_relative_defect": float(strict_residual),
        "strict_lu_passed": True,
        "condensation_defects_relative": _v6_condensation_defects(
            blocks, {"R": R, "T": T}
        ),
    }


def _v6_condensation_defects(
    blocks: Mapping[str, np.ndarray], rts: Mapping[str, np.ndarray]
) -> dict[str, float]:
    K = np.asarray(blocks["K"], dtype=np.complex128)
    G = np.asarray(blocks["G"], dtype=np.complex128)
    J = np.asarray(blocks["J"], dtype=np.complex128)
    R = np.asarray(rts["R"], dtype=np.complex128)
    T = np.asarray(rts["T"], dtype=np.complex128)
    tiny = np.finfo(np.float64).tiny
    return {
        "KR_plus_G": float(np.linalg.norm((K @ R + G).ravel()))
        / max(float(np.linalg.norm(G.ravel())), float(np.linalg.norm((K @ R).ravel())), tiny),
        "TK_plus_J": float(np.linalg.norm((T @ K + J).ravel()))
        / max(float(np.linalg.norm(J.ravel())), float(np.linalg.norm((T @ K).ravel())), tiny),
    }


class _CandidateNotAdmitted(RuntimeError):
    """Exact-geometry candidate lacks fixed-window or resource headroom."""


def _v4_required_checker_watchdog_elapsed_seconds(
    v4_extraction: Mapping[str, Any],
) -> float:
    value = float(v4_extraction["required_checker_watchdog_elapsed_seconds"])
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError("V4 required-checker watchdog elapsed time is not finite and positive")
    return value


def _v6_postbuild_reserve_evidence(
    receipt_path: str | Path,
    *,
    donor_contract: Mapping[str, Any],
    donor_contract_sha256: str,
    donor_manifest_sha256: str,
    current_execution_window_sha256: str,
) -> dict[str, Any]:
    path = Path(receipt_path)
    raw = path.read_bytes()
    receipt_sha256 = hashlib.sha256(raw).hexdigest()
    if receipt_sha256 != TASK41_P0_V4_VOLUME_ONLY_RECEIPT_SHA256:
        raise ValueError("frozen V4 post-build receipt SHA-256 differs")
    receipt = json.loads(raw)
    identity = receipt.get("identity", {})
    extraction = receipt.get("volume_only_extraction", {})
    donor_source = donor_contract.get("source", {})
    donor_window = donor_contract.get("window", {})
    expected_identity = {
        "v3_donor_source_sha": donor_source.get("sha"),
        "v3_donor_contract_sha256": donor_contract_sha256,
        "v3_donor_manifest_sha256": donor_manifest_sha256,
        "campaign_window_sha256": donor_window.get("sha256"),
    }
    for key, expected in expected_identity.items():
        if not expected or identity.get(key) != expected:
            raise ValueError(f"frozen V4 post-build donor identity mismatch at identity.{key}")
    if extraction.get("status") != "COMPLETED":
        raise ValueError("frozen V4 post-build extraction is not completed")
    if (
        extraction.get("source_sha")
        != identity.get("v4_volume_only_consumer_source_sha")
    ):
        raise ValueError("frozen V4 post-build consumer source identity differs")
    if (
        extraction.get("contract_sha256")
        != identity.get("v4_volume_consumer_contract_sha256")
    ):
        raise ValueError("frozen V4 post-build consumer contract identity differs")
    if extraction.get("report_sha256") != TASK41_P0_V4_SOURCE_REPORT_SHA256:
        raise ValueError("frozen V4 post-build report SHA-256 differs")
    parent_seconds = float(extraction["service_parent_seconds"])
    worker_seconds = float(extraction["worker_elapsed_seconds"])
    if (
        not math.isfinite(parent_seconds)
        or parent_seconds <= 0.0
        or not math.isfinite(worker_seconds)
        or worker_seconds <= 0.0
    ):
        raise ValueError("V4 measured post-build service/worker time is not finite and positive")
    return {
        "schema": "task41.p0.v6.postbuild_reserve_evidence.v1",
        "path": str(path),
        "sha256": receipt_sha256,
        "historical_v4_evidence_identity": {
            "campaign_window_sha256": identity["campaign_window_sha256"],
            "v3_donor_source_sha": identity["v3_donor_source_sha"],
            "v3_donor_contract_sha256": identity["v3_donor_contract_sha256"],
            "v3_donor_manifest_sha256": identity["v3_donor_manifest_sha256"],
            "v4_volume_only_consumer_source_sha": identity[
                "v4_volume_only_consumer_source_sha"
            ],
            "v4_volume_consumer_contract_sha256": identity[
                "v4_volume_consumer_contract_sha256"
            ],
            "report_sha256": extraction["report_sha256"],
        },
        "current_execution_window_sha256": current_execution_window_sha256,
        "measured_service_parent_seconds": parent_seconds,
        "measured_worker_seconds": worker_seconds,
        "required_checker_watchdog_seconds": (
            _v4_required_checker_watchdog_elapsed_seconds(extraction)
        ),
        "safety_factor": TASK41_P0_V5_POSTBUILD_SAFETY_FACTOR,
    }


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _persist_array(
    directory: Path,
    name: str,
    value: np.ndarray,
    *,
    sha256_file: Any,
) -> dict[str, Any]:
    if not name or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in name):
        raise ValueError("Task41 V4 evidence array name is not a safe leaf")
    path = directory / f"{name}.npy"
    temporary = directory / f".{name}.npy.tmp"
    if path.exists() or temporary.exists():
        raise FileExistsError(f"Task41 V4 evidence output already exists: {path}")
    array = np.asarray(value)
    with temporary.open("xb") as stream:
        np.save(stream, array, allow_pickle=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "bytes": int(path.stat().st_size),
        "shape": list(array.shape),
        "dtype": str(array.dtype),
    }


def _v8_load_bound_array(
    record: Mapping[str, Any],
    *,
    results_root: Path,
    path_basis: Path | None = None,
    sha256_file: Any,
    expected_sha256: str | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Verify one selected saved array and keep it memory-mapped."""

    raw_path = record.get("path")
    if not isinstance(raw_path, str):
        raise ValueError("V8 saved-array record has no path")
    raw = Path(raw_path)
    basis = ROOT if path_basis is None else Path(path_basis)
    path = (raw if raw.is_absolute() else basis / raw).resolve(strict=True)
    digest = expected_sha256 or record.get("sha256")
    if (
        not path.is_relative_to(results_root)
        or not isinstance(digest, str)
        or len(digest) != 64
        or sha256_file(path) != digest
    ):
        raise ValueError(f"V8 saved-array path or SHA-256 differs: {path}")
    if type(record.get("bytes")) is not int or path.stat().st_size != record["bytes"]:
        raise ValueError(f"V8 saved-array byte count differs: {path}")
    value = np.load(path, mmap_mode="r", allow_pickle=False)
    if (
        list(value.shape) != record.get("shape")
        or str(value.dtype) != record.get("dtype")
        or value.dtype.kind not in "fciu"
    ):
        raise ValueError(f"V8 saved-array layout differs: {path}")
    for start in range(0, int(value.shape[0]) if value.ndim else 1, 262_144):
        chunk = value[start : start + 262_144] if value.ndim else value
        if not np.isfinite(chunk).all():
            raise ValueError(f"V8 saved-array has non-finite data: {path}")
    return value, {
        "name": str(record.get("name", path.stem)),
        "path": str(path),
        "sha256": digest,
        "bytes": int(record["bytes"]),
        "shape": list(value.shape),
        "dtype": str(value.dtype),
    }


def _v8_load_saved_operand_arrays(
    *,
    results_root: Path,
    fixed_window_sha256: str,
    donor_existing_evidence_bytes: int,
    sha256_file: Any,
) -> dict[str, Any]:
    """Bind only the V6/V7 arrays needed by the selected-row operand audit."""

    results_root = Path(results_root).resolve(strict=True)
    outcomes = ROOT / "docs/task41extra_phi90_p50x50_g17x20/outcomes"
    v6_index_path = outcomes / "b0_v6_actual_qmetric_hash_index_20261021.json"
    v7_index_path = outcomes / "b0_v7_saved_attribution_20261021.json"
    if sha256_file(v6_index_path) != TASK41_P0_V8_V6_INDEX_SHA256:
        raise ValueError("V8 frozen V6 array index SHA-256 differs")
    if sha256_file(v7_index_path) != TASK41_P0_V8_V7_INDEX_SHA256:
        raise ValueError("V8 frozen V7 saved-attribution index SHA-256 differs")
    v6_index = json.loads(v6_index_path.read_text(encoding="utf-8"))
    v7_index = json.loads(v7_index_path.read_text(encoding="utf-8"))
    v6_payload = v6_index.get("candidate_persisted_arrays")
    if (
        not isinstance(v6_payload, Mapping)
        or v6_payload.get("count") != 174
        or v6_payload.get("declared_payload_bytes") != TASK41_P0_V8_V6_ARRAY_PAYLOAD_BYTES
        or v6_index.get("window_sha256") != fixed_window_sha256
    ):
        raise ValueError("V8 frozen V6 array-index count, bytes, or window differs")
    path_basis = Path(str(v6_payload.get("path_basis", ""))).resolve(strict=True)
    if path_basis != ROOT.resolve(strict=True):
        raise ValueError("V8 V6 array path basis is not this canonical workstation repository")
    v6_report_path = Path(str(v6_index.get("candidate_report_path", ""))).resolve(strict=True)
    if (
        not v6_report_path.is_relative_to(results_root)
        or v6_report_path.stat().st_size != v6_index.get("candidate_report_bytes")
        or sha256_file(v6_report_path) != TASK41_P0_V8_V6_REPORT_SHA256
    ):
        raise ValueError("V8 frozen V6 candidate report path, size, or SHA-256 differs")
    v6_report = json.loads(v6_report_path.read_text(encoding="utf-8"))
    v6_records = v6_payload.get("items")
    report_records = v6_report.get("persisted_evidence_arrays")
    if (
        not isinstance(v6_records, list)
        or len(v6_records) != 174
        or not isinstance(report_records, list)
        or len(report_records) != 174
    ):
        raise ValueError("V8 V6 candidate report and compact index do not bind 174 arrays")

    def resolved_record_path(record: Mapping[str, Any], basis: Path) -> Path:
        raw = Path(str(record.get("path", "")))
        return (raw if raw.is_absolute() else basis / raw).resolve(strict=True)

    index_by_name = {str(item.get("name")): item for item in v6_records if isinstance(item, Mapping)}
    report_by_name = {
        str(item.get("name")): item for item in report_records if isinstance(item, Mapping)
    }
    if len(index_by_name) != 174 or len(report_by_name) != 174 or index_by_name.keys() != report_by_name.keys():
        raise ValueError("V8 V6 report and compact index array names differ")
    for name, record in index_by_name.items():
        report_record = report_by_name[name]
        if (
            record.get("bytes") != report_record.get("bytes")
            or record.get("dtype") != report_record.get("dtype")
            or record.get("shape") != report_record.get("shape")
            or record.get("sha256") != report_record.get("sha256")
            or resolved_record_path(record, path_basis) != resolved_record_path(report_record, ROOT)
        ):
            raise ValueError(f"V8 V6 array index/report identity differs for {name}")

    v7_identity = v7_index.get("identity")
    v7_audit = v7_index.get("audit")
    v7_records = v7_index.get("arrays", {}).get("records")
    if (
        not isinstance(v7_identity, Mapping)
        or v7_identity.get("fixed_window_sha256") != fixed_window_sha256
        or v7_identity.get("consumer_source_sha") != TASK41_P0_V8_V7_CONSUMER_SOURCE_SHA
        or v7_identity.get("candidate_producer_source_sha") != TASK41_P0_V8_V6_PRODUCER_SOURCE_SHA
        or not isinstance(v7_audit, Mapping)
        or not isinstance(v7_records, list)
        or len(v7_records) != 8
    ):
        raise ValueError("V8 frozen V7 attribution identity or eight-array inventory differs")
    v7_report_path = Path(str(v7_audit.get("report_path", ""))).resolve(strict=True)
    if (
        not v7_report_path.is_relative_to(results_root)
        or v7_report_path.stat().st_size != v7_audit.get("report_bytes")
        or sha256_file(v7_report_path) != v7_audit.get("report_sha256")
    ):
        raise ValueError("V8 frozen V7 full report path, size, or SHA-256 differs")

    required_v6_names = {
        "task41_p0_v6_qmetric_candidate_full_p6",
        "task41_p0_v6_qmetric_candidate_full_reduced_rhs",
    }
    for column in range(2):
        required_v6_names.add(f"task41_v4_d_volume_trace_col{column}")
        for state in ("j0", "j3"):
            required_v6_names.update(
                {
                    f"task41_p0_v6_qmetric_candidate_attribution_col{column}_{state}_{field}"
                    for field in ("T_r_i", "delta_t", "attributed_terms")
                }
            )
            required_v6_names.add(f"task41_v4_reduce_r_volume_{state}_col{column}")
            required_v6_names.add(f"task41_v4_reduce_r_full_{state}_col{column}")
    for cell_index in TASK41_P0_V6_PREFIX_CELLS:
        prefix = f"task41_v6_prefix_cell{cell_index}"
        required_v6_names.update(
            {
                f"{prefix}_candidate_raw_tensor",
                f"{prefix}_candidate_oriented_tensor",
                f"{prefix}_candidate_coordinates",
                f"{prefix}_reference_raw_tensor",
                f"{prefix}_reference_oriented_tensor",
            }
        )
        for role in ("candidate", "reference"):
            required_v6_names.update(
                f"{prefix}_{role}_{name}" for name in ("R", "T", "S")
            )
    for cell_index in TASK41_P0_V5_REFERENCE_CELLS:
        prefix = f"task41_v4_volume_cell_{cell_index}"
        required_v6_names.update(
            f"{prefix}_{name}"
            for name in (
                "interior_original_rows",
                "trace_original_rows",
                "active_ids",
                "trace_expansion_data",
                "trace_expansion_indices",
                "trace_expansion_indptr",
            )
        )
        prefix_numeric = f"task41_v6_prefix_cell{cell_index}"
        required_v6_names.update(
            f"{prefix_numeric}_col{column}_{state}_{role}_local_action"
            for column in range(2)
            for state in ("j0", "j3")
            for role in ("candidate", "reference")
        )
    missing = required_v6_names - index_by_name.keys()
    if missing:
        raise ValueError(f"V8 V6 input index omits selected closure operands: {sorted(missing)}")

    v6_arrays: dict[str, np.ndarray] = {}
    v6_artifacts: dict[str, dict[str, Any]] = {}
    for name in sorted(required_v6_names):
        array, artifact = _v8_load_bound_array(
            index_by_name[name],
            results_root=results_root,
            path_basis=path_basis,
            sha256_file=sha256_file,
        )
        v6_arrays[name] = array
        v6_artifacts[name] = artifact

    v7_by_name = {str(item.get("name")): item for item in v7_records if isinstance(item, Mapping)}
    expected_v7_names = set(TASK41_P0_V8_V7_ARRAY_SHA256)
    if v7_by_name.keys() != expected_v7_names:
        raise ValueError("V8 V7 closure array names differ from the frozen eight-item map")
    v7_arrays: dict[str, np.ndarray] = {}
    v7_artifacts: dict[str, dict[str, Any]] = {}
    for name in sorted(expected_v7_names):
        record = v7_by_name[name]
        if (
            record.get("sha256") != TASK41_P0_V8_V7_ARRAY_SHA256[name]
            or record.get("shape") != [5_688_000]
            or record.get("dtype") != "complex128"
            or record.get("bytes") != 91_008_128
        ):
            raise ValueError(f"V8 frozen V7 closure array metadata differs for {name}")
        array, artifact = _v8_load_bound_array(
            record,
            results_root=results_root,
            sha256_file=sha256_file,
            expected_sha256=TASK41_P0_V8_V7_ARRAY_SHA256[name],
        )
        v7_arrays[name] = array
        v7_artifacts[name] = artifact

    prior_array_bytes = (
        int(donor_existing_evidence_bytes)
        + int(v6_payload["declared_payload_bytes"])
        + sum(int(item["bytes"]) for item in v7_records)
    )
    if prior_array_bytes != TASK41_P0_V8_PRIOR_ARRAY_BYTES:
        raise ValueError(
            "V8 cumulative prior array payload differs from the frozen 16 GiB accounting "
            f"({prior_array_bytes} != {TASK41_P0_V8_PRIOR_ARRAY_BYTES})"
        )
    return {
        "v6_arrays": v6_arrays,
        "v7_arrays": v7_arrays,
        "v6_artifacts": v6_artifacts,
        "v7_artifacts": v7_artifacts,
        "v6_report": v6_report,
        "v6_records_by_name": index_by_name,
        "v6_index_path": str(v6_index_path.resolve()),
        "v6_index_sha256": TASK41_P0_V8_V6_INDEX_SHA256,
        "v6_report_path": str(v6_report_path),
        "v6_report_sha256": TASK41_P0_V8_V6_REPORT_SHA256,
        "v7_index_path": str(v7_index_path.resolve()),
        "v7_index_sha256": TASK41_P0_V8_V7_INDEX_SHA256,
        "v7_report_path": str(v7_report_path),
        "v7_report_sha256": str(v7_audit["report_sha256"]),
        "prior_array_payload_bytes": prior_array_bytes,
        "cumulative_array_cap_bytes": 16 * 1024**3,
        "remaining_array_cap_bytes": 16 * 1024**3 - prior_array_bytes,
    }


def _v8_chunked_pair_metrics(
    left: np.ndarray,
    right: np.ndarray,
    *,
    chunk_size: int = 131_072,
) -> dict[str, Any]:
    """Compare two saved complex vectors with float64 and real/imag longdouble."""

    a = np.asarray(left)
    b = np.asarray(right)
    if (
        a.ndim != 1
        or b.shape != a.shape
        or a.dtype != np.dtype(np.complex128)
        or b.dtype != np.dtype(np.complex128)
    ):
        raise ValueError("V8 closure vectors must be matching complex128 vectors")
    max_float = 0.0
    max_longdouble = np.longdouble(0.0)
    sum_sq_float = 0.0
    sum_sq_longdouble = np.longdouble(0.0)
    max_float_vs_longdouble = np.longdouble(0.0)
    for start in range(0, len(a), chunk_size):
        aa = np.asarray(a[start : start + chunk_size], dtype=np.complex128)
        bb = np.asarray(b[start : start + chunk_size], dtype=np.complex128)
        diff = aa - bb
        magnitude = np.abs(diff)
        max_float = max(max_float, float(magnitude.max(initial=0.0)))
        sum_sq_float += float(np.dot(magnitude, magnitude))
        dr = aa.real.astype(np.longdouble) - bb.real.astype(np.longdouble)
        di = aa.imag.astype(np.longdouble) - bb.imag.astype(np.longdouble)
        long_magnitude = np.sqrt(dr * dr + di * di)
        max_longdouble = max(max_longdouble, long_magnitude.max(initial=np.longdouble(0)))
        sum_sq_longdouble += np.sum(dr * dr + di * di, dtype=np.longdouble)
        float_r = diff.real.astype(np.longdouble)
        float_i = diff.imag.astype(np.longdouble)
        recomputed_error = np.sqrt((float_r - dr) ** 2 + (float_i - di) ** 2)
        max_float_vs_longdouble = max(
            max_float_vs_longdouble,
            recomputed_error.max(initial=np.longdouble(0)),
        )
    return {
        "vector_length": int(len(a)),
        "float64_difference_max_abs": max_float,
        "float64_difference_l2": math.sqrt(sum_sq_float),
        "longdouble_real_imag_difference_max_abs": float(max_longdouble),
        "longdouble_real_imag_difference_l2": float(np.sqrt(sum_sq_longdouble)),
        "float64_vs_longdouble_difference_max_abs": float(max_float_vs_longdouble),
        "longdouble_mantissa_bits": int(np.finfo(np.longdouble).nmant),
        "longdouble_is_wider_than_float64": bool(
            np.finfo(np.longdouble).nmant > np.finfo(np.float64).nmant
        ),
        "chunk_size": int(chunk_size),
    }


def _v8_recompose_saved_closure_inputs(
    *,
    active_original_rows: np.ndarray,
    native_rhs: np.ndarray,
    native_volume_rhs: np.ndarray,
    native_volume_action: np.ndarray,
    b_alpha_rows: np.ndarray,
    b_alpha_values: np.ndarray,
    full_p6: np.ndarray,
    full_reduced_rhs: np.ndarray,
    d_volume: np.ndarray,
    reduce_r_full: np.ndarray,
    reduce_r_volume: np.ndarray,
    T_r_i: np.ndarray,
    delta_t: np.ndarray,
    attributed_terms: np.ndarray,
    saved_full_closure: np.ndarray,
    saved_volume_closure: np.ndarray,
    column_index: int,
    paired_state_inputs: Mapping[str, np.ndarray] | None = None,
    chunk_size: int = 131_072,
) -> dict[str, Any]:
    """Recompose V7 closures from saved operands, not from the closure vectors."""

    active = np.asarray(active_original_rows, dtype=np.int64)
    vectors = {
        name: np.asarray(value)
        for name, value in (
            ("native_rhs", native_rhs),
            ("native_volume_rhs", native_volume_rhs),
            ("native_volume_action", native_volume_action),
        )
    }
    original_rows = vectors["native_rhs"].shape
    if (
        active.ndim != 1
        or np.unique(active).size != active.size
        or any(value.ndim != 1 or value.shape != original_rows for value in vectors.values())
        or vectors["native_rhs"].dtype != np.dtype(np.complex128)
        or vectors["native_volume_rhs"].dtype != np.dtype(np.complex128)
        or vectors["native_volume_action"].dtype != np.dtype(np.complex128)
        or (active.size and (np.any(active < 0) or np.any(active >= original_rows[0])))
    ):
        raise ValueError("V8 native closure operands or active-row map are malformed")
    rows = np.asarray(b_alpha_rows)
    beta_values = np.asarray(b_alpha_values)
    if (
        rows.ndim != 1
        or rows.dtype.kind not in "iu"
        or beta_values.shape != rows.shape
        or beta_values.dtype != np.dtype(np.complex128)
        or not np.isfinite(beta_values).all()
        or (rows.size and (np.any(rows < 0) or np.any(rows >= original_rows[0])))
    ):
        raise ValueError("V8 B-alpha rows or values are malformed")
    if not 0 <= int(column_index) < 2:
        raise ValueError("V8 full-action column index must be zero or one")
    full = np.asarray(full_p6)
    reduced = np.asarray(full_reduced_rhs)
    if (
        full.ndim != 2
        or full.shape[1] != 2
        or reduced.shape != full.shape
        or full.shape[0] < active.size
        or full.dtype != np.dtype(np.complex128)
        or reduced.dtype != np.dtype(np.complex128)
    ):
        raise ValueError("V8 saved trace/port action and reduced RHS layouts differ")

    def active_vector(name: str, value: np.ndarray) -> np.ndarray:
        result = np.asarray(value)
        if result.shape != (active.size,) or result.dtype != np.dtype(np.complex128):
            raise ValueError(f"V8 saved active vector {name} has an invalid layout")
        return result

    active_inputs = {
        name: active_vector(name, value)
        for name, value in (
            ("d_volume", d_volume),
            ("reduce_r_full", reduce_r_full),
            ("reduce_r_volume", reduce_r_volume),
            ("T_r_i", T_r_i),
            ("delta_t", delta_t),
            ("attributed_terms", attributed_terms),
            ("saved_full_closure", saved_full_closure),
            ("saved_volume_closure", saved_volume_closure),
        )
    }
    paired_inputs: dict[str, np.ndarray] = {}
    if paired_state_inputs is not None:
        for name in ("native_volume_action", "T_r_i", "delta_t", "attributed_terms"):
            value = np.asarray(paired_state_inputs.get(name))
            expected_shape = original_rows if name == "native_volume_action" else (active.size,)
            if value.shape != expected_shape or value.dtype != np.dtype(np.complex128):
                raise ValueError(f"V8 paired-state operand {name} has an invalid layout")
            paired_inputs[name] = value
    active_order = np.argsort(active, kind="stable")
    sorted_active = active[active_order]
    active_ids = np.searchsorted(sorted_active, rows)
    if active_ids.size and (
        np.any(active_ids >= sorted_active.size)
        or np.any(sorted_active[np.minimum(active_ids, sorted_active.size - 1)] != rows)
    ):
        raise ValueError("V8 B-alpha row is not an independent active trace row")
    active_ids = active_order[active_ids]
    beta_order = np.argsort(active_ids, kind="stable")
    beta_active_ids = active_ids[beta_order]
    beta_sorted_values = beta_values[beta_order]

    longdouble = np.longdouble

    def wide(value: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        value = np.asarray(value, dtype=np.complex128)
        return value.real.astype(longdouble), value.imag.astype(longdouble)

    def wide_add(
        left: tuple[np.ndarray, np.ndarray], right: tuple[np.ndarray, np.ndarray], sign: int = 1
    ) -> tuple[np.ndarray, np.ndarray]:
        return left[0] + sign * right[0], left[1] + sign * right[1]

    def metric_state() -> dict[str, Any]:
        return {"sum_squares": longdouble(0), "max_abs": longdouble(0), "max_row": None}

    def update_metric(state: dict[str, Any], real: np.ndarray, imag: np.ndarray, row_start: int) -> None:
        magnitude_sq = real * real + imag * imag
        if magnitude_sq.size:
            max_local = int(np.argmax(magnitude_sq))
            local_max = np.sqrt(magnitude_sq[max_local])
            if local_max > state["max_abs"]:
                state["max_abs"] = local_max
                state["max_row"] = row_start + max_local
            state["sum_squares"] += np.sum(magnitude_sq, dtype=longdouble)

    metric_names = (
            "full_float64_recompose_vs_saved",
            "volume_float64_recompose_vs_saved",
            "full_float64_reduce_r_grouping_vs_saved",
            "volume_float64_reduce_r_grouping_vs_saved",
            "full_longdouble_recompose_vs_saved",
            "volume_longdouble_recompose_vs_saved",
            "full_longdouble_closure",
            "volume_longdouble_closure",
            "full_float64_vs_longdouble_last_combination",
            "volume_float64_vs_longdouble_last_combination",
            "full_original_rhs_grouping_vs_saved_reduce_r",
            "volume_original_rhs_grouping_vs_saved_reduce_r",
            "full_rebuilt_reduce_r_vs_saved",
            "volume_rebuilt_reduce_r_vs_saved",
            "full_longdouble_dhat_j0_vs_j3",
            "volume_longdouble_dhat_j0_vs_j3",
    )
    metrics: dict[str, dict[str, Any]] = {
        name: metric_state()
        for name in metric_names
        if paired_inputs or name not in {
            "full_longdouble_dhat_j0_vs_j3",
            "volume_longdouble_dhat_j0_vs_j3",
        }
    }
    for start in range(0, active.size, chunk_size):
        stop = min(active.size, start + chunk_size)
        original = active[start:stop]
        beta = np.zeros(stop - start, dtype=np.complex128)
        beta_lo = int(np.searchsorted(beta_active_ids, start, side="left"))
        beta_hi = int(np.searchsorted(beta_active_ids, stop, side="left"))
        if beta_hi > beta_lo:
            np.add.at(
                beta,
                beta_active_ids[beta_lo:beta_hi] - start,
                beta_sorted_values[beta_lo:beta_hi],
            )

        f_t = vectors["native_rhs"][original]
        b_t = vectors["native_volume_rhs"][original]
        n_t = vectors["native_volume_action"][original]
        p6_t = full[start:stop, column_index]
        reduced_t = reduced[start:stop, column_index]
        d_full = p6_t - reduced_t
        d_vol = active_inputs["d_volume"][start:stop]
        u = active_inputs["T_r_i"][start:stop]
        delta = active_inputs["delta_t"][start:stop]
        q = active_inputs["attributed_terms"][start:stop]
        right = delta + q
        r_full = (f_t - n_t) - beta
        r_volume = b_t - n_t
        full_float = ((d_full + r_full) + u) - right
        volume_float = ((d_vol + r_volume) + u) - right
        full_reduce_r_float = (d_full + active_inputs["reduce_r_full"][start:stop]) - right
        volume_reduce_r_float = (d_vol + active_inputs["reduce_r_volume"][start:stop]) - right

        f_wide, b_wide, n_wide = wide(f_t), wide(b_t), wide(n_t)
        beta_wide = wide(beta)
        u_wide, delta_wide, q_wide = wide(u), wide(delta), wide(q)
        p6_wide, reduced_wide = wide(p6_t), wide(reduced_t)
        d_full_wide = wide_add(p6_wide, reduced_wide, -1)
        d_volume_wide = wide(d_vol)
        r_full_wide = wide_add(wide_add(f_wide, n_wide, -1), beta_wide, -1)
        r_volume_wide = wide_add(b_wide, n_wide, -1)
        right_wide = wide_add(delta_wide, q_wide)
        full_wide = wide_add(
            wide_add(wide_add(d_full_wide, r_full_wide), u_wide), right_wide, -1
        )
        volume_wide = wide_add(
            wide_add(wide_add(d_volume_wide, r_volume_wide), u_wide), right_wide, -1
        )
        full_reduce_r_wide = wide_add(
            wide_add(d_full_wide, wide(active_inputs["reduce_r_full"][start:stop])),
            right_wide,
            -1,
        )
        volume_reduce_r_wide = wide_add(
            wide_add(d_volume_wide, wide(active_inputs["reduce_r_volume"][start:stop])),
            right_wide,
            -1,
        )
        full_dhat_wide = wide_add(wide_add(right_wide, r_full_wide, -1), u_wide, -1)
        volume_dhat_wide = wide_add(wide_add(right_wide, r_volume_wide, -1), u_wide, -1)

        saved_full = active_inputs["saved_full_closure"][start:stop]
        saved_volume = active_inputs["saved_volume_closure"][start:stop]
        chunk_inputs = (
            f_t,
            b_t,
            n_t,
            p6_t,
            reduced_t,
            beta,
            d_vol,
            u,
            delta,
            q,
            active_inputs["reduce_r_full"][start:stop],
            active_inputs["reduce_r_volume"][start:stop],
            saved_full,
            saved_volume,
        )
        if any(not np.isfinite(value).all() for value in chunk_inputs):
            raise ValueError("V8 saved closure operands contain non-finite data")
        for key, values in (
            ("full_float64_recompose_vs_saved", full_float - saved_full),
            ("volume_float64_recompose_vs_saved", volume_float - saved_volume),
            ("full_float64_reduce_r_grouping_vs_saved", full_reduce_r_float - saved_full),
            ("volume_float64_reduce_r_grouping_vs_saved", volume_reduce_r_float - saved_volume),
            ("full_original_rhs_grouping_vs_saved_reduce_r", full_float - full_reduce_r_float),
            ("volume_original_rhs_grouping_vs_saved_reduce_r", volume_float - volume_reduce_r_float),
            (
                "full_rebuilt_reduce_r_vs_saved",
                ((f_t - n_t) - beta + u) - active_inputs["reduce_r_full"][start:stop],
            ),
            (
                "volume_rebuilt_reduce_r_vs_saved",
                (b_t - n_t + u) - active_inputs["reduce_r_volume"][start:stop],
            ),
        ):
            update_metric(metrics[key], values.real.astype(longdouble), values.imag.astype(longdouble), start)
        for key, value in (
            ("full_longdouble_recompose_vs_saved", wide_add(full_wide, wide(saved_full), -1)),
            ("volume_longdouble_recompose_vs_saved", wide_add(volume_wide, wide(saved_volume), -1)),
            ("full_longdouble_closure", full_wide),
            ("volume_longdouble_closure", volume_wide),
            (
                "full_float64_vs_longdouble_last_combination",
                wide_add(wide(full_float), full_wide, -1),
            ),
            (
                "volume_float64_vs_longdouble_last_combination",
                wide_add(wide(volume_float), volume_wide, -1),
            ),
        ):
            update_metric(metrics[key], value[0], value[1], start)

        if paired_inputs:
            paired_n = paired_inputs["native_volume_action"][original]
            paired_u = paired_inputs["T_r_i"][start:stop]
            paired_delta = paired_inputs["delta_t"][start:stop]
            paired_q = paired_inputs["attributed_terms"][start:stop]
            if any(
                not np.isfinite(value).all()
                for value in (paired_n, paired_u, paired_delta, paired_q)
            ):
                raise ValueError("V8 paired-state closure operands contain non-finite data")
            paired_n_wide = wide(paired_n)
            paired_u_wide = wide(paired_u)
            paired_right_wide = wide_add(wide(paired_delta), wide(paired_q))
            paired_r_full_wide = wide_add(wide_add(f_wide, paired_n_wide, -1), beta_wide, -1)
            paired_r_volume_wide = wide_add(b_wide, paired_n_wide, -1)
            paired_full_dhat = wide_add(
                wide_add(paired_right_wide, paired_r_full_wide, -1), paired_u_wide, -1
            )
            paired_volume_dhat = wide_add(
                wide_add(paired_right_wide, paired_r_volume_wide, -1), paired_u_wide, -1
            )
            update_metric(
                metrics["full_longdouble_dhat_j0_vs_j3"],
                full_dhat_wide[0] - paired_full_dhat[0],
                full_dhat_wide[1] - paired_full_dhat[1],
                start,
            )
            update_metric(
                metrics["volume_longdouble_dhat_j0_vs_j3"],
                volume_dhat_wide[0] - paired_volume_dhat[0],
                volume_dhat_wide[1] - paired_volume_dhat[1],
                start,
            )

    def finish(state: Mapping[str, Any]) -> dict[str, Any]:
        sum_squares = max(longdouble(0), state["sum_squares"])
        return {
            "absolute_l2": float(np.sqrt(sum_squares)),
            "max_abs": float(state["max_abs"]),
            "max_row": state["max_row"],
            "longdouble_mantissa_bits": int(np.finfo(np.longdouble).nmant),
            "longdouble_is_wider_than_float64": bool(
                np.finfo(np.longdouble).nmant > np.finfo(np.float64).nmant
            ),
            "chunk_size": int(chunk_size),
        }

    return {name: finish(value) for name, value in metrics.items()}


def _v8_replay_saved_operand_closures(
    donor: Mapping[str, Any],
    saved: Mapping[str, Any],
    *,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """Run the bounded P0 recompose over saved inputs for both columns/states."""

    v6_arrays = saved["v6_arrays"]
    v7_arrays = saved["v7_arrays"]
    v6_prefix = "task41_p0_v6_qmetric_candidate"
    rows = []
    for column_index, column in enumerate(donor["columns"]):
        if int(column.get("column", column_index)) != column_index:
            raise ValueError("V8 donor column ordering differs from the frozen two-column identity")
        active = np.asarray(column["active_original_rows"], dtype=np.int64)
        for state in ("j0", "j3"):
            state_record = next(
                (item for item in column["states"] if item.get("label") == state), None
            )
            if state_record is None:
                raise ValueError(f"V8 donor column {column_index} omits state {state}")
            names = {
                field: f"{v6_prefix}_attribution_col{column_index}_{state}_{field}"
                for field in ("T_r_i", "delta_t", "attributed_terms")
            }
            paired = None
            if state == "j0":
                paired_state = next(
                    item for item in column["states"] if item.get("label") == "j3"
                )
                paired = {
                    "native_volume_action": np.asarray(
                        paired_state["native_volume_action"], dtype=np.complex128
                    ),
                    **{
                        field: v6_arrays[
                            f"{v6_prefix}_attribution_col{column_index}_j3_{field}"
                        ]
                        for field in ("T_r_i", "delta_t", "attributed_terms")
                    },
                }
            result = _v8_recompose_saved_closure_inputs(
                active_original_rows=active,
                native_rhs=np.asarray(column["native_rhs"], dtype=np.complex128),
                native_volume_rhs=np.asarray(column["native_volume_rhs"], dtype=np.complex128),
                native_volume_action=np.asarray(
                    state_record["native_volume_action"], dtype=np.complex128
                ),
                b_alpha_rows=np.asarray(column["b_alpha_rows"], dtype=np.int64),
                b_alpha_values=np.asarray(column["b_alpha_values"], dtype=np.complex128),
                full_p6=v6_arrays[f"{v6_prefix}_full_p6"],
                full_reduced_rhs=v6_arrays[f"{v6_prefix}_full_reduced_rhs"],
                d_volume=v6_arrays[f"task41_v4_d_volume_trace_col{column_index}"],
                reduce_r_full=v6_arrays[
                    f"task41_v4_reduce_r_full_{state}_col{column_index}"
                ],
                reduce_r_volume=v6_arrays[
                    f"task41_v4_reduce_r_volume_{state}_col{column_index}"
                ],
                T_r_i=v6_arrays[names["T_r_i"]],
                delta_t=v6_arrays[names["delta_t"]],
                attributed_terms=v6_arrays[names["attributed_terms"]],
                saved_full_closure=v7_arrays[
                    f"task41_p0_v7_attribution_col{column_index}_{state}_corrected_full_closure"
                ],
                saved_volume_closure=v7_arrays[
                    f"task41_p0_v7_attribution_col{column_index}_{state}_corrected_volume_closure"
                ],
                column_index=column_index,
                paired_state_inputs=paired,
            )
            rows.append(
                {
                    "column": column_index,
                    "state": state,
                    "role_identity": {
                        "full_action": "V6 actual_qmetric candidate full_p6",
                        "full_reduced_rhs": "V6 actual_qmetric candidate full_reduced_rhs",
                        "volume_defect": "V6 saved V4 production d_volume_trace",
                        "T_r_i_delta_t_Q": "V6 saved actual-geometry attribution operands",
                        "saved_comparison": "V7 corrected full/volume closure",
                    },
                    "metrics": result,
                }
            )
            if progress_callback is not None:
                progress_callback(
                    {
                        "phase": "selected_trace_star_p0_saved_operand_recompose",
                        "status": "COLUMN_STATE_COMPLETED",
                        "column": column_index,
                        "state": state,
                        "wide_full_closure_l2": result["full_longdouble_closure"]["absolute_l2"],
                        "wide_volume_closure_l2": result["volume_longdouble_closure"]["absolute_l2"],
                        "wide_dhat_j0_vs_j3_l2": (
                            result["full_longdouble_dhat_j0_vs_j3"]["absolute_l2"]
                            if "full_longdouble_dhat_j0_vs_j3" in result
                            else None
                        ),
                    }
                )
    return {
        "schema": "task41.p0.v8.saved_operand_recomposition.v1",
        "selected_active_row": TASK41_P0_V8_SELECTED_ACTIVE_ROW,
        "source_artifacts": {
            "v6_index": saved["v6_index_path"],
            "v6_index_sha256": saved["v6_index_sha256"],
            "v6_report": saved["v6_report_path"],
            "v6_report_sha256": saved["v6_report_sha256"],
            "v7_index": saved["v7_index_path"],
            "v7_index_sha256": saved["v7_index_sha256"],
            "v7_report": saved["v7_report_path"],
            "v7_report_sha256": saved["v7_report_sha256"],
            "v6_arrays": saved["v6_artifacts"],
            "v7_arrays": saved["v7_artifacts"],
        },
        "prior_array_payload_bytes": saved["prior_array_payload_bytes"],
        "remaining_array_cap_bytes": saved["remaining_array_cap_bytes"],
        "wide_precision": {
            "implementation": "real_and_imaginary_numpy.longdouble_chunk_arithmetic",
            "mantissa_bits": int(np.finfo(np.longdouble).nmant),
            "wider_than_float64": bool(
                np.finfo(np.longdouble).nmant > np.finfo(np.float64).nmant
            ),
            "formal_complex128_outputs_modified": False,
        },
        "column_states": rows,
    }


def _v8_defect_matrices(
    K: np.ndarray,
    G: np.ndarray,
    J: np.ndarray,
    L: np.ndarray,
    R: np.ndarray,
    T: np.ndarray,
    S: np.ndarray,
    *,
    states: Mapping[str, tuple[np.ndarray, np.ndarray]] | None = None,
) -> dict[str, Any]:
    """Recompute the four stored-block defects and their exact identity residual."""

    K, G, J, L, R, T, S = tuple(
        np.asarray(value, dtype=np.complex128)
        for value in (K, G, J, L, R, T, S)
    )
    if (
        K.ndim != 2
        or G.ndim != 2
        or J.shape != (G.shape[1], K.shape[0])
        or L.shape != (G.shape[1], G.shape[1])
        or G.shape[0] != K.shape[0]
        or R.shape != G.shape
        or T.shape != J.shape
        or S.shape != L.shape
    ):
        raise ValueError("V8 K/G/J/L/R/T/S local block layouts are inconsistent")
    if any(not np.isfinite(value).all() for value in (K, G, J, L, R, T, S)):
        raise ValueError("V8 local block contains non-finite values")
    E_R = K @ R + G
    E_T = J + T @ K
    C_S = S - L - J @ R
    E_S = S - L - T @ G
    identity_rhs = C_S + E_T @ R - T @ E_R
    identity_residual = E_S - identity_rhs

    def metrics(value: np.ndarray) -> dict[str, float]:
        data = np.asarray(value, dtype=np.complex128)
        return {
            "frobenius": float(np.linalg.norm(data.ravel())),
            "max_abs": float(np.max(np.abs(data), initial=0.0)),
        }

    state_actions: dict[str, dict[str, np.ndarray]] = {}
    if states is not None:
        for label, (interior_state, trace_state) in states.items():
            u = np.asarray(interior_state, dtype=np.complex128)
            t = np.asarray(trace_state, dtype=np.complex128)
            if u.shape != (K.shape[0],) or t.shape != (G.shape[1],):
                raise ValueError(f"V8 local state {label!r} does not match its I/T block")
            if not np.isfinite(u).all() or not np.isfinite(t).all():
                raise ValueError(f"V8 local state {label!r} contains non-finite values")
            state_actions[str(label)] = {
                "E_R_t": E_R @ t,
                "E_T_u": E_T @ u,
                "C_S_t": C_S @ t,
                "E_S_t": E_S @ t,
                "E_S_identity_residual_t": identity_residual @ t,
            }
    return {
        "E_R": metrics(E_R),
        "E_T": metrics(E_T),
        "C_S": metrics(C_S),
        "E_S": metrics(E_S),
        "E_S_identity_rhs": metrics(identity_rhs),
        "E_S_identity_residual": metrics(identity_residual),
        "state_actions": state_actions,
    }


def _v8_wide_matvec_parts(
    matrix: np.ndarray,
    vector: tuple[np.ndarray, np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    """Multiply complex128 inputs using independent real/imaginary longdouble sums."""

    a = np.asarray(matrix, dtype=np.complex128)
    xr, xi = vector
    if a.ndim != 2 or xr.ndim != 1 or xi.shape != xr.shape or a.shape[1] != xr.size:
        raise ValueError("V8 wide matvec layouts differ")
    ar = a.real.astype(np.longdouble)
    ai = a.imag.astype(np.longdouble)
    xr = np.asarray(xr, dtype=np.longdouble)
    xi = np.asarray(xi, dtype=np.longdouble)
    return (
        np.sum(ar * xr[None, :] - ai * xi[None, :], axis=1, dtype=np.longdouble),
        np.sum(ar * xi[None, :] + ai * xr[None, :], axis=1, dtype=np.longdouble),
    )


def _v8_wide_matvec_difference_parts(
    left: np.ndarray,
    right: np.ndarray,
    vector: tuple[np.ndarray, np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    """Multiply (left-right) by a vector without rounding the matrix difference."""
    a = np.asarray(left, dtype=np.complex128)
    b = np.asarray(right, dtype=np.complex128)
    xr, xi = vector
    if (
        a.ndim != 2
        or b.shape != a.shape
        or xr.ndim != 1
        or xi.shape != xr.shape
        or a.shape[1] != xr.size
    ):
        raise ValueError("V8 wide matrix-difference matvec layouts differ")
    ar = a.real.astype(np.longdouble) - b.real.astype(np.longdouble)
    ai = a.imag.astype(np.longdouble) - b.imag.astype(np.longdouble)
    xr = np.asarray(xr, dtype=np.longdouble)
    xi = np.asarray(xi, dtype=np.longdouble)
    return (
        np.sum(ar * xr[None, :] - ai * xi[None, :], axis=1, dtype=np.longdouble),
        np.sum(ar * xi[None, :] + ai * xr[None, :], axis=1, dtype=np.longdouble),
    )


def _v8_wide_vdot_parts(
    left: np.ndarray,
    right: tuple[np.ndarray, np.ndarray],
    indices: np.ndarray | None = None,
) -> tuple[np.longdouble, np.longdouble]:
    w = np.asarray(left, dtype=np.complex128)
    rr, ri = right
    if indices is not None:
        index = np.asarray(indices, dtype=np.int64)
        w = w[index]
        rr, ri = np.asarray(rr)[index], np.asarray(ri)[index]
    if w.ndim != 1 or np.asarray(rr).shape != w.shape or np.asarray(ri).shape != w.shape:
        raise ValueError("V8 wide projection layouts differ")
    wr = w.real.astype(np.longdouble)
    wi = w.imag.astype(np.longdouble)
    rr = np.asarray(rr, dtype=np.longdouble)
    ri = np.asarray(ri, dtype=np.longdouble)
    return (
        np.sum(wr * rr + wi * ri, dtype=np.longdouble),
        np.sum(wr * ri - wi * rr, dtype=np.longdouble),
    )


def _v8_wide_add_parts(
    left: tuple[np.ndarray | np.longdouble, np.ndarray | np.longdouble],
    right: tuple[np.ndarray | np.longdouble, np.ndarray | np.longdouble],
    sign: int = 1,
) -> tuple[np.ndarray | np.longdouble, np.ndarray | np.longdouble]:
    return left[0] + sign * right[0], left[1] + sign * right[1]


def _v8_wide_scalar_json(value: tuple[np.longdouble, np.longdouble]) -> list[float]:
    return [float(value[0]), float(value[1])]


def _v8_vector_metrics(value: np.ndarray) -> dict[str, Any]:
    array = np.asarray(value, dtype=np.complex128).reshape(-1)
    if not np.isfinite(array).all():
        raise ValueError("V8 selected-cell vector contains non-finite values")
    magnitude = np.abs(array)
    index = int(np.argmax(magnitude)) if magnitude.size else None
    return {
        "length": int(array.size),
        "l2": float(np.linalg.norm(array)),
        "max_abs": float(magnitude[index]) if index is not None else 0.0,
        "max_index": index,
        "sum_real": float(np.sum(array.real, dtype=np.float64)),
        "sum_imag": float(np.sum(array.imag, dtype=np.float64)),
    }


def _v8_selected_row_vdot(
    weights: np.ndarray, vector: np.ndarray, selected_rows: np.ndarray
) -> complex:
    """Project one E-column support without pairing sparse and full vectors."""

    w = np.asarray(weights, dtype=np.complex128)
    x = np.asarray(vector, dtype=np.complex128)
    rows = np.asarray(selected_rows, dtype=np.int64)
    if (
        w.ndim != 1
        or x.shape != w.shape
        or rows.ndim != 1
        or (rows.size and (np.any(rows < 0) or np.any(rows >= w.size)))
        or (rows.size > 1 and np.any(rows[1:] <= rows[:-1]))
    ):
        raise ValueError("V8 selected-row projection has an invalid support layout")
    return complex(np.vdot(w[rows], x[rows]))


def _v8_ordered_cell_scalar_sum(
    cell_terms: Mapping[int, complex],
    cell_order: Iterable[int],
    *,
    initial: complex = 0.0 + 0.0j,
) -> complex:
    """Reproduce one deterministic complex128 cell accumulation order."""

    order = tuple(int(cell) for cell in cell_order)
    if len(order) != len(set(order)):
        raise ValueError("V8 selected-row accumulation order contains duplicate cells")
    result = complex(initial)
    for cell in order:
        if cell not in cell_terms:
            raise ValueError(f"V8 selected-row accumulation lacks cell {cell}")
        result += complex(cell_terms[cell])
    return result


def _v8_sum_selected_row_cell_terms(
    cell_contributions: Mapping[
        tuple[int, int, str, str], Mapping[str, Mapping[str, Any]]
    ],
    *,
    column_index: int,
    state_label: str,
    role: str,
    cell_order: Iterable[int],
    native_trace: complex,
) -> dict[str, Any]:
    """Sum actual selected-row contributions in one named cell order."""

    order = tuple(int(cell) for cell in cell_order)
    fields = ("s", "rhs_i", "T_r_i", "delta_t", "Q", "Q_regrouped")
    float_values: dict[str, complex] = {}
    wide_values: dict[str, tuple[np.longdouble, np.longdouble]] = {}
    native = complex(native_trace)
    for field in fields:
        float_terms: dict[int, complex] = {}
        wide_terms: dict[int, tuple[np.longdouble, np.longdouble]] = {}
        for cell in order:
            key = (cell, int(column_index), str(state_label), str(role))
            if key not in cell_contributions:
                raise ValueError(f"V8 ordered selected-row terms omit cell {cell}")
            term = cell_contributions[key]
            float_terms[cell] = complex(term["float"][field])
            pair = term["wide"][field]
            wide_terms[cell] = (np.longdouble(pair[0]), np.longdouble(pair[1]))
        initial_float = -native if field == "delta_t" else 0.0 + 0.0j
        float_value = _v8_ordered_cell_scalar_sum(
            float_terms, order, initial=initial_float
        )
        wide_value = (np.longdouble(0.0), np.longdouble(0.0))
        if field == "delta_t":
            wide_value = (-np.longdouble(native.real), -np.longdouble(native.imag))
        for cell in order:
            wide_value = _v8_wide_add_parts(wide_value, wide_terms[cell])
        float_values[field] = float_value
        wide_values[field] = (np.longdouble(wide_value[0]), np.longdouble(wide_value[1]))
    delta_t_cell_sum = _v8_ordered_cell_scalar_sum(
        {
            int(cell): complex(
                cell_contributions[
                    (int(cell), int(column_index), str(state_label), str(role))
                ]["float"]["delta_t"]
            )
            for cell in order
        },
        order,
    )
    return {
        "cell_order": list(order),
        "float64_complex128": float_values,
        "longdouble_real_imag": wide_values,
        "delta_t_sum_then_subtract_diagnostic": delta_t_cell_sum - native,
    }


def _v8_replay_selected_row_rhs_split(
    *,
    s_volume: complex,
    reduced_rhs_i: complex,
    native_volume_rhs_t: complex,
    native_full_rhs_t: complex,
    native_volume_action_t: complex,
    b_alpha_t: complex,
) -> dict[str, complex]:
    """Keep volume and full rows distinct, applying saved B-alpha exactly once."""

    s_volume = complex(s_volume)
    reduced_rhs_i = complex(reduced_rhs_i)
    native_volume_rhs_t = complex(native_volume_rhs_t)
    native_full_rhs_t = complex(native_full_rhs_t)
    native_volume_action_t = complex(native_volume_action_t)
    b_alpha_t = complex(b_alpha_t)
    s_full = s_volume + b_alpha_t
    g_volume = native_volume_rhs_t + reduced_rhs_i
    g_full = native_full_rhs_t + reduced_rhs_i
    d_volume = s_volume - g_volume
    d_full = s_full - g_full
    r_volume = native_volume_rhs_t - native_volume_action_t
    r_full = native_full_rhs_t - native_volume_action_t - b_alpha_t
    return {
        "s_volume": s_volume,
        "s_full": s_full,
        "g_volume": g_volume,
        "g_full": g_full,
        "d_volume": d_volume,
        "d_full": d_full,
        "r_volume": r_volume,
        "r_full": r_full,
    }


def _v8_validate_donor_state_pairing(
    donor: Mapping[str, Any], *, chunk_size: int = 131_072
) -> dict[str, Any]:
    """Check saved j0/j3 trace pairing, slave zeros and native action/residual identity."""

    columns = donor.get("columns")
    if not isinstance(columns, list) or len(columns) != 2:
        raise ValueError("V8 state-pair audit requires exactly two donor columns")
    column_results = []
    for column_index, column in enumerate(columns):
        active = np.asarray(column["active_original_rows"], dtype=np.int64)
        slaves = np.asarray(column["slave_rows"], dtype=np.int64)
        known = np.asarray(column["known_field"], dtype=np.complex128)
        native_rhs = np.asarray(column["native_rhs"], dtype=np.complex128)
        volume_rhs = np.asarray(column["native_volume_rhs"], dtype=np.complex128)
        if (
            active.ndim != 1
            or slaves.ndim != 1
            or slaves.dtype.kind not in "iu"
            or known.ndim != 1
            or native_rhs.shape != known.shape
            or volume_rhs.shape != known.shape
            or not np.isfinite(known).all()
            or not np.isfinite(native_rhs).all()
            or not np.isfinite(volume_rhs).all()
            or (slaves.size and (np.any(slaves < 0) or np.any(slaves >= known.size)))
        ):
            raise ValueError(f"V8 donor column {column_index} state-pair inputs are malformed")
        if slaves.size > 1 and np.any(slaves[1:] <= slaves[:-1]):
            raise ValueError(f"V8 donor column {column_index} slave rows are not strictly ordered")
        zero_counts = {"known_field": 0, "native_rhs": 0, "native_volume_rhs": 0}
        for start in range(0, slaves.size, chunk_size):
            rows = slaves[start : start + chunk_size]
            zero_counts["known_field"] += int(np.count_nonzero(known[rows] != 0.0))
            zero_counts["native_rhs"] += int(np.count_nonzero(native_rhs[rows] != 0.0))
            zero_counts["native_volume_rhs"] += int(np.count_nonzero(volume_rhs[rows] != 0.0))

        states = column.get("states")
        if not isinstance(states, list) or {item.get("label") for item in states} != {"j0", "j3"}:
            raise ValueError(f"V8 donor column {column_index} does not have paired j0/j3 states")
        by_label = {str(item["label"]): item for item in states}
        trace_difference_max = 0.0
        trace_difference_count = 0
        residual_metrics = {}
        for label in ("j0", "j3"):
            state = by_label[label]
            storage = np.asarray(state["storage"], dtype=np.complex128)
            action = np.asarray(state["native_volume_action"], dtype=np.complex128)
            residual = np.asarray(state["native_volume_residual"], dtype=np.complex128)
            if (
                storage.shape != known.shape
                or action.shape != known.shape
                or residual.shape != known.shape
                or not np.isfinite(storage).all()
                or not np.isfinite(action).all()
                or not np.isfinite(residual).all()
            ):
                raise ValueError(f"V8 donor column {column_index} {label} state layout is malformed")
            zero_counts[f"{label}_storage"] = 0
            for start in range(0, slaves.size, chunk_size):
                rows = slaves[start : start + chunk_size]
                zero_counts[f"{label}_storage"] += int(
                    np.count_nonzero(storage[rows] != 0.0)
                )
            residual_max = 0.0
            residual_mismatch_count = 0
            for start in range(0, action.size, chunk_size):
                stop = min(action.size, start + chunk_size)
                expected = volume_rhs[start:stop] - action[start:stop]
                difference = expected - residual[start:stop]
                residual_mismatch_count += int(np.count_nonzero(difference != 0.0))
                residual_max = max(
                    residual_max,
                    float(np.max(np.abs(difference), initial=0.0)),
                )
            residual_metrics[label] = {
                "status": "PASS" if residual_mismatch_count == 0 else "FAIL",
                "mismatch_count": residual_mismatch_count,
                "max_abs_difference": residual_max,
                "identity": "saved native_volume_residual == native_volume_rhs - saved native_volume_action",
            }
        state0 = np.asarray(by_label["j0"]["storage"], dtype=np.complex128)
        state3 = np.asarray(by_label["j3"]["storage"], dtype=np.complex128)
        for start in range(0, active.size, chunk_size):
            rows = active[start : start + chunk_size]
            difference = state0[rows] - state3[rows]
            trace_difference_count += int(np.count_nonzero(difference != 0.0))
            trace_difference_max = max(
                trace_difference_max,
                float(np.max(np.abs(difference), initial=0.0)),
            )
        column_results.append(
            {
                "column": column_index,
                "active_trace_rows": int(active.size),
                "slave_rows": int(slaves.size),
                "strict_slave_zero_counts": zero_counts,
                "j0_j3_active_trace": {
                    "status": "PASS" if trace_difference_count == 0 else "FAIL",
                    "mismatch_count": trace_difference_count,
                    "max_abs_difference": trace_difference_max,
                },
                "native_action_residual_pairing": residual_metrics,
                "state_local_inputs_are_role_paired": True,
            }
        )
    passed = all(
        not any(int(value) for value in row["strict_slave_zero_counts"].values())
        and row["j0_j3_active_trace"]["status"] == "PASS"
        and all(item["status"] == "PASS" for item in row["native_action_residual_pairing"].values())
        for row in column_results
    )
    return {
        "schema": "task41.p0.v8.donor_state_pairing.v1",
        "status": "PASS" if passed else "FAIL",
        "checks": [
            "known/native RHS and donor storage are exactly zero on saved MPC slave rows",
            "j0 and j3 share the exact saved independent active trace values",
            "saved native volume residual is exactly recomputed from paired action and RHS",
            "each P3 role consumes the same paired donor state and native vectors",
        ],
        "columns": column_results,
    }


def _v8_rebuild_selected_cell_role_artifacts(
    *,
    cell_index: int,
    row: Mapping[str, Any],
    combined_form: Any,
    kernels: dict[int, Any],
    element: Any,
    dimension: int,
    interior_positions: np.ndarray,
    trace_positions: np.ndarray,
    candidate_evaluator: Any,
    persist_array: Any,
    progress: Any,
) -> dict[str, dict[str, Any]]:
    """Run and persist both production-role local paths for one selected cell."""
    from src.solvers.hcurl_assembly_time_condensation import (
        _tabulate_volume_audit_path,
        condense_selected_volume_tensor,
    )

    coordinates = np.ascontiguousarray(
        row["actual_geometry_coordinates"], dtype=np.float64
    )
    role_sets: dict[str, dict[str, Any]] = {}
    for role, raw_evaluator in (
        ("candidate", candidate_evaluator),
        ("reference", None),
    ):
        progress(
            {
                "phase": "selected_trace_star_local_tensor",
                "status": "STARTED",
                "cell_index": int(cell_index),
                "role": role,
                "source": "RECONSTRUCTED_SELECTED_CELL",
            }
        )
        path = _tabulate_volume_audit_path(
            combined_form,
            kernels,
            element,
            coordinates,
            tag=int(row["cell_tag"]),
            permutation=int(row["cell_permutation"]),
            dimension=dimension,
            interior_positions=interior_positions,
            trace_positions=trace_positions,
            raw_tensor_evaluator=raw_evaluator,
        )
        oriented = np.asarray(path["oriented_tensor"], dtype=np.complex128)
        condensed = condense_selected_volume_tensor(
            oriented,
            interior_positions,
            trace_positions,
        )
        role_sets[role] = {
            "source": "RECONSTRUCTED_SELECTED_CELL",
            "raw_tensor": np.asarray(path["raw_tensor"], dtype=np.complex128),
            "oriented_tensor": oriented,
            "rts": {
                name: np.asarray(condensed[name], dtype=np.complex128)
                for name in ("R", "T", "S")
            },
            "lu": np.asarray(condensed["interior_lu"], dtype=np.complex128),
            "pivots": np.asarray(condensed["interior_lu_pivots"], dtype=np.int32),
            "strict_lu_residual": float(condensed["strict_lu_residual"]),
            "raw_tensor_evaluator_identity": (
                candidate_evaluator.identity if role == "candidate" else None
            ),
        }
        artifact_prefix = f"task41_p0_v8_selected_cell{cell_index}_{role}"
        artifacts = {
            "raw_tensor": {
                "name": f"{artifact_prefix}_raw_tensor",
                **persist_array(
                    f"{artifact_prefix}_raw_tensor", role_sets[role]["raw_tensor"]
                ),
            },
            "oriented_tensor": {
                "name": f"{artifact_prefix}_oriented_tensor",
                **persist_array(
                    f"{artifact_prefix}_oriented_tensor", oriented
                ),
            },
        }
        for name, value in role_sets[role]["rts"].items():
            artifacts[name] = {
                "name": f"{artifact_prefix}_{name}",
                **persist_array(f"{artifact_prefix}_{name}", value),
            }
        artifacts["interior_lu"] = {
            "name": f"{artifact_prefix}_interior_lu",
            **persist_array(
                f"{artifact_prefix}_interior_lu", role_sets[role]["lu"]
            ),
        }
        artifacts["interior_lu_pivots"] = {
            "name": f"{artifact_prefix}_interior_lu_pivots",
            **persist_array(
                f"{artifact_prefix}_interior_lu_pivots", role_sets[role]["pivots"]
            ),
        }
        role_sets[role]["artifacts"] = artifacts
        progress(
            {
                "phase": "selected_trace_star_local_tensor",
                "status": "COMPLETED",
                "cell_index": int(cell_index),
                "role": role,
                "strict_lu_residual": role_sets[role]["strict_lu_residual"],
                "source": "RECONSTRUCTED_SELECTED_CELL",
            }
        )
    return role_sets


def _run_v8_selected_trace_star_audit(
    *,
    cfg: Any,
    donor: dict[str, Any],
    fixed_window: Any,
    output_directory: Path,
    consumer_contract: Mapping[str, Any],
    ffcx_c_source_path: Path | None,
    sha256_file: Any,
    allocation_gate: Any,
    persist_array: Any,
    progress: Any,
    checkpoint: Any,
) -> dict[str, Any]:
    """Replay saved B0 operands and only the V8 target row's complete cell star."""

    import ufl
    from basix.ufl import element
    from dolfinx import default_real_type, fem
    from mpi4py import MPI
    from scipy import sparse

    from src.solvers.common_3d_forms import _build_physical_volume_terms
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
    from src.solvers.hcurl_assembly_time_condensation import (
        _cell_integral_kernels,
        _orient_cell_tensor,
        build_selected_volume_trace_star_metadata,
    )
    from src.solvers.task41_actual_qmetric_blocked_gram import (
        IDENTITY as V6_CANDIDATE_IDENTITY,
        Task41ActualQMetricBlockedGramCandidate,
    )

    if fixed_window.sha256 != consumer_contract.get("window", {}).get("sha256"):
        raise ValueError("V8 selected-star fixed-window hash differs from the consumer contract")
    if ffcx_c_source_path is None:
        raise ValueError("V8 selected-star audit requires the frozen actual-qmetric C source")

    # Pair the original donor states before releasing fields that establish
    # trace, slave-row, and native-action/residual identity.
    donor_state_pairing = _v8_validate_donor_state_pairing(donor)
    checkpoint("selected_trace_star_donor_state_pairing", donor_state_pairing)
    if donor_state_pairing.get("status") != "PASS":
        raise ValueError("V8 saved donor state-pairing checks did not pass")

    # Drop V4-only class and global-operator arrays before mapping the narrow V8 inputs.
    for column in donor["columns"]:
        for key in list(column):
            if key not in {
                "active_original_rows",
                "native_rhs",
                "native_volume_rhs",
                "b_alpha_rows",
                "b_alpha_values",
                "states",
            }:
                del column[key]
        for state in column["states"]:
            for key in list(state):
                if key not in {"label", "storage", "native_volume_action"}:
                    del state[key]
    donor.pop("raw_classes", None)
    donor.pop("cell_maps", None)
    donor.pop("attribution", None)

    allocation_gate(
        "v8_selected_trace_star_saved_inputs_preflight",
        {
            "additional_payload_bytes": 0,
            "workspace_bytes": 4 * 1024**3,
            "estimated_remaining_seconds_upper": 0.0,
            "termination_reserve_seconds": TASK41_P0_V5_TERMINATION_RESERVE_SECONDS,
            "selected_work_scope": "saved-array verification and chunked original-operand recomposition",
        },
    )
    results_root = (
        ROOT / "results" / str(consumer_contract["case"]["model_id"])
    ).resolve(strict=True)
    saved = _v8_load_saved_operand_arrays(
        results_root=results_root,
        fixed_window_sha256=fixed_window.sha256,
        donor_existing_evidence_bytes=int(donor["existing_evidence_bytes"]),
        sha256_file=sha256_file,
    )
    v6_arrays = saved["v6_arrays"]
    v7_arrays = saved["v7_arrays"]
    v6_report = saved["v6_report"]
    prefix_qualification = v6_report.get("candidate_prefix_qualification")
    prefix_records_raw = (
        prefix_qualification.get("records")
        if isinstance(prefix_qualification, Mapping)
        else None
    )
    if not isinstance(prefix_records_raw, list) or len(prefix_records_raw) != 8:
        raise ValueError("V8 V6 source report does not bind all eight actual-qmetric prefix cells")
    prefix_records = {
        int(item["cell_index"]): item
        for item in prefix_records_raw
        if isinstance(item, Mapping) and type(item.get("cell_index")) is int
    }
    if set(prefix_records) != set(TASK41_P0_V6_PREFIX_CELLS):
        raise ValueError("V8 V6 prefix record cell identities differ from the frozen eight-cell order")
    if len(donor["columns"]) != 2:
        raise ValueError("V8 saved donor does not contain the two frozen input columns")
    active_original_rows = np.asarray(
        donor["columns"][0]["active_original_rows"], dtype=np.int64
    )
    if not np.array_equal(
        active_original_rows,
        np.asarray(donor["columns"][1]["active_original_rows"], dtype=np.int64),
    ):
        raise ValueError("V8 donor columns disagree on the saved active-original row map")
    selected_row = TASK41_P0_V8_SELECTED_ACTIVE_ROW
    if not 0 <= selected_row < active_original_rows.size:
        raise IndexError("V8 selected active row lies outside the saved donor map")
    selected_original_row = int(active_original_rows[selected_row])

    progress(
        {
            "phase": "selected_trace_star_saved_operand_recomposition",
            "status": "STARTED",
            "selected_active_row": selected_row,
            "selected_original_row": selected_original_row,
            "input_scope": "hash-bound V6/V7 arrays; donor j0/j3 operands; mmap for large arrays",
        }
    )
    saved_operand_replay = _v8_replay_saved_operand_closures(
        donor,
        saved,
        progress_callback=progress,
    )

    allocation_gate(
        "v8_selected_trace_star_mesh_metadata_preflight",
        {
            "additional_payload_bytes": 0,
            "workspace_bytes": 6 * 1024**3,
            "estimated_remaining_seconds_upper": TASK41_P0_V5_PREFIX_MINIMUM_SECONDS,
            "termination_reserve_seconds": TASK41_P0_V5_TERMINATION_RESERVE_SECONDS,
            "metadata_scope": "one p6/MPC row-numbering scan over the existing 28,000-cell mesh; no tensor, owner, or carrier",
        },
    )
    progress(
        {
            "phase": "selected_trace_star_mesh_metadata",
            "status": "STARTED",
            "degree": 6,
            "selected_active_row": selected_row,
            "selected_original_row": selected_original_row,
            "witness_cells": list(TASK41_P0_V6_PREFIX_CELLS),
        }
    )
    levels = _build_same_mesh_levels(
        cfg,
        MPI.COMM_SELF,
        (6,),
        include_positive_coefficients=False,
    )
    space = levels["spaces"][6]
    floquet = levels["floquets"][6]
    metadata = build_selected_volume_trace_star_metadata(
        space,
        floquet.mpc,
        levels["mesh_data"].cell_tags,
        selected_active_row=selected_row,
        expected_active_original_rows=active_original_rows,
        witness_cell_indices=TASK41_P0_V6_PREFIX_CELLS,
        progress_callback=progress,
    )
    if int(metadata["selected_original_row"]) != selected_original_row:
        raise ValueError("V8 fresh metadata does not resolve the selected original storage row")
    incidents = list(metadata["incidents"])
    incident_order = [int(item["cell_index"]) for item in incidents]
    if not incident_order or incident_order != sorted(set(incident_order)):
        raise ValueError("V8 selected-row incident cell list is empty, duplicated, or not in production order")
    witness_cells = metadata["witness_cells"]
    if set(map(int, witness_cells)) != set(TASK41_P0_V6_PREFIX_CELLS):
        raise ValueError("V8 fresh metadata omitted one of the V6 prefix map witnesses")
    interior_positions = np.asarray(metadata["interior_positions"], dtype=np.int64)
    trace_positions = np.asarray(metadata["trace_positions"], dtype=np.int64)
    dimension = int(metadata["element_dimension"])
    if dimension != int(space.element.space_dimension):
        raise ValueError("V8 selected-star metadata and p6 element dimensions differ")

    # Cross-check the V4 maps carried by the V6 index wherever those maps exist.
    saved_map_checks = []
    for cell_index in TASK41_P0_V5_REFERENCE_CELLS:
        fresh = witness_cells[cell_index]
        prefix = f"task41_v4_volume_cell_{cell_index}"
        map_fields = (
            ("interior_original_rows", "interior_original_rows"),
            ("trace_original_rows", "trace_original_rows"),
            ("active_ids", "active_ids"),
            ("trace_expansion_data", "trace_expansion_data"),
            ("trace_expansion_indices", "trace_expansion_indices"),
            ("trace_expansion_indptr", "trace_expansion_indptr"),
        )
        field_results = {}
        for field, fresh_name in map_fields:
            equal = np.array_equal(
                np.asarray(fresh[fresh_name]),
                np.asarray(v6_arrays[f"{prefix}_{field}"]),
            )
            field_results[field] = bool(equal)
            if not equal:
                raise ValueError(
                    f"V8 fresh p6/MPC map differs from the frozen V6 cell{cell_index} map at {field}"
                )
        saved_map_checks.append(
            {
                "cell_index": int(cell_index),
                "fields_bitwise_equal": field_results,
                "status": "PASS",
            }
        )

    # Precompute the exact local array payload before any selected numerical work.
    metadata_fields = (
        "geometry_dofs",
        "actual_geometry_coordinates",
        "local_dofs",
        "original_rows",
        "interior_positions",
        "trace_positions",
        "interior_original_rows",
        "trace_original_rows",
        "active_ids",
        "trace_expansion_data",
        "trace_expansion_indices",
        "trace_expansion_indptr",
        "selected_local_trace_rows",
        "selected_trace_coefficients",
    )
    metadata_cells: dict[int, dict[str, Any]] = {
        int(item["cell_index"]): item for item in incidents
    }
    metadata_cells.update(
        {int(cell): item for cell, item in witness_cells.items()}
    )
    estimated_array_payload = 0

    def reserve_shape(shape: tuple[int, ...], dtype: Any) -> None:
        nonlocal estimated_array_payload
        estimated_array_payload += int(math.prod(shape) * np.dtype(dtype).itemsize) + 4096

    for row in metadata_cells.values():
        for key in metadata_fields:
            array = np.asarray(row[key])
            reserve_shape(tuple(array.shape), array.dtype)
    missing_numeric_cells = sorted(
        set(incident_order) - set(TASK41_P0_V6_PREFIX_CELLS)
    )
    interior_count = int(interior_positions.size)
    trace_count = int(trace_positions.size)
    for _cell_index in missing_numeric_cells:
        for _role in ("candidate", "reference"):
            reserve_shape((dimension, dimension), np.complex128)  # raw tensor
            reserve_shape((dimension, dimension), np.complex128)  # oriented tensor
            reserve_shape((interior_count, trace_count), np.complex128)  # R
            reserve_shape((trace_count, interior_count), np.complex128)  # T
            reserve_shape((trace_count, trace_count), np.complex128)  # S
            reserve_shape((interior_count, interior_count), np.complex128)  # strict LU
            reserve_shape((interior_count,), np.int32)  # pivots
    p3_artifact_fields = (
        "u_i",
        "t_c",
        "b_i",
        "n_i",
        "K_u",
        "G_t",
        "actual_i",
        "delta_i",
        "J_u",
        "L_t",
        "actual_t",
        "S_action",
        "local_reduced_rhs",
        "T_r_i",
        "T_delta_i",
        "E_S_t",
        "minus_E_T_u",
        "Q_local",
        "Q_regrouped_local",
        "projected_actual_trace",
        "projected_T_r_i",
        "projected_Q",
        "projected_Q_regrouped",
    )
    for row in incidents:
        ni = int(np.asarray(row["interior_positions"]).size)
        nt = int(np.asarray(row["trace_positions"]).size)
        na = int(np.asarray(row["active_ids"]).size)
        for column in range(2):
            for state in ("j0", "j3"):
                for field in ("u_i", "t_c", "b_i", "n_i"):
                    reserve_shape(
                        (ni if field in {"u_i", "b_i", "n_i"} else nt,),
                        np.complex128,
                    )
                for _role in ("candidate", "reference"):
                    for field in p3_artifact_fields[4:]:
                        reserve_shape(
                            (na if field.startswith("projected_") else ni if field in {"K_u", "G_t", "actual_i", "delta_i"} else nt,),
                            np.complex128,
                        )
    prefix_action_fields = (
        "E_R_t",
        "E_T_u",
        "C_S_t",
        "E_S_t",
        "E_S_identity_residual_t",
    )
    for _cell_index in TASK41_P0_V6_PREFIX_CELLS:
        for _column in range(2):
            for _state in ("j0", "j3"):
                for _role in ("candidate", "reference"):
                    for field in prefix_action_fields:
                        reserve_shape(
                            (interior_count if field == "E_R_t" else trace_count,),
                            np.complex128,
                        )
        if _cell_index in TASK41_P0_V5_REFERENCE_CELLS:
            for _column in range(2):
                for _state in ("j0", "j3"):
                    for _role in ("candidate", "reference"):
                        reserve_shape((dimension,), np.complex128)

    allocation_gate(
        "v8_selected_trace_star_local_numeric_preflight",
        {
            "additional_payload_bytes": estimated_array_payload,
            "evidence_reserve_bytes": estimated_array_payload,
            "workspace_bytes": 3 * 1024**3,
            "scratch_reserve_bytes": 128 * 1024**2,
            "estimated_remaining_seconds_upper": (
                TASK41_P0_V5_PREFIX_MINIMUM_SECONDS
                + len(missing_numeric_cells)
                * max(
                    float(item.get("candidate_build_seconds", 0.0))
                    + float(
                        item.get("original_kernel_oracle_timing", {}).get(
                            "compiler_seconds", 0.0
                        )
                    )
                    + float(
                        item.get("original_kernel_oracle_timing", {}).get(
                            "kernel_call_seconds", 0.0
                        )
                    )
                    for item in prefix_records.values()
                )
                * 2.0
            ),
            "incident_cells": incident_order,
            "missing_selected_numeric_cells": missing_numeric_cells,
            "v6_prefix_cells_reused": list(TASK41_P0_V6_PREFIX_CELLS),
            "matrix_scope": "selected cells only; no global owner or full-key cache",
        },
    )
    run_record_metadata = {
        "schema": "task41.p0.v8.selected_trace_star_metadata.v1",
        "selected_active_row": selected_row,
        "selected_original_row": selected_original_row,
        "active_trace_rows": int(metadata["active_trace_rows"]),
        "full_trace_rows": int(metadata["full_trace_rows"]),
        "slave_rows": int(metadata["slave_rows"]),
        "full_storage_rows": int(metadata["full_storage_rows"]),
        "owned_cells_scanned": int(metadata["owned_cells"]),
        "incident_cell_count": len(incidents),
        "incident_cell_order": incident_order,
        "observer_v6_prefix_order": list(TASK41_P0_V6_PREFIX_CELLS),
        "saved_v6_map_checks": saved_map_checks,
        "cell_artifacts": {},
        "selected_cells": [],
    }
    checkpoint(
        "selected_trace_star_evidence_reserve",
        {
            "schema": "task41.p0.v8.selected_trace_star_evidence_reserve.v1",
            "array_payload_upper_bytes": int(estimated_array_payload),
            "incident_cells": incident_order,
            "missing_selected_numeric_cells": missing_numeric_cells,
        "prefix_defect_state_actions": len(TASK41_P0_V6_PREFIX_CELLS) * 2 * 2 * 2,
        },
    )
    for cell_index, row in sorted(metadata_cells.items()):
        artifacts = {}
        for field in metadata_fields:
            name = f"task41_p0_v8_metadata_cell{cell_index}_{field}"
            artifacts[field] = {"name": name, **persist_array(name, np.asarray(row[field]))}
        run_record_metadata["cell_artifacts"][str(cell_index)] = {
            "cell_index": int(cell_index),
            "cell_tag": int(row["cell_tag"]),
            "cell_permutation": int(row["cell_permutation"]),
            "actual_coordinate_sha256": row["actual_coordinate_sha256"],
            "is_incident": cell_index in set(incident_order),
            "selected_trace_contribution_kinds": list(
                row["selected_trace_contribution_kinds"]
            ),
            "arrays": artifacts,
        }
    run_record_metadata["selected_cells"] = [
        {
            "cell_index": int(row["cell_index"]),
            "cell_tag": int(row["cell_tag"]),
            "cell_permutation": int(row["cell_permutation"]),
            "actual_coordinate_sha256": row["actual_coordinate_sha256"],
            "selected_local_trace_rows": np.asarray(
                row["selected_local_trace_rows"], dtype=np.int64
            ).tolist(),
            "selected_trace_coefficients": [
                [float(value.real), float(value.imag)]
                for value in np.asarray(row["selected_trace_coefficients"], dtype=np.complex128)
            ],
            "selected_trace_contribution_kinds": list(
                row["selected_trace_contribution_kinds"]
            ),
        }
        for row in incidents
    ]
    checkpoint("selected_trace_star_metadata", run_record_metadata)
    progress(
        {
            "phase": "selected_trace_star_mesh_metadata",
            "status": "COMPLETED",
            "selected_active_row": selected_row,
            "selected_original_row": selected_original_row,
            "owned_cells_scanned": int(metadata["owned_cells"]),
            "incident_cells": incident_order,
        }
    )

    # Compile just the existing combined volume form after all selected-cell gates pass.
    progress({"phase": "selected_trace_star_form_compile", "status": "STARTED"})
    mesh_data = levels["mesh_data"]
    trial, test = ufl.TrialFunction(space), ufl.TestFunction(space)
    dx = ufl.Measure("dx", domain=levels["mesh"], subdomain_data=mesh_data.cell_tags)
    curl_form, mass_form = _build_physical_volume_terms(cfg, trial, test, dx)
    combined_form = fem.form(
        curl_form + mass_form,
        jit_options=dict(SAME_MESH_JIT_OPTIONS),
    )
    kernels = _cell_integral_kernels(combined_form, sum_duplicate_cell_integrals=True)
    evaluator = Task41ActualQMetricBlockedGramCandidate(
        space.element.basix_element,
        curl_form + mass_form,
        combined_form,
        c_source_path=ffcx_c_source_path,
        scratch_directory=output_directory / "actual_qmetric_scratch",
    )
    if evaluator.identity != V6_CANDIDATE_IDENTITY:
        raise ValueError("V8 selected-cell evaluator identity differs from frozen V6")
    evaluator.validate_compiled_form(combined_form, kernels)
    evaluator.prepare()
    compiled_identity = _compiled_kernel_identity(
        combined_form,
        rank=2,
        label="selected_trace_star_combined_curl_plus_mass",
        sha256_file=sha256_file,
    )
    progress(
        {
            "phase": "selected_trace_star_form_compile",
            "status": "COMPLETED",
            "ffcx_kernel_identity": compiled_identity,
            "candidate_identity": evaluator.identity,
            "candidate_cache_identity": evaluator.cache_identity,
            "candidate_prepare_seconds": float(evaluator.preparation_seconds),
        }
    )

    # Reuse V6's eight saved tensor/RTS sets; reconstruct only missing selected cells.
    cell_numeric: dict[int, dict[str, Any]] = {}
    for cell_index in sorted(set(TASK41_P0_V6_PREFIX_CELLS) | set(incident_order)):
        row = metadata_cells.get(cell_index)
        if row is None:
            raise ValueError(f"V8 selected-star map omits cell {cell_index}")
        role_sets: dict[str, dict[str, Any]] = {}
        if cell_index in TASK41_P0_V6_PREFIX_CELLS:
            record = prefix_records[cell_index]
            if (
                int(record.get("tag", -1)) != int(row["cell_tag"])
                or int(record.get("permutation", -1)) != int(row["cell_permutation"])
                or record.get("coordinates_sha256") != row["actual_coordinate_sha256"]
            ):
                raise ValueError(f"V8 fresh metadata identity differs from V6 prefix cell {cell_index}")
            prefix = f"task41_v6_prefix_cell{cell_index}"
            saved_coordinates = np.asarray(v6_arrays[f"{prefix}_candidate_coordinates"])
            if not np.array_equal(saved_coordinates, row["actual_geometry_coordinates"]):
                raise ValueError(f"V8 actual coordinates differ from V6 prefix cell {cell_index}")
            for role in ("candidate", "reference"):
                raw = np.asarray(v6_arrays[f"{prefix}_{role}_raw_tensor"], dtype=np.complex128)
                oriented = np.asarray(
                    v6_arrays[f"{prefix}_{role}_oriented_tensor"], dtype=np.complex128
                )
                reconstructed_orientation = raw.copy()
                _orient_cell_tensor(
                    space.element,
                    reconstructed_orientation,
                    np.asarray([row["cell_permutation"]], dtype=np.uint32),
                )
                if not np.array_equal(reconstructed_orientation, oriented):
                    raise ValueError(
                        f"V8 V6 raw/oriented tensor identity differs for {role} cell {cell_index}"
                    )
                rts = {
                    name: np.asarray(v6_arrays[f"{prefix}_{role}_{name}"], dtype=np.complex128)
                    for name in ("R", "T", "S")
                }
                role_sets[role] = {
                    "source": "REUSED_HASH_BOUND_V6_PREFIX",
                    "raw_tensor": raw,
                    "oriented_tensor": oriented,
                    "rts": rts,
                    "strict_lu": record.get("comparisons", {}).get("strict_lu", {}).get(role),
                    "v6_prefix_record": record,
                }
        else:
            role_sets = _v8_rebuild_selected_cell_role_artifacts(
                cell_index=cell_index,
                row=row,
                combined_form=combined_form,
                kernels=kernels,
                element=space.element,
                dimension=dimension,
                interior_positions=interior_positions,
                trace_positions=trace_positions,
                candidate_evaluator=evaluator,
                persist_array=persist_array,
                progress=progress,
            )
        cell_numeric[cell_index] = {"row": row, "roles": role_sets}

    def expansion_for(row: Mapping[str, Any]) -> Any:
        return sparse.csr_matrix(
            (
                np.asarray(row["trace_expansion_data"], dtype=np.complex128),
                np.asarray(row["trace_expansion_indices"], dtype=np.int32),
                np.asarray(row["trace_expansion_indptr"], dtype=np.int32),
            ),
            shape=(len(trace_positions), len(np.asarray(row["active_ids"]))),
        )

    def local_state_vectors(
        row: Mapping[str, Any], column_index: int, state_label: str
    ) -> dict[str, np.ndarray]:
        column = donor["columns"][column_index]
        state = next(item for item in column["states"] if item["label"] == state_label)
        storage = np.asarray(state["storage"], dtype=np.complex128)
        original_rows = np.asarray(row["original_rows"], dtype=np.int64)
        active_ids = np.asarray(row["active_ids"], dtype=np.int64)
        expansion = expansion_for(row)
        trace_values = np.asarray(
            storage[np.asarray(column["active_original_rows"], dtype=np.int64)[active_ids]],
            dtype=np.complex128,
        )
        return {
            "u_i": np.asarray(storage[original_rows[interior_positions]], dtype=np.complex128),
            "t_c": np.asarray(expansion @ trace_values, dtype=np.complex128).reshape(-1),
            "local_full": np.asarray(storage[original_rows], dtype=np.complex128),
            "native_action": np.asarray(state["native_volume_action"], dtype=np.complex128),
        }

    # P0: recompute the four matrix defects for each frozen V6 prefix role.
    p0_rows = []
    progress(
        {
            "phase": "selected_trace_star_p0_defect_replay",
            "status": "STARTED",
            "cell_order": list(TASK41_P0_V6_PREFIX_CELLS),
        }
    )
    for cell_index in TASK41_P0_V6_PREFIX_CELLS:
        cell_entry = cell_numeric[cell_index]
        row = witness_cells[cell_index]
        role_rows = []
        interior = np.asarray(row["interior_positions"], dtype=np.int64)
        trace = np.asarray(row["trace_positions"], dtype=np.int64)
        for role in ("candidate", "reference"):
            role_data = cell_entry["roles"][role]
            tensor = np.asarray(role_data["oriented_tensor"], dtype=np.complex128)
            blocks = {
                "K": tensor[np.ix_(interior, interior)],
                "G": tensor[np.ix_(interior, trace)],
                "J": tensor[np.ix_(trace, interior)],
                "L": tensor[np.ix_(trace, trace)],
            }
            p0_states: dict[str, tuple[np.ndarray, np.ndarray]] = {}
            state_map: dict[tuple[int, str], dict[str, np.ndarray]] = {}
            for column_index in range(2):
                for state_label in ("j0", "j3"):
                    vectors = local_state_vectors(row, column_index, state_label)
                    p0_states[f"col{column_index}_{state_label}"] = (
                        vectors["u_i"],
                        vectors["t_c"],
                    )
                    state_map[(column_index, state_label)] = vectors
            defects = _v8_defect_matrices(
                blocks["K"],
                blocks["G"],
                blocks["J"],
                blocks["L"],
                role_data["rts"]["R"],
                role_data["rts"]["T"],
                role_data["rts"]["S"],
                states=p0_states,
            )
            p0_state_artifacts = {}
            for (column_index, state_label), state_vectors in state_map.items():
                state_key = f"col{column_index}_{state_label}"
                action_fields = defects["state_actions"][state_key]
                action_artifacts = {}
                for field in prefix_action_fields:
                    name = (
                        f"task41_p0_v8_prefix_cell{cell_index}_{role}_"
                        f"col{column_index}_{state_label}_defect_{field}"
                    )
                    action = np.asarray(action_fields[field], dtype=np.complex128)
                    action_artifacts[field] = {
                        "name": name,
                        **persist_array(name, action),
                        "metrics": _v8_vector_metrics(action),
                    }

                if cell_index in TASK41_P0_V5_REFERENCE_CELLS:
                    local_action = tensor @ state_vectors["local_full"]
                    saved_name = (
                        f"task41_v6_prefix_cell{cell_index}_col{column_index}_"
                        f"{state_label}_{role}_local_action"
                    )
                    saved_action = np.asarray(v6_arrays[saved_name], dtype=np.complex128)
                    difference = local_action - saved_action
                    difference_name = (
                        f"task41_p0_v8_prefix_cell{cell_index}_col{column_index}_"
                        f"{state_label}_{role}_local_action_difference"
                    )
                    difference_artifact = {
                        "name": difference_name,
                        **persist_array(difference_name, difference),
                    }
                    action_artifacts["v6_saved_local_action_difference"] = {
                        "source_array": saved["v6_artifacts"][saved_name],
                        "difference_artifact": difference_artifact,
                        "metrics": _v6_screen_metrics(local_action, saved_action),
                        "signed_difference_sum": [
                            float(np.sum(difference.real)),
                            float(np.sum(difference.imag)),
                        ],
                    }
                p0_state_artifacts[state_key] = {
                    "u_i_metrics": _v8_vector_metrics(state_vectors["u_i"]),
                    "t_c_metrics": _v8_vector_metrics(state_vectors["t_c"]),
                    "defect_action_artifacts": action_artifacts,
                }
            role_rows.append(
                {
                    "role": role,
                    "source": role_data["source"],
                    "tensor_identity": {
                        "raw_sha256": saved["v6_artifacts"].get(
                            f"task41_v6_prefix_cell{cell_index}_{role}_raw_tensor", {}
                        ).get("sha256"),
                        "oriented_sha256": saved["v6_artifacts"].get(
                            f"task41_v6_prefix_cell{cell_index}_{role}_oriented_tensor", {}
                        ).get("sha256"),
                    },
                    "stored_strict_lu": role_data.get("strict_lu"),
                    "four_defects": {
                        key: defects[key]
                        for key in (
                            "E_R",
                            "E_T",
                            "C_S",
                            "E_S",
                            "E_S_identity_rhs",
                            "E_S_identity_residual",
                        )
                    },
                    "state_actions": p0_state_artifacts,
                }
            )
        p0_rows.append(
            {
                "cell_index": int(cell_index),
                "tag": int(row["cell_tag"]),
                "permutation": int(row["cell_permutation"]),
                "actual_coordinate_sha256": row["actual_coordinate_sha256"],
                "roles": role_rows,
            }
        )
        progress(
            {
                "phase": "selected_trace_star_p0_defect_replay",
                "status": "CELL_COMPLETED",
                "cell_index": int(cell_index),
            }
        )
    progress(
        {
            "phase": "selected_trace_star_p0_defect_replay",
            "status": "COMPLETED",
            "cell_count": len(p0_rows),
        }
    )

    def complex_pair(value: complex) -> list[float]:
        return [float(complex(value).real), float(complex(value).imag)]

    def parts(value: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        data = np.asarray(value, dtype=np.complex128)
        return data.real.astype(np.longdouble), data.imag.astype(np.longdouble)

    def row_scalar(weights: np.ndarray, vector: np.ndarray, rows: np.ndarray) -> complex:
        return _v8_selected_row_vdot(weights, vector, rows)

    def row_wide_scalar(
        weights: np.ndarray,
        vector_parts: tuple[np.ndarray, np.ndarray],
        rows: np.ndarray,
    ) -> tuple[np.longdouble, np.longdouble]:
        return _v8_wide_vdot_parts(weights, vector_parts, rows)

    row_accumulators: dict[tuple[int, str, str], dict[str, Any]] = {}
    p3_cell_contributions: dict[
        tuple[int, int, str, str], dict[str, Any]
    ] = {}
    p3_es_trace_state_differences: dict[tuple[int, int, str], dict[str, Any]] = {}
    p3_es_trace_j0: dict[tuple[int, int, str], np.ndarray] = {}
    p3_cell_rows = []
    progress(
        {
            "phase": "selected_trace_star_p3_production_row_replay",
            "status": "STARTED",
            "columns": 2,
            "states": ["j0", "j3"],
            "role_order": ["candidate", "reference"],
            "cell_sum_order": incident_order,
        }
    )
    for cell_index in incident_order:
        row = metadata_cells[cell_index]
        expansion = expansion_for(row)
        active_ids = np.asarray(row["active_ids"], dtype=np.int64)
        selected_active_locations = np.flatnonzero(active_ids == selected_row)
        if selected_active_locations.size != 1:
            raise ValueError(
                f"selected trace row {selected_row} is absent or duplicated in cell {cell_index} E map"
            )
        selected_active_location = int(selected_active_locations[0])
        selected_local_rows = np.asarray(row["selected_local_trace_rows"], dtype=np.int64)
        weights = np.zeros(len(trace_positions), dtype=np.complex128)
        weights[selected_local_rows] = np.asarray(
            row["selected_trace_coefficients"], dtype=np.complex128
        )
        if not np.any(weights != 0.0):
            raise ValueError(f"cell {cell_index} selected-row E column has empty support")
        original_rows = np.asarray(row["original_rows"], dtype=np.int64)
        interior_rows = np.asarray(row["interior_original_rows"], dtype=np.int64)
        trace_positions_cell = np.asarray(row["trace_positions"], dtype=np.int64)
        cell_state_records = []
        for column_index in range(2):
            column = donor["columns"][column_index]
            native_rhs = np.asarray(column["native_rhs"], dtype=np.complex128)
            volume_rhs = np.asarray(column["native_volume_rhs"], dtype=np.complex128)
            if not np.array_equal(native_rhs[interior_rows], volume_rhs[interior_rows]):
                raise ValueError(
                    f"V8 full and volume native RHS differ on cell {cell_index} interior rows"
                )
            for state_label in ("j0", "j3"):
                state_vectors = local_state_vectors(row, column_index, state_label)
                storage_inputs = {
                    "u_i": state_vectors["u_i"],
                    "t_c": state_vectors["t_c"],
                    "b_i": np.asarray(volume_rhs[interior_rows], dtype=np.complex128),
                    "n_i": np.asarray(
                        state_vectors["native_action"][interior_rows], dtype=np.complex128
                    ),
                }
                input_artifacts = {}
                for field, values in storage_inputs.items():
                    name = (
                        f"task41_p0_v8_selected_cell{cell_index}_col{column_index}_"
                        f"{state_label}_input_{field}"
                    )
                    input_artifacts[field] = {
                        "name": name,
                        **persist_array(name, values),
                        "metrics": _v8_vector_metrics(values),
                    }

                state_role_rows = []
                for role in ("candidate", "reference"):
                    role_data = cell_numeric[cell_index]["roles"][role]
                    tensor = np.asarray(role_data["oriented_tensor"], dtype=np.complex128)
                    K = tensor[np.ix_(interior_positions, interior_positions)]
                    G = tensor[np.ix_(interior_positions, trace_positions_cell)]
                    J = tensor[np.ix_(trace_positions_cell, interior_positions)]
                    L = tensor[np.ix_(trace_positions_cell, trace_positions_cell)]
                    R = np.asarray(role_data["rts"]["R"], dtype=np.complex128)
                    T = np.asarray(role_data["rts"]["T"], dtype=np.complex128)
                    S = np.asarray(role_data["rts"]["S"], dtype=np.complex128)
                    u_i, t_c = storage_inputs["u_i"], storage_inputs["t_c"]
                    b_i, n_i = storage_inputs["b_i"], storage_inputs["n_i"]

                    K_u = K @ u_i
                    G_t = G @ t_c
                    actual_i = K_u + G_t
                    delta_i = actual_i - n_i
                    J_u = J @ u_i
                    L_t = L @ t_c
                    actual_t = J_u + L_t
                    local_reduced_rhs = T @ b_i
                    T_r_i = T @ (b_i - n_i)
                    T_delta_i = T @ delta_i
                    E_S_t = S @ t_c - L_t - T @ G_t
                    E_T_u = J_u + T @ K_u
                    minus_E_T_u = -E_T_u
                    Q_local = T_delta_i + E_S_t - E_T_u
                    Q_regrouped_local = (S - L) @ t_c - J @ u_i - T @ n_i
                    projected_actual_trace = np.asarray(
                        expansion.conj().T @ actual_t, dtype=np.complex128
                    ).reshape(-1)
                    projected_T_r_i = np.asarray(
                        expansion.conj().T @ T_r_i, dtype=np.complex128
                    ).reshape(-1)
                    projected_Q = np.asarray(
                        expansion.conj().T @ Q_local, dtype=np.complex128
                    ).reshape(-1)
                    projected_Q_regrouped = np.asarray(
                        expansion.conj().T @ Q_regrouped_local, dtype=np.complex128
                    ).reshape(-1)
                    role_vectors = {
                        "K_u": K_u,
                        "G_t": G_t,
                        "actual_i": actual_i,
                        "delta_i": delta_i,
                        "J_u": J_u,
                        "L_t": L_t,
                        "actual_t": actual_t,
                        "S_action": S @ t_c,
                        "local_reduced_rhs": local_reduced_rhs,
                        "T_r_i": T_r_i,
                        "T_delta_i": T_delta_i,
                        "E_S_t": E_S_t,
                        "minus_E_T_u": minus_E_T_u,
                        "Q_local": Q_local,
                        "Q_regrouped_local": Q_regrouped_local,
                        "projected_actual_trace": projected_actual_trace,
                        "projected_T_r_i": projected_T_r_i,
                        "projected_Q": projected_Q,
                        "projected_Q_regrouped": projected_Q_regrouped,
                    }
                    es_pair_key = (cell_index, column_index, role)
                    if state_label == "j0":
                        p3_es_trace_j0[es_pair_key] = np.asarray(E_S_t).copy()
                    else:
                        if es_pair_key not in p3_es_trace_j0:
                            raise ValueError(
                                f"V8 P3 state j3 has no paired j0 E_S action for cell {cell_index}"
                            )
                        previous_es = p3_es_trace_j0.pop(es_pair_key)
                        es_difference = np.asarray(E_S_t) - previous_es
                        p3_es_trace_state_differences[es_pair_key] = {
                            "bitwise_equal": bool(np.array_equal(E_S_t, previous_es)),
                            "difference_metrics": _v8_vector_metrics(es_difference),
                        }
                    role_artifacts = {}
                    for field, values in role_vectors.items():
                        name = (
                            f"task41_p0_v8_selected_cell{cell_index}_col{column_index}_"
                            f"{state_label}_{role}_{field}"
                        )
                        role_artifacts[field] = {
                            "name": name,
                            **persist_array(name, np.asarray(values, dtype=np.complex128)),
                            "metrics": _v8_vector_metrics(values),
                        }

                    native_action = state_vectors["native_action"]
                    native_t = complex(native_action[selected_original_row])
                    native_volume_t = complex(volume_rhs[selected_original_row])
                    native_full_t = complex(native_rhs[selected_original_row])
                    beta_rows = np.asarray(column["b_alpha_rows"], dtype=np.int64)
                    beta_values = np.asarray(column["b_alpha_values"], dtype=np.complex128)
                    beta_selected = beta_values[beta_rows == selected_original_row]
                    if beta_selected.size > 1:
                        raise ValueError("V8 selected-row B-alpha contribution is duplicated")
                    beta_value = complex(beta_selected[0]) if beta_selected.size else 0.0 + 0.0j

                    accumulator_key = (column_index, state_label, role)
                    accumulator = row_accumulators.setdefault(
                        accumulator_key,
                        {
                            "s": 0.0 + 0.0j,
                            "rhs_i": 0.0 + 0.0j,
                            "T_r_i": 0.0 + 0.0j,
                            "delta_t": -native_t,
                            "Q": 0.0 + 0.0j,
                            "Q_regrouped": 0.0 + 0.0j,
                            "wide_s": (np.longdouble(0.0), np.longdouble(0.0)),
                            "wide_rhs_i": (np.longdouble(0.0), np.longdouble(0.0)),
                            "wide_T_r_i": (np.longdouble(0.0), np.longdouble(0.0)),
                            "wide_delta_t": (
                                -np.longdouble(native_t.real),
                                -np.longdouble(native_t.imag),
                            ),
                            "wide_Q": (np.longdouble(0.0), np.longdouble(0.0)),
                            "wide_Q_regrouped": (np.longdouble(0.0), np.longdouble(0.0)),
                            "native_volume_t": native_volume_t,
                            "native_full_t": native_full_t,
                            "native_t": native_t,
                            "beta_selected": beta_value,
                        },
                    )
                    accumulator["s"] += row_scalar(weights, role_vectors["S_action"], selected_local_rows)
                    accumulator["rhs_i"] += row_scalar(
                        weights, local_reduced_rhs, selected_local_rows
                    )
                    accumulator["T_r_i"] += row_scalar(
                        weights, T_r_i, selected_local_rows
                    )
                    accumulator["delta_t"] += row_scalar(
                        weights, actual_t, selected_local_rows
                    )
                    accumulator["Q"] += row_scalar(weights, Q_local, selected_local_rows)
                    accumulator["Q_regrouped"] += row_scalar(
                        weights, Q_regrouped_local, selected_local_rows
                    )

                    # Re-evaluate products and projections with separate longdouble real/imaginary sums.
                    u_w, t_w, b_w, n_w = map(parts, (u_i, t_c, b_i, n_i))
                    w_Ku = _v8_wide_matvec_parts(K, u_w)
                    w_Gt = _v8_wide_matvec_parts(G, t_w)
                    w_Ju = _v8_wide_matvec_parts(J, u_w)
                    w_Lt = _v8_wide_matvec_parts(L, t_w)
                    w_S_t = _v8_wide_matvec_parts(S, t_w)
                    w_local_rhs = _v8_wide_matvec_parts(T, b_w)
                    w_r_i = _v8_wide_add_parts(b_w, n_w, -1)
                    w_T_r_i = _v8_wide_matvec_parts(T, w_r_i)
                    w_delta_i = _v8_wide_add_parts(
                        _v8_wide_add_parts(w_Ku, w_Gt), n_w, -1
                    )
                    w_T_delta = _v8_wide_matvec_parts(T, w_delta_i)
                    w_T_Gt = _v8_wide_matvec_parts(T, w_Gt)
                    w_T_Ku = _v8_wide_matvec_parts(T, w_Ku)
                    w_E_S_t = _v8_wide_add_parts(
                        _v8_wide_add_parts(w_S_t, w_Lt, -1), w_T_Gt, -1
                    )
                    w_E_T_u = _v8_wide_add_parts(w_Ju, w_T_Ku)
                    w_Q = _v8_wide_add_parts(
                        _v8_wide_add_parts(w_T_delta, w_E_S_t), w_E_T_u, -1
                    )
                    w_S_minus_L_t = _v8_wide_matvec_difference_parts(
                        S, L, t_w
                    )
                    w_Q_regrouped = _v8_wide_add_parts(
                        _v8_wide_add_parts(w_S_minus_L_t, w_Ju, -1),
                        _v8_wide_matvec_parts(T, n_w),
                        -1,
                    )
                    w_actual_t = _v8_wide_add_parts(w_Ju, w_Lt)
                    float_terms = {
                        "s": row_scalar(weights, role_vectors["S_action"], selected_local_rows),
                        "rhs_i": row_scalar(weights, local_reduced_rhs, selected_local_rows),
                        "T_r_i": row_scalar(weights, T_r_i, selected_local_rows),
                        "delta_t": row_scalar(weights, actual_t, selected_local_rows),
                        "Q": row_scalar(weights, Q_local, selected_local_rows),
                        "Q_regrouped": row_scalar(
                            weights, Q_regrouped_local, selected_local_rows
                        ),
                    }
                    wide_terms = {
                        "s": row_wide_scalar(weights, w_S_t, selected_local_rows),
                        "rhs_i": row_wide_scalar(
                            weights, w_local_rhs, selected_local_rows
                        ),
                        "T_r_i": row_wide_scalar(
                            weights, w_T_r_i, selected_local_rows
                        ),
                        "delta_t": row_wide_scalar(
                            weights, w_actual_t, selected_local_rows
                        ),
                        "Q": row_wide_scalar(weights, w_Q, selected_local_rows),
                        "Q_regrouped": row_wide_scalar(
                            weights, w_Q_regrouped, selected_local_rows
                        ),
                    }
                    p3_cell_contributions[
                        (cell_index, column_index, state_label, role)
                    ] = {"float": float_terms, "wide": wide_terms}
                    accumulator["wide_s"] = _v8_wide_add_parts(
                        accumulator["wide_s"],
                        wide_terms["s"],
                    )
                    accumulator["wide_rhs_i"] = _v8_wide_add_parts(
                        accumulator["wide_rhs_i"],
                        wide_terms["rhs_i"],
                    )
                    accumulator["wide_T_r_i"] = _v8_wide_add_parts(
                        accumulator["wide_T_r_i"],
                        wide_terms["T_r_i"],
                    )
                    accumulator["wide_delta_t"] = _v8_wide_add_parts(
                        accumulator["wide_delta_t"],
                        wide_terms["delta_t"],
                    )
                    accumulator["wide_Q"] = _v8_wide_add_parts(
                        accumulator["wide_Q"],
                        wide_terms["Q"],
                    )
                    accumulator["wide_Q_regrouped"] = _v8_wide_add_parts(
                        accumulator["wide_Q_regrouped"],
                        wide_terms["Q_regrouped"],
                    )

                    wide_q_difference = _v8_wide_add_parts(w_Q, w_Q_regrouped, -1)
                    q_float_parts = parts(Q_local)
                    q_float_wide_error = _v8_wide_add_parts(
                        (
                            q_float_parts[0][selected_local_rows].astype(np.longdouble),
                            q_float_parts[1][selected_local_rows].astype(np.longdouble),
                        ),
                        (
                            np.asarray(w_Q[0])[selected_local_rows],
                            np.asarray(w_Q[1])[selected_local_rows],
                        ),
                        -1,
                    )
                    wide_q_max = float(
                        np.max(
                            np.sqrt(
                                np.asarray(wide_q_difference[0]) ** 2
                                + np.asarray(wide_q_difference[1]) ** 2
                            ),
                            initial=np.longdouble(0.0),
                        )
                    )
                    wide_q_float_max = float(
                        np.max(
                            np.sqrt(
                                np.asarray(q_float_wide_error[0]) ** 2
                                + np.asarray(q_float_wide_error[1]) ** 2
                            ),
                            initial=np.longdouble(0.0),
                        )
                    )

                    row_cell_artifacts = {}
                    for field, values in (
                        ("u_i", u_i),
                        ("t_c", t_c),
                        ("b_i", b_i),
                        ("n_i", n_i),
                    ):
                        row_cell_artifacts[field] = input_artifacts[field]
                    state_role_rows.append(
                        {
                            "role": role,
                            "source": role_data["source"],
                            "local_values": row_cell_artifacts,
                            "signed_action_artifacts": role_artifacts,
                            "selected_row_contributions": {
                                "S_action": complex_pair(float_terms["s"]),
                                "local_reduced_rhs_T_b_i": complex_pair(float_terms["rhs_i"]),
                                "T_r_i": complex_pair(float_terms["T_r_i"]),
                                "delta_t_cell": complex_pair(float_terms["delta_t"]),
                                "Q_cell": complex_pair(float_terms["Q"]),
                                "Q_regrouped_cell": complex_pair(float_terms["Q_regrouped"]),
                                "projected_actual_trace": complex_pair(
                                    projected_actual_trace[selected_active_location]
                                ),
                                "projected_Q": complex_pair(
                                    projected_Q[selected_active_location]
                                ),
                                "projected_Q_regrouped": complex_pair(
                                    projected_Q_regrouped[selected_active_location]
                                ),
                            },
                            "wide_selected_row_contributions": {
                                field: _v8_wide_scalar_json(value)
                                for field, value in wide_terms.items()
                            },
                            "local_Q_regrouping": {
                                "float64_signed_difference_artifact": role_artifacts[
                                    "Q_regrouped_local"
                                ],
                                "wide_max_abs_Q_vs_regrouped_Q": wide_q_max,
                                "wide_max_abs_Q_vs_float64_Q": wide_q_float_max,
                            },
                        }
                    )
                cell_state_records.append(
                    {
                        "column": int(column_index),
                        "state": state_label,
                        "native_full_rhs_at_selected_original_row": complex_pair(
                            native_rhs[selected_original_row]
                        ),
                        "native_volume_rhs_at_selected_original_row": complex_pair(
                            volume_rhs[selected_original_row]
                        ),
                        "native_volume_action_at_selected_original_row": complex_pair(
                            state_vectors["native_action"][selected_original_row]
                        ),
                        "B_alpha_selected_row_applied_once": complex_pair(
                            beta_values[beta_rows == selected_original_row].sum()
                        ),
                        "roles": state_role_rows,
                    }
                )
        p3_cell_rows.append(
            {
                "cell_index": int(cell_index),
                "roles_and_states": cell_state_records,
            }
        )
        progress(
            {
                "phase": "selected_trace_star_p3_production_row_replay",
                "status": "CELL_COMPLETED",
                "cell_index": int(cell_index),
                "incident_cells_completed": len(p3_cell_rows),
                "incident_cell_count": len(incident_order),
            }
        )

    if p3_es_trace_j0:
        raise ValueError("V8 P3 left unpaired j0 E_S actions")
    if not set(incident_order).issubset(cell_numeric):
        raise ValueError("V8 selected-star numeric cells do not cover every incident cell")
    if any(
        set(cell_numeric[cell]["roles"]) != {"candidate", "reference"}
        for cell in incident_order
    ):
        raise ValueError("V8 selected-star numeric block is incomplete for an incident cell")

    incident_set = set(incident_order)
    # A non-incident V6 prefix cell has an exactly zero selected-row E column.
    # Include that zero so the observer sequence still begins with all eight keys.
    ordered_contributions = dict(p3_cell_contributions)
    for cell_index in TASK41_P0_V6_PREFIX_CELLS:
        if cell_index in incident_set:
            continue
        for column_index in range(2):
            for state_label in ("j0", "j3"):
                for role in ("candidate", "reference"):
                    ordered_contributions[(cell_index, column_index, state_label, role)] = {
                        "float": {
                            field: 0.0 + 0.0j
                            for field in ("s", "rhs_i", "T_r_i", "delta_t", "Q", "Q_regrouped")
                        },
                        "wide": {
                            field: (np.longdouble(0.0), np.longdouble(0.0))
                            for field in ("s", "rhs_i", "T_r_i", "delta_t", "Q", "Q_regrouped")
                        },
                    }
    v6_prefix_observer_order = [
        *[int(cell) for cell in TASK41_P0_V6_PREFIX_CELLS],
        *[int(cell) for cell in incident_order if cell not in set(TASK41_P0_V6_PREFIX_CELLS)],
    ]
    cell_orders = {
        "production_original_cell_order": incident_order,
        "v6_eight_key_prefix_observer_order": v6_prefix_observer_order,
    }

    def wide_complex(value: complex) -> tuple[np.longdouble, np.longdouble]:
        number = complex(value)
        return np.longdouble(number.real), np.longdouble(number.imag)

    def wide_pair_add(
        left: tuple[np.longdouble, np.longdouble],
        right: tuple[np.longdouble, np.longdouble],
        sign: int = 1,
    ) -> tuple[np.longdouble, np.longdouble]:
        return (
            np.longdouble(left[0] + sign * right[0]),
            np.longdouble(left[1] + sign * right[1]),
        )

    def wide_pair_subtract_complex(
        left: tuple[np.longdouble, np.longdouble], right: complex
    ) -> tuple[np.longdouble, np.longdouble]:
        return wide_pair_add(left, wide_complex(right), -1)

    p3_order_rows: dict[str, list[dict[str, Any]]] = {}
    p3_order_values: dict[tuple[str, int, str, str], dict[str, Any]] = {}
    for order_name, order in cell_orders.items():
        order_rows = []
        for column_index in range(2):
            column = donor["columns"][column_index]
            for state_label in ("j0", "j3"):
                for role in ("candidate", "reference"):
                    accumulator = row_accumulators[(column_index, state_label, role)]
                    totals = _v8_sum_selected_row_cell_terms(
                        ordered_contributions,
                        column_index=column_index,
                        state_label=state_label,
                        role=role,
                        cell_order=order,
                        native_trace=accumulator["native_t"],
                    )
                    float_terms = totals["float64_complex128"]
                    wide_terms = totals["longdouble_real_imag"]
                    if order_name == "production_original_cell_order":
                        for field in ("s", "rhs_i", "T_r_i", "delta_t", "Q", "Q_regrouped"):
                            if float_terms[field] != complex(accumulator[field]):
                                raise ValueError(
                                    f"V8 P3 production {field} sum changed while materializing its report"
                                )
                        for field, accumulator_field in (
                            ("s", "wide_s"),
                            ("rhs_i", "wide_rhs_i"),
                            ("T_r_i", "wide_T_r_i"),
                            ("delta_t", "wide_delta_t"),
                            ("Q", "wide_Q"),
                            ("Q_regrouped", "wide_Q_regrouped"),
                        ):
                            if wide_terms[field] != accumulator[accumulator_field]:
                                raise ValueError(
                                    f"V8 P3 production wide {field} sum changed while materializing its report"
                                )

                    native_volume_t = complex(accumulator["native_volume_t"])
                    native_full_t = complex(accumulator["native_full_t"])
                    native_t = complex(accumulator["native_t"])
                    beta_value = complex(accumulator["beta_selected"])
                    rhs_replay = _v8_replay_selected_row_rhs_split(
                        s_volume=float_terms["s"],
                        reduced_rhs_i=float_terms["rhs_i"],
                        native_volume_rhs_t=native_volume_t,
                        native_full_rhs_t=native_full_t,
                        native_volume_action_t=native_t,
                        b_alpha_t=beta_value,
                    )
                    g_volume = rhs_replay["g_volume"]
                    g_full = rhs_replay["g_full"]
                    d_volume_star = rhs_replay["d_volume"]
                    s_full = rhs_replay["s_full"]
                    d_full_star = rhs_replay["d_full"]
                    r_volume = rhs_replay["r_volume"]
                    r_full = rhs_replay["r_full"]
                    d_volume_saved = complex(
                        v6_arrays[f"task41_v4_d_volume_trace_col{column_index}"][selected_row]
                    )
                    full_p6_saved = complex(
                        v6_arrays["task41_p0_v6_qmetric_candidate_full_p6"][
                            selected_row, column_index
                        ]
                    )
                    full_reduced_rhs_saved = complex(
                        v6_arrays["task41_p0_v6_qmetric_candidate_full_reduced_rhs"][
                            selected_row, column_index
                        ]
                    )
                    d_full_saved = full_p6_saved - full_reduced_rhs_saved
                    left_volume = d_volume_saved + r_volume + float_terms["T_r_i"]
                    left_full = d_full_saved + r_full + float_terms["T_r_i"]
                    right_attribution = float_terms["delta_t"] + float_terms["Q"]
                    closure_volume = left_volume - right_attribution
                    closure_full = left_full - right_attribution
                    d_hat_volume = (
                        float_terms["delta_t"]
                        + float_terms["Q"]
                        - r_volume
                        - float_terms["T_r_i"]
                    )
                    d_hat_full = (
                        float_terms["delta_t"]
                        + float_terms["Q"]
                        - r_full
                        - float_terms["T_r_i"]
                    )

                    wide_g_volume = wide_pair_add(
                        wide_complex(native_volume_t), wide_terms["rhs_i"]
                    )
                    wide_g_full = wide_pair_add(
                        wide_complex(native_full_t), wide_terms["rhs_i"]
                    )
                    wide_s_full = wide_pair_add(wide_terms["s"], wide_complex(beta_value))
                    wide_d_volume_star = wide_pair_add(
                        wide_terms["s"], wide_g_volume, -1
                    )
                    wide_d_full_star = wide_pair_add(wide_s_full, wide_g_full, -1)
                    wide_r_volume = wide_pair_subtract_complex(
                        wide_complex(native_volume_t), native_t
                    )
                    wide_r_full = wide_pair_subtract_complex(
                        wide_pair_subtract_complex(wide_complex(native_full_t), native_t),
                        beta_value,
                    )
                    wide_d_volume_saved = wide_complex(d_volume_saved)
                    wide_d_full_saved = wide_complex(d_full_saved)
                    wide_closure_volume = wide_pair_add(
                        wide_pair_add(
                            wide_pair_add(wide_d_volume_saved, wide_r_volume),
                            wide_terms["T_r_i"],
                        ),
                        wide_pair_add(wide_terms["delta_t"], wide_terms["Q"]),
                        -1,
                    )
                    wide_closure_full = wide_pair_add(
                        wide_pair_add(
                            wide_pair_add(wide_d_full_saved, wide_r_full),
                            wide_terms["T_r_i"],
                        ),
                        wide_pair_add(wide_terms["delta_t"], wide_terms["Q"]),
                        -1,
                    )
                    wide_d_hat_volume = wide_pair_add(
                        wide_pair_add(wide_terms["delta_t"], wide_terms["Q"]),
                        wide_pair_add(wide_r_volume, wide_terms["T_r_i"]),
                        -1,
                    )
                    wide_d_hat_full = wide_pair_add(
                        wide_pair_add(wide_terms["delta_t"], wide_terms["Q"]),
                        wide_pair_add(wide_r_full, wide_terms["T_r_i"]),
                        -1,
                    )

                    saved_attribution = None
                    saved_closures = None
                    if role == "candidate":
                        v6_prefix = f"task41_p0_v6_qmetric_candidate_attribution_col{column_index}_{state_label}_"
                        saved_attribution = {
                            field: complex(v6_arrays[f"{v6_prefix}{field}"][selected_row])
                            for field in ("T_r_i", "delta_t", "attributed_terms")
                        }
                        v7_prefix = f"task41_p0_v7_attribution_col{column_index}_{state_label}_corrected_"
                        saved_closures = {
                            "full": complex(
                                v7_arrays[f"{v7_prefix}full_closure"][selected_row]
                            ),
                            "volume": complex(
                                v7_arrays[f"{v7_prefix}volume_closure"][selected_row]
                            ),
                        }

                    order_row = {
                        "column": column_index,
                        "state": state_label,
                        "role": role,
                        "sources_by_incident_cell": {
                            str(cell): cell_numeric[cell]["roles"][role]["source"]
                            for cell in incident_order
                        },
                        "selected_row_rhs_and_action": {
                            "native_volume_rhs_b_t": complex_pair(native_volume_t),
                            "native_full_rhs_f_t": complex_pair(native_full_t),
                            "native_volume_action_n_t": complex_pair(native_t),
                            "B_alpha_selected_row_applied_once": complex_pair(beta_value),
                            "full_rhs_split_rule": "use saved native_rhs once; subtract sparse B_alpha once in r_full; never remultiply phase or E^H",
                        },
                        "production_row_replay": {
                            "s_r_volume_sum_wH_S_t": complex_pair(float_terms["s"]),
                            "s_r_full_volume_plus_B_alpha_once": complex_pair(s_full),
                            "g_volume_r_b_t_plus_sum_wH_T_b_i": complex_pair(g_volume),
                            "d_volume_star_s_minus_g_volume": complex_pair(d_volume_star),
                            "g_full_r_f_t_plus_sum_wH_T_b_i": complex_pair(g_full),
                            "d_full_star_s_plus_B_alpha_minus_g_full": complex_pair(d_full_star),
                            "sum_wH_T_r_i": complex_pair(float_terms["T_r_i"]),
                            "delta_t_sum_then_subtract_diagnostic": complex_pair(
                                totals["delta_t_sum_then_subtract_diagnostic"]
                            ),
                            "delta_t_original_order_starts_at_minus_native_action": complex_pair(
                                float_terms["delta_t"]
                            ),
                            "Q_sum_wH_attributed_terms": complex_pair(float_terms["Q"]),
                            "Q_regrouped_sum": complex_pair(float_terms["Q_regrouped"]),
                            "Q_minus_regrouped_signed_difference": complex_pair(
                                float_terms["Q"] - float_terms["Q_regrouped"]
                            ),
                            "v7_grouped_left_volume": complex_pair(left_volume),
                            "v7_grouped_left_full": complex_pair(left_full),
                        },
                        "wide_real_imag_diagnostic": {
                            "implementation": "independent numpy.longdouble real/imag products and additions",
                            "mantissa_bits": int(np.finfo(np.longdouble).nmant),
                            "wider_than_float64": bool(
                                np.finfo(np.longdouble).nmant > np.finfo(np.float64).nmant
                            ),
                            "s_volume": _v8_wide_scalar_json(wide_terms["s"]),
                            "s_full_plus_B_alpha_once": _v8_wide_scalar_json(wide_s_full),
                            "g_volume": _v8_wide_scalar_json(wide_g_volume),
                            "d_volume_star": _v8_wide_scalar_json(wide_d_volume_star),
                            "g_full": _v8_wide_scalar_json(wide_g_full),
                            "d_full_star": _v8_wide_scalar_json(wide_d_full_star),
                            "T_r_i": _v8_wide_scalar_json(wide_terms["T_r_i"]),
                            "delta_t": _v8_wide_scalar_json(wide_terms["delta_t"]),
                            "Q": _v8_wide_scalar_json(wide_terms["Q"]),
                            "Q_regrouped": _v8_wide_scalar_json(wide_terms["Q_regrouped"]),
                            "v7_grouped_left_volume": _v8_wide_scalar_json(
                                wide_pair_add(
                                    wide_pair_add(wide_d_volume_saved, wide_r_volume),
                                    wide_terms["T_r_i"],
                                )
                            ),
                            "v7_grouped_left_full": _v8_wide_scalar_json(
                                wide_pair_add(
                                    wide_pair_add(wide_d_full_saved, wide_r_full),
                                    wide_terms["T_r_i"],
                                )
                            ),
                            "closure_volume_from_saved_d_volume": _v8_wide_scalar_json(
                                wide_closure_volume
                            ),
                            "closure_full_from_saved_d_full": _v8_wide_scalar_json(
                                wide_closure_full
                            ),
                            "d_hat_volume": _v8_wide_scalar_json(wide_d_hat_volume),
                            "d_hat_full": _v8_wide_scalar_json(wide_d_hat_full),
                        },
                        "saved_v6_v7_row_comparisons": (
                            None
                            if role != "candidate"
                            else {
                                "V6_s_full_p6": complex_pair(full_p6_saved),
                                "V6_g_full_reduced_rhs": complex_pair(full_reduced_rhs_saved),
                                "V6_d_full_s_minus_g": complex_pair(d_full_saved),
                                "V6_d_volume": complex_pair(d_volume_saved),
                                "star_s_full_minus_V6_full_p6": complex_pair(
                                    s_full - full_p6_saved
                                ),
                                "star_g_full_minus_V6_full_reduced_rhs": complex_pair(
                                    g_full - full_reduced_rhs_saved
                                ),
                                "star_d_volume_minus_V6_d_volume": complex_pair(
                                    d_volume_star - d_volume_saved
                                ),
                                "star_d_full_minus_V6_d_full": complex_pair(
                                    d_full_star - d_full_saved
                                ),
                                "V6_delta_t": complex_pair(saved_attribution["delta_t"]),
                                "V6_T_r_i": complex_pair(saved_attribution["T_r_i"]),
                                "V6_attributed_terms_Q": complex_pair(
                                    saved_attribution["attributed_terms"]
                                ),
                                "star_delta_t_minus_V6": complex_pair(
                                    float_terms["delta_t"] - saved_attribution["delta_t"]
                                ),
                                "star_T_r_i_minus_V6": complex_pair(
                                    float_terms["T_r_i"] - saved_attribution["T_r_i"]
                                ),
                                "star_Q_minus_V6": complex_pair(
                                    float_terms["Q"] - saved_attribution["attributed_terms"]
                                ),
                                "star_corrected_full_closure": complex_pair(closure_full),
                                "star_corrected_volume_closure": complex_pair(closure_volume),
                                "V7_corrected_full_closure": complex_pair(saved_closures["full"]),
                                "V7_corrected_volume_closure": complex_pair(saved_closures["volume"]),
                                "recomposed_full_closure_minus_V7": complex_pair(
                                    closure_full - saved_closures["full"]
                                ),
                                "recomposed_volume_closure_minus_V7": complex_pair(
                                    closure_volume - saved_closures["volume"]
                                ),
                                "wide_closure_volume_minus_V7": _v8_wide_scalar_json(
                                    wide_pair_subtract_complex(
                                        wide_closure_volume, saved_closures["volume"]
                                    )
                                ),
                                "wide_closure_full_minus_V7": _v8_wide_scalar_json(
                                    wide_pair_subtract_complex(
                                        wide_closure_full, saved_closures["full"]
                                    )
                                ),
                            }
                        ),
                    }
                    order_rows.append(order_row)
                    p3_order_values[(order_name, column_index, state_label, role)] = {
                        "d_hat_volume": d_hat_volume,
                        "d_hat_full": d_hat_full,
                        "wide_d_hat_volume": wide_d_hat_volume,
                        "wide_d_hat_full": wide_d_hat_full,
                    }
        p3_order_rows[order_name] = order_rows

    p3_state_invariance = []
    for order_name in cell_orders:
        for column_index in range(2):
            for role in ("candidate", "reference"):
                j0 = p3_order_values[(order_name, column_index, "j0", role)]
                j3 = p3_order_values[(order_name, column_index, "j3", role)]
                p3_state_invariance.append(
                    {
                        "cell_order": order_name,
                        "column": column_index,
                        "role": role,
                        "float64_j0_minus_j3_d_hat_volume": complex_pair(
                            j0["d_hat_volume"] - j3["d_hat_volume"]
                        ),
                        "float64_j0_minus_j3_d_hat_full": complex_pair(
                            j0["d_hat_full"] - j3["d_hat_full"]
                        ),
                        "wide_j0_minus_j3_d_hat_volume": _v8_wide_scalar_json(
                            wide_pair_add(
                                j0["wide_d_hat_volume"], j3["wide_d_hat_volume"], -1
                            )
                        ),
                        "wide_j0_minus_j3_d_hat_full": _v8_wide_scalar_json(
                            wide_pair_add(
                                j0["wide_d_hat_full"], j3["wide_d_hat_full"], -1
                            )
                        ),
                    }
                )

    p3_result = {
        "schema": "task41.p0.v8.selected_trace_star_p3_replay.v1",
        "status": "COMPLETED_LOCAL_ROW_REPLAY",
        "selected_active_row": selected_row,
        "selected_original_row": selected_original_row,
        "incident_cell_count": len(incident_order),
        "complete_incident_cell_coverage": True,
        "cell_sum_orders": {
            "production_original_cell_order": incident_order,
            "v6_eight_key_prefix_observer_order": v6_prefix_observer_order,
            "v6_eight_key_prefix_order": list(TASK41_P0_V6_PREFIX_CELLS),
            "nonincident_prefix_cells_contribute_exact_zero": [
                int(cell)
                for cell in TASK41_P0_V6_PREFIX_CELLS
                if int(cell) not in incident_set
            ],
        },
        "term_definition": {
            "s": "sum over incident cells w_c^H S_c t_c",
            "g_volume": "native_volume_rhs[selected_original_row] + sum over incident cells w_c^H T_c b_i,c",
            "g_full": "saved native_rhs[selected_original_row] once + sum over incident cells w_c^H T_c b_i,c; saved native_rhs already contains B_alpha",
            "r_full": "native_rhs[selected_original_row] - native_volume_action[selected_original_row] - sparse B_alpha[selected_original_row] exactly once",
            "d_hat": "delta_t + Q - r_t - sum(w_c^H T_c r_i,c)",
            "formal_candidate_or_residual_gate_changed": False,
        },
        "local_es_state_pair_differences": [
            {
                "cell_index": key[0],
                "column": key[1],
                "role": key[2],
                **value,
            }
            for key, value in sorted(p3_es_trace_state_differences.items())
        ],
        "ordered_summaries": p3_order_rows,
        "j0_j3_d_hat_state_invariance": p3_state_invariance,
        "per_cell_signed_contributions": p3_cell_rows,
    }
    checkpoint("selected_trace_star_p3_replay", p3_result)
    progress(
        {
            "phase": "selected_trace_star_p3_production_row_replay",
            "status": "COMPLETED",
            "incident_cell_count": len(incident_order),
            "summation_orders": list(cell_orders),
        }
    )

    numeric_cell_records = []
    for cell_index in sorted(cell_numeric):
        row = cell_numeric[cell_index]["row"]
        role_records = []
        for role in ("candidate", "reference"):
            role_data = cell_numeric[cell_index]["roles"][role]
            if role_data["source"] == "REUSED_HASH_BOUND_V6_PREFIX":
                prefix = f"task41_v6_prefix_cell{cell_index}_{role}"
                array_bindings = {
                    field: saved["v6_artifacts"][f"{prefix}_{field}"]
                    for field in ("raw_tensor", "oriented_tensor", "R", "T", "S")
                }
            else:
                array_bindings = {
                    field: role_data["artifacts"][field]
                    for field in ("raw_tensor", "oriented_tensor", "R", "T", "S")
                }
            role_records.append(
                {
                    "role": role,
                    "source": role_data["source"],
                    "producer_identity": (
                        evaluator.identity
                        if role == "candidate"
                        else "original_ffcx_reference_kernel"
                    ),
                    "raw_oriented_RTS_artifacts": array_bindings,
                    "strict_lu": role_data.get(
                        "strict_lu", role_data.get("strict_lu_residual")
                    ),
                    "raw_tensor_evaluator_identity": role_data.get(
                        "raw_tensor_evaluator_identity"
                    ),
                }
            )
        numeric_cell_records.append(
            {
                "cell_index": int(cell_index),
                "is_target_row_incident": int(cell_index) in incident_set,
                "tag": int(row["cell_tag"]),
                "permutation_and_direction": int(row["cell_permutation"]),
                "actual_geometry_coordinates_sha256": row["actual_coordinate_sha256"],
                "actual_geometry_coordinates_shape": list(
                    np.asarray(row["actual_geometry_coordinates"]).shape
                ),
                "true_interior_positions": np.asarray(
                    row["interior_positions"], dtype=np.int64
                ).tolist(),
                "trace_complement_positions": np.asarray(
                    row["trace_positions"], dtype=np.int64
                ).tolist(),
                "interior_original_rows": np.asarray(
                    row["interior_original_rows"], dtype=np.int64
                ).tolist(),
                "trace_original_rows": np.asarray(
                    row["trace_original_rows"], dtype=np.int64
                ).tolist(),
                "active_ids": np.asarray(row["active_ids"], dtype=np.int64).tolist(),
                "selected_local_trace_rows": np.asarray(
                    row["selected_local_trace_rows"], dtype=np.int64
                ).tolist(),
                "selected_trace_coefficients": [
                    complex_pair(value)
                    for value in np.asarray(
                        row["selected_trace_coefficients"], dtype=np.complex128
                    )
                ],
                "roles": role_records,
            }
        )

    result = {
        "schema": "task41.p0.v8.selected_trace_star_audit_result.v1",
        "status": "COMPLETED_SELECTED_TRACE_STAR_AUDIT",
        "selected_active_row": selected_row,
        "selected_original_row": selected_original_row,
        "donor_state_pairing": donor_state_pairing,
        "source_artifacts": saved_operand_replay["source_artifacts"],
        "saved_operand_recomposition": saved_operand_replay,
        "metadata": {
            "schema": "task41.p0.v8.selected_trace_star_metadata.v1",
            "selected_active_row": selected_row,
            "selected_original_row": selected_original_row,
            "active_trace_rows": int(metadata["active_trace_rows"]),
            "full_trace_rows": int(metadata["full_trace_rows"]),
            "slave_rows": int(metadata["slave_rows"]),
            "full_storage_rows": int(metadata["full_storage_rows"]),
            "owned_cells_scanned": int(metadata["owned_cells"]),
            "incident_cell_count": len(incident_order),
            "incident_cell_order": incident_order,
            "observer_v6_prefix_order": list(TASK41_P0_V6_PREFIX_CELLS),
            "v6_eight_key_prefix_observer_order": v6_prefix_observer_order,
            "saved_v6_map_checks": saved_map_checks,
            "selected_cells": run_record_metadata["selected_cells"],
            "element_dimension": dimension,
            "true_interior_positions": interior_positions.tolist(),
            "trace_complement_positions": trace_positions.tolist(),
        },
        "local_numeric_cell_identity_and_artifacts": numeric_cell_records,
        "p0_prefix_four_matrix_defects_and_state_actions": p0_rows,
        "p3_production_row_replay": p3_result,
        "wide_precision": {
            "implementation": "separate real/imag numpy.longdouble matvec, projection, and ordered scalar accumulation",
            "mantissa_bits": int(np.finfo(np.longdouble).nmant),
            "wider_than_float64": bool(
                np.finfo(np.longdouble).nmant > np.finfo(np.float64).nmant
            ),
            "formal_complex128_outputs_modified": False,
        },
        "evidence_cap_bytes": 16 * 1024**3,
        "prior_array_payload_bytes": int(saved["prior_array_payload_bytes"]),
        "remaining_array_cap_bytes_before_this_route": int(
            saved["remaining_array_cap_bytes"]
        ),
        "persisted_array_artifacts_directory": str(output_directory),
        "candidate_identity": evaluator.identity,
        "candidate_cache_identity": evaluator.cache_identity,
        "combined_ffcx_kernel_identity": compiled_identity,
        "scope_note": "One selected active trace row only. Both columns, paired donor states, candidate and original-FFCx reference are replayed locally; this diagnostic does not alter or pass any formal full-vector gate.",
    }
    checkpoint("selected_trace_star_result", result)
    return result


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--numerical-output", type=Path, required=True)
    parser.add_argument("--donor-contract", type=Path, required=True)
    parser.add_argument("--donor-contract-sha256", required=True)
    parser.add_argument("--consumer-contract", type=Path, required=True)
    parser.add_argument("--consumer-contract-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--geometry-pair-only", action="store_true")
    parser.add_argument("--selected-trace-star-audit", action="store_true")
    parser.add_argument(
        "--geometry-policy",
        choices=("canonical", "mesh_actual_exact"),
        default="canonical",
    )
    parser.add_argument(
        "--raw-tensor-evaluator",
        choices=("actual_qmetric_blocked_gram",),
        help="select the explicitly unqualified Review V6 actual-geometry candidate",
    )
    parser.add_argument("--ffcx-c-source", type=Path)
    parser.add_argument("--source-report", type=Path)
    parser.add_argument("--geometry-reference-report", type=Path)
    return parser.parse_args(argv)


def _checked_allocation_gate(
    label: str,
    facts: Mapping[str, Any],
    *,
    resource_admission: Any,
    resource_snapshot: Any,
    resources: Mapping[str, Any],
    progress: Any,
) -> None:
    required = int(facts.get("additional_payload_bytes", 0)) + int(facts.get("workspace_bytes", 0))
    admission = resource_admission(
        f"task41_v4_{label}",
        required,
        resource_sample=resource_snapshot,
        require_task_cgroup=True,
        explicit_process_tree_cap_bytes=int(resources["task_memory_max_bytes"]),
        host_reserve_bytes=int(resources["host_reserve_bytes"]),
        task_cgroup_reserve_bytes=int(resources.get("task_cgroup_reserve_bytes", 0)),
    )
    progress(
        {
            "phase": "allocation_gate",
            "status": "PASSED",
            "label": label,
            "additional_upper_bytes": required,
            "resource_admission": admission,
        }
    )


def _v8_selected_trace_star_allocation_gate(
    label: str,
    facts: Mapping[str, Any],
    *,
    fixed_window: Any,
    resources: Mapping[str, Any],
    resource_admission: Any,
    resource_snapshot: Any,
    output_directory: Path,
    prior_array_payload_bytes: int,
    persisted_array_bytes: int,
    progress: Any,
) -> dict[str, Any]:
    """Apply the selected-star local budget without V5/V6 global reserves."""

    from src.runners.task40_v10_campaign import read_campaign_state

    checked = dict(facts)
    estimate = float(checked.get("estimated_remaining_seconds_upper", 0.0))
    termination_reserve = float(
        checked.get("termination_reserve_seconds", TASK41_P0_V5_TERMINATION_RESERVE_SECONDS)
    )
    if (
        not math.isfinite(estimate)
        or estimate < 0.0
        or not math.isfinite(termination_reserve)
        or termination_reserve < 0.0
    ):
        raise ValueError("V8 selected-star time estimate or termination reserve is invalid")
    state = read_campaign_state(fixed_window, phase="numeric")
    remaining = float(state["remaining_phase_seconds"])
    required_seconds = estimate + termination_reserve
    if remaining < required_seconds:
        raise _CandidateNotAdmitted(
            f"{label}: fixed-window balance {remaining:.3f}s is below the selected-star "
            f"estimate and termination reserve {required_seconds:.3f}s"
        )

    evidence_reserve = int(
        checked.get(
            "evidence_reserve_bytes",
            checked.get("additional_payload_bytes", 0),
        )
    )
    scratch_reserve = int(checked.get("scratch_reserve_bytes", 0))
    if evidence_reserve < 0 or scratch_reserve < 0:
        raise ValueError("V8 selected-star evidence and scratch reserves cannot be negative")
    cumulative = int(prior_array_payload_bytes) + int(persisted_array_bytes) + evidence_reserve
    if cumulative > 16 * 1024**3:
        raise _CandidateNotAdmitted(
            f"{label}: selected-star evidence would exceed the unchanged 16 GiB cap by "
            f"{cumulative - 16 * 1024**3} bytes"
        )
    free_bytes = int(shutil.disk_usage(output_directory).free)
    if free_bytes - evidence_reserve - scratch_reserve < 2 * 1024**3:
        raise _CandidateNotAdmitted(
            f"{label}: selected-star output and scratch would breach the 2 GiB free-space floor by "
            f"{2 * 1024**3 - (free_bytes - evidence_reserve - scratch_reserve)} bytes"
        )
    checked["additional_payload_bytes"] = evidence_reserve
    checked["workspace_bytes"] = int(checked.get("workspace_bytes", 0)) + scratch_reserve
    _checked_allocation_gate(
        label,
        checked,
        resource_admission=resource_admission,
        resource_snapshot=resource_snapshot,
        resources=resources,
        progress=progress,
    )
    admission = {
        "campaign_window_sha256": fixed_window.sha256,
        "remaining_numeric_seconds": remaining,
        "estimated_remaining_selected_work_seconds": estimate,
        "termination_reserve_seconds": termination_reserve,
        "required_seconds": required_seconds,
        "prior_array_payload_bytes": int(prior_array_payload_bytes),
        "persisted_array_bytes": int(persisted_array_bytes),
        "selected_star_evidence_reserve_bytes": evidence_reserve,
        "evidence_cap_bytes": 16 * 1024**3,
        "free_bytes_before_reservation": free_bytes,
        "free_space_floor_bytes": 2 * 1024**3,
        "scratch_reserve_bytes": scratch_reserve,
        "read_only_live_campaign_state": state,
    }
    progress(
        {
            "phase": "selected_trace_star_live_admission",
            "status": "BALANCE_AND_RESOURCES_RECORDED",
            "label": label,
            **admission,
        }
    )
    return admission


def _v8_selected_trace_star_worker_allocation_gate(
    worker_args: argparse.Namespace,
    label: str,
    facts: Mapping[str, Any],
    *,
    fixed_window: Any,
    resources: Mapping[str, Any],
    resource_admission: Any,
    resource_snapshot: Any,
    output_directory: Path,
    prior_array_payload_bytes: int,
    persisted_array_bytes: int,
    progress: Any,
) -> dict[str, Any]:
    """Route the real worker allocation gate through the V8 local admission."""

    if not bool(getattr(worker_args, "selected_trace_star_audit", False)):
        raise ValueError("V8 worker allocation gate was called outside the selected-star route")
    return _v8_selected_trace_star_allocation_gate(
        label,
        facts,
        fixed_window=fixed_window,
        resources=resources,
        resource_admission=resource_admission,
        resource_snapshot=resource_snapshot,
        output_directory=output_directory,
        prior_array_payload_bytes=prior_array_payload_bytes,
        persisted_array_bytes=persisted_array_bytes,
        progress=progress,
    )


def _compiled_kernel_identity(compiled_form: Any, *, rank: int, label: str, sha256_file: Any) -> dict[str, Any]:
    form = compiled_form.ufcx_form
    ffi = compiled_form.module.ffi
    signature = ffi.string(form.signature).decode("ascii")
    # The existing raw-cell core only indexes the cell-integral offset pair.
    # Read that same bounded pair; do not walk the opaque FFCx pointer table.
    offsets = [int(form.form_integral_offsets[index]) for index in range(2)]
    if offsets[0] != 0 or offsets[1] < offsets[0]:
        raise ValueError("FFCx cell-integral offsets are invalid")
    if offsets[1] > 128:
        raise ValueError("FFCx cell-integral count is outside the finite identity bound")
    kernel_counts: dict[int, int] = {}
    for position in range(offsets[0], offsets[1]):
        integral_id = int(form.form_integral_ids[position])
        kernel = form.form_integrals[position].tabulate_tensor_complex128
        if kernel == ffi.NULL:
            raise TypeError("compiled form does not expose a complex128 cell kernel")
        kernel_counts[integral_id] = kernel_counts.get(integral_id, 0) + 1
    module_path_value = getattr(compiled_form.module, "__file__", None)
    module_path = None
    module_sha256 = None
    if module_path_value:
        candidate = Path(module_path_value).resolve()
        if candidate.is_file():
            module_path = str(candidate)
            module_sha256 = sha256_file(candidate)
    return {
        "label": label,
        "form_rank": int(rank),
        "ffcx_form_signature": signature,
        "ffcx_module_path": module_path,
        "ffcx_module_sha256": module_sha256,
        "cell_integral_count": offsets[1] - offsets[0],
        "cell_integral_offsets": offsets,
        "integral_kernel_counts": {
            str(key): kernel_counts[key] for key in sorted(kernel_counts)
        },
        "num_coefficients": int(form.num_coefficients),
        "num_constants": int(form.num_constants),
        "dtype": str(np.dtype(compiled_form.dtype)),
    }


def _load_bound_report_array(
    source_root: Path,
    records: Mapping[str, Mapping[str, Any]],
    name: str,
    *,
    sha256_file: Any,
) -> np.ndarray:
    record = records.get(name)
    if not isinstance(record, Mapping):
        raise ValueError(f"Task41 V4 source report omits saved array {name}")
    raw_path = Path(str(record.get("path", "")))
    path = (raw_path if raw_path.is_absolute() else source_root / raw_path).resolve(strict=True)
    if not path.is_relative_to(source_root) or path.stat().st_size != int(record.get("bytes", -1)):
        raise ValueError(f"Task41 V4 source array path or size differs for {name}")
    if sha256_file(path) != record.get("sha256"):
        raise ValueError(f"Task41 V4 source array hash differs for {name}")
    value = np.load(path, allow_pickle=False)
    if list(value.shape) != list(record.get("shape", ())) or str(value.dtype) != str(record.get("dtype")):
        raise ValueError(f"Task41 V4 source array metadata differs for {name}")
    return np.asarray(value)


def _load_v5_geometry_reference(
    report_path: Path,
    *,
    donor_manifest_sha256: str,
    sha256_file: Any,
) -> dict[str, Any]:
    report_path = report_path.resolve(strict=True)
    source_root = report_path.parent.resolve(strict=True)
    if not source_root.is_relative_to((ROOT / "results").resolve()):
        raise ValueError("V5 geometry reference report must remain in the registered results tree")
    if sha256_file(report_path) != TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256:
        raise ValueError("V5 geometry reference report SHA-256 differs from the frozen V4 evidence")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    probe = report.get("geometry_pair_probe")
    if (
        report.get("status") != "COMPLETED_GEOMETRY_PAIR_PROBE"
        or not isinstance(probe, Mapping)
        or probe.get("schema") != "task41.p0.v4.geometry_pair_probe.v1"
        or probe.get("source_report_sha256") != TASK41_P0_V4_SOURCE_REPORT_SHA256
        or probe.get("source_donor_manifest_sha256") != donor_manifest_sha256
        or [item.get("cell_index") for item in probe.get("selected_cells", [])]
        != list(TASK41_P0_V5_REFERENCE_CELLS)
    ):
        raise ValueError("V5 geometry reference is not the frozen two-cell V4 report")
    records_list = report.get("persisted_evidence_arrays")
    if not isinstance(records_list, list):
        raise ValueError("V5 geometry reference omits its hash-bound array inventory")
    records = {
        str(item["name"]): item
        for item in records_list
        if isinstance(item, Mapping) and isinstance(item.get("name"), str)
    }
    if len(records) != len(records_list):
        raise ValueError("V5 geometry reference has duplicate or malformed array identities")
    references: dict[int, dict[str, Any]] = {}
    for cell in probe["selected_cells"]:
        index = int(cell["cell_index"])
        prefix = f"cell{index}_actual_"
        geometry = _load_bound_report_array(
            source_root,
            records,
            f"cell{index}_actual_geometry_coordinates",
            sha256_file=sha256_file,
        )
        blocks = {
            name: _load_bound_report_array(
                source_root,
                records,
                prefix + name,
                sha256_file=sha256_file,
            )
            for name in ("K", "G", "J", "L")
        }
        block_meta = cell["block_artifacts"]["actual"]
        if any(
            not isinstance(block_meta.get(name), Mapping)
            or block_meta[name].get("sha256") != records[prefix + name].get("sha256")
            or block_meta[name].get("shape") != records[prefix + name].get("shape")
            or block_meta[name].get("dtype") != records[prefix + name].get("dtype")
            for name in ("K", "G", "J", "L")
        ):
            raise ValueError(f"V5 reference inventory disagrees with selected cell {index} block metadata")
        references[index] = {
            "coordinates": geometry,
            "blocks": blocks,
            "cell_tag": int(cell["cell_tag"]),
            "cell_permutation": int(cell["cell_permutation"]),
            "block_sha256": {
                name: str(records[prefix + name]["sha256"])
                for name in ("K", "G", "J", "L")
            },
            "coordinates_sha256": str(
                records[f"cell{index}_actual_geometry_coordinates"]["sha256"]
            ),
        }
    return {
        "path": str(report_path),
        "sha256": TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256,
        "source_root": str(source_root),
        "cells": references,
    }


def _run_geometry_pair_probe(
    *,
    cfg: Any,
    donor: dict[str, Any],
    source_report_path: Path,
    consumer_contract: Mapping[str, Any],
    output_directory: Path,
    persist_array: Any,
    allocation_gate: Any,
    progress: Any,
    sha256_file: Any,
) -> dict[str, Any]:
    """Extract and attribute only the two frozen selected-row incident cells."""

    import ufl
    from basix.ufl import element
    from dolfinx import default_real_type, fem
    from mpi4py import MPI

    from src.geometry.mesh_builder_3d import _mark_cells, _stage4_axis_plan, _structured_hexa_mesh
    from src.solvers.common_3d_forms import _build_physical_volume_terms
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
    from src.solvers.hcurl_assembly_time_condensation import tabulate_volume_audit_cell_geometry_pair
    from src.solvers.task41_v4_volume_only_audit import audit_task41_v4_geometry_pair_attribution

    selected_cells = (26762, 26897)
    source_report_path = source_report_path.resolve(strict=True)
    source_root = source_report_path.parent.resolve(strict=True)
    expected_report_sha = TASK41_P0_V4_SOURCE_REPORT_SHA256
    if not source_root.is_relative_to((ROOT / "results").resolve()):
        raise ValueError("Task41 V4 source report must remain inside this repository's results tree")
    if sha256_file(source_report_path) != expected_report_sha:
        raise ValueError("Task41 V4 source report SHA-256 differs from the frozen Review V4 receipt")
    source_report = json.loads(source_report_path.read_text(encoding="utf-8"))
    if (
        source_report.get("status") != "COMPLETED"
        or source_report.get("donor_manifest_sha256") != donor.get("manifest_sha256")
        or source_report.get("consumer_source_sha") != "d883c1f3381b4f3d6100022097d615846564673c"
        or source_report.get("owner_audit", {}).get("selected_active_row")
        != TASK41_P0_V4_SELECTED_ACTIVE_ROW
        or source_report.get("owner_audit", {}).get("selected_original_row")
        != TASK41_P0_V4_SELECTED_ORIGINAL_ROW
    ):
        raise ValueError("Task41 V4 source receipt is not the frozen two-cell donor")
    records_list = source_report.get("persisted_evidence_arrays")
    if not isinstance(records_list, list):
        raise ValueError("Task41 V4 source receipt omits its hash-bound array inventory")
    records = {
        str(item["name"]): item for item in records_list
        if isinstance(item, Mapping) and isinstance(item.get("name"), str)
    }
    if len(records) != len(records_list):
        raise ValueError("Task41 V4 source receipt has duplicate or malformed array names")
    class_keys = {
        tuple(item["class_key"])
        for item in source_report.get("identity_audit", {}).get("local_class_identities", ())
        if isinstance(item, Mapping) and isinstance(item.get("class_key"), list)
    }

    allocation_gate(
        "geometry_pair_mesh_rebuild",
        {"additional_payload_bytes": 0, "workspace_bytes": 6 * 1024**3, "degree": 6},
    )
    prior_bytes = int(donor["existing_evidence_bytes"]) + int(source_report["persisted_evidence_bytes"])
    if prior_bytes >= 16 * 1024**3:
        raise MemoryError("Task41 V4 geometry-pair input is already at the unchanged 16 GiB cap")
    if not output_directory.is_dir():
        raise FileNotFoundError("Task41 V4 geometry-pair output directory was not prepared")
    import shutil

    free_bytes = int(shutil.disk_usage(output_directory).free)
    if free_bytes < 2 * 1024**3:
        raise OSError("Task41 V4 geometry-pair output is below the unchanged 2 GiB free-space floor")

    progress({"phase": "geometry_pair_mesh_space", "status": "STARTED", "degree": 6})
    plan = _stage4_axis_plan(cfg, MPI.COMM_SELF.size)
    mesh = _structured_hexa_mesh(
        MPI.COMM_SELF,
        plan.x_values,
        plan.y_values,
        plan.z_values,
        preserve_input_partition=cfg.stage4_preserve_structured_input_partition,
    )
    cell_tags = _mark_cells(mesh, cfg)
    space = fem.functionspace(mesh, element("N1curl", mesh.basix_cell(), 6, dtype=default_real_type))
    progress({
        "phase": "geometry_pair_mesh_space",
        "status": "COMPLETED",
        "owned_cells": int(mesh.topology.index_map(mesh.topology.dim).size_local),
        "global_dofs": int(space.dofmap.index_map.size_global),
    })

    trial, test = ufl.TrialFunction(space), ufl.TestFunction(space)
    dx = ufl.Measure("dx", domain=mesh, subdomain_data=cell_tags)
    curl_form, mass_form = _build_physical_volume_terms(cfg, trial, test, dx)
    jit_options = dict(SAME_MESH_JIT_OPTIONS)
    combined_form = fem.form(curl_form + mass_form, jit_options=jit_options)
    source_function = fem.Function(space)
    split_forms = (
        fem.form(ufl.action(curl_form, source_function), jit_options=jit_options),
        fem.form(ufl.action(mass_form, source_function), jit_options=jit_options),
    )
    kernel_identities = {
        "fresh_combined_volume": _compiled_kernel_identity(
            combined_form, rank=2, label="combined_curl_plus_mass", sha256_file=sha256_file
        ),
        "native_split_curl_action": _compiled_kernel_identity(
            split_forms[0], rank=1, label="split_curl_ufl_action", sha256_file=sha256_file
        ),
        "native_split_mass_action": _compiled_kernel_identity(
            split_forms[1], rank=1, label="split_mass_ufl_action", sha256_file=sha256_file
        ),
        "relationship": "Fresh blocks are combined rank-2 FFCx; saved native actions are split rank-1 FFCx. The signatures and arithmetic paths are kept distinct.",
    }

    dimension = int(space.element.space_dimension)
    interior_count = len(space.element.basix_element.entity_dofs[mesh.topology.dim][0])
    geometry_node_count = int(np.asarray(mesh.geometry.dofmap).shape[1])
    block_bytes = 2 * len(selected_cells) * dimension * dimension * np.dtype(np.complex128).itemsize
    geometry_and_dof_bytes = len(selected_cells) * (
        2 * geometry_node_count * 3 * np.dtype(np.float64).itemsize
        + geometry_node_count * np.dtype(np.int32).itemsize
        + dimension * np.dtype(np.int32).itemsize
        + dimension * np.dtype(np.int64).itemsize
    )
    selected_vector_bytes = (
        2 * 2 * 2 * len(selected_cells) * interior_count * np.dtype(np.complex128).itemsize
    )
    projected_evidence_bytes = int(
        block_bytes + geometry_and_dof_bytes + selected_vector_bytes + 1024**2
    )
    pair_workspace_bytes = int(
        2 * len(selected_cells) * 2 * dimension * dimension * np.dtype(np.complex128).itemsize
        + projected_evidence_bytes
        + 32 * 1024**2
    )
    if prior_bytes + projected_evidence_bytes > 16 * 1024**3:
        raise MemoryError("Task41 V4 geometry-pair evidence would exceed the unchanged 16 GiB cap")
    if free_bytes - projected_evidence_bytes < 2 * 1024**3:
        raise OSError(
            "Task41 V4 geometry-pair output would breach the unchanged 2 GiB free-space floor"
        )
    allocation_gate(
        "geometry_pair_blocks_and_selected_row_vectors",
        {
            "additional_payload_bytes": projected_evidence_bytes,
            "workspace_bytes": pair_workspace_bytes,
            "selected_cells": list(selected_cells),
            "coordinate_paths": 2,
            "block_artifacts_only": ["K", "G", "J", "L"],
        },
    )
    cell_pairs: dict[int, dict[str, Any]] = {}
    saved_maps: dict[int, dict[str, np.ndarray]] = {}
    saved_classes: dict[int, Mapping[str, np.ndarray] | None] = {}
    cell_records = []
    for cell_index in selected_cells:
        progress({"phase": "geometry_pair_cell", "status": "STARTED", "cell_index": cell_index})
        pair = tabulate_volume_audit_cell_geometry_pair(combined_form, space, cell_tags, cell_index)
        if pair["actual_geometry_coordinates"].shape != (8, 3):
            raise ValueError(f"selected cell {cell_index} does not have the expected eight actual geometry nodes")
        if tuple(pair["class_key"]) not in class_keys:
            raise ValueError(f"fresh cell class/permutation identity is absent from the frozen V4 receipt: {cell_index}")
        prefix = f"task41_v4_volume_cell_{cell_index}"
        cell_map = {
            name: _load_bound_report_array(source_root, records, f"{prefix}_{name}", sha256_file=sha256_file)
            for name in (
                "interior_original_rows", "trace_original_rows", "active_ids",
                "trace_expansion_data", "trace_expansion_indices", "trace_expansion_indptr",
            )
        }
        if not (
            np.array_equal(pair["interior_original_dofs"], cell_map["interior_original_rows"])
            and np.array_equal(pair["trace_original_dofs"], cell_map["trace_original_rows"])
        ):
            raise ValueError(f"fresh p6 cell dofmap differs from saved V4 rows for cell {cell_index}")
        if cell_map["active_ids"].size == 0 or np.any(cell_map["active_ids"] < 0):
            raise ValueError(f"saved V4 active map is invalid for cell {cell_index}")
        saved_maps[cell_index] = cell_map
        cell_pairs[cell_index] = pair

        class_ids = sorted({
            name[len("task41_v4_volume_class_"):-2]
            for name in records
            if name.startswith("task41_v4_volume_class_") and name.endswith("_K")
        })
        class_data = {}
        for class_id in class_ids:
            candidate = {
                name: _load_bound_report_array(
                    source_root, records, f"task41_v4_volume_class_{class_id}_{name}", sha256_file=sha256_file
                )
                for name in ("K", "G", "J", "L", "T", "S")
            }
            if all(np.array_equal(pair["canonical"][name], candidate[name]) for name in ("K", "G", "J", "L")):
                class_data[class_id] = candidate
        if len(class_data) > 1:
            raise ValueError(f"saved canonical class blocks are ambiguous for cell {cell_index}")
        saved_class_id, saved_class = next(iter(class_data.items())) if class_data else (None, None)
        saved_classes[cell_index] = saved_class

        artifacts = {}
        for name, value in (
            ("geometry_dofs", pair["geometry_dofs"]),
            ("actual_geometry_coordinates", pair["actual_geometry_coordinates"]),
            ("canonical_geometry_coordinates", pair["canonical_geometry_coordinates"]),
            ("local_dofs", pair["local_dofs"]),
            ("original_dofs", pair["original_dofs"]),
        ):
            artifacts[name] = persist_array(f"cell{cell_index}_{name}", value)
        block_artifacts = {
            path_name: {
                name: persist_array(f"cell{cell_index}_{path_name}_{name}", pair[path_name][name])
                for name in ("K", "G", "J", "L")
            }
            for path_name in ("actual", "canonical")
        }
        cell_records.append({
            "cell_index": cell_index,
            "cell_tag": int(pair["cell_tag"]),
            "class_key": [int(pair["class_key"][0]), *[float(v) for v in pair["class_key"][1:4]], int(pair["class_key"][4])],
            "cell_permutation": int(pair["cell_permutation"]),
            "dofmap_identity_passed": True,
            "saved_class_key_listed": True,
            "saved_canonical_class_id": saved_class_id,
            "saved_map_artifacts": {name: dict(records[f"{prefix}_{name}"]) for name in cell_map},
            "geometry_and_dof_artifacts": artifacts,
            "block_artifacts": block_artifacts,
            "integral_kernel_counts": pair["integral_kernel_counts"],
        })
        progress({"phase": "geometry_pair_cell", "status": "COMPLETED", "cell_index": cell_index})

    columns = donor["columns"]
    for column in columns:
        for name in list(column):
            if name not in {"active_original_rows", "known_field", "states"}:
                del column[name]
        for state in column["states"]:
            for name in list(state):
                if name not in {"storage", "native_volume_action"}:
                    del state[name]
    donor.pop("raw_classes", None)
    donor.pop("cell_maps", None)
    donor.pop("attribution", None)

    saved_d_volume = [
        _load_bound_report_array(source_root, records, f"task41_v4_d_volume_trace_col{col}", sha256_file=sha256_file)
        for col in range(2)
    ]
    saved_reduce = {
        (col, state): _load_bound_report_array(
            source_root, records, f"task41_v4_reduce_r_volume_{state}_col{col}", sha256_file=sha256_file
        )
        for col in range(2) for state in ("j0", "j3")
    }
    denominators = [float(item["saved_original_denom"]) for item in source_report["identity_audit"]["columns"]]
    attribution = audit_task41_v4_geometry_pair_attribution(
        cell_pairs=cell_pairs,
        saved_maps=saved_maps,
        columns=columns,
        saved_classes=saved_classes,
        saved_d_volume=saved_d_volume,
        saved_reduce_r_volume=saved_reduce,
        original_denominators=denominators,
        target_active_row=TASK41_P0_V4_SELECTED_ACTIVE_ROW,
        target_original_row=TASK41_P0_V4_SELECTED_ORIGINAL_ROW,
    )
    attribution_artifacts = {
        name: persist_array(name, values)
        for name, values in attribution.pop("delta_i_arrays").items()
    }
    return {
        "schema": "task41.p0.v4.geometry_pair_probe.v1",
        "source_report_path": str(source_report_path),
        "source_report_sha256": expected_report_sha,
        "consumer_source_sha": consumer_contract.get("source", {}).get("sha"),
        "source_donor_manifest_sha256": donor.get("manifest_sha256"),
        "prior_evidence_bytes": prior_bytes,
        "projected_new_evidence_bytes": projected_evidence_bytes,
        "unchanged_evidence_cap_bytes": 16 * 1024**3,
        "selected_active_row": TASK41_P0_V4_SELECTED_ACTIVE_ROW,
        "selected_original_row": TASK41_P0_V4_SELECTED_ORIGINAL_ROW,
        "selected_cells": cell_records,
        "ffcx_kernel_identities": kernel_identities,
        "attribution": attribution["attribution"],
        "delta_i_artifacts": attribution_artifacts,
        "scope_note": "Two-cell selected-row diagnostic only. Its global-denominator-scaled residual is not the whole-column 1e-11 gate. Actual-vs-canonical uses one combined rank-2 form; saved native actions use two separately compiled rank-1 forms.",
    }

def main(argv: list[str] | None = None) -> int:
    started_perf = perf_counter()
    started_at_utc = datetime.now(timezone.utc).isoformat()
    args = _parse_args(argv)
    if args.selected_trace_star_audit and args.geometry_pair_only:
        raise ValueError("V8 selected trace-star audit cannot use the V4 geometry-pair mode")
    if args.geometry_pair_only != (args.source_report is not None):
        raise ValueError("--geometry-pair-only and --source-report must be provided together")
    if args.geometry_pair_only and args.geometry_policy != "canonical":
        raise ValueError("the selected-cell geometry-pair diagnostic remains canonical-only")
    if (
        args.geometry_policy == "mesh_actual_exact"
        and args.geometry_reference_report is None
        and not args.selected_trace_star_audit
    ):
        raise ValueError("mesh_actual_exact requires the frozen two-cell V4 geometry reference report")
    if args.geometry_policy != "mesh_actual_exact" and args.geometry_reference_report is not None:
        raise ValueError("V4 canonical paths cannot consume the V5 exact-geometry reference")
    if args.raw_tensor_evaluator is not None and args.geometry_policy != "mesh_actual_exact":
        raise ValueError("actual q-metric evaluator requires --geometry-policy mesh_actual_exact")
    if (args.raw_tensor_evaluator is None) != (args.ffcx_c_source is None):
        raise ValueError("--ffcx-c-source must be supplied exactly with --raw-tensor-evaluator")
    if args.selected_trace_star_audit and (
        args.geometry_policy != "mesh_actual_exact"
        or args.raw_tensor_evaluator != "actual_qmetric_blocked_gram"
    ):
        raise ValueError(
            "V8 selected trace-star audit requires mesh_actual_exact and the frozen actual-qmetric evaluator"
        )
    from src.runners.task40_v20_stage_runner import _resource_snapshot
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.runners.task41_p0_checker import load_task41_v4_volume_only_donor
    from src.runners.task41_p0_contract import require_task41_p0_contract, sha256_file
    from src.solvers.task40_v22_operator_probe import _resource_admission
    from src.solvers.task41_v4_volume_only_audit import (
        TASK41_V4_DONOR_MANIFEST_SHA256,
        TASK41_V5_ATTRIBUTION_ACCUMULATOR_COUNT,
        TASK41_V5_FROZEN_DENOMINATORS,
        Task41V5VolumeAttributionAccumulator,
        audit_task41_v4_volume_identity,
        build_task41_v4_volume_only_owner,
    )

    donor_contract, donor_digest = require_task41_p0_contract(
        args.donor_contract,
        expected_sha256=args.donor_contract_sha256,
        current_root=ROOT,
        check_current_source=False,
        require_clean_source=False,
    )
    consumer_contract, consumer_digest = require_task41_p0_contract(
        args.consumer_contract,
        expected_sha256=args.consumer_contract_sha256,
        current_root=ROOT,
        check_current_source=True,
        require_clean_source=True,
    )
    fixed_window = None
    initial_fixed_window_state = None
    postbuild_reserve_evidence: dict[str, Any] | None = None
    if args.geometry_policy == "mesh_actual_exact":
        from src.runners.task41_p0_contract import load_task41_p0_fixed_window
        from src.runners.task40_v10_campaign import read_campaign_state

        fixed_window = load_task41_p0_fixed_window(
            consumer_contract,
            current_root=ROOT,
        )
        initial_fixed_window_state = read_campaign_state(
            fixed_window,
            phase="numeric",
        )
        v4_receipt_path = (
            ROOT
            / "docs/task41extra_phi90_p50x50_g17x20/outcomes/"
            / "b0_v4_volume_only_attribution_20261020.json"
        )
        if not args.selected_trace_star_audit:
            postbuild_reserve_evidence = _v6_postbuild_reserve_evidence(
                v4_receipt_path,
                donor_contract=donor_contract,
                donor_contract_sha256=donor_digest,
                donor_manifest_sha256=TASK41_V4_DONOR_MANIFEST_SHA256,
                current_execution_window_sha256=fixed_window.sha256,
            )
            postbuild_parent_seconds = float(
                postbuild_reserve_evidence["measured_service_parent_seconds"]
            )
    donor_case = donor_contract.get("case", {})
    consumer_case = consumer_contract.get("case", {})
    for key in (
        "model_id",
        "method",
        "mpi_size",
        "input_sha256",
        "physical_model_sha256",
        "resolved_config_sha256",
        "run_id",
    ):
        if donor_case.get(key) != consumer_case.get(key):
            raise ValueError(f"Task41 V4 donor/consumer case identity differs at {key}")
    if args.summary.resolve(strict=True).parent != args.numerical_output.resolve().parent:
        raise ValueError("Task41 V4 summary and numerical-output roots differ")
    run_root = args.summary.resolve(strict=True).parent
    config_path = run_root / "resolved_config.json"
    if sha256_file(config_path) != donor_case.get("resolved_config_sha256"):
        raise ValueError("Task41 V4 resolved configuration differs from its frozen producer contract")
    resolved = json.loads(config_path.read_text(encoding="utf-8"))
    cfg = simulation_config_3d_from_normalized(resolved)
    output_root = args.output_dir.resolve(strict=True)
    v6_actual_qmetric_mode = args.raw_tensor_evaluator == "actual_qmetric_blocked_gram"
    output_directory = output_root / (
        "selected_trace_star_audit"
        if args.selected_trace_star_audit
        else "geometry_pair"
        if args.geometry_pair_only
        else "actual_qmetric_blocked_gram"
        if v6_actual_qmetric_mode
        else "mesh_actual_exact"
        if args.geometry_policy == "mesh_actual_exact"
        else "volume_only"
    )
    output_directory.mkdir(parents=True, exist_ok=False)
    report_path = output_root / (
        "task41_p0_v8_selected_trace_star_audit.json"
        if args.selected_trace_star_audit
        else "task41_p0_v4_geometry_pair_probe.json"
        if args.geometry_pair_only
        else "task41_p0_v6_actual_qmetric_candidate.json"
        if v6_actual_qmetric_mode
        else "task41_p0_v5_mesh_actual_exact_attribution.json"
        if args.geometry_policy == "mesh_actual_exact"
        else "task41_p0_v4_volume_only_attribution.json"
    )
    if report_path.exists():
        raise FileExistsError(f"Task41 V4 attribution report already exists: {report_path}")
    phase_path = output_root / (
        "task41_p0_v8_selected_trace_star_phase.json"
        if args.selected_trace_star_audit
        else "task41_p0_v4_volume_only_phase.json"
    )
    event_path = output_root / (
        "task41_p0_v8_selected_trace_star_events.jsonl"
        if args.selected_trace_star_audit
        else "task41_p0_v4_volume_only_events.jsonl"
    )
    donor = load_task41_v4_volume_only_donor(
        summary_path=args.summary,
        numerical_output=args.numerical_output,
    )
    geometry_reference = (
        _load_v5_geometry_reference(
            args.geometry_reference_report,
            donor_manifest_sha256=str(donor["manifest_sha256"]),
            sha256_file=sha256_file,
        )
        if args.geometry_policy == "mesh_actual_exact" and not args.selected_trace_star_audit
        else None
    )
    run_record: dict[str, Any] = {
        "schema": (
            "task41.p0.v8.selected_trace_star_audit_receipt.v1"
            if args.selected_trace_star_audit
            else "task41.p0.v4.geometry_pair_probe_receipt.v1"
            if args.geometry_pair_only
            else "task41.p0.v6.actual_qmetric_candidate_receipt.v1"
            if v6_actual_qmetric_mode
            else "task41.p0.v5.mesh_actual_exact_attribution_receipt.v1"
            if args.geometry_policy == "mesh_actual_exact"
            else "task41.p0.v4.volume_only_attribution_receipt.v1"
        ),
        "status": "RUNNING",
        "geometry_policy": args.geometry_policy,
        "raw_tensor_evaluator": args.raw_tensor_evaluator,
        "started_at_utc": started_at_utc,
        "worker_started_perf_counter": started_perf,
        "donor_contract_path": str(args.donor_contract.resolve()),
        "donor_contract_sha256": donor_digest,
        "donor_source_sha": donor_contract.get("source", {}).get("sha"),
        "consumer_contract_path": str(args.consumer_contract.resolve()),
        "consumer_contract_sha256": consumer_digest,
        "consumer_source_sha": consumer_contract.get("source", {}).get("sha"),
        "resolved_config_sha256": donor_case.get("resolved_config_sha256"),
        "donor_manifest_sha256": donor.get("manifest_sha256"),
        "output_directory": str(output_root),
        "volume_evidence_directory": str(output_directory),
        "source_report_path": (
            str(args.source_report.resolve()) if args.source_report is not None else None
        ),
        "geometry_reference_report_path": (
            geometry_reference["path"] if geometry_reference is not None else None
        ),
        "geometry_reference_report_sha256": (
            geometry_reference["sha256"] if geometry_reference is not None else None
        ),
        "phase_path": str(phase_path),
        "event_log_path": str(event_path),
        "preparation_elapsed_seconds": perf_counter() - started_perf,
        "initial_fixed_window_state": initial_fixed_window_state,
        "postbuild_reserve_evidence": postbuild_reserve_evidence,
    }
    if v6_actual_qmetric_mode:
        run_record["candidate_prefix_qualification"] = {
            "schema": "task41.p0.v6.actual_qmetric_prefix_qualification.v1",
            "status": "PREFIX_QUALIFICATION_PENDING",
            "required_sample_cell_indices": list(TASK41_P0_V6_PREFIX_CELLS),
            "sample_count": 0,
            "required_sample_count": len(TASK41_P0_V6_PREFIX_CELLS),
            "geometry_witness_count": 0,
            "full_admission_eligible": False,
            "records": [],
            "global_b_t_accumulation": "not_performed_by_local_prefix_qualification",
        }
    _write_json_atomic(report_path, run_record)
    phase_started: dict[tuple[str, Any], float] = {}

    def progress(event: Mapping[str, Any]) -> None:
        now = perf_counter()
        phase = str(event.get("phase", "unknown"))
        phase_key = (phase, event.get("column"))
        if event.get("status") == "STARTED" or phase_key not in phase_started:
            phase_started[phase_key] = now
        row = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "elapsed_since_worker_start_seconds": now - started_perf,
            "elapsed_in_phase_seconds": now - phase_started[phase_key],
            **dict(event),
        }
        with event_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        _write_json_atomic(phase_path, row)
        print(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False), flush=True)

    def checkpoint(name: str, payload: Mapping[str, Any]) -> None:
        run_record[str(name)] = dict(payload)
        _write_json_atomic(report_path, run_record)

    def persist_volume_array(name: str, array: np.ndarray) -> dict[str, Any]:
        array_bytes_upper = int(np.asarray(array).nbytes) + 4096
        prefix_budget_remaining = int(
            run_record.get("candidate_prefix_evidence_reserve_remaining_bytes", 0)
        )
        if name.startswith("task41_v6_prefix_") and array_bytes_upper > prefix_budget_remaining:
            raise MemoryError(
                "V6 prefix artifact exceeds its reserved evidence budget by "
                f"{array_bytes_upper - prefix_budget_remaining} bytes"
            )
        prefix_budget_consumed = (
            array_bytes_upper if name.startswith("task41_v6_prefix_") else 0
        )
        prefix_budget_after = prefix_budget_remaining - prefix_budget_consumed
        if args.selected_trace_star_audit:
            cumulative_after = (
                TASK41_P0_V8_PRIOR_ARRAY_BYTES
                + int(run_record.get("persisted_evidence_bytes", 0))
                + array_bytes_upper
            )
            if cumulative_after > 16 * 1024**3:
                raise MemoryError(
                    "V8 selected-star evidence would exceed the unchanged 16 GiB cap by "
                    f"{cumulative_after - 16 * 1024**3} bytes"
                )
            free_before = int(shutil.disk_usage(output_directory).free)
            if free_before - array_bytes_upper < 2 * 1024**3:
                raise OSError(
                    "V8 selected-star evidence write would breach the 2 GiB free-space floor by "
                    f"{2 * 1024**3 - (free_before - array_bytes_upper)} bytes"
                )
        else:
            cumulative_before = (
                int(donor.get("existing_evidence_bytes", 0))
                + int(run_record.get("candidate_admission_evidence_bytes", 0))
            ) + int(run_record.get("persisted_evidence_bytes", 0))
            if cumulative_before + array_bytes_upper + prefix_budget_after > 16 * 1024**3:
                raise MemoryError(
                    "Task41 V5 evidence write would exceed the unchanged 16 GiB cap by "
                    f"{cumulative_before + array_bytes_upper + prefix_budget_after - 16 * 1024**3} bytes"
                )
            free_before = int(shutil.disk_usage(output_directory).free)
            if free_before - array_bytes_upper - prefix_budget_after < 2 * 1024**3:
                raise OSError(
                    "Task41 V5 evidence write would breach the 2 GiB free-space floor by "
                    f"{2 * 1024**3 - (free_before - array_bytes_upper - prefix_budget_after)} bytes"
                )
        artifact = _persist_array(
            output_directory, name, array, sha256_file=sha256_file
        )
        records = run_record.setdefault("persisted_evidence_arrays", [])
        records.append({"name": name, **artifact})
        run_record["persisted_evidence_bytes"] = sum(
            int(item["bytes"]) for item in records
        )
        if prefix_budget_consumed:
            run_record["candidate_prefix_evidence_reserve_remaining_bytes"] = (
                prefix_budget_after
            )
        _write_json_atomic(report_path, run_record)
        return artifact

    candidate_identity = None
    candidate_artifact_prefix = "task41_p0_v5_candidate"
    candidate_attribution_prefix = "task41_p0_v5_attribution"
    if v6_actual_qmetric_mode:
        from src.solvers.task41_actual_qmetric_blocked_gram import IDENTITY

        candidate_identity = IDENTITY
        candidate_artifact_prefix = "task41_p0_v6_qmetric_candidate"
        candidate_attribution_prefix = "task41_p0_v6_qmetric_candidate_attribution"
    exact_attribution = (
        Task41V5VolumeAttributionAccumulator(
            donor,
            artifact_prefix=candidate_artifact_prefix,
            attribution_prefix=candidate_attribution_prefix,
            candidate_identity=candidate_identity,
        )
        if args.geometry_policy == "mesh_actual_exact" and not args.selected_trace_star_audit
        else None
    )

    def allocation_gate(label: str, facts: Mapping[str, Any]) -> None:
        checked_facts = dict(facts)
        if args.selected_trace_star_audit:
            if fixed_window is None:
                raise RuntimeError("V8 selected-star admission requires the fixed numeric window")
            admission = _v8_selected_trace_star_worker_allocation_gate(
                args,
                label,
                checked_facts,
                fixed_window=fixed_window,
                resources=consumer_contract["resources"],
                resource_admission=_resource_admission,
                resource_snapshot=_resource_snapshot,
                output_directory=output_directory,
                prior_array_payload_bytes=TASK41_P0_V8_PRIOR_ARRAY_BYTES,
                persisted_array_bytes=int(run_record.get("persisted_evidence_bytes", 0)),
                progress=progress,
            )
            run_record.setdefault("selected_trace_star_admissions", []).append(admission)
            _write_json_atomic(report_path, run_record)
            return
        scratch_reserve_bytes = 0
        if (
            args.geometry_policy == "mesh_actual_exact"
            and label == "mesh_actual_exact_prefix_preflight"
        ):
            scratch_reserve_bytes = int(
                checked_facts.get("raw_tensor_candidate_scratch_bytes_upper", 0)
            )
            if scratch_reserve_bytes < 0:
                raise ValueError("candidate scratch reservation cannot be negative")
            free_bytes = int(shutil.disk_usage(output_directory).free)
            checked_facts["candidate_scratch_disk_preflight"] = {
                "reserved_scratch_bytes_upper": scratch_reserve_bytes,
                "free_bytes_before_scratch": free_bytes,
                "free_bytes_after_reservation": free_bytes - scratch_reserve_bytes,
                "free_space_floor_bytes": 2 * 1024**3,
            }
            if free_bytes - scratch_reserve_bytes < 2 * 1024**3:
                raise _CandidateNotAdmitted(
                    "actual-qmetric helper/oracle scratch would breach the 2 GiB "
                    "free-space floor before preparation"
                )
            if v6_actual_qmetric_mode:
                dimension = int(checked_facts["tensor_dimension"])
                interior_dimension = int(checked_facts["interior_dimension"])
                trace_dimension = int(checked_facts["trace_dimension"])
                matrix_bytes = dimension * dimension * np.dtype(np.complex128).itemsize
                rts_bytes_per_key = (
                    interior_dimension * interior_dimension
                    + 2 * interior_dimension * trace_dimension
                    + trace_dimension * trace_dimension
                ) * np.dtype(np.complex128).itemsize
                prefix_evidence_reserve = (
                    32 * matrix_bytes
                    + 8 * 2 * rts_bytes_per_key
                    + 2 * 2 * 3 * 2 * dimension * np.dtype(np.complex128).itemsize
                    + 8 * (8 * 3 * np.dtype(np.float64).itemsize + 4096)
                    + 8 * 1024**2
                )
                evidence_bytes_before = (
                    int(donor.get("existing_evidence_bytes", 0))
                    + int(run_record.get("candidate_admission_evidence_bytes", 0))
                    + int(run_record.get("persisted_evidence_bytes", 0))
                )
                free_bytes = int(shutil.disk_usage(output_directory).free)
                checked_facts["v6_prefix_qualification_evidence_reserve"] = {
                    "required_cells": list(TASK41_P0_V6_PREFIX_CELLS),
                    "candidate_and_reference_tensor_bytes_upper": 32 * matrix_bytes,
                    "candidate_and_reference_RTS_bytes_upper": 8 * 2 * rts_bytes_per_key,
                    "saved_cell_action_bytes_upper": (
                        2 * 2 * 3 * 2 * dimension * np.dtype(np.complex128).itemsize
                    ),
                    "artifact_and_json_overhead_bytes_upper": (
                        8 * (8 * 3 * np.dtype(np.float64).itemsize + 4096)
                        + 8 * 1024**2
                    ),
                    "total_reserved_bytes_upper": int(prefix_evidence_reserve),
                    "evidence_bytes_before": evidence_bytes_before,
                    "free_bytes_before": free_bytes,
                    "evidence_cap_bytes": 16 * 1024**3,
                    "free_space_floor_bytes": 2 * 1024**3,
                }
                if evidence_bytes_before + prefix_evidence_reserve > 16 * 1024**3:
                    raise _CandidateNotAdmitted(
                        "V6 eight-key qualification evidence would exceed the unchanged 16 GiB cap"
                    )
                if (
                    free_bytes
                    - scratch_reserve_bytes
                    - prefix_evidence_reserve
                    < 2 * 1024**3
                ):
                    raise _CandidateNotAdmitted(
                        "V6 prefix evidence and oracle scratch would breach the 2 GiB free-space floor"
                    )
                run_record["candidate_prefix_evidence_reserve_bytes"] = int(
                    prefix_evidence_reserve
                )
                run_record["candidate_prefix_evidence_reserve_remaining_bytes"] = int(
                    prefix_evidence_reserve
                )
                _write_json_atomic(report_path, run_record)
        if args.geometry_policy == "mesh_actual_exact" and label in {
            "mesh_actual_exact_prefix_preflight",
            "mesh_actual_exact_full_admission",
        }:
            if label == "mesh_actual_exact_full_admission":
                active_rows = int(donor["manifest"]["active_trace_rows"])
                port_rows = int(donor["manifest"]["port_rows"])
                full_rows = int(donor["manifest"]["full_storage_rows"])
                candidate_rows = active_rows + port_rows
                candidate_array_bytes = (
                    2 * candidate_rows * 2 * np.dtype(np.complex128).itemsize
                )
                accumulator_bytes = (
                    TASK41_V5_ATTRIBUTION_ACCUMULATOR_COUNT
                    * active_rows
                    * np.dtype(np.complex128).itemsize
                )
                action_and_closure_workspace = (
                    np.dtype(np.complex128).itemsize
                    * (full_rows + 4 * (active_rows + 1))
                    + candidate_array_bytes
                    + 4 * active_rows * np.dtype(np.complex128).itemsize
                )
                expected_identity_evidence = (
                    26 * active_rows * np.dtype(np.complex128).itemsize
                    + 28 * 4096
                    + candidate_array_bytes
                    + 4 * full_rows * np.dtype(np.complex128).itemsize
                    + 4 * 4096
                )
                expected_evidence_total = (
                    int(donor.get("existing_evidence_bytes", 0))
                    + int(run_record.get("candidate_admission_evidence_bytes", 0))
                    + int(run_record.get("persisted_evidence_bytes", 0))
                    + expected_identity_evidence
                )
                if expected_evidence_total > 16 * 1024**3:
                    raise _CandidateNotAdmitted(
                        "V5 selected output arrays exceed the unchanged 16 GiB evidence cap by "
                        f"{expected_evidence_total - 16 * 1024**3} bytes"
                    )
                checked_facts["additional_payload_bytes"] = int(
                    checked_facts.get("additional_payload_bytes", 0)
                ) + accumulator_bytes
                checked_facts["workspace_bytes"] = max(
                    int(checked_facts.get("workspace_bytes", 0)),
                    action_and_closure_workspace,
                )
                checked_facts["v5_postbuild_reserve"] = {
                    "candidate_rows_active_plus_port": candidate_rows,
                    "candidate_full_array_bytes": candidate_array_bytes,
                    "attribution_accumulator_bytes": accumulator_bytes,
                    "attribution_accumulators": TASK41_V5_ATTRIBUTION_ACCUMULATOR_COUNT,
                    "production_action_and_global_closure_workspace_bytes": action_and_closure_workspace,
                    "projected_identity_evidence_bytes": expected_identity_evidence,
                    "projected_evidence_total_bytes": expected_evidence_total,
                    "evidence_cap_bytes": 16 * 1024**3,
                    "free_space_floor_bytes": 2 * 1024**3,
                }
                verified = {
                    int(item["cell_index"]): item
                    for item in checked_facts.get("prefix_records", ())
                    if isinstance(item, Mapping)
                    and isinstance(item.get("reference_validation"), Mapping)
                }
                if v6_actual_qmetric_mode:
                    qualification = run_record.get("candidate_prefix_qualification", {})
                    if (
                        set(verified) != set(TASK41_P0_V6_PREFIX_CELLS)
                        or qualification.get("status") != "PREFIX_QUALIFIED"
                        or qualification.get("sample_count") != 8
                        or qualification.get("geometry_witness_count", 0) < 1
                        or any(
                            item["reference_validation"].get("status") != "PASS"
                            for item in verified.values()
                        )
                        or int(
                            run_record.get(
                                "candidate_prefix_evidence_reserve_remaining_bytes", 0
                            )
                        ) != 0
                    ):
                        raise ValueError(
                            "V6 full admission requires eight passing actual-key records, "
                            "a frozen-FFCx geometry witness, and fully saved prefix evidence"
                        )
                elif set(verified) != set(TASK41_P0_V5_REFERENCE_CELLS) or any(
                    item["reference_validation"].get("coordinates_bitwise_equal") is not True
                    or item["reference_validation"].get("K_G_J_L_bitwise_equal") is not True
                    for item in verified.values()
                ):
                    raise ValueError(
                        "V5 exact prefix did not reproduce the frozen actual coordinates/K/G/J/L "
                        "for cells 26762 and 26897"
                    )
            key_inventory = checked_facts.pop("exact_key_inventory", None)
            artifact = None
            if key_inventory is not None:
                inventory_path = output_directory / "mesh_actual_exact_key_inventory.json"
                if inventory_path.exists():
                    raise FileExistsError(f"exact key inventory already exists: {inventory_path}")
                encoded = json.dumps(
                    {
                        "schema": "task41.p0.v5.mesh_actual_exact_key_inventory.v1",
                        "consumer_source_sha": consumer_contract.get("source", {}).get("sha"),
                        "campaign_window_sha256": fixed_window.sha256,
                        "form_identity": checked_facts.get("exact_form_identity"),
                        "geometry_material_identity_by_tag": checked_facts.get(
                            "geometry_material_identity_by_tag"
                        ),
                        "keys": key_inventory,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                    allow_nan=False,
                ) + "\n"
                payload_size = len(encoded.encode("utf-8"))
                current_bytes = int(donor.get("existing_evidence_bytes", 0)) + int(
                    run_record.get("candidate_admission_evidence_bytes", 0)
                )
                free_bytes = int(shutil.disk_usage(output_directory).free)
                if current_bytes + payload_size > 16 * 1024**3:
                    raise _CandidateNotAdmitted(
                        f"exact key inventory would exceed the unchanged 16 GiB evidence cap by "
                        f"{current_bytes + payload_size - 16 * 1024**3} bytes"
                    )
                if free_bytes - payload_size - scratch_reserve_bytes < 2 * 1024**3:
                    raise _CandidateNotAdmitted(
                        f"exact key inventory plus candidate scratch would breach the "
                        f"2 GiB free-space floor by "
                        f"{2 * 1024**3 - (free_bytes - payload_size - scratch_reserve_bytes)} bytes"
                    )
                _write_json_atomic(inventory_path, json.loads(encoded))
                artifact = {
                    "path": str(inventory_path.resolve()),
                    "sha256": sha256_file(inventory_path),
                    "bytes": int(inventory_path.stat().st_size),
                    "key_count": len(key_inventory),
                }
                run_record["candidate_key_inventory"] = artifact
                run_record["candidate_key_inventory_bytes"] = artifact["bytes"]
                run_record["candidate_admission_evidence_bytes"] = int(
                    run_record.get("candidate_admission_evidence_bytes", 0)
                ) + int(artifact["bytes"])
            if label == "mesh_actual_exact_full_admission":
                measurement_path = output_directory / "mesh_actual_exact_prefix_measurement.json"
                if measurement_path.exists():
                    raise FileExistsError(f"exact prefix measurement already exists: {measurement_path}")
                measurement_size_upper = len(
                    json.dumps(
                        {"schema": "task41.p0.v5.mesh_actual_exact_prefix_measurement.v1", "facts": checked_facts},
                        ensure_ascii=False,
                        sort_keys=True,
                        indent=2,
                        allow_nan=False,
                    ).encode("utf-8")
                ) + 512
                current_bytes = int(donor.get("existing_evidence_bytes", 0)) + int(
                    run_record.get("candidate_admission_evidence_bytes", 0)
                )
                free_bytes = int(shutil.disk_usage(output_directory).free)
                if current_bytes + measurement_size_upper > 16 * 1024**3:
                    raise _CandidateNotAdmitted(
                        f"prefix measurement would exceed the unchanged 16 GiB evidence cap by "
                        f"{current_bytes + measurement_size_upper - 16 * 1024**3} bytes"
                    )
                if free_bytes - measurement_size_upper < 2 * 1024**3:
                    raise _CandidateNotAdmitted(
                        f"prefix measurement would breach the 2 GiB free-space floor by "
                        f"{2 * 1024**3 - (free_bytes - measurement_size_upper)} bytes"
                    )
                measurement_payload = {
                    "schema": "task41.p0.v5.mesh_actual_exact_prefix_measurement.v1",
                    "campaign_window_sha256": fixed_window.sha256,
                    "facts": checked_facts,
                }
                _write_json_atomic(measurement_path, measurement_payload)
                run_record["candidate_prefix_measurement"] = {
                    "path": str(measurement_path.resolve()),
                    "sha256": sha256_file(measurement_path),
                    "bytes": int(measurement_path.stat().st_size),
                    "measured_misses": int(
                        checked_facts.get("measured_prefix_cache_misses", 0)
                    ),
                }
                run_record["candidate_prefix_measurement_bytes"] = int(
                    measurement_path.stat().st_size
                )
                run_record["candidate_admission_evidence_bytes"] = int(
                    run_record.get("candidate_admission_evidence_bytes", 0)
                ) + int(measurement_path.stat().st_size)
            gate_record = {
                "gate": label,
                "status": "INPUTS_RECORDED_BEFORE_ADMISSION",
                "key_inventory_artifact": artifact,
            }
            if label == "mesh_actual_exact_prefix_preflight":
                gate_record["facts"] = checked_facts
            else:
                gate_record["facts_artifact"] = run_record.get(
                    "candidate_prefix_measurement"
                )
                gate_record["facts_summary"] = {
                    "raw_key_count": checked_facts.get("raw_key_count"),
                    "oriented_key_count": checked_facts.get("oriented_key_count"),
                    "measured_prefix_cache_misses": checked_facts.get(
                        "measured_prefix_cache_misses"
                    ),
                    "projected_remaining_class_build_seconds_upper": checked_facts.get(
                        "projected_remaining_class_build_seconds_upper"
                    ),
                }
            run_record.setdefault("candidate_admission_gates", []).append(gate_record)
            _write_json_atomic(report_path, run_record)
            progress(
                {
                    "phase": "mesh_actual_exact_gate_evidence",
                    "status": "INPUTS_RECORDED_BEFORE_ADMISSION",
                    **gate_record,
                }
            )
        if args.geometry_policy == "mesh_actual_exact":
            assert fixed_window is not None
            from src.runners.task40_v10_campaign import read_campaign_state

            from src.runners.workflow_timebase import TimebaseInconsistency

            try:
                state = read_campaign_state(fixed_window, phase="numeric")
            except TimebaseInconsistency as exc:
                admission = {
                    "status": "CANDIDATE_NOT_ADMITTED",
                    "reason": f"fixed-window balance could not be verified: {type(exc).__name__}: {exc}",
                    "gate": label,
                    "facts": checked_facts,
                }
                run_record["candidate_admission"] = admission
                progress(
                    {
                        "phase": "mesh_actual_exact_candidate_admission",
                        "status": "CANDIDATE_NOT_ADMITTED",
                        **admission,
                    }
                )
                raise _CandidateNotAdmitted(admission["reason"]) from exc
            remaining = float(state["remaining_phase_seconds"])
            postbuild_reserve = math.ceil(
                float(postbuild_reserve_evidence["measured_service_parent_seconds"])
                * TASK41_P0_V5_POSTBUILD_SAFETY_FACTOR
            )
            if label == "mesh_actual_exact_prefix_preflight":
                estimated_required = (
                    TASK41_P0_V5_PREFIX_MINIMUM_SECONDS
                    + TASK41_P0_V5_TERMINATION_RESERVE_SECONDS
                )
            elif label == "mesh_actual_exact_full_admission":
                estimated_required = (
                    float(facts["projected_remaining_class_build_seconds_upper"])
                    + postbuild_reserve
                    + TASK41_P0_V5_TERMINATION_RESERVE_SECONDS
                )
            else:
                estimated_required = 0.0
            checked_facts["fixed_window_admission"] = {
                "campaign_window_sha256": fixed_window.sha256,
                "remaining_numeric_seconds": remaining,
                "estimated_required_seconds": estimated_required,
                "postbuild_two_column_action_write_checker_reserve_seconds": postbuild_reserve,
                "termination_reserve_seconds": (
                    TASK41_P0_V5_TERMINATION_RESERVE_SECONDS
                    if label == "mesh_actual_exact_full_admission"
                    else 0.0
                ),
                "source_of_postbuild_reserve": postbuild_reserve_evidence,
                "read_only_live_campaign_state": state,
            }
            if label in {"mesh_actual_exact_prefix_preflight", "mesh_actual_exact_full_admission"}:
                gate_rows = run_record.get("candidate_admission_gates", [])
                if gate_rows and gate_rows[-1].get("gate") == label:
                    gate_rows[-1]["fixed_window_admission"] = checked_facts[
                        "fixed_window_admission"
                    ]
                if label == "mesh_actual_exact_full_admission":
                    measurement_path = output_directory / "mesh_actual_exact_prefix_measurement.json"
                    _write_json_atomic(
                        measurement_path,
                        {
                            "schema": "task41.p0.v5.mesh_actual_exact_prefix_measurement.v1",
                            "campaign_window_sha256": fixed_window.sha256,
                            "facts": checked_facts,
                        },
                    )
                    run_record["candidate_prefix_measurement"].update(
                        {
                            "sha256": sha256_file(measurement_path),
                            "bytes": int(measurement_path.stat().st_size),
                        }
                    )
                    gate_rows[-1]["measurement_artifact"] = dict(
                        run_record["candidate_prefix_measurement"]
                    )
                _write_json_atomic(report_path, run_record)
                progress(
                    {
                        "phase": "mesh_actual_exact_gate_evidence",
                        "status": "LIVE_WINDOW_BALANCE_RECORDED",
                        "gate": label,
                        "fixed_window_admission": checked_facts["fixed_window_admission"],
                    }
                )
            if estimated_required > remaining:
                admission = {
                    "status": "CANDIDATE_NOT_ADMITTED",
                    "reason": "fixed-window numeric balance is below conservative remaining-work estimate",
                    "gate": label,
                    "facts": checked_facts,
                    "time_deficit_seconds": estimated_required - remaining,
                }
                run_record["candidate_admission"] = admission
                progress(
                    {
                        "phase": "mesh_actual_exact_candidate_admission",
                        "status": "CANDIDATE_NOT_ADMITTED",
                        **admission,
                    }
                )
                raise _CandidateNotAdmitted(
                    f"{label}: fixed-window deficit {estimated_required - remaining:.3f}s; "
                    f"N={facts.get('oriented_key_count')}, "
                    f"working_set={facts.get('projected_condensation_and_key_bytes_upper')} bytes"
                )
        from src.solvers.task40_v22_operator_probe import _ProbeResourceBlocked

        try:
            _checked_allocation_gate(
                label,
                checked_facts,
                resource_admission=_resource_admission,
                resource_snapshot=_resource_snapshot,
                resources=consumer_contract["resources"],
                progress=progress,
            )
        except _ProbeResourceBlocked as exc:
            if args.geometry_policy != "mesh_actual_exact" or label not in {
                "mesh_actual_exact_prefix_preflight",
                "mesh_actual_exact_full_admission",
            }:
                raise
            admission = {
                "status": "CANDIDATE_NOT_ADMITTED",
                "reason": f"resource admission rejected the exact candidate: {exc}",
                "gate": label,
                "facts": checked_facts,
                "resource_block": getattr(exc, "facts", None),
            }
            run_record["candidate_admission"] = admission
            progress(
                {
                    "phase": "mesh_actual_exact_candidate_admission",
                    "status": "CANDIDATE_NOT_ADMITTED",
                    **admission,
                }
            )
            raise _CandidateNotAdmitted(
                f"{label}: {type(exc).__name__}; N={facts.get('oriented_key_count')}, "
                f"projected_retained={facts.get('projected_retained_numeric_bytes_upper')} bytes"
            ) from exc
        if (
            args.geometry_policy == "mesh_actual_exact"
            and label == "mesh_actual_exact_full_admission"
        ):
            assert exact_attribution is not None
            exact_attribution.admit(int(donor["manifest"]["active_trace_rows"]))

    owner_result = None
    native_volume_action = None
    try:
        if args.selected_trace_star_audit:
            if fixed_window is None:
                raise RuntimeError("V8 selected trace-star audit requires the fixed numeric window")
            selected_result = _run_v8_selected_trace_star_audit(
                cfg=cfg,
                donor=donor,
                fixed_window=fixed_window,
                output_directory=output_directory,
                consumer_contract=consumer_contract,
                ffcx_c_source_path=args.ffcx_c_source,
                sha256_file=sha256_file,
                allocation_gate=allocation_gate,
                persist_array=persist_volume_array,
                progress=progress,
                checkpoint=checkpoint,
            )
            run_record.update(
                {
                    "status": "COMPLETED_SELECTED_TRACE_STAR_AUDIT",
                    "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                    "elapsed_since_worker_start_seconds": perf_counter() - started_perf,
                    "selected_trace_star_audit": selected_result,
                    "evidence_cap_bytes": 16 * 1024**3,
                    "free_space_floor_bytes": 2 * 1024**3,
                }
            )
            _write_json_atomic(report_path, run_record)
            progress(
                {
                    "phase": "selected_trace_star_audit",
                    "status": "COMPLETED",
                    "incident_cells": int(
                        selected_result["metadata"]["incident_cell_count"]
                    ),
                    "reconstructed_cells": sum(
                        bool(cell.get("is_target_row_incident"))
                        and any(
                            role.get("role") == "candidate"
                            and role.get("source") == "RECONSTRUCTED_SELECTED_CELL"
                            for role in cell.get("roles", [])
                        )
                        for cell in selected_result[
                            "local_numeric_cell_identity_and_artifacts"
                        ]
                    ),
                }
            )
            return 0
        if args.geometry_pair_only:
            probe = _run_geometry_pair_probe(
                cfg=cfg,
                donor=donor,
                source_report_path=args.source_report,
                consumer_contract=consumer_contract,
                output_directory=output_directory,
                persist_array=persist_volume_array,
                allocation_gate=allocation_gate,
                progress=progress,
                sha256_file=sha256_file,
            )
            actual_cumulative_bytes = int(probe["prior_evidence_bytes"]) + int(
                run_record.get("persisted_evidence_bytes", 0)
            )
            if actual_cumulative_bytes > 16 * 1024**3:
                raise MemoryError("Task41 V4 geometry-pair output exceeded the unchanged 16 GiB cap")
            run_record.update(
                {
                    "status": "COMPLETED_GEOMETRY_PAIR_PROBE",
                    "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                    "elapsed_since_worker_start_seconds": perf_counter() - started_perf,
                    "geometry_pair_probe": probe,
                    "evidence_cap_bytes": 16 * 1024**3,
                    "free_space_floor_bytes": 2 * 1024**3,
                }
            )
            _write_json_atomic(report_path, run_record)
            progress({"phase": "v4_geometry_pair_probe", "status": "COMPLETED"})
            return 0
        donor["prior_new_evidence_bytes"] = int(
            run_record.get("candidate_admission_evidence_bytes", 0)
        )

        def validate_exact_prefix_cell(
            cell_index: int,
            coordinates: np.ndarray,
            blocks: Mapping[str, np.ndarray],
            context: Mapping[str, Any],
        ) -> Mapping[str, Any]:
            if not v6_actual_qmetric_mode:
                if geometry_reference is None or cell_index not in geometry_reference["cells"]:
                    return {}
                reference = geometry_reference["cells"][cell_index]
                coordinates_equal = np.array_equal(
                    np.asarray(coordinates, dtype=np.float64), reference["coordinates"]
                )
                block_equal = all(
                    np.array_equal(np.asarray(blocks[name]), reference["blocks"][name])
                    for name in ("K", "G", "J", "L")
                )
                if not coordinates_equal or not block_equal:
                    mismatches = [
                        name
                        for name in ("K", "G", "J", "L")
                        if not np.array_equal(np.asarray(blocks[name]), reference["blocks"][name])
                    ]
                    raise ValueError(
                        f"V5 exact prefix differs from frozen V4 actual evidence for cell {cell_index}: "
                        f"coordinates_equal={coordinates_equal}, block_mismatches={mismatches}"
                    )
                return {
                    "cell_index": int(cell_index),
                    "reference_report_sha256": geometry_reference["sha256"],
                    "coordinates_bitwise_equal": True,
                    "coordinates_sha256": reference["coordinates_sha256"],
                    "K_G_J_L_bitwise_equal": True,
                    "block_sha256": dict(reference["block_sha256"]),
                }

            from src.solvers.hcurl_assembly_time_condensation import (
                _orient_cell_tensor,
                _unorient_cell_tensor,
            )
            from src.solvers.task41_actual_qmetric_blocked_gram import (
                V6_PREFIX_SAMPLE_CELL_INDICES,
            )

            if tuple(V6_PREFIX_SAMPLE_CELL_INDICES) != TASK41_P0_V6_PREFIX_CELLS:
                raise RuntimeError("V6 runner and evaluator prefix sample inventories differ")
            if cell_index not in TASK41_P0_V6_PREFIX_CELLS:
                raise ValueError(f"V6 prefix received non-inventory cell {cell_index}")
            evaluator = context.get("raw_tensor_evaluator")
            if evaluator is None or not callable(
                getattr(evaluator, "run_original_kernel_geometry_oracle", None)
            ):
                raise RuntimeError("V6 exact builder did not supply its bound oracle evaluator")
            coordinate_array = np.asarray(coordinates)
            candidate_raw = np.asarray(context["raw_tensor"], dtype=np.complex128)
            candidate_oriented = np.asarray(context["oriented_tensor"], dtype=np.complex128)
            coordinates_sha = hashlib.sha256(
                np.ascontiguousarray(coordinate_array).tobytes()
            ).hexdigest()
            sample_prefix = f"task41_v6_prefix_cell{cell_index}"
            record: dict[str, Any] = {
                "cell_index": int(cell_index),
                "tag": int(context["tag"]),
                "permutation": int(context["permutation"]),
                "coordinates_shape": list(coordinate_array.shape),
                "coordinates_dtype": str(coordinate_array.dtype),
                "coordinates_sha256": coordinates_sha,
                "coordinates_bitwise_identity_passed": bool(
                    coordinate_array.dtype == np.dtype(np.float64)
                    and coordinate_array.shape == (8, 3)
                    and coordinate_array.flags.c_contiguous
                ),
                "candidate_build_seconds": float(context["candidate_build_seconds"]),
                "candidate_artifacts": {},
                "reference_artifacts": {},
                "local_RTS_artifacts": {},
                "local_action_comparisons": [],
                "status": "IN_PROGRESS",
            }
            record_finished = False

            def checkpoint_prefix_record() -> None:
                qualification = run_record.setdefault(
                    "candidate_prefix_qualification",
                    {
                        "schema": "task41.p0.v6.actual_qmetric_prefix_qualification.v1",
                        "status": "PREFIX_QUALIFICATION_PENDING",
                        "required_sample_cell_indices": list(TASK41_P0_V6_PREFIX_CELLS),
                        "records": [],
                    },
                )
                stored_records = qualification.setdefault("records", [])
                existing_index = next(
                    (
                        index
                        for index, item in enumerate(stored_records)
                        if item.get("cell_index") == cell_index
                    ),
                    None,
                )
                if existing_index is None:
                    stored_records.append(dict(record))
                else:
                    stored_records[existing_index] = dict(record)
                qualification["sample_count"] = len(stored_records)
                qualification["required_sample_count"] = len(TASK41_P0_V6_PREFIX_CELLS)
                qualification.setdefault("geometry_witness_count", 0)
                qualification.setdefault("full_admission_eligible", False)
                _write_json_atomic(report_path, run_record)

            def persist_reference_artifact(role: str, array: np.ndarray) -> None:
                artifact_name = f"{sample_prefix}_{role}"
                record["reference_artifacts"][role] = {
                    "name": artifact_name,
                    **persist_volume_array(artifact_name, array),
                }
                checkpoint_prefix_record()

            def finish_prefix_record() -> None:
                nonlocal record_finished
                if record_finished:
                    return
                evaluator.record_prefix_qualification(record)
                qualification = run_record.setdefault(
                    "candidate_prefix_qualification",
                    {
                        "schema": "task41.p0.v6.actual_qmetric_prefix_qualification.v1",
                        "required_sample_cell_indices": list(TASK41_P0_V6_PREFIX_CELLS),
                        "records": [],
                    },
                )
                stored_records = qualification.setdefault("records", [])
                existing_index = next(
                    (
                        index
                        for index, item in enumerate(stored_records)
                        if item.get("cell_index") == cell_index
                    ),
                    None,
                )
                if existing_index is None:
                    stored_records.append(dict(record))
                else:
                    stored_records[existing_index] = dict(record)
                audit = evaluator.prefix_qualification_audit()
                qualification.update(
                    {
                        "status": audit["status"],
                        "sample_count": audit["sample_count"],
                        "required_sample_count": audit["required_sample_count"],
                        "geometry_witness_count": audit["geometry_witness_count"],
                        "full_admission_eligible": audit["full_admission_eligible"],
                    }
                )
                qualification["original_kernel_oracle_inventory"] = {
                    "execution_count": len(evaluator.original_kernel_oracle_records),
                    "maximum_additional_executions": 6,
                    "records": [
                        dict(item) for item in evaluator.original_kernel_oracle_records
                    ],
                }
                saved_action_cells = [
                    item
                    for item in stored_records
                    if item.get("source") == "V4_SAVED_ACTUAL_BLOCKS"
                ]
                incident: dict[str, dict[str, Any]] = {}
                for saved_cell in saved_action_cells:
                    for action in saved_cell.get("local_action_comparisons", ()):
                        key = f"col{action['column']}_{action['state']}"
                        row = incident.setdefault(
                            key,
                            {
                                "column": int(action["column"]),
                                "state": str(action["state"]),
                                "cell_count": 0,
                                "reference_sum": 0.0 + 0.0j,
                                "candidate_sum": 0.0 + 0.0j,
                                "frozen_denominator": float(action["frozen_denominator"]),
                            },
                        )
                        row["cell_count"] += 1
                        row["reference_sum"] += complex(*action["selected_row_reference"])
                        row["candidate_sum"] += complex(*action["selected_row_candidate"])
                qualification["original_failed_row_incident_contributions"] = [
                    {
                        "column": row["column"],
                        "state": row["state"],
                        "cell_count": row["cell_count"],
                        "reference_sum": [row["reference_sum"].real, row["reference_sum"].imag],
                        "candidate_sum": [row["candidate_sum"].real, row["candidate_sum"].imag],
                        "difference_abs": abs(row["candidate_sum"] - row["reference_sum"]),
                        "difference_over_frozen_denominator": (
                            abs(row["candidate_sum"] - row["reference_sum"])
                            / row["frozen_denominator"]
                        ),
                        "frozen_denominator": row["frozen_denominator"],
                    }
                    for _key, row in sorted(incident.items())
                ]
                qualification["global_b_t_accumulation"] = (
                    "not_performed_by_local_prefix_qualification"
                )
                if audit["status"] == "PREFIX_QUALIFIED":
                    reserve_remaining = int(
                        run_record.get(
                            "candidate_prefix_evidence_reserve_remaining_bytes", 0
                        )
                    )
                    run_record["candidate_prefix_evidence_reserve_released_bytes"] = (
                        int(
                            run_record.get(
                                "candidate_prefix_evidence_reserve_released_bytes", 0
                            )
                        )
                        + reserve_remaining
                    )
                    run_record["candidate_prefix_evidence_reserve_remaining_bytes"] = 0
                _write_json_atomic(report_path, run_record)
                record_finished = True

            try:
                if not record["coordinates_bitwise_identity_passed"]:
                    raise ValueError("V6 prefix coordinates are not original contiguous float64 (8, 3) bytes")
                for role, array in (
                    ("candidate_raw_tensor", candidate_raw),
                    ("candidate_oriented_tensor", candidate_oriented),
                    ("candidate_coordinates", coordinate_array),
                ):
                    artifact_name = f"{sample_prefix}_{role}"
                    record["candidate_artifacts"][role] = {
                        "name": artifact_name,
                        **persist_volume_array(artifact_name, array),
                    }
                checkpoint_prefix_record()

                if cell_index in TASK41_P0_V5_REFERENCE_CELLS:
                    reference = geometry_reference["cells"][cell_index]
                    coordinates_equal = np.array_equal(
                        coordinate_array, reference["coordinates"]
                    )
                    if (
                        not coordinates_equal
                        or int(context["tag"]) != reference["cell_tag"]
                        or int(context["permutation"]) != reference["cell_permutation"]
                    ):
                        raise ValueError(
                            f"V6 saved V4 cell identity differs at cell {cell_index}: "
                            f"coordinates_equal={coordinates_equal}, "
                            f"tag={context['tag']}/{reference['cell_tag']}, "
                            f"permutation={context['permutation']}/{reference['cell_permutation']}"
                        )
                    reference_blocks = reference["blocks"]
                    allocation_gate(
                        "task41_v6_prefix_saved_reference_reconstruction",
                        {
                            "additional_payload_bytes": 0,
                            "workspace_bytes": int(
                                4 * candidate_oriented.nbytes
                                + 2 * candidate_raw.nbytes
                            ),
                            "cell_index": int(cell_index),
                            "reference_source": "frozen_V4_saved_actual_KGJL_blocks",
                        },
                    )
                    reference_oriented = _v6_reconstruct_oriented_tensor(
                        reference_blocks,
                        np.asarray(context["interior_positions"]),
                        np.asarray(context["trace_positions"]),
                        candidate_oriented.shape[0],
                    )
                    reference_raw = reference_oriented.copy()
                    _unorient_cell_tensor(
                        context["element"],
                        reference_raw,
                        np.asarray([context["permutation"]], dtype=np.uint32),
                    )
                    record["source"] = "V4_SAVED_ACTUAL_BLOCKS"
                    record["reference_report_sha256"] = geometry_reference["sha256"]
                    record["reference_coordinates_sha256"] = reference["coordinates_sha256"]
                    record["reference_block_sha256"] = dict(reference["block_sha256"])
                    record["reference_tag"] = int(reference["cell_tag"])
                    record["reference_permutation"] = int(reference["cell_permutation"])
                    geometry_witness = {
                        "status": "NOT_REQUIRED_V4_SAVED_ACTUAL_BLOCKS",
                        "source_report_sha256": geometry_reference["sha256"],
                        "coordinates_bitwise_equal": True,
                    }
                    persist_reference_artifact("reference_raw_tensor", reference_raw)
                    persist_reference_artifact(
                        "reference_oriented_tensor", reference_oriented
                    )
                else:
                    record["source"] = "ORIGINAL_FFCX_KERNEL_ORACLE"
                    oracle = evaluator.run_original_kernel_geometry_oracle(
                        int(context["tag"]),
                        coordinate_array,
                        0,
                        512,
                        allocation_gate=allocation_gate,
                        candidate_tensor=candidate_raw,
                        candidate_build_seconds=float(context["candidate_build_seconds"]),
                    )
                    geometry_witness = {
                        "status": oracle["geometry_comparison"]["status"],
                        "q_begin": int(oracle["q_begin"]),
                        "q_end": int(oracle["q_end"]),
                        "point_count": int(oracle["geometry_comparison"]["point_count"]),
                        "field_count": int(oracle["geometry_comparison"]["field_count"]),
                        "field_names_sha256": oracle["geometry_comparison"]["field_names_sha256"],
                        "max_abs": float(oracle["geometry_comparison"]["max_abs"]),
                        "relative_frobenius": float(oracle["geometry_comparison"]["relative_frobenius"]),
                        "compile_audit": dict(oracle["compile_audit"]),
                    }
                    record["original_kernel_oracle_timing"] = {
                        "source_generation_seconds": float(oracle["compile_audit"].get("source_generation_seconds", 0.0)),
                        "compiler_seconds": float(oracle["compile_audit"].get("compiler_seconds", 0.0)),
                        "kernel_call_seconds": float(oracle["kernel_call_seconds"]),
                        "output_allocation_seconds": float(oracle["output_allocation_seconds"]),
                    }
                    reference_raw = np.asarray(oracle["tensor"], dtype=np.complex128)
                    persist_reference_artifact("reference_raw_tensor", reference_raw)
                    reference_oriented = reference_raw.copy()
                    _orient_cell_tensor(
                        context["element"],
                        reference_oriented,
                        np.asarray([context["permutation"]], dtype=np.uint32),
                    )
                    persist_reference_artifact(
                        "reference_oriented_tensor", reference_oriented
                    )
                    interior = np.asarray(context["interior_positions"], dtype=np.int64)
                    trace = np.asarray(context["trace_positions"], dtype=np.int64)
                    reference_blocks = {
                        "K": reference_oriented[np.ix_(interior, interior)],
                        "G": reference_oriented[np.ix_(interior, trace)],
                        "J": reference_oriented[np.ix_(trace, interior)],
                        "L": reference_oriented[np.ix_(trace, trace)],
                    }
                record["geometry_witness"] = geometry_witness
                checkpoint_prefix_record()
                raw_metrics = _v6_screen_metrics(candidate_raw, reference_raw)
                oriented_metrics = _v6_screen_metrics(candidate_oriented, reference_oriented)
                block_metrics = {
                    name: _v6_screen_metrics(blocks[name], reference_blocks[name])
                    for name in ("K", "G", "J", "L")
                }
                reference_rts, reference_lu = _v6_condense_blocks(reference_blocks)
                candidate_rts = {
                    name: np.asarray(context[name], dtype=np.complex128)
                    for name in ("R", "T", "S")
                }
                candidate_defects = _v6_condensation_defects(blocks, candidate_rts)
                rts_metrics = {
                    name: _v6_screen_metrics(candidate_rts[name], reference_rts[name])
                    for name in ("R", "T", "S")
                }
                for role, rts in (("reference", reference_rts), ("candidate", candidate_rts)):
                    for name, array in rts.items():
                        artifact_name = f"{sample_prefix}_{role}_{name}"
                        record["local_RTS_artifacts"][f"{role}_{name}"] = {
                            "name": artifact_name,
                            **persist_volume_array(artifact_name, array),
                        }
                for name, array in block_metrics.items():
                    del name, array
                record["comparisons"] = {
                    "raw_tensor": raw_metrics,
                    "oriented_tensor": oriented_metrics,
                    "K_G_J_L": block_metrics,
                    "R_T_S": rts_metrics,
                    "reference_condensation_defects_relative": reference_lu["condensation_defects_relative"],
                    "candidate_condensation_defects_relative": candidate_defects,
                    "condensation_defects_classification": "diagnostic_only",
                    "strict_lu": {
                        "reference": reference_lu["strict_lu_identity_relative_defect"],
                        "candidate": float(context["strict_lu_residual"]),
                        "relative_limit": 1.0e-11,
                        "passed": (
                            reference_lu["strict_lu_identity_relative_defect"] <= 1.0e-11
                            and float(context["strict_lu_residual"]) <= 1.0e-11
                        ),
                    },
                }
                local_comparisons_pass = (
                    raw_metrics["status"] == "PASS"
                    and oriented_metrics["status"] == "PASS"
                    and all(item["status"] == "PASS" for item in block_metrics.values())
                    and all(item["status"] == "PASS" for item in rts_metrics.values())
                    and record["comparisons"]["strict_lu"]["passed"]
                    and all(
                        np.isfinite(value) and value >= 0.0
                        for defect_map in (
                            reference_lu["condensation_defects_relative"],
                            candidate_defects,
                        )
                        for value in defect_map.values()
                    )
                    and geometry_witness["status"] in {
                        "BITWISE_EQUAL",
                        "NOT_REQUIRED_V4_SAVED_ACTUAL_BLOCKS",
                    }
                )

                if cell_index in TASK41_P0_V5_REFERENCE_CELLS:
                    interior = np.asarray(context["interior_positions"], dtype=np.int64)
                    trace = np.asarray(context["trace_positions"], dtype=np.int64)
                    original_dofs = np.asarray(context["original_dofs"], dtype=np.int64)
                    active_ids = np.asarray(context["active_ids"], dtype=np.int64)
                    expansion = context["trace_expansion"]
                    for column_index, column in enumerate(donor["columns"]):
                        field_inputs = [("known", column["known_field"])] + [
                            (str(state["label"]), state["storage"])
                            for state in column["states"]
                        ]
                        for state_label, full_values in field_inputs:
                            local_values = np.asarray(full_values, dtype=np.complex128)[original_dofs]
                            reference_action = reference_oriented @ local_values
                            candidate_action = candidate_oriented @ local_values
                            reference_action_name = (
                                f"{sample_prefix}_col{column_index}_{state_label}_reference_local_action"
                            )
                            candidate_action_name = (
                                f"{sample_prefix}_col{column_index}_{state_label}_candidate_local_action"
                            )
                            action_record: dict[str, Any] = {
                                "column": int(column_index),
                                "state": state_label,
                                "reference_artifact": {
                                    "name": reference_action_name,
                                    **persist_volume_array(reference_action_name, reference_action),
                                },
                                "candidate_artifact": {
                                    "name": candidate_action_name,
                                    **persist_volume_array(candidate_action_name, candidate_action),
                                },
                                **_v6_saved_local_action_diagnostic(
                                    reference_action,
                                    candidate_action,
                                    frozen_denominators=TASK41_V5_FROZEN_DENOMINATORS,
                                    column_index=column_index,
                                    trace_positions=trace,
                                    active_ids=active_ids,
                                    trace_expansion=expansion,
                                    selected_active_row=TASK41_P0_V4_SELECTED_ACTIVE_ROW,
                                ),
                            }
                            record["local_action_comparisons"].append(action_record)

                record["status"] = "PASS" if local_comparisons_pass else "FAIL"
                record["admission_eligible"] = bool(local_comparisons_pass)
                finish_prefix_record()
                if not local_comparisons_pass:
                    raise ValueError(
                        f"V6 prefix local qualification failed at cell {cell_index}; "
                        "raw evidence and comparison metrics were persisted before rejection"
                    )
                return {
                    "status": "PASS",
                    "cell_index": int(cell_index),
                    "source": record["source"],
                    "coordinates_bitwise_equal": True,
                    "raw_tensor": raw_metrics,
                    "oriented_tensor": oriented_metrics,
                    "K_G_J_L": block_metrics,
                    "R_T_S": rts_metrics,
                    "strict_lu_passed": True,
                    "geometry_witness": geometry_witness,
                }
            except Exception as exc:
                if not record_finished:
                    record.update(
                        {
                            "status": "FAIL",
                            "admission_eligible": False,
                            "error": {"type": type(exc).__name__, "message": str(exc)},
                        }
                    )
                    finish_prefix_record()
                raise

        owner_result = build_task41_v4_volume_only_owner(
            cfg,
            donor,
            output_directory,
            allocation_gate=allocation_gate,
            progress_callback=progress,
            persist_array=persist_volume_array,
            geometry_policy=args.geometry_policy,
            raw_tensor_evaluator_kind=args.raw_tensor_evaluator,
            ffcx_c_source_path=args.ffcx_c_source,
            required_prefix_cells=(
                TASK41_P0_V6_PREFIX_CELLS
                if v6_actual_qmetric_mode
                else TASK41_P0_V5_REFERENCE_CELLS
                if args.geometry_policy == "mesh_actual_exact"
                else ()
            ),
            prefix_cell_validator=(
                validate_exact_prefix_cell
                if args.geometry_policy == "mesh_actual_exact"
                else None
            ),
            exact_cell_observer=(
                exact_attribution.observe
                if exact_attribution is not None
                else None
            ),
        )
        donor["prior_new_evidence_bytes"] += int(
            owner_result["audit"]["evidence_bytes_added"]
        )
        donor["attribution"]["local_class_identities"] = owner_result["audit"]["local_class_identities"]
        native_volume_apply = None
        if args.geometry_policy == "mesh_actual_exact":
            from mpi4py import MPI
            from petsc4py import PETSc
            from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
                _build_split_volume_action,
            )
            from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import (
                SAME_MESH_JIT_OPTIONS,
            )

            levels = owner_result["levels"]
            full_rows = int(owner_result["condensed"].full_rows)
            allocation_gate(
                "v5_candidate_recovery_native_action_preflight",
                {
                    "additional_payload_bytes": 0,
                    "workspace_bytes": 3 * full_rows * np.dtype(np.complex128).itemsize,
                    "native_volume_action_calls": 2,
                    "candidate_recovery_vectors": 2,
                    "port_or_surface_action": False,
                },
            )
            progress(
                {
                    "phase": "v5_candidate_recovery_native_action_build",
                    "status": "STARTED",
                    "action": "existing split volume-only form action",
                }
            )
            native_volume_action = _build_split_volume_action(
                levels["mesh_data"],
                cfg,
                levels["spaces"][6],
                levels["floquets"][6],
                jit_options=dict(SAME_MESH_JIT_OPTIONS),
            )
            native_apply_count = 0

            def native_volume_apply(values: np.ndarray) -> np.ndarray:
                nonlocal native_apply_count
                if native_apply_count >= 2:
                    raise RuntimeError("V5 recovery exceeded its two native volume-only action calls")
                source_values = np.asarray(values, dtype=np.complex128)
                if source_values.shape != (full_rows,) or not np.isfinite(source_values).all():
                    raise ValueError("V5 candidate recovery storage has an invalid full-space layout")
                source = PETSc.Vec().createWithArray(source_values, comm=MPI.COMM_SELF)
                try:
                    result = native_volume_action.apply(source)
                    # The split action owns and reuses its returned work Vec; copy
                    # the values and keep that Vec alive for the next column.
                    output = np.array(
                        result.getArray(readonly=True), dtype=np.complex128, copy=True
                    )
                finally:
                    source.destroy()
                native_apply_count += 1
                return output

            progress(
                {
                    "phase": "v5_candidate_recovery_native_action_build",
                    "status": "COMPLETED",
                }
            )
        candidate_evaluator_audit = owner_result["condensed"].build_audit.get(
            "raw_tensor_evaluator"
        )
        candidate_cache_identity = None
        if v6_actual_qmetric_mode:
            if not isinstance(candidate_evaluator_audit, Mapping):
                raise RuntimeError("V6 volume owner omitted its raw-tensor evaluator audit")
            candidate_cache_identity = candidate_evaluator_audit.get("cache_identity")
            if not isinstance(candidate_cache_identity, str) or not candidate_cache_identity:
                raise RuntimeError("V6 volume owner omitted its dynamic evaluator cache identity")
        identity_report = audit_task41_v4_volume_identity(
            owner_result["condensed"],
            donor,
            allocation_gate=allocation_gate,
            progress_callback=progress,
            persist_array=persist_volume_array,
            output_directory=output_directory,
            native_volume_apply=native_volume_apply,
            artifact_prefix=candidate_artifact_prefix,
            candidate_identity=candidate_identity,
            candidate_cache_identity=candidate_cache_identity,
        )
        if v6_actual_qmetric_mode:
            assert isinstance(candidate_evaluator_audit, Mapping)
            identity_report["candidate_evaluator_audit"] = dict(candidate_evaluator_audit)
            identity_report["candidate_evaluator_cache_identity"] = candidate_cache_identity
            if exact_attribution is not None:
                exact_attribution.candidate_cache_identity = candidate_cache_identity
        if exact_attribution is not None:
            array_records = {
                str(item["name"]): item
                for item in run_record.get("persisted_evidence_arrays", ())
                if isinstance(item, Mapping) and item.get("name")
            }
            candidate_evidence_prefix = (
                "task41_p0_v6_qmetric_candidate"
                if v6_actual_qmetric_mode
                else "task41_p0_v5_candidate"
            )
            p6_record = array_records.get(f"{candidate_evidence_prefix}_full_p6")
            reduced_record = array_records.get(
                f"{candidate_evidence_prefix}_full_reduced_rhs"
            )
            if p6_record is None or reduced_record is None:
                raise RuntimeError("V5 full-action arrays were not persisted before attribution")
            active_rows = int(owner_result["condensed"].active_rows)
            d_volume_records = [
                array_records.get(f"task41_v4_d_volume_trace_col{column_index}")
                for column_index in range(2)
            ]
            if any(record is None for record in d_volume_records):
                raise RuntimeError("V7 saved volume-defect arrays were not persisted before attribution")
            candidate_d_volume_columns = [
                np.load(record["path"], mmap_mode="r", allow_pickle=False)
                for record in d_volume_records
                if record is not None
            ]
            if any(
                values.shape != (active_rows,)
                or values.dtype != np.dtype(np.complex128)
                for values in candidate_d_volume_columns
            ):
                raise ValueError("V7 saved volume-defect arrays have invalid layouts")
            candidate_p6 = np.load(
                p6_record["path"], mmap_mode="r", allow_pickle=False
            )
            candidate_reduced = np.load(
                reduced_record["path"], mmap_mode="r", allow_pickle=False
            )
            identity_report["global_geometry_native_elimination_attribution"] = (
                exact_attribution.finalize(
                    candidate_p6,
                    candidate_reduced,
                    active_rows=active_rows,
                    candidate_d_volume_columns=candidate_d_volume_columns,
                    persist_array=persist_volume_array,
                )
            )
            del candidate_p6, candidate_reduced, candidate_d_volume_columns
        candidate_gate = identity_report.get("candidate_full_action_gate")
        action_candidate_status = (
            str(candidate_gate.get("status"))
            if args.geometry_policy == "mesh_actual_exact" and candidate_gate is not None
            else None
        )
        recovery_gate = identity_report.get("candidate_recovery_gate")
        candidate_status = (
            "PASS"
            if args.geometry_policy == "mesh_actual_exact"
            and action_candidate_status == "PASS"
            and isinstance(recovery_gate, Mapping)
            and recovery_gate.get("status") == "PASS"
            else "ACTUAL_COORDINATES_INSUFFICIENT"
            if args.geometry_policy == "mesh_actual_exact"
            else None
        )
        if args.geometry_policy == "mesh_actual_exact" and candidate_status is None:
            raise RuntimeError("exact-geometry audit did not produce full-action and recovery gates")
        attribution_status = (
            identity_report.get("global_geometry_native_elimination_attribution", {}).get(
                "global_closure_status"
            )
            if args.geometry_policy == "mesh_actual_exact"
            else None
        )
        if args.geometry_policy == "mesh_actual_exact" and attribution_status is None:
            raise RuntimeError("exact-geometry audit did not produce the global attribution closure")
        if args.geometry_policy == "mesh_actual_exact":
            run_status = (
                "CANDIDATE_NUMERICAL_PASS_CHECKER_PENDING"
                if candidate_status == "PASS"
                else "ACTUAL_COORDINATES_INSUFFICIENT"
            )
            run_record["candidate_attribution_status"] = attribution_status
            run_record["independent_checker_status"] = "NOT_RUN"
            run_record["candidate_numeric_status"] = candidate_status
        else:
            run_status = "COMPLETED"
        run_record.update(
            {
                "status": run_status,
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_since_worker_start_seconds": perf_counter() - started_perf,
                "owner_audit": owner_result["audit"],
                "identity_audit": identity_report,
                "evidence_cap_bytes": 16 * 1024**3,
                "free_space_floor_bytes": 2 * 1024**3,
            }
        )
        _write_json_atomic(report_path, run_record)
        progress(
            {
                "phase": (
                    "v6_actual_qmetric_full_action"
                    if v6_actual_qmetric_mode
                    else "v5_mesh_actual_exact_full_action"
                    if args.geometry_policy == "mesh_actual_exact"
                    else "v4_volume_only_attribution"
                ),
                "status": (
                    "PASS_CHECKER_PENDING"
                    if candidate_status == "PASS"
                    else "ACTUAL_COORDINATES_INSUFFICIENT"
                    if candidate_status is not None
                    else "COMPLETED"
                ),
            }
        )
        # A complete exact-geometry report, including a numerical negative, is
        # worker-success evidence so the independent checker can run. The
        # service records scientific acceptance separately from audit completion.
        return 0
    except Exception as exc:
        if isinstance(exc, _CandidateNotAdmitted) and "candidate_admission" not in run_record:
            last_gate = (
                run_record.get("candidate_admission_gates", [])[-1]
                if run_record.get("candidate_admission_gates")
                else {}
            )
            run_record["candidate_admission"] = {
                "status": "CANDIDATE_NOT_ADMITTED",
                "reason": str(exc),
                "gate": last_gate.get("gate"),
                "gate_evidence": last_gate,
            }
        failure_status = (
            "CANDIDATE_NOT_ADMITTED"
            if isinstance(exc, _CandidateNotAdmitted)
            else "FAILED_SELECTED_TRACE_STAR_EVIDENCE_RETAINED"
            if args.selected_trace_star_audit
            else
            "FAILED_GEOMETRY_PAIR_EVIDENCE_RETAINED"
            if args.geometry_pair_only
            else "FAILED_RAW_EVIDENCE_RETAINED"
        )
        run_record.update(
            {
                "status": failure_status,
                "failed_at_utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_since_worker_start_seconds": perf_counter() - started_perf,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
        )
        _write_json_atomic(report_path, run_record)
        progress(
            {
                "phase": (
                    "v8_selected_trace_star_audit"
                    if args.selected_trace_star_audit
                    else "v4_geometry_pair_probe"
                    if args.geometry_pair_only
                    else "v4_volume_only_attribution"
                ),
                "status": "FAILED",
                "error": str(exc),
            }
        )
        return 3
    finally:
        if native_volume_action is not None:
            native_volume_action.destroy()
        if owner_result is not None:
            owner_result["condensed"].destroy()


if __name__ == "__main__":
    raise SystemExit(main())
