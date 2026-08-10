from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import benchmarks.run_task037_extra_candidate_h as candidate_h
from benchmarks.run_task037_extra_candidate_h import (
    H1R32_ACTION_SECONDS_PER_ROW_LIMIT,
    H1R32_ALPHA_PAYLOAD_LIMIT,
    H1R32_AXIS_CELL_COUNTS,
    H1R32_CANDIDATE_APPLY_COUNT,
    H1R32_GLOBAL_CELLS,
    H1R32_GLOBAL_ROWS,
    H1R32_H10_GLOBAL_ROWS,
    H1R32_H10_PEAK_BYTES,
    H1R32_H10_PAYLOAD_BYTES,
    H1R32_H1_AXIS_CELL_COUNTS,
    H1R32_H1_GLOBAL_ROWS,
    H1R32_PACKED_BYTES_PER_ROW_LIMIT,
    H1R32_PAYLOAD_BYTES_PER_ROW_LIMIT,
    H1R32_PEAK_LIMIT_BYTES,
    H1R32_PEAK_SLOPE_BYTES_PER_ROW_LIMIT,
    H1R32_SOURCE_LABEL,
    H1R32_TIMEOUT_SECONDS,
    _evaluate_h1r32_worker_qualification,
    _h1r32_check_raw,
    _h1r32_scope,
    _h1r32_structured_hexa_identity,
    _h1r2_runtime_identity,
    _h1r3_file_metadata,
    _h1r3_path_metadata,
    _h1r32_file_metadata,
    _parser,
    _source_definition,
    _watchdog_command,
    attach_evidence_sha256,
    evidence_sha256_is_valid,
    run_h1r32_check,
)
from src.test.test_281_task037_extra_h1r2_runner_contract import (
    _candidate_audit,
    _measurement,
)


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _source_identity(sha: str) -> dict:
    return {
        "source_commit_full_sha": sha,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }


def _make_h10_authority(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    raw_dir = tmp_path / "h10"
    record_path = tmp_path / "h10_record.json"
    raw_dir.mkdir()
    source = _source_identity("a" * 40)
    raw_worker = attach_evidence_sha256(
        {
            "schema": "task037.candidate_h.h1r3.warm.worker.v1",
            "status": "pass",
            "qualification": {"status": "pass", "pass": True},
            "global_rows": H1R32_H10_GLOBAL_ROWS,
            "candidate_action_audit": {
                "global_rows": H1R32_H10_GLOBAL_ROWS,
                "retained_numeric_payload_global_sum_bytes": H1R32_H10_PAYLOAD_BYTES,
            },
            "source_at_start": source,
            "source_at_end": source,
        }
    )
    _write_json(raw_dir / "run_summary.json", raw_worker)
    (raw_dir / "worker_stdout.txt").write_text("h10 worker\n", encoding="utf-8")
    (raw_dir / "watchdog_timeline.jsonl").write_text("{}\n", encoding="utf-8")
    (raw_dir / "apply_telemetry.jsonl").write_text("{}\n", encoding="utf-8")
    _write_json(
        raw_dir / "h1r3_root_pid.json",
        {"schema": "task037.candidate_h.h1r3.root_pid.v1", "root_pid": 11},
    )
    manifest_path = raw_dir / "canonical/seed_17037/candidate_manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("{}\n", encoding="utf-8")
    base_artifacts = _h10_artifacts_without_watchdog(raw_dir, manifest_path)
    raw_watchdog = attach_evidence_sha256(
        {
            "schema": "task037.candidate_h.h1r3.warm.watchdog.v1",
            "status": "pass",
            "return_code": 0,
            "peak_process_tree_rss_bytes": H1R32_H10_PEAK_BYTES,
            "source_at_start": source,
            "source_at_end": source,
            "raw_artifacts": base_artifacts,
        }
    )
    _write_json(raw_dir / "watchdog_summary.json", raw_watchdog)
    all_artifacts = dict(base_artifacts)
    all_artifacts["watchdog_summary.json"] = _h1r3_path_metadata(
        raw_dir / "watchdog_summary.json", "watchdog_summary.json"
    )
    compact = attach_evidence_sha256(
        {
            "schema": "task037.candidate_h.h1r3.warm.compact_check.v1",
            "status": "pass",
            "pass": True,
            "source_identity": {
                "source_commit_full_sha": "a" * 40,
                "start": source,
                "end": source,
            },
            "raw_artifacts": all_artifacts,
            "measurement": {
                "global_rows": H1R32_H10_GLOBAL_ROWS,
                "retained_payload_global_sum_bytes": H1R32_H10_PAYLOAD_BYTES,
            },
            "memory_authority": {
                "completed_process_tree_peak_rss_bytes": H1R32_H10_PEAK_BYTES
            },
        }
    )
    _write_json(record_path, compact)
    monkeypatch.setattr(candidate_h, "H1R32_H10_RAW_DIR", raw_dir)
    monkeypatch.setattr(candidate_h, "H1R32_H10_RECORD", record_path)
    monkeypatch.setattr(candidate_h, "H1R32_H10_SOURCE_SHA", "a" * 40)
    monkeypatch.setattr(
        candidate_h,
        "H1R32_H10_RECORD_SHA256",
        hashlib.sha256(record_path.read_bytes()).hexdigest(),
    )
    return raw_dir, record_path


def _h10_artifacts_without_watchdog(raw_dir: Path, manifest_path: Path) -> dict:
    artifacts = _h1r3_file_metadata(raw_dir)
    artifacts["canonical/seed_17037/candidate_manifest.json"] = (
        _h1r3_path_metadata(
            manifest_path, "canonical/seed_17037/candidate_manifest.json"
        )
    )
    return artifacts


def _make_h1r31_prerequisite(tmp_path: Path, monkeypatch) -> Path:
    record_path = tmp_path / "h1r31_record.json"
    record = attach_evidence_sha256(
        {
            "schema": "task037.candidate_h.h1r3.mpi2.compact_check.v1",
            "status": "pass",
            "pass": True,
            "problems": [],
            "scope_boundary": {
                "H1R3.2": "eligible_by_review_v6",
                "H2": "locked",
            },
            "source_identity": {"source_commit_full_sha": "b" * 40},
        }
    )
    _write_json(record_path, record)
    monkeypatch.setattr(candidate_h, "H1R32_H1R31_RECORD", record_path)
    monkeypatch.setattr(
        candidate_h,
        "H1R32_H1R31_RECORD_SHA256",
        hashlib.sha256(record_path.read_bytes()).hexdigest(),
    )
    return record_path


def _make_h5_run(tmp_path: Path, monkeypatch) -> Path:
    _make_h10_authority(tmp_path, monkeypatch)
    _make_h1r31_prerequisite(tmp_path, monkeypatch)
    run_dir = tmp_path / "h5"
    run_dir.mkdir()
    measurement = _measurement()
    measurement.update(
        {
            "reference_apply_seconds": 10.0,
            "candidate_apply_seconds": 5.0,
            "candidate_repeat_apply_seconds": 5.0,
            "timing_reduction": "mpi_max",
            "canonical_export": False,
            "candidate_canonical_packet_count": None,
            "candidate_manifest": None,
        }
    )
    audit = _candidate_audit()
    audit.update(
        {
            "global_rows": H1R32_GLOBAL_ROWS,
            "constraint_count": 1,
            "last_packed_coefficient_bytes": 2048,
            "per_apply_bounded_temporary_bytes": 2048,
            "cell_schur_matrix_nnz": 0,
            "slab_matrix_nnz": 0,
            "cell_schur_matrix_materialized": False,
            "slab_matrix_materialized": False,
        }
    )
    scope = _h1r32_scope(
        global_rows=H1R32_GLOBAL_ROWS,
        constraint_count=1,
        global_cells=H1R32_GLOBAL_CELLS,
        axis_cell_counts=H1R32_AXIS_CELL_COUNTS,
    )
    qualification = _evaluate_h1r32_worker_qualification(
        measurement, audit, scope=scope
    )
    source = _source_identity("c" * 40)
    worker = attach_evidence_sha256(
        {
            "schema": "task037.candidate_h.h1r3.h5.worker.v1",
            "status": "pass",
            "mpi_size": 1,
            "global_rows": H1R32_GLOBAL_ROWS,
            "constraint_count": 1,
            "global_cells": H1R32_GLOBAL_CELLS,
            "axis_cell_counts": list(H1R32_AXIS_CELL_COUNTS),
            "scope": scope,
            "runtime_identity": _h1r2_runtime_identity(),
            "source_definitions": {
                H1R32_SOURCE_LABEL: measurement["source_definition"]
            },
            "measurements": [measurement],
            "candidate_action_audit": audit,
            "reference_action": {
                "type": "MpcFormActionContext",
                "same_worker": True,
                "apply_count": 1,
                "global_matrix_materialized": False,
            },
            "qualification": qualification,
            "source_at_start": source,
            "source_at_end": source,
        }
    )
    _write_json(run_dir / "run_summary.json", worker)
    (run_dir / "worker_stdout.txt").write_text("h5 worker\n", encoding="utf-8")
    timeline = [
        {
            "worker_alive": True,
            "worker_tree_rss_sum_bytes": 350000000,
            "process_tree_swap_bytes": 0,
            "process_tree_all_status_readable": True,
        },
        {
            "worker_alive": False,
            "worker_tree_rss_sum_bytes": 0,
            "process_tree_swap_bytes": 0,
            "process_tree_all_status_readable": True,
        },
    ]
    (run_dir / "watchdog_timeline.jsonl").write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in timeline),
        encoding="utf-8",
    )
    _write_json(
        run_dir / candidate_h.H1R32_ROOT_PID_FILE,
        {
            "schema": "task037.candidate_h.h1r3.h5.root_pid.v1",
            "root_pid": 12,
        },
    )
    watchdog = attach_evidence_sha256(
        {
            "schema": "task037.candidate_h.h1r3.h5.watchdog.v1",
            "command": _watchdog_command(
                SimpleNamespace(run_dir=run_dir), mode="h1r3_h5"
            ),
            "mpi_size": 1,
            "return_code": 0,
            "status": "pass",
            "controlled_stop": None,
            "timeout_seconds": 1800.0,
            "poll_interval_seconds": 0.25,
            "rss_limit_bytes": H1R32_PEAK_LIMIT_BYTES,
            "termination": {"requested": False, "method": None},
            "completion_elapsed_seconds": 1.0,
            "peak_process_tree_rss_bytes": 350000000,
            "worker_live_sample_count": 1,
            "worker_process_tree_swap_bytes": 0,
            "worker_swap_zero": True,
            "resource_authority_readable": True,
            "worker_summary_present": True,
            "worker_summary_status": "pass",
            "worker_summary_evidence_sha256_valid": True,
            "worker_qualification_recomputed": qualification,
            "worker_qualification_pass": True,
            "watchdog_runtime_identity": _h1r2_runtime_identity(),
            "worker_runtime_identity_match": True,
            "source_at_start": source,
            "source_at_end": source,
            "source_stable_clean": True,
            "raw_artifacts": _h1r32_file_metadata(run_dir),
        }
    )
    _write_json(run_dir / "watchdog_summary.json", watchdog)
    return run_dir


def test_h1r32_parser_and_fixed_identity_contract():
    parser = _parser()
    args = parser.parse_args(
        ["h1r3-h5-watchdog", "--run-dir", "relative/h5"]
    )
    command = _watchdog_command(args, mode="h1r3_h5")
    assert command[:3] == ["mpiexec", "-n", "1"]
    assert command[6:8] == ["h1r3-h5-worker", "--run-dir"]
    assert command[-1] == str(Path("relative/h5").resolve())
    assert H1R32_TIMEOUT_SECONDS == 1800.0
    assert H1R32_PEAK_LIMIT_BYTES == 805306368
    assert H1R32_CANDIDATE_APPLY_COUNT == 2
    for name in ("degree", "h_nm", "source", "repeat", "limit", "mpi_size"):
        assert not hasattr(args, name)
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["h1r3-h5-worker", "--run-dir", "h5", "--degree", "6"]
        )


@pytest.mark.parametrize(
    "axes,expected_cells,expected_rows",
    (
        (H1R32_AXIS_CELL_COUNTS, H1R32_GLOBAL_CELLS, H1R32_GLOBAL_ROWS),
        ((6, 3, 14), 252, H1R32_H10_GLOBAL_ROWS),
        (H1R32_H1_AXIS_CELL_COUNTS, 51 * 25 * 140, H1R32_H1_GLOBAL_ROWS),
    ),
)
def test_h1r32_structured_hexa_row_identity(axes, expected_cells, expected_rows):
    identity = _h1r32_structured_hexa_identity(axes)
    assert identity["global_cells"] == expected_cells
    assert identity["global_rows"] == expected_rows


def test_h1r32_good_checker_disables_canonical_and_preserves_raw(
    tmp_path, monkeypatch
):
    run_dir = _make_h5_run(tmp_path, monkeypatch)
    before = {
        path.relative_to(run_dir): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    }
    output = tmp_path / "compact.json"
    assert run_h1r32_check(
        run_dir, candidate_h.H1R32_H10_RAW_DIR, output
    ) == 0
    compact = json.loads(output.read_text(encoding="utf-8"))
    assert compact["pass"] is True
    assert compact["scope_boundary"]["H2"] == "locked"
    assert compact["measurement"]["canonical_export"] is False
    assert compact["measurement"]["canonical_packet_count"] is None
    assert compact["scaling"]["alpha_payload"] <= H1R32_ALPHA_PAYLOAD_LIMIT
    scaling = compact["scaling"]
    measurement = json.loads(
        (run_dir / "run_summary.json").read_text(encoding="utf-8")
    )["measurements"][0]
    audit = json.loads(
        (run_dir / "run_summary.json").read_text(encoding="utf-8")
    )["candidate_action_audit"]
    assert scaling["retained_payload_bytes_per_row"] == pytest.approx(
        audit["retained_numeric_payload_global_sum_bytes"] / H1R32_GLOBAL_ROWS
    )
    assert scaling["packed_temporary_bytes_per_row"] == pytest.approx(
        audit["last_packed_coefficient_bytes"] / H1R32_GLOBAL_ROWS
    )
    assert scaling["action_seconds_per_row"] == pytest.approx(
        measurement["candidate_repeat_apply_seconds"] / H1R32_GLOBAL_ROWS
    )
    assert scaling["N_h1_rows"] == H1R32_H1_GLOBAL_ROWS
    assert scaling["N_h1_axis_cell_counts"] == list(H1R32_H1_AXIS_CELL_COUNTS)
    assert evidence_sha256_is_valid(compact)
    for path in run_dir.rglob("*"):
        if path.is_file():
            assert before[path.relative_to(run_dir)] == path.read_bytes()


@pytest.mark.parametrize(
    "mutation",
    (
        "audit_missing",
        "packed_per_row",
        "alpha",
        "action_per_row",
        "b_peak",
        "peak",
        "swap",
        "h1r31_prerequisite",
        "h10_bytes",
    ),
)
def test_h1r32_checker_rejects_representative_fail_closed_mutations(
    tmp_path, monkeypatch, mutation
):
    run_dir = _make_h5_run(tmp_path, monkeypatch)
    worker_path = run_dir / "run_summary.json"
    worker = json.loads(worker_path.read_text(encoding="utf-8"))
    watchdog_path = run_dir / "watchdog_summary.json"
    watchdog = json.loads(watchdog_path.read_text(encoding="utf-8"))
    if mutation == "audit_missing":
        del worker["candidate_action_audit"]["cell_schur_matrix_nnz"]
    elif mutation == "packed_per_row":
        worker["candidate_action_audit"][
            "last_packed_coefficient_bytes"
        ] = H1R32_PACKED_BYTES_PER_ROW_LIMIT * H1R32_GLOBAL_ROWS + 1
    elif mutation == "alpha":
        target_payload = 50_000_000
        components = worker["candidate_action_audit"][
            "retained_numeric_payload_components"
        ]
        component_name = next(iter(components))
        components[component_name] += target_payload - sum(components.values())
        for name in (
            "retained_numeric_payload_local_bytes",
            "retained_numeric_payload_global_sum_bytes",
            "retained_numeric_payload_global_max_bytes",
        ):
            worker["candidate_action_audit"][name] = target_payload
    elif mutation == "action_per_row":
        worker["measurements"][0][
            "candidate_repeat_apply_seconds"
        ] = H1R32_ACTION_SECONDS_PER_ROW_LIMIT * H1R32_GLOBAL_ROWS + 1.0
    elif mutation in {"b_peak", "peak"}:
        peak = (
            H1R32_H10_PEAK_BYTES
            + (H1R32_GLOBAL_ROWS - H1R32_H10_GLOBAL_ROWS)
            * (H1R32_PEAK_SLOPE_BYTES_PER_ROW_LIMIT + 1)
        )
        if mutation == "peak":
            peak = H1R32_PEAK_LIMIT_BYTES + 1
        rows = [
            json.loads(line)
            for line in (run_dir / "watchdog_timeline.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        rows[0]["worker_tree_rss_sum_bytes"] = peak
        (run_dir / "watchdog_timeline.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        watchdog["peak_process_tree_rss_bytes"] = peak
    elif mutation == "swap":
        rows = [
            json.loads(line)
            for line in (run_dir / "watchdog_timeline.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        rows[0]["process_tree_swap_bytes"] = 1
        (run_dir / "watchdog_timeline.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        watchdog["worker_process_tree_swap_bytes"] = 1
    elif mutation == "h1r31_prerequisite":
        monkeypatch.setattr(candidate_h, "H1R32_H1R31_RECORD_SHA256", "0" * 64)
    elif mutation == "h10_bytes":
        h10_path = candidate_h.H1R32_H10_RAW_DIR / "run_summary.json"
        h10_path.write_bytes(h10_path.read_bytes() + b"\n")
    worker = attach_evidence_sha256(worker)
    _write_json(worker_path, worker)
    if mutation not in {"h1r31_prerequisite", "h10_bytes"}:
        watchdog["raw_artifacts"] = _h1r32_file_metadata(run_dir)
        watchdog = attach_evidence_sha256(watchdog)
        _write_json(watchdog_path, watchdog)
    output = tmp_path / "failed.json"
    assert run_h1r32_check(
        run_dir, candidate_h.H1R32_H10_RAW_DIR, output
    ) == 1
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["pass"] is False
    assert result["problems"]
    if mutation == "alpha":
        assert result["checks"]["scale.payload_per_row"] is True
        assert result["checks"]["scale.alpha_payload"] is False


def test_h1r32_negative_peak_slope_is_derived_from_both_peaks(
    tmp_path, monkeypatch
):
    run_dir = _make_h5_run(tmp_path, monkeypatch)
    timeline_path = run_dir / "watchdog_timeline.jsonl"
    rows = [
        json.loads(line)
        for line in timeline_path.read_text(encoding="utf-8").splitlines()
    ]
    negative_peak = H1R32_H10_PEAK_BYTES - 1000
    rows[0]["worker_tree_rss_sum_bytes"] = negative_peak
    timeline_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    watchdog_path = run_dir / "watchdog_summary.json"
    watchdog = json.loads(watchdog_path.read_text(encoding="utf-8"))
    watchdog["peak_process_tree_rss_bytes"] = negative_peak
    watchdog["raw_artifacts"] = _h1r32_file_metadata(run_dir)
    _write_json(watchdog_path, attach_evidence_sha256(watchdog))
    output = tmp_path / "negative_slope.json"
    assert run_h1r32_check(
        run_dir, candidate_h.H1R32_H10_RAW_DIR, output
    ) == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    slope = (
        negative_peak - H1R32_H10_PEAK_BYTES
    ) / (H1R32_GLOBAL_ROWS - H1R32_H10_GLOBAL_ROWS)
    assert result["scaling"]["b_peak_bytes_per_row"] == pytest.approx(slope)
    assert result["scaling"]["b_peak_bytes_per_row"] < 0.0
    assert result["checks"]["scale.peak_slope"] is True
    assert result["scaling"]["P_h1_pred_bytes"] == pytest.approx(
        H1R32_H10_PEAK_BYTES
        + slope * (H1R32_H1_GLOBAL_ROWS - H1R32_H10_GLOBAL_ROWS)
    )
