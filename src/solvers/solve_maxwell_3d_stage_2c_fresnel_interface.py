from __future__ import annotations

from pathlib import Path

from ..common.config_3d import SimulationConfig3D
from .common_3d_case_flow import run_prepared_3d_case_flow
from .common_3d_postprocess import run_fresnel_analytic_postprocess_sanity


STAGE2C_CASES = frozenset({"fresnel_interface"})


def run_stage2c_fresnel_interface_3d_case(cfg: SimulationConfig3D, out_dir: Path) -> dict[str, object]:
    """Run Stage 2C: flat air/substrate Fresnel interface diagnostic.

    Case flow:

    1. Build a two-layer air/substrate mesh with top/bottom PML.
    2. Create the N1curl function space.
    3. Build x/y Floquet MPC constraints.
    4. Use the incident plane wave as the known background source.
    5. Solve for the scattered field in the substrate-contrast source region.
    6. Form ``E_total = E_inc + E_sca`` and compare fitted R/T with Fresnel data.

    This remains a historical Stage-2 diagnostic; the refactor preserves its
    behavior but does not claim that the current 2C physics is final.
    """

    if cfg.stage_case not in STAGE2C_CASES:
        raise ValueError("run_stage2c_fresnel_interface_3d_case accepts only stage_case='fresnel_interface'.")
    return run_prepared_3d_case_flow(
        cfg,
        out_dir,
        expected_stage_case="fresnel_interface",
        field_formulation="incident_scattered",
        solve_incident_scattered=True,
        apply_strong_boundary_bc=True,
    )


__all__ = [
    "STAGE2C_CASES",
    "run_fresnel_analytic_postprocess_sanity",
    "run_stage2c_fresnel_interface_3d_case",
]
