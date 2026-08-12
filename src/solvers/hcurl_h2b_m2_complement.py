"""Research-only M2 high-complement patch oracle.

The module owns the small p4/p6 split algebra.  A caller supplies the
already constrained and oriented central-cell injection and the restricted
global row-complete B0 patch.  No global matrix, neighbourhood collection, or
factor-store policy is implemented here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any
import hashlib
import json

import numpy as np


M2_LOW_DIMENSION = 300
M2_PATCH_DIMENSION = 882
M2_HIGH_DIMENSION = M2_PATCH_DIMENSION - M2_LOW_DIMENSION
M2_RANK_TOLERANCE_FACTOR = 128.0 * np.finfo(np.float64).eps
M2_Q_ORTHOGONALITY_LIMIT = 1.0e-12
M2_SPLIT_RECONSTRUCTION_LIMIT = 1.0e-11


def _array_sha256(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value)
    header = json.dumps(
        {"dtype": array.dtype.str, "shape": list(array.shape)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    digest = hashlib.sha256()
    digest.update(header)
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _readonly_copy(value: Any, dtype: np.dtype[Any]) -> np.ndarray:
    array = np.array(value, dtype=dtype, copy=True, order="C")
    array.setflags(write=False)
    return array


def _canonicalize_columns(value: np.ndarray) -> np.ndarray:
    result = np.array(value, dtype=np.complex128, copy=True, order="C")
    for column in range(result.shape[1]):
        pivot = int(np.argmax(np.abs(result[:, column])))
        amplitude = abs(result[pivot, column])
        if amplitude == 0.0:
            raise ValueError("M2 QR produced a zero column")
        result[:, column] *= np.conjugate(result[pivot, column]) / amplitude
    return result


def _validate_injection(
    value: Any,
    *,
    expected_patch_dimension: int,
    expected_low_dimension: int,
) -> np.ndarray:
    injection = np.asarray(value)
    if (
        injection.dtype != np.dtype(np.complex128)
        or injection.ndim != 2
        or injection.shape != (expected_patch_dimension, expected_low_dimension)
        or not injection.flags.c_contiguous
        or not np.all(np.isfinite(injection))
    ):
        raise ValueError("M2 central injection must be finite C-contiguous complex128")
    return injection


@dataclass(frozen=True)
class H2BM2ComplementCarrier:
    """One immutable central-cell complement carrier.

    ``q_low`` and ``q_high`` are retained for one representative only.  The
    interface is intentionally suitable for M3 to use one current carrier at
    a time; it has no per-neighbourhood storage contract.
    """

    q_low: np.ndarray
    q_high: np.ndarray
    injection_sha256: str
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        q_low = _readonly_copy(self.q_low, np.dtype(np.complex128))
        q_high = _readonly_copy(self.q_high, np.dtype(np.complex128))
        if q_low.ndim != 2 or q_high.ndim != 2 or q_low.shape[0] != q_high.shape[0]:
            raise ValueError("M2 complement basis shapes are incompatible")
        if not np.all(np.isfinite(q_low)) or not np.all(np.isfinite(q_high)):
            raise ValueError("M2 complement basis is nonfinite")
        object.__setattr__(self, "q_low", q_low)
        object.__setattr__(self, "q_high", q_high)
        object.__setattr__(self, "audit", MappingProxyType(dict(self.audit)))

    @property
    def patch_dimension(self) -> int:
        return int(self.q_low.shape[0])

    @property
    def low_dimension(self) -> int:
        return int(self.q_low.shape[1])

    @property
    def high_dimension(self) -> int:
        return int(self.q_high.shape[1])

    @property
    def retained_transform_bytes(self) -> int:
        return int(self.q_low.nbytes + self.q_high.nbytes)

    def project_low(self, values: np.ndarray) -> np.ndarray:
        return np.ascontiguousarray(self.q_low.conj().T @ values, dtype=np.complex128)

    def project_high(self, values: np.ndarray) -> np.ndarray:
        return np.ascontiguousarray(self.q_high.conj().T @ values, dtype=np.complex128)

    def lift_low(self, values: np.ndarray) -> np.ndarray:
        return np.ascontiguousarray(self.q_low @ values, dtype=np.complex128)

    def lift_high(self, values: np.ndarray) -> np.ndarray:
        return np.ascontiguousarray(self.q_high @ values, dtype=np.complex128)


def build_h2b_m2_complement(
    injection: np.ndarray,
    *,
    expected_patch_dimension: int = M2_PATCH_DIMENSION,
    expected_low_dimension: int = M2_LOW_DIMENSION,
) -> H2BM2ComplementCarrier:
    """Build the fixed deterministic Householder QR p4/high split."""

    injection = _validate_injection(
        injection,
        expected_patch_dimension=expected_patch_dimension,
        expected_low_dimension=expected_low_dimension,
    )
    q_full, r_factor = np.linalg.qr(injection, mode="complete")
    norm_two = float(np.linalg.norm(injection, ord=2))
    rank_threshold = M2_RANK_TOLERANCE_FACTOR * norm_two
    diagonal = np.abs(np.diag(r_factor))
    rank = int(np.count_nonzero(diagonal > rank_threshold))
    if rank != expected_low_dimension:
        raise ValueError(
            f"M2 central injection rank {rank} is not {expected_low_dimension}"
        )
    q_low = _canonicalize_columns(q_full[:, :expected_low_dimension])
    q_high = _canonicalize_columns(q_full[:, expected_low_dimension:])
    q_all = np.concatenate((q_low, q_high), axis=1)
    identity = np.eye(q_all.shape[1], dtype=np.complex128)
    q_orthogonality_error = float(np.linalg.norm(q_all.conj().T @ q_all - identity, ord=2))
    split_reconstruction_error = float(
        np.linalg.norm(q_low @ q_low.conj().T + q_high @ q_high.conj().T - np.eye(q_all.shape[0]), ord=2)
    )
    if (
        q_orthogonality_error > M2_Q_ORTHOGONALITY_LIMIT
        or split_reconstruction_error > M2_SPLIT_RECONSTRUCTION_LIMIT
    ):
        raise ValueError("M2 QR orthogonality or split reconstruction Gate failed")
    injection_sha = _array_sha256(injection)
    audit = {
        "schema": "task037.extra.h2b.m2.complement.v1",
        "injection_sha256": injection_sha,
        "rank_threshold_factor": M2_RANK_TOLERANCE_FACTOR,
        "rank_threshold": rank_threshold,
        "injection_2_norm": norm_two,
        "rank": rank,
        "q_low_dimension": int(q_low.shape[1]),
        "q_high_dimension": int(q_high.shape[1]),
        "q_orthogonality_error": q_orthogonality_error,
        "split_reconstruction_error": split_reconstruction_error,
        "q_low_sha256": _array_sha256(q_low),
        "q_high_sha256": _array_sha256(q_high),
        "retained_transform_bytes": int(q_low.nbytes + q_high.nbytes),
        "dense_qh_retained": True,
        "dense_qh_count": 1,
        "ordinary_default_changed": False,
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "per_neighborhood_qh_retained": False,
    }
    return H2BM2ComplementCarrier(q_low, q_high, injection_sha, audit)


def build_h2b_m2_cell_injection(
    *,
    patch_rows: np.ndarray,
    p4_global_rows: np.ndarray,
    p4_cell_dofs: np.ndarray,
    p6_global_rows: np.ndarray,
    p6_cell_dofs: np.ndarray,
    p4_local_rows: int,
    p6_local_rows: int,
    cell_info: int,
    local_apply: Callable[[np.ndarray, int], np.ndarray],
    p4_lift: Callable[[np.ndarray], None] | None = None,
    p6_lift: Callable[[np.ndarray], None] | None = None,
) -> np.ndarray:
    """Build one actual oriented/MPC central-cell injection.

    Global row labels are used only to place local contributions into the
    central patch slots.  The returned matrix is the local ``I_c`` carrier;
    it contains no reusable global-row identity.
    """

    patch = np.asarray(patch_rows, dtype=np.int64)
    p4_rows = np.asarray(p4_global_rows, dtype=np.int64)
    p4_dofs = np.asarray(p4_cell_dofs, dtype=np.int32)
    p6_rows = np.asarray(p6_global_rows, dtype=np.int64)
    p6_dofs = np.asarray(p6_cell_dofs, dtype=np.int32)
    if (
        patch.ndim != 1
        or p4_rows.shape != p4_dofs.shape
        or p6_rows.shape != p6_dofs.shape
        or p4_rows.size == 0
        or np.unique(patch).size != patch.size
        or np.unique(p4_rows).size != p4_rows.size
        or np.unique(p6_rows).size != p6_rows.size
        or np.any(p4_dofs < 0)
        or np.any(p4_dofs >= p4_local_rows)
        or np.any(p6_dofs < 0)
        or np.any(p6_dofs >= p6_local_rows)
        or set(map(int, p6_rows)) != set(map(int, patch))
    ):
        raise ValueError("M2 cell injection row/dof metadata is invalid")
    patch_index = {int(row): index for index, row in enumerate(patch.tolist())}
    result = np.zeros((patch.size, p4_rows.size), dtype=np.complex128, order="C")
    for column, local_dof in enumerate(p4_dofs.tolist()):
        p4_values = np.zeros(p4_local_rows, dtype=np.complex128, order="C")
        p4_values[int(local_dof)] = 1.0
        if p4_lift is not None:
            p4_lift(p4_values)
        local_p6 = np.asarray(
            local_apply(np.ascontiguousarray(p4_values[p4_dofs]), int(cell_info)),
            dtype=np.complex128,
        )
        if local_p6.shape != p6_dofs.shape or not np.all(np.isfinite(local_p6)):
            raise ValueError("M2 local oriented injection returned invalid data")
        p6_values = np.zeros(p6_local_rows, dtype=np.complex128, order="C")
        p6_values[p6_dofs] = local_p6
        if p6_lift is not None:
            p6_lift(p6_values)
        for local_position, global_row in enumerate(p6_rows.tolist()):
            result[patch_index[int(global_row)], column] = p6_values[
                int(p6_dofs[local_position])
            ]
    if not np.all(np.isfinite(result)):
        raise ValueError("M2 central injection is nonfinite")
    return result


def measure_h2b_m2_source(
    rhs_full: np.ndarray,
    patch_rows: np.ndarray,
    carrier: H2BM2ComplementCarrier,
    factor: Any,
    exact_action: Callable[[np.ndarray], np.ndarray],
    *,
    patch_matrix: np.ndarray,
    high_patch_matrix: np.ndarray,
) -> dict[str, Any]:
    """Apply the high complement and measure the complete patch action.

    The full-space action is still formed before restriction.  The M2 gates
    use all row-complete patch rows; the global residual is retained only as a
    spill diagnostic because one local patch cannot reduce the whole mesh.
    """

    rhs = np.ascontiguousarray(np.asarray(rhs_full, dtype=np.complex128))
    rows = np.asarray(patch_rows, dtype=np.int64)
    patch_operator = np.asarray(patch_matrix)
    matrix = np.asarray(high_patch_matrix)
    if (
        rhs.ndim != 1
        or not np.all(np.isfinite(rhs))
        or rows.ndim != 1
        or np.unique(rows).size != rows.size
        or np.any(rows < 0)
        or np.any(rows >= rhs.size)
        or rows.size != carrier.patch_dimension
        or patch_operator.dtype != np.dtype(np.complex128)
        or patch_operator.shape != (carrier.patch_dimension, carrier.patch_dimension)
        or not patch_operator.flags.c_contiguous
        or not np.all(np.isfinite(patch_operator))
        or matrix.dtype != np.dtype(np.complex128)
        or matrix.shape != (carrier.high_dimension, carrier.high_dimension)
        or not matrix.flags.c_contiguous
        or not np.all(np.isfinite(matrix))
    ):
        raise ValueError("M2 source oracle inputs are invalid")
    patch_rhs = np.ascontiguousarray(rhs[rows], dtype=np.complex128)
    patch_rhs_norm = float(np.linalg.norm(patch_rhs))
    if not math_is_positive_finite(patch_rhs_norm):
        raise ValueError("M2 patch RHS is zero or nonfinite")
    low = carrier.project_low(patch_rhs)
    high = carrier.project_high(patch_rhs)
    solution = np.ascontiguousarray(factor.solve(high), dtype=np.complex128)
    if solution.shape != (carrier.high_dimension,) or not np.all(np.isfinite(solution)):
        raise ValueError("M2 high complement solve is invalid")
    correction_patch = carrier.lift_high(solution)
    correction_full = np.zeros_like(rhs)
    correction_full[rows] = correction_patch
    action_full = np.ascontiguousarray(
        np.asarray(exact_action(correction_full), dtype=np.complex128)
    )
    if action_full.shape != rhs.shape or not np.all(np.isfinite(action_full)):
        raise ValueError("M2 full-space action is invalid")
    action_patch = np.ascontiguousarray(action_full[rows], dtype=np.complex128)
    expected_patch_action = np.ascontiguousarray(
        patch_operator @ correction_patch, dtype=np.complex128
    )
    expected_patch_norm = float(np.linalg.norm(expected_patch_action))
    if not math_is_positive_finite(expected_patch_norm):
        raise ValueError("M2 expected patch action is zero or nonfinite")
    closure = float(
        np.linalg.norm(action_patch - expected_patch_action) / expected_patch_norm
    )
    projected_action = carrier.project_high(action_patch)
    expected_projected_action = np.ascontiguousarray(matrix @ solution, dtype=np.complex128)
    projected_closure = float(
        np.linalg.norm(projected_action - expected_projected_action)
        / max(float(np.linalg.norm(expected_projected_action)), np.finfo(float).tiny)
    )
    patch_action_norm = float(np.linalg.norm(action_patch))
    if not math_is_positive_finite(patch_action_norm):
        raise ValueError("M2 patch action is zero or nonfinite")
    patch_inner = np.vdot(action_patch, patch_rhs)
    patch_omega = complex(patch_inner / np.vdot(action_patch, action_patch))
    rho_star = float(
        np.linalg.norm(patch_rhs - patch_omega * action_patch) / patch_rhs_norm
    )
    rho_unit = float(np.linalg.norm(patch_rhs - action_patch) / patch_rhs_norm)
    global_rhs_norm = float(np.linalg.norm(rhs))
    global_action_norm = float(np.linalg.norm(action_full))
    global_inner = np.vdot(action_full, rhs)
    global_omega = complex(global_inner / np.vdot(action_full, action_full))
    global_rho_star = float(
        np.linalg.norm(rhs - global_omega * action_full) / global_rhs_norm
    )
    global_rho_unit = float(np.linalg.norm(rhs - action_full) / global_rhs_norm)
    patch_norm_sq = float(np.vdot(patch_rhs, patch_rhs).real)
    if not math_is_positive_finite(patch_norm_sq):
        raise ValueError("M2 patch RHS energy is zero or nonfinite")
    return {
        "p4_low_energy_fraction": float(np.vdot(low, low).real / patch_norm_sq),
        "high_complement_energy_fraction": float(np.vdot(high, high).real / patch_norm_sq),
        "action_closure_relative": closure,
        "projected_high_closure_relative": projected_closure,
        "rho_scope": f"complete_{carrier.patch_dimension}_patch_rows",
        "full_space_rho_star": rho_star,
        "full_space_rho_unit": rho_unit,
        "omega_real": float(patch_omega.real),
        "omega_imag": float(patch_omega.imag),
        "patch_rhs_norm": patch_rhs_norm,
        "patch_action_norm": patch_action_norm,
        "global_rho_star": global_rho_star,
        "global_rho_unit": global_rho_unit,
        "global_rho_scope": "full_global_rows_diagnostic_only",
        "global_rhs_norm": global_rhs_norm,
        "global_action_norm": global_action_norm,
        "correction_norm": float(np.linalg.norm(correction_full)),
        "rhs_sha256": _array_sha256(rhs),
        "correction_sha256": _array_sha256(correction_full),
        "action_sha256": _array_sha256(action_full),
        "finite": True,
        "correction": correction_full,
        "action": action_full,
    }


def math_is_positive_finite(value: float) -> bool:
    return bool(np.isfinite(value) and value > np.finfo(float).tiny)


__all__ = (
    "H2BM2ComplementCarrier",
    "M2_HIGH_DIMENSION",
    "M2_LOW_DIMENSION",
    "M2_PATCH_DIMENSION",
    "M2_Q_ORTHOGONALITY_LIMIT",
    "M2_RANK_TOLERANCE_FACTOR",
    "M2_SPLIT_RECONSTRUCTION_LIMIT",
    "build_h2b_m2_cell_injection",
    "build_h2b_m2_complement",
    "measure_h2b_m2_source",
)
