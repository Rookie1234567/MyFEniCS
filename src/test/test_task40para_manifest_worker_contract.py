"""Task40 direct manifests must survive the real worker payload gate."""

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from src.io.execution_plan import build_execution_plan
from src.io.input_validation import load_and_resolve
from src.io.run_specification import thaw
from src.runners.task038_input_worker import _load_and_validate_worker_payload
from src.runners.task038_launcher import _write_bootstrap

REPO = Path(__file__).resolve().parents[2]
INPUT = REPO / "input/task40para_phi90_mesh_modes_direct/d13_b_r13_p6_direct.dat"
D5_INPUTS = {
    case: REPO / f"input/task40para_phi90_mesh_modes_direct/d5_{case.lower()}_r5_p6_direct.dat"
    for case in ("B", "X", "Y", "Z")
}
D5C_INPUTS = {
    case: REPO / f"input/task40para_phi90_mesh_modes_direct/d5c_{case.lower()}_r5_p6_direct.dat"
    for case in (
        "B", "X1", "X2", "X3", "Y1", "Y2", "Y3", "Y4", "Y5",
        "Y6", "Y7", "Y8", "Z1", "Z2", "Z3",
    )
}
Y3_INPUT = REPO / "input/task40para_phi90_mesh_modes_direct/d13_y3_r13_p6_direct.dat"
Y3_K_INPUTS = {
    k: REPO
    / f"input/task40para_phi90_mesh_modes_direct/d15_y3_k{k}_r13_p6_direct.dat"
    for k in range(1, 5)
}
Z2_INPUT = REPO / "input/task40para_phi90_mesh_modes_direct/d13_z2_from_y2_r13_p6_direct.dat"
H15_INPUTS = {
    case: REPO / f"input/task40para_phi90_mesh_modes_direct/h15_{case.lower()}_r13_p6_direct.dat"
    for case in ("B", "X", "Y", "Z", "YZ480")
}
SOURCE_SHA = "b" * 40


def _task40_manifest(tmp_path, input_path=INPUT):
    specification = load_and_resolve(input_path)
    run_directory = (tmp_path / "run").resolve()
    run_directory.mkdir()
    specification = replace(
        specification,
        expected_output_parent=run_directory.parent,
    )
    plan = build_execution_plan(
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
        adapter_identity=plan.adapter_identity,
        start_time="2026-10-16T00:00:00Z",
    )
    return specification, run_directory, manifest, resolved_sha, plan


def _worker_validate(specification, run_directory, resolved_sha, plan):
    return _load_and_validate_worker_payload(
        resolved_config=run_directory / "resolved_config.json",
        manifest=run_directory / "run_manifest.json",
        expected_input_sha256=specification.input_sha256,
        expected_physical_model_sha256=specification.physical_model_sha256,
        expected_source_sha=SOURCE_SHA,
        expected_mpi_size=1,
        expected_method="full3d_direct",
        expected_adapter=plan.adapter_identity,
        expected_output_directory=run_directory,
        expected_resolved_config_sha256=resolved_sha,
        actual_mpi_size=1,
    )


def test_task40_manifest_roundtrips_through_worker_payload_gate(tmp_path):
    specification, run_directory, manifest, resolved_sha, plan = _task40_manifest(
        tmp_path
    )
    profile = specification.derived["native_capacity_profile"]
    contract = manifest["native_capacity_contract"]

    assert manifest["native_capacity_profile_identity"] == profile["identity"]
    assert manifest["native_capacity_profile"] == thaw(profile)
    assert manifest["component_options"] == thaw(profile["component_options"])
    assert contract["resource_stop_policy"] == "host_available_floor_v1"
    assert contract["rss_hard_limit_bytes"] is None
    assert contract["minimum_available_bytes"] == 64 * 1024**3
    assert contract["direct_route"] == thaw(
        profile["campaign_authorization"]["direct_route"]
    )

    resolved, errors = _worker_validate(
        specification, run_directory, resolved_sha, plan
    )
    assert errors == []
    assert resolved is not None
    assert resolved["derived"]["native_capacity_profile"] == thaw(profile)


def test_task40_y3_manifest_roundtrips_through_worker_payload_gate(tmp_path):
    specification, run_directory, manifest, resolved_sha, plan = _task40_manifest(
        tmp_path, Y3_INPUT
    )
    profile = specification.derived["native_capacity_profile"]
    directional = profile["component_options"]["directional_mesh_comparison"]
    assert profile["identity"] == "task40para_phi90_13p5_D13_Y3_p6_direct_v1"
    assert directional["case"] == "Y3"
    assert directional["parent_case"] == "Y2"
    assert directional["changed_axis"] == "y"
    assert tuple(directional["axis_cell_counts"]) == (6, 48, 14)
    assert manifest["native_capacity_profile_identity"] == profile["identity"]
    assert manifest["native_capacity_contract"]["direct_route"] == thaw(
        profile["campaign_authorization"]["direct_route"]
    )

    resolved, errors = _worker_validate(
        specification, run_directory, resolved_sha, plan
    )
    assert errors == []
    assert resolved is not None
    assert resolved["derived"]["native_capacity_profile"] == thaw(profile)


@pytest.mark.parametrize(("k", "active_count"), ((1, 36), (2, 100), (3, 196), (4, 324)))
def test_task40_d15_y3_k_manifest_roundtrips_through_worker_payload_gate(
    tmp_path, k, active_count
):
    specification, run_directory, manifest, resolved_sha, plan = _task40_manifest(
        tmp_path, Y3_K_INPUTS[k]
    )
    profile = specification.derived["native_capacity_profile"]
    options = profile["component_options"]
    mode = options["mode_selection"]
    route = profile["campaign_authorization"]["direct_route"]

    assert profile["identity"] == (
        f"task40para_phi90_13p5_D15_Y3_K{k}_p6_direct_v1"
    )
    assert options["directional_mesh_comparison"]["case"] == "Y3"
    assert tuple(options["expected_axis_cell_counts"]) == (6, 10, 6)
    assert mode["parent_inventory_scope"] == "R13_finite_rectangle_including_evanescent"
    assert mode["expected_mode_count"] == 612
    assert mode["expected_active_mode_count"] == active_count
    assert tuple(mode["active_rectangle_max_abs_m_n"]) == (k, k)
    assert mode["quadrature_reference_label"] == "R13_full_612_parent"
    assert options["surface_quadrature"]["degree"] == 28
    assert options["volume_quadrature"]["degree"] == 15
    assert route["parent_mode_count"] == 612
    assert route["active_mode_count"] == active_count
    assert tuple(route["active_rectangle_max_abs_m_n"]) == (k, k)
    assert manifest["native_capacity_profile_identity"] == profile["identity"]
    assert manifest["native_capacity_contract"]["direct_route"] == thaw(route)

    resolved, errors = _worker_validate(
        specification, run_directory, resolved_sha, plan
    )
    assert errors == []
    assert resolved is not None
    assert resolved["derived"]["native_capacity_profile"] == thaw(profile)


@pytest.mark.parametrize("case", tuple(D5C_INPUTS))
def test_task40_d5c_manifest_roundtrips_through_worker_payload_gate(tmp_path, case):
    specification, run_directory, manifest, resolved_sha, plan = _task40_manifest(
        tmp_path, D5C_INPUTS[case]
    )
    profile = specification.derived["native_capacity_profile"]
    options = profile["component_options"]
    route = profile["campaign_authorization"]["direct_route"]
    native_contract = manifest["native_capacity_contract"]

    assert profile["identity"] == (
        f"task40para_phi90_5_D5C_{case}_p6_direct_v1"
    )
    assert options["task_family"] == "task40_phi90_d5c_mesh_modes_direct"
    assert options["coarse_study_lineage"]["baseline_case"] == "B"
    assert options["coarse_study_lineage"]["historical_D5_family_modified"] is False
    if case in {"Y6", "Y7", "Y8"}:
        assert options["coarse_study_lineage"]["comparison_reference_case"] == "Y5"
        assert options["coarse_study_lineage"]["sequence_decision_rule"][
            "pre_Y8_pairs"
        ] == ("Y5->Y6", "Y5->Y7", "Y6<->Y7")
    assert options["directional_mesh_comparison"]["display_name"] == f"D5C-{case}"
    assert options["mode_selection"]["expected_mode_count"] == 3772
    assert options["mode_selection"]["expected_mode_sha256"] == (
        "752333bbc4082b9d7f9f1c935433eeb8e4c8b5e44a74a27310944b6b8aa531bc"
    )
    assert options["mode_selection"]["boundary_amplitude_scale_policy"] == (
        "boundary_magnitude_scaled_r5_v1"
    )
    assert options["surface_quadrature"]["degree"] == 39
    assert options["volume_quadrature"]["degree"] == 15
    assert route["d5c_case"] == case
    assert route["parent_mode_count"] == 3772
    assert manifest["native_capacity_profile_identity"] == profile["identity"]
    assert native_contract["direct_route"] == thaw(route)
    assert native_contract["resource_stop_policy"] == "host_available_floor_v1"
    assert native_contract["rss_hard_limit_bytes"] is None
    assert native_contract["minimum_available_bytes"] == 64 * 1024**3
    assert native_contract["swap_policy"] == "observe_only"
    assert profile["resources"]["stop_on_global_swap"] is False

    resolved, errors = _worker_validate(
        specification, run_directory, resolved_sha, plan
    )
    assert errors == []
    assert resolved is not None
    assert resolved["derived"]["native_capacity_profile"] == thaw(profile)


def test_task40_z2_manifest_roundtrips_through_worker_payload_gate(tmp_path):
    specification, run_directory, manifest, resolved_sha, plan = _task40_manifest(
        tmp_path, Z2_INPUT
    )
    profile = specification.derived["native_capacity_profile"]
    directional = profile["component_options"]["directional_mesh_comparison"]
    from src.geometry.task40_phi90_d13_axis_plan import d13_axis_plan

    y2_axis_hashes = d13_axis_plan("Y2")["actual_axis_sha256_le_f64"]
    assert profile["identity"] == (
        "task40para_phi90_13p5_D13_Z2_from_Y2_p6_direct_v1"
    )
    assert directional["case"] == "Z2"
    assert directional["parent_case"] == "Y2"
    assert directional["axis_comparison_parent"] == "Y2"
    assert directional["changed_axis"] == "z"
    assert tuple(directional["axis_cell_counts"]) == (6, 24, 28)
    assert profile["component_options"]["expected_global_cell_count"] == 4032
    assert directional["expected_material_tag_counts"] == {
        "1": 3360, "2": 288, "3": 384
    }
    assert directional["base_axis_sha256_le_f64"] == y2_axis_hashes
    assert profile["component_options"]["surface_quadrature"]["degree"] == 28
    assert profile["component_options"]["volume_quadrature"]["degree"] == 15
    assert manifest["native_capacity_profile_identity"] == profile["identity"]
    assert manifest["native_capacity_contract"]["direct_route"] == thaw(
        profile["campaign_authorization"]["direct_route"]
    )

    resolved, errors = _worker_validate(
        specification, run_directory, resolved_sha, plan
    )
    assert errors == []
    assert resolved is not None
    assert resolved["derived"]["native_capacity_profile"] == thaw(profile)


@pytest.mark.parametrize("case", ("B", "X", "Y", "Z"))
def test_task40_d5_r5_manifest_roundtrips_through_worker_payload_gate(tmp_path, case):
    specification, run_directory, manifest, resolved_sha, plan = _task40_manifest(
        tmp_path, D5_INPUTS[case]
    )
    profile = specification.derived["native_capacity_profile"]
    options = profile["component_options"]
    route = profile["campaign_authorization"]["direct_route"]
    assert profile["identity"] == f"task40para_phi90_5_D5_{case}_p6_direct_v1"
    expected_tags = (
        {"1": 5188, "2": 920, "3": 792}
        if case == "B"
        else {"1": 10376, "2": 1840, "3": 1584}
    )
    assert options["directional_mesh_comparison"][
        "expected_material_tag_counts"
    ] == expected_tags
    assert options["mode_selection"]["expected_mode_count"] == 3772
    assert options["mode_selection"]["expected_mode_sha256"] == (
        "752333bbc4082b9d7f9f1c935433eeb8e4c8b5e44a74a27310944b6b8aa531bc"
    )
    assert options["mode_selection"]["boundary_amplitude_scale_policy"] == (
        "boundary_magnitude_scaled_r5_v1"
    )
    assert options["surface_quadrature"]["degree"] == 39
    assert route["parent_mode_count"] == 3772
    assert route["parent_mode_sha256"] == options["mode_selection"][
        "expected_mode_sha256"
    ]
    assert route["port_boundary_amplitude_scale_policy"] == (
        "boundary_magnitude_scaled_r5_v1"
    )

    resolved, errors = _worker_validate(
        specification, run_directory, resolved_sha, plan
    )
    assert errors == []
    assert resolved is not None
    assert resolved["derived"]["native_capacity_profile"] == thaw(profile)
    assert manifest["native_capacity_contract"]["direct_route"] == thaw(route)


@pytest.mark.parametrize("case", ("B", "X", "Y", "Z", "YZ480"))
def test_task40_h15_manifests_roundtrip_through_worker_payload_gate(tmp_path, case):
    specification, run_directory, manifest, resolved_sha, plan = _task40_manifest(
        tmp_path, H15_INPUTS[case]
    )
    profile = specification.derived["native_capacity_profile"]
    directional = profile["component_options"]["directional_mesh_comparison"]
    assert profile["identity"] == f"task40para_phi90_13p5_H15_{case}_p6_direct_v1"
    assert directional["case"] == case
    assert directional["mesh_plan_family"] == "task40_phi90_h15"
    if case == "YZ480":
        assert directional["parent_case"] == "Y"
        assert tuple(directional["changed_axes"]) == ("y", "z")
        assert tuple(directional["axis_cell_counts"]) == (6, 10, 8)
        assert directional["expected_material_tag_counts"] == {
            "1": 348, "2": 60, "3": 72
        }
    assert tuple(directional["axis_cell_counts"]) == tuple(
        profile["component_options"]["expected_axis_cell_counts"]
    )
    assert profile["component_options"]["mesh_target_nm"] == 15.0
    assert profile["component_options"]["surface_quadrature"]["degree"] == 28
    assert manifest["native_capacity_profile_identity"] == profile["identity"]
    assert manifest["component_options"] == thaw(profile["component_options"])
    assert manifest["native_capacity_contract"]["direct_route"] == thaw(
        profile["campaign_authorization"]["direct_route"]
    )

    resolved, errors = _worker_validate(
        specification, run_directory, resolved_sha, plan
    )
    assert errors == []
    assert resolved is not None
    assert resolved["derived"]["native_capacity_profile"] == thaw(profile)


@pytest.mark.parametrize(
    ("contract_path", "replacement", "error_fragment"),
    [
        (("resource_stop_policy",), "legacy", "resource stop policy mismatch"),
        (("minimum_available_bytes",), 1, "minimum available-memory floor mismatch"),
        (("direct_route", "surface_quadrature"), {}, "route contract mismatch"),
    ],
)
def test_task40_worker_rejects_manifest_contract_drift(
    tmp_path, contract_path, replacement, error_fragment
):
    specification, run_directory, manifest, resolved_sha, plan = _task40_manifest(
        tmp_path
    )
    target = manifest["native_capacity_contract"]
    for key in contract_path[:-1]:
        target = target[key]
    target[contract_path[-1]] = replacement
    (run_directory / "run_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    _resolved, errors = _worker_validate(
        specification, run_directory, resolved_sha, plan
    )
    assert any(error_fragment in error for error in errors)
