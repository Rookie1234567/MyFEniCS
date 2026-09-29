"""Guard the actual adapter's array-input boundary, not just its label."""

from unittest.mock import patch

from src.runners.neural_fe_calibration import stage_moments


def test_column_stages_do_not_read_neural_moment_arrays():
    identity = {"moment_packet": {"sha256": "identity-only"}}
    with patch(
        "src.runners.neural_fe_calibration.read_moments",
        side_effect=AssertionError("forbidden moment read"),
    ):
        for stage in ("V8-C2-SETUP", "V8-C2-LSQR", "V8-C2-VERIFY"):
            arrays, record = stage_moments(stage, identity)
            assert arrays is None
            assert record == identity["moment_packet"]


def test_neural_stages_and_reuse_inventory_retain_original_moments():
    packet, record = object(), {"sha256": "original-qualified-packet"}
    with patch(
        "src.runners.neural_fe_calibration.read_moments", return_value=(packet, record)
    ) as read:
        for stage in ("V8-C0", "V8-C3-EQUIVALENCE", "V8-C3-MICRO"):
            assert stage_moments(stage, {}) == (packet, record)
        assert read.call_count == 3
