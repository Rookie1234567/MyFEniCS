from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import tomllib

from src.geometry.mesh_builder_3d import stage4_axis_plan
from src.geometry.task40_phi90_h15_axis_plan import (
    H15_AXIS_PLANS,
    H15_BASE_AXES_NM,
    H15_BASE_AXIS_SHA256_LE_F64,
    validate_frozen_h15_axes,
)
from src.io.input_loader import InputError, load_dat_input
from src.io.input_validation import (
    _plain,
    _validate_sections,
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.io.native_capacity_profile import (
    TASK40_PHI90_H15_PROFILES,
    native_profile_facts,
    validate_native_case,
)
from src.runners.p6_condensed_direct import (
    _direct_run_contract,
    _task40_h15_mesh_evidence,
)

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "input" / "task40para_phi90_mesh_modes_direct"
DAT_FILES = {
    "B": "h15_b_r13_p6_direct.dat",
    "X": "h15_x_r13_p6_direct.dat",
    "Y": "h15_y_r13_p6_direct.dat",
    "Z": "h15_z_r13_p6_direct.dat",
}


@pytest.mark.parametrize("case", ("B", "X", "Y", "Z"))
def test_h15_dat_resolves_to_exact_boundary_fitted_axes_and_profile(case):
    plan = H15_AXIS_PLANS[case]
    specification = load_and_resolve(INPUTS / DAT_FILES[case])
    resolved = specification.as_jsonable()
    cfg = simulation_config_3d_from_normalized(resolved)
    profile_id = resolved["derived"]["native_capacity_profile"]["identity"]
    facts = native_profile_facts(profile_id)
    comparison = facts["component_options"]["directional_mesh_comparison"]
    route = _direct_run_contract(profile_id)

    assert profile_id in TASK40_PHI90_H15_PROFILES
    assert tuple(plan["axis_cell_counts"]) == tuple(
        facts["component_options"]["expected_axis_cell_counts"]
    )
    assert facts["allowed_mesh_targets_nm"] == [15.0]
    assert facts["component_options"]["mesh_target_nm"] == 15.0
    assert facts["component_options"]["mode_selection"][
        "parent_inventory_scope"
    ] == "R13_finite_rectangle_including_evanescent"
    assert facts["component_options"]["surface_quadrature"]["degree"] == 28
    assert facts["component_options"]["volume_quadrature"] == {
        "degree": 15,
        "rule": "default",
        "authority": "live_fine_volume_quadrature_metadata",
    }
    assert facts["resources"]["rss_hard_limit_bytes"] is None
    assert facts["resources"]["minimum_available_bytes"] == 64 * 1024**3
    assert comparison["expected_axis_sha256_le_f64"] == plan[
        "actual_axis_sha256_le_f64"
    ]
    assert route["task40_mesh_plan_family"] == "h15"
    assert route["task40_mesh_case"] == case
    assert route["expected_axis_cell_counts"] == list(plan["axis_cell_counts"])
    assert route["expected_global_cell_count"] == plan["expected_global_cell_count"]
    assert route["surface_quadrature_degree"] == 28
    assert route["sparse_cutoff_policy"] == "scale_homogeneous_relative_only_v1"

    planned = stage4_axis_plan(cfg, comm_size=1)
    actual_axes = {
        axis: tuple(float(v) for v in getattr(planned, f"{axis}_values"))
        for axis in ("x", "y", "z")
    }
    assert planned.mesh_cells_resolved == tuple(plan["axis_cell_counts"])
    assert planned.mesh_spacing_mode_resolved == "task40_phi90_h15_frozen_axes"
    assert actual_axes == {
        axis: tuple(float(v) for v in plan["axes_nm"][axis])
        for axis in ("x", "y", "z")
    }

    coordinates = np.asarray(
        [
            (x, y, z)
            for z in plan["axes_nm"]["z"]
            for y in plan["axes_nm"]["y"]
            for x in plan["axes_nm"]["x"]
        ],
        dtype=np.float64,
    )
    axes = {axis: tuple(plan["axes_nm"][axis]) for axis in ("x", "y", "z")}
    cell_tag_values = []
    for z0, z1 in zip(axes["z"], axes["z"][1:]):
        z_mid = (z0 + z1) / 2.0
        for y0, y1 in zip(axes["y"], axes["y"][1:]):
            y_mid = (y0 + y1) / 2.0
            for x0, x1 in zip(axes["x"], axes["x"][1:]):
                x_mid = (x0 + x1) / 2.0
                if z_mid < 0.0:
                    tag = 2
                elif z_mid < 120.0 and 16.5 < x_mid < 33.5 and 15.0 < y_mid < 35.0:
                    tag = 3
                else:
                    tag = 1
                cell_tag_values.append(tag)
    cell_tags = np.asarray(cell_tag_values, dtype=np.int32)
    expected_tag_counts = {
        "1": 184 if case == "B" else 368,
        "2": 24 if case == "B" else 48,
        "3": 32 if case == "B" else 64,
    }
    assert comparison["expected_material_tag_counts"] == expected_tag_counts
    fake_mesh = SimpleNamespace(
        geometry=SimpleNamespace(x=coordinates),
        topology=SimpleNamespace(
            dim=3,
            index_map=lambda _dim: SimpleNamespace(
                size_global=plan["expected_global_cell_count"]
            ),
            cell_name=lambda: "hexahedron",
        ),
    )
    evidence = _task40_h15_mesh_evidence(
        {"mesh_data": SimpleNamespace(
            mesh=fake_mesh, cell_tags=SimpleNamespace(values=cell_tags)
        )},
        SimpleNamespace(tags=SimpleNamespace(air=1, substrate=2, grating=3)),
        route,
    )
    assert evidence["status"] == "PASS"
    assert evidence["actual_global_cell_count"] == plan["expected_global_cell_count"]
    assert evidence["axis_sha256_le_f64"] == plan["actual_axis_sha256_le_f64"]
    assert evidence["material_tag_counts"] == {
        "1": expected_tag_counts["1"],
        "2": expected_tag_counts["2"],
        "3": expected_tag_counts["3"],
    }
    wrong_whole_middle_layer = cell_tags.copy()
    for index, tag in enumerate(wrong_whole_middle_layer):
        z_index = index // (plan["axis_cell_counts"][0] * plan["axis_cell_counts"][1])
        z_mid = (axes["z"][z_index] + axes["z"][z_index + 1]) / 2.0
        if 0.0 < z_mid < 120.0:
            wrong_whole_middle_layer[index] = 3
    with pytest.raises(ValueError, match="material tag counts differ"):
        _task40_h15_mesh_evidence(
            {"mesh_data": SimpleNamespace(
                mesh=fake_mesh, cell_tags=SimpleNamespace(values=wrong_whole_middle_layer)
            )},
            SimpleNamespace(tags=SimpleNamespace(air=1, substrate=2, grating=3)),
            route,
        )


def test_h15_base_coordinates_equal_unfrozen_actual_boundary_fitted_planner():
    resolved = load_and_resolve(INPUTS / DAT_FILES["B"]).as_jsonable()
    cfg = simulation_config_3d_from_normalized(resolved)
    cfg.mesh_axis_cell_counts = None
    cfg.mesh_axis_x_values = None
    cfg.mesh_axis_y_values = None
    cfg.mesh_axis_z_values = None
    cfg.mesh_plan_id = None
    cfg.mesh_plan_sha256 = None
    actual = stage4_axis_plan(cfg, comm_size=1)
    axes = {
        axis: tuple(float(v) for v in getattr(actual, f"{axis}_values"))
        for axis in ("x", "y", "z")
    }
    assert axes == H15_BASE_AXES_NM
    assert actual.mesh_cells_resolved == (6, 4, 10)
    assert H15_AXIS_PLANS["B"]["actual_axis_sha256_le_f64"] == (
        H15_BASE_AXIS_SHA256_LE_F64
    )


def test_h15_axis_validator_rejects_plan_hash_count_and_segment_quota_drift():
    plan = H15_AXIS_PLANS["Y"]
    payload = {
        "mesh_plan_id": plan["plan_id"],
        "mesh_plan_sha256": plan["mesh_plan_sha256"],
        "mesh_axis_cell_counts": plan["axis_cell_counts"],
        "mesh_axis_x_values": plan["axes_nm"]["x"],
        "mesh_axis_y_values": plan["axes_nm"]["y"],
        "mesh_axis_z_values": plan["axes_nm"]["z"],
    }
    assert validate_frozen_h15_axes(payload)["y"] == tuple(plan["axes_nm"]["y"])

    wrong_hash = dict(payload, mesh_plan_sha256="0" * 64)
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        validate_frozen_h15_axes(wrong_hash)
    wrong_counts = dict(payload, mesh_axis_cell_counts=(6, 4, 10))
    with pytest.raises(ValueError, match="cell counts mismatch"):
        validate_frozen_h15_axes(wrong_counts)
    wrong_y = (0.0, 7.5, 15.0, 20.0, 25.0, 32.5, 35.0, 42.5, 50.0)
    wrong_segment_payload = dict(payload, mesh_axis_y_values=wrong_y)
    with pytest.raises(ValueError, match="y coordinates differ"):
        validate_frozen_h15_axes(wrong_segment_payload)

    loaded = load_dat_input(INPUTS / DAT_FILES["Y"])
    config = _validate_sections(_plain(loaded.document))
    config["discretization"]["mesh_axis_y_values"] = wrong_y
    with pytest.raises(InputError, match="invalid frozen H15 mesh"):
        validate_native_case(config)


def test_h15_profile_dispatch_is_separate_from_d13_identities():
    assert TASK40_PHI90_H15_PROFILES == {
        "task40para_phi90_13p5_H15_B_p6_direct_v1": "B",
        "task40para_phi90_13p5_H15_X_p6_direct_v1": "X",
        "task40para_phi90_13p5_H15_Y_p6_direct_v1": "Y",
        "task40para_phi90_13p5_H15_Z_p6_direct_v1": "Z",
    }
    for case in ("B", "X", "Y", "Z"):
        loaded = load_dat_input(INPUTS / DAT_FILES[case])
        config = _validate_sections(_plain(loaded.document))
        validate_native_case(config)
        resolved = load_and_resolve(INPUTS / DAT_FILES[case]).as_jsonable()
        assert resolved["derived"]["native_capacity_profile"]["identity"] == (
            f"task40para_phi90_13p5_H15_{case}_p6_direct_v1"
        )


def test_h15_inputs_preserve_the_d13_b_physics_and_only_change_mesh_identity():
    baseline = tomllib.loads(
        (INPUTS / "d13_b_r13_p6_direct.dat").read_text(encoding="utf-8")
    )
    h15_base = tomllib.loads(
        (INPUTS / DAT_FILES["B"]).read_text(encoding="utf-8")
    )
    for section in (
        "geometry", "materials", "incidence", "boundary", "method", "execution", "output"
    ):
        assert h15_base[section] == baseline[section]
    base_discretization = dict(baseline["discretization"])
    h15_discretization = dict(h15_base["discretization"])
    base_discretization["mesh_target_nm"] = 15.0
    for key in (
        "mesh_axis_cell_counts", "mesh_axis_x_values", "mesh_axis_y_values",
        "mesh_axis_z_values", "mesh_plan_id", "mesh_plan_sha256",
    ):
        h15_discretization.pop(key)
    assert h15_discretization == base_discretization

    for case in ("X", "Y", "Z"):
        candidate = tomllib.loads(
            (INPUTS / DAT_FILES[case]).read_text(encoding="utf-8")
        )
        for section in (
            "geometry", "materials", "incidence", "boundary", "method", "execution", "output"
        ):
            assert candidate[section] == h15_base[section]
        candidate_axes = candidate["discretization"]
        for key in ("nedelec_degree", "visualization_degree", "mesh_target_nm",
                    "mesh_cell_type", "mesh_spacing_mode", "assembly_backend",
                    "floquet_constraint_mode"):
            assert candidate_axes[key] == h15_base["discretization"][key]
        plan = H15_AXIS_PLANS[case]
        assert candidate_axes["mesh_axis_cell_counts"] == plan["axis_cell_counts"]
        for axis in ("x", "y", "z"):
            assert candidate_axes[f"mesh_axis_{axis}_values"] == plan["axes_nm"][axis]
