"""Versioned campaign, route timing and label isolation; no physical replay."""

from pathlib import Path

from src.io.neural_wave_campaign import (
    ROOT,
    load_wave,
    profile_paths,
    training_open_allowed,
)
from src.runners.neural_wave_campaign import stage_deadline


def test_v30_default_and_v31_distinct_window_and_artifacts():
    old = load_wave(ROOT / "input/task042extra_feinn_5nm/v30_m5_fixed_wave.dat")
    new = load_wave(ROOT / "input/task042extra_feinn_5nm/v31_fixed_block_wave.dat")
    assert profile_paths(old)["root"].name == "v30"
    assert profile_paths(new)["root"].name == "v31"
    assert old["max_seconds"] == 172800
    assert new["max_seconds"] == 21600
    assert new["role"] == "FIXED_WAVE_BLOCK_GREEDY"
    assert profile_paths(new)["reserve"] == 3600


def test_both_new_routes_same_preserved_wall_and_verification_reserve():
    campaign = dict(deadline_monotonic=100000)
    allocation = dict(deadline_monotonic=20000)
    for role in ("FIXED_WAVE_BLOCK_GREEDY", "LEARNED_WAVE_BLOCK_GREEDY"):
        deadline, reserve = stage_deadline(
            dict(role=role, campaign_version=31), allocation, campaign
        )
        assert deadline == 20000 and reserve == 7200
    deadline, reserve = stage_deadline(
        dict(role="FIXED_WAVE_GREEDY_CONTROL"), allocation, campaign
    )
    assert deadline == 20000 and reserve == 5400


def test_training_data_whitelist_and_own_boundary_only():
    import json

    design = json.loads(
        (ROOT / "input/task042extra_feinn_5nm/design_v31.json").read_text()
    )
    design["active_training_artifact"] = str(
        ROOT / "benchmarks/artifacts/task42extra/v31/v31_learned_block_wave"
    )
    assert training_open_allowed(ROOT / design["files"]["native"]["path"], design)
    assert training_open_allowed(
        Path(design["active_training_artifact"]) / "basis/state_1.npz", design
    )
    for file in (
        ROOT
        / "benchmarks/artifacts/task42extra/v30/v30_m5_learned_wave/basis/state_1.npz",
        ROOT
        / "benchmarks/artifacts/task42extra/v31/v31_fixed_block_wave/basis/state_1.npz",
        ROOT / "benchmarks/artifacts/task42extra/v31/v31_block_reconstruct/raw.npz",
        ROOT / "benchmarks/artifacts/task42extra/reference_state.npz",
        ROOT / "benchmarks/artifacts/task42extra/index_e3_reference.json",
        ROOT / "old.pt",
    ):
        assert not training_open_allowed(file, design)


def test_successful_psi_checks_are_not_failed_wait_pool(monkeypatch, tmp_path):
    from src.runners import block_wave_admission as policy, feinn_resources

    monkeypatch.setattr(policy, "POOL", tmp_path / "pool.jsonl")
    monkeypatch.setattr(
        feinn_resources,
        "stable_window",
        lambda *a, **k: dict(passed=True, observed_seconds=60),
    )
    assert policy.stable_window(tmp_path, 2 * 2**30)["passed"]
    assert policy.rejected_wait_seconds() == 0

    def refuse(*a, **k):
        raise RuntimeError("actual unsafe PSI")

    monkeypatch.setattr(feinn_resources, "stable_window", refuse)
    import pytest

    with pytest.raises(RuntimeError):
        policy.stable_window(tmp_path, 2 * 2**30)
    assert policy.POOL.exists()
    assert policy.rejected_wait_seconds() >= 0


def test_new_six_hour_ceiling_reserves_verification_and_preserves_old_default():
    from src.runners.neural_wave_campaign import worker_stop_time

    for role in ("FIXED_WAVE_BLOCK_GREEDY", "LEARNED_WAVE_BLOCK_GREEDY"):
        assert worker_stop_time(dict(role=role, campaign_version=31), 21600) == 19800
    assert worker_stop_time(dict(role="LEARNED_WAVE_GREEDY"), 172800) == 172650


def test_decimal_only_selected_binary_terms_no_field_solver():
    from src.postprocessing.neural_wave_roundoff import decimal_sum

    value, evidence = decimal_sum([1e16 + 2e16j, 1 - 3j, -1e16 - 2e16j])
    assert value == 1 - 3j
    assert evidence["precision"] == 110
