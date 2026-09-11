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


class V11Factor(Factor):
    controls = None
    compaction_supported = False

    def __init__(self, matrix):
        super().__init__(matrix)
        V11Factor.controls = {23: 0}

    def info(self, **kwargs):
        return {
            'info': {'1': 0}, 'rinfo': {'1': 0.0},
            'infog': {'16': 20, '17': 20, '19': 3, '22': 2, '29': 3},
            'rinfog': {'1': 0.0},
        }

    def get_icntl(self, index):
        if index == 49 and not self.compaction_supported:
            raise RuntimeError('MatMumpsGetIcntl(49) returned PETSc error code 62')
        return self.controls[index]

    def try_get_icntl(self, index):
        if index == 49 and not self.compaction_supported:
            return {'index': 49, 'supported': False, 'value': None, 'error_code': 62}
        return {'index': index, 'supported': True, 'value': self.controls[index], 'error_code': None}

    def set_icntl(self, index, value):
        self.events.append(('set_icntl', index, value))
        self.controls[index] = value

    def set_memory_limit_mb(self, value):
        self.set_icntl(23, value)


class FailingV11Factor(V11Factor):
    def numeric(self, matrix):
        self.events.append('numeric')
        raise RuntimeError('injected numeric failure')

    def info(self, **kwargs):
        value = super().info(**kwargs)
        value['info'].update({'1': 0, '2': -19})
        value['infog'].update({'1': 0, '2': -9, '9': -19, '19': -9})
        return value


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


def test_symbolic_sized_v11_formula_uses_decimal_mb_and_mpi1_fields():
    result = bounded.symbolic_sized_local_mumps_request(
        {'infog': {'16': 20, '17': 20}}, mpi_size=1,
    )
    assert result['estimate_bytes'] == 21_000_000
    assert result['minimum_request_bytes'] == 2 * 21_000_000 + 8 * 1024**2
    assert result['request_bytes'] == 51_000_000
    assert result['request_mb'] == 51
    with pytest.raises(ValueError, match='MPI1'):
        bounded.symbolic_sized_local_mumps_request(
            {'infog': {'16': 20, '17': 20}}, mpi_size=2,
        )
    with pytest.raises(RuntimeError, match=r'INFOG\(17\)'):
        bounded.symbolic_sized_local_mumps_request({'infog': {'16': 20, '17': -1}})
    with pytest.raises(RuntimeError, match='MPI1.*disagree'):
        bounded.symbolic_sized_local_mumps_request({'infog': {'16': 20, '17': 24}})


def test_v11_is_explicit_opt_in_and_unsupported_compaction_is_recorded(fake, monkeypatch):
    monkeypatch.setattr(bounded, '_MumpsFactor', V11Factor)
    factor = bounded.BoundedP1Factor(
        Matrix(), **fake, memory_policy=bounded.SYMBOLIC_SIZED_LOCAL_MUMPS_V11,
    )
    assert factor.audit['memory_policy'] == bounded.SYMBOLIC_SIZED_LOCAL_MUMPS_V11
    assert factor.audit['icntl23_requested_mb'] == 51
    assert factor.audit['icntl23_readback_mb'] == 51
    assert factor.audit['icntl49']['status'] == 'COMPACTION_UNSUPPORTED'
    assert factor.audit['numeric_raw']['info'] == {'1': 0}
    assert Factor.latest.events == [
        'symbolic', ('set_icntl', 23, 51), 'numeric',
    ]
    factor.destroy()


def test_v11_request_is_checked_against_hard_local_cap_before_numeric(fake, monkeypatch):
    monkeypatch.setattr(bounded, '_MumpsFactor', V11Factor)
    monkeypatch.setattr(bounded, 'LOCAL_FACTOR_MAX_BYTES', 2 * 116 + 32 * 1024**2)
    with pytest.raises(RuntimeError, match='512MiB|requested factor'):
        bounded.BoundedP1Factor(
            Matrix(), **fake, memory_policy=bounded.SYMBOLIC_SIZED_LOCAL_MUMPS_V11,
        )
    assert Factor.latest.events == ['symbolic', 'destroy']


def test_v11_numeric_failure_saves_raw_status_before_destroy(fake, monkeypatch):
    events = []
    monkeypatch.setattr(bounded, '_MumpsFactor', FailingV11Factor)
    with pytest.raises(RuntimeError, match='injected numeric failure'):
        bounded.BoundedP1Factor(
            Matrix(), **{**fake, 'marker': lambda stage, facts: events.append((stage, facts))},
            memory_policy=bounded.SYMBOLIC_SIZED_LOCAL_MUMPS_V11,
        )
    failed = [facts for stage, facts in events if stage == 'p1_numeric_failed']
    assert len(failed) == 1
    facts = failed[0]
    assert facts['numeric_failure_raw']['info']['2'] == -19
    assert facts['numeric_failure_raw']['infog']['9'] == -19
    assert facts['numeric_failure_codes']['INFO(2)'] == -19
    assert facts['numeric_failure_classification'] == 'NUMERIC_FAILED'
    assert FailingV11Factor.latest.events[-1] == 'destroy'


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


def test_actual_mumps_v11_controls_and_repeated_solve():
    from petsc4py import PETSc

    matrix = PETSc.Mat().createAIJ([3, 3], nnz=1, comm=PETSc.COMM_SELF)
    rhs = matrix.createVecRight()
    factor = None
    try:
        for i, value in enumerate((2 + 1j, 3 + 0.5j, 4 - 0.25j)):
            matrix.setValue(i, i, value)
        matrix.assemble()
        rhs.array[:] = (1.0 + 2.0j, 2.0 - 1.0j, 3.0 + 0.5j)
        factor = bounded.BoundedP1Factor(
            matrix,
            label='tiny_v11',
            resource_sample=lambda: dict(
                rss_bytes=100_000_000, launch_cap_bytes=12_000_000_000,
            ),
            marker=lambda *_: None,
            memory_policy=bounded.SYMBOLIC_SIZED_LOCAL_MUMPS_V11,
        )
        assert factor.audit['icntl23_readback_mb'] == factor.audit['symbolic_sized_request']['request_mb']
        assert factor.audit['icntl49']['status'] == 'COMPACTION_UNSUPPORTED'
        assert factor.audit['numeric_raw']['local_info_supported'] is True
        for scale in (1.0, 2.0):
            rhs.scale(scale)
            solution, facts = factor.solve_lean(rhs)
            try:
                checked = matrix.createVecRight()
                matrix.mult(solution, checked)
                checked.axpy(-1.0, rhs)
                assert checked.norm() / rhs.norm() < 1e-14
            finally:
                checked.destroy()
                solution.destroy()
        assert facts['solve_count'] == 2
    finally:
        if factor is not None:
            factor.destroy()
        rhs.destroy()
        matrix.destroy()
