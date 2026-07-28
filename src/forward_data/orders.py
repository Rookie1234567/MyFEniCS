"""Fixed-identity Task001 diffraction-order extraction."""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

from .schema import TASK001_OBSERVABLE_SCHEMA_VERSION
from .schema import Task001ForwardParameters
from .task001_config import task001_stage4_config
from src.common.modes_3d import enumerate_diffraction_orders_3d


FIXED_M_ORDERS = (0, -1, -2, -3, -4, -5, -6, -7, 1)
SIDES = ("top", "bottom")
POLARIZATIONS = ("s", "p")


def _key(row: Mapping[str, Any]) -> tuple[str, int, int, str]:
    side = str(row.get("side", row.get("port", ""))).lower()
    polarization = str(row.get("polarization", row.get("component", ""))).lower()
    m = int(row.get("m", row.get("order_m")))
    n = int(row.get("n", row.get("order_n")))
    if side not in SIDES or polarization not in POLARIZATIONS:
        raise ValueError(f"invalid diffraction identity: {(side, m, n, polarization)}")
    return side, m, n, polarization


def _power(row: Mapping[str, Any]) -> float | None:
    propagating = row.get("propagating", row.get("power_carrying", True))
    if propagating is False:
        return None
    value = row.get("power", row.get("outgoing_power", row.get("power_ratio")))
    if value is None:
        raise ValueError("propagating diffraction order is missing power")
    return float(value)


def extract_fixed_orders(
    rows: Iterable[Mapping[str, Any]], *, port_power: Mapping[str, Any] | None = None,
    expected_nonpropagating: set[tuple[str, int, int, str]] | None = None,
) -> dict[str, Any]:
    """Extract the fixed window without sorting or zero-filling absent physics."""

    indexed: dict[tuple[str, int, int, str], Mapping[str, Any]] = {}
    n_nonzero_leakage = 0.0
    raw_r_total = 0.0
    raw_t_total = 0.0
    for row in rows:
        key = _key(row)
        if key in indexed:
            raise ValueError(f"duplicate diffraction identity: {key}")
        indexed[key] = row
        power = _power(row)
        raw_r_total += float(row.get("R", power if key[0] == "top" else 0.0) or 0.0)
        raw_t_total += float(row.get("T", power if key[0] == "bottom" else 0.0) or 0.0)
        if key[2] != 0 and power is not None:
            n_nonzero_leakage += power
    extracted: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for side in SIDES:
        for m in FIXED_M_ORDERS:
            for polarization in POLARIZATIONS:
                identity = (side, m, 0, polarization)
                row = indexed.get(identity)
                if row is None:
                    if expected_nonpropagating is not None and identity in expected_nonpropagating:
                        extracted.append({
                            "side": side, "m": m, "n": 0, "polarization": polarization,
                            "propagating": False, "power": None,
                            "outgoing_amplitude_at_boundary": None,
                        })
                        continue
                    missing.append({"side": side, "m": m, "n": 0, "polarization": polarization})
                    continue
                amplitude = row.get("outgoing_amplitude_at_boundary", row.get("complex_amplitude"))
                extracted.append({
                    "side": side, "m": m, "n": 0, "polarization": polarization,
                    "propagating": bool(row.get("propagating", row.get("power_carrying", True))),
                    "power": _power(row), "outgoing_amplitude_at_boundary": amplitude,
                })
    consistency = None
    if port_power is not None:
        expected_r = float(port_power["R_total"])
        expected_t = float(port_power["T_total"])
        consistency = {
            "raw_r_total": raw_r_total,
            "raw_t_total": raw_t_total,
            "reported_r_total": expected_r,
            "reported_t_total": expected_t,
            "r_matches": math.isclose(raw_r_total, expected_r, rel_tol=1.0e-10, abs_tol=1.0e-12),
            "t_matches": math.isclose(raw_t_total, expected_t, rel_tol=1.0e-10, abs_tol=1.0e-12),
        }
        if not consistency["r_matches"] or not consistency["t_matches"]:
            raise ValueError(f"raw diffraction totals disagree with port power: {consistency}")
    return {
        "schema_version": TASK001_OBSERVABLE_SCHEMA_VERSION,
        "fixed_m_order": list(FIXED_M_ORDERS),
        "orders": extracted, "missing": missing,
        "n_nonzero_leakage_power": n_nonzero_leakage,
        "raw_r_total": raw_r_total,
        "raw_t_total": raw_t_total,
        "port_power_consistency": consistency,
        "fixed_window_power_sum": sum(row["power"] for row in extracted if row["power"] is not None),
        "semantics": "fixed identity window; not R/T total; nonpropagating power is null",
    }


def extract_task001_orders(
    rows: Iterable[Mapping[str, Any]], *, parameters: Task001ForwardParameters,
    port_power: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify omitted auto-DtN identities with the authoritative dispersion model."""

    cfg = task001_stage4_config(parameters)
    analytic = {
        (order.m, order.n): order
        for order in enumerate_diffraction_orders_3d(
            cfg, max_m_override=max(abs(value) for value in FIXED_M_ORDERS),
            max_n_override=0,
        )
    }
    expected_nonpropagating: set[tuple[str, int, int, str]] = set()
    for m in FIXED_M_ORDERS:
        order = analytic[(m, 0)]
        for side, propagating in (
            ("top", order.top_propagating), ("bottom", order.bottom_propagating)
        ):
            if not propagating:
                for polarization in POLARIZATIONS:
                    expected_nonpropagating.add((side, m, 0, polarization))
    result = extract_fixed_orders(
        rows, port_power=port_power,
        expected_nonpropagating=expected_nonpropagating,
    )
    result["analytic_nonpropagating_identities"] = [
        {"side": side, "m": m, "n": n, "polarization": polarization}
        for side, m, n, polarization in sorted(expected_nonpropagating)
    ]
    return result
