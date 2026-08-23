"""Small affine-cell high-order/LOR H(curl) transfer oracle.

This module is deliberately local.  It builds one tensor-product affine
hexahedron using Gauss--Lobatto--Legendre refinement, lowest-order edge
incidence, and a positive curl-curl plus mass auxiliary form.  No global
transfer matrix or global numeric payload is part of this API; the dense
objects are the bounded single-cell L1 oracle only.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
import sys
import time

import basix
import numpy as np
from scipy.linalg import eigvalsh

from .hcurl_affine_isotropic_tensor import (
    AffineIsotropicMaxwellTensorFactory,
    AffineIsotropicMaxwellTensorSpec,
)

L1_TRANSFER_TOL = 1.0e-12
L1_REPEAT_TOL = 1.0e-13
L1_SPECTRAL_CONDITION_LIMIT = 100.0
L1_DEGREES = (2, 3, 6)
LOR_BATCH_CELL_CAP = 32


def _gll_nodes(degree: int) -> np.ndarray:
    degree = int(degree)
    if degree < 1:
        raise ValueError("GLL refinement degree must be positive")
    polynomial = np.zeros(degree + 1, dtype=np.float64)
    polynomial[-1] = 1.0
    interior = np.polynomial.legendre.legroots(
        np.polynomial.legendre.legder(polynomial)
    )
    nodes = np.concatenate(
        (
            np.asarray([0.0], dtype=np.float64),
            (np.asarray(interior, dtype=np.float64) + 1.0) / 2.0,
            np.asarray([1.0], dtype=np.float64),
        )
    )
    if nodes.size != degree + 1 or not np.all(np.diff(nodes) > 0.0):
        raise RuntimeError("GLL nodes are not strictly ordered")
    nodes.setflags(write=False)
    return nodes


def _edge_id(axis: int, i: int, j: int, k: int, degree: int) -> int:
    count = degree * (degree + 1) ** 2
    axis = int(axis)
    if axis == 0:
        return int(i + degree * (j + (degree + 1) * k))
    if axis == 1:
        return int(count + j + degree * (k + (degree + 1) * i))
    if axis == 2:
        return int(2 * count + k + degree * (j + (degree + 1) * i))
    raise ValueError("edge axis must be 0, 1, or 2")


def _cell_edges(i: int, j: int, k: int, degree: int) -> tuple[int, ...]:
    return (
        _edge_id(0, i, j, k, degree),
        _edge_id(0, i, j + 1, k, degree),
        _edge_id(0, i, j, k + 1, degree),
        _edge_id(0, i, j + 1, k + 1, degree),
        _edge_id(1, i, j, k, degree),
        _edge_id(1, i + 1, j, k, degree),
        _edge_id(1, i, j, k + 1, degree),
        _edge_id(1, i + 1, j, k + 1, degree),
        _edge_id(2, i, j, k, degree),
        _edge_id(2, i + 1, j, k, degree),
        _edge_id(2, i, j + 1, k, degree),
        _edge_id(2, i + 1, j + 1, k, degree),
    )


def _edge_endpoints(degree: int) -> tuple[np.ndarray, np.ndarray]:
    starts: list[tuple[int, int, int]] = []
    ends: list[tuple[int, int, int]] = []
    for k in range(degree + 1):
        for j in range(degree + 1):
            for i in range(degree):
                starts.append((i, j, k))
                ends.append((i + 1, j, k))
    for i in range(degree + 1):
        for k in range(degree + 1):
            for j in range(degree):
                starts.append((i, j, k))
                ends.append((i, j + 1, k))
    for i in range(degree + 1):
        for j in range(degree + 1):
            for k in range(degree):
                starts.append((i, j, k))
                ends.append((i, j, k + 1))
    start = np.asarray(starts, dtype=np.int32)
    end = np.asarray(ends, dtype=np.int32)
    expected = 3 * degree * (degree + 1) ** 2
    if start.shape != (expected, 3) or end.shape != start.shape:
        raise RuntimeError("LOR edge endpoint inventory does not close")
    return start, end


def _local_edge_basis(
    x: float,
    y: float,
    z: float,
    widths: tuple[float, float, float],
) -> tuple[np.ndarray, np.ndarray]:
    hx, hy, hz = (float(value) for value in widths)
    values = np.zeros((12, 3), dtype=np.float64)
    curls = np.zeros((12, 3), dtype=np.float64)
    for index, (side_y, side_z) in enumerate(
        ((0, 0), (1, 0), (0, 1), (1, 1))
    ):
        ly = 1.0 - y if side_y == 0 else y
        lz = 1.0 - z if side_z == 0 else z
        dly = (-1.0 if side_y == 0 else 1.0) / hy
        dlz = (-1.0 if side_z == 0 else 1.0) / hz
        values[index, 0] = ly * lz / hx
        curls[index, 1] = ly * dlz / hx
        curls[index, 2] = -dly * lz / hx
    for index, (side_x, side_z) in enumerate(
        ((0, 0), (1, 0), (0, 1), (1, 1)), start=4
    ):
        lx = 1.0 - x if side_x == 0 else x
        lz = 1.0 - z if side_z == 0 else z
        dlx = (-1.0 if side_x == 0 else 1.0) / hx
        dlz = (-1.0 if side_z == 0 else 1.0) / hz
        values[index, 1] = lx * lz / hy
        curls[index, 0] = -lx * dlz / hy
        curls[index, 2] = dlx * lz / hy
    for index, (side_x, side_y) in enumerate(
        ((0, 0), (1, 0), (0, 1), (1, 1)), start=8
    ):
        lx = 1.0 - x if side_x == 0 else x
        ly = 1.0 - y if side_y == 0 else y
        dlx = (-1.0 if side_x == 0 else 1.0) / hx
        dly = (-1.0 if side_y == 0 else 1.0) / hy
        values[index, 2] = lx * ly / hz
        curls[index, 0] = dly * lx / hz
        curls[index, 1] = -dlx * ly / hz
    return values, curls


def _assemble_lor_matrix(
    degree: int,
    nodes: np.ndarray,
    widths: tuple[float, float, float],
) -> np.ndarray:
    edge_count = 3 * degree * (degree + 1) ** 2
    matrix = np.zeros((edge_count, edge_count), dtype=np.complex128)
    quadrature, weights = np.polynomial.legendre.leggauss(3)
    quadrature = (quadrature + 1.0) / 2.0
    weights = weights / 2.0
    for i in range(degree):
        for j in range(degree):
            for k in range(degree):
                cell_widths = (
                    widths[0] * (nodes[i + 1] - nodes[i]),
                    widths[1] * (nodes[j + 1] - nodes[j]),
                    widths[2] * (nodes[k + 1] - nodes[k]),
                )
                local = np.zeros((12, 12), dtype=np.complex128)
                for ix, x in enumerate(quadrature):
                    for iy, y in enumerate(quadrature):
                        for iz, z in enumerate(quadrature):
                            values, curls = _local_edge_basis(
                                float(x), float(y), float(z), cell_widths
                            )
                            weight = (
                                weights[ix]
                                * weights[iy]
                                * weights[iz]
                                * float(np.prod(cell_widths))
                            )
                            local += weight * (
                                curls @ curls.conj().T
                                + values @ values.conj().T
                            )
                edge_ids = _cell_edges(i, j, k, degree)
                matrix[np.ix_(edge_ids, edge_ids)] += local
    return np.ascontiguousarray(matrix)


def _build_edge_transfer(
    degree: int,
    nodes: np.ndarray,
    high_element: Any,
) -> np.ndarray:
    edge_count = 3 * degree * (degree + 1) ** 2
    transfer = np.zeros(
        (edge_count, int(high_element.dim)), dtype=np.complex128
    )
    quadrature, weights = np.polynomial.legendre.leggauss(degree + 2)

    def fill(axis: int, i: int, j: int, k: int) -> None:
        if axis == 0:
            a, b = nodes[i], nodes[i + 1]
            points = (quadrature + 1.0) * (b - a) / 2.0 + a
            samples = np.column_stack(
                (
                    points,
                    np.full_like(points, nodes[j]),
                    np.full_like(points, nodes[k]),
                )
            )
        elif axis == 1:
            a, b = nodes[j], nodes[j + 1]
            points = (quadrature + 1.0) * (b - a) / 2.0 + a
            samples = np.column_stack(
                (
                    np.full_like(points, nodes[i]),
                    points,
                    np.full_like(points, nodes[k]),
                )
            )
        else:
            a, b = nodes[k], nodes[k + 1]
            points = (quadrature + 1.0) * (b - a) / 2.0 + a
            samples = np.column_stack(
                (
                    np.full_like(points, nodes[i]),
                    np.full_like(points, nodes[j]),
                    points,
                )
            )
        values = high_element.tabulate(0, samples)[0]
        transfer[_edge_id(axis, i, j, k, degree)] = (
            (weights * (b - a) / 2.0) @ values[:, :, axis]
        )

    for j in range(degree + 1):
        for k in range(degree + 1):
            for i in range(degree):
                fill(0, i, j, k)
    for i in range(degree + 1):
        for k in range(degree + 1):
            for j in range(degree):
                fill(1, i, j, k)
    for i in range(degree + 1):
        for j in range(degree + 1):
            for k in range(degree):
                fill(2, i, j, k)
    if not np.all(np.isfinite(transfer)):
        raise FloatingPointError("high-to-LOR transfer is non-finite")
    return transfer


def _face_descriptors(
    degree: int,
) -> tuple[tuple[int, int, int, int, int], ...]:
    descriptors: list[tuple[int, int, int, int, int]] = []
    for k in range(degree + 1):
        for j in range(degree):
            for i in range(degree):
                descriptors.append((2, 1, i, j, k))
    for i in range(degree + 1):
        for k in range(degree):
            for j in range(degree):
                descriptors.append((0, 1, i, j, k))
    for j in range(degree + 1):
        for k in range(degree):
            for i in range(degree):
                descriptors.append((1, -1, i, j, k))
    return tuple(descriptors)


def _build_incidence(
    degree: int,
) -> tuple[
    np.ndarray,
    np.ndarray,
    tuple[tuple[int, int, int, int, int], ...],
]:
    node_count = (degree + 1) ** 3
    edge_count = 3 * degree * (degree + 1) ** 2
    gradient = np.zeros((edge_count, node_count), dtype=np.float64)

    def node(i: int, j: int, k: int) -> int:
        return int(i + (degree + 1) * (j + (degree + 1) * k))

    starts, ends = _edge_endpoints(degree)
    for row, (start, end) in enumerate(zip(starts, ends, strict=True)):
        gradient[row, node(*end)] = 1.0
        gradient[row, node(*start)] = -1.0

    descriptors = _face_descriptors(degree)
    curl = np.zeros((len(descriptors), edge_count), dtype=np.float64)
    for row, (axis, _normal_sign, i, j, k) in enumerate(descriptors):
        if axis == 2:
            face = (
                (1, _edge_id(0, i, j, k, degree)),
                (1, _edge_id(1, i + 1, j, k, degree)),
                (-1, _edge_id(0, i, j + 1, k, degree)),
                (-1, _edge_id(1, i, j, k, degree)),
            )
        elif axis == 0:
            face = (
                (1, _edge_id(1, i, j, k, degree)),
                (1, _edge_id(2, i, j + 1, k, degree)),
                (-1, _edge_id(1, i, j, k + 1, degree)),
                (-1, _edge_id(2, i, j, k, degree)),
            )
        else:
            face = (
                (1, _edge_id(0, i, j, k, degree)),
                (1, _edge_id(2, i + 1, j, k, degree)),
                (-1, _edge_id(0, i, j, k + 1, degree)),
                (-1, _edge_id(2, i, j, k, degree)),
            )
        for sign, edge in face:
            curl[row, edge] = float(sign)
    return gradient, curl, descriptors


def _build_face_curl_transfer(
    degree: int,
    nodes: np.ndarray,
    high_element: Any,
    descriptors: tuple[tuple[int, int, int, int, int], ...],
) -> np.ndarray:
    transfer = np.zeros(
        (len(descriptors), int(high_element.dim)), dtype=np.float64
    )
    quadrature, weights = np.polynomial.legendre.leggauss(degree + 2)

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
        derivatives = high_element.tabulate(1, samples)
        curls = np.stack(
            (
                derivatives[2, :, :, 2] - derivatives[3, :, :, 1],
                derivatives[3, :, :, 0] - derivatives[1, :, :, 2],
                derivatives[1, :, :, 1] - derivatives[2, :, :, 0],
            ),
            axis=2,
        )
        transfer[row] = float(normal_sign) * (
            face_weight.reshape(-1) @ curls[:, :, component]
        )
    return transfer


def _build_scalar_transfer_and_gradient(
    degree: int,
    nodes: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    scalar = basix.create_element(
        basix.ElementFamily.P,
        basix.CellType.hexahedron,
        degree,
        basix.LagrangeVariant.equispaced,
    )
    node_points = np.asarray(
        [
            (nodes[i], nodes[j], nodes[k])
            for k in range(degree + 1)
            for j in range(degree + 1)
            for i in range(degree + 1)
        ],
        dtype=np.float64,
    )
    scalar_transfer = np.asarray(scalar.tabulate(0, node_points)[0, :, :, 0])
    edge_count = 3 * degree * (degree + 1) ** 2
    gradient_high_edge = np.zeros(
        (edge_count, int(scalar.dim)), dtype=np.float64
    )
    quadrature, weights = np.polynomial.legendre.leggauss(degree + 2)

    def fill(axis: int, i: int, j: int, k: int) -> None:
        if axis == 0:
            a, b = nodes[i], nodes[i + 1]
            points = (quadrature + 1.0) * (b - a) / 2.0 + a
            samples = np.column_stack(
                (
                    points,
                    np.full_like(points, nodes[j]),
                    np.full_like(points, nodes[k]),
                )
            )
        elif axis == 1:
            a, b = nodes[j], nodes[j + 1]
            points = (quadrature + 1.0) * (b - a) / 2.0 + a
            samples = np.column_stack(
                (
                    np.full_like(points, nodes[i]),
                    points,
                    np.full_like(points, nodes[k]),
                )
            )
        else:
            a, b = nodes[k], nodes[k + 1]
            points = (quadrature + 1.0) * (b - a) / 2.0 + a
            samples = np.column_stack(
                (
                    np.full_like(points, nodes[i]),
                    np.full_like(points, nodes[j]),
                    points,
                )
            )
        values = scalar.tabulate(1, samples)[1 + axis, :, :, 0]
        gradient_high_edge[_edge_id(axis, i, j, k, degree)] = (
            (weights * (b - a) / 2.0) @ values
        )

    for j in range(degree + 1):
        for k in range(degree + 1):
            for i in range(degree):
                fill(0, i, j, k)
    for i in range(degree + 1):
        for k in range(degree + 1):
            for j in range(degree):
                fill(1, i, j, k)
    for i in range(degree + 1):
        for j in range(degree + 1):
            for k in range(degree):
                fill(2, i, j, k)
    return scalar_transfer, gradient_high_edge


@dataclass(frozen=True)
class LocalLorTransfer:
    """One bounded single-cell high-order/LOR transfer and its audit."""

    degree: int
    widths: tuple[float, float, float]
    nodes: np.ndarray
    high_to_lor_matrix: np.ndarray
    lor_to_high_matrix: np.ndarray
    high_matrix: np.ndarray
    lor_matrix: np.ndarray
    h1_transfer: np.ndarray
    high_gradient_edge: np.ndarray
    high_curl_face: np.ndarray
    lor_gradient: np.ndarray
    lor_curl_incidence: np.ndarray
    audit: MappingProxyType

    def high_to_lor(self, values: np.ndarray) -> np.ndarray:
        vector = np.asarray(values, dtype=np.complex128)
        if vector.shape != (self.high_to_lor_matrix.shape[1],):
            raise ValueError("high vector has an unexpected local dimension")
        return self.high_to_lor_matrix @ vector

    def lor_to_high(self, values: np.ndarray) -> np.ndarray:
        vector = np.asarray(values, dtype=np.complex128)
        if vector.shape != (self.lor_to_high_matrix.shape[1],):
            raise ValueError("LOR vector has an unexpected local dimension")
        return self.lor_to_high_matrix @ vector


@dataclass(frozen=True)
class ReferenceFactorLorTransfer:
    """Owner-local H/LOR transfer retaining three axis-local tensors.

    The dense matrices used to derive these tensors are bounded single-cell
    oracle workspaces and are released before this object is returned.  The
    retained action consists of one coefficient tensor per reference axis in
    each direction; no dense transfer matrix is kept.
    """

    degree: int
    nodes: np.ndarray
    high_edge_groups: tuple[np.ndarray, np.ndarray, np.ndarray]
    forward_tensors: tuple[np.ndarray, np.ndarray, np.ndarray]
    inverse_tensors: tuple[np.ndarray, np.ndarray, np.ndarray]
    audit: MappingProxyType

    @property
    def edge_count(self) -> int:
        return int(3 * self.degree * (self.degree + 1) ** 2)

    def high_to_lor_many(self, values: np.ndarray) -> np.ndarray:
        vectors = np.asarray(values, dtype=np.complex128)
        if (
            vectors.ndim != 2
            or vectors.shape[1] != self.edge_count
            or vectors.shape[0] < 1
            or vectors.shape[0] > LOR_BATCH_CELL_CAP
        ):
            raise ValueError("high batch has an unexpected fixed-batch shape")
        result = np.empty_like(vectors)
        block_size = int(self.degree * (self.degree + 1) ** 2)
        for axis, (columns, tensor) in enumerate(
            zip(self.high_edge_groups, self.forward_tensors, strict=True)
        ):
            offset = axis * block_size
            result[:, offset : offset + block_size] = np.einsum(
                "bh,hijk->bijk",
                vectors[:, columns],
                tensor,
                optimize=True,
            ).reshape(vectors.shape[0], block_size)
        return result

    def lor_to_high_many(self, values: np.ndarray) -> np.ndarray:
        vectors = np.asarray(values, dtype=np.complex128)
        if (
            vectors.ndim != 2
            or vectors.shape[1] != self.edge_count
            or vectors.shape[0] < 1
            or vectors.shape[0] > LOR_BATCH_CELL_CAP
        ):
            raise ValueError("LOR batch has an unexpected fixed-batch shape")
        result = np.empty_like(vectors)
        block_size = int(self.degree * (self.degree + 1) ** 2)
        for axis, (rows, tensor) in enumerate(
            zip(self.high_edge_groups, self.inverse_tensors, strict=True)
        ):
            block = vectors[:, axis * block_size : (axis + 1) * block_size]
            shape = tensor.shape[1:]
            result[:, rows] = np.einsum(
                "bijk,hijk->bh",
                block.reshape((vectors.shape[0],) + shape),
                tensor,
                optimize=True,
            )
        return result

    def lor_to_high_adjoint_many(self, values: np.ndarray) -> np.ndarray:
        """Apply the Hermitian adjoint of the retained LOR-to-high action."""

        vectors = np.asarray(values, dtype=np.complex128)
        if (
            vectors.ndim != 2
            or vectors.shape[1] != self.edge_count
            or vectors.shape[0] < 1
            or vectors.shape[0] > LOR_BATCH_CELL_CAP
        ):
            raise ValueError("high dual batch has an unexpected fixed-batch shape")
        result = np.empty_like(vectors)
        block_size = int(self.degree * (self.degree + 1) ** 2)
        for axis, (rows, tensor) in enumerate(
            zip(self.high_edge_groups, self.inverse_tensors, strict=True)
        ):
            block = vectors[:, rows]
            result[:, axis * block_size : (axis + 1) * block_size] = np.einsum(
                "bh,hijk->bijk",
                block,
                np.conjugate(tensor),
                optimize=True,
            ).reshape(vectors.shape[0], block_size)
        return result

    def high_to_lor(self, values: np.ndarray) -> np.ndarray:
        vector = np.asarray(values, dtype=np.complex128)
        if vector.shape != (self.edge_count,):
            raise ValueError("high vector has an unexpected local dimension")
        return self.high_to_lor_many(vector[np.newaxis, :])[0]

    def lor_to_high(self, values: np.ndarray) -> np.ndarray:
        vector = np.asarray(values, dtype=np.complex128)
        if vector.shape != (self.edge_count,):
            raise ValueError("LOR vector has an unexpected local dimension")
        return self.lor_to_high_many(vector[np.newaxis, :])[0]


def _reference_edge_shapes(degree: int) -> tuple[tuple[int, int, int], ...]:
    return (
        (degree, degree + 1, degree + 1),
        (degree + 1, degree, degree + 1),
        (degree + 1, degree + 1, degree),
    )


def _build_reference_tensors(
    forward_matrix: np.ndarray, inverse_matrix: np.ndarray, degree: int
) -> tuple[
    tuple[np.ndarray, np.ndarray, np.ndarray],
    tuple[np.ndarray, np.ndarray, np.ndarray],
    tuple[np.ndarray, np.ndarray, np.ndarray],
]:
    """Pack the three independent reference-axis coefficient tensors."""

    block_size = int(degree * (degree + 1) ** 2)
    groups: list[np.ndarray] = []
    forward_tensors: list[np.ndarray] = []
    inverse_tensors: list[np.ndarray] = []
    for axis, shape in enumerate(_reference_edge_shapes(degree)):
        row_start = axis * block_size
        row_end = (axis + 1) * block_size
        block = forward_matrix[row_start:row_end]
        columns = np.flatnonzero(
            np.linalg.norm(block, axis=0) > L1_TRANSFER_TOL
        ).astype(np.int32)
        if columns.size != block_size:
            raise RuntimeError("reference transfer source-axis partition is incomplete")
        for other in range(3):
            if other == axis:
                continue
            cross = forward_matrix[
                other * block_size : (other + 1) * block_size
            ][:, columns]
            if np.linalg.norm(cross) > L1_TRANSFER_TOL:
                raise RuntimeError("reference transfer couples distinct edge axes")
        groups.append(columns)
        tensor_shape = (int(columns.size),) + tuple(int(value) for value in shape)
        forward_tensor = np.ascontiguousarray(
            block[:, columns].T.reshape(tensor_shape), dtype=np.complex128
        )
        inverse_tensor = np.ascontiguousarray(
            inverse_matrix[columns, row_start:row_end].reshape(tensor_shape),
            dtype=np.complex128,
        )
        for array in (columns, forward_tensor, inverse_tensor):
            array.setflags(write=False)
        forward_tensors.append(forward_tensor)
        inverse_tensors.append(inverse_tensor)
    return tuple(groups), tuple(forward_tensors), tuple(inverse_tensors)


def _reference_factor_object_accounting(
    nodes: np.ndarray,
    groups: tuple[np.ndarray, np.ndarray, np.ndarray],
    forward_tensors: tuple[np.ndarray, np.ndarray, np.ndarray],
    inverse_tensors: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> tuple[int, int, int]:
    """Count retained packed arrays and separate metadata/numeric bytes."""

    object_count = 0
    metadata_bytes = 0
    numeric_bytes = 0

    def add_object(value: object) -> None:
        nonlocal object_count, metadata_bytes
        object_count += 1
        metadata_bytes += int(sys.getsizeof(value))

    def add_array(value: np.ndarray, *, numeric: bool) -> None:
        nonlocal object_count, metadata_bytes, numeric_bytes
        object_count += 1
        size = int(value.nbytes)
        metadata_bytes += max(0, int(sys.getsizeof(value)) - size)
        if numeric:
            numeric_bytes += size
        else:
            metadata_bytes += size

    add_array(nodes, numeric=False)
    add_object(groups)
    for group in groups:
        add_array(group, numeric=False)
    add_object(forward_tensors)
    add_object(inverse_tensors)
    for tensor in (*forward_tensors, *inverse_tensors):
        add_array(tensor, numeric=True)
    return object_count, metadata_bytes, numeric_bytes


def build_reference_factor_lor_transfer(
    degree: int,
    *,
    widths: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> ReferenceFactorLorTransfer:
    """Build an axis-packed reference-factor H/LOR action.

    A single-cell dense oracle is used only while deriving and checking the
    three reference tensors.  The returned object has no dense transfer
    arrays or per-fiber Python payload.
    """

    started = time.perf_counter()
    oracle = build_local_lor_transfer(degree, widths=widths)
    high_to_lor = oracle.high_to_lor_matrix
    lor_to_high = oracle.lor_to_high_matrix
    groups, forward_tensors, inverse_tensors = _build_reference_tensors(
        high_to_lor, lor_to_high, int(degree)
    )
    probe = np.arange(high_to_lor.shape[1], dtype=np.float64) + (0.125 + 0.25j)
    retained_nodes = np.asarray(oracle.nodes, dtype=np.float64).copy()
    retained_nodes.setflags(write=False)
    factor_lor = ReferenceFactorLorTransfer(
        degree=int(degree),
        nodes=retained_nodes,
        high_edge_groups=groups,
        forward_tensors=forward_tensors,
        inverse_tensors=inverse_tensors,
        audit=MappingProxyType(
            {
                **dict(oracle.audit),
                "schema": "task038.lor-reference-factors.v1",
                "global_transfer_matrix": False,
                "local_tensor_action": True,
                "oracle_local_dense": False,
                "production_reference_factors_only": True,
                "production_local_tensor_action": True,
                "reference_factor_kind": "axis_local_reference_tensors",
                "reference_factor_axis_count": 3,
                "reference_factor_batch_cell_cap": LOR_BATCH_CELL_CAP,
                "retained_dense_transfer_bytes": 0,
                "dense_oracle_workspace_released": True,
                "numeric_allgather": False,
            }
        ),
    )
    object_count, metadata_bytes, numeric_bytes = _reference_factor_object_accounting(
        retained_nodes, groups, forward_tensors, inverse_tensors
    )
    dense_lor = high_to_lor @ probe
    factor_lor_values = factor_lor.high_to_lor(probe)
    dense_high = lor_to_high @ dense_lor
    factor_high = factor_lor.lor_to_high(factor_lor_values)
    factor_lor_error = np.linalg.norm(factor_lor_values - dense_lor) / max(
        np.linalg.norm(dense_lor), np.finfo(float).tiny
    )
    factor_high_error = np.linalg.norm(factor_high - dense_high) / max(
        np.linalg.norm(dense_high), np.finfo(float).tiny
    )
    repeat_lor = factor_lor.high_to_lor(probe)
    repeat_high = factor_lor.lor_to_high(repeat_lor)
    repeat_error = max(
        np.linalg.norm(repeat_lor - factor_lor_values)
        / max(np.linalg.norm(factor_lor_values), np.finfo(float).tiny),
        np.linalg.norm(repeat_high - factor_high)
        / max(np.linalg.norm(factor_high), np.finfo(float).tiny),
    )
    if factor_lor_error > L1_TRANSFER_TOL or factor_high_error > L1_TRANSFER_TOL:
        raise RuntimeError(
            "reference-factor action differs from bounded oracle: "
            f"high_to_lor={factor_lor_error:.17g}, "
            f"lor_to_high={factor_high_error:.17g}, "
            f"limit={L1_TRANSFER_TOL:.17g}"
        )
    audit = dict(factor_lor.audit)
    audit["forward_tensor_shapes"] = [
        list(tensor.shape) for tensor in forward_tensors
    ]
    audit["inverse_tensor_shapes"] = [
        list(tensor.shape) for tensor in inverse_tensors
    ]
    audit["forward_tensor_numeric_bytes"] = int(
        sum(tensor.nbytes for tensor in forward_tensors)
    )
    audit["inverse_tensor_numeric_bytes"] = int(
        sum(tensor.nbytes for tensor in inverse_tensors)
    )
    audit["reference_factor_numeric_bytes"] = int(numeric_bytes)
    audit["reference_factor_index_metadata_bytes"] = int(metadata_bytes)
    audit["reference_factor_python_object_count"] = int(object_count + 1)
    audit["reference_factor_approx_retained_bytes"] = int(
        numeric_bytes + metadata_bytes
    )
    audit["reference_factor_batch_input_bytes"] = int(
        LOR_BATCH_CELL_CAP
        * factor_lor.edge_count
        * np.dtype(np.complex128).itemsize
    )
    audit["reference_factor_batch_output_bytes"] = int(
        LOR_BATCH_CELL_CAP
        * factor_lor.edge_count
        * np.dtype(np.complex128).itemsize
    )
    audit["reference_factor_batch_scratch_bytes"] = int(
        audit["reference_factor_batch_input_bytes"]
        + audit["reference_factor_batch_output_bytes"]
    )
    audit["reference_factor_retained_provenance"] = (
        "axis_tensor_numeric_plus_sys_getsizeof_array_and_container_metadata"
    )
    audit["reference_factor_build_wall_seconds"] = float(
        time.perf_counter() - started
    )
    audit["reference_factor_action_relative"] = float(
        max(factor_lor_error, factor_high_error)
    )
    audit["reference_factor_repeat_relative"] = float(repeat_error)
    audit["reference_factor_repeat_exact"] = bool(
        np.array_equal(repeat_lor, factor_lor_values)
        and np.array_equal(repeat_high, factor_high)
    )
    result = ReferenceFactorLorTransfer(
        degree=factor_lor.degree,
        nodes=factor_lor.nodes,
        high_edge_groups=factor_lor.high_edge_groups,
        forward_tensors=factor_lor.forward_tensors,
        inverse_tensors=factor_lor.inverse_tensors,
        audit=MappingProxyType(audit),
    )
    del factor_lor, oracle, high_to_lor, lor_to_high
    del dense_lor, factor_lor_values, dense_high, factor_high
    del repeat_lor, repeat_high
    return result


def build_local_lor_transfer(
    degree: int,
    *,
    widths: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> LocalLorTransfer:
    """Build the fixed GLL single-cell L1 transfer oracle."""

    degree = int(degree)
    if degree not in L1_DEGREES:
        raise ValueError(f"L1 degree must be one of {L1_DEGREES}")
    widths = tuple(float(value) for value in widths)
    if len(widths) != 3 or not all(np.isfinite(widths)) or any(
        value <= 0.0 for value in widths
    ):
        raise ValueError("cell widths must be three positive finite values")
    nodes = _gll_nodes(degree)
    high_element = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        degree,
        basix.LagrangeVariant.equispaced,
    )
    spec = AffineIsotropicMaxwellTensorSpec(
        curl_coefficient=1.0,
        mass_coefficient_by_tag={1: 1.0},
    )
    factory = AffineIsotropicMaxwellTensorFactory(high_element, spec)
    high_matrix = factory.tensor(tag=1, widths=widths)
    lor_matrix = _assemble_lor_matrix(degree, nodes, widths)
    high_to_lor = _build_edge_transfer(degree, nodes, high_element)
    lor_to_high = np.linalg.inv(high_to_lor)
    h1_transfer, high_gradient_edge = _build_scalar_transfer_and_gradient(
        degree, nodes
    )
    lor_gradient, lor_curl, face_descriptors = _build_incidence(degree)
    high_curl_face = _build_face_curl_transfer(
        degree, nodes, high_element, face_descriptors
    )
    high_gradient = lor_to_high @ high_gradient_edge
    pulled_lor = high_to_lor.conj().T @ lor_matrix @ high_to_lor
    eigenvalues = eigvalsh(high_matrix, pulled_lor)
    if not np.all(np.isfinite(eigenvalues)) or np.any(eigenvalues <= 0.0):
        raise FloatingPointError("L1 transfer has non-positive spectrum")
    spectral_condition = float(eigenvalues[-1] / eigenvalues[0])
    if spectral_condition > L1_SPECTRAL_CONDITION_LIMIT:
        raise ValueError(
            "L1 local spectral equivalence exceeds limit: "
            f"{spectral_condition:.17g} > {L1_SPECTRAL_CONDITION_LIMIT:.17g}"
        )
    source = np.arange(high_to_lor.shape[1], dtype=np.float64) + 1j
    observed_lor = high_to_lor @ source
    repeated_lor = high_to_lor @ source
    high_roundtrip = lor_to_high @ observed_lor
    repeated_high = lor_to_high @ observed_lor
    identity_high = np.linalg.norm(high_roundtrip - source) / max(
        np.linalg.norm(source), np.finfo(float).tiny
    )
    identity_lor = np.linalg.norm(
        high_to_lor @ lor_to_high @ observed_lor - observed_lor
    ) / max(np.linalg.norm(observed_lor), np.finfo(float).tiny)
    scalar_nodes = (degree + 1) ** 3
    gradient_commuting = np.linalg.norm(
        high_to_lor @ high_gradient - lor_gradient @ h1_transfer
    ) / max(np.linalg.norm(lor_gradient @ h1_transfer), 1.0)
    curl_gradient = np.linalg.norm(lor_curl @ lor_gradient) / max(
        np.linalg.norm(lor_gradient), 1.0
    )
    curl_transferred_gradient = np.linalg.norm(
        lor_curl @ high_to_lor @ high_gradient
    ) / max(np.linalg.norm(high_to_lor @ high_gradient), 1.0)
    curl_commuting = np.linalg.norm(
        lor_curl @ high_to_lor - high_curl_face
    ) / max(np.linalg.norm(high_curl_face), 1.0)
    high_matrix_hermitian = np.linalg.norm(
        high_matrix - high_matrix.conj().T
    ) / max(np.linalg.norm(high_matrix), 1.0)
    lor_matrix_hermitian = np.linalg.norm(
        lor_matrix - lor_matrix.conj().T
    ) / max(np.linalg.norm(lor_matrix), 1.0)
    audit = MappingProxyType(
        {
            "schema": "task038.lor-transfer.v1",
            "scope": "L1_single_affine_hexahedron_oracle",
            "degree": degree,
            "high_edge_dofs": int(high_to_lor.shape[1]),
            "lor_edge_dofs": int(high_to_lor.shape[0]),
            "h1_nodes": scalar_nodes,
            "gll_refinement": True,
            "high_to_lor_identity_relative": float(identity_high),
            "lor_to_high_identity_relative": float(identity_lor),
            "repeat_exact": bool(np.array_equal(observed_lor, repeated_lor)),
            "repeat_relative": float(
                np.linalg.norm(observed_lor - repeated_lor)
                / max(np.linalg.norm(observed_lor), np.finfo(float).tiny)
            ),
            "de_rham_gradient_commuting_relative": float(gradient_commuting),
            "curl_incidence_relative": float(curl_gradient),
            "curl_transferred_gradient_relative": float(
                curl_transferred_gradient
            ),
            "curl_face_commuting_relative": float(curl_commuting),
            "high_matrix_hermitian_relative": float(high_matrix_hermitian),
            "lor_matrix_hermitian_relative": float(lor_matrix_hermitian),
            "spectral_lambda_min": float(eigenvalues[0]),
            "spectral_lambda_max": float(eigenvalues[-1]),
            "spectral_condition": spectral_condition,
            "global_transfer_matrix": False,
            "local_tensor_action": False,
            "oracle_local_dense": True,
            "production_reference_factors_only": False,
            "production_local_tensor_action": False,
            "owner_local_maps": False,
            "numeric_allgather": False,
            "global_direct_coarse": False,
            "global_aij": False,
            "local_dense_oracle_bytes": int(
                high_to_lor.nbytes
                + lor_to_high.nbytes
                + high_matrix.nbytes
                + lor_matrix.nbytes
            ),
            "local_dense_oracle_only": True,
        }
    )
    if identity_high > L1_TRANSFER_TOL or identity_lor > L1_TRANSFER_TOL:
        raise RuntimeError(
            "L1 transfer identity exceeds limit: "
            f"high={identity_high:.17g}, lor={identity_lor:.17g}, "
            f"limit={L1_TRANSFER_TOL:.17g}"
        )
    if (
        gradient_commuting > L1_TRANSFER_TOL
        or curl_gradient > L1_TRANSFER_TOL
        or curl_commuting > L1_TRANSFER_TOL
    ):
        raise RuntimeError(
            "L1 de Rham identity exceeds limit: "
            f"gradient={gradient_commuting:.17g}, "
            f"curl_incidence={curl_gradient:.17g}, "
            f"curl_face={curl_commuting:.17g}, "
            f"limit={L1_TRANSFER_TOL:.17g}"
        )
    for array in (
        high_to_lor,
        lor_to_high,
        high_matrix,
        lor_matrix,
        h1_transfer,
        high_gradient,
        high_curl_face,
        lor_gradient,
        lor_curl,
    ):
        array.setflags(write=False)
    return LocalLorTransfer(
        degree=degree,
        widths=widths,
        nodes=nodes,
        high_to_lor_matrix=high_to_lor,
        lor_to_high_matrix=lor_to_high,
        high_matrix=high_matrix,
        lor_matrix=lor_matrix,
        h1_transfer=h1_transfer,
        high_gradient_edge=high_gradient,
        high_curl_face=high_curl_face,
        lor_gradient=lor_gradient,
        lor_curl_incidence=lor_curl,
        audit=audit,
    )


__all__ = [
    "L1_DEGREES",
    "L1_REPEAT_TOL",
    "L1_SPECTRAL_CONDITION_LIMIT",
    "L1_TRANSFER_TOL",
    "LocalLorTransfer",
    "ReferenceFactorLorTransfer",
    "build_reference_factor_lor_transfer",
    "build_local_lor_transfer",
]
