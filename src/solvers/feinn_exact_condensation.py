"""Reference-only exact cell-interior elimination with full FE recovery.

No approximate inverse, shift, thresholded tensor or reduced physical field.
The sparse expansion must have one master per local dof; otherwise reject.
"""

from time import perf_counter

import numpy as np
from scipy import linalg, sparse

from src.solvers.feinn_discretization_audit import atomic_npz


class ExactInteriorCondensation:
    def __init__(self, packet, interior_positions):
        self.packet = packet
        self.i = np.asarray(interior_positions, dtype=int)
        self.t = np.setdiff1d(np.arange(packet.dim), self.i)
        a = packet.a
        if not np.all(np.bincount(a["erows"], minlength=packet.nc * packet.dim) == 1):
            raise ValueError("CONDENSATION_GENERAL_MPC_NOT_QUALIFIED")
        order = np.argsort(a["erows"])
        self.ids = a["eids"][order].reshape(packet.nc, packet.dim)
        self.phase = a["evals"][order].reshape(packet.nc, packet.dim)
        internal = self.ids[:, self.i].ravel()
        if len(np.unique(internal)) != len(internal):
            raise ValueError("CONDENSATION_INTERIOR_NOT_CELL_LOCAL")
        if np.max(abs(self.phase[:, self.i] - 1), initial=0) > 1e-14:
            raise ValueError("CONDENSATION_INTERIOR_PHASE_NOT_QUALIFIED")
        if np.intersect1d(internal, np.r_[a["br"], a["dr"]]).size:
            raise ValueError("CONDENSATION_PORT_HAS_INTERIOR_SUPPORT")
        self.trace = np.setdiff1d(np.arange(packet.size), internal)
        lookup = np.full(packet.size, -1, dtype=np.int32)
        lookup[self.trace] = np.arange(len(self.trace), dtype=np.int32)
        self.trace_ids = lookup[self.ids[:, self.t]]
        if np.any(self.trace_ids < 0):
            raise ValueError("CONDENSATION_TRACE_INTERIOR_OVERLAP")
        self.lu, self.X, self.S = [], [], []
        for F in a["F"]:
            lu = linalg.lu_factor(F[np.ix_(self.i, self.i)])
            X = linalg.lu_solve(lu, F[np.ix_(self.i, self.t)])
            S = F[np.ix_(self.t, self.t)] - F[np.ix_(self.t, self.i)] @ X
            self.lu.append(lu)
            self.X.append(X)
            self.S.append(S)
        self.X, self.S = np.asarray(self.X), np.asarray(self.S)
        self.gi = a["g"][self.ids[:, self.i]].copy()
        self.ui0 = np.empty_like(self.gi)
        gt = a["g"][self.trace].copy()
        for cell, cls in enumerate(a["classes"]):
            self.ui0[cell] = linalg.lu_solve(self.lu[cls], self.gi[cell])
            correction = a["F"][cls][np.ix_(self.t, self.i)] @ self.ui0[cell]
            np.add.at(
                gt, self.trace_ids[cell], -self.phase[cell, self.t].conj() * correction
            )
        self.rhs = np.r_[gt, a["gp"]]

    def recover(self, reduced):
        p = self.packet
        c = np.zeros(p.size, np.complex128)
        c[self.trace] = reduced[: len(self.trace)]
        local_trace = self.phase[:, self.t] * c[self.ids[:, self.t]]
        for cell, cls in enumerate(p.a["classes"]):
            c[self.ids[cell, self.i]] = self.ui0[cell] - self.X[cls] @ local_trace[cell]
        return c, np.asarray(reduced[len(self.trace) :], dtype=np.complex128).copy()

    def correction_rhs(self, body, port):
        """Exact reduction of a full residual using the already held local LU."""
        p = self.packet
        gi = np.asarray(body)[self.ids[:,self.i]]
        ui = np.empty_like(gi)
        gt = np.asarray(body)[self.trace].copy()
        for cell,cls in enumerate(p.a["classes"]):
            ui[cell] = linalg.lu_solve(self.lu[cls],gi[cell])
            correction = p.a["F"][cls][np.ix_(self.t,self.i)]@ui[cell]
            np.add.at(gt,self.trace_ids[cell],-self.phase[cell,self.t].conj()*correction)
        return np.r_[gt,port],ui

    def recover_correction(self, vector, ui):
        c = np.zeros(self.packet.size,np.complex128)
        c[self.trace] = vector[:len(self.trace)]
        local = self.phase[:,self.t]*c[self.ids[:,self.t]]
        for cell,cls in enumerate(self.packet.a["classes"]):
            c[self.ids[cell,self.i]] = ui[cell]-self.X[cls]@local[cell]
        return c,np.asarray(vector[len(self.trace):],np.complex128).copy()

    def assemble(self, model=None, packet=None, marker=lambda *_: None, *, save=None):
        start = perf_counter()
        p, a = self.packet, self.packet.a
        nt, d = len(self.trace), len(self.t)
        n = p.nc * d**2
        rows, cols, values = (
            np.empty(n, np.int32),
            np.empty(n, np.int32),
            np.empty(n, np.complex128),
        )
        for first in range(0, p.nc, 8):
            stop = min(first + 8, p.nc)
            idx, ph = self.trace_ids[first:stop], self.phase[first:stop, self.t]
            section = slice(first * d**2, stop * d**2)
            rows[section] = np.broadcast_to(
                idx[:, :, None], (stop - first, d, d)
            ).ravel()
            cols[section] = np.broadcast_to(
                idx[:, None, :], (stop - first, d, d)
            ).ravel()
            values[section] = (
                ph[:, :, None].conj()
                * self.S[a["classes"][first:stop]]
                * ph[:, None, :]
            ).ravel()
        V = sparse.coo_matrix((values, (rows, cols)), shape=(nt, nt)).tocsr()
        del rows, cols, values
        B = sparse.coo_matrix(
            (a["bv"], (a["br"], a["bp"])), shape=(p.size, p.np)
        ).tocsr()[self.trace]
        D = sparse.coo_matrix(
            (a["dv"], (a["dp"], a["dr"])), shape=(p.np, p.size)
        ).tocsr()[:, self.trace]
        M = sparse.bmat([[V, B], [-D, sparse.diags(a["H"])]], format="csr")
        M.eliminate_zeros()
        M.sort_indices()
        rng = np.random.default_rng(421909)
        pairs = []
        for _ in range(3):
            z = rng.normal(size=nt + p.np) + 1j * rng.normal(size=nt + p.np)
            c, alpha = self.recover(z)
            full = np.r_[
                p.volume(c) + p.B(alpha) - a["g"], -p.D(c) + a["H"] * alpha - a["gp"]
            ]
            reduced = M @ z - self.rhs
            expected = np.r_[full[self.trace], full[p.size :]]
            scale = np.linalg.norm(expected) + np.linalg.norm(reduced)
            interior = np.setdiff1d(np.arange(p.size), self.trace)
            pairs.append(
                dict(
                    reduced=float(np.linalg.norm(reduced - expected) / scale),
                    interior=float(
                        np.linalg.norm(full[interior])
                        / max(np.linalg.norm(full), 1e-30)
                    ),
                )
            )
        if max(v for row in pairs for v in row.values()) > 1e-10:
            raise ValueError("EXACT_CONDENSATION_ACTION_PAIR_FAILED")
        if save:
            atomic_npz(
                save,
                indptr=M.indptr,
                indices=M.indices,
                data=M.data,
                shape=np.asarray(M.shape),
                rhs=self.rhs,
                trace=self.trace,
                local_ids=self.ids,
                local_phase=self.phase,
                interior_positions=self.i,
                gi=self.gi,
                ui0=self.ui0,
                X=self.X,
                lu=np.asarray([x[0] for x in self.lu]),
                pivots=np.asarray([x[1] for x in self.lu]),
            )
        marker(
            "exact_condensed_CSR",
            dict(
                rows=M.shape[0],
                nnz=M.nnz,
                complete_recovered_FE=p.size,
                action_pairs=pairs,
                seconds=perf_counter() - start,
            ),
        )
        return M, max(v for row in pairs for v in row.values())


def capacity(cells, degree, classes=48, ports=40):
    dim = 3 * degree * (degree + 1) ** 2
    interior = 3 * degree * (degree - 1) ** 2
    trace = dim - interior
    triplets = cells * trace**2
    # COO + conversion/sort work + CSR and int64 PETSc duplication; factors
    # are admitted from the actual symbolic estimate, not this payload.
    local_cache = classes * (dim**2 + interior**2 + interior * trace + trace**2) * 16
    reserve = triplets * 80 + local_cache + 1024 * 2**20
    return dict(
        kind="derived conservative assembly/conversion overlap; not RSS",
        degree=degree,
        local_dimension=dim,
        local_interior=interior,
        local_trace=trace,
        raw_all_cell_tensor_bytes=cells * dim**2 * 16,
        triplets=triplets,
        cache_classes_assumed=classes,
        local_cache_upper_bytes=local_cache,
        allocation_upper_bytes=reserve,
        factor_planning_cap_bytes=12 * 2**30,
        full_FE_recovered=True,
    )
