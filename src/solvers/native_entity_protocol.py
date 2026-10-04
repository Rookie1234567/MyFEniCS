"""Complete structured entities, owner routing and bounded dual scatter.

Keys describe actual coordinate-axis vertices, never native full-p6 row IDs.
All moments of one entity have one owner; periodic corner normalization is
done once. Only requested complete entities are exchanged by all-to-all.
"""

import numpy as np


def entity_keys(coordinates, vertices, axes, dimension):
    """Vectorized exact vertex-to-axis lookup, without rounded class keys."""
    points = np.asarray(coordinates)[np.asarray(vertices)]
    lattice = np.empty(points.shape, np.int64)
    for a, grid in enumerate(axes):
        ids = np.searchsorted(grid, points[:, :, a])
        if np.any(ids >= len(grid)) or not np.array_equal(
            np.asarray(grid)[ids], points[:, :, a]
        ):
            raise ValueError("native coordinate absent from frozen exact axes")
        lattice[:, :, a] = ids
    lo, hi = lattice.min(axis=1), lattice.max(axis=1)
    changed = hi != lo
    if not np.all(changed.sum(axis=1) == dimension) or np.any(hi - lo > 1):
        raise ValueError("complete affine grid entity")
    direction = np.argmax(changed if dimension == 1 else ~changed, axis=1)
    return np.column_stack((np.full(len(lo), dimension), direction, lo)).astype(
        np.int64
    )


def periodic_master(keys, shape, phases):
    keys = np.asarray(keys, np.int64)
    master = keys.copy()
    weights = np.ones(len(keys), np.complex128)
    for a in (0, 1):
        # Edges varying along a cannot lie wholly on the max plane.
        boundary = (keys[:, 2 + a] == shape[a]) & (
            (keys[:, 0] == 2) | (keys[:, 1] != a)
        )
        master[boundary, 2 + a] = 0
        weights[boundary] *= phases[a]
    return master, weights


def key_owner_directory(comm, owned_keys, owned_ids, requested_keys):
    """Distributed complete-entity lookup; only needed periodic entities route.

    The directory receives native entity records, not moment-row dictionaries.
    Integer IDs/owners are actual mesh data. No trace allgather is used.
    """

    def bucket(key):
        return int(sum((i + 3) * int(v) for i, v in enumerate(key)) % comm.size)

    send = [[] for _ in range(comm.size)]
    for key, gid in zip(owned_keys, owned_ids, strict=True):
        send[bucket(key)].append((tuple(map(int, key)), int(gid), comm.rank))
    incoming = comm.alltoall(send)
    directory = {}
    for rows in incoming:
        for key, gid, owner in rows:
            if key in directory:
                raise ValueError("duplicate native entity owner")
            directory[key] = (gid, owner)
    request = [[] for _ in range(comm.size)]
    for i, key in enumerate(requested_keys):
        request[bucket(key)].append((i, tuple(map(int, key))))
    incoming_requests = comm.alltoall(request)
    responses = [[] for _ in range(comm.size)]
    bad = 0
    for rank, rows in enumerate(incoming_requests):
        for i, key in rows:
            if key not in directory:
                bad += 1
            else:
                responses[rank].append((i, *directory[key]))
    if comm.allreduce(bad):
        raise ValueError("missing periodic master entity")
    result = np.full((len(requested_keys), 2), -1, np.int64)
    for rows in comm.alltoall(responses):
        for i, gid, owner in rows:
            result[i] = (gid, owner)
    if np.any(result < 0):
        raise ValueError("owner response coverage")
    return result


class OwnerEntityRouter:
    """Caller-owned entity buffers; communicate whole 6/60-moment blocks."""

    def __init__(self, comm, owned_ids, requested_ids, requested_owners, moments):
        self.comm = comm
        self.owned_ids = np.asarray(owned_ids, np.int64)
        self.requested_ids = np.asarray(requested_ids, np.int64)
        self.requested_owners = np.asarray(requested_owners, np.int64)
        self.moments = int(moments)
        if (
            len(np.unique(self.owned_ids)) != len(self.owned_ids)
            or self.requested_ids.shape != self.requested_owners.shape
            or np.any(self.requested_owners < 0)
            or np.any(self.requested_owners >= comm.size)
        ):
            raise ValueError("owner complete entity inventory")
        send = [[] for _ in range(comm.size)]
        for i, (gid, owner) in enumerate(
            zip(self.requested_ids, self.requested_owners, strict=True)
        ):
            send[int(owner)].append((i, int(gid)))
        self.incoming = comm.alltoall(send)
        self.lookup = {int(gid): i for i, gid in enumerate(self.owned_ids)}
        bad = sum(gid not in self.lookup for rows in self.incoming for _, gid in rows)
        if comm.allreduce(bad):
            raise ValueError("route uses wrong native owner")

    def extract(self, owned):
        owned = np.asarray(owned)
        if (
            owned.shape != (len(self.owned_ids), self.moments)
            or owned.dtype != np.complex128
        ):
            raise ValueError("owned entity buffer shape")
        send = [
            [(i, owned[self.lookup[gid]].copy()) for i, gid in rows]
            for rows in self.incoming
        ]
        out = np.empty((len(self.requested_ids), self.moments), np.complex128)
        for rows in self.comm.alltoall(send):
            for i, values in rows:
                out[i] = values
        return out

    def scatter_into(self, values, target):
        values = np.asarray(values)
        if (
            values.shape != (len(self.requested_ids), self.moments)
            or values.dtype != np.complex128
        ):
            raise ValueError("entity dual buffer shape")
        if (
            target.shape != (len(self.owned_ids), self.moments)
            or target.dtype != np.complex128
        ):
            raise ValueError("caller-owned dual target")
        send = [[] for _ in range(self.comm.size)]
        for gid, owner, value in zip(
            self.requested_ids, self.requested_owners, values, strict=True
        ):
            send[int(owner)].append((int(gid), value.copy()))
        for rows in self.comm.alltoall(send):
            for gid, value in rows:
                target[self.lookup[gid]] += value
        return target


def structured_counts(shape):
    x, y, z = map(int, shape)
    return {
        "cells": x * y * z,
        "vertices": (x + 1) * (y + 1) * (z + 1),
        "edges": x * (y + 1) * (z + 1) + (x + 1) * y * (z + 1) + (x + 1) * (y + 1) * z,
        "faces": (x + 1) * y * z + x * (y + 1) * z + x * y * (z + 1),
        "boundary_faces": 2 * x * y + 2 * x * z + 2 * y * z,
    }


def canonical_values(keys, moments, seed):
    """Deterministic general complex complete-entity witness, MPI invariant."""
    k = np.asarray(keys, np.float64)
    n = np.arange(moments, dtype=np.float64)[None, :]
    a = k @ np.array([1.17, 0.31, 0.73, 0.19, 0.47])
    return np.ascontiguousarray(
        np.sin(a[:, None] + n * 0.37 + seed * 0.013)
        + 1j * np.cos(a[:, None] * 0.83 + n * 0.61 + seed * 0.017),
        np.complex128,
    )
