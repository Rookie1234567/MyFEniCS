from __future__ import annotations

from pathlib import Path

from ..common.config_3d import SimulationConfig3D
from .common_3d_case_flow import run_prepared_3d_case_flow


STAGE1_CASES = frozenset({"stage1_airbox"})


def run_stage1_airbox_3d_case(cfg: SimulationConfig3D, out_dir: Path) -> dict[str, object]:
    """Run Stage 1: closed-form plane-wave propagation in a 3D air box.

    Read this file first when you only care about the minimal 3D Maxwell
    benchmark.  It deliberately accepts only ``stage_case="stage1_airbox"``;
    Floquet, PML, Fresnel, and grating-specific settings are routed through the
    later stage modules instead.

    Case flow:

    1. Build the air-box mesh.
    2. Create the N1curl function space.
    3. Interpolate the analytic plane wave as ``E_exact``.
    4. Impose tangential ``E_exact`` on all outer faces.
    5. Solve the homogeneous total-field curl-curl equation.
    6. Save fields and analytic-error metrics.
    """

    if cfg.stage_case not in STAGE1_CASES:
        raise ValueError("run_stage1_airbox_3d_case only accepts stage_case='stage1_airbox'.")
    return run_prepared_3d_case_flow(
        cfg,
        out_dir,
        expected_stage_case="stage1_airbox",
        field_formulation="total_field",
        apply_strong_boundary_bc=True,
    )
