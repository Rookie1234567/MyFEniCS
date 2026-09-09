"""Focused projected two-group sequential inverse tests; no FE/PETSc run."""

import numpy as np
import pytest

from src.solvers.physical_projected_trace import (
    ProjectedSequentialTraceFactorStore,
    structured_cell_parity_groups,
)


def _fixture():
    indices = np.array([[0, 1], [1, 2], [2, 3]], dtype=np.int64)
    weights = 1.0 / np.sqrt([1, 2, 2, 1])
    offsets = np.array([0, 1, 2, 4], dtype=np.int64)
    coordinates = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0]], dtype=np.int64)
    matrices = [
        np.array([[2.0 + .2j, .4 - .1j], [.1 + .3j, 1.7 - .2j]]),
        np.array([[1.4 - .3j, -.2 + .5j], [.6 + .1j, 2.2 + .4j]]),
        np.array([[1.8 + .1j, .7 + .2j], [-.3 + .4j, 1.3 - .2j]]),
    ]
    complete_matrix = np.array([
        [2.0 + .1j, .2 - .4j, -.1 + .2j, .0 + .3j],
        [.5 + .2j, 1.1 - .2j, .3 + .1j, -.2j],
        [.4 - .1j, .0 + .5j, 1.7 + .3j, .2 - .2j],
        [-.3 + .2j, .6 + .1j, .1 - .3j, 1.2 + .4j],
    ])
    rhs = np.array([1.0 + .2j, -.3 + .5j, 2.0 - 1.0j, .7 + .4j])
    return indices, weights, offsets, coordinates, matrices, complete_matrix, rhs


def _explicit_group_apply(rhs, indices, weights, matrices, members):
    result = np.zeros_like(rhs)
    for index in members:
        rows = indices[index]
        value = np.linalg.solve(matrices[index], weights[rows] * rhs[rows])
        np.add.at(result, rows, weights[rows] * value)
    return result


def test_structured_parity_is_fixed_and_not_material_or_row_selected():
    coordinates = np.array([[4, 2, 0], [0, 1, 0], [1, 1, 0], [2, 2, 2]])
    group0, group1 = structured_cell_parity_groups(coordinates)
    np.testing.assert_array_equal(group0, [0, 2, 3])
    np.testing.assert_array_equal(group1, [1])
    with pytest.raises(ValueError, match='both groups'):
        structured_cell_parity_groups(np.zeros((2, 3), dtype=np.int64))


def test_seq2_matches_explicit_formula_and_counts_one_complete_T(tmp_path):
    indices, weights, offsets, coordinates, matrices, complete_matrix, rhs = _fixture()
    store = ProjectedSequentialTraceFactorStore(
        indices, weights, offsets, coordinates,
        lambda value: complete_matrix @ value,
    )
    for matrix in matrices:
        store.append(matrix, save=lambda *_: None)

    before = rhs.copy()
    group0, group1 = structured_cell_parity_groups(coordinates)
    d0 = _explicit_group_apply(rhs, indices, weights, matrices, group0)
    f1 = rhs - complete_matrix @ d0
    d1 = _explicit_group_apply(f1, indices, weights, matrices, group1)
    expected = d0 + d1

    actual = np.concatenate(store.apply([rhs[:1], rhs[1:]], lambda: None))
    np.testing.assert_allclose(actual, expected, rtol=1e-13, atol=1e-13)
    np.testing.assert_array_equal(rhs, before)
    assert store.counts['applications'] == 1
    assert store.counts['sequential_applications'] == 1
    assert store.counts['T_started'] == store.counts['T_completed'] == 1
    assert store.counts['group0_patch_apply_rhs'] == len(group0)
    assert store.counts['group1_patch_apply_rhs'] == len(group1)
    assert store.counts['patch_MatSolve'] == len(indices)
    assert store.last_facts['local_backsolves'] == len(indices)
    assert store.last_facts['T_calls'] == 1
    assert all(not hasattr(factor, 'D') for factor in store.factors)

    old_additive = np.concatenate(store.apply_additive([rhs[:1], rhs[1:]]))
    expected_additive = _explicit_group_apply(
        rhs, indices, weights, matrices, np.arange(len(indices)))
    np.testing.assert_allclose(old_additive, expected_additive, rtol=1e-13, atol=1e-13)
    assert not np.allclose(actual, old_additive)


def test_complete_T_fixture_is_full_nonhermitian_physical_expression():
    Q = np.array([
        [1.0 + .1j, .2 - .1j],
        [.1 + .3j, 1.1 + .2j],
        [.4 - .2j, -.1 + .1j],
        [.2 + .2j, .3 - .3j],
    ])
    J = np.array([
        [.2 + .1j, -.1 + .2j],
        [.3 - .2j, .2 + .1j],
        [1.0 + .2j, .1 - .1j],
        [.0 + .3j, 1.0 - .2j],
    ])
    A_block = np.array([
        [1.8 + .2j, .2 - .1j, .1 + .3j, .0 + .2j],
        [.4 + .1j, 1.2 - .3j, -.2 + .2j, .3 + .1j],
        [.0 + .4j, .5 - .2j, 1.5 + .1j, .2 - .3j],
        [-.1 + .2j, .2 + .4j, .3 + .1j, 1.3 - .2j],
    ])
    D = Q.conj().T @ A_block @ Q
    L = J.conj().T @ A_block @ Q
    R = Q.conj().T @ A_block @ J
    S = J.conj().T @ A_block @ J
    F_right = J - Q @ np.linalg.solve(D, R)
    F_left = J.conj().T - L @ np.linalg.solve(D, Q.conj().T)
    legacy_schur = S - L @ np.linalg.solve(D, R)
    np.testing.assert_allclose(
        F_left @ A_block @ F_right, legacy_schur, rtol=1e-12, atol=1e-12)
    assert not np.allclose(F_left, F_right.conj().T)

    indices, weights, offsets, coordinates, matrices, _, rhs = _fixture()
    F = np.array([
        [1.0 + .1j, .2 - .3j, .0 + .2j, -.1 + .1j],
        [.4 + .2j, 1.3 - .1j, .2 + .4j, .0 - .2j],
        [.1 - .2j, .0 + .3j, 1.1 + .2j, .5 + .1j],
        [-.2 + .4j, .3 + .1j, .6 - .2j, 1.2 + .3j],
    ])
    FH = np.array([
        [1.2 - .2j, -.1 + .4j, .3 + .1j, .0 - .2j],
        [.2 + .1j, .9 + .3j, -.2 + .2j, .4 - .1j],
        [.0 + .5j, .3 - .2j, 1.4 + .1j, -.1 + .3j],
        [.5 + .1j, -.3 + .2j, .2 + .4j, .8 - .2j],
    ])
    A = np.array([
        [1.7 + .2j, .2 - .1j, .1 + .3j, 0.0 + .2j],
        [.4 + .1j, 1.1 - .3j, -.2 + .2j, .3 + .1j],
        [.0 + .4j, .5 - .2j, 1.5 + .1j, .2 - .3j],
        [-.1 + .2j, .2 + .4j, .3 + .1j, 1.3 - .2j],
    ])
    CU = np.array([
        [.1 + .2j, .2 - .1j, .0 + .3j, -.1 + .2j],
        [.0 + .1j, .3 + .1j, .2 - .2j, .1 + .1j],
        [.2 - .1j, .0 + .2j, .1 + .3j, .3 - .1j],
        [.1 + .3j, -.2 + .1j, .2 + .2j, .2 - .2j],
    ])
    full_T = FH @ A @ (np.eye(4, dtype=complex) - CU @ A) @ F
    calls = []
    store = ProjectedSequentialTraceFactorStore(
        indices, weights, offsets, coordinates,
        lambda value: calls.append(value.copy()) or full_T @ value)
    for matrix in matrices:
        store.append(matrix, save=lambda *_: None)
    result = np.concatenate(store.apply(rhs))
    explicit = store.apply_explicit_sequential(rhs)
    explicit_result = np.concatenate(explicit['coefficients'])
    np.testing.assert_allclose(result, explicit_result, rtol=1e-13, atol=1e-13)
    assert len(calls) == 2
    assert not np.allclose(FH, F.conj().T)
    assert not np.allclose(A, A.conj().T)
    # The full physical expression has block-external coupling; a local
    # D-only/block-diagonal surrogate cannot be this callback.
    local_only = np.block([
        [full_T[:2, :2], np.zeros((2, 2), dtype=complex)],
        [np.zeros((2, 2), dtype=complex), full_T[2:, 2:]],
    ])
    assert np.linalg.norm(full_T - local_only) > 1e-12


def test_seq2_restores_saved_factor_without_refactor_or_original_D():
    indices, weights, offsets, coordinates, matrices, complete_matrix, rhs = _fixture()
    store = ProjectedSequentialTraceFactorStore(
        indices, weights, offsets, coordinates,
        lambda value: complete_matrix @ value)
    from scipy.linalg import lu_factor

    for matrix in matrices:
        factor, _ = lu_factor(matrix), None
        store.append_saved_factor(factor[0], factor[1], facts={'matrix_sha256': 'bound'})
    result = np.concatenate(store.apply(rhs))
    assert np.isfinite(result).all()
    assert store.counts['restored_factors'] == len(matrices)
    assert store.counts['patch_LU'] == 0
