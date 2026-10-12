"""Explicit V6 p3 profile/input identity checks; no FE operator is built."""
from pathlib import Path

import pytest

from benchmarks.physical_intermediate_checker import check_retained_v20
from src.io import load_and_resolve
from src.io.input_loader import InputError
from src.io.native_capacity_profile import native_profile_facts, validate_native_case
from src.runners.physical_retained_condensed_v20 import (
    _geometry_identity_policy_for_profile,
)
from src.runners.task038_launcher import _base_manifest
from src.solvers.fullspace_same_mesh_hcurl_pmg import (
    V6_P3_CANONICAL_TRACE_MAP_POLICY,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("p3_input", "p4_input", "expected_mode_count", "expected_profile"),
    [
        (
            "v6_13p5_p3_anchor.dat",
            "v5_node1_13p5nm_p6h7p5_q4.dat",
            80,
            "dual_condensed_balh_native_13p5_p3_v6",
        ),
        (
            "v6_5nm_p3_full.dat",
            "v6_5nm_full.dat",
            600,
            "dual_condensed_balh_native_5nm_p3_v6",
        ),
        (
            "v6_2nm_p3_pilot16.dat",
            "v6_2nm_pilot16.dat",
            3904,
            "dual_condensed_balh_native_2nm_p3_pilot16_v6",
        ),
    ],
)
def test_explicit_p3_input_resolves_a3_without_changing_physics(
    p3_input, p4_input, expected_mode_count, expected_profile, tmp_path
):
    p3 = load_and_resolve(
        ROOT / "input/task39extra_para_workstation_capacity" / p3_input
    )
    p4 = load_and_resolve(
        ROOT / "input/task39extra_para_workstation_capacity" / p4_input
    )

    assert p3.solver["coarse_degree"] == 3
    assert p3.solver["preconditioner"] == expected_profile
    assert p3.physical_model_sha256 == p4.physical_model_sha256
    assert p3.method == p4.method

    profile = native_profile_facts(expected_profile)
    assert (
        profile["condensed_route"]["geometry_identity_policy"]
        == _geometry_identity_policy_for_profile(expected_profile)
    )
    assert profile["retained_condensed_v20"]["coarse_degree"] == 3
    assert profile["coarse_operator"]["name"] == "A3"
    assert profile["coarse_operator"]["degree"] == 3
    assert (
        profile["component_options"]["same_mesh_trace_map_policy"]
        == V6_P3_CANONICAL_TRACE_MAP_POLICY
    )
    assert (
        profile["coarse_operator"]["same_mesh_trace_map_policy"]
        == V6_P3_CANONICAL_TRACE_MAP_POLICY
    )
    assert profile["backend"]["original_a3"] == "fused_original_volume_plus_complete_DtN"
    assert "original_a4" not in profile["backend"]
    assert profile["backend"]["p4_compatibility_alias"].endswith("actual operator is A3")
    assert profile["component_options"]["reference_metric_diagonal"] is True
    assert profile["component_options"]["direct_h6_backend"] is True
    assert profile["component_options"]["blocked_gram"] is True

    snapshot = p3.as_jsonable()
    manifest = _base_manifest(
        p3,
        run_directory=tmp_path,
        source_sha="1" * 40,
        adapter_identity="task038.full3d_iterative",
        start_time="2026-10-04T00:00:00Z",
        resolved_sha="2" * 64,
    )
    contract = manifest["native_capacity_contract"]["coarse_operator"]
    assert snapshot["solver"]["coarse_degree"] == 3
    assert contract["degree"] == contract["resolved_solver_degree"] == 3
    assert contract["name"] == "A3"
    assert contract["compatibility_storage_names"] == ["p4_* aliases"]
    assert expected_mode_count == (
        600 if "5nm" in p3_input else 80 if "13p5" in p3_input else 3904
    )
    if "13p5" in p3_input:
        assert profile["execution_mode"] == "full_solve"
        assert profile["outer"]["planned_stop_iteration"] is None
        assert profile["resources"]["rss_hard_limit_bytes"] == 1_300_000_000_000
        assert profile["native_execution"]["mpi_size"] == 1
        assert profile["native_execution"]["math_threads"] == 1

    wrong_degree = snapshot
    wrong_degree["solver"]["coarse_degree"] = 4
    with pytest.raises(InputError, match="coarse_degree=3"):
        validate_native_case(wrong_degree)


@pytest.mark.parametrize(
    "identity",
    [
        "dual_condensed_balh_native_5nm_v6",
        "dual_condensed_balh_native_2nm_h6_only_v6",
        "dual_condensed_balh_native_2nm_pilot16_v6",
    ],
)
def test_existing_v6_q4_facts_keep_the_legacy_contract(identity):
    facts = native_profile_facts(identity)
    assert facts["retained_condensed_v20"]["coarse_degree"] == 4
    assert "coarse_operator" not in facts
    assert "coarse_operator" not in facts["backend"]
    assert "original_a3" not in facts["backend"]
    assert facts["backend"]["original_a4"] == "fused_original_volume_plus_complete_DtN"
    assert "same_mesh_trace_map_policy" not in facts["component_options"]
    assert facts["execution_mode"] == (
        "h6_only" if "h6_only" in identity else
        "pilot_16" if "pilot16" in identity else "full_solve"
    )


def test_v5_p3_does_not_enable_v6_trace_policy():
    facts = native_profile_facts("dual_condensed_balh_native_13p5_q3_v5")
    assert facts["retained_condensed_v20"]["coarse_degree"] == 3
    assert "same_mesh_trace_map_policy" not in facts.get("component_options", {})
    assert facts["condensed_route"]["geometry_identity_policy"] == "raw_unrounded"
    assert (
        facts["condensed_route"]["geometry_identity_policy"]
        == _geometry_identity_policy_for_profile("dual_condensed_balh_native_13p5_q3_v5")
    )


def test_frozen_r13_axes_are_rejected_for_non_anchor_v6_profile(tmp_path):
    source = ROOT / "input/task39extra_para_workstation_capacity/v6_5nm_p3_full.dat"
    original = source.read_text(encoding="utf-8")
    section = "[discretization]\n"
    assert original.count(section) == 1
    modified = original.replace(
        section,
        section + "mesh_axis_cell_counts = [7, 4, 19]\n",
        1,
    )
    invalid_input = tmp_path / "v6_5nm_p3_with_frozen_r13_axes.dat"
    invalid_input.write_text(modified, encoding="utf-8")

    with pytest.raises(InputError, match="frozen x/y/z mesh axes are reserved"):
        load_and_resolve(invalid_input)


def test_v6_13p5_p3_identity_is_opt_in_and_keeps_q4_profile_unchanged():
    from src.io.native_capacity_profile import V6_BASE_PROFILES, V6_P3_PROFILES

    identity = "dual_condensed_balh_native_13p5_p3_v6"
    assert V6_BASE_PROFILES[identity] == "dual_condensed_balh_native_13p5_q3_v5"
    assert identity in V6_P3_PROFILES
    old_facts = native_profile_facts("dual_condensed_balh_native_13p5_q3_v5")
    assert "same_mesh_trace_map_policy" not in old_facts.get("component_options", {})
    facts = native_profile_facts(identity)
    runtime_policy = _geometry_identity_policy_for_profile(identity)
    assert facts["condensed_route"]["geometry_identity_policy"] == runtime_policy
    assert runtime_policy == "rounded_12_representative"


def test_checker_still_resolves_the_legacy_v3_profile_contract(tmp_path):
    identity = "dual_condensed_balh_native_5nm_v3"
    summary = {
        "profile": native_profile_facts(identity),
        "solve": {},
        "retained_runtime": {},
    }
    result = check_retained_v20(tmp_path, summary)

    # This deliberately incomplete checker fixture is expected to fail other
    # output/resource gates; it must still resolve and compare the old V3
    # profile contract instead of comparing its facts with an empty dict.
    assert "retained resolved profile facts differ from native contract" not in result[
        "gate_failures"
    ]
    assert result["raw_facts"]["reference_scope"]["case_expected_mode_count"] == 600


def test_checker_rejects_a3_runtime_with_legacy_a4_label(tmp_path):
    identity = "dual_condensed_balh_native_5nm_p3_v6"
    summary = {
        "profile": native_profile_facts(identity),
        "solve": {},
        "retained_runtime": {"coarse_operator": {"degree": 3, "name": "A4"}},
    }
    result = check_retained_v20(tmp_path, summary)
    assert "p3 runtime summary does not identify the actual A3 operator" in result[
        "gate_failures"
    ]


def test_0p7_p3_hp_optin_keeps_its_own_material_and_component_identity(tmp_path):
    from copy import deepcopy

    from src.io.native_capacity_profile import (
        V6_0P7_P3_HP_OPTIN_PROFILES,
        V6_P3_PROFILES,
    )

    input_path = ROOT / "input/task39extra_para_workstation_capacity/v6_0p7nm_p3_pilot16.dat"
    spec = load_and_resolve(input_path)
    identity = "dual_condensed_balh_native_0p7nm_p3_pilot16_v6"
    assert identity == spec.solver["preconditioner"]
    snapshot = spec.as_jsonable()
    assert snapshot["incidence"]["wavelength_nm"] == 0.7
    assert snapshot["discretization"]["mesh_target_nm"] == 0.7
    assert spec.solver["coarse_degree"] == 3

    facts = native_profile_facts(identity)
    assert identity in V6_0P7_P3_HP_OPTIN_PROFILES & V6_P3_PROFILES
    assert facts["campaign_authorization"]["user_material"]["source_sha256"] == (
        "3e947de11141efbba8b0df1ece4d75f56c72075d060cc2b457cf21be1400d884"
    )
    assert "two_nm_material" not in facts["campaign_authorization"]
    assert "five_nm_material" not in facts["campaign_authorization"]
    assert facts["component_options"]["exact_carrier_diagonal_hp"] is True
    assert facts["component_options"]["omit_structural_zero_hlocal"] is True
    assert facts["component_options"]["reuse_dtn_surface_vector"] is True
    assert facts["component_options"]["reuse_dtn_surface_geometry_cache"] is True
    assert facts["component_options"]["dtn_surface_geometry_cache_limit_bytes"] == 4 * 1024**3
    assert facts["component_options"]["dtn_component_cache_last_use_release"] is True
    assert facts["component_options"]["dtn_mode_progress_interval"] == 1024
    assert facts["component_options"]["dtn_surface_assembly_backend_by_degree"] == {
        "p6": "q160_affine_hex_pointwise_weighted_legendre_component_pair_v1",
        "p3": "native_ffcx",
    }
    assert facts["resources"]["rss_hard_limit_bytes"] == 1_950_000_000_000
    assert facts["campaign_authorization"]["resource_policy"]["rss_hard_limit_bytes"] == (
        1_950_000_000_000
    )
    assert facts["campaign_authorization"]["memory_override"][
        "parent_and_worker_cap_bytes"
    ] == 1_950_000_000_000

    manifest = _base_manifest(
        spec,
        run_directory=tmp_path,
        source_sha="a" * 40,
        adapter_identity="task038.full3d_iterative",
        start_time="2026-10-05T00:00:00Z",
        resolved_sha="b" * 64,
    )
    assert manifest["component_options"] == facts["component_options"]
    assert manifest["native_capacity_contract"]["profile"] == identity
    assert manifest["native_capacity_contract"]["wavelength_nm"] == 0.7

    wrong_material = deepcopy(snapshot)
    wrong_material["materials"]["n_substrate"] = [0.99880148307, 0.000213688647]
    with pytest.raises(InputError, match="materials.n_substrate"):
        validate_native_case(wrong_material)

    for old_identity in (
        "dual_condensed_balh_native_5nm_p3_v6",
        "dual_condensed_balh_native_2nm_p3_pilot16_v6",
        "dual_condensed_balh_native_2nm_pilot16_v6",
    ):
        old_facts = native_profile_facts(old_identity)
        assert "exact_carrier_diagonal_hp" not in old_facts["component_options"]
        assert "omit_structural_zero_hlocal" not in old_facts["component_options"]
        assert "reuse_dtn_surface_vector" not in old_facts["component_options"]
        assert "reuse_dtn_surface_geometry_cache" not in old_facts["component_options"]
        assert "dtn_surface_geometry_cache_limit_bytes" not in old_facts["component_options"]
        assert "dtn_surface_assembly_backend_by_degree" not in old_facts[
            "component_options"
        ]
        assert old_facts["resources"]["rss_hard_limit_bytes"] == 1_300_000_000_000


def test_0p7_n0_profile_is_explicit_and_keeps_parent_quadrature_identity():
    from src.io.native_capacity_profile import (
        V6_0P7_N0_P3_PROFILES,
        V6_0P7_P3_HP_OPTIN_PROFILES,
        V6_PILOT16_PROFILES,
        V6_P3_PROFILES,
        native_profile_facts,
    )

    path = ROOT / "input/task39extra_para_workstation_capacity/v6_0p7nm_n0_p3_pilot16.dat"
    specification = load_and_resolve(path)
    identity = "dual_condensed_balh_native_0p7nm_n0_p3_pilot16_v6"
    assert specification.solver["preconditioner"] == identity
    assert identity in V6_0P7_N0_P3_PROFILES
    assert identity in V6_0P7_P3_HP_OPTIN_PROFILES & V6_P3_PROFILES & V6_PILOT16_PROFILES
    assert specification.as_jsonable()["execution"]["terminate_memory_gib"] == (
        1_950_000_000_000 / 2**30
    )

    facts = native_profile_facts(identity)
    selection = facts["component_options"]["dtn_mode_selection"]
    assert selection == {
        "schema": "task39extra.dtn-mode-selection.v1",
        "policy": "n_equals_zero_both_ports_both_polarizations",
        "parent_mode_count": 32060,
        "parent_mode_sha256": (
            "7f023c73d7b63379955642dd062e47ba7004f3cdf0accf42684286c4af71dbfb"
        ),
        "active_mode_count": 572,
        "expected_active_mode_sha256": (
            "946e0d294b99cb7f44817c3649029942ac325f345eb1770caa566183d2b04f3b"
        ),
        "m_range_in_each_side_polarization": [-142, 0],
        "quadrature_inventory": "full_parent_modes",
        "operator_scope": "n0_filtered_dtn_not_full_dtn",
    }
    assert facts["outer"]["planned_stop_iteration"] == 16
    assert facts["resources"]["rss_hard_limit_bytes"] == 1_950_000_000_000
    assert "full_dtn" not in facts.get("qualification", {})


def test_n0_mode_inventory_binds_parent_and_active_identities(monkeypatch):
    from types import SimpleNamespace

    import src.solvers.fullspace_dtn_action as action

    selected_modes = []
    for side in ("bottom", "top"):
        for polarization in ("s", "p"):
            for m in range(-142, 1):
                mode = SimpleNamespace(side=side, polarization=polarization, m=m, n=0)
                selected_modes.append(mode)
    selected_parent_indices_expected = tuple(
        1 + round(index * (action.N0_PARENT_MODE_COUNT - 3) / (len(selected_modes) - 1))
        for index in range(len(selected_modes))
    )
    selected_by_parent_index = dict(
        zip(selected_parent_indices_expected, selected_modes, strict=True)
    )
    parent_modes = []
    parent_rows = []
    for index in range(action.N0_PARENT_MODE_COUNT):
        mode = selected_by_parent_index.get(index)
        if mode is None:
            mode = SimpleNamespace(
                side="top", polarization="s", m=index % 7, n=1
            )
        parent_modes.append(mode)
        parent_rows.append(
            {"mode_index": index, "side": mode.side, "polarization": mode.polarization,
             "m": mode.m, "n": mode.n}
        )
    assert selected_parent_indices_expected[0] > 0
    assert selected_parent_indices_expected[-1] < action.N0_PARENT_MODE_COUNT - 1
    assert any(
        right - left > 1
        for left, right in zip(
            selected_parent_indices_expected,
            selected_parent_indices_expected[1:],
        )
    )
    assert any(int(mode.n) != 0 for mode in parent_modes[:572])

    monkeypatch.setattr(action, "N0_PARENT_MODE_SHA256", "a" * 64)
    monkeypatch.setattr(action, "N0_EXPECTED_ACTIVE_MODE_SHA256", "b" * 64)
    monkeypatch.setattr(
        action,
        "build_ordered_mode_manifest",
        lambda modes, _cfg: (
            tuple({"mode_index": i, "n": int(mode.n)} for i, mode in enumerate(modes)),
            b"active",
            "b" * 64,
        ),
    )
    active, selection, parent_indices = action.build_n0_mode_inventory(
        (tuple(parent_modes), tuple(parent_rows), "a" * 64), object()
    )
    assert len(active[0]) == len(active[1]) == 572
    assert active[2] == selection["active_mode_sha256"] == "b" * 64
    assert parent_indices == selected_parent_indices_expected
    assert active[0] == tuple(selected_modes)
    assert active[0] != tuple(parent_modes[:572])
    assert tuple(index for index, mode in enumerate(parent_modes) if mode.n == 0) == (
        selected_parent_indices_expected
    )
    assert selection["parent_mode_sha256"] == "a" * 64
    assert selection["parent_mode_count"] == 32060
    assert selection["active_mode_count"] == 572

    with pytest.raises(ValueError, match="exact full 32060-mode parent"):
        action.build_n0_mode_inventory(
            (tuple(parent_modes), tuple(parent_rows), "c" * 64), object()
        )

    # An implementation that treats the selected 572 rows as a prefix is wrong.
    # The deliberately interleaved fixture makes that shortcut observably different.
    prefix_shortcut = tuple(parent_modes[:572])
    assert prefix_shortcut != active[0]
    assert sum(int(mode.n) == 0 for mode in prefix_shortcut) < action.N0_ACTIVE_MODE_COUNT


def test_generic_572_mode_store_does_not_imply_n0_selection():
    from copy import deepcopy

    import src.solvers.fullspace_dtn_functional_store as store

    generic_identity = {
        "schema": store.P3_NUMERICAL_IDENTITY_SCHEMA,
        "source_sha256": "a" * 40,
        "resolved_config_sha256": "b" * 64,
        "implementation_file_sha256": {"src/fake.py": "c" * 64},
        "input_sha256": "d" * 64,
        "physical_model_sha256": "e" * 64,
        "backend": "native_ffcx",
        "degree": 3,
        "mesh": {},
        "dof_mpc": {},
        "modes": {
            "count": 572,
            "ordered_manifest_sha256": "f" * 64,
        },
        "quadrature": {"degree": 160, "surface_forms": {}},
        "abi": {},
    }
    accepted = store._validate_identity(generic_identity)
    assert accepted["modes"]["count"] == 572
    assert "operator_selection" not in accepted

    n0_selection = {
        "schema": "task39extra.dtn-mode-selection.v1",
        "policy": "n_equals_zero_both_ports_both_polarizations",
        "parent_mode_count": 32060,
        "parent_mode_sha256": (
            "7f023c73d7b63379955642dd062e47ba7004f3cdf0accf42684286c4af71dbfb"
        ),
        "active_mode_count": 572,
        "active_mode_sha256": (
            "946e0d294b99cb7f44817c3649029942ac325f345eb1770caa566183d2b04f3b"
        ),
        "expected_active_mode_sha256": (
            "946e0d294b99cb7f44817c3649029942ac325f345eb1770caa566183d2b04f3b"
        ),
        "selected_parent_indices_sha256": "1" * 64,
        "side_polarization_counts": {
            "bottom_p": 143,
            "bottom_s": 143,
            "top_p": 143,
            "top_s": 143,
        },
        "m_range_in_each_side_polarization": [-142, 0],
        "quadrature_inventory": "full_parent_modes",
        "operator_scope": "n0_filtered_dtn_not_full_dtn",
    }
    active_mode_identity = {
        "count": 572,
        "ordered_manifest_sha256": n0_selection["active_mode_sha256"],
    }
    assert store._validate_operator_selection_identity(
        n0_selection, active_mode_identity
    ) == n0_selection

    wrong_count = deepcopy(n0_selection)
    wrong_count["active_mode_count"] = 571
    with pytest.raises(ValueError, match="N0 operator selection identity is malformed"):
        store._validate_operator_selection_identity(wrong_count, active_mode_identity)

    wrong_hash = deepcopy(n0_selection)
    wrong_hash["expected_active_mode_sha256"] = "2" * 64
    with pytest.raises(ValueError, match="N0 operator selection identity is malformed"):
        store._validate_operator_selection_identity(wrong_hash, active_mode_identity)
