"""Independent g*psi basis integration; no producer local tensors are read.

Physical derivatives differentiate g*psi componentwise, independently of the
UFL curl_kappa form. Surface blocks retain physical wavevector/polarization.
"""

import numpy as np
from scipy import sparse


def affine_basis(model, cell, points):
    import basix

    space = model["space"]
    msh = space.mesh
    vertices = basix.cell.geometry(basix.CellType.hexahedron)
    X = np.column_stack((np.ones(8), vertices))
    coordinates = msh.geometry.x[msh.geometry.dofmap[cell]]
    fit = np.linalg.lstsq(X, coordinates, rcond=None)[0]
    J = fit[1:].T
    determinant = np.linalg.det(J)
    if determinant <= 0 or np.max(abs(X @ fit - coordinates)) > 1e-12:
        raise ValueError("AFFINE_GEOMETRY_NOT_QUALIFIED")
    invJ = np.linalg.inv(J)
    tab = space.element.basix_element.tabulate(1, points)
    E = np.einsum("qia,ab->qib", tab[0], invJ)
    derivatives = np.einsum("rqia,ab,rd->dqib", tab[1:4], invJ, invJ)
    msh.topology.create_entity_permutations()
    info = msh.topology.get_cell_permutation_info()[cell]
    T = np.eye(space.element.basix_element.dim).ravel()
    space.element.T_apply(
        T, np.asarray([info], np.uint32), space.element.basix_element.dim
    )
    T = T.reshape(space.element.basix_element.dim, -1)
    # Keep exact nonzeros of the orientation map; no amplitude truncation.
    transformation = sparse.csr_matrix(T)
    E = (
        (transformation @ E.transpose(1, 0, 2).reshape(T.shape[0], -1))
        .reshape(T.shape[0], len(points), 3)
        .transpose(1, 0, 2)
    )
    derivatives = np.stack(
        [
            (transformation @ d.transpose(1, 0, 2).reshape(T.shape[0], -1))
            .reshape(T.shape[0], len(points), 3)
            .transpose(1, 0, 2)
            for d in derivatives
        ]
    )
    physical_points = points @ J.T + fit[0]
    g = np.exp(1j * (physical_points @ model["kappa"]))
    # Direct product derivatives of the physical basis, not curl_kappa(u).
    physical_derivatives = g[None, :, None, None] * (
        derivatives + 1j * model["kappa"][:, None, None, None] * E[None]
    )
    C = np.stack(
        (
            physical_derivatives[1, :, :, 2] - physical_derivatives[2, :, :, 1],
            physical_derivatives[2, :, :, 0] - physical_derivatives[0, :, :, 2],
            physical_derivatives[0, :, :, 1] - physical_derivatives[1, :, :, 0],
        ),
        axis=2,
    )
    return g[:, None, None] * E, C, physical_points, determinant, J


class PhysicalVolumeAudit:
    def __init__(self, model, packet, q=15):
        import basix

        self.model, self.packet = model, packet
        points, w = basix.make_quadrature(basix.CellType.hexahedron, q)
        cfg, space = model["cfg"], model["space"]
        eps = {
            cfg.tags.air: cfg.eps_r,
            cfg.tags.substrate: cfg.substrate_index**2,
            cfg.tags.grating: cfg.grating_index**2,
        }
        infos = space.mesh.topology.get_cell_permutation_info()
        matrices, classes, cache = [], [], {}
        for cell, tag in enumerate(model["tags"]):
            coordinates = space.mesh.geometry.x[space.mesh.geometry.dofmap[cell]].copy()
            coordinates -= coordinates[0]
            key = (int(tag), np.round(coordinates, 13).tobytes(), int(infos[cell]))
            if key not in cache:
                E, C, _, det, _ = affine_basis(model, cell, points)
                K = det * (
                    np.einsum("qia,qja,q->ij", C.conj(), C, w, optimize=True) / cfg.mu_r
                    - cfg.k0**2
                    * eps[int(tag)]
                    * np.einsum("qia,qja,q->ij", E.conj(), E, w, optimize=True)
                )
                cache[key] = len(matrices)
                matrices.append(K)
            classes.append(cache[key])
        self.matrices, self.classes = np.asarray(matrices), np.asarray(classes)
        self.scope = dict(
            q=q,
            classes=len(cache),
            physical_product_derivative=True,
            producer_F_read=False,
            shared="Basix, geometry, orientation API, MPC input",
        )

    def volume(self, c):
        local = self.packet.expand(c)
        out = np.empty_like(local)
        for first in range(0, self.packet.nc, 8):
            sl = slice(first, min(first + 8, self.packet.nc))
            out[sl] = np.einsum(
                "cij,cj->ci", self.matrices[self.classes[sl]], local[sl]
            )
        return self.packet.pullback(out)

    def check(self):
        rng = np.random.default_rng(422001)
        samples = []
        for _ in range(3):
            c = rng.normal(size=self.packet.size) + 1j * rng.normal(
                size=self.packet.size
            )
            v, expected = self.volume(c), self.packet.volume(c)
            samples.append(
                float(np.linalg.norm(v - expected) / np.linalg.norm(expected))
            )
        return dict(relative=samples, passed=max(samples) <= 1e-10, scope=self.scope)


def surface_blocks(model, packet, q=15):
    import basix

    cfg = model["cfg"]
    points, weights = basix.make_quadrature(basix.CellType.quadrilateral, q)
    vertices, topology = (
        basix.cell.geometry(basix.CellType.hexahedron),
        basix.cell.topology(basix.CellType.hexahedron),
    )
    order = np.argsort(packet.a["erows"])
    if np.any(np.bincount(packet.a["erows"], minlength=packet.nc * packet.dim) != 1):
        raise ValueError("INDEPENDENT_SURFACE_REQUIRES_QUALIFIED_SINGLE_MASTER_MPC")
    ids = packet.a["eids"][order].reshape(packet.nc, packet.dim)
    phase = packet.a["evals"][order].reshape(packet.nc, packet.dim)
    br, bc, bv, dr, dc, dv = [], [], [], [], [], []
    for cell in range(packet.nc):
        coordinates = model["space"].mesh.geometry.x[
            model["space"].mesh.geometry.dofmap[cell]
        ]
        for face in topology[2]:
            vtx = vertices[face]
            physical_face = coordinates[face]
            side = None
            if np.max(abs(physical_face[:, 2] - cfg.physical_z_max)) < 1e-12:
                side = "top"
            if np.max(abs(physical_face[:, 2] - cfg.physical_z_min)) < 1e-12:
                side = "bottom"
            if side is None:
                continue
            axes = np.flatnonzero(np.ptp(vtx, axis=0) > 0.5)
            ref = np.tile(vtx.min(axis=0), (len(points), 1))
            ref[:, axes] = points
            E, _, physical, _, J = affine_basis(model, cell, ref)
            area = np.linalg.norm(np.cross(J[:, axes[0]], J[:, axes[1]]))
            ports = [
                i for i, m in enumerate(model["bundle"]["modes"]) if m.side == side
            ]
            modes = [model["bundle"]["modes"][i] for i in ports]
            k = np.asarray([m.k_vector for m in modes])
            e = np.asarray([m.e_vector for m in modes])
            normal = [0, 0, 1 if side == "top" else -1]
            traction = np.cross(1j * np.cross(k, e), normal)
            wave = np.exp(1j * (physical @ k.T))
            B = sum(
                E[:, :, j].conj().T
                @ (-area * weights[:, None] * wave * traction[None, :, j])
                for j in range(3)
            )
            # DtN projects the tangential trace, not the normal electric field.
            D = sum(
                (area * weights[:, None] * wave.conj() * e[None, :, j].conj()).T
                @ E[:, :, j]
                for j in range(2)
            )
            B *= phase[cell, :, None].conj()
            D *= phase[cell, None, :]
            nonzero_b = np.nonzero(B)
            nonzero_d = np.nonzero(D)
            br.extend(ids[cell, nonzero_b[0]])
            bc.extend(np.asarray(ports)[nonzero_b[1]])
            bv.extend(B[nonzero_b])
            dr.extend(np.asarray(ports)[nonzero_d[0]])
            dc.extend(ids[cell, nonzero_d[1]])
            dv.extend(D[nonzero_d])
    B = sparse.coo_matrix((bv, (br, bc)), shape=(packet.size, packet.np)).tocsr()
    D = sparse.coo_matrix((dv, (dr, dc)), shape=(packet.np, packet.size)).tocsr()
    H = np.asarray(
        [
            (cfg.period_x * cfg.period_y)
            * np.vdot(m.e_vector[:2], m.e_vector[:2]).real
            * abs(
                np.exp(
                    1j
                    * m.k_vector[2]
                    * (cfg.physical_z_max if m.side == "top" else cfg.physical_z_min)
                )
            )
            ** 2
            for m in model["bundle"]["modes"]
        ]
    )
    return B, D, H


def block_pair(packet, B, D, H):
    rng = np.random.default_rng(422002)
    rows = []
    for _ in range(3):
        c = rng.normal(size=packet.size) + 1j * rng.normal(size=packet.size)
        a = rng.normal(size=packet.np) + 1j * rng.normal(size=packet.np)
        expected = (packet.B(a), packet.D(c), packet.a["H"] * a)
        actual = (B @ a, D @ c, H * a)
        rows.append(
            [
                float(np.linalg.norm(x - y) / max(np.linalg.norm(y), 1e-30))
                for x, y in zip(actual, expected, strict=True)
            ]
        )
    return dict(samples=rows, passed=max(x for row in rows for x in row) <= 1e-10)


def integrate_load(model, packet, source, boundary_traction, q=15):
    """Analytic physical J and curl(E)xnormal, not a manufactured A*x.

    Explicit ``source=None`` certifies an identically zero volume source. It
    skips volume quadrature/basis tabulation, never tests its magnitude or
    changes a nonzero source. Existing callback paths are unchanged.
    """
    import basix

    if source is not None:
        points, w = basix.make_quadrature(basix.CellType.hexahedron, q)
    fp, fw = basix.make_quadrature(basix.CellType.quadrilateral, q)
    vertices = basix.cell.geometry(basix.CellType.hexahedron)
    faces = basix.cell.topology(basix.CellType.hexahedron)[2]
    cfg = model["cfg"]
    local = np.zeros((packet.nc, packet.dim), complex)
    for cell in range(packet.nc):
        if source is not None:
            E, _, physical, det, _ = affine_basis(model, cell, points)
            local[cell] = det * np.einsum("qia,qa,q->i", E.conj(), source(physical), w)
        coordinates = model["space"].mesh.geometry.x[
            model["space"].mesh.geometry.dofmap[cell]
        ]
        for face in faces:
            vtx, coords = vertices[face], coordinates[face]
            side = (
                "top"
                if np.max(abs(coords[:, 2] - cfg.physical_z_max)) < 1e-12
                else "bottom"
                if np.max(abs(coords[:, 2] - cfg.physical_z_min)) < 1e-12
                else None
            )
            if side is None:
                continue
            axes = np.flatnonzero(np.ptp(vtx, axis=0) > 0.5)
            ref = np.tile(vtx.min(axis=0), (len(fp), 1))
            ref[:, axes] = fp
            E, _, physical, _, J = affine_basis(model, cell, ref)
            area = np.linalg.norm(np.cross(J[:, axes[0]], J[:, axes[1]]))
            local[cell] += area * np.einsum(
                "qia,qa,q->i", E.conj(), boundary_traction(physical, side), fw
            )
    return packet.pullback(local)


def analytic_projections(model, electric, q=15):
    """Independent rectangular integration of physical tangential traces."""
    import basix

    cfg, modes = model["cfg"], model["bundle"]["modes"]
    points, weights = basix.make_quadrature(basix.CellType.quadrilateral, q)
    # Integrate per mesh surface cell: avoids a different oscillatory rule.
    values = np.zeros(len(modes), complex)
    for side, z in (("top", cfg.physical_z_max), ("bottom", cfg.physical_z_min)):
        for xa, xb in zip(model["axes"][0][:-1], model["axes"][0][1:]):
            for ya, yb in zip(model["axes"][1][:-1], model["axes"][1][1:]):
                physical = np.column_stack(
                    (
                        xa + (xb - xa) * points[:, 0],
                        ya + (yb - ya) * points[:, 1],
                        np.full(len(points), z),
                    )
                )
                E = electric(physical)
                for i, mode in enumerate(modes):
                    if mode.side != side:
                        continue
                    wave = np.exp(1j * (physical @ np.asarray(mode.k_vector)))
                    H = (
                        cfg.period_x
                        * cfg.period_y
                        * np.vdot(mode.e_vector[:2], mode.e_vector[:2]).real
                        * abs(np.exp(1j * mode.k_vector[2] * z)) ** 2
                    )
                    values[i] += (
                        (xb - xa)
                        * (yb - ya)
                        * np.sum(
                            weights
                            * wave.conj()
                            * (E[:, :2] @ np.asarray(mode.e_vector[:2]).conj())
                        )
                        / H
                    )
    return values


def incident_rhs(model, packet, B, q=15, *, exact_zero_volume=False):
    cfg = model["cfg"]
    k = np.asarray(cfg.wavevector, complex)
    e = cfg.incident_amplitude * np.asarray(cfg.polarization_vector, complex)

    def traction(x, side):
        if side == "bottom":
            return np.zeros_like(x, dtype=complex)
        return np.exp(1j * (x @ k))[:, None] * np.cross(1j * np.cross(k, e), [0, 0, 1])

    load = integrate_load(
        model,
        packet,
        None if exact_zero_volume else lambda x: np.zeros_like(x, dtype=complex),
        traction,
        q,
    )
    return load + B @ np.asarray(model["bundle"]["incident_projections"])
