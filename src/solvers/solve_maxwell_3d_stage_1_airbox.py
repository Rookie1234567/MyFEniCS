from __future__ import annotations

from pathlib import Path

from ..common.config_3d import SimulationConfig3D
from .solve_maxwell_3d_common import _run_maxwell_3d_case_core


STAGE1_CASES = frozenset({"stage1_airbox"})


def run_stage1_airbox_3d_case(cfg: SimulationConfig3D, out_dir: Path) -> dict[str, object]:
    """Run Stage 1: closed-form plane-wave propagation in a 3D air box.

    Read this file first when you only care about the minimal 3D Maxwell
    benchmark.  It deliberately accepts only ``stage_case="stage1_airbox"``;
    Floquet, PML, Fresnel, and grating-specific settings are routed through the
    later stage modules instead.
    """

    if cfg.stage_case not in STAGE1_CASES:
        raise ValueError("run_stage1_airbox_3d_case only accepts stage_case='stage1_airbox'.")
    return _run_maxwell_3d_case_core(cfg, out_dir)
