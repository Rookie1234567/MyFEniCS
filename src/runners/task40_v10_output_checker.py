"""Independent integrity and full-residual recheck for Task40 V10 packets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

_TASK40_V10_INTERNAL_RECOVERY_LIMIT = 1.0e-11


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _raw_array_ref(record: Mapping[str, Any], key: str, arrays: Any) -> np.ndarray:
    reference = record.get(key)
    if not isinstance(reference, Mapping) or not isinstance(reference.get("array_key"), str):
        raise ValueError(f"saved residual packet is missing array reference {key!r}")
    value = np.asarray(arrays[reference["array_key"]])
    if list(value.shape) != reference.get("shape"):
        raise ValueError(f"saved residual array {key!r} changed shape")
    return value


def _array_ref(record: Mapping[str, Any], key: str, arrays: Any) -> np.ndarray:
    return np.asarray(_raw_array_ref(record, key, arrays), dtype=np.complex128)


def verify_v10_regular_internal_witness(packet_json: str | Path) -> dict[str, Any]:
    """Recompute Task40's 36,000-row internal recovery from saved raw arrays."""

    path = Path(packet_json).resolve()
    record = json.loads(path.read_text(encoding="utf-8"))
    array_manifest = record.get("arrays")
    if not isinstance(array_manifest, Mapping):
        raise ValueError("V10 regular witness packet has no NPZ array manifest")
    npz_path = Path(str(array_manifest["path"])).resolve()
    actual_npz_sha = _file_sha256(npz_path)
    if actual_npz_sha != array_manifest.get("sha256"):
        raise ValueError("V10 regular witness NPZ identity check failed")

    with np.load(npz_path, allow_pickle=False) as arrays:
        effective_rhs = _array_ref(record, "full_internal_effective_rhs", arrays)
        saved_action = _array_ref(record, "full_internal_saved_field_action", arrays)
        saved_residual = _array_ref(record, "full_internal_recovery_residuals", arrays)
        original_rows = _raw_array_ref(record, "full_internal_original_rows", arrays)
        twists = _raw_array_ref(record, "full_internal_twist_indices", arrays)

    expected_rows = int(record.get("full_internal_recovery_rows", 0))
    if expected_rows != 36_000:
        raise ValueError("V10 regular witness must cover exactly 36,000 internal rows")
    row_shape = (expected_rows,)
    if any(
        vector.shape != row_shape
        for vector in (effective_rhs, saved_action, saved_residual, original_rows, twists)
    ):
        raise ValueError("V10 regular internal raw arrays do not share the 36,000-row layout")
    if not np.issubdtype(original_rows.dtype, np.integer) or not np.issubdtype(
        twists.dtype, np.integer
    ):
        raise ValueError("V10 regular internal row identity arrays must be integers")
    if not np.isfinite(effective_rhs).all() or not np.isfinite(saved_action).all():
        raise ValueError("V10 regular internal raw action arrays contain non-finite values")
    if not np.array_equal(np.unique(twists), np.array([0, 1], dtype=twists.dtype)):
        raise ValueError("V10 regular internal raw arrays do not identify both twists")
    ordered = np.lexsort((original_rows, twists))
    row_pairs = np.rec.fromarrays((twists, original_rows))
    if not np.array_equal(ordered, np.arange(expected_rows)) or np.unique(row_pairs).size != expected_rows:
        raise ValueError("V10 regular internal twist/row order is not unique and canonical")

    recomputed = effective_rhs - saved_action
    scale = float(record["full_internal_recovery_operation_scale"])
    limits = record.get("limits")
    if not isinstance(limits, Mapping) or "full_internal_recovery" not in limits:
        raise ValueError("V10 regular witness is missing limits.full_internal_recovery")
    recorded_limit = float(limits["full_internal_recovery"])
    if "full_internal_recovery_limit" in record:
        duplicate_limit = float(record["full_internal_recovery_limit"])
        if not np.isfinite(duplicate_limit) or duplicate_limit != recorded_limit:
            raise ValueError("V10 regular internal recovery limit fields conflict")
    stored_relative = float(record["full_internal_recovery_relative"])
    if not np.isfinite(scale) or scale < 0.0:
        raise ValueError("V10 regular internal operation scale is invalid")
    if (
        not np.isfinite(recorded_limit)
        or recorded_limit != _TASK40_V10_INTERNAL_RECOVERY_LIMIT
    ):
        raise ValueError("V10 regular internal witness limit differs from fixed 1e-11 contract")
    limit = _TASK40_V10_INTERNAL_RECOVERY_LIMIT
    denominator = max(scale, np.finfo(float).tiny)
    relative = float(np.linalg.norm(recomputed) / denominator)
    algebra_defect = float(
        np.linalg.norm(recomputed - saved_residual)
        / max(
            float(np.linalg.norm(effective_rhs)) + float(np.linalg.norm(saved_action)),
            np.finfo(float).tiny,
        )
    )
    passed = bool(
        np.isfinite(relative)
        and relative <= limit
        and abs(relative - stored_relative) <= 1.0e-12
        and algebra_defect <= 1.0e-12
    )
    if not passed:
        raise ValueError("V10 regular internal residual failed raw-array recomputation")
    return {
        "schema": "task40extra.review_v10_regular_internal_witness_recheck.v1",
        "packet_json": str(path),
        "packet_npz": str(npz_path),
        "packet_npz_sha256": actual_npz_sha,
        "internal_row_count": expected_rows,
        "twist_row_order": "twist_index ascending; original storage row ascending within twist",
        "recomputed_relative_residual": relative,
        "stored_relative_residual": stored_relative,
        "residual_algebra_defect_relative": algebra_defect,
        "operation_scale": scale,
        "limit": limit,
        "passed": True,
        "operator_reapplied_by_checker": False,
    }


def verify_v10_output_bundle(packet_json: str | Path) -> dict[str, Any]:
    """Reopen output identities and independently recompute saved A6 residuals.

    The checker verifies the saved backend applications and their residual
    algebra.  It does not claim to rerun DOLFINx or independently apply A6.
    The worker's distinct sum-factorized and native applications remain the
    operator evidence.
    """
    path = Path(packet_json).resolve()
    record = json.loads(path.read_text(encoding="utf-8"))
    identity = record.get("scientific_identity")
    if not isinstance(identity, Mapping):
        raise ValueError("V10 output packet has no scientific identity")
    file_checks = []
    for item in identity.get("field_mode_and_diffraction_files", ()):
        file_path = Path(str(item["path"])).resolve()
        actual = _file_sha256(file_path)
        file_checks.append({
            "path": str(file_path),
            "expected_sha256": str(item["sha256"]),
            "actual_sha256": actual,
            "size_bytes": file_path.stat().st_size,
            "passed": actual == item["sha256"],
        })
    if not all(row["passed"] for row in file_checks):
        raise ValueError("V10 scientific field/mode output file identity check failed")

    residual_path = Path(str(identity["full_solution_packet_json"])).resolve()
    residual_record = json.loads(residual_path.read_text(encoding="utf-8"))
    array_manifest = residual_record.get("arrays")
    if not isinstance(array_manifest, Mapping):
        raise ValueError("V10 final full-state packet has no NPZ array manifest")
    npz_path = Path(str(array_manifest["path"])).resolve()
    actual_npz_sha = _file_sha256(npz_path)
    if actual_npz_sha != array_manifest.get("sha256"):
        raise ValueError("V10 final full-state NPZ identity check failed")

    residual_checks = []
    with np.load(npz_path, allow_pickle=False) as arrays:
        rhs = _array_ref(residual_record, "full_physical_rhs_storage", arrays)
        solution = _array_ref(residual_record, "full_solution_storage", arrays)
        if solution.shape != rhs.shape:
            raise ValueError("V10 full solution and physical RHS layouts differ")
        for label, applied_key, residual_key, stored_relative in (
            (
                "sum_factorized_target_backend",
                "target_backend_applied_storage",
                "target_backend_residual_storage",
                float(residual_record["relative_residual"]),
            ),
            (
                "native_full_A6_witness",
                "native_witness_applied_storage",
                "native_witness_residual_storage",
                float(residual_record["native_witness_relative_residual"]),
            ),
        ):
            applied = _array_ref(residual_record, applied_key, arrays)
            saved_residual = _array_ref(residual_record, residual_key, arrays)
            recomputed = rhs - applied
            scale = max(float(np.linalg.norm(rhs)), np.finfo(float).tiny)
            relative = float(np.linalg.norm(recomputed) / scale)
            algebra_defect = float(
                np.linalg.norm(recomputed - saved_residual)
                / max(scale + float(np.linalg.norm(saved_residual)), np.finfo(float).tiny)
            )
            residual_checks.append({
                "backend": label,
                "recomputed_relative_residual": relative,
                "stored_relative_residual": stored_relative,
                "residual_algebra_defect_relative": algebra_defect,
                "limit": float(residual_record["limit"]),
                "passed": bool(
                    np.isfinite(relative)
                    and relative <= float(residual_record["limit"])
                    and abs(relative - stored_relative) <= 1.0e-12
                    and algebra_defect <= 1.0e-12
                ),
            })
    if not all(row["passed"] for row in residual_checks):
        raise ValueError("V10 independently recomputed saved residual did not pass")
    return {
        "schema": "task40extra.review_v10_output_packet_recheck.v1",
        "packet_json": str(path),
        "residual_packet_json": str(residual_path),
        "residual_packet_npz": str(npz_path),
        "residual_packet_npz_sha256": actual_npz_sha,
        "full_solution_storage_sha256": str(identity["full_solution_storage_sha256"]),
        "ordered_physical_mode_sha256": str(identity["ordered_physical_mode_sha256"]),
        "field_mode_and_diffraction_file_checks": file_checks,
        "residual_checks": residual_checks,
        "operator_reapplied_by_checker": False,
        "status": "PASS",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet_json", type=Path)
    parser.add_argument("--regular-internal-witness", action="store_true")
    args = parser.parse_args(argv)
    result = (
        verify_v10_regular_internal_witness(args.packet_json)
        if args.regular_internal_witness
        else verify_v10_output_bundle(args.packet_json)
    )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
