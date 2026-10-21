"""D15 frozen axis, profile, mesh-evidence, and worker identity contracts."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.geometry.mesh_builder_3d import stage4_axis_plan
from src.geometry.task40_phi90_d15_axis_plan import (
    D15_AXIS_PLANS,
    D15_LAUNCHABLE_CASES,
    D15_STATIC_PLAN_RECORD,
    D15_STATIC_PLAN_SHA256,
    D15_SUPERSEDED_STATIC_PROPOSAL_SHA256,
    D15_Z2_HISTORICAL_REUSE,
    validate_frozen_d15_axes,
)
from src.io.execution_plan import build_execution_plan
from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.io.native_capacity_profile import (
    TASK40_PHI90_D15_PROFILES,
    native_profile_facts,
)
from src.io.run_specification import thaw
from src.runners.p6_condensed_direct import (
    _direct_run_contract,
    _task40_d15_mesh_evidence,
)
from src.runners.task038_input_worker import _load_and_validate_worker_payload
from src.runners.task038_launcher import _write_bootstrap

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "input/task40para_phi90_mesh_modes_direct"
D15_INPUTS = {
    case: INPUTS / f"d15_{case.lower()}_r13_p6_direct.dat"
    for case in D15_LAUNCHABLE_CASES
}
SOURCE_SHA = "d" * 40
D15_Z2_RUN = (
    ROOT
    / D15_Z2_HISTORICAL_REUSE["run_directory"]
)


def _midpoint_cell_tags(plan):
    """Independently classify cells from physical interval midpoints."""
    axes = plan["axes_nm"]
    values = []
    for z0, z1 in zip(axes["z"], axes["z"][1:]):
        zm = (z0 + z1) / 2.0
        for y0, y1 in zip(axes["y"], axes["y"][1:]):
            ym = (y0 + y1) / 2.0
            for x0, x1 in zip(axes["x"], axes["x"][1:]):
                xm = (x0 + x1) / 2.0
                if zm < 0.0:
                    tag = 2
                elif zm < 120.0 and 16.5 < xm < 33.5 and 15.0 < ym < 35.0:
                    tag = 3
                else:
                    tag = 1
                values.append(tag)
    return np.asarray(values, dtype=np.int32)


def _fake_mesh(plan, tags):
    coordinates = np.asarray(
        [
            (x, y, z)
            for z in plan["axes_nm"]["z"]
            for y in plan["axes_nm"]["y"]
            for x in plan["axes_nm"]["x"]
        ],
        dtype=np.float64,
    )
    return SimpleNamespace(
        geometry=SimpleNamespace(x=coordinates),
        topology=SimpleNamespace(
            dim=3,
            index_map=lambda _dim: SimpleNamespace(
                size_global=plan["expected_global_cell_count"]
            ),
            cell_name=lambda: "hexahedron",
        ),
    )


@pytest.mark.parametrize("case", D15_LAUNCHABLE_CASES)
def test_d15_inputs_resolve_to_frozen_planner_route_and_independent_tags(case):
    plan = D15_AXIS_PLANS[case]
    specification = load_and_resolve(D15_INPUTS[case])
    resolved = specification.as_jsonable()
    config = simulation_config_3d_from_normalized(resolved)
    profile_id = resolved["derived"]["native_capacity_profile"]["identity"]
    facts = native_profile_facts(profile_id)
    directional = facts["component_options"]["directional_mesh_comparison"]
    route = _direct_run_contract(profile_id)

    assert profile_id == f"task40para_phi90_13p5_D15_{case}_p6_direct_v1"
    assert profile_id in TASK40_PHI90_D15_PROFILES
    assert config.mesh_plan_id == plan["plan_id"]
    assert facts["allowed_mesh_targets_nm"] == [15.0]
    assert facts["wavelength_nm"] == 13.5
    assert facts["component_options"]["mode_selection"]["expected_mode_count"] == 612
    assert facts["component_options"]["mode_selection"]["expected_mode_sha256"] == (
        "1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e"
    )
    assert facts["component_options"]["surface_quadrature"]["degree"] == 28
    assert facts["component_options"]["volume_quadrature"] == {
        "degree": 15,
        "rule": "default",
        "authority": "live_fine_volume_quadrature_metadata",
    }
    assert facts["component_options"]["dtn_sparse_cutoff_policy"] == (
        "scale_homogeneous_relative_only_v1"
    )
    assert facts["component_options"]["dtn_sparse_cutoff_relative_tolerance"] == 1.0e-13
    assert facts["resources"]["minimum_available_bytes"] == 64 * 1024**3
    assert facts["resources"]["rss_hard_limit_bytes"] is None
    assert facts["full_dtn_status"] == "FULL_DTN_NOT_VERIFIED"
    assert directional["mesh_plan_family"] == "d15"
    assert directional["static_plan_record"] == plan["static_plan_record"]
    assert directional["static_plan_sha256"] == plan["static_plan_sha256"]
    assert directional["expected_axis_sha256_le_f64"] == plan["axis_sha256_le_f64"]
    assert tuple(route["expected_axis_cell_counts"]) == tuple(plan["axis_cell_counts"])
    assert route["expected_global_cell_count"] == plan["expected_global_cell_count"]
    assert route["task40_mesh_plan_family"] == "d15"
    assert route["task40_mesh_case"] == case
    assert route["surface_quadrature_degree"] == 28

    planned = stage4_axis_plan(config, comm_size=1)
    actual_axes = {
        axis: tuple(float(v) for v in getattr(planned, f"{axis}_values"))
        for axis in ("x", "y", "z")
    }
    assert tuple(planned.mesh_cells_resolved) == tuple(plan["axis_cell_counts"])
    assert planned.mesh_spacing_mode_resolved == "task40_phi90_d15_frozen_axes"
    assert actual_axes == {
        axis: tuple(plan["axes_nm"][axis]) for axis in ("x", "y", "z")
    }
    assert all(
        width > 0.0
        for axis in actual_axes.values()
        for width in np.diff(np.asarray(axis, dtype=np.float64))
    )

    tags = _midpoint_cell_tags(plan)
    static_counts = {
        1: int(np.count_nonzero(tags == 1)),
        2: int(np.count_nonzero(tags == 2)),
        3: int(np.count_nonzero(tags == 3)),
    }
    assert static_counts == {
        1: plan["static_midpoint_tags"]["air"],
        2: plan["static_midpoint_tags"]["substrate"],
        3: plan["static_midpoint_tags"]["grating"],
    }
    evidence = _task40_d15_mesh_evidence(
        {"mesh_data": SimpleNamespace(mesh=_fake_mesh(plan, tags),
                                      cell_tags=SimpleNamespace(values=tags))},
        SimpleNamespace(tags=SimpleNamespace(air=1, substrate=2, grating=3)),
        route,
    )
    assert evidence["status"] == "PASS"
    assert evidence["actual_global_cell_count"] == plan["expected_global_cell_count"]
    assert evidence["axis_sha256_le_f64"] == plan["axis_sha256_le_f64"]
    assert evidence["material_tag_counts"] == {
        "1": plan["static_midpoint_tags"]["air"],
        "2": plan["static_midpoint_tags"]["substrate"],
        "3": plan["static_midpoint_tags"]["grating"],
    }

    # A mistaken whole-middle-z-layer tag must fail the unchanged live tag gate.
    wrong_tags = tags.copy()
    nxy = plan["axis_cell_counts"][0] * plan["axis_cell_counts"][1]
    for cell in range(wrong_tags.size):
        iz = cell // nxy
        zmid = (plan["axes_nm"]["z"][iz] + plan["axes_nm"]["z"][iz + 1]) / 2.0
        if 0.0 <= zmid < 120.0:
            wrong_tags[cell] = 3
    assert wrong_tags.size == math.prod(plan["axis_cell_counts"])
    with pytest.raises(ValueError, match="material tags differ"):
        _task40_d15_mesh_evidence(
            {"mesh_data": SimpleNamespace(mesh=_fake_mesh(plan, wrong_tags),
                                          cell_tags=SimpleNamespace(values=wrong_tags))},
            SimpleNamespace(tags=SimpleNamespace(air=1, substrate=2, grating=3)),
            route,
        )


def test_d15_y3_user_correction_and_static_record_supersede_v1():
    plan = D15_AXIS_PLANS["Y3"]
    assert tuple(plan["axes_nm"]["y"]) == (
        0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0
    )
    assert plan["segment_cell_counts"]["y"] == [3, 4, 3]
    assert plan["static_midpoint_tags"] == {
        "air": 268, "substrate": 60, "grating": 32
    }
    record = json.loads((ROOT / D15_STATIC_PLAN_RECORD).read_text())
    record_sha = hashlib.sha256((ROOT / D15_STATIC_PLAN_RECORD).read_bytes()).hexdigest()
    assert record_sha == D15_STATIC_PLAN_SHA256
    assert record["supersedes"]["proposal_sha256"] == D15_SUPERSEDED_STATIC_PROPOSAL_SHA256
    assert next(row for row in record["cases"] if row["case"] == "Y3")[
        "static_midpoint_tags"
    ] == {"air": 268, "substrate": 60, "grating": 32}


def test_d15_y3_2_uses_supplemental_2_6_2_axes_and_independent_tags():
    plan = D15_AXIS_PLANS["Y3_2"]
    assert plan["plan_id"] == "task40_phi90_d15_y3_2_axes_v1"
    assert plan["axis_cell_counts"] == [6, 10, 6]
    assert plan["expected_global_cell_count"] == 360
    assert plan["segment_cell_counts"] == {
        "x": [2, 2, 2], "y": [2, 6, 2], "z": [1, 4, 1]
    }
    assert tuple(plan["axes_nm"]["y"]) == (
        0.0, 7.5, 15.0, 18.333333333333332, 21.666666666666668,
        25.0, 28.333333333333336, 31.666666666666668, 35.0, 42.5, 50.0
    )
    assert plan["axes_nm"]["x"] == D15_AXIS_PLANS["B"]["axes_nm"]["x"]
    assert plan["axes_nm"]["z"] == D15_AXIS_PLANS["B"]["axes_nm"]["z"]
    assert plan["axis_sha256_le_f64"]["x"] == D15_AXIS_PLANS["B"]["axis_sha256_le_f64"]["x"]
    assert plan["axis_sha256_le_f64"]["z"] == D15_AXIS_PLANS["B"]["axis_sha256_le_f64"]["z"]
    assert plan["static_midpoint_tags"] == {
        "air": 252, "substrate": 60, "grating": 48
    }
    assert plan["parent_case"] == "B"
    assert plan["previous_case"] == "Y3"
    assert plan["nestedness_from_previous_level"] is False
    supplement = ROOT / plan["static_plan_record"]
    assert hashlib.sha256(supplement.read_bytes()).hexdigest() == plan["static_plan_sha256"]
    resolved = load_and_resolve(D15_INPUTS["Y3_2"]).as_jsonable()
    discretization = resolved["discretization"]
    assert tuple(discretization["mesh_axis_cell_counts"]) == (6, 10, 6)
    assert tuple(discretization["mesh_axis_y_values"]) == tuple(plan["axes_nm"]["y"])
    assert discretization["mesh_plan_id"] == plan["plan_id"]
    assert discretization["mesh_plan_sha256"] == plan["mesh_plan_sha256"]


def test_d15_z2_is_exact_h15_b_historical_reuse_not_a_launch_input():
    plan = D15_AXIS_PLANS["Z2"]
    reuse = D15_Z2_HISTORICAL_REUSE
    assert plan["launchable"] is False
    assert "Z2" not in TASK40_PHI90_D15_PROFILES.values()
    assert not (INPUTS / "d15_z2_r13_p6_direct.dat").exists()
    assert plan["axis_cell_counts"] == reuse["axis_cell_counts"]
    assert plan["axis_sha256_le_f64"] == reuse["axis_sha256_le_f64"]

    manifest = json.loads((D15_Z2_RUN / "run_manifest.json").read_text())
    summary = json.loads((D15_Z2_RUN / "run_summary.json").read_text())
    direct = json.loads((D15_Z2_RUN / "p6_condensed_direct_summary.json").read_text())
    assert manifest["run_id"] == reuse["run_id"]
    assert manifest["source_sha"] == reuse["source_sha"]
    assert manifest["input_sha256"] == reuse["input_sha256"]
    assert manifest["physical_model_sha256"] == reuse["physical_model_sha256"]
    assert manifest["resolved_config_sha256"] == reuse["resolved_config_sha256"]
    assert manifest["status"] == "finished"
    assert summary["status"] == "finished"
    assert direct["status"] == "TASK40_PHI90_H15_B_P6_DIRECT_R13_COMPLETED_AUTHORITY_LIMITED"
    mesh = direct["mesh_evidence"]
    operator = direct["operator_identity"]
    assert tuple(mesh["axis_cell_counts"]) == (6, 4, 10)
    assert mesh["axis_sha256_le_f64"] == reuse["axis_sha256_le_f64"]
    assert operator["active_mode_count"] == reuse["mode_count"]
    assert operator["active_mode_sha256"] == reuse["mode_sha256"]
    assert operator["parent_quadrature_degree"] == reuse["surface_quadrature_degree"]
    assert operator["dtn_sparse_cutoff_policy"] == reuse["dtn_sparse_cutoff_policy"]
    assert operator["dtn_sparse_cutoff_relative_tolerance"] == reuse[
        "dtn_sparse_cutoff_relative_tolerance"
    ]


def test_d15_axis_validator_fails_closed_on_y3_axis_drift():
    plan = D15_AXIS_PLANS["Y3"]
    payload = {
        "mesh_plan_id": plan["plan_id"],
        "mesh_plan_sha256": plan["mesh_plan_sha256"],
        "mesh_axis_cell_counts": plan["axis_cell_counts"],
        "mesh_axis_x_values": plan["axes_nm"]["x"],
        "mesh_axis_y_values": plan["axes_nm"]["y"],
        "mesh_axis_z_values": plan["axes_nm"]["z"],
    }
    assert validate_frozen_d15_axes(payload)["y"] == tuple(plan["axes_nm"]["y"])
    wrong = dict(payload, mesh_axis_y_values=(0.0, 5.0, 10.0, 15.0, 20.0,
                                               25.0, 30.0, 35.0, 40.0, 42.5, 50.0))
    with pytest.raises(ValueError, match="y coordinates differ"):
        validate_frozen_d15_axes(wrong)
    wrong_hash = dict(payload, mesh_plan_sha256="0" * 64)
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        validate_frozen_d15_axes(wrong_hash)


@pytest.mark.parametrize("case", ("B", "Y3", "Y3_2"))
def test_d15_manifest_roundtrips_through_real_worker_payload_gate(tmp_path, case):
    specification = load_and_resolve(D15_INPUTS[case])
    run_directory = (tmp_path / "run").resolve()
    run_directory.mkdir()
    specification = replace(specification, expected_output_parent=run_directory.parent)
    execution = build_execution_plan(
        specification,
        run_directory,
        source_sha=SOURCE_SHA,
        python_executable=sys.executable,
        mpiexec_command="/usr/bin/mpiexec",
    )
    manifest, resolved_sha = _write_bootstrap(
        specification,
        run_directory,
        source_sha=SOURCE_SHA,
        adapter_identity=execution.adapter_identity,
        start_time="2026-10-21T00:00:00Z",
    )
    profile = specification.derived["native_capacity_profile"]
    assert profile["identity"] == f"task40para_phi90_13p5_D15_{case}_p6_direct_v1"
    plan = D15_AXIS_PLANS[case]
    directional = profile["component_options"]["directional_mesh_comparison"]
    assert tuple(directional["axis_cell_counts"]) == tuple(plan["axis_cell_counts"])
    assert directional["expected_axis_sha256_le_f64"] == plan["axis_sha256_le_f64"]
    normalized = specification.as_jsonable()
    assert tuple(normalized["discretization"]["mesh_axis_cell_counts"]) == tuple(
        plan["axis_cell_counts"]
    )
    if case == "Y3":
        assert tuple(directional["segment_cell_counts"]["y"]) == (3, 4, 3)
        assert tuple(normalized["discretization"]["mesh_axis_y_values"]) == (
            0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0
        )
        assert directional["expected_material_tag_counts"] == {
            "1": 268, "2": 60, "3": 32
        }
    if case == "Y3_2":
        assert tuple(directional["segment_cell_counts"]["y"]) == (2, 6, 2)
        assert tuple(normalized["discretization"]["mesh_axis_y_values"]) == tuple(
            D15_AXIS_PLANS["Y3_2"]["axes_nm"]["y"]
        )
        assert directional["expected_material_tag_counts"] == {
            "1": 252, "2": 60, "3": 48
        }
    assert manifest["native_capacity_profile_identity"] == profile["identity"]
    assert manifest["component_options"] == thaw(profile["component_options"])
    assert manifest["native_capacity_contract"]["direct_route"] == thaw(
        profile["campaign_authorization"]["direct_route"]
    )
    resolved, errors = _load_and_validate_worker_payload(
        resolved_config=run_directory / "resolved_config.json",
        manifest=run_directory / "run_manifest.json",
        expected_input_sha256=specification.input_sha256,
        expected_physical_model_sha256=specification.physical_model_sha256,
        expected_source_sha=SOURCE_SHA,
        expected_mpi_size=1,
        expected_method="full3d_direct",
        expected_adapter=execution.adapter_identity,
        expected_output_directory=run_directory,
        expected_resolved_config_sha256=resolved_sha,
        actual_mpi_size=1,
    )
    assert errors == []
    assert resolved["derived"]["native_capacity_profile"] == thaw(profile)


def test_d15_b_manifest_route_drift_is_rejected_by_worker(tmp_path):
    specification = load_and_resolve(D15_INPUTS["B"])
    run_directory = (tmp_path / "run").resolve()
    run_directory.mkdir()
    specification = replace(specification, expected_output_parent=run_directory.parent)
    execution = build_execution_plan(
        specification,
        run_directory,
        source_sha=SOURCE_SHA,
        python_executable=sys.executable,
        mpiexec_command="/usr/bin/mpiexec",
    )
    manifest, resolved_sha = _write_bootstrap(
        specification,
        run_directory,
        source_sha=SOURCE_SHA,
        adapter_identity=execution.adapter_identity,
        start_time="2026-10-21T00:00:00Z",
    )
    manifest["native_capacity_contract"]["direct_route"]["surface_quadrature"] = (
        "silently_changed"
    )
    (run_directory / "run_manifest.json").write_text(json.dumps(manifest))
    _resolved, errors = _load_and_validate_worker_payload(
        resolved_config=run_directory / "resolved_config.json",
        manifest=run_directory / "run_manifest.json",
        expected_input_sha256=specification.input_sha256,
        expected_physical_model_sha256=specification.physical_model_sha256,
        expected_source_sha=SOURCE_SHA,
        expected_mpi_size=1,
        expected_method="full3d_direct",
        expected_adapter=execution.adapter_identity,
        expected_output_directory=run_directory,
        expected_resolved_config_sha256=resolved_sha,
        actual_mpi_size=1,
    )
    assert any("route contract mismatch" in error for error in errors)
