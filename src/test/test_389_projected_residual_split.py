"""One complex 3x3, two-overlap diagnostic identity; no PDE."""
import numpy as np
import pytest
from scipy.linalg import lu_factor
from src.solvers.physical_projected_trace import projected_residual_split


def test_complex_overlap_fixed_residual_split():
    T = np.array([[3+.2j, .4-.1j, .2j], [.2+.3j, 2-.1j, -.3j], [.1, .6, 4+.1j]])
    rows = np.array([[0, 1], [1, 2]]); weights = 1/np.sqrt([1, 2, 1])
    xi = np.array([1+.2j, -.3+.5j, 2-1j]); before = xi.copy()
    matrices = [T[np.ix_(r, r)] for r in rows]
    def packets():
        for D in matrices:
            yield D, lu_factor(D)
    d = projected_residual_split(xi, rows, weights, packets(), lambda z: T@z)
    explicit = np.zeros((3, 3), complex)
    for r, D in zip(rows, matrices, strict=True):
        explicit[np.ix_(r, r)] += weights[r, None]*np.linalg.inv(D)*weights[None, r]
    np.testing.assert_allclose(d['z'], explicit@xi, atol=1e-14)
    np.testing.assert_allclose(d['l'], xi, atol=1e-14)
    np.testing.assert_allclose(d['terms'].sum(axis=0), (T@explicit-np.eye(3))@xi, atol=1e-14)
    expected_gram = np.array([[np.vdot(a, b) for b in d['terms']] for a in d['terms']])
    np.testing.assert_allclose(d['gram'], expected_gram, atol=1e-14)
    np.testing.assert_allclose(d['gram_normalized'], expected_gram/np.linalg.norm(xi)**2, atol=1e-14)
    np.testing.assert_allclose(d['gram'].real.sum(), np.linalg.norm(d['total'])**2, atol=1e-14)
    assert np.linalg.norm(d['terms'][0]) > 1e-3 and np.linalg.norm(d['terms'][1]) > 1e-3
    assert d['local_solves'] == 2 and max(d['identity_relative'], d['local_relative']) < 1e-11
    np.testing.assert_array_equal(xi, before)
    for bad_rows, bad_weights in [(np.array([[0, 0], [1, 2]]), weights), (rows, np.ones(3))]:
        with pytest.raises(ValueError):
            projected_residual_split(xi, bad_rows, bad_weights, iter(()), lambda z: T@z)
