"""One fixed scalar/vector H1 V-cycle on a paired LOR hierarchy."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from types import MappingProxyType
from typing import Mapping

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from .static_lor_h1_hierarchy import LORH1Hierarchy


_JACOBI_OMEGA = 0.5
_JACOBI_DIAGONAL_RELATIVE_TOLERANCE = 1.0e-14
_SCALAR_GAUGE_TOLERANCE = 1.0e-12


def _sparse_payload_bytes(matrix: sp.spmatrix) -> int:
    return int(
        matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes
    )


def _inverse_diagonal(
    matrix: sp.csr_matrix,
    label: str,
) -> tuple[np.ndarray, float, float]:
    diagonal = np.asarray(matrix.diagonal(), dtype=np.complex128)
    if not np.all(np.isfinite(matrix.data)) or not np.all(np.isfinite(diagonal)):
        raise ValueError(f"{label} is not finite")
    scale = max(float(np.max(np.abs(diagonal))), np.finfo(float).tiny)
    threshold = _JACOBI_DIAGONAL_RELATIVE_TOLERANCE * scale
    if np.any(np.abs(diagonal) <= threshold):
        raise ValueError(f"{label} has a numerically zero diagonal")
    inverse = np.ascontiguousarray(1.0 / diagonal, dtype=np.complex128)
    inverse.setflags(write=False)
    return inverse, scale, threshold


def _nullspace_relative(operator: sp.csr_matrix) -> float:
    ones = np.ones(operator.shape[0], dtype=np.complex128)
    denominator = max(float(np.linalg.norm(operator.data)), np.finfo(float).tiny)
    return float(np.linalg.norm(operator @ ones) / denominator)


def _factor_inventory(factor: spla.SuperLU, rows: int) -> dict[str, int]:
    lower = factor.L
    upper = factor.U
    payload = (
        _sparse_payload_bytes(lower)
        + _sparse_payload_bytes(upper)
        + np.asarray(factor.perm_r).nbytes
        + np.asarray(factor.perm_c).nbytes
    )
    return {
        "rows": int(rows),
        "L_nnz": int(lower.nnz),
        "U_nnz": int(upper.nnz),
        "factor_payload_lower_bound_bytes": int(payload),
    }


def _solve_coarsest(
    factor: spla.SuperLU,
    rhs: np.ndarray,
    scalar_gauge: bool,
) -> np.ndarray:
    if not scalar_gauge:
        return np.asarray(factor.solve(rhs), dtype=np.complex128)
    solution = np.zeros_like(rhs, dtype=np.complex128)
    solution[1:] = factor.solve(rhs[1:])
    return solution


def _vcycle(
    operators: tuple[sp.csr_matrix, ...],
    prolongations: tuple[sp.csr_matrix, ...],
    inverse_diagonals: tuple[np.ndarray, ...],
    factor: spla.SuperLU,
    rhs: np.ndarray,
    level: int,
    scalar_gauge: bool,
) -> np.ndarray:
    if level == len(operators) - 1:
        return _solve_coarsest(factor, rhs, scalar_gauge)
    operator = operators[level]
    correction = _JACOBI_OMEGA * inverse_diagonals[level] * rhs
    residual = rhs - operator @ correction
    prolongation = prolongations[level]
    coarse_rhs = prolongation.conjugate().transpose() @ residual
    correction += prolongation @ _vcycle(
        operators,
        prolongations,
        inverse_diagonals,
        factor,
        np.asarray(coarse_rhs, dtype=np.complex128),
        level + 1,
        scalar_gauge,
    )
    residual = rhs - operator @ correction
    correction += _JACOBI_OMEGA * inverse_diagonals[level] * residual
    return correction


@dataclass(frozen=True)
class LORH1VCycle:
    """One fixed scalar or vector H1 V-cycle with coarsest-only factors."""

    hierarchy: LORH1Hierarchy
    _scalar_inverse_diagonals: tuple[np.ndarray, ...]
    _vector_inverse_diagonals: tuple[np.ndarray, ...]
    _scalar_factor: spla.SuperLU
    _vector_factor: spla.SuperLU
    _scalar_gauge: bool
    audit: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "audit", MappingProxyType(dict(self.audit)))

    def apply_scalar(self, rhs: np.ndarray) -> np.ndarray:
        values = np.asarray(rhs, dtype=np.complex128)
        if values.shape != (self.hierarchy.scalar_operators[0].shape[0],):
            raise ValueError("scalar V-cycle RHS has the wrong size")
        return _vcycle(
            self.hierarchy.scalar_operators,
            self.hierarchy.scalar_prolongations,
            self._scalar_inverse_diagonals,
            self._scalar_factor,
            values,
            0,
            self._scalar_gauge,
        )

    def apply_vector(self, rhs: np.ndarray) -> np.ndarray:
        values = np.asarray(rhs, dtype=np.complex128)
        if values.shape != (self.hierarchy.vector_operators[0].shape[0],):
            raise ValueError("vector V-cycle RHS has the wrong size")
        return _vcycle(
            self.hierarchy.vector_operators,
            self.hierarchy.vector_prolongations,
            self._vector_inverse_diagonals,
            self._vector_factor,
            values,
            0,
            False,
        )


def build_lor_h1_vcycle(hierarchy: LORH1Hierarchy) -> LORH1VCycle:
    """Build the fixed one-cycle scalar/vector action."""

    started = perf_counter()
    scalar_operators = hierarchy.scalar_operators
    vector_operators = hierarchy.vector_operators
    scalar_inverse_diagonals = []
    vector_inverse_diagonals = []
    scalar_scales = []
    vector_scales = []
    scalar_thresholds = []
    vector_thresholds = []
    for level, (scalar, vector) in enumerate(
        zip(scalar_operators[:-1], vector_operators[:-1], strict=True)
    ):
        scalar_inverse, scalar_scale, scalar_threshold = _inverse_diagonal(
            scalar,
            f"scalar hierarchy level {level}",
        )
        vector_inverse, vector_scale, vector_threshold = _inverse_diagonal(
            vector,
            f"vector hierarchy level {level}",
        )
        scalar_inverse_diagonals.append(scalar_inverse)
        vector_inverse_diagonals.append(vector_inverse)
        scalar_scales.append(scalar_scale)
        vector_scales.append(vector_scale)
        scalar_thresholds.append(scalar_threshold)
        vector_thresholds.append(vector_threshold)

    scalar_nullspace_relative = _nullspace_relative(scalar_operators[0])
    scalar_gauge = scalar_nullspace_relative <= _SCALAR_GAUGE_TOLERANCE
    scalar_coarse = scalar_operators[-1]
    if scalar_gauge:
        scalar_factor = spla.splu(scalar_coarse[1:, 1:].tocsc())
        scalar_factor_rows = scalar_coarse.shape[0] - 1
    else:
        scalar_factor = spla.splu(scalar_coarse.tocsc())
        scalar_factor_rows = scalar_coarse.shape[0]
    vector_coarse = vector_operators[-1]
    vector_factor = spla.splu(vector_coarse.tocsc())
    scalar_inventory = _factor_inventory(scalar_factor, scalar_factor_rows)
    vector_inventory = _factor_inventory(vector_factor, vector_coarse.shape[0])
    audit = {
        "level_count": len(scalar_operators),
        "level_rows": tuple(
            (int(scalar.shape[0]), int(vector.shape[0]))
            for scalar, vector in zip(
                scalar_operators,
                vector_operators,
                strict=True,
            )
        ),
        "pre_steps": 1,
        "post_steps": 1,
        "omega": _JACOBI_OMEGA,
        "jacobi_diagonal_relative_tolerance": (
            _JACOBI_DIAGONAL_RELATIVE_TOLERANCE
        ),
        "jacobi_diagonal_scales": (
            tuple(scalar_scales),
            tuple(vector_scales),
        ),
        "jacobi_diagonal_thresholds": (
            tuple(scalar_thresholds),
            tuple(vector_thresholds),
        ),
        "scalar_nullspace_relative": scalar_nullspace_relative,
        "scalar_constant_nullspace": scalar_gauge,
        "scalar_gauge_mode": "coarsest_index_zero_fixed" if scalar_gauge else "none",
        "scalar_factor_inventory": scalar_inventory,
        "vector_factor_inventory": vector_inventory,
        "factor_count": 2,
        "coarsest_factor_count": 2,
        "fine_intermediate_factor_count": 0,
        "coarsest_only": True,
        "large_factor": False,
        "global_dense": False,
        "restriction_retained": False,
        "hierarchy_payload_reference_bytes": int(
            hierarchy.audit["retained_csr_payload_bytes"]
        ),
        "inverse_diagonal_bytes": int(
            sum(inverse.nbytes for inverse in scalar_inverse_diagonals)
            + sum(inverse.nbytes for inverse in vector_inverse_diagonals)
        ),
        "build_seconds": float(perf_counter() - started),
    }
    return LORH1VCycle(
        hierarchy,
        tuple(scalar_inverse_diagonals),
        tuple(vector_inverse_diagonals),
        scalar_factor,
        vector_factor,
        scalar_gauge,
        audit,
    )


__all__ = ("LORH1VCycle", "build_lor_h1_vcycle")
