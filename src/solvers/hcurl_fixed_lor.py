"""Task040 L0a: fixed p6 local low-order-refined de Rham complex.

This is a research/local-only reference object. It deliberately has no
mesh-refinement framework, Basix/DOLFINx/PETSc/MPI integration, transfer
operator, or Maxwell action. The one fixed ``6 x 6 x 6`` subdivision provides
only canonical entities and oriented sparse incidence matrices for L0a.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.sparse import csr_matrix

__all__ = ("FixedP6LORReferenceComplex", "build_fixed_p6_lor_reference_complex")

_N = 6
_N1 = _N + 1
_EDGE_BLOCK = _N * _N1 * _N1
_FACE_BLOCK = _N * _N * _N1
Key3 = tuple[int, int, int]
EdgeKey = tuple[str, int, int, int]
EdgeLookup = dict[tuple[Key3, Key3], tuple[int, int]]


@dataclass(frozen=True)
class FixedP6LORReferenceComplex:
    """Canonical local complex for one fixed p6 reference hexahedron.

    Keys use integer coordinates in ``[0, 6]^3`` with x varying fastest.
    Edges are positive x/y/z oriented and grouped in that order; faces are
    positive x/y/z normal and grouped in that order. This is not a DOLFINx
    mesh or a production preconditioner.
    """

    vertex_keys: tuple[Key3, ...]
    edge_keys: tuple[EdgeKey, ...]
    face_keys: tuple[EdgeKey, ...]
    cell_keys: tuple[Key3, ...]
    gradient_incidence: csr_matrix
    curl_incidence: csr_matrix
    divergence_incidence: csr_matrix
    audit: dict[str, Any]


def _vertex_id(i: int, j: int, k: int) -> int:
    return i + _N1 * (j + _N1 * k)


def _build_vertices() -> tuple[Key3, ...]:
    return tuple((i, j, k) for k in range(_N1) for j in range(_N1) for i in range(_N1))


def _build_edges() -> tuple[tuple[EdgeKey, ...], EdgeLookup, list[tuple[int, int]]]:
    keys: list[EdgeKey] = []
    endpoints: list[tuple[int, int]] = []
    lookup: EdgeLookup = {}
    limits = {"x": (_N, _N1, _N1), "y": (_N1, _N, _N1), "z": (_N1, _N1, _N)}
    axes = {"x": 0, "y": 1, "z": 2}
    for axis in ("x", "y", "z"):
        for k in range(limits[axis][2]):
            for j in range(limits[axis][1]):
                for i in range(limits[axis][0]):
                    start = (i, j, k)
                    end = list(start)
                    end[axes[axis]] += 1
                    end = tuple(end)
                    edge = len(keys)
                    keys.append((axis, i, j, k))
                    endpoints.append((_vertex_id(*start), _vertex_id(*end)))
                    lookup[(start, end)] = (edge, 1)
                    lookup[(end, start)] = (edge, -1)
    return tuple(keys), lookup, endpoints


def _build_faces(
    edge_lookup: EdgeLookup,
) -> tuple[tuple[EdgeKey, ...], list[tuple[tuple[int, int], ...]]]:
    keys: list[EdgeKey] = []
    boundaries: list[tuple[tuple[int, int], ...]] = []

    def add(axis: str, i: int, j: int, k: int, loop: tuple[Key3, ...]) -> None:
        try:
            boundary = tuple(
                edge_lookup[(first, second)]
                for first, second in zip(loop, (*loop[1:], loop[0]), strict=True)
            )
        except KeyError as exc:
            raise RuntimeError("reference face loop has no canonical edge") from exc
        keys.append((axis, i, j, k))
        boundaries.append(boundary)

    for k in range(_N):
        for j in range(_N):
            for i in range(_N1):
                add(
                    "x", i, j, k,
                    ((i, j, k), (i, j + 1, k), (i, j + 1, k + 1), (i, j, k + 1)),
                )
    for k in range(_N):
        for j in range(_N1):
            for i in range(_N):
                add(
                    "y", i, j, k,
                    ((i, j, k), (i, j, k + 1), (i + 1, j, k + 1), (i + 1, j, k)),
                )
    for k in range(_N1):
        for j in range(_N):
            for i in range(_N):
                add(
                    "z", i, j, k,
                    ((i, j, k), (i + 1, j, k), (i + 1, j + 1, k), (i, j + 1, k)),
                )
    return tuple(keys), boundaries


def _build_cells(
    face_keys: tuple[EdgeKey, ...],
) -> tuple[tuple[Key3, ...], list[tuple[tuple[int, int], ...]]]:
    keys = tuple((i, j, k) for k in range(_N) for j in range(_N) for i in range(_N))
    face_id = {key: index for index, key in enumerate(face_keys)}
    boundaries = []
    for i, j, k in keys:
        boundaries.append(
            (
                (face_id[("x", i, j, k)], -1),
                (face_id[("x", i + 1, j, k)], 1),
                (face_id[("y", i, j, k)], -1),
                (face_id[("y", i, j + 1, k)], 1),
                (face_id[("z", i, j, k)], -1),
                (face_id[("z", i, j, k + 1)], 1),
            )
        )
    return keys, boundaries


def _incidence(
    boundaries: list[tuple[tuple[int, int], ...]], shape: tuple[int, int]
) -> csr_matrix:
    rows: list[int] = []
    columns: list[int] = []
    values: list[int] = []
    for row, boundary in enumerate(boundaries):
        for column, sign in boundary:
            rows.append(row)
            columns.append(column)
            values.append(sign)
    return csr_matrix(
        (np.asarray(values, dtype=np.float64), (rows, columns)), shape=shape
    )


def _numeric_rank(matrix: csr_matrix) -> tuple[int, float]:
    dense = np.asarray(matrix.toarray(), dtype=np.float64)
    singular_values = np.linalg.svd(dense, compute_uv=False)
    tolerance = 0.0 if not singular_values.size else float(
        singular_values[0] * max(dense.shape) * np.finfo(np.float64).eps
    )
    return int(np.count_nonzero(singular_values > tolerance)), tolerance


def _zero_product(left: csr_matrix, right: csr_matrix) -> dict[str, Any]:
    product = (left @ right).tocsr()
    product.eliminate_zeros()
    return {
        "shape": tuple(map(int, product.shape)),
        "nnz": int(product.nnz),
        "max_abs": float(np.max(np.abs(product.data))) if product.nnz else 0.0,
        "zero": bool(product.nnz == 0),
    }


def build_fixed_p6_lor_reference_complex() -> FixedP6LORReferenceComplex:
    """Build and audit the fixed p6 local reference complex."""

    vertex_keys = _build_vertices()
    edge_keys, edge_lookup, edge_endpoints = _build_edges()
    face_keys, face_boundaries = _build_faces(edge_lookup)
    cell_keys, cell_boundaries = _build_cells(face_keys)
    gradient = _incidence(
        [((start, -1), (end, 1)) for start, end in edge_endpoints],
        (len(edge_keys), len(vertex_keys)),
    )
    curl = _incidence(face_boundaries, (len(face_keys), len(edge_keys)))
    divergence = _incidence(cell_boundaries, (len(cell_keys), len(face_keys)))

    ranks: dict[str, int] = {}
    rank_tolerances: dict[str, float] = {}
    for name, matrix in (("G", gradient), ("C", curl), ("D", divergence)):
        ranks[name], rank_tolerances[name] = _numeric_rank(matrix)
    cg = _zero_product(curl, gradient)
    dc = _zero_product(divergence, curl)
    counts = {
        "vertices": len(vertex_keys),
        "edges": len(edge_keys),
        "faces": len(face_keys),
        "cells": len(cell_keys),
    }
    unique = all(
        len(keys) == len(set(keys))
        for keys in (vertex_keys, edge_keys, face_keys, cell_keys)
    )
    local_coverage = (
        all(
            len(boundary) == 4
            and len({edge for edge, _ in boundary}) == 4
            for boundary in face_boundaries
        )
        and all(
            len(boundary) == 6
            and len({face for face, _ in boundary}) == 6
            for boundary in cell_boundaries
        )
    )
    checks = {
        "expected_counts": counts
        == {"vertices": 343, "edges": 882, "faces": 756, "cells": 216},
        "unique_key_coverage": unique,
        "local_incidence_coverage": local_coverage,
        "CG_zero": cg["zero"],
        "DC_zero": dc["zero"],
        "rank_G": ranks["G"] == 342,
        "rank_C": ranks["C"] == 540,
        "rank_D": ranks["D"] == 216,
    }
    audit = {
        "schema_version": "task040.fixed-lor.l0a.v1",
        "scope": "research_local_only_reference_complex",
        "degree": _N,
        "subdivision": (_N, _N, _N),
        "counts": counts,
        "axis_block_counts": {
            "edges": {"x": _EDGE_BLOCK, "y": _EDGE_BLOCK, "z": _EDGE_BLOCK},
            "faces": {"x": _FACE_BLOCK, "y": _FACE_BLOCK, "z": _FACE_BLOCK},
        },
        "matrix_shapes": {name: tuple(map(int, matrix.shape)) for name, matrix in (
            ("G", gradient), ("C", curl), ("D", divergence)
        )},
        "matrix_nnz": {name: int(matrix.nnz) for name, matrix in (
            ("G", gradient), ("C", curl), ("D", divergence)
        )},
        "unique_key_coverage": unique,
        "local_incidence_coverage": local_coverage,
        "incidence_products": {"CG": cg, "DC": dc},
        "numeric_ranks": ranks,
        "rank_tolerances": rank_tolerances,
        "checks": checks,
        "pass": bool(all(checks.values())),
        "external_runtime": "numpy_scipy_only",
    }
    return FixedP6LORReferenceComplex(
        vertex_keys, edge_keys, face_keys, cell_keys, gradient, curl, divergence, audit
    )
