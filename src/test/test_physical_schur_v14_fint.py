"""Independent whole-F_int checks using the small production PETSc core."""

from copy import deepcopy

import numpy as np
import pytest

from src.solvers.physical_interface_schur import (
    InterfaceFintAdapter,
    build_interface_coarse_pair,
    build_interface_local_smoother,
    factorize_interface_schur,
)
from src.test.test_390_physical_interface_schur import NumpyFactor, _core
from src.runners.physical_p4_schur_v14 import _q3_interface_operation_audit


@pytest.mark.parametrize("zero_rhs", [False, True])
def test_full_fint_after_global_release_matches_elimination_and_fixed_cycle(zero_rhs):
    core, matrix, volume, B, D, H = _core()
    local = coarse = adapter = rhs = solution = None
    try:
        gamma = np.array([4, 5, 6])
        interiors = (np.array([0, 1]), np.array([2, 3]))
        A = volume + B @ np.linalg.solve(H, D)
        S = A[np.ix_(gamma, gamma)].copy()
        for rows in interiors:
            S -= volume[np.ix_(gamma, rows)] @ np.linalg.solve(
                volume[np.ix_(rows, rows)], volume[np.ix_(rows, gamma)])
        patches = (np.array([0, 1]), np.array([1, 2]))
        multiplicity = np.array([1., 2., 1.])
        J = np.zeros((3, 3), dtype=complex)
        for rows in patches:
            J[np.ix_(rows, rows)] += np.linalg.solve(
                S[np.ix_(rows, rows)], np.eye(len(rows))) / multiplicity[rows, None]
        P = np.array([[1.], [.2j], [.1]], dtype=complex)
        Q = np.array([[.5j], [1.], [.3]], dtype=complex)
        C = P @ np.linalg.solve(Q.conj().T @ S @ P, Q.conj().T)
        interface_inverse = J + C @ (np.eye(3) - S @ J)
        interface_inverse += J @ (np.eye(3) - S @ interface_inverse)

        local = build_interface_local_smoother(core.S_V, patches, port_data=core.port_data)
        coarse = build_interface_coarse_pair(core.apply_physical_schur_block, P, Q)
        factorize_interface_schur(core, factor_factory=NumpyFactor)
        former_global_factor = core.interface_factor
        core.release_global_factor()
        core.release_explicit_schur()
        assert former_global_factor.destroyed
        assert core.interface_factor is core.interface_matrix is core.S_V is None

        adapter = InterfaceFintAdapter(core, local, coarse)
        g = np.arange(1., 8.) + 1j*np.arange(7., 0., -1.)
        if zero_rhs:
            g.fill(0)
        reduced = g[gamma].copy()
        for rows in interiors:
            reduced -= volume[np.ix_(gamma, rows)] @ np.linalg.solve(
                volume[np.ix_(rows, rows)], g[rows])
        expected = np.zeros(7, dtype=complex)
        expected[gamma] = interface_inverse @ reduced
        for rows in interiors:
            expected[rows] = np.linalg.solve(volume[np.ix_(rows, rows)],
                g[rows] - volume[np.ix_(rows, gamma)] @ expected[gamma])

        rhs = matrix.createVecRight()
        rhs.array[:] = g
        solution, facts = adapter.apply_with_facts(rhs)
        np.testing.assert_allclose(solution.array, expected, rtol=2e-12, atol=2e-12)
        np.testing.assert_array_equal(rhs.array, g)
        assert facts['factor_solve_delta'] == [4, 4]
        assert [patch.solve_count for patch in local.patches] == [2, 2]
        assert facts['cycle']['coarse_apply_count'] == 1
        assert facts['inner_iteration_count'] == 0
        assert not facts['reference_used'] and not facts['ksp_created']
        assert _q3_interface_operation_audit(facts, 2)['passed']
        # The 168 limit is an upper bound, not a requirement to solve an
        # uncoupled block merely to increment a counter.
        skipped = deepcopy(facts)
        skipped['operation_counts']['factor_solve_delta_by_phase']['reduce'][0] = 0
        skipped['factor_solve_delta'][0] -= 1
        assert _q3_interface_operation_audit(skipped, 2)['passed']
        missing = dict(facts, operation_counts={})
        assert not _q3_interface_operation_audit(missing, 2)['passed']
        over = dict(facts, factor_solve_delta=[5, 4])
        assert not _q3_interface_operation_audit(over, 2)['passed']

        residual = g - A @ solution.array
        np.testing.assert_allclose(residual[:4], 0., atol=2e-12)
        np.testing.assert_allclose(residual[gamma], reduced - S @ solution.array[gamma],
                                   rtol=2e-12, atol=2e-12)
        if not zero_rhs:
            assert np.linalg.norm(residual) > 1e-5
    finally:
        for item in (solution, rhs, adapter, coarse, local, core, matrix):
            if item is not None:
                item.destroy()
