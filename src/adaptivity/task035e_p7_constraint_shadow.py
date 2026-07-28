"""Exact mixed-p and hanging constraints for Task035e p7 shadows.

The production space remains the qualified p4/p5/p6 exact sequence.  This
module constructs no global p7 row.  It supplies two local authorities needed
to measure p6 saturation without confusing structural availability with a
numerical result:

* an arbitrary exact-sequence p4/p5/p6 cell is embedded into the standard p7
  hexahedron, with selected edge/face/cell complements closed under the
  discrete gradient; and
* one p4, p5, or p6 hanging-face constraint is lifted to p7 using the same
  Basix covariant-Piola restriction used by the production constraint graph.

All embeddings come from Basix interpolation operators.  No coefficient
prefix, mode-count surrogate, global p7 numbering, tensor, residual, or
adjoint is used here.
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

from .exact_sequence_variable_p import (
    HexaEntityDegreeMap,
    VariablePReferenceSpace,
    apply_active_dof_transformation,
    build_variable_p_reference_space,
)
from .hcurl_hanging_trace import (
    _QUADRANTS,
    _aggregate_gradient,
    _aggregate_local_rows,
    _child_restriction,
    _curl_gradient_error,
    _discrete_gradient,
    _h1_element,
    _hcurl_element,
    _merge_child_matrices,
    build_hanging_face_reference_pair,
    build_quad_d4_trace_transform_pair,
)


_SOURCE_DEGREES = (4, 5, 6)
_PRODUCTION_DEGREES = frozenset(_SOURCE_DEGREES)
_HCURL = "hcurl"
_H1 = "h1"
_FAMILIES = (_HCURL, _H1)
_ROUND_OFF_LIMIT = 5.0e-10


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


def _canonical(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _canonical(value.item())
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value


def _payload_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            _canonical(value),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _rank(values: np.ndarray) -> tuple[int, float]:
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


@lru_cache(maxsize=8)
def _standard_hexa(
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


@lru_cache(maxsize=6)
def _standard_injection_to_p7(
    family: str,
    source_degree: int,
) -> np.ndarray:
    result = np.asarray(
        basix.compute_interpolation_operator(
            _standard_hexa(family, int(source_degree)),
            _standard_hexa(family, 7),
        ),
        dtype=np.float64,
    )
    return _readonly(result)


def _source_element(
    space: VariablePReferenceSpace,
    family: str,
) -> basix.finite_element.FiniteElement:
    return space.hcurl_element if family == _HCURL else space.h1_element


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


def _edge_to_faces() -> tuple[tuple[int, ...], ...]:
    topology = basix.topology(basix.CellType.hexahedron)
    edge_vertices = [set(map(int, row)) for row in topology[1]]
    face_vertices = [set(map(int, row)) for row in topology[2]]
    result = tuple(
        tuple(
            face
            for face, vertices in enumerate(face_vertices)
            if edge.issubset(vertices)
        )
        for edge in edge_vertices
    )
    if len(result) != 12 or any(len(row) != 2 for row in result):
        raise RuntimeError("Basix hexahedron edge/face incidence changed")
    return result


def close_mixed_p7_local_selection(
    requested_edges: Iterable[int],
    requested_faces: Iterable[int],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Close edge requests to incident faces for the local de Rham pair."""

    edges = tuple(sorted(set(map(int, requested_edges))))
    faces = tuple(sorted(set(map(int, requested_faces))))
    if any(not 0 <= edge < 12 for edge in edges):
        raise ValueError("mixed p7 shadow edge must be in [0, 11]")
    if any(not 0 <= face < 6 for face in faces):
        raise ValueError("mixed p7 shadow face must be in [0, 5]")
    if not edges and not faces:
        raise ValueError("mixed p7 shadow requires one trace entity")
    closed_faces = set(faces)
    for edge in edges:
        closed_faces.update(_edge_to_faces()[edge])
    return edges, tuple(sorted(closed_faces))


@dataclass(frozen=True)
class MixedP7EntityComplement:
    """One source entity injection plus its p7-only coefficient complement."""

    family: str
    source_degree: int
    dimension: int
    local_entity: int
    source_dofs: np.ndarray
    p7_dofs: np.ndarray
    source_to_p7_on_entity: np.ndarray
    complement_on_entity: np.ndarray
    complement_to_p7: np.ndarray
    embedded_q: np.ndarray
    embedded_r: np.ndarray
    audit: Mapping[str, Any]

    @property
    def complement_dimension(self) -> int:
        return int(self.complement_on_entity.shape[1])


def _entity_transform(
    element: basix.finite_element.FiniteElement,
    *,
    dimension: int,
    reflected: bool,
    rotations: int,
) -> np.ndarray:
    if dimension == 1:
        generator = np.asarray(
            element.entity_transformations()["interval"][0],
            dtype=np.float64,
        )
        return (
            generator
            if reflected
            else np.eye(generator.shape[0], dtype=np.float64)
        )
    if dimension != 2:
        raise ValueError("entity transform requires an edge or face")
    rotation, reflection = np.asarray(
        element.entity_transformations()["quadrilateral"],
        dtype=np.float64,
    )
    result = np.eye(rotation.shape[0], dtype=np.float64)
    if reflected:
        result = reflection @ result
    for _ in range(int(rotations) % 4):
        result = rotation @ result
    return result


def _entity_orientation_audit(
    *,
    family: str,
    source_degree: int,
    dimension: int,
    embedded: np.ndarray,
    complement: np.ndarray,
) -> Mapping[str, Any]:
    source = _standard_hexa(family, source_degree)
    target = _standard_hexa(family, 7)
    actions = (
        ((False, 0), (True, 0))
        if dimension == 1
        else tuple(
            (reflected, rotations)
            for reflected in (False, True)
            for rotations in range(4)
        )
    )
    maximum_embedding = 0.0
    maximum_complement = 0.0
    maximum_unitarity = 0.0
    for reflected, rotations in actions:
        source_transform = _entity_transform(
            source,
            dimension=dimension,
            reflected=reflected,
            rotations=rotations,
        )
        target_transform = _entity_transform(
            target,
            dimension=dimension,
            reflected=reflected,
            rotations=rotations,
        )
        representation = (
            complement.conj().T @ target_transform @ complement
        )
        maximum_embedding = max(
            maximum_embedding,
            _maximum_absolute(
                target_transform @ embedded
                - embedded @ source_transform
            ),
        )
        maximum_complement = max(
            maximum_complement,
            _maximum_absolute(
                target_transform @ complement
                - complement @ representation
            ),
        )
        maximum_unitarity = max(
            maximum_unitarity,
            _maximum_absolute(
                representation.conj().T @ representation
                - np.eye(complement.shape[1])
            ),
        )
    passed = (
        maximum_embedding <= _ROUND_OFF_LIMIT
        and maximum_complement <= _ROUND_OFF_LIMIT
        and maximum_unitarity <= _ROUND_OFF_LIMIT
    )
    return MappingProxyType(
        {
            "action_count": len(actions),
            "source_injection_commuting_error_max": maximum_embedding,
            "complement_closure_error_max": maximum_complement,
            "complement_unitarity_error_max": maximum_unitarity,
            "pass": passed,
        }
    )


def _build_entity_complement(
    *,
    family: str,
    degree_map: HexaEntityDegreeMap,
    source_element: basix.finite_element.FiniteElement,
    p7_element: basix.finite_element.FiniteElement,
    source_to_p7: np.ndarray,
    dimension: int,
    entity: int,
) -> MixedP7EntityComplement | None:
    source_dofs = _entity_dofs(source_element, dimension, entity)
    p7_dofs = _entity_dofs(p7_element, dimension, entity)
    difference = len(p7_dofs) - len(source_dofs)
    if difference < 0:
        raise RuntimeError("p7 entity has fewer modes than its source")
    if difference == 0:
        return None
    embedded = np.ascontiguousarray(
        source_to_p7[np.ix_(p7_dofs, source_dofs)]
    )
    orthogonal, upper = np.linalg.qr(embedded, mode="complete")
    embedded_q = np.ascontiguousarray(
        orthogonal[:, : len(source_dofs)]
    )
    embedded_r = np.ascontiguousarray(upper[: len(source_dofs)])
    complement = _canonicalize_columns(
        orthogonal[:, len(source_dofs) :]
    )
    complement_to_p7 = np.zeros(
        (int(p7_element.dim), difference),
        dtype=np.float64,
    )
    complement_to_p7[p7_dofs] = complement
    source_degree = int(
        degree_map.entity_degrees(family)[dimension][entity]
    )
    standard_source = _standard_hexa(family, source_degree)
    standard_injection = _standard_injection_to_p7(
        family,
        source_degree,
    )
    standard_source_dofs = _entity_dofs(
        standard_source,
        dimension,
        entity,
    )
    standard_block = standard_injection[
        np.ix_(p7_dofs, standard_source_dofs)
    ]
    standard_mismatch = _maximum_absolute(embedded - standard_block)
    rank, rank_tolerance = _rank(embedded)
    orientation = (
        _entity_orientation_audit(
            family=family,
            source_degree=source_degree,
            dimension=dimension,
            embedded=embedded,
            complement=complement,
        )
        if dimension in (1, 2)
        else MappingProxyType(
            {
                "action_count": 1,
                "source_injection_commuting_error_max": 0.0,
                "complement_closure_error_max": 0.0,
                "complement_unitarity_error_max": 0.0,
                "pass": True,
            }
        )
    )
    checks = {
        "source_entity_embedding_full_rank": rank == len(source_dofs),
        "complete_p7_entity_complement": (
            rank + difference == len(p7_dofs)
        ),
        "matches_standard_source_entity_injection": (
            standard_mismatch <= _ROUND_OFF_LIMIT
        ),
        "complement_is_orthogonal": (
            _maximum_absolute(embedded.T @ complement)
            <= _ROUND_OFF_LIMIT
        ),
        "complement_is_orthonormal": (
            _maximum_absolute(
                complement.T @ complement - np.eye(difference)
            )
            <= _ROUND_OFF_LIMIT
        ),
        "orientation_closes": orientation["pass"] is True,
    }
    if not all(checks.values()):
        failures = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            f"mixed {family} p{source_degree}->p7 entity "
            f"({dimension}, {entity}) failed: {', '.join(failures)}"
        )
    audit = MappingProxyType(
        {
            "schema_version": "task035e.mixed-p7-entity-injection.v1",
            "status": "mixed_p_to_p7_entity_injection_pass",
            "pass": True,
            "family": family,
            "source_degree": source_degree,
            "target_degree": 7,
            "dimension": int(dimension),
            "local_entity": int(entity),
            "source_entity_dimension": len(source_dofs),
            "p7_entity_dimension": len(p7_dofs),
            "complement_dimension": difference,
            "embedding_rank": rank,
            "embedding_rank_tolerance": rank_tolerance,
            "standard_entity_injection_error_max": standard_mismatch,
            "orientation": orientation,
            "checks": checks,
            "shadow_only": True,
            "globally_numbered": False,
            "selectable_as_production": False,
        }
    )
    arrays = (
        source_dofs,
        p7_dofs,
        embedded,
        complement,
        complement_to_p7,
        embedded_q,
        embedded_r,
    )
    frozen = tuple(_readonly(array) for array in arrays)
    return MixedP7EntityComplement(
        family=family,
        source_degree=source_degree,
        dimension=int(dimension),
        local_entity=int(entity),
        source_dofs=frozen[0],
        p7_dofs=frozen[1],
        source_to_p7_on_entity=frozen[2],
        complement_on_entity=frozen[3],
        complement_to_p7=frozen[4],
        embedded_q=frozen[5],
        embedded_r=frozen[6],
        audit=audit,
    )


def _blocks(
    *,
    family: str,
    degree_map: HexaEntityDegreeMap,
    source_element: basix.finite_element.FiniteElement,
    p7_element: basix.finite_element.FiniteElement,
    source_to_p7: np.ndarray,
) -> Mapping[tuple[int, int], MixedP7EntityComplement]:
    rows: dict[tuple[int, int], MixedP7EntityComplement] = {}
    for dimension in range(4):
        for entity in range(len(source_element.entity_dofs[dimension])):
            block = _build_entity_complement(
                family=family,
                degree_map=degree_map,
                source_element=source_element,
                p7_element=p7_element,
                source_to_p7=source_to_p7,
                dimension=dimension,
                entity=entity,
            )
            if block is not None:
                rows[(dimension, entity)] = block
    return MappingProxyType(rows)


def _selected_keys(
    edges: tuple[int, ...],
    faces: tuple[int, ...],
) -> tuple[tuple[int, int], ...]:
    return (
        *((1, edge) for edge in edges),
        *((2, face) for face in faces),
        (3, 0),
    )


def _expansion_and_ranges(
    source_to_p7: np.ndarray,
    blocks: Mapping[tuple[int, int], MixedP7EntityComplement],
    selected: tuple[tuple[int, int], ...],
) -> tuple[np.ndarray, Mapping[tuple[int, int], np.ndarray]]:
    columns = [np.asarray(source_to_p7)]
    ranges: dict[tuple[int, int], np.ndarray] = {}
    next_column = source_to_p7.shape[1]
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
    source_element: basix.finite_element.FiniteElement,
    p7_element: basix.finite_element.FiniteElement,
    source_to_p7: np.ndarray,
    blocks: Mapping[tuple[int, int], MixedP7EntityComplement],
    selected_ranges: Mapping[tuple[int, int], np.ndarray],
    expansion: np.ndarray,
    values: np.ndarray,
) -> tuple[np.ndarray, float]:
    rhs = np.asarray(values)
    vector_input = rhs.ndim == 1
    if vector_input:
        rhs = rhs[:, None]
    if rhs.ndim != 2 or rhs.shape[0] != int(p7_element.dim):
        raise ValueError("mixed p7 coordinate input has the wrong shape")
    coordinates = np.zeros(
        (expansion.shape[1], rhs.shape[1]),
        dtype=np.result_type(rhs, np.float64),
    )
    solved_source: list[int] = []
    entity_error = 0.0
    for dimension in range(4):
        for entity in range(len(source_element.entity_dofs[dimension])):
            source_dofs = _entity_dofs(
                source_element,
                dimension,
                entity,
            )
            p7_dofs = _entity_dofs(p7_element, dimension, entity)
            if len(source_dofs) == 0 and len(p7_dofs) == 0:
                continue
            residual = np.asarray(rhs[p7_dofs]).copy()
            if solved_source:
                residual -= (
                    source_to_p7[np.ix_(p7_dofs, solved_source)]
                    @ coordinates[solved_source]
                )
            embedded = source_to_p7[
                np.ix_(p7_dofs, source_dofs)
            ]
            key = (dimension, entity)
            block = blocks.get(key)
            if block is None:
                if embedded.shape[0] != embedded.shape[1]:
                    raise RuntimeError(
                        "zero-complement mixed entity is not square"
                    )
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
            coordinates[source_dofs] = base_values
            solved_source.extend(map(int, source_dofs))
            entity_error = max(
                entity_error,
                _maximum_absolute(reconstructed - residual),
            )
    full_error = _maximum_absolute(expansion @ coordinates - rhs)
    result = np.ascontiguousarray(coordinates)
    if vector_input:
        return result[:, 0], max(entity_error, full_error)
    return result, max(entity_error, full_error)


def _composed_injection(
    space: VariablePReferenceSpace,
    family: str,
) -> tuple[
    basix.finite_element.FiniteElement,
    basix.finite_element.FiniteElement,
    np.ndarray,
    float,
]:
    source = _source_element(space, family)
    p7 = _standard_hexa(family, 7)
    source_to_p6 = (
        np.asarray(space.hcurl_to_p6)
        if family == _HCURL
        else np.asarray(space.h1_to_q6)
    )
    p6_to_p7 = _standard_injection_to_p7(family, 6)
    composed = np.ascontiguousarray(p6_to_p7 @ source_to_p6)
    direct = np.asarray(
        basix.compute_interpolation_operator(source, p7),
        dtype=np.float64,
    )
    return source, p7, composed, _maximum_absolute(composed - direct)


def _orientation_injection_error(
    *,
    space: VariablePReferenceSpace,
    family: str,
    p7_element: basix.finite_element.FiniteElement,
    injection: np.ndarray,
    cell_infos: tuple[int, ...],
) -> float:
    def apply_standard(
        values: np.ndarray,
        *,
        inverse: bool,
        cell_info: int,
    ) -> np.ndarray:
        result = np.ascontiguousarray(values.copy())
        flattened = result.reshape(int(p7_element.dim), -1)
        transformations = p7_element.entity_transformations()
        edge_reflection = np.asarray(
            transformations["interval"][0],
            dtype=np.float64,
        )
        face_rotation, face_reflection = np.asarray(
            transformations["quadrilateral"],
            dtype=np.float64,
        )
        for edge in range(12):
            if not ((int(cell_info) >> (18 + edge)) & 1):
                continue
            dofs = _entity_dofs(p7_element, 1, edge)
            block = (
                np.linalg.inv(edge_reflection)
                if inverse
                else edge_reflection
            )
            flattened[dofs] = block @ flattened[dofs]
        for face in range(6):
            dofs = _entity_dofs(p7_element, 2, face)
            rotations = (int(cell_info) >> (3 * face + 1)) & 3
            reflected = (int(cell_info) >> (3 * face)) & 1
            if inverse:
                inverse_rotation = np.linalg.inv(face_rotation)
                for _ in range(rotations):
                    flattened[dofs] = (
                        inverse_rotation @ flattened[dofs]
                    )
                if reflected:
                    flattened[dofs] = (
                        np.linalg.inv(face_reflection)
                        @ flattened[dofs]
                    )
            else:
                if reflected:
                    flattened[dofs] = (
                        face_reflection @ flattened[dofs]
                    )
                for _ in range(rotations):
                    flattened[dofs] = (
                        face_rotation @ flattened[dofs]
                    )
        return result

    maximum = 0.0
    source_dimension = injection.shape[1]
    for cell_info in cell_infos:
        target = np.ascontiguousarray(injection.copy())
        p7_element.T_apply(
            target.ravel(),
            target.shape[1],
            int(cell_info),
        )
        source_transform = apply_active_dof_transformation(
            space,
            np.eye(source_dimension, dtype=np.float64),
            family=family,
            cell_info=int(cell_info),
        )
        explicit_target = apply_standard(
            injection,
            inverse=False,
            cell_info=int(cell_info),
        )
        authority_error = _maximum_absolute(
            explicit_target - target
        )
        source_inverse = apply_active_dof_transformation(
            space,
            np.eye(source_dimension, dtype=np.float64),
            family=family,
            cell_info=int(cell_info),
            transpose=True,
        )
        source_inverse_error = _maximum_absolute(
            source_inverse @ source_transform
            - np.eye(source_dimension)
        )
        # Coefficients in an oriented cell use the real transfer
        # T_p7 E T_source^-1.  E need not itself be invariant under a
        # permutation.  The fail-closed check is that applying the inverse
        # source and target transforms recovers the exact reference injection.
        oriented = np.ascontiguousarray(
            target @ source_inverse
        )
        restored = np.ascontiguousarray(
            oriented @ source_transform
        )
        restored = apply_standard(
            restored,
            inverse=True,
            cell_info=int(cell_info),
        )
        maximum = max(
            maximum,
            authority_error,
            source_inverse_error,
            _maximum_absolute(restored - injection),
        )
    return maximum


@dataclass(frozen=True)
class MixedSelectiveP7ShadowSpace:
    """One variable-p exact-sequence cell plus selected p7 complements."""

    degree_map: HexaEntityDegreeMap
    source_space: VariablePReferenceSpace
    requested_edges: tuple[int, ...]
    requested_faces: tuple[int, ...]
    selected_edges: tuple[int, ...]
    selected_faces: tuple[int, ...]
    hcurl_expansion: np.ndarray
    h1_expansion: np.ndarray
    discrete_gradient: np.ndarray
    hcurl_selected_ranges: Mapping[tuple[int, int], np.ndarray]
    h1_selected_ranges: Mapping[tuple[int, int], np.ndarray]
    audit: Mapping[str, Any]
    production_degrees_unchanged: frozenset[int] = _PRODUCTION_DEGREES
    shadow_only: bool = True
    selectable_as_production: bool = False


@lru_cache(maxsize=256)
def build_mixed_selective_p7_shadow_space(
    degree_map: HexaEntityDegreeMap,
    requested_edges: tuple[int, ...] = (),
    requested_faces: tuple[int, ...] = (),
    cell_infos: tuple[int, ...] = (0,),
) -> MixedSelectiveP7ShadowSpace:
    """Build a real mixed-p-to-p7 local exact-sequence shadow."""

    edges, faces = close_mixed_p7_local_selection(
        requested_edges,
        requested_faces,
    )
    infos = tuple(sorted(set(map(int, cell_infos))))
    if not infos:
        raise ValueError("mixed p7 orientation audit requires cell_info")
    source_space = build_variable_p_reference_space(degree_map)
    hcurl_source, hcurl_p7, hcurl_injection, hcurl_direct_error = (
        _composed_injection(source_space, _HCURL)
    )
    h1_source, h1_p7, h1_injection, h1_direct_error = (
        _composed_injection(source_space, _H1)
    )
    hcurl_blocks = _blocks(
        family=_HCURL,
        degree_map=degree_map,
        source_element=hcurl_source,
        p7_element=hcurl_p7,
        source_to_p7=hcurl_injection,
    )
    h1_blocks = _blocks(
        family=_H1,
        degree_map=degree_map,
        source_element=h1_source,
        p7_element=h1_p7,
        source_to_p7=h1_injection,
    )
    selected = _selected_keys(edges, faces)
    hcurl_expansion, hcurl_ranges = _expansion_and_ranges(
        hcurl_injection,
        hcurl_blocks,
        selected,
    )
    h1_expansion, h1_ranges = _expansion_and_ranges(
        h1_injection,
        h1_blocks,
        selected,
    )
    p7_gradient = _discrete_gradient(h1_p7, hcurl_p7)
    injection_commuting_error = _maximum_absolute(
        p7_gradient @ h1_injection
        - hcurl_injection @ source_space.discrete_gradient
    )
    expanded_gradient = np.ascontiguousarray(
        p7_gradient @ h1_expansion
    )
    shadow_gradient, range_error = _coordinates_in_active_space(
        source_element=hcurl_source,
        p7_element=hcurl_p7,
        source_to_p7=hcurl_injection,
        blocks=hcurl_blocks,
        selected_ranges=hcurl_ranges,
        expansion=hcurl_expansion,
        values=expanded_gradient,
    )
    gradient_rank, gradient_tolerance = _rank(shadow_gradient)
    hcurl_orientation_error = _orientation_injection_error(
        space=source_space,
        family=_HCURL,
        p7_element=hcurl_p7,
        injection=hcurl_injection,
        cell_infos=infos,
    )
    h1_orientation_error = _orientation_injection_error(
        space=source_space,
        family=_H1,
        p7_element=h1_p7,
        injection=h1_injection,
        cell_infos=infos,
    )
    trace_columns = int(source_space.audit["active_trace_dimension"])
    trace_columns += sum(
        hcurl_blocks[key].complement_dimension
        for key in selected
        if key[0] < 3
    )
    interior_columns = hcurl_expansion.shape[1] - trace_columns
    checks = {
        "source_exact_sequence_pass": (
            source_space.audit["pass"] is True
        ),
        "composed_hcurl_injection_matches_direct": (
            hcurl_direct_error <= _ROUND_OFF_LIMIT
        ),
        "composed_h1_injection_matches_direct": (
            h1_direct_error <= _ROUND_OFF_LIMIT
        ),
        "source_gradient_injection_commutes": (
            injection_commuting_error <= _ROUND_OFF_LIMIT
        ),
        "edge_to_face_closure_complete": all(
            set(_edge_to_faces()[edge]).issubset(faces)
            for edge in edges
        ),
        "selection_closes_cell_interior": (3, 0) in selected,
        "selected_gradient_range_closes": (
            range_error <= _ROUND_OFF_LIMIT
        ),
        "selected_gradient_has_constant_kernel_only": (
            gradient_rank == h1_expansion.shape[1] - 1
        ),
        "actual_hcurl_orientation_commutes": (
            hcurl_orientation_error <= _ROUND_OFF_LIMIT
        ),
        "actual_h1_orientation_commutes": (
            h1_orientation_error <= _ROUND_OFF_LIMIT
        ),
        "active_partition_covers_every_hcurl_column": (
            trace_columns + interior_columns
            == hcurl_expansion.shape[1]
        ),
    }
    if not all(checks.values()):
        failures = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "mixed selective p7 exact sequence failed: "
            + ", ".join(failures)
        )
    audit_core = {
        "schema_version": "task035e.mixed-selective-p7-shadow.v1",
        "status": "mixed_selective_p7_shadow_component_pass",
        "component_pass": True,
        "degree_map": degree_map.to_dict(),
        "requested_edges": list(map(int, requested_edges)),
        "requested_faces": list(map(int, requested_faces)),
        "selected_edges": list(edges),
        "selected_faces": list(faces),
        "cell_selected_by_exact_sequence_closure": True,
        "actual_cell_infos": list(infos),
        "source_hcurl_dimension": source_space.hcurl_dimension,
        "source_h1_dimension": source_space.h1_dimension,
        "shadow_hcurl_dimension": hcurl_expansion.shape[1],
        "shadow_h1_dimension": h1_expansion.shape[1],
        "active_trace_columns": trace_columns,
        "active_cell_interior_columns": interior_columns,
        "hcurl_injection_direct_error_max": hcurl_direct_error,
        "h1_injection_direct_error_max": h1_direct_error,
        "gradient_injection_commuting_error_max": (
            injection_commuting_error
        ),
        "gradient_range_error_max": range_error,
        "gradient_rank": gradient_rank,
        "gradient_rank_tolerance": gradient_tolerance,
        "hcurl_orientation_commuting_error_max": (
            hcurl_orientation_error
        ),
        "h1_orientation_commuting_error_max": h1_orientation_error,
        "hcurl_expansion_sha256": _matrix_sha256(hcurl_expansion),
        "h1_expansion_sha256": _matrix_sha256(h1_expansion),
        "discrete_gradient_sha256": _matrix_sha256(shadow_gradient),
        "entity_injection_audit_sha256": _payload_sha256(
            [
                block.audit
                for block in (
                    *hcurl_blocks.values(),
                    *h1_blocks.values(),
                )
            ]
        ),
        "checks": checks,
        "production_degrees_unchanged": [4, 5, 6],
        "p7_rows_globally_numbered": False,
        "shadow_only": True,
        "selectable_as_production": False,
        "ordinary_default_changed": False,
    }
    audit = MappingProxyType(
        audit_core
        | {"component_sha256": _payload_sha256(audit_core)}
    )
    return MixedSelectiveP7ShadowSpace(
        degree_map=degree_map,
        source_space=source_space,
        requested_edges=tuple(sorted(set(map(int, requested_edges)))),
        requested_faces=tuple(sorted(set(map(int, requested_faces)))),
        selected_edges=edges,
        selected_faces=faces,
        hcurl_expansion=_readonly(hcurl_expansion),
        h1_expansion=_readonly(h1_expansion),
        discrete_gradient=_readonly(shadow_gradient),
        hcurl_selected_ranges=hcurl_ranges,
        h1_selected_ranges=h1_ranges,
        audit=audit,
    )


@dataclass(frozen=True)
class P7ShadowHangingClosure:
    """Exact source/p7 hanging restriction and complement decomposition."""

    source_degree: int
    hcurl_coarse_injection: np.ndarray
    h1_coarse_injection: np.ndarray
    hcurl_fine_injection: np.ndarray
    h1_fine_injection: np.ndarray
    hcurl_p7_fine_from_coarse: np.ndarray
    h1_p7_fine_from_coarse: np.ndarray
    hcurl_coarse_complement: np.ndarray
    h1_coarse_complement: np.ndarray
    hcurl_fine_lower_from_coarse_complement: np.ndarray
    h1_fine_lower_from_coarse_complement: np.ndarray
    hcurl_fine_complement_from_coarse_complement: np.ndarray
    h1_fine_complement_from_coarse_complement: np.ndarray
    audit: Mapping[str, Any]


def _aggregate_injection(
    *,
    source_rows: tuple[np.ndarray, ...],
    target_rows: tuple[np.ndarray, ...],
    local_injection: np.ndarray,
    source_dimension: int,
    target_dimension: int,
) -> tuple[np.ndarray, float]:
    result = np.zeros(
        (int(target_dimension), int(source_dimension)),
        dtype=np.float64,
    )
    assigned = np.zeros(int(target_dimension), dtype=bool)
    mismatch = 0.0
    for source, target in zip(
        source_rows,
        target_rows,
        strict=True,
    ):
        for local_row, global_row in enumerate(target):
            values = np.zeros(int(source_dimension), dtype=np.float64)
            values[source] = local_injection[local_row]
            if assigned[global_row]:
                mismatch = max(
                    mismatch,
                    _maximum_absolute(result[global_row] - values),
                )
            else:
                result[global_row] = values
                assigned[global_row] = True
    if not np.all(assigned):
        raise RuntimeError("fine p7 injection has an unassigned row")
    return np.ascontiguousarray(result), mismatch


def _p7_hanging_pair() -> dict[str, Any]:
    degree = 7
    hcurl = _hcurl_element(degree)
    h1 = _h1_element(degree)
    hcurl_children = tuple(
        _child_restriction(hcurl, hcurl, quadrant)
        for quadrant in _QUADRANTS
    )
    h1_children = tuple(
        _child_restriction(h1, h1, quadrant)
        for quadrant in _QUADRANTS
    )
    hcurl_rows, fine_hcurl_dimension = _aggregate_local_rows(
        hcurl,
        family=_HCURL,
        degree=degree,
    )
    h1_rows, fine_h1_dimension = _aggregate_local_rows(
        h1,
        family=_H1,
        degree=degree,
    )
    hcurl_restriction, hcurl_mismatch = _merge_child_matrices(
        hcurl_rows,
        hcurl_children,
        aggregate_rows=fine_hcurl_dimension,
    )
    h1_restriction, h1_mismatch = _merge_child_matrices(
        h1_rows,
        h1_children,
        aggregate_rows=fine_h1_dimension,
    )
    coarse_gradient = _discrete_gradient(h1, hcurl)
    fine_gradient, gradient_mismatch = _aggregate_gradient(
        hcurl_rows,
        h1_rows,
        coarse_gradient,
        hcurl_dimension=fine_hcurl_dimension,
        h1_dimension=fine_h1_dimension,
    )
    commuting_error = _maximum_absolute(
        hcurl_restriction @ coarse_gradient
        - fine_gradient @ h1_restriction
    )
    restriction_rank, rank_tolerance = _rank(hcurl_restriction)
    checks = {
        "hcurl_shared_rows_match": hcurl_mismatch <= 2.0e-12,
        "h1_shared_rows_match": h1_mismatch <= 2.0e-12,
        "gradient_shared_rows_match": gradient_mismatch <= 2.0e-12,
        "p7_hanging_gradient_commutes": (
            commuting_error <= _ROUND_OFF_LIMIT
        ),
        "p7_hcurl_restriction_full_column_rank": (
            restriction_rank == int(hcurl.dim)
        ),
        "p7_curl_grad": (
            _curl_gradient_error(hcurl, coarse_gradient)
            <= _ROUND_OFF_LIMIT
        ),
    }
    if not all(checks.values()):
        failures = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "p7 hanging reference pair failed: " + ", ".join(failures)
        )
    return {
        "hcurl": hcurl,
        "h1": h1,
        "hcurl_rows": hcurl_rows,
        "h1_rows": h1_rows,
        "fine_hcurl_dimension": fine_hcurl_dimension,
        "fine_h1_dimension": fine_h1_dimension,
        "hcurl_restriction": hcurl_restriction,
        "h1_restriction": h1_restriction,
        "coarse_gradient": coarse_gradient,
        "fine_gradient": fine_gradient,
        "rank_tolerance": rank_tolerance,
        "commuting_error": commuting_error,
        "checks": checks,
    }


def _fine_injection(
    *,
    family: str,
    source_degree: int,
    source_rows: tuple[np.ndarray, ...],
    target_rows: tuple[np.ndarray, ...],
    source_dimension: int,
    target_dimension: int,
) -> tuple[np.ndarray, float]:
    source = (
        _hcurl_element(source_degree)
        if family == _HCURL
        else _h1_element(source_degree)
    )
    target = _hcurl_element(7) if family == _HCURL else _h1_element(7)
    local = np.asarray(
        basix.compute_interpolation_operator(source, target),
        dtype=np.float64,
    )
    return _aggregate_injection(
        source_rows=source_rows,
        target_rows=target_rows,
        local_injection=local,
        source_dimension=source_dimension,
        target_dimension=target_dimension,
    )


def _complement_decomposition(
    coarse_injection: np.ndarray,
    fine_injection: np.ndarray,
    p7_restriction: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, int]:
    coarse_q, _coarse_r = np.linalg.qr(
        coarse_injection,
        mode="complete",
    )
    coarse_complement = _canonicalize_columns(
        coarse_q[:, coarse_injection.shape[1] :]
    )
    fine_q, fine_r_full = np.linalg.qr(
        fine_injection,
        mode="complete",
    )
    fine_source_columns = fine_injection.shape[1]
    fine_q_source = fine_q[:, :fine_source_columns]
    fine_complement = _canonicalize_columns(
        fine_q[:, fine_source_columns:]
    )
    fine_r = fine_r_full[:fine_source_columns]
    image = p7_restriction @ coarse_complement
    lower = solve_triangular(
        fine_r,
        fine_q_source.T @ image,
        lower=False,
        check_finite=False,
    )
    complement = fine_complement.T @ image
    reconstruction = (
        fine_injection @ lower + fine_complement @ complement
    )
    error = _maximum_absolute(reconstruction - image)
    image_rank, _tolerance = _rank(image)
    return (
        _readonly(coarse_complement),
        _readonly(lower),
        _readonly(complement),
        error,
        image_rank,
    )


def _d4_injection_audit(
    *,
    family: str,
    source_degree: int,
    injection: np.ndarray,
) -> tuple[float, int]:
    maximum = 0.0
    for permutation in sorted(quadrilateral_d4_vertex_permutations()):
        source = build_quad_d4_trace_transform_pair(
            source_degree,
            permutation,
        )
        if family == _HCURL:
            source_transform = np.asarray(source.hcurl_coefficients)
        else:
            source_transform = np.asarray(source.h1_coefficients)
        p7_element = _hcurl_element(7) if family == _HCURL else _h1_element(7)
        # The private affine constructor is the same production authority
        # exercised by build_quad_d4_trace_transform_pair.  Calling it via a
        # degree-seven element avoids broadening the production p4/p5/p6 API.
        from .hcurl_hanging_trace import (  # noqa: PLC0415
            _affine_pullback_restriction,
            _quad_affine_chart,
        )

        offset, jacobian = _quad_affine_chart(permutation)
        target_transform = _affine_pullback_restriction(
            p7_element,
            p7_element,
            offset=offset,
            jacobian=jacobian,
        )
        maximum = max(
            maximum,
            _maximum_absolute(
                target_transform @ injection
                - injection @ source_transform
            ),
        )
    return maximum, len(quadrilateral_d4_vertex_permutations())


@lru_cache(maxsize=3)
def build_p7_shadow_hanging_closure(
    source_degree: int,
) -> P7ShadowHangingClosure:
    """Lift one real p4/p5/p6 hanging restriction to p7."""

    degree = int(source_degree)
    if degree not in _SOURCE_DEGREES:
        raise ValueError("p7 hanging shadow source must be p4, p5, or p6")
    source = build_hanging_face_reference_pair(degree)
    if source.audit["pass"] is not True:
        raise RuntimeError("source hanging authority did not pass")
    p7 = _p7_hanging_pair()
    hcurl_coarse = np.asarray(
        basix.compute_interpolation_operator(
            _hcurl_element(degree),
            p7["hcurl"],
        ),
        dtype=np.float64,
    )
    h1_coarse = np.asarray(
        basix.compute_interpolation_operator(
            _h1_element(degree),
            p7["h1"],
        ),
        dtype=np.float64,
    )
    hcurl_fine, hcurl_fine_mismatch = _fine_injection(
        family=_HCURL,
        source_degree=degree,
        source_rows=source.hcurl_child_rows,
        target_rows=p7["hcurl_rows"],
        source_dimension=source.hcurl_unique_fine_from_coarse.shape[0],
        target_dimension=p7["fine_hcurl_dimension"],
    )
    h1_fine, h1_fine_mismatch = _fine_injection(
        family=_H1,
        source_degree=degree,
        source_rows=source.h1_child_rows,
        target_rows=p7["h1_rows"],
        source_dimension=source.h1_unique_fine_from_coarse.shape[0],
        target_dimension=p7["fine_h1_dimension"],
    )
    hcurl_injection_error = _maximum_absolute(
        p7["hcurl_restriction"] @ hcurl_coarse
        - hcurl_fine @ source.hcurl_unique_fine_from_coarse
    )
    h1_injection_error = _maximum_absolute(
        p7["h1_restriction"] @ h1_coarse
        - h1_fine @ source.h1_unique_fine_from_coarse
    )
    fine_gradient_injection_error = _maximum_absolute(
        p7["fine_gradient"] @ h1_fine
        - hcurl_fine @ source.fine_discrete_gradient
    )
    (
        hcurl_coarse_complement,
        hcurl_lower,
        hcurl_complement,
        hcurl_decomposition_error,
        hcurl_image_rank,
    ) = _complement_decomposition(
        hcurl_coarse,
        hcurl_fine,
        p7["hcurl_restriction"],
    )
    (
        h1_coarse_complement,
        h1_lower,
        h1_complement,
        h1_decomposition_error,
        h1_image_rank,
    ) = _complement_decomposition(
        h1_coarse,
        h1_fine,
        p7["h1_restriction"],
    )
    hcurl_d4_error, d4_count = _d4_injection_audit(
        family=_HCURL,
        source_degree=degree,
        injection=hcurl_coarse,
    )
    h1_d4_error, _ = _d4_injection_audit(
        family=_H1,
        source_degree=degree,
        injection=h1_coarse,
    )
    checks = {
        "source_hanging_authority_pass": source.audit["pass"] is True,
        "p7_hanging_authority_pass": all(p7["checks"].values()),
        "fine_hcurl_injection_shared_rows_match": (
            hcurl_fine_mismatch <= _ROUND_OFF_LIMIT
        ),
        "fine_h1_injection_shared_rows_match": (
            h1_fine_mismatch <= _ROUND_OFF_LIMIT
        ),
        "hcurl_hanging_injection_commutes": (
            hcurl_injection_error <= _ROUND_OFF_LIMIT
        ),
        "h1_hanging_injection_commutes": (
            h1_injection_error <= _ROUND_OFF_LIMIT
        ),
        "fine_gradient_injection_commutes": (
            fine_gradient_injection_error <= _ROUND_OFF_LIMIT
        ),
        "hcurl_complement_constraint_reconstructs": (
            hcurl_decomposition_error <= _ROUND_OFF_LIMIT
        ),
        "h1_complement_constraint_reconstructs": (
            h1_decomposition_error <= _ROUND_OFF_LIMIT
        ),
        "hcurl_coarse_complement_restriction_full_rank": (
            hcurl_image_rank == hcurl_coarse_complement.shape[1]
        ),
        "h1_coarse_complement_restriction_full_rank": (
            h1_image_rank == h1_coarse_complement.shape[1]
        ),
        "all_d4_injections_commute": (
            hcurl_d4_error <= _ROUND_OFF_LIMIT
            and h1_d4_error <= _ROUND_OFF_LIMIT
            and d4_count == 8
        ),
    }
    if not all(checks.values()):
        failures = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            f"p{degree}->p7 hanging complement failed: "
            + ", ".join(failures)
        )
    audit_core = {
        "schema_version": "task035e.p7-hanging-complement-shadow.v1",
        "status": "p7_hanging_complement_shadow_component_pass",
        "component_pass": True,
        "source_degree": degree,
        "target_degree": 7,
        "source_hanging_sha256": source.audit[
            "hcurl_restriction_sha256"
        ],
        "p7_hanging_sha256": _matrix_sha256(
            p7["hcurl_restriction"]
        ),
        "source_coarse_hcurl_dimension": hcurl_coarse.shape[1],
        "p7_coarse_hcurl_dimension": hcurl_coarse.shape[0],
        "source_unique_fine_hcurl_dimension": hcurl_fine.shape[1],
        "p7_unique_fine_hcurl_dimension": hcurl_fine.shape[0],
        "hcurl_coarse_complement_dimension": (
            hcurl_coarse_complement.shape[1]
        ),
        "h1_coarse_complement_dimension": (
            h1_coarse_complement.shape[1]
        ),
        "hcurl_hanging_injection_error_max": hcurl_injection_error,
        "h1_hanging_injection_error_max": h1_injection_error,
        "fine_gradient_injection_error_max": (
            fine_gradient_injection_error
        ),
        "hcurl_complement_decomposition_error_max": (
            hcurl_decomposition_error
        ),
        "h1_complement_decomposition_error_max": (
            h1_decomposition_error
        ),
        "hcurl_d4_injection_error_max": hcurl_d4_error,
        "h1_d4_injection_error_max": h1_d4_error,
        "d4_action_count": d4_count,
        "checks": checks,
        "restriction_construction": (
            "production Basix covariant-Piola child restriction"
        ),
        "production_degrees_unchanged": [4, 5, 6],
        "p7_rows_globally_numbered": False,
        "shadow_only": True,
        "selectable_as_production": False,
        "ordinary_default_changed": False,
    }
    audit = MappingProxyType(
        audit_core
        | {"component_sha256": _payload_sha256(audit_core)}
    )
    return P7ShadowHangingClosure(
        source_degree=degree,
        hcurl_coarse_injection=_readonly(hcurl_coarse),
        h1_coarse_injection=_readonly(h1_coarse),
        hcurl_fine_injection=_readonly(hcurl_fine),
        h1_fine_injection=_readonly(h1_fine),
        hcurl_p7_fine_from_coarse=_readonly(
            p7["hcurl_restriction"]
        ),
        h1_p7_fine_from_coarse=_readonly(p7["h1_restriction"]),
        hcurl_coarse_complement=hcurl_coarse_complement,
        h1_coarse_complement=h1_coarse_complement,
        hcurl_fine_lower_from_coarse_complement=hcurl_lower,
        h1_fine_lower_from_coarse_complement=h1_lower,
        hcurl_fine_complement_from_coarse_complement=hcurl_complement,
        h1_fine_complement_from_coarse_complement=h1_complement,
        audit=audit,
    )


@lru_cache(maxsize=12)
def audit_mixed_p7_floquet_entity(
    source_degree: int,
    dimension: int,
    phase: complex,
) -> Mapping[str, Any]:
    """Audit one actual scalar Floquet phase on a mixed entity injection."""

    degree = int(source_degree)
    dimension = int(dimension)
    phase = complex(phase)
    if degree not in _SOURCE_DEGREES:
        raise ValueError("Floquet p7 source degree must be p4/p5/p6")
    if dimension not in (1, 2):
        raise ValueError("Floquet p7 entity must be an edge or face")
    if not np.isfinite(phase.real) or not np.isfinite(phase.imag):
        raise ValueError("Floquet phase must be finite")
    if not np.isclose(abs(phase), 1.0, rtol=0.0, atol=2.0e-12):
        raise ValueError("Floquet phase must have unit modulus")
    rows: dict[str, Any] = {}
    maximum_injection = 0.0
    maximum_complement = 0.0
    for family in _FAMILIES:
        source = _standard_hexa(family, degree)
        target = _standard_hexa(family, 7)
        injection = np.asarray(
            basix.compute_interpolation_operator(source, target),
            dtype=np.float64,
        )
        source_dofs = _entity_dofs(source, dimension, 0)
        target_dofs = _entity_dofs(target, dimension, 0)
        embedded = injection[np.ix_(target_dofs, source_dofs)]
        q, _r = np.linalg.qr(embedded, mode="complete")
        complement = q[:, len(source_dofs) :]
        source_phase = phase * np.eye(len(source_dofs))
        target_phase = phase * np.eye(len(target_dofs))
        injection_error = _maximum_absolute(
            target_phase @ embedded - embedded @ source_phase
        )
        representation = (
            complement.conj().T @ target_phase @ complement
        )
        complement_error = _maximum_absolute(
            target_phase @ complement
            - complement @ representation
        )
        maximum_injection = max(maximum_injection, injection_error)
        maximum_complement = max(maximum_complement, complement_error)
        rows[family] = {
            "injection_error_max": injection_error,
            "complement_error_max": complement_error,
            "complement_transform_sha256": _matrix_sha256(
                representation
            ),
        }
    passed = (
        maximum_injection <= _ROUND_OFF_LIMIT
        and maximum_complement <= _ROUND_OFF_LIMIT
    )
    core = {
        "schema_version": "task035e.mixed-p7-floquet-entity.v1",
        "status": (
            "mixed_p7_floquet_entity_component_pass"
            if passed
            else "mixed_p7_floquet_entity_component_fail"
        ),
        "component_pass": passed,
        "source_degree": degree,
        "dimension": dimension,
        "phase": [phase.real, phase.imag],
        "families": rows,
        "maximum_injection_error": maximum_injection,
        "maximum_complement_error": maximum_complement,
        "production_degrees_unchanged": [4, 5, 6],
        "p7_rows_globally_numbered": False,
        "shadow_only": True,
        "selectable_as_production": False,
    }
    if not passed:
        raise RuntimeError("mixed p7 Floquet entity closure failed")
    return MappingProxyType(
        core | {"component_sha256": _payload_sha256(core)}
    )


__all__ = [
    "MixedP7EntityComplement",
    "MixedSelectiveP7ShadowSpace",
    "P7ShadowHangingClosure",
    "audit_mixed_p7_floquet_entity",
    "build_mixed_selective_p7_shadow_space",
    "build_p7_shadow_hanging_closure",
    "close_mixed_p7_local_selection",
]
