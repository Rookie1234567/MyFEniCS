"""Tests for the future global-p6/h14 trace discriminator."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import benchmarks.task035b_global_p6_h14_trace_discriminator as module
from benchmarks.task035b_global_p6_h14_trace_discriminator import (
    EXPECTED_BRANCH,
    _qualified_output_source,
    _validate_postprocess_authorities_against_manifest,
    _validate_solve_artifact_manifest,
    build_global_p6_h14_trace_discriminator,
    main,
)
from benchmarks.run_task035_actual_r5 import (
    _global_pair_solve_artifact_manifest,
)


def _source() -> dict[str, Any]:
    sha = "a" * 40
    return {
        "commit_sha": sha,
        "verified_clean_sha": sha,
        "tracked_source_dirty": False,
        "head_after_sha": sha,
        "status_after_before_record_write": "",
        "stable_and_clean_after": True,
    }


def _qualification() -> dict[str, Any]:
    requested = {
        name: True
        for name in (
            "requested_static_condensation_active",
            "requested_condensed_rows_physically_measured",
            "requested_full_residual_audit_present",
            "requested_floquet_slave_elimination_active",
            "requested_floquet_slave_rows_physically_removed",
            "requested_assembly_time_condensation_active",
            "requested_full_matrices_never_allocated",
            "requested_matrix_free_full_residual_present",
            "requested_global_pair_solve_artifacts_hash_bound",
        )
    }
    return {
        "pass": True,
        "checks": {"fixture": True, **requested},
        "failures": [],
    }


def _mesh() -> dict[str, Any]:
    return {
        "schema_version": "task035b.partition-independent-linear-mesh.v1",
        "mesh_cell_type": "hexahedron",
        "global_cell_count": 132,
        "mesh_cells_resolved": [6, 2, 11],
        "partition_independent_mesh_sha256": "1" * 64,
        "cell_tag_sha256": "2" * 64,
        "facet_tag_sha256": "3" * 64,
        "material_plane_alignment": {"all_aligned": True},
    }


def _result(
    degree: int,
    dofs: int,
    *,
    trace_degree: int,
    interior_degree: int,
    rows: int,
    nnz: int,
    factor_nnz: int,
) -> dict[str, Any]:
    residual = 2.0e-12
    return {
        "degree": degree,
        "h_nm": 14.0,
        "case_status": "completed",
        "official_result": True,
        "mpi_size": 8,
        "num_mesh_cells": 132,
        "mesh_cell_type_actual": "hexahedron",
        "num_nedelec_dofs": dofs,
        "nedelec_trace_degree_resolved": trace_degree,
        "nedelec_interior_degree_resolved": interior_degree,
        "linear_system_relative_residual": residual,
        "R00_total": 0.1,
        "R_total": 0.2,
        "T_total": 0.7,
        "stage4_dtn_floquet_independent_matrix_stats": {
            "matrix_rows": rows,
            "matrix_nnz_used": nnz,
        },
        "stage4_dtn_factor_inventory": {
            "available": True,
            "matrix_stats": {"matrix_nnz_used": factor_nnz},
        },
        "stage4_cell_static_condensation": True,
        "stage4_assembly_time_cell_static_condensation": True,
        "stage4_floquet_slave_elimination": True,
        "cell_static_condensation": {
            "matrix_rows": rows,
            "full_global_matrix_allocated": False,
            "full_trace_matrix_allocated": False,
            "embedded_mpc_slave_identity_rows_allocated": False,
            "floquet_slave_elimination": {
                "constraint_applied_before_global_matrix_insertion": True,
                "embedded_identity_slave_rows_allocated": False,
            },
            "full_explicit_true_residual": {
                "linear_system_relative_residual": residual,
            },
        },
        "high_order_resource_audit": {"mesh_identity": _mesh()},
    }


def _global_record() -> dict[str, Any]:
    return {
        "schema_version": "task035.actual-global-r5-watchdog.v1",
        "status": "actual_global_r5_pass",
        "source": _source(),
        "qualification": _qualification(),
        "terminated_for_memory": False,
        "terminated_for_timeout": False,
        "target_identity": dict(module._FIXED_TARGET_IDENTITY),
        "common_mesh_identity": _mesh(),
        "coarse": _result(
            5,
            54595,
            trace_degree=5,
            interior_degree=5,
            rows=18500,
            nnz=9_500_000,
            factor_nnz=30_000_000,
        ),
        "enriched": _result(
            6,
            92850,
            trace_degree=6,
            interior_degree=6,
            rows=27080,
            nnz=14_000_000,
            factor_nnz=45_000_000,
        ),
        "same_mesh_hashes": True,
        "single_in_memory_mesh_instance": True,
        "reuse_single_mesh_requested": True,
        "resource_authority": {
            "memory_authority_gib": 8.0,
            "stage_peaks": [
                {
                    "stage": "actual_r5_enriched_solve",
                    "max_mpi_process_tree_rss_mb": 7680.0,
                }
            ],
        },
    }


def _channel_rows(*, passed: bool) -> list[dict[str, Any]]:
    rows = []
    for index in range(12):
        side = "bottom" if index < 6 else "top"
        m = index if index < 6 else index - 6
        rows.append(
            {
                "side": side,
                "m": m,
                "n": 0,
                "polarization": "s",
                "analytic_identity_pass": True,
                "candidate_vs_reference_power_absolute_error": (
                    0.5 if passed else 2.0
                ),
                "unchanged_v0_power_tolerance": 1.0,
                "power_pass": passed,
                "candidate_vs_reference_amplitude_absolute_error": (
                    0.5 if passed else 2.0
                ),
                "unchanged_v0_complex_amplitude_tolerance": 1.0,
                "complex_amplitude_pass": passed,
            }
        )
    return rows


def _channel_comparison(*, passed: bool) -> dict[str, Any]:
    return {
        "schema_version": (
            "task035b.significant-channel-reference-v1-comparison.v1"
        ),
        "frozen_significant_channel_count": 12,
        "significant_power_pass_count": 12 if passed else 0,
        "significant_complex_amplitude_pass_count": 12 if passed else 0,
        "all_12_significant_powers_pass": passed,
        "all_12_significant_complex_amplitudes_pass": passed,
        "analytic_channel_identity_pass": True,
        "thresholds_relaxed": False,
        "candidate_authority": {"sha256": "4" * 64},
        "channels": _channel_rows(passed=passed),
        "pass": passed,
    }


def _scalar_comparison(error: float) -> dict[str, Any]:
    rows = {
        name: {"normalized_error": error, "pass": error <= 1.0}
        for name in ("R00_total", "R_total", "T_total", "A_closure")
    }
    return {
        "schema_version": "task035b.cross-mesh-observable-comparison.v1",
        "observables": rows,
        "normalized_R_T_Aclosure_l2": error,
        "pass": error <= 1.0,
    }


def _field_comparison(error: float) -> dict[str, Any]:
    selections = {
        name: {
            "candidate_vs_p6_weighted_relative_l2": error,
            "candidate_vs_p6_max_pointwise_absolute_error": 2.0 * error,
            "pass": error <= 1.0,
        }
        for name in ("volume", "interface")
    }
    return {
        "schema_version": "task035b.cross-mesh-field-comparison.v1",
        "no_threshold_relaxation": True,
        "selections": selections,
        "pass": error <= 1.0,
    }


def _fixed_record() -> dict[str, Any]:
    return {
        "schema_version": "task035b.fixed-trace-watchdog.v1",
        "status": "actual_fixed_trace_controlled_negative",
        "source": _source(),
        "qualification": _qualification(),
        "terminated_for_memory": False,
        "terminated_for_timeout": False,
        "candidate": _result(
            6,
            82315,
            trace_degree=5,
            interior_degree=6,
            rows=18500,
            nnz=10_104_512,
            factor_nnz=31_347_000,
        ),
        "diffraction_channel_comparison": {
            **_channel_comparison(passed=False),
            "significant_power_pass_count": 7,
            "significant_complex_amplitude_pass_count": 9,
        },
        "observable_comparison": _scalar_comparison(0.5),
        "selected_field_interface_error_gate": _field_comparison(0.5),
        "resource_authority": {
            "memory_authority_gib": 6.4,
            "stage_peaks": [
                {
                    "stage": "fixed_trace_candidate_solve",
                    "max_mpi_process_tree_rss_mb": 6400.0,
                }
            ],
        },
    }


def _control_record() -> dict[str, Any]:
    record = _global_record()
    record["coarse"]["h_nm"] = 10.0
    record["enriched"]["h_nm"] = 10.0
    return record


def _reference() -> dict[str, Any]:
    return {
        "schema_version": "task035b.significant-channel-reference.v1",
        "status": "significant_channel_reference_v1_frozen",
        "pass": True,
        "mechanical_validation_pass": True,
    }


def _candidate_summary(global_record: dict[str, Any]) -> dict[str, Any]:
    summary = copy.deepcopy(global_record["enriched"])
    summary["nedelec_degree"] = 6
    summary["mesh_cells_resolved"] = [6, 2, 11]
    summary["mesh_material_plane_alignment"] = {"all_aligned": True}
    summary.pop("high_order_resource_audit")
    return summary


def _raw_authorities() -> dict[str, Any]:
    return {
        "enriched_p6_summary": {"sha256": "5" * 64},
        "enriched_p6_orders": {"sha256": "4" * 64},
        "enriched_p6_fields": {
            "shard_count": 8,
            "manifest_sha256": "6" * 64,
        },
        "watchdog_manifest_alignment": {
            "pass": True,
            "reverified_after_all_postprocess_reads": True,
            "checks": {
                "summary_path_size_sha_match_watchdog_manifest": True,
                "orders_path_size_sha_match_watchdog_manifest": True,
                "eight_field_path_size_sha_rows_match_watchdog_manifest": True,
            },
        },
    }


def _build(*, channels_pass: bool = True):
    global_record = _global_record()
    return build_global_p6_h14_trace_discriminator(
        global_record=global_record,
        global_authority={"sha256": "7" * 64},
        reference_record=_reference(),
        reference_authority={"sha256": "8" * 64},
        fixed_record=_fixed_record(),
        fixed_authority={"sha256": "9" * 64},
        control_record=_control_record(),
        control_authority={"sha256": "a" * 64},
        candidate_summary=_candidate_summary(global_record),
        raw_authorities=_raw_authorities(),
        scalar_comparison=_scalar_comparison(0.25),
        channel_comparison=_channel_comparison(passed=channels_pass),
        field_comparison=_field_comparison(0.25),
    )


def test_all_12_channels_support_only_future_selective_trace():
    evidence = _build(channels_pass=True)
    assert evidence["status"] == (
        "positive_global_p6_h14_trace_physics_signal"
    )
    assert evidence["selective_trace_lane_physically_supported"] is True
    assert evidence["diagnostic_only"] is True
    assert evidence["formal_candidate_eligible"] is False
    assert evidence["decision"]["global_p6_h14_is_candidate"] is False
    assert evidence["decision"]["over_limit_by"] == 2850
    resources = evidence[
        "trace_only_marginal_on_identical_h14_mesh"
    ]["resources"]
    assert resources["marginal"]["full3d_equivalent_dofs"][
        "absolute_delta"
    ] == 10535.0
    assert resources["global_p6_h14_within_limit"] is False
    assert evidence["execution_contract"]["pde_solve_count"] == 0


def test_any_channel_failure_is_controlled_negative():
    evidence = _build(channels_pass=False)
    assert evidence["status"] == (
        "controlled_negative_global_p6_h14_trace_discriminator"
    )
    assert evidence["selective_trace_lane_physically_supported"] is False
    assert evidence["pass"] is True


@pytest.mark.parametrize("failed_gate", ["scalar", "field"])
def test_trace_signal_requires_all_same_error_gates(failed_gate: str):
    global_record = _global_record()
    kwargs = {
        "global_record": global_record,
        "global_authority": {"sha256": "7" * 64},
        "reference_record": _reference(),
        "reference_authority": {"sha256": "8" * 64},
        "fixed_record": _fixed_record(),
        "fixed_authority": {"sha256": "9" * 64},
        "control_record": _control_record(),
        "control_authority": {"sha256": "a" * 64},
        "candidate_summary": _candidate_summary(global_record),
        "raw_authorities": _raw_authorities(),
        "scalar_comparison": _scalar_comparison(
            2.0 if failed_gate == "scalar" else 0.25
        ),
        "channel_comparison": _channel_comparison(passed=True),
        "field_comparison": _field_comparison(
            2.0 if failed_gate == "field" else 0.25
        ),
    }
    evidence = build_global_p6_h14_trace_discriminator(**kwargs)
    assert evidence["status"] == (
        "controlled_negative_global_p6_h14_trace_discriminator"
    )
    assert evidence["selective_trace_lane_physically_supported"] is False


def test_watchdog_manifest_hash_binds_realistic_raw_layout(tmp_path: Path):
    run_dir = tmp_path / "raw"
    result: dict[str, Any] = {}
    for result_key, level_name in (
        ("coarse", "coarse_p5"),
        ("enriched", "enriched_p6"),
    ):
        directory = run_dir / level_name
        directory.mkdir(parents=True)
        summary = {
            "dtn_port_orders_json": (
                "dtn_port_diffraction_orders_3d.json"
            ),
            "level": level_name,
        }
        (directory / "run_summary.json").write_text(
            json.dumps(summary),
            encoding="utf-8",
        )
        (directory / "dtn_port_diffraction_orders_3d.json").write_text(
            json.dumps(
                {"orders": [{"index": index} for index in range(80)]}
            ),
            encoding="utf-8",
        )
        for rank in range(8):
            (directory / f"fields_3d_for_paraview_rank{rank:04d}.vtu").write_text(
                f"rank={rank}",
                encoding="utf-8",
            )
        result[result_key] = {"summary": summary}
    manifest = _global_pair_solve_artifact_manifest(
        run_dir=run_dir,
        result=result,
        coarse_degree=5,
        enriched_degree=6,
        mpi_size=8,
    )
    assert manifest["pass"] is True
    record = {
        "raw_evidence": {
            "global_pair_solve_artifact_manifest": manifest,
        }
    }
    verified = _validate_solve_artifact_manifest(
        module.ROOT,
        record,
        run_dir,
    )
    assert verified["files_manifest_sha256"] == (
        manifest["files_manifest_sha256"]
    )
    enriched = manifest["levels"]["enriched_p6"]
    authorities = {
        "enriched_p6_summary": dict(enriched["run_summary"]),
        "enriched_p6_orders": dict(enriched["dtn_port_orders"]),
        "enriched_p6_fields": {
            "shard_count": 8,
            "shards": [
                dict(row)
                for row in enriched["field_shards"]["shards"]
            ],
        },
    }
    alignment = _validate_postprocess_authorities_against_manifest(
        module.ROOT,
        manifest,
        authorities,
    )
    assert alignment["pass"] is True
    authorities["enriched_p6_orders"]["sha256"] = "0" * 64
    with pytest.raises(
        ValueError,
        match="postprocess authorities differ",
    ):
        _validate_postprocess_authorities_against_manifest(
            module.ROOT,
            manifest,
            authorities,
        )
    shard = run_dir / "enriched_p6/fields_3d_for_paraview_rank0007.vtu"
    shard.write_text("mutated", encoding="utf-8")
    with pytest.raises(ValueError, match="differs from the watchdog"):
        _validate_solve_artifact_manifest(
            module.ROOT,
            record,
            run_dir,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda record: record["enriched"].__setitem__(
                "num_nedelec_dofs",
                92849,
            ),
            "global_h14_p6 formal identity is invalid",
        ),
        (
            lambda record: record["common_mesh_identity"].__setitem__(
                "mesh_cells_resolved",
                [6, 2, 10],
            ),
            "exact \\(6,2,11\\)",
        ),
    ],
)
def test_formal_h14_identity_fails_closed(mutation, message):
    global_record = _global_record()
    mutation(global_record)
    with pytest.raises(ValueError, match=message):
        build_global_p6_h14_trace_discriminator(
            global_record=global_record,
            global_authority={"sha256": "7" * 64},
            reference_record=_reference(),
            reference_authority={"sha256": "8" * 64},
            fixed_record=_fixed_record(),
            fixed_authority={"sha256": "9" * 64},
            control_record=_control_record(),
            control_authority={"sha256": "a" * 64},
            candidate_summary=_candidate_summary(_global_record()),
            raw_authorities=_raw_authorities(),
            scalar_comparison=_scalar_comparison(0.25),
            channel_comparison=_channel_comparison(passed=True),
            field_comparison=_field_comparison(0.25),
        )


def test_nonfinite_trace_resource_fails_closed():
    global_record = _global_record()
    global_record["enriched"][
        "stage4_dtn_floquet_independent_matrix_stats"
    ]["matrix_nnz_used"] = float("nan")
    summary = _candidate_summary(global_record)
    with pytest.raises(ValueError, match="matrix_nnz_used must be finite"):
        build_global_p6_h14_trace_discriminator(
            global_record=global_record,
            global_authority={"sha256": "7" * 64},
            reference_record=_reference(),
            reference_authority={"sha256": "8" * 64},
            fixed_record=_fixed_record(),
            fixed_authority={"sha256": "9" * 64},
            control_record=_control_record(),
            control_authority={"sha256": "a" * 64},
            candidate_summary=summary,
            raw_authorities=_raw_authorities(),
            scalar_comparison=_scalar_comparison(0.25),
            channel_comparison=_channel_comparison(passed=True),
            field_comparison=_field_comparison(0.25),
        )


def test_output_source_requires_stable_hash_bound_branch():
    sha = "b" * 40
    source = {
        "commit_sha": sha,
        "verified_clean_sha": sha,
        "branch": EXPECTED_BRANCH,
        "tracked_source_dirty": False,
        "stable_and_clean_before": True,
        "head_after_sha": sha,
        "branch_after": EXPECTED_BRANCH,
        "status_after_before_record_write": "",
        "stable_and_clean_after": True,
        "checks": {"before": True, "after": True},
    }
    assert _qualified_output_source(source)["commit_sha"] == sha
    source["branch_after"] = "master"
    with pytest.raises(ValueError, match="source identity"):
        _qualified_output_source(source)


def test_cli_output_is_exclusive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    sha = "c" * 40
    source_before = {
        "commit_sha": sha,
        "verified_clean_sha": sha,
        "branch": EXPECTED_BRANCH,
        "tracked_source_dirty": False,
        "stable_and_clean_before": True,
        "status_before": "",
        "checks": {"before": True},
    }
    source_after = {
        "head_after_sha": sha,
        "branch_after": EXPECTED_BRANCH,
        "status_after_before_record_write": "",
        "stable_and_clean_after": True,
        "checks": {"after": True},
    }
    monkeypatch.setattr(
        module,
        "_verified_source_identity",
        lambda _root, _sha: dict(source_before),
    )
    monkeypatch.setattr(
        module,
        "_environment_identity",
        lambda _root: {"checks": {"fixture": True}},
    )
    monkeypatch.setattr(
        module,
        "_source_file_sha256",
        lambda _root: {"source": "d" * 64},
    )
    monkeypatch.setattr(
        module,
        "_reverify_after_build",
        lambda _root, _source, _hashes: (
            dict(source_after),
            {"source": "d" * 64},
        ),
    )
    monkeypatch.setattr(
        module,
        "_formal_analysis",
        lambda **_kwargs: _build(channels_pass=True),
    )
    output = tmp_path / "trace.json"
    arguments = [
        "--verified-clean-sha",
        sha,
        "--global-h14-record",
        str(tmp_path / "future.json"),
        "--global-h14-record-sha256",
        "e" * 64,
        "--output",
        str(output),
    ]
    assert main(arguments) == 0
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        main(arguments)
    assert hashlib.sha256(output.read_bytes()).hexdigest() == digest
