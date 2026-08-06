from __future__ import annotations

import hashlib
import json

import pytest

import benchmarks.check_task037_extra_full_channels as channel_checker


def test_g0_posthoc_checker_recomputes_twelve_channels(tmp_path, monkeypatch):
    authority_channels = []
    current_orders = []
    for index in range(12):
        prefix = "R" if index < 6 else "T"
        side = "top" if prefix == "R" else "bottom"
        m = -7 + (index % 6)
        label = f"{prefix}({m},0)_s"
        power = 0.1 + index
        amplitude = [float(index), -float(index)]
        authority_channels.append(
            {
                "label": label,
                "direct_power": power,
                "power_tolerance": 0.1,
                "direct_boundary_amplitude": amplitude,
                "amplitude_tolerance": 0.1,
                "power_pass": False,
                "amplitude_pass": False,
                "power_abs_diff": 999.0,
                "amplitude_abs_diff": 999.0,
            }
        )
        current_orders.append(
            {
                "side": side,
                "m": m,
                "n": 0,
                "polarization": "s",
                "power_ratio": power + 0.01,
                "outgoing_amplitude_at_boundary": [
                    amplitude[0] + 0.01,
                    amplitude[1] - 0.02,
                ],
            }
        )

    authority_path = tmp_path / "authority.json"
    current_path = tmp_path / "current.json"
    authority_path.write_text(
        json.dumps({"channels_12": authority_channels}), encoding="utf-8"
    )
    current_path.write_text(json.dumps({"orders": current_orders}), encoding="utf-8")

    fixture_sha = hashlib.sha256(authority_path.read_bytes()).hexdigest()
    monkeypatch.setattr(channel_checker, "EXPECTED_AUTHORITY_SHA256", fixture_sha)
    report = channel_checker.check_channels(authority_path, current_path)

    assert report["overall_pass"] is True
    assert report["power_pass_count"] == 12
    assert report["amplitude_pass_count"] == 12
    assert (
        report["reference_role"]
        == "direct_authority_embedded_in_historical_m3a_record"
    )
    assert report["channels"][0]["reference_power"] == pytest.approx(0.1)
    assert report["channels"][0]["reference_amplitude"] == [0.0, 0.0]
    assert report["channels"][0]["power_abs_diff"] == pytest.approx(0.01)
    assert report["channels"][0]["amplitude_abs_diff"] == pytest.approx(
        0.022360679774997897
    )
