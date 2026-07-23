"""Actual goal-weighted periodic tetra adaptive cycles for Task035."""

from __future__ import annotations

from dataclasses import replace
import gc
import math
from pathlib import Path
import time
from typing import Any

from mpi4py import MPI

from src.adaptivity.goal_weighted_two_level import (
    run_target_goal_weighted_two_level,
)
from src.adaptivity.periodic_tetra_refinement import (
    refine_periodic_marked_tetra_mesh,
)
from src.adaptivity.target_r5_adaptive_cycles import (
    task034_best_available_observable_reference,
)
from src.common.config_3d import target_stage4_config
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.geometry.tetra_mesh_audit import audit_periodic_tetra_mesh


OBSERVABLES = ("R_total", "T_total", "A_volume_total")
TINY = float.fromhex("0x1.0p-1022")


def _observable_vector(result: dict[str, Any], level: str) -> dict[str, float]:
    summary = result[level]["summary"]
    return {name: float(summary[name]) for name in OBSERVABLES}


def _delta_norm(left: dict[str, float], right: dict[str, float]) -> float:
    return math.sqrt(sum((left[name] - right[name]) ** 2 for name in OBSERVABLES))


def _resolve_theta_schedule(
    marked_cycles: int,
    theta: float,
    theta_schedule: tuple[float, ...] | None,
) -> tuple[float, ...]:
    if marked_cycles < 1:
        raise ValueError("marked_cycles must be at least one")
    if theta_schedule is None:
        schedule = (float(theta),) * marked_cycles
    else:
        schedule = tuple(float(value) for value in theta_schedule)
    if len(schedule) != marked_cycles:
        raise ValueError(
            "theta_schedule must contain exactly one value per marked cycle"
        )
    if any(not 0.0 < value <= 1.0 for value in schedule):
        raise ValueError("every theta_schedule value must lie in (0, 1]")
    return schedule


def run_target_dwr_adaptive_cycles(
    out_dir: Path,
    *,
    marked_cycles: int = 1,
    coarse_degree: int = 2,
    enriched_degree: int = 3,
    h_nm: float = 50.0,
    theta: float = 0.5,
    theta_schedule: tuple[float, ...] | None = None,
    polarization_kind: str = "s",
    marker_policy: str = "combined_relative_R_T",
    full_boundary_synchronization: bool = True,
    stop_on_nonpositive_signal: bool = True,
    progress_observer=None,
) -> dict[str, Any]:
    """Refine with the MPI-stable physical R/T adjoint-weighted marker."""

    resolved_theta_schedule = _resolve_theta_schedule(
        marked_cycles, theta, theta_schedule
    )
    if marker_policy not in {
        "combined_relative_R_T",
        "R_total",
        "T_total",
    }:
        raise ValueError("unsupported DWR marker policy")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    comm = MPI.COMM_WORLD
    base = target_stage4_config(degree=coarse_degree, h_nm=h_nm)
    mesh_cfg = replace(
        base,
        case_name="task035_actual_dwr_adaptive_tetra",
        polarization_kind=polarization_kind,
        custom_polarization=None,
        mesh_cell_type="tetrahedron",
        unique_output=False,
    )

    def progress(stage: str, status: str) -> None:
        if progress_observer is not None:
            progress_observer(stage, status)

    progress("dwr_adaptive_initial_mesh", "begin")
    mesh_data = build_airbox_mesh_3d(mesh_cfg, out_dir / "initial_mesh")
    initial_audit = audit_periodic_tetra_mesh(
        mesh_data.mesh,
        mesh_data.cell_tags,
        mesh_data.facet_tags,
        mesh_cfg,
    )
    if not initial_audit["pass"]:
        raise RuntimeError(f"initial periodic tetra audit failed: {initial_audit}")
    progress("dwr_adaptive_initial_mesh", "end")

    started = time.perf_counter()
    cycles: list[dict[str, Any]] = []
    refinements: list[dict[str, Any]] = []
    reductions: list[dict[str, Any]] = []
    stopped_early = False
    stop_reason: str | None = None
    fixed_reference = task034_best_available_observable_reference()
    previous_delta: float | None = None
    previous_coarse_reference_error: float | None = None
    previous_enriched_reference_error: float | None = None

    for cycle_index in range(marked_cycles + 1):
        cycle_theta = resolved_theta_schedule[min(cycle_index, marked_cycles - 1)]
        progress(f"dwr_adaptive_cycle_{cycle_index}", "begin")
        result = run_target_goal_weighted_two_level(
            out_dir / f"cycle_{cycle_index}",
            coarse_degree=coarse_degree,
            enriched_degree=enriched_degree,
            h_nm=h_nm,
            theta=cycle_theta,
            polarization_kind=polarization_kind,
            mesh_cell_type="tetrahedron",
            mesh_data_override=mesh_data,
            progress_observer=lambda stage, status, index=cycle_index: progress(
                f"dwr_adaptive_cycle_{index}_{stage}", status
            ),
        )
        progress(f"dwr_adaptive_cycle_{cycle_index}", "end")
        if not result["pass"]:
            stopped_early = True
            stop_reason = "goal_weighted_estimator_gate_failed"
            break

        coarse_vector = _observable_vector(result, "coarse")
        enriched_vector = _observable_vector(result, "enriched")
        delta = _delta_norm(coarse_vector, enriched_vector)
        coarse_reference_error = _delta_norm(
            coarse_vector, fixed_reference["observables"]
        )
        enriched_reference_error = _delta_norm(
            enriched_vector, fixed_reference["observables"]
        )
        audit = (
            initial_audit if cycle_index == 0 else refinements[-1]["refined_mesh_audit"]
        )
        marker = (
            result["DWR"]["combined_relative_R_T"]
            if marker_policy == "combined_relative_R_T"
            else result["DWR"]["goals"][marker_policy]
        )
        cycles.append(
            {
                "cycle_index": cycle_index,
                "theta": cycle_theta,
                "mesh_audit": audit,
                "coarse_observables": coarse_vector,
                "enriched_observables": enriched_vector,
                "official_observable_delta_l2": delta,
                "coarse_fixed_reference_error_l2": coarse_reference_error,
                "enriched_fixed_reference_error_l2": enriched_reference_error,
                "marker": {
                    "kind": marker_policy,
                    "marked_count": marker["marking"]["count"],
                    "marked_geometry_sha256": marker["marked_geometry_sha256"],
                },
                "goal_dwr": result,
            }
        )
        if previous_delta is not None:
            assert previous_coarse_reference_error is not None
            assert previous_enriched_reference_error is not None
            coarse_reduction = 1.0 - coarse_reference_error / max(
                previous_coarse_reference_error, TINY
            )
            enriched_reduction = 1.0 - enriched_reference_error / max(
                previous_enriched_reference_error, TINY
            )
            internal_gap_reduction = 1.0 - delta / max(previous_delta, TINY)
            positive = coarse_reduction > 0.0 and enriched_reduction > 0.0
            reductions.append(
                {
                    "from_cycle": cycle_index - 1,
                    "to_cycle": cycle_index,
                    "coarse_fixed_reference_error_previous_l2": (
                        previous_coarse_reference_error
                    ),
                    "coarse_fixed_reference_error_current_l2": (coarse_reference_error),
                    "coarse_fixed_reference_reduction_fraction": (coarse_reduction),
                    "enriched_fixed_reference_error_previous_l2": (
                        previous_enriched_reference_error
                    ),
                    "enriched_fixed_reference_error_current_l2": (
                        enriched_reference_error
                    ),
                    "enriched_fixed_reference_reduction_fraction": (enriched_reduction),
                    "internal_p_gap_previous_l2": previous_delta,
                    "internal_p_gap_current_l2": delta,
                    "internal_p_gap_reduction_fraction": internal_gap_reduction,
                    "internal_p_gap_is_gate": False,
                    "fixed_reference_positive_signal": positive,
                }
            )
            if stop_on_nonpositive_signal and not positive:
                stopped_early = True
                stop_reason = "nonpositive_fixed_reference_observable_error_reduction"
                break

        previous_delta = delta
        previous_coarse_reference_error = coarse_reference_error
        previous_enriched_reference_error = enriched_reference_error
        if cycle_index == marked_cycles:
            break

        progress(f"dwr_adaptive_cycle_{cycle_index}_refine", "begin")
        mesh_data, refinement = refine_periodic_marked_tetra_mesh(
            mesh_data,
            mesh_cfg,
            marker["marked_global_cell_ids"],
            full_boundary_synchronization=full_boundary_synchronization,
        )
        refinements.append(refinement)
        progress(f"dwr_adaptive_cycle_{cycle_index}_refine", "end")
        if not refinement["pass"]:
            stopped_early = True
            stop_reason = "periodic_tetra_refinement_audit_failed"
            break
        gc.collect()

    all_reference_reductions_positive = bool(reductions) and all(
        entry["fixed_reference_positive_signal"] for entry in reductions
    )
    completed_requested_cycles = len(refinements) == marked_cycles and (
        len(cycles) == marked_cycles + 1
    )
    passed = bool(
        completed_requested_cycles
        and all_reference_reductions_positive
        and all(entry["pass"] for entry in refinements)
    )
    if passed:
        status = "actual_dwr_adaptive_cycles_pass"
    elif stopped_early:
        status = "controlled_negative"
    else:
        status = "incomplete"
    return {
        "schema_version": "task035.target-dwr-adaptive-cycles.v1",
        "status": status,
        "pass": passed,
        "canonical": False,
        "production_qualified": False,
        "ordinary_default_changed": False,
        "target_identity": {
            "wavelength_nm": 13.5,
            "incidence_theta_deg": 80.0,
            "grazing_angle_deg": 10.0,
            "polarization": polarization_kind.upper(),
            "geometry": "Task034 fixed rectangular block grating",
            "mesh_backend": "audited periodic DWR-refined tetrahedron",
        },
        "mpi_size": comm.size,
        "marked_cycles_requested": marked_cycles,
        "marked_cycles_completed": len(refinements),
        "coarse_degree": coarse_degree,
        "enriched_degree": enriched_degree,
        "h_nm": h_nm,
        "theta": theta,
        "theta_schedule": list(resolved_theta_schedule),
        "marker_policy": marker_policy,
        "periodic_edge_closure_policy": (
            "full_periodic_boundary_synchronization"
            if full_boundary_synchronization
            else "minimal_periodic_mates_only"
        ),
        "fixed_observable_reference": fixed_reference,
        "initial_mesh_audit": initial_audit,
        "cycles": cycles,
        "refinements": refinements,
        "observable_error_reductions": reductions,
        "all_fixed_reference_error_reductions_positive": (
            all_reference_reductions_positive
        ),
        "internal_p_gap_is_gate": False,
        "stopped_early": stopped_early,
        "stop_reason": stop_reason,
        "elapsed_seconds": float(
            comm.allreduce(time.perf_counter() - started, op=MPI.MAX)
        ),
    }


__all__ = [
    "_resolve_theta_schedule",
    "run_target_dwr_adaptive_cycles",
]
