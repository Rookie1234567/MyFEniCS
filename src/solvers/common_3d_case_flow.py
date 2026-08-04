from __future__ import annotations

import gc
import json
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from dolfinx import default_scalar_type, fem
from dolfinx.fem import petsc as fem_petsc

from ..common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND,
    SimulationConfig3D,
    resolve_stage4_full3d_assembly_backend,
)
from ..constraints.floquet_3d import DoubleFloquet3DData, build_double_floquet_mpc
from ..geometry.mesh_builder_3d import AirBox3DMesh, build_airbox_mesh_3d
from ..postprocessing.diffraction_3d import compute_diffraction_orders_3d
from ..postprocessing.flat_layer_reference_3d import write_flat_layer_reference_outputs
from ..postprocessing.postprocess_3d import save_airbox_3d_fields
from ..postprocessing.rta_3d import (
    compute_volume_absorption_3d,
    write_power_summary_csv,
)
from .common_3d_fields import (
    _add_reference_field_to_solution,
    _combine_fields,
    _function_coefficient_norm,
    incident_air_plane_wave_field,
    plane_wave_electric_field,
    stage4_layered_background_field,
)
from .common_3d_forms import (
    _build_variational_forms,
    _incident_scattered_rhs_source_norm,
    _layered_scattered_rhs_source_norm,
    _z_boundary_facets,
)
from .common_3d_postprocess import (
    _cell_tag_volumes,
    _floquet_probe_metrics,
    _pml_probe_metrics,
    _stage2_reference_metrics,
    _stage4_lossless_energy_balance_check,
    _stage4_scattered_pml_metrics,
)
from .common_3d_solve import (
    DirectSolveFailure,
    _assembled_rhs_norm,
    _cleanup_mumps_ooc_directory_on_success,
    _create_nedelec_space,
    _ksp_reason_name,
    _linear_system_diagnostics,
    _log_matrix_stats,
    _pc_factor_solver_type,
    _petsc_error_diagnostics,
    _petsc_matrix_stats,
    _prepare_direct_lu_options_for_comm,
    _prepare_mumps_ooc_runtime,
    _retain_mumps_ooc_directory_on_failure,
)
from .common_3d_utils import (
    _clear_official_field_outputs,
    _complete_rank_sum,
    _finish_timed_stage,
    _gather_optional_rank_floats,
    _global_max_rss_mb,
    _global_total_peak_rss_mb,
    _log_solver_summary,
    _stage_label,
    _start_timed_stage,
    _summary_base_fields,
    _trim_process_heap,
    _write_case_outputs,
    _write_progress_event,
)
from .dtn_port_3d import (
    Stage4VariablePLiveView,
    solve_stage4_dtn_port_total_field,
)
from .solve_vector_maxwell import _json_default


def _log_case_header(
    cfg: SimulationConfig3D,
    log,
    petsc_options,
    selected_parallel_lu,
    disabled_reason,
    linear_solve_method: str = "direct_lu",
):
    k = cfg.wavevector
    p = cfg.polarization_vector
    dot_k_p = np.dot(k, p)
    log(f"case = {cfg.case_name}")
    log(f"stage = {_stage_label(cfg)}")
    log(f"geometry kind = {cfg.geometry_kind}")
    log(f"validation role = {cfg.validation_role}")
    log(f"substrate material label = {cfg.substrate_material_label}")
    log(f"grating material label = {cfg.grating_material_label}")
    log(f"lambda0 nm = {cfg.lambda0}")
    log(f"n_substrate = {cfg.substrate_index}")
    log(f"n_grating = {cfg.grating_index}")
    log(f"use Floquet xy = {cfg.use_floquet_xy}")
    log(f"use PML = {cfg.use_pml}")
    log(f"PETSc ScalarType = {PETSc.ScalarType}")
    log(f"DOLFINx scalar type = {default_scalar_type}")
    log(f"k0 = {cfg.k0:.12g}")
    log(f"k = {k.tolist()}")
    log(f"polarization = {p.tolist()}")
    log(f"dot(k, p) = {dot_k_p:.6e}")
    log(f"mesh target size = {cfg.mesh_target_size}")
    log(f"mesh cell type requested = {cfg.mesh_cell_type}")
    log(f"mesh cell type resolved = {cfg.mesh_cell_type_resolved}")
    log(f"Floquet constraint mode requested = {cfg.floquet_constraint_mode_requested}")
    log(
        "Stage-4 Full3D assembly backend requested = "
        f"{cfg.stage4_full3d_assembly_backend}"
    )
    log(f"linear solve method = {linear_solve_method}")
    if linear_solve_method == "direct_lu":
        log(f"PETSc direct solver profile requested = {cfg.petsc_direct_solver_profile_requested}")
    log(f"divergence penalty = {cfg.divergence_penalty}")
    if selected_parallel_lu is not None:
        log(f"MPI direct factor solver selected = {selected_parallel_lu}")
    if disabled_reason is not None:
        log(f"WARNING: {disabled_reason}")
    if linear_solve_method == "direct_lu":
        log(f"PETSc direct LU options = {petsc_options}")
    return dot_k_p


def _matrix_nnz_ratio(after: dict[str, Any] | None, before: dict[str, Any] | None) -> float | None:
    if after is None or before is None:
        return None
    after_nnz = after.get("matrix_nnz_used")
    before_nnz = before.get("matrix_nnz_used")
    if after_nnz is None or before_nnz in (None, 0.0):
        return None
    return float(after_nnz) / float(before_nnz)


def _matrix_row_ratio(after: dict[str, Any] | None, before: dict[str, Any] | None) -> float | None:
    if after is None or before is None:
        return None
    after_rows = after.get("matrix_rows")
    before_rows = before.get("matrix_rows")
    if after_rows is None or before_rows in (None, 0):
        return None
    return float(after_rows) / float(before_rows)


def _merge_volume_closure_into_dtn_port_outputs(
    out_dir: Path,
    comm: MPI.Intracomm,
    *,
    port_metrics: dict[str, Any] | None,
    volume_metrics: dict[str, Any] | None,
) -> dict[str, Any]:
    """Attach material-volume closure fields to the official DtN port metrics."""

    if port_metrics is None or volume_metrics is None:
        return {}
    try:
        R_total = float(port_metrics["R_total"])
        T_total = float(port_metrics["T_total"])
        A_volume_total = float(volume_metrics["A_volume_total"])
    except (KeyError, TypeError, ValueError):
        return {}
    closure = float(R_total + T_total + A_volume_total - 1.0)
    fields = {
        "A_volume_total": A_volume_total,
        "R_plus_T_plus_A_volume": float(R_total + T_total + A_volume_total),
        "R_plus_T_plus_A_volume_dtn_port_modal": float(R_total + T_total + A_volume_total),
        "energy_closure_error_dtn_port_modal_volume": closure,
        "energy_closure_error_port_volume": closure,
        "A_port_balance_minus_A_volume_total": float(
            port_metrics.get("A_balance", 1.0 - R_total - T_total) - A_volume_total
        ),
    }
    port_metrics.update(fields)
    if comm.rank == 0:
        for filename in ("port_power.json", "dtn_port_power_metrics_3d.json"):
            path = out_dir / filename
            if not path.exists():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload.update(fields)
            if filename == "port_power.json":
                payload["R_total_dtn_port_modal"] = port_metrics.get("R_total_dtn_port_modal", R_total)
                payload["T_total_dtn_port_modal"] = port_metrics.get("T_total_dtn_port_modal", T_total)
                payload["R_plus_T_dtn_port_modal"] = port_metrics.get("R_plus_T_dtn_port_modal", R_total + T_total)
                payload["A_balance_dtn_port_modal"] = port_metrics.get("A_balance_dtn_port_modal")
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
                encoding="utf-8",
            )
    comm.barrier()
    return fields


def _assemble_unconstrained_matrix_stats(a, bcs, comm: MPI.Intracomm, log) -> dict[str, Any] | None:
    """Optionally assemble the pre-MPC matrix for density diagnostics.

    This doubles peak matrix memory for the diagnostic run, so it is controlled
    by cfg.matrix_diagnostics_assemble_unconstrained and should be used first on
    small meshes.
    """

    try:
        A_raw = fem_petsc.assemble_matrix(fem.form(a), bcs=[] if bcs is None else bcs)
        A_raw.assemble()
        stats = _petsc_matrix_stats(A_raw)
        A_raw.destroy()
        return stats
    except Exception as exc:
        message = f"WARNING: unconstrained matrix diagnostic assembly failed: {exc}"
        if comm.rank == 0:
            log(message)
        return {"diagnostic_error": str(exc)}


def _parallel_lu_failure_summary(
    cfg: SimulationConfig3D,
    out_dir: Path,
    comm: MPI.Intracomm,
    timings: dict[str, float],
    started: float,
    log,
    log_lines: list[str],
    petsc_options: dict[str, Any],
    selected_parallel_lu: str | None,
    reason_text: str,
    dot_k_p: complex,
) -> dict[str, Any]:
    _clear_official_field_outputs(out_dir, comm)
    elapsed = float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))
    summary = {
        "case_name": cfg.case_name,
        "stage": _stage_label(cfg),
        **_summary_base_fields(cfg, comm),
        "config": cfg.as_jsonable(),
        "case_status": "failed_parallel_direct_lu_unavailable",
        "official_result": False,
        "diagnostic_only": True,
        "postprocess_skipped": True,
        "postprocess_skip_reason": reason_text,
        "num_mesh_cells": None,
        "num_nedelec_dofs": None,
        "matrix_stats": None,
        "petsc_scalar_type": str(PETSc.ScalarType),
        "dolfinx_default_scalar_type": str(default_scalar_type),
        "solver_backend": "3D Maxwell direct LU path",
        "linear_solve_method": "direct_lu",
        "petsc_direct_solver_profile": cfg.petsc_direct_solver_profile_requested,
        "linear_solve_petsc_options": petsc_options,
        "linear_solve_disabled_reason": reason_text,
        "actual_ksp_type": None,
        "actual_pc_type": None,
        "actual_pc_factor_solver_type": None,
        "selected_parallel_lu_solver_type": selected_parallel_lu,
        "ksp_converged": False,
        "ksp_converged_reason": None,
        "ksp_converged_reason_name": "PARALLEL_DIRECT_LU_UNAVAILABLE",
        "ksp_iterations": 0,
        "solver_residual_norm": None,
        "incident_transversality_dot_k_p": dot_k_p,
        "timings_seconds": timings,
        "elapsed_seconds": elapsed,
        "max_rss_mb": _global_max_rss_mb(comm),
        "total_peak_rss_mb": _global_total_peak_rss_mb(comm),
    }
    summary["sum_rank_historical_peaks_mb_upper_bound"] = summary[
        "total_peak_rss_mb"
    ]
    summary["total_peak_rss_semantics"] = (
        "sum_rank_historical_peaks_upper_bound_not_simultaneous"
    )
    _log_solver_summary(summary, log)
    log(f"elapsed seconds = {elapsed:.3f}")
    _write_case_outputs(out_dir, summary, log_lines, comm)
    return summary

def _direct_solve_failure_summary(
    *,
    cfg: SimulationConfig3D,
    out_dir: Path,
    comm: MPI.Intracomm,
    timings: dict[str, float],
    started: float,
    log,
    log_lines: list[str],
    petsc_options: dict[str, Any],
    selected_parallel_lu: str | None,
    dot_k_p: complex,
    failure: DirectSolveFailure,
    num_cells: int,
    num_dofs: int,
    floquet_data: DoubleFloquet3DData | None,
    mesh_data,
    domain_tag_volumes: dict[str, float],
    unconstrained_rhs_norm: float | None,
    unconstrained_matrix_stats: dict[str, Any] | None,
    field_formulation: str,
    solve_stage4_dtn_port: bool,
    raw_boundary_dofs_global: int,
    boundary_dofs_global: int,
    ooc_info: dict[str, Any],
) -> dict[str, Any]:
    """Write a diagnostic summary when PETSc direct LU raises before solution."""

    _clear_official_field_outputs(out_dir, comm)
    matrix_stats = None
    linear_system_diagnostics = {}
    if failure.A is not None:
        try:
            matrix_stats = _petsc_matrix_stats(failure.A)
            _log_matrix_stats(matrix_stats, log)
        except Exception as exc:
            matrix_stats = {"diagnostic_error": str(exc)}
    if failure.A is not None and failure.b is not None and failure.x is not None:
        linear_system_diagnostics = _linear_system_diagnostics(failure.A, failure.b, failure.x)
    error_diagnostics = _petsc_error_diagnostics(failure.petsc_error, failure.ksp)
    reason = None
    reason_name = None
    iterations = 0
    residual_norm = None
    ksp_type = None
    pc_type = None
    pc_factor_solver_type = None
    if failure.ksp is not None:
        try:
            reason = int(failure.ksp.getConvergedReason())
            reason_name = _ksp_reason_name(reason)
        except Exception:
            reason_name = "PETSC_DIRECT_SOLVE_EXCEPTION"
        try:
            iterations = int(failure.ksp.getIterationNumber())
        except Exception:
            iterations = 0
        try:
            residual_norm = float(failure.ksp.getResidualNorm())
        except Exception:
            residual_norm = None
        try:
            ksp_type = failure.ksp.getType()
            pc = failure.ksp.getPC()
            pc_type = pc.getType()
            pc_factor_solver_type = _pc_factor_solver_type(pc)
        except Exception:
            pass
    elapsed = float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))
    dtn_solver_info = failure.extra_summary.get("solver_info", {})
    dtn_assembly_backend_requested = dtn_solver_info.get(
        "stage4_full3d_assembly_backend_requested",
        cfg.stage4_full3d_assembly_backend,
    )
    dtn_assembly_backend_actual = dtn_solver_info.get(
        "stage4_full3d_assembly_backend_actual"
    )
    dtn_assembly_backend_selection_source = dtn_solver_info.get(
        "stage4_full3d_assembly_backend_selection_source"
    )
    dtn_assembly_backend_qualification = dtn_solver_info.get(
        "stage4_full3d_assembly_backend_qualification"
    )
    dtn_assembly_backend_audit = dtn_solver_info.get(
        "stage4_full3d_assembly_backend_audit"
    )
    dtn_base_matrix_stats = dtn_solver_info.get("dtn_base_matrix_stats")
    dtn_augmented_matrix_stats = dtn_solver_info.get("dtn_augmented_matrix_stats_after_finalize")
    dtn_auxiliary_block_stats = dtn_solver_info.get("dtn_auxiliary_block_stats")
    constraint_matrix_transform = {
        "uses_floquet_mpc": bool(floquet_data is not None),
        "mpc_backend": None if floquet_data is None else "dolfinx_mpc low-level topological constraints",
        "explicit_chac_constructed": False,
        "chac_matrix_stats_before": None,
        "chac_matrix_stats_after": None,
        "unconstrained_matrix_stats": unconstrained_matrix_stats,
        "constrained_matrix_stats": matrix_stats,
        "constrained_to_unconstrained_nnz_ratio": _matrix_nnz_ratio(matrix_stats, unconstrained_matrix_stats)
        if isinstance(matrix_stats, dict)
        else None,
        "constrained_to_unconstrained_row_ratio": _matrix_row_ratio(matrix_stats, unconstrained_matrix_stats)
        if isinstance(matrix_stats, dict)
        else None,
        "dtn_auxiliary_augmented_matrix": bool(solve_stage4_dtn_port),
        "dtn_base_matrix_stats": dtn_base_matrix_stats,
        "dtn_augmented_matrix_stats_after_finalize": dtn_augmented_matrix_stats,
        "dtn_auxiliary_block_stats": dtn_auxiliary_block_stats,
        "dtn_augmented_to_base_nnz_ratio": _matrix_nnz_ratio(matrix_stats, dtn_base_matrix_stats)
        if isinstance(matrix_stats, dict)
        else None,
        "dtn_augmented_to_base_row_ratio": _matrix_row_ratio(matrix_stats, dtn_base_matrix_stats)
        if isinstance(matrix_stats, dict)
        else None,
    }
    ooc_status = _retain_mumps_ooc_directory_on_failure(ooc_info, log)
    summary = {
        "case_name": cfg.case_name,
        "stage": _stage_label(cfg),
        **_summary_base_fields(cfg, comm),
        "config": cfg.as_jsonable(),
        "case_status": "failed_direct_lu_exception",
        "official_result": False,
        "diagnostic_only": True,
        "postprocess_skipped": True,
        "postprocess_skip_reason": f"{failure.failure_stage}: {failure}",
        "failure_stage": failure.failure_stage,
        "last_completed_stage": failure.extra_summary.get("last_completed_stage"),
        "num_mesh_cells": int(num_cells),
        "num_nedelec_dofs": int(num_dofs),
        "matrix_stats": matrix_stats,
        "unconstrained_matrix_stats": unconstrained_matrix_stats,
        "constraint_matrix_transform": constraint_matrix_transform,
        "explicit_chac_constructed": False,
        "chac_nnz_before": None,
        "chac_nnz_after": None,
        "constrained_linear_system_size": None
        if not isinstance(matrix_stats, dict)
        else matrix_stats.get("matrix_rows"),
        "petsc_scalar_type": str(PETSc.ScalarType),
        "dolfinx_default_scalar_type": str(default_scalar_type),
        "solver_backend": failure.solver_backend or "3D Maxwell direct LU path",
        "field_formulation": field_formulation,
        "stage4_boundary_model": cfg.stage4_boundary_model.lower() if cfg.stage_case.startswith("stage4_") else None,
        "stage4_dtn_port_enabled": bool(solve_stage4_dtn_port),
        "stage4_full3d_assembly_backend_requested": (
            dtn_assembly_backend_requested
        ),
        "stage4_full3d_assembly_backend_actual": (
            dtn_assembly_backend_actual
        ),
        "stage4_full3d_assembly_backend_selection_source": (
            dtn_assembly_backend_selection_source
        ),
        "stage4_full3d_assembly_backend_qualification": (
            dtn_assembly_backend_qualification
        ),
        "stage4_full3d_assembly_backend_audit": (
            dtn_assembly_backend_audit
        ),
        "stage4_dtn_num_auxiliary_dofs": dtn_solver_info.get("num_auxiliary_dofs"),
        "num_active_exact_sequence_fe_dofs": dtn_solver_info.get(
            "num_active_exact_sequence_fe_dofs"
        ),
        "num_storage_carrier_fe_dofs": dtn_solver_info.get(
            "num_storage_carrier_fe_dofs"
        ),
        "num_independent_trace_rows": dtn_solver_info.get(
            "num_independent_trace_rows"
        ),
        "num_augmented_rows": dtn_solver_info.get("num_augmented_rows"),
        "dof_row_semantics": dtn_solver_info.get("dof_row_semantics"),
        "stage4_dtn_auxiliary_block_stats": dtn_auxiliary_block_stats,
        "stage4_dtn_base_matrix_stats": dtn_base_matrix_stats,
        "stage4_dtn_augmented_matrix_stats_after_finalize": dtn_augmented_matrix_stats,
        "strong_z_boundary_dirichlet_enabled": bool(boundary_dofs_global),
        "strong_z_boundary_dirichlet_dofs": int(boundary_dofs_global),
        "strong_z_boundary_dirichlet_raw_dofs_global": int(raw_boundary_dofs_global),
        "domain_tag_volumes": domain_tag_volumes,
        "rhs_source_norm": None,
        "unconstrained_rhs_norm": unconstrained_rhs_norm,
        "linear_solve_method": "direct_lu",
        "petsc_direct_solver_profile": cfg.petsc_direct_solver_profile_requested,
        "linear_solve_petsc_options": petsc_options,
        "linear_solve_disabled_reason": None,
        "direct_solve_exception": error_diagnostics,
        "actual_ksp_type": ksp_type,
        "actual_pc_type": pc_type,
        "actual_pc_factor_solver_type": pc_factor_solver_type,
        "selected_parallel_lu_solver_type": selected_parallel_lu,
        "ksp_converged": False,
        "ksp_converged_reason": reason,
        "ksp_converged_reason_name": reason_name or "PETSC_DIRECT_SOLVE_EXCEPTION",
        "ksp_iterations": iterations,
        "solver_residual_norm": residual_norm,
        **linear_system_diagnostics,
        "use_floquet_xy": cfg.use_floquet_xy,
        "use_pml": cfg.use_pml,
        "floquet_num_constraints": None if floquet_data is None else floquet_data.num_constraints,
        "floquet_constraint_mode_resolved": None if floquet_data is None else floquet_data.constraint_mode_resolved,
        "floquet_raw_map_nnz": None if floquet_data is None else floquet_data.raw_map_nnz,
        "floquet_max_masters_per_slave": None if floquet_data is None else floquet_data.max_masters_per_slave,
        "floquet_estimated_constraint_memory_mb": None
        if floquet_data is None
        else floquet_data.estimated_constraint_memory_mb,
        "floquet_topology_cache_hit": None
        if floquet_data is None
        else floquet_data.topology_cache_hit,
        "floquet_topology_build_seconds_current": None
        if floquet_data is None
        else floquet_data.topology_build_seconds_current,
        "floquet_phase_update_seconds": None
        if floquet_data is None
        else floquet_data.phase_update_seconds,
        "floquet_communication_bytes_sent_current": None
        if floquet_data is None
        else floquet_data.communication_bytes_sent_current,
        "floquet_communication_bytes_received_current": None
        if floquet_data is None
        else floquet_data.communication_bytes_received_current,
        "floquet_used_full_boundary_gather": None
        if floquet_data is None
        else floquet_data.used_full_boundary_gather,
        "floquet_created_dense_boundary_square": None
        if floquet_data is None
        else floquet_data.created_dense_boundary_square,
        "mesh_cell_type_actual": mesh_data.mesh_cell_type_resolved,
        "mesh_cells_resolved": list(mesh_data.mesh_cells_resolved),
        "mesh_spacing_mode_resolved": mesh_data.mesh_spacing_mode_resolved,
        "mesh_axis_cell_stats": mesh_data.mesh_axis_cell_stats,
        "mesh_material_plane_alignment": mesh_data.material_plane_alignment,
        "mumps_ooc_runtime": {**ooc_info, **ooc_status},
        "incident_transversality_dot_k_p": dot_k_p,
        "timings_seconds": {**timings, **failure.timing_details},
        "elapsed_seconds": elapsed,
        "max_rss_mb": _global_max_rss_mb(comm),
        "total_peak_rss_mb": _global_total_peak_rss_mb(comm),
    }
    summary["sum_rank_historical_peaks_mb_upper_bound"] = summary[
        "total_peak_rss_mb"
    ]
    summary["total_peak_rss_semantics"] = (
        "sum_rank_historical_peaks_upper_bound_not_simultaneous"
    )
    log(f"WARNING: direct LU failed at {failure.failure_stage}: {failure}")
    log(f"PETSc error diagnostics = {error_diagnostics}")
    _log_solver_summary(summary, log)
    log(f"elapsed seconds = {elapsed:.3f}")
    _write_progress_event(
        out_dir,
        comm,
        stage=failure.failure_stage,
        status="failed",
        started=started,
        dofs=num_dofs,
        constraints=None if floquet_data is None else floquet_data.num_constraints,
        matrix_stats=matrix_stats if isinstance(matrix_stats, dict) else None,
        petsc_options=petsc_options,
        extra={
            "petsc_error": error_diagnostics,
            "stage4_full3d_assembly_backend_requested": (
                dtn_assembly_backend_requested
            ),
            "stage4_full3d_assembly_backend_actual": (
                dtn_assembly_backend_actual
            ),
            "stage4_full3d_assembly_backend_selection_source": (
                dtn_assembly_backend_selection_source
            ),
            "stage4_full3d_assembly_backend_qualification": (
                dtn_assembly_backend_qualification
            ),
        },
    )
    try:
        _write_case_outputs(out_dir, summary, log_lines, comm)
    finally:
        failure.cleanup()
    return summary


def _build_floquet_and_boundary_conditions(
    cfg: SimulationConfig3D,
    mesh_data,
    V,
    E_bc: fem.Function,
    apply_strong_boundary_bc: bool,
    timings: dict[str, float],
    comm: MPI.Intracomm,
    log,
) -> tuple[DoubleFloquet3DData | None, list, int, int, np.ndarray]:
    fdim = mesh_data.mesh.topology.dim - 1
    floquet_data: DoubleFloquet3DData | None = None
    boundary_dofs = np.asarray([], dtype=np.int32)
    raw_boundary_dofs_global = 0
    boundary_dofs_global = 0

    stage_start = _start_timed_stage(comm)
    if cfg.use_floquet_xy:
        floquet_data = build_double_floquet_mpc(V, mesh_data, cfg, log)
        timings.update(floquet_data.timings_seconds)
    _finish_timed_stage(comm, timings, "floquet_constraint_setup_outer", stage_start, log)

    stage_start = _start_timed_stage(comm)
    if cfg.use_floquet_xy:
        if apply_strong_boundary_bc:
            boundary_facets = _z_boundary_facets(mesh_data, cfg)
            raw_boundary_dofs = fem.locate_dofs_topological(V, fdim, boundary_facets)
            boundary_dofs = np.setdiff1d(raw_boundary_dofs, floquet_data.local_slave_dofs, assume_unique=False).astype(
                np.int32
            )
            raw_boundary_dofs_global = int(comm.allreduce(len(raw_boundary_dofs), op=MPI.SUM))
            boundary_dofs_global = int(comm.allreduce(len(boundary_dofs), op=MPI.SUM))
            log(
                "Dirichlet H(curl) z-boundary dofs before slave removal "
                f"local/global = {len(raw_boundary_dofs)} / {raw_boundary_dofs_global}"
            )
        else:
            log("No z-boundary Dirichlet dofs were located for this Floquet run.")
    elif apply_strong_boundary_bc:
        boundary_dofs = fem.locate_dofs_topological(V, fdim, mesh_data.boundary_facets)
        raw_boundary_dofs_global = int(comm.allreduce(len(boundary_dofs), op=MPI.SUM))
        boundary_dofs_global = raw_boundary_dofs_global

    bcs = [fem.dirichletbc(E_bc, boundary_dofs)] if apply_strong_boundary_bc else []
    _finish_timed_stage(comm, timings, "boundary_condition_setup", stage_start, log)
    log(f"strong Dirichlet H(curl) boundary enabled = {apply_strong_boundary_bc}")
    log(f"Dirichlet H(curl) boundary dofs local/global = {len(boundary_dofs)} / {boundary_dofs_global}")
    return (
        floquet_data,
        bcs,
        raw_boundary_dofs_global,
        boundary_dofs_global,
        boundary_dofs,
    )


def _solve_standard_linear_problem(
    cfg: SimulationConfig3D,
    V,
    a,
    L,
    floquet_data: DoubleFloquet3DData | None,
    problem_bcs,
    apply_strong_boundary_bc: bool,
    petsc_options: dict[str, Any],
    timings: dict[str, float],
    comm: MPI.Intracomm,
    out_dir: Path,
    started: float,
    num_dofs: int,
    log,
):
    stage_start = _start_timed_stage(comm)
    if floquet_data is None:
        E = fem.Function(V, name="E_numerical")
        problem = fem_petsc.LinearProblem(
            a,
            L,
            bcs=problem_bcs,
            u=E,
            petsc_options_prefix=f"airbox3d_{cfg.case_name}_direct_lu_",
            petsc_options=petsc_options,
        )
        solver_backend = (
            "dolfinx.fem.petsc.LinearProblem with strong tangential E boundary data"
            if apply_strong_boundary_bc
            else "dolfinx.fem.petsc.LinearProblem without strong tangential E boundary data"
        )
    else:
        import dolfinx_mpc

        E = fem.Function(floquet_data.mpc.function_space, name="E_numerical")
        problem = dolfinx_mpc.LinearProblem(
            a,
            L,
            floquet_data.mpc,
            bcs=problem_bcs,
            u=E,
            petsc_options_prefix=f"airbox3d_{cfg.case_name}_direct_lu_mpc_",
            petsc_options=petsc_options,
        )
        solver_backend = (
            "dolfinx_mpc.LinearProblem with x/y double Floquet and z boundary data"
            if apply_strong_boundary_bc
            else "dolfinx_mpc.LinearProblem with x/y double Floquet and no strong tangential E boundary data"
        )
    _finish_timed_stage(comm, timings, "linear_problem_setup", stage_start, log)

    stage_start = _start_timed_stage(comm)
    _write_progress_event(
        out_dir,
        comm,
        stage="direct_lu_factorization_and_solve",
        status="begin",
        started=started,
        dofs=num_dofs,
        constraints=None if floquet_data is None else floquet_data.num_constraints,
        petsc_options=petsc_options,
    )
    try:
        E = problem.solve()
    except PETSc.Error as exc:
        _finish_timed_stage(comm, timings, "linear_problem_solve_failed", stage_start, log)
        raise DirectSolveFailure(
            "PETSc direct LU failed during KSPSolve.",
            failure_stage="direct_lu_factorization_and_solve",
            petsc_error=exc,
            A=problem.A,
            b=problem.b,
            x=problem.x,
            ksp=problem.solver,
            solver_backend=solver_backend,
        ) from exc
    E.x.scatter_forward()
    _finish_timed_stage(comm, timings, "linear_problem_solve", stage_start, log)
    _write_progress_event(
        out_dir,
        comm,
        stage="direct_lu_factorization_and_solve",
        status="end",
        started=started,
        dofs=num_dofs,
        constraints=None if floquet_data is None else floquet_data.num_constraints,
        petsc_options=petsc_options,
    )
    return E, problem, solver_backend


def run_prepared_3d_case_flow(
    cfg: SimulationConfig3D,
    out_dir: Path,
    *,
    expected_stage_case: str,
    field_formulation: str,
    solve_reference_correction: bool = False,
    solve_incident_scattered: bool = False,
    solve_layered_scattered: bool = False,
    solve_stage4_dtn_port: bool = False,
    apply_strong_boundary_bc: bool = True,
    run_diffraction_postprocess: bool = False,
    solution_observer: Callable[..., None] | None = None,
    linear_solver_port=None,
    variable_p_live_observer: (
        Callable[[Stage4VariablePLiveView], None] | None
    ) = None,
    variable_p_retain_local_schur_for_research: bool = False,
    static_retain_local_schur_for_matrix_free: bool = False,
    canonical_vector_export: bool = False,
    mesh_data_override: AirBox3DMesh | None = None,
) -> dict[str, object]:
    """Run one explicit 3D Maxwell case after the stage file chooses the recipe.

    This helper contains shared FEM bookkeeping only.  It does not dispatch on
    ``cfg.stage_case``; each stage solver validates and chooses the formulation
    before entering this flow.  ``solution_observer`` is an explicit research
    hook invoked only after the official solve and postprocess have completed;
    the ordinary solver path leaves it unset.
    ``variable_p_live_observer`` is a separate default-off collective research
    hook invoked after primal solver telemetry is frozen but before the direct
    factor and recovered active vectors are released.  Its PETSc objects are
    borrowed for the callback lifetime only.
    ``variable_p_retain_local_schur_for_research`` is an independent opt-in
    lease for pre-constraint cell Schur matrices during that callback only.
    ``mesh_data_override`` is a default-off research hook for solving on an
    already audited conforming mesh; ordinary callers continue to build a mesh.
    """

    comm = (
        MPI.COMM_WORLD
        if mesh_data_override is None
        else mesh_data_override.mesh.comm
    )
    live_observer_flags = comm.allgather(
        (
            variable_p_live_observer is not None,
            bool(variable_p_retain_local_schur_for_research),
            linear_solver_port is not None,
        )
    )
    if len(set(live_observer_flags)) != 1:
        raise ValueError(
            "variable-p observer, Schur retention, and external solver-port "
            "presence must match on every MPI rank"
        )
    if cfg.stage_case != expected_stage_case:
        raise ValueError(f"This solver accepts only stage_case={expected_stage_case!r}.")
    if not np.issubdtype(default_scalar_type, np.complexfloating):
        raise RuntimeError("The 3D Maxwell solver requires complex-mode DOLFINx/PETSc.")
    if variable_p_live_observer is not None:
        local_validation_errors: list[str] = []
        try:
            if solution_observer is not None:
                raise ValueError(
                    "the late solution observer and variable-p live "
                    "observer cannot be enabled together"
                )
            if not solve_stage4_dtn_port:
                raise ValueError(
                    "the variable-p live observer requires the Stage-4 "
                    "DtN flow"
                )
            backend = resolve_stage4_full3d_assembly_backend(cfg)
            if (
                backend["actual"]
                != ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
            ):
                raise ValueError(
                    "the variable-p live observer requires the exact-"
                    "sequence assembly-time variable-p backend"
                )
            if (
                cfg.matrix_diagnostics_assemble_only
                or cfg.matrix_diagnostics_factorization_only
            ):
                raise ValueError(
                    "the variable-p live observer requires a complete solve"
                )
        except Exception as exc:
            local_validation_errors.append(
                f"rank {comm.rank}: {type(exc).__name__}: {exc}"
            )
        collective_validation_errors = [
            error
            for rank_errors in comm.allgather(local_validation_errors)
            for error in rank_errors
        ]
        if collective_validation_errors:
            raise ValueError(
                "variable-p live observer validation failed: "
                + "; ".join(collective_validation_errors)
            )
    elif variable_p_retain_local_schur_for_research:
        raise ValueError(
            "research Schur retention requires a variable-p live observer"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    log_lines: list[str] = []
    timings: dict[str, float] = {}
    started = _start_timed_stage(comm)

    def log(message: str):
        log_lines.append(message)
        if comm.rank == 0:
            PETSc.Sys.Print(message)

    _write_progress_event(
        out_dir,
        comm,
        stage="process_start",
        status="begin",
        started=started,
        extra={"case_name": cfg.case_name, "stage_case": cfg.stage_case},
    )

    stage_start = _start_timed_stage(comm)
    if cfg.use_pml and (cfg.pml_top_thickness <= 0.0 or cfg.pml_bottom_thickness <= 0.0):
        raise ValueError("3D PML cases require positive pml_top_thickness and pml_bottom_thickness.")
    if solve_stage4_dtn_port:
        if cfg.use_pml:
            raise ValueError("stage4_boundary_model='dtn_port' requires use_pml=False.")
        if not cfg.use_floquet_xy:
            raise ValueError("stage4_boundary_model='dtn_port' requires use_floquet_xy=True.")
        if cfg.stage4_dtn_assembly.lower() != "auxiliary":
            raise NotImplementedError("Stage-4 3D DtN v1 supports only stage4_dtn_assembly='auxiliary'.")
    if (
        cfg.matrix_diagnostics_assemble_only
        and cfg.matrix_diagnostics_factorization_only
    ):
        raise ValueError(
            "assemble-only and factorization-only diagnostics are mutually exclusive."
        )
    if linear_solver_port is not None and (
        not solve_stage4_dtn_port
        or cfg.matrix_diagnostics_assemble_only
        or cfg.matrix_diagnostics_factorization_only
        or resolve_stage4_full3d_assembly_backend(cfg)["actual"]
        != ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
    ):
        raise ValueError(
            "external linear-solver port requires a complete "
            "assembly_time_static_condensed Stage-4 DtN solve"
        )
    if cfg.matrix_diagnostics_factorization_only and not solve_stage4_dtn_port:
        raise NotImplementedError(
            "factorization-only diagnostics currently require the Stage-4 auxiliary DtN path."
        )
    _finish_timed_stage(comm, timings, "config_validation", stage_start, log)
    _write_progress_event(out_dir, comm, stage="after_config", status="end", started=started)

    if linear_solver_port is None:
        petsc_options, selected_parallel_lu, disabled_reason = _prepare_direct_lu_options_for_comm(comm, cfg)
    else:
        petsc_options = {}
        selected_parallel_lu = None
        disabled_reason = None
    dot_k_p = _log_case_header(
        cfg,
        log,
        petsc_options,
        selected_parallel_lu,
        disabled_reason,
        linear_solve_method=(
            "external_linear_solver_port"
            if linear_solver_port is not None
            else "direct_lu"
        ),
    )
    if linear_solver_port is not None:
        ooc_info = {
            "mumps_ooc_enabled": False,
            "mumps_ooc_tmpdir": None,
            "mumps_ooc_prefix": None,
            "status": "not_run_external_linear_solver_port",
        }
    _write_progress_event(
        out_dir,
        comm,
        stage="case_start",
        status="begin",
        started=started,
        petsc_options=petsc_options,
        extra={
            "case_name": cfg.case_name,
            "stage_case": cfg.stage_case,
            "stage4_full3d_assembly_backend_requested": (
                cfg.stage4_full3d_assembly_backend
            ),
            "solver_profile": (
                None
                if linear_solver_port is not None
                else cfg.petsc_direct_solver_profile_requested
            ),
            "matrix_diagnostics_assemble_only": cfg.matrix_diagnostics_assemble_only,
            "matrix_diagnostics_factorization_only": (
                cfg.matrix_diagnostics_factorization_only
            ),
        },
    )
    if disabled_reason is not None:
        return _parallel_lu_failure_summary(
            cfg,
            out_dir,
            comm,
            timings,
            started,
            log,
            log_lines,
            petsc_options,
            selected_parallel_lu,
            disabled_reason,
            dot_k_p,
        )
    if linear_solver_port is None:
        ooc_info = _prepare_mumps_ooc_runtime(cfg, out_dir, petsc_options, comm, log)
    _write_progress_event(
        out_dir,
        comm,
        stage="mumps_ooc_runtime_setup",
        status="end",
        started=started,
        petsc_options=petsc_options,
        extra=ooc_info,
    )

    stage_start = _start_timed_stage(comm)
    _write_progress_event(
        out_dir,
        comm,
        stage="mesh_build",
        status="begin",
        started=started,
        petsc_options=petsc_options,
    )
    if mesh_data_override is None:
        if cfg.stage4_local_h_refinement_plan is None:
            mesh_data = build_airbox_mesh_3d(cfg, out_dir)
        else:
            from ..adaptivity.stage4_local_h import (
                build_stage4_local_h_mesh_data,
            )

            mesh_data = build_stage4_local_h_mesh_data(
                cfg,
                cfg.stage4_local_h_refinement_plan,
                comm=comm,
            )
            log("mesh source = explicit hash-bound balanced local-h plan")
    else:
        relation = MPI.Comm.Compare(comm, mesh_data_override.mesh.comm)
        if relation not in (MPI.IDENT, MPI.CONGRUENT):
            raise ValueError("mesh_data_override must use the solver communicator")
        if mesh_data_override.mesh_cell_type_resolved != cfg.mesh_cell_type_resolved:
            raise ValueError(
                "mesh_data_override cell type does not match the requested config"
            )
        mesh_data = mesh_data_override
        log("mesh source = explicit audited mesh_data_override")
    local_h_context = getattr(mesh_data, "local_h_context", None)
    if (
        cfg.stage4_local_h_refinement_plan is None
        and local_h_context is not None
    ):
        raise ValueError(
            "a local-h mesh override requires stage4_local_h_refinement_plan"
        )
    if (
        cfg.stage4_local_h_refinement_plan is not None
        and local_h_context is None
    ):
        raise ValueError(
            "stage4_local_h_refinement_plan did not produce a local-h context"
        )
    _finish_timed_stage(comm, timings, "mesh_build", stage_start, log)
    _write_progress_event(
        out_dir,
        comm,
        stage="mesh_build",
        status="end",
        started=started,
        petsc_options=petsc_options,
    )
    _write_progress_event(
        out_dir,
        comm,
        stage="after_mesh",
        status="end",
        started=started,
        petsc_options=petsc_options,
    )
    log(f"mesh cell type actual = {mesh_data.mesh_cell_type_resolved}")
    log(f"mesh cells requested = {cfg.mesh_cells}")
    log(f"mesh cells resolved = {mesh_data.mesh_cells_resolved}")
    log(f"mesh spacing mode resolved = {mesh_data.mesh_spacing_mode_resolved}")
    if mesh_data.mesh_axis_cell_stats:
        log(f"mesh axis cell stats = {mesh_data.mesh_axis_cell_stats}")
    if mesh_data.material_plane_alignment.get("all_aligned") is False:
        log(f"WARNING: mesh material plane alignment = {mesh_data.material_plane_alignment}")
    for warning in mesh_data.z_alignment_warnings:
        log(f"WARNING: {warning}")

    msh = mesh_data.mesh
    tdim = msh.topology.dim
    num_cells = msh.topology.index_map(tdim).size_global
    domain_tag_volumes = _cell_tag_volumes(msh, mesh_data, cfg)
    variable_p_mesh_identity = None
    if (
        cfg.stage4_full3d_assembly_backend
        == "assembly_time_variable_p_condensed"
    ):
        from ..adaptivity.high_order_resource_audit import (
            partition_independent_linear_mesh_identity,
        )

        stage_start = _start_timed_stage(comm)
        variable_p_mesh_identity = (
            partition_independent_linear_mesh_identity(mesh_data)
        )
        _finish_timed_stage(
            comm,
            timings,
            "variable_p_mesh_identity",
            stage_start,
            log,
        )
    local_h_mesh_audit = (
        None
        if local_h_context is None
        else dict(local_h_context.audit)
    )

    stage_start = _start_timed_stage(comm)
    _write_progress_event(out_dir, comm, stage="function_space_setup", status="begin", started=started)
    V = _create_nedelec_space(msh, cfg)
    num_dofs = V.dofmap.index_map.size_global * V.dofmap.index_map_bs
    _finish_timed_stage(comm, timings, "function_space_setup", stage_start, log)
    _write_progress_event(
        out_dir,
        comm,
        stage="function_space_setup",
        status="end",
        started=started,
        dofs=num_dofs,
    )
    _write_progress_event(
        out_dir,
        comm,
        stage="after_function_space",
        status="end",
        started=started,
        dofs=num_dofs,
    )
    log(f"mesh cells = {num_cells}")
    log(f"3D N1curl dofs = {num_dofs}")

    stage_start = _start_timed_stage(comm)
    _write_progress_event(
        out_dir,
        comm,
        stage="field_formulation_setup",
        status="begin",
        started=started,
        dofs=num_dofs,
    )
    E_source_for_rhs = None
    rhs_source_norm = None
    if solve_incident_scattered:
        E_source_for_rhs = incident_air_plane_wave_field(V, cfg)
        rhs_source_norm = _incident_scattered_rhs_source_norm(msh, mesh_data, cfg, E_source_for_rhs)
    elif solve_layered_scattered:
        E_source_for_rhs = stage4_layered_background_field(V, cfg)
        rhs_source_norm = _layered_scattered_rhs_source_norm(msh, mesh_data, cfg, E_source_for_rhs)

    solve_with_zero_bc = (
        solve_reference_correction or solve_incident_scattered or solve_layered_scattered or solve_stage4_dtn_port
    )
    E_exact = None if solve_with_zero_bc else plane_wave_electric_field(V, cfg)
    E_bc = fem.Function(V, name="E_zero_bc") if solve_with_zero_bc else E_exact
    _finish_timed_stage(comm, timings, "field_formulation_setup", stage_start, log)
    _write_progress_event(
        out_dir,
        comm,
        stage="field_formulation_setup",
        status="end",
        started=started,
        dofs=num_dofs,
    )

    _write_progress_event(
        out_dir,
        comm,
        stage="floquet_and_boundary_setup",
        status="begin",
        started=started,
        dofs=num_dofs,
    )
    floquet_data, bcs, raw_boundary_dofs_global, boundary_dofs_global, boundary_dofs = (
        _build_floquet_and_boundary_conditions(cfg, mesh_data, V, E_bc, apply_strong_boundary_bc, timings, comm, log)
    )
    _write_progress_event(
        out_dir,
        comm,
        stage="floquet_and_boundary_setup",
        status="end",
        started=started,
        dofs=num_dofs,
        constraints=None if floquet_data is None else floquet_data.num_constraints,
    )
    _write_progress_event(
        out_dir,
        comm,
        stage="after_floquet_mpc_finalize",
        status="end",
        started=started,
        dofs=num_dofs,
        constraints=None if floquet_data is None else floquet_data.num_constraints,
    )
    problem_bcs = bcs if bcs else None
    log(f"field formulation = {field_formulation}")
    if solve_incident_scattered:
        log("incident-scattered RHS sign = +k0^2*(eps_sub - eps_air)*inner(E_inc, v)")
        log("incident-scattered RHS source region = physical_substrate")
        log(f"incident-scattered RHS source tag volumes = {{'substrate': {domain_tag_volumes['substrate']:.6e}}}")
        log(f"incident-scattered RHS source norm = {rhs_source_norm:.6e}")
    if solve_layered_scattered:
        log("layered-scattered RHS sign = +k0^2*(eps_true - eps_bg)*inner(E_bg, v)")
        log("layered-scattered RHS source region = physical_grating")
        log(f"layered-scattered RHS source tag volumes = {{'grating': {domain_tag_volumes['grating']:.6e}}}")
        log(f"layered-scattered RHS source contrast = {cfg.eps_grating - cfg.grating_background_eps!r}")
        log(f"layered-scattered RHS source norm = {rhs_source_norm:.6e}")
    if solve_stage4_dtn_port:
        log("stage4 boundary model = dtn_port")
        log(f"stage4 DtN order policy = {cfg.stage4_dtn_order_policy}")
        log(f"stage4 DtN assembly = {cfg.stage4_dtn_assembly}")
        log("stage4 DtN field formulation = total field with top incident port and outgoing top/bottom modes")

    stage_start = _start_timed_stage(comm)
    _write_progress_event(
        out_dir,
        comm,
        stage="variational_form_setup",
        status="begin",
        started=started,
        dofs=num_dofs,
        constraints=None if floquet_data is None else floquet_data.num_constraints,
    )
    a, L = _build_variational_forms(
        msh,
        mesh_data,
        cfg,
        V,
        field_formulation=field_formulation,
        incident_field=E_source_for_rhs,
    )
    _write_progress_event(
        out_dir,
        comm,
        stage="after_materials_and_forms",
        status="end",
        started=started,
        dofs=num_dofs,
        constraints=None if floquet_data is None else floquet_data.num_constraints,
    )
    unconstrained_rhs_norm = _assembled_rhs_norm(L)
    unconstrained_matrix_stats = None
    if cfg.matrix_diagnostics_assemble_unconstrained:
        log("assembling unconstrained matrix for diagnostic nnz comparison")
        unconstrained_matrix_stats = _assemble_unconstrained_matrix_stats(a, problem_bcs, comm, log)
        if unconstrained_matrix_stats is not None and "diagnostic_error" not in unconstrained_matrix_stats:
            log("unconstrained matrix diagnostic stats:")
            _log_matrix_stats(unconstrained_matrix_stats, log)
    _finish_timed_stage(comm, timings, "variational_form_setup", stage_start, log)
    _write_progress_event(
        out_dir,
        comm,
        stage="variational_form_setup",
        status="end",
        started=started,
        dofs=num_dofs,
        constraints=None if floquet_data is None else floquet_data.num_constraints,
    )
    log(f"unconstrained RHS norm = {unconstrained_rhs_norm}")

    dtn_result: dict[str, Any] | None = None
    if solve_stage4_dtn_port:
        if floquet_data is None:
            raise RuntimeError("Stage-4 dtn_port requires Floquet MPC data.")
        stage_start = _start_timed_stage(comm)
        try:
            dtn_result = solve_stage4_dtn_port_total_field(
                a=a,
                L=L,
                V=V,
                mesh_data=mesh_data,
                cfg=cfg,
                floquet_data=floquet_data,
                petsc_options=petsc_options,
                out_dir=out_dir,
                log=log,
                started=started,
                linear_solver_port=linear_solver_port,
                variable_p_live_observer=variable_p_live_observer,
                variable_p_retain_local_schur_for_research=(
                    variable_p_retain_local_schur_for_research
                ),
                static_retain_local_schur_for_matrix_free=(
                    static_retain_local_schur_for_matrix_free
                ),
                canonical_vector_export=canonical_vector_export,
            )
        except DirectSolveFailure as failure:
            _finish_timed_stage(
                comm,
                timings,
                "stage4_dtn_port_assembly_and_solve_failed",
                stage_start,
                log,
            )
            return _direct_solve_failure_summary(
                cfg=cfg,
                out_dir=out_dir,
                comm=comm,
                timings=timings,
                started=started,
                log=log,
                log_lines=log_lines,
                petsc_options=petsc_options,
                selected_parallel_lu=selected_parallel_lu,
                dot_k_p=dot_k_p,
                failure=failure,
                num_cells=num_cells,
                num_dofs=num_dofs,
                floquet_data=floquet_data,
                mesh_data=mesh_data,
                domain_tag_volumes=domain_tag_volumes,
                unconstrained_rhs_norm=unconstrained_rhs_norm,
                unconstrained_matrix_stats=unconstrained_matrix_stats,
                field_formulation=field_formulation,
                solve_stage4_dtn_port=solve_stage4_dtn_port,
                raw_boundary_dofs_global=raw_boundary_dofs_global,
                boundary_dofs_global=boundary_dofs_global,
                ooc_info=ooc_info,
            )
        _finish_timed_stage(comm, timings, "stage4_dtn_port_assembly_and_solve", stage_start, log)
        dtn_backend_progress = {
            key: dtn_result["solver_info"].get(key)
            for key in (
                "stage4_full3d_assembly_backend_requested",
                "stage4_full3d_assembly_backend_actual",
                "stage4_full3d_assembly_backend_selection_source",
                "stage4_full3d_assembly_backend_qualification",
            )
        }
        _write_progress_event(
            out_dir,
            comm,
            stage="stage4_dtn_port_assembly_and_solve",
            status="end",
            started=started,
            dofs=num_dofs,
            constraints=floquet_data.num_constraints,
            petsc_options=petsc_options,
            extra=dtn_backend_progress,
        )
        E = dtn_result["E_total"]
        solver_backend = dtn_result["solver_info"]["solver_backend"]
        problem = None
    else:
        try:
            E, problem, solver_backend = _solve_standard_linear_problem(
                cfg,
                V,
                a,
                L,
                floquet_data,
                problem_bcs,
                apply_strong_boundary_bc,
                petsc_options,
                timings,
                comm,
                out_dir,
                started,
                num_dofs,
                log,
            )
        except DirectSolveFailure as failure:
            return _direct_solve_failure_summary(
                cfg=cfg,
                out_dir=out_dir,
                comm=comm,
                timings=timings,
                started=started,
                log=log,
                log_lines=log_lines,
                petsc_options=petsc_options,
                selected_parallel_lu=selected_parallel_lu,
                dot_k_p=dot_k_p,
                failure=failure,
                num_cells=num_cells,
                num_dofs=num_dofs,
                floquet_data=floquet_data,
                mesh_data=mesh_data,
                domain_tag_volumes=domain_tag_volumes,
                unconstrained_rhs_norm=unconstrained_rhs_norm,
                unconstrained_matrix_stats=unconstrained_matrix_stats,
                field_formulation=field_formulation,
                solve_stage4_dtn_port=solve_stage4_dtn_port,
                raw_boundary_dofs_global=raw_boundary_dofs_global,
                boundary_dofs_global=boundary_dofs_global,
                ooc_info=ooc_info,
            )

    E_sca = E if (solve_incident_scattered or solve_layered_scattered) else None
    E_incident_solution = None
    E_background_solution = None
    E_total = E
    if solve_reference_correction:
        _add_reference_field_to_solution(E, cfg)
    elif solve_incident_scattered:
        E_incident_solution = incident_air_plane_wave_field(E.function_space, cfg)
        E_total = _combine_fields(E_sca, E_incident_solution, "E_total")
    elif solve_layered_scattered:
        E_background_solution = stage4_layered_background_field(E.function_space, cfg)
        E_total = _combine_fields(E_sca, E_background_solution, "E_total")
    elif solve_stage4_dtn_port:
        E_incident_solution = incident_air_plane_wave_field(E.function_space, cfg)

    stage_start = _start_timed_stage(comm)
    system_A = dtn_result["A"] if solve_stage4_dtn_port else problem.A
    system_b = dtn_result["b"] if solve_stage4_dtn_port else problem.b
    system_x = dtn_result["x"] if solve_stage4_dtn_port else problem.x
    system_ksp = dtn_result["ksp"] if solve_stage4_dtn_port else problem.solver
    assemble_only_result = bool(
        cfg.matrix_diagnostics_assemble_only
        or (dtn_result is not None and (dtn_result.get("solver_info", {}) or {}).get("assemble_only"))
    )
    factorization_only_result = bool(
        cfg.matrix_diagnostics_factorization_only
        or (
            dtn_result is not None
            and (dtn_result.get("solver_info", {}) or {}).get(
                "factorization_only"
            )
        )
    )
    diagnostic_only_result = assemble_only_result or factorization_only_result
    dtn_solver_info = None if dtn_result is None else dtn_result.get("solver_info", {})
    external_solver_snapshot = bool(
        dtn_solver_info and dtn_solver_info.get("external_linear_solver_port")
    )
    dtn_base_matrix_stats = None if dtn_solver_info is None else dtn_solver_info.get("dtn_base_matrix_stats")
    dtn_augmented_matrix_stats = (
        None if dtn_solver_info is None else dtn_solver_info.get("dtn_augmented_matrix_stats_after_finalize")
    )
    dtn_condensed_matrix_stats = (
        None
        if dtn_solver_info is None
        else dtn_solver_info.get("dtn_condensed_matrix_stats")
    )
    dtn_floquet_independent_matrix_stats = (
        None
        if dtn_solver_info is None
        else dtn_solver_info.get(
            "dtn_floquet_independent_matrix_stats"
        )
    )
    dtn_auxiliary_block_stats = None if dtn_solver_info is None else dtn_solver_info.get("dtn_auxiliary_block_stats")
    matrix_stats = (
        dtn_augmented_matrix_stats
        if system_A is None
        else _petsc_matrix_stats(system_A)
    )
    _finish_timed_stage(comm, timings, "matrix_stats", stage_start, log)
    _log_matrix_stats(matrix_stats, log)
    explicit_chac_constructed = False
    chac_before_stats = None
    chac_after_stats = None
    constraint_matrix_transform = {
        "uses_floquet_mpc": bool(floquet_data is not None),
        "mpc_backend": None if floquet_data is None else "dolfinx_mpc low-level topological constraints",
        "explicit_chac_constructed": explicit_chac_constructed,
        "chac_matrix_stats_before": chac_before_stats,
        "chac_matrix_stats_after": chac_after_stats,
        "unconstrained_matrix_stats": unconstrained_matrix_stats,
        "constrained_matrix_stats": matrix_stats,
        "constrained_to_unconstrained_nnz_ratio": _matrix_nnz_ratio(matrix_stats, unconstrained_matrix_stats),
        "constrained_to_unconstrained_row_ratio": _matrix_row_ratio(matrix_stats, unconstrained_matrix_stats),
        "dtn_auxiliary_augmented_matrix": bool(solve_stage4_dtn_port),
        "dtn_base_matrix_stats": dtn_base_matrix_stats,
        "dtn_augmented_matrix_stats_after_finalize": dtn_augmented_matrix_stats,
        "dtn_condensed_matrix_stats": dtn_condensed_matrix_stats,
        "dtn_floquet_independent_matrix_stats": (
            dtn_floquet_independent_matrix_stats
        ),
        "dtn_auxiliary_block_stats": dtn_auxiliary_block_stats,
        "dtn_augmented_to_base_nnz_ratio": _matrix_nnz_ratio(matrix_stats, dtn_base_matrix_stats),
        "dtn_augmented_to_base_row_ratio": _matrix_row_ratio(matrix_stats, dtn_base_matrix_stats),
    }
    log(f"explicit C^H A C constructed = {explicit_chac_constructed}")
    if unconstrained_matrix_stats is None:
        log("unconstrained pre-MPC matrix stats = not assembled")
    elif "diagnostic_error" not in unconstrained_matrix_stats:
        log(
            f"constrained/unconstrained nnz ratio = {constraint_matrix_transform['constrained_to_unconstrained_nnz_ratio']}"
        )
    if dtn_base_matrix_stats is not None:
        log(f"DtN augmented/base nnz ratio = {constraint_matrix_transform['dtn_augmented_to_base_nnz_ratio']}")

    live_observer_primal_snapshot = bool(
        dtn_solver_info is not None
        and dtn_solver_info.get("variable_p_live_observer_invoked")
    )
    if assemble_only_result:
        reason = 0
        reason_name = "ASSEMBLE_ONLY_SKIPPED_SOLVE"
        iterations = 0
        residual_norm = None
    elif factorization_only_result:
        reason = 0
        reason_name = "FACTORIZATION_ONLY_SKIPPED_SOLVE"
        iterations = 0
        residual_norm = None
    elif external_solver_snapshot or live_observer_primal_snapshot:
        reason = int(dtn_solver_info["ksp_converged_reason"])
        reason_name = _ksp_reason_name(reason)
        iterations = int(dtn_solver_info["ksp_iterations"])
        residual_norm = (
            None
            if external_solver_snapshot
            else float(dtn_solver_info["primal_ksp_residual_norm"])
        )
    else:
        reason = int(system_ksp.getConvergedReason())
        reason_name = _ksp_reason_name(reason)
        iterations = int(system_ksp.getIterationNumber())
        residual_norm = float(system_ksp.getResidualNorm())
    if external_solver_snapshot or live_observer_primal_snapshot:
        ksp_type = dtn_solver_info["actual_ksp_type"]
        pc_type = dtn_solver_info["actual_pc_type"]
        pc_factor_solver_type = dtn_solver_info[
            "actual_pc_factor_solver_type"
        ]
    else:
        ksp_type = system_ksp.getType()
        pc = system_ksp.getPC()
        pc_type = pc.getType()
        pc_factor_solver_type = _pc_factor_solver_type(pc)
    condensed_full_residual = (
        None
        if dtn_solver_info is None
        else (
            dtn_solver_info.get("cell_static_condensation") or {}
        ).get("full_explicit_true_residual")
    )
    linear_system_diagnostics = (
        {
            "linear_system_rhs_norm": None,
            "linear_system_solution_norm": None,
            "linear_system_residual_norm": None,
            "linear_system_relative_residual": None,
        }
        if diagnostic_only_result
        else condensed_full_residual
        if condensed_full_residual is not None
        else _linear_system_diagnostics(system_A, system_b, system_x)
    )
    external_rta_gate_pass = (
        None
        if not external_solver_snapshot
        else bool(dtn_solver_info["external_rta_gate_pass"])
    )
    solver_converged = (reason > 0) and not diagnostic_only_result
    official_result = solver_converged and (
        not external_solver_snapshot or external_rta_gate_pass is True
    )
    log(f"solver converged reason = {reason}")
    log(f"solver converged reason name = {reason_name}")
    log(f"solver iterations = {iterations}")
    log("solver residual norm = None" if residual_norm is None else f"solver residual norm = {residual_norm:.6e}")
    log(f"actual KSP type = {ksp_type}")
    log(f"actual PC type = {pc_type}")
    log(f"actual PC factor solver type = {pc_factor_solver_type}")
    log(f"linear system RHS norm = {linear_system_diagnostics['linear_system_rhs_norm']}")
    log(f"linear system solution norm = {linear_system_diagnostics['linear_system_solution_norm']}")
    log(f"linear system true relative residual = {linear_system_diagnostics['linear_system_relative_residual']}")
    variable_p_live_observer_invoked = bool(
        dtn_solver_info is not None
        and dtn_solver_info.get("variable_p_live_observer_invoked")
    )
    if variable_p_live_observer_invoked:
        _write_progress_event(
            out_dir,
            comm,
            stage="variable_p_live_observer",
            status="end",
            started=started,
            dofs=num_dofs,
            constraints=floquet_data.num_constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
            extra={
                "callback_lifetime": "borrowed_live_objects_only",
                "recovered_active_vectors_released_after_callback": True,
                "ordinary_default_changed": False,
            },
        )
    solver_objects_released_before_postprocess = bool(
        cfg.direct_release_solver_before_postprocess
        and solve_stage4_dtn_port
        and not diagnostic_only_result
        and reason > 0
        and system_A is not None
    )
    solver_release_audit = None
    if solver_objects_released_before_postprocess:
        released_objects = ["system Mat", "RHS Vec", "solution Vec"]
        if system_ksp is not None:
            system_ksp.destroy()
            released_objects.insert(0, "KSP/MUMPS factor")
        system_x.destroy()
        system_b.destroy()
        system_A.destroy()
        system_A = None
        system_b = None
        system_x = None
        system_ksp = None
        if dtn_result is not None:
            dtn_result["A"] = None
            dtn_result["b"] = None
            dtn_result["x"] = None
            dtn_result["ksp"] = None
        gc.collect()
        PETSc.garbage_cleanup(comm)
        gc.collect()
        local_heap_trim = _trim_process_heap()
        local_before_mb = local_heap_trim.get("rss_before_mb")
        local_after_mb = local_heap_trim.get("rss_after_mb")
        local_released_mb = local_heap_trim.get("rss_released_mb")
        before_by_rank = _gather_optional_rank_floats(comm, local_before_mb)
        after_by_rank = _gather_optional_rank_floats(comm, local_after_mb)
        released_by_rank = _gather_optional_rank_floats(
            comm, local_released_mb
        )
        solver_release_audit = {
            "petsc_garbage_cleanup_called": True,
            "process_heap_trim": {
                "implementation": local_heap_trim["implementation"],
                "supported_on_all_ranks": bool(
                    comm.allreduce(
                        bool(local_heap_trim["supported"]),
                        op=MPI.LAND,
                    )
                ),
                "succeeded_on_all_ranks": bool(
                    comm.allreduce(
                        bool(local_heap_trim["succeeded"]),
                        op=MPI.LAND,
                    )
                ),
                "call_completed_on_all_ranks": bool(
                    comm.allreduce(
                        bool(local_heap_trim["call_completed"]),
                        op=MPI.LAND,
                    )
                ),
                "allocator_reported_pages_released_by_rank": [
                    bool(value)
                    for value in comm.allgather(
                        bool(
                            local_heap_trim[
                                "allocator_reported_pages_released"
                            ]
                        )
                    )
                ],
                "return_codes_by_rank": [
                    int(value)
                    for value in comm.allgather(
                        int(local_heap_trim["return_code"] or 0)
                    )
                ],
                "current_rss_before_mb_by_rank": before_by_rank,
                "current_rss_after_mb_by_rank": after_by_rank,
                "current_rss_released_mb_by_rank": released_by_rank,
                "sum_rss_before_mb": _complete_rank_sum(before_by_rank),
                "sum_rss_after_mb": _complete_rank_sum(after_by_rank),
                "sum_rss_released_mb": _complete_rank_sum(
                    released_by_rank
                ),
                "rss_measurement_semantics": (
                    "diagnostic in-process phase-local rank samples; not "
                    "external synchronized process-tree RSS/PSS/USS authority"
                ),
                "ordinary_default_changed": False,
            },
        }
        _write_progress_event(
            out_dir,
            comm,
            stage="solver_objects_released_before_postprocess",
            status="end",
            started=started,
            dofs=num_dofs,
            constraints=(
                None
                if floquet_data is None
                else floquet_data.num_constraints
            ),
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
            extra={
                "released_objects": released_objects,
                "ordinary_default_changed": False,
                **solver_release_audit,
            },
        )
    else:
        _write_progress_event(
            out_dir,
            comm,
            stage="solver_objects_retained_for_postprocess",
            status="end",
            started=started,
            dofs=num_dofs,
            constraints=(
                None
                if floquet_data is None
                else floquet_data.num_constraints
            ),
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
            extra={
                "lifecycle_note": (
                    "External solver-port callback owned temporary solver objects; "
                    "no KSP/MUMPS factor is retained."
                    if external_solver_snapshot
                    else
                    "Telemetry-only baseline preserves the Task28 lifecycle: "
                    "KSP/factor, system Mat, RHS Vec, and solution Vec remain "
                    "referenced during postprocess."
                )
            },
        )

    elapsed = float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))
    stage4_boundary_model = cfg.stage4_boundary_model.lower() if cfg.stage_case.startswith("stage4_") else None
    summary = {
        "case_name": cfg.case_name,
        "stage": _stage_label(cfg),
        **_summary_base_fields(cfg, comm),
        "config": cfg.as_jsonable(),
        "case_status": "diagnostic_assemble_only"
        if assemble_only_result
        else "diagnostic_factorization_only"
        if factorization_only_result
        else "completed"
        if official_result
        else "external_solver_not_converged"
        if external_solver_snapshot and not solver_converged
        else "external_residual_gate_failed"
        if external_solver_snapshot and external_rta_gate_pass is False
        else "failed_not_converged",
        "official_result": official_result,
        "diagnostic_only": not official_result,
        "postprocess_skipped": not official_result,
        "postprocess_skip_reason": None
        if official_result
        else "Matrix diagnostics assemble-only mode skipped LU factorization/solve."
        if assemble_only_result
        else "Matrix diagnostics factorization-only mode stopped after KSPSetUp/LU; KSPSolve and postprocess were skipped."
        if factorization_only_result
        else "External solver did not converge; official RTA was not run."
        if external_solver_snapshot and not solver_converged
        else "External solver residual/RTA gate failed; official RTA was not run."
        if external_solver_snapshot and external_rta_gate_pass is False
        else "PETSc KSP did not converge.",
        "num_mesh_cells": int(num_cells),
        "variable_p_mesh_identity": variable_p_mesh_identity,
        "stage4_local_h_mesh_audit": local_h_mesh_audit,
        "num_nedelec_dofs": int(num_dofs),
        "matrix_stats": matrix_stats,
        "unconstrained_matrix_stats": unconstrained_matrix_stats,
        "constraint_matrix_transform": constraint_matrix_transform,
        "explicit_chac_constructed": explicit_chac_constructed,
        "chac_nnz_before": None,
        "chac_nnz_after": None,
        "constrained_linear_system_size": int(matrix_stats["matrix_rows"]),
        "petsc_scalar_type": str(PETSc.ScalarType),
        "dolfinx_default_scalar_type": str(default_scalar_type),
        "solver_backend": solver_backend,
        "field_formulation": field_formulation,
        "stage4_boundary_model": stage4_boundary_model,
        "stage4_dtn_port_enabled": bool(solve_stage4_dtn_port),
        "stage4_full3d_assembly_backend_requested": (
            cfg.stage4_full3d_assembly_backend
            if dtn_solver_info is None
            else dtn_solver_info.get(
                "stage4_full3d_assembly_backend_requested",
                cfg.stage4_full3d_assembly_backend,
            )
        ),
        "stage4_full3d_assembly_backend_actual": (
            None
            if dtn_solver_info is None
            else dtn_solver_info.get(
                "stage4_full3d_assembly_backend_actual"
            )
        ),
        "stage4_full3d_assembly_backend_selection_source": (
            None
            if dtn_solver_info is None
            else dtn_solver_info.get(
                "stage4_full3d_assembly_backend_selection_source"
            )
        ),
        "stage4_full3d_assembly_backend_qualification": (
            None
            if dtn_solver_info is None
            else dtn_solver_info.get(
                "stage4_full3d_assembly_backend_qualification"
            )
        ),
        "stage4_full3d_assembly_backend_audit": (
            None
            if dtn_solver_info is None
            else dtn_solver_info.get(
                "stage4_full3d_assembly_backend_audit"
            )
        ),
        "stage4_dtn_order_policy": cfg.stage4_dtn_order_policy if solve_stage4_dtn_port else None,
        "stage4_dtn_assembly": cfg.stage4_dtn_assembly if solve_stage4_dtn_port else None,
        "stage4_dtn_num_auxiliary_dofs": None
        if dtn_result is None
        else dtn_result["solver_info"].get("num_auxiliary_dofs"),
        "stage4_dtn_auxiliary_block_stats": dtn_auxiliary_block_stats,
        "stage4_dtn_factor_inventory": None
        if dtn_solver_info is None
        else dtn_solver_info.get("factor_inventory"),
        "stage4_dtn_ksp_setup_seconds": None
        if dtn_solver_info is None
        else dtn_solver_info.get("ksp_setup_seconds"),
        "stage4_dtn_ksp_solve_seconds": None
        if dtn_solver_info is None
        else dtn_solver_info.get("ksp_solve_seconds"),
        "stage4_dtn_base_matrix_stats": dtn_base_matrix_stats,
        "stage4_dtn_augmented_matrix_stats_after_finalize": dtn_augmented_matrix_stats,
        "stage4_dtn_condensed_matrix_stats": dtn_condensed_matrix_stats,
        "stage4_dtn_floquet_independent_matrix_stats": (
            dtn_floquet_independent_matrix_stats
        ),
        "stage4_cell_static_condensation": False
        if dtn_solver_info is None
        else bool(dtn_solver_info.get("stage4_cell_static_condensation")),
        "stage4_assembly_time_cell_static_condensation": False
        if dtn_solver_info is None
        else bool(
            dtn_solver_info.get(
                "stage4_assembly_time_cell_static_condensation"
            )
        ),
        "stage4_variable_p_active": False
        if dtn_solver_info is None
        else bool(dtn_solver_info.get("stage4_variable_p_active")),
        "stage4_local_h_active": bool(
            local_h_context is not None
            or (
                dtn_solver_info is not None
                and dtn_solver_info.get("stage4_local_h_active")
            )
        ),
        "stage4_local_h_constraint_audit": None
        if dtn_solver_info is None
        else dtn_solver_info.get("stage4_local_h_constraint_audit"),
        "num_actual_conforming_active_fe_dofs": None
        if dtn_solver_info is None
        else dtn_solver_info.get(
            "num_actual_conforming_active_fe_dofs"
        ),
        "num_raw_broken_active_fe_dofs": None
        if dtn_solver_info is None
        else dtn_solver_info.get("num_raw_broken_active_fe_dofs"),
        "num_active_trace_dofs": None
        if dtn_solver_info is None
        else dtn_solver_info.get("num_active_trace_dofs"),
        "num_active_condensed_dofs": None
        if dtn_solver_info is None
        else dtn_solver_info.get("num_active_condensed_dofs"),
        "num_active_exact_sequence_fe_dofs": None
        if dtn_solver_info is None
        else dtn_solver_info.get("num_active_exact_sequence_fe_dofs"),
        "num_storage_carrier_fe_dofs": None
        if dtn_solver_info is None
        else dtn_solver_info.get("num_storage_carrier_fe_dofs"),
        "num_independent_trace_rows": None
        if dtn_solver_info is None
        else dtn_solver_info.get("num_independent_trace_rows"),
        "num_augmented_rows": None
        if dtn_solver_info is None
        else dtn_solver_info.get("num_augmented_rows"),
        "dof_row_semantics": None
        if dtn_solver_info is None
        else dtn_solver_info.get("dof_row_semantics"),
        "stage4_dtn_variable_p_auxiliary_interior_columns_allocated": None
        if dtn_solver_info is None
        else dtn_solver_info.get(
            "stage4_dtn_variable_p_auxiliary_interior_columns_allocated"
        ),
        "stage4_dtn_variable_p_auxiliary_interior_column_bytes_local_max": None
        if dtn_solver_info is None
        else dtn_solver_info.get(
            "stage4_dtn_variable_p_auxiliary_interior_column_bytes_local_max"
        ),
        "stage4_dtn_variable_p_trace_functional_count": None
        if dtn_solver_info is None
        else dtn_solver_info.get(
            "stage4_dtn_variable_p_trace_functional_count"
        ),
        "stage4_dtn_variable_p_removed_interior_max_abs": None
        if dtn_solver_info is None
        else dtn_solver_info.get(
            "stage4_dtn_variable_p_removed_interior_max_abs"
        ),
        "stage4_dtn_variable_p_trace_only_gate_pass": None
        if dtn_solver_info is None
        else dtn_solver_info.get(
            "stage4_dtn_variable_p_trace_only_gate_pass"
        ),
        "stage4_floquet_slave_elimination": False
        if dtn_solver_info is None
        else bool(
            dtn_solver_info.get("stage4_floquet_slave_elimination")
        ),
        "direct_release_solver_before_postprocess": bool(
            cfg.direct_release_solver_before_postprocess
        ),
        "solver_objects_released_before_postprocess": (
            solver_objects_released_before_postprocess
        ),
        "solver_release_audit": solver_release_audit,
        "cell_static_condensation": None
        if dtn_solver_info is None
        else dtn_solver_info.get("cell_static_condensation"),
        "strong_z_boundary_dirichlet_enabled": bool(apply_strong_boundary_bc),
        "strong_z_boundary_dirichlet_dofs": int(boundary_dofs_global),
        "strong_z_boundary_dirichlet_raw_dofs_global": int(raw_boundary_dofs_global),
        "strong_z_boundary_dirichlet_dofs_global": int(boundary_dofs_global),
        "incident_added_to_solution": field_formulation in {"incident_correction", "incident_scattered"},
        "incident_port_used_for_solution": bool(solve_stage4_dtn_port),
        "background_added_to_solution": field_formulation == "layered_scattered",
        "background_zeroed_in_pml_for_stage4_output": bool(solve_layered_scattered),
        "reference_added_to_solution": field_formulation == "reference_correction",
        "fresnel_reference_used_for_solution": False,
        "fresnel_reference_used_for_comparison_only": cfg.geometry_kind
        in {"fresnel_interface", "rectangular_block_grating"},
        "rhs_source_region": (
            "physical_substrate"
            if solve_incident_scattered
            else "physical_grating"
            if solve_layered_scattered
            else None
        ),
        "rhs_source_sign": (
            "+k0^2*(eps_sub-eps_air)*inner(E_inc,v)"
            if solve_incident_scattered
            else "+k0^2*(eps_true-eps_bg)*inner(E_bg,v)"
            if solve_layered_scattered
            else None
        ),
        "rhs_source_contrast": (
            complex(cfg.substrate_index**2 - cfg.eps_r)
            if solve_incident_scattered
            else complex(cfg.eps_grating - cfg.grating_background_eps)
            if solve_layered_scattered
            else None
        ),
        "rhs_source_tag_ids": (
            {"substrate": cfg.tags.substrate}
            if solve_incident_scattered
            else {"grating": cfg.tags.grating}
            if solve_layered_scattered
            else {}
        ),
        "rhs_source_tag_volumes": (
            {"substrate": domain_tag_volumes["substrate"]}
            if solve_incident_scattered
            else {"grating": domain_tag_volumes["grating"]}
            if solve_layered_scattered
            else {}
        ),
        "rhs_source_excludes_air_and_pml": bool(solve_incident_scattered or solve_layered_scattered),
        "rhs_source_norm": rhs_source_norm,
        "unconstrained_rhs_norm": unconstrained_rhs_norm,
        "domain_tag_volumes": domain_tag_volumes,
        "linear_solve_method": (
            "external_linear_solver_port"
            if external_solver_snapshot
            else "direct_lu"
        ),
        "petsc_direct_solver_profile": (
            None
            if external_solver_snapshot
            else cfg.petsc_direct_solver_profile_requested
        ),
        "matrix_diagnostics_assemble_only": bool(assemble_only_result),
        "matrix_diagnostics_factorization_only": bool(
            factorization_only_result
        ),
        "linear_solve_petsc_options": petsc_options,
        "linear_solve_disabled_reason": None,
        "actual_ksp_type": ksp_type,
        "actual_pc_type": pc_type,
        "actual_pc_factor_solver_type": pc_factor_solver_type,
        "selected_parallel_lu_solver_type": selected_parallel_lu,
        "ksp_converged": solver_converged,
        "ksp_converged_reason": reason,
        "ksp_converged_reason_name": reason_name,
        "ksp_iterations": iterations,
        "solver_residual_norm": residual_norm,
        **linear_system_diagnostics,
        "use_floquet_xy": cfg.use_floquet_xy,
        "use_pml": cfg.use_pml,
        "floquet_num_local_slaves": None if floquet_data is None else floquet_data.num_local_slaves,
        "floquet_num_local_slave_records_seen": None
        if floquet_data is None
        else floquet_data.num_local_slave_records_seen,
        "floquet_num_local_ghost_slave_constraints": None
        if floquet_data is None
        else floquet_data.num_local_ghost_slave_constraints,
        "floquet_num_global_ghost_slave_constraints": None
        if floquet_data is None
        else floquet_data.num_global_ghost_slave_constraints,
        "floquet_num_local_ghost_slave_records_skipped": None
        if floquet_data is None
        else floquet_data.num_local_ghost_slave_records_skipped,
        "floquet_num_global_ghost_slave_records_skipped": None
        if floquet_data is None
        else floquet_data.num_global_ghost_slave_records_skipped,
        "floquet_constraint_mode_resolved": None if floquet_data is None else floquet_data.constraint_mode_resolved,
        "floquet_raw_map_nnz": None if floquet_data is None else floquet_data.raw_map_nnz,
        "floquet_max_masters_per_slave": None if floquet_data is None else floquet_data.max_masters_per_slave,
        "floquet_estimated_constraint_memory_mb": None
        if floquet_data is None
        else floquet_data.estimated_constraint_memory_mb,
        "floquet_topology_cache_hit": None
        if floquet_data is None
        else floquet_data.topology_cache_hit,
        "floquet_topology_build_seconds_current": None
        if floquet_data is None
        else floquet_data.topology_build_seconds_current,
        "floquet_phase_update_seconds": None
        if floquet_data is None
        else floquet_data.phase_update_seconds,
        "floquet_communication_bytes_sent_current": None
        if floquet_data is None
        else floquet_data.communication_bytes_sent_current,
        "floquet_communication_bytes_received_current": None
        if floquet_data is None
        else floquet_data.communication_bytes_received_current,
        "floquet_used_full_boundary_gather": None
        if floquet_data is None
        else floquet_data.used_full_boundary_gather,
        "floquet_created_dense_boundary_square": None
        if floquet_data is None
        else floquet_data.created_dense_boundary_square,
        "floquet_num_slave_edges": None if floquet_data is None else floquet_data.num_slave_edges,
        "floquet_num_matched_master_edges": None if floquet_data is None else floquet_data.num_matched_master_edges,
        "floquet_num_slave_faces": None if floquet_data is None else floquet_data.num_slave_faces,
        "floquet_num_matched_master_faces": None if floquet_data is None else floquet_data.num_matched_master_faces,
        "floquet_num_constraints": None if floquet_data is None else floquet_data.num_constraints,
        "floquet_num_edge_constraints": None if floquet_data is None else floquet_data.num_edge_constraints,
        "floquet_num_face_constraints": None if floquet_data is None else floquet_data.num_face_constraints,
        "floquet_num_face_transform_fits": None if floquet_data is None else floquet_data.num_face_transform_fits,
        "floquet_max_face_transform_fit_residual": None
        if floquet_data is None
        else floquet_data.max_face_transform_fit_residual,
        "floquet_max_edge_midpoint_pairing_error": None
        if floquet_data is None
        else floquet_data.max_edge_midpoint_pairing_error,
        "floquet_max_face_midpoint_pairing_error": None
        if floquet_data is None
        else floquet_data.max_face_midpoint_pairing_error,
        "floquet_num_x_constraints": None if floquet_data is None else floquet_data.num_x_constraints,
        "floquet_num_y_constraints": None if floquet_data is None else floquet_data.num_y_constraints,
        "floquet_num_corner_constraints": None if floquet_data is None else floquet_data.num_corner_constraints,
        "mesh_cell_type_actual": mesh_data.mesh_cell_type_resolved,
        "mesh_cells_resolved": list(mesh_data.mesh_cells_resolved),
        "mesh_spacing_mode_resolved": mesh_data.mesh_spacing_mode_resolved,
        "mesh_axis_cell_stats": mesh_data.mesh_axis_cell_stats,
        "mesh_material_plane_alignment": mesh_data.material_plane_alignment,
        "mesh_local_refinement_regions": mesh_data.local_refinement_regions,
        "mesh_z_alignment_warnings": mesh_data.z_alignment_warnings,
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
        "floquet_constraint_timings_seconds": None if floquet_data is None else floquet_data.timings_seconds,
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
        "max_rss_mb": _global_max_rss_mb(comm),
        "total_peak_rss_mb": _global_total_peak_rss_mb(comm),
        "mumps_ooc_runtime": {
            **ooc_info,
            **_retain_mumps_ooc_directory_on_failure(ooc_info),
        },
    }
    summary["sum_rank_historical_peaks_mb_upper_bound"] = summary[
        "total_peak_rss_mb"
    ]
    summary["total_peak_rss_semantics"] = (
        "sum_rank_historical_peaks_upper_bound_not_simultaneous"
    )
    if variable_p_live_observer is not None:
        summary.update(
            {
                "variable_p_live_observer_requested": True,
                "variable_p_live_observer_invoked": (
                    variable_p_live_observer_invoked
                ),
                "variable_p_live_observer_contract": (
                    "controlled_collective_callback_borrowed_objects"
                ),
                "variable_p_retain_local_schur_for_research": bool(
                    variable_p_retain_local_schur_for_research
                ),
                "variable_p_local_schur_release": (
                    None
                    if dtn_solver_info is None
                    else dtn_solver_info.get(
                        "variable_p_local_schur_release"
                    )
                ),
            }
        )

    if external_solver_snapshot:
        summary.update(
            {
                "external_linear_solver_port": True,
                "external_rta_gate_pass": external_rta_gate_pass,
                "external_reported_relative_residual": dtn_solver_info[
                    "reported_relative_residual"
                ],
                "external_condensed_true_residual": dtn_solver_info[
                    "condensed_true_residual"
                ],
                "external_full_augmented_true_residual": dtn_solver_info[
                    "full_augmented_true_residual"
                ],
                "external_residual_limit": dtn_solver_info[
                    "residual_limit"
                ],
                "external_no_global_factor": dtn_solver_info[
                    "no_global_factor"
                ],
                "external_solver_profile": dtn_solver_info[
                    "solver_profile"
                ],
                "external_assembled_matrix_released_before_solve": (
                    dtn_solver_info[
                        "assembled_matrix_released_before_solve"
                    ]
                ),
                "external_reduced_residual_norm": dtn_solver_info[
                    "reduced_residual_norm"
                ],
            }
        )

    if not official_result:
        summary["mumps_ooc_runtime"] = {
            **ooc_info,
            **_retain_mumps_ooc_directory_on_failure(ooc_info, log),
        }
        _clear_official_field_outputs(out_dir, comm)
        if assemble_only_result:
            log("Matrix diagnostics assemble-only mode: LU factorization/solve and field postprocess were skipped.")
        elif factorization_only_result:
            log(
                "Matrix diagnostics factorization-only mode: KSPSetUp/LU completed; "
                "KSPSolve and field postprocess were skipped."
            )
        elif external_solver_snapshot and not solver_converged:
            log(
                "WARNING: external solver did not converge; "
                "official RTA was not run."
            )
        elif external_solver_snapshot and external_rta_gate_pass is False:
            log(
                "WARNING: external solver residual/RTA gate failed; "
                "official RTA was not run."
            )
        else:
            log("WARNING: PETSc KSP did not converge.")
        _log_solver_summary(summary, log)
        log(f"elapsed seconds = {elapsed:.3f}")
        _write_case_outputs(out_dir, summary, log_lines, comm)
        return summary

    stage_start = _start_timed_stage(comm)
    field_metrics = save_airbox_3d_fields(
        mesh_data,
        cfg,
        E_total,
        out_dir,
        E_scattered=E_sca if solve_layered_scattered else None,
        E_background=E_background_solution if solve_layered_scattered else None,
        E_incident_port=E_incident_solution if solve_stage4_dtn_port else None,
    )
    _finish_timed_stage(comm, timings, "postprocess", stage_start, log)
    summary["timings_seconds"] = timings
    summary["elapsed_seconds"] = float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))
    summary["max_rss_mb"] = _global_max_rss_mb(comm)
    summary["total_peak_rss_mb"] = _global_total_peak_rss_mb(comm)
    summary["sum_rank_historical_peaks_mb_upper_bound"] = summary["total_peak_rss_mb"]
    summary["total_peak_rss_semantics"] = "sum_rank_historical_peaks_upper_bound_not_simultaneous"
    summary["total_peak_rss_gb"] = (
        None if summary["total_peak_rss_mb"] is None else summary["total_peak_rss_mb"] / 1024.0
    )
    summary.update(field_metrics)
    _write_progress_event(
        out_dir,
        comm,
        stage="after_field_output",
        status="end",
        started=started,
        dofs=num_dofs,
        constraints=None if floquet_data is None else floquet_data.num_constraints,
        petsc_options=petsc_options,
    )

    if solve_incident_scattered:
        summary["E_sca_norm"] = _function_coefficient_norm(E_sca)
        summary["E_inc_norm"] = _function_coefficient_norm(E_incident_solution)
        summary["E_bg_norm"] = None
        summary["E_total_norm"] = _function_coefficient_norm(E_total)
    elif solve_layered_scattered:
        summary["E_sca_norm"] = _function_coefficient_norm(E_sca)
        summary["E_inc_norm"] = None
        summary["E_bg_norm"] = _function_coefficient_norm(E_background_solution)
        summary["E_total_norm"] = _function_coefficient_norm(E_total)
    else:
        summary["E_sca_norm"] = None
        summary["E_inc_norm"] = _function_coefficient_norm(E_incident_solution) if solve_stage4_dtn_port else None
        summary["E_bg_norm"] = None
        summary["E_total_norm"] = _function_coefficient_norm(E)

    stage2_metrics: dict[str, Any] = {}
    if floquet_data is not None:
        stage2_metrics.update(_floquet_probe_metrics(floquet_data))
    if cfg.use_pml and solve_layered_scattered:
        stage2_metrics.update(_stage4_scattered_pml_metrics(E_sca, cfg))
    elif cfg.use_pml:
        stage2_metrics.update(_pml_probe_metrics(E_total, cfg))
    stage2_metrics.update(_stage2_reference_metrics(E_total, cfg, field_metrics))
    summary.update(stage2_metrics)

    port_power_metrics: dict[str, Any] | None = None
    probe_power_metrics: dict[str, Any] | None = None
    volume_absorption_metrics: dict[str, Any] | None = None
    if solve_stage4_dtn_port and dtn_result is not None:
        port_power_metrics = dtn_result["port_metrics"]
        summary.update(port_power_metrics)
        stage_start = _start_timed_stage(comm)
        probe_power_metrics = compute_diffraction_orders_3d(
            mesh_data,
            cfg,
            E_total,
            out_dir,
            E_scattered=E_sca if solve_layered_scattered else None,
        )
        _finish_timed_stage(comm, timings, "diffraction_postprocess", stage_start, log)
        probe_R = probe_power_metrics.get("R_total")
        probe_T = probe_power_metrics.get("T_total")
        flux_R = probe_power_metrics.get("R_total_from_net_flux")
        flux_T = probe_power_metrics.get("T_total_from_net_flux")
        summary.update(
            {
                "probe_R_total": probe_R,
                "probe_T_total": probe_T,
                "probe_A_balance": probe_power_metrics.get("A_balance"),
                "probe_power_file": probe_power_metrics.get("probe_power_file"),
                "R_total_diagnostic_eh_fourier": probe_power_metrics.get("R_total_diagnostic_eh_fourier", probe_R),
                "T_total_diagnostic_eh_fourier": probe_power_metrics.get("T_total_diagnostic_eh_fourier", probe_T),
                "A_balance_diagnostic_eh_fourier": probe_power_metrics.get(
                    "A_balance_diagnostic_eh_fourier",
                    probe_power_metrics.get("A_balance"),
                ),
                "R_plus_T_diagnostic_eh_fourier": probe_power_metrics.get(
                    "R_plus_T_diagnostic_eh_fourier",
                    probe_power_metrics.get("R_plus_T"),
                ),
                "diagnostic_eh_fourier_probe_power_source": probe_power_metrics.get("power_source"),
                "probe_top_z": probe_power_metrics.get("diffraction_top_probe_z"),
                "probe_bottom_z": probe_power_metrics.get("diffraction_bottom_probe_z"),
                "diagnostic_eh_minus_dtn_R": None if probe_R is None else float(probe_R - summary["R_total"]),
                "diagnostic_eh_minus_dtn_T": None if probe_T is None else float(probe_T - summary["T_total"]),
                "diff_vs_dtn_R": None if probe_R is None else float(probe_R - summary["R_total"]),
                "diff_vs_dtn_T": None if probe_T is None else float(probe_T - summary["T_total"]),
                "flux_R_total": flux_R,
                "flux_T_total": flux_T,
                "flux_A_balance": probe_power_metrics.get("A_balance_from_net_flux"),
                "R_total_diagnostic_sampled_net_flux": probe_power_metrics.get(
                    "R_total_diagnostic_sampled_net_flux",
                    flux_R,
                ),
                "T_total_diagnostic_sampled_net_flux": probe_power_metrics.get(
                    "T_total_diagnostic_sampled_net_flux",
                    flux_T,
                ),
                "A_balance_diagnostic_sampled_net_flux": probe_power_metrics.get(
                    "A_balance_diagnostic_sampled_net_flux",
                    probe_power_metrics.get("A_balance_from_net_flux"),
                ),
                "flux_power_file": probe_power_metrics.get("flux_power_file"),
            }
        )
        summary.update(_stage4_lossless_energy_balance_check(cfg, summary))
    elif run_diffraction_postprocess:
        stage_start = _start_timed_stage(comm)
        probe_power_metrics = compute_diffraction_orders_3d(
            mesh_data,
            cfg,
            E_total,
            out_dir,
            E_scattered=E_sca if solve_layered_scattered else None,
        )
        _finish_timed_stage(comm, timings, "diffraction_postprocess", stage_start, log)
        summary.update(probe_power_metrics)
        summary.update(_stage4_lossless_energy_balance_check(cfg, summary))
        summary["timings_seconds"] = timings

    incident_power_for_absorption = (
        None if port_power_metrics is None else port_power_metrics.get("incident_power_code_units")
    )
    if incident_power_for_absorption is None and probe_power_metrics is not None:
        incident_power_for_absorption = probe_power_metrics.get("incident_power_code_units")
    if (
        cfg.stage_case in {"stage4_flat_layer_sanity", "stage4_block_grating"}
        and incident_power_for_absorption is not None
    ):
        stage_start = _start_timed_stage(comm)
        volume_absorption_metrics = compute_volume_absorption_3d(
            mesh_data,
            cfg,
            E_total,
            out_dir,
            incident_power=float(incident_power_for_absorption),
            port_metrics=port_power_metrics,
            probe_metrics=probe_power_metrics,
        )
        _finish_timed_stage(comm, timings, "volume_absorption_postprocess", stage_start, log)
        summary.update(
            {
                "volume_absorption_file": "volume_absorption.json",
                "A_volume_grating": volume_absorption_metrics.get("A_volume_grating"),
                "A_volume_substrate": volume_absorption_metrics.get("A_volume_substrate"),
                "A_volume_total": volume_absorption_metrics.get("A_volume_total"),
                "A_port_balance_minus_A_volume_total": volume_absorption_metrics.get(
                    "A_port_balance_minus_A_volume_total"
                ),
                "A_probe_balance_minus_A_volume_total": volume_absorption_metrics.get(
                    "A_probe_balance_minus_A_volume_total"
                ),
                "A_flux_minus_A_volume_total": volume_absorption_metrics.get("A_flux_minus_A_volume_total"),
                "energy_closure_error_port_volume": volume_absorption_metrics.get("energy_closure_error_port_volume"),
            }
        )
        closure_fields = _merge_volume_closure_into_dtn_port_outputs(
            out_dir,
            comm,
            port_metrics=port_power_metrics,
            volume_metrics=volume_absorption_metrics,
        )
        summary.update(closure_fields)

    if cfg.stage_case in {"stage4_flat_layer_sanity", "stage4_block_grating"}:
        power_summary_rows = write_power_summary_csv(
            out_dir,
            comm,
            port_metrics=port_power_metrics,
            probe_metrics=probe_power_metrics,
            volume_metrics=volume_absorption_metrics,
        )
        summary["power_summary_csv"] = "power_summary.csv"
        summary["power_summary_rows"] = power_summary_rows
        summary["timings_seconds"] = timings

    _write_progress_event(
        out_dir,
        comm,
        stage="after_official_rta_and_volume_absorption",
        status="end",
        started=started,
        dofs=num_dofs,
        constraints=None if floquet_data is None else floquet_data.num_constraints,
        petsc_options=petsc_options,
        extra={
            "R_total": summary.get("R_total"),
            "T_total": summary.get("T_total"),
            "A_volume_total": summary.get("A_volume_total"),
            "energy_closure_error": summary.get("energy_closure_error_port_volume"),
        },
    )

    if cfg.stage_case == "stage4_flat_layer_sanity":
        flat_reference_outputs = write_flat_layer_reference_outputs(
            out_dir,
            cfg,
            comm,
            port_metrics=port_power_metrics,
            probe_metrics=probe_power_metrics,
            volume_metrics=volume_absorption_metrics,
        )
        summary.update(
            {
                "flat_layer_reference_file": flat_reference_outputs["flat_layer_reference_file"],
                "power_consistency_file": flat_reference_outputs["power_consistency_file"],
                "flat_layer_reference_R_ref": flat_reference_outputs["flat_layer_reference"]["R_ref"],
                "flat_layer_reference_T_ref": flat_reference_outputs["flat_layer_reference"][
                    "T_ref_at_bottom_reference_plane"
                ],
                "flat_layer_reference_A_ref": flat_reference_outputs["flat_layer_reference"][
                    "A_ref_between_reference_planes"
                ],
                "flat_layer_reference_T_ref_at_bottom_port_plane": flat_reference_outputs["flat_layer_reference"][
                    "T_ref_at_bottom_port_plane"
                ],
                "flat_layer_reference_A_ref_between_port_planes": flat_reference_outputs["flat_layer_reference"][
                    "A_ref_between_port_planes"
                ],
                "power_consistency": flat_reference_outputs["power_consistency"],
            }
        )

    if summary.get("stage4_energy_balance_pass") is False:
        summary["official_result"] = False
        summary["diagnostic_only"] = True
        summary["case_status"] = "failed_stage4_energy_balance"
        summary["postprocess_skipped"] = False
        summary["postprocess_skip_reason"] = None

    if solution_observer is not None:
        solution_observer(
            field=E_total,
            mesh_data=mesh_data,
            config=cfg,
            floquet_data=floquet_data,
            summary=summary,
            linear_system={
                "A": system_A,
                "b": system_b,
                "x": system_x,
                "ksp": system_ksp,
            },
            dtn_result=dtn_result,
        )

    if summary.get("case_status") == "completed":
        summary["mumps_ooc_runtime"] = {
            **ooc_info,
            **_cleanup_mumps_ooc_directory_on_success(ooc_info, comm, log),
        }
    else:
        summary["mumps_ooc_runtime"] = {
            **ooc_info,
            **_retain_mumps_ooc_directory_on_failure(ooc_info, log),
        }

    has_power_metrics = (
        {"R_total", "T_total", "R_plus_T"}.issubset(summary)
        and summary.get("R_total") is not None
        and summary.get("T_total") is not None
        and summary.get("R_plus_T") is not None
    )
    if comm.rank == 0 and has_power_metrics and cfg.geometry_kind != "rectangular_block_grating":
        (out_dir / "power_metrics_3d.json").write_text(
            json.dumps(
                {
                    key: summary[key]
                    for key in (
                        "R_total",
                        "T_total",
                        "R_plus_T",
                        "fresnel_R",
                        "fresnel_T",
                        "fresnel_R_error",
                        "fresnel_T_error",
                    )
                    if key in summary
                },
                ensure_ascii=False,
                indent=2,
                default=_json_default,
            ),
            encoding="utf-8",
        )

    log(f"max |E| = {field_metrics['max_abs_E']:.6e}")
    log(
        "max component |Ex|/|Ey|/|Ez| = "
        f"{field_metrics['max_abs_Ex']:.6e} / {field_metrics['max_abs_Ey']:.6e} / {field_metrics['max_abs_Ez']:.6e}"
    )
    if field_metrics.get("exact_reference_available"):
        log(f"plane-wave relative max error = {field_metrics['relative_max_abs_E_error']:.6e}")
        log(f"H relative max error = {field_metrics['relative_max_abs_H_error']:.6e}")
    else:
        log("exact reference unavailable for this case; E_exact/H_exact error fields are not written.")
    log(f"max |H| = {field_metrics['max_abs_H']:.6e}")
    log(f"Poynting direction cosine = {field_metrics['poynting_direction_cosine']:.6e}")
    if floquet_data is not None:
        log(f"Floquet x-face mismatch = {summary['floquet_x_face_mismatch']:.6e}")
        log(f"Floquet y-face mismatch = {summary['floquet_y_face_mismatch']:.6e}")
        log(f"Floquet edge/corner mismatch = {summary['floquet_edge_corner_mismatch']:.6e}")
    if cfg.use_pml:
        if summary.get("pml_reflection_proxy") is not None:
            log(f"PML reflection proxy = {summary['pml_reflection_proxy']:.6e}")
        if summary.get("pml_metric_field"):
            log(f"PML metric field = {summary['pml_metric_field']}")
        log(f"PML top decay ratio = {summary['pml_decay_ratio_top']}")
        log(f"PML bottom decay ratio = {summary['pml_decay_ratio_bottom']}")
    if cfg.geometry_kind == "fresnel_interface":
        log(f"Numerical R/T = {summary['R_total']:.6e} / {summary['T_total']:.6e}")
        log(f"Fresnel R/T = {summary['fresnel_R']:.6e} / {summary['fresnel_T']:.6e}")
        log(f"R+T = {summary['R_plus_T']:.6e}")
    if cfg.geometry_kind == "rectangular_block_grating":
        log(f"Stage-4 primary power source = {summary.get('diffraction_total_power_source')}")
        log(f"Stage-4 primary R/T = {summary['R_total']:.6e} / {summary['T_total']:.6e}")
        log(f"Stage-4 primary R+T = {summary['R_plus_T']:.6e}")
        log(f"Stage-4 primary A_balance = {summary['A_balance']:.6e}")
        if summary.get("probe_R_total") is not None:
            log(f"Stage-4 probe E/H Fourier R/T = {summary['probe_R_total']:.6e} / {summary['probe_T_total']:.6e}")
        if summary.get("flux_R_total") is not None:
            log(f"Stage-4 sampled net-flux R/T = {summary['flux_R_total']:.6e} / {summary['flux_T_total']:.6e}")
        if summary.get("A_volume_total") is not None:
            log(f"Stage-4 material A_volume_total = {summary['A_volume_total']:.6e}")
            log(f"Stage-4 port-volume closure error = {summary.get('energy_closure_error_port_volume')}")
        if summary.get("stage4_material_absorption_present"):
            log(f"3D diffraction absorption from balance = {summary.get('stage4_absorption_from_balance'):.6e}")
    log(f"ParaView file = {field_metrics['paraview_file']}")
    log("timing summary seconds:")
    for name, value in timings.items():
        log(f"  {name}: {value:.3f}")
    _log_solver_summary(summary, log)
    log(f"elapsed seconds = {summary['elapsed_seconds']:.3f}")
    _write_progress_event(
        out_dir,
        comm,
        stage="final_cleanup",
        status="end",
        started=started,
        dofs=num_dofs,
        constraints=None if floquet_data is None else floquet_data.num_constraints,
        petsc_options=petsc_options,
    )
    _write_case_outputs(out_dir, summary, log_lines, comm)
    return summary
