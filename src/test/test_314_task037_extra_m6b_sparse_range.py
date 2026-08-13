from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

import benchmarks.run_task037_extra_m6b as runner
from src.solvers.hcurl_fullspace_dtn import (
    FullspaceDtnCarrier,
    FullspaceDtnModeEntries,
    build_fullspace_dtn_action,
)
from src.solvers.hcurl_m6b_sparse_range import (
    M6B_W1_NORMAL_CLOSURE_LIMIT,
    SparseM6BRangeCarrier,
    _array_sha256,
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

    def adjoint(values: np.ndarray) -> np.ndarray:
        return np.asarray(operator.conjugate().T @ values, dtype=np.complex128)

    carrier = SparseM6BRangeCarrier.from_action(
        basis,
        action,
        hermitian_action=adjoint,
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
    correction = carrier.apply(np.asarray(rhs, dtype=np.complex128))
    z_dense = np.zeros((90, 75), dtype=np.complex128)
    z_dense[np.arange(75), np.arange(75)] = [
        1.0 + 0.01j * (column + 1) for column in range(75)
    ]
    v_dense = operator @ z_dense
    coefficients = np.linalg.lstsq(v_dense, rhs, rcond=None)[0]
    expected_correction = z_dense @ coefficients
    assert np.linalg.norm(correction - expected_correction) / np.linalg.norm(expected_correction) <= 1.0e-11
    assert carrier.rank == 75
    assert carrier.normal_closure <= M6B_W1_NORMAL_CLOSURE_LIMIT
    assert carrier.audit["mpi_scope"] == "MPI1"
    assert carrier.audit["factor_audit"]["rank"] == 75
    assert carrier.audit["dense_nrows_x_columns_retained"] is False
    assert carrier.audit["dense_nrows_x_columns_bytes"] == 0
    correction_repeat = carrier.apply(np.asarray(rhs, dtype=np.complex128))
    assert np.array_equal(correction, correction_repeat)


def test_m6b_sparse_range_cold_store_mmap_and_fail_closed(tmp_path: Path):
    carrier, _operator, _ = _carrier()
    manifest = carrier.save(tmp_path / "range_store")
    loaded = load_sparse_m6b_range_carrier(
        manifest,
        comm=MPI.COMM_SELF,
        hermitian_action=lambda values: np.asarray(values, dtype=np.complex128),
    )
    assert loaded.audit["mmap_readonly"] is True
    assert not hasattr(loaded, "_z")
    assert not hasattr(loaded, "_v")
    assert not any(
        "scipy.sparse" in type(value).__module__
        for value in vars(loaded).values()
    )
    assert {
        path.name for path in (tmp_path / "range_store").iterdir() if path.is_file()
    } == {
        "manifest.json",
        "z_data.npy",
        "z_indices.npy",
        "z_indptr.npy",
        "r_factor.npy",
    }
    for array in (
        loaded.z_data,
        loaded.z_indices,
        loaded.z_indptr,
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
    expected_sparse_temporaries = (
        2
        * loaded.audit["max_z_column_nnz"]
        * np.dtype(np.complex128).itemsize
    )
    assert loaded.audit["bounded_work_components"][
        "two_max_sparse_column_temporaries_bytes"
    ] == expected_sparse_temporaries
    assert loaded.audit["bounded_work_bytes"] == sum(
        loaded.audit["bounded_work_components"].values()
    )
    assert loaded.audit["az_column_sha256_aggregate"] == carrier.audit[
        "az_column_sha256_aggregate"
    ]
    assert loaded.audit["az_v_retained"] is False
    assert loaded.audit["retained_az_bytes"] == 0

    missing = tmp_path / "missing_key"
    shutil.copytree(tmp_path / "range_store", missing)
    missing_manifest = json.loads((missing / "manifest.json").read_text())
    del missing_manifest["arrays"]["z_indptr"]
    missing_manifest["evidence_sha256"] = hashlib.sha256(
        json.dumps(
            {key: value for key, value in missing_manifest.items() if key != "evidence_sha256"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    (missing / "manifest.json").write_text(json.dumps(missing_manifest))
    with pytest.raises(ValueError, match="array set"):
        load_sparse_m6b_range_carrier(
            missing / "manifest.json",
            comm=MPI.COMM_SELF,
            hermitian_action=lambda values: np.asarray(values, dtype=np.complex128),
        )

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
            missing_audit / "manifest.json",
            comm=MPI.COMM_SELF,
            hermitian_action=lambda values: np.asarray(values, dtype=np.complex128),
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
            tampered_factor_audit / "manifest.json",
            comm=MPI.COMM_SELF,
            hermitian_action=lambda values: np.asarray(values, dtype=np.complex128),
        )

    tampered = tmp_path / "tampered"
    shutil.copytree(tmp_path / "range_store", tampered)
    values = np.load(tampered / "z_data.npy", allow_pickle=False)
    values = np.array(values, copy=True)
    values[0] += 1.0
    np.save(tampered / "z_data.npy", values, allow_pickle=False)
    with pytest.raises(ValueError, match="file SHA"):
        load_sparse_m6b_range_carrier(
            tampered / "manifest.json",
            comm=MPI.COMM_SELF,
            hermitian_action=lambda values: np.asarray(values, dtype=np.complex128),
        )


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
    assert runner.M6B_W1_SCHEMA == "task037.extra.m6b.sparse-range-builder.v2"
    assert (
        f"{runner.M6B_W1_SCHEMA}.progress.v1"
        == "task037.extra.m6b.sparse-range-builder.v2.progress.v1"
    )
    assert runner.M6B_W1_BASE_PREDICTED_LIVE_SET_BYTES == 1_657_665_813
    assert runner.M6B_W1_PREDICTED_LIVE_SET_LIMIT_BYTES == 1_750_000_000


def test_m6b_w1_cache_delta_records_content_changes():
    before = {
        "entries": [
            {"path": "same.bin", "bytes": 3, "sha256": "a" * 64},
            {"path": "removed.bin", "bytes": 5, "sha256": "b" * 64},
        ]
    }
    after_forward = {
        "entries": [
            {"path": "same.bin", "bytes": 4, "sha256": "c" * 64},
            {"path": "added.bin", "bytes": 7, "sha256": "d" * 64},
        ]
    }
    snapshots = runner._m6b_w1_cache_deltas(
        before,
        after_forward,
        after_forward,
        after_forward,
        after_forward,
    )
    assert set(snapshots) == {
        "forward_delta",
        "adjoint_staging_delta",
        "surface_delta",
        "final_delta",
    }
    assert snapshots["forward_delta"] == {
        "added": [{"path": "added.bin", "bytes": 7, "sha256": "d" * 64}],
        "removed": [{"path": "removed.bin", "bytes": 5, "sha256": "b" * 64}],
        "changed": [
            {
                "path": "same.bin",
                "before": {"path": "same.bin", "bytes": 3, "sha256": "a" * 64},
                "after": {"path": "same.bin", "bytes": 4, "sha256": "c" * 64},
            }
        ],
    }
    for key in ("adjoint_staging_delta", "surface_delta", "final_delta"):
        assert snapshots[key] == {"added": [], "removed": [], "changed": []}


def test_m6b_sparse_range_keeps_exact_tiny_nonzero():
    basis = _basis()

    def action(vector: SimpleNamespace) -> np.ndarray:
        values = np.zeros(90, dtype=np.complex128)
        values[vector.indices] = vector.values
        values[89] = 1.0e-300 + 0.0j
        return values

    def adjoint(values: np.ndarray) -> np.ndarray:
        return np.asarray(values, dtype=np.complex128)

    carrier = SparseM6BRangeCarrier.from_action(
        basis,
        action,
        hermitian_action=adjoint,
        global_rows=90,
        ownership_range=(0, 90),
        comm=MPI.COMM_SELF,
        identity=_identity(basis),
    )
    assert carrier.audit["az_column_count"] == 75
    assert carrier._manifest["az_column_sha256"][0] == _array_sha256(action(basis[0]))


def test_m6b_fullspace_dtn_adjoint_identity():
    def identity(index: int) -> dict[str, object]:
        return {
            "schema": "PortMode3D",
            "mode_index": index,
            "side": "top",
            "m": index,
            "n": 0,
            "polarization": "s",
            "alpha": 0.0,
            "gamma": 0.0,
            "beta": 1.0,
            "k_vector": [1.0, 0.0, 0.1],
            "e_vector": [0.0, 1.0, 0.0],
            "power_per_unit_amplitude": 1.0,
            "rayleigh_warning": False,
            "projection_denominator": 1.0 + 0.2j,
            "traction_vector": [1.0 + 0.1j, 0.2 - 0.3j],
            "refractive_index": 1.0,
            "vertical_sign": 1,
            "h_vector": [0.1, 0.2, 0.3],
            "electric_tangential_norm_sq": 1.0,
            "propagating": True,
        }

    entries = (
        FullspaceDtnModeEntries(
            (0,),
            np.asarray([0, 2], dtype=np.int32),
            np.asarray([1.0 + 0.2j, -0.3 + 0.4j]),
            np.asarray([1, 3], dtype=np.int32),
            np.asarray([0.5 - 0.1j, 0.2 + 0.3j]),
            identity(0),
        ),
        FullspaceDtnModeEntries(
            (1,),
            np.asarray([1, 3], dtype=np.int32),
            np.asarray([0.4 - 0.2j, 0.7 + 0.1j]),
            np.asarray([0, 2], dtype=np.int32),
            np.asarray([-0.2 + 0.5j, 0.6 - 0.4j]),
            identity(1),
        ),
    )
    carrier = FullspaceDtnCarrier(
        entries,
        global_rows=4,
        ownership_range=(0, 4),
        expected_mode_count=2,
        comm=MPI.COMM_SELF,
    )
    action = build_fullspace_dtn_action(carrier, comm=MPI.COMM_SELF)
    x = PETSc.Vec().createSeq(4, comm=PETSc.COMM_SELF)
    y = PETSc.Vec().createSeq(4, comm=PETSc.COMM_SELF)
    forward = x.duplicate()
    adjoint = x.duplicate()
    x.getArray()[:] = [1.0 + 0.2j, -0.4 + 0.1j, 0.3 - 0.5j, 0.7 + 0.6j]
    y.getArray()[:] = [-0.2 + 0.3j, 0.4 - 0.6j, 0.8 + 0.1j, -0.5 + 0.2j]
    try:
        action.apply(x, forward)
        action.apply_hermitian(y, adjoint)
        assert np.isclose(
            np.vdot(forward.getArray(readonly=True), y.getArray(readonly=True)),
            np.vdot(x.getArray(readonly=True), adjoint.getArray(readonly=True)),
            rtol=1.0e-13,
            atol=1.0e-13,
        )
        assert action.audit["modal_allreduce_count_per_hermitian_apply"] == 1
    finally:
        adjoint.destroy()
        forward.destroy()
        y.destroy()
        x.destroy()
        action.destroy()
