"""Opt-in block algebra, original amplitude maps and complete boundaries."""

import json
from dataclasses import asdict

import numpy as np
import pytest
from scipy import linalg

from src.solvers.neural_wave_block import (
    BlockWaveSubspace,
    BlockBasisStore,
    compensated_columns,
)
from src.solvers.neural_wave_subspace import WaveSubspace, optimal_amplitudes
from src.solvers.neural_wave_moments import Patch
from src.solvers.neural_wave_projection import ResidualProjectionCache


class DenseAction:
    def __init__(self, A, f):
        self.A = A
        self.f = np.asarray(f, np.complex128)
        self.size = len(f)
        self.bnorm = float(np.linalg.norm(f))

    def apply(self, v, adjoint=False):
        return (self.A.conj().T if adjoint else self.A) @ v


def test_immediate_equivalence_and_later_recombination():
    a = DenseAction(np.eye(3, dtype=complex), np.array([1, 0, 1]))
    block, old = BlockWaveSubspace(a, 3), WaveSubspace(a, 3)
    C = np.eye(3, dtype=complex)[:, :2]
    p, _, _ = optimal_amplitudes(a, old, C)
    assert block.add_block(C)["accepted"]
    assert old.add(C @ p)["accepted"]
    np.testing.assert_allclose(old.c, block.c, rtol=1e-12, atol=1e-12)
    C2 = np.array([[0], [1], [1]], dtype=complex)
    block.add_block(C2)
    old.add(C2[:, 0])
    assert np.linalg.norm(old.r) / a.bnorm == pytest.approx(0.5)
    assert np.linalg.norm(block.r) / a.bnorm < 1e-14


def test_global_rank_is_not_sum_of_block_ranks_and_projection_matches_svd(tmp_path):
    action = DenseAction(np.eye(4, dtype=complex), [1, 1j, 2, -1j])
    s = BlockWaveSubspace(action, 4)
    first = np.eye(4, dtype=complex)[:, :1]
    second = first + 1.5e-12 * np.eye(4, dtype=complex)[:, 1:2]
    zeros = np.zeros((4, 2), complex)
    binding = dict(
        route="control",
        source_sha="source",
        native_sha256="a",
        moments_sha256="m",
        design_sha256="d",
    )
    store = BlockBasisStore(tmp_path, binding)
    rng = np.random.default_rng(4213103)
    model = dict(q=np.array([[0.2, -0.1, 0.3]]), patch=Patch((0, 0, 0), (1, 1, 1)))
    initial = s.add_block(np.hstack([first, zeros]))
    assert initial["accepted"]
    store.commit(s, model, 1, initial, rng, 1e99)
    event = s.add_block(np.hstack([second, zeros]))
    assert event["accepted"]
    assert s.m == 2 and s.effective_rank == 1
    C = np.column_stack([first, second])
    scales = np.linalg.norm(C, axis=0)
    coeff = linalg.lstsq(C / scales, action.f, cond=1e-12)[0]
    np.testing.assert_allclose(s.c, C / scales @ coeff, atol=1e-12)
    left, sv, _ = linalg.svd(C / scales, full_matrices=False)
    Q = left[:, sv > 1e-12 * sv[0]]
    rng = np.random.default_rng(4213103)
    value = rng.normal(size=(4, 3)) + 1j * rng.normal(size=(4, 3))
    expected = value - Q @ (Q.conj().T @ value)
    np.testing.assert_allclose(s.project(value), expected, atol=1e-12)
    cache = ResidualProjectionCache(s, np.arange(4))
    np.testing.assert_allclose(
        cache.project(value, supported=True), expected, atol=1e-12
    )
    assert event["small_full_action_pair_relative"] < 1e-12
    store.commit(s, model, 2, event, rng, 1e99)
    restored = BlockWaveSubspace(action, 4)
    boundary = BlockBasisStore(tmp_path, binding).restore(restored, rng)
    assert restored.effective_rank == s.effective_rank
    np.testing.assert_allclose(restored.project(value), expected, atol=1e-12)
    from src.solvers.neural_wave_greedy import atomic_npz, sha

    path = tmp_path / boundary["state"]["path"]
    with np.load(path, allow_pickle=False) as z:
        fields = {k: np.array(z[k]) for k in z.files}
    fields["projection_null"] = np.array([[1], [0]], complex)
    atomic_npz(path, **fields)
    boundary["state"]["sha256"] = sha(path)
    (tmp_path / "committed.json").write_text(json.dumps(boundary))
    with pytest.raises(ValueError, match="RECOVERY_RETAINED_RANGE_LAYOUT_FAILED"):
        BlockBasisStore(tmp_path, binding).restore(BlockWaveSubspace(action, 4), rng)


@pytest.mark.parametrize(
    "kind", ["full", "duplicate", "nearly_correlated", "scales", "zero"]
)
def test_nonhermitian_against_independent_svd(kind):
    rng = np.random.default_rng(4213101)
    A = rng.normal(size=(12, 12)) + 1j * rng.normal(size=(12, 12))
    f = rng.normal(size=12) + 1j * rng.normal(size=12)
    C = rng.normal(size=(12, 5)) + 1j * rng.normal(size=(12, 5))
    if kind == "duplicate":
        C[:, 3] = C[:, 0]
    if kind == "nearly_correlated":
        C[:, 3] = C[:, 0] + 1e-6 * C[:, 3]
    if kind == "scales":
        C *= np.array([1e-8, 1e8, 1, 0.2, 5])[None, :]
    if kind == "zero":
        C[:, 3] = 0
    action = DenseAction(A, f)
    space = BlockWaveSubspace(action, 12)
    event = space.add_block(C)
    assert event["accepted"]
    B = A @ C
    scales = np.linalg.norm(B, axis=0)
    keep = scales > 0
    coeff = linalg.lstsq(
        B[:, keep] / scales[keep], f, cond=1e-12, lapack_driver="gelsd"
    )[0]
    expected = f - B[:, keep] / scales[keep] @ coeff
    np.testing.assert_allclose(space.r, expected, rtol=1e-8, atol=1e-9)
    np.testing.assert_allclose(
        C @ space.pending_block["amplitude_map"],
        space.U[:, : space.m],
        rtol=1e-14,
        atol=1e-14,
    )
    assert space.rank_audit()["orthogonality"] < 1e-12


def test_whole_block_rolls_back_on_actual_action_failure():
    action = DenseAction(np.eye(6, dtype=complex), np.arange(1, 7))
    s = BlockWaveSubspace(action, 6)
    s.add_block(np.eye(6, dtype=complex)[:, :2])
    previous = s.m, s.a.copy(), s.c.copy(), s.r.copy()
    original = action.apply
    calls = 0

    def broken(v, adjoint=False):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("actual full-action failure after two candidate columns")
        return original(v, adjoint)

    action.apply = broken
    with pytest.raises(RuntimeError):
        s.add_block(np.eye(6, dtype=complex)[:, 2:4])
    assert s.m == previous[0]
    for x, y in zip((s.a, s.c, s.r), previous[1:], strict=True):
        np.testing.assert_array_equal(x, y)


def test_atomic_boundary_inverse_map_and_recovery(tmp_path):
    action = DenseAction(np.eye(6, dtype=complex), np.arange(1, 7))
    s = BlockWaveSubspace(action, 6)
    e = s.add_block(np.eye(6, dtype=complex)[:, :3])
    binding = dict(
        route="control",
        design_sha256="d",
        native_sha256="a",
        moments_sha256="m",
        source_sha="source",
    )
    store = BlockBasisStore(tmp_path, binding)
    rng = np.random.default_rng(4213001)
    model = dict(q=np.array([[0.3, 0.2, 0.1]]), patch=Patch((0, 0, 0), (1, 1, 1)))
    # The real runner publishes dataclass coordinates as tuples; reopening
    # JSON yields lists and must still retain the complete matching state.
    e.update(patch=asdict(model["patch"]), learned_q=model["q"].tolist())
    store.commit(s, model, 1, e, rng, 1e99)
    other = BlockWaveSubspace(action, 6)
    recovered = BlockBasisStore(tmp_path, binding).restore(
        other, np.random.default_rng(0)
    )
    assert recovered["columns"] == 3
    for key in ("a", "c", "r"):
        np.testing.assert_array_equal(getattr(other, key), getattr(s, key))
    bad = json.loads((tmp_path / "committed.json").read_text())
    bad["chunks"][0]["stop"] = 2
    (tmp_path / "committed.json").write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        BlockBasisStore(tmp_path, binding).restore(BlockWaveSubspace(action, 6), rng)


def test_complex128_compensation_cancellation():
    C = np.array([[1e16 + 1e16j, 1 + 2j, -1e16 - 1e16j]], np.complex128)
    assert compensated_columns(C, np.ones(3), batch=1)[0] == 1 + 2j


def test_invalid_true_residual_rolls_back_and_can_reselect():
    action = DenseAction(np.eye(4, dtype=complex), np.arange(1, 5))
    space = BlockWaveSubspace(action, 4)
    original = action.apply
    calls = 0

    def invalid_true_apply(v, adjoint=False):
        nonlocal calls
        calls += 1
        return original(v, adjoint) * (1 if calls <= 2 else -1)

    action.apply = invalid_true_apply
    event = space.add_block(np.eye(4, dtype=complex)[:, :2])
    assert not event["accepted"]
    assert event["reason"] == "SMALL_R_COMPLETE_ACTION_PAIR_REJECTED"
    assert space.m == 0
    np.testing.assert_array_equal(space.r, action.f)


def test_diagnostic_recovery_never_relaxes_new_block_acceptance():
    action = DenseAction(np.eye(4, dtype=complex), np.arange(1, 5))
    s = BlockWaveSubspace(action, 4)
    assert s.add_block(np.eye(4, dtype=complex)[:, :2])["accepted"]
    original = action.apply
    error = np.array([0, 0, 0, 1e-8], complex)
    action.apply = lambda v, adjoint=False: original(v, adjoint) + error
    with pytest.raises(ArithmeticError, match="SMALL_R_COMPLETE_ACTION_PAIR_REJECTED"):
        s.fit_retained_amplitudes()
    diagnostic = s.fit_retained_amplitudes(require_strict_pair=False)
    assert not diagnostic["small_full_action_pair_pass"]
    before = s.a.copy(), s.c.copy(), s.r.copy()
    event = s.add_block(np.eye(4, dtype=complex)[:, 2:3])
    assert not event["accepted"]
    for actual, expected in zip((s.a, s.c, s.r), before):
        np.testing.assert_array_equal(actual, expected)


def test_interrupted_block_publication_preserves_previous_complete_state(
    tmp_path, monkeypatch
):
    from src.solvers import neural_wave_block as module

    action = DenseAction(np.eye(6, dtype=complex), np.arange(1, 7))
    space = BlockWaveSubspace(action, 6)
    binding = dict(
        route="control",
        design_sha256="d",
        native_sha256="a",
        moments_sha256="m",
        source_sha="source",
    )
    store = BlockBasisStore(tmp_path, binding)
    rng = np.random.default_rng(4213001)
    model = dict(q=np.array([[0.3, 0.2, 0.1]]), patch=Patch((0, 0, 0), (1, 1, 1)))
    event = space.add_block(np.eye(6, dtype=complex)[:, :3])
    store.commit(space, model, 1, event, rng, 1e99)
    previous = (tmp_path / "committed.json").read_bytes()
    event = space.add_block(np.eye(6, dtype=complex)[:, 3:])
    original = module.atomic_json

    def interrupted(path, value):
        if path.name == "committed.json":
            raise OSError("injected interruption before atomic publication")
        original(path, value)

    monkeypatch.setattr(module, "atomic_json", interrupted)
    with pytest.raises(OSError):
        store.commit(space, model, 2, event, rng, 1e99)
    assert (tmp_path / "committed.json").read_bytes() == previous
    restored = BlockWaveSubspace(action, 6)
    BlockBasisStore(tmp_path, binding).restore(restored, rng)
    assert restored.m == 3
