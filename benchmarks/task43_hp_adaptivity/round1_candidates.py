"""Build and audit the first Task43 p/h candidates without solving Maxwell."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
from dolfinx import fem
from mpi4py import MPI

from benchmarks.task43_hp_adaptivity.candidate_records import (
    load_accepted_parent_artifacts,
)
from benchmarks.task43_hp_adaptivity.compare_initial_to_references import (
    _actual_mesh_identity,
)
from benchmarks.task43_hp_adaptivity.h100_anchor import _h100_config
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
    parent_independent_fe_dofs: int = PARENT_INDEPENDENT_FE_DOFS,
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
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-run", type=Path, default=DEFAULT_PARENT_RUN)
    parser.add_argument("--tightening-run", type=Path, default=DEFAULT_TIGHT_RUN)
    parser.add_argument("--marking-record", type=Path, default=DEFAULT_MARKING)
    parser.add_argument("--acceptance-contract", type=Path, default=DEFAULT_ACCEPTANCE)
    parser.add_argument("--accepted-parent-selection-record", type=Path)
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
    cfg = _h100_config(
        kind="empty_h_active_p3",
        case_name=f"task43_{args.round_id}_candidate_plan_initial180_mpi1",
        geometry_profile="initial_180",
    )
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=False)
    plans_dir = output_root / "plans"
    plans_dir.mkdir()
    summaries = []
    if args.accepted_parent_selection_record is None:
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
            "task43.round1-candidate-plan-audit-bundle.v1"
            if args.accepted_parent_selection_record is None
            else "task43.adaptive-candidate-plan-audit-bundle.v1"
        ),
        "classification": "mesh_and_entity_closure_only_no_pde_solve",
        "skip_parent_transfer_requested": args.skip_parent_transfer,
        "started_unix_seconds": program_started_unix_seconds,
        "completed_unix_seconds": time.time(),
        "total_wall_seconds": time.perf_counter() - program_started,
        "parent_identity": (
            parent_identity
            if args.accepted_parent_selection_record is None
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
    record_path = output_root / "plan_audit.json"
    record_path.write_text(
        json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(record, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
