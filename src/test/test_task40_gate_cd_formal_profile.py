"""No-solve integration checks for the distinct Gate-CD M8N64 direct route."""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.gate_cd_formal_once import _expected_identity
from src.common.gate_cd_materials import GATE_CD_REGION_TAGS
from src.geometry.task40_gate_cd_mesh_plan import (
    GATE_CD_PROFILE_ID,
    GATE_CD_STATIC_PLAN,
)
from src.io.execution_plan import build_execution_plan
from src.io.input_validation import (
    InputError,
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.io.native_capacity_profile import (
    TASK40_GATE_CD_M8N64_P6_DIRECT_PROFILE,
    TASK40_GATE_CD_P6_DIRECT_PROFILE,
    _validate_task40_gate_cd_geometry_cache_readiness,
    native_profile_facts,
)
from src.io.run_specification import thaw
from src.runners.p6_condensed_direct import (
    _condensation_geometry_cache_kwargs,
    _direct_output_policy,
    _direct_run_contract,
    _reject_unqualified_gate_cd_full_solve,
    _task40_gate_cd_mesh_evidence,
    _validate_resolved_profile,
)
from src.runners.task038_input_worker import _load_and_validate_worker_payload
from src.runners.task038_launcher import _write_bootstrap

_ROOT = Path(__file__).resolve().parents[2]
_INPUT = _ROOT / "input/task40_gate_cd/gate_cd_0p7_mapped_m8n64_p6_direct.dat"
_EXPECTED_MODE_SHA = "6cf60807239dffc209b47336581e8bb50a5f4d986cba5bbdc06500f6271d3865"
_EXPECTED_LABEL_COUNTS = {
    "Air": 10_800,
    "Si_substrate": 1_200,
    "Si_Fin0": 400,
    "STI_SiO2": 800,
    "Si_poly": 2_800,
    "Gate_SiO2": 240,
    "SiN": 7_520,
    **{f"Fin{index}": 240 for index in range(1, 16)},
    "MDI": 240,
}
_EXPECTED_TAGS = {
    str(GATE_CD_REGION_TAGS[label]): count
    for label, count in _EXPECTED_LABEL_COUNTS.items()
}


def test_staged_profile_stays_qa_only_and_formal_dat_binds_distinct_identity():
    staged = native_profile_facts(TASK40_GATE_CD_P6_DIRECT_PROFILE)
    assert staged["execution_mode"] == "staged_mesh_and_material_qa"
    with pytest.raises(RuntimeError, match="staged profile permits"):
        _reject_unqualified_gate_cd_full_solve(staged)

    spec = load_and_resolve(_INPUT)
    resolved = spec.as_jsonable()
    facts = native_profile_facts(TASK40_GATE_CD_M8N64_P6_DIRECT_PROFILE)
    options = facts["component_options"]
    assert _validate_resolved_profile(resolved)["identity"] == (
        TASK40_GATE_CD_M8N64_P6_DIRECT_PROFILE
    )
    assert resolved["run_id"] == TASK40_GATE_CD_M8N64_P6_DIRECT_PROFILE
    assert resolved["solver"]["native_capacity_profile"] == (
        TASK40_GATE_CD_M8N64_P6_DIRECT_PROFILE
    )
    assert facts["execution_mode"] == "full_solve"
    assert facts["operator_scope"] == "task40_gate_cd_mapped_M8N64_finite_signed_rectangle"
    assert options["mesh_plan_id"] == GATE_CD_PROFILE_ID
    assert options["mesh_plan_sha256"] == GATE_CD_STATIC_PLAN.plan_sha256
    assert options["expected_global_cell_count"] == 27_600
    assert GATE_CD_STATIC_PLAN.tag_counts == _EXPECTED_LABEL_COUNTS
    assert options["directional_mesh_comparison"]["expected_material_tag_counts"] == _EXPECTED_TAGS
    assert options["route_readiness"]["launchable"] is True
    volume = options["volume_quadrature"]
    assert volume["production_ffcx_metadata"] == {"degree": 15, "rule": "default"}
    assert volume["production_ffcx_metadata_role"] == (
        "pre_override_automatic_ffcx_default_baseline_not_selected_operator"
    )
    assert volume["candidate_degrees"] == [15, 21, 27]
    assert volume["degree"] == 21 and volume["rule"] == "default"
    assert volume["status"] == (
        "SELECTED_Q21_BOUNDED_LOCAL_CANDIDATE_NOT_GLOBAL_ERROR_BOUND"
    )
    assert volume["selection_witness"]["sha256"] == (
        "3b012b12005aed7fc809beb349a511c27c8f5a28b74b054f130429986951735e"
    )
    cache_policy = options["mapped_geometry_cache_policy"]
    assert cache_policy["identity"] == "profile_selected_mapped_geometry_cache_v1"
    assert cache_policy["mapped_geometry_translation_invariant"] is True
    assert cache_policy["translation_normalized_candidate"] is True
    assert cache_policy["translation_equivalence_status"] == (
        "PASS_BOUNDED_TRANSLATION_EQUIVALENCE"
    )
    assert cache_policy["translation_equivalence_witness"]["max_relative_error"] <= 1e-11
    assert _condensation_geometry_cache_kwargs(facts) == {
        "geometry_identity_policy": "mapped_exact",
        "mapped_geometry_translation_invariant": True,
    }
    _validate_task40_gate_cd_geometry_cache_readiness(
        cache_policy,
        facts["condensed_route"],
        options["route_readiness"],
    )
    assert _reject_unqualified_gate_cd_full_solve(facts) is None


def test_condensation_geometry_cache_policy_is_explicit_and_fail_closed():
    assert _condensation_geometry_cache_kwargs(
        {"condensed_route": {"geometry_identity_policy": "raw_unrounded"}}
    ) == {
        "geometry_identity_policy": "raw_unrounded",
        "mapped_geometry_translation_invariant": False,
    }
    with pytest.raises(ValueError, match="requires mapped_exact"):
        _condensation_geometry_cache_kwargs(
            {
                "condensed_route": {
                    "geometry_identity_policy": "raw_unrounded",
                    "mapped_geometry_translation_invariant": True,
                }
            }
        )
    with pytest.raises(TypeError, match="must be boolean"):
        _condensation_geometry_cache_kwargs(
            {
                "condensed_route": {
                    "geometry_identity_policy": "mapped_exact",
                    "mapped_geometry_translation_invariant": "false",
                }
            }
        )

    candidate = {
        "identity": "profile_selected_mapped_geometry_cache_v1",
        "geometry_identity_policy": "mapped_exact",
        "mapped_geometry_translation_invariant": True,
        "translation_normalized_candidate": True,
        "translation_equivalence_status": "PASS_BOUNDED_TRANSLATION_EQUIVALENCE",
        "translation_equivalence_witness": {
            "sha256": "a" * 64,
            "scope": "active_local_tensor_schur_recovery_trace_rhs_same_storage",
            "max_relative_error": 1.0e-12,
            "reviewed_tolerance": 1.0e-11,
        },
        "cell_tensor_key_includes_material_tag": True,
        "local_recovery_key_includes_orientation": True,
    }
    route = {
        "geometry_identity_policy": "mapped_exact",
        "mapped_geometry_translation_invariant": True,
    }
    readiness = {
        "launchable": True,
        "completed_bounded_witnesses": [
            "actual_translation_normalized_cache_equivalence_witness"
        ],
    }
    _validate_task40_gate_cd_geometry_cache_readiness(candidate, route, readiness)
    assert _condensation_geometry_cache_kwargs(
        {"condensed_route": route}
    )["mapped_geometry_translation_invariant"] is True

    missing_witness = dict(candidate)
    missing_witness["translation_equivalence_witness"] = None
    with pytest.raises(ValueError, match="needs its bounded equivalence witness"):
        _validate_task40_gate_cd_geometry_cache_readiness(
            missing_witness, route, readiness
        )

    exact = dict(candidate)
    exact.update(
        mapped_geometry_translation_invariant=False,
        translation_equivalence_status="SELECTED_EXACT_PHYSICAL_COORDINATE_KEYS",
        translation_equivalence_witness=None,
    )
    exact_route = {
        "geometry_identity_policy": "mapped_exact",
        "mapped_geometry_translation_invariant": False,
    }
    exact_readiness = {
        "launchable": True,
        "completed_bounded_witnesses": [
            "selected_exact_physical_coordinate_cache_identity"
        ],
    }
    _validate_task40_gate_cd_geometry_cache_readiness(
        exact, exact_route, exact_readiness
    )


def test_real_loader_route_inventory_mesh_scope_and_output_are_gate_cd_labeled(monkeypatch):
    resolved = load_and_resolve(_INPUT).as_jsonable()
    assert resolved["run_id"] == TASK40_GATE_CD_M8N64_P6_DIRECT_PROFILE
    facts = native_profile_facts(TASK40_GATE_CD_M8N64_P6_DIRECT_PROFILE)
    identity = _expected_identity(
        load_and_resolve(_INPUT), TASK40_GATE_CD_M8N64_P6_DIRECT_PROFILE, "a" * 40
    )
    assert identity["direct_route_contract"] == facts["campaign_authorization"][
        "direct_route"
    ]
    route = _direct_run_contract(TASK40_GATE_CD_M8N64_P6_DIRECT_PROFILE)

    assert route["family"] == "task40_phi90"  # shared qualified algorithm branch
    assert route["comparison_family"] == "GATE_CD_M8N64_FINITE_SIGNED_RECTANGLE"
    assert route["task40_mesh_plan_family"] == "gate_cd"
    assert route["task40_mesh_case"] == "M8N64"
    assert route["d13_case"] is None
    assert route["signed_rectangle_bounds_mn"] == [-8, 8, -64, 1]
    assert route["expected_mode_count"] == 4_488
    assert route["expected_mode_sha256"] == _EXPECTED_MODE_SHA
    assert route["summary_prefix"] == "task40_gate_cd_m8n64_p6_direct_M8N64"
    assert route["surface_quadrature_degree"] == 81
    assert route["surface_quadrature_reference_degree"] == 161
    assert route["geometry_identity_policy"] == "mapped_exact"
    assert route["mapped_geometry_translation_invariant"] is True
    route_volume = route["volume_quadrature"]
    assert route_volume["degree"] == 21 and route_volume["rule"] == "default"
    assert route_volume["production_ffcx_metadata"] == {
        "degree": 15,
        "rule": "default",
    }
    assert route_volume["production_ffcx_metadata_role"] == (
        "pre_override_automatic_ffcx_default_baseline_not_selected_operator"
    )
    assert route_volume["candidate_degrees"] == [15, 21, 27]
    assert route_volume["selection_witness"]["sha256"] == (
        "3b012b12005aed7fc809beb349a511c27c8f5a28b74b054f130429986951735e"
    )
    assert route["mapped_geometry_cache_identity"] == (
        "profile_selected_mapped_geometry_cache_v1"
    )

    output = _direct_output_policy(route)
    assert output["active_port_outputs_only"] is False
    assert output["dtn_output_mode_count"] == 4_488
    assert output["active_fe_port_output_contract"]["active_signed_bounds_mn"] == (
        [-8, 8, -64, 1]
    )
    assert output["active_fe_port_output_contract"]["full_dtn_status"] == (
        "FULL_DTN_NOT_VERIFIED"
    )

    import src.geometry.task40_gate_cd_mesh_plan as mesh_plan

    expected_axes = facts["component_options"]["directional_mesh_comparison"][
        "expected_axis_sha256_le_f64"
    ]
    monkeypatch.setattr(
        mesh_plan,
        "gate_cd_live_mesh_facts",
        lambda *_args: {
            "status": "PASS",
            "scope": "TEST_FAKE_LIVE_MESH_FACTS_ONLY",
            "owned_cells": 27_600,
            "axis_hashes_sha256_le_f64": expected_axes,
            "cell_tag_counts_by_tag": _EXPECTED_TAGS,
            "expected_cell_tag_counts_by_tag": _EXPECTED_TAGS,
            "live_q1_analytic_jacobian_min_nm3": 0.01,
        },
    )
    levels = {
        "mesh_data": SimpleNamespace(
            mesh=object(),
            cell_tags=object(),
            mesh_cell_type_resolved="hexahedron",
            mesh_spacing_mode_resolved="task40_gate_cd_mapped_swept_axes",
        ),
        "spaces": {
            6: SimpleNamespace(
                dofmap=SimpleNamespace(
                    index_map=SimpleNamespace(size_global=18_378_528),
                    index_map_bs=1,
                ),
                element=SimpleNamespace(space_dimension=882),
            )
        },
    }
    mesh_cfg = SimpleNamespace(
        mesh_plan_id=GATE_CD_PROFILE_ID,
        mesh_plan_sha256=GATE_CD_STATIC_PLAN.plan_sha256,
        physical_material_regions=facts["component_options"]["physical_material_regions"],
        geometry_kind="task40_gate_cd_mapped",
        tags=SimpleNamespace(air=1, substrate=2, grating=3),
    )
    evidence = _task40_gate_cd_mesh_evidence(levels, mesh_cfg, route)
    assert evidence["status"] == "PASS"
    assert evidence["operator_scope"] == route["operator_scope"]
    assert evidence["global_p6_dof_rows"] == 18_378_528
    assert evidence["p6_local_element_dimension"] == 882
    bad_route = dict(route)
    bad_route["task40_mesh_plan_family"] = "d13"
    with pytest.raises(ValueError, match="mapped mesh plan"):
        _task40_gate_cd_mesh_evidence(levels, mesh_cfg, bad_route)


def test_formal_profile_roundtrips_through_manifest_and_worker(tmp_path):
    specification = load_and_resolve(_INPUT)
    run_directory = tmp_path / "gate-cd-formal-run"
    run_directory.mkdir()
    specification = replace(
        specification,
        expected_output_parent=run_directory.parent,
    )
    source_sha = "a" * 64
    plan = build_execution_plan(
        specification,
        run_directory,
        source_sha=source_sha,
        python_executable=sys.executable,
        mpiexec_command="/usr/bin/mpiexec",
    )
    manifest, resolved_sha = _write_bootstrap(
        specification,
        run_directory,
        source_sha=source_sha,
        adapter_identity=plan.adapter_identity,
        start_time="2026-11-01T00:00:00Z",
    )
    native_contract = manifest["native_capacity_contract"]
    route = native_contract["direct_route"]
    assert native_contract["resource_stop_policy"] == "host_available_floor_v1"
    assert native_contract["rss_hard_limit_bytes"] is None
    assert native_contract["minimum_available_bytes"] == 64 * 1024**3
    assert route["geometry_identity_policy"] == "mapped_exact"
    assert route["mapped_geometry_translation_invariant"] is True
    route_volume = route["volume_quadrature"]
    assert route_volume["degree"] == 21 and route_volume["rule"] == "default"
    assert route_volume["production_ffcx_metadata_role"] == (
        "pre_override_automatic_ffcx_default_baseline_not_selected_operator"
    )
    assert route_volume["selection_witness"]["sha256"] == (
        "3b012b12005aed7fc809beb349a511c27c8f5a28b74b054f130429986951735e"
    )
    assert route["mapped_geometry_cache_identity"] == (
        "profile_selected_mapped_geometry_cache_v1"
    )

    def validate_worker():
        return _load_and_validate_worker_payload(
            resolved_config=run_directory / "resolved_config.json",
            manifest=run_directory / "run_manifest.json",
            expected_input_sha256=specification.input_sha256,
            expected_physical_model_sha256=specification.physical_model_sha256,
            expected_source_sha=source_sha,
            expected_mpi_size=1,
            expected_method="full3d_direct",
            expected_adapter=plan.adapter_identity,
            expected_output_directory=run_directory,
            expected_resolved_config_sha256=resolved_sha,
            actual_mpi_size=1,
        )

    resolved_payload, errors = validate_worker()
    assert errors == []
    assert resolved_payload["derived"]["native_capacity_profile"] == thaw(
        specification.derived["native_capacity_profile"]
    )

    manifest["native_capacity_contract"]["direct_route"][
        "mapped_geometry_translation_invariant"
    ] = False
    (run_directory / "run_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    _, errors = validate_worker()
    assert "manifest condensed-direct route contract mismatch" in errors


def test_formal_profile_drives_the_real_finite_m8n64_production_inventory():
    from src.solvers.dtn_port_3d import _dtn_surface_quadrature_degree
    from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory

    resolved = load_and_resolve(_INPUT).as_jsonable()
    cfg = simulation_config_3d_from_normalized(resolved)
    route = _direct_run_contract(TASK40_GATE_CD_M8N64_P6_DIRECT_PROFILE)
    cfg.stage4_dtn_order_policy = "explicit_signed_rectangle"
    cfg.task40_dtn_signed_rectangle_bounds_mn = tuple(route["signed_rectangle_bounds_mn"])
    cfg.stage4_dtn_quadrature_degree = route["surface_quadrature_degree"]
    cfg.task40_port_boundary_amplitude_scale_policy = route["mode_basis_scale_policy"]
    inventory = build_dynamic_mode_inventory(cfg)
    modes, rows, mode_sha = inventory
    assert len(modes) == len(rows) == 4_488
    assert mode_sha == _EXPECTED_MODE_SHA
    assert all(-8 <= mode.m <= 8 and -64 <= mode.n <= 1 for mode in modes)
    assert {mode.side for mode in modes} == {"top", "bottom"}
    assert {mode.polarization for mode in modes} == {"s", "p"}
    by_side = Counter(mode.side for mode in modes)
    assert by_side == {"top": 2_244, "bottom": 2_244}
    prop_by_side = Counter(mode.side for mode in modes if bool(mode.propagating))
    power_by_side = Counter(
        mode.side for mode in modes if float(mode.power_per_unit_amplitude) > 0.0
    )
    assert prop_by_side == {"top": 2_182, "bottom": 2_178}
    assert power_by_side == {"top": 2_182, "bottom": 2_244}
    assert sum(
        not bool(mode.propagating) and float(mode.power_per_unit_amplitude) > 0.0
        for mode in modes
    ) == 66
    assert _dtn_surface_quadrature_degree(cfg, list(modes)) == 81

def test_formal_gate_cd_dat_rejects_run_id_and_reporting_envelope_drift(tmp_path):
    source = _INPUT.read_text()
    bad_run = tmp_path / "bad_run.dat"
    bad_run.write_text(source.replace(
        'run_id = "task40_gate_cd_0p7_mapped_m8n64_p6_direct_v1"',
        'run_id = "task40_gate_cd_0p7_mapped_p6_staged_v1"',
    ))
    with pytest.raises(InputError, match="formal run_id"):
        load_and_resolve(bad_run)

    bad_output = tmp_path / "bad_output.dat"
    bad_output.write_text(source.replace("diffraction_order_max_n = 64", "diffraction_order_max_n = 143"))
    with pytest.raises(InputError, match="reporting envelope"):
        load_and_resolve(bad_output)
