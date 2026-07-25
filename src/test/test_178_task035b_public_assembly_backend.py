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


def _qualified_config(**updates: object) -> SimulationConfig3D:
    values: dict[str, object] = {
        "stage_case": "stage4_block_grating",
        "geometry_kind": "rectangular_block_grating",
        "mesh_cell_type": "hexahedron",
        "use_floquet_xy": True,
        "use_pml": False,
        "stage4_boundary_model": "dtn_port",
        "stage4_dtn_assembly": "auxiliary",
        "grating_width_x": 17.0,
        "grating_width_y": 25.0,
        "grating_height": 120.0,
        "stage4_full3d_assembly_backend": (
            ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
        ),
    }
    values.update(updates)
    return SimulationConfig3D(**values)


def test_ordinary_default_is_standard_full_and_does_not_mutate_internal_state():
    cfg = SimulationConfig3D()

    audit = resolve_stage4_full3d_assembly_backend(cfg, apply=True)

    assert cfg.stage4_full3d_assembly_backend == STANDARD_FULL_ASSEMBLY_BACKEND
    assert audit["requested"] == STANDARD_FULL_ASSEMBLY_BACKEND
    assert audit["actual"] == STANDARD_FULL_ASSEMBLY_BACKEND
    assert audit["selection_source"] == "public_default"
    assert audit["ordinary_default_unchanged"] is True
    assert cfg.stage4_cell_static_condensation is False
    assert cfg.stage4_assembly_time_cell_static_condensation is False
    assert cfg.stage4_floquet_slave_elimination is False


def test_public_condensed_backend_sets_the_complete_internal_contract():
    cfg = _qualified_config()

    audit = resolve_stage4_full3d_assembly_backend(cfg, apply=True)

    assert audit["requested"] == ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
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
        {"stage4_assembly_time_cell_static_condensation": True},
        {"stage4_floquet_slave_elimination": True},
        {
            "stage4_cell_static_condensation": True,
            "stage4_assembly_time_cell_static_condensation": True,
        },
    ),
)
def test_partial_legacy_combinations_fail_closed(updates: dict[str, object]):
    with pytest.raises(ValueError, match="partial|conflicts"):
        resolve_stage4_full3d_assembly_backend(
            SimulationConfig3D(**updates),
            apply=True,
        )


def test_unknown_public_backend_fails_closed():
    cfg = SimulationConfig3D(stage4_full3d_assembly_backend="automatic")

    with pytest.raises(ValueError, match="stage4_full3d_assembly_backend"):
        resolve_stage4_full3d_assembly_backend(cfg)


def test_legacy_post_assembly_path_is_internal_not_a_public_choice():
    cfg = SimulationConfig3D(stage4_cell_static_condensation=True)

    audit = resolve_stage4_full3d_assembly_backend(cfg)

    assert audit["actual"] == "legacy_post_assembly_static_condensed"
    assert audit["selection_source"] == "legacy_internal_compatibility"
    assert qualify_stage4_full3d_assembly_backend(cfg, audit)["status"] == (
        "not_required"
    )


def test_public_backend_qualification_accepts_fixed_direct_target():
    cfg = _qualified_config()
    audit = resolve_stage4_full3d_assembly_backend(cfg, apply=True)

    qualification = qualify_stage4_full3d_assembly_backend(cfg, audit)

    assert qualification["status"] == "qualified"
    assert qualification["qualified_scope"] is True
    assert "full_recovery_and_explicit_residual" in qualification["contract"]


@pytest.mark.parametrize(
    "updates,match",
    (
        ({"mesh_cell_type": "tetrahedron"}, "hexahedra"),
        ({"geometry_kind": "sloped_sidewall"}, "rectangular"),
        ({"use_pml": True}, "PML"),
        ({"stage4_boundary_model": "pml"}, "dtn_port"),
        ({"stage4_dtn_assembly": "dense"}, "auxiliary"),
        ({"matrix_diagnostics_assemble_only": True}, "complete direct solve"),
        (
            {"matrix_diagnostics_factorization_only": True},
            "complete direct solve",
        ),
    ),
)
def test_public_backend_rejects_unqualified_scope(
    updates: dict[str, object],
    match: str,
):
    cfg = _qualified_config(**updates)
    audit = resolve_stage4_full3d_assembly_backend(cfg, apply=True)

    with pytest.raises(ValueError, match=match):
        qualify_stage4_full3d_assembly_backend(cfg, audit)


def test_complete_legacy_assembly_time_triple_obeys_the_same_scope_gate():
    cfg = _qualified_config(
        stage4_full3d_assembly_backend=STANDARD_FULL_ASSEMBLY_BACKEND,
        mesh_cell_type="tetrahedron",
        stage4_cell_static_condensation=True,
        stage4_assembly_time_cell_static_condensation=True,
        stage4_floquet_slave_elimination=True,
    )
    audit = resolve_stage4_full3d_assembly_backend(cfg, apply=True)

    assert audit["actual"] == ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
    assert audit["selection_source"] == "legacy_internal_compatibility"
    with pytest.raises(ValueError, match="standard_full"):
        qualify_stage4_full3d_assembly_backend(cfg, audit)


def test_json_snapshot_has_one_public_port_and_no_research_local_p_fields():
    data = SimulationConfig3D().as_jsonable()

    assert data["stage4_full3d_assembly_backend"] == STANDARD_FULL_ASSEMBLY_BACKEND
    assert "stage4_regionwise_interior_p" not in data
    assert data["nedelec_trace_degree"] is None
    assert data["nedelec_interior_degree"] is None
    assert data["nedelec_fixed_trace_contract"] == "uniform_n1curl"


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


def test_pycharm_facade_ordinary_default_is_standard_full():
    assert (
        Stage4GratingInputs3D().stage4_full3d_assembly_backend
        == STANDARD_FULL_ASSEMBLY_BACKEND
    )


def test_runner_cli_maps_only_the_public_backend(tmp_path: Path):
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
