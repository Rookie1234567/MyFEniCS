"""Paired algebraic scalar/vector H1 hierarchy; no factors or V-cycle actions."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

import numpy as np
import scipy.sparse as sp


_COARSEST_MAX_VERTICES = 32
_JACOBI_OMEGA = 0.5
_JACOBI_DIAGONAL_RELATIVE_TOLERANCE = 1.0e-14


def _readonly_csr(values: sp.spmatrix) -> sp.csr_matrix:
    matrix = sp.csr_matrix(values, dtype=np.complex128, copy=True)
    matrix.sum_duplicates()
    matrix.sort_indices()
    matrix.eliminate_zeros()
    for array in (matrix.data, matrix.indices, matrix.indptr):
        array.setflags(write=False)
    return matrix


def _csr_payload_bytes(matrix: sp.csr_matrix) -> int:
    return int(matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes)


def _matrix_metrics(matrix: sp.csr_matrix) -> tuple[int, int, int]:
    return int(matrix.shape[0]), int(matrix.nnz), _csr_payload_bytes(matrix)


def _inverse_diagonal(matrix: sp.csr_matrix, label: str) -> tuple[np.ndarray, float, float]:
    diagonal = np.asarray(matrix.diagonal(), dtype=np.complex128)
    if not np.all(np.isfinite(matrix.data)) or not np.all(np.isfinite(diagonal)):
        raise ValueError(f"{label} is not finite")
    scale = max(float(np.max(np.abs(diagonal))), np.finfo(float).tiny)
    threshold = _JACOBI_DIAGONAL_RELATIVE_TOLERANCE * scale
    if np.any(np.abs(diagonal) <= threshold):
        raise ValueError(f"{label} has a numerically zero diagonal")
    return 1.0 / diagonal, scale, threshold


def _pairwise_heavy_edge_aggregates(matrix: sp.csr_matrix) -> tuple[np.ndarray, int]:
    aggregate_of = np.full(matrix.shape[0], -1, dtype=np.int64)
    aggregate_count = 0
    for row in range(matrix.shape[0]):
        if aggregate_of[row] >= 0:
            continue
        start = int(matrix.indptr[row])
        end = int(matrix.indptr[row + 1])
        best_column = -1
        best_weight = -1.0
        for column_value, value in zip(
            matrix.indices[start:end],
            matrix.data[start:end],
            strict=True,
        ):
            column = int(column_value)
            weight = float(abs(value))
            if (
                column != row
                and aggregate_of[column] < 0
                and weight > 0.0
                and (
                    weight > best_weight
                    or (weight == best_weight and column < best_column)
                )
            ):
                best_column = column
                best_weight = weight
        aggregate_of[row] = aggregate_count
        if best_column >= 0:
            aggregate_of[best_column] = aggregate_count
        aggregate_count += 1
    return aggregate_of, aggregate_count


def _tentative_prolongation(
    aggregate_of: np.ndarray, aggregate_count: int, component_count: int
) -> sp.csr_matrix:
    fine_vertices = aggregate_of.size
    fine_rows = component_count * fine_vertices
    rows = np.arange(fine_rows, dtype=np.int64)
    if component_count == 1:
        columns = aggregate_of.copy()
    else:
        vertices = rows // component_count
        components = rows % component_count
        columns = component_count * aggregate_of[vertices] + components
    values = np.ones(fine_rows, dtype=np.complex128)
    return sp.csr_matrix(
        (values, (rows, columns)),
        shape=(fine_rows, component_count * aggregate_count),
        dtype=np.complex128,
    )


def _smoothed_prolongation(
    operator: sp.csr_matrix,
    aggregate_of: np.ndarray,
    aggregate_count: int,
    component_count: int,
    label: str,
) -> tuple[sp.csr_matrix, float, float]:
    inverse, scale, threshold = _inverse_diagonal(operator, label)
    tentative = _tentative_prolongation(
        aggregate_of,
        aggregate_count,
        component_count,
    )
    applied = (operator @ tentative).tocsr()
    scaled = sp.diags(inverse, format="csr") @ applied
    prolongation = _readonly_csr(tentative - _JACOBI_OMEGA * scaled)
    return prolongation, scale, threshold


def _galerkin(operator: sp.csr_matrix, prolongation: sp.csr_matrix) -> sp.csr_matrix:
    restriction = prolongation.conjugate().transpose()
    return _readonly_csr(restriction @ operator @ prolongation)


@dataclass(frozen=True)
class LORH1Hierarchy:
    """Read-only paired scalar/vector hierarchy with transient restrictions."""

    scalar_operators: tuple[sp.csr_matrix, ...]
    vector_operators: tuple[sp.csr_matrix, ...]
    scalar_prolongations: tuple[sp.csr_matrix, ...]
    vector_prolongations: tuple[sp.csr_matrix, ...]
    audit: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "audit", MappingProxyType(dict(self.audit)))

    def apply_scalar_prolongation(
        self,
        level: int,
        coarse_values: np.ndarray,
    ) -> np.ndarray:
        prolongation = self.scalar_prolongations[level]
        values = np.asarray(coarse_values, dtype=np.complex128)
        if values.shape != (prolongation.shape[1],):
            raise ValueError("scalar coarse values have the wrong size")
        return np.asarray(prolongation @ values)

    def apply_scalar_restriction(
        self,
        level: int,
        fine_values: np.ndarray,
    ) -> np.ndarray:
        prolongation = self.scalar_prolongations[level]
        values = np.asarray(fine_values, dtype=np.complex128)
        if values.shape != (prolongation.shape[0],):
            raise ValueError("scalar fine values have the wrong size")
        return np.asarray(prolongation.conjugate().transpose() @ values)

    def apply_vector_prolongation(
        self,
        level: int,
        coarse_values: np.ndarray,
    ) -> np.ndarray:
        prolongation = self.vector_prolongations[level]
        values = np.asarray(coarse_values, dtype=np.complex128)
        if values.shape != (prolongation.shape[1],):
            raise ValueError("vector coarse values have the wrong size")
        return np.asarray(prolongation @ values)

    def apply_vector_restriction(
        self,
        level: int,
        fine_values: np.ndarray,
    ) -> np.ndarray:
        prolongation = self.vector_prolongations[level]
        values = np.asarray(fine_values, dtype=np.complex128)
        if values.shape != (prolongation.shape[0],):
            raise ValueError("vector fine values have the wrong size")
        return np.asarray(prolongation.conjugate().transpose() @ values)


def build_lor_h1_hierarchy(
    scalar_operator: sp.csr_matrix, vector_operator: sp.csr_matrix
) -> LORH1Hierarchy:
    """Build the fixed paired hierarchy from D2a scalar/vector operators."""

    if not sp.isspmatrix_csr(scalar_operator) or not sp.isspmatrix_csr(
        vector_operator
    ):
        raise TypeError("D2a operators must be CSR matrices")
    if (
        scalar_operator.shape[0] != scalar_operator.shape[1]
        or vector_operator.shape[0] != vector_operator.shape[1]
        or vector_operator.shape[0] != 3 * scalar_operator.shape[0]
    ):
        raise ValueError("scalar/vector operator dimensions are incompatible")

    scalar_operators = [scalar_operator]
    vector_operators = [vector_operator]
    scalar_prolongations = []
    vector_prolongations = []
    aggregate_counts = []
    diagonal_scales = []
    diagonal_thresholds = []

    while scalar_operators[-1].shape[0] > _COARSEST_MAX_VERTICES:
        current_scalar = scalar_operators[-1]
        current_vector = vector_operators[-1]
        aggregate_of, aggregate_count = _pairwise_heavy_edge_aggregates(
            current_scalar
        )
        if aggregate_count >= current_scalar.shape[0]:
            raise RuntimeError(
                "pairwise heavy-edge aggregation did not reduce scalar rows"
            )
        scalar_prolongation, scalar_scale, scalar_threshold = (
            _smoothed_prolongation(
                current_scalar,
                aggregate_of,
                aggregate_count,
                1,
                "scalar hierarchy operator",
            )
        )
        vector_prolongation, vector_scale, vector_threshold = (
            _smoothed_prolongation(
                current_vector,
                aggregate_of,
                aggregate_count,
                3,
                "vector hierarchy operator",
            )
        )
        scalar_next = _galerkin(current_scalar, scalar_prolongation)
        vector_next = _galerkin(current_vector, vector_prolongation)
        scalar_prolongations.append(scalar_prolongation)
        vector_prolongations.append(vector_prolongation)
        scalar_operators.append(scalar_next)
        vector_operators.append(vector_next)
        aggregate_counts.append(aggregate_count)
        diagonal_scales.append((scalar_scale, vector_scale))
        diagonal_thresholds.append((scalar_threshold, vector_threshold))

    operator_metrics = tuple(
        (_matrix_metrics(scalar), _matrix_metrics(vector))
        for scalar, vector in zip(scalar_operators, vector_operators, strict=True)
    )
    prolongation_metrics = tuple(
        (_matrix_metrics(scalar), _matrix_metrics(vector))
        for scalar, vector in zip(
            scalar_prolongations,
            vector_prolongations,
            strict=True,
        )
    )
    retained_payload = sum(
        _csr_payload_bytes(matrix)
        for matrix in (
            *scalar_operators,
            *vector_operators,
            *scalar_prolongations,
            *vector_prolongations,
        )
    )
    audit = {
        "level_count": len(scalar_operators),
        "level_operator_rows_nnz_payload": operator_metrics,
        "level_prolongation_rows_nnz_payload": prolongation_metrics,
        "aggregate_counts": tuple(aggregate_counts),
        "coarsest_max_vertices": _COARSEST_MAX_VERTICES,
        "coarsest_scalar_rows": int(scalar_operators[-1].shape[0]),
        "jacobi_omega": _JACOBI_OMEGA,
        "jacobi_diagonal_relative_tolerance": (
            _JACOBI_DIAGONAL_RELATIVE_TOLERANCE
        ),
        "jacobi_diagonal_scales": tuple(diagonal_scales),
        "jacobi_diagonal_thresholds": tuple(diagonal_thresholds),
        "aggregation_method": "deterministic_pairwise_heavy_edge",
        "factor_count": 0,
        "restriction_retained": False,
        "global_dense": False,
        "large_factor": False,
        "shared_vertex_aggregates": True,
        "component_order": "vertex_interleaved_xyz",
        "retained_csr_payload_bytes": int(retained_payload),
    }
    return LORH1Hierarchy(
        tuple(scalar_operators),
        tuple(vector_operators),
        tuple(scalar_prolongations),
        tuple(vector_prolongations),
        audit,
    )


__all__ = ("LORH1Hierarchy", "build_lor_h1_hierarchy")
