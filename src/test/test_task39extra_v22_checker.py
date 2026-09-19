"""Small raw-evidence tests for the explicit V22 capacity checker wrapper."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from benchmarks import check_dual_condensed_robustness_v21 as checker
from src.solvers.mumps_capacity_budget_v22 import capacity_budget_v22


SOURCE_SHA = "a" * 40
INPUT_SHA = "b" * 64
PHYSICAL_SHA = "c" * 64


def _write_json(path: Path, value):
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows):
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _capacity_run(tmp_path: Path):
    run = tmp_path / "v22-run"
    run.mkdir()
    (run / "watchdog").mkdir()
    ledger_path = tmp_path / "shared_workflow_ledger.json"
    dynamic_cap = 7 * (1 << 30)
    context = {
        "schema": "task039extra.v22.capacity-context.v2",
        "classification": "derived_pre_numeric_payload_estimates_live_RSS_separate",
        "identity": {"p6_port_count": 80, "surface_cells_per_side": 45},
        "future_inventory_components": {
            "future": 100,
            "p6_global_trace_map_inventory_bytes": 100,
        },
        "future_workspace_phases": {"setup": {"workspace": 100}},
    }
    budget = capacity_budget_v22(
        launch_cap_bytes=dynamic_cap,
        inventory_cap_bytes=6 * (1 << 30),
        current_tree_rss_bytes=1 * (1 << 30),
        current_inventory_bytes=1 * (1 << 30),
        future_inventory_components=context["future_inventory_components"],
        future_workspace_phases=context["future_workspace_phases"],
        numeric_untouched_pool_bytes=1 * (1 << 30),
        workspace_pool_cap_bytes=1 * (1 << 30),
    )
    allocated_mb = int(budget["continuation_max_allocated_bytes"] // 1_000_000)
    allocated_mb += 1
    used_mb = 2
    infog = {
        "1": 0,
        "2": 2,
        "9": 9,
        "19": allocated_mb,
        "22": used_mb,
        "29": 29,
    }
    request = {
        "policy": "CAPACITY_CONTROLLED_LOCAL_MUMPS_V22",
        "requested_memory_limit_mb": budget["icntl23_mb"],
        "capacity_budget": budget,
    }
    before = {"icntl": {"7": 7, "10": 0, "14": 120, "23": 0}}
    after = {"icntl": {"7": 7, "10": 0, "14": 120, "23": budget["icntl23_mb"]}}
    symbolic_resource = {
        "rss_bytes": 1 * (1 << 30) - 123,
        "launch_cap_bytes": dynamic_cap - 123,
    }
    events = [
        {
            "event": "schur_factor_symbolic_complete",
            "timestamp_ns": 1,
            "facts": {"symbolic_resource": symbolic_resource},
        },
        {
            "event": "v22_capacity_pre_numeric_frozen",
            "timestamp_ns": 3,
            "facts": budget,
        },
        {
            "event": "v22_numeric_observed_before_post_gate",
            "timestamp_ns": 4,
            "facts": {},
        },
        {
            "event": "v22_continuation_allocated_gate_failed",
            "timestamp_ns": 5,
            "facts": {
                "allocated_upper_bytes": (allocated_mb + 1) * 1_000_000,
                "native_used_upper_bytes": (used_mb + 1) * 1_000_000,
                "continuation_max_allocated_bytes": budget[
                    "continuation_max_allocated_bytes"
                ],
            },
        },
    ]
    native = {
        "schema": "task039extra.v22.native-factor-observation.v1",
        "source_sha": SOURCE_SHA,
        "native_infog": infog,
        "matrix_identity_before_factor": {"sha256": "d" * 64},
        "matrix_identity_after_factor": None,
        "matrix_identity_after_factor_status": "pending_post_factor_hash",
        "observation": {
            "numeric_raw": {"infog": infog},
            "memory_request": request,
            "icntl23_readback_mb": budget["icntl23_mb"],
            "symbolic_memory_settings": before,
            "symbolic_memory_settings_after_memory_limit": after,
        },
    }
    watchdog_row = {
        "rss_bytes": 1 * (1 << 30),
        "swap_bytes": 0,
        "all_status_readable": True,
        "pss_all_readable": True,
        "memory_envelope": {
            "effective_available_bytes": 4 * (1 << 30),
            "reserve_bytes": 1 * (1 << 30),
        },
        "global_swap_pages": {"pswpin_pages": 0, "pswpout_pages": 0},
        "time_policy": "observe_only",
        "time_gate_evaluated": False,
    }
    worker_row = {
        "timestamp_ns": 2,
        "launch_cap_bytes": dynamic_cap,
        "rss_bytes": 1 * (1 << 30),
        "inventory_used_bytes": 1 * (1 << 30),
        "inventory_peak_bytes": 2 * (1 << 30),
        "workspace_live_bytes": 0,
        "workspace_peak_bytes": 1 * (1 << 30),
    }
    manifest = {
        "source_sha": SOURCE_SHA,
        "input_sha256": INPUT_SHA,
        "physical_model_sha256": PHYSICAL_SHA,
        "source_after": {"tracked_and_nonignored_untracked_clean": True},
    }
    resolved = {
        "solver": {
            "preconditioner": checker.V22_PROFILE,
            "stage": checker.V22_STAGE,
        },
        "provenance": {
            "source_sha": SOURCE_SHA,
            "input_sha256": INPUT_SHA,
            "physical_model_sha256": PHYSICAL_SHA,
        },
    }
    summary = {
        "schema": checker.V22_SUMMARY_SCHEMA,
        "profile": checker.V22_PROFILE,
        "stage": checker.V22_STAGE,
        "source_sha": SOURCE_SHA,
        "status": "CONTROLLED_STOP",
        "result_classification": "RESOURCE_CONTROLLED_STOP",
    }
    run_summary = {
        "resource_authority": {
            "launch_envelope": {"launch_cap_bytes": dynamic_cap},
            "global_swap_activity": {
                "baseline": {"pswpin_pages": 0, "pswpout_pages": 0},
                "end": {"pswpin_pages": 0, "pswpout_pages": 0},
            },
            "descendants_cleared": True,
            "remaining_child_pids": [],
        },
        "time_policy": "observe_only",
        "time_gate_evaluated": False,
    }
    ledger = {
        "schema": checker.V22_LEDGER_SCHEMA,
        "batch_identity": checker.V22_BATCH_IDENTITY,
        "allowed_stages": [checker.V22_STAGE],
        "cross_case_recycling": False,
        "unique_bug_replay_count": 0,
        "fresh_worker_count": 1,
        "predecessors": {
            "v21": {"sha256": checker.V22_PREDECESSOR_V21_LEDGER_SHA256}
        },
        "source_attempts": [
            {"stage": checker.V22_STAGE, "source_sha": SOURCE_SHA, "attempt": 1}
        ],
        "stages": {
            checker.V22_STAGE: {
                "active_attempt": None,
                "attempts": [
                    {
                        "run_directory": str(run),
                        "source_sha": SOURCE_SHA,
                        "replay": False,
                        "actual_elapsed_seconds": 1.0,
                    }
                ],
            }
        },
    }
    _write_json(run / "v22_capacity_context.json", context)
    _write_jsonl(run / "v22_events.jsonl", events)
    _write_json(run / "v22_numeric_native_facts.json", native)
    _write_jsonl(run / "watchdog/resources.jsonl", [watchdog_row])
    _write_jsonl(run / "v22_worker_resources.jsonl", [worker_row])
    _write_json(run / "run_manifest.json", manifest)
    _write_json(run / "resolved_config.json", resolved)
    _write_json(run / "run_summary.json", run_summary)
    _write_json(run / checker.V22_SUMMARY_FILENAME, summary)
    _write_json(ledger_path, ledger)
    return run, ledger_path, budget


def test_v22_capacity_wrapper_accepts_dynamic_cap_and_keeps_physics_unknown(tmp_path):
    run, ledger_path, budget = _capacity_run(tmp_path)
    result = checker.check_v22_run(
        run, expected_source_sha=SOURCE_SHA, ledger_path=ledger_path
    )
    assert result["evidence_valid"] is True
    assert result["full_numerical_pass"] is False
    assert result["stage_pass"] is False
    assert result["official_result"] is False
    assert result["physics_status"] == "UNKNOWN_CONTROLLED_RESOURCE_STOP"
    assert result["capacity_evidence"]["budget"]["launch_cap_bytes"] < 8 * (1 << 30)
    assert result["capacity_evidence"]["native_allocated_upper_bytes"] > budget[
        "continuation_max_allocated_bytes"
    ]
    assert result["capacity_evidence"]["native_used_upper_bytes"] < result[
        "capacity_evidence"
    ]["native_allocated_upper_bytes"]
    assert result["capacity_evidence"]["checks"][
        "continuation_gate_recomputed"
    ] is True
    assert result["capacity_evidence"]["checks"][
        "controlled_stop_classification"
    ] is True
    assert result["capacity_evidence"]["capacity_stop_evidence"] is True


def test_v22_capacity_checker_rejects_request_readback_tamper_against_budget(tmp_path):
    run, ledger_path, _budget = _capacity_run(tmp_path)
    native_path = run / "v22_numeric_native_facts.json"
    native = json.loads(native_path.read_text(encoding="utf-8"))
    tampered = native["observation"]["memory_request"]["requested_memory_limit_mb"] + 1
    native["observation"]["memory_request"]["requested_memory_limit_mb"] = tampered
    native["observation"]["icntl23_readback_mb"] = tampered
    _write_json(native_path, native)
    result = checker.check_v22_run(
        run, expected_source_sha=SOURCE_SHA, ledger_path=ledger_path
    )
    assert result["evidence_valid"] is False
    assert "quota_set_and_readback" in result["errors"]


def test_v22_capacity_checker_rejects_missing_gate_cleanup_swap_and_ledger_tamper(
    tmp_path,
):
    run, ledger_path, _budget = _capacity_run(tmp_path)
    events = [
        row
        for row in _jsonl_rows(run / "v22_events.jsonl")
        if row["event"] != "v22_continuation_allocated_gate_failed"
    ]
    _write_jsonl(run / "v22_events.jsonl", events)
    run_summary = json.loads((run / "run_summary.json").read_text(encoding="utf-8"))
    run_summary["resource_authority"]["descendants_cleared"] = False
    run_summary["resource_authority"]["global_swap_activity"]["end"][
        "pswpout_pages"
    ] = 1
    _write_json(run / "run_summary.json", run_summary)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["fresh_worker_count"] = 2
    _write_json(ledger_path, ledger)
    result = checker.check_v22_run(
        run, expected_source_sha=SOURCE_SHA, ledger_path=ledger_path
    )
    assert result["evidence_valid"] is False
    assert "watchdog_cleanup" in result["errors"]
    assert "watchdog_raw" in result["errors"]
    assert "ledger_attempt_settled" in result["errors"]


def _jsonl_rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_v22_wrapper_preserves_ordinary_worker_failure_without_capacity_claim(tmp_path):
    run, ledger_path, budget = _capacity_run(tmp_path)
    summary_path = run / checker.V22_SUMMARY_FILENAME
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["status"] = "FAILED"
    summary["result_classification"] = "WORKER_FAILED"
    _write_json(summary_path, summary)
    native_path = run / "v22_numeric_native_facts.json"
    native = json.loads(native_path.read_text(encoding="utf-8"))
    allocated_mb = int(budget["continuation_max_allocated_bytes"] // 1_000_000) - 1
    native["native_infog"]["19"] = allocated_mb
    native["observation"]["numeric_raw"]["infog"]["19"] = allocated_mb
    _write_json(native_path, native)
    events = _jsonl_rows(run / "v22_events.jsonl")
    gate = next(
        row for row in events if row["event"] == "v22_continuation_allocated_gate_failed"
    )
    gate["event"] = "v22_continuation_capacity_gate"
    future_inventory = budget["future_inventory_bytes"]
    workspace_pool = budget["workspace_pool_cap_bytes"]
    gate["timestamp_ns"] = 6
    gate["facts"] = {
        "allocated_upper_bytes": (allocated_mb + 1) * 1_000_000,
        "used_upper_bytes": 3 * 1_000_000,
        "future_inventory_bytes": future_inventory,
        "workspace_pool_cap_bytes": workspace_pool,
        "rss_bytes": 1 * (1 << 30),
        "projected_tree_bytes": 1 * (1 << 30) + future_inventory + workspace_pool,
        "launch_cap_bytes": 7 * (1 << 30),
        "gate": "native_allocated_then_live_tree_before_post_numeric_gate",
    }
    _write_jsonl(run / "v22_events.jsonl", events)
    worker_rows = _jsonl_rows(run / "v22_worker_resources.jsonl")
    worker_rows.append(
        {
            "timestamp_ns": 5,
            "label": "v22_continuation_resource_gate",
            "launch_cap_bytes": 7 * (1 << 30),
            "rss_bytes": 1 * (1 << 30),
            "inventory_used_bytes": 1 * (1 << 30),
            "inventory_peak_bytes": 2 * (1 << 30),
            "workspace_live_bytes": 0,
            "workspace_peak_bytes": 1 * (1 << 30),
        }
    )
    _write_jsonl(run / "v22_worker_resources.jsonl", worker_rows)
    result = checker.check_v22_run(
        run, expected_source_sha=SOURCE_SHA, ledger_path=ledger_path
    )
    assert result["evidence_valid"] is True
    assert result["full_numerical_pass"] is False
    assert result["physics_status"] == "UNKNOWN_WORKER_FAILED"


def test_v22_checker_records_legal_allocated_but_projected_tree_capacity_stop(
    tmp_path,
):
    run, ledger_path, budget = _capacity_run(tmp_path)
    summary_path = run / checker.V22_SUMMARY_FILENAME
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["status"] = "CONTROLLED_STOP"
    summary["result_classification"] = "RESOURCE_CONTROLLED_STOP"
    _write_json(summary_path, summary)

    native_path = run / "v22_numeric_native_facts.json"
    native = json.loads(native_path.read_text(encoding="utf-8"))
    allocated_mb = int(budget["continuation_max_allocated_bytes"] // 1_000_000) - 1
    native["native_infog"]["19"] = allocated_mb
    native["observation"]["numeric_raw"]["infog"]["19"] = allocated_mb
    _write_json(native_path, native)

    future_inventory = budget["future_inventory_bytes"]
    workspace_pool = budget["workspace_pool_cap_bytes"]
    projected_rss = 7 * (1 << 30) - future_inventory - workspace_pool + 1
    events = _jsonl_rows(run / "v22_events.jsonl")
    gate = next(
        row for row in events if row["event"] == "v22_continuation_allocated_gate_failed"
    )
    gate["event"] = "v22_continuation_capacity_gate"
    gate["timestamp_ns"] = 6
    gate["facts"] = {
        "allocated_upper_bytes": (allocated_mb + 1) * 1_000_000,
        "used_upper_bytes": 3 * 1_000_000,
        "future_inventory_bytes": future_inventory,
        "workspace_pool_cap_bytes": workspace_pool,
        "rss_bytes": projected_rss,
        "projected_tree_bytes": projected_rss + future_inventory + workspace_pool,
        "launch_cap_bytes": 7 * (1 << 30),
        "gate": "native_allocated_then_live_tree_before_post_numeric_gate",
    }
    _write_jsonl(run / "v22_events.jsonl", events)

    worker_rows = _jsonl_rows(run / "v22_worker_resources.jsonl")
    worker_rows.append(
        {
            "timestamp_ns": 5,
            "label": "v22_continuation_resource_gate",
            "launch_cap_bytes": 7 * (1 << 30),
            "rss_bytes": projected_rss,
            "inventory_used_bytes": 1 * (1 << 30),
            "inventory_peak_bytes": 2 * (1 << 30),
            "workspace_live_bytes": 0,
            "workspace_peak_bytes": 1 * (1 << 30),
        }
    )
    _write_jsonl(run / "v22_worker_resources.jsonl", worker_rows)

    result = checker.check_v22_run(
        run, expected_source_sha=SOURCE_SHA, ledger_path=ledger_path
    )
    capacity = result["capacity_evidence"]
    assert result["evidence_valid"] is True
    assert result["full_numerical_pass"] is False
    assert result["physics_status"] == "UNKNOWN_CONTROLLED_RESOURCE_STOP"
    assert capacity["tree_capacity_stop_evidence"] is True
    assert capacity["continuation_rss_bytes"] < capacity[
        "continuation_projected_tree_bytes"
    ]
    assert capacity["continuation_projected_tree_bytes"] >= capacity[
        "continuation_launch_cap_bytes"
    ]


def test_v22_event_alias_is_prefix_specific_and_preserves_raw_v22_packet_event():
    events = [
        {
            "event": "v22_complete_field_packet_saved",
            "timestamp_ns": 1,
            "facts": {"packet": "x2_retained_final.json"},
        }
    ]
    adapted = checker._alias_v21_events(events, stage=checker.V22_STAGE, evidence_prefix="v22")
    assert events[0]["event"] == "v22_complete_field_packet_saved"
    assert any(row.get("event") == "v20_complete_field_packet_saved" for row in adapted)
