from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

import src.runners.v7_anisotropic_mesh_evidence as v7_mesh_evidence
from src.geometry.mesh_builder_3d import stage4_axis_plan
from src.geometry.v7_d_aniso_n0_p6_axis_plan import (
    D_AXIS_COUNTS,
    D_AXIS_PLAN_ID,
    D_X_SEGMENT_COUNTS,
    D_Y_SEGMENT_COUNTS,
    D_Z_PROFILE,
    D_Z_SEGMENT_COUNTS,
    d_axis_plan,
    validate_frozen_d_axes,
)
from src.io.execution_plan import build_execution_plan
from src.io.input_loader import InputError, load_dat_input
from src.io.input_validation import (
    _plain,
    _validate_sections,
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.io.native_capacity_profile import (
    V7_ANISO_N0_P6_DIRECT_PROFILE,
    V7_D_ANISO_N0_P6_DIRECT_PROFILE,
    native_profile_facts,
    validate_native_case,
)
from src.runners.p6_condensed_direct import (
    _direct_output_policy,
    _direct_run_contract,
    _validate_resolved_profile,
)

REPO = Path(__file__).resolve().parents[2]
D_INPUT = REPO / "input/task39extra_para_workstation_capacity/v7_0p7nm_si_p6_direct_candidate_d.dat"
BASE_INPUT = REPO / "input/task39extra_para_workstation_capacity/v7_0p7nm_si_p6_direct_n0_full.dat"


def test_d_axis_plan_has_the_authorized_piecewise_counts_and_stable_hashes():
    plan = d_axis_plan()
    axes = plan["axes_nm"]

    assert plan["plan_id"] == D_AXIS_PLAN_ID
    assert plan["axis_cell_counts"] == list(D_AXIS_COUNTS) == [200, 2, 118]
    assert plan["segment_cell_counts"] == {
        "x": list(D_X_SEGMENT_COUNTS),
        "y": list(D_Y_SEGMENT_COUNTS),
        "z": list(D_Z_SEGMENT_COUNTS),
    }
    assert plan["segment_cell_counts"]["y"] == list(D_Y_SEGMENT_COUNTS)
    assert plan["segment_cell_counts"]["z"] == list(D_Z_SEGMENT_COUNTS)
    assert {name: len(values) - 1 for name, values in axes.items()} == {
        "x": 200,
        "y": 2,
        "z": 118,
    }
    assert np.array_equal(np.diff(axes["x"])[0:66], np.full(66, 0.25))
    assert np.allclose(np.diff(axes["x"])[66:134], 17.0 / 68.0, rtol=0, atol=1e-14)
    assert np.array_equal(np.diff(axes["x"])[134:200], np.full(66, 0.25))
    assert np.allclose(np.diff(axes["z"])[0:9], 10.0 / 9.0, rtol=0, atol=1e-14)
    assert np.allclose(np.diff(axes["z"])[9:109], 1.2, rtol=0, atol=5e-14)
    assert np.allclose(np.diff(axes["z"])[109:118], 10.0 / 9.0, rtol=0, atol=5e-14)


def test_d_axis_validator_rejects_mutated_identity_count_and_coordinate():
    plan = d_axis_plan()
    axes = plan["axes_nm"]
    config = {
        "mesh_plan_id": plan["plan_id"],
        "mesh_plan_sha256": plan["plan_sha256"],
        "mesh_axis_cell_counts": list(D_AXIS_COUNTS),
        "mesh_axis_x_values": list(axes["x"]),
        "mesh_axis_y_values": list(axes["y"]),
        "mesh_axis_z_values": list(axes["z"]),
        "mesh_axis_z_profile": D_Z_PROFILE,
    }
    assert validate_frozen_d_axes(config) == axes

    for change in (
        {"mesh_plan_sha256": "0" * 64},
        {"mesh_axis_cell_counts": [200, 2, 117]},
        {"mesh_axis_z_profile": "wrong-profile"},
    ):
        invalid = {**config, **change}
        with pytest.raises(ValueError):
            validate_frozen_d_axes(invalid)
    changed_x = list(config["mesh_axis_x_values"])
    changed_x[10] += 1.0e-9
    with pytest.raises(ValueError, match="x_values differ"):
        validate_frozen_d_axes({**config, "mesh_axis_x_values": changed_x})


def test_d_input_resolves_to_separate_n0_fullsolve_direct_contract(tmp_path):
    resolved = load_and_resolve(D_INPUT).as_jsonable()
    identity = resolved["derived"]["native_capacity_profile"]["identity"]
    facts = resolved["derived"]["native_capacity_profile"]
    assert resolved["run_id"] == "v7_interleave_0p7nm_aniso_p6_direct_d_cross_changed_q160_n0_full"
    assert identity == V7_D_ANISO_N0_P6_DIRECT_PROFILE
    assert resolved["derived"]["mesh_cells"] == [200, 2, 118]
    assert resolved["method"]["kind"] == "full3d_direct"
    assert facts["resources"]["rss_hard_limit_bytes"] == 1_800_000_000_000
    selection = facts["component_options"]["dtn_mode_selection"]
    assert selection["parent_mode_count"] == 32_060
    assert selection["parent_mode_sha256"] == (
        "7f023c73d7b63379955642dd062e47ba7004f3cdf0accf42684286c4af71dbfb"
    )
    assert selection["active_mode_count"] == 572
    assert selection["expected_active_mode_sha256"] == (
        "946e0d294b99cb7f44817c3649029942ac325f345eb1770caa566183d2b04f3b"
    )
    assert facts["component_options"]["surface_quadrature"]["degree"] == 160
    assert facts["component_options"]["volume_quadrature"]["degree"] == 15
    assert facts["component_options"]["grid_comparison_scope"] == (
        "CROSS_CHANGED_GRID_DIAGNOSTIC"
    )
    assert "rows" not in facts["condensed_route"]
    assert facts["backend"]["p4_factor"] == "NOT_BUILT"
    assert facts["backend"]["outer_ksp"] == "NOT_BUILT"

    cfg = simulation_config_3d_from_normalized(resolved)
    axis_plan = stage4_axis_plan(cfg, comm_size=1)
    expected = d_axis_plan()["axes_nm"]
    assert np.array_equal(axis_plan.x_values, expected["x"])
    assert np.array_equal(axis_plan.y_values, expected["y"])
    assert np.array_equal(axis_plan.z_values, expected["z"])
    assert axis_plan.mesh_cells_resolved == D_AXIS_COUNTS

    route = _direct_run_contract(identity)
    assert route["family"] == "v7_aniso_n0"
    assert route["diagnostic_scope"] == "CROSS_CHANGED_GRID_DIAGNOSTIC"
    assert route["expected_full_p6_rows"] is None
    assert route["expected_active_rows"] is None
    assert route["require_mumps_icntl23_zero"] is True
    assert route["active_count"] == 572
    assert route["parent_count"] == 32_060
    assert route["full_dtn_status"] == "FULL_DTN_NOT_VERIFIED"
    assert _direct_output_policy(route)["active_port_outputs_only"] is True
    assert _validate_resolved_profile(resolved)["identity"] == identity

    execution = build_execution_plan(
        load_and_resolve(D_INPUT),
        tmp_path / "candidate-d-plan",
        source_sha="d" * 40,
        python_executable=REPO / ".venv/bin/python",
        mpiexec_command="/usr/bin/mpiexec",
    )
    assert execution.argv[:8] == (
        "/usr/bin/mpiexec",
        "-n",
        "1",
        "/usr/bin/numactl",
        "--interleave=0,1",
        "/usr/bin/taskset",
        "-c",
        "24",
    )
    assert execution.argv[8] == str(REPO / ".venv/bin/python")
    assert execution.argv.count(str(REPO / ".venv/bin/python")) == 1


def test_original_v7_profile_and_route_keep_their_original_axes_and_rows():
    resolved = load_and_resolve(BASE_INPUT).as_jsonable()
    facts = resolved["derived"]["native_capacity_profile"]
    assert facts["identity"] == V7_ANISO_N0_P6_DIRECT_PROFILE
    assert tuple(resolved["derived"]["mesh_cells"]) == (100, 2, 234)
    route = _direct_run_contract(V7_ANISO_N0_P6_DIRECT_PROFILE)
    assert route["expected_full_p6_rows"] == 32_061_312
    assert route["expected_active_rows"] == 9_280_800
    assert route["diagnostic_scope"] == "ORIGINAL_V7_100x2x234_GRID"


def test_d_case_validator_rejects_solver_or_mesh_policy_changes():
    loaded = load_dat_input(D_INPUT)
    config = _validate_sections(_plain(loaded.document))
    validate_native_case(config)

    for invalid in ("p4", "linear_solver", "mesh_axis"):
        candidate = deepcopy(config)
        if invalid == "p4":
            candidate["solver"]["preconditioner"] = "legacy_p4"
        elif invalid == "linear_solver":
            candidate["solver"]["linear_solver"] = "iterative"
        else:
            altered_z = list(candidate["discretization"]["mesh_axis_z_values"])
            altered_z[10] += 0.01
            candidate["discretization"]["mesh_axis_z_values"] = tuple(altered_z)
        with pytest.raises(InputError):
            validate_native_case(candidate)


def test_d_profile_facts_keep_hard_rss_and_actual_symbolic_readback_contract():
    facts = native_profile_facts(V7_D_ANISO_N0_P6_DIRECT_PROFILE)
    assert facts["resources"]["rss_hard_limit_bytes"] == 1_800_000_000_000
    assert facts["campaign_authorization"]["resource_policy"][
        "rss_hard_limit_bytes"
    ] == 1_800_000_000_000
    assert facts["backend"]["factor"] == "one_MUMPS_symbolic_then_numeric_on_the_same_matrix"
    assert facts["condensed_route"]["matrix_lifecycle"] == (
        "one_materialized_PETSc_AIJ_through_symbolic_numeric_solve"
    )
    assert facts["condensed_route"]["rows_source"].startswith("actual D mesh")


def test_d_mesh_evidence_exposes_axis_counts_expected_by_direct_runner(monkeypatch):
    plan = d_axis_plan()
    axes = plan["axes_nm"]
    cfg = type("Cfg", (), {
        "mesh_plan_id": plan["plan_id"],
        "mesh_plan_sha256": plan["plan_sha256"],
        "mesh_axis_cell_counts_requested": D_AXIS_COUNTS,
        "mesh_axis_x_values_requested": axes["x"],
        "mesh_axis_y_values_requested": axes["y"],
        "mesh_axis_z_values_requested": axes["z"],
        "mesh_axis_z_profile": D_Z_PROFILE,
    })()
    monkeypatch.setattr(
        v7_mesh_evidence,
        "actual_v7_anisotropic_mesh_evidence",
        lambda *_args, **_kwargs: {
            "status": "PASS",
            "actual_axis_cell_counts": list(D_AXIS_COUNTS),
        },
    )

    evidence = v7_mesh_evidence.actual_v7_candidate_d_mesh_evidence({}, cfg)

    assert evidence["actual_axis_cell_counts"] == [200, 2, 118]
    assert evidence["axis_cell_counts"] == [200, 2, 118]
