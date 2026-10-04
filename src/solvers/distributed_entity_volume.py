"""Full cell action on caller-owned native witness rows, with exact MPC dual.

Only the finite witness uses native row IDs. The target must use complete
entities; this scalar router is explicitly not a target decoder.
"""

from time import perf_counter

import numpy as np

from src.solvers.native_entity_protocol import OwnerEntityRouter


def cell_transform(element, info):
    """Native basis orientation, including all high-order edge/face moments."""
    t = np.eye(element.dim, dtype=np.float64)
    generators = element.entity_transformations()
    for i, dofs in enumerate(element.entity_dofs[1]):
        if (int(info) >> (18 + i)) & 1:
            ids = np.asarray(dofs)
            t[ids, :] = generators["interval"][0] @ t[ids, :]
    for i, dofs in enumerate(element.entity_dofs[2]):
        fi = (int(info) >> (3 * i)) & 7
        ids = np.asarray(dofs)
        g = np.eye(len(ids))
        if fi & 1:
            g = generators["quadrilateral"][1] @ g
        for _ in range(fi >> 1):
            g = generators["quadrilateral"][0] @ g
        t[ids, :] = g @ t[ids, :]
    return t


class NativeDistributedAction:
    """Owned-cell sum; communication never gathers a complete vector."""

    def __init__(
        self, comm, literal, matrices, class_ids, element, owned_rows, owned_cells
    ):
        self.comm, self.literal = comm, literal
        self.matrices, self.class_ids = matrices, np.asarray(class_ids)
        self.owned_rows, self.owned_cells = int(owned_rows), int(owned_cells)
        gids, owners = literal["actual_dof_global_ids"], literal["actual_dof_owners"]
        self.router = OwnerEntityRouter(comm, gids[:owned_rows], gids, owners, 1)
        self.transforms = {
            int(p): cell_transform(element, int(p))
            for p in np.unique(literal["cell_permutations"][:owned_cells])
        }
        self.calls = {"forward": 0, "adjoint": 0}
        self.seconds = dict.fromkeys(self.calls, 0.0)

    def expand(self, owned):
        u = self.router.extract(np.asarray(owned, np.complex128).reshape(-1, 1)).ravel()
        p = self.literal
        for row in p["slave_local_dofs"]:
            lo, hi = p["MPC_offsets"][row : row + 2]
            u[row] = p["MPC_coefficients"][lo:hi] @ u[p["MPC_masters"][lo:hi]]
        return u

    def pull(self, local):
        p = self.literal
        local = np.asarray(local, np.complex128).copy()
        for row in p["slave_local_dofs"]:
            lo, hi = p["MPC_offsets"][row : row + 2]
            np.add.at(
                local,
                p["MPC_masters"][lo:hi],
                p["MPC_coefficients"][lo:hi].conjugate() * local[row],
            )
            local[row] = 0
        owned = np.zeros((self.owned_rows, 1), np.complex128)
        self.router.scatter_into(local.reshape(-1, 1), owned)
        return owned.ravel()

    def apply_original(self, owned, *, adjoint=False):
        kind = "adjoint" if adjoint else "forward"
        self.calls[kind] += 1
        began = perf_counter()
        physical = self.expand(owned)
        local = np.zeros_like(physical)
        for c in range(self.owned_cells):
            ids = self.literal["cell_native_dofs"][c]
            t = self.transforms[int(self.literal["cell_permutations"][c])]
            a = self.matrices[int(self.class_ids[c])]
            raw = t.T @ physical[ids]
            result = t @ ((a.conjugate().T if adjoint else a) @ raw)
            np.add.at(local, ids, result)
        out = self.pull(local)
        self.seconds[kind] += perf_counter() - began
        return out

    def apply_original_adjoint(self, owned):
        return self.apply_original(owned, adjoint=True)


def affine_internal_recover(
    raw_matrix,
    lu,
    pivots,
    trace_positions,
    interior_positions,
    physical_trace,
    internal_rhs,
    transform,
):
    """Affine particular solution stays unscaled; no global inverse is used."""
    from scipy.linalg import lu_solve

    raw = transform.T @ physical_trace
    rhs = (
        internal_rhs
        - raw_matrix[np.ix_(interior_positions, trace_positions)] @ raw[trace_positions]
    )
    raw[interior_positions] = lu_solve((lu, pivots), rhs)
    return transform @ raw
