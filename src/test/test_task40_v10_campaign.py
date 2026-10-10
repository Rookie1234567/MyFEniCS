from dataclasses import replace

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
