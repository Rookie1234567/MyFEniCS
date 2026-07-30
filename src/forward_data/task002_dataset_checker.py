"""Independent exact-design verifier for the Task002 p5 compact dataset."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .task002_dataset import (
    ARRAY_FILES, PRODUCTION_AXIS_COUNTS, PRODUCTION_MODEL, PRODUCTION_ROUTE,
    verify_compact_dataset,
)
from .task002_m4 import design_point_hash, load_frozen_design
from .task002_schema import TASK002_OBSERVABLE_SCHEMA_VERSION


def _records(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def verify_exact_design_dataset(
    dataset_dir: Path, *, training_design_path: Path,
    validation_design_path: Path, baseline_sha: str,
) -> dict[str, Any]:
    basic = verify_compact_dataset(dataset_dir)
    training = load_frozen_design(
        training_design_path, baseline_sha=baseline_sha, split="train",
    )
    validation = load_frozen_design(
        validation_design_path, baseline_sha=baseline_sha,
        split="frozen_validation",
    )
    samples = _records(dataset_dir / "sample_records.jsonl")
    expected: dict[tuple[str, int], dict[str, Any]] = {}
    for design, split in ((training, "train"), (validation, "frozen_validation")):
        for index, point in enumerate(design["points"]):
            expected[(design["design_id"], index)] = {
                "split": split,
                "inputs": [float(point[name]) for name in (
                    "height_nm", "width_x_nm", "grazing_deg", "azimuth_deg",
                )],
                "point_hash": design_point_hash(
                    design_id=design["design_id"], design_index=index, point=point,
                ),
            }
    observed: dict[tuple[str, int], dict[str, Any]] = {}
    for sample in samples:
        key = (sample["design_id"], int(sample["design_index"]))
        if key in observed:
            raise ValueError(f"duplicate exact-design sample: {key}")
        if key not in expected:
            raise ValueError(f"extra point outside frozen designs: {key}")
        identity = expected[key]
        if sample.get("split") != identity["split"]:
            raise ValueError(f"sample split mismatch: {key}")
        if [float(value) for value in sample.get("inputs", [])] != identity["inputs"]:
            raise ValueError(f"sample tuple mismatch: {key}")
        if sample.get("point_hash") != identity["point_hash"]:
            raise ValueError(f"sample point hash mismatch: {key}")
        if sample.get("source_sha") != baseline_sha or sample.get("source_dirty") is not False:
            raise ValueError(f"sample source mismatch: {key}")
        if sample.get("status") != "measured_pass":
            raise ValueError(f"non-passing sample entered dataset: {key}")
        if sample.get("solver_route_id") != PRODUCTION_ROUTE:
            raise ValueError(f"non-Ny4 sample entered dataset: {key}")
        if sample.get("model_id") != PRODUCTION_MODEL:
            raise ValueError(f"non-Ny4 model entered dataset: {key}")
        if sample.get("axis_cell_counts") != PRODUCTION_AXIS_COUNTS:
            raise ValueError(f"non-Ny4 topology entered dataset: {key}")
        mother = sample.get("mother_response", {})
        if mother.get("schema_version") != TASK002_OBSERVABLE_SCHEMA_VERSION:
            raise ValueError(f"observable v3 mismatch: {key}")
        leakage = mother.get("leakage", {})
        if (float(leakage.get("n_nonzero_reflection_power_sum", 1.0))
                + float(leakage.get("n_nonzero_transmission_power_sum", 1.0))) > 1.0e-7:
            raise ValueError(f"n!=0 power leakage Gate failed: {key}")
        if float(leakage.get("n_nonzero_max_abs_amplitude", 1.0)) > 1.0e-4:
            raise ValueError(f"n!=0 amplitude leakage Gate failed: {key}")
        ledger = mother.get("power_ledger", {})
        if abs(float(ledger.get("raw_R_minus_fixed_n0_R_minus_n_nonzero_R", 1.0))) > 1e-12:
            raise ValueError(f"reflection ledger failed: {key}")
        if abs(float(ledger.get("raw_T_minus_fixed_n0_T_minus_n_nonzero_T", 1.0))) > 1e-12:
            raise ValueError(f"transmission ledger failed: {key}")
        if not all(sample.get("numerical_gates", {}).values()):
            raise ValueError(f"numerical Gate failed: {key}")
        if not all(sample.get("resource_gates", {}).values()):
            raise ValueError(f"resource Gate failed: {key}")
        observed[key] = sample
    missing = sorted(set(expected) - set(observed))
    if missing:
        raise ValueError(f"dataset misses frozen design points: {missing[:5]}")
    arrays = {name: np.load(dataset_dir / name, allow_pickle=False) for name in ARRAY_FILES}
    if len(arrays["train_indices.npy"]) != 96:
        raise ValueError("exact training count is not 96")
    if len(arrays["frozen_validation_indices.npy"]) != 16:
        raise ValueError("exact frozen-validation count is not 16")
    train_tuples = {tuple(sample["inputs"]) for sample in samples if sample["split"] == "train"}
    validation_tuples = {
        tuple(sample["inputs"]) for sample in samples
        if sample["split"] == "frozen_validation"
    }
    if train_tuples & validation_tuples:
        raise ValueError("training and frozen validation tuples overlap")
    return {
        **basic, "status": "pass", "exact_design_coverage": True,
        "training_count": 96, "frozen_validation_count": 16,
        "extra_count": 0, "missing_count": 0, "source_sha": baseline_sha,
    }
