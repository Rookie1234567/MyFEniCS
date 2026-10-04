"""Synthetic c81 bitwise equivalence only; no saved scientific arrays or FE."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import pathlib
import sys
import weakref

import numpy as np
import pytest
from scipy import sparse

REPO = pathlib.Path(__file__).resolve().parents[2]
import subprocess
from src.solvers import bounded_compact_q_projection as candidate
from src.solvers.fresh_projection_support_replay import load_verified_accumulator
BASELINE_BLOB = 'ce9dc6a67be3188da6e9d5d9dd2fb63f249a373a'
BASELINE_SHA256 = '02a11ce42b8a075d0aa4508c659d5327110be37be6ce74dad9259f58ff11e0e0'
BASELINE_BYTES = subprocess.check_output(['git', 'cat-file', 'blob', BASELINE_BLOB], cwd=REPO)
base_class = load_verified_accumulator(BASELINE_BYTES, expected_sha256=BASELINE_SHA256, git_blob=BASELINE_BLOB)
baseline = sys.modules[base_class.__module__]


def bits(values):
    return values.dtype.str, values.shape, values.tobytes()


def same_csr(left, right):
    assert left.shape == right.shape
    for x, y in zip((left.data, left.indices, left.indptr),
                    (right.data, right.indices, right.indptr), strict=True):
        assert bits(x) == bits(y)


def acc(module, shape, *, budget=10**8, width=8, dtype=np.int32):
    events = []
    obj = module.BoundedCompactQAccumulator(shape, max_owned_bytes=budget,
        tile_width=width, index_dtype=dtype,
        gate=lambda name, **facts: events.append((name, facts)))
    return obj, events


def direct_merge(old, tile, first_p=0, first_q=0, *, budget=10**8, dtype=np.int32):
    one, events_one = acc(baseline, old.shape, budget=budget, dtype=dtype)
    two, events_two = acc(candidate, old.shape, budget=budget, dtype=dtype)
    one.result, two.result = old.copy(), old.copy()
    before = tuple(bits(x) for x in (old.data, old.indices, old.indptr, tile))
    result_one = one._merge(tile, first_p, first_q, 'synthetic')
    result_two = two._merge(tile, first_p, first_q, 'synthetic')
    assert result_one == result_two
    same_csr(one.result, two.result)
    assert before == tuple(bits(x) for x in (old.data, old.indices, old.indptr, tile))
    assert all(facts['projection_owned_upper_bytes'] <= budget for _, facts in events_two)
    return one, two, events_one, events_two


def complex_bits(pairs):
    return np.array(pairs, dtype=np.float64).view(np.complex128).reshape(-1)


@pytest.mark.parametrize('old_index_dtype', [np.int32, np.int64])
def test_signed_zero_explicit_zero_and_outside_copy_bits(old_index_dtype):
    old = sparse.csr_matrix((complex_bits([
        (0., -0.), (3., -0.), (-0., 0.), (2., -0.), (0., -3.),
        (0., 0.), (-2., 0.), (7., 0.), (0., -0.), (9., -0.)]),
        np.array([0, 7, 0, 2, 4, 7, 1, 6, 0, 7], dtype=old_index_dtype),
        np.array([0, 2, 6, 8, 10], dtype=old_index_dtype)), shape=(4, 8))
    old.indices = old.indices.astype(old_index_dtype)
    old.indptr = old.indptr.astype(old_index_dtype)
    # Affected rows 1/2: old zeros outside the tile must be removed, untouched
    # row 0/3 zeros retained; overlap cancellation exactly removes columns 2/1.
    tile = complex_bits([(4., -0.), (-2., 0.), (0., -0.), (0., 0.),
                         (2., -0.), (0., -6.), (-0., 5.), (0., -0.)]).reshape(2, 4)
    old.data.flags.writeable = False
    tile.flags.writeable = False
    _, two, _, _ = direct_merge(old, tile, 1, 1)
    assert two.row_merges_vectorized == 1
    assert two.result.data[0].imag == 0 and np.signbit(two.result.data[0].imag)
    row = two.result.data[two.result.indptr[1]:two.result.indptr[2]]
    assert bits(row[0:1]) == bits(tile[0, :1])


@pytest.mark.parametrize('support', ['dense', 'sparse', 'explicit_zero'])
@pytest.mark.parametrize('width', [1, 3, 16, 64])
def test_random_rows_compare_exact_bytes(support, width):
    rng = np.random.default_rng(93423 + width)
    for attempt in range(20):
        shape = (7, 2 * width + 5)
        original = rng.normal(size=shape) + 1j * rng.normal(size=shape)
        if support != 'dense':
            original[rng.random(shape) < .8] = 0
        old = sparse.csr_matrix(original)
        if support == 'explicit_zero' and old.nnz:
            old.data[::3] = complex(-0., -0.)
        tile = rng.normal(size=(3, width)) + 1j * rng.normal(size=(3, width))
        tile[rng.random(tile.shape) < .5] = 0
        # Force exact overlap cancellation without tolerance-based dropping.
        for row in range(2, 5):
            for k in range(old.indptr[row], old.indptr[row + 1]):
                col = old.indices[k]
                if 1 <= col < width + 1 and k % 2 == 0:
                    tile[row - 2, col - 1] = -old.data[k]
        _, two, _, _ = direct_merge(old, tile, 2, 1)
        assert two.row_merges_vectorized == 1
        candidate.audit_csr_scalar(two.result, index_dtype=np.int32)


@pytest.mark.parametrize('value', [complex(np.inf, 0), complex(0, -np.inf), complex(np.nan, 2)])
def test_nonfinite_tile_and_overlap_exception_leave_old_unchanged(value):
    old = sparse.csr_matrix(np.eye(3, dtype=complex))
    tile = np.ones((2, 2), dtype=complex)
    tile[0, 1] = value
    for module in (baseline, candidate):
        obj, _ = acc(module, old.shape)
        obj.result = old.copy()
        with np.errstate(over='ignore', invalid='ignore'):
            with pytest.raises(FloatingPointError, match='accumulation produced a nonfinite entry'):
                obj._merge(tile, 0, 0, 'bad')
        same_csr(obj.result, old)


@pytest.mark.parametrize('budget', [200, 1000, 10**8])
def test_arithmetic_overflow_fail_closed_in_vector_and_fallback(budget):
    old = sparse.csr_matrix([[complex(1e308, 0)]])
    tile = np.array([[complex(1e308, 0)]])
    for module in (baseline, candidate):
        obj, _ = acc(module, old.shape, budget=budget)
        obj.result = old.copy()
        with np.errstate(over='ignore', invalid='ignore'):
            with pytest.raises(FloatingPointError, match='accumulation produced a nonfinite entry'):
                obj._merge(tile, 0, 0, 'overflow')
        same_csr(obj.result, old)


@pytest.mark.parametrize('budget', [100, 200, 430, 800, 1050, 2500, 10000])
@pytest.mark.parametrize('width', [1, 2, 4, 9])
def test_tiny_budget_exact_split_schedule_and_partial_result(budget, width):
    rng = np.random.default_rng(932)
    left = sparse.csr_matrix(rng.normal(size=(5, 4)) + 1j * rng.normal(size=(5, 4)))
    right = sparse.csr_matrix(rng.normal(size=(5, 6)) + 1j * rng.normal(size=(5, 6)))
    rows, cols = np.array([3, 1, 3, 0]), np.array([4, 2, 4, 1])
    values = rng.normal(size=(4, 4)) + 1j * rng.normal(size=(4, 4))
    objects, histories, errors = [], [], []
    for module in (baseline, candidate):
        obj, events = acc(module, (4, 6), budget=budget, width=width)
        error = None
        try:
            obj.add(left, right, rows, cols, values, 'first')
            obj.add(left, right, rows, cols, -values, 'second')
            obj.finish()
        except MemoryError as exc:
            error = str(exc)
        objects.append(obj)
        errors.append(error)
        histories.append([(name, facts.get('tile_rows'), facts.get('tile_columns'))
            for name, facts in events if name.startswith('bounded/projection/')])
        assert obj.peak_owned_upper_bytes <= budget
    assert errors[0] == errors[1]
    assert histories[0] == histories[1]
    same_csr(objects[0].result, objects[1].result)
    assert objects[0].tiles_projected == objects[1].tiles_projected


def test_row_scratch_admission_counts_all_buffers_and_fallback_exact_threshold():
    old = sparse.csr_matrix(np.ones((4, 8), dtype=complex))
    tile = np.ones((2, 3), dtype=complex)
    _, two, _, events = direct_merge(old, tile, 1, 2)
    entry = next(f for n, f in events if n.startswith('bounded/CSR_row_scratch/'))
    scratch = 3 * 48 + 8 + 8 * np.dtype(np.intp).itemsize + 8 * 8
    assert entry['row_merge_scratch_bytes'] == scratch
    assert entry['payload'] == tile.nbytes + 2 * entry['next_CSR_payload_upper_bytes'] + scratch
    actual = next(f for n, f in events if n.startswith('bounded/CSR_merge/'))
    assert actual['payload'] == tile.nbytes + 2 * actual['next_CSR_payload_bytes'] + scratch
    threshold = entry['projection_owned_upper_bytes']
    _, below, _, below_events = direct_merge(old, tile, 1, 2, budget=threshold - 1)
    assert below.row_merges_scalar == 1 and below.row_merges_vectorized == 0
    assert not any('CSR_row_scratch/' in name for name, _ in below_events)
    _, exact, _, _ = direct_merge(old, tile, 1, 2, budget=threshold)
    assert exact.row_merges_vectorized == 1


def test_gate_denial_occurs_before_row_scratch_allocations(monkeypatch):
    old = sparse.csr_matrix(np.eye(3, dtype=complex))
    obj, _ = acc(candidate, old.shape)
    obj.result = old
    def deny(name, **facts):
        raise MemoryError('row scratch denied')
    obj.gate = deny
    def forbidden(*args, **kwargs):
        raise AssertionError('scratch allocation before external gate acceptance')
    monkeypatch.setattr(np, 'empty', forbidden)
    with pytest.raises(MemoryError, match='row scratch denied'):
        obj._merge(np.ones((2, 2), dtype=complex), 0, 0, 'denied')
    assert obj.result is old


@pytest.mark.parametrize('nonfinite', [False, True])
def test_projected_finite_mask_budget_fallback_and_release(nonfinite, monkeypatch):
    projected = np.array([[2-0j, 0-3j], [complex(-0., 2), 4+1j]])
    if nonfinite:
        projected[1, 0] = complex(1, np.nan)
    obj, events = acc(candidate, (2, 2))
    minimum = candidate._bytes(obj.result) + projected.nbytes + projected.size
    before = bits(projected)
    for budget, vector in ((minimum - 1, False), (minimum, True)):
        obj.budget = budget
        events.clear()
        if nonfinite:
            with pytest.raises(FloatingPointError, match='projected contribution'):
                obj._check_projected_finite(projected, 'synthetic')
        else:
            obj._check_projected_finite(projected, 'synthetic')
        assert any('projection_finite/' in name for name, _ in events) == vector
        assert before == bits(projected)
        if vector:
            assert events[0][1]['payload'] == projected.nbytes + projected.size
    assert obj.projected_finite_checks_vectorized == obj.projected_finite_checks_scalar == 1


@pytest.mark.parametrize('index_dtype', [np.int32, np.int64])
def test_duplicate_unsorted_q_maps_and_repeated_native_rows_bitwise(index_dtype):
    # Borrowed noncanonical map semantics remain literal scalar accumulation.
    left = sparse.csr_matrix((np.array([1+2j, 3-1j, -.5j, 4+2j, -1j]),
        np.array([3, 3, 0, 2, 1], dtype=index_dtype), np.array([0, 3, 5], dtype=index_dtype)), shape=(2, 5))
    right = sparse.csr_matrix((np.array([2j, 1-3j, -1j, 2+1j]),
        np.array([2, 0, 2, 1], dtype=index_dtype), np.array([0, 3, 4], dtype=index_dtype)), shape=(2, 4))
    before = [bits(x) for x in (left.data, left.indices, left.indptr, right.data, right.indices, right.indptr)]
    rows, cols = np.array([1, 0, 1]), np.array([0, 0, 1])
    values = np.array([[1+.5j, 3-2j, 0], [-2j, 1, 4], [2, -1j, 1+.25j]])
    result = []
    for module in (baseline, candidate):
        obj, _ = acc(module, (5, 4), width=3, dtype=index_dtype)
        obj.add(left, right, rows, cols, values, 'duplicates')
        result.append(obj.finish())
    same_csr(*result)
    assert before == [bits(x) for x in (left.data, left.indices, left.indptr, right.data, right.indices, right.indptr)]
    assert not left.has_canonical_format and not right.has_canonical_format


def test_forced_int64_result_promotion_with_high_column_and_narrow_old_storage():
    high = int(np.iinfo(np.int32).max)
    shape = (3, high + 1)
    old = sparse.csr_matrix((np.array([1+2j, 3-1j]),
        np.array([0, 2], dtype=np.int64), np.array([0, 1, 2, 2], dtype=np.int64)), shape=shape)
    old.indices = old.indices.astype(np.int32)
    old.indptr = old.indptr.astype(np.int32)
    tile = np.array([[1-2j, 2+0j, complex(0, -3)], [0, 4j, 1+1j]])
    _, two, _, _ = direct_merge(old, tile, 1, high - 2, dtype=np.int64)
    assert two.result.indices.dtype == two.result.indptr.dtype == np.dtype(np.int64)
    assert two.result.indices[-1] == high
    candidate.audit_csr_scalar(two.result, index_dtype=np.int64)


def test_index_contract_overflow_before_replacement_and_pointer_arithmetic():
    high = int(np.iinfo(np.int32).max)
    for module in (baseline, candidate):
        with pytest.raises(OverflowError, match='indices'):
            acc(module, (2, high + 1), dtype=np.int32)
        target = np.empty(1, dtype=np.int64)
        module._shift_indptr(np.array([high - 3], dtype=np.int32), 10, target)
        assert int(target[0]) == high + 7


def test_no_coo_sparse_add_or_advanced_gather_result(monkeypatch):
    old = sparse.csr_matrix(np.ones((4, 8), dtype=complex))
    tile = np.ones((2, 3), dtype=complex)
    def forbidden(*args, **kwargs):
        raise AssertionError('sparse materialization is forbidden')
    monkeypatch.setattr(sparse, 'coo_matrix', forbidden)
    monkeypatch.setattr(sparse.csr_matrix, '__add__', forbidden)
    monkeypatch.setattr(sparse.csr_matrix, '__getitem__', forbidden)
    direct_merge(old, tile, 1, 2)


def test_only_target_ast_changes_and_scalar_fallback_is_identical():
    old_tree = ast.parse(BASELINE_BYTES)
    new_tree = ast.parse(pathlib.Path(candidate.__file__).read_text())
    def methods(tree):
        return {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    old, new = methods(old_tree), methods(new_tree)
    for name in old.keys() - {'BoundedCompactQAccumulator'}:
        assert ast.dump(old[name], include_attributes=False) == ast.dump(new[name], include_attributes=False)
    one = {node.name: node for node in old['BoundedCompactQAccumulator'].body if isinstance(node, ast.FunctionDef)}
    two = {node.name: node for node in new['BoundedCompactQAccumulator'].body if isinstance(node, ast.FunctionDef)}
    for name in one.keys() - {'__init__', '_project_tile', '_merge', 'finish'}:
        assert ast.dump(one[name], include_attributes=False) == ast.dump(two[name], include_attributes=False)
    two['_merge_scalar'].name = '_merge'
    assert ast.dump(one['_merge'], include_attributes=False) == ast.dump(two['_merge_scalar'], include_attributes=False)


def test_controls_isolate_finite_and_merge_paths():
    maps = sparse.eye(4, dtype=complex, format='csr')
    values = np.ones((4, 4), dtype=complex)
    results = []
    for row_flag, finite_flag in ((False, False), (True, False), (False, True), (True, True)):
        obj, _ = acc(candidate, (4, 4), width=4)
        obj.vectorized_row_merge_enabled = row_flag
        obj.vectorized_projected_finite_enabled = finite_flag
        obj.add(maps, maps, np.arange(4), np.arange(4), values, 'isolation')
        results.append(obj.finish())
        assert bool(obj.row_merges_vectorized) == row_flag
        assert bool(obj.projected_finite_checks_vectorized) == finite_flag
    for result in results[1:]:
        same_csr(results[0], result)


def test_selection_lifetime_and_clip_take_without_dtype_conversion(monkeypatch):
    old = sparse.csr_matrix(np.ones((6, 100), dtype=complex))
    old.indices = old.indices.astype(np.int64)
    tile = np.ones((4, 5), dtype=complex)
    obj, events = acc(candidate, old.shape)
    obj.result = old
    original_nonzero, original_take = np.flatnonzero, np.take
    references = []
    def nonzero(value):
        assert all(reference() is None for reference in references)
        result = original_nonzero(value)
        references.append(weakref.ref(result))
        return result
    def take(source, positions, **kwargs):
        assert kwargs['mode'] == 'clip'
        assert source.dtype == kwargs['out'].dtype == np.dtype(np.complex128)
        assert not len(positions) or (int(np.min(positions)) >= 0 and int(np.max(positions)) < len(source))
        return original_take(source, positions, **kwargs)
    monkeypatch.setattr(np, 'flatnonzero', nonzero)
    monkeypatch.setattr(np, 'take', take)
    obj._merge(tile, 1, 30, 'liveness')
    assert obj.row_merges_vectorized == 1
    assert all(reference() is None for reference in references)
    entry = next(f for n, f in events if n.startswith('bounded/CSR_merge/'))
    assert entry['row_merge_selection_upper_bytes'] == 100 * np.dtype(np.intp).itemsize
    assert entry['row_merge_selected_indices_upper_bytes'] == 100 * 8


@pytest.mark.parametrize('kind', ['dense', 'dense_H', 'diagonal_H', 'correction'])
def test_all_recipe_projections_are_bitwise_c81_and_readonly_borrowed(kind):
    from src.solvers.original_port_blocks import CachedPortCorrection, DenseOriginalPortBlock, DiagonalOriginalPortBlock
    rng = np.random.default_rng(753)
    def numeric(shape):
        value = rng.normal(size=shape) + 1j * rng.normal(size=shape)
        value.flags.writeable = False
        return value
    left, right = sparse.csr_matrix(numeric((5, 7))), sparse.csr_matrix(numeric((5, 9)))
    rows, cols = np.array([4, 0, 2]), np.array([1, 3, 1])
    keys = tuple(('mode', i) for i in range(3))
    if kind == 'dense':
        value = numeric((3, 3))
        owners = (value,)
    elif kind == 'dense_H':
        value = DenseOriginalPortBlock(numeric((3, 3)), keys, reason='synthetic', max_bytes=144)
        owners = value.numeric_arrays
    elif kind == 'diagonal_H':
        value = DiagonalOriginalPortBlock(numeric((3,)), keys)
        owners = (value.diagonal,)
    else:
        di, xib = numeric((6, 4))[::2], numeric((4, 6))[:, ::2]
        value = CachedPortCorrection(np.arange(3), di, xib)
        owners = (di, xib)
    before = tuple(bits(x) for x in owners)
    results = []
    for module in (baseline, candidate):
        obj, _ = acc(module, (7, 9), width=4)
        obj.add(left, right, rows, cols, value, kind)
        obj.add(left, right, rows, cols, value, kind + '/repeat')
        results.append(obj.finish())
    same_csr(*results)
    assert before == tuple(bits(x) for x in owners)
    assert all(not x.flags.writeable for x in owners)


def test_extreme_finite_small_bits_and_exact_zero_cancellation():
    tiny = np.nextafter(0., 1.)
    old = sparse.csr_matrix((complex_bits([(tiny, -0.), (1e-250, -1e-250), (-tiny, tiny), (0., -7.)]),
        np.array([0, 2, 4, 6]), np.array([0, 4])), shape=(1, 8))
    tile = complex_bits([(-tiny, 0.), (tiny, -0.), (0., tiny), (1e-308, -1e-308),
                         (tiny, -tiny), (-0., 9.), (-0., 7.), (1., -0.)]).reshape(1, 8)
    _, obj, _, _ = direct_merge(old, tile)
    assert obj.result.nnz == 5


def test_tight_budget_cancellation_that_fits_scalar_keeps_original_decision():
    old = sparse.csr_matrix(np.ones((3, 7), dtype=complex))
    old.indices = old.indices.astype(np.int64)
    old.indptr = old.indptr.astype(np.int64)
    tile = -np.ones((2, 5), dtype=complex)
    _, _, original_events, _ = direct_merge(old, tile, 1, 1)
    exact = next(f for n, f in original_events if n.startswith('bounded/CSR_merge/'))
    budget = baseline._bytes(old) + exact['payload']
    _, obj, _, events = direct_merge(old, tile, 1, 1, budget=budget)
    assert obj.row_merges_scalar == 1 and obj.row_merges_vectorized == 0
    assert obj.result.nnz == 11
    assert obj.result.indices.dtype == obj.result.indptr.dtype == np.dtype(np.int32)
    assert not any('CSR_row_scratch/' in name for name, _ in events)
