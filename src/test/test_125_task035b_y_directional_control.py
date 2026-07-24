"""Tests for the independent Task035b y-only directional comparator."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import benchmarks.task035b_y_directional_control as y_control_module
from benchmarks.run_task035_actual_r5 import (
    _watchdog_ordinary_default_identity,
)
from benchmarks.task035b_y_directional_control import (
    EXPECTED_BRANCH,
    _EXPECTED_Y_MESH_IDENTITY,
    _FIXED_TARGET_IDENTITY,
    _H15_AXIS_SHA256,
    _Y_AXIS_SHA256,
    _directional_signal,
    _reverify_source_before_write,
    _verified_source_identity,
    build_y_directional_control_comparison,
    main,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    return _sha256(path)


def _order(
    *,
    side: str,
    m: int,
    polarization: str,
    power: float,
    amplitude: complex,
) -> dict[str, Any]:
    return {
        "side": side,
        "m": m,
        "n": 0,
        "polarization": polarization,
        "direction": (
            "outgoing_up" if side == "top" else "outgoing_down"
        ),
        "medium": "air" if side == "top" else "substrate",
        "order_m": m,
        "order_n": 0,
        "alpha": [float(m), 0.0],
        "gamma": [0.0, 0.0],
        "beta": [1.0, 0.0],
        "kz": [1.0, 0.0],
        "vertical_sign": 1 if side == "top" else -1,
        "propagating": True,
        "power_carrying": True,
        "rayleigh_warning": False,
        "refractive_index": [1.0, 0.0],
        "boundary_phase": [1.0, 0.0],
        "power_ratio": power,
        "outgoing_amplitude_at_boundary": [
            amplitude.real,
            amplitude.imag,
        ],
    }


def _orders_payload(offset: float) -> dict[str, Any]:
    orders = []
    for side in ("bottom", "top"):
        for m in range(-5, 1):
            center_power = 0.01 + 0.001 * (m + 5)
            center_amplitude = complex(0.1 + 0.01 * (m + 5), 0.02)
            orders.append(
                _order(
                    side=side,
                    m=m,
                    polarization="s",
                    power=center_power + offset,
                    amplitude=center_amplitude + offset,
                )
            )
    for index in range(68):
        orders.append(
            _order(
                side="top",
                m=100 + index,
                polarization="p",
                power=0.0,
                amplitude=0.0j,
            )
        )
    assert len(orders) == 80
    return {"metrics": {}, "orders": orders}


def _compact_solve(
    degree: int,
    dofs: int,
    *,
    axis_cells: list[int],
    exact_axis: bool,
) -> dict[str, Any]:
    residual = 2.0e-12
    result = {
        "degree": degree,
        "h_nm": 15.0,
        "case_status": "completed",
        "official_result": True,
        "mpi_size": 8,
        "num_mesh_cells": (
            axis_cells[0] * axis_cells[1] * axis_cells[2]
        ),
        "mesh_cell_type_actual": "hexahedron",
        "num_nedelec_dofs": dofs,
        "linear_system_relative_residual": residual,
        "cell_static_condensation": {
            "full_explicit_true_residual": {
                "linear_system_relative_residual": residual,
            }
        },
    }
    if exact_axis:
        result["mesh_cells_resolved"] = axis_cells
        result["mesh_axis_cell_counts_requested"] = axis_cells
    return result


def _clean_source() -> dict[str, Any]:
    sha = "a" * 40
    return {
        "commit_sha": sha,
        "verified_clean_sha": sha,
        "tracked_source_dirty": False,
        "stable_and_clean_after": True,
    }


def _qualification() -> dict[str, Any]:
    return {
        "pass": True,
        "checks": {
            "fixture_gate": True,
            "ordinary_default_unchanged": True,
        },
        "failures": [],
    }


def _comparison_source() -> dict[str, Any]:
    sha = "b" * 40
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
            "fixture_source_before": True,
            "fixture_source_after": True,
        },
    }


def _baseline_record() -> dict[str, Any]:
    mesh = {
        "mesh_cell_type": "hexahedron",
        "global_cell_count": 120,
        "mesh_cells_resolved": [6, 2, 10],
        "partition_independent_mesh_sha256": "1" * 64,
        "cell_tag_sha256": "2" * 64,
        "facet_tag_sha256": "3" * 64,
        "material_plane_alignment": {"all_aligned": True},
    }
    return {
        "schema_version": "task035.actual-global-r5-watchdog.v1",
        "status": "actual_global_r5_pass",
        "source": _clean_source(),
        "qualification": _qualification(),
        "terminated_for_memory": False,
        "terminated_for_timeout": False,
        "target_identity": _FIXED_TARGET_IDENTITY,
        "same_mesh_hashes": True,
        "common_mesh_identity": mesh,
        "coarse": _compact_solve(
            5,
            49690,
            axis_cells=[6, 2, 10],
            exact_axis=False,
        ),
        "enriched": _compact_solve(
            6,
            84492,
            axis_cells=[6, 2, 10],
            exact_axis=False,
        ),
    }


def _reference(
    *,
    baseline_path: Path,
    baseline_sha: str,
    baseline_orders_path: Path,
    baseline_orders_sha: str,
) -> dict[str, Any]:
    channels = []
    for side in ("bottom", "top"):
        for m in range(-5, 1):
            center_power = 0.01 + 0.001 * (m + 5)
            center_amplitude = complex(0.1 + 0.01 * (m + 5), 0.02)
            analytic = _order(
                side=side,
                m=m,
                polarization="s",
                power=center_power,
                amplitude=center_amplitude,
            )
            analytic_identity = {
                key: analytic[key]
                for key in (
                    "side",
                    "direction",
                    "medium",
                    "m",
                    "n",
                    "order_m",
                    "order_n",
                    "polarization",
                    "alpha",
                    "gamma",
                    "beta",
                    "kz",
                    "vertical_sign",
                    "propagating",
                    "power_carrying",
                    "rayleigh_warning",
                    "refractive_index",
                    "boundary_phase",
                )
            }
            channels.append(
                {
                    "channel": {
                        "side": side,
                        "m": m,
                        "n": 0,
                        "polarization": "s",
                    },
                    "analytic_identity": analytic_identity,
                    "reference_center": {
                        "power": center_power,
                        "complex_amplitude": [
                            center_amplitude.real,
                            center_amplitude.imag,
                        ],
                    },
                    "unchanged_v0_acceptance_gate": {
                        "power_absolute_tolerance": 1.0e-4,
                        "complex_amplitude_absolute_tolerance": 1.0e-4,
                        "uses_numerical_convergence_band": False,
                        "uses_h15_or_fixed_diagnostics": False,
                        "unchanged_v0_formula_verified": True,
                    },
                }
            )
    common = _baseline_record()["common_mesh_identity"]
    expectations = {
        f"common_mesh_identity.{key}": value
        for key, value in common.items()
        if key != "material_plane_alignment"
    }
    return {
        "schema_version": "task035b.significant-channel-reference.v1",
        "status": "significant_channel_reference_v1_frozen",
        "pass": True,
        "mechanical_validation_pass": True,
        "reference_payload_sha256": "4" * 64,
        "significant_channel_selection": {
            "channel_count": 12,
            "expected_and_observed_identity_match": True,
        },
        "reference_convergence_summary": {
            "all_12_channels_converged": True,
        },
        "authority_manifest": {"mechanically_validated": True},
        "authorities": [
            {
                "sample_id": "p5_h15",
                "role": "underresolved_diagnostic",
                "degree": 5,
                "h_nm": 15.0,
                "qualification": "validated_pass",
                "record": {
                    "path": str(baseline_path),
                    "sha256": baseline_sha,
                },
                "raw_dtn_port_orders": {
                    "path": str(baseline_orders_path),
                    "sha256": baseline_orders_sha,
                    "order_count": 80,
                },
                "record_expectations": expectations,
            }
        ],
        "channels": channels,
    }


def _raw_summary(
    degree: int,
    dofs: int,
    *,
    include_orders_filename: bool,
) -> dict[str, Any]:
    compact = _compact_solve(
        degree,
        dofs,
        axis_cells=[6, 3, 10],
        exact_axis=True,
    )
    compact["config"] = {
        "mesh_axis_cell_counts_requested": [6, 3, 10],
    }
    if include_orders_filename:
        compact[
            "dtn_port_orders_json"
        ] = "dtn_port_diffraction_orders_3d.json"
    return compact


def _write_y_record(
    root: Path,
    *,
    candidate_offset: float,
) -> tuple[Path, str]:
    run_dir = root / "raw_y_control"
    orders_path = (
        run_dir
        / "enriched_p5"
        / "dtn_port_diffraction_orders_3d.json"
    )
    orders_sha = _write_json(
        orders_path,
        _orders_payload(candidate_offset),
    )
    mesh = {
        **_EXPECTED_Y_MESH_IDENTITY,
        "material_plane_alignment": {"all_aligned": True},
    }
    raw_result = {
        "schema_version": "task035.target-actual-global-r5.v1",
        "status": "actual_global_r5_pass",
        "ordinary_default_changed": False,
        "same_mesh_hashes": True,
        "reuse_single_mesh_requested": True,
        "single_in_memory_mesh_instance": True,
        "common_mesh_identity": mesh,
        "coarse": {
            "degree": 4,
            "h_nm": 15.0,
            "summary": _raw_summary(
                4,
                38092,
                include_orders_filename=False,
            ),
        },
        "enriched": {
            "degree": 5,
            "h_nm": 15.0,
            "summary": _raw_summary(
                5,
                72995,
                include_orders_filename=True,
            ),
        },
    }
    raw_result_path = run_dir / "actual_r5_result.json"
    raw_result_sha = _write_json(raw_result_path, raw_result)
    preflight = {
        "schema_version": (
            "task035b.structured-axis-global-control-preflight.v1"
        ),
        "status": "pass",
        "pass": True,
        "control_role": "y_only_global_p5_directional_control",
        "ordinary_default_changed": False,
        "axis_plan": {
            "mesh_cells_resolved": [6, 3, 10],
            "axis_sha256": _Y_AXIS_SHA256,
            "h15_axis_sha256": _H15_AXIS_SHA256,
            "expected_mesh_identity": {
                key: value
                for key, value in _EXPECTED_Y_MESH_IDENTITY.items()
                if key.endswith("sha256")
            },
        },
    }
    preflight_path = run_dir / "structured_axis_resource_preflight.json"
    preflight_sha = _write_json(preflight_path, preflight)
    record = {
        "schema_version": "task035.actual-global-r5-watchdog.v1",
        "status": "actual_global_r5_pass",
        "source": _clean_source(),
        "qualification": _qualification(),
        "terminated_for_memory": False,
        "terminated_for_timeout": False,
        "target_identity": _FIXED_TARGET_IDENTITY,
        **_watchdog_ordinary_default_identity(raw_result),
        "same_mesh_hashes": True,
        "reuse_single_mesh_requested": True,
        "single_in_memory_mesh_instance": True,
        "common_mesh_identity": mesh,
        "coarse": _compact_solve(
            4,
            38092,
            axis_cells=[6, 3, 10],
            exact_axis=True,
        ),
        "enriched": _compact_solve(
            5,
            72995,
            axis_cells=[6, 3, 10],
            exact_axis=True,
        ),
        "structured_axis_resource_preflight": preflight,
        "structured_axis_control_classification": {
            "role": "y_only_global_p5_directional_control",
            "diagnostic_only": True,
            "formal_candidate_eligible": False,
            "reference_v1_gate_evaluated_in_this_record": False,
            "required_followup": (
                "SHA-bound frozen-reference-v1 channel comparator"
            ),
            "thresholds_relaxed": False,
        },
        "raw_evidence": {
            "run_directory": str(run_dir),
            "actual_r5_result": str(raw_result_path),
            "actual_r5_result_sha256": raw_result_sha,
            "structured_axis_resource_preflight": str(
                preflight_path
            ),
            "structured_axis_resource_preflight_sha256": (
                preflight_sha
            ),
            "structured_axis_enriched_orders": str(orders_path),
            "structured_axis_enriched_orders_sha256": orders_sha,
            "structured_axis_enriched_orders_count": 80,
            "structured_axis_enriched_orders_qualified": True,
        },
    }
    record_path = root / "y_control_watchdog.json"
    return record_path, _write_json(record_path, record)


def _authorities(
    tmp_path: Path,
    *,
    candidate_offset: float,
) -> dict[str, Any]:
    baseline_orders_path = tmp_path / "baseline_p5_orders.json"
    baseline_orders_sha = _write_json(
        baseline_orders_path,
        _orders_payload(2.0e-4),
    )
    baseline_path = tmp_path / "baseline_watchdog.json"
    baseline_sha = _write_json(baseline_path, _baseline_record())
    reference_path = tmp_path / "reference_v1.json"
    reference_sha = _write_json(
        reference_path,
        _reference(
            baseline_path=baseline_path,
            baseline_sha=baseline_sha,
            baseline_orders_path=baseline_orders_path,
            baseline_orders_sha=baseline_orders_sha,
        ),
    )
    y_path, y_sha = _write_y_record(
        tmp_path,
        candidate_offset=candidate_offset,
    )
    return {
        "repo_root": tmp_path,
        "y_control_record_path": y_path,
        "y_control_record_sha256": y_sha,
        "reference_record_path": reference_path,
        "reference_record_sha256": reference_sha,
        "h15_p5_baseline_record_path": baseline_path,
        "h15_p5_baseline_record_sha256": baseline_sha,
        "source": _comparison_source(),
    }


def test_y_only_control_positive_remains_diagnostic_only(
    tmp_path: Path,
) -> None:
    result = build_y_directional_control_comparison(
        **_authorities(tmp_path, candidate_offset=0.0)
    )
    signal = result["directional_signal"]
    assert result["qualification"]["pass"] is True
    assert result["classification"] == "positive"
    assert result["diagnostic_only"] is True
    assert result["formal_candidate_eligible"] is False
    assert result["thresholds_relaxed"] is False
    assert signal["seed_power_pass_count"] == 0
    assert signal["seed_complex_amplitude_pass_count"] == 0
    assert signal["candidate_power_pass_count"] == 12
    assert signal["candidate_complex_amplitude_pass_count"] == 12
    assert signal["all_12_normalized_power_l2"]["candidate"] == 0.0
    assert result["mesh_directional_identity"]["changed_axes"] == ["y"]


def test_watchdog_projects_ordinary_default_identity_from_raw_result() -> None:
    assert _watchdog_ordinary_default_identity(
        {"ordinary_default_changed": False}
    ) == {"ordinary_default_changed": False}
    assert _watchdog_ordinary_default_identity({}) == {
        "ordinary_default_changed": None
    }


def test_y_only_control_without_improvement_is_controlled_negative(
    tmp_path: Path,
) -> None:
    result = build_y_directional_control_comparison(
        **_authorities(tmp_path, candidate_offset=2.0e-4)
    )
    signal = result["directional_signal"]
    assert result["classification"] == "controlled_negative"
    assert signal["positive_signal"] is False
    assert signal["count_improved"] is False
    assert signal["all_12_normalized_power_l2"]["relative_reduction"] == 0.0
    assert result["formal_candidate_eligible"] is False


@pytest.mark.parametrize(
    ("field", "value", "change_both"),
    (
        (
            "candidate_vs_reference_power_absolute_error",
            float("nan"),
            False,
        ),
        (
            "candidate_vs_reference_amplitude_absolute_error",
            float("inf"),
            False,
        ),
        ("unchanged_v0_power_tolerance", 0.0, True),
        ("unchanged_v0_complex_amplitude_tolerance", 0.0, True),
        (
            "candidate_vs_reference_power_absolute_error",
            1.0e308,
            False,
        ),
    ),
)
def test_directional_signal_rejects_nonfinite_or_zero_numeric_authority(
    tmp_path: Path,
    field: str,
    value: float,
    change_both: bool,
) -> None:
    result = build_y_directional_control_comparison(
        **_authorities(tmp_path, candidate_offset=0.0)
    )
    seed = copy.deepcopy(
        result["seed_significant_channel_comparison"]
    )
    candidate = copy.deepcopy(
        result["candidate_significant_channel_comparison"]
    )
    candidate["channels"][0][field] = value
    if change_both:
        seed["channels"][0][field] = value
    if value == 1.0e308:
        seed["channels"][0][
            "unchanged_v0_power_tolerance"
        ] = 1.0e-308
        candidate["channels"][0][
            "unchanged_v0_power_tolerance"
        ] = 1.0e-308
    with pytest.raises(
        ValueError,
        match="non-finite|tolerances differ",
    ):
        _directional_signal(seed, candidate)


def test_y_only_control_rejects_sha_and_residual_tampering(
    tmp_path: Path,
) -> None:
    authorities = _authorities(tmp_path, candidate_offset=0.0)
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        build_y_directional_control_comparison(
            **{
                **authorities,
                "y_control_record_sha256": "0" * 64,
            }
        )

    y_path = authorities["y_control_record_path"]
    y_record = json.loads(y_path.read_text(encoding="utf-8"))
    y_record["enriched"]["cell_static_condensation"][
        "full_explicit_true_residual"
    ]["linear_system_relative_residual"] = 2.0e-8
    authorities["y_control_record_sha256"] = _write_json(
        y_path,
        y_record,
    )
    with pytest.raises(ValueError, match="true residual exceeds"):
        build_y_directional_control_comparison(**authorities)


def test_y_only_control_rejects_unbound_orders_and_identity_tampering(
    tmp_path: Path,
) -> None:
    authorities = _authorities(tmp_path, candidate_offset=0.0)
    y_path = authorities["y_control_record_path"]
    y_record = json.loads(y_path.read_text(encoding="utf-8"))
    orders_path = Path(
        y_record["raw_evidence"]["structured_axis_enriched_orders"]
    )
    payload = json.loads(orders_path.read_text(encoding="utf-8"))
    payload["orders"][0]["power_ratio"] += 0.25
    _write_json(orders_path, payload)
    with pytest.raises(ValueError, match="not SHA-bound"):
        build_y_directional_control_comparison(**authorities)

    new_orders_sha = _sha256(orders_path)
    y_record["raw_evidence"][
        "structured_axis_enriched_orders_sha256"
    ] = new_orders_sha
    authorities["y_control_record_sha256"] = _write_json(
        y_path,
        y_record,
    )
    payload["orders"][0]["boundary_phase"] = [0.5, 0.0]
    new_orders_sha = _write_json(orders_path, payload)
    y_record["raw_evidence"][
        "structured_axis_enriched_orders_sha256"
    ] = new_orders_sha
    authorities["y_control_record_sha256"] = _write_json(
        y_path,
        y_record,
    )
    with pytest.raises(
        ValueError,
        match="candidate significant-channel comparison identity failed",
    ):
        build_y_directional_control_comparison(**authorities)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        (
            "structured_axis_control_classification",
            {
                "role": "y_only_global_p5_directional_control",
                "diagnostic_only": False,
                "formal_candidate_eligible": True,
                "reference_v1_gate_evaluated_in_this_record": False,
                "required_followup": (
                    "SHA-bound frozen-reference-v1 channel comparator"
                ),
                "thresholds_relaxed": True,
            },
        ),
    ),
)
def test_y_only_control_rejects_unsafe_watchdog_classification(
    tmp_path: Path,
    field: str,
    value: Any,
) -> None:
    authorities = _authorities(tmp_path, candidate_offset=0.0)
    y_path = authorities["y_control_record_path"]
    record = json.loads(y_path.read_text(encoding="utf-8"))
    record[field] = value
    authorities["y_control_record_sha256"] = _write_json(
        y_path,
        record,
    )
    with pytest.raises(ValueError, match="diagnostic-only contract"):
        build_y_directional_control_comparison(**authorities)


def test_y_only_control_requires_three_way_ordinary_default_closure(
    tmp_path: Path,
) -> None:
    authorities = _authorities(tmp_path, candidate_offset=0.0)
    y_path = authorities["y_control_record_path"]
    record = json.loads(y_path.read_text(encoding="utf-8"))
    record.pop("ordinary_default_changed")
    authorities["y_control_record_sha256"] = _write_json(y_path, record)
    with pytest.raises(ValueError, match="ordinary-default identity"):
        build_y_directional_control_comparison(**authorities)

    authorities = _authorities(
        tmp_path / "qualification",
        candidate_offset=0.0,
    )
    y_path = authorities["y_control_record_path"]
    record = json.loads(y_path.read_text(encoding="utf-8"))
    record["qualification"]["checks"][
        "ordinary_default_unchanged"
    ] = False
    authorities["y_control_record_sha256"] = _write_json(y_path, record)
    with pytest.raises(ValueError, match="qualification is not a complete"):
        build_y_directional_control_comparison(**authorities)

    authorities = _authorities(
        tmp_path / "raw",
        candidate_offset=0.0,
    )
    y_path = authorities["y_control_record_path"]
    record = json.loads(y_path.read_text(encoding="utf-8"))
    raw_path = Path(record["raw_evidence"]["actual_r5_result"])
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    raw["ordinary_default_changed"] = True
    record["raw_evidence"]["actual_r5_result_sha256"] = _write_json(
        raw_path,
        raw,
    )
    authorities["y_control_record_sha256"] = _write_json(y_path, record)
    with pytest.raises(ValueError, match="ordinary-default identity"):
        build_y_directional_control_comparison(**authorities)


@pytest.mark.parametrize(
    "source",
    (
        {},
        {
            **_comparison_source(),
            "verified_clean_sha": "c" * 40,
        },
        {
            **_comparison_source(),
            "branch": "wrong",
        },
        {
            **_comparison_source(),
            "stable_and_clean_after": False,
        },
    ),
)
def test_y_only_control_rejects_missing_or_tampered_comparator_source(
    tmp_path: Path,
    source: dict[str, Any],
) -> None:
    authorities = _authorities(tmp_path, candidate_offset=0.0)
    authorities["source"] = source
    with pytest.raises(ValueError, match="source identity"):
        build_y_directional_control_comparison(**authorities)


def test_source_gate_rejects_wrong_sha_dirty_tree_and_postbuild_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    head = "d" * 40

    def clean_git(_root: Path, *args: str) -> str:
        if args == ("rev-parse", "HEAD"):
            return head
        if args == ("branch", "--show-current"):
            return EXPECTED_BRANCH
        if args[:2] == ("status", "--short"):
            return ""
        raise AssertionError(args)

    monkeypatch.setattr(y_control_module, "_git", clean_git)
    with pytest.raises(SystemExit, match="head_matches_verified_sha"):
        _verified_source_identity(tmp_path, "e" * 40)

    def dirty_git(_root: Path, *args: str) -> str:
        if args[:2] == ("status", "--short"):
            return " M benchmarks/task035b_y_directional_control.py"
        return clean_git(_root, *args)

    monkeypatch.setattr(y_control_module, "_git", dirty_git)
    with pytest.raises(
        SystemExit,
        match="tracked_and_untracked_worktree_clean",
    ):
        _verified_source_identity(tmp_path, head)

    source = _comparison_source()

    def drift_git(_root: Path, *args: str) -> str:
        if args == ("rev-parse", "HEAD"):
            return "f" * 40
        if args == ("branch", "--show-current"):
            return EXPECTED_BRANCH
        if args[:2] == ("status", "--short"):
            return ""
        raise AssertionError(args)

    monkeypatch.setattr(y_control_module, "_git", drift_git)
    with pytest.raises(SystemExit, match="head_stable_after_build"):
        _reverify_source_before_write(tmp_path, source)


def test_y_only_control_main_refuses_to_overwrite_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorities = _authorities(tmp_path, candidate_offset=0.0)
    output = tmp_path / "comparison.json"
    source = _comparison_source()
    source_before = {
        key: value
        for key, value in source.items()
        if key
        not in {
            "head_after_sha",
            "branch_after",
            "status_after_before_record_write",
            "stable_and_clean_after",
        }
    }
    source_before["checks"] = {"fixture_source_before": True}
    source_after = {
        "head_after_sha": source["head_after_sha"],
        "branch_after": source["branch_after"],
        "status_after_before_record_write": "",
        "stable_and_clean_after": True,
        "checks": {"fixture_source_after": True},
    }
    monkeypatch.setattr(
        y_control_module,
        "_verified_source_identity",
        lambda _root, _sha: source_before,
    )
    monkeypatch.setattr(
        y_control_module,
        "_reverify_source_before_write",
        lambda _root, _source: source_after,
    )
    argv = [
        "--repo-root",
        str(tmp_path),
        "--verified-clean-sha",
        source["verified_clean_sha"],
        "--y-control-record",
        str(authorities["y_control_record_path"]),
        "--y-control-record-sha256",
        authorities["y_control_record_sha256"],
        "--reference-record",
        str(authorities["reference_record_path"]),
        "--reference-record-sha256",
        authorities["reference_record_sha256"],
        "--h15-p5-baseline-record",
        str(authorities["h15_p5_baseline_record_path"]),
        "--h15-p5-baseline-record-sha256",
        authorities["h15_p5_baseline_record_sha256"],
        "--output",
        str(output),
    ]
    assert main(argv) == 0
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["source"]["stable_and_clean_after"] is True
    assert written["qualification"]["checks"][
        "comparator_source_identity_hash_bound"
    ] is True
    assert set(written["source_file_sha256"]) == {
        "benchmarks/task035b_y_directional_control.py",
        "src/adaptivity/high_order_same_error.py",
    }
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        main(argv)
