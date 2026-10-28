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
TASK41_P0_V11_METADATA_ACTIVE_ROW = 87_567
TASK41_P0_V11_METADATA_ORIGINAL_ROW = 250_113
TASK41_P0_V11_METADATA_REPORT_SHA256 = (
    "332baa3a5253a8322b56615c7fe087e401f909c3c889fa048fccc3f9f2b9fcd3"
)
TASK41_P0_V11_METADATA_SERVICE_RECEIPT_SHA256 = (
    "ccf9c796ed38d21180e5336d59b8610a62fb869fc271dc3703a87cedb986eb4c"
)
TASK41_P0_V11_METADATA_CONSUMER_SOURCE_SHA = (
    "967ad08d7da75ff8fa4e49bd63ed9abe53469d46"
)
TASK41_P0_V11_METADATA_CONSUMER_CONTRACT_SHA256 = (
    "af27a07502f72f5d3d1effecf98bda21f09e95cca230278e05ed1a63eeaf8931"
)
TASK41_P0_V11_METADATA_CONSUMER_CONTRACT_RELATIVE = Path(
    "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/"
    "p0_b0_controller/execution_contract_source_967ad08d7da75ff8fa4e49bd63ed9abe53469d46.json"
)
TASK41_P0_V11_METADATA_WINDOW_SHA256 = (
    "bc646b17157eed567e2c5391df79e4eda681ab4028f9e86901e8c7fcfd9222b4"
)
TASK41_P0_V11_GLOBAL_ROW_COUNT = 5_752_120
TASK41_P0_V11_V9_COMPACT_REPORT_SHA256 = (
    "e4db4e42b8a4f3b407ed0b00add8029f7e066aad6c38a2945d60e33ffbde7d93"
)
TASK41_P0_V11_FFCX_C_SOURCE_SHA256 = (
    "d3302fba22074b755ac3b7d4a0b361af926ae7801aac25a7f1cd1d69cbeb9f03"
)
TASK41_P0_V11_SELECTED_CELLS = (360, 446)
TASK41_P0_V17_SELECTED_CELLS = (7873, 8014)
TASK41_P0_V17_ACTIVE_ROW = 1_622_464
TASK41_P0_V17_ORIGINAL_ROW = 5_218_672
TASK41_P0_V17_V16_MANIFEST_SHA256 = (
    "3fae0774772550faf173444e9c5aedd608212b430957ae591ffdb31daabeb215"
)
TASK41_P0_V17_V16_MANIFEST_RELATIVE = Path(
    "task41_p0_saved_diagnostics_6h/"
    "3d22e02f713c4a68c79759b2c5cb7cbcec693b7b3277ad98b529838008e38beb/"
    "saved_vector_distribution/attempt05.service/"
    "task41_p0_v16_metadata_bound_manifest.json"
)
TASK41_P0_V17_FFCX_C_SOURCE_RELATIVE = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/"
    "jit_cache/fenics/libffcx_forms_2f92c03a20c09db3cb8f0382bec2294daa94ab16.c"
)
TASK41_P0_V11_V9_FULL_ACTION_ARRAY_SHA256 = (
    "740eae4b52d810060e334e96a62979626a7f13fe0464cf86f87670bd98c9eaac"
)
TASK41_P0_V11_V9_REDUCED_RHS_ARRAY_SHA256 = (
    "ac5a86b9c06656d6d8461ec20db973ea8df0c6635a42af9d79d207b44362a55b"
)
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
    selected_v6_names: set[str] | None = None,
    load_v7_payloads: bool = True,
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
    if selected_v6_names is not None:
        selected_v6_names = {str(name) for name in selected_v6_names}
        if not selected_v6_names <= index_by_name.keys():
            raise ValueError("selected V6 input names are absent from the frozen hash index")
        required_v6_names = selected_v6_names
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
        if load_v7_payloads:
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
        "v7_payloads_loaded": bool(load_v7_payloads),
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
    candidate_only: bool = False,
    artifact_prefix_template: str = "task41_p0_v8_selected_cell{cell_index}_{role}",
    checkpoint: Any | None = None,
) -> dict[str, dict[str, Any]]:
    """Run and persist selected-cell production-role paths.

    The default preserves the historical candidate-plus-reference audit.  A
    candidate-only replay is useful when the saved metadata already identifies
    the incident cells and the first required product is the actual candidate
    tensor and its same-source R/T/S/LU artifacts; it avoids compiling the
    expensive reference FFCx kernel before those products are durable.
    """
    from src.solvers.hcurl_assembly_time_condensation import (
        _tabulate_volume_audit_path,
        condense_selected_volume_tensor,
    )

    coordinates = np.ascontiguousarray(
        row["actual_geometry_coordinates"], dtype=np.float64
    )
    role_sets: dict[str, dict[str, Any]] = {}
    role_evaluators = (
        (("candidate", candidate_evaluator),)
        if candidate_only
        else (("candidate", candidate_evaluator), ("reference", None))
    )
    for role, raw_evaluator in role_evaluators:
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
        artifact_prefix = artifact_prefix_template.format(
            cell_index=int(cell_index), role=role
        )
        artifacts: dict[str, dict[str, Any]] = {}

        def persist_artifact(name: str, value: np.ndarray) -> None:
            artifact_name = f"{artifact_prefix}_{name}"
            record = {"name": artifact_name, **persist_array(artifact_name, value)}
            artifacts[name] = record
            if checkpoint is not None:
                checkpoint(
                    "selected_cell_artifact_persisted",
                    {
                        "schema": "task41.p0.selected_cell_artifact_checkpoint.v1",
                        "cell_index": int(cell_index),
                        "role": role,
                        "artifact_name": name,
                        "artifact_record": dict(record),
                        "persisted_artifacts": {
                            key: dict(item) for key, item in artifacts.items()
                        },
                    },
                )

        persist_artifact("raw_tensor", role_sets[role]["raw_tensor"])
        persist_artifact("oriented_tensor", oriented)
        for name, value in role_sets[role]["rts"].items():
            persist_artifact(name, value)
        persist_artifact("interior_lu", role_sets[role]["lu"])
        persist_artifact("interior_lu_pivots", role_sets[role]["pivots"])
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


def _task41_p0_v17_json_sha256(value: Mapping[str, Any]) -> str:
    import hashlib

    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _task41_p0_v17_checkpoint_progress(
    path: Path,
    name: str,
    payload: Mapping[str, Any],
) -> None:
    """Persist checkpoints without replacing progress with the final callback receipt."""
    if not isinstance(payload, Mapping):
        raise ValueError("V17 checkpoint payload must be a mapping")
    if name == "v17_selected_two_cell_progress":
        if payload.get("schema") != "task41.p0.b0.v17.selected_two_cell_progress.v2":
            raise ValueError("V17 progress checkpoint has an unknown schema")
        merged = dict(payload)
    elif name == "v17_selected_two_cell_candidate_callback":
        target = Path(path)
        if target.is_symlink() or not target.is_file() or target.stat().st_size > 16 * 1024**2:
            raise ValueError("V17 final callback checkpoint lacks a bounded progress record")
        try:
            previous = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("V17 final callback checkpoint cannot read prior progress") from exc
        if (
            not isinstance(previous, Mapping)
            or previous.get("schema") != "task41.p0.b0.v17.selected_two_cell_progress.v2"
            or payload.get("schema") != "task41.p0.b0.v17.selected_two_cell_candidate_callback.v1"
            or payload.get("status") != "COMPLETED_SELECTED_TWO_CELL_CANDIDATE_AND_RHS_REPLAY"
            or payload.get("run_identity") != previous.get("run_identity")
        ):
            raise ValueError("V17 final callback checkpoint is not bound to the persisted progress")
        merged = dict(previous)
        merged["selected_two_cell_candidate_callback"] = dict(payload)
    else:
        raise ValueError(f"V17 checkpoint name {name!r} is not registered")
    _write_json_atomic(Path(path), merged)


def _task41_p0_v17_array_sha256(value: np.ndarray) -> str:
    import hashlib

    array = np.ascontiguousarray(np.asarray(value))
    return hashlib.sha256(memoryview(array).cast("B")).hexdigest()


def _task41_p0_v17_load_array_record(
    record: Mapping[str, Any],
    *,
    results_root: Path,
    sha256_file: Any,
    shape: tuple[int, ...],
    dtype: np.dtype[Any],
    label: str,
) -> np.ndarray:
    value, _identity = _v8_load_bound_array(
        record,
        results_root=results_root,
        path_basis=ROOT,
        sha256_file=sha256_file,
    )
    if value.shape != shape or value.dtype != dtype:
        raise ValueError(f"V17 {label} saved array shape or dtype differs")
    return value


def _task41_p0_v17_reopen_completed_candidate(
    *,
    cell_state: Mapping[str, Any],
    cell_index: int,
    expected_cell_identity_sha256: str,
    artifact_names: set[str],
    dimension: int,
    interior_size: int,
    trace_size: int,
    results_root: Path,
    sha256_file: Any,
    candidate_evaluator_identity: str,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Read a completed candidate checkpoint without integration or GETRS."""
    if (
        cell_state.get("candidate_status") != "CELL_COMPLETE"
        or cell_state.get("candidate_identity_sha256")
        != expected_cell_identity_sha256
    ):
        raise ValueError(f"V17 saved candidate cell {cell_index} identity/status differs")
    records = cell_state.get("candidate_artifacts")
    if not isinstance(records, Mapping) or set(records) != artifact_names:
        raise ValueError(f"V17 completed candidate cell {cell_index} artifacts are incomplete")
    charge_fields = {
        "candidate_build_count": 1,
        "lu_factorization_count": 1,
        "matrix_rhs_getrs_count": 3,
    }
    for name, expected in charge_fields.items():
        if type(cell_state.get(name)) is not int or cell_state[name] != expected:
            raise ValueError(f"V17 completed candidate cell {cell_index} charge {name} differs")
    shapes = {
        "raw_tensor": (dimension, dimension),
        "oriented_tensor": (dimension, dimension),
        "R": (interior_size, trace_size),
        "T": (trace_size, interior_size),
        "S": (trace_size, trace_size),
        "interior_lu": (interior_size, interior_size),
        "interior_lu_pivots": (interior_size,),
    }
    loaded = {
        name: _task41_p0_v17_load_array_record(
            record,
            results_root=results_root,
            sha256_file=sha256_file,
            shape=shapes[name],
            dtype=(
                np.dtype(np.int32)
                if name == "interior_lu_pivots"
                else np.dtype(np.complex128)
            ),
            label=f"completed cell {cell_index} {name}",
        )
        for name, record in records.items()
    }
    strict_residual = cell_state.get("strict_lu_residual")
    if (
        isinstance(strict_residual, bool)
        or not isinstance(strict_residual, (int, float))
        or not math.isfinite(float(strict_residual))
        or float(strict_residual) < 0.0
    ):
        raise ValueError(f"V17 completed cell {cell_index} strict LU residual is invalid")
    candidate = {
        "source": "RECONSTRUCTED_SELECTED_CELL",
        "raw_tensor": loaded["raw_tensor"],
        "oriented_tensor": loaded["oriented_tensor"],
        "rts": {name: loaded[name] for name in ("R", "T", "S")},
        "lu": loaded["interior_lu"],
        "pivots": loaded["interior_lu_pivots"],
        "strict_lu_residual": float(strict_residual),
        "raw_tensor_evaluator_identity": candidate_evaluator_identity,
        "artifacts": dict(records),
    }
    charges = {name: int(cell_state[name]) for name in charge_fields}
    return candidate, charges


def _task41_p0_v17_reopen_completed_rhs(
    *,
    rhs_state: Mapping[str, Any],
    expected_rhs_identity: Mapping[str, Any],
    expected_rhs_identity_sha256: str,
    cell_index: int,
    column_index: int,
    interior_size: int,
    trace_size: int,
    J: np.ndarray,
    results_root: Path,
    sha256_file: Any,
) -> tuple[dict[str, Any], np.ndarray, np.ndarray, np.ndarray, np.ndarray, Mapping[str, Any]]:
    """Hash-reopen a completed RHS path, rejecting a saved non-``-Jz`` correction."""
    state = dict(rhs_state)
    if (
        state.get("rhs_identity") != dict(expected_rhs_identity)
        or state.get("rhs_identity_sha256") != expected_rhs_identity_sha256
    ):
        raise ValueError(
            f"V17 cell {cell_index} column {column_index} RHS mathematical identity differs"
        )
    artifacts = state.get("artifacts")
    if not isinstance(artifacts, Mapping) or not {
        "z0", "final_z", "returned_minus_Jz"
    }.issubset(artifacts):
        raise ValueError("V17 completed RHS omits same-call z0/final solution/correction")
    if state.get("status") == "RHS_IN_PROGRESS":
        final_step = state.get("steps", {}).get("final")
        if (
            not isinstance(final_step, Mapping)
            or type(final_step.get("getrs_count")) is not int
            or final_step["getrs_count"] < 0
            or final_step["getrs_count"] > 3
        ):
            raise ValueError(
                f"V17 cell {cell_index} column {column_index} has no complete final RHS checkpoint"
            )
        stop_reason = final_step.get("stop_reason")
        if stop_reason not in {
            "zero_rhs", "exact_zero_residual", "bitwise_unchanged_update", "max_steps"
        }:
            raise ValueError(
                f"V17 cell {cell_index} column {column_index} final stop reason is invalid"
            )
        step_names = set(state.get("steps", {}))
        residual_count = sum(
            name in step_names for name in ("step1_residual", "step2_residual")
        )
        correction_count = sum(
            name in artifacts for name in ("step1_delta", "step2_delta")
        )
        nonzero_rhs = stop_reason != "zero_rhs"
        initial_getrs_count = 1 if nonzero_rhs else 0
        if final_step["getrs_count"] != initial_getrs_count + correction_count:
            raise ValueError(
                f"V17 cell {cell_index} column {column_index} final GETRS count differs from saved steps"
            )
        state["status"] = "RHS_COMPLETE"
        state["timing"] = {
            "nonzero_rhs": nonzero_rhs,
            "refinement_max_steps": 2,
            "refinement_steps": correction_count,
            "initial_getrs_count": initial_getrs_count,
            "correction_getrs_count": correction_count,
            "getrs_count": final_step["getrs_count"],
            "residual_evaluation_count": residual_count,
            "stop_reason": stop_reason,
            "reopened_from_completed_final_step": True,
        }
    elif state.get("status") != "RHS_COMPLETE":
        raise ValueError(
            f"V17 cell {cell_index} column {column_index} has incomplete RHS steps; refusing repeated GETRS"
        )
    timing = state.get("timing")
    if (
        not isinstance(timing, Mapping)
        or type(timing.get("getrs_count")) is not int
        or not 0 <= timing["getrs_count"] <= 3
    ):
        raise ValueError("V17 completed RHS timing/count record is malformed")
    z0 = _task41_p0_v17_load_array_record(
        artifacts["z0"], results_root=results_root, sha256_file=sha256_file,
        shape=(interior_size,), dtype=np.dtype(np.complex128),
        label="same-call initial z0",
    )
    z_final = _task41_p0_v17_load_array_record(
        artifacts["final_z"], results_root=results_root, sha256_file=sha256_file,
        shape=(interior_size,), dtype=np.dtype(np.complex128), label="completed final z",
    )
    returned_minus_Jz = _task41_p0_v17_load_array_record(
        artifacts["returned_minus_Jz"], results_root=results_root, sha256_file=sha256_file,
        shape=(trace_size,), dtype=np.dtype(np.complex128),
        label="completed returned -Jz",
    )
    expected_minus_Jz = -np.asarray(J @ z_final, dtype=np.complex128)
    if not np.array_equal(returned_minus_Jz, expected_minus_Jz):
        raise ValueError(
            f"V17 reopened correction artifact for cell {cell_index} column {column_index} is not -Jz"
        )
    z0_minus_Jz = np.asarray(-J @ z0, dtype=np.complex128)
    saved_z0_record = artifacts.get("z0_minus_Jz")
    if saved_z0_record is not None:
        saved_z0_minus_Jz = _task41_p0_v17_load_array_record(
            saved_z0_record, results_root=results_root, sha256_file=sha256_file,
            shape=(trace_size,), dtype=np.dtype(np.complex128),
            label="saved same-call z0 action",
        )
        if not np.array_equal(saved_z0_minus_Jz, z0_minus_Jz):
            raise ValueError("V17 saved z0 action differs from the same-call -Jz0 product")
    return state, z0, z_final, returned_minus_Jz, z0_minus_Jz, timing


def _task41_p0_v17_selected_q_from_expansion(
    expansion: Any,
    *,
    active_slot: int,
    selected_trace_slot: int,
) -> np.ndarray:
    """Extract and bind this cell's E column, independent of prior cells' slots."""
    if (
        not 0 <= int(active_slot) < expansion.shape[1]
        or not 0 <= int(selected_trace_slot) < expansion.shape[0]
    ):
        raise ValueError("V17 selected E-column slot is out of range")
    q = np.asarray(
        expansion.getcol(int(active_slot)).toarray(), dtype=np.complex128
    ).reshape(-1)
    expected = np.zeros(int(expansion.shape[0]), dtype=np.complex128)
    expected[int(selected_trace_slot)] = 1.0 + 0.0j
    if not np.array_equal(q, expected):
        raise ValueError("V17 selected active-row E column is not the frozen +1 unit slot")
    return q


def _run_v17_selected_two_cell_candidate_callback(
    *,
    consumer_contract: Mapping[str, Any],
    consumer_contract_sha256: str,
    consumer_contract_path: str | Path,
    fixed_window: Any,
    v16_metadata: Mapping[str, Any],
    v16_metadata_path: str | Path,
    v16_metadata_sha256: str,
    v16_saved_vector_manifest: Mapping[str, Any],
    v16_saved_vector_manifest_path: str | Path,
    v16_saved_vector_manifest_sha256: str,
    saved_vectors: Mapping[str, tuple[np.ndarray, np.ndarray]],
    donor: Mapping[str, Any],
    fresh_metadata: Mapping[str, Any],
    element: Any,
    combined_form: Any,
    kernels: Mapping[int, Any],
    candidate_evaluator: Any,
    output_directory: Path,
    results_root: Path,
    sha256_file: Any,
    allocation_gate: Any,
    persist_array: Any,
    progress: Any,
    checkpoint: Any,
    resume_progress: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build/reopen the V17 two-cell candidate and the four same-LU RHS solves.

    The caller must obtain the contract/window through the strict Task41
    contract loaders, V16 metadata through its pinned loader, the V16 saved
    vectors through load_task41_p0_b0_v16_saved_vector_manifest, and the V3
    donor through the hash-bound V16 donor loader. ``fresh_metadata`` must be
    the result of build_selected_volume_trace_star_metadata with exactly the
    contract cell order. This callback never scans the row's full incident
    star and never creates a full owner, carrier, or surface object.
    """
    import hashlib
    import math
    import re
    import shutil

    from scipy.sparse import csr_matrix

    from src.runners.task41_p0_checker import (
        TASK41_P0_B0_V16_ROWS,
        TASK41_P0_B0_V16_STORAGE_ROWS,
        TASK41_P0_B0_V16_TRACE_ROWS,
        TASK41_P0_B0_V3_DONOR_MANIFEST_SHA256,
        TASK41_P0_B0_V17_SELECTED_CELLS,
        TASK41_P0_B0_V17_SELECTED_METADATA_RELATIVE,
        TASK41_P0_B0_V17_SELECTED_METADATA_SHA256,
        TASK41_P0_B0_V17_SELECTED_ORIGINAL_ROW,
        TASK41_P0_B0_V17_SELECTED_ROW,
        TASK41_P0_B0_V3_VECTOR_INDEX_SHA256,
        TASK41_P0_B0_V16_V3_DONOR_RUN_NAME,
        load_task41_p0_b0_v17_selected_cell_metadata,
        task41_p0_b0_v17_signed_cell_identity,
        task41_p0_b0_v17_signed_two_cell_identity,
    )
    from src.runners.task41_p0_contract import (
        TASK41_B0_RUN_ID,
        TASK41_MODEL_ID,
        TASK41_B0_V17_SELECTED_TWO_CELL_SCOPE,
        require_task41_p0_contract,
    )
    from src.solvers.hcurl_assembly_time_condensation import (
        _cell_integral_kernels,
        project_internal_rhs_same_lu,
    )

    if (
        fixed_window is None
        or not isinstance(consumer_contract, Mapping)
        or not isinstance(consumer_contract.get("window"), Mapping)
        or consumer_contract.get("execution_scope")
        != TASK41_B0_V17_SELECTED_TWO_CELL_SCOPE
        or not isinstance(consumer_contract.get("case"), Mapping)
        or not isinstance(consumer_contract.get("source"), Mapping)
        or not re.fullmatch(r"[0-9a-f]{64}", str(consumer_contract_sha256))
    ):
        raise ValueError("V17 callback requires the strict selected-two-cell consumer contract")
    contract_window = consumer_contract["window"]
    window_path = Path(str(contract_window.get("path", "")))
    if not window_path.is_absolute():
        window_path = ROOT / window_path
    payload = getattr(fixed_window, "payload", None)
    if (
        not isinstance(payload, Mapping)
        or contract_window.get("sha256") != getattr(fixed_window, "sha256", None)
        or window_path.resolve() != Path(str(getattr(fixed_window, "path", ""))).resolve()
        or contract_window.get("entry_source_sha") != payload.get("source_sha")
        or contract_window.get("authorization_sha256")
        != payload.get("authorization_sha256")
    ):
        raise ValueError("V17 callback fixed window is not the contract-bound window")
    if (
        consumer_contract.get("case", {}).get("run_id") != TASK41_B0_RUN_ID
        or consumer_contract.get("case", {}).get("model_id") != TASK41_MODEL_ID
        or consumer_contract.get("numerical_strategy", {}).get(
            "internal_rhs_strategy"
        )
        != "same_lu_rhs_solve"
    ):
        raise ValueError("V17 callback case or same-LU strategy differs")

    root = ROOT.resolve(strict=True)
    current_contract_path = Path(consumer_contract_path)
    if not current_contract_path.is_absolute():
        current_contract_path = root / current_contract_path
    current_contract_path = current_contract_path.resolve(strict=True)
    loaded_contract, loaded_contract_sha256 = require_task41_p0_contract(
        current_contract_path,
        expected_sha256=consumer_contract_sha256,
        current_root=root,
        case_id="B0",
    )
    if (
        loaded_contract != dict(consumer_contract)
        or loaded_contract_sha256 != consumer_contract_sha256
        or not current_contract_path.is_relative_to(root)
    ):
        raise ValueError("V17 callback consumer contract path/hash/object differs")
    current_binding = {
        "path": str(current_contract_path.relative_to(root)),
        "sha256": str(consumer_contract_sha256),
        "source_sha": str(consumer_contract.get("source", {}).get("sha", "")),
        "fixed_window_sha256": str(fixed_window.sha256),
    }
    results_root = Path(results_root).resolve(strict=True)
    expected_results_root = (
        root / "results" / str(consumer_contract["case"].get("model_id", ""))
    ).resolve(strict=True)
    if results_root != expected_results_root:
        raise ValueError("V17 callback results root differs from the contracted model")
    metadata_path = Path(v16_metadata_path).resolve(strict=True)
    expected_metadata_path = (
        root / TASK41_P0_B0_V17_SELECTED_METADATA_RELATIVE
    ).resolve(strict=True)
    if (
        metadata_path != expected_metadata_path
        or Path(v16_metadata_path).is_symlink()
        or v16_metadata_sha256 != TASK41_P0_B0_V17_SELECTED_METADATA_SHA256
        or sha256_file(metadata_path) != TASK41_P0_B0_V17_SELECTED_METADATA_SHA256
        or v16_metadata.get("source_metadata_sha256")
        != TASK41_P0_B0_V17_SELECTED_METADATA_SHA256
        or v16_metadata.get("selected_active_row")
        != TASK41_P0_B0_V17_SELECTED_ROW
        or v16_metadata.get("selected_original_row")
        != TASK41_P0_B0_V17_SELECTED_ORIGINAL_ROW
        or v16_metadata.get("incident_cell_order")
        != list(TASK41_P0_B0_V17_SELECTED_CELLS)
    ):
        raise ValueError("V17 callback V16 metadata path, digest, or row scope differs")
    pinned_metadata = load_task41_p0_b0_v17_selected_cell_metadata(
        repo_root=root,
        metadata_path=metadata_path,
        expected_sha256=TASK41_P0_B0_V17_SELECTED_METADATA_SHA256,
    )
    if (
        len(v16_metadata["cells"]) != len(pinned_metadata["cells"])
        or any(
            supplied.get("cell_id") != pinned.get("cell_id")
            or supplied.get("cell_tag") != pinned.get("cell_tag")
            or supplied.get("cell_permutation") != pinned.get("cell_permutation")
            or supplied.get("local_position") != pinned.get("local_position")
            or supplied.get("actual_coordinate_sha256")
            != pinned.get("actual_coordinate_sha256")
            or not np.array_equal(supplied.get("coordinates"), pinned.get("coordinates"))
            or not np.array_equal(supplied.get("active_ids"), pinned.get("active_ids"))
            for supplied, pinned in zip(
                v16_metadata["cells"], pinned_metadata["cells"], strict=True
            )
        )
    ):
        raise ValueError("V17 callback supplied metadata differs from the pinned loader")

    raw_manifest_path = Path(v16_saved_vector_manifest_path)
    manifest_path = raw_manifest_path.resolve(strict=False)
    expected_manifest_path = (
        results_root / TASK41_P0_V17_V16_MANIFEST_RELATIVE
    ).resolve(strict=False)
    if (
        manifest_path != expected_manifest_path
        or raw_manifest_path.is_symlink()
        or v16_saved_vector_manifest_sha256
        != TASK41_P0_V17_V16_MANIFEST_SHA256
        or v16_saved_vector_manifest.get("schema")
        != "task41.p0.b0.v16.saved_vector_manifest.v1"
        or v16_saved_vector_manifest.get("rows") != TASK41_P0_B0_V16_ROWS
        or v16_saved_vector_manifest.get("trace_rows") != TASK41_P0_B0_V16_TRACE_ROWS
        or v16_saved_vector_manifest.get("columns") != [0, 1]
    ):
        raise ValueError("V17 callback V16 saved-vector manifest identity differs")
    manifest_path = raw_manifest_path.resolve(strict=True)
    manifest_bytes = manifest_path.read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != TASK41_P0_V17_V16_MANIFEST_SHA256:
        raise ValueError("V17 callback V16 saved-vector manifest file hash differs")
    if json.loads(manifest_bytes) != dict(v16_saved_vector_manifest):
        raise ValueError("V17 callback V16 manifest object differs from its pinned file")
    required_saved_vectors = {"y9", "g9", "y15", "g15"}
    if not required_saved_vectors.issubset(saved_vectors) or any(
        len(saved_vectors[name]) != 2 for name in required_saved_vectors
    ):
        raise ValueError("V17 callback requires both columns of saved V9 and V15 y/g vectors")
    for field in required_saved_vectors:
        for column in range(2):
            vector = np.asarray(saved_vectors[field][column])
            if (
                vector.shape != (TASK41_P0_B0_V16_ROWS,)
                or vector.dtype != np.dtype(np.complex128)
            ):
                raise ValueError(f"V17 saved {field} column {column} layout differs")

    if (
        donor.get("manifest_sha256") != TASK41_P0_B0_V3_DONOR_MANIFEST_SHA256
        or donor.get("source_index_sha256")
        not in (None, TASK41_P0_B0_V3_VECTOR_INDEX_SHA256)
        or donor.get("run_name") not in (None, TASK41_P0_B0_V16_V3_DONOR_RUN_NAME)
    ):
        raise ValueError("V17 callback V3 donor manifest/index identity differs")
    columns = donor.get("columns")
    if not isinstance(columns, (list, tuple)) or len(columns) != 2:
        raise ValueError("V17 callback V3 donor must contain exactly two ordered columns")
    active_rows = np.asarray(columns[0].get("active_original_rows"))
    second_active_rows = np.asarray(columns[1].get("active_original_rows"))
    if (
        active_rows.shape != (TASK41_P0_B0_V16_TRACE_ROWS,)
        or active_rows.dtype != np.dtype(np.int64)
        or not np.array_equal(active_rows, second_active_rows)
        or int(active_rows[TASK41_P0_B0_V17_SELECTED_ROW])
        != TASK41_P0_B0_V17_SELECTED_ORIGINAL_ROW
    ):
        raise ValueError("V17 callback V3 active-to-original row map differs")
    required_vectors = ("known_field", "native_rhs", "native_volume_rhs")
    for column_index, column in enumerate(columns):
        if column.get("column", column_index) != column_index:
            raise ValueError("V17 callback donor columns are not in [0, 1] order")
        for name in required_vectors:
            vector = np.asarray(column.get(name))
            if (
                vector.shape != (TASK41_P0_B0_V16_STORAGE_ROWS,)
                or vector.dtype != np.dtype(np.complex128)
            ):
                raise ValueError(
                    f"V17 callback donor column {column_index} {name} layout differs"
                )
        beta_rows = np.asarray(column.get("b_alpha_rows"))
        beta_values = np.asarray(column.get("b_alpha_values"))
        if (
            beta_rows.ndim != 1
            or beta_rows.dtype != np.dtype(np.int64)
            or beta_values.shape != beta_rows.shape
            or beta_values.dtype != np.dtype(np.complex128)
        ):
            raise ValueError(f"V17 callback donor column {column_index} B-alpha arrays differ")

    if (
        fresh_metadata.get("selected_active_row")
        != TASK41_P0_B0_V17_SELECTED_ROW
        or fresh_metadata.get("selected_original_row")
        != TASK41_P0_B0_V17_SELECTED_ORIGINAL_ROW
        or fresh_metadata.get("selected_cell_indices")
        != list(TASK41_P0_V17_SELECTED_CELLS)
        or not np.array_equal(
            np.asarray(fresh_metadata.get("active_original_rows")), active_rows
        )
        or not isinstance(v16_metadata.get("cells"), list)
        or len(v16_metadata["cells"]) != 2
    ):
        raise ValueError("V17 fresh selected-cell metadata has the wrong row/cell scope")
    fresh_cells_raw = fresh_metadata.get("incidents")
    if not isinstance(fresh_cells_raw, list) or len(fresh_cells_raw) != 2:
        raise ValueError("V17 fresh FE map must contain exactly the two selected cells")
    fresh_cells: dict[int, dict[str, Any]] = {}
    for saved_cell, fresh_cell in zip(
        v16_metadata["cells"], fresh_cells_raw, strict=True
    ):
        cell_index = int(saved_cell["cell_id"])
        if (
            cell_index not in TASK41_P0_V17_SELECTED_CELLS
            or int(fresh_cell.get("cell_index", -1)) != cell_index
            or int(fresh_cell.get("cell_tag", -1)) != 1
            or int(fresh_cell.get("cell_permutation", -1)) != 0
            or fresh_cell.get("actual_coordinate_sha256")
            != saved_cell.get("actual_coordinate_sha256")
        ):
            raise ValueError(f"V17 fresh cell {cell_index} geometry/tag/permutation differs")
        coordinates = np.asarray(fresh_cell.get("actual_geometry_coordinates"))
        if (
            coordinates.shape != (8, 3)
            or coordinates.dtype != np.dtype(np.float64)
            or not np.array_equal(coordinates, saved_cell["coordinates"])
            or _task41_p0_v17_array_sha256(coordinates.astype("<f8", copy=False))
            != saved_cell.get("actual_coordinate_sha256")
        ):
            raise ValueError(f"V17 fresh cell {cell_index} ordered geometry differs")
        active_ids = np.asarray(fresh_cell.get("active_ids"))
        if (
            active_ids.shape != (432,)
            or active_ids.dtype.kind not in "iu"
            or not np.array_equal(active_ids, saved_cell["active_ids"])
        ):
            raise ValueError(f"V17 fresh cell {cell_index} active trace map differs")
        local_position = int(saved_cell["local_position"])
        interior_positions_cell = np.asarray(
            fresh_cell.get("interior_positions"), dtype=np.int64
        )
        trace_positions_cell = np.asarray(
            fresh_cell.get("trace_positions"), dtype=np.int64
        )
        if (
            interior_positions_cell.shape != (450,)
            or trace_positions_cell.shape != (432,)
            or np.intersect1d(interior_positions_cell, trace_positions_cell).size
            or not np.array_equal(
                np.sort(np.concatenate((interior_positions_cell, trace_positions_cell))),
                np.arange(882, dtype=np.int64),
            )
        ):
            raise ValueError(f"V17 fresh cell {cell_index} I/T partition differs")
        selected_trace_slots = np.flatnonzero(trace_positions_cell == local_position)
        selected_active_slots = np.flatnonzero(
            active_ids == TASK41_P0_B0_V17_SELECTED_ROW
        )
        selected_local_rows = np.asarray(
            fresh_cell.get("selected_local_trace_rows"), dtype=np.int64
        )
        selected_coefficients = np.asarray(
            fresh_cell.get("selected_trace_coefficients"), dtype=np.complex128
        )
        original_rows = np.asarray(fresh_cell.get("original_rows"), dtype=np.int64)
        trace_original_rows = np.asarray(
            fresh_cell.get("trace_original_rows"), dtype=np.int64
        )
        if (
            selected_trace_slots.shape != (1,)
            or selected_active_slots.shape != (1,)
            or selected_local_rows.tolist() != [int(selected_trace_slots[0])]
            or selected_coefficients.shape != (1,)
            or selected_coefficients[0] != 1.0 + 0.0j
            or int(original_rows[local_position]) != TASK41_P0_V17_ORIGINAL_ROW
            or int(trace_original_rows[selected_trace_slots[0]])
            != TASK41_P0_V17_ORIGINAL_ROW
        ):
            raise ValueError(f"V17 fresh cell {cell_index} I/T/E target-row map differs")
        fresh_cells[cell_index] = dict(fresh_cell)
    if tuple(fresh_cells) != TASK41_P0_V17_SELECTED_CELLS:
        raise ValueError("V17 fresh selected cells are not in the frozen production order")
    if (
        int(element.space_dimension) != 882
        or np.asarray(fresh_metadata.get("interior_positions")).size != 450
        or np.asarray(fresh_metadata.get("trace_positions")).size != 432
    ):
        raise ValueError("V17 prepared p6 element or I/T dimensions differ")

    producer_reports = v16_saved_vector_manifest.get("producer_reports")
    v9_record = producer_reports.get("v9_audit") if isinstance(producer_reports, Mapping) else None
    if not isinstance(v9_record, Mapping) or not isinstance(v9_record.get("path"), str):
        raise ValueError("V17 V16 saved manifest omits its V9 compact audit binding")
    raw_v9_path = Path(v9_record["path"])
    v9_path = raw_v9_path if raw_v9_path.is_absolute() else results_root / raw_v9_path
    raw_v9_path = v9_path
    v9_path = raw_v9_path.resolve(strict=True)
    if (
        raw_v9_path.is_symlink()
        or not v9_path.is_relative_to(results_root)
        or v9_path.stat().st_size > 8 * 1024**2
        or sha256_file(v9_path) != v9_record.get("sha256")
    ):
        raise ValueError("V17 V9 compact audit path or hash differs from the V16 manifest")
    v9_report = json.loads(v9_path.read_text(encoding="utf-8"))
    action_gate = v9_report.get("candidate_full_action_gate")
    if (
        v9_report.get("schema") != "task41.p0.b0.v9.compact_volume_identity.v1"
        or v9_report.get("internal_rhs_strategy") != "same_lu_rhs_solve"
        or v9_report.get("donor_manifest_sha256") != donor.get("manifest_sha256")
        or not isinstance(action_gate, Mapping)
    ):
        raise ValueError("V17 hash-bound V9 compact report is not the required same-LU source")
    if (
        not callable(getattr(candidate_evaluator, "validate_compiled_form", None))
        or not callable(getattr(candidate_evaluator, "prepare", None))
        or not isinstance(candidate_evaluator.identity, str)
        or not isinstance(candidate_evaluator.cache_identity, str)
        or candidate_evaluator.identity != v9_report.get("candidate_evaluator_identity")
        or candidate_evaluator.cache_identity
        != v9_report.get("candidate_evaluator_cache_identity")
    ):
        raise ValueError("V17 candidate evaluator/cache identity differs from V9")
    output_directory = Path(output_directory).resolve(strict=True)
    if not output_directory.is_relative_to(results_root) or not output_directory.is_dir():
        raise ValueError("V17 output directory is outside the contracted results root")
    expected_array_payload = 74_684_304
    rhs_payload_reserve = 8 * 1024**2
    estimated_payload = expected_array_payload + rhs_payload_reserve
    allocation_gate(
        "v17_selected_two_cell_candidate_preflight",
        {
            "additional_payload_bytes": estimated_payload,
            "evidence_reserve_bytes": estimated_payload,
            "new_evidence_limit_bytes": 128 * 1024**2,
            "raw_artifact_limit_bytes": 16 * 1024**3,
            "workspace_bytes": 16 * 1024**3,
            "scratch_reserve_bytes": 512 * 1024**2,
            "free_space_floor_bytes": 2 * 1024**3,
            "estimated_remaining_seconds_upper": 900.0,
            "termination_reserve_seconds": 120.0,
            "candidate_builds_max": 2,
            "candidate_lu_factorizations_max": 2,
            "matrix_rhs_getrs_max": 6,
            "internal_rhs_count": 4,
            "internal_rhs_getrs_max": 12,
            "selected_active_row": TASK41_P0_B0_V17_SELECTED_ROW,
            "selected_original_row": TASK41_P0_B0_V17_SELECTED_ORIGINAL_ROW,
            "selected_cells": list(TASK41_P0_V17_SELECTED_CELLS),
        },
    )
    if shutil.disk_usage(output_directory).free < 2 * 1024**3 + estimated_payload:
        raise OSError("V17 selected-cell output violates the 2 GiB free-space floor")
    candidate_evaluator.validate_compiled_form(
        combined_form,
        _cell_integral_kernels(combined_form, sum_duplicate_cell_integrals=True),
    )
    candidate_evaluator.prepare()
    _task41_v12_curl_mass_integral_profile(kernels)

    def complex_pair(value: complex) -> list[float]:
        scalar = complex(value)
        if not math.isfinite(scalar.real) or not math.isfinite(scalar.imag):
            raise ValueError("V17 callback produced a non-finite complex scalar")
        return [float(scalar.real), float(scalar.imag)]

    run_identity = {
        "schema": "task41.p0.b0.v17.selected_two_cell_reuse_identity.v1",
        "fixed_window_sha256": str(fixed_window.sha256),
        "v16_metadata_sha256": v16_metadata_sha256,
        "v16_saved_vector_manifest_sha256": v16_saved_vector_manifest_sha256,
        "v3_donor_manifest_sha256": str(donor["manifest_sha256"]),
        "v3_vector_index_sha256": TASK41_P0_B0_V3_VECTOR_INDEX_SHA256,
        "v9_compact_audit_sha256": str(v9_record["sha256"]),
        "candidate_evaluator_identity": candidate_evaluator.identity,
        "candidate_cache_identity": candidate_evaluator.cache_identity,
        "selected_active_row": TASK41_P0_V17_ACTIVE_ROW,
        "selected_original_row": TASK41_P0_V17_ORIGINAL_ROW,
        "selected_cells": list(TASK41_P0_V17_SELECTED_CELLS),
        "internal_rhs_strategy": "same_lu_binary64_products_real_imag_fsum",
        "internal_rhs_refinement_max_steps": 2,
    }
    run_identity_sha256 = _task41_p0_v17_json_sha256(run_identity)
    if resume_progress is None:
        state: dict[str, Any] = {
            "schema": "task41.p0.b0.v17.selected_two_cell_progress.v2",
            "run_identity": run_identity,
            "run_identity_sha256": run_identity_sha256,
            "producer_execution_binding": dict(current_binding),
            "consumer_execution_bindings": [dict(current_binding)],
            "latest_consumer_execution_binding": dict(current_binding),
            "cells": {},
        }
    else:
        state = dict(resume_progress)
        if (
            state.get("schema") != "task41.p0.b0.v17.selected_two_cell_progress.v2"
            or state.get("run_identity") != run_identity
            or state.get("run_identity_sha256") != run_identity_sha256
            or not isinstance(state.get("cells"), Mapping)
        ):
            raise ValueError("V17 resume progress is not bound to the same mathematical inputs")
        producer_binding = state.get("producer_execution_binding")
        if not isinstance(producer_binding, Mapping):
            raise ValueError("V17 resume progress lacks its original producer contract binding")
        producer_path = Path(str(producer_binding.get("path", "")))
        if producer_path.is_absolute():
            raise ValueError("V17 resume producer contract path must be repo-relative")
        old_contract, old_contract_sha256 = require_task41_p0_contract(
            producer_path,
            expected_sha256=str(producer_binding.get("sha256", "")),
            current_root=root,
            case_id="B0",
        )
        old_window = old_contract.get("window", {})
        new_window = consumer_contract.get("window", {})
        if (
            producer_binding.get("fixed_window_sha256") != fixed_window.sha256
            or old_window.get("sha256") != new_window.get("sha256")
            or old_window.get("path") != new_window.get("path")
            or old_contract_sha256 != producer_binding.get("sha256")
            or old_contract.get("execution_scope") != TASK41_B0_V17_SELECTED_TWO_CELL_SCOPE
        ):
            raise ValueError("V17 resume producer contract is not bound to this same fixed window/scope")
        bindings = state.get("consumer_execution_bindings")
        if not isinstance(bindings, list) or not bindings:
            raise ValueError("V17 resume progress has no execution contract history")
        if current_binding not in bindings:
            bindings = [*bindings, dict(current_binding)]
            state["consumer_execution_bindings"] = bindings
        state["latest_consumer_execution_binding"] = dict(current_binding)
        state["cells"] = dict(state["cells"])

    def save_state() -> None:
        checkpoint("v17_selected_two_cell_progress", state)

    def persist_named(name: str, value: np.ndarray) -> dict[str, Any]:
        array = np.asarray(value)
        if not np.isfinite(array).all():
            raise ValueError(f"V17 callback array {name} contains non-finite values")
        return {"name": name, **persist_array(name, array)}

    map_fields = (
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

    def local_candidate_identity(
        cell_index: int, row: Mapping[str, Any]
    ) -> tuple[dict[str, Any], str]:
        local_identity = {
            "run_identity_sha256": run_identity_sha256,
            "cell_index": int(cell_index),
            "cell_tag": int(row["cell_tag"]),
            "cell_permutation": int(row["cell_permutation"]),
            "actual_coordinate_sha256": str(row["actual_coordinate_sha256"]),
            "original_rows_sha256": _task41_p0_v17_array_sha256(row["original_rows"]),
            "active_ids_sha256": _task41_p0_v17_array_sha256(row["active_ids"]),
            "interior_positions_sha256": _task41_p0_v17_array_sha256(
                np.asarray(row["interior_positions"], dtype=np.int64)
            ),
            "trace_positions_sha256": _task41_p0_v17_array_sha256(
                np.asarray(row["trace_positions"], dtype=np.int64)
            ),
            "trace_expansion_data_sha256": _task41_p0_v17_array_sha256(
                row["trace_expansion_data"]
            ),
            "trace_expansion_indices_sha256": _task41_p0_v17_array_sha256(
                row["trace_expansion_indices"]
            ),
            "trace_expansion_indptr_sha256": _task41_p0_v17_array_sha256(
                row["trace_expansion_indptr"]
            ),
            "candidate_evaluator_identity": candidate_evaluator.identity,
            "candidate_cache_identity": candidate_evaluator.cache_identity,
        }
        return local_identity, _task41_p0_v17_json_sha256(local_identity)

    for cell_index in TASK41_P0_V17_SELECTED_CELLS:
        row = fresh_cells[cell_index]
        cell_state = dict(state["cells"].get(str(cell_index), {}))
        map_identity = {
            "cell_index": int(cell_index),
            "cell_tag": int(row["cell_tag"]),
            "cell_permutation": int(row["cell_permutation"]),
            "actual_coordinate_sha256": str(row["actual_coordinate_sha256"]),
            "array_sha256s": {
                name: _task41_p0_v17_array_sha256(np.asarray(row[name]))
                for name in map_fields
            },
        }
        map_identity_sha256 = _task41_p0_v17_json_sha256(map_identity)
        candidate_identity, candidate_identity_sha256 = local_candidate_identity(
            cell_index, row
        )
        if (
            cell_state
            and cell_state.get("cell_identity_sha256") != candidate_identity_sha256
        ):
            raise ValueError(f"V17 saved cell {cell_index} progress identity differs")
        saved_identity = cell_state.get("fresh_map_identity")
        saved_records = cell_state.get("fresh_map_artifacts")
        if saved_records is not None:
            if (
                saved_identity != map_identity
                or cell_state.get("fresh_map_identity_sha256") != map_identity_sha256
                or not isinstance(saved_records, Mapping)
                or set(saved_records) != set(map_fields)
            ):
                raise ValueError(
                    f"V17 saved fresh cell {cell_index} map identity or artifact set differs"
                )
            for name in map_fields:
                record = saved_records[name]
                array = _task41_p0_v17_load_array_record(
                    record,
                    results_root=results_root,
                    sha256_file=sha256_file,
                    shape=tuple(np.asarray(row[name]).shape),
                    dtype=np.asarray(row[name]).dtype,
                    label=f"fresh map cell {cell_index} {name}",
                )
                if not np.array_equal(array, np.asarray(row[name])):
                    raise ValueError(
                        f"V17 saved fresh cell {cell_index} map {name} differs from the current FE map"
                    )
        else:
            partial_map = cell_state.get("fresh_map_artifacts_partial", {})
            if partial_map:
                raise ValueError(
                    f"V17 cell {cell_index} has partial fresh-map artifacts; refusing a second map write"
                )
            cell_state["fresh_map_identity"] = map_identity
            cell_state["fresh_map_identity_sha256"] = map_identity_sha256
            cell_state["cell_identity"] = candidate_identity
            cell_state["cell_identity_sha256"] = candidate_identity_sha256
            cell_state["fresh_map_artifacts_partial"] = {}
            state["cells"][str(cell_index)] = cell_state
            save_state()
            for name in map_fields:
                record = persist_named(
                    f"task41_p0_v17_cell{cell_index}_map_{name}",
                    np.asarray(row[name]),
                )
                cell_state["fresh_map_artifacts_partial"][name] = record
                state["cells"][str(cell_index)] = cell_state
                save_state()
            cell_state["fresh_map_artifacts"] = dict(
                cell_state.pop("fresh_map_artifacts_partial")
            )
            state["cells"][str(cell_index)] = cell_state
            save_state()

    cell_candidates: dict[int, dict[str, Any]] = {}
    candidate_cells_built: list[int] = []
    candidate_cells_reused: list[int] = []
    matrix_rhs_getrs_charged = 0
    candidate_builds_charged = 0
    lu_factorizations_charged = 0
    candidate_builds_this_invocation = 0
    lu_factorizations_this_invocation = 0
    matrix_rhs_getrs_this_invocation = 0
    for cell_index in TASK41_P0_V17_SELECTED_CELLS:
        row = fresh_cells[cell_index]
        interior_positions = np.asarray(row["interior_positions"], dtype=np.int64)
        trace_positions = np.asarray(row["trace_positions"], dtype=np.int64)
        local_identity, local_identity_sha256 = local_candidate_identity(
            cell_index, row
        )
        cell_state = dict(state["cells"].get(str(cell_index), {}))
        if cell_state and cell_state.get("cell_identity_sha256") != local_identity_sha256:
            raise ValueError(f"V17 saved cell {cell_index} progress identity differs")
        cell_state.setdefault("cell_index", int(cell_index))
        cell_state.setdefault("cell_identity", local_identity)
        cell_state.setdefault("cell_identity_sha256", local_identity_sha256)
        artifact_names = {
            "raw_tensor", "oriented_tensor", "R", "T", "S",
            "interior_lu", "interior_lu_pivots",
        }
        if cell_state.get("candidate_status") == "CELL_COMPLETE":
            candidate, candidate_charges = _task41_p0_v17_reopen_completed_candidate(
                cell_state=cell_state,
                cell_index=cell_index,
                expected_cell_identity_sha256=local_identity_sha256,
                artifact_names=artifact_names,
                dimension=int(element.space_dimension),
                interior_size=len(interior_positions),
                trace_size=len(trace_positions),
                results_root=results_root,
                sha256_file=sha256_file,
                candidate_evaluator_identity=candidate_evaluator.identity,
            )
            candidate_cells_reused.append(cell_index)
            candidate_builds_charged += candidate_charges["candidate_build_count"]
            lu_factorizations_charged += candidate_charges["lu_factorization_count"]
            matrix_rhs_getrs_charged += candidate_charges["matrix_rhs_getrs_count"]
            progress({
                "phase": "v17_selected_candidate_cell",
                "status": "READ_FROM_HASH_BOUND_PROGRESS",
                "cell_index": cell_index,
            })
        else:
            partial = cell_state.get("candidate_artifacts_partial", {})
            if partial:
                raise ValueError(
                    f"V17 cell {cell_index} has partial candidate artifacts; refusing a second integration/factorization"
                )
            progress({
                "phase": "v17_selected_candidate_cell",
                "status": "STARTED",
                "cell_index": cell_index,
                "source": "RECONSTRUCTED_SELECTED_CELL",
            })

            def artifact_checkpoint(_section: str, record: Mapping[str, Any]) -> None:
                name = str(record.get("artifact_name", ""))
                artifact = record.get("artifact_record")
                if name not in artifact_names or not isinstance(artifact, Mapping):
                    raise ValueError("V17 candidate artifact checkpoint is malformed")
                partial_records = dict(cell_state.get("candidate_artifacts_partial", {}))
                partial_records[name] = dict(artifact)
                cell_state["candidate_artifacts_partial"] = partial_records
                state["cells"][str(cell_index)] = cell_state
                save_state()

            role_sets = _v8_rebuild_selected_cell_role_artifacts(
                cell_index=cell_index,
                row=row,
                combined_form=combined_form,
                kernels=dict(kernels),
                element=element,
                dimension=int(element.space_dimension),
                interior_positions=interior_positions,
                trace_positions=trace_positions,
                candidate_evaluator=candidate_evaluator,
                persist_array=persist_array,
                progress=progress,
                candidate_only=True,
                artifact_prefix_template="task41_p0_v17_selected_cell{cell_index}_{role}",
                checkpoint=artifact_checkpoint,
            )
            if set(role_sets) != {"candidate"}:
                raise ValueError(f"V17 selected cell {cell_index} did not build candidate-only data")
            candidate = role_sets["candidate"]
            if set(candidate["artifacts"]) != artifact_names:
                raise ValueError(f"V17 selected cell {cell_index} candidate artifact set differs")
            cell_state.update({
                "candidate_status": "CELL_COMPLETE",
                "candidate_identity_sha256": local_identity_sha256,
                "candidate_artifacts": {
                    name: dict(record) for name, record in candidate["artifacts"].items()
                },
                "strict_lu_residual": float(candidate["strict_lu_residual"]),
                "candidate_build_count": 1,
                "lu_factorization_count": 1,
                "matrix_rhs_getrs_count": 3,
                "candidate_artifacts_partial": {},
                "rhs": dict(cell_state.get("rhs", {})),
                "column_terms": dict(cell_state.get("column_terms", {})),
            })
            state["cells"][str(cell_index)] = cell_state
            save_state()
            candidate_cells_built.append(cell_index)
            candidate_builds_charged += 1
            lu_factorizations_charged += 1
            matrix_rhs_getrs_charged += 3
            candidate_builds_this_invocation += 1
            lu_factorizations_this_invocation += 1
            matrix_rhs_getrs_this_invocation += 3
            progress({
                "phase": "v17_selected_candidate_cell",
                "status": "COMPLETED",
                "cell_index": cell_index,
                "strict_lu_residual": float(candidate["strict_lu_residual"]),
            })
        cell_state["candidate_status"] = "CELL_COMPLETE"
        cell_state["candidate_identity_sha256"] = local_identity_sha256
        cell_state.setdefault("candidate_artifacts", dict(candidate["artifacts"]))
        cell_state.setdefault("rhs", {})
        cell_state.setdefault("column_terms", {})
        state["cells"][str(cell_index)] = cell_state
        cell_candidates[cell_index] = candidate

    if (
        candidate_builds_charged > 2
        or lu_factorizations_charged > 2
        or matrix_rhs_getrs_charged > 6
    ):
        raise ValueError("V17 candidate/LU/matrix-GETRS charge exceeds the two-cell scope")

    rhs_getrs_charged = 0
    rhs_getrs_this_invocation = 0
    rhs_results: dict[tuple[int, int], dict[str, Any]] = {}
    cell_terms: dict[tuple[int, int], dict[str, Any]] = {}
    for column_index, donor_column in enumerate(columns):
        if (
            "column" in donor_column
            and int(donor_column["column"]) != column_index
        ):
            raise ValueError("V17 donor column order changed during replay")
        known = np.asarray(donor_column["known_field"])
        native_rhs = np.asarray(donor_column["native_rhs"])
        native_volume_rhs = np.asarray(donor_column["native_volume_rhs"])
        active_rows = np.asarray(donor_column["active_original_rows"], dtype=np.int64)
        original_row = TASK41_P0_V17_ORIGINAL_ROW
        b_alpha_rows = np.asarray(donor_column["b_alpha_rows"], dtype=np.int64)
        b_alpha_values = np.asarray(donor_column["b_alpha_values"], dtype=np.complex128)
        beta_values = b_alpha_values[b_alpha_rows == original_row]
        if beta_values.size > 1:
            raise ValueError("V17 target row has duplicate native B-alpha entries")
        beta_t = complex(beta_values[0]) if beta_values.size else 0.0 + 0.0j
        row_terms = []
        for cell_index in TASK41_P0_V17_SELECTED_CELLS:
            row = fresh_cells[cell_index]
            candidate = cell_candidates[cell_index]
            cell_state = state["cells"][str(cell_index)]
            interior_positions = np.asarray(row["interior_positions"], dtype=np.int64)
            trace_positions = np.asarray(row["trace_positions"], dtype=np.int64)
            original_rows = np.asarray(row["original_rows"], dtype=np.int64)
            interior_rows = np.asarray(row["interior_original_rows"], dtype=np.int64)
            trace_rows = np.asarray(row["trace_original_rows"], dtype=np.int64)
            active_ids = np.asarray(row["active_ids"], dtype=np.int64)
            if (
                not np.array_equal(original_rows[interior_positions], interior_rows)
                or not np.array_equal(original_rows[trace_positions], trace_rows)
                or np.any(active_ids < 0)
                or np.any(active_ids >= active_rows.size)
            ):
                raise ValueError(f"V17 cell {cell_index} row-to-dof maps are inconsistent")
            expansion = csr_matrix(
                (
                    np.asarray(row["trace_expansion_data"], dtype=np.complex128),
                    np.asarray(row["trace_expansion_indices"], dtype=np.int32),
                    np.asarray(row["trace_expansion_indptr"], dtype=np.int32),
                ),
                shape=(len(trace_positions), len(active_ids)),
            )
            active_slot = np.flatnonzero(active_ids == TASK41_P0_V17_ACTIVE_ROW)
            if active_slot.shape != (1,):
                raise ValueError(f"V17 selected active row is absent/duplicated in cell {cell_index}")
            local_column = str(column_index)
            term_records = dict(cell_state["column_terms"].get(local_column, {}))
            term_identity = {
                "cell_identity_sha256": cell_state["cell_identity_sha256"],
                "column": column_index,
                "known_field_local_sha256": _task41_p0_v17_array_sha256(
                    known[interior_rows]
                ),
                "native_rhs_interior_sha256": _task41_p0_v17_array_sha256(
                    native_rhs[interior_rows]
                ),
                "native_volume_rhs_interior_sha256": _task41_p0_v17_array_sha256(
                    native_volume_rhs[interior_rows]
                ),
            }
            term_identity_sha256 = _task41_p0_v17_json_sha256(term_identity)
            if term_records:
                if (
                    term_records.get("term_identity") != term_identity
                    or term_records.get("term_identity_sha256") != term_identity_sha256
                    or term_records.get("status") != "CELL_COLUMN_TERMS_COMPLETE"
                ):
                    raise ValueError(
                        f"V17 cell {cell_index} column {column_index} has partial/mismatched saved inputs"
                    )
                term_arrays = term_records.get("artifacts")
                if not isinstance(term_arrays, Mapping) or set(term_arrays) != {
                    "known_trace_local", "known_interior_local", "native_rhs_interior",
                    "native_volume_rhs_interior", "S_action",
                }:
                    raise ValueError("V17 saved cell-column term artifacts are incomplete")
                loaded_terms = {
                    name: _task41_p0_v17_load_array_record(
                        record,
                        results_root=results_root,
                        sha256_file=sha256_file,
                        shape=(len(trace_positions) if name in {"known_trace_local", "S_action"}
                               else len(interior_positions),),
                        dtype=np.dtype(np.complex128),
                        label=f"cell {cell_index} column {column_index} {name}",
                    )
                    for name, record in term_arrays.items()
                }
                t_c = np.asarray(loaded_terms["known_trace_local"])
                u_i = np.asarray(loaded_terms["known_interior_local"])
                b_i = np.asarray(loaded_terms["native_rhs_interior"])
                volume_b_i = np.asarray(loaded_terms["native_volume_rhs_interior"])
                s_action = np.asarray(loaded_terms["S_action"])
            else:
                known_active = np.asarray(
                    known[active_rows[active_ids]], dtype=np.complex128
                )
                t_c = np.asarray(expansion @ known_active, dtype=np.complex128).reshape(-1)
                u_i = np.asarray(known[interior_rows], dtype=np.complex128)
                b_i = np.asarray(native_rhs[interior_rows], dtype=np.complex128)
                volume_b_i = np.asarray(native_volume_rhs[interior_rows], dtype=np.complex128)
                if not np.array_equal(b_i, volume_b_i):
                    raise ValueError(
                        f"V17 full and volume native interior RHS differ in cell {cell_index}"
                    )
                tensor = np.asarray(candidate["oriented_tensor"], dtype=np.complex128)
                K = tensor[np.ix_(interior_positions, interior_positions)]
                J = tensor[np.ix_(trace_positions, interior_positions)]
                L = tensor[np.ix_(trace_positions, trace_positions)]
                s_action = np.asarray(candidate["rts"]["S"] @ t_c, dtype=np.complex128)
                arrays_to_save = {
                    "known_trace_local": t_c,
                    "known_interior_local": u_i,
                    "native_rhs_interior": b_i,
                    "native_volume_rhs_interior": volume_b_i,
                    "S_action": s_action,
                }
                term_records = {
                    "status": "CELL_COLUMN_TERMS_IN_PROGRESS",
                    "term_identity": term_identity,
                    "term_identity_sha256": term_identity_sha256,
                    "artifacts": {},
                }
                cell_state["column_terms"][local_column] = term_records
                state["cells"][str(cell_index)] = cell_state
                save_state()
                for name, value in arrays_to_save.items():
                    record = persist_named(
                        f"task41_p0_v17_cell{cell_index}_col{column_index}_{name}",
                        value,
                    )
                    term_records["artifacts"][name] = record
                    checkpoint("v17_selected_two_cell_progress", state)
                term_records["status"] = "CELL_COLUMN_TERMS_COMPLETE"
                cell_state["column_terms"][local_column] = term_records
                state["cells"][str(cell_index)] = cell_state
                save_state()
            if not np.array_equal(b_i, volume_b_i):
                raise ValueError(f"V17 saved volume/native RHS differs in cell {cell_index}")

            rhs_key = local_column
            rhs_state = dict(cell_state["rhs"].get(rhs_key, {}))
            rhs_identity = {
                "cell_identity_sha256": cell_state["cell_identity_sha256"],
                "term_identity_sha256": term_identity_sha256,
                "column": column_index,
                "K_sha256": _task41_p0_v17_array_sha256(
                    np.asarray(candidate["oriented_tensor"])[
                        np.ix_(interior_positions, interior_positions)
                    ]
                ),
                "J_sha256": _task41_p0_v17_array_sha256(
                    np.asarray(candidate["oriented_tensor"])[
                        np.ix_(trace_positions, interior_positions)
                    ]
                ),
                "rhs_sha256": _task41_p0_v17_array_sha256(b_i),
                "refinement_max_steps": 2,
            }
            rhs_identity_sha256 = _task41_p0_v17_json_sha256(rhs_identity)
            tensor = np.asarray(candidate["oriented_tensor"], dtype=np.complex128)
            K = tensor[np.ix_(interior_positions, interior_positions)]
            J = tensor[np.ix_(trace_positions, interior_positions)]
            if rhs_state:
                old_status = rhs_state.get("status")
                (
                    rhs_state,
                    z0,
                    z_final,
                    minus_J_z,
                    minus_J_z0,
                    timing,
                ) = _task41_p0_v17_reopen_completed_rhs(
                    rhs_state=rhs_state,
                    expected_rhs_identity=rhs_identity,
                    expected_rhs_identity_sha256=rhs_identity_sha256,
                    cell_index=cell_index,
                    column_index=column_index,
                    interior_size=len(interior_positions),
                    trace_size=len(trace_positions),
                    J=J,
                    results_root=results_root,
                    sha256_file=sha256_file,
                )
                if old_status != "RHS_COMPLETE":
                    cell_state["rhs"][rhs_key] = rhs_state
                    state["cells"][str(cell_index)] = cell_state
                    save_state()
                rhs_getrs_charged += int(timing["getrs_count"])
            else:
                rhs_state = {
                    "status": "RHS_IN_PROGRESS",
                    "rhs_identity": rhs_identity,
                    "rhs_identity_sha256": rhs_identity_sha256,
                    "artifacts": {},
                    "steps": {},
                }
                cell_state["rhs"][rhs_key] = rhs_state
                state["cells"][str(cell_index)] = cell_state
                save_state()

                def save_step_array(step_name: str, values: np.ndarray) -> None:
                    record = persist_named(
                        f"task41_p0_v17_cell{cell_index}_col{column_index}_rhs_{step_name}",
                        values,
                    )
                    rhs_state["artifacts"][step_name] = record
                    rhs_state["steps"][step_name] = {"artifact": dict(record)}
                    cell_state["rhs"][rhs_key] = rhs_state
                    state["cells"][str(cell_index)] = cell_state
                    checkpoint("v17_selected_two_cell_progress", state)

                def step_callback(record: Mapping[str, Any]) -> None:
                    event = str(record.get("event", ""))
                    if event == "initial":
                        save_step_array("z0", np.asarray(record["solved"], dtype=np.complex128))
                    elif event == "correction_step":
                        step = int(record.get("step", 0))
                        if step not in (1, 2):
                            raise ValueError("V17 RHS refinement emitted an out-of-scope step")
                        prefix = f"step{step}"
                        for field, artifact in (
                            ("z_before", "z_before"),
                            ("residual", "residual"),
                            ("delta", "delta"),
                            ("z_after", "z_after"),
                        ):
                            value = record.get(field)
                            if value is not None:
                                save_step_array(f"{prefix}_{artifact}", np.asarray(value, dtype=np.complex128))
                        rhs_state["steps"].setdefault(prefix, {})["stop_reason"] = record.get("stop_reason")
                        checkpoint("v17_selected_two_cell_progress", state)
                    elif event == "final":
                        if "z0" not in rhs_state["artifacts"]:
                            if record.get("stop_reason") != "zero_rhs":
                                raise ValueError("V17 nonzero RHS final event omitted its initial solve")
                            save_step_array("z0", np.asarray(record["solved"], dtype=np.complex128))
                        save_step_array("final_z", np.asarray(record["solved"], dtype=np.complex128))
                        save_step_array("returned_minus_Jz", np.asarray(record["correction"], dtype=np.complex128))
                        rhs_state["steps"]["final"] = {
                            "stop_reason": record.get("stop_reason"),
                            "getrs_count": int(record.get("getrs_count", 0)),
                        }
                        checkpoint("v17_selected_two_cell_progress", state)
                    else:
                        raise ValueError(f"V17 RHS emitted an unknown event {event!r}")

                tensor = np.asarray(candidate["oriented_tensor"], dtype=np.complex128)
                K = tensor[np.ix_(interior_positions, interior_positions)]
                J = tensor[np.ix_(trace_positions, interior_positions)]
                matrix_identity = (
                    f"v17-cell-{cell_index}-K-{rhs_identity['K_sha256']}"
                )
                z_final, minus_J_z, timing = project_internal_rhs_same_lu(
                    (np.asarray(candidate["lu"], dtype=np.complex128),
                     np.array(candidate["pivots"], dtype=np.int32, copy=True)),
                    J,
                    b_i,
                    refinement_max_steps=2,
                    actual_internal_matrix=K,
                    actual_internal_matrix_identity=matrix_identity,
                    factor_matrix_identity=matrix_identity,
                    step_callback=step_callback,
                )
                z_final = np.asarray(z_final, dtype=np.complex128)
                minus_J_z = np.asarray(minus_J_z, dtype=np.complex128)
                if (
                    not np.array_equal(
                        minus_J_z,
                        -np.asarray(J @ z_final, dtype=np.complex128),
                    )
                    or "final_z" not in rhs_state["artifacts"]
                    or "returned_minus_Jz" not in rhs_state["artifacts"]
                ):
                    raise ValueError("V17 actual returned correction does not equal the saved -Jz action")
                getrs_count = int(timing.get("getrs_count", -1))
                if getrs_count < 0 or getrs_count > 3:
                    raise ValueError("V17 one RHS exceeded its initial-plus-two-steps GETRS limit")
                rhs_getrs_charged += getrs_count
                rhs_getrs_this_invocation += getrs_count
                rhs_state["status"] = "RHS_COMPLETE"
                rhs_state["timing"] = {
                    str(key): (int(value) if isinstance(value, (np.integer,)) else
                               float(value) if isinstance(value, (np.floating,)) else value)
                    for key, value in timing.items()
                }
                cell_state["rhs"][rhs_key] = rhs_state
                state["cells"][str(cell_index)] = cell_state
                save_state()
            tensor = np.asarray(candidate["oriented_tensor"], dtype=np.complex128)
            K = tensor[np.ix_(interior_positions, interior_positions)]
            J = tensor[np.ix_(trace_positions, interior_positions)]
            if "z0" not in rhs_state.get("artifacts", {}):
                raise ValueError(
                    f"V17 cell {cell_index} column {column_index} has no durable same-call z0"
                )
            z0 = _task41_p0_v17_load_array_record(
                rhs_state["artifacts"]["z0"],
                results_root=results_root,
                sha256_file=sha256_file,
                shape=(len(interior_positions),),
                dtype=np.dtype(np.complex128),
                label="same-call initial z0 for g9 comparison",
            )
            minus_J_z0 = np.asarray(-J @ z0, dtype=np.complex128)
            if not np.array_equal(minus_J_z, -np.asarray(J @ z_final, dtype=np.complex128)):
                raise ValueError(
                    f"V17 reopened correction artifact for cell {cell_index} column {column_index} is not -Jz"
                )
            z0_action_record = rhs_state.get("artifacts", {}).get("z0_minus_Jz")
            if z0_action_record is not None:
                saved_z0_action = _task41_p0_v17_load_array_record(
                    z0_action_record,
                    results_root=results_root,
                    sha256_file=sha256_file,
                    shape=(len(trace_positions),),
                    dtype=np.dtype(np.complex128),
                    label="saved same-call z0 action",
                )
                if not np.array_equal(saved_z0_action, minus_J_z0):
                    raise ValueError("V17 saved z0 action differs from the same-call -Jz0 product")
            else:
                record = persist_named(
                    f"task41_p0_v17_cell{cell_index}_col{column_index}_rhs_z0_minus_Jz",
                    minus_J_z0,
                )
                rhs_state.setdefault("artifacts", {})["z0_minus_Jz"] = record
                cell_state["rhs"][rhs_key] = rhs_state
                state["cells"][str(cell_index)] = cell_state
                checkpoint("v17_selected_two_cell_progress", state)
            if rhs_getrs_charged > 12:
                raise ValueError("V17 aggregate internal RHS GETRS charge exceeds 12")

            S = np.asarray(candidate["rts"]["S"], dtype=np.complex128)
            projected_s = np.asarray(
                expansion.getcol(int(active_slot[0])).conjugate().transpose() @ s_action
            ).reshape(-1)
            projected_g = np.asarray(
                expansion.getcol(int(active_slot[0])).conjugate().transpose() @ minus_J_z
            ).reshape(-1)
            s_term = complex(projected_s[0])
            g_term = complex(projected_g[0])
            projected_g0 = np.asarray(
                expansion.getcol(int(active_slot[0])).conjugate().transpose() @ minus_J_z0
            ).reshape(-1)
            g0_term = complex(projected_g0[0])
            row_terms.append({
                "cell_index": cell_index,
                "known_trace_local_artifact": term_records["artifacts"]["known_trace_local"],
                "known_interior_local_artifact": term_records["artifacts"]["known_interior_local"],
                "native_rhs_interior_artifact": term_records["artifacts"]["native_rhs_interior"],
                "native_volume_rhs_interior_artifact": term_records["artifacts"]["native_volume_rhs_interior"],
                "S_action_artifact": term_records["artifacts"]["S_action"],
                "rhs_artifacts": dict(rhs_state["artifacts"]),
                "rhs_timing": dict(rhs_state.get("timing", {})),
                "strict_rhs_residual_count": int(
                    rhs_state.get("timing", {}).get("residual_evaluation_count", 0)
                ),
                "rhs_getrs_count": int(rhs_state.get("timing", {}).get("getrs_count", 0)),
                "s_projected_term": complex_pair(s_term),
                "minus_Jz_projected_term": complex_pair(g_term),
                "minus_Jz0_projected_term": complex_pair(g0_term),
                "t_is_elementwise_zero": bool(np.all(t_c == 0.0)),
            })
            q = _task41_p0_v17_selected_q_from_expansion(
                expansion,
                active_slot=int(active_slot[0]),
                selected_trace_slot=int(row["selected_local_trace_rows"][0]),
            )
            signed_cell = task41_p0_b0_v17_signed_cell_identity(
                K=tensor[np.ix_(interior_positions, interior_positions)],
                G=tensor[np.ix_(interior_positions, trace_positions)],
                J=J,
                L=tensor[np.ix_(trace_positions, trace_positions)],
                R=np.asarray(candidate["rts"]["R"], dtype=np.complex128),
                T=np.asarray(candidate["rts"]["T"], dtype=np.complex128),
                S=S,
                q=q,
                u_i=u_i,
                t_c=t_c,
                b_i=b_i,
                z_c=z_final,
            )
            signed_cell["cell_id"] = cell_index
            row_terms[-1]["signed_identity"] = signed_cell
            cell_terms[(column_index, cell_index)] = {
                "s_term": s_term,
                "g_term": g_term,
                "g0_term": g0_term,
                "row_record": row_terms[-1],
            }
            del S, J
        saved_y = complex(saved_vectors["y15"][column_index][TASK41_P0_V17_ACTIVE_ROW])
        saved_g = complex(saved_vectors["g15"][column_index][TASK41_P0_V17_ACTIVE_ROW])
        saved_y9 = complex(saved_vectors["y9"][column_index][TASK41_P0_V17_ACTIVE_ROW])
        saved_g9 = complex(saved_vectors["g9"][column_index][TASK41_P0_V17_ACTIVE_ROW])
        replay_y = 0.0 + 0.0j
        replay_g = complex(native_rhs[original_row])
        replay_g0 = complex(native_rhs[original_row])
        for cell_index in TASK41_P0_V17_SELECTED_CELLS:
            replay_y += cell_terms[(column_index, cell_index)]["s_term"]
            replay_g += cell_terms[(column_index, cell_index)]["g_term"]
            replay_g0 += cell_terms[(column_index, cell_index)]["g0_term"]
        replay_y += beta_t
        signed_cells = [
            cell_terms[(column_index, cell_index)]["row_record"]["signed_identity"]
            for cell_index in TASK41_P0_V17_SELECTED_CELLS
        ]
        signed_two_cell = task41_p0_b0_v17_signed_two_cell_identity(
            cells=signed_cells,
            b_t_volume=complex(native_volume_rhs[original_row]),
            b_t_full=complex(native_rhs[original_row]),
            b_alpha_t=beta_t,
            observed_d=saved_y - saved_g,
        )
        rhs_results[column_index, -1] = {
            "column": column_index,
            "saved_y9": complex_pair(saved_y9),
            "replayed_y9": complex_pair(replay_y),
            "y9_exact_saved_value_reproduced": bool(replay_y == saved_y9),
            "saved_g9": complex_pair(saved_g9),
            "replayed_g9_from_same_call_z0": complex_pair(replay_g0),
            "g9_exact_saved_value_reproduced": bool(replay_g0 == saved_g9),
            "saved_y15": complex_pair(saved_y),
            "replayed_y15": complex_pair(replay_y),
            "y15_exact_saved_value_reproduced": bool(replay_y == saved_y),
            "saved_g15": complex_pair(saved_g),
            "replayed_g15": complex_pair(replay_g),
            "g15_exact_saved_value_reproduced": bool(replay_g == saved_g),
            "native_rhs_t": complex_pair(complex(native_rhs[original_row])),
            "native_volume_rhs_t": complex_pair(complex(native_volume_rhs[original_row])),
            "b_alpha_t": complex_pair(beta_t),
            "cells": row_terms,
            "signed_two_cell_identity": signed_two_cell,
        }

    if candidate_builds_charged > 2 or lu_factorizations_charged > 2 or matrix_rhs_getrs_charged > 6:
        raise ValueError("V17 callback exceeded the candidate/LU/matrix GETRS contract")
    if rhs_getrs_charged > 12:
        raise ValueError("V17 callback exceeded the aggregate 12-vector-GETRS contract")
    result = {
        "schema": "task41.p0.b0.v17.selected_two_cell_candidate_callback.v1",
        "status": "COMPLETED_SELECTED_TWO_CELL_CANDIDATE_AND_RHS_REPLAY",
        "classification": (
            "LOCAL_REPLAY_COMPLETED"
            if all(
                item["g9_exact_saved_value_reproduced"]
                and item["y15_exact_saved_value_reproduced"]
                and item["g15_exact_saved_value_reproduced"]
                for item in rhs_results.values()
            )
            else "LOCAL_REPLAY_UNBOUND"
        ),
        "scope": {
            "selected_active_row": TASK41_P0_V17_ACTIVE_ROW,
            "selected_original_row": TASK41_P0_V17_ORIGINAL_ROW,
            "cell_order": list(TASK41_P0_V17_SELECTED_CELLS),
            "columns": [0, 1],
            "full_owner": False,
            "carrier_replay": False,
            "surface_replay": False,
            "full_q_scan": False,
            "official_result": False,
        },
        "run_identity": run_identity,
        "run_identity_sha256": run_identity_sha256,
        "candidate_cells_built_this_invocation": candidate_cells_built,
        "candidate_cells_reused": candidate_cells_reused,
        "candidate_builds_charged": candidate_builds_charged,
        "candidate_builds_this_invocation": candidate_builds_this_invocation,
        "lu_factorizations_charged": lu_factorizations_charged,
        "lu_factorizations_this_invocation": lu_factorizations_this_invocation,
        "matrix_rhs_getrs_charged": matrix_rhs_getrs_charged,
        "matrix_rhs_getrs_this_invocation": matrix_rhs_getrs_this_invocation,
        "matrix_rhs_getrs_upper_bound": 6,
        "matrix_rhs_getrs_accounting": {
            str(cell_index): {"strict_factor_check": 1, "R_build": 1, "T_build": 1}
            for cell_index in TASK41_P0_V17_SELECTED_CELLS
        },
        "internal_rhs_getrs_charged": rhs_getrs_charged,
        "internal_rhs_getrs_this_invocation": rhs_getrs_this_invocation,
        "internal_rhs_getrs_upper_bound": 12,
        "cells": [
            {
                "cell_index": cell_index,
                "cell_tag": int(fresh_cells[cell_index]["cell_tag"]),
                "cell_permutation": int(fresh_cells[cell_index]["cell_permutation"]),
                "actual_coordinate_sha256": str(
                    fresh_cells[cell_index]["actual_coordinate_sha256"]
                ),
                "fresh_map_identity": dict(
                    state["cells"][str(cell_index)]["fresh_map_identity"]
                ),
                "fresh_map_identity_sha256": str(
                    state["cells"][str(cell_index)]["fresh_map_identity_sha256"]
                ),
                "fresh_map_artifacts": dict(
                    state["cells"][str(cell_index)]["fresh_map_artifacts"]
                ),
                "source": "RECONSTRUCTED_SELECTED_CELL",
                "strict_lu_residual": float(
                    cell_candidates[cell_index]["strict_lu_residual"]
                ),
                "candidate_artifacts": dict(
                    cell_candidates[cell_index]["artifacts"]
                ),
                "columns": [
                    cell_terms[(column_index, cell_index)]["row_record"]
                    for column_index in range(2)
                ],
            }
            for cell_index in TASK41_P0_V17_SELECTED_CELLS
        ],
        "columns": [rhs_results[(column_index, -1)] for column_index in range(2)],
        "scope_note": (
            "Only active row 1622464 and cells 7873/8014 were evaluated. "
            "This local replay does not pass or reopen any full-owner, carrier, "
            "surface, full-q, or official-result gate."
        ),
    }
    checkpoint("v17_selected_two_cell_candidate_callback", result)
    return result


def _run_v17_selected_two_cell_replay(args: argparse.Namespace) -> dict[str, Any]:
    """Run the strict V17 worker without loading any legacy full V4 donor."""
    import json
    import re

    import ufl
    from dolfinx import fem
    from mpi4py import MPI

    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.runners.task40_v20_stage_runner import _resource_snapshot
    from src.runners.task41_p0_checker import (
        TASK41_P0_B0_V17_SELECTED_METADATA_RELATIVE,
        TASK41_P0_B0_V17_SELECTED_METADATA_SHA256,
        TASK41_P0_B0_V17_SELECTED_ROW,
        TASK41_P0_B0_V3_DONOR_MANIFEST_SHA256,
        TASK41_P0_B0_V3_VECTOR_INDEX_SHA256,
        load_task41_p0_b0_v16_saved_vector_manifest,
        load_task41_p0_b0_v17_selected_cell_metadata,
        load_task41_p0_b0_v17_v3_selected_donor,
    )
    from src.runners.task41_p0_contract import (
        TASK41_B0_V17_SAVED_VECTOR_MANIFEST_RELATIVE,
        TASK41_B0_V17_SAVED_VECTOR_MANIFEST_SHA256,
        load_task41_p0_fixed_window,
        require_task41_p0_contract,
        sha256_file,
    )
    from src.solvers.common_3d_forms import _build_physical_volume_terms
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
    from src.solvers.hcurl_assembly_time_condensation import (
        _cell_integral_kernels,
        build_selected_volume_trace_star_metadata,
    )
    from src.solvers.task40_v22_operator_probe import _resource_admission
    from src.solvers.task41_actual_qmetric_blocked_gram import (
        IDENTITY as V17_CANDIDATE_IDENTITY,
        Task41ActualQMetricBlockedGramCandidate,
    )

    root = ROOT.resolve(strict=True)
    contract_path = Path(args.v17_consumer_contract).resolve(strict=True)
    if contract_path.is_symlink():
        raise ValueError("V17 consumer contract cannot be a symlink")
    contract, contract_sha = require_task41_p0_contract(
        contract_path,
        expected_sha256=args.v17_consumer_contract_sha256,
        current_root=root,
        case_id="B0",
    )
    fixed_window = load_task41_p0_fixed_window(contract, current_root=root)
    results_root = (root / "results" / str(contract["case"]["model_id"])).resolve(strict=True)
    manifest_path = Path(args.v16_saved_vector_manifest)
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    expected_manifest = (root / TASK41_B0_V17_SAVED_VECTOR_MANIFEST_RELATIVE).resolve(strict=True)
    if (
        manifest_path.is_symlink()
        or manifest_path.resolve(strict=True) != expected_manifest
        or args.v16_saved_vector_manifest_sha256 != TASK41_B0_V17_SAVED_VECTOR_MANIFEST_SHA256
    ):
        raise ValueError("V17 worker V16 manifest path/hash differs from the frozen binding")
    output_directory = Path(args.output_dir).resolve(strict=True)
    expected_output = Path(os.environ.get("TASK41_P0_V17_OUTPUT_DIRECTORY", "")).resolve()
    if (
        output_directory != expected_output
        or not output_directory.is_relative_to(results_root)
        or output_directory.parent.name != "selected_incident_replay"
        or re.fullmatch(r"attempt[0-9]{2,}", output_directory.name) is None
        or output_directory.is_symlink()
        or not output_directory.is_dir()
    ):
        raise ValueError("V17 worker output directory is not the service-prepared numbered attempt")
    if (
        os.environ.get("TASK41_P0_V17_SELECTED_TWO_CELL_REPLAY") != "1"
        or os.environ.get("TASK41_P0_STRICT_EXECUTION") != "1"
        or os.environ.get("TASK41_P0_EXPECTED_SOURCE_SHA") != contract["source"]["sha"]
    ):
        raise ValueError("V17 worker is outside its registered strict service environment")

    service_directory = output_directory.with_name(output_directory.name + ".service")
    progress_path = output_directory / "task41_p0_v17_progress.json"
    progress_log_path = output_directory / "task41_p0_v17_progress.jsonl"
    report_path = output_directory / "task41_p0_v17_selected_two_cell_worker.json"
    if report_path.exists() or report_path.is_symlink():
        raise FileExistsError("V17 worker report must be a new file")
    resume_progress: Mapping[str, Any] | None = None
    producer_contract_path: Path | None = None
    producer_contract_sha256: str | None = None
    producer_progress_path: Path | None = None
    producer_progress_sha256: str | None = None
    if args.v17_producer_progress is not None:
        producer_contract_raw = Path(args.v17_producer_contract)
        producer_progress_raw = Path(args.v17_producer_progress)
        if producer_contract_raw.is_symlink() or producer_progress_raw.is_symlink():
            raise ValueError("V17 readonly producer contract/progress cannot be symlinks")
        producer_contract_path = producer_contract_raw.resolve(strict=True)
        producer_progress_path = producer_progress_raw.resolve(strict=True)
        producer_contract_sha256 = str(args.v17_producer_contract_sha256)
        producer_progress_sha256 = str(args.v17_producer_progress_sha256)
        producer_contract, checked_producer_sha = require_task41_p0_contract(
            producer_contract_path,
            expected_sha256=producer_contract_sha256,
            current_root=root,
            require_clean_source=False,
            check_current_source=False,
            case_id="B0",
        )
        producer_window = producer_contract.get("window", {})
        if (
            producer_contract_sha256 != checked_producer_sha
            or not producer_contract_path.is_relative_to(root / "benchmarks/artifacts")
            or producer_contract.get("execution_scope") != contract.get("execution_scope")
            or producer_contract.get("case") != contract.get("case")
            or producer_contract.get("numerical_strategy") != contract.get("numerical_strategy")
            or producer_contract.get("source", {}).get("sha") == contract.get("source", {}).get("sha")
            or producer_window.get("path") != contract.get("window", {}).get("path")
            or producer_window.get("sha256") != fixed_window.sha256
            or not producer_progress_path.is_relative_to(results_root)
            or producer_progress_path.name != "task41_p0_v17_progress.json"
            or producer_progress_path.stat().st_size > 16 * 1024**2
            or not re.fullmatch(r"[0-9a-f]{64}", producer_progress_sha256)
            or sha256_file(producer_progress_path) != producer_progress_sha256
        ):
            raise ValueError("V17 readonly producer progress/contract differs from the new consumer")
        expected_producer_binding = {
            "path": str(producer_contract_path.relative_to(root)),
            "sha256": producer_contract_sha256,
            "source_sha": producer_contract.get("source", {}).get("sha"),
            "fixed_window_sha256": fixed_window.sha256,
        }
        producer_progress_payload = json.loads(
            producer_progress_path.read_text(encoding="utf-8")
        )
        history = producer_progress_payload.get("consumer_execution_bindings")
        latest = producer_progress_payload.get("latest_consumer_execution_binding")
        if latest is None and isinstance(history, list) and history:
            latest = history[-1]
        if (
            not isinstance(producer_progress_payload, Mapping)
            or producer_progress_payload.get("schema") != "task41.p0.b0.v17.selected_two_cell_progress.v2"
            or producer_progress_payload.get("producer_execution_binding", {}).get(
                "fixed_window_sha256"
            ) != fixed_window.sha256
            or not isinstance(history, list)
            or expected_producer_binding not in history
            or latest != expected_producer_binding
        ):
            raise ValueError("V17 readonly progress is not bound to the explicit producer contract")
        producer_report = producer_progress_path.parent / "task41_p0_v17_selected_two_cell_worker.json"
        if producer_report.exists() or producer_report.is_symlink():
            raise ValueError("V17 producer report appeared after service selected progress-resume mode")
        resume_progress = producer_progress_payload
    elif progress_path.exists():
        if progress_path.is_symlink() or progress_path.stat().st_size > 16 * 1024**2:
            raise ValueError("V17 progress checkpoint is symlinked or exceeds its size bound")
        resume_progress = json.loads(progress_path.read_text(encoding="utf-8"))
        if not isinstance(resume_progress, Mapping):
            raise ValueError("V17 progress checkpoint must be a JSON object")

    pre_admission_path = Path(args.v17_pre_admission)
    expected_pre_admission_path = service_directory / "task41_p0_v17_pre_admission.json"
    if (
        pre_admission_path.is_symlink()
        or pre_admission_path.resolve(strict=True) != expected_pre_admission_path.resolve(strict=True)
        or pre_admission_path.stat().st_size > 1024**2
        or not re.fullmatch(r"[0-9a-f]{64}", str(args.v17_pre_admission_sha256))
        or sha256_file(pre_admission_path) != args.v17_pre_admission_sha256
    ):
        raise ValueError("V17 worker service pre-admission path or hash differs")
    pre_admission = json.loads(pre_admission_path.read_text(encoding="utf-8"))
    if (
        not isinstance(pre_admission, Mapping)
        or pre_admission.get("schema") != "task41.p0.b0.v17.selected_two_cell_pre_admission.v1"
        or pre_admission.get("consumer_contract_sha256") != contract_sha
        or pre_admission.get("consumer_window_sha256") != fixed_window.sha256
        or pre_admission.get("v16_saved_vector_manifest_sha256") != TASK41_B0_V17_SAVED_VECTOR_MANIFEST_SHA256
        or pre_admission.get("output_directory") != str(output_directory)
        or pre_admission.get("service_directory") != str(service_directory.resolve(strict=True))
        or pre_admission.get("producer_contract_path")
        != (str(producer_contract_path) if producer_contract_path is not None else None)
        or pre_admission.get("producer_contract_sha256") != producer_contract_sha256
        or pre_admission.get("producer_progress_path")
        != (str(producer_progress_path) if producer_progress_path is not None else None)
        or pre_admission.get("producer_progress_sha256") != producer_progress_sha256
    ):
        raise ValueError("V17 worker pre-admission is not bound to this input and output scope")

    def progress(event: Mapping[str, Any]) -> None:
        line = json.dumps(dict(event), ensure_ascii=False, sort_keys=True, allow_nan=False)
        with progress_log_path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def checkpoint(name: str, payload: Mapping[str, Any]) -> None:
        _task41_p0_v17_checkpoint_progress(progress_path, name, payload)

    def persist_array(name: str, value: np.ndarray) -> dict[str, Any]:
        return _persist_array(output_directory, name, value, sha256_file=sha256_file)

    resources = contract["resources"]
    raw_cap = 16 * 1024**3
    evidence_cap = 128 * 1024**2
    free_floor = 2 * 1024**3
    minimum_work_seconds = 900.0
    termination_reserve_seconds = 120.0
    planned_workspace_bytes = 16 * 1024**3

    def current_window_output_bytes() -> int:
        total = 0
        window_output_root = output_directory.parent.parent
        if (
            output_directory.parent.name != "selected_incident_replay"
            or not window_output_root.is_dir()
            or window_output_root.is_symlink()
        ):
            raise ValueError("V17 output is outside the prepared fixed-window inventory root")
        for item in window_output_root.rglob("*"):
            if item.is_symlink():
                raise ValueError("V17 fixed-window output inventory cannot contain symlinks")
            if item.is_file():
                total += int(item.stat().st_size)
        return total

    def check_window_balance() -> float:
        from src.runners.task40_v10_campaign import read_campaign_state

        campaign_state = read_campaign_state(fixed_window, phase="numeric")
        remaining = float(campaign_state["remaining_phase_seconds"])
        required = minimum_work_seconds + termination_reserve_seconds
        if not math.isfinite(remaining) or remaining < required:
            raise RuntimeError(
                "V17 selected replay requires at least 900 s work estimate + 120 s "
                f"termination reserve; numeric balance is {remaining:.3f} s"
            )
        return remaining

    def check_evidence_inventory() -> dict[str, int]:
        budget = pre_admission.get("saved_diagnostics_disk_budget")
        if not isinstance(budget, Mapping):
            raise ValueError("V17 service pre-admission omits its saved-evidence inventory")
        recorded = budget.get("recorded_cumulative_raw_artifact_bytes")
        bound = budget.get("bound_raw_artifact_bytes_stat_deduplicated")
        before = budget.get("window_output_tree_bytes")
        if (
            budget.get("status") != "PRE_CHECKER_ADMITTED"
            or budget.get("window_wide_new_evidence_limit_bytes") != evidence_cap
            or budget.get("cumulative_raw_artifact_limit_bytes") != raw_cap
            or budget.get("free_space_floor_bytes") != free_floor
            or type(recorded) is not int or recorded < 0
            or type(bound) is not int or bound < 0
            or type(before) is not int or before < 0
        ):
            raise ValueError("V17 service evidence inventory has invalid limits or counters")
        current = current_window_output_bytes()
        if current < before or current > evidence_cap:
            raise OSError("V17 fixed-window outputs changed outside the admitted evidence cap")
        reserve = evidence_cap - current
        cumulative_with_reserved_cap = max(recorded, bound) + current + reserve
        if cumulative_with_reserved_cap > raw_cap:
            raise OSError("V17 fixed-window evidence reserve exceeds the cumulative 16 GiB raw cap")
        free_bytes = int(shutil.disk_usage(output_directory).free)
        if free_bytes < free_floor + reserve:
            raise OSError("V17 output inventory no longer preserves its 2 GiB free-space floor")
        return {
            "recorded_cumulative_raw_artifact_bytes": recorded,
            "bound_raw_artifact_bytes_stat_deduplicated": bound,
            "window_output_tree_bytes_before_worker": before,
            "window_output_tree_bytes_at_gate": current,
            "cumulative_raw_artifact_limit_bytes": raw_cap,
            "new_evidence_limit_bytes": evidence_cap,
            "reserved_remaining_new_evidence_bytes": reserve,
            "free_space_bytes": free_bytes,
            "free_space_floor_bytes": free_floor,
        }

    def allocation_gate(label: str, facts: Mapping[str, Any]) -> None:
        _checked_allocation_gate(
            label,
            facts,
            resource_admission=_resource_admission,
            resource_snapshot=_resource_snapshot,
            resources=resources,
            progress=progress,
        )
        free_bytes = int(shutil.disk_usage(output_directory).free)
        required_free = (
            int(facts.get("free_space_floor_bytes", 0))
            + int(facts.get("additional_payload_bytes", 0))
            + int(facts.get("scratch_reserve_bytes", 0))
        )
        if free_bytes < required_free:
            raise OSError("V17 worker allocation gate failed its free-space floor")

    # Check the live window before loading the saved arrays, then again immediately
    # before fresh FE preparation so preparation cannot consume the protected reserve.
    check_window_balance()
    check_evidence_inventory()

    v16_manifest, saved_vectors, _unused_group_codes = (
        load_task41_p0_b0_v16_saved_vector_manifest(
            manifest_path,
            TASK41_B0_V17_SAVED_VECTOR_MANIFEST_SHA256,
            repo_root=root,
            include_saved_array_replay=False,
            include_row_incidence=False,
        )
    )
    v16_metadata = load_task41_p0_b0_v17_selected_cell_metadata(repo_root=root)
    donor = load_task41_p0_b0_v17_v3_selected_donor(
        repo_root=root, results_root=results_root
    )
    if (
        donor["manifest_sha256"] != TASK41_P0_B0_V3_DONOR_MANIFEST_SHA256
        or donor["source_index_sha256"] != TASK41_P0_B0_V3_VECTOR_INDEX_SHA256
    ):
        raise ValueError("V17 worker V3 donor/index differs from its pinned source")
    donor_run_root = Path(donor["manifest_path"]).resolve(strict=True).parent
    resolved_config_path = (donor_run_root / "resolved_config.json").resolve(strict=True)
    if (
        not resolved_config_path.is_relative_to(results_root)
        or sha256_file(resolved_config_path)
        != contract.get("case", {}).get("resolved_config_sha256")
    ):
        raise ValueError("V17 worker resolved config differs from the frozen B0 case")
    config_value = json.loads(resolved_config_path.read_text(encoding="utf-8"))
    cfg = simulation_config_3d_from_normalized(config_value)

    ffcx_c_source = Path(args.ffcx_c_source).resolve(strict=True)
    if (
        ffcx_c_source.is_symlink()
        or not ffcx_c_source.is_relative_to(root)
        or ffcx_c_source.relative_to(root) != TASK41_P0_V17_FFCX_C_SOURCE_RELATIVE
        or sha256_file(ffcx_c_source) != TASK41_P0_V11_FFCX_C_SOURCE_SHA256
    ):
        raise ValueError("V17 worker FFCx source path/hash differs from the frozen q-metric source")

    progress({"phase": "v17_worker_inputs", "status": "STARTED"})
    remaining_numeric_seconds = check_window_balance()
    evidence_inventory = check_evidence_inventory()
    allocation_gate(
        "v17_selected_two_cell_prebuild_admission",
        {
            "additional_payload_bytes": 74_684_304 + 8 * 1024**2,
            "workspace_bytes": planned_workspace_bytes,
            "scratch_reserve_bytes": 512 * 1024**2,
            "free_space_floor_bytes": free_floor,
            "estimated_remaining_seconds_upper": minimum_work_seconds,
            "termination_reserve_seconds": termination_reserve_seconds,
            "candidate_builds_max": 2,
            "candidate_lu_factorizations_max": 2,
            "matrix_rhs_getrs_max": 6,
            "internal_rhs_count": 4,
            "internal_rhs_getrs_max": 12,
            "selected_active_row": TASK41_P0_V17_ACTIVE_ROW,
            "selected_original_row": TASK41_P0_V17_ORIGINAL_ROW,
            "selected_cells": list(TASK41_P0_V17_SELECTED_CELLS),
        },
    )
    progress({
        "phase": "v17_prebuild_admission",
        "status": "PASSED",
        "remaining_numeric_seconds": remaining_numeric_seconds,
        "minimum_work_seconds": minimum_work_seconds,
        "termination_reserve_seconds": termination_reserve_seconds,
        "planned_workspace_bytes": planned_workspace_bytes,
        "evidence_inventory": evidence_inventory,
    })
    levels = _build_same_mesh_levels(
        cfg, MPI.COMM_SELF, (6,), include_positive_coefficients=False
    )
    space = levels["spaces"][6]
    floquet = levels["floquets"][6]
    fresh_metadata = build_selected_volume_trace_star_metadata(
        space,
        floquet.mpc,
        levels["mesh_data"].cell_tags,
        selected_active_row=TASK41_P0_V17_ACTIVE_ROW,
        expected_active_original_rows=np.asarray(
            donor["columns"][0]["active_original_rows"], dtype=np.int64
        ),
        selected_cell_indices=TASK41_P0_V17_SELECTED_CELLS,
        progress_callback=progress,
    )
    trial, test = ufl.TrialFunction(space), ufl.TestFunction(space)
    dx = ufl.Measure("dx", domain=levels["mesh"], subdomain_data=levels["mesh_data"].cell_tags)
    curl_form, mass_form = _build_physical_volume_terms(cfg, trial, test, dx)
    combined_integrand = curl_form + mass_form
    combined_form = fem.form(combined_integrand, jit_options=dict(SAME_MESH_JIT_OPTIONS))
    kernels = _cell_integral_kernels(combined_form, sum_duplicate_cell_integrals=True)
    candidate_evaluator = Task41ActualQMetricBlockedGramCandidate(
        space.element.basix_element,
        combined_integrand,
        combined_form,
        c_source_path=ffcx_c_source,
        scratch_directory=output_directory / "actual_qmetric_scratch",
    )
    if candidate_evaluator.identity != V17_CANDIDATE_IDENTITY:
        raise ValueError("V17 worker actual-qmetric evaluator identity differs")
    callback = _run_v17_selected_two_cell_candidate_callback(
        consumer_contract=contract,
        consumer_contract_sha256=contract_sha,
        consumer_contract_path=contract_path,
        fixed_window=fixed_window,
        v16_metadata=v16_metadata,
        v16_metadata_path=root / TASK41_P0_B0_V17_SELECTED_METADATA_RELATIVE,
        v16_metadata_sha256=TASK41_P0_B0_V17_SELECTED_METADATA_SHA256,
        v16_saved_vector_manifest=v16_manifest,
        v16_saved_vector_manifest_path=manifest_path,
        v16_saved_vector_manifest_sha256=TASK41_B0_V17_SAVED_VECTOR_MANIFEST_SHA256,
        saved_vectors=saved_vectors,
        donor=donor,
        fresh_metadata=fresh_metadata,
        element=space.element,
        combined_form=combined_form,
        kernels=kernels,
        candidate_evaluator=candidate_evaluator,
        output_directory=output_directory,
        results_root=results_root,
        sha256_file=sha256_file,
        allocation_gate=allocation_gate,
        persist_array=persist_array,
        progress=progress,
        checkpoint=checkpoint,
        resume_progress=resume_progress,
    )
    payload = {
        "schema": "task41.p0.b0.v17.selected_two_cell_worker_receipt.v1",
        "status": "COMPLETED_LOCAL_SELECTED_TWO_CELL_REPLAY",
        "consumer_contract_sha256": contract_sha,
        "consumer_window_sha256": fixed_window.sha256,
        "v16_metadata_sha256": TASK41_P0_B0_V17_SELECTED_METADATA_SHA256,
        "v16_saved_vector_manifest_sha256": TASK41_B0_V17_SAVED_VECTOR_MANIFEST_SHA256,
        "v3_donor_manifest_sha256": donor["manifest_sha256"],
        "v3_vector_index_sha256": donor["source_index_sha256"],
        "selected_two_cell_candidate_callback": callback,
        "official_result": False,
        "scientific_qualified": False,
        "full_owner_unlocked": False,
    }
    from src.runners.task41_p0_checker import _task41_p0_v16_write_new_json

    _task41_p0_v16_write_new_json(report_path, payload)
    return {
        "report_path": str(report_path.resolve()),
        "report_sha256": sha256_file(report_path),
        "report_bytes": int(report_path.stat().st_size),
        "status": payload["status"],
        "callback": callback,
    }


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
    metadata_only: bool = False,
    selected_active_row: int = TASK41_P0_V8_SELECTED_ACTIVE_ROW,
) -> dict[str, Any]:
    """Replay saved B0 operands and only the V8 target row's complete cell star."""

    if metadata_only:
        return _run_v8_selected_trace_star_metadata_only(
            cfg=cfg,
            donor=donor,
            fixed_window=fixed_window,
            output_directory=output_directory,
            consumer_contract=consumer_contract,
            selected_active_row=selected_active_row,
            allocation_gate=allocation_gate,
            persist_array=persist_array,
            progress=progress,
            checkpoint=checkpoint,
        )

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
    selected_row = int(selected_active_row)
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


def _v11_accumulate_saved_candidate_row_terms(
    *,
    native_rhs_row: complex,
    native_action_row: complex,
    b_alpha_row: complex,
    s_cell_terms: list[complex],
    same_lu_cell_terms: list[complex],
    stored_t_cell_terms: list[complex],
    delta_t_cell_terms: list[complex],
    cs_t_cell_terms: list[complex],
    j_middle_cell_terms: list[complex],
    minus_j_z_r_cell_terms: list[complex],
) -> dict[str, complex]:
    """Apply production row ordering and the V11 row identity's one global terms."""

    cell_lengths = {
        len(s_cell_terms),
        len(same_lu_cell_terms),
        len(stored_t_cell_terms),
        len(delta_t_cell_terms),
        len(cs_t_cell_terms),
        len(j_middle_cell_terms),
        len(minus_j_z_r_cell_terms),
    }
    if len(cell_lengths) != 1:
        raise ValueError("V11 selected row term lists have different incident-cell coverage")
    y_value = 0.0 + 0.0j
    g_same_lu = complex(native_rhs_row)
    g_stored_t = complex(native_rhs_row)
    review_rhs = 0.0 + 0.0j
    review_lu_residual = 0.0 + 0.0j
    for s_term, lu_term, stored_t, delta_t, cs_t, j_middle, minus_j_z_r in zip(
        s_cell_terms,
        same_lu_cell_terms,
        stored_t_cell_terms,
        delta_t_cell_terms,
        cs_t_cell_terms,
        j_middle_cell_terms,
        minus_j_z_r_cell_terms,
        strict=True,
    ):
        y_value += complex(s_term)
        g_same_lu += complex(lu_term)
        g_stored_t += complex(stored_t)
        review_rhs += complex(delta_t)
        review_rhs += complex(cs_t)
        review_rhs += complex(j_middle)
        review_lu_residual += complex(minus_j_z_r)
    y_value += complex(b_alpha_row)
    review_rhs -= complex(native_action_row)
    residual_row = complex(native_rhs_row) - complex(native_action_row) - complex(b_alpha_row)
    return {
        "y9": y_value,
        "g9_same_lu": g_same_lu,
        "g9_stored_t": g_stored_t,
        "d_lu": y_value - g_same_lu,
        "native_residual_row": residual_row,
        "review_eq1_lhs": y_value - g_same_lu + residual_row + review_lu_residual,
        "review_eq1_rhs": review_rhs,
    }


def _v11_local_replay_delta_diagnostic(
    *,
    saved_value: complex,
    replayed_value: complex,
    original_d: complex,
    roundoff_estimate: float,
) -> dict[str, Any]:
    """Keep the conservative arithmetic bound separate from replay conclusions."""

    delta = complex(replayed_value) - complex(saved_value)
    d_abs = abs(complex(original_d))
    delta_abs = abs(delta)
    return {
        "saved_value": complex(saved_value),
        "replayed_value": complex(replayed_value),
        "delta_replay_minus_saved": delta,
        "delta_absolute": float(delta_abs),
        "original_d": complex(original_d),
        "original_d_absolute": float(d_abs),
        "delta_relative_to_original_d": (
            float(delta_abs / d_abs) if d_abs > 0.0 else None
        ),
        "roundoff_estimate": float(roundoff_estimate),
        "roundoff_estimate_contains_difference": bool(
            delta_abs <= float(roundoff_estimate)
        ),
        # The gamma*N estimate is a conservative diagnostic bound. It is not
        # an acceptance threshold or evidence of causal closure.
        "status": (
            "EXACT_SAVED_VALUE_REPRODUCED"
            if delta_abs == 0.0
            else "LOCAL_REPLAY_UNBOUND"
        ),
    }



def _task41_p0_v11_metadata_accounting_path_matches(
    metadata_window_state: Mapping[str, Any],
    old_window: Any,
) -> bool:
    """Bind the saved receipt path to the accounting ledger, not the window JSON."""

    return metadata_window_state.get("path") == str(old_window.accounting_path)


def _v11_candidate_cell_reuse_identity(
    *,
    consumer_contract: Mapping[str, Any],
    fixed_window: Any,
    donor_manifest_sha256: str,
    metadata_report_sha256: str,
    v9_compact_report_sha256: str,
    evaluator_identity: str,
    cache_identity: str,
    ffcx_c_source_sha256: str,
    row: Mapping[str, Any],
) -> dict[str, Any]:
    """Identify the numerical inputs that make one saved local cell reusable.

    The consumer source/contract SHA is intentionally excluded: fixing worker
    orchestration or checkpoint code must not invalidate unchanged local FE
    products. The fixed authorization/window, source artifacts, form/cache,
    cell coordinates and local partition remain exact reuse boundaries.
    """
    import hashlib
    import json

    def digest_json(value: Any) -> str:
        raw = json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    case = consumer_contract.get("case")
    window = consumer_contract.get("window")
    if not isinstance(case, Mapping) or not isinstance(window, Mapping):
        raise ValueError("V11 cell reuse requires bound consumer case and window objects")
    fixed_payload = fixed_window.payload
    cell_index = int(row["cell_index"])
    identity = {
        "schema": "task41.p0.v12.candidate_cell_reuse_identity.v1",
        "case": {
            key: case.get(key)
            for key in (
                "model_id",
                "run_id",
                "input_sha256",
                "physical_model_sha256",
                "resolved_config_sha256",
                "method",
                "mpi_size",
                "profile_identity",
                "solver_stage",
                "geometry_identity",
            )
        },
        "numerical_strategy": consumer_contract.get("numerical_strategy"),
        "window": {
            "path": str(fixed_window.path),
            "sha256": fixed_window.sha256,
            "entry_source_sha": window.get("entry_source_sha"),
            "authorization_sha256": window.get("authorization_sha256"),
            "scope": window.get("scope"),
            "source_sha_in_window": fixed_payload.get("source_sha"),
            "prior_window_path": window.get("prior_window_path"),
            "prior_window_sha256": window.get("prior_window_sha256"),
            "prior_ledger_path": window.get("prior_ledger_path"),
            "prior_ledger_sha256": window.get("prior_ledger_sha256"),
        },
        "donor_manifest_sha256": donor_manifest_sha256,
        "selected_metadata_report_sha256": metadata_report_sha256,
        "v9_compact_report_sha256": v9_compact_report_sha256,
        "candidate_evaluator_identity": evaluator_identity,
        "candidate_cache_identity": cache_identity,
        "ffcx_c_source_sha256": ffcx_c_source_sha256,
        "integration": {
            "identity": "task41.p0.v11.same_mesh_p6.curl_plus_mass.v1",
            "degree": 6,
            "sum_duplicate_cell_integrals": True,
            "internal_rhs_strategy": "same_lu_rhs_solve",
        },
        "cell": {
            "cell_index": cell_index,
            "cell_tag": int(row["cell_tag"]),
            "cell_permutation": int(row["cell_permutation"]),
            "actual_coordinate_sha256": row["actual_coordinate_sha256"],
            "element_dimension": int(row["element_dimension"]),
            "interior_positions_sha256": digest_json(
                np.asarray(row["interior_positions"], dtype=np.int64).tolist()
            ),
            "trace_positions_sha256": digest_json(
                np.asarray(row["trace_positions"], dtype=np.int64).tolist()
            ),
        },
    }
    return identity


def _v11_prior_candidate_cell_progress(
    prior_report: Mapping[str, Any],
    *,
    prior_report_path: Path,
    fixed_window: Any,
    consumer_contract: Mapping[str, Any],
    donor_manifest_sha256: str,
    metadata_report_path: Path,
    metadata_report_sha256: str,
    v9_compact_report_path: Path,
    v9_compact_report_sha256: str,
    current_root: Path,
    require_contract: Any,
) -> Mapping[str, Any] | None:
    """Validate the failed/completed producer envelope before reading its cells."""
    import re

    if prior_report.get("schema") != (
        "task41.p0.v11.selected_trace_star_candidate_replay_receipt.v1"
    ):
        return None
    progress = prior_report.get("v11_selected_candidate_cell_progress")
    if progress is None:
        return None
    if not isinstance(progress, Mapping) or progress.get("schema") != (
        "task41.p0.v11.selected_candidate_cell_progress.v1"
    ):
        raise ValueError(
            f"completed candidate progress in {prior_report_path} has an invalid schema"
        )
    cells = progress.get("cells")
    completed = progress.get("completed_cells")
    if not isinstance(cells, Mapping) or not isinstance(completed, list):
        raise ValueError(
            f"candidate progress in {prior_report_path} omits its completed-cell inventory"
        )
    if any(type(value) is not int for value in completed) or len(set(completed)) != len(completed):
        raise ValueError(f"candidate progress in {prior_report_path} has a malformed cell inventory")
    declared = {
        int(key)
        for key, value in cells.items()
        if isinstance(key, str)
        and key.isdigit()
        and isinstance(value, Mapping)
        and value.get("completion_status") == "CELL_COMPLETE"
    }
    if not completed and not declared:
        return None
    expected_cells = set(TASK41_P0_V11_SELECTED_CELLS)
    if not set(completed).issubset(expected_cells) or set(completed) != declared:
        raise ValueError(
            f"candidate progress in {prior_report_path} has inconsistent complete-cell markers"
        )

    window_path = str(fixed_window.path)
    if (
        prior_report.get("consumer_window_path") != window_path
        or prior_report.get("consumer_window_sha256") != fixed_window.sha256
        or prior_report.get("selected_metadata_report_path")
        != str(metadata_report_path.resolve())
        or prior_report.get("selected_metadata_report_sha256")
        != metadata_report_sha256
        or prior_report.get("v9_compact_report_path")
        != str(v9_compact_report_path.resolve())
        or prior_report.get("v9_compact_report_sha256")
        != v9_compact_report_sha256
        or prior_report.get("donor_manifest_sha256") != donor_manifest_sha256
    ):
        raise ValueError(
            f"completed candidate cells in {prior_report_path} have mismatched producer/window bindings"
        )
    old_source_sha = prior_report.get("consumer_source_sha")
    old_contract_sha = prior_report.get("consumer_contract_sha256")
    old_contract_path_value = prior_report.get("consumer_contract_path")
    if (
        not isinstance(old_source_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", old_source_sha) is None
        or not isinstance(old_contract_sha, str)
        or re.fullmatch(r"[0-9a-f]{64}", old_contract_sha) is None
        or not isinstance(old_contract_path_value, str)
    ):
        raise ValueError(
            f"completed candidate cells in {prior_report_path} omit their source/contract binding"
        )
    from src.runners.task41_p0_contract import (
        TASK41_B0_V12_CANDIDATE_REPLAY_INSTANCE,
        contract_relative_path,
    )

    old_contract_path = Path(old_contract_path_value).resolve(strict=True)
    expected_old_path = (
        current_root
        / contract_relative_path(
            old_source_sha,
            "B0",
            saved_diagnostics_instance=TASK41_B0_V12_CANDIDATE_REPLAY_INSTANCE,
        )
    ).resolve()
    if old_contract_path != expected_old_path:
        raise ValueError(
            f"completed candidate cells in {prior_report_path} point to an unregistered contract"
        )
    old_contract, old_digest = require_contract(
        old_contract_path,
        expected_sha256=old_contract_sha,
        current_root=current_root,
        check_current_source=False,
        require_clean_source=False,
        case_id="B0",
    )
    current_window = consumer_contract.get("window")
    old_window = old_contract.get("window")
    if (
        old_digest != old_contract_sha
        or old_contract.get("source", {}).get("sha") != old_source_sha
        or prior_report.get("consumer_contract_path") != str(old_contract_path)
        or not isinstance(old_window, Mapping)
        or not isinstance(current_window, Mapping)
        or any(
            old_window.get(key) != current_window.get(key)
            for key in (
                "path",
                "sha256",
                "entry_source_sha",
                "authorization_sha256",
                "scope",
                "prior_window_path",
                "prior_window_sha256",
                "prior_ledger_path",
                "prior_ledger_sha256",
            )
        )
        or old_window.get("sha256") != fixed_window.sha256
        or old_window.get("entry_source_sha")
        != fixed_window.payload.get("source_sha")
        or any(
            old_contract.get(key) != consumer_contract.get(key)
            for key in (
                "task_id",
                "branch",
                "case",
                "runtime",
                "resources",
                "time",
                "numerical_strategy",
                "execution_scope",
                "preparation",
            )
        )
        or old_contract.get("evidence", {}).get("raw_disk_policy")
        != consumer_contract.get("evidence", {}).get("raw_disk_policy")
    ):
        raise ValueError(
            f"completed candidate cells in {prior_report_path} are not bound to the same authorized numerical inputs"
        )
    return progress


def _v11_load_completed_candidate_cell(
    saved_cell: Mapping[str, Any],
    *,
    expected_reuse_identity: Mapping[str, Any],
    results_root: Path,
    dimension: int,
    interior_count: int,
    trace_count: int,
    sha256_file: Any,
) -> dict[str, Any] | None:
    """Hash-check every declared-complete array, then reuse only an exact math identity."""
    import hashlib
    import json
    import math

    cell_index = int(expected_reuse_identity["cell"]["cell_index"])
    artifact_records = saved_cell.get("candidate_artifacts")
    if (
        saved_cell.get("completion_status") != "CELL_COMPLETE"
        or saved_cell.get("cell_index") != cell_index
        or not isinstance(artifact_records, Mapping)
        or set(artifact_records)
        != {"raw_tensor", "oriented_tensor", "R", "T", "S", "interior_lu", "interior_lu_pivots"}
    ):
        raise ValueError(f"declared-complete candidate cell {cell_index} has incomplete artifacts")
    recorded_identity = saved_cell.get("reuse_identity")
    recorded_identity_sha = saved_cell.get("reuse_identity_sha256")
    if not isinstance(recorded_identity, Mapping) or not isinstance(recorded_identity_sha, str):
        raise ValueError(f"declared-complete candidate cell {cell_index} omits its reuse identity")
    identity_raw = json.dumps(
        recorded_identity, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    if hashlib.sha256(identity_raw).hexdigest() != recorded_identity_sha:
        raise ValueError(f"declared-complete candidate cell {cell_index} has a corrupt reuse-identity hash")

    loaded: dict[str, np.ndarray] = {}
    for name, record in artifact_records.items():
        if not isinstance(record, Mapping):
            raise ValueError(f"declared-complete candidate cell {cell_index} omits {name} metadata")
        try:
            array, _identity = _v8_load_bound_array(
                record,
                results_root=results_root,
                path_basis=ROOT,
                sha256_file=sha256_file,
            )
        except (OSError, ValueError) as exc:
            raise ValueError(
                f"declared-complete candidate cell {cell_index} artifact {name} failed path/hash/layout verification: {exc}"
            ) from exc
        loaded[name] = np.asarray(array)
    expected_shapes = {
        "raw_tensor": (dimension, dimension),
        "oriented_tensor": (dimension, dimension),
        "R": (interior_count, trace_count),
        "T": (trace_count, interior_count),
        "S": (trace_count, trace_count),
        "interior_lu": (interior_count, interior_count),
        "interior_lu_pivots": (interior_count,),
    }
    for name, shape in expected_shapes.items():
        if loaded[name].shape != shape:
            raise ValueError(
                f"declared-complete candidate cell {cell_index} artifact {name} shape differs"
            )
    for name in expected_shapes.keys() - {"interior_lu_pivots"}:
        if loaded[name].dtype != np.dtype(np.complex128):
            raise ValueError(
                f"declared-complete candidate cell {cell_index} artifact {name} dtype differs"
            )
    if loaded["interior_lu_pivots"].dtype != np.dtype(np.int32):
        raise ValueError(
            f"declared-complete candidate cell {cell_index} pivot dtype differs"
        )
    residual = saved_cell.get("strict_lu_residual")
    if (
        isinstance(residual, bool)
        or not isinstance(residual, (int, float))
        or not math.isfinite(float(residual))
        or float(residual) < 0.0
    ):
        raise ValueError(f"declared-complete candidate cell {cell_index} LU residual is invalid")
    if recorded_identity != expected_reuse_identity:
        return None
    return {
        "source": "RECONSTRUCTED_SELECTED_CELL",
        "raw_tensor": loaded["raw_tensor"],
        "oriented_tensor": loaded["oriented_tensor"],
        "rts": {name: loaded[name] for name in ("R", "T", "S")},
        "lu": loaded["interior_lu"],
        "pivots": loaded["interior_lu_pivots"].astype(np.int32, copy=True),
        "strict_lu_residual": float(residual),
        "raw_tensor_evaluator_identity": recorded_identity.get(
            "candidate_evaluator_identity"
        ),
        "artifacts": dict(artifact_records),
    }


def _task41_v12_curl_mass_integral_profile(
    kernels: Mapping[int, Any],
) -> tuple[list[int], list[int], dict[str, int]]:
    """Bind the prepared curl+mass form to every frozen evaluator material tag."""
    from src.solvers.task41_actual_qmetric_blocked_gram import PROFILE_TAGS

    expected_profile_tags = sorted(int(tag) for tag in PROFILE_TAGS)
    cell_integral_ids = sorted(int(tag) for tag in kernels)
    integral_kernel_counts = {
        str(int(tag)): len(values)
        for tag, values in sorted(kernels.items(), key=lambda item: int(item[0]))
    }
    expected_kernel_counts = {str(tag): 1 for tag in expected_profile_tags}
    if (
        cell_integral_ids != expected_profile_tags
        or integral_kernel_counts != expected_kernel_counts
    ):
        raise ValueError(
            "prepared candidate form integral profile differs from the frozen evaluator: "
            f"ids={cell_integral_ids!r}, expected={expected_profile_tags!r}, "
            f"kernel_counts={integral_kernel_counts!r}"
        )
    return expected_profile_tags, cell_integral_ids, integral_kernel_counts


def _run_v11_selected_trace_star_candidate_replay(
    *,
    args: argparse.Namespace,
    cfg: Any,
    donor: dict[str, Any],
    fixed_window: Any,
    output_directory: Path,
    consumer_contract: Mapping[str, Any],
    consumer_contract_sha256: str,
    sha256_file: Any,
    allocation_gate: Any,
    persist_array: Any,
    progress: Any,
    checkpoint: Any,
) -> dict[str, Any]:
    """Rebuild only the two frozen candidate cells and replay the saved V9 target row."""

    import hashlib
    import json
    import shutil

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
        project_internal_rhs_same_lu,
    )
    from src.solvers.task41_actual_qmetric_blocked_gram import (
        IDENTITY as V6_CANDIDATE_IDENTITY,
        Task41ActualQMetricBlockedGramCandidate,
    )

    if fixed_window is None or fixed_window.sha256 != consumer_contract.get(
        "window", {}
    ).get("sha256"):
        raise ValueError("V11 candidate replay fixed-window hash differs from the consumer contract")
    from src.runners.task41_p0_contract import (
        TASK41_B0_V12_CANDIDATE_REPLAY_SCOPE,
    )

    consumer_window = consumer_contract.get("window")
    consumer_source = consumer_contract.get("source")
    consumer_window_path_value = (
        consumer_window.get("path") if isinstance(consumer_window, Mapping) else None
    )
    consumer_window_path = (
        Path(str(consumer_window_path_value)) if consumer_window_path_value else None
    )
    if consumer_window_path is not None and not consumer_window_path.is_absolute():
        consumer_window_path = ROOT / consumer_window_path
    if (
        consumer_contract.get("execution_scope") != TASK41_B0_V12_CANDIDATE_REPLAY_SCOPE
        or not isinstance(consumer_window, Mapping)
        or not isinstance(consumer_source, Mapping)
        or consumer_window.get("sha256") != fixed_window.sha256
        or consumer_window_path is None
        or consumer_window_path.resolve() != Path(fixed_window.path).resolve()
        or consumer_window.get("entry_source_sha")
        != fixed_window.payload.get("source_sha")
        or consumer_window.get("authorization_sha256")
        != fixed_window.payload.get("authorization_sha256")
    ):
        raise ValueError(
            "V12 candidate replay requires its independent authorization-bound consumer window"
        )
    if args.selected_active_row != TASK41_P0_V11_METADATA_ACTIVE_ROW:
        raise ValueError("V11 candidate replay target row differs from frozen active row 87567")
    if len(donor.get("columns", ())) != 2:
        raise ValueError("V11 candidate replay requires exactly two saved donor columns")
    if args.ffcx_c_source is None or sha256_file(args.ffcx_c_source) != TASK41_P0_V11_FFCX_C_SOURCE_SHA256:
        raise ValueError("V11 candidate replay FFCx source differs from the frozen V9 candidate source")

    results_root = (ROOT / "results" / str(consumer_contract["case"]["model_id"])).resolve()
    metadata_path = args.selected_metadata_report.resolve(strict=True)
    if (
        metadata_path.name != "task41_p0_v8_selected_trace_star_metadata.json"
        or not metadata_path.is_relative_to(results_root)
        or args.selected_metadata_report_sha256 != TASK41_P0_V11_METADATA_REPORT_SHA256
        or sha256_file(metadata_path) != TASK41_P0_V11_METADATA_REPORT_SHA256
    ):
        raise ValueError("V11 selected metadata report path or SHA-256 differs from the frozen attempt02")
    metadata_receipt_path = (
        metadata_path.parent.with_name(metadata_path.parent.name + ".service")
        / "task41_p0_service_receipt.json"
    )
    if sha256_file(metadata_receipt_path) != TASK41_P0_V11_METADATA_SERVICE_RECEIPT_SHA256:
        raise ValueError("V11 metadata service receipt SHA-256 differs from the completed attempt02")
    metadata_receipt = json.loads(metadata_receipt_path.read_text(encoding="utf-8"))
    if (
        metadata_receipt.get("schema") != "task41.p0.saved_output_service_receipt.v1"
        or metadata_receipt.get("status") != "completed"
        or metadata_receipt.get("mode") != "saved_b0_v8_selected_trace_star_metadata_only"
        or metadata_receipt.get("contract_sha256")
        != TASK41_P0_V11_METADATA_CONSUMER_CONTRACT_SHA256
        or metadata_receipt.get("selected_trace_star_metadata_only_result_path")
        != str(metadata_path)
        or metadata_receipt.get("selected_trace_star_metadata_only_status")
        != "metadata_only_completed"
    ):
        raise ValueError("V11 completed metadata service receipt is not bound to attempt02")

    metadata_report = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata = metadata_report.get("selected_trace_star_metadata_only")
    from src.runners.task41_p0_contract import (
        load_task41_p0_fixed_window,
        require_task41_p0_contract,
    )

    old_contract_path = Path(str(metadata_report.get("consumer_contract_path", "")))
    expected_old_contract_path = (
        ROOT / TASK41_P0_V11_METADATA_CONSUMER_CONTRACT_RELATIVE
    ).resolve(strict=True)
    if old_contract_path.resolve(strict=True) != expected_old_contract_path:
        raise ValueError("V11 metadata report names a different frozen attempt02 consumer contract")
    old_contract, old_contract_sha = require_task41_p0_contract(
        old_contract_path,
        expected_sha256=TASK41_P0_V11_METADATA_CONSUMER_CONTRACT_SHA256,
        current_root=ROOT,
        check_current_source=False,
        require_clean_source=False,
        case_id="B0",
    )
    old_window = load_task41_p0_fixed_window(
        old_contract, current_root=ROOT, require_current_boot=False
    )
    metadata_window_state = metadata_report.get("initial_fixed_window_state")
    metadata_window_accounting = (
        metadata_window_state.get("accounting_record")
        if isinstance(metadata_window_state, Mapping)
        else None
    )
    if (
        metadata_report.get("schema")
        != "task41.p0.v8.selected_trace_star_metadata_only_receipt.v1"
        or metadata_report.get("status") != "COMPLETED_METADATA_ONLY"
        or metadata_report.get("consumer_source_sha")
        != TASK41_P0_V11_METADATA_CONSUMER_SOURCE_SHA
        or metadata_report.get("consumer_contract_sha256")
        != old_contract_sha
        or old_contract.get("source", {}).get("sha")
        != TASK41_P0_V11_METADATA_CONSUMER_SOURCE_SHA
        or old_window.sha256 != TASK41_P0_V11_METADATA_WINDOW_SHA256
        or not isinstance(metadata_window_state, Mapping)
        or metadata_window_state.get("campaign_window_sha256") != old_window.sha256
        or not _task41_p0_v11_metadata_accounting_path_matches(metadata_window_state, old_window)
        or not isinstance(metadata_window_accounting, Mapping)
        or metadata_window_accounting.get("campaign_window_sha256") != old_window.sha256
        or metadata_report.get("donor_manifest_sha256")
        != donor.get("manifest_sha256")
        or not isinstance(metadata, Mapping)
        or metadata.get("schema") != "task41.p0.v8.selected_trace_star_metadata_only.v1"
        or metadata.get("status") != "COMPLETED_METADATA_ONLY"
        or metadata.get("selected_active_row") != TASK41_P0_V11_METADATA_ACTIVE_ROW
        or metadata.get("selected_original_row") != TASK41_P0_V11_METADATA_ORIGINAL_ROW
        or metadata.get("incident_cell_order") != list(TASK41_P0_V11_SELECTED_CELLS)
        or metadata.get("numerical_work_started") is not False
    ):
        raise ValueError("V11 metadata attempt02 report identity or selected incident cells differ")

    metadata_cells = metadata.get("selected_cells")
    if not isinstance(metadata_cells, list) or [
        item.get("cell_index") for item in metadata_cells if isinstance(item, Mapping)
    ] != list(TASK41_P0_V11_SELECTED_CELLS):
        raise ValueError("V11 attempt02 selected-cell inventory is incomplete or unordered")
    dimension = int(metadata.get("element_dimension", -1))
    if dimension < 1:
        raise ValueError("V11 saved row metadata has no valid element dimension")
    metadata_root = metadata_path.parent.resolve(strict=True)
    metadata_arrays: dict[int, dict[str, np.ndarray]] = {}
    metadata_rows: dict[int, dict[str, Any]] = {}
    metadata_array_fields = (
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
    expected_cell_identity = {360: (2, 4680, 375), 446: (1, 0, 75)}
    for cell_record in metadata_cells:
        cell_index = int(cell_record["cell_index"])
        expected_tag, expected_permutation, expected_local_trace = expected_cell_identity[cell_index]
        arrays = cell_record.get("arrays")
        if (
            cell_record.get("cell_tag") != expected_tag
            or cell_record.get("cell_permutation") != expected_permutation
            or cell_record.get("selected_local_trace_rows") != [expected_local_trace]
            or cell_record.get("selected_trace_coefficients") != [[1.0, 0.0]]
            or cell_record.get("selected_trace_contribution_kinds")
            != ["direct_original_row"]
            or not isinstance(arrays, Mapping)
            or set(arrays) != set(metadata_array_fields)
        ):
            raise ValueError(f"V11 attempt02 cell {cell_index} identity or array fields differ")
        loaded: dict[str, np.ndarray] = {}
        for field in metadata_array_fields:
            record = arrays[field]
            if not isinstance(record, Mapping) or record.get("name") != (
                f"task41_p0_v11_selected_cell{cell_index}_{field}"
            ):
                raise ValueError(f"V11 attempt02 cell {cell_index} {field} record is malformed")
            loaded[field] = _load_bound_report_array(
                metadata_root, {field: record}, field, sha256_file=sha256_file
            )
        coordinates = np.ascontiguousarray(
            loaded["actual_geometry_coordinates"], dtype=np.float64
        )
        coordinate_hash = hashlib.sha256(memoryview(coordinates).cast("B")).hexdigest()
        if coordinate_hash != cell_record.get("actual_coordinate_sha256"):
            raise ValueError(f"V11 attempt02 cell {cell_index} geometry hash differs")
        row = dict(loaded)
        row.update(
            {
                "cell_index": cell_index,
                "cell_tag": expected_tag,
                "cell_permutation": expected_permutation,
                "actual_coordinate_sha256": coordinate_hash,
                "element_dimension": dimension,
            }
        )
        metadata_arrays[cell_index] = loaded
        metadata_rows[cell_index] = row

    active_rows = np.asarray(donor["columns"][0]["active_original_rows"])
    second_active_rows = np.asarray(donor["columns"][1]["active_original_rows"])
    if (
        active_rows.ndim != 1
        or active_rows.dtype.kind not in "iu"
        or not np.array_equal(active_rows, second_active_rows)
        or int(active_rows[TASK41_P0_V11_METADATA_ACTIVE_ROW])
        != TASK41_P0_V11_METADATA_ORIGINAL_ROW
    ):
        raise ValueError("V11 metadata and donor active-to-original row maps differ")
    selected_original_row = int(active_rows[TASK41_P0_V11_METADATA_ACTIVE_ROW])

    v9_path = args.v9_compact_report.resolve(strict=True)
    if (
        v9_path.name != "task41_p0_b0_v9_compact_volume_audit.json"
        or not v9_path.is_relative_to(results_root)
        or args.v9_compact_report_sha256 != TASK41_P0_V11_V9_COMPACT_REPORT_SHA256
        or sha256_file(v9_path) != TASK41_P0_V11_V9_COMPACT_REPORT_SHA256
        or v9_path.stat().st_size > 8 * 1024**2
    ):
        raise ValueError("V11 V9 compact report path, size, or SHA-256 differs from the frozen source")
    v9_report = json.loads(v9_path.read_text(encoding="utf-8"))
    action_gate = v9_report.get("candidate_full_action_gate")
    if (
        v9_report.get("schema") != "task41.p0.b0.v9.compact_volume_identity.v1"
        or v9_report.get("status") != "GATE_FAILED"
        or v9_report.get("official_result") is not False
        or v9_report.get("internal_rhs_strategy") != "same_lu_rhs_solve"
        or v9_report.get("donor_manifest_sha256") != donor.get("manifest_sha256")
        or not isinstance(action_gate, Mapping)
        or action_gate.get("status") != "GATE_FAILED"
    ):
        raise ValueError("V11 V9 compact report is not the hash-bound failed same-LU action source")

    def load_v9_full_vector(field: str, expected_sha: str) -> np.ndarray:
        record = action_gate.get(field)
        if not isinstance(record, Mapping):
            raise ValueError(f"V11 V9 compact report omits {field}")
        raw_path = Path(str(record.get("path", "")))
        array_path = (
            raw_path if raw_path.is_absolute() else v9_path.parent / raw_path
        ).resolve(strict=True)
        if (
            not array_path.is_relative_to(v9_path.parent.resolve(strict=True))
            or array_path.stat().st_size != int(record.get("bytes", -1))
            or record.get("sha256") != expected_sha
            or sha256_file(array_path) != expected_sha
            or record.get("shape") != [TASK41_P0_V11_GLOBAL_ROW_COUNT, 2]
            or record.get("dtype") != "complex128"
        ):
            raise ValueError(f"V11 V9 compact {field} file identity is invalid")
        value = np.load(array_path, mmap_mode="r", allow_pickle=False)
        if value.shape != (TASK41_P0_V11_GLOBAL_ROW_COUNT, 2) or value.dtype != np.dtype(np.complex128):
            raise ValueError(f"V11 V9 compact {field} array shape or dtype differs")
        return value

    saved_y = load_v9_full_vector(
        "full_action_artifact", TASK41_P0_V11_V9_FULL_ACTION_ARRAY_SHA256
    )
    saved_g = load_v9_full_vector(
        "full_reduced_rhs_artifact", TASK41_P0_V11_V9_REDUCED_RHS_ARRAY_SHA256
    )
    y9_row = np.asarray(saved_y[TASK41_P0_V11_METADATA_ACTIVE_ROW, :]).copy()
    g9_row = np.asarray(saved_g[TASK41_P0_V11_METADATA_ACTIVE_ROW, :]).copy()

    interior_positions = np.asarray(metadata["interior_positions"], dtype=np.int64)
    trace_positions = np.asarray(metadata["trace_positions"], dtype=np.int64)
    if (
        interior_positions.ndim != 1
        or trace_positions.ndim != 1
        or not np.array_equal(
            np.sort(np.concatenate((interior_positions, trace_positions))),
            np.arange(dimension, dtype=np.int64),
        )
        or any(
            row["interior_positions"].tolist() != interior_positions.tolist()
            or row["trace_positions"].tolist() != trace_positions.tolist()
            for row in metadata_rows.values()
        )
    ):
        raise ValueError("V11 saved row metadata local interior/trace partition is invalid")

    estimated_evidence_bytes = 128 * 1024**2
    allocation_gate(
        "v11_selected_trace_star_candidate_replay_preflight",
        {
            "additional_payload_bytes": estimated_evidence_bytes,
            "evidence_reserve_bytes": estimated_evidence_bytes,
            "new_evidence_limit_bytes": 512 * 1024**2,
            "raw_artifact_limit_bytes": 16 * 1024**3,
            "workspace_bytes": 6 * 1024**3,
            "scratch_reserve_bytes": 512 * 1024**2,
            "estimated_remaining_seconds_upper": 900.0,
            "termination_reserve_seconds": 120.0,
            "candidate_only_replay": True,
            "selected_active_row": TASK41_P0_V11_METADATA_ACTIVE_ROW,
            "selected_original_row": selected_original_row,
            "incident_cells": list(TASK41_P0_V11_SELECTED_CELLS),
        },
    )
    if not output_directory.is_dir():
        raise FileNotFoundError("V11 selected candidate output directory was not prepared")
    free_before_compile = int(shutil.disk_usage(output_directory).free)
    if free_before_compile < 2 * 1024**3 + estimated_evidence_bytes:
        raise OSError("V11 selected candidate output violates its 2 GiB free-space floor")

    progress(
        {
            "phase": "v11_selected_candidate_mesh_space",
            "status": "STARTED",
            "degree": 6,
            "selected_active_row": TASK41_P0_V11_METADATA_ACTIVE_ROW,
        }
    )
    levels = _build_same_mesh_levels(
        cfg,
        MPI.COMM_SELF,
        (6,),
        include_positive_coefficients=False,
    )
    space = levels["spaces"][6]
    if int(space.element.space_dimension) != dimension:
        raise ValueError("V11 saved incident cells use a different p6 element dimension")
    progress(
        {
            "phase": "v11_selected_candidate_mesh_space",
            "status": "COMPLETED",
            "owned_cells": int(levels["mesh"].topology.index_map(levels["mesh"].topology.dim).size_local),
            "global_dofs": int(space.dofmap.index_map.size_global),
        }
    )
    trial, test = ufl.TrialFunction(space), ufl.TestFunction(space)
    dx = ufl.Measure("dx", domain=levels["mesh"], subdomain_data=levels["mesh_data"].cell_tags)
    curl_form, mass_form = _build_physical_volume_terms(cfg, trial, test, dx)
    combined_integrand = curl_form + mass_form
    combined_form = fem.form(
        combined_integrand,
        jit_options=dict(SAME_MESH_JIT_OPTIONS),
    )
    kernels = _cell_integral_kernels(combined_form, sum_duplicate_cell_integrals=True)
    evaluator = Task41ActualQMetricBlockedGramCandidate(
        space.element.basix_element,
        combined_integrand,
        combined_form,
        c_source_path=args.ffcx_c_source,
        scratch_directory=output_directory / "actual_qmetric_scratch",
    )
    if evaluator.identity != V6_CANDIDATE_IDENTITY:
        raise ValueError("V11 q-metric candidate identity differs from the frozen V9 evaluator")
    evaluator.validate_compiled_form(combined_form, kernels)
    evaluator.prepare()
    if (
        evaluator.identity != v9_report.get("candidate_evaluator_identity")
        or evaluator.cache_identity
        != v9_report.get("candidate_evaluator_cache_identity")
        or consumer_contract.get("numerical_strategy", {}).get(
            "internal_rhs_strategy"
        )
        != v9_report.get("internal_rhs_strategy")
        or v9_report.get("internal_rhs_strategy") != "same_lu_rhs_solve"
    ):
        raise ValueError(
            "prepared candidate evaluator/cache or RHS integration strategy differs from V9 compact"
        )
    (
        frozen_evaluator_profile_tags,
        cell_integral_ids,
        integral_kernel_counts,
    ) = _task41_v12_curl_mass_integral_profile(kernels)
    integration_identity = {
        "schema": "task41.p0.v12.same_mesh_p6_curl_plus_mass.v1",
        "degree": 6,
        "form_terms": ["curl", "mass"],
        "frozen_evaluator_profile_tags": frozen_evaluator_profile_tags,
        "cell_integral_ids": cell_integral_ids,
        "integral_kernel_counts": integral_kernel_counts,
        "sum_duplicate_cell_integrals": True,
        "internal_rhs_strategy": "same_lu_rhs_solve",
        "candidate_evaluator_identity": evaluator.identity,
        "candidate_cache_identity": evaluator.cache_identity,
    }
    progress(
        {
            "phase": "v11_selected_candidate_form_compile",
            "status": "COMPLETED",
            "candidate_identity": evaluator.identity,
            "candidate_cache_identity": evaluator.cache_identity,
            "candidate_prepare_seconds": float(evaluator.preparation_seconds),
            "ffcx_c_source_sha256": TASK41_P0_V11_FFCX_C_SOURCE_SHA256,
        }
    )

    from src.runners.task41_p0_v4_volume_only_audit import (
        _v8_rebuild_selected_cell_role_artifacts,
    )

    cell_numeric: dict[int, dict[str, Any]] = {}
    cell_progress_records: dict[str, dict[str, Any]] = {}
    candidate_build_seconds = 0.0
    candidate_cells_built: list[int] = []
    candidate_cells_reused: list[int] = []
    previous_attempt_root = output_directory.parent.parent
    prior_reports = sorted(
        previous_attempt_root.glob("attempt[0-9][0-9]*/task41_p0_v11_selected_trace_candidate_replay.json"),
        reverse=True,
    )
    for prior_report_path in prior_reports:
        if prior_report_path.resolve() == (output_directory.parent / "task41_p0_v11_selected_trace_candidate_replay.json").resolve():
            continue
        if prior_report_path.stat().st_size > 8 * 1024**2:
            continue
        try:
            prior_report = json.loads(prior_report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(prior_report, Mapping):
            continue
        prior_progress = _v11_prior_candidate_cell_progress(
            prior_report,
            prior_report_path=prior_report_path,
            fixed_window=fixed_window,
            consumer_contract=consumer_contract,
            donor_manifest_sha256=str(donor.get("manifest_sha256")),
            metadata_report_path=metadata_path,
            metadata_report_sha256=TASK41_P0_V11_METADATA_REPORT_SHA256,
            v9_compact_report_path=v9_path,
            v9_compact_report_sha256=TASK41_P0_V11_V9_COMPACT_REPORT_SHA256,
            current_root=ROOT,
            require_contract=require_task41_p0_contract,
        )
        if prior_progress is None:
            continue
        prior_cells = prior_progress.get("cells")
        completed_cells = set(prior_progress["completed_cells"])
        for cell_index in TASK41_P0_V11_SELECTED_CELLS:
            cell_key = str(cell_index)
            if cell_index in cell_numeric or cell_index not in completed_cells:
                continue
            if cell_key not in prior_cells:
                raise ValueError(
                    f"prior candidate progress declares cell {cell_index} complete without its record"
                )
            saved_cell = prior_cells[cell_key]
            if not isinstance(saved_cell, Mapping):
                raise ValueError(f"prior candidate cell {cell_index} record is malformed")
            row = metadata_rows[cell_index]
            reuse_identity = _v11_candidate_cell_reuse_identity(
                consumer_contract=consumer_contract,
                fixed_window=fixed_window,
                donor_manifest_sha256=str(donor["manifest_sha256"]),
                metadata_report_sha256=TASK41_P0_V11_METADATA_REPORT_SHA256,
                v9_compact_report_sha256=TASK41_P0_V11_V9_COMPACT_REPORT_SHA256,
                evaluator_identity=evaluator.identity,
                cache_identity=evaluator.cache_identity,
                ffcx_c_source_sha256=TASK41_P0_V11_FFCX_C_SOURCE_SHA256,
                row=row,
            )
            candidate = _v11_load_completed_candidate_cell(
                saved_cell,
                expected_reuse_identity=reuse_identity,
                results_root=results_root,
                dimension=dimension,
                interior_count=len(row["interior_positions"]),
                trace_count=len(row["trace_positions"]),
                sha256_file=sha256_file,
            )
            if candidate is None:
                progress(
                    {
                        "phase": "v11_selected_candidate_cell",
                        "status": "NOT_REUSED_NUMERICAL_IDENTITY_CHANGED",
                        "cell_index": cell_index,
                        "prior_report_path": str(prior_report_path),
                    }
                )
                continue
            cell_numeric[cell_index] = {"candidate": candidate}
            cell_progress_records[cell_key] = dict(saved_cell)
            candidate_cells_reused.append(cell_index)
            progress(
                {
                    "phase": "v11_selected_candidate_cell",
                    "status": "READ_FROM_COMPLETED_CELL",
                    "cell_index": cell_index,
                    "source": "HASH_BOUND_PRIOR_ATTEMPT",
                    "prior_report_path": str(prior_report_path),
                }
            )

    for cell_index in TASK41_P0_V11_SELECTED_CELLS:
        if cell_index in cell_numeric:
            continue
        progress(
            {
                "phase": "v11_selected_candidate_cell",
                "status": "STARTED",
                "cell_index": cell_index,
                "source": "RECONSTRUCTED_SELECTED_CELL",
            }
        )
        cell_build_started = perf_counter()
        role_sets = _v8_rebuild_selected_cell_role_artifacts(
            cell_index=cell_index,
            row=metadata_rows[cell_index],
            combined_form=combined_form,
            kernels=kernels,
            element=space.element,
            dimension=dimension,
            interior_positions=interior_positions,
            trace_positions=trace_positions,
            candidate_evaluator=evaluator,
            persist_array=persist_array,
            progress=progress,
            candidate_only=True,
            artifact_prefix_template="task41_p0_v11_selected_cell{cell_index}_{role}",
        )
        if set(role_sets) != {"candidate"}:
            raise ValueError(f"V11 selected cell {cell_index} did not save candidate only")
        candidate_build_seconds += perf_counter() - cell_build_started
        candidate_cells_built.append(cell_index)
        cell_numeric[cell_index] = role_sets
        candidate = role_sets["candidate"]
        reuse_identity = _v11_candidate_cell_reuse_identity(
            consumer_contract=consumer_contract,
            fixed_window=fixed_window,
            donor_manifest_sha256=str(donor["manifest_sha256"]),
            metadata_report_sha256=TASK41_P0_V11_METADATA_REPORT_SHA256,
            v9_compact_report_sha256=TASK41_P0_V11_V9_COMPACT_REPORT_SHA256,
            evaluator_identity=evaluator.identity,
            cache_identity=evaluator.cache_identity,
            ffcx_c_source_sha256=TASK41_P0_V11_FFCX_C_SOURCE_SHA256,
            row=metadata_rows[cell_index],
        )
        reuse_identity_sha256 = hashlib.sha256(
            json.dumps(
                reuse_identity,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        cell_progress_records[str(cell_index)] = {
            "completion_status": "CELL_COMPLETE",
            "cell_index": cell_index,
            "source": "RECONSTRUCTED_SELECTED_CELL",
            "strict_lu_residual": candidate["strict_lu_residual"],
            "reuse_identity": reuse_identity,
            "reuse_identity_sha256": reuse_identity_sha256,
            "candidate_artifacts": {
                name: dict(value)
                for name, value in candidate["artifacts"].items()
            },
        }
        checkpoint(
            "v11_selected_candidate_cell_progress",
            {
                "schema": "task41.p0.v11.selected_candidate_cell_progress.v1",
                "completed_cells": sorted(cell_numeric),
                "required_cells": list(TASK41_P0_V11_SELECTED_CELLS),
                "cells": dict(cell_progress_records),
            },
        )

    if not set(cell_numeric) == set(TASK41_P0_V11_SELECTED_CELLS):
        raise ValueError("V11 candidate replay did not reconstruct both complete incident cells")

    epsilon = np.finfo(np.float64).eps

    def gamma(operations: int) -> float:
        x = float(operations) * epsilon
        return x / (1.0 - x) if x < 1.0 else float("inf")

    def complex_pair(value: complex) -> list[float]:
        value = complex(value)
        return [float(value.real), float(value.imag)]

    def persist_named(name: str, values: np.ndarray) -> dict[str, Any]:
        array = np.asarray(values)
        return {"name": name, **persist_array(name, array)}

    def selected_value(expansion: Any, local_trace: np.ndarray) -> tuple[complex, np.ndarray, np.ndarray]:
        projected = np.asarray(expansion.conjugate().transpose() @ local_trace).reshape(-1)
        selected_local = np.flatnonzero(active_ids == TASK41_P0_V11_METADATA_ACTIVE_ROW)
        if selected_local.size != 1:
            raise ValueError("V11 selected active row is absent or duplicated in a saved cell map")
        return complex(projected[int(selected_local[0])]), projected, np.abs(projected)

    column_results = []
    review_identity_results = []
    diagnostic_solve_calls = {"bi": 0, "ri": 0, "getrs": 0}
    diagnostic_getrs_seconds = 0.0
    for column_index, column in enumerate(donor["columns"]):
        if int(column.get("column", column_index)) != column_index:
            raise ValueError("V12 donor columns are not in frozen [0, 1] order")
        states = column.get("states")
        if not isinstance(states, list):
            raise ValueError(f"V12 donor column {column_index} omits its paired states")
        labels = [state.get("label") for state in states if isinstance(state, Mapping)]
        if len(states) != 2 or len(labels) != 2 or sorted(labels) != ["j0", "j3"]:
            raise ValueError(
                f"V12 donor column {column_index} must bind exactly one j0 and one j3 state"
            )
        states_by_label = {str(state["label"]): state for state in states}
        saved_y_value = complex(y9_row[column_index])
        saved_g_value = complex(g9_row[column_index])
        native_rhs = np.asarray(column["native_rhs"])
        native_volume_rhs = np.asarray(column["native_volume_rhs"])
        known = np.asarray(column["known_field"])
        native_rhs_row = complex(native_rhs[selected_original_row])
        native_rhs_t_for_state: dict[str, complex] = {}
        native_action_t_for_state: dict[str, complex] = {}
        s_cell_terms: list[complex] = []
        same_lu_cell_terms: list[complex] = []
        stored_t_cell_terms: list[complex] = []
        review_cell_terms: dict[str, dict[str, list[complex]]] = {
            label: {name: [] for name in ("delta_t", "cs_t", "j_middle", "minus_j_z_r")}
            for label in ("j0", "j3")
        }
        beta_rows = np.asarray(column["b_alpha_rows"], dtype=np.int64)
        beta_values = np.asarray(column["b_alpha_values"], dtype=np.complex128)
        beta_match = beta_values[beta_rows == selected_original_row]
        if beta_match.size > 1:
            raise ValueError("V11 selected row has duplicate B-alpha entries")
        beta_t = complex(beta_match[0]) if beta_match.size else 0.0 + 0.0j
        y_abs_work = abs(saved_y_value)
        g_abs_work = abs(saved_g_value) + abs(native_rhs_row)
        per_cell_column = []
        for cell_index in TASK41_P0_V11_SELECTED_CELLS:
            row = metadata_rows[cell_index]
            arrays = metadata_arrays[cell_index]
            active_ids = np.asarray(row["active_ids"], dtype=np.int64)
            original_rows = np.asarray(row["original_rows"], dtype=np.int64)
            interior_rows = np.asarray(row["interior_original_rows"], dtype=np.int64)
            trace_rows = np.asarray(row["trace_original_rows"], dtype=np.int64)
            local_interior = np.asarray(row["interior_positions"], dtype=np.int64)
            local_trace = np.asarray(row["trace_positions"], dtype=np.int64)
            if (
                not np.array_equal(original_rows[local_interior], interior_rows)
                or not np.array_equal(original_rows[local_trace], trace_rows)
                or np.any(active_ids < 0)
                or np.any(active_ids >= active_rows.size)
            ):
                raise ValueError(f"V11 selected cell {cell_index} saved row-to-dof maps are inconsistent")
            expansion = sparse.csr_matrix(
                (
                    np.asarray(row["trace_expansion_data"], dtype=np.complex128),
                    np.asarray(row["trace_expansion_indices"], dtype=np.int32),
                    np.asarray(row["trace_expansion_indptr"], dtype=np.int32),
                ),
                shape=(len(local_trace), len(active_ids)),
            )
            selected_local_rows = np.asarray(row["selected_local_trace_rows"], dtype=np.int64)
            selected_coefficients = np.asarray(
                row["selected_trace_coefficients"], dtype=np.complex128
            )
            weights = np.zeros(len(local_trace), dtype=np.complex128)
            if (
                selected_local_rows.size != selected_coefficients.size
                or selected_local_rows.size == 0
                or np.any(selected_local_rows < 0)
                or np.any(selected_local_rows >= len(local_trace))
            ):
                raise ValueError(f"V11 selected cell {cell_index} row weights are malformed")
            weights[selected_local_rows] = selected_coefficients
            if not np.any(weights != 0.0):
                raise ValueError(f"V11 selected cell {cell_index} target E column is zero")

            known_active = np.asarray(
                known[active_rows[active_ids]], dtype=np.complex128
            )
            t_c = np.asarray(expansion @ known_active, dtype=np.complex128).reshape(-1)
            selected_local_rows = np.asarray(
                row["selected_local_trace_rows"], dtype=np.int64
            )
            selected_coefficients = np.asarray(
                row["selected_trace_coefficients"], dtype=np.complex128
            )
            selected_active_local = np.flatnonzero(
                active_ids == TASK41_P0_V11_METADATA_ACTIVE_ROW
            )
            if (
                selected_local_rows.shape != (1,)
                or selected_coefficients.shape != (1,)
                or selected_coefficients[0] != 1.0 + 0.0j
                or selected_active_local.shape != (1,)
                or int(trace_rows[selected_local_rows[0]]) != selected_original_row
            ):
                raise ValueError(
                    f"V12 selected trace/state binding is not the frozen one-entry coefficient at cell {cell_index}"
                )
            selected_expansion_row = expansion.getrow(int(selected_local_rows[0]))
            if (
                selected_expansion_row.nnz != 1
                or int(selected_expansion_row.indices[0]) != int(selected_active_local[0])
                or selected_expansion_row.data[0] != 1.0 + 0.0j
                or t_c[int(selected_local_rows[0])]
                != known[selected_original_row]
            ):
                raise ValueError(
                    f"V12 selected known trace does not match its saved j0/j3 active-row mapping at cell {cell_index}"
                )
            b_i = np.asarray(native_rhs[interior_rows], dtype=np.complex128)
            volume_b_i = np.asarray(native_volume_rhs[interior_rows], dtype=np.complex128)
            if not np.array_equal(b_i, volume_b_i):
                raise ValueError(f"V11 full and volume native RHS differ on cell {cell_index} interior")
            state_details = []
            candidate = cell_numeric[cell_index]["candidate"]
            tensor = np.asarray(candidate["oriented_tensor"], dtype=np.complex128)
            K = tensor[np.ix_(local_interior, local_interior)]
            G = tensor[np.ix_(local_interior, local_trace)]
            J = tensor[np.ix_(local_trace, local_interior)]
            L = tensor[np.ix_(local_trace, local_trace)]
            R = np.asarray(candidate["rts"]["R"], dtype=np.complex128)
            T = np.asarray(candidate["rts"]["T"], dtype=np.complex128)
            S = np.asarray(candidate["rts"]["S"], dtype=np.complex128)
            lu = np.asarray(candidate["lu"], dtype=np.complex128)
            pivots = np.array(candidate["pivots"], dtype=np.int32, copy=True)
            S_t = S @ t_c
            T_b_i = T @ b_i
            z_b, minus_J_z_b, z_b_timing = project_internal_rhs_same_lu(
                (lu, pivots), J, b_i
            )
            diagnostic_solve_calls["bi"] += 1
            diagnostic_solve_calls["getrs"] += int(z_b_timing["nonzero_rhs"] is True)
            diagnostic_getrs_seconds += float(z_b_timing["getrs_seconds"])
            independently_projected_z_b = -(J @ z_b)
            same_lu_correction_difference = minus_J_z_b - independently_projected_z_b
            if not np.array_equal(minus_J_z_b, independently_projected_z_b):
                raise ValueError("V11 same-LU correction differs from an independent -Jz_b matvec")
            projected_s, projected_S_t, _ = selected_value(expansion, S_t)
            projected_T_b = np.asarray(
                expansion.conjugate().transpose() @ T_b_i
            ).reshape(-1)
            projected_same_lu = np.asarray(
                expansion.conjugate().transpose() @ minus_J_z_b
            ).reshape(-1)
            selected_map = np.flatnonzero(active_ids == TASK41_P0_V11_METADATA_ACTIVE_ROW)
            if selected_map.size != 1:
                raise ValueError(f"V11 selected row map is absent in cell {cell_index}")
            selected_position = int(selected_map[0])
            s_term = complex(projected_s)
            tb_term = complex(projected_T_b[selected_position])
            lu_term = complex(projected_same_lu[selected_position])
            s_cell_terms.append(s_term)
            same_lu_cell_terms.append(lu_term)
            stored_t_cell_terms.append(tb_term)
            y_abs_work += float(
                np.sum(np.abs(weights) * (np.abs(S) @ np.abs(t_c)), dtype=np.float64)
            )
            g_abs_work += float(
                np.sum(np.abs(weights) * (np.abs(T) @ np.abs(b_i)), dtype=np.float64)
                + np.sum(np.abs(weights) * (np.abs(J) @ np.abs(z_b)), dtype=np.float64)
            )

            cell_base = f"task41_p0_v11_cell{cell_index}_col{column_index}"
            per_cell_artifacts = {
                "known_trace_local": persist_named(cell_base + "_known_trace_local", t_c),
                "native_rhs_interior": persist_named(cell_base + "_native_rhs_interior", b_i),
                "S_action": persist_named(cell_base + "_S_action", S_t),
                "S_projected_active": persist_named(cell_base + "_S_projected_active", projected_S_t),
                "T_native_rhs": persist_named(cell_base + "_T_native_rhs", T_b_i),
                "T_projected_active": persist_named(cell_base + "_T_projected_active", projected_T_b),
                "same_lu_z_b": persist_named(cell_base + "_same_lu_z_b", z_b),
                "same_lu_minus_Jz_b": persist_named(cell_base + "_same_lu_minus_Jz_b", minus_J_z_b),
                "same_lu_minus_Jz_b_independent_difference": persist_named(cell_base + "_same_lu_minus_Jz_b_independent_difference", same_lu_correction_difference),
                "same_lu_z_b_timing": z_b_timing,
                "same_lu_projected_active": persist_named(cell_base + "_same_lu_projected_active", projected_same_lu),
            }

            for state_label in ("j0", "j3"):
                state = states_by_label[state_label]
                storage = np.asarray(state["storage"])
                native_action = np.asarray(state["native_volume_action"])
                u_i = np.asarray(storage[interior_rows], dtype=np.complex128)
                n_i = np.asarray(native_action[interior_rows], dtype=np.complex128)
                n_t = np.asarray(native_action[trace_rows], dtype=np.complex128)
                r_i = b_i - n_i
                z_r, minus_J_z_r, z_r_timing = project_internal_rhs_same_lu(
                    (lu, pivots), J, r_i
                )
                diagnostic_solve_calls["ri"] += 1
                diagnostic_solve_calls["getrs"] += int(z_r_timing["nonzero_rhs"] is True)
                diagnostic_getrs_seconds += float(z_r_timing["getrs_seconds"])
                independently_projected_z_r = -(J @ z_r)
                if not np.array_equal(minus_J_z_r, independently_projected_z_r):
                    raise ValueError("V11 same-LU residual correction differs from independent -Jz_r")
                r_b = b_i - K @ z_b
                r_r = r_i - K @ z_r
                delta_i = K @ u_i + G @ t_c - n_i
                delta_t = J @ u_i + L @ t_c
                E_R = K @ R + G
                C_S = S - L - J @ R
                E_R_t = E_R @ t_c
                C_S_t = C_S @ t_c
                review_middle = R @ t_c + z_b - z_r - u_i
                review_eq2_left = K @ review_middle
                review_eq2_right = E_R_t - delta_i - r_b + r_r
                review_eq2_delta = review_eq2_left - review_eq2_right
                native_rhs_t = native_rhs_row
                native_action_t = complex(native_action[selected_original_row])
                residual_t = native_rhs_t - native_action_t - beta_t
                projected_delta_t = np.asarray(
                    expansion.conjugate().transpose() @ delta_t
                ).reshape(-1)
                projected_CS_t = np.asarray(
                    expansion.conjugate().transpose() @ C_S_t
                ).reshape(-1)
                projected_J_middle = np.asarray(
                    expansion.conjugate().transpose() @ (J @ review_middle)
                ).reshape(-1)
                projected_J_z_r = np.asarray(
                    expansion.conjugate().transpose() @ minus_J_z_r
                ).reshape(-1)
                projected_delta_t_term = complex(projected_delta_t[selected_position])
                projected_cs_t_term = complex(projected_CS_t[selected_position])
                projected_j_middle_term = complex(projected_J_middle[selected_position])
                local_identity_rhs_contribution = (
                    projected_delta_t_term + projected_cs_t_term + projected_j_middle_term
                )
                projected_minus_J_z_r = complex(projected_J_z_r[selected_position])
                review_cell_terms[state_label]["delta_t"].append(projected_delta_t_term)
                review_cell_terms[state_label]["cs_t"].append(projected_cs_t_term)
                review_cell_terms[state_label]["j_middle"].append(projected_j_middle_term)
                review_cell_terms[state_label]["minus_j_z_r"].append(projected_minus_J_z_r)
                previous_rhs_t = native_rhs_t_for_state.setdefault(state_label, native_rhs_t)
                previous_action_t = native_action_t_for_state.setdefault(
                    state_label, native_action_t
                )
                if previous_rhs_t != native_rhs_t or previous_action_t != native_action_t:
                    raise ValueError("V11 global native trace rows changed across incident cells")
                equation2_bound = gamma(16 * max(1, dimension)) * max(
                    1.0,
                    float(np.max(np.abs(review_eq2_left), initial=0.0)),
                    float(np.max(np.abs(review_eq2_right), initial=0.0)),
                )
                equation2_max = float(
                    np.max(np.abs(review_eq2_delta), initial=0.0)
                )
                cell_base_state = cell_base + f"_{state_label}"
                state_artifacts = {
                    "u_i": persist_named(cell_base_state + "_u_i", u_i),
                    "native_action_i": persist_named(cell_base_state + "_native_action_i", n_i),
                    "native_action_global_trace_slice": persist_named(cell_base_state + "_native_action_global_trace_slice", n_t),
                    "r_i": persist_named(cell_base_state + "_r_i", r_i),
                    "same_lu_z_r": persist_named(cell_base_state + "_same_lu_z_r", z_r),
                    "same_lu_minus_Jz_r": persist_named(cell_base_state + "_same_lu_minus_Jz_r", minus_J_z_r),
                    "same_lu_z_r_timing": z_r_timing,
                    "delta_i": persist_named(cell_base_state + "_delta_i", delta_i),
                    "delta_t": persist_named(cell_base_state + "_delta_t", delta_t),
                    "r_b": persist_named(cell_base_state + "_r_b", r_b),
                    "r_r": persist_named(cell_base_state + "_r_r", r_r),
                    "E_R_t": persist_named(cell_base_state + "_E_R_t", E_R_t),
                    "C_S_t": persist_named(cell_base_state + "_C_S_t", C_S_t),
                    "review_eq2_left": persist_named(cell_base_state + "_review_eq2_left", review_eq2_left),
                    "review_eq2_right": persist_named(cell_base_state + "_review_eq2_right", review_eq2_right),
                    "review_eq2_difference": persist_named(cell_base_state + "_review_eq2_difference", review_eq2_delta),
                    "old_Tb_plus_Jzb": persist_named(
                        cell_base_state + "_old_Tb_plus_Jzb", T_b_i + J @ z_b
                    ),
                    "old_identity_rhs": persist_named(
                        cell_base_state + "_old_identity_rhs",
                        (J + T @ K) @ z_b + T @ r_b,
                    ),
                    "old_identity_difference": persist_named(
                        cell_base_state + "_old_identity_difference",
                        (T @ b_i + J @ z_b) - ((J + T @ K) @ z_b + T @ r_b),
                    ),
                }
                state_details.append(
                    {
                        "state": state_label,
                        "inputs": {
                            "u_i": state_artifacts["u_i"],
                            "n_i": state_artifacts["native_action_i"],
                            "n_t_global_trace_slice": state_artifacts["native_action_global_trace_slice"],
                            "b_i": per_cell_artifacts["native_rhs_interior"],
                            "t_c": per_cell_artifacts["known_trace_local"],
                        },
                        "review_identity": {
                            "equation_1_rhs_cell_contribution": complex_pair(
                                local_identity_rhs_contribution
                            ),
                            "equation_1_projected_minus_Jz_r_cell_contribution": complex_pair(
                                projected_minus_J_z_r
                            ),
                            "equation_1_native_residual_row": complex_pair(residual_t),
                            "equation_2_max_abs_difference": equation2_max,
                            "equation_2_roundoff_bound": equation2_bound,
                            "equation_2_status": "DIAGNOSTIC_ONLY",
                            "old_Tb_Jzb_identity_max_abs_difference": float(
                                np.max(
                                    np.abs(
                                        (T @ b_i + J @ z_b)
                                        - ((J + T @ K) @ z_b + T @ r_b)
                                    ),
                                    initial=0.0,
                                )
                            ),
                            "artifacts": state_artifacts,
                        }
                    }
                )
            per_cell_artifacts["states"] = state_details
            per_cell_column.append(
                {
                    "cell_index": cell_index,
                    "cell_tag": int(row["cell_tag"]),
                    "cell_permutation": int(row["cell_permutation"]),
                    "source": "RECONSTRUCTED_SELECTED_CELL",
                    "candidate_identity": candidate["raw_tensor_evaluator_identity"],
                    "strict_lu_residual": float(candidate["strict_lu_residual"]),
                    "selected_row_terms": {
                        "S_t": complex_pair(s_term),
                        "T_b_i": complex_pair(tb_term),
                        "same_lu_minus_Jz_b": complex_pair(lu_term),
                        "same_lu_minus_stored_T": complex_pair(lu_term - tb_term),
                    },
                    "artifacts": per_cell_artifacts,
                }
            )
        beta_rows = np.asarray(column["b_alpha_rows"], dtype=np.int64)
        beta_values = np.asarray(column["b_alpha_values"], dtype=np.complex128)
        beta_match = beta_values[beta_rows == selected_original_row]
        if beta_match.size > 1:
            raise ValueError("V11 selected row has duplicate B-alpha entries")
        beta_t = complex(beta_match[0]) if beta_match.size else 0.0 + 0.0j
        bound_y = gamma(32 * dimension * max(1, len(TASK41_P0_V11_SELECTED_CELLS))) * max(
            1.0, y_abs_work + abs(beta_t)
        )
        bound_g = gamma(48 * dimension * max(1, len(TASK41_P0_V11_SELECTED_CELLS))) * max(
            1.0, g_abs_work
        )
        row_replays = {}
        column_review_identities = []
        for state_label in ("j0", "j3"):
            terms = review_cell_terms[state_label]
            native_action_t = native_action_t_for_state[state_label]
            row_replay = _v11_accumulate_saved_candidate_row_terms(
                native_rhs_row=native_rhs_row,
                native_action_row=native_action_t,
                b_alpha_row=beta_t,
                s_cell_terms=s_cell_terms,
                same_lu_cell_terms=same_lu_cell_terms,
                stored_t_cell_terms=stored_t_cell_terms,
                delta_t_cell_terms=terms["delta_t"],
                cs_t_cell_terms=terms["cs_t"],
                j_middle_cell_terms=terms["j_middle"],
                minus_j_z_r_cell_terms=terms["minus_j_z_r"],
            )
            row_replays[state_label] = row_replay
            residual_t = row_replay["native_residual_row"]
            lhs_identity = row_replay["review_eq1_lhs"]
            rhs_identity = row_replay["review_eq1_rhs"]
            lu_residual = sum(terms["minus_j_z_r"], 0.0 + 0.0j)
            identity_delta = lhs_identity - rhs_identity
            identity_scale = max(
                1.0,
                abs(lhs_identity),
                abs(rhs_identity),
                y_abs_work + g_abs_work + abs(native_action_t) + abs(lu_residual),
            )
            identity_bound = gamma(64 * dimension * len(TASK41_P0_V11_SELECTED_CELLS)) * identity_scale
            identity_item = {
                "column": column_index,
                "state": state_label,
                "d_lu_replayed_y_minus_g": complex_pair(row_replay["d_lu"]),
                "native_residual_row": complex_pair(residual_t),
                "global_native_action_row_subtracted_once": complex_pair(native_action_t),
                "sum_projected_minus_Jz_r": complex_pair(lu_residual),
                "equation_1_lhs": complex_pair(lhs_identity),
                "equation_1_rhs": complex_pair(rhs_identity),
                "equation_1_difference": complex_pair(identity_delta),
                "equation_1_roundoff_estimate": identity_bound,
                "equation_1_roundoff_estimate_contains_difference": bool(
                    abs(identity_delta) <= identity_bound
                ),
                "equation_1_status": "DIAGNOSTIC_ONLY",
                "cell_count": len(terms["delta_t"]),
            }
            column_review_identities.append(identity_item)
            review_identity_results.append(identity_item)
        replay_y = row_replays["j0"]["y9"]
        replay_g_same_lu = row_replays["j0"]["g9_same_lu"]
        replay_g_stored_t = row_replays["j0"]["g9_stored_t"]
        if any(
            row_replays[label][key] != row_replays["j0"][key]
            for label in ("j3",)
            for key in ("y9", "g9_same_lu", "g9_stored_t", "d_lu")
        ):
            raise ValueError("V11 paired Review states changed the saved target-row y/g replay")
        original_d_row = saved_y_value - saved_g_value
        y_diagnostic = _v11_local_replay_delta_diagnostic(
            saved_value=saved_y_value,
            replayed_value=replay_y,
            original_d=original_d_row,
            roundoff_estimate=bound_y,
        )
        g_diagnostic = _v11_local_replay_delta_diagnostic(
            saved_value=saved_g_value,
            replayed_value=replay_g_same_lu,
            original_d=original_d_row,
            roundoff_estimate=bound_g,
        )
        delta_y = y_diagnostic["delta_replay_minus_saved"]
        delta_g = g_diagnostic["delta_replay_minus_saved"]
        column_results.append(
            {
                "original_d_saved_y9_minus_saved_g9": complex_pair(original_d_row),
                "original_d_absolute": float(abs(original_d_row)),
                "column": column_index,
                "saved_y9": complex_pair(y_diagnostic["saved_value"]),
                "replayed_y9": complex_pair(y_diagnostic["replayed_value"]),
                "saved_g9": complex_pair(g_diagnostic["saved_value"]),
                "replayed_g9_same_lu": complex_pair(g_diagnostic["replayed_value"]),
                "replayed_g9_stored_T": complex_pair(replay_g_stored_t),
                "same_lu_minus_stored_T_g": complex_pair(
                    replay_g_same_lu - replay_g_stored_t
                ),
                "delta_y_replay_minus_saved": complex_pair(delta_y),
                "delta_y_absolute": y_diagnostic["delta_absolute"],
                "delta_y_relative_to_original_d": y_diagnostic[
                    "delta_relative_to_original_d"
                ],
                "delta_g_replay_minus_saved": complex_pair(delta_g),
                "delta_g_absolute": g_diagnostic["delta_absolute"],
                "delta_g_relative_to_original_d": g_diagnostic[
                    "delta_relative_to_original_d"
                ],
                "y_roundoff_estimate": bound_y,
                "y_roundoff_estimate_contains_difference": y_diagnostic[
                    "roundoff_estimate_contains_difference"
                ],
                "g_roundoff_estimate": bound_g,
                "g_roundoff_estimate_contains_difference": g_diagnostic[
                    "roundoff_estimate_contains_difference"
                ],
                "roundoff_interpretation": (
                    "conservative diagnostic bound only; overlap does not establish exact "
                    "reproduction or causal attribution"
                ),
                "y_replay_status": y_diagnostic["status"],
                "g_replay_status": g_diagnostic["status"],
                "B_alpha_selected_original_row_applied_once": complex_pair(beta_t),
                "incident_cell_terms": per_cell_column,
                "review_v11_row_identities": column_review_identities,
                "formal_action_gate_changed": False,
            }
        )

    if diagnostic_solve_calls != {"bi": 4, "ri": 8, "getrs": 12}:
        raise ValueError(
            f"V12 selected replay expected 4 bi and 8 ri GETRS calls, got {diagnostic_solve_calls}"
        )
    result = {
        "schema": "task41.p0.v11.selected_trace_star_candidate_replay.v1",
        "status": "COMPLETED_LOCAL_CANDIDATE_REPLAY",
        "replay_completed": True,
        "data_integrity": True,
        "y_replay_bound": all(
            item["y_replay_status"] == "EXACT_SAVED_VALUE_REPRODUCED"
            for item in column_results
        ),
        "g_replay_bound": all(
            item["g_replay_status"] == "EXACT_SAVED_VALUE_REPRODUCED"
            for item in column_results
        ),
        "identity_remainder_status": "DIAGNOSTIC_ONLY",
        "scientific_qualified": False,
        "integration_identity": integration_identity,
        "v9_compact_evaluator_identity": v9_report["candidate_evaluator_identity"],
        "v9_compact_cache_identity": v9_report["candidate_evaluator_cache_identity"],
        "stage_accounting": {
            "form_evaluator_prepare_seconds": float(evaluator.preparation_seconds),
            "candidate_cells_built": candidate_cells_built,
            "candidate_cells_reused": candidate_cells_reused,
            "candidate_cell_build_seconds": float(candidate_build_seconds),
            "diagnostic_same_lu_getrs": {
                "bi_calls": diagnostic_solve_calls["bi"],
                "ri_calls": diagnostic_solve_calls["ri"],
                "getrs_calls": diagnostic_solve_calls["getrs"],
                "expected_getrs_calls": 12,
                "getrs_seconds": diagnostic_getrs_seconds,
                "build_and_audit_accounted_separately": True,
            },
        },
        "selected_active_row": TASK41_P0_V11_METADATA_ACTIVE_ROW,
        "selected_original_row": selected_original_row,
        "incident_cell_order": list(TASK41_P0_V11_SELECTED_CELLS),
        "metadata_report_path": str(metadata_path),
        "metadata_report_sha256": TASK41_P0_V11_METADATA_REPORT_SHA256,
        "metadata_consumer_contract_path": str(old_contract_path),
        "metadata_consumer_contract_sha256": old_contract_sha,
        "consumer_contract_sha256": consumer_contract_sha256,
        "donor_manifest_sha256": donor["manifest_sha256"],
        "metadata_window_path": str(old_window.path),
        "metadata_window_sha256": old_window.sha256,
        "consumer_window_path": str(fixed_window.path),
        "consumer_window_sha256": fixed_window.sha256,
        "consumer_source_sha": str(consumer_source["sha"]),
        "metadata_service_receipt_path": str(metadata_receipt_path),
        "metadata_service_receipt_sha256": TASK41_P0_V11_METADATA_SERVICE_RECEIPT_SHA256,
        "v9_compact_report_path": str(v9_path),
        "v9_compact_report_sha256": TASK41_P0_V11_V9_COMPACT_REPORT_SHA256,
        "source_semantics": {
            "y9": "candidate action applied to known_field[active_original_rows], then saved B_alpha at this row exactly once",
            "g9": "saved native_rhs at the original row once plus cellwise same-LU -J solve(K,b_i), projected through the saved E map",
            "j0_j3": "paired saved native action/residual inputs for Review V11 identities only; never substitute for known_field",
            "formal_action_gate_changed": False,
            "official_result": False,
        },
        "candidate_evaluator_identity": evaluator.identity,
        "candidate_cache_identity": evaluator.cache_identity,
        "ffcx_c_source_sha256": TASK41_P0_V11_FFCX_C_SOURCE_SHA256,
        "cells": [
            {
                "cell_index": cell_index,
                "cell_tag": int(metadata_rows[cell_index]["cell_tag"]),
                "cell_permutation": int(metadata_rows[cell_index]["cell_permutation"]),
                "actual_coordinate_sha256": metadata_rows[cell_index][
                    "actual_coordinate_sha256"
                ],
                "candidate_source": "RECONSTRUCTED_SELECTED_CELL",
                "candidate_artifacts": cell_numeric[cell_index]["candidate"]["artifacts"],
                "strict_lu_residual": float(
                    cell_numeric[cell_index]["candidate"]["strict_lu_residual"]
                ),
            }
            for cell_index in TASK41_P0_V11_SELECTED_CELLS
        ],
        "columns": column_results,
        "review_v11_local_identities": review_identity_results,
        "classification": (
            "LOCAL_REPLAY_COMPLETED"
            if all(
                item["y_replay_status"] == "EXACT_SAVED_VALUE_REPRODUCED"
                and item["g_replay_status"] == "EXACT_SAVED_VALUE_REPRODUCED"
                for item in column_results
            )
            else "LOCAL_REPLAY_UNBOUND"
        ),
        "scope_note": (
            "Only the two complete saved-metadata incident cells for active row 87567 are rebuilt. "
            "Local replay diagnoses the stored V9 y9/g9 target row and does not pass or reopen the full action gate."
        ),
    }
    checkpoint("v11_selected_trace_candidate_replay", result)
    return result



def _run_v8_selected_trace_star_metadata_only(
    *,
    cfg: Any,
    donor: dict[str, Any],
    fixed_window: Any,
    output_directory: Path,
    consumer_contract: Mapping[str, Any],
    selected_active_row: int,
    allocation_gate: Any,
    persist_array: Any,
    progress: Any,
    checkpoint: Any,
) -> dict[str, Any]:
    """Persist one fresh selected-row MPC star without loading saved solution arrays."""

    import hashlib
    from mpi4py import MPI

    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.hcurl_assembly_time_condensation import (
        build_selected_volume_trace_star_metadata,
    )

    if fixed_window.sha256 != consumer_contract.get("window", {}).get("sha256"):
        raise ValueError("V8 metadata-only fixed-window hash differs from the consumer contract")
    if selected_active_row != TASK41_P0_V11_METADATA_ACTIVE_ROW:
        raise ValueError("V11 metadata-only selected row differs from the frozen target row")
    if len(donor.get("columns", ())) != 2:
        raise ValueError("V8 metadata-only donor does not contain exactly two columns")
    active_rows = np.asarray(donor["columns"][0]["active_original_rows"])
    second_map = np.asarray(donor["columns"][1]["active_original_rows"])
    if (
        active_rows.ndim != 1
        or active_rows.dtype.kind not in "iu"
        or not np.array_equal(active_rows, second_map)
    ):
        raise ValueError("V8 metadata-only donor active-row maps are invalid or disagree")
    active_rows = np.ascontiguousarray(active_rows, dtype=np.int64)
    if not 0 <= selected_active_row < active_rows.size:
        raise IndexError("V11 metadata-only active row lies outside the saved donor map")
    selected_original_row = int(active_rows[selected_active_row])
    allocation_gate(
        "v11_selected_trace_star_metadata_preflight",
        {
            "additional_payload_bytes": 0,
            "workspace_bytes": 6 * 1024**3,
            "estimated_remaining_seconds_upper": TASK41_P0_V5_PREFIX_MINIMUM_SECONDS,
            "metadata_only": True,
            "selected_active_row": selected_active_row,
            "selected_original_row": selected_original_row,
            "selected_work_scope": (
                "one p6/MPC row-numbering scan and selected incident-cell metadata; "
                "no saved vector replay, form, tensor, FFCx, owner, factor, or carrier"
            ),
        },
    )
    progress(
        {
            "phase": "selected_trace_star_metadata_only",
            "status": "STARTED",
            "selected_active_row": selected_active_row,
            "selected_original_row": selected_original_row,
        }
    )
    levels = _build_same_mesh_levels(
        cfg,
        MPI.COMM_SELF,
        (6,),
        include_positive_coefficients=False,
    )
    space = levels["spaces"][6]
    metadata = build_selected_volume_trace_star_metadata(
        space,
        levels["floquets"][6].mpc,
        levels["mesh_data"].cell_tags,
        selected_active_row=selected_active_row,
        expected_active_original_rows=active_rows,
        progress_callback=progress,
    )
    incidents = list(metadata["incidents"])
    incident_order = [int(item["cell_index"]) for item in incidents]
    if not incident_order or incident_order != sorted(set(incident_order)):
        raise ValueError("V11 selected-row incident cell list is empty, duplicated, or unordered")
    if int(metadata["selected_original_row"]) != selected_original_row:
        raise ValueError("V11 fresh metadata resolves a different original storage row")

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
    estimated_payload_bytes = sum(
        int(np.asarray(row[field]).nbytes) + 4096
        for row in incidents
        for field in metadata_fields
    )
    from src.runners.task41_p0_contract import task41_raw_artifact_limit_bytes

    allocation_gate(
        "v11_selected_trace_star_metadata_evidence_preflight",
        {
            "additional_payload_bytes": estimated_payload_bytes,
            "evidence_reserve_bytes": estimated_payload_bytes,
            "workspace_bytes": 512 * 1024**2,
            "estimated_remaining_seconds_upper": 0.0,
            "metadata_only": True,
            "new_evidence_limit_bytes": int(
                consumer_contract.get("execution_scope", {}).get(
                    "new_evidence_limit_bytes", 0
                )
            ),
            "raw_artifact_limit_bytes": int(
                task41_raw_artifact_limit_bytes(consumer_contract)
            ),
            "incident_cells": incident_order,
        },
    )
    selected_cells = []
    for row in incidents:
        cell_index = int(row["cell_index"])
        arrays = {}
        for field in metadata_fields:
            name = f"task41_p0_v11_selected_cell{cell_index}_{field}"
            arrays[field] = {"name": name, **persist_array(name, np.asarray(row[field]))}
        selected_cells.append(
            {
                "cell_index": cell_index,
                "cell_tag": int(row["cell_tag"]),
                "cell_permutation": int(row["cell_permutation"]),
                "actual_coordinate_sha256": str(row["actual_coordinate_sha256"]),
                "selected_local_trace_rows": np.asarray(
                    row["selected_local_trace_rows"], dtype=np.int64
                ).tolist(),
                "selected_trace_coefficients": [
                    [float(value.real), float(value.imag)]
                    for value in np.asarray(
                        row["selected_trace_coefficients"], dtype=np.complex128
                    )
                ],
                "selected_trace_contribution_kinds": list(
                    row["selected_trace_contribution_kinds"]
                ),
                "arrays": arrays,
            }
        )
    result = {
        "schema": "task41.p0.v8.selected_trace_star_metadata_only.v1",
        "status": "COMPLETED_METADATA_ONLY",
        "selected_active_row": selected_active_row,
        "selected_original_row": selected_original_row,
        "saved_active_original_rows_sha256": hashlib.sha256(
            memoryview(active_rows).cast("B")
        ).hexdigest(),
        "active_trace_rows": int(metadata["active_trace_rows"]),
        "full_trace_rows": int(metadata["full_trace_rows"]),
        "slave_rows": int(metadata["slave_rows"]),
        "full_storage_rows": int(metadata["full_storage_rows"]),
        "owned_cells_scanned": int(metadata["owned_cells"]),
        "element_dimension": int(metadata["element_dimension"]),
        "incident_cell_count": len(incident_order),
        "incident_cell_order": incident_order,
        "interior_positions": np.asarray(
            metadata["interior_positions"], dtype=np.int64
        ).tolist(),
        "trace_positions": np.asarray(
            metadata["trace_positions"], dtype=np.int64
        ).tolist(),
        "selected_cells": selected_cells,
        "numerical_work_started": False,
        "scope_note": (
            "Fresh p6/MPC active-row map equality and complete incident-cell metadata only; "
            "no saved solution-vector replay or numerical reconstruction."
        ),
    }
    checkpoint("selected_trace_star_metadata_only", result)
    progress(
        {
            "phase": "selected_trace_star_metadata_only",
            "status": "COMPLETED",
            "selected_active_row": selected_active_row,
            "selected_original_row": selected_original_row,
            "incident_cells": incident_order,
        }
    )
    return result


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--numerical-output", type=Path)
    parser.add_argument("--donor-contract", type=Path)
    parser.add_argument("--donor-contract-sha256")
    parser.add_argument("--consumer-contract", type=Path)
    parser.add_argument("--consumer-contract-sha256")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--geometry-pair-only", action="store_true")
    parser.add_argument("--selected-trace-star-audit", action="store_true")
    parser.add_argument("--selected-trace-star-metadata-only", action="store_true")
    parser.add_argument("--selected-trace-star-candidate-replay", action="store_true")
    parser.add_argument("--v17-selected-two-cell-replay", action="store_true")
    parser.add_argument("--v16-saved-vector-manifest", type=Path)
    parser.add_argument("--v16-saved-vector-manifest-sha256")
    parser.add_argument("--v17-consumer-contract", type=Path)
    parser.add_argument("--v17-consumer-contract-sha256")
    parser.add_argument("--v17-pre-admission", type=Path)
    parser.add_argument("--v17-pre-admission-sha256")
    parser.add_argument("--v17-producer-contract", type=Path)
    parser.add_argument("--v17-producer-contract-sha256")
    parser.add_argument("--v17-producer-progress", type=Path)
    parser.add_argument("--v17-producer-progress-sha256")
    parser.add_argument("--selected-metadata-report", type=Path)
    parser.add_argument("--selected-metadata-report-sha256")
    parser.add_argument("--v9-compact-report", type=Path)
    parser.add_argument("--v9-compact-report-sha256")
    parser.add_argument(
        "--selected-active-row", type=int, default=TASK41_P0_V8_SELECTED_ACTIVE_ROW
    )
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


def _dispatch_v11_candidate_replay_callback(
    args: argparse.Namespace,
    *,
    callback: Any,
    callback_kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    """Route the service-built candidate request to the local FE callback."""
    if (
        not args.selected_trace_star_candidate_replay
        or args.selected_active_row != TASK41_P0_V11_METADATA_ACTIVE_ROW
        or args.geometry_policy != "mesh_actual_exact"
        or args.raw_tensor_evaluator != "actual_qmetric_blocked_gram"
        or args.ffcx_c_source is None
        or args.selected_metadata_report is None
        or args.v9_compact_report is None
    ):
        raise ValueError("service worker request is not the frozen selected-candidate replay")
    return callback(args=args, **dict(callback_kwargs))


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
    metadata_only = checked.get("metadata_only") is True
    cumulative = int(prior_array_payload_bytes) + int(persisted_array_bytes) + evidence_reserve
    if metadata_only and (
        int(persisted_array_bytes) + evidence_reserve
        > int(checked.get("new_evidence_limit_bytes", 0))
    ):
        raise _CandidateNotAdmitted(
            f"{label}: metadata-only evidence would exceed the fixed new-evidence limit"
        )
    if cumulative > int(checked.get("raw_artifact_limit_bytes", 16 * 1024**3)):
        raise _CandidateNotAdmitted(
            f"{label}: selected-star evidence would exceed its cumulative raw-artifact cap by "
            f"{cumulative - int(checked.get('raw_artifact_limit_bytes', 16 * 1024**3))} bytes"
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
        "evidence_cap_bytes": int(
            checked.get("new_evidence_limit_bytes", 16 * 1024**3)
        ) if metadata_only else 16 * 1024**3,
        "cumulative_raw_artifact_limit_bytes": int(
            checked.get("raw_artifact_limit_bytes", 16 * 1024**3)
        ),
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

    if not (
        bool(getattr(worker_args, "selected_trace_star_audit", False))
        or bool(getattr(worker_args, "selected_trace_star_metadata_only", False))
        or bool(getattr(worker_args, "selected_trace_star_candidate_replay", False))
    ):
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
    if args.v17_selected_two_cell_replay:
        unexpected = [
            name for name, value in vars(args).items()
            if name not in {
                "v17_selected_two_cell_replay", "v16_saved_vector_manifest",
                "v16_saved_vector_manifest_sha256", "v17_consumer_contract",
                "v17_consumer_contract_sha256", "v17_pre_admission",
                "v17_producer_contract", "v17_producer_contract_sha256",
                "v17_producer_progress", "v17_producer_progress_sha256",
                "v17_pre_admission_sha256", "output_dir", "selected_active_row",
                "geometry_policy", "raw_tensor_evaluator", "ffcx_c_source",
            }
            and value not in (None, False, TASK41_P0_V8_SELECTED_ACTIVE_ROW)
        ]
        if (
            args.v16_saved_vector_manifest is None
            or args.v16_saved_vector_manifest_sha256 is None
            or args.v17_consumer_contract is None
            or args.v17_consumer_contract_sha256 is None
            or args.v17_pre_admission is None
            or args.v17_pre_admission_sha256 is None
            or args.selected_active_row != TASK41_P0_V17_ACTIVE_ROW
            or args.geometry_policy != "mesh_actual_exact"
            or args.raw_tensor_evaluator != "actual_qmetric_blocked_gram"
            or args.ffcx_c_source is None
            or (args.v17_producer_contract is None)
            != (args.v17_producer_contract_sha256 is None)
            or (args.v17_producer_progress is None)
            != (args.v17_producer_progress_sha256 is None)
            or (args.v17_producer_contract is None)
            != (args.v17_producer_progress is None)
            or unexpected
        ):
            raise ValueError("V17 worker requires only its fixed consumer, manifest, row, and q-metric bindings")
        result = _run_v17_selected_two_cell_replay(args)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    if any(
        value is None
        for value in (
            args.summary, args.numerical_output, args.donor_contract,
            args.donor_contract_sha256, args.consumer_contract,
            args.consumer_contract_sha256,
        )
    ):
        raise ValueError("legacy volume-audit modes require summary, numerical output, and both contracts")
    selected_trace_metadata_mode = bool(
        args.selected_trace_star_audit
        or args.selected_trace_star_metadata_only
        or args.selected_trace_star_candidate_replay
    )
    if selected_trace_metadata_mode and args.geometry_pair_only:
        raise ValueError("V8 selected trace-star audit cannot use the V4 geometry-pair mode")
    if args.geometry_pair_only != (args.source_report is not None):
        raise ValueError("--geometry-pair-only and --source-report must be provided together")
    if args.geometry_pair_only and args.geometry_policy != "canonical":
        raise ValueError("the selected-cell geometry-pair diagnostic remains canonical-only")
    if (
        args.geometry_policy == "mesh_actual_exact"
        and args.geometry_reference_report is None
        and not selected_trace_metadata_mode
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
    if args.selected_trace_star_metadata_only and (
        args.geometry_policy != "mesh_actual_exact"
        or args.selected_trace_star_audit
        or args.raw_tensor_evaluator is not None
        or args.ffcx_c_source is not None
        or args.selected_active_row != TASK41_P0_V11_METADATA_ACTIVE_ROW
    ):
        raise ValueError(
            "V11 metadata-only requires mesh_actual_exact, row 87567, and no numeric evaluator or FFCx source"
        )
    if args.selected_trace_star_candidate_replay and (
        args.geometry_policy != "mesh_actual_exact"
        or args.selected_trace_star_audit
        or args.selected_trace_star_metadata_only
        or args.raw_tensor_evaluator != "actual_qmetric_blocked_gram"
        or args.ffcx_c_source is None
        or args.selected_active_row != TASK41_P0_V11_METADATA_ACTIVE_ROW
        or args.selected_metadata_report is None
        or args.selected_metadata_report_sha256 is None
        or args.v9_compact_report is None
        or args.v9_compact_report_sha256 is None
    ):
        raise ValueError(
            "V11 candidate replay requires row 87567, frozen q-metric source, and hash-bound metadata/V9 reports"
        )
    if not args.selected_trace_star_candidate_replay and any(
        value is not None
        for value in (
            args.selected_metadata_report,
            args.selected_metadata_report_sha256,
            args.v9_compact_report,
            args.v9_compact_report_sha256,
        )
    ):
        raise ValueError("V11 report bindings require the selected candidate replay mode")
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
        if not selected_trace_metadata_mode:
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
        "selected_trace_star_candidate_replay"
        if args.selected_trace_star_candidate_replay
        else "selected_trace_star_metadata_only"
        if args.selected_trace_star_metadata_only
        else "selected_trace_star_audit"
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
        "task41_p0_v11_selected_trace_candidate_replay.json"
        if args.selected_trace_star_candidate_replay
        else "task41_p0_v8_selected_trace_star_metadata.json"
        if args.selected_trace_star_metadata_only
        else "task41_p0_v8_selected_trace_star_audit.json"
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
        "task41_p0_v11_selected_trace_candidate_replay_phase.json"
        if args.selected_trace_star_candidate_replay
        else "task41_p0_v8_selected_trace_star_metadata_phase.json"
        if args.selected_trace_star_metadata_only
        else "task41_p0_v8_selected_trace_star_phase.json"
        if args.selected_trace_star_audit
        else "task41_p0_v4_volume_only_phase.json"
    )
    event_path = output_root / (
        "task41_p0_v11_selected_trace_candidate_replay_events.jsonl"
        if args.selected_trace_star_candidate_replay
        else "task41_p0_v8_selected_trace_star_metadata_events.jsonl"
        if args.selected_trace_star_metadata_only
        else "task41_p0_v8_selected_trace_star_events.jsonl"
        if args.selected_trace_star_audit
        else "task41_p0_v4_volume_only_events.jsonl"
    )
    donor = load_task41_v4_volume_only_donor(
        summary_path=args.summary,
        numerical_output=args.numerical_output,
        metadata_only=args.selected_trace_star_metadata_only,
    )
    v11_prior_cumulative_evidence_bytes = None
    if args.selected_trace_star_candidate_replay:
        if sha256_file(args.v9_compact_report) != TASK41_P0_V11_V9_COMPACT_REPORT_SHA256:
            raise ValueError("V11 compact report hash differs before evidence admission")
        v11_compact_for_budget = json.loads(
            args.v9_compact_report.read_text(encoding="utf-8")
        )
        prior_value = v11_compact_for_budget.get("cumulative_evidence_bytes")
        if type(prior_value) is not int or prior_value < 0:
            raise ValueError("V11 compact report omits its cumulative raw-evidence total")
        v11_prior_cumulative_evidence_bytes = prior_value
    geometry_reference = (
        _load_v5_geometry_reference(
            args.geometry_reference_report,
            donor_manifest_sha256=str(donor["manifest_sha256"]),
            sha256_file=sha256_file,
        )
        if args.geometry_policy == "mesh_actual_exact" and not selected_trace_metadata_mode
        else None
    )
    run_record: dict[str, Any] = {
        "schema": (
            "task41.p0.v11.selected_trace_star_candidate_replay_receipt.v1"
            if args.selected_trace_star_candidate_replay
            else "task41.p0.v8.selected_trace_star_metadata_only_receipt.v1"
            if args.selected_trace_star_metadata_only
            else "task41.p0.v8.selected_trace_star_audit_receipt.v1"
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
        "consumer_window_path": str(fixed_window.path) if fixed_window is not None else None,
        "consumer_window_sha256": fixed_window.sha256 if fixed_window is not None else None,
        "selected_metadata_report_path": (
            str(args.selected_metadata_report.resolve())
            if args.selected_metadata_report is not None
            else None
        ),
        "selected_metadata_report_sha256": args.selected_metadata_report_sha256,
        "v9_compact_report_path": (
            str(args.v9_compact_report.resolve())
            if args.v9_compact_report is not None
            else None
        ),
        "v9_compact_report_sha256": args.v9_compact_report_sha256,
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
        if args.selected_trace_star_metadata_only or args.selected_trace_star_candidate_replay:
            from src.runners.task41_p0_contract import task41_raw_artifact_limit_bytes

            new_cap = int(
                consumer_contract.get("execution_scope", {}).get(
                    "new_evidence_limit_bytes", 0
                )
            )
            raw_cap = int(task41_raw_artifact_limit_bytes(consumer_contract))
            persisted_after = int(run_record.get("persisted_evidence_bytes", 0)) + array_bytes_upper
            cumulative_base = (
                int(v11_prior_cumulative_evidence_bytes)
                if args.selected_trace_star_candidate_replay
                else int(donor.get("existing_evidence_bytes", 0))
            )
            cumulative_after = cumulative_base + persisted_after
            window_root = output_root.parent.parent
            prior_window_output_bytes = 0
            if args.selected_trace_star_candidate_replay:
                for prior_path in window_root.rglob("*"):
                    if prior_path.is_file() and not prior_path.is_relative_to(output_root):
                        prior_window_output_bytes += int(prior_path.stat().st_size)
            new_evidence_after = prior_window_output_bytes + persisted_after
            if new_evidence_after > new_cap:
                raise MemoryError(
                    "V11 candidate replay would exceed the fixed 512 MiB window-wide new-evidence cap"
                )
            if cumulative_after > raw_cap:
                raise MemoryError(
                    "V11 selected evidence would exceed the fixed cumulative raw-artifact cap"
                )
            free_before = int(shutil.disk_usage(output_directory).free)
            if free_before - array_bytes_upper < 2 * 1024**3:
                raise OSError(
                    "V11 selected evidence write would breach the 2 GiB free-space floor"
                )
        elif args.selected_trace_star_audit:
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
        if args.geometry_policy == "mesh_actual_exact" and not selected_trace_metadata_mode
        else None
    )

    def allocation_gate(label: str, facts: Mapping[str, Any]) -> None:
        checked_facts = dict(facts)
        if selected_trace_metadata_mode:
            if fixed_window is None:
                raise RuntimeError("V8 selected-star admission requires the fixed numeric window")
            checked_facts.setdefault(
                "metadata_only", bool(args.selected_trace_star_metadata_only)
            )
            if args.selected_trace_star_metadata_only or args.selected_trace_star_candidate_replay:
                from src.runners.task41_p0_contract import task41_raw_artifact_limit_bytes

                checked_facts.setdefault(
                    "new_evidence_limit_bytes",
                    int(
                        consumer_contract.get("execution_scope", {}).get(
                            "new_evidence_limit_bytes", 0
                        )
                    ),
                )
                checked_facts.setdefault(
                    "raw_artifact_limit_bytes",
                    int(task41_raw_artifact_limit_bytes(consumer_contract)),
                )
            admission = _v8_selected_trace_star_worker_allocation_gate(
                args,
                label,
                checked_facts,
                fixed_window=fixed_window,
                resources=consumer_contract["resources"],
                resource_admission=_resource_admission,
                resource_snapshot=_resource_snapshot,
                output_directory=output_directory,
                prior_array_payload_bytes=(
                    int(v11_prior_cumulative_evidence_bytes)
                    if args.selected_trace_star_candidate_replay
                    else int(donor.get("existing_evidence_bytes", 0))
                    if args.selected_trace_star_metadata_only
                    else TASK41_P0_V8_PRIOR_ARRAY_BYTES
                ),
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
        if selected_trace_metadata_mode:
            if fixed_window is None:
                raise RuntimeError("V8 selected trace-star audit requires the fixed numeric window")
            selected_result = (
                _dispatch_v11_candidate_replay_callback(
                    args,
                    callback=_run_v11_selected_trace_star_candidate_replay,
                    callback_kwargs={
                        "cfg": cfg,
                        "donor": donor,
                        "fixed_window": fixed_window,
                        "output_directory": output_directory,
                        "consumer_contract": consumer_contract,
                        "consumer_contract_sha256": consumer_digest,
                        "sha256_file": sha256_file,
                        "allocation_gate": allocation_gate,
                        "persist_array": persist_volume_array,
                        "progress": progress,
                        "checkpoint": checkpoint,
                    },
                )
                if args.selected_trace_star_candidate_replay
                else _run_v8_selected_trace_star_audit(
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
                    metadata_only=args.selected_trace_star_metadata_only,
                    selected_active_row=args.selected_active_row,
                )
            )
            run_record.update(
                {
                    "schema": (
                        "task41.p0.v11.selected_trace_star_candidate_replay_receipt.v1"
                        if args.selected_trace_star_candidate_replay
                        else run_record["schema"]
                    ),
                    "status": (
                        "COMPLETED_LOCAL_CANDIDATE_REPLAY"
                        if args.selected_trace_star_candidate_replay
                        else "COMPLETED_METADATA_ONLY"
                        if args.selected_trace_star_metadata_only
                        else "COMPLETED_SELECTED_TRACE_STAR_AUDIT"
                    ),
                    "independent_checker_status": "NOT_APPLICABLE_METADATA_ONLY"
                    if args.selected_trace_star_metadata_only
                    else "NOT_RUN",
                    "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                    "elapsed_since_worker_start_seconds": perf_counter() - started_perf,
                    "v11_selected_trace_candidate_replay"
                    if args.selected_trace_star_candidate_replay
                    else "selected_trace_star_metadata_only"
                    if args.selected_trace_star_metadata_only
                    else "selected_trace_star_audit": selected_result,
                    "evidence_cap_bytes": (
                        int(consumer_contract.get("execution_scope", {}).get("new_evidence_limit_bytes", 0))
                        if args.selected_trace_star_metadata_only or args.selected_trace_star_candidate_replay
                        else 16 * 1024**3
                    ),
                    "free_space_floor_bytes": 2 * 1024**3,
                }
            )
            _write_json_atomic(report_path, run_record)
            progress(
                {
                    "phase": "v11_selected_trace_candidate_replay"
                    if args.selected_trace_star_candidate_replay
                    else "selected_trace_star_metadata_only"
                    if args.selected_trace_star_metadata_only
                    else "selected_trace_star_audit",
                    "status": "COMPLETED",
                    "incident_cells": int(
                        len(selected_result["incident_cell_order"])
                        if args.selected_trace_star_candidate_replay
                        else selected_result["incident_cell_count"]
                        if args.selected_trace_star_metadata_only
                        else selected_result["metadata"]["incident_cell_count"]
                    ),
                    **(
                        {"numerical_work_started": False}
                        if args.selected_trace_star_metadata_only
                        else {"candidate_cells_reconstructed": list(TASK41_P0_V11_SELECTED_CELLS)}
                        if args.selected_trace_star_candidate_replay
                        else {
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
                            )
                        }
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
            else "FAILED_METADATA_ONLY_EVIDENCE_RETAINED"
            if args.selected_trace_star_metadata_only
            else "FAILED_SELECTED_CANDIDATE_REPLAY_EVIDENCE_RETAINED"
            if args.selected_trace_star_candidate_replay
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
                    "v11_selected_trace_candidate_replay"
                    if args.selected_trace_star_candidate_replay
                    else "selected_trace_star_metadata_only"
                    if args.selected_trace_star_metadata_only
                    else "v8_selected_trace_star_audit"
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
