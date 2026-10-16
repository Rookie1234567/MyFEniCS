from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from src.runners import task40_v10_campaign as campaign


def test_v22_campaign_window_is_bound_to_its_exact_six_hour_registration():
    path = campaign.TASK40_V22_CAMPAIGN_WINDOW.resolve()
    window = campaign.load_fixed_campaign_window(path, require_current_boot=False)

    assert window.sha256 == campaign.TASK40_V22_CAMPAIGN_SHA256
    assert window.total_seconds == 21_600.0
    assert window.closeout_seconds == 600.0
    assert window.payload["parent_window"] == campaign.TASK40_V22_PARENT_WINDOW
    assert window.payload["parent_ledger"] == campaign.TASK40_V22_PARENT_LEDGER

    with pytest.raises(ValueError, match="SHA-256 changed"):
        campaign._validate_v22_campaign_registration(
            path, "0" * 64, window.payload
        )
    changed_scope = dict(window.payload, stage_scope=["implementation"])
    with pytest.raises(ValueError, match="identity or scope changed"):
        campaign._validate_v22_campaign_registration(
            path, window.sha256, changed_scope
        )


def test_campaign_observation_keeps_forward_utc_charge_across_service_attempts(
    tmp_path, monkeypatch
):
    boot_id = "0bb7278d-a4d8-4b78-b625-895e739880e6"
    namespace = {"time": "time:[4026531834]", "time_for_children": "time:[4026531834]"}
    t0_utc_ns = 1_700_000_000_000_000_000
    anchor = {
        "monotonic": 100.0,
        "boottime": 100.0,
        "utc_ns": t0_utc_ns + 20_000_000_000,
        "boot_id": boot_id,
    }
    window = campaign.FixedCampaignWindow(
        path=tmp_path / "campaign_window.json",
        sha256="a" * 64,
        payload={},
        anchor=anchor,
        t0_utc_ns=t0_utc_ns,
        deadline_utc_ns=t0_utc_ns + 86_400_000_000_000,
        total_seconds=86_400.0,
        bootstrap_seconds=20.0,
        closeout_seconds=600.0,
    )
    samples = iter(
        (
            {**anchor, "monotonic": 110.0, "boottime": 110.0,
             "utc_ns": t0_utc_ns + 130_000_000_000},
            {**anchor, "monotonic": 120.0, "boottime": 120.0,
             "utc_ns": t0_utc_ns + 70_000_000_000},
        )
    )
    monkeypatch.setattr(
        campaign, "clock_sample", lambda *, include_boot_id=False: next(samples)
    )
    monkeypatch.setattr(campaign, "time_namespace_identity", lambda: dict(namespace))

    attempt_one = window.observe(label="service_attempt_1_end")
    # A new service attempt creates a new account object but inherits the same
    # immutable window and append-only accounting file.
    attempt_two = replace(window).observe(label="service_attempt_2_start")

    first = attempt_one["accounting_record"]
    second = attempt_two["accounting_record"]
    assert first["sequence"] == 0
    assert second["sequence"] == 1
    assert first["deadline_utc_ns"] == second["deadline_utc_ns"] == window.deadline_utc_ns
    assert attempt_one["adjacent_charged_seconds"] == 110.0
    assert attempt_one["cumulative_charged_seconds"] == 130.0
    assert attempt_two["adjacent_charged_seconds"] == 10.0
    assert attempt_two["cumulative_charged_seconds"] == 140.0
    assert attempt_two["cumulative_charged_seconds"] > attempt_one["cumulative_charged_seconds"]
    assert second["adjacent_interval"]["elapsed_seconds"]["utc"] < 0.0

    ledger = tmp_path / campaign.CAMPAIGN_ACCOUNTING_NAME
    before = ledger.stat().st_size
    worker_sample = {
        **anchor,
        "monotonic": 121.0,
        "boottime": 121.0,
        "utc_ns": t0_utc_ns + 71_000_000_000,
    }
    worker = campaign.read_campaign_state(
        window,
        sample=worker_sample,
        namespace_identity=namespace,
    )
    assert worker["read_only"] is True
    assert worker["deadline_utc_ns"] == window.deadline_utc_ns
    assert worker["projected_cumulative_charged_seconds"] == 141.0
    assert ledger.stat().st_size == before


def test_v33_extension_seed_inherits_parent_charge_and_child_ledger_resumes(tmp_path):
    boot_id = "0bb7278d-a4d8-4b78-b625-895e739880e6"
    namespace = {"time": "time:[4026531834]", "time_for_children": "time:[4026531834]"}
    t0_utc_ns = 1_700_000_000_000_000_000
    anchor = {
        "monotonic": 100.0,
        "boottime": 100.0,
        "utc_ns": t0_utc_ns,
        "boot_id": boot_id,
    }
    parent_path = tmp_path / "campaign_accounting_parent.jsonl"
    parent_window = campaign.FixedCampaignWindow(
        path=tmp_path / "campaign_window_parent.json",
        sha256="a" * 64,
        payload={"accounting_path": str(parent_path)},
        anchor=anchor,
        t0_utc_ns=t0_utc_ns,
        deadline_utc_ns=t0_utc_ns + 86_400_000_000_000,
        total_seconds=86_400.0,
        bootstrap_seconds=0.0,
        closeout_seconds=1_200.0,
    )
    parent_sample = {
        **anchor,
        "monotonic": 110.0,
        "boottime": 110.0,
        "utc_ns": t0_utc_ns + 10_000_000_000,
    }
    campaign.CampaignAccount(parent_window).record_sample(
        parent_sample, label="parent_last_sample", namespace_identity=namespace
    )
    parent_state = campaign.verify_campaign_accounting_chain(parent_window)
    parent_bytes = parent_path.read_bytes()
    parent_sha = hashlib.sha256(parent_bytes).hexdigest()

    child_path = tmp_path / "campaign_accounting_v33_extension.jsonl"
    extension = {
        "parent_last_sequence": parent_state["last_sequence"],
        "parent_cumulative_charged_seconds": parent_state[
            "cumulative_charged_seconds"
        ],
        "parent_last_sample": parent_state["last_sample"],
        "parent_time_namespace_identity": parent_state[
            "time_namespace_identity"
        ],
        "parent_accounting_sha256": parent_state["sha256"],
    }
    child_window = campaign.FixedCampaignWindow(
        path=tmp_path / "campaign_window_v33_extension.json",
        sha256="b" * 64,
        payload={"accounting_path": str(child_path), "extension": extension},
        anchor=anchor,
        t0_utc_ns=t0_utc_ns,
        deadline_utc_ns=t0_utc_ns + 172_800_000_000_000,
        total_seconds=172_800.0,
        bootstrap_seconds=0.0,
        closeout_seconds=1_200.0,
    )
    first_seed = campaign.write_campaign_extension_seed(child_window, parent_state)
    seed = json.loads(child_path.read_bytes().splitlines()[0])
    assert seed["adjacent_interval"]["budget_seconds"] == 0.0
    assert seed["cumulative_charged_seconds"] == parent_state[
        "cumulative_charged_seconds"
    ]
    assert campaign.CampaignAccount(child_window).path == child_path.resolve()
    assert child_window.accounting_path == child_path.resolve()

    child_sample = {
        **anchor,
        "monotonic": 125.0,
        "boottime": 125.0,
        "utc_ns": t0_utc_ns + 25_000_000_000,
    }
    child_record = campaign.CampaignAccount(child_window).record_sample(
        child_sample,
        label="child_after_extension_downtime",
        namespace_identity=namespace,
    )
    assert child_record["sequence"] == parent_state["last_sequence"] + 1
    assert child_record["previous_sample"] == parent_state["last_sample"]
    assert child_record["adjacent_interval"]["budget_seconds"] == 15.0
    assert child_record["cumulative_charged_seconds"] == 25.0
    child_bytes = child_path.read_bytes()
    reopened_seed = campaign.write_campaign_extension_seed(child_window, parent_state)
    assert child_path.read_bytes() == child_bytes
    assert reopened_seed["seed"] == first_seed["seed"] == seed
    assert parent_path.read_bytes() == parent_bytes
    assert hashlib.sha256(parent_path.read_bytes()).hexdigest() == parent_sha

    launcher = Path(__file__).resolve().parents[1] / "runners/task038_launcher.py"
    assert "campaign_accounting_path = campaign_window.accounting_path" in launcher.read_text(
        encoding="utf-8"
    )


def test_v23_campaign_window_is_bound_to_its_exact_six_hour_registration():
    path = campaign.TASK40_V23_CAMPAIGN_WINDOW.resolve()
    window = campaign.load_fixed_campaign_window(path, require_current_boot=False)

    assert window.sha256 == campaign.TASK40_V23_CAMPAIGN_SHA256
    assert window.total_seconds == 21_600.0
    assert window.closeout_seconds == 1_200.0
    assert window.payload["stage_scope"] == list(campaign.TASK40_V23_STAGE_SCOPE)
    assert window.payload["forbidden_scope"] == list(campaign.TASK40_V23_FORBIDDEN_SCOPE)
    assert window.payload["parent_window"] == campaign.TASK40_V23_PARENT_WINDOW
    assert window.payload["parent_ledger"] == campaign.TASK40_V23_PARENT_LEDGER

    with pytest.raises(ValueError, match="SHA-256 changed"):
        campaign._validate_v23_campaign_registration(path, "0" * 64, window.payload)
    changed_scope = dict(window.payload, stage_scope=["implementation"])
    with pytest.raises(ValueError, match="identity or scope changed"):
        campaign._validate_v23_campaign_registration(
            path, window.sha256, changed_scope
        )


def test_v24_campaign_window_is_bound_to_its_exact_six_hour_registration():
    path = campaign.TASK40_V24_CAMPAIGN_WINDOW.resolve()
    window = campaign.load_fixed_campaign_window(path, require_current_boot=False)

    assert window.sha256 == campaign.TASK40_V24_CAMPAIGN_SHA256
    assert window.total_seconds == 21_600.0
    assert window.closeout_seconds == 1_200.0
    assert window.payload["campaign"] == campaign.TASK40_V24_CAMPAIGN_ID
    assert window.payload["stage_scope"] == list(campaign.TASK40_V24_STAGE_SCOPE)
    assert window.payload["forbidden_scope"] == list(campaign.TASK40_V24_FORBIDDEN_SCOPE)
    assert window.payload["parent_window"] == campaign.TASK40_V24_PARENT_WINDOW
    assert window.payload["parent_ledger"] == campaign.TASK40_V24_PARENT_LEDGER
    assert window.payload["artifact_execution_identity_separate"] is True

    with pytest.raises(ValueError, match="SHA-256 changed"):
        campaign._validate_v24_campaign_registration(path, "0" * 64, window.payload)
    changed_scope = dict(window.payload, stage_scope=["implementation"])
    with pytest.raises(ValueError, match="identity or scope changed"):
        campaign._validate_v24_campaign_registration(
            path, window.sha256, changed_scope
        )


def test_v25_campaign_window_is_bound_to_its_exact_six_hour_registration():
    path = campaign.TASK40_V25_CAMPAIGN_WINDOW.resolve()
    window = campaign.load_fixed_campaign_window(path, require_current_boot=False)

    assert window.sha256 == campaign.TASK40_V25_CAMPAIGN_SHA256
    assert window.total_seconds == campaign.TASK40_V25_CAMPAIGN_SECONDS
    assert window.closeout_seconds == campaign.TASK40_V25_CLOSEOUT_RESERVE_SECONDS
    assert window.payload["campaign"] == campaign.TASK40_V25_CAMPAIGN_ID
    assert window.payload["source_at_entry"] == campaign.TASK40_V25_SOURCE_AT_ENTRY
    assert window.payload["stage_scope"] == list(campaign.TASK40_V25_STAGE_SCOPE)
    assert window.payload["forbidden_scope"] == list(campaign.TASK40_V25_FORBIDDEN_SCOPE)
    assert window.payload["parent_window"] == campaign.TASK40_V25_PARENT_WINDOW
    assert window.payload["parent_ledger"] == campaign.TASK40_V25_PARENT_LEDGER

    with pytest.raises(ValueError, match="SHA-256 changed"):
        campaign._validate_v25_campaign_registration(path, "0" * 64, window.payload)
    changed_scope = dict(window.payload, stage_scope=["implementation"])
    with pytest.raises(ValueError, match="identity or scope changed"):
        campaign._validate_v25_campaign_registration(
            path, window.sha256, changed_scope
        )


def test_v30_window_preserves_unknown_boottime_and_requires_matching_boot(
    tmp_path, monkeypatch
):
    repository = tmp_path / "checkout"
    monkeypatch.setattr(
        campaign, "__file__", str(repository / "src/runners/task40_v10_campaign.py")
    )
    target_relative = Path("benchmarks/artifacts/v30/campaign_window_v30.json")
    monkeypatch.setattr(
        campaign, "TASK40_V30_CAMPAIGN_WINDOW", Path("benchmarks/artifacts/v30/control.json")
    )
    monkeypatch.setattr(campaign, "TASK40_V30_TARGET_CAMPAIGN_WINDOW", target_relative)
    monkeypatch.setattr(campaign, "_validate_v30_campaign_registration", lambda *args: None)

    t0_utc = "2030-01-01T00:00:00Z"
    t0_ns = campaign._utc_ns(t0_utc)
    boot_id = "12345678-1234-1234-1234-123456789abc"
    payload = {
        "schema": campaign.CAMPAIGN_SCHEMA,
        "window_refreshed": False,
        "old_costs_and_unknowns_preserved": True,
        "campaign_seconds": campaign.TASK40_V30_CAMPAIGN_SECONDS,
        "time_policy": campaign.CONSERVATIVE_REALTIME,
        "t0_utc": t0_utc,
        "deadline_utc": "2030-01-01T12:00:00Z",
        "first_full_three_clock_sample": {
            "monotonic": 6.0,
            "boottime": 5.0,
            "utc_ns": t0_ns + 15_000_000_000,
            "boot_id": boot_id,
        },
        "initial_boot_id": boot_id,
        "bootstrap_utc_elapsed_seconds": 15.0,
        "bootstrap_boottime_elapsed_seconds": None,
        "bootstrap_time_treatment": "UTC elapsed; boottime UNKNOWN; null is not zero.",
        "closeout_reserve_seconds": campaign.TASK40_V30_CLOSEOUT_RESERVE_SECONDS,
    }
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    target_path = repository / target_relative
    target_path.parent.mkdir(parents=True)
    target_path.write_bytes(encoded)
    monkeypatch.setattr(
        campaign,
        "TASK40_V30_TARGET_CAMPAIGN_SHA256",
        hashlib.sha256(encoded).hexdigest(),
    )

    window = campaign.load_fixed_campaign_window(target_path, require_current_boot=False)
    assert window.payload["bootstrap_boottime_elapsed_seconds"] is None
    assert window.bootstrap_seconds == 15.0

    monkeypatch.setattr(
        campaign,
        "clock_sample",
        lambda **kwargs: {"boot_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
    )
    with pytest.raises(campaign.TimebaseInconsistency, match="boot identity changed"):
        campaign.load_fixed_campaign_window(target_path)

    monkeypatch.setattr(campaign, "clock_sample", lambda **kwargs: {"boot_id": boot_id})
    assert campaign.load_fixed_campaign_window(target_path).anchor["boot_id"] == boot_id
