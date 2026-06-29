from __future__ import annotations

from pathlib import Path

from ..common.config_3d import SimulationConfig3D
from .solve_maxwell_3d_common_old import (
    _field_formulation_label,
    _fresnel_numerical_metrics,
    _mode_basis,
    _use_incident_scattered_formulation,
    _use_layered_scattered_formulation,
    _use_reference_correction_formulation,
    incident_air_plane_wave_field,
    plane_wave_electric_field,
    run_fresnel_analytic_postprocess_sanity,
    stage4_layered_background_field,
)
from .solve_maxwell_3d_stage_1_airbox import STAGE1_CASES, run_stage1_airbox_3d_case
from .solve_maxwell_3d_stage_2_no_grating_old import STAGE2_CASES, run_stage2_no_grating_3d_case
from .solve_maxwell_3d_stage_4_grating_old import STAGE4_CASES, run_stage4_grating_3d_case


def run_airbox_3d_case(cfg: SimulationConfig3D, out_dir: Path) -> dict[str, object]:
    """Compatibility dispatcher for old imports.

    New code should import the stage-specific entry it needs:

    - ``solve_maxwell_3d_stage_1_airbox.run_stage1_airbox_3d_case``
    - ``solve_maxwell_3d_stage_2_no_grating.run_stage2_no_grating_3d_case``
    - ``solve_maxwell_3d_stage_4_grating.run_stage4_grating_3d_case``
    """

    if cfg.stage_case in STAGE1_CASES:
        return run_stage1_airbox_3d_case(cfg, out_dir)
    if cfg.stage_case in STAGE2_CASES:
        return run_stage2_no_grating_3d_case(cfg, out_dir)
    if cfg.stage_case in STAGE4_CASES:
        return run_stage4_grating_3d_case(cfg, out_dir)
    raise ValueError(
        "Unsupported 3D stage_case. Expected Stage 1, Stage 2 no-grating, or Stage 4 grating case."
    )


__all__ = [
    "_field_formulation_label",
    "_fresnel_numerical_metrics",
    "_mode_basis",
    "_use_incident_scattered_formulation",
    "_use_layered_scattered_formulation",
    "_use_reference_correction_formulation",
    "incident_air_plane_wave_field",
    "plane_wave_electric_field",
    "run_airbox_3d_case",
    "run_fresnel_analytic_postprocess_sanity",
    "stage4_layered_background_field",
]
