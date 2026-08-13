"""Offline, hash-bound aggregation of the four Task039 trace captures."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from benchmarks.task039_review_v1_contracts import audit_m960_trace

FAMILY_MS = (120, 240, 480, 960)
EXPECTED_SOURCE_SHA = "34bca037870cc4d7d132dcfbec71981a867213b8"
SIDES = ("bottom", "top")
MATRIX_NAMES = (
    "surface_gram",
    "raw_negative_overlap",
    "canonical_negative_overlap",
    "canonical_mapping",
    "repeat_surface_gram",
    "repeat_raw_overlap",
    "repeat_canonical_negative_overlap",
    "repeat_canonical_mapping",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _descriptor_matches(
    descriptor: Mapping[str, Any], array: np.ndarray, label: str
) -> None:
    value = np.asarray(array)
    _require(
        descriptor.get("shape") == list(value.shape),
        f"{label} descriptor shape mismatch",
    )
    _require(descriptor.get("dtype") == str(value.dtype), f"{label} dtype mismatch")
    _require(descriptor.get("bytes") == int(value.nbytes), f"{label} byte mismatch")
    _require(
        descriptor.get("sha256")
        == hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest(),
        f"{label} array SHA mismatch",
    )
    _require(
        descriptor.get("finite") is bool(np.isfinite(value).all()),
        f"{label} finite descriptor mismatch",
    )


def _column_identity(capture: Mapping[str, Any], dimension: int) -> bool:
    keys = capture.get("column_keys")
    identifiers = capture.get("mode_identifiers")
    if not isinstance(keys, list) or not isinstance(identifiers, list):
        return False
    if len(keys) != dimension or len(identifiers) != dimension:
        return False
    for index, (key, identifier) in enumerate(zip(keys, identifiers, strict=True)):
        if not isinstance(key, list) or len(key) != 4:
            return False
        if not isinstance(identifier, Mapping):
            return False
        if key != identifier.get("key") or key[0] != index:
            return False
        if identifier.get("index") != index or key[1] != "backward":
            return False
        if identifier.get("direction") != "backward":
            return False
        if key[2:] != identifier.get("beta"):
            return False

    groups = capture.get("degenerate_groups")
    if not isinstance(groups, list):
        return False
    covered: list[int] = []
    for group in groups:
        if not isinstance(group, Mapping):
            return False
        indices = group.get("indices")
        group_keys = group.get("keys")
        if not isinstance(indices, list) or not isinstance(group_keys, list):
            return False
        if len(indices) != len(group_keys) or not indices:
            return False
        for index, key in zip(indices, group_keys, strict=True):
            if not isinstance(index, int) or index < 0 or index >= dimension:
                return False
            if key != keys[index] or index in covered:
                return False
            covered.append(index)
    return covered == list(range(dimension))


def _identity_and_root(record_path: Path, record: Mapping[str, Any], mode: int) -> dict:
    metadata = record.get("metadata")
    _require(isinstance(metadata, Mapping), f"M{mode} metadata missing")
    _require(
        metadata.get("source_commit_sha") == EXPECTED_SOURCE_SHA,
        f"M{mode} source SHA mismatch",
    )
    _require(metadata.get("mpi_size") == 8, f"M{mode} MPI size is not 8")
    _require(
        metadata.get("requested_modes_per_direction") == mode,
        f"M{mode} requested mode count mismatch",
    )
    for name in ("input_sha256", "resolved_config_sha256", "physical_model_sha256"):
        value = metadata.get(name)
        _require(isinstance(value, str) and len(value) == 64, f"M{mode} {name} missing")

    root = record_path.parents[2]
    for filename, expected in (
        ("source_sha.txt", EXPECTED_SOURCE_SHA),
        ("input_sha256.txt", metadata["input_sha256"]),
        ("physical_model_sha256.txt", metadata["physical_model_sha256"]),
    ):
        path = root / filename
        _require(path.is_file(), f"M{mode} missing {filename}")
        _require(
            path.read_text(encoding="utf-8").strip() == expected,
            f"M{mode} {filename} mismatch",
        )
    input_path = root / "input_original.dat"
    _require(input_path.is_file(), f"M{mode} input_original.dat missing")
    _require(
        _sha256(input_path) == metadata["input_sha256"], f"M{mode} input SHA mismatch"
    )
    resolved = root / "resolved_config.json"
    _require(resolved.is_file(), f"M{mode} resolved_config.json missing")
    _require(
        _sha256(resolved) == metadata["resolved_config_sha256"],
        f"M{mode} resolved SHA mismatch",
    )
    manifest = root / "run_manifest.json"
    _require(manifest.is_file(), f"M{mode} run_manifest.json missing")
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    _require(
        manifest_data.get("source_sha") == EXPECTED_SOURCE_SHA,
        f"M{mode} manifest source SHA mismatch",
    )
    _require(
        manifest_data.get("physical_model_sha256") == metadata["physical_model_sha256"],
        f"M{mode} manifest physical SHA mismatch",
    )
    _require(manifest_data.get("mpi_size") == 8, f"M{mode} manifest MPI mismatch")
    _require(
        manifest_data.get("requested_modes") == mode,
        f"M{mode} manifest requested mode mismatch",
    )
    _require(
        manifest_data.get("method") == "hybrid_direct"
        and manifest_data.get("resolved_method_adapter") == "task039.hybrid_direct",
        f"M{mode} manifest Hybrid direct adapter mismatch",
    )
    inventory = manifest_data.get("external_mode_inventory")
    _require(
        isinstance(inventory, Mapping) and inventory.get("count") == 604,
        f"M{mode} external inventory count mismatch",
    )
    _require(
        manifest_data.get("result_classification") == "task039_trace_capture_complete",
        f"M{mode} manifest result classification mismatch",
    )
    _require(manifest_data.get("exit_status") == 0, f"M{mode} manifest exit mismatch")
    for key in ("input_sha256", "resolved_config_sha256"):
        _require(
            manifest_data.get(key) == metadata[key],
            f"M{mode} manifest {key} mismatch",
        )
    return {
        "source_commit_sha": EXPECTED_SOURCE_SHA,
        "input_sha256": metadata["input_sha256"],
        "resolved_config_sha256": metadata["resolved_config_sha256"],
        "physical_model_sha256": metadata["physical_model_sha256"],
        "mpi_size": 8,
    }


def _history_entry(audit: Mapping[str, Any], sign_order: bool) -> dict[str, Any]:
    gates = audit["gates"]
    finite = bool(
        gates["finite_all_trace_arrays"]["pass"]
        and gates["finite_gram_mapping"]["pass"]
    )
    return {
        "raw_forward_error": float(audit["raw_forward_error"]),
        "backward_error_eta": float(audit["backward_error_eta"]),
        "dimension": int(audit["dimension"]),
        "dynamic_backward_error_limit": float(audit["dynamic_backward_error_limit"]),
        "representation_error": float(audit["representation_error"]),
        "finite": finite,
        "sign_order_exact": bool(sign_order),
        "gram_condition": float(audit["gram_condition"]),
    }


def _reported_scalars_match(
    recorded: Mapping[str, Any], audit: Mapping[str, Any], mode: int, side: str
) -> None:
    for field in (
        "raw_forward_error",
        "representation_error",
        "backward_error_eta",
        "repeat_backward_error_eta",
        "repeat_backward_error_denominator",
        "repeat_raw_forward_error",
        "repeat_representation_error",
        "dynamic_backward_error_limit",
        "gram_condition",
    ):
        reported = recorded.get(field)
        recomputed = audit.get(field)
        _require(
            isinstance(reported, (int, float))
            and math.isclose(
                float(reported), float(recomputed), rel_tol=1.0e-12, abs_tol=1.0e-30
            ),
            f"M{mode} {side} reported audit scalar {field} mismatch",
        )
    reported_differences = recorded.get("repeat_matrix_differences")
    recomputed_differences = audit.get("repeat_matrix_differences")
    _require(
        isinstance(reported_differences, Mapping)
        and isinstance(recomputed_differences, Mapping),
        f"M{mode} {side} repeat matrix differences missing",
    )
    for matrix_name in ("raw_negative_overlap", "surface_gram", "canonical_mapping"):
        for metric in ("absolute", "denominator", "relative"):
            reported = reported_differences.get(matrix_name, {}).get(metric)
            recomputed = recomputed_differences.get(matrix_name, {}).get(metric)
            _require(
                isinstance(reported, (int, float))
                and math.isclose(
                    float(reported),
                    float(recomputed),
                    rel_tol=1.0e-12,
                    abs_tol=1.0e-30,
                ),
                f"M{mode} {side} reported repeat {matrix_name}.{metric} mismatch",
            )


def _load_capture(record_path: str | Path, mode: int) -> dict[str, Any]:
    path = Path(record_path)
    _require(path.is_file(), f"M{mode} evidence JSON missing")
    record = json.loads(path.read_text(encoding="utf-8"))
    _require(
        record.get("schema") == "task039.review-v1.m960-trace-evidence.v1",
        f"M{mode} schema mismatch",
    )
    _require(
        record.get("status") == "controlled_stop_ready", f"M{mode} status mismatch"
    )
    _require(
        record.get("individual_capture_complete") is True, f"M{mode} capture incomplete"
    )
    identity = _identity_and_root(path, record, mode)
    capture = record.get("capture")
    _require(
        isinstance(capture, Mapping) and capture.get("mode_count") == mode,
        f"M{mode} mode count mismatch",
    )
    sign_order = _column_identity(capture, mode)
    _require(sign_order, f"M{mode} column/sign/order identity mismatch")
    sides = capture.get("sides")
    _require(
        isinstance(sides, Mapping) and set(sides) == set(SIDES),
        f"M{mode} bottom/top sides missing",
    )
    artifact = record.get("artifact")
    _require(isinstance(artifact, Mapping), f"M{mode} artifact missing")
    expected_keys = {f"{side}_{name}" for side in SIDES for name in MATRIX_NAMES}
    _require(
        set(artifact.get("keys", [])) == expected_keys,
        f"M{mode} artifact key set mismatch",
    )
    npz_path = path.parent / str(artifact.get("path", ""))
    _require(
        npz_path.name == f"task039_trace_evidence_m{mode}.npz" and npz_path.is_file(),
        f"M{mode} NPZ missing",
    )
    _require(
        artifact.get("bytes") == npz_path.stat().st_size, f"M{mode} NPZ byte mismatch"
    )
    npz_sha = _sha256(npz_path)
    _require(artifact.get("sha256") == npz_sha, f"M{mode} NPZ SHA mismatch")
    arrays: dict[str, np.ndarray] = {}
    with np.load(npz_path, allow_pickle=False) as archive:
        _require(set(archive.files) == expected_keys, f"M{mode} NPZ key set mismatch")
        arrays = {key: np.array(archive[key], copy=True) for key in archive.files}
    artifact_arrays = artifact.get("arrays")
    _require(
        isinstance(artifact_arrays, Mapping) and set(artifact_arrays) == expected_keys,
        f"M{mode} array descriptors missing",
    )
    for key, array in arrays.items():
        _require(array.shape == (mode, mode), f"M{mode} {key} shape mismatch")
        _require(array.dtype == np.dtype("complex128"), f"M{mode} {key} dtype mismatch")
        _require(bool(np.isfinite(array).all()), f"M{mode} {key} is non-finite")
        _descriptor_matches(artifact_arrays[key], array, f"M{mode} {key}")

    audits: dict[str, dict[str, Any]] = {}
    for side in SIDES:
        side_meta = sides[side]
        descriptors = side_meta.get("matrix_descriptors")
        _require(
            isinstance(descriptors, Mapping) and set(descriptors) == set(MATRIX_NAMES),
            f"M{mode} {side} descriptors missing",
        )
        for name in MATRIX_NAMES:
            _descriptor_matches(
                descriptors[name], arrays[f"{side}_{name}"], f"M{mode} {side} {name}"
            )
        payload = {name: arrays[f"{side}_{name}"] for name in MATRIX_NAMES}
        payload.update(
            {
                "column_keys": capture["column_keys"],
                "degenerate_groups": capture["degenerate_groups"],
                "column_sign_order_exact": sign_order,
                "raw_artifact_exact": True,
            }
        )
        audit = audit_m960_trace(payload, evaluate_historical=False)
        _require(
            audit["pass"] is True, f"M{mode} {side} individual numerical gate failed"
        )
        recorded_audit = side_meta.get("audit")
        _require(isinstance(recorded_audit, Mapping), f"M{mode} {side} audit missing")
        _reported_scalars_match(recorded_audit, audit, mode, side)
        _require(
            side_meta.get("column_sign_order_exact") is sign_order,
            f"M{mode} {side} sign/order report mismatch",
        )
        _require(
            side_meta.get("raw_artifact_exact") is True,
            f"M{mode} {side} artifact report mismatch",
        )
        audits[side] = audit
    return {
        "record": record,
        "identity": identity,
        "capture": capture,
        "arrays": arrays,
        "audits": audits,
        "sign_order_exact": sign_order,
        "json_sha256": _sha256(path),
        "json_bytes": path.stat().st_size,
        "npz_sha256": npz_sha,
        "npz_bytes": npz_path.stat().st_size,
    }


def aggregate_trace_family(
    evidence_paths: Mapping[int, str | Path],
    *,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Recompute the four-record family gate from independent evidence files."""

    expected = set(FAMILY_MS)
    _require(set(evidence_paths) == expected, f"family requires M={FAMILY_MS}")
    loaded: dict[int, dict[str, Any]] = {}
    physical_sha: str | None = None
    for mode in FAMILY_MS:
        item = _load_capture(evidence_paths[mode], mode)
        current_physical = item["identity"]["physical_model_sha256"]
        if physical_sha is None:
            physical_sha = current_physical
        _require(
            current_physical == physical_sha,
            "physical model SHA mismatch across family",
        )
        loaded[mode] = item

    historical_by_side = {
        side: {
            str(mode): _history_entry(
                loaded[mode]["audits"][side], loaded[mode]["sign_order_exact"]
            )
            for mode in FAMILY_MS[:-1]
        }
        for side in SIDES
    }
    m960 = loaded[FAMILY_MS[-1]]
    family_audits: dict[str, dict[str, Any]] = {}
    for side in SIDES:
        payload = {name: m960["arrays"][f"{side}_{name}"] for name in MATRIX_NAMES}
        payload.update(
            {
                "column_keys": m960["capture"]["column_keys"],
                "degenerate_groups": m960["capture"]["degenerate_groups"],
                "column_sign_order_exact": m960["sign_order_exact"],
                "raw_artifact_exact": True,
                "historical_sign_order_exact": all(
                    loaded[mode]["sign_order_exact"] for mode in FAMILY_MS[:-1]
                ),
                "historical_m_modes": historical_by_side[side],
            }
        )
        family_audits[side] = audit_m960_trace(
            payload,
            evaluate_historical=True,
            historical_modes=tuple(FAMILY_MS[:-1]),
        )

    individual_pass = all(
        all(loaded[mode]["audits"][side]["pass"] for side in SIDES)
        for mode in FAMILY_MS
    )
    family_pass = bool(
        individual_pass and all(audit["pass"] for audit in family_audits.values())
    )
    result: dict[str, Any] = {
        "schema": "task039.review-v1.m960-trace-family.v1",
        "status": "pass" if family_pass else "fail",
        "classification": "M960_TRACE_AUTHORITY_NUMERICAL_AUDIT_PASS"
        if family_pass
        else "M960_TRACE_AUTHORITY_NUMERICAL_AUDIT_FAIL",
        "family_modes": list(FAMILY_MS),
        "source_commit_sha": EXPECTED_SOURCE_SHA,
        "physical_model_sha256": physical_sha,
        "individual_capture_pass": individual_pass,
        "historical_sign_order_exact": all(
            loaded[mode]["sign_order_exact"] for mode in FAMILY_MS[:-1]
        ),
        "historical_m_modes": historical_by_side,
        "records": {
            str(mode): {
                key: loaded[mode][key]
                for key in (
                    "json_sha256",
                    "json_bytes",
                    "npz_sha256",
                    "npz_bytes",
                    "identity",
                    "sign_order_exact",
                    "audits",
                )
            }
            for mode in FAMILY_MS
        },
        "family_audit": family_audits,
        "family_pass": family_pass,
    }
    if output_path is not None:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return result


__all__ = ["EXPECTED_SOURCE_SHA", "FAMILY_MS", "aggregate_trace_family"]
