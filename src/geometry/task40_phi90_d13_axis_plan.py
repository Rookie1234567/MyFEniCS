"""Frozen Task40 D13 axes derived by bisecting actual D13-B intervals.

The X/Y/Z cases are genuine one-axis refinements: every interval in the
selected D13-B axis gets one midpoint, while the other two coordinate arrays
remain byte-for-byte identical to the recorded D13-B axes.
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
    """Return one deterministic D13 case plan, with arrays derived from B."""
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


D13_AXIS_PLANS = {case: d13_axis_plan(case) for case in D13_CASES}
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
