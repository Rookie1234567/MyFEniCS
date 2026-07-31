from __future__ import annotations

import os
import shutil
from typing import Any

from basix.ufl import element
from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from dolfinx import default_real_type, fem
from dolfinx.fem import petsc as fem_petsc

from ..common.config_3d import SimulationConfig3D


class DirectSolveFailure(RuntimeError):
    """Carry PETSc objects far enough to write a diagnostic summary."""

    def __init__(
        self,
        message: str,
        *,
        failure_stage: str,
        petsc_error: BaseException,
        A=None,
        b=None,
        x=None,
        ksp=None,
        solver_backend: str | None = None,
        timing_details: dict[str, Any] | None = None,
        extra_summary: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.failure_stage = failure_stage
        self.petsc_error = petsc_error
        self.A = A
        self.b = b
        self.x = x
        self.ksp = ksp
        self.solver_backend = solver_backend
        self.timing_details = timing_details or {}
        self.extra_summary = extra_summary or {}

    def cleanup(self) -> None:
        """Collectively release retained PETSc diagnostics, safely and idempotently."""

        for name in ("ksp", "x", "b", "A"):
            obj = getattr(self, name, None)
            if obj is not None and getattr(obj, "handle", 0):
                obj.destroy()
            setattr(self, name, None)


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


def _has_petsc_package(package_name: str) -> bool:
    try:
        return bool(PETSc.Sys.hasExternalPackage(package_name))
    except Exception:
        return False


def _mumps_ooc_minimal_options() -> dict[str, Any]:
    return {
        "pc_factor_mat_solver_type": "mumps",
        "mat_mumps_icntl_22": 1,
        "mat_mumps_icntl_14": 80,
    }


def _mumps_blr_minimal_options() -> dict[str, Any]:
    """Return the reviewed MUMPS BLR direct-factorization fallback."""

    return {
        "pc_factor_mat_solver_type": "mumps",
        "mat_mumps_icntl_35": 1,
        "mat_mumps_cntl_7": 1.0e-5,
        "mat_mumps_icntl_14": 80,
    }


def _available_parallel_lu_solver_type() -> str | None:
    """Return the one supported MPI sparse direct solver for the live code path."""

    try:
        if PETSc.Sys.hasExternalPackage("mumps"):
            return "mumps"
    except Exception:
        return None
    return None


def _apply_petsc_option_dict(options: dict[str, Any], extra_options: dict[str, Any]) -> None:
    """Merge user/PETSc options without dropping falsey but meaningful values."""

    for key, value in extra_options.items():
        clean_key = str(key).lstrip("-")
        if not clean_key:
            continue
        if clean_key == "log_view":
            continue
        options[clean_key] = "" if value is None else value


def _apply_global_petsc_options(cfg: SimulationConfig3D, petsc_options: dict[str, Any]) -> None:
    """Set PETSc process-global options such as -log_view.

    KSP options are also copied into ``petsc_options`` because the actual KSPs
    use stage-specific prefixes.
    """

    opts = PETSc.Options()
    if cfg.petsc_log_view or "log_view" in cfg.petsc_extra_options:
        opts["log_view"] = ""
    if cfg.petsc_ksp_view or "ksp_view" in cfg.petsc_extra_options:
        petsc_options["ksp_view"] = ""


def _prepare_direct_lu_options_for_comm(
    comm: MPI.Intracomm,
    cfg: SimulationConfig3D | None = None,
) -> tuple[dict[str, Any], str | None, str | None]:
    """Make direct solver options explicit and safe for serial or MPI runs.

    The public code path exposes normal LU, MUMPS out-of-core LU, and the
    reviewed MUMPS BLR compressed direct factorization. BLR remains a direct
    fallback; it must not be presented as the qualified iterative solver.
    """

    petsc_options = _direct_lu_petsc_options()
    profile = "default" if cfg is None else cfg.petsc_direct_solver_profile_requested

    selected_solver: str | None = None
    if profile == "mumps_ooc":
        if not _has_petsc_package("mumps"):
            return (
                petsc_options,
                None,
                "PETSc was asked to use MUMPS out-of-core, but this build does not report MUMPS.",
            )
        selected_solver = "mumps"
        petsc_options.update(_mumps_ooc_minimal_options())
    elif profile == "mumps_blr":
        if not _has_petsc_package("mumps"):
            return (
                petsc_options,
                None,
                "PETSc was asked to use MUMPS BLR, but this build does not report MUMPS.",
            )
        selected_solver = "mumps"
        petsc_options.update(_mumps_blr_minimal_options())
    elif profile != "default":
        return (
            petsc_options,
            None,
            (f"Unsupported PETSc direct solver profile '{profile}'. Use 'default', 'mumps_ooc', or 'mumps_blr'."),
        )

    if cfg is not None:
        _apply_petsc_option_dict(petsc_options, cfg.petsc_extra_options)

    explicitly_requested_solver = petsc_options.get("pc_factor_mat_solver_type")
    if selected_solver is None and explicitly_requested_solver:
        requested_solver = str(explicitly_requested_solver).strip().lower()
        distributed_packages = {
            "mumps",
            "superlu_dist",
            "pastix",
            "strumpack",
            "mkl_cpardiso",
        }
        if comm.size > 1 and requested_solver not in distributed_packages:
            return (
                petsc_options,
                None,
                f"Explicit factor solver '{requested_solver}' is not approved for the MPI direct path.",
            )
        if not _has_petsc_package(requested_solver):
            return (
                petsc_options,
                None,
                f"PETSc does not report the explicitly requested factor solver '{requested_solver}'.",
            )
        selected_solver = requested_solver

    if comm.size == 1:
        if selected_solver is not None:
            petsc_options["pc_factor_mat_solver_type"] = selected_solver
        if cfg is not None:
            _apply_global_petsc_options(cfg, petsc_options)
        return petsc_options, selected_solver, None
    if selected_solver is not None:
        petsc_options["pc_factor_mat_solver_type"] = selected_solver
        if cfg is not None:
            _apply_global_petsc_options(cfg, petsc_options)
        return petsc_options, selected_solver, None
    parallel_lu = _available_parallel_lu_solver_type()
    if parallel_lu is None:
        reason = (
            "MPI direct solve requested, but this PETSc build does not report MUMPS. "
            "Refusing to run preonly+lu because it can "
            "produce partition-dependent local-factorization results."
        )
        return petsc_options, None, reason
    if parallel_lu is not None:
        petsc_options["pc_factor_mat_solver_type"] = parallel_lu
    if cfg is not None:
        _apply_global_petsc_options(cfg, petsc_options)
    return petsc_options, parallel_lu, None


def _prepare_mumps_ooc_runtime(
    cfg: SimulationConfig3D,
    out_dir,
    petsc_options: dict[str, Any],
    comm: MPI.Intracomm,
    log=None,
) -> dict[str, Any]:
    """Pin MUMPS out-of-core files to the current case directory."""

    ooc_enabled = int(petsc_options.get("mat_mumps_icntl_22", 0) or 0) == 1
    if not ooc_enabled:
        return {
            "mumps_ooc_enabled": False,
            "mumps_ooc_tmpdir": None,
            "mumps_ooc_prefix": None,
        }
    if comm.rank == 0:
        ooc_dir = out_dir / "mumps_ooc_files"
        ooc_dir.mkdir(parents=True, exist_ok=True)
        ooc_dir_text = str(ooc_dir)
    else:
        ooc_dir_text = None
    ooc_dir_text = comm.bcast(ooc_dir_text, root=0)
    prefix = f"{cfg.case_name}_mumps_ooc"
    os.environ["MUMPS_OOC_TMPDIR"] = ooc_dir_text
    os.environ["MUMPS_OOC_PREFIX"] = prefix
    if log is not None:
        log(f"MUMPS OOC tmpdir = {ooc_dir_text}")
        log(f"MUMPS OOC prefix = {prefix}")
    return {
        "mumps_ooc_enabled": True,
        "mumps_ooc_tmpdir": ooc_dir_text,
        "mumps_ooc_prefix": prefix,
    }


def _mumps_ooc_directory_status(ooc_info: dict[str, Any] | None) -> dict[str, Any]:
    if not ooc_info or not ooc_info.get("mumps_ooc_tmpdir"):
        return {
            "mumps_ooc_residual_file_count": None,
            "mumps_ooc_residual_file_bytes": None,
            "mumps_ooc_cleaned_by_solver": None,
        }
    directory = os.fspath(ooc_info["mumps_ooc_tmpdir"])
    try:
        paths: list[str] = []
        for root, _, files in os.walk(directory):
            paths.extend(os.path.join(root, filename) for filename in files)
        total = sum(os.path.getsize(path) for path in paths)
        return {
            "mumps_ooc_residual_file_count": len(paths),
            "mumps_ooc_residual_file_bytes": int(total),
            "mumps_ooc_cleaned_by_solver": len(paths) == 0,
        }
    except OSError as exc:
        return {
            "mumps_ooc_residual_file_count": None,
            "mumps_ooc_residual_file_bytes": None,
            "mumps_ooc_cleaned_by_solver": None,
            "mumps_ooc_status_error": str(exc),
        }


def _cleanup_mumps_ooc_directory_on_success(
    ooc_info: dict[str, Any] | None,
    comm: MPI.Intracomm,
    log=None,
) -> dict[str, Any]:
    """Delete MUMPS OOC files after a successful run and report before/after size."""

    before = _mumps_ooc_directory_status(ooc_info)
    result: dict[str, Any] = {
        **before,
        "mumps_ooc_cleanup_policy": "delete_on_success_keep_on_failure",
        "mumps_ooc_cleanup_attempted": False,
        "mumps_ooc_cleanup_success": None,
        "mumps_ooc_cleanup_removed_file_count": 0,
        "mumps_ooc_cleanup_removed_file_bytes": 0,
        "mumps_ooc_cleanup_error": None,
        "mumps_ooc_retained_on_failure": False,
    }
    if not ooc_info or not ooc_info.get("mumps_ooc_tmpdir"):
        return result
    directory = os.fspath(ooc_info["mumps_ooc_tmpdir"])
    if comm.rank == 0:
        result["mumps_ooc_cleanup_attempted"] = True
        result["mumps_ooc_cleanup_removed_file_count"] = before.get("mumps_ooc_residual_file_count") or 0
        result["mumps_ooc_cleanup_removed_file_bytes"] = before.get("mumps_ooc_residual_file_bytes") or 0
        try:
            if os.path.isdir(directory):
                for entry in os.scandir(directory):
                    if entry.is_dir(follow_symlinks=False):
                        shutil.rmtree(entry.path)
                    else:
                        os.remove(entry.path)
            result["mumps_ooc_cleanup_success"] = True
            if log is not None and result["mumps_ooc_cleanup_removed_file_bytes"]:
                removed_mb = result["mumps_ooc_cleanup_removed_file_bytes"] / (1024.0 * 1024.0)
                log(
                    "MUMPS OOC cleanup after successful run: "
                    f"removed {result['mumps_ooc_cleanup_removed_file_count']} files, "
                    f"{removed_mb:.2f} MiB from {directory}"
                )
        except OSError as exc:
            result["mumps_ooc_cleanup_success"] = False
            result["mumps_ooc_cleanup_error"] = str(exc)
            if log is not None:
                log(f"WARNING: MUMPS OOC cleanup failed for {directory}: {exc}")
    result = comm.bcast(result if comm.rank == 0 else None, root=0)
    after = _mumps_ooc_directory_status(ooc_info)
    return {**result, **after}


def _retain_mumps_ooc_directory_on_failure(
    ooc_info: dict[str, Any] | None,
    log=None,
) -> dict[str, Any]:
    """Keep MUMPS OOC files for failed runs and report their location and size."""

    status = _mumps_ooc_directory_status(ooc_info)
    result = {
        **status,
        "mumps_ooc_cleanup_policy": "delete_on_success_keep_on_failure",
        "mumps_ooc_cleanup_attempted": False,
        "mumps_ooc_cleanup_success": None,
        "mumps_ooc_cleanup_removed_file_count": 0,
        "mumps_ooc_cleanup_removed_file_bytes": 0,
        "mumps_ooc_cleanup_error": None,
        "mumps_ooc_retained_on_failure": bool(
            ooc_info and ooc_info.get("mumps_ooc_tmpdir") and (status.get("mumps_ooc_residual_file_count") or 0) > 0
        ),
    }
    if log is not None and result["mumps_ooc_retained_on_failure"]:
        retained_mb = (status.get("mumps_ooc_residual_file_bytes") or 0) / (1024.0 * 1024.0)
        log(
            "MUMPS OOC files retained because the run did not complete successfully: "
            f"{ooc_info.get('mumps_ooc_tmpdir')} "
            f"({status.get('mumps_ooc_residual_file_count')} files, {retained_mb:.2f} MiB)"
        )
    return result


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


def _petsc_matrix_stats(A, *, assemble: bool = True) -> dict[str, Any]:
    if assemble:
        A.assemble()
    rows, cols = A.getSize()
    info = A.getInfo()
    try:
        global_info = A.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
    except Exception:
        global_info = {}
    try:
        local_rows, local_cols = A.getLocalSize()
    except Exception:
        local_rows = local_cols = None
    try:
        row_ownership = A.getOwnershipRange()
    except Exception:
        row_ownership = (None, None)
    try:
        column_ownership = A.getOwnershipRangeColumn()
    except Exception:
        column_ownership = (None, None)
    try:
        row_block_size, column_block_size = A.getBlockSizes()
    except Exception:
        row_block_size = column_block_size = None
    matrix_norm_frobenius = _petsc_object_norm(A, ("NORM_FROBENIUS", "FROBENIUS"))
    matrix_norm_infinity = _petsc_object_norm(A, ("NORM_INFINITY", "INFINITY"))
    maximum_nnz_per_row = None
    try:
        row_offsets, _ = A.getRowIJ(compressed=False)
        local_maximum = (
            int(np.max(np.diff(np.asarray(row_offsets, dtype=np.int64))))
            if len(row_offsets) > 1
            else 0
        )
        maximum_nnz_per_row = int(
            A.getComm().tompi4py().allreduce(local_maximum, op=MPI.MAX)
        )
    except Exception:
        # Some factor matrix implementations do not expose a CSR row view.
        maximum_nnz_per_row = None
    nnz_used = info.get("nz_used")
    nnz_allocated = info.get("nz_allocated")
    average_nnz_per_row = None
    average_allocated_nnz_per_row = None
    memory_estimate_bytes = None
    if nnz_used is not None and rows > 0:
        average_nnz_per_row = float(nnz_used) / float(rows)
        # Rough AIJ/CSR storage estimate: complex128 value, column index, and
        # row pointer. PETSc's own memory field can be zero for some builds.
        memory_estimate_bytes = float(nnz_used) * (16.0 + 8.0) + float(rows + 1) * 8.0
    if nnz_allocated is not None and rows > 0:
        average_allocated_nnz_per_row = float(nnz_allocated) / float(rows)
    matrix_memory_bytes = float(info.get("memory")) if info.get("memory") is not None else None
    return {
        "matrix_rows": int(rows),
        "matrix_cols": int(cols),
        "matrix_nnz_used": float(nnz_used) if nnz_used is not None else None,
        "matrix_nnz_allocated": float(nnz_allocated) if nnz_allocated is not None else None,
        "matrix_nnz_unneeded": (float(info["nz_unneeded"]) if info.get("nz_unneeded") is not None else None),
        "matrix_mallocs": (float(info["mallocs"]) if info.get("mallocs") is not None else None),
        "matrix_type": A.getType(),
        "matrix_local_rows": None if local_rows is None else int(local_rows),
        "matrix_local_cols": None if local_cols is None else int(local_cols),
        "matrix_row_ownership_range": [
            None if row_ownership[0] is None else int(row_ownership[0]),
            None if row_ownership[1] is None else int(row_ownership[1]),
        ],
        "matrix_column_ownership_range": [
            None if column_ownership[0] is None else int(column_ownership[0]),
            None if column_ownership[1] is None else int(column_ownership[1]),
        ],
        "matrix_row_block_size": (None if row_block_size is None else int(row_block_size)),
        "matrix_column_block_size": (None if column_block_size is None else int(column_block_size)),
        "matrix_average_nnz_per_row": average_nnz_per_row,
        "matrix_maximum_nnz_per_row": maximum_nnz_per_row,
        "matrix_average_allocated_nnz_per_row": average_allocated_nnz_per_row,
        "matrix_memory_bytes": matrix_memory_bytes,
        "matrix_memory_mb": None if matrix_memory_bytes is None else matrix_memory_bytes / (1024.0 * 1024.0),
        "matrix_memory_estimate_bytes": memory_estimate_bytes,
        "matrix_memory_estimate_mb": None
        if memory_estimate_bytes is None
        else memory_estimate_bytes / (1024.0 * 1024.0),
        "matrix_norm_frobenius": matrix_norm_frobenius,
        "matrix_norm_infinity": matrix_norm_infinity,
        "matrix_petsc_info": {str(key): float(value) for key, value in info.items()},
        "matrix_petsc_info_global_sum": {str(key): float(value) for key, value in global_info.items()},
    }


def _corrected_mumps_factor_nnz(
    factor_solver_type: str | None,
    raw_infog_9: int | None,
) -> int | None:
    """Decode MUMPS' negative INFOG(9) million-entry representation."""

    if factor_solver_type != "mumps" or raw_infog_9 is None:
        return None
    raw_value = int(raw_infog_9)
    if raw_value >= 0:
        return None
    return int(abs(raw_value) * 1_000_000)


def _petsc_factor_inventory(ksp) -> dict[str, Any]:
    """Return only factor data exposed by the active petsc4py build."""

    inventory: dict[str, Any] = {
        "available": False,
        "factor_solver_type": None,
        "matrix_stats": None,
        "factor_nnz_corrected": None,
        "factor_nnz_corrected_source": None,
        "mumps_raw_infog": {},
        "mumps_raw_rinfog": {},
        "mumps_api_available": False,
        "limitations": [],
    }
    try:
        pc = ksp.getPC()
        inventory["factor_solver_type"] = pc.getFactorSolverType()
        factor = pc.getFactorMatrix()
    except Exception as exc:
        inventory["limitations"].append(f"factor_matrix_unavailable:{type(exc).__name__}")
        return inventory
    try:
        inventory["matrix_stats"] = _petsc_matrix_stats(factor, assemble=False)
        inventory["available"] = True
    except Exception as exc:
        inventory["limitations"].append(f"factor_matrix_stats_unavailable:{type(exc).__name__}")

    if inventory["factor_solver_type"] != "mumps":
        inventory["limitations"].append(
            f"mumps_raw_api_not_applicable_for_factor_solver:{inventory['factor_solver_type']}"
        )
        return inventory
    if not hasattr(factor, "getMumpsInfog"):
        inventory["limitations"].append("mumps_raw_api_not_exposed")
        return inventory
    inventory["mumps_api_available"] = True
    for index in range(1, 41):
        try:
            inventory["mumps_raw_infog"][str(index)] = int(factor.getMumpsInfog(index))
        except Exception:
            continue
    for index in range(1, 21):
        try:
            inventory["mumps_raw_rinfog"][str(index)] = float(factor.getMumpsRinfog(index))
        except Exception:
            continue
    corrected_factor_nnz = _corrected_mumps_factor_nnz(
        inventory["factor_solver_type"],
        inventory["mumps_raw_infog"].get("9"),
    )
    if corrected_factor_nnz is not None:
        inventory["factor_nnz_corrected"] = corrected_factor_nnz
        inventory["factor_nnz_corrected_source"] = (
            "mumps_infog_9_negative_millions"
        )
    inventory["limitations"].append(
        "MUMPS INFOG/RINFOG values are stored by raw index; only negative "
        "INFOG(9) receives the documented million-entry correction."
    )
    return inventory


def _petsc_error_diagnostics(exc: BaseException, ksp=None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "petsc_error_type": type(exc).__name__,
        "petsc_error_message": str(exc),
        "petsc_error_code": getattr(exc, "ierr", None),
        "mumps_infog_1": None,
        "mumps_infog_2": None,
        "mumps_info_1": None,
        "mumps_info_2": None,
    }
    if ksp is None:
        return data
    try:
        pc = ksp.getPC()
        factor = pc.getFactorMatrix()
    except Exception:
        return data
    for name, method_name, idx in (
        ("mumps_infog_1", "getMumpsInfog", 1),
        ("mumps_infog_2", "getMumpsInfog", 2),
        ("mumps_info_1", "getMumpsInfo", 1),
        ("mumps_info_2", "getMumpsInfo", 2),
    ):
        try:
            method = getattr(factor, method_name)
            data[name] = method(idx)
        except Exception:
            data[name] = None
    return data


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

    vec = None
    try:
        vec = fem_petsc.assemble_vector(fem.form(L))
        vec.ghostUpdate(addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE)
        return _petsc_object_norm(vec, ("NORM_2",))
    except Exception:
        return None
    finally:
        if vec is not None:
            vec.destroy()


def _linear_system_diagnostics(A, b, x) -> dict[str, float | None]:
    """Measure the actually solved PETSc system after MPC assembly."""

    rhs_norm = _petsc_object_norm(b, ("NORM_2",))
    solution_norm = _petsc_object_norm(x, ("NORM_2",))
    residual_norm = None
    relative_residual = None
    residual = None
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
    finally:
        if residual is not None:
            residual.destroy()
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
    log(f"matrix nnz allocated = {matrix_stats['matrix_nnz_allocated']}")
    if matrix_stats["matrix_average_nnz_per_row"] is not None:
        log(f"average nnz per row = {matrix_stats['matrix_average_nnz_per_row']:.2f}")
    if matrix_stats["matrix_average_allocated_nnz_per_row"] is not None:
        log(f"average allocated nnz per row = {matrix_stats['matrix_average_allocated_nnz_per_row']:.2f}")
    log(f"PETSc matrix memory bytes = {matrix_stats['matrix_memory_bytes']}")
    log(f"PETSc matrix memory MB = {matrix_stats['matrix_memory_mb']}")
    log(f"estimated AIJ matrix memory bytes = {matrix_stats['matrix_memory_estimate_bytes']}")
    log(f"estimated AIJ matrix memory MB = {matrix_stats['matrix_memory_estimate_mb']}")
    log(f"matrix Frobenius norm = {matrix_stats['matrix_norm_frobenius']}")
    log(f"matrix infinity norm = {matrix_stats['matrix_norm_infinity']}")


def _create_nedelec_space(msh, cfg: SimulationConfig3D):
    if cfg.nedelec_fixed_trace_enabled:
        if "hexahedron" not in str(msh.basix_cell()).lower():
            raise NotImplementedError(
                "the qualified fixed-trace H(curl) element supports "
                "hexahedra only"
            )
        # Accessing the contract fails closed for every pair except the
        # reviewed global p5-trace / p6-interior exact-sequence space.
        _ = cfg.nedelec_fixed_trace_contract
        from .hcurl_fixed_trace_element import (
            fixed_trace_hcurl_ufl_element,
        )

        curl_el = fixed_trace_hcurl_ufl_element(
            cfg.nedelec_trace_degree_resolved,
            cfg.nedelec_interior_degree_resolved,
        )
    else:
        curl_el = element(
            "N1curl",
            msh.basix_cell(),
            cfg.nedelec_degree,
            dtype=default_real_type,
        )
    return fem.functionspace(msh, curl_el)
