from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI

import benchmarks.run_task037_extra_m6b as runner
from src.solvers.hcurl_m6b_sparse_range import (
    M6B_W1_NORMAL_CLOSURE_LIMIT,
    SparseM6BRangeCarrier,
    basis_manifest_from_vectors,
    load_sparse_m6b_range_carrier,
)


def _basis(local_rows: int = 90) -> tuple[SimpleNamespace, ...]:
    result = []
    for column in range(75):
        rows = np.asarray([column], dtype=np.int64)
        values = np.asarray([1.0 + 0.01j * (column + 1)], dtype=np.complex128)
        result.append(SimpleNamespace(indices=rows, values=values, storage_bytes=32))
    return tuple(result)


def _identity(basis: tuple[SimpleNamespace, ...]) -> dict[str, object]:
    manifest = basis_manifest_from_vectors(basis)
    manifest_sha = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "source_sha": "a" * 40,
        "operator_identity": "A=synthetic-fullspace",
        "basis_manifest_sha256": manifest_sha,
        "basis_manifest": manifest,
    }


def _carrier() -> tuple[SparseM6BRangeCarrier, np.ndarray, np.ndarray]:
    local_rows = 90
    rng = np.random.default_rng(314)
    operator = rng.standard_normal((local_rows, local_rows)) + 1j * rng.standard_normal(
        (local_rows, local_rows)
    )
    operator += 8.0 * np.eye(local_rows)
    basis = _basis(local_rows)

    def action(vector: SimpleNamespace) -> np.ndarray:
        values = np.zeros(local_rows, dtype=np.complex128)
        values[vector.indices] = vector.values
        return np.asarray(operator @ values, dtype=np.complex128)

    carrier = SparseM6BRangeCarrier.from_action(
        basis,
        action,
        global_rows=local_rows,
        ownership_range=(0, local_rows),
        comm=MPI.COMM_SELF,
        identity=_identity(basis),
    )
    return carrier, operator, np.asarray(basis[0].values, dtype=np.complex128)


def test_m6b_sparse_range_matches_dense_lstsq_and_repeats():
    carrier, operator, _ = _carrier()
    rng = np.random.default_rng(315)
    rhs = rng.standard_normal(90) + 1j * rng.standard_normal(90)
    correction, represented = carrier.apply(np.asarray(rhs, dtype=np.complex128))
    z_dense = np.zeros((90, 75), dtype=np.complex128)
    z_dense[np.arange(75), np.arange(75)] = [
        1.0 + 0.01j * (column + 1) for column in range(75)
    ]
    v_dense = operator @ z_dense
    coefficients = np.linalg.lstsq(v_dense, rhs, rcond=None)[0]
    expected_correction = z_dense @ coefficients
    expected_action = v_dense @ coefficients
    assert np.linalg.norm(correction - expected_correction) / np.linalg.norm(expected_correction) <= 1.0e-11
    assert np.linalg.norm(represented - expected_action) / np.linalg.norm(expected_action) <= 1.0e-11
    assert carrier.rank == 75
    assert carrier.normal_closure <= M6B_W1_NORMAL_CLOSURE_LIMIT
    assert carrier.audit["mpi_scope"] == "MPI1"
    assert carrier.audit["factor_audit"]["rank"] == 75
    assert carrier.audit["dense_nrows_x_columns_retained"] is False
    assert carrier.audit["dense_nrows_x_columns_bytes"] == 0
    correction_repeat, action_repeat = carrier.apply(np.asarray(rhs, dtype=np.complex128))
    assert np.array_equal(correction, correction_repeat)
    assert np.array_equal(represented, action_repeat)


def test_m6b_sparse_range_cold_store_mmap_and_fail_closed(tmp_path: Path):
    carrier, _operator, _ = _carrier()
    manifest = carrier.save(tmp_path / "range_store")
    loaded = load_sparse_m6b_range_carrier(manifest, comm=MPI.COMM_SELF)
    assert loaded.audit["mmap_readonly"] is True
    assert not hasattr(loaded, "_z")
    assert not hasattr(loaded, "_v")
    for array in (
        loaded.z_data,
        loaded.z_indices,
        loaded.z_indptr,
        loaded.v_data,
        loaded.v_indices,
        loaded.v_indptr,
        loaded.r_factor,
    ):
        assert isinstance(array, np.memmap)
        assert array.flags.writeable is False
    assert loaded.audit["retained_plus_work_bytes"] == (
        loaded.audit["retained_total_bytes"] + loaded.audit["bounded_work_bytes"]
    )
    assert sum(loaded.audit["retained_components"].values()) == loaded.audit[
        "retained_total_bytes"
    ]
    expected_sparse_temporaries = 2 * max(
        loaded.audit["max_z_column_nnz"], loaded.audit["max_v_column_nnz"]
    ) * np.dtype(np.complex128).itemsize
    assert loaded.audit["bounded_work_components"][
        "two_max_sparse_column_temporaries_bytes"
    ] == expected_sparse_temporaries
    assert loaded.audit["bounded_work_bytes"] == sum(
        loaded.audit["bounded_work_components"].values()
    )
    assert loaded.audit["v_column_sha256_aggregate"] == carrier.audit[
        "v_column_sha256_aggregate"
    ]

    missing = tmp_path / "missing_key"
    shutil.copytree(tmp_path / "range_store", missing)
    missing_manifest = json.loads((missing / "manifest.json").read_text())
    del missing_manifest["arrays"]["v_indptr"]
    missing_manifest["evidence_sha256"] = hashlib.sha256(
        json.dumps(
            {key: value for key, value in missing_manifest.items() if key != "evidence_sha256"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    (missing / "manifest.json").write_text(json.dumps(missing_manifest))
    with pytest.raises(ValueError, match="array set"):
        load_sparse_m6b_range_carrier(missing / "manifest.json", comm=MPI.COMM_SELF)

    missing_audit = tmp_path / "missing_factor_audit"
    shutil.copytree(tmp_path / "range_store", missing_audit)
    missing_audit_manifest = json.loads(
        (missing_audit / "manifest.json").read_text()
    )
    del missing_audit_manifest["factor_audit"]
    missing_audit_manifest["evidence_sha256"] = hashlib.sha256(
        json.dumps(
            {
                key: value
                for key, value in missing_audit_manifest.items()
                if key != "evidence_sha256"
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    (missing_audit / "manifest.json").write_text(
        json.dumps(missing_audit_manifest)
    )
    with pytest.raises(ValueError, match="factor audit"):
        load_sparse_m6b_range_carrier(
            missing_audit / "manifest.json", comm=MPI.COMM_SELF
        )

    tampered_factor_audit = tmp_path / "tampered_factor_audit"
    shutil.copytree(tmp_path / "range_store", tampered_factor_audit)
    tampered_factor_manifest = json.loads(
        (tampered_factor_audit / "manifest.json").read_text()
    )
    tampered_factor_manifest["factor_audit"]["r_singular_max"] *= 1.01
    tampered_factor_manifest["evidence_sha256"] = hashlib.sha256(
        json.dumps(
            {
                key: value
                for key, value in tampered_factor_manifest.items()
                if key != "evidence_sha256"
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    (tampered_factor_audit / "manifest.json").write_text(
        json.dumps(tampered_factor_manifest)
    )
    with pytest.raises(ValueError, match="does not match R"):
        load_sparse_m6b_range_carrier(
            tampered_factor_audit / "manifest.json", comm=MPI.COMM_SELF
        )

    tampered = tmp_path / "tampered"
    shutil.copytree(tmp_path / "range_store", tampered)
    values = np.load(tampered / "v_data.npy", allow_pickle=False)
    values = np.array(values, copy=True)
    values[0] += 1.0
    np.save(tampered / "v_data.npy", values, allow_pickle=False)
    with pytest.raises(ValueError, match="file SHA"):
        load_sparse_m6b_range_carrier(tampered / "manifest.json", comm=MPI.COMM_SELF)


def test_m6b_w1_builder_command_is_parameterized():
    args = runner._parser().parse_args(
        [
            "m6b-w1-builder",
            "--run-dir",
            "/tmp/m6b-w1-test",
            "--jit-cache-source",
            "/tmp/run5/jit_cache",
        ]
    )
    assert args.command == "m6b-w1-builder"
    assert runner.M6B_W1_BASE_PREDICTED_LIVE_SET_BYTES == 1_657_665_813
    assert runner.M6B_W1_PREDICTED_LIVE_SET_LIMIT_BYTES == 1_750_000_000


def test_m6b_sparse_range_keeps_exact_tiny_nonzero():
    basis = _basis()

    def action(vector: SimpleNamespace) -> np.ndarray:
        values = np.zeros(90, dtype=np.complex128)
        values[vector.indices] = vector.values
        values[89] = 1.0e-300 + 0.0j
        return values

    carrier = SparseM6BRangeCarrier.from_action(
        basis,
        action,
        global_rows=90,
        ownership_range=(0, 90),
        comm=MPI.COMM_SELF,
        identity=_identity(basis),
    )
    assert np.any(carrier.v_data == np.complex128(1.0e-300))
