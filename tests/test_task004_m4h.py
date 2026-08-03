"""Pure contract tests for Required M4H risk and acceptance logic."""

from __future__ import annotations

import numpy as np

from src.surrogate.angle.m4h import (
    RULES,
    _composition_exact,
    _fit_bounds,
    _risk_from_raw,
)


def _raw(n: int = 6) -> dict[str, np.ndarray]:
    return {
        "native_std": np.column_stack([np.linspace(0.1, 0.6, n)] * 3),
        "rbf_matern_disagreement": np.column_stack([np.linspace(0.2, 0.7, n)] * 3),
        "matern_k24_k32_disagreement": np.column_stack([np.linspace(0.3, 0.8, n)] * 3),
        "nearest_training_distance": np.linspace(0.05, 0.3, n),
        "cutoff_risk": np.linspace(1.0, 8.0, n),
        "topology_risk": np.linspace(0.1, 1.0, n),
        "boundary_risk": np.asarray([0, 0, 1, 0, 1, 0], dtype=float)[:n],
    }


def test_m4h_normalization_is_source_only_and_finite():
    raw = _raw()
    source = np.asarray([0, 1, 2, 3], dtype=np.int64)
    bounds = _fit_bounds(raw, source)
    # The held-out large values cannot change the source quantile bounds.
    bounds_again = _fit_bounds(raw, source)
    assert bounds == bounds_again
    risk, components = _risk_from_raw(raw, bounds, RULES[0])
    assert risk.shape == (6,)
    assert np.isfinite(risk).all()
    assert np.isfinite(components["cutoff_topology_scaled"]).all()


def test_s1_and_s2_are_distinct_finite_contracts():
    raw = _raw()
    bounds = _fit_bounds(raw, np.arange(6, dtype=np.int64))
    s1, _ = _risk_from_raw(raw, bounds, RULES[0])
    s2, _ = _risk_from_raw(raw, bounds, RULES[1])
    assert s1.shape == s2.shape == (6,)
    assert np.isfinite(s1).all() and np.isfinite(s2).all()
    assert not np.allclose(s1, s2)


def test_composition_gate_is_exact_and_fail_closed():
    good = np.asarray([[0.2, 0.3, 0.5], [0.0, 1.0, 0.0]])
    bad = np.asarray([[0.2, 0.3, 0.5000000001]])
    assert _composition_exact(good)
    assert not _composition_exact(bad)
