"""Frozen one-axis tensor mesh plans for the SAXS center P6 direct route.

Both plans are configuration-only. Only the C profile selected after B2 is used
for a target solve; these plans do not authorize or launch either solve.
"""

from __future__ import annotations

import hashlib
import json
import struct
from itertools import pairwise
from math import prod
from typing import Mapping


SAXS_G6_BASE_AXES = {
    "x": (0.0, 8.25, 16.5, 25.0, 33.5, 41.75, 50.0),
    "y": tuple(float(i) * 0.25 for i in range(201)),
    "z": (-10.0, -5.0, 0.0, 30.0, 60.0, 90.0, 120.0, 125.0, 130.0),
}


def _piecewise_axis(intervals, counts):
    result = []
    for (start, stop), count in zip(pairwise(intervals), counts, strict=True):
        segment = tuple(start + (stop - start) * j / count for j in range(count + 1))
        result.extend(segment if not result else segment[1:])
    return tuple(result)


D07C_B_AXES = {
    "x": _piecewise_axis((0.0, 16.5, 33.5, 50.0), (2, 2, 2)),
    "y": _piecewise_axis((0.0, 15.0, 35.0, 50.0), (10, 6, 10)),
    "z": _piecewise_axis((-10.0, 0.0, 120.0, 130.0), (2, 2, 2)),
}


def _axis_sha256(values) -> str:
    packed = struct.pack(f"<{len(values)}d", *(float(value) for value in values))
    return hashlib.sha256(packed).hexdigest()


def _axes_sha256(axes) -> dict[str, str]:
    return {axis: _axis_sha256(axes[axis]) for axis in "xyz"}


def _midpoint_tags(axes) -> dict[str, int]:
    """Independent structured-cell midpoint classification for the Si geometry."""
    tags = {"1": 0, "2": 0, "3": 0}
    for x0, x1 in pairwise(axes["x"]):
        x = (x0 + x1) * 0.5
        for y0, y1 in pairwise(axes["y"]):
            y = (y0 + y1) * 0.5
            for z0, z1 in pairwise(axes["z"]):
                z = (z0 + z1) * 0.5
                if z < 0.0:
                    tag = "2"
                elif z < 120.0 and 16.5 <= x <= 33.5 and 15.0 <= y <= 35.0:
                    tag = "3"
                else:
                    tag = "1"
                tags[tag] += 1
    return tags


def _refine_x(axes):
    source = axes["x"]
    result = []
    for left, right in pairwise(source):
        result.extend((left, (left + right) * 0.5))
    result.append(source[-1])
    return tuple(result)


def _refine_pillar_z(axes):
    source = axes["z"]
    result = []
    for left, right in pairwise(source):
        result.append(left)
        if 0.0 <= left < right <= 120.0 and right - left == 30.0:
            result.append((left + right) * 0.5)
    result.append(source[-1])
    return tuple(result)


def saxs_one_axis_plan(axis: str) -> dict[str, object]:
    """Build one candidate plan relative to the current SAXS G6 mesh only."""
    if axis not in {"x", "z"}:
        raise ValueError("the reviewed C scope permits exactly x or pillar-z refinement")
    axes = {key: tuple(values) for key, values in SAXS_G6_BASE_AXES.items()}
    if axis == "x":
        axes["x"] = _refine_x(axes)
        case = "C_X_BISECT"
        d07c_b_changed_axes = ["x", "y", "z"]
        expected_tags = {"1": 13120, "2": 4800, "3": 1280}
    else:
        axes["z"] = _refine_pillar_z(axes)
        case = "C_Z_PILLAR_30_TO15"
        d07c_b_changed_axes = ["y", "z"]
        expected_tags = {"1": 10720, "2": 2400, "3": 1280}

    counts = [len(axes[key]) - 1 for key in "xyz"]
    cells = prod(counts)
    tags = _midpoint_tags(axes)
    if tags != expected_tags or sum(tags.values()) != cells:
        raise AssertionError(f"{case} static midpoint tags changed: {tags} != {expected_tags}")

    parent_hashes = _axes_sha256(SAXS_G6_BASE_AXES)
    actual_hashes = _axes_sha256(axes)
    d07c_b_hashes = _axes_sha256(D07C_B_AXES)
    changed_vs_saxs = [key for key in "xyz" if actual_hashes[key] != parent_hashes[key]]
    changed_vs_d07c_b = [key for key in "xyz" if actual_hashes[key] != d07c_b_hashes[key]]
    if changed_vs_saxs != [axis] or changed_vs_d07c_b != d07c_b_changed_axes:
        raise AssertionError(
            f"{case} lineage mismatch: SAXS={changed_vs_saxs}, D07C-B={changed_vs_d07c_b}"
        )

    periodic_trace_rows = counts[0] * counts[1] * (198 * counts[2] + 72)
    mode_rows = 1088
    plan: dict[str, object] = {
        "schema": "saxs.simple_grating.one_axis_plan.v1",
        "case": case,
        "parent_case": "SAXS_G6_BASELINE",
        "changed_axis": axis,
        "changed_axes": changed_vs_saxs,
        "changed_axes_vs_d07c_b": changed_vs_d07c_b,
        "axis_cell_counts": counts,
        "axes_nm": {key: list(axes[key]) for key in "xyz"},
        "axis_sha256_le_f64": actual_hashes,
        "parent_axis_sha256_le_f64": parent_hashes,
        "d07c_b_axis_sha256_le_f64": d07c_b_hashes,
        "expected_global_cell_count": cells,
        "expected_material_tag_counts": tags,
        "static_condensed_rows": {
            "periodic_trace_rows": periodic_trace_rows,
            "port_mode_rows": mode_rows,
            "augmented_rows": periodic_trace_rows + mode_rows,
            "status": "combinatorial_estimate_not_live_matrix_qa",
        },
        "static_plan_record": {
            "source": "explicit SAXS center G6 axis coordinates; one axis changed",
            "relative_to_saxs_baseline_changes_exactly_one_axis": True,
            "relative_to_d07c_b_axes_recorded_separately": True,
            "material_tags": "independent_cell_midpoint_classification_not_live_mesh_qa",
            "lu_memory_prediction": None,
        },
    }
    plan_hash = hashlib.sha256(
        json.dumps(plan, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
    plan["mesh_plan_id"] = f"saxs_simple_grating_center_{axis}_one_axis_v1"
    plan["mesh_plan_sha256"] = plan_hash
    return plan


SAXS_ONE_AXIS_PLAN_CASES = {
    "C_X_BISECT": "x",
    "C_Z_PILLAR_30_TO15": "z",
}
SAXS_ONE_AXIS_PLAN_IDS = {
    str(saxs_one_axis_plan(axis)["mesh_plan_id"]): axis for axis in ("x", "z")
}


def validate_saxs_one_axis_plan(payload: Mapping[str, object]) -> dict[str, tuple[float, ...]]:
    """Validate the selected profile's exact coordinates and frozen plan identity."""
    plan_id = str(payload.get("mesh_plan_id") or "")
    axis = SAXS_ONE_AXIS_PLAN_IDS.get(plan_id)
    if axis is None:
        raise ValueError(f"unsupported SAXS one-axis mesh plan {plan_id!r}")
    plan = saxs_one_axis_plan(axis)
    if payload.get("mesh_plan_sha256") != plan["mesh_plan_sha256"]:
        raise ValueError("SAXS one-axis plan SHA256 differs from the frozen plan")
    try:
        counts = tuple(int(value) for value in payload.get("mesh_axis_cell_counts", ()))
        axes = {
            key: tuple(float(value) for value in payload.get(f"mesh_axis_{key}_values", ()))
            for key in "xyz"
        }
    except (TypeError, ValueError) as exc:
        raise ValueError("SAXS one-axis mesh payload is malformed") from exc
    if counts != tuple(plan["axis_cell_counts"]):
        raise ValueError("SAXS one-axis cell counts differ from the frozen plan")
    if axes != {key: tuple(plan["axes_nm"][key]) for key in "xyz"}:
        raise ValueError("SAXS one-axis coordinates differ from the frozen plan")
    if _axes_sha256(axes) != plan["axis_sha256_le_f64"]:
        raise ValueError("SAXS one-axis coordinate hashes differ from the frozen plan")
    return axes
