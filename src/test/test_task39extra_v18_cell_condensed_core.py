"""Review V18 U0: tiny algebra oracle plus one real FFCx adapter call."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest
from scipy.linalg import lu_factor, lu_solve

from src.solvers.p4_cell_condensed_inverse import (
    P4CellCondensedInverse,
    csr_content_identity,
)


@dataclass(frozen=True)
class CellBlocks:
    """Test-only dense local tensor used as the U0 algebra oracle."""

    Vii: np.ndarray
    Vit: np.ndarray
    Vti: np.ndarray
    Vtt: np.ndarray
    Bi: np.ndarray
    Bt: np.ndarray
    Di: np.ndarray
    Dt: np.ndarray
    H: np.ndarray
    gi: np.ndarray
    gt: np.ndarray


@dataclass(frozen=True)
class CondensedCellBlock:
    """Test-only Schur result; no dense full-p4 object is production-owned."""

    S_V: np.ndarray
    Bhat: np.ndarray
    Dhat: np.ndarray
    Hhat: np.ndarray
    Xit: np.ndarray
    XiB: np.ndarray
    _interior_lu: tuple[np.ndarray, np.ndarray]

    def solve_interior(self, rhs: np.ndarray) -> np.ndarray:
        return lu_solve(self._interior_lu, np.asarray(rhs, dtype=np.complex128))


def condense_cell_tensor(blocks: CellBlocks) -> CondensedCellBlock:
    """Build the small dense oracle for the complete local block formula."""

    lu = lu_factor(np.asarray(blocks.Vii, dtype=np.complex128), check_finite=True)
    Xit = lu_solve(lu, blocks.Vit, check_finite=True)
    XiB = lu_solve(lu, blocks.Bi, check_finite=True)
    return CondensedCellBlock(
        S_V=blocks.Vtt - blocks.Vti @ Xit,
        Bhat=blocks.Bt - blocks.Vti @ XiB,
        Dhat=blocks.Dt - blocks.Di @ Xit,
        Hhat=blocks.H + blocks.Di @ XiB,
        Xit=np.asarray(Xit, dtype=np.complex128),
        XiB=np.asarray(XiB, dtype=np.complex128),
        _interior_lu=lu,
    )


def combine_cell_tensors(blocks: list[CellBlocks]) -> CellBlocks:
    """Sum local tensors before elimination, exposing non-commuting Schur order."""

    if not blocks:
        raise ValueError("at least one test tensor is required")
    fields = tuple(
        np.sum(np.stack([getattr(block, name) for block in blocks]), axis=0)
        for name in CellBlocks.__dataclass_fields__
    )
    return CellBlocks(*fields)


def augmented_residual_identity(
    V: np.ndarray,
    B: np.ndarray,
    D: np.ndarray,
    H: np.ndarray,
    g: np.ndarray,
    c: np.ndarray,
    alpha: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return the lower-eliminated residual and its augmented residual vector."""

    top = np.asarray(g) - V @ c - B @ alpha
    lower = D @ c - H @ alpha
    errors = np.concatenate((top, lower))
    return top - B @ np.linalg.solve(H, lower), errors


def _blocks(seed: int, *, ni: int = 2, nt: int = 2, np_: int = 1) -> CellBlocks:
    rng = np.random.default_rng(seed)

    def m(rows: int, columns: int, diagonal: float = 0.0) -> np.ndarray:
        value = rng.normal(size=(rows, columns)) + 1j * rng.normal(size=(rows, columns))
        if rows == columns:
            value += diagonal * np.eye(rows)
        return value.astype(np.complex128)

    return CellBlocks(
        Vii=m(ni, ni, 4.0),
        Vit=m(ni, nt), Vti=m(nt, ni), Vtt=m(nt, nt, 2.0),
        Bi=m(ni, np_), Bt=m(nt, np_), Di=m(np_, ni), Dt=m(np_, nt),
        H=m(np_, np_, 3.0), gi=m(ni, 1)[:, 0], gt=m(nt, 1)[:, 0],
    )


def _add_block(target: np.ndarray, rows: np.ndarray, block: np.ndarray) -> None:
    target[np.ix_(rows, rows)] += block


def test_complete_nonhermitian_cell_tensor_matches_dense_augmented_oracle():
    first, second = _blocks(11), _blocks(12)
    # Two cells share one independent trace row and one port row.  The dense
    # matrix is a test oracle only; no such matrix is kept by the adapter.
    full_rows, port_rows = 7, 1
    full = np.zeros((full_rows + port_rows, full_rows + port_rows), complex)
    for blocks, interiors, traces in (
        (first, [0, 1], [4, 5]),
        (second, [2, 3], [5, 6]),
    ):
        rows = np.asarray(interiors + traces + [full_rows], dtype=int)
        local = np.block([[blocks.Vii, blocks.Vit, blocks.Bi],
                          [blocks.Vti, blocks.Vtt, blocks.Bt],
                          [-blocks.Di, -blocks.Dt, blocks.H]])
        _add_block(full, rows, local)

    reduced = np.zeros((4, 4), complex)
    for blocks, traces in ((first, [0, 1]), (second, [1, 2])):
        cell = condense_cell_tensor(blocks)
        rows = np.asarray(traces + [3], dtype=int)
        local = np.block([[cell.S_V, cell.Bhat],
                          [-cell.Dhat, cell.Hhat]])
        _add_block(reduced, rows, local)

    rng = np.random.default_rng(20260914)
    rhs = rng.normal(size=full_rows) + 1j * rng.normal(size=full_rows)
    augmented_rhs = np.r_[rhs, 0.0j]
    full_solution = np.linalg.solve(full, augmented_rhs)
    reduced_rhs = np.zeros(4, complex)
    reduced_rhs[:3] = rhs[[4, 5, 6]]
    for blocks, interiors, traces in (
        (first, [0, 1], [0, 1]),
        (second, [2, 3], [1, 2]),
    ):
        cell = condense_cell_tensor(blocks)
        xig = cell.solve_interior(rhs[interiors])
        reduced_rhs[traces] -= blocks.Vti @ xig
        reduced_rhs[3] += (blocks.Di @ xig)[0]
    reduced_solution = np.linalg.solve(reduced, reduced_rhs)
    recovered = np.zeros(full_rows, complex)
    recovered[[4, 5, 6]] = reduced_solution[:3]
    for blocks, interiors, traces in (
        (first, [0, 1], [0, 1]),
        (second, [2, 3], [1, 2]),
    ):
        cell = condense_cell_tensor(blocks)
        recovered[interiors] = (
            cell.solve_interior(rhs[interiors])
            - cell.Xit @ reduced_solution[traces]
            - cell.XiB @ reduced_solution[[3]]
        )
    np.testing.assert_allclose(reduced_solution, full_solution[[4, 5, 6, 7]], rtol=2e-12, atol=2e-12)
    np.testing.assert_allclose(recovered, full_solution[:full_rows], rtol=2e-12, atol=2e-12)
    assert not np.allclose(first.Di, first.Bi.conj().T)


def test_sum_before_schur_and_general_residual_identity():
    first, second = _blocks(23), _blocks(24)
    combined = combine_cell_tensors([first, second])
    combined_schur = condense_cell_tensor(combined)
    separate = condense_cell_tensor(first).S_V + condense_cell_tensor(second).S_V
    assert not np.allclose(combined_schur.S_V, separate)

    rng = np.random.default_rng(91)
    V = rng.normal(size=(3, 3)) + 1j * rng.normal(size=(3, 3)) + 5 * np.eye(3)
    B = rng.normal(size=(3, 2)) + 1j * rng.normal(size=(3, 2))
    D = rng.normal(size=(2, 3)) + 1j * rng.normal(size=(2, 3))
    H = rng.normal(size=(2, 2)) + 1j * rng.normal(size=(2, 2)) + 5 * np.eye(2)
    c = rng.normal(size=3) + 1j * rng.normal(size=3)
    alpha = rng.normal(size=2) + 1j * rng.normal(size=2)
    g = V @ c + B @ alpha + rng.normal(size=3)
    residual, errors = augmented_residual_identity(V, B, D, H, g, c, alpha)
    np.testing.assert_allclose(residual, errors[:3] - B @ np.linalg.solve(H, errors[3:]))


def test_csr_identity_is_content_bound_without_dense_gather():
    matrix = np.asarray([[1 + 2j, 0, 3], [0, 4, 0]], dtype=np.complex128)
    first = csr_content_identity(matrix)
    same = csr_content_identity(matrix.copy())
    changed = csr_content_identity(matrix + np.asarray([[0, 0, 1e-8], [0, 0, 0]]))
    assert first["csr_sha256"] == same["csr_sha256"]
    assert first["csr_sha256"] != changed["csr_sha256"]
    assert first["dense_gather"] is False
    assert first["nnz_semantics"].startswith("sum_duplicates")


def test_real_ffcx_system_uses_one_factor_solve_and_recovers_interiors():
    from basix.ufl import element
    from dolfinx import default_real_type, fem, mesh
    from dolfinx.fem import petsc as fem_petsc
    from mpi4py import MPI
    from petsc4py import PETSc
    import ufl
    from src.solvers.hcurl_assembly_time_condensation import build_unconstrained_assembly_time_condensation

    domain = mesh.create_unit_cube(MPI.COMM_SELF, 2, 1, 1, cell_type=mesh.CellType.hexahedron)
    tags = mesh.meshtags(domain, 3, np.asarray([0, 1], dtype=np.int32), np.asarray([1, 1], dtype=np.int32))
    V = fem.functionspace(domain, element("N1curl", domain.basix_cell(), 2, dtype=default_real_type))
    u, v = ufl.TrialFunction(V), ufl.TestFunction(V)
    form = fem.form((ufl.inner(ufl.curl(u), ufl.curl(v)) + PETSc.ScalarType(2.5 - 0.2j) * ufl.inner(u, v)) * ufl.Measure("dx", domain=domain, subdomain_data=tags)(1))
    condensed = build_unconstrained_assembly_time_condensation(form, V, tags)
    full = fem_petsc.assemble_matrix(form, bcs=[]); full.assemble()

    class Factor:
        def __init__(self, matrix):
            self.ksp = PETSc.KSP().create(MPI.COMM_SELF)
            self.ksp.setOperators(matrix); self.ksp.setType("preonly"); self.ksp.getPC().setType("lu"); self.ksp.setUp(); self.calls = 0; self.destroyed = False
        def solve_repeated(self, rhs_value, solution):
            self.ksp.solve(rhs_value, solution); self.calls += 1
        def destroy(self):
            self.ksp.destroy(); self.destroyed = True

    factor = Factor(condensed.matrix)
    inverse = P4CellCondensedInverse(condensed, factor, owns_factor=True)
    rhs = full.createVecRight(); rng = np.random.default_rng(20260914); rhs.getArray()[:] = rng.normal(size=rhs.getLocalSize()) + 1j * rng.normal(size=rhs.getLocalSize()); rhs.assemble()
    original = rhs.getArray(readonly=True).copy()
    result = inverse.apply(rhs)
    assert factor.calls == inverse.solve_count == 1
    np.testing.assert_array_equal(rhs.getArray(readonly=True), original)
    residual = full.createVecLeft(); full.mult(result, residual); residual.axpy(PETSc.ScalarType(-1), rhs)
    assert residual.norm() / max(rhs.norm(), 1e-30) < 2e-11
    zero = rhs.duplicate(); zero.set(PETSc.ScalarType(0)); zero.assemble(); zero_result = inverse.apply(zero)
    assert factor.calls == 1 and zero_result.norm() == 0
    inverse.destroy(); assert factor.destroyed
    with pytest.raises(RuntimeError, match="destroyed"):
        inverse.apply(rhs)
    zero_result.destroy(); zero.destroy(); residual.destroy(); result.destroy(); rhs.destroy(); full.destroy(); condensed.destroy()
