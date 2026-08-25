"""Pure single-cell interlevel LOR edge-transfer audit primitives.

The module keeps only bounded cell-local arrays.  It does not construct a
distributed object or a numerical hierarchy; those concerns belong to later
stages.  The supported maps are fixed at 6<-3, 3<-1, 6<-2, and 2<-1.
"""

from __future__ import annotations

from types import MappingProxyType

import basix
import numpy as np

from .fullspace_lor_edge_geometric_mg import (
    _basix_to_lor_edge_order,
    _curl_face_oracle,
    _edge_line_integral_oracle,
    build_local_lor_edge_geometric_transfer,
)
from .fullspace_lor_transfer import (
    LOR_BATCH_CELL_CAP,
    _build_incidence,
    _edge_id,
    _edge_endpoints,
    _face_descriptors,
    _gll_nodes,
    build_local_lor_transfer,
)


INTERLEVEL_PAIRS = ((6, 3), (3, 1), (6, 2), (2, 1))
INTERLEVEL_BATCH_CELL_CAP = LOR_BATCH_CELL_CAP
EDGE_QUADRATURE_LIMIT = 1.0e-11
GRADIENT_LIMIT = 1.0e-11
CURL_LIMIT = 1.0e-11
ADJOINT_LIMIT = 1.0e-12
LINEARITY_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-13
NESTED_SHARED_EDGE_LIMIT = 1.0e-12
NESTED_COMPOSITION_LIMIT = 1.0e-11


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left)
    right = np.asarray(right)
    return float(
        np.linalg.norm(left - right)
        / max(np.linalg.norm(right), np.finfo(float).tiny)
    )


def _n1e(degree: int):
    return basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        int(degree),
        basix.LagrangeVariant.equispaced,
    )


def _scalar(degree: int):
    return basix.create_element(
        basix.ElementFamily.P,
        basix.CellType.hexahedron,
        int(degree),
        basix.LagrangeVariant.equispaced,
    )


def _node_transfer(
    fine_local: object,
    coarse_local: object,
    fine_degree: int,
    coarse_degree: int,
) -> np.ndarray:
    coarse_element = _scalar(coarse_degree)
    fine_element = _scalar(fine_degree)
    interpolation = np.asarray(
        basix.compute_interpolation_operator(coarse_element, fine_element),
        dtype=np.complex128,
    )
    fine_h1 = np.asarray(fine_local.h1_transfer, dtype=np.complex128)
    coarse_h1 = np.asarray(coarse_local.h1_transfer, dtype=np.complex128)
    if interpolation.shape != (int(fine_element.dim), int(coarse_element.dim)):
        raise RuntimeError("scalar interpolation shape is not closed")
    return np.ascontiguousarray(
        fine_h1 @ interpolation @ np.linalg.solve(coarse_h1, np.eye(coarse_h1.shape[0]))
    )


def _nested_subset_facts() -> dict[str, object]:
    fine_nodes = np.asarray(_gll_nodes(6), dtype=np.float64)
    coarse_nodes = np.asarray(_gll_nodes(2), dtype=np.float64)
    subset_indices: list[int] = []
    for value in coarse_nodes:
        matches = np.flatnonzero(fine_nodes == value)
        if matches.size != 1:
            raise ValueError("p2 GLL nodes are not an exact p6 subset")
        subset_indices.append(int(matches[0]))
    if not np.array_equal(fine_nodes[subset_indices], coarse_nodes):
        raise ValueError("p2 GLL subset coordinate identity is not exact")
    return {
        "gll_subset_exact": True,
        "coarse_gll_subset_indices": subset_indices,
        "coarse_gll_subset_coordinate_identity": [
            float(value).hex() for value in coarse_nodes
        ],
        "fine_gll_subset_coordinate_identity": [
            float(value).hex() for value in fine_nodes[subset_indices]
        ],
    }


def _nested_parent_cell(
    start: np.ndarray, end: np.ndarray
) -> tuple[int, tuple[int, int, int]]:
    axis = int(np.argmax(np.asarray(end, dtype=np.int32) - start))
    parent = [0 if int(value) <= 3 else 1 for value in start]
    parent[axis] = int(start[axis]) // 3
    return axis, tuple(parent)


def _nested_p62_geometry_maps() -> tuple[np.ndarray, np.ndarray]:
    """Build the unique-owner p2-to-p6 nested geometric maps.

    Each p6 edge is assigned once by the fixed half-open parent-cell rule.
    The four same-axis p2 edge columns receive the tangent-length ratio times
    Q1 barycentric weights in the two transverse coordinates.
    """

    fine_nodes = np.asarray(_gll_nodes(6), dtype=np.float64)
    coarse_nodes = np.asarray(_gll_nodes(2), dtype=np.float64)
    starts, ends = _edge_endpoints(6)
    edge_transfer = np.zeros((882, 54), dtype=np.complex128)
    for row, (start, end) in enumerate(zip(starts, ends, strict=True)):
        axis, parent = _nested_parent_cell(start, end)
        tangent_start = int(start[axis])
        coarse_length = coarse_nodes[parent[axis] + 1] - coarse_nodes[parent[axis]]
        fine_length = fine_nodes[tangent_start + 1] - fine_nodes[tangent_start]
        tangent_ratio = float(fine_length / coarse_length)
        transverse_axes = tuple(value for value in range(3) if value != axis)
        for first_bit in (0, 1):
            for second_bit in (0, 1):
                bits = {transverse_axes[0]: first_bit, transverse_axes[1]: second_bit}
                coarse_start = list(parent)
                weight = tangent_ratio
                for transverse_axis in transverse_axes:
                    local_coordinate = float(
                        (fine_nodes[int(start[transverse_axis])]
                         - coarse_nodes[parent[transverse_axis]])
                        / (coarse_nodes[parent[transverse_axis] + 1]
                           - coarse_nodes[parent[transverse_axis]])
                    )
                    bit = bits[transverse_axis]
                    coarse_start[transverse_axis] = parent[transverse_axis] + bit
                    weight *= local_coordinate if bit else 1.0 - local_coordinate
                column = _edge_id(axis, *coarse_start, 2)
                edge_transfer[row, column] = weight

    node_transfer = np.zeros((343, 27), dtype=np.complex128)
    for k in range(7):
        for j in range(7):
            for i in range(7):
                indices = (i, j, k)
                parent = tuple(0 if value <= 3 else 1 for value in indices)
                local = tuple(
                    float(
                        (fine_nodes[index] - coarse_nodes[parent[axis]])
                        / (coarse_nodes[parent[axis] + 1]
                           - coarse_nodes[parent[axis]])
                    )
                    for axis, index in enumerate(indices)
                )
                row = i + 7 * (j + 7 * k)
                for dk in (0, 1):
                    for dj in (0, 1):
                        for di in (0, 1):
                            column = parent[0] + di + 3 * (
                                parent[1] + dj + 3 * (parent[2] + dk)
                            )
                            node_transfer[row, column] = np.prod(
                                [
                                    coordinate if bit else 1.0 - coordinate
                                    for coordinate, bit in zip(
                                        local, (di, dj, dk), strict=True
                                    )
                                ]
                            )
    return (
        np.ascontiguousarray(edge_transfer),
        np.ascontiguousarray(node_transfer),
    )


def _nested_quadrature_maps() -> tuple[
    np.ndarray, np.ndarray, np.ndarray, dict[str, float | int | bool]
]:
    """Independently integrate p1 N1E edge and face-curl basis functions."""

    element = _n1e(1)
    node_element = _scalar(1)
    columns = np.argsort(_basix_to_lor_edge_order())
    quadrature, weights = np.polynomial.legendre.leggauss(7)
    fine_nodes = np.asarray(_gll_nodes(6), dtype=np.float64)
    coarse_nodes = np.asarray(_gll_nodes(2), dtype=np.float64)
    local_edges = _edge_endpoints(3)
    local_edge_axes = np.argmax(local_edges[1] - local_edges[0], axis=1)
    local_faces = _face_descriptors(3)
    fine_faces = _face_descriptors(6)
    fine_face_lookup = {tuple(value): index for index, value in enumerate(fine_faces)}
    coarse_edges = _edge_endpoints(1)
    coarse_edge_axes = np.argmax(coarse_edges[1] - coarse_edges[0], axis=1)
    edge_oracle = np.zeros((882, 54), dtype=np.complex128)
    curl_oracle = np.zeros((len(fine_faces), 54), dtype=np.complex128)
    edge_seen = np.zeros(882, dtype=bool)
    face_seen = np.zeros(len(fine_faces), dtype=bool)
    shared_edge_checks = 0
    shared_face_checks = 0
    shared_edge_max_abs = 0.0
    shared_face_max_abs = 0.0

    def local_edge_map(local_nodes: tuple[np.ndarray, ...]) -> np.ndarray:
        result = np.zeros((144, 12), dtype=np.complex128)
        for row, (start, end) in enumerate(zip(*local_edges, strict=True)):
            axis = int(local_edge_axes[row])
            a = float(local_nodes[axis][start[axis]])
            b = float(local_nodes[axis][end[axis]])
            points = (quadrature + 1.0) * (b - a) / 2.0 + a
            base = np.asarray(
                [local_nodes[d][start[d]] for d in range(3)], dtype=np.float64
            )
            samples = np.repeat(base[None, :], points.size, axis=0)
            samples[:, axis] = points
            values = element.tabulate(0, samples)[0, :, :, axis]
            result[row] = (weights * (b - a) / 2.0) @ values
        return np.ascontiguousarray(result[:, columns])

    def local_curl_map(local_nodes: tuple[np.ndarray, ...]) -> np.ndarray:
        result = np.zeros((len(local_faces), 12), dtype=np.complex128)
        for row, (axis, normal_sign, i, j, k) in enumerate(local_faces):
            if axis == 2:
                a, b = local_nodes[0][i], local_nodes[0][i + 1]
                c, d = local_nodes[1][j], local_nodes[1][j + 1]
                u = (quadrature + 1.0) * (b - a) / 2.0 + a
                v = (quadrature + 1.0) * (d - c) / 2.0 + c
                samples = np.asarray(
                    [(x, y, local_nodes[2][k]) for y in v for x in u],
                    dtype=np.float64,
                )
                face_weight = np.outer(weights, weights) * (b - a) * (d - c) / 4.0
                component = 2
            elif axis == 0:
                a, b = local_nodes[1][j], local_nodes[1][j + 1]
                c, d = local_nodes[2][k], local_nodes[2][k + 1]
                u = (quadrature + 1.0) * (b - a) / 2.0 + a
                v = (quadrature + 1.0) * (d - c) / 2.0 + c
                samples = np.asarray(
                    [(local_nodes[0][i], x, y) for y in v for x in u],
                    dtype=np.float64,
                )
                face_weight = np.outer(weights, weights) * (b - a) * (d - c) / 4.0
                component = 0
            else:
                a, b = local_nodes[0][i], local_nodes[0][i + 1]
                c, d = local_nodes[2][k], local_nodes[2][k + 1]
                u = (quadrature + 1.0) * (b - a) / 2.0 + a
                v = (quadrature + 1.0) * (d - c) / 2.0 + c
                samples = np.asarray(
                    [(x, local_nodes[1][j], y) for y in v for x in u],
                    dtype=np.float64,
                )
                face_weight = np.outer(weights, weights) * (b - a) * (d - c) / 4.0
                component = 1
            derivatives = element.tabulate(1, samples)
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
        return np.ascontiguousarray(result[:, columns])

    for ck in range(2):
        for cj in range(2):
            for ci in range(2):
                local_nodes = tuple(
                    (fine_nodes[3 * parent : 3 * parent + 4] - coarse_nodes[parent])
                    / (coarse_nodes[parent + 1] - coarse_nodes[parent])
                    for parent in (ci, cj, ck)
                )
                local_edge = local_edge_map(local_nodes)
                local_curl = local_curl_map(local_nodes)
                for row, start in enumerate(local_edges[0]):
                    axis = int(local_edge_axes[row])
                    fine_id = _edge_id(
                        axis,
                        3 * ci + int(start[0]),
                        3 * cj + int(start[1]),
                        3 * ck + int(start[2]),
                        6,
                    )
                    value = np.zeros(54, dtype=np.complex128)
                    for column, coarse_start in enumerate(coarse_edges[0]):
                        coarse_axis = int(coarse_edge_axes[column])
                        coarse_id = _edge_id(
                            coarse_axis,
                            ci + int(coarse_start[0]),
                            cj + int(coarse_start[1]),
                            ck + int(coarse_start[2]),
                            2,
                        )
                        value[coarse_id] = local_edge[row, column]
                    if edge_seen[fine_id]:
                        shared_edge_checks += 1
                        shared_edge_max_abs = max(
                            shared_edge_max_abs,
                            float(np.max(np.abs(edge_oracle[fine_id] - value))),
                        )
                    else:
                        edge_oracle[fine_id] = value
                        edge_seen[fine_id] = True
                for row, (axis, normal_sign, i, j, k) in enumerate(local_faces):
                    fine_face_id = fine_face_lookup[
                        (
                            axis,
                            normal_sign,
                            3 * ci + i,
                            3 * cj + j,
                            3 * ck + k,
                        )
                    ]
                    value = np.zeros(54, dtype=np.complex128)
                    for column, coarse_start in enumerate(coarse_edges[0]):
                        coarse_axis = int(coarse_edge_axes[column])
                        coarse_id = _edge_id(
                            coarse_axis,
                            ci + int(coarse_start[0]),
                            cj + int(coarse_start[1]),
                            ck + int(coarse_start[2]),
                            2,
                        )
                        value[coarse_id] = local_curl[row, column]
                    if face_seen[fine_face_id]:
                        shared_face_checks += 1
                        shared_face_max_abs = max(
                            shared_face_max_abs,
                            float(np.max(np.abs(curl_oracle[fine_face_id] - value))),
                        )
                    else:
                        curl_oracle[fine_face_id] = value
                        face_seen[fine_face_id] = True

    node_oracle = np.zeros((343, 27), dtype=np.complex128)
    geometry = np.asarray(basix.geometry(basix.CellType.hexahedron))
    for k in range(7):
        for j in range(7):
            for i in range(7):
                indices = (i, j, k)
                parent = tuple(0 if value <= 3 else 1 for value in indices)
                local = np.asarray(
                    [
                        (fine_nodes[index] - coarse_nodes[parent[axis]])
                        / (coarse_nodes[parent[axis] + 1]
                           - coarse_nodes[parent[axis]])
                        for axis, index in enumerate(indices)
                    ],
                    dtype=np.float64,
                )
                values = node_element.tabulate(0, local[None, :])[0, 0, :, 0]
                row = i + 7 * (j + 7 * k)
                for column, vertex in enumerate(geometry):
                    bits = tuple(int(value) for value in vertex)
                    coarse_id = parent[0] + bits[0] + 3 * (
                        parent[1] + bits[1] + 3 * (parent[2] + bits[2])
                    )
                    node_oracle[row, coarse_id] = values[column]
    if not np.all(edge_seen) or not np.all(face_seen):
        raise RuntimeError("nested quadrature owner inventories are incomplete")
    return (
        edge_oracle,
        curl_oracle,
        node_oracle,
        {
            "shared_edge_checks": shared_edge_checks,
            "shared_face_checks": shared_face_checks,
            "shared_edge_max_abs": shared_edge_max_abs,
            "shared_face_max_abs": shared_face_max_abs,
            "shared_consistency": bool(
                shared_edge_max_abs <= NESTED_SHARED_EDGE_LIMIT
                and shared_face_max_abs <= NESTED_SHARED_EDGE_LIMIT
            ),
        },
    )


def _nested_p62_composition_relative(edge_transfer: np.ndarray) -> float:
    p21_authority = build_local_lor_edge_geometric_transfer(2)
    p61_authority = build_local_lor_edge_geometric_transfer(6)
    p21 = p21_authority.edge_transfer[
        :, np.argsort(p21_authority.coarse_basix_to_lor_order)
    ]
    p61 = p61_authority.edge_transfer[
        :, np.argsort(p61_authority.coarse_basix_to_lor_order)
    ]
    return _relative(edge_transfer @ p21, p61)


def _structural_trace_mask(
    fine_degree: int, coarse_degree: int
) -> np.ndarray:
    """Return the reference-cell boundary-plane support mask for an edge map."""

    fine_start, fine_end = _edge_endpoints(int(fine_degree))
    coarse_start, coarse_end = _edge_endpoints(int(coarse_degree))
    mask = np.ones(
        (fine_start.shape[0], coarse_start.shape[0]), dtype=bool
    )
    for row, (start, end) in enumerate(zip(fine_start, fine_end, strict=True)):
        boundary_planes = tuple(
            (axis, int(start[axis]))
            for axis in range(3)
            if int(start[axis]) == int(end[axis])
            and int(start[axis]) in (0, int(fine_degree))
        )
        if not boundary_planes:
            continue
        for column, (coarse_row, coarse_column) in enumerate(
            zip(coarse_start, coarse_end, strict=True)
        ):
            mask[row, column] = all(
                int(coarse_row[axis]) == int(coarse_column[axis])
                and int(coarse_row[axis])
                == (0 if position == 0 else int(coarse_degree))
                for axis, position in boundary_planes
            )
    return mask


def _probe_facts(edge_transfer: np.ndarray) -> dict[str, object]:
    columns = int(edge_transfer.shape[1])
    rows = int(edge_transfer.shape[0])
    first = (
        np.arange(1, columns + 1, dtype=np.float64)
        + 1j * np.arange(columns, 0, -1, dtype=np.float64)
    ).astype(np.complex128)
    second = (
        np.arange(columns + 3, 2 * columns + 3, dtype=np.float64)
        - 0.5j * np.arange(1, columns + 1, dtype=np.float64)
    ).astype(np.complex128)
    fine = (
        np.arange(2, rows + 2, dtype=np.float64)
        + 0.25j * np.arange(rows, 0, -1, dtype=np.float64)
    ).astype(np.complex128)
    before = first.copy()
    alpha = 0.37 + 0.19j
    beta = -0.23 + 0.41j
    observed = edge_transfer @ first
    repeated = edge_transfer @ first
    combined = edge_transfer @ (alpha * first + beta * second)
    expected = alpha * observed + beta * (edge_transfer @ second)
    lhs = np.vdot(observed, fine)
    rhs = np.vdot(first, edge_transfer.conj().T @ fine)
    return {
        "adjoint_work_relative": float(
            abs(lhs - rhs) / max(abs(rhs), np.finfo(float).tiny)
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


def _independent_facts(
    fine_degree: int,
    coarse_degree: int,
    edge_transfer: np.ndarray,
    node_transfer: np.ndarray,
) -> dict[str, object]:
    fine_degree = int(fine_degree)
    coarse_degree = int(coarse_degree)
    if (fine_degree, coarse_degree) not in INTERLEVEL_PAIRS:
        raise ValueError(
            "only (6, 3), (3, 1), (6, 2), and (2, 1) interlevel maps are supported"
        )
    edge_transfer = np.asarray(edge_transfer, dtype=np.complex128)
    node_transfer = np.asarray(node_transfer, dtype=np.complex128)
    if (fine_degree, coarse_degree) == (6, 2):
        if edge_transfer.shape != (882, 54) or node_transfer.shape != (343, 27):
            raise ValueError("nested (6,2) map shapes are not closed")
        early_mask = _structural_trace_mask(6, 2)
        if np.any(edge_transfer[~early_mask] != 0.0):
            raise ValueError("structural forbidden edge entries are not exact zero")
    node_reference = None
    subset_facts: dict[str, object] = {}
    nested_facts: dict[str, object] = {}
    if (fine_degree, coarse_degree) == (6, 2):
        expected_shape = (882, 54)
        expected_node_shape = (343, 27)
        (
            edge_oracle,
            curl_oracle,
            node_reference,
            shared_facts,
        ) = _nested_quadrature_maps()
        fine_gradient, fine_curl, _ = _build_incidence(6)
        coarse_gradient, _, _ = _build_incidence(2)
        cond = 1.0
        subset_facts = _nested_subset_facts()
        composition_relative = _nested_p62_composition_relative(edge_transfer)
        if shared_facts["shared_consistency"] is not True:
            raise ValueError("nested shared edge/face consistency failed")
        if float(composition_relative) > NESTED_COMPOSITION_LIMIT:
            raise ValueError(
                "nested P62*P21 composition exceeds the fixed limit: "
                f"{composition_relative:.17g} > {NESTED_COMPOSITION_LIMIT:.17g}"
            )
        nested_facts = {
            "nested_tiled_geometric": True,
            "generic_high_polynomial_reconstruction": False,
            "deterministic_owner_policy": "fine_edge_half_open_parent_cell",
            "edge_nnz": int(np.count_nonzero(edge_transfer)),
            "node_nnz": int(np.count_nonzero(node_transfer)),
            "shared_edge_checks": int(shared_facts["shared_edge_checks"]),
            "shared_face_checks": int(shared_facts["shared_face_checks"]),
            "shared_edge_max_abs": float(shared_facts["shared_edge_max_abs"]),
            "shared_face_max_abs": float(shared_facts["shared_face_max_abs"]),
            "shared_consistency": bool(shared_facts["shared_consistency"]),
            "p62_p21_composition_relative": float(composition_relative),
        }
    elif coarse_degree == 1:
        authority = build_local_lor_edge_geometric_transfer(fine_degree)
        basix_to_lor = np.asarray(
            authority.coarse_basix_to_lor_order, dtype=np.int32
        )
        custom_columns = np.argsort(basix_to_lor)
        expected_shape = tuple(int(value) for value in authority.edge_transfer.shape)
        expected_node_shape = tuple(int(value) for value in authority.node_transfer.shape)
        edge_oracle = np.asarray(
            authority.direct_edge_integral[:, custom_columns],
            dtype=np.complex128,
        )
        curl_oracle = np.asarray(
            authority.direct_curl_flux[:, custom_columns],
            dtype=np.complex128,
        )
        fine_curl = np.asarray(authority.fine_curl_incidence, dtype=np.complex128)
        coarse_gradient = np.asarray(
            authority.coarse_gradient[custom_columns], dtype=np.complex128
        )
        fine_gradient = np.asarray(authority.fine_gradient, dtype=np.complex128)
        node_reference = np.asarray(authority.node_transfer, dtype=np.complex128)
        cond = 1.0
    else:
        fine_local = build_local_lor_transfer(fine_degree)
        coarse_local = build_local_lor_transfer(coarse_degree)
        coarse_element = _n1e(coarse_degree)
        coarse_transform = np.asarray(
            coarse_local.high_to_lor_matrix, dtype=np.complex128
        )
        expected_shape = (
            int(fine_local.high_to_lor_matrix.shape[0]),
            int(coarse_transform.shape[0]),
        )
        expected_node_shape = (
            int(fine_local.h1_transfer.shape[0]),
            int(coarse_local.h1_transfer.shape[0]),
        )
        coarse_inverse = np.linalg.solve(
            coarse_transform,
            np.eye(coarse_transform.shape[0], dtype=np.complex128),
        )
        edge_oracle = _edge_line_integral_oracle(
            fine_degree, coarse_element, fine_local.nodes
        ) @ coarse_inverse
        curl_oracle = _curl_face_oracle(
            fine_degree, coarse_element, fine_local.nodes
        ) @ coarse_inverse
        fine_curl = np.asarray(fine_local.lor_curl_incidence, dtype=np.complex128)
        coarse_gradient = np.asarray(coarse_local.lor_gradient, dtype=np.complex128)
        fine_gradient = np.asarray(fine_local.lor_gradient, dtype=np.complex128)
        cond = float(np.linalg.cond(coarse_transform))

    if edge_transfer.shape != expected_shape:
        raise ValueError(
            f"edge map shape {edge_transfer.shape} != expected {expected_shape}"
        )
    if node_transfer.shape != expected_node_shape:
        raise ValueError(
            f"node map shape {node_transfer.shape} != expected {expected_node_shape}"
        )
    if not np.all(np.isfinite(edge_transfer)) or not np.all(
        np.isfinite(node_transfer)
    ):
        raise ValueError("interlevel map contains non-finite values")

    structural_mask = _structural_trace_mask(fine_degree, coarse_degree)
    forbidden = edge_transfer[~structural_mask]
    if np.any(forbidden != 0.0):
        raise ValueError("structural forbidden edge entries are not exact zero")

    curl_incidence = fine_curl @ edge_transfer
    gradient_left = fine_gradient @ node_transfer
    gradient_right = edge_transfer @ coarse_gradient
    probe = _probe_facts(edge_transfer)
    edge_relative = _relative(edge_transfer, edge_oracle)
    curl_relative = _relative(curl_incidence, curl_oracle)
    gradient_relative = _relative(gradient_left, gradient_right)
    node_relative = (
        0.0
        if node_reference is None
        else _relative(node_transfer, node_reference)
    )
    if not np.isfinite(cond):
        raise ValueError("coarse high-to-LOR transform condition is non-finite")
    audit = {
        "schema": "task038.local_interlevel_edge_transfer.v1",
        "fine_degree": fine_degree,
        "coarse_degree": coarse_degree,
        "batch_cell_cap": int(INTERLEVEL_BATCH_CELL_CAP),
        "edge_shape": tuple(int(value) for value in edge_transfer.shape),
        "node_shape": tuple(int(value) for value in node_transfer.shape),
        "edge_dtype": "complex128",
        "node_dtype": "complex128",
        "edge_numeric_bytes": int(edge_transfer.nbytes),
        "node_numeric_bytes": int(node_transfer.nbytes),
        "coarse_transform_condition": cond,
        "edge_line_integral_relative": edge_relative,
        "curl_flux_relative": curl_relative,
        "gradient_commuting_relative": gradient_relative,
        "node_transfer_relative": node_relative,
        "adjoint_work_relative": probe["adjoint_work_relative"],
        "linearity_relative": probe["linearity_relative"],
        "repeat_relative": probe["repeat_relative"],
        "input_unchanged": probe["input_unchanged"],
        "finite": probe["finite"],
        "line_integral_histopolation": True,
        "simple_injection": False,
        "global_transfer_matrix": False,
        "oracle_workspace_retained": False,
        "structural_projection": True,
        "structural_forbidden_entry_count": int(np.count_nonzero(~structural_mask)),
        "structural_forbidden_nnz_after": int(np.count_nonzero(forbidden)),
        "structural_removed_nonzero_count": 0,
        "structural_removed_max_abs": 0.0,
        **subset_facts,
        **nested_facts,
    }
    limits = (
        ("edge_line_integral_relative", EDGE_QUADRATURE_LIMIT),
        ("curl_flux_relative", CURL_LIMIT),
        ("gradient_commuting_relative", GRADIENT_LIMIT),
        ("node_transfer_relative", GRADIENT_LIMIT),
        ("adjoint_work_relative", ADJOINT_LIMIT),
        ("linearity_relative", LINEARITY_LIMIT),
        ("repeat_relative", REPEAT_LIMIT),
    )
    for name, limit in limits:
        if float(audit[name]) > limit:
            raise ValueError(f"{name}={audit[name]:.17g} exceeds {limit:.17g}")
    if not audit["input_unchanged"] or not audit["finite"]:
        raise ValueError("interlevel local legality probe failed")
    return audit


def audit_local_interlevel_transfer(
    fine_degree: int,
    coarse_degree: int,
    edge_transfer: np.ndarray,
    node_transfer: np.ndarray,
) -> dict[str, object]:
    """Independently recompute all bounded local transfer facts."""

    return _independent_facts(
        fine_degree, coarse_degree, edge_transfer, node_transfer
    )


class LocalInterlevelEdgeTransfer:
    """Immutable bounded cell-local transfer for one fixed supported pair."""

    __slots__ = (
        "fine_degree",
        "coarse_degree",
        "edge_transfer",
        "node_transfer",
        "audit",
        "_frozen",
    )

    def __init__(
        self,
        fine_degree: int,
        coarse_degree: int,
        edge_transfer: np.ndarray,
        node_transfer: np.ndarray,
        audit: dict[str, object],
    ) -> None:
        object.__setattr__(self, "fine_degree", int(fine_degree))
        object.__setattr__(self, "coarse_degree", int(coarse_degree))
        edge = np.ascontiguousarray(edge_transfer, dtype=np.complex128)
        node = np.ascontiguousarray(node_transfer, dtype=np.complex128)
        edge.setflags(write=False)
        node.setflags(write=False)
        object.__setattr__(self, "edge_transfer", edge)
        object.__setattr__(self, "node_transfer", node)
        object.__setattr__(self, "audit", MappingProxyType(dict(audit)))
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_frozen", False):
            raise AttributeError("LocalInterlevelEdgeTransfer is immutable")
        object.__setattr__(self, name, value)

    @property
    def edge_shape(self) -> tuple[int, int]:
        return tuple(int(value) for value in self.edge_transfer.shape)

    def apply_primal_many(self, values: np.ndarray) -> np.ndarray:
        vectors = np.asarray(values, dtype=np.complex128)
        squeezed = vectors.ndim == 1
        if squeezed:
            vectors = vectors[None, :]
        if vectors.ndim != 2 or vectors.shape[1] != self.edge_shape[1]:
            raise ValueError("coarse batch has an unexpected local shape")
        if not 1 <= vectors.shape[0] <= INTERLEVEL_BATCH_CELL_CAP:
            raise ValueError("interlevel batch exceeds the fixed cap")
        result = np.asarray(vectors @ self.edge_transfer.T, dtype=np.complex128)
        return result[0] if squeezed else result

    def apply_adjoint_many(self, values: np.ndarray) -> np.ndarray:
        vectors = np.asarray(values, dtype=np.complex128)
        squeezed = vectors.ndim == 1
        if squeezed:
            vectors = vectors[None, :]
        if vectors.ndim != 2 or vectors.shape[1] != self.edge_shape[0]:
            raise ValueError("fine batch has an unexpected local shape")
        if not 1 <= vectors.shape[0] <= INTERLEVEL_BATCH_CELL_CAP:
            raise ValueError("interlevel batch exceeds the fixed cap")
        result = np.asarray(vectors @ self.edge_transfer.conj(), dtype=np.complex128)
        return result[0] if squeezed else result


def build_local_interlevel_edge_transfer(
    fine_degree: int, coarse_degree: int
) -> LocalInterlevelEdgeTransfer:
    """Build and independently qualify one fixed local interlevel map."""

    pair = (int(fine_degree), int(coarse_degree))
    if pair not in INTERLEVEL_PAIRS:
        raise ValueError(
            "only (fine, coarse)=(6, 3), (3, 1), (6, 2), or (2, 1) is supported"
        )
    if pair == (6, 2):
        edge_transfer, node_transfer = _nested_p62_geometry_maps()
    elif pair[1] == 1:
        authority = build_local_lor_edge_geometric_transfer(pair[0])
        custom_columns = np.argsort(authority.coarse_basix_to_lor_order)
        edge_transfer = np.asarray(
            authority.edge_transfer[:, custom_columns], dtype=np.complex128
        )
        node_transfer = np.asarray(authority.node_transfer, dtype=np.complex128)
    else:
        fine_local = build_local_lor_transfer(pair[0])
        coarse_local = build_local_lor_transfer(pair[1])
        fine_element = _n1e(pair[0])
        coarse_element = _n1e(pair[1])
        interpolation = np.asarray(
            basix.compute_interpolation_operator(coarse_element, fine_element),
            dtype=np.complex128,
        )
        coarse_transform = np.asarray(
            coarse_local.high_to_lor_matrix, dtype=np.complex128
        )
        edge_transfer = np.asarray(
            fine_local.high_to_lor_matrix
            @ interpolation
            @ np.linalg.solve(
                coarse_transform,
                np.eye(coarse_transform.shape[0], dtype=np.complex128),
            ),
            dtype=np.complex128,
        )
        node_transfer = _node_transfer(
            fine_local, coarse_local, pair[0], pair[1]
        )
    edge_transfer = np.ascontiguousarray(edge_transfer, dtype=np.complex128)
    structural_mask = _structural_trace_mask(pair[0], pair[1])
    removed = edge_transfer[~structural_mask]
    removed_nonzero_count = int(np.count_nonzero(removed))
    removed_max_abs = float(np.max(np.abs(removed))) if removed.size else 0.0
    edge_transfer[~structural_mask] = 0.0
    audit = _independent_facts(
        pair[0], pair[1], edge_transfer, node_transfer
    )
    audit.update(
        structural_removed_nonzero_count=removed_nonzero_count,
        structural_removed_max_abs=removed_max_abs,
    )
    return LocalInterlevelEdgeTransfer(
        pair[0], pair[1], edge_transfer, node_transfer, audit
    )


__all__ = [
    "ADJOINT_LIMIT",
    "CURL_LIMIT",
    "EDGE_QUADRATURE_LIMIT",
    "GRADIENT_LIMIT",
    "INTERLEVEL_BATCH_CELL_CAP",
    "INTERLEVEL_PAIRS",
    "LINEARITY_LIMIT",
    "REPEAT_LIMIT",
    "LocalInterlevelEdgeTransfer",
    "audit_local_interlevel_transfer",
    "build_local_interlevel_edge_transfer",
]
