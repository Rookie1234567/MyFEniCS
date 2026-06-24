from __future__ import annotations

from pathlib import Path

from ..common.config_3d import SimulationConfig3D
from .solve_maxwell_3d_common import (
    _run_maxwell_3d_case_core,
    run_fresnel_analytic_postprocess_sanity,
)


STAGE2_CASES = frozenset({"floquet_airbox", "pml_airbox", "fresnel_interface"})


def run_stage2_no_grating_3d_case(cfg: SimulationConfig3D, out_dir: Path) -> dict[str, object]:
    """Run Stage 2 no-grating benchmarks.

    This is the reading entry for:

    - ``floquet_airbox``: x/y double-Floquet air box.
    - ``pml_airbox``: double-Floquet air box with z-PML diagnostics.
    - ``fresnel_interface``: flat air/substrate interface diagnostics.

    No rectangular grating source is allowed here; Stage 4 owns that path.
    """

    if cfg.stage_case not in STAGE2_CASES:
        raise ValueError(
            "run_stage2_no_grating_3d_case accepts only 'floquet_airbox', "
            "'pml_airbox', or 'fresnel_interface'."
        )
    return _run_maxwell_3d_case_core(cfg, out_dir)


__all__ = [
    "STAGE2_CASES",
    "run_fresnel_analytic_postprocess_sanity",
    "run_stage2_no_grating_3d_case",
]
