"""Frozen Task40 D13 axes derived by bisecting actual parent intervals.

The X/Y/Z cases are genuine one-axis refinements: every interval in the
selected D13-B axis gets one midpoint, while the other two coordinate arrays
remain byte-for-byte identical to the recorded D13-B axes.

Y2 is the first y-only refinement: it bisects each actual D13-Y interval and
retains the D13-Y x/z arrays exactly. Y3 bisects every actual Y2 y interval
and retains the Y2 x/z arrays exactly. X2 bisects every actual Y2 x interval
and retains the Y2 y/z arrays exactly.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from collections.abc import Mapping
from itertools import pairwise

D13_B_AXES_NM = {
    "x": (0.0, 8.25, 16.5, 25.0, 33.5, 41.75, 50.0),
    "y": (0.0, 7.5, 15.0, 25.0, 35.0, 42.5, 50.0),
    "z": (-10.0, *tuple(float(v) for v in range(0, 121, 10)), 130.0),
}
D13_B_AXIS_SHA256_LE_F64 = {
    axis: hashlib.sha256(struct.pack(f"<{len(values)}d", *values)).hexdigest()
    for axis, values in D13_B_AXES_NM.items()
}
D13_CASES = {
    "B": {"changed_axis": None, "axis_cell_counts": (6, 6, 14)},
    "X": {"changed_axis": "x", "axis_cell_counts": (12, 6, 14)},
    "Y": {"changed_axis": "y", "axis_cell_counts": (6, 12, 14)},
    "Z": {"changed_axis": "z", "axis_cell_counts": (6, 6, 28)},
}


def _bisect_every_interval(values: tuple[float, ...]) -> tuple[float, ...]:
    refined: list[float] = [values[0]]
    for left, right in pairwise(values):
        refined.append(left + (right - left) / 2.0)
        refined.append(right)
    return tuple(refined)


def _axis_digest(values: tuple[float, ...]) -> str:
    return hashlib.sha256(struct.pack(f"<{len(values)}d", *values)).hexdigest()


def d13_axis_plan(case: str) -> dict[str, object]:
    """Return a deterministic D13 plan, deriving refinements from their parents."""
    if case in {"Y2", "Y3", "X2"}:
        return D13_AXIS_PLANS[case]
    if case not in D13_CASES:
        raise ValueError(f"unsupported Task40 D13 case {case!r}")
    metadata = D13_CASES[case]
    changed_axis = metadata["changed_axis"]
    axes = {
        axis: (
            _bisect_every_interval(values)
            if axis == changed_axis
            else values
        )
        for axis, values in D13_B_AXES_NM.items()
    }
    counts = tuple(len(axes[axis]) - 1 for axis in ("x", "y", "z"))
    if counts != tuple(metadata["axis_cell_counts"]):
        raise AssertionError(f"Task40 D13 {case} axis-plan counts are inconsistent")
    plan_id = f"task40_phi90_d13_{case.lower()}_axes_bisect_v1"
    digest_payload = {
        "schema": "task40.phi90.d13.axis_plan.v1",
        "case": case,
        "parent_case": "B",
        "changed_axis": changed_axis,
        "axes_nm": {axis: list(values) for axis, values in axes.items()},
        "axis_cell_counts": list(counts),
        "parent_axis_sha256_le_f64": D13_B_AXIS_SHA256_LE_F64,
    }
    plan_sha256 = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        **digest_payload,
        "plan_id": plan_id,
        "mesh_plan_sha256": plan_sha256,
        "actual_axis_sha256_le_f64": {
            axis: _axis_digest(values) for axis, values in axes.items()
        },
        "expected_global_cell_count": math.prod(counts),
    }


def d13_y2_axis_plan() -> dict[str, object]:
    """Bisect every realized D13-Y y interval; preserve its x/z axes exactly."""
    parent = d13_axis_plan("Y")
    parent_axes = parent["axes_nm"]
    axes = {
        "x": tuple(float(value) for value in parent_axes["x"]),
        "y": _bisect_every_interval(
            tuple(float(value) for value in parent_axes["y"])
        ),
        "z": tuple(float(value) for value in parent_axes["z"]),
    }
    counts = tuple(len(axes[axis]) - 1 for axis in ("x", "y", "z"))
    if counts != (6, 24, 14):
        raise AssertionError(f"Task40 D13 Y2 axis-plan counts are inconsistent: {counts}")
    plan_id = "task40_phi90_d13_y2_axes_bisect_from_y_v1"
    digest_payload = {
        "schema": "task40.phi90.d13.y2_axis_plan.v1",
        "case": "Y2",
        "parent_case": "Y",
        "parent_plan_id": parent["plan_id"],
        "parent_plan_sha256": parent["mesh_plan_sha256"],
        "changed_axis": "y",
        "axes_nm": {axis: list(values) for axis, values in axes.items()},
        "axis_cell_counts": list(counts),
        "parent_axis_sha256_le_f64": parent["actual_axis_sha256_le_f64"],
    }
    plan_sha256 = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        **digest_payload,
        "plan_id": plan_id,
        "mesh_plan_sha256": plan_sha256,
        "actual_axis_sha256_le_f64": {
            axis: _axis_digest(values) for axis, values in axes.items()
        },
        "expected_global_cell_count": math.prod(counts),
    }


def d13_y3_axis_plan() -> dict[str, object]:
    """Bisect every realized D13-Y2 y interval; preserve its x/z axes exactly."""
    parent = d13_axis_plan("Y2")
    parent_axes = parent["axes_nm"]
    axes = {
        "x": tuple(float(value) for value in parent_axes["x"]),
        "y": _bisect_every_interval(
            tuple(float(value) for value in parent_axes["y"])
        ),
        "z": tuple(float(value) for value in parent_axes["z"]),
    }
    counts = tuple(len(axes[axis]) - 1 for axis in ("x", "y", "z"))
    if counts != (6, 48, 14):
        raise AssertionError(f"Task40 D13 Y3 axis-plan counts are inconsistent: {counts}")
    segment_counts = tuple(
        sum(
            1
            for left, right in pairwise(axes["y"])
            if left >= lower and right <= upper
        )
        for lower, upper in ((0.0, 15.0), (15.0, 35.0), (35.0, 50.0))
    )
    if segment_counts != (16, 16, 16):
        raise AssertionError(f"Task40 D13 Y3 segment counts are inconsistent: {segment_counts}")
    plan_id = "task40_phi90_d13_y3_axes_bisect_from_y2_v1"
    digest_payload = {
        "schema": "task40.phi90.d13.y3_axis_plan.v1",
        "case": "Y3",
        "parent_case": "Y2",
        "parent_plan_id": parent["plan_id"],
        "parent_plan_sha256": parent["mesh_plan_sha256"],
        "changed_axis": "y",
        "axes_nm": {axis: list(values) for axis, values in axes.items()},
        "axis_cell_counts": list(counts),
        "segment_cell_counts": {
            "x": [2, 2, 2],
            "y": list(segment_counts),
            "z": [1, 12, 1],
        },
        "parent_axis_sha256_le_f64": parent["actual_axis_sha256_le_f64"],
    }
    plan_sha256 = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        **digest_payload,
        "plan_id": plan_id,
        "mesh_plan_sha256": plan_sha256,
        "actual_axis_sha256_le_f64": {
            axis: _axis_digest(values) for axis, values in axes.items()
        },
        "expected_global_cell_count": math.prod(counts),
    }


def d13_x2_axis_plan() -> dict[str, object]:
    """Bisect every realized Y2 x interval; preserve its y/z axes exactly."""
    parent = d13_axis_plan("Y2")
    parent_axes = parent["axes_nm"]
    axes = {
        "x": _bisect_every_interval(
            tuple(float(value) for value in parent_axes["x"])
        ),
        "y": tuple(float(value) for value in parent_axes["y"]),
        "z": tuple(float(value) for value in parent_axes["z"]),
    }
    counts = tuple(len(axes[axis]) - 1 for axis in ("x", "y", "z"))
    if counts != (12, 24, 14):
        raise AssertionError(
            f"Task40 D13 X2 axis-plan counts are inconsistent: {counts}"
        )
    segment_counts = {
        "x": tuple(
            sum(left >= lower and right <= upper for left, right in pairwise(axes["x"]))
            for lower, upper in ((0.0, 16.5), (16.5, 33.5), (33.5, 50.0))
        ),
        "y": tuple(
            sum(left >= lower and right <= upper for left, right in pairwise(axes["y"]))
            for lower, upper in ((0.0, 15.0), (15.0, 35.0), (35.0, 50.0))
        ),
        "z": tuple(
            sum(left >= lower and right <= upper for left, right in pairwise(axes["z"]))
            for lower, upper in ((-10.0, 0.0), (0.0, 120.0), (120.0, 130.0))
        ),
    }
    if segment_counts != {"x": (4, 4, 4), "y": (8, 8, 8), "z": (1, 12, 1)}:
        raise AssertionError(
            f"Task40 D13 X2 material segment counts are inconsistent: {segment_counts}"
        )
    plan_id = "task40_phi90_d13_x2_axes_bisect_from_y2_v1"
    digest_payload = {
        "schema": "task40.phi90.d13.x2_axis_plan.v1",
        "case": "X2",
        "parent_case": "Y2",
        "parent_plan_id": parent["plan_id"],
        "parent_plan_sha256": parent["mesh_plan_sha256"],
        "changed_axis": "x",
        "axes_nm": {axis: list(values) for axis, values in axes.items()},
        "axis_cell_counts": list(counts),
        "segment_cell_counts": {
            axis: list(values) for axis, values in segment_counts.items()
        },
        "parent_axis_sha256_le_f64": parent["actual_axis_sha256_le_f64"],
    }
    plan_sha256 = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        **digest_payload,
        "plan_id": plan_id,
        "mesh_plan_sha256": plan_sha256,
        "actual_axis_sha256_le_f64": {
            axis: _axis_digest(values) for axis, values in axes.items()
        },
        "expected_global_cell_count": math.prod(counts),
    }


D13_AXIS_PLANS = {case: d13_axis_plan(case) for case in D13_CASES}
D13_AXIS_PLANS["Y2"] = d13_y2_axis_plan()
D13_AXIS_PLANS["Y3"] = d13_y3_axis_plan()
D13_CASES["X2"] = {
    "changed_axis": "x",
    "parent_case": "Y2",
    "axis_cell_counts": (12, 24, 14),
}
D13_AXIS_PLANS["X2"] = d13_x2_axis_plan()
D13_AXIS_PLAN_IDS = {
    str(plan["plan_id"]): case for case, plan in D13_AXIS_PLANS.items()
    if case != "B"
}


def validate_frozen_d13_axes(payload: Mapping[str, object]) -> dict[str, tuple[float, ...]]:
    """Reject altered counts, hashes, or any coordinate not in the frozen plan."""
    plan_id = payload.get("mesh_plan_id")
    case = D13_AXIS_PLAN_IDS.get(str(plan_id))
    if case is None:
        raise ValueError(f"unsupported Task40 D13 frozen axis plan {plan_id!r}")
    plan = D13_AXIS_PLANS[case]
    if payload.get("mesh_plan_sha256") != plan["mesh_plan_sha256"]:
        raise ValueError("Task40 D13 frozen mesh plan SHA256 mismatch")
    counts = tuple(payload.get("mesh_axis_cell_counts") or ())
    if counts != tuple(plan["axis_cell_counts"]):
        raise ValueError("Task40 D13 frozen mesh axis cell counts mismatch")
    result: dict[str, tuple[float, ...]] = {}
    for axis in ("x", "y", "z"):
        raw = payload.get(f"mesh_axis_{axis}_values")
        if raw is None:
            raise ValueError(f"Task40 D13 frozen mesh requires {axis} coordinates")
        values = tuple(float(value) for value in raw)
        expected = tuple(float(value) for value in plan["axes_nm"][axis])
        if values != expected:
            raise ValueError(f"Task40 D13 frozen {axis} coordinates differ from plan")
        result[axis] = values
    return result
