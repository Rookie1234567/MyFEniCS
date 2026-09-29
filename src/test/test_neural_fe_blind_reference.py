"""The reference-only CSR must use the actual complex nonsymmetric action."""

import numpy as np

from src.solvers.neural_fe_blind_reference import reference_csr
from src.test.test_neural_fe_action_packet import witness


def test_reference_csr_includes_dense_mpc_and_both_port_signs():
    packet, expected, *_ = witness()
    matrix = reference_csr(packet)
    np.testing.assert_allclose(matrix.toarray(), expected, rtol=1e-13, atol=1e-13)
    x = np.array([1 + 2j, -0.7j, 0.9 + 0.1j, -0.2 - 0.4j])
    np.testing.assert_allclose(matrix @ x, packet.apply(x), rtol=1e-13, atol=1e-13)
    np.testing.assert_allclose(
        matrix.conj().T @ x, packet.apply(x, adjoint=True), rtol=1e-13, atol=1e-13
    )
