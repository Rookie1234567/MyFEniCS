"""Focused contracts for the opt-in h13 direct setup profiler."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.run_task035b_direct_setup_profile import (
    _classify_profile,
    _default_run_directory,
    _direct_config,
    _dry_run_plan,
    _parse_args,
    _profile_contract,
    _profile_request,
)
from src.common.config_3d import target_stage4_config
from src.geometry.mesh_builder_3d import stage4_axis_plan


SOURCE_SHA = "a" * 40


def _topology_evidence(h_nm: float) -> dict[str, object]:
    profile = _profile_contract(h_nm, source_sha=SOURCE_SHA)
    return {
        "worker_h_nm": h_nm,
        "worker_profile_identity": profile,
        "mesh_target_size": h_nm,
        "mesh_cell_type": "hexahedron",
        "mesh_cells_resolved": profile["mesh_cells_resolved"],
        "num_mesh_cells": profile["num_mesh_cells"],
        "full3d_equivalent_dofs": profile["full3d_equivalent_dofs"],
        "active_rows_with_dtn": profile["active_rows_with_dtn"],
        "mpi_size": 8,
        "configuration_identity": {
            "case_name": (
                "task035b_direct_setup_fixed_p5trace_p6interior_"
                f"h{h_nm:g}_cold"
            ),
            "mesh_target_size": h_nm,
            "trace_degree": 5,
            "interior_degree": 6,
        },
    }


def _classify_topology(
    evidence: dict[str, object],
    *,
    expected_h_nm: float,
) -> dict[str, object]:
    return _classify_profile(
        evidence,
        {"observed_worker_rank_count": 8},
        cache_state="cold",
        source_sha=SOURCE_SHA,
        expected_mpi_size=8,
        return_code=0,
        terminated_for_memory=False,
        terminated_for_timeout=False,
        telemetry_readable=True,
        source_stable_and_clean_after=True,
        expected_h_nm=expected_h_nm,
    )


def test_parse_keeps_h15_rank_study_and_restricts_h13_to_mpi8() -> None:
    for mpi_size in (1, 2, 4, 8):
        args = _parse_args(
            ["--h-nm", "15", "--mpi-size", str(mpi_size)]
        )
        assert args.h_nm == 15.0
        assert args.mpi_size == mpi_size

    h13 = _parse_args(["--h-nm", "13", "--mpi-size", "8"])
    assert h13.h_nm == 13.0
    assert h13.mpi_size == 8

    for mpi_size in (1, 2, 4):
        with pytest.raises(SystemExit):
            _parse_args(
                ["--h-nm", "13", "--mpi-size", str(mpi_size)]
            )
    with pytest.raises(SystemExit):
        _parse_args(["--h-nm", "14", "--mpi-size", "8"])


def test_h13_dry_plan_run_directory_and_request_are_sha_bound(
    tmp_path: Path,
) -> None:
    args = _parse_args(
        [
            "--h-nm",
            "13",
            "--mpi-size",
            "8",
            "--artifact-root",
            str(tmp_path),
        ]
    )
    plan = _dry_run_plan(args, source_sha=SOURCE_SHA)
    profile = plan["profile_identity"]
    assert plan["h_nm"] == 13.0
    assert plan["rank_study"] == [8]
    assert plan["source_sha"] == SOURCE_SHA
    assert plan["source_sha_bound"] is True
    assert profile["profile_slug"] == "h13_directional_z"
    assert profile["mesh_cells_resolved"] == [6, 2, 12]
    assert profile["num_mesh_cells"] == 144
    assert profile["full3d_equivalent_dofs"] == 89740
    assert profile["active_rows_with_dtn"] == 20120
    assert profile["source_sha"] == SOURCE_SHA
    assert profile["source_sha_bound"] is True
    assert "h13_directional_z" in plan["cache_directory"]
    assert SOURCE_SHA in plan["cache_directory"]

    run_dir = _default_run_directory(
        tmp_path,
        profile_identity=profile,
        cache_state="cold",
        mpi_size=8,
        timestamp="20260725T000000Z",
    )
    assert "h13_directional_z" in run_dir.name
    assert f"mpi8_{SOURCE_SHA}_" in run_dir.name

    request = _profile_request(
        profile_identity=profile,
        mpi_size=8,
        cache_state="cold",
        cache_directory=tmp_path / "cache",
        canonical_orientation_class_reuse=True,
    )
    assert request["h_nm"] == 13.0
    assert request["profile_identity"] == profile
    assert request["source_sha"] == SOURCE_SHA
    assert request["source_sha_bound"] is True
    assert request["mpi_size"] == 8
    with pytest.raises(ValueError):
        _default_run_directory(
            tmp_path,
            profile_identity=profile,
            cache_state="cold",
            mpi_size=4,
            timestamp="20260725T000000Z",
        )


def test_h13_direct_config_resolves_exact_directional_z_axis() -> None:
    ordinary = target_stage4_config(degree=6, h_nm=13.0)
    assert ordinary.stage4_assembly_time_cell_static_condensation is False
    assert ordinary.stage4_fast_fixed_trace_setup is False

    cfg = _direct_config(
        source_sha=SOURCE_SHA,
        cache_directory=Path("/tmp/task035b-h13-unused-cache"),
        cache_state="cold",
        h_nm=13.0,
        canonical_orientation_class_reuse=True,
    )
    axis = stage4_axis_plan(cfg, comm_size=8)
    assert cfg.case_name == (
        "task035b_direct_setup_fixed_p5trace_p6interior_h13_cold"
    )
    assert cfg.mesh_target_size == 13.0
    assert cfg.mesh_axis_cell_counts is None
    assert axis.mesh_spacing_mode_resolved == "boundary_fitted"
    assert axis.mesh_cells_resolved == (6, 2, 12)
    assert axis.material_plane_alignment["all_aligned"] is True
    assert cfg.nedelec_trace_degree_resolved == 5
    assert cfg.nedelec_interior_degree_resolved == 6
    assert cfg.stage4_assembly_time_cell_static_condensation is True
    assert cfg.stage4_fast_fixed_trace_setup is True
    assert cfg.stage4_canonical_orientation_class_reuse is True


def test_classifier_fails_closed_across_h13_and_h15_topologies() -> None:
    h13 = _classify_topology(
        _topology_evidence(13.0),
        expected_h_nm=13.0,
    )
    assert h13["checks"]["fixed_rectangular_hexa_h13"] is True
    assert h13["checks"]["expected_h_identity_if_reported"] is True
    assert h13["checks"]["worker_profile_identity_if_reported"] is True
    assert h13["checks"]["full3d_equivalent_dof_identity"] is True
    assert h13["checks"]["active_row_identity"] is True

    h13_as_h15 = _classify_topology(
        _topology_evidence(13.0),
        expected_h_nm=15.0,
    )
    assert h13_as_h15["checks"]["fixed_rectangular_hexa_h15"] is False
    assert (
        h13_as_h15["checks"]["expected_h_identity_if_reported"]
        is False
    )
    assert (
        h13_as_h15["checks"]["worker_profile_identity_if_reported"]
        is False
    )
    assert (
        h13_as_h15["checks"]["full3d_equivalent_dof_identity"]
        is False
    )
    assert h13_as_h15["checks"]["active_row_identity"] is False

    h15_as_h13 = _classify_topology(
        _topology_evidence(15.0),
        expected_h_nm=13.0,
    )
    assert h15_as_h13["checks"]["fixed_rectangular_hexa_h13"] is False
    assert (
        h15_as_h13["checks"]["expected_h_identity_if_reported"]
        is False
    )
    assert h15_as_h13["formal_profile_pass"] is False


def test_h15_default_classifier_and_plan_contract_are_unchanged(
    tmp_path: Path,
) -> None:
    args = _parse_args(
        [
            "--h-nm",
            "15",
            "--mpi-size",
            "1",
            "--artifact-root",
            str(tmp_path),
        ]
    )
    plan = _dry_run_plan(args, source_sha=SOURCE_SHA)
    assert plan["h_nm"] == 15.0
    assert plan["rank_study"] == [1, 2, 4, 8]
    assert plan["profile_identity"]["profile_slug"] == "h15"
    assert plan["profile_identity"]["mesh_cells_resolved"] == [6, 2, 10]

    result = _classify_profile(
        _topology_evidence(15.0),
        {"observed_worker_rank_count": 8},
        cache_state="cold",
        source_sha=SOURCE_SHA,
        expected_mpi_size=8,
        return_code=0,
        terminated_for_memory=False,
        terminated_for_timeout=False,
        telemetry_readable=True,
        source_stable_and_clean_after=True,
    )
    assert result["checks"]["fixed_rectangular_hexa_h15"] is True
    assert "fixed_rectangular_hexa_h13" not in result["checks"]
    assert result["checks"]["expected_h_mpi_policy"] is True
