from __future__ import annotations

from pathlib import Path

from ..common.config_3d import SimulationConfig3D
from .common_3d_case_flow import run_prepared_3d_case_flow


STAGE4B_CASES = frozenset({"stage4_block_grating"})


def run_stage4b_block_grating_3d_case(
    cfg: SimulationConfig3D,
    out_dir: Path,
    *,
    solution_observer=None,
    stage4_pre_release_numerical_capture=None,
    mesh_data_override=None,
    actual_selective_trace_expansion_factory=None,
) -> dict[str, object]:
    """Run Stage 4B: rectangular block grating with 3D DtN total-field ports.

    Case flow:

    1. Build the boundary-fitted or locally refined hexahedral periodic cell.
    2. Tag air, substrate, and the central rectangular block grating.
    3. Create the degree-1 or degree-2 N1curl function space.
    4. Build explicit topological x/y Floquet MPC constraints:
       p=1 uses edge dofs, while p=2 uses edge plus face-interior trace dofs.
    5. Assemble the total-field Maxwell system with the true grating material.
    6. Add top incident-port injection and outgoing top/bottom DtN modes.
    7. Save the total field and modal R/T power balance.
    """

    if cfg.stage_case not in STAGE4B_CASES:
        raise ValueError("run_stage4b_block_grating_3d_case accepts only stage_case='stage4_block_grating'.")
    return run_prepared_3d_case_flow(
        cfg,
        out_dir,
        expected_stage_case="stage4_block_grating",
        field_formulation="total_field_dtn_port",
        solve_stage4_dtn_port=True,
        apply_strong_boundary_bc=False,
        solution_observer=solution_observer,
        stage4_pre_release_numerical_capture=(
            stage4_pre_release_numerical_capture
        ),
        mesh_data_override=mesh_data_override,
        actual_selective_trace_expansion_factory=(
            actual_selective_trace_expansion_factory
        ),
    )


__all__ = ["STAGE4B_CASES", "run_stage4b_block_grating_3d_case"]
