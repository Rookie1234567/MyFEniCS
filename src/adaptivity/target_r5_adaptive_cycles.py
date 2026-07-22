"""Actual p-adjoint R5 driven periodic tetra adaptive cycles for Task035."""

from __future__ import annotations

from dataclasses import replace
import gc
import math
from pathlib import Path
import time
from typing import Any

from mpi4py import MPI

from src.adaptivity.global_two_level_r5 import run_target_global_two_level_r5
from src.adaptivity.periodic_tetra_refinement import (
    refine_periodic_marked_tetra_mesh,
)
from src.common.config_3d import target_stage4_config
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.geometry.tetra_mesh_audit import audit_periodic_tetra_mesh


OBSERVABLES = ("R_total", "T_total", "A_volume_total")


def _observable_vector(result: dict[str, Any], level: str) -> dict[str, float]:
    summary = result[level]["summary"]
    return {name: float(summary[name]) for name in OBSERVABLES}


def _delta_norm(left: dict[str, float], right: dict[str, float]) -> float:
    return math.sqrt(sum((left[name] - right[name]) ** 2 for name in OBSERVABLES))


def run_target_r5_adaptive_cycles(
    out_dir: Path,
    *,
    marked_cycles: int = 1,
    coarse_degree: int = 2,
    enriched_degree: int = 3,
    h_nm: float = 50.0,
    theta: float = 0.5,
    polarization_kind: str = "s",
    stop_on_nonpositive_signal: bool = True,
    progress_observer=None,
) -> dict[str, Any]:
    """Run actual target solves, R5 marking, and audited tetra refinement.

    One marked cycle means two estimator evaluations: the initial mesh and one
    estimator-refined mesh. The official p-to-p+1 R/T/A delta is the measured
    low-cost observable-error proxy. A nonpositive reduction closes this lane
    without turning an estimator/backend negative into a repository blocker.
    """

    if marked_cycles < 1:
        raise ValueError("marked_cycles must be at least one")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    comm = MPI.COMM_WORLD
    base = target_stage4_config(degree=coarse_degree, h_nm=h_nm)
    mesh_cfg = replace(
        base,
        case_name="task035_actual_r5_adaptive_tetra",
        polarization_kind=polarization_kind,
        custom_polarization=None,
        mesh_cell_type="tetrahedron",
        unique_output=False,
    )

    def progress(stage: str, status: str) -> None:
        if progress_observer is not None:
            progress_observer(stage, status)

    progress("adaptive_initial_mesh", "begin")
    mesh_data = build_airbox_mesh_3d(mesh_cfg, out_dir / "initial_mesh")
    initial_audit = audit_periodic_tetra_mesh(
        mesh_data.mesh, mesh_data.cell_tags, mesh_data.facet_tags, mesh_cfg
    )
    if not initial_audit["pass"]:
        raise RuntimeError(f"initial periodic tetra audit failed: {initial_audit}")
    progress("adaptive_initial_mesh", "end")

    started = time.perf_counter()
    cycles: list[dict[str, Any]] = []
    refinements: list[dict[str, Any]] = []
    reductions: list[dict[str, Any]] = []
    stopped_early = False
    stop_reason: str | None = None
    previous_delta: float | None = None
    for cycle_index in range(marked_cycles + 1):
        progress(f"adaptive_cycle_{cycle_index}_r5", "begin")
        result = run_target_global_two_level_r5(
            out_dir / f"cycle_{cycle_index}",
            coarse_degree=coarse_degree,
            enriched_degree=enriched_degree,
            h_nm=h_nm,
            theta=theta,
            polarization_kind=polarization_kind,
            mesh_cell_type="tetrahedron",
            mesh_data_override=mesh_data,
            progress_observer=lambda stage, status, index=cycle_index: progress(
                f"adaptive_cycle_{index}_{stage}", status
            ),
        )
        progress(f"adaptive_cycle_{cycle_index}_r5", "end")
        coarse_vector = _observable_vector(result, "coarse")
        enriched_vector = _observable_vector(result, "enriched")
        delta = _delta_norm(coarse_vector, enriched_vector)
        audit = (
            initial_audit
            if cycle_index == 0
            else refinements[-1]["refined_mesh_audit"]
        )
        cycles.append(
            {
                "cycle_index": cycle_index,
                "mesh_audit": audit,
                "coarse_observables": coarse_vector,
                "enriched_observables": enriched_vector,
                "official_observable_delta_l2": delta,
                "actual_r5": result,
            }
        )
        if previous_delta is not None:
            reduction_fraction = 1.0 - delta / max(
                previous_delta, float.fromhex("0x1.0p-1022")
            )
            positive = delta < previous_delta
            reductions.append(
                {
                    "from_cycle": cycle_index - 1,
                    "to_cycle": cycle_index,
                    "previous_delta_l2": previous_delta,
                    "current_delta_l2": delta,
                    "reduction_fraction": reduction_fraction,
                    "positive_signal": positive,
                }
            )
            if stop_on_nonpositive_signal and not positive:
                stopped_early = True
                stop_reason = "nonpositive_official_observable_error_reduction"
                break
        previous_delta = delta
        if cycle_index == marked_cycles:
            break
        progress(f"adaptive_cycle_{cycle_index}_refine", "begin")
        mesh_data, refinement = refine_periodic_marked_tetra_mesh(
            mesh_data,
            mesh_cfg,
            result["R5"]["marked_global_cell_ids"],
        )
        refinements.append(refinement)
        progress(f"adaptive_cycle_{cycle_index}_refine", "end")
        if not refinement["pass"]:
            stopped_early = True
            stop_reason = "periodic_tetra_refinement_audit_failed"
            break
        gc.collect()

    all_reductions_positive = bool(reductions) and all(
        entry["positive_signal"] for entry in reductions
    )
    completed_requested_cycles = len(refinements) == marked_cycles and (
        len(cycles) == marked_cycles + 1
    )
    passed = (
        completed_requested_cycles
        and all_reductions_positive
        and all(entry["pass"] for entry in refinements)
    )
    if passed:
        status = "actual_r5_adaptive_cycles_pass"
    elif stopped_early:
        status = "controlled_negative"
    else:
        status = "incomplete"
    return {
        "schema_version": "task035.target-r5-adaptive-cycles.v1",
        "status": status,
        "target_identity": {
            "wavelength_nm": 13.5,
            "incidence_theta_deg": 80.0,
            "grazing_angle_deg": 10.0,
            "polarization": polarization_kind.upper(),
            "geometry": "Task034 fixed rectangular block grating",
            "mesh_backend": "audited periodic estimator-refined tetrahedron",
        },
        "mpi_size": comm.size,
        "marked_cycles_requested": marked_cycles,
        "marked_cycles_completed": len(refinements),
        "coarse_degree": coarse_degree,
        "enriched_degree": enriched_degree,
        "h_nm": h_nm,
        "theta": theta,
        "polarization_kind": polarization_kind,
        "initial_mesh_audit": initial_audit,
        "cycles": cycles,
        "refinements": refinements,
        "observable_error_reductions": reductions,
        "all_observable_error_reductions_positive": all_reductions_positive,
        "stopped_early": stopped_early,
        "stop_reason": stop_reason,
        "elapsed_seconds": float(
            comm.allreduce(time.perf_counter() - started, op=MPI.MAX)
        ),
        "ordinary_default_changed": False,
        "pass": passed,
    }


__all__ = ["run_target_r5_adaptive_cycles"]
