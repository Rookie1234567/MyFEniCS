"""Reference-cell authority for exact-sequence hexahedral variable-p spaces.

The Task035d active space is represented inside one degree-six reference
container, but only the active edge, face, and cell coefficients are globally
numbered.  A local expansion maps those active coefficients to the p6
reference basis.  This module constructs that expansion from Basix
interpolation moments; it never assumes that a lower-order basis is a prefix
of the p6 coefficient array.

The admissible degree rule is the tensor-product de Rham closure

``edge degree <= incident face degree <= cell degree``.

The paired scalar space uses Q1 vertex extensions and the same entity degrees
on edges, faces, and the cell.  For a uniform degree the ordinary Basix
elements are reused exactly.  Mixed layouts are represented by custom Basix
elements whose entity moments come from the requested source degrees and whose
polynomial span is embedded in the p6 container.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
from typing import Any, Literal

import basix
import basix.ufl
import numpy as np
from scipy.linalg import qr


QualifiedDegree = Literal[4, 5, 6]
_QUALIFIED_DEGREES = (4, 5, 6)
_HCURL_FAMILY = "hcurl"
_H1_FAMILY = "h1"
_FAMILIES = (_HCURL_FAMILY, _H1_FAMILY)


class ExactSequenceDegreeError(ValueError):
    """An entity-degree layout is not closed under the discrete gradient."""


def _hexahedron_topology() -> list[list[list[int]]]:
    return basix.topology(basix.CellType.hexahedron)


@lru_cache(maxsize=1)
def _face_edge_incidence() -> tuple[tuple[int, ...], ...]:
    topology = _hexahedron_topology()
    edge_vertices = [set(map(int, vertices)) for vertices in topology[1]]
    result: list[tuple[int, ...]] = []
    for face_vertices_raw in topology[2]:
        face_vertices = set(map(int, face_vertices_raw))
        result.append(
            tuple(
                edge
                for edge, vertices in enumerate(edge_vertices)
                if vertices.issubset(face_vertices)
            )
        )
    if len(result) != 6 or any(len(edges) != 4 for edges in result):
        raise RuntimeError("Basix returned an unexpected hexahedron topology")
    return tuple(result)


@dataclass(frozen=True)
class HexaEntityDegreeMap:
    """Degrees attached to the twelve edges, six faces, and one cell."""

    edges: tuple[int, ...]
    faces: tuple[int, ...]
    cell: int

    def __post_init__(self) -> None:
        edges = tuple(map(int, self.edges))
        faces = tuple(map(int, self.faces))
        cell = int(self.cell)
        if len(edges) != 12:
            raise ValueError("a hexahedron degree map requires twelve edges")
        if len(faces) != 6:
            raise ValueError("a hexahedron degree map requires six faces")
        invalid = [
            degree
            for degree in (*edges, *faces, cell)
            if degree not in _QUALIFIED_DEGREES
        ]
        if invalid:
            raise ValueError(
                "Task035d qualifies only p4/p5/p6 entity degrees; "
                f"observed={sorted(set(invalid))}"
            )
        violations: list[str] = []
        for face, incident_edges in enumerate(_face_edge_incidence()):
            maximum_edge = max(edges[edge] for edge in incident_edges)
            if faces[face] < maximum_edge:
                violations.append(
                    f"face {face} p{faces[face]} < incident edge p{maximum_edge}"
                )
        maximum_face = max(faces)
        if cell < maximum_face:
            violations.append(f"cell p{cell} < incident face p{maximum_face}")
        if violations:
            raise ExactSequenceDegreeError(
                "entity degrees are not exact-sequence closed: "
                + "; ".join(violations)
            )
        object.__setattr__(self, "edges", edges)
        object.__setattr__(self, "faces", faces)
        object.__setattr__(self, "cell", cell)

    @classmethod
    def uniform(cls, degree: int) -> HexaEntityDegreeMap:
        """Return the ordinary uniform-p layout."""

        value = int(degree)
        return cls(edges=(value,) * 12, faces=(value,) * 6, cell=value)

    @classmethod
    def dimension_uniform(
        cls,
        *,
        edge_degree: int,
        face_degree: int,
        cell_degree: int,
    ) -> HexaEntityDegreeMap:
        """Return one degree on every entity of each topological dimension."""

        return cls(
            edges=(int(edge_degree),) * 12,
            faces=(int(face_degree),) * 6,
            cell=int(cell_degree),
        )

    @property
    def uniform_degree(self) -> int | None:
        values = set((*self.edges, *self.faces, self.cell))
        return values.pop() if len(values) == 1 else None

    @property
    def signature(self) -> str:
        edge_text = ",".join(map(str, self.edges))
        face_text = ",".join(map(str, self.faces))
        return f"e[{edge_text}]-f[{face_text}]-c[{self.cell}]"

    def entity_degrees(self, family: str) -> tuple[tuple[int, ...], ...]:
        """Return the source degree associated with every reference entity."""

        if family == _HCURL_FAMILY:
            vertex_degrees = (min(self.edges),) * 8
        elif family == _H1_FAMILY:
            # Q1 vertex extensions keep the scalar trace continuous without
            # coupling the vertex shape to one arbitrary adjacent edge order.
            vertex_degrees = (1,) * 8
        else:
            raise ValueError(f"unsupported exact-sequence family {family!r}")
        return (
            vertex_degrees,
            self.edges,
            self.faces,
            (self.cell,),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "edges": list(self.edges),
            "faces": list(self.faces),
            "cell": self.cell,
            "signature": self.signature,
            "uniform_degree": self.uniform_degree,
            "exact_sequence_monotone": True,
        }


@dataclass(frozen=True)
class VariablePReferenceSpace:
    """One active H(curl)/H1 pair and its degree-six expansions."""

    degree_map: HexaEntityDegreeMap
    hcurl_element: basix.finite_element.FiniteElement
    h1_element: basix.finite_element.FiniteElement
    hcurl_to_p6: np.ndarray
    h1_to_q6: np.ndarray
    discrete_gradient: np.ndarray
    trace_dofs: np.ndarray
    interior_dofs: np.ndarray
    audit: dict[str, Any]

    @property
    def hcurl_dimension(self) -> int:
        return int(self.hcurl_element.dim)

    @property
    def h1_dimension(self) -> int:
        return int(self.h1_element.dim)

    def expand_hcurl_coefficients(self, active: np.ndarray) -> np.ndarray:
        """Recover coefficients in the p6 reference container."""

        values = np.asarray(active)
        if values.shape[0] != self.hcurl_dimension:
            raise ValueError(
                "active H(curl) coefficient dimension does not match the "
                "reference space"
            )
        return np.asarray(self.hcurl_to_p6 @ values)

    def apply_hcurl_dof_transform(
        self,
        values: np.ndarray,
        *,
        cell_info: int,
        transpose: bool = False,
    ) -> np.ndarray:
        """Apply the explicit per-entity Basix transform to active data."""

        return apply_active_dof_transformation(
            self,
            values,
            family=_HCURL_FAMILY,
            cell_info=cell_info,
            transpose=transpose,
        )

    def orient_hcurl_tensor(
        self,
        tensor: np.ndarray,
        *,
        cell_info: int,
    ) -> np.ndarray:
        """Apply the DOLFINx ``T A T^T`` convention to one active tensor."""

        values = np.asarray(tensor)
        expected = (self.hcurl_dimension, self.hcurl_dimension)
        if values.shape != expected:
            raise ValueError(
                f"active tensor shape {values.shape} does not match {expected}"
            )
        oriented = self.apply_hcurl_dof_transform(
            values,
            cell_info=cell_info,
        )
        transposed = self.apply_hcurl_dof_transform(
            np.ascontiguousarray(oriented.T),
            cell_info=cell_info,
        )
        return np.ascontiguousarray(transposed.T)

    def active_to_p6_oriented(
        self,
        active_coefficients: np.ndarray,
        *,
        cell_info: int,
    ) -> np.ndarray:
        """Map oriented active coefficients to oriented p6 coefficients."""

        active = np.asarray(active_coefficients)
        if active.shape != (self.hcurl_dimension,):
            raise ValueError("active local coefficient vector has wrong size")
        active_reference = self.apply_hcurl_dof_transform(
            active,
            cell_info=cell_info,
            transpose=True,
        )
        p6_reference = np.ascontiguousarray(
            self.hcurl_to_p6 @ active_reference
        )
        p6_space = build_variable_p_reference_space(
            HexaEntityDegreeMap.uniform(6)
        )
        return apply_active_dof_transformation(
            p6_space,
            p6_reference,
            family=_HCURL_FAMILY,
            cell_info=cell_info,
        )

    def project_p6_oriented_dual(
        self,
        p6_dual: np.ndarray,
        *,
        cell_info: int,
    ) -> np.ndarray:
        """Apply the Hermitian transpose of the oriented local expansion."""

        values = np.asarray(p6_dual)
        expected = (self.hcurl_to_p6.shape[0],)
        if values.shape != expected:
            raise ValueError("p6 local dual vector has wrong size")
        p6_space = build_variable_p_reference_space(
            HexaEntityDegreeMap.uniform(6)
        )
        p6_reference_dual = apply_active_dof_transformation(
            p6_space,
            values,
            family=_HCURL_FAMILY,
            cell_info=cell_info,
            transpose=True,
        )
        active_reference_dual = np.ascontiguousarray(
            self.hcurl_to_p6.conj().T @ p6_reference_dual
        )
        return self.apply_hcurl_dof_transform(
            active_reference_dual,
            cell_info=cell_info,
        )


def allowed_dimension_degree_triples() -> tuple[tuple[int, int, int], ...]:
    """Return all p4/p5/p6 dimension-uniform exact-sequence layouts."""

    return tuple(
        (edge, face, cell)
        for edge in _QUALIFIED_DEGREES
        for face in _QUALIFIED_DEGREES
        for cell in _QUALIFIED_DEGREES
        if edge <= face <= cell
    )


@lru_cache(maxsize=12)
def _standard_element(
    family: str,
    degree: int,
) -> basix.finite_element.FiniteElement:
    degree = int(degree)
    if family == _HCURL_FAMILY:
        return basix.ufl.element(
            "N1curl",
            "hexahedron",
            degree,
        ).basix_element
    if family == _H1_FAMILY:
        return basix.ufl.element(
            "Lagrange",
            "hexahedron",
            degree,
            lagrange_variant=basix.LagrangeVariant.gll_warped,
        ).basix_element
    raise ValueError(f"unsupported exact-sequence family {family!r}")


@lru_cache(maxsize=12)
def _to_p6_interpolation(family: str, degree: int) -> np.ndarray:
    source = _standard_element(family, int(degree))
    target = _standard_element(family, 6)
    if int(degree) == 6:
        result = np.eye(int(target.dim), dtype=np.float64)
    else:
        result = np.asarray(
            basix.compute_interpolation_operator(source, target),
            dtype=np.float64,
        )
    result.setflags(write=False)
    return result


@lru_cache(maxsize=12)
def _embedded_basis_coefficients(family: str, degree: int) -> np.ndarray:
    target = _standard_element(family, 6)
    values = (
        _to_p6_interpolation(family, int(degree)).T
        @ np.asarray(target.coefficient_matrix)
    )
    values = np.ascontiguousarray(values)
    values.setflags(write=False)
    return values


def _entity_dofs_flat(
    element: basix.finite_element.FiniteElement,
    dimensions: range,
) -> np.ndarray:
    result = np.asarray(
        [
            int(dof)
            for dimension in dimensions
            for entity in element.entity_dofs[dimension]
            for dof in entity
        ],
        dtype=np.int32,
    )
    result.setflags(write=False)
    return result


def _matrix_sha256(matrix: np.ndarray) -> str:
    values = np.ascontiguousarray(matrix)
    return hashlib.sha256(values.tobytes()).hexdigest()


def _numerical_rank(matrix: np.ndarray) -> tuple[int, float]:
    values = np.asarray(matrix)
    if min(values.shape, default=0) == 0:
        return 0, 0.0
    _orthogonal, upper, _pivots = qr(
        values,
        mode="economic",
        pivoting=True,
        check_finite=False,
    )
    diagonal = np.abs(np.diag(upper))
    tolerance = (
        0.0
        if len(diagonal) == 0
        else float(
            diagonal[0]
            * max(values.shape)
            * np.finfo(np.float64).eps
        )
    )
    return int(np.count_nonzero(diagonal > tolerance)), tolerance


def _active_dimension(family: str, degree_map: HexaEntityDegreeMap) -> int:
    count = 0
    for dimension, degrees in enumerate(
        degree_map.entity_degrees(family)
    ):
        for entity, degree in enumerate(degrees):
            count += len(
                _standard_element(family, degree).entity_dofs[dimension][
                    entity
                ]
            )
    return int(count)


@lru_cache(maxsize=32)
def _create_active_element(
    family: str,
    degree_map: HexaEntityDegreeMap,
) -> tuple[basix.finite_element.FiniteElement, np.ndarray, dict[str, Any]]:
    if family not in _FAMILIES:
        raise ValueError(f"unsupported exact-sequence family {family!r}")
    uniform_degree = degree_map.uniform_degree
    target = _standard_element(family, 6)
    if uniform_degree is not None:
        element = _standard_element(family, uniform_degree)
        expansion = _to_p6_interpolation(family, uniform_degree)
        return (
            element,
            expansion,
            {
                "custom": False,
                "construction": "ordinary_uniform_basix_element",
                "uniform_degree": uniform_degree,
                "polynomial_subspace_rank": int(element.dim),
            },
        )

    source_degrees = degree_map.entity_degrees(family)
    nodal_rows: list[np.ndarray] = []
    interpolation_points: list[list[np.ndarray]] = []
    interpolation_matrices: list[list[np.ndarray]] = []
    selected_degrees: set[int] = set()
    for dimension, degrees in enumerate(source_degrees):
        dimension_points: list[np.ndarray] = []
        dimension_matrices: list[np.ndarray] = []
        for entity, degree in enumerate(degrees):
            source = _standard_element(family, degree)
            selected_degrees.add(int(degree))
            dofs = np.asarray(
                source.entity_dofs[dimension][entity],
                dtype=np.int32,
            )
            if len(dofs):
                nodal_rows.append(
                    _embedded_basis_coefficients(family, degree)[dofs]
                )
            dimension_points.append(
                np.asarray(source.x[dimension][entity]).copy()
            )
            dimension_matrices.append(
                np.asarray(source.M[dimension][entity]).copy()
            )
        interpolation_points.append(dimension_points)
        interpolation_matrices.append(dimension_matrices)

    nodal_coefficients = np.ascontiguousarray(np.vstack(nodal_rows))
    expected_dimension = _active_dimension(family, degree_map)
    if nodal_coefficients.shape[0] != expected_dimension:
        raise RuntimeError("active entity moments have the wrong dimension")
    rank, rank_tolerance = _numerical_rank(nodal_coefficients)
    if rank != expected_dimension:
        raise RuntimeError(
            "active entity polynomial span is rank deficient: "
            f"rank={rank}, expected={expected_dimension}"
        )
    orthogonal_columns, _upper = np.linalg.qr(
        nodal_coefficients.T,
        mode="reduced",
    )
    source_elements = [
        _standard_element(family, degree)
        for degree in sorted(selected_degrees)
    ]
    custom = basix.create_custom_element(
        basix.CellType.hexahedron,
        tuple(target.value_shape),
        np.ascontiguousarray(orthogonal_columns.T),
        interpolation_points,
        interpolation_matrices,
        int(target.interpolation_nderivs),
        target.map_type,
        target.sobolev_space,
        False,
        min(element.embedded_subdegree for element in source_elements),
        int(target.embedded_superdegree),
        target.polyset_type,
    )
    if int(custom.dim) != expected_dimension:
        raise RuntimeError("custom active element dimension does not close")
    expansion = np.asarray(
        basix.compute_interpolation_operator(custom, target),
        dtype=np.float64,
    )
    expansion_rank, expansion_tolerance = _numerical_rank(expansion)
    if expansion_rank != expected_dimension:
        raise RuntimeError("active-to-p6 expansion is rank deficient")
    expansion = np.ascontiguousarray(expansion)
    expansion.setflags(write=False)
    return (
        custom,
        expansion,
        {
            "custom": True,
            "construction": (
                "entity_moments_plus_orthogonal_p6_polynomial_span"
            ),
            "uniform_degree": None,
            "polynomial_subspace_rank": rank,
            "polynomial_subspace_rank_tolerance": rank_tolerance,
            "expansion_rank": expansion_rank,
            "expansion_rank_tolerance": expansion_tolerance,
            "selected_source_degrees": sorted(selected_degrees),
        },
    )


def _discrete_gradient(
    scalar_element: basix.finite_element.FiniteElement,
    hcurl_element: basix.finite_element.FiniteElement,
) -> np.ndarray:
    points = np.asarray(hcurl_element.points)
    scalar_table = np.asarray(scalar_element.tabulate(1, points))
    if scalar_table.shape[:2] != (4, len(points)):
        raise RuntimeError(
            "unexpected scalar derivative tabulation for the hexahedron"
        )
    gradient_values = np.stack(
        (
            scalar_table[1, :, :, 0],
            scalar_table[2, :, :, 0],
            scalar_table[3, :, :, 0],
        ),
        axis=2,
    )
    flattened = np.ascontiguousarray(
        gradient_values.transpose(2, 0, 1)
    ).reshape(
        3 * len(points),
        int(scalar_element.dim),
    )
    result = np.asarray(hcurl_element.interpolation_matrix) @ flattened
    return np.ascontiguousarray(result)


@lru_cache(maxsize=1)
def _p6_discrete_gradient() -> np.ndarray:
    result = _discrete_gradient(
        _standard_element(_H1_FAMILY, 6),
        _standard_element(_HCURL_FAMILY, 6),
    )
    result.setflags(write=False)
    return result


def _curl_sampling_matrix(
    element: basix.finite_element.FiniteElement,
) -> np.ndarray:
    points_per_axis = max(int(element.embedded_superdegree) + 1, 7)
    axis = (
        np.polynomial.legendre.leggauss(points_per_axis)[0] + 1.0
    ) / 2.0
    points = np.asarray(
        [(x, y, z) for x in axis for y in axis for z in axis],
        dtype=np.float64,
    )
    table = np.asarray(element.tabulate(1, points))
    derivative_x = table[1]
    derivative_y = table[2]
    derivative_z = table[3]
    curl = np.stack(
        (
            derivative_y[:, :, 2] - derivative_z[:, :, 1],
            derivative_z[:, :, 0] - derivative_x[:, :, 2],
            derivative_x[:, :, 1] - derivative_y[:, :, 0],
        ),
        axis=2,
    )
    return np.ascontiguousarray(
        curl.transpose(0, 2, 1).reshape(-1, int(element.dim))
    )


def _orientation_audit(
    element: basix.finite_element.FiniteElement,
    *,
    family: str | None = None,
    degree_map: HexaEntityDegreeMap | None = None,
) -> dict[str, Any]:
    expected_count = 12 + 2 * 6
    explicit_per_entity = degree_map is not None
    if explicit_per_entity and family not in _FAMILIES:
        raise ValueError(
            "an explicit orientation audit requires an element family"
        )
    transformations = (
        None
        if explicit_per_entity
        else np.asarray(element.base_transformations())
    )
    if transformations is not None and transformations.shape != (
        expected_count,
        int(element.dim),
        int(element.dim),
    ):
        raise RuntimeError(
            "Basix returned an unexpected hexahedron transformation catalog"
        )
    custom_basix_comparable = bool(
        explicit_per_entity
        and len(set(degree_map.edges)) == 1
        and len(set(degree_map.faces)) == 1
    )
    custom_transformations = (
        np.asarray(element.base_transformations())
        if custom_basix_comparable
        else None
    )
    entries: list[dict[str, Any]] = []
    max_outside_block = 0.0
    max_condition = 0.0
    max_custom_basix_error = 0.0
    for index in range(expected_count):
        if index < 12:
            dimension = 1
            entity = index
            generator = "edge_reflection"
            generator_index = 0
            entity_type = "interval"
        else:
            dimension = 2
            entity = (index - 12) // 2
            generator = (
                "face_rotation" if (index - 12) % 2 == 0 else "face_reflection"
            )
            generator_index = (index - 12) % 2
            entity_type = "quadrilateral"
        entity_dofs = np.asarray(
            element.entity_dofs[dimension][entity],
            dtype=np.int32,
        )
        if explicit_per_entity:
            degree = degree_map.entity_degrees(family)[dimension][entity]
            source = _standard_element(family, degree)
            block = np.asarray(
                source.entity_transformations()[entity_type][
                    generator_index
                ],
            )
            outside_error = 0.0
            if block.shape != (len(entity_dofs), len(entity_dofs)):
                raise RuntimeError(
                    "per-entity Basix transformation dimension does not "
                    "match the active entity"
                )
            if custom_transformations is not None:
                observed = custom_transformations[index][
                    np.ix_(entity_dofs, entity_dofs)
                ]
                custom_basix_error = float(
                    np.max(np.abs(observed - block), initial=0.0)
                )
                max_custom_basix_error = max(
                    max_custom_basix_error,
                    custom_basix_error,
                )
            else:
                custom_basix_error = None
        else:
            transformation = transformations[index]
            identity = np.eye(int(element.dim))
            delta = np.asarray(transformation) - identity
            outside = np.ones(int(element.dim), dtype=bool)
            outside[entity_dofs] = False
            outside_error = float(
                max(
                    np.max(np.abs(delta[outside, :]), initial=0.0),
                    np.max(np.abs(delta[:, outside]), initial=0.0),
                )
            )
            block = np.asarray(
                transformation[np.ix_(entity_dofs, entity_dofs)]
            )
            custom_basix_error = 0.0
        block_rank, block_tolerance = _numerical_rank(block)
        condition = float(np.linalg.cond(block))
        max_outside_block = max(max_outside_block, outside_error)
        max_condition = max(max_condition, condition)
        entries.append(
            {
                "index": index,
                "dimension": dimension,
                "entity": entity,
                "generator": generator,
                "block_shape": list(block.shape),
                "block_rank": block_rank,
                "block_rank_tolerance": block_tolerance,
                "block_condition_number": condition,
                "block_sha256": _matrix_sha256(block),
                "outside_entity_block_error_max": outside_error,
                "source_degree": (
                    int(degree) if explicit_per_entity else None
                ),
                "custom_basix_comparison_error_max": custom_basix_error,
            }
        )
    passed = (
        max_outside_block <= 5.0e-12
        and max_condition <= 1.0 + 5.0e-11
        and (
            not custom_basix_comparable
            or max_custom_basix_error <= 5.0e-12
        )
        and all(
            entry["block_rank"] == entry["block_shape"][0]
            for entry in entries
        )
    )
    return {
        "status": (
            "basix_entity_orientation_pass"
            if passed
            else "basix_entity_orientation_fail"
        ),
        "pass": passed,
        "generator_count": len(entries),
        "max_outside_entity_block_error": max_outside_block,
        "max_entity_transform_condition_number": max_condition,
        "transformation_source": (
            "per_entity_standard_basix_degree"
            if explicit_per_entity
            else "element_base_transformations"
        ),
        "heterogeneous_custom_basix_T_apply_used": False,
        "custom_basix_uniform_entity_comparison_executed": (
            custom_basix_comparable
        ),
        "custom_basix_uniform_entity_comparison_error_max": (
            max_custom_basix_error
            if custom_basix_comparable
            else None
        ),
        "generators": entries,
    }


def _active_element(
    space: VariablePReferenceSpace,
    family: str,
) -> basix.finite_element.FiniteElement:
    if family == _HCURL_FAMILY:
        return space.hcurl_element
    if family == _H1_FAMILY:
        return space.h1_element
    raise ValueError(f"unsupported exact-sequence family {family!r}")


def apply_active_dof_transformation(
    space: VariablePReferenceSpace,
    values: np.ndarray,
    *,
    family: str,
    cell_info: int,
    transpose: bool = False,
) -> np.ndarray:
    """Apply Basix transforms with each entity's own active degree.

    Basix custom elements assume that all entities of one cell type expose the
    same transformation block.  A true variable-p cell does not satisfy that
    assumption.  This routine follows Basix's documented bit ordering but
    takes the edge/face block from the standard element at that entity's
    degree.  It is therefore safe for heterogeneous layouts and deliberately
    does not call the custom element's ``T_apply`` in that case.
    """

    element = _active_element(space, family)
    data = np.asarray(values)
    if data.ndim == 0 or data.shape[0] != int(element.dim):
        raise ValueError(
            "active transformation data must have one leading entry per DoF"
        )
    transformed = np.ascontiguousarray(data.copy())
    flattened = transformed.reshape(int(element.dim), -1)
    info = int(cell_info)
    if info < 0 or info >= 2**30:
        raise ValueError("hexahedron cell permutation info is invalid")
    face_start = 3 * 6
    degrees = space.degree_map.entity_degrees(family)

    for edge in range(12):
        dofs = np.asarray(
            element.entity_dofs[1][edge],
            dtype=np.int32,
        )
        if len(dofs) and ((info >> (face_start + edge)) & 1):
            degree = degrees[1][edge]
            reflection = np.asarray(
                _standard_element(
                    family,
                    degree,
                ).entity_transformations()["interval"][0]
            )
            flattened[dofs] = (
                reflection.T if transpose else reflection
            ) @ flattened[dofs]

    for face in range(6):
        dofs = np.asarray(
            element.entity_dofs[2][face],
            dtype=np.int32,
        )
        if not len(dofs):
            continue
        degree = degrees[2][face]
        generators = np.asarray(
            _standard_element(
                family,
                degree,
            ).entity_transformations()["quadrilateral"]
        )
        rotations = (info >> (3 * face + 1)) & 3
        if transpose:
            for _ in range(rotations):
                flattened[dofs] = generators[0].T @ flattened[dofs]
            if (info >> (3 * face)) & 1:
                flattened[dofs] = generators[1].T @ flattened[dofs]
        else:
            if (info >> (3 * face)) & 1:
                flattened[dofs] = generators[1] @ flattened[dofs]
            for _ in range(rotations):
                flattened[dofs] = generators[0] @ flattened[dofs]
    return transformed


def _embedding_audit(
    family: str,
    degree: int,
) -> dict[str, Any]:
    source = _standard_element(family, degree)
    target = _standard_element(family, 6)
    expansion = _to_p6_interpolation(family, degree)
    rank, tolerance = _numerical_rank(expansion)
    naive_prefix = np.zeros_like(expansion)
    naive_prefix[: int(source.dim), :] = np.eye(int(source.dim))
    entity_stats: list[dict[str, Any]] = []
    for dimension in range(4):
        for entity, dofs_raw in enumerate(source.entity_dofs[dimension]):
            dofs = np.asarray(dofs_raw, dtype=np.int32)
            if not len(dofs):
                continue
            block = np.asarray(expansion[:, dofs])
            block_rank, block_tolerance = _numerical_rank(block)
            entity_stats.append(
                {
                    "dimension": dimension,
                    "entity": entity,
                    "source_mode_count": len(dofs),
                    "rank": block_rank,
                    "rank_tolerance": block_tolerance,
                    "condition_number": float(np.linalg.cond(block)),
                    "sha256": _matrix_sha256(block),
                }
            )
    return {
        "family": family,
        "source_degree": int(degree),
        "target_degree": 6,
        "shape": list(expansion.shape),
        "rank": rank,
        "rank_tolerance": tolerance,
        "condition_number": float(np.linalg.cond(expansion)),
        "sha256": _matrix_sha256(expansion),
        "naive_prefix_error_max": float(
            np.max(np.abs(expansion - naive_prefix), initial=0.0)
        ),
        "constructed_by": "basix.compute_interpolation_operator",
        "prefix_assumption_used": False,
        "source_dimension": int(source.dim),
        "target_dimension": int(target.dim),
        "entity_subspaces": entity_stats,
    }


@lru_cache(maxsize=1)
def build_p4_p6_entity_dof_catalog() -> dict[str, Any]:
    """Build the normalized p4/p5/p6 entity and embedding authority."""

    degrees: list[dict[str, Any]] = []
    for degree in _QUALIFIED_DEGREES:
        hcurl = _standard_element(_HCURL_FAMILY, degree)
        h1 = _standard_element(_H1_FAMILY, degree)
        degrees.append(
            {
                "degree": degree,
                "hcurl_dimension": int(hcurl.dim),
                "h1_dimension": int(h1.dim),
                "hcurl_entity_dofs": [
                    [len(entity) for entity in dimension]
                    for dimension in hcurl.entity_dofs
                ],
                "h1_entity_dofs": [
                    [len(entity) for entity in dimension]
                    for dimension in h1.entity_dofs
                ],
                "hcurl_orientation": _orientation_audit(hcurl),
                "h1_orientation": _orientation_audit(h1),
                "hcurl_to_p6": _embedding_audit(
                    _HCURL_FAMILY,
                    degree,
                ),
                "h1_to_q6": _embedding_audit(_H1_FAMILY, degree),
            }
        )
    passed = all(
        item["hcurl_orientation"]["pass"]
        and item["h1_orientation"]["pass"]
        and item["hcurl_to_p6"]["rank"]
        == item["hcurl_dimension"]
        and item["h1_to_q6"]["rank"] == item["h1_dimension"]
        for item in degrees
    )
    return {
        "schema_version": "task035d.reference-entity-dof-catalog.v1",
        "status": (
            "reference_entity_dof_catalog_pass"
            if passed
            else "reference_entity_dof_catalog_fail"
        ),
        "pass": passed,
        "cell_type": "hexahedron",
        "qualified_degrees": list(_QUALIFIED_DEGREES),
        "basix_version": str(basix.__version__),
        "degrees": degrees,
        "allowed_dimension_degree_triples": [
            list(values) for values in allowed_dimension_degree_triples()
        ],
        "exact_sequence_degree_rule": (
            "edge_degree <= each_incident_face_degree <= cell_degree"
        ),
        "ordinary_default_changed": False,
    }


@lru_cache(maxsize=32)
def build_variable_p_reference_space(
    degree_map: HexaEntityDegreeMap,
) -> VariablePReferenceSpace:
    """Construct and audit one active H(curl)/H1 reference pair."""

    hcurl, hcurl_to_p6, hcurl_build = _create_active_element(
        _HCURL_FAMILY,
        degree_map,
    )
    h1, h1_to_q6, h1_build = _create_active_element(
        _H1_FAMILY,
        degree_map,
    )
    discrete_gradient = _discrete_gradient(h1, hcurl)
    gradient_rank, gradient_tolerance = _numerical_rank(discrete_gradient)
    curl_matrix = _curl_sampling_matrix(hcurl)
    curl_rank, curl_rank_tolerance = _numerical_rank(curl_matrix)
    curl_nullity = int(hcurl.dim) - curl_rank
    expected_gradient_rank = int(h1.dim) - 1
    expanded_gradient = np.asarray(hcurl_to_p6) @ discrete_gradient
    p6_gradient = _p6_discrete_gradient() @ np.asarray(h1_to_q6)
    gradient_embedding_error = expanded_gradient - p6_gradient
    curl_gradient = curl_matrix @ discrete_gradient
    constant_error = float(
        np.max(
            np.abs(
                discrete_gradient
                @ np.ones(int(h1.dim), dtype=np.float64)
            ),
            initial=0.0,
        )
    )
    hcurl_orientation = _orientation_audit(
        hcurl,
        family=_HCURL_FAMILY,
        degree_map=degree_map,
    )
    h1_orientation = _orientation_audit(
        h1,
        family=_H1_FAMILY,
        degree_map=degree_map,
    )
    range_error_max = float(
        np.max(np.abs(gradient_embedding_error), initial=0.0)
    )
    curl_gradient_error_max = float(
        np.max(np.abs(curl_gradient), initial=0.0)
    )
    checks = {
        "hcurl_dimension_matches_entity_count": (
            int(hcurl.dim) == _active_dimension(_HCURL_FAMILY, degree_map)
        ),
        "h1_dimension_matches_entity_count": (
            int(h1.dim) == _active_dimension(_H1_FAMILY, degree_map)
        ),
        "gradient_has_constant_nullspace_only": (
            gradient_rank == expected_gradient_rank
        ),
        "curl_nullity_matches_gradient_rank": (
            curl_nullity == expected_gradient_rank
        ),
        "gradient_embedding_commutes_with_p6": (
            range_error_max <= 5.0e-11
        ),
        "curl_grad_zero": curl_gradient_error_max <= 2.0e-10,
        "constant_gradient_zero": constant_error <= 5.0e-11,
        "hcurl_orientation": hcurl_orientation["pass"],
        "h1_orientation": h1_orientation["pass"],
    }
    passed = all(checks.values())
    if not passed:
        failed = [name for name, value in checks.items() if not value]
        raise RuntimeError(
            "variable-p exact-sequence reference audit failed: "
            + ", ".join(failed)
        )
    trace_dofs = _entity_dofs_flat(hcurl, range(3))
    interior_dofs = _entity_dofs_flat(hcurl, range(3, 4))
    for array in (
        hcurl_to_p6,
        h1_to_q6,
        discrete_gradient,
        trace_dofs,
        interior_dofs,
    ):
        array.setflags(write=False)
    audit = {
        "schema_version": "task035d.variable-p-reference-space.v1",
        "status": "variable_p_exact_sequence_reference_pass",
        "pass": True,
        "degree_map": degree_map.to_dict(),
        "hcurl_dimension": int(hcurl.dim),
        "h1_dimension": int(h1.dim),
        "p6_hcurl_dimension": int(
            _standard_element(_HCURL_FAMILY, 6).dim
        ),
        "q6_h1_dimension": int(_standard_element(_H1_FAMILY, 6).dim),
        "active_trace_dimension": len(trace_dofs),
        "active_cell_interior_dimension": len(interior_dofs),
        "inactive_p6_local_modes": int(
            _standard_element(_HCURL_FAMILY, 6).dim - int(hcurl.dim)
        ),
        "hcurl_construction": hcurl_build,
        "h1_construction": h1_build,
        "hcurl_expansion_sha256": _matrix_sha256(hcurl_to_p6),
        "h1_expansion_sha256": _matrix_sha256(h1_to_q6),
        "discrete_gradient_sha256": _matrix_sha256(discrete_gradient),
        "gradient_rank": gradient_rank,
        "gradient_rank_tolerance": gradient_tolerance,
        "expected_nonconstant_gradient_dimension": expected_gradient_rank,
        "sampled_curl_rank": curl_rank,
        "sampled_curl_rank_tolerance": curl_rank_tolerance,
        "sampled_curl_nullity": curl_nullity,
        "gradient_embedding_error_max": range_error_max,
        "curl_gradient_error_max": curl_gradient_error_max,
        "constant_gradient_error_max": constant_error,
        "hcurl_orientation": hcurl_orientation,
        "h1_orientation": h1_orientation,
        "checks": checks,
        "inactive_modes_globally_numbered": False,
        "full_p6_global_matrix_constructed": False,
        "ordinary_default_changed": False,
    }
    return VariablePReferenceSpace(
        degree_map=degree_map,
        hcurl_element=hcurl,
        h1_element=h1,
        hcurl_to_p6=hcurl_to_p6,
        h1_to_q6=h1_to_q6,
        discrete_gradient=discrete_gradient,
        trace_dofs=trace_dofs,
        interior_dofs=interior_dofs,
        audit=audit,
    )


__all__ = [
    "ExactSequenceDegreeError",
    "HexaEntityDegreeMap",
    "VariablePReferenceSpace",
    "apply_active_dof_transformation",
    "allowed_dimension_degree_triples",
    "build_p4_p6_entity_dof_catalog",
    "build_variable_p_reference_space",
]
