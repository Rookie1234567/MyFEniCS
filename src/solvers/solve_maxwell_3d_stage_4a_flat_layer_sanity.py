from __future__ import annotations

from pathlib import Path

from ..common.config_3d import SimulationConfig3D
from .common_3d_case_flow import run_prepared_3d_case_flow


STAGE4A_CASES = frozenset({"stage4_flat_layer_sanity"})


def run_stage4a_flat_layer_sanity_3d_case(cfg: SimulationConfig3D, out_dir: Path) -> dict[str, object]:
    """Run Stage 4A: DtN total-field flat-layer sanity case.

    Case flow:

    1. Build the hexahedral periodic cell without a grating contrast source.
    2. Create the N1curl function space.
    3. Build x/y Floquet MPC constraints.
    4. Assemble the total-field Maxwell matrix in the layered medium.
    5. Add top incident-port injection and top/bottom outgoing DtN modes.
    6. Report R/T directly from port modal amplitudes.
    """

    if cfg.stage_case not in STAGE4A_CASES:
        raise ValueError(
            "run_stage4a_flat_layer_sanity_3d_case accepts only "
            "stage_case='stage4_flat_layer_sanity'."
        )
    return run_prepared_3d_case_flow(
        cfg,
        out_dir,
        expected_stage_case="stage4_flat_layer_sanity",
        field_formulation="total_field_dtn_port",
        solve_stage4_dtn_port=True,
        apply_strong_boundary_bc=False,
    )


__all__ = ["STAGE4A_CASES", "run_stage4a_flat_layer_sanity_3d_case"]
