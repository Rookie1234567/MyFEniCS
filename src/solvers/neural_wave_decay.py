"""Explicit real oscillation/decay parameters for opt-in wave neurons."""

import numpy as np


def real_waves(value, name):
    a = np.asarray(value)
    if np.iscomplexobj(a):
        raise ValueError(f"EXPLICIT_REAL_{name}_REQUIRED_NO_SILENT_COMPLEX_CAST")
    a = np.asarray(a, dtype=np.float64).reshape(-1, 3)
    if not np.isfinite(a).all():
        raise ValueError(f"NONFINITE_{name}")
    return a


def decay_phase(displacement, window, q, kappa, base_q=None, base_kappa=None):
    """No exponent clipping; strictly zero window samples contribute zero."""
    q, kappa = real_waves(q, "Q"), real_waves(kappa, "KAPPA")
    if q.shape != kappa.shape:
        raise ValueError("OSCILLATION_DECAY_WIDTH_MISMATCH")
    selected = np.asarray(window) != 0
    d = displacement[selected]
    exponent = d @ (1j * q - kappa).T
    if np.max(np.abs(exponent.real), initial=0) > 8 + 1e-12:
        raise ValueError("DECAY_EXPONENT_BOUND_EXCEEDED_NO_CLIP")
    phase = np.zeros((len(displacement), len(q)), np.complex128)
    if base_q is None:
        phase[selected] = window[selected, None] * np.exp(exponent)
    else:
        bq = real_waves(base_q, "BASE_Q")
        bk = real_waves(base_kappa, "BASE_KAPPA")
        if q.shape != bq.shape or kappa.shape != bk.shape:
            raise ValueError("FIXED_DECAY_WIDTH_REQUIRED")
        base = d @ (1j * bq - bk).T
        if np.max(np.abs(base.real), initial=0) > 8 + 1e-12:
            raise ValueError("BASE_DECAY_EXPONENT_BOUND_EXCEEDED")
        phase[selected] = (
            window[selected, None]
            * np.exp(base)
            * np.expm1(d @ (1j * (q - bq) - (kappa - bk)).T)
        )
    return phase


def support_distances(patch, moments):
    lo, hi = moments.boxes
    lo, hi = lo.min(0), hi.max(0)
    center = np.asarray(patch.center)
    if patch.kind != "global":
        lo = np.maximum(lo, center - np.asarray(patch.radius))
        hi = np.minimum(hi, center + np.asarray(patch.radius))
    distance = np.maximum(abs(lo - center), abs(hi - center))
    if np.any(lo >= hi) or not np.isfinite(distance).all() or np.any(distance <= 0):
        raise ValueError("EMPTY_OR_DEGENERATE_DECAY_SUPPORT")
    return distance


def block_parameters(block):
    q = real_waves(block["wave_q"], "Q")
    k = real_waves(block.get("decay_kappa", np.zeros_like(q)), "KAPPA")
    return np.c_[q, k]


def coordinate_contract(block, moments, k0):
    radius = support_distances(block["patch"], moments)
    shape = block_parameters(block).shape
    scale = np.broadcast_to(np.r_[np.full(3, k0), 1 / radius], shape).copy()
    bounds = [
        (-4.0, 4.0) if j % 6 < 3 else (-8 / 3, 8 / 3) for j in range(np.prod(shape))
    ]
    return scale, bounds, radius


def physical_decay_seeds(block, moments, k0, beta):
    """Only known-material seeds, equal for both routes; never a label."""
    z = block_parameters(block)
    scale, bounds, radius = coordinate_contract(block, moments, k0)
    seeds, receipt = [], []
    for sign in (1, -1):
        kappa = np.zeros_like(z[:, :3])
        kappa[:, 2] = sign * float(beta.imag)
        raw_eta = kappa * radius
        eta = np.clip(raw_eta, -8 / 3, 8 / 3)
        trial = np.c_[z[:, :3], eta / radius]
        seeds.append(trial)
        receipt.append(
            dict(
                sign=sign,
                raw_eta=raw_eta.tolist(),
                projected_eta=eta.tolist(),
                projected=bool(np.any(eta != raw_eta)),
                R=radius.tolist(),
                q_real=trial[:, :3].tolist(),
                decay_kappa=trial[:, 3:].tolist(),
            )
        )
    return seeds, receipt


class ComplexActivityMoments:
    """Packed real six-vectors only inside LS; persisted q/kappa stay separate."""

    def __init__(self, packet, batch=8):
        from src.solvers.neural_wave_moments import WaveMoments

        self.kernel = WaveMoments(packet, batch)
        self.counts, self.seconds, self.boxes = (
            self.kernel.counts,
            self.kernel.seconds,
            self.kernel.boxes,
        )

    @staticmethod
    def split(z):
        z = np.asarray(z)
        if np.iscomplexobj(z) or z.ndim != 2 or z.shape[1] != 6:
            raise ValueError("PACKED_REAL_Q_KAPPA_REQUIRED")
        return real_waves(z[:, :3], "Q"), real_waves(z[:, 3:], "KAPPA")

    def columns(self, patch, z):
        q, k = self.split(z)
        return self.kernel.columns(patch, q, decay_kappa=k)

    def delta_columns(self, patch, z, base):
        q, k = self.split(z)
        bq, bk = self.split(base)
        return self.kernel.delta_columns(patch, q, bq, decay_kappa=k, base_kappa=bk)

    def vjp(self, patch, z, amplitude, cotangent):
        q, k = self.split(z)
        gq, gk, gp = self.kernel.vjp_decay(patch, q, k, amplitude, cotangent)
        return np.c_[gq, gk], gp


def normalized_complex_gradients(action, moments, space, blocks, k0):
    cotangent = -action.apply(space.r, adjoint=True) / action.bnorm**2
    scores = []
    for block in blocks:
        amplitude = block["amplitude_map"] @ space.a[block["start"] : block["stop"]]
        g, _ = moments.vjp(
            block["patch"], block_parameters(block), amplitude, cotangent
        )
        scale, _, _ = coordinate_contract(block, moments, k0)
        scores.append(float(np.linalg.norm(g * scale) / np.sqrt(max(1, g.size))))
    return scores
