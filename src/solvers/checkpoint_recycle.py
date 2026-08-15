"""Fixed four-checkpoint offline recycle-space projection."""

from collections.abc import Mapping
from typing import Any

import numpy as np


CHECKPOINT_ITERATIONS = (20, 100, 150, 200)
RECYCLE_COLUMNS = 4
RANK_THRESHOLD_MULTIPLIER = 128.0
NORMAL_CLOSURE_LIMIT = 1.0e-11


def _vector(value: Any, rows: int | None, label: str) -> np.ndarray:
    array = np.asarray(value)
    if array.ndim != 1 or array.dtype != np.dtype(np.complex128):
        raise ValueError(f"{label} must be one-dimensional complex128")
    if rows is not None and array.shape != (rows,):
        raise ValueError(f"{label} has inconsistent length")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{label} is not finite")
    return array


def build_checkpoint_increments(
    checkpoints: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    """Return dX and dAX in the fixed 20/100/150/200 order."""

    if not isinstance(checkpoints, Mapping) or set(checkpoints) != set(CHECKPOINT_ITERATIONS):
        raise ValueError("checkpoint set must be exactly 20/100/150/200")
    solutions: list[np.ndarray] = []
    actions: list[np.ndarray] = []
    rows: int | None = None
    for iteration in CHECKPOINT_ITERATIONS:
        item = checkpoints[iteration]
        if not isinstance(item, Mapping) or set(item) != {"solution", "outer_action"}:
            raise ValueError(f"checkpoint {iteration} is incomplete")
        solution = _vector(item["solution"], rows, f"solution {iteration}")
        if rows is None:
            rows = solution.size
        action = _vector(item["outer_action"], rows, f"outer action {iteration}")
        solutions.append(solution)
        actions.append(action)
    d_solution = np.column_stack((solutions[0], *(solutions[i] - solutions[i - 1] for i in range(1, 4))))
    d_action = np.column_stack((actions[0], *(actions[i] - actions[i - 1] for i in range(1, 4))))
    if not np.all(np.isfinite(d_solution)) or not np.all(np.isfinite(d_action)):
        raise ValueError("checkpoint increments are not finite")
    return {"checkpoint_iterations": CHECKPOINT_ITERATIONS, "dX": d_solution, "dAX": d_action}


def project_residual(delta_action: Any, residual: Any) -> dict[str, Any]:
    """Project one residual with fixed SVD and scale-normalized normal closure."""

    matrix = np.asarray(delta_action)
    if (
        matrix.ndim != 2
        or matrix.shape[1] != RECYCLE_COLUMNS
        or matrix.dtype != np.dtype(np.complex128)
        or not np.all(np.isfinite(matrix))
    ):
        raise ValueError("delta_action must be finite complex128 with four columns")
    vector = _vector(residual, matrix.shape[0], "residual")
    left, singular, right_h = np.linalg.svd(matrix, full_matrices=False)
    sigma_max = float(singular[0])
    threshold = RANK_THRESHOLD_MULTIPLIER * np.finfo(np.float64).eps * sigma_max
    rank = int(np.count_nonzero(singular > threshold))
    finite = bool(np.all(np.isfinite(left)) and np.all(np.isfinite(singular)) and np.all(np.isfinite(right_h)))
    result: dict[str, Any] = {
        "finite": finite,
        "rank": rank,
        "column_count": RECYCLE_COLUMNS,
        "singular_values": singular.copy(),
        "rank_threshold": threshold,
        "condition_number": float(sigma_max / singular[-1]) if singular[-1] > 0 else float("inf"),
        "coefficients": None,
        "normal_closure": None,
        "rho": None,
        "captured_energy_ratio": None,
        "pass": False,
        "problems": [],
    }
    if not finite:
        result["problems"] = ["nonfinite_svd"]
        return result
    if rank != RECYCLE_COLUMNS:
        result["problems"] = ["rank"]
        return result
    coefficients = right_h.conj().T @ ((left.conj().T @ vector) / singular)
    projected = matrix @ coefficients
    remaining = vector - projected
    vector_norm = float(np.linalg.norm(vector))
    remaining_norm = float(np.linalg.norm(remaining))
    normal_error = matrix.conj().T @ (projected - vector)
    closure = float(
        np.linalg.norm(normal_error)
        / max(sigma_max * vector_norm, np.finfo(float).tiny)
    )
    rho = float(remaining_norm / max(vector_norm, np.finfo(float).tiny))
    captured = float(np.vdot(projected, projected).real / max(vector_norm * vector_norm, np.finfo(float).tiny))
    finite = bool(finite and np.all(np.isfinite(coefficients)) and np.isfinite(closure) and np.isfinite(rho) and np.isfinite(captured))
    passed = bool(finite and closure <= NORMAL_CLOSURE_LIMIT)
    result.update({
        "finite": finite,
        "coefficients": coefficients.copy(),
        "normal_closure": closure,
        "rho": rho,
        "captured_energy_ratio": captured,
        "pass": passed,
        "problems": [] if passed else ["normal_closure"],
    })
    return result
