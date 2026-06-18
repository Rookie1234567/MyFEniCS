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

import numpy as np
import ufl
from basix.ufl import element
from mpi4py import MPI
from petsc4py import PETSc

from dolfinx import default_real_type, default_scalar_type, fem, geometry
from dolfinx.fem import petsc as fem_petsc

from ..common.analytic_fields_3d import electric_field_code_values, fresnel_reference
from ..common.config_3d import SimulationConfig3D
from ..common.pml_3d import z_pml_tensors
from ..constraints.floquet_3d import DoubleFloquet3DData, build_double_floquet_mpc
from ..geometry.mesh_builder_3d import build_airbox_mesh_3d
from ..postprocessing.postprocess_3d import save_airbox_3d_fields
from .solve_vector_maxwell import _json_default


SUPPORTED_SOLVER_PROFILES = (
    "default",
    "direct",
    "direct_lu",
    "iterative_asm_lu",
    "iterative_asm_lu_overlap2",
    "iterative_asm_ilu",
    "iterative_bjacobi_ilu",
    "iterative_jacobi",
    "iterative_hypre",
)

DIRECT_SOLVER_ALIASES = ("default", "direct", "direct_lu")
EXPERIMENTAL_SOLVER_PROFILES = (
    "iterative_asm_lu",
    "iterative_asm_lu_overlap2",
    "iterative_asm_ilu",
    "iterative_bjacobi_ilu",
    "iterative_jacobi",
)
DISABLED_SOLVER_PROFILES = {
    "iterative_hypre": (
        "hypre BoomerAMG is disabled for this complex Nedelec H(curl) Maxwell "
        "system because it has shown low-level crashes in the current runtime."
    ),
}


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


def _solver_profile_settings(cfg: SimulationConfig3D) -> dict[str, Any]:
    profile = cfg.solver_profile.strip().lower()
    if profile not in SUPPORTED_SOLVER_PROFILES:
        raise ValueError(
            f"Unknown 3D solver_profile={cfg.solver_profile!r}. "
            f"Supported profiles are: {', '.join(SUPPORTED_SOLVER_PROFILES)}."
        )

    if profile in DISABLED_SOLVER_PROFILES:
        return {
            "profile_requested": cfg.solver_profile,
            "profile_resolved": profile,
            "petsc_options": {},
            "reliability": "disabled",
            "experimental": True,
            "disabled": True,
            "disabled_reason": DISABLED_SOLVER_PROFILES[profile],
            "warnings": [
                DISABLED_SOLVER_PROFILES[profile],
                "BoomerAMG is mainly intended for scalar H1-type elliptic problems, "
                "not as a default preconditioner for this complex H(curl) Maxwell system.",
            ],
        }

    if profile in DIRECT_SOLVER_ALIASES:
        return {
            "profile_requested": cfg.solver_profile,
            "profile_resolved": "direct",
            "petsc_options": {
                "ksp_type": "preonly",
                "pc_type": "lu",
                "ksp_error_if_not_converged": True,
            },
            "reliability": "reliable_reference",
            "experimental": False,
            "disabled": False,
            "disabled_reason": None,
            "warnings": [],
        }

    common = {
        "ksp_type": "fgmres",
        "ksp_rtol": cfg.solver_rtol,
        "ksp_atol": cfg.solver_atol,
        "ksp_max_it": cfg.solver_max_it,
        "ksp_error_if_not_converged": False,
    }
    if cfg.solver_monitor:
        common["ksp_monitor"] = None

    if profile == "iterative_asm_lu":
        petsc_options = {
            **common,
            "pc_type": "asm",
            "pc_asm_overlap": 1,
            "sub_ksp_type": "preonly",
            "sub_pc_type": "lu",
        }
    elif profile == "iterative_asm_lu_overlap2":
        petsc_options = {
            **common,
            "pc_type": "asm",
            "pc_asm_overlap": 2,
            "sub_ksp_type": "preonly",
            "sub_pc_type": "lu",
        }
    elif profile == "iterative_asm_ilu":
        petsc_options = {
            **common,
            "pc_type": "asm",
            "pc_asm_overlap": 1,
            "sub_ksp_type": "preonly",
            "sub_pc_type": "ilu",
        }
    elif profile == "iterative_bjacobi_ilu":
        petsc_options = {
            **common,
            "pc_type": "bjacobi",
            "sub_ksp_type": "preonly",
            "sub_pc_type": "ilu",
        }
    elif profile == "iterative_jacobi":
        petsc_options = {
            **common,
            "pc_type": "jacobi",
        }
    else:
        raise AssertionError(f"Unhandled solver profile {profile!r}.")

    warnings = [
        "This iterative solver profile is experimental for the complex 3D H(curl) Maxwell system.",
        "Compare any converged iterative result against the direct solver before using it as a benchmark.",
    ]
    if profile == "iterative_asm_ilu":
        warnings.append("ASM+ILU has been observed to run but not converge for tested degree-2 airbox cases.")
    elif profile == "iterative_bjacobi_ilu":
        warnings.append("Block-Jacobi+ILU has been observed to run but not converge for tested degree-2 airbox cases.")
    elif profile == "iterative_jacobi":
        warnings.append("Jacobi is too weak for this Maxwell system and should be used only as a diagnostic baseline.")
    elif profile == "iterative_asm_lu_overlap2":
        warnings.append("ASM overlap=2 strengthens the preconditioner but increases memory use.")

    return {
        "profile_requested": cfg.solver_profile,
        "profile_resolved": profile,
        "petsc_options": petsc_options,
        "reliability": "experimental_compare_with_direct",
        "experimental": profile in EXPERIMENTAL_SOLVER_PROFILES,
        "disabled": False,
        "disabled_reason": None,
        "warnings": warnings,
    }


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
    }


def _log_matrix_stats(matrix_stats: dict[str, Any], log) -> None:
    log(f"matrix rows = {matrix_stats['matrix_rows']}")
    log(f"matrix cols = {matrix_stats['matrix_cols']}")
    log(f"matrix nnz used = {matrix_stats['matrix_nnz_used']}")
    if matrix_stats["matrix_average_nnz_per_row"] is not None:
        log(f"average nnz per row = {matrix_stats['matrix_average_nnz_per_row']:.2f}")
    log(f"PETSc matrix memory bytes = {matrix_stats['matrix_memory_bytes']}")
    log(f"estimated AIJ matrix memory bytes = {matrix_stats['matrix_memory_estimate_bytes']}")


def _log_solver_summary(summary: dict[str, Any], log) -> None:
    log("Solver summary:")
    log(f"  profile              = {summary['solver_profile']}")
    log(f"  resolved profile     = {summary['solver_profile_resolved']}")
    log(f"  reliability          = {summary['solver_reliability']}")
    log(f"  ksp_type             = {summary.get('actual_ksp_type')}")
    log(f"  pc_type              = {summary.get('actual_pc_type')}")
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


def plane_wave_electric_field(V, cfg: SimulationConfig3D) -> fem.Function:
    field = fem.Function(V, name="E_exact")

    def eval_field(x):
        return electric_field_code_values(cfg, x.T).T

    field.interpolate(eval_field)
    return field


def _sample_field_at_points(function, points: np.ndarray) -> np.ndarray:
    msh = function.function_space.mesh
    comm = msh.comm
    points = np.asarray(points, dtype=np.float64).reshape((-1, 3))
    tree = geometry.bb_tree(msh, msh.topology.dim)
    candidates = geometry.compute_collisions_points(tree, points)
    collisions = geometry.compute_colliding_cells(msh, candidates, points)
    local_indices: list[int] = []
    local_cells: list[int] = []
    for i in range(len(points)):
        links = collisions.links(i)
        if len(links) >= 1:
            local_indices.append(i)
            local_cells.append(int(links[0]))

    if local_indices:
        local_points = points[np.asarray(local_indices, dtype=np.int32)]
        local_values = function.eval(local_points, np.asarray(local_cells, dtype=np.int32))
        local_values = np.asarray(local_values, dtype=np.complex128)
        if local_values.ndim == 1:
            local_values = local_values.reshape((-1, 1))
    else:
        local_values = np.zeros((0, 0), dtype=np.complex128)

    packets = comm.allgather((local_indices, local_values))
    width = 0
    for _, values in packets:
        if values.size:
            width = int(values.shape[1])
            break
    if width == 0:
        raise RuntimeError("No rank could evaluate the requested 3D probe points.")

    values = np.zeros((len(points), width), dtype=np.complex128)
    filled = np.zeros(len(points), dtype=bool)
    for indices, packet_values in packets:
        for row, point_index in enumerate(indices):
            if not filled[point_index]:
                values[int(point_index)] = packet_values[row]
                filled[int(point_index)] = True
    if not np.all(filled):
        missing = np.flatnonzero(~filled)[:5]
        examples = ", ".join(str(points[i].tolist()) for i in missing)
        raise RuntimeError(f"No mesh cell found for {np.count_nonzero(~filled)} 3D probe points: {examples}")
    return values[:, :3]


def _relative_norm_error(actual: np.ndarray, expected: np.ndarray) -> float:
    diff = actual - expected
    denom = max(float(np.linalg.norm(actual)), float(np.linalg.norm(expected)), 1.0e-30)
    return float(np.linalg.norm(diff) / denom)


def _floquet_probe_metrics(floquet_data: DoubleFloquet3DData) -> dict[str, float]:
    stats = floquet_data.orientation_factor_stats
    x_mismatch = float(stats.get("x_max_probe_error", float("nan")))
    y_mismatch = float(stats.get("y_max_probe_error", float("nan")))
    return {
        "floquet_x_face_mismatch": x_mismatch,
        "floquet_y_face_mismatch": y_mismatch,
        "floquet_edge_corner_mismatch": floquet_data.edge_corner_phase_mismatch,
    }


def _pml_probe_metrics(E, cfg: SimulationConfig3D) -> dict[str, float | None]:
    if not cfg.use_pml:
        return {
            "pml_reflection_proxy": None,
            "pml_decay_ratio_top": None,
            "pml_decay_ratio_bottom": None,
        }

    center_x = 0.5 * (cfg.x_min + cfg.x_max)
    center_y = 0.5 * (cfg.y_min + cfg.y_max)
    metrics: dict[str, float | None] = {}
    physical_z = np.linspace(cfg.physical_z_min + 0.15 * (cfg.physical_z_max - cfg.physical_z_min),
                             cfg.physical_z_max - 0.15 * (cfg.physical_z_max - cfg.physical_z_min), 6)
    physical_points = np.asarray([[center_x, center_y, z] for z in physical_z], dtype=np.float64)
    numerical = _sample_field_at_points(E, physical_points)
    exact = electric_field_code_values(cfg, physical_points)
    metrics["pml_reflection_proxy"] = _relative_norm_error(numerical, exact)

    if cfg.pml_top_thickness > 0.0:
        top_inner = np.asarray([[center_x, center_y, cfg.physical_z_max + 0.05 * cfg.pml_top_thickness]])
        top_outer = np.asarray([[center_x, center_y, cfg.domain_z_max - 0.05 * cfg.pml_top_thickness]])
        metrics["pml_decay_ratio_top"] = float(
            np.linalg.norm(_sample_field_at_points(E, top_outer)) / max(np.linalg.norm(_sample_field_at_points(E, top_inner)), 1.0e-30)
        )
    else:
        metrics["pml_decay_ratio_top"] = None

    if cfg.pml_bottom_thickness > 0.0:
        bottom_inner = np.asarray([[center_x, center_y, cfg.physical_z_min - 0.05 * cfg.pml_bottom_thickness]])
        bottom_outer = np.asarray([[center_x, center_y, cfg.domain_z_min + 0.05 * cfg.pml_bottom_thickness]])
        metrics["pml_decay_ratio_bottom"] = float(
            np.linalg.norm(_sample_field_at_points(E, bottom_outer))
            / max(np.linalg.norm(_sample_field_at_points(E, bottom_inner)), 1.0e-30)
        )
    else:
        metrics["pml_decay_ratio_bottom"] = None
    return metrics


def _stage2_reference_metrics(cfg: SimulationConfig3D, field_metrics: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    if cfg.geometry_kind == "fresnel_interface":
        ref = fresnel_reference(cfg)
        metrics.update(
            {
                "R_total": ref["R"],
                "T_total": ref["T"],
                "R_plus_T": ref["R_plus_T"],
                "fresnel_R": ref["R"],
                "fresnel_T": ref["T"],
                "fresnel_R_error": 0.0,
                "fresnel_T_error": 0.0,
                "fresnel_reference": ref,
                "rt_metric_note": "Stage-2 first version uses the analytic Fresnel field as the manufactured reference.",
            }
        )
    elif cfg.use_pml:
        metrics.update(
            {
                "R_total": None,
                "T_total": None,
                "R_plus_T": None,
                "fresnel_R": None,
                "fresnel_T": None,
                "fresnel_R_error": None,
                "fresnel_T_error": None,
            }
        )
    metrics["fresnel_field_relative_max_error"] = field_metrics.get("relative_max_abs_E_error")
    return metrics


def _stage_label(cfg: SimulationConfig3D) -> str:
    if cfg.stage_case == "stage1_airbox":
        return "stage1_3d_airbox"
    return f"stage2_3d_{cfg.stage_case}"


def _build_variational_forms(msh, mesh_data, cfg: SimulationConfig3D, V):
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    dx = ufl.Measure("dx", domain=msh, subdomain_data=mesh_data.cell_tags)
    zero = fem.Constant(msh, np.zeros(3, dtype=default_scalar_type))
    curl_u = ufl.curl(u)
    curl_v = ufl.curl(v)
    a = PETSc.ScalarType(0.0) * ufl.inner(u, v) * dx

    def add_isotropic(tag: int, eps_r: complex):
        return (
            PETSc.ScalarType(1.0 / cfg.mu_r) * ufl.inner(curl_u, curl_v) * dx(tag)
            - cfg.k0**2 * PETSc.ScalarType(eps_r) * ufl.inner(u, v) * dx(tag)
        )

    a += add_isotropic(cfg.tags.air, cfg.eps_r)
    a += add_isotropic(cfg.tags.substrate, cfg.substrate_index**2)

    x = ufl.SpatialCoordinate(msh)
    if cfg.use_pml and cfg.pml_top_thickness > 0.0:
        eps_top, mu_top = z_pml_tensors(x, cfg, "top", cfg.eps_r)
        a += ufl.inner(ufl.inv(mu_top) * curl_u, curl_v) * dx(cfg.tags.top_pml)
        a += -cfg.k0**2 * ufl.inner(eps_top * u, v) * dx(cfg.tags.top_pml)
    if cfg.use_pml and cfg.pml_bottom_thickness > 0.0:
        eps_bottom_background = cfg.substrate_index**2 if cfg.geometry_kind == "fresnel_interface" else cfg.eps_r
        eps_bottom, mu_bottom = z_pml_tensors(x, cfg, "bottom", eps_bottom_background)
        a += ufl.inner(ufl.inv(mu_bottom) * curl_u, curl_v) * dx(cfg.tags.bottom_pml)
        a += -cfg.k0**2 * ufl.inner(eps_bottom * u, v) * dx(cfg.tags.bottom_pml)
    L = ufl.inner(zero, v) * dx
    return a, L


def _z_boundary_facets(mesh_data, cfg: SimulationConfig3D) -> np.ndarray:
    return np.unique(
        np.concatenate(
            [
                np.asarray(mesh_data.facet_tags.find(cfg.tags.z_min), dtype=np.int32),
                np.asarray(mesh_data.facet_tags.find(cfg.tags.z_max), dtype=np.int32),
            ]
        )
    )


def run_airbox_3d_case(cfg: SimulationConfig3D, out_dir: Path) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    comm = MPI.COMM_WORLD
    log_lines: list[str] = []
    timings: dict[str, float] = {}
    start = _start_timed_stage(comm)

    def log(message: str):
        log_lines.append(message)
        if comm.rank == 0:
            PETSc.Sys.Print(message)

    if not np.issubdtype(default_scalar_type, np.complexfloating):
        raise RuntimeError("The 3D Maxwell solver requires complex-mode DOLFINx/PETSc.")

    stage_start = _start_timed_stage(comm)
    # Trigger validation before any expensive setup.
    if cfg.stage_case not in {
        "stage1_airbox",
        "floquet_airbox",
        "pml_airbox",
        "fresnel_interface",
    }:
        raise ValueError(
            "3D stage_case must be 'stage1_airbox', 'floquet_airbox', 'pml_airbox', or 'fresnel_interface'."
        )
    if cfg.use_pml and (cfg.pml_top_thickness <= 0.0 or cfg.pml_bottom_thickness <= 0.0):
        raise ValueError("3D PML cases require positive pml_top_thickness and pml_bottom_thickness.")
    k = cfg.wavevector
    p = cfg.polarization_vector
    dot_k_p = np.dot(k, p)
    _finish_timed_stage(comm, timings, "config_validation", stage_start, log)

    log(f"case = {cfg.case_name}")
    log(f"stage = {_stage_label(cfg)}")
    log(f"geometry kind = {cfg.geometry_kind}")
    log(f"use Floquet xy = {cfg.use_floquet_xy}")
    log(f"use PML = {cfg.use_pml}")
    log(f"PETSc ScalarType = {PETSc.ScalarType}")
    log(f"DOLFINx scalar type = {default_scalar_type}")
    log(f"k0 = {cfg.k0:.12g}")
    log(f"k = {k.tolist()}")
    log(f"polarization = {p.tolist()}")
    log(f"dot(k, p) = {dot_k_p:.6e}")
    log(f"mesh target size = {cfg.mesh_target_size}")
    solver_settings = _solver_profile_settings(cfg)
    solver_profile_resolved = solver_settings["profile_resolved"]
    petsc_options = solver_settings["petsc_options"]
    log(f"solver profile requested = {solver_settings['profile_requested']}")
    log(f"solver profile resolved = {solver_profile_resolved}")
    log(f"solver reliability = {solver_settings['reliability']}")
    for warning in solver_settings["warnings"]:
        log(f"WARNING: {warning}")
    log(f"PETSc solver options = {petsc_options}")

    if solver_settings["disabled"]:
        _clear_official_field_outputs(out_dir, comm)
        elapsed = float(comm.allreduce(time.perf_counter() - start, op=MPI.MAX))
        max_rss_mb = _global_max_rss_mb(comm)
        summary = {
            "case_name": cfg.case_name,
            "stage": _stage_label(cfg),
            "config": cfg.as_jsonable(),
            "case_status": "failed_disabled_solver_profile",
            "official_result": False,
            "diagnostic_only": True,
            "postprocess_skipped": True,
            "postprocess_skip_reason": solver_settings["disabled_reason"],
            "num_mesh_cells": None,
            "num_nedelec_dofs": None,
            "matrix_stats": None,
            "petsc_scalar_type": str(PETSc.ScalarType),
            "dolfinx_default_scalar_type": str(default_scalar_type),
            "solver_backend": "stage-2 3D Maxwell manufactured-reference path",
            "solver_profile": cfg.solver_profile,
            "solver_profile_resolved": solver_profile_resolved,
            "solver_petsc_options": petsc_options,
            "solver_reliability": solver_settings["reliability"],
            "solver_experimental": solver_settings["experimental"],
            "solver_disabled": True,
            "solver_disabled_reason": solver_settings["disabled_reason"],
            "solver_warnings": solver_settings["warnings"],
            "actual_ksp_type": None,
            "actual_pc_type": None,
            "ksp_converged": False,
            "ksp_converged_reason": None,
            "ksp_converged_reason_name": "DISABLED_SOLVER_PROFILE",
            "ksp_iterations": 0,
            "solver_residual_norm": None,
            "incident_transversality_dot_k_p": dot_k_p,
            "timings_seconds": timings,
            "elapsed_seconds": elapsed,
            "max_rss_mb": max_rss_mb,
        }
        _log_solver_summary(summary, log)
        log(f"elapsed seconds = {elapsed:.3f}")
        _write_case_outputs(out_dir, summary, log_lines, comm)
        return summary

    stage_start = _start_timed_stage(comm)
    mesh_data = build_airbox_mesh_3d(cfg, out_dir)
    _finish_timed_stage(comm, timings, "mesh_build", stage_start, log)

    msh = mesh_data.mesh
    tdim = msh.topology.dim
    fdim = tdim - 1
    num_cells = msh.topology.index_map(tdim).size_global

    stage_start = _start_timed_stage(comm)
    curl_el = element("N1curl", msh.basix_cell(), cfg.nedelec_degree, dtype=default_real_type)
    V = fem.functionspace(msh, curl_el)
    num_dofs = V.dofmap.index_map.size_global * V.dofmap.index_map_bs
    _finish_timed_stage(comm, timings, "function_space_setup", stage_start, log)
    log(f"mesh cells = {num_cells}")
    log(f"3D N1curl dofs = {num_dofs}")

    stage_start = _start_timed_stage(comm)
    E_exact = plane_wave_electric_field(V, cfg)
    floquet_data: DoubleFloquet3DData | None = None
    if cfg.use_floquet_xy:
        floquet_data = build_double_floquet_mpc(V, mesh_data, cfg, log)
        boundary_facets = _z_boundary_facets(mesh_data, cfg)
        raw_boundary_dofs = fem.locate_dofs_topological(V, fdim, boundary_facets)
        boundary_dofs = np.setdiff1d(raw_boundary_dofs, floquet_data.local_slave_dofs, assume_unique=False).astype(np.int32)
        log(f"Dirichlet H(curl) z-boundary dofs before slave removal = {len(raw_boundary_dofs)}")
    else:
        boundary_dofs = fem.locate_dofs_topological(V, fdim, mesh_data.boundary_facets)
    bc = fem.dirichletbc(E_exact, boundary_dofs)
    _finish_timed_stage(comm, timings, "boundary_condition_setup", stage_start, log)
    log(f"Dirichlet H(curl) boundary dofs = {len(boundary_dofs)}")

    stage_start = _start_timed_stage(comm)
    a, L = _build_variational_forms(msh, mesh_data, cfg, V)
    _finish_timed_stage(comm, timings, "variational_form_setup", stage_start, log)

    stage_start = _start_timed_stage(comm)
    if floquet_data is None:
        E = fem.Function(V, name="E_numerical")
        problem = fem_petsc.LinearProblem(
            a,
            L,
            bcs=[bc],
            u=E,
            petsc_options_prefix=f"airbox3d_{cfg.case_name}_{solver_profile_resolved}_",
            petsc_options=petsc_options,
        )
        solver_backend = "dolfinx.fem.petsc.LinearProblem with strong tangential E boundary data"
    else:
        import dolfinx_mpc

        E = fem.Function(floquet_data.mpc.function_space, name="E_numerical")
        problem = dolfinx_mpc.LinearProblem(
            a,
            L,
            floquet_data.mpc,
            bcs=[bc],
            u=E,
            petsc_options_prefix=f"airbox3d_{cfg.case_name}_{solver_profile_resolved}_mpc_",
            petsc_options=petsc_options,
        )
        solver_backend = "dolfinx_mpc.LinearProblem with x/y double Floquet and z boundary data"
    _finish_timed_stage(comm, timings, "linear_problem_setup", stage_start, log)

    stage_start = _start_timed_stage(comm)
    E = problem.solve()
    if floquet_data is not None:
        floquet_data.mpc.backsubstitution(E)
    _finish_timed_stage(comm, timings, "linear_problem_solve", stage_start, log)

    stage_start = _start_timed_stage(comm)
    matrix_stats = _petsc_matrix_stats(problem.A)
    _finish_timed_stage(comm, timings, "matrix_stats", stage_start, log)
    _log_matrix_stats(matrix_stats, log)

    reason = int(problem.solver.getConvergedReason())
    reason_name = _ksp_reason_name(reason)
    iterations = int(problem.solver.getIterationNumber())
    residual_norm = float(problem.solver.getResidualNorm())
    ksp_type = problem.solver.getType()
    pc_type = problem.solver.getPC().getType()
    log(f"solver converged reason = {reason}")
    log(f"solver converged reason name = {reason_name}")
    log(f"solver iterations = {iterations}")
    log(f"solver residual norm = {residual_norm:.6e}")
    log(f"actual KSP type = {ksp_type}")
    log(f"actual PC type = {pc_type}")
    elapsed = float(comm.allreduce(time.perf_counter() - start, op=MPI.MAX))
    max_rss_mb = _global_max_rss_mb(comm)
    converged = reason > 0

    summary = {
        "case_name": cfg.case_name,
        "stage": _stage_label(cfg),
        "config": cfg.as_jsonable(),
        "case_status": "completed" if converged else "failed_not_converged",
        "official_result": converged,
        "diagnostic_only": not converged,
        "postprocess_skipped": not converged,
        "postprocess_skip_reason": None if converged else "PETSc KSP did not converge.",
        "num_mesh_cells": int(num_cells),
        "num_nedelec_dofs": int(num_dofs),
        "matrix_stats": matrix_stats,
        "petsc_scalar_type": str(PETSc.ScalarType),
        "dolfinx_default_scalar_type": str(default_scalar_type),
        "solver_backend": solver_backend,
        "solver_profile": cfg.solver_profile,
        "solver_profile_resolved": solver_profile_resolved,
        "solver_petsc_options": petsc_options,
        "solver_reliability": solver_settings["reliability"],
        "solver_experimental": solver_settings["experimental"],
        "solver_disabled": False,
        "solver_disabled_reason": None,
        "solver_warnings": solver_settings["warnings"],
        "actual_ksp_type": ksp_type,
        "actual_pc_type": pc_type,
        "ksp_converged": converged,
        "ksp_converged_reason": reason,
        "ksp_converged_reason_name": reason_name,
        "ksp_iterations": iterations,
        "solver_residual_norm": residual_norm,
        "use_floquet_xy": cfg.use_floquet_xy,
        "use_pml": cfg.use_pml,
        "floquet_num_local_slaves": None if floquet_data is None else floquet_data.num_local_slaves,
        "max_face_pairing_coordinate_error": None
        if floquet_data is None
        else floquet_data.max_face_pairing_coordinate_error,
        "nedelec_orientation_factor_stats": None if floquet_data is None else floquet_data.orientation_factor_stats,
        "floquet_constraint_phase_x": None if floquet_data is None else floquet_data.phase_x,
        "floquet_constraint_phase_y": None if floquet_data is None else floquet_data.phase_y,
        "floquet_constraint_phase_corner": None if floquet_data is None else floquet_data.phase_corner,
        "floquet_edge_corner_constraint_phase_mismatch": None
        if floquet_data is None
        else floquet_data.edge_corner_phase_mismatch,
        "pml_parameters": {
            "pml_alpha": cfg.pml_alpha,
            "pml_top_thickness": cfg.pml_top_thickness,
            "pml_bottom_thickness": cfg.pml_bottom_thickness,
            "physical_z_min": cfg.physical_z_min,
            "physical_z_max": cfg.physical_z_max,
            "domain_z_min": cfg.domain_z_min,
            "domain_z_max": cfg.domain_z_max,
        },
        "incident_transversality_dot_k_p": dot_k_p,
        "timings_seconds": timings,
        "elapsed_seconds": elapsed,
        "max_rss_mb": max_rss_mb,
    }

    if not converged:
        _clear_official_field_outputs(out_dir, comm)
        log("WARNING: PETSc KSP did not converge.")
        log("WARNING: This field is only a diagnostic iterate and must not be used as a valid solution.")
        log("WARNING: Official postprocess and ParaView output are skipped for this failed case.")
        _log_solver_summary(summary, log)
        log("timing summary seconds:")
        for name, value in timings.items():
            log(f"  {name}: {value:.3f}")
        log(f"elapsed seconds = {elapsed:.3f}")
        _write_case_outputs(out_dir, summary, log_lines, comm)
        return summary

    stage_start = _start_timed_stage(comm)
    field_metrics = save_airbox_3d_fields(mesh_data, cfg, E, out_dir)
    _finish_timed_stage(comm, timings, "postprocess", stage_start, log)
    elapsed = float(comm.allreduce(time.perf_counter() - start, op=MPI.MAX))
    max_rss_mb = _global_max_rss_mb(comm)
    summary["timings_seconds"] = timings
    summary["elapsed_seconds"] = elapsed
    summary["max_rss_mb"] = max_rss_mb
    summary.update(field_metrics)
    stage2_metrics: dict[str, Any] = {}
    if floquet_data is not None:
        stage2_metrics.update(_floquet_probe_metrics(floquet_data))
    if cfg.use_pml:
        stage2_metrics.update(_pml_probe_metrics(E, cfg))
    stage2_metrics.update(_stage2_reference_metrics(cfg, field_metrics))
    summary.update(stage2_metrics)
    if comm.rank == 0 and {"R_total", "T_total", "R_plus_T"}.issubset(stage2_metrics):
        (out_dir / "power_metrics_3d.json").write_text(
            json.dumps(
                {key: stage2_metrics[key] for key in ("R_total", "T_total", "R_plus_T", "fresnel_R", "fresnel_T", "fresnel_R_error", "fresnel_T_error") if key in stage2_metrics},
                ensure_ascii=False,
                indent=2,
                default=_json_default,
            ),
            encoding="utf-8",
        )
    log(f"max |E| = {field_metrics['max_abs_E']:.6e}")
    log(f"max |H| = {field_metrics['max_abs_H']:.6e}")
    log(f"plane-wave relative max error = {field_metrics['relative_max_abs_E_error']:.6e}")
    log(f"H relative max error = {field_metrics['relative_max_abs_H_error']:.6e}")
    log(f"Poynting direction cosine = {field_metrics['poynting_direction_cosine']:.6e}")
    if floquet_data is not None:
        log(f"Floquet x-face mismatch = {summary['floquet_x_face_mismatch']:.6e}")
        log(f"Floquet y-face mismatch = {summary['floquet_y_face_mismatch']:.6e}")
        log(f"Floquet edge/corner mismatch = {summary['floquet_edge_corner_mismatch']:.6e}")
    if cfg.use_pml:
        log(f"PML reflection proxy = {summary['pml_reflection_proxy']:.6e}")
        log(f"PML top decay ratio = {summary['pml_decay_ratio_top']}")
        log(f"PML bottom decay ratio = {summary['pml_decay_ratio_bottom']}")
    if cfg.geometry_kind == "fresnel_interface":
        log(f"Fresnel R/T = {summary['fresnel_R']:.6e} / {summary['fresnel_T']:.6e}")
        log(f"R+T = {summary['R_plus_T']:.6e}")
    log(f"ParaView file = {field_metrics['paraview_file']}")
    log("timing summary seconds:")
    for name, value in timings.items():
        log(f"  {name}: {value:.3f}")
    _log_solver_summary(summary, log)
    log(f"elapsed seconds = {elapsed:.3f}")

    _write_case_outputs(out_dir, summary, log_lines, comm)
    return summary
