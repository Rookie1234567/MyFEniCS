"""Frozen Task40 13.5 nm h15 axes and one-axis midpoint refinements.

The h15 base coordinates are taken from the reviewed boundary-fitted
``stage4_axis_plan`` result.  X/Y/Z bisect every actual interval of that base
axis and leave the other coordinate arrays exactly unchanged.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from collections.abc import Mapping
from itertools import pairwise

H15_BASE_AXES_NM: dict[str, tuple[float, ...]] = {
    "x": (0.0, 8.25, 16.5, 25.0, 33.5, 41.75, 50.0),
    "y": (0.0, 15.0, 25.0, 35.0, 50.0),
    "z": (-10.0, 0.0, 15.0, 30.0, 45.0, 60.0, 75.0, 90.0, 105.0, 120.0, 130.0),
}
H15_BASE_AXIS_SHA256_LE_F64 = {
    axis: hashlib.sha256(struct.pack(f"<{len(values)}d", *values)).hexdigest()
    for axis, values in H15_BASE_AXES_NM.items()
}
H15_CASES = {
    "B": {"changed_axis": None, "axis_cell_counts": (6, 4, 10)},
    "X": {"changed_axis": "x", "axis_cell_counts": (12, 4, 10)},
    "Y": {"changed_axis": "y", "axis_cell_counts": (6, 8, 10)},
    "Z": {"changed_axis": "z", "axis_cell_counts": (6, 4, 20)},
    "YZ480": {
        "changed_axis": None,
        "changed_axes": ("y", "z"),
        "parent_case": "Y",
        "axis_cell_counts": (6, 10, 8),
        "axes_nm": {
            "x": (0.0, 8.25, 16.5, 25.0, 33.5, 41.75, 50.0),
            "y": (
                0.0,
                7.5,
                15.0,
                18.333333333333332,
                21.666666666666668,
                25.0,
                28.333333333333336,
                31.666666666666668,
                35.0,
                42.5,
                50.0,
            ),
            "z": (-10.0, 0.0, 15.0, 37.5, 60.0, 82.5, 105.0, 120.0, 130.0),
        },
    },
}
_MATERIAL_INTERVALS = {
    "x": (0.0, 16.5, 33.5, 50.0),
    "y": (0.0, 15.0, 35.0, 50.0),
    "z": (-10.0, 0.0, 120.0, 130.0),
}


def _bisect_every_interval(values: tuple[float, ...]) -> tuple[float, ...]:
    result: list[float] = [values[0]]
    for left, right in pairwise(values):
        result.extend((left + (right - left) / 2.0, right))
    return tuple(result)


def _axis_sha256(values: tuple[float, ...]) -> str:
    return hashlib.sha256(struct.pack(f"<{len(values)}d", *values)).hexdigest()


def _segment_counts(axis: tuple[float, ...], breakpoints: tuple[float, ...]) -> list[int]:
    return [
        sum(left >= low and right <= high for left, right in pairwise(axis))
        for low, high in pairwise(breakpoints)
    ]


def h15_axis_plan(case: str) -> dict[str, object]:
    """Return a deterministic frozen H15 or approved 480-cell axis plan."""
    if case not in H15_CASES:
        raise ValueError(f"unsupported Task40 h15 case {case!r}")
    facts = H15_CASES[case]
    changed_axis = facts["changed_axis"]
    if "axes_nm" in facts:
        axes = {
            axis: tuple(values)
            for axis, values in facts["axes_nm"].items()
        }
    else:
        axes = {
            axis: (
                _bisect_every_interval(values)
                if axis == changed_axis
                else values
            )
            for axis, values in H15_BASE_AXES_NM.items()
        }
    counts = tuple(len(axes[axis]) - 1 for axis in ("x", "y", "z"))
    if counts != tuple(H15_CASES[case]["axis_cell_counts"]):
        raise AssertionError(f"Task40 h15 {case} axis counts are inconsistent: {counts}")
    if any(
        tuple(sorted(set(axes[axis]))) != axes[axis]
        for axis in ("x", "y", "z")
    ):
        raise AssertionError(f"Task40 h15 {case} axes must be strictly increasing")
    segment_counts = {
        axis: _segment_counts(axes[axis], _MATERIAL_INTERVALS[axis])
        for axis in ("x", "y", "z")
    }
    if case == "B" and segment_counts != {
        "x": [2, 2, 2], "y": [1, 2, 1], "z": [1, 8, 1]
    }:
        raise AssertionError(f"Task40 h15 base material segmentation changed: {segment_counts}")
    parent_case = facts.get("parent_case", None if case == "B" else "B")
    if case == "YZ480":
        parent_axes = h15_axis_plan(str(parent_case))["axes_nm"]
        parent_hashes = {
            axis: _axis_sha256(tuple(parent_axes[axis]))
            for axis in ("x", "y", "z")
        }
    else:
        parent_hashes = H15_BASE_AXIS_SHA256_LE_F64
    payload = {
        "schema": "task40.phi90.h15.axis_plan.v1",
        "case": case,
        "parent_case": parent_case,
        "changed_axis": changed_axis,
        "axes_nm": {axis: list(values) for axis, values in axes.items()},
        "axis_cell_counts": list(counts),
        "segment_cell_counts": segment_counts,
        "parent_axis_sha256_le_f64": dict(parent_hashes),
    }
    if "changed_axes" in facts:
        payload["changed_axes"] = list(facts["changed_axes"])
    plan_sha256 = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        **payload,
        "plan_id": (
            "task40_phi90_h15_yz480_480_axes_v1"
            if case == "YZ480"
            else f"task40_phi90_h15_{case.lower()}_axes_v1"
        ),
        "mesh_plan_sha256": plan_sha256,
        "actual_axis_sha256_le_f64": {
            axis: _axis_sha256(values) for axis, values in axes.items()
        },
        "expected_global_cell_count": math.prod(counts),
    }


H15_AXIS_PLANS = {case: h15_axis_plan(case) for case in H15_CASES}
H15_AXIS_PLAN_IDS = {
    str(plan["plan_id"]): case for case, plan in H15_AXIS_PLANS.items()
}


def validate_frozen_h15_axes(payload: Mapping[str, object]) -> dict[str, tuple[float, ...]]:
    """Fail closed on altered H15 plan identity, counts, or axis coordinates."""
    plan_id = payload.get("mesh_plan_id")
    case = H15_AXIS_PLAN_IDS.get(str(plan_id))
    if case is None:
        raise ValueError(f"unsupported Task40 H15 frozen axis plan {plan_id!r}")
    plan = H15_AXIS_PLANS[case]
    if payload.get("mesh_plan_sha256") != plan["mesh_plan_sha256"]:
        raise ValueError("Task40 H15 frozen mesh plan SHA256 mismatch")
    if tuple(payload.get("mesh_axis_cell_counts") or ()) != tuple(
        plan["axis_cell_counts"]
    ):
        raise ValueError("Task40 H15 frozen mesh axis cell counts mismatch")
    axes: dict[str, tuple[float, ...]] = {}
    for axis in ("x", "y", "z"):
        raw = payload.get(f"mesh_axis_{axis}_values")
        if raw is None:
            raise ValueError(f"Task40 H15 frozen mesh requires {axis} coordinates")
        try:
            values = tuple(float(value) for value in raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Task40 H15 frozen {axis} coordinates are invalid") from exc
        expected = tuple(float(value) for value in plan["axes_nm"][axis])
        if values != expected:
            raise ValueError(f"Task40 H15 frozen {axis} coordinates differ from plan")
        axes[axis] = values
    return axes
