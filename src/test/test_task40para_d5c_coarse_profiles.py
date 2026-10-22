"""D5C coarse 5 nm planner, profile, live-mesh gate, and input checks."""

from __future__ import annotations

from collections import Counter
from itertools import pairwise, product
from math import prod
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.geometry.mesh_builder_3d import stage4_axis_plan
from src.geometry.task40_phi90_d5c_axis_plan import (
    D5C_BASE_AXIS_SHA256_LE_F64,
    D5C_CASE_SEGMENT_COUNTS,
    d5c_axis_plan,
)
from src.io.input_loader import InputError, load_dat_input
from src.io.input_validation import (
    _plain,
    _validate_sections,
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.io.native_capacity_profile import (
    TASK40_PHI90_D5C_PROFILE_BY_CASE,
    native_profile_facts,
    validate_native_case,
)
from src.runners.p6_condensed_direct import (
    _direct_run_contract,
    _task40_d5c_mesh_evidence,
)

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "input" / "task40para_phi90_mesh_modes_direct"
DAT_FILES = {
    case: INPUTS / f"d5c_{case.lower()}_r5_p6_direct.dat"
    for case in D5C_CASE_SEGMENT_COUNTS
}
EXPECTED_TAGS = {
    "B": {"1": 136, "2": 72, "3": 8},
    "X1": {"1": 216, "2": 120, "3": 24},
    "X2": {"1": 360, "2": 192, "3": 24},
    "X3": {"1": 456, "2": 240, "3": 24},
    "Y1": {"1": 216, "2": 120, "3": 24},
    "Y2": {"1": 360, "2": 192, "3": 24},
    "Y3": {"1": 456, "2": 240, "3": 24},
    "Y4": {"1": 440, "2": 240, "3": 40},
    "Y5": {"1": 600, "2": 312, "3": 24},
    "Z1": {"1": 264, "2": 72, "3": 24},
    "Z2": {"1": 372, "2": 180, "3": 24},
    "Z3": {"1": 444, "2": 252, "3": 24},
}


def _independent_midpoint_tags(plan):
    axes = plan["axes_nm"]
    tags: list[int] = []
    for z0, z1 in pairwise(axes["z"]):
        zmid = 0.5 * (z0 + z1)
        for y0, y1 in pairwise(axes["y"]):
            ymid = 0.5 * (y0 + y1)
            for x0, x1 in pairwise(axes["x"]):
                xmid = 0.5 * (x0 + x1)
                if zmid < 0.0:
                    tag = 2
                elif zmid >= 120.0:
                    tag = 1
                elif 16.5 < xmid < 33.5 and 15.0 < ymid < 35.0:
                    tag = 3
                else:
                    tag = 1
                tags.append(tag)
    return Counter({str(key): value for key, value in Counter(tags).items()})


@pytest.mark.parametrize("case", tuple(D5C_CASE_SEGMENT_COUNTS))
def test_d5c_dat_resolves_to_exact_frozen_axes_and_independent_tags(case):
    plan = d5c_axis_plan(case)
    specification = load_and_resolve(DAT_FILES[case])
    resolved = specification.as_jsonable()
    cfg = simulation_config_3d_from_normalized(resolved)
    actual = stage4_axis_plan(cfg, comm_size=1)
    actual_axes = {
        axis: tuple(float(value) for value in getattr(actual, f"{axis}_values"))
        for axis in "xyz"
    }

    assert tuple(actual.mesh_cells_resolved) == tuple(plan["axis_cell_counts"])
    assert actual.mesh_spacing_mode_resolved == "task40_phi90_d5c_frozen_axes"
    for axis in "xyz":
        assert actual_axes[axis] == tuple(plan["axes_nm"][axis])
        if plan["changed_axis"] is None or axis != plan["changed_axis"]:
            assert plan["axis_sha256_le_f64"][axis] == (
                D5C_BASE_AXIS_SHA256_LE_F64[axis]
            )
    assert plan["parent_axis_sha256_le_f64"] == D5C_BASE_AXIS_SHA256_LE_F64
    assert dict(_independent_midpoint_tags(plan)) == EXPECTED_TAGS[case]
    assert plan["expected_material_tag_counts"] == EXPECTED_TAGS[case]
    assert plan["expected_global_cell_count"] == prod(plan["axis_cell_counts"])
    assert plan["static_geometry_only"]["strictly_increasing_axes"] is True
    assert plan["static_geometry_only"]["minimum_cell_volume_nm3"] > 0.0

    profile_id = resolved["solver"]["native_capacity_profile"]
    assert profile_id == TASK40_PHI90_D5C_PROFILE_BY_CASE[case]
    facts = native_profile_facts(profile_id)
    options = facts["component_options"]
    assert options["directional_mesh_comparison"]["expected_material_tag_counts"] == (
        EXPECTED_TAGS[case]
    )
    assert options["mode_selection"]["expected_mode_count"] == 3772
    assert options["mode_selection"]["expected_mode_sha256"] == (
        "752333bbc4082b9d7f9f1c935433eeb8e4c8b5e44a74a27310944b6b8aa531bc"
    )
    assert options["surface_quadrature"]["degree"] == 39
    assert options["volume_quadrature"]["degree"] == 15
    assert options["dtn_sparse_cutoff_policy"] == (
        "scale_homogeneous_relative_only_v1"
    )
    assert facts["full_dtn_status"] == "FULL_DTN_NOT_VERIFIED"
    assert resolved["incidence"]["wavelength_nm"] == 5.0
    assert resolved["discretization"]["nedelec_degree"] == 6


@pytest.mark.parametrize("case", tuple(D5C_CASE_SEGMENT_COUNTS))
def test_d5c_profile_validation_and_runner_mesh_evidence(case):
    specification = load_and_resolve(DAT_FILES[case])
    resolved = specification.as_jsonable()
    profile_id = resolved["solver"]["native_capacity_profile"]
    validate_native_case(_validate_sections(_plain(load_dat_input(DAT_FILES[case]).document)))
    route = _direct_run_contract(profile_id)
    assert route["task40_mesh_plan_family"] == "d5c"
    assert route["task40_mesh_case"] == case
    assert route["task40_parent_case"] == "B"
    assert route["parent_count"] == 3772
    assert route["surface_quadrature_degree"] == 39
    assert route["diagnostic_scope"].startswith("TASK40_D5C_")

    plan = d5c_axis_plan(case)
    coords = np.asarray(
        list(product(plan["axes_nm"]["x"], plan["axes_nm"]["y"], plan["axes_nm"]["z"])),
        dtype=np.float64,
    )
    cell_count = plan["expected_global_cell_count"]
    tags = []
    for z0, z1 in pairwise(plan["axes_nm"]["z"]):
        zm = (z0 + z1) / 2
        for y0, y1 in pairwise(plan["axes_nm"]["y"]):
            ym = (y0 + y1) / 2
            for x0, x1 in pairwise(plan["axes_nm"]["x"]):
                xm = (x0 + x1) / 2
                tags.append(2 if zm < 0 else 1 if zm >= 120 else 3 if 16.5 < xm < 33.5 and 15 < ym < 35 else 1)
    msh = SimpleNamespace(
        geometry=SimpleNamespace(x=coords),
        topology=SimpleNamespace(
            dim=3,
            index_map=lambda _dim: SimpleNamespace(size_global=cell_count),
            cell_name=lambda: "hexahedron",
        ),
    )
    levels = {"mesh_data": SimpleNamespace(mesh=msh, cell_tags=SimpleNamespace(values=np.asarray(tags)))}
    cfg = SimpleNamespace(tags=SimpleNamespace(air=1, substrate=2, grating=3))
    evidence = _task40_d5c_mesh_evidence(levels, cfg, route)
    assert evidence["status"] == "PASS"
    assert evidence["actual_global_cell_count"] == cell_count
    assert evidence["material_tag_counts"] == EXPECTED_TAGS[case]


def test_d5c_rejects_the_historical_d5_plan_and_non_target_axis_mutation():
    wrong_family_axes = load_dat_input(DAT_FILES["B"])
    wrong_cfg = _validate_sections(_plain(wrong_family_axes.document))
    old_plan = load_and_resolve(INPUTS / "d5_b_r5_p6_direct.dat").as_jsonable()[
        "discretization"
    ]
    for key in (
        "mesh_plan_id", "mesh_plan_sha256", "mesh_axis_cell_counts",
        "mesh_axis_x_values", "mesh_axis_y_values", "mesh_axis_z_values",
    ):
        wrong_cfg["discretization"][key] = old_plan[key]
    with pytest.raises(InputError, match="invalid frozen D5C axes"):
        validate_native_case(wrong_cfg)

    loaded = load_dat_input(DAT_FILES["X1"])
    cfg = _validate_sections(_plain(loaded.document))
    y = tuple(cfg["discretization"]["mesh_axis_y_values"])
    cfg["discretization"]["mesh_axis_y_values"] = [*y[:-1], y[-1] - 0.25]
    with pytest.raises(InputError, match="invalid frozen D5C axes"):
        validate_native_case(cfg)


def test_d5c_tag_midpoints_do_not_label_the_entire_middle_z_band_as_grating():
    plan = d5c_axis_plan("B")
    whole_middle_as_grating = Counter()
    for z0, z1 in pairwise(plan["axes_nm"]["z"]):
        zm = 0.5 * (z0 + z1)
        for _y0, _y1 in pairwise(plan["axes_nm"]["y"]):
            for _x0, _x1 in pairwise(plan["axes_nm"]["x"]):
                whole_middle_as_grating[2 if zm < 0 else 1 if zm >= 120 else 3] += 1
    assert whole_middle_as_grating == Counter({2: 72, 1: 72, 3: 72})
    assert whole_middle_as_grating != Counter({int(k): v for k, v in EXPECTED_TAGS["B"].items()})
