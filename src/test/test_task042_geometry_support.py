"""Existing MPC support mapping: include periodic master once, preserve phase."""

from types import SimpleNamespace

import numpy as np
from mpi4py import MPI

from src.solvers.hcurl_assembly_time_condensation import owned_active_support_groups
from src.solvers.learned_geometry_overlap import CellPortOverlapPC, cell_port_indices


def test_periodic_slave_support_uses_master_and_does_not_apply_phase_twice():
    phase = np.exp(0.7j)
    original = np.array(
        [[2, 0.2, 0, 0], [0.1, 3, 0.3, 0], [0, 0.2, 4, 0.4], [0, 0, 0.1, 5]],
        dtype=np.complex128,
    )
    c = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1], [phase, 0, 0]], dtype=np.complex128)
    a = c.conj().T @ original @ c
    mapping = {
        0: (np.array([0]), np.array([1.0])),
        1: (np.array([1]), np.array([1.0])),
        2: (np.array([2]), np.array([1.0])),
        3: (np.array([0]), np.array([phase])),
    }
    condensed = SimpleNamespace(
        comm=MPI.COMM_SELF,
        owned_active_rows=3,
        trace_constraints=SimpleNamespace(expansion_by_original=mapping),
        cell_recovery_maps=(
            SimpleNamespace(trace_original_dofs=np.array([0, 1])),
            SimpleNamespace(trace_original_dofs=np.array([2, 3])),
        ),
    )
    supports = owned_active_support_groups(condensed, (np.array([0]), np.array([1])))
    assert [s.tolist() for s in supports] == [[0, 1], [0, 2]]
    augmented = np.zeros((4, 4), dtype=np.complex128)
    augmented[:3, :3] = a
    augmented[3, 3] = 2j
    patches = cell_port_indices(supports, 3, 1)
    pc = CellPortOverlapPC(4, patches, lambda i: augmented[np.ix_(i, i)])
    # The diagonal case has an independent exact reference, including periodic phase magnitude.
    diag = np.diag(np.diag(augmented))
    pd = CellPortOverlapPC(4, patches, lambda i: diag[np.ix_(i, i)])
    rhs = np.array([1 + 2j, 3 - 1j, 4 + 0.2j, 1j], dtype=np.complex128)
    np.testing.assert_allclose(
        pd.apply_array(rhs), np.linalg.solve(diag, rhs), atol=1e-14
    )
    assert pc.weights[0] == 0.5 and len(pc.factors) == 2
