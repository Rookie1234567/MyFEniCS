"""Selective p7 trace-complement shadow algebra for Task035e.

The production degree set remains p4/p5/p6.  This module supplies only a
cell-local p7 shadow: selected p6 edge or face entities receive their complete
p7 coefficient complement, and exact-sequence closure also includes all
required incident faces and the p7 cell-interior complement.  Unselected p7
modes never receive an active column.

The periodic-orbit API closes caller-supplied physical edge/face relations and
checks the p7 complement transforms, but it does not claim binding to a real
multilevel mesh or MPI8 partition.  Consequently its aggregate evidence is
always coverage-incomplete and can never be a measured saturation pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from types import MappingProxyType
from typing import Any, Iterable, Mapping

import basix
import basix.ufl
import numpy as np
from scipy.linalg import qr, solve_triangular

from src.constraints.high_order_floquet_trace import (
    quadrilateral_d4_vertex_permutations,
)


_P6 = 6
_P7 = 7
_HCURL = "hcurl"
_H1 = "h1"
_FORMAL_GOAL_COUNT = 59
_ROUND_OFF_LIMIT = 3.0e-10
_PRODUCTION_DEGREES = frozenset({4, 5, 6})


def _readonly(values: np.ndarray) -> np.ndarray:
    result = np.ascontiguousarray(values)
    result.setflags(write=False)
    return result


def _maximum_absolute(values: np.ndarray) -> float:
    return float(np.max(np.abs(values), initial=0.0))


def _matrix_sha256(values: np.ndarray) -> str:
    matrix = np.ascontiguousarray(values)
    header = json.dumps(
        {"dtype": matrix.dtype.str, "shape": list(matrix.shape)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    digest = hashlib.sha256()
    digest.update(header)
    digest.update(matrix.tobytes())
    return digest.hexdigest()


def _payload_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_sha(value: str, *, length: int, label: str) -> str:
    normalized = str(value).lower()
    if len(normalized) != length or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{label} must be a {length}-character hex digest")
    return normalized


def _standard_element(
    family: str,
    degree: int,
) -> basix.finite_element.FiniteElement:
    if family == _HCURL:
        return basix.ufl.element(
            "N1curl",
            "hexahedron",
            int(degree),
        ).basix_element
    if family == _H1:
        return basix.ufl.element(
            "Lagrange",
            "hexahedron",
            int(degree),
            lagrange_variant=basix.LagrangeVariant.gll_warped,
        ).basix_element
    raise ValueError(f"unsupported de Rham family {family!r}")


def _entity_dofs(
    element: basix.finite_element.FiniteElement,
    dimension: int,
    entity: int,
) -> np.ndarray:
    return np.asarray(
        element.entity_dofs[int(dimension)][int(entity)],
        dtype=np.int32,
    )


def _flatten_entity_dofs(
    element: basix.finite_element.FiniteElement,
    dimensions: range,
) -> np.ndarray:
    return np.asarray(
        [
            int(dof)
            for dimension in dimensions
            for entity in element.entity_dofs[dimension]
            for dof in entity
        ],
        dtype=np.int32,
    )


def _canonicalize_columns(values: np.ndarray) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64).copy()
    for column in range(result.shape[1]):
        pivot = int(np.argmax(np.abs(result[:, column])))
        if result[pivot, column] < 0.0:
            result[:, column] *= -1.0
    return np.ascontiguousarray(result)


def _rank_from_pivoted_qr(values: np.ndarray) -> tuple[int, float]:
    matrix = np.asarray(values)
    if min(matrix.shape, default=0) == 0:
        return 0, 0.0
    _orthogonal, upper, _pivots = qr(
        matrix,
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
            * max(matrix.shape)
            * np.finfo(np.float64).eps
            * 16.0
        )
    )
    return int(np.count_nonzero(diagonal > tolerance)), tolerance


def _discrete_gradient(
    scalar_element: basix.finite_element.FiniteElement,
    hcurl_element: basix.finite_element.FiniteElement,
) -> np.ndarray:
    points = np.asarray(hcurl_element.points)
    scalar_table = np.asarray(scalar_element.tabulate(1, points))
    if scalar_table.shape[:2] != (4, len(points)):
        raise RuntimeError(
            "unexpected scalar derivative tabulation for a hexahedron"
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
    ).reshape(3 * len(points), int(scalar_element.dim))
    return np.ascontiguousarray(
        np.asarray(hcurl_element.interpolation_matrix) @ flattened
    )


def _face_coefficient_transform(
    element: basix.finite_element.FiniteElement,
    vertex_permutation: tuple[int, ...],
) -> np.ndarray:
    try:
        face_info = quadrilateral_d4_vertex_permutations()[
            tuple(vertex_permutation)
        ]
    except KeyError as exc:
        raise ValueError(
            "face vertex permutation is not a quadrilateral D4 action"
        ) from exc
    transformations = np.asarray(
        element.entity_transformations()["quadrilateral"],
        dtype=np.float64,
    )
    if transformations.shape[0] != 2:
        raise RuntimeError("Basix quadrilateral generators changed")
    rotation, reflection = transformations
    basis = np.eye(rotation.shape[0], dtype=np.float64)
    if int(face_info) & 1:
        basis = reflection @ basis
    for _ in range((int(face_info) >> 1) & 3):
        basis = rotation @ basis
    return np.asarray(basis.T, dtype=np.complex128)


def _edge_coefficient_transform(
    element: basix.finite_element.FiniteElement,
    vertex_permutation: tuple[int, ...],
) -> np.ndarray:
    permutation = tuple(vertex_permutation)
    if permutation == (0, 1):
        size = len(element.entity_dofs[1][0])
        return np.eye(size, dtype=np.complex128)
    if permutation != (1, 0):
        raise ValueError("edge vertex permutation must be identity or reversal")
    reversal = np.asarray(
        element.entity_transformations()["interval"][0],
        dtype=np.float64,
    )
    return np.asarray(reversal.T, dtype=np.complex128)


def _coefficient_transform(
    element: basix.finite_element.FiniteElement,
    *,
    dimension: int,
    vertex_permutation: tuple[int, ...],
) -> np.ndarray:
    if int(dimension) == 1:
        return _edge_coefficient_transform(element, vertex_permutation)
    if int(dimension) == 2:
        return _face_coefficient_transform(element, vertex_permutation)
    raise ValueError("p7 trace transforms require an edge or face")


@lru_cache(maxsize=1)
def _edge_to_faces() -> tuple[tuple[int, ...], ...]:
    topology = basix.topology(basix.CellType.hexahedron)
    edge_vertices = [set(map(int, row)) for row in topology[1]]
    face_vertices = [set(map(int, row)) for row in topology[2]]
    result = tuple(
        tuple(
            face
            for face, vertices in enumerate(face_vertices)
            if edge_vertices[edge].issubset(vertices)
        )
        for edge in range(12)
    )
    if len(result) != 12 or any(len(faces) != 2 for faces in result):
        raise RuntimeError("Basix returned unexpected hexahedron incidence")
    return result


@dataclass(frozen=True)
class P7EntityComplement:
    """Complete p7 coefficient complement on one canonical entity."""

    family: str
    dimension: int
    local_entity: int
    p6_dofs: np.ndarray
    p7_dofs: np.ndarray
    p6_to_p7_on_entity: np.ndarray
    complement_on_entity: np.ndarray
    complement_to_p7: np.ndarray
    embedded_q: np.ndarray
    embedded_r: np.ndarray
    audit: Mapping[str, Any]

    @property
    def complement_dimension(self) -> int:
        return int(self.complement_on_entity.shape[1])


def _orientation_audit(
    *,
    family: str,
    dimension: int,
    p6_element: basix.finite_element.FiniteElement,
    p7_element: basix.finite_element.FiniteElement,
    embedded: np.ndarray,
    complement: np.ndarray,
) -> Mapping[str, Any]:
    if dimension == 1:
        permutations = ((0, 1), (1, 0))
    elif dimension == 2:
        permutations = tuple(
            sorted(quadrilateral_d4_vertex_permutations())
        )
    else:
        raise ValueError("entity orientation audit requires edge or face")
    maximum_embedding_error = 0.0
    maximum_complement_closure_error = 0.0
    maximum_complement_unitarity_error = 0.0
    for permutation in permutations:
        transform_p6 = _coefficient_transform(
            p6_element,
            dimension=dimension,
            vertex_permutation=permutation,
        )
        transform_p7 = _coefficient_transform(
            p7_element,
            dimension=dimension,
            vertex_permutation=permutation,
        )
        representation = (
            complement.conj().T @ transform_p7 @ complement
        )
        maximum_embedding_error = max(
            maximum_embedding_error,
            _maximum_absolute(
                transform_p7 @ embedded - embedded @ transform_p6
            ),
        )
        maximum_complement_closure_error = max(
            maximum_complement_closure_error,
            _maximum_absolute(
                transform_p7 @ complement
                - complement @ representation
            ),
        )
        maximum_complement_unitarity_error = max(
            maximum_complement_unitarity_error,
            _maximum_absolute(
                representation.conj().T @ representation
                - np.eye(complement.shape[1])
            ),
        )
    checks = {
        "all_orientation_actions_covered": len(permutations)
        == {1: 2, 2: 8}[dimension],
        "p6_injection_orientation_commutes": (
            maximum_embedding_error <= _ROUND_OFF_LIMIT
        ),
        "p7_complement_orientation_closes": (
            maximum_complement_closure_error <= _ROUND_OFF_LIMIT
        ),
        "p7_complement_orientation_is_unitary": (
            maximum_complement_unitarity_error <= _ROUND_OFF_LIMIT
        ),
    }
    return MappingProxyType(
        {
            "family": family,
            "dimension": int(dimension),
            "action_count": len(permutations),
            "p6_injection_commuting_error_max": (
                maximum_embedding_error
            ),
            "complement_closure_error_max": (
                maximum_complement_closure_error
            ),
            "complement_unitarity_error_max": (
                maximum_complement_unitarity_error
            ),
            "pass": all(checks.values()),
            "checks": MappingProxyType(checks),
        }
    )


def _build_entity_complement(
    *,
    family: str,
    dimension: int,
    entity: int,
    p6_element: basix.finite_element.FiniteElement,
    p7_element: basix.finite_element.FiniteElement,
    p6_to_p7: np.ndarray,
) -> P7EntityComplement | None:
    p6_dofs = _entity_dofs(p6_element, dimension, entity)
    p7_dofs = _entity_dofs(p7_element, dimension, entity)
    difference = len(p7_dofs) - len(p6_dofs)
    if difference < 0:
        raise RuntimeError("p7 entity has fewer modes than p6")
    if difference == 0:
        return None
    embedded = np.ascontiguousarray(
        p6_to_p7[np.ix_(p7_dofs, p6_dofs)]
    )
    orthogonal, upper_full = np.linalg.qr(embedded, mode="complete")
    embedded_q = np.ascontiguousarray(
        orthogonal[:, : len(p6_dofs)]
    )
    embedded_r = np.ascontiguousarray(upper_full[: len(p6_dofs)])
    complement = _canonicalize_columns(
        orthogonal[:, len(p6_dofs) :]
    )
    complement_to_p7 = np.zeros(
        (int(p7_element.dim), difference),
        dtype=np.float64,
    )
    complement_to_p7[p7_dofs] = complement
    rank, rank_tolerance = _rank_from_pivoted_qr(embedded)
    orthogonality_error = _maximum_absolute(embedded.T @ complement)
    gram_error = _maximum_absolute(
        complement.T @ complement - np.eye(difference)
    )
    support_outside = _maximum_absolute(
        np.delete(complement_to_p7, p7_dofs, axis=0)
    )
    naive_prefix = np.eye(len(p7_dofs), len(p6_dofs))
    naive_prefix_error = _maximum_absolute(embedded - naive_prefix)
    if dimension in (1, 2):
        orientation = _orientation_audit(
            family=family,
            dimension=dimension,
            p6_element=p6_element,
            p7_element=p7_element,
            embedded=embedded,
            complement=complement,
        )
        orientation_pass = orientation["pass"] is True
    else:
        maximum_d4_invariance = 0.0
        maximum_d4_trace_support = 0.0
        trace_dofs = _flatten_entity_dofs(p7_element, range(3))
        for face in range(6):
            for reflected in (0, 1):
                for rotations in range(4):
                    cell_info = (
                        (reflected << (3 * face))
                        | (rotations << (3 * face + 1))
                    )
                    oriented = np.ascontiguousarray(
                        complement_to_p7.copy()
                    )
                    p7_element.T_apply(
                        oriented.ravel(),
                        oriented.shape[1],
                        int(cell_info),
                    )
                    maximum_d4_invariance = max(
                        maximum_d4_invariance,
                        _maximum_absolute(
                            oriented - complement_to_p7
                        ),
                    )
                    maximum_d4_trace_support = max(
                        maximum_d4_trace_support,
                        _maximum_absolute(oriented[trace_dofs]),
                    )
        orientation_pass = (
            maximum_d4_invariance <= _ROUND_OFF_LIMIT
            and maximum_d4_trace_support <= _ROUND_OFF_LIMIT
        )
        orientation = MappingProxyType(
            {
                "family": family,
                "dimension": 3,
                "action_count": 48,
                "cell_interior_invariance_error_max": (
                    maximum_d4_invariance
                ),
                "cell_interior_trace_support_max": (
                    maximum_d4_trace_support
                ),
                "pass": orientation_pass,
            }
        )
    checks = {
        "p6_entity_embedding_full_rank": rank == len(p6_dofs),
        "complete_p7_entity_complement": (
            rank + difference == len(p7_dofs)
        ),
        "complement_is_coefficient_orthogonal": (
            orthogonality_error <= _ROUND_OFF_LIMIT
        ),
        "complement_is_coefficient_orthonormal": (
            gram_error <= _ROUND_OFF_LIMIT
        ),
        "complement_has_only_its_entity_support": (
            support_outside <= _ROUND_OFF_LIMIT
        ),
        "orientation_closes": orientation_pass,
        "no_prefix_assumption": True,
    }
    if not all(checks.values()):
        failures = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            f"{family} p7 entity complement failed at "
            f"({dimension}, {entity}): {', '.join(failures)}"
        )
    audit = MappingProxyType(
        {
            "schema_version": "task035e.p7-entity-complement.v1",
            "status": "p7_entity_complement_component_pass",
            "pass": True,
            "family": family,
            "dimension": int(dimension),
            "local_entity": int(entity),
            "p6_entity_dimension": len(p6_dofs),
            "p7_entity_dimension": len(p7_dofs),
            "complement_dimension": difference,
            "embedding_rank": rank,
            "embedding_rank_tolerance": rank_tolerance,
            "orthogonality_error_max": orthogonality_error,
            "complement_gram_error_max": gram_error,
            "support_outside_entity_max": support_outside,
            "naive_prefix_error_max": naive_prefix_error,
            "prefix_assumption_used": False,
            "orientation": orientation,
            "checks": MappingProxyType(checks),
            "shadow_only": True,
            "globally_numbered": False,
            "selectable_as_production": False,
        }
    )
    arrays = (
        p6_dofs,
        p7_dofs,
        embedded,
        complement,
        complement_to_p7,
        embedded_q,
        embedded_r,
    )
    readonly = tuple(_readonly(array) for array in arrays)
    return P7EntityComplement(
        family=family,
        dimension=int(dimension),
        local_entity=int(entity),
        p6_dofs=readonly[0],
        p7_dofs=readonly[1],
        p6_to_p7_on_entity=readonly[2],
        complement_on_entity=readonly[3],
        complement_to_p7=readonly[4],
        embedded_q=readonly[5],
        embedded_r=readonly[6],
        audit=audit,
    )


@dataclass(frozen=True)
class P7TraceShadowCatalog:
    """Immutable p6-to-p7 entity-complement catalog for one hexahedron."""

    hcurl_p6_element: basix.finite_element.FiniteElement
    hcurl_p7_element: basix.finite_element.FiniteElement
    h1_p6_element: basix.finite_element.FiniteElement
    h1_p7_element: basix.finite_element.FiniteElement
    hcurl_p6_to_p7: np.ndarray
    h1_p6_to_p7: np.ndarray
    hcurl_blocks: tuple[P7EntityComplement, ...]
    h1_blocks: tuple[P7EntityComplement, ...]
    audit: Mapping[str, Any]


def _family_blocks(
    family: str,
) -> tuple[
    basix.finite_element.FiniteElement,
    basix.finite_element.FiniteElement,
    np.ndarray,
    tuple[P7EntityComplement, ...],
]:
    p6_element = _standard_element(family, _P6)
    p7_element = _standard_element(family, _P7)
    p6_to_p7 = np.asarray(
        basix.compute_interpolation_operator(p6_element, p7_element),
        dtype=np.float64,
    )
    blocks = tuple(
        block
        for dimension in range(4)
        for entity in range(len(p6_element.entity_dofs[dimension]))
        if (
            block := _build_entity_complement(
                family=family,
                dimension=dimension,
                entity=entity,
                p6_element=p6_element,
                p7_element=p7_element,
                p6_to_p7=p6_to_p7,
            )
        )
        is not None
    )
    return p6_element, p7_element, _readonly(p6_to_p7), blocks


@lru_cache(maxsize=1)
def build_p7_trace_shadow_catalog() -> P7TraceShadowCatalog:
    """Build edge, face, and cell p7 complements without global rows."""

    hcurl_p6, hcurl_p7, hcurl_injection, hcurl_blocks = (
        _family_blocks(_HCURL)
    )
    h1_p6, h1_p7, h1_injection, h1_blocks = _family_blocks(_H1)

    def counts(
        blocks: tuple[P7EntityComplement, ...],
    ) -> dict[int, tuple[int, int]]:
        return {
            dimension: (
                sum(block.dimension == dimension for block in blocks),
                sum(
                    block.complement_dimension
                    for block in blocks
                    if block.dimension == dimension
                ),
            )
            for dimension in (1, 2, 3)
        }

    hcurl_counts = counts(hcurl_blocks)
    h1_counts = counts(h1_blocks)
    hcurl_naive_prefix_error = _maximum_absolute(
        hcurl_injection
        - np.eye(int(hcurl_p7.dim), int(hcurl_p6.dim))
    )
    h1_naive_prefix_error = _maximum_absolute(
        h1_injection - np.eye(int(h1_p7.dim), int(h1_p6.dim))
    )
    checks = {
        "hcurl_p6_dimension_882": int(hcurl_p6.dim) == 882,
        "hcurl_p7_dimension_1344": int(hcurl_p7.dim) == 1344,
        "hcurl_edge_complements_12x1": hcurl_counts[1] == (12, 12),
        "hcurl_face_complements_6x24": hcurl_counts[2] == (6, 144),
        "hcurl_cell_complement_306": hcurl_counts[3] == (1, 306),
        "hcurl_all_complements_span_462": (
            sum(row[1] for row in hcurl_counts.values()) == 462
        ),
        "h1_p6_dimension_343": int(h1_p6.dim) == 343,
        "h1_p7_dimension_512": int(h1_p7.dim) == 512,
        "h1_edge_complements_12x1": h1_counts[1] == (12, 12),
        "h1_face_complements_6x11": h1_counts[2] == (6, 66),
        "h1_cell_complement_91": h1_counts[3] == (1, 91),
        "h1_all_complements_span_169": (
            sum(row[1] for row in h1_counts.values()) == 169
        ),
        "all_entity_and_orientation_audits_pass": all(
            block.audit["pass"] is True
            for block in (*hcurl_blocks, *h1_blocks)
        ),
        "full_hcurl_interpolation_is_not_a_prefix": (
            hcurl_naive_prefix_error > 1.0e-3
        ),
        "full_h1_interpolation_is_not_a_prefix": (
            h1_naive_prefix_error > 1.0e-3
        ),
    }
    if not all(checks.values()):
        failures = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "p7 trace shadow catalog failed: " + ", ".join(failures)
        )
    audit = MappingProxyType(
        {
            "schema_version": "task035e.p7-trace-shadow-catalog.v1",
            "status": "p7_trace_shadow_catalog_component_pass",
            "component_pass": True,
            "hcurl_p6_dimension": int(hcurl_p6.dim),
            "hcurl_p7_dimension": int(hcurl_p7.dim),
            "hcurl_edge_complement_per_entity": 1,
            "hcurl_face_complement_per_entity": 24,
            "hcurl_cell_complement": 306,
            "hcurl_total_complement": 462,
            "h1_p6_dimension": int(h1_p6.dim),
            "h1_p7_dimension": int(h1_p7.dim),
            "h1_edge_complement_per_entity": 1,
            "h1_face_complement_per_entity": 11,
            "h1_cell_complement": 91,
            "h1_total_complement": 169,
            "hcurl_naive_prefix_error_max": hcurl_naive_prefix_error,
            "h1_naive_prefix_error_max": h1_naive_prefix_error,
            "prefix_assumption_used": False,
            "checks": MappingProxyType(checks),
            "production_degrees_unchanged": (4, 5, 6),
            "shadow_only": True,
            "inactive_p7_modes_globally_numbered": False,
            "selectable_as_production": False,
            "next_production_plan": None,
            "ordinary_default_changed": False,
        }
    )
    return P7TraceShadowCatalog(
        hcurl_p6_element=hcurl_p6,
        hcurl_p7_element=hcurl_p7,
        h1_p6_element=h1_p6,
        h1_p7_element=h1_p7,
        hcurl_p6_to_p7=hcurl_injection,
        h1_p6_to_p7=h1_injection,
        hcurl_blocks=hcurl_blocks,
        h1_blocks=h1_blocks,
        audit=audit,
    )


def _block_map(
    blocks: tuple[P7EntityComplement, ...],
) -> Mapping[tuple[int, int], P7EntityComplement]:
    return MappingProxyType(
        {(block.dimension, block.local_entity): block for block in blocks}
    )


def _closed_local_selection(
    requested_edges: Iterable[int],
    requested_faces: Iterable[int],
) -> tuple[
    tuple[int, ...],
    tuple[int, ...],
    tuple[int, ...],
    bool,
]:
    edges = tuple(sorted(set(map(int, requested_edges))))
    faces = tuple(sorted(set(map(int, requested_faces))))
    if any(not 0 <= edge < 12 for edge in edges):
        raise ValueError("local p7 shadow edge must be in [0, 11]")
    if any(not 0 <= face < 6 for face in faces):
        raise ValueError("local p7 shadow face must be in [0, 5]")
    if not edges and not faces:
        raise ValueError(
            "selective p7 trace shadow requires an edge or face request"
        )
    closed_faces = set(faces)
    for edge in edges:
        closed_faces.update(_edge_to_faces()[edge])
    return edges, faces, tuple(sorted(closed_faces)), True


def _selected_keys(
    edges: tuple[int, ...],
    faces: tuple[int, ...],
    *,
    cell: bool,
) -> tuple[tuple[int, int], ...]:
    result = [(1, edge) for edge in edges]
    result.extend((2, face) for face in faces)
    if cell:
        result.append((3, 0))
    return tuple(result)


def _expansion_and_ranges(
    p6_to_p7: np.ndarray,
    blocks: Mapping[tuple[int, int], P7EntityComplement],
    selected: tuple[tuple[int, int], ...],
) -> tuple[np.ndarray, Mapping[tuple[int, int], np.ndarray]]:
    columns = [np.asarray(p6_to_p7)]
    ranges: dict[tuple[int, int], np.ndarray] = {}
    next_column = p6_to_p7.shape[1]
    for key in selected:
        block = blocks[key]
        columns.append(np.asarray(block.complement_to_p7))
        values = np.arange(
            next_column,
            next_column + block.complement_dimension,
            dtype=np.int32,
        )
        ranges[key] = _readonly(values)
        next_column += block.complement_dimension
    return (
        _readonly(np.concatenate(columns, axis=1)),
        MappingProxyType(ranges),
    )


def _coordinates_in_active_space(
    *,
    p6_element: basix.finite_element.FiniteElement,
    p7_element: basix.finite_element.FiniteElement,
    p6_to_p7: np.ndarray,
    blocks: Mapping[tuple[int, int], P7EntityComplement],
    selected_ranges: Mapping[tuple[int, int], np.ndarray],
    expansion: np.ndarray,
    values: np.ndarray,
) -> tuple[np.ndarray, float]:
    rhs = np.asarray(values)
    vector_input = rhs.ndim == 1
    if vector_input:
        rhs = rhs[:, None]
    if rhs.ndim != 2 or rhs.shape[0] != int(p7_element.dim):
        raise ValueError("p7 active coordinate input has the wrong shape")
    coordinates = np.zeros(
        (expansion.shape[1], rhs.shape[1]),
        dtype=np.result_type(rhs, np.float64),
    )
    solved_p6: list[int] = []
    entity_closure_error = 0.0
    for dimension in range(4):
        for entity in range(len(p6_element.entity_dofs[dimension])):
            p6_dofs = _entity_dofs(p6_element, dimension, entity)
            p7_dofs = _entity_dofs(p7_element, dimension, entity)
            if len(p6_dofs) == 0 and len(p7_dofs) == 0:
                continue
            residual = np.asarray(rhs[p7_dofs]).copy()
            if solved_p6:
                residual -= (
                    p6_to_p7[np.ix_(p7_dofs, solved_p6)]
                    @ coordinates[solved_p6]
                )
            key = (dimension, entity)
            embedded = p6_to_p7[np.ix_(p7_dofs, p6_dofs)]
            block = blocks.get(key)
            if block is None:
                if embedded.shape[0] != embedded.shape[1]:
                    raise RuntimeError("zero-complement entity is not square")
                base_values = np.linalg.solve(embedded, residual)
                reconstructed = embedded @ base_values
            else:
                base_values = solve_triangular(
                    block.embedded_r,
                    block.embedded_q.T @ residual,
                    lower=False,
                    check_finite=False,
                )
                reconstructed = embedded @ base_values
                if key in selected_ranges:
                    complement_values = (
                        block.complement_on_entity.conj().T @ residual
                    )
                    coordinates[selected_ranges[key]] = complement_values
                    reconstructed += (
                        block.complement_on_entity @ complement_values
                    )
            coordinates[p6_dofs] = base_values
            solved_p6.extend(map(int, p6_dofs))
            entity_closure_error = max(
                entity_closure_error,
                _maximum_absolute(reconstructed - residual),
            )
    full_error = _maximum_absolute(expansion @ coordinates - rhs)
    error = max(entity_closure_error, full_error)
    result = np.ascontiguousarray(coordinates)
    if vector_input:
        return result[:, 0], error
    return result, error


@dataclass(frozen=True)
class SelectiveP7TraceShadowSpace:
    """One exact-sequence-closed local p7 trace shadow."""

    catalog: P7TraceShadowCatalog
    requested_edges: tuple[int, ...]
    requested_faces: tuple[int, ...]
    selected_edges: tuple[int, ...]
    selected_faces: tuple[int, ...]
    cell_selected: bool
    hcurl_expansion: np.ndarray
    h1_expansion: np.ndarray
    discrete_gradient: np.ndarray
    hcurl_trace_dofs: np.ndarray
    hcurl_interior_dofs: np.ndarray
    hcurl_selected_ranges: Mapping[tuple[int, int], np.ndarray]
    h1_selected_ranges: Mapping[tuple[int, int], np.ndarray]
    audit: Mapping[str, Any]
    production_degrees_unchanged: frozenset[int] = _PRODUCTION_DEGREES
    shadow_only: bool = True
    selectable_as_production: bool = False
    next_production_plan: None = None

    @property
    def hcurl_dimension(self) -> int:
        return int(self.hcurl_expansion.shape[1])

    @property
    def h1_dimension(self) -> int:
        return int(self.h1_expansion.shape[1])


@lru_cache(maxsize=64)
def build_selective_p7_trace_shadow_space(
    requested_edges: tuple[int, ...] = (),
    requested_faces: tuple[int, ...] = (),
) -> SelectiveP7TraceShadowSpace:
    """Close one local trace request upward and build its p7 shadow pair."""

    requested_edge_rows, requested_face_rows, selected_faces, cell = (
        _closed_local_selection(requested_edges, requested_faces)
    )
    selected_edges = requested_edge_rows
    selected = _selected_keys(
        selected_edges,
        selected_faces,
        cell=cell,
    )
    catalog = build_p7_trace_shadow_catalog()
    hcurl_blocks = _block_map(catalog.hcurl_blocks)
    h1_blocks = _block_map(catalog.h1_blocks)
    hcurl_expansion, hcurl_ranges = _expansion_and_ranges(
        catalog.hcurl_p6_to_p7,
        hcurl_blocks,
        selected,
    )
    h1_expansion, h1_ranges = _expansion_and_ranges(
        catalog.h1_p6_to_p7,
        h1_blocks,
        selected,
    )

    p6_gradient = _discrete_gradient(
        catalog.h1_p6_element,
        catalog.hcurl_p6_element,
    )
    p7_gradient = _discrete_gradient(
        catalog.h1_p7_element,
        catalog.hcurl_p7_element,
    )
    p6_commuting_error = _maximum_absolute(
        p7_gradient @ catalog.h1_p6_to_p7
        - catalog.hcurl_p6_to_p7 @ p6_gradient
    )
    expanded_gradient = np.ascontiguousarray(
        p7_gradient @ h1_expansion
    )
    shadow_gradient, gradient_range_error = _coordinates_in_active_space(
        p6_element=catalog.hcurl_p6_element,
        p7_element=catalog.hcurl_p7_element,
        p6_to_p7=catalog.hcurl_p6_to_p7,
        blocks=hcurl_blocks,
        selected_ranges=hcurl_ranges,
        expansion=hcurl_expansion,
        values=expanded_gradient,
    )
    gradient_rank, gradient_rank_tolerance = _rank_from_pivoted_qr(
        shadow_gradient
    )
    hcurl_trace = list(
        map(
            int,
            _flatten_entity_dofs(
                catalog.hcurl_p6_element,
                range(3),
            ),
        )
    )
    hcurl_interior = list(
        map(
            int,
            _flatten_entity_dofs(
                catalog.hcurl_p6_element,
                range(3, 4),
            ),
        )
    )
    for key in selected:
        target = hcurl_interior if key[0] == 3 else hcurl_trace
        target.extend(map(int, hcurl_ranges[key]))
    hcurl_trace_array = np.asarray(hcurl_trace, dtype=np.int32)
    hcurl_interior_array = np.asarray(hcurl_interior, dtype=np.int32)
    signature_payload = {
        "requested_edges": list(requested_edge_rows),
        "requested_faces": list(requested_face_rows),
        "selected_edges": list(selected_edges),
        "selected_faces": list(selected_faces),
        "cell_selected": cell,
        "hcurl_dimension": hcurl_expansion.shape[1],
        "h1_dimension": h1_expansion.shape[1],
        "hcurl_expansion_sha256": _matrix_sha256(hcurl_expansion),
        "h1_expansion_sha256": _matrix_sha256(h1_expansion),
    }
    signature = _payload_sha256(signature_payload)
    checks = {
        "catalog_component_pass": catalog.audit["component_pass"] is True,
        "edge_requests_preserved": selected_edges == requested_edge_rows,
        "edge_to_incident_face_closure_complete": all(
            set(_edge_to_faces()[edge]).issubset(selected_faces)
            for edge in selected_edges
        ),
        "trace_selection_closes_cell": cell,
        "active_hcurl_columns_are_not_full_p7_unless_all_selected": (
            hcurl_expansion.shape[1] <= int(catalog.hcurl_p7_element.dim)
        ),
        "p6_discrete_gradient_injection_commutes": (
            p6_commuting_error <= _ROUND_OFF_LIMIT
        ),
        "selective_discrete_gradient_range_closes": (
            gradient_range_error <= _ROUND_OFF_LIMIT
        ),
        "selective_gradient_kernel_is_constant_only": (
            gradient_rank == h1_expansion.shape[1] - 1
        ),
        "active_partition_covers_each_column_once": (
            len(hcurl_trace_array) + len(hcurl_interior_array)
            == hcurl_expansion.shape[1]
            and len(
                np.unique(
                    np.concatenate(
                        (hcurl_trace_array, hcurl_interior_array)
                    )
                )
            )
            == hcurl_expansion.shape[1]
        ),
    }
    if not all(checks.values()):
        failures = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "selective p7 trace shadow exact sequence failed: "
            + ", ".join(failures)
        )
    audit = MappingProxyType(
        {
            "schema_version": "task035e.selective-p7-trace-shadow.v1",
            "status": "selective_p7_trace_shadow_component_pass",
            "component_pass": True,
            "requested_edges": requested_edge_rows,
            "requested_faces": requested_face_rows,
            "selected_edges": selected_edges,
            "selected_faces": selected_faces,
            "closure_added_faces": tuple(
                sorted(set(selected_faces) - set(requested_face_rows))
            ),
            "cell_selected_by_exact_sequence_closure": cell,
            "hcurl_dimension": hcurl_expansion.shape[1],
            "h1_dimension": h1_expansion.shape[1],
            "hcurl_added_edge_modes": len(selected_edges),
            "hcurl_added_face_modes": 24 * len(selected_faces),
            "hcurl_added_cell_modes": 306,
            "h1_added_edge_modes": len(selected_edges),
            "h1_added_face_modes": 11 * len(selected_faces),
            "h1_added_cell_modes": 91,
            "active_trace_rows": len(hcurl_trace_array),
            "active_cell_interior_rows": len(hcurl_interior_array),
            "p6_gradient_commuting_error_max": p6_commuting_error,
            "gradient_range_error_max": gradient_range_error,
            "gradient_rank": gradient_rank,
            "gradient_rank_tolerance": gradient_rank_tolerance,
            "selection_signature_sha256": signature,
            "checks": MappingProxyType(checks),
            "production_degrees_unchanged": (4, 5, 6),
            "shadow_only": True,
            "inactive_p7_modes_globally_numbered": False,
            "selectable_as_production": False,
            "next_production_plan": None,
            "actual_multilevel_plan_binding_status": "unknown",
            "mpi8_partition_identity_status": "unknown",
            "coverage_status": "incomplete",
            "p6_saturation_status": "unknown",
            "p6_saturation_measured_pass": False,
            "can_satisfy_f1_alone": False,
            "ordinary_default_changed": False,
        }
    )
    arrays = (
        hcurl_expansion,
        h1_expansion,
        shadow_gradient,
        hcurl_trace_array,
        hcurl_interior_array,
    )
    readonly = tuple(_readonly(array) for array in arrays)
    return SelectiveP7TraceShadowSpace(
        catalog=catalog,
        requested_edges=requested_edge_rows,
        requested_faces=requested_face_rows,
        selected_edges=selected_edges,
        selected_faces=selected_faces,
        cell_selected=cell,
        hcurl_expansion=readonly[0],
        h1_expansion=readonly[1],
        discrete_gradient=readonly[2],
        hcurl_trace_dofs=readonly[3],
        hcurl_interior_dofs=readonly[4],
        hcurl_selected_ranges=hcurl_ranges,
        h1_selected_ranges=h1_ranges,
        audit=audit,
    )


@dataclass(frozen=True, order=True)
class P7TraceEntityKey:
    """Caller-supplied physical trace identity."""

    dimension: int
    entity: int

    def __post_init__(self) -> None:
        if int(self.dimension) not in (1, 2):
            raise ValueError("p7 periodic shadow entity must be edge or face")
        if int(self.entity) < 0:
            raise ValueError("p7 periodic shadow entity id must be nonnegative")
        object.__setattr__(self, "dimension", int(self.dimension))
        object.__setattr__(self, "entity", int(self.entity))


@dataclass(frozen=True)
class P7FloquetTraceRelation:
    """One structural master-to-slave p7 trace relation."""

    axis: str
    master: P7TraceEntityKey
    slave: P7TraceEntityKey
    vertex_permutation: tuple[int, ...]
    phase: complex

    def __post_init__(self) -> None:
        axis = str(self.axis).lower()
        if axis not in {"x", "y"}:
            raise ValueError("p7 Floquet relation axis must be x or y")
        if self.master.dimension != self.slave.dimension:
            raise ValueError("p7 Floquet relation mixes entity dimensions")
        if self.master == self.slave:
            raise ValueError("p7 Floquet master and slave must differ")
        permutation = tuple(map(int, self.vertex_permutation))
        expected = 2 if self.master.dimension == 1 else 4
        if len(permutation) != expected or sorted(permutation) != list(
            range(expected)
        ):
            raise ValueError("p7 Floquet vertex permutation is invalid")
        phase = complex(self.phase)
        if not np.isfinite(phase.real) or not np.isfinite(phase.imag):
            raise ValueError("p7 Floquet phase must be finite")
        if not np.isclose(abs(phase), 1.0, rtol=0.0, atol=2.0e-12):
            raise ValueError("p7 Floquet phase must have unit modulus")
        object.__setattr__(self, "axis", axis)
        object.__setattr__(self, "vertex_permutation", permutation)
        object.__setattr__(self, "phase", phase)


@dataclass(frozen=True)
class P7TraceOrbitClosure:
    """Closed physical trace selection and complement-transform evidence."""

    requested: tuple[P7TraceEntityKey, ...]
    selected: tuple[P7TraceEntityKey, ...]
    closure_added: tuple[P7TraceEntityKey, ...]
    relations: tuple[P7FloquetTraceRelation, ...]
    audit: Mapping[str, Any]


def _relation_complement_transform(
    catalog: P7TraceShadowCatalog,
    relation: P7FloquetTraceRelation,
    *,
    family: str,
) -> tuple[np.ndarray, float, float]:
    if family == _HCURL:
        p6_element = catalog.hcurl_p6_element
        p7_element = catalog.hcurl_p7_element
        blocks = _block_map(catalog.hcurl_blocks)
    elif family == _H1:
        p6_element = catalog.h1_p6_element
        p7_element = catalog.h1_p7_element
        blocks = _block_map(catalog.h1_blocks)
    else:
        raise ValueError(f"unsupported relation family {family!r}")
    dimension = relation.master.dimension
    block = blocks[(dimension, 0)]
    transform_p6 = _coefficient_transform(
        p6_element,
        dimension=dimension,
        vertex_permutation=relation.vertex_permutation,
    )
    transform_p7 = _coefficient_transform(
        p7_element,
        dimension=dimension,
        vertex_permutation=relation.vertex_permutation,
    )
    embedded = np.asarray(block.p6_to_p7_on_entity)
    complement = np.asarray(block.complement_on_entity)
    injection_error = _maximum_absolute(
        transform_p7 @ embedded - embedded @ transform_p6
    )
    representation = complement.conj().T @ transform_p7 @ complement
    closure_error = _maximum_absolute(
        transform_p7 @ complement - complement @ representation
    )
    return (
        np.ascontiguousarray(relation.phase * representation),
        injection_error,
        closure_error,
    )


def _components(
    nodes: set[P7TraceEntityKey],
    relations: tuple[P7FloquetTraceRelation, ...],
) -> tuple[
    Mapping[P7TraceEntityKey, P7TraceEntityKey],
    tuple[tuple[P7TraceEntityKey, ...], ...],
]:
    parent = {node: node for node in nodes}

    def find(node: P7TraceEntityKey) -> P7TraceEntityKey:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: P7TraceEntityKey, right: P7TraceEntityKey) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for relation in relations:
        union(relation.master, relation.slave)
    groups: dict[P7TraceEntityKey, list[P7TraceEntityKey]] = {}
    for node in nodes:
        groups.setdefault(find(node), []).append(node)
    components = tuple(
        tuple(sorted(group))
        for group in sorted(groups.values(), key=lambda row: min(row))
    )
    roots = MappingProxyType({node: find(node) for node in nodes})
    return roots, components


def close_p7_trace_floquet_orbits(
    requested: Iterable[P7TraceEntityKey],
    relations: Iterable[P7FloquetTraceRelation],
) -> P7TraceOrbitClosure:
    """Close requested physical entities over supplied Floquet orbits."""

    requested_rows = tuple(sorted(set(requested)))
    if not requested_rows:
        raise ValueError("p7 Floquet shadow requires a requested entity")
    relation_rows = tuple(relations)
    nodes = set(requested_rows)
    for relation in relation_rows:
        nodes.update((relation.master, relation.slave))
    roots, components = _components(nodes, relation_rows)
    requested_roots = {roots[node] for node in requested_rows}
    selected = tuple(
        sorted(
            node
            for component in components
            if roots[component[0]] in requested_roots
            for node in component
        )
    )
    closure_added = tuple(
        sorted(set(selected) - set(requested_rows))
    )
    catalog = build_p7_trace_shadow_catalog()
    adjacency: dict[
        str,
        dict[P7TraceEntityKey, list[tuple[P7TraceEntityKey, np.ndarray]]],
    ] = {
        family: {node: [] for node in nodes}
        for family in (_HCURL, _H1)
    }
    relation_records: list[dict[str, Any]] = []
    maximum_injection_error = 0.0
    maximum_subspace_error = 0.0
    for relation in relation_rows:
        transforms: dict[str, np.ndarray] = {}
        errors: dict[str, tuple[float, float]] = {}
        for family in (_HCURL, _H1):
            transform, injection_error, closure_error = (
                _relation_complement_transform(
                    catalog,
                    relation,
                    family=family,
                )
            )
            transforms[family] = transform
            errors[family] = (injection_error, closure_error)
            adjacency[family][relation.master].append(
                (relation.slave, transform)
            )
            adjacency[family][relation.slave].append(
                (relation.master, np.linalg.inv(transform))
            )
            maximum_injection_error = max(
                maximum_injection_error,
                injection_error,
            )
            maximum_subspace_error = max(
                maximum_subspace_error,
                closure_error,
            )
        relation_records.append(
            {
                "axis": relation.axis,
                "dimension": relation.master.dimension,
                "master_entity": relation.master.entity,
                "slave_entity": relation.slave.entity,
                "vertex_permutation": list(
                    relation.vertex_permutation
                ),
                "phase": [relation.phase.real, relation.phase.imag],
                "hcurl_complement_transform_sha256": _matrix_sha256(
                    transforms[_HCURL]
                ),
                "h1_complement_transform_sha256": _matrix_sha256(
                    transforms[_H1]
                ),
                "hcurl_injection_error_max": errors[_HCURL][0],
                "hcurl_subspace_error_max": errors[_HCURL][1],
                "h1_injection_error_max": errors[_H1][0],
                "h1_subspace_error_max": errors[_H1][1],
            }
        )
    maximum_cycle_error = 0.0
    for family in (_HCURL, _H1):
        for component in components:
            if len(component) == 1 or not set(component).intersection(
                selected
            ):
                continue
            root = component[0]
            mode_count = {
                (_HCURL, 1): 1,
                (_HCURL, 2): 24,
                (_H1, 1): 1,
                (_H1, 2): 11,
            }[(family, root.dimension)]
            potentials = {
                root: np.eye(mode_count, dtype=np.complex128)
            }
            queue = [root]
            while queue:
                current = queue.pop(0)
                for neighbor, transform in adjacency[family][current]:
                    candidate = transform @ potentials[current]
                    if neighbor in potentials:
                        maximum_cycle_error = max(
                            maximum_cycle_error,
                            _maximum_absolute(
                                candidate - potentials[neighbor]
                            ),
                        )
                    else:
                        potentials[neighbor] = candidate
                        queue.append(neighbor)
            if set(potentials) != set(component):
                raise RuntimeError(
                    "p7 Floquet shadow orbit traversal is incomplete"
                )
    if (
        maximum_injection_error > _ROUND_OFF_LIMIT
        or maximum_subspace_error > _ROUND_OFF_LIMIT
        or maximum_cycle_error > _ROUND_OFF_LIMIT
    ):
        raise RuntimeError(
            "p7 Floquet shadow transform or cycle audit failed"
        )
    selected_components = [
        component
        for component in components
        if set(component).intersection(selected)
    ]
    full_rows = sum(
        {1: 1, 2: 24}[node.dimension] for node in selected
    )
    independent_rows = sum(
        {1: 1, 2: 24}[component[0].dimension]
        for component in selected_components
    )
    core = {
        "schema_version": "task035e.p7-trace-floquet-orbit-shadow.v1",
        "status": "p7_trace_floquet_orbit_component_closed",
        "component_pass": True,
        "requested": [
            [node.dimension, node.entity] for node in requested_rows
        ],
        "selected": [[node.dimension, node.entity] for node in selected],
        "closure_added": [
            [node.dimension, node.entity] for node in closure_added
        ],
        "relation_count": len(relation_rows),
        "selected_orbit_count": len(selected_components),
        "maximum_selected_orbit_size": max(
            (len(component) for component in selected_components),
            default=1,
        ),
        "hcurl_shadow_rows_before_periodic_elimination": full_rows,
        "hcurl_independent_shadow_rows": independent_rows,
        "maximum_p6_injection_commuting_error": maximum_injection_error,
        "maximum_p7_complement_subspace_error": maximum_subspace_error,
        "maximum_floquet_cycle_error": maximum_cycle_error,
        "relations": relation_records,
        "all_requested_orbits_closed": True,
        "inactive_p7_modes_globally_numbered": False,
        "geometry_binding_status": "caller_supplied_unverified",
        "actual_multilevel_plan_binding_status": "unknown",
        "mpi8_partition_identity_status": "unknown",
        "coverage_status": "incomplete",
        "measured_pass": False,
        "selectable_as_production": False,
        "next_production_plan": None,
    }
    audit = MappingProxyType(core | {"orbit_sha256": _payload_sha256(core)})
    return P7TraceOrbitClosure(
        requested=requested_rows,
        selected=selected,
        closure_added=closure_added,
        relations=relation_rows,
        audit=audit,
    )


@dataclass(frozen=True)
class SelectiveP7TraceShadowSchur:
    """Local projected tensor and exact cell-interior Schur elimination."""

    space: SelectiveP7TraceShadowSpace
    active_tensor: np.ndarray
    active_rhs: np.ndarray
    schur_tensor: np.ndarray
    schur_rhs: np.ndarray
    interior_from_trace: np.ndarray
    interior_load: np.ndarray
    audit: Mapping[str, Any]

    def recover_active_coefficients(
        self,
        trace_coefficients: np.ndarray,
    ) -> np.ndarray:
        trace = np.asarray(trace_coefficients)
        if trace.shape != (len(self.space.hcurl_trace_dofs),):
            raise ValueError("selective p7 trace vector has the wrong shape")
        interior = self.interior_load - self.interior_from_trace @ trace
        active = np.zeros(
            self.space.hcurl_dimension,
            dtype=np.result_type(trace, self.active_rhs),
        )
        active[self.space.hcurl_trace_dofs] = trace
        active[self.space.hcurl_interior_dofs] = interior
        return np.ascontiguousarray(active)

    def recover_p7_coefficients(
        self,
        trace_coefficients: np.ndarray,
    ) -> np.ndarray:
        return np.ascontiguousarray(
            self.space.hcurl_expansion
            @ self.recover_active_coefficients(trace_coefficients)
        )


def condense_selective_p7_trace_shadow_tensor(
    space: SelectiveP7TraceShadowSpace,
    p7_tensor: np.ndarray,
    p7_rhs: np.ndarray | None = None,
) -> SelectiveP7TraceShadowSchur:
    """Project one p7 cell tensor and eliminate all active cell modes."""

    tensor = np.asarray(p7_tensor)
    dimension = int(space.catalog.hcurl_p7_element.dim)
    if tensor.shape != (dimension, dimension):
        raise ValueError("p7 trace-shadow cell tensor has the wrong shape")
    if not np.all(np.isfinite(tensor)):
        raise ValueError("p7 trace-shadow cell tensor is non-finite")
    if p7_rhs is None:
        rhs = np.zeros(dimension, dtype=tensor.dtype)
    else:
        rhs = np.asarray(p7_rhs)
        if rhs.shape != (dimension,):
            raise ValueError("p7 trace-shadow right-hand side is wrong")
        if not np.all(np.isfinite(rhs)):
            raise ValueError("p7 trace-shadow right-hand side is non-finite")
    expansion = np.asarray(space.hcurl_expansion)
    active_tensor = np.ascontiguousarray(
        expansion.conj().T @ tensor @ expansion
    )
    active_rhs = np.ascontiguousarray(expansion.conj().T @ rhs)
    trace = np.asarray(space.hcurl_trace_dofs)
    interior = np.asarray(space.hcurl_interior_dofs)
    a_tt = active_tensor[np.ix_(trace, trace)]
    a_ti = active_tensor[np.ix_(trace, interior)]
    a_it = active_tensor[np.ix_(interior, trace)]
    a_ii = active_tensor[np.ix_(interior, interior)]
    b_t = active_rhs[trace]
    b_i = active_rhs[interior]
    try:
        interior_from_trace = np.linalg.solve(a_ii, a_it)
        interior_load = np.linalg.solve(a_ii, b_i)
    except np.linalg.LinAlgError as exc:
        raise RuntimeError(
            "selective p7 trace-shadow interior block is singular"
        ) from exc
    schur_tensor = np.ascontiguousarray(
        a_tt - a_ti @ interior_from_trace
    )
    schur_rhs = np.ascontiguousarray(b_t - a_ti @ interior_load)
    itemsize = int(active_tensor.dtype.itemsize)
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035e.selective-p7-trace-shadow-schur.v1"
            ),
            "status": "selective_p7_trace_shadow_schur_component_pass",
            "component_pass": True,
            "selection_signature_sha256": space.audit[
                "selection_signature_sha256"
            ],
            "p7_cell_local_rows": dimension,
            "active_local_rows": space.hcurl_dimension,
            "active_trace_rows": len(trace),
            "active_cell_interior_rows": len(interior),
            "schur_rows": len(trace),
            "projection_convention": "E^H A E",
            "input_tensor_sha256": _matrix_sha256(tensor),
            "input_rhs_sha256": _matrix_sha256(rhs),
            "active_tensor_sha256": _matrix_sha256(active_tensor),
            "schur_tensor_sha256": _matrix_sha256(schur_tensor),
            "cell_local_p7_input_bytes": dimension**2 * itemsize,
            "active_tensor_bytes": space.hcurl_dimension**2 * itemsize,
            "interior_block_bytes": len(interior) ** 2 * itemsize,
            "schur_tensor_bytes": len(trace) ** 2 * itemsize,
            "input_p7_tensor_retained": False,
            "global_p7_matrix_constructed": False,
            "inactive_p7_modes_globally_numbered": False,
            "shadow_only": True,
            "coverage_status": "incomplete",
            "p6_saturation_status": "unknown",
            "p6_saturation_measured_pass": False,
            "selectable_as_production": False,
            "next_production_plan": None,
        }
    )
    arrays = (
        active_tensor,
        active_rhs,
        schur_tensor,
        schur_rhs,
        interior_from_trace,
        interior_load,
    )
    readonly = tuple(_readonly(array) for array in arrays)
    return SelectiveP7TraceShadowSchur(
        space=space,
        active_tensor=readonly[0],
        active_rhs=readonly[1],
        schur_tensor=readonly[2],
        schur_rhs=readonly[3],
        interior_from_trace=readonly[4],
        interior_load=readonly[5],
        audit=audit,
    )


@dataclass(frozen=True)
class SelectiveP7TraceShadowDWR:
    """Local residual/adjoint component on selected p7 complements."""

    space: SelectiveP7TraceShadowSpace
    projected_residual: np.ndarray
    projected_goal_gradients: np.ndarray
    adjoints: np.ndarray
    correction: np.ndarray
    signed_contributions: np.ndarray
    direct_goal_deltas: np.ndarray
    audit: Mapping[str, Any]


def evaluate_selective_p7_trace_shadow_dwr(
    space: SelectiveP7TraceShadowSpace,
    p7_tensor: np.ndarray,
    p7_rhs: np.ndarray,
    current_p6_coefficients: np.ndarray,
    p7_goal_gradients: np.ndarray,
) -> SelectiveP7TraceShadowDWR:
    """Compute the signed 59-goal component on selected p7-only modes."""

    tensor = np.asarray(p7_tensor)
    rhs = np.asarray(p7_rhs)
    current = np.asarray(current_p6_coefficients)
    gradients = np.asarray(p7_goal_gradients)
    p7_dimension = int(space.catalog.hcurl_p7_element.dim)
    if tensor.shape != (p7_dimension, p7_dimension):
        raise ValueError("p7 DWR tensor has the wrong shape")
    if rhs.shape != (p7_dimension,):
        raise ValueError("p7 DWR right-hand side has the wrong shape")
    if current.shape != (int(space.catalog.hcurl_p6_element.dim),):
        raise ValueError("p6 DWR current coefficients have the wrong shape")
    if gradients.shape != (_FORMAL_GOAL_COUNT, p7_dimension):
        raise ValueError("p7 DWR requires exactly 59 full goal gradients")
    for name, values in (
        ("tensor", tensor),
        ("right-hand side", rhs),
        ("current coefficients", current),
        ("goal gradients", gradients),
    ):
        if not np.all(np.isfinite(values)):
            raise ValueError(f"p7 DWR {name} contains non-finite values")
    complement = np.asarray(
        space.hcurl_expansion[
            :, int(space.catalog.hcurl_p6_element.dim) :
        ]
    )
    current_p7 = space.catalog.hcurl_p6_to_p7 @ current
    projected_residual = np.ascontiguousarray(
        complement.conj().T @ (rhs - tensor @ current_p7)
    )
    projected_goals = np.ascontiguousarray(
        gradients @ complement.conj()
    )
    complement_tensor = np.ascontiguousarray(
        complement.conj().T @ tensor @ complement
    )
    try:
        correction = np.linalg.solve(
            complement_tensor,
            projected_residual,
        )
        adjoints = np.linalg.solve(
            complement_tensor.conj().T,
            projected_goals.T,
        ).T
    except np.linalg.LinAlgError as exc:
        raise RuntimeError("selected p7 DWR complement block is singular") from exc
    signed = np.ascontiguousarray(
        np.real(np.einsum("gi,i->g", adjoints.conj(), projected_residual))
    )
    direct = np.ascontiguousarray(
        np.real(np.einsum("gi,i->g", projected_goals.conj(), correction))
    )
    closure_error = _maximum_absolute(signed - direct)
    scale = max(
        _maximum_absolute(signed),
        _maximum_absolute(direct),
        1.0,
    )
    if closure_error > 5.0e-10 * scale:
        raise RuntimeError("selected p7 trace-shadow DWR closure failed")
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035e.selective-p7-trace-shadow-dwr.v1"
            ),
            "status": "selective_p7_trace_shadow_dwr_component_pass",
            "component_pass": True,
            "selection_signature_sha256": space.audit[
                "selection_signature_sha256"
            ],
            "goal_count": _FORMAL_GOAL_COUNT,
            "selected_complement_rows": complement.shape[1],
            "selected_edge_complement_rows": len(space.selected_edges),
            "selected_face_complement_rows": 24
            * len(space.selected_faces),
            "selected_cell_complement_rows": 306,
            "projected_residual_norm": float(
                np.linalg.norm(projected_residual)
            ),
            "dwr_direct_closure_error_max": closure_error,
            "tensor_sha256": _matrix_sha256(tensor),
            "rhs_sha256": _matrix_sha256(rhs),
            "current_p6_sha256": _matrix_sha256(current),
            "goal_gradients_sha256": _matrix_sha256(gradients),
            "signed_contributions_sha256": _matrix_sha256(signed),
            "global_p7_matrix_constructed": False,
            "inactive_p7_modes_globally_numbered": False,
            "shadow_only": True,
            "coverage_status": "incomplete",
            "actual_multilevel_plan_binding_status": "unknown",
            "mpi8_partition_identity_status": "unknown",
            "p6_saturation_status": "unknown",
            "p6_saturation_measured_pass": False,
            "can_satisfy_f1_alone": False,
            "selectable_as_production": False,
            "next_production_plan": None,
        }
    )
    arrays = (
        projected_residual,
        projected_goals,
        adjoints,
        correction,
        signed,
        direct,
    )
    readonly = tuple(_readonly(array) for array in arrays)
    return SelectiveP7TraceShadowDWR(
        space=space,
        projected_residual=readonly[0],
        projected_goal_gradients=readonly[1],
        adjoints=readonly[2],
        correction=readonly[3],
        signed_contributions=readonly[4],
        direct_goal_deltas=readonly[5],
        audit=audit,
    )


def build_closed_p7_trace_shadow_evidence(
    *,
    source_sha: str,
    leaf_identity_sha256: str,
    space: SelectiveP7TraceShadowSpace,
    orbit_closure: P7TraceOrbitClosure,
    schur: SelectiveP7TraceShadowSchur,
    dwr: SelectiveP7TraceShadowDWR,
) -> Mapping[str, Any]:
    """Aggregate hash-bound component evidence without formal-pass credit."""

    clean_source = _validate_sha(
        source_sha,
        length=40,
        label="source SHA",
    )
    leaf_sha = _validate_sha(
        leaf_identity_sha256,
        length=64,
        label="leaf identity SHA",
    )
    signature = str(space.audit["selection_signature_sha256"])
    if schur.space is not space or dwr.space is not space:
        raise ValueError("p7 trace-shadow evidence mixes space instances")
    if (
        str(schur.audit["selection_signature_sha256"]) != signature
        or str(dwr.audit["selection_signature_sha256"]) != signature
    ):
        raise ValueError("p7 trace-shadow component signatures disagree")
    orbit_dimensions = {node.dimension for node in orbit_closure.selected}
    available_dimensions = {
        *(1 for _edge in space.selected_edges),
        *(2 for _face in space.selected_faces),
    }
    if not orbit_dimensions.issubset(available_dimensions):
        raise ValueError(
            "Floquet orbit evidence selects a trace dimension absent "
            "from the local shadow"
        )
    component_checks = {
        "element_exact_sequence_component": (
            space.audit["component_pass"] is True
        ),
        "periodic_orbit_component_closed": (
            orbit_closure.audit["component_pass"] is True
            and orbit_closure.audit["all_requested_orbits_closed"] is True
        ),
        "local_schur_component": (
            schur.audit["component_pass"] is True
        ),
        "local_59_goal_dwr_component": (
            dwr.audit["component_pass"] is True
            and dwr.audit["goal_count"] == _FORMAL_GOAL_COUNT
        ),
        "inactive_p7_modes_not_globally_numbered": all(
            record["inactive_p7_modes_globally_numbered"] is False
            for record in (space.audit, orbit_closure.audit, schur.audit, dwr.audit)
        ),
    }
    if not all(component_checks.values()):
        failures = [
            name for name, passed in component_checks.items() if not passed
        ]
        raise RuntimeError(
            "p7 trace-shadow component evidence did not close: "
            + ", ".join(failures)
        )
    core = {
        "schema_version": "task035e.closed-p7-trace-shadow-evidence.v1",
        "status": "component_closed_formal_coverage_incomplete",
        "component_checks_pass": True,
        "formal_gate_status": "unknown",
        "coverage_status": "incomplete",
        "measured_pass": False,
        "source_sha": clean_source,
        "leaf_identity_sha256": leaf_sha,
        "selection_signature_sha256": signature,
        "orbit_sha256": orbit_closure.audit["orbit_sha256"],
        "input_tensor_sha256": schur.audit["input_tensor_sha256"],
        "input_rhs_sha256": schur.audit["input_rhs_sha256"],
        "schur_tensor_sha256": schur.audit["schur_tensor_sha256"],
        "current_p6_sha256": dwr.audit["current_p6_sha256"],
        "goal_gradients_sha256": dwr.audit["goal_gradients_sha256"],
        "signed_contributions_sha256": dwr.audit[
            "signed_contributions_sha256"
        ],
        "component_checks": component_checks,
        "actual_multilevel_plan_binding_status": "unknown",
        "mpi8_partition_identity_status": "unknown",
        "physical_periodic_geometry_binding_status": (
            orbit_closure.audit["geometry_binding_status"]
        ),
        "p6_saturation_status": "unknown",
        "p6_saturation_measured_pass": False,
        "can_satisfy_f1_alone": False,
        "production_degrees_unchanged": [4, 5, 6],
        "shadow_only": True,
        "inactive_p7_modes_globally_numbered": False,
        "selectable_as_production": False,
        "next_production_plan": None,
        "ordinary_default_changed": False,
        "heavy_pde_run": False,
    }
    return MappingProxyType(
        core | {"evidence_sha256": _payload_sha256(core)}
    )


__all__ = [
    "P7EntityComplement",
    "P7FloquetTraceRelation",
    "P7TraceEntityKey",
    "P7TraceOrbitClosure",
    "P7TraceShadowCatalog",
    "SelectiveP7TraceShadowDWR",
    "SelectiveP7TraceShadowSchur",
    "SelectiveP7TraceShadowSpace",
    "build_closed_p7_trace_shadow_evidence",
    "build_p7_trace_shadow_catalog",
    "build_selective_p7_trace_shadow_space",
    "close_p7_trace_floquet_orbits",
    "condense_selective_p7_trace_shadow_tensor",
    "evaluate_selective_p7_trace_shadow_dwr",
]
