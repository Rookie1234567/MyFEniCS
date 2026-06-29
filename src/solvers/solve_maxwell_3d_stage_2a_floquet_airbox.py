from __future__ import annotations

from pathlib import Path

from ..common.config_3d import SimulationConfig3D
from .common_3d_case_flow import run_prepared_3d_case_flow


STAGE2A_CASES = frozenset({"floquet_airbox"})


def run_stage2a_floquet_airbox_3d_case(cfg: SimulationConfig3D, out_dir: Path) -> dict[str, object]:
    """Run Stage 2A: double-Floquet air box without PML.

    Case flow:

    1. Build the periodic-compatible 3D air-box mesh.
    2. Create the N1curl function space.
    3. Build explicit edge-topology x/y Floquet MPC constraints.
    4. Solve a correction-field problem with zero z-boundary data.
    5. Add the analytic incident plane wave back to obtain the total field.
    6. Report face/edge Floquet mismatch and analytic-field error metrics.
    """

    if cfg.stage_case not in STAGE2A_CASES:
        raise ValueError("run_stage2a_floquet_airbox_3d_case accepts only stage_case='floquet_airbox'.")
    return run_prepared_3d_case_flow(
        cfg,
        out_dir,
        expected_stage_case="floquet_airbox",
        field_formulation="incident_correction",
        solve_reference_correction=True,
        apply_strong_boundary_bc=True,
    )


__all__ = ["STAGE2A_CASES", "run_stage2a_floquet_airbox_3d_case"]
