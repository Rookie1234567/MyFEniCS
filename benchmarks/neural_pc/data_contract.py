from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from src.solvers.local_slab_solver import LocalCsrOperator


DATASET_SCHEMA = "myfenics.neural_local_pc.dataset.v1"
OPERATOR_SCHEMA = "myfenics.neural_local_pc.operator.v1"


def save_operator(directory: Path, operator: LocalCsrOperator) -> None:
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        target / "operator.npz",
        indptr=operator.indptr,
        indices=operator.indices,
        values=operator.values,
        shape=np.asarray(operator.shape, dtype=np.int64),
    )
    metadata = {
        "schema": OPERATOR_SCHEMA,
        "fingerprint": operator.fingerprint,
        "shape": list(operator.shape),
        "storage_bytes": operator.storage_bytes,
        "metadata": operator.metadata,
    }
    (target / "operator.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8"
    )


def load_operator(directory: Path) -> LocalCsrOperator:
    source = Path(directory)
    metadata = json.loads((source / "operator.json").read_text(encoding="utf-8"))
    if metadata.get("schema") != OPERATOR_SCHEMA:
        raise ValueError("unsupported local operator schema")
    with np.load(source / "operator.npz", allow_pickle=False) as payload:
        operator = LocalCsrOperator(
            shape=tuple(int(value) for value in payload["shape"]),
            indptr=payload["indptr"],
            indices=payload["indices"],
            values=payload["values"],
            metadata=dict(metadata.get("metadata", {})),
        )
    if operator.fingerprint != metadata.get("fingerprint"):
        raise ValueError("local operator fingerprint mismatch")
    return operator


def save_dataset(
    directory: Path,
    *,
    operator: LocalCsrOperator,
    rhs: np.ndarray,
    target: np.ndarray,
    sample_kind: np.ndarray,
    split: np.ndarray,
    metadata: dict[str, Any],
) -> None:
    rhs = np.asarray(rhs, dtype=np.complex128)
    target_values = np.asarray(target, dtype=np.complex128)
    kinds = np.asarray(sample_kind, dtype="U32")
    splits = np.asarray(split, dtype="U16")
    if rhs.ndim != 2 or rhs.shape != target_values.shape:
        raise ValueError("dataset rhs and target must be matching matrices")
    if rhs.shape[1] != operator.shape[1]:
        raise ValueError("dataset sample width does not match operator")
    if kinds.shape != (rhs.shape[0],) or splits.shape != kinds.shape:
        raise ValueError("dataset kind/split arrays do not match sample count")
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    save_operator(target_dir, operator)
    np.savez_compressed(
        target_dir / "samples.npz",
        rhs=rhs,
        target=target_values,
        sample_kind=kinds,
        split=splits,
    )
    manifest = {
        "schema": DATASET_SCHEMA,
        "operator_fingerprint": operator.fingerprint,
        "sample_count": int(rhs.shape[0]),
        "sample_kind_counts": {
            str(kind): int(np.count_nonzero(kinds == kind)) for kind in np.unique(kinds)
        },
        "split_counts": {
            str(name): int(np.count_nonzero(splits == name)) for name in np.unique(splits)
        },
        **metadata,
    }
    (target_dir / "dataset.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )


def load_dataset(directory: Path) -> tuple[LocalCsrOperator, dict[str, np.ndarray], dict[str, Any]]:
    source = Path(directory)
    operator = load_operator(source)
    manifest = json.loads((source / "dataset.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != DATASET_SCHEMA:
        raise ValueError("unsupported neural local dataset schema")
    if manifest.get("operator_fingerprint") != operator.fingerprint:
        raise ValueError("dataset/operator fingerprint mismatch")
    with np.load(source / "samples.npz", allow_pickle=False) as payload:
        samples = {key: payload[key] for key in payload.files}
    return operator, samples, manifest
