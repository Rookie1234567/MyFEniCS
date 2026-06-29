from __future__ import annotations

from pathlib import Path

from ..common.config_3d import SimulationConfig3D
from .common_3d_case_flow import run_prepared_3d_case_flow


STAGE2B_CASES = frozenset({"pml_airbox"})


def run_stage2b_pml_airbox_3d_case(cfg: SimulationConfig3D, out_dir: Path) -> dict[str, object]:
    """Run Stage 2B: double-Floquet air box with z-direction PML.

    Case flow:

    1. Build the physical air region plus top/bottom PML layers.
    2. Create the N1curl function space.
    3. Build x/y Floquet MPC constraints across physical and PML cells.
    4. Solve a reference-correction problem with zero outer z-boundary data.
    5. Add the analytic plane wave back to obtain the total field.
    6. Report PML decay proxy, Floquet mismatch, and analytic-field errors.
    """

    if cfg.stage_case not in STAGE2B_CASES:
        raise ValueError("run_stage2b_pml_airbox_3d_case accepts only stage_case='pml_airbox'.")
    return run_prepared_3d_case_flow(
        cfg,
        out_dir,
        expected_stage_case="pml_airbox",
        field_formulation="reference_correction",
        solve_reference_correction=True,
        apply_strong_boundary_bc=True,
    )


__all__ = ["STAGE2B_CASES", "run_stage2b_pml_airbox_3d_case"]
