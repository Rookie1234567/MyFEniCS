"""Independent small-array checks of V14 mathematical and work bounds."""

import numpy as np
import pytest

from src.solvers.physical_interface_schur import (
    PairedPatchBasis,
    apply_interface_cycle,
    build_interface_candidate_directions,
    build_interface_coarse_pair,
    build_interface_local_smoother,
    build_paired_patch_basis,
)


class _SparseBlockFixture:
    def __init__(self, values):
        self.values = np.asarray(values, dtype=complex)

    def getSize(self):
        return self.values.shape

    def getValues(self, rows, columns):
        return self.values[np.ix_(rows, columns)].copy()


def test_accurate_local_lu_is_not_rejected_by_the_coarse_only_rcond_gate():
    matrix = _SparseBlockFixture(np.diag([2.**-50, 1.]))
    smoother = build_interface_local_smoother(matrix, [np.arange(2)])
    try:
        np.testing.assert_allclose(smoother.apply(np.array([2.**-50, 1.])), [1., 1.])
    finally:
        smoother.destroy()


def test_each_local_apply_checks_original_matrix_residual(monkeypatch):
    matrix = _SparseBlockFixture(np.diag([2., 3.]))
    smoother = build_interface_local_smoother(matrix, [np.arange(2)])
    monkeypatch.setattr('scipy.linalg.lu_solve', lambda _factor, rhs, **_kw: np.zeros_like(rhs))
    try:
        with pytest.raises(np.linalg.LinAlgError):
            smoother.apply(np.ones(2, dtype=complex))
    finally:
        smoother.destroy()


def test_oversize_patch_is_refused_before_dense_conversion():
    class Oversize:
        shape = (2049, 2049)

        def toarray(self):
            raise AssertionError('an oversized patch must never be materialized')

    with pytest.raises(ValueError, match='2048'):
        build_paired_patch_basis(Oversize(), np.ones(2049), patch_id=0)


def test_small_operator_scale_does_not_hide_bad_singular_vectors(monkeypatch):
    def incorrect_svd(matrix, **_kwargs):
        return np.eye(2, dtype=complex), np.array([2., 1.])*1e-90, np.eye(2, dtype=complex)

    monkeypatch.setattr('scipy.linalg.svd', incorrect_svd)
    matrix = 1e-90*np.array([[2., .3j], [.1, 1.]], dtype=complex)
    with pytest.raises(FloatingPointError):
        build_paired_patch_basis(matrix, np.ones(2), patch_id=0)


def test_accurate_small_singular_modes_use_operator_scaled_residuals():
    rng = np.random.default_rng(141)
    left = np.linalg.qr(rng.normal(size=(8, 8)) + 1j*rng.normal(size=(8, 8)))[0]
    right = np.linalg.qr(rng.normal(size=(8, 8)) + 1j*rng.normal(size=(8, 8)))[0]
    matrix = (left * np.geomspace(1., 1e-8, 8)) @ right.conj().T
    basis = build_paired_patch_basis(matrix, np.ones(8), patch_id=0)
    assert basis.P.shape == basis.Q.shape == (8, 8)
    np.testing.assert_allclose(basis.singular_values, np.geomspace(1e-8, 1., 8), rtol=1e-8)
    assert max(basis.checks['right_action_relative_per_pair']) <= 1e-10
    assert max(basis.checks['left_action_relative_per_pair']) <= 1e-10


def test_operator_error_does_not_trigger_hidden_repeat_actions():
    calls = []

    def invalid_action(values):
        calls.append(values.shape)
        raise ValueError('original action failure')

    with pytest.raises(ValueError, match='original action failure'):
        build_interface_coarse_pair(invalid_action, np.eye(4), np.eye(4))
    assert len(calls) == 1


@pytest.mark.parametrize('bad_pairing', [False, True])
def test_unstable_coarse_pair_stops_without_replacing_the_test_space(bad_pairing):
    if bad_pairing:
        A = np.eye(2, dtype=complex)
        P, Q = np.array([[1.], [0.]]), np.array([[0.], [1.]])
    else:
        A = np.diag([1., 1e-14]).astype(complex)
        P = Q = np.eye(2, dtype=complex)
    with pytest.raises(np.linalg.LinAlgError, match='COARSE_PAIR_UNSTABLE'):
        build_interface_coarse_pair(lambda values: A @ values, P, Q)


@pytest.mark.parametrize('storage_order', ['C', 'F'])
def test_coarse_assembly_is_bounded_and_keeps_two_distinct_spaces(storage_order):
    rng = np.random.default_rng(140)
    n, rank = 73, 40
    P = np.array(np.linalg.qr(
        rng.normal(size=(n, rank)) + 1j*rng.normal(size=(n, rank)))[0], order=storage_order)
    Q = np.array(np.linalg.qr(
        P + .01*(rng.normal(size=(n, rank)) + 1j*rng.normal(size=(n, rank))))[0],
        order=storage_order)
    A = np.eye(n, dtype=complex)
    A[np.arange(n-1), np.arange(1, n)] = .1j
    widths = []

    def action(values):
        width = 1 if values.ndim == 1 else values.shape[1]
        assert width <= 32
        widths.append(width)
        return A @ values

    coarse = build_interface_coarse_pair(action, P, Q)
    try:
        assert sum(widths) == rank
        assert np.shares_memory(coarse.P, P)
        assert np.shares_memory(coarse.Q, Q)
        np.testing.assert_allclose(coarse.E, Q.conj().T @ A @ P, atol=1e-13)
        rhs = rng.normal(size=n) + 1j*rng.normal(size=n)
        expected = P @ np.linalg.solve(Q.conj().T @ A @ P, Q.conj().T @ rhs)
        np.testing.assert_allclose(coarse.apply(rhs), expected, atol=1e-12)
    finally:
        coarse.destroy()


def test_coarse_factor_inventory_is_separate_from_long_vector_workspace():
    P = np.eye(200, 8, dtype=complex)
    coarse = build_interface_coarse_pair(lambda values: values.copy(), P, P,
        max_workspace_bytes=4096, max_temp_workspace_bytes=131072)
    try:
        assert coarse.facts['workspace_bytes'] <= 4096
        assert coarse.facts['coarse_temp_workspace_bound_bytes'] > 4096
        assert coarse.facts['retained_E_bytes'] == coarse.E.nbytes
        assert coarse.facts['retained_LU_bytes'] == coarse.lu.nbytes
    finally:
        coarse.destroy()


def test_candidate_lifting_weights_local_directions_but_not_port_families():
    patches = (np.array([0, 1]), np.array([1, 2]))
    bases = {
        1: PairedPatchBasis(1, np.array([[2.], [1j]]), np.array([[1.], [2j]]),
                           np.ones(1), {}),
        0: PairedPatchBasis(0, np.array([[1.], [2j]]), np.array([[3j], [1.]]),
                           np.ones(1), {}),
    }
    ports = [{'port': 0, 'b_gamma': np.array([0, 2]),
              'b_values': np.array([2.+1j, -1j]), 'd_gamma': np.array([1]),
              'd_values': np.array([1.-2j])}]
    preflight = []
    P, Q, mapping, facts = build_interface_candidate_directions(
        patches, bases, ports, np.array([2., 4., 8.]),
        preallocation_callback=lambda row: preflight.append(row))
    np.testing.assert_allclose(P[:, :2], [[1., 0.], [1j, 1.], [0., 1j]])
    np.testing.assert_allclose(Q[:, :2], [[3j, 0.], [.5, .5], [0., 2j]])
    expected_ports = np.array([[1.+.5j, 0.], [0., .25+.5j], [-.125j, 0.]])
    np.testing.assert_allclose(P[:, 2:], expected_ports)
    np.testing.assert_allclose(Q[:, 2:], expected_ports)
    assert [row['patch'] for row in mapping[:2]] == [0, 1]
    assert facts['candidate_count'] == 4 and len(preflight) == 1


def test_representative_stop_prevents_building_unapproved_remaining_patches():
    class TrackingSparse(_SparseBlockFixture):
        def __init__(self):
            super().__init__(np.diag([2., 3., 4., 5.]))
            self.extracted = []

        def getValues(self, rows, columns):
            self.extracted.append(tuple(rows))
            return super().getValues(rows, columns)

    matrix = TrackingSparse()
    completed = []

    def progress(row):
        if row['event'] == 'patch_completed':
            completed.append(row['patch_id'])
            if len(completed) == 2:
                raise RuntimeError('representatives show setup will exceed budget')

    with pytest.raises(RuntimeError, match='representatives show setup'):
        build_interface_local_smoother(matrix, [np.array([i]) for i in range(4)],
            paired_patch_deltas={i: np.ones(1) for i in range(4)},
            process_order=[3, 1, 0, 2], progress_callback=progress)
    assert completed == [3, 1]
    assert matrix.extracted == [(3,), (1,)]


def test_fixed_cycle_matches_independent_dense_formula_and_counts():
    A = np.array([[3.+1j, 2.-1j], [.25j, 2.]], dtype=complex)
    P = np.array([[1.], [.3j]], dtype=complex)
    Q = np.array([[.5j], [1.]], dtype=complex)
    coarse = build_interface_coarse_pair(lambda x: A @ x, P, Q)
    calls = {'S': 0, 'J': 0}
    J = np.diag([.2, .3]).astype(complex)
    rhs = np.array([1.+2j, -.5j])
    original = rhs.copy()

    def action(x):
        calls['S'] += 1
        return A @ x

    def local(x):
        calls['J'] += 1
        return J @ x

    try:
        C = P @ np.linalg.solve(Q.conj().T @ A @ P, Q.conj().T)
        cycle_matrix = J + C @ (np.eye(2) - A @ J)
        cycle_matrix += J @ (np.eye(2) - A @ cycle_matrix)
        result, facts = apply_interface_cycle(rhs, action, local, coarse)
        np.testing.assert_allclose(result, cycle_matrix @ rhs, atol=1e-13)
        np.testing.assert_array_equal(rhs, original)
        assert calls == {'S': 2, 'J': 2}
        assert facts['coarse_apply_count'] == facts['cycle_count'] == 1
    finally:
        coarse.destroy()
