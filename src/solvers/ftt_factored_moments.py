"""Opt-in FTT moments: full polynomial finite sums, bounded core AD.

The p3 Basix moment densities have degree at most two per varying axis.
All polynomial coefficients (including tiny nonzeros) are retained. The
recovered finite sum is checked against EVERY original interpolation entry;
an unsupported entity/geometry uses the original exact point sum instead.
No network/material/reference-dependent factorization occurs here.
"""

import hashlib
from functools import lru_cache
from time import perf_counter
import numpy as np
import torch
from scipy import sparse


@lru_cache(maxsize=256)
def _path(formula, shapes):
    return np.einsum_path(formula, *[np.empty(s) for s in shapes], optimize="greedy")[0]


def contract(formula, *arrays):
    return np.einsum(
        formula, *arrays, optimize=_path(formula, tuple(a.shape for a in arrays))
    )


def model_identity(model):
    h = hashlib.sha256(model.model_kind.encode())
    for name, value in model.state_dict().items():
        h.update(name.encode())
        h.update(value.detach().numpy().tobytes())
    return h.hexdigest()


def tensor_plan(packet):
    """Recover the original degree-two polynomial definition, not low-rank SVD.

    Complete Gauss finite sums provide the Legendre coefficients by exact
    discrete orthogonality. A failed algebraic pairing keeps the raw row.
    """
    points = packet["reference_points"]
    interpolation = packet["interpolation"].reshape(-1, 3, len(points))
    groups = {}
    for row, weights in enumerate(interpolation):
        support = tuple(np.flatnonzero(np.any(weights != 0, axis=0)))
        groups.setdefault(support, []).append(row)
    plans, errors = [], []
    for support, rows in groups.items():
        ids = np.asarray(support)
        coords = points[ids]
        axes = [np.unique(coords[:, a]) for a in range(3)]
        indices = [np.searchsorted(axes[a], coords[:, a]) for a in range(3)]
        shape = tuple(len(a) for a in axes)
        if np.prod(shape) != len(ids):
            plans.append(dict(rows=np.asarray(rows), raw=True, ids=ids))
            continue
        bases, left, quadrature = [], [], []
        qualified = True
        for nodes in axes:
            if len(nodes) == 1:
                basis, w, L = np.ones((1, 1)), np.ones(1), np.ones((1, 1))
            else:
                gauss, w = np.polynomial.legendre.leggauss(len(nodes))
                w = w / 2
                qualified &= np.max(abs((gauss + 1) / 2 - nodes)) <= 2e-14
                basis = np.polynomial.legendre.legvander(2 * nodes - 1, 2)
                L = basis.T * np.asarray([1, 3, 5])[:, None]
            bases.append(basis)
            left.append(L)
            quadrature.append(w)
        raw = np.zeros((len(rows), 3, *shape))
        raw[:, :, indices[0], indices[1], indices[2]] = interpolation[rows][:, :, ids]
        C = np.einsum("raijk,pi,qj,sk->rapqs", raw, *left, optimize=True)
        W = [b * w[:, None] for b, w in zip(bases, quadrature, strict=True)]
        recovered = np.einsum("rapqs,ip,jq,ks->raijk", C, *W, optimize=True)
        numerator = float(np.linalg.norm(recovered - raw))
        denominator = float(np.linalg.norm(raw))
        error = numerator / denominator
        errors.append(
            dict(
                rows=rows,
                numerator=numerator,
                denominator=denominator,
                relative=error,
                polynomial_degrees=[w.shape[1] - 1 for w in W],
            )
        )
        # No magnitude truncation. Raw non-polynomial rows remain exact.
        if not qualified or error > 1e-12:
            plans.append(dict(rows=np.asarray(rows), raw=True, ids=ids))
        else:
            plans.append(
                dict(
                    rows=np.asarray(rows),
                    raw=False,
                    axes=axes,
                    weights=[w.T.copy() for w in W],
                    coefficients=C,
                )
            )
    return plans, errors


def core_product(cores):
    return np.einsum("psij,qsjk,rskl->pqrsil", *cores, optimize=True)[..., 0, 0]


def core_product_adjoint(cores, dual):
    X, Y, Z = cores
    # Real pairing Re(vdot(dual, X Y Z)): every other factor is conjugated.
    gx = np.einsum("pqrs,qsjk,rskl->psjl", dual, Y.conj(), Z.conj(), optimize=True)
    gy = np.einsum("pqrs,psij,rskl->qsjk", dual, X.conj(), Z.conj(), optimize=True)
    gz = np.einsum("pqrs,psij,qsjk->rski", dual, X.conj(), Y.conj(), optimize=True)
    return gx.transpose(0, 1, 3, 2), gy, gz


class FactoredMomentMap:
    """Original full owner/Piola/orientation, unique 1-D node tables and VJP.

    The axis-aligned affine identity is verified explicitly. Tiny least-squares
    geometry roundoff is reported, never used to merge nearby distinct nodes.
    Piola uses the original full J, including its small off-diagonal entries.
    Unsupported geometry uses exact physical coordinates and raw finite sums.
    """

    def __init__(self, packet, point_batch=512, *, share_entity_integrals=True):
        started = perf_counter()
        self.packet, self.point_batch = packet, point_batch
        if point_batch not in (128, 256, 512):
            raise ValueError("PREDECLARED_FTT_POINT_BATCH_REQUIRED")
        self.size = int(packet["active_rows"])
        self.nc = len(packet["owner_rows"])
        self.nq = len(packet["reference_points"])
        rows = packet["owner_rows"]
        if not np.array_equal(np.sort(rows[rows >= 0]), np.arange(self.size)):
            raise ValueError("ONE_OWNER_PER_INDEPENDENT_FE_COEFFICIENT_REQUIRED")
        self.plans, self.interpolation_errors = tensor_plan(packet)
        self.interpolation = sparse.csr_matrix(
            packet["interpolation"], dtype=np.complex128
        )
        self.ref_axes = [np.unique(packet["reference_points"][:, a]) for a in range(3)]
        self.geometry_records, self.cell_plans = [], []
        self.node_lists = [[], [], []]
        # This construction is cell bounded; no global 3-D coordinate table.
        for cell in range(self.nc):
            J = packet["jacobians"][cell]
            perm = np.argmax(abs(J), axis=0)
            aligned = len(np.unique(perm)) == 3
            canonical = np.zeros((3, 3))
            canonical[perm, np.arange(3)] = J[perm, np.arange(3)]
            defect = float(np.linalg.norm(J - canonical) / np.linalg.norm(J))
            aligned &= defect <= 2e-14
            origin = packet["origins"][cell]
            if aligned:
                physical_axes = [None] * 3
                for ref in range(3):
                    phys = int(perm[ref])
                    physical_axes[phys] = (
                        origin[phys] + self.ref_axes[ref] * J[phys, ref]
                    )
                actual = origin + packet["reference_points"] @ J.T
                canonical_points = origin + packet["reference_points"] @ canonical.T
                coordinate_error = float(np.max(abs(actual - canonical_points)))
                self.geometry_records.append(
                    dict(
                        cell=cell,
                        aligned=True,
                        affine_roundoff_relative=defect,
                        max_node_roundoff_nm=coordinate_error,
                        reference_to_physical_axes=perm.tolist(),
                    )
                )
                for a in range(3):
                    self.node_lists[a].append(physical_axes[a])
                self.cell_plans.append((True, perm))
            else:
                coords = origin + packet["reference_points"] @ J.T
                self.geometry_records.append(
                    dict(
                        cell=cell,
                        aligned=False,
                        affine_roundoff_relative=defect,
                        exact_point_fallback=True,
                    )
                )
                for a in range(3):
                    self.node_lists[a].append(np.unique(coords[:, a]))
                self.cell_plans.append((False, None))
        self.nodes = [np.unique(np.concatenate(values)) for values in self.node_lists]
        self.cell_indices = [
            [np.searchsorted(self.nodes[a], values) for values in self.node_lists[a]]
            for a in range(3)
        ]
        self.cache_key, self.core_values = None, None
        self.costs = dict(
            setup=perf_counter() - started,
            core_evaluation=0.0,
            contraction=0.0,
            moments=0.0,
            core_cotangent=0.0,
            core_backward=0.0,
            cache_hash=0.0,
        )
        self.counts = dict(
            forward=0, VJP=0, cache_builds=0, cache_hits=0, backward_microbatches=0
        )
        self.static_bytes = (
            sum(v.nbytes for v in self.nodes)
            + sum(v.nbytes for vals in self.cell_indices for v in vals)
            + sum(
                sum(v.nbytes for v in p["weights"]) + p["coefficients"].nbytes
                for p in self.plans
                if not p["raw"]
            )
        )
        self.dynamic_bytes = 0
        self.block_metadata = {}
        self.share_entity_integrals = share_entity_integrals
        self.shared_definitions = {}

    def _shared_definition(self, permutation):
        """Merge bitwise-identical one-dimensional linear functionals only.

        Each original entity still contributes all its polynomial coefficients.
        Endpoint evaluations and Gauss moments share a small local tensor; this
        does not merge close coordinates or discard small coefficients.
        """
        key = tuple(permutation)
        if key in self.shared_definitions:
            return self.shared_definitions[key]
        weights, dictionaries, definitions = [], [], []
        for phys in range(3):
            ref = int(np.flatnonzero(permutation == phys)[0])
            weights.append([])
            dictionaries.append({})
            definitions.append(ref)
        mappings = []
        for plan in self.plans:
            ids = []
            for phys, ref in enumerate(definitions):
                node_ids = np.searchsorted(self.ref_axes[ref], plan["axes"][ref])
                selected = []
                for original in plan["weights"][ref]:
                    row = np.zeros(len(self.ref_axes[ref]), dtype=np.float64)
                    row[node_ids] = original
                    # Exact bytes, including signed zeros, define reuse.
                    token = row.tobytes()
                    if token not in dictionaries[phys]:
                        dictionaries[phys][token] = len(weights[phys])
                        weights[phys].append(row)
                    selected.append(dictionaries[phys][token])
                ids.append(np.asarray(selected))
            mappings.append(ids)
        W = [np.asarray(rows) for rows in weights]
        coefficients = np.zeros(
            (self.packet["owner_rows"].shape[1], 3, *(len(w) for w in W)),
            dtype=np.complex128,
        )
        for plan, ids in zip(self.plans, mappings, strict=True):
            original = plan["coefficients"].transpose(
                0, 1, *[2 + ref for ref in definitions]
            )
            coefficients[np.ix_(plan["rows"], np.arange(3), *ids)] = original
        self.static_bytes += coefficients.nbytes + sum(w.nbytes for w in W)
        self.shared_definitions[key] = (W, coefficients)
        return W, coefficients

    def _shared_integrated_block(self, cells, values):
        key = ("shared", tuple(cells))
        if key not in self.block_metadata:
            W, C = self._shared_definition(self.cell_plans[cells[0]][1])
            indices, scatter = [], []
            for phys in range(3):
                ids = np.asarray([self.cell_indices[phys][c] for c in cells])
                unique, inverse = np.unique(ids.ravel(), return_inverse=True)
                S = sparse.csr_matrix(
                    (np.ones(ids.size), (inverse, np.arange(ids.size))),
                    shape=(len(unique), ids.size),
                )
                indices.append(ids)
                scatter.append((unique, S))
                self.static_bytes += (
                    ids.nbytes
                    + unique.nbytes
                    + S.data.nbytes
                    + S.indices.nbytes
                    + S.indptr.nbytes
                )
            self.block_metadata[key] = (W, C, indices, scatter)
        W, C, indices, scatter = self.block_metadata[key]
        cores = [
            contract("pn,cnsij->cpsij", w, values[a][ids])
            for a, (w, ids) in enumerate(zip(W, indices, strict=True))
        ]
        return cores, C, (W, scatter)

    def invalidate(self):
        self.cache_key, self.core_values = None, None

    def _cores(self, model):
        if any(v.dtype != torch.float64 for v in model.state_dict().values()):
            raise ValueError("FTT_FLOAT64_PARAMETERS_AND_BUFFERS_REQUIRED")
        began = perf_counter()
        key = model_identity(model)
        self.costs["cache_hash"] += perf_counter() - began
        if key != self.cache_key:
            began = perf_counter()
            values = []
            with torch.no_grad():
                for a, nodes in enumerate(self.nodes):
                    normalized = (
                        torch.from_numpy(nodes) - model.center[a]
                    ) / model.half_width[a]
                    chunks = [
                        model.core(a, normalized[s : s + self.point_batch]).numpy()
                        for s in range(0, len(nodes), self.point_batch)
                    ]
                    values.append(np.concatenate(chunks))
            self.core_values, self.cache_key = values, key
            self.dynamic_bytes = sum(v.nbytes for v in values)
            if self.static_bytes + 2 * self.dynamic_bytes > 2**30:
                raise MemoryError("FTT_NEW_CACHE_AD_PLANNING_LIMIT")
            self.counts["cache_builds"] += 1
            self.costs["core_evaluation"] += perf_counter() - began
        else:
            self.counts["cache_hits"] += 1
        return self.core_values

    def _integrated(self, cell, plan, values):
        _, perm = self.cell_plans[cell]
        cores = []
        for phys in range(3):
            ref = int(np.flatnonzero(perm == phys)[0])
            idx = np.searchsorted(self.ref_axes[ref], plan["axes"][ref])
            ids = self.cell_indices[phys][cell][idx]
            cores.append(
                np.einsum("pn,nsij->psij", plan["weights"][ref], values[phys][ids])
            )
        # Polynomial axes must follow physical X Y Z order, not reference order.
        C = plan["coefficients"].transpose(
            0, 1, *[2 + int(np.flatnonzero(perm == a)[0]) for a in range(3)]
        )
        return cores, C

    def _integrated_block(self, cells, plan, values):
        key = (tuple(cells), int(plan["rows"][0]))
        if key not in self.block_metadata:
            perm = self.cell_plans[cells[0]][1]
            indices = []
            scatter = []
            weights = []
            for phys in range(3):
                ref = int(np.flatnonzero(perm == phys)[0])
                idx = np.searchsorted(self.ref_axes[ref], plan["axes"][ref])
                ids = np.asarray([self.cell_indices[phys][c][idx] for c in cells])
                unique, inverse = np.unique(ids.ravel(), return_inverse=True)
                S = sparse.csr_matrix(
                    (np.ones(ids.size), (inverse, np.arange(ids.size))),
                    shape=(len(unique), ids.size),
                )
                scatter.append((unique, S))
                indices.append(ids)
                weights.append(plan["weights"][ref])
                self.static_bytes += (
                    ids.nbytes
                    + unique.nbytes
                    + S.data.nbytes
                    + S.indices.nbytes
                    + S.indptr.nbytes
                )
            C = plan["coefficients"].transpose(
                0, 1, *[2 + int(np.flatnonzero(perm == a)[0]) for a in range(3)]
            )
            self.block_metadata[key] = (weights, C, indices, scatter)
        weights, C, indices, scatter = self.block_metadata[key]
        cores = [
            contract("pn,cnsij->cpsij", w, values[a][ids])
            for a, (w, ids) in enumerate(zip(weights, indices, strict=True))
        ]
        return cores, C, (weights, scatter)

    def _blocks(self, batch):
        for start in range(0, self.nc, batch):
            cells = list(range(start, min(start + batch, self.nc)))
            aligned = all(
                self.cell_plans[c][0]
                and np.array_equal(self.cell_plans[c][1], self.cell_plans[cells[0]][1])
                for c in cells
            )
            if aligned and not any(p["raw"] for p in self.plans):
                yield cells, True
            else:
                for c in cells:
                    yield [c], False

    def _raw_values(self, cell, model_values):
        p = self.packet
        coords = p["origins"][cell] + p["reference_points"] @ p["jacobians"][cell].T
        cores = [
            model_values[a][np.searchsorted(self.nodes[a], coords[:, a])]
            for a in range(3)
        ]
        return (
            np.einsum("nsij,nsjk,nskl->nsil", *cores, optimize=True)[:, :, 0, 0],
            cores,
            coords,
        )

    def forward(self, model, batch=8):
        if batch not in (1, 8):
            raise ValueError("ONLY_BATCH_1_8")
        self.counts["forward"] += 1
        values = self._cores(model)
        out = np.empty(self.size, dtype=np.complex128)
        p = self.packet
        for cells, fast in self._blocks(batch):
            if fast:
                began = perf_counter()
                J = p["jacobians"][cells]
                local = np.zeros((len(cells), p["owner_rows"].shape[1]), complex)
                prepared = (
                    [self._shared_integrated_block(cells, values)]
                    if self.share_entity_integrals
                    else [
                        self._integrated_block(cells, plan, values)
                        for plan in self.plans
                    ]
                )
                for index, (cores, C, _) in enumerate(prepared):
                    F = contract("cpsij,cqsjk,crskl->cpqrsil", *cores)[..., 0, 0]
                    moments = contract("rtpqs,cpqsa->crta", C, F)
                    value = contract("crta,cat->cr", moments, J)
                    if self.share_entity_integrals:
                        local[:] = value
                    else:
                        local[:, self.plans[index]["rows"]] = value
                self.costs["contraction"] += perf_counter() - began
                began = perf_counter()
                oriented = contract(
                    "cij,cj->ci", p["transforms"][p["orientation_ids"][cells]], local
                )
                rows = p["owner_rows"][cells]
                out[rows[rows >= 0]] = oriented[rows >= 0]
                self.costs["moments"] += perf_counter() - began
                continue
            cell = cells[0]
            began = perf_counter()
            J = p["jacobians"][cell]
            local = np.zeros(p["owner_rows"].shape[1], complex)
            aligned, _ = self.cell_plans[cell]
            if not aligned:
                vals, _, _ = self._raw_values(cell, values)
                local = self.interpolation @ (vals @ J).T.ravel()
            else:
                raw_vals = None
                for plan in self.plans:
                    if plan["raw"]:
                        # Preserve unsupported polynomial rows by exact summation.
                        coords = p["origins"][cell] + p["reference_points"] @ J.T
                        with torch.no_grad():
                            if raw_vals is None:
                                raw_vals = model(torch.from_numpy(coords)).numpy()
                        local[plan["rows"]] = (
                            self.interpolation[plan["rows"]] @ (raw_vals @ J).T.ravel()
                        )
                    else:
                        cores, C = self._integrated(cell, plan, values)
                        moments = np.einsum(
                            "rtpqs,pqsa->rta", C, core_product(cores), optimize=True
                        )
                        local[plan["rows"]] = np.einsum("rta,at->r", moments, J)
            self.costs["contraction"] += perf_counter() - began
            began = perf_counter()
            T = p["transforms"][p["orientation_ids"][cell]]
            oriented = T @ local
            rows = p["owner_rows"][cell]
            out[rows[rows >= 0]] = oriented[rows >= 0]
            self.costs["moments"] += perf_counter() - began
        if not np.isfinite(out).all():
            raise ValueError("NONFINITE_FTT_COMPLETE_MOMENTS")
        return out

    def vjp(self, model, dual, batch=8):
        if batch not in (1, 8):
            raise ValueError("ONLY_BATCH_1_8")
        if dual.dtype != np.complex128 or dual.shape != (self.size,):
            raise ValueError("COMPLETE_COMPLEX128_COTANGENT_REQUIRED")
        self.counts["VJP"] += 1
        values = self._cores(model)
        dvalues = [np.zeros_like(v) for v in values]
        model.zero_grad(set_to_none=True)
        p = self.packet
        for cells, fast in self._blocks(batch):
            if fast:
                began = perf_counter()
                rows = p["owner_rows"][cells]
                loc = np.zeros(rows.shape, complex)
                loc[rows >= 0] = dual[rows[rows >= 0]]
                T = p["transforms"][p["orientation_ids"][cells]]
                loc = contract("cij,ci->cj", T.conj(), loc)
                J = p["jacobians"][cells]
                prepared = (
                    [self._shared_integrated_block(cells, values)]
                    if self.share_entity_integrals
                    else [
                        self._integrated_block(cells, plan, values)
                        for plan in self.plans
                    ]
                )
                for index, (cores, C, (weights, scatter)) in enumerate(prepared):
                    selected_dual = (
                        loc
                        if self.share_entity_integrals
                        else loc[:, self.plans[index]["rows"]]
                    )
                    dF = contract(
                        "rtpqs,cr,cat->cpqsa", C.conj(), selected_dual, J.conj()
                    )
                    X, Y, Z = cores
                    ds = [
                        contract(
                            "cpqrs,cqsjk,crskl->cpsjl", dF, Y.conj(), Z.conj()
                        ).transpose(0, 1, 2, 4, 3),
                        contract("cpqrs,cpsij,crskl->cqsjk", dF, X.conj(), Z.conj()),
                        contract("cpqrs,cpsij,cqsjk->crski", dF, X.conj(), Y.conj()),
                    ]
                    for phys in range(3):
                        expanded = contract("pn,cpsij->cnsij", weights[phys], ds[phys])
                        unique, S = scatter[phys]
                        accumulated = S @ expanded.reshape(
                            expanded.shape[0] * expanded.shape[1], -1
                        )
                        dvalues[phys][unique] += accumulated.reshape(
                            len(unique), *expanded.shape[2:]
                        )
                self.costs["core_cotangent"] += perf_counter() - began
                continue
            cell = cells[0]
            began = perf_counter()
            rows = p["owner_rows"][cell]
            loc = np.zeros(len(rows), complex)
            loc[rows >= 0] = dual[rows[rows >= 0]]
            T = p["transforms"][p["orientation_ids"][cell]]
            loc = T.conj().T @ loc
            J = p["jacobians"][cell]
            aligned, perm = self.cell_plans[cell]
            if not aligned:
                pointdual = (self.interpolation.conj().T @ loc).reshape(
                    3, self.nq
                ).T @ J.conj().T
                _, cs, coords = self._raw_values(cell, values)
                X, Y, Z = cs
                ds = [
                    np.einsum(
                        "ns,nsjk,nskl->nsjl", pointdual, Y.conj(), Z.conj()
                    ).transpose(0, 1, 3, 2),
                    np.einsum("ns,nsij,nskl->nsjk", pointdual, X.conj(), Z.conj()),
                    np.einsum("ns,nsij,nsjk->nski", pointdual, X.conj(), Y.conj()),
                ]
                for a in range(3):
                    np.add.at(
                        dvalues[a], np.searchsorted(self.nodes[a], coords[:, a]), ds[a]
                    )
            else:
                for plan in self.plans:
                    if plan["raw"]:
                        coords = p["origins"][cell] + p["reference_points"] @ J.T
                        pointdual = (
                            self.interpolation[plan["rows"]].conj().T
                            @ loc[plan["rows"]]
                        ).reshape(3, self.nq).T @ J.conj().T
                        for start in range(0, len(coords), self.point_batch):
                            sl = slice(start, start + self.point_batch)
                            v = model(torch.from_numpy(coords[sl]))
                            torch.real(
                                torch.vdot(
                                    torch.from_numpy(pointdual[sl]).ravel(), v.ravel()
                                )
                            ).backward()
                    else:
                        cores, C = self._integrated(cell, plan, values)
                        dF = np.einsum(
                            "rtpqs,r,at->pqsa",
                            C.conj(),
                            loc[plan["rows"]],
                            J.conj(),
                            optimize=True,
                        )
                        ds = core_product_adjoint(cores, dF)
                        for phys in range(3):
                            ref = int(np.flatnonzero(perm == phys)[0])
                            idx = np.searchsorted(self.ref_axes[ref], plan["axes"][ref])
                            ids = self.cell_indices[phys][cell][idx]
                            expanded = np.einsum(
                                "pn,psij->nsij", plan["weights"][ref], ds[phys]
                            )
                            np.add.at(dvalues[phys], ids, expanded)
            self.costs["core_cotangent"] += perf_counter() - began
        began = perf_counter()
        for a, nodes in enumerate(self.nodes):
            for start in range(0, len(nodes), self.point_batch):
                sl = slice(start, start + self.point_batch)
                v = model.core(
                    a,
                    (torch.from_numpy(nodes[sl]) - model.center[a])
                    / model.half_width[a],
                )
                torch.real(
                    torch.vdot(torch.from_numpy(dvalues[a][sl]).ravel(), v.ravel())
                ).backward()
                self.counts["backward_microbatches"] += 1
                del v
        self.costs["core_backward"] += perf_counter() - began
        gradient = (
            torch.cat([p.grad.ravel() for p in model.parameters()])
            .detach()
            .numpy()
            .copy()
        )
        if not np.isfinite(gradient).all():
            raise ValueError("NONFINITE_FTT_PARAMETER_GRADIENT")
        return gradient
