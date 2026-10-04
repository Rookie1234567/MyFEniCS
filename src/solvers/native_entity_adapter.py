"""Complete-entity decoder and its conjugate dual, with bounded workspaces.

These IDs are native mesh entities. Target moment rows are a separate
canonical boundary protocol, not a target DOLFINx p6 dofmap.
"""

import numpy as np

from src.constraints.high_order_floquet_trace import (
    edge_coefficient_transform,
    face_coefficient_transform,
)
from src.solvers.native_entity_protocol import OwnerEntityRouter


def entity_transform(dimension, permutation):
    p = tuple(map(int, permutation))
    if dimension == 1:
        return np.asarray(
            edge_coefficient_transform(
                6, reversed_orientation=p != (0, 1), cell_type="hexahedron"
            ),
            np.complex128,
        )
    if dimension != 2:
        raise ValueError("complete edge or face")
    return np.asarray(face_coefficient_transform(6, p), np.complex128)


def inverse_entity_transform(dimension, permutation):
    p = tuple(map(int, permutation))
    inverse = tuple(int(i) for i in np.argsort(p))
    return entity_transform(dimension, inverse)


class CompleteEntityAdapter:
    def __init__(
        self, comm, owned_ids, requested_ids, owners, phases, permutations, dimension
    ):
        self.dimension = dimension
        self.moments = 6 if dimension == 1 else 60
        self.router = OwnerEntityRouter(
            comm, owned_ids, requested_ids, owners, self.moments
        )
        self.phases = np.asarray(phases, np.complex128)
        self.permutations = np.asarray(permutations, np.int8)
        if self.phases.shape != (len(requested_ids),) or len(self.permutations) != len(
            requested_ids
        ):
            raise ValueError("entity phase/direction coverage")
        self.transforms = {
            tuple(p): entity_transform(dimension, p)
            for p in np.unique(self.permutations, axis=0)
        }
        self.inverses = {
            p: inverse_entity_transform(dimension, p) for p in self.transforms
        }
        for p, transform in self.transforms.items():
            if (
                np.linalg.norm(self.inverses[p] @ transform - np.eye(self.moments))
                > 1e-10
            ):
                raise ValueError("p6 entity inverse direction")

    def extract(self, owned_canonical):
        values = self.router.extract(owned_canonical)
        # One complete entity at a time; no 882-by84 direction buffer or
        # all-nnz repeat/multiply array is needed.
        for i, p in enumerate(self.permutations):
            values[i] = self.phases[i] * (self.transforms[tuple(p)] @ values[i])
        return values

    def canonical_from_physical(self, values):
        out = np.empty_like(values)
        for i, p in enumerate(self.permutations):
            out[i] = (self.inverses[tuple(p)] @ values[i]) / self.phases[i]
        return out

    def physical_dual_from_canonical(self, values):
        """Adjoint of canonical_from_physical, not adjoint of extract."""
        out = np.empty_like(values)
        for i, p in enumerate(self.permutations):
            out[i] = (self.inverses[tuple(p)].conjugate().T @ values[i]) / self.phases[
                i
            ].conjugate()
        return out

    def scatter_into(self, physical_dual, owned_canonical_dual):
        values = np.empty_like(physical_dual)
        for i, p in enumerate(self.permutations):
            values[i] = self.phases[i].conjugate() * (
                self.transforms[tuple(p)].conjugate().T @ physical_dual[i]
            )
        return self.router.scatter_into(values, owned_canonical_dual)


def boundary_rows(keys, shape, dimension):
    """V38 canonical boundary row identity, bottom then top, full moments."""
    nx, ny, nz = map(int, shape)
    n = 6 if dimension == 1 else 60
    keys = np.asarray(keys, np.int64)
    if (
        np.any((keys[:, 4] != 0) & (keys[:, 4] != nz))
        or np.any(keys[:, 0] != dimension)
        or np.any(keys[:, 2] >= nx)
        or np.any(keys[:, 3] >= ny)
    ):
        raise ValueError("canonical top/bottom master entity")
    side = (keys[:, 4] == nz).astype(np.int64)
    offset = side * (72 * nx * ny)
    index = keys[:, 2] * ny + keys[:, 3]
    if dimension == 1:
        if np.any(keys[:, 1] > 1):
            raise ValueError("vertical edge is not tangential boundary")
        offset += keys[:, 1] * (6 * nx * ny) + index * 6
    else:
        if np.any(keys[:, 1] != 2):
            raise ValueError("nonhorizontal face is not DtN boundary")
        offset += 12 * nx * ny + index * 60
    return offset[:, None] + np.arange(n, dtype=np.int64)
