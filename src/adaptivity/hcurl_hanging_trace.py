"""Reference authority for one-level hexahedral H(curl) hanging faces.

A coarse quadrilateral face next to four dyadically refined hexahedra owns
``2 p (p + 1)`` Nedelec trace coefficients.  The four child faces together
own more edge/face rows (144 rather than 40 at p4), but those rows are not
independent: their tangential field must be the covariant restriction of the
coarse trace.

This module constructs that restriction from the production Basix elements,
merges shared child edges, and pairs it with the scalar H1 restriction.  The
paired maps are then checked for the commuting identity

``R_hcurl @ grad_coarse == grad_fine @ R_h1``.

The result is a component authority only.  It does not create a DOLFINx MPC,
does not claim MPI ownership closure, and grants no PDE accuracy credit.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
from types import MappingProxyType
from typing import Any, Mapping

import basix
import basix.ufl
import numpy as np

from src.constraints.high_order_floquet_trace import (
    edge_coefficient_transform,
    face_coefficient_transform,
    quadrilateral_d4_vertex_permutations,
    quadrilateral_face_info,
)


_QUADRANTS = ((0, 0), (0, 1), (1, 0), (1, 1))


def _matrix_sha256(matrix: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(matrix).view(np.uint8)
    ).hexdigest()


def _hcurl_element(degree: int) -> basix.finite_element.FiniteElement:
    return basix.ufl.element(
        "N1curl",
        "quadrilateral",
        int(degree),
    ).basix_element


def _h1_element(degree: int) -> basix.finite_element.FiniteElement:
    return basix.ufl.element(
        "Lagrange",
        "quadrilateral",
        int(degree),
        lagrange_variant=basix.LagrangeVariant.gll_warped,
    ).basix_element


def _flatten_interpolation_values(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3:
        raise ValueError("interpolation values must be point/basis/component")
    return np.ascontiguousarray(values.transpose(2, 0, 1)).reshape(
        values.shape[0] * values.shape[2],
        values.shape[1],
    )


def _child_restriction(
    source: basix.finite_element.FiniteElement,
    target: basix.finite_element.FiniteElement,
    quadrant: tuple[int, int],
) -> np.ndarray:
    """Interpolate the parent field pulled back to one reference child."""

    if int(source.interpolation_nderivs) != 0:
        raise NotImplementedError("parent interpolation derivatives are unsupported")
    if int(target.interpolation_nderivs) != 0:
        raise NotImplementedError("child interpolation derivatives are unsupported")
    offset = 0.5 * np.asarray(quadrant, dtype=np.float64)
    child_points = np.asarray(target.points, dtype=np.float64)
    parent_points = offset[None, :] + 0.5 * child_points
    values = np.asarray(source.tabulate(0, parent_points)[0])
    if source.map_type == basix.MapType.covariantPiola:
        # F_child(xi) = offset + J xi, J = 0.5 I.  H(curl) uses the
        # covariant pullback J^T v(F_child(xi)).
        values = 0.5 * values
    elif source.map_type != basix.MapType.identity:
        raise NotImplementedError(
            f"unsupported hanging restriction map {source.map_type}"
        )
    flattened = _flatten_interpolation_values(values)
    interpolation = np.asarray(target.interpolation_matrix)
    if interpolation.shape[1] != flattened.shape[0]:
        raise RuntimeError(
            "Basix interpolation layout changed for hanging restriction"
        )
    return np.ascontiguousarray(interpolation @ flattened)


def _affine_pullback_restriction(
    source: basix.finite_element.FiniteElement,
    target: basix.finite_element.FiniteElement,
    *,
    offset: np.ndarray,
    jacobian: np.ndarray,
) -> np.ndarray:
    """Interpolate one affine scalar or covariant-Piola pullback."""

    if int(source.interpolation_nderivs) != 0:
        raise NotImplementedError("source interpolation derivatives are unsupported")
    if int(target.interpolation_nderivs) != 0:
        raise NotImplementedError("target interpolation derivatives are unsupported")
    offset = np.asarray(offset, dtype=np.float64)
    jacobian = np.asarray(jacobian, dtype=np.float64)
    if offset.shape != (2,) or jacobian.shape != (2, 2):
        raise ValueError("quadrilateral affine chart must be two-dimensional")
    mapped_points = (
        np.asarray(target.points, dtype=np.float64) @ jacobian.T
        + offset[None, :]
    )
    values = np.asarray(source.tabulate(0, mapped_points)[0])
    if source.map_type == basix.MapType.covariantPiola:
        values = np.einsum(
            "pbi,ij->pbj",
            values,
            jacobian,
            optimize=True,
        )
    elif source.map_type != basix.MapType.identity:
        raise NotImplementedError(
            f"unsupported affine trace map {source.map_type}"
        )
    flattened = _flatten_interpolation_values(values)
    interpolation = np.asarray(target.interpolation_matrix)
    if interpolation.shape[1] != flattened.shape[0]:
        raise RuntimeError(
            "Basix interpolation layout changed for affine trace restriction"
        )
    return np.ascontiguousarray(interpolation @ flattened)


def _quad_affine_chart(
    vertex_permutation: tuple[int, int, int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``g(eta)=offset+jacobian@eta`` for one D4 permutation."""

    permutation = tuple(map(int, vertex_permutation))
    quadrilateral_face_info(permutation)
    geometry = np.asarray(
        basix.geometry(basix.CellType.quadrilateral),
        dtype=np.float64,
    )
    design = np.column_stack(
        (geometry[:3], np.ones(3, dtype=np.float64))
    )
    coefficients = np.linalg.solve(
        design,
        geometry[np.asarray(permutation[:3], dtype=np.int32)],
    )
    jacobian = np.ascontiguousarray(coefficients[:2].T)
    offset = np.ascontiguousarray(coefficients[2])
    mapped = geometry @ jacobian.T + offset[None, :]
    expected = geometry[np.asarray(permutation, dtype=np.int32)]
    if not np.allclose(mapped, expected, rtol=0.0, atol=1.0e-14):
        raise RuntimeError("quadrilateral D4 permutation is not affine")
    return offset, jacobian


@dataclass(frozen=True)
class QuadChildTraceRestriction:
    """Parent-to-child coefficient maps for one dyadic quadrant."""

    degree: int
    quadrant: tuple[int, int]
    hcurl_from_parent: np.ndarray
    h1_from_parent: np.ndarray
    audit: Mapping[str, Any]


def build_quad_child_trace_restriction(
    degree: int,
    quadrant: tuple[int, int],
) -> QuadChildTraceRestriction:
    """Construct one child restriction with the production element variants."""

    degree = int(degree)
    normalized = tuple(map(int, quadrant))
    if degree not in {4, 5, 6}:
        raise ValueError("Task035d hanging traces qualify p4/p5/p6 only")
    if normalized not in _QUADRANTS:
        raise ValueError("quadrant must be one of the four dyadic children")
    hcurl = _hcurl_element(degree)
    h1 = _h1_element(degree)
    hcurl_restriction = _child_restriction(hcurl, hcurl, normalized)
    h1_restriction = _child_restriction(h1, h1, normalized)
    for matrix in (hcurl_restriction, h1_restriction):
        matrix.setflags(write=False)
    audit = MappingProxyType(
        {
            "schema_version": "task035d.quad-child-trace-restriction.v1",
            "degree": degree,
            "quadrant": list(normalized),
            "hcurl_shape": list(hcurl_restriction.shape),
            "h1_shape": list(h1_restriction.shape),
            "hcurl_sha256": _matrix_sha256(hcurl_restriction),
            "h1_sha256": _matrix_sha256(h1_restriction),
            "hcurl_variant": str(hcurl.lagrange_variant).split(".")[-1],
            "h1_variant": str(h1.lagrange_variant).split(".")[-1],
            "hcurl_map": str(hcurl.map_type).split(".")[-1],
            "child_jacobian": [[0.5, 0.0], [0.0, 0.5]],
            "ordinary_default_changed": False,
        }
    )
    return QuadChildTraceRestriction(
        degree=degree,
        quadrant=normalized,
        hcurl_from_parent=hcurl_restriction,
        h1_from_parent=h1_restriction,
        audit=audit,
    )


@dataclass(frozen=True)
class QuadD4TraceTransformPair:
    """Full H(curl)/H1 coefficient transforms for one quad D4 chart."""

    degree: int
    vertex_permutation: tuple[int, int, int, int]
    face_info: int
    hcurl_coefficients: np.ndarray
    h1_coefficients: np.ndarray
    audit: Mapping[str, Any]


def _expected_hcurl_d4_transform(
    degree: int,
    permutation: tuple[int, int, int, int],
) -> np.ndarray:
    """Assemble the existing Task033 edge/face transform into full trace order."""

    element = _hcurl_element(degree)
    topology = basix.topology(basix.CellType.quadrilateral)
    result = np.zeros(
        (int(element.dim), int(element.dim)),
        dtype=np.complex128,
    )
    for slave_edge, slave_vertices in enumerate(topology[1]):
        mapped = tuple(permutation[int(vertex)] for vertex in slave_vertices)
        master_edge = next(
            (
                entity
                for entity, vertices in enumerate(topology[1])
                if set(map(int, vertices)) == set(mapped)
            ),
            None,
        )
        if master_edge is None:
            raise RuntimeError("D4 edge has no canonical master")
        master_vertices = tuple(map(int, topology[1][master_edge]))
        reversed_orientation = mapped != master_vertices
        slave_dofs = np.asarray(
            element.entity_dofs[1][slave_edge],
            dtype=np.int32,
        )
        master_dofs = np.asarray(
            element.entity_dofs[1][master_edge],
            dtype=np.int32,
        )
        result[np.ix_(slave_dofs, master_dofs)] = (
            edge_coefficient_transform(
                degree,
                reversed_orientation=reversed_orientation,
            )
        )
    face_dofs = np.asarray(element.entity_dofs[2][0], dtype=np.int32)
    result[np.ix_(face_dofs, face_dofs)] = face_coefficient_transform(
        degree,
        permutation,
    )
    return np.ascontiguousarray(result)


@lru_cache(maxsize=24)
def build_quad_d4_trace_transform_pair(
    degree: int,
    vertex_permutation: tuple[int, int, int, int],
) -> QuadD4TraceTransformPair:
    """Build a complete affine-Piola D4 transform and cross-check Task033."""

    degree = int(degree)
    permutation = tuple(map(int, vertex_permutation))
    if degree not in {4, 5, 6}:
        raise ValueError("Task035d D4 traces qualify p4/p5/p6 only")
    if permutation not in quadrilateral_d4_vertex_permutations():
        raise ValueError("vertex permutation is not a quadrilateral D4 symmetry")
    offset, jacobian = _quad_affine_chart(permutation)
    hcurl = _hcurl_element(degree)
    h1 = _h1_element(degree)
    hcurl_coefficients = _affine_pullback_restriction(
        hcurl,
        hcurl,
        offset=offset,
        jacobian=jacobian,
    )
    h1_coefficients = _affine_pullback_restriction(
        h1,
        h1,
        offset=offset,
        jacobian=jacobian,
    )
    expected_hcurl = _expected_hcurl_d4_transform(
        degree,
        permutation,
    )
    gradient = _discrete_gradient(h1, hcurl)
    commuting_error = float(
        np.max(
            np.abs(
                hcurl_coefficients @ gradient
                - gradient @ h1_coefficients
            ),
            initial=0.0,
        )
    )
    hcurl_inverse_error = float(
        np.max(
            np.abs(
                hcurl_coefficients.conj().T @ hcurl_coefficients
                - np.eye(int(hcurl.dim))
            ),
            initial=0.0,
        )
    )
    h1_inverse_error = float(
        np.max(
            np.abs(
                h1_coefficients.conj().T @ h1_coefficients
                - np.eye(int(h1.dim))
            ),
            initial=0.0,
        )
    )
    task033_mismatch = float(
        np.max(
            np.abs(hcurl_coefficients - expected_hcurl),
            initial=0.0,
        )
    )
    checks = {
        "affine_chart_is_d4": abs(abs(np.linalg.det(jacobian)) - 1.0)
        <= 1.0e-14,
        "hcurl_transform_is_orthogonal": hcurl_inverse_error <= 5.0e-12,
        "h1_transform_is_orthogonal": h1_inverse_error <= 5.0e-12,
        "d4_gradient_commutes": commuting_error <= 5.0e-11,
        "matches_task033_edge_face_blocks": task033_mismatch <= 5.0e-12,
    }
    failures = [name for name, passed in checks.items() if not passed]
    for matrix in (hcurl_coefficients, h1_coefficients):
        matrix.setflags(write=False)
    audit = MappingProxyType(
        {
            "schema_version": "task035d.quad-d4-trace-transform.v1",
            "status": (
                "quad_d4_trace_transform_pass"
                if not failures
                else "quad_d4_trace_transform_fail"
            ),
            "pass": not failures,
            "degree": degree,
            "vertex_permutation": list(permutation),
            "face_info": quadrilateral_face_info(permutation),
            "offset": offset.tolist(),
            "jacobian": jacobian.tolist(),
            "jacobian_determinant": float(np.linalg.det(jacobian)),
            "hcurl_inverse_error": hcurl_inverse_error,
            "h1_inverse_error": h1_inverse_error,
            "gradient_commuting_error": commuting_error,
            "task033_block_mismatch": task033_mismatch,
            "hcurl_sha256": _matrix_sha256(hcurl_coefficients),
            "h1_sha256": _matrix_sha256(h1_coefficients),
            "checks": checks,
            "failures": failures,
            "ordinary_default_changed": False,
        }
    )
    return QuadD4TraceTransformPair(
        degree=degree,
        vertex_permutation=permutation,
        face_info=quadrilateral_face_info(permutation),
        hcurl_coefficients=hcurl_coefficients,
        h1_coefficients=h1_coefficients,
        audit=audit,
    )


@dataclass(frozen=True)
class OrientedQuadChildTraceRestriction:
    """One child restriction expressed in arbitrary coarse/fine D4 charts."""

    degree: int
    quadrant: tuple[int, int]
    coarse_vertex_permutation: tuple[int, int, int, int]
    fine_vertex_permutation: tuple[int, int, int, int]
    hcurl_from_parent: np.ndarray
    h1_from_parent: np.ndarray
    audit: Mapping[str, Any]


@lru_cache(maxsize=768)
def build_oriented_quad_child_trace_restriction(
    degree: int,
    quadrant: tuple[int, int],
    coarse_vertex_permutation: tuple[int, int, int, int],
    fine_vertex_permutation: tuple[int, int, int, int],
) -> OrientedQuadChildTraceRestriction:
    """Conjugate one canonical child map by complete D4 trace transforms."""

    canonical = build_quad_child_trace_restriction(degree, quadrant)
    coarse = build_quad_d4_trace_transform_pair(
        degree,
        coarse_vertex_permutation,
    )
    fine = build_quad_d4_trace_transform_pair(
        degree,
        fine_vertex_permutation,
    )
    hcurl_restriction = np.ascontiguousarray(
        fine.hcurl_coefficients
        @ canonical.hcurl_from_parent
        @ coarse.hcurl_coefficients.conj().T
    )
    h1_restriction = np.ascontiguousarray(
        fine.h1_coefficients
        @ canonical.h1_from_parent
        @ coarse.h1_coefficients.conj().T
    )
    hcurl = _hcurl_element(int(degree))
    h1 = _h1_element(int(degree))
    gradient = _discrete_gradient(h1, hcurl)
    coarse_gradient = (
        coarse.hcurl_coefficients
        @ gradient
        @ coarse.h1_coefficients.conj().T
    )
    fine_gradient = (
        fine.hcurl_coefficients
        @ gradient
        @ fine.h1_coefficients.conj().T
    )
    commuting_error = float(
        np.max(
            np.abs(
                hcurl_restriction @ coarse_gradient
                - fine_gradient @ h1_restriction
            ),
            initial=0.0,
        )
    )
    singular_values = np.linalg.svd(
        hcurl_restriction,
        compute_uv=False,
    )
    rank_tolerance = (
        singular_values[0]
        * max(hcurl_restriction.shape)
        * np.finfo(np.float64).eps
    )
    rank = int(np.count_nonzero(singular_values > rank_tolerance))
    condition = float(singular_values[0] / singular_values[-1])
    canonical_condition = float(
        np.linalg.cond(canonical.hcurl_from_parent)
    )
    condition_relative_drift = abs(
        condition - canonical_condition
    ) / max(canonical_condition, 1.0)
    checks = {
        "coarse_d4_pass": coarse.audit["pass"] is True,
        "fine_d4_pass": fine.audit["pass"] is True,
        "full_column_rank": rank == int(hcurl.dim),
        "condition_is_d4_invariant": condition_relative_drift <= 1.0e-7,
        "oriented_child_commutes": commuting_error <= 5.0e-11,
    }
    failures = [name for name, passed in checks.items() if not passed]
    for matrix in (hcurl_restriction, h1_restriction):
        matrix.setflags(write=False)
    audit = MappingProxyType(
        {
            "schema_version": "task035d.oriented-quad-child-trace.v1",
            "status": (
                "oriented_quad_child_trace_pass"
                if not failures
                else "oriented_quad_child_trace_fail"
            ),
            "pass": not failures,
            "degree": int(degree),
            "quadrant": list(map(int, quadrant)),
            "coarse_vertex_permutation": list(
                map(int, coarse_vertex_permutation)
            ),
            "fine_vertex_permutation": list(
                map(int, fine_vertex_permutation)
            ),
            "rank": rank,
            "condition_number": condition,
            "canonical_condition_number": canonical_condition,
            "condition_relative_drift": condition_relative_drift,
            "commuting_error": commuting_error,
            "hcurl_sha256": _matrix_sha256(hcurl_restriction),
            "h1_sha256": _matrix_sha256(h1_restriction),
            "checks": checks,
            "failures": failures,
            "pde_accuracy_credit": False,
            "ordinary_default_changed": False,
        }
    )
    return OrientedQuadChildTraceRestriction(
        degree=int(degree),
        quadrant=tuple(map(int, quadrant)),
        coarse_vertex_permutation=tuple(
            map(int, coarse_vertex_permutation)
        ),
        fine_vertex_permutation=tuple(map(int, fine_vertex_permutation)),
        hcurl_from_parent=hcurl_restriction,
        h1_from_parent=h1_restriction,
        audit=audit,
    )


def _aggregate_local_rows(
    element: basix.finite_element.FiniteElement,
    *,
    family: str,
    degree: int,
) -> tuple[tuple[np.ndarray, ...], int]:
    topology = basix.topology(basix.CellType.quadrilateral)
    geometry = np.asarray(
        basix.geometry(basix.CellType.quadrilateral),
        dtype=np.int32,
    )
    vertex_keys = sorted(
        {
            (
                quadrant[0] + int(vertex[0]),
                quadrant[1] + int(vertex[1]),
            )
            for quadrant in _QUADRANTS
            for vertex in geometry
        }
    )
    edge_keys = sorted(
        {
            tuple(
                sorted(
                    (
                        (
                            quadrant[0] + int(geometry[vertices[0], 0]),
                            quadrant[1] + int(geometry[vertices[0], 1]),
                        ),
                        (
                            quadrant[0] + int(geometry[vertices[1], 0]),
                            quadrant[1] + int(geometry[vertices[1], 1]),
                        ),
                    )
                )
            )
            for quadrant in _QUADRANTS
            for vertices in topology[1]
        }
    )
    next_row = 0
    vertex_rows: dict[tuple[int, int], np.ndarray] = {}
    if family == "h1":
        for key in vertex_keys:
            vertex_rows[key] = np.asarray([next_row], dtype=np.int64)
            next_row += 1
    edge_mode_count = degree if family == "hcurl" else degree - 1
    edge_rows: dict[
        tuple[tuple[int, int], tuple[int, int]],
        np.ndarray,
    ] = {}
    for key in edge_keys:
        edge_rows[key] = np.arange(
            next_row,
            next_row + edge_mode_count,
            dtype=np.int64,
        )
        next_row += edge_mode_count
    face_mode_count = (
        2 * degree * (degree - 1)
        if family == "hcurl"
        else (degree - 1) ** 2
    )
    face_rows: dict[tuple[int, int], np.ndarray] = {}
    for quadrant in _QUADRANTS:
        face_rows[quadrant] = np.arange(
            next_row,
            next_row + face_mode_count,
            dtype=np.int64,
        )
        next_row += face_mode_count

    child_rows: list[np.ndarray] = []
    for quadrant in _QUADRANTS:
        local = np.full(int(element.dim), -1, dtype=np.int64)
        if family == "h1":
            for entity, vertex in enumerate(geometry):
                key = (
                    quadrant[0] + int(vertex[0]),
                    quadrant[1] + int(vertex[1]),
                )
                dofs = np.asarray(element.entity_dofs[0][entity])
                if len(dofs) != 1:
                    raise RuntimeError("H1 vertex moment count changed")
                local[dofs] = vertex_rows[key]
        for entity, vertices in enumerate(topology[1]):
            ordered = (
                (
                    quadrant[0] + int(geometry[vertices[0], 0]),
                    quadrant[1] + int(geometry[vertices[0], 1]),
                ),
                (
                    quadrant[0] + int(geometry[vertices[1], 0]),
                    quadrant[1] + int(geometry[vertices[1], 1]),
                ),
            )
            key = tuple(sorted(ordered))
            if ordered != key:
                raise RuntimeError(
                    "Attempt1 child edge orientation is not canonical"
                )
            dofs = np.asarray(element.entity_dofs[1][entity])
            if len(dofs) != edge_mode_count:
                raise RuntimeError("quadrilateral edge mode count changed")
            local[dofs] = edge_rows[key]
        face_dofs = np.asarray(element.entity_dofs[2][0])
        if len(face_dofs) != face_mode_count:
            raise RuntimeError("quadrilateral face mode count changed")
        local[face_dofs] = face_rows[quadrant]
        if np.any(local < 0) or len(np.unique(local)) != int(element.dim):
            raise RuntimeError("child aggregate row map is incomplete")
        local.setflags(write=False)
        child_rows.append(local)
    return tuple(child_rows), next_row


def _merge_child_matrices(
    child_rows: tuple[np.ndarray, ...],
    child_matrices: tuple[np.ndarray, ...],
    *,
    aggregate_rows: int,
) -> tuple[np.ndarray, float]:
    columns = child_matrices[0].shape[1]
    result = np.zeros((aggregate_rows, columns), dtype=np.float64)
    assigned = np.zeros(aggregate_rows, dtype=bool)
    maximum_mismatch = 0.0
    for rows, matrix in zip(child_rows, child_matrices, strict=True):
        if matrix.shape[0] != len(rows) or matrix.shape[1] != columns:
            raise RuntimeError("child restriction shape does not match rows")
        for local_row, global_row in enumerate(rows):
            values = matrix[local_row]
            if assigned[global_row]:
                maximum_mismatch = max(
                    maximum_mismatch,
                    float(
                        np.max(
                            np.abs(result[global_row] - values),
                            initial=0.0,
                        )
                    ),
                )
            else:
                result[global_row] = values
                assigned[global_row] = True
    if not np.all(assigned):
        raise RuntimeError("aggregate restriction has an unassigned row")
    return result, maximum_mismatch


def _discrete_gradient(
    scalar: basix.finite_element.FiniteElement,
    hcurl: basix.finite_element.FiniteElement,
) -> np.ndarray:
    points = np.asarray(hcurl.points)
    table = np.asarray(scalar.tabulate(1, points))
    topological_dimension = int(points.shape[1])
    if table.shape[:2] != (topological_dimension + 1, len(points)):
        raise RuntimeError(
            "unexpected scalar derivative tabulation for discrete gradient"
        )
    gradient = np.stack(
        tuple(
            table[axis + 1, :, :, 0]
            for axis in range(topological_dimension)
        ),
        axis=2,
    )
    flattened = np.ascontiguousarray(
        gradient.transpose(2, 0, 1)
    ).reshape(
        topological_dimension * len(points),
        int(scalar.dim),
    )
    return np.ascontiguousarray(
        np.asarray(hcurl.interpolation_matrix) @ flattened
    )


@dataclass(frozen=True)
class HexaFaceTracePair:
    """Exact trace maps from one hexahedron face closure to a quad."""

    degree: int
    local_face: int
    normal_axis: int
    side: int
    tangential_axes: tuple[int, int]
    hcurl_closure_dofs: np.ndarray
    h1_closure_dofs: np.ndarray
    hcurl_trace_from_cell: np.ndarray
    h1_trace_from_cell: np.ndarray
    hcurl_trace_from_closure: np.ndarray
    h1_trace_from_closure: np.ndarray
    audit: Mapping[str, Any]


def _hexa_elements(
    degree: int,
) -> tuple[
    basix.finite_element.FiniteElement,
    basix.finite_element.FiniteElement,
]:
    return (
        basix.ufl.element(
            "N1curl",
            "hexahedron",
            int(degree),
        ).basix_element,
        basix.ufl.element(
            "Lagrange",
            "hexahedron",
            int(degree),
            lagrange_variant=basix.LagrangeVariant.gll_warped,
        ).basix_element,
    )


def _hexa_face_chart(
    local_face: int,
) -> tuple[int, int, tuple[int, int]]:
    local_face = int(local_face)
    topology = basix.topology(basix.CellType.hexahedron)
    geometry = np.asarray(
        basix.geometry(basix.CellType.hexahedron),
        dtype=np.float64,
    )
    if not 0 <= local_face < len(topology[2]):
        raise ValueError("hexahedron local face must be in [0, 5]")
    vertices = np.asarray(topology[2][local_face], dtype=np.int32)
    points = geometry[vertices]
    fixed_axes = [
        axis
        for axis in range(3)
        if np.all(points[:, axis] == points[0, axis])
    ]
    if len(fixed_axes) != 1 or points[0, fixed_axes[0]] not in {0.0, 1.0}:
        raise RuntimeError("Basix hexahedron face is not axis aligned")
    normal_axis = fixed_axes[0]
    side = int(points[0, normal_axis])
    tangential_axes = tuple(
        axis for axis in range(3) if axis != normal_axis
    )
    return normal_axis, side, tangential_axes  # type: ignore[return-value]


def _trace_from_hexa(
    source: basix.finite_element.FiniteElement,
    target: basix.finite_element.FiniteElement,
    *,
    normal_axis: int,
    side: int,
    tangential_axes: tuple[int, int],
) -> np.ndarray:
    target_points = np.asarray(target.points, dtype=np.float64)
    embedded = np.zeros((len(target_points), 3), dtype=np.float64)
    embedded[:, normal_axis] = float(side)
    embedded[:, tangential_axes[0]] = target_points[:, 0]
    embedded[:, tangential_axes[1]] = target_points[:, 1]
    values = np.asarray(source.tabulate(0, embedded)[0])
    if source.map_type == basix.MapType.covariantPiola:
        values = np.ascontiguousarray(
            values[..., np.asarray(tangential_axes, dtype=np.int32)]
        )
    elif source.map_type != basix.MapType.identity:
        raise NotImplementedError(
            f"unsupported hexahedron trace map {source.map_type}"
        )
    flattened = _flatten_interpolation_values(values)
    interpolation = np.asarray(target.interpolation_matrix)
    if interpolation.shape[1] != flattened.shape[0]:
        raise RuntimeError("hexahedron trace interpolation layout changed")
    return np.ascontiguousarray(interpolation @ flattened)


@lru_cache(maxsize=18)
def build_hexa_face_trace_pair(
    degree: int,
    local_face: int,
) -> HexaFaceTracePair:
    """Qualify one of the six hexahedron-to-quadrilateral trace charts."""

    degree = int(degree)
    local_face = int(local_face)
    if degree not in {4, 5, 6}:
        raise ValueError("Task035d hexa traces qualify p4/p5/p6 only")
    normal_axis, side, tangential_axes = _hexa_face_chart(local_face)
    hcurl_hexa, h1_hexa = _hexa_elements(degree)
    hcurl_quad = _hcurl_element(degree)
    h1_quad = _h1_element(degree)
    hcurl_trace = _trace_from_hexa(
        hcurl_hexa,
        hcurl_quad,
        normal_axis=normal_axis,
        side=side,
        tangential_axes=tangential_axes,
    )
    h1_trace = _trace_from_hexa(
        h1_hexa,
        h1_quad,
        normal_axis=normal_axis,
        side=side,
        tangential_axes=tangential_axes,
    )
    hcurl_closure = np.asarray(
        hcurl_hexa.entity_closure_dofs[2][local_face],
        dtype=np.int32,
    )
    h1_closure = np.asarray(
        h1_hexa.entity_closure_dofs[2][local_face],
        dtype=np.int32,
    )
    hcurl_closure_map = np.ascontiguousarray(
        hcurl_trace[:, hcurl_closure]
    )
    h1_closure_map = np.ascontiguousarray(h1_trace[:, h1_closure])
    hcurl_outside = np.delete(
        hcurl_trace,
        hcurl_closure,
        axis=1,
    )
    h1_outside = np.delete(h1_trace, h1_closure, axis=1)
    hcurl_rank = int(np.linalg.matrix_rank(hcurl_closure_map))
    h1_rank = int(np.linalg.matrix_rank(h1_closure_map))
    hcurl_condition = float(np.linalg.cond(hcurl_closure_map))
    h1_condition = float(np.linalg.cond(h1_closure_map))
    gradient_hexa = _discrete_gradient(h1_hexa, hcurl_hexa)
    gradient_quad = _discrete_gradient(h1_quad, hcurl_quad)
    commuting_error = float(
        np.max(
            np.abs(
                hcurl_trace @ gradient_hexa
                - gradient_quad @ h1_trace
            ),
            initial=0.0,
        )
    )
    hcurl_outside_max = float(
        np.max(np.abs(hcurl_outside), initial=0.0)
    )
    h1_outside_max = float(np.max(np.abs(h1_outside), initial=0.0))
    checks = {
        "hcurl_trace_uses_face_closure_only": hcurl_outside_max <= 5.0e-12,
        "h1_trace_uses_face_closure_only": h1_outside_max <= 5.0e-12,
        "hcurl_closure_isomorphism": (
            hcurl_closure_map.shape
            == (int(hcurl_quad.dim), int(hcurl_quad.dim))
            and hcurl_rank == int(hcurl_quad.dim)
        ),
        "h1_closure_isomorphism": (
            h1_closure_map.shape == (int(h1_quad.dim), int(h1_quad.dim))
            and h1_rank == int(h1_quad.dim)
        ),
        "hcurl_closure_condition": hcurl_condition <= 1.0 + 5.0e-11,
        "h1_closure_condition": h1_condition <= 1.0 + 5.0e-11,
        "hexa_trace_gradient_commutes": commuting_error <= 5.0e-11,
    }
    failures = [name for name, passed in checks.items() if not passed]
    for matrix in (
        hcurl_closure,
        h1_closure,
        hcurl_trace,
        h1_trace,
        hcurl_closure_map,
        h1_closure_map,
    ):
        matrix.setflags(write=False)
    audit = MappingProxyType(
        {
            "schema_version": "task035d.hexa-face-trace-pair.v1",
            "status": (
                "hexa_face_trace_pair_pass"
                if not failures
                else "hexa_face_trace_pair_fail"
            ),
            "pass": not failures,
            "degree": degree,
            "local_face": local_face,
            "normal_axis": normal_axis,
            "side": side,
            "tangential_axes": list(tangential_axes),
            "hcurl_trace_dimension": int(hcurl_quad.dim),
            "h1_trace_dimension": int(h1_quad.dim),
            "hcurl_trace_rank": hcurl_rank,
            "h1_trace_rank": h1_rank,
            "hcurl_trace_condition_number": hcurl_condition,
            "h1_trace_condition_number": h1_condition,
            "hcurl_outside_closure_max": hcurl_outside_max,
            "h1_outside_closure_max": h1_outside_max,
            "gradient_commuting_error": commuting_error,
            "hcurl_closure_map_sha256": _matrix_sha256(
                hcurl_closure_map
            ),
            "h1_closure_map_sha256": _matrix_sha256(h1_closure_map),
            "checks": checks,
            "failures": failures,
            "pde_accuracy_credit": False,
            "ordinary_default_changed": False,
        }
    )
    return HexaFaceTracePair(
        degree=degree,
        local_face=local_face,
        normal_axis=normal_axis,
        side=side,
        tangential_axes=tangential_axes,
        hcurl_closure_dofs=hcurl_closure,
        h1_closure_dofs=h1_closure,
        hcurl_trace_from_cell=hcurl_trace,
        h1_trace_from_cell=h1_trace,
        hcurl_trace_from_closure=hcurl_closure_map,
        h1_trace_from_closure=h1_closure_map,
        audit=audit,
    )


@lru_cache(maxsize=3)
def build_oriented_hanging_face_reference_catalog(
    degree: int,
) -> Mapping[str, Any]:
    """Audit all six face charts and all coarse/fine D4 child maps."""

    degree = int(degree)
    faces = tuple(
        build_hexa_face_trace_pair(degree, local_face)
        for local_face in range(6)
    )
    permutations = tuple(
        sorted(quadrilateral_d4_vertex_permutations())
    )
    oriented_count = 0
    maximum_commuting_error = 0.0
    maximum_condition_drift = 0.0
    oriented_hashes: list[str] = []
    for quadrant in _QUADRANTS:
        for coarse_permutation in permutations:
            for fine_permutation in permutations:
                row = build_oriented_quad_child_trace_restriction(
                    degree,
                    quadrant,
                    coarse_permutation,
                    fine_permutation,
                )
                if row.audit["pass"] is not True:
                    raise RuntimeError(
                        "one oriented hanging child restriction failed"
                    )
                oriented_count += 1
                maximum_commuting_error = max(
                    maximum_commuting_error,
                    float(row.audit["commuting_error"]),
                )
                maximum_condition_drift = max(
                    maximum_condition_drift,
                    float(row.audit["condition_relative_drift"]),
                )
                oriented_hashes.append(
                    str(row.audit["hcurl_sha256"])
                )
    checks = {
        "all_six_hexa_faces_pass": all(
            face.audit["pass"] is True for face in faces
        ),
        "all_d4_child_combinations_pass": oriented_count == 4 * 8 * 8,
        "oriented_child_commuting": maximum_commuting_error <= 5.0e-11,
        "d4_condition_invariance": maximum_condition_drift <= 1.0e-7,
    }
    failures = [name for name, passed in checks.items() if not passed]
    payload = {
        "schema_version": "task035d.oriented-hanging-face-catalog.v1",
        "status": (
            "oriented_hanging_face_catalog_pass"
            if not failures
            else "oriented_hanging_face_catalog_fail"
        ),
        "pass": not failures,
        "degree": degree,
        "hexa_face_count": len(faces),
        "d4_permutation_count": len(permutations),
        "oriented_child_combination_count": oriented_count,
        "maximum_hexa_trace_commuting_error": max(
            float(face.audit["gradient_commuting_error"])
            for face in faces
        ),
        "maximum_oriented_child_commuting_error": (
            maximum_commuting_error
        ),
        "maximum_d4_condition_relative_drift": maximum_condition_drift,
        "hexa_face_hcurl_sha256": [
            str(face.audit["hcurl_closure_map_sha256"])
            for face in faces
        ],
        "oriented_child_catalog_sha256": hashlib.sha256(
            "".join(oriented_hashes).encode("ascii")
        ).hexdigest(),
        "checks": checks,
        "failures": failures,
        "shared_fine_edges_require_global_entity_orientation": True,
        "mpi_ownership_qualified": False,
        "pde_accuracy_credit": False,
        "ordinary_default_changed": False,
    }
    return MappingProxyType(payload)


def _aggregate_gradient(
    hcurl_rows: tuple[np.ndarray, ...],
    h1_rows: tuple[np.ndarray, ...],
    local_gradient: np.ndarray,
    *,
    hcurl_dimension: int,
    h1_dimension: int,
) -> tuple[np.ndarray, float]:
    result = np.zeros(
        (hcurl_dimension, h1_dimension),
        dtype=np.float64,
    )
    assigned = np.zeros(hcurl_dimension, dtype=bool)
    maximum_mismatch = 0.0
    for curl_rows, scalar_rows in zip(
        hcurl_rows,
        h1_rows,
        strict=True,
    ):
        for local_row, global_row in enumerate(curl_rows):
            values = np.zeros(h1_dimension, dtype=np.float64)
            values[scalar_rows] = local_gradient[local_row]
            if assigned[global_row]:
                maximum_mismatch = max(
                    maximum_mismatch,
                    float(
                        np.max(
                            np.abs(result[global_row] - values),
                            initial=0.0,
                        )
                    ),
                )
            else:
                result[global_row] = values
                assigned[global_row] = True
    if not np.all(assigned):
        raise RuntimeError("aggregate discrete gradient has an unassigned row")
    return result, maximum_mismatch


def _curl_gradient_error(
    hcurl: basix.finite_element.FiniteElement,
    gradient: np.ndarray,
) -> float:
    axis = (
        np.polynomial.legendre.leggauss(
            max(int(hcurl.embedded_superdegree) + 2, 7)
        )[0]
        + 1.0
    ) / 2.0
    points = np.asarray(
        [(x, y) for x in axis for y in axis],
        dtype=np.float64,
    )
    table = np.asarray(hcurl.tabulate(1, points))
    curl = table[1, :, :, 1] - table[2, :, :, 0]
    return float(
        np.max(np.abs(curl @ gradient), initial=0.0)
    )


@dataclass(frozen=True)
class HangingFaceReferencePair:
    """Unique fine-face H(curl)/H1 restrictions and commuting authority."""

    degree: int
    quadrants: tuple[QuadChildTraceRestriction, ...]
    hcurl_unique_fine_from_coarse: np.ndarray
    h1_unique_fine_from_coarse: np.ndarray
    coarse_discrete_gradient: np.ndarray
    fine_discrete_gradient: np.ndarray
    hcurl_child_rows: tuple[np.ndarray, ...]
    h1_child_rows: tuple[np.ndarray, ...]
    audit: Mapping[str, Any]


@lru_cache(maxsize=3)
def build_hanging_face_reference_pair(
    degree: int = 4,
) -> HangingFaceReferencePair:
    """Build and audit the unique four-child hanging-face restriction."""

    degree = int(degree)
    quadrants = tuple(
        build_quad_child_trace_restriction(degree, quadrant)
        for quadrant in _QUADRANTS
    )
    hcurl = _hcurl_element(degree)
    h1 = _h1_element(degree)
    hcurl_rows, fine_hcurl_dimension = _aggregate_local_rows(
        hcurl,
        family="hcurl",
        degree=degree,
    )
    h1_rows, fine_h1_dimension = _aggregate_local_rows(
        h1,
        family="h1",
        degree=degree,
    )
    hcurl_restriction, hcurl_shared_mismatch = _merge_child_matrices(
        hcurl_rows,
        tuple(row.hcurl_from_parent for row in quadrants),
        aggregate_rows=fine_hcurl_dimension,
    )
    h1_restriction, h1_shared_mismatch = _merge_child_matrices(
        h1_rows,
        tuple(row.h1_from_parent for row in quadrants),
        aggregate_rows=fine_h1_dimension,
    )
    coarse_gradient = _discrete_gradient(h1, hcurl)
    fine_gradient, gradient_shared_mismatch = _aggregate_gradient(
        hcurl_rows,
        h1_rows,
        coarse_gradient,
        hcurl_dimension=fine_hcurl_dimension,
        h1_dimension=fine_h1_dimension,
    )
    child_commuting_errors = []
    for row in quadrants:
        child_commuting_errors.append(
            float(
                np.max(
                    np.abs(
                        row.hcurl_from_parent @ coarse_gradient
                        - coarse_gradient @ row.h1_from_parent
                    ),
                    initial=0.0,
                )
            )
        )
    commuting_error = float(
        np.max(
            np.abs(
                hcurl_restriction @ coarse_gradient
                - fine_gradient @ h1_restriction
            ),
            initial=0.0,
        )
    )
    singular_values = np.linalg.svd(
        hcurl_restriction,
        compute_uv=False,
    )
    rank_tolerance = (
        singular_values[0]
        * max(hcurl_restriction.shape)
        * np.finfo(np.float64).eps
    )
    restriction_rank = int(
        np.count_nonzero(singular_values > rank_tolerance)
    )
    restriction_condition = float(
        singular_values[0] / singular_values[-1]
    )
    gradient_singular_values = np.linalg.svd(
        fine_gradient,
        compute_uv=False,
    )
    gradient_tolerance = (
        gradient_singular_values[0]
        * max(fine_gradient.shape)
        * np.finfo(np.float64).eps
    )
    gradient_rank = int(
        np.count_nonzero(
            gradient_singular_values > gradient_tolerance
        )
    )
    curl_gradient_error = _curl_gradient_error(hcurl, coarse_gradient)
    expected_hcurl_dimension = 4 * degree * (2 * degree + 1)
    expected_h1_dimension = (2 * degree + 1) ** 2
    checks = {
        "production_hcurl_variant": (
            hcurl.lagrange_variant == basix.LagrangeVariant.legendre
        ),
        "production_h1_variant": (
            h1.lagrange_variant == basix.LagrangeVariant.gll_warped
        ),
        "unique_hcurl_dimension": (
            hcurl_restriction.shape
            == (expected_hcurl_dimension, int(hcurl.dim))
        ),
        "unique_h1_dimension": (
            h1_restriction.shape
            == (expected_h1_dimension, int(h1.dim))
        ),
        "hcurl_restriction_full_column_rank": (
            restriction_rank == int(hcurl.dim)
        ),
        "hcurl_restriction_condition": (
            restriction_condition < (50.0 if degree == 4 else 150.0)
        ),
        "shared_child_hcurl_rows_match": hcurl_shared_mismatch <= 2.0e-12,
        "shared_child_h1_rows_match": h1_shared_mismatch <= 2.0e-12,
        "shared_child_gradient_rows_match": (
            gradient_shared_mismatch <= 2.0e-12
        ),
        "child_commuting": max(child_commuting_errors) <= 5.0e-11,
        "unique_commuting": commuting_error <= 5.0e-11,
        "fine_gradient_exact_rank": (
            gradient_rank == fine_h1_dimension - 1
        ),
        "curl_grad": curl_gradient_error <= 2.0e-10,
    }
    failures = [name for name, passed in checks.items() if not passed]
    for matrix in (
        hcurl_restriction,
        h1_restriction,
        coarse_gradient,
        fine_gradient,
    ):
        matrix.setflags(write=False)
    audit = MappingProxyType(
        {
            "schema_version": "task035d.hanging-face-reference-pair.v1",
            "status": (
                "hanging_face_reference_pair_pass"
                if not failures
                else "hanging_face_reference_pair_fail"
            ),
            "pass": not failures,
            "degree": degree,
            "checks": checks,
            "failures": failures,
            "coarse_hcurl_dimension": int(hcurl.dim),
            "unique_fine_hcurl_dimension": fine_hcurl_dimension,
            "coarse_h1_dimension": int(h1.dim),
            "unique_fine_h1_dimension": fine_h1_dimension,
            "hcurl_restriction_rank": restriction_rank,
            "hcurl_restriction_rank_tolerance": rank_tolerance,
            "hcurl_restriction_condition_number": restriction_condition,
            "fine_discrete_gradient_rank": gradient_rank,
            "fine_discrete_gradient_expected_rank": (
                fine_h1_dimension - 1
            ),
            "maximum_child_commuting_error": max(
                child_commuting_errors
            ),
            "unique_commuting_error": commuting_error,
            "curl_grad_maximum_error": curl_gradient_error,
            "shared_child_hcurl_row_mismatch": hcurl_shared_mismatch,
            "shared_child_h1_row_mismatch": h1_shared_mismatch,
            "shared_child_gradient_row_mismatch": (
                gradient_shared_mismatch
            ),
            "hcurl_restriction_sha256": _matrix_sha256(
                hcurl_restriction
            ),
            "h1_restriction_sha256": _matrix_sha256(h1_restriction),
            "coarse_gradient_sha256": _matrix_sha256(coarse_gradient),
            "fine_gradient_sha256": _matrix_sha256(fine_gradient),
            "constraint_class": (
                "one_level_uniform_p_hanging_face_component"
            ),
            "mpi_ownership_qualified": False,
            "pde_accuracy_credit": False,
            "ordinary_default_changed": False,
        }
    )
    return HangingFaceReferencePair(
        degree=degree,
        quadrants=quadrants,
        hcurl_unique_fine_from_coarse=hcurl_restriction,
        h1_unique_fine_from_coarse=h1_restriction,
        coarse_discrete_gradient=coarse_gradient,
        fine_discrete_gradient=fine_gradient,
        hcurl_child_rows=hcurl_rows,
        h1_child_rows=h1_rows,
        audit=audit,
    )


def random_hanging_static_condensation_audit(
    pair: HangingFaceReferencePair,
    *,
    seed: int = 350197,
    interior_rows_per_child: int = 5,
) -> dict[str, Any]:
    """Compare local condensation-then-constraint with one-shot algebra."""

    if pair.audit["pass"] is not True:
        raise ValueError("hanging reference pair must pass before Schur audit")
    interior_rows_per_child = int(interior_rows_per_child)
    if interior_rows_per_child < 1:
        raise ValueError("random Schur fixture needs positive interiors")
    rng = np.random.default_rng(int(seed))
    trace_rows = pair.hcurl_unique_fine_from_coarse.shape[0]
    coarse_rows = pair.hcurl_unique_fine_from_coarse.shape[1]
    interior_rows = len(_QUADRANTS) * interior_rows_per_child
    full_rows = trace_rows + interior_rows
    matrix = np.zeros((full_rows, full_rows), dtype=np.complex128)
    condensed_trace = np.zeros(
        (trace_rows, trace_rows),
        dtype=np.complex128,
    )
    for child, child_trace_rows in enumerate(pair.hcurl_child_rows):
        local_size = len(child_trace_rows) + interior_rows_per_child
        raw = (
            rng.standard_normal((local_size, local_size))
            + 1j * rng.standard_normal((local_size, local_size))
        )
        local = raw.conj().T @ raw + (2.0 + child) * np.eye(local_size)
        child_interior_rows = np.arange(
            trace_rows + child * interior_rows_per_child,
            trace_rows + (child + 1) * interior_rows_per_child,
            dtype=np.int64,
        )
        rows = np.concatenate((child_trace_rows, child_interior_rows))
        matrix[np.ix_(rows, rows)] += local
        split = len(child_trace_rows)
        local_trace = local[:split, :split]
        trace_interior = local[:split, split:]
        interior_trace = local[split:, :split]
        interior = local[split:, split:]
        schur = (
            local_trace
            - trace_interior
            @ np.linalg.solve(interior, interior_trace)
        )
        condensed_trace[
            np.ix_(child_trace_rows, child_trace_rows)
        ] += schur

    expansion = np.zeros(
        (full_rows, coarse_rows + interior_rows),
        dtype=np.complex128,
    )
    expansion[:trace_rows, :coarse_rows] = (
        pair.hcurl_unique_fine_from_coarse
    )
    expansion[
        trace_rows:,
        coarse_rows:,
    ] = np.eye(interior_rows)
    constrained = expansion.conj().T @ matrix @ expansion
    constrained_trace = constrained[:coarse_rows, :coarse_rows]
    constrained_trace_interior = constrained[
        :coarse_rows,
        coarse_rows:,
    ]
    constrained_interior_trace = constrained[
        coarse_rows:,
        :coarse_rows,
    ]
    constrained_interior = constrained[
        coarse_rows:,
        coarse_rows:,
    ]
    one_shot_schur = (
        constrained_trace
        - constrained_trace_interior
        @ np.linalg.solve(
            constrained_interior,
            constrained_interior_trace,
        )
    )
    local_then_hanging = (
        pair.hcurl_unique_fine_from_coarse.conj().T
        @ condensed_trace
        @ pair.hcurl_unique_fine_from_coarse
    )
    scale = max(
        float(np.linalg.norm(one_shot_schur)),
        np.finfo(np.float64).tiny,
    )
    relative_schur_error = float(
        np.linalg.norm(one_shot_schur - local_then_hanging) / scale
    )
    hermitian_error = float(
        np.linalg.norm(
            local_then_hanging - local_then_hanging.conj().T
        )
        / max(
            float(np.linalg.norm(local_then_hanging)),
            np.finfo(np.float64).tiny,
        )
    )
    rhs = (
        rng.standard_normal(coarse_rows)
        + 1j * rng.standard_normal(coarse_rows)
    )
    solution = np.linalg.solve(local_then_hanging, rhs)
    stationarity = float(
        np.linalg.norm(local_then_hanging @ solution - rhs)
        / max(float(np.linalg.norm(rhs)), np.finfo(np.float64).tiny)
    )
    checks = {
        "local_condensation_matches_one_shot": (
            relative_schur_error <= 2.0e-12
        ),
        "reduced_schur_is_hermitian": hermitian_error <= 2.0e-12,
        "reduced_solve_stationarity": stationarity <= 2.0e-12,
        "fine_patch_rows_depend_on_coarse_trace": (
            coarse_rows < trace_rows
            and one_shot_schur.shape == (coarse_rows, coarse_rows)
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "task035d.hanging-static-schur-fixture.v1",
        "status": (
            "hanging_static_schur_fixture_pass"
            if not failures
            else "hanging_static_schur_fixture_fail"
        ),
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "seed": int(seed),
        "child_count": len(_QUADRANTS),
        "local_trace_rows_per_child": len(pair.hcurl_child_rows[0]),
        "unique_fine_patch_trace_rows": trace_rows,
        "independent_coarse_trace_rows": coarse_rows,
        "hanging_constraint_slave_rows": trace_rows,
        "fine_patch_coordinate_excess_over_coarse": (
            trace_rows - coarse_rows
        ),
        "interior_rows_per_child": interior_rows_per_child,
        "relative_schur_error": relative_schur_error,
        "hermitian_error": hermitian_error,
        "stationarity_residual": stationarity,
        "reduced_schur_sha256": _matrix_sha256(local_then_hanging),
        "pde_accuracy_credit": False,
        "ordinary_default_changed": False,
    }


__all__ = [
    "HexaFaceTracePair",
    "HangingFaceReferencePair",
    "OrientedQuadChildTraceRestriction",
    "QuadChildTraceRestriction",
    "QuadD4TraceTransformPair",
    "build_hanging_face_reference_pair",
    "build_hexa_face_trace_pair",
    "build_oriented_hanging_face_reference_catalog",
    "build_oriented_quad_child_trace_restriction",
    "build_quad_child_trace_restriction",
    "build_quad_d4_trace_transform_pair",
    "random_hanging_static_condensation_audit",
]
