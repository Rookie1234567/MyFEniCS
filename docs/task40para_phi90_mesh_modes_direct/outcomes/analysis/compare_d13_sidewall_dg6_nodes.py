#!/usr/bin/env python3
"""Compare saved exact DG6 FE-export nodes on the four rectangular sidewalls.

No resampling, ParaView interpolation, phase fitting, or synthetic field values
are created. The script selects stored point-data values whose coordinates lie
on the material faces and compares only coordinates present in both runs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pyvista as pv

ROOT = Path("results/si_block_phi90_50x50_17x20_h120")
CASES = {
    "B": ("task40_phi90_13p5_D13_B_p6_direct_v1", "20261016T091948.653032Z"),
    "X": ("task40_phi90_13p5_D13_X_p6_direct_v1", "20261016T094950.200837Z"),
    "Y": ("task40_phi90_13p5_D13_Y_p6_direct_v1", "20261016T102453.831934Z"),
    "Z": ("task40_phi90_13p5_D13_Z_p6_direct_v1", "20261016T104423.676151Z"),
}
FACES = {
    "x16p5": {"axis": 0, "coordinate": 16.5, "range_axis": 1, "range": (15.0, 35.0), "z_range": (0.0, 120.0), "tangential_components": [1, 2]},
    "x33p5": {"axis": 0, "coordinate": 33.5, "range_axis": 1, "range": (15.0, 35.0), "z_range": (0.0, 120.0), "tangential_components": [1, 2]},
    "y15": {"axis": 1, "coordinate": 15.0, "range_axis": 0, "range": (16.5, 33.5), "z_range": (0.0, 120.0), "tangential_components": [0, 2]},
    "y35": {"axis": 1, "coordinate": 35.0, "range_axis": 0, "range": (16.5, 33.5), "z_range": (0.0, 120.0), "tangential_components": [0, 2]},
}
TAG_NAMES = {1: "air", 3: "grating"}
TOL = 1.0e-8


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def norm_metrics(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    delta = b - a
    a_norm = float(np.linalg.norm(a.ravel()))
    delta_norm = float(np.linalg.norm(delta.ravel()))
    return {
        "reference_l2": a_norm,
        "delta_l2": delta_norm,
        "relative_l2_no_phase_fit": delta_norm / a_norm if a_norm else (0.0 if delta_norm == 0 else float("inf")),
        "max_abs_delta": float(np.max(np.abs(delta))) if delta.size else 0.0,
    }


def read_vtu(label: str) -> dict:
    folder, stamp = CASES[label]
    run_dir = ROOT / f"{folder}__full3d_direct__mpi1__Mna" / stamp
    path = run_dir / "numerical_output" / "fields_3d_for_paraview.vtu"
    grid = pv.read(path)
    if grid.n_cells == 0 or grid.n_points == 0:
        raise ValueError(f"{label}: empty VTU fallback")
    expected_arrays = {
        "E_tot_V_per_m_real", "E_tot_V_per_m_imag",
        "H_A_per_m_real", "H_A_per_m_imag",
    }
    if not expected_arrays.issubset(set(grid.point_data.keys())):
        raise ValueError(f"{label}: incomplete complex E/H point arrays")
    if "domain_tag" not in grid.cell_data:
        raise ValueError(f"{label}: missing cellwise domain_tag")
    for name in expected_arrays:
        if not np.isfinite(np.asarray(grid.point_data[name])).all():
            raise ValueError(f"{label}: non-finite {name}")
    tags = np.asarray(grid.cell_data["domain_tag"], dtype=np.int32)
    direct = json.loads((run_dir / "p6_condensed_direct_summary.json").read_text())
    if len(grid.cells) % grid.n_cells != 0:
        raise ValueError(f"{label}: variable VTK connectivity unexpected")
    cells = np.asarray(grid.cells, dtype=np.int64).reshape(grid.n_cells, -1)
    if not np.all(cells[:, 0] == cells[0, 0]) or int(cells[0, 0]) != 343:
        raise ValueError(f"{label}: expected 343 DG6 nodal points per hex cell")
    if sorted(set(grid.celltypes.tolist())) != [72]:
        raise ValueError(f"{label}: expected VTK_LAGRANGE_HEXAHEDRON cells")
    points = np.asarray(grid.points, dtype=np.float64)
    e = np.asarray(grid.point_data["E_tot_V_per_m_real"]) + 1j * np.asarray(grid.point_data["E_tot_V_per_m_imag"])
    h = np.asarray(grid.point_data["H_A_per_m_real"]) + 1j * np.asarray(grid.point_data["H_A_per_m_imag"])
    if points.shape != (grid.n_points, 3) or e.shape != (grid.n_points, 3) or h.shape != (grid.n_points, 3):
        raise ValueError(f"{label}: unexpected point field shape")
    expected_tags = {int(k): int(v) for k, v in direct["mesh_evidence"]["material_tag_counts"].items()}
    actual_tags = {int(tag): int(np.count_nonzero(tags == tag)) for tag in sorted(set(tags.tolist()))}
    if actual_tags != expected_tags:
        raise ValueError(f"{label}: VTU tag counts differ from actual mesh evidence")
    return {
        "run_dir": str(run_dir),
        "path": str(path),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "grid": grid,
        "cells": cells[:, 1:],
        "points": points,
        "e": e,
        "h": h,
        "tags": tags,
        "direct": direct,
        "cell_count": int(grid.n_cells),
        "point_count": int(grid.n_points),
        "vtk_cell_type": "VTK_LAGRANGE_HEXAHEDRON",
        "dg6_nodes_per_cell": int(cells.shape[1] - 1),
        "tag_counts": actual_tags,
    }


def extract_face_nodes(case: dict) -> dict:
    points, e, h = case["points"], case["e"], case["h"]
    cells, tags = case["cells"], case["tags"]
    records: dict[tuple, list[tuple[int, int, tuple[float, ...], np.ndarray, np.ndarray]]] = {}
    face_cell_counts: dict[str, dict[str, int]] = {}
    for face_name, spec in FACES.items():
        axis = int(spec["axis"])
        transverse_axis = int(spec["range_axis"])
        plane = float(spec["coordinate"])
        range_lo, range_hi = spec["range"]
        z_lo, z_hi = spec["z_range"]
        for cell_id, point_ids in enumerate(cells):
            xyz = points[point_ids]
            lo = xyz.min(axis=0)
            hi = xyz.max(axis=0)
            if abs(lo[axis] - plane) > TOL and abs(hi[axis] - plane) > TOL:
                continue
            center = 0.5 * (lo[axis] + hi[axis])
            face_side = "minus" if center < plane else "plus"
            tag = int(tags[cell_id])
            # Only the sidewall interior, excluding top/bottom and vertical edges.
            select = (
                (np.abs(xyz[:, axis] - plane) <= TOL)
                & (xyz[:, transverse_axis] > range_lo + TOL)
                & (xyz[:, transverse_axis] < range_hi - TOL)
                & (xyz[:, 2] > z_lo + TOL)
                & (xyz[:, 2] < z_hi - TOL)
            )
            local_indices = np.flatnonzero(select)
            if not local_indices.size:
                continue
            face_cell_counts.setdefault(face_name, {}).setdefault(f"{face_side}:{tag}", 0)
            face_cell_counts[face_name][f"{face_side}:{tag}"] += 1
            for local_id in local_indices.tolist():
                point_id = int(point_ids[local_id])
                coord = tuple(float(v) for v in xyz[local_id])
                coord_key = tuple(round(v, 9) for v in coord)
                key = (face_name, face_side, tag, *coord_key)
                tangent = tuple(spec["tangential_components"])
                records.setdefault(key, []).append(
                    (cell_id, local_id, coord, e[point_id, list(tangent)].copy(), h[point_id, list(tangent)].copy())
                )
    reduced = {}
    duplicate_spread = {}
    for key, values in records.items():
        values.sort(key=lambda value: (value[0], value[1]))
        reduced[key] = values[0]
        if len(values) > 1:
            e_values = np.stack([item[3] for item in values])
            h_values = np.stack([item[4] for item in values])
            duplicate_spread[str(key)] = {
                "copies": len(values),
                "max_abs_E_t_spread": float(np.max(np.abs(e_values - e_values[0]))),
                "max_abs_H_t_spread": float(np.max(np.abs(h_values - h_values[0]))),
            }
    group_counts = {}
    for key in reduced:
        face, side, tag = key[:3]
        group_counts.setdefault(f"{face}|{side}|{tag}", 0)
        group_counts[f"{face}|{side}|{tag}"] += 1
    return {
        "records": reduced,
        "duplicate_spread": duplicate_spread,
        "face_cell_counts": face_cell_counts,
        "unique_point_counts_by_face_side_tag": group_counts,
    }


def compare_group(base: dict, candidate: dict, group: tuple[str, str, int]) -> dict:
    def keys_for(records):
        return {key for key in records if key[:3] == group}
    a_keys = keys_for(base["records"])
    b_keys = keys_for(candidate["records"])
    common = sorted(a_keys & b_keys)
    if not common:
        raise ValueError(f"no common sidewall nodes for {group}")
    a_e = np.stack([base["records"][key][3] for key in common])
    b_e = np.stack([candidate["records"][key][3] for key in common])
    a_h = np.stack([base["records"][key][4] for key in common])
    b_h = np.stack([candidate["records"][key][4] for key in common])
    coord_deltas = [
        max(abs(x - y) for x, y in zip(base["records"][key][2], candidate["records"][key][2], strict=True))
        for key in common
    ]
    return {
        "tag_name": TAG_NAMES.get(group[2], "unknown"),
        "B_unique_nodes": len(a_keys),
        "candidate_unique_nodes": len(b_keys),
        "common_coordinate_count": len(common),
        "B_only_coordinate_count": len(a_keys - b_keys),
        "candidate_only_coordinate_count": len(b_keys - a_keys),
        "max_coordinate_delta_nm": max(coord_deltas, default=0.0),
        "E_t_no_phase_fit": norm_metrics(a_e, b_e),
        "H_t_no_phase_fit": norm_metrics(a_h, b_h),
    }


runs = {label: read_vtu(label) for label in CASES}
face_data = {label: extract_face_nodes(case) for label, case in runs.items()}
comparisons = {}
for label in ("X", "Y", "Z"):
    groups = {}
    for face_name in FACES:
        for side in ("minus", "plus"):
            for tag in (1, 3):
                group = (face_name, side, tag)
                name = f"{face_name}|{side}|{tag}"
                if group[0:2] not in [("x16p5", "minus"), ("x16p5", "plus"), ("x33p5", "minus"), ("x33p5", "plus"), ("y15", "minus"), ("y15", "plus"), ("y35", "minus"), ("y35", "plus")]:
                    continue
                if not face_data["B"]["records"].keys() or not face_data[label]["records"].keys():
                    raise ValueError("empty sidewall extraction")
                if any(key[:3] == group for key in face_data["B"]["records"]) or any(key[:3] == group for key in face_data[label]["records"]):
                    groups[name] = compare_group(face_data["B"], face_data[label], group)
    comparisons[label] = groups

out = {
    "schema": "task40_d13_bxyz_sidewall_dg6_node_comparison_v1",
    "source_representation": {
        "vtk_fallback": "existing fields_3d_for_paraview.vtu",
        "field_construction": "postprocess_3d.py creates DG6 vector fields by DOLFINx interpolation and exports the per-cell Lagrange-hex nodal values",
        "sampling_method": "select only saved DG6 nodes exactly on material sidewall faces; no geometric/visualization interpolation and no phase fit",
        "scope_limit": "stored DG6 representation at exact nodes only; not a full-domain norm; not new solve or reconstruction from canonical H(curl) coefficients",
        "tangential_components": {"x_normal": ["y", "z"], "y_normal": ["x", "z"]},
        "excluded_edges": "strictly excludes z=0/120 and sidewall corners",
    },
    "face_geometry_nm": {
        "x16p5": {"x": 16.5, "inside_grating_y": [15.0, 35.0], "inside_grating_z": [0.0, 120.0]},
        "x33p5": {"x": 33.5, "inside_grating_y": [15.0, 35.0], "inside_grating_z": [0.0, 120.0]},
        "y15": {"y": 15.0, "inside_grating_x": [16.5, 33.5], "inside_grating_z": [0.0, 120.0]},
        "y35": {"y": 35.0, "inside_grating_x": [16.5, 33.5], "inside_grating_z": [0.0, 120.0]},
    },
    "runs": {
        label: {
            "path": case["path"], "sha256": case["sha256"], "bytes": case["bytes"],
            "cell_count": case["cell_count"], "point_count": case["point_count"],
            "cell_type": case["vtk_cell_type"], "dg6_nodes_per_cell": case["dg6_nodes_per_cell"],
            "tag_counts": case["tag_counts"],
            "finite_EH": True,
            "extracted_unique_point_counts_by_face_side_tag": face_data[label]["unique_point_counts_by_face_side_tag"],
            "duplicate_trace_spread_summary": {
                "duplicate_coordinate_groups": len(face_data[label]["duplicate_spread"]),
                "max_abs_E_t_spread": max((v["max_abs_E_t_spread"] for v in face_data[label]["duplicate_spread"].values()), default=0.0),
                "max_abs_H_t_spread": max((v["max_abs_H_t_spread"] for v in face_data[label]["duplicate_spread"].values()), default=0.0),
            },
        }
        for label, case in runs.items()
    },
    "comparisons_to_B": comparisons,
}
output = Path("docs/task40para_phi90_mesh_modes_direct/outcomes/records/d13_bxyz_sidewall_comparison.json")
output.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
print(json.dumps({"output": str(output), "sha256": sha256(output), "comparisons": comparisons, "runs": out["runs"]}, indent=2, sort_keys=True))
