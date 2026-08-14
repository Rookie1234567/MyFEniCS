from __future__ import annotations

import hashlib
import json
import shutil
from copy import deepcopy
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
from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import (
    H2BM6BProjectedRangePC,
    H2BM6BShiftedPatchPC,
    H2BM6BShiftedRangePC,
)
from src.solvers.hcurl_h2b_m6b_shifted_lu_store import (
    build_h2b_m6b_shifted_lu_factor,
    build_h2b_m6b_shifted_lu_patch_store,
    load_h2b_m6b_shifted_lu_patch_store,
    write_h2b_m6b_shifted_lu_patch_store,
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


def _w2_local_store(tmp_path: Path):
    factor = build_h2b_m6b_shifted_lu_factor(
        np.eye(90, dtype=np.complex128), task037_extra_m6b=True
    )
    store = build_h2b_m6b_shifted_lu_patch_store(
        (factor,),
        ({
            "neighborhood_id": 0,
            "key_sha256": "8" * 64,
            "cell_ordinals": [0],
            "multiplicity": 1,
            "factor_id": 0,
        },),
        np.asarray([0], dtype=np.int32),
        np.asarray([0, 90], dtype=np.int64),
        np.arange(90, dtype=np.int64),
        identity={"source_provenance": "w2-synthetic", "beta": 1.0},
        task037_extra_m6b=True,
    )
    manifest = write_h2b_m6b_shifted_lu_patch_store(
        store, tmp_path / "w2_local_store", task037_extra_m6b=True
    )
    return load_h2b_m6b_shifted_lu_patch_store(
        manifest, task037_extra_m6b=True
    )


def test_m6b_w2_local_then_range_synthetic_is_exact_and_repeatable(tmp_path: Path):
    basis = _basis()

    def identity_action(vector: SimpleNamespace) -> np.ndarray:
        values = np.zeros(90, dtype=np.complex128)
        values[vector.indices] = vector.values
        return values

    carrier = SparseM6BRangeCarrier.from_action(
        basis,
        identity_action,
        hermitian_action=lambda values: np.asarray(values, dtype=np.complex128),
        global_rows=90,
        ownership_range=(0, 90),
        comm=MPI.COMM_SELF,
        identity=_identity(basis),
    )
    local = H2BM6BShiftedPatchPC(
        _w2_local_store(tmp_path),
        global_row_count=90,
        shifted_action=lambda values: np.asarray(2.0 * values, dtype=np.complex128),
        task037_extra_m6b=True,
    )
    composite = H2BM6BShiftedRangePC(
        local,
        carrier,
        lambda values: np.array(values, dtype=np.complex128, copy=True),
        global_row_count=90,
        task037_extra_m6b=True,
    )
    rhs = np.zeros(90, dtype=np.complex128)
    rhs[:75] = np.arange(75, dtype=np.float64) + 1j * (1.0 + np.arange(75))
    correction, measurement = composite.apply_with_measurement(rhs)
    repeat, repeat_measurement = composite.apply_with_measurement(rhs)
    production = composite.apply(rhs)
    local_correction = local.apply(rhs)
    expected = local_correction + carrier.apply(rhs - local_correction)
    assert np.array_equal(correction, production)
    assert np.array_equal(correction, expected)
    assert not np.array_equal(local_correction, rhs)
    assert np.array_equal(correction, repeat)
    assert measurement == repeat_measurement
    assert measurement["rho_local_only"] == pytest.approx(0.5)
    assert measurement["rho_composed"] <= measurement["rho_local_only"] + 1.0e-12
    assert measurement["linear_action_closure"] <= 1.0e-11
    assert measurement["normal_projected_component_ratio"] <= 1.0e-11
    assert measurement["action_counts"] == {
        "local_apply": 1,
        "physical_outer_action": 5,
        "range_apply": 3,
    }
    audit = composite.audit
    assert audit["fixed_order"] == "local_then_physical_residual_then_range"
    assert audit["composition_incremental_bytes"] == 2 * 90 * 16
    assert audit["local_bounded_work_bytes"] == local.audit[
        "bounded_apply_workspace_bytes"
    ]
    assert audit["bounded_work_bytes"] == max(
        audit["local_bounded_work_bytes"],
        audit["range_bounded_work_bytes"] + audit["composition_incremental_bytes"],
    )
    assert audit["global_matrix"] is False
    assert audit["static_condensation"] is False
    assert audit["trace_slab_pc"] is False


def test_m6b_w2r_projected_range_complement_is_exact_and_fail_closed(
    tmp_path: Path,
):
    basis = _basis()

    def identity_action(vector: SimpleNamespace) -> np.ndarray:
        values = np.zeros(90, dtype=np.complex128)
        values[vector.indices] = vector.values
        return values

    carrier = SparseM6BRangeCarrier.from_action(
        basis,
        identity_action,
        hermitian_action=lambda values: np.asarray(values, dtype=np.complex128),
        global_rows=90,
        ownership_range=(0, 90),
        comm=MPI.COMM_SELF,
        identity=_identity(basis),
    )
    local = H2BM6BShiftedPatchPC(
        _w2_local_store(tmp_path / "projected"),
        global_row_count=90,
        shifted_action=lambda values: np.asarray(2.0j * values, dtype=np.complex128),
        task037_extra_m6b=True,
    )
    projected = H2BM6BProjectedRangePC(
        local,
        carrier,
        lambda values: np.array(values, dtype=np.complex128, copy=True),
        global_row_count=90,
        task037_extra_m6b=True,
    )
    rhs = np.zeros(90, dtype=np.complex128)
    rhs[:75] = np.arange(75, dtype=np.float64) + 1j * (1.0 + np.arange(75))
    rhs[75:] = 1.0 - 0.5j

    correction, measurement = projected.apply_with_measurement(rhs)
    repeat, repeat_measurement = projected.apply_with_measurement(rhs)
    production = projected.apply(rhs)
    assert np.allclose(correction, rhs, rtol=0.0, atol=1.0e-13)
    assert np.array_equal(correction, production)
    assert np.array_equal(correction, repeat)
    assert measurement == repeat_measurement
    assert measurement["alpha"][0] == pytest.approx(0.0, abs=1.0e-14)
    assert measurement["alpha"][1] == pytest.approx(2.0, abs=1.0e-14)
    assert measurement["rho_projected"] <= measurement["rho_range_only"] + 1.0e-12
    assert measurement["linear_action_closure"] <= 1.0e-11
    assert measurement["normal_projected_component_ratio"] <= 1.0e-11
    assert measurement["complement_optimality"] <= 1.0e-11
    assert measurement["action_counts"] == {
        "local_apply": 1,
        "physical_outer_action": 5,
        "range_apply": 3,
    }
    assert not np.array_equal(local.apply(rhs), rhs)
    audit = projected.audit
    assert audit["fixed_order"] == "projected_range_complement"
    assert audit["production_action_counts"] == {
        "local_apply": 1,
        "physical_outer_action": 3,
        "range_apply": 2,
    }
    assert audit["projected_incremental_bytes"] == 8 * 90 * 16
    assert audit["bounded_work_bytes"] == max(
        audit["local_bounded_work_bytes"],
        audit["range_bounded_work_bytes"] + audit["projected_incremental_bytes"],
    )
    assert audit["global_matrix"] is False
    assert audit["static_condensation"] is False
    assert audit["trace_slab_pc"] is False

    unit_basis = tuple(
        SimpleNamespace(
            indices=np.asarray([column], dtype=np.int64),
            values=np.asarray([1.0 + 0.0j], dtype=np.complex128),
            storage_bytes=32,
        )
        for column in range(75)
    )
    unit_carrier = SparseM6BRangeCarrier.from_action(
        unit_basis,
        identity_action,
        hermitian_action=lambda values: np.asarray(values, dtype=np.complex128),
        global_rows=90,
        ownership_range=(0, 90),
        comm=MPI.COMM_SELF,
        identity=_identity(unit_basis),
    )
    zero_local = H2BM6BShiftedPatchPC(
        _w2_local_store(tmp_path / "zero_local"),
        global_row_count=90,
        shifted_action=lambda values: np.asarray(2.0j * values, dtype=np.complex128),
        task037_extra_m6b=True,
    )
    rhs_in_range = np.zeros(90, dtype=np.complex128)
    rhs_in_range[:75] = 1.0 + 0.5j
    local_probe = zero_local.apply(rhs_in_range)
    assert np.all(np.isfinite(local_probe)) and np.linalg.norm(local_probe) > 0.0
    projected_zero = H2BM6BProjectedRangePC(
        zero_local,
        unit_carrier,
        lambda values: np.array(values, dtype=np.complex128, copy=True),
        global_row_count=90,
        task037_extra_m6b=True,
    )
    with pytest.raises(FloatingPointError, match="W2R projected denominator"):
        projected_zero.apply(rhs_in_range)

    bad_local = H2BM6BShiftedPatchPC(
        _w2_local_store(tmp_path / "bad_beta"),
        global_row_count=90,
        shifted_action=lambda values: np.asarray(values, dtype=np.complex128),
        task037_extra_m6b=True,
    )
    bad_local._audit["beta"] = 0.5
    accepted_beta05 = H2BM6BProjectedRangePC(
        bad_local,
        carrier,
        lambda values: np.asarray(values, dtype=np.complex128),
        global_row_count=90,
        task037_extra_m6b=True,
        expected_local_beta=0.5,
    )
    assert accepted_beta05.audit["local_beta"] == 0.5
    with pytest.raises(ValueError, match="expected beta"):
        H2BM6BProjectedRangePC(
            bad_local,
            carrier,
            lambda values: np.asarray(values, dtype=np.complex128),
            global_row_count=90,
            task037_extra_m6b=True,
            expected_local_beta=0.75,
        )
    with pytest.raises(ValueError, match="carrier identity"):
        H2BM6BProjectedRangePC(
            bad_local,
            carrier,
            lambda values: np.asarray(values, dtype=np.complex128),
            global_row_count=90,
            task037_extra_m6b=True,
        )


def test_m6b_w2_rejects_non_beta_one_local_pc(tmp_path: Path):
    local = H2BM6BShiftedPatchPC(
        _w2_local_store(tmp_path / "bad"),
        global_row_count=90,
        shifted_action=lambda values: np.asarray(values, dtype=np.complex128),
        task037_extra_m6b=True,
    )
    local._audit["beta"] = 0.5
    carrier, _operator, _basis_value = _carrier()
    with pytest.raises(ValueError, match="carrier identity"):
        H2BM6BShiftedRangePC(
            local,
            carrier,
            lambda values: np.asarray(values, dtype=np.complex128),
            global_row_count=90,
            task037_extra_m6b=True,
        )


def test_m6b_w2_parser_and_fixed_gate_fail_closed():
    parser_prefix = [
        "m6b-w2-diagnostic",
        "--run-dir",
        "/tmp/w2",
        "--factor-authority-dir",
        "/tmp/factor",
        "--wave-authority-dir",
        "/tmp/wave",
        "--jit-cache-source",
        "/tmp/jit",
    ]
    with pytest.raises(SystemExit):
        runner._parser().parse_args(parser_prefix)
    with pytest.raises(SystemExit):
        runner._parser().parse_args(
            parser_prefix
            + [
                "--expected-source-sha",
                "A" * 40,
                "--w0-authority-file",
                "/tmp/w0.json",
            ]
        )
    args = runner._parser().parse_args(
        parser_prefix
        + [
            "--expected-source-sha",
            "a" * 40,
            "--w0-authority-file",
            "/tmp/w0.json",
        ]
    )
    assert args.command == "m6b-w2-diagnostic"
    assert args.expected_source_sha == "a" * 40
    assert args.w0_authority_file == "/tmp/w0.json"
    w2r_args = runner._parser().parse_args(
        ["m6b-w2r-diagnostic", *parser_prefix[1:]]
        + [
            "--expected-source-sha",
            "a" * 40,
            "--w0-authority-file",
            "/tmp/w0.json",
        ]
    )
    assert w2r_args.command == "m6b-w2r-diagnostic"
    measurements = {}
    for key in ("20", "100", "150", "200"):
        measurements[key] = {
            "schema": "task037.extra.h2b.m6b.shifted-range-pc.v1",
            "iteration": int(key),
            "residual_array_sha256": runner.M6B_W2_RESIDUAL_ARRAY_SHAS[key],
            "residual_artifact": {
                "path": f"m6b_iter{key}_residual.npy",
                "absolute_path": f"/tmp/m6b_iter{key}_residual.npy",
                "present": True,
                "bytes": 1,
                "sha256": "c" * 64,
            },
            "finite": True,
            "rho_local_only": 1.0,
            "rho_range_only": runner.M6B_W2_RANGE_RHO_AUTHORITY[key],
            "rho_composed": 0.5,
            "linear_action_closure": 0.0,
            "normal_projected_component_ratio": 0.0,
            "action_counts": {
                "local_apply": 1,
                "physical_outer_action": 5,
                "range_apply": 3,
            },
            "final_correction_sha256": "a" * 64,
            "correction_sha256": "a" * 64,
            "repeat_correction_sha256": "a" * 64,
            "repeat_identical": True,
        }
        for field in (
            "rhs_sha256",
            "local_correction_sha256",
            "local_action_sha256",
            "local_residual_sha256",
            "range_only_correction_sha256",
            "range_only_action_sha256",
            "range_correction_sha256",
            "range_action_sha256",
            "final_action_sha256",
            "final_residual_sha256",
            "final_range_correction_sha256",
            "final_range_action_sha256",
        ):
            measurements[key][field] = "a" * 64
        measurements[key]["rhs_sha256"] = "a" * 64
    assert runner._m6b_w2_gate(measurements)["pass"] is True
    missing = dict(measurements)
    missing.pop("100")
    assert runner._m6b_w2_gate(missing)["pass"] is False
    nonfinite = {key: dict(value) for key, value in measurements.items()}
    nonfinite["20"]["rho_composed"] = float("nan")
    assert runner._m6b_w2_gate(nonfinite)["pass"] is False


def test_m6b_w2r_gate_missing_and_nonfinite_fail_closed():
    prediction = runner._m6b_w2r_predicted_live_set()
    assert prediction["predicted_live_set_bytes"] == 1_723_301_083
    assert prediction["projected_full_vector_count"] == 8
    assert prediction["is_measurement"] is False
    assert prediction["derived_not_measured"] is True
    assert prediction["gate"] is True
    measurements = {}
    hash_fields = (
        "rhs_sha256",
        "local_correction_sha256",
        "local_action_sha256",
        "range_only_correction_sha256",
        "range_only_action_sha256",
        "range_correction_sha256",
        "range_action_sha256",
        "correction_sha256",
        "final_correction_sha256",
        "repeat_correction_sha256",
        "represented_action_sha256",
        "final_action_sha256",
        "final_residual_sha256",
        "final_range_correction_sha256",
        "final_range_action_sha256",
    )
    for key in ("20", "100", "150", "200"):
        record = {
            "schema": "task037.extra.h2b.m6b.projected-range-pc.v1",
            "iteration": int(key),
            "residual_array_sha256": runner.M6B_W2_RESIDUAL_ARRAY_SHAS[key],
            "residual_artifact": {
                "path": f"m6b_iter{key}_residual.npy",
                "absolute_path": f"/tmp/m6b_iter{key}_residual.npy",
                "bytes": 1,
                "sha256": "c" * 64,
                "present": True,
            },
            "finite": True,
            "rho_local_only": 1.0,
            "rho_range_only": runner.M6B_W2_RANGE_RHO_AUTHORITY[key],
            "rho_projected": 0.5,
            "linear_action_closure": 0.0,
            "normal_projected_component_ratio": 0.0,
            "complement_optimality": 0.0,
            "alpha": [1.0, 0.0],
            "projection_denominator": [1.0, 0.0],
            "action_counts": {
                "local_apply": 1,
                "physical_outer_action": 5,
                "range_apply": 3,
            },
            "repeat_identical": True,
        }
        record.update({field: "a" * 64 for field in hash_fields})
        measurements[key] = record
    assert runner._m6b_w2r_gate(measurements)["pass"] is True
    missing = deepcopy(measurements)
    del missing["100"]["rho_projected"]
    assert runner._m6b_w2r_gate(missing)["pass"] is False
    nonfinite = deepcopy(measurements)
    nonfinite["150"]["complement_optimality"] = float("nan")
    assert runner._m6b_w2r_gate(nonfinite)["pass"] is False
    over_gate = deepcopy(measurements)
    over_gate["20"]["rho_projected"] = 0.91
    assert runner._m6b_w2r_gate(over_gate)["pass"] is False


def test_m6b_w2r_old_negative_nested_evidence_is_fail_closed():
    source = {
        "source_commit_full_sha": runner.M6B_W2R_OLD_NEGATIVE_SOURCE_SHA,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }
    checks = {
        "fixed_iterations": True,
        "residual_artifacts": True,
        "finite_deterministic": True,
        "range_authority": True,
        "linear_action_closure": True,
        "normal_projected_component": True,
        "composed_not_worse": True,
        "composed_rho_gate": False,
    }
    raw = runner._attach_evidence(
        {
            "status": "gate_failed",
            "error": None,
            "diagnostic_numeric_pass": False,
            "w2_pass": False,
            "formal_pass": False,
            "pde_pass": False,
            "source_at_start": source,
            "source_at_end": source,
            "gate": {
                "pass": False,
                "problems": ["composed_rho_gate"],
                "checks": checks,
            },
        }
    )
    watchdog = runner._attach_evidence(
        {
            "formal_pass": False,
            "w2_pass": False,
            "pde_pass": False,
            "wrapper_error": None,
            "source_start": source,
            "source_end": source,
            "process": {
                "return_code": 1,
                "termination": None,
                "peak_rss_bytes": runner.M6B_W2R_OLD_NEGATIVE_PEAK_RSS_BYTES,
                "swap_bytes": 0,
            },
            "worker_summary": {"gate": {"checks": checks}},
        }
    )
    assert runner._m6b_w2r_old_negative_valid(
        raw,
        watchdog,
        runner.M6B_W2R_OLD_RAW_SUMMARY_SHA256,
        runner.M6B_W2R_OLD_WATCHDOG_SUMMARY_SHA256,
    ) is True

    missing_gate = deepcopy(watchdog)
    del missing_gate["worker_summary"]["gate"]
    missing_gate = runner._attach_evidence(missing_gate)
    assert runner._m6b_w2r_old_negative_valid(
        raw,
        missing_gate,
        runner.M6B_W2R_OLD_RAW_SUMMARY_SHA256,
        runner.M6B_W2R_OLD_WATCHDOG_SUMMARY_SHA256,
    ) is False

    tampered = deepcopy(raw)
    tampered["gate"]["checks"]["composed_rho_gate"] = True
    tampered = runner._attach_evidence(tampered)
    assert runner._m6b_w2r_old_negative_valid(
        tampered,
        watchdog,
        runner.M6B_W2R_OLD_RAW_SUMMARY_SHA256,
        runner.M6B_W2R_OLD_WATCHDOG_SUMMARY_SHA256,
    ) is False

    non_mapping_gate = deepcopy(watchdog)
    non_mapping_gate["worker_summary"]["gate"] = []
    non_mapping_gate = runner._attach_evidence(non_mapping_gate)
    assert runner._m6b_w2r_old_negative_valid(
        raw,
        non_mapping_gate,
        runner.M6B_W2R_OLD_RAW_SUMMARY_SHA256,
        runner.M6B_W2R_OLD_WATCHDOG_SUMMARY_SHA256,
    ) is False


def test_m6b_w2_w0_authority_file_and_tamper_fail_closed(tmp_path: Path, monkeypatch):
    payload = {
        "schema": "task037.m6b.wave_range_az_oracle.v1",
        "formal_pass": False,
        "pde_pass": False,
        "full_pde_qualifies": False,
        "raw_unchanged": True,
        "source": {
            "residual_producer_source": runner.M6B_W2_RESIDUAL_SOURCE_SHA,
            "oracle_execution_source": runner.M6B_W2_W0_ORACLE_SOURCE_SHA,
            "git": {
                "branch": "codex/20260806-task37-iterative-extra-development",
                "head": runner.M6B_W2_W0_ORACLE_SOURCE_SHA,
                "upstream": runner.M6B_W2_W0_ORACLE_SOURCE_SHA,
                "ahead": 0,
                "behind": 0,
                "clean": True,
            },
        },
        "basis": {
            "manifest_sha256": runner.M6B_W2_W0_BASIS_MANIFEST_SHA256,
            "az_column_sha256_aggregate": (
                runner.M6B_W2_W0_AZ_COLUMN_SHA256_AGGREGATE
            ),
        },
        "range_projection": {
            "checkpoints": {
                key: {
                    "iteration": int(key),
                    "finite": True,
                    "rho_range": runner.M6B_W2_W0_RANGE_RHO_AUTHORITY[key],
                }
                for key in ("20", "100", "150", "200")
            }
        },
    }
    payload = runner._attach_evidence(payload)
    path = tmp_path / "w0.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        runner, "_sha256_file", lambda _path: runner.M6B_W2_W0_OUTPUT_SHA256
    )
    record = runner._m6b_w2_w0_authority_record(path)
    assert record["file_artifact"]["path"] == str(path.resolve())
    tampered = deepcopy(payload)
    tampered["basis"]["manifest_sha256"] = "0" * 64
    assert runner._m6b_w2_w0_payload_valid(tampered) is False


def test_m6b_w2_factor_manifest_requires_nested_audit():
    materialization = {
        key: False
        for key in (
            "global_constraint_matrix",
            "global_matrix",
            "patch_matrices",
            "per_cell_factor",
            "schur",
            "slab_factor",
            "static_condensation",
            "trace_slab",
        )
    }
    payload = {
        "schema": "task037.extra.h2b.m6b.shifted-lu-store.v1",
        "beta": 1.0,
        "audit": {
            "schema": "task037.extra.h2b.m6b.shifted-lu-store.v1",
            "beta": 1.0,
            "factor_count": 84,
            "cell_count": 252,
            "factor_order": 882,
            "factor_reuse_count": 168,
            "factor_payload_bytes": runner.M6B_FACTOR_PAYLOAD_BYTES,
            "retained_total_gate": True,
            "materialization_identity": materialization,
        },
    }
    assert runner._m6b_w2_factor_manifest_valid(payload) is True
    beta05 = deepcopy(payload)
    beta05["beta"] = 0.5
    beta05["audit"]["beta"] = 0.5
    assert runner._m6b_w2_factor_manifest_valid(
        beta05, expected_beta=runner.M6B_W3_BETA05
    ) is True
    assert runner._m6b_w2_factor_manifest_valid(beta05) is False
    assert runner._m6b_w2_factor_manifest_valid(
        beta05, expected_beta=0.75
    ) is False
    top_level_only = deepcopy(payload)
    top_level_only.update(top_level_only.pop("audit"))
    assert runner._m6b_w2_factor_manifest_valid(top_level_only) is False
    missing_audit = deepcopy(payload)
    del missing_audit["audit"]
    assert runner._m6b_w2_factor_manifest_valid(missing_audit) is False
