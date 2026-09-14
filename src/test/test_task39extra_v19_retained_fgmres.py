"""Real PETSc checks for physical stopping on a smaller Krylov space."""

import numpy as np
from petsc4py import PETSc

from src.solvers.physical_retained_fgmres import run_retained_fgmres


def _solve(matrix, *, physical_scale=1.0, port_error=0.0, stop=lambda: False):
    rhs = PETSc.Vec().createSeq(len(matrix), comm=PETSc.COMM_SELF)
    rhs.array[:] = 1.0
    rows, checkpoints = [], []

    def action(source):
        target = source.duplicate()
        target.array[:] = matrix @ source.array_r
        return target

    def evaluate(y, residual):
        rho = float(residual.norm()) / rhs.norm()
        return {"original_A6_relative": physical_scale * rho,
                "port_closure_relative": port_error,
                "internal_residual_relative": 0.0,
                "native_identity_relative": 0.0,
                "schur_port_identity_relative": 0.0,
                "retained_solution_norm": float(y.norm())}

    try:
        result = run_retained_fgmres(
            rhs, action, lambda source: source.copy(), evaluate=evaluate,
            checkpoint=lambda it, y, facts: checkpoints.append((it, y.array_r.copy())),
            append=lambda name, row: rows.append((name, row)),
            seconds=lambda: 1e9, stop_requested=stop,
        )
        result["final_solution"].destroy()
        return result, rows, checkpoints
    finally:
        rhs.destroy()


def test_real_ksp_solves_retained_space_with_physical_terminal_check():
    matrix = np.array([[3.0, 1j, 0.0], [0.1, 2.0, 0.3j], [0.0, 0.2, 4.0]])
    result, _rows, checkpoints = _solve(matrix)
    assert result["status"] == "TRUE_RESIDUAL_PASS"
    assert result["retained_global_size"] == 3
    assert result["ksp_create_count"] == result["ksp_solve_count"] == result["ksp_destroy_count"] == 1
    assert result["final_true_residual"] < 1e-12
    assert checkpoints[0][0] == 0 and np.count_nonzero(checkpoints[0][1]) == 0
    assert checkpoints[-1][0] == result["iterations"]
    np.testing.assert_allclose(matrix @ checkpoints[-1][1], np.ones(3), atol=1e-12)
    assert result["time_gate_evaluated"] is False


def test_schur_convergence_cannot_bypass_port_closure():
    result, _rows, _checkpoints = _solve(np.eye(3), port_error=1e-4)
    assert result["status"] != "TRUE_RESIDUAL_PASS"
    assert result["final_evaluation"]["schur_true_relative_residual"] < 1e-12
    assert result["final_evaluation"]["physical_residual_pass"] is False


def test_user_stop_preserves_a_terminal_checkpoint_and_closes_ksp():
    result, _rows, checkpoints = _solve(np.eye(3), stop=lambda: True)
    assert result["status"] == "USER_CONTROLLED_STOP"
    assert result["iterations"] == 0
    assert len(checkpoints) == 1
    assert result["ksp_destroy_count"] == 1


def test_continues_same_ksp_past_64_steps_and_observes_large_time():
    # A fixed nonnormal Grcar system takes several restart cycles without
    # any PC, exposing the former 64-step hard screen on a tiny fixture.
    n = 100
    matrix = np.eye(n, dtype=complex) - np.eye(n, k=-1)
    for k in (1, 2, 3):
        matrix += np.eye(n, k=k)
    result, rows, checkpoints = _solve(matrix)
    assert result["iterations"] > 64
    assert result["status"] == "TRUE_RESIDUAL_PASS"
    assert result["screen_enabled"] is False
    assert result["ksp_solve_count"] == 1
    iterations = {row["iteration"] for name, row in rows if name == "monitor_residuals.jsonl"}
    assert set(range(0, result["iterations"], 8)) <= iterations
    saved = {it for it, _ in checkpoints}
    assert set(range(0, result["iterations"], 32)) <= saved
    assert result["elapsed_seconds"] == 1e9
