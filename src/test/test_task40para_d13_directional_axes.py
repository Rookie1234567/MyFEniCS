from __future__ import annotations

from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.geometry.mesh_builder_3d import (
    _subdivide_piecewise_axis_exact_count,
    stage4_axis_plan,
)
from src.geometry.task40_phi90_d13_axis_plan import (
    D13_B_AXES_NM,
    D13_B_AXIS_SHA256_LE_F64,
    D13_CASES,
    d13_axis_plan,
    validate_frozen_d13_axes,
)
from src.io.input_loader import InputError, load_dat_input
from src.io.input_validation import (
    _plain,
    _validate_sections,
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.io.native_capacity_profile import native_profile_facts, validate_native_case
from src.runners.p6_condensed_direct import (
    _direct_run_contract,
    _task40_d13_mesh_evidence,
)

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "input" / "task40para_phi90_mesh_modes_direct"
DAT_FILES = {
    "B": "d13_b_r13_p6_direct.dat",
    "X": "d13_x_r13_p6_direct.dat",
    "Y": "d13_y_r13_p6_direct.dat",
    "Z": "d13_z_r13_p6_direct.dat",
    "X2": "d13_x2_from_y2_r13_p6_direct.dat",
    "Z2": "d13_z2_from_y2_r13_p6_direct.dat",
}


@pytest.mark.parametrize("case", ("B", "X", "Y", "Z"))
def test_d13_dat_drives_actual_stage4_planner_to_frozen_one_axis_coordinates(case):
    plan = d13_axis_plan(case)
    specification = load_and_resolve(INPUTS / DAT_FILES[case])
    resolved = specification.as_jsonable()
    config = simulation_config_3d_from_normalized(resolved)
    profile_identity = resolved["derived"]["native_capacity_profile"]["identity"]
    profile_facts = native_profile_facts(profile_identity)
    route = _direct_run_contract(profile_identity)

    actual = stage4_axis_plan(config, comm_size=1)
    actual_axes = {
        axis: np.asarray(getattr(actual, f"{axis}_values"), dtype=np.float64)
        for axis in ("x", "y", "z")
    }
    assert tuple(actual.mesh_cells_resolved) == tuple(plan["axis_cell_counts"])
    assert actual.mesh_spacing_mode_resolved == (
        "boundary_fitted" if case == "B" else "task40_phi90_d13_frozen_axes"
    )
    for axis, values in plan["axes_nm"].items():
        np.testing.assert_array_equal(actual_axes[axis], np.asarray(values))
    assert profile_facts["component_options"]["directional_mesh_comparison"][
        "expected_axis_sha256_le_f64"
    ] == plan["actual_axis_sha256_le_f64"]
    assert route["d13_case"] == case
    assert route["expected_axis_cell_counts"] == list(plan["axis_cell_counts"])
    assert route["d13_expected_axis_sha256_le_f64"] == (
        plan["actual_axis_sha256_le_f64"]
    )

    node_coordinates = np.asarray(
        [
            (x, y, z)
            for z in plan["axes_nm"]["z"]
            for y in plan["axes_nm"]["y"]
            for x in plan["axes_nm"]["x"]
        ],
        dtype=np.float64,
    )
    expected_tags = profile_facts["component_options"][
        "directional_mesh_comparison"
    ]["expected_material_tag_counts"]
    tags = np.concatenate(
        [
            np.full(expected_tags["1"], 1, dtype=np.int32),
            np.full(expected_tags["2"], 2, dtype=np.int32),
            np.full(expected_tags["3"], 3, dtype=np.int32),
        ]
    )
    mesh = SimpleNamespace(
        geometry=SimpleNamespace(x=node_coordinates),
        topology=SimpleNamespace(
            dim=3,
            index_map=lambda dim: SimpleNamespace(
                size_global=plan["expected_global_cell_count"]
            ),
            cell_name=lambda: "hexahedron",
        ),
    )
    evidence = _task40_d13_mesh_evidence(
        {"mesh_data": SimpleNamespace(
            mesh=mesh, cell_tags=SimpleNamespace(values=tags)
        )},
        SimpleNamespace(tags=SimpleNamespace(air=1, substrate=2, grating=3)),
        route,
    )
    assert evidence["status"] == "PASS"
    assert evidence["case"] == case
    assert evidence["changed_axis"] == D13_CASES[case]["changed_axis"]
    assert evidence["actual_global_cell_count"] == plan["expected_global_cell_count"]

    if case == "B":
        assert D13_B_AXIS_SHA256_LE_F64 == plan["actual_axis_sha256_le_f64"]
    else:
        changed = D13_CASES[case]["changed_axis"]
        assert changed in {"x", "y", "z"}
        for axis in ("x", "y", "z"):
            if axis == changed:
                assert plan["actual_axis_sha256_le_f64"][axis] != (
                    D13_B_AXIS_SHA256_LE_F64[axis]
                )
            else:
                assert plan["actual_axis_sha256_le_f64"][axis] == (
                    D13_B_AXIS_SHA256_LE_F64[axis]
                )


def test_d13_y_quota_445_fallback_is_rejected_instead_of_masquerading_as_bisection():
    # The generic length-quota helper allocates 12 Y cells as 4/5/3 over
    # [0,15], [15,35], [35,50]. D13-Y must instead bisect the six realized B
    # intervals, producing four cells in each of those three regions.
    wrong_y = tuple(
        float(value)
        for value in _subdivide_piecewise_axis_exact_count(
            0.0, 50.0, [15.0, 35.0], num_cells=12
        )
    )
    quota_segments = tuple(
        sum(
            left >= low and right <= high
            for left, right in pairwise(wrong_y)
        )
        for low, high in ((0.0, 15.0), (15.0, 35.0), (35.0, 50.0))
    )
    assert quota_segments == (4, 5, 3)

    y_plan = d13_axis_plan("Y")
    correct_y = tuple(y_plan["axes_nm"]["y"])
    correct_segments = tuple(
        sum(
            left >= low and right <= high
            for left, right in pairwise(correct_y)
        )
        for low, high in ((0.0, 15.0), (15.0, 35.0), (35.0, 50.0))
    )
    assert correct_segments == (4, 4, 4)
    assert correct_y != wrong_y

    invalid_payload = {
        "mesh_plan_id": y_plan["plan_id"],
        "mesh_plan_sha256": y_plan["mesh_plan_sha256"],
        "mesh_axis_cell_counts": y_plan["axis_cell_counts"],
        "mesh_axis_x_values": y_plan["axes_nm"]["x"],
        "mesh_axis_y_values": wrong_y,
        "mesh_axis_z_values": y_plan["axes_nm"]["z"],
    }
    with pytest.raises(ValueError, match="y coordinates differ"):
        validate_frozen_d13_axes(invalid_payload)

    loaded = load_dat_input(INPUTS / DAT_FILES["Y"])
    config = _validate_sections(_plain(loaded.document))
    config["discretization"]["mesh_axis_y_values"] = wrong_y
    with pytest.raises(InputError, match="invalid frozen D13 mesh"):
        validate_native_case(config)


def test_axis_plan_baseline_is_the_actual_d13_b_coordinate_identity():
    baseline = d13_axis_plan("B")
    assert {
        axis: tuple(values) for axis, values in baseline["axes_nm"].items()
    } == D13_B_AXES_NM
    assert baseline["actual_axis_sha256_le_f64"] == D13_B_AXIS_SHA256_LE_F64


def test_d13_x2_dat_bisects_only_relative_only_y2_x_and_uses_y2_as_parent():
    parent = d13_axis_plan("Y2")
    plan = d13_axis_plan("X2")
    specification = load_and_resolve(INPUTS / DAT_FILES["X2"])
    resolved = specification.as_jsonable()
    config = simulation_config_3d_from_normalized(resolved)
    profile_identity = resolved["derived"]["native_capacity_profile"]["identity"]
    profile_facts = native_profile_facts(profile_identity)
    directional = profile_facts["component_options"]["directional_mesh_comparison"]
    route = _direct_run_contract(profile_identity)

    actual = stage4_axis_plan(config, comm_size=1)
    actual_axes = {
        axis: tuple(float(value) for value in getattr(actual, f"{axis}_values"))
        for axis in ("x", "y", "z")
    }
    parent_axes = parent["axes_nm"]
    assert plan["parent_case"] == "Y2"
    assert plan["axis_cell_counts"] == [12, 24, 14]
    assert plan["expected_global_cell_count"] == 4032
    assert plan["segment_cell_counts"] == {
        "x": [4, 4, 4], "y": [8, 8, 8], "z": [1, 12, 1]
    }
    assert actual.mesh_cells_resolved == (12, 24, 14)
    assert actual.mesh_spacing_mode_resolved == "task40_phi90_d13_frozen_axes"
    for axis in ("x", "y", "z"):
        np.testing.assert_array_equal(
            actual_axes[axis], np.asarray(plan["axes_nm"][axis], dtype=np.float64)
        )
    assert actual_axes["x"] != tuple(parent_axes["x"])
    assert actual_axes["y"] == tuple(parent_axes["y"])
    assert actual_axes["z"] == tuple(parent_axes["z"])
    assert plan["actual_axis_sha256_le_f64"]["y"] == (
        parent["actual_axis_sha256_le_f64"]["y"]
    )
    assert plan["actual_axis_sha256_le_f64"]["z"] == (
        parent["actual_axis_sha256_le_f64"]["z"]
    )
    assert directional["case"] == "X2"
    assert directional["parent_case"] == "Y2"
    assert directional["axis_comparison_parent"] == "Y2"
    assert directional["changed_axis"] == "x"
    assert directional["base_axis_sha256_le_f64"] == (
        parent["actual_axis_sha256_le_f64"]
    )
    assert directional["expected_axis_sha256_le_f64"] == (
        plan["actual_axis_sha256_le_f64"]
    )
    assert directional["only_axis_changes_from_B"] is None
    assert directional["only_axis_changes_from_parent"] == "x"
    assert route["d13_case"] == "X2"
    assert route["d13_axis_comparison_parent"] == "Y2"
    assert route["d13_base_axis_sha256_le_f64"] == (
        parent["actual_axis_sha256_le_f64"]
    )
    assert route["surface_quadrature_degree"] == 28
    assert route["sparse_cutoff_policy"] == (
        "scale_homogeneous_relative_only_v1"
    )

    node_coordinates = np.asarray(
        [
            (x, y, z)
            for z in plan["axes_nm"]["z"]
            for y in plan["axes_nm"]["y"]
            for x in plan["axes_nm"]["x"]
        ],
        dtype=np.float64,
    )
    expected_tags = directional["expected_material_tag_counts"]
    tags = np.concatenate(
        [
            np.full(expected_tags["1"], 1, dtype=np.int32),
            np.full(expected_tags["2"], 2, dtype=np.int32),
            np.full(expected_tags["3"], 3, dtype=np.int32),
        ]
    )
    mesh = SimpleNamespace(
        geometry=SimpleNamespace(x=node_coordinates),
        topology=SimpleNamespace(
            dim=3,
            index_map=lambda dim: SimpleNamespace(size_global=4032),
            cell_name=lambda: "hexahedron",
        ),
    )
    evidence = _task40_d13_mesh_evidence(
        {"mesh_data": SimpleNamespace(
            mesh=mesh, cell_tags=SimpleNamespace(values=tags)
        )},
        SimpleNamespace(tags=SimpleNamespace(air=1, substrate=2, grating=3)),
        route,
    )
    assert evidence["status"] == "PASS"
    assert evidence["parent_case"] == "Y2"
    assert evidence["changed_axis"] == "x"
    assert evidence["only_declared_axis_changed_from_B"] is False
    assert evidence["only_declared_axis_changed_from_parent"] is True


def test_d13_z2_dat_bisects_only_y2_z_and_checks_independent_midpoint_tags():
    parent = d13_axis_plan("Y2")
    plan = d13_axis_plan("Z2")
    specification = load_and_resolve(INPUTS / DAT_FILES["Z2"])
    resolved = specification.as_jsonable()
    config = simulation_config_3d_from_normalized(resolved)
    config.stage4_dtn_order_policy = "explicit_rectangle"
    config.task40_dtn_rectangle_max_m = 4
    config.task40_dtn_rectangle_max_n = 8
    profile_identity = resolved["derived"]["native_capacity_profile"]["identity"]
    profile_facts = native_profile_facts(profile_identity)
    directional = profile_facts["component_options"]["directional_mesh_comparison"]
    route = _direct_run_contract(profile_identity)

    parent_z = tuple(float(value) for value in parent["axes_nm"]["z"])
    expected_z = [parent_z[0]]
    for left, right in pairwise(parent_z):
        expected_z.extend((left + (right - left) / 2.0, right))
    axes = plan["axes_nm"]
    assert plan["parent_case"] == "Y2"
    assert tuple(plan["axis_cell_counts"]) == (6, 24, 28)
    assert plan["expected_global_cell_count"] == 4032
    assert plan["segment_cell_counts"] == {
        "x": [2, 2, 2], "y": [8, 8, 8], "z": [2, 24, 2]
    }
    assert tuple(axes["x"]) == tuple(parent["axes_nm"]["x"])
    assert tuple(axes["y"]) == tuple(parent["axes_nm"]["y"])
    assert tuple(axes["z"]) == tuple(expected_z)
    assert plan["actual_axis_sha256_le_f64"]["x"] == (
        parent["actual_axis_sha256_le_f64"]["x"]
    )
    assert plan["actual_axis_sha256_le_f64"]["y"] == (
        parent["actual_axis_sha256_le_f64"]["y"]
    )
    assert plan["actual_axis_sha256_le_f64"]["z"] != (
        parent["actual_axis_sha256_le_f64"]["z"]
    )
    assert plan["axes_nm"]["z"] == [
        -10.0, -5.0, 0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0,
        40.0, 45.0, 50.0, 55.0, 60.0, 65.0, 70.0, 75.0, 80.0, 85.0,
        90.0, 95.0, 100.0, 105.0, 110.0, 115.0, 120.0, 125.0, 130.0,
    ]

    actual = stage4_axis_plan(config, comm_size=1)
    actual_axes = {
        axis: tuple(float(value) for value in getattr(actual, f"{axis}_values"))
        for axis in ("x", "y", "z")
    }
    assert actual.mesh_cells_resolved == (6, 24, 28)
    assert actual.mesh_spacing_mode_resolved == "task40_phi90_d13_frozen_axes"
    assert actual_axes == {axis: tuple(axes[axis]) for axis in ("x", "y", "z")}
    assert directional["case"] == "Z2"
    assert directional["parent_case"] == "Y2"
    assert directional["axis_comparison_parent"] == "Y2"
    assert directional["changed_axis"] == "z"
    assert directional["base_axis_sha256_le_f64"] == (
        parent["actual_axis_sha256_le_f64"]
    )
    assert directional["only_axis_changes_from_B"] is None
    assert directional["only_axis_changes_from_parent"] == "z"
    assert directional["expected_axis_sha256_le_f64"] == (
        plan["actual_axis_sha256_le_f64"]
    )
    assert directional["expected_material_tag_counts"] == {
        "1": 3360, "2": 288, "3": 384
    }
    assert profile_facts["component_options"]["mode_selection"][
        "active_rectangle_max_abs_m_n"
    ] == [4, 8]
    assert profile_facts["component_options"]["surface_quadrature"]["degree"] == 28
    assert profile_facts["component_options"]["volume_quadrature"]["degree"] == 15
    assert profile_facts["component_options"]["dtn_sparse_cutoff_policy"] == (
        "scale_homogeneous_relative_only_v1"
    )
    from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory

    modes, mode_rows, mode_sha = build_dynamic_mode_inventory(config)
    assert len(modes) == len(mode_rows) == 612
    assert mode_sha == "1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e"
    assert route["d13_case"] == "Z2"
    assert route["d13_axis_comparison_parent"] == "Y2"
    assert route["d13_base_axis_sha256_le_f64"] == (
        parent["actual_axis_sha256_le_f64"]
    )
    assert route["surface_quadrature_degree"] == 28
    assert route["sparse_cutoff_policy"] == (
        "scale_homogeneous_relative_only_v1"
    )

    # Classify each fake cell independently from its interval midpoint rather
    # than constructing tags from the profile's own expected counts.
    cell_tags = []
    for z0, z1 in zip(axes["z"], axes["z"][1:]):
        zm = (z0 + z1) / 2.0
        for y0, y1 in zip(axes["y"], axes["y"][1:]):
            ym = (y0 + y1) / 2.0
            for x0, x1 in zip(axes["x"], axes["x"][1:]):
                xm = (x0 + x1) / 2.0
                if zm < 0.0:
                    cell_tags.append(2)
                elif (
                    0.0 <= zm < 120.0
                    and 16.5 < xm < 33.5
                    and 15.0 < ym < 35.0
                ):
                    cell_tags.append(3)
                else:
                    cell_tags.append(1)
    cell_tags = np.asarray(cell_tags, dtype=np.int32)
    assert {
        tag: int(np.count_nonzero(cell_tags == tag)) for tag in (1, 2, 3)
    } == {1: 3360, 2: 288, 3: 384}

    node_coordinates = np.asarray(
        [
            (x, y, z)
            for z in axes["z"]
            for y in axes["y"]
            for x in axes["x"]
        ],
        dtype=np.float64,
    )
    fake_mesh = SimpleNamespace(
        geometry=SimpleNamespace(x=node_coordinates),
        topology=SimpleNamespace(
            dim=3,
            index_map=lambda _dim: SimpleNamespace(size_global=4032),
            cell_name=lambda: "hexahedron",
        ),
    )
    levels = {
        "mesh_data": SimpleNamespace(
            mesh=fake_mesh, cell_tags=SimpleNamespace(values=cell_tags)
        )
    }
    mesh_cfg = SimpleNamespace(tags=SimpleNamespace(air=1, substrate=2, grating=3))
    evidence = _task40_d13_mesh_evidence(levels, mesh_cfg, route)
    assert evidence["status"] == "PASS"
    assert evidence["parent_case"] == "Y2"
    assert evidence["changed_axis"] == "z"
    assert evidence["actual_global_cell_count"] == 4032
    assert evidence["material_tag_counts"] == {
        "1": 3360,
        "2": 288,
        "3": 384,
    }

    bad_z = dict(axes)
    bad_z["z"] = list(parent["axes_nm"]["z"])
    bad_payload = {
        "mesh_plan_id": plan["plan_id"],
        "mesh_plan_sha256": plan["mesh_plan_sha256"],
        "mesh_axis_cell_counts": plan["axis_cell_counts"],
        "mesh_axis_x_values": axes["x"],
        "mesh_axis_y_values": axes["y"],
        "mesh_axis_z_values": bad_z["z"],
    }
    with pytest.raises(ValueError, match="z coordinates differ"):
        validate_frozen_d13_axes(bad_payload)

    whole_middle_layer_as_grating = cell_tags.copy()
    for index in range(whole_middle_layer_as_grating.size):
        iz = index // (len(axes["x"]) - 1) // (len(axes["y"]) - 1)
        zm = (axes["z"][iz] + axes["z"][iz + 1]) / 2.0
        if 0.0 <= zm < 120.0:
            whole_middle_layer_as_grating[index] = 3
    levels["mesh_data"].cell_tags.values = whole_middle_layer_as_grating
    with pytest.raises(ValueError, match="material tag counts differ"):
        _task40_d13_mesh_evidence(levels, mesh_cfg, route)
    assert evidence["axis_sha256_le_f64"] == plan["actual_axis_sha256_le_f64"]


def test_d13_x2_frozen_plan_rejects_y_axis_drift_from_y2_parent():
    plan = d13_axis_plan("X2")
    bad_y = list(plan["axes_nm"]["y"])
    bad_y[3] += 0.03125
    payload = {
        "mesh_plan_id": plan["plan_id"],
        "mesh_plan_sha256": plan["mesh_plan_sha256"],
        "mesh_axis_cell_counts": plan["axis_cell_counts"],
        "mesh_axis_x_values": plan["axes_nm"]["x"],
        "mesh_axis_y_values": bad_y,
        "mesh_axis_z_values": plan["axes_nm"]["z"],
    }
    with pytest.raises(ValueError, match="y coordinates differ"):
        validate_frozen_d13_axes(payload)
