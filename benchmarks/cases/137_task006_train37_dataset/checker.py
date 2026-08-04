"""Independent exact-design checker for the immutable Task006 train37 data."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


FORWARD_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"
OBSERVABLE = "task002.fixed-n0-orders.v3"
DATASET_ID = "task006_fixed_A05_A07_A09_hw_train37_p5_ny4_v1"
ANGLES = (("A05", 2.0, 0.0), ("A07", 2.0, 90.0), ("A09", 4.0, 60.0))
H = (115.0, 117.5, 118.75, 120.0, 121.25, 122.5, 125.0)
W = (16.0, 16.5, 16.75, 17.0, 17.25, 17.5, 18.0)
BLIND = {
    (117.5, 16.5), (117.5, 16.75), (117.5, 17.25), (117.5, 17.5),
    (118.75, 16.5), (118.75, 17.5), (121.25, 16.5), (121.25, 17.5),
    (122.5, 16.5), (122.5, 16.75), (122.5, 17.25), (122.5, 17.5),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def expected_train() -> list[list[float]]:
    rows = [[h, w] for h in H for w in W if h in (115.0, 125.0) or w in (16.0, 18.0)]
    rows += [[120.0, 17.0], [118.75, 17.0], [121.25, 17.0], [120.0, 16.75], [120.0, 17.25], [118.75, 16.75], [118.75, 17.25], [121.25, 17.25]]
    rows += [[117.5, 17.0], [122.5, 17.0], [120.0, 16.5], [120.0, 17.5], [121.25, 16.75]]
    result: list[list[float]] = []
    for row in rows:
        if row not in result:
            result.append(row)
    return result


def _load_source(path: Path, line_match: list[float] | None) -> dict[str, Any]:
    if line_match is None:
        return json.loads(path.read_text())
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    matches = [row for row in rows if row.get("inputs") == line_match]
    if len(matches) != 1:
        raise ValueError(f"source row not unique: {path} {line_match}")
    return matches[0]


def check(root: Path) -> tuple[dict[str, bool], list[str]]:
    dataset = root / "benchmarks/artifacts/cases/137_task006_train37_dataset/train37"
    outcomes = root / "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes"
    checks: dict[str, bool] = {}
    errors: list[str] = []
    try:
        manifest = json.loads((dataset / "dataset_manifest.json").read_text())
        stored_hashes = json.loads((dataset / "file_hashes.json").read_text())
        geometries = np.load(dataset / "geometries.npy")
        angles = np.load(dataset / "angle_contract.npy")
        inputs = np.load(dataset / "inputs_by_angle.npy")
        aggregates = np.load(dataset / "aggregates.npy")
        latent = np.load(dataset / "aggregate_latent.npy")
        selected = np.load(dataset / "s1_selected_powers.npy")
        side_totals = np.load(dataset / "s1_side_totals.npy")
        other = np.load(dataset / "s1_other_powers.npy")
        fractions = np.load(dataset / "s1_fractions.npy")
        selected_mask = np.load(dataset / "s1_selected_mask.npy")
        order_powers = np.load(dataset / "order_powers.npy")
        order_mask = np.load(dataset / "order_mask.npy")
        sample_ids = np.load(dataset / "sample_ids.npy", allow_pickle=True)
        formal_hashes = np.load(dataset / "formal_record_hashes.npy", allow_pickle=True)
        execution_hashes = np.load(dataset / "execution_hashes.npy", allow_pickle=True)
        provenance = json.loads((dataset / "provenance.json").read_text())
        order_identity = json.loads((dataset / "order_identity.json").read_text())
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"required_dataset_files": False}, [f"read failed: {exc}"]

    checks["required_dataset_files"] = True
    checks["manifest_identity"] = bool(
        manifest.get("status") == "immutable" and manifest.get("dataset_id") == DATASET_ID
        and manifest.get("forward_solver_sha") == FORWARD_SHA and manifest.get("model_id") == MODEL_ID
        and manifest.get("solver_route_id") == ROUTE_ID and manifest.get("observable_schema_version") == OBSERVABLE
        and manifest.get("geometry_count") == 37 and manifest.get("angle_count") == 3
        and manifest.get("record_count") == 111 and manifest.get("reuse_record_count") == 32
        and manifest.get("new_fem_record_count") == 79 and manifest.get("blind_response_accessed") is False
        and manifest.get("validation_target_accessed") is False
    )
    expected = np.asarray(expected_train(), dtype=np.float64)
    expected_angles = np.asarray([[g, a] for _, g, a in ANGLES], dtype=np.float64)
    checks["exact_geometry_and_angle_arrays"] = bool(
        geometries.shape == (37, 2) and np.array_equal(geometries, expected)
        and manifest.get("training_tuple_sha256") == canonical(expected.tolist())
        and angles.shape == (3, 2) and np.array_equal(angles, expected_angles)
        and manifest.get("angle_tuple_sha256") == canonical(expected_angles.tolist())
    )
    checks["array_shapes"] = bool(
        inputs.shape == (37, 3, 4) and aggregates.shape == (37, 3, 4)
        and latent.shape == (37, 3, 2) and selected.shape == (37, 3, 2)
        and side_totals.shape == selected.shape and other.shape == selected.shape
        and fractions.shape == (37, 3, 2, 2) and selected_mask.shape == selected.shape
        and order_powers.shape[:2] == (37, 3) and order_mask.shape == order_powers.shape
        and sample_ids.shape == (37, 3) and formal_hashes.shape == (37, 3)
        and execution_hashes.shape == (37, 3)
    )
    logits = np.concatenate([latent, np.zeros((37, 3, 1))], axis=2)
    logits -= np.max(logits, axis=2, keepdims=True)
    weights = np.exp(logits); weights /= np.sum(weights, axis=2, keepdims=True)
    reconstructed = weights
    checks["s0_composition_contract"] = bool(
        np.all(np.isfinite(latent)) and np.all(reconstructed >= 0.0)
        and np.max(np.abs(np.sum(reconstructed, axis=2) - 1.0)) <= 1.0e-12
        and np.max(np.abs(reconstructed - aggregates[:, :, :3])) <= 1.0e-12
    )
    checks["s1_sidewise_ledger_contract"] = bool(
        np.all(selected_mask) and np.all(np.isfinite(selected)) and np.all(np.isfinite(other))
        and np.all(selected >= 0.0) and np.all(other >= 0.0)
        and np.max(np.abs(selected + other - side_totals)) <= 1.0e-12
        and np.max(np.abs(np.sum(fractions, axis=3) - 1.0)) <= 1.0e-12
        and np.max(np.abs(fractions - np.divide(np.stack([selected, other], axis=3), side_totals[:, :, :, None], out=np.zeros((37,3,2,2)), where=side_totals[:, :, :, None] > 0))) <= 1.0e-12
    )
    expected_axis = [{"side": side, "m": m, "n": 0} for side in ("reflection", "transmission") for m in range(-7, 4)]
    checks["order_identity_and_null_semantics"] = bool(
        order_identity.get("axis") == expected_axis and order_powers.shape == (37, 3, 22)
        and np.all(np.isfinite(order_powers[order_mask]))
        and np.all(np.isnan(order_powers[~order_mask]))
    )
    checks["inputs_match_geometry_angles"] = bool(
        np.all(inputs[:, :, :2] == geometries[:, None, :])
        and np.all(inputs[:, :, 2:] == angles[None, :, :])
    )
    checks["unique_sample_and_hash_identity"] = bool(
        len(set(str(x) for x in sample_ids.ravel())) == 111
        and np.all(np.asarray(formal_hashes, dtype=str) != "")
        and np.all(np.asarray(execution_hashes, dtype=str) != "")
    )
    actual_hashes = {path.name: sha(path) for path in sorted(dataset.iterdir())
                     if path.is_file() and path.name not in {"file_hashes.json", "dataset_manifest.json"}}
    checks["array_file_hashes"] = actual_hashes == stored_hashes
    provenance_ok = len(provenance) == 111
    for item in provenance:
        if tuple(item.get("geometry", [])) in BLIND:
            provenance_ok = False; errors.append(f"blind geometry present in provenance: {item.get('key')}")
        path = Path(item.get("sample_path", ""))
        if not path.is_file():
            provenance_ok = False; errors.append(f"missing source: {path}"); continue
        try:
            sample = _load_source(path, item.get("line_match"))
            inputs_row = sample.get("inputs")
            if sample.get("source_sha") != FORWARD_SHA or sample.get("source_dirty") is not False:
                provenance_ok = False
            if sample.get("model_id") != MODEL_ID or sample.get("solver_route_id") != ROUTE_ID or sample.get("observable_schema_version") != OBSERVABLE:
                provenance_ok = False
            if inputs_row is None:
                provenance_ok = False
        except (OSError, ValueError, json.JSONDecodeError):
            provenance_ok = False
    checks["provenance_exact_and_no_blind"] = provenance_ok
    checks["training_design_bound"] = bool(
        json.loads((outcomes / "HW_TRAIN37_DESIGN.json").read_text()).get("tuple_sha256") == manifest.get("training_tuple_sha256")
        and json.loads((outcomes / "HW_BLIND12_DESIGN.json").read_text()).get("responses_accessed") is False
    )
    if not all(checks.values()):
        errors.extend(f"failed:{name}" for name, value in checks.items() if not value)
    return checks, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "records/case137_check.json")
    args = parser.parse_args()
    checks, errors = check(args.root.resolve())
    result = {"schema_version": "task006.case137-dataset-check.v1", "status": "pass" if all(checks.values()) else "failed", "checks": checks, "errors": errors, "blind_response_accessed": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
