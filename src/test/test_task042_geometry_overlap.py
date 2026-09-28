"""Bounded overlap/ports, numbering covariance, and fail-closed local factors."""

import numpy as np
import pytest
from scipy.linalg import LinAlgWarning

from src.solvers.learned_geometry_overlap import CellPortOverlapPC, cell_port_indices


def test_overlap_partition_preserves_complete_diagonal_inverse_including_ports():
    patches = cell_port_indices(([0, 1], [1, 2], [2, 3]), 4, 2)
    a = np.diag(np.arange(1, 7) + 0.3j).astype(np.complex128)
    pc = CellPortOverlapPC(6, patches, lambda i: a[np.ix_(i, i)])
    rhs = np.arange(6).astype(np.complex128) + 1j
    np.testing.assert_allclose(pc.apply_array(rhs), np.linalg.solve(a, rhs), atol=1e-14)
    assert all(np.array_equal(i[-2:], [4, 5]) for i in patches)
    assert pc.weights[1] == 0.5 and pc.weights[4] == 1 / 3
    assert all(f.scope == "patch" and f.rows < 6 for f in pc.declarations)


def test_geometry_support_action_is_covariant_under_row_permutation():
    rng = np.random.default_rng(420901)
    a = rng.standard_normal((6, 6)) + 1j * rng.standard_normal((6, 6)) + 8 * np.eye(6)
    rhs = rng.standard_normal(6) + 1j * rng.standard_normal(6)
    patches = cell_port_indices(([0, 1, 2], [1, 2, 3]), 4, 2)
    pc = CellPortOverlapPC(6, patches, lambda i: a[np.ix_(i, i)])
    perm = np.array([3, 0, 2, 1, 5, 4])
    inverse = np.argsort(perm)
    changed = tuple(np.sort(inverse[i]) for i in patches)
    ap = a[np.ix_(perm, perm)]
    pp = CellPortOverlapPC(6, changed, lambda i: ap[np.ix_(i, i)])
    np.testing.assert_allclose(
        pp.apply_array(rhs[perm]), pc.apply_array(rhs)[perm], atol=1e-14
    )
    assert (
        np.linalg.norm(a @ pc.apply_array(rhs) - rhs) > 1e-3
    )  # not a hidden global solve


def test_budget_rejected_before_any_block_read_and_no_global_patch():
    calls = []
    with pytest.raises(ValueError, match="capacity"):
        CellPortOverlapPC(
            6001, (np.arange(6000), np.arange(1, 6001)), lambda i: calls.append(i)
        )
    assert calls == []
    with pytest.raises(ValueError, match="smaller"):
        CellPortOverlapPC(4, (np.arange(4),), lambda i: calls.append(i))


def test_singular_local_patch_has_no_shift_or_global_fallback():
    a = np.array(
        [[0, 0, 0, 1], [0, 1, 0, 0], [0, 0, 1, 0], [1, 0, 0, 1]], dtype=np.complex128
    )
    assert np.linalg.det(a) != 0
    calls = []

    def read(i):
        calls.append(i.copy())
        return a[np.ix_(i, i)]

    with pytest.raises(LinAlgWarning):
        CellPortOverlapPC(4, (np.array([0, 1, 2]), np.array([1, 2, 3])), read)
    assert len(calls) == 1 and len(calls[0]) == 3
