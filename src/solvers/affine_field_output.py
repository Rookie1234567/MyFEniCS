"""Explicit opt-in exact affine FE output; ordinary single-array paths unchanged.

Two binary64 components represent their exact real sum. Implicit ndarray
conversion is forbidden. Consumers must apply linear maps to BOTH components;
quadratic physical observables combine them only after field evaluation.
"""

from dataclasses import dataclass
import numpy as np


def two_sum(a, b):
    a, b = np.asarray(a), np.asarray(b)
    if a.dtype != np.complex128 or b.dtype != np.complex128 or a.shape != b.shape:
        raise ValueError("AFFINE_OUTPUT_COMPLEX128_LAYOUT")
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("AFFINE_OUTPUT_NONFINITE")
    parts = []
    for x, y in ((a.real, b.real), (a.imag, b.imag)):
        s = x + y
        v = s - x
        e = (x - (s - v)) + (y - v)
        if not np.isfinite(s).all() or not np.isfinite(e).all():
            raise ValueError("AFFINE_OUTPUT_OVERFLOW")
        parts.append((s, e))
    return SplitVector(parts[0][0] + 1j * parts[1][0], parts[0][1] + 1j * parts[1][1])


@dataclass(frozen=True)
class SplitVector:
    hi: np.ndarray
    lo: np.ndarray

    def __post_init__(self):
        for a in (self.hi, self.lo):
            if a.dtype != np.complex128 or not np.isfinite(a).all():
                raise ValueError("AFFINE_OUTPUT_COMPONENT_INVALID")
        if self.hi.shape != self.lo.shape:
            raise ValueError("AFFINE_OUTPUT_COMPONENT_SHAPE")

    def __array__(self, *args, **kwargs):
        raise TypeError("EXACT_AFFINE_OUTPUT_REQUIRES_BOTH_COMPONENTS")

    def map(self, action):
        return SplitVector(action(self.hi), action(self.lo))

    def __getitem__(self, key):
        return SplitVector(self.hi[key], self.lo[key])

    def physical_values(self):
        """Combine AFTER physical field evaluation, not before FE/port action."""
        return self.hi.astype(np.clongdouble) + self.lo.astype(np.clongdouble)

    def lossy_projection(self):
        return self.hi + self.lo, "LOSSY_SINGLE_COMPLEX128_PROJECTION"


def affine_state(packet, c, alpha):
    total = two_sum(c, packet.a["background"])
    atotal = two_sum(alpha, packet.a["background_alpha"])
    return dict(
        schema=np.asarray("exact_affine_FE_hi_lo.v1"),
        c_scattered=c,
        background=packet.a["background"],
        total_hi=total.hi,
        total_lo=total.lo,
        alpha_scattered=alpha,
        background_alpha=packet.a["background_alpha"],
        alpha_total_hi=atotal.hi,
        alpha_total_lo=atotal.lo,
        masters=packet.a["masters"],
    )


def total_field(state):
    if str(state["schema"]) != "exact_affine_FE_hi_lo.v1":
        raise ValueError("AFFINE_OUTPUT_SCHEMA")
    return SplitVector(state["total_hi"], state["total_lo"])


def split_equation(packet, state):
    """Full uncondensed equations use both actual output components."""
    from src.solvers.accurate_ports import recover_ports_components

    c, alpha = state["c_scattered"], state["alpha_scattered"]
    total = total_field(state)
    at = SplitVector(state["alpha_total_hi"], state["alpha_total_lo"])
    body = packet.volume(c) + packet.B(alpha) - packet.a["g"]
    port = -packet.D(c) + packet.a["H"] * alpha - packet.a["gp"]
    # Linear maps act separately; accumulate their physical outputs with guard
    # digits. Port recovery itself uses exact products, not extended precision.
    vb = total.map(packet.volume).physical_values()
    ba = at.map(packet.B).physical_values()
    da = total.map(packet.D).physical_values()
    ha = at.map(lambda x: packet.a["H"] * x).physical_values()

    def norm(x):
        return float(np.sqrt(np.sum(abs(x) ** 2, dtype=np.longdouble)))

    tb, tp = vb + ba - packet.a["total_g"], -da + ha
    expected, _ = recover_ports_components(
        packet.a, (total.hi, total.lo), gp=np.zeros_like(packet.a["gp"])
    )
    return dict(
        native_relative=norm(packet.apply(c) - packet.f) / packet.bnorm,
        augmented_relative=norm(np.r_[body, port])
        / norm(np.r_[packet.a["g"], packet.a["gp"]]),
        original_total_augmented_relative=norm(np.r_[tb, tp])
        / norm(packet.a["total_g"]),
        total_origin_recovery=norm(at.physical_values() - expected)
        / max(norm(expected), 1e-12),
        both_total_components_consumed=True,
        actual_output_used=True,
    )
