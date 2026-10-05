"""Independent two-pass projection, invalidation and real-gradient fixtures."""

import numpy as np
import pytest

from src.solvers.neural_wave_projection import ResidualProjectionCache
from src.solvers.neural_wave_subspace import WaveSubspace, conjugate_product
from src.solvers.neural_wave_greedy import variable_projection
from src.solvers.neural_wave_moments import WaveMoments
from src.test.test_neural_wave import fixture


@pytest.mark.parametrize("count", [0, 3, 8])
def test_exact_two_pass_sparse_dense_pair_and_near_cancellation(count):
    rng, _, action = fixture()
    space = WaveSubspace(action, 12)
    for _ in range(count):
        assert space.add(rng.normal(size=action.size) + 1j * rng.normal(size=action.size))["accepted"]
    rows = np.arange(0, action.size, 2)
    cached = ResidualProjectionCache(space, rows)
    np.testing.assert_allclose(
        cached.small_product, conjugate_product(space.Q[:, :count], space.Q[:, :count]),
        rtol=1e-13, atol=1e-13,
    )
    values = np.zeros((action.size, 6), complex)
    values[rows] = rng.normal(size=(len(rows), 6)) + 1j * rng.normal(size=(len(rows), 6))
    np.testing.assert_allclose(cached.project(values, supported=True), space.project(values), rtol=1e-12, atol=1e-12)
    vector = rng.normal(size=action.size) + 1j * rng.normal(size=action.size)
    np.testing.assert_allclose(cached.project(vector), space.project(vector), rtol=1e-12, atol=1e-12)
    if count:
        cancelled = space.Q[:, :count] @ (rng.normal(size=count) + 1j * rng.normal(size=count))
        np.testing.assert_array_equal(cached.project(cancelled), space.project(cancelled))
        assert cached.counts["explicit_two_pass_fallback"] == 1
    bad = values.copy()
    bad[1, 0] = 1e-200
    with pytest.raises(ValueError, match="EXACT_SUPPORT_FAILED"):
        cached.project(bad, supported=True)
    assert space.add(rng.normal(size=action.size) + 1j * rng.normal(size=action.size))["accepted"]
    with pytest.raises(ValueError, match="CACHE_STALE"):
        cached.project(vector)
    replaced = ResidualProjectionCache(space, rows)
    np.testing.assert_allclose(replaced.small_product, conjugate_product(space.Q[:, :space.m], space.Q[:, :space.m]), atol=1e-13, rtol=1e-13)


def test_full_native_score_gradient_and_nonzero_parameter_direction():
    from src.solvers.neural_wave_greedy import Patch

    rng, packet, action = fixture()
    moments = WaveMoments(packet)
    space = WaveSubspace(action, 8)
    for _ in range(3):
        space.add(rng.normal(size=action.size) + 1j * rng.normal(size=action.size))
    cached = ResidualProjectionCache(space, np.arange(action.size))
    patch = Patch((0.8, 0.5, 0.3), (2.0, 1.0, 1.0))
    q = rng.normal(size=(2, 3))
    old = variable_projection(action, space, moments, patch, q, gradient=True)
    new = variable_projection(action, space, moments, patch, q, gradient=True, projector=cached)
    for j in (0, 1, 2, 4):
        np.testing.assert_allclose(new[j], old[j], rtol=1e-10, atol=1e-11)
    direction = rng.normal(size=q.shape)
    direction /= np.linalg.norm(direction)
    step = 1e-5
    upper = variable_projection(action, space, moments, patch, q + step * direction, gradient=False, projector=cached)[0]
    lower = variable_projection(action, space, moments, patch, q - step * direction, gradient=False, projector=cached)[0]
    finite = (upper - lower) / (2 * step) / action.bnorm**2
    assert abs(finite - np.sum(new[4] * direction)) <= 1e-7 * max(1, abs(finite))
    # q trials leave the basis/cached projector intact; accepted changes reject it.
    assert cached.columns == space.m


def test_cache_capacity_and_restored_basis_rebuild():
    _, _, action = fixture()
    space = WaveSubspace(action, 4)
    with pytest.raises(MemoryError, match="2GIB_PLANNING_LINE"):
        ResidualProjectionCache(space, np.arange(action.size), additional_cache_bytes=2 * 2**30)
    space.m = 3
    space.Q[:, :3] = np.linalg.qr(np.eye(action.size, 3, dtype=complex))[0]
    cached = ResidualProjectionCache(space, np.arange(action.size))
    np.testing.assert_array_equal(cached.small_product, np.eye(3))


def test_dependent_amplitude_columns_use_original_two_pass_rounding_path():
    from src.solvers.neural_wave_greedy import Patch

    rng, packet, action = fixture()
    space = WaveSubspace(action, 8)
    for _ in range(3):
        assert space.add(rng.normal(size=action.size) + 1j * rng.normal(size=action.size))["accepted"]
    moments = WaveMoments(packet)
    patch = Patch((0.8, 0.5, 0.3), (2.0, 1.0, 1.0))
    q = np.repeat(rng.normal(size=(1, 3)), 2, axis=0)
    cached = ResidualProjectionCache(space, np.arange(action.size))
    original = variable_projection(action, space, moments, patch, q, gradient=True)
    actual = variable_projection(action, space, moments, patch, q, gradient=True, projector=cached)
    assert actual[3]["original_two_pass_rounding_fallback"]
    for j in (0, 1, 2, 4):
        np.testing.assert_array_equal(actual[j], original[j])


def test_inherited_route_span_is_not_additive_attempt_cost_or_new_budget():
    from src.runners.neural_wave_campaign import timing_fields

    allocation = dict(origin_monotonic=100.0, deadline_monotonic=172900.0)
    actual = timing_fields(allocation, dict(origin_monotonic=5000.0), 6000.0)
    assert actual["actual_attempt_elapsed_seconds"] == 1000.0
    assert actual["inherited_route_allocation_span_seconds"] == 5900.0
    assert actual["launch_to_summary_seconds"] == 5900.0
    assert allocation["deadline_monotonic"] == 172900.0
    for origin in (99.0, 6001.0):
        with pytest.raises(ValueError, match="TIMEBASE_INCONSISTENT"):
            timing_fields(allocation, dict(origin_monotonic=origin), 6000.0)
