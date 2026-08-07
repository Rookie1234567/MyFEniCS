"""Owner-independent scalar/vector auxiliary maps on the affine LOR edge space.

The maps in this module are compatibility primitives only.  They construct
the canonical H1 vertex expansion, the discrete gradient, and the straight
edge line-integral map for a nodal vector field.  They do not build an LOR
operator, smoother, hierarchy, factor, or PETSc object.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable

import numpy as np
import scipy.sparse as sp

from .static_lor_hcurl_transfer import (
    _HEX_EDGES,
    AffineLORParentTopology,
    LORSlabEdgeSpace,
)


PointKey = tuple[int, int, int]
EdgeKey = tuple[PointKey, PointKey]

_CSR_ZERO_TOLERANCE = 1.0e-14
_COMMUTING_TOLERANCE = 1.0e-12
_HEX_FACE_CYCLES: tuple[tuple[int, ...], ...] = (
    (0, 1, 3, 2),
    (0, 1, 5, 4),
    (0, 2, 6, 4),
    (1, 3, 7, 5),
    (2, 3, 7, 6),
    (4, 5, 7, 6),
)
_HEX_EDGE_BY_VERTICES = {
    frozenset(edge): edge_id for edge_id, edge in enumerate(_HEX_EDGES)
}


def _readonly_csr(values: sp.spmatrix | np.ndarray) -> sp.csr_matrix:
    matrix = sp.csr_matrix(values, dtype=np.complex128, copy=True)
    matrix.sum_duplicates()
    matrix.sort_indices()
    small = np.abs(matrix.data) <= _CSR_ZERO_TOLERANCE
    if np.any(small):
        matrix.data[small] = 0.0
        matrix.eliminate_zeros()
    for array in (matrix.data, matrix.indices, matrix.indptr):
        array.setflags(write=False)
    return matrix


def _csr_payload_bytes(matrix: sp.csr_matrix) -> int:
    return int(matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes)


def _sparse_relative_error(
    observed: sp.spmatrix,
    expected: sp.spmatrix,
) -> float:
    difference = (observed - expected).tocsr()
    numerator = float(np.linalg.norm(difference.data))
    denominator = max(float(np.linalg.norm(expected.data)), np.finfo(float).tiny)
    return numerator / denominator


def _edge_vertex_pairing(
    slave_key: EdgeKey,
    master_key: EdgeKey,
) -> tuple[tuple[tuple[PointKey, PointKey], ...], int]:
    slave = tuple(slave_key)
    master = tuple(master_key)
    for orientation, ordered_master in ((1, master), (-1, master[::-1])):
        translation = np.asarray(slave[0]) - np.asarray(ordered_master[0])
        if all(
            np.array_equal(
                np.asarray(slave_point) - np.asarray(master_point),
                translation,
            )
            for slave_point, master_point in zip(
                slave, ordered_master, strict=True
            )
        ):
            return (
                (
                    (slave[0], ordered_master[0]),
                    (slave[1], ordered_master[1]),
                ),
                orientation,
            )
    raise RuntimeError("periodic child-edge endpoint translation is inconsistent")


def _physical_points(
    topologies: tuple[AffineLORParentTopology, ...],
) -> dict[PointKey, np.ndarray]:
    points: dict[PointKey, np.ndarray] = {}
    for topology in topologies:
        for key, point in zip(topology.vertex_keys, topology.vertices, strict=True):
            value = np.asarray(point, dtype=np.float64)
            previous = points.get(key)
            if previous is not None and not np.allclose(
                previous, value, rtol=0.0, atol=1.0e-12
            ):
                raise RuntimeError("one physical vertex key has inconsistent coordinates")
            points[key] = value.copy()
    return points


def _edge_relations(
    topologies: tuple[AffineLORParentTopology, ...],
    edge_space: LORSlabEdgeSpace,
) -> dict[EdgeKey, tuple[EdgeKey, complex, tuple[tuple[PointKey, PointKey], ...]]]:
    active = set(edge_space.active_edge_keys)
    relations: dict[
        EdgeKey, tuple[EdgeKey, complex, tuple[tuple[PointKey, PointKey], ...]]
    ] = {}
    for parent_index, topology in enumerate(topologies):
        expansion = edge_space._parent_expansions[parent_index]
        if expansion.shape[0] != len(topology.edge_keys):
            raise ValueError("edge expansion rows do not match parent topology")
        for row, slave_key in enumerate(topology.edge_keys):
            start = int(expansion.indptr[row])
            end = int(expansion.indptr[row + 1])
            if end - start != 1:
                raise RuntimeError("each parent edge row must have one expansion entry")
            column = int(expansion.indices[start])
            master_key = edge_space.active_edge_keys[column]
            coefficient = complex(expansion.data[start])
            if slave_key in active:
                if master_key != slave_key or not np.isclose(
                    coefficient, 1.0, rtol=0.0, atol=_COMMUTING_TOLERANCE
                ):
                    raise RuntimeError("active edge expansion is not the identity")
                continue
            endpoint_pairs, orientation = _edge_vertex_pairing(
                slave_key, master_key
            )
            phase = coefficient / orientation
            candidate = (master_key, phase, endpoint_pairs)
            previous = relations.get(slave_key)
            if previous is not None:
                if previous[0] != master_key or not np.isclose(
                    previous[1], phase, rtol=0.0, atol=_COMMUTING_TOLERANCE
                ) or previous[2] != endpoint_pairs:
                    raise RuntimeError("periodic edge identity is inconsistent")
            else:
                relations[slave_key] = candidate
    return relations


def _vertex_relations(
    edge_relations: dict[
        EdgeKey, tuple[EdgeKey, complex, tuple[tuple[PointKey, PointKey], ...]]
    ],
) -> dict[PointKey, tuple[PointKey, complex]]:
    direct: dict[PointKey, list[tuple[PointKey, complex]]] = {}
    for _slave_edge, (_master_edge, phase, endpoint_pairs) in edge_relations.items():
        for slave_vertex, master_vertex in endpoint_pairs:
            direct.setdefault(slave_vertex, []).append((master_vertex, phase))

    resolved: dict[PointKey, tuple[PointKey, complex]] = {}
    resolving: set[PointKey] = set()

    def resolve(vertex: PointKey) -> tuple[PointKey, complex]:
        cached = resolved.get(vertex)
        if cached is not None:
            return cached
        if vertex in resolving:
            raise RuntimeError("periodic vertex identities contain a cycle")
        candidates = direct.get(vertex)
        if not candidates:
            result = (vertex, 1.0 + 0.0j)
            resolved[vertex] = result
            return result
        resolving.add(vertex)
        final_candidates = []
        for master, phase in candidates:
            final_master, downstream_phase = resolve(master)
            final_candidates.append((final_master, phase * downstream_phase))
        resolving.remove(vertex)
        first_master, first_phase = final_candidates[0]
        if any(
            master != first_master
            or not np.isclose(
                phase,
                first_phase,
                rtol=0.0,
                atol=_COMMUTING_TOLERANCE,
            )
            for master, phase in final_candidates[1:]
        ):
            raise RuntimeError("periodic vertex identity is inconsistent")
        result = (first_master, first_phase)
        resolved[vertex] = result
        return result

    relations = {vertex: resolve(vertex) for vertex in direct}
    return relations


def _vertex_expansion(
    vertex_keys: Iterable[PointKey],
    active_index: dict[PointKey, int],
    relations: dict[PointKey, tuple[PointKey, complex]],
) -> sp.csr_matrix:
    columns: list[int] = []
    values: list[complex] = []
    keys = tuple(vertex_keys)
    for key in keys:
        relation = relations.get(key)
        if relation is None:
            master, coefficient = key, 1.0 + 0.0j
        else:
            master, coefficient = relation
        try:
            columns.append(active_index[master])
        except KeyError as error:
            raise RuntimeError(
                "vertex expansion references a missing active key"
            ) from error
        values.append(coefficient)
    indptr = np.arange(len(columns) + 1, dtype=np.int64)
    return _readonly_csr(
        sp.csr_matrix(
            (
                np.asarray(values, dtype=np.complex128),
                np.asarray(columns, dtype=np.int64),
                indptr,
            ),
            shape=(len(keys), len(active_index)),
        )
    )


def _edge_maps(
    edge_keys: tuple[EdgeKey, ...],
    vertex_keys: tuple[PointKey, ...],
    points: dict[PointKey, np.ndarray],
) -> tuple[sp.csr_matrix, sp.csr_matrix]:
    vertex_index = {key: index for index, key in enumerate(vertex_keys)}
    incidence_rows: list[int] = []
    incidence_columns: list[int] = []
    incidence_values: list[complex] = []
    pi_rows: list[int] = []
    pi_columns: list[int] = []
    pi_values: list[complex] = []
    for row, edge_key in enumerate(edge_keys):
        first, second = edge_key
        first_index = vertex_index[first]
        second_index = vertex_index[second]
        incidence_rows.extend((row, row))
        incidence_columns.extend((first_index, second_index))
        incidence_values.extend((-1.0, 1.0))
        delta = points[second] - points[first]
        for component, value in enumerate(delta):
            if abs(value) <= _CSR_ZERO_TOLERANCE:
                continue
            pi_rows.extend((row, row))
            pi_columns.extend(
                (3 * first_index + component, 3 * second_index + component)
            )
            pi_values.extend((0.5 * value, 0.5 * value))
    incidence = _readonly_csr(
        sp.csr_matrix(
            (
                np.asarray(incidence_values, dtype=np.complex128),
                (np.asarray(incidence_rows), np.asarray(incidence_columns)),
            ),
            shape=(len(edge_keys), len(vertex_keys)),
        )
    )
    vector_interpolation = _readonly_csr(
        sp.csr_matrix(
            (
                np.asarray(pi_values, dtype=np.complex128),
                (np.asarray(pi_rows), np.asarray(pi_columns)),
            ),
            shape=(len(edge_keys), 3 * len(vertex_keys)),
        )
    )
    return incidence, vector_interpolation


def _child_cell_curl_error(
    orientation_pattern: np.ndarray,
) -> float:
    """Return ``max|C D|`` for one actual local edge-orientation pattern."""

    d_matrix = np.zeros((len(_HEX_EDGES), 8), dtype=np.float64)
    c_matrix = np.zeros(
        (len(_HEX_FACE_CYCLES), len(_HEX_EDGES)),
        dtype=np.float64,
    )
    for local_edge, (first, second) in enumerate(_HEX_EDGES):
        orientation = float(orientation_pattern[local_edge])
        d_matrix[local_edge, first] = -orientation
        d_matrix[local_edge, second] = orientation
    for face_row, cycle in enumerate(_HEX_FACE_CYCLES):
        for first, second in zip(cycle, cycle[1:] + cycle[:1], strict=True):
            local_edge = _HEX_EDGE_BY_VERTICES[frozenset((first, second))]
            local_first, local_second = _HEX_EDGES[local_edge]
            loop_sign = 1.0 if (first, second) == (
                local_first,
                local_second,
            ) else -1.0
            c_matrix[face_row, local_edge] = (
                loop_sign * float(orientation_pattern[local_edge])
            )
    curl = c_matrix @ d_matrix
    return float(np.max(np.abs(curl), initial=0.0))


@dataclass(frozen=True)
class LORHcurlAuxiliarySpace:
    """Read-only owner-independent ``V``, ``G`` and ``Pi`` maps."""

    parent_ids: tuple[int, ...]
    active_vertex_keys: tuple[PointKey, ...]
    _parent_vertex_expansions: tuple[sp.csr_matrix, ...]
    _gradient: sp.csr_matrix
    _gradient_adjoint: sp.csr_matrix
    _vector_interpolation: sp.csr_matrix
    _vector_interpolation_adjoint: sp.csr_matrix
    audit: dict[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "parent_ids",
            tuple(int(value) for value in self.parent_ids),
        )
        object.__setattr__(self, "active_vertex_keys", tuple(self.active_vertex_keys))
        object.__setattr__(
            self,
            "_parent_vertex_expansions",
            tuple(_readonly_csr(matrix) for matrix in self._parent_vertex_expansions),
        )
        for name in (
            "_gradient",
            "_gradient_adjoint",
            "_vector_interpolation",
            "_vector_interpolation_adjoint",
        ):
            object.__setattr__(self, name, _readonly_csr(getattr(self, name)))
        object.__setattr__(self, "audit", MappingProxyType(dict(self.audit)))

    @property
    def parent_vertex_expansions(self) -> tuple[sp.csr_matrix, ...]:
        return self._parent_vertex_expansions

    @property
    def gradient_matrix(self) -> sp.csr_matrix:
        return self._gradient

    @property
    def vector_interpolation_matrix(self) -> sp.csr_matrix:
        return self._vector_interpolation

    def apply_gradient(self, values: np.ndarray) -> np.ndarray:
        values = np.asarray(values, dtype=np.complex128)
        if values.shape != (len(self.active_vertex_keys),):
            raise ValueError("scalar H1 values have the wrong vertex count")
        return np.asarray(self._gradient @ values, dtype=np.complex128)

    def apply_gradient_adjoint(self, values: np.ndarray) -> np.ndarray:
        values = np.asarray(values, dtype=np.complex128)
        if values.shape != (self._gradient.shape[0],):
            raise ValueError("edge values have the wrong count")
        return np.asarray(self._gradient_adjoint @ values, dtype=np.complex128)

    def apply_vector_h1(self, values: np.ndarray) -> np.ndarray:
        values = np.asarray(values, dtype=np.complex128)
        if values.shape != (3 * len(self.active_vertex_keys),):
            raise ValueError("vector H1 values have the wrong vertex count")
        return np.asarray(self._vector_interpolation @ values, dtype=np.complex128)

    def apply_vector_h1_adjoint(self, values: np.ndarray) -> np.ndarray:
        values = np.asarray(values, dtype=np.complex128)
        if values.shape != (self._vector_interpolation.shape[0],):
            raise ValueError("edge values have the wrong count")
        return np.asarray(
            self._vector_interpolation_adjoint @ values,
            dtype=np.complex128,
        )


def build_lor_hcurl_auxiliary_space(
    parent_topologies: Iterable[AffineLORParentTopology],
    edge_space: LORSlabEdgeSpace,
) -> LORHcurlAuxiliarySpace:
    """Build owner-independent scalar/vector auxiliary CSR maps.

    The periodic vertex relation is recovered from the already-qualified
    physical child-edge expansion in ``edge_space``.  No p6 trace row or
    high-order coefficient transform participates in this construction.
    """

    topologies = tuple(
        sorted(parent_topologies, key=lambda topology: topology.canonical_cell_id)
    )
    if not topologies:
        raise ValueError("at least one LOR parent topology is required")
    parent_ids = tuple(int(topology.canonical_cell_id) for topology in topologies)
    if parent_ids != tuple(edge_space.parent_ids):
        raise ValueError("parent topology order does not match the LOR edge space")
    if len(set(parent_ids)) != len(parent_ids):
        raise ValueError("parent canonical IDs must be unique")

    points = _physical_points(topologies)
    edge_relations = _edge_relations(topologies, edge_space)
    vertex_relations = _vertex_relations(edge_relations)
    physical_vertex_keys = tuple(sorted(points))
    active_vertex_keys = tuple(
        key for key in physical_vertex_keys if key not in vertex_relations
    )
    active_index = {key: index for index, key in enumerate(active_vertex_keys)}
    physical_vertex_expansion = _vertex_expansion(
        physical_vertex_keys,
        active_index,
        vertex_relations,
    )
    vertex_expansions = tuple(
        _vertex_expansion(topology.vertex_keys, active_index, vertex_relations)
        for topology in topologies
    )

    physical_incidence, physical_vector_interpolation = _edge_maps(
        edge_space.active_edge_keys,
        physical_vertex_keys,
        points,
    )
    gradient = _readonly_csr(physical_incidence @ physical_vertex_expansion)
    vector_interpolation = _readonly_csr(
        physical_vector_interpolation
        @ sp.kron(
            physical_vertex_expansion,
            sp.eye(3, format="csr"),
            format="csr",
        )
    )
    gradient_commuting_error = 0.0
    vector_commuting_error = 0.0
    curl_gradient_max_abs = 0.0
    for topology in topologies:
        orientation_patterns = np.unique(
            topology.cell_edge_orientations,
            axis=0,
        )
        for orientation_pattern in orientation_patterns:
            curl_gradient_max_abs = max(
                curl_gradient_max_abs,
                _child_cell_curl_error(orientation_pattern),
            )
    for parent_index, topology in enumerate(topologies):
        incidence, local_pi = _edge_maps(
            topology.edge_keys,
            topology.vertex_keys,
            points,
        )
        expansion = edge_space._parent_expansions[parent_index]
        observed_gradient = expansion @ gradient
        expected_gradient = incidence @ vertex_expansions[parent_index]
        gradient_commuting_error = max(
            gradient_commuting_error,
            _sparse_relative_error(observed_gradient, expected_gradient),
        )
        vertex_vector_expansion = sp.kron(
            vertex_expansions[parent_index],
            sp.eye(3, format="csr"),
            format="csr",
        )
        observed_vector = expansion @ vector_interpolation
        expected_vector = local_pi @ vertex_vector_expansion
        vector_commuting_error = max(
            vector_commuting_error,
            _sparse_relative_error(observed_vector, expected_vector),
        )
    if gradient_commuting_error > _COMMUTING_TOLERANCE:
        raise RuntimeError("LOR gradient does not commute with parent edge expansion")
    if vector_commuting_error > _COMMUTING_TOLERANCE:
        raise RuntimeError(
            "LOR vector-H1 interpolation does not commute with parent expansion"
        )
    if curl_gradient_max_abs > _COMMUTING_TOLERANCE:
        raise RuntimeError("child-hexa face boundary does not annihilate gradient")

    gradient_adjoint = _readonly_csr(gradient.conjugate().transpose())
    vector_interpolation_adjoint = _readonly_csr(
        vector_interpolation.conjugate().transpose()
    )
    audit = {
        "definition": "canonical LOR vertex H1, discrete gradient, and vector-H1 edge moment maps",
        "parent_ids": list(parent_ids),
        "parent_count": len(parent_ids),
        "physical_vertex_count": len(physical_vertex_keys),
        "active_vertex_count": len(active_vertex_keys),
        "periodic_slave_vertex_count": len(vertex_relations),
        "active_edge_count": len(edge_space.active_edge_keys),
        "parent_vertex_expansion_nnz": [
            int(matrix.nnz) for matrix in vertex_expansions
        ],
        "gradient_nnz": int(gradient.nnz),
        "vector_interpolation_nnz": int(vector_interpolation.nnz),
        "gradient_adjoint_nnz": int(gradient_adjoint.nnz),
        "vector_interpolation_adjoint_nnz": int(
            vector_interpolation_adjoint.nnz
        ),
        "gradient_commuting_max_relative_error": float(
            gradient_commuting_error
        ),
        "vector_interpolation_commuting_max_relative_error": float(
            vector_commuting_error
        ),
        "curl_gradient_max_abs": float(curl_gradient_max_abs),
        "gradient_csr_payload_bytes": _csr_payload_bytes(gradient),
        "gradient_adjoint_csr_payload_bytes": _csr_payload_bytes(
            gradient_adjoint
        ),
        "vector_interpolation_csr_payload_bytes": _csr_payload_bytes(
            vector_interpolation
        ),
        "vector_interpolation_adjoint_csr_payload_bytes": _csr_payload_bytes(
            vector_interpolation_adjoint
        ),
        "parent_vertex_expansion_csr_payload_bytes": [
            _csr_payload_bytes(matrix) for matrix in vertex_expansions
        ],
        "factor_count": 0,
        "global_dense_object_retained": False,
        "global_dense_T_retained": False,
        "component_order": "vertex_interleaved_xyz",
        "active_vertex_order": "canonical_physical_point_key_ascending",
    }
    return LORHcurlAuxiliarySpace(
        parent_ids=parent_ids,
        active_vertex_keys=active_vertex_keys,
        _parent_vertex_expansions=vertex_expansions,
        _gradient=gradient,
        _gradient_adjoint=gradient_adjoint,
        _vector_interpolation=vector_interpolation,
        _vector_interpolation_adjoint=vector_interpolation_adjoint,
        audit=audit,
    )


__all__ = (
    "LORHcurlAuxiliarySpace",
    "build_lor_hcurl_auxiliary_space",
)
