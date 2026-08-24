"""Owner-space LOR/H(curl) spectral audit primitives.

This module is deliberately an audit utility, not a production preconditioner.
It keeps the low-order sparse matrix and applies the pulled high-order operator
through a PETSc MatShell.  No high-order AIJ matrix or global transfer matrix is
created.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
from petsc4py import PETSc
from slepc4py import SLEPc

from src.solvers.fullspace_lor_hx_root_cause import (
    lift_low_primal,
    low_input_from_high_dual,
)


DEGREE = 3
H_NM = 50.0
FULL_EDGE_ROWS = 3018
SLAVE_EDGE_ROWS = 480
INDEPENDENT_EDGE_ROWS = 2538
LINEARITY_ALPHA = 0.37 + 0.19j
LINEARITY_BETA = -0.23 + 0.41j
WORK_LIMIT = 1.0e-12
LINEARITY_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-13
EIGEN_RESIDUAL_LIMIT = 1.0e-10
SPECTRAL_CONDITION_LIMIT = 100.0
EPS_TOL = 1.0e-10
EPS_MAX_IT = 500
EPS_NEV = 1
EPS_NCV = 21
EPS_ST_TYPE = "shift"
EPS_SHIFT = 0.0
EPS_KSP_TYPE = "preonly"
EPS_PC_TYPE = "lu"
EPS_FACTOR_SOLVER = "mumps"


def relative(left: np.ndarray, right: np.ndarray, denominator: np.ndarray | None = None) -> float:
    """Return a complex-vector relative error with an explicit denominator."""

    left = np.asarray(left, dtype=np.complex128)
    right = np.asarray(right, dtype=np.complex128)
    base = right if denominator is None else np.asarray(denominator, dtype=np.complex128)
    return float(
        np.linalg.norm(left - right)
        / max(float(np.linalg.norm(base)), np.finfo(float).tiny)
    )


def scalar_relative(left: complex, right: complex) -> float:
    """Relative error for a complex work scalar."""

    return float(abs(complex(left) - complex(right)) / max(abs(complex(right)), np.finfo(float).tiny))


def build_independent_layout(
    full_rows: int,
    slave_rows: np.ndarray,
    raw_to_canonical: Mapping[int, int],
    owner_ids: np.ndarray,
) -> dict[str, Any]:
    """Build and verify the raw-row to canonical-owner bijection.

    The independent coordinate order is increasing raw PETSc row.  Canonical
    IDs are only identities; they are not assumed to be contiguous or equal to
    PETSc row ordinals.
    """

    full_rows = int(full_rows)
    if full_rows < 1:
        raise ValueError("full row count must be positive")
    slave = np.asarray(slave_rows, dtype=np.int64)
    owners = np.asarray(owner_ids, dtype=np.int64)
    if slave.ndim != 1 or owners.ndim != 1:
        raise ValueError("row inventories must be one-dimensional")
    if np.unique(slave).size != slave.size or np.any(slave < 0) or np.any(slave >= full_rows):
        raise ValueError("slave row inventory is not unique and in range")
    slave_set = set(int(row) for row in slave.tolist())
    active = np.asarray(
        [row for row in range(full_rows) if row not in slave_set], dtype=np.int64
    )
    if active.size != full_rows - slave.size:
        raise ValueError("active row count does not close full/slave rows")
    try:
        canonical = np.asarray([int(raw_to_canonical[int(row)]) for row in active], dtype=np.int64)
    except KeyError as exc:
        raise ValueError(f"missing raw-to-canonical row mapping: {exc}") from exc
    if np.unique(canonical).size != canonical.size:
        raise ValueError("active raw rows do not map uniquely to canonical IDs")
    if np.unique(owners).size != owners.size or not np.array_equal(np.sort(canonical), np.sort(owners)):
        raise ValueError("active raw rows and owner IDs are not a bijection")
    return {
        "full_rows": full_rows,
        "slave_rows": slave.copy(),
        "active_raw_rows": active,
        "canonical_ids": canonical,
        "owner_ids": owners.copy(),
        "owner_count": int(active.size),
        "bijection": True,
    }


def raw_slave_global_rows(space: Any, mpc: Any) -> np.ndarray:
    """Return finalized MPC slave rows in the raw space's global numbering."""

    index_map = space.dofmap.index_map
    local = int(index_map.size_local)
    storage = local + int(index_map.num_ghosts)
    global_ids = np.asarray(
        index_map.local_to_global(np.arange(storage, dtype=np.int32)), dtype=np.int64
    )
    slave_local = np.asarray(mpc.slaves, dtype=np.int64)
    slave_local = slave_local[(slave_local >= 0) & (slave_local < storage)]
    return np.unique(global_ids[slave_local]).astype(np.int64, copy=False)


def create_independent_submatrix(matrix: PETSc.Mat, active_raw_rows: np.ndarray) -> PETSc.Mat:
    """Create the sparse low-order active-row/active-column submatrix."""

    rows = np.asarray(active_raw_rows, dtype=PETSc.IntType)
    row_is = PETSc.IS().createGeneral(rows, comm=matrix.comm)
    col_is = PETSc.IS().createGeneral(rows, comm=matrix.comm)
    try:
        result = matrix.createSubMatrix(row_is, col_is)
    finally:
        row_is.destroy()
        col_is.destroy()
    if result.getSize() != (int(rows.size), int(rows.size)):
        result.destroy()
        raise ValueError("independent sparse submatrix has an unexpected size")
    return result


def embed_owner_values(layout: Mapping[str, Any], vector: PETSc.Vec, values: np.ndarray) -> None:
    """Write owner coordinates into active raw rows and keep slave rows zero."""

    active = np.asarray(layout["active_raw_rows"], dtype=np.int64)
    values = np.asarray(values, dtype=np.complex128)
    start, stop = (int(value) for value in vector.getOwnershipRange())
    if values.size != active.size or start != 0 or stop != active.size + int(np.asarray(layout["slave_rows"]).size):
        raise ValueError("owner vector and raw vector use incompatible serial layouts")
    vector.set(0.0 + 0.0j)
    vector.array[active] = values


def extract_owner_values(layout: Mapping[str, Any], vector: PETSc.Vec) -> np.ndarray:
    """Extract active raw rows in the fixed increasing-raw-row coordinate order."""

    active = np.asarray(layout["active_raw_rows"], dtype=np.int64)
    start, stop = (int(value) for value in vector.getOwnershipRange())
    if start != 0 or stop < int(active[-1]) + 1:
        raise ValueError("raw vector ownership is not the fixed MPI1 audit layout")
    return np.asarray(vector.array[active], dtype=np.complex128).copy()


class PulledHighActionContext:
    """MatShell context for (A_pull=L^H B_H L)."""

    def __init__(self, fixture: Any, layout: Mapping[str, Any]):
        self.fixture = fixture
        self.layout = layout
        self.apply_count = 0

    def mult(self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec) -> None:
        low = self.fixture.edge_matrix.createVecRight()
        high = None
        action = None
        low_dual = None
        try:
            embed_owner_values(self.layout, low, source.array)
            high = lift_low_primal(self.fixture, low)
            action = self.fixture.apply_high_action_copy(high)
            low_dual, _owner_packet = low_input_from_high_dual(self.fixture, action)
            target.array[:] = extract_owner_values(self.layout, low_dual)
            target.assemble()
            self.apply_count += 1
        finally:
            if low_dual is not None:
                low_dual.destroy()
            if action is not None:
                action.destroy()
            if high is not None:
                high.destroy()
            low.destroy()


def build_pulled_high_shell(
    fixture: Any, layout: Mapping[str, Any]
) -> tuple[PETSc.Mat, PulledHighActionContext]:
    """Create the owner-space matrix-free pulled high action."""

    owner = int(layout["owner_count"])
    context = PulledHighActionContext(fixture, layout)
    matrix = PETSc.Mat().createPython(
        ((owner, owner), (owner, owner)), context=context, comm=fixture.comm
    )
    matrix.setUp()
    matrix.setOption(PETSc.Mat.Option.HERMITIAN, True)
    return matrix, context


def owner_to_high(fixture: Any, layout: Mapping[str, Any], values: np.ndarray) -> PETSc.Vec:
    """Apply the primal low-owner to high-space route once."""

    low = fixture.edge_matrix.createVecRight()
    embed_owner_values(layout, low, values)
    try:
        result = lift_low_primal(fixture, low)
    finally:
        low.destroy()
    return result


def high_dual_to_owner(fixture: Any, layout: Mapping[str, Any], high: PETSc.Vec) -> np.ndarray:
    """Apply the dual high-to-low route and extract active raw rows."""

    low, _owner_packet = low_input_from_high_dual(fixture, high)
    try:
        return extract_owner_values(layout, low)
    finally:
        low.destroy()


def work_identity_relative(
    high_primal: np.ndarray, high_dual: np.ndarray, owner_primal: np.ndarray, owner_dual: np.ndarray
) -> float:
    """Compute ``<L q,h> = <q,L^H h>`` using NumPy's complex convention."""

    lhs = np.vdot(np.asarray(high_primal, dtype=np.complex128), np.asarray(high_dual, dtype=np.complex128))
    rhs = np.vdot(np.asarray(owner_primal, dtype=np.complex128), np.asarray(owner_dual, dtype=np.complex128))
    return scalar_relative(lhs, rhs)


def _solve_one_eigenpair(
    operator: PETSc.Mat,
    mass: PETSc.Mat,
    initial: PETSc.Vec,
    which: Any,
) -> dict[str, Any]:
    eps = SLEPc.EPS().create(operator.comm)
    vector = operator.createVecRight()
    action = operator.createVecLeft()
    mass_action = mass.createVecLeft()
    initial_copy = initial.copy()
    try:
        eps.setOperators(operator, mass)
        eps.setProblemType(SLEPc.EPS.ProblemType.GHEP)
        eps.setType(SLEPc.EPS.Type.KRYLOVSCHUR)
        spectral_transform = eps.getST()
        spectral_transform.setType(SLEPc.ST.Type.SHIFT)
        spectral_transform.setShift(EPS_SHIFT)
        st_ksp = spectral_transform.getKSP()
        st_ksp.setType(PETSc.KSP.Type.PREONLY)
        st_pc = st_ksp.getPC()
        st_pc.setType(PETSc.PC.Type.LU)
        st_pc.setFactorSolverType(EPS_FACTOR_SOLVER)
        eps.setWhichEigenpairs(which)
        eps.setDimensions(nev=EPS_NEV, ncv=EPS_NCV)
        eps.setTolerances(tol=EPS_TOL, max_it=EPS_MAX_IT)
        eps.setInitialSpace([initial_copy])
        eps.solve()
        reason = int(eps.getConvergedReason())
        converged = int(eps.getConverged())
        if reason <= 0 or converged < EPS_NEV:
            raise RuntimeError(f"GHEP did not converge: reason={reason}, converged={converged}")
        eigenvalue = complex(eps.getEigenvalue(0))
        eps.getEigenvector(0, vector)
        operator.mult(vector, action)
        mass.mult(vector, mass_action)
        residual = action.copy()
        residual.axpy(PETSc.ScalarType(-eigenvalue), mass_action)
        action_norm = float(action.norm())
        mass_action_norm = float(mass_action.norm())
        residual_relative = float(
            residual.norm()
            / max(action_norm, abs(eigenvalue) * mass_action_norm, np.finfo(float).tiny)
        )
        quadratic = vector.dot(mass_action)
        return {
            "eigenvalue": float(eigenvalue.real),
            "imaginary_part": float(eigenvalue.imag),
            "residual_relative": residual_relative,
            "q_norm": float(vector.norm()),
            "quadratic_real": float(complex(quadratic).real),
            "quadratic_imag": float(complex(quadratic).imag),
            "reason": reason,
            "iterations": int(eps.getIterationNumber()),
            "vector": np.asarray(vector.array, dtype=np.complex128).copy(),
            "action": np.asarray(action.array, dtype=np.complex128).copy(),
            "mass_action": np.asarray(mass_action.array, dtype=np.complex128).copy(),
        }
    finally:
        initial_copy.destroy()
        mass_action.destroy()
        action.destroy()
        vector.destroy()
        eps.destroy()


def solve_extreme_generalized_pairs(
    operator: PETSc.Mat, mass: PETSc.Mat, initial: PETSc.Vec
) -> dict[str, dict[str, Any]]:
    """Solve the fixed smallest/largest generalized Hermitian pair."""

    return {
        "smallest": _solve_one_eigenpair(
            operator, mass, initial, SLEPc.EPS.Which.SMALLEST_REAL
        ),
        "largest": _solve_one_eigenpair(
            operator, mass, initial, SLEPc.EPS.Which.LARGEST_REAL
        ),
    }


def csr_matvec(
    indptr: np.ndarray, indices: np.ndarray, values: np.ndarray, vector: np.ndarray
) -> np.ndarray:
    """Small independent CSR arithmetic used by the read-only checker/tests."""

    indptr = np.asarray(indptr, dtype=np.int64)
    indices = np.asarray(indices, dtype=np.int64)
    values = np.asarray(values, dtype=np.complex128)
    vector = np.asarray(vector, dtype=np.complex128)
    result = np.zeros(indptr.size - 1, dtype=np.complex128)
    for row in range(result.size):
        result[row] = np.dot(values[indptr[row] : indptr[row + 1]], vector[indices[indptr[row] : indptr[row + 1]]])
    return result


def apply_with_input_snapshot(
    matrix: PETSc.Mat, values: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Apply a matrix and return output plus the actual Vec before/after arrays."""

    source = matrix.createVecRight()
    target = matrix.createVecLeft()
    try:
        source.array[:] = np.asarray(values, dtype=np.complex128)
        before = np.asarray(source.array, dtype=np.complex128).copy()
        matrix.mult(source, target)
        after = np.asarray(source.array, dtype=np.complex128).copy()
        return np.asarray(target.array, dtype=np.complex128).copy(), before, after
    finally:
        target.destroy()
        source.destroy()


__all__ = [
    "DEGREE",
    "H_NM",
    "FULL_EDGE_ROWS",
    "SLAVE_EDGE_ROWS",
    "INDEPENDENT_EDGE_ROWS",
    "LINEARITY_ALPHA",
    "LINEARITY_BETA",
    "WORK_LIMIT",
    "LINEARITY_LIMIT",
    "REPEAT_LIMIT",
    "EIGEN_RESIDUAL_LIMIT",
    "SPECTRAL_CONDITION_LIMIT",
    "EPS_TOL",
    "EPS_MAX_IT",
    "EPS_NEV",
    "EPS_NCV",
    "EPS_ST_TYPE",
    "EPS_SHIFT",
    "EPS_KSP_TYPE",
    "EPS_PC_TYPE",
    "EPS_FACTOR_SOLVER",
    "relative",
    "scalar_relative",
    "build_independent_layout",
    "raw_slave_global_rows",
    "create_independent_submatrix",
    "embed_owner_values",
    "extract_owner_values",
    "PulledHighActionContext",
    "build_pulled_high_shell",
    "owner_to_high",
    "high_dual_to_owner",
    "work_identity_relative",
    "solve_extreme_generalized_pairs",
    "csr_matvec",
    "apply_with_input_snapshot",
]
