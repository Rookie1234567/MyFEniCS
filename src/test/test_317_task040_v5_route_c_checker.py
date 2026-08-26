from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import benchmarks.check_task040_v5_route_c as checker


FORMAL_SOURCE_SHA = "a" * 40
CHECKER_SOURCE_SHA = "b" * 40


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _external_observed() -> dict[str, Any]:
    return {
        "matrix_objects": {"C": 0, "D": 0, "H": 0},
        "minimal_external_component_instances_total": 4,
        "minimal_external_coupling_construction_call_count": 2,
        "minimal_external_coupling_kind_count": 1,
        "minimal_external_coupling_objects_constructed": 1,
        "minimal_external_peak_live_components": 2,
        "minimal_external_surface_component_count": 2,
    }


def _route_record(label: str, scale: float) -> dict[str, Any]:
    return {
        "label": label,
        "final_iteration": 128,
        "conditional_256_authorized": False,
        "conditional_256_completed": False,
        "checkpoints": {
            "64": {"true_residual_relative": scale},
            "128": {"true_residual_relative": scale + 0.1},
        },
    }


def _run_manifest() -> dict[str, Any]:
    records = {
        checker.ROUTE_C_LABELS[0]: _route_record(checker.ROUTE_C_LABELS[0], 0.9),
        checker.ROUTE_C_LABELS[1]: _route_record(checker.ROUTE_C_LABELS[1], 1.0),
    }
    external = _external_observed()
    direction = {
        "basis_persistence_observed": True,
        "basis_persistence_all_pass": True,
        "canonical_interface_trace_observed": True,
        "canonical_interface_trace_all_pass": True,
        "interface_projection_observed": True,
        "interface_projection_all_pass": True,
        "pass": True,
        "replicated": False,
    }
    route = {
        "labels": list(checker.ROUTE_C_LABELS),
        "records": records,
        "conditional_checkpoint": 256,
        "conditional_256_gate": {
            "authorized_pass": False,
            "aggregate_pass": False,
            "aggregate_completed": False,
            "per_source": {
                label: {
                    "authorized": False,
                    "completed": False,
                    "final_iteration": 128,
                }
                for label in checker.ROUTE_C_LABELS
            },
        },
        "shared_slow_directions": {
            "threshold": 0.9,
            "matches": [],
            "count": 0,
            "stable_components": [],
        },
        "direction_audit_gate": direction,
        "signal": {
            "classification": "ROUTE_C_NO_SIGNAL",
            "no_signal": True,
        },
        "numeric_collective_inventory": {
            "fe_sized_numeric_allgather_count": 0,
            "owner_row_basis_replicated": False,
        },
        "exact_output_vectors_consumed": 0,
    }
    factor_lifecycle = {
        "construction_count": 3,
        "destruction_count": 3,
        "simultaneous_factor_count_max": 3,
        "pc_setup_count": 1,
        "continuous_source_solve_count": 2,
        "ready": {"factor_count_ready": 3},
        "after": {
            "factor_count_after_cleanup": 0,
            "destroyed": True,
            "action_destroyed": True,
            "parent_released": True,
        },
    }
    return {
        "schema": checker.WORKER_SCHEMA,
        "method": checker.WORKER_METHOD,
        "source_sha": FORMAL_SOURCE_SHA,
        "input_sha256": "c" * 64,
        "physical_model_sha256": "d" * 64,
        "classification": "ROUTE_C_NO_SIGNAL",
        "status": "completed_route_c_screen",
        "route_c": route,
        "group_pc": {"factor_lifecycle": factor_lifecycle},
        "external_dtn_coupling": {
            "path": "minimal_surface_rhs_only",
            "physical_dtn_operator_constructed": False,
            "full_C_materialized": False,
            "D_materialized": False,
            "H_materialized": False,
            "woodbury_inverse_constructed": False,
            "observed": external,
        },
        "rhs_vectors_loaded": 2,
        "exact_output_vectors_loaded": 0,
        "exact_output_vectors_consumed": 0,
        "system_created": True,
        "qep_calls": 0,
        "full_side_exact_factor_count": 0,
        "pde_solve": "not_run",
    }


def _timeline_row(
    *,
    stage: str,
    stage_status: str,
    readable: bool,
    rss: int,
    swap: int = 0,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "stage_status": stage_status,
        "timestamp_utc": f"2026-08-26T00:00:0{rss // 100}Z",
        "elapsed_seconds": float(rss),
        "post_sample_return_code": None,
        "authoritative_sample": True,
        "terminal_teardown_excluded": False,
        "resource_authority": {
            "process_tree": {
                "pids": [101, 102],
                "all_status_readable": readable,
                "rss_bytes": rss,
                "swap_bytes": swap,
            }
        },
    }


def _write_timeline(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "formal"
    worker = root / "worker"
    worker.mkdir(parents=True)
    input_path = tmp_path / "input.dat"
    input_path.write_bytes(b"synthetic official input\n")
    manifest = _run_manifest()
    manifest["input_sha256"] = checker._sha256(input_path)
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    (worker / "run_summary.json").write_text(manifest_bytes, encoding="utf-8")
    (worker / "route_c_manifest.json").write_text(manifest_bytes, encoding="utf-8")

    marker_path = root / "memory_stage_markers.raw.jsonl"
    stage_path = root / "memory_stages.jsonl"
    timeline_path = root / "process_tree_samples.jsonl"
    marker_rows = [
        {"stage": "construction_begin", "stage_status": "running"},
        {"stage": "v5_route_c_cleanup", "stage_status": "complete"},
    ]
    stage_rows = [
        {"stage": "construction_begin", "status": "running"},
        {"stage": "v5_route_c_cleanup", "status": "complete"},
    ]
    marker_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in marker_rows) + "\n",
        encoding="utf-8",
    )
    stage_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in stage_rows) + "\n",
        encoding="utf-8",
    )
    rows = [
        _timeline_row(
            stage="construction_begin",
            stage_status="running",
            readable=True,
            rss=100,
        ),
        _timeline_row(
            stage="v5_route_c_cleanup",
            stage_status="complete",
            readable=False,
            rss=200,
        ),
    ]
    _write_timeline(timeline_path, rows)
    stdout_path = root / "worker_stdout.txt"
    stdout_path.write_text("", encoding="utf-8")
    command = [
        "mpiexec",
        "-n",
        "8",
        "/fake/python",
        "-m",
        "benchmarks.task040_level_a",
        "--input",
        str(input_path),
        "--exact-spool-root",
        str(tmp_path / "frozen-spool"),
        "--run-directory",
        str(worker),
        "--source-sha",
        FORMAL_SOURCE_SHA,
        "--memory-stages",
        str(stage_path),
        "--memory-markers",
        str(marker_path),
        "--v5-route-c",
        "--watchdog-enabled",
        "--bottom-route-only",
    ]
    artifact_paths = {
        "memory_stage_markers.raw.jsonl": marker_path,
        "memory_stages.jsonl": stage_path,
        "process_tree_samples.jsonl": timeline_path,
        "worker_stdout.txt": stdout_path,
    }
    watchdog = {
        "schema": checker.WATCHDOG_SCHEMA,
        "method": checker.WORKER_METHOD,
        "source_sha": FORMAL_SOURCE_SHA,
        "command": command,
        "return_code": 0,
        "termination_reason": "natural_exit",
        "process_control": {
            "worker_exited": True,
            "process_group_exited": True,
            "sigkill_required": False,
        },
        "run_summary_present": True,
        "run_summary_sha256": checker._sha256(worker / "run_summary.json"),
        "artifact_hashes": {
            name: checker._sha256(path) for name, path in artifact_paths.items()
        },
        "hard_stop_bytes": checker.HARD_STOP_BYTES,
        "route_c_hard_stop_bytes": checker.HARD_STOP_BYTES,
        "route_c_hard_stop_crossed": False,
        "route_c_peak_memory_bytes": 200,
        "route_c_swap_limit_bytes": 0,
        "route_c_timeout_seconds": 21600,
        "peak_rss_bytes": 200,
        "peak_swap_bytes": 0,
        "sample_count": 2,
        "authoritative_sample_count": 2,
        "terminal_teardown_excluded_count": 0,
        "all_status_readable": False,
        "swap_authority_readable": False,
    }
    _write_json(root / "watchdog_summary.json", watchdog)
    output = tmp_path / "adjudication" / "result.json"
    return root, timeline_path, output


def _cli(root: Path, output: Path) -> int:
    return checker.main(
        [
            "--formal-root",
            str(root),
            "--formal-source-sha",
            FORMAL_SOURCE_SHA,
            "--checker-source-sha",
            CHECKER_SOURCE_SHA,
            "--output",
            str(output),
        ]
    )


def _refresh_timeline_summary(root: Path, timeline_path: Path) -> None:
    rows = checker._load_jsonl(timeline_path)
    watchdog_path = root / "watchdog_summary.json"
    watchdog = checker._load_json(watchdog_path)
    trees = [checker._process_tree(row) for row in rows]
    rss = [tree["rss_bytes"] for tree in trees if tree is not None]
    swap = [tree["swap_bytes"] for tree in trees if tree is not None]
    watchdog["sample_count"] = len(rows)
    watchdog["authoritative_sample_count"] = sum(
        row.get("authoritative_sample") is True for row in rows
    )
    watchdog["peak_rss_bytes"] = max(rss)
    watchdog["peak_swap_bytes"] = max(swap)
    watchdog["route_c_peak_memory_bytes"] = max(rss)
    watchdog["route_c_hard_stop_crossed"] = max(rss) >= checker.HARD_STOP_BYTES
    watchdog["artifact_hashes"]["process_tree_samples.jsonl"] = checker._sha256(
        timeline_path
    )
    _write_json(watchdog_path, watchdog)


def test_checker_accepts_valid_no_signal_but_candidate_gate_stops(tmp_path: Path) -> None:
    root, _, output = _fixture(tmp_path)
    result = checker.check_route_c(root, FORMAL_SOURCE_SHA, CHECKER_SOURCE_SHA)
    assert result["evidence_valid"] is True
    assert result["gate_pass"] is False
    assert result["checker_pass"] is True
    assert result["classification"] == "VALID_NEGATIVE_ROUTE_C_NO_SIGNAL"
    assert result["route_c_no_signal_stop_gate_triggered"] is True
    assert result["route_c_positive_signal_gate_pass"] is False
    assert result["teardown_adjudication_gate"] is True
    assert result["resource_authority_gate_pass"] is True
    assert result["derived_timeline"]["terminal_teardown_excluded_lines_1_based"] == [2]
    assert all(".npy" not in item["path"] for item in result["read_files"])
    assert _cli(root, output) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["checker_pass"] is True


def test_checker_reports_watchdog_hash_tamper_as_invalid(tmp_path: Path) -> None:
    root, timeline_path, output = _fixture(tmp_path)
    rows = checker._load_jsonl(timeline_path)
    rows[0]["elapsed_seconds"] = 999.0
    _write_timeline(timeline_path, rows)
    assert _cli(root, output) == 2
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["evidence_valid"] is False
    assert result["checker_pass"] is False
    assert result["checks"]["watchdog_artifact_hashes"] is False


def test_checker_keeps_suffix_gap_out_of_candidate_gate(tmp_path: Path) -> None:
    root, timeline_path, output = _fixture(tmp_path)
    rows = checker._load_jsonl(timeline_path)
    rows.append(
        _timeline_row(
            stage="post_cleanup_poll",
            stage_status="complete",
            readable=True,
            rss=150,
        )
    )
    _write_timeline(timeline_path, rows)
    _refresh_timeline_summary(root, timeline_path)
    assert _cli(root, output) == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["evidence_valid"] is True
    assert result["gate_pass"] is False
    assert result["checker_pass"] is True
    assert result["gate_failures"]
    assert result["derived_timeline"]["terminal_teardown_excluded_lines_1_based"] == []


def test_checker_preserves_live_unreadable_resource_gap(tmp_path: Path) -> None:
    root, timeline_path, output = _fixture(tmp_path)
    rows = checker._load_jsonl(timeline_path)
    rows[0]["resource_authority"]["process_tree"]["all_status_readable"] = False
    _write_timeline(timeline_path, rows)
    _refresh_timeline_summary(root, timeline_path)
    assert _cli(root, output) == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["evidence_valid"] is True
    assert result["gate_pass"] is False
    assert result["derived_timeline"]["live_unreadable_lines_1_based"] == [1]


def test_checker_accepts_raw_resource_failures_but_stops_gate(tmp_path: Path) -> None:
    root, timeline_path, output = _fixture(tmp_path)
    rows = checker._load_jsonl(timeline_path)
    rows[1]["resource_authority"]["process_tree"]["rss_bytes"] = checker.HARD_STOP_BYTES + 1
    _write_timeline(timeline_path, rows)
    _refresh_timeline_summary(root, timeline_path)
    assert _cli(root, output) == 0
    high_rss = json.loads(output.read_text(encoding="utf-8"))
    assert high_rss["evidence_valid"] is True
    assert high_rss["gate_pass"] is False
    assert high_rss["gate_checks"]["raw_observed_rss_below_hard_stop"] is False
    assert high_rss["gate_checks"]["rss_authority_complete"] is False

    root, timeline_path, output = _fixture(tmp_path / "swap")
    rows = checker._load_jsonl(timeline_path)
    rows[1]["resource_authority"]["process_tree"]["swap_bytes"] = 1
    _write_timeline(timeline_path, rows)
    _refresh_timeline_summary(root, timeline_path)
    assert _cli(root, output) == 0
    swap = json.loads(output.read_text(encoding="utf-8"))
    assert swap["evidence_valid"] is True
    assert swap["gate_pass"] is False
    assert swap["gate_checks"]["raw_observed_swap_zero"] is False
    assert swap["gate_checks"]["swap_authority_complete"] is False


def test_checker_never_writes_output_inside_formal_root(tmp_path: Path) -> None:
    root, _, _ = _fixture(tmp_path)
    output = root / "checker.json"
    assert _cli(root, output) == 2
    assert not output.exists()
