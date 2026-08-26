"""Owner-local canonical packets for the qualified hexahedral H(curl) path.

This adapter keeps mesh and constraint extraction beside the pure packet
kernel.  It supports uniform scalar-blocked complex N1curl spaces on
axis-aligned structured affine hexahedra.  Full-FE reconstruction and the
standard physical norm audit are opt-in offline comparator operations.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

import numpy as np
import ufl
from dolfinx import cpp, fem
from dolfinx.la.petsc import create_vector
from mpi4py import MPI
from petsc4py import PETSc

from ..constraints.high_order_floquet_trace import (
    edge_coefficient_transform,
    face_coefficient_transform,
)
from ..geometry.tetra_mesh_audit import (
    canonical_entity_key,
    mesh_coordinate_tolerance,
)
from .hcurl_assembly_time_condensation import (
    AssemblyTimeCondensedSystem,
    _cell_trace_expansion,
)
from .hcurl_canonical_vector import (
    CanonicalKey,
    CanonicalPacket,
    canonical_key,
    canonical_packet,
    canonical_source_coefficient_from_key,
)

__all__ = (
    "iter_canonical_active_trace_packets",
    "iter_canonical_full_fe_packets",
    "iter_canonical_full_fe_dual_packets",
    "extract_canonical_active_trace_packets",
    "extract_canonical_full_fe_packets",
    "extract_canonical_full_fe_dual_packets",
    "build_physical_canonical_primal_source",
    "build_physical_canonical_dual_source",
    "reconstruct_canonical_full_fe_function",
    "reconstruct_canonical_full_fe_dual_vector",
    "compare_hcurl_fields",
)


def _space_data(function_space) -> tuple[int, np.ndarray, np.ndarray]:
    mesh = function_space.mesh
    if "hexahedron" not in str(mesh.basix_cell()).lower():
        raise NotImplementedError("canonical extraction supports affine hexahedra only")
    element = function_space.element.basix_element
    family = str(getattr(element.family, "name", element.family)).lower()
    if family not in {"n1curl", "n1e"}:
        raise NotImplementedError("canonical extraction supports N1curl only")
    if int(function_space.dofmap.index_map_bs) != 1:
        raise NotImplementedError("canonical extraction requires scalar-blocked dofs")
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise NotImplementedError("canonical extraction requires complex128 PETSc")
    degree = int(element.degree)
    trace_positions = np.setdiff1d(
        np.arange(int(function_space.element.space_dimension), dtype=np.int32),
        np.asarray(element.entity_dofs[3][0], dtype=np.int32),
    )
    return (
        degree,
        trace_positions,
        np.asarray(element.entity_dofs[3][0], dtype=np.int32),
    )


def _global_dofs(function_space, local_dofs: np.ndarray) -> np.ndarray:
    local = np.asarray(local_dofs, dtype=np.int32)
    return np.asarray(
        function_space.dofmap.index_map.local_to_global(local), dtype=np.int64
    )


def _topology_data(function_space) -> tuple[Any, np.ndarray, np.ndarray]:
    topology = function_space.mesh.topology
    tdim = topology.dim
    for dimension in (1, 2):
        topology.create_entities(dimension)
        topology.create_connectivity(dimension, tdim)
        topology.create_connectivity(tdim, dimension)
    topology.create_entity_permutations()
    return (
        topology,
        np.asarray(topology.get_cell_permutation_info(), dtype=np.uint32),
        np.asarray([topology.index_map(tdim).size_local], dtype=np.int32),
    )


def _entity_coordinates(function_space, dimension: int, entity: int) -> np.ndarray:
    mesh = function_space.mesh
    geometry = cpp.mesh.entities_to_geometry(
        mesh._cpp_object,
        int(dimension),
        np.asarray([entity], dtype=np.int32),
        True,
    )
    return np.asarray(
        mesh.geometry.x[np.asarray(geometry[0], dtype=np.int64)], dtype=np.float64
    )


def _owned_entity_incidents(
    function_space, dimension: int
) -> tuple[tuple[int, int], ...]:
    topology = function_space.mesh.topology
    entity_map = topology.index_map(int(dimension))
    entity_to_cell = topology.connectivity(int(dimension), topology.dim)
    return tuple(
        (entity, int(entity_to_cell.links(entity)[0]))
        for entity in range(int(entity_map.size_local))
    )


def _cell_local_global_dofs(function_space, cell: int) -> np.ndarray:
    return _global_dofs(
        function_space,
        np.asarray(function_space.dofmap.cell_dofs(int(cell)), dtype=np.int32),
    )


def _scatter_values(
    vector: PETSc.Vec, global_ids: Iterable[int] | np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    indices = np.asarray(
        global_ids if isinstance(global_ids, np.ndarray) else sorted(global_ids),
        dtype=PETSc.IntType,
    )
    source = PETSc.Vec().createSeq(len(indices), comm=PETSc.COMM_SELF)
    global_is = PETSc.IS().createGeneral(indices, comm=PETSc.COMM_SELF)
    local_is = PETSc.IS().createStride(
        len(indices), first=0, step=1, comm=PETSc.COMM_SELF
    )
    scatter = PETSc.Scatter().create(vector, global_is, source, local_is)
    scatter.scatter(
        vector,
        source,
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    values = np.asarray(source.getArray(readonly=True), dtype=np.complex128).copy()
    scatter.destroy()
    local_is.destroy()
    global_is.destroy()
    source.destroy()
    return indices, values


def _entity_canonical_order(coords: np.ndarray, dimension: int, tolerance: float):
    if int(dimension) == 1:
        order = np.lexsort((coords[:, 2], coords[:, 1], coords[:, 0]))
        canonical = coords[order]
        permutation = tuple(
            int(np.flatnonzero(order == i)[0]) for i in range(len(order))
        )
        return canonical, permutation
    spans = np.ptp(coords, axis=0)
    axes = np.flatnonzero(spans > tolerance)
    if len(axes) != 2 or len(coords) != 4:
        raise NotImplementedError("hexahedral face geometry must be quadrilateral")
    u, v = (int(axes[0]), int(axes[1]))
    u0, u1 = float(np.min(coords[:, u])), float(np.max(coords[:, u]))
    v0, v1 = float(np.min(coords[:, v])), float(np.max(coords[:, v]))
    targets = ((u0, v0), (u1, v0), (u0, v1), (u1, v1))
    indices = []
    for target in targets:
        distances = np.linalg.norm(coords[:, (u, v)] - np.asarray(target), axis=1)
        index = int(np.argmin(distances))
        if float(distances[index]) > 10.0 * tolerance:
            raise RuntimeError("face geometry is not an affine quadrilateral")
        indices.append(index)
    canonical = coords[np.asarray(indices, dtype=np.int32)]
    permutation = tuple(
        int(np.flatnonzero(np.asarray(indices) == i)[0]) for i in range(4)
    )
    return canonical, permutation


def _floquet_relations(
    floquet_data,
) -> dict[tuple[int, tuple[tuple[int, ...], ...]], tuple[Any, ...]]:
    if floquet_data is None or floquet_data.phase_independent_topology is None:
        return {}
    phases = {
        "x": complex(floquet_data.phase_x),
        "y": complex(floquet_data.phase_y),
        "corner": complex(floquet_data.phase_corner),
    }
    relations = {}
    for block in floquet_data.phase_independent_topology.blocks:
        slave_key = tuple(
            sorted(
                tuple(int(x) for x in point)
                for point in block.slave_entity_geometry_key
            )
        )
        master_key = tuple(
            sorted(
                tuple(int(x) for x in point)
                for point in block.master_entity_geometry_key
            )
        )
        key = (
            1 if block.entity_kind == "edge" else 2,
            slave_key,
        )
        relations[key] = (
            master_key,
            phases[block.kind],
            ("floquet", block.kind, tuple(int(x) for x in block.periodic_pair_key)),
        )
    return relations


def _physical_entity_transform(
    coords: np.ndarray, dimension: int, degree: int, tolerance: float
) -> tuple[np.ndarray, tuple[str, ...]]:
    _canonical_coords, permutation = _entity_canonical_order(
        coords, dimension, tolerance
    )
    if int(dimension) == 1:
        reversed_orientation = tuple(permutation) != (0, 1)
        transform = edge_coefficient_transform(
            degree, reversed_orientation=reversed_orientation, cell_type="hexahedron"
        )
        state = ("canonical_edge", "lexicographic_xyz", "basix_coefficient_v1")
    else:
        transform = face_coefficient_transform(degree, permutation)
        state = ("canonical_face", "axis_aligned_reference_q1", "basix_coefficient_v1")
    return np.asarray(transform, dtype=np.complex128), state


def _canonical_entity_values(
    values: np.ndarray,
    coords: np.ndarray,
    dimension: int,
    degree: int,
    tolerance: float,
    relations: dict,
):
    physical_key = canonical_entity_key(coords, tolerance)
    transform, _physical_state = _physical_entity_transform(
        coords, dimension, degree, tolerance
    )
    relation = relations.get((int(dimension), physical_key))
    if relation is not None:
        master_key, phase, state = relation
        canonical_values = np.linalg.solve(transform, values) / phase
        return canonical_values, physical_key, master_key, phase, state
    return (
        np.linalg.solve(transform, values),
        physical_key,
        None,
        1.0 + 0.0j,
        _physical_state,
    )


def _packet_audit(
    packets: tuple[CanonicalPacket, ...], comm, *, role: str
) -> dict[str, Any]:
    keys = [key for key, _value in packets]
    local_unique = len(set(keys))
    return {
        "role": role,
        "local_packet_count": int(len(packets)),
        "local_duplicate_count": int(len(keys) - local_unique),
        "global_packet_count": int(comm.allreduce(len(packets), op=MPI.SUM)),
        "summed_local_duplicate_count": int(
            comm.allreduce(len(keys) - local_unique, op=MPI.SUM)
        ),
        "trace_mass_norm": "not_qualified",
        "hcurl_norm": "not_qualified",
    }


def _mpc_slave_mask(mpc, local_dofs: np.ndarray) -> np.ndarray:
    """Classify local rows without treating imported masters as slaves."""

    is_slave = np.asarray(mpc.is_slave, dtype=bool)
    return np.asarray(
        [
            int(local_dof) < is_slave.size
            and bool(is_slave[int(local_dof)])
            for local_dof in np.asarray(local_dofs, dtype=np.int32)
        ],
        dtype=bool,
    )


def iter_canonical_full_fe_dual_packets(
    function_space,
    mpc,
    recovered_vec,
    *,
    geometry_tolerance: float | None = None,
) -> Iterator[CanonicalPacket]:
    """Stream owner-local full-FE dual packets from a finalized MPC vector.

    Entity blocks use the conjugate-transpose physical transform.  Cell
    interiors use Basix ``Tt_apply`` directly.  The temporary extended vector
    is destroyed when iteration exhausts or raises; coefficient values are
    exchanged only by the ordinary owner-to-ghost update.
    """

    if mpc is None:
        raise ValueError("full-FE dual packets require finalized MPC metadata")
    degree, _trace_positions, interior_positions = _space_data(function_space)
    topology, cell_info, owned_cells = _topology_data(function_space)
    tolerance = (
        mesh_coordinate_tolerance(function_space.mesh)
        if geometry_tolerance is None
        else float(geometry_tolerance)
    )
    element_data = function_space.element
    layout = function_space.dofmap.dof_layout
    vector = (
        recovered_vec
        if isinstance(recovered_vec, PETSc.Vec)
        else recovered_vec.x.petsc_vec
    )
    vector_index_map = mpc.function_space.dofmap.index_map
    owned_size = int(function_space.dofmap.index_map.size_local)
    if int(vector_index_map.size_local) != owned_size:
        raise RuntimeError("MPC extended vector changed owned full-FE rows")
    source_values = np.asarray(vector.getArray(readonly=True))
    if source_values.size != owned_size:
        raise RuntimeError("full-FE dual source has an incompatible owned layout")

    extended = create_vector(
        [
            (
                vector_index_map,
                mpc.function_space.dofmap.index_map_bs,
            )
        ]
    )
    dimension = int(element_data.space_dimension)
    stored = np.empty(dimension, dtype=np.complex128)
    try:
        with extended.localForm() as local:
            local.set(0.0)
            local.array_w[:owned_size] = source_values
        extended.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        with extended.localForm() as local:
            local_values = local.array_r
            for dimension_index in (1, 2):
                cell_to_entity = topology.connectivity(topology.dim, dimension_index)
                for entity, cell in _owned_entity_incidents(
                    function_space, dimension_index
                ):
                    local_entities = np.asarray(
                        cell_to_entity.links(cell), dtype=np.int32
                    )
                    matches = np.flatnonzero(local_entities == int(entity))
                    if matches.size != 1:
                        raise RuntimeError("entity incidence is not unique")
                    positions = np.asarray(
                        layout.entity_dofs(dimension_index, int(matches[0])),
                        dtype=np.int32,
                    )
                    local_dofs = np.asarray(
                        function_space.dofmap.cell_dofs(cell), dtype=np.int32
                    )[positions]
                    slave_mask = _mpc_slave_mask(mpc, local_dofs)
                    if np.any(slave_mask) and not np.all(slave_mask):
                        raise RuntimeError("Floquet entity block is partly constrained")
                    if np.all(slave_mask):
                        continue
                    coordinates = _entity_coordinates(
                        function_space, dimension_index, entity
                    )
                    transform, state = _physical_entity_transform(
                        coordinates, dimension_index, degree, tolerance
                    )
                    canonical_values = transform.conj().T @ local_values[local_dofs]
                    physical_key = canonical_entity_key(coordinates, tolerance)
                    for basis, value in enumerate(canonical_values):
                        yield canonical_packet(
                            canonical_key(
                                role="full_fe_dual",
                                entity_dimension=dimension_index,
                                physical_entity=physical_key,
                                entity_local_basis_index=basis,
                                orientation_state=state,
                            ),
                            value,
                        )

            for cell in range(int(owned_cells[0])):
                local_dofs = np.asarray(
                    function_space.dofmap.cell_dofs(cell), dtype=np.int32
                )
                slave_mask = _mpc_slave_mask(mpc, local_dofs)
                stored[:] = local_values[local_dofs]
                stored[slave_mask] = 0.0
                element_data.Tt_apply(
                    stored,
                    np.asarray([cell_info[cell]], dtype=np.uint32),
                    1,
                )
                physical_key = canonical_entity_key(
                    _entity_coordinates(function_space, 3, cell), tolerance
                )
                for basis, position in enumerate(interior_positions):
                    local_dof = int(local_dofs[int(position)])
                    if local_dof < owned_size and not slave_mask[int(position)]:
                        yield canonical_packet(
                            canonical_key(
                                role="full_fe_dual",
                                entity_dimension=3,
                                physical_entity=physical_key,
                                entity_local_basis_index=basis,
                                orientation_state=("canonical_cell", "Tt_apply"),
                            ),
                            stored[int(position)],
                        )
    finally:
        extended.destroy()


def extract_canonical_full_fe_dual_packets(
    function_space,
    mpc,
    recovered_vec,
    *,
    geometry_tolerance: float | None = None,
) -> tuple[tuple[CanonicalPacket, ...], dict[str, Any]]:
    packets = tuple(
        iter_canonical_full_fe_dual_packets(
            function_space,
            mpc,
            recovered_vec,
            geometry_tolerance=geometry_tolerance,
        )
    )
    audit = _packet_audit(
        packets, function_space.mesh.comm, role="full_fe_dual"
    )
    audit.update(
        {
            "slave_exclusion": True,
            "numeric_allgather": False,
        }
    )
    return packets, audit


def iter_canonical_active_trace_packets(
    condensed: AssemblyTimeCondensedSystem,
    function_space,
    floquet_data,
    active_vec: PETSc.Vec,
) -> Iterator[CanonicalPacket]:
    """Expand active trace rows and emit one owner-local packet per edge/face."""

    degree, trace_positions, _interior_positions = _space_data(function_space)
    constraints = condensed.trace_constraints
    if int(active_vec.getSize()) != int(constraints.active_rows):
        raise ValueError("active vector size does not match trace constraints")
    topology, _cell_info, _owned = _topology_data(function_space)
    tolerance = mesh_coordinate_tolerance(function_space.mesh)
    relations = _floquet_relations(floquet_data)
    cell_to_entity = {
        dimension: topology.connectivity(topology.dim, dimension)
        for dimension in (1, 2)
    }
    incidents_by_dimension = {
        dimension: _owned_entity_incidents(function_space, dimension)
        for dimension in (1, 2)
    }
    incidents_by_cell: dict[int, list[tuple[int, int]]] = {}
    for dimension in (1, 2):
        for entity, cell in incidents_by_dimension[dimension]:
            incidents_by_cell.setdefault(cell, []).append((dimension, entity))
    del incidents_by_dimension
    active_union: set[int] = set()
    for cell in sorted(incidents_by_cell):
        cell_dofs = _cell_local_global_dofs(function_space, cell)
        original_trace = cell_dofs[trace_positions]
        active_ids, _expansion, _identity = _cell_trace_expansion(
            original_trace, constraints
        )
        active_union.update(int(value) for value in active_ids)
        del _expansion, active_ids, original_trace, cell_dofs
    union_ids, union_values = _scatter_values(active_vec, active_union)
    del active_union
    union_positions = {int(value): index for index, value in enumerate(union_ids)}
    layout = function_space.dofmap.dof_layout
    trace_rows = {int(position): row for row, position in enumerate(trace_positions)}
    for cell in sorted(incidents_by_cell):
        cell_dofs = _cell_local_global_dofs(function_space, cell)
        original_trace = cell_dofs[trace_positions]
        active_ids, expansion, _identity = _cell_trace_expansion(
            original_trace, constraints
        )
        local_values = expansion.dot(
            union_values[[union_positions[int(value)] for value in active_ids]]
        )
        for dimension, entity in incidents_by_cell[cell]:
            local_entity = int(
                np.flatnonzero(
                    np.asarray(cell_to_entity[dimension].links(cell), dtype=np.int32)
                    == int(entity)
                )[0]
            )
            positions = np.asarray(
                layout.entity_dofs(dimension, local_entity), dtype=np.int32
            )
            values = np.asarray(
                [local_values[trace_rows[int(position)]] for position in positions]
            )
            coords = _entity_coordinates(function_space, dimension, entity)
            (
                canonical_values,
                physical_key,
                floquet_master,
                phase,
                state,
            ) = _canonical_entity_values(
                values, coords, dimension, degree, tolerance, relations
            )
            for basis, value in enumerate(canonical_values):
                yield canonical_packet(
                    canonical_key(
                        role="active_trace",
                        entity_dimension=dimension,
                        physical_entity=physical_key,
                        entity_local_basis_index=basis,
                        orientation_state=state,
                        floquet_master=floquet_master,
                        floquet_coefficient=phase,
                    ),
                    value,
                )
        del expansion, active_ids, original_trace, cell_dofs, local_values


def extract_canonical_active_trace_packets(
    condensed: AssemblyTimeCondensedSystem,
    function_space,
    floquet_data,
    active_vec: PETSc.Vec,
) -> tuple[tuple[CanonicalPacket, ...], dict[str, Any]]:
    packets = tuple(
        iter_canonical_active_trace_packets(
            condensed, function_space, floquet_data, active_vec
        )
    )
    return packets, _packet_audit(
        packets, function_space.mesh.comm, role="active_trace"
    )


def iter_canonical_full_fe_packets(
    function_space,
    recovered_vec,
    floquet_data,
) -> Iterator[CanonicalPacket]:
    """Emit owner-local edge/face and cell-interior packets from a full field."""

    degree, _trace_positions, interior_positions = _space_data(function_space)
    topology, cell_info, owned_cells = _topology_data(function_space)
    tolerance = mesh_coordinate_tolerance(function_space.mesh)
    relations = _floquet_relations(floquet_data)
    vector = (
        recovered_vec
        if isinstance(recovered_vec, PETSc.Vec)
        else recovered_vec.x.petsc_vec
    )
    entity_incidents = {
        dimension: _owned_entity_incidents(function_space, dimension)
        for dimension in (1, 2)
    }
    index_map = function_space.dofmap.index_map
    selected_local_dof_mask = np.zeros(
        int(index_map.size_local) + int(index_map.num_ghosts), dtype=np.bool_
    )
    for cell in range(int(owned_cells[0])):
        selected_local_dof_mask[function_space.dofmap.cell_dofs(cell)] = True
    layout = function_space.dofmap.dof_layout
    for dimension, incidents in entity_incidents.items():
        cell_to_entity = topology.connectivity(topology.dim, dimension)
        for entity, cell in incidents:
            local_entity = int(
                np.flatnonzero(
                    np.asarray(cell_to_entity.links(cell), dtype=np.int32)
                    == int(entity)
                )[0]
            )
            positions = np.asarray(
                layout.entity_dofs(dimension, local_entity), dtype=np.int32
            )
            local_dofs = np.asarray(
                function_space.dofmap.cell_dofs(cell), dtype=np.int32
            )
            selected_local_dof_mask[local_dofs[positions]] = True
    relevant_local_dofs = np.flatnonzero(selected_local_dof_mask).astype(
        np.int32, copy=False
    )
    union_ids = np.asarray(
        index_map.local_to_global(relevant_local_dofs), dtype=PETSc.IntType
    )
    del selected_local_dof_mask, relevant_local_dofs
    union_ids.sort()
    union_ids, union_values = _scatter_values(vector, union_ids)
    for dimension, incidents in entity_incidents.items():
        cell_to_entity = topology.connectivity(topology.dim, dimension)
        for entity, cell in incidents:
            local_entity = int(
                np.flatnonzero(
                    np.asarray(cell_to_entity.links(cell), dtype=np.int32)
                    == int(entity)
                )[0]
            )
            positions = np.asarray(
                layout.entity_dofs(dimension, local_entity), dtype=np.int32
            )
            local_dofs = np.asarray(
                function_space.dofmap.cell_dofs(cell), dtype=np.int32
            )
            global_dofs = _global_dofs(function_space, local_dofs[positions])
            values = union_values[np.searchsorted(union_ids, global_dofs)]
            coords = _entity_coordinates(function_space, dimension, entity)
            (
                canonical_values,
                physical_key,
                floquet_master,
                phase,
                state,
            ) = _canonical_entity_values(
                values, coords, dimension, degree, tolerance, relations
            )
            for basis, value in enumerate(canonical_values):
                yield canonical_packet(
                    canonical_key(
                        role="full_fe",
                        entity_dimension=dimension,
                        physical_entity=physical_key,
                        entity_local_basis_index=basis,
                        orientation_state=state,
                        floquet_master=floquet_master,
                        floquet_coefficient=phase,
                    ),
                    value,
                )
    for cell in range(int(owned_cells[0])):
        local_dofs = np.asarray(function_space.dofmap.cell_dofs(cell), dtype=np.int32)
        global_dofs = _global_dofs(function_space, local_dofs)
        local_values = union_values[np.searchsorted(union_ids, global_dofs)]
        canonical_values = np.ascontiguousarray(local_values)
        function_space.element.Tt_apply(
            canonical_values,
            np.asarray([cell_info[cell]], dtype=np.uint32),
            1,
        )
        coords = _entity_coordinates(function_space, 3, cell)
        physical_key = canonical_entity_key(coords, tolerance)
        for basis, value in enumerate(canonical_values[interior_positions]):
            yield canonical_packet(
                canonical_key(
                    role="full_fe",
                    entity_dimension=3,
                    physical_entity=physical_key,
                    entity_local_basis_index=basis,
                    orientation_state=("canonical_cell", "Tt_apply"),
                ),
                value,
            )


def extract_canonical_full_fe_packets(
    function_space,
    recovered_vec,
    floquet_data,
) -> tuple[tuple[CanonicalPacket, ...], dict[str, Any]]:
    packets = tuple(
        iter_canonical_full_fe_packets(function_space, recovered_vec, floquet_data)
    )
    return packets, _packet_audit(packets, function_space.mesh.comm, role="full_fe")


def _canonical_packet_map(
    packets: Iterable[CanonicalPacket],
    *,
    role: str = "full_fe",
) -> dict[CanonicalKey, complex]:
    packet_map: dict[CanonicalKey, complex] = {}
    for key, value in packets:
        if key[0] != role:
            if role == "full_fe":
                raise ValueError("fresh-field reconstruction requires full_fe packets")
            raise ValueError(f"reconstruction requires {role} packets")
        if key in packet_map:
            raise ValueError(f"duplicate canonical full-FE key: {key!r}")
        packet_map[key] = canonical_packet(key, value)[1]
    if not packet_map:
        raise ValueError("cannot reconstruct a field from empty canonical packets")
    return packet_map


def _owned_global_to_local(function_space) -> dict[int, int]:
    index_map = function_space.dofmap.index_map
    local = np.arange(int(index_map.size_local), dtype=np.int32)
    return {
        int(global_id): int(local_id)
        for local_id, global_id in enumerate(index_map.local_to_global(local))
    }


def _fresh_entity_inverse(
    function_space,
    dimension: int,
    entity: int,
    degree: int,
    tolerance: float,
    relations: dict,
):
    coordinates = _entity_coordinates(function_space, dimension, entity)
    physical_key = canonical_entity_key(coordinates, tolerance)
    relation = relations.get((int(dimension), physical_key))
    transform, physical_state = _physical_entity_transform(
        coordinates, dimension, degree, tolerance
    )
    if relation is not None:
        master_key, phase, state = relation
        return physical_key, master_key, phase, transform, state
    return physical_key, None, 1.0 + 0.0j, transform, physical_state


def _physical_canonical_source_packets(
    function_space: Any,
    floquet_data: Any,
    fixed_seed: str,
    *,
    role: str,
) -> tuple[CanonicalPacket, ...]:
    """Build deterministic physical-key packets for one local source."""

    if role not in {"full_fe", "full_fe_dual"}:
        raise ValueError("unsupported physical canonical source role")
    degree, _trace_positions, interior_positions = _space_data(function_space)
    topology, _cell_info, owned_cells = _topology_data(function_space)
    tolerance = mesh_coordinate_tolerance(function_space.mesh)
    relations = _floquet_relations(floquet_data) if role == "full_fe" else {}
    layout = function_space.dofmap.dof_layout
    packets: list[CanonicalPacket] = []
    for dimension in (1, 2):
        cell_to_entity = topology.connectivity(topology.dim, dimension)
        for entity, _cell in _owned_entity_incidents(function_space, dimension):
            local_entity = int(
                np.flatnonzero(
                    np.asarray(cell_to_entity.links(_cell), dtype=np.int32)
                    == int(entity)
                )[0]
            )
            positions = np.asarray(
                layout.entity_dofs(dimension, local_entity), dtype=np.int32
            )
            local_dofs = np.asarray(
                function_space.dofmap.cell_dofs(_cell), dtype=np.int32
            )[positions]
            if role == "full_fe_dual":
                slave_mask = _mpc_slave_mask(floquet_data.mpc, local_dofs)
                if np.any(slave_mask) and not np.all(slave_mask):
                    raise RuntimeError("Floquet entity block is partly constrained")
                if np.all(slave_mask):
                    continue
            coordinates = _entity_coordinates(function_space, dimension, entity)
            if role == "full_fe":
                physical_key, master_key, phase, _transform, state = _fresh_entity_inverse(
                    function_space, dimension, entity, degree, tolerance, relations
                )
            else:
                physical_key = canonical_entity_key(coordinates, tolerance)
                _transform, state = _physical_entity_transform(
                    coordinates, dimension, degree, tolerance
                )
                master_key, phase = None, 1.0 + 0.0j
            for basis in range(len(positions)):
                key = canonical_key(
                    role=role,
                    entity_dimension=dimension,
                    physical_entity=physical_key,
                    entity_local_basis_index=basis,
                    orientation_state=state,
                    floquet_master=master_key,
                    floquet_coefficient=phase,
                )
                value, _digest, _payload = canonical_source_coefficient_from_key(
                    key, fixed_seed=fixed_seed
                )
                packets.append(canonical_packet(key, value))
    for cell in range(int(owned_cells[0])):
        local_dofs = np.asarray(
            function_space.dofmap.cell_dofs(cell), dtype=np.int32
        )
        interior_slave_mask = _mpc_slave_mask(
            floquet_data.mpc, local_dofs
        )[interior_positions]
        physical_key = canonical_entity_key(
            _entity_coordinates(function_space, 3, cell), tolerance
        )
        for basis, (_position, is_slave) in enumerate(
            zip(interior_positions, interior_slave_mask, strict=True)
        ):
            if role == "full_fe_dual" and bool(is_slave):
                continue
            key = canonical_key(
                role=role,
                entity_dimension=3,
                physical_entity=physical_key,
                entity_local_basis_index=basis,
                orientation_state=("canonical_cell", "Tt_apply"),
                floquet_master=None,
                floquet_coefficient=1.0 + 0.0j,
            )
            value, _digest, _payload = canonical_source_coefficient_from_key(
                key, fixed_seed=fixed_seed
            )
            packets.append(canonical_packet(key, value))
    if not packets:
        raise ValueError("physical canonical source has no local packets")
    return tuple(packets)


def build_physical_canonical_primal_source(
    function_space: Any,
    floquet_data: Any,
    *,
    fixed_seed: str,
) -> tuple[Any, dict[str, Any]]:
    """Build a legal primal field from deterministic physical canonical keys."""

    packets = _physical_canonical_source_packets(
        function_space, floquet_data, fixed_seed, role="full_fe"
    )
    field = reconstruct_canonical_full_fe_function(
        function_space, packets, floquet_data
    )
    field.x.scatter_forward()
    floquet_data.mpc.homogenize(field)
    field.x.scatter_forward()
    floquet_data.mpc.backsubstitution(field)
    field.x.scatter_forward()
    values = np.asarray(field.x.array, dtype=np.complex128)
    independent_count = sum(key[5] is None for key, _value in packets)
    comm = function_space.mesh.comm
    local_finite = bool(np.all(np.isfinite(values)))
    local_nonzero = bool(np.any(np.abs(values) > 0.0))
    dependent_count = len(packets) - independent_count
    return field, {
        "schema": "task038.v13.c0.physical-canonical-source.v1",
        "role": "full_fe",
        "fixed_seed": fixed_seed,
        "global_packet_count": int(comm.allreduce(len(packets), op=MPI.SUM)),
        "global_independent_packet_count": int(
            comm.allreduce(independent_count, op=MPI.SUM)
        ),
        "global_dependent_packet_count": int(
            comm.allreduce(dependent_count, op=MPI.SUM)
        ),
        "dependent_placeholder_non_authoritative": True,
        "dependent_value_authority": "finalized_mpc_master_phase_relation",
        "source_finite": bool(comm.allreduce(local_finite, op=MPI.LAND)),
        "source_nonzero": bool(comm.allreduce(local_nonzero, op=MPI.LOR)),
        "source_generation": "physical_canonical_key_sha256_v1",
        "phase_application": "finalized_floquet_mpc_once",
    }


def build_physical_canonical_dual_source(
    function_space: Any,
    floquet_data: Any,
    *,
    fixed_seed: str,
) -> tuple[Any, dict[str, Any]]:
    """Build a slave-zero dual vector from deterministic physical canonical keys."""

    packets = _physical_canonical_source_packets(
        function_space, floquet_data, fixed_seed, role="full_fe_dual"
    )
    vector = reconstruct_canonical_full_fe_dual_vector(
        function_space, floquet_data.mpc, packets
    )
    values = np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
    comm = function_space.mesh.comm
    local_finite = bool(np.all(np.isfinite(values)))
    local_nonzero = bool(np.any(np.abs(values) > 0.0))
    return vector, {
        "schema": "task038.v13.c0.physical-canonical-source.v1",
        "role": "full_fe_dual",
        "fixed_seed": fixed_seed,
        "global_packet_count": int(comm.allreduce(len(packets), op=MPI.SUM)),
        "global_independent_packet_count": int(
            comm.allreduce(len(packets), op=MPI.SUM)
        ),
        "global_dependent_packet_count": 0,
        "dependent_placeholder_non_authoritative": False,
        "dependent_value_authority": "slave_zero_dual_storage",
        "source_finite": bool(comm.allreduce(local_finite, op=MPI.LAND)),
        "source_nonzero": bool(comm.allreduce(local_nonzero, op=MPI.LOR)),
        "source_generation": "physical_canonical_key_sha256_v1",
        "phase_application": "dual_source_slave_zero_no_phase_reapplication",
    }


def reconstruct_canonical_full_fe_function(
    function_space,
    packets: Iterable[CanonicalPacket],
    floquet_data,
):
    """Rebuild a fresh H(curl) Function from reversible full-FE packets.

    Packets are physical keys, so the fresh mesh is resolved independently of
    the source PETSc numbering.  On MPI, callers pass owner-local packets for
    the same fresh partition or the same replicated global packet tuple on
    every rank; only local owned entities/cells are written on each rank.
    """

    degree, _trace_positions, interior_positions = _space_data(function_space)
    packet_map = _canonical_packet_map(packets)
    topology, cell_info, owned_cells = _topology_data(function_space)
    tolerance = mesh_coordinate_tolerance(function_space.mesh)
    relations = _floquet_relations(floquet_data)
    layout = function_space.dofmap.dof_layout
    global_to_local = _owned_global_to_local(function_space)
    expected_local_keys: set[CanonicalKey] = set()
    field = fem.Function(function_space)

    for dimension in (1, 2):
        cell_to_entity = topology.connectivity(topology.dim, dimension)
        for entity, cell in _owned_entity_incidents(function_space, dimension):
            local_entity = int(
                np.flatnonzero(
                    np.asarray(cell_to_entity.links(cell), dtype=np.int32)
                    == int(entity)
                )[0]
            )
            positions = np.asarray(
                layout.entity_dofs(dimension, local_entity), dtype=np.int32
            )
            physical_key, master_key, phase, transform, state = _fresh_entity_inverse(
                function_space, dimension, entity, degree, tolerance, relations
            )
            keys = tuple(
                canonical_key(
                    role="full_fe",
                    entity_dimension=dimension,
                    physical_entity=physical_key,
                    entity_local_basis_index=basis,
                    orientation_state=state,
                    floquet_master=master_key,
                    floquet_coefficient=phase,
                )
                for basis in range(len(positions))
            )
            expected_local_keys.update(keys)
            if any(key not in packet_map for key in keys):
                raise ValueError("missing canonical full-FE entity block")
            canonical_values = np.asarray(
                [packet_map[key] for key in keys], dtype=np.complex128
            )
            if transform.shape != (len(positions), len(positions)):
                raise ValueError("canonical entity transform has an unexpected shape")
            stored_values = phase * (transform @ canonical_values)
            global_dofs = _global_dofs(
                function_space,
                np.asarray(function_space.dofmap.cell_dofs(cell))[positions],
            )
            for global_id, stored_value in zip(global_dofs, stored_values, strict=True):
                local_id = global_to_local.get(int(global_id))
                if local_id is not None:
                    field.x.array[local_id] = stored_value

    for cell in range(int(owned_cells[0])):
        local_dofs = np.asarray(function_space.dofmap.cell_dofs(cell), dtype=np.int32)
        global_dofs = _global_dofs(function_space, local_dofs)
        coordinates = _entity_coordinates(function_space, 3, cell)
        physical_key = canonical_entity_key(coordinates, tolerance)
        keys = tuple(
            canonical_key(
                role="full_fe",
                entity_dimension=3,
                physical_entity=physical_key,
                entity_local_basis_index=basis,
                orientation_state=("canonical_cell", "Tt_apply"),
            )
            for basis in range(len(interior_positions))
        )
        expected_local_keys.update(keys)
        if any(key not in packet_map for key in keys):
            raise ValueError("missing canonical full-FE cell-interior block")
        canonical_values = np.asarray(
            [packet_map[key] for key in keys], dtype=np.complex128
        )
        canonical_block = np.zeros(
            int(function_space.element.space_dimension), dtype=np.complex128
        )
        canonical_block[interior_positions] = canonical_values
        stored_block = canonical_block.copy()
        function_space.element.T_apply(
            stored_block, np.asarray([cell_info[cell]], dtype=np.uint32), 1
        )
        for global_id, stored_value in zip(
            global_dofs[interior_positions],
            stored_block[interior_positions],
            strict=True,
        ):
            local_id = global_to_local.get(int(global_id))
            if local_id is not None:
                field.x.array[local_id] = stored_value

    missing = expected_local_keys.difference(packet_map)
    if missing:
        raise ValueError(f"missing canonical full-FE keys: {len(missing)}")
    if function_space.mesh.comm.size == 1:
        extra = set(packet_map).difference(expected_local_keys)
        if extra:
            raise ValueError(f"unexpected canonical full-FE keys: {len(extra)}")
    field.x.scatter_forward()
    return field


def reconstruct_canonical_full_fe_dual_vector(
    function_space,
    mpc,
    packets: Iterable[CanonicalPacket],
    *,
    geometry_tolerance: float | None = None,
) -> PETSc.Vec:
    """Rebuild a finalized-MPC dual vector from owner-local physical packets.

    The dual entity map solves with ``Tᴴ`` and the dual cell map reverses
    ``Tt_apply`` with ``T_apply``.  Dual packets intentionally carry no
    Floquet phase: the input/output vector already uses the finalized MPC
    convention, so a second phase application would be incorrect.
    """

    if mpc is None:
        raise ValueError("full-FE dual reconstruction requires finalized MPC metadata")
    degree, _trace_positions, interior_positions = _space_data(function_space)
    packet_map = _canonical_packet_map(packets, role="full_fe_dual")
    topology, cell_info, owned_cells = _topology_data(function_space)
    tolerance = (
        mesh_coordinate_tolerance(function_space.mesh)
        if geometry_tolerance is None
        else float(geometry_tolerance)
    )
    layout = function_space.dofmap.dof_layout
    target_space = mpc.function_space
    target_index_map = target_space.dofmap.index_map
    owned_size = int(function_space.dofmap.index_map.size_local)
    if int(target_index_map.size_local) != owned_size:
        raise RuntimeError("MPC target changed owned full-FE rows")
    global_to_local = _owned_global_to_local(target_space)
    expected_local_keys: set[CanonicalKey] = set()
    target = create_vector(
        [
            (
                target_index_map,
                target_space.dofmap.index_map_bs,
            )
        ]
    )
    target_values = target.getArray()
    target_values[:] = 0.0

    for dimension in (1, 2):
        cell_to_entity = topology.connectivity(topology.dim, dimension)
        for entity, cell in _owned_entity_incidents(function_space, dimension):
            local_entity = int(
                np.flatnonzero(
                    np.asarray(cell_to_entity.links(cell), dtype=np.int32)
                    == int(entity)
                )[0]
            )
            positions = np.asarray(
                layout.entity_dofs(dimension, local_entity), dtype=np.int32
            )
            local_dofs = np.asarray(
                function_space.dofmap.cell_dofs(cell), dtype=np.int32
            )[positions]
            slave_mask = _mpc_slave_mask(mpc, local_dofs)
            if np.any(slave_mask) and not np.all(slave_mask):
                target.destroy()
                raise RuntimeError("Floquet entity block is partly constrained")
            if np.all(slave_mask):
                continue
            coordinates = _entity_coordinates(function_space, dimension, entity)
            physical_key = canonical_entity_key(coordinates, tolerance)
            transform, state = _physical_entity_transform(
                coordinates, dimension, degree, tolerance
            )
            keys = tuple(
                canonical_key(
                    role="full_fe_dual",
                    entity_dimension=dimension,
                    physical_entity=physical_key,
                    entity_local_basis_index=basis,
                    orientation_state=state,
                )
                for basis in range(len(positions))
            )
            expected_local_keys.update(keys)
            if any(key not in packet_map for key in keys):
                target.destroy()
                raise ValueError("missing canonical full-FE dual entity block")
            canonical_values = np.asarray(
                [packet_map[key] for key in keys], dtype=np.complex128
            )
            if transform.shape != (len(positions), len(positions)):
                target.destroy()
                raise ValueError("canonical entity transform has an unexpected shape")
            stored_values = np.linalg.solve(transform.conj().T, canonical_values)
            global_dofs = _global_dofs(
                function_space,
                np.asarray(function_space.dofmap.cell_dofs(cell))[positions],
            )
            for global_id, stored_value in zip(global_dofs, stored_values, strict=True):
                local_id = global_to_local.get(int(global_id))
                if local_id is not None:
                    target_values[local_id] = stored_value

    for cell in range(int(owned_cells[0])):
        local_dofs = np.asarray(
            function_space.dofmap.cell_dofs(cell), dtype=np.int32
        )
        global_dofs = _global_dofs(function_space, local_dofs)
        slave_mask = _mpc_slave_mask(mpc, local_dofs)
        physical_key = canonical_entity_key(
            _entity_coordinates(function_space, 3, cell), tolerance
        )
        keys = tuple(
            canonical_key(
                role="full_fe_dual",
                entity_dimension=3,
                physical_entity=physical_key,
                entity_local_basis_index=basis,
                orientation_state=("canonical_cell", "Tt_apply"),
            )
            for basis, position in enumerate(interior_positions)
            if not slave_mask[int(position)]
        )
        expected_local_keys.update(keys)
        if any(key not in packet_map for key in keys):
            target.destroy()
            raise ValueError("missing canonical full-FE dual cell-interior block")
        canonical_block = np.zeros(
            int(function_space.element.space_dimension), dtype=np.complex128
        )
        for key, position in zip(
            keys,
            [
                int(position)
                for position in interior_positions
                if not slave_mask[int(position)]
            ],
            strict=True,
        ):
            canonical_block[int(position)] = packet_map[key]
        stored_block = canonical_block.copy()
        function_space.element.T_apply(
            stored_block,
            np.asarray([cell_info[cell]], dtype=np.uint32),
            1,
        )
        for position in interior_positions:
            if slave_mask[int(position)]:
                continue
            local_id = global_to_local.get(int(global_dofs[int(position)]))
            if local_id is not None:
                target_values[local_id] = stored_block[int(position)]

    missing = expected_local_keys.difference(packet_map)
    if missing:
        target.destroy()
        raise ValueError(f"missing canonical full-FE dual keys: {len(missing)}")
    if function_space.mesh.comm.size == 1:
        extra = set(packet_map).difference(expected_local_keys)
        if extra:
            target.destroy()
            raise ValueError(f"unexpected canonical full-FE dual keys: {len(extra)}")
    target.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    return target


def _assembled_real(form, comm) -> float:
    local = fem.assemble_scalar(fem.form(form))
    value = comm.allreduce(local, op=MPI.SUM)
    return max(float(np.real(value)), 0.0) ** 0.5


def compare_hcurl_fields(left_field, right_field) -> dict[str, Any]:
    """Compare fields with standard volume, curl, trace-mass, and H(curl) norms."""

    if left_field.function_space.mesh is not right_field.function_space.mesh:
        raise ValueError("H(curl) field comparison requires one common fresh mesh")
    mesh = left_field.function_space.mesh
    comm = mesh.comm
    difference = left_field - right_field
    curl_difference = ufl.curl(difference)
    curl_reference = ufl.curl(right_field)
    dx = ufl.Measure("dx", domain=mesh)
    ds = ufl.Measure("ds", domain=mesh)
    dS = ufl.Measure("dS", domain=mesh)
    normal = ufl.FacetNormal(mesh)
    boundary_difference = ufl.cross(normal, difference)
    interior_difference = ufl.cross(normal("+"), difference("+"))
    boundary_reference = ufl.cross(normal, right_field)
    interior_reference = ufl.cross(normal("+"), right_field("+"))
    l2_difference = _assembled_real(ufl.inner(difference, difference) * dx, comm)
    l2_reference = _assembled_real(ufl.inner(right_field, right_field) * dx, comm)
    curl_difference_norm = _assembled_real(
        ufl.inner(curl_difference, curl_difference) * dx, comm
    )
    curl_reference_norm = _assembled_real(
        ufl.inner(curl_reference, curl_reference) * dx, comm
    )
    trace_difference = _assembled_real(
        ufl.inner(boundary_difference, boundary_difference) * ds
        + ufl.inner(interior_difference, interior_difference) * dS,
        comm,
    )
    trace_reference = _assembled_real(
        ufl.inner(boundary_reference, boundary_reference) * ds
        + ufl.inner(interior_reference, interior_reference) * dS,
        comm,
    )
    hcurl_difference = float(np.hypot(l2_difference, curl_difference_norm))
    hcurl_reference = float(np.hypot(l2_reference, curl_reference_norm))
    return {
        "l2_difference_norm": l2_difference,
        "l2_reference_norm": l2_reference,
        "relative_l2": l2_difference / max(l2_reference, np.finfo(float).tiny),
        "curl_difference_norm": curl_difference_norm,
        "curl_reference_norm": curl_reference_norm,
        "relative_curl_l2": curl_difference_norm
        / max(curl_reference_norm, np.finfo(float).tiny),
        "tangential_trace_mass_difference_norm": trace_difference,
        "tangential_trace_mass_reference_norm": trace_reference,
        "relative_tangential_trace_mass": trace_difference
        / max(trace_reference, np.finfo(float).tiny),
        "hcurl_difference_norm": hcurl_difference,
        "hcurl_reference_norm": hcurl_reference,
        "relative_hcurl": hcurl_difference / max(hcurl_reference, np.finfo(float).tiny),
        "trace_measure": "outer ds plus one (+) side of interior dS",
    }
