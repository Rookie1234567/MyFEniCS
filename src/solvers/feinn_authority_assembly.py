"""Reference-only bounded assembly and a separate Basix integration authority.

The CSR uses saved F/P tensors. The verification integrates basis values and
derivatives independently; it never reads F. Port/material/MPC input is shared
and explicitly reported. This path is not imported by neural training.
"""

import gc
import json
import os
from pathlib import Path
import subprocess
import signal
import sys
from time import perf_counter

import numpy as np
from scipy import sparse

from src.solvers.feinn_discretization_audit import atomic_npz, POLICY, verify_model
from src.solvers.feinn_native import load_native


def packet_csr(model, packet, marker=lambda *_: None, *, save=None):
    """Assemble sum(P.H F P), including all independent interior moments."""
    started = perf_counter()
    a = packet.a
    local_rows = a["erows"]
    counts = np.bincount(local_rows, minlength=packet.nc * packet.dim)
    marker("packet_COO_begin", dict(cells=packet.nc, dimension=packet.dim))
    if np.all(counts == 1):
        order = np.argsort(local_rows)
        ids = a["eids"][order].reshape(packet.nc, packet.dim)
        phase = a["evals"][order].reshape(packet.nc, packet.dim)
        n = packet.nc * packet.dim**2
        rows, cols = np.empty(n, np.int32), np.empty(n, np.int32)
        vals = np.empty(n, np.complex128)
        for start in range(0, packet.nc, 8):
            stop = min(start + 8, packet.nc)
            section = slice(start * packet.dim**2, stop * packet.dim**2)
            rows[section] = np.broadcast_to(
                ids[start:stop, :, None], (stop - start, packet.dim, packet.dim)
            ).ravel()
            cols[section] = np.broadcast_to(
                ids[start:stop, None, :], (stop - start, packet.dim, packet.dim)
            ).ravel()
            vals[section] = (
                phase[start:stop, :, None].conj()
                * a["F"][a["classes"][start:stop]]
                * phase[start:stop, None, :]
            ).ravel()
            if start % 64 == 0:
                marker("packet_COO_progress", dict(completed_cells=stop))
        marker(
            "packet_CSR_begin",
            dict(triplets=n, payload_bytes=rows.nbytes + cols.nbytes + vals.nbytes),
        )
        V = sparse.coo_matrix(
            (vals, (rows, cols)), shape=(packet.size, packet.size)
        ).tocsr()
        del rows, cols, vals
    else:
        # General sparse MPC; no amplitude threshold and no dense global matrix.
        blocks = []
        for cell in range(packet.nc):
            selected = (local_rows // packet.dim) == cell
            P = sparse.csr_matrix(
                (
                    a["evals"][selected],
                    (local_rows[selected] % packet.dim, a["eids"][selected]),
                ),
                shape=(packet.dim, packet.size),
            )
            blocks.append(
                (P.conj().T @ sparse.csr_matrix(a["F"][a["classes"][cell]]) @ P).tocsr()
            )
            if len(blocks) >= 8:
                blocks = [sum(blocks[1:], blocks[0])]
        V = sum(blocks[1:], blocks[0])
    V.eliminate_zeros()  # exact structural zeros only
    V.sort_indices()
    marker("packet_CSR_end", dict(nnz=V.nnz, seconds=perf_counter() - started))
    B = sparse.coo_matrix(
        (a["bv"], (a["br"], a["bp"])), shape=(packet.size, packet.np)
    ).tocsr()
    D = sparse.coo_matrix(
        (a["dv"], (a["dp"], a["dr"])), shape=(packet.np, packet.size)
    ).tocsr()
    marker("packet_port_join_begin", {})
    M = sparse.bmat([[V, B], [-D, sparse.diags(a["H"])]], format="csr")
    M.eliminate_zeros()
    M.sort_indices()
    del V, B, D
    gc.collect()
    rng = np.random.default_rng(421801)
    pairs = []
    for _ in range(3):
        c = rng.normal(size=packet.size) + 1j * rng.normal(size=packet.size)
        alpha = rng.normal(size=packet.np) + 1j * rng.normal(size=packet.np)
        expected = np.r_[
            packet.volume(c) + packet.B(alpha), -packet.D(c) + a["H"] * alpha
        ]
        pairs.append(
            float(
                np.linalg.norm(M @ np.r_[c, alpha] - expected)
                / np.linalg.norm(expected)
            )
        )
    if max(pairs) > 1e-10:
        raise ValueError("PACKET_CSR_SELF_PAIR_FAILED")
    if save is not None:
        atomic_npz(
            save,
            indptr=M.indptr,
            indices=M.indices,
            data=M.data,
            shape=np.array(M.shape),
            rhs=np.r_[a["g"], a["gp"]],
            masters=a["masters"],
        )
    marker(
        "packet_port_join_end",
        dict(nnz=M.nnz, self_pairs=pairs, self_pair_is_not_independent_authority=True),
    )
    return M, max(pairs)


class BasixVolumeAudit:
    """Independent physical basis quadrature, distinct from saved FFCx F."""

    def __init__(self, model, packet):
        import basix

        self.packet = packet
        space = model["space"]
        element = space.element.basix_element
        q, weights = basix.make_quadrature(basix.CellType.hexahedron, 15)
        t = element.tabulate(1, q)
        curl = np.stack(
            (
                t[2, :, :, 2] - t[3, :, :, 1],
                t[3, :, :, 0] - t[1, :, :, 2],
                t[1, :, :, 1] - t[2, :, :, 0],
            ),
            axis=2,
        )
        mesh = space.mesh
        mesh.topology.create_entity_permutations()
        infos = mesh.topology.get_cell_permutation_info()
        vertices = basix.cell.geometry(basix.CellType.hexahedron)
        X = np.column_stack((np.ones(8), vertices))
        self.matrices, self.classes, cache = [], [], {}
        eps = {
            model["cfg"].tags.air: model["cfg"].eps_r,
            model["cfg"].tags.substrate: model["cfg"].substrate_index ** 2,
            model["cfg"].tags.grating: model["cfg"].grating_index ** 2,
        }
        for cell, tag in enumerate(model["tags"]):
            coordinates = mesh.geometry.x[mesh.geometry.dofmap[cell]].copy()
            coordinates -= coordinates[0]
            fit = np.linalg.lstsq(X, coordinates, rcond=None)[0]
            J = fit[1:].T
            key = (J.tobytes(), int(tag), int(infos[cell]))
            if key not in cache:
                determinant = np.linalg.det(J)
                if determinant <= 0 or np.linalg.norm(X @ fit - coordinates) > 1e-11:
                    raise ValueError("INDEPENDENT_AFFINE_GEOMETRY_FAILED")
                E = np.einsum("qia,ab->qib", t[0], np.linalg.inv(J))
                C = np.einsum("qia,ba->qib", curl, J) / determinant
                T = np.eye(element.dim).ravel()
                space.element.T_apply(
                    T, np.asarray([infos[cell]], np.uint32), element.dim
                )
                T = T.reshape(element.dim, element.dim)
                # Construct oriented basis independently, before quadrature.
                E = np.einsum("ij,qja->qia", T, E)
                C = np.einsum("ij,qja->qia", T, C)
                K = determinant * (
                    np.einsum("qia,qja,q->ij", C.conj(), C, weights, optimize=True)
                    / model["cfg"].mu_r
                    - model["cfg"].k0 ** 2
                    * eps[int(tag)]
                    * np.einsum("qia,qja,q->ij", E.conj(), E, weights, optimize=True)
                )
                cache[key] = len(self.matrices)
                self.matrices.append(K)
            self.classes.append(cache[key])
        self.matrices = np.asarray(self.matrices)
        self.classes = np.asarray(self.classes)
        self.scope = dict(
            integration="Basix value/derivative physical quadrature; oriented basis, no saved F used",
            shared_inputs=[
                "geometry",
                "materials",
                "Basix finite element",
                "orientation convention",
                "MPC expansion",
                "DtN coupling",
                "original rhs",
            ],
            q=15,
            classes=len(cache),
            quadrature_points=len(q),
        )

    def volume(self, c, adjoint=False):
        local = self.packet.expand(c)
        out = np.empty_like(local)
        for start in range(0, self.packet.nc, 8):
            stop = min(start + 8, self.packet.nc)
            K = self.matrices[self.classes[start:stop]]
            out[start:stop] = (
                np.einsum("cij,ci->cj", K.conj(), local[start:stop])
                if adjoint
                else np.einsum("cij,cj->ci", K, local[start:stop])
            )
        return self.packet.pullback(out)

    def check(self, seed=421802):
        rng = np.random.default_rng(seed)
        pairs = []
        for _ in range(3):
            c = rng.normal(size=self.packet.size) + 1j * rng.normal(
                size=self.packet.size
            )
            alpha = rng.normal(size=self.packet.np) + 1j * rng.normal(
                size=self.packet.np
            )
            y = rng.normal(size=self.packet.size) + 1j * rng.normal(
                size=self.packet.size
            )
            v, expected = self.volume(c), self.packet.volume(c)
            vh = self.volume(y, True)
            aug = np.r_[
                v + self.packet.B(alpha), -self.packet.D(c) + self.packet.a["H"] * alpha
            ]
            old = np.r_[
                expected + self.packet.B(alpha),
                -self.packet.D(c) + self.packet.a["H"] * alpha,
            ]
            pairs.append(
                dict(
                    volume=float(
                        np.linalg.norm(v - expected) / np.linalg.norm(expected)
                    ),
                    augmented=float(np.linalg.norm(aug - old) / np.linalg.norm(old)),
                    adjoint=float(
                        abs(np.vdot(y, v) - np.vdot(vh, c))
                        / (
                            np.linalg.norm(y) * np.linalg.norm(v)
                            + np.linalg.norm(vh) * np.linalg.norm(c)
                        )
                    ),
                    interior_norm=float(
                        np.linalg.norm(self.packet.storage(c)[self.packet.a["idofs"]])
                    ),
                )
            )
        return dict(
            samples=pairs,
            scope=self.scope,
            passed=all(
                row[k] <= 1e-10
                for row in pairs
                for k in ("volume", "augmented", "adjoint")
            ),
        )

    def total_residual(self, c):
        p = self.packet
        total = p.a["background"] + c
        alpha = p.a["background_alpha"] + p.alpha(c)
        r = np.r_[
            self.volume(total) + p.B(alpha) - p.a["total_g"],
            -p.D(total) + p.a["H"] * alpha,
        ]
        return float(np.linalg.norm(r) / np.linalg.norm(p.a["total_g"]))


def profile_native(path):
    """Child of the bounded formal checks tree, never a detached worker."""
    from src.solvers.feinn_fem import build_model
    from src.solvers.feinn_reference import original_augmented_matrix
    from src.io.feinn_pilot import DESIGN
    from src.runners.feinn_workflow import load_index

    started = perf_counter()

    def mark(name, facts):
        with Path(path).open("a") as stream:
            stream.write(
                json.dumps(
                    dict(name=name, seconds=perf_counter() - started, facts=facts)
                )
                + "\n"
            )
            stream.flush()
        print(name, flush=True)

    model = build_model(
        json.loads(DESIGN.read_text()), 4, mark, dtn_quadrature_degree=15
    )
    packet = load_native(load_index("v7_p_transfer_checks")["files"]["native"]["path"])
    M, pair = original_augmented_matrix(model, packet, mark)
    mark("profile_complete", dict(nnz=M.nnz, pair=pair))


def checks(design, native_index, reference_index, transfer, artifact, marker, manifest):
    from copy import deepcopy
    from src.solvers.feinn_fem import build_model, export_native
    from src.solvers.feinn_discretization_audit import load_p3
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )

    p3, ref, original = load_p3(native_index, reference_index)
    profile = artifact / "assembly_profile.jsonl"
    start = perf_counter()
    child = subprocess.Popen(
        [sys.executable, "-m", __name__, "profile", str(profile)],
        start_new_session=True,
    )
    try:
        code = child.wait(timeout=300)
        profile_stop = "COMPLETED" if code == 0 else "CHILD_ERROR"
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGTERM)
        child.wait(timeout=20)
        profile_stop = "BOUNDED_PROFILE_STOP"
    charged = perf_counter() - start
    events = (
        [json.loads(line) for line in profile.read_text().splitlines()]
        if profile.exists()
        else []
    )
    marker(
        "assembly_profile_end",
        dict(
            seconds=charged,
            stop=profile_stop,
            last_event=events[-1] if events else None,
        ),
    )
    small = deepcopy(design)
    small["geometry"]["cells"] = [2, 2, 2]
    small["geometry"]["bounds_nm"] = [[-1.25, 1.25], [-1.25, 1.25], [2.5, 5.0]]
    small_model = build_model(small, 4, marker, dtn_quadrature_degree=15)
    try:
        small_packet, _ = export_native(small_model, marker)
        small_integral = BasixVolumeAudit(small_model, small_packet)
        small_gate = small_integral.check()
        marker("eight_cell_independent_p4_integration", small_gate)
        if not small_gate["passed"]:
            raise ValueError("SMALL_P4_INDEPENDENT_INTEGRATION_FAILED")
        del small_integral, small_packet
    finally:
        destroy_same_mesh_physical_action(small_model["bundle"])
    model = build_model(design, 4, marker, dtn_quadrature_degree=15)
    try:
        equivalence = verify_model(model, original)
        p4 = load_native(transfer["files"]["native"]["path"])
        independent4 = BasixVolumeAudit(model, p4)
        gate4 = independent4.check()
        marker("independent_Basix_p4", gate4)
        if not gate4["passed"]:
            raise ValueError("REFERENCE_INDEPENDENCE_UNRESOLVED")
        csr_path = artifact / "p4_augmented_csr.npz"
        M, pair = packet_csr(model, p4, marker, save=csr_path)
        payload = sum(x.nbytes for x in (M.indptr, M.indices, M.data))
        del M, independent4
    finally:
        destroy_same_mesh_physical_action(model["bundle"])
    model3 = build_model(design, 3, marker, dtn_quadrature_degree=15)
    try:
        independent3 = BasixVolumeAudit(model3, p3)
        gate3 = independent3.check()
        M3, _ = packet_csr(model3, p3, marker)
        alpha = p3.alpha(ref)
        residual3 = float(
            np.linalg.norm(M3 @ np.r_[ref, alpha] - np.r_[p3.a["g"], p3.a["gp"]])
            / np.linalg.norm(np.r_[p3.a["g"], p3.a["gp"]])
        )
        total3 = independent3.total_residual(ref)
        if not gate3["passed"] or max(residual3, total3) > 1e-10:
            raise ValueError("NEW_ASSEMBLY_P3_REFERENCE_FAILED")
    finally:
        destroy_same_mesh_physical_action(model3["bundle"])
    return dict(
        status="AUTHORITY_ASSEMBLY_CHECKS_PASS",
        profile_seconds=charged,
        profile_events=events,
        profile_stop=profile_stop,
        eight_cell_p4=small_gate,
        independent_p4=gate4,
        independent_p3=gate3,
        p3_saved_reference_augmented=residual3,
        p3_independent_total=total3,
        CSR_self_pair=pair,
        CSR_payload_bytes=payload,
        physics_equivalence_fields=equivalence,
        identity=transfer["result"]["identity"],
        independent_families=transfer["result"]["independent_families"],
        repair="exact saved tensor P.H F P, independently Basix integrated",
        no_p3_solve=True,
        **POLICY,
    ), dict(csr=csr_path, profile=profile)


def recover(
    design,
    native_index,
    reference_index,
    transfer,
    assembly,
    artifact,
    marker,
    manifest,
):
    from src.solvers.feinn_discretization_audit import reference

    if assembly["result"]["status"] != "AUTHORITY_ASSEMBLY_CHECKS_PASS":
        raise ValueError("ASSEMBLY_NOT_QUALIFIED")
    entry = assembly["files"]["csr"]

    def assembler(model, packet, mark):
        with np.load(entry["path"], allow_pickle=False) as a:
            if not np.array_equal(
                a["masters"], packet.a["masters"]
            ) or not np.array_equal(a["rhs"], np.r_[packet.a["g"], packet.a["gp"]]):
                raise ValueError("CSR_RECOVERY_IDENTITY_FAILED")
            M = sparse.csr_matrix(
                (a["data"], a["indices"], a["indptr"]), shape=tuple(a["shape"])
            )
        mark("saved_CSR_loaded_no_reassembly", dict(sha256=entry["sha256"]))
        return M, assembly["result"]["CSR_self_pair"]

    # Explicit reviewed assembler hook; the ordinary reference remains unchanged.
    return reference(
        design,
        native_index,
        reference_index,
        transfer,
        artifact,
        marker,
        manifest,
        assembler=assembler,
        independent_factory=BasixVolumeAudit,
    )


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "profile":
        raise SystemExit("only bounded child profile supported")
    profile_native(sys.argv[2])
