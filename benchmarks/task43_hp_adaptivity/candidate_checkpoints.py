"""Atomic, pre-validation field checkpoints for Task43 candidate runs."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _array_identity(values: np.ndarray) -> dict[str, Any]:
    array = np.ascontiguousarray(values)
    if array.dtype.hasobject:
        raise TypeError("pre-validation checkpoint arrays must not use pickle")
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(json.dumps(list(array.shape)).encode("ascii"))
    digest.update(array.view(np.uint8))
    return {
        "dtype": array.dtype.str,
        "shape": list(array.shape),
        "sha256": digest.hexdigest(),
    }


def _replace_atomically(path: Path, writer) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as stream:
            writer(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def write_pre_validation_checkpoint(
    path: Path,
    arrays: Mapping[str, np.ndarray],
    *,
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Atomically save serial recovered state before expensive observer work.

    This checkpoint is diagnostic recovery material only. It does not mean the
    solver, independent active residual, or Task43 official-result gates passed.
    The NPZ is renamed into place before its hash-bound JSON sidecar is written.
    """

    path = Path(path)
    sidecar = path.with_suffix(".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or sidecar.exists():
        raise FileExistsError(f"refusing to overwrite checkpoint {path}")

    arrays_copy = {
        str(name): np.asarray(value) for name, value in arrays.items()
    }
    if not arrays_copy:
        raise ValueError("pre-validation checkpoint cannot be empty")
    array_identities = {
        name: _array_identity(values) for name, values in arrays_copy.items()
    }

    def write_npz(stream) -> None:
        np.savez_compressed(stream, **arrays_copy)

    _replace_atomically(path, write_npz)
    record = {
        "schema": "task43.pre-validation-field-checkpoint.v1",
        "status": "written_before_field_capture_and_independent_A6",
        "classification": "pre_validation_diagnostic_not_official",
        "official_result": False,
        "independent_A6": "not_run_at_checkpoint_time",
        "field_capture": "not_run_at_checkpoint_time",
        "mpi_size": 1,
        "npz_path": str(path),
        "npz_sha256": _sha256_file(path),
        "arrays": array_identities,
        "identity": dict(identity),
    }

    def write_json(stream) -> None:
        stream.write(
            (json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n")
            .encode("utf-8")
        )

    _replace_atomically(sidecar, write_json)
    return {**record, "sidecar_path": str(sidecar), "sidecar_sha256": _sha256_file(sidecar)}
