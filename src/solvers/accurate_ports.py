"""Opt-in final port constraint recovery for frozen binary64 inputs.

Products and sums are exact integers, followed by one correctly rounded
binary64 division. This is not a Maxwell solve and does not improve the input
field or quadrature precision. Ordinary packet operations remain unchanged.
"""

from fractions import Fraction
import numpy as np


def _ratio(x):
    n, d = float(x).as_integer_ratio()
    return n, d.bit_length() - 1


def recover_ports(a, c, *, gp=None):
    return recover_ports_components(a, (c,), gp=gp)


def recover_ports_components(a, components, *, gp=None):
    """Accumulate every component before the one final original-H division."""
    components = tuple(np.asarray(c) for c in components)
    if not components:
        raise ValueError("ACCURATE_PORT_COMPONENTS_REQUIRED")
    c = components[0]
    c = np.asarray(c)
    H = np.asarray(a["H"])
    gp = np.asarray(a["gp"] if gp is None else gp)
    dp, dr, dv = (np.asarray(a[k]) for k in ("dp", "dr", "dv"))
    if (
        c.dtype != np.complex128
        or dv.dtype != np.complex128
        or gp.dtype != np.complex128
        or H.ndim != 1
        or gp.shape != H.shape
        or c.ndim != 1
        or dp.shape != dr.shape
        or dp.shape != dv.shape
        or not np.issubdtype(dp.dtype, np.integer)
        or not np.issubdtype(dr.dtype, np.integer)
        or not np.isrealobj(H)
        or np.any(H <= 0)
        or any(not np.isfinite(x).all() for x in (c, H, dv, gp))
        or np.any(dp < 0)
        or np.any(dp >= len(H))
        or np.any(dr < 0)
        or np.any(dr >= len(c))
    ):
        raise ValueError("ACCURATE_PORT_INPUT_INVALID")
    if any(x.dtype != np.complex128 or x.shape != c.shape or not np.isfinite(x).all() for x in components):
        raise ValueError("ACCURATE_PORT_COMPONENT_INVALID")
    bits = 2148  # Two least binary64 subnormals can multiply to 2**-2148.
    real, imag = [], []
    for z in gp:
        n, e = _ratio(z.real)
        real.append(n << (bits - e))
        n, e = _ratio(z.imag)
        imag.append(n << (bits - e))

    def product(x, y):
        n, e = _ratio(x)
        m, f = _ratio(y)
        return (n * m) << (bits - e - f)

    terms = np.zeros(len(H), np.int64)
    absolute_sum = np.abs(gp).copy()
    for c in components:
        for j, row, d in zip(dp, dr, dv, strict=True):
            z = c[row]
            real[j] += product(d.real, z.real) - product(d.imag, z.imag)
            imag[j] += product(d.real, z.imag) + product(d.imag, z.real)
            terms[j] += 1
            absolute_sum[j] += abs(d) * abs(z)
    result = np.empty(len(H), np.complex128)
    for j, h in enumerate(H):
        n, e = _ratio(h)
        denominator = n << (bits - e)
        result[j] = complex(
            float(Fraction(real[j], denominator)), float(Fraction(imag[j], denominator))
        )
    if not np.isfinite(result).all():
        raise ValueError("ACCURATE_PORT_OUTPUT_NOT_FINITE")
    exact_numerator = np.asarray(
        [
            complex(float(Fraction(x, 1 << bits)), float(Fraction(y, 1 << bits)))
            for x, y in zip(real, imag, strict=True)
        ]
    )
    cancellation = absolute_sum / np.maximum(abs(exact_numerator), 1e-300)
    return result, dict(
        method="exact integer binary64 products/sums and rational division",
        input_precision="binary64 frozen field, blocks and rhs",
        output_precision="complex128, one nearest-even rounding per component",
        sum_denominator_power=bits,
        term_counts=terms.tolist(),
        complex_products=len(dv)*len(components),
        input_components=len(components),
        divisions=2 * len(H),
        per_mode_sum_absolute=absolute_sum.tolist(),
        per_mode_exact_numerator_absolute=abs(exact_numerator).tolist(),
        per_mode_cancellation_ratio=cancellation.tolist(),
        changes_field_coefficients=False,
        global_factor_count=0,
    )


def actual_vector_audit(packet, c, alpha, *, total=None, alpha_total=None):
    """Audit the actual published vector; never replace its port components."""
    a = packet.a
    total = c + a["background"] if total is None else total
    alpha_total = alpha + a["background_alpha"] if alpha_total is None else alpha_total
    for v, n in (
        (c, packet.size),
        (total, packet.size),
        (alpha, packet.np),
        (alpha_total, packet.np),
    ):
        if np.asarray(v).shape != (n,) or not np.isfinite(v).all():
            raise ValueError("ACTUAL_PUBLISHED_VECTOR_INVALID")
    body = packet.volume(c) + packet.B(alpha) - a["g"]
    port = -packet.D(c) + a["H"] * alpha - a["gp"]
    tbody = packet.volume(total) + packet.B(alpha_total) - a["total_g"]
    tport = -packet.D(total) + a["H"] * alpha_total
    return dict(
        native_relative=float(
            np.linalg.norm(packet.apply(c) - packet.f) / packet.bnorm
        ),
        augmented_relative=float(
            np.linalg.norm(np.r_[body, port]) / np.linalg.norm(np.r_[a["g"], a["gp"]])
        ),
        original_total_augmented_relative=float(
            np.linalg.norm(np.r_[tbody, tport]) / np.linalg.norm(a["total_g"])
        ),
        scattered_body_relative=float(np.linalg.norm(body) / np.linalg.norm(a["g"])),
        total_body_relative=float(np.linalg.norm(tbody) / np.linalg.norm(a["total_g"])),
        actual_output_used=True,
        port_replaced_during_audit=False,
    )
