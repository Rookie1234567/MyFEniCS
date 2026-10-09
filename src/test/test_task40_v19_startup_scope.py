from types import SimpleNamespace

import pytest

from src.runners.task40_v10_worker import (
    _v19_prepare_saved_v18_startup_reference,
)


def test_v19_registered_e1_q4_skips_inapplicable_v18_ny8_startup_receipt():
    profile = SimpleNamespace(
        name="task40extra_v17_p6_y_orbit_e1_reference_v1",
        q_count=4,
    )
    assert _v19_prepare_saved_v18_startup_reference({}, profile) is None


@pytest.mark.parametrize(
    ("profile_name", "q_count"),
    [
        ("task40extra_v17_p6_y_orbit_b0_reference_v1", 4),
        ("unregistered_profile", 4),
        ("task40extra_v17_p6_y_orbit_e1_reference_v1", 3),
    ],
)
def test_v19_q4_near_misses_still_require_qualified_receipt(profile_name, q_count):
    profile = SimpleNamespace(name=profile_name, q_count=q_count)
    with pytest.raises(
        ValueError,
        match="requires the qualified V18 Ny8 reuse receipt",
    ):
        _v19_prepare_saved_v18_startup_reference({}, profile)


def test_v19_ny8_b0_still_requires_qualified_v18_reuse_receipt():
    profile = SimpleNamespace(
        name="task40extra_v18_p6_y_orbit_b0_y8_reference_v1",
        q_count=8,
    )
    with pytest.raises(
        ValueError,
        match="requires the qualified V18 Ny8 reuse receipt",
    ):
        _v19_prepare_saved_v18_startup_reference({}, profile)
