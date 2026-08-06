"""Affine lowest-order-refined topology inside one high-order hexahedron.

This module records the ``degree**3`` low-order hexahedra obtained by splitting
one affine parent with degree-dependent Gauss--Lobatto--Legendre nodes.  It is
the topology and local-transfer layer for the Task037 LOR path, not a
same-mesh p2/p4 coarse space.  It never constructs a global transfer matrix.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Sequence

import basix
import basix.ufl
import numpy as np
import scipy.sparse as sp

from src.geometry.tetra_mesh_audit import (
    canonical_entity_key,
    canonical_point_key,
)
from src.constraints.high_order_floquet_trace import (
    FloquetTraceTopology,
    PhaseIndependentConstraintBlock,
)


_HEX_EDGES: tuple[tuple[int, int], ...] = (
    (0, 1),
    (0, 2),
    (0, 4),
    (1, 3),
    (1, 5),
    (2, 3),
    (2, 6),
    (3, 7),
    (4, 5),
    (4, 6),
    (5, 7),
    (6, 7),
)

_HEX_BOUNDARY_FACES: tuple[tuple[int, int], ...] = (
    (2, 0),  # Basix face 0: z = 0
    (1, 0),  # Basix face 1: y = 0
    (0, 0),  # Basix face 2: x = 0
    (0, 1),  # Basix face 3: x = 1
    (1, 1),  # Basix face 4: y = 1
    (2, 1),  # Basix face 5: z = 1
)

_HEX_FACE_VERTICES: tuple[tuple[int, ...], ...] = (
    (0, 1, 2, 3),
    (0, 1, 4, 5),
    (0, 2, 4, 6),
    (1, 3, 5, 7),
    (2, 3, 6, 7),
    (4, 5, 6, 7),
)

_HEX_EDGE_FACES: tuple[tuple[int, int], ...] = (
    (0, 1),
    (0, 2),
    (1, 2),
    (0, 3),
    (1, 3),
    (0, 4),
    (2, 4),
    (3, 4),
    (1, 5),
    (2, 5),
    (3, 5),
    (4, 5),
)


@dataclass(frozen=True)
class AffineLORParentTopology:
    """Canonical child topology and metadata for one affine parent hexahedron."""

    degree: int
    canonical_cell_id: int
    material_tag: int
    cell_permutation: int
    reference_nodes: np.ndarray
    vertices: np.ndarray
    cells: np.ndarray
    vertex_keys: tuple[tuple[int, int, int], ...]
    edge_keys: tuple[tuple[tuple[int, int, int], ...], ...]
    edge_endpoints: np.ndarray
    edge_boundary_faces: tuple[tuple[int, ...], ...]
    cell_edge_ids: np.ndarray
    cell_edge_orientations: np.ndarray

    def __post_init__(self) -> None:
        for name in (
            "reference_nodes",
            "vertices",
            "cells",
            "edge_endpoints",
            "cell_edge_ids",
            "cell_edge_orientations",
        ):
            array = np.asarray(getattr(self, name)).copy()
            array.setflags(write=False)
            object.__setattr__(self, name, array)


_TRANSFER_STRUCTURAL_ZERO_TOLERANCE = 1.0e-14
_TRANSFER_INVERSE_TOLERANCE = 1.0e-11
_TRANSFER_DEFINITION = (
    "D_p[k,m]=integral_positive_reference_child_edge(phi_m dot t_k ds); "
    "T_ref=D_p^-1; T=O(cell_info) T_ref S"
)


def _gll_nodes(degree: int) -> np.ndarray:
    nodes = np.asarray(
        basix.create_lattice(
            basix.CellType.interval,
            degree,
            basix.LatticeType.gll,
            True,
        ),
        dtype=np.float64,
    ).reshape(-1)
    if nodes.size != degree + 1:
        raise RuntimeError("Basix GLL lattice returned an unexpected node count")
    if abs(float(nodes[0])) > 1.0e-12 or abs(float(nodes[-1] - 1.0)) > 1.0e-12:
        raise RuntimeError("Basix GLL lattice endpoints are not [0, 1]")
    nodes[0] = 0.0
    nodes[-1] = 1.0
    if np.any(np.diff(nodes) <= 0.0):
        raise ValueError("GLL reference nodes must be strictly increasing")
    return nodes


def _validate_parent(
    parent_vertices: np.ndarray,
    coordinate_tolerance: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    vertices = np.asarray(parent_vertices, dtype=np.float64)
    if vertices.shape != (8, 3) or not np.all(np.isfinite(vertices)):
        raise ValueError("parent_vertices must be finite with shape (8, 3)")
    if not np.isfinite(coordinate_tolerance) or coordinate_tolerance <= 0.0:
        raise ValueError("coordinate_tolerance must be finite and positive")

    origin = vertices[0]
    axes = np.asarray(
        (vertices[1] - origin, vertices[2] - origin, vertices[4] - origin),
        dtype=np.float64,
    )
    determinant = float(np.linalg.det(axes))
    if determinant <= max(coordinate_tolerance**3, 1.0e-30):
        raise ValueError("parent hexahedron must have a positive affine volume")
    expected = np.asarray(
        [
            origin,
            origin + axes[0],
            origin + axes[1],
            origin + axes[0] + axes[1],
            origin + axes[2],
            origin + axes[0] + axes[2],
            origin + axes[1] + axes[2],
            origin + axes[0] + axes[1] + axes[2],
        ]
    )
    if not np.allclose(vertices, expected, rtol=0.0, atol=coordinate_tolerance):
        raise ValueError("parent_vertices must describe an affine hexahedron")
    return vertices, origin, axes[0], axes[1], axes[2]


def _grid_vertex_index(i: int, j: int, k: int, node_count: int) -> int:
    return (i * node_count + j) * node_count + k


def _boundary_faces_for_edge(
    first: tuple[int, int, int],
    second: tuple[int, int, int],
    degree: int,
) -> tuple[int, ...]:
    faces: list[int] = []
    for face_id, (axis, side) in enumerate(_HEX_BOUNDARY_FACES):
        boundary_index = degree if side else 0
        if first[axis] == boundary_index and second[axis] == boundary_index:
            faces.append(face_id)
    return tuple(faces)


def build_affine_lor_parent_topology(
    parent_vertices: Iterable[Iterable[float]],
    *,
    degree: int,
    canonical_cell_id: int,
    material_tag: int,
    cell_permutation: int,
    coordinate_tolerance: float,
) -> AffineLORParentTopology:
    """Build the deterministic lowest-order refinement of one affine hexahedron.

    ``parent_vertices`` use Basix hexahedron vertex ordering.  The returned
    child cells use the same local ordering, while every child edge is mapped
    to one canonical physical endpoint key and an orientation sign.  This
    function records topology only; it does not create ``T``/``T^H`` or a
    coarse operator.
    """

    if not isinstance(degree, (int, np.integer)) or isinstance(degree, bool):
        raise ValueError("degree must be an integer")
    degree = int(degree)
    if degree < 1:
        raise ValueError("degree must be positive")
    if not isinstance(material_tag, (int, np.integer)) or isinstance(
        material_tag, bool
    ):
        raise ValueError("material_tag must be an integer")
    if not isinstance(cell_permutation, (int, np.integer)) or isinstance(
        cell_permutation, bool
    ):
        raise ValueError("cell_permutation must be an integer bitfield")
    material_tag = int(material_tag)
    permutation = int(cell_permutation)

    _vertices, origin, axis_x, axis_y, axis_z = _validate_parent(
        np.asarray(parent_vertices, dtype=np.float64),
        float(coordinate_tolerance),
    )
    reference_nodes = _gll_nodes(degree)
    node_count = degree + 1
    refined_vertices = np.empty((node_count**3, 3), dtype=np.float64)
    for i, reference_x in enumerate(reference_nodes):
        for j, reference_y in enumerate(reference_nodes):
            for k, reference_z in enumerate(reference_nodes):
                refined_vertices[_grid_vertex_index(i, j, k, node_count)] = (
                    origin
                    + reference_x * axis_x
                    + reference_y * axis_y
                    + reference_z * axis_z
                )

    vertex_keys = tuple(
        canonical_point_key(point, float(coordinate_tolerance))
        for point in refined_vertices
    )
    if len(set(vertex_keys)) != len(vertex_keys):
        raise ValueError("refined vertices have duplicate canonical point keys")

    cell_rows: list[tuple[int, ...]] = []
    cell_grid_rows: list[tuple[tuple[int, int, int], ...]] = []
    for i in range(degree):
        for j in range(degree):
            for k in range(degree):
                local_grid = (
                    (i, j, k),
                    (i + 1, j, k),
                    (i, j + 1, k),
                    (i + 1, j + 1, k),
                    (i, j, k + 1),
                    (i + 1, j, k + 1),
                    (i, j + 1, k + 1),
                    (i + 1, j + 1, k + 1),
                )
                cell_grid_rows.append(local_grid)
                cell_rows.append(
                    tuple(
                        _grid_vertex_index(*grid_vertex, node_count)
                        for grid_vertex in local_grid
                    )
                )

    edge_id_by_key: dict[tuple[tuple[int, int, int], ...], int] = {}
    edge_keys: list[tuple[tuple[int, int, int], ...]] = []
    edge_endpoints: list[tuple[int, int]] = []
    edge_boundary_faces: list[set[int]] = []
    cell_edge_ids = np.empty((len(cell_rows), len(_HEX_EDGES)), dtype=np.int64)
    cell_edge_orientations = np.empty_like(cell_edge_ids)

    for cell_index, (cell_row, grid_row) in enumerate(
        zip(cell_rows, cell_grid_rows, strict=True)
    ):
        for local_edge, (first_local, second_local) in enumerate(_HEX_EDGES):
            first_vertex = cell_row[first_local]
            second_vertex = cell_row[second_local]
            first_key = vertex_keys[first_vertex]
            second_key = vertex_keys[second_vertex]
            edge_key = canonical_entity_key(
                refined_vertices[[first_vertex, second_vertex]],
                float(coordinate_tolerance),
            )
            edge_id = edge_id_by_key.get(edge_key)
            if edge_id is None:
                edge_id = len(edge_keys)
                edge_id_by_key[edge_key] = edge_id
                edge_keys.append(edge_key)
                if first_key <= second_key:
                    edge_endpoints.append((first_vertex, second_vertex))
                else:
                    edge_endpoints.append((second_vertex, first_vertex))
                edge_boundary_faces.append(set())
            canonical_endpoints = (
                vertex_keys[edge_endpoints[edge_id][0]],
                vertex_keys[edge_endpoints[edge_id][1]],
            )
            cell_edge_ids[cell_index, local_edge] = edge_id
            cell_edge_orientations[cell_index, local_edge] = (
                1 if (first_key, second_key) == canonical_endpoints else -1
            )
            edge_boundary_faces[edge_id].update(
                _boundary_faces_for_edge(
                    grid_row[first_local],
                    grid_row[second_local],
                    degree,
                )
            )

    return AffineLORParentTopology(
        degree=degree,
        canonical_cell_id=int(canonical_cell_id),
        material_tag=material_tag,
        cell_permutation=permutation,
        reference_nodes=reference_nodes,
        vertices=refined_vertices,
        cells=np.asarray(cell_rows, dtype=np.int64),
        vertex_keys=vertex_keys,
        edge_keys=tuple(edge_keys),
        edge_endpoints=np.asarray(edge_endpoints, dtype=np.int64),
        edge_boundary_faces=tuple(
            tuple(sorted(faces)) for faces in edge_boundary_faces
        ),
        cell_edge_ids=cell_edge_ids,
        cell_edge_orientations=cell_edge_orientations,
    )


def _readonly_csr(
    values: sp.spmatrix | np.ndarray,
    *,
    dtype: np.dtype | type = np.float64,
) -> sp.csr_matrix:
    matrix = sp.csr_matrix(values, dtype=dtype, copy=True)
    matrix.sum_duplicates()
    matrix.sort_indices()
    small = np.abs(matrix.data) <= _TRANSFER_STRUCTURAL_ZERO_TOLERANCE
    if np.any(small):
        matrix.data[small] = 0.0
        matrix.eliminate_zeros()
    for array in (matrix.data, matrix.indices, matrix.indptr):
        array.setflags(write=False)
    return matrix


def _parent_element(degree: int) -> basix.finite_element.FiniteElement:
    return basix.ufl.element(
        "N1curl",
        "hexahedron",
        int(degree),
    ).basix_element


def _positive_reference_edge_segments(
    topology: AffineLORParentTopology,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    degree = int(topology.degree)
    node_count = degree + 1
    corners = topology.vertices[
        [
            _grid_vertex_index(0, 0, 0, node_count),
            _grid_vertex_index(degree, 0, 0, node_count),
            _grid_vertex_index(0, degree, 0, node_count),
            _grid_vertex_index(0, 0, degree, node_count),
        ]
    ]
    origin = corners[0]
    affine_axes = np.column_stack(
        (corners[1] - origin, corners[2] - origin, corners[3] - origin)
    )
    reference_edge_signs = np.zeros(len(topology.edge_keys), dtype=np.int8)
    for edge_ids, edge_signs in zip(
        topology.cell_edge_ids,
        topology.cell_edge_orientations,
        strict=True,
    ):
        for edge_id, edge_sign in zip(edge_ids, edge_signs, strict=True):
            edge_id = int(edge_id)
            edge_sign = int(edge_sign)
            if reference_edge_signs[edge_id] == 0:
                reference_edge_signs[edge_id] = edge_sign
            elif reference_edge_signs[edge_id] != edge_sign:
                raise ValueError("one child edge has inconsistent reference signs")
    physical_edges = topology.vertices[topology.edge_endpoints]
    reference_edges = np.asarray(
        [
            np.linalg.solve(affine_axes, (physical_edge - origin).T).T
            for physical_edge in physical_edges
        ],
        dtype=np.float64,
    )
    positive_edges = reference_edges.copy()
    for edge_id, edge_sign in enumerate(reference_edge_signs):
        if edge_sign < 0:
            positive_edges[edge_id] = positive_edges[edge_id, ::-1]
    return (
        positive_edges[:, 0],
        positive_edges[:, 1],
        reference_edge_signs,
    )


def _reference_edge_moment_matrix(
    element: basix.finite_element.FiniteElement,
    topology: AffineLORParentTopology,
) -> np.ndarray:
    quadrature_degree = 2 * int(topology.degree) + 2
    quadrature_points, quadrature_weights = basix.make_quadrature(
        basix.CellType.interval,
        quadrature_degree,
    )
    quadrature_points = np.asarray(quadrature_points, dtype=np.float64).reshape(-1)
    quadrature_weights = np.asarray(quadrature_weights, dtype=np.float64).reshape(-1)
    starts, ends, _signs = _positive_reference_edge_segments(topology)
    matrix = np.zeros(
        (len(topology.edge_keys), int(element.dim)),
        dtype=np.complex128,
    )
    for row, (start, end) in enumerate(zip(starts, ends, strict=True)):
        tangent = end - start
        points = start + quadrature_points[:, None] * tangent
        values = np.asarray(element.tabulate(0, points)[0], dtype=np.complex128)
        axis = int(np.argmax(np.abs(tangent)))
        matrix[row] = np.einsum(
            "q,qm->m",
            quadrature_weights * tangent[axis],
            values[:, :, axis],
        )
    return matrix


def _relative_matrix_error(observed: np.ndarray, expected: np.ndarray) -> float:
    return float(
        np.linalg.norm(observed - expected)
        / max(float(np.linalg.norm(expected)), np.finfo(float).tiny)
    )


@lru_cache(maxsize=8)
def _reference_transfer_data(
    degree: int,
) -> tuple[sp.csr_matrix, float, float, float, int]:
    reference_topology = build_affine_lor_parent_topology(
        basix.geometry(basix.CellType.hexahedron),
        degree=int(degree),
        canonical_cell_id=0,
        material_tag=0,
        cell_permutation=0,
        coordinate_tolerance=1.0e-12,
    )
    element = _parent_element(int(degree))
    moment_matrix = _reference_edge_moment_matrix(element, reference_topology)
    high_dim = int(element.dim)
    if moment_matrix.shape != (high_dim, high_dim):
        raise RuntimeError("reference edge moment matrix is not square")
    reference_inverse = np.linalg.inv(moment_matrix)
    reference_csr = _readonly_csr(reference_inverse.real)
    compact_inverse = reference_csr.toarray()
    identity = np.eye(high_dim, dtype=np.complex128)
    left_error = _relative_matrix_error(
        moment_matrix @ compact_inverse,
        identity,
    )
    right_error = _relative_matrix_error(
        compact_inverse @ moment_matrix,
        identity,
    )
    if (
        left_error > _TRANSFER_INVERSE_TOLERANCE
        or right_error > _TRANSFER_INVERSE_TOLERANCE
    ):
        raise RuntimeError(
            "structural-zero reference transfer inverse exceeds tolerance"
        )
    return (
        reference_csr,
        float(np.linalg.cond(moment_matrix)),
        left_error,
        right_error,
        high_dim,
    )


@dataclass(frozen=True)
class LORParentTransfer:
    """Read-only local ``T`` and exact conjugate-transpose ``T^H`` actions."""

    _forward: sp.csr_matrix
    _adjoint: sp.csr_matrix
    audit: dict[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "_forward", _readonly_csr(self._forward))
        object.__setattr__(self, "_adjoint", _readonly_csr(self._adjoint))
        object.__setattr__(self, "audit", dict(self.audit))

    def apply(self, lor_values: np.ndarray) -> np.ndarray:
        values = np.asarray(lor_values, dtype=np.complex128)
        if values.shape != (int(self.audit["lor_edges"]),):
            raise ValueError("LOR values must match the parent edge count")
        return np.asarray(self._forward @ values, dtype=np.complex128)

    def apply_adjoint(self, high_values: np.ndarray) -> np.ndarray:
        values = np.asarray(high_values, dtype=np.complex128)
        if values.shape != (int(self.audit["high_dim"]),):
            raise ValueError("high values must match the parent element dimension")
        return np.asarray(self._adjoint @ values, dtype=np.complex128)


def build_lor_parent_transfer(
    topology: AffineLORParentTopology,
) -> LORParentTransfer:
    """Build the frozen local LOR-edge to stored parent N1curl transfer."""

    reference_csr, condition_number, left_error, right_error, high_dim = (
        _reference_transfer_data(int(topology.degree))
    )
    lor_edges = len(topology.edge_keys)
    if lor_edges != high_dim:
        raise ValueError("LOR edge count must equal the parent N1curl dimension")
    starts, ends, signs = _positive_reference_edge_segments(topology)
    del starts, ends
    reference_matrix = reference_csr.toarray()
    oriented = np.ascontiguousarray(
        reference_matrix.real * signs[None, :],
        dtype=np.float64,
    )
    element = _parent_element(int(topology.degree))
    element.T_apply(oriented.ravel(), high_dim, int(topology.cell_permutation))
    forward = _readonly_csr(oriented)
    adjoint = _readonly_csr(forward.conjugate().transpose())
    audit = {
        "degree": int(topology.degree),
        "high_dim": high_dim,
        "lor_edges": lor_edges,
        "definition": _TRANSFER_DEFINITION,
        "quadrature_degree": 2 * int(topology.degree) + 2,
        "condition_number": condition_number,
        "left_inverse_error": left_error,
        "right_inverse_error": right_error,
        "T_nnz": int(forward.nnz),
        "T_payload_bytes": int(
            forward.data.nbytes
            + forward.indices.nbytes
            + forward.indptr.nbytes
        ),
        "cell_permutation": int(topology.cell_permutation),
        "reference_cache_key": (
            f"N1curl-hexahedron-legendre-p{int(topology.degree)}-"
            f"gll-{2 * int(topology.degree) + 2}"
        ),
    }
    return LORParentTransfer(forward, adjoint, audit)


def _parent_corner_keys(
    topology: AffineLORParentTopology,
) -> tuple[tuple[int, int, int], ...]:
    degree = int(topology.degree)
    node_count = degree + 1
    grid_corners = (
        (0, 0, 0),
        (degree, 0, 0),
        (0, degree, 0),
        (degree, degree, 0),
        (0, 0, degree),
        (degree, 0, degree),
        (0, degree, degree),
        (degree, degree, degree),
    )
    return tuple(
        topology.vertex_keys[_grid_vertex_index(*corner, node_count)]
        for corner in grid_corners
    )


def _child_edge_keys_on_entity(
    topology: AffineLORParentTopology,
    entity_kind: str,
    entity_key: tuple[tuple[int, int, int], ...],
) -> tuple[tuple[tuple[int, int, int], ...], ...]:
    """Find child edges on one parent edge or in one parent-face interior."""

    corners = _parent_corner_keys(topology)
    if entity_kind == "edge":
        for edge_id, (first, second) in enumerate(_HEX_EDGES):
            macro_key = tuple(sorted((corners[first], corners[second])))
            if macro_key != entity_key:
                continue
            adjacent_faces = set(_HEX_EDGE_FACES[edge_id])
            return tuple(
                key
                for key, faces in zip(
                    topology.edge_keys,
                    topology.edge_boundary_faces,
                    strict=True,
                )
                if adjacent_faces.issubset(faces)
            )
        return ()
    if entity_kind == "face":
        for face_id, vertex_ids in enumerate(_HEX_FACE_VERTICES):
            macro_key = tuple(sorted(corners[index] for index in vertex_ids))
            if macro_key != entity_key:
                continue
            return tuple(
                key
                for key, faces in zip(
                    topology.edge_keys,
                    topology.edge_boundary_faces,
                    strict=True,
                )
                if len(faces) == 1 and int(face_id) in faces
            )
        return ()
    raise ValueError(f"unsupported Floquet entity kind {entity_kind!r}")


def _translation_from_entity_keys(
    master_key: tuple[tuple[int, int, int], ...],
    slave_key: tuple[tuple[int, int, int], ...],
) -> tuple[int, int, int]:
    master = np.asarray(master_key, dtype=np.int64)
    slave = np.asarray(slave_key, dtype=np.int64)
    if master.shape != slave.shape or master.ndim != 2:
        raise ValueError("periodic entity geometry keys have incompatible shapes")
    translation = slave[0] - master[0]
    if not np.all(slave - master == translation):
        raise NotImplementedError(
            "C1a LOR periodic identity requires a single quantized translation"
        )
    return tuple(int(value) for value in translation)


def _translated_edge_key(
    edge_key: tuple[tuple[int, int, int], ...],
    translation: tuple[int, int, int],
) -> tuple[tuple[int, int, int], ...]:
    return tuple(
        sorted(
            tuple(int(point[axis]) + int(translation[axis]) for axis in range(3))
            for point in edge_key
        )
    )


def _child_edge_orientation_sign(
    master_key: tuple[tuple[int, int, int], ...],
    slave_key: tuple[tuple[int, int, int], ...],
    translation: tuple[int, int, int],
) -> int:
    translated = tuple(
        tuple(
            int(point[axis]) + int(translation[axis]) for axis in range(3)
        )
        for point in master_key
    )
    if translated == slave_key:
        return 1
    if translated[::-1] == slave_key:
        return -1
    raise RuntimeError("periodic child-edge endpoint orientation is inconsistent")


def _periodic_phase(
    kind: str,
    phase_x: complex,
    phase_y: complex,
) -> complex:
    if kind == "x":
        return complex(phase_x)
    if kind == "y":
        return complex(phase_y)
    if kind == "corner":
        return complex(phase_x) * complex(phase_y)
    raise ValueError(f"unsupported Floquet phase kind {kind!r}")


def _validate_lor_floquet_block(block: PhaseIndependentConstraintBlock) -> None:
    if not block.has_physical_entity_identity:
        raise RuntimeError(
            "LOR periodic edge space requires complete physical entity identity"
        )
    if block.cell_type != "hexahedron":
        raise NotImplementedError("C1a LOR periodic identity supports hexahedra")


def _csr_payload_bytes(matrix: sp.csr_matrix) -> int:
    return int(
        matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes
    )


@dataclass(frozen=True)
class LORSlabEdgeSpace:
    """Owner-independent physical/independent LOR child-edge space.

    ``active_edge_keys`` removes only periodic slave physical edges.  Each
    stored CSR matrix maps those independent values to one parent-local
    canonical child-edge cochain; it is not a high-order transfer matrix.
    """

    parent_ids: tuple[int, ...]
    physical_edge_keys: tuple[tuple[tuple[int, int, int], ...], ...]
    active_edge_keys: tuple[tuple[tuple[int, int, int], ...], ...]
    _parent_expansions: tuple[sp.csr_matrix, ...]
    audit: dict[str, object]
    _parent_adjoint: tuple[sp.csr_matrix, ...] = ()

    def __post_init__(self) -> None:
        matrices = tuple(
            _readonly_csr(matrix, dtype=np.complex128)
            for matrix in self._parent_expansions
        )
        if len(matrices) != len(self.parent_ids):
            raise ValueError("one LOR expansion is required per parent")
        adjoints = tuple(
            _readonly_csr(
                matrix.conjugate().transpose(),
                dtype=np.complex128,
            )
            for matrix in matrices
        )
        object.__setattr__(self, "parent_ids", tuple(int(value) for value in self.parent_ids))
        object.__setattr__(self, "_parent_expansions", matrices)
        object.__setattr__(self, "_parent_adjoint", adjoints)
        object.__setattr__(self, "audit", dict(self.audit))

    def expand_parent(
        self,
        canonical_cell_id: int,
        active_values: np.ndarray,
    ) -> np.ndarray:
        """Expand independent active edge values to one parent edge cochain."""

        values = np.asarray(active_values, dtype=np.complex128)
        if values.shape != (len(self.active_edge_keys),):
            raise ValueError("active LOR values have the wrong edge count")
        try:
            position = self.parent_ids.index(int(canonical_cell_id))
        except ValueError as error:
            raise IndexError("unknown LOR parent canonical ID") from error
        return np.asarray(self._parent_expansions[position] @ values)

    def apply_adjoint(
        self,
        parent_values: Sequence[np.ndarray],
    ) -> np.ndarray:
        """Apply the exact conjugate transpose of all parent expansions."""

        if len(parent_values) != len(self._parent_expansions):
            raise ValueError("one parent value vector is required per parent")
        result = np.zeros(len(self.active_edge_keys), dtype=np.complex128)
        for adjoint, values in zip(
            self._parent_adjoint,
            parent_values,
            strict=True,
        ):
            vector = np.asarray(values, dtype=np.complex128)
            if vector.shape != (adjoint.shape[1],):
                raise ValueError("parent LOR values have the wrong edge count")
            result += np.asarray(adjoint @ vector)
        return result


def build_lor_slab_edge_space(
    parent_topologies: Iterable[AffineLORParentTopology],
    floquet_topology: FloquetTraceTopology,
    *,
    phase_x: complex,
    phase_y: complex,
) -> LORSlabEdgeSpace:
    """Build deterministic multi-parent LOR edge expansions.

    The input Floquet topology supplies physical entity identity only.  Its
    high-order ``coefficient_transform`` is deliberately not used: a refined
    lowest-order edge has one scalar cochain, related by translation, phase,
    and canonical endpoint orientation alone.
    """

    topologies = tuple(
        sorted(parent_topologies, key=lambda topology: topology.canonical_cell_id)
    )
    if not topologies:
        raise ValueError("at least one LOR parent topology is required")
    parent_ids = tuple(int(topology.canonical_cell_id) for topology in topologies)
    if len(set(parent_ids)) != len(parent_ids):
        raise ValueError("LOR parent canonical IDs must be unique")
    degrees = {int(topology.degree) for topology in topologies}
    if len(degrees) != 1:
        raise ValueError("all LOR parents must use one refinement degree")

    physical_edge_keys = tuple(
        sorted(
            {
                edge_key
                for topology in topologies
                for edge_key in topology.edge_keys
            }
        )
    )
    physical_edge_set = set(physical_edge_keys)
    relations: dict[
        tuple[tuple[int, int, int], ...],
        tuple[tuple[tuple[int, int, int], ...], str, complex],
    ] = {}
    matched_blocks = 0

    def add_block_relations(
        block: PhaseIndependentConstraintBlock,
        entity_kind: str,
    ) -> None:
        nonlocal matched_blocks
        _validate_lor_floquet_block(block)
        if block.entity_kind != entity_kind:
            return
        slave_entity_key = tuple(block.slave_entity_geometry_key)
        master_entity_key = tuple(block.master_entity_geometry_key)
        translation = _translation_from_entity_keys(
            master_entity_key,
            slave_entity_key,
        )
        candidates = {
            edge_key
            for topology in topologies
            for edge_key in _child_edge_keys_on_entity(
                topology,
                entity_kind,
                slave_entity_key,
            )
        }
        if not candidates:
            return
        matched_blocks += 1
        phase = _periodic_phase(block.kind, phase_x, phase_y)
        for slave_key in sorted(candidates):
            master_key = _translated_edge_key(
                slave_key,
                tuple(-value for value in translation),
            )
            if master_key not in physical_edge_set:
                raise RuntimeError("periodic child-edge master is outside the inventory")
            orientation = _child_edge_orientation_sign(
                master_key,
                slave_key,
                translation,
            )
            relation = (master_key, block.kind, phase * orientation)
            previous = relations.get(slave_key)
            if previous is not None and previous != relation:
                raise RuntimeError("conflicting periodic child-edge relations")
            relations[slave_key] = relation

    edge_blocks = sorted(
        (
            block
            for block in floquet_topology.blocks
            if block.entity_kind == "edge"
        ),
        key=lambda block: (
            block.kind,
            tuple(block.slave_entity_geometry_key),
            tuple(block.master_entity_geometry_key),
        ),
    )
    face_blocks = sorted(
        (
            block
            for block in floquet_topology.blocks
            if block.entity_kind == "face"
        ),
        key=lambda block: (
            block.kind,
            tuple(block.slave_entity_geometry_key),
            tuple(block.master_entity_geometry_key),
        ),
    )
    for block in edge_blocks:
        add_block_relations(block, "edge")
    for block in face_blocks:
        add_block_relations(block, "face")

    slave_keys = set(relations)
    if any(master_key in slave_keys for master_key, _kind, _coefficient in relations.values()):
        raise RuntimeError("periodic child-edge relations contain a slave chain")
    active_edge_keys = tuple(
        key for key in physical_edge_keys if key not in slave_keys
    )
    active_index = {key: index for index, key in enumerate(active_edge_keys)}
    parent_expansions = []
    for topology in topologies:
        columns = []
        values = []
        for edge_key in topology.edge_keys:
            relation = relations.get(edge_key)
            if relation is None:
                columns.append(active_index[edge_key])
                values.append(1.0 + 0.0j)
            else:
                columns.append(active_index[relation[0]])
                values.append(relation[2])
        indptr = np.arange(len(columns) + 1, dtype=np.int64)
        parent_expansions.append(
            sp.csr_matrix(
                (
                    np.asarray(values, dtype=np.complex128),
                    np.asarray(columns, dtype=np.int64),
                    indptr,
                ),
                shape=(len(columns), len(active_edge_keys)),
            )
        )

    relation_kind_counts = {
        kind: sum(1 for _master, relation_kind, _coefficient in relations.values() if relation_kind == kind)
        for kind in ("x", "y", "corner")
    }
    audit = {
        "definition": "physical canonical child edges -> independent LOR edges",
        "parent_ids": list(parent_ids),
        "parent_count": len(topologies),
        "refinement_degree": int(next(iter(degrees))),
        "physical_edge_count": len(physical_edge_keys),
        "active_edge_count": len(active_edge_keys),
        "periodic_slave_edge_count": len(slave_keys),
        "periodic_relation_count": len(relations),
        "periodic_relation_kind_counts": relation_kind_counts,
        "matched_identity_block_count": matched_blocks,
        "one_nonzero_per_parent_edge_row": True,
        "E_nnz_by_parent": [int(matrix.nnz) for matrix in parent_expansions],
        "E_payload_bytes_by_parent": [
            _csr_payload_bytes(matrix) for matrix in parent_expansions
        ],
        "high_order_coefficient_transform_used": False,
        "parent_order": "canonical_cell_id_ascending",
        "active_edge_order": "canonical_physical_endpoint_key_ascending",
    }
    return LORSlabEdgeSpace(
        parent_ids=parent_ids,
        physical_edge_keys=physical_edge_keys,
        active_edge_keys=active_edge_keys,
        _parent_expansions=tuple(parent_expansions),
        audit=audit,
    )
