"""Canonical Ny4 p5-only Task002 dataset v3 writer and verifier."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from .provenance import canonical_hash, file_hash
from .task002_schema import (
    TASK002_DATASET_SCHEMA_VERSION, TASK002_FIXED_M_ORDERS,
    TASK002_OBSERVABLE_SCHEMA_VERSION, TASK002_PARAMETER_SCHEMA_VERSION,
)


PRODUCTION_ROUTE = "full3d_static_uniform_n1curl_p5_h10_ny4"
PRODUCTION_MODEL = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
PRODUCTION_AXIS_COUNTS = [6, 4, 14]
ARRAY_FILES = (
    "inputs.npy", "aggregates.npy", "order_amplitudes.npy", "order_powers.npy",
    "power_carrying_mask.npy", "train_indices.npy",
    "frozen_validation_indices.npy",
)


def _json_dump(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                    encoding="utf-8")


def _source_identity(samples: list[Mapping[str, Any]]) -> str:
    identities = {(sample.get("source_sha"), sample.get("source_dirty")) for sample in samples}
    if len(identities) != 1:
        raise ValueError("Task002 dataset samples mix source identities")
    source_sha, dirty = identities.pop()
    if dirty is not False or not isinstance(source_sha, str) or len(source_sha) != 40:
        raise ValueError("Task002 dataset requires one clean full source SHA")
    return source_sha


def _validate_orders(sample: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    response = sample.get("mother_response", {})
    if response.get("schema_version") != TASK002_OBSERVABLE_SCHEMA_VERSION:
        raise ValueError("Task002 mother-response v3 schema mismatch")
    orders = list(response.get("orders", []))
    expected = [(side, m, 0) for side in ("reflection", "transmission")
                for m in TASK002_FIXED_M_ORDERS]
    actual = [(row.get("side"), row.get("m"), row.get("n")) for row in orders]
    if actual != expected:
        raise ValueError("Task002 mother-response v3 order identity mismatch")
    if response.get("uncovered_power_carrying_n0"):
        raise ValueError("Task002 mother-response has power outside the frozen v3 window")
    return orders


def write_compact_dataset(samples: Iterable[Mapping[str, Any]], *, output_dir: Path,
                          dataset_id: str) -> dict[str, Any]:
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
        raise ValueError("only measured_pass samples enter the compact production dataset")
    if any(record.get("solver_route_id") != PRODUCTION_ROUTE for record in records):
        raise ValueError("Task002 production dataset is Full3D p5/h10/Ny4 only")
    if any(record.get("model_id") != PRODUCTION_MODEL for record in records):
        raise ValueError("Task002 production dataset rejects non-Ny4 model identity")
    if any(record.get("axis_cell_counts") != PRODUCTION_AXIS_COUNTS for record in records):
        raise ValueError("Task002 production dataset rejects non-Ny4 topology")
    for record in records:
        if not all(record.get("numerical_gates", {}).values()):
            raise ValueError("Task002 dataset rejects samples with failed numerical gates")
        if not all(record.get("resource_gates", {}).values()):
            raise ValueError("Task002 dataset rejects samples with failed resource gates")
        mother = record.get("mother_response", {})
        leakage = mother.get("leakage", {})
        leakage_power = (
            float(leakage.get("n_nonzero_reflection_power_sum", 1.0))
            + float(leakage.get("n_nonzero_transmission_power_sum", 1.0))
        )
        if leakage_power > 1.0e-7 or float(
            leakage.get("n_nonzero_max_abs_amplitude", 1.0)
        ) > 1.0e-4:
            raise ValueError("Task002 dataset rejects n!=0 leakage Gate failure")
        ledger = mother.get("power_ledger", {})
        if max(
            abs(float(ledger.get("raw_R_minus_fixed_n0_R_minus_n_nonzero_R", 1.0))),
            abs(float(ledger.get("raw_T_minus_fixed_n0_T_minus_n_nonzero_T", 1.0))),
        ) > 1.0e-12:
            raise ValueError("Task002 dataset rejects fixed/raw power-ledger failure")

    n_orders = 2 * len(TASK002_FIXED_M_ORDERS)
    inputs = np.empty((len(records), 4), dtype=np.float64)
    aggregates = np.empty((len(records), 4), dtype=np.float64)
    amplitudes = np.full((len(records), n_orders, 2, 2), np.nan, dtype=np.float64)
    powers = np.full((len(records), n_orders, 2), np.nan, dtype=np.float64)
    mask = np.zeros((len(records), n_orders, 2), dtype=np.bool_)
    split_indices = {"train": [], "frozen_validation": []}
    for index, record in enumerate(records):
        inputs[index] = np.asarray(record["inputs"], dtype=np.float64)
        aggregates[index] = [float(record["aggregates"][name])
                             for name in ("R_total", "T_total", "A_balance", "A_volume")]
        for order_index, order in enumerate(_validate_orders(record)):
            for component_index, component_name in enumerate(("s", "p")):
                component = order["components"][component_name]
                real, imag, power = (component.get(name) for name in
                                     ("amplitude_re", "amplitude_im", "power"))
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
            raise ValueError(f"unsupported p5-only Task002 split: {split}")
        split_indices[split].append(index)

    arrays = {
        "inputs.npy": inputs, "aggregates.npy": aggregates,
        "order_amplitudes.npy": amplitudes, "order_powers.npy": powers,
        "power_carrying_mask.npy": mask,
        "train_indices.npy": np.asarray(split_indices["train"], dtype=np.int64),
        "frozen_validation_indices.npy": np.asarray(
            split_indices["frozen_validation"], dtype=np.int64),
    }
    for name, array in arrays.items():
        np.save(output_dir / name, array, allow_pickle=False)
    with (output_dir / "sample_records.jsonl").open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
    order_identity = {
        "schema_version": TASK002_OBSERVABLE_SCHEMA_VERSION,
        "axis": [{"side": side, "m": m, "n": 0}
                 for side in ("reflection", "transmission")
                 for m in TASK002_FIXED_M_ORDERS],
        "component_axis": ["s", "p"], "complex_axis": ["real", "imag"],
    }
    _json_dump(output_dir / "order_identity.json", order_identity)
    manifest = {
        "schema_version": TASK002_DATASET_SCHEMA_VERSION,
        "dataset_id": dataset_id, "dataset_source_sha": source_sha,
        "parameter_schema_version": TASK002_PARAMETER_SCHEMA_VERSION,
        "observable_schema_version": TASK002_OBSERVABLE_SCHEMA_VERSION,
        "production_solver_route_id": PRODUCTION_ROUTE,
        "production_model_id": PRODUCTION_MODEL,
        "production_axis_cell_counts": PRODUCTION_AXIS_COUNTS,
        "fidelity_semantics": "p5_single_fidelity_best_available_operational_HF",
        "sample_count": len(records), "sample_ids_hash": canonical_hash(sample_ids),
        "arrays": {name: {"shape": list(array.shape), "dtype": str(array.dtype)}
                   for name, array in arrays.items()},
        "axis_meaning": {
            "inputs": ["height_nm", "width_x_nm", "grazing_deg", "azimuth_deg"],
            "aggregates": ["R_total", "T_total", "A_balance", "A_volume"],
            "order_amplitudes": ["sample", "order", "component", "real_imag"],
            "order_powers": ["sample", "order", "component"],
        },
        "units": {"inputs": ["nm", "nm", "degree", "degree"], "powers": "1"},
        "structural_null": "NaN in arrays plus false in power_carrying_mask",
        "split_hash": canonical_hash(split_indices),
        "discretization_audit_disposition": "separate diagnostic table; never production samples",
    }
    _json_dump(output_dir / "dataset_manifest.json", manifest)
    hashed = [*ARRAY_FILES, "sample_records.jsonl", "order_identity.json", "dataset_manifest.json"]
    _json_dump(output_dir / "file_hashes.json",
               {name: file_hash(output_dir / name) for name in hashed})
    return verify_compact_dataset(output_dir)


def verify_compact_dataset(dataset_dir: Path) -> dict[str, Any]:
    manifest = json.loads((dataset_dir / "dataset_manifest.json").read_text())
    if manifest.get("schema_version") != TASK002_DATASET_SCHEMA_VERSION:
        raise ValueError("Task002 Ny4 dataset v3 schema mismatch")
    if manifest.get("production_solver_route_id") != PRODUCTION_ROUTE:
        raise ValueError("Task002 dataset manifest is not Ny4 p5-only")
    if manifest.get("production_model_id") != PRODUCTION_MODEL:
        raise ValueError("Task002 dataset manifest model is not Ny4 p5-only")
    if manifest.get("production_axis_cell_counts") != PRODUCTION_AXIS_COUNTS:
        raise ValueError("Task002 dataset manifest topology is not Ny4")
    hashes = json.loads((dataset_dir / "file_hashes.json").read_text())
    for name, expected in hashes.items():
        if file_hash(dataset_dir / name) != expected:
            raise ValueError(f"Task002 dataset hash mismatch: {name}")
    arrays = {name: np.load(dataset_dir / name, allow_pickle=False) for name in ARRAY_FILES}
    for name, array in arrays.items():
        identity = manifest["arrays"][name]
        if list(array.shape) != identity["shape"] or str(array.dtype) != identity["dtype"]:
            raise ValueError(f"Task002 dataset array identity mismatch: {name}")
    if not np.array_equal(np.isnan(arrays["order_powers.npy"]),
                          ~arrays["power_carrying_mask.npy"]):
        raise ValueError("Task002 structural null mask disagrees with power NaNs")
    combined = np.concatenate([arrays["train_indices.npy"],
                               arrays["frozen_validation_indices.npy"]])
    if combined.size != np.unique(combined).size:
        raise ValueError("Task002 dataset splits overlap")
    if np.any(combined < 0) or np.any(combined >= manifest["sample_count"]):
        raise ValueError("Task002 dataset split index out of range")
    if set(combined.tolist()) != set(range(manifest["sample_count"])):
        raise ValueError("Task002 dataset splits do not cover every sample exactly once")
    return {"status": "pass", "dataset_id": manifest["dataset_id"],
            "dataset_source_sha": manifest["dataset_source_sha"],
            "sample_count": manifest["sample_count"], "file_count": len(hashes)}
