"""Exactly one residual refinement in the conditional neural parameter space."""

from time import monotonic
import numpy as np
from scipy.sparse.linalg import lsmr
from src.solvers.ftt_conditional_core import CoreBudgetStop


def true_pair(op, b, delta, initial_norm=None, coordinate_transform=None):
    residual = b - op.B(delta)
    adjoint = op.BH(residual)
    initial = op.BH(b) if initial_norm is None or coordinate_transform is not None else None
    g0 = np.linalg.norm(initial) if initial_norm is None else initial_norm
    normg = float(np.linalg.norm(adjoint))
    record = dict(
        true_linear_residual_norm=float(np.linalg.norm(residual)),
        true_linear_rhs_norm=float(np.linalg.norm(b)),
        true_adjoint_residual_norm=normg,
        true_adjoint_initial_norm=float(g0),
        true_adjoint_residual_relative=normg / float(g0) if g0 != 0 else None,
        initial_adjoint_strict_zero=bool(g0 == 0),
        parameter_increment_norm=float(np.linalg.norm(delta)),
    )
    if coordinate_transform is not None:
        transformed = float(np.linalg.norm(coordinate_transform.adjoint(adjoint)))
        transformed_initial = float(np.linalg.norm(coordinate_transform.adjoint(initial)))
        record.update(
            coordinate_adjoint_residual_norm=transformed,
            coordinate_adjoint_initial_norm=transformed_initial,
            coordinate_adjoint_residual_relative=transformed/transformed_initial if transformed_initial else None,
            coordinate_transform_sha256=coordinate_transform.sha256,
            original_coordinates_used_for_quality=True,
        )
    return record, residual


def segment(op, b, maxiter, tolerance, coordinate_transform=None):
    began = monotonic()
    result = lsmr(
        op.operator() if coordinate_transform is None else coordinate_transform.operator(op),
        b,
        damp=0,
        atol=tolerance,
        btol=tolerance,
        conlim=1e12,
        maxiter=maxiter,
        x0=np.zeros(op.size, dtype=np.complex128),
    )
    solved, stop, iters, nr, na, normA, condA, normx = result
    if coordinate_transform is not None:
        coordinate_transform.last_solve_y = solved.copy()
    delta = solved if coordinate_transform is None else coordinate_transform.forward(solved)
    pair, residual = true_pair(op, b, delta, coordinate_transform=coordinate_transform)
    record = dict(
        pair,
        stop_code=int(stop),
        iterations=int(iters),
        maxiter=maxiter,
        atol=tolerance,
        btol=tolerance,
        damp=0,
        conlim=1e12,
        reported_normr=float(nr),
        reported_normar=float(na),
        reported_normA=float(normA),
        reported_condA=float(condA),
        reported_normx=float(normx),
        seconds=monotonic() - began,
        returned_solver_coordinate="delta" if coordinate_transform is None else "y",
        original_delta_norm=float(np.linalg.norm(delta)),
        solver_coordinate_norm=float(np.linalg.norm(solved)),
    )
    return delta, record, residual


def solve_refined(
    op,
    b,
    *,
    iteration_allowance,
    persist_first,
    resume_first=None,
    seconds_per_iteration=0.0,
    coordinate_transform=None,
):
    began = monotonic()
    def run_segment(rhs, limit, tol):
        # Ordinary/default calls retain their exact historical API and behavior.
        if coordinate_transform is None:
            return segment(op, rhs, limit, tol)
        return segment(op, rhs, limit, tol, coordinate_transform)

    if resume_first is None:
        delta1, first, residual1 = run_segment(b, min(300, iteration_allowance), 1e-8)
        persist_first(delta1, first, residual1)
    else:
        delta1, first = resume_first
        if coordinate_transform is not None and first.get("coordinate_transform_sha256") != coordinate_transform.sha256:
            raise ValueError("RETAINED_FEATURE_TRANSFORM_IDENTITY_MISMATCH")
        pair, residual1 = true_pair(op, b, delta1, coordinate_transform=coordinate_transform)
        if abs(
            pair["true_linear_residual_norm"] - first["true_linear_residual_norm"]
        ) > 1e-10 * max(1, first["true_linear_rhs_norm"]):
            raise ValueError("RETAINED_FIRST_INCREMENT_BASE_MISMATCH")
    relative = first["true_adjoint_residual_relative"]
    triggered = first["stop_code"] == 7 or (relative is not None and relative > 1e-3)
    second, delta, charged_lost = None, delta1, 0
    reason = (
        "FIRST_SEGMENT_SUFFICIENT" if not triggered else "REFINEMENT_DEFERRED_BY_BUDGET"
    )
    remaining = iteration_allowance - (
        first["iterations"] if resume_first is None else 0
    )
    enough = op.deadline - monotonic() > max(60, 900 * seconds_per_iteration + 20)
    if triggered and enough and remaining >= 900:
        reason = "RESIDUAL_REFINEMENT_COMPLETED"
        try:
            d2, second, _ = run_segment(residual1, 900, 1e-10)
            merged, _ = true_pair(
                op, b, delta1 + d2, first["true_adjoint_initial_norm"], coordinate_transform
            )
            second["merged_true_pair"] = merged
            if (
                merged["true_linear_residual_norm"]
                <= first["true_linear_residual_norm"]
            ):
                delta = delta1 + d2
            else:
                reason = "REFINEMENT_WORSE_FALLBACK_VERIFIED_FIRST"
        except CoreBudgetStop:
            charged_lost = 900
            reason = "REFINEMENT_INTERRUPTED_RETAINED_FIRST_ONLY"
    chosen = first if delta is delta1 else second["merged_true_pair"]
    sufficient = (
        chosen["initial_adjoint_strict_zero"]
        or chosen["true_adjoint_residual_relative"] <= 1e-3
    )
    return delta, dict(
        chosen,
        stop_code=first["stop_code"],
        iterations=(first["iterations"] if resume_first is None else 0)
        + (second["iterations"] if second else 0),
        charged_unretained_iterations=charged_lost,
        first_segment=first,
        second_segment=second,
        refinement_reason=reason,
        first_segment_reused=resume_first is not None,
        inner_quality="INNER_DIAGNOSTIC_SUFFICIENT"
        if sufficient
        else "INNER_ACCURACY_UNRESOLVED",
        chosen_increment="first" if delta is delta1 else "merged",
        counts=op.counts.copy(),
        costs_including_nested_actions=op.costs.copy(),
        solve_and_independent_check_seconds=monotonic() - began,
        original_PDE_pass_from_stop_code=False,
    )
