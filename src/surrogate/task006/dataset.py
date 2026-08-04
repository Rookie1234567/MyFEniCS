"""Build and load the immutable Task006 train37 compact dataset."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from .design import (
    ANGLES,
    FORWARD_SOLVER_SHA,
    MODEL_ID,
    OBSERVABLE_SCHEMA,
    ROUTE_ID,
    TASK006_DATASET_ID,
    TRAIN_GEOMETRIES,
    canonical_hash,
)


# All 111 measured records have strictly positive R/T/A.  A tiny nonzero
# floor keeps the transform defined while keeping softmax round-trip error
# below the 1e-12 composition identity gate.
EPSILON = 1.0e-15
DATASET_ROOT = Path("benchmarks/artifacts/cases/137_task006_train37_dataset/train37")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_source(path: Path, line_match: list[float] | None) -> dict[str, Any]:
    if line_match is None:
        return json.loads(path.read_text())
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    matches = [row for row in rows if row.get("inputs") == line_match]
    if len(matches) != 1:
        raise ValueError(f"exact JSONL source row not unique for {line_match}: {path}")
    return matches[0]


def _order_key(order: dict[str, Any]) -> tuple[str, int, int]:
    return str(order.get("side")), int(order.get("m")), int(order.get("n"))


def _expected_channel(sample: dict[str, Any], side: str) -> dict[str, Any]:
    matches = [
        order for order in sample.get("mother_response", {}).get("orders", [])
        if order.get("side") == side and int(order.get("m")) == 0 and int(order.get("n")) == 0
    ]
    if len(matches) != 1:
        raise ValueError(f"frozen m=0 channel not unique for {side}")
    order = matches[0]
    if order.get("power_carrying") is not True:
        raise ValueError(f"frozen m=0 channel is not power carrying for {side}")
    power = order.get("order_total_power")
    if power is None or not np.isfinite(float(power)) or float(power) < 0.0:
        raise ValueError(f"frozen m=0 power is null/nonfinite for {side}")
    return order


def _validate_sample(sample: dict[str, Any], h: float, w: float, angle_id: str,
                     grazing: float, azimuth: float) -> None:
    if sample.get("inputs") != [h, w, grazing, azimuth]:
        raise ValueError(f"input mismatch for {h},{w}/{angle_id}")
    if sample.get("status") != "measured_pass":
        raise ValueError(f"source status is not measured_pass for {h},{w}/{angle_id}")
    if sample.get("source_sha") != FORWARD_SOLVER_SHA or sample.get("source_dirty") is not False:
        raise ValueError(f"source identity mismatch for {h},{w}/{angle_id}")
    if sample.get("model_id") != MODEL_ID or sample.get("solver_route_id") != ROUTE_ID:
        raise ValueError(f"model/route mismatch for {h},{w}/{angle_id}")
    if sample.get("observable_schema_version") != OBSERVABLE_SCHEMA:
        raise ValueError(f"observable mismatch for {h},{w}/{angle_id}")
    aggregates = sample.get("aggregates", {})
    r, t, a = (aggregates.get("R_total"), aggregates.get("T_total"), aggregates.get("A_balance"))
    if any(value is None or not np.isfinite(float(value)) for value in (r, t, a)):
        raise ValueError(f"nonfinite aggregate for {h},{w}/{angle_id}")
    if min(float(r), float(t), float(a)) < -1.0e-10:
        raise ValueError(f"negative aggregate for {h},{w}/{angle_id}")
    if abs(float(a) - (1.0 - float(r) - float(t))) > 1.0e-7:
        raise ValueError(f"aggregate balance closure failed for {h},{w}/{angle_id}")
    for side in ("reflection", "transmission"):
        order = _expected_channel(sample, side)
        side_total = float(r if side == "reflection" else t)
        selected = float(order["order_total_power"])
        if selected > side_total + 1.0e-7:
            raise ValueError(f"selected {side} channel exceeds side total for {h},{w}/{angle_id}")


def _canonical_file_hashes(root: Path) -> dict[str, str]:
    return {path.name: _sha(path) for path in sorted(root.iterdir())
            if path.is_file() and path.name not in {"file_hashes.json", "dataset_manifest.json"}}


def build_dataset(*, manifest_path: Path, output_root: Path = DATASET_ROOT) -> dict[str, Any]:
    """Build arrays from the completed M1 campaign and explicit reuse paths."""

    campaign = json.loads(manifest_path.read_text())
    if campaign.get("status") != "pass" or int(campaign.get("new_fem_count", 0)) != 79:
        raise RuntimeError("M1 campaign must pass with exactly 79 new FEM before dataset build")
    records = campaign.get("records", {})
    output_root.mkdir(parents=True, exist_ok=True)
    geometries = np.asarray([[h, w] for h, w in TRAIN_GEOMETRIES], dtype=np.float64)
    angles = np.asarray([[g, a] for _, g, a in ANGLES], dtype=np.float64)
    inputs = np.zeros((len(TRAIN_GEOMETRIES), len(ANGLES), 4), dtype=np.float64)
    aggregates = np.zeros((len(TRAIN_GEOMETRIES), len(ANGLES), 4), dtype=np.float64)
    aggregate_latent = np.zeros((len(TRAIN_GEOMETRIES), len(ANGLES), 2), dtype=np.float64)
    selected = np.zeros((len(TRAIN_GEOMETRIES), len(ANGLES), 2), dtype=np.float64)
    side_totals = np.zeros_like(selected)
    other = np.zeros_like(selected)
    fractions = np.zeros((len(TRAIN_GEOMETRIES), len(ANGLES), 2, 2), dtype=np.float64)
    selected_masks = np.ones(selected.shape, dtype=bool)
    sample_ids = np.empty((len(TRAIN_GEOMETRIES), len(ANGLES)), dtype=object)
    formal_hashes = np.empty_like(sample_ids)
    execution_hashes = np.empty_like(sample_ids)
    provenance: list[dict[str, Any]] = []
    order_axis: list[tuple[str, int, int]] | None = None
    order_powers_rows: list[np.ndarray] = []
    order_masks_rows: list[np.ndarray] = []
    volume_absorption = np.zeros((len(TRAIN_GEOMETRIES), len(ANGLES)), dtype=np.float64)

    for gi, (h, w) in enumerate(TRAIN_GEOMETRIES):
        for ai, (angle_id, grazing, azimuth) in enumerate(ANGLES):
            key = f"{h:g},{w:g}/{angle_id}"
            row = records.get(key)
            if row is None:
                raise ValueError(f"M1 manifest missing {key}")
            source_path = Path(row.get("sample_path") or row.get("source_path", ""))
            if not source_path.is_file():
                raise FileNotFoundError(f"sample path missing for {key}: {source_path}")
            sample = _load_source(source_path, row.get("line_match") if row.get("reuse") else None)
            _validate_sample(sample, h, w, angle_id, grazing, azimuth)
            inputs[gi, ai] = [h, w, grazing, azimuth]
            agg = sample["aggregates"]
            r, t, a = float(agg["R_total"]), float(agg["T_total"]), float(agg["A_balance"])
            aggregates[gi, ai] = [r, t, a, float(agg.get("A_volume", a))]
            aggregate_latent[gi, ai] = [
                np.log((r + EPSILON) / (a + EPSILON)),
                np.log((t + EPSILON) / (a + EPSILON)),
            ]
            refl = _expected_channel(sample, "reflection")
            tran = _expected_channel(sample, "transmission")
            selected[gi, ai] = [float(refl["order_total_power"]), float(tran["order_total_power"])]
            side_totals[gi, ai] = [r, t]
            other[gi, ai] = np.maximum(side_totals[gi, ai] - selected[gi, ai], 0.0)
            fractions[gi, ai, :, 0] = selected[gi, ai] / np.maximum(side_totals[gi, ai], EPSILON)
            fractions[gi, ai, :, 1] = other[gi, ai] / np.maximum(side_totals[gi, ai], EPSILON)
            if np.max(np.abs(np.sum(fractions[gi, ai], axis=1) - 1.0)) > 1.0e-12:
                raise ValueError(f"S1 side composition does not close for {key}")
            volume_absorption[gi, ai] = float(agg.get("A_volume", a))
            sample_ids[gi, ai] = str(sample.get("sample_id", ""))
            formal_hashes[gi, ai] = str(sample.get("formal_record_sha256", ""))
            execution_hashes[gi, ai] = str(sample.get("execution_sha256", ""))
            current_axis = [_order_key(order) for order in sample["mother_response"]["orders"]]
            if order_axis is None:
                order_axis = current_axis
            elif current_axis != order_axis:
                raise ValueError(f"order identity changed at {key}")
            powers = np.asarray([
                float(order["order_total_power"]) if order.get("power_carrying") and order.get("order_total_power") is not None else np.nan
                for order in sample["mother_response"]["orders"]
            ], dtype=np.float64)
            masks = np.isfinite(powers)
            order_powers_rows.append(powers)
            order_masks_rows.append(masks)
            provenance.append({
                "geometry_index": gi, "angle_index": ai, "geometry": [h, w], "key": key,
                "reuse": bool(row.get("reuse")), "source_kind": row.get("source_kind"),
                "sample_path": str(source_path), "line_match": row.get("line_match"),
                "sample_id": sample_ids[gi, ai],
                "formal_record_sha256": formal_hashes[gi, ai],
                "execution_sha256": execution_hashes[gi, ai],
                "source_sha": sample.get("source_sha"), "config_hash": sample.get("config_hash"),
                "observable_schema_version": sample.get("observable_schema_version"),
            })

    if order_axis is None:
        raise ValueError("no records loaded")
    order_powers = np.asarray(order_powers_rows, dtype=np.float64).reshape(len(TRAIN_GEOMETRIES), len(ANGLES), -1)
    order_masks = np.asarray(order_masks_rows, dtype=bool).reshape(len(TRAIN_GEOMETRIES), len(ANGLES), -1)
    arrays: dict[str, np.ndarray] = {
        "geometries.npy": geometries,
        "angle_contract.npy": angles,
        "inputs_by_angle.npy": inputs,
        "aggregates.npy": aggregates,
        "aggregate_latent.npy": aggregate_latent,
        "s1_selected_powers.npy": selected,
        "s1_side_totals.npy": side_totals,
        "s1_other_powers.npy": other,
        "s1_fractions.npy": fractions,
        "s1_selected_mask.npy": selected_masks,
        "order_powers.npy": order_powers,
        "order_mask.npy": order_masks,
        "volume_absorption.npy": volume_absorption,
        "sample_ids.npy": sample_ids,
        "formal_record_hashes.npy": formal_hashes,
        "execution_hashes.npy": execution_hashes,
    }
    for name, value in arrays.items():
        np.save(output_root / name, value, allow_pickle=name.endswith(".npy") and value.dtype == object)
    (output_root / "angle_ids.json").write_text(json.dumps([aid for aid, _, _ in ANGLES], indent=2) + "\n")
    (output_root / "order_identity.json").write_text(json.dumps({"axis": [
        {"side": side, "m": m, "n": n} for side, m, n in order_axis
    ]}, indent=2) + "\n")
    (output_root / "provenance.json").write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n")
    manifest = {
        "schema_version": "task006.fixed-hw-train37-compact.v1",
        "dataset_id": TASK006_DATASET_ID, "status": "immutable",
        "forward_solver_sha": FORWARD_SOLVER_SHA, "model_id": MODEL_ID,
        "solver_route_id": ROUTE_ID, "observable_schema_version": OBSERVABLE_SCHEMA,
        "geometry_count": 37, "angle_count": 3, "record_count": 111,
        "training_tuple_sha256": canonical_hash(geometries.tolist()),
        "angle_tuple_sha256": canonical_hash(angles.tolist()),
        "training_geometry_hash": canonical_hash(geometries.tolist()),
        "source_sha_set": [FORWARD_SOLVER_SHA], "source_dirty": False,
        "reuse_record_count": int(sum(bool(item["reuse"]) for item in provenance)),
        "new_fem_record_count": int(sum(not bool(item["reuse"]) for item in provenance)),
        "new_fem_count": 79, "blind_response_accessed": False,
        "validation_target_accessed": False, "formal_inversion": False,
        "s0_schema": {"targets": ["R_total", "T_total", "A_balance"], "latent": "aggregate_latent"},
        "s1_schema": {"selected_channels": [["reflection", 0, 0], ["transmission", 0, 0]], "fractions": ["selected", "other"], "ledger_exact": True},
        "order_axis_count": len(order_axis),
        "array_shapes": {name: list(value.shape) for name, value in arrays.items()},
    }
    (output_root / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    hashes = _canonical_file_hashes(output_root)
    (output_root / "file_hashes.json").write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n")
    manifest["file_hashes"] = hashes
    (output_root / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest


def load_dataset(root: Path = DATASET_ROOT) -> dict[str, Any]:
    manifest = json.loads((root / "dataset_manifest.json").read_text())
    if manifest.get("status") != "immutable":
        raise ValueError("Task006 dataset is not immutable")
    arrays = {name[:-4]: np.load(root / name, allow_pickle=name in ("sample_ids.npy", "formal_record_hashes.npy", "execution_hashes.npy"))
              for name in manifest["array_shapes"]}
    arrays["manifest"] = manifest
    return arrays
