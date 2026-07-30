from __future__ import annotations

import math

import pytest

from benchmarks.check_case118_task002_m4d import check_records
from src.forward_data.task002_m4d import (
    AZIMUTH_STENCIL,
    FAILED_POINT,
    INDEPENDENT_PROJECTION_QUADRATURE,
    SURFACE_QUADRATURE_DEGREES,
    Y_CELL_COUNTS,
    alias_kinematics,
    build_task002_m4d_config,
    m4d_config_identity,
)


def test_m4d_matrix_is_exact_and_diagnostic_only() -> None:
    assert AZIMUTH_STENCIL == (
        50.0, 51.0, 52.0, 53.0, 53.5, 54.0, 54.25, 54.5,
        54.75, 55.0, 55.5, 56.0, 57.0, 58.0,
    )
    assert Y_CELL_COUNTS == (3, 4, 5, 6)
    assert SURFACE_QUADRATURE_DEGREES == (None, 31, 39, 47)
    assert INDEPENDENT_PROJECTION_QUADRATURE == 63


def test_alias_kinematics_matches_review_v6() -> None:
    row = alias_kinematics(FAILED_POINT)
    assert row["ky_per_nm"] == pytest.approx(0.3773457689, abs=2e-10)
    assert row["two_ky_minus_3Gy_per_nm"] == pytest.approx(7.093e-4, abs=2e-7)


def test_diagnostic_overrides_do_not_change_production_parameters() -> None:
    cfg = build_task002_m4d_config(
        FAILED_POINT, y_cells=4, surface_quadrature_degree=39,
    )
    assert cfg.mesh_axis_cell_counts == (6, 4, 14)
    assert cfg.stage4_dtn_quadrature_degree == 39
    identity = m4d_config_identity(
        FAILED_POINT, y_cells=4, surface_quadrature_degree=39,
    )
    assert identity["role"] == "diagnostic_only_not_dataset_eligible"
    assert len(identity["identity_sha256"]) == 64
    with pytest.raises(ValueError, match="y_cells"):
        build_task002_m4d_config(FAILED_POINT, y_cells=7)


def test_auto_quadrature_remains_unset() -> None:
    cfg = build_task002_m4d_config(FAILED_POINT, y_cells=3)
    assert cfg.stage4_dtn_quadrature_degree is None


def test_case118_tracked_evidence_passes_independent_checker() -> None:
    result = check_records()
    assert result["pass"] is True
    assert result["pass_count"] == result["check_count"] == 13
