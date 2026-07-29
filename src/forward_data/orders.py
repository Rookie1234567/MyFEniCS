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
    value = row.get("power", row.get("outgoing_power", row.get("power_ratio")))
    if value is None:
        if row.get("power_carrying", row.get("propagating", True)) is False:
            return None
        raise ValueError("power-carrying diffraction order is missing power")
    power = float(value)
    if power < 0.0:
        raise ValueError("outgoing diffraction power must be nonnegative")
    # The solver's historical ``propagating`` flag is a dispersion
    # classification.  A below-critical mode in a lossy substrate may retain
    # propagating=false while carrying positive outward real-Poynting flux.
    # Port R/T includes every such positive contribution.
    carrying = row.get("power_carrying")
    if carrying is None:
        carrying = row.get("propagating", True) is not False or power > 0.0
    return power if carrying else None


def _dispersion_propagating(row: Mapping[str, Any]) -> bool:
    return bool(row.get("dispersion_propagating", row.get("propagating", True)))


def _complex_json(value: complex | list[float] | tuple[float, float]) -> dict[str, float]:
    if isinstance(value, (list, tuple)):
        if len(value) != 2:
            raise ValueError("complex JSON value must contain [real, imaginary]")
        number = complex(float(value[0]), float(value[1]))
    else:
        number = complex(value)
    return {"re": float(number.real), "im": float(number.imag)}


def _amplitude_json(row: Mapping[str, Any]) -> dict[str, float] | None:
    value = row.get("outgoing_amplitude_at_boundary", row.get("complex_amplitude"))
    return None if value is None else _complex_json(value)


def _wavevector_from_row(row: Mapping[str, Any]) -> dict[str, dict[str, float]] | None:
    if all(key in row for key in ("kx", "ky", "kz")):
        return {key: _complex_json(row[key]) for key in ("kx", "ky", "kz")}
    return None


def extract_fixed_orders(
    rows: Iterable[Mapping[str, Any]], *, port_power: Mapping[str, Any] | None = None,
    expected_nonpropagating: set[tuple[str, int, int, str]] | None = None,
    incident_polarization: str | None = None,
    wavevectors: Mapping[tuple[str, int, int], Mapping[str, complex]] | None = None,
    fixed_m_orders: tuple[int, ...] = FIXED_M_ORDERS,
    schema_version: str = TASK001_OBSERVABLE_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Extract grouped S/P mother responses without zero-filling absent physics."""

    indexed: dict[tuple[str, int, int, str], Mapping[str, Any]] = {}
    n_nonzero_reflection = 0.0
    n_nonzero_transmission = 0.0
    n_nonzero_max_amplitude = 0.0
    raw_r_total = 0.0
    raw_t_total = 0.0
    for row in rows:
        key = _key(row)
        if key in indexed:
            raise ValueError(f"duplicate diffraction identity: {key}")
        indexed[key] = row
        power = _power(row)
        raw_r_total += float(power or 0.0) if key[0] == "top" else 0.0
        raw_t_total += float(power or 0.0) if key[0] == "bottom" else 0.0
        if key[2] != 0:
            if power is not None and key[0] == "top":
                n_nonzero_reflection += power
            if power is not None and key[0] == "bottom":
                n_nonzero_transmission += power
            amplitude = _amplitude_json(row)
            if amplitude is not None:
                n_nonzero_max_amplitude = max(
                    n_nonzero_max_amplitude,
                    math.hypot(amplitude["re"], amplitude["im"]),
                )
    extracted: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for side in SIDES:
        for m in fixed_m_orders:
            component_rows: dict[str, dict[str, Any]] = {}
            dispersion_flags: list[bool] = []
            row_wavevector = None
            for polarization in POLARIZATIONS:
                identity = (side, m, 0, polarization)
                row = indexed.get(identity)
                if row is None:
                    if expected_nonpropagating is not None and identity in expected_nonpropagating:
                        component_rows[polarization] = {
                            "amplitude_re": None, "amplitude_im": None,
                            "power": None, "power_carrying": False,
                        }
                        dispersion_flags.append(False)
                        continue
                    missing.append({
                        "side": "reflection" if side == "top" else "transmission",
                        "port_side": side, "m": m, "n": 0,
                        "component": polarization,
                    })
                    continue
                power = _power(row)
                amplitude = _amplitude_json(row)
                component_rows[polarization] = {
                    "amplitude_re": None if amplitude is None else amplitude["re"],
                    "amplitude_im": None if amplitude is None else amplitude["im"],
                    "power": power, "power_carrying": power is not None,
                }
                dispersion_flags.append(_dispersion_propagating(row))
                candidate_wavevector = _wavevector_from_row(row)
                if candidate_wavevector is not None:
                    if row_wavevector is not None and candidate_wavevector != row_wavevector:
                        raise ValueError(f"S/P wavevector identity mismatch for {(side, m, 0)}")
                    row_wavevector = candidate_wavevector
            if len(component_rows) != len(POLARIZATIONS):
                continue
            if len(set(dispersion_flags)) != 1:
                raise ValueError(f"S/P dispersion identity mismatch for {(side, m, 0)}")
            identity = (side, m, 0)
            supplied = None if wavevectors is None else wavevectors.get(identity)
            if supplied is not None:
                grouped_wavevector = {
                    key: _complex_json(supplied[key]) for key in ("kx", "ky", "kz")
                }
                if row_wavevector is not None and grouped_wavevector != row_wavevector:
                    raise ValueError(f"raw/analytic wavevector mismatch for {identity}")
            elif row_wavevector is not None:
                grouped_wavevector = row_wavevector
            else:
                raise ValueError(f"missing wavevector identity for {identity}")
            powers = [
                component_rows[polarization]["power"]
                for polarization in POLARIZATIONS
                if component_rows[polarization]["power"] is not None
            ]
            extracted.append({
                "side": "reflection" if side == "top" else "transmission",
                "port_side": side, "m": m, "n": 0,
                **grouped_wavevector,
                "dispersion_propagating": dispersion_flags[0],
                "power_carrying": bool(powers),
                "components": component_rows,
                "order_total_power": sum(powers) if powers else None,
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
        "schema_version": schema_version,
        "incident_polarization": None if incident_polarization is None else incident_polarization.upper(),
        "wavevector_unit": "1/nm",
        "wavevector_convention": (
            "outgoing wavevector: reflection/top kz=+beta_top; "
            "transmission/bottom kz=-beta_bottom"
        ),
        "fixed_m_order": list(fixed_m_orders),
        "orders": extracted, "missing": missing,
        "leakage": {
            "n_nonzero_reflection_power_sum": n_nonzero_reflection,
            "n_nonzero_transmission_power_sum": n_nonzero_transmission,
            "n_nonzero_max_abs_amplitude": n_nonzero_max_amplitude,
        },
        "raw_r_total": raw_r_total,
        "raw_t_total": raw_t_total,
        "port_power_consistency": consistency,
        "fixed_window_power_sum": sum(
            row["order_total_power"] for row in extracted
            if row["order_total_power"] is not None
        ),
        "semantics": (
            "fixed grouped S/P mother-response window; not R/T total; wavevectors and "
            "boundary amplitudes use explicit real/imaginary JSON; power_carrying is "
            "separate from dispersion_propagating; non-power-carrying component and "
            "order powers are null; n!=0 is leakage-only"
        ),
    }


def extract_task001_orders(
    rows: Iterable[Mapping[str, Any]], *, parameters: Task001ForwardParameters,
    port_power: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify omitted auto-DtN identities with the authoritative dispersion model."""

    raw_rows = list(rows)
    cfg = task001_stage4_config(parameters)
    analytic = {
        (order.m, order.n): order
        for order in enumerate_diffraction_orders_3d(
            cfg, max_m_override=max(abs(value) for value in FIXED_M_ORDERS),
            max_n_override=0,
        )
    }
    expected_nonpropagating: set[tuple[str, int, int, str]] = set()
    wavevectors: dict[tuple[str, int, int], dict[str, complex]] = {}
    for m in FIXED_M_ORDERS:
        order = analytic[(m, 0)]
        for side, propagating in (
            ("top", order.top_propagating), ("bottom", order.bottom_propagating)
        ):
            beta = order.beta_top if side == "top" else order.beta_bottom
            wavevectors[(side, m, 0)] = {
                "kx": order.alpha, "ky": order.gamma,
                "kz": beta if side == "top" else -beta,
            }
            if not propagating:
                for polarization in POLARIZATIONS:
                    expected_nonpropagating.add((side, m, 0, polarization))
    result = extract_fixed_orders(
        raw_rows, port_power=port_power,
        expected_nonpropagating=expected_nonpropagating,
        incident_polarization=parameters.incident_polarization,
        wavevectors=wavevectors,
    )
    for row in raw_rows:
        key = _key(row)
        if key[2] != 0 or key[1] not in FIXED_M_ORDERS or "beta_per_nm" not in row:
            continue
        expected_kz = wavevectors[(key[0], key[1], key[2])]["kz"]
        expected_beta = expected_kz if key[0] == "top" else -expected_kz
        raw_beta = complex(*map(float, row["beta_per_nm"]))
        if not (
            math.isclose(raw_beta.real, expected_beta.real, rel_tol=1.0e-12, abs_tol=1.0e-12)
            and math.isclose(raw_beta.imag, expected_beta.imag, rel_tol=1.0e-12, abs_tol=1.0e-12)
        ):
            raise ValueError(f"raw/analytic beta mismatch for {key}")
    result["analytic_nonpropagating_identities"] = [
        {"side": side, "m": m, "n": n, "polarization": polarization}
        for side, m, n, polarization in sorted(expected_nonpropagating)
    ]
    return result
