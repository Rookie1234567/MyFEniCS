from __future__ import annotations

from typing import Any

import numpy as np
from basix.ufl import element
from mpi4py import MPI
from petsc4py import PETSc

from dolfinx import default_real_type, fem
from dolfinx.fem import petsc as fem_petsc

from ..common.config_3d import SimulationConfig3D


def _direct_lu_petsc_options() -> dict[str, Any]:
    """Return the single supported 3D linear solve setting.

    The project is intentionally back to one direct solve path while Stage 4
    physics and diffraction postprocess are being debugged.  This keeps the
    PETSc setup explicit without exposing a user-facing solver profile.
    """
    return {
        "ksp_type": "preonly",
        "pc_type": "lu",
        "ksp_error_if_not_converged": True,
    }

def _available_parallel_lu_solver_type() -> str | None:
    """Return a PETSc LU package that can factor MPI matrices globally."""

    candidates = (
        ("mumps", "mumps"),
        ("superlu_dist", "superlu_dist"),
        ("strumpack", "strumpack"),
    )
    for package_name, solver_type in candidates:
        try:
            if PETSc.Sys.hasExternalPackage(package_name):
                return solver_type
        except Exception:
            continue
    return None

def _prepare_direct_lu_options_for_comm(comm: MPI.Intracomm) -> tuple[dict[str, Any], str | None, str | None]:
    """Make direct solver options explicit and safe for serial or MPI runs."""

    petsc_options = _direct_lu_petsc_options()
    if comm.size == 1:
        return petsc_options, None, None
    parallel_lu = _available_parallel_lu_solver_type()
    if parallel_lu is None:
        reason = (
            "MPI direct solve requested, but this PETSc build does not report MUMPS, "
            "SuperLU_DIST, or STRUMPACK. Refusing to run preonly+lu because it can "
            "produce partition-dependent local-factorization results."
        )
        return petsc_options, None, reason
    if parallel_lu is not None:
        petsc_options["pc_factor_mat_solver_type"] = parallel_lu
    return petsc_options, parallel_lu, None

def _pc_factor_solver_type(pc) -> str | None:
    try:
        return str(pc.getFactorSolverType())
    except Exception:
        return None

def _ksp_reason_name(reason: int) -> str:
    for name in dir(PETSc.KSP.ConvergedReason):
        if name.startswith("_"):
            continue
        try:
            if int(getattr(PETSc.KSP.ConvergedReason, name)) == reason:
                return name
        except (TypeError, ValueError):
            continue
    return str(reason)

def _petsc_matrix_stats(A) -> dict[str, Any]:
    A.assemble()
    rows, cols = A.getSize()
    info = A.getInfo()
    matrix_norm_frobenius = _petsc_object_norm(A, ("NORM_FROBENIUS", "FROBENIUS"))
    matrix_norm_infinity = _petsc_object_norm(A, ("NORM_INFINITY", "INFINITY"))
    nnz_used = info.get("nz_used")
    average_nnz_per_row = None
    memory_estimate_bytes = None
    if nnz_used is not None and rows > 0:
        average_nnz_per_row = float(nnz_used) / float(rows)
        # Rough AIJ/CSR storage estimate: complex128 value, column index, and
        # row pointer. PETSc's own memory field can be zero for some builds.
        memory_estimate_bytes = float(nnz_used) * (16.0 + 8.0) + float(rows + 1) * 8.0
    return {
        "matrix_rows": int(rows),
        "matrix_cols": int(cols),
        "matrix_nnz_used": float(nnz_used) if nnz_used is not None else None,
        "matrix_average_nnz_per_row": average_nnz_per_row,
        "matrix_memory_bytes": float(info.get("memory")) if info.get("memory") is not None else None,
        "matrix_memory_estimate_bytes": memory_estimate_bytes,
        "matrix_norm_frobenius": matrix_norm_frobenius,
        "matrix_norm_infinity": matrix_norm_infinity,
    }

def _petsc_object_norm(obj, names: tuple[str, ...]) -> float | None:
    for name in names:
        norm_type = getattr(PETSc.NormType, name, None)
        if norm_type is None:
            continue
        try:
            return float(obj.norm(norm_type))
        except Exception:
            continue
    try:
        return float(obj.norm())
    except Exception:
        return None

def _assembled_rhs_norm(L) -> float | None:
    """Assemble the original, unconstrained RHS for serial/MPI comparison."""

    try:
        vec = fem_petsc.assemble_vector(fem.form(L))
        vec.ghostUpdate(addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE)
        return _petsc_object_norm(vec, ("NORM_2",))
    except Exception:
        return None

def _linear_system_diagnostics(A, b, x) -> dict[str, float | None]:
    """Measure the actually solved PETSc system after MPC assembly."""

    rhs_norm = _petsc_object_norm(b, ("NORM_2",))
    solution_norm = _petsc_object_norm(x, ("NORM_2",))
    residual_norm = None
    relative_residual = None
    try:
        residual = b.duplicate()
        A.mult(x, residual)
        residual.axpy(PETSc.ScalarType(-1.0), b)
        residual_norm = _petsc_object_norm(residual, ("NORM_2",))
        if residual_norm is not None and rhs_norm is not None:
            relative_residual = float(residual_norm / max(rhs_norm, 1.0e-30))
    except Exception:
        residual_norm = None
        relative_residual = None
    return {
        "linear_system_rhs_norm": rhs_norm,
        "linear_system_solution_norm": solution_norm,
        "linear_system_residual_norm": residual_norm,
        "linear_system_relative_residual": relative_residual,
    }

def _log_matrix_stats(matrix_stats: dict[str, Any], log) -> None:
    log(f"matrix rows = {matrix_stats['matrix_rows']}")
    log(f"matrix cols = {matrix_stats['matrix_cols']}")
    log(f"matrix nnz used = {matrix_stats['matrix_nnz_used']}")
    if matrix_stats["matrix_average_nnz_per_row"] is not None:
        log(f"average nnz per row = {matrix_stats['matrix_average_nnz_per_row']:.2f}")
    log(f"PETSc matrix memory bytes = {matrix_stats['matrix_memory_bytes']}")
    log(f"estimated AIJ matrix memory bytes = {matrix_stats['matrix_memory_estimate_bytes']}")
    log(f"matrix Frobenius norm = {matrix_stats['matrix_norm_frobenius']}")
    log(f"matrix infinity norm = {matrix_stats['matrix_norm_infinity']}")

def _create_nedelec_space(msh, cfg: SimulationConfig3D):
    curl_el = element("N1curl", msh.basix_cell(), cfg.nedelec_degree, dtype=default_real_type)
    return fem.functionspace(msh, curl_el)
