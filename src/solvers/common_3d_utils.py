from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

try:
    import resource
except ImportError:  # pragma: no cover - Windows host fallback; Docker/Linux has resource.
    resource = None

from mpi4py import MPI
from petsc4py import PETSc

from ..common.config_3d import NUMERICAL_SANITY_ONLY, SimulationConfig3D
from .solve_vector_maxwell import _json_default


def _start_timed_stage(comm) -> float:
    comm.barrier()
    return time.perf_counter()

def _finish_timed_stage(comm, timings: dict[str, float], name: str, started: float, log) -> None:
    local_elapsed = time.perf_counter() - started
    elapsed = float(comm.allreduce(local_elapsed, op=MPI.MAX))
    timings[name] = elapsed
    log(f"{name} seconds = {elapsed:.3f}")

def _max_rss_mb() -> float | None:
    if resource is None:
        return None
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # Linux reports ru_maxrss in KiB; macOS reports bytes. The Docker runtime
    # used for this project is Linux, but keep the conversion harmless elsewhere.
    if sys.platform == "darwin":
        return float(usage.ru_maxrss) / (1024.0 * 1024.0)
    return float(usage.ru_maxrss) / 1024.0

def _global_max_rss_mb(comm) -> float | None:
    local = _max_rss_mb()
    if local is None:
        return None
    return float(comm.allreduce(local, op=MPI.MAX))

def _swap_used_mb() -> float | None:
    """Return current Linux swap use in MB when /proc/meminfo is available."""

    meminfo = Path("/proc/meminfo")
    if not meminfo.exists():
        return None
    values: dict[str, float] = {}
    try:
        lines = meminfo.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None
    for line in lines:
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        parts = rest.strip().split()
        if not parts:
            continue
        try:
            values[key] = float(parts[0]) / 1024.0
        except ValueError:
            continue
    if "SwapTotal" not in values or "SwapFree" not in values:
        return None
    return max(values["SwapTotal"] - values["SwapFree"], 0.0)

def _progress_matrix_fields(matrix_stats: dict[str, Any] | None) -> dict[str, Any]:
    if not matrix_stats:
        return {}
    return {
        "matrix_rows": matrix_stats.get("matrix_rows"),
        "matrix_cols": matrix_stats.get("matrix_cols"),
        "matrix_nnz_used": matrix_stats.get("matrix_nnz_used"),
        "matrix_nnz_allocated": matrix_stats.get("matrix_nnz_allocated"),
        "matrix_average_nnz_per_row": matrix_stats.get("matrix_average_nnz_per_row"),
        "matrix_memory_mb": matrix_stats.get("matrix_memory_mb"),
        "matrix_memory_estimate_mb": matrix_stats.get("matrix_memory_estimate_mb"),
    }

def _write_progress_event(
    out_dir: Path,
    comm,
    *,
    stage: str,
    status: str,
    started: float | None = None,
    dofs: int | None = None,
    constraints: int | None = None,
    matrix_stats: dict[str, Any] | None = None,
    petsc_options: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append a rank-0 progress checkpoint that survives hard solver failures.

    This intentionally does not call a barrier.  The event marks the latest
    reached stage before operations such as KSPSetUp/LU factorization, where a
    process may be killed before a normal summary can be written.
    """

    try:
        local_rss = _max_rss_mb()
        max_rss = None if local_rss is None else float(comm.allreduce(local_rss, op=MPI.MAX))
    except Exception:
        max_rss = _max_rss_mb()
    if comm.rank != 0:
        return
    payload: dict[str, Any] = {
        "time_wall": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stage": stage,
        "status": status,
        "elapsed_seconds": None if started is None else time.perf_counter() - started,
        "rank_count": comm.size,
        "max_rss_mb": max_rss,
        "swap_used_mb": _swap_used_mb(),
        "dofs": dofs,
        "floquet_constraints": constraints,
    }
    payload.update(_progress_matrix_fields(matrix_stats))
    if petsc_options is not None:
        payload["petsc_options"] = {str(key): value for key, value in petsc_options.items()}
    if extra:
        payload.update(extra)
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "progress_3d.jsonl").open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=False, default=_json_default) + "\n")

def _log_solver_summary(summary: dict[str, Any], log) -> None:
    log("Linear solve summary:")
    log(f"  method               = {summary['linear_solve_method']}")
    log(f"  ksp_type             = {summary.get('actual_ksp_type')}")
    log(f"  pc_type              = {summary.get('actual_pc_type')}")
    log(f"  pc factor solver    = {summary.get('actual_pc_factor_solver_type')}")
    log(f"  converged            = {summary['ksp_converged']}")
    log(f"  converged reason     = {summary['ksp_converged_reason']}")
    log(f"  reason name          = {summary['ksp_converged_reason_name']}")
    log(f"  iterations           = {summary['ksp_iterations']}")
    residual = summary["solver_residual_norm"]
    if residual is None:
        log("  residual norm        = None")
    else:
        log(f"  residual norm        = {residual:.6e}")
    max_rss = summary["max_rss_mb"]
    if max_rss is None:
        log("  max RSS across ranks = None")
    else:
        log(f"  max RSS across ranks = {max_rss:.1f} MB")
    log(f"  official result      = {summary['official_result']}")
    log(f"  diagnostic only      = {summary['diagnostic_only']}")
    log(f"  validation role      = {summary.get('validation_role')}")
    log(f"  physical benchmark  = {summary.get('physical_benchmark_candidate')}")
    log(f"  case status          = {summary['case_status']}")

def _write_case_outputs(out_dir: Path, summary: dict[str, Any], log_lines: list[str], comm) -> None:
    if comm.rank == 0:
        (out_dir / "run_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        (out_dir / "solver_log.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
        if summary.get("diagnostic_only"):
            (out_dir / "NO_OFFICIAL_FIELD_OUTPUT.txt").write_text(
                "This case did not produce official field output because the solver did not produce a valid solution.\n"
                "Read run_summary.json and solver_log.txt for the failure reason.\n",
                encoding="utf-8",
            )
        else:
            (out_dir / "NO_OFFICIAL_FIELD_OUTPUT.txt").unlink(missing_ok=True)

def _clear_official_field_outputs(out_dir: Path, comm) -> None:
    if comm.rank == 0:
        patterns = (
            "fields_3d_for_paraview*.vtu",
            "fields_3d_for_paraview_parallel.pvd",
            "E_3d_numerical.bp",
            "H_3d_A_per_m_from_curl.bp",
            "vtx_3d_warning.txt",
        )
        for pattern in patterns:
            for path in out_dir.glob(pattern):
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink(missing_ok=True)
    comm.barrier()

def _stage_label(cfg: SimulationConfig3D) -> str:
    if cfg.stage_case == "stage1_airbox":
        return "stage1_3d_airbox"
    if cfg.stage_case.startswith("stage4_"):
        return f"stage4_3d_{cfg.stage_case.removeprefix('stage4_')}"
    return f"stage2_3d_{cfg.stage_case}"

def _summary_base_fields(cfg: SimulationConfig3D, comm: MPI.Intracomm) -> dict[str, Any]:
    """Small duplicated-at-top fields used by test scripts and reports.

    The complete configuration remains under ``summary["config"]``.  These
    top-level copies keep validation scripts simple and avoid fragile lookups
    through the nested JSON structure.
    """
    physical_benchmark_candidate = cfg.validation_role != NUMERICAL_SANITY_ONLY
    physical_benchmark_note = (
        "Code-path or numerical sanity result only; do not use as a physical benchmark."
        if not physical_benchmark_candidate
        else "Candidate physical benchmark; verify against Fresnel, zero contrast, and mesh convergence."
    )
    return {
        "stage_case": cfg.stage_case,
        "geometry_kind": cfg.geometry_kind,
        "validation_role": cfg.validation_role,
        "physical_benchmark_candidate": physical_benchmark_candidate,
        "physical_benchmark_note": physical_benchmark_note,
        "substrate_material_label": cfg.substrate_material_label,
        "grating_material_label": cfg.grating_material_label,
        "lambda0_nm": cfg.lambda0,
        "n_substrate_complex": [cfg.substrate_index.real, cfg.substrate_index.imag],
        "n_grating_complex": [cfg.grating_index.real, cfg.grating_index.imag],
        "mpi_size": comm.size,
        "mpi_rank": comm.rank,
        "mesh_target_size": cfg.mesh_target_size,
        "mesh_cell_type": cfg.mesh_cell_type,
        "mesh_cell_type_resolved": cfg.mesh_cell_type_resolved,
        "mesh_spacing_mode": cfg.mesh_spacing_mode,
        "mesh_spacing_mode_requested": cfg.mesh_spacing_mode_requested,
        "mesh_refined_size": cfg.mesh_refined_size,
        "mesh_refinement_radius": cfg.mesh_refinement_radius,
        "floquet_constraint_mode_requested": cfg.floquet_constraint_mode_requested,
        "nedelec_degree": cfg.nedelec_degree,
        "visualization_degree": cfg.visualization_degree,
        "incident_theta_deg": cfg.incident_theta_deg,
        "incident_phi_deg": cfg.incident_phi_deg,
        "polarization_kind": cfg.polarization_kind,
        "length_unit": "nm",
        "electric_field_unit": "V/m",
        "magnetic_field_unit": "A/m",
    }
