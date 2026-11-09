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


def saxs_cxz15_plan() -> dict[str, object]:
    """Build CXZ15 relative to completed CX and retain the G6 baseline lineage."""
    cx_plan = saxs_one_axis_plan("x")
    g6_z_plan = saxs_one_axis_plan("z")
    axes = {
        key: tuple(values) for key, values in cx_plan["axes_nm"].items()
    }
    axes["z"] = tuple(g6_z_plan["axes_nm"]["z"])
    counts = [len(axes[key]) - 1 for key in "xyz"]
    cells = prod(counts)
    tags = _midpoint_tags(axes)
    expected_tags = {"1": 21440, "2": 4800, "3": 2560}
    if counts != [12, 200, 12] or tags != expected_tags or sum(tags.values()) != cells:
        raise AssertionError(
            f"CXZ15 static mesh inventory changed: counts={counts}, tags={tags}"
        )

    reference_hashes = _axes_sha256(cx_plan["axes_nm"])
    baseline_hashes = _axes_sha256(SAXS_G6_BASE_AXES)
    actual_hashes = _axes_sha256(axes)
    changed_from_cx = [
        key for key in "xyz" if actual_hashes[key] != reference_hashes[key]
    ]
    changed_from_g6 = [
        key for key in "xyz" if actual_hashes[key] != baseline_hashes[key]
    ]
    if changed_from_cx != ["z"] or changed_from_g6 != ["x", "z"]:
        raise AssertionError(
            f"CXZ15 lineage mismatch: CX={changed_from_cx}, G6={changed_from_g6}"
        )

    plan: dict[str, object] = {
        "schema": "saxs.simple_grating.cxz15_plan.v1",
        "case": "CXZ15",
        "parent_case": "CX",
        "reference_run_id": (
            "saxs_simple_grating_center_0p7135227949_phi84_p6_direct_cx_v1"
        ),
        "reference_run_timestamp": "20261108T144628.333953Z",
        "reference_source_sha256": (
            "0c8ab09edfd60f40a45785f5e637e7718c13abf2"
        ),
        "reference_axis_cell_counts": list(cx_plan["axis_cell_counts"]),
        "reference_global_cell_count": int(cx_plan["expected_global_cell_count"]),
        "reference_axis_sha256_le_f64": reference_hashes,
        "baseline_case": "SAXS_G6_BASELINE",
        "baseline_axis_cell_counts": [6, 200, 8],
        "baseline_axis_sha256_le_f64": baseline_hashes,
        "changed_axis": "z",
        "changed_axes": changed_from_cx,
        "changed_axes_vs_saxs_g6_baseline": changed_from_g6,
        "axis_cell_counts": counts,
        "axes_nm": {key: list(values) for key, values in axes.items()},
        "axis_sha256_le_f64": actual_hashes,
        "expected_global_cell_count": cells,
        "expected_material_tag_counts": tags,
        "static_condensed_rows": {
            "periodic_trace_rows": counts[0] * counts[1] * (198 * counts[2] + 72),
            "port_mode_rows": 1088,
            "augmented_rows": counts[0] * counts[1] * (198 * counts[2] + 72) + 1088,
            "status": "combinatorial_estimate_not_live_matrix_qa",
        },
        "static_plan_record": {
            "relative_to_completed_CX_changes_exactly_one_axis": True,
            "relative_to_SAXS_G6_baseline_changes_two_axes": ["x", "z"],
            "parent_reference_is_completed_CX_run": True,
            "material_tags": "independent_cell_midpoint_classification_not_live_mesh_qa",
            "lu_memory_prediction": None,
        },
    }
    plan_hash = hashlib.sha256(
        json.dumps(plan, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
    plan["mesh_plan_id"] = "saxs_simple_grating_center_cxz15_z_refine_from_cx_v1"
    plan["mesh_plan_sha256"] = plan_hash
    return plan


SAXS_ONE_AXIS_PLAN_CASES = {
    "C_X_BISECT": "x",
    "C_Z_PILLAR_30_TO15": "z",
}
SAXS_ONE_AXIS_PLAN_IDS = {
    str(saxs_one_axis_plan(axis)["mesh_plan_id"]): axis for axis in ("x", "z")
}
SAXS_CXZ15_PLAN_IDS = {"saxs_simple_grating_center_cxz15_z_refine_from_cx_v1"}


def validate_saxs_cxz15_plan(payload: Mapping[str, object]) -> dict[str, tuple[float, ...]]:
    """Validate the exact CXZ15 mesh and both reference/baseline identities."""
    plan = saxs_cxz15_plan()
    if payload.get("mesh_plan_id") != plan["mesh_plan_id"]:
        raise ValueError("unsupported SAXS CXZ15 mesh plan")
    if payload.get("mesh_plan_sha256") != plan["mesh_plan_sha256"]:
        raise ValueError("SAXS CXZ15 plan SHA256 differs from the frozen plan")
    try:
        counts = tuple(int(value) for value in payload.get("mesh_axis_cell_counts", ()))
        axes = {
            key: tuple(float(value) for value in payload.get(f"mesh_axis_{key}_values", ()))
            for key in "xyz"
        }
    except (TypeError, ValueError) as exc:
        raise ValueError("SAXS CXZ15 mesh payload is malformed") from exc
    if counts != tuple(plan["axis_cell_counts"]):
        raise ValueError("SAXS CXZ15 cell counts differ from the frozen plan")
    if axes != {key: tuple(plan["axes_nm"][key]) for key in "xyz"}:
        raise ValueError("SAXS CXZ15 coordinates differ from the frozen plan")
    if _axes_sha256(axes) != plan["axis_sha256_le_f64"]:
        raise ValueError("SAXS CXZ15 axis hashes differ from the frozen plan")
    return axes


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
