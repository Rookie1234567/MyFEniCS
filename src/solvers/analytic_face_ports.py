"""Opt-in affine planar N1curl Fourier-Legendre surface functionals.

No oscillatory quadrature is used by the producer. The Gauss transform below
integrates POLYNOMIAL coefficients exactly; Fourier moments use DLMF 10.54.2.
Only proven facet closure columns are constructed; no magnitude pruning.
"""

from dataclasses import dataclass
from time import perf_counter
import numpy as np
from numpy.polynomial.legendre import leggauss, legvander
from scipy.special import spherical_jn
from scipy import sparse


def fourier_legendre(z, degree):
    z = np.asarray(z, float)
    if not np.isfinite(z).all() or degree < 0 or degree > 12:
        raise ValueError("FOURIER_MOMENT_INPUT")
    # scipy's stable small-argument series / cylindrical Bessel evaluation;
    # use positive arguments and exact parity, never upward recurrence at 0.
    out = np.stack(
        [
            2 * (1j**j) * spherical_jn(j, abs(z)) * np.where(z < 0, (-1) ** j, 1)
            for j in range(degree + 1)
        ],
        axis=-1,
    )
    return out


def oracle_rule(max_half_span, degree):
    """A priori rule from phase span and polynomial degree, not result scanning."""
    n = max(24, int(np.ceil(2 * max_half_span)) + degree + 8)
    if n + 8 > 160:
        raise ValueError("FACE_ORACLE_SPAN_OUTSIDE_BOUNDED_RULE")
    return n, n + 8


@dataclass
class AffineFacePolynomial:
    coefficients: np.ndarray  # degree+1, degree+1, closure columns, xyz
    center: np.ndarray
    axes: np.ndarray  # two reference face directions mapped to physical half axes
    area: float
    closure: np.ndarray
    degree: int
    orientation: int

    def integrate(self, k, kappa):
        k = np.asarray(k, complex)
        kappa = np.asarray(kappa, float)
        if k.ndim != 2 or k.shape[1] != 3 or kappa.shape != (3,):
            raise ValueError("FACE_WAVEVECTOR_LAYOUT")
        z = (k - kappa) @ self.axes.T
        if np.max(abs(z.imag), initial=0) > 1e-12:
            raise ValueError("FACE_COMPLEX_TANGENTIAL_FREQUENCY_UNSUPPORTED")
        mx, my = [fourier_legendre(z[:, j].real, self.degree) for j in range(2)]
        phase = np.exp(1j * ((k - kappa) @ self.center))
        if np.any(abs(phase) == 0) or not np.isfinite(phase).all():
            raise ValueError("ORIGIN_PHASE_NOT_REVERSIBLY_REPRESENTABLE")
        # Parametric domain [-1,1]^2; area is full affine face area.
        return (
            self.area
            * 0.25
            * np.einsum("mi,mj,ijda->mda", mx, my, self.coefficients, optimize=True)
            * phase[:, None, None]
        )

    def blocks(self, modes, kappa, side):
        k = np.asarray([m.k_vector for m in modes])
        e = np.asarray([m.e_vector for m in modes])
        integrals = self.integrate(k, kappa)
        normal = np.array([0, 0, 1 if side == "top" else -1])
        traction = np.cross(1j * np.cross(k, e), normal)
        B = -np.einsum("mda,ma->dm", integrals, traction)
        D = np.einsum("mda,ma->md", integrals.conj()[:, :, :2], e[:, :2].conj())
        return B, D


def face_polynomial(model, cell, facet):
    import basix
    from src.solvers.fixed_phase_audit import affine_basis

    V = model["space"]
    element = V.element.basix_element
    if (
        element.family != basix.ElementFamily.N1E
        or element.cell_type != basix.CellType.hexahedron
    ):
        raise ValueError("ANALYTIC_FACE_REQUIRES_N1CURL_HEX")
    p = element.degree
    vertices = basix.cell.geometry(basix.CellType.hexahedron)
    face = basix.cell.topology(basix.CellType.hexahedron)[2][facet]
    v = vertices[face]
    ax = np.flatnonzero(np.ptp(v, axis=0) > 0.5)
    nodes, w = leggauss(p + 1)
    pairs = np.asarray([(x, y) for x in nodes for y in nodes])
    ref = np.tile(v.min(axis=0), (len(pairs), 1))
    ref[:, ax] = 0.5 * (pairs + 1)
    msh = V.mesh
    coords = msh.geometry.x[msh.geometry.dofmap[cell]]
    fit = np.linalg.lstsq(np.column_stack((np.ones(8), vertices)), coords, rcond=None)[
        0
    ]
    if np.max(abs(np.column_stack((np.ones(8), vertices)) @ fit - coords)) > 1e-12:
        raise ValueError("ANALYTIC_FACE_NON_AFFINE_GEOMETRY")
    J = fit[1:].T
    if np.linalg.det(J) <= 0 or np.max(abs(J[2, ax])) > 1e-12:
        raise ValueError("ANALYTIC_FACE_REQUIRES_HORIZONTAL_AFFINE_BOUNDARY")
    msh.topology.create_entity_permutations()
    info = int(msh.topology.get_cell_permutation_info()[cell])
    T = np.eye(element.dim).ravel()
    V.element.T_apply(T, np.asarray([info], np.uint32), element.dim)
    T = T.reshape(element.dim, element.dim)
    closure = np.asarray(element.entity_closure_dofs[2][facet], np.int64)
    outside = np.setdiff1d(np.arange(element.dim), closure)
    if np.any(T[np.ix_(closure, outside)] != 0) or np.any(
        T[np.ix_(outside, closure)] != 0
    ):
        raise ValueError("FACE_ORIENTATION_MIXES_CLOSURE")
    # Extract unphased Piola basis, retaining every polynomial coefficient.
    basis = affine_basis(dict(model, kappa=np.zeros(3)), cell, ref)[0][:, closure]
    tangential = basis.copy()
    tangential[:, :, 2] = 0
    transform = (legvander(nodes, p) * w[:, None] * (2 * np.arange(p + 1) + 1) / 2).T
    coefficients = np.einsum(
        "ix,jy,xyda->ijda",
        transform,
        transform,
        tangential.reshape(p + 1, p + 1, len(closure), 3),
        optimize=True,
    )
    center_ref = v.min(axis=0).copy()
    center_ref[ax] = 0.5
    center = fit[0] + J @ center_ref
    area = np.linalg.norm(np.cross(J[:, ax[0]], J[:, ax[1]]))
    return AffineFacePolynomial(
        coefficients, center, J[:, ax].T * 0.5, float(area), closure, p, info
    )


def surface_blocks_analytic(model, packet, marker=lambda *_: None):
    import basix

    begin = perf_counter()
    cfg = model["cfg"]
    modes = model["bundle"]["modes"]
    order = np.argsort(packet.a["erows"])
    if np.any(np.bincount(packet.a["erows"], minlength=packet.nc * packet.dim) != 1):
        raise ValueError("ANALYTIC_FACE_SINGLE_MASTER_MPC_REQUIRED")
    ids = packet.a["eids"][order].reshape(packet.nc, packet.dim)
    phase = packet.a["evals"][order].reshape(packet.nc, packet.dim)
    faces = basix.cell.topology(basix.CellType.hexahedron)[2]
    br, bc, bv, dr, dc, dv = [], [], [], [], [], []
    spans = []
    face_count = 0
    for cell in range(packet.nc):
        coords = model["space"].mesh.geometry.x[
            model["space"].mesh.geometry.dofmap[cell]
        ]
        for fi, face in enumerate(faces):
            z = coords[face, 2]
            side = (
                "top"
                if np.max(abs(z - cfg.physical_z_max)) < 1e-12
                else "bottom"
                if np.max(abs(z - cfg.physical_z_min)) < 1e-12
                else None
            )
            if side is None:
                continue
            poly = face_polynomial(model, cell, fi)
            ports = np.asarray([i for i, m in enumerate(modes) if m.side == side])
            sub = [modes[i] for i in ports]
            B, D = poly.blocks(sub, model["kappa"], side)
            cl = poly.closure
            B *= phase[cell, cl, None].conj()
            D *= phase[cell, cl][None, :]
            # Closure defines exact support. Preserve small AND numerically zero
            # entries until duplicate coalescence; no magnitude-based selection.
            br.extend(np.repeat(ids[cell, cl], len(ports)))
            bc.extend(np.tile(ports, len(cl)))
            bv.extend(B.ravel())
            dr.extend(np.repeat(ports, len(cl)))
            dc.extend(np.tile(ids[cell, cl], len(ports)))
            dv.extend(D.ravel())
            span = abs(
                (np.asarray([m.k_vector for m in sub]) - model["kappa"]) @ poly.axes.T
            )
            spans.append(float(np.max(span)))
            face_count += 1
    B = sparse.coo_matrix((bv, (br, bc)), shape=(packet.size, packet.np)).tocsr()
    D = sparse.coo_matrix((dv, (dr, dc)), shape=(packet.np, packet.size)).tocsr()
    H = np.asarray(
        [
            cfg.period_x
            * cfg.period_y
            * np.vdot(m.e_vector[:2], m.e_vector[:2]).real
            * abs(
                np.exp(
                    1j
                    * m.k_vector[2]
                    * (cfg.physical_z_max if m.side == "top" else cfg.physical_z_min)
                )
            )
            ** 2
            for m in modes
        ]
    )
    if not np.isfinite(H).all() or np.any(H <= 0):
        raise ValueError("ANALYTIC_ORIGINAL_H_UNDERFLOW_OR_INVALID")
    marker(
        "analytic_surface_frozen",
        dict(
            faces=face_count,
            max_half_span=max(spans),
            seconds=perf_counter() - begin,
            no_body_assembly=True,
        ),
    )
    return (
        B,
        D,
        H,
        dict(
            faces=face_count,
            max_half_span=max(spans),
            polynomial_degree=model["record"]["degree"],
            oracle_points=oracle_rule(max(spans), model["record"]["degree"]),
            seconds=perf_counter() - begin,
            amplitude_pruning=False,
            algorithm="affine_tensor_Fourier_Legendre_v1",
        ),
    )
