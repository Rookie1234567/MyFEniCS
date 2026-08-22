"""Prospective V2 certification arithmetic for one local B0 factor.

This module contains only frozen scalar arithmetic and a small certificate
summary.  It does not build a matrix, choose a class, or alter the production
triangular solve.  The independent benchmark checker deliberately repeats the
arithmetic instead of importing this module.
"""

from __future__ import annotations

import hashlib
from typing import Any, Callable, Iterable, Mapping

import numpy as np


EPS64 = float(np.finfo(np.float64).eps)
MAX_LOCAL_ROWS = 882
MAX_CLASSES = 32
FACTOR_BYTES_LIMIT = 6_230_448
TOTAL_FACTOR_BYTES_LIMIT = 199_374_336
ORDINARY_RESIDUAL_LIMIT = 1.0e-10
KAPPA_LIMIT = 1.0e8
CERTIFICATION_SCHEMA = "task038.local-factor-certification-v2"


def gamma_n(rows: int) -> float:
    """Return the frozen ``n*eps/(1-n*eps)`` bound."""

    n = int(rows)
    if n < 1 or n > MAX_LOCAL_ROWS:
        raise ValueError(f"local rows must be in [1,{MAX_LOCAL_ROWS}], got {n}")
    return n * EPS64 / (1.0 - n * EPS64)


def gate_limits(rows: int) -> dict[str, float]:
    """Return all V2 numeric limits for one row count."""

    gamma = gamma_n(rows)
    return {
        "hermitian_defect": max(1.0e-13, 8.0 * gamma),
        "factorization_relative_error": max(1.0e-13, 16.0 * gamma),
        "normalized_backward_error": max(1.0e-14, 16.0 * gamma),
        "ordinary_relative_residual": ORDINARY_RESIDUAL_LIMIT,
        "kappa2": KAPPA_LIMIT,
        "factor_bytes": FACTOR_BYTES_LIMIT,
    }


def fixed_rhs(rows: int) -> np.ndarray:
    """Return the source-independent V6 fixed RHS."""

    n = int(rows)
    if n < 1 or n > MAX_LOCAL_ROWS:
        raise ValueError(f"local rows must be in [1,{MAX_LOCAL_ROWS}], got {n}")
    return np.arange(n, dtype=np.float64) + (0.125 + 0.25j)


def relative(values: np.ndarray, reference: np.ndarray) -> float:
    return float(np.linalg.norm(np.asarray(values))) / max(
        float(np.linalg.norm(np.asarray(reference))), 1.0e-300
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def gate_passes(value: float, limit: float) -> bool:
    """Apply one finite, inclusive scalar Gate."""

    return bool(np.isfinite(value) and float(value) <= float(limit))


def _packed_sha256(packed: np.ndarray) -> str:
    return sha256_bytes(np.ascontiguousarray(packed).view(np.uint8).tobytes())


def certify_dense_factor(
    matrix: np.ndarray,
    solve: Callable[[np.ndarray], np.ndarray],
    *,
    packed: np.ndarray,
    lower: np.ndarray,
    rhs: np.ndarray | None = None,
) -> dict[str, Any]:
    """Measure one already-created packed Cholesky factor.

    ``solve`` is called exactly twice.  The caller supplies the production
    factor's packed lower triangle and reconstruction so this helper does not
    silently replace the production path.  No refinement or fallback is
    present here.
    """

    array = np.ascontiguousarray(np.asarray(matrix, dtype=np.complex128))
    if array.ndim != 2 or array.shape[0] != array.shape[1]:
        raise ValueError("local B0 must be square")
    rows = int(array.shape[0])
    limits = gate_limits(rows)
    vector = (
        fixed_rhs(rows)
        if rhs is None
        else np.ascontiguousarray(np.asarray(rhs, dtype=np.complex128))
    )
    if vector.shape != (rows,) or not np.array_equal(vector, fixed_rhs(rows)):
        raise ValueError("local certification RHS is not the frozen fixed RHS")
    packed_array = np.ascontiguousarray(np.asarray(packed, dtype=np.complex128))
    lower_array = np.ascontiguousarray(np.asarray(lower, dtype=np.complex128))
    if lower_array.shape != array.shape:
        raise ValueError("reconstructed lower factor shape does not match B0")
    if packed_array.ndim != 1 or packed_array.size != rows * (rows + 1) // 2:
        raise ValueError("packed lower factor shape is invalid")
    if not (
        np.all(np.isfinite(array))
        and np.all(np.isfinite(vector))
        and np.all(np.isfinite(packed_array))
        and np.all(np.isfinite(lower_array))
    ):
        raise ValueError("local certification data is non-finite")

    indices = np.tril_indices(rows)
    repacked = np.ascontiguousarray(lower_array[indices], dtype=np.complex128)
    hermitian = 0.5 * (array + array.conj().T)
    eigenvalues = np.linalg.eigvalsh(hermitian)
    lambda_min = float(eigenvalues[0])
    lambda_max = float(eigenvalues[-1])
    kappa2 = (
        float(lambda_max / lambda_min) if lambda_min > 0.0 else float("inf")
    )
    solution = np.ascontiguousarray(
        np.asarray(solve(vector), dtype=np.complex128)
    )
    repeated = np.ascontiguousarray(
        np.asarray(solve(vector), dtype=np.complex128)
    )
    residual = array @ solution - vector
    matrix_norm = float(np.linalg.norm(array, ord=2))
    backward_denominator = matrix_norm * float(np.linalg.norm(solution)) + float(
        np.linalg.norm(vector)
    )
    values = {
        "schema": CERTIFICATION_SCHEMA,
        "rows": rows,
        "finite": True,
        "rhs_identity": True,
        "hermitian_defect": relative(array - array.conj().T, array),
        "lambda_min": lambda_min,
        "lambda_max": lambda_max,
        "kappa2": kappa2,
        "factorization_relative_error": relative(
            lower_array @ lower_array.conj().T - array, array
        ),
        "packed_roundtrip_exact": bool(np.array_equal(packed_array, repacked)),
        "packed_roundtrip_relative": relative(repacked - packed_array, packed_array),
        "packed_factor_sha256": _packed_sha256(packed_array),
        "repacked_factor_sha256": _packed_sha256(repacked),
        "packed_bytes": int(packed_array.nbytes),
        "triangular_repeat_exact": bool(np.array_equal(solution, repeated)),
        "triangular_repeat_relative": relative(repeated - solution, solution),
        "ordinary_relative_residual": relative(residual, vector),
        "normalized_backward_error": float(np.linalg.norm(residual)) / max(
            backward_denominator, 1.0e-300
        ),
        "solution_finite": bool(np.all(np.isfinite(solution))),
        "matrix_norm_2": matrix_norm,
        "rhs_norm_2": float(np.linalg.norm(vector)),
        "thresholds": limits,
    }
    values["gates"] = {
        "finite": bool(values["finite"] and values["solution_finite"]),
        "rows": 1 <= rows <= MAX_LOCAL_ROWS,
        "hermitian": gate_passes(values["hermitian_defect"], limits["hermitian_defect"]),
        "positive": lambda_min > 0.0,
        "kappa2": gate_passes(kappa2, limits["kappa2"]),
        "factorization": gate_passes(
            values["factorization_relative_error"],
            limits["factorization_relative_error"],
        ),
        "packed_identity": bool(
            values["packed_roundtrip_exact"]
            and values["packed_factor_sha256"] == values["repacked_factor_sha256"]
        ),
        "triangular_repeat": values["triangular_repeat_exact"],
        "backward": gate_passes(
            values["normalized_backward_error"],
            limits["normalized_backward_error"],
        ),
        "ordinary_residual": gate_passes(
            values["ordinary_relative_residual"],
            limits["ordinary_relative_residual"],
        ),
        "factor_bytes": gate_passes(values["packed_bytes"], limits["factor_bytes"]),
    }
    values["gate_pass"] = bool(all(values["gates"].values()))
    return values


def summarize_certificates(
    certificates: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Aggregate all processed classes without early stopping on a scalar miss."""

    rows = tuple(certificates)
    class_count = len(rows)
    total_factor_bytes = sum(int(row.get("packed_bytes", 0)) for row in rows)
    return {
        "processed_class_count": class_count,
        "all_class_certificates_pass": bool(
            class_count > 0 and all(bool(row.get("gate_pass")) for row in rows)
        ),
        "total_factor_bytes": int(total_factor_bytes),
        "total_factor_bytes_limit": TOTAL_FACTOR_BYTES_LIMIT,
        "all_class_factor_bytes_within_global_limit": (
            total_factor_bytes <= TOTAL_FACTOR_BYTES_LIMIT
        ),
        "dense_class_max_live": 1,
        "dense_workspace_released": True,
    }
