"""Frozen Task40 D07C 0.7 nm mesh axes for the finite M32/N[-143,1] study."""

from __future__ import annotations

import hashlib
import json
import math
import struct
from collections.abc import Mapping
from itertools import pairwise

MATERIAL_INTERVALS_NM = {
    "x": (0.0, 16.5, 33.5, 50.0),
    "y": (0.0, 15.0, 35.0, 50.0),
    "z": (-10.0, 0.0, 120.0, 130.0),
}
D07C_CASE_SEGMENT_COUNTS = {
    "B": {"x": (2, 2, 2), "y": (10, 6, 10), "z": (2, 2, 2)},
    "Y1": {"x": (2, 2, 2), "y": (12, 6, 12), "z": (2, 2, 2)},
    "Y2": {"x": (2, 2, 2), "y": (10, 10, 10), "z": (2, 2, 2)},
    # Exact bisection of every B y interval; x/z remain frozen.
    "Y3": {"x": (2, 2, 2), "y": (20, 12, 20), "z": (2, 2, 2)},
    "G2": {"x": (2, 2, 2), "y": (20, 28, 20), "z": (2, 4, 2)},
    "G3": {"x": (2, 2, 2), "y": (30, 40, 30), "z": (2, 4, 2)},
}

def _uniform_segment(start: float, stop: float, cells: int) -> tuple[float, ...]:
    return tuple(start + (stop - start) * index / cells for index in range(cells + 1))

def _piecewise_axis(axis: str, counts: tuple[int, int, int]) -> tuple[float, ...]:
    values: list[float] = []
    for (start, stop), cells in zip(pairwise(MATERIAL_INTERVALS_NM[axis]), counts, strict=True):
        segment = _uniform_segment(start, stop, cells)
        values.extend(segment if not values else segment[1:])
    return tuple(values)

def _axis_digest(values: tuple[float, ...]) -> str:
    return hashlib.sha256(struct.pack(f"<{len(values)}d", *values)).hexdigest()

def _independent_midpoint_tags(axes: Mapping[str, tuple[float, ...]]) -> dict[str, int]:
    tags = {"1": 0, "2": 0, "3": 0}
    for x0, x1 in pairwise(axes["x"]):
        x = (x0 + x1) / 2.0
        for y0, y1 in pairwise(axes["y"]):
            y = (y0 + y1) / 2.0
            for z0, z1 in pairwise(axes["z"]):
                z = (z0 + z1) / 2.0
                if z < 0.0:
                    tag = "2"
                elif z < 120.0 and 16.5 < x < 33.5 and 15.0 < y < 35.0:
                    tag = "3"
                else:
                    tag = "1"
                tags[tag] += 1
    return tags

def d07c_axis_plan(case: str) -> dict[str, object]:
    if case not in D07C_CASE_SEGMENT_COUNTS:
        raise ValueError(f"unsupported Task40 D07C case {case!r}")
    segments = D07C_CASE_SEGMENT_COUNTS[case]
    axes = {axis: _piecewise_axis(axis, segments[axis]) for axis in "xyz"}
    counts = tuple(len(axes[axis]) - 1 for axis in "xyz")
    parent_axes = {
        axis: _piecewise_axis(axis, D07C_CASE_SEGMENT_COUNTS["B"][axis])
        for axis in "xyz"
    }
    if case == "Y3":
        # Preserve every B coordinate bit-for-bit and insert its exact midpoint.
        parent_y = parent_axes["y"]
        axes["y"] = tuple(
            value for left, right in pairwise(parent_y)
            for value in (left, (left + right) / 2.0)
        ) + (parent_y[-1],)
    hashes = {axis: _axis_digest(axes[axis]) for axis in "xyz"}
    parent_hashes = {axis: _axis_digest(parent_axes[axis]) for axis in "xyz"}
    changed = [axis for axis in "xyz" if hashes[axis] != parent_hashes[axis]]
    expected_changed = [] if case == "B" else (["y", "z"] if case in {"G2", "G3"} else ["y"])
    if changed != expected_changed:
        raise AssertionError(f"D07C-{case} changed axes {changed}, expected {expected_changed}")
    edge_lengths = {
        axis: tuple(right - left for left, right in pairwise(axes[axis]))
        for axis in "xyz"
    }
    minimum_edge = min(min(values) for values in edge_lengths.values())
    maximum_edge = max(max(values) for values in edge_lengths.values())
    maximum_aspect = max(
        max(dx, dy, dz) / min(dx, dy, dz)
        for dx in edge_lengths["x"] for dy in edge_lengths["y"] for dz in edge_lengths["z"]
    )
    minimum_volume = min(
        dx * dy * dz
        for dx in edge_lengths["x"] for dy in edge_lengths["y"] for dz in edge_lengths["z"]
    )
    tags = _independent_midpoint_tags(axes)
    expected_cells = math.prod(counts)
    if sum(tags.values()) != expected_cells:
        raise AssertionError("D07C independent midpoint tag counts do not cover the grid")
    if case == "B" and (counts, tags) != ((6, 26, 6), {"1": 600, "2": 312, "3": 24}):
        raise AssertionError(f"D07C-B static geometry changed: {counts}, {tags}")
    expected_refined = {
        "Y1": {"1": 696, "2": 360, "3": 24},
        "Y2": {"1": 680, "2": 360, "3": 40},
    }
    if case in expected_refined and (counts, tags) != ((6, 30, 6), expected_refined[case]):
        raise AssertionError(f"D07C-{case} static geometry changed: {counts}, {tags}")
    plan = {
        "schema": "task40.phi90.d07c.axis_plan.v1",
        "display_name": f"D07C-{case}",
        "case": case,
        "parent_case": "B",
        "changed_axis": None if case == "B" else ("yz" if case in {"G2", "G3"} else "y"),
        "segment_cell_counts": {axis: list(segments[axis]) for axis in "xyz"},
        "axes_nm": {axis: list(axes[axis]) for axis in "xyz"},
        "axis_cell_counts": list(counts),
        "axis_sha256_le_f64": hashes,
        "parent_axis_sha256_le_f64": parent_hashes,
        "expected_global_cell_count": expected_cells,
        "expected_material_tag_counts": tags,
        "static_geometry_only": {
            "method": "independent_cell_midpoint_classification; not live mesh QA",
            "strictly_increasing_axes": all(
                all(right > left for left, right in pairwise(axes[axis])) for axis in "xyz"
            ),
            "axis_aligned_cell_jacobian_determinant_positive": minimum_volume > 0.0,
            "minimum_edge_nm": minimum_edge,
            "maximum_edge_nm": maximum_edge,
            "maximum_cell_aspect_ratio": maximum_aspect,
            "minimum_cell_volume_nm3": minimum_volume,
            "material_and_periodic_endpoints_preserved": True,
        },
    }
    if case in {"G2", "G3"}:
        plan["changed_axes"] = ["y", "z"]
    plan_sha = hashlib.sha256(
        json.dumps(plan, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
    plan["mesh_plan_id"] = f"task40_phi90_d07c_{case.lower()}_axes_v1"
    plan["mesh_plan_sha256"] = plan_sha
    return plan

D07C_AXIS_PLANS = {case: d07c_axis_plan(case) for case in D07C_CASE_SEGMENT_COUNTS}
D07C_AXIS_PLAN_IDS = {str(plan["mesh_plan_id"]): case for case, plan in D07C_AXIS_PLANS.items()}


def validate_frozen_d07c_axes(payload: Mapping[str, object]) -> dict[str, tuple[float, ...]]:
    plan_id = str(payload.get("mesh_plan_id") or "")
    case = D07C_AXIS_PLAN_IDS.get(plan_id)
    if case is None:
        raise ValueError(f"unsupported Task40 D07C frozen mesh plan {plan_id!r}")
    plan = D07C_AXIS_PLANS[case]
    if payload.get("mesh_plan_sha256") != plan["mesh_plan_sha256"]:
        raise ValueError("D07C mesh plan SHA256 differs from the frozen plan")
    try:
        counts = tuple(int(value) for value in payload.get("mesh_axis_cell_counts", ()))
        axes = {
            axis: tuple(float(value) for value in payload.get(f"mesh_axis_{axis}_values", ()))
            for axis in "xyz"
        }
    except (TypeError, ValueError) as exc:
        raise ValueError("D07C explicit axis payload is malformed") from exc
    if counts != tuple(plan["axis_cell_counts"]):
        raise ValueError("D07C mesh axis cell counts differ from the frozen plan")
    if any(axes[axis] != tuple(plan["axes_nm"][axis]) for axis in "xyz"):
        raise ValueError("D07C mesh axis coordinates differ from the frozen plan")
    digests = {axis: _axis_digest(axes[axis]) for axis in "xyz"}
    if digests != plan["axis_sha256_le_f64"]:
        raise ValueError("D07C mesh axis hashes differ from the frozen plan")
    return axes
