"""Immutable Case119 loader and train-only dataset guards.

This module is intentionally independent of any FEM code.  The validation
array is never opened by :func:`load_training_dataset`; validation metadata is
checked only by the explicit M0 verifier before model selection is locked.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


CASE119_DATASET_ID = "task002_m4e_p5_ny4_112_v3"
CASE119_DATASET_SCHEMA = "task002.s-p5-ny4-single-fidelity-dataset.v3"
CASE119_ROOT = Path("benchmarks/artifacts/cases/119/m4e/compact_dataset")
ARRAY_FILES = (
    "inputs.npy",
    "aggregates.npy",
    "order_amplitudes.npy",
    "order_powers.npy",
    "power_carrying_mask.npy",
    "train_indices.npy",
    "frozen_validation_indices.npy",
)
NON_ARRAY_FILES = ("sample_records.jsonl", "order_identity.json", "dataset_manifest.json")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class CompactDatasetVerification:
    """Serializable result of the independent M0-L dataset audit."""

    dataset_id: str
    schema_version: str
    sample_count: int
    training_count: int
    frozen_validation_count: int
    arrays: dict[str, dict[str, Any]]
    file_hashes: dict[str, str]
    train_tuple_sha256: str
    frozen_validation_tuple_sha256: str
    validation_target_accessed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "pass",
            "dataset_id": self.dataset_id,
            "schema_version": self.schema_version,
            "sample_count": self.sample_count,
            "training_count": self.training_count,
            "frozen_validation_count": self.frozen_validation_count,
            "arrays": self.arrays,
            "file_hashes": self.file_hashes,
            "train_tuple_sha256": self.train_tuple_sha256,
            "frozen_validation_tuple_sha256": self.frozen_validation_tuple_sha256,
            "validation_target_accessed": self.validation_target_accessed,
        }


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


def _load_manifest(dataset_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    manifest = json.loads((dataset_dir / "dataset_manifest.json").read_text())
    hashes = json.loads((dataset_dir / "file_hashes.json").read_text())
    if manifest.get("dataset_id") != CASE119_DATASET_ID:
        raise ValueError("unexpected Case119 dataset id")
    if manifest.get("schema_version") != CASE119_DATASET_SCHEMA:
        raise ValueError("unexpected Case119 dataset schema")
    if int(manifest.get("sample_count", -1)) != 112:
        raise ValueError("Case119 dataset sample count is not 112")
    expected_files = {*ARRAY_FILES, *NON_ARRAY_FILES}
    if set(hashes) != expected_files:
        raise ValueError("Case119 file hash set is incomplete or has extra files")
    return manifest, hashes


def _tuple_hash(records: list[dict[str, Any]], split: str) -> str:
    tuples = [
        [float(v) for v in row["inputs"]]
        for row in records
        if row.get("split") == split
    ]
    return _canonical_hash(tuples)


def verify_case119_dataset(dataset_dir: Path = CASE119_ROOT) -> CompactDatasetVerification:
    """Verify all immutable hashes, array identities, and split invariants.

    This explicit audit may inspect the sealed validation *array identity* and
    row count.  It does not return validation values and is never used by the
    training loader.  ``validation_target_accessed`` therefore remains false
    by construction.
    """

    dataset_dir = Path(dataset_dir)
    manifest, expected_hashes = _load_manifest(dataset_dir)
    actual_hashes = {name: sha256_file(dataset_dir / name) for name in expected_hashes}
    if actual_hashes != expected_hashes:
        bad = [name for name in expected_hashes if actual_hashes[name] != expected_hashes[name]]
        raise ValueError(f"Case119 file hash mismatch: {bad}")

    arrays: dict[str, dict[str, Any]] = {}
    loaded: dict[str, np.ndarray] = {}
    for name in ARRAY_FILES:
        array = np.load(dataset_dir / name, allow_pickle=False)
        loaded[name] = array
        identity = {"shape": list(array.shape), "dtype": str(array.dtype)}
        if identity != manifest["arrays"][name]:
            raise ValueError(f"Case119 array identity mismatch: {name}")
        arrays[name] = identity

    inputs = loaded["inputs.npy"]
    aggregates = loaded["aggregates.npy"]
    powers = loaded["order_powers.npy"]
    mask = loaded["power_carrying_mask.npy"]
    train = loaded["train_indices.npy"]
    validation = loaded["frozen_validation_indices.npy"]
    if train.shape != (96,) or validation.shape != (16,):
        raise ValueError("Case119 split counts are not 96/16")
    combined = np.concatenate((train, validation))
    if not np.array_equal(np.sort(combined), np.arange(112)):
        raise ValueError("Case119 split indices do not partition 0..111")
    if not np.all(np.isfinite(inputs)) or not np.all(np.isfinite(aggregates)):
        raise ValueError("Case119 inputs/aggregates contain non-finite values")
    if not np.array_equal(np.isnan(powers), ~mask):
        raise ValueError("Case119 structural-null mask disagrees with power NaNs")
    if np.any(powers[mask] < 0):
        raise ValueError("Case119 power array contains a negative carrying value")

    records = [json.loads(line) for line in
               (dataset_dir / "sample_records.jsonl").read_text().splitlines() if line.strip()]
    if len(records) != 112:
        raise ValueError("Case119 sample record count is not 112")
    ids = [row.get("sample_id") for row in records]
    if len(set(ids)) != 112:
        raise ValueError("Case119 sample ids are not unique")
    if _canonical_hash(ids) != manifest.get("sample_ids_hash"):
        raise ValueError("Case119 sample id hash mismatch")
    if sum(row.get("split") == "train" for row in records) != 96:
        raise ValueError("Case119 records do not contain 96 training rows")
    if sum(row.get("split") == "frozen_validation" for row in records) != 16:
        raise ValueError("Case119 records do not contain 16 frozen-validation rows")

    return CompactDatasetVerification(
        dataset_id=manifest["dataset_id"],
        schema_version=manifest["schema_version"],
        sample_count=112,
        training_count=96,
        frozen_validation_count=16,
        arrays=arrays,
        file_hashes=actual_hashes,
        train_tuple_sha256=_tuple_hash(records, "train"),
        frozen_validation_tuple_sha256=_tuple_hash(records, "frozen_validation"),
    )


@dataclass(frozen=True)
class TrainingDataset:
    """A materialized training-only view of Case119.

    No frozen-validation index or row is loaded here.  The object intentionally
    has no attribute through which a caller could obtain sealed target rows.
    """

    inputs: np.ndarray
    aggregates: np.ndarray
    order_amplitudes: np.ndarray
    order_powers: np.ndarray
    power_carrying_mask: np.ndarray
    source_indices: np.ndarray
    dataset_id: str = CASE119_DATASET_ID

    @property
    def n_samples(self) -> int:
        return int(self.inputs.shape[0])


def load_training_dataset(dataset_dir: Path = CASE119_ROOT) -> TrainingDataset:
    """Load only the 96 training rows; never open the frozen split file."""

    dataset_dir = Path(dataset_dir)
    manifest = json.loads((dataset_dir / "dataset_manifest.json").read_text())
    if not manifest.get("dataset_id"):
        raise ValueError("dataset manifest is missing dataset id")
    train_indices = np.load(dataset_dir / "train_indices.npy", allow_pickle=False)
    expected_training = int(manifest.get("training_count", len(train_indices)))
    if train_indices.shape != (expected_training,):
        raise ValueError("training split count does not match dataset manifest")
    # mmap keeps the sealed file on disk and only copies the explicitly selected
    # rows.  The frozen-validation index file is deliberately not opened.
    arrays = {
        name: np.load(dataset_dir / name, allow_pickle=False, mmap_mode="r")[train_indices].copy()
        for name in ("inputs.npy", "aggregates.npy", "order_amplitudes.npy", "order_powers.npy",
                     "power_carrying_mask.npy")
    }
    if not np.all(np.isfinite(arrays["inputs.npy"])):
        raise ValueError("training inputs are non-finite")
    if not np.all(np.isfinite(arrays["aggregates.npy"])):
        raise ValueError("training aggregates are non-finite")
    if not np.array_equal(np.isnan(arrays["order_powers.npy"]),
                          ~arrays["power_carrying_mask.npy"]):
        raise ValueError("training structural-null mask disagrees")
    return TrainingDataset(
        inputs=arrays["inputs.npy"], aggregates=arrays["aggregates.npy"],
        order_amplitudes=arrays["order_amplitudes.npy"],
        order_powers=arrays["order_powers.npy"],
        power_carrying_mask=arrays["power_carrying_mask.npy"],
        source_indices=train_indices.copy(),
        dataset_id=str(manifest["dataset_id"]),
    )
