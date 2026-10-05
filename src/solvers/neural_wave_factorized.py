"""Tensor contraction of complete neural moments, not an FE solver.

All polynomial-density coefficients are retained. Phase and Piola use the
original full Jacobian. Only the window's Cartesian cell coordinates are
canonicalized, with an explicit geometric bound and independent 1e-10 pairing.
Accepted fields are still formed by the original full point-value map.
"""

from itertools import product
from time import perf_counter

import numpy as np

from src.solvers.neural_wave_moments import WaveMoments


class FactorizedWaveMoments:
    def __init__(self, packet, batch=8, degree=3):
        self.a, self.batch = packet, batch
        if batch not in (1, 8):
            raise ValueError("only qualified cell batches")
        self.size = int(packet["active_rows"])
        self.rows = packet["owner_rows"]
        self.counts = dict(forward=0, vjp=0, cells=0)
        self.seconds = dict(forward=0.0, vjp=0.0, cache_build=0.0)
        self.cell_cache = {}
        points = packet["reference_points"]
        codes = np.where(points == 0.0, 0, np.where(points == 1.0, 1, -1))
        self.entities = []
        interpolation = packet["interpolation"]
        n = len(points)
        start = perf_counter()
        maximum_pair = 0.0
        for code in np.unique(codes, axis=0):
            select = np.flatnonzero(np.all(codes == code, axis=1))
            axes = np.flatnonzero(code == -1)
            if not len(axes):
                raise ValueError("N1curl vertex point unsupported")
            nodes = np.unique(points[select, axes[0]])
            canonical, weights = np.polynomial.legendre.leggauss(len(nodes))
            canonical, weights = (canonical + 1) / 2, weights / 2
            if np.max(abs(nodes - canonical)) > 1e-12:
                raise ValueError("complete moment rule is not tensor Gauss")
            powers = np.array(list(product(range(degree + 1), repeat=len(axes))))
            V = np.ones((len(select), len(powers)))
            W = np.ones(len(select))
            for j, axis in enumerate(axes):
                table = np.polynomial.legendre.legvander(
                    2 * points[select, axis] - 1, degree
                )
                V *= table[:, powers[:, j]]
                positions = np.argmin(
                    abs(points[select, axis, None] - nodes[None]), axis=1
                )
                W *= weights[positions]
            if len(select) != len(nodes) ** len(axes):
                raise ValueError("incomplete full moment tensor grid")
            blocks = np.stack(
                [interpolation[:, k * n + select] for k in range(3)], axis=1
            )
            rows = np.flatnonzero(np.any(blocks != 0, axis=(1, 2)))
            blocks = blocks[rows]
            coefficient = (blocks @ V) * np.prod(2 * powers + 1, axis=1)[None, None, :]
            restored = (coefficient @ V.T) * W[None, None, :]
            pair = float(
                np.linalg.norm(restored - blocks) / max(np.linalg.norm(blocks), 1e-30)
            )
            maximum_pair = max(maximum_pair, pair)
            if pair > 1e-10:
                raise ValueError("complete polynomial density compression failed")
            self.entities.append(
                dict(
                    code=code,
                    axes=axes,
                    powers=powers,
                    nodes=nodes,
                    weights=weights,
                    rows=rows,
                    coefficient=coefficient,
                )
            )
        self.density_pair_relative = maximum_pair
        self.geometry = []
        defects = []
        corners = np.array(list(product((0.0, 1.0), repeat=3)))
        for origin, jac in zip(packet["origins"], packet["jacobians"], strict=True):
            major = np.argmax(abs(jac), axis=1)
            if len(set(major)) != 3:
                raise ValueError("factorized window needs Cartesian geometry")
            canonical = np.zeros((3, 3))
            canonical[np.arange(3), major] = jac[np.arange(3), major]
            defect = float(np.max(abs((jac - canonical) @ corners.T)))
            if defect > 1e-12:
                raise ValueError("Cartesian geometry proof failed; use full mapping")
            vertices = origin + corners @ jac.T
            self.geometry.append((major, vertices.min(0), vertices.max(0)))
            defects.append(defect)
        self.maximum_window_coordinate_defect_nm = max(defects)
        self.seconds["cache_build"] = perf_counter() - start

    def cells(self, patch):
        if patch not in self.cell_cache:
            center, radius = np.array(patch.center), np.array(patch.radius)
            self.cell_cache[patch] = np.array(
                [
                    c
                    for c, (_, lo, hi) in enumerate(self.geometry)
                    if np.all(
                        (hi > center - radius + 1e-12) & (lo < center + radius - 1e-12)
                    )
                ],
                dtype=int,
            )
        return self.cell_cache[patch]

    def local(self, cell, patch, q, derivative=False):
        jac, origin = self.a["jacobians"][cell], self.a["origins"][cell]
        major = self.geometry[cell][0]
        physical_of_ref = np.argsort(major)
        kappa = q @ jac
        displacement = origin - np.array(patch.center)
        phase_origin = np.exp(1j * q @ displacement)
        local = np.zeros((len(self.rows[cell]), len(q), 3), complex)
        deriv = np.zeros(local.shape + (3,), complex) if derivative else None
        for entity in self.entities:
            factors, first_moments = [], []
            code, axes, powers = entity["code"], entity["axes"], entity["powers"]
            for axis in range(3):
                physical = physical_of_ref[axis]
                if code[axis] != -1:
                    coordinate = float(code[axis])
                    t = (
                        displacement[physical] + jac[physical, axis] * coordinate
                    ) / patch.radius[physical]
                    window = max(1 - t * t, 0.0) ** 2
                    value = window * np.exp(1j * kappa[:, axis] * coordinate)
                    factors.append(
                        np.broadcast_to(value[:, None], (len(q), len(powers)))
                    )
                    first_moments.append(factors[-1] * coordinate)
                else:
                    nodes = entity["nodes"]
                    table = np.polynomial.legendre.legvander(
                        2 * nodes - 1, powers.max()
                    )
                    t = (
                        displacement[physical] + jac[physical, axis] * nodes
                    ) / patch.radius[physical]
                    window = np.maximum(1 - t * t, 0.0) ** 2
                    phase = np.exp(1j * kappa[:, axis, None] * nodes[None])
                    weighted = phase * (window * entity["weights"])[None]
                    integrals = weighted @ table
                    powers_axis = powers[:, int(np.flatnonzero(axes == axis)[0])]
                    factors.append(integrals[:, powers_axis])
                    first_moments.append(
                        ((weighted * nodes[None]) @ table)[:, powers_axis]
                    )
            product_all = factors[0] * factors[1] * factors[2] * phase_origin[:, None]
            value = np.einsum("dcp,jp->djc", entity["coefficient"], product_all)
            local[entity["rows"]] += np.einsum("djc,kc->djk", value, jac)
            if derivative:
                for physical in range(3):
                    dproduct = displacement[physical] * product_all
                    for axis in range(3):
                        others = phase_origin[:, None] * first_moments[axis]
                        for other in range(3):
                            if other != axis:
                                others = others * factors[other]
                        dproduct += jac[physical, axis] * others
                    dvalue = np.einsum(
                        "dcp,jp->djc", entity["coefficient"], 1j * dproduct
                    )
                    deriv[entity["rows"], :, :, physical] += np.einsum(
                        "djc,kc->djk", dvalue, jac
                    )
        transform = self.a["transforms"][self.a["orientation_ids"][cell]]
        local = (transform @ local.reshape(len(local), -1)).reshape(local.shape)
        if derivative:
            deriv = (transform @ deriv.reshape(len(deriv), -1)).reshape(deriv.shape)
        return local, deriv

    def columns(self, patch, q):
        start = perf_counter()
        q = np.asarray(q, dtype=float).reshape(-1, 3)
        c = np.zeros((self.size, len(q), 3), complex)
        for cell in self.cells(patch):
            values, _ = self.local(cell, patch, q)
            rows = self.rows[cell]
            keep = rows >= 0
            c[rows[keep]] = values[keep]
            self.counts["cells"] += 1
        self.counts["forward"] += 1
        self.seconds["forward"] += perf_counter() - start
        return c.reshape(self.size, -1)

    def forward(self, patch, q, p):
        return self.columns(patch, q) @ np.asarray(p).ravel()

    def vjp(self, patch, q, p, g):
        start = perf_counter()
        q, p = np.asarray(q).reshape(-1, 3), np.asarray(p).reshape(-1, 3)
        gq, gp = np.zeros_like(q), np.zeros_like(p)
        for cell in self.cells(patch):
            local, derivative = self.local(cell, patch, q, True)
            rows = self.rows[cell]
            keep = rows >= 0
            cot = g[rows[keep]]
            gp += np.einsum("djk,d->jk", local[keep].conj(), cot)
            gq += np.real(np.einsum("d,djka,jk->ja", cot.conj(), derivative[keep], p))
        self.counts["vjp"] += 1
        self.seconds["vjp"] += perf_counter() - start
        return gq, gp


def compare_factorized(packet, patches, seed=4213003):
    """No labels; independently pair every FE family and complete VJP."""
    original, fast = WaveMoments(packet), FactorizedWaveMoments(packet)
    rng = np.random.default_rng(seed)
    records = []
    for patch in patches:
        q = np.array([[4.0, -4.0, 4.0], [1.13, 0.42, -0.81]]) * 2 * np.pi / 5
        p = rng.normal(size=(2, 3)) + 1j * rng.normal(size=(2, 3))
        reference, new = original.forward(patch, q, p), fast.forward(patch, q, p)
        g = rng.normal(size=len(new)) + 1j * rng.normal(size=len(new))
        expected = original.vjp(patch, q, p, g)
        actual = fast.vjp(patch, q, p, g)
        family = {}
        for name in ("edge", "face", "interior"):
            rows = packet["owner_rows"][:, packet[name + "_positions"]].ravel()
            rows = rows[rows >= 0]
            family[name] = float(
                np.linalg.norm(new[rows] - reference[rows])
                / np.linalg.norm(reference[rows])
            )
        records.append(
            dict(
                forward_relative=float(
                    np.linalg.norm(new - reference) / np.linalg.norm(reference)
                ),
                real_q_VJP_relative=float(
                    np.linalg.norm(actual[0] - expected[0])
                    / np.linalg.norm(expected[0])
                ),
                complex_p_VJP_relative=float(
                    np.linalg.norm(actual[1] - expected[1])
                    / np.linalg.norm(expected[1])
                ),
                families=family,
            )
        )
    return dict(
        passed=all(
            max(
                row["forward_relative"],
                row["real_q_VJP_relative"],
                row["complex_p_VJP_relative"],
                *row["families"].values(),
            )
            <= 1e-10
            for row in records
        ),
        witnesses=records,
        density_pair_relative=fast.density_pair_relative,
        maximum_window_coordinate_defect_nm=fast.maximum_window_coordinate_defect_nm,
        original_seconds=original.seconds,
        factorized_seconds=fast.seconds,
        reference_loaded=False,
    )
