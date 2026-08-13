"""Task039 research-only canonical-trace evidence writer."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Mapping

import numpy as np

from benchmarks.task039_review_v1_contracts import audit_m960_trace


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _array_descriptor(array: np.ndarray) -> dict[str, object]:
    value = np.asarray(array)
    return {
        "shape": list(value.shape),
        "dtype": str(value.dtype),
        "bytes": int(value.nbytes),
        "sha256": _sha256_bytes(np.ascontiguousarray(value).tobytes()),
        "finite": bool(np.isfinite(value).all()),
    }


def _json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"Unsupported metadata value: {type(value).__name__}")


def _column_identity_exact(
    column_keys: list,
    mode_identifiers: list,
) -> bool:
    if len(column_keys) != len(mode_identifiers):
        return False
    indices = []
    for expected_index, (key, identifier) in enumerate(
        zip(column_keys, mode_identifiers, strict=True)
    ):
        if not isinstance(key, list) or len(key) != 4:
            return False
        if key != identifier.get("key") or key[0] != expected_index:
            return False
        if identifier.get("index") != expected_index:
            return False
        if identifier.get("direction") != "backward":
            return False
        if key[1] != identifier.get("direction"):
            return False
        if key[2:] != identifier.get("beta"):
            return False
        indices.append(key[0])
    return indices == list(range(len(indices)))


def write_trace_audit_capture(
    capture: Mapping[str, object],
    output_dir: str | Path,
    *,
    metadata: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Write one hash-bound NPZ plus metadata for a captured M trace audit."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    arrays: dict[str, np.ndarray] = {}
    side_metadata: dict[str, object] = {}
    matrix_names = (
        "surface_gram",
        "raw_negative_overlap",
        "canonical_negative_overlap",
        "canonical_mapping",
        "repeat_surface_gram",
        "repeat_raw_overlap",
        "repeat_canonical_negative_overlap",
        "repeat_canonical_mapping",
    )
    column_keys = list(capture["column_keys"])
    mode_identifiers = list(capture["mode_identifiers"])
    groups = list(capture.get("degenerate_groups", []))
    column_identity_exact = _column_identity_exact(column_keys, mode_identifiers)
    side_payloads: dict[str, dict[str, np.ndarray]] = {}
    for side in ("bottom", "top"):
        side_capture = capture["sides"][side]
        payload = {
            name: np.asarray(side_capture[name], dtype=np.complex128)
            for name in matrix_names
        }
        for name, array in payload.items():
            if array.ndim != 2 or array.shape[0] != array.shape[1]:
                raise ValueError(f"{side} trace matrix {name} must be square")
            if not np.isfinite(array).all():
                raise ValueError(f"{side} trace matrix {name} is non-finite")
            arrays[f"{side}_{name}"] = array
        side_payloads[side] = payload
        side_metadata[side] = {
            "matrix_descriptors": {
                name: _array_descriptor(array) for name, array in payload.items()
            },
            "lift_queries": side_capture["lift_queries"],
            "gram_condition": side_capture["gram_condition"],
            "repeat_gram_condition": side_capture["repeat_gram_condition"],
        }

    mode_count = int(capture["mode_count"])
    npz_path = destination / f"task039_trace_evidence_m{mode_count}.npz"
    np.savez(npz_path, **arrays)
    with np.load(npz_path, allow_pickle=False) as archive:
        artifact_exact = archive.files == list(arrays)
        if artifact_exact:
            artifact_exact = all(
                archive[key].dtype == value.dtype
                and archive[key].shape == value.shape
                and np.array_equal(archive[key], value)
                for key, value in arrays.items()
            )
    historical = (metadata or {}).get("historical_m_modes", {})
    historical_by_side = historical if isinstance(historical, Mapping) else {}
    historical_complete = all(
        isinstance(historical_by_side.get(side), Mapping)
        and all(
            isinstance(
                historical_by_side[side].get(
                    str(mode), historical_by_side[side].get(mode)
                ),
                Mapping,
            )
            for mode in (120, 240, 480)
        )
        for side in ("bottom", "top")
    )
    final_family_gate_evaluated = mode_count == 960 and historical_complete
    for side in ("bottom", "top"):
        payload = side_payloads[side]
        audit_payload = {
            "raw_negative_overlap": payload["raw_negative_overlap"],
            "canonical_negative_overlap": payload["canonical_negative_overlap"],
            "surface_gram": payload["surface_gram"],
            "canonical_mapping": payload["canonical_mapping"],
            "repeat_raw_overlap": payload["repeat_raw_overlap"],
            "repeat_surface_gram": payload["repeat_surface_gram"],
            "repeat_canonical_mapping": payload["repeat_canonical_mapping"],
            "repeat_canonical_negative_overlap": payload[
                "repeat_canonical_negative_overlap"
            ],
            "column_keys": column_keys,
            "degenerate_groups": groups,
            "column_sign_order_exact": column_identity_exact,
            "raw_artifact_exact": artifact_exact,
            "historical_sign_order_exact": bool(
                (metadata or {}).get("historical_sign_order_exact", False)
            ),
            "historical_m_modes": historical_by_side.get(side, {}),
        }
        side_metadata[side].update(
            {
                "column_sign_order_exact": column_identity_exact,
                "raw_artifact_exact": artifact_exact,
                "audit": audit_m960_trace(audit_payload),
                "final_family_gate_evaluated": final_family_gate_evaluated,
            }
        )
    artifact = {
        "path": npz_path.name,
        "bytes": npz_path.stat().st_size,
        "sha256": _sha256_bytes(npz_path.read_bytes()),
        "keys": list(arrays),
        "arrays": {key: _array_descriptor(value) for key, value in arrays.items()},
    }
    record = {
        "schema": "task039.review-v1.m960-trace-evidence.v1",
        "status": "controlled_stop_ready",
        "individual_capture_complete": bool(
            column_identity_exact
            and artifact_exact
            and set(side_payloads) == {"bottom", "top"}
        ),
        "final_family_gate_evaluated": final_family_gate_evaluated,
        "family_gate_note": (
            "Current-M individual capture and both-side historical M=120/240/480 "
            "evidence are complete; final family gate was evaluated."
            if final_family_gate_evaluated
            else "Current-M individual capture is complete; historical M=120/240/480 "
            "family evidence is required before final_family_gate_evaluated=true."
        ),
        "capture": {
            "mode_count": mode_count,
            "column_keys": column_keys,
            "mode_identifiers": capture["mode_identifiers"],
            "degenerate_groups": groups,
            "sides": side_metadata,
        },
        "metadata": dict(metadata or {}),
        "artifact": artifact,
    }
    metadata_path = destination / f"task039_trace_evidence_m{mode_count}.json"
    metadata_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )
    return {
        "schema": record["schema"],
        "status": record["status"],
        "individual_capture_complete": record["individual_capture_complete"],
        "final_family_gate_evaluated": final_family_gate_evaluated,
        "npz_path": str(npz_path),
        "metadata_path": str(metadata_path),
        "npz_sha256": artifact["sha256"],
        "metadata_sha256": _sha256_bytes(metadata_path.read_bytes()),
        "metadata_bytes": metadata_path.stat().st_size,
        "sides": side_metadata,
    }


__all__ = ["main", "write_trace_audit_capture"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one explicit Task039 canonical-trace capture lane."
    )
    parser.add_argument("input_path", type=Path)
    parser.add_argument("--source-sha")
    args = parser.parse_args(argv)
    from src.io import load_and_resolve
    from src.runners.task038_launcher import launch_specification

    specification = load_and_resolve(args.input_path)
    result = launch_specification(
        specification,
        source_sha=args.source_sha,
        task039_trace_audit=True,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=_json_default))
    return (
        0
        if result["result_classification"] == ("task039_trace_capture_complete")
        else 3
    )


if __name__ == "__main__":
    raise SystemExit(main())
