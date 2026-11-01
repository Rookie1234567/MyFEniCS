from __future__ import annotations

from pathlib import Path

from src.io.input_validation import load_and_resolve
from src.io.native_capacity_profile import (
    P6_CONDENSED_DIRECT_PROFILES,
    TASK40_GATE_CD_P6_DIRECT_PROFILE,
    native_profile_facts,
)
from src.io.resolved_config import canonical_json_bytes

_ROOT = Path(__file__).resolve().parents[2]
_INPUT = _ROOT / "input/task40_gate_cd/gate_cd_0p7_mapped_p6_staged.dat"


def _json_ready(value):
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_ready(item) for item in value]
    return value


def test_gate_cd_staged_profile_has_no_inherited_d13_operator_authority():
    facts = native_profile_facts(TASK40_GATE_CD_P6_DIRECT_PROFILE)
    options = facts["component_options"]

    assert TASK40_GATE_CD_P6_DIRECT_PROFILE in P6_CONDENSED_DIRECT_PROFILES
    assert facts["execution_mode"] == "staged_mesh_and_material_qa"
    assert (
        facts["launch_status"] == "BLOCKED_UNTIL_GATE_CD_MODE_AND_FULL_RESOURCE_REVIEW"
    )
    assert options["task_family"] == "task40_gate_cd_mapped_mesh_material_qa"
    assert options["mesh_axis_cell_counts"] == [5, 240, 23]
    assert options["expected_axis_cell_counts"] == [5, 240, 23]
    assert options["expected_global_cell_count"] == 27_600
    assert options["expected_material_tag_counts_by_label"] == {
        "Air": 10_800,
        "Si_substrate": 1_200,
        "Si_Fin0": 400,
        "STI_SiO2": 800,
        "Si_poly": 2_800,
        "SiN": 7_520,
        **{f"Fin{index}": 240 for index in range(1, 16)},
        "Gate_SiO2": 240,
        "MDI": 240,
    }
    assert options["directional_mesh_comparison"]["schema"] == (
        "task40.gate-cd-mesh-material-qa.v1"
    )
    assert options["directional_mesh_comparison"]["case"] == "gate_cd_mapped_staged_qa"
    assert options["directional_mesh_comparison"]["changed_axis"] is None
    assert options["mode_selection"]["policy"] == "NOT_FROZEN_FOR_GATE_CD"
    assert options["mode_selection"]["parent_inventory_scope"] == "NOT_RUN"
    assert options["surface_quadrature"]["production_degree"] is None
    assert options["surface_quadrature"]["status"] == "NOT_FROZEN_FOR_GATE_CD"
    assert options["volume_quadrature"]["candidate_degree"] is None
    assert options["volume_quadrature"]["status"] == "NOT_FROZEN_FOR_GATE_CD"
    assert options["dtn_sparse_cutoff_policy"] == (
        "NOT_CONFIGURED_FOR_STAGED_GATE_CD_QA"
    )
    assert options["direct_factor_evidence"]["status"] == ("NOT_RUN_NO_FACTOR_ALLOWED")
    assert options["direct_factor_evidence"]["enabled"] is False
    assert "mode_keys" not in options["direct_factor_evidence"]
    assert options["direct_route_launchable"] is False
    assert options["direct_p6_route"] is False
    assert "direct_route" not in facts["campaign_authorization"]
    assert facts["condensed_route"]["matrix_blocks"] == "NOT_BUILT"
    assert facts["condensed_route"]["factor"] == "NOT_BUILT"
    assert facts["backend"]["global_matrix"] == "NOT_BUILT"
    assert facts["backend"]["independent_residual"] == "NOT_RUN_NO_SOLVE_AUTHORIZED"
    assert facts["campaign_authorization"]["execution_mode"] == (
        "staged_mesh_and_material_qa"
    )
    assert facts["campaign_authorization"]["staged_scope"]["factor"] == (
        "NOT_AUTHORIZED"
    )
    assert not any("D13" in str(value) for value in options.values())
    assert (
        facts["operator_scope"] == "task40_gate_cd_mapped_p6_finite_dtn_not_yet_bound"
    )
    assert facts["full_dtn_status"] == "FULL_DTN_NOT_VERIFIED"


def test_gate_cd_staged_dat_resolves_exact_profile_without_enabling_operator():
    specification = load_and_resolve(_INPUT)
    payload = specification.as_jsonable()
    facts = native_profile_facts(TASK40_GATE_CD_P6_DIRECT_PROFILE)

    assert payload["solver"]["native_capacity_profile"] == (
        TASK40_GATE_CD_P6_DIRECT_PROFILE
    )
    assert canonical_json_bytes(payload["derived"]["native_capacity_profile"]) == (
        canonical_json_bytes(_json_ready(facts))
    )
    assert payload["derived"]["mesh_cells"] == [5, 240, 23]
    assert payload["output"]["write_visualization_files"] is False
    assert facts["component_options"]["direct_route_launchable"] is False
    assert facts["resources"]["resource_stop_policy"] == "host_available_floor_v1"
    assert facts["resources"]["minimum_available_bytes"] == 64 * 1024**3
    assert facts["resources"]["rss_hard_limit_bytes"] is None
