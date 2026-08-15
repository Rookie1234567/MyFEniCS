from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from benchmarks.task039_hybrid_direct_identity import (
    IdentityCheckError,
    _verify_canonical_shard_files,
    reconstruct_hash_bound_solution_vector,
)


def _bound_inventory(
    values: np.ndarray, layout: dict[str, object]
) -> dict[str, object]:
    payload = np.ascontiguousarray(values, dtype=np.complex128).tobytes(order="C")
    return {
        "mapping_status": "available",
        "row_mapping": {
            "layout": layout,
            "global_size": int(values.size),
            "solution_sha256": hashlib.sha256(payload).hexdigest(),
        },
    }


def test_direct_solution_reconstruction_is_hash_and_layout_bound():
    values = np.asarray([1.0 + 0.2j, -0.5 + 0.1j, 0.8 - 0.3j], dtype=np.complex128)
    layout = {"global_size": 3, "bottom": 1, "top": 1, "modal": 1}
    inventory = _bound_inventory(values, layout)
    actual = reconstruct_hash_bound_solution_vector(
        inventory,
        values,
        expected_layout=layout,
    )
    assert np.array_equal(actual, values)

    with pytest.raises(IdentityCheckError, match="hash"):
        reconstruct_hash_bound_solution_vector(
            inventory,
            values + 1.0,
            expected_layout=layout,
        )
    with pytest.raises(IdentityCheckError, match="layout"):
        reconstruct_hash_bound_solution_vector(
            inventory,
            values,
            expected_layout={**layout, "bottom": 2},
        )


def test_direct_solution_reconstruction_fails_closed_without_row_mapping():
    values = np.ones(3, dtype=np.complex128)
    with pytest.raises(IdentityCheckError, match="row map"):
        reconstruct_hash_bound_solution_vector(
            {"mapping_status": "not_available", "row_mapping": None},
            values,
            expected_layout={"global_size": 3},
        )


def test_canonical_shard_sha_and_presence_are_fail_closed(tmp_path: Path):
    shard = tmp_path / "rank0000.jsonl"
    shard.write_bytes(b"synthetic-shard\n")
    metadata = {
        "rank": 0,
        "filename": shard.name,
        "file_sha256": hashlib.sha256(shard.read_bytes()).hexdigest(),
        "packet_count": 0,
    }
    verified = _verify_canonical_shard_files(tmp_path / "manifest.json", [metadata])
    assert verified[0]["file_sha256"] == metadata["file_sha256"]
    assert len(verified) == 1

    shard.write_bytes(b"tampered\n")
    with pytest.raises(IdentityCheckError, match="SHA"):
        _verify_canonical_shard_files(tmp_path / "manifest.json", [metadata])
    shard.unlink()
    with pytest.raises(IdentityCheckError, match="missing"):
        _verify_canonical_shard_files(tmp_path / "manifest.json", [metadata])
