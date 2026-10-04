"""Independent exact rational sum identity and Decimal dual-component check."""

from fractions import Fraction
from decimal import Decimal, localcontext
import numpy as np


def exact_sum_identity(a, b, hi, lo):
    if any(
        x.dtype != np.complex128 or x.shape != a.shape or not np.isfinite(x).all()
        for x in (a, b, hi, lo)
    ):
        raise ValueError("AFFINE_CHECK_LAYOUT")
    for component in ("real", "imag"):
        arrays = [getattr(x, component).ravel() for x in (a, b, hi, lo)]
        for x, y, h, low in zip(*arrays, strict=True):
            if Fraction(float(x)) + Fraction(float(y)) != Fraction(float(h)) + Fraction(
                float(low)
            ):
                raise ValueError("AFFINE_CHECK_LOW_BITS_LOST_OR_CORRUPTED")
            if float(x + y) != float(h):
                raise ValueError("AFFINE_CHECK_NONCANONICAL_COMPONENT_ORDER")
    return True


def decimal_components(a, components, gp, precision=110):
    with localcontext() as ctx:
        ctx.prec = precision
        dr = [Decimal.from_float(float(x.real)) for x in gp]
        di = [Decimal.from_float(float(x.imag)) for x in gp]
        for c in components:
            for j, row, d in zip(a["dp"], a["dr"], a["dv"], strict=True):
                u, v = (
                    Decimal.from_float(float(d.real)),
                    Decimal.from_float(float(d.imag)),
                )
                x, y = (
                    Decimal.from_float(float(c[row].real)),
                    Decimal.from_float(float(c[row].imag)),
                )
                dr[j] += u * x - v * y
                di[j] += u * y + v * x
        return np.asarray(
            [
                complex(
                    float(r / Decimal.from_float(float(h))),
                    float(i / Decimal.from_float(float(h))),
                )
                for r, i, h in zip(dr, di, a["H"], strict=True)
            ]
        )


def check_state(a, state, *, mode_hash, expected_mode_hash):
    if mode_hash != expected_mode_hash:
        raise ValueError("AFFINE_CHECK_MODE_IDENTITY")
    if str(state["schema"]) != "exact_affine_FE_hi_lo.v1":
        raise ValueError("AFFINE_CHECK_SCHEMA")
    for k in ("background", "background_alpha", "masters"):
        if not np.array_equal(a[k], state[k]):
            raise ValueError("AFFINE_CHECK_BACKGROUND_OR_MASTER")
    exact_sum_identity(
        state["c_scattered"], state["background"], state["total_hi"], state["total_lo"]
    )
    exact_sum_identity(
        state["alpha_scattered"],
        state["background_alpha"],
        state["alpha_total_hi"],
        state["alpha_total_lo"],
    )
    zero = np.zeros_like(a["gp"])
    rows = {}
    for name, cs, actual, gp in (
        ("scattered", (state["c_scattered"],), state["alpha_scattered"], a["gp"]),
        ("background", (state["background"],), state["background_alpha"], zero),
        (
            "total",
            (state["total_hi"], state["total_lo"]),
            state["alpha_total_hi"].astype(np.clongdouble)
            + state["alpha_total_lo"].astype(np.clongdouble),
            zero,
        ),
    ):
        expected = decimal_components(a, cs, gp)
        r = float(
            np.linalg.norm(actual - expected) / max(np.linalg.norm(expected), 1e-12)
        )
        delta = abs(actual - expected)
        denominator = np.maximum(abs(expected), 1e-12)
        rows[name] = {
            "original_coordinates_relative": r,
            "all_modes": len(expected),
            "per_mode_absolute": np.asarray(delta, float).tolist(),
            "per_mode_denominator": np.asarray(denominator, float).tolist(),
            "per_mode_relative": np.asarray(delta / denominator, float).tolist(),
        }
    lossy = decimal_components(a, (state["total_hi"],), zero)
    rows["lossy_single_array_negative"] = {
        "relative": float(
            np.linalg.norm(
                lossy
                - (
                    state["alpha_total_hi"].astype(np.clongdouble)
                    + state["alpha_total_lo"].astype(np.clongdouble)
                )
            )
            / max(np.linalg.norm(lossy), 1e-12)
        ),
        "qualified": False,
    }
    return {
        "passed": all(
            rows[k]["original_coordinates_relative"] <= 1e-10
            for k in ("scattered", "background", "total")
        ),
        "rows": rows,
        "exact_sum_identity": True,
        "all_consumers_required": True,
    }
