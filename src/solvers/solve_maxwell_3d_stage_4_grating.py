from __future__ import annotations

from pathlib import Path

from ..common.config_3d import SimulationConfig3D
from .solve_maxwell_3d_common import _run_maxwell_3d_case_core


STAGE4_CASES = frozenset({"stage4_flat_layer_sanity", "stage4_block_grating"})


def run_stage4_grating_3d_case(cfg: SimulationConfig3D, out_dir: Path) -> dict[str, object]:
    """Run Stage 4 periodic grating cases.

    This is the reading entry for the real 3D periodic-structure workflow:
    layered Fresnel background, scattered-field source in the rectangular block,
    top/bottom PML, x/y Floquet constraints, and diffraction-order
    postprocessing.
    """

    if cfg.stage_case not in STAGE4_CASES:
        raise ValueError(
            "run_stage4_grating_3d_case accepts only 'stage4_flat_layer_sanity' "
            "or 'stage4_block_grating'."
        )
    return _run_maxwell_3d_case_core(cfg, out_dir)
