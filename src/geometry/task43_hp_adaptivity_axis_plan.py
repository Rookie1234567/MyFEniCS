"""Task43's exact 3x10x6 interface-fitted hexahedral starting axes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

TASK43_AXIS_PLAN_ID = "task43_hp_adaptivity_3x10x6_axes_v1"
TASK43_AXIS_PLAN_SHA256 = (
    "08c78cd927c6cd1dc268b9003a151178a5670f53a1940734f5761f3553eccdd0"
)
TASK43_AXIS_CELL_COUNTS = (3, 10, 6)
TASK43_AXES_NM = {
    "x": (0.0, 16.5, 33.5, 50.0),
    "y": (0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0),
    "z": (-10.0, 0.0, 30.0, 60.0, 90.0, 120.0, 130.0),
}


def _digest_payload() -> dict[str, object]:
    return {
        "schema": "task43.hp_adaptivity.axes.v1",
        "plan_id": TASK43_AXIS_PLAN_ID,
        "axis_cell_counts": list(TASK43_AXIS_CELL_COUNTS),
        "axes_nm": {
            axis: list(TASK43_AXES_NM[axis]) for axis in ("x", "y", "z")
        },
    }


def task43_axis_plan() -> dict[str, object]:
    """Return the fixed starting-axis identity used by the Task43 profile."""

    payload = _digest_payload()
    actual = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if actual != TASK43_AXIS_PLAN_SHA256:
        raise RuntimeError("Task43 axis-plan source digest is inconsistent")
    return {
        **payload,
        "mesh_plan_sha256": actual,
        "expected_global_cell_count": 180,
    }


def validate_frozen_task43_axes(
    payload: Mapping[str, object],
) -> dict[str, tuple[float, ...]]:
    """Fail closed unless mesh coordinates and plan digest match Task43."""

    plan = task43_axis_plan()
    if payload.get("mesh_plan_id") != TASK43_AXIS_PLAN_ID:
        raise ValueError("unsupported Task43 frozen axis-plan identity")
    if payload.get("mesh_plan_sha256") != plan["mesh_plan_sha256"]:
        raise ValueError("Task43 frozen mesh-plan SHA256 mismatch")
    if tuple(payload.get("mesh_axis_cell_counts") or ()) != TASK43_AXIS_CELL_COUNTS:
        raise ValueError("Task43 frozen mesh-axis cell counts mismatch")
    result: dict[str, tuple[float, ...]] = {}
    for axis in ("x", "y", "z"):
        values = payload.get(f"mesh_axis_{axis}_values")
        if values is None:
            raise ValueError(f"Task43 frozen mesh requires {axis} coordinates")
        actual_values = tuple(float(value) for value in values)
        if actual_values != TASK43_AXES_NM[axis]:
            raise ValueError(f"Task43 frozen {axis} coordinates differ from plan")
        result[axis] = actual_values
    return result


__all__ = [
    "TASK43_AXES_NM",
    "TASK43_AXIS_CELL_COUNTS",
    "TASK43_AXIS_PLAN_ID",
    "TASK43_AXIS_PLAN_SHA256",
    "task43_axis_plan",
    "validate_frozen_task43_axes",
]
