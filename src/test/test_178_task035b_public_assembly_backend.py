from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    STANDARD_FULL_ASSEMBLY_BACKEND,
    SimulationConfig3D,
    qualify_stage4_full3d_assembly_backend,
    resolve_stage4_full3d_assembly_backend,
)
from src.main import Stage4GratingInputs3D, preset_cli_args
from src.runners import run_3d_cases


def test_ordinary_default_resolves_to_standard_full_without_mutation():
    cfg = SimulationConfig3D()

    audit = resolve_stage4_full3d_assembly_backend(cfg, apply=True)

    assert audit["requested"] == STANDARD_FULL_ASSEMBLY_BACKEND
    assert audit["actual"] == STANDARD_FULL_ASSEMBLY_BACKEND
    assert audit["selection_source"] == "public_default"
    assert audit["ordinary_default_unchanged"] is True
    assert cfg.stage4_cell_static_condensation is False
    assert cfg.stage4_assembly_time_cell_static_condensation is False
    assert cfg.stage4_floquet_slave_elimination is False


def test_public_condensed_backend_enables_complete_internal_contract():
    cfg = SimulationConfig3D(
        stage4_full3d_assembly_backend=(
            ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
        )
    )

    audit = resolve_stage4_full3d_assembly_backend(cfg, apply=True)

    assert audit["actual"] == ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
    assert audit["selection_source"] == "public_port"
    assert cfg.stage4_cell_static_condensation is True
    assert cfg.stage4_assembly_time_cell_static_condensation is True
    assert cfg.stage4_floquet_slave_elimination is True


@pytest.mark.parametrize(
    "updates",
    (
        {
            "stage4_full3d_assembly_backend": (
                ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
            ),
            "stage4_cell_static_condensation": True,
        },
        {
            "stage4_assembly_time_cell_static_condensation": True,
        },
        {
            "stage4_floquet_slave_elimination": True,
        },
    ),
)
def test_incomplete_legacy_combinations_fail_closed(updates):
    with pytest.raises(ValueError):
        resolve_stage4_full3d_assembly_backend(
            SimulationConfig3D(**updates),
            apply=True,
        )


def test_legacy_post_assembly_path_is_internal_not_public():
    cfg = SimulationConfig3D(stage4_cell_static_condensation=True)

    audit = resolve_stage4_full3d_assembly_backend(cfg)

    assert audit["actual"] == "legacy_post_assembly_static_condensed"
    assert audit["selection_source"] == "legacy_internal_compatibility"


def test_public_backend_qualification_accepts_only_fixed_direct_target():
    cfg = SimulationConfig3D(
        stage_case="stage4_block_grating",
        geometry_kind="rectangular_block_grating",
        mesh_cell_type="hexahedron",
        use_floquet_xy=True,
        stage4_full3d_assembly_backend=(
            ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
        ),
    )
    audit = resolve_stage4_full3d_assembly_backend(cfg, apply=True)

    qualification = qualify_stage4_full3d_assembly_backend(cfg, audit)

    assert qualification["status"] == "qualified"
    assert qualification["qualified_scope"] is True


@pytest.mark.parametrize(
    "updates",
    (
        {"mesh_cell_type": "tetrahedron"},
        {"geometry_kind": "sloped_sidewall"},
        {"stage4_condensed_iterative_profile": "research_profile"},
        {"stage4_regionwise_interior_p": True},
        {"stage4_live_full_p6_local_schur_capture": True},
    ),
)
def test_public_backend_rejects_unqualified_capabilities(updates):
    values = {
        "stage_case": "stage4_block_grating",
        "geometry_kind": "rectangular_block_grating",
        "mesh_cell_type": "hexahedron",
        "use_floquet_xy": True,
        "stage4_full3d_assembly_backend": (
            ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
        ),
    }
    values.update(updates)
    cfg = SimulationConfig3D(**values)
    audit = resolve_stage4_full3d_assembly_backend(cfg, apply=True)

    with pytest.raises(ValueError, match="standard_full"):
        qualify_stage4_full3d_assembly_backend(cfg, audit)


def test_public_backend_rejects_selective_trace_hook():
    cfg = SimulationConfig3D(
        stage_case="stage4_block_grating",
        geometry_kind="rectangular_block_grating",
        mesh_cell_type="hexahedron",
        use_floquet_xy=True,
        stage4_full3d_assembly_backend=(
            ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
        ),
    )
    audit = resolve_stage4_full3d_assembly_backend(cfg, apply=True)

    with pytest.raises(ValueError, match="standard_full"):
        qualify_stage4_full3d_assembly_backend(
            cfg,
            audit,
            selective_trace_active=True,
        )


def test_complete_legacy_assembly_time_triple_obeys_same_scope_gate():
    cfg = SimulationConfig3D(
        stage_case="stage4_block_grating",
        geometry_kind="rectangular_block_grating",
        mesh_cell_type="tetrahedron",
        use_floquet_xy=True,
        stage4_cell_static_condensation=True,
        stage4_assembly_time_cell_static_condensation=True,
        stage4_floquet_slave_elimination=True,
    )
    audit = resolve_stage4_full3d_assembly_backend(cfg, apply=True)

    assert audit["actual"] == ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
    assert audit["selection_source"] == "legacy_internal_compatibility"
    with pytest.raises(ValueError, match="standard_full"):
        qualify_stage4_full3d_assembly_backend(cfg, audit)


def test_pycharm_facade_exposes_one_backend_value():
    settings = Stage4GratingInputs3D(
        stage4_full3d_assembly_backend=(
            ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
        )
    )
    with patch.dict(
        "src.main.PRESETS_3D",
        {"backend_contract": settings},
        clear=False,
    ):
        dimension, args = preset_cli_args("backend_contract")

    index = args.index("--stage4-full3d-assembly-backend")
    assert dimension == "3d"
    assert args[index + 1] == ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND


def test_runner_cli_maps_public_backend_without_exposing_legacy_flags(
    tmp_path,
):
    captured: dict[str, object] = {}

    def capture(case: str, stage_case: str, updates: dict[str, object]):
        captured.update(updates)
        return []

    with (
        patch.object(run_3d_cases, "_case_configs", side_effect=capture),
        patch.object(
            run_3d_cases,
            "project_root",
            return_value=Path(tmp_path),
        ),
    ):
        run_3d_cases.main(
            [
                "--stage-case",
                "stage4_block_grating",
                "--stage4-full3d-assembly-backend",
                ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
                "--results-root",
                str(tmp_path),
                "--no-unique-output",
            ]
        )

    assert captured["stage4_full3d_assembly_backend"] == (
        ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
    )
    assert "stage4_cell_static_condensation" not in captured
    assert "stage4_assembly_time_cell_static_condensation" not in captured
    assert "stage4_floquet_slave_elimination" not in captured
