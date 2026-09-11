"""Small, reference-free algebra for the reviewed p4 direction diagnosis.

The production p4 operator is deliberately not implemented here.  This
module only handles the at-most-48-column dense algebra used after a real
bounded I4/B4 call.  All least-squares solves use an explicit SVD cutoff;
normal equations and dense inverses are intentionally absent.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np


RANK_RTOL = 1.0e-12


def _as_columns(value: Any, *, name: str) -> np.ndarray:
    array = np.ascontiguousarray(np.asarray(value, dtype=np.complex128))
    if array.ndim != 2 or array.shape[0] == 0:
        raise ValueError(f"{name} must be a non-empty two-dimensional column array")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} contains non-finite entries")
    return array


def _as_vector(value: Any, *, name: str, size: int | None = None) -> np.ndarray:
    array = np.ascontiguousarray(np.asarray(value, dtype=np.complex128))
    if array.ndim != 1 or (size is not None and array.size != size):
        raise ValueError(f"{name} has an incompatible vector shape")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} contains non-finite entries")
    return array


def svd_lstsq(
    matrix: Any,
    rhs: Any,
    *,
    rtol: float = RANK_RTOL,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Solve a complex least-squares problem with one fixed relative cutoff."""

    matrix = _as_columns(matrix, name="least-squares matrix")
    rhs = _as_vector(rhs, name="least-squares rhs", size=matrix.shape[0])
    if not np.isfinite(rtol) or rtol <= 0.0:
        raise ValueError("SVD relative cutoff must be positive and finite")
    # Normalize columns before rank detection.  The candidates have very
    # different physical scales (in particular the local responses versus
    # the I4 directions); allowing those scales to determine the SVD rank
    # would turn an amplitude difference into a direction decision.  The
    # returned coefficients are transformed back to the original columns.
    column_scale = np.linalg.norm(matrix, axis=0)
    column_scale = np.where(
        column_scale > np.finfo(float).tiny, column_scale, 1.0
    )
    from scipy.linalg import qr as scipy_qr

    # Give SciPy an owned Fortran buffer so overwrite_a=True cannot copy the
    # tall matrix merely to satisfy a layout/ownership requirement.
    scaled_matrix = np.empty_like(matrix, order="F")
    np.divide(matrix, column_scale[None, :], out=scaled_matrix)
    # A tall SVD keeps several N-by-k LAPACK/work copies alive.  Economic
    # Householder QR reduces the large-space step to Q^H rhs and a small R;
    # only R (at most 48 rows/columns in the production diagnosis) is sent
    # through the rank-revealing SVD.  This remains a direct SVD cutoff and
    # never forms normal equations.
    q_factor, r_factor = scipy_qr(
        scaled_matrix, mode="economic", overwrite_a=True, check_finite=False,
    )
    u, singular, vh = np.linalg.svd(r_factor, full_matrices=False)
    scale = float(singular[0]) if singular.size else 0.0
    cutoff = float(rtol * scale)
    keep = singular > cutoff
    projected = u.conj().T @ (q_factor.conj().T @ rhs)
    coefficients = np.zeros(vh.shape[0], dtype=np.complex128)
    if np.any(keep):
        coefficients[keep] = projected[keep] / singular[keep]
    scaled_solution = vh.conj().T @ coefficients
    solution = scaled_solution / column_scale
    if not np.isfinite(solution).all():
        raise FloatingPointError("SVD least-squares solution is non-finite")
    facts = {
        "method": "complex_column_scaled_qr_small_svd",
        "relative_cutoff": float(rtol),
        "absolute_cutoff": cutoff,
        "rank": int(np.count_nonzero(keep)),
        "columns": int(matrix.shape[1]),
        "rows": int(matrix.shape[0]),
        "column_scaling": "euclidean_unit_norm_before_svd",
        "column_scale": column_scale.tolist(),
        "qr_shape": [int(value) for value in r_factor.shape],
        "singular_values": singular.tolist(),
        "rank_sensitive": bool(
            scale > 0.0
            and np.any(
                (singular >= 0.1 * cutoff) & (singular <= 10.0 * cutoff)
            )
        ),
    }
    return solution, facts


def _weighted_apply(
    apply_mass: Callable[[np.ndarray], np.ndarray], value: np.ndarray, *, name: str,
) -> np.ndarray:
    result = np.ascontiguousarray(np.asarray(apply_mass(value), dtype=np.complex128))
    if result.shape != value.shape or not np.isfinite(result).all():
        raise ValueError(f"weighted action returned an invalid {name}")
    return result


def weighted_mgs_lstsq(
    columns: Any,
    target: Any,
    apply_mass: Callable[[np.ndarray], np.ndarray],
    *,
    rtol: float = RANK_RTOL,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Solve ``min ||target-columns*y||_M`` by two-pass weighted MGS.

    The large-space operation is only the supplied matrix-free mass action.
    The resulting upper trapezoidal coefficient array is solved by the same
    small SVD routine as the Euclidean problem, so no normal-equation inverse
    is formed.
    """

    columns = _as_columns(columns, name="weighted columns")
    target = _as_vector(target, name="weighted target", size=columns.shape[0])
    if not np.isfinite(rtol) or rtol <= 0.0:
        raise ValueError("weighted SVD relative cutoff must be positive and finite")

    basis: list[np.ndarray] = []
    mass_basis: list[np.ndarray] = []
    weighted_norms: list[float] = []
    original_mass_energy: list[float] = []
    column_scale = np.ones(columns.shape[1], dtype=np.float64)
    rows_by_column: list[np.ndarray] = []
    for column_index, column in enumerate(columns.T):
        original = np.array(column, copy=True)
        mass_original = _weighted_apply(apply_mass, original, name="column mass")
        raw_energy = np.vdot(original, mass_original)
        raw_scale = max(
            float(np.linalg.norm(original) * np.linalg.norm(mass_original)),
            np.finfo(float).tiny,
        )
        if abs(float(raw_energy.imag)) > 1.0e-10 * raw_scale:
            raise ValueError("weighted mass action is not Hermitian on a column")
        if float(raw_energy.real) < -1.0e-10 * raw_scale:
            raise ValueError("weighted mass action is not positive on a column")
        # Weighted unit-norm scaling makes the rank test independent of the
        # arbitrary amplitude carried by each candidate column.
        scale = float(np.sqrt(max(float(raw_energy.real), 0.0)))
        if scale <= np.finfo(float).tiny:
            scale = 1.0
        column_scale[column_index] = scale
        candidate = original / scale
        mass_candidate = mass_original / scale
        row = np.zeros(len(columns.T), dtype=np.complex128)
        for _ in range(2):
            for index, (q, mass_q) in enumerate(zip(basis, mass_basis, strict=True)):
                coefficient = np.vdot(q, mass_candidate)
                row[index] += coefficient
                candidate -= coefficient * q
                mass_candidate -= coefficient * mass_q
        energy = np.vdot(candidate, mass_candidate)
        # Once a column has been projected out, both residual vectors can be
        # at roundoff scale.  Use the scale of the original weighted
        # operation after the same column normalization; a residual-sized
        # denominator would classify harmless cancellation roundoff as a
        # non-Hermitian mass action.
        normalized_energy_scale = max(
            raw_scale / (scale * scale),
            abs(float(raw_energy.real)) / (scale * scale),
            np.finfo(float).tiny,
        )
        energy_scale = max(
            normalized_energy_scale, abs(float(energy.real)),
            np.finfo(float).tiny,
        )
        if abs(float(energy.imag)) > 1.0e-10 * energy_scale:
            raise ValueError("weighted mass action is not Hermitian on a column")
        norm_squared = float(energy.real)
        if norm_squared < -1.0e-10 * energy_scale:
            raise ValueError("weighted mass action is not positive on a column")
        norm = float(np.sqrt(max(norm_squared, 0.0)))
        weighted_norms.append(norm)
        # Preserve the energy of the original input column.  In particular,
        # a zero/dependent column has energy 0; the unit fallback used by
        # ``column_scale`` is a rank-normalization convenience and is not a
        # physical mass measurement.
        original_mass_energy.append(max(float(raw_energy.real), 0.0))
        # Every input was first weighted-normalized, so a single fixed
        # relative threshold is sufficient and does not drift with the
        # running column amplitudes.
        if norm <= rtol:
            rows_by_column.append(row)
            continue
        row[len(basis)] = norm
        rows_by_column.append(row)
        candidate /= norm
        mass_candidate /= norm
        basis.append(candidate)
        mass_basis.append(mass_candidate)

    rank = len(basis)
    rhs_small: np.ndarray | None = None
    target_mass_squared: float | None = None
    if rank:
        # ``rows_by_column[j]`` contains the projection of input column j
        # onto every basis vector that existed when it was processed.  It is
        # already in the global basis-row order; do not reindex it by the
        # number of retained columns.
        r_factor = np.ascontiguousarray(np.asarray(rows_by_column).T[:rank, :])
        mass_target = _weighted_apply(apply_mass, target, name="target mass")
        rhs_small = np.asarray([np.vdot(q, mass_target) for q in basis])
        target_energy = np.vdot(target, mass_target)
        target_scale = max(
            float(np.linalg.norm(target) * np.linalg.norm(mass_target)),
            np.finfo(float).tiny,
        )
        if abs(float(target_energy.imag)) > 1.0e-10 * target_scale:
            raise ValueError("weighted mass action is not Hermitian on target")
        if float(target_energy.real) < -1.0e-10 * target_scale:
            raise ValueError("weighted mass action is not positive on target")
        target_mass_squared = max(float(target_energy.real), 0.0)
        scaled_solution, svd_facts = svd_lstsq(r_factor, rhs_small, rtol=rtol)
        solution = scaled_solution / column_scale
        effective_rank = int(svd_facts.get("rank", rank))
    else:
        r_factor = np.empty((0, columns.shape[1]), dtype=np.complex128)
        solution = np.zeros(columns.shape[1], dtype=np.complex128)
        svd_facts = {
            "method": "complex_column_scaled_qr_small_svd",
            "relative_cutoff": float(rtol),
            "absolute_cutoff": 0.0,
            "rank": 0,
            "columns": int(columns.shape[1]),
            "rows": 0,
            "singular_values": [],
            "rank_sensitive": False,
            "column_scaling": "not_applicable_zero_rank",
            "column_scale": column_scale.tolist(),
        }
        effective_rank = 0
    mgs_rank_sensitive = bool(any(
        1.0e-13 <= value <= 1.0e-11
        for value in weighted_norms
        if value <= rtol
    ))
    orthogonality = 0.0
    if rank:
        gram = np.asarray([[np.vdot(basis[i], mass_basis[j])
                            for j in range(rank)] for i in range(rank)])
        orthogonality = float(np.linalg.norm(gram - np.eye(rank)))
    facts = {
        "method": "two_pass_weighted_mgs_then_svd",
        "relative_cutoff": float(rtol),
        "rank": effective_rank,
        "mgs_rank": int(rank),
        "input_columns": int(columns.shape[1]),
        "weighted_norms": weighted_norms,
        "original_mass_energy": original_mass_energy,
        "column_scaling": "weighted_unit_norm_before_mgs",
        "column_scale": column_scale.tolist(),
        "rank_sensitive": bool(
            svd_facts.get("rank_sensitive", False) or mgs_rank_sensitive
        ),
        "mgs_rank_sensitive": mgs_rank_sensitive,
        "svd": svd_facts,
        "r_factor": r_factor,
        "rhs_small": None if rhs_small is None else rhs_small,
        "target_mass_squared": target_mass_squared,
        "weighted_basis_orthogonality": orthogonality,
    }
    return solution, facts


def select_local_response_indices(
    rhs: Any,
    base_images: Any,
    local_images: Any,
    *,
    max_local: int = 8,
    rtol: float = RANK_RTOL,
) -> tuple[list[int], dict[str, Any]]:
    """Select at most ``max_local`` local images by residual correlation.

    The returned indices are zero-based canonical block indices.  The rule
    sees only the RHS and A-images, never a reference field or held-out label.
    """

    rhs = _as_vector(rhs, name="selector rhs")
    base_images = _as_columns(base_images, name="selector base images")
    local_images = _as_columns(local_images, name="selector local images")
    if base_images.shape[0] != rhs.size or local_images.shape[0] != rhs.size:
        raise ValueError("selector image dimensions do not match the RHS")
    if max_local < 0:
        raise ValueError("selector local cap must be non-negative")

    chosen: list[int] = []
    current = np.array(base_images, copy=True)
    rounds: list[dict[str, Any]] = []
    for _ in range(min(int(max_local), local_images.shape[1])):
        # Rebuild a rank-revealing orthonormal basis from the currently
        # retained A-images.  Base directions therefore affect the first
        # residual as well as every later round.
        base_scale = np.linalg.norm(current, axis=0)
        base_scale = np.where(
            base_scale > np.finfo(float).tiny, base_scale, 1.0
        )
        scaled_current = current / base_scale[None, :]
        u, singular, _ = np.linalg.svd(scaled_current, full_matrices=False)
        cutoff = rtol * (float(singular[0]) if singular.size else 0.0)
        keep = singular > cutoff
        orthogonal = u[:, keep]
        residual = rhs - orthogonal @ (orthogonal.conj().T @ rhs)
        residual_norm = float(np.linalg.norm(residual))
        if residual_norm <= rtol * max(float(np.linalg.norm(rhs)), np.finfo(float).tiny):
            break
        best_index: int | None = None
        best_score = -1.0
        best_vector: np.ndarray | None = None
        for index in range(local_images.shape[1]):
            if index in chosen:
                continue
            raw_candidate = np.array(local_images[:, index], copy=True)
            candidate_scale = max(
                float(np.linalg.norm(raw_candidate)), np.finfo(float).tiny
            )
            candidate = raw_candidate / candidate_scale
            for _pass in range(2):
                if orthogonal.shape[1]:
                    candidate -= orthogonal @ (orthogonal.conj().T @ candidate)
            candidate_norm = float(np.linalg.norm(candidate))
            if candidate_norm <= rtol:
                continue
            score = abs(np.vdot(candidate, residual)) / max(
                candidate_norm * residual_norm, np.finfo(float).tiny
            )
            if score > best_score + 0.0 or (
                score == best_score and (best_index is None or index < best_index)
            ):
                best_index = index
                best_score = float(score)
                best_vector = candidate
        if best_index is None or best_vector is None:
            break
        chosen.append(best_index)
        current = np.column_stack((current, local_images[:, best_index]))
        rounds.append({
            "selected_block_index": int(best_index),
            "normalized_correlation": float(best_score),
            "residual_norm": float(np.linalg.norm(residual)),
            "current_rank": int(np.count_nonzero(keep)),
            "current_singular_values": singular.tolist(),
            "current_column_scale": base_scale.tolist(),
            "current_relative_cutoff": float(rtol),
        })
    return chosen, {
        "base_column_count": int(base_images.shape[1]),
        "candidate_column_count": int(local_images.shape[1]),
        "maximum_local_columns": int(max_local),
        "selected_block_indices": chosen,
        "rounds": rounds,
        "relative_cutoff": float(rtol),
        "rank_detection": "column_scaled_svd",
        "uses_reference": False,
    }


__all__ = [
    "RANK_RTOL",
    "select_local_response_indices",
    "svd_lstsq",
    "weighted_mgs_lstsq",
]
