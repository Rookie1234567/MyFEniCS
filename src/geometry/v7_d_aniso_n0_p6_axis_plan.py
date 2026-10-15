"""Frozen anisotropic axes for the bounded V7 candidate D grid.

Candidate D changes x and z together.  It is a diagnostic grid, not an
isolated x- or z-convergence point.  All coordinates are in nanometres.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from itertools import pairwise

import numpy as np

D_AXIS_PLAN_ID = "task39extra.v7.aniso_n0.p6.direct.grid_d.axes.v1"
D_AXIS_PLAN_IDS = frozenset({D_AXIS_PLAN_ID})
D_AXIS_COUNTS = (200, 2, 118)
D_X_SEGMENT_COUNTS = (66, 68, 66)
D_Y_SEGMENT_COUNTS = (2,)
D_Z_SEGMENT_COUNTS = (9, 100, 9)
D_Z_PROFILE = "v7_d_z_9_100_9_nm_v1"


def _segment(start: float, stop: float, cells: int) -> np.ndarray:
    return np.linspace(float(start), float(stop), int(cells) + 1, dtype=np.float64)


def d_axis_plan() -> dict[str, object]:
    """Build the exact 66/68/66 × 2 × 9/100/9 coordinate plan."""

    x = np.concatenate(
        (
            _segment(0.0, 16.5, D_X_SEGMENT_COUNTS[0])[:-1],
            _segment(16.5, 33.5, D_X_SEGMENT_COUNTS[1])[:-1],
            _segment(33.5, 50.0, D_X_SEGMENT_COUNTS[2]),
        )
    )
    y = _segment(0.0, 25.0, D_Y_SEGMENT_COUNTS[0])
    z = np.concatenate(
        (
            _segment(-10.0, 0.0, D_Z_SEGMENT_COUNTS[0])[:-1],
            _segment(0.0, 120.0, D_Z_SEGMENT_COUNTS[1])[:-1],
            _segment(120.0, 130.0, D_Z_SEGMENT_COUNTS[2]),
        )
    )
    axes = {"x": x, "y": y, "z": z}
    axis_hashes = {
        axis: hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()
        for axis, values in axes.items()
    }
    payload = {
        "schema": "task39extra.v7.aniso-n0-p6-axis-plan.v1",
        "plan_id": D_AXIS_PLAN_ID,
        "diagnostic_scope": "CROSS_CHANGED_GRID_DIAGNOSTIC",
        "axis_cell_counts": list(D_AXIS_COUNTS),
        "segment_cell_counts": {
            "x": list(D_X_SEGMENT_COUNTS),
            "y": list(D_Y_SEGMENT_COUNTS),
            "z": list(D_Z_SEGMENT_COUNTS),
        },
        "axis_sha256_le_f64": axis_hashes,
    }
    plan_sha = hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("ascii")
    ).hexdigest()
    return {
        **payload,
        "plan_sha256": plan_sha,
        "axes_nm": {
            axis: tuple(float(value) for value in values)
            for axis, values in axes.items()
        },
    }


def validate_frozen_d_axes(discretization: Mapping[str, object]) -> dict[str, tuple[float, ...]]:
    """Validate D plan identity, counts and exact x/y/z arrays."""

    plan = d_axis_plan()
    if discretization.get("mesh_plan_id") != D_AXIS_PLAN_ID:
        raise ValueError("input does not select the frozen V7 candidate-D axis plan")
    if discretization.get("mesh_plan_sha256") != plan["plan_sha256"]:
        raise ValueError("V7 candidate-D mesh-plan SHA differs")
    counts = tuple(int(value) for value in discretization.get("mesh_axis_cell_counts") or ())
    if counts != D_AXIS_COUNTS:
        raise ValueError(f"V7 candidate-D axis counts must equal {D_AXIS_COUNTS}")
    if discretization.get("mesh_axis_z_profile") != D_Z_PROFILE:
        raise ValueError("V7 candidate-D z-profile identity differs")

    resolved: dict[str, tuple[float, ...]] = {}
    expected = plan["axes_nm"]
    for axis in ("x", "y", "z"):
        raw = discretization.get(f"mesh_axis_{axis}_values")
        if not isinstance(raw, (list, tuple)) or len(raw) != len(expected[axis]):
            raise ValueError(f"V7 candidate-D mesh_axis_{axis}_values has wrong length")
        values = tuple(float(value) for value in raw)
        if any(not np.isfinite(value) for value in values):
            raise ValueError(f"V7 candidate-D mesh_axis_{axis}_values is non-finite")
        if values != expected[axis]:
            raise ValueError(f"V7 candidate-D mesh_axis_{axis}_values differ from plan")
        if any(right <= left for left, right in pairwise(values)):
            raise ValueError(f"V7 candidate-D mesh_axis_{axis}_values is not increasing")
        resolved[axis] = values
    return resolved


__all__ = [
    "D_AXIS_COUNTS",
    "D_AXIS_PLAN_ID",
    "D_AXIS_PLAN_IDS",
    "D_X_SEGMENT_COUNTS",
    "D_Y_SEGMENT_COUNTS",
    "D_Z_PROFILE",
    "D_Z_SEGMENT_COUNTS",
    "d_axis_plan",
    "validate_frozen_d_axes",
]
