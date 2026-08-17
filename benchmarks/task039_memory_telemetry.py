"""Small Task39-only lifecycle event and ledger helpers."""

from __future__ import annotations

import json
import math
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


def task039_v4_h4_hybrid_direct_formal_profile(
    payload: Mapping[str, Any],
) -> bool:
    """Return true only for the explicit V4 h4 Hybrid-direct profile."""

    method = payload.get("method")
    discretization = payload.get("discretization")
    execution = payload.get("execution")
    identity = payload.get("identity", payload)
    model_id = identity.get("model_id") if isinstance(identity, Mapping) else None
    return bool(
        isinstance(method, Mapping)
        and method.get("kind") == "hybrid_direct"
        and method.get("requested_modes_per_direction") == 480
        and model_id == "task039_5nm_v4_1deg_s5_hybrid_direct_m480"
        and isinstance(discretization, Mapping)
        and float(discretization.get("mesh_target_nm", float("nan"))) == 4.0
        and isinstance(execution, Mapping)
        and execution.get("mpi_size") == 8
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


_MEMORY_FIELDS = ("rss_bytes", "pss_bytes", "uss_bytes", "swap_bytes")


def _memory_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _not_available()
    if not math.isfinite(float(value)) or float(value) < 0:
        return _not_available()
    bytes_value = int(value)
    return {
        "bytes": bytes_value,
        "MiB": bytes_value / 2**20,
        "GiB": bytes_value / 2**30,
        "decimal_GB": bytes_value / 1.0e9,
        "classification": "measured_from_process_tree_sample",
    }


def _memory_snapshot(record: Mapping[str, Any]) -> dict[str, Any]:
    return {field: _memory_value(record.get(field)) for field in _MEMORY_FIELDS}


def _read_jsonl_records(path: Path) -> list[dict[str, Any]] | None:
    if not path.is_file():
        return None
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"JSONL record is not an object: {path}")
        records.append(value)
    return records


def _sample_elapsed(record: Mapping[str, Any]) -> float | None:
    value = record.get("elapsed_seconds")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value >= 0 else None


def task039_parse_memory_lifecycle(run_dir: Path | str) -> dict[str, Any]:
    """Parse existing Task39 stage and process-tree telemetry without rerunning it."""

    root = Path(run_dir).resolve()
    output = root / "numerical_output"
    stage_path = output / "memory_stages.jsonl"
    sample_path = output / "process_tree_samples.jsonl"
    ledger_path = output / "memory_object_ledger.json"
    summary_path = root / "run_summary.json"
    stage_records = _read_jsonl_records(stage_path)
    sample_records = _read_jsonl_records(sample_path)
    ledger = (
        json.loads(ledger_path.read_text(encoding="utf-8"))
        if ledger_path.is_file()
        else None
    )
    summary = (
        json.loads(summary_path.read_text(encoding="utf-8"))
        if summary_path.is_file()
        else {}
    )

    valid_samples: list[dict[str, Any]] = []
    invalid_sample_count = 0
    if sample_records is not None:
        for record in sample_records:
            elapsed = _sample_elapsed(record)
            if elapsed is None:
                invalid_sample_count += 1
                continue
            valid_samples.append({"elapsed_seconds": elapsed, **record})
    sample_elapsed_values = [item["elapsed_seconds"] for item in valid_samples]
    sample_monotonic = bool(sample_elapsed_values) and all(
        left <= right
        for left, right in zip(sample_elapsed_values, sample_elapsed_values[1:])
    )

    names = [record.get("stage") for record in stage_records or []]
    stage_indices = [record.get("stage_index") for record in stage_records or []]
    stage_markers = [
        record.get("marker_elapsed_seconds") for record in stage_records or []
    ]
    marker_values = [
        float(value)
        for value in stage_markers
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0
    ]
    marker_monotonic = bool(marker_values) and all(
        left <= right for left, right in zip(marker_values, marker_values[1:])
    )
    order_pass = names == list(TASK039_V2_H5_STAGE_ORDER) and stage_indices == list(
        range(len(TASK039_V2_H5_STAGE_ORDER))
    )
    stage_by_name = {
        record.get("stage"): record
        for record in stage_records or []
        if isinstance(record.get("stage"), str)
    }

    def interval_samples(
        start: float | None, end: float | None, *, include_end: bool
    ) -> list[dict[str, Any]]:
        if start is None or end is None or end < start:
            return []
        if include_end:
            return [
                sample
                for sample in valid_samples
                if start <= sample["elapsed_seconds"] <= end
            ]
        return [
            sample
            for sample in valid_samples
            if start <= sample["elapsed_seconds"] < end
        ]

    stage_output: list[dict[str, Any]] = []
    previous_rss: int | None = None
    for index, stage in enumerate(TASK039_V2_H5_STAGE_ORDER):
        record = stage_by_name.get(stage)
        if record is None or not order_pass:
            stage_output.append(
                {
                    "stage": stage,
                    "stage_index": index,
                    "status": "not_available",
                    "reason": "stage order or marker record incomplete",
                }
            )
            previous_rss = None
            continue
        anchor = _sample_elapsed(
            {"elapsed_seconds": record.get("sample_elapsed_seconds")}
        )
        next_record = (
            stage_records[index + 1]
            if stage_records is not None and index + 1 < len(stage_records)
            else None
        )
        next_anchor = (
            _sample_elapsed(
                {"elapsed_seconds": next_record.get("sample_elapsed_seconds")}
            )
            if isinstance(next_record, Mapping)
            else (max(sample_elapsed_values) if sample_elapsed_values else None)
        )
        collision = (
            anchor is not None and next_anchor is not None and anchor == next_anchor
        )
        samples = (
            []
            if collision
            else interval_samples(
                anchor,
                next_anchor,
                include_end=index == len(TASK039_V2_H5_STAGE_ORDER) - 1,
            )
        )
        peak: dict[str, dict[str, Any]] = {}
        for field in _MEMORY_FIELDS:
            values = [
                sample[field]
                for sample in samples
                if isinstance(sample.get(field), (int, float))
                and not isinstance(sample.get(field), bool)
                and math.isfinite(float(sample[field]))
                and float(sample[field]) >= 0
            ]
            peak[field] = _memory_value(max(values)) if values else _not_available()
        exit_sample = samples[-1] if samples else None
        rss_value = peak["rss_bytes"].get("bytes")
        delta = _not_available()
        if isinstance(rss_value, int) and previous_rss is not None:
            delta = {
                "bytes": rss_value - previous_rss,
                "relative": (rss_value - previous_rss) / max(previous_rss, 1),
                "classification": "derived_from_adjacent_stage_peaks",
            }
        if collision:
            delta = _not_available()
            previous_rss = None
        elif isinstance(rss_value, int):
            previous_rss = rss_value
        detail = record.get("marker_detail")
        detail = detail if isinstance(detail, Mapping) else {}
        capacity = record.get("object_capacity")
        capacity = capacity if isinstance(capacity, Mapping) else {}
        objects = {
            "created": capacity.get("created", _not_available()),
            "destroyed": capacity.get("destroyed", _not_available()),
            "after_destroy_marker": detail.get("after_destroy", False),
            "classification": "marker_or_worker_record_only",
        }
        stage_output.append(
            {
                "stage": stage,
                "stage_index": index,
                "status": "measured" if samples else "not_available",
                "marker_elapsed_seconds": record.get("marker_elapsed_seconds"),
                "entry_sample_elapsed_seconds": anchor,
                "exit_sample_elapsed_seconds": next_anchor,
                "interval_sample_count": len(samples),
                "interval_resolution": {
                    "collision": collision,
                    "status": "not_available" if collision else "sampled_interval",
                },
                "entry_memory": _memory_snapshot(record),
                "exit_memory": _memory_snapshot(exit_sample)
                if exit_sample
                else _not_available(),
                "local_peak": peak,
                "rss_delta_from_previous_stage": delta,
                "objects": objects,
            }
        )

    def global_peak(field: str) -> dict[str, Any]:
        values = [
            sample[field]
            for sample in valid_samples
            if isinstance(sample.get(field), (int, float))
            and not isinstance(sample.get(field), bool)
            and math.isfinite(float(sample[field]))
            and float(sample[field]) >= 0
        ]
        return _memory_value(max(values)) if values else _not_available()

    authority = summary.get("resource_authority")
    authority = authority if isinstance(authority, Mapping) else {}
    summary_peaks: dict[str, Any] = {}
    for field, key in (
        ("rss_bytes", "process_tree_peak_rss_mb"),
        ("pss_bytes", "peak_pss_mb"),
        ("uss_bytes", "peak_uss_mb"),
        ("swap_bytes", "process_tree_peak_swap_mb"),
    ):
        value = authority.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            item = _memory_value(float(value) * 2**20)
            item["source"] = f"run_summary.{key}; *_mb interpreted as MiB"
            summary_peaks[field] = item

    release = next(
        (
            item
            for item in stage_output
            if item["stage"] == "modal_qep_temporaries_released"
        ),
        None,
    )
    release_entry = (
        release.get("entry_memory") if isinstance(release, Mapping) else None
    )
    release_rss = (
        release_entry.get("rss_bytes", _not_available())
        if isinstance(release_entry, Mapping)
        else _not_available()
    )
    allocator_high_water = {
        "status": "not_available",
        "allocator_status": "not_available",
        "classification": "rss_retention_diagnostic_only",
        "reason": "allocator counters are absent; RSS retention is not an allocator measurement",
        "rss_retention_diagnostic": release_rss,
    }
    required_present = {
        "memory_stages": stage_records is not None,
        "process_tree_samples": sample_records is not None,
        "memory_object_ledger": ledger is not None,
    }
    all_present = all(required_present.values())
    measured = bool(stage_records and valid_samples and order_pass)
    return {
        "schema": "task039.memory-lifecycle-offline.v1",
        "run_directory": str(root),
        "status": "measured"
        if measured
        else ("partial" if any(required_present.values()) else "not_available"),
        "units": {
            "memory_bytes": "bytes",
            "memory_mib": "bytes / 2**20",
            "memory_gib": "bytes / 2**30",
            "memory_decimal_gb": "bytes / 1e9",
            "elapsed": "relative seconds from run/telemetry monotonic clock",
        },
        "artifacts": {
            "memory_stages": {
                "path": str(stage_path),
                "present": required_present["memory_stages"],
            },
            "process_tree_samples": {
                "path": str(sample_path),
                "present": required_present["process_tree_samples"],
            },
            "memory_object_ledger": {
                "path": str(ledger_path),
                "present": required_present["memory_object_ledger"],
            },
        },
        "stage_order": {
            "expected": list(TASK039_V2_H5_STAGE_ORDER),
            "observed": names,
            "complete_unique_ordered": order_pass,
        },
        "sample_coverage": {
            "sample_count": len(sample_records or []),
            "valid_sample_count": len(valid_samples),
            "invalid_sample_count": invalid_sample_count,
            "first_elapsed_seconds": sample_elapsed_values[0]
            if sample_elapsed_values
            else None,
            "last_elapsed_seconds": sample_elapsed_values[-1]
            if sample_elapsed_values
            else None,
            "sample_elapsed_monotonic": sample_monotonic
            if valid_samples
            else "not_available",
            "smaps_attempted_sample_count": authority.get(
                "smaps_attempted_sample_count", "not_available"
            ),
            "smaps_complete_sample_count": authority.get(
                "smaps_complete_sample_count", "not_available"
            ),
        },
        "timebase": {
            "stage_clock": "relative_elapsed_seconds",
            "sample_clock": "relative_elapsed_seconds",
            "wall_timestamp_present": bool(
                valid_samples
                and all(
                    isinstance(item.get("timestamp_utc"), str) for item in valid_samples
                )
            ),
            "monotonic_consistent": marker_monotonic and sample_monotonic
            if marker_values and valid_samples
            else "not_available",
            "alignment": "stage marker aligned to first process-tree sample at or after marker",
        },
        "peaks": {
            "from_process_tree_samples": {
                field: global_peak(field) for field in _MEMORY_FIELDS
            },
            "from_run_summary": summary_peaks or _not_available(),
        },
        "stages": stage_output,
        "object_ledger": {
            "status": ledger.get("status")
            if isinstance(ledger, Mapping)
            else "not_available",
            "classification": ledger.get("classification")
            if isinstance(ledger, Mapping)
            else "not_available",
            "object_names": list(ledger.get("objects", {}).keys())
            if isinstance(ledger, Mapping)
            and isinstance(ledger.get("objects"), Mapping)
            else [],
        },
        "allocator_high_water_after_release": allocator_high_water,
        "missing_or_incomplete": [
            name for name, present in required_present.items() if not present
        ]
        + (["stage_order"] if stage_records is not None and not order_pass else []),
        "all_required_artifacts_present": all_present,
    }


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
    "task039_v4_h4_hybrid_direct_formal_profile",
    "task039_h5_memory_object_ledger",
    "task039_parse_memory_lifecycle",
    "task039_read_new_markers",
    "task039_stage_target",
    "task039_v3_2d_formal_profile",
    "task039_v2_h5_stage_name",
    "task039_v2_h5_stage_event",
    "task039_write_memory_object_ledger",
]
