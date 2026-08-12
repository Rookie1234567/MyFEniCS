from __future__ import annotations

import json
import hashlib
from pathlib import Path

import numpy as np
import pytest

from src.solvers.hcurl_h2b_packed_patch_store import (
    H2B_M3Y_RETAINED_BYTES_LIMIT,
    H2BM3YPackedCholeskyFactor,
    build_h2b_m3y_packed_factor,
    build_h2b_m3y_packed_patch_store,
    load_h2b_m3y_packed_patch_store,
    packed_factor_nbytes,
    write_h2b_m3y_packed_patch_store,
)


def _matrix() -> np.ndarray:
    seed = np.asarray(
        (
            (1.0 + 0.2j, 0.1 - 0.3j, 0.2 + 0.1j),
            (0.4 + 0.1j, 1.4 + 0.2j, -0.2 + 0.2j),
            (0.3 - 0.1j, 0.2 + 0.4j, 1.1 + 0.1j),
        ),
        dtype=np.complex128,
        order="C",
    )
    return np.asarray(
        seed @ seed.conj().T + 2.0 * np.eye(3),
        dtype=np.complex128,
        order="C",
    )


def _neighborhoods() -> tuple[dict[str, object], ...]:
    return (
        {
            "neighborhood_id": 0,
            "key_sha256": "0" * 64,
            "cell_ordinals": [0],
            "multiplicity": 1,
            "factor_id": 0,
        },
        {
            "neighborhood_id": 1,
            "key_sha256": "1" * 64,
            "cell_ordinals": [1],
            "multiplicity": 1,
            "factor_id": 0,
        },
    )


def _store(tmp_path: Path):
    factor = build_h2b_m3y_packed_factor(
        _matrix(), task037_extra_h2b=True
    )
    store = build_h2b_m3y_packed_patch_store(
        (factor,),
        _neighborhoods(),
        np.asarray([0, 1], dtype=np.int32),
        np.asarray([0, 3, 6], dtype=np.int64),
        np.asarray([0, 1, 2, 4, 5, 6], dtype=np.int64),
        identity={"source_identity": "a" * 64, "scope": "synthetic"},
        task037_extra_h2b=True,
    )
    manifest = write_h2b_m3y_packed_patch_store(
        store, tmp_path / "packed_store", task037_extra_h2b=True
    )
    return store, manifest


def test_packed_factor_solves_and_retains_no_square_or_pivots():
    matrix = _matrix()
    factor = build_h2b_m3y_packed_factor(matrix, task037_extra_h2b=True)
    rhs = np.asarray([1.0 + 0.2j, -0.3 + 0.1j, 0.7 - 0.4j], dtype=np.complex128)
    expected = np.linalg.solve(matrix, rhs)
    assert np.allclose(factor.solve(rhs), expected, rtol=1e-11, atol=1e-12)
    assert factor.packed_values.ndim == 1
    assert factor.packed_values.shape == (6,)
    assert factor.matrix_sha256 == hashlib.sha256(
        memoryview(matrix).cast("B")
    ).hexdigest()
    assert factor.packed_nbytes == packed_factor_nbytes(3)
    assert not hasattr(factor, "pivots")
    assert not hasattr(factor, "values")
    assert factor.packed_values.flags.writeable is False
    assert factor.audit_jsonable()["full_dense_factor_retained"] is False
    assert factor.audit_jsonable()["pivots_retained"] is False


def test_packed_store_cold_roundtrip_mmap_mapping_and_audit(tmp_path):
    store, manifest_path = _store(tmp_path)
    loaded = load_h2b_m3y_packed_patch_store(
        manifest_path, task037_extra_h2b=True
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["evidence_sha256"]) == 64
    assert loaded.factor_for_cell(0).factor_sha256 == loaded.factor_for_cell(1).factor_sha256
    assert np.array_equal(loaded.cell_rows(1), np.asarray([4, 5, 6], dtype=np.int64))
    full = np.arange(10, dtype=np.float64).astype(np.complex128)
    assert np.array_equal(loaded.gather(full, 1), full[[4, 5, 6]])
    rhs = np.asarray([1.0 + 0.2j, -0.3 + 0.1j, 0.7 - 0.4j], dtype=np.complex128)
    assert np.allclose(loaded.solve(0, rhs), store.solve(0, rhs))
    gathered_rhs = loaded.gather(full, 0)
    assert np.allclose(
        loaded.solve(0, gathered_rhs), np.linalg.solve(_matrix(), gathered_rhs)
    )
    assert loaded.factor_for_cell(0).packed_values.flags.writeable is False
    assert isinstance(loaded.factor_for_cell(0).packed_values.base, np.memmap)
    audit = loaded.audit_jsonable()
    assert audit["packed_cholesky"] is True
    assert audit["full_dense_factor_count"] == 0
    assert audit["pivots_retained"] is False
    assert audit["retained_total_bytes"] == sum(
        audit["retained_payload_components"].values()
    )
    assert audit["retained_total_gate"] is True
    assert audit["retained_total_bytes"] <= H2B_M3Y_RETAINED_BYTES_LIMIT
    assert audit["materialization_identity"]["global_matrix"] is False
    assert audit["materialization_identity"]["static_condensation"] is False
    assert audit["materialization_identity"]["trace_slab"] is False


def test_packed_store_rejects_tampered_factor_sha(tmp_path):
    _store(tmp_path)
    root = tmp_path / "packed_store"
    packed_path = root / "factor_0_packed.npy"
    original = packed_path.read_bytes()
    packed_path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
    with pytest.raises(ValueError, match="SHA|identity"):
        load_h2b_m3y_packed_patch_store(
            root / "manifest.json", task037_extra_h2b=True
        )


def test_packed_factor_rejects_non_hp_or_wrong_shape():
    with pytest.raises(np.linalg.LinAlgError):
        build_h2b_m3y_packed_factor(
            np.asarray(
                ((1.0 + 0.0j, 2.0 + 0.0j), (2.0 + 0.0j, 1.0 + 0.0j)),
                dtype=np.complex128,
                order="C",
            ),
            task037_extra_h2b=True,
        )
    with pytest.raises(ValueError):
        H2BM3YPackedCholeskyFactor(
            np.ones(3, dtype=np.complex128), 3
        )
