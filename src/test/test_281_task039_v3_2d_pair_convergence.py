"""Focused contracts for the offline V3 2D pair checker."""

from __future__ import annotations

import numpy as np
import pytest

import benchmarks.task039_2d_pair_convergence as pair


def _run(
    *,
    source="source",
    scalar_shift=0.0,
    order_shift=0.0,
    field_shift=0.0,
    coordinate_shift=0.0,
    weak_shift=0.0,
    degree=6,
):
    rows = []
    for order in range(-21, 22):
        rows.append(
            {
                "order": order,
                "top_propagating": -19 <= order <= 0,
                "bottom_propagating": -19 <= order <= -1,
                "reflected_Ez_real": 0.0,
                "reflected_Ez_imag": 0.0,
                "transmitted_Ez_real": 0.0,
                "transmitted_Ez_imag": 0.0,
                "R_order": (0.2 + order_shift if order == 0 else 1e-8 + weak_shift),
                "T_order": 0.1 if order == -1 else 1e-8 + weak_shift,
            }
        )
    fields = {
        "x_nm": np.linspace(-1.0, 1.0, 40) + coordinate_shift,
        "z_nm": np.arange(7.0),
        "electric_y_V_per_m": np.ones((7, 40), dtype=np.complex128)
        * (1.0 + field_shift),
        "magnetic_x_A_per_m": np.ones((7, 40), dtype=np.complex128) * 2.0,
        "magnetic_z_A_per_m": np.ones((7, 40), dtype=np.complex128) * 3.0,
    }
    power = {
        "R_total": 0.2 + scalar_shift,
        "T_total": 0.1,
        "A_balance": 0.7 - scalar_shift,
        "A_volume": 0.7 - scalar_shift,
        "orders": rows,
        "port_dtn_order_count": 21,
    }
    return {
        "root": "synthetic",
        "reference": {"linear": {}, "elapsed_seconds": 1.0},
        "power": power,
        "orders": {row["order"]: row for row in rows},
        "closure": 0.0,
        "fields": fields,
        "source_sha": source,
        "input_sha": "input",
        "physical_sha": "physical",
        "model_id": "task039_5nm_v3_1deg_s5",
        "mesh_target_nm": 5.0,
        "degree": degree,
        "visualization_degree": degree,
        "space_identity": {
            "family": "Lagrange",
            "cell": "quadrilateral",
            "degree": degree,
        },
        "resolved_method": "2d_port",
        "resolved_solver": "direct",
    }


def _compare(monkeypatch, left, right):
    runs = {"left": left, "right": right}
    monkeypatch.setattr(pair, "_load_formal_run", lambda path, label: runs[str(path)])
    return pair.compare_2d_pair("left", "right")


def test_identical_pair_passes_and_reports_source_identity(monkeypatch):
    result = _compare(monkeypatch, _run(), _run(source="different"))
    assert result["pass"]
    assert result["source_identity"]["source_sha_equal"] is False
    assert result["gates"]["all_order_weighted_power"]


def test_scalar_gate_rejects_observable_delta(monkeypatch):
    result = _compare(monkeypatch, _run(), _run(scalar_shift=2e-6))
    assert not result["pass"]
    assert not result["gates"]["scalar_observables"]


def test_primary_order_gate_reports_absolute_and_relative_delta(monkeypatch):
    result = _compare(monkeypatch, _run(), _run(order_shift=5e-5))
    row = next(row for row in result["primary_power_rows"]["rows"] if row["order"] == 0)
    assert not result["gates"]["primary_propagating_orders"]
    assert row["absolute_delta"] == pytest.approx(5e-5)
    assert row["denominator"] == pytest.approx(0.20005)


def test_field_and_coordinate_gates_fail_closed(monkeypatch):
    field_result = _compare(monkeypatch, _run(), _run(field_shift=2e-3))
    coordinate_result = _compare(monkeypatch, _run(), _run(coordinate_shift=1e-9))
    assert not field_result["gates"]["electric_field"]
    assert not coordinate_result["gates"]["electric_field"]
    assert coordinate_result["coordinates"]["exact"] is False


def test_all_order_weighted_gate_catches_weak_rows(monkeypatch):
    result = _compare(monkeypatch, _run(), _run(weak_shift=2e-7))
    assert not result["gates"]["all_order_weighted_power"]
    assert result["all_order_weighted_power"]["denominator"] > 0


def test_pair_rejects_mismatched_scalar_degree(monkeypatch):
    with pytest.raises(ValueError, match="scalar degree"):
        _compare(monkeypatch, _run(degree=6), _run(degree=8))
