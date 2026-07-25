"""Cost-matched uniform tetra control for Task035 adaptive evidence."""

from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path
import time
from typing import Any

import numpy as np
from mpi4py import MPI

from src.adaptivity.global_two_level_r5 import run_target_global_two_level_r5
from src.adaptivity.periodic_tetra_refinement import (
    refine_periodic_marked_tetra_mesh,
)
from src.adaptivity.target_r5_adaptive_cycles import (
    OBSERVABLES,
    task034_best_available_observable_reference,
)
from src.common.config_3d import target_stage4_config
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.geometry.tetra_mesh_audit import audit_periodic_tetra_mesh


def _all_global_cell_ids(msh) -> list[int]:
    index_map = msh.topology.index_map(msh.topology.dim)
    owned = np.arange(index_map.size_local, dtype=np.int32)
    local = index_map.local_to_global(owned).astype(np.int64).tolist()
    return sorted(value for packet in msh.comm.allgather(local) for value in packet)


def _observable_vector(result: dict[str, Any], level: str) -> dict[str, float]:
    summary = result[level]["summary"]
    return {name: float(summary[name]) for name in OBSERVABLES}


def _error_norm(values: dict[str, float], reference: dict[str, float]) -> float:
    return math.sqrt(sum((values[name] - reference[name]) ** 2 for name in OBSERVABLES))


def run_target_uniform_tetra_control(
    out_dir: Path,
    *,
    refinement_levels: int = 2,
    coarse_degree: int = 2,
    enriched_degree: int = 3,
    initial_h_nm: float = 50.0,
    theta: float = 0.5,
    polarization_kind: str = "s",
    progress_observer=None,
) -> dict[str, Any]:
    """Uniformly refine the shared h50 mesh and solve the p2/p3 control pair."""

    if refinement_levels < 1:
        raise ValueError("refinement_levels must be at least one")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    comm = MPI.COMM_WORLD
    cfg = replace(
        target_stage4_config(degree=coarse_degree, h_nm=initial_h_nm),
        case_name="task035_uniform_tetra_control",
        polarization_kind=polarization_kind,
        custom_polarization=None,
        mesh_cell_type="tetrahedron",
        unique_output=False,
    )

    def progress(stage: str, status: str) -> None:
        if progress_observer is not None:
            progress_observer(stage, status)

    started = time.perf_counter()
    progress("uniform_control_initial_mesh", "begin")
    mesh_data = build_airbox_mesh_3d(cfg, out_dir / "initial_mesh")
    initial_audit = audit_periodic_tetra_mesh(
        mesh_data.mesh, mesh_data.cell_tags, mesh_data.facet_tags, cfg
    )
    if not initial_audit["pass"]:
        raise RuntimeError(
            f"initial uniform-control mesh audit failed: {initial_audit}"
        )
    progress("uniform_control_initial_mesh", "end")

    refinements: list[dict[str, Any]] = []
    for level in range(refinement_levels):
        progress(f"uniform_control_refine_{level}", "begin")
        marked = _all_global_cell_ids(mesh_data.mesh)
        mesh_data, report = refine_periodic_marked_tetra_mesh(mesh_data, cfg, marked)
        report["uniform_all_parent_cells_marked"] = (
            report["periodic_closure"]["initial_count"] == report["parent_global_cells"]
        )
        refinements.append(report)
        progress(f"uniform_control_refine_{level}", "end")
        if not report["pass"]:
            return {
                "schema_version": "task035.target-uniform-tetra-control.v1",
                "status": "controlled_negative",
                "stop_reason": "uniform_refinement_audit_failed",
                "refinements": refinements,
                "ordinary_default_changed": False,
                "pass": False,
            }

    progress("uniform_control_p2_p3", "begin")
    result = run_target_global_two_level_r5(
        out_dir / "final_uniform_pair",
        coarse_degree=coarse_degree,
        enriched_degree=enriched_degree,
        h_nm=initial_h_nm,
        theta=theta,
        polarization_kind=polarization_kind,
        mesh_cell_type="tetrahedron",
        mesh_data_override=mesh_data,
        progress_observer=lambda stage, status: progress(
            f"uniform_control_{stage}", status
        ),
    )
    progress("uniform_control_p2_p3", "end")
    reference = task034_best_available_observable_reference()
    coarse_vector = _observable_vector(result, "coarse")
    enriched_vector = _observable_vector(result, "enriched")
    coarse_error = _error_norm(coarse_vector, reference["observables"])
    enriched_error = _error_norm(enriched_vector, reference["observables"])
    passed = (
        result["status"] == "actual_global_r5_pass"
        and all(report["pass"] for report in refinements)
        and all(report["uniform_all_parent_cells_marked"] for report in refinements)
        and math.isfinite(coarse_error)
        and math.isfinite(enriched_error)
    )
    return {
        "schema_version": "task035.target-uniform-tetra-control.v1",
        "status": "actual_uniform_tetra_control_pass"
        if passed
        else "controlled_negative",
        "target_identity": {
            "wavelength_nm": 13.5,
            "incidence_theta_deg": 80.0,
            "grazing_angle_deg": 10.0,
            "polarization": polarization_kind.upper(),
            "geometry": "Task034 fixed rectangular block grating",
            "mesh_backend": "two-level deterministic uniform tetra refinement",
        },
        "mpi_size": comm.size,
        "refinement_levels": refinement_levels,
        "initial_h_nm": initial_h_nm,
        "initial_mesh_audit": initial_audit,
        "refinements": refinements,
        "final_mesh_audit": refinements[-1]["refined_mesh_audit"],
        "fixed_observable_reference": reference,
        "coarse_observables": coarse_vector,
        "enriched_observables": enriched_vector,
        "coarse_fixed_reference_error_l2": coarse_error,
        "enriched_fixed_reference_error_l2": enriched_error,
        "actual_r5_pair": result,
        "elapsed_seconds": float(
            comm.allreduce(time.perf_counter() - started, op=MPI.MAX)
        ),
        "ordinary_default_changed": False,
        "pass": passed,
    }


__all__ = ["run_target_uniform_tetra_control"]
