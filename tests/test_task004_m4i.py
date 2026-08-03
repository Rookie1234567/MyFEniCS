"""Pure tests for the Required M4I threshold and interval contracts."""

from __future__ import annotations

import json

import numpy as np

from src.surrogate.angle.m4i import (
    S1,
    _conformal_report,
    _finite_conformal_quantile,
    _source_threshold,
)


def _window_file(path):
    path.write_text(json.dumps({
        "windows": [{"name": "ordinary_interior",
                      "support_rows": [{"index": 0, "classification": "interior_bracketed"}]}]
    }))
    return path


def test_highest_acceptance_passing_quantile_is_selected(tmp_path):
    n = 20
    truth = np.column_stack([np.full(n, 0.2), np.full(n, 0.3), np.full(n, 0.5)])
    prediction = truth.copy()
    risk = np.linspace(0.0, 1.0, n)
    selected = _source_threshold(np.arange(n), risk, truth, prediction,
                                 _window_file(tmp_path / "windows.json"))
    assert selected["status"] == "qualified"
    assert selected["selected"]["quantile"] == 0.95
    assert selected["source_gate_selection_failed"] is False


def test_fallback_is_not_a_qualified_threshold(tmp_path):
    n = 20
    truth = np.column_stack([np.full(n, 0.2), np.full(n, 0.3), np.full(n, 0.5)])
    prediction = truth + np.asarray([0.2, -0.1, -0.1])
    risk = np.linspace(0.0, 1.0, n)
    selected = _source_threshold(np.arange(n), risk, truth, prediction,
                                 _window_file(tmp_path / "windows.json"))
    assert selected["status"] == "threshold_not_qualified"
    assert selected["source_gate_selection_failed"] is True
    assert selected["selected"] is None


def test_accepted_source_conformal_interval_has_lower_bound_and_sharpness():
    truth = np.asarray([[0.2, 0.3, 0.5], [0.21, 0.29, 0.5], [0.19, 0.31, 0.5]])
    prediction = truth + np.asarray([[0.001, -0.001, 0.0], [-0.001, 0.001, 0.0], [0.0, 0.0, 0.001]])
    accepted = np.asarray([True, True, True])
    radius = np.full_like(truth, 0.01)
    report = _conformal_report(truth, prediction, np.full_like(truth, 0.01), accepted, radius)
    assert report["coverage_gate"] is True
    assert report["sharpness_gate"] is True
    assert all(report["sharpness"][name]["finite_positive"] for name in ("R_total", "T_total", "A_balance"))
    assert _finite_conformal_quantile(np.asarray([0.001, 0.002, 0.003])) >= 0.003

