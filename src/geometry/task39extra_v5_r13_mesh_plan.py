"""Small R13-only binding for the frozen V21 original 13.5 nm mesh axes."""

from __future__ import annotations

from collections.abc import Mapping


MESH_PLAN_ID = "task039extra.v21.frozen-geometry-mesh-plan.v1"
MESH_PLAN_SHA256 = "b5bab6aae4668be60aacbb49265b4c875def42e2620256cd168d8c26207dc157"
AXIS_PLAN_SHA256 = "14d44ee25cdc60773031ea6ae405a0c6cff14ad23c33bdf3a575388370e8a115"
AXIS_CELL_COUNTS = (9, 5, 22)
FROZEN_AXES_NM = {
    "x": (
        0.0, 5.5, 11.0, 16.5, 22.166666666666668, 27.833333333333336,
        33.5, 39.0, 44.5, 50.0,
    ),
    "y": (
        0.0, 4.166666666666667, 8.333333333333334, 13.88888888888889,
        19.444444444444443, 25.0,
    ),
    "z": (
        -10.0, -5.0, 0.0, 6.666666666666667, 13.333333333333334, 20.0,
        26.666666666666668, 33.333333333333336, 40.0, 46.666666666666664,
        53.333333333333336, 60.0, 66.66666666666667, 73.33333333333334,
        80.0, 86.66666666666667, 93.33333333333333, 100.0,
        106.66666666666667, 113.33333333333334, 120.0, 125.0, 130.0,
    ),
}


def validate_frozen_r13_axes(discretization: Mapping[str, object]) -> dict[str, tuple[float, ...]]:
    """Require the complete, exact axis tuple bound to the R13 plan identity."""

    if discretization.get("mesh_plan_id") != MESH_PLAN_ID:
        raise ValueError("R13 input does not identify the frozen mesh plan")
    if discretization.get("mesh_plan_sha256") != MESH_PLAN_SHA256:
        raise ValueError("R13 input mesh_plan_sha256 differs from the frozen plan")
    counts = tuple(discretization.get("mesh_axis_cell_counts") or ())
    if counts != AXIS_CELL_COUNTS:
        raise ValueError("R13 input cell counts differ from the frozen mesh plan")

    resolved: dict[str, tuple[float, ...]] = {}
    for axis in ("x", "y", "z"):
        key = f"mesh_axis_{axis}_values"
        actual = discretization.get(key)
        expected = FROZEN_AXES_NM[axis]
        if not isinstance(actual, (list, tuple)) or len(actual) != len(expected):
            raise ValueError(f"R13 input {key} differs from the frozen mesh plan")
        values = tuple(float(value) for value in actual)
        if values != expected:
            raise ValueError(f"R13 input {key} differs from the frozen mesh plan")
        resolved[axis] = values
    if tuple(len(resolved[axis]) - 1 for axis in ("x", "y", "z")) != AXIS_CELL_COUNTS:
        raise ValueError("R13 frozen axis lengths disagree with cell counts")
    return resolved


__all__ = [
    "AXIS_CELL_COUNTS",
    "AXIS_PLAN_SHA256",
    "FROZEN_AXES_NM",
    "MESH_PLAN_ID",
    "MESH_PLAN_SHA256",
    "validate_frozen_r13_axes",
]
