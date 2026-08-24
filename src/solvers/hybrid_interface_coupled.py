"""Pure NumPy coupled lower/upper interface algebra for Task040 V3-1.

This module only combines the reviewed small projected matrices.  It does not
assemble a FEM operator, construct a PETSc/MUMPS factor, or load an interface
packet.  The full 776-dimensional result is a mechanism oracle; callers that
need a scalable candidate must apply the later bounded-rank contract.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

EXPECTED_GROUP_ORDER = ("group0", "group1", "group2")
EXPECTED_SPAN_SIZES = (296, 776, 480)
CONDITION_LIMIT = 1.0e12

__all__ = [
    "CONDITION_LIMIT",
    "EXPECTED_GROUP_ORDER",
    "EXPECTED_SPAN_SIZES",
    "assemble_coupled_interface_matrices",
    "matrix_diagnostics",
    "solve_coupled_interface",
]


def _matrix_sha256(matrix: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(matrix).tobytes()).hexdigest()


def _as_matrix(value: Any, name: str, expected_shape: tuple[int, int]) -> np.ndarray:
    matrix = np.asarray(value)
    if matrix.dtype != np.dtype(np.complex128):
        raise ValueError(f"{name} must have complex128 dtype")
    if matrix.shape != expected_shape or matrix.ndim != 2:
        raise ValueError(f"{name} must have shape {expected_shape}")
    if not np.isfinite(matrix).all():
        raise ValueError(f"{name} is nonfinite")
    return matrix


def matrix_diagnostics(
    matrix: np.ndarray,
    *,
    expected_shape: tuple[int, int] | None = None,
    square: bool = True,
) -> dict[str, Any]:
    """Return finite/rank/SVD/hash diagnostics for a small matrix.

    ``condition`` is reported only for square matrices.  Rectangular
    cross-interface blocks still receive their finite/rank/SVD/hash audit,
    but no square-system condition number is implied.
    """

    value = np.asarray(matrix)
    if value.dtype != np.dtype(np.complex128) or value.ndim != 2:
        raise ValueError("diagnostic matrix must be a complex128 2D array")
    if expected_shape is not None and value.shape != expected_shape:
        raise ValueError(f"diagnostic matrix shape {value.shape} != {expected_shape}")
    if square and value.shape[0] != value.shape[1]:
        raise ValueError("diagnostic matrix must be square")
    if not np.isfinite(value).all():
        raise ValueError("diagnostic matrix must be finite")
    singular_values = np.linalg.svd(value, compute_uv=False)
    rank = int(np.linalg.matrix_rank(value))
    condition = None
    if square:
        condition = (
            float(singular_values[0] / singular_values[-1])
            if singular_values.size and singular_values[-1] > 0.0
            else float("inf")
        )
    return {
        "shape": [int(item) for item in value.shape],
        "dtype": "complex128",
        "rank": rank,
        "singular_values": [float(item) for item in singular_values],
        "condition": condition,
        "sha256": _matrix_sha256(value),
    }


def _block_diagonal(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    result = np.zeros(
        (left.shape[0] + right.shape[0], left.shape[1] + right.shape[1]),
        dtype=np.complex128,
    )
    result[: left.shape[0], : left.shape[1]] = left
    result[left.shape[0] :, left.shape[1] :] = right
    return result


def _block_diagnostics(
    matrix: np.ndarray, lower_span: int, upper_span: int
) -> dict[str, dict[str, Any]]:
    slices = {
        "LL": (slice(0, lower_span), slice(0, lower_span)),
        "LU": (slice(0, lower_span), slice(lower_span, lower_span + upper_span)),
        "UL": (slice(lower_span, lower_span + upper_span), slice(0, lower_span)),
        "UU": (
            slice(lower_span, lower_span + upper_span),
            slice(lower_span, lower_span + upper_span),
        ),
    }
    full_norm = float(np.linalg.norm(matrix, ord="fro"))
    scale = max(full_norm, np.finfo(float).tiny)
    result: dict[str, dict[str, Any]] = {}
    for name, (row_slice, col_slice) in slices.items():
        block = np.asarray(matrix[row_slice, col_slice], dtype=np.complex128)
        result[name] = {
            **matrix_diagnostics(block, square=False),
            "frobenius_norm": float(np.linalg.norm(block, ord="fro")),
            "relative_frobenius_norm": float(np.linalg.norm(block, ord="fro") / scale),
        }
    return result


def assemble_coupled_interface_matrices(
    group_matrices: Sequence[Mapping[str, np.ndarray]],
    *,
    expected_span_sizes: tuple[int, int, int] = EXPECTED_SPAN_SIZES,
) -> dict[str, Any]:
    """Assemble the scalar/exact joint lower-plus-upper projected matrices.

    ``group_matrices`` is ordered group0, group1, group2.  Each mapping has
    ``gram``, ``projected_scalar`` and ``projected_exact`` arrays.  The middle
    group is always interpreted as lower rows/columns followed by upper rows.
    """

    if len(group_matrices) != 3:
        raise ValueError("coupled interface algebra requires exactly three groups")
    if len(expected_span_sizes) != 3:
        raise ValueError("three expected group spans are required")
    lower_span, middle_span, upper_span = (int(item) for item in expected_span_sizes)
    if middle_span != lower_span + upper_span:
        raise ValueError("middle span must equal lower plus upper span")

    required = ("gram", "projected_scalar", "projected_exact")
    groups: list[dict[str, np.ndarray]] = []
    group_diagnostics: list[dict[str, Any]] = []
    for group_index, payload in enumerate(group_matrices):
        expected_shape = (int(expected_span_sizes[group_index]),) * 2
        if any(name not in payload for name in required):
            raise ValueError(
                f"group{group_index} projected matrix inventory is incomplete"
            )
        matrices = {
            name: _as_matrix(
                payload[name], f"group{group_index}.{name}", expected_shape
            )
            for name in required
        }
        groups.append(matrices)
        group_diagnostics.append(
            {
                "group": f"group{group_index}",
                **{
                    name: matrix_diagnostics(matrix, expected_shape=expected_shape)
                    for name, matrix in matrices.items()
                },
            }
        )

    joint_names = ("projected_scalar", "projected_exact")
    joint = {
        name: groups[1][name] + _block_diagonal(groups[0][name], groups[2][name])
        for name in joint_names
    }
    joint_diagnostics = {
        name: matrix_diagnostics(matrix, expected_shape=(middle_span, middle_span))
        for name, matrix in joint.items()
    }
    return {
        "group_order": list(EXPECTED_GROUP_ORDER),
        "span_sizes": [lower_span, middle_span, upper_span],
        "lower_span": lower_span,
        "upper_span": upper_span,
        "joint_projected_scalar": joint["projected_scalar"],
        "joint_projected_exact": joint["projected_exact"],
        "diagnostics": {
            "groups": group_diagnostics,
            "joint": joint_diagnostics,
            "joint_exact_blocks": _block_diagnostics(
                joint["projected_exact"], lower_span, upper_span
            ),
            "joint_scalar_blocks": _block_diagnostics(
                joint["projected_scalar"], lower_span, upper_span
            ),
            "condition_limit": CONDITION_LIMIT,
        },
    }


def solve_coupled_interface(matrix: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    """Solve a small non-Hermitian projected system with an SVD solve."""

    operator = np.asarray(matrix)
    vector = np.asarray(rhs, dtype=np.complex128)
    if operator.dtype != np.dtype(np.complex128) or operator.ndim != 2:
        raise ValueError("coupled operator must be a complex128 matrix")
    if operator.shape[0] != operator.shape[1] or vector.shape[0] != operator.shape[0]:
        raise ValueError("coupled operator and RHS shapes do not match")
    if not np.isfinite(operator).all() or not np.isfinite(vector).all():
        raise ValueError("coupled solve input is nonfinite")
    u, singular_values, vh = np.linalg.svd(operator, full_matrices=False)
    if singular_values.size == 0 or not np.isfinite(singular_values).all():
        raise ValueError("coupled operator has no finite singular values")
    tolerance = np.finfo(float).eps * max(operator.shape) * singular_values[0]
    if singular_values[-1] <= tolerance:
        raise ValueError("coupled projected operator is numerically singular")
    projected = u.conj().T @ vector
    if vector.ndim == 1:
        return vh.conj().T @ (projected / singular_values)
    return vh.conj().T @ (projected / singular_values[:, None])
