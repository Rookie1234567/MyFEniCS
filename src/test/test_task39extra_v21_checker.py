"""Focused V21 contract tests for the repaired worker/checker boundary."""

from copy import deepcopy
from pathlib import Path

import pytest

from benchmarks import check_dual_condensed_robustness_v21 as checker
from benchmarks.check_p4_blr_v16 import _jsonl


SAVED_A_RUN = Path(
    "results/euv_grazing1_phi0/"
    "task39extra_v21_z2_notch_h10__full3d_iterative__mpi1__Mna/"
    "20260915T053102.148718Z"
)


def _v21_release_events():
    rows = []
    used = 0
    reservations = (
        ("v14_h6", 2),
        (checker.V21_P6_INVENTORY_LABEL, 8),
        ("v18_exact_condensed_global", 32),
        ("v18_exact_condensed_matrix", 16),
        ("v18_exact_port_recovery", 0),
    )
    timestamp = 1
    for label, amount in reservations:
        used += amount
        rows.append(
            {
                "event": "v14_inventory_reserved",
                "timestamp_ns": timestamp,
                "facts": {
                    "label": label,
                    "entry": {"bytes": amount},
                    "used_bytes": used,
                },
            }
        )
        timestamp += 1

    def add(event, facts=None):
        nonlocal timestamp
        rows.append(
            {"event": event, "timestamp_ns": timestamp, "facts": facts or {}}
        )
        timestamp += 1

    add("v20_complete_field_packet_saved")
    add(
        "y3_independent_final_residual_complete",
        {"relative": 1e-7},
    )
    add(
        "v20_release_gate_checked",
        {
            "field_packet_saved": True,
            "pre_release_A6_passed": True,
            "pre_release_identity_passed": True,
            "pre_release_A6_relative": 1e-7,
        },
    )
    add("v20_preconditioner_release_started")
    used -= 2
    add("v14_inventory_released", {"label": "v14_h6", "bytes": 2, "used_bytes": used})
    add("v20_preconditioner_release_complete")
    add("v20_p6_release_started")
    used -= 8
    add(
        "v14_inventory_released",
        {
            "label": checker.V21_P6_INVENTORY_LABEL,
            "bytes": 8,
            "used_bytes": used,
        },
    )
    add(
        "v20_p6_release_complete",
        {"owner_refs_cleared": True, "released_after_final_residual": True},
    )
    add("v20_p4_release_started")
    used -= 32
    add(
        "v14_inventory_released",
        {"label": "v18_exact_condensed_global", "bytes": 32, "used_bytes": used},
    )
    used -= 16
    add(
        "v14_inventory_released",
        {"label": "v18_exact_condensed_matrix", "bytes": 16, "used_bytes": used},
    )
    add(
        "v14_inventory_released",
        {"label": "v18_exact_port_recovery", "bytes": 0, "used_bytes": used},
    )
    add(
        "v20_p4_release_complete",
        {
            "matrix_lifecycle_policy": "MATRIX_RETAINED_BACKEND_DEPENDENCY",
            "factor_destroy_before_matrix": True,
        },
    )
    add("v20_post_release_final_residual_complete")
    add("y3_physical_output_comparison_complete")
    return rows


def test_v21_label_adapter_is_exact_and_does_not_mutate_raw_event():
    events = [
        {
            "event": "v14_inventory_released",
            "timestamp_ns": 1,
            "facts": {
                "label": checker.V21_P6_INVENTORY_LABEL,
                "bytes": 8,
                "used_bytes": 0,
            },
        }
    ]
    adapted = checker._alias_v21_events(events, stage="Z2_NOTCH_H10")
    assert events[0]["facts"]["label"] == checker.V21_P6_INVENTORY_LABEL
    aliases = [row for row in adapted if row.get("label_aliased_from")]
    assert len(aliases) == 1
    assert aliases[0]["facts"]["label"] == checker.V20_P6_INVENTORY_LABEL
    assert aliases[0]["aliased_from"] == "v14_inventory_released"


def test_v21_release_timeline_checks_raw_label_owner_and_amount():
    events = _v21_release_events()
    facts = checker._v21_release_timeline_facts(events, stage="Z2_NOTCH_H10")
    assert facts["passed"]
    assert facts["checks"]["v21_p6_raw_inventory_label"]
    assert facts["checks"]["v21_p6_release_owner_refs"]
    assert facts["checks"]["v21_p6_release_amount_matches_reservation"]
    assert facts["inventory_amount"]["reserved_bytes"] == 8
    assert facts["inventory_amount"]["released_bytes"] == 8


def test_v21_release_timeline_rejects_amount_or_owner_tampering():
    broken_amount = deepcopy(_v21_release_events())
    p6_release = next(
        row
        for row in broken_amount
        if row["event"] == "v14_inventory_released"
        and row["facts"].get("label") == checker.V21_P6_INVENTORY_LABEL
    )
    p6_release["facts"]["bytes"] = 7
    assert not checker._v21_release_timeline_facts(
        broken_amount, stage="Z2_NOTCH_H10"
    )["passed"]

    broken_owner = deepcopy(_v21_release_events())
    complete = next(
        row for row in broken_owner if row["event"] == "v20_p6_release_complete"
    )
    complete["facts"]["owner_refs_cleared"] = False
    assert not checker._v21_release_timeline_facts(
        broken_owner, stage="Z2_NOTCH_H10"
    )["passed"]

    broken_label = deepcopy(_v21_release_events())
    p6_release = next(
        row
        for row in broken_label
        if row["event"] == "v14_inventory_released"
        and row["facts"].get("label") == checker.V21_P6_INVENTORY_LABEL
    )
    p6_release["facts"]["label"] = "v21_p6_local_cache_typo"
    assert not checker._v21_release_timeline_facts(
        broken_label, stage="Z2_NOTCH_H10"
    )["passed"]

    broken_order = deepcopy(_v21_release_events())
    p6_release = next(
        row
        for row in broken_order
        if row["event"] == "v14_inventory_released"
        and row["facts"].get("label") == checker.V21_P6_INVENTORY_LABEL
    )
    p6_complete = next(
        row for row in broken_order if row["event"] == "v20_p6_release_complete"
    )
    p6_release["timestamp_ns"] = p6_complete["timestamp_ns"] + 1
    assert not checker._v21_release_timeline_facts(
        broken_order, stage="Z2_NOTCH_H10"
    )["passed"]


def test_historical_schema_compatibility_is_hash_bound():
    summary = {
        "schema": checker.HISTORICAL_V21_Z2_SUMMARY_SCHEMA,
        "profile": "physical_p6_trace_p4_condensed_robustness_v21",
    }
    accepted = checker._summary_schema_facts(
        summary,
        source_sha=checker.HISTORICAL_V21_Z2_SOURCE_SHA,
        stage="Z2_NOTCH_H10",
    )
    assert accepted["passed"]
    assert accepted["compatibility_applied"]
    for source_sha, stage, schema, profile in (
        ("0" * 40, "Z2_NOTCH_H10", summary["schema"], summary["profile"]),
        (checker.HISTORICAL_V21_Z2_SOURCE_SHA, "Z3_ORIGINAL_H7P5", summary["schema"], summary["profile"]),
        (checker.HISTORICAL_V21_Z2_SOURCE_SHA, "Z2_NOTCH_H10", "arbitrary.schema", summary["profile"]),
        (checker.HISTORICAL_V21_Z2_SOURCE_SHA, "Z2_NOTCH_H10", summary["schema"], "wrong.profile"),
    ):
        candidate = dict(summary, schema=schema, profile=profile)
        assert not checker._summary_schema_facts(
            candidate, source_sha=source_sha, stage=stage
        )["passed"]

    native = checker._summary_schema_facts(
        dict(summary, schema="task039extra.v21.worker-summary.v1"),
        source_sha="0" * 40,
        stage="Z4_NOTCH_H7P5",
    )
    assert native["passed"]
    assert not native["compatibility_applied"]


def test_v21_worker_enables_schema_restore_without_touching_v20_default(monkeypatch):
    from src.runners import physical_dual_cell_condensed_robustness_v21 as worker

    captured = {}

    def fake_runner(*args, **kwargs):
        captured.update(kwargs)
        return {"passed": True}

    monkeypatch.setattr(worker, "_run_physical_dual_cell_condensed_lowmem", fake_runner)
    worker.run_physical_dual_cell_condensed_robustness_v21(
        {"solver": {"preconditioner": "unused", "stage": "unused"}},
        "/tmp/v21-contract-test",
        source_sha="a" * 40,
    )
    assert captured["restore_summary_schema"] is True
    assert captured["summary_schema"] == "task039extra.v21.worker-summary.v1"


def test_saved_a_release_alias_keeps_raw_label_and_passes_release_contract():
    events_path = SAVED_A_RUN / "v21_events.jsonl"
    if not events_path.is_file():
        pytest.skip("the saved A event fixture is unavailable")
    events = _jsonl(events_path)
    raw = next(
        row
        for row in events
        if row["event"] == "v14_inventory_released"
        and row["facts"].get("label") == checker.V21_P6_INVENTORY_LABEL
    )
    adapted = checker._alias_v21_events(events, stage="Z2_NOTCH_H10")
    assert raw["facts"]["label"] == checker.V21_P6_INVENTORY_LABEL
    assert any(
        row.get("label_aliased_from") == checker.V21_P6_INVENTORY_LABEL
        and row["facts"]["label"] == checker.V20_P6_INVENTORY_LABEL
        for row in adapted
    )
    facts = checker._v21_release_timeline_facts(events, stage="Z2_NOTCH_H10")
    assert facts["passed"]
