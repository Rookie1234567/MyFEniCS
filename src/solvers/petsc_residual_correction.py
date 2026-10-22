"""One residual-correction step using an already configured PETSc KSP."""

from __future__ import annotations

from typing import Any

import numpy as np
from petsc4py import PETSc


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
