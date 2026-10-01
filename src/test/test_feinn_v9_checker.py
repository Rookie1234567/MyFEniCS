"""Negative raw-record fixtures: loss improvement cannot confer a GN signal."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from benchmarks.check_task42extra_v9 import gn_qualification, research_signal


def test_actual_bound_qualification_arithmetic_and_corrupted_adjoint_rejected():
    root = Path(__file__).resolve().parents[2]
    raw = json.loads(
        (
            root / "docs/task042extra_feinn_5nm/outcomes/records/gn_checks_v9.json"
        ).read_text()
    )["result"]
    assert gn_qualification(raw)["qualified"]
    bad = deepcopy(raw)
    bad["routes"]["plain"]["direction_checks"][0]["real_adjoint"] = 0.1
    with pytest.raises(ValueError, match="REAL_ADJOINT"):
        gn_qualification(bad)


def test_research_signal_requires_both_original_residuals_and_both_fields():
    old = dict(
        equation_audit=dict(native_relative=1.0, augmented_relative=1.0),
        errors={
            key: dict(relative=0.2) for key in ("scattered_L2", "scattered_scaled_curl")
        },
    )
    new = deepcopy(old)
    new["equation_audit"] = dict(native_relative=0.05, augmented_relative=0.05)
    for field in new["errors"].values():
        field["relative"] = 0.09
    assert research_signal(new, old)["signal"]
    for quantity in ("native_relative", "augmented_relative"):
        bad = deepcopy(new)
        bad["equation_audit"][quantity] = 0.11
        assert not research_signal(bad, old)["signal"]
    for quantity in ("scattered_L2", "scattered_scaled_curl"):
        bad = deepcopy(new)
        bad["errors"][quantity]["relative"] = 0.101
        assert not research_signal(bad, old)["signal"]
