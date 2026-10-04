"""Structural-skipping qualification; synthetic NumPy/SciPy algebra only."""
from __future__ import annotations

import sys
import weakref

import numpy as np
import pytest
from scipy import sparse

from src.solvers import bounded_compact_q_projection as candidate
# Load the immutable owned baseline blob; available in the public parent tree.
import hashlib
import subprocess
import types
from pathlib import Path
_baseline_bytes = subprocess.check_output(["git", "cat-file", "blob", "235892c6bd8692aef6e9059611fdd9cdcf9fc688"],
    cwd=Path(__file__).resolve().parents[2])
assert hashlib.sha256(_baseline_bytes).hexdigest() == "ac7f73b51ce67e7a0655ab71af1136c56d70f86ca1c4e42a1634782b0672f925"
baseline = types.ModuleType("src.solvers._exact_tile_support_baseline")
baseline.__package__ = "src.solvers"
exec(compile(_baseline_bytes, "owned_baseline_blob_235892c6", "exec"), baseline.__dict__)
from src.solvers.original_port_blocks import CachedPortCorrection, DiagonalOriginalPortBlock
from src.solvers.y_orbit_two_cell_block_audit import TwoCellBlockProvider
from src.test.test_bounded_compact_q_projection import (
    dense_recipe, fake_provider_fixture, log_gate, random_complex, readonly,
)


def accumulator(module, shape, budget=128 * 1024**2, width=2, gate=None):
    return module.BoundedCompactQAccumulator(
        shape, max_owned_bytes=budget, tile_width=width,
        index_dtype=np.int32, gate=gate or (lambda *args, **kwargs: None))


def bitwise_csr(a, b):
    assert a.shape == b.shape
    for field in ('data', 'indices', 'indptr'):
        left, right = getattr(a, field), getattr(b, field)
        assert left.dtype == right.dtype
        assert left.shape == right.shape
        assert left.tobytes() == right.tobytes(), field


@pytest.mark.parametrize('kind', ['diagonal', 'dense'])
@pytest.mark.parametrize('p,q', [(0, 0), (0, 1), (1, 0), (1, 1)])
def test_all_eight_provider_pairs_bitwise_previous_bounded_and_dense_oracle(monkeypatch, kind, p, q):
    condensed, coords, maps, native = fake_provider_fixture(kind)
    # Leave both active and fully empty width-2 tiles in the real provider
    # call path for every p/q pair, rather than only isolated helper tests.
    for matrix in maps:
        for row in range(matrix.shape[0]):
            for k in range(int(matrix.indptr[row]), int(matrix.indptr[row + 1])):
                if int(matrix.indices[k]) < 2:
                    matrix.data[k] = 0
        matrix.eliminate_zeros()
    events = []
    provider = TwoCellBlockProvider(condensed, coords,
        allocation_gate=lambda name, facts: events.append((name, facts)),
        compact_projection_max_owned_bytes=128 * 1024**2,
        compact_projection_tile_width=2)
    actual = provider.block(p, q)
    with monkeypatch.context() as context:
        context.setattr(candidate, 'BoundedCompactQAccumulator', baseline.BoundedCompactQAccumulator)
        reference = TwoCellBlockProvider(condensed, coords, allocation_gate=lambda *args: None,
            compact_projection_max_owned_bytes=128 * 1024**2,
            compact_projection_tile_width=2).block(p, q)
    bitwise_csr(actual, reference)
    expected = maps[p].toarray().conj().T @ native @ maps[q].toarray()
    np.testing.assert_allclose(actual.toarray(), expected, rtol=4e-13, atol=4e-13)
    assert any('/support_discovery/' in name for name, _ in events)
    assert events[-1][1]['tiles_skipped_structural'] > 0
    assert all(facts.get('numeric_factor_count', 0) == 0 for _, facts in events)
    assert all(facts.get('projection_owned_upper_bytes', 0) <= 128 * 1024**2 for _, facts in events)


@pytest.mark.parametrize('width', [1, 2, 4, 17])
@pytest.mark.parametrize('kind', ['dense', 'diagonal', 'factorized'])
def test_selected_native_rows_tile_gaps_and_recipe_bitwise(width, kind):
    rng = np.random.default_rng(20261004)
    l, r = np.zeros((5, 13), complex), np.zeros((5, 17), complex)
    l[:, [0, 2, 8, 12]] = random_complex(rng, (5, 4))
    r[:, [1, 6, 16]] = random_complex(rng, (5, 3))
    # Unselected rows have wider support and must not influence the schedule.
    l[1, :], r[1, :] = random_complex(rng, (13,)), random_complex(rng, (17,))
    rows, cols = np.array([4, 2, 0]), np.array([0, 4, 3])
    if kind == 'dense':
        value = readonly(random_complex(rng, (3, 3)))
    elif kind == 'diagonal':
        value = DiagonalOriginalPortBlock(np.array([1, 2j, -.4 + .7j]), tuple(('mode', i) for i in range(3)))
    else:
        value = CachedPortCorrection(readonly(np.arange(3), np.int32),
            readonly(random_complex(rng, (3, 2))), readonly(random_complex(rng, (2, 3))))
    maps = sparse.csr_matrix(l), sparse.csr_matrix(r)
    actual, reference = accumulator(candidate, (13, 17), width=width), accumulator(baseline, (13, 17), width=width)
    for sign in (1, -1, 1):
        # Recipe objects are borrowed unchanged; repeat accumulation also checks
        # that skipping preserves cancellation and addition order.
        recipe = value if sign == 1 else readonly(-dense_recipe(value))
        for acc in (actual, reference):
            acc.add(*maps, rows, cols, recipe, 'selected')
    bitwise_csr(actual.finish(), reference.finish())
    np.testing.assert_allclose(actual.result.toarray(), l[rows].conj().T @ dense_recipe(value) @ r[cols],
                               rtol=4e-13, atol=4e-13)


@pytest.mark.parametrize('empty', ['left', 'right', 'both'])
def test_empty_maps_skip_all_projection_admissions(empty):
    full = sparse.eye(5, format='csr', dtype=complex)
    zero = sparse.csr_matrix((5, 5), dtype=complex)
    left = zero if empty in ('left', 'both') else full
    right = zero if empty in ('right', 'both') else full
    events, gate = log_gate()
    acc = accumulator(candidate, (5, 5), width=2, gate=gate)
    acc.add(left, right, np.arange(5), np.arange(5), np.eye(5, dtype=complex), 'empty')
    assert acc.finish().nnz == 0
    assert acc.tiles_skipped_structural == 9
    assert not any('/projection/' in name for name, _ in events)
    assert sum('/support_discovery/' in name for name, _ in events) == 1


def test_explicit_stored_zeros_and_duplicate_cancellation_remain_structural_support():
    # Columns 1 and 7 have zero numeric gathers but remain stored support.
    left = sparse.csr_matrix((np.array([0, 2, 1, -1, 0], complex),
                             np.array([1, 3, 5, 5, 7]), np.array([0, 5])), shape=(1, 8))
    right = sparse.csr_matrix((np.array([0, 3, 0], complex),
                              np.array([1, 3, 7]), np.array([0, 3])), shape=(1, 8))
    events, gate = log_gate()
    actual = accumulator(candidate, (8, 8), width=2, gate=gate)
    reference = accumulator(baseline, (8, 8), width=2)
    for acc in (actual, reference):
        acc.add(left, right, np.array([0]), np.array([0]), np.array([[2j]]), 'storedzero')
    bitwise_csr(actual.finish(), reference.finish())
    # Left occupies all four tiles, right three: exactly 12 admissions, even
    # though numeric zeros/cancelling duplicates make only one product nonzero.
    assert sum('/projection/' in name for name, _ in events) == 12
    assert actual.tiles_skipped_structural == 4
    assert left.nnz == 5 and right.nnz == 3


@pytest.mark.parametrize('dtype', [np.int32, np.int64])
def test_actual_csr_index_width_and_exact_discovery_array_lifetimes(monkeypatch, dtype):
    maps = sparse.csr_matrix([[0, 1, 0, 0, 2, 0]], dtype=complex)
    maps.indices = maps.indices.astype(dtype)
    maps.indptr = maps.indptr.astype(dtype)
    references = []
    zeros, gather = np.zeros, candidate._gather_tile
    def checked_zeros(shape, *args, **kwargs):
        out = zeros(shape, *args, **kwargs)
        if out.dtype == np.dtype(np.bool_):
            references.append(weakref.ref(out))
        return out
    def checked_gather(*args):
        assert len(references) == 2
        assert all(reference() is None for reference in references)
        return gather(*args)
    events, gate = log_gate()
    acc = accumulator(candidate, (6, 6), width=2, gate=gate)
    monkeypatch.setattr(np, 'zeros', checked_zeros)
    monkeypatch.setattr(candidate, '_gather_tile', checked_gather)
    acc.add(maps, maps, np.array([0]), np.array([0]), np.array([[1j]]), 'width')
    acc.finish()
    support = [facts for name, facts in events if '/support_discovery/' in name][0]
    assert support['matrix_payload_bytes'] == support['support_mask_entries'] == 6
    assert support['support_mask_itemsize_bytes'] == 1
    assert support['left_CSR_index_itemsize_bytes'] == np.dtype(dtype).itemsize
    assert support['left_CSR_indptr_itemsize_bytes'] == np.dtype(dtype).itemsize
    assert support['right_CSR_index_itemsize_bytes'] == np.dtype(dtype).itemsize
    assert support['right_CSR_indptr_itemsize_bytes'] == np.dtype(dtype).itemsize
    assert all(reference() is None for reference in references)


@pytest.mark.parametrize('case', ['initial_width', 'growing_result', 'merge_retry'])
def test_changing_width_and_recursive_splits_remain_bitwise(case):
    if case == 'initial_width':
        maps = sparse.csr_matrix(np.ones((10, 7), complex))
        rows, value, shape, budget, width = np.arange(10), np.ones((10, 10), complex), (7, 7), 3500, 100
    elif case == 'growing_result':
        maps = sparse.csr_matrix(np.ones((100, 8), complex))
        rows, value, shape, budget, width = np.arange(100), np.ones((100, 100), complex), (8, 8), 10000, 8
    else:
        maps = sparse.eye(4, dtype=complex, format='csr')
        rows, value, shape, budget, width = np.arange(4), np.ones((4, 4), complex), (4, 4), 1050, 4
    events, gate = log_gate()
    actual = accumulator(candidate, shape, budget, width, gate)
    reference = accumulator(baseline, shape, budget, width)
    for acc in (actual, reference):
        for _ in range(2 if case == 'merge_retry' else 1):
            acc.add(maps, maps, rows, rows, value, case)
    bitwise_csr(actual.finish(), reference.finish())
    dimensions = {(facts['tile_rows'], facts['tile_columns']) for name, facts in events if '/projection/' in name}
    assert any(min(dim) < width for dim in dimensions)
    assert actual.peak_owned_upper_bytes <= budget


def test_recursive_children_with_empty_intervals_skip_without_admission(monkeypatch):
    maps = sparse.csr_matrix([[1, 0, 0, 0, 0, 0, 0, 2]], dtype=complex)
    rows = np.array([0])
    actual, reference = accumulator(candidate, (8, 8), width=8), accumulator(baseline, (8, 8), width=8)
    # Force only the initial merge to retry, identically in both implementations.
    for acc in (actual, reference):
        merge = acc._merge
        def retry_once(tile, p, q, label, merge=merge, first=[True]):
            if first[0]:
                first[0] = False
                return 1
            return merge(tile, p, q, label)
        monkeypatch.setattr(acc, '_merge', retry_once)
        acc.add(maps, maps, rows, rows, np.array([[2 + .5j]]), 'recursive')
    bitwise_csr(actual.finish(), reference.finish())
    # Direct recursive children can be narrower than the original width.
    events, gate = log_gate()
    actual.gate = gate
    actual._project_tile(maps, maps, rows, rows, np.array([[1j]]), 'empty_child', 2, 4, 0, 8)
    assert not events and actual.tiles_skipped_structural == 1


def test_discovery_budget_rejection_precedes_allocation(monkeypatch):
    shape = (1, 100000)
    acc = accumulator(candidate, shape, budget=200, width=1)
    left, right = sparse.csr_matrix([[1]], dtype=complex), sparse.csr_matrix((1, shape[1]), dtype=complex)
    def forbidden(*args, **kwargs):
        raise AssertionError('discovery allocation occurred after budget rejection')
    monkeypatch.setattr(np, 'zeros', forbidden)
    with pytest.raises(MemoryError, match='before support_discovery/.*support-discovery scratch'):
        acc.add(left, right, np.array([0]), np.array([0]), np.array([[1j]]), 'discovery_capacity')


def test_fresh_whole_rss_discovery_denial_precedes_allocation(monkeypatch):
    acc = accumulator(candidate, (2, 2))
    maps = sparse.eye(2, format='csr', dtype=complex)
    def deny(name, **facts):
        assert '/support_discovery/' in name
        assert facts['projection_owned_upper_bytes'] <= acc.budget
        raise MemoryError('whole RSS discovery denial')
    def forbidden(*args, **kwargs):
        raise AssertionError('support arrays allocated after whole RSS denial')
    acc.gate = deny
    monkeypatch.setattr(np, 'zeros', forbidden)
    with pytest.raises(MemoryError, match='whole RSS discovery denial'):
        acc.add(maps, maps, np.arange(2), np.arange(2), np.eye(2), 'denied')


def test_fresh_whole_rss_schedule_denial_precedes_python_tuple_construction(monkeypatch):
    acc = accumulator(candidate, (2, 2))
    maps = sparse.eye(2, format='csr', dtype=complex)
    def gate(name, **facts):
        if '/support_schedule/' in name:
            assert facts['workspace'] == facts['support_Python_tuple_workspace_allowance_bytes'] > 0
            assert facts['fresh_RSS_allowance_conservatively_recounts_current_support_masks']
            raise MemoryError('whole RSS schedule denial')
    def forbidden(*args, **kwargs):
        raise AssertionError('Python support tuple constructed after RSS denial')
    acc.gate = gate
    monkeypatch.setattr(candidate, 'tuple', forbidden, raising=False)
    with pytest.raises(MemoryError, match='whole RSS schedule denial'):
        acc.add(maps, maps, np.arange(2), np.arange(2), np.eye(2), 'schedule_denied')


def test_structural_discovery_reads_wide_stored_indices_without_cast_or_overflow():
    last = 2**31 + 17
    matrix = sparse.csr_matrix((np.array([0j, 1j]), np.array([0, last], np.int64),
                                np.array([0, 2], np.int64)), shape=(1, last + 1))
    assert matrix.indices.dtype == np.dtype(np.int64)
    support = np.zeros(3, dtype=np.bool_)
    candidate._mark_stored_tiles(matrix, np.array([0]), 2**30, support)
    np.testing.assert_array_equal(support, [True, False, True])
    assert candidate._has_stored_column(matrix, [0], last, last + 1)
    assert not candidate._has_stored_column(matrix, [0], 1, last)


@pytest.mark.parametrize('bad', ['unsorted', 'duplicate', 'column_oob', 'pointer', 'nonfinite'])
def test_provider_rejects_bad_csr_before_support_discovery(bad):
    condensed, coords, maps, _ = fake_provider_fixture('diagonal')
    left = maps[0]
    if bad == 'unsorted':
        left.indices[0], left.indices[1] = left.indices[1], left.indices[0]
    elif bad == 'duplicate':
        left.indices[1] = left.indices[0]
    elif bad == 'column_oob':
        left.indices[0] = left.shape[1]
    elif bad == 'pointer':
        left.indptr[1] = -1
    else:
        left.data[0] = np.nan
    events = []
    provider = TwoCellBlockProvider(condensed, coords,
        allocation_gate=lambda name, facts: events.append((name, facts)),
        compact_projection_max_owned_bytes=128 * 1024**2)
    with pytest.raises(ValueError, match='bounded compact CSR'):
        provider.block(0, 1)
    assert not any('/support_discovery/' in name for name, _ in events)


def test_direct_accumulator_unsorted_duplicates_bitwise_borrowed_unchanged():
    maps = sparse.csr_matrix((np.array([3j, 2, -1j, 0], complex),
                             np.array([5, 1, 5, 3]), np.array([0, 4])), shape=(1, 8))
    snapshots = tuple(getattr(maps, name).copy() for name in ('data', 'indices', 'indptr'))
    actual, reference = accumulator(candidate, (8, 8)), accumulator(baseline, (8, 8))
    for acc in (actual, reference):
        acc.add(maps, maps, np.array([0]), np.array([0]), np.array([[1 - 2j]]), 'duplicates')
    bitwise_csr(actual.finish(), reference.finish())
    for name, snapshot in zip(('data', 'indices', 'indptr'), snapshots, strict=True):
        np.testing.assert_array_equal(getattr(maps, name), snapshot)


@pytest.mark.parametrize('bad', ['dense_nonfinite', 'dense_shape', 'row_order', 'row_duplicate',
                                 'unknown_label', 'duplicate_label', 'missing_label',
                                 'H_identity', 'correction_identity'])
def test_structurally_empty_maps_do_not_bypass_source_recipe_validation(bad):
    condensed, coords, maps, _ = fake_provider_fixture('diagonal')
    contributions = list(condensed.iter_contributions())
    maps[:] = [sparse.csr_matrix(matrix.shape, dtype=complex) for matrix in maps]
    rows, cols, values, label = contributions[1]
    if bad == 'dense_nonfinite':
        replacement = values.copy()
        replacement[0, 0] = np.nan
        contributions[1] = rows, cols, readonly(replacement), label
    elif bad == 'dense_shape':
        contributions[1] = rows, cols, readonly(np.ones((1, 1), complex)), label
    elif bad == 'row_order':
        contributions[1] = readonly(rows[::-1], np.int32), cols, values, label
    elif bad == 'row_duplicate':
        contributions[1] = readonly([rows[0], rows[0]], np.int32), cols, values, label
    elif bad == 'unknown_label':
        contributions[1] = rows, cols, values, 'unknown'
    elif bad == 'duplicate_label':
        contributions.append(contributions[1])
    elif bad == 'missing_label':
        contributions.pop(1)
    elif bad == 'H_identity':
        r, c, h, name = contributions[0]
        contributions[0] = r, c, DiagonalOriginalPortBlock(h.diagonal, h.mode_keys), name
    else:
        r, c, value, name = contributions[4]
        contributions[4] = r, c, CachedPortCorrection(value.port_indices, readonly(value.Di.copy()), value.XiB), name
    condensed.iter_contributions = lambda **kwargs: iter(contributions)
    provider = TwoCellBlockProvider(condensed, coords, allocation_gate=lambda *args: None,
        compact_projection_max_owned_bytes=128 * 1024**2)
    with pytest.raises(ValueError):
        provider.block(0, 1)


def test_tests_do_not_import_fe_jit_packages():
    # Qualified activation ran its separate ABI preflight before this process.
    assert not any(name.split('.')[0] in {'dolfinx', 'basix', 'ffcx', 'petsc4py', 'mpi4py'}
                   for name in sys.modules)
