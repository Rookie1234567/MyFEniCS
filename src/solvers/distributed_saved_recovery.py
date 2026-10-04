"""Finite owner consumer of immutable native tensors and affine recovery.

Producer MPI1 row IDs are a saved coordinate system, not current native IDs.
Each row is assigned the owner of its actual consumer entity. Only requested
MPC masters cross ranks. A separate native bridge checks these coordinates.
This finite carrier must never be used to allocate a target-wide row table.
"""

from time import perf_counter

import numpy as np
from scipy.linalg import lu_solve

from src.solvers.native_entity_protocol import OwnerEntityRouter


def native_transfer(element, producer_info, consumer_info):
    """Physical coefficient map T_consumer^-T T_producer^T, no factorization."""
    t = np.eye(element.dim, dtype=np.float64)
    element.T_apply(t.ravel(), element.dim, int(producer_info))
    transfer = np.ascontiguousarray(t.T)
    element.Tt_inv_apply(transfer.ravel(), element.dim, int(consumer_info))
    return transfer


def create_distributed_patch(description, cfg, comm):
    """Only recreate the authorized eight-hex native numbering/MPC bridge."""
    import basix.ufl
    import ufl
    from dolfinx import fem, mesh

    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import _mark_boundary_facets

    points, lookup, cells = [], {}, []
    for cell in description["cells"]:
        ids = []
        for z in cell["bounds_nm"][2]:
            for y in cell["bounds_nm"][1]:
                for x in cell["bounds_nm"][0]:
                    key = (x, y, z)
                    if key not in lookup:
                        lookup[key] = len(points)
                        points.append(key)
                    ids.append(lookup[key])
        cells.append(ids)
    if len(cells) != 8:
        raise ValueError("only the frozen eight-cell recovery witness")
    coords = np.asarray(points, np.float64) if comm.rank == 0 else np.empty((0, 3))
    rows = np.asarray(cells, np.int64) if comm.rank == 0 else np.empty((0, 8), np.int64)
    domain = ufl.Mesh(basix.ufl.element("Lagrange", "hexahedron", 1, shape=(3,)))
    msh = mesh.create_mesh(
        comm,
        rows,
        domain,
        coords,
        partitioner=mesh.create_cell_partitioner(mesh.GhostMode.shared_facet),
    )
    tags, facets = _mark_boundary_facets(msh, cfg)
    from types import SimpleNamespace

    V = fem.functionspace(msh, basix.ufl.element("N1curl", "hexahedron", 6))
    mpc = build_double_floquet_mpc(
        V, SimpleNamespace(mesh=msh, facet_tags=tags, boundary_facets=facets), cfg
    ).mpc
    msh.topology.create_entity_permutations()
    return V, mpc


def native_bridge(V, mpc, literal):
    """Match actual cells by unrounded coordinates; derive actual row owners."""
    from mpi4py import MPI

    comm = V.mesh.comm
    top = V.mesh.topology.index_map(3)
    nc = top.size_local + top.num_ghosts
    points = V.mesh.geometry.x[V.mesh.geometry.dofmap[:nc]]
    old_points = literal["coordinates"][literal["geometry_dofmap"]]
    old_bounds = np.stack((old_points.min(axis=1), old_points.max(axis=1)), axis=2)
    bounds = np.stack((points.min(axis=1), points.max(axis=1)), axis=2)
    ids = []
    for b in bounds:
        found = np.flatnonzero(np.all(old_bounds == b, axis=(1, 2)))
        if len(found) != 1:
            raise ValueError("exact producer/consumer cell geometry identity")
        ids.append(int(found[0]))
    ids = np.asarray(ids, np.int64)
    # No replacement reference-vertex order is silently accepted.
    if not np.array_equal(points, old_points[ids]):
        raise ValueError("native reference vertex ordering changed")
    dm = mpc.function_space.dofmap.index_map
    native_owners = np.r_[np.full(dm.size_local, comm.rank, np.int32), dm.owners]
    dofs = np.asarray([V.dofmap.cell_dofs(c) for c in range(nc)], np.int32)
    n = int(literal["master_offsets"].size - 1)
    if n > 10000 or dm.size_global != n:
        raise ValueError("finite producer storage inventory")
    owner_min, owner_max = np.full(n, comm.size, np.int32), np.full(n, -1, np.int32)
    for c, old in enumerate(ids):
        r = literal["cell_dofs"][old]
        np.minimum.at(owner_min, r, native_owners[dofs[c]])
        np.maximum.at(owner_max, r, native_owners[dofs[c]])
    low, high = np.empty_like(owner_min), np.empty_like(owner_max)
    comm.Allreduce(owner_min, low, op=MPI.MIN)
    comm.Allreduce(owner_max, high, op=MPI.MAX)
    if np.any(low != high) or np.any(high < 0):
        raise ValueError("producer row has missing/inconsistent actual native owner")
    counts = np.zeros(8, np.int32)
    np.add.at(counts, ids[: top.size_local], 1)
    if not np.array_equal(comm.allreduce(counts), np.ones(8, np.int32)):
        raise ValueError("every owned cell must contribute exactly once")
    permutation = V.mesh.topology.get_cell_permutation_info()[:nc].copy()
    transfers = [
        native_transfer(V.element.basix_element, literal["permutations"][old], info)
        for old, info in zip(ids, permutation, strict=True)
    ]
    from src.solvers.distributed_entity_volume import cell_transform

    return {
        "producer_cells": ids,
        "owned_cells": top.size_local,
        "producer_owner": high,
        "native_dofs": dofs,
        "consumer_permutations": permutation,
        "transfer": transfers,
        "native_transforms": [
            cell_transform(V.element.basix_element, int(p)) for p in permutation
        ],
        "native_ids": dm.local_to_global(np.arange(len(native_owners), dtype=np.int32)),
        "native_owners": native_owners,
    }


class SavedRecoveryConsumer:
    def __init__(self, comm, literal, numbering, classes, bridge, C, D):
        self.comm, self.literal, self.numbering = comm, literal, numbering
        self.classes, self.bridge = classes, bridge
        self.owned_ids = np.flatnonzero(bridge["producer_owner"] == comm.rank)
        cells = bridge["producer_cells"][: bridge["owned_cells"]]
        offsets, masters = literal["master_offsets"], literal["master_rows"]
        requested = np.unique(
            np.concatenate(
                [
                    masters[offsets[int(r)] : offsets[int(r) + 1]]
                    for c in cells
                    for r in literal["cell_dofs"][c]
                ]
            )
        )
        self.requested = requested
        self.router = OwnerEntityRouter(
            comm, self.owned_ids, requested, bridge["producer_owner"][requested], 1
        )
        lookup = {int(r): i for i, r in enumerate(requested)}
        self.maps = []
        for c in cells:
            indices, coefficients = [], []
            for r in literal["cell_dofs"][c]:
                lo, hi = offsets[r : r + 2]
                indices.append(np.asarray([lookup[int(m)] for m in masters[lo:hi]]))
                coefficients.append(
                    literal["master_dual_coefficients"][lo:hi].conjugate()
                )
            self.maps.append((indices, coefficients))
        self.C, self.D = C[self.owned_ids], D[:, self.owned_ids]
        if C.shape[1] != 12 or D.shape != (12, len(bridge["producer_owner"])):
            raise ValueError("complete frozen twelve-port carrier")
        interiors = numbering["cell_interior"]
        if np.any(C[interiors]) or np.any(D[:, interiors]):
            raise ValueError("this anchor requires original trace-only port support")
        self.calls = {"forward": 0, "adjoint": 0, "recover": 0, "local_solve": 0}
        self.seconds = dict.fromkeys(self.calls, 0.0)

    def expand_cells(self, owned):
        q = self.router.extract(np.asarray(owned, np.complex128).reshape(-1, 1)).ravel()
        return [
            np.asarray([coef @ q[ix] for ix, coef in zip(i, v, strict=True)])
            for i, v in self.maps
        ]

    def pull_cells(self, values):
        local = np.zeros(len(self.requested), np.complex128)
        for (indices, coefficients), value in zip(self.maps, values, strict=True):
            for ix, coefficient, v in zip(indices, coefficients, value, strict=True):
                np.add.at(local, ix, coefficient.conjugate() * v)
        owned = np.zeros((len(self.owned_ids), 1), np.complex128)
        self.router.scatter_into(local[:, None], owned)
        return owned.ravel()

    def apply_original(self, owned, *, adjoint=False, coupled=False):
        kind = "adjoint" if adjoint else "forward"
        self.calls[kind] += 1
        began = perf_counter()
        physical = self.expand_cells(owned)
        values = []
        for j, u in enumerate(physical):
            c = int(self.bridge["producer_cells"][j])
            a = self.classes[int(self.numbering["cell_class"][c])]["raw_tensor"]
            m = self.bridge["transfer"][j]
            t = self.bridge["native_transforms"][j]
            # Current native coefficients and dual, not an old MPI1 action.
            raw = t.T @ (m @ u)
            native_force = t @ ((a.conjugate().T if adjoint else a) @ raw)
            values.append(m.conjugate().T @ native_force)
        result = self.pull_cells(values)
        if coupled:
            if adjoint:
                modal = self.comm.allreduce(self.C.conjugate().T @ owned)
                result += self.D.conjugate().T @ modal
            else:
                modal = self.comm.allreduce(self.D @ owned)
                result += self.C @ modal
        self.seconds[kind] += perf_counter() - began
        return result

    def recover(self, reduced, full_rhs):
        began = perf_counter()
        self.calls["recover"] += 1
        active = self.numbering["owned_active"]
        trace = np.zeros(len(self.bridge["producer_owner"]), np.complex128)
        trace[active] = reduced[: len(active)]
        owned = trace[self.owned_ids].copy()
        physical = self.expand_cells(owned)
        lookup = {int(r): i for i, r in enumerate(self.owned_ids)}
        for j, local in enumerate(physical):
            c = int(self.bridge["producer_cells"][j])
            a = self.classes[int(self.numbering["cell_class"][c])]
            ii, tt = self.numbering["cell_interior"][c], self.numbering["cell_trace"][c]
            tp = a["trace_positions"]
            ui = (
                lu_solve((a["lu"], a["pivots"]), full_rhs[ii])
                + a["recovery"] @ local[tp]
            )
            self.calls["local_solve"] += 1
            owned[[lookup[int(r)] for r in ii]] = ui
            if not np.array_equal(self.literal["cell_dofs"][c, tp], tt):
                raise ValueError("saved trace positions/cell coordinate pairing")
        self.seconds["recover"] += perf_counter() - began
        return owned

    def reduced_rhs(self, full_rhs, port_rhs):
        corrections = []
        for c in self.bridge["producer_cells"][: self.bridge["owned_cells"]]:
            a = self.classes[int(self.numbering["cell_class"][c])]
            local = np.zeros(a["original"].shape[0], np.complex128)
            local[a["trace_positions"]] = (
                a["rhs_trace"] @ full_rhs[self.numbering["cell_interior"][c]]
            )
            corrections.append(local)
        owned = full_rhs[self.owned_ids] + self.pull_cells(corrections)
        active = self.numbering["owned_active"]
        result = np.zeros(len(active) + 12, np.complex128)
        match = {int(r): i for i, r in enumerate(active)}
        for r, value in zip(self.owned_ids, owned, strict=True):
            if int(r) in match:
                result[match[int(r)]] = value
        result = self.comm.allreduce(result)
        result[len(active) :] = port_rhs
        return result
