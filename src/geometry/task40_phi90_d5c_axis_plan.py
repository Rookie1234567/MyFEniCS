"""Frozen Task40 D5C 5 nm coarse-grid one-axis study.

D5C is intentionally separate from historical D5. Every non-baseline case
changes exactly one axis from the unique 2/2/2-per-material-segment baseline.
"""

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

D5C_CASE_SEGMENT_COUNTS = {
    "B": {"x": (2, 2, 2), "y": (2, 2, 2), "z": (2, 2, 2)},
    "X1": {"x": (2, 6, 2), "y": (2, 2, 2), "z": (2, 2, 2)},
    "X2": {"x": (5, 6, 5), "y": (2, 2, 2), "z": (2, 2, 2)},
    "X3": {"x": (7, 6, 7), "y": (2, 2, 2), "z": (2, 2, 2)},
    "Y1": {"x": (2, 2, 2), "y": (2, 6, 2), "z": (2, 2, 2)},
    "Y2": {"x": (2, 2, 2), "y": (5, 6, 5), "z": (2, 2, 2)},
    "Y3": {"x": (2, 2, 2), "y": (7, 6, 7), "z": (2, 2, 2)},
    "Y4": {"x": (2, 2, 2), "y": (5, 10, 5), "z": (2, 2, 2)},
    "Y5": {"x": (2, 2, 2), "y": (10, 6, 10), "z": (2, 2, 2)},
    "Z1": {"x": (2, 2, 2), "y": (2, 2, 2), "z": (2, 6, 2)},
    "Z2": {"x": (2, 2, 2), "y": (2, 2, 2), "z": (5, 6, 5)},
    "Z3": {"x": (2, 2, 2), "y": (2, 2, 2), "z": (7, 6, 7)},
}


def _uniform_segment(start: float, stop: float, cells: int) -> tuple[float, ...]:
    return tuple(start + (stop - start) * index / cells for index in range(cells + 1))


def _piecewise_axis(axis: str, counts: tuple[int, int, int]) -> tuple[float, ...]:
    breakpoints = MATERIAL_INTERVALS_NM[axis]
    values: list[float] = []
    for (start, stop), cells in zip(pairwise(breakpoints), counts, strict=True):
        segment = _uniform_segment(start, stop, cells)
        values.extend(segment if not values else segment[1:])
    return tuple(values)


def axis_sha256_le_f64(values: tuple[float, ...]) -> str:
    return hashlib.sha256(struct.pack(f"<{len(values)}d", *values)).hexdigest()


def _segment_counts(axis: tuple[float, ...], axis_name: str) -> tuple[int, int, int]:
    breakpoints = MATERIAL_INTERVALS_NM[axis_name]
    return tuple(
        sum(left >= lo and right <= hi for left, right in pairwise(axis))
        for lo, hi in pairwise(breakpoints)
    )  # type: ignore[return-value]


def _expected_tags(segment_counts: Mapping[str, tuple[int, int, int]]) -> dict[str, int]:
    nx = sum(segment_counts["x"])
    ny = sum(segment_counts["y"])
    nz = sum(segment_counts["z"])
    substrate = nx * ny * segment_counts["z"][0]
    grating = (
        segment_counts["x"][1]
        * segment_counts["y"][1]
        * segment_counts["z"][1]
    )
    return {"1": nx * ny * nz - substrate - grating, "2": substrate, "3": grating}


def d5c_axis_plan(case: str) -> dict[str, object]:
    """Return a frozen D5C baseline or one-axis variant, never an old D5 plan."""
    if case not in D5C_CASE_SEGMENT_COUNTS:
        raise ValueError(f"unsupported Task40 D5C case {case!r}")
    segments = D5C_CASE_SEGMENT_COUNTS[case]
    axes = {axis: _piecewise_axis(axis, segments[axis]) for axis in "xyz"}
    actual_segments = {axis: _segment_counts(axes[axis], axis) for axis in "xyz"}
    if actual_segments != segments:
        raise AssertionError(f"D5C {case} material-segment counts changed: {actual_segments}")
    cell_counts = tuple(len(axes[axis]) - 1 for axis in "xyz")
    parent_segments = D5C_CASE_SEGMENT_COUNTS["B"]
    parent_axes = {axis: _piecewise_axis(axis, parent_segments[axis]) for axis in "xyz"}
    parent_hashes = {axis: axis_sha256_le_f64(parent_axes[axis]) for axis in "xyz"}
    hashes = {axis: axis_sha256_le_f64(axes[axis]) for axis in "xyz"}
    changed = [axis for axis in "xyz" if hashes[axis] != parent_hashes[axis]]
    if case == "B":
        if changed:
            raise AssertionError("D5C baseline axes differ from their own parent")
        changed_axis = None
    else:
        expected_axis = case[0].lower()
        if changed != [expected_axis]:
            raise AssertionError(f"D5C {case} must change only {expected_axis}: {changed}")
        changed_axis = expected_axis
    lengths = {
        axis: tuple(right - left for left, right in pairwise(axes[axis]))
        for axis in "xyz"
    }
    min_edge = min(min(values) for values in lengths.values())
    max_edge = max(max(values) for values in lengths.values())
    max_aspect = max(
        max(dx, dy, dz) / min(dx, dy, dz)
        for dx in lengths["x"]
        for dy in lengths["y"]
        for dz in lengths["z"]
    )
    min_volume = min(
        dx * dy * dz
        for dx in lengths["x"]
        for dy in lengths["y"]
        for dz in lengths["z"]
    )
    payload = {
        "schema": "task40.phi90.d5c.axis_plan.v1",
        "display_name": f"D5C-{case}",
        "case": case,
        "parent_case": "B",
        "changed_axis": changed_axis,
        "segment_cell_counts": {axis: list(actual_segments[axis]) for axis in "xyz"},
        "segment_step_nm": {
            axis: [
                (stop - start) / cells
                for (start, stop), cells in zip(
                    pairwise(MATERIAL_INTERVALS_NM[axis]),
                    actual_segments[axis],
                    strict=True,
                )
            ]
            for axis in "xyz"
        },
        "axis_cell_counts": list(cell_counts),
        "axes_nm": {axis: list(axes[axis]) for axis in "xyz"},
        "axis_sha256_le_f64": hashes,
        "parent_axis_sha256_le_f64": parent_hashes,
        "expected_material_tag_counts": _expected_tags(actual_segments),
        "static_geometry_only": {
            "method": "independent_axis_interval products; not a live mesh/Jacobian QA",
            "minimum_edge_nm": min_edge,
            "maximum_edge_nm": max_edge,
            "maximum_cell_aspect_ratio": max_aspect,
            "minimum_cell_volume_nm3": min_volume,
            "axis_aligned_cell_jacobian_determinant_positive": True,
            "strictly_increasing_axes": True,
            "material_and_periodic_endpoints_preserved": True,
        },
    }
    plan_sha = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    payload["mesh_plan_id"] = f"task40_phi90_d5c_{case.lower()}_axes_v1"
    payload["mesh_plan_sha256"] = plan_sha
    payload["expected_global_cell_count"] = math.prod(cell_counts)
    return payload


D5C_AXIS_PLANS = {case: d5c_axis_plan(case) for case in D5C_CASE_SEGMENT_COUNTS}
D5C_AXIS_PLAN_IDS = {
    str(plan["mesh_plan_id"]): case for case, plan in D5C_AXIS_PLANS.items()
}
D5C_BASE_AXES_NM = D5C_AXIS_PLANS["B"]["axes_nm"]
D5C_BASE_AXIS_SHA256_LE_F64 = D5C_AXIS_PLANS["B"]["axis_sha256_le_f64"]


def validate_frozen_d5c_axes(payload: Mapping[str, object]) -> dict[str, tuple[float, ...]]:
    """Validate D5C plan identity, cell counts, exact coordinates, and hashes."""
    plan_id = str(payload.get("mesh_plan_id") or "")
    case = D5C_AXIS_PLAN_IDS.get(plan_id)
    if case is None:
        raise ValueError(f"unsupported Task40 D5C frozen mesh plan {plan_id!r}")
    plan = D5C_AXIS_PLANS[case]
    if str(payload.get("mesh_plan_sha256") or "") != plan["mesh_plan_sha256"]:
        raise ValueError("Task40 D5C frozen mesh plan SHA256 mismatch")
    counts = tuple(payload.get("mesh_axis_cell_counts") or ())
    if counts != tuple(plan["axis_cell_counts"]):
        raise ValueError("Task40 D5C frozen mesh axis cell counts mismatch")
    axes: dict[str, tuple[float, ...]] = {}
    for axis in "xyz":
        raw = payload.get(f"mesh_axis_{axis}_values")
        if not isinstance(raw, (list, tuple)):
            raise TypeError(f"Task40 D5C frozen mesh requires {axis} coordinates")
        values = tuple(float(value) for value in raw)
        expected = tuple(plan["axes_nm"][axis])
        if values != expected:
            raise ValueError(f"Task40 D5C frozen {axis} coordinates differ from plan")
        if axis_sha256_le_f64(values) != plan["axis_sha256_le_f64"][axis]:
            raise ValueError(f"Task40 D5C frozen {axis} axis SHA256 mismatch")
        if any(right <= left for left, right in pairwise(values)):
            raise ValueError(f"Task40 D5C frozen {axis} axis must increase")
        axes[axis] = values
    return axes
