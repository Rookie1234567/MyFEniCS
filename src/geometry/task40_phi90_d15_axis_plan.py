"""Frozen Task40 D15 13.5 nm axis plans; arithmetic only, no mesh/FE work.

D15-Z2 is an identity-based reuse alias to the completed H15-B result. It is
not launchable and deliberately has no D15 profile or input.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
from collections.abc import Mapping
from itertools import pairwise

D15_STATIC_PLAN_RECORD = (
    "docs/task40para_phi90_mesh_modes_direct/outcomes/records/"
    "d15_static_axis_plan_v2.json"
)
D15_STATIC_PLAN_SHA256 = "185734f198f00d2c8bf17c87c760f85114e2156ee7e1185fa7884481782288e5"
D15_SUPERSEDED_STATIC_PROPOSAL_SHA256 = (
    "6c068546fbfa8f99aa93c0456dcf3a73cbacc430885abd9bf38b0730127e7e6c"
)
D15_Y3_2_STATIC_PLAN_RECORD = (
    "docs/task40para_phi90_mesh_modes_direct/outcomes/records/"
    "d15_y3_2_static_axis_supplement_v1.json"
)
D15_Y3_2_STATIC_PLAN_SHA256 = (
    "9c5c3683b1fb6db57401cb0709b25d972f396a519839ea9437aae0b27ad9bfc5"
)
D15_Y3_2_SIBLINGS_STATIC_PLAN_RECORD = (
    "docs/task40para_phi90_mesh_modes_direct/outcomes/records/"
    "d15_y3_2_siblings_static_axis_v2.json"
)
D15_Y3_2_SIBLINGS_STATIC_PLAN_SHA256 = (
    "9ad27c53e6668aeace605dbcbf47053aeccecc1102a383fb3864861811aa22fd"
)
D15_Y5_1_STATIC_PLAN_RECORD = (
    "docs/task40para_phi90_mesh_modes_direct/outcomes/records/"
    "d15_y5_1_static_axis_plan_v1.json"
)
D15_Y5_1_STATIC_PLAN_SHA256 = "122d947787fa51b9d5e70e97d9f61ba34a0802aa152cf70a18cbf149c71fa5ba"
D15_Y6_SIBLINGS_STATIC_PLAN_RECORD = (
    "docs/task40para_phi90_mesh_modes_direct/outcomes/records/"
    "d15_y6_siblings_static_axis_plan_v1.json"
)
D15_Y6_SIBLINGS_STATIC_PLAN_SHA256 = "d6b81cfac1c58cb4ae1e19f132b94d3676679db89858b1b9dff48736668c6035"
D15_Y5_1_Z_STATIC_PLAN_RECORD = (
    "docs/task40para_phi90_mesh_modes_direct/outcomes/records/"
    "d15_y5_1_z_refinement_static_plan_v1.json"
)
D15_Y5_1_Z_STATIC_PLAN_SHA256 = (
    "584023b9c810774bfecc9126365f68a22bf0c04050e242ee0b39225106b5244c"
)
D15_Y3_2_Y_COORDINATES_NM = (
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
)
D15_Y3_3_Y_COORDINATES_NM = (
    0.0, 5.0, 10.0, 15.0, 18.333333333333332, 21.666666666666668,
    25.0, 28.333333333333336, 31.666666666666668, 35.0, 40.0, 45.0, 50.0,
)
D15_Y3_4_Y_COORDINATES_NM = (
    0.0, 7.5, 15.0, 17.5, 20.0, 22.5, 25.0, 27.5, 30.0, 32.5,
    35.0, 42.5, 50.0,
)
D15_Y4_4_4_Y_COORDINATES_NM = (
    0.0, 3.75, 7.5, 11.25, 15.0, 20.0, 25.0, 30.0, 35.0,
    38.75, 42.5, 46.25, 50.0,
)

D15_Y5_1_Y_COORDINATES_NM = (
    0.0, 3.75, 7.5, 11.25, 15.0, 18.333333333333332,
    21.666666666666668, 25.0, 28.333333333333336, 31.666666666666668,
    35.0, 38.75, 42.5, 46.25, 50.0,
)


D15_Y6_1_Y_COORDINATES_NM = (
    0.0, 3.0, 6.0, 9.0, 12.0, 15.0, 18.333333333333332,
    21.666666666666668, 25.0, 28.333333333333336,
    31.666666666666668, 35.0, 38.0, 41.0, 44.0, 47.0, 50.0,
)
D15_Y6_2_Y_COORDINATES_NM = (
    0.0, 3.75, 7.5, 11.25, 15.0, 17.5, 20.0, 22.5, 25.0,
    27.5, 30.0, 32.5, 35.0, 38.75, 42.5, 46.25, 50.0,
)


def _uniform_piecewise_axis(bounds: tuple[float, ...], counts: tuple[int, ...]) -> tuple[float, ...]:
    """Create one deterministic float64 coordinate sequence from segment counts."""
    if len(bounds) != len(counts) + 1 or any(int(count) <= 0 for count in counts):
        raise ValueError("piecewise axis bounds/counts are inconsistent")
    values: list[float] = []
    for (start, stop), count in zip(pairwise(bounds), counts, strict=True):
        count = int(count)
        values.extend(float(start + (stop - start) * i / count) for i in range(count))
    values.append(float(bounds[-1]))
    if any(not math.isfinite(value) for value in values):
        raise ValueError("piecewise axis contains a non-finite coordinate")
    if any(right <= left for left, right in pairwise(values)):
        raise ValueError("piecewise axis is not strictly increasing")
    return tuple(values)


# Authorized D15 z variants from the actual D15-B x/y baseline. Z3_3 endpoint
# coordinates are generated once by the common segment planner above.
D15_Z3_3_Z_COORDINATES_NM = _uniform_piecewise_axis(
    (-10.0, 0.0, 120.0, 130.0), (3, 6, 3)
)
D15_Z_LEVEL_STATIC_PLAN_RECORD = (
    "docs/task40para_phi90_mesh_modes_direct/outcomes/records/"
    "d15_z_from_b_variants_static_axis_v1.json"
)
D15_Z_LEVEL_STATIC_PLAN_SHA256 = "1a96d63e4e99cd29147e77f4865e8da1770284cec48c25e6895708f50c6723fb"

D15_AXIS_COORDINATES_NM: dict[str, dict[int, tuple[float, ...]]] = {
    "x": {
        6: (0.0, 8.25, 16.5, 25.0, 33.5, 41.75, 50.0),
        8: (0.0, 8.25, 16.5, 20.75, 25.0, 29.25, 33.5, 41.75, 50.0),
        10: (0.0, 5.5, 11.0, 16.5, 20.75, 25.0, 29.25, 33.5, 39.0, 44.5, 50.0),
        12: (0.0, 4.125, 8.25, 12.375, 16.5, 20.75, 25.0, 29.25, 33.5, 37.625, 41.75, 45.875, 50.0),
    },
    "y": {
        4: (0.0, 15.0, 25.0, 35.0, 50.0),
        6: (0.0, 7.5, 15.0, 25.0, 35.0, 42.5, 50.0),
        8: (0.0, 7.5, 15.0, 20.0, 25.0, 30.0, 35.0, 42.5, 50.0),
        10: (0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0),
    },
    "z": {
        6: (-10.0, 0.0, 30.0, 60.0, 90.0, 120.0, 130.0),
        8: (-10.0, 0.0, 20.0, 40.0, 60.0, 80.0, 100.0, 120.0, 130.0),
        10: (-10.0, 0.0, 15.0, 30.0, 45.0, 60.0, 75.0, 90.0, 105.0, 120.0, 130.0),
        12: (-10.0, 0.0, 12.0, 24.0, 36.0, 48.0, 60.0, 72.0, 84.0, 96.0, 108.0, 120.0, 130.0),
    },
}

D15_CASES: dict[str, dict[str, object]] = {
    "B": {"axis_cell_counts": (6, 4, 6), "segment_cell_counts": {"x": (2, 2, 2), "y": (1, 2, 1), "z": (1, 4, 1)}, "changed_axis": None, "parent_case": None, "expected_tags": {"air": 104, "substrate": 24, "grating": 16}, "launchable": True},
    "X1": {"axis_cell_counts": (8, 4, 6), "segment_cell_counts": {"x": (2, 4, 2), "y": (1, 2, 1), "z": (1, 4, 1)}, "changed_axis": "x", "parent_case": "B", "expected_tags": {"air": 128, "substrate": 32, "grating": 32}, "launchable": True},
    "X2": {"axis_cell_counts": (10, 4, 6), "segment_cell_counts": {"x": (3, 4, 3), "y": (1, 2, 1), "z": (1, 4, 1)}, "changed_axis": "x", "parent_case": "B", "expected_tags": {"air": 168, "substrate": 40, "grating": 32}, "launchable": True},
    "X3": {"axis_cell_counts": (12, 4, 6), "segment_cell_counts": {"x": (4, 4, 4), "y": (1, 2, 1), "z": (1, 4, 1)}, "changed_axis": "x", "parent_case": "B", "expected_tags": {"air": 208, "substrate": 48, "grating": 32}, "launchable": True},
    "Y1": {"axis_cell_counts": (6, 6, 6), "segment_cell_counts": {"x": (2, 2, 2), "y": (2, 2, 2), "z": (1, 4, 1)}, "changed_axis": "y", "parent_case": "B", "expected_tags": {"air": 164, "substrate": 36, "grating": 16}, "launchable": True},
    "Y2": {"axis_cell_counts": (6, 8, 6), "segment_cell_counts": {"x": (2, 2, 2), "y": (2, 4, 2), "z": (1, 4, 1)}, "changed_axis": "y", "parent_case": "B", "expected_tags": {"air": 208, "substrate": 48, "grating": 32}, "launchable": True},
    "Y3": {"axis_cell_counts": (6, 10, 6), "segment_cell_counts": {"x": (2, 2, 2), "y": (3, 4, 3), "z": (1, 4, 1)}, "changed_axis": "y", "parent_case": "B", "expected_tags": {"air": 268, "substrate": 60, "grating": 32}, "launchable": True},
    "Y3_2": {"axis_cell_counts": (6, 10, 6), "segment_cell_counts": {"x": (2, 2, 2), "y": (2, 6, 2), "z": (1, 4, 1)}, "changed_axis": "y", "parent_case": "B", "expected_tags": {"air": 252, "substrate": 60, "grating": 48}, "launchable": True},
    "Y3_3": {"axis_cell_counts": (6, 12, 6), "segment_cell_counts": {"x": (2, 2, 2), "y": (3, 6, 3), "z": (1, 4, 1)}, "changed_axis": "y", "parent_case": "Y3_2", "expected_tags": {"air": 312, "substrate": 72, "grating": 48}, "launchable": True},
    "Y3_4": {"axis_cell_counts": (6, 12, 6), "segment_cell_counts": {"x": (2, 2, 2), "y": (2, 8, 2), "z": (1, 4, 1)}, "changed_axis": "y", "parent_case": "Y3_2", "expected_tags": {"air": 296, "substrate": 72, "grating": 64}, "launchable": True},
    "Y4_4_4": {"axis_cell_counts": (6, 12, 6), "segment_cell_counts": {"x": (2, 2, 2), "y": (4, 4, 4), "z": (1, 4, 1)}, "changed_axis": "y", "parent_case": "Y3_2", "expected_tags": {"air": 328, "substrate": 72, "grating": 32}, "launchable": True},
    "Y5_1": {"axis_cell_counts": (6, 14, 6), "segment_cell_counts": {"x": (2, 2, 2), "y": (4, 6, 4), "z": (1, 4, 1)}, "changed_axis": "y", "parent_case": "Y3", "expected_tags": {"air": 372, "substrate": 84, "grating": 48}, "launchable": True},
    "Y6_1": {"axis_cell_counts": (6, 16, 6), "segment_cell_counts": {"x": (2, 2, 2), "y": (5, 6, 5), "z": (1, 4, 1)}, "changed_axis": "y", "parent_case": "Y5_1", "expected_tags": {"air": 432, "substrate": 96, "grating": 48}, "launchable": True},
    "Y6_2": {"axis_cell_counts": (6, 16, 6), "segment_cell_counts": {"x": (2, 2, 2), "y": (4, 8, 4), "z": (1, 4, 1)}, "changed_axis": "y", "parent_case": "Y5_1", "expected_tags": {"air": 416, "substrate": 96, "grating": 64}, "launchable": True},
    # Retained only as history for the explicitly withdrawn Y5-parent proposal.
    "Y5_Z2": {"axis_cell_counts": (6, 14, 8), "segment_cell_counts": {"x": (2, 2, 2), "y": (4, 6, 4), "z": (1, 6, 1)}, "changed_axis": "z", "parent_case": "Y5_1", "expected_tags": {"air": 516, "substrate": 84, "grating": 72}, "launchable": False},
    "Z1": {"axis_cell_counts": (6, 4, 8), "segment_cell_counts": {"x": (2, 2, 2), "y": (1, 2, 1), "z": (1, 6, 1)}, "changed_axis": "z", "parent_case": "B", "expected_tags": {"air": 144, "substrate": 24, "grating": 24}, "launchable": True},
    "Z2": {"axis_cell_counts": (6, 4, 10), "segment_cell_counts": {"x": (2, 2, 2), "y": (1, 2, 1), "z": (1, 8, 1)}, "changed_axis": "z", "parent_case": "B", "expected_tags": {"air": 184, "substrate": 24, "grating": 32}, "launchable": False},
    "Z3": {"axis_cell_counts": (6, 4, 12), "segment_cell_counts": {"x": (2, 2, 2), "y": (1, 2, 1), "z": (1, 10, 1)}, "changed_axis": "z", "parent_case": "B", "expected_tags": {"air": 224, "substrate": 24, "grating": 40}, "launchable": True},
    "Z2_2": {"display_label": "D15-Z2-2", "axis_cell_counts": (6, 4, 10), "segment_cell_counts": {"x": (2, 2, 2), "y": (1, 2, 1), "z": (2, 6, 2)}, "changed_axis": "z", "parent_case": "B", "expected_tags": {"air": 168, "substrate": 48, "grating": 24}, "launchable": True},
    "Z3_2": {"display_label": "D15-Z3-2", "axis_cell_counts": (6, 4, 12), "segment_cell_counts": {"x": (2, 2, 2), "y": (1, 2, 1), "z": (2, 8, 2)}, "changed_axis": "z", "parent_case": "B", "expected_tags": {"air": 208, "substrate": 48, "grating": 32}, "launchable": True},
    "Z3_3": {"display_label": "D15-Z3-3", "axis_cell_counts": (6, 4, 12), "segment_cell_counts": {"x": (2, 2, 2), "y": (1, 2, 1), "z": (3, 6, 3)}, "changed_axis": "z", "parent_case": "B", "expected_tags": {"air": 192, "substrate": 72, "grating": 24}, "launchable": True},
}
D15_LAUNCHABLE_CASES = tuple(case for case, facts in D15_CASES.items() if facts["launchable"])
D15_PREVIOUS_CASE = {
    "B": None,
    "X1": "B",
    "X2": "X1",
    "X3": "X2",
    "Y1": "B",
    "Y2": "Y1",
    "Y3": "Y2",
    "Y3_2": "Y3",
    "Y3_3": "Y3_2",
    "Y3_4": "Y3_2",
    "Y4_4_4": "Y3_2",
    "Y5_1": "Y4_4_4",
    "Y6_1": "Y5_1",
    "Y6_2": "Y5_1",
    "Y5_Z2": "Y5_1",
    "Z1": "B",
    "Z2": "Z1",
    "Z3": "Z2",
    "Z2_2": "Z1",
    "Z3_2": "Z2_2",
    "Z3_3": "Z2_2",
}

D15_Z2_HISTORICAL_REUSE = {
    "case_role": "D15-Z2",
    "status": "REUSED_EXISTING_COMPLETED_H15_B_RESULT_NO_NEW_RUN",
    "run_directory": "results/si_block_phi90_50x50_17x20_h120/task40_phi90_13p5_H15_B_p6_direct_v1__full3d_direct__mpi1__Mna/20261017T052011.288309Z",
    "run_id": "task40_phi90_13p5_H15_B_p6_direct_v1",
    "profile_identity": "task40para_phi90_13p5_H15_B_p6_direct_v1",
    "source_sha": "d9edbcd583bb74dde36e3c9552893560f47bd230",
    "input_sha256": "ec5053a0d24e0e737faaccba027864e59cf0508aa63324f2bb2afc463cc18ec4",
    "physical_model_sha256": "515971779c8348f4914dad6a098bbc2c1f1dc4d22639779a71c3697cd7fe5974",
    "resolved_config_sha256": "ae4f6fde9a0ec10db248f75f23c53dca69ce4760022aaacbdbfac3629e38d104",
    "axis_cell_counts": [6, 4, 10],
    "axis_sha256_le_f64": {
        "x": "bb1d6be1e2cec153c7bd67a71e29f5967b3035b4928cd06f51ee2c0b6f2a5361",
        "y": "c0a1052034574ddda40b805390f8debb6abd3da6ec558cc0458820ee941198ba",
        "z": "bb32b94989a71ad930f909244cfada93e60634920ffdbf156378ae8f5df6888d",
    },
    "mode_count": 612,
    "mode_sha256": "1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e",
    "surface_quadrature_degree": 28,
    "volume_quadrature": {"degree": 15, "rule": "default"},
    "dtn_sparse_cutoff_policy": "scale_homogeneous_relative_only_v1",
    "dtn_sparse_cutoff_relative_tolerance": 1.0e-13,
    "operator_scope": "task40_phi90_H15_B_R13_finite_rectangle",
    "full_dtn_status": "FULL_DTN_NOT_VERIFIED",
}

def _axis_sha256(values: tuple[float, ...]) -> str:
    return hashlib.sha256(struct.pack(f"<{len(values)}d", *values)).hexdigest()

def _segment_counts(values: tuple[float, ...], bounds: tuple[float, ...]) -> tuple[int, ...]:
    return tuple(sum(left >= low - 1e-12 and right <= high + 1e-12 for left, right in pairwise(values)) for low, high in pairwise(bounds))

def _case_axis_values(case: str, axis: str, count: int) -> tuple[float, ...]:
    if axis == "z":
        if case == "Z2_2":
            return (-10.0, -5.0, 0.0, 20.0, 40.0, 60.0, 80.0, 100.0, 120.0, 125.0, 130.0)
        if case == "Z3_2":
            return (-10.0, -5.0, 0.0, 15.0, 30.0, 45.0, 60.0, 75.0, 90.0, 105.0, 120.0, 125.0, 130.0)
        if case == "Z3_3":
            return D15_Z3_3_Z_COORDINATES_NM
    if axis == "y":
        if case == "Y3_2":
            return D15_Y3_2_Y_COORDINATES_NM
        if case == "Y3_3":
            return D15_Y3_3_Y_COORDINATES_NM
        if case == "Y3_4":
            return D15_Y3_4_Y_COORDINATES_NM
        if case == "Y4_4_4":
            return D15_Y4_4_4_Y_COORDINATES_NM
        if case == "Y5_1":
            return D15_Y5_1_Y_COORDINATES_NM
        if case == "Y6_1":
            return D15_Y6_1_Y_COORDINATES_NM
        if case == "Y6_2":
            return D15_Y6_2_Y_COORDINATES_NM
        if case == "Y5_Z2":
            return D15_Y5_1_Y_COORDINATES_NM
    return tuple(D15_AXIS_COORDINATES_NM[axis][count])

def d15_axis_plan(case: str) -> dict[str, object]:
    if case not in D15_CASES:
        raise ValueError(f"unsupported Task40 D15 case {case!r}")
    facts = D15_CASES[case]
    counts = tuple(facts["axis_cell_counts"])
    axes = {
        axis: _case_axis_values(case, axis, counts[index])
        for index, axis in enumerate(("x", "y", "z"))
    }
    if tuple(len(axes[axis]) - 1 for axis in ("x", "y", "z")) != counts:
        raise AssertionError(f"Task40 D15 {case} axis count drift")
    if any(tuple(sorted(set(values))) != values for values in axes.values()):
        raise AssertionError(f"Task40 D15 {case} axes are not strictly increasing")
    segment_counts = {
        "x": _segment_counts(axes["x"], (0.0, 16.5, 33.5, 50.0)),
        "y": _segment_counts(axes["y"], (0.0, 15.0, 35.0, 50.0)),
        "z": _segment_counts(axes["z"], (-10.0, 0.0, 120.0, 130.0)),
    }
    if segment_counts != facts["segment_cell_counts"]:
        raise AssertionError(f"Task40 D15 {case} segment counts drift")
    total = math.prod(counts)
    substrate = counts[0] * counts[1] * segment_counts["z"][0]
    grating = segment_counts["x"][1] * segment_counts["y"][1] * segment_counts["z"][1]
    tags = {"air": total - substrate - grating, "substrate": substrate, "grating": grating}
    if tags != facts["expected_tags"]:
        raise AssertionError(f"Task40 D15 {case} static tag counts drift: {tags}")
    base_hashes = {
        axis: _axis_sha256(tuple(D15_AXIS_COORDINATES_NM[axis][D15_CASES["B"]["axis_cell_counts"][i]]))
        for i, axis in enumerate(("x", "y", "z"))
    }
    actual_hashes = {axis: _axis_sha256(axes[axis]) for axis in axes}
    base_axes = {
        axis: _case_axis_values("B", axis, D15_CASES["B"]["axis_cell_counts"][i])
        for i, axis in enumerate(("x", "y", "z"))
    }
    nested_from_base = all(
        set(base_axes[axis]).issubset(axes[axis]) for axis in ("x", "y", "z")
    )
    previous_case = D15_PREVIOUS_CASE[case]
    if previous_case is None:
        nested_from_previous = True
    else:
        previous_counts = tuple(D15_CASES[previous_case]["axis_cell_counts"])
        previous_axes = {
            axis: _case_axis_values(previous_case, axis, previous_counts[i])
            for i, axis in enumerate(("x", "y", "z"))
        }
        nested_from_previous = all(
            set(previous_axes[axis]).issubset(axes[axis])
            for axis in ("x", "y", "z")
        )
    parent = facts["parent_case"]
    changed_axis = facts["changed_axis"]
    if case == "Y3_2":
        static_plan_record = D15_Y3_2_STATIC_PLAN_RECORD
        static_plan_sha = D15_Y3_2_STATIC_PLAN_SHA256
    elif case in {"Y3_3", "Y3_4", "Y4_4_4"}:
        static_plan_record = D15_Y3_2_SIBLINGS_STATIC_PLAN_RECORD
        static_plan_sha = D15_Y3_2_SIBLINGS_STATIC_PLAN_SHA256
    elif case == "Y5_1":
        static_plan_record = D15_Y5_1_STATIC_PLAN_RECORD
        static_plan_sha = D15_Y5_1_STATIC_PLAN_SHA256
    elif case in {"Y6_1", "Y6_2"}:
        static_plan_record = D15_Y6_SIBLINGS_STATIC_PLAN_RECORD
        static_plan_sha = D15_Y6_SIBLINGS_STATIC_PLAN_SHA256
    elif case == "Y5_Z2":
        static_plan_record = D15_Y5_1_Z_STATIC_PLAN_RECORD
        static_plan_sha = D15_Y5_1_Z_STATIC_PLAN_SHA256
    elif case in {"Z2_2", "Z3_2", "Z3_3"}:
        static_plan_record = D15_Z_LEVEL_STATIC_PLAN_RECORD
        static_plan_sha = D15_Z_LEVEL_STATIC_PLAN_SHA256
    else:
        static_plan_record = D15_STATIC_PLAN_RECORD
        static_plan_sha = D15_STATIC_PLAN_SHA256
    if parent is None:
        if actual_hashes != base_hashes:
            raise AssertionError("Task40 D15-B axes differ from frozen baseline")
    else:
        parent_counts = tuple(D15_CASES[parent]["axis_cell_counts"])
        parent_hashes = {
            axis: _axis_sha256(
                _case_axis_values(parent, axis, parent_counts[i])
            )
            for i, axis in enumerate(("x", "y", "z"))
        }
        for axis in ("x", "y", "z"):
            if axis == changed_axis and actual_hashes[axis] == parent_hashes[axis]:
                raise AssertionError(f"Task40 D15 {case} did not change {axis}")
            if axis != changed_axis and actual_hashes[axis] != parent_hashes[axis]:
                raise AssertionError(f"Task40 D15 {case} changed non-target {axis}")
    if parent is None:
        parent_axis_hashes = base_hashes
    else:
        parent_counts = tuple(D15_CASES[parent]["axis_cell_counts"])
        parent_axis_hashes = {
            axis: _axis_sha256(
                _case_axis_values(parent, axis, parent_counts[index])
            )
            for index, axis in enumerate(("x", "y", "z"))
        }
    payload = {
        "schema": "task40.phi90.d15.axis_plan.v2",
        "case": case,
        "parent_case": parent,
        "previous_case": previous_case,
        "changed_axis": changed_axis,
        "axis_cell_counts": list(counts),
        "segment_cell_counts": {axis: list(values) for axis, values in segment_counts.items()},
        "axes_nm": {axis: list(values) for axis, values in axes.items()},
        "axis_sha256_le_f64": actual_hashes,
        "base_axis_sha256_le_f64": base_hashes,
        "static_midpoint_tags": tags,
        "nestedness_from_B": nested_from_base,
        "nestedness_from_previous_level": nested_from_previous,
        "static_plan_sha256": static_plan_sha,
        "reuse_existing_h15_b": case == "Z2",
    }
    if case == "Y5_Z2":
        payload["withdrawn_before_run_case"] = True
    if case == "Y5_Z2":
        payload["parent_axis_sha256_le_f64"] = parent_axis_hashes
    plan_sha = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        **payload,
        "plan_id": (
            "task40_phi90_d15_y3_2_axes_v1"
            if case == "Y3_2"
            else "task40_phi90_d15_y5_1_axes_v1"
            if case == "Y5_1"
            else f"task40_phi90_d15_{case.lower()}_axes_v1"
            if case in {"Y6_1", "Y6_2"}
            else "task40_phi90_d15_y5_z2_axes_v1"
            if case == "Y5_Z2"
            else f"task40_phi90_d15_{case.lower()}_axes_v2"
        ),
        "static_plan_record": static_plan_record,
        "mesh_plan_sha256": plan_sha,
        "expected_global_cell_count": total,
        "launchable": bool(facts["launchable"]),
    }

D15_AXIS_PLANS = {case: d15_axis_plan(case) for case in D15_CASES}
D15_AXIS_PLAN_IDS = {str(plan["plan_id"]): case for case, plan in D15_AXIS_PLANS.items()}

def validate_frozen_d15_axes(payload: Mapping[str, object]) -> dict[str, tuple[float, ...]]:
    case = D15_AXIS_PLAN_IDS.get(str(payload.get("mesh_plan_id")))
    if case is None:
        raise ValueError(f"unsupported Task40 D15 frozen axis plan {payload.get('mesh_plan_id')!r}")
    plan = D15_AXIS_PLANS[case]
    if not bool(plan["launchable"]):
        raise ValueError("Task40 D15-Z2 is a historical H15-B reuse alias, not a launch route")
    if payload.get("mesh_plan_sha256") != plan["mesh_plan_sha256"]:
        raise ValueError("Task40 D15 mesh plan SHA256 mismatch")
    if tuple(payload.get("mesh_axis_cell_counts") or ()) != tuple(plan["axis_cell_counts"]):
        raise ValueError("Task40 D15 mesh axis cell counts mismatch")
    axes = {}
    for axis in ("x", "y", "z"):
        raw = payload.get(f"mesh_axis_{axis}_values")
        if raw is None:
            raise ValueError(f"Task40 D15 frozen mesh requires {axis} coordinates")
        values = tuple(float(value) for value in raw)
        if values != tuple(plan["axes_nm"][axis]):
            raise ValueError(f"Task40 D15 frozen {axis} coordinates differ from plan")
        if _axis_sha256(values) != plan["axis_sha256_le_f64"][axis]:
            raise ValueError(f"Task40 D15 {axis} coordinate hash differs from plan")
        axes[axis] = values
    return axes
