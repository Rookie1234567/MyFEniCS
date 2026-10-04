"""Explicit V6 p3 profile/input identity checks; no FE operator is built."""
from pathlib import Path

import pytest

from benchmarks.physical_intermediate_checker import check_retained_v20
from src.io import load_and_resolve
from src.io.input_loader import InputError
from src.io.native_capacity_profile import native_profile_facts, validate_native_case
from src.runners.task038_launcher import _base_manifest
from src.solvers.fullspace_same_mesh_hcurl_pmg import (
    V6_P3_CANONICAL_TRACE_MAP_POLICY,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("p3_input", "p4_input", "expected_mode_count", "expected_profile"),
    [
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
    assert expected_mode_count == (600 if "5nm" in p3_input else 3904)

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
