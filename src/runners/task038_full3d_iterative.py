"""T1 identity stub for the not-yet-connected Full3D iterative adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


def run_full3d_iterative(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Expose the reviewed adapter identity without launching numerical code."""

    method = resolved_payload.get("method", {})
    if not isinstance(method, Mapping) or method.get("kind") != "full3d_iterative":
        raise ValueError("full3d_iterative adapter received a mismatched method")
    if resolved_payload.get("solver", {}).get("preconditioner") == "physical_p4_schur_v14":
        from .physical_p4_schur_v14 import run_physical_p4_schur_v14

        return run_physical_p4_schur_v14(
            resolved_payload,
            Path(run_directory),
            source_sha=_kwargs["source_sha"],
        )
    if resolved_payload.get("solver", {}).get("preconditioner") == "physical_p6_trace_p4_condensed_balh_v19":
        from .physical_dual_cell_condensed_v19 import run_physical_dual_cell_condensed_v19

        return run_physical_dual_cell_condensed_v19(
            resolved_payload, Path(run_directory), source_sha=_kwargs["source_sha"]
        )
    if resolved_payload.get("solver", {}).get("preconditioner") == "physical_p6_trace_p4_condensed_lowmem_v20":
        from .physical_dual_cell_condensed_lowmem_v20 import (
            run_physical_dual_cell_condensed_lowmem_v20,
        )

        return run_physical_dual_cell_condensed_lowmem_v20(
            resolved_payload, Path(run_directory), source_sha=_kwargs["source_sha"]
        )
    if resolved_payload.get("solver", {}).get("preconditioner") == "physical_p6_trace_p4_condensed_robustness_v21":
        from .physical_dual_cell_condensed_robustness_v21 import (
            run_physical_dual_cell_condensed_robustness_v21,
        )

        return run_physical_dual_cell_condensed_robustness_v21(
            resolved_payload, Path(run_directory), source_sha=_kwargs["source_sha"]
        )
    if resolved_payload.get("solver", {}).get("preconditioner") == "physical_p6_trace_p4_condensed_capacity_v22":
        from .physical_dual_cell_condensed_lowmem_v20 import (
            _run_physical_dual_cell_condensed_lowmem,
        )
        from src.io.physical_intermediate_profile import (
            CAPACITY_DUAL_CELL_CONDENSED_PROFILE,
        )

        return _run_physical_dual_cell_condensed_lowmem(
            resolved_payload,
            Path(run_directory),
            source_sha=_kwargs["source_sha"],
            profile_identity=CAPACITY_DUAL_CELL_CONDENSED_PROFILE,
            allowed_stages=("Z3_ORIGINAL_H7P5",),
            batch_identity="review_v22_original_b_capacity_trial",
            evidence_prefix="v22",
            summary_schema="task039extra.v22.worker-summary.v1",
            summary_filename="physical_dual_condensed_capacity_v22_summary.json",
            derive_live_space_identity=True,
            rhs_identity_policy="case_bound_physical_rhs",
            restore_summary_schema=True,
            reuse_qualified_jit=True,
            write_ordered_mode_manifest=True,
            write_geometry_audit=True,
            save_complete_field_packet=True,
            capacity_trial=True,
            reference_mode_by_stage={"Z3_ORIGINAL_H7P5": "authority_limited"},
            predecessor_by_stage={
                "Z3_ORIGINAL_H7P5": {
                    "accepted_v21_route": (
                        "physical_p6_trace_p4_condensed_robustness_v21"
                    ),
                    "cross_case_recycling": False,
                    "original_only": True,
                    "independent_batch": True,
                }
            },
            notch_by_stage={"Z3_ORIGINAL_H7P5": False},
        )
    if resolved_payload.get("solver", {}).get("preconditioner") == "physical_p4_blr_bal_h_v16":
        from .physical_p4_blr_v16 import run_physical_p4_blr_v16

        return run_physical_p4_blr_v16(
            resolved_payload,
            Path(run_directory),
            source_sha=_kwargs["source_sha"],
        )
    if resolved_payload.get("solver", {}).get("preconditioner") == "physical_p4_blr_tradeoff_v17":
        from .physical_p4_blr_v16 import run_physical_p4_blr_tradeoff_v17

        return run_physical_p4_blr_tradeoff_v17(
            resolved_payload,
            Path(run_directory),
            source_sha=_kwargs["source_sha"],
        )
    if resolved_payload.get("solver", {}).get("preconditioner") in {
        "physical_p4_cell_condensed_exact_v18",
        "physical_p4_cell_condensed_blr_v18",
    }:
        from .physical_p4_cell_condensed_v18 import (
            run_physical_p4_cell_condensed_v18,
        )

        return run_physical_p4_cell_condensed_v18(
            resolved_payload,
            Path(run_directory),
            source_sha=_kwargs["source_sha"],
        )
    from src.io.physical_intermediate_profile import PROFILES

    if resolved_payload.get("solver", {}).get("preconditioner") in PROFILES:
        from .physical_intermediate import run_physical_intermediate

        return run_physical_intermediate(resolved_payload, Path(run_directory), source_sha=_kwargs["source_sha"])
    return {
        "passed": False,
        "errors": [
            "full3d_iterative numerical adapter is not connected in T1; "
            "T2-T5 qualification is required"
        ],
        "summary": None,
        "numerical_output_directory": str(Path(run_directory).resolve() / "numerical_output"),
    }


__all__ = ["run_full3d_iterative"]
