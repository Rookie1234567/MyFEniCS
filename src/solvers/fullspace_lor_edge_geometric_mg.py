"""Single-cell LOR edge-geometric transfer and fixed smoother primitives.

This module is deliberately local and audit-only.  It contains no PETSc,
MPI, global matrix, hierarchy, or solver-selection code.  The transfer is
the line-integral map from the coarse p=1 Nedelec edge space through a
degree-p high space to the GLL-refined LOR edge space.
"""

from __future__ import annotations

from dataclasses import dataclass

import basix
import numpy as np

from .fullspace_lor_transfer import (
    _build_incidence,
    _edge_endpoints,
    _face_descriptors,
    build_local_lor_transfer,
)


METHOD = "lor_edge_geometric_mg_v1"
CHEBYSHEV_DEGREE = 3
POWER_STEPS = 10
LAMBDA_HI_FACTOR = 1.10
LAMBDA_LO_FACTOR = 0.10
PRE_POLYNOMIAL_COUNT = 1
POST_POLYNOMIAL_COUNT = 1
VCYCLE_COUNT = 1

ADJOINT_LIMIT = 1.0e-12
LINEARITY_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-13
DE_RHAM_LIMIT = 1.0e-11


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left)
    right = np.asarray(right)
    return float(
        np.linalg.norm(left - right)
        / max(np.linalg.norm(right), np.finfo(float).tiny)
    )


def _transfer_probe_facts(matrix: np.ndarray) -> dict[str, object]:
    columns = matrix.shape[1]
    rows = matrix.shape[0]
    coarse = np.arange(1, columns + 1, dtype=np.float64).astype(np.complex128)
    coarse += 1j * np.arange(columns, 0, -1, dtype=np.float64)
    coarse_before = coarse.copy()
    second = np.arange(columns, 2 * columns, dtype=np.float64).astype(
        np.complex128
    )
    second -= 0.5j * np.arange(1, columns + 1, dtype=np.float64)
    fine = np.arange(1, rows + 1, dtype=np.float64).astype(np.complex128)
    fine += 0.25j * np.arange(rows, 0, -1, dtype=np.float64)
    alpha = 0.37 + 0.19j
    beta = -0.23 + 0.41j
    first = matrix @ coarse
    repeated = matrix @ coarse
    combined = matrix @ (alpha * coarse + beta * second)
    expected = alpha * first + beta * (matrix @ second)
    adjoint_left = np.vdot(first, fine)
    adjoint_right = np.vdot(coarse, matrix.conj().T @ fine)
    return {
        "adjoint_work_relative": float(
            abs(adjoint_left - adjoint_right)
            / max(abs(adjoint_right), np.finfo(float).tiny)
        ),
        "linearity_relative": _relative(combined, expected),
        "repeat_relative": _relative(repeated, first),
        "input_unchanged": bool(np.array_equal(coarse, coarse_before)),
        "finite": bool(
            np.all(np.isfinite(first))
            and np.all(np.isfinite(repeated))
            and np.all(np.isfinite(combined))
        ),
    }


def _edge_axes(starts: np.ndarray, ends: np.ndarray) -> np.ndarray:
    directions = np.asarray(ends, dtype=np.int32) - np.asarray(
        starts, dtype=np.int32
    )
    if not np.all(np.sum(np.abs(directions), axis=1) == 1):
        raise ValueError("edge endpoint inventory is not axis-aligned")
    return np.argmax(np.abs(directions), axis=1).astype(np.int32)


def _coarse_edge_mask(degree: int) -> np.ndarray:
    fine_starts, fine_ends = _edge_endpoints(degree)
    geometry = np.asarray(basix.geometry(basix.CellType.hexahedron))
    topology = basix.topology(basix.CellType.hexahedron)[1]
    coarse_axes = np.asarray(
        [
            np.argmax(np.abs(geometry[int(end)] - geometry[int(start)]))
            for start, end in topology
        ],
        dtype=np.int32,
    )
    fine_axes = _edge_axes(fine_starts, fine_ends)
    # For an edge basis, the four coarse edges with the same tangent axis
    # are the complete tensor-product transverse stencil.  This is a
    # geometric mask, not a magnitude-based sparsification decision.
    return fine_axes[:, None] == coarse_axes[None, :]


def _basix_to_lor_edge_order() -> np.ndarray:
    custom_starts, custom_ends = _edge_endpoints(1)
    custom_lookup = {
        (tuple(start), tuple(end)): index
        for index, (start, end) in enumerate(
            zip(custom_starts, custom_ends, strict=True)
        )
    }
    geometry = np.asarray(basix.geometry(basix.CellType.hexahedron))
    order: list[int] = []
    for start, end in basix.topology(basix.CellType.hexahedron)[1]:
        start_point = tuple(np.rint(geometry[int(start)]).astype(np.int32))
        end_point = tuple(np.rint(geometry[int(end)]).astype(np.int32))
        try:
            order.append(custom_lookup[(start_point, end_point)])
        except KeyError as exc:
            raise RuntimeError("Basix/LOR coarse edge order is not closed") from exc
    if len(set(order)) != 12:
        raise RuntimeError("Basix/LOR coarse edge order is not bijective")
    return np.asarray(order, dtype=np.int32)


def _edge_line_integral_oracle(
    degree: int,
    coarse_element,
    nodes: np.ndarray,
) -> np.ndarray:
    starts, ends = _edge_endpoints(degree)
    quadrature, weights = np.polynomial.legendre.leggauss(degree + 4)
    result = np.zeros((starts.shape[0], int(coarse_element.dim)), dtype=np.float64)
    for row, (start, end) in enumerate(zip(starts, ends, strict=True)):
        axis = int(np.argmax(np.abs(end - start)))
        a = float(nodes[start[axis]])
        b = float(nodes[end[axis]])
        points = (quadrature + 1.0) * (b - a) / 2.0 + a
        samples = np.repeat(
            nodes[start][None, :].astype(np.float64), points.size, axis=0
        )
        samples[:, axis] = points
        values = coarse_element.tabulate(0, samples)[0, :, :, axis]
        result[row] = weights * ((b - a) / 2.0) @ values
    return result


def _curl_face_oracle(
    degree: int,
    coarse_element,
    nodes: np.ndarray,
) -> np.ndarray:
    descriptors = _face_descriptors(degree)
    quadrature, weights = np.polynomial.legendre.leggauss(degree + 4)
    result = np.zeros((len(descriptors), int(coarse_element.dim)), dtype=np.float64)
    for row, (axis, normal_sign, i, j, k) in enumerate(descriptors):
        if axis == 2:
            a, b = nodes[i], nodes[i + 1]
            c, d = nodes[j], nodes[j + 1]
            u = (quadrature + 1.0) * (b - a) / 2.0 + a
            v = (quadrature + 1.0) * (d - c) / 2.0 + c
            samples = np.asarray(
                [(x, y, nodes[k]) for y in v for x in u], dtype=np.float64
            )
            face_weight = np.outer(weights, weights) * (b - a) * (d - c) / 4.0
            component = 2
        elif axis == 0:
            a, b = nodes[j], nodes[j + 1]
            c, d = nodes[k], nodes[k + 1]
            u = (quadrature + 1.0) * (b - a) / 2.0 + a
            v = (quadrature + 1.0) * (d - c) / 2.0 + c
            samples = np.asarray(
                [(nodes[i], x, y) for y in v for x in u], dtype=np.float64
            )
            face_weight = np.outer(weights, weights) * (b - a) * (d - c) / 4.0
            component = 0
        else:
            a, b = nodes[i], nodes[i + 1]
            c, d = nodes[k], nodes[k + 1]
            u = (quadrature + 1.0) * (b - a) / 2.0 + a
            v = (quadrature + 1.0) * (d - c) / 2.0 + c
            samples = np.asarray(
                [(x, nodes[j], y) for y in v for x in u], dtype=np.float64
            )
            face_weight = np.outer(weights, weights) * (b - a) * (d - c) / 4.0
            component = 1
        derivatives = coarse_element.tabulate(1, samples)
        curls = np.stack(
            (
                derivatives[2, :, :, 2] - derivatives[3, :, :, 1],
                derivatives[3, :, :, 0] - derivatives[1, :, :, 2],
                derivatives[1, :, :, 1] - derivatives[2, :, :, 0],
            ),
            axis=2,
        )
        result[row] = float(normal_sign) * (
            face_weight.reshape(-1) @ curls[:, :, component]
        )
    return result


@dataclass(frozen=True)
class LocalLorEdgeGeometricTransfer:
    degree: int
    high_edge_interpolation: np.ndarray
    coarse_basix_to_lor_order: np.ndarray
    edge_transfer_unmasked: np.ndarray
    edge_transfer: np.ndarray
    node_transfer: np.ndarray
    coarse_gradient: np.ndarray
    fine_gradient: np.ndarray
    fine_curl_incidence: np.ndarray
    direct_edge_integral: np.ndarray
    direct_curl_flux: np.ndarray
    off_stencil_defect: float
    audit: dict[str, object]


def build_local_lor_edge_geometric_transfer(
    degree: int,
) -> LocalLorEdgeGeometricTransfer:
    """Build the fixed p=1 to p to LOR line-integral transfer."""

    degree = int(degree)
    if degree not in (2, 3, 6):
        raise ValueError("S4-A1 degree must be one of (2, 3, 6)")
    local = build_local_lor_transfer(degree)
    coarse_edge = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        1,
        basix.LagrangeVariant.equispaced,
    )
    high_edge = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        degree,
        basix.LagrangeVariant.equispaced,
    )
    high_edge_interpolation = np.asarray(
        basix.compute_interpolation_operator(coarse_edge, high_edge),
        dtype=np.float64,
    )
    expected_high_shape = (int(high_edge.dim), int(coarse_edge.dim))
    if high_edge_interpolation.shape != expected_high_shape:
        raise RuntimeError("Basix N1E interpolation shape is not closed")
    edge_transfer_unmasked = np.asarray(
        local.high_to_lor_matrix @ high_edge_interpolation,
        dtype=np.complex128,
    )
    mask = _coarse_edge_mask(degree)
    off_stencil_defect = float(
        np.linalg.norm(edge_transfer_unmasked[~mask])
        / max(np.linalg.norm(edge_transfer_unmasked), np.finfo(float).tiny)
    )
    if off_stencil_defect > DE_RHAM_LIMIT:
        raise RuntimeError(
            "same-axis edge stencil is not closed: "
            f"defect={off_stencil_defect:.17g}"
        )
    edge_transfer = np.where(mask, edge_transfer_unmasked, 0.0)

    coarse_node = basix.create_element(
        basix.ElementFamily.P,
        basix.CellType.hexahedron,
        1,
        basix.LagrangeVariant.equispaced,
    )
    high_node = basix.create_element(
        basix.ElementFamily.P,
        basix.CellType.hexahedron,
        degree,
        basix.LagrangeVariant.equispaced,
    )
    node_interpolation = np.asarray(
        basix.compute_interpolation_operator(coarse_node, high_node),
        dtype=np.float64,
    )
    node_transfer = np.asarray(local.h1_transfer @ node_interpolation)
    coarse_basix_to_lor_order = _basix_to_lor_edge_order()
    coarse_gradient, _coarse_curl, _coarse_faces = _build_incidence(1)
    coarse_gradient = coarse_gradient[coarse_basix_to_lor_order]
    fine_gradient = np.asarray(local.lor_gradient)
    fine_curl = np.asarray(local.lor_curl_incidence)
    direct_edge_integral = _edge_line_integral_oracle(
        degree, coarse_edge, local.nodes
    )
    direct_curl_flux = _curl_face_oracle(degree, coarse_edge, local.nodes)
    probe_facts = _transfer_probe_facts(edge_transfer)
    gradient_relative = _relative(
        fine_gradient @ node_transfer, edge_transfer @ coarse_gradient
    )
    curl_relative = _relative(
        fine_curl @ edge_transfer, direct_curl_flux
    )
    edge_quadrature_relative = _relative(edge_transfer, direct_edge_integral)
    if gradient_relative > DE_RHAM_LIMIT or curl_relative > DE_RHAM_LIMIT:
        raise RuntimeError(
            "local de Rham transfer does not commute: "
            f"gradient={gradient_relative:.17g}, curl={curl_relative:.17g}"
        )
    if edge_quadrature_relative > DE_RHAM_LIMIT:
        raise RuntimeError(
            "independent edge line-integral oracle mismatch: "
            f"relative={edge_quadrature_relative:.17g}"
        )
    if (
        probe_facts["adjoint_work_relative"] > ADJOINT_LIMIT
        or probe_facts["linearity_relative"] > LINEARITY_LIMIT
        or probe_facts["repeat_relative"] > REPEAT_LIMIT
        or not probe_facts["input_unchanged"]
        or not probe_facts["finite"]
    ):
        raise RuntimeError("local edge transfer legality probe failed")
    audit = {
        "method": METHOD,
        "degree": degree,
        "line_integral_histopolation": True,
        "simple_injection": False,
        "same_axis_transverse_stencil_size": 4,
        "off_stencil_defect": off_stencil_defect,
        "gradient_commuting_relative": gradient_relative,
        "curl_commuting_relative": curl_relative,
        "edge_line_integral_oracle_relative": edge_quadrature_relative,
        "adjoint_work_relative": probe_facts["adjoint_work_relative"],
        "linearity_relative": probe_facts["linearity_relative"],
        "repeat_relative": probe_facts["repeat_relative"],
        "input_unchanged": probe_facts["input_unchanged"],
        "finite": bool(
            probe_facts["finite"]
            and np.all(np.isfinite(edge_transfer))
            and np.all(np.isfinite(node_transfer))
            and np.all(np.isfinite(direct_curl_flux))
        ),
        "high_edge_dofs": int(high_edge.dim),
        "coarse_edge_dofs": int(coarse_edge.dim),
        "fine_lor_edge_dofs": int(edge_transfer.shape[0]),
        "coarse_node_dofs": int(coarse_node.dim),
        "fine_lor_node_dofs": int(node_transfer.shape[0]),
        "orientation_phase_scope": "not_exercised_by_local_A1",
        "global_orientation_phase_once": None,
        "global_transfer_matrix": False,
        "global_high_order_aij": False,
        "numeric_allgather": False,
    }
    for array in (
        high_edge_interpolation,
        edge_transfer_unmasked,
        edge_transfer,
        node_transfer,
        coarse_gradient,
        fine_gradient,
        fine_curl,
        direct_edge_integral,
        direct_curl_flux,
        coarse_basix_to_lor_order,
    ):
        array.setflags(write=False)
    return LocalLorEdgeGeometricTransfer(
        degree=degree,
        high_edge_interpolation=high_edge_interpolation,
        coarse_basix_to_lor_order=coarse_basix_to_lor_order,
        edge_transfer_unmasked=edge_transfer_unmasked,
        edge_transfer=edge_transfer,
        node_transfer=node_transfer,
        coarse_gradient=coarse_gradient,
        fine_gradient=fine_gradient,
        fine_curl_incidence=fine_curl,
        direct_edge_integral=direct_edge_integral,
        direct_curl_flux=direct_curl_flux,
        off_stencil_defect=off_stencil_defect,
        audit=audit,
    )


def power_estimate(matrix: np.ndarray) -> tuple[float, tuple[float, ...]]:
    """Perform the deterministic, fixed ten-step power estimate."""

    matrix = np.asarray(matrix, dtype=np.complex128)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("power estimate requires a square matrix")
    n = matrix.shape[0]
    vector = np.arange(1, n + 1, dtype=np.float64).astype(np.complex128)
    vector += 1j * np.arange(n, 0, -1, dtype=np.float64)
    vector /= np.linalg.norm(vector)
    history: list[float] = []
    for _ in range(POWER_STEPS):
        vector = matrix @ vector
        norm = float(np.linalg.norm(vector))
        if not np.isfinite(norm) or norm == 0.0:
            raise FloatingPointError("power estimate became non-finite")
        vector /= norm
        history.append(float(np.real(np.vdot(vector, matrix @ vector))))
    estimate = float(history[-1])
    if not np.isfinite(estimate) or estimate <= 0.0:
        raise FloatingPointError("power estimate is not positive and finite")
    return estimate, tuple(history)


class FixedChebyshevJacobi:
    """One frozen degree-three Jacobi-scaled Chebyshev polynomial."""

    def __init__(self, matrix: np.ndarray):
        matrix = np.asarray(matrix, dtype=np.complex128)
        if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
            raise ValueError("Chebyshev matrix must be square")
        diagonal = np.real(np.diag(matrix))
        if not np.all(np.isfinite(diagonal)) or np.any(diagonal <= 0.0):
            raise ValueError("Chebyshev Jacobi diagonal must be positive")
        scale = 1.0 / np.sqrt(diagonal)
        scaled = scale[:, None] * matrix * scale[None, :]
        lambda_power, history = power_estimate(scaled)
        lambda_hi = LAMBDA_HI_FACTOR * lambda_power
        lambda_lo = LAMBDA_LO_FACTOR * lambda_hi
        if not np.isfinite(lambda_hi) or not 0.0 < lambda_lo < lambda_hi:
            raise FloatingPointError("Chebyshev spectral window is invalid")
        self.matrix = matrix
        self.scaled_matrix = scaled
        self.scale = scale
        self.lambda_power10 = lambda_power
        self.lambda_hi = lambda_hi
        self.lambda_lo = lambda_lo
        self.power_history = history

    def apply(self, rhs: np.ndarray) -> np.ndarray:
        rhs = np.asarray(rhs, dtype=np.complex128)
        if rhs.shape != (self.matrix.shape[0],):
            raise ValueError("Chebyshev rhs shape does not match matrix")
        scaled_rhs = self.scale * rhs
        center = 0.5 * (self.lambda_hi + self.lambda_lo)
        half_width = 0.5 * (self.lambda_hi - self.lambda_lo)
        sigma = center / half_width
        rho = 1.0 / sigma
        residual = scaled_rhs
        direction = residual / center
        solution = direction.copy()
        for _step in range(1, CHEBYSHEV_DEGREE):
            residual = scaled_rhs - self.scaled_matrix @ solution
            rho_new = 1.0 / (2.0 * sigma - rho)
            direction = (
                rho_new * rho * direction
                + (2.0 * rho_new / half_width) * residual
            )
            solution = solution + direction
            rho = rho_new
        return self.scale * solution
