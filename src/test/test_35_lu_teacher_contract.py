from __future__ import annotations

import numpy as np
import pytest

from benchmarks.neural_pc.build_lu_teacher_dataset import _load_raw_rhs
from benchmarks.neural_pc.petsc_capture import LocalSlabCapture
from src.solvers.local_slab_solver import LocalCsrOperator, ScipyCsrAction
from src.solvers.lu_teacher_local_solver import SparseLuTeacherLocalSolver


def _operator() -> LocalCsrOperator:
    return LocalCsrOperator(
        shape=(4, 4),
        indptr=np.arange(5, dtype=np.int64),
        indices=np.arange(4, dtype=np.int64),
        values=np.array([2 + 1j, 3 - 0.5j, 4 + 2j, 5 - 1j]),
        metadata={"slab_id": 9},
    )


def test_sparse_lu_teacher_reuses_one_factor_and_destroys() -> None:
    operator = _operator()
    teacher = SparseLuTeacherLocalSolver(operator)
    rhs = np.array(
        [
            [1 + 2j, 2 - 3j, 4 + 0j, -1j],
            [-2 + 1j, 0.5j, 3 - 4j, 2 + 2j],
        ]
    )
    target, elapsed = teacher.solve_many(rhs)
    residual = rhs - ScipyCsrAction(operator).action_many(target)
    rho = np.linalg.norm(residual, axis=1) / np.linalg.norm(rhs, axis=1)
    assert np.max(rho) < 1e-13
    assert np.all(elapsed >= 0.0)
    assert teacher.diagnostics["solve_count"] == 2
    assert teacher.diagnostics["factor_nnz"] > 0

    teacher.destroy()
    assert teacher.diagnostics["destroyed"] is True
    with pytest.raises(RuntimeError, match="destroyed"):
        teacher.solve(rhs[0], np.empty(4, dtype=np.complex128))


def test_capture_can_store_selected_raw_rhs_without_ilu_payload(tmp_path) -> None:
    operator = _operator()
    capture = LocalSlabCapture(
        tmp_path,
        rank=0,
        included_slabs={9},
        store_local_correction=False,
        maximum_samples_per_slab=2,
        sample_stride=1,
    )
    capture.observe_operator(8, operator)
    capture.observe_operator(9, operator)
    rhs = np.arange(4) + 1j * np.arange(4)[::-1]
    capture.observe_sample(8, rhs, rhs, "ilu")
    capture.observe_sample(9, rhs, rhs, "ilu")
    capture.observe_sample(9, 2 * rhs, rhs, "ilu")
    capture.write_manifest()

    slab = tmp_path / "rank_0000" / "slab_009"
    assert not (tmp_path / "rank_0000" / "slab_008").exists()
    rows = _load_raw_rhs(slab)
    assert rows.shape == (2, 4)
    with np.load(slab / "real_krylov" / "sample_000000.npz") as payload:
        assert set(payload.files) == {"rhs", "apply_index"}


def test_raw_rhs_loader_rejects_ilu_conditioned_payload(tmp_path) -> None:
    samples = tmp_path / "real_krylov"
    samples.mkdir()
    np.savez_compressed(
        samples / "sample_000000.npz",
        rhs=np.ones(4, dtype=np.complex128),
        apply_index=np.asarray(1),
        local_correction=np.ones(4, dtype=np.complex128),
    )
    with pytest.raises(ValueError, match="not raw-RHS-only"):
        _load_raw_rhs(tmp_path)


def test_batched_raw_capture_uses_one_file_and_round_trips(tmp_path) -> None:
    operator = _operator()
    capture = LocalSlabCapture(
        tmp_path,
        rank=0,
        included_slabs={9},
        store_local_correction=False,
        batched_storage=True,
        maximum_samples_per_slab=3,
        sample_stride=2,
    )
    capture.observe_operator(9, operator)
    rhs = np.arange(4) + 1j * np.arange(4)[::-1]
    for scale in range(1, 7):
        capture.observe_sample(9, scale * rhs, rhs, "ilu")
    capture.write_manifest()

    slab = tmp_path / "rank_0000" / "slab_009"
    batch = slab / "real_krylov" / "samples.npz"
    assert batch.is_file()
    assert not list(batch.parent.glob("sample_*.npz"))
    np.testing.assert_array_equal(
        _load_raw_rhs(slab),
        np.stack((2 * rhs, 4 * rhs, 6 * rhs)),
    )
    assert capture.diagnostics["storage_layout"] == "one_uncompressed_batch_per_slab"


def test_batched_raw_loader_rejects_wrong_apply_index_shape(tmp_path) -> None:
    samples = tmp_path / "real_krylov"
    samples.mkdir()
    np.savez(
        samples / "samples.npz",
        rhs=np.ones((2, 4), dtype=np.complex128),
        apply_index=np.asarray([1], dtype=np.int64),
    )
    with pytest.raises(ValueError, match="invalid batched shapes"):
        _load_raw_rhs(tmp_path)
