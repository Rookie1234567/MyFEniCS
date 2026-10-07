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
    assert event["reason"] == "SMALL_R_NUMERICAL_RANK_REJECTED"
    assert space.m == 0
    np.testing.assert_array_equal(space.r, action.f)


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
