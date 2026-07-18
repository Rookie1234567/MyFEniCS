from __future__ import annotations

import numpy as np
import pytest
import scipy.sparse as sp
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.neural_pc.qualify_task006_borrowed_action import (
    qualify_borrowed_action,
)
from src.solvers.physical_slab_two_level import DistributedPhysicalSlabSmoother


def _global_operator(size: int = 8) -> tuple[PETSc.Mat, np.ndarray]:
    comm = PETSc.COMM_WORLD
    matrix = PETSc.Mat().createAIJ((size, size), nnz=3, comm=comm)
    matrix.setUp()
    start, end = matrix.getOwnershipRange()
    dense = np.zeros((size, size), dtype=np.complex128)
    for row in range(size):
        dense[row, row] = 4.5 + 0.2j + 0.07 * row
        if row:
            dense[row, row - 1] = -0.8 + 0.03j
        if row + 1 < size:
            dense[row, row + 1] = -1.1 - 0.02j
    for row in range(start, end):
        columns = np.flatnonzero(dense[row]).astype(PETSc.IntType)
        matrix.setValues(row, columns, dense[row, columns])
    matrix.assemble()
    return matrix, dense


def _subdomains() -> list[np.ndarray]:
    return [
        np.asarray(values, dtype=PETSc.IntType)
        for values in (
            (0, 1, 2, 3),
            (2, 3, 4, 5),
            (4, 5, 6, 7),
            (0, 1, 6, 7),
        )
    ]


def test_borrowed_action_matches_shifted_local_submatrix_and_rho() -> None:
    matrix, dense = _global_operator()
    subdomains = _subdomains()
    smoother = DistributedPhysicalSlabSmoother(
        matrix,
        subdomains,
        ilu_levels=0,
        action_operator=matrix,
        smoother_iterations=1,
        factor_only_storage=True,
    )
    auditor = smoother.create_borrowed_exact_auditor()
    rng = np.random.default_rng(1701)
    try:
        for slab_id, indices in enumerate(subdomains):
            owner = smoother.subdomain_owners[slab_id]
            correction = (
                rng.standard_normal(indices.size)
                + 1j * rng.standard_normal(indices.size)
            )
            correction *= np.exp(1j * 0.37 * (slab_id + 1))
            expected = dense[np.ix_(indices, indices)] @ correction
            result = auditor.audit(
                slab_id,
                rhs=expected if MPI.COMM_WORLD.rank == owner else None,
                correction=correction if MPI.COMM_WORLD.rank == owner else None,
            )
            assert result.owner_rank == owner
            assert result.rho <= 1.0e-14
            if MPI.COMM_WORLD.rank == owner:
                np.testing.assert_allclose(
                    result.local_action, expected, rtol=1.0e-14, atol=1.0e-14
                )
            else:
                assert result.local_action is None

        diagnostics = auditor.diagnostics
        assert diagnostics["audit_count"] == len(subdomains)
        assert diagnostics["work_vectors_created"] == 4
        assert diagnostics["private_persistent_local_csr_bytes"] == 0
        assert diagnostics["owns_action_operator"] is False
        assert diagnostics["owns_union_scatter"] is False
    finally:
        smoother.destroy()
        matrix.destroy()

    assert auditor.diagnostics["destroyed"] is True
    auditor.destroy()
    with pytest.raises(RuntimeError, match="destroyed"):
        auditor.audit(0, rhs=None, correction=None)


def test_borrowed_auditor_fails_closed_on_invalid_payload() -> None:
    matrix, _dense = _global_operator()
    subdomains = _subdomains()
    smoother = DistributedPhysicalSlabSmoother(
        matrix,
        subdomains,
        ilu_levels=0,
        action_operator=matrix,
        smoother_iterations=1,
        factor_only_storage=True,
    )
    auditor = smoother.create_borrowed_exact_auditor()
    owner = smoother.subdomain_owners[0]
    try:
        wrong_payload = np.ones(subdomains[0].size + 1, dtype=np.complex128)
        with pytest.raises(ValueError, match="shape mismatch"):
            auditor.audit(
                0,
                rhs=wrong_payload if MPI.COMM_WORLD.rank == owner else None,
                correction=wrong_payload if MPI.COMM_WORLD.rank == owner else None,
            )
    finally:
        smoother.destroy()
        matrix.destroy()


def test_borrowed_qualification_uses_ephemeral_csr_only(tmp_path) -> None:
    matrix, dense = _global_operator()
    subdomains = _subdomains()
    reference_root = tmp_path / "reference"
    for slab_id, indices in enumerate(subdomains):
        local = sp.csr_matrix(dense[np.ix_(indices, indices)])
        folder = reference_root / f"slab_{slab_id:03d}"
        folder.mkdir(parents=True)
        np.savez(
            folder / "operator.npz",
            indptr=local.indptr,
            indices=local.indices,
            values=local.data,
            shape=np.asarray(local.shape, dtype=np.int64),
        )
    smoother = DistributedPhysicalSlabSmoother(
        matrix,
        subdomains,
        ilu_levels=0,
        action_operator=matrix,
        smoother_iterations=1,
        factor_only_storage=True,
    )
    output = tmp_path / "borrowed.json"
    try:
        result = qualify_borrowed_action(
            smoother,
            reference_root=reference_root,
            output_path=output,
        )
        assert result["slabs"] == 4
        assert result["row_count"] == 16
        assert result["equivalence_pass"] is True
        assert result["action_relative_error_max"] <= 1.0e-12
        assert result["rho_absolute_error_max"] <= 1.0e-12
        assert result["private_persistent_local_csr_bytes"] == 0
        if MPI.COMM_WORLD.rank == 0:
            assert output.is_file()
    finally:
        smoother.destroy()
        matrix.destroy()
