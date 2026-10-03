"""Synthetic complex algebra only: no FE/PETSc imports, JIT, factors or raw files."""
from __future__ import annotations

from types import SimpleNamespace
import weakref

import numpy as np
import pytest
from scipy import sparse

from src.solvers import bounded_compact_q_projection as projection
from src.solvers.bounded_compact_q_projection import BoundedCompactQAccumulator
from src.solvers.original_port_blocks import (
    CachedPortCorrection, DenseOriginalPortBlock, DiagonalOriginalPortBlock,
)
from src.solvers.y_orbit_two_cell_block_audit import TwoCellBlockProvider


def readonly(value, dtype=np.complex128):
    array = np.asarray(value, dtype=dtype)
    array.flags.writeable = False
    return array


def random_complex(rng, shape):
    return rng.normal(size=shape) + 1j * rng.normal(size=shape)


def log_gate():
    events = []
    def gate(label, payload=0, workspace=0, **facts):
        events.append((label, dict(matrix_payload_bytes=payload, workspace_bytes=workspace, **facts)))
    return events, gate


def accumulator(shape, budget=10**7, width=2, gate=None):
    if gate is None:
        _, gate = log_gate()
    return BoundedCompactQAccumulator(shape, max_owned_bytes=budget,
                                     tile_width=width, index_dtype=np.int32, gate=gate)


def dense_recipe(value):
    if isinstance(value, CachedPortCorrection):
        return value.Di @ value.XiB
    if isinstance(value, DiagonalOriginalPortBlock):
        return np.diag(value.diagonal)
    if isinstance(value, DenseOriginalPortBlock):
        return value.numeric_arrays[0]
    return value


@pytest.mark.parametrize('kind', ['dense', 'dense_H', 'diagonal_H', 'correction'])
@pytest.mark.parametrize('width', [1, 2, 4, 30])
def test_rectangular_complex_nonhermitian_dense_oracle(kind, width):
    rng = np.random.default_rng(431089)
    # Many repeated q indices across rows, complex nonunitary maps, gaps in q
    # support, permuted and repeated native gathers, and rectangular p != q.
    a, b = random_complex(rng, (9, 8)), random_complex(rng, (9, 11))
    a[:, [1, 4, 6]] = 0
    b[:, [0, 3, 5, 9]] = 0
    left, right = sparse.csr_matrix(a), sparse.csr_matrix(b)
    rows = np.array([8, 2, 8, 0, 5])
    cols = np.array([7, 1, 6, 7, 4])
    keys = tuple(('mode', i) for i in range(5))
    if kind == 'diagonal_H':
        value = DiagonalOriginalPortBlock(np.arange(1, 6) + .5j, keys)
    elif kind == 'dense_H':
        value = DenseOriginalPortBlock(random_complex(rng, (5, 5)), keys,
                                       reason='synthetic non-Hermitian oracle', max_bytes=400)
    elif kind == 'correction':
        # Noncontiguous readonly borrowed factors exercise ownership and BLAS
        # packing uncertainty; D is independent from B and is not conjugated.
        di = readonly(random_complex(rng, (10, 7)))[::2, ::2]
        xib = readonly(random_complex(rng, (8, 10)))[::2, ::2]
        value = CachedPortCorrection(readonly(np.arange(5), np.int64), di, xib)
    else:
        value = readonly(random_complex(rng, (10, 10)))[::2, ::2]
    events, gate = log_gate()
    acc = accumulator((8, 11), width=width, gate=gate)
    before = [x.copy() for x in (left.data, left.indices, left.indptr, right.data)]
    acc.add(left, right, rows, cols, value, 'synthetic')
    actual = acc.finish()
    expected = a[rows, :].conj().T @ dense_recipe(value) @ b[cols, :]
    np.testing.assert_allclose(actual.toarray(), expected, rtol=4e-13, atol=4e-13)
    assert actual.has_canonical_format
    assert actual.shape == (8, 11)
    for original, copy in zip((left.data, left.indices, left.indptr, right.data), before, strict=True):
        np.testing.assert_array_equal(original, copy)
    assert all(e['projection_owned_upper_bytes'] <= e['projection_owned_budget_bytes'] for _, e in events)
    assert all(e['projection_owned_budget_excludes_Python_and_native_workspace'] for _, e in events)
    for _, event in events:
        if 'tile_rows' in event:
            assert event['tile_rows'] <= width and event['tile_columns'] <= width


def test_repeated_csr_indices_gather_uses_add_not_overwrite():
    left = sparse.csr_matrix((np.array([1+2j, 3-1j, -.5j]), np.array([3, 3, 0]), np.array([0, 3])), shape=(1, 5))
    right = sparse.csr_matrix([[0, 2+1j, 0, -3j]])
    acc = accumulator((5, 4), width=2)
    value = readonly([[2-.8j]])
    acc.add(left, right, np.array([0]), np.array([0]), value, 'duplicate_csr_entries')
    np.testing.assert_allclose(acc.finish().toarray(), left.toarray().conj().T @ value @ right.toarray())
    assert not left.has_canonical_format  # borrowing did not canonicalize it


@pytest.mark.parametrize('shape', [(0, 7), (5, 0), (0, 0), (4, 6)])
def test_empty_shapes_and_empty_native_support(shape):
    left, right = sparse.csr_matrix((3, shape[0]), dtype=complex), sparse.csr_matrix((3, shape[1]), dtype=complex)
    acc = accumulator(shape, width=2)
    acc.add(left, right, np.array([], dtype=int), np.array([1]), np.zeros((0, 1), complex), 'empty')
    acc.add(left, right, np.array([0]), np.array([1]), np.zeros((1, 1), complex), 'zero_map')
    result = acc.finish()
    assert result.shape == shape and result.nnz == 0


def test_exact_cancellations_and_arbitrarily_small_nonzero_are_preserved():
    maps = sparse.eye(4, dtype=complex, format='csr')
    rows = np.arange(4)
    value = readonly([[1+2j, 0, 0, 0], [0, 0, 0, 0], [0, 0, -2+3j, 0], [0, 0, 0, 0]])
    acc = accumulator((4, 4), width=2)
    acc.add(maps, maps, rows, rows, value, 'first')
    acc.add(maps, maps, rows, rows, -value, 'exact_cancellation')
    tiny = np.zeros((4, 4), complex)
    tiny[0, 3], tiny[3, 0] = 1e-250 + 2e-250j, -1e-250j
    acc.add(maps, maps, rows, rows, tiny, 'tiny')
    result = acc.finish()
    assert result.nnz == 2
    np.testing.assert_array_equal(result.toarray(), tiny)


def test_tiles_never_use_full_support_slices_coo_or_sparse_add(monkeypatch):
    rng = np.random.default_rng(6502)
    left, right = sparse.csr_matrix(random_complex(rng, (6, 13))), sparse.csr_matrix(random_complex(rng, (6, 17)))
    value = random_complex(rng, (6, 6))
    oracle = left.toarray().conj().T @ value @ right.toarray()
    observed = []
    original_gather = projection._gather_tile
    def gather(matrix, ids, first, last):
        assert last - first <= 3
        result = original_gather(matrix, ids, first, last)
        observed.append(result.shape)
        return result
    def forbidden(*args, **kwargs):
        raise AssertionError('full-support sparse slicing/COO/addition must not be called')
    monkeypatch.setattr(projection, '_gather_tile', gather)
    monkeypatch.setattr(sparse, 'coo_matrix', forbidden)
    monkeypatch.setattr(sparse.csr_matrix, '__getitem__', forbidden)
    monkeypatch.setattr(sparse.csr_matrix, '__add__', forbidden)
    acc = accumulator((13, 17), width=3)
    acc.add(left, right, np.arange(6), np.arange(6), value, 'bounded')
    np.testing.assert_allclose(acc.finish().toarray(), oracle, rtol=3e-13, atol=3e-13)
    assert observed and all(shape[1] <= 3 for shape in observed)


def test_budget_shrinks_width_and_counts_all_explicit_array_lifetimes():
    events, gate = log_gate()
    acc = accumulator((5, 7), budget=2500, width=100, gate=gate)
    left = sparse.csr_matrix(np.ones((10, 5), complex))
    right = sparse.csr_matrix(np.ones((10, 7), complex))
    di, xib = readonly(np.ones((10, 4), complex)), readonly(np.ones((4, 10), complex))
    acc.add(left, right, np.arange(10), np.arange(10), CachedPortCorrection(np.arange(10), di, xib), 'accounting')
    result = acc.finish()
    assert max(e.get('tile_rows', 0) for _, e in events) < 5
    assert max(e['projection_owned_upper_bytes'] for _, e in events) == acc.peak_owned_upper_bytes <= 2500
    for name, e in events:
        if 'projection/' in name:
            a, b = e['tile_rows'], e['tile_columns']
            assert e['matrix_payload_bytes'] == 16 * (10*a + 10*b + a*4 + 4*b + a*b)
        if 'CSR_merge/' in name:
            assert e['matrix_payload_bytes'] == e['projected_tile_bytes'] + 2*e['next_CSR_payload_bytes']
    assert events[-1][1]['exact_final_CSR_bytes'] == projection._bytes(result)


def test_insufficient_initial_or_minimum_scratch_budget_rejects_before_allocate(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('allocation occurred before rejecting the budget')
    with monkeypatch.context() as context:
        context.setattr(sparse, 'csr_matrix', forbidden)
        with pytest.raises(MemoryError, match='before empty_result'):
            accumulator((50, 50), budget=20)
    acc = accumulator((2, 2), budget=100)
    maps = sparse.eye(2, dtype=complex, format='csr')
    monkeypatch.setattr(projection, '_gather_tile', forbidden)
    with pytest.raises(MemoryError, match='before projection/'):
        acc.add(maps, maps, np.arange(2), np.arange(2), np.ones((2, 2), complex), 'scratch')


def test_final_csr_cannot_fit_rejects_before_replacement_buffers(monkeypatch):
    acc = accumulator((4, 4), budget=430, width=1)
    maps = sparse.eye(4, dtype=complex, format='csr')
    allocations = []
    original_empty = np.empty
    def empty(*args, **kwargs):
        allocations.append(args[0])
        return original_empty(*args, **kwargs)
    monkeypatch.setattr(np, 'empty', empty)
    with pytest.raises(MemoryError, match='before CSR_merge/.*complete final CSR/merge'):
        acc.add(maps, maps, np.arange(4), np.arange(4), np.ones((4, 4), complex), 'capacity')
    # The failed next replacement is not among the allocations; the partial
    # accumulator remains bounded and has not silently dropped any new entry.
    assert acc.result.nnz < 16
    assert allocations[-1] == acc.result.nnz
    assert acc.peak_owned_upper_bytes <= 430


def test_external_resource_gate_denial_precedes_projection_allocation(monkeypatch):
    acc = accumulator((2, 2))
    def deny(label, **facts):
        raise MemoryError('fresh process-tree gate denied')
    acc.gate = deny
    def forbidden(*args, **kwargs):
        raise AssertionError('gather allocated after gate denial')
    monkeypatch.setattr(projection, '_gather_tile', forbidden)
    maps = sparse.eye(2, dtype=complex, format='csr')
    with pytest.raises(MemoryError, match='process-tree gate'):
        acc.add(maps, maps, np.arange(2), np.arange(2), np.eye(2, dtype=complex), 'denied')


def test_borrowed_factors_not_retained_or_mutated():
    maps = sparse.eye(3, dtype=complex, format='csr')
    di, xib = readonly(np.eye(3, dtype=complex)), readonly((2+3j)*np.eye(3, dtype=complex))
    expected_di, expected_xib = di.copy(), xib.copy()
    recipe = CachedPortCorrection(readonly(np.arange(3), np.int32), di, xib)
    references = weakref.ref(di), weakref.ref(xib), weakref.ref(recipe)
    acc = accumulator((3, 3))
    acc.add(maps, maps, np.arange(3), np.arange(3), recipe, 'ownership')
    np.testing.assert_array_equal(di, expected_di)
    np.testing.assert_array_equal(xib, expected_xib)
    assert not di.flags.writeable and not xib.flags.writeable
    assert not np.shares_memory(acc.result.data, di) and not np.shares_memory(acc.result.data, xib)
    del recipe, di, xib
    assert all(reference() is None for reference in references)


def test_nonfinite_projection_and_nonfinite_accumulation_fail_closed():
    maps = sparse.eye(1, dtype=complex, format='csr')
    acc = accumulator((1, 1))
    with np.errstate(over='ignore', invalid='ignore'):
        with pytest.raises(FloatingPointError, match='projected contribution'):
            acc.add(maps, maps, np.array([0]), np.array([0]), np.array([[np.inf]], complex), 'bad')
        acc.add(maps, maps, np.array([0]), np.array([0]), np.array([[1e308]], complex), 'large')
        with pytest.raises(FloatingPointError, match='accumulation'):
            acc.add(maps, maps, np.array([0]), np.array([0]), np.array([[1e308]], complex), 'overflow')
    assert acc.result.data[0] == 1e308


@pytest.mark.parametrize('bad', [None, True, 0, -1, 1.5, np.int64(1000)])
def test_invalid_budget_rejected(bad):
    with pytest.raises(ValueError, match='positive Python integer'):
        accumulator((2, 2), budget=bad)


def fake_provider_fixture(kind):
    rng = np.random.default_rng(48932)
    nt, np_ = 3, 4
    keys = tuple(('port', i, i-2) for i in range(np_))
    h = (DiagonalOriginalPortBlock(np.arange(1, np_+1)+.3j, keys) if kind == 'diagonal' else
         DenseOriginalPortBlock(random_complex(rng, (np_, np_)), keys,
                                reason='synthetic full non-Hermitian H', max_bytes=16*np_**2))
    cells, contributions = [], []
    port_rows = readonly(np.arange(nt, nt+np_), np.int32)
    contributions.append((port_rows, port_rows, h, 'ports/H_original'))
    for index, (active, ports) in enumerate((([2, 0], [3, 1]), ([1, 2], [0, 3]))):
        cell = SimpleNamespace(**{field: None for field in (
            'original_interiors', 'original_trace', 'S_V', 'recovery', 'trace_from_interior',
            'Bi', 'Bt', 'Dt', 'Bhat', 'Dhat', 'Hlocal')})
        cell.active_ids, cell.ports = readonly(active, np.int32), readonly(ports, np.int32)
        cell.Di, cell.XiB = readonly(random_complex(rng, (2, 3))), readonly(random_complex(rng, (3, 2)))
        cell.interior_lu = (readonly(np.eye(3)), readonly(np.arange(3), np.int32))
        cell.expansion = sparse.eye(2, dtype=complex, format='csr')
        cells.append(cell)
        pids = readonly(nt + cell.ports, np.int32)
        for rows, cols, label in ((cell.active_ids, cell.active_ids, 'volume/cell/'),
                                  (cell.active_ids, pids, 'cell/C_hat/'),
                                  (pids, cell.active_ids, 'cell/-D_hat/')):
            contributions.append((rows, cols, readonly(random_complex(rng, (2, 2))), label+str(index)))
        contributions.append((pids, pids, CachedPortCorrection(cell.ports, cell.Di, cell.XiB), f'cell/Hhat_correction/{index}'))
    action = SimpleNamespace(uses_port_block_representation=True, _destroyed=False,
        condensed=SimpleNamespace(_destroyed=False, comm=SimpleNamespace(Get_size=lambda: 1), active_rows=nt, appended_rows=np_),
        port_coupling_mode='cached', _H_p=None, _Hhat=None, _cells=cells, _port_terms={},
        _direct_B_original={}, _direct_D_original={}, _direct_B_active={}, _direct_D_active={}, _original_port_block=h)
    condensed = SimpleNamespace(action=action,
        action_bundle={'dtn_action': SimpleNamespace(carrier=SimpleNamespace(entries=[SimpleNamespace(mode_key=key) for key in keys]))},
        iter_contributions=lambda **kwargs: iter(contributions))
    maps = [random_complex(rng, (7, 6)), random_complex(rng, (7, 9))]
    maps[0][:, [0, 4]] = 0
    maps[1][:, [1, 3, 6]] = 0
    maps = [sparse.csr_matrix(matrix) for matrix in maps]
    coords = SimpleNamespace(rows=7, index_dtype=np.dtype(np.int32), q_map=lambda q: maps[q])
    native = np.zeros((7, 7), complex)
    for rows, cols, value, _ in contributions:
        native[np.ix_(rows, cols)] += dense_recipe(value)
    return condensed, coords, maps, native


@pytest.mark.parametrize('kind', ['diagonal', 'dense'])
@pytest.mark.parametrize('p,q', [(0, 0), (0, 1), (1, 0), (1, 1)])
def test_provider_opt_in_all_q_blocks_match_legacy_and_native_dense(kind, p, q):
    condensed, coords, maps, native = fake_provider_fixture(kind)
    events = []
    gate = lambda name, facts: events.append((name, facts))
    provider = TwoCellBlockProvider(condensed, coords, allocation_gate=gate,
        compact_projection_max_owned_bytes=100_000, compact_projection_tile_width=2)
    result = provider.block(p, q)
    legacy = TwoCellBlockProvider(condensed, coords, allocation_gate=lambda *args: None).block(p, q)
    expected = maps[p].toarray().conj().T @ native @ maps[q].toarray()
    np.testing.assert_allclose(result.toarray(), expected, rtol=4e-13, atol=4e-13)
    np.testing.assert_allclose(result.toarray(), legacy.toarray(), rtol=4e-13, atol=4e-13)
    assert provider.calls == 1
    assert any('bounded/CSR_merge/' in name for name, _ in events)
    assert not any('/q_slices/' in name or 'factored_or_dense_projection/' in name for name, _ in events)
    assert all(e.get('numeric_factor_count', 0) == 0 for _, e in events)


def test_provider_legacy_default_unchanged_and_optin_requires_compact_layout():
    condensed, coords, _, _ = fake_provider_fixture('diagonal')
    events = []
    provider = TwoCellBlockProvider(condensed, coords, allocation_gate=lambda n, f: events.append(n))
    provider.block(1, 0)
    assert any('factored_or_dense_projection/' in name for name in events)
    assert not any('bounded/' in name for name in events)
    condensed.action.uses_port_block_representation = False
    with pytest.raises(ValueError, match='explicit compact port layout'):
        TwoCellBlockProvider(condensed, coords, allocation_gate=lambda *args: None,
                            compact_projection_max_owned_bytes=1000)


def test_growing_result_adapts_each_unprocessed_tile_instead_of_false_rejection():
    maps = sparse.csr_matrix(np.ones((100, 8), complex))
    rows = np.arange(100)
    value = np.ones((100, 100), complex)
    events, gate = log_gate()
    acc = accumulator((8, 8), budget=10_000, width=8, gate=gate)
    acc.add(maps, maps, rows, rows, value, 'growing_result')
    np.testing.assert_array_equal(acc.finish().toarray(), np.full((8, 8), 10000, complex))
    dimensions = {(e['tile_rows'], e['tile_columns']) for _, e in events if 'tile_rows' in e}
    assert (2, 2) in dimensions and ((1, 2) in dimensions or (2, 1) in dimensions)
    assert acc.peak_owned_upper_bytes <= 10_000


@pytest.mark.parametrize('fail', [False, True])
def test_provider_releases_results_and_borrowed_action_without_gc(fail):
    import gc
    def run():
        condensed, coords, _, _ = fake_provider_fixture('diagonal')
        provider = TwoCellBlockProvider(condensed, coords, allocation_gate=lambda *args: None,
            compact_projection_max_owned_bytes=100 if fail else 100_000, compact_projection_tile_width=2)
        references = [weakref.ref(provider), weakref.ref(condensed.action._cells[0].Di)]
        if fail:
            with pytest.raises(MemoryError):
                provider.block(1, 0)
        else:
            result = provider.block(1, 0)
            references.append(weakref.ref(result))
        return references
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        assert all(reference() is None for reference in run())
    finally:
        if was_enabled:
            gc.enable()


def test_opt_in_provider_validation_does_not_allocate_vector_masks(monkeypatch):
    from src.solvers import y_orbit_two_cell_block_audit as provider_module
    condensed, coords, _, _ = fake_provider_fixture('diagonal')
    original_finite = np.isfinite
    def scalar_finite(value, *args, **kwargs):
        assert np.ndim(value) == 0, 'unbudgeted vector finite mask'
        return original_finite(value, *args, **kwargs)
    def forbidden(*args, **kwargs):
        raise AssertionError('unbudgeted vector validation')
    monkeypatch.setattr(np, 'isfinite', scalar_finite)
    monkeypatch.setattr(np, 'array_equal', forbidden)
    monkeypatch.setattr(provider_module, 'csr_audit', forbidden)
    provider = TwoCellBlockProvider(condensed, coords, allocation_gate=lambda *args: None,
        compact_projection_max_owned_bytes=100_000, compact_projection_tile_width=2)
    assert provider.block(1, 0).nnz > 0


def test_scalar_csr_audit_rejects_noncanonical_nonfinite_and_abi_overflow():
    bad = sparse.csr_matrix([[1, 2]], dtype=complex)
    bad.indices[1] = 0
    with pytest.raises(ValueError, match='CSR entry'):
        projection.audit_csr_scalar(bad, index_dtype=np.int32)
    bad = sparse.csr_matrix([[np.nan]], dtype=complex)
    with pytest.raises(ValueError, match='CSR entry'):
        projection.audit_csr_scalar(bad, index_dtype=np.int32)
    with pytest.raises(OverflowError, match='indices'):
        accumulator((int(np.iinfo(np.int32).max)+1, 1), budget=100)


@pytest.mark.parametrize('source,delta,dtype,expected', [
    ([2147483640], 10, np.int64, [2147483650]),
    ([1, 2], 2147483648, np.int64, [2147483649, 2147483650]),
    ([2147483650], -2147483649, np.int32, [1]),
])
def test_csr_pointer_shift_uses_wide_arithmetic_before_output_cast(source, delta, dtype, expected):
    source_dtype = np.int32 if max(source) <= np.iinfo(np.int32).max else np.int64
    source = np.array(source, dtype=source_dtype)
    target = np.empty(len(source), dtype=dtype)
    projection._shift_indptr(source, delta, target)
    np.testing.assert_array_equal(target, expected)



def test_merge_capacity_adapts_tiles_without_retaining_rejected_backing(monkeypatch):
    acc = accumulator((4, 4), budget=1050, width=4)
    maps = sparse.eye(4, dtype=complex, format='csr')
    rows = np.arange(4)
    rejected_tiles = []
    original_merge = acc._merge
    def merge(tile, *args):
        # Previously rejected output buffers must be gone before a retry,
        # including their complete backing owners, without a GC dependency.
        assert all(reference() is None for reference in rejected_tiles)
        result = original_merge(tile, *args)
        if result is not None:
            rejected_tiles.append(weakref.ref(tile))
        return result
    monkeypatch.setattr(acc, '_merge', merge)
    for _ in range(2):
        acc.add(maps, maps, rows, rows, np.ones((4, 4), complex), 'merge_adaptation')
    np.testing.assert_array_equal(acc.finish().toarray(), np.full((4, 4), 2, complex))
    assert rejected_tiles and all(reference() is None for reference in rejected_tiles)
    assert acc.peak_owned_upper_bytes <= 1050
