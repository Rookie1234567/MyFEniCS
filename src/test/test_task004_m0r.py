"""Pure-Python M0R guards for Task004 provenance and angle pipeline."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("sklearn")

from src.forward_data.task002_full3d import (  # noqa: E402
    task002_full3d_command, task002_full3d_config_identity,
)
from src.forward_data.task002_schema import Task002ForwardParameters  # noqa: E402
from src.surrogate.angle.design import build_designs  # noqa: E402
from src.surrogate.angle.models import region_masks  # noqa: E402


def _parameters() -> Task002ForwardParameters:
    return Task002ForwardParameters(
        height_nm=120.0, width_x_nm=17.0,
        grazing_deg=5.25, azimuth_deg=45.0,
        model_id="S_PROD_FULL3D_STATIC_P5_H10_NY4",
    )


def test_mumps_workspace_is_hash_bound_and_prefixed() -> None:
    p = _parameters()
    low = task002_full3d_config_identity(p, mumps_icntl_14=40)
    high = task002_full3d_config_identity(p, mumps_icntl_14=80)
    assert low["config_sha256"] != high["config_sha256"]
    assert low["linear_solver"]["option_scope"] == "prefixed_ksp"
    assert low["linear_solver"]["mat_mumps_icntl_14"] == 40
    command = task002_full3d_command(
        root=Path("/tmp"), parameters_file=Path("/tmp/parameters.json"),
        baseline_sha="a" * 40, output_dir=Path("/tmp/results"),
        mumps_icntl_14=80,
    )
    assert "--mumps-icntl-14" in command and command[command.index("--mumps-icntl-14") + 1] == "80"


def test_frozen_angle_tuple_hashes_are_unchanged_by_metadata_v2() -> None:
    designs = build_designs(source_sha="a" * 40)
    assert designs["training"]["point_count"] == 96
    assert designs["validation"]["point_count"] == 24
    assert designs["candidate_pool"]["point_count"] == 4096
    assert designs["anchors"]["point_count"] == 5
    assert all(item["schema_version"] == "task004.angle-design.v2" for item in designs.values())
    assert designs["training"]["point_tuple_sha256"] == (
        "bfd68a374e5510284a972c640c6332d818917052ae30bd77c10af5240f0500ef"
    )
    assert all("region_labels" in point and "selection_reason" in point
               for point in designs["training"]["points"])


def test_region_masks_are_independent() -> None:
    masks = region_masks(np.asarray([[0.5, 90.0], [9.0, 0.0]]))
    assert masks["low_grazing"][0] and masks["high_azimuth"][0]
    assert not masks["ordinary_interior"][0]
    assert masks["ordinary_interior"][1]
