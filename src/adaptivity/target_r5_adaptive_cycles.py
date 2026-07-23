"""Actual p-adjoint R5 driven periodic tetra adaptive cycles for Task035."""

from __future__ import annotations

from dataclasses import replace
import gc
import hashlib
import json
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
ROOT = Path(__file__).resolve().parents[2]
TASK034_REFERENCE_PATH = (
    ROOT
    / "benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/records"
    / "convergence_summary.json"
)
TASK034_REFERENCE_SHA256 = "f5bad15f40ade652f6b4398e46852292ed323e3e5494b9fdb969c40bc6283111"


def _observable_vector(result: dict[str, Any], level: str) -> dict[str, float]:
    summary = result[level]["summary"]
    return {name: float(summary[name]) for name in OBSERVABLES}


def _delta_norm(left: dict[str, float], right: dict[str, float]) -> float:
    return math.sqrt(sum((left[name] - right[name]) ** 2 for name in OBSERVABLES))


def task034_best_available_observable_reference() -> dict[str, Any]:
    """Load the accepted p4/h5 compact reference with fail-closed identity."""

    payload = TASK034_REFERENCE_PATH.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != TASK034_REFERENCE_SHA256:
        raise RuntimeError(
            "Task034 convergence summary hash changed: "
            f"expected {TASK034_REFERENCE_SHA256}, got {digest}"
        )
    record = json.loads(payload)
    selected = record["selected_discrete_reference"]
    if (
        selected["key"] != "p4_h5"
        or selected["identity"] != "best_available_discrete_reference_for_case093"
        or selected["continuum_reference"] is not False
    ):
        raise RuntimeError("Task034 selected discrete reference identity changed")
    point = next(entry for entry in record["points"] if entry["key"] == "p4_h5")
    full3d = point["full3d"]
    if full3d["status"] != "full3d_reference_pass" or not full3d["qualified"]:
        raise RuntimeError("Task034 p4/h5 Full3D reference is not qualified")
    return {
        "identity": selected["identity"],
        "key": selected["key"],
        "continuum_reference": False,
        "record_path": str(TASK034_REFERENCE_PATH.relative_to(ROOT)),
        "record_sha256": digest,
        "source_sha": full3d["source"]["commit_sha"],
        "true_relative_residual": full3d["true_relative_residual"],
        "resource": dict(full3d["resource"]),
        "observables": {
            name: float(full3d["official_values"][name]) for name in OBSERVABLES
        },
    }


def task034_observable_control(key: str = "p4_h7p5") -> dict[str, Any]:
    """Load a qualified Task034 comparison point with fail-closed identity."""

    if key != "p4_h7p5":
        raise ValueError(f"unsupported Task034 observable control: {key}")
    reference = task034_best_available_observable_reference()
    record = json.loads(TASK034_REFERENCE_PATH.read_bytes())
    point = next((entry for entry in record["points"] if entry["key"] == key), None)
    if point is None:
        raise RuntimeError(f"Task034 observable control is missing: {key}")
    full3d = point["full3d"]
    if (
        full3d["degree"] != 4
        or float(full3d["h_nm"]) != 7.5
        or full3d["status"] != "full3d_reference_pass"
        or full3d["qualified"] is not True
        or full3d["polarization_kind"] != "s"
        or full3d["mpi_size"] != 8
    ):
        raise RuntimeError("Task034 p4/h7.5 Full3D control identity changed")
    observables = {
        name: float(full3d["official_values"][name]) for name in OBSERVABLES
    }
    return {
        "identity": "qualified_case093_full3d_accuracy_control",
        "key": key,
        "record_path": reference["record_path"],
        "record_sha256": reference["record_sha256"],
        "source_sha": full3d["source"]["commit_sha"],
        "true_relative_residual": float(full3d["true_relative_residual"]),
        "resource": dict(full3d["resource"]),
        "observables": observables,
        "reference_key": reference["key"],
        "reference_observable_error_l2": _delta_norm(
            observables, reference["observables"]
        ),
        "reference_r_total_absolute_error": abs(
            observables["R_total"] - reference["observables"]["R_total"]
        ),
    }


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
    fixed_reference = task034_best_available_observable_reference()
    previous_delta: float | None = None
    previous_coarse_reference_error: float | None = None
    previous_enriched_reference_error: float | None = None
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
        coarse_reference_error = _delta_norm(
            coarse_vector, fixed_reference["observables"]
        )
        enriched_reference_error = _delta_norm(
            enriched_vector, fixed_reference["observables"]
        )
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
                "coarse_fixed_reference_error_l2": coarse_reference_error,
                "enriched_fixed_reference_error_l2": enriched_reference_error,
                "actual_r5": result,
            }
        )
        if previous_delta is not None:
            reduction_fraction = 1.0 - delta / max(
                previous_delta, float.fromhex("0x1.0p-1022")
            )
            assert previous_coarse_reference_error is not None
            assert previous_enriched_reference_error is not None
            coarse_reduction = 1.0 - coarse_reference_error / max(
                previous_coarse_reference_error, float.fromhex("0x1.0p-1022")
            )
            enriched_reduction = 1.0 - enriched_reference_error / max(
                previous_enriched_reference_error,
                float.fromhex("0x1.0p-1022"),
            )
            positive = coarse_reduction > 0.0 and enriched_reduction > 0.0
            reductions.append(
                {
                    "from_cycle": cycle_index - 1,
                    "to_cycle": cycle_index,
                    "coarse_fixed_reference_error_previous_l2": (
                        previous_coarse_reference_error
                    ),
                    "coarse_fixed_reference_error_current_l2": coarse_reference_error,
                    "coarse_fixed_reference_reduction_fraction": coarse_reduction,
                    "enriched_fixed_reference_error_previous_l2": (
                        previous_enriched_reference_error
                    ),
                    "enriched_fixed_reference_error_current_l2": (
                        enriched_reference_error
                    ),
                    "enriched_fixed_reference_reduction_fraction": enriched_reduction,
                    "internal_p_gap_previous_l2": previous_delta,
                    "internal_p_gap_current_l2": delta,
                    "internal_p_gap_reduction_fraction": reduction_fraction,
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

    all_reference_reductions_positive = bool(reductions) and all(
        entry["fixed_reference_positive_signal"] for entry in reductions
    )
    completed_requested_cycles = len(refinements) == marked_cycles and (
        len(cycles) == marked_cycles + 1
    )
    passed = (
        completed_requested_cycles
        and all_reference_reductions_positive
        and all(entry["pass"] for entry in refinements)
    )
    if passed:
        status = "actual_r5_adaptive_cycles_pass"
    elif stopped_early:
        status = "controlled_negative"
    else:
        status = "incomplete"
    return {
        "schema_version": "task035.target-r5-adaptive-cycles.v2",
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
        "ordinary_default_changed": False,
        "pass": passed,
    }


__all__ = [
    "run_target_r5_adaptive_cycles",
    "task034_best_available_observable_reference",
    "task034_observable_control",
]
