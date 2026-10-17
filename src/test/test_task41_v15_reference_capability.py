from types import SimpleNamespace

import pytest

from src.runners.task40_v10_output_checker import (
    _registered_v15_profile_inventory as checker_inventory,
)
from src.solvers.augmented_reference_correction import (
    _registered_v15_profile_inventory as adapter_inventory,
)
from src.solvers import task40_v10_p6_periodic_profile as periodic_profiles


def test_task41_a2_has_exact_v15_capability_without_entering_task40_selector_set():
    profile = periodic_profiles.TASK41_G13_A2_P6_PROFILE
    assert profile.name not in periodic_profiles.TASK40_V15_SELECTOR_PROFILE_IDENTITIES
    assert profile.q_port_counts[1:3] == (0, 0)
    assert tuple(
        profile.q_port_counts[q] + profile.q_port_counts[q + 5]
        for q in range(5)
    ) == profile.sector_port_counts

    for inventory in (adapter_inventory, checker_inventory):
        admitted = inventory(profile.name)
        assert admitted["identity"] == profile.name
        assert admitted["q_count"] == 10
        assert admitted["twist_count"] == 5
        assert admitted["mode_count"] == 168
        assert admitted["sector_port_counts"] == (32, 28, 28, 40, 40)


def test_task41_v15_capability_rejects_near_match_and_inventory_drift(monkeypatch):
    profile = periodic_profiles.TASK41_G13_A2_P6_PROFILE
    near_match = profile.name + "_near_match"
    assert periodic_profiles.task41_a2_v15_reference_profile(near_match) is None
    with pytest.raises(ValueError, match="explicitly admitted"):
        adapter_inventory(near_match)
    with pytest.raises(ValueError, match="unknown registered"):
        checker_inventory(near_match)

    monkeypatch.setattr(
        periodic_profiles,
        "TASK41_G13_A2_P6_PROFILE",
        SimpleNamespace(
            name=profile.name,
            global_cell_axes=profile.global_cell_axes,
            global_cell_count=profile.global_cell_count,
            q_count=profile.q_count,
            q_port_counts=profile.q_port_counts,
            replication_count=profile.replication_count,
            sector_port_counts=(31, 28, 28, 40, 40),
            mode_count=profile.mode_count,
        ),
    )
    with pytest.raises(ValueError, match="capability inventory differs"):
        periodic_profiles.task41_a2_v15_reference_profile(profile.name)
