from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from src.solvers.hcurl_r2_constrained_local_block import (
    build_h2a_r2_cell_expansion,
)
from src.solvers.hcurl_r2_factor_store import (
    H2AR2CellReference,
    H2AR2ClassInput,
    build_h2a_r2_factor_store,
    load_h2a_r2_factor_store,
    write_h2a_r2_factor_store,
)


class _IndexMap:
    def local_to_global(self, rows):
        return np.asarray(rows, dtype=np.int64) + 100


def _expansion():
    return build_h2a_r2_cell_expansion(
        (),
        (0, 1),
        _IndexMap(),
        index_map_bs=1,
        phase_x=1.0 + 0.0j,
        phase_y=1.0 + 0.0j,
    )


def _matrix():
    return np.asarray(
        ((0.1 + 0.2j, 2.0 - 0.1j), (3.0 + 0.4j, 4.0 + 0.5j)),
        dtype=np.complex128,
        order="C",
    )


def _identity():
    return {
        "source_identity": {"commit": "a" * 40, "clean": True},
        "config_identity": {"degree": 2, "h_nm": 10.0},
        "form_identity": {"proxy": "B0", "jit": "qualified"},
        "cache_identity": {"manifest": "r2-a-test"},
    }


def _build_store():
    expansion = _expansion()
    matrix = _matrix()
    consumed = {"count": 0}

    def class_stream():
        for class_id, key in enumerate(("a" * 64, "b" * 64)):
            consumed["count"] += 1
            yield H2AR2ClassInput(
                class_id=class_id,
                class_key_sha256=key,
                constraint_pattern_sha256="c" * 64,
                expansion_pattern_sha256=expansion.pattern_sha256,
                expansion=expansion,
                transformed_matrix=matrix.copy(),
            )

    store = build_h2a_r2_factor_store(
        class_stream(),
        (
            H2AR2CellReference(0, np.asarray((100, 101), dtype=np.int64)),
            H2AR2CellReference(1, np.asarray((200, 201), dtype=np.int64)),
        ),
        identity=_identity(),
        task037_extra_h2a_r2=True,
    )
    return store, consumed


def test_r2_factor_store_streams_exact_dedup_and_residuals():
    store, consumed = _build_store()
    audit = store.audit
    assert consumed["count"] == 2
    assert audit["class_count"] == 2
    assert audit["unique_factor_count"] == 1
    assert audit["numeric_hash_dedup_count"] == 1
    assert audit["per_cell_factor_count"] == 0
    assert audit["finite"] is True
    assert audit["deterministic"] is True
    assert audit["factorization_residual_max"] <= 1.0e-10
    assert audit["solve_residual_max"] <= 1.0e-10
    assert audit["factor_plus_metadata_bytes"] == audit["retained_payload_bytes"]
    assert store.classes[0].constraint_pattern_sha256 == "c" * 64
    assert (
        store.classes[0].expansion_pattern_sha256
        == store.classes[0].expansion.pattern_sha256
    )
    assert store.classes[0].constraint_pattern_sha256 != (
        store.classes[0].expansion_pattern_sha256
    )
    assert store.classes[0].factor_id == store.classes[1].factor_id == 0
    assert store.classes[0].numeric_matrix_sha256 == store.classes[1].numeric_matrix_sha256
    assert np.any(store.factors[0].pivots != np.arange(2, dtype=np.int32))
    assert np.array_equal(store.factors[0].values, _build_store()[0].factors[0].values)
    assert np.array_equal(store.factors[0].pivots, _build_store()[0].factors[0].pivots)
    rhs = np.asarray((1.0 + 0.2j, -0.4 + 0.7j), dtype=np.complex128)
    expected = np.linalg.solve(_matrix(), rhs)
    observed = store.solve(0, rhs)
    assert np.linalg.norm(observed - expected) / np.linalg.norm(expected) <= 1.0e-10
    assert np.array_equal(observed, store.solve(1, rhs))
    assert not hasattr(store, "_transformed_matrices")
    assert not hasattr(store, "_dense_expansions")
    for record in store.classes:
        assert record.expansion.offsets.ndim == 1
        assert record.expansion.column_indices.ndim == 1
        assert record.expansion.coefficients.ndim == 1


def test_r2_factor_store_cold_roundtrip_uses_numeric_arrays_only(tmp_path, monkeypatch):
    store, _consumed = _build_store()
    manifest_path = write_h2a_r2_factor_store(
        store,
        tmp_path / "factor_store",
        task037_extra_h2a_r2=True,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "task037.extra.h2a.r2.factor-store.v1"
    assert all(Path(path).suffix == ".npy" for path in manifest["files"])
    assert all(
        item["dtype"] != "object" and "array_sha256" in item
        for item in manifest["files"].values()
    )
    assert manifest["payload"]["metadata_basis"] == "canonical_utf8_json_metadata"
    assert (
        manifest["payload"]["factor_plus_metadata_bytes"]
        == manifest["payload"]["retained_payload_bytes"]
    )
    assert (
        manifest["payload"]["factor_plus_metadata_basis"]
        == "factor_values+pivots+class_expansion_sparse+cell_references+"
        "canonical_json_metadata"
    )
    for item in manifest["metadata"]["classes"]:
        assert item["constraint_pattern_sha256"] == "c" * 64
        assert item["expansion_pattern_sha256"] == _expansion().pattern_sha256
        assert item["constraint_pattern_sha256"] != item["expansion_pattern_sha256"]
    assert manifest["metadata"]["factors"][0]["determinism_method"] == (
        "repeated_factorization_same_matrix"
    )
    tampered = json.loads(manifest_path.read_text(encoding="utf-8"))
    tampered["metadata"]["classes"][0]["solve_residual"] += 1.0
    tampered_path = manifest_path.with_name("tampered_manifest.json")
    tampered_path.write_bytes(
        json.dumps(
            tampered,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    with pytest.raises(ValueError, match="class/factor solve residual"):
        load_h2a_r2_factor_store(
            tampered_path,
            task037_extra_h2a_r2=True,
        )

    original_load = np.load

    def checked_load(*args, **kwargs):
        assert kwargs.get("allow_pickle") is False
        return original_load(*args, **kwargs)

    monkeypatch.setattr(np, "load", checked_load)
    loaded = load_h2a_r2_factor_store(
        manifest_path,
        task037_extra_h2a_r2=True,
    )
    assert loaded.audit["class_count"] == 2
    assert loaded.audit["unique_factor_count"] == 1
    assert loaded.audit["retained_payload_bytes"] == manifest["payload"][
        "retained_payload_bytes"
    ]
    assert loaded.audit["factor_plus_metadata_bytes"] == manifest["payload"][
        "factor_plus_metadata_bytes"
    ]
    assert loaded.classes[0].constraint_pattern_sha256 == "c" * 64
    assert (
        loaded.classes[0].expansion_pattern_sha256
        == loaded.classes[0].expansion.pattern_sha256
    )
    rhs = np.asarray((0.2 + 0.8j, 1.1 - 0.3j), dtype=np.complex128)
    assert np.array_equal(loaded.solve(0, rhs), store.solve(0, rhs))
    assert np.array_equal(loaded.solve(1, rhs), store.solve(1, rhs))


def test_r2_factor_store_rejects_factor_file_corruption(tmp_path):
    store, _consumed = _build_store()
    manifest_path = write_h2a_r2_factor_store(
        store,
        tmp_path / "factor_store",
        task037_extra_h2a_r2=True,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    factor_path = manifest_path.parent / manifest["metadata"]["factors"][0][
        "values_path"
    ]
    original = factor_path.read_bytes()
    factor_path.write_bytes(original[:-1] + bytes((original[-1] ^ 1,)))
    with pytest.raises(ValueError, match="file SHA"):
        load_h2a_r2_factor_store(
            manifest_path,
            task037_extra_h2a_r2=True,
        )
    assert hashlib.sha256(original).hexdigest() != hashlib.sha256(
        factor_path.read_bytes()
    ).hexdigest()


def test_r2_factor_store_closes_cell_rows_against_expansion():
    expansion = _expansion()
    with pytest.raises(ValueError, match="independent row count"):
        build_h2a_r2_factor_store(
            (
                H2AR2ClassInput(
                    class_id=0,
                    class_key_sha256="a" * 64,
                    constraint_pattern_sha256="c" * 64,
                    expansion_pattern_sha256=expansion.pattern_sha256,
                    expansion=expansion,
                    transformed_matrix=_matrix(),
                ),
            ),
            (H2AR2CellReference(0, np.asarray((100,), dtype=np.int64)),),
            identity=_identity(),
            task037_extra_h2a_r2=True,
        )
