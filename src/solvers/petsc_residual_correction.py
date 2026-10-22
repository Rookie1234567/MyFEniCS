"""One residual-correction step using an already configured PETSc KSP."""

from __future__ import annotations

import time
from typing import Any

import numpy as np
from petsc4py import PETSc


def _ksp_telemetry(ksp: PETSc.KSP) -> dict[str, Any]:
    """Snapshot KSP values that a subsequent solve would overwrite."""

    return {
        "converged_reason": int(ksp.getConvergedReason()),
        "iterations": int(ksp.getIterationNumber()),
        "residual_norm": float(ksp.getResidualNorm()),
        "ksp_type": str(ksp.getType()),
        "pc_type": str(ksp.getPC().getType()),
    }


def single_petsc_residual_correction(
    matrix: PETSc.Mat,
    rhs: PETSc.Vec,
    solution: PETSc.Vec,
    ksp: PETSc.KSP,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Return ``solution + delta`` where the same KSP solves ``A delta=b-Ax``.

    The borrowed matrix, RHS, solution, and KSP configuration are not modified.
    The returned vector is newly allocated and owned by the caller.  This
    helper does not assemble a matrix or replace/refactor the KSP operator; it
    applies one correction with the already configured solver.
    """

    residual = rhs.duplicate()
    correction = solution.duplicate()
    corrected = solution.copy()
    try:
        matrix.mult(solution, residual)
        residual.scale(PETSc.ScalarType(-1.0))
        residual.axpy(PETSc.ScalarType(1.0), rhs)
        rhs_norm = float(rhs.norm())
        initial_norm = float(residual.norm())
        initial_relative = initial_norm / max(rhs_norm, 1.0e-30)
        if not np.isfinite(initial_relative):
            raise FloatingPointError("initial explicit residual is non-finite")

        correction.set(PETSc.ScalarType(0.0))
        ksp.solve(residual, correction)
        converged_reason = int(ksp.getConvergedReason())
        if converged_reason <= 0:
            raise RuntimeError(
                "PETSc residual-correction solve did not converge: "
                f"reason={converged_reason}"
            )
        corrected.axpy(PETSc.ScalarType(1.0), correction)

        matrix.mult(corrected, residual)
        residual.axpy(PETSc.ScalarType(-1.0), rhs)
        corrected_norm = float(residual.norm())
        corrected_relative = corrected_norm / max(rhs_norm, 1.0e-30)
        solution_norm = float(solution.norm())
        correction_norm = float(correction.norm())
        if not all(
            np.isfinite(value)
            for value in (
                rhs_norm,
                initial_norm,
                corrected_norm,
                initial_relative,
                corrected_relative,
                solution_norm,
                correction_norm,
            )
        ):
            raise FloatingPointError("residual-correction diagnostics are non-finite")
        diagnostics = {
            "method": "same_ksp_single_residual_correction",
            "matrix_or_rhs_reassembled": False,
            "ksp_operator_replaced": False,
            "ksp_converged_reason": converged_reason,
            "ksp_iterations": int(ksp.getIterationNumber()),
            "rhs_norm": rhs_norm,
            "initial_explicit_residual_norm": initial_norm,
            "initial_relative_to_rhs": initial_relative,
            "correction_norm": correction_norm,
            "relative_correction_norm": correction_norm
            / max(solution_norm, 1.0e-30),
            "corrected_explicit_residual_norm": corrected_norm,
            "corrected_relative_to_rhs": corrected_relative,
        }
        return corrected, diagnostics
    except Exception:
        corrected.destroy()
        raise
    finally:
        residual.destroy()
        correction.destroy()


def single_petsc_residual_correction_in_place(
    matrix: PETSc.Mat | None,
    rhs: PETSc.Vec | None,
    solution: PETSc.Vec | None,
    ksp: PETSc.KSP | None,
    *,
    enabled: bool,
) -> dict[str, Any]:
    """Optionally improve ``solution`` with one same-KSP correction.

    When disabled, this is a strict no-op and does not inspect or touch PETSc
    objects.  When enabled, the caller's vector is only updated after a finite
    explicit residual has strictly decreased.  The borrowed matrix, RHS, and
    KSP operator are never replaced.
    """

    if not enabled:
        return {
            "requested": False,
            "status": "not_requested",
            "ordinary_default_changed": False,
        }
    if matrix is None or rhs is None or solution is None or ksp is None:
        raise ValueError("enabled residual correction requires matrix, RHS, solution, and KSP")

    started = time.perf_counter()
    original_ksp = _ksp_telemetry(ksp)
    corrected: PETSc.Vec | None = None
    report: dict[str, Any] = {
        "requested": True,
        "status": "failed",
        "method": "same_ksp_single_residual_correction",
        "matrix_or_rhs_reassembled": False,
        "ksp_operator_replaced": False,
        "solution_updated": False,
        "original_primal_ksp": original_ksp,
        "source_identity": {
            "implementation": (
                "src.solvers.petsc_residual_correction."
                "single_petsc_residual_correction_in_place"
            ),
        },
    }
    try:
        corrected, diagnostics = single_petsc_residual_correction(
            matrix,
            rhs,
            solution,
            ksp,
        )
        initial_relative = float(diagnostics["initial_relative_to_rhs"])
        corrected_relative = float(diagnostics["corrected_relative_to_rhs"])
        initial_norm = float(diagnostics["initial_explicit_residual_norm"])
        corrected_norm = float(diagnostics["corrected_explicit_residual_norm"])
        rhs_norm = float(diagnostics["rhs_norm"])
        correction_norm = float(diagnostics["correction_norm"])
        correction_relative = float(diagnostics["relative_correction_norm"])
        values = (
            initial_relative,
            corrected_relative,
            initial_norm,
            corrected_norm,
            rhs_norm,
            correction_norm,
            correction_relative,
        )
        if not all(np.isfinite(value) and value >= 0.0 for value in values):
            report["failure_reason"] = "non-finite or negative explicit residual diagnostic"
        elif corrected_relative >= initial_relative:
            report["failure_reason"] = "same-KSP correction did not strictly improve the explicit residual"
        else:
            corrected.copy(solution)
            report["status"] = "passed"
            report["solution_updated"] = True
        report.update(
            {
                "rhs_norm": rhs_norm,
                "initial_condensed_residual_norm": initial_norm,
                "initial_condensed_relative_to_rhs": initial_relative,
                "corrected_condensed_residual_norm": corrected_norm,
                "corrected_condensed_relative_to_rhs": corrected_relative,
                "correction_norm": correction_norm,
                "correction_relative_to_solution": correction_relative,
                "correction_ksp": {
                    "converged_reason": int(diagnostics["ksp_converged_reason"]),
                    "iterations": int(diagnostics["ksp_iterations"]),
                    "residual_norm": _ksp_telemetry(ksp)["residual_norm"],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001 - return an explicit failure diagnostic for every PETSc error.
        report["failure_reason"] = f"{type(exc).__name__}: {exc}"
        report["correction_ksp"] = _ksp_telemetry(ksp)
    finally:
        if corrected is not None:
            corrected.destroy()
        report["elapsed_seconds"] = float(time.perf_counter() - started)

    return report
