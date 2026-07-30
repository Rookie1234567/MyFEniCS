"""Frozen Task002 angle designs and analytic cutoff/order-window audits."""

from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np

from src.common.modes_3d import enumerate_diffraction_orders_3d

from .task002_full3d import build_task002_full3d_config
from .task002_schema import TASK002_FIXED_M_ORDERS, Task002ForwardParameters


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
    cfg = build_task002_full3d_config(parameters)
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
        if order.m not in TASK002_FIXED_M_ORDERS:
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


def _complex_record(value: complex) -> dict[str, float]:
    value = complex(value)
    return {"real": float(value.real), "imag": float(value.imag)}


def incident_wave_audit(parameters: Task002ForwardParameters) -> dict[str, Any]:
    """Record the runtime incident-wave identity used by the Stage-4 authority."""

    parameters.validate()
    cfg = build_task002_full3d_config(parameters)
    k = np.asarray(cfg.wavevector, dtype=np.complex128)
    e = complex(cfg.incident_amplitude) * np.asarray(
        cfg.polarization_vector, dtype=np.complex128,
    )
    h = np.cross(k, e) / (cfg.k0 * complex(cfg.mu_r))
    poynting = 0.5 * np.real(np.cross(e, np.conj(h)))
    k_real = np.real(k)
    k_norm = float(np.linalg.norm(k))
    s_norm = float(np.linalg.norm(poynting))
    return {
        "schema_version": "task002.incident-wave-audit.v1",
        "wavevector": {
            "kx": _complex_record(k[0]), "ky": _complex_record(k[1]),
            "kz": _complex_record(k[2]),
        },
        "abs_k_over_k0_abs_n_air": k_norm / abs(cfg.k0 * complex(cfg.n_air)),
        "mean_poynting": [float(value) for value in poynting],
        "mean_poynting_norm": s_norm,
        "k_dot_poynting": float(np.dot(k_real, poynting)),
        "k_poynting_direction_cosine": (
            float(np.dot(k_real, poynting) / (np.linalg.norm(k_real) * s_norm))
            if np.linalg.norm(k_real) > 0.0 and s_norm > 0.0 else None
        ),
        "floquet_phase_x": _complex_record(cfg.floquet_phase_x),
        "floquet_phase_y": _complex_record(cfg.floquet_phase_y),
        "incident_normal_power_density": float(-poynting[2]),
        "incident_normal_power_code_units": float(
            -poynting[2] * (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)
        ),
        "angle_convention": "theta_from_downward_normal_deg = 90 - grazing_deg",
    }


def cutoff_diagnostics_v2(
    parameters: Task002ForwardParameters, *, max_abs_m: int = 12,
    neighborhood_half_width_deg: float = 0.25,
) -> dict[str, Any]:
    """Separate incident grazing from genuine nonzero-order Rayleigh proximity."""

    parameters.validate()
    cfg = build_task002_full3d_config(parameters)
    k0 = float(cfg.k0)
    rows: list[dict[str, Any]] = []
    for order in _orders(parameters, max_abs_m=max_abs_m):
        rows.append({
            "side": "both", "m": int(order.m), "n": int(order.n),
            "kx": _complex_record(order.alpha),
            "ky": _complex_record(order.gamma),
            "beta_top": _complex_record(order.beta_top),
            "beta_bottom": _complex_record(order.beta_bottom),
            "top_abs_beta_over_k0": abs(complex(order.beta_top)) / k0,
            "bottom_abs_beta_over_k0": abs(complex(order.beta_bottom)) / k0,
            "top_dispersion_propagating": bool(order.top_propagating),
            "bottom_dispersion_propagating": bool(order.bottom_propagating),
        })

    zero = next(row for row in rows if row["m"] == 0 and row["n"] == 0)
    nonincident_candidates = [
        (row[f"{side}_abs_beta_over_k0"], side, row)
        for row in rows if (row["m"], row["n"]) != (0, 0)
        for side in ("top", "bottom")
    ]
    nearest_metric, nearest_side, nearest_row = min(
        nonincident_candidates, key=lambda item: item[0],
    )

    grazing_lo = max(0.5, parameters.grazing_deg - neighborhood_half_width_deg)
    grazing_hi = min(10.0, parameters.grazing_deg + neighborhood_half_width_deg)
    azimuth_lo = max(0.0, parameters.azimuth_deg - neighborhood_half_width_deg)
    azimuth_hi = min(90.0, parameters.azimuth_deg + neighborhood_half_width_deg)
    crossing_orders: set[tuple[int, int]] = set()
    propagation_states: dict[tuple[int, int], set[bool]] = {}
    for grazing in np.linspace(grazing_lo, grazing_hi, 11):
        for azimuth in np.linspace(azimuth_lo, azimuth_hi, 11):
            probe = Task002ForwardParameters(
                parameters.height_nm, parameters.width_x_nm, float(grazing),
                float(azimuth), parameters.model_id,
            )
            for order in _orders(probe, max_abs_m=max_abs_m):
                if (order.m, order.n) == (0, 0):
                    continue
                key = (int(order.m), int(order.n))
                propagation_states.setdefault(key, set()).add(bool(order.top_propagating))
    crossing_orders.update(
        key for key, states in propagation_states.items() if len(states) > 1
    )
    return {
        "schema_version": "task002.cutoff-diagnostics.v2",
        "incident_specular_abs_beta_over_k0": zero["top_abs_beta_over_k0"],
        "nearest_nonincident_abs_beta_over_k0": float(nearest_metric),
        "nearest_order": {
            "side": nearest_side, "m": nearest_row["m"], "n": nearest_row["n"],
        },
        "rayleigh_crossing_in_local_angle_neighborhood": bool(crossing_orders),
        "crossing_nonzero_orders": [
            {"side": "top", "m": m, "n": n} for m, n in sorted(crossing_orders)
        ],
        "local_angle_neighborhood": {
            "grazing_deg": [grazing_lo, grazing_hi],
            "azimuth_deg": [azimuth_lo, azimuth_hi],
            "grid_shape": [11, 11],
            "scope": "lossless top-port nonzero diffraction orders",
        },
        "interpretation": (
            "incident m0 grazing is reported separately and is not classified as "
            "a nonzero-order Rayleigh crossing"
        ),
        "orders": rows,
        "incident_wave_audit": incident_wave_audit(parameters),
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
            120.0, 17.0, grazing, azimuth, "S_PROD_FULL3D_STATIC_P5_H10_NY4"
        )
        for order in _orders(parameters, max_abs_m=max_abs_m):
            nearest[order.m] = min(
                nearest[order.m], abs(complex(order.beta_top)) / k0,
                abs(complex(order.beta_bottom)) / k0,
            )
            if order.top_propagating or order.bottom_propagating:
                relevant.add(order.m)
    fixed = set(TASK002_FIXED_M_ORDERS)
    return {
        "schema_version": "task002.order-window-audit.v1",
        "angle_count": angle_count,
        "searched_m_range": [-max_abs_m, max_abs_m],
        "propagating_m_union": sorted(relevant),
        "fixed_m_orders": list(TASK002_FIXED_M_ORDERS),
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
