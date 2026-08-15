"""Fixed four-checkpoint offline recycle-space projection."""

from collections.abc import Callable, Mapping
from typing import Any

import numpy as np


CHECKPOINT_ITERATIONS = (20, 100, 150, 200)
RECYCLE_COLUMNS = 4
RANK_THRESHOLD_MULTIPLIER = 128.0
NORMAL_CLOSURE_LIMIT = 1.0e-11
W12_SCHEMA = "task037.extra.h2b.w12.fixed-b0-trajectory-range.v1"
W12_B0_RESIDUAL_LIMIT = 1.0e-8
W12_Q_RHO_LIMIT = 0.70
W12_TARGET_RHO_LIMIT = 0.90


def _vector(value: Any, rows: int | None, label: str) -> np.ndarray:
    array = np.asarray(value)
    if array.ndim != 1 or array.dtype != np.dtype(np.complex128):
        raise ValueError(f"{label} must be one-dimensional complex128")
    if rows is not None and array.shape != (rows,):
        raise ValueError(f"{label} has inconsistent length")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{label} is not finite")
    return array


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float, np.integer, np.floating))
        and bool(np.isfinite(value))
    )


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


def _project_residual_twice(delta_action: np.ndarray, residual: np.ndarray) -> dict[str, Any]:
    first = project_residual(delta_action, residual)
    second = project_residual(delta_action, residual)
    exact = (
        first["finite"] == second["finite"]
        and first["rank"] == second["rank"]
        and first["pass"] == second["pass"]
        and first["normal_closure"] == second["normal_closure"]
        and first["rho"] == second["rho"]
        and first["captured_energy_ratio"] == second["captured_energy_ratio"]
        and np.array_equal(first["singular_values"], second["singular_values"])
        and (
            (
                first["coefficients"] is None
                and second["coefficients"] is None
            )
            or np.array_equal(first["coefficients"], second["coefficients"])
        )
    )
    first["repeat_exact"] = bool(exact)
    first["repeat"] = {
        "passes": 2,
        "rho": second["rho"],
        "normal_closure": second["normal_closure"],
        "captured_energy_ratio": second["captured_energy_ratio"],
    }
    if not exact:
        first["pass"] = False
        first["problems"] = [*first["problems"], "repeat"]
    return first


def run_w12_fixed_trajectory_range(
    q: Any,
    target: Any,
    *,
    b0_solve: Callable[[Callable[[int, np.ndarray], None]], Mapping[str, Any]],
    physical_action: Callable[[np.ndarray], np.ndarray],
    architecture: Mapping[str, Any],
    predicted_live_set_bytes: int,
    counters: Mapping[str, Any] | None = None,
    on_trajectory_ready: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Run the fixed W12 B0 trajectory and four-column range diagnostic.

    The B0 callback owns the PETSc solve and reports only the four requested
    ``buildSolution`` snapshots.  The target is not passed to that callback;
    it is used only after the four physical images have been formed.
    """

    q_value = _vector(q, None, "q")
    target_value = _vector(target, q_value.size, "target")
    checkpoints: dict[int, np.ndarray] = {}
    duplicate_checkpoint = False

    def observe(iteration: int, solution: np.ndarray) -> None:
        nonlocal duplicate_checkpoint
        if int(iteration) not in CHECKPOINT_ITERATIONS:
            return
        if int(iteration) in checkpoints:
            duplicate_checkpoint = True
        checkpoints[int(iteration)] = _vector(
            solution, q_value.size, f"checkpoint solution {iteration}"
        ).copy()

    solve = dict(b0_solve(observe))
    solution_present = "solution" in solve
    solve.pop("solution", None)
    solve_evidence = dict(solve)
    fixed_contract = (
        solve.get("max_it") == 200
        and solve.get("ksp_type") == "fgmres"
        and solve.get("initial_solution") == "zero_start"
        and solve.get("iterations") == 200
        and solve.get("converged_reason") == -3
        and solve.get("pc_apply_count") == 200
        and solve.get("restart") == 20
        and solve.get("pc_side") == "right"
        and solve.get("norm_type") == "unpreconditioned"
        and solve.get("rtol") == 0.0
        and solve.get("atol") == 0.0
        and solve.get("finite") is True
        and solution_present
    )
    b0_residual_pass = (
        _finite_number(solve.get("true_residual"))
        and float(solve["true_residual"]) <= W12_B0_RESIDUAL_LIMIT
    )
    checkpoint_set_pass = (
        not duplicate_checkpoint
        and set(checkpoints) == set(CHECKPOINT_ITERATIONS)
    )
    base_checks = {
        "b0_configuration": bool(fixed_contract),
        "b0_solve": bool(b0_residual_pass),
        "checkpoint_set": bool(checkpoint_set_pass),
    }
    if not all(base_checks.values()):
        problems = [name for name, passed in base_checks.items() if not passed]
        return {
            "schema": W12_SCHEMA,
            "status": "gate_failed",
            "classification": "W12_B0_TRAJECTORY_FAIL",
            "selected_range": None,
            "candidate_range": "dX_dAX_4D",
            "b0": {"solve200": solve_evidence},
            "trajectory": {
                "checkpoint_iterations": CHECKPOINT_ITERATIONS,
                "checkpoint_count": len(checkpoints),
                "physical_action_count": 0,
            },
            "checks": {
                **base_checks,
                "finite_deterministic": False,
                "physical_action_count": False,
                "range": False,
                "architecture": False,
                "predicted_live_set": False,
            },
            "problems": problems,
            "formal_pass": False,
            "pde_pass": False,
            "official_rta": False,
        }

    if on_trajectory_ready is not None:
        on_trajectory_ready()
    checkpoint_records: dict[int, dict[str, np.ndarray]] = {}
    physical_action_count = 0
    for iteration in CHECKPOINT_ITERATIONS:
        solution = checkpoints[iteration]
        action = np.asarray(physical_action(solution), dtype=np.complex128)
        action = _vector(action, q_value.size, f"physical action {iteration}").copy()
        checkpoint_records[iteration] = {
            "solution": solution,
            "outer_action": action,
        }
        physical_action_count += 1

    increments = build_checkpoint_increments(checkpoint_records)
    q_projection = _project_residual_twice(increments["dAX"], q_value)
    target_projection = _project_residual_twice(increments["dAX"], target_value)
    from src.solvers.persistent_residual_one_vector import validate_w11a_architecture

    architecture_pass = validate_w11a_architecture(architecture)
    checks = {
        **base_checks,
        "finite_deterministic": bool(
            q_projection["finite"]
            and target_projection["finite"]
            and q_projection["repeat_exact"]
            and target_projection["repeat_exact"]
        ),
        "physical_action_count": physical_action_count == 4,
        "q_projection": bool(
            q_projection["pass"]
            and _finite_number(q_projection.get("rho"))
            and q_projection["rho"] <= W12_Q_RHO_LIMIT
        ),
        "target_projection": bool(
            target_projection["pass"]
            and _finite_number(target_projection.get("rho"))
            and target_projection["rho"] <= W12_TARGET_RHO_LIMIT
        ),
        "range": bool(
            q_projection["rank"] == RECYCLE_COLUMNS
            and target_projection["rank"] == RECYCLE_COLUMNS
            and _finite_number(q_projection.get("normal_closure"))
            and _finite_number(target_projection.get("normal_closure"))
            and q_projection["normal_closure"] <= NORMAL_CLOSURE_LIMIT
            and target_projection["normal_closure"] <= NORMAL_CLOSURE_LIMIT
        ),
        "architecture": bool(architecture_pass),
        "predicted_live_set": (
            type(predicted_live_set_bytes) is int
            and predicted_live_set_bytes < 1_500_000_000
        ),
    }
    problems = sorted(name for name, passed in checks.items() if not passed)
    passed = not problems
    result = {
        "schema": W12_SCHEMA,
        "status": "diagnostic_complete" if passed else "gate_failed",
        "classification": "W12_PASS" if passed else "W12_TRAJECTORY_RANGE_FAIL",
        "selected_range": "dX_dAX_4D" if passed else None,
        "candidate_range": "dX_dAX_4D",
        "b0": {"solve200": solve_evidence},
        "trajectory": {
            "checkpoint_iterations": CHECKPOINT_ITERATIONS,
            "checkpoint_count": 4,
            "physical_action_count": physical_action_count,
            "dX_columns": RECYCLE_COLUMNS,
            "dAX_columns": RECYCLE_COLUMNS,
            "target_used_for_construction": False,
            "counters": {
                **dict(counters or {}),
                "physical_action_count": physical_action_count,
            },
        },
        "measurement": {"q": q_projection, "target": target_projection},
        "checks": checks,
        "problems": problems,
        "formal_pass": False,
        "pde_pass": False,
        "official_rta": False,
    }
    if passed:
        result["_trajectory_vectors"] = {
            "dX": increments["dX"],
            "dAX": increments["dAX"],
        }
    return result
