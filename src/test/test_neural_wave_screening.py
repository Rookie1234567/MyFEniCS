"""Frozen candidate order/coverage, independent old calls and corruption."""

import numpy as np
import pytest

from src.solvers.neural_wave_greedy import Patch, variable_projection
from src.solvers.neural_wave_moments import WaveMoments
from src.solvers.neural_wave_projection import ResidualProjectionCache
from src.solvers.neural_wave_screening import screen_candidates
from src.solvers.neural_wave_subspace import WaveSubspace, optimal_amplitudes
from src.test.test_neural_wave import fixture


@pytest.mark.parametrize("width", [1, 2, 4, 8])
def test_same_eight_frozen_candidates_individual_svd_and_best_direction(width):
    rng, packet, action = fixture()
    space = WaveSubspace(action, 8)
    for _ in range(3):
        space.add(rng.normal(size=action.size) + 1j * rng.normal(size=action.size))
    moments = WaveMoments(packet)
    patch = Patch((0.8, 0.5, 0.3), (2.0, 1.0, 1.0))
    cache = ResidualProjectionCache(space, np.arange(action.size))
    proposals = [rng.normal(size=(width, 3)) for _ in range(8)]
    # Include repeated/correlated amplitude columns, never silently drop them.
    proposals[-1][:] = proposals[-1][0]
    expected = [variable_projection(action, space, moments, patch, q, gradient=False) for q in proposals]
    before = moments.counts["forward"]
    actual = screen_candidates(action, space, moments, patch, proposals, local=None, projector=cache)
    fallback_count = sum(v is not None and v[3].get("original_complete_candidate_rounding_fallback", False) for v in actual)
    assert moments.counts["forward"] - before == 1 + fallback_count
    assert len(actual) == len(expected) == 8
    for got, want in zip(actual, expected, strict=True):
        assert got is not None
        for j in (0, 1, 2):
            np.testing.assert_allclose(got[j], want[j], rtol=1e-10, atol=1e-10)
        assert got[3]["rank"] == want[3]["rank"]
    assert np.argmax([v[0] for v in actual]) == np.argmax([v[0] for v in expected])
    # Rejections/trials have not changed the accepted state or projector.
    assert space.m == cache.columns == 3


def test_zero_candidates_retained_as_degenerate_and_layout_rejected():
    rng, packet, action = fixture()
    space = WaveSubspace(action, 4)
    moments = WaveMoments(packet)
    cache = ResidualProjectionCache(space, np.arange(action.size))
    zero_support = Patch((50., 50., 50.), (0.1, 0.1, 0.1))
    proposals = [rng.normal(size=(2, 3)) for _ in range(8)]
    assert screen_candidates(action, space, moments, zero_support, proposals, local=None, projector=cache) == [None] * 8
    with pytest.raises(ValueError, match="MODULE_LAYOUT_REQUIRED"):
        screen_candidates(action, space, moments, zero_support, [np.zeros((16, 3))], local=None, projector=cache)


@pytest.mark.parametrize("corruption", ["shape", "real_dtype", "nonfinite"])
def test_preprojected_blocks_cannot_bypass_complex_layout_and_finite_checks(corruption):
    rng, packet, action = fixture()
    space = WaveSubspace(action, 4)
    moments = WaveMoments(packet)
    patch = Patch((0.8, 0.5, 0.3), (2.0, 1.0, 1.0))
    columns = moments.columns(patch, rng.normal(size=(2, 3)))
    applied = np.column_stack([action.apply(c) for c in columns.T])
    projected = space.project(applied)
    if corruption == "shape":
        projected = projected[:-1]
    elif corruption == "real_dtype":
        projected = projected.real
    else:
        projected[0, 0] = np.nan
    with pytest.raises(ValueError, match="PROJECTED_CANDIDATE_COLUMNS_INVALID"):
        optimal_amplitudes(action, space, columns, applied_columns=applied,
                           projected_columns=projected)


def test_new_block_keeps_full_native_energy_decrease_and_original_field():
    rng, packet, action = fixture()
    original, batched = WaveSubspace(action, 8), WaveSubspace(action, 8)
    for _ in range(2):
        column = rng.normal(size=action.size) + 1j * rng.normal(size=action.size)
        assert original.add(column)["accepted"]
        assert batched.add(column)["accepted"]
    moments = WaveMoments(packet)
    patch = Patch((0.8, 0.5, 0.3), (2.0, 1.0, 1.0))
    directions = [rng.normal(size=(2, 3)) for _ in range(8)]
    expected = [variable_projection(action, original, moments, patch, q, gradient=False)
                for q in directions]
    cache = ResidualProjectionCache(batched, np.arange(action.size))
    actual = screen_candidates(action, batched, moments, patch, directions,
                               local=None, projector=cache)
    old_best = max(expected, key=lambda value: value[0])
    new_best = max(actual, key=lambda value: value[0])
    before = float(np.vdot(original.r, original.r).real)
    assert original.add(old_best[2])["accepted"]
    assert batched.add(new_best[2])["accepted"]
    np.testing.assert_allclose(batched.c, original.c, rtol=1e-10, atol=1e-10)
    np.testing.assert_allclose(batched.r, original.r, rtol=1e-10, atol=1e-10)
    actual_decrease = before - float(np.vdot(batched.r, batched.r).real)
    np.testing.assert_allclose(actual_decrease, new_best[0], rtol=1e-10, atol=1e-10)
    with pytest.raises(ValueError, match="CACHE_STALE"):
        cache.project(action.f)
