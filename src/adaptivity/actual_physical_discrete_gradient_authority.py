"""Actual same-mesh Q5/Q6-to-N1curl-p6 discrete-gradient authority.

The pure exact-sequence planner accepts :class:`DiscreteGradientOrbitRule`
objects, but a caller-supplied collection of booleans is not evidence that
those rules came from the physical finite-element spaces.  This module builds
the rules itself from the qualified DOLFINx 0.10 stack:

* conforming Q5 and Q6 GLL spaces are created on the supplied physical mesh;
* ``fem.interpolation_matrix(Q5, Q6)`` and
  ``fem.discrete_gradient(Q6, V6)`` are assembled and content-hashed;
* the one-dimensional edge and nine-dimensional face scalar shells are
  extracted from the actual interpolation coefficients;
* actual gradient coefficients are projected through the qualified
  covariant-Piola/tangential-Riesz missing N1curl-p6 complement; and
* scalar and H(curl) Floquet pullbacks are checked to commute on complete
  periodic orbits.

Only compact entity/orbit coefficients survive the build.  No Maxwell matrix,
candidate row, or inactive p6 row is constructed, and the ordinary solver
default is untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import basix
from basix.ufl import element
import dolfinx
import numpy as np
from petsc4py import PETSc

from dolfinx import cpp, default_real_type, fem

from src.adaptivity.p6_trace_complement_qualification import (
    P5P6TraceComplementQualification,
)
from src.adaptivity.physical_channel_dwr_trace_selection import (
    PhysicalDiscreteGradientAuthority,
)
from src.adaptivity.selective_p6_trace_exact_sequence import (
    DiscreteGradientOrbitRule,
)
from src.constraints.selective_p6_trace_expansion import (
    PhysicalP6TraceOrbitPullback,
    build_physical_p6_trace_orbit_pullbacks,
)
from src.constraints.selective_p6_trace_mesh_catalog import (
    EntityGeometryKey,
    SelectiveP6TraceMeshCatalog,
    TraceEntityKind,
)
from src.geometry.tetra_mesh_audit import canonical_entity_key


_ENTITY_DIMENSION = {"edge": 1, "face": 2}
_Q5_ENTITY_DIMENSION = {"edge": 4, "face": 16}
_Q6_ENTITY_DIMENSION = {"edge": 5, "face": 25}
_SCALAR_SHELL_DIMENSION = {"edge": 1, "face": 9}
_HCURL_P6_ENTITY_DIMENSION = {"edge": 6, "face": 60}
_HCURL_MISSING_DIMENSION = {"edge": 1, "face": 20}


def _validated_sha256(value: str, *, label: str) -> str:
    normalized = str(value).lower()
    try:
        valid = len(normalized) == 64 and len(bytes.fromhex(normalized)) == 32
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(f"{label} must contain 64 hexadecimal characters")
    return normalized


def _json_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _content_sha256(
    payload: Mapping[str, Any],
    arrays: Sequence[tuple[str, np.ndarray]],
) -> str:
    digest = hashlib.sha256()
    digest.update(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    for label, values in arrays:
        array = np.asarray(values)
        if np.issubdtype(array.dtype, np.integer):
            canonical = np.ascontiguousarray(array, dtype=np.dtype("<i8"))
        else:
            canonical = np.ascontiguousarray(array, dtype=np.dtype("<c16"))
        digest.update(label.encode("utf-8"))
        digest.update(np.asarray(canonical.shape, dtype="<i8").tobytes())
        digest.update(str(canonical.dtype).encode("ascii"))
        digest.update(canonical.tobytes())
    return digest.hexdigest()


def _readonly_matrix(values: np.ndarray, *, label: str) -> np.ndarray:
    matrix = np.array(values, dtype=np.complex128, copy=True)
    if matrix.ndim != 2 or not np.all(np.isfinite(matrix)):
        raise ValueError(f"{label} must be a finite matrix")
    matrix.setflags(write=False)
    return matrix


def _readonly_vector(values: np.ndarray, *, label: str) -> np.ndarray:
    vector = np.array(values, dtype=np.float64, copy=True)
    if vector.ndim != 1 or not np.all(np.isfinite(vector)):
        raise ValueError(f"{label} must be a finite vector")
    vector.setflags(write=False)
    return vector


def _relative_error(left: np.ndarray, right: np.ndarray) -> float:
    left_array = np.asarray(left, dtype=np.complex128)
    right_array = np.asarray(right, dtype=np.complex128)
    return float(np.linalg.norm(left_array - right_array)) / max(
        1.0,
        float(np.linalg.norm(left_array)),
        float(np.linalg.norm(right_array)),
    )


def _numerical_rank(
    values: np.ndarray,
) -> tuple[int, np.ndarray, float]:
    matrix = np.asarray(values, dtype=np.complex128)
    singular_values = np.linalg.svd(
        matrix,
        compute_uv=False,
    )
    largest = float(singular_values[0]) if len(singular_values) else 0.0
    tolerance = (
        max(matrix.shape, default=1)
        * np.finfo(np.float64).eps
        * max(1.0, largest)
        * 64.0
    )
    rank = int(np.count_nonzero(singular_values > tolerance))
    return rank, singular_values, tolerance


def _canonicalize_columns(values: np.ndarray) -> np.ndarray:
    result = np.asarray(values, dtype=np.complex128).copy()
    for column in range(result.shape[1]):
        pivot = int(np.argmax(np.abs(result[:, column])))
        value = result[pivot, column]
        if abs(value) == 0.0:
            raise RuntimeError("scalar shell basis contains a zero column")
        result[:, column] *= np.exp(-1.0j * np.angle(value))
        if result[pivot, column].real < 0.0:
            result[:, column] *= -1.0
        result[pivot, column] = complex(
            abs(result[pivot, column].real),
            0.0,
        )
    return result


@dataclass(frozen=True)
class ActualScalarEntityShell:
    """Actual Q6 entity coefficients complementary to the Q5 interpolation."""

    entity_id: int
    entity_kind: TraceEntityKind
    geometry_key: EntityGeometryKey
    q5_dimension: int
    q6_dimension: int
    scalar_shell_dimension: int
    interpolation_coefficients: np.ndarray
    interpolation_singular_values: np.ndarray
    interpolation_rank: int
    interpolation_rank_tolerance: float
    scalar_shell_basis: np.ndarray
    scalar_shell_orthogonality_error: float
    entity_shell_sha256: str

    def __post_init__(self) -> None:
        if self.entity_kind not in _ENTITY_DIMENSION:
            raise ValueError("scalar entity shell must be an edge or face")
        if int(self.entity_id) < 0:
            raise ValueError("scalar entity ID must be nonnegative")
        expected_q5 = _Q5_ENTITY_DIMENSION[self.entity_kind]
        expected_q6 = _Q6_ENTITY_DIMENSION[self.entity_kind]
        expected_shell = _SCALAR_SHELL_DIMENSION[self.entity_kind]
        if (
            int(self.q5_dimension) != expected_q5
            or int(self.q6_dimension) != expected_q6
            or int(self.scalar_shell_dimension) != expected_shell
        ):
            raise ValueError("scalar entity dimensions are inconsistent")
        interpolation = _readonly_matrix(
            self.interpolation_coefficients,
            label="Q5-to-Q6 entity interpolation",
        )
        shell = _readonly_matrix(
            self.scalar_shell_basis,
            label="Q5-to-Q6 scalar entity shell",
        )
        singular_values = _readonly_vector(
            self.interpolation_singular_values,
            label="Q5-to-Q6 interpolation singular values",
        )
        if interpolation.shape != (expected_q6, expected_q5):
            raise ValueError("entity interpolation matrix has the wrong shape")
        if shell.shape != (expected_q6, expected_shell):
            raise ValueError("scalar shell basis has the wrong shape")
        if len(singular_values) != expected_q5:
            raise ValueError(
                "entity interpolation singular-value count is wrong"
            )
        if int(self.interpolation_rank) != expected_q5:
            raise RuntimeError("actual Q5 entity interpolation is rank deficient")
        if (
            not np.isfinite(self.interpolation_rank_tolerance)
            or float(self.interpolation_rank_tolerance) <= 0.0
        ):
            raise ValueError("interpolation rank tolerance must be positive")
        if (
            not np.isfinite(self.scalar_shell_orthogonality_error)
            or float(self.scalar_shell_orthogonality_error) < 0.0
        ):
            raise ValueError("scalar shell leakage must be finite")
        object.__setattr__(self, "entity_id", int(self.entity_id))
        object.__setattr__(self, "q5_dimension", expected_q5)
        object.__setattr__(self, "q6_dimension", expected_q6)
        object.__setattr__(self, "scalar_shell_dimension", expected_shell)
        object.__setattr__(self, "interpolation_coefficients", interpolation)
        object.__setattr__(
            self,
            "interpolation_singular_values",
            singular_values,
        )
        object.__setattr__(self, "scalar_shell_basis", shell)
        object.__setattr__(
            self,
            "entity_shell_sha256",
            _validated_sha256(
                self.entity_shell_sha256,
                label="scalar entity shell SHA256",
            ),
        )


@dataclass(frozen=True)
class ActualScalarGradientOrbit:
    """Numerical scalar-shell gradient support for one physical orbit."""

    scalar_orbit_id: str
    anchor_trace_representative_id: int
    entity_kind: TraceEntityKind
    member_entity_ids: tuple[int, ...]
    scalar_mode_count: int
    representative_to_member_scalar_pullbacks: Mapping[int, np.ndarray]
    required_trace_representative_ids: tuple[int, ...]
    representative_missing_gradient_blocks: Mapping[int, np.ndarray]
    gradient_singular_values: np.ndarray
    discrete_gradient_rank: int
    discrete_gradient_rank_tolerance: float
    scalar_pullback_cycle_relative_error: float
    periodic_gradient_commuting_relative_error: float
    gradient_map_sha256: str

    def __post_init__(self) -> None:
        if self.entity_kind not in _ENTITY_DIMENSION:
            raise ValueError("scalar gradient orbit must be edge or face")
        orbit_id = str(self.scalar_orbit_id)
        if not orbit_id:
            raise ValueError("scalar gradient orbit ID must be nonempty")
        anchor = int(self.anchor_trace_representative_id)
        members = tuple(map(int, self.member_entity_ids))
        required = tuple(map(int, self.required_trace_representative_ids))
        expected = _SCALAR_SHELL_DIMENSION[self.entity_kind]
        if (
            anchor < 0
            or anchor not in members
            or not members
            or len(set(members)) != len(members)
        ):
            raise ValueError("scalar periodic orbit members are invalid")
        if (
            not required
            or len(set(required)) != len(required)
            or anchor not in required
        ):
            raise RuntimeError(
                "actual scalar gradient support does not include its anchor"
            )
        if int(self.scalar_mode_count) != expected:
            raise ValueError("scalar orbit mode count is wrong")
        if int(self.discrete_gradient_rank) != expected:
            raise RuntimeError(
                "actual scalar-shell discrete gradient is rank deficient"
            )
        if set(map(int, self.representative_to_member_scalar_pullbacks)) != set(
            members
        ):
            raise ValueError("scalar pullbacks do not cover the whole orbit")
        pullbacks: dict[int, np.ndarray] = {}
        for entity_id, values in (
            self.representative_to_member_scalar_pullbacks.items()
        ):
            matrix = _readonly_matrix(
                values,
                label="scalar Floquet orbit pullback",
            )
            if matrix.shape != (expected, expected):
                raise ValueError("scalar Floquet pullback has the wrong shape")
            pullbacks[int(entity_id)] = matrix
        identity = np.eye(expected, dtype=np.complex128)
        if _relative_error(pullbacks[anchor], identity) > 2.0e-12:
            raise RuntimeError(
                "scalar orbit representative pullback is not identity"
            )
        if set(map(int, self.representative_missing_gradient_blocks)) != set(
            required
        ):
            raise ValueError(
                "actual gradient coefficients do not cover declared support"
            )
        blocks: dict[int, np.ndarray] = {}
        for representative, values in (
            self.representative_missing_gradient_blocks.items()
        ):
            matrix = _readonly_matrix(
                values,
                label="representative missing-gradient coefficients",
            )
            if matrix.shape[1] != expected or matrix.shape[0] not in {1, 20}:
                raise ValueError(
                    "representative missing-gradient block has wrong shape"
                )
            blocks[int(representative)] = matrix
        singular_values = _readonly_vector(
            self.gradient_singular_values,
            label="discrete-gradient singular values",
        )
        if len(singular_values) != expected:
            raise ValueError(
                "discrete-gradient singular-value count is inconsistent"
            )
        for label, value in (
            (
                "scalar pullback cycle error",
                self.scalar_pullback_cycle_relative_error,
            ),
            (
                "periodic gradient commuting error",
                self.periodic_gradient_commuting_relative_error,
            ),
            (
                "discrete-gradient rank tolerance",
                self.discrete_gradient_rank_tolerance,
            ),
        ):
            if not np.isfinite(value) or float(value) < 0.0:
                raise ValueError(f"{label} must be finite and nonnegative")
        object.__setattr__(self, "scalar_orbit_id", orbit_id)
        object.__setattr__(
            self,
            "anchor_trace_representative_id",
            anchor,
        )
        object.__setattr__(self, "member_entity_ids", members)
        object.__setattr__(self, "scalar_mode_count", expected)
        object.__setattr__(
            self,
            "representative_to_member_scalar_pullbacks",
            MappingProxyType(pullbacks),
        )
        object.__setattr__(
            self,
            "required_trace_representative_ids",
            required,
        )
        object.__setattr__(
            self,
            "representative_missing_gradient_blocks",
            MappingProxyType(blocks),
        )
        object.__setattr__(
            self,
            "gradient_singular_values",
            singular_values,
        )
        object.__setattr__(
            self,
            "gradient_map_sha256",
            _validated_sha256(
                self.gradient_map_sha256,
                label="actual discrete-gradient map SHA256",
            ),
        )


@dataclass(frozen=True)
class ActualPhysicalDiscreteGradientAuthority(
    PhysicalDiscreteGradientAuthority
):
    """Base planner authority plus its actual numerical evidence."""

    dolfinx_version: str
    basix_version: str
    petsc_scalar_type: str
    petsc_int_type: str
    scalar_q5_global_dofs: int
    scalar_q6_global_dofs: int
    hcurl_p6_global_dofs: int
    interpolation_matrix_sha256: str
    discrete_gradient_matrix_sha256: str
    entity_shells: tuple[ActualScalarEntityShell, ...]
    orbit_evidence: tuple[ActualScalarGradientOrbit, ...]
    authority_sha256: str
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        super().__post_init__()
        if not str(self.dolfinx_version).startswith("0.10."):
            raise RuntimeError("actual authority requires DOLFINx 0.10")
        if not str(self.basix_version).startswith("0.10."):
            raise RuntimeError("actual authority requires Basix 0.10")
        if str(self.petsc_scalar_type) != "complex128":
            raise RuntimeError("actual authority requires complex128 PETSc")
        if str(self.petsc_int_type) != "int32":
            raise RuntimeError("actual authority requires int32 PETSc")
        if min(
            int(self.scalar_q5_global_dofs),
            int(self.scalar_q6_global_dofs),
            int(self.hcurl_p6_global_dofs),
        ) <= 0:
            raise ValueError("actual FE spaces must have positive dimensions")
        for field_name in (
            "interpolation_matrix_sha256",
            "discrete_gradient_matrix_sha256",
            "authority_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _validated_sha256(
                    getattr(self, field_name),
                    label=field_name.replace("_", " "),
                ),
            )
        shells = tuple(self.entity_shells)
        orbits = tuple(self.orbit_evidence)
        if not shells or not orbits:
            raise ValueError("actual discrete-gradient evidence is empty")
        if len(orbits) != len(self.rules):
            raise RuntimeError(
                "actual orbit evidence does not cover every planner rule"
            )
        if self.audit.get("pass") is not True:
            raise RuntimeError("actual discrete-gradient authority audit failed")
        object.__setattr__(self, "entity_shells", shells)
        object.__setattr__(self, "orbit_evidence", orbits)
        object.__setattr__(self, "audit", MappingProxyType(dict(self.audit)))


@dataclass(frozen=True)
class _EntityDofs:
    entity_id: int
    entity_kind: TraceEntityKind
    geometry_key: EntityGeometryKey
    global_dofs: tuple[int, ...]


@dataclass(frozen=True)
class _DistributedMatrixIdentity:
    shape: tuple[int, int]
    stored_nnz: int
    numerical_nnz: int
    matrix_sha256: str


def _validate_spaces(
    *,
    full_p6_hcurl_space: Any,
    q5_space: Any,
    q6_space: Any,
    qualification: P5P6TraceComplementQualification,
) -> None:
    msh = full_p6_hcurl_space.mesh
    if (
        q5_space.mesh is not msh
        or q6_space.mesh is not msh
        or "hexahedron" not in str(msh.basix_cell()).lower()
    ):
        raise RuntimeError(
            "Q5, Q6, and N1curl-p6 must share one hexahedral mesh"
        )
    q5 = q5_space.element.basix_element
    q6 = q6_space.element.basix_element
    v6 = full_p6_hcurl_space.element.basix_element
    v6_reference = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        6,
        basix.LagrangeVariant.legendre,
    )
    checks = {
        "dolfinx_0_10": str(dolfinx.__version__).startswith("0.10."),
        "basix_0_10": str(basix.__version__).startswith("0.10."),
        "petsc_complex128": np.dtype(PETSc.ScalarType)
        == np.dtype(np.complex128),
        "petsc_int32": np.dtype(PETSc.IntType) == np.dtype(np.int32),
        "q5_is_conforming_GLL_Q5": (
            q5.family == basix.ElementFamily.P
            and q5.cell_type == basix.CellType.hexahedron
            and q5.degree == 5
            and q5.sobolev_space == basix.SobolevSpace.H1
            and q5.map_type == basix.MapType.identity
            and q5.lagrange_variant == basix.LagrangeVariant.gll_warped
            and not q5.discontinuous
        ),
        "q6_is_conforming_GLL_Q6": (
            q6.family == basix.ElementFamily.P
            and q6.cell_type == basix.CellType.hexahedron
            and q6.degree == 6
            and q6.sobolev_space == basix.SobolevSpace.H1
            and q6.map_type == basix.MapType.identity
            and q6.lagrange_variant == basix.LagrangeVariant.gll_warped
            and not q6.discontinuous
        ),
        "v6_is_legendre_N1curl": (
            v6.hash() == v6_reference.hash()
            and v6.dim == 882
            and v6.map_type == basix.MapType.covariantPiola
            and v6.sobolev_space == basix.SobolevSpace.HCurl
            and v6.lagrange_variant == basix.LagrangeVariant.legendre
        ),
        "qualified_Riesz_basis_matches_v6": (
            qualification.audit.get("p6_dimension") == int(v6.dim)
            and qualification.audit.get("pass") is True
        ),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "actual same-mesh discrete-gradient space Gate failed: "
            + ", ".join(failed)
        )


def _global_entity_dofs(
    space: Any,
    *,
    catalog: SelectiveP6TraceMeshCatalog,
    coordinate_tolerance: float,
    expected_dimensions: Mapping[str, int],
) -> tuple[_EntityDofs, ...]:
    msh = space.mesh
    comm = msh.comm
    tdim = msh.topology.dim
    finite_element = space.element.basix_element
    dofmap = space.dofmap
    if int(dofmap.index_map_bs) != 1:
        raise NotImplementedError(
            "actual discrete-gradient authority requires scalar-blocked DoFs"
        )
    by_geometry = {
        (entity.entity_kind, entity.geometry_key): entity
        for entity in catalog.entities
    }
    local_records: dict[int, _EntityDofs] = {}
    for entity_kind in ("edge", "face"):
        dimension = _ENTITY_DIMENSION[entity_kind]
        msh.topology.create_entities(dimension)
        msh.topology.create_connectivity(tdim, dimension)
        cell_to_entity = msh.topology.connectivity(tdim, dimension)
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
        local_entity_dofs = finite_element.entity_dofs[dimension]
        cell_count = int(
            msh.topology.index_map(tdim).size_local
            + msh.topology.index_map(tdim).num_ghosts
        )
        for cell in range(cell_count):
            cell_entities = cell_to_entity.links(cell)
            cell_dofs = dofmap.cell_dofs(cell)
            if len(cell_entities) != len(local_entity_dofs):
                raise RuntimeError(
                    "Basix and DOLFINx entity inventories disagree"
                )
            for local_entity, mesh_entity in enumerate(cell_entities):
                positions = np.asarray(
                    local_entity_dofs[local_entity],
                    dtype=np.int32,
                )
                expected = int(expected_dimensions[entity_kind])
                if len(positions) != expected:
                    raise RuntimeError(
                        f"actual {entity_kind} DoF count is not {expected}"
                    )
                local_dofs = np.asarray(
                    cell_dofs[positions],
                    dtype=np.int32,
                )
                global_dofs = tuple(
                    map(
                        int,
                        dofmap.index_map.local_to_global(local_dofs),
                    )
                )
                geometry_key = geometry_key_by_local[int(mesh_entity)]
                try:
                    physical = by_geometry[(entity_kind, geometry_key)]
                except KeyError as exc:
                    raise RuntimeError(
                        "actual FE entity is absent from the physical catalog"
                    ) from exc
                record = _EntityDofs(
                    entity_id=physical.entity_id,
                    entity_kind=entity_kind,
                    geometry_key=geometry_key,
                    global_dofs=global_dofs,
                )
                previous = local_records.get(physical.entity_id)
                if previous is not None and previous != record:
                    raise RuntimeError(
                        "DOLFINx entity DoF ordering differs across cells"
                    )
                local_records[physical.entity_id] = record

    gathered = [
        record
        for rank_records in comm.allgather(tuple(local_records.values()))
        for record in rank_records
    ]
    global_records: dict[int, _EntityDofs] = {}
    for record in gathered:
        previous = global_records.setdefault(record.entity_id, record)
        if previous != record:
            raise RuntimeError(
                "MPI copies disagree on physical entity DoF ordering"
            )
    expected_ids = set(range(len(catalog.entities)))
    if set(global_records) != expected_ids:
        raise RuntimeError("actual entity DoF map is incomplete")
    ordered = tuple(
        global_records[entity_id] for entity_id in sorted(global_records)
    )
    flattened = [
        dof for record in ordered for dof in record.global_dofs
    ]
    if len(flattened) != len(set(flattened)):
        raise RuntimeError("physical entity DoF blocks overlap")
    return ordered


def _scalar_dof_coordinates(
    space: Any,
    *,
    records: Sequence[_EntityDofs],
    coordinate_tolerance: float,
) -> Mapping[int, np.ndarray]:
    comm = space.mesh.comm
    index_map = space.dofmap.index_map
    count = int(index_map.size_local + index_map.num_ghosts)
    local_ids = index_map.local_to_global(
        np.arange(count, dtype=np.int32)
    )
    coordinates = np.asarray(
        space.tabulate_dof_coordinates(),
        dtype=np.float64,
    )
    if coordinates.shape != (count, 3):
        raise RuntimeError(
            "conforming scalar GLL DoFs do not expose point coordinates"
        )
    needed = {
        dof for record in records for dof in record.global_dofs
    }
    local = tuple(
        (
            int(global_id),
            tuple(float(value) for value in coordinates[local_id]),
        )
        for local_id, global_id in enumerate(local_ids)
        if int(global_id) in needed
    )
    result: dict[int, np.ndarray] = {}
    for packet in comm.allgather(local):
        for global_id, values in packet:
            point = np.asarray(values, dtype=np.float64)
            previous = result.get(int(global_id))
            if previous is not None:
                if np.linalg.norm(previous - point) > coordinate_tolerance:
                    raise RuntimeError(
                        "MPI copies disagree on scalar GLL DoF coordinates"
                    )
            else:
                result[int(global_id)] = point
    if set(result) != needed:
        raise RuntimeError("scalar entity DoF coordinates are incomplete")
    return MappingProxyType(result)


def _distributed_matrix_identity(
    matrix: Any,
    *,
    comm: Any,
    label: str,
) -> _DistributedMatrixIdentity:
    csr = matrix.to_scipy().tocsr()
    csr.sort_indices()
    row_map = matrix.index_map(0)
    column_map = matrix.index_map(1)
    row_count = int(row_map.size_local)
    local_column_count = int(
        column_map.size_local + column_map.num_ghosts
    )
    if csr.shape != (row_count, local_column_count):
        raise RuntimeError(f"{label} local CSR shape is inconsistent")
    global_columns_by_local = column_map.local_to_global(
        np.arange(local_column_count, dtype=np.int32)
    )
    global_rows = row_map.local_to_global(
        np.arange(row_count, dtype=np.int32)
    )
    local_records: list[tuple[int, str, int, int]] = []
    for local_row, global_row in enumerate(global_rows):
        start = int(csr.indptr[local_row])
        stop = int(csr.indptr[local_row + 1])
        local_columns = np.asarray(
            csr.indices[start:stop],
            dtype=np.int64,
        )
        if len(local_columns) and (
            int(np.min(local_columns)) < 0
            or int(np.max(local_columns)) >= local_column_count
        ):
            raise RuntimeError(f"{label} has an invalid local column index")
        columns = np.asarray(
            global_columns_by_local[local_columns],
            dtype=np.int64,
        )
        values = np.asarray(csr.data[start:stop], dtype=np.complex128)
        if not np.all(np.isfinite(values)):
            raise FloatingPointError(f"{label} contains NaN or Inf")
        row_sha256 = _content_sha256(
            {
                "schema": "task035b.distributed-matrix-row.v1",
                "label": label,
                "global_row": int(global_row),
            },
            (
                ("columns", columns),
                ("values", values),
            ),
        )
        local_records.append(
            (
                int(global_row),
                row_sha256,
                len(values),
                int(np.count_nonzero(values)),
            )
        )
    records = tuple(
        record
        for packet in comm.allgather(tuple(local_records))
        for record in packet
    )
    expected_rows = int(row_map.size_global)
    if (
        len(records) != expected_rows
        or {record[0] for record in records} != set(range(expected_rows))
    ):
        raise RuntimeError(f"{label} global row hash inventory is incomplete")
    records = tuple(sorted(records))
    matrix_hash = _json_sha256(
        {
            "schema": "task035b.actual-dolfinx-matrix-identity.v1",
            "label": label,
            "shape": [expected_rows, int(column_map.size_global)],
            "rows": records,
        }
    )
    return _DistributedMatrixIdentity(
        shape=(expected_rows, int(column_map.size_global)),
        stored_nnz=sum(record[2] for record in records),
        numerical_nnz=sum(record[3] for record in records),
        matrix_sha256=matrix_hash,
    )


def _extract_trace_blocks(
    matrix: Any,
    *,
    row_records: Sequence[_EntityDofs],
    column_records: Sequence[_EntityDofs],
    comm: Any,
) -> Mapping[tuple[int, int], np.ndarray]:
    row_lookup = {
        int(dof): (record.entity_id, position)
        for record in row_records
        for position, dof in enumerate(record.global_dofs)
    }
    column_lookup = {
        int(dof): (record.entity_id, position)
        for record in column_records
        for position, dof in enumerate(record.global_dofs)
    }
    row_dimensions = {
        record.entity_id: len(record.global_dofs) for record in row_records
    }
    column_dimensions = {
        record.entity_id: len(record.global_dofs)
        for record in column_records
    }
    csr = matrix.to_scipy().tocsr()
    csr.sort_indices()
    row_map = matrix.index_map(0)
    column_map = matrix.index_map(1)
    local_column_count = int(
        column_map.size_local + column_map.num_ghosts
    )
    global_columns_by_local = column_map.local_to_global(
        np.arange(local_column_count, dtype=np.int32)
    )
    global_rows = row_map.local_to_global(
        np.arange(row_map.size_local, dtype=np.int32)
    )
    local_blocks: dict[tuple[int, int], np.ndarray] = {}
    local_occupied: dict[tuple[int, int], np.ndarray] = {}
    for local_row, global_row in enumerate(global_rows):
        row_identity = row_lookup.get(int(global_row))
        if row_identity is None:
            continue
        target_entity, row_position = row_identity
        start = int(csr.indptr[local_row])
        stop = int(csr.indptr[local_row + 1])
        for entry in range(start, stop):
            value = complex(csr.data[entry])
            if value == 0.0:
                continue
            local_column = int(csr.indices[entry])
            if local_column < 0 or local_column >= local_column_count:
                raise RuntimeError(
                    "distributed matrix has an invalid local column index"
                )
            global_column = int(global_columns_by_local[local_column])
            column_identity = column_lookup.get(global_column)
            if column_identity is None:
                continue
            source_entity, column_position = column_identity
            key = (target_entity, source_entity)
            shape = (
                row_dimensions[target_entity],
                column_dimensions[source_entity],
            )
            block = local_blocks.setdefault(
                key,
                np.zeros(shape, dtype=np.complex128),
            )
            occupied = local_occupied.setdefault(
                key,
                np.zeros(shape, dtype=np.bool_),
            )
            if occupied[row_position, column_position]:
                raise RuntimeError(
                    "rank-local matrix trace coefficient is duplicated"
                )
            block[row_position, column_position] = value
            occupied[row_position, column_position] = True
    local_packet = tuple(
        (
            target,
            source,
            local_blocks[(target, source)],
            local_occupied[(target, source)],
        )
        for target, source in sorted(local_blocks)
    )
    blocks: dict[tuple[int, int], np.ndarray] = {}
    occupied_by_block: dict[tuple[int, int], np.ndarray] = {}
    for packet in comm.allgather(local_packet):
        for target_entity, source_entity, local_block, local_mask in packet:
            key = (target_entity, source_entity)
            shape = (
                row_dimensions[target_entity],
                column_dimensions[source_entity],
            )
            block = blocks.setdefault(
                key,
                np.zeros(shape, dtype=np.complex128),
            )
            occupied = occupied_by_block.setdefault(
                key,
                np.zeros(shape, dtype=np.bool_),
            )
            mask = np.asarray(local_mask, dtype=np.bool_)
            if np.any(occupied & mask):
                raise RuntimeError(
                    "distributed matrix trace coefficient has multiple owners"
                )
            block[mask] = np.asarray(local_block)[mask]
            occupied |= mask
    return MappingProxyType(blocks)


def _scalar_entity_shells(
    *,
    catalog: SelectiveP6TraceMeshCatalog,
    interpolation_blocks: Mapping[tuple[int, int], np.ndarray],
    algebra_tolerance: float,
) -> tuple[ActualScalarEntityShell, ...]:
    result: list[ActualScalarEntityShell] = []
    # A nodal Q5 edge basis legitimately has values at Q6 face-interior
    # points on incident faces.  The entity shell is the topological quotient
    # of the entity-interior block, so only its diagonal entity block enters
    # this construction.  Periodic commuting is checked below on that actual
    # block; off-diagonal interpolation is not mislabeled as leakage.
    for entity in catalog.entities:
        q5_dimension = _Q5_ENTITY_DIMENSION[entity.entity_kind]
        q6_dimension = _Q6_ENTITY_DIMENSION[entity.entity_kind]
        shell_dimension = _SCALAR_SHELL_DIMENSION[entity.entity_kind]
        interpolation = np.asarray(
            interpolation_blocks.get(
                (entity.entity_id, entity.entity_id),
                np.zeros(
                    (q6_dimension, q5_dimension),
                    dtype=np.complex128,
                ),
            ),
            dtype=np.complex128,
        )
        rank, singular_values, rank_tolerance = _numerical_rank(
            interpolation
        )
        complete_q, _r = np.linalg.qr(
            interpolation,
            mode="complete",
        )
        shell_basis = _canonicalize_columns(complete_q[:, rank:])
        if shell_basis.shape[1] != shell_dimension:
            raise RuntimeError(
                "actual scalar p5-to-p6 entity shell has wrong dimension"
            )
        orthogonality_error = float(
            np.linalg.norm(shell_basis.conj().T @ interpolation)
        ) / max(1.0, float(np.linalg.norm(interpolation)))
        entity_hash = _content_sha256(
            {
                "schema": "task035b.actual-scalar-entity-shell.v1",
                "entity_id": entity.entity_id,
                "entity_kind": entity.entity_kind,
                "geometry_key": entity.geometry_key,
                "interpolation_rank": rank,
                "rank_tolerance": rank_tolerance,
                "orthogonality_error": orthogonality_error,
            },
            (
                ("interpolation", interpolation),
                ("singular_values", singular_values),
                ("scalar_shell_basis", shell_basis),
            ),
        )
        shell = ActualScalarEntityShell(
            entity_id=entity.entity_id,
            entity_kind=entity.entity_kind,
            geometry_key=entity.geometry_key,
            q5_dimension=q5_dimension,
            q6_dimension=q6_dimension,
            scalar_shell_dimension=shell_dimension,
            interpolation_coefficients=interpolation,
            interpolation_singular_values=singular_values,
            interpolation_rank=rank,
            interpolation_rank_tolerance=rank_tolerance,
            scalar_shell_basis=shell_basis,
            scalar_shell_orthogonality_error=orthogonality_error,
            entity_shell_sha256=entity_hash,
        )
        if (
            shell.scalar_shell_orthogonality_error
            > 50.0 * algebra_tolerance
        ):
            raise RuntimeError(
                "actual scalar shell leaks into Q5 interpolation range"
            )
        result.append(shell)
    return tuple(result)


def _point_permutation(
    *,
    slave_coordinates: np.ndarray,
    master_coordinates: np.ndarray,
    shift: np.ndarray,
    tolerance: float,
) -> np.ndarray:
    slave = np.asarray(slave_coordinates, dtype=np.float64)
    master = np.asarray(master_coordinates, dtype=np.float64)
    if slave.shape != master.shape or slave.ndim != 2:
        raise RuntimeError("periodic scalar entity coordinate shapes differ")
    permutation = np.zeros(
        (len(slave), len(master)),
        dtype=np.complex128,
    )
    used: set[int] = set()
    for slave_index, point in enumerate(slave):
        distances = np.linalg.norm(
            master - (point - shift),
            axis=1,
        )
        master_index = int(np.argmin(distances))
        if (
            float(distances[master_index]) > tolerance
            or master_index in used
        ):
            raise RuntimeError(
                "periodic scalar GLL nodes do not form a bijection"
            )
        permutation[slave_index, master_index] = 1.0
        used.add(master_index)
    if len(used) != len(master):
        raise RuntimeError("periodic scalar GLL node matching is incomplete")
    return permutation


def _scalar_orbit_pullbacks(
    *,
    catalog: SelectiveP6TraceMeshCatalog,
    entity_shells: Sequence[ActualScalarEntityShell],
    q5_records: Sequence[_EntityDofs],
    q6_records: Sequence[_EntityDofs],
    q5_coordinates: Mapping[int, np.ndarray],
    q6_coordinates: Mapping[int, np.ndarray],
    coordinate_tolerance: float,
    algebra_tolerance: float,
) -> tuple[
    Mapping[int, Mapping[int, np.ndarray]],
    float,
    float,
]:
    shells = {shell.entity_id: shell for shell in entity_shells}
    q5 = {record.entity_id: record for record in q5_records}
    q6 = {record.entity_id: record for record in q6_records}
    adjacency: dict[int, list[tuple[int, np.ndarray]]] = {
        entity.entity_id: [] for entity in catalog.entities
    }
    maximum_interpolation_error = 0.0
    maximum_shell_error = 0.0
    match_tolerance = 8.0 * coordinate_tolerance
    for relation in catalog.relation_metadata:
        slave = relation.slave_entity_id
        master = relation.master_entity_id
        slave_entity = catalog.entities[slave]
        master_entity = catalog.entities[master]
        shift = coordinate_tolerance * (
            np.mean(
                np.asarray(slave_entity.geometry_key, dtype=np.float64),
                axis=0,
            )
            - np.mean(
                np.asarray(master_entity.geometry_key, dtype=np.float64),
                axis=0,
            )
        )
        q5_permutation = _point_permutation(
            slave_coordinates=np.asarray(
                [q5_coordinates[dof] for dof in q5[slave].global_dofs]
            ),
            master_coordinates=np.asarray(
                [q5_coordinates[dof] for dof in q5[master].global_dofs]
            ),
            shift=shift,
            tolerance=match_tolerance,
        )
        q6_permutation = _point_permutation(
            slave_coordinates=np.asarray(
                [q6_coordinates[dof] for dof in q6[slave].global_dofs]
            ),
            master_coordinates=np.asarray(
                [q6_coordinates[dof] for dof in q6[master].global_dofs]
            ),
            shift=shift,
            tolerance=match_tolerance,
        )
        phase = complex(relation.floquet_phase)
        q5_pullback = phase * q5_permutation
        q6_pullback = phase * q6_permutation
        slave_shell = shells[slave]
        master_shell = shells[master]
        interpolation_error = _relative_error(
            q6_pullback @ master_shell.interpolation_coefficients,
            slave_shell.interpolation_coefficients @ q5_pullback,
        )
        maximum_interpolation_error = max(
            maximum_interpolation_error,
            interpolation_error,
        )
        scalar_pullback, _residuals, induced_rank, _singulars = (
            np.linalg.lstsq(
                slave_shell.scalar_shell_basis,
                q6_pullback @ master_shell.scalar_shell_basis,
                rcond=None,
            )
        )
        if induced_rank != master_shell.scalar_shell_dimension:
            raise RuntimeError("induced scalar Floquet pullback is rank deficient")
        shell_error = _relative_error(
            q6_pullback @ master_shell.scalar_shell_basis,
            slave_shell.scalar_shell_basis @ scalar_pullback,
        )
        maximum_shell_error = max(maximum_shell_error, shell_error)
        adjacency[master].append((slave, scalar_pullback))
        adjacency[slave].append(
            (
                master,
                np.linalg.solve(
                    scalar_pullback,
                    np.eye(
                        scalar_pullback.shape[0],
                        dtype=np.complex128,
                    ),
                ),
            )
        )

    pullbacks: dict[int, Mapping[int, np.ndarray]] = {}
    maximum_cycle_error = 0.0
    for orbit in catalog.all_inactive_orbit_numbering.orbits:
        representative = orbit.representative_entity_id
        dimension = shells[representative].scalar_shell_dimension
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
                else:
                    error = _relative_error(transforms[neighbor], candidate)
                    maximum_cycle_error = max(maximum_cycle_error, error)
        if set(transforms) != set(orbit.member_entity_ids):
            raise RuntimeError(
                "scalar and H(curl) physical periodic orbits differ"
            )
        frozen: dict[int, np.ndarray] = {}
        for member, transform in transforms.items():
            matrix = _readonly_matrix(
                transform,
                label="actual scalar orbit pullback",
            )
            frozen[member] = matrix
        pullbacks[representative] = MappingProxyType(frozen)
    maximum_relation_error = max(
        maximum_interpolation_error,
        maximum_shell_error,
    )
    if (
        maximum_relation_error > 50.0 * algebra_tolerance
        or maximum_cycle_error > 50.0 * algebra_tolerance
    ):
        raise RuntimeError(
            "actual scalar interpolation/Floquet pullback does not commute"
        )
    return (
        MappingProxyType(pullbacks),
        maximum_relation_error,
        maximum_cycle_error,
    )


def _allowed_trace_incidence(
    *,
    source_entity: Any,
    target_entity: Any,
) -> bool:
    if source_entity.entity_kind == "face":
        return (
            target_entity.entity_kind == "face"
            and target_entity.entity_id == source_entity.entity_id
        )
    if (
        target_entity.entity_kind == "edge"
        and target_entity.entity_id == source_entity.entity_id
    ):
        return True
    return (
        target_entity.entity_kind == "face"
        and set(source_entity.geometry_key).issubset(
            set(target_entity.geometry_key)
        )
    )


def _missing_gradient_entity_blocks(
    *,
    catalog: SelectiveP6TraceMeshCatalog,
    qualification: P5P6TraceComplementQualification,
    entity_shells: Sequence[ActualScalarEntityShell],
    raw_gradient_blocks: Mapping[tuple[int, int], np.ndarray],
    algebra_tolerance: float,
) -> tuple[Mapping[tuple[int, int], np.ndarray], float, float]:
    shells = {shell.entity_id: shell for shell in entity_shells}
    result: dict[tuple[int, int], np.ndarray] = {}
    leakage_sq = 0.0
    gradient_sq = 0.0
    forbidden_sq = 0.0
    for (target_id, source_id), raw_block in raw_gradient_blocks.items():
        target = catalog.entities[target_id]
        source = catalog.entities[source_id]
        scalar_basis = shells[source_id].scalar_shell_basis
        trace_gradient = np.asarray(raw_block) @ scalar_basis
        hcurl_shell = getattr(qualification, target.entity_kind)
        missing_coefficients = (
            hcurl_shell.missing_basis.conj().T
            @ hcurl_shell.trace_l2_gram
            @ trace_gradient
        )
        reconstructed = (
            hcurl_shell.retained_riesz_projector @ trace_gradient
            + hcurl_shell.missing_basis @ missing_coefficients
        )
        leakage_sq += float(
            np.linalg.norm(trace_gradient - reconstructed)
        ) ** 2
        gradient_sq += float(np.linalg.norm(trace_gradient)) ** 2
        if not _allowed_trace_incidence(
            source_entity=source,
            target_entity=target,
        ):
            forbidden_sq += float(np.linalg.norm(missing_coefficients)) ** 2
        if np.linalg.norm(missing_coefficients) > 0.0:
            result[(target_id, source_id)] = np.asarray(
                missing_coefficients,
                dtype=np.complex128,
            )
    decomposition_error = np.sqrt(leakage_sq) / max(
        1.0,
        np.sqrt(gradient_sq),
    )
    forbidden_error = np.sqrt(forbidden_sq) / max(
        1.0,
        np.sqrt(gradient_sq),
    )
    if (
        decomposition_error > 50.0 * algebra_tolerance
        or forbidden_error > 50.0 * algebra_tolerance
    ):
        raise RuntimeError(
            "actual discrete gradient fails Piola/Riesz trace leakage Gate"
        )
    return (
        MappingProxyType(result),
        decomposition_error,
        forbidden_error,
    )


def _fit_representative_block(
    *,
    orbit: PhysicalP6TraceOrbitPullback,
    entity_coefficients: Mapping[int, np.ndarray],
    scalar_mode_count: int,
) -> tuple[np.ndarray, float]:
    dimension = orbit.dimension
    denominator = np.zeros(
        (dimension, dimension),
        dtype=np.complex128,
    )
    numerator = np.zeros(
        (dimension, scalar_mode_count),
        dtype=np.complex128,
    )
    for member in orbit.member_entity_ids:
        pullback = orbit.representative_to_member[member]
        denominator += pullback.conj().T @ pullback
        numerator += pullback.conj().T @ entity_coefficients[member]
    representative = np.linalg.solve(denominator, numerator)
    error_sq = 0.0
    scale_sq = 0.0
    for member in orbit.member_entity_ids:
        expected = orbit.representative_to_member[member] @ representative
        actual = entity_coefficients[member]
        error_sq += float(np.linalg.norm(actual - expected)) ** 2
        scale_sq += float(np.linalg.norm(actual)) ** 2
    return representative, np.sqrt(error_sq) / max(1.0, np.sqrt(scale_sq))


def _ordered_scalar_basis_sha256(
    *,
    catalog: SelectiveP6TraceMeshCatalog,
    interpolation_matrix_sha256: str,
    entity_shells: Sequence[ActualScalarEntityShell],
    scalar_pullbacks: Mapping[int, Mapping[int, np.ndarray]],
) -> str:
    arrays: list[tuple[str, np.ndarray]] = []
    for shell in entity_shells:
        arrays.extend(
            (
                (
                    f"entity:{shell.entity_id}:interpolation",
                    shell.interpolation_coefficients,
                ),
                (
                    f"entity:{shell.entity_id}:scalar-shell",
                    shell.scalar_shell_basis,
                ),
            )
        )
    for representative, members in sorted(scalar_pullbacks.items()):
        for member, transform in sorted(members.items()):
            arrays.append(
                (
                    f"orbit:{representative}:member:{member}:pullback",
                    transform,
                )
            )
    return _content_sha256(
        {
            "schema": "task035b.actual-ordered-scalar-Q5-Q6-shell.v1",
            "dolfinx_version": dolfinx.__version__,
            "basix_version": basix.__version__,
            "catalog_sha256": catalog.catalog_sha256,
            "trace_geometry_sha256": catalog.trace_geometry_sha256,
            "interpolation_matrix_sha256": interpolation_matrix_sha256,
            "entities": [
                {
                    "entity_id": shell.entity_id,
                    "entity_kind": shell.entity_kind,
                    "geometry_key": shell.geometry_key,
                    "entity_shell_sha256": shell.entity_shell_sha256,
                }
                for shell in entity_shells
            ],
        },
        arrays,
    )


def _build_orbit_evidence(
    *,
    catalog: SelectiveP6TraceMeshCatalog,
    entity_shells: Sequence[ActualScalarEntityShell],
    scalar_pullbacks: Mapping[int, Mapping[int, np.ndarray]],
    hcurl_pullbacks: Sequence[PhysicalP6TraceOrbitPullback],
    missing_gradient_blocks: Mapping[tuple[int, int], np.ndarray],
    ordered_scalar_basis_sha256: str,
    discrete_gradient_matrix_sha256: str,
    scalar_pullback_cycle_error: float,
    support_tolerance: float,
    algebra_tolerance: float,
) -> tuple[
    tuple[ActualScalarGradientOrbit, ...],
    tuple[DiscreteGradientOrbitRule, ...],
    float,
]:
    shells = {shell.entity_id: shell for shell in entity_shells}
    hcurl_by_representative = {
        orbit.representative_entity_id: orbit for orbit in hcurl_pullbacks
    }
    result: list[ActualScalarGradientOrbit] = []
    rules: list[DiscreteGradientOrbitRule] = []
    maximum_commuting_error = 0.0
    for scalar_orbit in catalog.all_inactive_orbit_numbering.orbits:
        representative = scalar_orbit.representative_entity_id
        scalar_dimension = shells[representative].scalar_shell_dimension
        entity_coefficients = {
            entity.entity_id: np.zeros(
                (
                    _HCURL_MISSING_DIMENSION[entity.entity_kind],
                    scalar_dimension,
                ),
                dtype=np.complex128,
            )
            for entity in catalog.entities
        }
        for source in scalar_orbit.member_entity_ids:
            scalar_transform = scalar_pullbacks[representative][source]
            for target in catalog.entities:
                block = missing_gradient_blocks.get(
                    (target.entity_id, source)
                )
                if block is not None:
                    entity_coefficients[target.entity_id] += (
                        block @ scalar_transform
                    )

        representative_blocks: dict[int, np.ndarray] = {}
        orbit_commuting_error = 0.0
        for trace_representative, hcurl_orbit in sorted(
            hcurl_by_representative.items()
        ):
            block, error = _fit_representative_block(
                orbit=hcurl_orbit,
                entity_coefficients=entity_coefficients,
                scalar_mode_count=scalar_dimension,
            )
            orbit_commuting_error = max(orbit_commuting_error, error)
            representative_blocks[trace_representative] = block
        maximum_commuting_error = max(
            maximum_commuting_error,
            orbit_commuting_error,
        )
        scale = max(
            1.0,
            np.sqrt(
                sum(
                    float(np.linalg.norm(block)) ** 2
                    for block in representative_blocks.values()
                )
            ),
        )
        required = tuple(
            representative_id
            for representative_id, block in sorted(
                representative_blocks.items()
            )
            if np.linalg.norm(block) > support_tolerance * scale
        )
        if representative not in required:
            raise RuntimeError(
                "actual scalar gradient does not activate its H(curl) anchor"
            )
        active_blocks = {
            target: representative_blocks[target] for target in required
        }
        stacked = np.vstack(
            [active_blocks[target] for target in required]
        )
        gradient_rank, singular_values, rank_tolerance = _numerical_rank(
            stacked
        )
        if gradient_rank != scalar_dimension:
            raise RuntimeError(
                "actual scalar-orbit discrete gradient is rank deficient"
            )
        orbit_id = f"actual-scalar-{scalar_orbit.entity_kind}:{representative}"
        map_hash = _content_sha256(
            {
                "schema": (
                    "task035b.actual-scalar-to-missing-N1curl-gradient.v1"
                ),
                "scalar_orbit_id": orbit_id,
                "anchor_trace_representative_id": representative,
                "member_entity_ids": scalar_orbit.member_entity_ids,
                "required_trace_representative_ids": required,
                "ordered_scalar_basis_sha256": (
                    ordered_scalar_basis_sha256
                ),
                "ordered_trace_basis_sha256": (
                    catalog.ordered_trace_basis_sha256
                ),
                "discrete_gradient_matrix_sha256": (
                    discrete_gradient_matrix_sha256
                ),
                "gradient_rank": gradient_rank,
                "gradient_rank_tolerance": rank_tolerance,
                "periodic_gradient_commuting_relative_error": (
                    orbit_commuting_error
                ),
                "scalar_pullback_cycle_relative_error": (
                    scalar_pullback_cycle_error
                ),
                "support_tolerance": support_tolerance,
            },
            tuple(
                (
                    f"scalar-pullback:{member}",
                    scalar_pullbacks[representative][member],
                )
                for member in scalar_orbit.member_entity_ids
            )
            + tuple(
                (
                    f"trace-gradient:{target}",
                    active_blocks[target],
                )
                for target in required
            )
            + (("gradient-singular-values", singular_values),),
        )
        evidence = ActualScalarGradientOrbit(
            scalar_orbit_id=orbit_id,
            anchor_trace_representative_id=representative,
            entity_kind=scalar_orbit.entity_kind,
            member_entity_ids=scalar_orbit.member_entity_ids,
            scalar_mode_count=scalar_dimension,
            representative_to_member_scalar_pullbacks=(
                scalar_pullbacks[representative]
            ),
            required_trace_representative_ids=required,
            representative_missing_gradient_blocks=active_blocks,
            gradient_singular_values=singular_values,
            discrete_gradient_rank=gradient_rank,
            discrete_gradient_rank_tolerance=rank_tolerance,
            scalar_pullback_cycle_relative_error=(
                scalar_pullback_cycle_error
            ),
            periodic_gradient_commuting_relative_error=(
                orbit_commuting_error
            ),
            gradient_map_sha256=map_hash,
        )
        result.append(evidence)
        rules.append(
            DiscreteGradientOrbitRule(
                scalar_orbit_id=orbit_id,
                anchor_trace_representative_id=representative,
                required_trace_representative_ids=required,
                scalar_mode_count=scalar_dimension,
                discrete_gradient_rank=gradient_rank,
                ordered_scalar_basis_sha256=(
                    ordered_scalar_basis_sha256
                ),
                ordered_trace_basis_sha256=(
                    catalog.ordered_trace_basis_sha256
                ),
                gradient_map_sha256=map_hash,
                periodic_orbit_closed=True,
                discrete_gradient_verified=True,
                gradient_map_binds_ordered_basis_identity=True,
            )
        )
    if maximum_commuting_error > 50.0 * algebra_tolerance:
        raise RuntimeError(
            "actual discrete gradient does not commute with Floquet pullbacks"
        )
    return tuple(result), tuple(rules), maximum_commuting_error


def _constant_action_errors(
    *,
    interpolation_matrix: Any,
    discrete_gradient_matrix: Any,
    comm: Any,
) -> tuple[float, float]:
    interpolation = interpolation_matrix.to_scipy().tocsr()
    gradient = discrete_gradient_matrix.to_scipy().tocsr()
    interpolation_error = interpolation @ np.ones(
        interpolation.shape[1],
        dtype=np.float64,
    ) - 1.0
    gradient_error = gradient @ np.ones(
        gradient.shape[1],
        dtype=np.float64,
    )
    interpolation_norm = float(
        np.sqrt(comm.allreduce(float(np.vdot(
            interpolation_error,
            interpolation_error,
        ).real)))
    )
    gradient_norm = float(
        np.sqrt(comm.allreduce(float(np.vdot(
            gradient_error,
            gradient_error,
        ).real)))
    )
    return interpolation_norm, gradient_norm


def build_actual_physical_discrete_gradient_authority(
    *,
    full_p6_hcurl_space: Any,
    catalog: SelectiveP6TraceMeshCatalog,
    qualification: P5P6TraceComplementQualification,
    coordinate_tolerance: float,
    algebra_tolerance: float = 2.0e-10,
    support_tolerance: float = 1.0e-10,
) -> ActualPhysicalDiscreteGradientAuthority:
    """Build actual exact-sequence rules without caller qualification flags."""

    coordinate_tolerance = float(coordinate_tolerance)
    algebra_tolerance = float(algebra_tolerance)
    support_tolerance = float(support_tolerance)
    if (
        not np.isfinite(coordinate_tolerance)
        or coordinate_tolerance <= 0.0
        or not np.isfinite(algebra_tolerance)
        or algebra_tolerance <= 0.0
        or algebra_tolerance > 1.0e-8
        or not np.isfinite(support_tolerance)
        or support_tolerance <= 0.0
        or support_tolerance > algebra_tolerance
    ):
        raise ValueError(
            "actual gradient tolerances must be positive and fail-closed"
        )
    if catalog.audit.get("pass") is not True:
        raise RuntimeError("actual physical trace catalog is unqualified")
    if catalog.qualification_sha256 != qualification.qualification_sha256:
        raise RuntimeError("catalog and Piola/Riesz qualification hashes differ")

    msh = full_p6_hcurl_space.mesh
    comm = msh.comm
    metadata = (
        coordinate_tolerance,
        algebra_tolerance,
        support_tolerance,
        catalog.catalog_sha256,
        qualification.qualification_sha256,
    )
    if any(item != metadata for item in comm.allgather(metadata)):
        raise RuntimeError(
            "actual discrete-gradient metadata differs across MPI ranks"
        )
    q5_space = fem.functionspace(
        msh,
        element(
            "Q",
            msh.basix_cell(),
            5,
            lagrange_variant=basix.LagrangeVariant.gll_warped,
            dtype=default_real_type,
        ),
    )
    q6_space = fem.functionspace(
        msh,
        element(
            "Q",
            msh.basix_cell(),
            6,
            lagrange_variant=basix.LagrangeVariant.gll_warped,
            dtype=default_real_type,
        ),
    )
    _validate_spaces(
        full_p6_hcurl_space=full_p6_hcurl_space,
        q5_space=q5_space,
        q6_space=q6_space,
        qualification=qualification,
    )
    q5_records = _global_entity_dofs(
        q5_space,
        catalog=catalog,
        coordinate_tolerance=coordinate_tolerance,
        expected_dimensions=_Q5_ENTITY_DIMENSION,
    )
    q6_records = _global_entity_dofs(
        q6_space,
        catalog=catalog,
        coordinate_tolerance=coordinate_tolerance,
        expected_dimensions=_Q6_ENTITY_DIMENSION,
    )
    v6_records = _global_entity_dofs(
        full_p6_hcurl_space,
        catalog=catalog,
        coordinate_tolerance=coordinate_tolerance,
        expected_dimensions=_HCURL_P6_ENTITY_DIMENSION,
    )
    q5_coordinates = _scalar_dof_coordinates(
        q5_space,
        records=q5_records,
        coordinate_tolerance=coordinate_tolerance,
    )
    q6_coordinates = _scalar_dof_coordinates(
        q6_space,
        records=q6_records,
        coordinate_tolerance=coordinate_tolerance,
    )

    interpolation_matrix = fem.interpolation_matrix(q5_space, q6_space)
    discrete_gradient_matrix = fem.discrete_gradient(
        q6_space,
        full_p6_hcurl_space,
    )
    interpolation_identity = _distributed_matrix_identity(
        interpolation_matrix,
        comm=comm,
        label="dolfinx.fem.interpolation_matrix(Q5_GLL,Q6_GLL)",
    )
    gradient_identity = _distributed_matrix_identity(
        discrete_gradient_matrix,
        comm=comm,
        label="dolfinx.fem.discrete_gradient(Q6_GLL,N1curl_p6_legendre)",
    )
    expected_interpolation_shape = (
        int(q6_space.dofmap.index_map.size_global),
        int(q5_space.dofmap.index_map.size_global),
    )
    expected_gradient_shape = (
        int(full_p6_hcurl_space.dofmap.index_map.size_global),
        int(q6_space.dofmap.index_map.size_global),
    )
    if (
        interpolation_identity.shape != expected_interpolation_shape
        or gradient_identity.shape != expected_gradient_shape
    ):
        raise RuntimeError("actual DOLFINx matrix dimensions are inconsistent")

    interpolation_blocks = _extract_trace_blocks(
        interpolation_matrix,
        row_records=q6_records,
        column_records=q5_records,
        comm=comm,
    )
    raw_gradient_blocks = _extract_trace_blocks(
        discrete_gradient_matrix,
        row_records=v6_records,
        column_records=q6_records,
        comm=comm,
    )
    entity_shells = _scalar_entity_shells(
        catalog=catalog,
        interpolation_blocks=interpolation_blocks,
        algebra_tolerance=algebra_tolerance,
    )
    (
        scalar_pullbacks,
        scalar_relation_error,
        scalar_cycle_error,
    ) = _scalar_orbit_pullbacks(
        catalog=catalog,
        entity_shells=entity_shells,
        q5_records=q5_records,
        q6_records=q6_records,
        q5_coordinates=q5_coordinates,
        q6_coordinates=q6_coordinates,
        coordinate_tolerance=coordinate_tolerance,
        algebra_tolerance=algebra_tolerance,
    )
    (
        missing_gradient_blocks,
        riesz_decomposition_error,
        forbidden_trace_leakage,
    ) = _missing_gradient_entity_blocks(
        catalog=catalog,
        qualification=qualification,
        entity_shells=entity_shells,
        raw_gradient_blocks=raw_gradient_blocks,
        algebra_tolerance=algebra_tolerance,
    )
    hcurl_pullbacks = build_physical_p6_trace_orbit_pullbacks(
        catalog=catalog,
        basis_kind="missing",
        tolerance=algebra_tolerance,
    )
    ordered_scalar_basis_hash = _ordered_scalar_basis_sha256(
        catalog=catalog,
        interpolation_matrix_sha256=(
            interpolation_identity.matrix_sha256
        ),
        entity_shells=entity_shells,
        scalar_pullbacks=scalar_pullbacks,
    )
    orbit_evidence, rules, gradient_commuting_error = _build_orbit_evidence(
        catalog=catalog,
        entity_shells=entity_shells,
        scalar_pullbacks=scalar_pullbacks,
        hcurl_pullbacks=hcurl_pullbacks,
        missing_gradient_blocks=missing_gradient_blocks,
        ordered_scalar_basis_sha256=ordered_scalar_basis_hash,
        discrete_gradient_matrix_sha256=gradient_identity.matrix_sha256,
        scalar_pullback_cycle_error=scalar_cycle_error,
        support_tolerance=support_tolerance,
        algebra_tolerance=algebra_tolerance,
    )
    interpolation_constant_error, gradient_constant_error = (
        _constant_action_errors(
            interpolation_matrix=interpolation_matrix,
            discrete_gradient_matrix=discrete_gradient_matrix,
            comm=comm,
        )
    )
    maximum_shell_orthogonality_error = max(
        shell.scalar_shell_orthogonality_error for shell in entity_shells
    )
    maximum_error = max(
        maximum_shell_orthogonality_error,
        scalar_relation_error,
        scalar_cycle_error,
        riesz_decomposition_error,
        forbidden_trace_leakage,
        gradient_commuting_error,
        interpolation_constant_error,
        gradient_constant_error,
    )
    if maximum_error > 50.0 * algebra_tolerance:
        raise RuntimeError(
            "actual same-mesh discrete-gradient numerical audit failed: "
            f"maximum_error={maximum_error:.3e}"
        )

    checks = MappingProxyType(
        {
            "qualified_dolfinx_0_10_stack": True,
            "petsc_scalar_type_is_complex128": True,
            "petsc_int_type_is_int32": True,
            "q5_q6_are_same_mesh_conforming_GLL_spaces": True,
            "v6_is_same_mesh_N1curl_legendre": True,
            "actual_fem_interpolation_matrix_assembled": True,
            "actual_fem_discrete_gradient_assembled": True,
            "interpolation_matrix_content_hashed": True,
            "discrete_gradient_matrix_content_hashed": True,
            "edge_scalar_shell_rank_is_one": all(
                shell.scalar_shell_dimension == 1
                and shell.interpolation_rank == 4
                for shell in entity_shells
                if shell.entity_kind == "edge"
            ),
            "face_scalar_shell_rank_is_nine": all(
                shell.scalar_shell_dimension == 9
                and shell.interpolation_rank == 16
                for shell in entity_shells
                if shell.entity_kind == "face"
            ),
            "scalar_shell_is_complementary_to_Q5": (
                maximum_shell_orthogonality_error
                <= 50.0 * algebra_tolerance
            ),
            "physical_Piola_Riesz_decomposition_closes": (
                riesz_decomposition_error <= 50.0 * algebra_tolerance
            ),
            "forbidden_trace_leakage_absent": (
                forbidden_trace_leakage <= 50.0 * algebra_tolerance
            ),
            "scalar_interpolation_commutes_with_periodic_pullback": (
                scalar_relation_error <= 50.0 * algebra_tolerance
            ),
            "scalar_Floquet_pullback_cycles_close": (
                scalar_cycle_error <= 50.0 * algebra_tolerance
            ),
            "discrete_gradient_commutes_with_Hcurl_Floquet_pullback": (
                gradient_commuting_error <= 50.0 * algebra_tolerance
            ),
            "constant_Q5_interpolates_to_constant_Q6": (
                interpolation_constant_error <= 50.0 * algebra_tolerance
            ),
            "discrete_gradient_annihilates_constant_Q6": (
                gradient_constant_error <= 50.0 * algebra_tolerance
            ),
            "all_scalar_orbit_gradients_have_full_column_rank": all(
                orbit.discrete_gradient_rank == orbit.scalar_mode_count
                for orbit in orbit_evidence
            ),
            "gradient_coefficients_are_numerical_and_content_bound": True,
            "full_p6_Maxwell_matrix_not_constructed": True,
            "inactive_p6_rows_not_allocated": True,
            "ordinary_default_unchanged": True,
        }
    )
    checks = MappingProxyType(
        {name: bool(passed) for name, passed in checks.items()}
    )
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "actual physical discrete-gradient checks failed: "
            + ", ".join(failed)
        )
    authority_hash = _json_sha256(
        {
            "schema": (
                "task035b.actual-physical-discrete-gradient-authority.v1"
            ),
            "dolfinx_version": dolfinx.__version__,
            "basix_version": basix.__version__,
            "catalog_sha256": catalog.catalog_sha256,
            "trace_geometry_sha256": catalog.trace_geometry_sha256,
            "ordered_trace_basis_sha256": (
                catalog.ordered_trace_basis_sha256
            ),
            "ordered_scalar_basis_sha256": ordered_scalar_basis_hash,
            "interpolation_matrix_sha256": (
                interpolation_identity.matrix_sha256
            ),
            "discrete_gradient_matrix_sha256": (
                gradient_identity.matrix_sha256
            ),
            "rules": [
                {
                    "scalar_orbit_id": rule.scalar_orbit_id,
                    "anchor_trace_representative_id": (
                        rule.anchor_trace_representative_id
                    ),
                    "required_trace_representative_ids": (
                        rule.required_trace_representative_ids
                    ),
                    "scalar_mode_count": rule.scalar_mode_count,
                    "discrete_gradient_rank": rule.discrete_gradient_rank,
                    "gradient_map_sha256": rule.gradient_map_sha256,
                }
                for rule in rules
            ],
            "checks": dict(checks),
        }
    )
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035b.actual-physical-discrete-gradient-authority.v1"
            ),
            "status": "actual_same_mesh_discrete_gradient_authority_pass",
            "pass": True,
            "evidence_origin": (
                "internally_assembled_dolfinx_interpolation_and_gradient"
            ),
            "caller_qualification_booleans_accepted": False,
            "dolfinx_version": dolfinx.__version__,
            "basix_version": basix.__version__,
            "mpi_size": int(comm.size),
            "scalar_q5_global_dofs": expected_interpolation_shape[1],
            "scalar_q6_global_dofs": expected_interpolation_shape[0],
            "hcurl_p6_global_dofs": expected_gradient_shape[0],
            "interpolation_matrix_shape": interpolation_identity.shape,
            "interpolation_matrix_stored_nnz": (
                interpolation_identity.stored_nnz
            ),
            "interpolation_matrix_numerical_nnz": (
                interpolation_identity.numerical_nnz
            ),
            "discrete_gradient_matrix_shape": gradient_identity.shape,
            "discrete_gradient_matrix_stored_nnz": (
                gradient_identity.stored_nnz
            ),
            "discrete_gradient_matrix_numerical_nnz": (
                gradient_identity.numerical_nnz
            ),
            "physical_entity_count": len(entity_shells),
            "scalar_orbit_count": len(orbit_evidence),
            "edge_scalar_orbit_count": sum(
                orbit.entity_kind == "edge" for orbit in orbit_evidence
            ),
            "face_scalar_orbit_count": sum(
                orbit.entity_kind == "face" for orbit in orbit_evidence
            ),
            "maximum_scalar_shell_orthogonality_error": (
                maximum_shell_orthogonality_error
            ),
            "maximum_scalar_relation_commuting_error": (
                scalar_relation_error
            ),
            "maximum_scalar_pullback_cycle_error": scalar_cycle_error,
            "maximum_Piola_Riesz_decomposition_error": (
                riesz_decomposition_error
            ),
            "maximum_forbidden_trace_leakage": forbidden_trace_leakage,
            "maximum_periodic_gradient_commuting_error": (
                gradient_commuting_error
            ),
            "constant_interpolation_error": interpolation_constant_error,
            "constant_discrete_gradient_error": gradient_constant_error,
            "catalog_sha256": catalog.catalog_sha256,
            "trace_geometry_sha256": catalog.trace_geometry_sha256,
            "ordered_trace_basis_sha256": (
                catalog.ordered_trace_basis_sha256
            ),
            "ordered_scalar_basis_sha256": ordered_scalar_basis_hash,
            "interpolation_matrix_sha256": (
                interpolation_identity.matrix_sha256
            ),
            "discrete_gradient_matrix_sha256": (
                gradient_identity.matrix_sha256
            ),
            "authority_sha256": authority_hash,
            "matrix_hash_scope": (
                "current_MPI_partition_DOLFINx_global_numbering"
            ),
            "partition_independent_authority_hash_claimed": False,
            "actual_scalar_interpolation_matrix_retained_in_authority": False,
            "actual_discrete_gradient_matrix_retained_in_authority": False,
            "full_p6_Maxwell_matrix_constructed": False,
            "inactive_p6_rows_allocated": 0,
            "ordinary_default_changed": False,
            "checks": checks,
        }
    )
    authority = ActualPhysicalDiscreteGradientAuthority(
        rules=rules,
        evidence_class="actual_pde",
        catalog_sha256=catalog.catalog_sha256,
        trace_geometry_sha256=catalog.trace_geometry_sha256,
        ordered_trace_basis_sha256=catalog.ordered_trace_basis_sha256,
        ordered_scalar_basis_sha256=ordered_scalar_basis_hash,
        actual_scalar_space_on_same_mesh=True,
        actual_discrete_gradient_coefficients=True,
        actual_periodic_floquet_pullback=True,
        dolfinx_version=dolfinx.__version__,
        basix_version=basix.__version__,
        petsc_scalar_type=np.dtype(PETSc.ScalarType).name,
        petsc_int_type=np.dtype(PETSc.IntType).name,
        scalar_q5_global_dofs=expected_interpolation_shape[1],
        scalar_q6_global_dofs=expected_interpolation_shape[0],
        hcurl_p6_global_dofs=expected_gradient_shape[0],
        interpolation_matrix_sha256=(
            interpolation_identity.matrix_sha256
        ),
        discrete_gradient_matrix_sha256=(
            gradient_identity.matrix_sha256
        ),
        entity_shells=entity_shells,
        orbit_evidence=orbit_evidence,
        authority_sha256=authority_hash,
        audit=audit,
    )
    if any(
        value != authority.authority_sha256
        for value in comm.allgather(authority.authority_sha256)
    ):
        raise RuntimeError(
            "actual discrete-gradient authority hash differs across ranks"
        )
    return authority


__all__ = [
    "ActualPhysicalDiscreteGradientAuthority",
    "ActualScalarEntityShell",
    "ActualScalarGradientOrbit",
    "build_actual_physical_discrete_gradient_authority",
]
