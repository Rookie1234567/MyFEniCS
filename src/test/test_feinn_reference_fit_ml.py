"""Reference-exposed target has a correct real gradient and isolated policy."""

import numpy as np
from scipy import sparse

from src.solvers.feinn_reference_fit import FitMetric, LABELS
from src.solvers.feinn_reference import candidate_policy


def test_complex_gram_fit_real_direction_and_zero_error():
    matrix = np.array([[4, 1 + 2j, 0], [1 - 2j, 5, 0.3], [0, 0.3, 2]], dtype=np.complex128)
    reference = np.array([1 + 1j, -0.2 + 0.7j, 0.3 - 0.1j], dtype=np.complex128)
    metric = FitMetric(sparse.csr_matrix(matrix), reference)
    assert metric.value(reference, True)[0] == 0
    np.testing.assert_array_equal(metric.value(reference, True)[1], 0)
    c = np.array([0.3 + 0.4j, 0.1 - 0.2j, 0.8 + 0.2j], dtype=np.complex128)
    direction = np.array([0.7 - 0.3j, -0.4 + 0.5j, 0.1 + 0.6j], dtype=np.complex128)
    loss, gradient = metric.value(c, True)
    assert loss > 0
    for h in (1e-4, 1e-5, 1e-6):
        observed = (metric.value(c + h * direction)[0] - metric.value(c - h * direction)[0]) / (2 * h)
        np.testing.assert_allclose(observed, np.vdot(gradient, direction).real, rtol=1e-8, atol=1e-10)
    assert metric.matvec_count > 0


def test_reference_fit_exposure_flags_never_claim_pde_only_solve():
    assert LABELS == dict(reference_used_for_training=True, pde_only_solve=False,
                          production_initialization_allowed=False,
                          data_role="REFERENCE_EXPOSED_DIAGNOSTIC_ONLY")
    tagged = candidate_policy(True, reference_exposed=True)
    assert tagged["numerical_reconstruction_pass"]
    assert tagged["reference_used_for_training"]
    assert not tagged["pde_only_solver_qualified"]
    assert not tagged["official_candidate_results"]
    assert not tagged["production_initialization_allowed"]
    assert candidate_policy(True)["pde_only_solver_qualified"]
