import numpy as np

from src.solvers.floquet_envelope_hcurl import (
    FloquetLattice2D,
    carrier_phase_rank_report,
    cross_carrier_phase,
    floquet_compatibility_error,
    greedy_independent_carriers,
    make_floquet_carrier,
    maxwell_block_density,
    naive_memory_envelope,
    naive_uniform_refinement_multiplier,
    rectangular_carrier_family,
    shifted_curl_value,
)


def test_reciprocal_lattice_and_floquet_identity():
    lattice = FloquetLattice2D((50.0, 0.0), (0.0, 25.0))
    direct = lattice.direct_matrix()
    reciprocal = lattice.reciprocal_matrix()
    assert np.linalg.norm(direct.T @ reciprocal - 2 * np.pi * np.eye(2)) < 1e-14
    bloch = np.array([0.071, -0.023])
    for carrier in rectangular_carrier_family(
        lattice, bloch, [-2, 0, 3], [-1, 2]
    ):
        assert floquet_compatibility_error(carrier, lattice, bloch) < 1e-12


def test_shifted_curl_exact_product_rule():
    kappa = np.array([1.7, -0.4, 0.3 + 0.2j])
    q = np.array([-0.2, 0.8, 1.1])
    amplitude = np.array([0.4 + 0.1j, -0.7, 0.2j])
    point = np.array([0.13, -0.27, 0.31])
    envelope_phase = np.exp(1j * np.dot(q, point))
    value = amplitude * envelope_phase
    curl_value = 1j * np.cross(q, amplitude) * envelope_phase
    actual = shifted_curl_value(value, curl_value, kappa)
    expected = 1j * np.cross(kappa + q, amplitude) * envelope_phase
    assert np.linalg.norm(actual - expected) < 1e-13


def test_cross_phase_uses_conjugate_test_carrier():
    point = np.array([[0.2, -0.1, 0.7]])
    trial = np.array([0.5, 0.3, 0.4 + 0.2j])
    test = np.array([-0.2, 0.1, 0.7 + 0.1j])
    actual = cross_carrier_phase(point, trial, test)[0]
    expected = np.exp(1j * np.dot(trial - np.conjugate(test), point[0]))
    assert abs(actual - expected) < 1e-14


def test_maxwell_block_hermitian_for_real_coefficients():
    point = [0.1, 0.2, -0.3]
    u = [0.4 + 0.2j, -0.3, 0.7j]
    cu = [0.2, 0.1j, -0.5]
    v = [-0.6j, 0.8, 0.1 + 0.4j]
    cv = [0.9, -0.2j, 0.3]
    kp = [0.2, -0.1, 0.7]
    kq = [-0.3, 0.4, -0.2]
    pq = maxwell_block_density(
        point=point,
        trial_value=u,
        trial_curl=cu,
        test_value=v,
        test_curl=cv,
        trial_kappa=kp,
        test_kappa=kq,
        mu_inv=1.4,
        epsilon=2.3,
        k0=0.8,
    )
    qp = maxwell_block_density(
        point=point,
        trial_value=v,
        trial_curl=cv,
        test_value=u,
        test_curl=cu,
        trial_kappa=kq,
        test_kappa=kp,
        mu_inv=1.4,
        epsilon=2.3,
        k0=0.8,
    )
    assert abs(pq - np.conjugate(qp)) < 1e-13


def test_sampled_carrier_rank_and_greedy_filter():
    lattice = FloquetLattice2D((2.0, 0.0), (0.0, 3.0))
    bloch = [0.2, -0.1]
    carrier0 = make_floquet_carrier(lattice, bloch, 0, 0, label="base")
    duplicate = make_floquet_carrier(lattice, bloch, 0, 0, label="duplicate")
    carrier1 = make_floquet_carrier(lattice, bloch, 1, 0, label="x1")
    x = np.linspace(0.0, 2.0, 17, endpoint=False)
    y = np.linspace(0.0, 3.0, 19, endpoint=False)
    points = np.array([[xi, yi, 0.0] for xi in x for yi in y])
    weights = np.full(len(points), 1.0 / len(points))
    report = carrier_phase_rank_report(
        points, weights, [carrier0, duplicate, carrier1]
    )
    assert report["numerical_rank"] == 2
    selected, audit = greedy_independent_carriers(
        points, weights, [carrier0, duplicate, carrier1]
    )
    assert [carrier.label for carrier in selected] == ["base", "x1"]
    assert audit["selected_count"] == 2


def test_scaling_envelopes():
    assert naive_uniform_refinement_multiplier(5.0, 1.0) == 125.0
    expected = (5 / 0.7) ** 3
    assert abs(naive_uniform_refinement_multiplier(5.0, 0.7) - expected) < 1e-12
    assert naive_memory_envelope(80.0, 5.0, 1.0) == 10000.0
