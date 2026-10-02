import numpy as np
import pytest
from src.solvers.feinn_diagnostic_algebra import quadratic_change, project_real, energy


def fixture():
    rng = np.random.default_rng(4211201)
    L = rng.normal(size=(13, 13)) + 1j * rng.normal(size=(13, 13))
    W = L.conj().T @ L + np.eye(13)
    X = rng.normal(size=(13, 7)) + 1j * rng.normal(size=(13, 7))
    target = rng.normal(size=13) + 1j * rng.normal(size=13)
    return L, W, X, target


def test_nonhermitian_residual_quadratic_cross_terms():
    rng = np.random.default_rng(12)
    A = rng.normal(size=(13, 13)) + 1j * rng.normal(size=(13, 13))
    _, W, _, e = fixture()
    delta = rng.normal(size=13) + 1j * rng.normal(size=13)
    r = A @ e + rng.normal(size=13)
    Ad = A @ delta
    row = quadratic_change(r, Ad, np.linalg.solve(W, r), np.linalg.solve(W, Ad))
    actual = (
        np.vdot(r + Ad, np.linalg.solve(W, r + Ad)) - np.vdot(r, np.linalg.solve(W, r))
    ).real
    assert row["change"] == pytest.approx(actual)
    assert row["defect"] < 1e-12


@pytest.mark.parametrize("kind", ["full", "duplicate", "near", "scales"])
def test_real_complex_projection_against_independent_whitened_svd(kind):
    _, W, X, t = fixture()
    if kind == "duplicate":
        X[:, -1] = X[:, 0]
    if kind == "near":
        X[:, -1] = X[:, 0] + 1e-13 * X[:, 1]
    if kind == "scales":
        X *= np.logspace(-6, 6, X.shape[1])
    alpha, d, row = project_real(X, W @ X, t, W @ t)
    L = np.linalg.cholesky(W).conj().T
    scales = np.sqrt(np.sum((X.conj() * (W @ X)).real, axis=0))
    Z = L @ X / scales
    ref = (
        np.linalg.lstsq(
            np.r_[Z.real, Z.imag], np.r_[(L @ t).real, (L @ t).imag], rcond=1e-10
        )[0]
        / scales
    )
    assert np.linalg.norm(L @ (d - X @ ref)) / np.linalg.norm(L @ t) < 1e-9
    assert np.isrealobj(alpha)
    assert row["nonincrease"] and row["G_orthogonality"] < 1e-10
    assert row["normalized_reconstruction"] < 1e-10


def test_corrupt_energy_and_nonfinite_records_rejected():
    with pytest.raises(ValueError):
        energy(np.ones(3), -np.ones(3))
    with pytest.raises(ValueError):
        energy(np.ones(3), 1j * np.ones(3))
    _, W, X, t = fixture()
    X[0, 0] = np.nan
    with pytest.raises(ValueError):
        project_real(X, W @ X, t, W @ t)
