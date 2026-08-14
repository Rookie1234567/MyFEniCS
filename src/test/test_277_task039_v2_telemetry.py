"""Small V2 h5 telemetry contracts using a fake worker only."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from benchmarks.task039_memory_telemetry import (
    TASK039_E10_STAGE_ORDER,
    TASK039_V2_H5_STAGE_ORDER,
    task039_h5_memory_object_ledger,
    task039_read_new_markers,
    task039_stage_target,
    task039_v2_h5_stage_event,
)
from src.io import load_and_resolve
from src.io.execution_plan import ExecutionPlan
from src.runners import task038_launcher as launcher
from src.runners import task039_hybrid_direct as adapter


ROOT = Path(__file__).resolve().parents[2]
H5_HYBRID = ROOT / "input/official/task039/5nm_p6h5_hybrid_direct_m480_mpi8.dat"


class _FinishedProcess:
    pid = 7711

    def poll(self):
        return 0

    def wait(self):
        return 0


def _authority(*, complete=True):
    return {
        "memory_authority_bytes": 123456,
        "process_tree": {
            "root_pid": 7711,
            "rss_bytes": 123456,
            "swap_bytes": 0,
            "all_status_readable": True,
            "smaps": {
                "complete": complete,
                "pss_bytes": 111111 if complete else None,
                "uss_bytes": 99999 if complete else None,
            },
        },
        "job_cgroup": {"dedicated_job_cgroup": False},
    }


def _plan(spec, run_directory):
    return ExecutionPlan(
        argv=("fake-worker",),
        shell=False,
        executable=Path("/fake/python"),
        worker_module="fake",
        method="hybrid_direct",
        mpi_size=8,
        requested_modes=480,
        physical_model_sha256=spec.physical_model_sha256,
        input_sha256=spec.input_sha256,
        source_sha="a" * 40,
        adapter_identity="task039.hybrid_direct",
        adapter_available=True,
        contract_probe=False,
        task039_trace_audit=False,
        expected_output_directory=run_directory,
        expected_resolved_config=run_directory / "resolved_config.json",
        expected_manifest=run_directory / "run_manifest.json",
    )


def test_v2_stage_event_order_and_missing_capacity():
    events = [
        task039_v2_h5_stage_event(stage, elapsed_seconds=index)
        for index, stage in enumerate(TASK039_V2_H5_STAGE_ORDER)
    ]
    assert [event["stage"] for event in events] == list(TASK039_V2_H5_STAGE_ORDER)
    assert [event["stage_index"] for event in events] == list(range(18))
    assert events[0]["object_capacity"] == {
        "status": "not_available",
        "classification": "not_available",
    }


def test_worker_marker_mapping_is_exactly_the_frozen_18_stage_order():
    worker_labels = [
        "baseline_before_mesh",
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
        "mumps_analysis_ready_when_available",
        "direct_factor_or_iterative_side_factors_ready",
        "solution_ready",
        "field_reconstruction_start",
        "field_reconstruction_peak",
        "postprocess_peak",
        "all_modal_qep_temporaries_released",
        "final_cleanup",
    ]
    mapped = [
        target
        for label in worker_labels
        if (target := task039_stage_target(label, formal_v2_h5=True)) is not None
    ]
    assert mapped == list(TASK039_V2_H5_STAGE_ORDER)
    assert len(mapped) == len(set(mapped)) == 18
    assert all(
        task039_stage_target(stage, formal_v2_h5=False) == stage
        for stage in TASK039_E10_STAGE_ORDER
    )
    assert task039_stage_target("baseline_before_mesh", formal_v2_h5=False) is None


def test_partial_marker_without_newline_is_not_consumed(tmp_path):
    path = tmp_path / "markers.jsonl"
    path.write_text('{"stage": "baseline_before_mesh"', encoding="utf-8")
    assert task039_read_new_markers(path, 0) == ([], 0)
    path.write_text('{"stage": "baseline_before_mesh"}\n', encoding="utf-8")
    records, offset = task039_read_new_markers(path, 0)
    assert records == [{"stage": "baseline_before_mesh"}]
    assert offset == path.stat().st_size


def test_formal_h5_worker_writes_samples_stages_and_ledger(tmp_path, monkeypatch):
    spec = replace(load_and_resolve(H5_HYBRID), expected_output_parent=tmp_path)
    run_directory = tmp_path / "run"
    marker_path = run_directory / "numerical_output/memory_stage_markers.raw.jsonl"
    marker_path.parent.mkdir(parents=True)
    marker_path.write_text(
        "".join(
            json.dumps(
                task039_v2_h5_stage_event(stage, elapsed_seconds=index),
                ensure_ascii=False,
            )
            + "\n"
            for index, stage in enumerate(TASK039_V2_H5_STAGE_ORDER)
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        launcher,
        "_task039_memory_budget",
        lambda _execution: {
            "configured_warning_memory_gib": 170.0,
            "configured_critical_memory_gib": 195.0,
            "absolute_terminate_memory_bytes": 224000000000,
            "effective_terminate_memory_gib": 208.6162567138672,
        },
    )
    result = launcher._run_worker(
        _plan(spec, run_directory),
        spec,
        run_directory,
        popen_factory=lambda *_args, **_kwargs: _FinishedProcess(),
        sample_factory=lambda _pid: _authority(),
        terminate_factory=lambda _process: {"requested": True},
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: None,
        poll_interval=0.25,
    )
    numerical_output = run_directory / "numerical_output"
    samples = [
        json.loads(line)
        for line in (numerical_output / "process_tree_samples.jsonl")
        .read_text()
        .splitlines()
    ]
    stages = [
        json.loads(line)
        for line in (numerical_output / "memory_stages.jsonl").read_text().splitlines()
    ]
    ledger = json.loads(
        (numerical_output / "memory_object_ledger.json").read_text(encoding="utf-8")
    )
    assert result["result_classification"] == "worker_exit0"
    assert result["resource_authority"]["v2_h5_formal_telemetry"][
        "process_tree_sample_count"
    ] == len(samples)
    assert samples[0]["rss_bytes"] == 123456
    assert samples[0]["pss_bytes"] == 111111
    assert samples[0]["uss_bytes"] == 99999
    assert samples[0]["swap_bytes"] == 0
    assert [row["stage"] for row in stages] == list(TASK039_V2_H5_STAGE_ORDER)
    assert all(row["sample_status"] == "measured" for row in stages)
    assert ledger["status"] == "not_available"


def test_formal_h5_incomplete_smaps_never_becomes_zero(tmp_path, monkeypatch):
    spec = replace(load_and_resolve(H5_HYBRID), expected_output_parent=tmp_path)
    run_directory = tmp_path / "run"
    marker_path = run_directory / "numerical_output/memory_stage_markers.raw.jsonl"
    marker_path.parent.mkdir(parents=True)
    marker_path.write_text(
        json.dumps(task039_v2_h5_stage_event("baseline_before_mesh", elapsed_seconds=0))
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        launcher,
        "_task039_memory_budget",
        lambda _execution: {
            "configured_warning_memory_gib": 170.0,
            "configured_critical_memory_gib": 195.0,
            "absolute_terminate_memory_bytes": 224000000000,
            "effective_terminate_memory_gib": 208.6162567138672,
        },
    )
    launcher._run_worker(
        _plan(spec, run_directory),
        spec,
        run_directory,
        popen_factory=lambda *_args, **_kwargs: _FinishedProcess(),
        sample_factory=lambda _pid: _authority(complete=False),
        terminate_factory=lambda _process: {"requested": True},
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: None,
        poll_interval=0.25,
    )
    sample = json.loads(
        (run_directory / "numerical_output/process_tree_samples.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert sample["pss_bytes"] is None
    assert sample["uss_bytes"] is None
    assert sample["sample_status"] == "measured"
    assert task039_h5_memory_object_ledger({})["status"] == "not_available"


def test_h5_object_ledger_compacts_nested_factor_and_field_payload():
    ledger = task039_h5_memory_object_ledger(
        {
            "object_payload_ledger": {
                "local_or_augmented_factor_inventory": {
                    "augmented": {
                        "factor_solver_type": "mumps",
                        "factor_nnz_corrected": 2_597_000_000,
                        "matrix_stats": {
                            "matrix_rows": 337564,
                            "matrix_nnz_used": 298136764,
                            "matrix_memory_estimate_bytes": 123456,
                            "memory": 0,
                        },
                    }
                }
            },
            "physical_field_reconstruction": {"sample_payload_bytes": 4096},
        }
    )
    factor = ledger["objects"]["factor"]
    assert factor["factor_solver_type"] == "mumps"
    assert factor["factor_nnz_corrected"] == 2_597_000_000
    assert factor["matrix_stats"]["matrix_memory_estimate_bytes"] == 123456
    assert "memory" not in factor["matrix_stats"]
    assert ledger["objects"]["field_reconstruction"] == {
        "sample_payload_bytes": 4096,
        "classification": "measured_from_worker_record",
    }


def test_h5_adapter_passes_raw_marker_path_only_for_formal_profile(
    tmp_path, monkeypatch
):
    payload = load_and_resolve(H5_HYBRID).as_jsonable()
    captured = {}

    def fake_runner(*args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)
        return {"status": "formal_fake_record"}

    monkeypatch.setattr(adapter, "_default_runner", fake_runner)
    monkeypatch.setattr(adapter, "_authority_errors", lambda *_args: [])
    result = adapter.run_task039_hybrid_direct(
        payload,
        tmp_path,
        source_sha="a" * 40,
    )
    assert result["passed"] is True
    assert captured["args"][5] is None
    assert captured["task039_stage_marker_path"] == (
        tmp_path / "numerical_output/memory_stage_markers.raw.jsonl"
    )
