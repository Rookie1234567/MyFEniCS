import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.static_modal_coarse_basis import (
    OwnerLocalBasis,
    audit_owner_local_action_space,
    normalize_owner_local_columns,
    solve_homogeneous_prescribed_interface,
)


def _aij(values: np.ndarray) -> PETSc.Mat:
    values = np.asarray(values, dtype=PETSc.ScalarType)
    rows, columns = values.shape
    matrix = PETSc.Mat().createAIJ(
        size=(rows, columns),
        nnz=columns,
        comm=MPI.COMM_SELF,
    )
    matrix.setUp()
    matrix.setValues(
        np.arange(rows, dtype=PETSc.IntType),
        np.arange(columns, dtype=PETSc.IntType),
        values,
    )
    matrix.assemble()
    return matrix


def test_research_opt_in_normalization_and_owner_local_action_identity():
    local = np.asarray(
        [
            [1.0 + 1.0j, 0.0, 1.0],
            [1.0 + 1.0j, 0.0, 0.0],
            [0.0, 2.0 - 2.0j, 0.0],
            [0.0, 0.0, 1.0j],
        ],
        dtype=np.complex128,
    )
    with pytest.raises(ValueError, match="research-only"):
        OwnerLocalBasis.from_local_array(
            local,
            global_rows=4,
            comm=MPI.COMM_SELF,
            label="Z",
        )
    basis = OwnerLocalBasis.from_local_array(
        local,
        global_rows=4,
        comm=MPI.COMM_SELF,
        label="Z",
        research_opt_in=True,
    )
    normalized, audits = normalize_owner_local_columns(
        basis,
        research_opt_in=True,
    )
    operator = _aij(
        np.asarray(
            [
                [2.0 + 0.1j, 0.2 - 0.1j, 0.0, 0.0],
                [0.0, 1.5 - 0.2j, 0.3, 0.0],
                [0.1, 0.0, 1.2 + 0.3j, 0.2j],
                [0.0, 0.0, 0.4, 0.8 - 0.1j],
            ]
        )
    )
    action = normalized.apply(operator, research_opt_in=True)
    rng = np.random.default_rng(17037)
    coefficient = rng.standard_normal(3) + 1j * rng.standard_normal(3)
    source = normalized.combine(coefficient, research_opt_in=True)
    observed = action.combine(coefficient, research_opt_in=True)
    expected = operator.createVecLeft()
    difference = expected.duplicate()
    try:
        operator.mult(source, expected)
        expected.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), observed)
        assert difference.norm() <= 1.0e-13
        assert audits[0].pivot_global_row == 0
        assert all(abs(audit.norm_after - 1.0) <= 1.0e-13 for audit in audits)
        for vector, audit in zip(normalized.columns, audits, strict=True):
            values = vector.getArray(readonly=True)
            pivot = values[audit.pivot_global_row]
            assert pivot.real >= -1.0e-14
            assert abs(pivot.imag) <= 1.0e-14
            assert normalized.ownership_range == (0, 4)
        assert normalized.local_matrix().shape == (4, 3)
        action_audit = audit_owner_local_action_space(
            action,
            research_opt_in=True,
        )
        assert action_audit.effective_rank == 3
        assert np.isfinite(action_audit.retained_condition_number)
        assert action_audit.normal_equations_used is False
    finally:
        difference.destroy()
        expected.destroy()
        observed.destroy()
        source.destroy()
        action.destroy()
        operator.destroy()
        normalized.destroy()
        basis.destroy()


def test_stacked_r_svd_reports_known_rank_without_normal_equations():
    basis = OwnerLocalBasis.from_local_array(
        np.asarray(
            [
                [1.0, 0.0, 1.0],
                [0.0, 1.0, 1.0],
                [0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0],
            ]
        ),
        global_rows=4,
        comm=MPI.COMM_SELF,
        label="Y",
        research_opt_in=True,
    )
    try:
        audit = audit_owner_local_action_space(
            basis,
            rank_tolerance=1.0e-12,
            research_opt_in=True,
        )
        assert audit.effective_rank == 2
        assert np.isfinite(audit.retained_condition_number)
        assert audit.retained_condition_number == pytest.approx(np.sqrt(3.0))
        assert audit.local_qr_method == "scipy.linalg.qr"
        assert audit.stacked_r_svd_method.endswith("scipy.linalg.svd")
        assert audit.normal_equations_used is False
        assert len(audit.singular_values) == 3
    finally:
        basis.destroy()


class _FixtureFactor:
    def __init__(self, matrix: np.ndarray):
        self.matrix = matrix
        self.destroyed = False

    def solve(self, rhs: np.ndarray) -> np.ndarray:
        return np.linalg.solve(self.matrix, rhs)

    def destroy(self) -> None:
        self.destroyed = True


def test_prescribed_interface_partition_solves_retained_rows_and_releases_factor():
    matrix = np.asarray(
        [
            [2.0 + 0.2j, 0.3, 1.0 - 0.5j],
            [0.1, 1.5 - 0.1j, -0.4j],
            [0.7 + 0.2j, 0.4, 2.0 + 0.3j],
        ],
        dtype=np.complex128,
    )
    factor_box: list[_FixtureFactor] = []

    def make_factor(retained_matrix: np.ndarray) -> _FixtureFactor:
        factor = _FixtureFactor(retained_matrix)
        factor_box.append(factor)
        return factor

    result = solve_homogeneous_prescribed_interface(
        matrix,
        interface_rows=(2,),
        interface_values=(1.0 - 2.0j,),
        factor_factory=make_factor,
        research_opt_in=True,
    )
    assert result.interface_rows == (2,)
    assert result.retained_rows == (0, 1)
    assert result.factor_released is True
    assert factor_box[0].destroyed is True
    assert result.values[2] == 1.0 - 2.0j
    assert result.retained_residual_norm <= 1.0e-12
    assert result.retained_residual_relative <= 1.0e-12


def test_comm_world_owner_local_collective_semantics():
    comm = MPI.COMM_WORLD
    local_rows = 2
    global_rows = local_rows * comm.size
    local = np.zeros((local_rows, 2), dtype=np.complex128)
    local[0, 1] = 1.0 + 0.0j
    if comm.rank == 0:
        local[0, 0] = 1.0 + 1.0j
    if comm.rank == comm.size - 1:
        local[-1, 0] = 1.0 + 1.0j
    basis = OwnerLocalBasis.from_local_array(
        local,
        global_rows=global_rows,
        comm=comm,
        label="Z_mpi",
        research_opt_in=True,
    )
    normalized, audits = normalize_owner_local_columns(
        basis,
        research_opt_in=True,
    )
    operator = PETSc.Mat().createAIJ(
        size=(global_rows, global_rows),
        nnz=1,
        comm=comm,
    )
    operator.setUp()
    first, last = map(int, operator.getOwnershipRange())
    for row in range(first, last):
        operator.setValue(row, row, PETSc.ScalarType(1.0 + 0.25j))
    operator.assemble()
    action = normalized.apply(operator, research_opt_in=True)
    coefficients = np.asarray(
        [0.25 - 0.5j, -0.75 + 0.125j],
        dtype=np.complex128,
    )
    source = normalized.combine(coefficients, research_opt_in=True)
    observed = action.combine(coefficients, research_opt_in=True)
    expected = operator.createVecLeft()
    difference = expected.duplicate()
    try:
        operator.mult(source, expected)
        expected.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), observed)
        assert difference.norm() <= 1.0e-13
        assert audits[0].pivot_global_row == 0
        assert all(abs(audit.norm_after - 1.0) <= 1.0e-13 for audit in audits)
        pivot_values = []
        first, last = map(int, normalized.columns[0].getOwnershipRange())
        values = normalized.columns[0].getArray(readonly=True)
        for row in (0, global_rows - 1):
            pivot_values.append(
                complex(values[row - first]) if first <= row < last else None
            )
        gathered = comm.allgather(pivot_values)
        owned_pivots = [
            value for packet in gathered for value in packet if value is not None
        ]
        assert len(owned_pivots) == 2
        assert abs(owned_pivots[0].imag) <= 1.0e-14
        assert owned_pivots[0].real > 0.0
        audit = audit_owner_local_action_space(
            action,
            research_opt_in=True,
        )
        assert audit.effective_rank == 2
        assert np.isfinite(audit.retained_condition_number)
        assert comm.allreduce(audit.effective_rank, op=MPI.MIN) == 2
        assert comm.allreduce(audit.effective_rank, op=MPI.MAX) == 2
    finally:
        difference.destroy()
        expected.destroy()
        observed.destroy()
        source.destroy()
        action.destroy()
        operator.destroy()
        normalized.destroy()
        basis.destroy()
