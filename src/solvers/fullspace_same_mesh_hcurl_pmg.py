"""Bounded same-mesh Basix N1E transfer and local positive-cell audit.

This module is the local structural core for the C1 fallback.  A transfer is
the Basix interpolation map between two N1E polynomial spaces on one
reference hexahedron, with the selected Basix cell transformation applied on
the two sides.  The corresponding scalar-gradient and RT-curl maps are
constructed independently from their DOF functionals.  Only bounded
single-cell arrays are retained; no mesh, MPI, PETSc, global matrix, or
solver is involved here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from typing import Any, Mapping

import basix
import numpy as np
from scipy.linalg import eigvalsh

from .hcurl_affine_isotropic_tensor import (
    AffineIsotropicMaxwellTensorFactory,
    AffineIsotropicMaxwellTensorSpec,
)

SAME_MESH_METHOD = "same_mesh_hcurl_pmg_v1"
# Public pair convention is (fine_degree, coarse_degree); prolongation runs
# from the second entry to the first.
SAME_MESH_TRANSFER_PAIRS = ((3, 1), (6, 3))
SAME_MESH_EXTENDED_TRANSFER_PAIRS = (
    (2, 1),
    (3, 1),
    (4, 2),
    (6, 3),
    (6, 4),
)
EDGE_LIMIT = 1.0e-11
GRADIENT_LIMIT = 1.0e-11
CURL_LIMIT = 1.0e-11
ADJOINT_LIMIT = 1.0e-11
LINEARITY_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-13
MATERIAL_HERMITIAN_LIMIT = 1.0e-12
MATERIAL_ENERGY_LIMIT = 1.0e-9
DEFAULT_TRACE_MAP_POLICY = "basix_full_cell_interpolation_v1"
V6_P3_CANONICAL_TRACE_MAP_POLICY = "v6_p3_canonical_shared_trace_v1"


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left)
    right = np.asarray(right)
    return float(
        np.linalg.norm(left - right)
        / max(np.linalg.norm(right), np.finfo(np.float64).tiny)
    )


def _n1e(degree: int):
    return basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        int(degree),
        basix.LagrangeVariant.legendre,
    )


def _n1e_quadrilateral(degree: int):
    return basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.quadrilateral,
        int(degree),
        basix.LagrangeVariant.legendre,
    )


def _p_interval_legendre(degree: int):
    return basix.create_element(
        basix.ElementFamily.P,
        basix.CellType.interval,
        int(degree),
        basix.LagrangeVariant.legendre,
        discontinuous=True,
    )


def _canonical_quadrilateral_n1e_transfer(
    coarse_element: Any, fine_element: Any
) -> np.ndarray:
    """Return the shared canonical quadrilateral N1E interpolation map."""

    if coarse_element.cell_type != basix.CellType.quadrilateral or (
        fine_element.cell_type != basix.CellType.quadrilateral
    ):
        raise ValueError("canonical face transfer requires quadrilateral N1E spaces")
    if (int(coarse_element.degree), int(fine_element.degree)) != (3, 6):
        raise ValueError("canonical face transfer is restricted to P3-to-P6")
    matrix = np.asarray(
        basix.compute_interpolation_operator(coarse_element, fine_element),
        dtype=np.float64,
    )
    if matrix.shape != (int(fine_element.dim), int(coarse_element.dim)):
        raise RuntimeError("canonical quadrilateral transfer shape is not closed")
    if not np.isfinite(matrix).all():
        raise RuntimeError("canonical quadrilateral transfer is non-finite")
    return np.ascontiguousarray(matrix)


def _quadrilateral_trace_embedding(
    hex_element: Any, quad_element: Any, face: int
) -> np.ndarray:
    """Embed the complete quad trace closure into one hex face by topology."""

    hex_topology = basix.topology(basix.CellType.hexahedron)
    quad_topology = basix.topology(basix.CellType.quadrilateral)
    face_vertices = hex_topology[2][face]
    edge_by_vertices = {
        frozenset(edge): edge_id
        for edge_id, edge in enumerate(hex_topology[1])
    }
    result = np.zeros(
        (int(hex_element.dim), int(quad_element.dim)), dtype=np.float64
    )
    mapped_quad_edge_dofs: set[int] = set()

    for quad_edge, quad_vertices in enumerate(quad_topology[1]):
        va, vb = (int(face_vertices[int(vertex)]) for vertex in quad_vertices)
        hex_edge = edge_by_vertices[frozenset((va, vb))]
        same_direction = list(hex_topology[1][hex_edge]) == [va, vb]
        hex_dofs = hex_element.entity_dofs[1][hex_edge]
        quad_dofs = quad_element.entity_dofs[1][quad_edge]
        if len(hex_dofs) != len(quad_dofs):
            raise RuntimeError("reference edge DOF counts do not agree")
        for moment, (hex_dof, quad_dof) in enumerate(
            zip(hex_dofs, quad_dofs, strict=True)
        ):
            # Reversing the tangent also reverses the Legendre parameter.  The
            # sign follows the edge moment functional, not a fitted value.
            sign = 1.0 if same_direction else float((-1) ** (moment + 1))
            result[int(hex_dof), int(quad_dof)] = sign
            mapped_quad_edge_dofs.add(int(quad_dof))

    hex_face_dofs = hex_element.entity_dofs[2][face]
    quad_face_dofs = quad_element.entity_dofs[2][0]
    if len(hex_face_dofs) != len(quad_face_dofs):
        raise RuntimeError("reference face DOF counts do not agree")
    for hex_dof, quad_dof in zip(hex_face_dofs, quad_face_dofs, strict=True):
        result[int(hex_dof), int(quad_dof)] = 1.0

    closure = {
        int(value) for value in hex_element.entity_closure_dofs[2][face]
    }
    mapped_hex_rows = {
        int(value)
        for value in np.flatnonzero(np.any(result != 0.0, axis=1))
    }
    mapped_quad_columns = {
        int(value)
        for value in np.flatnonzero(np.any(result != 0.0, axis=0))
    }
    if mapped_hex_rows != closure or mapped_quad_columns != set(
        range(int(quad_element.dim))
    ):
        raise RuntimeError("topological trace embedding is not a closure bijection")
    if len(mapped_quad_edge_dofs) != sum(
        len(dofs) for dofs in quad_element.entity_dofs[1]
    ):
        raise RuntimeError("not all quadrilateral edge moments were mapped")
    return result


def _canonical_p63_trace_rows(
    coarse_element: Any,
    fine_element: Any,
    basix_interpolation: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Replace only P6 edge and face-owned rows using canonical shared traces.

    Edge inclusion is the exact nested inclusion of Basix's scalar Legendre
    interval moments.  Face-owned rows use one shared quadrilateral N1E map
    embedded over the complete edge-plus-face closure.  All cell-interior
    rows retain the original full-hexahedron Basix interpolation values.
    """

    if (
        int(coarse_element.degree) != 3
        or int(fine_element.degree) != 6
        or coarse_element.cell_type != basix.CellType.hexahedron
        or fine_element.cell_type != basix.CellType.hexahedron
    ):
        raise ValueError("canonical shared trace construction is restricted to P6<-P3")

    coarse_edge_moments = _p_interval_legendre(2)
    fine_edge_moments = _p_interval_legendre(5)
    if (
        int(coarse_edge_moments.dim) != 3
        or int(fine_edge_moments.dim) != 6
        or coarse_edge_moments.lagrange_variant != basix.LagrangeVariant.legendre
        or fine_edge_moments.lagrange_variant != basix.LagrangeVariant.legendre
        or not coarse_edge_moments.discontinuous
        or not fine_edge_moments.discontinuous
    ):
        raise RuntimeError("Basix NCE edge moment metadata changed")
    edge_map = np.zeros((6, 3), dtype=np.float64)
    np.fill_diagonal(edge_map, 1.0)

    coarse_quad = _n1e_quadrilateral(3)
    fine_quad = _n1e_quadrilateral(6)
    face_map = _canonical_quadrilateral_n1e_transfer(coarse_quad, fine_quad)

    candidate = np.asarray(basix_interpolation, dtype=np.complex128).copy()
    edge_rows: set[int] = set()
    for fine_dofs, coarse_dofs in zip(
        fine_element.entity_dofs[1],
        coarse_element.entity_dofs[1],
        strict=True,
    ):
        if (len(fine_dofs), len(coarse_dofs)) != edge_map.shape:
            raise RuntimeError("hex edge moments do not match the nested P2/P5 map")
        candidate[np.asarray(fine_dofs, dtype=np.int64), :] = 0.0
        candidate[np.ix_(fine_dofs, coarse_dofs)] = edge_map
        edge_rows.update(int(value) for value in fine_dofs)

    face_rows: set[int] = set()
    for face in range(6):
        coarse_embedding = _quadrilateral_trace_embedding(
            coarse_element, coarse_quad, face
        )
        fine_embedding = _quadrilateral_trace_embedding(
            fine_element, fine_quad, face
        )
        face_transfer = fine_embedding @ face_map @ coarse_embedding.T
        rows = [int(value) for value in fine_element.entity_dofs[2][face]]
        if face_rows.intersection(rows):
            raise RuntimeError("face-owned P6 rows are duplicated")
        face_rows.update(rows)
        candidate[rows, :] = face_transfer[rows, :]

    trace_rows = edge_rows | face_rows
    expected_edge_rows = 72
    expected_face_rows = 360
    expected_trace_rows = 432
    if (
        len(edge_rows) != expected_edge_rows
        or len(face_rows) != expected_face_rows
        or len(trace_rows) != expected_trace_rows
    ):
        raise RuntimeError("P6 trace row inventory differs from the reviewed 72+360 map")
    interior_rows = sorted(set(range(int(fine_element.dim))) - trace_rows)
    if len(interior_rows) != 450:
        raise RuntimeError("P6 internal row inventory differs from the reviewed 450 rows")
    if not np.array_equal(
        candidate[interior_rows, :],
        np.asarray(basix_interpolation)[interior_rows, :],
    ):
        raise RuntimeError("canonical trace construction changed a P6 interior row")
    if not np.isfinite(candidate).all():
        raise RuntimeError("canonical shared trace map contains non-finite values")

    canonical_reference = np.ascontiguousarray(candidate, dtype=np.complex128)
    facts = {
        "trace_map_policy": V6_P3_CANONICAL_TRACE_MAP_POLICY,
        "coarse_operator": "A3",
        "edge_moment_definition": "Basix scalar P_(degree-1), Legendre, discontinuous interval moments",
        "edge_map_shape": [6, 3],
        "face_map_definition": "one canonical quadrilateral N1E P3-to-P6 transfer embedded over each complete face closure",
        "face_map_shape": [int(face_map.shape[0]), int(face_map.shape[1])],
        "edge_trace_rows_replaced": len(edge_rows),
        "face_owned_trace_rows_replaced": len(face_rows),
        "trace_rows_replaced": len(trace_rows),
        "interior_rows_retained_from_basix": len(interior_rows),
        "interior_rows_bitwise_unchanged": True,
        "full_cell_basix_map_preserved": False,
        "canonical_reference_map_sha256": sha256(
            canonical_reference.view(np.uint8)
        ).hexdigest(),
        "edge_moment_ordering": "Basix entity DOF order; exact nested moment inclusion",
        "face_orientation_policy": "Basix full-cell T_apply after canonical trace construction",
    }
    return canonical_reference, facts


def _scalar(degree: int):
    return basix.create_element(
        basix.ElementFamily.P,
        basix.CellType.hexahedron,
        int(degree),
        basix.LagrangeVariant.equispaced,
    )


def _rt(degree: int):
    return basix.create_element(
        basix.ElementFamily.RT,
        basix.CellType.hexahedron,
        int(degree),
        basix.LagrangeVariant.equispaced,
    )


def _dof_transform(element: Any, cell_info: int) -> np.ndarray:
    """Materialise Basix's cell transformation without assuming a permutation."""

    cell_info = int(cell_info)
    if cell_info < 0:
        raise ValueError("Basix cell information must be non-negative")
    dimension = int(element.dim)
    data = np.eye(dimension, dtype=np.float64).reshape(-1).copy()
    # With an identity block, ``block_size=dimension`` materialises one
    # transformed column per right-hand side; block_size=1 would only test a
    # single coefficient vector and cannot be reshaped into the operator.
    element.T_apply(data, dimension, cell_info)
    transform = np.ascontiguousarray(data.reshape(dimension, dimension))
    if not np.all(np.isfinite(transform)):
        raise ValueError("Basix cell transformation is non-finite")
    if abs(np.linalg.det(transform)) <= np.finfo(np.float64).tiny:
        raise ValueError("Basix cell transformation is singular")
    transform.setflags(write=False)
    return transform


def _inverse(transform: np.ndarray) -> np.ndarray:
    return np.linalg.inv(np.asarray(transform, dtype=np.float64))


def _dof_functional_interpolation(source: Any, target: Any) -> np.ndarray:
    """Independently apply target DOF functionals to source basis values."""

    if source.map_type != target.map_type:
        raise ValueError("same-mesh N1E maps must have the same Basix map type")
    if tuple(source.value_shape) != tuple(target.value_shape):
        raise ValueError("same-mesh interpolation requires equal value shapes")
    points = np.asarray(target.points, dtype=np.float64)
    values = np.asarray(source.tabulate(0, points))[0]
    value_size = int(np.prod(source.value_shape, dtype=np.int64))
    expected_values = (len(points), int(source.dim), value_size)
    if values.shape != expected_values:
        raise RuntimeError(
            "Basix source tabulation shape changed: "
            f"{values.shape} != {expected_values}"
        )
    function_values = values.transpose(2, 0, 1).reshape(
        len(points) * value_size, int(source.dim)
    )
    interpolation = np.asarray(target.interpolation_matrix)
    expected_interpolation = (int(target.dim), len(points) * value_size)
    if interpolation.shape != expected_interpolation:
        raise RuntimeError(
            "Basix target interpolation shape changed: "
            f"{interpolation.shape} != {expected_interpolation}"
        )
    return np.ascontiguousarray(
        interpolation @ function_values,
        dtype=np.complex128,
    )


def _gradient_functional_map(vector_element: Any, scalar_element: Any) -> np.ndarray:
    points = np.asarray(vector_element.points, dtype=np.float64)
    derivatives = np.asarray(scalar_element.tabulate(1, points))
    gradient_values = np.stack(
        (
            derivatives[1, :, :, 0],
            derivatives[2, :, :, 0],
            derivatives[3, :, :, 0],
        ),
        axis=2,
    )
    values = gradient_values.transpose(2, 0, 1).reshape(
        3 * len(points), int(scalar_element.dim)
    )
    interpolation = np.asarray(vector_element.interpolation_matrix)
    if interpolation.shape != (int(vector_element.dim), 3 * len(points)):
        raise RuntimeError("Basix N1E gradient functional shape is not closed")
    return np.ascontiguousarray(interpolation @ values, dtype=np.complex128)


def _curl_functional_map(vector_element: Any, rt_element: Any) -> np.ndarray:
    points = np.asarray(rt_element.points, dtype=np.float64)
    derivatives = np.asarray(vector_element.tabulate(1, points))
    curls = np.stack(
        (
            derivatives[2, :, :, 2] - derivatives[3, :, :, 1],
            derivatives[3, :, :, 0] - derivatives[1, :, :, 2],
            derivatives[1, :, :, 1] - derivatives[2, :, :, 0],
        ),
        axis=2,
    )
    values = curls.transpose(2, 0, 1).reshape(
        3 * len(points), int(vector_element.dim)
    )
    interpolation = np.asarray(rt_element.interpolation_matrix)
    if interpolation.shape != (int(rt_element.dim), 3 * len(points)):
        raise RuntimeError("Basix RT curl functional shape is not closed")
    return np.ascontiguousarray(interpolation @ values, dtype=np.complex128)


def _element_metadata(element: Any) -> dict[str, object]:
    return {
        "dimension": int(element.dim),
        "map_type": str(element.map_type.name),
        "value_shape": [int(value) for value in element.value_shape],
        "points": int(len(element.points)),
        "dof_ordering": [int(value) for value in element.dof_ordering],
        "entity_dof_counts": [
            [int(len(entity)) for entity in dimension]
            for dimension in element.entity_dofs
        ],
        "dof_transformations_are_identity": bool(
            element.dof_transformations_are_identity
        ),
        "dof_transformations_are_permutations": bool(
            element.dof_transformations_are_permutations
        ),
    }


def _probe_facts(matrix: np.ndarray) -> dict[str, object]:
    columns = int(matrix.shape[1])
    rows = int(matrix.shape[0])
    first = (
        np.arange(1, columns + 1, dtype=np.float64)
        + 1j * np.arange(columns, 0, -1, dtype=np.float64)
    ).astype(np.complex128)
    second = (
        np.arange(columns, 2 * columns, dtype=np.float64)
        - 0.5j * np.arange(1, columns + 1, dtype=np.float64)
    ).astype(np.complex128)
    fine = (
        np.arange(1, rows + 1, dtype=np.float64)
        + 0.25j * np.arange(rows, 0, -1, dtype=np.float64)
    ).astype(np.complex128)
    before = first.copy()
    alpha = 0.37 + 0.19j
    beta = -0.23 + 0.41j
    observed = matrix @ first
    repeated = matrix @ first
    second_observed = matrix @ second
    combined = matrix @ (alpha * first + beta * second)
    expected = alpha * observed + beta * second_observed
    adjoint_left = np.vdot(observed, fine)
    adjoint_right = np.vdot(first, matrix.conj().T @ fine)
    return {
        "adjoint_work_relative": float(
            abs(adjoint_left - adjoint_right)
            / max(abs(adjoint_right), np.finfo(np.float64).tiny)
        ),
        "linearity_relative": _relative(combined, expected),
        "repeat_relative": _relative(repeated, observed),
        "input_unchanged": bool(np.array_equal(first, before)),
        "finite": bool(
            np.all(np.isfinite(observed))
            and np.all(np.isfinite(repeated))
            and np.all(np.isfinite(combined))
        ),
    }


def same_mesh_transfer_gate(facts: Mapping[str, Any]) -> dict[str, object]:
    """Apply the fixed local structural gates without defaulting missing facts."""

    failures: list[str] = []
    numeric_names = (
        "edge_functional_relative",
        "gradient_commuting_relative",
        "curl_commuting_relative",
        "adjoint_work_relative",
        "linearity_relative",
        "repeat_relative",
    )
    values: dict[str, float] = {}
    for name in numeric_names:
        value = facts.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            failures.append(f"{name} missing or non-numeric")
        elif not math.isfinite(float(value)):
            failures.append(f"{name} non-finite")
        else:
            values[name] = float(value)
    if facts.get("full_column_rank") is not True:
        failures.append("full column rank")
    if facts.get("rank") != facts.get("expected_rank"):
        failures.append("rank")
    if values.get("edge_functional_relative", math.inf) > EDGE_LIMIT:
        failures.append("edge functional")
    if values.get("gradient_commuting_relative", math.inf) > GRADIENT_LIMIT:
        failures.append("gradient commuting")
    if values.get("curl_commuting_relative", math.inf) > CURL_LIMIT:
        failures.append("curl commuting")
    if values.get("adjoint_work_relative", math.inf) > ADJOINT_LIMIT:
        failures.append("adjoint work")
    if values.get("linearity_relative", math.inf) > LINEARITY_LIMIT:
        failures.append("linearity")
    if values.get("repeat_relative", math.inf) > REPEAT_LIMIT:
        failures.append("repeat")
    if facts.get("input_unchanged") is not True:
        failures.append("input unchanged")
    if facts.get("finite") is not True:
        failures.append("finite")
    return {"passed": not failures, "failures": tuple(failures)}


@dataclass(frozen=True)
class SameMeshHcurlTransfer:
    """Immutable bounded transfer between two same-cell Basix N1E spaces."""

    fine_degree: int
    coarse_degree: int
    matrix: np.ndarray
    coarse_cell_info: int
    fine_cell_info: int
    audit: MappingProxyType

    def apply(self, values: np.ndarray) -> np.ndarray:
        vector = np.asarray(values, dtype=np.complex128)
        if vector.shape != (self.matrix.shape[1],):
            raise ValueError("coarse N1E vector has an unexpected local shape")
        return np.ascontiguousarray(self.matrix @ vector)

    def apply_adjoint(self, values: np.ndarray) -> np.ndarray:
        vector = np.asarray(values, dtype=np.complex128)
        if vector.shape != (self.matrix.shape[0],):
            raise ValueError("fine N1E vector has an unexpected local shape")
        return np.ascontiguousarray(self.matrix.conj().T @ vector)

    def apply_many(self, values: np.ndarray) -> np.ndarray:
        vectors = np.asarray(values, dtype=np.complex128)
        if vectors.ndim != 2 or vectors.shape[1] != self.matrix.shape[1]:
            raise ValueError("coarse N1E batch has an unexpected local shape")
        return np.ascontiguousarray(vectors @ self.matrix.T)

    def apply_adjoint_many(self, values: np.ndarray) -> np.ndarray:
        vectors = np.asarray(values, dtype=np.complex128)
        if vectors.ndim != 2 or vectors.shape[1] != self.matrix.shape[0]:
            raise ValueError("fine N1E batch has an unexpected local shape")
        return np.ascontiguousarray(vectors @ self.matrix.conj())

    apply_primal = apply


def build_same_mesh_hcurl_transfer(
    fine_degree: int,
    coarse_degree: int,
    *,
    coarse_cell_info: int = 0,
    fine_cell_info: int = 0,
    trace_map_policy: str = DEFAULT_TRACE_MAP_POLICY,
) -> SameMeshHcurlTransfer:
    """Build and independently audit one fixed same-mesh N1E transfer."""

    pair = (int(fine_degree), int(coarse_degree))
    if pair not in SAME_MESH_EXTENDED_TRANSFER_PAIRS:
        raise ValueError(
            "same-mesh transfer supports only fine/coarse pairs "
            f"{SAME_MESH_EXTENDED_TRANSFER_PAIRS}"
        )
    trace_map_policy = str(trace_map_policy)
    if trace_map_policy not in {
        DEFAULT_TRACE_MAP_POLICY,
        V6_P3_CANONICAL_TRACE_MAP_POLICY,
    }:
        raise ValueError(f"unsupported same-mesh trace map policy: {trace_map_policy}")
    if (
        trace_map_policy == V6_P3_CANONICAL_TRACE_MAP_POLICY
        and pair != (6, 3)
    ):
        raise ValueError(
            "canonical shared trace transfer is restricted to the explicit P6-to-P3 policy"
        )
    coarse_element = _n1e(coarse_degree)
    fine_element = _n1e(fine_degree)
    if coarse_element.map_type != fine_element.map_type:
        raise ValueError("same-mesh N1E elements have incompatible map types")
    coarse_transform = _dof_transform(coarse_element, coarse_cell_info)
    fine_transform = _dof_transform(fine_element, fine_cell_info)
    coarse_inverse = _inverse(coarse_transform)
    fine_inverse = _inverse(fine_transform)

    basix_interpolation = np.asarray(
        basix.compute_interpolation_operator(coarse_element, fine_element),
        dtype=np.complex128,
    )
    expected_shape = (int(fine_element.dim), int(coarse_element.dim))
    if basix_interpolation.shape != expected_shape:
        raise RuntimeError(
            "Basix N1E interpolation shape is not closed: "
            f"{basix_interpolation.shape} != {expected_shape}"
        )
    trace_map_facts: dict[str, Any] = {}
    reference_interpolation = basix_interpolation
    if trace_map_policy == V6_P3_CANONICAL_TRACE_MAP_POLICY:
        reference_interpolation, trace_map_facts = _canonical_p63_trace_rows(
            coarse_element,
            fine_element,
            basix_interpolation,
        )
    matrix = np.ascontiguousarray(
        fine_transform @ reference_interpolation @ coarse_inverse,
        dtype=np.complex128,
    )

    direct_reference = _dof_functional_interpolation(
        coarse_element, fine_element
    )
    direct_matrix = np.ascontiguousarray(
        fine_transform @ direct_reference @ coarse_inverse,
        dtype=np.complex128,
    )

    coarse_scalar = _scalar(coarse_degree)
    fine_scalar = _scalar(fine_degree)
    scalar_interpolation = np.asarray(
        basix.compute_interpolation_operator(coarse_scalar, fine_scalar),
        dtype=np.complex128,
    )
    coarse_scalar_transform = _dof_transform(coarse_scalar, coarse_cell_info)
    fine_scalar_transform = _dof_transform(fine_scalar, fine_cell_info)
    scalar_map = np.ascontiguousarray(
        fine_scalar_transform
        @ scalar_interpolation
        @ _inverse(coarse_scalar_transform),
        dtype=np.complex128,
    )
    coarse_gradient = _gradient_functional_map(coarse_element, coarse_scalar)
    fine_gradient = _gradient_functional_map(fine_element, fine_scalar)
    coarse_gradient = np.ascontiguousarray(
        coarse_transform @ coarse_gradient @ _inverse(coarse_scalar_transform)
    )
    fine_gradient = np.ascontiguousarray(
        fine_transform @ fine_gradient @ _inverse(fine_scalar_transform)
    )

    coarse_rt = _rt(coarse_degree)
    fine_rt = _rt(fine_degree)
    rt_interpolation = np.asarray(
        basix.compute_interpolation_operator(coarse_rt, fine_rt),
        dtype=np.complex128,
    )
    coarse_rt_transform = _dof_transform(coarse_rt, coarse_cell_info)
    fine_rt_transform = _dof_transform(fine_rt, fine_cell_info)
    rt_map = np.ascontiguousarray(
        fine_rt_transform @ rt_interpolation @ _inverse(coarse_rt_transform),
        dtype=np.complex128,
    )
    coarse_curl = _curl_functional_map(coarse_element, coarse_rt)
    fine_curl = _curl_functional_map(fine_element, fine_rt)
    coarse_curl = np.ascontiguousarray(
        coarse_rt_transform @ coarse_curl @ coarse_inverse
    )
    fine_curl = np.ascontiguousarray(
        fine_rt_transform @ fine_curl @ fine_inverse
    )

    singular_values = np.linalg.svd(matrix, compute_uv=False)
    sigma_max = float(singular_values[0])
    sigma_min = float(singular_values[-1])
    rank_threshold = max(matrix.shape) * np.finfo(np.float64).eps * sigma_max
    rank = int(np.count_nonzero(singular_values > rank_threshold))
    probe = _probe_facts(matrix)
    audit: dict[str, object] = {
        "schema": "task038.same_mesh_hcurl_transfer.v1",
        "method": SAME_MESH_METHOD,
        "pair_fine_to_coarse": [int(fine_degree), int(coarse_degree)],
        "fine_degree": int(fine_degree),
        "coarse_degree": int(coarse_degree),
        "shape": [int(value) for value in matrix.shape],
        "rows": int(matrix.shape[0]),
        "cols": int(matrix.shape[1]),
        "rank": rank,
        "expected_rank": int(coarse_element.dim),
        "rank_threshold": float(rank_threshold),
        "sigma_min": sigma_min,
        "sigma_max": sigma_max,
        "full_column_rank": bool(rank == int(coarse_element.dim)),
        "basix_interpolation": True,
        "dof_functional_independent_audit": True,
        "map_type": str(coarse_element.map_type.name),
        "coarse_lagrange_variant": str(coarse_element.lagrange_variant.name),
        "fine_lagrange_variant": str(fine_element.lagrange_variant.name),
        "coarse_cell_info": int(coarse_cell_info),
        "fine_cell_info": int(fine_cell_info),
        "orientation_transform": "basix_FiniteElement_T_apply",
        "coarse_orientation_relative_identity": _relative(
            coarse_transform, np.eye(int(coarse_element.dim))
        ),
        "fine_orientation_relative_identity": _relative(
            fine_transform, np.eye(int(fine_element.dim))
        ),
        "coarse_element": _element_metadata(coarse_element),
        "fine_element": _element_metadata(fine_element),
        "edge_functional_relative": _relative(matrix, direct_matrix),
        "gradient_commuting_relative": _relative(
            matrix @ coarse_gradient, fine_gradient @ scalar_map
        ),
        "curl_commuting_relative": _relative(
            rt_map @ coarse_curl, fine_curl @ matrix
        ),
        **probe,
        "finite": bool(
            np.all(np.isfinite(matrix))
            and np.all(np.isfinite(direct_matrix))
            and np.all(np.isfinite(coarse_gradient))
            and np.all(np.isfinite(fine_gradient))
            and np.all(np.isfinite(coarse_curl))
            and np.all(np.isfinite(fine_curl))
        ),
        "global_dense_transfer": False,
        "numeric_allgather": False,
    }
    if trace_map_policy == V6_P3_CANONICAL_TRACE_MAP_POLICY:
        audit.update(trace_map_facts)
        audit["orientation_pair"] = [
            int(fine_cell_info), int(coarse_cell_info)
        ]
        audit["oriented_matrix_sha256"] = sha256(
            np.ascontiguousarray(matrix).view(np.uint8)
        ).hexdigest()
        audit["candidate_vs_unmodified_independent_max_abs"] = float(
            np.max(np.abs(matrix - direct_matrix))
        )
        audit["absolute_owner_row_limit"] = 1.0e-11
        audit["absolute_owner_row_limit_changed"] = False
    gate = same_mesh_transfer_gate(audit)
    audit["gate_passed"] = bool(gate["passed"])
    audit["gate_failures"] = list(gate["failures"])
    if not gate["passed"]:
        raise RuntimeError(
            "same-mesh H(curl) transfer structural gate failed: "
            + ", ".join(str(value) for value in gate["failures"])
        )
    matrix.setflags(write=False)
    return SameMeshHcurlTransfer(
        int(fine_degree),
        int(coarse_degree),
        matrix,
        int(coarse_cell_info),
        int(fine_cell_info),
        MappingProxyType(audit),
    )


def _hermitian_defect(matrix: np.ndarray) -> float:
    return _relative(matrix, matrix.conj().T)


def same_mesh_material_gate(facts: Mapping[str, Any]) -> dict[str, object]:
    failures: list[str] = []
    for name in (
        "hermitian_defect_coarse",
        "hermitian_defect_galerkin",
        "minimum_eigenvalue_coarse",
        "minimum_eigenvalue_galerkin",
        "galerkin_matrix_relative",
        "rediscretized_energy_relative",
    ):
        value = facts.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            failures.append(f"{name} missing or non-numeric")
        elif not math.isfinite(float(value)):
            failures.append(f"{name} non-finite")
    if facts.get("strict_spd_coarse") is not True:
        failures.append("coarse strict SPD")
    if facts.get("strict_spd_galerkin") is not True:
        failures.append("Galerkin strict SPD")
    if float(facts.get("hermitian_defect_coarse", math.inf)) > MATERIAL_HERMITIAN_LIMIT:
        failures.append("coarse Hermitian")
    if float(facts.get("hermitian_defect_galerkin", math.inf)) > MATERIAL_HERMITIAN_LIMIT:
        failures.append("Galerkin Hermitian")
    if float(facts.get("minimum_eigenvalue_coarse", -math.inf)) <= 0.0:
        failures.append("coarse SPD minimum")
    if float(facts.get("minimum_eigenvalue_galerkin", -math.inf)) <= 0.0:
        failures.append("Galerkin SPD minimum")
    if float(facts.get("galerkin_matrix_relative", math.inf)) > MATERIAL_ENERGY_LIMIT:
        failures.append("Galerkin energy")
    if float(facts.get("rediscretized_energy_relative", math.inf)) > MATERIAL_ENERGY_LIMIT:
        failures.append("rediscretized energy")
    if facts.get("finite") is not True:
        failures.append("finite")
    return {"passed": not failures, "failures": tuple(failures)}


@dataclass(frozen=True)
class SameMeshMaterialResult:
    """Local positive material audit and bounded retained matrices."""

    audit: MappingProxyType
    retained: MappingProxyType


def build_same_mesh_material_class(
    transfer: SameMeshHcurlTransfer,
    *,
    class_name: str,
    material_role: str,
    widths: tuple[float, float, float] = (1.0, 1.0, 1.0),
    curl_coefficient: float = 1.0,
    mass_coefficient: float = 1.0,
) -> SameMeshMaterialResult:
    """Build independent affine positive matrices for one frozen class."""

    if material_role not in {"air", "grating", "substrate"}:
        raise ValueError("material role must be air, grating, or substrate")
    widths = tuple(float(value) for value in widths)
    if len(widths) != 3 or not all(math.isfinite(value) and value > 0.0 for value in widths):
        raise ValueError("material widths must be three positive finite values")
    curl_coefficient = float(curl_coefficient)
    mass_coefficient = float(mass_coefficient)
    if not math.isfinite(curl_coefficient) or curl_coefficient <= 0.0:
        raise ValueError("curl coefficient must be positive and finite")
    if not math.isfinite(mass_coefficient) or mass_coefficient <= 0.0:
        raise ValueError("mass coefficient must be positive and finite")

    spec = AffineIsotropicMaxwellTensorSpec(
        curl_coefficient=curl_coefficient,
        mass_coefficient_by_tag={1: mass_coefficient},
    )
    coarse_element = _n1e(transfer.coarse_degree)
    fine_element = _n1e(transfer.fine_degree)
    coarse_reference = AffineIsotropicMaxwellTensorFactory(
        coarse_element, spec
    ).tensor(tag=1, widths=widths)
    fine_reference = AffineIsotropicMaxwellTensorFactory(
        fine_element, spec
    ).tensor(tag=1, widths=widths)
    coarse_transform = _dof_transform(coarse_element, transfer.coarse_cell_info)
    fine_transform = _dof_transform(fine_element, transfer.fine_cell_info)
    coarse_inverse = _inverse(coarse_transform)
    fine_inverse = _inverse(fine_transform)
    coarse_matrix = np.ascontiguousarray(
        coarse_inverse.conj().T @ coarse_reference @ coarse_inverse
    )
    fine_matrix = np.ascontiguousarray(
        fine_inverse.conj().T @ fine_reference @ fine_inverse
    )
    galerkin = np.ascontiguousarray(transfer.matrix.conj().T @ fine_matrix @ transfer.matrix)
    coarse_eigenvalues = eigvalsh(coarse_matrix, check_finite=True)
    galerkin_eigenvalues = eigvalsh(galerkin, check_finite=True)
    probe = (
        np.arange(coarse_matrix.shape[0], dtype=np.float64) + 1.0
        + 1j * np.arange(coarse_matrix.shape[0], 0, -1, dtype=np.float64)
    ).astype(np.complex128)
    coarse_energy = np.vdot(probe, coarse_matrix @ probe)
    galerkin_energy = np.vdot(probe, galerkin @ probe)
    energy_relative = float(
        abs(galerkin_energy - coarse_energy)
        / max(abs(coarse_energy), np.finfo(np.float64).tiny)
    )
    facts: dict[str, object] = {
        "schema": "task038.same_mesh_hcurl_material.v1",
        "method": SAME_MESH_METHOD,
        "class_name": str(class_name),
        "material_role": material_role,
        "fine_degree": int(transfer.fine_degree),
        "coarse_degree": int(transfer.coarse_degree),
        "widths": [float(value) for value in widths],
        "curl_coefficient": curl_coefficient,
        "mass_coefficient": mass_coefficient,
        "coarse_shape": [int(value) for value in coarse_matrix.shape],
        "galerkin_shape": [int(value) for value in galerkin.shape],
        "hermitian_defect_coarse": _hermitian_defect(coarse_matrix),
        "hermitian_defect_galerkin": _hermitian_defect(galerkin),
        "minimum_eigenvalue_coarse": float(coarse_eigenvalues[0]),
        "minimum_eigenvalue_galerkin": float(galerkin_eigenvalues[0]),
        "strict_spd_coarse": bool(coarse_eigenvalues[0] > 0.0),
        "strict_spd_galerkin": bool(galerkin_eigenvalues[0] > 0.0),
        "galerkin_matrix_relative": _relative(galerkin, coarse_matrix),
        "rediscretized_energy_relative": energy_relative,
        "finite": bool(
            np.all(np.isfinite(coarse_matrix))
            and np.all(np.isfinite(galerkin))
            and np.all(np.isfinite(coarse_eigenvalues))
            and np.all(np.isfinite(galerkin_eigenvalues))
            and np.isfinite(energy_relative)
        ),
        "global_matrix": False,
    }
    gate = same_mesh_material_gate(facts)
    facts["gate_passed"] = bool(gate["passed"])
    facts["gate_failures"] = list(gate["failures"])
    if not gate["passed"]:
        raise RuntimeError(
            "same-mesh material structural gate failed: "
            + ", ".join(str(value) for value in gate["failures"])
        )
    for array in (coarse_matrix, galerkin):
        array.setflags(write=False)
    retained = MappingProxyType(
        {
            "transfer": transfer.matrix,
            "coarse_matrix": coarse_matrix,
            "galerkin_matrix": galerkin,
        }
    )
    return SameMeshMaterialResult(MappingProxyType(facts), retained)


__all__ = [
    "ADJOINT_LIMIT",
    "CURL_LIMIT",
    "EDGE_LIMIT",
    "GRADIENT_LIMIT",
    "LINEARITY_LIMIT",
    "MATERIAL_ENERGY_LIMIT",
    "MATERIAL_HERMITIAN_LIMIT",
    "REPEAT_LIMIT",
    "SAME_MESH_METHOD",
    "SAME_MESH_TRANSFER_PAIRS",
    "SAME_MESH_EXTENDED_TRANSFER_PAIRS",
    "SameMeshHcurlTransfer",
    "SameMeshMaterialResult",
    "build_same_mesh_hcurl_transfer",
    "build_same_mesh_material_class",
    "same_mesh_material_gate",
    "same_mesh_transfer_gate",
]
