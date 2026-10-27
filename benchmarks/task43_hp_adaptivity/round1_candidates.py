"""Build and audit the first Task43 p/h candidates without solving Maxwell."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from functools import wraps
from pathlib import Path
from collections.abc import Callable, Mapping
from typing import Any

import numpy as np
from dolfinx import fem
from mpi4py import MPI

from benchmarks.task43_hp_adaptivity.candidate_records import (
    load_accepted_parent_artifacts,
)
from benchmarks.task43_hp_adaptivity.candidate_checkpoints import write_atomic_json
from benchmarks.task43_hp_adaptivity import compare_initial_to_references as base
from benchmarks.task43_hp_adaptivity.compare_initial_to_references import (
    _actual_mesh_identity,
)
from benchmarks.task43_hp_adaptivity import compare_round1_candidate as candidate_comparator
from benchmarks.task43_hp_adaptivity.reference_restore import (
    _configure_historical_direct_route,
    _load_inventory_entry,
)
from benchmarks.task43_hp_adaptivity.compare_v2_endpoints import (
    R13_MODE_KEYS,
    _validated_rows,
)
from benchmarks.task43_hp_adaptivity.h100_anchor import (
    _check_v11_runtime_envelope,
    _h100_config,
    _load_v11_primary_contract,
    _require_v11_watchdog_worker_identity,
    _v11_input_snapshot,
    _v11_source_snapshot,
    _load_v12_execution_recovery_manifest,
    _resolve_v12_p2_source,
)
from benchmarks.task43_hp_adaptivity.profile import (
    TASK43_VARIABLE_P_ACTIVE_FE_DOF_GATE_POLICY,
)
from src.adaptivity.exact_sequence_variable_p import (
    HexaEntityDegreeMap,
    build_variable_p_reference_space,
)
from src.adaptivity.hcurl_broken_trace_graph import (
    raise_cell_degrees_for_p_up,
)
from src.adaptivity.physical_g_error import dorfler_mark_physical_g
from src.adaptivity.stage4_local_h import (
    _build_forest,
    build_stage4_local_h_mesh_data,
    build_stage4_local_h_reduction_authority,
    stage4_local_h_refinement_plan_payload,
)
from src.adaptivity.variable_p_transfer import (
    audit_full_active_trace_constraints,
    build_variable_p_global_transfer,
    extract_active_full_from_p6_field,
    recover_active_full_to_p6_field,
)
from src.solvers.common_3d_solve import _create_nedelec_space
from src.runners.physical_intermediate import WorkflowLedger
from src.io.input_validation import simulation_config_3d_from_normalized

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
V11_SEED8_IDENTITY = {
    "global_cell_id": 8,
    "lower_nm": [16.5, 5.0, -10.0],
    "upper_nm": [33.5, 10.0, 0.0],
    "parent_degree": 5,
}
PARENT_INDEPENDENT_FE_DOFS = 15120
_V11_P2_INPUT_ROLES = {
    "R9_authority_plan",
    "R9_candidate_plan_copy",
    "R9_candidate_storage",
    "R9_candidate_record",
    "R9_selection_transition",
    "R9_comparison",
    "R8_ancestry_selection",
    "frozen_acceptance_contract",
    "frozen_comparison_contract",
    "reference_calibration",
    "A2_saved_modal_orders",
    "A2_primary_packet",
    "A2_q8_saved_sample",
    "A2_q10_saved_sample",
    "A2_saved_absorption",
    "historical_joint_comparison",
    "historical_joint_q8",
    "historical_joint_q10",
    "Y6_1_modal_orders",
    "Y6_1_resolved_config",
    "Y6_1_restore_inventory",
}


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



def _load_accepted_parent_state(
    selection_path: Path,
    *,
    cfg,
    comm_size: int,
) -> dict[str, Any]:
    """Load only a hash-bound, already accepted candidate as next-round parent."""

    accepted_parent = load_accepted_parent_artifacts(
        selection_path,
        artifact_root=ROOT,
        acceptance_contract_path=DEFAULT_ACCEPTANCE,
    )
    selection_path = accepted_parent["selection_path"]
    selected = accepted_parent["selected"]
    candidate_id = accepted_parent["candidate_id"]
    run_root = accepted_parent["run_root"]
    record_path = accepted_parent["record_path"]
    storage_path = accepted_parent["storage_path"]
    plan_path = accepted_parent["plan_path"]
    comparison_path = accepted_parent["comparison_path"]
    hashes = accepted_parent["hashes"]
    selection_sha = accepted_parent["selection_sha256"]
    comparison = accepted_parent["comparison"]
    record = accepted_parent["record"]
    storage_identity = record.get("recovered_solution_storage", {})
    plan = accepted_parent["plan"]
    candidate = plan.get("task43_candidate", {})
    if candidate.get("candidate_id") != candidate_id:
        raise ValueError("accepted parent run plan identifies another candidate")
    provenance = candidate.get("provenance", {})
    parent_selection_sha = record.get("candidate_identity", {}).get(
        "accepted_parent_selection_sha256"
    )
    if parent_selection_sha:
        ancestry_path = Path(
            str(record["candidate_identity"].get("parent_selection_record_path", ""))
        ).resolve()
        if (
            not ancestry_path.is_file()
            or _sha256_file(ancestry_path) != parent_selection_sha
            or provenance.get("accepted_parent_selection_sha256") != parent_selection_sha
        ):
            raise ValueError("accepted parent candidate ancestry identity is inconsistent")
    elif provenance.get("accepted_parent_selection_sha256"):
        raise ValueError("plan records accepted ancestry absent from the solve identity")
    old_roots = tuple(
        tuple(map(float, (*row["lower"], *row["upper"])))
        for row in plan.get("marked_root_boxes", [])
    )
    forest = _build_forest(
        cfg,
        comm_size=comm_size,
        marked_root_boxes=old_roots,
        maximum_level=int(plan.get("maximum_level", 1)),
        allow_no_refinement=not old_roots,
    )
    expected = plan.get("expected_forest", {})
    if (
        len(forest.root_boxes) != int(expected.get("root_cell_count", -1))
        or len(forest.leaves) != int(expected.get("leaf_cell_count", -1))
        or forest.audit["leaf_catalog_sha256"]
        != expected.get("leaf_catalog_sha256")
    ):
        raise ValueError("accepted parent plan does not rebuild its actual leaf forest")
    degree_rows = plan.get("cell_interior_degrees")
    if not isinstance(degree_rows, list) or len(degree_rows) != len(forest.leaves):
        raise ValueError("accepted parent plan lacks a full actual-leaf degree map")
    degree_by_box: dict[tuple[float, ...], int] = {}
    for row in degree_rows:
        box = tuple(map(float, (*row["lower"], *row["upper"])))
        if box in degree_by_box:
            raise ValueError("accepted parent plan repeats a leaf degree box")
        degree_by_box[box] = int(row["degree"])
    leaf_boxes = {cell.box for cell in forest.leaves}
    if set(degree_by_box) != leaf_boxes:
        raise ValueError("accepted parent degree map differs from actual leaf boxes")

    with np.load(storage_path, allow_pickle=False) as storage:
        cell_ids = np.asarray(storage["mesh_owned_cell_global_ids"], dtype=np.int64)
        geometry_dofmap = np.asarray(storage["mesh_geometry_dofmap"], dtype=np.int64)
        coordinates = np.asarray(
            storage["mesh_geometry_coordinates_nm"], dtype=np.float64
        )
    boxes_by_id: dict[int, tuple[float, ...]] = {}
    for index, global_id in enumerate(cell_ids):
        vertices = coordinates[geometry_dofmap[index], :3]
        lower = vertices.min(axis=0)
        upper = vertices.max(axis=0)
        box = tuple(float(value) for value in (*lower, *upper))
        if box not in degree_by_box:
            raise ValueError("accepted parent storage cell is absent from its plan")
        boxes_by_id[int(global_id)] = box
    if (
        len(boxes_by_id) != len(cell_ids)
        or len(cell_ids) != len(forest.leaves)
        or set(boxes_by_id.values()) != leaf_boxes
    ):
        raise ValueError(
            "accepted parent storage geometry does not cover actual leaves"
        )

    contribution = comparison.get("candidate_leaf_G_contributions", {})
    contribution_ids = np.asarray(
        contribution.get("cell_global_ids", []), dtype=np.int64
    )
    contribution_values = np.asarray(
        contribution.get("cell_g_error_squared", []), dtype=np.float64
    )
    if (
        contribution_ids.shape != cell_ids.shape
        or contribution_values.shape != cell_ids.shape
        or len(set(map(int, contribution_ids))) != len(contribution_ids)
        or set(map(int, contribution_ids)) != set(boxes_by_id)
        or not np.isfinite(contribution_values).all()
        or np.any(contribution_values < 0.0)
    ):
        raise ValueError(
            "accepted parent comparison lacks complete nonnegative leaf G data"
        )
    marked_ids, marking = dorfler_mark_physical_g(
        contribution_ids,
        contribution_values,
        theta=0.5,
    )
    if marked_ids.size == 0:
        raise ValueError("accepted parent has no positive physical G contribution to mark")
    marked_boxes = tuple(boxes_by_id[int(value)] for value in marked_ids)
    parent_trace_rows = int(storage_identity["active_trace_rows"])
    parent_interior_rows = int(storage_identity["active_cell_interior_rows"])
    parent_dofs = parent_trace_rows + parent_interior_rows
    if parent_dofs != int(selected["independent_FE_dofs"]):
        raise ValueError(
            "accepted selection independent FE DoF differs from parent storage"
        )
    return {
        "selection_path": str(selection_path),
        "selection_sha256": selection_sha,
        "selected_candidate_id": candidate_id,
        "parent_run_root": str(run_root),
        "parent_record_path": str(record_path),
        "parent_record_sha256": hashes["record_sha256"],
        "parent_storage_path": str(storage_path),
        "parent_storage_sha256": hashes["storage_sha256"],
        "parent_plan_path": str(plan_path),
        "parent_plan_sha256": hashes["plan_sha256"],
        "parent_comparison_path": str(comparison_path),
        "parent_comparison_sha256": hashes["comparison_record_sha256"],
        "parent_marked_root_boxes": old_roots,
        "parent_forest": forest,
        "parent_degree_by_box": degree_by_box,
        "parent_boxes_by_global_id": boxes_by_id,
        "marked_global_cell_ids": marked_ids.tolist(),
        "marked_boxes": marked_boxes,
        "marking": marking,
        "parent_independent_fe_dofs": parent_dofs,
        "parent_record": record,
        "parent_plan": plan,
        "parent_comparison": comparison,
        "parent_provenance": provenance,
    }


def _build_next_round_plan(
    cfg,
    *,
    action: str,
    candidate_id: str,
    parent: dict[str, Any],
    comm_size: int,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    parent_forest = parent["parent_forest"]
    parent_degrees = parent["parent_degree_by_box"]
    marked_boxes = tuple(parent["marked_boxes"])
    old_roots = tuple(parent["parent_marked_root_boxes"])
    provenance = {
        "task43_candidate_id": candidate_id,
        "task43_action": action,
        "accepted_parent_selection_record_path": parent["selection_path"],
        "accepted_parent_selection_sha256": parent["selection_sha256"],
        "parent_run_root": parent["parent_run_root"],
        "parent_candidate_id": parent["selected_candidate_id"],
        "parent_case_record_sha256": parent["parent_record_sha256"],
        "parent_recovered_storage_sha256": parent["parent_storage_sha256"],
        "parent_plan_sha256": parent["parent_plan_sha256"],
        "parent_comparison_record_path": parent["parent_comparison_path"],
        "parent_comparison_sha256": parent["parent_comparison_sha256"],
        "acceptance_contract_sha256": _sha256_file(DEFAULT_ACCEPTANCE),
        "marked_global_cell_ids": parent["marked_global_cell_ids"],
        "marked_global_cell_ids_sha256": _sha256_json(parent["marked_global_cell_ids"]),
        "marking_theta": 0.5,
        "marked_global_cell_ids_source": (
            "accepted_parent_candidate_leaf_G_contributions"
        ),
        "selection_reference_role": "Y6_1",
        "holdout_excluded": "Y5_1",
        "final_6x10x6_p6_control_excluded_from_selection": True,
    }
    if action == "p_up":
        candidate_forest = parent_forest
        degree_by_box, closure = raise_cell_degrees_for_p_up(
            candidate_forest,
            parent_degrees,
            marked_boxes,
        )
        if closure["all_marked_cells_saturated"]:
            return None, {
                "candidate_id": candidate_id,
                "action": action,
                "status": "not_run_all_dorfler_marks_saturated_at_p6",
                "closure_audit": dict(closure),
            }
        h_root_boxes = old_roots
        allow_empty = not h_root_boxes
        closure = dict(closure)
        provenance["p_up_closure"] = closure
    elif action == "h_refine":
        roots = set(parent_forest.root_boxes)
        already_refined = set(old_roots)
        level_one_marks = {box for box in marked_boxes if box not in roots}
        new_root_marks = {
            box for box in marked_boxes if box in roots and box not in already_refined
        }
        if level_one_marks:
            return None, {
                "candidate_id": candidate_id,
                "action": action,
                "status": "not_run_level2_qualification_required_for_full_dorfler_set",
                "marked_level_one_child_count": len(level_one_marks),
                "marked_unrefined_root_count": len(new_root_marks),
                "full_dorfler_set_omitted": False,
            }
        h_root_boxes = tuple(sorted(already_refined | new_root_marks))
        if not new_root_marks:
            return None, {
                "candidate_id": candidate_id,
                "action": action,
                "status": "not_run_no_new_unrefined_root_mark",
                "marked_level_one_child_count": 0,
                "parent_marked_root_count": len(old_roots),
                "full_dorfler_set_omitted": False,
            }
        candidate_forest = _build_forest(
            cfg,
            comm_size=comm_size,
            marked_root_boxes=h_root_boxes,
            maximum_level=1,
            allow_no_refinement=False,
        )
        degree_by_box = {}
        degree_by_root = {
            cell.box: parent_degrees[cell.box]
            for cell in parent_forest.leaves
            if cell.key.level == 0
        }
        for cell in candidate_forest.leaves:
            degree = parent_degrees.get(cell.box)
            if degree is None:
                degree = degree_by_root[candidate_forest.root_boxes[cell.key.root]]
            degree_by_box[cell.box] = degree
        if set(degree_by_box) != {cell.box for cell in candidate_forest.leaves}:
            raise RuntimeError(
                "h candidate did not inherit a degree for every actual leaf"
            )
        provenance["h_split_source"] = (
            "parent_level1_roots_union_new_marked_unrefined_roots"
        )
        provenance["marked_level_one_child_count_not_split"] = len(level_one_marks)
        provenance["new_root_split_count"] = len(new_root_marks)
        closure = {"inherited_cell_degree_map": True}
        allow_empty = False
    else:
        raise ValueError(f"unsupported adaptive action {action!r}")

    plan = stage4_local_h_refinement_plan_payload(
        cfg,
        h_root_boxes,
        comm_size=comm_size,
        trace_degree=3,
        cell_interior_degree=6,
        provenance=provenance,
        cell_interior_degree_overrides=degree_by_box,
        variable_trace_from_cell_degrees=True,
        allow_no_refinement=allow_empty,
    )
    plan["task43_candidate"] = {
        "candidate_id": candidate_id,
        "action": action,
        "action_description": (
            "accepted_parent_marked_leaf_p_up_with_minimal_periodic_closure"
            if action == "p_up"
            else "accepted_parent_marked_unrefined_root_h_split_with_degree_inheritance"
        ),
        "provenance": provenance,
    }
    plan["task43_candidate"]["provenance"]["closure_or_inheritance"] = dict(closure)
    return plan, {
        "candidate_id": candidate_id,
        "action": action,
        "status": "plan_built",
        "marked_leaf_count": len(marked_boxes),
        "marked_level_one_child_count": int(
            provenance.get("marked_level_one_child_count_not_split", 0)
        ),
        "closure_or_inheritance": closure,
    }


def _build_v11_seed8_plan(
    cfg,
    *,
    parent: dict[str, Any],
    comm_size: int,
    contract: dict[str, Any],
    recovery_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the sole V11 h candidate from the predeclared accepted-R9 root."""

    phase = contract["phases"]["P4"]
    seed = dict(phase["seed"])
    if seed != {**V11_SEED8_IDENTITY, "split": seed.get("split"), "maximum_level": 1}:
        raise ValueError("V11 seed identity differs from the audited global-cell-8 request")
    if parent["selected_candidate_id"] != "round9_p_up":
        raise ValueError("V11 h candidate requires the accepted round9_p_up parent")
    if int(parent["parent_independent_fe_dofs"]) != int(
        phase["required_fe_bounds"]["parent_fe_dofs"]
    ):
        raise ValueError("accepted R9 independent FE count differs from frozen 110472")
    if parent["parent_marked_root_boxes"]:
        raise ValueError("V11 seed8 request requires an unrefined accepted R9 root mesh")

    seed_box = tuple(map(float, (*seed["lower_nm"], *seed["upper_nm"])))
    actual_box = parent["parent_boxes_by_global_id"].get(
        int(seed["global_cell_id"])
    )
    if actual_box != seed_box:
        raise ValueError(
            "predeclared V11 global cell 8 geometry differs from accepted R9 storage"
        )
    if seed_box not in parent["parent_forest"].root_boxes:
        raise ValueError("V11 global cell 8 is not an unrefined root in the accepted R9 forest")
    parent_degree = parent["parent_degree_by_box"].get(seed_box)
    if int(parent_degree or -1) != int(seed["parent_degree"]):
        raise ValueError("V11 seed8 accepted-parent interior degree is not p5")

    fixed_parent = dict(parent)
    fixed_parent["marked_global_cell_ids"] = [int(seed["global_cell_id"])]
    fixed_parent["marked_boxes"] = (seed_box,)
    plan, status = _build_next_round_plan(
        cfg,
        action="h_refine",
        candidate_id="v11_r9_h8",
        parent=fixed_parent,
        comm_size=comm_size,
    )
    if plan is None or status.get("status") != "plan_built":
        raise ValueError(f"V11 predeclared seed8 h plan could not be built: {status}")
    provenance = plan["task43_candidate"]["provenance"]
    provenance.pop("marking_theta", None)
    provenance.pop("marked_global_cell_ids_sha256", None)
    provenance["marked_global_cell_ids_source"] = "v11_predeclared_seed8"
    provenance["v11_seed"] = seed
    provenance["seed_geometry_audit_sha256"] = next(
        item["sha256"]
        for item in contract["inputs"]
        if item["role"] == "seed_geometry_audit"
    )
    provenance["full_dorfer_set_not_used"] = True
    if recovery_binding is not None:
        provenance["v12_recovery_binding"] = dict(recovery_binding)
    plan["task43_candidate"]["action_description"] = (
        "one_predeclared_seed8_global_root_split_with_degree_inheritance"
    )
    return plan

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


def _v12_observed_call(output_root: Path, stage: str, function, *args, **kwargs):
    """Observe existing calls without changing their results, keys or caches.

    The journal is append-only. A BEGIN without END/ERROR means
    IN_PROGRESS_AT_STOP, never a zero-duration completed call. Process-tree CPU
    and sampling costs remain in the unchanged watchdog resource stream.
    """
    journal = output_root / "authority_observations.jsonl"
    calls: dict[str, int] = {}
    sequence = 0

    def describe(value):
        if value is None or isinstance(value, (str, bool, int, float)):
            return value
        if isinstance(value, complex):
            return {"complex": [value.real, value.imag]}
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, np.generic):
            return describe(value.item())
        if isinstance(value, np.ndarray):
            return {"shape": list(value.shape), "dtype": str(value.dtype),
                    "sha256": hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()}
        if isinstance(value, HexaEntityDegreeMap):
            return value.to_dict()
        if isinstance(value, (tuple, list)):
            return [describe(item) for item in value]
        if isinstance(value, Mapping):
            return {
                str(key): (
                    {"description": "existing hash-bound historical payload; see input manifest",
                     "keys": sorted(map(str, item)) if isinstance(item, Mapping) else None}
                    if key in {"parent_record", "parent_plan", "parent_comparison"}
                    else describe(item)
                )
                for key, item in value.items()
            }
        result = {"type": type(value).__module__ + "." + type(value).__qualname__}
        for name in ("degree", "family", "cell_type", "dim", "floquet_phase_x",
                     "floquet_phase_y", "stage4_local_h_refinement_plan"):
            if hasattr(value, name):
                item = getattr(value, name)
                result[name] = describe(item) if isinstance(item, (str, int, float, complex, type(None))) else str(item)
        if hasattr(value, "leaves") and hasattr(value, "root_boxes"):
            result.update(root_count=len(value.root_boxes), leaf_count=len(value.leaves))
        return result

    def emit(event):
        event.update(stage=stage, monotonic=time.monotonic(), worker_cpu_seconds=time.process_time(),
                     worker_pid=os.getpid())
        with journal.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, sort_keys=True, allow_nan=False) + "\n")

    def summarize_owned_cells(result):
        if not hasattr(result, "owned_cells"):
            return {}
        returned_cells = tuple(result.owned_cells)
        entity_map = getattr(result, "entity_map", None)
        if entity_map is not None and hasattr(entity_map, "owned_cells"):
            degree_cells = tuple(entity_map.owned_cells)
            result_kind = "cell_trace_constraint_map"
            degree_source = "result.entity_map.owned_cells"
        elif all(hasattr(cell, "degree_map") for cell in returned_cells):
            degree_cells = returned_cells
            result_kind = "entity_map"
            degree_source = "result.owned_cells"
        else:
            degree_cells = ()
            result_kind = "owned_cell_result_without_entity_degree_maps"
            degree_source = None
        degree_maps = [
            json.dumps(cell.degree_map.to_dict(), sort_keys=True)
            for cell in degree_cells
        ]
        return {
            "result_kind": result_kind,
            "result_owned_cell_count": len(returned_cells),
            "result_owned_cell_type": (
                type(returned_cells[0]).__module__
                + "."
                + type(returned_cells[0]).__qualname__
                if returned_cells
                else None
            ),
            "degree_map_source": degree_source,
            "degree_map_count": len(degree_maps),
            "degree_map_multiplicity": {
                key: degree_maps.count(key) for key in sorted(set(degree_maps))
            },
        }

    def emit_observer_error(call_id, name, started, error, classification):
        try:
            emit(
                {
                    "event": "OBSERVER_ERROR",
                    "call_id": call_id,
                    "function": name,
                    "wall_seconds": time.monotonic() - started,
                    "classification": classification,
                    "exception": type(error).__name__ + ": " + str(error),
                }
            )
        except BaseException as journal_error:
            error.add_note(
                "Task43 observer could not persist its error classification: "
                + type(journal_error).__name__
                + ": "
                + str(journal_error)
            )

    def wrap(original, name):
        @wraps(original)
        def observed(*positional, **keywords):
            nonlocal sequence
            sequence += 1
            call_id = sequence
            arguments = {"args": describe(positional), "kwargs": describe(keywords)}
            key = name + ":" + json.dumps(arguments, sort_keys=True)
            calls[key] = calls.get(key, 0) + 1
            cache = getattr(original, "cache_info", None)
            before = dict(cache()._asdict()) if cache else None
            started = time.monotonic()
            emit({"event": "BEGIN", "call_id": call_id, "function": name,
                  "arguments": arguments, "key_occurrence": calls[key], "cache_before": before,
                  "unreturned_status": "IN_PROGRESS_AT_STOP"})
            try:
                result = original(*positional, **keywords)
            except BaseException as error:
                try:
                    emit({"event": "ERROR", "call_id": call_id, "function": name,
                          "wall_seconds": time.monotonic() - started,
                          "exception": type(error).__name__ + ": " + str(error)})
                except BaseException as journal_error:
                    error.add_note(
                        "Task43 observer could not persist the original function error: "
                        + type(journal_error).__name__
                        + ": "
                        + str(journal_error)
                    )
                raise
            try:
                detail = summarize_owned_cells(result)
            except BaseException as error:
                emit_observer_error(
                    call_id,
                    name,
                    started,
                    error,
                    "observer_return_summary_failed",
                )
                raise
            try:
                emit({"event": "END", "call_id": call_id, "function": name,
                      "wall_seconds": time.monotonic() - started,
                      "cache_after": dict(cache()._asdict()) if cache else None, "completed_work": detail})
            except BaseException as error:
                emit_observer_error(
                    call_id,
                    name,
                    started,
                    error,
                    "observer_journal_persistence_failed",
                )
                raise
            return result
        if hasattr(original, "cache_info"):
            observed.cache_info = original.cache_info
        if hasattr(original, "cache_parameters"):
            observed.cache_parameters = original.cache_parameters
        return observed

    names = {
        "_build_forest", "build_stage4_local_h_mesh_data", "build_stage4_local_h_reduction_authority",
        "build_broken_hexa_trace_constraint_authority", "build_broken_hexa_entity_degree_arrays",
        "build_variable_p_global_entity_map", "build_broken_hexa_cell_trace_constraint_map",
        "build_variable_p_reference_space", "_create_active_element", "_from_p6_interpolation",
        "_to_p6_interpolation", "_discrete_gradient", "_orientation_audit",
        "compute_interpolation_operator", "build_oriented_hanging_face_reference_catalog",
        "build_hanging_face_reference_pair", "build_oriented_quad_child_trace_restriction",
    }
    module_names = (
        __name__, "basix", "src.adaptivity.stage4_local_h",
        "src.adaptivity.exact_sequence_variable_p", "src.adaptivity.hcurl_broken_trace_graph",
        "src.adaptivity.hcurl_broken_cell_trace", "src.adaptivity.hcurl_hanging_trace",
        "src.adaptivity.variable_p_entity_map", "src.adaptivity.variable_p_degree_plan",
    )
    replacements = []
    wrappers = {}
    for module_name in module_names:
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for name in names:
            original = getattr(module, name, None)
            if not callable(original):
                continue
            if original not in wrappers:
                wrappers[original] = wrap(original, original.__module__ + "." + original.__name__)
            replacements.append((module, name, original, wrappers[original]))
    try:
        for module, name, original, observed in replacements:
            setattr(module, name, observed)
        result = wrap(function, stage)(*args, **kwargs)
        write_atomic_json(output_root / (stage + "_observation_complete.json"), {
            "stage": stage, "status": "COMPLETED", "journal_path": str(journal),
            "observed_calls": sequence, "unique_function_argument_keys": len(calls),
            "repeated_calls": sum(count - 1 for count in calls.values()),
            "cache_policy_changed": False, "numerical_results_changed": False,
            "cost_scope": "Nested call times overlap; do not sum as workflow wall time.",
        })
        return result
    finally:
        for module, name, original, observed in reversed(replacements):
            setattr(module, name, original)


def _audit_plan(
    cfg,
    *,
    plan_path: Path,
    candidate_id: str,
    comm: MPI.Intracomm,
    parent_independent_fe_dofs: int = PARENT_INDEPENDENT_FE_DOFS,
    parent_root_degree_by_box: Mapping[tuple[float, ...], int] | None = None,
    parent_storage_path: Path | None = None,
    parent_storage_sha256: str | None = None,
    audit_parent_transfer: bool = True,
) -> dict[str, Any]:
    audit_started = time.perf_counter()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    reference_cache_before = dict(
        build_variable_p_reference_space.cache_info()._asdict()
    )
    authority_started = time.perf_counter()
    mesh_data = build_stage4_local_h_mesh_data(cfg, plan_path, comm=comm)
    authority = build_stage4_local_h_reduction_authority(
        mesh_data.local_h_context,
        phase_x=complex(cfg.floquet_phase_x),
        phase_y=complex(cfg.floquet_phase_y),
        active_fe_dof_gate_policy=TASK43_VARIABLE_P_ACTIVE_FE_DOF_GATE_POLICY,
    )
    authority_wall_seconds = time.perf_counter() - authority_started
    reference_cache_after = dict(
        build_variable_p_reference_space.cache_info()._asdict()
    )
    local_degree_maps = {
        cell.degree_map for cell in authority.degree_plan.entity_map.owned_cells
    }
    local_maps_with_uniform_p6 = local_degree_maps | {
        HexaEntityDegreeMap.uniform(6)
    }
    local_reference_workset_size = len(local_maps_with_uniform_p6)
    reference_cache_fits_local_workset = (
        reference_cache_after["maxsize"] is None
        or local_reference_workset_size <= reference_cache_after["maxsize"]
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
    forest = mesh_data.local_h_context.forest
    normalized_marked_boxes = {
        tuple(
            map(
                float,
                (*row["lower"], *row["upper"]),
            )
        )
        for row in plan["marked_root_boxes"]
    }
    requested_root_ids = [
        root_id
        for root_id, box in enumerate(forest.root_boxes)
        if tuple(map(float, box)) in normalized_marked_boxes
    ]
    if len(requested_root_ids) != len(normalized_marked_boxes):
        raise RuntimeError("candidate requests a box outside the actual root forest")
    actual_refined_root_ids = sorted(
        {int(cell.key.root) for cell in forest.leaves if cell.key.level > 0}
    )
    forced_closure_root_ids = sorted(
        set(actual_refined_root_ids).difference(requested_root_ids)
    )
    actual_root_boxes = {
        root_id: [float(value) for value in box]
        for root_id, box in enumerate(forest.root_boxes)
    }
    degree_rows = plan.get("cell_interior_degrees", [])
    degree_by_box: dict[tuple[float, ...], int] = {}
    for row in degree_rows:
        box = tuple(map(float, (*row["lower"], *row["upper"])))
        if box in degree_by_box:
            raise RuntimeError("candidate plan repeats an actual-leaf degree box")
        degree_by_box[box] = int(row["degree"])
    actual_leaf_boxes = {cell.box for cell in forest.leaves}
    if set(degree_by_box) != actual_leaf_boxes:
        raise RuntimeError("candidate plan degree rows differ from actual local-h leaves")
    normalized_parent_degrees = (
        {
            tuple(map(float, box)): int(degree)
            for box, degree in parent_root_degree_by_box.items()
        }
        if parent_root_degree_by_box is not None
        else None
    )
    if normalized_parent_degrees is not None and set(normalized_parent_degrees) != {
        tuple(map(float, box)) for box in forest.root_boxes
    }:
        raise RuntimeError("parent degree map does not cover the actual root forest")
    leaf_parent_degree_inheritance: dict[str, dict[str, int]] = {}
    leaf_inheritance_by_root: dict[int, dict[str, Any]] = {}
    for cell in forest.leaves:
        root_id = int(cell.key.root)
        degree = degree_by_box.get(tuple(map(float, cell.box)))
        if degree is None:
            raise RuntimeError("actual local-h leaf lacks a saved interior degree")
        if normalized_parent_degrees is not None:
            root_box = tuple(map(float, forest.root_boxes[root_id]))
            parent_degree = normalized_parent_degrees[root_box]
            if degree != parent_degree:
                raise RuntimeError(
                    "candidate actual leaf does not inherit its parent root degree: "
                    f"root={root_id}, candidate={degree}, parent={parent_degree}"
                )
            inherited = leaf_parent_degree_inheritance.setdefault(
                str(root_id), {"parent_degree": parent_degree, "leaf_count": 0}
            )
            if inherited["parent_degree"] != parent_degree:
                raise RuntimeError("candidate root has inconsistent parent degrees")
            inherited["leaf_count"] += 1
        entry = leaf_inheritance_by_root.setdefault(
            root_id,
            {"leaf_count": 0, "degree_counts": {}},
        )
        entry["leaf_count"] += 1
        degree_key = f"p{degree}"
        entry["degree_counts"][degree_key] = (
            int(entry["degree_counts"].get(degree_key, 0)) + 1
        )
    seed = plan["task43_candidate"].get("provenance", {}).get("v11_seed")
    seed_box = (
        tuple(map(float, (*seed["lower_nm"], *seed["upper_nm"])))
        if isinstance(seed, Mapping) and "lower_nm" in seed and "upper_nm" in seed
        else None
    )
    matching_seed_roots = (
        [
            root_id
            for root_id, box in enumerate(forest.root_boxes)
            if tuple(map(float, box)) == seed_box
        ]
        if seed_box is not None
        else []
    )
    if seed_box is not None and len(matching_seed_roots) != 1:
        raise RuntimeError("V11 seed geometry does not map to exactly one forest root index")
    seed_forest_root_index = matching_seed_roots[0] if matching_seed_roots else None
    seed_mesh_global_cell_id = (
        int(seed["global_cell_id"])
        if isinstance(seed, Mapping) and "global_cell_id" in seed
        else None
    )
    seed_parent_degree = int(seed["parent_degree"]) if isinstance(seed, Mapping) and "parent_degree" in seed else None
    seed_child_degrees = (
        sorted(
            {
                degree_by_box[tuple(map(float, cell.box))]
                for cell in forest.leaves
                if int(cell.key.root) == seed_forest_root_index
            }
        )
        if seed_forest_root_index is not None
        else []
    )
    constraint_audit = dict(authority.audit["trace_constraints"])
    entity_map = authority.degree_plan.entity_map
    space_authority_detail = {
        "requested_root_ids": requested_root_ids,
        "requested_root_boxes": {
            str(root_id): actual_root_boxes[root_id]
            for root_id in requested_root_ids
        },
        "actual_refined_root_ids": actual_refined_root_ids,
        "forced_closure_root_ids": forced_closure_root_ids,
        "forced_closure_root_boxes": {
            str(root_id): actual_root_boxes[root_id]
            for root_id in forced_closure_root_ids
        },
        "forced_closure_root_degrees": {
            str(root_id): (
                normalized_parent_degrees[
                    tuple(map(float, forest.root_boxes[root_id]))
                ]
                if normalized_parent_degrees is not None
                else None
            )
            for root_id in forced_closure_root_ids
        },
        "root_id_namespace": "forest_root_index; not the parent mesh global-cell ID",
        "requested_root_mesh_global_cell_ids": (
            [seed_mesh_global_cell_id]
            if seed_forest_root_index in requested_root_ids
            else []
        ),
        "seed_mesh_global_cell_id": seed_mesh_global_cell_id,
        "seed_forest_root_index": seed_forest_root_index,
        "seed_root_box_nm": list(seed_box) if seed_box is not None else None,
        "leaf_interior_degree_histogram": degrees,
        "leaf_inheritance_by_root": {
            str(root_id): entry
            for root_id, entry in sorted(leaf_inheritance_by_root.items())
        },
        "leaf_parent_degree_inheritance_by_root": leaf_parent_degree_inheritance,
        "all_actual_leaves_inherit_parent_degree": (
            (
                sum(
                    entry["leaf_count"]
                    for entry in leaf_parent_degree_inheritance.values()
                )
                == leaf_count
            )
            if normalized_parent_degrees is not None
            else None
        ),
        "seed_parent_degree": seed_parent_degree,
        "seed_child_degrees": seed_child_degrees,
        "seed_child_degree_inheritance_pass": (
            seed_parent_degree is None or seed_child_degrees == [seed_parent_degree]
        ),
        "independent_trace_rows": independent_trace_rows,
        "independent_cell_interior_rows": cell_interior_rows,
        "independent_fe_dofs": independent_dofs,
        "hanging_slave_rows": int(constraint_audit.get("hanging_slave_rows", 0)),
        "floquet_periodic_relations": {
            key: int(value)
            for key, value in constraint_audit.items()
            if key.startswith("periodic_") and isinstance(value, (int, np.integer))
        },
        "hanging_or_floquet_slave_rows_globally_numbered": bool(
            constraint_audit.get("hanging_or_floquet_slave_rows_globally_numbered", True)
        ),
        "p6_carrier": {
            "container_degree": int(plan["cell_interior_degree"]),
            "uniform_p6_global_rows": int(entity_map.uniform_p6_rows),
            "uniform_p6_trace_rows": int(entity_map.uniform_p6_trace_rows),
            "active_entity_rows": int(entity_map.active_rows),
            "inactive_p6_rows": int(entity_map.uniform_p6_rows - entity_map.active_rows),
            "full_p6_global_matrix_constructed": bool(
                entity_map.audit.get("full_p6_global_matrix_constructed", False)
            ),
        },
        "predicted_returned_trace_dtn_rows": independent_trace_rows + 612,
        "predicted_returned_trace_dtn_scope": "independent trace rows plus exactly 612 R13 modal rows",
    }
    transfer_audit = None
    if parent_storage_path is not None:
        if plan["task43_candidate"]["action"] != "p_up":
            raise ValueError(
                "same-mesh parent-to-candidate transfer is qualified only for p-up"
            )
        if comm.size != 1:
            raise ValueError("accepted-parent p transfer audit is serial-only")
        transfer_started = time.perf_counter()
        parent_storage_path = parent_storage_path.resolve()
        actual_storage_sha256 = _sha256_file(parent_storage_path)
        if (
            parent_storage_sha256 is None
            or actual_storage_sha256 != parent_storage_sha256
        ):
            raise ValueError("accepted parent storage SHA differs before transfer audit")
        if not audit_parent_transfer:
            transfer_audit = {
                "classification": "accepted-parent-to-candidate-space-transfer",
                "status": "not_run_direct_solve_does_not_use_initial_guess",
                "pass": None,
                "performed": False,
                "parent_storage_path": str(parent_storage_path),
                "parent_storage_sha256": actual_storage_sha256,
                "mesh_and_p6_dof_identity_pass": None,
                "cost_status": "not_incurred",
                "wall_seconds": None,
                "pde_solve_performed": False,
            }
    if parent_storage_path is not None and audit_parent_transfer:
        p6_space = _create_nedelec_space(mesh_data.mesh, cfg)
        actual_arrays = _actual_mesh_identity(mesh_data.mesh, p6_space)
        identity_to_storage = {
            "mesh_geometry_coordinates_nm": "mesh_geometry_coordinates_nm",
            "mesh_geometry_dofmap": "mesh_geometry_dofmap",
            "mesh_owned_cell_global_ids": "mesh_owned_cell_global_ids",
            "mesh_cell_vertex_dofmap": "mesh_cell_vertex_dofmap",
            "p6_function_space_cell_dofmap": "p6_function_space_dofmap",
            "p6_owned_global_dof_block_ids": "p6_owned_global_dof_block_ids",
            "p6_ghost_global_dof_block_ids": "p6_ghost_global_dof_block_ids",
        }
        with np.load(parent_storage_path, allow_pickle=False) as storage:
            for identity_key, storage_key in identity_to_storage.items():
                if not np.array_equal(actual_arrays[identity_key], storage[storage_key]):
                    raise ValueError(
                        "accepted parent p6 mesh/function identity differs from "
                        f"the rebuilt candidate: {identity_key}"
                    )
            parent_coefficients = np.asarray(
                storage["recovered_p6_local_coefficients"], dtype=np.complex128
            ).copy()
        parent_field = fem.Function(p6_space, name="accepted_parent_full_p6_field")
        if parent_field.x.array.shape != parent_coefficients.shape:
            raise ValueError("accepted parent p6 coefficient layout changed")
        parent_field.x.array[:] = parent_coefficients
        parent_field.x.scatter_forward()

        transfer = build_variable_p_global_transfer(
            authority.degree_plan.entity_map,
            p6_space,
        )
        candidate_active, extraction = extract_active_full_from_p6_field(
            transfer,
            parent_field,
        )
        trace_audit = audit_full_active_trace_constraints(
            candidate_active,
            authority.trace_constraints,
        )
        candidate_field, recovery = recover_active_full_to_p6_field(
            transfer,
            candidate_active,
        )
        local_scale = float(
            np.max(np.abs(parent_coefficients), initial=0.0)
        )
        relative_recovery_error = float(
            np.max(
                np.abs(
                    np.asarray(candidate_field.x.array, dtype=np.complex128)
                    - parent_coefficients
                ),
                initial=0.0,
            )
            / max(1.0, local_scale)
        )
        if relative_recovery_error > 5.0e-10:
            raise RuntimeError(
                "accepted-parent p transfer does not preserve the p6 carrier: "
                f"relative_error={relative_recovery_error:.6e}"
            )
        transfer_audit = {
            "classification": "same_mesh_accepted_parent_to_candidate_p_transfer",
            "status": "pass",
            "pass": True,
            "parent_storage_path": str(parent_storage_path),
            "parent_storage_sha256": actual_storage_sha256,
            "mesh_and_p6_dof_identity_pass": True,
            "active_extraction": extraction,
            "full_active_trace_constraint_audit": trace_audit,
            "p6_recovery": recovery,
            "parent_to_candidate_p6_relative_error": relative_recovery_error,
            "parent_to_candidate_p6_tolerance": 5.0e-10,
            "candidate_independent_active_fe_dofs": independent_dofs,
            "unique_cell_degree_map_count": extraction[
                "unique_cell_degree_maps"
            ],
            "reference_space_cache_delta": extraction[
                "reference_space_cache_delta"
            ],
            "matrix_allocated": False,
            "pde_solve_performed": False,
            "wall_seconds": time.perf_counter() - transfer_started,
        }
    elif parent_storage_path is None and plan["task43_candidate"]["provenance"].get(
        "accepted_parent_selection_sha256"
    ):
        transfer_audit = {
            "classification": "accepted-parent-to-candidate-space-transfer",
            "status": "not_run_cross_mesh_transfer_not_qualified",
            "pass": None,
            "pde_solve_performed": False,
        }
    return {
        "schema": "task43.round1-candidate-plan-audit.v1",
        "classification": "mesh_and_entity_closure_only_no_pde_solve",
        "candidate_id": candidate_id,
        "plan_and_authority_wall_seconds": authority_wall_seconds,
        "total_audit_wall_seconds": time.perf_counter() - audit_started,
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
        "reference_space_cache_capacity_audit": {
            "scope": "per_rank_local_owned_cells",
            "rank": int(comm.rank),
            "mpi_size": int(comm.size),
            "local_unique_cell_degree_map_count": len(local_degree_maps),
            "local_maps_including_uniform_p6": local_reference_workset_size,
            "build_cache_maxsize": reference_cache_after["maxsize"],
            "capacity_contains_local_workset": bool(
                reference_cache_fits_local_workset
            ),
            "cache_before_authority": reference_cache_before,
            "cache_after_authority": reference_cache_after,
            "cache_delta_authority": {
                key: int(reference_cache_after[key] - reference_cache_before[key])
                for key in ("hits", "misses")
            },
        },
        "dofs": {
            "parent_independent_fe_dofs": int(parent_independent_fe_dofs),
            "independent_trace_rows": independent_trace_rows,
            "active_cell_interior_rows": cell_interior_rows,
            "independent_active_fe_dofs": independent_dofs,
            "added_independent_fe_dofs": independent_dofs - int(parent_independent_fe_dofs),
            "raw_broken_active_fe_dofs_before_hanging_floquet_constraints": int(
                audit["raw_broken_active_fe_dofs"]
            ),
            "active_fe_dof_gate_policy": audit["active_fe_dof_gate_policy"],
            "active_fe_dof_gate_limit": audit["active_fe_dof_gate_limit"],
            "active_fe_dof_gate_pass": bool(audit["active_fe_dof_gate_pass"]),
        },
        "accepted_parent_transfer_audit": transfer_audit,
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
        "space_authority_detail": space_authority_detail,
    }


_V11_A2_CHECKPOINT_STAGES = ("raw", "modal", "q8", "q10")


def _v11_saved_a2_failure_response(
    error: BaseException,
    checkpoint_refs: Mapping[str, Mapping[str, Any]],
    *,
    failure_stage: str | None = None,
    failure_origin: str = "saved_data_recomputation",
) -> dict[str, Any]:
    completed = set(checkpoint_refs)
    if failure_stage is None:
        failure_stage = next(
            (stage for stage in _V11_A2_CHECKPOINT_STAGES if stage not in completed),
            "response_assembly",
        )
    statuses = {
        stage: (
            "CHECKPOINTED"
            if stage in completed
            else "FAILED"
            if stage == failure_stage
            else "NOT_REACHED"
        )
        for stage in _V11_A2_CHECKPOINT_STAGES
    }
    return {
        "schema": "task43.v11.saved_a2_primary_q_response.v1",
        "status": "failed_saved_primary_read_or_recomputation",
        "pass": False,
        "error": f"{type(error).__name__}: {error}",
        "failure_stage": failure_stage,
        "failure_origin": failure_origin,
        "substage_statuses": statuses,
        "substage_checkpoint_refs": dict(checkpoint_refs),
        "historical_endpoint_status": "INCOMPLETE_NOT_QUALIFIED",
        "official_result": False,
        "passed": False,
        "extra_correction_status": "historical_failure_preserved_not_replayed",
        "selection_or_transition_authority": False,
        "continuation": False,
    }


def _v11_saved_a2_primary_q_response(
    contract: dict[str, Any],
    *,
    checkpoint_callback: Callable[[str, Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Recompute only the hash-bound A2 primary vectors and saved q8/q10 fields."""

    checkpoint_refs: dict[str, dict[str, Any]] = {}

    def checkpoint(stage: str, values: Mapping[str, Any]) -> None:
        if checkpoint_callback is None:
            return
        reference = checkpoint_callback(stage, values)
        if not isinstance(reference, Mapping) or not all(
            isinstance(reference.get(key), str) and reference[key]
            for key in ("path", "sha256")
        ):
            raise TypeError(f"V13 A2 {stage} checkpoint callback returned no path/hash")
        checkpoint_refs[stage] = dict(reference)

    def input_path(role: str) -> Path:
        matches = [item for item in contract["inputs"] if item["role"] == role]
        if len(matches) != 1:
            raise ValueError(f"V11 A2 audit requires exactly one {role} input")
        return (ROOT / matches[0]["path"]).resolve()

    def selected_npz(
        path: Path,
        names: set[str],
        *,
        require_embedded_identity: bool = True,
    ) -> tuple[dict[str, np.ndarray], dict[str, Any] | None]:
        with np.load(path, allow_pickle=False) as archive:
            missing = names.difference(archive.files)
            if missing or (
                require_embedded_identity
                and "__task43_record_json__" not in archive.files
            ):
                raise ValueError(
                    f"saved NPZ {path} is missing arrays or its embedded identity: {sorted(missing)}"
                )
            values = {name: np.asarray(archive[name]).copy() for name in names}
            identity = (
                json.loads(
                    np.asarray(archive["__task43_record_json__"], dtype=np.uint8).tobytes()
                )
                if "__task43_record_json__" in archive.files
                else None
            )
        return values, identity

    def array_identity(values: np.ndarray) -> dict[str, Any]:
        array = np.ascontiguousarray(values)
        digest = hashlib.sha256()
        digest.update(array.dtype.str.encode("ascii"))
        digest.update(json.dumps(list(array.shape)).encode("ascii"))
        digest.update(array.view(np.uint8))
        return {
            "dtype": array.dtype.str,
            "shape": list(array.shape),
            "sha256": digest.hexdigest(),
            "finite": bool(np.isfinite(array).all()),
        }

    def finite_vector(arrays: dict[str, np.ndarray], name: str, size: int) -> np.ndarray:
        value = np.asarray(arrays[name], dtype=np.complex128)
        if value.shape != (size,) or not np.isfinite(value).all():
            raise ValueError(f"saved A2 primary vector {name} must be finite with {size} rows")
        return value

    packet_path = input_path("A2_primary_packet")
    packet_names = {
        "primary_native_A6_effective_rhs",
        "primary_independent_A6_residual",
        "primary_zero_slave_carrier_residual",
        "primary_augmented_port_residual",
        "primary_returned_trace_dtn_rhs",
        "primary_returned_trace_dtn_solution",
        "primary_returned_trace_dtn_b_minus_Ax",
        "normal_correction_b_minus_Ax_snapshot_0",
        "normal_correction_b_minus_Ax_snapshot_1",
        "primary_full_physical_rhs",
        "primary_recovered_p6_storage",
    }
    raw, packet_identity = selected_npz(packet_path, packet_names)
    if (
        packet_identity.get("schema") != "task43.v3.a2_primary_before_extra.v1"
        or packet_identity.get("official_result") is not False
        or packet_identity.get("passed") is not False
    ):
        raise ValueError("historical A2 primary packet identity is not incomplete/nonofficial")
    identity = packet_identity.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("historical A2 primary packet lacks its saved identity")
    resolved_config_item = next(
        item for item in contract["inputs"] if item["role"] == "Y6_1_resolved_config"
    )
    resolved_config_path = (ROOT / resolved_config_item["path"]).resolve()
    if (
        identity.get("resolved_config_path") != str(resolved_config_path)
        or identity.get("resolved_config_sha256") != resolved_config_item["sha256"]
        or identity.get("resolved_config_sha256") != _sha256_file(resolved_config_path)
    ):
        raise ValueError("historical A2 packet resolved-config path/hash differs from Y6 identity")
    array_identities = packet_identity.get("arrays")
    if not isinstance(array_identities, dict):
        raise ValueError("historical A2 primary packet lacks raw array identities")
    vectors = {
        name: finite_vector(raw, name, 389832)
        for name in (
            "primary_native_A6_effective_rhs",
            "primary_independent_A6_residual",
            "primary_zero_slave_carrier_residual",
            "primary_full_physical_rhs",
            "primary_recovered_p6_storage",
        )
    }
    vectors["primary_augmented_port_residual"] = finite_vector(
        raw, "primary_augmented_port_residual", 612
    )
    for name in (
        "primary_returned_trace_dtn_rhs",
        "primary_returned_trace_dtn_solution",
        "primary_returned_trace_dtn_b_minus_Ax",
        "normal_correction_b_minus_Ax_snapshot_0",
        "normal_correction_b_minus_Ax_snapshot_1",
    ):
        vectors[name] = finite_vector(raw, name, 121572)
    if any(
        array_identities.get(name, {}).get("sha256")
        != array_identity(values)["sha256"]
        for name, values in raw.items()
    ):
        raise ValueError("historical A2 primary packet array bytes differ from embedded identities")
    norm = lambda value: float(np.linalg.norm(value))  # noqa: E731 - local scalar helper
    native_rhs_norm = norm(vectors["primary_native_A6_effective_rhs"])
    returned_rhs_norm = norm(vectors["primary_returned_trace_dtn_rhs"])
    if native_rhs_norm <= 0.0 or returned_rhs_norm <= 0.0:
        raise ValueError("historical A2 primary residual denominator is not positive")
    a6_relative = norm(vectors["primary_independent_A6_residual"]) / native_rhs_norm
    full_active_relative = math.hypot(
        norm(vectors["primary_zero_slave_carrier_residual"]),
        norm(vectors["primary_augmented_port_residual"]),
    ) / native_rhs_norm
    condensed_relative = (
        norm(vectors["primary_returned_trace_dtn_b_minus_Ax"]) / returned_rhs_norm
    )
    before_relative = (
        norm(vectors["normal_correction_b_minus_Ax_snapshot_0"]) / returned_rhs_norm
    )
    after_relative = (
        norm(vectors["normal_correction_b_minus_Ax_snapshot_1"]) / returned_rhs_norm
    )
    if not np.allclose(
        vectors["normal_correction_b_minus_Ax_snapshot_1"],
        vectors["primary_returned_trace_dtn_b_minus_Ax"],
        rtol=1.0e-12,
        atol=1.0e-24,
    ):
        raise ValueError("historical A2 normal snapshot 1 differs from returned raw residual")
    raw_gates = {
        "independent_A6_raw_relative_le_1e-8": bool(a6_relative <= 1.0e-8),
        "full_active_hypot_raw_relative_le_1e-8": bool(
            full_active_relative <= 1.0e-8
        ),
        "returned_condensed_raw_relative_le_1e-9": bool(
            condensed_relative <= 1.0e-9
        ),
        "normal_correction_raw_residual_strictly_decreased": bool(
            after_relative < before_relative
        ),
    }
    stored_residual_metrics = identity.get("primary_solver_residual_metrics_before_extra")
    if not isinstance(stored_residual_metrics, dict):
        raise ValueError("historical A2 packet lacks the recorded raw residual scalar identity")
    recomputed_metrics = {
        "condensed_b_minus_Ax_relative": condensed_relative,
        "independent_A6_relative": a6_relative,
        "full_active_zero_slave_carrier_plus_modal_port_euclidean_relative": full_active_relative,
    }
    scalar_identity_differences = {}
    stored_key_by_recomputed = {
        "condensed_b_minus_Ax_relative": "condensed_b_minus_Ax_relative",
        "independent_A6_relative": "independent_A6_relative",
        "full_active_zero_slave_carrier_plus_modal_port_euclidean_relative":
            "full_active_space_transformed_relative",
    }
    for name, value in recomputed_metrics.items():
        stored = float(stored_residual_metrics[stored_key_by_recomputed[name]])
        scalar_identity_differences[name] = abs(stored - value)
        if not np.isclose(stored, value, rtol=1.0e-12, atol=1.0e-24):
            raise ValueError(f"historical A2 recomputed {name} differs from its packet identity")
    raw_recomputation = {
        "packet_npz_sha256": _sha256_file(packet_path),
        "packet_embedded_identity": identity,
        "raw_vector_arrays": {
            name: array_identity(values) for name, values in raw.items()
        },
        "A6_relative_to_native_effective_rhs": a6_relative,
        "full_active_zero_slave_carrier_l2": norm(
            vectors["primary_zero_slave_carrier_residual"]
        ),
        "full_active_modal_port_l2": norm(vectors["primary_augmented_port_residual"]),
        "full_active_zero_slave_carrier_plus_modal_port_euclidean_relative_to_native_effective_rhs": full_active_relative,
        "returned_condensed_relative_to_returned_rhs": condensed_relative,
        "normal_correction_relative_history": [before_relative, after_relative],
        "stored_scalar_identity_absolute_differences": scalar_identity_differences,
        "scope": "native explicit full-active residual: zero-slave carrier and modal-port Euclidean components, normalized by native effective RHS; not a variable-p Gram metric norm; no operator application, resampling, material integration, or PDE solve",
        "historical_scalar_alias": {
            "packet_key": "full_active_space_transformed_relative",
            "recomputed_scope": "full_active_zero_slave_carrier_plus_modal_port_euclidean_relative",
        },
        "normal_raw_state_limitation": "legacy packet lacks separate normal RHS/solution vectors; verifies the returned RHS/solution/residual and two b-Ax snapshots only",
        "gates": raw_gates,
        "pass": all(raw_gates.values()),
    }
    checkpoint("raw", raw_recomputation)

    modal_path = input_path("A2_saved_modal_orders")
    mode_payload = json.loads(modal_path.read_text(encoding="utf-8"))
    modal_rows = _validated_rows(
        mode_payload, label="A2_saved_primary", expected=R13_MODE_KEYS
    )
    absorption_path = input_path("A2_saved_absorption")
    absorption = json.loads(absorption_path.read_text(encoding="utf-8"))
    a_volume = float(absorption["A_volume_total"])
    if not math.isfinite(a_volume):
        raise ValueError("saved A2 primary A_volume is not finite")
    region_total = sum(
        float(value["A_volume"])
        for value in absorption.get("regions", {}).values()
    )
    if not np.isclose(region_total, a_volume, rtol=2.0e-12, atol=1.0e-14):
        raise ValueError("saved A2 primary material-volume absorption does not sum to A_volume")
    mode_metrics = mode_payload["metrics"]
    a2_case = {
        "label": "A2_saved_primary",
        "mode_payload": mode_payload,
        "power": {
            "R_total": float(mode_metrics["R_total"]),
            "T_total": float(mode_metrics["T_total"]),
            "A_volume": a_volume,
            "R00_s": float(mode_metrics["R00_s"]),
            "R00_p": float(mode_metrics["R00_p"]),
            "R00_total": float(mode_metrics["R00_total"]),
        },
    }
    y6_inventory = _load_inventory_entry("Y6_1")
    y6_config = json.loads(resolved_config_path.read_text(encoding="utf-8"))
    historical_cfg = _configure_historical_direct_route(y6_config, y6_inventory)
    a2_operator_q = int(identity.get("operator_q", -1))
    a2_incident_port_q = int(identity.get("incident_port_q", -1))
    if (
        a2_operator_q != 19
        or a2_incident_port_q != 32
        or identity.get("mode_basis_scale_policy") is not None
    ):
        raise ValueError("saved A2 primary is not the bound historical unscaled q19/q32 route")
    # The resolved JSON is the original Y6 config (q15/q28). V3 records the
    # actual A2 per-run overrides in its primary identity; bind those overrides
    # explicitly while keeping its historical unscaled modal gauge.
    a2_cfg = historical_cfg
    a2_cfg.stage4_volume_quadrature_degree = a2_operator_q
    a2_cfg.stage4_incident_quadrature_degree = a2_incident_port_q
    a2_cfg.stage4_dtn_quadrature_degree = a2_incident_port_q
    y6_case = candidate_comparator._load_modal_case("Y6_1")
    y6_case = {**y6_case, "label": "Y6_1"}
    mode_physics = base._validate_mode_physics(
        {"Y6_1": y6_case, "A2_saved_primary": a2_case},
        labels=("Y6_1", "A2_saved_primary"),
    )
    # Existing mode-power helpers re-evaluate all 612 rows against the same
    # physical configuration before any saved observable is used.
    a2_case["cfg"] = a2_cfg
    y6_case["cfg"] = historical_cfg
    a2_case["record"] = {"power": {"A_volume_total": a_volume}}
    y6_case["record"] = y6_case.get("record", {})
    physical_rows = {
        "A2_saved_primary": candidate_comparator._post_selection_full_mode_physics(
            a2_case
        ),
        "Y6_1": candidate_comparator._post_selection_full_mode_physics(y6_case),
    }
    modal_comparison = base._modal_comparison(y6_case, a2_case)
    modal_thresholds = contract["quadrature_response_thresholds"]
    modal_gates = {
        f"aggregate_{name}_le_1e-6": bool(
            abs(float(value)) <= float(modal_thresholds["aggregate_absolute_max"])
        )
        for name, value in modal_comparison["power_absolute_differences"].items()
        if name not in {"R00_s", "R00_p"}
    }
    modal_gates["zero_order_s_p_and_each_channel_le_1e-7"] = bool(
        max(
            float(modal_comparison["power_absolute_differences"]["R00_s"]),
            float(modal_comparison["power_absolute_differences"]["R00_p"]),
            float(
                modal_comparison[
                    "maximum_individual_channel_power_ratio_absolute_difference"
                ]
            ),
        )
        <= float(modal_thresholds["zero_order_s_p_and_each_channel_power_absolute_max"])
    )
    modal_gates["four_boundary_amplitude_groups_le_1e-5"] = bool(
        all(
            float(item["relative_with_unit_incident_modal_floor"])
            <= float(
                modal_thresholds[
                    "four_boundary_amplitude_and_total_scattered_E_H_G_floor_normalized_max"
                ]
            )
            for item in modal_comparison["boundary_amplitude_groups"].values()
        )
    )
    modal_validation = {
        "row_physics": mode_physics,
        "physical_mode_power_reconstruction": physical_rows,
        "ordered_rows_checked": len(modal_rows),
        "actual_basis_gauge": "historical_unscaled_Task40_direct_route",
        "resolved_config_path": str(resolved_config_path),
        "resolved_config_sha256": resolved_config_item["sha256"],
        "A2_actual_quadrature_identity": {
            "volume_degree": a2_operator_q,
            "incident_and_port_degree": a2_incident_port_q,
            "source": "primary NPZ identity overrides the hash-bound original Y6 resolved config",
        },
        "modal_comparison_metrics": modal_comparison,
        "gates": modal_gates,
        "pass": all(modal_gates.values()),
        "A_volume": {
            "saved_value": a_volume,
            "material_region_sum": region_total,
            "reintegrated": False,
            "inferred_from_one_minus_R_minus_T": False,
            "historical_automatic_rule_reinterpreted_as_q19": False,
        },
    }
    checkpoint("modal", modal_validation)
    q_comparisons: dict[str, Any] = {}
    q_gates: dict[str, bool] = {}
    comparison_record = json.loads(input_path("historical_joint_comparison").read_text())
    for order in (8, 10):
        key = f"q{order}"
        saved_path = input_path(f"A2_q{order}_saved_sample")
        reference_path = input_path(f"historical_joint_q{order}")
        comparison_rule = comparison_record["quadrature"][key]
        if (
            Path(str(comparison_rule["sample_bundle"])).resolve() != reference_path
            or _sha256_file(reference_path) != comparison_rule["sample_bundle_sha256"]
        ):
            raise ValueError(f"historical {key} reference path/hash differs from its frozen record")
        saved, saved_identity = selected_npz(
            saved_path,
            {
                "points_nm",
                "weights_nm3",
                "E_total_code",
                "curl_E_total_code",
                "H_total_A_per_m",
            },
        )
        reference, _ = selected_npz(
            reference_path,
            {"points_nm", "weights_nm3", "Y6_1_E", "Y6_1_curl_E"},
            require_embedded_identity=False,
        )
        points = np.asarray(saved["points_nm"], dtype=np.float64)
        weights = np.asarray(saved["weights_nm3"], dtype=np.float64)
        if (
            points.ndim != 2
            or points.shape[1] != 3
            or weights.shape != (points.shape[0],)
            or not all(np.isfinite(array).all() for array in (*saved.values(), *reference.values()))
            or np.any(weights <= 0.0)
            or not np.array_equal(points, reference["points_nm"])
            or not np.array_equal(weights, reference["weights_nm3"])
            or abs(float(np.sum(weights, dtype=np.float64)) - 350000.0) > 1.0e-8
        ):
            raise ValueError(f"saved A2 and Y6 {key} point/weight identity or domain is invalid")
        if (
            saved_identity.get("identity", {}).get("primary_before_extra_npz_sha256")
            != _sha256_file(packet_path)
        ):
            raise ValueError(f"saved A2 {key} sample does not bind the primary NPZ")
        expected_h = (
            saved["curl_E_total_code"]
            * float(historical_cfg.magnetic_field_scale_A_per_m)
            / (1j * float(historical_cfg.k0) * complex(historical_cfg.mu_r))
        )
        if not np.allclose(
            saved["H_total_A_per_m"], expected_h, rtol=2.0e-12, atol=1.0e-14
        ):
            raise ValueError(f"saved A2 {key} H is inconsistent with curl(E)")
        field_metrics = base._field_metrics(
            {
                "E": reference["Y6_1_E"],
                "curl_E": reference["Y6_1_curl_E"],
            },
            {
                "E": saved["E_total_code"],
                "curl_E": saved["curl_E_total_code"],
            },
            points,
            weights,
            historical_cfg,
        )
        field_threshold = float(
            modal_thresholds[
                "four_boundary_amplitude_and_total_scattered_E_H_G_floor_normalized_max"
            ]
        )
        field_gate = {
            name: bool(
                float(field_metrics[name]["relative_to_reference_or_floor"])
                <= field_threshold
            )
            for name in (
                "E_total_code",
                "H_total_A_per_m",
                "E_scattered_code",
                "H_scattered_A_per_m",
            )
        }
        field_gate["G"] = bool(
            float(field_metrics["G"]["relative_with_incident_floor"])
            <= field_threshold
        )
        q_comparisons[key] = {
            "status": "measured_from_saved_arrays_no_resampling_or_integration",
            "sample_count": int(weights.size),
            "points_sha256": array_identity(points)["sha256"],
            "weights_sha256": array_identity(weights)["sha256"],
            "integrated_domain_volume_nm3": float(np.sum(weights, dtype=np.float64)),
            "A2_sample_npz_sha256": _sha256_file(saved_path),
            "Y6_sample_bundle_sha256": _sha256_file(reference_path),
            "field_metrics": field_metrics,
            "gates": field_gate,
            "pass": all(field_gate.values()),
        }
        q_gates.update({f"{key}_{name}": value for name, value in field_gate.items()})
        checkpoint(
            key,
            {
                "status": q_comparisons[key]["status"],
                "sample_count": q_comparisons[key]["sample_count"],
                "points_sha256": q_comparisons[key]["points_sha256"],
                "weights_sha256": q_comparisons[key]["weights_sha256"],
                "integrated_domain_volume_nm3": q_comparisons[key][
                    "integrated_domain_volume_nm3"
                ],
                "A2_sample_npz_sha256": q_comparisons[key]["A2_sample_npz_sha256"],
                "Y6_sample_bundle_sha256": q_comparisons[key][
                    "Y6_sample_bundle_sha256"
                ],
                "field_metrics": field_metrics,
                "gates": field_gate,
                "pass": q_comparisons[key]["pass"],
            },
        )

    all_gates = {
        **raw_gates,
        **modal_gates,
        **q_gates,
    }
    response = {
        "schema": "task43.v11.saved_a2_primary_q_response.v1",
        "status": "measured_limited_saved_primary_diagnostic",
        "historical_endpoint_status": "INCOMPLETE_NOT_QUALIFIED",
        "historical_endpoint_official_result": False,
        "historical_extra_correction_failure_preserved": True,
        "historical_extra_correction_status": "failure preserved; no extra replay or continuation",
        "packet_npz_sha256": _sha256_file(packet_path),
        "packet_embedded_identity": identity,
        "raw_vector_arrays": {
            name: array_identity(values) for name, values in raw.items()
        },
        "raw_vector_recomputation": raw_recomputation,
        "modal_physics_validation": modal_validation,
        "modal_comparison_vs_Y6_1": {
            "metrics": modal_comparison,
            "gates": modal_gates,
            "pass": all(modal_gates.values()),
        },
        "saved_field_comparisons_vs_Y6_1": q_comparisons,
        "all_gates": all_gates,
        "pass": all(value is True for value in all_gates.values()),
        "selection_or_transition_authority": False,
        "A_volume": modal_validation["A_volume"],
    }
    if checkpoint_callback is not None:
        response["substage_checkpoint_refs"] = dict(checkpoint_refs)
        response["substage_statuses"] = {
            stage: "CHECKPOINTED" for stage in _V11_A2_CHECKPOINT_STAGES
        }
    return response


def _v11_actual_space_gate(
    audit: Mapping[str, Any], *, parent_fe_dofs: int, fe_bounds: Mapping[str, Any]
) -> dict[str, Any]:
    """Apply the existing fixed-seed/closure and strict FE post-authority gates."""
    space_detail = audit["space_authority_detail"]
    expected_seed_box = [16.5, 5.0, -10.0, 33.5, 10.0, 0.0]
    seed_root_index = space_detail["seed_forest_root_index"]
    requested_roots = set(space_detail["requested_root_ids"])
    actual_roots = set(space_detail["actual_refined_root_ids"])
    forced_closure_roots = set(space_detail["forced_closure_root_ids"])
    if (
        len(space_detail["requested_root_ids"]) != 1
        or space_detail["requested_root_ids"] != [seed_root_index]
        or space_detail["requested_root_boxes"]
        != {str(seed_root_index): expected_seed_box}
        or space_detail["seed_root_box_nm"] != expected_seed_box
        or space_detail["seed_mesh_global_cell_id"] != 8
        or space_detail["requested_root_mesh_global_cell_ids"] != [8]
        or space_detail["root_id_namespace"]
        != "forest_root_index; not the parent mesh global-cell ID"
        or requested_roots.intersection(forced_closure_roots)
        or actual_roots != requested_roots.union(forced_closure_roots)
        or not space_detail["all_actual_leaves_inherit_parent_degree"]
        or space_detail["seed_parent_degree"] != 5
        or space_detail["seed_child_degrees"] != [5]
        or not space_detail["seed_child_degree_inheritance_pass"]
        or space_detail["predicted_returned_trace_dtn_rows"]
        != int(audit["dofs"]["independent_trace_rows"]) + 612
        or space_detail["hanging_or_floquet_slave_rows_globally_numbered"]
    ):
        raise RuntimeError("V11 P2 actual root/degree/Floquet/carrier authority differs")
    candidate_fe_dofs = int(audit["dofs"]["independent_active_fe_dofs"])
    minimum_exclusive = int(fe_bounds["parent_fe_dofs"])
    maximum_exclusive = int(fe_bounds["target_exclusive_upper"])
    gate = {
        "parent_independent_fe_dofs": parent_fe_dofs,
        "candidate_independent_fe_dofs": int(audit["dofs"]["independent_active_fe_dofs"]),
        "added_dofs": candidate_fe_dofs - parent_fe_dofs,
        "positive_added_dofs": candidate_fe_dofs - parent_fe_dofs > 0,
        "exclusive_upper_bound": maximum_exclusive,
        "below_exclusive_upper": candidate_fe_dofs < maximum_exclusive,
        "minimum_exclusive_lower_bound": minimum_exclusive,
        "maximum_exclusive_upper_bound": maximum_exclusive,
        "parent_matches_frozen_lower_bound": parent_fe_dofs == minimum_exclusive,
        "above_exclusive_lower_bound": candidate_fe_dofs > minimum_exclusive,
        "below_exclusive_upper_bound": candidate_fe_dofs < maximum_exclusive,
    }
    gate["pass"] = bool(
        gate["parent_matches_frozen_lower_bound"]
        and gate["above_exclusive_lower_bound"]
        and gate["below_exclusive_upper_bound"]
    )
    return gate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-run", type=Path, default=DEFAULT_PARENT_RUN)
    parser.add_argument("--tightening-run", type=Path, default=DEFAULT_TIGHT_RUN)
    parser.add_argument("--marking-record", type=Path, default=DEFAULT_MARKING)
    parser.add_argument("--acceptance-contract", type=Path, default=DEFAULT_ACCEPTANCE)
    parser.add_argument("--accepted-parent-selection-record", type=Path)
    parser.add_argument("--primary-diagnostic-contract", type=Path)
    parser.add_argument("--execution-recovery-manifest", type=Path)
    parser.add_argument(
        "--skip-parent-transfer",
        action="store_true",
        help="skip the accepted-parent p transfer audit unused by direct solves; keep actual space authority",
    )
    parser.add_argument("--round-id", default="round1")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    program_started = time.perf_counter()
    program_started_unix_seconds = time.time()
    comm = MPI.COMM_WORLD
    if comm.size != 1:
        parser.error("candidate plan audit is qualified here for MPI1 only")
    if args.skip_parent_transfer and args.accepted_parent_selection_record is None:
        parser.error("--skip-parent-transfer requires --accepted-parent-selection-record")
    v11_contract = None
    v11_plan_path = None
    v11_parent = None
    v11_plan = None
    v11_runtime_environment = None
    v11_worker_identity = None
    v11_source_before = None
    v11_inputs_before = None
    v11_ledger = None
    v11_a2_response = None
    v12_recovery = None
    v12_recovery_binding = None
    if args.primary_diagnostic_contract is not None:
        if args.accepted_parent_selection_record is None:
            parser.error("V11 P2 requires the frozen accepted-R9 selection record")
        if args.round_id != "round1" or args.skip_parent_transfer:
            parser.error("V11 P2 is a fixed seed8 space audit and rejects legacy plan options")
        try:
            v11_contract, v11_contract_sha256 = _load_v11_primary_contract(
                args.primary_diagnostic_contract
            )
        except (OSError, json.JSONDecodeError, RuntimeError, TypeError, ValueError) as exc:
            parser.error(f"V11 P2 contract is invalid: {exc}")
        if args.execution_recovery_manifest is None:
            parser.error("V11 P2 requires --execution-recovery-manifest")
        try:
            v12_recovery = _load_v12_execution_recovery_manifest(
                args.execution_recovery_manifest,
                contract_sha256=v11_contract_sha256,
            )
            attempt_root_text = os.environ.get("TASK43_V11_ATTEMPT_ROOT")
            if not attempt_root_text:
                raise ValueError(
                    "TASK43_V11_ATTEMPT_ROOT must explicitly select D1 or P2R"
                )
            v12_source = _resolve_v12_p2_source(
                v12_recovery,
                attempt_root=Path(attempt_root_text),
            )
        except (OSError, json.JSONDecodeError, RuntimeError, TypeError, ValueError) as exc:
            parser.error(f"V12 P2 recovery binding is invalid: {exc}")
        v11_plan_path = Path(v12_source["plan_output_path"])
        v11_output_root = Path(v12_source["output_root"])
        v12_recovery_binding = {
            "manifest_path": v12_recovery["manifest_path"],
            "manifest_sha256": v12_recovery["manifest_sha256"],
            "contract_sha256": v11_contract_sha256,
            "p2_source_id": v12_source["p2_source_id"],
            "support_root": v12_source["support_root"],
            "output_root": v12_source["output_root"],
            "plan_output_path": v12_source["plan_output_path"],
            "audit_path": v12_source["audit_path"],
            "bundle_path": v12_source["bundle_path"],
        }
        for key in (
            "user_recovery_authorization_path",
            "user_recovery_authorization_sha256",
            "superseded_failure_closeout_path",
            "superseded_failure_closeout_sha256",
        ):
            if key in v12_source:
                v12_recovery_binding[key] = v12_source[key]
        expected_selection = next(
            item["path"]
            for item in v11_contract["inputs"]
            if item["role"] == "R9_selection_transition"
        )
        expected_selection_path = (ROOT / expected_selection).resolve()
        if args.accepted_parent_selection_record.resolve() != expected_selection_path:
            parser.error("V11 P2 requires the contract-bound accepted R9 selection path")
        if args.acceptance_contract.resolve() != DEFAULT_ACCEPTANCE.resolve():
            parser.error("V11 P2 requires the frozen round-one acceptance contract")
        if args.output_root.resolve() not in {
            DEFAULT_OUTPUT.resolve(),
            v11_output_root.resolve(),
        }:
            parser.error("V11 P2 output differs from its unique contract-bound plan root")
        selection_item = next(
            item for item in v11_contract["inputs"]
            if item["role"] == "R9_selection_transition"
        )
        acceptance_item = next(
            item for item in v11_contract["inputs"]
            if item["role"] == "frozen_acceptance_contract"
        )
        if (
            _sha256_file(expected_selection_path) != selection_item["sha256"]
            or _sha256_file(DEFAULT_ACCEPTANCE) != acceptance_item["sha256"]
        ):
            parser.error("V11 P2 selection/acceptance bytes differ from the frozen contract")
        try:
            v11_runtime_environment = _check_v11_runtime_envelope(comm)
            v11_worker_identity = v11_runtime_environment[
                "v11_watchdog_worker_identity"
            ]
            v11_inputs_before = _v11_input_snapshot(
                v11_contract, _V11_P2_INPUT_ROLES
            )
            v11_source_before = _v11_source_snapshot()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            parser.error(f"V11 P2 worker/input preflight failed: {exc}")
    cfg = _h100_config(
        kind="empty_h_active_p3",
        case_name=(
            "task43_v11_r9_h8_candidate_plan_mpi1"
            if v11_contract is not None
            else f"task43_{args.round_id}_candidate_plan_initial180_mpi1"
        ),
        geometry_profile="initial_180",
    )
    if v11_contract is not None:
        output_root = v11_output_root
        output_root.mkdir(parents=True, exist_ok=False)
        assert v11_worker_identity is not None
        assert v11_runtime_environment is not None
        v11_ledger = WorkflowLedger(
            output_root, Path(v11_worker_identity["phase_path"])
        )
        v11_ledger.set_phase("preflight")
        v11_ledger.marker(
            "task43_v11_p2_worker_identity_bound",
            {
                "worker_identity": v11_worker_identity,
                "runtime_environment": v11_runtime_environment,
                "input_sha256": v11_inputs_before,
                "source_sha256": v11_source_before,
                "v12_recovery_binding": v12_recovery_binding,
            },
        )
        a2_substage_root = output_root / "A2_saved_primary_q_response_substages"
        a2_substage_root.mkdir()
        a2_substage_refs: dict[str, dict[str, Any]] = {}
        a2_checkpoint_state: dict[str, str | None] = {"stage": None}

        def persist_a2_substage(stage: str, values: Mapping[str, Any]):
            if stage not in _V11_A2_CHECKPOINT_STAGES:
                raise ValueError(f"unexpected V13 A2 checkpoint stage {stage!r}")
            a2_checkpoint_state["stage"] = stage
            checkpoint_record = {
                "schema": "task43.v13.saved_a2_primary_substage.v1",
                "status": "COMPLETED_SUBSTAGE",
                "classification": "measured_saved_array_diagnostic_substage_nonofficial",
                "stage": stage,
                "identity": {
                    "contract_sha256": v11_contract_sha256,
                    "recovery_manifest_sha256": v12_recovery_binding[
                        "manifest_sha256"
                    ],
                    "v12_recovery_binding": v12_recovery_binding,
                    "input_sha256": v11_inputs_before,
                    "source_sha256": v11_source_before,
                },
                "completed_substage_values": dict(values),
                "overall_pass": False,
                "official_result": False,
                "selection_or_transition_authority": False,
                "continuation": False,
            }
            reference = write_atomic_json(
                a2_substage_root / f"{stage}.json", checkpoint_record
            )
            a2_substage_refs[stage] = reference
            a2_checkpoint_state["stage"] = None
            return reference

        try:
            v11_a2_response = _v11_saved_a2_primary_q_response(
                v11_contract,
                checkpoint_callback=persist_a2_substage,
            )
        except (OSError, KeyError, TypeError, ValueError, RuntimeError) as exc:
            checkpoint_stage = a2_checkpoint_state["stage"]
            v11_a2_response = _v11_saved_a2_failure_response(
                exc,
                a2_substage_refs,
                failure_stage=checkpoint_stage,
                failure_origin=(
                    "atomic_substage_checkpoint_persistence"
                    if checkpoint_stage is not None
                    else "saved_data_recomputation"
                ),
            )
        if "substage_checkpoint_refs" not in v11_a2_response:
            v11_a2_response["substage_checkpoint_refs"] = dict(a2_substage_refs)
        if "substage_statuses" not in v11_a2_response:
            completed_stages = set(a2_substage_refs)
            v11_a2_response["substage_statuses"] = {
                stage: (
                    "CHECKPOINTED"
                    if stage in completed_stages
                    else "NOT_REACHED"
                )
                for stage in _V11_A2_CHECKPOINT_STAGES
            }
        v11_a2_response["persisted_before_space_authority"] = True
        v11_a2_response["contract_sha256"] = v11_contract_sha256
        v11_a2_response["v12_recovery_binding"] = v12_recovery_binding
        a2_checkpoint = write_atomic_json(
            output_root / "A2_saved_primary_q_response.json",
            v11_a2_response,
        )
        v11_ledger.marker(
            "task43_v11_p2_saved_a2_response_persisted_before_authority",
            {
                "record_path": a2_checkpoint["path"],
                "record_sha256": a2_checkpoint["sha256"],
                "pass": v11_a2_response.get("pass") is True,
            },
        )
        if v11_a2_response.get("pass") is not True:
            raise RuntimeError(
                "V11 P2 saved A2 primary raw/q response failed before space authority"
            )
        v11_parent = _v12_observed_call(
            output_root, "parent_identity", _load_accepted_parent_state,
            expected_selection_path,
            cfg=cfg,
            comm_size=comm.size,
        )
        v11_plan = _v12_observed_call(
            output_root, "plan", _build_v11_seed8_plan,
            cfg,
            parent=v11_parent,
            comm_size=comm.size,
            contract=v11_contract,
            recovery_binding=v12_recovery_binding,
        )
    else:
        output_root = args.output_root.resolve()
        output_root.mkdir(parents=True, exist_ok=False)
    plans_dir = output_root / "plans"
    plans_dir.mkdir()
    summaries = []
    if v11_contract is not None:
        assert v11_plan_path is not None and v11_plan is not None
        if v11_plan_path != (plans_dir / "v11_r9_h8.json").resolve():
            raise ValueError("V11 P2 plan path escaped the unique plan_output root")
        v11_plan_path.write_text(
            json.dumps(v11_plan, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        assert v11_ledger is not None and v11_worker_identity is not None
        v11_ledger.set_phase("mesh_setup")
        v11_ledger.marker(
            "task43_v11_p2_mesh_authority_begin",
            {"candidate_id": "v11_r9_h8", "plan_sha256": _sha256_file(v11_plan_path)},
        )
        audit = _v12_observed_call(
            output_root, "space_authority", _audit_plan,
            cfg,
            plan_path=v11_plan_path,
            candidate_id="v11_r9_h8",
            comm=comm,
            parent_independent_fe_dofs=int(v11_parent["parent_independent_fe_dofs"]),
            parent_root_degree_by_box=v11_parent["parent_degree_by_box"],
        )
        # Persist the returned actual audit before any later identity/FE gate.
        write_atomic_json(output_root / "actual_authority_before_fe_gate.json", audit)
        fe_gate_started = time.monotonic()
        with (output_root / "authority_observations.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": "BEGIN", "stage": "FE_verification",
                                     "monotonic": fe_gate_started,
                                     "unreturned_status": "IN_PROGRESS_AT_STOP"}) + "\n")
        strict_fe_gate = _v11_actual_space_gate(
            audit,
            parent_fe_dofs=int(v11_parent["parent_independent_fe_dofs"]),
            fe_bounds=v11_contract["phases"]["P4"]["required_fe_bounds"],
        )
        _require_v11_watchdog_worker_identity(
            require_unused_phase_file=False,
            expected_identity=v11_worker_identity,
        )
        v11_ledger.marker(
            "task43_v11_p2_mesh_authority_complete",
            {
                "candidate_id": "v11_r9_h8",
                "plan_sha256": _sha256_file(v11_plan_path),
                "independent_trace_rows": audit["dofs"]["independent_trace_rows"],
                "active_cell_interior_rows": audit["dofs"]["active_cell_interior_rows"],
                "independent_active_fe_dofs": audit["dofs"]["independent_active_fe_dofs"],
            },
        )
        audit["plan_status"] = {
            "candidate_id": "v11_r9_h8",
            "action": "h_refine",
            "status": "plan_built",
            "predeclared_global_cell_id": 8,
            "requested_h_root_splits": 1,
            "source": "v11_predeclared_seed8",
        }
        audit["v12_recovery_binding"] = dict(v12_recovery_binding)
        audit["strict_fe_gate"] = strict_fe_gate
        with (output_root / "authority_observations.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": "END", "stage": "FE_verification",
                                     "monotonic": time.monotonic(),
                                     "wall_seconds": time.monotonic() - fe_gate_started,
                                     "gate": audit["strict_fe_gate"]}) + "\n")
        summaries.append(audit)
        write_atomic_json(plans_dir / "v11_r9_h8.audit.json", audit)
    elif args.accepted_parent_selection_record is None:
        if args.round_id != "round1":
            parser.error("later rounds require --accepted-parent-selection-record")
        parent_identity, boxes_by_id = _load_parent_identity(
            args.parent_run.resolve(),
            args.tightening_run.resolve(),
            args.marking_record.resolve(),
            args.acceptance_contract.resolve(),
        )
        marked_ids = parent_identity["marked_global_cell_ids"]
        marked_boxes = tuple(boxes_by_id[int(global_id)] for global_id in marked_ids)
        candidates = (
            ("round1_p_up_p4_46", "p_up"),
            ("round1_h_split_46_p3", "h_refine"),
        )
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
            audit_path = plans_dir / f"{candidate_id}.audit.json"
            audit_path.write_text(
                json.dumps(summaries[-1], indent=2, sort_keys=True, allow_nan=False)
                + "\n",
                encoding="utf-8",
            )
    else:
        parent = _load_accepted_parent_state(
            args.accepted_parent_selection_record,
            cfg=cfg,
            comm_size=comm.size,
        )
        for action in ("p_up", "h_refine"):
            candidate_id = f"{args.round_id}_{action}"
            plan, plan_status = _build_next_round_plan(
                cfg,
                action=action,
                candidate_id=candidate_id,
                parent=parent,
                comm_size=comm.size,
            )
            if plan is None:
                summaries.append(plan_status)
                audit_path = plans_dir / f"{candidate_id}.audit.json"
                audit_path.write_text(
                    json.dumps(
                        summaries[-1], indent=2, sort_keys=True, allow_nan=False
                    )
                    + "\n",
                    encoding="utf-8",
                )
                continue
            plan_path = plans_dir / f"{candidate_id}.json"
            plan_path.write_text(
                json.dumps(plan, indent=2, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            transfer_kwargs = {}
            if action == "p_up":
                transfer_kwargs = {
                    "parent_storage_path": Path(parent["parent_storage_path"]),
                    "parent_storage_sha256": parent["parent_storage_sha256"],
                    "audit_parent_transfer": not args.skip_parent_transfer,
                }
            summaries.append(
                _audit_plan(
                    cfg,
                    plan_path=plan_path,
                    candidate_id=candidate_id,
                    comm=comm,
                    parent_independent_fe_dofs=parent["parent_independent_fe_dofs"],
                    **transfer_kwargs,
                )
            )
            summaries[-1]["plan_status"] = plan_status
            audit_path = plans_dir / f"{candidate_id}.audit.json"
            audit_path.write_text(
                json.dumps(summaries[-1], indent=2, sort_keys=True, allow_nan=False)
                + "\n",
                encoding="utf-8",
            )
    record = {
        "schema": (
            "task43.v11_r9_h8_plan_audit_bundle.v1"
            if v11_contract is not None
            else (
            "task43.round1-candidate-plan-audit-bundle.v1"
            if args.accepted_parent_selection_record is None
            else "task43.adaptive-candidate-plan-audit-bundle.v1"
            )
        ),
        "classification": "mesh_and_entity_closure_only_no_pde_solve",
        "contract_path": (
            str(args.primary_diagnostic_contract.resolve())
            if args.primary_diagnostic_contract is not None
            else None
        ),
        "contract_sha256": v11_contract_sha256 if v11_contract is not None else None,
        "v12_recovery_binding": v12_recovery_binding,
        "plan_output_path": (
            str(v11_plan_path) if v11_plan_path is not None else None
        ),
        "skip_parent_transfer_requested": args.skip_parent_transfer,
        "started_unix_seconds": program_started_unix_seconds,
        "completed_unix_seconds": time.time(),
        "total_wall_seconds": time.perf_counter() - program_started,
        "parent_identity": (
            parent_identity
            if args.accepted_parent_selection_record is None
            else {
                key: value
                for key, value in v11_parent.items()
                if key
                not in {
                    "parent_forest",
                    "parent_degree_by_box",
                    "parent_boxes_by_global_id",
                    "parent_record",
                    "parent_plan",
                    "parent_comparison",
                }
            }
            if v11_contract is not None
            else {
                key: value
                for key, value in parent.items()
                if key
                not in {
                    "parent_forest",
                    "parent_degree_by_box",
                    "parent_boxes_by_global_id",
                    "parent_record",
                    "parent_plan",
                    "parent_comparison",
                }
            }
        ),
        "candidates": summaries,
    }
    if v11_contract is not None:
        record["A2_saved_primary_q_response"] = v11_a2_response
    record_path = output_root / "plan_audit.json"
    if v11_contract is not None:
        assert v11_worker_identity is not None
        _require_v11_watchdog_worker_identity(
            require_unused_phase_file=False,
            expected_identity=v11_worker_identity,
        )
        inputs_after = _v11_input_snapshot(v11_contract, _V11_P2_INPUT_ROLES)
        source_after = _v11_source_snapshot()
        if inputs_after != v11_inputs_before or source_after != v11_source_before:
            raise RuntimeError("V11 P2 source/input identity changed during space preparation")
        record["v11_runtime_identity"] = {
            "worker_identity": v11_worker_identity,
            "runtime_environment": v11_runtime_environment,
            "input_sha256_before": v11_inputs_before,
            "input_sha256_after": inputs_after,
            "source_sha256_before": v11_source_before,
            "source_sha256_after": source_after,
            "unchanged": True,
        }
    if v11_contract is not None:
        write_atomic_json(record_path, record)
    else:
        record_path.write_text(
            json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(record, sort_keys=True, allow_nan=False))
    if v11_contract is not None and summaries[0]["strict_fe_gate"]["pass"] is not True:
        raise RuntimeError("V11 seed8 actual independent FE strict bounds failed")
    if v11_contract is not None and (
        not isinstance(v11_a2_response, dict)
        or v11_a2_response.get("pass") is not True
    ):
        raise RuntimeError(
            "V11 P2 saved A2 primary raw/q response failed; see plan_audit.json"
        )
    if v11_ledger is not None:
        v11_ledger.set_phase("complete")
        v11_ledger.marker(
            "task43_v11_p2_space_plan_complete",
            {
                "plan_audit_path": str(record_path.resolve()),
                "plan_audit_sha256": _sha256_file(record_path),
                "plan_sha256": _sha256_file(v11_plan_path),
            },
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
