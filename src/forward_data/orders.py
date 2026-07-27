"""Fixed-identity Task001 diffraction-order extraction."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .schema import TASK001_OBSERVABLE_SCHEMA_VERSION


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
    value = row.get("power", row.get("outgoing_power"))
    if value is None:
        raise ValueError("propagating diffraction order is missing power")
    return float(value)


def extract_fixed_orders(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Extract the fixed window without sorting or zero-filling absent physics."""

    indexed: dict[tuple[str, int, int, str], Mapping[str, Any]] = {}
    n_nonzero_leakage = 0.0
    for row in rows:
        key = _key(row)
        if key in indexed:
            raise ValueError(f"duplicate diffraction identity: {key}")
        indexed[key] = row
        power = _power(row)
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
                    missing.append({"side": side, "m": m, "n": 0, "polarization": polarization})
                    continue
                amplitude = row.get("outgoing_amplitude_at_boundary", row.get("complex_amplitude"))
                extracted.append({
                    "side": side, "m": m, "n": 0, "polarization": polarization,
                    "propagating": bool(row.get("propagating", row.get("power_carrying", True))),
                    "power": _power(row), "outgoing_amplitude_at_boundary": amplitude,
                })
    return {
        "schema_version": TASK001_OBSERVABLE_SCHEMA_VERSION,
        "fixed_m_order": list(FIXED_M_ORDERS),
        "orders": extracted, "missing": missing,
        "n_nonzero_leakage_power": n_nonzero_leakage,
        "fixed_window_power_sum": sum(row["power"] for row in extracted if row["power"] is not None),
        "semantics": "fixed identity window; not R/T total; nonpropagating power is null",
    }
