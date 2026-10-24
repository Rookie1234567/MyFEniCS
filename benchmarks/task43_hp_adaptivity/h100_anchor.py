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
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.task43_hp_adaptivity.candidate_checkpoints import (
    task43_v3_partial_terminal_record,
    write_atomic_json,
    write_atomic_npz,
    write_pre_validation_checkpoint,
    write_v3_primary_before_extra_packet,
    write_v3_primary_field_sample,
)
from benchmarks.task43_hp_adaptivity.candidate_records import (
    load_accepted_parent_artifacts,
)
from benchmarks.task43_hp_adaptivity.compare_v2_endpoints import (
    R13_MODE_KEYS,
    R14_MODE_KEYS,
    compare_field_sample_bundles,
    compare_r13_modal_outputs,
    compare_r13_r14_modal_outputs,
    task43_v2_physical_configuration_identity,
)
from benchmarks.task43_hp_adaptivity.compare_v2_endpoints import (
    _validated_rows as _v2_validated_rows,
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
from src.runners.physical_intermediate import WorkflowLedger
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
_V2_CONTRACT_SHA256 = "33a5d94ea8c61a26fb1d55c6268709fd283acc549beaeba429833aa68f5055cc"
_V2_PLAN_MARKDOWN_SHA256 = "864330a9a8d7efeeb1e9e48c73cf48331a9a4963a1bcea1ae061c00c769b455e"
_V3_CONTRACT_REL = Path(
    "docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v3_contract.json"
)
_V3_PLAN_REL = Path("docs/task43_hp_adaptivity/diagnostic_plan_v3.md")
_V3_CONTRACT_SHA256: str | None = "b694a975dee21d8347d77b3c247edda313422c9f2f6c5c605f8bcb52161e3898"
_V3_PLAN_SHA256: str | None = "b162512ed484ae30b88555b83afe0ad0ac669014e18cf1f1114f24c02bdb1db7"
_V2_LEGACY_R10_RECORD_SHA256 = "29b6a568956de31482688a8433021f779b616ab90a01660f63d53e4a5be2300d"
_V2_LEGACY_R10_SAMPLE_SHA256 = "d21d9977f518050ac53c675539df5010d12b6126687ac84b01c0f71b2f9b0a71"
_V2_R10_PLAN_SHA256 = "7e8305e0d6117ceeb37e88eb715d98ab5212505a2410161f0b38aff5c7ed1826"
_V2_R10_RECORD_SHA256 = "66d56c0644b5c8eb66d075a7898cdfa28024e3cc30834a08cd3d8b76e453968d"
_V2_R10_ROWS_SHA256 = "f7048a9ecad65db39faa688d9d4f0041099f2719e64e5ea2898e3dc793003450"
_V2_R10_STORAGE_SHA256 = "e1296a9b55ff6d29fde55bf545e44be737c4f5d534b12b69f1ded5f05a0a7eaf"
_V2_SELECTION_SHA256 = "8307bbe843b0db0f95949f29de106e32ee6dff5f83bdd44bfd7a33c29c7404e9"
_V2_ACCEPTANCE_SHA256 = "e589d7c980b4467fc21e13445c4af19202ea662cae9f7277f61e98a3e7702647"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_THREAD_ENV = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)
_SOURCE_FILES = (
    "benchmarks/task43_hp_adaptivity/h100_anchor.py",
    "benchmarks/task43_hp_adaptivity/compare_v2_endpoints.py",
    "benchmarks/task43_hp_adaptivity/sample_v2_legacy_r10_fields.py",
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
    "src/adaptivity/variable_p_transfer.py",
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
    *,
    workflow_ledger: WorkflowLedger | None = None,
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
        if workflow_ledger is not None:
            ledger_stage = f"task43_{stage}"
            if status == "begin":
                workflow_ledger.set_phase(ledger_stage)
            workflow_ledger.marker(f"{ledger_stage}_{status}", details)


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


def _plain_nested_containers(value: Any) -> Any:
    """Copy read-only mappings to pickle/JSON-safe plain containers."""

    if isinstance(value, Mapping):
        return {
            _plain_nested_containers(key): _plain_nested_containers(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(_plain_nested_containers(item) for item in value)
    if isinstance(value, list):
        return [_plain_nested_containers(item) for item in value]
    return value


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
    on_sample=None,
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
        try:
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
                if on_sample is not None:
                    on_sample(order, samples[f"q{order}"])
        except Exception as exc:  # noqa: BLE001 - fail closed on sampling/callback errors
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
    *,
    expected_keys: frozenset[tuple[str, int, int, str]] = R13_MODE_KEYS,
) -> dict[str, Any]:
    def key(row: dict[str, Any]) -> tuple[str, int, int, str]:
        return str(row["side"]), int(row["m"]), int(row["n"]), str(row["polarization"])

    reference_keys = [key(row) for row in reference_rows]
    candidate_keys = [key(row) for row in candidate_rows]
    if (
        reference_keys != candidate_keys
        or len(reference_keys) != len(expected_keys)
        or set(reference_keys) != expected_keys
    ):
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
    expected_keys: frozenset[tuple[str, int, int, str]] = R13_MODE_KEYS,
    initial_active_action: dict[str, Any] | None = None,
    initial_explicit_residual: dict[str, Any] | None = None,
    v2_endpoint_identity: dict[str, Any] | None = None,
    on_extra_sample=None,
    workflow_ledger: WorkflowLedger | None = None,
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
    is_v2 = v2_endpoint_identity is not None
    if is_v2 and (initial_active_action is None or initial_explicit_residual is None):
        raise ValueError("V2 same-LU uncertainty requires both before-state residual audits")
    if is_v2 and len(expected_keys) not in {612, 836}:
        raise ValueError("V2 same-LU uncertainty requires the frozen R13 or R14 inventory")
    before_explicit_residual = (
        initial_explicit_residual
        if initial_explicit_residual is not None
        else _linear_residual(view.A, view.b, view.x)
    )
    before_condensed_residual = _plain_nested_containers(view.full_active_residual)

    _log_stage(
        comm,
        started,
        "same_lu_residual_correction",
        "begin",
        workflow_ledger=workflow_ledger,
    )
    corrected_x, correction = single_petsc_residual_correction(
        view.A, view.b, view.x, view.ksp
    )
    try:
        modes = tuple(view.goal_context["modes"])
        n_auxiliary = len(modes)
        n_fem_tail = int(corrected_x.getSize()) - n_auxiliary
        if n_auxiliary != len(expected_keys) or n_fem_tail < 0:
            raise RuntimeError("corrected vector does not contain the full ordered modal tail")
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
            _log_stage(
                comm,
                started,
                "same_lu_recovery_and_a6",
                "begin",
                workflow_ledger=workflow_ledger,
            )
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
            _log_stage(
                comm,
                started,
                "same_lu_recovery_and_a6",
                "end",
                workflow_ledger=workflow_ledger,
            )

            root_error = None
            tight_root = run_root / "same_lu_tightening"
            ports_root = (
                tight_root / "after" / "ports"
                if is_v2
                else tight_root / "ports"
            )
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

            before_a_volume = None
            before_port_metrics = _plain_nested_containers(view.port_metrics)
            if is_v2:
                _log_stage(
                    comm,
                    started,
                    "same_lu_before_volume_absorption",
                    "begin",
                    workflow_ledger=workflow_ledger,
                )
                before_volume = compute_volume_absorption_3d(
                    view.mesh_data,
                    view.config,
                    view.recovered.field,
                    tight_root / "before" / "volume",
                    incident_power=incident_power_3d(view.config),
                    port_metrics=before_port_metrics,
                )
                before_a_volume = before_volume.get("A_volume_total")
                if before_a_volume is None or not np.isfinite(float(before_a_volume)):
                    raise ValueError("same-LU before-state A_volume_total is missing or non-finite")
                before_a_volume = float(before_a_volume)
                before_port_metrics["R_plus_T_plus_A_volume"] = float(
                    before_port_metrics["R_total"]
                    + before_port_metrics["T_total"]
                    + before_a_volume
                )
                before_port_metrics["energy_closure_error_dtn_port_modal_volume"] = float(
                    before_port_metrics["R_plus_T_plus_A_volume"] - 1.0
                )
                _log_stage(
                    comm,
                    started,
                    "same_lu_before_volume_absorption",
                    "end",
                    workflow_ledger=workflow_ledger,
                )

            _log_stage(
                comm,
                started,
                "same_lu_volume_absorption",
                "begin",
                workflow_ledger=workflow_ledger,
            )
            corrected_volume_root = (
                tight_root / "after" / "volume" if is_v2 else tight_root / "volume"
            )
            corrected_volume = compute_volume_absorption_3d(
                view.mesh_data,
                view.config,
                corrected_recovered.field,
                corrected_volume_root,
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
            _log_stage(
                comm,
                started,
                "same_lu_volume_absorption",
                "end",
                workflow_ledger=workflow_ledger,
            )

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

            _log_stage(
                comm,
                started,
                "same_lu_field_capture",
                "begin",
                workflow_ledger=workflow_ledger,
            )
            corrected_fields = _field_capture(
                corrected_recovered.field,
                view.mesh_data,
                view.config,
                comm,
                None,
                "initial_180",
                on_sample=on_extra_sample,
            )
            corrected_storage_arrays, corrected_storage_metadata = (
                _active_solution_storage(corrected_view)
            )
            _log_stage(
                comm,
                started,
                "same_lu_field_capture",
                "end",
                workflow_ledger=workflow_ledger,
            )

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
                        original_port["orders"],
                        corrected_port["orders"],
                        expected_keys=expected_keys,
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
                    v2_uncertainty = None
                    if is_v2:
                        assert initial_active_action is not None
                        before_a6_payload = initial_active_action[
                            "full_solver_gauge_residual"
                        ]
                        before_a6 = float(
                            before_a6_payload["relative_to_independent_rhs"]
                        )
                        before_condensed = float(
                            before_condensed_residual[
                                "linear_system_relative_residual"
                            ]
                        )
                        before_reduced = float(
                            before_explicit_residual["linear_system_relative_residual"]
                        )
                        before_explicit_norm = float(
                            before_explicit_residual["linear_system_residual_norm"]
                        )
                        corrected_explicit_norm = float(
                            corrected_reduced_residual["linear_system_residual_norm"]
                        )
                        before_closure = float(
                            before_port_metrics[
                                "energy_closure_error_dtn_port_modal_volume"
                            ]
                        )
                        before_rows_path = run_root / "solve" / (
                            "dtn_port_diffraction_orders_3d.json"
                        )
                        with before_rows_path.open(encoding="utf-8") as stream:
                            before_payload = json.load(stream)
                        physical_identity = v2_endpoint_identity[
                            "physical_configuration"
                        ]
                        physical_sha = physical_identity["sha256"]
                        discretization_sha = physical_identity[
                            "discretization_identity"
                        ]["sha256"]
                        same_lu_modal = compare_r13_modal_outputs(
                            before_payload,
                            json.loads(corrected_port_path.read_text(encoding="utf-8")),
                            reference_a_volume=before_a_volume,
                            candidate_a_volume=corrected_a_volume,
                            reference_physical_configuration_sha256=physical_sha,
                            candidate_physical_configuration_sha256=physical_sha,
                            reference_discretization_sha256=discretization_sha,
                            candidate_discretization_sha256=discretization_sha,
                            expected_keys=expected_keys,
                        )
                        field_comparisons = {}
                        volume = float(
                            view.config.period_x
                            * view.config.period_y
                            * (view.config.domain_z_max - view.config.domain_z_min)
                        )
                        e_floor = float(np.sqrt(volume))
                        h_floor = e_floor * float(
                            view.config.magnetic_field_scale_A_per_m
                        )
                        g_floor = float(np.sqrt(2.0 * volume))
                        for order, before_sample in initial_fields["samples"].items():
                            after_sample = corrected_fields["samples"][order]
                            field_comparisons[order] = compare_field_sample_bundles(
                                _v2_field_bundle_from_capture(
                                    before_sample, view.config, physical_sha
                                ),
                                _v2_field_bundle_from_capture(
                                    after_sample, view.config, physical_sha
                                ),
                                k0_per_nm=float(view.config.k0),
                                magnetic_field_scale_A_per_m=float(
                                    view.config.magnetic_field_scale_A_per_m
                                ),
                                mu_r=complex(view.config.mu_r),
                                incident_e_norm_floor=e_floor,
                                incident_h_norm_floor=h_floor,
                                incident_g_norm_floor=g_floor,
                            )
                        a6_after = independent_a6
                        explicit_finite = all(
                            np.isfinite(value)
                            for value in (
                                before_explicit_norm,
                                corrected_explicit_norm,
                                before_reduced,
                                reduced_relative,
                            )
                        )
                        quality_gates = {
                            "before_and_after_explicit_b_minus_Ax_finite": bool(
                                explicit_finite
                            ),
                            "explicit_residual_norm_strictly_decreased": bool(
                                explicit_finite
                                and corrected_explicit_norm < before_explicit_norm
                            ),
                            "rhs_normalized_residual_strictly_decreased": bool(
                                explicit_finite and reduced_relative < before_reduced
                            ),
                            "before_explicit_relative_le_1e-8": bool(
                                np.isfinite(before_reduced) and before_reduced <= 1.0e-8
                            ),
                            "after_explicit_relative_le_1e-8": bool(
                                np.isfinite(reduced_relative)
                                and reduced_relative <= 1.0e-8
                            ),
                            "before_and_after_independent_A6_le_1e-8": bool(
                                bool(before_a6_payload["finite"])
                                and np.isfinite(before_a6)
                                and before_a6 <= 1.0e-8
                                and bool(independent_gauge["finite"])
                                and np.isfinite(a6_after)
                                and a6_after <= 1.0e-8
                            ),
                            "before_and_after_condensed_residual_le_1e-9": bool(
                                np.isfinite(before_condensed)
                                and before_condensed <= 1.0e-9
                                and np.isfinite(condensed_relative)
                                and condensed_relative <= 1.0e-9
                            ),
                            **{
                                f"before_{name}": passed
                                for name, passed in _v3_residual_scope_gates(
                                    before_explicit_residual,
                                    before_condensed_residual,
                                ).items()
                            },
                            **{
                                f"after_{name}": passed
                                for name, passed in _v3_residual_scope_gates(
                                    corrected_reduced_residual,
                                    condensed_residual,
                                ).items()
                            },
                            "before_and_after_energy_closure_le_1e-5": bool(
                                np.isfinite(before_closure)
                                and abs(before_closure) <= 1.0e-5
                                and np.isfinite(corrected_closure)
                                and abs(corrected_closure) <= 1.0e-5
                            ),
                            "all_modal_outputs_within_0p1_final_tolerance": bool(
                                same_lu_modal["pass_10_percent_perturbation_gate"]
                            ),
                            "all_q8_q10_field_outputs_within_0p1_final_tolerance": bool(
                                all(
                                    item["pass_10_percent_perturbation_gate"]
                                    for item in field_comparisons.values()
                                )
                            ),
                        }
                        v2_uncertainty = {
                            "schema": "task43.v2.same_lu_output_uncertainty.v1",
                            "extra_corrections_applied": 1,
                            "separate_from_solver_normal_correction": True,
                            "before_explicit_residual": before_explicit_residual,
                            "after_explicit_residual": corrected_reduced_residual,
                            "before_independent_A6": initial_active_action,
                            "after_independent_A6": independent_active_action,
                            "before_condensed_residual": before_condensed_residual,
                            "after_condensed_residual": condensed_residual,
                            "before_port_metrics": before_port_metrics,
                            "after_port_metrics": corrected_port_metrics,
                            "before_A_volume_total": before_a_volume,
                            "after_A_volume_total": corrected_a_volume,
                            "same_inventory_modal_comparison": same_lu_modal,
                            "same_point_field_comparisons": field_comparisons,
                            "gates": quality_gates,
                            "pass": all(value is True for value in quality_gates.values()),
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
                        "v2_output_uncertainty": v2_uncertainty,
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
            result = _plain_nested_containers(result)
            result, result_error = comm.bcast((result, result_error), root=0)
            if result_error is not None:
                raise RuntimeError(f"same-LU postprocessing failed: {result_error}")
            _log_stage(
                comm,
                started,
                "same_lu_tightening",
                "end",
                workflow_ledger=workflow_ledger,
            )
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
    *,
    identity: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
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
    if identity is None:
        np.savez_compressed(path, **arrays)
        return None
    else:
        return write_atomic_npz(
            path,
            arrays,
            identity=identity,
            schema="task43.v3.primary_q8_q10_samples.v1",
            classification="measured_primary_samples_before_extra_correction_not_official",
        )


def _validate_v3_primary_packet_arrays(
    packet_arrays: Mapping[str, np.ndarray], raw_vector_keys: set[str]
) -> None:
    """Validate V3 evidence arrays without flattening storage identity arrays."""

    missing = raw_vector_keys.difference(packet_arrays)
    if missing:
        raise TypeError(f"V3 primary packet is missing raw vectors: {sorted(missing)}")
    for name, raw_values in packet_arrays.items():
        values = np.asarray(raw_values)
        if values.dtype.hasobject:
            raise TypeError(f"V3 primary packet array {name} has object dtype")
        if not np.isfinite(values).all():
            raise ValueError(f"V3 primary packet array {name} is non-finite")
        if name in raw_vector_keys and values.ndim != 1:
            raise ValueError(f"V3 primary raw vector {name} is not one-dimensional")


def _write_v3_partial_terminal(
    run_root: Path,
    *,
    phase: str | None,
    source_identity: dict[str, Any],
    captured: dict[str, Any],
    error: BaseException | str,
) -> dict[str, Any]:
    """Demote any incomplete V3 endpoint while retaining before evidence."""

    error_text = (
        f"{type(error).__name__}: {error}"
        if isinstance(error, BaseException)
        else str(error)
    )
    terminal_path = (Path(run_root) / "task43_v3_partial_terminal.json").resolve()
    run_summary_path = Path(run_root) / "solve" / "run_summary.json"
    native_run_summary = {
        "path": str(run_summary_path.resolve()),
        "status": "not_present",
        "sha256": _sha256_file(run_summary_path)
        if run_summary_path.is_file()
        else None,
    }
    if run_summary_path.is_file():
        try:
            run_summary = json.loads(run_summary_path.read_text(encoding="utf-8"))
            if not isinstance(run_summary, dict):
                raise TypeError("native run_summary.json is not an object")
            original_sha256 = _sha256_file(run_summary_path)
            legacy_official = run_summary.get(
                "legacy_solver_reported_official_result",
                run_summary.get("official_result"),
            )
            legacy_case_status = run_summary.get(
                "legacy_solver_reported_case_status",
                run_summary.get("case_status"),
            )
            run_summary["legacy_solver_reported_official_result"] = legacy_official
            run_summary["legacy_solver_reported_case_status"] = legacy_case_status
            run_summary["official_result"] = False
            run_summary["diagnostic_only"] = True
            run_summary["case_status"] = "failed_or_incomplete_task43_v3_endpoint"
            run_summary["task43_v3_endpoint_authority"] = False
            run_summary["task43_v3_failure_terminal_path"] = str(terminal_path)
            run_summary["task43_v3_failure_error"] = error_text
            written = write_atomic_json(
                run_summary_path,
                run_summary,
                refuse_overwrite=False,
            )
            native_run_summary = {
                "path": str(run_summary_path.resolve()),
                "status": "demoted_to_diagnostic_only",
                "pre_demote_sha256": original_sha256,
                "post_demote_sha256": written["sha256"],
                "legacy_solver_reported_official_result": legacy_official,
                "legacy_solver_reported_case_status": legacy_case_status,
            }
        except (OSError, TypeError, ValueError) as summary_error:
            native_run_summary["status"] = "demotion_failed"
            native_run_summary["error"] = (
                f"{type(summary_error).__name__}: {summary_error}"
            )
    endpoint_path = Path(run_root) / "task43_v2_a1_endpoint.json"
    if endpoint_path.is_file():
        try:
            endpoint = json.loads(endpoint_path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            endpoint = None
        if isinstance(endpoint, dict):
            endpoint["pass"] = False
            endpoint["status"] = "FAILED_OR_INCOMPLETE_V3_POSTPROCESS"
            endpoint["official_result"] = False
            endpoint["selection_eligible"] = False
            endpoint["selection_candidate"] = False
            endpoint["candidate_selected"] = False
            endpoint["continuation_all_false"] = True
            endpoint["continuation"] = {
                "same_group_R": False,
                "A1_R": False,
                "A2_q": False,
                "A2_R": False,
                "A2_q3": False,
                "B": False,
                "C": False,
                "cost_campaign": False,
                "iteration": False,
            }
            gates = endpoint.get("gates")
            if isinstance(gates, dict):
                gates["status"] = "failed"
                if "pass" in gates:
                    gates["pass"] = False
                gates["continuation_all_false"] = True
            endpoint["failure_error"] = error_text
            endpoint["failure_terminal_path"] = str(
                terminal_path
            )
            write_atomic_json(endpoint_path, endpoint, refuse_overwrite=False)
    record = task43_v3_partial_terminal_record(
        phase=phase,
        source_identity=source_identity,
        error=error_text,
        primary_before_extra_packet=captured.get(
            "v3_primary_before_extra_packet"
        ),
        primary_q_samples=captured.get("v3_primary_sample_records", {}),
        extra_q_samples=captured.get("v3_extra_sample_records", {}),
        primary_q8_q10_bundle=captured.get("v3_primary_q8_q10_samples"),
        pre_validation_checkpoint=captured.get("pre_validation_checkpoint"),
        native_run_summary=native_run_summary,
    )
    path = Path(run_root) / "task43_v3_partial_terminal.json"
    if path.is_file():
        return {"path": str(path), "sha256": _sha256_file(path)}
    return write_atomic_json(path, record, refuse_overwrite=True)


def _configure_direct_factor_backend(cfg, requested: str) -> None:
    """Select an existing direct factor implementation; leave defaults intact."""
    if requested not in {"default", "mumps"}:
        raise ValueError(f"unsupported direct factor backend: {requested}")
    if requested == "mumps":
        cfg.petsc_extra_options = dict(cfg.petsc_extra_options or {})
        cfg.petsc_extra_options["pc_factor_mat_solver_type"] = "mumps"


def _load_v2_diagnostic_contract(path: Path, expected_sha256: str) -> dict[str, Any]:
    contract_path = path.resolve()
    expected_path = (
        _REPOSITORY_ROOT
        / "docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v2_contract.json"
    ).resolve()
    markdown_path = (
        _REPOSITORY_ROOT / "docs/task43_hp_adaptivity/diagnostic_plan_v2.md"
    )
    if contract_path != expected_path:
        raise ValueError("V2 diagnostics must use the tracked frozen contract path")
    if expected_sha256 != _V2_CONTRACT_SHA256:
        raise ValueError("V2 contract CLI SHA is not the frozen contract identity")
    if _sha256_file(contract_path) != _V2_CONTRACT_SHA256:
        raise ValueError("tracked V2 diagnostic contract hash changed")
    if _sha256_file(markdown_path) != _V2_PLAN_MARKDOWN_SHA256:
        raise ValueError("tracked V2 diagnostic plan hash changed")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if (
        contract.get("schema") != "task43.v2.finite_diagnostic_contract.v2"
        or contract.get("status") != "frozen_for_execution"
        or contract.get("formal_model_attempts", {}).get("current_v2_formal_models_run")
        != 0
    ):
        raise ValueError("V2 diagnostic contract is not the frozen executable contract")
    return contract


def _configure_v2_a1_endpoint(cfg, phase: str, contract: dict[str, Any]) -> dict[str, Any]:
    phases = {item["id"]: item for item in contract["phases"]["A1"]}
    if phase not in {"A1_q", "A1_R"} or phase not in phases:
        raise ValueError(f"unsupported V2 A1 phase: {phase!r}")
    if cfg.stage4_full3d_assembly_backend != ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND:
        raise ValueError("V2 A1 requires the recorded variable-p condensed route")
    endpoint = contract["quadrature_and_modal_endpoints"]
    cfg.stage4_volume_quadrature_degree = int(endpoint["test_volume_q"])
    cfg.stage4_incident_quadrature_degree = int(endpoint["test_incident_and_port_q"])
    cfg.stage4_dtn_quadrature_degree = int(endpoint["test_incident_and_port_q"])
    modal_name = "R13" if phase == "A1_q" else "R14"
    modal = endpoint[modal_name]
    cfg.stage4_dtn_order_policy = "explicit_rectangle"
    cfg.stage4_dtn_rectangle_max_m = int(modal["max_abs_m"])
    cfg.stage4_dtn_rectangle_max_n = int(modal["max_abs_n"])
    expected_mode_count = 4 * (2 * cfg.stage4_dtn_rectangle_max_m + 1) * (
        2 * cfg.stage4_dtn_rectangle_max_n + 1
    )
    if expected_mode_count != int(modal["count"]):
        raise ValueError("V2 contract mode rectangle and count disagree")
    route = contract["spatial_core_identities"]["A1_R10"]["solver_settings"]
    if route["backend"] != ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND:
        raise ValueError("V2 contract A1 route differs from the implemented backend")
    cfg.stage4_cell_static_condensation = bool(route["cell_static_condensation"])
    cfg.stage4_assembly_time_cell_static_condensation = bool(
        route["assembly_time_static_condensation"]
    )
    cfg.stage4_floquet_slave_elimination = bool(route["floquet_slave_elimination"])
    if not all(
        (
            cfg.stage4_cell_static_condensation,
            cfg.stage4_assembly_time_cell_static_condensation,
            cfg.stage4_floquet_slave_elimination,
        )
    ):
        raise ValueError("V2 A1 must explicitly preserve all recorded condensation flags")
    backend = resolve_stage4_full3d_assembly_backend(cfg, apply=False)
    if backend["actual"] != ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND:
        raise ValueError(f"V2 A1 resolved an unexpected assembly backend: {backend}")
    _configure_direct_factor_backend(cfg, "mumps")
    return {
        "phase": phase,
        "reference": phases[phase]["reference"],
        "test": phases[phase]["test"],
        "changed_only": phases[phase]["changed_only"],
        "quadrature": {
            "volume": int(cfg.stage4_volume_quadrature_degree),
            "incident": int(cfg.stage4_incident_quadrature_degree),
            "ports": int(cfg.stage4_dtn_quadrature_degree),
        },
        "modal_rectangle": {
            "max_abs_m": int(cfg.stage4_dtn_rectangle_max_m),
            "max_abs_n": int(cfg.stage4_dtn_rectangle_max_n),
            "mode_count": expected_mode_count,
        },
        "backend_audit": backend,
        "factor_solver": "mumps",
        "same_lu_solver_residual_correction_enabled": True,
    }


def _v2_endpoint_identity(
    cfg,
    modes,
    *,
    axes_nm: dict[str, Any],
    candidate_plan_sha256: str,
    active_degree_plan_sha256: str,
    phase: str,
    contract_sha256: str,
) -> dict[str, Any]:
    physical_identity = task43_v2_physical_configuration_identity(
        cfg.as_jsonable(),
        axis_values_nm=axes_nm,
        candidate_plan_sha256=candidate_plan_sha256,
        active_degree_plan_sha256=active_degree_plan_sha256,
    )
    expected_keys = R13_MODE_KEYS if phase == "A1_q" else R14_MODE_KEYS
    actual_keys = {
        (str(mode.side), int(mode.m), int(mode.n), str(mode.polarization))
        for mode in modes
    }
    if len(modes) != len(expected_keys) or actual_keys != expected_keys:
        raise ValueError(
            f"{phase} resolved mode inventory has {len(actual_keys)} unexpected keys"
        )
    controls = {
        "phase": phase,
        "quadrature": {
            "volume": int(cfg.stage4_volume_quadrature_degree),
            "incident": int(cfg.stage4_incident_quadrature_degree),
            "ports": int(cfg.stage4_dtn_quadrature_degree),
        },
        "modal_rectangle": {
            "m": int(cfg.stage4_dtn_rectangle_max_m),
            "n": int(cfg.stage4_dtn_rectangle_max_n),
            "mode_count": len(modes),
        },
        "assembly_backend": str(cfg.stage4_full3d_assembly_backend),
        "factor_solver": str(
            dict(cfg.petsc_extra_options or {}).get("pc_factor_mat_solver_type", "")
        ),
        "stage4_cell_static_condensation": bool(cfg.stage4_cell_static_condensation),
        "stage4_assembly_time_cell_static_condensation": bool(
            cfg.stage4_assembly_time_cell_static_condensation
        ),
        "stage4_floquet_slave_elimination": bool(cfg.stage4_floquet_slave_elimination),
    }
    return {
        "schema": "task43.v2.a1_endpoint_identity.v1",
        "contract_sha256": contract_sha256,
        "physical_configuration": physical_identity,
        "numerical_controls": controls,
        "numerical_controls_sha256": _sha256_json(controls),
    }


def _v2_field_bundle_from_capture(
    sample: dict[str, np.ndarray], cfg, physical_configuration_sha256: str
) -> dict[str, Any]:
    points = np.asarray(sample["points_nm"], dtype=np.float64)
    background_e = electric_field_code_values(cfg, points)
    background_h = cfg.magnetic_field_scale_A_per_m * magnetic_field_code_values(
        cfg, points
    )
    total_e = np.asarray(sample["E_total"], dtype=np.complex128)
    total_h = np.asarray(sample["H_total_A_per_m"], dtype=np.complex128)
    return {
        "physical_configuration_identity_sha256": physical_configuration_sha256,
        "points_nm": points,
        "weights_nm3": np.asarray(sample["weights_nm3"], dtype=np.float64),
        "E_total_code": total_e,
        "curl_E_total_code": np.asarray(sample["curl_E_total"], dtype=np.complex128),
        "H_total_A_per_m": total_h,
        "incident_background_E_code": np.asarray(background_e, dtype=np.complex128),
        "incident_background_H_A_per_m": np.asarray(background_h, dtype=np.complex128),
        "E_scattered_code": scattered_field_samples(total_e, background_e),
        "H_scattered_A_per_m": scattered_field_samples(total_h, background_h),
    }


def _v2_field_bundle_from_npz(
    samples_path: Path,
    order: int,
    cfg,
    physical_configuration_sha256: str,
) -> dict[str, Any]:
    prefix = f"q{order}_"
    with np.load(samples_path, allow_pickle=False) as samples:
        available = set(samples.files)
        names = {
            "points_nm": ("points_nm",),
            "weights_nm3": ("weights_nm3",),
            "E_total_code": ("E_total_code", "E_total"),
            "curl_E_total_code": ("curl_E_total_code", "curl_E_total"),
            "H_total_A_per_m": ("H_total_A_per_m",),
        }
        arrays = {}
        for output, aliases in names.items():
            matches = [prefix + alias for alias in aliases if prefix + alias in available]
            if len(matches) != 1:
                raise ValueError(
                    f"{samples_path} q{order} sample must contain exactly one "
                    f"{output} schema field; found {matches}"
                )
            arrays[output] = np.asarray(samples[matches[0]]).copy()
    points = np.asarray(arrays["points_nm"], dtype=np.float64)
    background_e = electric_field_code_values(cfg, points)
    background_h = cfg.magnetic_field_scale_A_per_m * magnetic_field_code_values(
        cfg, points
    )
    total_e = np.asarray(arrays["E_total_code"], dtype=np.complex128)
    total_h = np.asarray(arrays["H_total_A_per_m"], dtype=np.complex128)
    return {
        "physical_configuration_identity_sha256": physical_configuration_sha256,
        **arrays,
        "incident_background_E_code": np.asarray(background_e, dtype=np.complex128),
        "incident_background_H_A_per_m": np.asarray(background_h, dtype=np.complex128),
        "E_scattered_code": scattered_field_samples(total_e, background_e),
        "H_scattered_A_per_m": scattered_field_samples(total_h, background_h),
    }


def _v2_legacy_r10_reference() -> dict[str, Any]:
    artifact_root = _REPOSITORY_ROOT / "benchmarks/artifacts/task43"
    resampling_record_path = (
        artifact_root
        / "v2_legacy_r10_field_resampling_attempt3/fields/legacy_r10_field_resampling.json"
    )
    sample_path = (
        artifact_root
        / "v2_legacy_r10_field_resampling_attempt3/fields/r10_q8_q10_field_samples.npz"
    )
    run_root = artifact_root / "round10_p_up_attempt1/run"
    record_path = run_root / "task43_round1_candidate_record.json"
    rows_path = run_root / "solve/dtn_port_diffraction_orders_3d.json"
    plan_path = run_root / "candidate_plan.json"
    storage_path = run_root / "candidate_recovered_solution_storage.npz"
    for path, expected, label in (
        (
            resampling_record_path,
            _V2_LEGACY_R10_RECORD_SHA256,
            "legacy R10 field resampling record",
        ),
        (sample_path, _V2_LEGACY_R10_SAMPLE_SHA256, "legacy R10 q8/q10 samples"),
        (record_path, _V2_R10_RECORD_SHA256, "legacy R10 solver record"),
        (plan_path, _V2_R10_PLAN_SHA256, "legacy R10 candidate plan"),
        (storage_path, _V2_R10_STORAGE_SHA256, "legacy R10 recovered coefficients"),
        (rows_path, _V2_R10_ROWS_SHA256, "legacy R10 R13 modal rows"),
    ):
        if _sha256_file(path) != expected:
            raise ValueError(f"{label} hash differs from its frozen evidence identity")
    resampling = json.loads(resampling_record_path.read_text(encoding="utf-8"))
    if (
        resampling.get("PDE_solve_performed") is not False
        or resampling.get("candidate_id") != "round10_p_up"
        or resampling.get("candidate_record_sha256") != _V2_R10_RECORD_SHA256
        or resampling.get("plan_sha256") != _V2_R10_PLAN_SHA256
        or resampling.get("recovered_storage_sha256") != _V2_R10_STORAGE_SHA256
        or resampling.get("mode_rows_sha256") != _V2_R10_ROWS_SHA256
    ):
        raise ValueError("legacy R10 resampling identity does not bind the frozen solve")
    compatibility = resampling.get("solver_source_compatibility", {})
    if (
        compatibility.get("all_recorded_numerical_sources_match") is not True
        or compatibility.get("matching_source_file_count") != 41
        or compatibility.get("mismatches") != []
    ):
        raise ValueError("legacy R10 numerical-source continuity evidence is incomplete")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    payload = json.loads(rows_path.read_text(encoding="utf-8"))
    _v2_validated_rows(
        payload, label="legacy R10 q15/q28/R13", expected=R13_MODE_KEYS
    )
    controls = record["numerical_controls"]
    if (
        controls.get("volume_quadrature_degree") != 15
        or controls.get("incident_and_port_quadrature_degree") != 28
        or controls.get("ordered_mode_count") != 612
    ):
        raise ValueError("legacy R10 baseline does not use q15/q28/R13")
    identity = resampling["sampling"]["physical_configuration_identity"]
    return {
        "phase": "frozen_R10_q15_q28_R13",
        "record": record,
        "record_path": record_path,
        "record_sha256": _V2_R10_RECORD_SHA256,
        "payload": payload,
        "payload_path": rows_path,
        "payload_sha256": _V2_R10_ROWS_SHA256,
        "samples_path": sample_path,
        "samples_sha256": _V2_LEGACY_R10_SAMPLE_SHA256,
        "physical_configuration_identity": identity,
        "physical_configuration_sha256": identity["sha256"],
        "discretization_sha256": identity["discretization_identity"]["sha256"],
        "A_volume_total": float(record["power"]["A_volume_total"]),
        "solver_source_compatibility": compatibility,
    }


def _v2_normal_correction_passed(report: Any) -> bool:
    if not isinstance(report, dict):
        return False
    try:
        initial_norm = float(report["initial_condensed_residual_norm"])
        corrected_norm = float(report["corrected_condensed_residual_norm"])
        initial_relative = float(report["initial_condensed_relative_to_rhs"])
        corrected_relative = float(report["corrected_condensed_relative_to_rhs"])
        reason = int(report["correction_ksp"]["converged_reason"])
    except (KeyError, TypeError, ValueError):
        return False
    return bool(
        report.get("status") == "passed"
        and report.get("solution_updated") is True
        and all(
            np.isfinite(value) and value >= 0.0
            for value in (
                initial_norm,
                corrected_norm,
                initial_relative,
                corrected_relative,
            )
        )
        and corrected_norm < initial_norm
        and corrected_relative < initial_relative
        and reason > 0
    )


def _v2_recompute_reference_hard_gates(
    record: dict[str, Any], payload: dict[str, Any], expected_keys: set
) -> dict[str, bool]:
    """Recompute A1 hard gates from the saved solver and power measurements."""
    solver = record.get("solver", {})
    explicit = solver.get("explicit_b_minus_Ax", {})
    independent_a6 = solver.get("independent_A6", {}).get(
        "full_solver_gauge_residual", {}
    )
    condensed = solver.get("condensed_residual", {})
    normal_correction = solver.get("normal_same_lu_correction")
    local_h = solver.get("local_h_audit", {})
    storage = record.get("recovered_solution_storage", {})
    power = record.get("power", {})
    aggregate = power.get("aggregate", {})
    payload_metrics = payload.get("metrics", {})

    def finite_or_none(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if np.isfinite(parsed) else None

    explicit_relative = finite_or_none(
        explicit.get("linear_system_relative_residual")
    )
    a6_relative = finite_or_none(independent_a6.get("relative_to_independent_rhs"))
    condensed_relative = finite_or_none(
        condensed.get("linear_system_relative_residual")
    )
    rows = payload.get("orders", [])
    try:
        rows_r_total = finite_or_none(sum(float(row["R"]) for row in rows))
        rows_t_total = finite_or_none(sum(float(row["T"]) for row in rows))
    except (KeyError, TypeError, ValueError):
        rows_r_total = None
        rows_t_total = None
    payload_r_total = finite_or_none(payload_metrics.get("R_total"))
    payload_t_total = finite_or_none(payload_metrics.get("T_total"))
    record_r_total = finite_or_none(aggregate.get("R_total"))
    record_t_total = finite_or_none(aggregate.get("T_total"))
    a_volume = finite_or_none(power.get("A_volume_total"))
    closure = (
        rows_r_total + rows_t_total + a_volume - 1.0
        if None not in (rows_r_total, rows_t_total, a_volume)
        else None
    )
    stored_closure = finite_or_none(power.get("energy_closure_error"))
    stored_sum = finite_or_none(power.get("R_plus_T_plus_A_volume"))
    if (
        closure is None
        or stored_closure is None
        or stored_sum is None
        or None
        in (
            payload_r_total,
            payload_t_total,
            record_r_total,
            record_t_total,
            rows_r_total,
            rows_t_total,
        )
    ):
        closure_matches_record = False
    else:
        row_payload_aggregate_matches = bool(
            np.isclose(rows_r_total, payload_r_total, rtol=2.0e-10, atol=1.0e-13)
            and np.isclose(rows_t_total, payload_t_total, rtol=2.0e-10, atol=1.0e-13)
            and np.isclose(rows_r_total, record_r_total, rtol=2.0e-10, atol=1.0e-13)
            and np.isclose(rows_t_total, record_t_total, rtol=2.0e-10, atol=1.0e-13)
        )
        closure_matches_record = bool(
            row_payload_aggregate_matches
            and np.isclose(closure, stored_closure, rtol=1.0e-12, atol=1.0e-15)
            and np.isclose(
                closure + 1.0, stored_sum, rtol=1.0e-12, atol=1.0e-15
            )
        )

    expected_inventory = "R13" if len(expected_keys) == len(R13_MODE_KEYS) else "R14"
    recomputed = {
        "solver_completed": solver.get("case_status") == "completed",
        "actual_live_and_summary_factor_backend_mumps": (
            solver.get("actual_direct_factor_backend") == "mumps"
            and solver.get("actual_live_direct_factor_backend") == "mumps"
        ),
        "normal_same_lu_correction_passed": (
            _v2_normal_correction_passed(normal_correction)
        ),
        "exact_complete_modal_inventory": (
            record.get("modal_outputs", {}).get("inventory") == expected_inventory
            and record.get("modal_outputs", {}).get("mode_count")
            == len(expected_keys)
            and len(rows) == len(expected_keys)
        ),
        "explicit_b_minus_Ax_relative_le_1e-8": bool(
            explicit_relative is not None and 0.0 <= explicit_relative <= 1.0e-8
        ),
        "independent_A6_relative_le_1e-8": bool(
            independent_a6.get("finite") is True
            and a6_relative is not None
            and 0.0 <= a6_relative <= 1.0e-8
        ),
        "condensed_residual_relative_le_1e-9": bool(
            condensed_relative is not None
            and 0.0 <= condensed_relative <= 1.0e-9
        ),
        "energy_closure_absolute_le_1e-5": bool(
            closure_matches_record and abs(closure) <= 1.0e-5
        ),
        "local_h_closure_pass": local_h.get("pass") is True,
        "variable_p_degree_plan_pass": storage.get("degree_plan_pass") is True,
        "trace_constraint_closure_pass": (
            storage.get("trace_constraints_pass") is True
        ),
        "active_fe_dof_resource_gate_pass": (
            storage.get("active_fe_dof_gate_pass") is True
        ),
    }
    stored = record.get("hard_solver_gates")
    if stored != recomputed:
        raise ValueError(
            "A1 reference hard-gate fields disagree with recomputed solver/power evidence"
        )
    if record.get("hard_solver_gates_pass") is not all(recomputed.values()):
        raise ValueError("A1 reference hard-gate summary disagrees with raw evidence")
    return recomputed


def _v2_a1_reference_endpoint(
    run_root: Path,
    *,
    expected_phase: str,
    contract_sha256: str,
    require_hard_gates: bool = True,
) -> dict[str, Any]:
    record_path = run_root / "task43_v2_a1_endpoint.json"
    if not record_path.is_file():
        raise FileNotFoundError(f"missing V2 A1 reference endpoint: {record_path}")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if (
        record.get("schema") != "task43.v2.a1_endpoint.v1"
        or record.get("phase") != expected_phase
        or record.get("contract_sha256") != contract_sha256
        or record.get("candidate_id") != "round10_p_up"
    ):
        raise ValueError("A1 reference endpoint identity/phase/contract mismatch")
    rows_path = Path(record["modal_outputs"]["file"]).resolve()
    samples_path = Path(record["field_samples"]["file"]).resolve()
    if rows_path != (run_root / "solve/dtn_port_diffraction_orders_3d.json").resolve():
        raise ValueError("A1 reference modal output path differs from its run root")
    if samples_path != (run_root / "field_samples_q8_q10.npz").resolve():
        raise ValueError("A1 reference field sample path differs from its run root")
    if _sha256_file(rows_path) != record["modal_outputs"]["sha256"]:
        raise ValueError("A1 reference modal output hash differs from its record")
    if _sha256_file(samples_path) != record["field_samples"]["sha256"]:
        raise ValueError("A1 reference field sample hash differs from its record")
    payload = json.loads(rows_path.read_text(encoding="utf-8"))
    expected_keys = R13_MODE_KEYS if expected_phase == "A1_q" else R14_MODE_KEYS
    _v2_validated_rows(
        payload, label=f"A1 reference {expected_phase}", expected=expected_keys
    )
    hard_gates = _v2_recompute_reference_hard_gates(record, payload, expected_keys)
    if require_hard_gates and not all(hard_gates.values()):
        raise ValueError("A1_R requires the A1_q endpoint's recomputed hard gates to pass")
    return {
        "phase": expected_phase,
        "record": record,
        "record_path": record_path,
        "record_sha256": _sha256_file(record_path),
        "payload": payload,
        "payload_path": rows_path,
        "payload_sha256": record["modal_outputs"]["sha256"],
        "samples_path": samples_path,
        "samples_sha256": record["field_samples"]["sha256"],
        "physical_configuration_identity": record["endpoint_identity"][
            "physical_configuration"
        ],
        "physical_configuration_sha256": record["endpoint_identity"][
            "physical_configuration"
        ]["sha256"],
        "discretization_sha256": record["endpoint_identity"][
            "physical_configuration"
        ]["discretization_identity"]["sha256"],
        "A_volume_total": float(record["power"]["A_volume_total"]),
        "recomputed_hard_solver_gates": hard_gates,
    }


def _v3_residual_scope_gates(
    returned_trace_dtn_residual: Mapping[str, Any],
    block_gaussian_full_active_residual: Mapping[str, Any],
) -> dict[str, bool]:
    """Apply V3 residual limits to the scopes their stored values actually describe.

    Older endpoint names are retained for compatibility, but ``explicit`` is the
    returned trace/DtN system and ``condensed`` is the block-Gaussian transformed
    full-active residual.  V3 records both scopes explicitly and gates each against
    its own frozen limit.
    """

    def relative(record: Mapping[str, Any]) -> float | None:
        try:
            value = float(record["linear_system_relative_residual"])
        except (KeyError, TypeError, ValueError):
            return None
        return value if np.isfinite(value) and value >= 0.0 else None

    returned_relative = relative(returned_trace_dtn_residual)
    transformed_relative = relative(block_gaussian_full_active_residual)
    return {
        "returned_trace_dtn_condensed_relative_le_1e-9": (
            returned_relative is not None and returned_relative <= 1.0e-9
        ),
        "block_gaussian_full_transformed_relative_le_1e-8": (
            transformed_relative is not None and transformed_relative <= 1.0e-8
        ),
    }


def _validate_v3_a1_entry_contract(contract: Mapping[str, Any]) -> None:
    """Accept only the single frozen A1_q2 extension of the V2 plan."""

    attempts = contract.get("formal_model_attempts", {})
    authority = contract.get("authority", {})
    immutable = contract.get("immutable_prior_contracts_and_review", {})
    phases = contract.get("phases", {})
    a1_rows = phases.get("A1", [])
    row = next(
        (
            item
            for item in a1_rows
            if isinstance(item, Mapping) and item.get("id") == "A1_q"
        ),
        None,
    )
    prohibited = set(contract.get("prohibited", ()))
    if (
        contract.get("schema") != "task43.v3.finite_diagnostic_contract.v1"
        or contract.get("status") != "frozen_for_execution"
        or authority.get("review_commit")
        != "fd7ebd2a60eb6fd7d776f1ca68d367581e8f7d12"
        or authority.get("review_path")
        != "docs/task43_hp_adaptivity/review_report_v2.md"
        or authority.get("execution_section") != "10"
        or immutable.get("docs/task43_hp_adaptivity/review_report_v2.md")
        != "7899e25ab9b2dee763dbc4b99255d98ed4c23ae935853a9f5cfb1f3ce99ffbbf"
        or immutable.get(
            "docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v2_contract.json"
        )
        != "33a5d94ea8c61a26fb1d55c6268709fd283acc549beaeba429833aa68f5055cc"
        or immutable.get(
            "docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v2_a2_native_contract.json"
        )
        != "77c533673eba4178868ef22f4a27f8d7ecfbf50d6a47acbcbf2fe45b269960d0"
        or attempts.get("total_original_max") != 6
        or attempts.get("already_consumed") != 3
        or attempts.get("new_dispatches_max") != 2
        or attempts.get("cumulative_max_after_this_review") != 5
        or attempts.get("sealed_remaining_unallocated") != 1
        or attempts.get("no_automatic_retry") is not True
        or attempts.get("A1_cumulative_max_this_review") != 2
        or attempts.get("A2_cumulative_max_this_review") != 3
        or row is None
        or row.get("attempt") != 2
        or row.get("new_dispatches_max") != 1
        or row.get("operator_q") != 19
        or row.get("incident_port_q") != 32
        or row.get("modal_rectangle") != "R13"
        or row.get("normal_corrections") != 1
        or row.get("extra_corrections_max") != 1
        or not {"A1_R", "A2_R", "B", "C"}.issubset(prohibited)
        or phases.get("A1_R", {}).get("authorized") is not False
        or phases.get("A2_R", {}).get("authorized") is not False
        or phases.get("B", {}).get("authorized") is not False
        or phases.get("C", {}).get("authorized") is not False
    ):
        raise ValueError("Task43 V3 A1_q2 entry differs from its frozen allocation")


def _require_v3_watchdog_worker_identity(
    *, require_unused_phase_file: bool = True
) -> dict[str, Any]:
    """Verify the post-exec A1 worker is the watchdog's direct child."""

    try:
        expected_parent = int(os.environ["PHYSICAL_WATCHDOG_PARENT_PID"])
        phase_path = Path(os.environ["PHYSICAL_WATCHDOG_PHASE_PATH"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("V3 A1 requires native watchdog parent and phase identity") from exc
    actual_parent = os.getppid()
    if expected_parent != actual_parent:
        raise RuntimeError(
            "V3 A1 worker is not the direct child registered by its native watchdog"
        )
    if not phase_path.is_absolute():
        raise RuntimeError("V3 A1 watchdog phase path must be absolute")
    phase_path = phase_path.resolve()
    if not phase_path.parent.is_dir():
        raise RuntimeError("V3 A1 watchdog phase parent directory is missing")
    if require_unused_phase_file and phase_path.exists():
        raise RuntimeError("V3 A1 watchdog phase file already exists")
    return {
        "worker_pid": os.getpid(),
        "worker_parent_pid": actual_parent,
        "watchdog_parent_pid_environment": expected_parent,
        "direct_watchdog_parent_verified": True,
        "phase_path": str(phase_path),
    }


def _validate_v3_consumed_formal_attempts(
    contract: Mapping[str, Any], repository_root: Path
) -> None:
    """Verify the three counted V1/V2 dispatch terminals before either V3 route."""

    entries = contract.get("formal_model_attempts", {}).get("consumed_attempts")
    expected = (("A1_q", 1), ("A2_q", 1), ("A2_q", 2))
    if not isinstance(entries, list) or len(entries) != len(expected):
        raise ValueError("V3 allocation must bind exactly the three prior dispatches")
    for entry, (phase, attempt) in zip(entries, expected, strict=True):
        if (
            not isinstance(entry, Mapping)
            or entry.get("phase") != phase
            or entry.get("attempt") != attempt
        ):
            raise ValueError("V3 prior dispatch inventory is incomplete or reordered")
        attempt_root = repository_root / str(entry.get("attempt_root", ""))
        summary_path = attempt_root / "watchdog/summary.json"
        launcher_path = attempt_root / "launcher_exit_code.txt"
        if (
            not summary_path.is_file()
            or _sha256_file(summary_path) != entry.get("watchdog_summary_sha256")
            or not launcher_path.is_file()
            or launcher_path.read_text(encoding="utf-8").strip()
            != str(entry.get("launcher_exit"))
        ):
            raise ValueError(f"V3 prior {phase} attempt {attempt} evidence changed")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if (
            summary.get("classification") != entry.get("classification")
            or summary.get("leader_exit_code") != entry.get("worker_exit")
            or summary.get("descendants_cleared")
            is not entry.get("descendants_cleared")
        ):
            raise ValueError(f"V3 prior {phase} attempt {attempt} terminal changed")


def _v2_a1_endpoint_record(
    *,
    phase: str,
    run_root: Path,
    summary: dict[str, Any],
    actual_factor_backend: str | None,
    actual_live_factor_backend: str | None,
    environment: dict[str, Any],
    cfg,
    candidate_identity: dict[str, Any],
    source_identity: dict[str, Any],
    endpoint_controls: dict[str, Any],
    reference: dict[str, Any],
    captured: dict[str, Any],
    port_payload: dict[str, Any],
    rows_path: Path,
    samples_path: Path,
    storage_record: dict[str, Any],
    A_volume_total: float,
    contract_sha256: str,
) -> dict[str, Any]:
    expected_keys = R13_MODE_KEYS if phase == "A1_q" else R14_MODE_KEYS
    _v2_validated_rows(
        port_payload, label=f"A1 endpoint {phase}", expected=expected_keys
    )
    endpoint_identity = captured["v2_endpoint_identity"]
    physical_identity = endpoint_identity["physical_configuration"]
    physical_sha256 = physical_identity["sha256"]
    discretization_sha256 = physical_identity["discretization_identity"]["sha256"]
    if phase == "A1_q":
        modal_comparison = compare_r13_modal_outputs(
            reference["payload"],
            port_payload,
            reference_a_volume=reference["A_volume_total"],
            candidate_a_volume=A_volume_total,
            reference_physical_configuration_sha256=(
                reference["physical_configuration_sha256"]
            ),
            candidate_physical_configuration_sha256=physical_sha256,
            reference_discretization_sha256=reference["discretization_sha256"],
            candidate_discretization_sha256=discretization_sha256,
            expected_keys=R13_MODE_KEYS,
        )
    elif phase == "A1_R":
        modal_comparison = compare_r13_r14_modal_outputs(
            reference["payload"],
            port_payload,
            r13_a_volume=reference["A_volume_total"],
            r14_a_volume=A_volume_total,
            r13_physical_configuration_sha256=(
                reference["physical_configuration_sha256"]
            ),
            r14_physical_configuration_sha256=physical_sha256,
            r13_discretization_sha256=reference["discretization_sha256"],
            r14_discretization_sha256=discretization_sha256,
        )
    else:
        raise ValueError(f"unsupported V2 A1 endpoint phase {phase!r}")

    field_comparisons = {}
    volume = float(
        cfg.period_x * cfg.period_y * (cfg.domain_z_max - cfg.domain_z_min)
    )
    e_floor = float(np.sqrt(volume))
    h_floor = e_floor * float(cfg.magnetic_field_scale_A_per_m)
    g_floor = float(np.sqrt(2.0 * volume))
    for order in (8, 10):
        reference_bundle = _v2_field_bundle_from_npz(
            reference["samples_path"],
            order,
            cfg,
            reference["physical_configuration_sha256"],
        )
        current_bundle = _v2_field_bundle_from_capture(
            captured["fields"]["samples"][f"q{order}"], cfg, physical_sha256
        )
        field_comparisons[f"q{order}"] = compare_field_sample_bundles(
            reference_bundle,
            current_bundle,
            k0_per_nm=float(cfg.k0),
            magnetic_field_scale_A_per_m=float(cfg.magnetic_field_scale_A_per_m),
            mu_r=complex(cfg.mu_r),
            incident_e_norm_floor=e_floor,
            incident_h_norm_floor=h_floor,
            incident_g_norm_floor=g_floor,
        )

    independent = captured["independent_active_action"][
        "full_solver_gauge_residual"
    ]
    explicit = captured["explicit_active_residual"]
    condensed = captured["condensed_residual"]
    local_h = captured.get("local_h_audit", {})
    storage_metadata = captured.get("solution_storage_metadata", {})
    port_metrics = port_payload["metrics"]
    closure = float(
        float(port_metrics["R_total"])
        + float(port_metrics["T_total"])
        + A_volume_total
        - 1.0
    )
    normal_correction = summary.get("variable_p_same_lu_residual_correction")
    def finite_or_none(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if np.isfinite(parsed) else None

    explicit_relative = finite_or_none(
        explicit.get("linear_system_relative_residual")
    )
    a6_relative = finite_or_none(independent.get("relative_to_independent_rhs"))
    condensed_relative = finite_or_none(
        condensed.get("linear_system_relative_residual")
    )
    v3_scope_gates = _v3_residual_scope_gates(explicit, condensed)
    hard_gates = {
        "solver_completed": summary.get("case_status") == "completed",
        "actual_live_and_summary_factor_backend_mumps": (
            actual_factor_backend == "mumps"
            and actual_live_factor_backend == "mumps"
        ),
        "normal_same_lu_correction_passed": (
            _v2_normal_correction_passed(normal_correction)
        ),
        "exact_complete_modal_inventory": (
            int(captured.get("mode_count", -1)) == len(expected_keys)
            and len(port_payload.get("orders", [])) == len(expected_keys)
        ),
        "explicit_b_minus_Ax_relative_le_1e-8": bool(
            explicit_relative is not None and 0.0 <= explicit_relative <= 1.0e-8
        ),
        "independent_A6_relative_le_1e-8": bool(
            independent.get("finite") is True
            and a6_relative is not None
            and 0.0 <= a6_relative <= 1.0e-8
        ),
        "condensed_residual_relative_le_1e-9": bool(
            condensed_relative is not None
            and 0.0 <= condensed_relative <= 1.0e-9
        ),
        **v3_scope_gates,
        "energy_closure_absolute_le_1e-5": bool(
            np.isfinite(closure) and abs(closure) <= 1.0e-5
        ),
        "local_h_closure_pass": local_h.get("pass") is True,
        "variable_p_degree_plan_pass": storage_metadata.get("degree_plan_pass")
        is True,
        "trace_constraint_closure_pass": storage_metadata.get(
            "trace_constraints_pass"
        )
        is True,
        "active_fe_dof_resource_gate_pass": storage_metadata.get(
            "active_fe_dof_gate_pass"
        )
        is True,
    }
    modal_pass = modal_comparison.get("pass_10_percent_perturbation_gate") is True
    field_gates = {
        f"{order}_field_outputs_within_0p1_final_tolerance": (
            field_comparisons[f"q{order}"].get("pass_10_percent_perturbation_gate")
            is True
        )
        for order in (8, 10)
    }
    same_lu_result = captured.get("same_lu_tightening")
    same_lu = (
        same_lu_result.get("v2_output_uncertainty")
        if isinstance(same_lu_result, dict)
        else None
    )
    uncertainty_pass = isinstance(same_lu, dict) and same_lu.get("pass") is True
    perturbation_gates = {
        "modal_outputs_within_0p1_final_tolerance": modal_pass,
        **field_gates,
        "extra_same_lu_output_uncertainty_pass": uncertainty_pass,
    }
    gates = {
        **{f"hard_{name}": value for name, value in hard_gates.items()},
        **perturbation_gates,
    }
    gates_pass = all(value is True for value in gates.values())
    return {
        "schema": "task43.v2.a1_endpoint.v1",
        "classification": "controlled_A1_factor_diagnostic_not_selection_eligible",
        "contract_sha256": contract_sha256,
        "selection_eligible": False,
        "official_result": False,
        "phase": phase,
        "candidate_id": "round10_p_up",
        "candidate_identity": candidate_identity,
        "environment": environment,
        "diagnostic_contract": {
            "file": str(
                _REPOSITORY_ROOT
                / "docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v2_contract.json"
            ),
            "sha256": contract_sha256,
            "plan_markdown_sha256": _V2_PLAN_MARKDOWN_SHA256,
        },
        "endpoint_controls": endpoint_controls,
        "endpoint_identity": endpoint_identity,
        "reference": {
            "phase": reference["phase"],
            "record_file": str(reference["record_path"]),
            "record_sha256": reference["record_sha256"],
            "modal_outputs": {
                "file": str(reference["payload_path"]),
                "sha256": reference["payload_sha256"],
            },
            "field_samples": {
                "file": str(reference["samples_path"]),
                "sha256": reference["samples_sha256"],
            },
            "solver_source_compatibility": reference.get(
                "solver_source_compatibility"
            ),
        },
        "field_and_modal_endpoint_state": (
            "after the solver's configured normal correction and before the one extra diagnostic correction"
        ),
        "solver": {
            "case_status": summary.get("case_status"),
            "actual_direct_factor_backend": actual_factor_backend,
            "actual_live_direct_factor_backend": actual_live_factor_backend,
            "normal_same_lu_correction": normal_correction,
            "local_h_audit": local_h,
            "explicit_b_minus_Ax": explicit,
            "independent_A6": captured.get("independent_active_action"),
            "condensed_residual": condensed,
            "extra_same_lu_output_uncertainty": same_lu,
        },
        "power": {
            "aggregate": port_metrics,
            "A_volume_total": A_volume_total,
            "R_plus_T_plus_A_volume": float(
                float(port_metrics["R_total"])
                + float(port_metrics["T_total"])
                + A_volume_total
            ),
            "energy_closure_error": closure,
            "channel_rows_file": str(rows_path.resolve()),
            "channel_rows_sha256": _sha256_file(rows_path),
        },
        "modal_outputs": {
            "file": str(rows_path.resolve()),
            "sha256": _sha256_file(rows_path),
            "inventory": "R13" if phase == "A1_q" else "R14",
            "mode_count": len(expected_keys),
            "comparison": modal_comparison,
        },
        "field_samples": {
            "file": str(samples_path.resolve()),
            "sha256": _sha256_file(samples_path),
            "quadrature_orders": [8, 10],
            "point_counts": {
                key: int(value["weights_nm3"].size)
                for key, value in captured["fields"]["samples"].items()
            },
            "physical_H_from_recovered_curl": True,
            "phase_fit": False,
            "comparison": field_comparisons,
        },
        "recovered_solution_storage": storage_record,
        "hard_solver_gates": hard_gates,
        "hard_solver_gates_pass": all(hard_gates.values()),
        "v3_residual_scope_metrics": {
            "returned_trace_dtn_condensed_relative": explicit_relative,
            "returned_trace_dtn_condensed_limit": 1.0e-9,
            "block_gaussian_full_transformed_relative": condensed_relative,
            "block_gaussian_full_transformed_limit": 1.0e-8,
            "scope_gates": v3_scope_gates,
        },
        "perturbation_gates": perturbation_gates,
        "gates": gates,
        "pass": gates_pass,
        "source_identity": source_identity,
        "run_root": str(run_root.resolve()),
        "not_run": [
            "vertical material-side one-sided traces remain NOT_MEASURED",
            "A2, B, and C remain subject to frozen diagnostic-plan gates",
        ],
    }


def _run_impl(
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
    same_lu_solve_residual_correction_enabled: bool = False,
    direct_factor_backend: str = "default",
    v2_diagnostic_phase: str | None = None,
    v2_contract_path: Path | None = None,
    v2_contract_sha256: str | None = None,
    v2_reference_run_root: Path | None = None,
    v3_failure_evidence_enabled: bool = False,
    v3_contract_path: Path | None = None,
    v3_contract_sha256: str | None = None,
    v3_plan_path: Path | None = None,
    v3_plan_sha256: str | None = None,
    _failure_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    comm = MPI.COMM_WORLD
    started = time.perf_counter()
    expected_size, kind = _CASES[case]
    current_case = case == _CURRENT_CASE
    candidate_case = case == _ROUND1_CANDIDATE_CASE
    v2_diagnostic = v2_diagnostic_phase is not None
    if v3_failure_evidence_enabled and not v2_diagnostic:
        raise ValueError("V3 failure evidence requires a frozen V2 endpoint route")
    v3_fields = (
        v3_contract_path,
        v3_contract_sha256,
        v3_plan_path,
        v3_plan_sha256,
    )
    if v3_failure_evidence_enabled:
        if (
            v2_diagnostic_phase != "A1_q"
            or not candidate_case
            or any(value is None for value in v3_fields)
        ):
            raise ValueError("V3 A1 evidence is fixed to A1_q attempt 2")
    elif any(value is not None for value in v3_fields):
        raise ValueError("V3 contract inputs require --v3-failure-evidence")
    if v2_diagnostic and not candidate_case:
        raise ValueError("V2 A1 diagnostics reuse only the accepted R10 candidate route")
    if v2_diagnostic and (
        candidate_id != "round10_p_up"
        or not same_lu_tightening_enabled
        or not same_lu_solve_residual_correction_enabled
        or direct_factor_backend != "mumps"
    ):
        raise ValueError(
            "V2 A1 requires the frozen R10 candidate, normal solver correction, "
            "one extra same-LU check, and MUMPS"
        )
    if v2_diagnostic and (
        v2_contract_path is None or v2_contract_sha256 is None
    ):
        raise ValueError("V2 A1 requires the frozen diagnostic contract and SHA")
    if v2_diagnostic_phase == "A1_R" and v2_reference_run_root is None:
        raise ValueError("A1_R requires the completed A1_q reference endpoint")
    if v2_diagnostic_phase == "A1_q" and v2_reference_run_root is not None:
        raise ValueError("A1_q uses the frozen original R10 reference, not a run path")
    if same_lu_solve_residual_correction_enabled and not candidate_case:
        raise ValueError(
            "same-LU solve residual correction is only enabled for a candidate case"
        )
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
        direct_factor_backend,
        v2_diagnostic_phase,
        None if v2_contract_path is None else str(v2_contract_path.resolve()),
        v2_contract_sha256,
        None
        if v2_reference_run_root is None
        else str(v2_reference_run_root.resolve()),
        bool(v3_failure_evidence_enabled),
        None if v3_contract_path is None else str(v3_contract_path.resolve()),
        v3_contract_sha256,
        None if v3_plan_path is None else str(v3_plan_path.resolve()),
        v3_plan_sha256,
    )
    root_contracts = comm.allgather(root_contract)
    if any(contract != root_contracts[0] for contract in root_contracts[1:]):
        raise RuntimeError("all MPI ranks must use identical run/reference roots")
    run_root = Path(root_contract[0])
    if _failure_context is not None:
        _failure_context["run_root"] = run_root
        _failure_context["phase"] = v2_diagnostic_phase
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
    v2_diagnostic_phase = root_contract[11]
    v2_contract_path = None if root_contract[12] is None else Path(root_contract[12])
    v2_contract_sha256 = root_contract[13]
    v2_reference_run_root = (
        None if root_contract[14] is None else Path(root_contract[14])
    )
    v3_failure_evidence_enabled = bool(root_contract[15])
    v3_contract_path = None if root_contract[16] is None else Path(root_contract[16])
    v3_contract_sha256 = root_contract[17]
    v3_plan_path = None if root_contract[18] is None else Path(root_contract[18])
    v3_plan_sha256 = root_contract[19]
    v2_diagnostic = v2_diagnostic_phase is not None
    v2_contract = (
        _load_v2_diagnostic_contract(v2_contract_path, str(v2_contract_sha256))
        if v2_diagnostic
        else None
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
    if _failure_context is not None:
        _failure_context["run_root"] = run_root

    v3_workflow_ledger = None
    if v3_failure_evidence_enabled and comm.rank == 0:
        watchdog_identity = _require_v3_watchdog_worker_identity()
        v3_workflow_ledger = WorkflowLedger(
            run_root, Path(watchdog_identity["phase_path"])
        )
        v3_workflow_ledger.set_phase("preflight")
        v3_workflow_ledger.marker(
            "task43_v3_a1_worker_identity_bound", watchdog_identity
        )
        if _failure_context is not None:
            _failure_context["workflow_ledger"] = v3_workflow_ledger

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
        if v2_diagnostic and (
            candidate_id != "round10_p_up"
            or candidate_plan_sha256 != _V2_R10_PLAN_SHA256
            or candidate_identity.get("accepted_parent_selection_sha256")
            != _V2_SELECTION_SHA256
            or candidate_identity.get("acceptance_contract_sha256")
            != _V2_ACCEPTANCE_SHA256
        ):
            raise ValueError("V2 A1 candidate does not match the frozen R10 lineage")
        if v3_workflow_ledger is not None:
            v3_workflow_ledger.marker(
                "task43_v3_a1_candidate_inputs_bound",
                {
                    "candidate_id": str(candidate_id),
                    "candidate_plan_sha256": candidate_plan_sha256,
                    "accepted_parent_selection_sha256": candidate_identity.get(
                        "accepted_parent_selection_sha256"
                    ),
                },
            )

    v2_reference_data = None
    if v2_diagnostic_phase == "A1_q":
        v2_reference_data = _v2_legacy_r10_reference()
    elif v2_diagnostic_phase == "A1_R":
        assert v2_reference_run_root is not None
        v2_reference_data = _v2_a1_reference_endpoint(
            v2_reference_run_root,
            expected_phase="A1_q",
            contract_sha256=str(v2_contract_sha256),
        )
        if v2_reference_data["record"].get("candidate_identity", {}).get(
            "plan_sha256"
        ) != candidate_plan_sha256:
            raise ValueError("A1_R reference endpoint uses another candidate plan")

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
        workflow_ledger=v3_workflow_ledger,
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
    if _failure_context is not None:
        _failure_context["source_identity"] = source_identity
    if v3_workflow_ledger is not None:
        v3_workflow_ledger.marker(
            "task43_v3_a1_source_identity_bound",
            {"git_head": source_identity.get("git_head")},
        )
    if v2_diagnostic:
        source_identity["v2_frozen_contract"] = {
            "contract_path": str(v2_contract_path),
            "contract_sha256": _V2_CONTRACT_SHA256,
            "markdown_plan_sha256": _V2_PLAN_MARKDOWN_SHA256,
        }
        source_identity["v2_reference_endpoint"] = {
            "phase": v2_reference_data["phase"],
            "record_path": str(v2_reference_data["record_path"]),
            "record_sha256": v2_reference_data["record_sha256"],
            "modal_output_path": str(v2_reference_data["payload_path"]),
            "modal_output_sha256": v2_reference_data["payload_sha256"],
            "field_samples_path": str(v2_reference_data["samples_path"]),
            "field_samples_sha256": v2_reference_data["samples_sha256"],
        }
        if v2_diagnostic_phase == "A1_R":
            reference_files = v2_reference_data["record"]["source_identity"].get(
                "file_sha256", {}
            )
            current_files = source_identity.get("file_sha256", {})
            if reference_files != current_files:
                raise ValueError(
                    "A1_R and A1_q must use identical tracked numerical source hashes"
                )
    if v3_failure_evidence_enabled:
        if (
            v3_contract_path is None
            or v3_contract_sha256 != _V3_CONTRACT_SHA256
            or v3_plan_path is None
            or v3_plan_sha256 != _V3_PLAN_SHA256
        ):
            raise ValueError("V3 A1 frozen contract identity changed between ranks")
        source_identity["v3_frozen_contract"] = {
            "contract_path": str(v3_contract_path),
            "contract_sha256": v3_contract_sha256,
            "plan_path": str(v3_plan_path),
            "plan_sha256": v3_plan_sha256,
            "phase": v2_diagnostic_phase,
            "attempt": 2,
        }
        source_identity["v3_watchdog_worker_identity"] = (
            _require_v3_watchdog_worker_identity(require_unused_phase_file=False)
        )
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
    _configure_direct_factor_backend(cfg, direct_factor_backend)
    v2_phase_controls = None
    if v2_diagnostic:
        assert v2_contract is not None and v2_diagnostic_phase is not None
        v2_phase_controls = _configure_v2_a1_endpoint(
            cfg, v2_diagnostic_phase, v2_contract
        )
    _log_stage(
        comm,
        started,
        "mesh_build",
        "begin",
        workflow_ledger=v3_workflow_ledger,
    )
    if v3_workflow_ledger is not None:
        v3_workflow_ledger.set_phase("mesh_setup")
        v3_workflow_ledger.marker(
            "task43_v3_a1_mesh_setup_started",
            {
                "case": case,
                "geometry_profile": geometry_profile,
                "candidate_plan_sha256": candidate_plan_sha256,
            },
        )
    mesh_data = build_airbox_mesh_3d(cfg, run_root / "resolved_mesh")
    if v3_workflow_ledger is not None:
        v3_workflow_ledger.marker("task43_v3_a1_mesh_setup_complete", {})
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
        workflow_ledger=v3_workflow_ledger,
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
    if _failure_context is not None:
        _failure_context["captured"] = captured

    def capture(
        field,
        live_mesh_data,
        live_cfg,
        goal_context,
        *,
        capture_v3_samples: bool = False,
    ) -> None:
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
            sample_fields=(not candidate_case or v2_diagnostic),
            on_sample=(
                (lambda order, sample: _write_v3_primary_sample(order, sample))
                if capture_v3_samples
                else None
            ),
        )
        modes = goal_context["modes"]
        captured["mode_count"] = len(modes)
        captured["ordered_mode_keys"] = [
            [str(mode.side), int(mode.m), int(mode.n), str(mode.polarization)]
            for mode in modes
        ]
        if (current_case or candidate_case) and not v2_diagnostic:
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

    def _write_v3_primary_sample(order: int, sample: dict[str, np.ndarray]) -> None:
        if not v3_failure_evidence_enabled or comm.rank != 0:
            return
        write_v3_primary_field_sample(
            run_root / f"primary_before_extra_q{int(order)}_samples.npz",
            order,
            sample,
            identity={
                "phase": v2_diagnostic_phase,
                "source_identity": source_identity,
                "contract_sha256": v2_contract_sha256,
                "quadrature_order": int(order),
                "mesh_and_dof_order_sha256": captured.get(
                    "solution_storage_metadata", {}
                ).get("mesh_and_dof_order_sha256"),
            },
            sample_records=captured.setdefault("v3_primary_sample_records", {}),
        )

    def _write_v3_extra_sample(order: int, sample: dict[str, np.ndarray]) -> None:
        if not v3_failure_evidence_enabled or comm.rank != 0:
            return
        sample_record = write_atomic_npz(
            run_root
            / "same_lu_tightening"
            / "after"
            / f"field_sample_q{int(order)}.npz",
            sample,
            schema="task43.v3.a1_extra_field_sample.v1",
            classification="measured_extra_sample_after_extra_not_official",
            identity={
                "phase": v2_diagnostic_phase,
                "source_identity": source_identity,
                "contract_sha256": v2_contract_sha256,
                "primary_before_extra_packet_sha256": captured.get(
                    "v3_primary_before_extra_packet", {}
                ).get("npz_sha256"),
                "quadrature_order": int(order),
            },
        )
        captured.setdefault("v3_extra_sample_records", {})[
            f"q{int(order)}"
        ] = sample_record

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
        captured["actual_live_factor_backend"] = (
            view.ksp.getPC().getFactorSolverType()
        )
        if current_case or candidate_case:
            if comm.size == 1:
                _log_stage(
                    comm,
                    started,
                    "pre_validation_checkpoint",
                    "begin",
                    workflow_ledger=v3_workflow_ledger,
                )
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
                checkpoint_profile_identity = (
                    None
                    if v2_diagnostic
                    else task43_profile_identity(
                        view.config,
                        modes,
                        resolved_axes_nm=resolved_axes,
                        resolved_mesh_audit=resolved_mesh_audit,
                    )
                )
                checkpoint_v2_identity = None
                if v2_diagnostic:
                    checkpoint_v2_identity = _v2_endpoint_identity(
                        view.config,
                        modes,
                        axes_nm=resolved_axes,
                        candidate_plan_sha256=str(candidate_plan_sha256),
                        active_degree_plan_sha256=str(
                            storage_metadata["active_degree_plan_sha256"]
                        ),
                        phase=str(v2_diagnostic_phase),
                        contract_sha256=str(v2_contract_sha256),
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
                    "v2_endpoint_identity": checkpoint_v2_identity,
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
                    workflow_ledger=v3_workflow_ledger,
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
        def capture_primary_fields(*, capture_v3_samples: bool) -> None:
            capture_started = time.perf_counter()
            _log_stage(
                comm,
                started,
                "field_capture",
                "begin",
                workflow_ledger=v3_workflow_ledger,
            )
            try:
                capture(
                    view.field,
                    view.mesh_data,
                    view.config,
                    view.goal_context,
                    capture_v3_samples=capture_v3_samples,
                )
            except Exception as error:
                _log_stage(
                    comm,
                    started,
                    "field_capture",
                    "failed",
                    workflow_ledger=v3_workflow_ledger,
                    stage_duration_seconds=time.perf_counter() - capture_started,
                    error=repr(error),
                )
                raise
            if v2_diagnostic:
                storage_metadata = captured.get("solution_storage_metadata")
                if not isinstance(storage_metadata, dict):
                    raise RuntimeError("V2 endpoint lacks captured active-space identity")
                captured["v2_endpoint_identity"] = _v2_endpoint_identity(
                    view.config,
                    view.goal_context["modes"],
                    axes_nm=captured["fields"]["axes_nm"],
                    candidate_plan_sha256=str(candidate_plan_sha256),
                    active_degree_plan_sha256=str(
                        storage_metadata["active_degree_plan_sha256"]
                    ),
                    phase=str(v2_diagnostic_phase),
                    contract_sha256=str(v2_contract_sha256),
                )
            _log_stage(
                comm,
                started,
                "field_capture",
                "end",
                workflow_ledger=v3_workflow_ledger,
                stage_duration_seconds=time.perf_counter() - capture_started,
            )

        if not v3_failure_evidence_enabled:
            capture_primary_fields(capture_v3_samples=False)
        captured["distinct_physical_trace_degrees"] = sorted(
            {
                int(value)
                for value in view.reduction.degree_plan.audit[
                    "trace_degree_values"
                ]
            }
        )
        action_started = time.perf_counter()
        _log_stage(
            comm,
            started,
            "independent_active_action",
            "begin",
            workflow_ledger=v3_workflow_ledger,
        )
        try:
            independent_action = compute_stage4_independent_active_action(
                view, capture_raw_vectors=v3_failure_evidence_enabled
            )
            if v3_failure_evidence_enabled:
                captured["independent_active_action_raw_vectors"] = (
                    independent_action.pop("raw_vectors", None)
                )
                captured["independent_active_action_raw_vector_scope"] = (
                    independent_action.pop("raw_vector_scope", None)
                )
            captured["independent_active_action"] = independent_action
        except Exception as error:
            _log_stage(
                comm,
                started,
                "independent_active_action",
                "failed",
                workflow_ledger=v3_workflow_ledger,
                stage_duration_seconds=time.perf_counter() - action_started,
                error=repr(error),
            )
            raise
        _log_stage(
            comm,
            started,
            "independent_active_action",
            "end",
            workflow_ledger=v3_workflow_ledger,
            stage_duration_seconds=time.perf_counter() - action_started,
        )
        if v2_diagnostic:
            captured["explicit_active_residual"] = _linear_residual(
                view.A, view.b, view.x
            )
        if v3_failure_evidence_enabled:
            captured["full_active_residual_raw_vectors"] = (
                view.full_active_residual.get("raw_vectors")
            )
            captured["full_active_residual_raw_vector_scope"] = (
                view.full_active_residual.get("raw_vector_scope")
            )
        captured["condensed_residual"] = _plain_nested_containers(
            {
                key: value
                for key, value in view.full_active_residual.items()
                if key not in {"raw_vectors", "raw_vector_scope"}
            }
        )
        captured["port_metrics"] = _plain_nested_containers(view.port_metrics)
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
        if v3_failure_evidence_enabled:
            raw_action = view.b.duplicate()
            raw_residual = view.b.duplicate()
            try:
                view.A.mult(view.x, raw_action)
                view.b.copy(raw_residual)
                raw_residual.axpy(PETSc.ScalarType(-1.0), raw_action)
                packet_arrays = {
                    f"recovered_{name}": np.asarray(values)
                    for name, values in captured["solution_storage_arrays"].items()
                }
                packet_arrays.update(
                    returned_trace_dtn_rhs=np.asarray(
                        view.b.getArray(readonly=True), dtype=np.complex128
                    ).copy(),
                    returned_trace_dtn_solution=np.asarray(
                        view.x.getArray(readonly=True), dtype=np.complex128
                    ).copy(),
                    returned_trace_dtn_b_minus_Ax=np.asarray(
                        raw_residual.getArray(readonly=True), dtype=np.complex128
                    ).copy(),
                )
                full_raw = captured.get("full_active_residual_raw_vectors")
                a6_raw = captured.get("independent_active_action_raw_vectors")
                if not isinstance(full_raw, Mapping) or not isinstance(a6_raw, Mapping):
                    raise TypeError(
                        "V3 A1 observer did not retain full-active and independent-A6 raw vectors"
                    )
                if not isinstance(
                    captured.get("full_active_residual_raw_vector_scope"), Mapping
                ) or not isinstance(
                    captured.get("independent_active_action_raw_vector_scope"), Mapping
                ):
                    raise TypeError("V3 A1 raw residual scope metadata is missing")
                packet_arrays.update(
                    {
                        f"full_active_{name}": np.asarray(values)
                        for name, values in full_raw.items()
                    }
                )
                packet_arrays.update(
                    {
                        f"independent_A6_{name}": np.asarray(values)
                        for name, values in a6_raw.items()
                    }
                )
                normal_vectors = view.normal_correction_raw_vectors
                if normal_vectors is None or set(normal_vectors) != {
                    "before_normal_correction_rhs",
                    "before_normal_correction_solution",
                    "before_normal_correction_residual_b_minus_Ax",
                    "after_normal_correction_rhs",
                    "after_normal_correction_solution",
                    "after_normal_correction_residual_b_minus_Ax",
                }:
                    raise RuntimeError(
                        "V3 A1 observer lacks both raw normal-correction vector states"
                    )
                packet_arrays.update(
                    {
                        f"normal_{name}": np.asarray(values)
                        for name, values in normal_vectors.items()
                    }
                )
                raw_vector_keys = {
                    "returned_trace_dtn_rhs",
                    "returned_trace_dtn_solution",
                    "returned_trace_dtn_b_minus_Ax",
                    *{f"full_active_{name}" for name in full_raw},
                    *{f"independent_A6_{name}" for name in a6_raw},
                    *{f"normal_{name}" for name in normal_vectors},
                }
                _validate_v3_primary_packet_arrays(packet_arrays, raw_vector_keys)
                active_rows = int(
                    captured["solution_storage_metadata"]["active_rows"]
                )
                for key in (
                    "full_active_active_full_rhs",
                    "full_active_active_full_solution",
                    "full_active_eliminated_active_interior_residual",
                ):
                    if packet_arrays[key].shape != (active_rows,):
                        raise RuntimeError(
                            f"V3 A1 raw vector {key} has the wrong active-row count"
                        )
                a6_rows = captured["independent_active_action"]["rows"]
                for key, expected_size in (
                    (
                        "independent_A6_independent_active_residual_trace",
                        int(a6_rows["independent_trace"]),
                    ),
                    (
                        "independent_A6_independent_active_residual_cell_interior",
                        int(a6_rows["active_cell_interior"]),
                    ),
                    (
                        "independent_A6_independent_active_modal_lower_solver_gauge",
                        int(a6_rows["modal_lower"]),
                    ),
                ):
                    if packet_arrays[key].shape != (expected_size,):
                        raise RuntimeError(
                            f"V3 A1 raw vector {key} has the wrong row count"
                        )
            finally:
                raw_action.destroy()
                raw_residual.destroy()
            port_path = run_root / "solve" / "dtn_port_diffraction_orders_3d.json"
            packet_identity = {
                "phase": v2_diagnostic_phase,
                "source_identity": source_identity,
                "contract_sha256": v2_contract_sha256,
                "candidate_identity": candidate_identity,
                "v2_endpoint_identity": _v2_endpoint_identity(
                    view.config,
                    view.goal_context["modes"],
                    axes_nm={
                        name: axis.tolist()
                        for name, axis in zip(
                            ("x", "y", "z"), axes, strict=True
                        )
                    },
                    candidate_plan_sha256=str(candidate_plan_sha256),
                    active_degree_plan_sha256=str(
                        captured["solution_storage_metadata"][
                            "active_degree_plan_sha256"
                        ]
                    ),
                    phase=str(v2_diagnostic_phase),
                    contract_sha256=str(v2_contract_sha256),
                ),
                "pre_validation_checkpoint": captured["pre_validation_checkpoint"],
                "port_outputs_written_before_observer": bool(port_path.is_file()),
                "port_output_sha256": (
                    _sha256_file(port_path) if port_path.is_file() else None
                ),
                "normal_correction_audit": _plain_nested_containers(
                    view.primal_solver_telemetry
                ),
                "normal_correction_count": view.primal_solver_telemetry[
                    "normal_correction_count"
                ],
                "normal_correction_raw_vector_keys": sorted(normal_vectors),
                "returned_trace_dtn_system_scope": (
                    "view.A/b/x and b-Ax are the returned independent-trace/DtN "
                    "reduced system; these arrays are not the full active-space residual"
                ),
                "returned_trace_dtn_matrix_shape": [
                    int(value) for value in view.A.getSize()
                ],
                "returned_trace_dtn_residual_metrics": captured.get(
                    "explicit_active_residual"
                ),
                "block_gaussian_full_active_residual_metrics": captured.get(
                    "condensed_residual"
                ),
                "full_active_residual_scope": captured.get(
                    "full_active_residual_raw_vector_scope"
                ),
                "independent_A6_raw_vector_scope": captured.get(
                    "independent_active_action_raw_vector_scope"
                ),
                "independent_A6": captured["independent_active_action"],
                "legacy_returned_system_residual_name": (
                    "explicit_active_residual in the existing endpoint record refers "
                    "to the returned reduced system; V3 packet uses the explicit scope above"
                ),
                "legacy_condensed_residual_name_scope": (
                    "condensed_residual in existing endpoint records is the exact "
                    "block-Gaussian transformed full-active residual; see the raw "
                    "vector method/norm definition above"
                ),
                "condensed_residual": captured["condensed_residual"],
                "port_metrics": captured["port_metrics"],
                "extra_correction_status": "not_run_at_packet_time",
                "official_result": False,
                "passed": False,
            }
            packet_record = None
            packet_error = None
            if comm.rank == 0:
                try:
                    packet_record = write_v3_primary_before_extra_packet(
                        run_root / "primary_before_extra.npz",
                        packet_arrays,
                        identity=packet_identity,
                    )
                    captured["v3_primary_before_extra_packet"] = packet_record
                except (OSError, TypeError, ValueError) as error:
                    packet_error = f"{type(error).__name__}: {error}"
            packet_record, packet_error = comm.bcast(
                (packet_record, packet_error), root=0
            )
            if packet_error is not None:
                raise RuntimeError(f"V3 A1 primary packet write failed: {packet_error}")
            captured["v3_primary_before_extra_packet"] = packet_record
            capture_primary_fields(capture_v3_samples=True)
            samples_path = run_root / "field_samples_q8_q10.npz"
            sample_error = None
            sample_record = None
            if comm.rank == 0:
                try:
                    sample_record = _write_samples(
                        samples_path,
                        captured["fields"]["samples"],
                        tuple(
                            np.asarray(captured["fields"]["axes_nm"][axis])
                            for axis in ("x", "y", "z")
                        ),
                        identity={
                            "phase": v2_diagnostic_phase,
                            "primary_before_extra_packet_sha256": packet_record[
                                "npz_sha256"
                            ],
                            "source_identity": source_identity,
                            "contract_sha256": v2_contract_sha256,
                        },
                    )
                except (OSError, TypeError, ValueError) as error:
                    sample_error = f"{type(error).__name__}: {error}"
            sample_record, sample_error = comm.bcast(
                (sample_record, sample_error), root=0
            )
            if sample_error is not None:
                raise RuntimeError(f"V3 A1 aggregate sample write failed: {sample_error}")
            captured["v3_primary_q8_q10_samples"] = sample_record
        if (current_case or candidate_case) and same_lu_tightening_enabled:
            captured["same_lu_tightening"] = _same_lu_tightening(
                view,
                run_root=run_root,
                comm=comm,
                started=started,
                initial_fields=captured["fields"],
                expected_keys=(
                    R13_MODE_KEYS if v2_diagnostic_phase == "A1_q" else R14_MODE_KEYS
                ) if v2_diagnostic else R13_MODE_KEYS,
                initial_active_action=(
                    captured.get("independent_active_action") if v2_diagnostic else None
                ),
                initial_explicit_residual=(
                    captured.get("explicit_active_residual") if v2_diagnostic else None
                ),
                v2_endpoint_identity=(
                    captured.get("v2_endpoint_identity") if v2_diagnostic else None
                ),
                on_extra_sample=(
                    _write_v3_extra_sample if v3_failure_evidence_enabled else None
                ),
                workflow_ledger=v3_workflow_ledger,
            )

    _log_stage(
        comm,
        started,
        "solve_and_observe",
        "begin",
        workflow_ledger=v3_workflow_ledger,
    )
    try:
        summary = run_stage4b_block_grating_3d_case(
            cfg,
            run_root / "solve",
            solution_observer=(native_observer if kind == "native_p3" else None),
            variable_p_live_observer=(
                active_observer if kind == "empty_h_active_p3" else None
            ),
            variable_p_single_lu_residual_correction=(
                same_lu_solve_residual_correction_enabled
            ),
            variable_p_capture_normal_correction_vectors=(
                v3_failure_evidence_enabled
            ),
            mesh_data_override=mesh_data,
        )
    except BaseException as error:
        if v3_failure_evidence_enabled:
            terminal_error = None
            if comm.rank == 0:
                try:
                    _write_v3_partial_terminal(
                        run_root,
                        phase=v2_diagnostic_phase,
                        source_identity=source_identity,
                        captured=captured,
                        error=error,
                    )
                except (OSError, TypeError, ValueError) as write_error:
                    terminal_error = f"{type(write_error).__name__}: {write_error}"
            terminal_error = comm.bcast(terminal_error, root=0)
            if terminal_error is not None:
                print(
                    f"failed to persist V3 partial terminal: {terminal_error}",
                    file=sys.stderr,
                    flush=True,
                )
        raise
    _log_stage(
        comm,
        started,
        "solve_and_observe",
        "end",
        workflow_ledger=v3_workflow_ledger,
    )
    actual_factor_backend = summary.get("actual_pc_factor_solver_type")
    actual_live_factor_backend = captured.get("actual_live_factor_backend")
    if kind == "empty_h_active_p3" and actual_live_factor_backend != actual_factor_backend:
        raise RuntimeError("live and summary direct factor backend identities differ")
    if direct_factor_backend == "mumps" and actual_factor_backend != "mumps":
        raise RuntimeError(
            f"requested MUMPS direct factor, actual backend={actual_factor_backend!r}"
        )
    source_paths = {
        name: Path(__file__).resolve().parents[2] / name for name in _SOURCE_FILES
    }
    source_hashes_after = {
        name: _sha256_file(path) for name, path in source_paths.items()
    }
    if source_hashes_before != source_hashes_after:
        raise RuntimeError("a source file changed while the PDE case was running")
    expected_mode_count = len(
        R13_MODE_KEYS
        if not v2_diagnostic or v2_diagnostic_phase == "A1_q"
        else R14_MODE_KEYS
    )
    if int(captured.get("mode_count", -1)) != expected_mode_count:
        raise RuntimeError(
            "resolved modal inventory differs from the endpoint contract: "
            f"actual={captured.get('mode_count')}, expected={expected_mode_count}"
        )
    _log_stage(
        comm,
        started,
        "record_and_compare",
        "begin",
        workflow_ledger=v3_workflow_ledger,
    )
    post_error = None
    task43_gated_official_result = None
    if comm.rank == 0:
        record_path = run_root / (
            "task43_v2_a1_endpoint.json"
            if v2_diagnostic
            else (
                "task43_initial180_current_record.json"
                if current_case
                else (
                    "task43_round1_candidate_record.json"
                    if candidate_case
                    else "task43_h100_anchor_record.json"
                )
            )
        )
        try:
            orders_path = run_root / "solve" / "dtn_port_diffraction_orders_3d.json"
            with orders_path.open(encoding="utf-8") as stream:
                port_payload = json.load(stream)
            rows = port_payload["orders"]
            if len(rows) != expected_mode_count:
                raise RuntimeError(
                    "serialized channel output differs from the endpoint contract: "
                    f"actual={len(rows)}, expected={expected_mode_count}"
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
            if not candidate_case or v2_diagnostic:
                samples_path = run_root / "field_samples_q8_q10.npz"
                if v3_failure_evidence_enabled:
                    sample_record = captured.get("v3_primary_q8_q10_samples")
                    if (
                        not isinstance(sample_record, dict)
                        or not samples_path.is_file()
                        or _sha256_file(samples_path)
                        != sample_record.get("npz_sha256")
                    ):
                        raise RuntimeError(
                            "V3 A1 primary q8/q10 bundle is absent or changed after its pre-extra write"
                        )
                else:
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
                (
                    "all_expected_ordered_modes_present"
                    if v2_diagnostic
                    else "all_612_ordered_modes_present"
                ): len(rows) == expected_mode_count,
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
                    "requested_direct_factor_backend": direct_factor_backend,
                    "actual_direct_factor_backend": actual_factor_backend,
                    "actual_live_direct_factor_backend": actual_live_factor_backend,
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
                    "same_lu_solver_residual_correction": summary.get(
                        "variable_p_same_lu_residual_correction"
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
                    if candidate_case and not v2_diagnostic
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
            if v2_diagnostic:
                assert v2_diagnostic_phase is not None
                assert v2_phase_controls is not None
                assert v2_reference_data is not None
                assert v2_contract_sha256 is not None
                assert samples_path is not None
                record = _v2_a1_endpoint_record(
                    phase=v2_diagnostic_phase,
                    run_root=run_root,
                    summary=summary,
                    actual_factor_backend=actual_factor_backend,
                    actual_live_factor_backend=actual_live_factor_backend,
                    environment=environment,
                    cfg=cfg,
                    candidate_identity=candidate_identity or {},
                    source_identity=source_identity,
                    endpoint_controls=v2_phase_controls,
                    reference=v2_reference_data,
                    captured=captured,
                    port_payload=port_payload,
                    rows_path=orders_path,
                    samples_path=samples_path,
                    storage_record=storage_record,
                    A_volume_total=a_volume,
                    contract_sha256=v2_contract_sha256,
                )
                if v3_failure_evidence_enabled:
                    record["continuation"] = {
                        "same_group_R": False,
                        "A1_R": False,
                        "A2_R": False,
                        "B": False,
                        "C": False,
                    }
                    record["continuation_all_false"] = True
                    record["selection_eligible"] = False
                    record["selection_candidate"] = False
                    record["candidate_selected"] = False
                    record["v3_primary_before_extra_packet"] = captured.get(
                        "v3_primary_before_extra_packet"
                    )
                    record["v3_primary_samples"] = {
                        "individual": captured.get("v3_primary_sample_records", {}),
                        "q8_q10_bundle": captured.get(
                            "v3_primary_q8_q10_samples"
                        ),
                    }
                    record["v3_extra_samples"] = captured.get(
                        "v3_extra_sample_records", {}
                    )
                    record["complete_v3_failure_safe_endpoint"] = True
                gates = dict(record["gates"])
                gates["pass"] = bool(record["pass"])
                gates["status"] = "passed" if gates["pass"] else "failed"
                record["gates"] = gates
                task43_gated_official_result = False
            record_path.write_text(
                json.dumps(
                    _plain_nested_containers(record),
                    indent=2,
                    sort_keys=True,
                    default=_json_default,
                )
                + "\n",
                encoding="utf-8",
            )
            if not gates["pass"] and not v2_diagnostic:
                post_error = f"Task43 case gates failed; see {record_path}"
            _log_stage(
                comm,
                started,
                "record_and_compare",
                gates["status"],
                workflow_ledger=v3_workflow_ledger,
                record_path=str(record_path),
            )
        except Exception as exc:  # noqa: BLE001 - broadcast rank-zero postsolve failures
            post_error = f"{type(exc).__name__}: {exc}"
            if v3_failure_evidence_enabled:
                try:
                    _write_v3_partial_terminal(
                        run_root,
                        phase=v2_diagnostic_phase,
                        source_identity=source_identity,
                        captured=captured,
                        error=exc,
                    )
                except (OSError, TypeError, ValueError) as terminal_error:
                    post_error += (
                        f"; terminal-persist={type(terminal_error).__name__}: "
                        f"{terminal_error}"
                    )
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
            workflow_ledger=v3_workflow_ledger,
            error=post_error,
        )
        raise RuntimeError(post_error)
    _log_stage(
        comm,
        started,
        "case_complete",
        "end",
        workflow_ledger=v3_workflow_ledger,
        total_wall_seconds=time.perf_counter() - started,
    )
    return summary


def _run_with_v3_failure_terminal(run_impl, *args, **kwargs) -> dict[str, Any]:
    """Persist a V3 terminal if any post-solve step escapes its local handler."""
    from inspect import signature

    bound = signature(_run_impl).bind_partial(*args, **kwargs)
    arguments = bound.arguments
    v3_enabled = bool(arguments.get("v3_failure_evidence_enabled", False))
    context: dict[str, Any] = {
        "run_root": arguments.get("run_root"),
        "phase": arguments.get("v2_diagnostic_phase"),
        "source_identity": {},
        "captured": {},
    }
    kwargs["_failure_context"] = context
    try:
        return run_impl(*args, **kwargs)
    except BaseException as error:
        workflow_ledger = context.get("workflow_ledger")
        run_root = context.get("run_root")
        terminal_record = None
        if (
            v3_enabled
            and run_root is not None
            and Path(run_root).is_dir()
            and MPI.COMM_WORLD.rank == 0
        ):
            try:
                terminal_record = _write_v3_partial_terminal(
                    Path(run_root),
                    phase=context.get("phase"),
                    source_identity=context.get("source_identity") or {},
                    captured=context.get("captured") or {},
                    error=error,
                )
            # Do not replace the original solver exception with a write failure.
            except BaseException as terminal_error:  # noqa: BLE001
                print(
                    "failed to persist V3 failure terminal after escaped error: "
                    f"{type(terminal_error).__name__}: {terminal_error}",
                    file=sys.stderr,
                    flush=True,
                )
        if v3_enabled and workflow_ledger is not None:
            try:
                failure_facts = {
                    "previous_stage": workflow_ledger.last_stage,
                    "exception_type": type(error).__name__,
                    "exception_message": str(error),
                }
                if terminal_record is not None:
                    failure_facts["terminal_reference"] = terminal_record
                workflow_ledger.marker(
                    "task43_v3_a1_failed",
                    failure_facts,
                    allow_stop=True,
                )
            # Do not replace the original solver exception with a ledger failure.
            except BaseException as ledger_error:  # noqa: BLE001
                print(
                    "failed to persist V3 A1 workflow failure marker: "
                    f"{type(ledger_error).__name__}: {ledger_error}",
                    file=sys.stderr,
                    flush=True,
                )
        raise


def _run(*args, **kwargs) -> dict[str, Any]:
    return _run_with_v3_failure_terminal(_run_impl, *args, **kwargs)


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
    parser.add_argument("--v2-diagnostic-phase", choices=("A1_q", "A1_R"))
    parser.add_argument("--v2-contract", type=Path)
    parser.add_argument("--v2-contract-sha256")
    parser.add_argument("--v2-reference-run-root", type=Path)
    parser.add_argument(
        "--v3-failure-evidence",
        action="store_true",
        help="persist V3 primary-before-extra evidence and explicit partial terminal status",
    )
    parser.add_argument("--v3-contract", type=Path)
    parser.add_argument("--v3-plan", type=Path)
    parser.add_argument(
        "--direct-factor-backend", choices=("default", "mumps"), default="default",
        help="use the existing direct LU backend; default preserves prior configuration",
    )
    parser.add_argument(
        "--same-lu-tightening",
        action="store_true",
        help=(
            "for the frozen 180-cell current only, perform one residual correction "
            "with the already configured KSP and save a diagnostic field/modal comparison"
        ),
    )
    parser.add_argument(
        "--same-lu-solve-residual-correction",
        action="store_true",
        help=(
            "for a variable-p candidate, apply one opt-in correction with the "
            "already factored KSP before field recovery and official R/T"
        ),
    )
    args = parser.parse_args(argv)
    comm = MPI.COMM_WORLD
    expected_size, kind = _CASES[args.case]
    is_current = args.case == _CURRENT_CASE
    is_candidate = args.case == _ROUND1_CANDIDATE_CASE
    is_native = kind == "native_p3"
    is_mpi2 = args.case == "empty_h_active_p3_mpi2"
    v2_diagnostic = args.v2_diagnostic_phase is not None
    if args.v3_failure_evidence and not v2_diagnostic:
        parser.error("--v3-failure-evidence requires --v2-diagnostic-phase")
    if args.v3_failure_evidence:
        if (
            args.v2_diagnostic_phase != "A1_q"
            or not is_candidate
            or args.v3_contract is None
            or args.v3_plan is None
        ):
            parser.error(
                "V3 is fixed to A1_q attempt 2 and requires --v3-contract and --v3-plan"
            )
        if _V3_CONTRACT_SHA256 is None or _V3_PLAN_SHA256 is None:
            parser.error("V3 contract bytes are not frozen in this source revision")
        contract_path = _REPOSITORY_ROOT / _V3_CONTRACT_REL
        plan_path = _REPOSITORY_ROOT / _V3_PLAN_REL
        if (
            args.v3_contract.resolve() != contract_path.resolve()
            or args.v3_plan.resolve() != plan_path.resolve()
        ):
            parser.error("V3 CLI paths differ from the frozen repository files")
        if (
            _sha256_file(contract_path) != _V3_CONTRACT_SHA256
            or _sha256_file(plan_path) != _V3_PLAN_SHA256
        ):
            parser.error("V3 contract or plan bytes differ from their frozen hashes")
        try:
            with contract_path.open("r", encoding="utf-8") as handle:
                v3_contract = json.load(handle)
            _validate_v3_a1_entry_contract(v3_contract)
            _validate_v3_consumed_formal_attempts(v3_contract, _REPOSITORY_ROOT)
            _require_v3_watchdog_worker_identity()
        except (OSError, json.JSONDecodeError, RuntimeError, TypeError, ValueError) as exc:
            parser.error(f"V3 A1 frozen contract is invalid: {exc}")
    elif args.v3_contract is not None or args.v3_plan is not None:
        parser.error("V3 contract paths require --v3-failure-evidence")
    if args.same_lu_tightening and not (
        is_current or (is_candidate and v2_diagnostic)
    ):
        parser.error(
            "--same-lu-tightening is only valid for the frozen current or V2 A1 endpoint"
        )
    if args.same_lu_solve_residual_correction and not is_candidate:
        parser.error(
            "--same-lu-solve-residual-correction is only valid for a candidate case"
        )
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
    v2_arguments = (
        args.v2_contract,
        args.v2_contract_sha256,
        args.v2_reference_run_root,
    )
    if v2_diagnostic:
        if not is_candidate:
            parser.error("V2 A1 diagnostics require --case round1_candidate_mpi1")
        if args.candidate_parent_selection_record is None:
            parser.error("V2 A1 diagnostics require the frozen R10 accepted-parent selection")
        if args.candidate_id != "round10_p_up":
            parser.error("V2 A1 diagnostics require --candidate-id round10_p_up")
        if args.v2_contract is None or args.v2_contract_sha256 is None:
            parser.error("V2 A1 diagnostics require --v2-contract and its exact SHA256")
        if (
            not args.same_lu_tightening
            or not args.same_lu_solve_residual_correction
            or args.direct_factor_backend != "mumps"
        ):
            parser.error(
                "V2 A1 requires normal and one extra same-LU correction plus MUMPS"
            )
        if args.reference_run_root is not None or args.parallel_reference_run_root is not None:
            parser.error("V2 A1 uses its explicit V2 reference path, not V1 references")
        if args.v2_diagnostic_phase == "A1_q" and args.v2_reference_run_root is not None:
            parser.error("A1_q binds the frozen original R10 baseline, not a run path")
        if args.v2_diagnostic_phase == "A1_R" and args.v2_reference_run_root is None:
            parser.error("A1_R requires --v2-reference-run-root from A1_q")
    elif any(value is not None for value in v2_arguments):
        parser.error("V2 contract/reference arguments require --v2-diagnostic-phase")
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
        direct_factor_backend=args.direct_factor_backend,
        same_lu_tightening_enabled=args.same_lu_tightening,
        candidate_plan_path=args.candidate_plan,
        candidate_id=args.candidate_id,
        candidate_parent_run_root=args.candidate_parent_run_root,
        candidate_tightening_run_root=args.candidate_tightening_run_root,
        candidate_marking_record=args.candidate_marking_record,
        candidate_acceptance_contract=args.candidate_acceptance_contract,
        candidate_parent_selection_record=args.candidate_parent_selection_record,
        same_lu_solve_residual_correction_enabled=(
            args.same_lu_solve_residual_correction
        ),
        v2_diagnostic_phase=args.v2_diagnostic_phase,
        v2_contract_path=args.v2_contract,
        v2_contract_sha256=args.v2_contract_sha256,
        v2_reference_run_root=args.v2_reference_run_root,
        v3_failure_evidence_enabled=args.v3_failure_evidence,
        v3_contract_path=args.v3_contract,
        v3_contract_sha256=_V3_CONTRACT_SHA256 if args.v3_failure_evidence else None,
        v3_plan_path=args.v3_plan,
        v3_plan_sha256=_V3_PLAN_SHA256 if args.v3_failure_evidence else None,
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
