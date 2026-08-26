"""Pure local nested LOR edge prolongation for the C2 fallback.

The fixed geometry is ``h6 -> h3star -> h1star``.  ``h3star`` uses the
indices ``(0, 2, 4, 6)`` of the p6 GLL coordinates; it is a custom nested
subgrid, not a standard polynomial-level grid.  Every array here is bounded
to one reference hexahedron.  No MPI, PETSc, global transfer, or solver is
constructed.
"""

from __future__ import annotations

from types import MappingProxyType

import numpy as np

from .fullspace_lor_transfer import _edge_endpoints, _edge_id, _gll_nodes


C2_METHOD = "nested_lor_edge_hmg_v1"
C2_LEVELS = ("h6", "h3star", "h1star")
C2_PAIRS = (("h6", "h3star"), ("h3star", "h1star"))
H6_GLL_INDICES = (0, 1, 2, 3, 4, 5, 6)
H3STAR_GLL_INDICES = (0, 2, 4, 6)
H1STAR_GLL_INDICES = (0, 6)
LOCAL_BATCH_CAP = 32
EDGE_LIMIT = 1.0e-11
GRADIENT_LIMIT = 1.0e-11
CURL_LIMIT = 1.0e-11
ADJOINT_LIMIT = 1.0e-11
LINEARITY_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-13


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left)
    right = np.asarray(right)
    return float(
        np.linalg.norm(left - right)
        / max(np.linalg.norm(right), np.finfo(float).tiny)
    )


def _level_indices(level: str) -> np.ndarray:
    if level == "h6":
        values = H6_GLL_INDICES
    elif level == "h3star":
        values = H3STAR_GLL_INDICES
    elif level == "h1star":
        values = H1STAR_GLL_INDICES
    else:
        raise ValueError(f"unsupported nested HMG level: {level}")
    return np.asarray(values, dtype=np.int32)


def _level_nodes(p6_nodes: np.ndarray, level: str) -> np.ndarray:
    result = np.asarray(p6_nodes, dtype=np.float64)[_level_indices(level)].copy()
    result.setflags(write=False)
    return result


def _node_id(i: int, j: int, k: int, resolution: int) -> int:
    side = int(resolution) + 1
    return int(i + side * (j + side * k))


def _bracket(global_index: int, coarse_indices: np.ndarray) -> int:
    position = int(
        np.searchsorted(coarse_indices, int(global_index), side="right") - 1
    )
    return min(max(position, 0), int(coarse_indices.size) - 2)


def _tangent_brick(
    start: int, end: int, coarse_indices: np.ndarray
) -> int:
    for position in range(int(coarse_indices.size) - 1):
        if (
            int(coarse_indices[position]) <= int(start)
            and int(end) <= int(coarse_indices[position + 1])
        ):
            return position
    raise ValueError("nested fine edge is not contained in one coarse interval")


def _geometric_edge_map(
    fine_level: str, coarse_level: str, p6_nodes: np.ndarray
) -> np.ndarray:
    """Build the unique-owner Q1 transverse line-integral map."""

    fine_indices = _level_indices(fine_level)
    coarse_indices = _level_indices(coarse_level)
    fine_resolution = int(fine_indices.size - 1)
    coarse_resolution = int(coarse_indices.size - 1)
    starts, ends = _edge_endpoints(fine_resolution)
    result = np.zeros(
        (
            int(starts.shape[0]),
            3 * coarse_resolution * (coarse_resolution + 1) ** 2,
        ),
        dtype=np.complex128,
    )
    transverse_axes_by_axis = {
        axis: tuple(value for value in range(3) if value != axis)
        for axis in range(3)
    }
    for row, (start, end) in enumerate(zip(starts, ends, strict=True)):
        axis = int(np.flatnonzero(end != start)[0])
        fine_start = int(fine_indices[int(start[axis])])
        fine_end = int(fine_indices[int(end[axis])])
        tangent_cell = _tangent_brick(fine_start, fine_end, coarse_indices)
        tangent_ratio = float(
            (p6_nodes[fine_end] - p6_nodes[fine_start])
            / (
                p6_nodes[int(coarse_indices[tangent_cell + 1])]
                - p6_nodes[int(coarse_indices[tangent_cell])]
            )
        )
        transverse_axes = transverse_axes_by_axis[axis]
        for first_bit in (0, 1):
            for second_bit in (0, 1):
                coarse_start = [0, 0, 0]
                coarse_start[axis] = tangent_cell
                weight = tangent_ratio
                for transverse_axis, bit in zip(
                    transverse_axes, (first_bit, second_bit), strict=True
                ):
                    global_index = int(fine_indices[int(start[transverse_axis])])
                    transverse_cell = _bracket(global_index, coarse_indices)
                    left = int(coarse_indices[transverse_cell])
                    right = int(coarse_indices[transverse_cell + 1])
                    coordinate = float(
                        (p6_nodes[global_index] - p6_nodes[left])
                        / (p6_nodes[right] - p6_nodes[left])
                    )
                    coarse_start[transverse_axis] = transverse_cell + bit
                    weight *= coordinate if bit else 1.0 - coordinate
                column = _edge_id(
                    axis,
                    coarse_start[0],
                    coarse_start[1],
                    coarse_start[2],
                    coarse_resolution,
                )
                result[row, column] = weight
    return result


def _geometric_node_map(
    fine_level: str, coarse_level: str, p6_nodes: np.ndarray
) -> np.ndarray:
    """Build the matching unique-owner trilinear nodal map."""

    fine_indices = _level_indices(fine_level)
    coarse_indices = _level_indices(coarse_level)
    fine_resolution = int(fine_indices.size - 1)
    coarse_resolution = int(coarse_indices.size - 1)
    result = np.zeros(
        (
            (fine_resolution + 1) ** 3,
            (coarse_resolution + 1) ** 3,
        ),
        dtype=np.complex128,
    )
    for k in range(fine_resolution + 1):
        for j in range(fine_resolution + 1):
            for i in range(fine_resolution + 1):
                local_indices = (i, j, k)
                coarse_cells = tuple(
                    _bracket(int(fine_indices[local]), coarse_indices)
                    for local in local_indices
                )
                coordinates = tuple(
                    float(
                        (
                            p6_nodes[int(fine_indices[local])]
                            - p6_nodes[int(coarse_indices[cell])]
                        )
                        / (
                            p6_nodes[int(coarse_indices[cell + 1])]
                            - p6_nodes[int(coarse_indices[cell])]
                        )
                    )
                    for local, cell in zip(local_indices, coarse_cells, strict=True)
                )
                row = _node_id(i, j, k, fine_resolution)
                for dk in (0, 1):
                    for dj in (0, 1):
                        for di in (0, 1):
                            column = _node_id(
                                coarse_cells[0] + di,
                                coarse_cells[1] + dj,
                                coarse_cells[2] + dk,
                                coarse_resolution,
                            )
                            weight = 1.0
                            for coordinate, bit in zip(
                                coordinates, (di, dj, dk), strict=True
                            ):
                                weight *= coordinate if bit else 1.0 - coordinate
                            result[row, column] = weight
    return result


def _physical_interval_cell(
    start: float, end: float, nodes: np.ndarray, coarse_indices: np.ndarray
) -> int:
    for position in range(int(coarse_indices.size) - 1):
        left = nodes[int(coarse_indices[position])]
        right = nodes[int(coarse_indices[position + 1])]
        if start >= left and end <= right:
            return position
    raise ValueError("oracle edge is not contained in one coarse interval")


def _physical_point_cell(value: float, nodes: np.ndarray, coarse_indices: np.ndarray) -> int:
    last = int(coarse_indices.size) - 2
    for position in range(int(coarse_indices.size) - 1):
        left = nodes[int(coarse_indices[position])]
        right = nodes[int(coarse_indices[position + 1])]
        if value >= left and (value < right or position == last):
            return position
    raise ValueError("oracle point is outside the coarse nested grid")


def _oracle_edge_map(
    fine_level: str, coarse_level: str, p6_nodes: np.ndarray
) -> np.ndarray:
    """Independently integrate the lowest-order edge basis on each fine edge."""

    fine_indices = _level_indices(fine_level)
    coarse_indices = _level_indices(coarse_level)
    fine_resolution = int(fine_indices.size - 1)
    coarse_resolution = int(coarse_indices.size - 1)
    starts, ends = _edge_endpoints(fine_resolution)
    result = np.zeros(
        (
            int(starts.shape[0]),
            3 * coarse_resolution * (coarse_resolution + 1) ** 2,
        ),
        dtype=np.complex128,
    )
    for row, (start, end) in enumerate(zip(starts, ends, strict=True)):
        axis = int(np.flatnonzero(end != start)[0])
        physical_start = [
            float(p6_nodes[int(fine_indices[int(start[d])])]) for d in range(3)
        ]
        physical_end = [
            float(p6_nodes[int(fine_indices[int(end[d])])]) for d in range(3)
        ]
        tangent_start = physical_start[axis]
        tangent_end = physical_end[axis]
        tangent_cell = _physical_interval_cell(
            tangent_start,
            tangent_end,
            p6_nodes,
            coarse_indices,
        )
        tangent_length = tangent_end - tangent_start
        coarse_length = float(
            p6_nodes[int(coarse_indices[tangent_cell + 1])]
            - p6_nodes[int(coarse_indices[tangent_cell])]
        )
        tangent_ratio = tangent_length / coarse_length
        transverse_axes = tuple(value for value in range(3) if value != axis)
        for first_bit in (0, 1):
            for second_bit in (0, 1):
                coarse_start = [0, 0, 0]
                coarse_start[axis] = tangent_cell
                weight = tangent_ratio
                for transverse_axis, bit in zip(
                    transverse_axes, (first_bit, second_bit), strict=True
                ):
                    value = physical_start[transverse_axis]
                    transverse_cell = _physical_point_cell(
                        value, p6_nodes, coarse_indices
                    )
                    left_index = int(coarse_indices[transverse_cell])
                    right_index = int(coarse_indices[transverse_cell + 1])
                    coordinate = float(
                        (value - p6_nodes[left_index])
                        / (p6_nodes[right_index] - p6_nodes[left_index])
                    )
                    coarse_start[transverse_axis] = transverse_cell + bit
                    weight *= coordinate if bit else 1.0 - coordinate
                column = _edge_id(
                    axis,
                    coarse_start[0],
                    coarse_start[1],
                    coarse_start[2],
                    coarse_resolution,
                )
                result[row, column] = weight
    return result


def _oracle_node_map(
    fine_level: str, coarse_level: str, p6_nodes: np.ndarray
) -> np.ndarray:
    """Independently evaluate the trilinear nodal basis at physical points."""

    fine_indices = _level_indices(fine_level)
    coarse_indices = _level_indices(coarse_level)
    fine_resolution = int(fine_indices.size - 1)
    coarse_resolution = int(coarse_indices.size - 1)
    result = np.zeros(
        ((fine_resolution + 1) ** 3, (coarse_resolution + 1) ** 3),
        dtype=np.complex128,
    )
    for k in range(fine_resolution + 1):
        for j in range(fine_resolution + 1):
            for i in range(fine_resolution + 1):
                local_indices = (i, j, k)
                physical = tuple(
                    float(p6_nodes[int(fine_indices[index])])
                    for index in local_indices
                )
                cells = tuple(
                    _physical_point_cell(value, p6_nodes, coarse_indices)
                    for value in physical
                )
                coordinates = tuple(
                    float(
                        (value - p6_nodes[int(coarse_indices[cell])])
                        / (
                            p6_nodes[int(coarse_indices[cell + 1])]
                            - p6_nodes[int(coarse_indices[cell])]
                        )
                    )
                    for value, cell in zip(physical, cells, strict=True)
                )
                row = _node_id(i, j, k, fine_resolution)
                for dk in (0, 1):
                    for dj in (0, 1):
                        for di in (0, 1):
                            column = _node_id(
                                cells[0] + di,
                                cells[1] + dj,
                                cells[2] + dk,
                                coarse_resolution,
                            )
                            weight = 1.0
                            for coordinate, bit in zip(
                                coordinates, (di, dj, dk), strict=True
                            ):
                                weight *= coordinate if bit else 1.0 - coordinate
                            result[row, column] = weight
    return result


def _gradient_incidence(resolution: int) -> np.ndarray:
    starts, ends = _edge_endpoints(resolution)
    result = np.zeros(
        (int(starts.shape[0]), (int(resolution) + 1) ** 3),
        dtype=np.complex128,
    )
    for row, (start, end) in enumerate(zip(starts, ends, strict=True)):
        result[row, _node_id(*start, resolution)] = -1.0
        result[row, _node_id(*end, resolution)] = 1.0
    return result


def _face_incidence(
    resolution: int,
) -> tuple[tuple[tuple[int, int, int, int], ...], np.ndarray]:
    resolution = int(resolution)
    face_count = 3 * (resolution + 1) * resolution * resolution
    edge_count = 3 * resolution * (resolution + 1) ** 2
    descriptors: list[tuple[int, int, int, int]] = []
    result = np.zeros((face_count, edge_count), dtype=np.complex128)

    def add_edge(row: int, axis: int, coordinates: list[int], sign: int) -> None:
        result[row, _edge_id(axis, *coordinates, resolution)] = sign

    row = 0
    for normal in range(3):
        tangent_b = (normal + 1) % 3
        tangent_c = (normal + 2) % 3
        for plane in range(resolution + 1):
            for cell_b in range(resolution):
                for cell_c in range(resolution):
                    descriptors.append((normal, plane, cell_b, cell_c))
                    base = [0, 0, 0]
                    base[normal] = plane
                    base[tangent_b] = cell_b
                    base[tangent_c] = cell_c

                    plus_b = base.copy()
                    add_edge(row, tangent_b, plus_b, 1)
                    plus_c = base.copy()
                    plus_c[tangent_b] += 1
                    add_edge(row, tangent_c, plus_c, 1)
                    minus_b = base.copy()
                    minus_b[tangent_c] += 1
                    add_edge(row, tangent_b, minus_b, -1)
                    minus_c = base.copy()
                    add_edge(row, tangent_c, minus_c, -1)
                    row += 1
    return tuple(descriptors), result


def _curl_commuting_relative(
    fine_level: str,
    coarse_level: str,
    edge_transfer: np.ndarray,
) -> float:
    fine_indices = _level_indices(fine_level)
    coarse_indices = _level_indices(coarse_level)
    fine_resolution = int(fine_indices.size - 1)
    coarse_resolution = int(coarse_indices.size - 1)
    fine_descriptors, fine_incidence = _face_incidence(fine_resolution)
    coarse_descriptors, coarse_incidence = _face_incidence(coarse_resolution)
    fine_flux = fine_incidence @ edge_transfer
    aggregated = np.zeros_like(coarse_incidence)
    for coarse_row, (axis, plane, cell_b, cell_c) in enumerate(
        coarse_descriptors
    ):
        tangent_b = (axis + 1) % 3
        tangent_c = (axis + 2) % 3
        coarse_b0 = int(coarse_indices[cell_b])
        coarse_b1 = int(coarse_indices[cell_b + 1])
        coarse_c0 = int(coarse_indices[cell_c])
        coarse_c1 = int(coarse_indices[cell_c + 1])
        plane_index = int(coarse_indices[plane])
        for fine_row, (
            fine_axis,
            fine_plane,
            fine_cell_b,
            fine_cell_c,
        ) in enumerate(fine_descriptors):
            if (
                fine_axis != axis
                or int(fine_indices[fine_plane]) != plane_index
            ):
                continue
            fine_b0 = int(fine_indices[fine_cell_b])
            fine_b1 = int(fine_indices[fine_cell_b + 1])
            fine_c0 = int(fine_indices[fine_cell_c])
            fine_c1 = int(fine_indices[fine_cell_c + 1])
            if (
                fine_b0 >= coarse_b0
                and fine_b1 <= coarse_b1
                and fine_c0 >= coarse_c0
                and fine_c1 <= coarse_c1
            ):
                aggregated[coarse_row] += fine_flux[fine_row]
    return _relative(aggregated, coarse_incidence)


def _probe_facts(edge_transfer: np.ndarray) -> dict[str, object]:
    columns = int(edge_transfer.shape[1])
    rows = int(edge_transfer.shape[0])
    first = np.arange(1, columns + 1, dtype=np.float64).astype(np.complex128)
    first += 1j * np.arange(columns, 0, -1, dtype=np.float64)
    second = np.arange(columns, 2 * columns, dtype=np.float64).astype(np.complex128)
    second -= 0.5j * np.arange(1, columns + 1, dtype=np.float64)
    before = first.copy()
    fine = np.arange(1, rows + 1, dtype=np.float64).astype(np.complex128)
    fine += 0.25j * np.arange(rows, 0, -1, dtype=np.float64)
    alpha = 0.37 + 0.19j
    beta = -0.23 + 0.41j
    action = edge_transfer @ first
    repeat = edge_transfer @ first
    combo = edge_transfer @ (alpha * first + beta * second)
    expected = alpha * action + beta * (edge_transfer @ second)
    lhs = np.vdot(action, fine)
    rhs = np.vdot(first, edge_transfer.conj().T @ fine)
    return {
        "adjoint_work_relative": float(
            abs(lhs - rhs) / max(abs(rhs), np.finfo(float).tiny)
        ),
        "linearity_relative": _relative(combo, expected),
        "repeat_relative": _relative(repeat, action),
        "input_unchanged": bool(np.array_equal(first, before)),
        "finite": bool(
            np.all(np.isfinite(action))
            and np.all(np.isfinite(repeat))
            and np.all(np.isfinite(combo))
        ),
    }


def _pair_facts(
    fine_level: str,
    coarse_level: str,
    edge_transfer: np.ndarray,
    node_transfer: np.ndarray,
    p6_nodes: np.ndarray,
) -> dict[str, object]:
    fine_indices = _level_indices(fine_level)
    coarse_indices = _level_indices(coarse_level)
    fine_resolution = int(fine_indices.size - 1)
    coarse_resolution = int(coarse_indices.size - 1)
    expected_edge_shape = (
        3 * fine_resolution * (fine_resolution + 1) ** 2,
        3 * coarse_resolution * (coarse_resolution + 1) ** 2,
    )
    expected_node_shape = (
        (fine_resolution + 1) ** 3,
        (coarse_resolution + 1) ** 3,
    )
    edge_transfer = np.asarray(edge_transfer, dtype=np.complex128)
    node_transfer = np.asarray(node_transfer, dtype=np.complex128)
    if edge_transfer.shape != expected_edge_shape:
        raise ValueError(f"nested edge shape {edge_transfer.shape} != {expected_edge_shape}")
    if node_transfer.shape != expected_node_shape:
        raise ValueError(f"nested node shape {node_transfer.shape} != {expected_node_shape}")
    if not np.all(np.isfinite(edge_transfer)) or not np.all(np.isfinite(node_transfer)):
        raise ValueError("nested local transfer contains non-finite values")

    oracle_edge = _oracle_edge_map(fine_level, coarse_level, p6_nodes)
    oracle_node = _oracle_node_map(fine_level, coarse_level, p6_nodes)
    fine_gradient = _gradient_incidence(fine_resolution)
    coarse_gradient = _gradient_incidence(coarse_resolution)
    probe = _probe_facts(edge_transfer)
    gradient_relative = _relative(
        fine_gradient @ node_transfer,
        edge_transfer @ coarse_gradient,
    )
    curl_relative = _curl_commuting_relative(
        fine_level, coarse_level, edge_transfer
    )
    edge_rank = int(np.linalg.matrix_rank(edge_transfer))
    edge_line_integral_relative = _relative(edge_transfer, oracle_edge)
    facts: dict[str, object] = {
        "method": C2_METHOD,
        "pair_fine_to_coarse": (fine_level, coarse_level),
        "fine_level": fine_level,
        "coarse_level": coarse_level,
        "fine_gll_indices": tuple(int(value) for value in fine_indices),
        "coarse_gll_indices": tuple(int(value) for value in coarse_indices),
        "custom_nested_subgrid": True,
        "standard_polynomial_level_substitution": False,
        "edge_shape": expected_edge_shape,
        "node_shape": expected_node_shape,
        "edge_nnz": int(np.count_nonzero(edge_transfer)),
        "node_nnz": int(np.count_nonzero(node_transfer)),
        "line_integral_histopolation": True,
        "simple_injection": False,
        "edge_rank": edge_rank,
        "edge_columns_full_rank": bool(edge_rank == expected_edge_shape[1]),
        "edge_line_integral_relative": edge_line_integral_relative,
        "node_functional_relative": _relative(node_transfer, oracle_node),
        "curl_commuting_relative": curl_relative,
        "gradient_commuting_relative": gradient_relative,
        "adjoint_work_relative": probe["adjoint_work_relative"],
        "linearity_relative": probe["linearity_relative"],
        "repeat_relative": probe["repeat_relative"],
        "input_unchanged": probe["input_unchanged"],
        "finite": bool(
            probe["finite"]
            and np.all(np.isfinite(oracle_edge))
            and np.all(np.isfinite(oracle_node))
        ),
        "deterministic_owner_policy": "fixed_half_open_nested_brick",
        "orientation_policy": "canonical_positive_reference_axes",
        "global_transfer_matrix": False,
        "numeric_allgather": False,
        "solver_built": False,
    }
    failures: list[str] = []
    if not facts["edge_columns_full_rank"]:
        failures.append("edge transfer is not full column rank")
    if facts["edge_line_integral_relative"] > EDGE_LIMIT:
        failures.append("edge line-integral oracle")
    if facts["node_functional_relative"] > EDGE_LIMIT:
        failures.append("node interpolation oracle")
    if facts["curl_commuting_relative"] > CURL_LIMIT:
        failures.append("curl commuting")
    if facts["gradient_commuting_relative"] > GRADIENT_LIMIT:
        failures.append("gradient commuting")
    if facts["adjoint_work_relative"] > ADJOINT_LIMIT:
        failures.append("adjoint work")
    if facts["linearity_relative"] > LINEARITY_LIMIT:
        failures.append("linearity")
    if facts["repeat_relative"] > REPEAT_LIMIT:
        failures.append("repeat")
    if facts["input_unchanged"] is not True or facts["finite"] is not True:
        failures.append("finite/input")
    facts["gate_passed"] = not failures
    facts["gate_failures"] = tuple(failures)
    if failures:
        raise ValueError(
            f"nested local transfer {fine_level}->{coarse_level} failed: "
            + ", ".join(failures)
        )
    return facts


class NestedHmgLocalTransfer:
    """Immutable bounded transfer for one fixed nested HMG pair."""

    __slots__ = (
        "fine_level",
        "coarse_level",
        "fine_nodes",
        "coarse_nodes",
        "edge_transfer",
        "node_transfer",
        "audit",
        "_frozen",
    )

    def __init__(
        self,
        fine_level: str,
        coarse_level: str,
        fine_nodes: np.ndarray,
        coarse_nodes: np.ndarray,
        edge_transfer: np.ndarray,
        node_transfer: np.ndarray,
        audit: dict[str, object],
    ) -> None:
        if (fine_level, coarse_level) not in C2_PAIRS:
            raise ValueError("only fixed h6->h3star and h3star->h1star pairs are supported")
        for name, value in (
            ("fine_nodes", fine_nodes),
            ("coarse_nodes", coarse_nodes),
            ("edge_transfer", edge_transfer),
            ("node_transfer", node_transfer),
        ):
            frozen = np.ascontiguousarray(value, dtype=np.complex128 if "transfer" in name else np.float64).copy()
            frozen.setflags(write=False)
            object.__setattr__(self, name, frozen)
        object.__setattr__(self, "fine_level", fine_level)
        object.__setattr__(self, "coarse_level", coarse_level)
        object.__setattr__(self, "audit", MappingProxyType(dict(audit)))
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_frozen", False):
            raise AttributeError("NestedHmgLocalTransfer is immutable")
        object.__setattr__(self, name, value)

    @property
    def edge_shape(self) -> tuple[int, int]:
        return tuple(int(value) for value in self.edge_transfer.shape)

    def apply_primal_many(self, values: np.ndarray) -> np.ndarray:
        vectors = np.asarray(values, dtype=np.complex128)
        squeezed = vectors.ndim == 1
        if squeezed:
            vectors = vectors[None, :]
        if vectors.ndim != 2 or vectors.shape[1] != self.edge_transfer.shape[1]:
            raise ValueError("nested coarse batch has an unexpected shape")
        if not 1 <= vectors.shape[0] <= LOCAL_BATCH_CAP:
            raise ValueError("nested batch exceeds the fixed local cap")
        result = np.asarray(vectors @ self.edge_transfer.T, dtype=np.complex128)
        return result[0] if squeezed else result

    def apply_adjoint_many(self, values: np.ndarray) -> np.ndarray:
        vectors = np.asarray(values, dtype=np.complex128)
        squeezed = vectors.ndim == 1
        if squeezed:
            vectors = vectors[None, :]
        if vectors.ndim != 2 or vectors.shape[1] != self.edge_transfer.shape[0]:
            raise ValueError("nested fine batch has an unexpected shape")
        if not 1 <= vectors.shape[0] <= LOCAL_BATCH_CAP:
            raise ValueError("nested batch exceeds the fixed local cap")
        result = np.asarray(vectors @ self.edge_transfer.conj(), dtype=np.complex128)
        return result[0] if squeezed else result


class NestedLorEdgeHmg:
    """Immutable fixed local h6/h3star/h1star transfer pair."""

    __slots__ = (
        "h6_nodes",
        "h3star_nodes",
        "h1star_nodes",
        "h6_to_h3star",
        "h3star_to_h1star",
        "audit",
        "_frozen",
    )

    def __init__(
        self,
        h6_nodes: np.ndarray,
        h3star_nodes: np.ndarray,
        h1star_nodes: np.ndarray,
        h6_to_h3star: NestedHmgLocalTransfer,
        h3star_to_h1star: NestedHmgLocalTransfer,
        audit: dict[str, object],
    ) -> None:
        for name, value in (
            ("h6_nodes", h6_nodes),
            ("h3star_nodes", h3star_nodes),
            ("h1star_nodes", h1star_nodes),
        ):
            frozen = np.ascontiguousarray(value, dtype=np.float64).copy()
            frozen.setflags(write=False)
            object.__setattr__(self, name, frozen)
        object.__setattr__(self, "h6_to_h3star", h6_to_h3star)
        object.__setattr__(self, "h3star_to_h1star", h3star_to_h1star)
        object.__setattr__(self, "audit", MappingProxyType(dict(audit)))
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_frozen", False):
            raise AttributeError("NestedLorEdgeHmg is immutable")
        object.__setattr__(self, name, value)


def audit_nested_hmg_transfer(transfer: NestedHmgLocalTransfer) -> dict[str, object]:
    """Recompute one pair against the independent endpoint oracle."""

    p6_nodes = np.asarray(_gll_nodes(6), dtype=np.float64)
    expected_fine = _level_nodes(p6_nodes, transfer.fine_level)
    expected_coarse = _level_nodes(p6_nodes, transfer.coarse_level)
    if not np.array_equal(transfer.fine_nodes, expected_fine):
        raise ValueError("nested fine coordinate identity is not exact")
    if not np.array_equal(transfer.coarse_nodes, expected_coarse):
        raise ValueError("nested coarse coordinate identity is not exact")
    return _pair_facts(
        transfer.fine_level,
        transfer.coarse_level,
        transfer.edge_transfer,
        transfer.node_transfer,
        p6_nodes,
    )


def build_nested_lor_edge_hmg() -> NestedLorEdgeHmg:
    """Build and qualify the only supported C2 local nested hierarchy."""

    p6_nodes = np.asarray(_gll_nodes(6), dtype=np.float64).copy()
    h6_nodes = _level_nodes(p6_nodes, "h6")
    h3star_nodes = _level_nodes(p6_nodes, "h3star")
    h1star_nodes = _level_nodes(p6_nodes, "h1star")

    def build_pair(fine_level: str, coarse_level: str) -> NestedHmgLocalTransfer:
        edge = _geometric_edge_map(fine_level, coarse_level, p6_nodes)
        node = _geometric_node_map(fine_level, coarse_level, p6_nodes)
        facts = _pair_facts(
            fine_level, coarse_level, edge, node, p6_nodes
        )
        return NestedHmgLocalTransfer(
            fine_level,
            coarse_level,
            _level_nodes(p6_nodes, fine_level),
            _level_nodes(p6_nodes, coarse_level),
            edge,
            node,
            facts,
        )

    h6_to_h3star = build_pair("h6", "h3star")
    h3star_to_h1star = build_pair("h3star", "h1star")
    direct = _oracle_edge_map("h6", "h1star", p6_nodes)
    composition = h6_to_h3star.edge_transfer @ h3star_to_h1star.edge_transfer
    composition_relative = _relative(composition, direct)
    direct_node = _oracle_node_map("h6", "h1star", p6_nodes)
    node_composition = (
        h6_to_h3star.node_transfer @ h3star_to_h1star.node_transfer
    )
    node_composition_relative = _relative(node_composition, direct_node)
    if composition_relative > EDGE_LIMIT:
        raise ValueError(
            "nested h6->h3star->h1star composition exceeds the fixed limit"
        )
    if node_composition_relative > EDGE_LIMIT:
        raise ValueError(
            "nested h6->h3star->h1star node composition exceeds the fixed limit"
        )
    audit = {
        "method": C2_METHOD,
        "levels": C2_LEVELS,
        "pairs": C2_PAIRS,
        "fine_gll_indices": H6_GLL_INDICES,
        "h3star_gll_indices": H3STAR_GLL_INDICES,
        "h1star_gll_indices": H1STAR_GLL_INDICES,
        "h3star_is_standard_polynomial_level": False,
        "node_subset_exact": True,
        "composition_direct_edge_relative": composition_relative,
        "composition_direct_node_relative": node_composition_relative,
        "composition_direct_is_independent_oracle": True,
        "finite": True,
        "global_transfer_matrix": False,
        "numeric_allgather": False,
        "solver_built": False,
    }
    return NestedLorEdgeHmg(
        h6_nodes,
        h3star_nodes,
        h1star_nodes,
        h6_to_h3star,
        h3star_to_h1star,
        audit,
    )


__all__ = [
    "ADJOINT_LIMIT",
    "C2_LEVELS",
    "C2_METHOD",
    "C2_PAIRS",
    "CURL_LIMIT",
    "EDGE_LIMIT",
    "GRADIENT_LIMIT",
    "H1STAR_GLL_INDICES",
    "H3STAR_GLL_INDICES",
    "H6_GLL_INDICES",
    "LINEARITY_LIMIT",
    "LOCAL_BATCH_CAP",
    "NestedHmgLocalTransfer",
    "NestedLorEdgeHmg",
    "REPEAT_LIMIT",
    "audit_nested_hmg_transfer",
    "build_nested_lor_edge_hmg",
]
