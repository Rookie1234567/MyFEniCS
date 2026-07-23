"""SHA-bound common-mesh grazing-angle sweep for Task035."""

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
from src.adaptivity.target_r5_adaptive_cycles import (
    task034_best_available_observable_reference,
    task034_observable_control,
)
from src.common.config_3d import target_stage4_config
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.geometry.tetra_mesh_audit import audit_periodic_tetra_mesh


_AUDIT_IDENTITY_FIELDS = (
    "global_cell_count",
    "partition_independent_mesh_sha256",
    "cell_tag_sha256",
    "facet_tag_sha256",
)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _audit_identity(audit: dict[str, Any]) -> dict[str, Any]:
    return {name: audit.get(name) for name in _AUDIT_IDENTITY_FIELDS}


def load_common_mesh_replay_contract(
    record_path: Path,
    *,
    expected_sha256: str,
    expected_theta: float = 0.7,
    expected_final_cells: int = 1316,
) -> dict[str, Any]:
    """Load and fail-closed validate an accepted DWR marker record."""

    path = Path(record_path)
    payload = path.read_bytes()
    actual_sha256 = _sha256_bytes(payload)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            "common-mesh replay record SHA256 mismatch: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )
    record = json.loads(payload)
    cycles = record.get("cycles") or []
    source = record.get("source") or {}
    qualification = record.get("qualification") or {}
    target = record.get("target_identity") or {}
    failures: list[str] = []
    theta_schedule = record.get("theta_schedule")
    if theta_schedule is not None:
        recorded_theta = (
            float(theta_schedule[0])
            if isinstance(theta_schedule, list) and len(theta_schedule) == 1
            else None
        )
    else:
        command = record.get("command") or []
        try:
            theta_index = command.index("--theta")
            recorded_theta = float(command[theta_index + 1])
        except (AttributeError, IndexError, TypeError, ValueError):
            recorded_theta = None
    refinements = record.get("refinements") or []
    recorded_closure_policy = record.get("periodic_edge_closure_policy")
    if recorded_closure_policy is not None:
        full_periodic_closure = (
            recorded_closure_policy == "full_periodic_boundary_synchronization"
        )
    else:
        full_periodic_closure = bool(refinements) and (
            (refinements[0].get("periodic_edge_closure") or {}).get(
                "full_periodic_boundary_synchronization"
            )
            is True
        )
    requirements = {
        "accepted_status": record.get("status") == "actual_dwr_adaptive_cycles_pass",
        "accepted_qualification": qualification.get("pass") is True,
        "clean_stable_source": (
            source.get("tracked_source_dirty") is False
            and source.get("stable_and_clean_after") is True
            and source.get("commit_sha") == source.get("head_after_sha")
        ),
        "r_total_marker": record.get("dwr_marker_policy") == "R_total",
        "requested_theta": (
            recorded_theta is not None
            and math.isclose(recorded_theta, expected_theta, abs_tol=1.0e-12)
        ),
        "one_refinement": (
            record.get("marked_cycles_requested") == 1
            and record.get("marked_cycles_completed") == 1
            and len(cycles) == 2
        ),
        "full_periodic_closure": full_periodic_closure,
        "fixed_target": (
            target.get("grazing_angle_deg") == 10.0
            and target.get("polarization") == "S"
            and target.get("geometry") == "Task034 fixed rectangular block grating"
        ),
    }
    failures.extend(name for name, passed in requirements.items() if not passed)
    if failures:
        raise ValueError(f"common-mesh replay authority rejected: {failures}")

    cycle_zero = cycles[0]
    cycle_one = cycles[1]
    r_goal = ((cycle_zero.get("DWR") or {}).get("goals") or {}).get("R_total") or {}
    marker = cycle_zero.get("marker") or {}
    marked_ids = r_goal.get("marked_global_cell_ids")
    if (
        not isinstance(marked_ids, list)
        or not marked_ids
        or any(not isinstance(value, int) for value in marked_ids)
    ):
        raise ValueError("common-mesh replay authority has no integer R_total marker")
    marker_hash = r_goal.get("marked_geometry_sha256")
    if (
        marker.get("kind") != "R_total"
        or marker.get("marked_count") != len(marked_ids)
        or marker.get("marked_geometry_sha256") != marker_hash
    ):
        raise ValueError("common-mesh replay marker identity is inconsistent")
    initial_audit = record.get("initial_mesh_audit") or {}
    cycle_zero_audit = cycle_zero.get("mesh_audit") or {}
    final_audit = cycle_one.get("mesh_audit") or {}
    if (
        initial_audit.get("pass") is not True
        or final_audit.get("pass") is not True
        or _audit_identity(initial_audit) != _audit_identity(cycle_zero_audit)
    ):
        raise ValueError("common-mesh replay audit authority is inconsistent")
    if final_audit.get("global_cell_count") != expected_final_cells:
        raise ValueError(
            "common-mesh replay final cell count mismatch: "
            f"expected {expected_final_cells}, got {final_audit.get('global_cell_count')}"
        )
    return {
        "schema_version": "task035.common-mesh-replay-contract.v2",
        "record_path": str(path),
        "record_sha256": actual_sha256,
        "source_sha": source["commit_sha"],
        "theta": recorded_theta,
        "marker_policy": "R_total",
        "marked_global_cell_ids": marked_ids,
        "marked_count": len(marked_ids),
        "marked_geometry_sha256": marker_hash,
        "initial_mesh_identity": _audit_identity(initial_audit),
        "source_mpi_size": initial_audit.get("mpi_size"),
        "final_mesh_identity": _audit_identity(final_audit),
    }


def build_replayed_common_mesh(
    out_dir: Path,
    *,
    replay_record: Path,
    replay_record_sha256: str,
    coarse_degree: int = 4,
    h_nm: float = 50.0,
    polarization_kind: str = "s",
    replay_expected_theta: float = 0.7,
    replay_expected_final_cells: int = 1316,
) -> tuple[Any, Any, dict[str, Any]]:
    """Rebuild and exactly replay an accepted full-sleeve DWR mesh."""

    contract = load_common_mesh_replay_contract(
        replay_record,
        expected_sha256=replay_record_sha256,
        expected_theta=replay_expected_theta,
        expected_final_cells=replay_expected_final_cells,
    )
    if MPI.COMM_WORLD.size != contract["source_mpi_size"]:
        raise RuntimeError(
            "common-mesh replay requires the authority MPI size "
            f"{contract['source_mpi_size']}; the accepted compact record binds "
            "marked cell IDs and their geometry hash but does not embed the "
            "full marked geometry key list"
        )
    base = target_stage4_config(degree=coarse_degree, h_nm=h_nm)
    mesh_cfg = replace(
        base,
        case_name="task035_common_mesh_angle_sweep",
        incident_theta_deg=80.0,
        polarization_kind=polarization_kind,
        custom_polarization=None,
        mesh_cell_type="tetrahedron",
        unique_output=False,
    )
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mesh_data = build_airbox_mesh_3d(mesh_cfg, out_dir / "initial_mesh")
    initial_audit = audit_periodic_tetra_mesh(
        mesh_data.mesh,
        mesh_data.cell_tags,
        mesh_data.facet_tags,
        mesh_cfg,
    )
    if initial_audit.get("pass") is not True:
        raise RuntimeError("common-mesh replay initial tetra audit failed")
    if _audit_identity(initial_audit) != contract["initial_mesh_identity"]:
        raise RuntimeError("common-mesh replay initial mesh identity mismatch")

    mesh_data, refinement = refine_periodic_marked_tetra_mesh(
        mesh_data,
        mesh_cfg,
        contract["marked_global_cell_ids"],
        full_boundary_synchronization=True,
    )
    final_audit = refinement.get("refined_mesh_audit") or {}
    closure = refinement.get("periodic_closure") or {}
    if refinement.get("pass") is not True:
        raise RuntimeError("common-mesh replay periodic tetra refinement failed")
    if closure.get("initial_geometry_sha256") != contract["marked_geometry_sha256"]:
        raise RuntimeError("common-mesh replay marker geometry identity mismatch")
    if _audit_identity(final_audit) != contract["final_mesh_identity"]:
        raise RuntimeError("common-mesh replay final mesh identity mismatch")
    report = {
        "schema_version": "task035.common-mesh-replay.v1",
        "status": "pass",
        "pass": True,
        "contract": contract,
        "initial_mesh_audit": initial_audit,
        "refinement": refinement,
        "final_mesh_audit": final_audit,
        "single_in_memory_mesh_instance": True,
        "ordinary_default_changed": False,
    }
    return mesh_data, mesh_cfg, report


def _evaluate_hp_budget(
    angle_results: list[dict[str, Any]],
    *,
    dof_ceiling: int,
    accuracy_control_key: str,
) -> dict[str, Any]:
    if len(angle_results) != 1 or angle_results[0]["grazing_angle_deg"] != 10.0:
        raise ValueError("hp budget evaluation requires exactly the 10-degree target")
    reference = task034_best_available_observable_reference()
    control = task034_observable_control(accuracy_control_key)
    summary = angle_results[0]["actual_r5_pair"]["enriched"]["summary"]
    observables = {
        name: float(summary[name])
        for name in ("R_total", "T_total", "A_volume_total")
    }
    candidate_dofs = int(summary["num_nedelec_dofs"])
    reference_dofs = int(reference["resource"]["dofs"])
    vector_error = math.sqrt(
        sum(
            (observables[name] - reference["observables"][name]) ** 2
            for name in observables
        )
    )
    r_error = abs(observables["R_total"] - reference["observables"]["R_total"])
    saving_fraction = 1.0 - candidate_dofs / reference_dofs
    checks = {
        "candidate_dofs_within_ceiling": candidate_dofs <= dof_ceiling,
        "minimum_50_percent_dof_saving": saving_fraction >= 0.5,
        "r_total_error_no_worse_than_control": (
            r_error <= control["reference_r_total_absolute_error"]
        ),
        "observable_vector_error_no_worse_than_control": (
            vector_error <= control["reference_observable_error_l2"]
        ),
    }
    passed = all(checks.values())
    return {
        "schema_version": "task035.hp-budget-evaluation.v1",
        "status": "candidate_pass" if passed else "controlled_negative",
        "pass": passed,
        "checks": checks,
        "candidate": {
            "degree": int(summary["degree"]),
            "dofs": candidate_dofs,
            "observables": observables,
            "reference_r_total_absolute_error": r_error,
            "reference_observable_error_l2": vector_error,
            "dof_saving_fraction": saving_fraction,
        },
        "dof_ceiling": dof_ceiling,
        "fixed_reference": reference,
        "accuracy_control": control,
        "thresholds_relaxed": False,
    }


def run_target_common_mesh_angle_sweep(
    out_dir: Path,
    *,
    replay_record: Path,
    replay_record_sha256: str,
    grazing_angles_deg: tuple[float, ...] = (1.0, 5.0, 10.0),
    coarse_degree: int = 4,
    enriched_degree: int = 5,
    h_nm: float = 50.0,
    theta: float = 0.7,
    polarization_kind: str = "s",
    progress_observer=None,
    replay_expected_theta: float = 0.7,
    replay_expected_final_cells: int = 1316,
    dof_ceiling: int | None = None,
    accuracy_control_key: str | None = None,
) -> dict[str, Any]:
    """Solve all requested angles on one SHA-bound replayed tetra mesh."""

    if not grazing_angles_deg or any(
        not 0.0 < float(angle) < 90.0 for angle in grazing_angles_deg
    ):
        raise ValueError("grazing angles must lie strictly between 0 and 90 degrees")
    if len(set(float(angle) for angle in grazing_angles_deg)) != len(
        grazing_angles_deg
    ):
        raise ValueError("grazing angles must be unique")
    if (dof_ceiling is None) != (accuracy_control_key is None):
        raise ValueError("dof ceiling and accuracy control must be provided together")
    if dof_ceiling is not None and dof_ceiling <= 0:
        raise ValueError("dof ceiling must be positive")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def progress(stage: str, status: str) -> None:
        if progress_observer is not None:
            progress_observer(stage, status)

    started = time.perf_counter()
    progress("common_mesh_replay", "begin")
    mesh_data, _, replay = build_replayed_common_mesh(
        out_dir / "mesh_replay",
        replay_record=replay_record,
        replay_record_sha256=replay_record_sha256,
        coarse_degree=coarse_degree,
        h_nm=h_nm,
        polarization_kind=polarization_kind,
        replay_expected_theta=replay_expected_theta,
        replay_expected_final_cells=replay_expected_final_cells,
    )
    progress("common_mesh_replay", "end")
    angle_results: list[dict[str, Any]] = []
    for angle in grazing_angles_deg:
        grazing_angle = float(angle)
        incident_theta = 90.0 - grazing_angle
        label = f"grazing_{grazing_angle:g}deg".replace(".", "p")
        progress(f"common_mesh_{label}", "begin")
        result = run_target_global_two_level_r5(
            out_dir / label,
            coarse_degree=coarse_degree,
            enriched_degree=enriched_degree,
            h_nm=h_nm,
            theta=theta,
            incident_theta_deg=incident_theta,
            polarization_kind=polarization_kind,
            mesh_cell_type="tetrahedron",
            mesh_data_override=mesh_data,
            progress_observer=lambda stage, status, name=label: progress(
                f"common_mesh_{name}_{stage}", status
            ),
        )
        angle_results.append(
            {
                "grazing_angle_deg": grazing_angle,
                "incident_theta_deg": incident_theta,
                "actual_r5_pair": result,
            }
        )
        progress(f"common_mesh_{label}", "end")
        gc.collect()
    hp_budget_evaluation = (
        None
        if dof_ceiling is None
        else _evaluate_hp_budget(
            angle_results,
            dof_ceiling=dof_ceiling,
            accuracy_control_key=accuracy_control_key,
        )
    )
    return {
        "schema_version": "task035.target-common-mesh-angle-sweep.v1",
        "status": "actual_common_mesh_angle_sweep_pass",
        "pass": True,
        "target_identity": {
            "wavelength_nm": 13.5,
            "grazing_angles_deg": [float(value) for value in grazing_angles_deg],
            "polarization": polarization_kind.upper(),
            "geometry": "Task034 fixed rectangular block grating",
            "mesh_backend": "single SHA-bound replayed periodic tetrahedron mesh",
        },
        "mesh_replay": replay,
        "common_mesh_identity": replay["contract"]["final_mesh_identity"],
        "single_in_memory_mesh_instance": True,
        "angle_results": angle_results,
        "hp_budget_evaluation": hp_budget_evaluation,
        "elapsed_seconds": float(
            MPI.COMM_WORLD.allreduce(time.perf_counter() - started, op=MPI.MAX)
        ),
        "ordinary_default_changed": False,
    }


__all__ = [
    "build_replayed_common_mesh",
    "load_common_mesh_replay_contract",
    "run_target_common_mesh_angle_sweep",
]
