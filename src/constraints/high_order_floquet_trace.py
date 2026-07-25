from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from typing import Hashable, Iterable, Literal
import weakref

import basix
import numpy as np
from basix import CellType, ElementFamily, LagrangeVariant
from basix.ufl import element


PhaseKind = Literal["x", "y", "corner"]
EntityKind = Literal["edge", "face"]
EntityGeometryKey = tuple[tuple[int, int, int], ...]

_PHASE_KIND_ORDER = {"x": 0, "y": 1, "corner": 2}
_ENTITY_KIND_ORDER = {"edge": 0, "face": 1}


@dataclass(frozen=True)
class HighOrderTraceLayout:
    """Degree-generic tensor-product N1curl trace layout."""

    degree: int
    hexahedron_dimension: int
    edge_dofs: int
    face_interior_dofs: int
    cell_interior_dofs: int
    face_trace_dofs: int
    quadrilateral_n1curl_dimension: int


@dataclass(frozen=True)
class TetrahedralTraceLayout:
    """Degree-generic simplex N1curl trace layout."""

    degree: int
    tetrahedron_dimension: int
    edge_dofs: int
    face_interior_dofs: int
    cell_interior_dofs: int
    face_trace_dofs: int
    triangle_n1curl_dimension: int


@lru_cache(maxsize=6)
def high_order_trace_layout(degree: int) -> HighOrderTraceLayout:
    """Read and cross-check the p1--p6 Basix entity layout.

    Formulas are checks, not the source of the production layout.  The actual
    entity sizes come from the Basix element shipped in the qualified image.
    """

    degree = int(degree)
    if degree not in {1, 2, 3, 4, 5, 6}:
        raise ValueError(
            f"Task033/Task035b qualifies hexa N1curl degrees 1--6, got {degree}."
        )
    hexa = element("N1curl", "hexahedron", degree).basix_element
    quadrilateral = element("N1curl", "quadrilateral", degree).basix_element
    edge_counts = {len(dofs) for dofs in hexa.entity_dofs[1]}
    face_counts = {len(dofs) for dofs in hexa.entity_dofs[2]}
    cell_counts = {len(dofs) for dofs in hexa.entity_dofs[3]}
    if len(edge_counts) != 1 or len(face_counts) != 1 or len(cell_counts) != 1:
        raise RuntimeError(
            "Basix returned a non-uniform hexahedron N1curl entity layout."
        )
    edge_dofs = edge_counts.pop()
    face_interior_dofs = face_counts.pop()
    cell_interior_dofs = cell_counts.pop()
    face_trace_dofs = 4 * edge_dofs + face_interior_dofs
    expected = {
        "hexahedron_dimension": 3 * degree * (degree + 1) ** 2,
        "edge_dofs": degree,
        "face_interior_dofs": 2 * degree * (degree - 1),
        "cell_interior_dofs": 3 * degree * (degree - 1) ** 2,
        "face_trace_dofs": 2 * degree * (degree + 1),
    }
    observed = {
        "hexahedron_dimension": int(hexa.dim),
        "edge_dofs": int(edge_dofs),
        "face_interior_dofs": int(face_interior_dofs),
        "cell_interior_dofs": int(cell_interior_dofs),
        "face_trace_dofs": int(face_trace_dofs),
    }
    if observed != expected:
        raise RuntimeError(
            "Basix tensor-product N1curl semantics changed; refusing to infer a high-order trace layout: "
            f"observed={observed}, expected={expected}."
        )
    if int(quadrilateral.dim) != face_trace_dofs:
        raise RuntimeError(
            "The 3D face trace and 2D N1curl degree semantics disagree: "
            f"3D trace={face_trace_dofs}, 2D dimension={quadrilateral.dim}."
        )
    return HighOrderTraceLayout(
        degree=degree,
        hexahedron_dimension=int(hexa.dim),
        edge_dofs=int(edge_dofs),
        face_interior_dofs=int(face_interior_dofs),
        cell_interior_dofs=int(cell_interior_dofs),
        face_trace_dofs=int(face_trace_dofs),
        quadrilateral_n1curl_dimension=int(quadrilateral.dim),
    )


@lru_cache(maxsize=6)
def tetrahedral_trace_layout(degree: int) -> TetrahedralTraceLayout:
    """Read and cross-check the p1--p6 tetrahedral N1curl entity layout."""

    degree = int(degree)
    if degree not in {1, 2, 3, 4, 5, 6}:
        raise ValueError(f"Task035 qualifies tetra N1curl degrees 1--6, got {degree}.")
    tetrahedron = element("N1curl", "tetrahedron", degree).basix_element
    triangle = element("N1curl", "triangle", degree).basix_element
    edge_counts = {len(dofs) for dofs in tetrahedron.entity_dofs[1]}
    face_counts = {len(dofs) for dofs in tetrahedron.entity_dofs[2]}
    cell_counts = {len(dofs) for dofs in tetrahedron.entity_dofs[3]}
    if len(edge_counts) != 1 or len(face_counts) != 1 or len(cell_counts) != 1:
        raise RuntimeError(
            "Basix returned a non-uniform tetrahedron N1curl entity layout."
        )
    edge_dofs = edge_counts.pop()
    face_interior_dofs = face_counts.pop()
    cell_interior_dofs = cell_counts.pop()
    face_trace_dofs = 3 * edge_dofs + face_interior_dofs
    expected = {
        "tetrahedron_dimension": degree * (degree + 2) * (degree + 3) // 2,
        "edge_dofs": degree,
        "face_interior_dofs": degree * (degree - 1),
        "cell_interior_dofs": degree * (degree - 1) * (degree - 2) // 2,
        "face_trace_dofs": degree * (degree + 2),
    }
    observed = {
        "tetrahedron_dimension": int(tetrahedron.dim),
        "edge_dofs": int(edge_dofs),
        "face_interior_dofs": int(face_interior_dofs),
        "cell_interior_dofs": int(cell_interior_dofs),
        "face_trace_dofs": int(face_trace_dofs),
    }
    if observed != expected:
        raise RuntimeError(
            "Basix simplex N1curl semantics changed; refusing to infer a trace layout: "
            f"observed={observed}, expected={expected}."
        )
    if int(triangle.dim) != face_trace_dofs:
        raise RuntimeError(
            "The tetrahedron face trace and triangle N1curl degree semantics disagree: "
            f"3D trace={face_trace_dofs}, 2D dimension={triangle.dim}."
        )
    return TetrahedralTraceLayout(
        degree=degree,
        tetrahedron_dimension=int(tetrahedron.dim),
        edge_dofs=int(edge_dofs),
        face_interior_dofs=int(face_interior_dofs),
        cell_interior_dofs=int(cell_interior_dofs),
        face_trace_dofs=int(face_trace_dofs),
        triangle_n1curl_dimension=int(triangle.dim),
    )


@lru_cache(maxsize=1)
def quadrilateral_d4_vertex_permutations() -> dict[tuple[int, int, int, int], int]:
    """Return Basix's eight quadrilateral orientation permutations.

    The three face-info bits use reflection in bit 0 and a 0--3 rotation count
    in bits 1--2.  Asking Basix to permute a P1 face closure makes this mapping
    independent of a guessed vertex-numbering diagram.
    """

    p1 = basix.create_element(
        ElementFamily.P,
        CellType.hexahedron,
        1,
        LagrangeVariant.equispaced,
    )
    reference = np.asarray(p1.entity_closure_dofs[2][0], dtype=np.int32)
    if reference.shape != (4,):
        raise RuntimeError(
            f"Expected four P1 quadrilateral closure dofs, got {reference}."
        )
    mapping: dict[tuple[int, int, int, int], int] = {}
    for face_info in range(8):
        permuted = reference.copy()
        p1.permute_subentity_closure(permuted, face_info, CellType.quadrilateral)
        local_permutation = tuple(
            int(np.where(reference == value)[0][0]) for value in permuted
        )
        if local_permutation in mapping:
            raise RuntimeError(
                "Basix returned duplicate quadrilateral D4 permutations."
            )
        mapping[local_permutation] = face_info
    if len(mapping) != 8:
        raise RuntimeError(
            f"Expected eight quadrilateral D4 permutations, got {len(mapping)}."
        )
    return mapping


def quadrilateral_face_info(vertex_permutation: Iterable[int]) -> int:
    permutation = tuple(int(value) for value in vertex_permutation)
    if len(permutation) != 4 or sorted(permutation) != [0, 1, 2, 3]:
        raise ValueError(
            f"Expected a quadrilateral vertex permutation, got {permutation}."
        )
    try:
        return quadrilateral_d4_vertex_permutations()[permutation]  # type: ignore[index]
    except KeyError as exc:  # pragma: no cover - all S4 non-D4 permutations are invalid
        raise ValueError(
            f"Permutation {permutation} is not a quadrilateral D4 symmetry."
        ) from exc


@lru_cache(maxsize=1)
def triangle_s3_vertex_permutations() -> dict[tuple[int, int, int], int]:
    """Return Basix's six triangle orientation permutations."""

    p1 = basix.create_element(
        ElementFamily.P,
        CellType.tetrahedron,
        1,
        LagrangeVariant.equispaced,
    )
    reference = np.asarray(p1.entity_closure_dofs[2][0], dtype=np.int32)
    if reference.shape != (3,):
        raise RuntimeError(f"Expected three P1 triangle closure dofs, got {reference}.")
    mapping: dict[tuple[int, int, int], int] = {}
    for face_info in range(6):
        permuted = reference.copy()
        p1.permute_subentity_closure(permuted, face_info, CellType.triangle)
        local_permutation = tuple(
            int(np.where(reference == value)[0][0]) for value in permuted
        )
        if local_permutation in mapping:
            raise RuntimeError("Basix returned duplicate triangle S3 permutations.")
        mapping[local_permutation] = face_info  # type: ignore[index]
    if len(mapping) != 6:
        raise RuntimeError(f"Expected six triangle S3 permutations, got {len(mapping)}.")
    return mapping


def triangle_face_info(vertex_permutation: Iterable[int]) -> int:
    permutation = tuple(int(value) for value in vertex_permutation)
    if len(permutation) != 3 or sorted(permutation) != [0, 1, 2]:
        raise ValueError(f"Expected a triangle vertex permutation, got {permutation}.")
    try:
        return triangle_s3_vertex_permutations()[permutation]  # type: ignore[index]
    except KeyError as exc:  # pragma: no cover - every S3 permutation is valid
        raise ValueError(f"Permutation {permutation} is not a triangle symmetry.") from exc


@lru_cache(maxsize=6)
def _entity_transformations(degree: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    high_order_trace_layout(degree)
    hexa = element("N1curl", "hexahedron", int(degree)).basix_element
    transformations = hexa.entity_transformations()
    interval = np.asarray(transformations["interval"][0], dtype=np.float64)
    quadrilateral = np.asarray(transformations["quadrilateral"], dtype=np.float64)
    if quadrilateral.shape[0] != 2:
        raise RuntimeError(
            "Basix must provide rotation and reflection generators for quadrilateral faces."
        )
    return interval, quadrilateral[0], quadrilateral[1]


@lru_cache(maxsize=6)
def _tetrahedral_entity_transformations(
    degree: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    tetrahedral_trace_layout(degree)
    tetrahedron = element("N1curl", "tetrahedron", int(degree)).basix_element
    transformations = tetrahedron.entity_transformations()
    interval = np.asarray(transformations["interval"][0], dtype=np.float64)
    triangle = np.asarray(transformations["triangle"], dtype=np.float64)
    if triangle.shape[0] != 2:
        raise RuntimeError(
            "Basix must provide rotation and reflection generators for triangle faces."
        )
    return interval, triangle[0], triangle[1]


def edge_coefficient_transform(
    degree: int,
    *,
    reversed_orientation: bool,
    cell_type: str = "hexahedron",
) -> np.ndarray:
    """Map canonical master edge coefficients into slave coefficient ordering."""

    if cell_type == "tetrahedron":
        interval, _rotation, _reflection = _tetrahedral_entity_transformations(
            int(degree)
        )
    else:
        interval, _rotation, _reflection = _entity_transformations(int(degree))
    if not reversed_orientation:
        return np.eye(interval.shape[0], dtype=np.complex128)
    # Basix T matrices transform basis data.  Coefficients therefore use T^T.
    return np.asarray(interval.T, dtype=np.complex128)


def face_basis_transform(degree: int, face_info: int) -> np.ndarray:
    """Compose the Basix face basis transform for one D4 orientation."""

    if not 0 <= int(face_info) < 8:
        raise ValueError(f"Quadrilateral face_info must be in [0, 7], got {face_info}.")
    _interval, rotation, reflection = _entity_transformations(int(degree))
    transform = np.eye(rotation.shape[0], dtype=np.float64)
    if int(face_info) & 1:
        transform = reflection @ transform
    for _ in range((int(face_info) >> 1) & 3):
        transform = rotation @ transform
    return transform


def face_coefficient_transform(
    degree: int, vertex_permutation: Iterable[int]
) -> np.ndarray:
    """Map canonical master face-interior coefficients into slave ordering."""

    face_info = quadrilateral_face_info(vertex_permutation)
    return np.asarray(
        face_basis_transform(int(degree), face_info).T, dtype=np.complex128
    )


def triangle_face_basis_transform(degree: int, face_info: int) -> np.ndarray:
    """Compose the Basix triangle face basis transform for one S3 orientation."""

    if not 0 <= int(face_info) < 6:
        raise ValueError(f"Triangle face_info must be in [0, 5], got {face_info}.")
    _interval, rotation, reflection = _tetrahedral_entity_transformations(
        int(degree)
    )
    transform = np.eye(rotation.shape[0], dtype=np.float64)
    if int(face_info) & 1:
        transform = reflection @ transform
    for _ in range((int(face_info) >> 1) % 3):
        transform = rotation @ transform
    return transform


def triangle_face_coefficient_transform(
    degree: int, vertex_permutation: Iterable[int]
) -> np.ndarray:
    """Map canonical master triangle-face coefficients into slave ordering."""

    face_info = triangle_face_info(vertex_permutation)
    return np.asarray(
        triangle_face_basis_transform(int(degree), face_info).T,
        dtype=np.complex128,
    )


@dataclass(frozen=True)
class FloquetTopologyKey:
    mesh_token: Hashable
    element_family: str
    degree: int
    periodic_axes: tuple[str, ...] = ("x", "y")
    orientation_schema: str = "basix-0.10-d4-v1"


@dataclass(frozen=True)
class PhaseIndependentConstraintBlock:
    kind: PhaseKind
    slave_global_dofs: tuple[int, ...]
    master_global_dofs: tuple[int, ...]
    coefficient_transform: np.ndarray
    slave_local_dofs: tuple[int, ...] = ()
    master_owners: tuple[int, ...] = ()
    slave_owned: tuple[bool, ...] = ()
    touches_owned_cell: bool = False
    entity_kind: EntityKind = "edge"
    pair_error: float = 0.0
    slave_entity_id: int | None = None
    master_entity_id: int | None = None
    slave_entity_geometry_key: EntityGeometryKey = ()
    master_entity_geometry_key: EntityGeometryKey = ()
    periodic_pair_key: tuple[int, ...] = ()
    entity_vertex_permutation: tuple[int, ...] = ()
    cell_type: str = ""

    def __post_init__(self) -> None:
        matrix = np.asarray(self.coefficient_transform, dtype=np.complex128)
        if matrix.shape != (len(self.slave_global_dofs), len(self.master_global_dofs)):
            raise ValueError(
                "Constraint block shape does not match slave/master dof counts: "
                f"shape={matrix.shape}, slaves={len(self.slave_global_dofs)}, "
                f"masters={len(self.master_global_dofs)}."
            )
        matrix.setflags(write=False)
        object.__setattr__(self, "coefficient_transform", matrix)
        if self.slave_local_dofs and len(self.slave_local_dofs) != len(
            self.slave_global_dofs
        ):
            raise ValueError("Local and global slave dof counts differ.")
        if self.master_owners and len(self.master_owners) != len(
            self.master_global_dofs
        ):
            raise ValueError("Master owner and global dof counts differ.")
        if self.slave_owned and len(self.slave_owned) != len(self.slave_global_dofs):
            raise ValueError("Slave ownership and global dof counts differ.")
        if self.entity_kind not in {"edge", "face"}:
            raise ValueError(f"Unsupported trace entity kind {self.entity_kind!r}.")
        if float(self.pair_error) < 0.0:
            raise ValueError("Periodic entity pairing error cannot be negative.")
        identity_fields_present = (
            self.slave_entity_id is not None,
            self.master_entity_id is not None,
            bool(self.slave_entity_geometry_key),
            bool(self.master_entity_geometry_key),
            bool(self.periodic_pair_key),
            bool(self.entity_vertex_permutation),
            bool(self.cell_type),
        )
        if any(identity_fields_present) and not all(identity_fields_present):
            raise ValueError(
                "Physical periodic entity identity must provide both entity IDs, "
                "both geometry keys, pair key, vertex permutation, and cell type."
            )
        if all(identity_fields_present):
            slave_entity_id = int(self.slave_entity_id)  # type: ignore[arg-type]
            master_entity_id = int(self.master_entity_id)  # type: ignore[arg-type]
            if slave_entity_id < 0 or master_entity_id < 0:
                raise ValueError("Physical periodic entity IDs must be nonnegative.")
            if slave_entity_id == master_entity_id:
                raise ValueError(
                    "A periodic slave and master cannot share one physical entity ID."
                )
            slave_key = _normalize_entity_geometry_key(
                self.slave_entity_geometry_key,
                label="slave entity geometry key",
            )
            master_key = _normalize_entity_geometry_key(
                self.master_entity_geometry_key,
                label="master entity geometry key",
            )
            if slave_key == master_key:
                raise ValueError(
                    "Periodic slave/master physical geometry keys must differ."
                )
            pair_key = tuple(int(value) for value in self.periodic_pair_key)
            if len(pair_key) != 6:
                raise ValueError(
                    "A 3D periodic entity pair key must contain six integers."
                )
            expected_dimension = 1 if self.entity_kind == "edge" else 2
            if pair_key[0] != expected_dimension:
                raise ValueError(
                    "Periodic pair-key entity dimension disagrees with entity kind."
                )
            expected_kind_code = {"x": 1, "y": 2, "corner": 3}[self.kind]
            if pair_key[1] != expected_kind_code:
                raise ValueError(
                    "Periodic pair-key direction disagrees with block kind."
                )
            permutation = tuple(
                int(value) for value in self.entity_vertex_permutation
            )
            expected_vertices = (
                {2}
                if self.entity_kind == "edge"
                else ({3} if "tetrahedron" in self.cell_type else {4})
            )
            if (
                len(permutation) not in expected_vertices
                or sorted(permutation) != list(range(len(permutation)))
            ):
                raise ValueError(
                    "Periodic entity vertex permutation is invalid for its "
                    "entity kind/cell type."
                )
            cell_type = _normalize_cell_type(self.cell_type)
            if self.entity_kind == "face" and self.kind == "corner":
                raise ValueError("Periodic faces do not use corner relations.")
            object.__setattr__(self, "slave_entity_id", slave_entity_id)
            object.__setattr__(self, "master_entity_id", master_entity_id)
            object.__setattr__(
                self,
                "slave_entity_geometry_key",
                slave_key,
            )
            object.__setattr__(
                self,
                "master_entity_geometry_key",
                master_key,
            )
            object.__setattr__(self, "periodic_pair_key", pair_key)
            object.__setattr__(
                self,
                "entity_vertex_permutation",
                permutation,
            )
            object.__setattr__(self, "cell_type", cell_type)

    @property
    def has_physical_entity_identity(self) -> bool:
        """Whether this block carries the complete opt-in physical identity."""

        return self.slave_entity_id is not None


def _normalize_entity_geometry_key(
    key: Iterable[Iterable[int]],
    *,
    label: str,
) -> EntityGeometryKey:
    normalized = tuple(
        tuple(int(component) for component in point) for point in key
    )
    if not normalized or any(len(point) != 3 for point in normalized):
        raise ValueError(f"{label} must contain nonempty three-component points.")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{label} contains duplicate physical vertices.")
    if tuple(sorted(normalized)) != normalized:
        raise ValueError(f"{label} must use canonical sorted vertex order.")
    return normalized


def _normalize_cell_type(value: str) -> str:
    normalized = str(value).lower()
    if "tetrahedron" in normalized:
        return "tetrahedron"
    if "hexahedron" in normalized:
        return "hexahedron"
    raise ValueError(f"Unsupported physical periodic cell type {value!r}.")


@dataclass(frozen=True)
class FloquetTraceTopology:
    key: FloquetTopologyKey
    blocks: tuple[PhaseIndependentConstraintBlock, ...]
    topology_build_seconds: float
    bytes_sent: int
    bytes_received: int
    used_full_boundary_gather: bool = False
    created_dense_boundary_square: bool = False
    pair_counts: tuple[tuple[EntityKind, PhaseKind, int], ...] = ()

    def materialize(
        self,
        *,
        phase_x: complex,
        phase_y: complex,
    ) -> tuple[np.ndarray, ...]:
        phase_by_kind = {
            "x": complex(phase_x),
            "y": complex(phase_y),
            "corner": complex(phase_x) * complex(phase_y),
        }
        return tuple(
            phase_by_kind[block.kind] * block.coefficient_transform
            for block in self.blocks
        )


@dataclass(frozen=True, order=True)
class MissingP6TraceOrbitRelationInput:
    """One physical periodic relation, ready for p6-transform composition."""

    entity_kind: EntityKind
    direction: PhaseKind
    slave_entity_id: int
    master_entity_id: int
    slave_entity_geometry_key: EntityGeometryKey
    master_entity_geometry_key: EntityGeometryKey
    periodic_pair_key: tuple[int, ...]
    entity_vertex_permutation: tuple[int, ...]
    cell_type: str


@dataclass(frozen=True)
class MissingP6TraceOrbitIdentityInput:
    """Mesh-bound relations; no p6 basis, DWR, rows, or matrix are created."""

    mesh_sha256: str
    relations: tuple[MissingP6TraceOrbitRelationInput, ...]
    input_sha256: str
    scope: str = "identity_only_no_basis_dwr_rows_or_matrix"


def _validated_sha256(value: str) -> str:
    normalized = str(value).lower()
    try:
        valid = len(normalized) == 64 and len(bytes.fromhex(normalized)) == 32
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("mesh_sha256 must contain 64 hexadecimal characters.")
    return normalized


def _block_identity_tuple(block: PhaseIndependentConstraintBlock) -> tuple:
    if not block.has_physical_entity_identity:
        raise RuntimeError(
            "Floquet topology lacks physical entity identity required for "
            "missing-p6 orbit closure."
        )
    if block.cell_type != "hexahedron":
        raise NotImplementedError(
            "Missing-p6 orbit identity is qualified only for hexahedra."
        )
    return (
        block.entity_kind,
        block.kind,
        int(block.slave_entity_id),  # type: ignore[arg-type]
        int(block.master_entity_id),  # type: ignore[arg-type]
        block.slave_entity_geometry_key,
        block.master_entity_geometry_key,
        block.periodic_pair_key,
        block.entity_vertex_permutation,
        block.cell_type,
    )


def build_missing_p6_trace_orbit_identity_input(
    topology: FloquetTraceTopology,
    *,
    mesh_sha256: str,
    comm: object,
) -> MissingP6TraceOrbitIdentityInput:
    """Canonicalize actual p5 periodic entities into an MPI-complete seed.

    DOLFINx global topology IDs are paired with partition-independent physical
    geometry keys.  The bridge stops before p6 intertwining, Floquet pullback,
    active numbering, DWR, or matrix construction.
    """

    mesh_sha256 = _validated_sha256(mesh_sha256)
    if int(topology.key.degree) != 5:
        raise ValueError("Missing-p6 orbit identity requires retained degree p5.")
    if not hasattr(comm, "allgather"):
        raise TypeError("comm must provide an MPI-compatible allgather method.")
    metadata = (
        mesh_sha256,
        str(topology.key.element_family),
        int(topology.key.degree),
        str(topology.key.orientation_schema),
    )
    if any(
        value != metadata
        for value in comm.allgather(metadata)  # type: ignore[attr-defined]
    ):
        raise RuntimeError("Missing-p6 orbit metadata differs across MPI ranks.")

    local_rows = [_block_identity_tuple(block) for block in topology.blocks]
    rows = [
        row
        for packet in comm.allgather(local_rows)  # type: ignore[attr-defined]
        for row in packet
    ]
    if not rows:
        raise RuntimeError("Missing-p6 orbit input has no periodic relations.")

    relations_by_geometry: dict[tuple, tuple] = {}
    for row in rows:
        relation_key = (row[0], row[1], row[4], row[5])
        previous = relations_by_geometry.setdefault(relation_key, row)
        if previous != row:
            raise RuntimeError(
                "MPI copies disagree on a physical periodic entity relation."
            )
    unique_rows = tuple(relations_by_geometry.values())
    relations = tuple(
        MissingP6TraceOrbitRelationInput(
            entity_kind=row[0],
            direction=row[1],
            slave_entity_id=row[2],
            master_entity_id=row[3],
            slave_entity_geometry_key=row[4],
            master_entity_geometry_key=row[5],
            periodic_pair_key=row[6],
            entity_vertex_permutation=row[7],
            cell_type=row[8],
        )
        for row in sorted(
            unique_rows,
            key=lambda value: (
                _ENTITY_KIND_ORDER[value[0]],
                _PHASE_KIND_ORDER[value[1]],
                value[4],
                value[5],
            ),
        )
    )
    payload = {
        "schema": "task035b.missing-p6-trace-orbit-identity.v1",
        "mesh_sha256": mesh_sha256,
        "element_family": str(topology.key.element_family),
        "orientation_schema": str(topology.key.orientation_schema),
        "relations": [
            (
                relation.entity_kind,
                relation.direction,
                relation.slave_entity_id,
                relation.master_entity_id,
                relation.slave_entity_geometry_key,
                relation.master_entity_geometry_key,
                relation.periodic_pair_key,
                relation.entity_vertex_permutation,
                relation.cell_type,
            )
            for relation in relations
        ],
    }
    input_sha256 = hashlib.sha256(
        json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    ).hexdigest()
    return MissingP6TraceOrbitIdentityInput(
        mesh_sha256=mesh_sha256,
        relations=relations,
        input_sha256=input_sha256,
    )


class FloquetTopologyCache:
    """Weak-owner-aware LRU cache whose values never contain Bloch phases.

    Production entries validate live mesh/function-space wrappers by identity.
    Weak references avoid retaining large DOLFINx graphs, and make ``id()``
    reuse in :class:`FloquetTopologyKey` fail closed.
    """

    def __init__(self, max_entries: int = 8):
        if int(max_entries) < 1:
            raise ValueError("max_entries must be positive.")
        self.max_entries = int(max_entries)
        self._values: OrderedDict[
            FloquetTopologyKey,
            tuple[
                FloquetTraceTopology,
                weakref.ReferenceType[object] | None,
                weakref.ReferenceType[object] | None,
            ],
        ] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(
        self,
        key: FloquetTopologyKey,
        *,
        mesh: object | None = None,
        space: object | None = None,
    ) -> FloquetTraceTopology | None:
        entry = self._values.get(key)
        if entry is None:
            self.misses += 1
            return None
        value, mesh_ref, space_ref = entry
        if mesh is not None or space is not None:
            owners_match = bool(
                mesh is not None
                and space is not None
                and mesh_ref is not None
                and space_ref is not None
                and mesh_ref() is mesh
                and space_ref() is space
            )
            if not owners_match:
                self._values.pop(key, None)
                self.misses += 1
                return None
        self._values.move_to_end(key)
        self.hits += 1
        return value

    def put(
        self,
        topology: FloquetTraceTopology,
        *,
        mesh: object | None = None,
        space: object | None = None,
    ) -> None:
        if (mesh is None) != (space is None):
            raise ValueError("mesh and space cache owners must be supplied together.")
        mesh_ref = None if mesh is None else weakref.ref(mesh)
        space_ref = None if space is None else weakref.ref(space)
        self._values[topology.key] = (topology, mesh_ref, space_ref)
        self._values.move_to_end(topology.key)
        while len(self._values) > self.max_entries:
            self._values.popitem(last=False)

    def clear(self) -> None:
        self._values.clear()

    def __len__(self) -> int:
        return len(self._values)


@dataclass(frozen=True)
class DistributedPairingMetrics:
    records_sent: int
    records_received: int
    bytes_sent: int
    bytes_received: int
    pair_count: int
    used_full_boundary_gather: bool = False


def stable_pairing_rank(pair_key: Iterable[int], comm_size: int) -> int:
    """Map a periodic entity key to one deterministic pairing rank."""

    if int(comm_size) < 1:
        raise ValueError("comm_size must be positive.")
    normalized = tuple(int(value) for value in pair_key)
    digest = hashlib.blake2b(
        json.dumps(normalized, separators=(",", ":")).encode("ascii"),
        digest_size=8,
        person=b"task033",
    ).digest()
    return int.from_bytes(digest, "little", signed=False) % int(comm_size)


def _alltoallv_json_records(
    comm, buckets: list[list[dict]]
) -> tuple[list[dict], int, int]:
    """Exchange routed JSON records without replicating a whole boundary."""

    from mpi4py import MPI

    if len(buckets) != int(comm.size):
        raise ValueError(
            f"Expected {comm.size} destination buckets, got {len(buckets)}."
        )
    payloads = [
        json.dumps(bucket, separators=(",", ":"), sort_keys=True).encode("utf-8")
        for bucket in buckets
    ]
    send_counts = np.asarray([len(payload) for payload in payloads], dtype=np.int64)
    recv_counts = np.empty(int(comm.size), dtype=np.int64)
    comm.Alltoall(send_counts, recv_counts)
    send_displacements = np.zeros(int(comm.size), dtype=np.int64)
    recv_displacements = np.zeros(int(comm.size), dtype=np.int64)
    if int(comm.size) > 1:
        send_displacements[1:] = np.cumsum(send_counts[:-1])
        recv_displacements[1:] = np.cumsum(recv_counts[:-1])
    send_blob = b"".join(payloads)
    send_buffer = np.frombuffer(send_blob, dtype=np.uint8)
    recv_buffer = np.empty(int(np.sum(recv_counts)), dtype=np.uint8)
    comm.Alltoallv(
        [send_buffer, send_counts, send_displacements, MPI.BYTE],
        [recv_buffer, recv_counts, recv_displacements, MPI.BYTE],
    )
    received: list[dict] = []
    for count, displacement in zip(recv_counts, recv_displacements, strict=True):
        if int(count) == 0:
            continue
        packet = recv_buffer[int(displacement) : int(displacement + count)].tobytes()
        decoded = json.loads(packet.decode("utf-8"))
        if not isinstance(decoded, list):
            raise RuntimeError(
                "Distributed Floquet pairing received a non-list JSON packet."
            )
        received.extend(decoded)
    return received, int(np.sum(send_counts)), int(np.sum(recv_counts))


def distributed_match_periodic_records(
    comm,
    local_records: list[dict],
) -> tuple[list[dict], DistributedPairingMetrics]:
    """Match periodic slave records with masters via distributed hash routing.

    Each input record must contain JSON-compatible ``pair_key``, ``role``,
    ``global_dofs``, ``reply_rank`` and ``token`` fields.  Master records may
    be repeated by ghost contributors, but all copies must name the same global
    DOFs.  Replies are sent only to ranks that contributed a slave record.
    """

    size = int(comm.size)
    rank = int(comm.rank)
    routed: list[list[dict]] = [[] for _ in range(size)]
    for record in local_records:
        pair_key = tuple(int(value) for value in record.get("pair_key", ()))
        role = record.get("role")
        if not pair_key or role not in {"master", "slave"}:
            raise ValueError(
                f"Invalid periodic pairing record on rank {rank}: {record}."
            )
        if int(record.get("reply_rank", -1)) != rank:
            raise ValueError(
                "Each local pairing record must reply to its contributing rank."
            )
        routed[stable_pairing_rank(pair_key, size)].append(record)

    received, first_sent, first_received = _alltoallv_json_records(comm, routed)
    grouped: dict[tuple[int, ...], list[dict]] = {}
    for record in received:
        key = tuple(int(value) for value in record["pair_key"])
        grouped.setdefault(key, []).append(record)

    replies_by_rank: list[list[dict]] = [[] for _ in range(size)]
    local_errors: list[str] = []
    local_pair_count = 0
    for key, records in grouped.items():
        masters = [record for record in records if record["role"] == "master"]
        slaves = [record for record in records if record["role"] == "slave"]
        master_by_dofs: dict[tuple[int, ...], dict] = {}
        master_payload_signatures: dict[tuple[int, ...], set[str]] = {}
        for master in masters:
            master_dofs = tuple(int(value) for value in master["global_dofs"])
            comparable_payload = {
                name: master.get(name)
                for name in (
                    "pair_key",
                    "global_dofs",
                    "owners",
                    "midpoint",
                    "tangent",
                    "geometry_coords",
                    "normal_axis",
                    "physical_global_entity_id",
                    "entity_geometry_key",
                    "cell_type",
                )
                if name in master
            }
            master_payload_signatures.setdefault(master_dofs, set()).add(
                json.dumps(
                    comparable_payload,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            current = master_by_dofs.get(master_dofs)
            if current is None or (
                bool(master.get("owns_any", False)),
                -int(master["reply_rank"]),
            ) > (
                bool(current.get("owns_any", False)),
                -int(current["reply_rank"]),
            ):
                master_by_dofs[master_dofs] = master
        inconsistent_master_payloads = [
            dofs
            for dofs, signatures in master_payload_signatures.items()
            if len(signatures) != 1
        ]
        if inconsistent_master_payloads:
            local_errors.append(
                f"key={key}: inconsistent_master_payloads={inconsistent_master_payloads}"
            )
            continue
        if len(master_by_dofs) != 1 or not slaves:
            local_errors.append(
                f"key={key}: unique_masters={len(master_by_dofs)}, slave_records={len(slaves)}"
            )
            continue
        master = next(iter(master_by_dofs.values()))
        slave_entities = {
            tuple(int(value) for value in slave["global_dofs"]) for slave in slaves
        }
        if len(slave_entities) != 1:
            local_errors.append(
                f"key={key}: distinct_slave_entities={len(slave_entities)}"
            )
            continue
        local_pair_count += 1
        master_payload = {
            name: value
            for name, value in master.items()
            if name not in {"role", "reply_rank", "token"}
        }
        for slave in slaves:
            replies_by_rank[int(slave["reply_rank"])].append(
                {
                    "token": slave["token"],
                    "pair_key": list(key),
                    "master": master_payload,
                }
            )

    error_count = int(comm.allreduce(len(local_errors)))
    if error_count:
        detail = (
            local_errors[0]
            if local_errors
            else "error was detected on another pairing rank"
        )
        raise RuntimeError(
            "Distributed periodic entity pairing is not one-to-one: "
            f"global_error_count={error_count}; {detail}."
        )

    replies, second_sent, second_received = _alltoallv_json_records(
        comm, replies_by_rank
    )
    global_pairs = int(comm.allreduce(local_pair_count))
    metrics = DistributedPairingMetrics(
        records_sent=len(local_records),
        records_received=len(replies),
        bytes_sent=first_sent + second_sent,
        bytes_received=first_received + second_received,
        pair_count=global_pairs,
    )
    return replies, metrics
