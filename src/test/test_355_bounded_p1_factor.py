"""Budget/lifecycle tests; the only numeric case is a three-row matrix."""

import numpy as np
import pytest

from src.solvers import fullspace_bounded_mumps as bounded
from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor


class Matrix:
    def __init__(self, **info):
        self.info = dict(nz_used=3, nz_allocated=5, memory=0, **info)

    def getType(self):
        return 'seqaij'

    def getSize(self):
        return (3, 3)

    def getComm(self):
        return self

    def getInfo(self):
        return self.info

    def getValuesCSR(self):
        return np.arange(4, dtype=np.int32), np.arange(3, dtype=np.int32), np.ones(3, dtype=np.complex128)


class Comm:
    def getSize(self):
        return 1


class Factor:
    latest = None
    estimated = 0
    allocated = 0

    def __init__(self, matrix):
        self.events = []
        Factor.latest = self

    def symbolic(self, matrix):
        self.events.append('symbolic')

    def numeric(self, matrix):
        self.events.append('numeric')

    def info(self, **kwargs):
        return {'infog': {'17': self.estimated, '19': self.allocated, '22': 0, '29': 3}}

    def set_memory_limit_mb(self, value):
        self.events.append('budget')

    def destroy(self):
        self.events.append('destroy')


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(bounded, '_MumpsFactor', Factor)
    monkeypatch.setattr(Matrix, 'getComm', lambda self: Comm())
    monkeypatch.setattr(Factor, 'estimated', 0)
    monkeypatch.setattr(Factor, 'allocated', 0)
    return dict(label='test', resource_sample=lambda: dict(rss_bytes=1, launch_cap_bytes=12_000_000_000),
                marker=lambda stage, facts: None)


def test_unknown_allocator_has_derived_reserve_and_ordered_factor_lifecycle(fake):
    factor = bounded.BoundedP1Factor(Matrix(), **fake)
    assert factor.audit['matrix_petsc_allocator_bytes'] is None
    assert factor.audit['matrix_allocated_csr_storage_bytes'] == 4*4 + 5*20
    assert factor.audit['matrix_unobservable_overhead_reserve_bytes'] == 116 + 16*1024**2
    assert not factor.audit['reserve_is_proven_allocator_upper_bound']
    assert Factor.latest.events == ['symbolic', 'budget', 'numeric']
    factor.destroy()
    factor.destroy()
    assert Factor.latest.events.count('destroy') == 1


@pytest.mark.parametrize('field,value', [('nz_used', None), ('nz_allocated', None), ('nz_allocated', 2)])
def test_missing_or_inconsistent_actual_nnz_fails_before_factor(fake, field, value):
    matrix = Matrix()
    matrix.info[field] = value
    with pytest.raises(RuntimeError, match='NNZ'):
        bounded.BoundedP1Factor(matrix, **fake)


@pytest.mark.parametrize('estimate', [None, -1, 600])
def test_missing_or_overbudget_symbolic_never_starts_numeric(fake, monkeypatch, estimate):
    monkeypatch.setattr(Factor, 'estimated', estimate)
    with pytest.raises(RuntimeError):
        bounded.BoundedP1Factor(Matrix(), **fake)
    assert Factor.latest.events == ['symbolic', 'destroy']


def test_exact_cap_passes_but_one_byte_less_cap_fails(fake, monkeypatch):
    matrix_budget = 2*116 + 16*1024**2
    monkeypatch.setattr(bounded, 'LOCAL_FACTOR_MAX_BYTES', matrix_budget + 1_000_000)
    bounded.BoundedP1Factor(Matrix(), **fake).destroy()
    monkeypatch.setattr(bounded, 'LOCAL_FACTOR_MAX_BYTES', matrix_budget + 999_999)
    with pytest.raises(RuntimeError, match='512MiB'):
        bounded.BoundedP1Factor(Matrix(), **fake)
    assert Factor.latest.events == ['symbolic', 'destroy']


def test_numeric_report_over_cap_releases_factor(fake, monkeypatch):
    monkeypatch.setattr(Factor, 'allocated', 600)
    with pytest.raises(RuntimeError, match='reported factor'):
        bounded.BoundedP1Factor(Matrix(), **fake)
    assert Factor.latest.events == ['symbolic', 'budget', 'numeric', 'destroy']


def test_actual_mumps_repeated_solve_and_old_one_shot_contract():
    from petsc4py import PETSc

    matrix = PETSc.Mat().createAIJ([3, 3], nnz=1, comm=PETSc.COMM_SELF)
    rhs = matrix.createVecRight()
    solution = rhs.duplicate()
    coarse = old = None
    try:
        for i in range(3):
            matrix.setValue(i, i, 2+1j+i)
        matrix.assemble()
        rhs.set(1+2j)
        coarse = bounded.BoundedP1Factor(matrix, label='tiny_shifted',
            resource_sample=lambda: dict(rss_bytes=100_000_000, launch_cap_bytes=12_000_000_000),
            marker=lambda stage, facts: None)
        for scale in (1, 3):
            rhs.set(scale*(1+2j))
            answer, facts = coarse.solve_lean(rhs)
            try:
                matrix.mult(answer, solution)
                solution.axpy(-1, rhs)
                assert solution.norm()/rhs.norm() < 1e-14
            finally:
                answer.destroy()
        assert facts['solve_count'] == 2
        coarse.destroy()
        with pytest.raises(RuntimeError, match='destroyed'):
            coarse.solve_lean(rhs)
        old = _MumpsFactor(matrix)
        old.symbolic(matrix)
        old.numeric(matrix)
        old.solve(rhs, solution)
        with pytest.raises(RuntimeError, match='lifecycle'):
            old.solve(rhs, solution)
    finally:
        if coarse is not None:
            coarse.destroy()
        if old is not None:
            old.destroy()
        solution.destroy()
        rhs.destroy()
        matrix.destroy()
