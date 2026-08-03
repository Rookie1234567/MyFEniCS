"""Pure-Python guards for the Task004 M4A/M4B/M4C contract."""

from __future__ import annotations

import numpy as np
import pytest

from src.surrogate.angle.api import AngleSurrogate
from src.surrogate.angle.models import MaskedFractionPowerModel, region_masks
from src.surrogate.models import deterministic_optimization_initials


def test_public_api_refuses_unqualified_package(tmp_path):
    (tmp_path / "angle_model.pkl").write_bytes(b"not loaded")
    with pytest.raises(RuntimeError, match="fail-closed"):
        AngleSurrogate.from_package(tmp_path)


def test_ard_initials_cover_high_dimensional_f3():
    starts = deterministic_optimization_initials(13, count=8)
    assert len(starts) == 8
    assert all(item.shape == (13,) for item in starts)


def test_region_masks_are_overlapping():
    angles = np.asarray([[5.25, 45.0], [1.0, 45.0]])
    masks = region_masks(angles)
    assert np.any(masks["ordinary_interior"] & masks["cutoff_near"])
    assert bool(masks["low_grazing"][1])


def test_unseen_power_topology_fails_closed():
    angles = np.asarray([[5.0, 45.0], [6.0, 45.0], [7.0, 45.0]])
    powers = np.full((3, 22, 2), np.nan)
    mask = np.zeros((3, 22, 2), dtype=bool)
    # One active reflection and transmission channel is the only trained
    # topology; the query asks for an additional channel.
    mask[:, 7, 0] = True; mask[:, 18, 0] = True
    powers[:, 7, 0] = 0.5; powers[:, 18, 0] = 0.5
    model = MaskedFractionPowerModel().fit(angles, powers, mask)
    query_mask = mask[:1].copy(); query_mask[0, 6, 0] = True
    output, uncertainty = model.predict(
        angles[:1], np.asarray([[0.5, 0.5, 0.0]]), query_mask,
    )
    assert model.unsupported_topologies
    assert np.isnan(output[0, 6, 0])
    assert np.isnan(uncertainty[0, 6, 0])
