"""Bounded native geometry/topology extraction, without full-p6 target space."""

from time import perf_counter

import numpy as np

from src.solvers.native_entity_protocol import (
    entity_keys,
    key_owner_directory,
    periodic_master,
)


def create_structured_mesh(axes, comm, *, relabel=False, keep_partition=False):
    """Preallocated input arrays, no per-target-cell Python tuple/list mesh."""
    import basix.ufl
    import ufl
    from dolfinx import graph, mesh

    began = perf_counter()
    nx, ny, nz = (len(a) - 1 for a in axes)
    points = np.empty(((nx + 1) * (ny + 1) * (nz + 1), 3), np.float64)
    ids = np.arange(len(points), dtype=np.int64)
    points[:, 0] = axes[0][ids % (nx + 1)]
    points[:, 1] = axes[1][(ids // (nx + 1)) % (ny + 1)]
    points[:, 2] = axes[2][ids // ((nx + 1) * (ny + 1))]
    if keep_partition:
        cells_ids = np.arange(nx * ny * nz, dtype=np.int64)
        cells_ids = cells_ids[cells_ids % nx % comm.size == comm.rank]
    else:
        lo, hi = (
            nx * ny * nz * comm.rank // comm.size,
            nx * ny * nz * (comm.rank + 1) // comm.size,
        )
        cells_ids = np.arange(lo, hi, dtype=np.int64)
    ix, iy, iz = cells_ids % nx, (cells_ids // nx) % ny, cells_ids // (nx * ny)
    base = iz * (ny + 1) * (nx + 1) + iy * (nx + 1) + ix
    offsets = np.array(
        [
            0,
            1,
            nx + 1,
            nx + 2,
            (nx + 1) * (ny + 1),
            (nx + 1) * (ny + 1) + 1,
            (nx + 1) * (ny + 1) + nx + 1,
            (nx + 1) * (ny + 1) + nx + 2,
        ],
        np.int64,
    )
    cells = base[:, None] + offsets
    if relabel:
        # A single legal input-label permutation, identical geometry/reference
        # cell vertex order. Only the global native vertex labels change.
        labels = np.random.default_rng(424113).permutation(len(points))
        revised = np.empty_like(points)
        revised[labels] = points
        points, cells = revised, labels[cells]
    input_bytes = points.nbytes + cells.nbytes + cells_ids.nbytes + ids.nbytes
    domain = ufl.Mesh(basix.ufl.element("Lagrange", "hexahedron", 1, shape=(3,)))
    if keep_partition:

        def partitioner(_comm, partitions, adjacency, _ghost):
            if partitions != comm.size:
                raise ValueError("input partition identity")
            return graph.adjacencylist(
                np.full((adjacency.num_nodes, 1), comm.rank, np.int32)
            )._cpp_object

        part = mesh.create_cell_partitioner(partitioner, mesh.GhostMode.shared_facet)
    else:
        part = mesh.create_cell_partitioner(mesh.GhostMode.shared_facet)
    msh = mesh.create_mesh(comm, cells, domain, points, partitioner=part)
    costs = {
        "input_simultaneous_explicit_bytes": int(input_bytes),
        "geometry_build_seconds": perf_counter() - began,
        "p6_space_constructed": False,
        "form_JIT": 0,
        "LU": 0,
    }
    del points, cells, cells_ids, ids, base, ix, iy, iz
    return msh, costs


def topology_packet(msh, axes, phases, *, block=4096):
    from dolfinx import cpp, mesh

    t = msh.topology
    began = perf_counter()
    for d in (1, 2):
        t.create_entities(d)
        t.create_connectivity(d, 0)
        t.create_connectivity(3, d)
        t.create_connectivity(d, 3)
    t.create_entity_permutations()
    shape = tuple(len(a) - 1 for a in axes)
    out, sizes, workspace = {}, {}, 0
    for d, nv in ((1, 2), (2, 4)):
        imap = t.index_map(d)
        n = imap.size_local + imap.num_ghosts
        keys = np.empty((n, 5), np.int64)
        permutations = np.empty((n, nv), np.int8)
        native_vertices = np.empty((n, nv), np.int64)
        for lo in range(0, n, block):
            rows = np.arange(lo, min(lo + block, n), dtype=np.int32)
            geom = np.asarray(
                cpp.mesh.entities_to_geometry(msh._cpp_object, d, rows, True)
            )
            keys[lo : lo + len(rows)] = entity_keys(msh.geometry.x, geom, axes, d)
            xyz = msh.geometry.x[geom]
            low, high = xyz.min(axis=1), xyz.max(axis=1)
            if d == 1:
                axis = keys[lo : lo + len(rows), 1]
                perm = np.zeros((len(rows), 2), np.int8)
                perm[:, 0] = (
                    xyz[np.arange(len(rows)), 0, axis]
                    == high[np.arange(len(rows)), axis]
                )
                perm[:, 1] = 1 - perm[:, 0]
            else:
                normal = keys[lo : lo + len(rows), 1]
                perm = np.zeros((len(rows), 4), np.int8)
                for a in range(3):
                    other = np.array([q for q in range(3) if q != a])
                    hit = normal == a
                    perm[hit] = (
                        xyz[hit, :, other[0]] == high[hit, other[0], None]
                    ).astype(np.int8) + 2 * (
                        xyz[hit, :, other[1]] == high[hit, other[1], None]
                    ).astype(np.int8)
            if not np.all(np.sort(perm, axis=1) == np.arange(nv)):
                raise ValueError("native entity vertex permutation is not bijective")
            permutations[lo : lo + len(rows)] = perm
            native_vertices[lo : lo + len(rows)] = msh.geometry.input_global_indices[
                geom
            ]
            workspace = max(
                workspace,
                int(
                    geom.nbytes
                    + xyz.nbytes
                    + low.nbytes
                    + high.nbytes
                    + perm.nbytes
                    + rows.nbytes
                ),
            )
        ids = imap.local_to_global(np.arange(n, dtype=np.int32)).astype(np.int64)
        owner = np.r_[np.full(imap.size_local, msh.comm.rank, np.int32), imap.owners]
        master, phase = periodic_master(keys, shape, phases)
        periodic = np.any(master != keys, axis=1)
        on_seam = (
            (keys[:, 2] == 0)
            | (keys[:, 2] == shape[0])
            | (keys[:, 3] == 0)
            | (keys[:, 3] == shape[1])
        )
        owned_seam = np.flatnonzero(on_seam & (np.arange(n) < imap.size_local))
        req = np.flatnonzero(periodic)
        route = key_owner_directory(
            msh.comm, keys[owned_seam], ids[owned_seam], master[req]
        )
        master_ids, master_owners = ids.copy(), owner.copy()
        master_ids[req], master_owners[req] = route[:, 0], route[:, 1]
        for name, a in (
            ("keys", keys),
            ("native_ids", ids),
            ("owners", owner),
            ("vertex_ids", native_vertices),
            ("vertex_permutations", permutations),
            ("master_keys", master),
            ("master_ids", master_ids),
            ("master_owners", master_owners),
            ("phase", phase),
        ):
            out[f"entity{d}_{name}"] = np.asarray(a)
        # This is the topology IndexMap's actual vertex numbering, distinct
        # from geometry.input_global_indices exported as vertex_ids above.
        vertices = np.asarray(t.connectivity(d, 0).array, np.int32).reshape(n, nv)
        out[f"entity{d}_topology_vertex_global_ids"] = (
            t.index_map(0)
            .local_to_global(vertices.ravel())
            .reshape(n, nv)
            .astype(np.int64)
        )
        sizes[str(d)] = {
            "owned": int(imap.size_local),
            "ghost": int(imap.num_ghosts),
            "global": int(imap.size_global),
            "periodic_owned": int(periodic[: imap.size_local].sum()),
            "cross_rank_periodic_owned": int(
                np.sum(
                    periodic[: imap.size_local]
                    & (master_owners[: imap.size_local] != msh.comm.rank)
                )
            ),
        }
    cmap = t.index_map(3)
    ncell = cmap.size_local + cmap.num_ghosts
    out["cell_permutations"] = np.asarray(
        t.get_cell_permutation_info()[:ncell], np.uint32
    )
    out["cell_native_ids"] = cmap.local_to_global(
        np.arange(ncell, dtype=np.int32)
    ).astype(np.int64)
    out["cell_vertices"] = np.asarray(msh.geometry.dofmap[:ncell], np.int32)
    out["coordinates"] = msh.geometry.x.copy()
    sizes["3"] = {
        "owned": int(cmap.size_local),
        "ghost": int(cmap.num_ghosts),
        "global": int(cmap.size_global),
    }
    sizes["0"] = {
        "owned": int(t.index_map(0).size_local),
        "ghost": int(t.index_map(0).num_ghosts),
        "global": int(t.index_map(0).size_global),
    }
    for d in (1, 2):
        con = t.connectivity(3, d)
        out[f"cell_entity{d}"] = (
            np.asarray(con.array, np.int32).reshape(ncell, 12 if d == 1 else 6).copy()
        )
    out["boundary_facets"] = mesh.exterior_facet_indices(t).astype(np.int32)
    return out, {
        "entity_sizes": sizes,
        "topology_extract_seconds": perf_counter() - began,
        "bounded_geometry_workspace_measured_payload": workspace,
        "packet_array_payload": sum(a.nbytes for a in out.values()),
        "MPI_size": msh.comm.size,
        "rank": msh.comm.rank,
        "producer_numbering": "ACTUAL_NATIVE_MESH_ENTITY_GLOBAL_IDS",
        "consumer_numbering": "STRUCTURED_CANONICAL_ENTITY_AND_MOMENT_PREFIX_PROTOCOL",
        "full_target_p6_native_ids": "NOT_CONSTRUCTED",
        "vertex_identity": {
            "vertex_ids": "actual geometry.input_global_indices in transformed geometry order",
            "topology_vertex_global_ids": "actual topology vertex IndexMap global IDs in connectivity order",
        },
    }


def raw_classes(msh, packet, tags):
    """Exact IEEE width/tag + actual native orientation class counts/users."""
    n = msh.topology.index_map(3).size_local
    raw, oriented = {}, {}
    cell_class = np.empty(n, np.int32)
    for lo in range(0, n, 4096):
        xyz = packet["coordinates"][packet["cell_vertices"][lo : min(lo + 4096, n)]]
        widths = xyz.max(axis=1) - xyz.min(axis=1)
        for j, width in enumerate(widths):
            c = lo + j
            key = (int(tags[c]), *[float(v).hex() for v in width])
            if key not in raw:
                raw[key] = {"index": len(raw), "count": 0}
            raw[key]["count"] += 1
            cell_class[c] = raw[key]["index"]
            coords = xyz[j]
            # Native reference geometry order, retained separately from
            # entity coefficient orientation/permutation bitfield.
            relative = tuple(
                map(
                    int,
                    (
                        (coords[:, 0] == coords[:, 0].max()).astype(np.int8)
                        + 2 * (coords[:, 1] == coords[:, 1].max()).astype(np.int8)
                        + 4 * (coords[:, 2] == coords[:, 2].max()).astype(np.int8)
                    ),
                )
            )
            ok = (*key, int(packet["cell_permutations"][c]), relative)
            oriented[ok] = oriented.get(ok, 0) + 1
    packet["cell_raw_class_local"] = cell_class
    packet["cell_tags"] = tags
    return [{"tag": k[0], "width_hex": list(k[1:]), **v} for k, v in raw.items()], [
        {
            "tag": k[0],
            "width_hex": list(k[1:4]),
            "permutation": k[4],
            "native_reference_vertex_order": list(k[5]),
            "count": v,
        }
        for k, v in oriented.items()
    ]


def basis_axis_transform(element, data, info):
    """Independent small entity-generator action on both tensor axes."""
    result = np.array(data, np.complex128, copy=True)
    generators = element.entity_transformations()
    blocks = []
    for i, dofs in enumerate(element.entity_dofs[1]):
        if (int(info) >> (18 + i)) & 1:
            blocks.append((np.asarray(dofs), generators["interval"][0]))
    for i, dofs in enumerate(element.entity_dofs[2]):
        face_info = (int(info) >> (3 * i)) & 7
        transform = np.eye(len(dofs))
        if face_info & 1:
            transform = generators["quadrilateral"][1] @ transform
        for _ in range(face_info >> 1):
            transform = generators["quadrilateral"][0] @ transform
        blocks.append((np.asarray(dofs), transform))
    for ids, transform in blocks:
        result[ids, :] = transform @ result[ids, :]
    for ids, transform in blocks:
        result[:, ids] = result[:, ids] @ transform.T
    return result
