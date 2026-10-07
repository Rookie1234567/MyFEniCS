"""Local complex-exponential neurons through all original H(curl) moments.

Numeric, detached cell blocks only. The original owner, Piola and orientation
maps are applied once; slave expansion remains the native packet's job.
"""

from dataclasses import dataclass
from time import perf_counter

import numpy as np
from scipy import sparse


@dataclass(frozen=True)
class Patch:
    center: tuple
    radius: tuple
    level: int = 0
    kind: str = "local"

    def __post_init__(self):
        if self.kind not in ("local", "global"):
            raise ValueError("UNKNOWN_WAVE_SUPPORT_KIND")

    def window(self, points):
        if self.kind == "global":
            return np.ones(np.asarray(points).shape[:-1], dtype=np.float64)
        t = (points - np.asarray(self.center)) / np.asarray(self.radius)
        # C1 at the support boundary; breaks coincide with cell boundaries.
        return np.prod(np.maximum(1.0 - t * t, 0.0) ** 2, axis=-1)


class WaveMoments:
    """Exact-zero sparse contraction of a qualified full moment packet."""

    def __init__(self, packet, batch=8):
        if batch not in (1, 8):
            raise ValueError("qualified batches are 1 and 8")
        self.a, self.batch = packet, batch
        self.size = int(packet["active_rows"])
        self.rows = packet["owner_rows"]
        self.points = np.asarray(packet["reference_points"])
        interpolation = packet["interpolation"]
        n = len(self.points)
        if interpolation.shape[1] != 3 * n:
            raise ValueError("complete three-component moment layout required")
        # No magnitude pruning. Every exactly nonzero full moment is retained.
        self.maps = []
        for transform in packet["transforms"]:
            oriented = transform @ interpolation
            self.maps.append(
                tuple(
                    sparse.csr_matrix(oriented[:, j * n : (j + 1) * n])
                    for j in range(3)
                )
            )
        self.counts = dict(forward=0, vjp=0, cells=0)
        self.seconds = dict(forward=0.0, vjp=0.0)
        corners = np.asarray(
            [[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)]
        )
        vertices = packet["origins"][:, None, :] + np.einsum(
            "pj,cij->cpi", corners, packet["jacobians"]
        )
        self.boxes = (vertices.min(1), vertices.max(1))
        self.cell_cache = {}

    def cells(self, patch):
        if patch in self.cell_cache:
            return self.cell_cache[patch]
        lo, hi = self.boxes
        if patch.kind == "global":
            result = np.arange(len(lo))
            self.cell_cache[patch] = result
            return result
        center, radius = np.asarray(patch.center), np.asarray(patch.radius)
        result = np.flatnonzero(
            np.all(
                (hi > center - radius + 1e-12) & (lo < center + radius - 1e-12), axis=1
            )
        )
        self.cell_cache[patch] = result
        return result

    def blocks(self, patch):
        cells = self.cells(patch)
        for first in range(0, len(cells), self.batch):
            section = cells[first : first + self.batch]
            for cell in section:
                jac = self.a["jacobians"][cell]
                x = self.a["origins"][cell] + self.points @ jac.T
                displacement = x - np.asarray(patch.center)
                yield cell, jac, displacement, patch.window(x)

    def columns(self, patch, q):
        """Three amplitude columns per neuron; not a parameter Jacobian."""
        start = perf_counter()
        q = np.asarray(q, dtype=np.float64).reshape(-1, 3)
        result = np.zeros((self.size, len(q), 3), dtype=np.complex128)
        for cell, jac, displacement, window in self.blocks(patch):
            phase = window[:, None] * np.exp(1j * displacement @ q.T)
            maps = self.maps[self.a["orientation_ids"][cell]]
            pulled = np.stack([matrix @ phase for matrix in maps], axis=-1)
            physical = np.einsum("dja,ka->djk", pulled, jac)
            rows = self.rows[cell]
            selected = rows >= 0
            result[rows[selected]] = physical[selected]
            self.counts["cells"] += 1
        self.counts["forward"] += 1
        self.seconds["forward"] += perf_counter() - start
        return result.reshape(self.size, -1)

    def forward(self, patch, q, amplitude):
        p = np.asarray(amplitude, dtype=np.complex128).reshape(-1, 3)
        return self.columns(patch, q) @ p.ravel()

    def vjp(self, patch, q, amplitude, cotangent):
        """Real convention dL=Re(g^H dc); no mesh-wide AD graph or J."""
        start = perf_counter()
        q = np.asarray(q, dtype=np.float64).reshape(-1, 3)
        p = np.asarray(amplitude, dtype=np.complex128).reshape(-1, 3)
        g = np.asarray(cotangent, dtype=np.complex128)
        gp = np.zeros_like(p)
        gq = np.zeros_like(q)
        for cell, jac, displacement, window in self.blocks(patch):
            rows = self.rows[cell]
            local = np.zeros(len(rows), dtype=np.complex128)
            selected = rows >= 0
            local[selected] = g[rows[selected]]
            maps = self.maps[self.a["orientation_ids"][cell]]
            # Original numeric interpolation matrices are real.
            pulled = np.stack([matrix.T @ local for matrix in maps], axis=-1)
            field_g = pulled @ jac.T
            phase = window[:, None] * np.exp(1j * displacement @ q.T)
            gp += phase.conj().T @ field_g
            scalar = field_g.conj() @ p.T
            for axis in range(3):
                gq[:, axis] += np.real(
                    np.sum(scalar * phase * (1j * displacement[:, axis, None]), axis=0)
                )
        self.counts["vjp"] += 1
        self.seconds["vjp"] += perf_counter() - start
        return gq, gp


def score_and_cotangent(z, residual):
    """Direction score without an epsilon in the denominator."""
    denominator = float(np.vdot(z, z).real)
    if not np.isfinite(denominator) or denominator <= 0:
        raise ValueError("DEGENERATE_NEW_DIRECTION")
    dot = np.vdot(z, residual)
    score = float(abs(dot) ** 2 / denominator)
    gradient = 2 * (residual * dot.conjugate() / denominator - z * score / denominator)
    return score, gradient


def pack(q, p):
    return np.r_[
        np.asarray(q).ravel(), np.asarray(p).real.ravel(), np.asarray(p).imag.ravel()
    ]


def unpack(theta):
    if len(theta) % 9:
        raise ValueError("nine real weights per complex vector neuron")
    r = len(theta) // 9
    return (
        theta[: 3 * r].reshape(r, 3),
        (theta[3 * r : 6 * r] + 1j * theta[6 * r :]).reshape(r, 3),
    )
