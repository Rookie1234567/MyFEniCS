"""Actual complex discrete adjoints for Stage-4 DtN power goals.

The Stage-4 auxiliary DtN formulation stores each finite-port modal
projection as an algebraic unknown.  This module differentiates the official
modal ``R_total``/``T_total`` definitions with respect to those unknowns and
solves ``A^H z = g`` without assembling a second matrix: a complex Hermitian
solve is obtained from the existing direct factorization by conjugating a
``KSPSolveTranspose``.  The ordinary solver path is unchanged; callers reach
this code only through the explicit solution-observer research hook.
"""

from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path
from typing import Any, Callable

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from ..common.modes_3d import incident_power_3d
from ..solvers.dtn_port_3d import (
    _gather_auxiliary_values,
    _mode_carries_outward_power,
    _mode_power_at_boundary,
    _port_power_metrics,
)


TINY = np.finfo(float).tiny
SUPPORTED_GOALS = ("R_total", "T_total")


def _relative_difference(left: float, right: float) -> float:
    return float(abs(left - right) / max(abs(left), abs(right), 1.0e-14))


def _linear_residual(
    matrix: PETSc.Mat,
    right_hand_side: PETSc.Vec,
    solution: PETSc.Vec,
    *,
    hermitian: bool = False,
) -> dict[str, float]:
    residual = right_hand_side.duplicate()
    if hermitian:
        matrix.multHermitian(solution, residual)
    else:
        matrix.mult(solution, residual)
    residual.axpy(PETSc.ScalarType(-1.0), right_hand_side)
    rhs_norm = float(right_hand_side.norm())
    residual_norm = float(residual.norm())
    residual.destroy()
    return {
        "rhs_norm": rhs_norm,
        "residual_norm": residual_norm,
        "relative_residual": residual_norm / max(rhs_norm, TINY),
    }


def _normalized_goal_weights(config, modes, goal: str) -> np.ndarray:
    if goal not in SUPPORTED_GOALS:
        raise ValueError(f"unsupported DtN power goal: {goal!r}")
    side = "top" if goal == "R_total" else "bottom"
    incident_power = float(incident_power_3d(config))
    weights = np.zeros(len(modes), dtype=np.float64)
    for index, mode in enumerate(modes):
        if mode.side != side or not _mode_carries_outward_power(mode):
            continue
        weights[index] = float(
            _mode_power_at_boundary(mode, config, 1.0 + 0.0j)
            / incident_power
        )
    if np.any(weights < -1.0e-14) or not np.all(np.isfinite(weights)):
        raise RuntimeError("DtN power goal produced invalid modal weights.")
    return np.maximum(weights, 0.0)


def dtn_power_goal_value(
    config,
    modes,
    auxiliary_values: np.ndarray,
    incident_projections,
    *,
    goal: str,
) -> float:
    metrics = _port_power_metrics(
        config,
        list(modes),
        np.asarray(auxiliary_values, dtype=np.complex128),
        [complex(value) for value in incident_projections],
    )
    return float(metrics[goal])


def build_dtn_power_goal_gradient(
    state: PETSc.Vec,
    config,
    goal_context: dict[str, Any],
    *,
    goal: str,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Build ``g`` such that ``dJ(x)[dx] = Re(g^H dx)``."""

    modes = list(goal_context["modes"])
    auxiliary = np.asarray(
        goal_context["auxiliary_values"], dtype=np.complex128
    )
    incident = np.asarray(
        goal_context["incident_projections"], dtype=np.complex128
    )
    n_fe = int(goal_context["num_fem_dofs_after_mpc"])
    if auxiliary.shape != incident.shape or len(modes) != len(auxiliary):
        raise ValueError("DtN goal context arrays are not shape-compatible.")
    if state.getSize() != n_fe + len(auxiliary):
        raise ValueError("DtN goal context does not match the augmented system.")

    weights = _normalized_goal_weights(config, modes, goal)
    outgoing = auxiliary.copy()
    for index, mode in enumerate(modes):
        if mode.side == "top":
            outgoing[index] -= incident[index]
    auxiliary_gradient = 2.0 * weights * outgoing

    gradient = state.duplicate()
    gradient.set(PETSc.ScalarType(0.0))
    row_start, row_end = gradient.getOwnershipRange()
    indices = np.arange(n_fe, n_fe + len(auxiliary), dtype=np.int64)
    owned = (indices >= row_start) & (indices < row_end)
    if np.any(owned):
        gradient.setValues(
            np.asarray(indices[owned], dtype=PETSc.IntType),
            np.asarray(auxiliary_gradient[owned], dtype=PETSc.ScalarType),
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
    gradient.assemble()
    goal_value = float(np.sum(weights * np.abs(outgoing) ** 2))
    return gradient, {
        "goal": goal,
        "goal_value_from_quadratic_form": goal_value,
        "active_modal_count": int(np.count_nonzero(weights > 0.0)),
        "modal_weight_sum": float(np.sum(weights)),
        "gradient_norm": float(gradient.norm()),
        "gradient_convention": "dJ=Re(g^H dx), g_aux=2*w*outgoing_amplitude",
    }


def _normalized_rhs_direction(
    right_hand_side: PETSc.Vec,
) -> PETSc.Vec:
    direction = right_hand_side.copy()
    rhs_norm = float(direction.norm())
    if rhs_norm <= TINY:
        raise ValueError("cannot verify an adjoint with a zero right-hand side")
    direction.scale(PETSc.ScalarType(1.0 / rhs_norm))
    values = direction.getArray()
    row_start, row_end = direction.getOwnershipRange()
    indices = np.arange(row_start, row_end, dtype=np.float64)
    probe = (
        np.cos(0.173 * (indices + 1.0))
        + 1j * np.sin(0.311 * (indices + 1.0))
    ) / math.sqrt(max(direction.getSize(), 1))
    values[:] += PETSc.ScalarType(0.05) * probe
    direction_norm = float(direction.norm())
    direction.scale(PETSc.ScalarType(1.0 / max(direction_norm, TINY)))
    return direction


def verify_hermitian_discrete_adjoint(
    matrix: PETSc.Mat,
    right_hand_side: PETSc.Vec,
    state: PETSc.Vec,
    solver: PETSc.KSP,
    goal_gradient: PETSc.Vec,
    goal_evaluator: Callable[[PETSc.Vec], float],
    *,
    finite_difference_relative_step: float = 1.0e-5,
) -> dict[str, Any]:
    """Solve and independently verify a real functional's complex adjoint."""

    if not np.issubdtype(PETSc.ScalarType, np.complexfloating):
        raise RuntimeError("the DtN discrete adjoint requires complex PETSc scalars")
    if matrix.getSize()[0] != state.getSize():
        raise ValueError("matrix and state sizes do not match")

    conjugated_gradient = goal_gradient.copy()
    conjugated_gradient.getArray()[:] = np.conj(
        goal_gradient.getArray(readonly=True)
    )
    transpose_solution = state.duplicate()
    solver.solveTranspose(conjugated_gradient, transpose_solution)
    transpose_reason = int(solver.getConvergedReason())
    adjoint = transpose_solution.copy()
    adjoint.getArray()[:] = np.conj(
        transpose_solution.getArray(readonly=True)
    )
    adjoint_residual = _linear_residual(
        matrix, goal_gradient, adjoint, hermitian=True
    )

    direction = _normalized_rhs_direction(right_hand_side)
    rhs_norm = float(right_hand_side.norm())
    step = float(finite_difference_relative_step) * rhs_norm
    rhs_minus = right_hand_side.copy()
    rhs_plus = right_hand_side.copy()
    rhs_minus.axpy(PETSc.ScalarType(-step), direction)
    rhs_plus.axpy(PETSc.ScalarType(step), direction)
    state_minus = state.duplicate()
    state_plus = state.duplicate()
    solver.solve(rhs_minus, state_minus)
    minus_reason = int(solver.getConvergedReason())
    solver.solve(rhs_plus, state_plus)
    plus_reason = int(solver.getConvergedReason())
    minus_residual = _linear_residual(matrix, rhs_minus, state_minus)
    plus_residual = _linear_residual(matrix, rhs_plus, state_plus)

    goal_minus = float(goal_evaluator(state_minus))
    goal_plus = float(goal_evaluator(state_plus))
    finite_difference = (goal_plus - goal_minus) / (2.0 * step)
    tangent = state_plus.copy()
    tangent.axpy(PETSc.ScalarType(-1.0), state_minus)
    tangent.scale(PETSc.ScalarType(1.0 / (2.0 * step)))
    direct_derivative = float(np.real(goal_gradient.dot(tangent)))
    adjoint_derivative = float(np.real(adjoint.dot(direction)))
    direct_adjoint_relative_error = _relative_difference(
        direct_derivative, adjoint_derivative
    )
    finite_difference_relative_error = _relative_difference(
        finite_difference, adjoint_derivative
    )

    passed = bool(
        transpose_reason > 0
        and minus_reason > 0
        and plus_reason > 0
        and adjoint_residual["relative_residual"] <= 1.0e-9
        and minus_residual["relative_residual"] <= 1.0e-9
        and plus_residual["relative_residual"] <= 1.0e-9
        and direct_adjoint_relative_error <= 1.0e-8
        and finite_difference_relative_error <= 1.0e-7
    )
    report = {
        "pass": passed,
        "actual_discrete_system": True,
        "complex_adjoint_equation": "A^H z = g",
        "adjoint_solve_method": (
            "z=conj(KSPSolveTranspose(conj(g))); reuse_forward_direct_factor"
        ),
        "forward_factor_reused": True,
        "matrix_rows": int(matrix.getSize()[0]),
        "mpi_size": int(matrix.getComm().getSize()),
        "transpose_converged_reason": transpose_reason,
        "minus_converged_reason": minus_reason,
        "plus_converged_reason": plus_reason,
        "adjoint_residual": adjoint_residual,
        "minus_primal_residual": minus_residual,
        "plus_primal_residual": plus_residual,
        "finite_difference_relative_step": float(
            finite_difference_relative_step
        ),
        "finite_difference_absolute_step": step,
        "goal_minus": goal_minus,
        "goal_plus": goal_plus,
        "derivative_direct_tangent": direct_derivative,
        "derivative_adjoint": adjoint_derivative,
        "derivative_finite_difference": finite_difference,
        "direct_adjoint_relative_error": direct_adjoint_relative_error,
        "finite_difference_relative_error": finite_difference_relative_error,
    }
    for vector in (
        conjugated_gradient,
        transpose_solution,
        adjoint,
        direction,
        rhs_minus,
        rhs_plus,
        state_minus,
        state_plus,
        tangent,
    ):
        vector.destroy()
    return report


def evaluate_actual_dtn_power_adjoints(
    *,
    linear_system: dict[str, Any],
    dtn_result: dict[str, Any],
    config,
    communicator: MPI.Intracomm,
    official_summary: dict[str, Any],
    goals: tuple[str, ...] = SUPPORTED_GOALS,
) -> dict[str, Any]:
    """Evaluate actual discrete adjoints while forward objects are alive."""

    goal_context = dtn_result.get("goal_context")
    if not isinstance(goal_context, dict):
        raise RuntimeError("the solved DtN system did not retain goal context")
    matrix = linear_system["A"]
    right_hand_side = linear_system["b"]
    state = linear_system["x"]
    solver = linear_system["ksp"]
    n_fe = int(goal_context["num_fem_dofs_after_mpc"])
    n_aux = len(goal_context["modes"])

    goal_reports: dict[str, Any] = {}
    for goal in goals:
        gradient, metadata = build_dtn_power_goal_gradient(
            state, config, goal_context, goal=goal
        )

        def evaluate(candidate: PETSc.Vec, selected_goal: str = goal) -> float:
            auxiliary = _gather_auxiliary_values(
                candidate, n_fe, n_aux, communicator
            )
            return dtn_power_goal_value(
                config,
                goal_context["modes"],
                auxiliary,
                goal_context["incident_projections"],
                goal=selected_goal,
            )

        verification = verify_hermitian_discrete_adjoint(
            matrix,
            right_hand_side,
            state,
            solver,
            gradient,
            evaluate,
        )
        official_value = float(official_summary[goal])
        functional_value = float(metadata["goal_value_from_quadratic_form"])
        official_closure = abs(functional_value - official_value)
        goal_reports[goal] = {
            **metadata,
            **verification,
            "official_summary_value": official_value,
            "official_functional_absolute_closure": official_closure,
            "pass": bool(
                verification["pass"]
                and official_closure
                <= 1.0e-11 * max(abs(official_value), 1.0)
            ),
        }
        gradient.destroy()

    passed = all(report["pass"] for report in goal_reports.values())
    return {
        "schema_version": "task035.actual-dtn-discrete-adjoint.v1",
        "status": (
            "actual_discrete_dtn_adjoint_pass"
            if passed
            else "actual_discrete_dtn_adjoint_fail"
        ),
        "pass": passed,
        "canonical": False,
        "production_qualified": False,
        "ordinary_default_changed": False,
        "official_goals": list(goals),
        "complex_conjugation": "Hermitian A^H, never plain transpose",
        "normalization": goal_context["normalization"],
        "field_gather": False,
        "auxiliary_scalar_gather_only": True,
        "goals": goal_reports,
    }


def run_target_actual_dtn_adjoint(
    out_dir: Path,
    *,
    degree: int = 2,
    h_nm: float = 50.0,
    polarization_kind: str = "s",
    mesh_cell_type: str = "tetrahedron",
    progress_observer=None,
    mesh_data_override=None,
) -> dict[str, Any]:
    """Run one low-cost Task034 target solve and its actual R/T adjoints."""

    from src.common.config_3d import target_stage4_config
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    captured: dict[str, Any] = {}

    def progress(stage: str, status: str) -> None:
        if progress_observer is not None:
            progress_observer(stage, status)

    def observer(**state) -> None:
        progress("actual_dtn_discrete_adjoint", "begin")
        captured["adjoint"] = evaluate_actual_dtn_power_adjoints(
            linear_system=state["linear_system"],
            dtn_result=state["dtn_result"],
            config=state["config"],
            communicator=state["field"].function_space.mesh.comm,
            official_summary=state["summary"],
        )
        progress("actual_dtn_discrete_adjoint", "end")

    base = target_stage4_config(degree=int(degree), h_nm=float(h_nm))
    config = replace(
        base,
        case_name=f"task035_actual_dtn_adjoint_p{degree}_h{h_nm:g}".replace(
            ".", "p"
        ),
        polarization_kind=polarization_kind,
        custom_polarization=None,
        mesh_cell_type=mesh_cell_type,
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        full3d_reference_export=False,
        direct_release_base_after_augmentation=True,
        unique_output=False,
    )
    progress("actual_dtn_primal_solve", "begin")
    summary = run_stage4b_block_grating_3d_case(
        config,
        out_dir / "primal",
        solution_observer=observer,
        mesh_data_override=mesh_data_override,
    )
    progress("actual_dtn_primal_solve", "end")
    residual = summary.get("linear_system_relative_residual")
    prerequisites = bool(
        summary.get("official_result") is True
        and summary.get("case_status") == "completed"
        and isinstance(residual, (int, float))
        and float(residual) <= 1.0e-9
        and "adjoint" in captured
    )
    adjoint = captured.get("adjoint") or {
        "status": "actual_discrete_dtn_adjoint_not_run",
        "pass": False,
    }
    passed = prerequisites and adjoint["pass"]
    return {
        "schema_version": "task035.target-actual-dtn-adjoint.v1",
        "status": (
            "target_actual_dtn_adjoint_pass"
            if passed
            else "target_actual_dtn_adjoint_fail"
        ),
        "pass": passed,
        "target_identity": {
            "wavelength_nm": 13.5,
            "incidence_theta_deg": 80.0,
            "grazing_angle_deg": 10.0,
            "polarization": polarization_kind.upper(),
            "geometry": "Task034 fixed rectangular block grating",
            "mesh_backend": f"boundary-fitted conforming {mesh_cell_type}",
            "degree": int(degree),
            "h_nm": float(h_nm),
        },
        "primal_prerequisites_pass": prerequisites,
        "primal_summary": summary,
        "adjoint": adjoint,
    }


__all__ = [
    "SUPPORTED_GOALS",
    "build_dtn_power_goal_gradient",
    "dtn_power_goal_value",
    "evaluate_actual_dtn_power_adjoints",
    "run_target_actual_dtn_adjoint",
    "verify_hermitian_discrete_adjoint",
]
