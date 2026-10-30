"""Focused metadata/worker contract for the D07C G3 M8/N96 candidate."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

from src.geometry.task40_phi90_d07c_axis_plan import d07c_axis_plan
from src.io.execution_plan import build_execution_plan
from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.io.native_capacity_profile import (
    TASK40_PHI90_D07C_PROFILE_BY_CASE,
    native_profile_facts,
)
from src.io.resolved_config import resolved_config_sha256
from src.runners.p6_condensed_direct import _direct_run_contract
from src.runners.task038_input_worker import _load_and_validate_worker_payload
from src.runners.task038_launcher import _write_bootstrap
from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory

ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = ROOT / "input/task40para_phi90_mesh_modes_direct"
N64_INPUT = INPUT_DIR / "d07c_g3_m8_nminus64_to1_p6_direct.dat"
N96_INPUT = INPUT_DIR / "d07c_g3_m8_nminus96_to1_p6_direct.dat"
N64_SHA = "e4cef2ecadaab2563a46592dfe31df04aa47bc113f3a69e1ac0ecd70cebf2ef0"
N96_SHA = "f044d5183d9f106bfff3e9d312e6aef9e7a205ab42b961655c4415a6afab949d"
SOURCE_SHA = "d07c-n96-focused-contract-test"


def _resolved_inventory(path: Path):
    specification = load_and_resolve(path)
    resolved = specification.as_jsonable()
    profile = resolved["solver"]["native_capacity_profile"]
    route = _direct_run_contract(profile)
    cfg = simulation_config_3d_from_normalized(resolved)
    cfg.stage4_dtn_order_policy = "explicit_signed_rectangle"
    cfg.task40_dtn_signed_rectangle_bounds_mn = tuple(
        int(value) for value in route["signed_rectangle_bounds_mn"]
    )
    cfg.stage4_dtn_quadrature_degree = int(route["surface_quadrature_degree"])
    cfg.task40_port_boundary_amplitude_scale_policy = route[
        "mode_basis_scale_policy"
    ]
    modes, rows, digest = build_dynamic_mode_inventory(cfg)
    keys = [(mode.side, int(mode.m), int(mode.n), mode.polarization) for mode in modes]
    return specification, resolved, profile, route, modes, rows, digest, keys


def test_g3_m8_n96_real_loader_profile_and_production_inventory():
    spec, resolved, profile, route, modes, rows, digest, keys = _resolved_inventory(
        N96_INPUT
    )
    assert profile == "task40para_phi90_0p7_D07C_G3_M8_N96_p6_direct_v1"
    assert resolved["run_id"] == profile
    assert TASK40_PHI90_D07C_PROFILE_BY_CASE["G3_M8_N96"] == profile
    assert resolved_config_sha256(spec)
    assert route["signed_rectangle_bounds_mn"] == [-8, 8, -96, 1]
    assert route["active_sha256"] == route["expected_mode_sha256"] == N96_SHA
    assert route["surface_quadrature_degree"] == 81
    assert route["surface_quadrature_reference_degree"] == 161
    assert route["full_dtn_status"] == "FULL_DTN_NOT_VERIFIED"
    assert len(modes) == len(rows) == route["active_count"] == 6664
    assert digest == N96_SHA
    assert sum(bool(mode.propagating) for mode in modes) == 6536
    assert sum(float(mode.power_per_unit_amplitude) > 0.0 for mode in modes) == 6602
    assert keys[0] == ("top", -8, -96, "s")
    assert keys[-1] == ("bottom", 8, 1, "p")
    assert set(keys) == {
        (side, m, n, pol)
        for side in ("top", "bottom")
        for m in range(-8, 9)
        for n in range(-96, 2)
        for pol in ("s", "p")
    }
    selection = native_profile_facts(profile)["component_options"]["mode_selection"]
    assert selection["parent_signed_bounds_mn"] == [-8, 8, -96, 1]
    assert selection["expected_mode_count"] == 6664
    assert selection["expected_mode_sha256"] == N96_SHA
    assert selection["expected_active_propagating_count"] == 6536
    assert selection["expected_active_power_carrying_count"] == 6602
    assert selection["comparison_reference_signed_bounds_mn"] == [-8, 8, -64, 1]
    assert selection["comparison_reference_mode_sha256"] == N64_SHA
    assert selection["same_mesh_modal_reference_case"] == "G3_M8_N64"
    assert selection["same_mesh_modal_reference_mode_sha256"] == N64_SHA
    assert native_profile_facts(profile)["component_options"][
        "directional_mesh_comparison"
    ]["changed_axes"] == []
    assert selection["added_mode_count_vs_n64"] == 2176
    assert selection["omitted_auto_propagating_mode_count"] == 64120 - 6536
    assert selection["omitted_from_same_mesh_M8_Nminus143_to1_mode_count"] == 9860 - 6664
    assert selection["omitted_from_same_mesh_M8_Nminus143_to1_propagating_count"] == 9664 - 6536
    assert selection["omitted_from_same_mesh_M8_Nminus143_to1_power_carrying_count"] == 9764 - 6602
    facts = native_profile_facts(profile)
    assert facts["component_options"]["volume_quadrature"] == {
        "degree": 15,
        "rule": "default",
        "authority": "live_FFCx_Basix_p6_volume_form_degree_metadata",
    }
    assert facts["resources"]["resource_stop_policy"] == "host_available_floor_v1"
    assert facts["resources"]["minimum_available_bytes"] == 64 * 1024**3
    assert facts["resources"]["rss_hard_limit_bytes"] is None
    assert facts["resources"]["concurrent_neighbor_authorized"] is False


def test_g3_m8_n64_inventory_is_ordered_subset_of_n96_only_new_n_band():
    _n64_spec, _n64_resolved, _n64_profile, _n64_route, old_modes, old_rows, old_sha, old_keys = (
        _resolved_inventory(N64_INPUT)
    )
    _n96_spec, _n96_resolved, _n96_profile, _n96_route, new_modes, new_rows, new_sha, new_keys = (
        _resolved_inventory(N96_INPUT)
    )
    assert len(old_modes) == len(old_rows) == 4488
    assert old_sha == N64_SHA
    assert len(new_modes) == len(new_rows) == 6664
    assert new_sha == N96_SHA
    positions = {key: index for index, key in enumerate(new_keys)}
    assert set(old_keys) <= set(positions)
    assert [positions[key] for key in old_keys] == sorted(positions[key] for key in old_keys)
    added = set(new_keys) - set(old_keys)
    assert len(added) == 2176
    assert added == {
        (side, m, n, pol)
        for side in ("top", "bottom")
        for m in range(-8, 9)
        for n in range(-96, -64)
        for pol in ("s", "p")
    }


def test_g3_m8_n96_profile_rejects_unknown_identity_and_worker_contract_drift(
    tmp_path,
):
    spec, _resolved, profile, _route, _modes, _rows, _digest, _keys = _resolved_inventory(
        N96_INPUT
    )
    with pytest.raises(KeyError):
        native_profile_facts(profile + "_typo")

    run_dir = (tmp_path / "d07c-g3-n96-run").resolve()
    run_dir.mkdir()
    spec = replace(spec, expected_output_parent=run_dir.parent)
    plan = build_execution_plan(
        spec,
        run_dir,
        source_sha=SOURCE_SHA,
        python_executable=sys.executable,
        mpiexec_command="/usr/bin/mpiexec",
    )
    manifest, resolved_sha = _write_bootstrap(
        spec,
        run_dir,
        source_sha=SOURCE_SHA,
        adapter_identity=plan.adapter_identity,
        start_time="2026-10-31T00:00:00Z",
    )
    loaded, errors = _load_and_validate_worker_payload(
        resolved_config=run_dir / "resolved_config.json",
        manifest=run_dir / "run_manifest.json",
        expected_input_sha256=spec.input_sha256,
        expected_physical_model_sha256=spec.physical_model_sha256,
        expected_source_sha=SOURCE_SHA,
        expected_mpi_size=1,
        expected_method="full3d_direct",
        expected_adapter=plan.adapter_identity,
        expected_output_directory=run_dir,
        expected_resolved_config_sha256=resolved_sha,
        actual_mpi_size=1,
    )
    assert errors == []
    assert loaded["derived"]["native_capacity_profile"]["identity"] == profile
    assert manifest["native_capacity_contract"]["direct_route"][
        "active_signed_bounds_mn"
    ] == [-8, 8, -96, 1]
    assert manifest["native_capacity_contract"]["direct_route"][
        "active_mode_count"
    ] == 6664
    assert d07c_axis_plan("G3")["expected_global_cell_count"] == 4800
