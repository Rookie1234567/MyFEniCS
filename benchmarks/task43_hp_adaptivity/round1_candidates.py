"""Build and audit the first Task43 p/h candidates without solving Maxwell."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from mpi4py import MPI

from benchmarks.task43_hp_adaptivity.h100_anchor import _h100_config
from benchmarks.task43_hp_adaptivity.profile import (
    TASK43_VARIABLE_P_ACTIVE_FE_DOF_GATE_POLICY,
)
from src.adaptivity.stage4_local_h import (
    _build_forest,
    build_stage4_local_h_mesh_data,
    build_stage4_local_h_reduction_authority,
    stage4_local_h_refinement_plan_payload,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARENT_RUN = ROOT / "benchmarks/artifacts/task43/current_180/attempt1/run"
DEFAULT_TIGHT_RUN = (
    ROOT / "benchmarks/artifacts/task43/current_180/tightening_attempt2/run"
)
DEFAULT_MARKING = (
    ROOT
    / "benchmarks/artifacts/task43/current_180/tightening_marking_q8/attempt2/tightening_marking_q8.json"
)
DEFAULT_ACCEPTANCE = (
    ROOT / "docs/task43_hp_adaptivity/outcomes/records/round1_acceptance_contract_v1.json"
)
DEFAULT_OUTPUT = ROOT / "benchmarks/artifacts/task43/round1_candidates/attempt2"
PARENT_INDEPENDENT_FE_DOFS = 15120


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _load_parent_identity(
    parent_run: Path,
    tightening_run: Path,
    marking_path: Path,
    acceptance_path: Path,
) -> tuple[dict[str, Any], dict[int, tuple[float, ...]]]:
    parent_record_path = parent_run / "task43_initial180_current_record.json"
    parent_storage_path = parent_run / "recovered_solution_storage.npz"
    parent_record = json.loads(parent_record_path.read_text(encoding="utf-8"))
    parent_record_sha = _sha256_file(parent_record_path)
    parent_storage_sha = _sha256_file(parent_storage_path)
    if parent_record.get("gates", {}).get("pass") is not True:
        raise ValueError("frozen p3 parent did not pass its hard numerical gates")
    if parent_record.get("recovered_solution_storage", {}).get("sha256") != parent_storage_sha:
        raise ValueError("frozen p3 storage differs from its recorded hash")

    tightening_record_path = tightening_run / "task43_initial180_current_record.json"
    tightening_record = json.loads(tightening_record_path.read_text(encoding="utf-8"))
    acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    marking = json.loads(marking_path.read_text(encoding="utf-8"))
    if acceptance.get("schema") != "task43.round1-acceptance-contract.v1":
        raise ValueError("round-one acceptance contract schema is unknown")
    if acceptance.get("git_head_at_freeze") != "6389b9f5e0a2151014021ad25618637cfd948c72":
        raise ValueError("round-one acceptance contract was frozen on another source HEAD")
    evidence = acceptance["evidence"]
    for key, actual in (
        ("solver_tightening", _sha256_file(tightening_record_path)),
        ("tightening_marking", _sha256_file(marking_path)),
    ):
        if evidence[key]["sha256"] != actual:
            raise ValueError(f"acceptance contract {key} hash mismatch")
    identities = marking["identities"]
    if identities["initial_record_sha256"] != parent_record_sha:
        raise ValueError("Dörfler evidence is not bound to the frozen p3 parent record")
    if identities["initial_storage_sha256"] != parent_storage_sha:
        raise ValueError("Dörfler evidence is not bound to the frozen p3 parent storage")
    tightened_storage = tightening_record["same_lu_tightening"][
        "recovered_solution_storage"
    ]["sha256"]
    if identities["tightened_storage_sha256"] != tightened_storage:
        raise ValueError("tightened field differs from the recorded Dörfler perturbation")
    if not marking["identities"]["tightening_hard_quality_gates_pass"]:
        raise ValueError("Dörfler marking did not pass the tightening hard gates")
    dorfler = marking["dorfler"]
    if dorfler["theta"] != 0.5 or dorfler["initial_marked_global_cell_ids"] != dorfler[
        "tightened_marked_global_cell_ids"
    ]:
        raise ValueError("frozen parent/tightened Dörfler sets are not identical")
    marked_ids = [int(value) for value in dorfler["tightened_marked_global_cell_ids"]]
    if len(marked_ids) != 46 or len(set(marked_ids)) != 46:
        raise ValueError("the frozen first-round set must contain 46 distinct cells")

    with np.load(parent_storage_path, allow_pickle=False) as storage:
        cell_ids = np.asarray(storage["mesh_owned_cell_global_ids"], dtype=np.int64)
        geometry_dofmap = np.asarray(storage["mesh_geometry_dofmap"], dtype=np.int64)
        coordinates = np.asarray(storage["mesh_geometry_coordinates_nm"], dtype=np.float64)
    if len(cell_ids) != 180 or len(set(map(int, cell_ids))) != 180:
        raise ValueError("frozen parent geometry is not the serial 180-cell mesh")
    boxes_by_id: dict[int, tuple[float, ...]] = {}
    for index, global_id in enumerate(cell_ids):
        vertices = coordinates[geometry_dofmap[index], :3]
        lower = vertices.min(axis=0)
        upper = vertices.max(axis=0)
        box = tuple(float(value) for value in (*lower, *upper))
        boxes_by_id[int(global_id)] = box
    if not set(marked_ids) <= set(boxes_by_id):
        raise ValueError("Dörfler set contains an ID absent from parent mesh storage")

    identities_out = {
        "parent_case_record": str(parent_record_path),
        "parent_case_record_sha256": parent_record_sha,
        "parent_recovered_storage": str(parent_storage_path),
        "parent_recovered_storage_sha256": parent_storage_sha,
        "tightening_record": str(tightening_record_path),
        "tightening_record_sha256": _sha256_file(tightening_record_path),
        "tightening_recovered_storage_sha256": tightened_storage,
        "marking_record": str(marking_path),
        "marking_record_sha256": _sha256_file(marking_path),
        "acceptance_contract": str(acceptance_path),
        "acceptance_contract_sha256": _sha256_file(acceptance_path),
        "marked_global_cell_ids": marked_ids,
        "marked_global_cell_ids_sha256": _sha256_json(marked_ids),
        "marked_count": len(marked_ids),
        "theta": float(dorfler["theta"]),
        "captured_fraction": float(dorfler["tightened_marking"]["captured_fraction"]),
    }
    return identities_out, boxes_by_id


def _build_candidate_plan(
    cfg,
    *,
    action: str,
    candidate_id: str,
    marked_boxes: tuple[tuple[float, ...], ...],
    parent_identity: dict[str, Any],
    comm_size: int,
) -> dict[str, Any]:
    if action == "p_up":
        h_marked_boxes: tuple[tuple[float, ...], ...] = ()
        forest = _build_forest(
            cfg,
            comm_size=comm_size,
            marked_root_boxes=(),
            maximum_level=1,
            allow_no_refinement=True,
        )
        selected = set(marked_boxes)
        degrees = {leaf.box: (4 if leaf.box in selected else 3) for leaf in forest.leaves}
        provenance_action = "p_up_p4_on_frozen_theta05_dorfler_cells"
    elif action == "h_refine":
        h_marked_boxes = marked_boxes
        forest = _build_forest(
            cfg,
            comm_size=comm_size,
            marked_root_boxes=h_marked_boxes,
            maximum_level=1,
            allow_no_refinement=False,
        )
        degrees = {leaf.box: 3 for leaf in forest.leaves}
        provenance_action = "one_level_h_split_frozen_theta05_dorfler_roots_p3"
    else:
        raise ValueError(f"unknown first-round action {action!r}")
    provenance = {
        "task43_candidate_id": candidate_id,
        "task43_action": provenance_action,
        "parent_case_record_sha256": parent_identity["parent_case_record_sha256"],
        "parent_recovered_storage_sha256": parent_identity[
            "parent_recovered_storage_sha256"
        ],
        "tightening_record_sha256": parent_identity["tightening_record_sha256"],
        "marking_record_sha256": parent_identity["marking_record_sha256"],
        "acceptance_contract_sha256": parent_identity[
            "acceptance_contract_sha256"
        ],
        "marked_global_cell_ids": parent_identity["marked_global_cell_ids"],
        "marked_global_cell_ids_sha256": parent_identity[
            "marked_global_cell_ids_sha256"
        ],
        "marked_root_box_count": len(h_marked_boxes),
        "p_up_root_box_count": len(marked_boxes) if action == "p_up" else 0,
        "selection_reference_role": "Y6_1",
        "holdout_excluded": "Y5_1",
        "final_6x10x6_p6_control_excluded_from_selection": True,
    }
    plan = stage4_local_h_refinement_plan_payload(
        cfg,
        h_marked_boxes,
        comm_size=comm_size,
        trace_degree=3,
        cell_interior_degree=6,
        provenance=provenance,
        cell_interior_degree_overrides=degrees,
        variable_trace_from_cell_degrees=True,
        allow_no_refinement=action == "p_up",
    )
    plan["task43_candidate"] = {
        "candidate_id": candidate_id,
        "action": action,
        "action_description": provenance_action,
        "provenance": provenance,
    }
    return plan


def _audit_plan(
    cfg,
    *,
    plan_path: Path,
    candidate_id: str,
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    mesh_data = build_stage4_local_h_mesh_data(cfg, plan_path, comm=comm)
    authority = build_stage4_local_h_reduction_authority(
        mesh_data.local_h_context,
        phase_x=complex(cfg.floquet_phase_x),
        phase_y=complex(cfg.floquet_phase_y),
        active_fe_dof_gate_policy=TASK43_VARIABLE_P_ACTIVE_FE_DOF_GATE_POLICY,
    )
    audit = dict(authority.audit)
    degree_audit = dict(authority.degree_plan.audit)
    physical_audit = dict(audit["physical_trace"])
    context_audit = dict(mesh_data.local_h_context.audit)
    degrees = {
        str(key): int(value)
        for key, value in degree_audit["cell_degree_counts"].items()
        if int(value) > 0
    }
    cell_interior_rows = int(authority.degree_plan.entity_map.active_cell_interior_rows)
    independent_trace_rows = int(authority.trace_constraints.independent_trace_rows)
    independent_dofs = independent_trace_rows + cell_interior_rows
    root_count = int(context_audit["root_cell_count"])
    leaf_count = int(context_audit["leaf_cell_count"])
    actual_h_splits = (leaf_count - root_count) // 7
    if root_count + 7 * actual_h_splits != leaf_count:
        raise RuntimeError("one-level octree leaf count does not encode whole-cell splits")
    requested_h_splits = len(plan["marked_root_boxes"])
    distinct_trace_degrees = sorted(
        {int(value) for value in physical_audit["trace_degree_values"]}
    )
    return {
        "schema": "task43.round1-candidate-plan-audit.v1",
        "classification": "mesh_and_entity_closure_only_no_pde_solve",
        "candidate_id": candidate_id,
        "plan_path": str(plan_path),
        "plan_sha256": _sha256_file(plan_path),
        "action": plan["task43_candidate"]["action"],
        "parent_identity": plan["task43_candidate"]["provenance"],
        "forest": {
            "root_cell_count": root_count,
            "actual_leaf_cell_count": leaf_count,
            "axis_partition_interval_product_is_not_leaf_count": True,
            "requested_h_root_splits": requested_h_splits,
            "actual_one_level_root_splits": actual_h_splits,
            "forced_closure_h_splits": actual_h_splits - requested_h_splits,
            "hanging_patch_count": int(context_audit["hanging_patch_count"]),
            "closure_split_counts": dict(
                context_audit["forest"]["closure_split_counts"]
            ),
            "leaf_catalog_sha256": str(
                context_audit["forest"]["leaf_catalog_sha256"]
            ),
        },
        "degrees": {
            "cell_interior_histogram": degrees,
            "actual_p4_cell_count": degrees.get("p4", 0),
            "distinct_physical_trace_degrees": distinct_trace_degrees,
            "entity_degree_plan_sha256": str(degree_audit["cell_degree_plan_sha256"]),
            "entity_map_sha256": str(
                degree_audit["runtime_global_entity_degree_sha256"]
            ),
            "minimum_trace_degree": int(degree_audit["minimum_trace_degree"]),
            "maximum_trace_degree": max(distinct_trace_degrees),
            "degree_plan_pass": bool(degree_audit["pass"]),
            "entity_constraints_pass": bool(audit["pass"]),
        },
        "dofs": {
            "parent_independent_fe_dofs": PARENT_INDEPENDENT_FE_DOFS,
            "independent_trace_rows": independent_trace_rows,
            "active_cell_interior_rows": cell_interior_rows,
            "independent_active_fe_dofs": independent_dofs,
            "added_independent_fe_dofs": independent_dofs - PARENT_INDEPENDENT_FE_DOFS,
            "raw_broken_active_fe_dofs_before_hanging_floquet_constraints": int(
                audit["raw_broken_active_fe_dofs"]
            ),
            "active_fe_dof_gate_policy": audit["active_fe_dof_gate_policy"],
            "active_fe_dof_gate_limit": audit["active_fe_dof_gate_limit"],
            "active_fe_dof_gate_pass": bool(audit["active_fe_dof_gate_pass"]),
        },
        "actual_geometry": {
            "global_cells": leaf_count,
            "mesh_box_catalog_sha256": str(
                degree_audit["mesh_cell_box_catalog_sha256"]
            ),
            "mesh_cell_type": str(mesh_data.mesh_cell_type_resolved),
            "axis_union_interval_counts": [
                len(np.unique(mesh_data.mesh.geometry.x[np.unique(mesh_data.mesh.geometry.dofmap), axis])) - 1
                for axis in range(3)
            ],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-run", type=Path, default=DEFAULT_PARENT_RUN)
    parser.add_argument("--tightening-run", type=Path, default=DEFAULT_TIGHT_RUN)
    parser.add_argument("--marking-record", type=Path, default=DEFAULT_MARKING)
    parser.add_argument("--acceptance-contract", type=Path, default=DEFAULT_ACCEPTANCE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    comm = MPI.COMM_WORLD
    if comm.size != 1:
        parser.error("candidate plan audit is qualified here for MPI1 only")
    parent_identity, boxes_by_id = _load_parent_identity(
        args.parent_run.resolve(),
        args.tightening_run.resolve(),
        args.marking_record.resolve(),
        args.acceptance_contract.resolve(),
    )
    marked_ids = parent_identity["marked_global_cell_ids"]
    marked_boxes = tuple(boxes_by_id[int(global_id)] for global_id in marked_ids)
    cfg = _h100_config(
        kind="empty_h_active_p3",
        case_name="task43_round1_candidate_plan_initial180_mpi1",
        geometry_profile="initial_180",
    )
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=False)
    plans_dir = output_root / "plans"
    plans_dir.mkdir()
    candidates = (
        ("round1_p_up_p4_46", "p_up"),
        ("round1_h_split_46_p3", "h_refine"),
    )
    summaries = []
    for candidate_id, action in candidates:
        plan = _build_candidate_plan(
            cfg,
            action=action,
            candidate_id=candidate_id,
            marked_boxes=marked_boxes,
            parent_identity=parent_identity,
            comm_size=comm.size,
        )
        plan_path = plans_dir / f"{candidate_id}.json"
        plan_path.write_text(
            json.dumps(plan, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        summaries.append(
            _audit_plan(
                cfg,
                plan_path=plan_path,
                candidate_id=candidate_id,
                comm=comm,
            )
        )
    record = {
        "schema": "task43.round1-candidate-plan-audit-bundle.v1",
        "classification": "mesh_and_entity_closure_only_no_pde_solve",
        "parent_identity": parent_identity,
        "candidates": summaries,
    }
    record_path = output_root / "plan_audit.json"
    record_path.write_text(
        json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(record, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
