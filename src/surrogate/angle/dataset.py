"""Task004 angle compact dataset assembly and train/validation guards."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from src.forward_data.task002_m4 import formal_record_to_production_sample
from src.forward_data.provenance import file_hash


MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"
PARAMETER_SCHEMA = "task002.s-p5-ny4-production-parameters.v3"
OBSERVABLE_SCHEMA = "task002.fixed-n0-orders.v3"
DATASET_SCHEMA = "task004.angle-p5-ny4-dataset.v1"


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()


def tuple_from_point(point: dict[str, Any]) -> list[float]:
    return [float(point[key]) for key in ("height_nm", "width_x_nm", "grazing_deg", "azimuth_deg")]


def _records_from_manifest(manifest_path: Path, design_id: str, count: int) -> list[dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text())
    rows = []
    for index in range(count):
        key = f"{design_id}:{index:04d}"
        row = manifest["samples"].get(key)
        if row is None or row.get("status") != "measured_pass":
            raise RuntimeError(f"Task004 sample is not measured_pass: {key}")
        run_directory = Path(row["run_directory"])
        formal = run_directory / "results/task002_full3d_record.json"
        execution = run_directory / "execution.json"
        if not formal.is_file() or not execution.is_file():
            raise RuntimeError(f"missing formal Task004 record: {key}")
        rows.append(formal_record_to_production_sample(
            manifest_row=row, formal_record_path=formal, execution_path=execution,
        ))
    return rows


def _arrays(records: list[dict[str, Any]]) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    inputs = np.asarray([row["inputs"] for row in records], dtype=np.float64)
    if np.any(inputs[:, :2] != np.asarray([120.0, 17.0])):
        raise ValueError("Task004 dataset contains non-nominal geometry")
    aggregates = np.asarray([[row["aggregates"][name] for name in
                              ("R_total", "T_total", "A_balance", "A_volume")]
                             for row in records], dtype=np.float64)
    amplitudes = np.full((len(records), 22, 2, 2), np.nan, dtype=np.float64)
    powers = np.full((len(records), 22, 2), np.nan, dtype=np.float64)
    mask = np.zeros((len(records), 22, 2), dtype=bool)
    order_identity = None
    for ri, row in enumerate(records):
        orders = row["mother_response"]["orders"]
        identity = [(item["side"], int(item["m"]), int(item["n"])) for item in orders]
        if order_identity is None:
            order_identity = identity
        elif identity != order_identity:
            raise ValueError("Task004 order identity changed across samples")
        for oi, order in enumerate(orders):
            for ci, component in enumerate(("s", "p")):
                value = order["components"][component]
                if not value.get("power_carrying", False):
                    continue
                mask[ri, oi, ci] = True
                amplitudes[ri, oi, ci, 0] = float(value["amplitude_re"])
                amplitudes[ri, oi, ci, 1] = float(value["amplitude_im"])
                powers[ri, oi, ci] = float(value["power"])
    if order_identity is None:
        raise ValueError("empty Task004 record list")
    return {
        "angles.npy": inputs[:, 2:].copy(), "inputs.npy": inputs,
        "aggregates.npy": aggregates, "order_amplitudes.npy": amplitudes,
        "order_powers.npy": powers, "power_carrying_mask.npy": mask,
        "sample_ids.npy": np.asarray([row["sample_id"] for row in records], dtype="U64"),
    }, {"axis": [{"side": side, "m": m, "n": n} for side, m, n in order_identity]}


def build_dataset(*, artifact_root: Path, campaign_manifest: Path,
                  include_validation: bool,
                  training_design_ids: tuple[str, ...] = ("task004_angle_training_v1",),
                  training_counts: tuple[int, ...] = (96,)) -> dict[str, Any]:
    if len(training_design_ids) != len(training_counts):
        raise ValueError("training design/count lists must have equal length")
    training: list[dict[str, Any]] = []
    for design_id, count in zip(training_design_ids, training_counts):
        training.extend(_records_from_manifest(campaign_manifest, design_id, count))
    validation = []
    if include_validation:
        # This is the only function that may read Task004 blind-validation
        # responses, and it must be called only after the model lock exists.
        validation = _records_from_manifest(
            campaign_manifest, "task004_angle_frozen_validation_v1", 24,
        )
    records = training + validation
    arrays, order_identity = _arrays(records)
    dataset_dir = artifact_root / "compact_dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    for name, array in arrays.items():
        np.save(dataset_dir / name, array, allow_pickle=False)
    training_count = len(training)
    np.save(dataset_dir / "train_indices.npy", np.arange(training_count, dtype=np.int64))
    np.save(dataset_dir / "sealed_validation_indices.npy",
            np.arange(training_count, training_count + len(validation), dtype=np.int64)
            if include_validation else np.arange(0, dtype=np.int64))
    (dataset_dir / "fixed_parameters.json").write_text(json.dumps({
        "height_nm": 120.0, "width_x_nm": 17.0, "wavelength_nm": 13.5,
        "incident_polarization": "S", "model_id": MODEL_ID,
        "solver_route_id": ROUTE_ID, "parameter_schema_version": PARAMETER_SCHEMA,
        "observable_schema_version": OBSERVABLE_SCHEMA,
    }, indent=2) + "\n")
    (dataset_dir / "order_identity.json").write_text(json.dumps(order_identity, indent=2) + "\n")
    (dataset_dir / "sample_records.jsonl").write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in records)
    )
    tuples = [row["inputs"] for row in records]
    manifest = {
        "schema_version": DATASET_SCHEMA,
        "dataset_id": "task004_angle_nominal_p5_ny4_96_plus24_v1",
        "source_sha": records[0]["source_sha"], "source_dirty": False,
        "parameter_schema_version": PARAMETER_SCHEMA,
        "observable_schema_version": OBSERVABLE_SCHEMA,
        "model_id": MODEL_ID, "solver_route_id": ROUTE_ID,
        "fixed_geometry": {"height_nm": 120.0, "width_nm": 17.0},
        "sample_count": len(records), "training_count": training_count,
        "blind_validation_count": len(validation),
        "train_tuple_sha256": canonical_hash(tuples[:training_count]),
        "blind_validation_tuple_sha256": canonical_hash(tuples[training_count:]) if validation else None,
        "sample_ids_hash": canonical_hash([row["sample_id"] for row in records]),
        "validation_target_accessed": bool(include_validation),
        "arrays": {},
    }
    for path in dataset_dir.iterdir():
        if path.is_file() and path.name not in {"dataset_manifest.json", "file_hashes.json"}:
            if path.suffix == ".npy":
                value = np.load(path, mmap_mode="r", allow_pickle=False)
                manifest["arrays"][path.name] = {"shape": list(value.shape), "dtype": str(value.dtype)}
    (dataset_dir / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    hashes = {path.name: file_hash(path) for path in dataset_dir.iterdir()
              if path.is_file() and path.name != "file_hashes.json"}
    (dataset_dir / "file_hashes.json").write_text(json.dumps(hashes, indent=2) + "\n")
    return manifest


def load_training_dataset(dataset_dir: Path) -> dict[str, np.ndarray]:
    """Load only the 96 angle rows; never open sealed validation indices/targets."""

    manifest = json.loads((dataset_dir / "dataset_manifest.json").read_text())
    expected_count = int(manifest.get("training_count", -1))
    if expected_count not in (96, 112):
        raise ValueError("Task004 training count must be 96 or 112")
    indices = np.load(dataset_dir / "train_indices.npy", allow_pickle=False)
    if indices.shape != (expected_count,):
        raise ValueError("Task004 train index identity mismatch")
    names = ("angles.npy", "inputs.npy", "aggregates.npy", "order_amplitudes.npy",
             "order_powers.npy", "power_carrying_mask.npy")
    arrays = {name: np.load(dataset_dir / name, mmap_mode="r", allow_pickle=False)[indices].copy()
              for name in names}
    return arrays


def load_sealed_validation(dataset_dir: Path) -> dict[str, np.ndarray]:
    """Explicit one-time validation load, called only after model lock."""

    indices = np.load(dataset_dir / "sealed_validation_indices.npy", allow_pickle=False)
    if indices.shape != (24,):
        raise ValueError("Task004 sealed validation is not a 24-row split")
    names = ("angles.npy", "inputs.npy", "aggregates.npy", "order_amplitudes.npy",
             "order_powers.npy", "power_carrying_mask.npy")
    return {name: np.load(dataset_dir / name, allow_pickle=False)[indices].copy()
            for name in names}
