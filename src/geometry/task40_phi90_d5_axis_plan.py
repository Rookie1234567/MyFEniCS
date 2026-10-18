"""Frozen Task40 5 nm budgeted anisotropic axes and one-axis refinements.

The baseline keeps the nominal 7,020-cell budget while reallocating cells
toward the fast y propagation direction using the Task40 D13 evidence. Each
directional case bisects every realized interval on exactly one axis.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from collections.abc import Mapping
from itertools import pairwise


def _piecewise(values_by_segment: tuple[tuple[float, ...], ...]) -> tuple[float, ...]:
    result: list[float] = []
    for segment in values_by_segment:
        if not result:
            result.extend(segment)
        else:
            if result[-1] != segment[0]:
                raise ValueError("piecewise axis segments must share endpoints")
            result.extend(segment[1:])
    return tuple(result)


def _uniform_segment(start: float, stop: float, cells: int) -> tuple[float, ...]:
    count = int(cells)
    return tuple(start + (stop - start) * index / count for index in range(count + 1))


D5_BASE_AXES_NM: dict[str, tuple[float, ...]] = {
    # 10 cells: [3, 4, 3] across the x-material intervals.
    "x": _piecewise(
        (
            _uniform_segment(0.0, 16.5, 3),
            _uniform_segment(16.5, 33.5, 4),
            _uniform_segment(33.5, 50.0, 3),
        )
    ),
    # 23 cells: [7, 9, 7], with the y-material planes kept exact.
    "y": _piecewise(
        (
            _uniform_segment(0.0, 15.0, 7),
            _uniform_segment(15.0, 35.0, 9),
            _uniform_segment(35.0, 50.0, 7),
        )
    ),
    # 30 cells: [4, 22, 4]. Near z=0 and z=120, intervals are graded
    # toward the material interfaces; ports remain exactly at -10 and 130.
    "z": _piecewise(
        (
            (-10.0, -7.5, -5.0, -2.5, 0.0),
            (
                0.0, 1.0, 3.0, 7.0, 15.0,
                *(15.0 + 90.0 * index / 14.0 for index in range(1, 15)),
                113.0, 117.0, 119.0, 120.0,
            ),
            (120.0, 122.5, 125.0, 127.5, 130.0),
        )
    ),
}


def _axis_sha256(values: tuple[float, ...]) -> str:
    return hashlib.sha256(struct.pack(f"<{len(values)}d", *values)).hexdigest()


D5_BASE_AXIS_SHA256_LE_F64 = {
    axis: _axis_sha256(values) for axis, values in D5_BASE_AXES_NM.items()
}


def _bisect_every_interval(values: tuple[float, ...]) -> tuple[float, ...]:
    result: list[float] = [values[0]]
    for left, right in pairwise(values):
        result.extend((left + (right - left) / 2.0, right))
    return tuple(result)


def _segment_counts(
    axis: tuple[float, ...], breakpoints: tuple[float, ...]
) -> list[int]:
    return [
        sum(left >= low and right <= high for left, right in pairwise(axis))
        for low, high in pairwise(breakpoints)
    ]


D5_CASES = {
    "B": {"changed_axis": None, "axis_cell_counts": (10, 23, 30)},
    "X": {"changed_axis": "x", "axis_cell_counts": (20, 23, 30)},
    "Y": {"changed_axis": "y", "axis_cell_counts": (10, 46, 30)},
    "Z": {"changed_axis": "z", "axis_cell_counts": (10, 23, 60)},
}
_MATERIAL_INTERVALS = {
    "x": (0.0, 16.5, 33.5, 50.0),
    "y": (0.0, 15.0, 35.0, 50.0),
    "z": (-10.0, 0.0, 120.0, 130.0),
}


def d5_axis_plan(case: str) -> dict[str, object]:
    """Return the D5 budgeted baseline or a true one-axis midpoint refinement."""
    if case not in D5_CASES:
        raise ValueError(f"unsupported Task40 D5 case {case!r}")
    facts = D5_CASES[case]
    changed_axis = facts["changed_axis"]
    axes = {
        axis: (
            _bisect_every_interval(values)
            if axis == changed_axis
            else values
        )
        for axis, values in D5_BASE_AXES_NM.items()
    }
    counts = tuple(len(axes[axis]) - 1 for axis in ("x", "y", "z"))
    if counts != tuple(facts["axis_cell_counts"]):
        raise AssertionError(f"Task40 D5 {case} axis counts are inconsistent: {counts}")
    segment_counts = {
        axis: _segment_counts(axes[axis], _MATERIAL_INTERVALS[axis])
        for axis in ("x", "y", "z")
    }
    expected_segments = (
        {"x": [3, 4, 3], "y": [7, 9, 7], "z": [4, 22, 4]}
        if case == "B"
        else None
    )
    if expected_segments is not None and segment_counts != expected_segments:
        raise AssertionError(
            f"Task40 D5 baseline material segmentation changed: {segment_counts}"
        )
    parent_hashes = dict(D5_BASE_AXIS_SHA256_LE_F64)
    axis_hashes = {axis: _axis_sha256(values) for axis, values in axes.items()}
    payload = {
        "schema": "task40.phi90.d5.axis_plan.v1",
        "case": case,
        "parent_case": "B",
        "changed_axis": changed_axis,
        "axes_nm": {axis: list(values) for axis, values in axes.items()},
        "axis_cell_counts": list(counts),
        "segment_cell_counts": segment_counts,
        "parent_axis_sha256_le_f64": parent_hashes,
    }
    plan_sha = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        **payload,
        "plan_id": f"task40_phi90_d5_{case.lower()}_budgeted_axes_v1",
        "mesh_plan_sha256": plan_sha,
        "actual_axis_sha256_le_f64": axis_hashes,
        "expected_global_cell_count": math.prod(counts),
    }


D5_AXIS_PLANS = {case: d5_axis_plan(case) for case in D5_CASES}
D5_AXIS_PLAN_IDS = {
    str(plan["plan_id"]): case for case, plan in D5_AXIS_PLANS.items()
}


def validate_frozen_d5_axes(payload: Mapping[str, object]) -> dict[str, tuple[float, ...]]:
    """Validate all coordinates and declared parent-lineage hashes."""
    plan_id = str(payload.get("mesh_plan_id") or "")
    case = D5_AXIS_PLAN_IDS.get(plan_id)
    if case is None:
        raise ValueError(f"unsupported Task40 D5 frozen mesh plan {plan_id!r}")
    plan = D5_AXIS_PLANS[case]
    if str(payload.get("mesh_plan_sha256") or "") != plan["mesh_plan_sha256"]:
        raise ValueError("Task40 D5 frozen mesh plan SHA256 mismatch")
    counts = tuple(payload.get("mesh_axis_cell_counts") or ())
    if counts != tuple(plan["axis_cell_counts"]):
        raise ValueError("Task40 D5 frozen mesh axis cell counts mismatch")
    axes: dict[str, tuple[float, ...]] = {}
    for axis in ("x", "y", "z"):
        raw = payload.get(f"mesh_axis_{axis}_values")
        if not isinstance(raw, (list, tuple)):
            raise TypeError(f"Task40 D5 frozen mesh requires {axis} coordinates")
        values = tuple(float(value) for value in raw)
        if values != tuple(plan["axes_nm"][axis]):
            raise ValueError(f"Task40 D5 frozen {axis} coordinates differ from plan")
        if any(right <= left for left, right in pairwise(values)):
            raise ValueError(f"Task40 D5 frozen {axis} coordinates must increase")
        axes[axis] = values
    return axes
