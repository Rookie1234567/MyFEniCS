"""V21 geometry-robustness adapter over the reviewed V20 numerical route."""

from __future__ import annotations

from pathlib import Path

from src.io.physical_intermediate_profile import (
    ROBUSTNESS_DUAL_CELL_CONDENSED_PROFILE,
)

from .physical_dual_cell_condensed_lowmem_v20 import (
    _run_physical_dual_cell_condensed_lowmem,
)


def run_physical_dual_cell_condensed_robustness_v21(
    resolved_payload, run_directory, *, source_sha
):
    """Run one explicit V21 A/B/C stage with live dimension identities."""

    return _run_physical_dual_cell_condensed_lowmem(
        resolved_payload,
        Path(run_directory),
        source_sha=source_sha,
        profile_identity=ROBUSTNESS_DUAL_CELL_CONDENSED_PROFILE,
        allowed_stages=(
            "Z2_NOTCH_H10",
            "Z3_ORIGINAL_H7P5",
            "Z4_NOTCH_H7P5",
        ),
        batch_identity="review_v21_dual_condensed_geometry_h7p5",
        evidence_prefix="v21",
        summary_schema="task039extra.v21.worker-summary.v1",
        summary_filename="physical_dual_condensed_robustness_v21_summary.json",
        derive_live_space_identity=True,
        rhs_identity_policy="case_bound_physical_rhs",
        restore_summary_schema=True,
        reference_mode_by_stage={
            "Z2_NOTCH_H10": "required",
            "Z3_ORIGINAL_H7P5": "authority_limited",
            "Z4_NOTCH_H7P5": "authority_limited",
        },
        predecessor_by_stage={
            stage: {
                "accepted_v20_numerical_route": (
                    "physical_p6_trace_p4_condensed_lowmem_v20"
                ),
                "cross_case_recycling": False,
                "frozen_geometry_plan": (
                    "task039extra.v21.frozen-geometry-mesh-plan.v1"
                ),
                "stage_independent_fresh_worker": True,
            }
            for stage in (
                "Z2_NOTCH_H10",
                "Z3_ORIGINAL_H7P5",
                "Z4_NOTCH_H7P5",
            )
        },
        notch_by_stage={
            "Z2_NOTCH_H10": True,
            "Z3_ORIGINAL_H7P5": False,
            "Z4_NOTCH_H7P5": True,
        },
    )


__all__ = ["run_physical_dual_cell_condensed_robustness_v21"]
