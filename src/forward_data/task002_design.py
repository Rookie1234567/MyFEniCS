"""Frozen Task002 angle designs and analytic cutoff/order-window audits."""

from __future__ import annotations

import math
from typing import Any, Iterable

from src.common.modes_3d import enumerate_diffraction_orders_3d

from .orders import FIXED_M_ORDERS
from .task001_config import task001_stage4_config
from .task002_schema import Task002ForwardParameters


LF_GRAZING_DEG = (0.5, 1.0, 2.0, 4.0, 6.0, 8.0, 10.0)
LF_AZIMUTH_DEG = (0.0, 15.0, 30.0, 45.0, 60.0, 75.0, 90.0)
ANGLE_CENTER = (5.25, 45.0)


def angle_id(grazing_deg: float, azimuth_deg: float) -> str:
    def token(value: float) -> str:
        return f"{value:g}".replace(".", "p")
    return f"g{token(grazing_deg)}_a{token(azimuth_deg)}"


def lf_angle_pilot() -> list[dict[str, Any]]:
    return [
        {"angle_id": angle_id(g, a), "grazing_deg": g, "azimuth_deg": a,
         "role": "lf_angle_pilot"}
        for g in LF_GRAZING_DEG for a in LF_AZIMUTH_DEG
    ]


def fixed_hf_angle_pilot() -> list[dict[str, Any]]:
    points = [
        (0.5, 0.0, "corner"), (0.5, 90.0, "corner"),
        (10.0, 0.0, "corner"), (10.0, 90.0, "corner"),
        (0.5, 45.0, "edge_midpoint"), (10.0, 45.0, "edge_midpoint"),
        (5.25, 0.0, "edge_midpoint"), (5.25, 90.0, "edge_midpoint"),
        (5.25, 45.0, "center"),
    ]
    return [
        {"angle_id": angle_id(g, a), "grazing_deg": g, "azimuth_deg": a, "role": role}
        for g, a, role in points
    ]


def _orders(parameters: Task002ForwardParameters, max_abs_m: int = 12):
    cfg = task001_stage4_config(parameters.to_task001())
    return enumerate_diffraction_orders_3d(
        cfg, max_m_override=max_abs_m, max_n_override=0,
    )


def cutoff_diagnostics(
    parameters: Task002ForwardParameters, *, near_cutoff_threshold: float = 0.02,
) -> dict[str, Any]:
    """Return dimensionless beta distance without conflating propagation and power."""

    parameters.validate()
    k0 = 2.0 * math.pi / float(parameters.wavelength_nm)
    rows = []
    for order in _orders(parameters):
        if order.m not in FIXED_M_ORDERS:
            continue
        top_metric = abs(complex(order.beta_top)) / k0
        bottom_metric = abs(complex(order.beta_bottom)) / k0
        rows.append({
            "m": order.m, "n": order.n,
            "top_abs_beta_over_k0": top_metric,
            "bottom_abs_beta_over_k0": bottom_metric,
            "top_dispersion_propagating": bool(order.top_propagating),
            "bottom_dispersion_propagating": bool(order.bottom_propagating),
        })
    metric = min(min(row["top_abs_beta_over_k0"], row["bottom_abs_beta_over_k0"])
                 for row in rows)
    return {
        "cutoff_metric": metric,
        "near_cutoff_threshold": near_cutoff_threshold,
        "near_cutoff": metric <= near_cutoff_threshold,
        "orders": rows,
    }


def audit_order_window(
    angles: Iterable[tuple[float, float]] | None = None,
    *, max_abs_m: int = 12,
) -> dict[str, Any]:
    """Audit every n=0 order that can propagate on the frozen angle grid."""

    if angles is None:
        angles = ((row["grazing_deg"], row["azimuth_deg"]) for row in lf_angle_pilot())
    relevant: set[int] = set()
    nearest: dict[int, float] = {m: float("inf") for m in range(-max_abs_m, max_abs_m + 1)}
    k0 = 2.0 * math.pi / 13.5
    angle_count = 0
    for grazing, azimuth in angles:
        angle_count += 1
        parameters = Task002ForwardParameters(
            120.0, 17.0, grazing, azimuth, "S_LF_HYBRID_P4_H10_M120"
        )
        for order in _orders(parameters, max_abs_m=max_abs_m):
            nearest[order.m] = min(
                nearest[order.m], abs(complex(order.beta_top)) / k0,
                abs(complex(order.beta_bottom)) / k0,
            )
            if order.top_propagating or order.bottom_propagating:
                relevant.add(order.m)
    fixed = set(FIXED_M_ORDERS)
    return {
        "schema_version": "task002.order-window-audit.v1",
        "angle_count": angle_count,
        "searched_m_range": [-max_abs_m, max_abs_m],
        "propagating_m_union": sorted(relevant),
        "fixed_m_orders": list(FIXED_M_ORDERS),
        "missing_propagating_m": sorted(relevant - fixed),
        "coverage_pass": relevant.issubset(fixed),
        "nearest_abs_beta_over_k0": {str(m): value for m, value in nearest.items()},
        "n_nonzero_disposition": (
            "geometry and materials are y-invariant; n!=0 response is numerical leakage, "
            "not a production channel"
        ),
        "power_semantics": (
            "analytic propagation is a dispersion audit; power_carrying remains an "
            "independent measured mother-response field"
        ),
    }
