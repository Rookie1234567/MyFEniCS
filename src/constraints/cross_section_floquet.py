from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from dolfinx import cpp, mesh
from mpi4py import MPI
from petsc4py import PETSc

from ..modes.cross_section_spaces import CrossSectionMesh, CrossSectionSpaces
from .high_order_floquet_trace import (
    _alltoallv_json_records,
    distributed_match_periodic_records,
)


@dataclass(frozen=True)
class CrossSectionFloquetConstraints:
    """Owned mixed-space slave rows with global mixed-space master columns."""

    slave_local: np.ndarray
    slave_global: np.ndarray
    master_global: np.ndarray
    master_owners: np.ndarray
    coefficients: np.ndarray
    offsets: np.ndarray
    phase_x: complex
    phase_y: complex
    transverse_constraint_count: int
    longitudinal_constraint_count: int
    max_pair_coordinate_error: float
    max_probe_residual: float
    communication_scope: str = "distributed_hash_periodic_boundary_entities_only"
    orientation_schema: str = "basix_interval_exact_p1_p6"
    used_full_boundary_gather: bool = False
    created_dense_boundary_square: bool = False
    pairing_bytes_sent: int = 0
    pairing_bytes_received: int = 0


@dataclass(frozen=True)
class DistributedConstraintTransform:
    matrix: PETSc.Mat
    full_global_size: int
    reduced_global_size: int
    full_local_size: int
    reduced_local_size: int
    global_slave_count: int
    ownership_note: str = "PETSc distributed rows; no rank-0 eigenvector gather"


def _global_info(space, dofs: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    dofs = np.asarray(dofs, dtype=np.int64)
    index_map = space.dofmap.index_map
    bs = int(space.dofmap.index_map_bs)
    blocks = dofs // bs
    components = dofs % bs
    global_blocks = index_map.local_to_global(blocks.astype(np.int32)).astype(np.int64)
    global_dofs = global_blocks * bs + components
    owned = blocks < index_map.size_local
    owners = np.empty(len(dofs), dtype=np.int32)
    owners[owned] = space.mesh.comm.rank
    if np.any(~owned):
        ghost_owners = np.asarray(index_map.owners, dtype=np.int32)
        owners[~owned] = ghost_owners[blocks[~owned] - index_map.size_local]
    return global_dofs, owners, owned


def _parent_info(
    spaces: CrossSectionSpaces,
    collapsed_to_mixed: np.ndarray,
    collapsed_dofs: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    parent_local = np.asarray(collapsed_to_mixed, dtype=np.int64)[collapsed_dofs]
    parent_global, parent_owners, parent_owned = _global_info(
        spaces.mixed, parent_local
    )
    return parent_local, parent_global, parent_owners, parent_owned


def _coordinate_key(value: float, tolerance: float) -> int:
    return int(round(float(value) / tolerance))


def _collective_guard(comm, local_errors: list[str], prefix: str) -> None:
    error_count = int(comm.allreduce(len(local_errors), op=MPI.SUM))
    if error_count:
        first_error_rank = int(
            comm.allreduce(
                int(comm.rank) if local_errors else int(comm.size),
                op=MPI.MIN,
            )
        )
        detail = comm.bcast(
            local_errors[0] if int(comm.rank) == first_error_rank else None,
            root=first_error_rank,
        )
        raise RuntimeError(f"{prefix}: global_error_count={error_count}; {detail}.")


def _transverse_entity_dof_map(
    spaces: CrossSectionSpaces,
) -> dict[int, dict[str, object]]:
    """Return Basix entity-ordered N1curl dofs for every local/ghost edge."""

    V = spaces.transverse
    msh = V.mesh
    tdim = msh.topology.dim
    fdim = tdim - 1
    cell_type = msh.basix_cell()
    cell_name = str(getattr(cell_type, "name", cell_type))
    if tdim != 2 or cell_name != "quadrilateral":
        raise NotImplementedError(
            "Exact cross-section Floquet constraints require a quadrilateral mesh."
        )
    if int(spaces.transverse_degree) not in {1, 2, 3, 4, 5, 6}:
        raise ValueError(
            "Exact cross-section N1curl constraints are qualified for p=1..6."
        )

    msh.topology.create_entity_permutations()
    msh.topology.create_connectivity(tdim, fdim)
    cell_to_facet = msh.topology.connectivity(tdim, fdim)
    cell_map = msh.topology.index_map(tdim)
    num_cells = int(cell_map.size_local + cell_map.num_ghosts)
    reference_dofs = [
        np.asarray(V.dofmap.dof_layout.entity_dofs(fdim, local_facet), dtype=np.int32)
        for local_facet in range(4)
    ]
    basix_reference_dofs = [
        np.asarray(
            V.element.basix_element.entity_dofs[fdim][local_facet],
            dtype=np.int32,
        )
        for local_facet in range(4)
    ]
    if any(
        not np.array_equal(dolfinx_dofs, basix_dofs)
        for dolfinx_dofs, basix_dofs in zip(
            reference_dofs, basix_reference_dofs, strict=True
        )
    ):
        raise RuntimeError(
            "DOLFINx and Basix disagree on quadrilateral N1curl edge-entity "
            f"dof ordering for p={spaces.transverse_degree}."
        )
    if any(len(dofs) != int(spaces.transverse_degree) for dofs in reference_dofs):
        raise RuntimeError(
            "Basix/DOLFINx interval entity layout disagrees with the requested "
            f"N1curl degree p={spaces.transverse_degree}."
        )
    interval_transforms = np.asarray(
        V.element.basix_element.entity_transformations()["interval"],
        dtype=np.float64,
    )
    expected_transform_shape = (
        1,
        int(spaces.transverse_degree),
        int(spaces.transverse_degree),
    )
    if interval_transforms.shape != expected_transform_shape:
        raise RuntimeError(
            "Basix quadrilateral N1curl interval transform shape changed: "
            f"observed={interval_transforms.shape}, "
            f"expected={expected_transform_shape}."
        )

    records: dict[int, dict[str, object]] = {}
    for cell in range(num_cells):
        facets = cell_to_facet.links(cell)
        cell_dofs = V.dofmap.cell_dofs(cell)
        if len(facets) != 4:
            raise RuntimeError(
                "A quadrilateral cell must expose four interval entities."
            )
        for local_facet, facet in enumerate(facets):
            collapsed_dofs = np.asarray(
                [int(cell_dofs[int(index)]) for index in reference_dofs[local_facet]],
                dtype=np.int32,
            )
            parent_local, parent_global, parent_owners, parent_owned = _parent_info(
                spaces, spaces.transverse_to_mixed, collapsed_dofs
            )
            record = {
                "facet": int(facet),
                "collapsed_dofs": collapsed_dofs,
                "parent_local": parent_local,
                "parent_global": parent_global,
                "parent_owners": parent_owners,
                "parent_owned": parent_owned,
                "touches_owned_cell": bool(cell < cell_map.size_local),
            }
            current = records.get(int(facet))
            if current is not None and not np.array_equal(
                np.asarray(current["parent_global"], dtype=np.int64), parent_global
            ):
                raise RuntimeError(
                    "DOLFINx returned inconsistent global coefficient ordering "
                    f"for cross-section edge {int(facet)}."
                )
            if current is None:
                records[int(facet)] = record
            else:
                current["touches_owned_cell"] = bool(
                    current["touches_owned_cell"]
                ) or bool(record["touches_owned_cell"])
                if np.any(parent_owned) and not np.any(current["parent_owned"]):
                    record["touches_owned_cell"] = bool(
                        record["touches_owned_cell"]
                    ) or bool(current["touches_owned_cell"])
                    records[int(facet)] = record
    return records


def _transverse_edge_coefficient_transform(
    spaces: CrossSectionSpaces,
    *,
    reversed_orientation: bool,
) -> np.ndarray:
    """Return Basix's exact coefficient map for one cross-section edge."""

    degree = int(spaces.transverse_degree)
    transformations = spaces.transverse.element.basix_element.entity_transformations()
    interval = np.asarray(transformations["interval"][0], dtype=np.float64)
    if interval.shape != (degree, degree):
        raise RuntimeError(
            "Basix quadrilateral N1curl interval transform disagrees with the "
            f"requested degree p={degree}: shape={interval.shape}."
        )
    if not reversed_orientation:
        return np.eye(degree, dtype=np.complex128)
    return np.asarray(interval.T, dtype=np.complex128)


def _local_transverse_records(
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    dof_map: dict[int, dict[str, object]],
    *,
    normal_axis: int,
    side: str,
    tolerance: float,
) -> list[dict[str, object]]:
    msh = cross_section.mesh
    fdim = msh.topology.dim - 1
    boundary_values = (
        cross_section.x_values if normal_axis == 0 else cross_section.y_values
    )
    coordinate = float(boundary_values[0 if side == "min" else -1])
    facets = np.asarray(
        mesh.locate_entities_boundary(
            msh,
            fdim,
            lambda x: np.isclose(x[normal_axis], coordinate, atol=tolerance, rtol=0.0),
        ),
        dtype=np.int32,
    )
    if len(facets) == 0:
        return []
    midpoints = mesh.compute_midpoints(msh, fdim, facets)
    geometry = cpp.mesh.entities_to_geometry(msh._cpp_object, fdim, facets, True)
    records: list[dict[str, object]] = []
    for facet, midpoint, geometry_dofs in zip(facets, midpoints, geometry, strict=True):
        dofs = dof_map.get(int(facet))
        if dofs is None:
            raise RuntimeError(
                f"No exact N1curl entity dof record exists for boundary edge {int(facet)}."
            )
        coordinates = np.asarray(
            msh.geometry.x[np.asarray(geometry_dofs, dtype=np.int64)],
            dtype=np.float64,
        )
        if coordinates.shape[0] != 2:
            raise RuntimeError(
                "Task033 exact interval orientation requires linear edge geometry."
            )
        tangent = np.asarray(coordinates[1] - coordinates[0], dtype=np.float64)
        if float(np.linalg.norm(tangent)) <= 1.0e-30:
            raise RuntimeError("A periodic cross-section edge has a zero tangent.")
        records.append(
            {
                **dofs,
                "midpoint": np.asarray(midpoint, dtype=np.float64),
                "tangent": tangent,
            }
        )
    return records


def _owned_parent_lookup(spaces: CrossSectionSpaces) -> dict[int, int]:
    index_map = spaces.mixed.dofmap.index_map
    bs = int(spaces.mixed.dofmap.index_map_bs)
    if bs != 1:
        raise NotImplementedError("Cross-section mixed-space block size must be one.")
    local = np.arange(index_map.size_local, dtype=np.int32)
    global_dofs = index_map.local_to_global(local).astype(np.int64)
    return {
        int(global_dof): int(local_dof)
        for local_dof, global_dof in zip(local, global_dofs)
    }


def _transverse_axis_constraints(
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    *,
    normal_axis: int,
    phase: complex,
    tolerance: float,
) -> tuple[
    list[tuple[int, int, list[int], list[int], list[complex]]],
    float,
    int,
    int,
]:
    comm = cross_section.mesh.comm
    dof_map = _transverse_entity_dof_map(spaces)
    low = _local_transverse_records(
        cross_section,
        spaces,
        dof_map,
        normal_axis=normal_axis,
        side="min",
        tolerance=tolerance,
    )
    high = _local_transverse_records(
        cross_section,
        spaces,
        dof_map,
        normal_axis=normal_axis,
        side="max",
        tolerance=tolerance,
    )
    span = float(
        (cross_section.x_values[-1] - cross_section.x_values[0])
        if normal_axis == 0
        else (cross_section.y_values[-1] - cross_section.y_values[0])
    )
    tangent_axis = 1 - normal_axis
    packets: list[dict] = []
    slaves_by_token: dict[str, dict[str, object]] = {}
    for role, records in (("master", low), ("slave", high)):
        for record in records:
            midpoint = np.asarray(record["midpoint"], dtype=np.float64)
            canonical = midpoint.copy()
            if role == "slave":
                canonical[normal_axis] -= span
            token = f"t:{normal_axis}:{int(record['facet'])}"
            if role == "slave":
                if token in slaves_by_token:
                    raise RuntimeError(
                        f"Duplicate local transverse slave token {token}."
                    )
                slaves_by_token[token] = record
            packets.append(
                {
                    "pair_key": [
                        1,
                        normal_axis + 1,
                        _coordinate_key(float(canonical[0]), tolerance),
                        _coordinate_key(float(canonical[1]), tolerance),
                        tangent_axis,
                    ],
                    "role": role,
                    "global_dofs": [
                        int(value)
                        for value in np.asarray(record["parent_global"], dtype=np.int64)
                    ],
                    "owners": [
                        int(value)
                        for value in np.asarray(record["parent_owners"], dtype=np.int32)
                    ],
                    "owns_any": bool(np.any(record["parent_owned"])),
                    "reply_rank": int(comm.rank),
                    "token": token,
                    "midpoint": [float(value) for value in midpoint],
                    "tangent": [
                        float(value)
                        for value in np.asarray(record["tangent"], dtype=np.float64)
                    ],
                }
            )

    replies, metrics = distributed_match_periodic_records(comm, packets)
    replies_by_token = {str(reply["token"]): reply for reply in replies}
    local_errors: list[str] = []
    if len(replies_by_token) != len(replies):
        local_errors.append("duplicate distributed transverse pairing replies")
    if set(replies_by_token) != set(slaves_by_token):
        local_errors.append("reply tokens disagree with local transverse slave tokens")
    _collective_guard(comm, local_errors, "Exact transverse Floquet pairing failed")

    rows: list[tuple[int, int, list[int], list[int], list[complex]]] = []
    max_pair_error = 0.0
    for token, record in slaves_by_token.items():
        master = replies_by_token[token]["master"]
        target = np.asarray(record["midpoint"], dtype=np.float64).copy()
        target[normal_axis] -= span
        master_midpoint = np.asarray(master["midpoint"], dtype=np.float64)
        pair_error = float(np.linalg.norm(target - master_midpoint))
        max_pair_error = max(max_pair_error, pair_error)
        if pair_error > 10.0 * tolerance:
            raise RuntimeError(
                "Exact transverse Floquet pair exceeds coordinate tolerance: "
                f"axis={normal_axis}, token={token}, error={pair_error:.3e}."
            )
        tangent = np.asarray(record["tangent"], dtype=np.float64)
        master_tangent = np.asarray(master["tangent"], dtype=np.float64)
        tangent_dot = float(np.dot(tangent, master_tangent))
        tangent_norm = float(np.linalg.norm(tangent) * np.linalg.norm(master_tangent))
        if tangent_norm <= 1.0e-30 or abs(tangent_dot) / tangent_norm < 0.99:
            raise RuntimeError(
                "Paired cross-section interval tangents are not collinear."
            )
        transform = _transverse_edge_coefficient_transform(
            spaces,
            reversed_orientation=tangent_dot < 0.0,
        )
        slave_global = np.asarray(record["parent_global"], dtype=np.int64)
        slave_local = np.asarray(record["parent_local"], dtype=np.int64)
        slave_owned = np.asarray(record["parent_owned"], dtype=bool)
        master_global = np.asarray(master["global_dofs"], dtype=np.int64)
        master_owners = np.asarray(master["owners"], dtype=np.int32)
        if transform.shape != (len(slave_global), len(master_global)):
            raise RuntimeError(
                "Basix interval transform shape disagrees with paired entity dofs."
            )
        for row_index, is_owned in enumerate(slave_owned):
            if not bool(is_owned):
                continue
            row_coefficients = phase * transform[row_index]
            cutoff = max(
                1.0e-14,
                1.0e-13 * float(np.max(np.abs(row_coefficients), initial=0.0)),
            )
            selected = np.flatnonzero(np.abs(row_coefficients) > cutoff)
            if len(selected) == 0:
                raise RuntimeError("An exact Basix interval row has no nonzero master.")
            rows.append(
                (
                    int(slave_local[row_index]),
                    int(slave_global[row_index]),
                    [int(value) for value in master_global[selected]],
                    [int(value) for value in master_owners[selected]],
                    [complex(value) for value in row_coefficients[selected]],
                )
            )
    max_pair_error = float(comm.allreduce(max_pair_error, op=MPI.MAX))
    return rows, max_pair_error, int(metrics.bytes_sent), int(metrics.bytes_received)


def _longitudinal_constraints(
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    *,
    phase_x: complex,
    phase_y: complex,
    tolerance: float,
) -> tuple[
    list[tuple[int, int, list[int], list[int], list[complex]]],
    float,
    int,
    int,
]:
    Vz = spaces.longitudinal
    comm = cross_section.mesh.comm
    coordinates = np.asarray(Vz.tabulate_dof_coordinates(), dtype=np.float64)
    all_local = np.arange(len(coordinates), dtype=np.int32)
    parent_local, parent_global, parent_owners, parent_owned = _parent_info(
        spaces, spaces.longitudinal_to_mixed, all_local
    )

    x_min, x_max = cross_section.x_values[[0, -1]]
    y_min, y_max = cross_section.y_values[[0, -1]]

    length_x = float(x_max - x_min)
    length_y = float(y_max - y_min)
    phase_by_kind = {
        "x": complex(phase_x),
        "y": complex(phase_y),
        "corner": complex(phase_x) * complex(phase_y),
    }
    code_by_kind = {"x": 1, "y": 2, "corner": 3}
    packets: list[dict] = []
    slaves_by_token: dict[str, dict[str, object]] = {}
    for dof, coordinate in enumerate(coordinates):
        on_x_min = bool(np.isclose(coordinate[0], x_min, atol=tolerance, rtol=0.0))
        on_x_max = bool(np.isclose(coordinate[0], x_max, atol=tolerance, rtol=0.0))
        on_y_min = bool(np.isclose(coordinate[1], y_min, atol=tolerance, rtol=0.0))
        on_y_max = bool(np.isclose(coordinate[1], y_max, atol=tolerance, rtol=0.0))
        specifications: list[tuple[str, str]] = []
        if on_x_min and not on_y_max:
            specifications.append(("x", "master"))
        if on_y_min and not on_x_max:
            specifications.append(("y", "master"))
        if on_x_min and on_y_min:
            specifications.append(("corner", "master"))
        if on_x_max and on_y_max:
            specifications.append(("corner", "slave"))
        elif on_x_max:
            specifications.append(("x", "slave"))
        elif on_y_max:
            specifications.append(("y", "slave"))

        for kind, role in specifications:
            canonical = np.asarray(coordinate, dtype=np.float64).copy()
            if role == "slave":
                if kind in {"x", "corner"}:
                    canonical[0] -= length_x
                if kind in {"y", "corner"}:
                    canonical[1] -= length_y
            token = f"l:{kind}:{dof}"
            if role == "slave":
                if token in slaves_by_token:
                    raise RuntimeError(
                        f"Duplicate local longitudinal slave token {token}."
                    )
                slaves_by_token[token] = {
                    "kind": kind,
                    "coordinate": np.asarray(coordinate, dtype=np.float64),
                    "parent_local": int(parent_local[dof]),
                    "parent_global": int(parent_global[dof]),
                    "parent_owner": int(parent_owners[dof]),
                    "parent_owned": bool(parent_owned[dof]),
                }
            packets.append(
                {
                    "pair_key": [
                        0,
                        code_by_kind[kind],
                        _coordinate_key(float(canonical[0]), tolerance),
                        _coordinate_key(float(canonical[1]), tolerance),
                    ],
                    "role": role,
                    "global_dofs": [int(parent_global[dof])],
                    "owners": [int(parent_owners[dof])],
                    "owns_any": bool(parent_owned[dof]),
                    "reply_rank": int(comm.rank),
                    "token": token,
                    # Hash/signature coordinate: ghost copies may differ by a
                    # final floating-point bit.  Keep the unrounded coordinate
                    # separately for the geometric error gate below.
                    "midpoint": [
                        float(_coordinate_key(float(value), tolerance) * tolerance)
                        for value in coordinate
                    ],
                    "actual_coordinate": [float(value) for value in coordinate],
                }
            )

    replies, metrics = distributed_match_periodic_records(comm, packets)
    replies_by_token = {str(reply["token"]): reply for reply in replies}
    local_errors: list[str] = []
    if len(replies_by_token) != len(replies):
        local_errors.append("duplicate distributed longitudinal pairing replies")
    if set(replies_by_token) != set(slaves_by_token):
        local_errors.append(
            "reply tokens disagree with local longitudinal slave tokens"
        )
    _collective_guard(comm, local_errors, "Exact longitudinal Floquet pairing failed")

    rows: list[tuple[int, int, list[int], list[int], list[complex]]] = []
    max_pair_error = 0.0
    for token, record in slaves_by_token.items():
        master = replies_by_token[token]["master"]
        kind = str(record["kind"])
        target = np.asarray(record["coordinate"], dtype=np.float64).copy()
        if kind in {"x", "corner"}:
            target[0] -= length_x
        if kind in {"y", "corner"}:
            target[1] -= length_y
        master_coordinate = np.asarray(master["actual_coordinate"], dtype=np.float64)
        pair_error = float(np.linalg.norm(target - master_coordinate))
        max_pair_error = max(max_pair_error, pair_error)
        if pair_error > 10.0 * tolerance:
            raise RuntimeError(
                "Exact longitudinal Floquet pair exceeds coordinate tolerance: "
                f"kind={kind}, token={token}, error={pair_error:.3e}."
            )
        if not bool(record["parent_owned"]):
            continue
        master_global = np.asarray(master["global_dofs"], dtype=np.int64)
        master_owner = np.asarray(master["owners"], dtype=np.int32)
        if len(master_global) != 1 or len(master_owner) != 1:
            raise RuntimeError("A scalar periodic pair must expose one master dof.")
        rows.append(
            (
                int(record["parent_local"]),
                int(record["parent_global"]),
                [int(master_global[0])],
                [int(master_owner[0])],
                [phase_by_kind[kind]],
            )
        )
    max_pair_error = float(comm.allreduce(max_pair_error, op=MPI.MAX))
    return rows, max_pair_error, int(metrics.bytes_sent), int(metrics.bytes_received)


def _distributed_owner_lookup(
    spaces: CrossSectionSpaces,
    masters: np.ndarray,
    owners: np.ndarray,
    *,
    owned_values: dict[int, int],
    local_slaves: set[int],
    context: str,
) -> tuple[dict[int, int], int, int]:
    """Resolve owner-held values and reject slave masters without global maps."""

    comm = spaces.mixed.mesh.comm
    if len(masters) != len(owners):
        raise ValueError("Master dofs and owner arrays have different lengths.")
    owner_by_master: dict[int, int] = {}
    local_errors: list[str] = []
    for master, owner in zip(masters, owners, strict=True):
        master_int = int(master)
        owner_int = int(owner)
        if not 0 <= owner_int < int(comm.size):
            local_errors.append(f"invalid owner {owner_int} for master {master_int}")
            continue
        previous = owner_by_master.setdefault(master_int, owner_int)
        if previous != owner_int:
            local_errors.append(
                f"conflicting owners {previous}/{owner_int} for master {master_int}"
            )
    _collective_guard(comm, local_errors, f"{context} owner declarations failed")

    request_buckets: list[list[dict]] = [[] for _ in range(int(comm.size))]
    for master, owner in sorted(owner_by_master.items()):
        request_buckets[owner].append(
            {
                "master": master,
                "request_rank": int(comm.rank),
            }
        )
    received, first_sent, first_received = _alltoallv_json_records(
        comm, request_buckets
    )
    reply_buckets: list[list[dict]] = [[] for _ in range(int(comm.size))]
    for request in received:
        master = int(request["master"])
        if master in local_slaves:
            status = "slave_chain"
            value = -1
        elif master not in owned_values:
            status = "not_owned_by_declared_rank"
            value = -1
        else:
            status = "ok"
            value = int(owned_values[master])
        reply_buckets[int(request["request_rank"])].append(
            {
                "master": master,
                "status": status,
                "value": value,
            }
        )
    replies, second_sent, second_received = _alltoallv_json_records(comm, reply_buckets)
    resolved: dict[int, int] = {}
    local_errors = []
    for reply in replies:
        master = int(reply["master"])
        status = str(reply["status"])
        if status != "ok":
            local_errors.append(f"master {master}: {status}")
            continue
        if master in resolved and resolved[master] != int(reply["value"]):
            local_errors.append(f"master {master}: conflicting owner values")
            continue
        resolved[master] = int(reply["value"])
    missing = set(owner_by_master) - set(resolved)
    if missing and not local_errors:
        local_errors.append(f"missing replies for masters {sorted(missing)[:5]}")
    _collective_guard(comm, local_errors, f"{context} distributed owner query failed")
    return (
        resolved,
        int(first_sent + second_sent),
        int(first_received + second_received),
    )


def build_cross_section_floquet_constraints(
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    *,
    kx: float,
    ky: float,
) -> CrossSectionFloquetConstraints:
    """Build exact p1--p6 double-periodic constraints on the mixed space.

    Boundary entities are hash-routed to pairing ranks and replied only to
    contributing slave ranks.  No boundary-sized global map or probe fit is
    constructed.
    """

    length_x = float(cross_section.x_values[-1] - cross_section.x_values[0])
    length_y = float(cross_section.y_values[-1] - cross_section.y_values[0])
    phase_x = complex(np.exp(1j * kx * length_x))
    phase_y = complex(np.exp(1j * ky * length_y))
    tolerance = 1.0e-11 * max(length_x, length_y, 1.0)

    transverse_x, pair_x, sent_x, received_x = _transverse_axis_constraints(
        cross_section,
        spaces,
        normal_axis=0,
        phase=phase_x,
        tolerance=tolerance,
    )
    transverse_y, pair_y, sent_y, received_y = _transverse_axis_constraints(
        cross_section,
        spaces,
        normal_axis=1,
        phase=phase_y,
        tolerance=tolerance,
    )
    longitudinal, pair_z, sent_z, received_z = _longitudinal_constraints(
        cross_section,
        spaces,
        phase_x=phase_x,
        phase_y=phase_y,
        tolerance=tolerance,
    )
    rows = transverse_x + transverse_y + longitudinal
    rows.sort(key=lambda row: row[1])

    slave_local: list[int] = []
    slave_global: list[int] = []
    master_global: list[int] = []
    master_owners: list[int] = []
    coefficients: list[complex] = []
    offsets = [0]
    for local, global_dof, masters, owners, row_coefficients in rows:
        slave_local.append(local)
        slave_global.append(global_dof)
        master_global.extend(masters)
        master_owners.extend(owners)
        coefficients.extend(row_coefficients)
        offsets.append(len(master_global))

    comm = cross_section.mesh.comm
    local_slave_set = {int(value) for value in slave_global}
    owned_parent = _owned_parent_lookup(spaces)
    local_errors: list[str] = []
    if len(local_slave_set) != len(slave_global):
        local_errors.append("duplicate locally owned mixed-space slave rows")
    for local, global_dof in zip(slave_local, slave_global, strict=True):
        if owned_parent.get(int(global_dof)) != int(local):
            local_errors.append(
                f"slave {int(global_dof)} is not owned at mixed local row {int(local)}"
            )
            break
    _collective_guard(comm, local_errors, "Cross-section slave ownership failed")
    _, owner_sent, owner_received = _distributed_owner_lookup(
        spaces,
        np.asarray(master_global, dtype=np.int64),
        np.asarray(master_owners, dtype=np.int32),
        owned_values=owned_parent,
        local_slaves=local_slave_set,
        context="Cross-section master-to-slave chain veto",
    )

    local_sent = sent_x + sent_y + sent_z + owner_sent
    local_received = received_x + received_y + received_z + owner_received
    global_sent = int(comm.allreduce(local_sent, op=MPI.SUM))
    global_received = int(comm.allreduce(local_received, op=MPI.SUM))

    return CrossSectionFloquetConstraints(
        slave_local=np.asarray(slave_local, dtype=np.int32),
        slave_global=np.asarray(slave_global, dtype=np.int64),
        master_global=np.asarray(master_global, dtype=np.int64),
        master_owners=np.asarray(master_owners, dtype=np.int32),
        coefficients=np.asarray(coefficients, dtype=np.complex128),
        offsets=np.asarray(offsets, dtype=np.int32),
        phase_x=phase_x,
        phase_y=phase_y,
        transverse_constraint_count=len(transverse_x) + len(transverse_y),
        longitudinal_constraint_count=len(longitudinal),
        max_pair_coordinate_error=max(pair_x, pair_y, pair_z),
        max_probe_residual=0.0,
        pairing_bytes_sent=global_sent,
        pairing_bytes_received=global_received,
    )


def build_distributed_constraint_transform(
    spaces: CrossSectionSpaces,
    constraints: CrossSectionFloquetConstraints,
) -> DistributedConstraintTransform:
    """Create the distributed full-to-free map ``u = C q`` without root gather."""

    V = spaces.mixed
    comm = V.mesh.comm
    index_map = V.dofmap.index_map
    if int(V.dofmap.index_map_bs) != 1:
        raise NotImplementedError(
            "The QEP constraint transform currently requires block size one."
        )
    full_local = int(index_map.size_local)
    full_global = int(index_map.size_global)
    ownership_start, ownership_end = map(int, index_map.local_range)
    local_slaves = {int(value) for value in constraints.slave_global}
    local_errors: list[str] = []
    if len(local_slaves) != len(constraints.slave_global):
        local_errors.append("duplicate locally owned slave rows")
    outside = sorted(
        slave for slave in local_slaves if not ownership_start <= slave < ownership_end
    )
    if outside:
        local_errors.append(f"non-owned slave rows {outside[:5]}")
    _collective_guard(comm, local_errors, "Constraint transform slave audit failed")

    free_globals = [
        global_dof
        for global_dof in range(ownership_start, ownership_end)
        if global_dof not in local_slaves
    ]
    reduced_local = len(free_globals)
    prefix = comm.exscan(reduced_local, op=MPI.SUM)
    reduced_start = 0 if prefix is None else int(prefix)
    owned_free_reduced = {
        int(global_dof): int(reduced_start + local_index)
        for local_index, global_dof in enumerate(free_globals)
    }
    reduced_global = int(comm.allreduce(reduced_local, op=MPI.SUM))
    global_slave_count = int(comm.allreduce(len(local_slaves), op=MPI.SUM))
    if reduced_global != full_global - global_slave_count:
        raise RuntimeError(
            "Distributed free-dof numbering does not conserve the full-space size."
        )
    reduced_master, _, _ = _distributed_owner_lookup(
        spaces,
        constraints.master_global,
        constraints.master_owners,
        owned_values=owned_free_reduced,
        local_slaves=local_slaves,
        context="Constraint transform reduced-index lookup",
    )

    C = PETSc.Mat().createAIJ(
        size=((full_local, full_global), (reduced_local, reduced_global)),
        nnz=max(1, int(max(np.diff(constraints.offsets), default=1))),
        comm=comm,
    )
    C.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)
    local_constraint_rows = {
        int(slave): row for row, slave in enumerate(constraints.slave_global)
    }
    for global_row in range(ownership_start, ownership_end):
        constraint_row = local_constraint_rows.get(global_row)
        if constraint_row is None:
            C.setValue(global_row, owned_free_reduced[global_row], 1.0)
            continue
        start = int(constraints.offsets[constraint_row])
        stop = int(constraints.offsets[constraint_row + 1])
        columns = [
            reduced_master[int(master)]
            for master in constraints.master_global[start:stop]
        ]
        C.setValues(
            [global_row],
            columns,
            constraints.coefficients[start:stop][None, :],
        )
    C.assemble()
    return DistributedConstraintTransform(
        matrix=C,
        full_global_size=full_global,
        reduced_global_size=reduced_global,
        full_local_size=full_local,
        reduced_local_size=reduced_local,
        global_slave_count=global_slave_count,
        ownership_note=(
            "Owned free rows use rank-local order plus MPI exscan; remote master "
            "columns are resolved by owner query; no global slave map"
        ),
    )


def reduce_matrix_hermitian(
    matrix: PETSc.Mat,
    transform: PETSc.Mat,
    *,
    transform_h: PETSc.Mat | None = None,
) -> PETSc.Mat:
    """Return ``C^H A C`` using distributed PETSc sparse products."""

    product = matrix.matMult(transform)
    owns_transpose = transform_h is None
    if transform_h is None:
        transform_h = PETSc.Mat()
        transform.hermitianTranspose(transform_h)
    reduced = transform_h.matMult(product)
    product.destroy()
    if owns_transpose:
        transform_h.destroy()
    return reduced
