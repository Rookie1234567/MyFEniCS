"""The save reservation includes import time and never resets the launch clock."""

import pytest

from src.runners.feinn_workflow import replay_closure_deadline


def test_import_delay_does_not_move_closure_deadline():
    manifest = dict(
        supervision_budget_origin_monotonic=1000, supervised_limit_seconds=10800
    )
    deadline = replay_closure_deadline(manifest)
    # A worker entering after 9 seconds still leaves 150 seconds from launch.
    worker_entered = 1009
    assert deadline - worker_entered == 10800 - 150 - 9
    assert 1000 + 10800 - deadline == 150


def test_reduced_budget_keeps_save_reservation():
    manifest = dict(
        supervision_budget_origin_monotonic=1000, supervised_limit_seconds=900
    )
    assert replay_closure_deadline(manifest) == 1750
    with pytest.raises(ValueError, match="REPLAY_SAVE_RESERVE_UNAVAILABLE"):
        replay_closure_deadline(dict(manifest, supervised_limit_seconds=150))
