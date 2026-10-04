from types import SimpleNamespace

import numpy as np
import pytest
from numpy.polynomial.legendre import leggauss, legvander

from src.solvers.interval_facet_moments import (
    unit_interval_moments,
    facet_identity,
    integrate_receiver_facet,
    IntervalFacetAdapter,
)


@pytest.mark.parametrize("degree", [0, 4, 6])
def test_center_half_scale_zero_signed_frequency(degree):
    omega = np.array([0.0, 1e-14, -1e-8, 0.4, -3.0, 8.0, -18.0, 55.0])
    x, w = leggauss(96)
    t = 0.5 * (x + 1)
    w = 0.5 * w
    independent = (np.exp(1j * omega[:, None] * t) * w) @ legvander(x, degree)
    actual = unit_interval_moments(omega, degree)
    assert np.max(abs(actual - independent)) < 1e-13
    assert np.array_equal(actual[0], np.r_[1.0 + 0j, np.zeros(degree)])
    assert np.linalg.norm(actual[1:] - 0.5 * actual[1:]) > 0.1


def poly():
    rng = np.random.default_rng(4212301)
    c = rng.normal(size=(5, 5, 7, 2)) + 1j * rng.normal(size=(5, 5, 7, 2))
    return SimpleNamespace(p=4, coefficients={"top": c, "bottom": c * 0.7j})


@pytest.mark.parametrize("side", ["top", "bottom"])
def test_real_consumer_contraction_and_compatibility(side):
    p = poly()
    k = np.array([1.7, -0.2, 1.1j])
    J = np.diag([0.2, 6.25, 2.0])
    origin = np.array([0.3, 0.1, -1.0])
    expected = facet_identity(p, side, k, J, origin)
    actual = integrate_receiver_facet(p, side, k, J, origin, expected=expected)
    x, w = leggauss(96)
    t = 0.5 * (x + 1)
    w *= 0.5
    vx = legvander(x, p.p)
    point = np.einsum("xa,yb,abjc->xyjc", vx, vx, p.coefficients[side])
    pos = origin.copy()
    pos[2] += J[2, 2] if side == "top" else 0
    ref = np.einsum(
        "x,y,xyjc->jc",
        w * np.exp(1j * k[0] * J[0, 0] * t),
        w * np.exp(1j * k[1] * J[1, 1] * t),
        point,
    )
    ref *= np.array([J[1, 1], J[0, 0]]) * np.exp(1j * k @ pos)
    assert np.linalg.norm(actual - ref) / np.linalg.norm(ref) < 1e-12
    adapter = IntervalFacetAdapter(p, lambda *_: expected)
    assert np.array_equal(actual, adapter.integral(side, k, J, origin, 60))


@pytest.mark.parametrize(
    "bad",
    [
        "length",
        "frequency",
        "side",
        "basis",
        "complex_tangent",
        "shear",
        "phase_underflow",
    ],
)
def test_identity_geometry_layout_and_irreversible_phase_rejected(bad):
    p = poly()
    side = "top"
    k = np.array([1.7, -0.2, 1.1j])
    J = np.diag([0.2, 6.25, 2.0])
    o = np.array([0.3, 0.1, 1.0])
    expected = facet_identity(p, side, k, J, o)
    if bad == "length":
        J[1, 1] *= 1.01
    elif bad == "frequency":
        k[0] *= 1.01
    elif bad == "side":
        side = "bottom"
    elif bad == "basis":
        p.coefficients["top"][0, 0, 0, 0] += 1e-8
    elif bad == "complex_tangent":
        k[1] += 1e-6j
    elif bad == "shear":
        J[0, 1] = 0.2
    else:
        k[2] = 1000j
        expected = facet_identity(p, side, k, J, o)
    with pytest.raises(ValueError):
        integrate_receiver_facet(p, side, k, J, o, expected=expected)


@pytest.mark.parametrize(
    "omega,degree", [(1j, 4), (float("nan"), 4), (1.0, True), (1.0, 13)]
)
def test_unsupported_interval_input_rejected(omega, degree):
    with pytest.raises(ValueError):
        unit_interval_moments(omega, degree)
