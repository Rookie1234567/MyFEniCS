"""Task43 same-mesh h100 p3 anchor runner.

Run one case per process.  The native case uses the ordinary degree-three
Nedelec space and ``standard_full`` backend; the empty-h cases use the
qualified p6 carrier with a geometry-bound all-p3 active-space plan.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.task43_hp_adaptivity.candidate_checkpoints import (
    write_pre_validation_checkpoint,
)
from benchmarks.task43_hp_adaptivity.candidate_records import (
    load_accepted_parent_artifacts,
)
from benchmarks.task43_hp_adaptivity.profile import (
    task43_initial_profile,
    task43_profile_identity,
    task43_watchdog_resource_gate_from_environment,
)
from src.adaptivity.physical_g_error import physical_g_difference_metrics
from src.adaptivity.stage4_local_h import (
    build_stage4_local_h_mesh_data,
    stage4_local_h_refinement_plan_payload,
)
from src.adaptivity.variable_p_degree_plan import cell_box_catalog
from src.common.analytic_fields_3d import (
    electric_field_code_values,
    magnetic_field_code_values,
)
from src.common.config_3d import (
    ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND,
    STANDARD_FULL_ASSEMBLY_BACKEND,
    resolve_stage4_full3d_assembly_backend,
)
from src.common.modes_3d import incident_power_3d
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.geometry.task43_hp_adaptivity_axis_plan import (
    TASK43_AXES_NM,
    TASK43_AXIS_CELL_COUNTS,
)
from src.postprocessing.physical_field_comparison import (
    build_common_volume_quadrature,
    magnetic_field_from_electric_curl,
    scattered_field_samples,
    weighted_vector_field_metrics,
)
from src.postprocessing.physical_field_sampling import (
    prepare_cell_local_vector_field_export,
    sample_cell_local_vector_fields,
)
from src.postprocessing.rta_3d import compute_volume_absorption_3d
from src.solvers.dtn_port_3d import (
    Stage4VariablePLiveView,
    _deep_readonly_copy,
    _gather_auxiliary_values,
    _linear_residual,
    _port_power_metrics,
    _readonly_goal_context,
    _write_port_outputs,
    compute_stage4_independent_active_action,
)
from src.solvers.petsc_residual_correction import single_petsc_residual_correction
from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
    run_stage4b_block_grating_3d_case,
)

_CASES = {
    "native_p3_mpi1": (1, "native_p3"),
    "empty_h_active_p3_mpi1": (1, "empty_h_active_p3"),
    "empty_h_active_p3_mpi2": (2, "empty_h_active_p3"),
    "current_active_p3_initial180_mpi1": (1, "empty_h_active_p3"),
    "round1_candidate_mpi1": (1, "empty_h_active_p3"),
}
_CURRENT_CASE = "current_active_p3_initial180_mpi1"
_ROUND1_CANDIDATE_CASE = "round1_candidate_mpi1"
_THREAD_ENV = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)
_SOURCE_FILES = (
    "benchmarks/task43_hp_adaptivity/h100_anchor.py",
    "benchmarks/task43_hp_adaptivity/candidate_records.py",
    "benchmarks/task43_hp_adaptivity/candidate_checkpoints.py",
    "benchmarks/task43_hp_adaptivity/round1_candidates.py",
    "src/adaptivity/physical_g_error.py",
    "benchmarks/task43_hp_adaptivity/profile.py",
    "benchmarks/subreaper_watchdog.py",
    "src/adaptivity/exact_sequence_variable_p.py",
    "src/adaptivity/hcurl_broken_cell_trace.py",
    "src/adaptivity/hcurl_broken_trace_graph.py",
    "src/adaptivity/stage4_local_h.py",
    "src/adaptivity/variable_p_degree_plan.py",
    "src/adaptivity/variable_p_entity_map.py",
    "src/common/analytic_fields_3d.py",
    "src/common/config_3d.py",
    "src/common/modes_3d.py",
    "src/constraints/floquet_3d.py",
    "src/geometry/mesh_builder_3d.py",
    "src/geometry/task43_hp_adaptivity_axis_plan.py",
    "src/io/native_capacity_profile.py",
    "src/postprocessing/diffraction_3d.py",
    "src/postprocessing/physical_field_comparison.py",
    "src/postprocessing/physical_field_sampling.py",
    "src/postprocessing/flat_layer_reference_3d.py",
    "src/postprocessing/postprocess_3d.py",
    "src/postprocessing/rta_3d.py",
    "src/solvers/common_3d_fields.py",
    "src/solvers/common_3d_postprocess.py",
    "src/solvers/common_3d_solve.py",
    "src/solvers/common_3d_forms.py",
    "src/solvers/common_3d_utils.py",
    "src/solvers/common_3d_case_flow.py",
    "src/solvers/dtn_port_3d.py",
    "src/solvers/hcurl_blocked_gram_tensor.py",
    "src/solvers/hcurl_variable_p_local.py",
    "src/solvers/hcurl_variable_p_assembly.py",
    "src/solvers/hcurl_variable_p_reduction.py",
    "src/solvers/independent_active_action.py",
    "src/solvers/petsc_residual_correction.py",
    "src/solvers/solve_maxwell_3d_stage_4b_block_grating.py",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _log_stage(
    comm: MPI.Intracomm,
    started: float,
    stage: str,
    status: str,
    **details: Any,
) -> None:
    if comm.rank == 0:
        print(
            json.dumps(
                {
                    "task43_stage": stage,
                    "status": status,
                    "elapsed_wall_seconds": time.perf_counter() - started,
                    **details,
                },
                sort_keys=True,
                default=_json_default,
            ),
            flush=True,
        )


def _validate_reference_run(
    run_root: Path,
    *,
    expected_case_id: str,
) -> dict[str, Any]:
    record_path = run_root / "task43_h100_anchor_record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("case_id") != expected_case_id:
        raise ValueError(
            f"reference case identity mismatch: expected {expected_case_id}, "
            f"got {record.get('case_id')}"
        )
    if record.get("gates", {}).get("pass") is not True:
        raise ValueError("reference anchor did not pass all of its gates")
    if record.get("solver", {}).get("official_result") is not True:
        raise ValueError("reference solver result is not official")
    if record.get("solver", {}).get("case_status") != "completed":
        raise ValueError("reference solver case is not completed")

    expected_files = (
        (
            run_root / "field_samples_q8_q10.npz",
            record.get("field_samples", {}).get("file"),
            record.get("field_samples", {}).get("sha256"),
            "field samples",
        ),
        (
            run_root / "solve" / "dtn_port_diffraction_orders_3d.json",
            record.get("power", {}).get("channel_rows_file"),
            record.get("power", {}).get("channel_rows_sha256"),
            "ordered channel rows",
        ),
    )
    verified: dict[str, str] = {}
    for expected_path, recorded_path, recorded_hash, label in expected_files:
        if not isinstance(recorded_path, str) or not isinstance(recorded_hash, str):
            raise TypeError(f"reference record lacks {label} identity")
        actual_path = Path(recorded_path).resolve()
        if actual_path != expected_path.resolve():
            raise ValueError(f"reference {label} path differs from its record")
        actual_hash = _sha256_file(actual_path)
        if actual_hash != recorded_hash:
            raise ValueError(f"reference {label} hash differs from its record")
        verified[label.replace(" ", "_")] = actual_hash
    return {
        "case_id": expected_case_id,
        "record_sha256": _sha256_file(record_path),
        "verified_artifact_sha256": verified,
    }


def _validate_round1_candidate_inputs(
    *,
    candidate_plan_path: Path,
    candidate_id: str,
    parent_run_root: Path,
    tightening_run_root: Path,
    marking_record_path: Path,
    acceptance_contract_path: Path,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    plan_path = candidate_plan_path.resolve()
    plan_sha = _sha256_file(plan_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    candidate = plan.get("task43_candidate")
    if not isinstance(candidate, dict) or candidate.get("candidate_id") != candidate_id:
        raise ValueError("candidate ID does not match the geometry-bound plan")
    action = candidate.get("action")
    if action not in {"p_up", "h_refine"}:
        raise ValueError(f"unsupported Task43 candidate action: {action!r}")
    provenance = candidate.get("provenance")
    if not isinstance(provenance, dict):
        raise TypeError("candidate plan is missing its frozen parent identity")
    if (
        plan.get("trace_degree") != 3
        or plan.get("cell_interior_degree") != 6
        or plan.get("variable_trace_from_cell_degrees") is not True
        or len(plan.get("cell_interior_degrees", []))
        != int(plan.get("expected_forest", {}).get("leaf_cell_count", -1))
    ):
        raise ValueError("candidate plan is not a complete p3-p6 degree map")
    expected_empty_h = action == "p_up"
    if bool(plan.get("allow_no_refinement", False)) is not expected_empty_h:
        raise ValueError("candidate h/no-h policy does not match its action")

    parent_record_path = parent_run_root / "task43_initial180_current_record.json"
    parent_storage_path = parent_run_root / "recovered_solution_storage.npz"
    parent_record = json.loads(parent_record_path.read_text(encoding="utf-8"))
    parent_record_sha = _sha256_file(parent_record_path)
    parent_storage_sha = _sha256_file(parent_storage_path)
    if parent_record.get("case_id") != _CURRENT_CASE:
        raise ValueError("candidate parent record is not the frozen 180-cell current")
    if parent_record.get("gates", {}).get("pass") is not True:
        raise ValueError("candidate parent did not pass its current hard gates")
    if (
        parent_record.get("solver", {}).get("case_status") != "completed"
        or parent_record.get("solver", {}).get("official_result") is not True
    ):
        raise ValueError("candidate parent is not a gated completed numerical result")
    if parent_record.get("recovered_solution_storage", {}).get("sha256") != parent_storage_sha:
        raise ValueError("candidate parent recovered storage differs from its record")
    if provenance.get("parent_case_record_sha256") != parent_record_sha:
        raise ValueError("candidate plan is bound to another parent case record")
    if provenance.get("parent_recovered_storage_sha256") != parent_storage_sha:
        raise ValueError("candidate plan is bound to another parent recovered field")

    tightening_record_path = tightening_run_root / "task43_initial180_current_record.json"
    tightening_record = json.loads(tightening_record_path.read_text(encoding="utf-8"))
    tightening_record_sha = _sha256_file(tightening_record_path)
    tight_storage = tightening_record.get("same_lu_tightening", {}).get(
        "recovered_solution_storage", {}
    )
    if provenance.get("tightening_record_sha256") != tightening_record_sha:
        raise ValueError("candidate plan is bound to another same-LU tightening record")
    if not isinstance(tight_storage, dict) or not tight_storage.get("sha256"):
        raise ValueError("same-LU tightening record lacks corrected full field storage")
    if _sha256_file(Path(tight_storage["file"])) != tight_storage["sha256"]:
        raise ValueError("corrected same-LU field differs from its record")

    marking_record_path = marking_record_path.resolve()
    marking_record_sha = _sha256_file(marking_record_path)
    marking_record = json.loads(marking_record_path.read_text(encoding="utf-8"))
    if provenance.get("marking_record_sha256") != marking_record_sha:
        raise ValueError("candidate plan is bound to another Dörfler marker record")
    marked_ids = [int(value) for value in marking_record["dorfler"]["initial_marked_global_cell_ids"]]
    if marked_ids != [int(value) for value in provenance.get("marked_global_cell_ids", [])]:
        raise ValueError("candidate plan Dörfler cell IDs differ from the frozen record")
    if marking_record["dorfler"].get("theta") != 0.5:
        raise ValueError("candidate plan marker is not the frozen theta=0.5 set")

    acceptance_contract_path = acceptance_contract_path.resolve()
    acceptance_sha = _sha256_file(acceptance_contract_path)
    if provenance.get("acceptance_contract_sha256") != acceptance_sha:
        raise ValueError("candidate plan is bound to another acceptance contract")
    acceptance = json.loads(acceptance_contract_path.read_text(encoding="utf-8"))
    if acceptance.get("schema") != "task43.round1-acceptance-contract.v1":
        raise ValueError("round-one acceptance contract schema is unknown")
    for evidence_key, actual_sha in (
        ("solver_tightening", tightening_record_sha),
        ("tightening_marking", marking_record_sha),
    ):
        if acceptance["evidence"][evidence_key]["sha256"] != actual_sha:
            raise ValueError(f"acceptance contract {evidence_key} evidence changed")

    identity = {
        "candidate_id": candidate_id,
        "action": action,
        "plan_path": str(plan_path),
        "plan_sha256": plan_sha,
        "parent_case_record_sha256": parent_record_sha,
        "parent_recovered_storage_sha256": parent_storage_sha,
        "tightening_record_sha256": tightening_record_sha,
        "tightened_recovered_storage_sha256": str(tight_storage["sha256"]),
        "marking_record_sha256": marking_record_sha,
        "acceptance_contract_sha256": acceptance_sha,
        "acceptance_contract_schema": acceptance["schema"],
    }
    return plan, plan_sha, identity


def _validate_accepted_candidate_inputs(
    *,
    candidate_plan_path: Path,
    candidate_id: str,
    accepted_parent_selection_record: Path,
    acceptance_contract_path: Path,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Validate a later-round candidate against a hash-bound accepted parent."""
    plan_path = candidate_plan_path.resolve()
    plan_sha = _sha256_file(plan_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    candidate = plan.get("task43_candidate", {})
    provenance = candidate.get("provenance", {})
    if candidate.get("candidate_id") != candidate_id:
        raise ValueError("candidate ID does not match its geometry-bound plan")
    if candidate.get("action") not in {"p_up", "h_refine"}:
        raise ValueError("accepted-parent plan has an unknown adaptive action")
    if (
        plan.get("trace_degree") != 3
        or plan.get("cell_interior_degree") != 6
        or plan.get("variable_trace_from_cell_degrees") is not True
        or len(plan.get("cell_interior_degrees", []))
        != int(plan.get("expected_forest", {}).get("leaf_cell_count", -1))
    ):
        raise ValueError("later-round candidate plan lacks its complete p3-p6 leaf degree map")
    expected_no_refinement = (
        candidate["action"] == "p_up" and not plan.get("marked_root_boxes", [])
    )
    if bool(plan.get("allow_no_refinement", False)) is not expected_no_refinement:
        raise ValueError("later-round candidate h/no-h policy differs from its action")

    accepted_parent = load_accepted_parent_artifacts(
        accepted_parent_selection_record,
        artifact_root=Path(__file__).resolve().parents[2],
        acceptance_contract_path=acceptance_contract_path,
    )
    selection_path = accepted_parent["selection_path"]
    selected = accepted_parent["selected"]
    selection_sha = accepted_parent["selection_sha256"]
    run_root = accepted_parent["run_root"]
    record_sha = accepted_parent["hashes"]["record_sha256"]
    storage_sha = accepted_parent["hashes"]["storage_sha256"]
    parent_plan_sha = accepted_parent["hashes"]["plan_sha256"]
    comparison_sha = accepted_parent["hashes"]["comparison_record_sha256"]
    acceptance_sha = accepted_parent["acceptance_contract_sha256"]

    expected_provenance = {
        "accepted_parent_selection_sha256": selection_sha,
        "parent_run_root": str(run_root),
        "parent_candidate_id": selected["candidate_id"],
        "parent_case_record_sha256": record_sha,
        "parent_recovered_storage_sha256": storage_sha,
        "parent_plan_sha256": parent_plan_sha,
        "parent_comparison_sha256": comparison_sha,
        "acceptance_contract_sha256": acceptance_sha,
        "selection_reference_role": "Y6_1",
        "holdout_excluded": "Y5_1",
        "final_6x10x6_p6_control_excluded_from_selection": True,
    }
    if any(provenance.get(key) != value for key, value in expected_provenance.items()):
        raise ValueError("candidate plan provenance differs from the accepted parent selection")
    if Path(str(provenance.get("accepted_parent_selection_record_path"))).resolve() != selection_path:
        raise ValueError("candidate plan names a different accepted selection record")

    identity = {
        "candidate_id": candidate_id,
        "action": candidate["action"],
        "plan_path": str(plan_path),
        "plan_sha256": plan_sha,
        "parent_selection_record_path": str(selection_path),
        "accepted_parent_selection_sha256": selection_sha,
        "parent_candidate_id": str(selected["candidate_id"]),
        "parent_run_root": str(run_root),
        "parent_case_record_sha256": record_sha,
        "parent_recovered_storage_sha256": storage_sha,
        "parent_plan_sha256": parent_plan_sha,
        "parent_comparison_record_sha256": comparison_sha,
        "acceptance_contract_sha256": acceptance_sha,
    }
    return plan, plan_sha, identity


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _h100_config(
    *, kind: str, case_name: str, geometry_profile: str = "h100"
):
    degree = 3 if kind == "native_p3" else 6
    cfg = task43_initial_profile(case_name=case_name)
    cfg.nedelec_degree = degree
    cfg.visualization_degree = degree
    if geometry_profile == "h100":
        # The component anchors deliberately resolve their own h=100 nm mesh.
        cfg.mesh_plan_id = None
        cfg.mesh_plan_sha256 = None
        cfg.mesh_axis_cell_counts = None
        cfg.mesh_axis_x_values = None
        cfg.mesh_axis_y_values = None
        cfg.mesh_axis_z_values = None
        cfg.mesh_axis_z_profile = None
        cfg.mesh_spacing_mode = "boundary_fitted"
        cfg.mesh_target_size = 100.0
    elif geometry_profile == "initial_180":
        if kind != "empty_h_active_p3":
            raise ValueError("the frozen 180-cell current uses active-p3 on p6")
    else:
        raise ValueError(f"unknown Task43 geometry profile {geometry_profile!r}")
    cfg.mesh_cell_type = "hexahedron"
    if geometry_profile == "h100":
        cfg.mesh_refined_size = None
        cfg.mesh_refinement_radius = None
    cfg.stage4_variable_p_cell_degree_plan = None
    cfg.stage4_local_h_refinement_plan = None
    cfg.matrix_diagnostics_assemble_only = False
    cfg.matrix_diagnostics_factorization_only = False
    cfg.unique_output = False
    cfg.stage4_full3d_assembly_backend = (
        STANDARD_FULL_ASSEMBLY_BACKEND
        if kind == "native_p3"
        else ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
    )
    if kind == "native_p3":
        cfg.stage4_variable_p_raw_tensor_backend = None
    return cfg


def _mesh_axes(mesh, comm: MPI.Intracomm) -> tuple[np.ndarray, ...]:
    topological_dimension = int(mesh.topology.dim)
    cell_map = mesh.topology.index_map(topological_dimension)
    local_vertices = [
        np.asarray(
            mesh.geometry.x[np.asarray(mesh.geometry.dofmap[cell]), :3],
            dtype=np.float64,
        )
        for cell in range(int(cell_map.size_local))
    ]
    if local_vertices:
        local_points = np.vstack(local_vertices)
    else:
        local_points = np.zeros((0, 3), dtype=np.float64)
    packets = comm.allgather(local_points)
    all_points = np.vstack([packet for packet in packets if len(packet)])
    axes = tuple(np.unique(all_points[:, axis]) for axis in range(3))
    return axes


def _assert_mesh_profile(
    mesh_data,
    axes: tuple[np.ndarray, ...],
    geometry_profile: str,
    candidate_plan: dict[str, Any] | None = None,
    candidate_plan_sha256: str | None = None,
) -> dict[str, Any]:
    cell_map = mesh_data.mesh.topology.index_map(mesh_data.mesh.topology.dim)
    global_cells = int(cell_map.size_global)
    cell_counts = tuple(len(axis) - 1 for axis in axes)
    if geometry_profile == "candidate_initial180":
        if candidate_plan is None:
            raise ValueError("candidate mesh validation requires its exact plan")
        context = mesh_data.local_h_context
        forest = context.forest
        expected_forest = candidate_plan["expected_forest"]
        forest_audit = context.audit["forest"]
        root_catalog_sha256 = _sha256_json(
            [
                {"box": list(box), "material_tag": int(tag)}
                for box, tag in zip(
                    forest.root_boxes,
                    forest.root_material_tags,
                    strict=True,
                )
            ]
        )
        base_axes = tuple(
            np.asarray(TASK43_AXES_NM[name], dtype=np.float64)
            for name in ("x", "y", "z")
        )
        if any(
            not set(axis.tolist()).issubset(set(actual.tolist()))
            for axis, actual in zip(base_axes, axes, strict=True)
        ):
            raise RuntimeError("candidate mesh lost a frozen 180-cell base-axis breakpoint")
        if global_cells != int(expected_forest["leaf_cell_count"]):
            raise RuntimeError(
                "candidate global cell count differs from its audited forest: "
                f"mesh={global_cells}, plan={expected_forest['leaf_cell_count']}"
            )
        if len(forest.root_boxes) != int(expected_forest["root_cell_count"]):
            raise RuntimeError("candidate forest root count differs from its plan")
        if len(forest.leaves) != global_cells:
            raise RuntimeError("candidate forest leaf count differs from the global mesh")
        if len(context.cell_interior_degree_by_box) != global_cells:
            raise RuntimeError("candidate degree map is not complete over actual leaves")
        if (
            candidate_plan_sha256 is None
            or context.audit["plan_file_sha256"] != candidate_plan_sha256
        ):
            raise RuntimeError("candidate mesh did not load the supplied plan identity")
        if forest_audit["leaf_catalog_sha256"] != expected_forest[
            "leaf_catalog_sha256"
        ]:
            raise RuntimeError("candidate leaf catalogue differs from its plan")
        if root_catalog_sha256 != expected_forest["root_catalog_sha256"]:
            raise RuntimeError("candidate root catalogue differs from its plan")
        if context.audit["cell_interior_degree_plan_sha256"] != candidate_plan[
            "cell_interior_degree_plan_sha256"
        ]:
            raise RuntimeError("candidate degree map differs from its plan")
        expected_bounds = ((0.0, 50.0), (0.0, 50.0), (-10.0, 130.0))
        for axis, bounds in zip(axes, expected_bounds, strict=True):
            if not np.isclose(axis[0], bounds[0]) or not np.isclose(axis[-1], bounds[1]):
                raise RuntimeError(f"candidate mesh has unexpected domain endpoints: {axis}")
        return {
            "geometry_profile": geometry_profile,
            "global_cells": global_cells,
            "root_cell_count": len(forest.root_boxes),
            "leaf_cell_count": len(forest.leaves),
            "axis_union_interval_counts_xyz": list(cell_counts),
            "axis_union_interval_product_not_global_cell_count": True,
            "axes_nm": [axis.tolist() for axis in axes],
            "axis_values_sha256": _sha256_json([axis.tolist() for axis in axes]),
            "base_axis_values_sha256": _sha256_json(
                [axis.tolist() for axis in base_axes]
            ),
            "leaf_catalog_sha256": str(
                forest_audit["leaf_catalog_sha256"]
            ),
            "root_catalog_sha256": root_catalog_sha256,
            "closure_split_counts": dict(
                forest_audit["closure_split_counts"]
            ),
            "hanging_patch_count": int(context.audit["hanging_patch_count"]),
            "plan_sha256": str(context.audit["plan_file_sha256"]),
            "spacing_mode_resolved": str(mesh_data.mesh_spacing_mode_resolved),
            "mesh_cell_type_resolved": str(mesh_data.mesh_cell_type_resolved),
            "material_plane_alignment": mesh_data.material_plane_alignment,
        }
    if geometry_profile == "h100":
        expected_global_cells = 36
        expected_counts = (3, 3, 4)
        expected_axes = None
        profile_label = "qualified 36-cell 3x3x4 h100 geometry"
    elif geometry_profile == "initial_180":
        expected_global_cells = int(np.prod(TASK43_AXIS_CELL_COUNTS))
        expected_counts = tuple(TASK43_AXIS_CELL_COUNTS)
        expected_axes = TASK43_AXES_NM
        profile_label = "frozen Task43 initial 180-cell 3x10x6 geometry"
    else:
        raise ValueError(f"unknown Task43 geometry profile {geometry_profile!r}")
    if global_cells != expected_global_cells or cell_counts != expected_counts:
        raise RuntimeError(
            f"mesh differs from the {profile_label}: "
            f"cells={global_cells}, axes={cell_counts}"
        )
    if tuple(mesh_data.mesh_cells_resolved) != cell_counts:
        raise RuntimeError(
            "mesh builder cell counts disagree with resolved coordinate axes: "
            f"builder={mesh_data.mesh_cells_resolved}, axes={cell_counts}"
        )
    if expected_axes is not None and any(
        not np.array_equal(axis, np.asarray(expected_axes[name], dtype=np.float64))
        for name, axis in zip(("x", "y", "z"), axes, strict=True)
    ):
        raise RuntimeError("actual mesh coordinates differ from frozen Task43 axes")
    expected_bounds = ((0.0, 50.0), (0.0, 50.0), (-10.0, 130.0))
    for axis, bounds in zip(axes, expected_bounds, strict=True):
        if not np.isclose(axis[0], bounds[0]) or not np.isclose(axis[-1], bounds[1]):
            raise RuntimeError(f"resolved mesh has unexpected domain endpoints: {axis}")
    return {
        "geometry_profile": geometry_profile,
        "global_cells": global_cells,
        "axis_cell_counts_xyz": list(cell_counts),
        "axes_nm": [axis.tolist() for axis in axes],
        "axis_values_sha256": _sha256_json([axis.tolist() for axis in axes]),
        "spacing_mode_resolved": str(mesh_data.mesh_spacing_mode_resolved),
        "mesh_cell_type_resolved": str(mesh_data.mesh_cell_type_resolved),
        "material_plane_alignment": mesh_data.material_plane_alignment,
    }


def _assert_h100_mesh(mesh_data, axes: tuple[np.ndarray, ...]) -> dict[str, Any]:
    return _assert_mesh_profile(mesh_data, axes, "h100")


def _native_explicit_residual(linear_system: dict[str, Any]) -> dict[str, float]:
    matrix = linear_system["A"]
    rhs = linear_system["b"]
    solution = linear_system["x"]
    if matrix is None or rhs is None or solution is None:
        raise RuntimeError("native standard solver did not retain A, b, and x")
    residual = rhs.duplicate()
    try:
        matrix.mult(solution, residual)
        residual.axpy(PETSc.ScalarType(-1.0), rhs)
        residual_norm = float(residual.norm())
        rhs_norm = float(rhs.norm())
        return {
            "explicit_augmented_Ax_minus_b_norm": residual_norm,
            "augmented_rhs_norm": rhs_norm,
            "relative_to_rhs": residual_norm / max(rhs_norm, 1.0e-30),
            "classification": "standard_full_explicit_augmented_true_residual",
        }
    finally:
        residual.destroy()


def _array_identity(values: np.ndarray) -> dict[str, Any]:
    array = np.ascontiguousarray(values)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(json.dumps(list(array.shape)).encode("ascii"))
    digest.update(array.view(np.uint8))
    return {
        "dtype": array.dtype.str,
        "shape": list(array.shape),
        "sha256": digest.hexdigest(),
    }


def _active_solution_storage(view) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Copy the recovered carrier and active vectors before the observer lease ends."""

    field = view.recovered.field
    mesh = view.mesh_data.mesh
    function_dofmap = field.function_space.dofmap
    function_index_map = function_dofmap.index_map
    topology_dimension = int(mesh.topology.dim)
    cell_connectivity = mesh.topology.connectivity(topology_dimension, 0)
    if cell_connectivity is None:
        raise RuntimeError("cell-to-vertex connectivity was not prepared before observation")
    cell_vertices = cell_connectivity.array
    cell_index_map = mesh.topology.index_map(topology_dimension)
    cell_owned_ids = cell_index_map.local_to_global(
        np.arange(cell_index_map.size_local, dtype=np.int32)
    )
    dof_owned_ids = function_index_map.local_to_global(
        np.arange(function_index_map.size_local, dtype=np.int32)
    )

    def owned_values(vector) -> np.ndarray | None:
        if vector is None:
            return None
        return np.asarray(vector.getArray(readonly=True)).copy()

    p6_owned = owned_values(field.x.petsc_vec)
    active_solution = owned_values(view.recovered.active_full_solution)
    active_rhs = owned_values(view.recovered.active_full_rhs)
    if p6_owned is None or active_solution is None or active_rhs is None:
        raise RuntimeError("active current storage is missing an owned solution/RHS")
    arrays: dict[str, np.ndarray] = {
        "recovered_p6_local_coefficients": np.asarray(field.x.array).copy(),
        "recovered_p6_owned_coefficients": p6_owned,
        "mesh_geometry_coordinates_nm": np.asarray(mesh.geometry.x).copy(),
        "mesh_geometry_dofmap": np.asarray(mesh.geometry.dofmap).copy(),
        "mesh_owned_cell_global_ids": np.asarray(cell_owned_ids, dtype=np.int64),
        "mesh_cell_vertex_dofmap": np.asarray(cell_vertices).copy(),
        "p6_function_space_dofmap": np.asarray(function_dofmap.list).copy(),
        "p6_owned_global_dof_block_ids": np.asarray(dof_owned_ids, dtype=np.int64),
        "p6_ghost_global_dof_block_ids": np.asarray(
            function_index_map.ghosts, dtype=np.int64
        ).copy(),
        "active_full_solution_owned": active_solution,
        "active_full_rhs_owned": active_rhs,
    }
    if view.recovered.active_auxiliary_interior_action is not None:
        arrays["active_auxiliary_interior_action_owned"] = owned_values(
            view.recovered.active_auxiliary_interior_action
        )

    def vector_layout(vector) -> dict[str, Any] | None:
        if vector is None:
            return None
        return {
            "global_size": int(vector.getSize()),
            "local_size": int(vector.getLocalSize()),
            "ownership_range": [int(value) for value in vector.getOwnershipRange()],
        }

    mesh_identity_arrays = (
        "mesh_geometry_coordinates_nm",
        "mesh_geometry_dofmap",
        "mesh_owned_cell_global_ids",
        "mesh_cell_vertex_dofmap",
        "p6_function_space_dofmap",
        "p6_owned_global_dof_block_ids",
        "p6_ghost_global_dof_block_ids",
    )
    cell_degree_counts = dict(view.reduction.degree_plan.audit["cell_degree_counts"])
    independent_trace_rows = int(view.reduction.system.active_trace_rows)
    active_cell_interior_rows = int(
        view.reduction.system.entity_map.active_cell_interior_rows
    )
    reduction_audit = view.reduction.build_audit
    trace_constraint_audit = reduction_audit.get("trace_constraints") or {}
    metadata = {
        "representation": (
            "variable-p active solution recovered into the full p6 carrier function; "
            "the local carrier vector includes ghost slots and a separate owned "
            "coefficient segment is stored; cell-degree counts are recorded"
        ),
        "active_cell_degree_counts": cell_degree_counts,
        "mpi_size": int(MPI.COMM_WORLD.size),
        "p6_field_local_vector_size": int(field.x.array.size),
        "p6_field_owned_vector": vector_layout(field.x.petsc_vec),
        "p6_dof_index_map": {
            "size_global_blocks": int(function_index_map.size_global),
            "size_local_blocks": int(function_index_map.size_local),
            "num_ghost_blocks": int(function_index_map.num_ghosts),
            "block_size": int(function_dofmap.index_map_bs),
        },
        "active_full_solution_vector": vector_layout(
            view.recovered.active_full_solution
        ),
        "active_full_rhs_vector": vector_layout(view.recovered.active_full_rhs),
        "active_rows": int(view.reduction.system.entity_map.active_rows),
        "active_trace_rows": int(view.reduction.system.active_trace_rows),
        "active_cell_interior_rows": active_cell_interior_rows,
        "independent_trace_rows": independent_trace_rows,
        "independent_active_fe_dofs": (
            independent_trace_rows + active_cell_interior_rows
        ),
        "active_fe_dof_gate_policy": reduction_audit.get(
            "active_fe_dof_gate_policy"
        ),
        "active_fe_dof_gate_limit": reduction_audit.get(
            "active_fe_dof_gate_limit"
        ),
        "active_fe_dof_gate_pass": reduction_audit.get(
            "active_fe_dof_gate_pass"
        ),
        "degree_plan_pass": view.reduction.degree_plan.audit.get("pass"),
        "trace_constraints_pass": trace_constraint_audit.get("pass"),
        "trace_constraints_status": trace_constraint_audit.get("status"),
        "p6_field_recovery_audit": dict(view.recovered.audit),
        "mesh_and_dof_order_arrays": {
            name: _array_identity(arrays[name]) for name in mesh_identity_arrays
        },
    }
    metadata["mesh_and_dof_order_sha256"] = _sha256_json(
        metadata["mesh_and_dof_order_arrays"]
    )
    metadata["active_degree_plan_sha256"] = str(
        view.reduction.degree_plan.audit["cell_degree_plan_sha256"]
    )
    return arrays, metadata


def _field_capture(
    field,
    mesh_data,
    cfg,
    comm: MPI.Intracomm,
    reference_axes: tuple[np.ndarray, ...] | None,
    geometry_profile: str = "h100",
    candidate_plan: dict[str, Any] | None = None,
    candidate_plan_sha256: str | None = None,
    sample_fields: bool = True,
) -> dict[str, Any]:
    export = prepare_cell_local_vector_field_export(field)
    axes = _mesh_axes(mesh_data.mesh, comm)
    mesh_identity = _assert_mesh_profile(
        mesh_data,
        axes,
        geometry_profile,
        candidate_plan=candidate_plan,
        candidate_plan_sha256=candidate_plan_sha256,
    )
    if reference_axes is not None and any(
        not np.array_equal(axis, reference_axis)
        for axis, reference_axis in zip(axes, reference_axes, strict=True)
    ):
        raise RuntimeError("candidate mesh axes differ from the native h100 mesh")
    samples: dict[str, dict[str, np.ndarray]] = {}
    sample_error = None
    for order in ((8, 10) if sample_fields else ()):
        common_axes = [axes] if reference_axes is None else [reference_axes, axes]
        quadrature = build_common_volume_quadrature(
            common_axes, gauss_order=order
        )
        sampled = sample_cell_local_vector_fields(
            {
                "E_total": export.electric_dgq6,
                "curl_E_total": export.curl_electric_dgq6,
            },
            quadrature.points_nm,
        )
        if comm.rank == 0:
            try:
                assert sampled is not None
                curl = sampled["curl_E_total"]
                magnetic = magnetic_field_from_electric_curl(
                    curl,
                    magnetic_field_scale_A_per_m=cfg.magnetic_field_scale_A_per_m,
                    k0_per_nm=cfg.k0,
                    mu_r=cfg.mu_r,
                )
                samples[f"q{order}"] = {
                    "points_nm": quadrature.points_nm,
                    "weights_nm3": quadrature.weights_nm3,
                    "E_total": sampled["E_total"],
                    "curl_E_total": curl,
                    "H_total_A_per_m": magnetic,
                }
            except (
                AssertionError,
                IndexError,
                OverflowError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as exc:
                sample_error = f"{type(exc).__name__}: {exc}"
        errors = comm.allgather(sample_error)
        if any(error is not None for error in errors):
            raise RuntimeError(
                "field sample postprocessing failed collectively: "
                + "; ".join(
                    f"rank {rank}: {error}"
                    for rank, error in enumerate(errors)
                    if error is not None
                )
            )
    return {
        "source_degree": int(export.source_degree),
        "target_degree": int(export.target_degree),
        "representation": export.representation,
        "mesh_identity": mesh_identity,
        "axes_nm": {
            name: axis.tolist()
            for name, axis in zip(("x", "y", "z"), axes, strict=True)
        },
        "samples": samples,
    }


def _array_norm(values: np.ndarray, weights: np.ndarray) -> float:
    return float(np.sqrt(np.dot(weights, np.sum(np.abs(values) ** 2, axis=1))))


def _field_comparison(
    current: dict[str, dict[str, np.ndarray]],
    reference_path: Path,
    cfg,
) -> dict[str, Any]:
    from src.common.analytic_fields_3d import (
        electric_field_code_values,
        magnetic_field_code_values,
    )

    volume = float(cfg.period_x * cfg.period_y * (cfg.domain_z_max - cfg.domain_z_min))
    e_floor = float(np.sqrt(volume))
    h_floor = e_floor * float(cfg.magnetic_field_scale_A_per_m)
    g_floor = float(np.sqrt(2.0 * volume))
    result: dict[str, Any] = {}
    with np.load(reference_path, allow_pickle=False) as reference:
        for order in (8, 10):
            key = f"q{order}"
            observed = current[key]
            ref_points = reference[f"{key}_points_nm"]
            if not np.array_equal(observed["points_nm"], ref_points):
                raise ValueError(f"{key} quadrature points differ from native p3")
            weights = reference[f"{key}_weights_nm3"]
            if not np.array_equal(observed["weights_nm3"], weights):
                raise ValueError(f"{key} quadrature weights differ from native p3")
            background_e = electric_field_code_values(cfg, observed["points_nm"])
            background_h = cfg.magnetic_field_scale_A_per_m * magnetic_field_code_values(
                cfg, observed["points_nm"]
            )
            reference_e_scattered = scattered_field_samples(
                reference[f"{key}_E_total"], background_e
            )
            current_e_scattered = scattered_field_samples(
                observed["E_total"], background_e
            )
            reference_h_scattered = scattered_field_samples(
                reference[f"{key}_H_total_A_per_m"], background_h
            )
            current_h_scattered = scattered_field_samples(
                observed["H_total_A_per_m"], background_h
            )

            metrics = {
                "E_total_code": weighted_vector_field_metrics(
                    reference[f"{key}_E_total"],
                    observed["E_total"],
                    weights,
                    reference_norm_floor=e_floor,
                ),
                "curl_E_over_k0_code": weighted_vector_field_metrics(
                    reference[f"{key}_curl_E_total"] / cfg.k0,
                    observed["curl_E_total"] / cfg.k0,
                    weights,
                    reference_norm_floor=e_floor,
                ),
                "H_total_A_per_m": weighted_vector_field_metrics(
                    reference[f"{key}_H_total_A_per_m"],
                    observed["H_total_A_per_m"],
                    weights,
                    reference_norm_floor=h_floor,
                ),
                "E_scattered_code": weighted_vector_field_metrics(
                    reference_e_scattered,
                    current_e_scattered,
                    weights,
                    reference_norm_floor=e_floor,
                ),
                "H_scattered_A_per_m": weighted_vector_field_metrics(
                    reference_h_scattered,
                    current_h_scattered,
                    weights,
                    reference_norm_floor=h_floor,
                ),
            }
            e_delta = observed["E_total"] - reference[f"{key}_E_total"]
            curl_delta = (
                observed["curl_E_total"] - reference[f"{key}_curl_E_total"]
            ) / cfg.k0
            g_delta = np.sqrt(
                np.sum(np.abs(e_delta) ** 2 + np.abs(curl_delta) ** 2, axis=1)
            )
            g_reference = np.sqrt(
                np.sum(
                    np.abs(reference[f"{key}_E_total"]) ** 2
                    + np.abs(reference[f"{key}_curl_E_total"] / cfg.k0) ** 2,
                    axis=1,
                )
            )
            g_difference = float(np.sqrt(np.dot(weights, g_delta**2)))
            g_reference_norm = float(np.sqrt(np.dot(weights, g_reference**2)))
            metrics["G"] = {
                "difference_norm": g_difference,
                "reference_norm": g_reference_norm,
                "relative_with_incident_floor": g_difference
                / max(g_reference_norm, g_floor),
                "incident_floor": g_floor,
            }
            result[key] = metrics
    return result


def _complex_rows(rows: list[dict[str, Any]]) -> np.ndarray:
    return np.asarray(
        [complex(*row["outgoing_amplitude_at_boundary"]) for row in rows],
        dtype=np.complex128,
    )


def _modal_comparison(
    current_rows: list[dict[str, Any]],
    current_metrics: dict[str, Any],
    current_a_volume: float | None,
    reference_run_root: Path,
) -> dict[str, Any]:
    with (reference_run_root / "solve" / "dtn_port_diffraction_orders_3d.json").open(
        encoding="utf-8"
    ) as stream:
        reference_payload = json.load(stream)
    reference_rows = reference_payload["orders"]
    current_keys = [
        (row["side"], int(row["m"]), int(row["n"]), row["polarization"])
        for row in current_rows
    ]
    reference_keys = [
        (row["side"], int(row["m"]), int(row["n"]), row["polarization"])
        for row in reference_rows
    ]
    if current_keys != reference_keys:
        raise ValueError("native and active ordered R13 mode inventories differ")
    current_amplitudes = _complex_rows(current_rows)
    reference_amplitudes = _complex_rows(reference_rows)
    amplitude_difference = current_amplitudes - reference_amplitudes
    group_metrics: dict[str, Any] = {}
    for side in ("top", "bottom"):
        for polarization in ("s", "p"):
            indices = [
                index
                for index, row in enumerate(current_rows)
                if row["side"] == side and row["polarization"] == polarization
            ]
            ref = reference_amplitudes[indices]
            delta = amplitude_difference[indices]
            reference_norm = float(np.linalg.norm(ref))
            difference_norm = float(np.linalg.norm(delta))
            group_metrics[f"{side}_{polarization}"] = {
                "entry_count": len(indices),
                "reference_l2": reference_norm,
                "difference_l2": difference_norm,
                "raw_relative": (
                    difference_norm / reference_norm if reference_norm > 0.0 else None
                ),
                "relative_with_unit_modal_floor": difference_norm
                / max(reference_norm, 1.0),
            }
    channel_power_delta = np.asarray(
        [
            abs(float(row["power_ratio"]) - float(reference_rows[index]["power_ratio"]))
            for index, row in enumerate(current_rows)
        ],
        dtype=np.float64,
    )
    max_power_index = int(np.argmax(channel_power_delta))
    aggregate = {}
    for key in ("R_total", "T_total", "R00_s", "R00_p", "R00_total"):
        current = float(current_metrics[key])
        reference = float(reference_payload["metrics"][key])
        aggregate[key] = {
            "current": current,
            "reference": reference,
            "absolute_difference": abs(current - reference),
        }
    if current_a_volume is not None:
        with (reference_run_root / "task43_h100_anchor_record.json").open(
            encoding="utf-8"
        ) as stream:
            reference_record = json.load(stream)
        reference_a_volume = reference_record["power"]["A_volume_total"]
        aggregate["A_volume_total"] = {
            "current": float(current_a_volume),
            "reference": float(reference_a_volume),
            "absolute_difference": abs(
                float(current_a_volume) - float(reference_a_volume)
            ),
        }
    return {
        "mode_count": len(current_rows),
        "ordered_mode_keys_sha256": _sha256_json(current_keys),
        "ordered_boundary_amplitudes_sha256": _sha256_json(
            [[float(value.real), float(value.imag)] for value in current_amplitudes]
        ),
        "maximum_channel_power_absolute_difference": float(
            channel_power_delta[max_power_index]
        ),
        "maximum_channel_power_difference_mode": list(current_keys[max_power_index]),
        "amplitude_groups": group_metrics,
        "aggregate_power": aggregate,
    }


def _comparison_gates(
    field_metrics: dict[str, Any],
    modal_metrics: dict[str, Any],
) -> dict[str, bool]:
    max_field = max(
        metric["relative_to_reference_or_floor"]
        for order_metrics in field_metrics.values()
        for name, metric in order_metrics.items()
        if name != "G"
    )
    max_g = max(
        order_metrics["G"]["relative_with_incident_floor"]
        for order_metrics in field_metrics.values()
    )
    max_amplitude = max(
        metric["relative_with_unit_modal_floor"]
        for metric in modal_metrics["amplitude_groups"].values()
    )
    max_aggregate_power = max(
        item["absolute_difference"]
        for item in modal_metrics["aggregate_power"].values()
    )
    return {
        "field_and_modal_amplitude_max_relative_le_1e-8": bool(
            max(max_field, max_g, max_amplitude) <= 1.0e-8
        ),
        "aggregate_power_max_absolute_le_1e-8": bool(
            max_aggregate_power <= 1.0e-8
        ),
        "maximum_channel_power_absolute_le_1e-8": bool(
            modal_metrics["maximum_channel_power_absolute_difference"]
            <= 1.0e-8
        ),
    }


def _compare_against_reference(
    *,
    current_rows: list[dict[str, Any]],
    current_port_metrics: dict[str, Any],
    current_a_volume: float,
    current_field_samples: dict[str, Any],
    reference_run_root: Path,
    cfg,
) -> dict[str, Any]:
    field_metrics = _field_comparison(
        current_field_samples,
        reference_run_root / "field_samples_q8_q10.npz",
        cfg,
    )
    modal_metrics = _modal_comparison(
        current_rows,
        current_port_metrics,
        current_a_volume,
        reference_run_root,
    )
    return {
        "field_metrics_q8_q10": field_metrics,
        "modal_metrics": modal_metrics,
        "gates": _comparison_gates(field_metrics, modal_metrics),
    }


def _tightening_field_metrics(
    reference: dict[str, np.ndarray],
    candidate: dict[str, np.ndarray],
    cfg,
) -> dict[str, Any]:
    points = reference["points_nm"]
    weights = reference["weights_nm3"]
    if not np.array_equal(points, candidate["points_nm"]):
        raise ValueError("same-LU field samples use different quadrature points")
    if not np.array_equal(weights, candidate["weights_nm3"]):
        raise ValueError("same-LU field samples use different quadrature weights")
    volume = float(
        cfg.period_x * cfg.period_y * (cfg.domain_z_max - cfg.domain_z_min)
    )
    e_floor = float(np.sqrt(volume))
    h_floor = e_floor * float(cfg.magnetic_field_scale_A_per_m)
    background_e = electric_field_code_values(cfg, points)
    background_h = cfg.magnetic_field_scale_A_per_m * magnetic_field_code_values(
        cfg, points
    )
    reference_e_scattered = scattered_field_samples(
        reference["E_total"], background_e
    )
    candidate_e_scattered = scattered_field_samples(
        candidate["E_total"], background_e
    )
    reference_h_scattered = scattered_field_samples(
        reference["H_total_A_per_m"], background_h
    )
    candidate_h_scattered = scattered_field_samples(
        candidate["H_total_A_per_m"], background_h
    )
    return {
        "E_total_code": weighted_vector_field_metrics(
            reference["E_total"], candidate["E_total"], weights,
            reference_norm_floor=e_floor,
        ),
        "curl_E_over_k0_code": weighted_vector_field_metrics(
            reference["curl_E_total"] / cfg.k0,
            candidate["curl_E_total"] / cfg.k0,
            weights,
            reference_norm_floor=e_floor,
        ),
        "H_total_A_per_m": weighted_vector_field_metrics(
            reference["H_total_A_per_m"],
            candidate["H_total_A_per_m"],
            weights,
            reference_norm_floor=h_floor,
        ),
        "E_scattered_code": weighted_vector_field_metrics(
            reference_e_scattered,
            candidate_e_scattered,
            weights,
            reference_norm_floor=e_floor,
        ),
        "H_scattered_A_per_m": weighted_vector_field_metrics(
            reference_h_scattered,
            candidate_h_scattered,
            weights,
            reference_norm_floor=h_floor,
        ),
        "G": physical_g_difference_metrics(
            reference["E_total"],
            candidate["E_total"],
            reference["curl_E_total"],
            candidate["curl_E_total"],
            weights,
            k0_per_nm=cfg.k0,
            incident_g_norm_floor=float(np.sqrt(2.0 * volume)),
        ),
    }


def _tightening_modal_metrics(
    reference_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    def key(row: dict[str, Any]) -> tuple[str, int, int, str]:
        return str(row["side"]), int(row["m"]), int(row["n"]), str(row["polarization"])

    reference_keys = [key(row) for row in reference_rows]
    candidate_keys = [key(row) for row in candidate_rows]
    if reference_keys != candidate_keys or len(reference_keys) != 612:
        raise ValueError("same-LU modal inventories differ or are incomplete")
    reference_amplitudes = _complex_rows(reference_rows)
    candidate_amplitudes = _complex_rows(candidate_rows)
    delta = candidate_amplitudes - reference_amplitudes
    groups: dict[str, Any] = {}
    for side in ("top", "bottom"):
        for polarization in ("s", "p"):
            indices = [
                index for index, row in enumerate(reference_rows)
                if row["side"] == side and row["polarization"] == polarization
            ]
            reference_norm = float(np.linalg.norm(reference_amplitudes[indices]))
            difference_norm = float(np.linalg.norm(delta[indices]))
            groups[f"{side}_{polarization}"] = {
                "entry_count": len(indices),
                "reference_boundary_amplitude_l2": reference_norm,
                "difference_boundary_amplitude_l2": difference_norm,
                "raw_relative": difference_norm / reference_norm if reference_norm else None,
                "relative_with_unit_modal_floor": difference_norm / max(reference_norm, 1.0),
            }
    power_delta = np.asarray(
        [
            abs(float(candidate["power_ratio"]) - float(reference["power_ratio"]))
            for reference, candidate in zip(reference_rows, candidate_rows, strict=True)
        ],
        dtype=np.float64,
    )
    max_index = int(np.argmax(power_delta))
    return {
        "mode_count": len(reference_rows),
        "ordered_mode_keys_sha256": _sha256_json(reference_keys),
        "maximum_channel_power_absolute_difference": float(power_delta[max_index]),
        "maximum_channel_power_difference_mode": list(reference_keys[max_index]),
        "amplitude_groups": groups,
    }


def _same_lu_tightening(
    view: Stage4VariablePLiveView,
    *,
    run_root: Path,
    comm: MPI.Intracomm,
    started: float,
    initial_fields: dict[str, Any],
) -> dict[str, Any]:
    """Apply one existing-KSP residual correction and capture the new state."""

    if view.port_operator_audit.get("pass") is not True:
        raise RuntimeError("same-LU correction requires the qualified trace-only port audit")
    checks = view.port_operator_audit.get("checks", {})
    if checks.get("no_auxiliary_interior_columns") is not True:
        raise RuntimeError("same-LU correction requires no auxiliary interior columns")
    old_auxiliary_action = view.recovered.active_auxiliary_interior_action
    if old_auxiliary_action is not None and float(old_auxiliary_action.norm()) != 0.0:
        raise RuntimeError("same-LU correction found nonzero auxiliary interior action")

    _log_stage(comm, started, "same_lu_residual_correction", "begin")
    corrected_x, correction = single_petsc_residual_correction(
        view.A, view.b, view.x, view.ksp
    )
    try:
        modes = tuple(view.goal_context["modes"])
        n_auxiliary = len(modes)
        n_fem_tail = int(corrected_x.getSize()) - n_auxiliary
        if n_auxiliary != 612 or n_fem_tail < 0:
            raise RuntimeError("corrected vector does not contain the full ordered R13 tail")
        old_auxiliary = _gather_auxiliary_values(
            view.x, int(view.x.getSize()) - n_auxiliary, n_auxiliary, comm
        )
        stored_auxiliary = np.asarray(
            view.goal_context["auxiliary_values"], dtype=np.complex128
        )
        if not np.array_equal(old_auxiliary, stored_auxiliary):
            raise RuntimeError("original ordered modal tail differs from the observer context")
        corrected_auxiliary = _gather_auxiliary_values(
            corrected_x, n_fem_tail, n_auxiliary, comm
        )
        incident_projections = [
            complex(value)
            for value in view.goal_context["incident_projections"]
        ]
        corrected_port_metrics = _port_power_metrics(
            view.config,
            list(modes),
            corrected_auxiliary,
            incident_projections,
        )
        corrected_reduced_residual = _linear_residual(view.A, view.b, corrected_x)
        corrected_recovered = view.reduction.recover(
            corrected_x,
            None,
            active_full_rhs_override=view.recovered.active_full_rhs,
        )
        try:
            updated_goal_context = dict(view.goal_context)
            updated_goal_context["auxiliary_values"] = corrected_auxiliary
            _log_stage(comm, started, "same_lu_recovery_and_a6", "begin")
            condensed_residual = view.reduction.full_active_residual(
                view.A, view.b, corrected_x, corrected_recovered
            )
            corrected_view = replace(
                view,
                field=corrected_recovered.field,
                x=corrected_x,
                recovered=corrected_recovered,
                goal_context=_readonly_goal_context(updated_goal_context),
                port_metrics=_deep_readonly_copy(corrected_port_metrics),
                full_active_residual=_deep_readonly_copy(condensed_residual),
                primal_solver_telemetry=_deep_readonly_copy(
                    {
                        **dict(view.primal_solver_telemetry),
                        **corrected_reduced_residual,
                        "corrected_condensed_full_active_residual": condensed_residual,
                        "residual_correction": correction,
                    }
                ),
            )
            independent_active_action = compute_stage4_independent_active_action(
                corrected_view
            )
            _log_stage(comm, started, "same_lu_recovery_and_a6", "end")

            root_error = None
            tight_root = run_root / "same_lu_tightening"
            ports_root = tight_root / "ports"
            if comm.rank == 0:
                try:
                    if tight_root.exists() and any(tight_root.iterdir()):
                        raise FileExistsError(
                            f"refusing to overwrite same-LU result {tight_root}"
                        )
                    ports_root.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    root_error = f"{type(exc).__name__}: {exc}"
            root_error = comm.bcast(root_error, root=0)
            if root_error is not None:
                raise RuntimeError(root_error)
            comm.Barrier()

            _log_stage(comm, started, "same_lu_volume_absorption", "begin")
            corrected_volume = compute_volume_absorption_3d(
                view.mesh_data,
                view.config,
                corrected_recovered.field,
                tight_root / "volume",
                incident_power=incident_power_3d(view.config),
                port_metrics=corrected_port_metrics,
            )
            corrected_a_volume = corrected_volume.get("A_volume_total")
            if corrected_a_volume is None or not np.isfinite(float(corrected_a_volume)):
                raise ValueError("same-LU corrected A_volume_total is missing or non-finite")
            corrected_a_volume = float(corrected_a_volume)
            corrected_port_metrics["R_plus_T_plus_A_volume"] = float(
                corrected_port_metrics["R_total"]
                + corrected_port_metrics["T_total"]
                + corrected_a_volume
            )
            corrected_port_metrics["energy_closure_error_dtn_port_modal_volume"] = float(
                corrected_port_metrics["R_plus_T_plus_A_volume"] - 1.0
            )
            _log_stage(comm, started, "same_lu_volume_absorption", "end")

            write_error = None
            try:
                _write_port_outputs(
                    ports_root,
                    view.config,
                    list(modes),
                    corrected_auxiliary,
                    incident_projections,
                    corrected_port_metrics,
                    comm,
                )
            except Exception as exc:  # noqa: BLE001 - synchronize root-only output failures
                if comm.rank == 0:
                    write_error = f"{type(exc).__name__}: {exc}"
            write_error = comm.bcast(write_error, root=0)
            if write_error is not None:
                raise RuntimeError(f"same-LU modal output failed: {write_error}")

            _log_stage(comm, started, "same_lu_field_capture", "begin")
            corrected_fields = _field_capture(
                corrected_recovered.field,
                view.mesh_data,
                view.config,
                comm,
                None,
                "initial_180",
            )
            corrected_storage_arrays, corrected_storage_metadata = (
                _active_solution_storage(corrected_view)
            )
            _log_stage(comm, started, "same_lu_field_capture", "end")

            result = None
            result_error = None
            if comm.rank == 0:
                try:
                    original_port_path = (
                        run_root / "solve" / "dtn_port_diffraction_orders_3d.json"
                    )
                    corrected_port_path = (
                        ports_root / "dtn_port_diffraction_orders_3d.json"
                    )
                    with original_port_path.open(encoding="utf-8") as stream:
                        original_port = json.load(stream)
                    with corrected_port_path.open(encoding="utf-8") as stream:
                        corrected_port = json.load(stream)
                    modal_metrics = _tightening_modal_metrics(
                        original_port["orders"], corrected_port["orders"]
                    )
                    field_metrics = {
                        order: _tightening_field_metrics(
                            initial_sample,
                            corrected_fields["samples"][order],
                            view.config,
                        )
                        for order, initial_sample in initial_fields["samples"].items()
                    }
                    independent_gauge = independent_active_action[
                        "full_solver_gauge_residual"
                    ]
                    independent_a6 = float(
                        independent_gauge["relative_to_independent_rhs"]
                    )
                    condensed_relative = float(
                        condensed_residual["linear_system_relative_residual"]
                    )
                    reduced_relative = float(
                        corrected_reduced_residual["linear_system_relative_residual"]
                    )
                    corrected_closure = float(
                        corrected_port_metrics["energy_closure_error_dtn_port_modal_volume"]
                    )
                    quality_gates = {
                        "residual_correction_converged": bool(
                            int(correction["ksp_converged_reason"]) > 0
                        ),
                        "explicit_reduced_system_residual_le_1e-9": bool(
                            np.isfinite(reduced_relative) and reduced_relative <= 1.0e-9
                        ),
                        "condensed_full_active_residual_le_1e-9": bool(
                            np.isfinite(condensed_relative)
                            and condensed_relative <= 1.0e-9
                        ),
                        "independent_A6_relative_to_rhs_le_1e-6": bool(
                            bool(independent_gauge["finite"])
                            and np.isfinite(independent_a6)
                            and independent_a6 <= 1.0e-6
                        ),
                        "independent_A6_direct_target_le_1e-8": bool(
                            bool(independent_gauge["finite"])
                            and np.isfinite(independent_a6)
                            and independent_a6 <= 1.0e-8
                        ),
                        "A_volume_finite": bool(np.isfinite(corrected_a_volume)),
                        "energy_closure_abs_le_1e-5": bool(
                            np.isfinite(corrected_closure)
                            and abs(corrected_closure) <= 1.0e-5
                        ),
                    }
                    quality_gates["pass"] = all(
                        value is True for value in quality_gates.values()
                    )
                    samples_path = tight_root / "field_samples_q8_q10.npz"
                    _write_samples(
                        samples_path,
                        corrected_fields["samples"],
                        tuple(
                            np.asarray(corrected_fields["axes_nm"][axis], dtype=np.float64)
                            for axis in ("x", "y", "z")
                        ),
                    )
                    storage_path = tight_root / "recovered_solution_storage.npz"
                    np.savez_compressed(storage_path, **corrected_storage_arrays)
                    result = {
                        "classification": "same_matrix_rhs_and_factor_one_residual_correction_diagnostic",
                        "matrix_or_rhs_reassembled": False,
                        "ksp_operator_replaced": False,
                        "residual_correction": correction,
                        "explicit_reduced_system_residual": corrected_reduced_residual,
                        "condensed_active_residual": condensed_residual,
                        "independent_active_action": independent_active_action,
                        "corrected_port_metrics": {
                            name: corrected_port_metrics[name]
                            for name in (
                                "R_total", "T_total", "R00_s", "R00_p", "R00_total",
                                "R_plus_T_plus_A_volume",
                                "energy_closure_error_dtn_port_modal_volume",
                            )
                        },
                        "corrected_A_volume_total": corrected_a_volume,
                        "quality_gates": quality_gates,
                        "field_difference_from_initial_q8_q10": field_metrics,
                        "modal_difference_from_initial": modal_metrics,
                        "field_samples": {
                            "file": str(samples_path),
                            "sha256": _sha256_file(samples_path),
                            "rule_orders": [8, 10],
                            "point_counts": {
                                key: int(value["weights_nm3"].size)
                                for key, value in corrected_fields["samples"].items()
                            },
                        },
                        "recovered_solution_storage": {
                            "file": str(storage_path),
                            "sha256": _sha256_file(storage_path),
                            "arrays": {
                                name: _array_identity(values)
                                for name, values in corrected_storage_arrays.items()
                            },
                            **corrected_storage_metadata,
                        },
                        "port_outputs": {
                            "directory": str(ports_root),
                            "orders_sha256": _sha256_file(corrected_port_path),
                        },
                        "case_elapsed_at_completion_seconds": time.perf_counter() - started,
                    }
                except Exception as exc:  # noqa: BLE001 - broadcast root comparison failures collectively
                    result_error = f"{type(exc).__name__}: {exc}"
            result, result_error = comm.bcast((result, result_error), root=0)
            if result_error is not None:
                raise RuntimeError(f"same-LU postprocessing failed: {result_error}")
            _log_stage(comm, started, "same_lu_tightening", "end")
            return result
        finally:
            corrected_recovered.destroy()
    finally:
        corrected_x.destroy()


def _check_environment(comm: MPI.Intracomm) -> dict[str, Any]:
    local_error = None
    threads = {name: os.environ.get(name) for name in _THREAD_ENV}
    resource_gate = None
    try:
        if os.environ.get("_MYFENICS_NATIVE_QUALIFIED_ACTIVATION") != "1":
            raise RuntimeError("qualified native activation marker is missing")
        resource_gate = task43_watchdog_resource_gate_from_environment()
        if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
            raise RuntimeError(
                f"PETSc scalar type is not complex128: {PETSc.ScalarType}"
            )
        if np.dtype(PETSc.IntType) != np.dtype(np.int64):
            raise RuntimeError(f"PETSc integer type is not int64: {PETSc.IntType}")
        bad_threads = {
            name: value for name, value in threads.items() if value != "1"
        }
        if bad_threads:
            raise RuntimeError(f"math thread counts must all be 1: {bad_threads}")
    except (RuntimeError, TypeError, ValueError) as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    errors = comm.allgather(local_error)
    if any(error is not None for error in errors):
        raise RuntimeError(
            "qualified runtime preflight failed: "
            + "; ".join(
                f"rank {rank}: {error}"
                for rank, error in enumerate(errors)
                if error is not None
            )
        )
    resource_gates = comm.allgather(resource_gate)
    if any(gate != resource_gates[0] for gate in resource_gates[1:]):
        raise RuntimeError("MPI ranks have different Task43 watchdog resource gates")
    return {
        "python": sys.executable,
        "python_version": sys.version.split()[0],
        "qualified_activation_marker": True,
        "petsc_scalar_type": str(PETSc.ScalarType),
        "petsc_int_type": str(PETSc.IntType),
        "mpi_size": int(comm.size),
        "rank_affinity": comm.allgather(sorted(os.sched_getaffinity(0))),
        "math_threads": threads,
        "task43_watchdog_resource_gate": resource_gates[0],
    }


def _write_samples(
    path: Path,
    samples: dict[str, dict[str, np.ndarray]],
    axes: tuple[np.ndarray, ...],
) -> None:
    arrays: dict[str, np.ndarray] = {}
    arrays.update(
        {
            f"axis_{name}_nm": np.asarray(axis, dtype=np.float64)
            for name, axis in zip(("x", "y", "z"), axes, strict=True)
        }
    )
    for key, values in samples.items():
        for name, value in values.items():
            arrays[f"{key}_{name}"] = np.asarray(value)
    np.savez_compressed(path, **arrays)


def _run(
    case: str,
    run_root: Path,
    reference_run_root: Path | None,
    parallel_reference_run_root: Path | None,
    same_lu_tightening_enabled: bool = False,
    candidate_plan_path: Path | None = None,
    candidate_id: str | None = None,
    candidate_parent_run_root: Path | None = None,
    candidate_tightening_run_root: Path | None = None,
    candidate_marking_record: Path | None = None,
    candidate_acceptance_contract: Path | None = None,
    candidate_parent_selection_record: Path | None = None,
) -> dict[str, Any]:
    comm = MPI.COMM_WORLD
    started = time.perf_counter()
    expected_size, kind = _CASES[case]
    current_case = case == _CURRENT_CASE
    candidate_case = case == _ROUND1_CANDIDATE_CASE
    geometry_profile = "initial_180" if current_case or candidate_case else "h100"
    candidate_plan: dict[str, Any] | None = None
    candidate_plan_sha256: str | None = None
    candidate_identity: dict[str, Any] | None = None
    if int(comm.size) != expected_size:
        raise RuntimeError(f"case {case} requires MPI size {expected_size}, got {comm.size}")
    _log_stage(
        comm,
        started,
        "preflight",
        "begin",
        case_id=case,
        candidate_id=candidate_id if candidate_case else None,
    )
    environment = _check_environment(comm)
    root_contract = (
        str(run_root.resolve()),
        None if reference_run_root is None else str(reference_run_root.resolve()),
        None
        if parallel_reference_run_root is None
        else str(parallel_reference_run_root.resolve()),
        None if candidate_plan_path is None else str(candidate_plan_path.resolve()),
        candidate_id,
        None
        if candidate_parent_run_root is None
        else str(candidate_parent_run_root.resolve()),
        None
        if candidate_tightening_run_root is None
        else str(candidate_tightening_run_root.resolve()),
        None
        if candidate_marking_record is None
        else str(candidate_marking_record.resolve()),
        None
        if candidate_acceptance_contract is None
        else str(candidate_acceptance_contract.resolve()),
        None
        if candidate_parent_selection_record is None
        else str(candidate_parent_selection_record.resolve()),
    )
    root_contracts = comm.allgather(root_contract)
    if any(contract != root_contracts[0] for contract in root_contracts[1:]):
        raise RuntimeError("all MPI ranks must use identical run/reference roots")
    run_root = Path(root_contract[0])
    reference_run_root = (
        None if root_contract[1] is None else Path(root_contract[1])
    )
    parallel_reference_run_root = (
        None
        if root_contract[2] is None
        else Path(root_contract[2])
    )
    candidate_plan_path = None if root_contract[3] is None else Path(root_contract[3])
    candidate_id = root_contract[4]
    candidate_parent_run_root = (
        None if root_contract[5] is None else Path(root_contract[5])
    )
    candidate_tightening_run_root = (
        None if root_contract[6] is None else Path(root_contract[6])
    )
    candidate_marking_record = (
        None if root_contract[7] is None else Path(root_contract[7])
    )
    candidate_acceptance_contract = (
        None if root_contract[8] is None else Path(root_contract[8])
    )
    candidate_parent_selection_record = (
        None if root_contract[9] is None else Path(root_contract[9])
    )
    root_error = None
    if comm.rank == 0:
        try:
            if run_root.exists() and any(run_root.iterdir()):
                raise FileExistsError(
                    f"refusing to overwrite nonempty output root {run_root}"
                )
            run_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # synchronize a rank-zero filesystem error
            root_error = f"{type(exc).__name__}: {exc}"
    root_error = comm.bcast(root_error, root=0)
    if root_error is not None:
        raise RuntimeError(root_error)
    comm.Barrier()

    if candidate_case:
        if any(value is None for value in (candidate_plan_path, candidate_id, candidate_acceptance_contract)):
            raise ValueError("candidate case requires plan, ID and frozen acceptance contract")
        if candidate_parent_selection_record is None:
            if any(value is None for value in (candidate_parent_run_root, candidate_tightening_run_root, candidate_marking_record)):
                raise ValueError("round-one candidate case requires its frozen initial inputs")
            (
                candidate_plan,
                candidate_plan_sha256,
                candidate_identity,
            ) = _validate_round1_candidate_inputs(
                candidate_plan_path=candidate_plan_path,
                candidate_id=str(candidate_id),
                parent_run_root=candidate_parent_run_root,
                tightening_run_root=candidate_tightening_run_root,
                marking_record_path=candidate_marking_record,
                acceptance_contract_path=candidate_acceptance_contract,
            )
        else:
            (
                candidate_plan,
                candidate_plan_sha256,
                candidate_identity,
            ) = _validate_accepted_candidate_inputs(
                candidate_plan_path=candidate_plan_path,
                candidate_id=str(candidate_id),
                accepted_parent_selection_record=candidate_parent_selection_record,
                acceptance_contract_path=candidate_acceptance_contract,
            )
        candidate_plan_copy = run_root / "candidate_plan.json"
        copy_error = None
        if comm.rank == 0:
            try:
                shutil.copyfile(candidate_plan_path, candidate_plan_copy)
                if _sha256_file(candidate_plan_copy) != candidate_plan_sha256:
                    raise RuntimeError("copied candidate plan hash changed")
            except (OSError, RuntimeError) as exc:
                copy_error = f"{type(exc).__name__}: {exc}"
        copy_error = comm.bcast(copy_error, root=0)
        if copy_error is not None:
            raise RuntimeError(copy_error)
        comm.Barrier()
        candidate_identity["run_plan_path"] = str(candidate_plan_copy)
        candidate_identity["adaptive_round_id"] = str(candidate_id).split("_", 1)[0]

    reference_identities: dict[str, Any] = {}
    references = []
    if reference_run_root is not None:
        references.append(("native_p3_mpi1", reference_run_root))
    if parallel_reference_run_root is not None:
        references.append(("empty_h_active_p3_mpi1", parallel_reference_run_root))
    for expected_reference, reference_path in references:
        identity = None
        validation_error = None
        if comm.rank == 0:
            try:
                identity = _validate_reference_run(
                    reference_path,
                    expected_case_id=expected_reference,
                )
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                validation_error = f"{type(exc).__name__}: {exc}"
        identity, validation_error = comm.bcast(
            (identity, validation_error), root=0
        )
        if validation_error is not None:
            raise RuntimeError(
                f"invalid {expected_reference} reference: {validation_error}"
            )
        reference_identities[expected_reference] = identity
    _log_stage(
        comm,
        started,
        "preflight",
        "end",
        validated_references=sorted(reference_identities),
    )

    source_identity = None
    source_error = None
    if comm.rank == 0:
        try:
            repository = Path(__file__).resolve().parents[2]
            source_hashes = {
                name: _sha256_file(repository / name) for name in _SOURCE_FILES
            }
            source_identity = {
                "git_head": subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=repository,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                "file_sha256": source_hashes,
            }
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
            source_error = f"{type(exc).__name__}: {exc}"
    source_identity, source_error = comm.bcast((source_identity, source_error), root=0)
    if source_error is not None:
        raise RuntimeError(f"could not capture run source snapshot: {source_error}")
    source_hashes_before = source_identity["file_sha256"]

    cfg = _h100_config(
        kind=kind,
        case_name=(
            f"task43_initial180_{case}"
            if current_case
            else (
                f"task43_{candidate_id}"
                if candidate_case
                else f"task43_h100_{case}"
            )
        ),
        geometry_profile=geometry_profile,
    )
    _log_stage(comm, started, "mesh_build", "begin")
    mesh_data = build_airbox_mesh_3d(cfg, run_root / "resolved_mesh")
    axes = _mesh_axes(mesh_data.mesh, comm)
    _assert_mesh_profile(mesh_data, axes, geometry_profile)
    reference_axes = None
    if reference_run_root is not None:
        with np.load(
            reference_run_root / "field_samples_q8_q10.npz", allow_pickle=False
        ) as native_reference:
            reference_axes = tuple(
                np.asarray(native_reference[f"axis_{name}_nm"], dtype=np.float64)
                for name in ("x", "y", "z")
            )
    local_h_plan_identity = None
    if kind == "empty_h_active_p3":
        if candidate_case:
            assert candidate_plan is not None
            assert candidate_plan_sha256 is not None
            plan = candidate_plan
            plan_path = run_root / "candidate_plan.json"
        else:
            boxes = cell_box_catalog(mesh_data.mesh)
            plan = stage4_local_h_refinement_plan_payload(
                cfg,
                (),
                comm_size=comm.size,
                trace_degree=3,
                cell_interior_degree=6,
                provenance={
                    "purpose": (
                        "Task43 frozen initial-mesh active-p3 current"
                        if current_case
                        else "Task43 empty-h active-p3 same-mesh anchor"
                    ),
                    "mesh_role": (
                        "frozen interface-fitted 180-cell 3x10x6 Task43 start"
                        if current_case
                        else "resolved boundary-fitted h100 36-cell geometry"
                    ),
                    "active_degree": 3,
                    "formal_candidate": False,
                },
                cell_interior_degree_overrides={box: 3 for box in boxes},
                variable_trace_from_cell_degrees=True,
                allow_no_refinement=True,
            )
            expected_leaf_count = int(
                mesh_data.mesh.topology.index_map(mesh_data.mesh.topology.dim).size_global
            )
            if plan["expected_forest"]["leaf_cell_count"] != expected_leaf_count:
                raise RuntimeError("empty-h active plan changed the resolved cell set")
            plan_path = run_root / "empty_h_active_p3_plan.json"
            plan_error = None
            if comm.rank == 0:
                try:
                    plan_path.write_text(
                        json.dumps(plan, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                except OSError as exc:
                    plan_error = f"{type(exc).__name__}: {exc}"
            plan_error = comm.bcast(plan_error, root=0)
            if plan_error is not None:
                raise RuntimeError(plan_error)
            comm.Barrier()
        cfg.stage4_local_h_refinement_plan = str(plan_path)
        mesh_data = build_stage4_local_h_mesh_data(
            cfg,
            plan_path,
            comm=comm,
        )
        axes = _mesh_axes(mesh_data.mesh, comm)
        mesh_audit_profile = (
            "candidate_initial180" if candidate_case else geometry_profile
        )
        actual_mesh_identity = _assert_mesh_profile(
            mesh_data,
            axes,
            mesh_audit_profile,
            candidate_plan=plan if candidate_case else None,
            candidate_plan_sha256=candidate_plan_sha256,
        )
        actual_degree_counts = dict(
            mesh_data.local_h_context.audit["cell_interior_degree_counts"]
        )
        local_h_context_audit = mesh_data.local_h_context.audit
        local_h_plan_identity = {
            "plan_sha256": _sha256_file(plan_path),
            "candidate_id": candidate_id if candidate_case else None,
            "action": plan.get("task43_candidate", {}).get("action"),
            "root_cell_count": int(local_h_context_audit["root_cell_count"]),
            "leaf_cell_count": int(local_h_context_audit["leaf_cell_count"]),
            "marked_root_count": len(plan["marked_root_boxes"]),
            "cell_interior_degree_counts": actual_degree_counts,
            "leaf_catalog_sha256": actual_mesh_identity.get(
                "leaf_catalog_sha256"
            ),
            "root_catalog_sha256": actual_mesh_identity.get(
                "root_catalog_sha256"
            ),
            "closure_split_counts": actual_mesh_identity.get(
                "closure_split_counts"
            ),
            "hanging_patch_count": actual_mesh_identity.get(
                "hanging_patch_count"
            ),
            "trace_degree": int(plan["trace_degree"]),
            "cell_interior_degree": int(plan["cell_interior_degree"]),
            "variable_trace_from_cell_degrees": bool(
                plan["variable_trace_from_cell_degrees"]
            ),
            "allow_no_refinement": bool(plan.get("allow_no_refinement", False)),
        }
    if current_case:
        mesh_data.mesh.topology.create_connectivity(mesh_data.mesh.topology.dim, 0)
    if candidate_case:
        mesh_data.mesh.topology.create_connectivity(mesh_data.mesh.topology.dim, 0)
    _log_stage(
        comm,
        started,
        "mesh_build",
        "end",
        global_cells=int(mesh_data.mesh.topology.index_map(mesh_data.mesh.topology.dim).size_global),
        axis_cell_counts_xyz=[len(axis) - 1 for axis in axes],
        local_h_allow_no_refinement=(
            None
            if local_h_plan_identity is None
            else bool(local_h_plan_identity["allow_no_refinement"])
        ),
        base_geometry_profile=geometry_profile,
        actual_mesh_profile=(
            "candidate_local_h_from_initial180"
            if candidate_case
            else geometry_profile
        ),
    )

    backend_audit = resolve_stage4_full3d_assembly_backend(cfg, apply=False)
    expected_backend = (
        STANDARD_FULL_ASSEMBLY_BACKEND
        if kind == "native_p3"
        else ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
    )
    if backend_audit["actual"] != expected_backend:
        raise RuntimeError(f"unexpected assembly backend: {backend_audit}")

    captured: dict[str, Any] = {}

    def capture(field, live_mesh_data, live_cfg, goal_context) -> None:
        field_mesh_profile = (
            "candidate_initial180" if candidate_case else geometry_profile
        )
        captured["fields"] = _field_capture(
            field,
            live_mesh_data,
            live_cfg,
            comm,
            reference_axes,
            field_mesh_profile,
            candidate_plan=candidate_plan if candidate_case else None,
            candidate_plan_sha256=(
                candidate_plan_sha256 if candidate_case else None
            ),
            sample_fields=not candidate_case,
        )
        modes = goal_context["modes"]
        captured["mode_count"] = len(modes)
        captured["ordered_mode_keys"] = [
            [str(mode.side), int(mode.m), int(mode.n), str(mode.polarization)]
            for mode in modes
        ]
        if current_case or candidate_case:
            captured["resolved_profile_identity"] = task43_profile_identity(
                live_cfg,
                modes,
                resolved_axes_nm=captured["fields"]["axes_nm"],
                resolved_mesh_audit={
                    "global_cell_count": int(
                        captured["fields"]["mesh_identity"]["global_cells"]
                    ),
                    "leaf_cell_count": int(
                        captured["fields"]["mesh_identity"]["global_cells"]
                    ),
                },
            )

    def native_observer(**kwargs) -> None:
        capture(
            kwargs["field"],
            kwargs["mesh_data"],
            kwargs["config"],
            kwargs["dtn_result"]["goal_context"],
        )
        captured["native_explicit_residual"] = _native_explicit_residual(
            kwargs["linear_system"]
        )
        captured["port_metrics"] = kwargs["dtn_result"]["port_metrics"]

    def active_observer(view) -> None:
        if current_case or candidate_case:
            if comm.size == 1:
                _log_stage(comm, started, "pre_validation_checkpoint", "begin")
                storage_arrays, storage_metadata = _active_solution_storage(view)
                modes = view.goal_context["modes"]
                ordered_mode_keys = [
                    [
                        str(mode.side),
                        int(mode.m),
                        int(mode.n),
                        str(mode.polarization),
                    ]
                    for mode in modes
                ]
                resolved_axes = {
                    name: axis.tolist()
                    for name, axis in zip(("x", "y", "z"), axes, strict=True)
                }
                resolved_mesh_audit = {
                    "global_cell_count": int(local_h_plan_identity["leaf_cell_count"]),
                    "leaf_cell_count": int(local_h_plan_identity["leaf_cell_count"]),
                }
                checkpoint_profile_identity = task43_profile_identity(
                    view.config,
                    modes,
                    resolved_axes_nm=resolved_axes,
                    resolved_mesh_audit=resolved_mesh_audit,
                )
                checkpoint_identity = {
                    "case_id": case,
                    "candidate_id": candidate_id if candidate_case else None,
                    "candidate_action": (
                        None
                        if not candidate_case
                        else candidate_identity.get("action")
                    ),
                    "candidate_plan_sha256": candidate_plan_sha256,
                    "accepted_parent_selection_sha256": (
                        None
                        if not candidate_case
                        else candidate_identity.get(
                            "accepted_parent_selection_sha256"
                        )
                    ),
                    "mpi_size": int(comm.size),
                    "source_identity": source_identity,
                    "resolved_profile_identity": checkpoint_profile_identity,
                    "resolved_axes_nm": resolved_axes,
                    "local_h_plan_identity": local_h_plan_identity,
                    "ordered_mode_count": len(ordered_mode_keys),
                    "ordered_mode_keys_sha256": _sha256_json(ordered_mode_keys),
                    "active_degree_plan_sha256": storage_metadata[
                        "active_degree_plan_sha256"
                    ],
                    "mesh_and_dof_order_sha256": storage_metadata[
                        "mesh_and_dof_order_sha256"
                    ],
                }
                checkpoint_path = run_root / "pre_validation_checkpoint.npz"
                captured["pre_validation_checkpoint"] = (
                    write_pre_validation_checkpoint(
                        checkpoint_path,
                        storage_arrays,
                        identity=checkpoint_identity,
                    )
                )
                captured["solution_storage_arrays"] = storage_arrays
                captured["solution_storage_metadata"] = storage_metadata
                _log_stage(
                    comm,
                    started,
                    "pre_validation_checkpoint",
                    "end",
                    npz_sha256=captured["pre_validation_checkpoint"][
                        "npz_sha256"
                    ],
                    official_result=False,
                )
            else:
                captured["pre_validation_checkpoint"] = {
                    "status": "not_written_mpi_size_not_one",
                    "classification": "diagnostic_checkpoint_is_serial_only",
                    "official_result": False,
                    "mpi_size": int(comm.size),
                }
        capture(view.field, view.mesh_data, view.config, view.goal_context)
        captured["distinct_physical_trace_degrees"] = sorted(
            {
                int(value)
                for value in view.reduction.degree_plan.audit[
                    "trace_degree_values"
                ]
            }
        )
        captured["independent_active_action"] = (
            compute_stage4_independent_active_action(view)
        )
        captured["condensed_residual"] = dict(view.full_active_residual)
        captured["port_metrics"] = dict(view.port_metrics)
        audit = view.mesh_data.local_h_context.audit
        captured["local_h_audit"] = {
            key: audit[key]
            for key in (
                "status",
                "pass",
                "root_cell_count",
                "leaf_cell_count",
                "hanging_patch_count",
                "cell_interior_degree_counts",
                "variable_trace_from_cell_degrees",
                "allow_no_refinement",
            )
        }
        captured["local_h_audit"]["closure_split_counts"] = dict(
            audit["forest"]["closure_split_counts"]
        )
        if (current_case or candidate_case) and same_lu_tightening_enabled:
            captured["same_lu_tightening"] = _same_lu_tightening(
                view,
                run_root=run_root,
                comm=comm,
                started=started,
                initial_fields=captured["fields"],
            )

    _log_stage(comm, started, "solve_and_observe", "begin")
    summary = run_stage4b_block_grating_3d_case(
        cfg,
        run_root / "solve",
        solution_observer=(native_observer if kind == "native_p3" else None),
        variable_p_live_observer=(
            active_observer if kind == "empty_h_active_p3" else None
        ),
        mesh_data_override=mesh_data,
    )
    _log_stage(comm, started, "solve_and_observe", "end")
    source_paths = {
        name: Path(__file__).resolve().parents[2] / name for name in _SOURCE_FILES
    }
    source_hashes_after = {
        name: _sha256_file(path) for name, path in source_paths.items()
    }
    if source_hashes_before != source_hashes_after:
        raise RuntimeError("a source file changed while the PDE case was running")
    if int(captured.get("mode_count", -1)) != 612:
        raise RuntimeError(f"resolved R13 inventory is not 612 modes: {captured.get('mode_count')}")
    _log_stage(comm, started, "record_and_compare", "begin")
    post_error = None
    task43_gated_official_result = None
    if comm.rank == 0:
        record_path = run_root / (
            "task43_initial180_current_record.json"
            if current_case
            else (
                "task43_round1_candidate_record.json"
                if candidate_case
                else "task43_h100_anchor_record.json"
            )
        )
        try:
            orders_path = run_root / "solve" / "dtn_port_diffraction_orders_3d.json"
            with orders_path.open(encoding="utf-8") as stream:
                port_payload = json.load(stream)
            rows = port_payload["orders"]
            if len(rows) != 612:
                raise RuntimeError(
                    f"serialized channel output has {len(rows)} rows, expected 612"
                )
            serialized_mode_keys = [
                [row["side"], int(row["m"]), int(row["n"]), row["polarization"]]
                for row in rows
            ]
            if serialized_mode_keys != captured["ordered_mode_keys"]:
                raise RuntimeError(
                    "serialized channels differ from actual ordered mode inventory"
                )
            fields = captured["fields"]
            samples_path = None
            if not candidate_case:
                samples_path = run_root / "field_samples_q8_q10.npz"
                _write_samples(samples_path, fields["samples"], axes)
            storage_record = None
            if current_case or candidate_case:
                storage_arrays = captured.get("solution_storage_arrays")
                storage_metadata = captured.get("solution_storage_metadata")
                if not isinstance(storage_arrays, dict) or not isinstance(
                    storage_metadata, dict
                ):
                    raise RuntimeError("current case did not capture recovered coefficients")
                storage_path = run_root / (
                    "recovered_solution_storage.npz"
                    if current_case
                    else "candidate_recovered_solution_storage.npz"
                )
                np.savez_compressed(storage_path, **storage_arrays)
                storage_record = {
                    "file": str(storage_path),
                    "sha256": _sha256_file(storage_path),
                    "arrays": {
                        name: _array_identity(values)
                        for name, values in storage_arrays.items()
                    },
                    **storage_metadata,
                }
            a_volume_value = summary.get("A_volume_total")
            if a_volume_value is None or not np.isfinite(float(a_volume_value)):
                raise ValueError("official A_volume_total is missing or non-finite")
            a_volume = float(a_volume_value)

            gates: dict[str, Any] = {
                ("solver_completed" if current_case or candidate_case else "solver_completed_and_official"): bool(
                    summary.get("case_status") == "completed"
                    and (
                        current_case
                        or candidate_case
                        or summary.get("official_result") is True
                    )
                ),
                "all_612_ordered_modes_present": len(rows) == 612,
            }
            small_direct_target_diagnostic = None
            if kind == "native_p3":
                residual = captured["native_explicit_residual"]
                gates["native_explicit_Ax_minus_b_relative_le_1e-9"] = bool(
                    np.isfinite(residual["relative_to_rhs"])
                    and residual["relative_to_rhs"] <= 1.0e-9
                )
            else:
                independent = captured["independent_active_action"][
                    "full_solver_gauge_residual"
                ]
                condensed = captured["condensed_residual"]
                a6_relative = independent["relative_to_independent_rhs"]
                if current_case or candidate_case:
                    gates["independent_A6_relative_to_rhs_le_1e-6"] = bool(
                        independent["finite"]
                        and np.isfinite(a6_relative)
                        and a6_relative <= 1.0e-6
                    )
                    small_direct_target_diagnostic = {
                        "relative_to_independent_rhs": (
                            float(a6_relative) if np.isfinite(a6_relative) else None
                        ),
                        "limit": 1.0e-8,
                        "passed": bool(
                            independent["finite"]
                            and np.isfinite(a6_relative)
                            and a6_relative <= 1.0e-8
                        ),
                        "classification": "diagnostic_only_not_hard_gate",
                    }
                else:
                    gates["independent_A6_relative_to_rhs_le_1e-9"] = bool(
                        independent["finite"]
                        and np.isfinite(a6_relative)
                        and a6_relative <= 1.0e-9
                    )
                gates["condensed_active_residual_le_1e-9"] = bool(
                    np.isfinite(condensed["linear_system_relative_residual"])
                    and condensed["linear_system_relative_residual"] <= 1.0e-9
                )
                if candidate_case:
                    storage_metadata = captured.get("solution_storage_metadata", {})
                    local_h_audit = captured.get("local_h_audit", {})
                    gates["local_h_closure_pass"] = bool(
                        local_h_audit.get("pass") is True
                    )
                    gates["variable_p_degree_plan_pass"] = bool(
                        storage_metadata.get("degree_plan_pass") is True
                    )
                    gates["trace_constraint_closure_pass"] = bool(
                        storage_metadata.get("trace_constraints_pass") is True
                    )
                    gates["active_fe_dof_resource_gate_pass"] = bool(
                        storage_metadata.get("active_fe_dof_gate_pass") is True
                    )
            if current_case or candidate_case:
                closure = abs(
                    float(port_payload["metrics"]["R_total"])
                    + float(port_payload["metrics"]["T_total"])
                    + a_volume
                    - 1.0
                )
                gates["finite_A_volume_total"] = bool(np.isfinite(a_volume))
                gates["energy_closure_abs_le_1e-5"] = bool(
                    np.isfinite(closure) and closure <= 1.0e-5
                )

            comparisons: dict[str, Any] = {}
            if reference_run_root is not None:
                native_comparison = _compare_against_reference(
                    current_rows=rows,
                    current_port_metrics=port_payload["metrics"],
                    current_a_volume=a_volume,
                    current_field_samples=fields["samples"],
                    reference_run_root=reference_run_root,
                    cfg=cfg,
                )
                comparisons["native_p3_mpi1"] = native_comparison
                gates.update(
                    {
                        f"native_p3_{key}": value
                        for key, value in native_comparison["gates"].items()
                    }
                )
            if parallel_reference_run_root is not None:
                parallel_comparison = _compare_against_reference(
                    current_rows=rows,
                    current_port_metrics=port_payload["metrics"],
                    current_a_volume=a_volume,
                    current_field_samples=fields["samples"],
                    reference_run_root=parallel_reference_run_root,
                    cfg=cfg,
                )
                comparisons["empty_h_active_p3_mpi1"] = parallel_comparison
                gates.update(
                    {
                        f"active_mpi1_{key}": value
                        for key, value in parallel_comparison["gates"].items()
                    }
                )

            gates["pass"] = all(value is True for value in gates.values())
            gates["status"] = "passed" if gates["pass"] else "failed"
            task43_gated_official_result = bool(
                (current_case or candidate_case)
                and gates["pass"]
                and summary.get("case_status") == "completed"
            )
            storage_metadata = captured.get("solution_storage_metadata")
            active_space_summary = None
            if isinstance(storage_metadata, dict):
                active_space_summary = {
                    key: storage_metadata.get(key)
                    for key in (
                        "active_cell_degree_counts",
                        "active_trace_rows",
                        "active_cell_interior_rows",
                        "independent_trace_rows",
                        "independent_active_fe_dofs",
                        "active_fe_dof_gate_policy",
                        "active_fe_dof_gate_limit",
                        "active_fe_dof_gate_pass",
                        "degree_plan_pass",
                        "trace_constraints_pass",
                        "trace_constraints_status",
                    )
                }
            local_h_plan_record = None
            if local_h_plan_identity is not None:
                local_h_plan_record = dict(local_h_plan_identity)
                local_h_plan_record[
                    "distinct_physical_trace_degrees"
                ] = captured.get("distinct_physical_trace_degrees")
            record = {
                "schema": (
                    "task43.initial_180_cell_active_p3_current.v1"
                    if current_case
                    else (
                        "task43.round1_candidate_solve.v1"
                        if candidate_case
                        else "task43.h100_same_mesh_p3_anchor.v1"
                    )
                ),
                "classification": (
                    "G2_frozen_initial_180_cell_current_numerical_result_not_accuracy_qualified"
                    if current_case
                    else (
                        "G2_adaptive_candidate_numerically_gated_pending_common_comparison_and_acceptance"
                        if candidate_case
                        else "G1_same_mesh_component_anchor_not_adaptive_accuracy_claim"
                    )
                ),
                "case_id": case,
                "method": (
                    "native degree-3 Nedelec, standard_full backend"
                    if kind == "native_p3"
                    else (
                        str(candidate_plan["task43_candidate"]["action_description"])
                        if candidate_case
                        else "empty-h p3 active space on p6 carrier, variable-p backend"
                    )
                ),
                "candidate_identity": candidate_identity,
                "selection_status": (
                    "pending_common_q8_comparison_and_decision_under_frozen_contract"
                    if candidate_case
                    else None
                ),
                "environment": environment,
                "resolved_config": cfg.as_jsonable(),
                "numerical_controls": {
                    "assembly_backend": backend_audit,
                    "nedelec_degree": int(cfg.nedelec_degree),
                    "volume_quadrature_degree": int(
                        cfg.stage4_volume_quadrature_degree
                    ),
                    "volume_quadrature_rule": str(
                        cfg.stage4_volume_quadrature_rule
                    ),
                    "incident_and_port_quadrature_degree": int(
                        cfg.stage4_dtn_quadrature_degree
                    ),
                    "sparse_cutoff_policy": str(
                        cfg.stage4_dtn_sparse_cutoff_policy
                    ),
                    "sparse_cutoff_relative_tolerance": float(
                        cfg.stage4_dtn_sparse_cutoff_relative_tolerance
                    ),
                    "port_amplitude_scale_policy": str(
                        cfg.stage4_port_boundary_amplitude_scale_policy
                    ),
                    "mesh": fields["mesh_identity"],
                    (
                        "candidate_local_h_plan"
                        if candidate_case
                        else "local_h_empty_plan"
                    ): local_h_plan_record,
                    "local_h_actual_audit": captured.get("local_h_audit"),
                    "ordered_mode_count": len(rows),
                    "ordered_mode_keys_sha256": _sha256_json(
                        captured["ordered_mode_keys"]
                    ),
                    "field_export": fields["representation"],
                    "resolved_task43_profile_identity": captured.get(
                        "resolved_profile_identity"
                    ),
                    "active_space": active_space_summary,
                },
                "solver": {
                    "case_status": summary.get("case_status"),
                    "official_result": (
                        task43_gated_official_result
                        if current_case or candidate_case
                        else summary.get("official_result")
                    ),
                    "official_result_scope": (
                        "Task43 gated result requiring independent A6, condensed residual, "
                        "energy closure, complete modes and solver completion"
                        if current_case or candidate_case
                        else "legacy component-anchor solver result"
                    ),
                    "legacy_solver_reported_official_result": summary.get(
                        "official_result"
                    ),
                    "legacy_solver_result_is_diagnostic_only_if_task_gates_fail": (
                        bool((current_case or candidate_case) and not gates["pass"])
                    ),
                    "timings_seconds": summary.get("timings_seconds"),
                    "wall_seconds_through_record": time.perf_counter() - started,
                    "explicit_native_residual": captured.get(
                        "native_explicit_residual"
                    ),
                    "condensed_residual": captured.get("condensed_residual"),
                    "independent_active_action": captured.get(
                        "independent_active_action"
                    ),
                    "small_direct_target_diagnostic": small_direct_target_diagnostic,
                },
                "power": {
                    "aggregate": port_payload["metrics"],
                    "A_volume_total": a_volume,
                    "channel_rows_file": str(orders_path),
                    "channel_rows_sha256": _sha256_file(orders_path),
                    "ordered_boundary_amplitudes_sha256": _sha256_json(
                        [row["outgoing_amplitude_at_boundary"] for row in rows]
                    ),
                    "ordered_channel_power_sha256": _sha256_json(
                        [float(row["power_ratio"]) for row in rows]
                    ),
                },
                "field_samples": (
                    {
                        "status": "not_run_candidate_uses_frozen_common_comparison_rule",
                        "rule_orders": [],
                        "physical_H_from_recovered_curl": True,
                        "scattered_background": "analytic_flat_air_substrate_fresnel",
                        "phase_fit": False,
                    }
                    if candidate_case
                    else {
                        "file": str(samples_path),
                        "sha256": _sha256_file(samples_path),
                        "rule_orders": [8, 10],
                        "point_counts": {
                            key: int(values["weights_nm3"].size)
                            for key, values in fields["samples"].items()
                        },
                        "physical_H_from_recovered_curl": True,
                        "scattered_background": "analytic_flat_air_substrate_fresnel",
                        "phase_fit": False,
                    }
                ),
                "recovered_solution_storage": storage_record,
                "pre_validation_checkpoint": captured.get(
                    "pre_validation_checkpoint"
                ),
                "reference_identities": reference_identities,
                "reference_comparison": {
                    "status": "not_run" if not comparisons else "measured",
                    "comparisons": comparisons,
                },
                "same_lu_tightening": captured.get("same_lu_tightening"),
                "gates": gates,
                "source_identity": source_identity,
                "not_run": (
                    [
                        "vertical sidewall one-sided mathematical traces",
                        "candidate common-rule comparison and frozen-contract decision",
                        "R14 port truncation comparison",
                        "independent Y5_1 holdout qualification; final 6x10x6 p6 comparison is excluded from selection",
                    ]
                    if candidate_case
                    else [
                        "vertical sidewall one-sided mathematical traces",
                        "adaptive selection or accepted h/p updates",
                        "R14 port truncation comparison",
                        "reference qualification and frozen marking/acceptance uncertainty",
                    ]
                ),
            }
            record_path.write_text(
                json.dumps(record, indent=2, sort_keys=True, default=_json_default)
                + "\n",
                encoding="utf-8",
            )
            if not gates["pass"]:
                post_error = f"Task43 case gates failed; see {record_path}"
            _log_stage(
                comm,
                started,
                "record_and_compare",
                gates["status"],
                record_path=str(record_path),
            )
        except Exception as exc:  # noqa: BLE001 - broadcast rank-zero postsolve failures
            post_error = f"{type(exc).__name__}: {exc}"
            try:
                (run_root / "task43_h100_anchor_postprocess_failure.json").write_text(
                    json.dumps(
                        {
                            "case_id": case,
                            "classification": "postsolve_record_or_comparison_failure",
                            "error": post_error,
                            "elapsed_wall_seconds": time.perf_counter() - started,
                            "source_identity": source_identity,
                        },
                        indent=2,
                        sort_keys=True,
                        default=_json_default,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            except OSError:
                pass
    if current_case or candidate_case:
        task43_gated_official_result = comm.bcast(
            task43_gated_official_result, root=0
        )
        summary = dict(summary)
        summary["legacy_solver_reported_official_result"] = summary.get(
            "official_result"
        )
        summary["official_result"] = task43_gated_official_result
    post_error = comm.bcast(post_error, root=0)
    if post_error is not None:
        _log_stage(
            comm,
            started,
            "record_and_compare",
            "failed",
            error=post_error,
        )
        raise RuntimeError(post_error)
    _log_stage(
        comm,
        started,
        "case_complete",
        "end",
        total_wall_seconds=time.perf_counter() - started,
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=tuple(_CASES), required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--reference-run-root", type=Path)
    parser.add_argument("--parallel-reference-run-root", type=Path)
    parser.add_argument("--candidate-plan", type=Path)
    parser.add_argument("--candidate-id")
    parser.add_argument("--candidate-parent-run-root", type=Path)
    parser.add_argument("--candidate-tightening-run-root", type=Path)
    parser.add_argument("--candidate-marking-record", type=Path)
    parser.add_argument("--candidate-acceptance-contract", type=Path)
    parser.add_argument("--candidate-parent-selection-record", type=Path)
    parser.add_argument(
        "--same-lu-tightening",
        action="store_true",
        help=(
            "for the frozen 180-cell current only, perform one residual correction "
            "with the already configured KSP and save a diagnostic field/modal comparison"
        ),
    )
    args = parser.parse_args(argv)
    comm = MPI.COMM_WORLD
    expected_size, kind = _CASES[args.case]
    is_current = args.case == _CURRENT_CASE
    is_candidate = args.case == _ROUND1_CANDIDATE_CASE
    is_native = kind == "native_p3"
    is_mpi2 = args.case == "empty_h_active_p3_mpi2"
    if args.same_lu_tightening and not is_current:
        parser.error("--same-lu-tightening is only valid for the frozen current case")
    if is_native and (
        args.reference_run_root is not None
        or args.parallel_reference_run_root is not None
    ):
        parser.error("native p3 is the common reference and takes no reference path")
    if not is_native and not is_current and not is_candidate and args.reference_run_root is None:
        parser.error("empty-h active p3 requires --reference-run-root from native_p3_mpi1")
    if is_current and (
        args.reference_run_root is not None
        or args.parallel_reference_run_root is not None
    ):
        parser.error("the frozen 180-cell current does not use a reference for selection")
    if is_mpi2 and args.parallel_reference_run_root is None:
        parser.error(
            "MPI2 active p3 requires --parallel-reference-run-root from empty_h_active_p3_mpi1"
        )
    if not is_mpi2 and args.parallel_reference_run_root is not None:
        parser.error("--parallel-reference-run-root is only used by the MPI2 active case")
    candidate_core_arguments = (
        args.candidate_plan,
        args.candidate_id,
        args.candidate_acceptance_contract,
    )
    round1_candidate_arguments = (
        args.candidate_parent_run_root,
        args.candidate_tightening_run_root,
        args.candidate_marking_record,
    )
    if is_candidate and any(value is None for value in candidate_core_arguments):
        parser.error(
            "candidate case requires --candidate-plan, --candidate-id and "
            "--candidate-acceptance-contract"
        )
    if is_candidate and args.candidate_parent_selection_record is None and any(
        value is None for value in round1_candidate_arguments
    ):
        parser.error("round-one candidate requires the initial parent/tightening/marking inputs")
    if is_candidate and args.candidate_parent_selection_record is not None and any(
        value is not None for value in round1_candidate_arguments
    ):
        parser.error("accepted-parent candidates do not take round-one initial inputs")
    all_candidate_arguments = (
        *candidate_core_arguments,
        *round1_candidate_arguments,
        args.candidate_parent_selection_record,
    )
    if not is_candidate and any(value is not None for value in all_candidate_arguments):
        parser.error("candidate inputs are only valid for round1_candidate_mpi1")
    if comm.size != expected_size:
        parser.error(f"--case {args.case} requires MPI size {expected_size}")
    summary = _run(
        args.case,
        args.run_root,
        args.reference_run_root,
        args.parallel_reference_run_root,
        same_lu_tightening_enabled=args.same_lu_tightening,
        candidate_plan_path=args.candidate_plan,
        candidate_id=args.candidate_id,
        candidate_parent_run_root=args.candidate_parent_run_root,
        candidate_tightening_run_root=args.candidate_tightening_run_root,
        candidate_marking_record=args.candidate_marking_record,
        candidate_acceptance_contract=args.candidate_acceptance_contract,
        candidate_parent_selection_record=args.candidate_parent_selection_record,
    )
    if comm.rank == 0:
        print(
            json.dumps(
                {
                    "case_id": args.case,
                    "candidate_id": args.candidate_id,
                    "case_status": summary.get("case_status"),
                    "official_result": summary.get("official_result"),
                    "legacy_solver_reported_official_result": summary.get(
                        "legacy_solver_reported_official_result"
                    ),
                    "run_root": str(args.run_root.resolve()),
                },
                sort_keys=True,
            ),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
