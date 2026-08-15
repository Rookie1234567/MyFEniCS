"""Small Task39-only lifecycle event and ledger helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
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


TASK039_V2_H5_STAGE_ORDER = (
    "baseline_before_mesh",
    "mesh_spaces_ready",
    "qep_matrices_ready",
    "positive_qep_peak",
    "negative_qep_peak",
    "raw_candidate_modes_ready",
    "selected_biorthogonal_bases_ready",
    "canonical_traces_ready",
    "projection_matrices_ready",
    "traction_matrices_ready",
    "local_fe_dtn_ready",
    "hybrid_augmented_matrix_ready",
    "mumps_analysis_ready_when_available",
    "mumps_numeric_factor_ready",
    "solution_ready",
    "field_reconstruction_peak",
    "modal_qep_temporaries_released",
    "final_cleanup",
)

_TASK039_V2_H5_STAGE_ALIASES = {
    "positive_qep_solve_peak": "positive_qep_peak",
    "negative_qep_solve_peak": "negative_qep_peak",
    "raw_candidate_eigenvectors_ready": "raw_candidate_modes_ready",
    "canonical_negative_traces_ready": "canonical_traces_ready",
    "local_fe_dtn_systems_ready": "local_fe_dtn_ready",
    "hybrid_augmented_operator_ready": "hybrid_augmented_matrix_ready",
    "direct_factor_or_iterative_side_factors_ready": "mumps_numeric_factor_ready",
    "all_modal_qep_temporaries_released": "modal_qep_temporaries_released",
}


def task039_v2_h5_stage_name(stage: str) -> str | None:
    """Map a worker marker to the frozen V2 h5 stage, or omit legacy-only nodes."""

    mapped = _TASK039_V2_H5_STAGE_ALIASES.get(stage, stage)
    return mapped if mapped in TASK039_V2_H5_STAGE_ORDER else None


def task039_stage_target(stage: str, *, formal_v2_h5: bool) -> str | None:
    if formal_v2_h5:
        return task039_v2_h5_stage_name(stage)
    return stage if stage in TASK039_E10_STAGE_ORDER else None


def task039_h5_hybrid_direct_formal_profile(
    payload: Mapping[str, Any],
) -> bool:
    """Return true only for the opt-in V2 h5 Hybrid-direct profile."""

    method = payload.get("method")
    discretization = payload.get("discretization")
    identity = payload.get("identity", payload)
    model_id = identity.get("model_id") if isinstance(identity, Mapping) else None
    return bool(
        isinstance(method, Mapping)
        and method.get("kind") == "hybrid_direct"
        and method.get("requested_modes_per_direction") == 480
        and model_id
        in {
            "task039_5nm_hybrid_direct_m480",
            "task039_5nm_v3_1deg_s5_hybrid_direct_m480",
        }
        and isinstance(discretization, Mapping)
        and float(discretization.get("mesh_target_nm", float("nan"))) == 5.0
    )


def task039_h5_hybrid_iterative_formal_profile(
    payload: Mapping[str, Any],
) -> bool:
    """Return true only for the opt-in V2 h5 Hybrid-iterative profile."""

    method = payload.get("method")
    discretization = payload.get("discretization")
    execution = payload.get("execution")
    identity = payload.get("identity", payload)
    model_id = identity.get("model_id") if isinstance(identity, Mapping) else None
    return bool(
        isinstance(method, Mapping)
        and method.get("kind") == "hybrid_iterative"
        and method.get("requested_modes_per_direction") == 480
        and model_id == "task039_5nm_hybrid_iterative_m480_candidate"
        and isinstance(discretization, Mapping)
        and float(discretization.get("mesh_target_nm", float("nan"))) == 5.0
        and isinstance(execution, Mapping)
        and execution.get("mpi_size") == 8
    )


def task039_v3_2d_formal_profile(payload: Mapping[str, Any]) -> bool:
    """Return true only for the V3 1-degree TE reference inputs."""

    method = payload.get("method")
    discretization = payload.get("discretization")
    execution = payload.get("execution")
    identity = payload.get("identity", payload)
    model_id = identity.get("model_id") if isinstance(identity, Mapping) else None
    mesh_target = (
        discretization.get("mesh_target_nm")
        if isinstance(discretization, Mapping)
        else None
    )
    return bool(
        isinstance(method, Mapping)
        and method.get("kind") == "2d_port"
        and model_id == "task039_5nm_v3_1deg_s5"
        and isinstance(execution, Mapping)
        and execution.get("mpi_size") == 1
        and isinstance(discretization, Mapping)
        and any(
            isinstance(mesh_target, (int, float))
            and abs(float(mesh_target) - target) <= 1.0e-12
            for target in (5.0, 4.0, 3.0, 2.0, 1.5)
        )
    )


def task039_v2_h5_stage_event(
    stage: str,
    *,
    elapsed_seconds: float,
    object_capacity: Mapping[str, Any] | None = None,
    detail: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if stage not in TASK039_V2_H5_STAGE_ORDER:
        raise ValueError(f"unknown Task39 V2 h5 stage: {stage}")
    event: dict[str, Any] = {
        "schema": "task039.v2-h5-stage-marker.v1",
        "stage": stage,
        "stage_index": TASK039_V2_H5_STAGE_ORDER.index(stage),
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


def task039_read_new_markers(
    path: Path, offset: int = 0
) -> tuple[list[dict[str, Any]], int]:
    """Read complete new JSONL marker records without retaining the stream."""

    if not path.is_file():
        return [], offset
    with path.open("rb") as stream:
        stream.seek(offset)
        chunk = stream.read()
    if not chunk or b"\n" not in chunk:
        return [], offset
    complete = chunk if chunk.endswith(b"\n") else chunk.rsplit(b"\n", 1)[0] + b"\n"
    consumed = len(complete)
    records: list[dict[str, Any]] = []
    for line in complete.splitlines():
        if line.strip():
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError("Task39 V2 stage marker must be a JSON object")
            records.append(record)
    return records, offset + consumed


def _not_available(status: str = "not_available") -> dict[str, str]:
    return {"status": status, "classification": status}


def _compact_fields(
    value: Any,
    keys: tuple[str, ...],
    *,
    classification: str = "measured_from_worker_record",
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return _not_available()
    selected = {key: value[key] for key in keys if value.get(key) is not None}
    if not selected:
        return _not_available()
    selected["classification"] = classification
    return selected


def _compact_matrix(value: Any) -> dict[str, Any]:
    return _compact_fields(
        value,
        (
            "matrix_rows",
            "matrix_cols",
            "matrix_nnz_used",
            "matrix_nnz_allocated",
            "matrix_memory_estimate_bytes",
            "matrix_type",
            "matrix_stats_measurement_status",
        ),
    )


def task039_h5_memory_object_ledger(record: Mapping[str, Any]) -> dict[str, Any]:
    """Make a compact worker-owned object ledger from fields already in a record."""

    source = record.get("object_payload_ledger")
    source = source if isinstance(source, Mapping) else {}
    qep = record.get("qep")
    qep = qep if isinstance(qep, Mapping) else {}
    hybrid = record.get("hybrid_system")
    hybrid = hybrid if isinstance(hybrid, Mapping) else {}
    projection = source.get("projection_matrix")
    projection = projection if isinstance(projection, Mapping) else {}
    factor = source.get("local_or_augmented_factor_inventory")
    factor = factor if isinstance(factor, Mapping) else {}
    factor_payload = factor.get("augmented")
    factor_payload = factor_payload if isinstance(factor_payload, Mapping) else factor
    factor_matrix = factor_payload.get("matrix_stats")
    factor_entry = _compact_fields(
        factor_payload,
        (
            "factor_solver_type",
            "factor_nnz_corrected",
            "factor_nnz_corrected_source",
            "mumps_api_available",
            "mumps_raw_infog",
            "mumps_raw_rinfog",
        ),
    )
    if isinstance(factor_matrix, Mapping):
        factor_entry["matrix_stats"] = _compact_matrix(factor_matrix)
    qep_entry = _compact_fields(
        qep,
        (
            "full_shape",
            "reduced_shape",
            "positive_solver_converged_modes",
            "negative_solver_converged_modes",
        ),
    )
    selected_vectors = source.get("retained_right_left_eigenvector_bytes")
    selected_entry = (
        {
            "bytes": selected_vectors,
            "classification": "derived_from_vector_sizes",
        }
        if isinstance(selected_vectors, int) and selected_vectors > 0
        else _not_available()
    )
    objects: dict[str, Any] = {
        "qep_matrices": qep_entry,
        "raw_candidate_modes": _compact_fields(
            qep,
            (
                "candidate_modes",
                "positive_solver_converged_modes",
                "negative_solver_converged_modes",
            ),
        ),
        "selected_biorthogonal_bases": selected_entry,
        "canonical_traces": _not_available(),
        "projection_matrices": {
            side: _compact_matrix(stats) for side, stats in projection.items()
        }
        or _not_available(),
        "traction_matrices": _not_available(),
        "local_fe_dtn": {
            side: _compact_matrix(hybrid.get(f"{side}_matrix_stats"))
            for side in ("bottom", "top")
        }
        if any(f"{side}_matrix_stats" in hybrid for side in ("bottom", "top"))
        else _not_available(),
        "hybrid_augmented_matrix": {
            "matrix_size": hybrid["matrix_size"]
            for key in ("matrix_size",)
            if key in hybrid
        }
        | (
            {"matrix_stats": _compact_matrix(hybrid["matrix_stats"])}
            if isinstance(hybrid.get("matrix_stats"), Mapping)
            else {}
        )
        | (
            {"inserted_nnz_by_block": hybrid["inserted_nnz_by_block"]}
            if isinstance(hybrid.get("inserted_nnz_by_block"), Mapping)
            else {}
        )
        | {"classification": "measured_from_worker_record"}
        if any(
            key in hybrid
            for key in ("matrix_size", "matrix_stats", "inserted_nnz_by_block")
        )
        else _not_available(),
        "factor": factor_entry,
        "modal_schur": _not_available("not_applicable"),
        "field_reconstruction": _compact_fields(
            record.get("physical_field_reconstruction"),
            ("sample_payload_bytes",),
        ),
    }
    return {
        "schema": "task039.memory-object-ledger.v1",
        "status": "measured_from_worker_record" if source else "not_available",
        "classification": "worker_record_fields_only" if source else "not_available",
        "objects": objects,
    }


def task039_write_memory_object_ledger(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(task039_h5_memory_object_ledger(record), ensure_ascii=False) + "\n",
        encoding="utf-8",
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


__all__ = [
    "TASK039_E10_STAGE_ORDER",
    "TASK039_V2_H5_STAGE_ORDER",
    "task039_e10_ledger",
    "task039_e10_stage_event",
    "task039_h5_hybrid_direct_formal_profile",
    "task039_h5_hybrid_iterative_formal_profile",
    "task039_h5_memory_object_ledger",
    "task039_read_new_markers",
    "task039_stage_target",
    "task039_v3_2d_formal_profile",
    "task039_v2_h5_stage_name",
    "task039_v2_h5_stage_event",
    "task039_write_memory_object_ledger",
]
