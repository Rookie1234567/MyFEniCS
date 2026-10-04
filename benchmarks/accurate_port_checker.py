"""Independent Decimal port constraint checker; no producer recovery import."""

from decimal import Decimal, localcontext
import numpy as np


def decimal_ports(a, c, *, gp=None, precision=110):
    H, dp, dr, dv = (a[k] for k in ("H", "dp", "dr", "dv"))
    gp = a["gp"] if gp is None else gp
    if (
        np.asarray(c).dtype != np.complex128
        or np.asarray(c).ndim != 1
        or np.asarray(H).ndim != 1
        or not np.isrealobj(H)
        or np.any(H <= 0)
        or np.shape(gp) != np.shape(H)
        or np.shape(dp) != np.shape(dr)
        or np.shape(dp) != np.shape(dv)
        or np.any(dp < 0)
        or np.any(dp >= len(H))
        or np.any(dr < 0)
        or np.any(dr >= len(c))
        or any(not np.isfinite(v).all() for v in (H, dp, dr, dv, gp, c))
    ):
        raise ValueError("DECIMAL_PORT_INVALID_RAW_LAYOUT")
    with localcontext() as ctx:
        ctx.prec = precision
        real = [Decimal.from_float(float(z.real)) for z in gp]
        imag = [Decimal.from_float(float(z.imag)) for z in gp]
        for j, row, d in zip(dp, dr, dv, strict=True):
            u, v = Decimal.from_float(float(d.real)), Decimal.from_float(float(d.imag))
            x, y = (
                Decimal.from_float(float(c[row].real)),
                Decimal.from_float(float(c[row].imag)),
            )
            real[j] += u * x - v * y
            imag[j] += u * y + v * x
        return np.asarray(
            [
                complex(
                    float(x / Decimal.from_float(float(h))),
                    float(y / Decimal.from_float(float(h))),
                )
                for x, y, h in zip(real, imag, H, strict=True)
            ],
            dtype=np.complex128,
        )


def check_published(a, state, *, expected_mode_hash, mode_hash):
    if mode_hash != expected_mode_hash:
        raise ValueError("ACCURATE_PORT_MODE_IDENTITY")
    for key in ("masters", "background", "background_alpha"):
        if not np.array_equal(a[key], state[key]):
            raise ValueError("ACCURATE_PORT_BACKGROUND_OR_MASTER_IDENTITY")
    if not np.array_equal(
        state["c_total"], state["c_scattered"] + state["background"]
    ) or not np.array_equal(
        state["alpha_total"], state["alpha_scattered"] + state["background_alpha"]
    ):
        raise ValueError("ACCURATE_PORT_AFFINE_IDENTITY")
    rows = {}
    for name, gp in (("scattered", a["gp"]), ("total", np.zeros_like(a["gp"]))):
        c, actual = state["c_" + name], state["alpha_" + name]
        if actual.shape != a["H"].shape or not np.isfinite(actual).all():
            raise ValueError("ACCURATE_PORT_OUTPUT_LAYOUT")
        expected = decimal_ports(a, c, gp=gp, precision=110)
        other = decimal_ports(a, c, gp=gp, precision=90)
        relative = float(
            np.linalg.norm(actual - expected) / max(np.linalg.norm(expected), 1e-12)
        )
        rows[name] = dict(
            original_coordinates_relative=relative,
            decimal_90_110_equal=bool(np.array_equal(expected, other)),
            expected_norm=float(np.linalg.norm(expected)),
            actual_norm=float(np.linalg.norm(actual)),
        )
    background = decimal_ports(a, state["background"], gp=np.zeros_like(a["gp"]))
    background_relative = float(
        np.linalg.norm(background - state["background_alpha"])
        / max(np.linalg.norm(background), 1e-12)
    )
    return dict(
        passed=rows["scattered"]["original_coordinates_relative"] <= 1e-10
        and rows["scattered"]["decimal_90_110_equal"]
        and background_relative <= 1e-10,
        rows=rows,
        background_original_coordinates_relative=background_relative,
        recovery_gate="alpha_scattered=H^-1(gp+D*c_scattered), background separately; actual affine total equation gated by full residual",
        total_rounding_difference_scope="diagnostic: rounded c_total addition versus affine alpha_total, not a silently replaced vector",
        independent_arithmetic="Decimal 90/110",
        no_FE_or_solve=True,
    )
