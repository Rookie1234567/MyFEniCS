"""Task040 L0b: local p6-to-LOR reference transfer.

This module is deliberately research/local-only.  It constructs fixed p6
reference arrays with Basix and NumPy, and calls the L0a incidence builder.  It
does not create a mesh, a global object, a PETSc object, an MPI communicator,
an operator, or a preconditioner.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import basix
import basix.ufl
import numpy as np

from src.solvers.hcurl_fixed_lor import (
    FixedP6LORReferenceComplex,
    build_fixed_p6_lor_reference_complex,
)

__all__ = (
    "FixedP6LORReferenceTransfer",
    "build_fixed_p6_lor_reference_transfer",
)

_N = 6
_N1 = _N + 1
_TINY = np.finfo(np.float64).tiny
_EDGE_BLOCK = _N * _N1 * _N1
_QUADRATURE_PRIMARY = 8
_QUADRATURE_CROSS_CHECK = 10


@dataclass(frozen=True)
class FixedP6LORReferenceTransfer:
    """Fixed local maps from p6 coefficients to LOR nodal/edge data."""

    reference: FixedP6LORReferenceComplex
    R0: np.ndarray
    R1: np.ndarray
    p6_discrete_gradient: np.ndarray
    audit: dict[str, Any]


def _reference_vertex_points() -> np.ndarray:
    return np.asarray(
        [
            (i / _N, j / _N, k / _N)
            for k in range(_N1)
            for j in range(_N1)
            for i in range(_N1)
        ],
        dtype=np.float64,
    )


def _build_R0(scalar_element, vertex_points: np.ndarray) -> np.ndarray:
    table = np.asarray(scalar_element.tabulate(0, vertex_points), dtype=np.float64)
    if table.shape != (1, len(vertex_points), int(scalar_element.dim), 1):
        raise RuntimeError(f"unexpected Q6 value tabulation shape: {table.shape}")
    result = np.ascontiguousarray(table[0, :, :, 0])
    if result.shape != (_N1**3, _N1**3):
        raise RuntimeError(f"unexpected R0 shape: {result.shape}")
    return result


def _edge_points(
    edge_key: tuple[str, int, int, int], quadrature_points: np.ndarray
) -> np.ndarray:
    axis, i, j, k = edge_key
    start = np.asarray((i, j, k), dtype=np.float64) / _N
    points = np.repeat(start[None, :], len(quadrature_points), axis=0)
    points[:, "xyz".index(axis)] += quadrature_points / _N
    return points


def _build_R1(hcurl_element, edge_keys, quadrature_degree: int) -> np.ndarray:
    points, weights = basix.make_quadrature(
        basix.CellType.interval,
        int(quadrature_degree),
    )
    quadrature_points = np.asarray(points, dtype=np.float64).reshape(-1)
    quadrature_weights = np.asarray(weights, dtype=np.float64).reshape(-1)
    if len(quadrature_points) != len(quadrature_weights):
        raise RuntimeError(
            "interval quadrature points and weights have different sizes"
        )
    result = np.empty((len(edge_keys), int(hcurl_element.dim)), dtype=np.float64)
    for axis in ("x", "y", "z"):
        rows = [index for index, key in enumerate(edge_keys) if key[0] == axis]
        samples = np.concatenate(
            [_edge_points(edge_keys[row], quadrature_points) for row in rows],
            axis=0,
        )
        values = np.asarray(hcurl_element.tabulate(0, samples), dtype=np.float64)
        if values.shape != (1, len(samples), int(hcurl_element.dim), 3):
            raise RuntimeError(
                f"unexpected N1curl value tabulation shape: {values.shape}"
            )
        values = values[0].reshape(
            len(rows), len(quadrature_points), int(hcurl_element.dim), 3
        )
        result[rows, :] = np.einsum(
            "q,eqd->ed",
            quadrature_weights,
            values[:, :, :, "xyz".index(axis)],
            optimize=True,
        ) / _N
    return np.ascontiguousarray(result)


def _build_p6_discrete_gradient(scalar_element, hcurl_element) -> np.ndarray:
    points = np.asarray(hcurl_element.points, dtype=np.float64)
    table = np.asarray(scalar_element.tabulate(1, points), dtype=np.float64)
    if table.shape[0] != 4 or table.shape[1] != len(points):
        raise RuntimeError(f"unexpected Q6 derivative tabulation shape: {table.shape}")
    values = np.stack(
        (table[1, :, :, 0], table[2, :, :, 0], table[3, :, :, 0]),
        axis=2,
    )
    flattened = np.ascontiguousarray(values.transpose(2, 0, 1)).reshape(
        3 * len(points), int(scalar_element.dim)
    )
    interpolation = np.asarray(hcurl_element.interpolation_matrix, dtype=np.float64)
    if interpolation.shape != (int(hcurl_element.dim), 3 * len(points)):
        raise RuntimeError(
            "unexpected N1curl interpolation matrix shape: "
            f"{interpolation.shape}"
        )
    result = np.ascontiguousarray(interpolation @ flattened)
    if result.shape != (int(hcurl_element.dim), int(scalar_element.dim)):
        raise RuntimeError(f"unexpected p6 gradient shape: {result.shape}")
    return result


def _rank_and_condition(matrix: np.ndarray) -> tuple[int, float, float]:
    singular_values = np.linalg.svd(matrix, compute_uv=False)
    tolerance = 0.0 if not singular_values.size else float(
        singular_values[0] * max(matrix.shape) * np.finfo(np.float64).eps
    )
    rank = int(np.count_nonzero(singular_values > tolerance))
    condition = (
        float(singular_values[0] / singular_values[-1])
        if singular_values.size and singular_values[-1] > 0.0
        else float("inf")
    )
    return rank, tolerance, condition


def _finite(*arrays: np.ndarray) -> bool:
    return all(bool(np.all(np.isfinite(array))) for array in arrays)


def _relative_difference(
    actual: np.ndarray, expected: np.ndarray
) -> tuple[float, float]:
    difference = np.asarray(actual) - np.asarray(expected)
    absolute = float(np.linalg.norm(difference))
    relative = absolute / max(float(np.linalg.norm(expected)), _TINY)
    return absolute, relative


def _solve_roundtrip(matrix: np.ndarray, offset: float) -> float:
    size = int(matrix.shape[1])
    indices = np.arange(size, dtype=np.float64)
    probe = np.sin(0.013 * (indices + 1.0) + offset) + 1j * np.cos(
        0.017 * (indices + 2.0) - offset
    )
    image = matrix @ probe
    recovered = np.linalg.solve(matrix, image)
    return float(np.linalg.norm(recovered - probe) / max(np.linalg.norm(probe), _TINY))


def build_fixed_p6_lor_reference_transfer() -> FixedP6LORReferenceTransfer:
    """Build fixed p6 R0/R1 maps and independently construct the p6 gradient."""

    reference = build_fixed_p6_lor_reference_complex()
    hcurl = basix.ufl.element("N1curl", "hexahedron", _N).basix_element
    scalar = basix.ufl.element(
        "Lagrange",
        "hexahedron",
        _N,
        lagrange_variant=basix.LagrangeVariant.gll_warped,
    ).basix_element
    vertex_points = _reference_vertex_points()
    R0 = _build_R0(scalar, vertex_points)
    R1_primary = _build_R1(hcurl, reference.edge_keys, _QUADRATURE_PRIMARY)
    R1_cross = _build_R1(hcurl, reference.edge_keys, _QUADRATURE_CROSS_CHECK)
    p6_gradient = _build_p6_discrete_gradient(scalar, hcurl)

    r0_rank, r0_tolerance, r0_condition = _rank_and_condition(R0)
    r1_rank, r1_tolerance, r1_condition = _rank_and_condition(R1_primary)
    gp_rank, gp_tolerance, _ = _rank_and_condition(p6_gradient)
    q_absolute, q_relative = _relative_difference(R1_primary, R1_cross)
    lor_gradient = reference.gradient_incidence @ R0
    p6_image = R1_primary @ p6_gradient
    commuting_absolute = float(np.linalg.norm(p6_image - lor_gradient))
    commuting_source = float(np.linalg.norm(p6_image))
    commuting_output = float(np.linalg.norm(lor_gradient))
    commuting_relative = commuting_absolute / max(
        commuting_source, commuting_output, _TINY
    )
    roundtrip = {
        "R0": _solve_roundtrip(R0, 0.11),
        "R1": _solve_roundtrip(R1_primary, 0.23),
    }
    finite = _finite(R0, R1_primary, R1_cross, p6_gradient)
    checks = {
        "shapes": (
            R0.shape == (343, 343)
            and R1_primary.shape == (882, 882)
            and p6_gradient.shape == (882, 343)
        ),
        "finite": finite,
        "reference_complex_pass": bool(reference.audit["pass"]),
        "condition_R0_finite": bool(np.isfinite(r0_condition)),
        "condition_R1_finite": bool(np.isfinite(r1_condition)),
        "rank_R0": r0_rank == 343,
        "rank_R1": r1_rank == 882,
        "rank_p6_gradient": gp_rank == 342,
        "quadrature_relative_defect": q_relative <= 1.0e-12,
        "commuting_relative_defect": commuting_relative <= 2.0e-10,
        "solve_roundtrip": max(roundtrip.values()) <= 2.0e-10,
    }
    audit = {
        "schema_version": "task040.fixed-lor.l0b.v1",
        "scope": "research_local_only_reference_transfer",
        "degree": _N,
        "subdivision": (_N, _N, _N),
        "element_family": {"hcurl": "N1curl", "scalar": "Lagrange"},
        "scalar_variant": "gll_warped",
        "shapes": {
            "R0": tuple(map(int, R0.shape)),
            "R1": tuple(map(int, R1_primary.shape)),
            "p6_discrete_gradient": tuple(map(int, p6_gradient.shape)),
        },
        "ordering": {
            "R0_rows": "L0a vertex_keys, x-fastest",
            "R0_columns": "Basix Q6 gll_warped coefficients",
            "R1_rows": "L0a edge_keys, positive x/y/z blocks",
            "R1_columns": "Basix N1curl p6 coefficients",
            "p6_gradient": "Basix N1curl interpolation rows by Q6 columns",
        },
        "quadrature": {
            "primary_degree": _QUADRATURE_PRIMARY,
            "cross_check_degree": _QUADRATURE_CROSS_CHECK,
            "edge_length_factor": 1.0 / _N,
            "axis_blocks_tabulated_separately": True,
        },
        "finite": finite,
        "numeric_rank": {"R0": r0_rank, "R1": r1_rank, "p6_gradient": gp_rank},
        "svd_tolerance": {
            "R0": r0_tolerance,
            "R1": r1_tolerance,
            "p6_gradient": gp_tolerance,
        },
        "full_rank_condition_estimate": {
            "R0": r0_condition,
            "R1": r1_condition,
        },
        "p6_gradient_nullity": int(343 - gp_rank),
        "p6_gradient_condition_status": (
            "rank_deficient_by_design_constant_kernel"
        ),
        "quadrature_defect": {
            "absolute": q_absolute,
            "relative": q_relative,
        },
        "commuting_defect": {
            "absolute": commuting_absolute,
            "source_norm": commuting_source,
            "output_norm": commuting_output,
            "relative": commuting_relative,
        },
        "solve_roundtrip_relative": roundtrip,
        "checks": checks,
        "pass": bool(all(checks.values())),
        "global_objects": False,
        "petsc": False,
        "dolfinx": False,
        "mpi": False,
        "phase_constraints": False,
        "adjoint_test": "deferred_to_focused_test",
    }
    for array in (R0, R1_primary, p6_gradient):
        array.setflags(write=False)
    return FixedP6LORReferenceTransfer(
        reference=reference,
        R0=R0,
        R1=R1_primary,
        p6_discrete_gradient=p6_gradient,
        audit=audit,
    )
