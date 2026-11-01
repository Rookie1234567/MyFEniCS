"""Exact mapped Q1 hexahedral planner for the fixed Task40 gate_cd cell."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from itertools import pairwise
from math import inf
from typing import Any

import numpy as np

from src.common.gate_cd_materials import (
    GATE_CD_CONDITIONS_SHA256,
    GATE_CD_REGION_MATERIAL,
    GATE_CD_REGION_TAGS,
)

GATE_CD_PROFILE_ID = "task40_gate_cd_0p7_mapped_p6_v1"
GATE_CD_REQUIRED_Z_PLANES_NM = (
    -10.0,
    0.0,
    50.0,
    55.0,
    63.0,
    70.0,
    78.0,
    85.0,
    93.0,
    100.0,
    108.0,
    127.0,
    135.0,
    142.0,
    150.0,
    157.0,
    165.0,
    172.0,
    180.0,
    190.0,
    200.0,
    228.0,
    230.0,
    240.0,
)
GATE_CD_X_CELLS = 5
GATE_CD_Y_SEGMENT_CELLS = (80, 80, 80)
GATE_CD_CELLS = (
    GATE_CD_X_CELLS,
    sum(GATE_CD_Y_SEGMENT_CELLS),
    len(GATE_CD_REQUIRED_Z_PLANES_NM) - 1,
)

_STACK_LAYERS = (
    (50.0, 55.0, "Fin1"),
    (55.0, 63.0, "Fin2"),
    (63.0, 70.0, "Fin3"),
    (70.0, 78.0, "Fin4"),
    (78.0, 85.0, "Fin5"),
    (85.0, 93.0, "Fin6"),
    (93.0, 100.0, "Fin7"),
    (100.0, 108.0, "Fin8"),
    (108.0, 127.0, "MDI"),
    (127.0, 135.0, "Fin9"),
    (135.0, 142.0, "Fin10"),
    (142.0, 150.0, "Fin11"),
    (150.0, 157.0, "Fin12"),
    (157.0, 165.0, "Fin13"),
    (165.0, 172.0, "Fin14"),
    (172.0, 180.0, "Fin15"),
)


@dataclass(frozen=True)
class GateCdMeshPlan:
    z: np.ndarray
    x_sections: np.ndarray
    y_sections: np.ndarray
    tag_counts: dict[str, int]
    axis_hashes: dict[str, str]
    plan_sha256: str
    static_facts: dict[str, Any]


def _axis_sha(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values, dtype="<f8")
    return hashlib.sha256(array.tobytes()).hexdigest()


def _x_section(z: float) -> np.ndarray:
    if z <= 200.0:
        outer_l, inner_l, inner_r, outer_r = 16.5, 18.5, 31.5, 33.5
    elif z <= 228.0:
        wg = 17.0 - (7.0 / 30.0) * (z - 200.0)
        wo = 13.0 - 0.25 * (z - 200.0)
        outer_l, outer_r = 25.0 - wg / 2.0, 25.0 + wg / 2.0
        inner_l, inner_r = 25.0 - wo / 2.0, 25.0 + wo / 2.0
    elif z <= 230.0:
        wg = 17.0 - (7.0 / 30.0) * (z - 200.0)
        outer_l, outer_r = 25.0 - wg / 2.0, 25.0 + wg / 2.0
        inner_l, inner_r = 22.0, 28.0
    else:
        outer_l, inner_l, inner_r, outer_r = 20.0, 22.0, 28.0, 30.0
    return np.asarray((0.0, outer_l, inner_l, inner_r, outer_r, 50.0), dtype=np.float64)


def _fin_bounds(z: float) -> tuple[float, float]:
    if z <= 0.0:
        return 15.0, 35.0
    if z < 50.0:
        return 15.0 + 0.1 * z, 35.0 - 0.1 * z
    return 20.0, 30.0


def _y_section(z: float) -> np.ndarray:
    lo, hi = _fin_bounds(z)
    return np.concatenate(
        (
            np.linspace(0.0, lo, 81, dtype=np.float64),
            np.linspace(lo, hi, 81, dtype=np.float64)[1:],
            np.linspace(hi, 50.0, 81, dtype=np.float64)[1:],
        )
    )


def gate_cd_material_label(x: float, y: float, z: float) -> str:
    """Classify a point using the exact priority/geometry in user conditions."""

    if z < 0.0:
        return "Si_substrate"
    if z < 50.0:
        lo, hi = _fin_bounds(z)
        return "Si_Fin0" if lo < y < hi else "STI_SiO2"
    if z < 180.0:
        material = next(name for lo, hi, name in _STACK_LAYERS if lo < z < hi)
        if 16.5 < x < 33.5 and 20.0 < y < 30.0:
            return material
        if 16.5 < x < 33.5:
            return "Si_poly" if 18.5 < x < 31.5 else "SiN"
        return "Air"
    if z < 190.0:
        if 18.5 < x < 31.5:
            return "Si_poly"
        if 16.5 < x < 33.5:
            return "SiN"
        return "Air"
    if z < 200.0:
        return "SiN" if 16.5 < x < 33.5 else "Air"
    if z < 228.0:
        wg = 17.0 - (7.0 / 30.0) * (z - 200.0)
        wo = 13.0 - 0.25 * (z - 200.0)
        if 25.0 - wg / 2.0 < x < 25.0 + wg / 2.0:
            return "Gate_SiO2" if 25.0 - wo / 2.0 < x < 25.0 + wo / 2.0 else "SiN"
        return "Air"
    if z < 230.0:
        wg = 17.0 - (7.0 / 30.0) * (z - 200.0)
        return "SiN" if 25.0 - wg / 2.0 < x < 25.0 + wg / 2.0 else "Air"
    return "Air"


def _cell_midpoint(
    xb: np.ndarray, xt: np.ndarray, yb: np.ndarray, yt: np.ndarray, z0: float, z1: float
) -> tuple[float, float, float]:
    return (
        float((xb[0] + xb[1] + xt[0] + xt[1]) / 4.0),
        float((yb[0] + yb[1] + yt[0] + yt[1]) / 4.0),
        0.5 * (float(z0) + float(z1)),
    )


def build_gate_cd_plan() -> GateCdMeshPlan:
    z = np.asarray(GATE_CD_REQUIRED_Z_PLANES_NM, dtype=np.float64)
    x_sections = np.vstack([_x_section(float(value)) for value in z])
    y_sections = np.vstack([_y_section(float(value)) for value in z])
    if x_sections.shape != (len(z), GATE_CD_X_CELLS + 1):
        raise AssertionError("gate_cd x section topology changed")
    if y_sections.shape != (len(z), sum(GATE_CD_Y_SEGMENT_CELLS) + 1):
        raise AssertionError("gate_cd y section topology changed")
    if np.any(np.diff(x_sections, axis=1) <= 0.0) or np.any(
        np.diff(y_sections, axis=1) <= 0.0
    ):
        raise ValueError("gate_cd mapped cross-sections must be strictly ordered")
    if not (
        np.all(x_sections[:, 0] == 0.0)
        and np.all(x_sections[:, -1] == 50.0)
        and np.all(y_sections[:, 0] == 0.0)
        and np.all(y_sections[:, -1] == 50.0)
    ):
        raise ValueError("gate_cd periodic boundary coordinates must stay fixed")

    counts: Counter[str] = Counter()
    volumes: Counter[str] = Counter()
    min_det = inf
    max_det = 0.0
    min_widths = np.full(3, inf)
    max_widths = np.zeros(3)
    max_edge_ratio = 0.0
    for k, (z0, z1) in enumerate(pairwise(z)):
        dz = float(z1 - z0)
        if dz <= 0.0:
            raise ValueError("gate_cd z intervals must be positive")
        for j in range(GATE_CD_CELLS[1]):
            yb = y_sections[k, j : j + 2]
            yt = y_sections[k + 1, j : j + 2]
            for i in range(GATE_CD_CELLS[0]):
                xb = x_sections[k, i : i + 2]
                xt = x_sections[k + 1, i : i + 2]
                wx0, wx1 = float(xb[1] - xb[0]), float(xt[1] - xt[0])
                wy0, wy1 = float(yb[1] - yb[0]), float(yt[1] - yt[0])
                if min(wx0, wx1, wy0, wy1, dz) <= 0.0:
                    raise ValueError("gate_cd swept cell has non-positive edge width")
                ax, bx = wx0, wx1 - wx0
                ay, by = wy0, wy1 - wy0
                c0 = ax * ay
                c1 = ax * by + ay * bx
                c2 = bx * by
                candidates = [0.0, 1.0]
                if c2 != 0.0:
                    t_vertex = -c1 / (2.0 * c2)
                    if 0.0 < t_vertex < 1.0:
                        candidates.append(t_vertex)
                determinant_samples = [
                    dz * (c0 + c1 * t + c2 * t * t) for t in candidates
                ]
                cell_min_det, cell_max_det = (
                    min(determinant_samples),
                    max(determinant_samples),
                )
                if cell_min_det <= 0.0:
                    raise ValueError("gate_cd analytic mapped Jacobian is not positive")
                min_det = min(min_det, cell_min_det)
                max_det = max(max_det, cell_max_det)
                min_widths = np.minimum(min_widths, (min(wx0, wx1), min(wy0, wy1), dz))
                max_widths = np.maximum(max_widths, (max(wx0, wx1), max(wy0, wy1), dz))
                edge_lengths = (
                    wx0,
                    wx1,
                    wy0,
                    wy1,
                    dz,
                    float(np.hypot(wx1 - wx0, dz)),
                    float(np.hypot(wy1 - wy0, dz)),
                )
                max_edge_ratio = max(
                    max_edge_ratio, max(edge_lengths) / min(edge_lengths)
                )
                xm, ym, zm = _cell_midpoint(xb, xt, yb, yt, z0, z1)
                label = gate_cd_material_label(xm, ym, zm)
                counts[label] += 1
                # Integrate dz*(wx0+bx*t)*(wy0+by*t) exactly on the affine map.
                volumes[label] += dz * (c0 + c1 / 2.0 + c2 / 3.0)

    if sum(counts.values()) != int(np.prod(GATE_CD_CELLS)):
        raise AssertionError(
            "gate_cd midpoint tags do not cover every cell exactly once"
        )
    if set(counts) != set(GATE_CD_REGION_TAGS):
        raise AssertionError("gate_cd plan omitted one or more physical materials")
    axes = {"x": x_sections, "y": y_sections, "z": z}
    hashes = {name: _axis_sha(values) for name, values in axes.items()}
    material_volume_totals: dict[str, float] = Counter()
    for label, volume in volumes.items():
        material = GATE_CD_REGION_MATERIAL[label]
        material_volume_totals[material] += float(volume)
    expected = {
        "Air": 327250.0,
        "Si": 70490.0,
        "SiGe": 10880.0,
        "SiN": 38250.0,
        "SiO2": 104030.0,
        "Si_poly": 74100.0,
    }
    if any(
        abs(material_volume_totals[key] - value) > 1e-7
        for key, value in expected.items()
    ):
        raise AssertionError(
            "gate_cd exact swept-cell material volume differs from user audit"
        )
    facts: dict[str, Any] = {
        "source_conditions_sha256": GATE_CD_CONDITIONS_SHA256,
        "cell_counts_xyz": list(GATE_CD_CELLS),
        "global_cell_count": int(np.prod(GATE_CD_CELLS)),
        "required_z_planes_nm": z.tolist(),
        "axis_hashes_sha256_le_f64": hashes,
        "periodic_boundaries_are_fixed_translations": True,
        "all_cross_section_widths_positive": True,
        "analytic_Q1_jacobian_min_nm3": min_det,
        "analytic_Q1_jacobian_max_nm3": max_det,
        "minimum_cell_dimensions_nm": min_widths.tolist(),
        "maximum_cell_dimensions_nm": max_widths.tolist(),
        "maximum_edge_aspect_ratio": max_edge_ratio,
        "midpoint_cell_counts_by_label": dict(sorted(counts.items())),
        "exact_affine_volume_by_label_nm3": dict(sorted(volumes.items())),
        "aggregated_volume_check_nm3": dict(sorted(material_volume_totals.items())),
        "total_volume_nm3": float(sum(volumes.values())),
        "z_interval_count": len(GATE_CD_REQUIRED_Z_PLANES_NM) - 1,
        "y_segment_counts": list(GATE_CD_Y_SEGMENT_CELLS),
    }
    hash_payload = json.dumps(
        facts, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("ascii")
    plan_sha = hashlib.sha256(hash_payload).hexdigest()
    return GateCdMeshPlan(
        z, x_sections, y_sections, dict(counts), hashes, plan_sha, facts
    )


def build_gate_cd_mesh(comm, plan: GateCdMeshPlan | None = None):
    """Build only the fixed gate_cd mesh and cell tags; no FE space is created."""

    if comm.size != 1:
        raise NotImplementedError("gate_cd mapped mesh QA is currently MPI1-only")
    # Keep profile/input identity imports usable without initializing MPI or
    # importing DOLFINx.  The FE mesh builder is needed only on the live QA
    # path after explicit qualification.
    from src.geometry.swept_hex_mesh import build_swept_hex_mesh

    selected = build_gate_cd_plan() if plan is None else plan
    flat_tags = np.empty(int(np.prod(GATE_CD_CELLS)), dtype=np.int32)
    cell = 0
    for k, (z0, z1) in enumerate(pairwise(selected.z)):
        for j in range(GATE_CD_CELLS[1]):
            yb = selected.y_sections[k, j : j + 2]
            yt = selected.y_sections[k + 1, j : j + 2]
            for i in range(GATE_CD_CELLS[0]):
                xb = selected.x_sections[k, i : i + 2]
                xt = selected.x_sections[k + 1, i : i + 2]
                xyz = _cell_midpoint(xb, xt, yb, yt, z0, z1)
                label = gate_cd_material_label(*xyz)
                flat_tags[cell] = GATE_CD_REGION_TAGS[label]
                cell += 1
    expected = Counter(
        {
            GATE_CD_REGION_TAGS[label]: count
            for label, count in selected.tag_counts.items()
        }
    )
    actual = Counter(int(value) for value in flat_tags)
    if actual != expected:
        raise AssertionError(
            "gate_cd live input-order tags differ from the independent plan"
        )
    msh, cell_tags = build_swept_hex_mesh(
        comm,
        selected.z,
        selected.x_sections,
        selected.y_sections,
        cell_tags=flat_tags,
        require_periodic_xy=True,
    )
    return msh, cell_tags, selected


def gate_cd_live_mesh_facts(msh, cell_tags, plan: GateCdMeshPlan) -> dict[str, Any]:
    """Compare post-create_mesh cells and geometry back to the frozen plan."""

    if msh.comm.size != 1:
        raise NotImplementedError("gate_cd live mesh evidence currently requires MPI1")
    tdim = msh.topology.dim
    owned = int(msh.topology.index_map(tdim).size_local)
    if owned != int(np.prod(GATE_CD_CELLS)):
        raise RuntimeError("live gate_cd owned cell count differs from frozen plan")
    actual = {
        str(tag): len(cell_tags.find(tag)) for tag in GATE_CD_REGION_TAGS.values()
    }
    expected = {
        str(GATE_CD_REGION_TAGS[label]): int(count)
        for label, count in plan.tag_counts.items()
    }
    if actual != expected:
        raise RuntimeError(f"live gate_cd material tags differ: {actual} != {expected}")
    coordinates = msh.geometry.x
    if not np.all(np.isfinite(coordinates)):
        raise RuntimeError("live gate_cd geometry contains non-finite coordinates")
    if not (
        np.isclose(coordinates[:, 0].min(), 0.0)
        and np.isclose(coordinates[:, 0].max(), 50.0)
        and np.isclose(coordinates[:, 1].min(), 0.0)
        and np.isclose(coordinates[:, 1].max(), 50.0)
        and np.isclose(coordinates[:, 2].min(), -10.0)
        and np.isclose(coordinates[:, 2].max(), 240.0)
    ):
        raise RuntimeError("live gate_cd mesh extents differ from the frozen domain")
    # Every input Q1 cell is an affine x/y-width product over its z interval.
    # The exact determinant check in the planner is repeated against all live
    # physical cell corners to catch ordering/remap changes in create_mesh.
    min_live_det = inf
    for cell in range(owned):
        vertices = coordinates[np.asarray(msh.geometry.dofmap[cell], dtype=np.int64)]
        if vertices.shape != (8, 3):
            raise RuntimeError(
                "live gate_cd Q1 cell does not have eight geometry nodes"
            )
        bottom = vertices[:4]
        top = vertices[4:]
        wx0 = float(bottom[1, 0] - bottom[0, 0])
        wy0 = float(bottom[2, 1] - bottom[0, 1])
        wx1 = float(top[1, 0] - top[0, 0])
        wy1 = float(top[2, 1] - top[0, 1])
        dz = float(top[0, 2] - bottom[0, 2])
        if min(wx0, wy0, wx1, wy1, dz) <= 0.0:
            raise RuntimeError("live gate_cd cell has a non-positive mapped width")
        bx, by = wx1 - wx0, wy1 - wy0
        c0, c1, c2 = wx0 * wy0, wx0 * by + wy0 * bx, bx * by
        ts = [0.0, 1.0]
        if c2 != 0.0:
            vertex_t = -c1 / (2.0 * c2)
            if 0.0 < vertex_t < 1.0:
                ts.append(vertex_t)
        min_live_det = min(min_live_det, *(dz * (c0 + c1 * t + c2 * t * t) for t in ts))
    if min_live_det <= 0.0:
        raise RuntimeError("live gate_cd mapped Jacobian is not positive")
    actual_z = np.unique(np.asarray(coordinates[:, 2], dtype=np.float64))
    if not np.array_equal(actual_z, plan.z):
        raise RuntimeError("live gate_cd z planes differ from the frozen plan")
    actual_x_sections = np.empty_like(plan.x_sections)
    actual_y_sections = np.empty_like(plan.y_sections)
    for section_index, z_value in enumerate(actual_z):
        section_mask = np.asarray(coordinates[:, 2] == z_value, dtype=bool)
        actual_x = np.unique(np.asarray(coordinates[section_mask, 0], dtype=np.float64))
        actual_y = np.unique(np.asarray(coordinates[section_mask, 1], dtype=np.float64))
        if actual_x.shape != actual_x_sections[section_index].shape:
            raise RuntimeError("live gate_cd x-section node count differs from plan")
        if actual_y.shape != actual_y_sections[section_index].shape:
            raise RuntimeError("live gate_cd y-section node count differs from plan")
        actual_x_sections[section_index] = actual_x
        actual_y_sections[section_index] = actual_y
    if not np.array_equal(actual_x_sections, plan.x_sections):
        raise RuntimeError("live gate_cd x-section coordinates differ from plan")
    if not np.array_equal(actual_y_sections, plan.y_sections):
        raise RuntimeError("live gate_cd y-section coordinates differ from plan")
    actual_axis_hashes = {
        "x": _axis_sha(actual_x_sections),
        "y": _axis_sha(actual_y_sections),
        "z": _axis_sha(actual_z),
    }
    if actual_axis_hashes != plan.axis_hashes:
        raise RuntimeError("live gate_cd axis hashes differ from the frozen plan")
    return {
        "status": "PASS",
        "scope": "LIVE_MESH_ONLY_NO_FE_SPACE_OR_MATRIX",
        "owned_cells": owned,
        "axis_cell_counts": list(GATE_CD_CELLS),
        "axis_hashes_sha256_le_f64": actual_axis_hashes,
        "cell_tag_counts_by_tag": actual,
        "expected_cell_tag_counts_by_tag": expected,
        "domain_nm": [[0.0, 50.0], [0.0, 50.0], [-10.0, 240.0]],
        "live_q1_analytic_jacobian_min_nm3": min_live_det,
        "planner_q1_analytic_jacobian_min_nm3": float(
            plan.static_facts["analytic_Q1_jacobian_min_nm3"]
        ),
        "cell_geometry_identity": "post-create_mesh exact vertex remap; all Q1 swept-cell corners checked",
        "vtk_family_outputs": "NOT_WRITTEN",
    }


GATE_CD_STATIC_PLAN = build_gate_cd_plan()
