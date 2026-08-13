"""Small Task39-only lifecycle event and ledger helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


TASK039_E10_STAGE_ORDER = (
    "mesh_spaces_ready",
    "qep_matrices_ready",
    "positive_qep_solve_peak",
    "negative_qep_solve_peak",
    "raw_candidate_eigenvectors_ready",
    "selected_biorthogonal_bases_ready",
    "canonical_negative_traces_ready",
    "projection_matrices_ready",
    "traction_matrices_ready",
    "local_fe_dtn_systems_ready",
    "hybrid_augmented_operator_ready",
    "direct_factor_or_iterative_side_factors_ready",
    "modal_schur_ready",
    "field_reconstruction_start",
    "field_reconstruction_peak",
    "postprocess_peak",
    "all_modal_qep_temporaries_released",
    "final_cleanup",
)


def task039_e10_stage_event(
    stage: str,
    *,
    elapsed_seconds: float,
    object_capacity: Mapping[str, Any] | None = None,
    detail: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if stage not in TASK039_E10_STAGE_ORDER:
        raise ValueError(f"unknown Task39 E10 stage: {stage}")
    event: dict[str, Any] = {
        "schema": "task039.e10-stage-event.v1",
        "stage": stage,
        "stage_index": TASK039_E10_STAGE_ORDER.index(stage),
        "elapsed_seconds": float(elapsed_seconds),
        "object_capacity": (
            dict(object_capacity)
            if object_capacity is not None
            else {"status": "not_available", "classification": "not_available"}
        ),
    }
    if detail is not None:
        event["detail"] = dict(detail)
    return event


def task039_e10_ledger(
    events: list[Mapping[str, Any]],
    *,
    object_capacity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    observed: dict[str, dict[str, Any]] = {}
    previous_index = -1
    for event in events:
        stage = str(event["stage"])
        if stage in observed:
            raise ValueError(f"duplicate Task39 E10 stage event: {stage}")
        index = TASK039_E10_STAGE_ORDER.index(stage)
        if index <= previous_index:
            raise ValueError(f"out-of-order Task39 E10 stage event: {stage}")
        observed[stage] = dict(event)
        previous_index = index
    nodes = {
        stage: observed.get(
            stage,
            {
                "status": "not_available",
                "classification": "not_available",
                "reason": "stage was not observed",
            },
        )
        for stage in TASK039_E10_STAGE_ORDER
    }
    return {
        "schema": "task039.e10-lifecycle.v1",
        "order": list(TASK039_E10_STAGE_ORDER),
        "nodes": nodes,
        "object_capacity": (
            dict(object_capacity)
            if object_capacity is not None
            else {"status": "not_available", "classification": "not_available"}
        ),
    }


__all__ = ["TASK039_E10_STAGE_ORDER", "task039_e10_ledger", "task039_e10_stage_event"]
