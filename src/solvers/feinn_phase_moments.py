"""FE-only phase/moment qualification and quadrature packet preparation."""

from copy import deepcopy
from itertools import product
from pathlib import Path

import basix
import numpy as np
from dolfinx import fem

from src.solvers.feinn_interpolation import build_full_moments, full_space
from src.solvers.feinn_discretization_audit import atomic_npz
from src.solvers.feinn_fem import build_model
from src.solvers.neural_trace import moment_packet_values
from src.solvers.neural_fe_action_packet import array_hash

K_INC = np.array([1.2564456695248023, 0, -0.02193134074032823])
XC = np.array([0, 0, 3.75])
AMPLITUDE = np.array([1.1 + 0.4j, -0.7 + 0.8j, 0.3 - 0.6j])


def independent_phase_moments(packet, element, k):
    """Legendre density reconstruction and separate 64-node 1D integration.

    Only the manufactured plane wave is separable here; the network field and
    Maxwell problem remain fully 3D. No custom full_moment_element is called.
    """
    geometry = basix.cell.geometry(element.cell_type)
    topology = basix.cell.topology(element.cell_type)
    metadata = []
    for dimension in (1, 2, 3):
        for entity, points in enumerate(element.x[dimension]):
            if not len(points):
                continue
            vertices = geometry[topology[dimension][entity]]
            axes = np.flatnonzero(np.ptp(vertices, axis=0) > 0.5)
            count = len(np.unique(points[:, axes[0]]))
            nodes, weights = np.polynomial.legendre.leggauss(count)
            nodes, weights = (nodes + 1) / 2, weights / 2
            old_weights = np.ones(len(points))
            polynomials = list(product(range(count), repeat=dimension))
            vander = [
                np.polynomial.legendre.legvander(2 * points[:, axis] - 1, count - 1)
                for axis in axes
            ]
            V = np.column_stack(
                [
                    np.prod(
                        np.stack([vander[j][:, power[j]] for j in range(dimension)]),
                        axis=0,
                    )
                    for power in polynomials
                ]
            )
            for axis in axes:
                nearest = np.argmin(abs(points[:, axis, None] - nodes[None]), axis=1)
                old_weights *= weights[nearest]
            density = element.M[dimension][entity][..., 0] / old_weights[None, None, :]
            coefficients = np.linalg.solve(
                V, density.reshape(-1, len(points)).T
            ).T.reshape(density.shape[0], 3, len(polynomials))
            fixed = vertices.min(axis=0).copy()
            fixed[axes] = 0
            metadata.append(
                (
                    axes,
                    polynomials,
                    coefficients,
                    fixed,
                    element.entity_dofs[dimension][entity],
                )
            )
    nodes, weights = np.polynomial.legendre.leggauss(64)
    nodes, weights = (nodes + 1) / 2, weights / 2
    out = np.empty(int(packet["active_rows"]), np.complex128)
    for cell, J in enumerate(packet["jacobians"]):
        kr = J.T @ k
        integrals = [
            np.sum(
                np.polynomial.legendre.legvander(2 * nodes - 1, element.degree)
                * (weights * np.exp(1j * kr[axis] * nodes))[:, None],
                axis=0,
            )
            for axis in range(3)
        ]
        values = np.zeros(element.dim, np.complex128)
        for axes, powers, coefficients, fixed, positions in metadata:
            phases = np.array(
                [
                    np.prod([integrals[axis][power[j]] for j, axis in enumerate(axes)])
                    for power in powers
                ]
            ) * np.exp(1j * np.dot(kr, fixed))
            values[positions] = np.einsum(
                "iap,a,p->i", coefficients, AMPLITUDE @ J, phases
            ) * np.exp(1j * np.dot(k, packet["origins"][cell] - XC))
        values = packet["transforms"][packet["orientation_ids"][cell]] @ values
        rows = packet["owner_rows"][cell]
        selected = rows >= 0
        out[rows[selected]] = values[selected]
    return out


def plane(k):
    def field(x):
        return np.exp(1j * ((x - XC) @ k))[:, None] * AMPLITUDE

    return field


def pair_phase(packet, space, witness, mpc, k):
    expected = fem.Function(witness)
    expected.interpolate(lambda x: plane(k)(x.T).T)
    c = moment_packet_values(packet, plane(k))
    direct = independent_phase_moments(packet, space.element.basix_element, k)
    masters = packet["master_native_rows"]
    family = {}
    for name in ("edge", "face", "interior"):
        rows = packet["owner_rows"][:, packet[name + "_positions"]].ravel()
        rows = rows[rows >= 0]
        family[name] = dict(
            count=len(rows),
            norm=float(np.linalg.norm(direct[rows])),
            relative=float(
                np.linalg.norm(c[rows] - direct[rows]) / np.linalg.norm(direct[rows])
            ),
        )
    stored = fem.Function(mpc.function_space)
    stored.x.array[:] = 0
    stored.x.array[masters] = c
    mpc.backsubstitution(stored)
    defect = float(
        np.linalg.norm(stored.x.array - expected.x.array)
        / np.linalg.norm(expected.x.array)
    )
    relative = float(np.linalg.norm(c - direct) / np.linalg.norm(direct))
    return dict(
        independent_64_node_Legendre_relative=relative,
        custom_DOLFINx_relative=float(
            np.linalg.norm(c - expected.x.array[masters]) / np.linalg.norm(c)
        ),
        mpc_full_storage_relative=defect,
        families=family,
        orientations=len(packet["transforms"]),
        passed=max(relative, defect, *[v["relative"] for v in family.values()])
        <= 1e-10,
    )


def prepare(design, native_index, artifact, marker, manifest):
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )

    model = build_model(design, 3, marker, dtn_quadrature_degree=15)
    try:
        cfg = model["cfg"]
        actual = np.array([cfg.kx, cfg.ky, -np.sqrt(cfg.k0**2 - cfg.kx**2 - cfg.ky**2)])
        if np.linalg.norm(actual - K_INC) > 1e-14:
            raise ValueError("INCIDENT_PHASE_IDENTITY_FAILED")
        maps, files = {}, {}
        for q in (15, 30, 60):
            packet, witness = build_full_moments(
                model["space"], model["floquet"].mpc, q, design["geometry"]["cells"]
            )
            path = Path(artifact) / f"moments_q{q}.npz"
            if q in (15, 30):
                entry = native_index["files"][f"moments_q{q}"]
                with np.load(entry["path"], allow_pickle=False) as old:
                    if any(
                        array_hash(packet[key]) != array_hash(old[key])
                        for key in packet
                    ):
                        raise ValueError("ORIGINAL_MOMENT_IDENTITY_FAILED")
                files[f"moments_q{q}"] = Path(entry["path"])
            else:
                atomic_npz(path, **packet)
                files[f"moments_q{q}"] = path
            maps[q] = packet
            marker(
                "network_moment_rule_prepared",
                dict(
                    q=q,
                    points=len(packet["reference_points"]),
                    payload_bytes=sum(v.nbytes for v in packet.values()),
                ),
            )
            if q == 15:
                main = pair_phase(
                    packet, model["space"], witness, model["floquet"].mpc, K_INC
                )
                marker("independent_phase_all_families", main)
        if not main["passed"]:
            raise ValueError("PHASE_INDEPENDENT_MOMENTS_FAILED")
    finally:
        destroy_same_mesh_physical_action(model["bundle"])
    small = deepcopy(design)
    small["geometry"]["cells"] = [2, 2, 2]
    small["geometry"]["bounds_nm"] = [[-1.25, 1.25], [-1.25, 1.25], [2.5, 5]]
    small["incidence"]["grazing_deg"] = 35
    cfg, data, space, *_ = full_space(small, 3)
    floquet = build_double_floquet_mpc(space, data, cfg)
    synthetic_k = np.array(
        [cfg.kx, cfg.ky, -np.sqrt(cfg.k0**2 - cfg.kx**2 - cfg.ky**2)]
    )
    p, w = build_full_moments(space, floquet.mpc, 15, [2, 2, 2])
    synthetic = pair_phase(p, space, w, floquet.mpc, synthetic_k)
    phase_x = np.exp(1j * cfg.kx * 2.5)
    synthetic["phase_x"] = [float(phase_x.real), float(phase_x.imag)]
    synthetic["nonunit_distance"] = float(abs(phase_x - 1))
    marker("nonunit_Floquet_phase_check", synthetic)
    if not synthetic["passed"] or synthetic["nonunit_distance"] < 0.1:
        raise ValueError("NONUNIT_FLOQUET_PHASE_FAILED")
    return dict(
        status="PHASE_FE_MOMENTS_PASS",
        actual_k_inc=actual,
        origin_nm=XC,
        independent_phase=main,
        synthetic_nonunit_Floquet=synthetic,
        volume_and_DtN_degree=15,
        reference_loaded=False,
        full_independent_complex_FE=31968,
    ), files
