"""Actual-mesh catalog for the physical p5-to-p6 H(curl) trace shell.

This module is the mesh-bound bridge between the phase-independent p5
Floquet topology and the pure selective-p6 orbit/row-planning layers.  It
enumerates every physical edge and face of an actual affine hexahedral
DOLFINx mesh, including entities that are not on a periodic boundary.

The bridge deliberately stops before channel DWR, entity selection, matrix
assembly, or active-row allocation.  Its outputs are:

* partition-independent canonical physical entity IDs and geometry hashes;
* qualified p6 missing-shell periodic/Floquet pullbacks;
* complete periodic orbits, including singleton interior entities; and
* the actual owner rank of each canonical orbit representative.

Those representative owners and the helper at the end of this module are
direct inputs to ``build_selective_p6_trace_mpi_row_plan`` after a separate
actual-channel DWR and exact-sequence closure have selected whole orbits.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from numbers import Integral
from types import MappingProxyType
from typing import Any, Literal, Mapping, Sequence

import numpy as np

from dolfinx import cpp

from src.adaptivity.p6_trace_complement_qualification import (
    P5P6TraceComplementQualification,
)
from src.adaptivity.selective_p6_trace_orbits import (
    MissingP6TraceEntity,
    PeriodicMissingTraceRelation,
    SelectiveP6TraceNumbering,
    build_selective_p6_trace_numbering,
    validate_missing_trace_intertwining,
)
from src.constraints.high_order_floquet_trace import (
    FloquetTraceTopology,
    build_missing_p6_trace_orbit_identity_input,
    edge_coefficient_transform,
    face_coefficient_transform,
)
from src.geometry.tetra_mesh_audit import canonical_entity_key


TraceEntityKind = Literal["edge", "face"]
PeriodicDirection = Literal["x", "y", "corner"]
EntityGeometryKey = tuple[tuple[int, int, int], ...]

_ENTITY_DIMENSION = {"edge": 1, "face": 2}
_ENTITY_ORDER = {"edge": 0, "face": 1}
_MISSING_MODE_COUNT = {"edge": 1, "face": 20}
_DIRECTION_ORDER = {"x": 0, "y": 1, "corner": 2}


def _validated_sha256(value: str, *, label: str) -> str:
    normalized = str(value).lower()
    try:
        valid = len(normalized) == 64 and len(bytes.fromhex(normalized)) == 32
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(f"{label} must contain 64 hexadecimal characters")
    return normalized


def _complex_matrix_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values, dtype=np.dtype("<c16"))
    digest = hashlib.sha256()
    digest.update(np.asarray(array.shape, dtype="<i8").tobytes())
    digest.update(array.tobytes())
    return digest.hexdigest()


def _payload_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _unit_phase(value: complex, *, label: str, tolerance: float) -> complex:
    phase = complex(value)
    if not np.isfinite(phase.real) or not np.isfinite(phase.imag):
        raise FloatingPointError(f"{label} contains NaN or Inf")
    if abs(abs(phase) - 1.0) > tolerance:
        raise ValueError(f"{label} must have unit magnitude")
    return phase


@dataclass(frozen=True)
class PhysicalP6TraceEntity:
    """One canonical physical edge or face in the actual mesh."""

    entity_id: int
    entity_kind: TraceEntityKind
    geometry_key: EntityGeometryKey
    dolfinx_global_entity_id: int
    owner_rank: int
    missing_mode_count: int
    required_periodic_directions: tuple[PeriodicDirection, ...]
    shell_sha256: str

    def __post_init__(self) -> None:
        if int(self.entity_id) < 0:
            raise ValueError("canonical physical entity ID must be nonnegative")
        if self.entity_kind not in _ENTITY_DIMENSION:
            raise ValueError("physical p6 trace entity must be an edge or face")
        if int(self.dolfinx_global_entity_id) < 0:
            raise ValueError("DOLFINx global entity ID must be nonnegative")
        if int(self.owner_rank) < 0:
            raise ValueError("physical entity owner rank must be nonnegative")
        expected_modes = _MISSING_MODE_COUNT[self.entity_kind]
        if int(self.missing_mode_count) != expected_modes:
            raise ValueError(
                f"{self.entity_kind} missing-shell mode count must be "
                f"{expected_modes}"
            )
        key = tuple(
            tuple(int(component) for component in point)
            for point in self.geometry_key
        )
        expected_vertices = 2 if self.entity_kind == "edge" else 4
        if len(key) != expected_vertices or any(len(point) != 3 for point in key):
            raise ValueError(
                f"{self.entity_kind} geometry key must contain "
                f"{expected_vertices} three-component vertices"
            )
        if tuple(sorted(key)) != key or len(set(key)) != len(key):
            raise ValueError("physical entity geometry key is not canonical")
        directions = tuple(self.required_periodic_directions)
        if len(set(directions)) != len(directions):
            raise ValueError("physical entity periodic directions are duplicated")
        if any(direction not in _DIRECTION_ORDER for direction in directions):
            raise ValueError("physical entity has an invalid periodic direction")
        directions = tuple(
            sorted(directions, key=_DIRECTION_ORDER.__getitem__)
        )
        object.__setattr__(self, "entity_id", int(self.entity_id))
        object.__setattr__(
            self,
            "dolfinx_global_entity_id",
            int(self.dolfinx_global_entity_id),
        )
        object.__setattr__(self, "owner_rank", int(self.owner_rank))
        object.__setattr__(self, "geometry_key", key)
        object.__setattr__(
            self,
            "required_periodic_directions",
            directions,
        )
        object.__setattr__(
            self,
            "shell_sha256",
            _validated_sha256(
                self.shell_sha256,
                label="trace complement shell SHA256",
            ),
        )


@dataclass(frozen=True)
class PhysicalP6TracePeriodicRelation:
    """Canonical metadata for one qualified periodic missing-shell relation."""

    slave_entity_id: int
    master_entity_id: int
    direction: PeriodicDirection
    periodic_pair_key: tuple[int, ...]
    entity_vertex_permutation: tuple[int, ...]
    dolfinx_entity_vertex_permutation: tuple[int, ...]
    floquet_phase: complex
    coefficient_pullback_sha256: str
    dolfinx_coefficient_pullback: np.ndarray
    dolfinx_coefficient_pullback_sha256: str

    def __post_init__(self) -> None:
        if int(self.slave_entity_id) < 0 or int(self.master_entity_id) < 0:
            raise ValueError("periodic canonical entity IDs must be nonnegative")
        if int(self.slave_entity_id) == int(self.master_entity_id):
            raise ValueError("periodic relation cannot pair an entity to itself")
        if self.direction not in _DIRECTION_ORDER:
            raise ValueError("periodic relation direction is invalid")
        pair_key = tuple(int(value) for value in self.periodic_pair_key)
        if len(pair_key) != 6:
            raise ValueError("periodic pair key must contain six integers")
        permutation = tuple(
            int(value) for value in self.entity_vertex_permutation
        )
        if sorted(permutation) != list(range(len(permutation))):
            raise ValueError("periodic entity vertex permutation is invalid")
        dolfinx_permutation = tuple(
            int(value) for value in self.dolfinx_entity_vertex_permutation
        )
        if sorted(dolfinx_permutation) != list(
            range(len(dolfinx_permutation))
        ):
            raise ValueError(
                "DOLFINx periodic entity vertex permutation is invalid"
            )
        dolfinx_pullback = np.array(
            self.dolfinx_coefficient_pullback,
            dtype=np.complex128,
            copy=True,
        )
        if (
            dolfinx_pullback.ndim != 2
            or dolfinx_pullback.shape[0] != dolfinx_pullback.shape[1]
            or dolfinx_pullback.shape[0] == 0
            or not np.all(np.isfinite(dolfinx_pullback))
        ):
            raise ValueError(
                "DOLFINx periodic coefficient pullback must be a finite "
                "nonempty square matrix"
            )
        dolfinx_pullback.setflags(write=False)
        object.__setattr__(self, "slave_entity_id", int(self.slave_entity_id))
        object.__setattr__(self, "master_entity_id", int(self.master_entity_id))
        object.__setattr__(self, "periodic_pair_key", pair_key)
        object.__setattr__(
            self,
            "entity_vertex_permutation",
            permutation,
        )
        object.__setattr__(
            self,
            "dolfinx_entity_vertex_permutation",
            dolfinx_permutation,
        )
        object.__setattr__(self, "floquet_phase", complex(self.floquet_phase))
        object.__setattr__(
            self,
            "coefficient_pullback_sha256",
            _validated_sha256(
                self.coefficient_pullback_sha256,
                label="periodic coefficient pullback SHA256",
            ),
        )
        object.__setattr__(
            self,
            "dolfinx_coefficient_pullback",
            dolfinx_pullback,
        )
        dolfinx_hash = _validated_sha256(
            self.dolfinx_coefficient_pullback_sha256,
            label="DOLFINx periodic coefficient pullback SHA256",
        )
        if dolfinx_hash != _complex_matrix_sha256(dolfinx_pullback):
            raise RuntimeError(
                "DOLFINx coefficient pullback hash does not match its matrix"
            )
        object.__setattr__(
            self,
            "dolfinx_coefficient_pullback_sha256",
            dolfinx_hash,
        )


@dataclass(frozen=True)
class SelectedP6TraceOrbitOwnerInputs:
    """Whole-orbit owner inputs for the pure MPI row planner."""

    selected_representative_entity_ids: tuple[int, ...]
    selected_orbit_owner_ranks: Mapping[int, int]
    owned_selected_trace_row_counts_by_rank: tuple[int, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "selected_orbit_owner_ranks",
            MappingProxyType(
                {
                    int(representative): int(owner)
                    for representative, owner in (
                        self.selected_orbit_owner_ranks.items()
                    )
                }
            ),
        )


@dataclass(frozen=True)
class SelectiveP6TraceMeshCatalog:
    """Qualified actual-mesh inventory with no selected or active p6 rows."""

    mpi_size: int
    entities: tuple[PhysicalP6TraceEntity, ...]
    missing_trace_entities: tuple[MissingP6TraceEntity, ...]
    periodic_relations: tuple[PeriodicMissingTraceRelation, ...]
    relation_metadata: tuple[PhysicalP6TracePeriodicRelation, ...]
    all_inactive_orbit_numbering: SelectiveP6TraceNumbering
    representative_owner_ranks: Mapping[int, int]
    trace_geometry_sha256: str
    ordered_trace_basis_sha256: str
    catalog_sha256: str
    qualification_sha256: str
    floquet_phase_x: complex
    floquet_phase_y: complex
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.audit.get("pass") is not True:
            raise ValueError("selective p6 trace mesh catalog is unqualified")
        object.__setattr__(
            self,
            "representative_owner_ranks",
            MappingProxyType(
                {
                    int(representative): int(owner)
                    for representative, owner in (
                        self.representative_owner_ranks.items()
                    )
                }
            ),
        )
        for field_name in (
            "trace_geometry_sha256",
            "ordered_trace_basis_sha256",
            "catalog_sha256",
            "qualification_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _validated_sha256(
                    getattr(self, field_name),
                    label=field_name.replace("_", " "),
                ),
            )


@dataclass(frozen=True)
class _OwnedEntityPacket:
    entity_kind: TraceEntityKind
    dolfinx_global_entity_id: int
    owner_rank: int
    geometry_key: EntityGeometryKey
    coordinates: tuple[tuple[float, float, float], ...]


def _space_validation_issue(
    retained_trace_space: Any,
    topology: FloquetTraceTopology,
) -> str | None:
    try:
        msh = retained_trace_space.mesh
        if "hexahedron" not in str(msh.basix_cell()).lower():
            return "actual selective p6 trace catalog requires hexahedra"
        if int(topology.key.degree) != 5:
            return "actual selective p6 trace catalog requires p5 topology"
        if tuple(topology.key.periodic_axes) != ("x", "y"):
            return "actual selective p6 trace catalog requires x/y periodic axes"
        element = retained_trace_space.element.basix_element
        if str(element.family) != str(topology.key.element_family):
            return "retained space family disagrees with Floquet topology"
        expected_by_dimension = {1: 5, 2: 40}
        for dimension, expected in expected_by_dimension.items():
            entity_dofs = element.entity_dofs[dimension]
            if not entity_dofs or any(
                len(dofs) != expected for dofs in entity_dofs
            ):
                return (
                    "retained space does not expose the qualified p5 "
                    f"{dimension}D trace layout"
                )
    except Exception as exc:  # pragma: no cover - fail-closed diagnostic
        return f"retained space/topology validation raised {type(exc).__name__}: {exc}"
    return None


def _owned_entity_packets(
    msh: Any,
    *,
    entity_kind: TraceEntityKind,
    coordinate_tolerance: float,
) -> tuple[_OwnedEntityPacket, ...]:
    dimension = _ENTITY_DIMENSION[entity_kind]
    msh.topology.create_entities(dimension)
    msh.topology.create_connectivity(dimension, msh.topology.dim)
    entity_map = msh.topology.index_map(dimension)
    owned_entities = np.arange(entity_map.size_local, dtype=np.int32)
    global_ids = entity_map.local_to_global(owned_entities).astype(np.int64)
    geometry = cpp.mesh.entities_to_geometry(
        msh._cpp_object,
        dimension,
        owned_entities,
        True,
    )
    packets: list[_OwnedEntityPacket] = []
    expected_vertices = 2 if entity_kind == "edge" else 4
    for global_id, geometry_dofs in zip(global_ids, geometry, strict=True):
        coordinates = np.asarray(
            msh.geometry.x[np.asarray(geometry_dofs, dtype=np.int64)],
            dtype=np.float64,
        )
        if coordinates.shape != (expected_vertices, 3):
            raise RuntimeError(
                "actual selective trace catalog supports affine "
                f"{entity_kind}s with {expected_vertices} vertices"
            )
        packets.append(
            _OwnedEntityPacket(
                entity_kind=entity_kind,
                dolfinx_global_entity_id=int(global_id),
                owner_rank=int(msh.comm.rank),
                geometry_key=canonical_entity_key(
                    coordinates,
                    coordinate_tolerance,
                ),
                coordinates=tuple(
                    tuple(float(component) for component in point)
                    for point in coordinates
                ),
            )
        )
    expected_global = int(entity_map.size_global)
    if len(packets) != int(entity_map.size_local):
        raise RuntimeError("owned physical entity enumeration is incomplete")
    if any(
        int(value) != expected_global
        for value in msh.comm.allgather(expected_global)
    ):
        raise RuntimeError("DOLFINx global entity count differs across ranks")
    return tuple(packets)


def _global_entity_packets(
    msh: Any,
    *,
    coordinate_tolerance: float,
) -> tuple[_OwnedEntityPacket, ...]:
    local = tuple(
        packet
        for kind in ("edge", "face")
        for packet in _owned_entity_packets(
            msh,
            entity_kind=kind,
            coordinate_tolerance=coordinate_tolerance,
        )
    )
    gathered = tuple(
        packet for rank_packet in msh.comm.allgather(local) for packet in rank_packet
    )
    by_global_id: dict[tuple[str, int], _OwnedEntityPacket] = {}
    by_geometry: dict[tuple[str, EntityGeometryKey], _OwnedEntityPacket] = {}
    for packet in gathered:
        global_key = (
            packet.entity_kind,
            packet.dolfinx_global_entity_id,
        )
        if global_key in by_global_id:
            raise RuntimeError(
                "a DOLFINx physical entity has multiple declared owners"
            )
        geometry_key = (packet.entity_kind, packet.geometry_key)
        if geometry_key in by_geometry:
            raise RuntimeError(
                "duplicate physical trace entity geometry key"
            )
        by_global_id[global_key] = packet
        by_geometry[geometry_key] = packet

    expected_by_kind: dict[str, int] = {}
    for kind in ("edge", "face"):
        dimension = _ENTITY_DIMENSION[kind]
        expected_by_kind[kind] = int(
            msh.topology.index_map(dimension).size_global
        )
        actual = sum(packet.entity_kind == kind for packet in gathered)
        if actual != expected_by_kind[kind]:
            raise RuntimeError(
                f"global {kind} catalog count disagrees with DOLFINx: "
                f"catalog={actual}, DOLFINx={expected_by_kind[kind]}"
            )
    return tuple(
        sorted(
            gathered,
            key=lambda packet: (
                _ENTITY_ORDER[packet.entity_kind],
                packet.geometry_key,
            ),
        )
    )


def _mesh_bounds(
    packets: Sequence[_OwnedEntityPacket],
) -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(
        [
            point
            for packet in packets
            for point in packet.coordinates
        ],
        dtype=np.float64,
    )
    if points.ndim != 2 or points.shape[1] != 3 or len(points) == 0:
        raise RuntimeError("actual mesh trace entity catalog is empty")
    lower = np.min(points, axis=0)
    upper = np.max(points, axis=0)
    if np.any(~np.isfinite(lower)) or np.any(~np.isfinite(upper)):
        raise FloatingPointError("actual mesh bounds contain NaN or Inf")
    return lower, upper


def _on_plane(
    coordinates: np.ndarray,
    *,
    axis: int,
    value: float,
    tolerance: float,
) -> bool:
    return bool(np.all(np.abs(coordinates[:, axis] - value) <= tolerance))


def _required_periodic_directions(
    packet: _OwnedEntityPacket,
    *,
    lower: np.ndarray,
    upper: np.ndarray,
    tolerance: float,
) -> tuple[PeriodicDirection, ...]:
    coordinates = np.asarray(packet.coordinates, dtype=np.float64)
    x_min = _on_plane(
        coordinates,
        axis=0,
        value=float(lower[0]),
        tolerance=tolerance,
    )
    x_max = _on_plane(
        coordinates,
        axis=0,
        value=float(upper[0]),
        tolerance=tolerance,
    )
    y_min = _on_plane(
        coordinates,
        axis=1,
        value=float(lower[1]),
        tolerance=tolerance,
    )
    y_max = _on_plane(
        coordinates,
        axis=1,
        value=float(upper[1]),
        tolerance=tolerance,
    )
    directions: list[PeriodicDirection] = []
    if packet.entity_kind == "face":
        if x_min or x_max:
            directions.append("x")
        if y_min or y_max:
            directions.append("y")
    else:
        # This is the same corner ownership convention used by the production
        # high-order Floquet topology builder.  It avoids duplicate edge
        # constraints while retaining the x/y/corner closure cycle.
        if (x_min or x_max) and not y_max:
            directions.append("x")
        if (y_min or y_max) and not x_max:
            directions.append("y")
        if (x_min and y_min) or (x_max and y_max):
            directions.append("corner")
    return tuple(directions)


def _expected_p5_p6_transforms(
    *,
    entity_kind: TraceEntityKind,
    vertex_permutation: tuple[int, ...],
) -> tuple[np.ndarray, np.ndarray]:
    if entity_kind == "edge":
        if vertex_permutation not in {(0, 1), (1, 0)}:
            raise RuntimeError("periodic edge orientation is invalid")
        reversed_orientation = vertex_permutation == (1, 0)
        return (
            edge_coefficient_transform(
                5,
                reversed_orientation=reversed_orientation,
                cell_type="hexahedron",
            ),
            edge_coefficient_transform(
                6,
                reversed_orientation=reversed_orientation,
                cell_type="hexahedron",
            ),
        )
    if len(vertex_permutation) != 4:
        raise RuntimeError("periodic hexahedral face permutation is invalid")
    return (
        face_coefficient_transform(5, vertex_permutation),
        face_coefficient_transform(6, vertex_permutation),
    )


def _canonical_periodic_vertex_permutation(
    *,
    slave: _OwnedEntityPacket,
    master: _OwnedEntityPacket,
    direction: PeriodicDirection,
    lower: np.ndarray,
    upper: np.ndarray,
    coordinate_tolerance: float,
) -> tuple[int, ...]:
    """Validate a translation pair in canonical physical vertex ordering."""

    shift = np.zeros(3, dtype=np.float64)
    if direction in {"x", "corner"}:
        shift[0] = float(upper[0] - lower[0])
    if direction in {"y", "corner"}:
        shift[1] = float(upper[1] - lower[1])
    shifted_slave_key = canonical_entity_key(
        np.asarray(slave.coordinates, dtype=np.float64) - shift,
        coordinate_tolerance,
    )
    if shifted_slave_key != master.geometry_key:
        raise RuntimeError(
            "periodic entity pair is not a canonical x/y translation"
        )
    return tuple(range(len(slave.geometry_key)))


def _local_topology_validation_issues(
    *,
    topology: FloquetTraceTopology,
    packet_by_global_id: Mapping[tuple[str, int], _OwnedEntityPacket],
    tolerance: float,
) -> tuple[str, ...]:
    issues: list[str] = []
    for block_index, block in enumerate(topology.blocks):
        try:
            if not block.has_physical_entity_identity:
                raise RuntimeError("block lacks physical entity identity")
            if block.cell_type != "hexahedron":
                raise RuntimeError("block is not a hexahedral relation")
            kind = block.entity_kind
            slave = packet_by_global_id[
                (kind, int(block.slave_entity_id))
            ]
            master = packet_by_global_id[
                (kind, int(block.master_entity_id))
            ]
            if slave.geometry_key != block.slave_entity_geometry_key:
                raise RuntimeError("slave geometry key disagrees with actual mesh")
            if master.geometry_key != block.master_entity_geometry_key:
                raise RuntimeError("master geometry key disagrees with actual mesh")
            expected_p5, _expected_p6 = _expected_p5_p6_transforms(
                entity_kind=kind,
                vertex_permutation=block.entity_vertex_permutation,
            )
            error = float(
                np.linalg.norm(
                    np.asarray(block.coefficient_transform) - expected_p5,
                    ord="fro",
                )
                / max(
                    1.0,
                    float(np.linalg.norm(expected_p5, ord="fro")),
                )
            )
            if error > tolerance:
                raise RuntimeError(
                    "p5 coefficient transform disagrees with the qualified "
                    f"orientation basis: relative_error={error:.3e}"
                )
        except Exception as exc:
            issues.append(
                f"rank-local Floquet block {block_index}: "
                f"{type(exc).__name__}: {exc}"
            )
    return tuple(issues)


def _trace_geometry_sha256(
    packets: Sequence[_OwnedEntityPacket],
) -> str:
    return _payload_sha256(
        {
            "schema": "task035b.actual-p6-trace-geometry.v1",
            "cell_type": "hexahedron",
            "entities": [
                {
                    "entity_id": entity_id,
                    "entity_kind": packet.entity_kind,
                    "geometry_key": packet.geometry_key,
                }
                for entity_id, packet in enumerate(packets)
            ],
        }
    )


def _ordered_trace_basis_sha256(
    *,
    packets: Sequence[_OwnedEntityPacket],
    qualification: P5P6TraceComplementQualification,
) -> str:
    return _payload_sha256(
        {
            "schema": "task035b.actual-ordered-p6-trace-basis.v1",
            "qualification_sha256": qualification.qualification_sha256,
            "p5_element_sha256": qualification.p5_element_sha256,
            "p6_element_sha256": qualification.p6_element_sha256,
            "entities": [
                {
                    "entity_id": entity_id,
                    "entity_kind": packet.entity_kind,
                    "geometry_key": packet.geometry_key,
                    "shell_sha256": getattr(
                        qualification,
                        packet.entity_kind,
                    ).shell_sha256,
                    "mode_coefficient_sha256": [
                        mode.coefficient_sha256
                        for mode in getattr(
                            qualification,
                            packet.entity_kind,
                        ).mode_metadata
                    ],
                }
                for entity_id, packet in enumerate(packets)
            ],
        }
    )


def build_selective_p6_trace_mesh_catalog(
    *,
    retained_trace_space: Any,
    phase_independent_topology: FloquetTraceTopology,
    qualification: P5P6TraceComplementQualification,
    coordinate_tolerance: float,
    floquet_phase_x: complex,
    floquet_phase_y: complex,
    expected_qualification_sha256: str,
    expected_ordered_trace_basis_sha256: str | None = None,
    algebra_tolerance: float = 2.0e-10,
) -> SelectiveP6TraceMeshCatalog:
    """Build the all-inactive physical p6 trace catalog on an actual mesh."""

    msh = retained_trace_space.mesh
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
    expected_qualification = _validated_sha256(
        expected_qualification_sha256,
        label="expected qualification SHA256",
    )
    actual_qualification = _validated_sha256(
        qualification.qualification_sha256,
        label="qualification SHA256",
    )
    if qualification.audit.get("pass") is not True:
        raise RuntimeError("p5/p6 trace complement qualification did not pass")
    if expected_qualification != actual_qualification:
        raise RuntimeError("p5/p6 trace complement basis hash mismatch")

    phase_x = _unit_phase(
        floquet_phase_x,
        label="x Floquet phase",
        tolerance=algebra_tolerance,
    )
    phase_y = _unit_phase(
        floquet_phase_y,
        label="y Floquet phase",
        tolerance=algebra_tolerance,
    )
    metadata = (
        coordinate_tolerance,
        algebra_tolerance,
        phase_x,
        phase_y,
        expected_qualification,
    )
    if any(value != metadata for value in comm.allgather(metadata)):
        raise RuntimeError("actual trace catalog metadata differs across ranks")

    local_space_issue = _space_validation_issue(
        retained_trace_space,
        phase_independent_topology,
    )
    space_issues = tuple(
        issue
        for issue in comm.allgather(local_space_issue)
        if issue is not None
    )
    if space_issues:
        raise RuntimeError(
            "retained space/Floquet topology validation failed: "
            + "; ".join(space_issues)
        )

    packets = _global_entity_packets(
        msh,
        coordinate_tolerance=coordinate_tolerance,
    )
    trace_geometry_hash = _trace_geometry_sha256(packets)
    ordered_basis_hash = _ordered_trace_basis_sha256(
        packets=packets,
        qualification=qualification,
    )
    if expected_ordered_trace_basis_sha256 is not None:
        expected_basis = _validated_sha256(
            expected_ordered_trace_basis_sha256,
            label="expected ordered trace basis SHA256",
        )
        if expected_basis != ordered_basis_hash:
            raise RuntimeError("ordered physical p6 trace basis hash mismatch")

    lower, upper = _mesh_bounds(packets)
    if (
        float(upper[0] - lower[0]) <= coordinate_tolerance
        or float(upper[1] - lower[1]) <= coordinate_tolerance
    ):
        raise RuntimeError("actual mesh has a degenerate periodic span")

    packet_by_global_id = {
        (packet.entity_kind, packet.dolfinx_global_entity_id): packet
        for packet in packets
    }
    local_issues = _local_topology_validation_issues(
        topology=phase_independent_topology,
        packet_by_global_id=packet_by_global_id,
        tolerance=algebra_tolerance,
    )
    topology_issues = tuple(
        issue
        for rank_issues in comm.allgather(local_issues)
        for issue in rank_issues
    )
    if topology_issues:
        raise RuntimeError(
            "phase-independent Floquet topology validation failed: "
            + "; ".join(topology_issues)
        )

    identity = build_missing_p6_trace_orbit_identity_input(
        phase_independent_topology,
        mesh_sha256=trace_geometry_hash,
        comm=comm,
    )
    packet_to_canonical_id = {
        (packet.entity_kind, packet.dolfinx_global_entity_id): entity_id
        for entity_id, packet in enumerate(packets)
    }
    required_directions = {
        entity_id: _required_periodic_directions(
            packet,
            lower=lower,
            upper=upper,
            tolerance=coordinate_tolerance,
        )
        for entity_id, packet in enumerate(packets)
    }

    physical_entities = tuple(
        PhysicalP6TraceEntity(
            entity_id=entity_id,
            entity_kind=packet.entity_kind,
            geometry_key=packet.geometry_key,
            dolfinx_global_entity_id=packet.dolfinx_global_entity_id,
            owner_rank=packet.owner_rank,
            missing_mode_count=_MISSING_MODE_COUNT[packet.entity_kind],
            required_periodic_directions=required_directions[entity_id],
            shell_sha256=getattr(
                qualification,
                packet.entity_kind,
            ).shell_sha256,
        )
        for entity_id, packet in enumerate(packets)
    )
    missing_entities = tuple(
        MissingP6TraceEntity(
            entity_id=entity.entity_id,
            entity_kind=entity.entity_kind,
            missing_mode_count=entity.missing_mode_count,
            required_periodic_directions=(
                entity.required_periodic_directions
            ),
        )
        for entity in physical_entities
    )

    phase_by_direction = {
        "x": phase_x,
        "y": phase_y,
        "corner": phase_x * phase_y,
    }
    periodic_relations: list[PeriodicMissingTraceRelation] = []
    relation_metadata: list[PhysicalP6TracePeriodicRelation] = []
    incidence: dict[tuple[int, str], int] = {}
    for relation in identity.relations:
        kind = relation.entity_kind
        slave_key = (kind, relation.slave_entity_id)
        master_key = (kind, relation.master_entity_id)
        try:
            slave_id = packet_to_canonical_id[slave_key]
            master_id = packet_to_canonical_id[master_key]
        except KeyError as exc:
            raise RuntimeError(
                "periodic topology refers to a missing actual mesh entity"
            ) from exc
        slave_packet = packets[slave_id]
        master_packet = packets[master_id]
        if (
            slave_packet.geometry_key
            != relation.slave_entity_geometry_key
            or master_packet.geometry_key
            != relation.master_entity_geometry_key
        ):
            raise RuntimeError(
                "periodic topology geometry identity disagrees with actual mesh"
            )
        shell = getattr(qualification, kind)
        (
            dolfinx_retained_transform,
            dolfinx_enriched_transform,
        ) = _expected_p5_p6_transforms(
            entity_kind=kind,
            vertex_permutation=relation.entity_vertex_permutation,
        )
        dolfinx_projection = validate_missing_trace_intertwining(
            enriched_transform=dolfinx_enriched_transform,
            retained_transform=dolfinx_retained_transform,
            retained_embedding=shell.retained_embedding,
            missing_embedding=shell.missing_basis,
            tolerance=algebra_tolerance,
        )
        canonical_permutation = _canonical_periodic_vertex_permutation(
            slave=slave_packet,
            master=master_packet,
            direction=relation.direction,
            lower=lower,
            upper=upper,
            coordinate_tolerance=coordinate_tolerance,
        )
        retained_transform, enriched_transform = _expected_p5_p6_transforms(
            entity_kind=kind,
            vertex_permutation=canonical_permutation,
        )
        projection = validate_missing_trace_intertwining(
            enriched_transform=enriched_transform,
            retained_transform=retained_transform,
            retained_embedding=shell.retained_embedding,
            missing_embedding=shell.missing_basis,
            tolerance=algebra_tolerance,
        )
        periodic_relation = PeriodicMissingTraceRelation(
            slave_entity_id=slave_id,
            master_entity_id=master_id,
            direction=relation.direction,
            intertwining_projection=projection,
            floquet_phase=phase_by_direction[relation.direction],
            phase_tolerance=algebra_tolerance,
        )
        periodic_relations.append(periodic_relation)
        dolfinx_pullback = (
            phase_by_direction[relation.direction]
            * dolfinx_projection.induced_missing_transform
        )
        relation_metadata.append(
            PhysicalP6TracePeriodicRelation(
                slave_entity_id=slave_id,
                master_entity_id=master_id,
                direction=relation.direction,
                periodic_pair_key=relation.periodic_pair_key,
                entity_vertex_permutation=canonical_permutation,
                dolfinx_entity_vertex_permutation=(
                    relation.entity_vertex_permutation
                ),
                floquet_phase=phase_by_direction[relation.direction],
                coefficient_pullback_sha256=_complex_matrix_sha256(
                    periodic_relation.coefficient_pullback
                ),
                dolfinx_coefficient_pullback=dolfinx_pullback,
                dolfinx_coefficient_pullback_sha256=(
                    _complex_matrix_sha256(dolfinx_pullback)
                ),
            )
        )
        for entity_id in (slave_id, master_id):
            incidence_key = (entity_id, relation.direction)
            incidence[incidence_key] = incidence.get(incidence_key, 0) + 1

    expected_incidence = {
        (entity.entity_id, direction)
        for entity in physical_entities
        for direction in entity.required_periodic_directions
    }
    observed_incidence = set(incidence)
    if observed_incidence != expected_incidence:
        missing = sorted(expected_incidence - observed_incidence)
        unexpected = sorted(observed_incidence - expected_incidence)
        raise RuntimeError(
            "periodic entity relation coverage is incomplete or unexpected: "
            f"missing={missing[:8]}, unexpected={unexpected[:8]}"
        )
    multiply_incident = sorted(
        key for key, count in incidence.items() if count != 1
    )
    if multiply_incident:
        raise RuntimeError(
            "periodic entity has duplicate mates for one direction: "
            f"{multiply_incident[:8]}"
        )

    all_inactive = build_selective_p6_trace_numbering(
        entities=missing_entities,
        periodic_relations=tuple(periodic_relations),
        selected_entity_ids=(),
        full3d_base_dofs=0,
        active_base_rows=0,
        full3d_dof_limit=None,
        tolerance=algebra_tolerance,
    )
    if all_inactive.active_row_increment != 0:
        raise RuntimeError("mesh catalog unexpectedly allocated active p6 rows")
    if all_inactive.inactive_entity_ids != tuple(
        entity.entity_id for entity in physical_entities
    ):
        raise RuntimeError("mesh catalog orbits do not cover every entity")

    representative_owners = {
        orbit.representative_entity_id: physical_entities[
            orbit.representative_entity_id
        ].owner_rank
        for orbit in all_inactive.orbits
    }
    if any(
        owner < 0 or owner >= int(comm.size)
        for owner in representative_owners.values()
    ):
        raise RuntimeError("canonical orbit representative owner is invalid")

    catalog_hash = _payload_sha256(
        {
            "schema": "task035b.actual-p6-trace-mesh-catalog.v1",
            "trace_geometry_sha256": trace_geometry_hash,
            "ordered_trace_basis_sha256": ordered_basis_hash,
            "qualification_sha256": actual_qualification,
            "floquet_phase_x": [phase_x.real, phase_x.imag],
            "floquet_phase_y": [phase_y.real, phase_y.imag],
            "relations": [
                {
                    "slave_entity_id": relation.slave_entity_id,
                    "master_entity_id": relation.master_entity_id,
                    "direction": relation.direction,
                    "periodic_pair_key": relation.periodic_pair_key,
                    "entity_vertex_permutation": (
                        relation.entity_vertex_permutation
                    ),
                    "floquet_phase": [
                        relation.floquet_phase.real,
                        relation.floquet_phase.imag,
                    ],
                    "coefficient_pullback_sha256": (
                        relation.coefficient_pullback_sha256
                    ),
                }
                for relation in relation_metadata
            ],
            "orbits": [
                {
                    "representative_entity_id": (
                        orbit.representative_entity_id
                    ),
                    "member_entity_ids": orbit.member_entity_ids,
                    "entity_kind": orbit.entity_kind,
                    "missing_mode_count": orbit.missing_mode_count,
                    "representative_to_member_pullback_sha256": {
                        str(entity_id): _complex_matrix_sha256(pullback)
                        for entity_id, pullback in sorted(
                            orbit.representative_to_member_pullbacks.items()
                        )
                    },
                }
                for orbit in all_inactive.orbits
            ],
        }
    )
    edge_count = sum(
        entity.entity_kind == "edge" for entity in physical_entities
    )
    face_count = len(physical_entities) - edge_count
    singleton_orbit_count = sum(
        len(orbit.member_entity_ids) == 1
        for orbit in all_inactive.orbits
    )
    physical_shell_dofs = sum(
        entity.missing_mode_count for entity in physical_entities
    )
    quotient_shell_dofs = sum(
        orbit.missing_mode_count for orbit in all_inactive.orbits
    )
    checks = MappingProxyType(
        {
            "actual_dolfinx_mesh_inspected": True,
            "retained_p5_trace_space_inspected": True,
            "all_physical_edges_and_faces_have_unique_geometry_keys": True,
            "periodic_geometry_keys_match_actual_mesh": True,
            "periodic_relation_coverage_is_exact": True,
            "p5_p6_basis_hash_matches_authority": True,
            "p5_and_p6_entity_transforms_intertwine": True,
            "floquet_pullback_cycles_close": True,
            "every_entity_belongs_to_exactly_one_orbit": True,
            "singleton_nonperiodic_entities_retained": (
                singleton_orbit_count > 0
            ),
            "representative_owners_are_actual_entity_owners": True,
            "inactive_missing_p6_modes_have_no_rows": (
                all_inactive.active_row_increment == 0
            ),
            "matrix_not_constructed": True,
            "channel_dwr_not_computed": True,
        }
    )
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "actual selective p6 trace mesh catalog audit failed: "
            + ", ".join(failed)
        )
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035b.actual-selective-p6-trace-mesh-catalog.v1"
            ),
            "status": "actual_p6_trace_mesh_catalog_pass",
            "pass": True,
            "mpi_size": int(comm.size),
            "physical_entity_count": len(physical_entities),
            "physical_edge_count": edge_count,
            "physical_face_count": face_count,
            "periodic_relation_count": len(periodic_relations),
            "periodic_orbit_count": len(all_inactive.orbits),
            "singleton_orbit_count": singleton_orbit_count,
            "physical_missing_shell_dofs": physical_shell_dofs,
            "quotient_missing_shell_dofs": quotient_shell_dofs,
            "trace_geometry_sha256": trace_geometry_hash,
            "ordered_trace_basis_sha256": ordered_basis_hash,
            "catalog_sha256": catalog_hash,
            "qualification_sha256": actual_qualification,
            "topology_identity_sha256": identity.input_sha256,
            "topology_identity_hash_includes_dolfinx_global_ids": True,
            "partition_independent_hashes_exclude_owner_and_dolfinx_ids": True,
            "selection_performed": False,
            "active_rows_allocated": 0,
            "actual_channel_dwr_computed": False,
            "matrix_constructed": False,
            "ordinary_default_changed": False,
            "checks": checks,
        }
    )
    return SelectiveP6TraceMeshCatalog(
        mpi_size=int(comm.size),
        entities=physical_entities,
        missing_trace_entities=missing_entities,
        periodic_relations=tuple(periodic_relations),
        relation_metadata=tuple(relation_metadata),
        all_inactive_orbit_numbering=all_inactive,
        representative_owner_ranks=representative_owners,
        trace_geometry_sha256=trace_geometry_hash,
        ordered_trace_basis_sha256=ordered_basis_hash,
        catalog_sha256=catalog_hash,
        qualification_sha256=actual_qualification,
        floquet_phase_x=phase_x,
        floquet_phase_y=phase_y,
        audit=audit,
    )


def build_selected_p6_trace_orbit_owner_inputs(
    catalog: SelectiveP6TraceMeshCatalog,
    *,
    selected_physical_entity_ids: Sequence[int],
) -> SelectedP6TraceOrbitOwnerInputs:
    """Validate a whole-orbit selection and return MPI row-plan owner inputs."""

    selected_ids: list[int] = []
    for value in selected_physical_entity_ids:
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise TypeError("selected physical entity IDs must be integers")
        selected_ids.append(int(value))
    if len(set(selected_ids)) != len(selected_ids):
        raise ValueError("selected physical entity IDs are duplicated")
    selected_set = set(selected_ids)
    known = {entity.entity_id for entity in catalog.entities}
    unknown = selected_set - known
    if unknown:
        raise ValueError(
            f"selected physical entity IDs are unknown: {sorted(unknown)}"
        )

    selected_representatives: list[int] = []
    for orbit in catalog.all_inactive_orbit_numbering.orbits:
        members = set(orbit.member_entity_ids)
        intersection = selected_set.intersection(members)
        if intersection and intersection != members:
            raise RuntimeError(
                "selected physical p6 trace entities are not a union of "
                "whole periodic orbits"
            )
        if intersection:
            selected_representatives.append(
                orbit.representative_entity_id
            )
    owners = {
        representative: catalog.representative_owner_ranks[representative]
        for representative in selected_representatives
    }
    counts = [0] * catalog.mpi_size
    orbit_by_representative = {
        orbit.representative_entity_id: orbit
        for orbit in catalog.all_inactive_orbit_numbering.orbits
    }
    for representative, owner in owners.items():
        counts[owner] += orbit_by_representative[
            representative
        ].missing_mode_count
    return SelectedP6TraceOrbitOwnerInputs(
        selected_representative_entity_ids=tuple(
            sorted(selected_representatives)
        ),
        selected_orbit_owner_ranks=owners,
        owned_selected_trace_row_counts_by_rank=tuple(counts),
    )


__all__ = [
    "PhysicalP6TraceEntity",
    "PhysicalP6TracePeriodicRelation",
    "SelectedP6TraceOrbitOwnerInputs",
    "SelectiveP6TraceMeshCatalog",
    "build_selected_p6_trace_orbit_owner_inputs",
    "build_selective_p6_trace_mesh_catalog",
]
