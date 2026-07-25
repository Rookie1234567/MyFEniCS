"""Physical full-p6-storage expansion for selective p6 trace orbits.

The assembly-time condensation kernel accepts a generalized expansion

``u_storage_trace = C q_active``.

This module builds that expansion from actual DOLFINx hexahedral entity
DoFs.  The storage function space is required to be the standard full-p6
Nedelec space: both its trace and cell interior are p6.  The active
coordinates contain:

* the complete periodic quotient of the p5 retained trace subspace; and
* only the missing-p6 shell orbits selected by an owner-aware row plan.

The fixed-p5-trace/p6-interior element is deliberately rejected as storage.
It has no physical missing-p6 trace rows and therefore cannot be used to
manufacture a selective p6 enrichment after assembly.

No PETSc matrix, local Maxwell tensor, DWR score, or selection is created
here.  The returned ``CallerTraceExpansion`` is consumed before global
matrix insertion by the assembly-time condensation path.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import basix
import numpy as np
from petsc4py import PETSc

from dolfinx import cpp

from src.adaptivity.p6_trace_complement_qualification import (
    P5P6TraceComplementQualification,
)
from src.constraints.high_order_floquet_trace import (
    FloquetTraceTopology,
    build_missing_p6_trace_orbit_identity_input,
    edge_coefficient_transform,
    face_coefficient_transform,
)
from src.constraints.selective_p6_trace_3d import (
    SelectiveP6TraceMPIRowPlan,
)
from src.constraints.selective_p6_trace_mesh_catalog import (
    EntityGeometryKey,
    PhysicalP6TraceEntity,
    PhysicalP6TracePeriodicRelation,
    SelectiveP6TraceMeshCatalog,
    TraceEntityKind,
)
from src.geometry.tetra_mesh_audit import canonical_entity_key
from src.solvers.hcurl_assembly_time_condensation import (
    CallerTraceExpansion,
)


_ENTITY_DIMENSION = {"edge": 1, "face": 2}
_RETAINED_DIMENSION = {"edge": 5, "face": 40}
_MISSING_DIMENSION = {"edge": 1, "face": 20}


def _relative_matrix_error(left: np.ndarray, right: np.ndarray) -> float:
    left_array = np.asarray(left, dtype=np.complex128)
    right_array = np.asarray(right, dtype=np.complex128)
    return float(np.linalg.norm(left_array - right_array, ord="fro")) / max(
        1.0,
        float(np.linalg.norm(left_array, ord="fro")),
        float(np.linalg.norm(right_array, ord="fro")),
    )


def _readonly_matrix(values: np.ndarray, *, label: str) -> np.ndarray:
    matrix = np.array(values, dtype=np.complex128, copy=True)
    if matrix.ndim != 2 or not np.all(np.isfinite(matrix)):
        raise ValueError(f"{label} must be a finite matrix")
    matrix.setflags(write=False)
    return matrix


def _readonly_int_vector(values: Sequence[int], *, label: str) -> np.ndarray:
    raw = np.asarray(values)
    if raw.ndim != 1 or not np.issubdtype(raw.dtype, np.integer):
        raise ValueError(f"{label} must be a one-dimensional integer vector")
    result = np.asarray(raw, dtype=PETSc.IntType).copy()
    result.setflags(write=False)
    return result


@dataclass(frozen=True)
class PhysicalEntityP6TraceExpansion:
    """Full-p6 storage rows for one physical edge or face."""

    entity_id: int
    representative_entity_id: int
    entity_kind: TraceEntityKind
    storage_original_dofs: np.ndarray
    base_active_rows: np.ndarray
    selected_missing_active_rows: np.ndarray
    active_rows: np.ndarray
    coefficient_matrix: np.ndarray
    retained_pullback: np.ndarray
    missing_pullback: np.ndarray | None

    def __post_init__(self) -> None:
        storage = _readonly_int_vector(
            self.storage_original_dofs,
            label="physical entity storage DoFs",
        )
        base = _readonly_int_vector(
            self.base_active_rows,
            label="physical entity base active rows",
        )
        missing = _readonly_int_vector(
            self.selected_missing_active_rows,
            label="physical entity selected missing rows",
        )
        active = _readonly_int_vector(
            self.active_rows,
            label="physical entity active rows",
        )
        coefficients = _readonly_matrix(
            self.coefficient_matrix,
            label="physical entity p6 trace expansion",
        )
        retained_pullback = _readonly_matrix(
            self.retained_pullback,
            label="physical entity retained pullback",
        )
        expected_storage = (
            6 if self.entity_kind == "edge" else 60
        )
        expected_retained = _RETAINED_DIMENSION[self.entity_kind]
        if len(storage) != expected_storage:
            raise ValueError("physical entity has the wrong p6 storage size")
        if len(base) != expected_retained:
            raise ValueError("physical entity has the wrong p5 base size")
        if coefficients.shape != (len(storage), len(active)):
            raise ValueError("physical entity expansion shape is inconsistent")
        if retained_pullback.shape != (
            expected_retained,
            expected_retained,
        ):
            raise ValueError("physical entity retained pullback shape is wrong")
        if not np.array_equal(
            active,
            np.concatenate((base, missing)),
        ):
            raise ValueError(
                "physical entity active rows are not base then selected shell"
            )
        if self.missing_pullback is None:
            if len(missing):
                raise ValueError(
                    "unselected entity cannot expose missing active rows"
                )
        else:
            missing_pullback = _readonly_matrix(
                self.missing_pullback,
                label="physical entity missing pullback",
            )
            expected_missing = _MISSING_DIMENSION[self.entity_kind]
            if missing_pullback.shape != (
                expected_missing,
                expected_missing,
            ):
                raise ValueError(
                    "physical entity missing pullback shape is wrong"
                )
            if len(missing) != expected_missing:
                raise ValueError(
                    "selected entity missing active-row count is wrong"
                )
            object.__setattr__(
                self,
                "missing_pullback",
                missing_pullback,
            )
        object.__setattr__(self, "storage_original_dofs", storage)
        object.__setattr__(self, "base_active_rows", base)
        object.__setattr__(
            self,
            "selected_missing_active_rows",
            missing,
        )
        object.__setattr__(self, "active_rows", active)
        object.__setattr__(self, "coefficient_matrix", coefficients)
        object.__setattr__(
            self,
            "retained_pullback",
            retained_pullback,
        )


@dataclass(frozen=True)
class PhysicalCellP6TraceExpansion:
    """One owned cell's full-p6 trace rows and sparse active columns."""

    local_cell: int
    storage_original_dofs: np.ndarray
    active_rows: np.ndarray
    coefficient_matrix: np.ndarray

    def __post_init__(self) -> None:
        if int(self.local_cell) < 0:
            raise ValueError("local cell index must be nonnegative")
        storage = _readonly_int_vector(
            self.storage_original_dofs,
            label="cell storage trace DoFs",
        )
        active = _readonly_int_vector(
            self.active_rows,
            label="cell active rows",
        )
        coefficients = _readonly_matrix(
            self.coefficient_matrix,
            label="cell p6 trace expansion",
        )
        if coefficients.shape != (len(storage), len(active)):
            raise ValueError("cell trace expansion shape is inconsistent")
        if len(np.unique(storage)) != len(storage):
            raise ValueError("cell storage trace DoFs are duplicated")
        if len(np.unique(active)) != len(active):
            raise ValueError("cell active rows are duplicated")
        object.__setattr__(self, "local_cell", int(self.local_cell))
        object.__setattr__(self, "storage_original_dofs", storage)
        object.__setattr__(self, "active_rows", active)
        object.__setattr__(self, "coefficient_matrix", coefficients)


@dataclass(frozen=True)
class ActualSelectiveP6TraceExpansion:
    """Qualified bridge product ready for assembly-time condensation."""

    caller_trace_expansion: CallerTraceExpansion
    entity_expansions: tuple[PhysicalEntityP6TraceExpansion, ...]
    owned_cell_expansions: tuple[PhysicalCellP6TraceExpansion, ...]
    storage_expansion_by_original: Mapping[
        int,
        tuple[np.ndarray, np.ndarray],
    ]
    base_logical_rows: Mapping[tuple[int, int], int]
    selected_missing_logical_rows: Mapping[tuple[int, int], int]
    full_p6_storage_trace_rows: int
    p5_periodic_quotient_rows: int
    selected_missing_rows: int
    active_rows: int
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.audit.get("pass") is not True:
            raise ValueError("actual selective p6 trace expansion is unqualified")
        frozen_expansion: dict[
            int,
            tuple[np.ndarray, np.ndarray],
        ] = {}
        for original, (rows, coefficients) in (
            self.storage_expansion_by_original.items()
        ):
            row_array = _readonly_int_vector(
                rows,
                label="storage expansion active rows",
            )
            coefficient_array = np.asarray(
                coefficients,
                dtype=np.complex128,
            ).copy()
            coefficient_array.setflags(write=False)
            frozen_expansion[int(original)] = (
                row_array,
                coefficient_array,
            )
        object.__setattr__(
            self,
            "storage_expansion_by_original",
            MappingProxyType(frozen_expansion),
        )
        object.__setattr__(
            self,
            "base_logical_rows",
            MappingProxyType(
                {
                    (int(key[0]), int(key[1])): int(row)
                    for key, row in self.base_logical_rows.items()
                }
            ),
        )
        object.__setattr__(
            self,
            "selected_missing_logical_rows",
            MappingProxyType(
                {
                    (int(key[0]), int(key[1])): int(row)
                    for key, row in (
                        self.selected_missing_logical_rows.items()
                    )
                }
            ),
        )


@dataclass(frozen=True)
class _StorageEntityDofs:
    entity_id: int
    entity_kind: TraceEntityKind
    geometry_key: EntityGeometryKey
    dolfinx_global_entity_id: int
    storage_original_dofs: tuple[int, ...]


@dataclass(frozen=True)
class _OrbitPullback:
    representative_entity_id: int
    member_entity_ids: tuple[int, ...]
    entity_kind: TraceEntityKind
    dimension: int
    representative_to_member: Mapping[int, np.ndarray]


def _validate_full_p6_storage(
    storage_space: Any,
    qualification: P5P6TraceComplementQualification,
) -> None:
    msh = storage_space.mesh
    if "hexahedron" not in str(msh.basix_cell()).lower():
        raise NotImplementedError("selective p6 storage requires hexahedra")
    actual = storage_space.element.basix_element
    reference = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        6,
        basix.LagrangeVariant.legendre,
    )
    checks = {
        "standard_full_p6_element_hash_matches": (
            actual.hash() == reference.hash()
        ),
        "standard_full_p6_dimension_is_882": (
            int(actual.dim) == int(reference.dim) == 882
        ),
        "p6_trace_edge_dimension_is_6": all(
            len(dofs) == 6 for dofs in actual.entity_dofs[1]
        ),
        "p6_trace_face_dimension_is_60": all(
            len(dofs) == 60 for dofs in actual.entity_dofs[2]
        ),
        "p6_cell_interior_dimension_is_450": (
            len(actual.entity_dofs[3][0]) == 450
        ),
        "qualified_p6_dimension_matches_storage": (
            qualification.audit.get("p6_dimension") == int(actual.dim)
        ),
        "covariant_piola_storage": (
            actual.map_type == basix.MapType.covariantPiola
        ),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise ValueError(
            "storage space is not the qualified full-p6 trace/p6-interior "
            "element; fixed-p5-trace storage cannot create missing p6 modes: "
            + ", ".join(failed)
        )


def _validate_catalog_topology_identity(
    *,
    storage_space: Any,
    catalog: SelectiveP6TraceMeshCatalog,
    topology: FloquetTraceTopology,
) -> None:
    msh = storage_space.mesh
    mesh_token = topology.key.mesh_token
    if (
        not isinstance(mesh_token, tuple)
        or not mesh_token
        or int(mesh_token[0]) != id(msh._cpp_object)
    ):
        raise RuntimeError(
            "Floquet topology and full-p6 storage do not share the same "
            "actual DOLFINx mesh object"
        )
    identity = build_missing_p6_trace_orbit_identity_input(
        topology,
        mesh_sha256=catalog.trace_geometry_sha256,
        comm=msh.comm,
    )
    if identity.input_sha256 != catalog.audit.get(
        "topology_identity_sha256"
    ):
        raise RuntimeError(
            "Floquet topology identity differs from the actual mesh catalog"
        )


def _global_storage_entity_dofs(
    storage_space: Any,
    *,
    catalog: SelectiveP6TraceMeshCatalog,
    coordinate_tolerance: float,
) -> tuple[
    tuple[_StorageEntityDofs, ...],
    tuple[tuple[int, ...], ...],
]:
    msh = storage_space.mesh
    comm = msh.comm
    tdim = msh.topology.dim
    element = storage_space.element.basix_element
    dofmap = storage_space.dofmap
    if int(dofmap.index_map_bs) != 1:
        raise NotImplementedError("full-p6 storage requires scalar-blocked DoFs")
    catalog_by_geometry = {
        (entity.entity_kind, entity.geometry_key): entity
        for entity in catalog.entities
    }
    local_records: dict[int, _StorageEntityDofs] = {}
    for entity_kind in ("edge", "face"):
        dimension = _ENTITY_DIMENSION[entity_kind]
        msh.topology.create_entities(dimension)
        msh.topology.create_connectivity(tdim, dimension)
        cell_to_entity = msh.topology.connectivity(tdim, dimension)
        local_entity_dofs = element.entity_dofs[dimension]
        entity_map = msh.topology.index_map(dimension)
        local_entities = np.arange(
            entity_map.size_local + entity_map.num_ghosts,
            dtype=np.int32,
        )
        geometry = cpp.mesh.entities_to_geometry(
            msh._cpp_object,
            dimension,
            local_entities,
            True,
        )
        geometry_key_by_local = {
            int(entity): canonical_entity_key(
                np.asarray(
                    msh.geometry.x[
                        np.asarray(geometry_dofs, dtype=np.int64)
                    ],
                    dtype=np.float64,
                ),
                coordinate_tolerance,
            )
            for entity, geometry_dofs in zip(
                local_entities,
                geometry,
                strict=True,
            )
        }
        global_entity_by_local = {
            int(entity): int(global_entity)
            for entity, global_entity in zip(
                local_entities,
                entity_map.local_to_global(local_entities),
                strict=True,
            )
        }
        cell_count = int(
            msh.topology.index_map(tdim).size_local
            + msh.topology.index_map(tdim).num_ghosts
        )
        for cell in range(cell_count):
            cell_entities = cell_to_entity.links(cell)
            cell_dofs = dofmap.cell_dofs(cell)
            if len(cell_entities) != len(local_entity_dofs):
                raise RuntimeError(
                    "Basix and DOLFINx entity counts disagree for full p6"
                )
            for local_entity, mesh_entity in enumerate(cell_entities):
                positions = np.asarray(
                    local_entity_dofs[local_entity],
                    dtype=np.int32,
                )
                local_dofs = np.asarray(
                    [cell_dofs[int(position)] for position in positions],
                    dtype=np.int32,
                )
                global_dofs = dofmap.index_map.local_to_global(
                    local_dofs
                ).astype(np.int64)
                geometry_key = geometry_key_by_local[int(mesh_entity)]
                try:
                    physical = catalog_by_geometry[
                        (entity_kind, geometry_key)
                    ]
                except KeyError as exc:
                    raise RuntimeError(
                        "full-p6 storage entity is missing from the actual "
                        "mesh catalog"
                    ) from exc
                global_entity = global_entity_by_local[int(mesh_entity)]
                if global_entity != physical.dolfinx_global_entity_id:
                    raise RuntimeError(
                        "catalog and storage DOLFINx global entity IDs differ"
                    )
                record = _StorageEntityDofs(
                    entity_id=physical.entity_id,
                    entity_kind=entity_kind,
                    geometry_key=geometry_key,
                    dolfinx_global_entity_id=global_entity,
                    storage_original_dofs=tuple(map(int, global_dofs)),
                )
                previous = local_records.get(physical.entity_id)
                if previous is not None and previous != record:
                    raise RuntimeError(
                        "full-p6 entity DoF ordering differs across cells"
                    )
                local_records[physical.entity_id] = record

    gathered = [
        record
        for packet in comm.allgather(tuple(local_records.values()))
        for record in packet
    ]
    global_records: dict[int, _StorageEntityDofs] = {}
    for record in gathered:
        previous = global_records.setdefault(record.entity_id, record)
        if previous != record:
            raise RuntimeError(
                "MPI copies disagree on full-p6 entity storage DoFs"
            )
    expected_ids = set(range(len(catalog.entities)))
    if set(global_records) != expected_ids:
        raise RuntimeError("full-p6 storage entity catalog is incomplete")
    ordered_records = tuple(
        global_records[entity_id] for entity_id in sorted(global_records)
    )
    all_storage_dofs = [
        dof
        for record in ordered_records
        for dof in record.storage_original_dofs
    ]
    if len(all_storage_dofs) != len(set(all_storage_dofs)):
        raise RuntimeError("full-p6 physical trace entity DoFs overlap")

    trace_positions = np.asarray(
        [
            dof
            for dimension in (1, 2)
            for entity_dofs in element.entity_dofs[dimension]
            for dof in entity_dofs
        ],
        dtype=np.int32,
    )
    solver_trace_positions = np.setdiff1d(
        np.arange(element.dim, dtype=np.int32),
        np.asarray(element.entity_dofs[tdim][0], dtype=np.int32),
        assume_unique=True,
    )
    if not np.array_equal(trace_positions, solver_trace_positions):
        raise RuntimeError(
            "physical entity trace ordering differs from the condensation "
            "kernel's full-p6 storage trace ordering"
        )
    owned_cells = int(msh.topology.index_map(tdim).size_local)
    owned_cell_trace_dofs = tuple(
        tuple(
            map(
                int,
                dofmap.index_map.local_to_global(
                    np.asarray(
                        dofmap.cell_dofs(cell)[trace_positions],
                        dtype=np.int32,
                    )
                ),
            )
        )
        for cell in range(owned_cells)
    )
    if any(len(set(dofs)) != len(dofs) for dofs in owned_cell_trace_dofs):
        raise RuntimeError("owned cell full-p6 trace DoFs are duplicated")
    return ordered_records, owned_cell_trace_dofs


def _p5_transform(
    metadata: PhysicalP6TracePeriodicRelation,
    *,
    entity_kind: TraceEntityKind,
) -> np.ndarray:
    permutation = metadata.dolfinx_entity_vertex_permutation
    if entity_kind == "edge":
        transform = edge_coefficient_transform(
            5,
            reversed_orientation=permutation == (1, 0),
            cell_type="hexahedron",
        )
    else:
        transform = face_coefficient_transform(5, permutation)
    return np.asarray(
        metadata.floquet_phase * transform,
        dtype=np.complex128,
    )


def _discover_actual_orbit_pullbacks(
    *,
    catalog: SelectiveP6TraceMeshCatalog,
    basis_kind: str,
    tolerance: float,
) -> tuple[_OrbitPullback, ...]:
    if basis_kind not in {"retained", "missing"}:
        raise ValueError("orbit pullback basis must be retained or missing")
    by_id = {entity.entity_id: entity for entity in catalog.entities}
    adjacency: dict[int, list[tuple[int, np.ndarray]]] = {
        entity_id: [] for entity_id in by_id
    }
    for metadata in catalog.relation_metadata:
        slave = by_id[metadata.slave_entity_id]
        master = by_id[metadata.master_entity_id]
        if slave.entity_kind != master.entity_kind:
            raise RuntimeError("periodic relation mixes edge and face entities")
        matrix = (
            _p5_transform(metadata, entity_kind=slave.entity_kind)
            if basis_kind == "retained"
            else np.asarray(
                metadata.dolfinx_coefficient_pullback,
                dtype=np.complex128,
            )
        )
        inverse = np.linalg.solve(
            matrix,
            np.eye(matrix.shape[0], dtype=np.complex128),
        )
        adjacency[master.entity_id].append((slave.entity_id, matrix))
        adjacency[slave.entity_id].append((master.entity_id, inverse))

    expected_orbits = {
        orbit.representative_entity_id: orbit
        for orbit in catalog.all_inactive_orbit_numbering.orbits
    }
    visited: set[int] = set()
    result: list[_OrbitPullback] = []
    for seed in sorted(by_id):
        if seed in visited:
            continue
        component: set[int] = set()
        stack = [seed]
        while stack:
            entity_id = stack.pop()
            if entity_id in component:
                continue
            component.add(entity_id)
            stack.extend(neighbor for neighbor, _matrix in adjacency[entity_id])
        representative = min(component)
        physical = by_id[representative]
        dimension = (
            _RETAINED_DIMENSION[physical.entity_kind]
            if basis_kind == "retained"
            else _MISSING_DIMENSION[physical.entity_kind]
        )
        transforms: dict[int, np.ndarray] = {
            representative: np.eye(dimension, dtype=np.complex128)
        }
        queue = [representative]
        while queue:
            current = queue.pop(0)
            for neighbor, neighbor_from_current in sorted(
                adjacency[current],
                key=lambda item: item[0],
            ):
                candidate = neighbor_from_current @ transforms[current]
                if neighbor not in transforms:
                    transforms[neighbor] = candidate
                    queue.append(neighbor)
                elif (
                    _relative_matrix_error(
                        transforms[neighbor],
                        candidate,
                    )
                    > tolerance
                ):
                    raise RuntimeError(
                        "actual DOLFINx/Floquet orbit pullback cycle does "
                        "not close"
                    )
        expected = expected_orbits.get(representative)
        members = tuple(sorted(component))
        if expected is None or expected.member_entity_ids != members:
            raise RuntimeError(
                "actual oriented orbit membership differs from canonical "
                "physical catalog"
            )
        if expected.entity_kind != physical.entity_kind:
            raise RuntimeError("actual and canonical orbit kinds differ")
        frozen = {
            entity_id: _readonly_matrix(
                transform,
                label="actual orbit pullback",
            )
            for entity_id, transform in transforms.items()
        }
        result.append(
            _OrbitPullback(
                representative_entity_id=representative,
                member_entity_ids=members,
                entity_kind=physical.entity_kind,
                dimension=dimension,
                representative_to_member=MappingProxyType(frozen),
            )
        )
        visited.update(component)
    return tuple(result)


def _base_logical_rows(
    *,
    catalog: SelectiveP6TraceMeshCatalog,
    row_plan: SelectiveP6TraceMPIRowPlan,
    retained_orbits: Sequence[_OrbitPullback],
) -> dict[tuple[int, int], int]:
    by_owner: list[list[_OrbitPullback]] = [
        [] for _rank in range(row_plan.mpi_size)
    ]
    for orbit in retained_orbits:
        owner = catalog.representative_owner_ranks[
            orbit.representative_entity_id
        ]
        by_owner[owner].append(orbit)
    expected_counts = tuple(
        sum(orbit.dimension for orbit in orbits)
        for orbits in by_owner
    )
    if expected_counts != row_plan.owned_base_row_counts_by_rank:
        raise RuntimeError(
            "actual p5 periodic quotient ownership differs from row plan"
        )
    logical: dict[tuple[int, int], int] = {}
    for rank, orbits in enumerate(by_owner):
        cursor = row_plan.rank_base_row_ranges[rank][0]
        for orbit in sorted(
            orbits,
            key=lambda item: item.representative_entity_id,
        ):
            for mode in range(orbit.dimension):
                logical[(orbit.representative_entity_id, mode)] = cursor
                cursor += 1
        if cursor != row_plan.rank_base_row_ranges[rank][1]:
            raise RuntimeError("actual p5 base rows do not close owner range")
    if len(logical) != row_plan.active_base_rows:
        raise RuntimeError("actual p5 periodic quotient row count is wrong")
    return logical


def _validate_selected_orbits(
    *,
    catalog: SelectiveP6TraceMeshCatalog,
    row_plan: SelectiveP6TraceMPIRowPlan,
) -> set[int]:
    catalog_orbits = {
        orbit.representative_entity_id: orbit
        for orbit in catalog.all_inactive_orbit_numbering.orbits
    }
    selected: set[int] = set()
    for representatives in (
        row_plan.owned_selected_orbit_representatives_by_rank
    ):
        selected.update(representatives)
    descriptor_by_representative: dict[int, tuple[str, tuple[int, ...]]] = {}
    for descriptor in row_plan.selected_row_descriptors:
        value = (
            descriptor.entity_kind,
            descriptor.physical_member_entity_ids,
        )
        previous = descriptor_by_representative.setdefault(
            descriptor.representative_entity_id,
            value,
        )
        if previous != value:
            raise RuntimeError("selected row descriptors disagree within orbit")
    if set(descriptor_by_representative) != selected:
        raise RuntimeError("selected orbit row descriptors are incomplete")
    for representative in selected:
        orbit = catalog_orbits.get(representative)
        if orbit is None:
            raise RuntimeError("row plan selects an unknown physical orbit")
        descriptor_kind, descriptor_members = (
            descriptor_by_representative[representative]
        )
        if (
            descriptor_kind != orbit.entity_kind
            or descriptor_members != orbit.member_entity_ids
        ):
            raise RuntimeError(
                "row plan selection is not the catalog's complete orbit"
            )
        expected_owner = catalog.representative_owner_ranks[representative]
        if (
            row_plan.selected_orbit_owner_ranks[representative]
            != expected_owner
        ):
            raise RuntimeError("selected orbit owner differs from actual mesh")
    return selected


def _row_expansion_from_entities(
    entity_expansions: Sequence[PhysicalEntityP6TraceExpansion],
) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    result: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for entity in entity_expansions:
        for row_index, original in enumerate(entity.storage_original_dofs):
            values = np.asarray(
                entity.coefficient_matrix[row_index],
                dtype=np.complex128,
            )
            nonzero = np.flatnonzero(values != 0.0)
            active_rows = np.asarray(
                entity.active_rows[nonzero],
                dtype=PETSc.IntType,
            )
            coefficients = np.asarray(
                values[nonzero],
                dtype=np.complex128,
            )
            if int(original) in result:
                raise RuntimeError("full-p6 storage trace row is duplicated")
            result[int(original)] = (active_rows, coefficients)
    return result


def _owned_cell_expansions(
    *,
    cell_trace_original_dofs: Sequence[Sequence[int]],
    expansion_by_original: Mapping[
        int,
        tuple[np.ndarray, np.ndarray],
    ],
) -> tuple[PhysicalCellP6TraceExpansion, ...]:
    result: list[PhysicalCellP6TraceExpansion] = []
    for local_cell, originals in enumerate(cell_trace_original_dofs):
        active_rows = np.asarray(
            sorted(
                {
                    int(active)
                    for original in originals
                    for active in expansion_by_original[int(original)][0]
                }
            ),
            dtype=PETSc.IntType,
        )
        active_index = {
            int(active): index for index, active in enumerate(active_rows)
        }
        matrix = np.zeros(
            (len(originals), len(active_rows)),
            dtype=np.complex128,
        )
        for row, original in enumerate(originals):
            ids, coefficients = expansion_by_original[int(original)]
            for active, coefficient in zip(ids, coefficients, strict=True):
                matrix[row, active_index[int(active)]] = coefficient
        result.append(
            PhysicalCellP6TraceExpansion(
                local_cell=local_cell,
                storage_original_dofs=np.asarray(
                    originals,
                    dtype=PETSc.IntType,
                ),
                active_rows=active_rows,
                coefficient_matrix=matrix,
            )
        )
    return tuple(result)


def build_actual_selective_p6_trace_expansion(
    *,
    full_p6_storage_space: Any,
    phase_independent_topology: FloquetTraceTopology,
    catalog: SelectiveP6TraceMeshCatalog,
    qualification: P5P6TraceComplementQualification,
    row_plan: SelectiveP6TraceMPIRowPlan,
    coordinate_tolerance: float,
    algebra_tolerance: float = 2.0e-10,
) -> ActualSelectiveP6TraceExpansion:
    """Build ``full-p6 storage trace = C [p5 quotient, selected shell]``."""

    msh = full_p6_storage_space.mesh
    comm = msh.comm
    coordinate_tolerance = float(coordinate_tolerance)
    algebra_tolerance = float(algebra_tolerance)
    if (
        not np.isfinite(coordinate_tolerance)
        or coordinate_tolerance <= 0.0
    ):
        raise ValueError("coordinate tolerance must be positive and finite")
    if not np.isfinite(algebra_tolerance) or algebra_tolerance <= 0.0:
        raise ValueError("algebra tolerance must be positive and finite")
    if catalog.audit.get("pass") is not True:
        raise RuntimeError("actual mesh catalog is not qualified")
    if qualification.audit.get("pass") is not True:
        raise RuntimeError("p5/p6 complement basis is not qualified")
    if catalog.qualification_sha256 != qualification.qualification_sha256:
        raise RuntimeError("catalog and p5/p6 complement basis hashes differ")
    if row_plan.audit.get("pass") is not True or row_plan.actual_mesh is not True:
        raise RuntimeError("selective row plan is not actual-mesh qualified")
    if row_plan.mpi_size != int(comm.size):
        raise RuntimeError("selective row plan MPI size differs from storage")
    if row_plan.geometry_key_sha256 != catalog.trace_geometry_sha256:
        raise RuntimeError("row plan and catalog geometry hashes differ")
    if (
        row_plan.ordered_trace_basis_sha256
        != catalog.ordered_trace_basis_sha256
    ):
        raise RuntimeError("row plan and catalog ordered basis hashes differ")

    _validate_full_p6_storage(full_p6_storage_space, qualification)
    _validate_catalog_topology_identity(
        storage_space=full_p6_storage_space,
        catalog=catalog,
        topology=phase_independent_topology,
    )
    storage_entities, cell_trace_dofs = _global_storage_entity_dofs(
        full_p6_storage_space,
        catalog=catalog,
        coordinate_tolerance=coordinate_tolerance,
    )
    retained_orbits = _discover_actual_orbit_pullbacks(
        catalog=catalog,
        basis_kind="retained",
        tolerance=algebra_tolerance,
    )
    missing_orbits = _discover_actual_orbit_pullbacks(
        catalog=catalog,
        basis_kind="missing",
        tolerance=algebra_tolerance,
    )
    retained_by_entity = {
        entity_id: orbit
        for orbit in retained_orbits
        for entity_id in orbit.member_entity_ids
    }
    missing_by_entity = {
        entity_id: orbit
        for orbit in missing_orbits
        for entity_id in orbit.member_entity_ids
    }
    base_logical = _base_logical_rows(
        catalog=catalog,
        row_plan=row_plan,
        retained_orbits=retained_orbits,
    )
    selected_representatives = _validate_selected_orbits(
        catalog=catalog,
        row_plan=row_plan,
    )
    selected_missing_logical = dict(
        row_plan.logical_orbit_mode_to_petsc_row
    )

    entity_expansions: list[PhysicalEntityP6TraceExpansion] = []
    for storage in storage_entities:
        physical: PhysicalP6TraceEntity = catalog.entities[storage.entity_id]
        retained_orbit = retained_by_entity[physical.entity_id]
        missing_orbit = missing_by_entity[physical.entity_id]
        representative = retained_orbit.representative_entity_id
        if representative != missing_orbit.representative_entity_id:
            raise RuntimeError("retained and missing physical orbits differ")
        shell = getattr(qualification, physical.entity_kind)
        retained_pullback = retained_orbit.representative_to_member[
            physical.entity_id
        ]
        base_rows = np.asarray(
            [
                base_logical[(representative, mode)]
                for mode in range(retained_orbit.dimension)
            ],
            dtype=PETSc.IntType,
        )
        retained_block = (
            shell.retained_embedding @ retained_pullback
        )
        if representative in selected_representatives:
            missing_pullback = missing_orbit.representative_to_member[
                physical.entity_id
            ]
            missing_rows = np.asarray(
                [
                    selected_missing_logical[(representative, mode)]
                    for mode in range(missing_orbit.dimension)
                ],
                dtype=PETSc.IntType,
            )
            missing_block = shell.missing_basis @ missing_pullback
            active_rows = np.concatenate((base_rows, missing_rows))
            coefficients = np.concatenate(
                (retained_block, missing_block),
                axis=1,
            )
        else:
            missing_pullback = None
            missing_rows = np.empty(0, dtype=PETSc.IntType)
            active_rows = base_rows.copy()
            coefficients = retained_block
        entity_expansions.append(
            PhysicalEntityP6TraceExpansion(
                entity_id=physical.entity_id,
                representative_entity_id=representative,
                entity_kind=physical.entity_kind,
                storage_original_dofs=np.asarray(
                    storage.storage_original_dofs,
                    dtype=PETSc.IntType,
                ),
                base_active_rows=base_rows,
                selected_missing_active_rows=missing_rows,
                active_rows=active_rows,
                coefficient_matrix=coefficients,
                retained_pullback=retained_pullback,
                missing_pullback=missing_pullback,
            )
        )

    expansion_by_original = _row_expansion_from_entities(entity_expansions)
    for active_ids, coefficients in expansion_by_original.values():
        active_ids.setflags(write=False)
        coefficients.setflags(write=False)
    full_trace_rows = sum(
        len(entity.storage_original_dofs)
        for entity in entity_expansions
    )
    if len(expansion_by_original) != full_trace_rows:
        raise RuntimeError("full-p6 storage expansion does not cover trace rows")
    expected_full_trace_rows = (
        sum(
            6 if entity.entity_kind == "edge" else 60
            for entity in catalog.entities
        )
    )
    if full_trace_rows != expected_full_trace_rows:
        raise RuntimeError("full-p6 physical trace row count is inconsistent")
    referenced_active = {
        int(active)
        for rows, _coefficients in expansion_by_original.values()
        for active in rows
    }
    if referenced_active != set(range(row_plan.active_rows)):
        raise RuntimeError(
            "physical full-p6 expansion does not cover every active row"
        )
    inactive_representatives = {
        orbit.representative_entity_id
        for orbit in catalog.all_inactive_orbit_numbering.orbits
        if orbit.representative_entity_id not in selected_representatives
    }
    if any(
        expansion.selected_missing_active_rows.size
        for expansion in entity_expansions
        if expansion.representative_entity_id in inactive_representatives
    ):
        raise RuntimeError("inactive missing-p6 orbit received active rows")

    owned_cell_expansions = _owned_cell_expansions(
        cell_trace_original_dofs=cell_trace_dofs,
        expansion_by_original=expansion_by_original,
    )
    ownership_start, ownership_stop = row_plan.petsc_ownership_ranges[
        comm.rank
    ]
    owned_active_rows = np.arange(
        ownership_start,
        ownership_stop,
        dtype=PETSc.IntType,
    )
    qualification_audit = MappingProxyType(
        {
            "schema_version": (
                "task035b.actual-physical-selective-p6-trace-expansion.v1"
            ),
            "pass": True,
            "owner_aware_contiguous_petsc_rows": True,
            "inactive_modes_have_no_petsc_rows": True,
            "full_trace_matrix_constructed": False,
            "ordinary_default_changed": False,
            "full_p6_storage_trace_verified": True,
            "full_p6_storage_interior_verified": True,
            "fixed_p5_storage_rejected": True,
            "p5_riesz_retained_embedding_used": True,
            "selected_missing_riesz_embedding_used": True,
            "actual_dolfinx_orientation_used": True,
            "actual_floquet_pullback_cycles_closed": True,
            "catalog_sha256": catalog.catalog_sha256,
            "trace_geometry_sha256": catalog.trace_geometry_sha256,
            "ordered_trace_basis_sha256": (
                catalog.ordered_trace_basis_sha256
            ),
            "selection_sha256": row_plan.selection_sha256,
            "actual_channel_dwr_computed_by_this_layer": False,
            "selection_authority": "caller_row_plan_only",
        }
    )
    caller = CallerTraceExpansion(
        owned_active_rows=owned_active_rows,
        expansion_by_original=MappingProxyType(expansion_by_original),
        full_trace_rows=full_trace_rows,
        active_rows=row_plan.active_rows,
        qualification_audit=qualification_audit,
    )
    checks = MappingProxyType(
        {
            "storage_is_standard_full_p6_trace_and_interior": True,
            "fixed_p5_storage_not_used_for_missing_shell": True,
            "catalog_topology_and_storage_share_actual_mesh": True,
            "all_physical_p6_trace_rows_covered_once": True,
            "p5_periodic_quotient_rows_match_owner_plan": True,
            "selected_missing_rows_match_complete_orbits": True,
            "actual_dolfinx_retained_pullback_cycles_close": True,
            "actual_dolfinx_missing_pullback_cycles_close": True,
            "active_coordinate_coverage_is_exact": True,
            "inactive_missing_modes_have_no_petsc_rows": True,
            "full_p6_trace_matrix_not_constructed": True,
            "local_tensor_not_constructed": True,
            "actual_dwr_not_computed": True,
        }
    )
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035b.actual-selective-p6-trace-expansion-bridge.v1"
            ),
            "status": "actual_selective_p6_trace_expansion_pass",
            "pass": True,
            "mpi_size": int(comm.size),
            "physical_entity_count": len(entity_expansions),
            "owned_cell_count": len(owned_cell_expansions),
            "full_p6_storage_local_dimension": 882,
            "full_p6_storage_local_trace_dimension": 432,
            "full_p6_storage_local_interior_dimension": 450,
            "full_p6_storage_trace_rows": full_trace_rows,
            "p5_periodic_quotient_rows": row_plan.active_base_rows,
            "selected_missing_orbit_count": len(
                selected_representatives
            ),
            "selected_missing_rows": row_plan.quotient_active_increment,
            "active_rows": row_plan.active_rows,
            "inactive_missing_orbit_count": len(
                inactive_representatives
            ),
            "inactive_missing_petsc_rows": 0,
            "catalog_sha256": catalog.catalog_sha256,
            "selection_sha256": row_plan.selection_sha256,
            "matrix_constructed": False,
            "local_tensor_constructed": False,
            "actual_channel_dwr_computed": False,
            "ordinary_default_changed": False,
            "checks": checks,
        }
    )
    return ActualSelectiveP6TraceExpansion(
        caller_trace_expansion=caller,
        entity_expansions=tuple(entity_expansions),
        owned_cell_expansions=owned_cell_expansions,
        storage_expansion_by_original=expansion_by_original,
        base_logical_rows=base_logical,
        selected_missing_logical_rows=selected_missing_logical,
        full_p6_storage_trace_rows=full_trace_rows,
        p5_periodic_quotient_rows=row_plan.active_base_rows,
        selected_missing_rows=row_plan.quotient_active_increment,
        active_rows=row_plan.active_rows,
        audit=audit,
    )


def constrain_physical_cell_schur(
    cell_expansion: PhysicalCellP6TraceExpansion,
    storage_schur: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return active IDs and ``C_K^H S_K C_K`` without allocating PETSc rows."""

    schur = np.asarray(storage_schur, dtype=np.complex128)
    expected = len(cell_expansion.storage_original_dofs)
    if schur.shape != (expected, expected):
        raise ValueError("storage cell Schur tensor has the wrong shape")
    if not np.all(np.isfinite(schur)):
        raise FloatingPointError("storage cell Schur tensor contains NaN or Inf")
    expansion = np.asarray(
        cell_expansion.coefficient_matrix,
        dtype=np.complex128,
    )
    constrained = expansion.conj().T @ schur @ expansion
    return cell_expansion.active_rows.copy(), constrained


__all__ = [
    "ActualSelectiveP6TraceExpansion",
    "PhysicalCellP6TraceExpansion",
    "PhysicalEntityP6TraceExpansion",
    "build_actual_selective_p6_trace_expansion",
    "constrain_physical_cell_schur",
]
