"""Exact-q tensor contraction of a native H(curl) boundary polynomial.

This opt-in decoder owns only the two boundary surfaces, not volume row IDs.
It retains native basis functions through a bounded local polynomial change
of coordinates. No modal truncation, threshold clipping or FFT is used.
"""

from time import perf_counter

import numpy as np
from numpy.polynomial.legendre import legvander


def zvalue(x):
    return complex(x["real"], x["imag"]) if isinstance(x, dict) else complex(x)


class FacetPolynomial:
    def __init__(self, element):
        import basix

        self.element, self.p = element, element.degree
        self.q1, self.w1 = np.polynomial.legendre.leggauss(self.p + 1)
        self.q1 = (self.q1 + 1) / 2
        self.w1 /= 2
        v = legvander(2 * self.q1 - 1, self.p)
        x, y = np.meshgrid(self.q1, self.q1, indexing="ij")
        self.coefficients = {}
        self.active = {}
        topology = basix.cell.topology(basix.CellType.hexahedron)
        for side, zz, face in [("bottom", 0.0, 0), ("top", 1.0, 5)]:
            points = np.column_stack((x.ravel(), y.ravel(), np.full(x.size, zz)))
            tab = element.tabulate(0, points)[0][:, :, :2].reshape(
                self.p + 1, self.p + 1, element.dim, 2
            )
            # Two bounded polynomial-coordinate solves, not a global inverse.
            first = np.linalg.solve(v, tab.reshape(self.p + 1, -1)).reshape(tab.shape)
            coeff = (
                np.linalg.solve(v, first.swapaxes(0, 1).reshape(self.p + 1, -1))
                .reshape(tab.shape)
                .swapaxes(0, 1)
            )
            self.coefficients[side] = np.ascontiguousarray(coeff)
            vertices = set(topology[2][face])
            edges = [i for i, edge in enumerate(topology[1]) if set(edge) <= vertices]
            self.active[side] = np.array(
                [j for edge in edges for j in element.entity_dofs[1][edge]]
                + element.entity_dofs[2][face],
                dtype=np.int64,
            )
        self.nbytes = sum(v.nbytes for v in self.coefficients.values())
        for a in (*self.coefficients.values(), *self.active.values()):
            a.flags.writeable = False

    def integral(self, side, k, J, origin, q):
        import basix

        if np.linalg.norm(J - np.diag(np.diag(J))) > 1e-12 or np.any(np.diag(J) <= 0):
            raise ValueError("directional kernel requires axis-aligned affine face")
        rule, w = basix.make_quadrature(basix.CellType.interval, q)
        r = rule[:, 0]
        v = legvander(2 * r - 1, self.p)
        ix = (w * np.exp(1j * k[0] * J[0, 0] * r)) @ v
        iy = (w * np.exp(1j * k[1] * J[1, 1] * r)) @ v
        local = np.einsum(
            "a,b,abjc->jc", ix, iy, self.coefficients[side], optimize=True
        )
        local *= np.array([J[1, 1], J[0, 0]])
        pos = origin.copy()
        if side == "top":
            pos[2] += J[2, 2]
        local *= np.exp(1j * np.dot(k, pos))
        return np.ascontiguousarray(local, np.complex128)


class BoundaryLayout:
    """Canonical complete entities of the periodic 2D boundary trace only."""

    def __init__(self, x, y, polynomial, phases):
        import basix

        self.x, self.y = np.asarray(x), np.asarray(y)
        self.nx, self.ny, self.p = len(x) - 1, len(y) - 1, polynomial.p
        self.polynomial = polynomial
        self.phases = tuple(map(complex, phases))
        self.side_rows = 2 * self.p**2 * self.nx * self.ny
        self.rows = 2 * self.side_rows
        self.maps, self.weights = {}, {}
        ref = basix.cell.geometry(basix.CellType.hexahedron)
        topo = basix.cell.topology(basix.CellType.hexahedron)
        for si, side in enumerate(("bottom", "top")):
            active = polynomial.active[side]
            lookup = {int(d): j for j, d in enumerate(active)}
            maps = np.empty((self.nx, self.ny, len(active)), np.int64)
            phase = np.ones_like(maps, dtype=np.complex128)
            face = 0 if side == "bottom" else 5
            faceids = polynomial.element.entity_dofs[2][face]
            for i in range(self.nx):
                for j in range(self.ny):
                    for edge, vs in enumerate(topo[1]):
                        ids = polynomial.element.entity_dofs[1][edge]
                        if not ids or ids[0] not in lookup:
                            continue
                        pts = ref[vs]
                        along_x = pts[0, 0] != pts[1, 0]
                        if along_x:
                            jj = j + int(pts[0, 1])
                            block = 0
                            entity = i * self.ny + (jj % self.ny)
                            ph = self.phases[1] if jj == self.ny else 1
                        else:
                            ii = i + int(pts[0, 0])
                            block = self.nx * self.ny * self.p
                            entity = (ii % self.nx) * self.ny + j
                            ph = self.phases[0] if ii == self.nx else 1
                        for l, d in enumerate(ids):
                            maps[i, j, lookup[d]] = (
                                si * self.side_rows + block + entity * self.p + l
                            )
                            phase[i, j, lookup[d]] = ph
                    offset = 2 * self.nx * self.ny * self.p + (i * self.ny + j) * len(
                        faceids
                    )
                    for l, d in enumerate(faceids):
                        maps[i, j, lookup[d]] = si * self.side_rows + offset + l
            self.maps[side], self.weights[side] = maps, phase
        self.nbytes = sum(
            a.nbytes for a in (*self.maps.values(), *self.weights.values())
        )
        for a in (*self.maps.values(), *self.weights.values()):
            a.flags.writeable = False
        inventory = np.concatenate([m.ravel() for m in self.maps.values()])
        if (
            len(np.unique(inventory)) != self.rows
            or inventory.min() != 0
            or inventory.max() != self.rows - 1
        ):
            raise ValueError("complete periodic entity row inventory")

    def field_coefficients(self, t, side):
        local = np.asarray(t)[self.maps[side]] * self.weights[side]
        coeff = self.polynomial.coefficients[side][
            :, :, self.polynomial.active[side], :
        ]
        result = np.einsum("ija,uvac->ijuvc", local, coeff, optimize=True)
        result[:, :, :, :, 0] *= np.diff(self.y)[None, :, None, None]
        result[:, :, :, :, 1] *= np.diff(self.x)[:, None, None, None]
        return result

    def scatter_coefficients(self, coeff, side):
        coeff = coeff.copy()
        coeff[:, :, :, :, 0] *= np.diff(self.y)[None, :, None, None]
        coeff[:, :, :, :, 1] *= np.diff(self.x)[:, None, None, None]
        pcoef = self.polynomial.coefficients[side][
            :, :, self.polynomial.active[side], :
        ]
        local = (
            np.einsum("ijuvc,uvac->ija", coeff, pcoef, optimize=True)
            * self.weights[side].conj()
        )
        out = np.zeros(self.rows, np.complex128)
        np.add.at(out, self.maps[side].ravel(), local.ravel())
        return out


class DirectionalBoundaryAction:
    def __init__(self, layout, modes, q):
        import basix

        self.layout, self.modes, self.q = layout, tuple(modes), q
        self.by_side = {
            s: [i for i, r in enumerate(modes) if r["side"] == s]
            for s in ("bottom", "top")
        }
        rule, w = basix.make_quadrature(basix.CellType.interval, q)
        v = legvander(2 * rule[:, 0] - 1, layout.p)
        self.tables = {}
        for side, indices in self.by_side.items():
            ax = sorted(
                {zvalue(modes[i]["k_vector"][0]) for i in indices},
                key=lambda z: (z.real, z.imag),
            )
            ay = sorted(
                {zvalue(modes[i]["k_vector"][1]) for i in indices},
                key=lambda z: (z.real, z.imag),
            )
            mats = []
            for coords, ks in [(layout.x, ax), (layout.y, ay)]:
                pts = coords[:-1, None] + np.diff(coords)[:, None] * rule[:, 0]
                # Canonical tensor row layout (cell, Legendre degree).
                mat = np.einsum(
                    "kij,j,jd->kid",
                    np.exp(-1j * np.conj(np.array(ks))[:, None, None] * pts[None]),
                    w,
                    v,
                    optimize=True,
                )
                # A frozen ordered prefix can contain modes from one side
                # only. Keep the other side's empty table well shaped.
                mats.append(mat.reshape(len(ks), (len(coords) - 1) * (layout.p + 1)))
            lookupx = {k: i for i, k in enumerate(ax)}
            lookupy = {k: i for i, k in enumerate(ay)}
            ix = np.array([lookupx[zvalue(modes[i]["k_vector"][0])] for i in indices])
            iy = np.array([lookupy[zvalue(modes[i]["k_vector"][1])] for i in indices])
            zphase = np.array(
                [
                    np.exp(
                        -1j
                        * np.conj(zvalue(modes[i]["k_vector"][2]))
                        * modes[i]["reference_plane_nm"]
                    )
                    for i in indices
                ]
            )
            self.tables[side] = (mats[0], mats[1], ix, iy, zphase)
        self.cache_bytes = layout.polynomial.nbytes + sum(
            v.nbytes for vs in self.tables.values() for v in vs
        )
        if self.cache_bytes > 64 * 2**20:
            raise MemoryError("all numeric moment caches 64MiB")
        self.e = np.array([[zvalue(v) for v in r["e_vector"][:2]] for r in modes])
        self.traction = np.array(
            [[zvalue(v) for v in r["traction_vector"][:2]] for r in modes]
        )
        self.H = np.array([r["projection_denominator"] for r in modes])
        self.cache_bytes += self.e.nbytes + self.traction.nbytes + self.H.nbytes
        if self.cache_bytes > 64 * 2**20:
            raise MemoryError("all moments/polarizations/H cache 64MiB")
        for values in self.tables.values():
            for a in values:
                a.flags.writeable = False
        for a in (self.e, self.traction, self.H):
            a.flags.writeable = False
        self.stats = {
            "project_calls": 0,
            "scatter_calls": 0,
            "project_seconds": 0.0,
            "scatter_seconds": 0.0,
        }

    def project_components(self, t):
        began = perf_counter()
        out = np.zeros((len(self.modes), 2), np.complex128)
        for side, ids in self.by_side.items():
            if not ids:
                continue
            fx, fy, ix, iy, phase = self.tables[side]
            coef = self.layout.field_coefficients(t, side)
            for c in (0, 1):
                grid = (
                    coef[:, :, :, :, c]
                    .transpose(0, 2, 1, 3)
                    .reshape(fx.shape[1], fy.shape[1])
                )
                spectral = (fx @ grid) @ fy.T
                for start in range(0, len(ids), 64):
                    stop = min(start + 64, len(ids))
                    selected = ids[start:stop]
                    out[selected, c] = (
                        spectral[ix[start:stop], iy[start:stop]] * phase[start:stop]
                    )
        self.stats["project_calls"] += 1
        self.stats["project_seconds"] += perf_counter() - began
        return out

    def scatter_components(self, a):
        began = perf_counter()
        out = np.zeros(self.layout.rows, np.complex128)
        for side, ids in self.by_side.items():
            if not ids:
                continue
            fx, fy, ix, iy, phase = self.tables[side]
            coeff = np.zeros(
                (
                    self.layout.nx,
                    self.layout.ny,
                    self.layout.p + 1,
                    self.layout.p + 1,
                    2,
                ),
                np.complex128,
            )
            for c in (0, 1):
                spectral = np.zeros((len(fx), len(fy)), np.complex128)
                for start in range(0, len(ids), 64):
                    stop = min(start + 64, len(ids))
                    np.add.at(
                        spectral,
                        (ix[start:stop], iy[start:stop]),
                        np.asarray(a)[ids[start:stop], c] * phase[start:stop].conj(),
                    )
                grid = (fx.conj().T @ spectral) @ fy.conj()
                coeff[:, :, :, :, c] = grid.reshape(
                    self.layout.nx, self.layout.p + 1, self.layout.ny, self.layout.p + 1
                ).transpose(0, 2, 1, 3)
            out += self.layout.scatter_coefficients(coeff, side)
        self.stats["scatter_calls"] += 1
        self.stats["scatter_seconds"] += perf_counter() - began
        return out

    def recover(self, t):
        return np.sum(self.e.conj() * self.project_components(t), axis=1) / self.H

    def modal_rhs(self, alpha):
        return self.scatter_components(-self.traction * np.asarray(alpha)[:, None])

    def apply(self, t, *, adjoint=False):
        components = self.project_components(t)
        if adjoint:
            a = np.sum(-self.traction.conj() * components, axis=1) / self.H
            return self.scatter_components(self.e * a[:, None])
        a = np.sum(self.e.conj() * components, axis=1) / self.H
        return self.modal_rhs(a)
