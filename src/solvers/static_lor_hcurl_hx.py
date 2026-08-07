"""Fixed finest-level H(curl) auxiliary correction around the shifted LOR proxy.

This module implements one stateless linear action only:
edge pre-smooth, scalar H1 correction, vector H1 correction, and edge
post-smooth.  It has no hierarchy, coarsest solve, factor, or V-cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from types import MappingProxyType

import numpy as np
import scipy.sparse as sp

from .static_lor_hcurl_auxiliary import LORHcurlAuxiliarySpace
from .static_lor_hcurl_proxy import LORShiftedProxy


_JACOBI_OMEGA = 0.5
_JACOBI_DIAGONAL_TOLERANCE = 1.0e-14


def _readonly_csr(values: sp.spmatrix) -> sp.csr_matrix:
    matrix = sp.csr_matrix(values, dtype=np.complex128, copy=True)
    matrix.sum_duplicates()
    matrix.sort_indices()
    matrix.eliminate_zeros()
    for array in (matrix.data, matrix.indices, matrix.indptr):
        array.setflags(write=False)
    return matrix


def _inverse_diagonal(
    matrix: sp.csr_matrix,
    label: str,
) -> tuple[np.ndarray, float, float]:
    diagonal = np.asarray(matrix.diagonal(), dtype=np.complex128)
    if not np.all(np.isfinite(diagonal)):
        raise ValueError(f"{label} diagonal is not finite")
    scale = max(float(np.max(np.abs(diagonal))), np.finfo(float).tiny)
    threshold = _JACOBI_DIAGONAL_TOLERANCE * scale
    if np.any(np.abs(diagonal) <= threshold):
        raise ValueError(f"{label} has a numerically zero diagonal")
    inverse = np.ascontiguousarray(1.0 / diagonal, dtype=np.complex128)
    inverse.setflags(write=False)
    return inverse, scale, threshold


def _csr_payload_bytes(matrix: sp.csr_matrix) -> int:
    return int(matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes)


@dataclass(frozen=True)
class LORHcurlHX:
    """Read-only fixed finest-level scalar/vector auxiliary action."""

    _a: sp.csr_matrix
    _auxiliary: LORHcurlAuxiliarySpace
    _scalar_operator: sp.csr_matrix
    _vector_operator: sp.csr_matrix
    _edge_inverse_diagonal: np.ndarray
    _scalar_inverse_diagonal: np.ndarray
    _vector_inverse_diagonal: np.ndarray
    audit: dict[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "audit",
            MappingProxyType(dict(self.audit)),
        )

    @property
    def matrix(self) -> sp.csr_matrix:
        return self._a

    @property
    def scalar_operator(self) -> sp.csr_matrix:
        return self._scalar_operator

    @property
    def vector_operator(self) -> sp.csr_matrix:
        return self._vector_operator

    def _jacobi(
        self,
        matrix: sp.csr_matrix,
        inverse_diagonal: np.ndarray,
        rhs: np.ndarray,
        steps: int,
    ) -> np.ndarray:
        correction = np.zeros_like(rhs, dtype=np.complex128)
        for _ in range(steps):
            correction += _JACOBI_OMEGA * inverse_diagonal * (
                rhs - matrix @ correction
            )
        return correction

    def apply(self, rhs: np.ndarray) -> np.ndarray:
        values = np.asarray(rhs, dtype=np.complex128)
        if values.shape != (self._a.shape[0],):
            raise ValueError("HX RHS has the wrong edge count")
        auxiliary = self._auxiliary
        solution = np.zeros_like(values, dtype=np.complex128)

        solution += _JACOBI_OMEGA * self._edge_inverse_diagonal * values
        residual = values - self._a @ solution

        scalar_rhs = auxiliary.apply_gradient_adjoint(residual)
        scalar_correction = self._jacobi(
            self._scalar_operator,
            self._scalar_inverse_diagonal,
            scalar_rhs,
            2,
        )
        solution += auxiliary.apply_gradient(scalar_correction)
        residual = values - self._a @ solution

        vector_rhs = auxiliary.apply_vector_h1_adjoint(residual)
        vector_correction = self._jacobi(
            self._vector_operator,
            self._vector_inverse_diagonal,
            vector_rhs,
            2,
        )
        solution += auxiliary.apply_vector_h1(vector_correction)
        residual = values - self._a @ solution
        solution += _JACOBI_OMEGA * self._edge_inverse_diagonal * residual
        return solution


def build_lor_hcurl_hx(
    proxy: LORShiftedProxy,
    auxiliary: LORHcurlAuxiliarySpace,
) -> LORHcurlHX:
    """Build the fixed finest-level scalar/vector auxiliary correction."""

    started = perf_counter()
    matrix = proxy.matrix
    gradient = auxiliary.gradient_matrix
    vector_interpolation = auxiliary.vector_interpolation_matrix
    if (
        gradient.shape[0] != matrix.shape[0]
        or vector_interpolation.shape[0] != matrix.shape[0]
    ):
        raise ValueError("auxiliary edge maps do not match the LOR proxy")
    gradient_adjoint = gradient.conjugate().transpose()
    vector_interpolation_adjoint = vector_interpolation.conjugate().transpose()
    scalar_operator = _readonly_csr(gradient_adjoint @ matrix @ gradient)
    vector_operator = _readonly_csr(
        vector_interpolation_adjoint @ matrix @ vector_interpolation
    )
    del gradient_adjoint, vector_interpolation_adjoint
    edge_inverse_diagonal, edge_scale, edge_threshold = _inverse_diagonal(
        matrix,
        "edge proxy",
    )
    scalar_inverse_diagonal, scalar_scale, scalar_threshold = _inverse_diagonal(
        scalar_operator,
        "scalar auxiliary operator",
    )
    vector_inverse_diagonal, vector_scale, vector_threshold = _inverse_diagonal(
        vector_operator,
        "vector auxiliary operator",
    )
    audit = {
        "definition": "edge pre -> scalar H1 -> vector H1 -> edge post",
        "edge_rows": int(matrix.shape[0]),
        "scalar_rows": int(scalar_operator.shape[0]),
        "vector_rows": int(vector_operator.shape[0]),
        "edge_nnz": int(matrix.nnz),
        "scalar_nnz": int(scalar_operator.nnz),
        "vector_nnz": int(vector_operator.nnz),
        "edge_csr_payload_bytes": _csr_payload_bytes(matrix),
        "scalar_csr_payload_bytes": _csr_payload_bytes(scalar_operator),
        "vector_csr_payload_bytes": _csr_payload_bytes(vector_operator),
        "inverse_diagonal_bytes": int(
            edge_inverse_diagonal.nbytes
            + scalar_inverse_diagonal.nbytes
            + vector_inverse_diagonal.nbytes
        ),
        "jacobi_diagonal_relative_tolerance": _JACOBI_DIAGONAL_TOLERANCE,
        "jacobi_diagonal_scales": [edge_scale, scalar_scale, vector_scale],
        "jacobi_diagonal_thresholds": [
            edge_threshold,
            scalar_threshold,
            vector_threshold,
        ],
        "edge_pre_steps": 1,
        "scalar_steps": 2,
        "vector_steps": 2,
        "edge_post_steps": 1,
        "omega": _JACOBI_OMEGA,
        "order": "edge_pre_scalar_H1_vector_H1_edge_post",
        "factor_count": 0,
        "large_factor": False,
        "global_dense": False,
        "literal_p6_galerkin": False,
        "shifted_proxy": True,
        "build_seconds": float(perf_counter() - started),
    }
    return LORHcurlHX(
        matrix,
        auxiliary,
        scalar_operator,
        vector_operator,
        edge_inverse_diagonal,
        scalar_inverse_diagonal,
        vector_inverse_diagonal,
        audit,
    )


__all__ = ("LORHcurlHX", "build_lor_hcurl_hx")
