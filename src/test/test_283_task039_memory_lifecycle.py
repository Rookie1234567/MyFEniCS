from __future__ import annotations

import json
from pathlib import Path

from benchmarks.task039_memory_telemetry import (
    TASK039_V2_H5_STAGE_ORDER,
    task039_parse_memory_lifecycle,
)


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _complete_fixture(
    root: Path,
    *,
    nonmonotonic_samples: bool = False,
    collision: bool = False,
) -> None:
    output = root / "numerical_output"
    stages = []
    samples = []
    for index, stage in enumerate(TASK039_V2_H5_STAGE_ORDER):
        marker = float(index)
        sample_elapsed = marker + 0.1
        if collision and index == 2:
            sample_elapsed = 1.1
        stages.append(
            {
                "stage": stage,
                "stage_index": index,
                "marker_elapsed_seconds": marker,
                "sample_elapsed_seconds": sample_elapsed,
                "rss_bytes": (index + 1) * 100,
                "pss_bytes": (index + 1) * 80,
                "uss_bytes": (index + 1) * 60,
                "swap_bytes": 0,
                "sample_status": "measured",
                "marker_detail": {"after_destroy": index == 16},
                "object_capacity": {"status": "not_available"},
            }
        )
        samples.append(
            {
                "elapsed_seconds": sample_elapsed,
                "timestamp_utc": f"2026-01-01T00:00:{index:02d}Z",
                "rss_bytes": (index + 1) * 100,
                "pss_bytes": (index + 1) * 80,
                "uss_bytes": (index + 1) * 60,
                "swap_bytes": 0,
                "sample_status": "measured",
            }
        )
    if nonmonotonic_samples:
        samples[1]["elapsed_seconds"] = 0.05
    _write_jsonl(output / "memory_stages.jsonl", stages)
    _write_jsonl(output / "process_tree_samples.jsonl", samples)
    (output / "memory_object_ledger.json").write_text(
        json.dumps(
            {
                "schema": "task039.memory-object-ledger.v1",
                "status": "measured_from_worker_record",
                "classification": "worker_record_fields_only",
                "objects": {"qep_matrices": {}, "factor": {}},
            }
        ),
        encoding="utf-8",
    )
    (root / "run_summary.json").write_text(
        json.dumps(
            {
                "resource_authority": {
                    "process_tree_peak_rss_mb": 1.0,
                    "peak_pss_mb": 0.8,
                    "peak_uss_mb": 0.6,
                    "process_tree_peak_swap_mb": 0.0,
                    "smaps_attempted_sample_count": 18,
                    "smaps_complete_sample_count": 18,
                }
            }
        ),
        encoding="utf-8",
    )


def test_lifecycle_parser_aligns_stages_deltas_and_release_marker(
    tmp_path: Path,
) -> None:
    root = tmp_path / "complete"
    _complete_fixture(root)

    result = task039_parse_memory_lifecycle(root)

    assert result["status"] == "measured"
    assert result["stage_order"]["complete_unique_ordered"] is True
    assert result["sample_coverage"]["sample_count"] == 18
    stage = result["stages"][1]
    assert stage["entry_sample_elapsed_seconds"] == 1.1
    assert result["stages"][0]["local_peak"]["rss_bytes"]["bytes"] == 100
    assert stage["local_peak"]["rss_bytes"]["bytes"] == 200
    assert stage["rss_delta_from_previous_stage"]["bytes"] == 100
    assert result["stages"][16]["objects"]["after_destroy_marker"] is True
    assert (
        result["allocator_high_water_after_release"]["allocator_status"]
        == "not_available"
    )
    assert result["peaks"]["from_process_tree_samples"]["rss_bytes"]["bytes"] == 1800
    assert result["peaks"]["from_process_tree_samples"]["rss_bytes"]["GiB"] > 0


def test_lifecycle_parser_marks_clock_and_units_without_inference(
    tmp_path: Path,
) -> None:
    root = tmp_path / "clock"
    _complete_fixture(root, nonmonotonic_samples=True)

    result = task039_parse_memory_lifecycle(root)

    assert result["timebase"]["stage_clock"] == "relative_elapsed_seconds"
    assert result["sample_coverage"]["sample_elapsed_monotonic"] is False
    assert result["timebase"]["monotonic_consistent"] is False
    value = result["peaks"]["from_run_summary"]["rss_bytes"]
    assert value["MiB"] == 1.0
    assert value["GiB"] == 1.0 / 1024.0
    assert value["decimal_GB"] == 2**20 / 1.0e9


def test_lifecycle_parser_missing_samples_is_not_available(tmp_path: Path) -> None:
    root = tmp_path / "partial"
    _complete_fixture(root)
    (root / "numerical_output" / "process_tree_samples.jsonl").unlink()
    (root / "numerical_output" / "memory_object_ledger.json").unlink()

    result = task039_parse_memory_lifecycle(root)

    assert result["status"] == "partial"
    assert result["missing_or_incomplete"] == [
        "process_tree_samples",
        "memory_object_ledger",
    ]
    assert result["stages"][0]["status"] == "not_available"
    assert result["peaks"]["from_process_tree_samples"]["rss_bytes"]["status"] == (
        "not_available"
    )


def test_lifecycle_parser_marks_same_anchor_collision(tmp_path: Path) -> None:
    root = tmp_path / "collision"
    _complete_fixture(root, collision=True)

    result = task039_parse_memory_lifecycle(root)
    stage = result["stages"][1]

    assert stage["entry_memory"]["rss_bytes"]["bytes"] == 200
    assert stage["interval_resolution"]["collision"] is True
    assert stage["local_peak"]["rss_bytes"]["status"] == "not_available"
    assert stage["rss_delta_from_previous_stage"]["status"] == "not_available"


def test_lifecycle_parser_absent_run_is_not_available(tmp_path: Path) -> None:
    result = task039_parse_memory_lifecycle(tmp_path / "historical_without_telemetry")

    assert result["status"] == "not_available"
    assert len(result["stages"]) == len(TASK039_V2_H5_STAGE_ORDER)
    assert result["all_required_artifacts_present"] is False
