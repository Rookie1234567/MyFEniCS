"""Staged contracts plus tiny synthetic coordinate tests, no automatic PDE.

These algebra tests qualify only map semantics. The source/ABI/hash-bound real
sparse-p2 oracle test is a separate explicitly admitted runner phase.
"""
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from src.solvers.y_orbit_condensed_adapter import _csr_payload_upper, _integer_capacity, _mpc_expansion_width, _native_indices, _port_payload_upper, trace_layout_coordinates


def _fixture():
    # Two orbits, each two trace slots plus one interior slot. Nonunitary R
    # deliberately distinguishes primal inverse from Hermitian dual action.
    r = sparse.diags(np.asarray([2, 3, 5, 7, 11, 13], complex), format="csr")
    ri = sparse.diags(1 / r.diagonal(), format="csr")
    f = sparse.kron(np.asarray([[1, 1], [1, -1]], complex) / np.sqrt(2),
                    sparse.eye(3), format="csr")
    shift = sparse.csr_matrix((np.ones(6), (np.arange(6), (np.arange(6) + 3) % 6)), shape=(6, 6))
    layout = SimpleNamespace(independent=np.arange(6), full_rows=6, ny=2, width=3,
                             r=r, r_inverse=ri, fourier=f, native_translation=r @ shift @ ri)
    system = SimpleNamespace(full_rows=6, active_rows=4, active_interior_rows=2,
        trace_constraints=SimpleNamespace(owned_active_original_dofs=np.asarray([3, 0, 4, 1])),
        cell_recovery_maps=(SimpleNamespace(interior_original_dofs=np.asarray([2])),
                            SimpleNamespace(interior_original_dofs=np.asarray([5]))))
    return layout, system


def test_exact_trace_restriction_retains_nonunitary_primal_dual_maps():
    layout, system = _fixture()
    gates = []
    result = trace_layout_coordinates(layout, system, allocation_gate=lambda *args: gates.append(args))
    assert set(result) == {"R_t", "R_t_inverse", "F_t", "native_trace_translation", "trace_width", "ny",
                           "trace_original_rows", "full_independent_trace_positions", "full_canonical_trace_positions", "audit"}
    np.testing.assert_array_equal(result["trace_original_rows"], [3, 0, 4, 1])
    np.testing.assert_array_equal(result["full_canonical_trace_positions"], [0, 1, 3, 4])
    q = result["R_t"] @ result["F_t"]
    q_inverse = result["F_t"].conj().T @ result["R_t_inverse"]
    np.testing.assert_allclose((q_inverse @ q).toarray(), np.eye(4), atol=1e-12)
    assert sparse.linalg.norm(q.conj().T @ q - sparse.eye(4)) > 1
    assert gates and result["audit"]["partition_exact"]


def test_reject_incomplete_original_cell_interior_inventory():
    layout, system = _fixture()
    system.cell_recovery_maps = (SimpleNamespace(interior_original_dofs=np.asarray([2])),)
    with pytest.raises(ValueError, match="partition"):
        trace_layout_coordinates(layout, system, allocation_gate=lambda *_: None)


def test_reject_canonical_trace_interior_mixing_without_threshold_drop():
    layout, system = _fixture()
    layout.r = layout.r.tolil(); layout.r[2, 0] = 1e-18; layout.r = layout.r.tocsr()
    with pytest.raises(ValueError, match="mixes"):
        trace_layout_coordinates(layout, system, allocation_gate=lambda *_: None)


def test_measured_allocation_gate_is_required():
    layout, system = _fixture()
    with pytest.raises(ValueError, match="allocation gate"):
        trace_layout_coordinates(layout, system, allocation_gate=None)


def test_reject_tiny_fourier_trace_interior_mixing():
    layout, system = _fixture()
    layout.fourier = layout.fourier.tolil(); layout.fourier[0, 2] = 1e-18
    layout.fourier = layout.fourier.tocsr()
    with pytest.raises(ValueError, match="mixes"):
        trace_layout_coordinates(layout, system, allocation_gate=lambda *_: None)


def test_native_index_range_rejects_wide_values_before_int32_narrowing():
    with pytest.raises(OverflowError, match="before narrowing"):
        _native_indices(np.asarray([2**32], dtype=np.uint64), 6, np.int32)
    with pytest.raises(OverflowError, match="before narrowing"):
        _native_indices(np.asarray([-1], dtype=np.int64), 6, np.int32)
    with pytest.raises(OverflowError, match="before narrowing"):
        _integer_capacity(6, 2**31, np.int32)
    np.testing.assert_array_equal(_native_indices(np.asarray([0, 5], dtype=np.uint64), 6, np.int32), [0, 5])


def test_public_finalized_mpc_width_uses_all_master_links_and_rejects_inconsistent_map():
    offsets = np.asarray([0, 0, 2, 2, 4, 4, 4], dtype=np.int32)
    masters = np.asarray([0, 2, 2, 4], dtype=np.int32)
    mpc = SimpleNamespace(slaves=np.asarray([1, 3], dtype=np.int32),
        coefficients=lambda: (np.ones(4, complex), offsets),
        masters=SimpleNamespace(array=masters, links=lambda i: masters[offsets[i]:offsets[i + 1]]))
    assert _mpc_expansion_width(mpc, 6) == 2
    mpc.coefficients = lambda: (np.ones(3, complex), offsets)
    with pytest.raises(ValueError, match="cannot qualify"):
        _mpc_expansion_width(mpc, 6)


def test_csr_and_complete_port_allowances_use_actual_int32_or_int64_width():
    assert _csr_payload_upper(6, 10, np.int32) == 7 * 4 + 10 * 20
    assert _csr_payload_upper(6, 10, np.int64) == 7 * 8 + 10 * 24
    narrow = _port_payload_upper(6, [2, 3], np.int32)
    wide = _port_payload_upper(6, [2, 3], np.int64)
    assert wide[0] - narrow[0] == 5 * 4
    assert wide[1] - narrow[1] == 3 * 4
