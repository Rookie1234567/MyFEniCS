"""Multi-goal h/p screening for aligned high-order H(curl) indicators."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from typing import Any

import numpy as np

from dolfinx import mesh

from src.geometry.tetra_mesh_audit import (
    canonical_entity_key,
    canonical_owned_cell_ids,
    geometry_key_sha256,
    mesh_coordinate_tolerance,
)


def _json_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_cell_geometry_priors(mesh_data: Any, cfg: Any) -> dict[str, Any]:
    """Bind material/interface and periodic priors to canonical cell IDs.

    These priors are explanatory and may only break ties between measured
    indicators. They never promote a cell by themselves.
    """

    msh = mesh_data.mesh
    comm = msh.comm
    tdim = msh.topology.dim
    fdim = tdim - 1
    tolerance = mesh_coordinate_tolerance(msh)
    canonical_ids, records, ordered_keys = canonical_owned_cell_ids(
        msh,
        tolerance=tolerance,
    )
    mesh_geometry_sha256 = geometry_key_sha256(ordered_keys)
    tag_by_local_cell = {
        int(index): int(value)
        for index, value in zip(
            mesh_data.cell_tags.indices,
            mesh_data.cell_tags.values,
            strict=True,
        )
    }
    material_names = {
        int(getattr(cfg.tags, name)): name
        for name in ("air", "substrate", "grating", "top_pml", "bottom_pml")
    }

    msh.topology.create_connectivity(tdim, fdim)
    cell_to_facet = msh.topology.connectivity(tdim, fdim)
    if cell_to_facet is None:
        raise RuntimeError("cell-to-facet connectivity is unavailable")

    local_cells: list[dict[str, Any]] = []
    local_face_rows: list[
        tuple[tuple[tuple[int, int, int], ...], int, int]
    ] = []
    for canonical_id, record in zip(canonical_ids, records, strict=True):
        local_cell = int(record.local_index)
        material_tag = tag_by_local_cell.get(local_cell)
        if material_tag is None:
            raise RuntimeError("an owned cell is missing its material tag")
        coordinates = np.asarray(record.coordinates, dtype=np.float64)
        lower = np.min(coordinates, axis=0)
        upper = np.max(coordinates, axis=0)
        integer_coordinates = np.asarray(record.key, dtype=np.int64)
        integer_lower = np.min(integer_coordinates, axis=0)
        integer_upper = np.max(integer_coordinates, axis=0)
        local_cells.append(
            {
                "canonical_cell_id": int(canonical_id),
                "material_tag": int(material_tag),
                "material_name": material_names.get(
                    int(material_tag),
                    f"tag_{material_tag}",
                ),
                "bounds_nm": {
                    "lower": lower.tolist(),
                    "upper": upper.tolist(),
                },
                "centroid_nm": np.mean(coordinates, axis=0).tolist(),
                "_integer_lower": integer_lower.tolist(),
                "_integer_upper": integer_upper.tolist(),
            }
        )
        facet_ids = np.asarray(
            cell_to_facet.links(local_cell),
            dtype=np.int32,
        )
        facet_geometry = mesh.entities_to_geometry(
            msh,
            fdim,
            facet_ids,
            False,
        )
        for geometry_indices in facet_geometry:
            face_key = canonical_entity_key(
                msh.geometry.x[geometry_indices],
                tolerance,
            )
            local_face_rows.append(
                (face_key, int(canonical_id), int(material_tag))
            )

    global_cells = [
        row
        for packet in comm.allgather(local_cells)
        for row in packet
    ]
    global_face_rows = [
        row
        for packet in comm.allgather(local_face_rows)
        for row in packet
    ]
    global_cells.sort(key=lambda row: int(row["canonical_cell_id"]))
    expected_ids = list(range(len(global_cells)))
    actual_ids = [int(row["canonical_cell_id"]) for row in global_cells]
    if actual_ids != expected_ids:
        raise RuntimeError("canonical cell priors are not complete and ordered")

    rows_by_face: dict[
        tuple[tuple[int, int, int], ...],
        list[tuple[int, int]],
    ] = defaultdict(list)
    for face_key, canonical_id, material_tag in global_face_rows:
        rows_by_face[face_key].append((canonical_id, material_tag))
    interface_neighbors: dict[int, set[int]] = defaultdict(set)
    interface_facet_count: Counter[int] = Counter()
    for adjacent in rows_by_face.values():
        tags = {material_tag for _, material_tag in adjacent}
        if len(adjacent) == 2 and len(tags) == 2:
            for canonical_id, material_tag in adjacent:
                interface_facet_count[canonical_id] += 1
                interface_neighbors[canonical_id].update(
                    tag for tag in tags if tag != material_tag
                )

    domain_integer_lower = np.rint(
        np.asarray(
            (cfg.x_min, cfg.y_min, cfg.domain_z_min),
            dtype=np.float64,
        )
        / tolerance
    ).astype(np.int64)
    domain_integer_upper = np.rint(
        np.asarray(
            (cfg.x_max, cfg.y_max, cfg.domain_z_max),
            dtype=np.float64,
        )
        / tolerance
    ).astype(np.int64)
    periodic_groups: dict[
        tuple[Any, ...],
        dict[str, Any],
    ] = {}
    for row in global_cells:
        canonical_id = int(row["canonical_cell_id"])
        lower = np.asarray(row.pop("_integer_lower"), dtype=np.int64)
        upper = np.asarray(row.pop("_integer_upper"), dtype=np.int64)
        periodic_axes: list[str] = []
        for axis, axis_name in ((0, "x"), (1, "y")):
            side = None
            if lower[axis] == domain_integer_lower[axis]:
                side = "min"
            elif upper[axis] == domain_integer_upper[axis]:
                side = "max"
            if side is None:
                continue
            periodic_axes.append(axis_name)
            other_axis = 1 - axis
            key = (
                axis_name,
                int(lower[other_axis]),
                int(upper[other_axis]),
                int(lower[2]),
                int(upper[2]),
            )
            group = periodic_groups.setdefault(
                key,
                {"axis": axis_name, "members": {}},
            )
            group["members"][side] = canonical_id
        row["material_interface_facet_count"] = int(
            interface_facet_count[canonical_id]
        )
        row["material_interface"] = bool(interface_facet_count[canonical_id])
        row["interface_neighbor_material_tags"] = sorted(
            interface_neighbors[canonical_id]
        )
        row["interface_neighbor_material_names"] = sorted(
            material_names.get(tag, f"tag_{tag}")
            for tag in interface_neighbors[canonical_id]
        )
        row["corner_or_edge_junction_prior"] = bool(
            interface_facet_count[canonical_id] >= 2
        )
        row["periodic_boundary_axes"] = periodic_axes

    periodic_mate_groups: list[dict[str, Any]] = []
    for key, group in sorted(periodic_groups.items()):
        members = group["members"]
        if set(members) != {"min", "max"}:
            raise RuntimeError(f"incomplete periodic mate group: {key}")
        periodic_mate_groups.append(
            {
                "axis": group["axis"],
                "min_cell_id": int(members["min"]),
                "max_cell_id": int(members["max"]),
            }
        )

    material_counts = Counter(
        str(row["material_name"]) for row in global_cells
    )
    payload = {
        "schema_version": "myfenics.canonical-cell-geometry-priors.v1",
        "status": "canonical_cell_geometry_priors_pass",
        "pass": True,
        "geometry": "Task034 fixed rectangular block grating",
        "mesh_geometry_sha256": mesh_geometry_sha256,
        "cell_count": len(global_cells),
        "material_counts": dict(sorted(material_counts.items())),
        "material_interface_cell_count": int(
            sum(bool(row["material_interface"]) for row in global_cells)
        ),
        "corner_or_edge_junction_cell_count": int(
            sum(
                bool(row["corner_or_edge_junction_prior"])
                for row in global_cells
            )
        ),
        "periodic_mate_group_count": len(periodic_mate_groups),
        "periodic_mate_groups": periodic_mate_groups,
        "cells": global_cells,
        "prior_semantics": (
            "material/interface/corner and periodic identity are auxiliary; "
            "they do not override measured eta or DWR indicators"
        ),
    }
    payload["canonical_priors_sha256"] = _json_sha256(payload)
    return payload


def _snapshot_values(
    snapshot: dict[str, Any],
    expected_ids: np.ndarray,
    expected_mesh_sha256: str,
    label: str,
) -> np.ndarray:
    if snapshot.get("storage") != "inline_complete_vector":
        raise ValueError(f"{label} must be an inline complete vector")
    if snapshot.get("mesh_geometry_sha256") != expected_mesh_sha256:
        raise ValueError(f"{label} uses a different mesh geometry")
    ids = np.asarray(snapshot.get("canonical_cell_ids"), dtype=np.int64)
    values = np.asarray(snapshot.get("indicator_values"), dtype=np.float64)
    if not np.array_equal(ids, expected_ids) or values.shape != ids.shape:
        raise ValueError(f"{label} canonical cell IDs are not aligned")
    if not np.all(np.isfinite(values)) or np.any(values < 0.0):
        raise ValueError(f"{label} values must be finite and nonnegative")
    return values


def classify_multigoal_hp_candidates(
    base_classifier_record: dict[str, Any],
    dwr_record: dict[str, Any],
    cell_geometry_priors: dict[str, Any],
) -> dict[str, Any]:
    """Join eta p-decay, strict/multi-goal DWR, R5, and geometry priors."""

    if base_classifier_record.get("pass") is not True:
        raise ValueError("base p4/p5/p6 classifier is not qualified")
    if (dwr_record.get("qualification") or {}).get("pass") is not True:
        raise ValueError("multi-goal DWR authority is not qualified")
    if cell_geometry_priors.get("pass") is not True:
        raise ValueError("cell geometry priors are not qualified")

    mesh_sha256 = str(base_classifier_record["mesh_geometry_sha256"])
    if cell_geometry_priors.get("mesh_geometry_sha256") != mesh_sha256:
        raise ValueError("cell priors use a different mesh geometry")
    base_actions = (
        (base_classifier_record.get("classifier") or {}).get(
            "local_order_actions"
        )
        or []
    )
    expected_ids = np.arange(
        int(base_classifier_record["cell_count"]),
        dtype=np.int64,
    )
    actions_by_id = {
        int(row["canonical_cell_id"]): row for row in base_actions
    }
    priors_by_id = {
        int(row["canonical_cell_id"]): row
        for row in cell_geometry_priors.get("cells", [])
    }
    if sorted(actions_by_id) != expected_ids.tolist():
        raise ValueError("base classifier actions are not complete")
    if sorted(priors_by_id) != expected_ids.tolist():
        raise ValueError("cell priors are not complete")

    goals = (dwr_record.get("DWR") or {}).get("goals") or {}
    required_goals = ("R00_total", "R_total", "T_total")
    if set(required_goals) - set(goals):
        raise ValueError("DWR authority lacks a required R00/R/T goal")
    reports = {
        "DWR_R00": goals["R00_total"],
        "DWR_R": goals["R_total"],
        "DWR_T": goals["T_total"],
        "DWR_relative_R_T": dwr_record["DWR"]["combined_relative_R_T"],
        "DWR_tolerance_normalized_R_T": dwr_record["DWR"][
            "tolerance_normalized_R_T"
        ],
        "R5": dwr_record["R5_control"],
    }
    indicator_values = {
        name: _snapshot_values(
            report["cell_indicator_snapshot"],
            expected_ids,
            mesh_sha256,
            name,
        )
        for name, report in reports.items()
    }
    normalized_values = {
        name: values / max(float(np.sum(values)), np.finfo(float).tiny)
        for name, values in indicator_values.items()
    }
    marked_sets = {
        name: {
            int(value)
            for value in report.get("marked_canonical_cell_ids", [])
        }
        for name, report in reports.items()
    }
    strict_r00 = marked_sets["DWR_R00"]
    normalized_rt = marked_sets["DWR_tolerance_normalized_R_T"]
    raw_goal_important = strict_r00 | normalized_rt
    if not raw_goal_important:
        raise ValueError("strict R00 plus normalized R/T marker is empty")
    goal_important = set(raw_goal_important)
    changed = True
    while changed:
        changed = False
        for group in cell_geometry_priors["periodic_mate_groups"]:
            left = int(group["min_cell_id"])
            right = int(group["max_cell_id"])
            if (left in goal_important) == (right in goal_important):
                continue
            goal_important.update((left, right))
            changed = True
    periodic_closure_added = sorted(goal_important - raw_goal_important)

    ratio_threshold = float(
        base_classifier_record["classifier"]["p_decay_ratio_threshold"]
    )
    decisions: list[dict[str, Any]] = []
    action_counts: Counter[str] = Counter()
    for canonical_id in expected_ids.tolist():
        base = actions_by_id[canonical_id]
        prior = priors_by_id[canonical_id]
        ratio = base.get("higher_to_lower_ratio")
        goal_marked = canonical_id in goal_important
        if ratio is None:
            action = "undetermined"
            reason = "consecutive p-correction ratio is unavailable"
        elif goal_marked and float(ratio) > ratio_threshold:
            action = "h_refine_candidate"
            reason = (
                "strict-R00 or normalized-R/T important with slow p-decay"
            )
        elif goal_marked:
            action = "p_up_candidate"
            reason = (
                "strict-R00 or normalized-R/T important with fast p-decay"
            )
        elif base.get("action") == "p_down":
            action = "p_down_candidate"
            reason = "goal-unmarked and below the conservative p-down floor"
        else:
            action = "p_keep_candidate"
            reason = "not selected by strict-R00 or normalized-R/T marking"
        action_counts[action] += 1
        decisions.append(
            {
                "canonical_cell_id": canonical_id,
                "action": action,
                "reason": reason,
                "eta_p4p5": float(base["lower_pair_indicator"]),
                "eta_p5p6": float(base["higher_pair_indicator"]),
                "eta_p5p6_over_eta_p4p5": (
                    None if ratio is None else float(ratio)
                ),
                "marked": {
                    name: canonical_id in marked
                    for name, marked in marked_sets.items()
                },
                "periodic_goal_marker_closure_only": (
                    canonical_id in periodic_closure_added
                ),
                "normalized_indicator_contributions": {
                    name: float(values[canonical_id])
                    for name, values in normalized_values.items()
                },
                "material_tag": int(prior["material_tag"]),
                "material_name": str(prior["material_name"]),
                "material_interface": bool(prior["material_interface"]),
                "material_interface_facet_count": int(
                    prior["material_interface_facet_count"]
                ),
                "corner_or_edge_junction_prior": bool(
                    prior["corner_or_edge_junction_prior"]
                ),
                "periodic_boundary_axes": list(
                    prior["periodic_boundary_axes"]
                ),
            }
        )

    decision_by_id = {
        int(row["canonical_cell_id"]): str(row["action"])
        for row in decisions
    }
    periodic_mismatches = []
    for group in cell_geometry_priors["periodic_mate_groups"]:
        left = int(group["min_cell_id"])
        right = int(group["max_cell_id"])
        if decision_by_id[left] != decision_by_id[right]:
            periodic_mismatches.append(
                {
                    **group,
                    "min_action": decision_by_id[left],
                    "max_action": decision_by_id[right],
                }
            )

    action_by_material: dict[str, Counter[str]] = defaultdict(Counter)
    interface_action_counts: Counter[str] = Counter()
    corner_action_counts: Counter[str] = Counter()
    for decision in decisions:
        action = str(decision["action"])
        action_by_material[str(decision["material_name"])][action] += 1
        if decision["material_interface"]:
            interface_action_counts[action] += 1
        if decision["corner_or_edge_junction_prior"]:
            corner_action_counts[action] += 1

    missing_required_signals = [
        "target_cell_hierarchical_coefficient_decay",
        "target_cell_local_projection_defect",
        "actual_local_h_vs_p_cost_normalized_competition",
    ]
    return {
        "schema_version": "task035b.same-mesh-multigoal-hp-classifier.v2",
        "status": "multigoal_hp_screening_pass",
        "pass": len(periodic_mismatches) == 0,
        "canonical": False,
        "production_qualified": False,
        "ordinary_default_changed": False,
        "geometry": "Task034 fixed rectangular block grating",
        "mesh_geometry_sha256": mesh_sha256,
        "cell_count": len(expected_ids),
        "goal_importance_policy": (
            "union(strict DWR_R00 theta set, tolerance-normalized DWR_R/T "
            "theta set), followed by x/y periodic mate closure; strict R and "
            "T remain separately audited"
        ),
        "raw_goal_important_cell_count": len(raw_goal_important),
        "goal_important_cell_count": len(goal_important),
        "goal_important_canonical_cell_ids": sorted(goal_important),
        "periodic_goal_marker_closure_added_cell_count": len(
            periodic_closure_added
        ),
        "periodic_goal_marker_closure_added_canonical_cell_ids": (
            periodic_closure_added
        ),
        "p_decay_ratio_threshold": ratio_threshold,
        "action_counts": dict(
            sorted(
                {
                    name: int(action_counts.get(name, 0))
                    for name in (
                        "p_down_candidate",
                        "p_keep_candidate",
                        "p_up_candidate",
                        "h_refine_candidate",
                        "undetermined",
                    )
                }.items()
            )
        ),
        "actions_by_material": {
            material: dict(sorted(counts.items()))
            for material, counts in sorted(action_by_material.items())
        },
        "interface_action_counts": dict(
            sorted(interface_action_counts.items())
        ),
        "corner_or_edge_action_counts": dict(
            sorted(corner_action_counts.items())
        ),
        "marker_counts": {
            name: len(marked) for name, marked in marked_sets.items()
        },
        "decisions": decisions,
        "periodic_decision_audit": {
            "pass": len(periodic_mismatches) == 0,
            "mate_group_count": len(
                cell_geometry_priors["periodic_mate_groups"]
            ),
            "mismatch_count": len(periodic_mismatches),
            "mismatches": periodic_mismatches,
        },
        "signal_coverage": {
            "eta_p4p5": "actual_same_mesh",
            "eta_p5p6": "actual_same_mesh",
            "DWR_R00": "actual_same_mesh_independent_adjoint",
            "DWR_R": "actual_same_mesh_independent_adjoint",
            "DWR_T": "actual_same_mesh_independent_adjoint",
            "DWR_tolerance_normalized_R_T": "actual_same_mesh",
            "R5_correction_energy": "actual_same_mesh",
            "material_interface_corner_priors": "actual_same_mesh",
            "target_cell_hierarchical_coefficient_decay": "not_available",
            "target_cell_local_projection_defect": "not_available",
            "actual_local_h_vs_p_cost_normalized_competition": "not_run",
        },
        "missing_required_signals": missing_required_signals,
        "decision_semantics": (
            "research screening only; missing target coefficient/projection "
            "signals and actual h-vs-p competition prevent production use"
        ),
    }


__all__ = [
    "build_cell_geometry_priors",
    "classify_multigoal_hp_candidates",
]
