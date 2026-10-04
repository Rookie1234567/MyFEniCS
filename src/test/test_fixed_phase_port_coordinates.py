"""Independent complex block models for exact modal-coordinate authority."""

import numpy as np
import pytest
from scipy import sparse
from src.solvers.fixed_phase_port_coordinates import transform, scales


@pytest.mark.parametrize("exponents", [[0, 0, 0], [-2, -1, 1], [-84, -60, 0]])
def test_exact_complex_port_coordinates_and_original_recovery(exponents):
    rng = np.random.default_rng(422024)
    fe, ports = 7, 3
    V = rng.normal(size=(fe, fe)) + 1j * rng.normal(size=(fe, fe)) + 10 * np.eye(fe)
    B = rng.normal(size=(fe, ports)) + 1j * rng.normal(size=(fe, ports))
    D = rng.normal(size=(ports, fe)) + 1j * rng.normal(size=(ports, fe))
    h = np.array([0.7, 1.4, 0.9])
    phase = 10.0 ** np.array(exponents) * np.exp(1j * np.array([0.2, 0.8, -0.4]))
    physical = np.block([[V, B], [-D, np.diag(h)]])
    raw = sparse.csr_matrix(
        np.block(
            [[V, B * phase], [-D * phase.conj()[:, None], np.diag(h * abs(phase) ** 2)]]
        )
    )
    physical_rhs = rng.normal(size=fe + ports) + 1j * rng.normal(size=fe + ports)
    raw_rhs = physical_rhs.copy()
    raw_rhs[fe:] *= phase.conj()
    M, rhs, left, right = transform(raw, raw_rhs, fe, h * abs(phase) ** 2, phase)
    # Independent canonical boundary-coordinate system; port row is divided
    # by h, while field rows and Maxwell rhs are untouched.
    canonical = physical.copy()
    canonical[fe:] /= h[:, None]
    assert np.linalg.norm(M.toarray() - canonical) / np.linalg.norm(canonical) < 1e-14
    y = np.linalg.solve(M.toarray(), rhs)
    x = right * y
    expected = np.linalg.solve(physical, physical_rhs)
    assert (
        np.linalg.norm(np.r_[x[:fe], phase * x[fe:]] - expected)
        / np.linalg.norm(expected)
        < 1e-12
    )
    assert np.linalg.norm(raw @ x - raw_rhs) / np.linalg.norm(raw_rhs) < 1e-12
    assert np.linalg.norm(left * (raw @ x - raw_rhs)) / np.linalg.norm(rhs) < 1e-12
    assert np.allclose(x[:fe], expected[:fe], rtol=0, atol=1e-12)


def test_identity_phase_retains_physical_equations():
    H = np.array([0.7, 1.4])
    left, right = scales(3, H, np.ones(2))
    assert np.array_equal(right, np.ones(5))
    assert np.array_equal(left[:3], np.ones(3))
    assert np.array_equal(left[3:], 1 / H)


@pytest.mark.parametrize(
    "H,p", [(np.array([0.0]), np.array([1j])), (np.array([1.0]), np.array([0j]))]
)
def test_singular_coordinate_map_rejected(H, p):
    with pytest.raises(ValueError, match="PORT_COORDINATES"):
        scales(1, H, p)
