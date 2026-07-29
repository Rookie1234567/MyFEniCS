"""Canonical portable Task002 dataset writer and independent verifier."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from .orders import FIXED_M_ORDERS
from .provenance import canonical_hash, file_hash
from .task002_schema import (
    TASK002_DATASET_SCHEMA_VERSION,
    TASK002_OBSERVABLE_SCHEMA_VERSION,
    TASK002_PARAMETER_SCHEMA_VERSION,
)


ARRAY_FILES = (
    "inputs.npy", "aggregates.npy", "order_amplitudes.npy", "order_powers.npy",
    "power_carrying_mask.npy", "train_hf_indices.npy", "train_lf_indices.npy",
    "frozen_validation_indices.npy",
)


def _json_dump(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _source_identity(samples: list[Mapping[str, Any]]) -> str:
    identities = {
        (sample.get("source_sha"), sample.get("source_dirty")) for sample in samples
    }
    if len(identities) != 1:
        raise ValueError("Task002 dataset samples mix source identities")
    source_sha, dirty = identities.pop()
    if dirty is not False or not isinstance(source_sha, str) or len(source_sha) != 40:
        raise ValueError("Task002 dataset requires one clean full source SHA")
    return source_sha


def _validate_orders(sample: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    response = sample.get("mother_response", {})
    if response.get("schema_version") != TASK002_OBSERVABLE_SCHEMA_VERSION:
        raise ValueError("Task002 mother-response schema mismatch")
    orders = list(response.get("orders", []))
    expected = [
        (side, m, 0) for side in ("reflection", "transmission") for m in FIXED_M_ORDERS
    ]
    actual = [(row.get("side"), row.get("m"), row.get("n")) for row in orders]
    if actual != expected:
        raise ValueError("Task002 mother-response order identity mismatch")
    return orders


def write_compact_dataset(
    samples: Iterable[Mapping[str, Any]], *, output_dir: Path, dataset_id: str,
) -> dict[str, Any]:
    records = [dict(sample) for sample in samples]
    if not records:
        raise ValueError("Task002 dataset requires at least one sample")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("Task002 dataset output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    source_sha = _source_identity(records)
    sample_ids = [str(record.get("sample_id")) for record in records]
    if len(set(sample_ids)) != len(sample_ids) or any(value in {"", "None"} for value in sample_ids):
        raise ValueError("Task002 sample_id values must be unique and nonempty")
    if any(record.get("status") != "measured_pass" for record in records):
        raise ValueError("only measured_pass samples enter the compact training dataset")

    n_orders = 2 * len(FIXED_M_ORDERS)
    inputs = np.empty((len(records), 4), dtype=np.float64)
    aggregates = np.empty((len(records), 4), dtype=np.float64)
    amplitudes = np.full((len(records), n_orders, 2, 2), np.nan, dtype=np.float64)
    powers = np.full((len(records), n_orders, 2), np.nan, dtype=np.float64)
    mask = np.zeros((len(records), n_orders, 2), dtype=np.bool_)
    split_indices = {"train_lf": [], "train_hf": [], "frozen_validation": []}

    for index, record in enumerate(records):
        inputs[index] = np.asarray(record["inputs"], dtype=np.float64)
        aggregates[index] = [
            float(record["aggregates"][name])
            for name in ("R_total", "T_total", "A_balance", "A_volume")
        ]
        for order_index, order in enumerate(_validate_orders(record)):
            for component_index, component_name in enumerate(("s", "p")):
                component = order["components"][component_name]
                real = component.get("amplitude_re")
                imag = component.get("amplitude_im")
                power = component.get("power")
                carrying = bool(component.get("power_carrying"))
                if carrying and power is None:
                    raise ValueError("power-carrying component is missing power")
                if not carrying and power is not None:
                    raise ValueError("structural null power must be null")
                if real is not None and imag is not None:
                    amplitudes[index, order_index, component_index] = [real, imag]
                if power is not None:
                    powers[index, order_index, component_index] = float(power)
                mask[index, order_index, component_index] = carrying
        split = str(record.get("split"))
        if split not in split_indices:
            raise ValueError(f"unsupported Task002 split: {split}")
        split_indices[split].append(index)

    arrays = {
        "inputs.npy": inputs,
        "aggregates.npy": aggregates,
        "order_amplitudes.npy": amplitudes,
        "order_powers.npy": powers,
        "power_carrying_mask.npy": mask,
        "train_hf_indices.npy": np.asarray(split_indices["train_hf"], dtype=np.int64),
        "train_lf_indices.npy": np.asarray(split_indices["train_lf"], dtype=np.int64),
        "frozen_validation_indices.npy": np.asarray(
            split_indices["frozen_validation"], dtype=np.int64
        ),
    }
    for name, array in arrays.items():
        np.save(output_dir / name, array, allow_pickle=False)
    with (output_dir / "sample_records.jsonl").open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
    order_identity = {
        "schema_version": TASK002_OBSERVABLE_SCHEMA_VERSION,
        "axis": [
            {"side": side, "m": m, "n": 0}
            for side in ("reflection", "transmission") for m in FIXED_M_ORDERS
        ],
        "component_axis": ["s", "p"],
        "complex_axis": ["real", "imag"],
    }
    _json_dump(output_dir / "order_identity.json", order_identity)
    manifest = {
        "schema_version": TASK002_DATASET_SCHEMA_VERSION,
        "dataset_id": dataset_id, "dataset_source_sha": source_sha,
        "parameter_schema_version": TASK002_PARAMETER_SCHEMA_VERSION,
        "observable_schema_version": TASK002_OBSERVABLE_SCHEMA_VERSION,
        "sample_count": len(records), "sample_ids_hash": canonical_hash(sample_ids),
        "arrays": {
            name: {"shape": list(array.shape), "dtype": str(array.dtype)}
            for name, array in arrays.items()
        },
        "axis_meaning": {
            "inputs": ["height_nm", "width_x_nm", "grazing_deg", "azimuth_deg"],
            "aggregates": ["R_total", "T_total", "A_balance", "A_volume"],
            "order_amplitudes": ["sample", "order", "component", "real_imag"],
            "order_powers": ["sample", "order", "component"],
        },
        "units": {"inputs": ["nm", "nm", "degree", "degree"], "powers": "1"},
        "structural_null": "NaN in arrays plus false in power_carrying_mask",
        "split_hash": canonical_hash(split_indices),
    }
    _json_dump(output_dir / "dataset_manifest.json", manifest)
    hashed = [*ARRAY_FILES, "sample_records.jsonl", "order_identity.json", "dataset_manifest.json"]
    hashes = {name: file_hash(output_dir / name) for name in hashed}
    _json_dump(output_dir / "file_hashes.json", hashes)
    return verify_compact_dataset(output_dir)


def verify_compact_dataset(dataset_dir: Path) -> dict[str, Any]:
    manifest = json.loads((dataset_dir / "dataset_manifest.json").read_text())
    hashes = json.loads((dataset_dir / "file_hashes.json").read_text())
    for name, expected in hashes.items():
        if file_hash(dataset_dir / name) != expected:
            raise ValueError(f"Task002 dataset hash mismatch: {name}")
    arrays = {name: np.load(dataset_dir / name, allow_pickle=False) for name in ARRAY_FILES}
    for name, array in arrays.items():
        identity = manifest["arrays"][name]
        if list(array.shape) != identity["shape"] or str(array.dtype) != identity["dtype"]:
            raise ValueError(f"Task002 dataset array identity mismatch: {name}")
    powers = arrays["order_powers.npy"]
    mask = arrays["power_carrying_mask.npy"]
    if not np.array_equal(np.isnan(powers), ~mask):
        raise ValueError("Task002 structural null mask disagrees with power NaNs")
    split_arrays = [
        arrays["train_lf_indices.npy"], arrays["train_hf_indices.npy"],
        arrays["frozen_validation_indices.npy"],
    ]
    combined = np.concatenate(split_arrays)
    if combined.size != np.unique(combined).size:
        raise ValueError("Task002 dataset splits overlap")
    if np.any(combined < 0) or np.any(combined >= manifest["sample_count"]):
        raise ValueError("Task002 dataset split index out of range")
    return {
        "status": "pass", "dataset_id": manifest["dataset_id"],
        "dataset_source_sha": manifest["dataset_source_sha"],
        "sample_count": manifest["sample_count"], "file_count": len(hashes),
    }
