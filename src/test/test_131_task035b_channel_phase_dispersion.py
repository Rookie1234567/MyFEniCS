"""Tests for the Task035b channel phase-dispersion postprocessor."""

from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path

import pytest

import benchmarks.task035b_channel_phase_dispersion as phase_module
from benchmarks.task035b_channel_phase_dispersion import (
    DEFAULT_AUTHORITIES,
    EXPECTED_BRANCH,
    ROOT,
    SOURCE_FILES,
    _load_authorities,
    _validated_source,
    build_channel_phase_dispersion_evidence,
    main,
)
from src.adaptivity.channel_phase_dispersion import (
    analyze_candidate_phase_dispersion,
    build_phase_dispersion_analysis,
    radial_tangential_complex_error,
)


def _qualified_source() -> dict[str, object]:
    sha = "a" * 40
    return {
        "commit_sha": sha,
        "verified_clean_sha": sha,
        "branch": EXPECTED_BRANCH,
        "tracked_source_dirty": False,
        "stable_and_clean_before": True,
        "status_before": "",
        "head_after_sha": sha,
        "branch_after": EXPECTED_BRANCH,
        "status_after_before_record_write": "",
        "stable_and_clean_after": True,
        "checks": {
            "fixture_before": True,
            "fixture_after": True,
        },
    }


def _source_hashes() -> dict[str, str]:
    return {path: "b" * 64 for path in SOURCE_FILES}


@pytest.fixture(scope="module")
def actual_authorities():
    return _load_authorities(ROOT, DEFAULT_AUTHORITIES)


@pytest.fixture(scope="module")
def actual_evidence(actual_authorities):
    authorities, manifest = actual_authorities
    return build_channel_phase_dispersion_evidence(
        authorities=authorities,
        authority_manifest=manifest,
        source=_qualified_source(),
        source_file_sha256=_source_hashes(),
    )


def _synthetic_contract() -> tuple[list[dict], list[dict]]:
    reference = []
    candidate = []
    shifts = {"bottom": 0.0125, "top": -0.025}
    for side, sign in (("bottom", -1.0), ("top", 1.0)):
        for index, order in enumerate((-7, -5, -4, -2, -1, 0)):
            kz = sign * (0.1 + 0.05 * index)
            amplitude = complex(1.0 + 0.1 * index, -0.2 + 0.03 * index)
            phase = kz * shifts[side]
            trial = amplitude * complex(math.cos(phase), math.sin(phase))
            power = 1.0e-6 * (index + 1)
            identity = {
                "label": (
                    ("T" if side == "bottom" else "R")
                    + f"({order},0)_s"
                ),
                "side": side,
                "m": order,
                "n": 0,
                "polarization": "s",
            }
            reference.append(
                {
                    **identity,
                    "kz": [kz, 0.0],
                    "reference_amplitude": [
                        amplitude.real,
                        amplitude.imag,
                    ],
                    "reference_power": power,
                    "power_tolerance": 1.0e-8,
                    "amplitude_tolerance": 1.0e-2,
                }
            )
            candidate.append(
                {
                    **identity,
                    "candidate_amplitude": [trial.real, trial.imag],
                    "candidate_power": power,
                }
            )
    return reference, candidate


def test_synthetic_fit_recovers_each_side_effective_shift():
    reference, candidate = _synthetic_contract()
    analysis = analyze_candidate_phase_dispersion(
        candidate_id="synthetic",
        reference_channels=reference,
        candidate_channels=candidate,
    )
    bottom = analysis["phase_fit_by_side"]["bottom"][
        "reference_power_weighted"
    ]
    top = analysis["phase_fit_by_side"]["top"][
        "reference_power_weighted"
    ]
    assert bottom["delta_z_eff_nm"] == pytest.approx(0.0125, abs=1.0e-13)
    assert top["delta_z_eff_nm"] == pytest.approx(-0.025, abs=1.0e-13)
    assert bottom["weighted_residual_rms_radians"] < 1.0e-15
    assert top["weighted_residual_rms_radians"] < 1.0e-15
    assert all(
        row["tangential_absolute_fraction"] > 0.999
        for row in analysis["channels"]
    )


def test_radial_tangential_split_closes_in_reference_frame():
    result = radial_tangential_complex_error(
        2.0 + 1.0j,
        2.0 + 1.2j,
    )
    assert result["radial_tangential_squared_fraction_closure"] == (
        pytest.approx(1.0, abs=1.0e-15)
    )
    assert result["complex_error_magnitude"] == pytest.approx(0.2)
    assert result["tangential_absolute_fraction"] > 0.89


def test_actual_authorities_produce_diagnostic_only_payload(actual_evidence):
    evidence = actual_evidence
    assert evidence["pass"] is True
    assert evidence["status"] == "diagnostic_only_phase_dispersion_complete"
    assert evidence["classification"] == "diagnostic_only"
    assert evidence["formal_record"] is False
    assert evidence["production_qualified"] is False
    assert evidence["formal_candidate_eligible"] is False
    assert evidence["thresholds_relaxed"] is False
    assert evidence["pde"] == {
        "status": "not_run",
        "mesh_built": False,
        "form_compiled": False,
        "matrix_assembled": False,
        "factorization_started": False,
        "solver_started": False,
    }
    assert evidence["execution_contract"] == {
        "pure_postprocess": True,
        "pde_solve_count": 0,
        "mesh_build_count": 0,
        "matrix_assembly_count": 0,
        "factorization_count": 0,
        "mpi_launch_count": 0,
        "ordinary_default_changed": False,
        "thresholds_relaxed": False,
        "irregular_geometry_run": False,
        "formal_candidate_eligible": False,
        "formal_record_created": False,
    }


def test_actual_phase_fit_and_gate_counts_match_authorities(actual_evidence):
    summaries = actual_evidence["compact_phase_summary"]
    assert summaries["global_p6_h15_control"]["power_pass_count"] == 6
    assert (
        summaries["global_p6_h15_control"]["complex_amplitude_pass_count"]
        == 8
    )
    assert summaries["fixed_p5trace_p6interior_h15"][
        "complex_amplitude_pass_count"
    ] == 7
    assert summaries["fixed_p5trace_p6interior_h14"][
        "complex_amplitude_pass_count"
    ] == 9
    assert summaries["fixed_p5trace_p6interior_h13"][
        "power_pass_count"
    ] == 10
    assert summaries["fixed_p5trace_p6interior_h13"][
        "complex_amplitude_pass_count"
    ] == 10
    assert summaries["fixed_p5trace_p6interior_h15"][
        "bottom_reference_power_weighted_delta_z_eff_nm"
    ] == pytest.approx(0.008526950296922709)
    assert summaries["fixed_p5trace_p6interior_h14"][
        "bottom_reference_power_weighted_delta_z_eff_nm"
    ] == pytest.approx(0.00913892865868693)
    assert summaries["fixed_p5trace_p6interior_h13"][
        "bottom_reference_power_weighted_delta_z_eff_nm"
    ] == pytest.approx(0.009797710953094813)
    global_bottom = actual_evidence["analysis"]["candidates"][
        "global_p6_h15_control"
    ]["phase_fit_by_side"]["bottom"]["reference_power_weighted"]
    fixed_bottom = actual_evidence["analysis"]["candidates"][
        "fixed_p5trace_p6interior_h15"
    ]["phase_fit_by_side"]["bottom"]["reference_power_weighted"]
    assert global_bottom["weighted_raw_phase_rms_radians"] < (
        fixed_bottom["weighted_raw_phase_rms_radians"] / 30.0
    )


def test_actual_remaining_failures_prioritize_phase_trace_orbits(
    actual_evidence,
):
    decision = actual_evidence["research_decision"]
    assert decision["supported"] is True
    assert decision["status"] == (
        "prioritize_phase_bearing_periodic_trace_orbit_diagnostic"
    )
    assert decision["remaining_failed_channel_labels"] == [
        "T(-4,0)_s",
        "R(-5,0)_s",
        "R(-4,0)_s",
    ]
    assert decision["phase_bearing_failed_channel_labels"] == (
        decision["remaining_failed_channel_labels"]
    )
    assert decision["does_not_select_trace_modes"] is True
    assert decision["does_not_authorize_candidate_matrix"] is True
    assert decision["does_not_authorize_gate_relaxation"] is True
    h13 = actual_evidence["analysis"]["candidates"][
        "fixed_p5trace_p6interior_h13"
    ]
    fractions = {
        row["label"]: row["tangential_absolute_fraction"]
        for row in h13["failed_channels"]
    }
    assert fractions["T(-4,0)_s"] == pytest.approx(0.9310238536331821)
    assert fractions["R(-5,0)_s"] == pytest.approx(0.9876809105104267)
    assert fractions["R(-4,0)_s"] == pytest.approx(0.8457227617126716)


def test_phase_priority_fails_closed_when_failures_are_radial():
    reference, _candidate = _synthetic_contract()
    radial_candidate = [
        {
            **{
                key: row[key]
                for key in ("label", "side", "m", "n", "polarization")
            },
            "candidate_amplitude": row["reference_amplitude"],
            "candidate_power": row["reference_power"],
        }
        for row in reference
    ]
    for row in radial_candidate[:2]:
        identity = next(
            reference_row
            for reference_row in reference
            if all(
                reference_row[key] == row[key]
                for key in ("side", "m", "n", "polarization")
            )
        )
        amplitude = complex(*identity["reference_amplitude"]) * 1.2
        row["candidate_amplitude"] = [amplitude.real, amplitude.imag]
        row["candidate_power"] = identity["reference_power"] * 1.44
    result = build_phase_dispersion_analysis(
        reference_channels=reference,
        candidates={"radial": radial_candidate},
        priority_candidate_id="radial",
    )
    assert result["research_priority"]["supported"] is False
    assert result["research_priority"]["phase_bearing_failed_channel_count"] == 0


def test_authority_sha_mismatch_fails_before_analysis():
    definitions = {
        name: dict(definition)
        for name, definition in DEFAULT_AUTHORITIES.items()
    }
    definitions["fixed_h13"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="fixed_h13 SHA256 mismatch"):
        _load_authorities(ROOT, definitions)


def test_tampered_frozen_gate_fails_closed(actual_authorities):
    authorities, manifest = actual_authorities
    tampered = copy.deepcopy(authorities)
    tampered["significant_reference_v1"]["channels"][0][
        "unchanged_v0_acceptance_gate"
    ]["uses_h15_or_fixed_diagnostics"] = True
    with pytest.raises(ValueError, match="unchanged-v0 Gate"):
        build_channel_phase_dispersion_evidence(
            authorities=tampered,
            authority_manifest=manifest,
            source=_qualified_source(),
            source_file_sha256=_source_hashes(),
        )


def test_source_identity_fails_closed_on_wrong_branch():
    source = _qualified_source()
    source["branch"] = "master"
    with pytest.raises(ValueError, match="source is unqualified"):
        _validated_source(source)


def test_cli_uses_exclusive_artifact_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source_before = _qualified_source()
    for key in (
        "head_after_sha",
        "branch_after",
        "status_after_before_record_write",
        "stable_and_clean_after",
    ):
        source_before.pop(key)
    source_before["checks"] = {"fixture_before": True}
    source_after = {
        "head_after_sha": source_before["commit_sha"],
        "branch_after": EXPECTED_BRANCH,
        "status_after_before_record_write": "",
        "stable_and_clean_after": True,
        "checks": {"fixture_after": True},
    }
    monkeypatch.setattr(
        phase_module,
        "_runtime_preflight",
        lambda _root: {"pass": True, "checks": {"fixture": True}},
    )
    monkeypatch.setattr(
        phase_module,
        "_verified_source_identity",
        lambda _root, _sha: dict(source_before),
    )
    monkeypatch.setattr(
        phase_module,
        "_reverify_source_before_write",
        lambda _root, _source: dict(source_after),
    )
    monkeypatch.setattr(
        phase_module,
        "_source_file_sha256",
        lambda _root: _source_hashes(),
    )
    output = tmp_path / "phase_dispersion.json"
    arguments = [
        "--verified-clean-sha",
        "a" * 40,
        "--output",
        str(output),
    ]
    assert main(arguments) == 0
    original_sha = hashlib.sha256(output.read_bytes()).hexdigest()
    payload = json_load(output)
    assert payload["classification"] == "diagnostic_only"
    assert payload["formal_record"] is False
    with pytest.raises(FileExistsError):
        main(arguments)
    assert hashlib.sha256(output.read_bytes()).hexdigest() == original_sha


def json_load(path: Path) -> dict:
    import json

    return json.loads(path.read_text(encoding="utf-8"))
