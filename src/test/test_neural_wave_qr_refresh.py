"""Same-space original-action QR, rollback, and complete stored boundaries."""

import json
from time import monotonic

import numpy as np
import pytest
from scipy import linalg

from src.solvers.neural_wave_block import BlockWaveSubspace, BlockBasisStore
from src.solvers.neural_wave_moments import Patch
from src.solvers.neural_wave_qr_refresh import refresh_original_qr, repair_saved_readout


class Action:
    def __init__(self, matrix, load):
        self.A, self.f = matrix, load
        self.size, self.bnorm = len(load), float(np.linalg.norm(load))
        self.counts, self.costs = {"A": 0}, {"A": 0.0}

    def apply(self, v, adjoint=False):
        self.counts["A"] += 1
        return (self.A.conj().T if adjoint else self.A) @ v

    def audit(self, c):
        return {
            "native_relative": float(
                np.linalg.norm(self.f - self.apply(c)) / self.bnorm
            )
        }


@pytest.mark.parametrize("kind", ["complex", "scales", "correlated"])
def test_same_original_space_against_independent_svd(kind):
    rng = np.random.default_rng(4213203)
    a = Action(
        rng.normal(size=(12, 12)) + 1j * rng.normal(size=(12, 12)),
        rng.normal(size=12) + 1j * rng.normal(size=12),
    )
    C = rng.normal(size=(12, 5)) + 1j * rng.normal(size=(12, 5))
    if kind == "scales":
        C *= np.array([1e-8, 1e8, 1, 0.2, 5])
    if kind == "correlated":
        C[:, 4] = C[:, 0] + 1e-6 * C[:, 4]
    s = BlockWaveSubspace(a, 12)
    assert s.add_block(C)["accepted"]
    old_U = s.U[:, : s.m].copy()
    s.R[0, 0] += 1e-5  # An observed readout defect, not a changed operator.
    prior = [
        np.array(x, copy=True)
        for x in (s.Q[:, : s.m], s.R[: s.m, : s.m], s.a, s.c, s.r)
    ]
    try:
        result = refresh_original_qr(s, monotonic() + 600)
    except ArithmeticError as error:
        # A highly cancelling same-space refit may fail the unchanged physical
        # action gate. That is a retained negative outcome, never a forced pass.
        assert kind == "correlated"
        assert str(error) == "SMALL_R_COMPLETE_ACTION_PAIR_REJECTED"
        for x, y in zip(
            (s.Q[:, : s.m], s.R[: s.m, : s.m], s.a, s.c, s.r), prior, strict=True
        ):
            np.testing.assert_array_equal(x, y)
        np.testing.assert_array_equal(s.U[:, : s.m], old_U)
        return
    np.testing.assert_array_equal(old_U, s.U[:, : s.m])
    coeff = linalg.lstsq(a.A @ old_U, a.f, cond=1e-12, lapack_driver="gelsd")[0]
    np.testing.assert_allclose(s.c, old_U @ coeff, rtol=1e-8, atol=1e-9)
    assert result["qualified"] and result["unchanged_rcond"] == 1e-12
    assert result["fit"]["small_full_action_pair_relative"] < 1e-10


def test_invalid_actual_action_rolls_back_all_readout_arrays():
    a = Action(np.eye(6, dtype=complex), np.arange(1, 7, dtype=complex))
    s = BlockWaveSubspace(a, 6)
    assert s.add_block(np.eye(6, dtype=complex)[:, :3])["accepted"]
    old = [np.array(x, copy=True) for x in (s.Q[:, :3], s.R[:3, :3], s.a, s.c, s.r)]
    original = a.apply
    a.apply = lambda v: original(v) + np.ones(6) * 1e-6
    with pytest.raises(ArithmeticError):
        refresh_original_qr(s, monotonic() + 600)
    for x, y in zip((s.Q[:, :3], s.R[:3, :3], s.a, s.c, s.r), old, strict=True):
        np.testing.assert_array_equal(x, y)


def test_save_reserve_is_checked_before_original_action():
    a = Action(np.eye(6, dtype=complex), np.arange(1, 7, dtype=complex))
    s = BlockWaveSubspace(a, 6)
    s.add_block(np.eye(6, dtype=complex)[:, :3])
    count = a.counts["A"]
    with pytest.raises(TimeoutError):
        refresh_original_qr(s, monotonic() + 100)
    assert a.counts["A"] == count


def test_actual_atomic_writer_reopen_and_restore(tmp_path, monkeypatch):
    from src.solvers.neural_wave_greedy import sha

    a = Action(np.eye(6, dtype=complex), np.arange(1, 7, dtype=complex))
    s = BlockWaveSubspace(a, 6)
    e = s.add_block(np.eye(6, dtype=complex)[:, :3])
    binding = dict(
        route="CONTROL",
        source_sha="old",
        native_sha256="n",
        moments_sha256="m",
        design_sha256="d",
        route_origin_monotonic=monotonic(),
    )
    directory = tmp_path / "basis"
    store = BlockBasisStore(directory, binding)
    costs = dict(
        action_counts=a.counts,
        action_seconds=a.costs,
        qr_seconds=s.seconds,
        moment_counts={},
        moment_seconds={},
        projection_reuse={},
    )
    old = store.commit(
        s,
        dict(q=np.array([[0.3, 0.2, 0.1]]), patch=Patch((0, 0, 0), (1, 1, 1))),
        1,
        e,
        np.random.default_rng(4213201),
        monotonic() + 14400,
        dict(cost_state=costs),
    )
    old_hashes = {z["path"]: sha(directory / z["path"]) for z in old["chunks"]}

    # Pure storage fixture: real M5 pointwise mapping is qualified separately.
    def toy_rebuild(path, packet, marker):
        b = json.loads((path / "committed.json").read_text())
        with np.load(path / b["state"]["path"]) as z:
            amp, saved = z["a"], z["c"]
        cols = []
        for ent in b["chunks"]:
            with np.load(path / ent["path"]) as z:
                cols.append(z["u"])
        return np.column_stack(cols) @ amp, saved, b

    monkeypatch.setattr(
        "src.solvers.neural_wave_qr_refresh.rebuild_stable", toy_rebuild
    )
    artifact = tmp_path / "art"
    artifact.mkdir()
    result = repair_saved_readout(
        a,
        {},
        {"strategy": {"route_seconds": 14400}},
        directory,
        artifact,
        "new",
        "d",
        monotonic() + 600,
        lambda *_: None,
    )
    assert result["qualified"] and not result["current_boundary_unchanged"]
    assert all(sha(directory / p) == h for p, h in old_hashes.items())
    new = BlockWaveSubspace(a, 4096)
    loaded = BlockBasisStore(directory, dict(binding, source_sha="new")).restore(
        new, np.random.default_rng(0)
    )
    assert loaded["binding"]["source_sha"] == "new" and loaded["columns"] == 3
    assert new.retained_readout_pair_relative() < 1e-10
    np.testing.assert_allclose(new.c, s.c, rtol=1e-12, atol=1e-12)


def test_filtered_repair_receipt_allowed_but_labels_rejected():
    from src.io.neural_wave_campaign import ROOT, training_open_allowed

    design = json.loads(
        (ROOT / "input/task042extra_feinn_5nm/design_v32.json").read_text()
    )
    base = ROOT / "benchmarks/artifacts/task42extra/v32"
    design["active_training_artifact"] = str(base / "v32_fixed_multiscale_wave")
    assert training_open_allowed(
        base / "v32_fixed_original_qr_checks/result.json", design
    )
    assert not training_open_allowed(
        base / "v32_fixed_original_qr_checks/trial_qr/x.npz", design
    )
    assert not training_open_allowed(
        base / "v32_fixed_multiscale_wave/basis/reference_state.npz", design
    )


def test_real_readout_stage_has_numeric_cap_while_pure_checker_keeps_light_cap():
    import ast
    from src.io.neural_wave_campaign import ROOT

    tree = ast.parse((ROOT / "src/runners/neural_wave_campaign.py").read_text())
    assignment = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "hard" for t in n.targets)
    )
    expression = compile(ast.Expression(assignment.value), "actual-stage-cap", "eval")
    assert (
        eval(
            expression,
            {"__builtins__": {}},
            {"spec": {"role": "readout_repair_checks"}},
        )
        == 16 * 2**30
    )
    assert (
        eval(expression, {"__builtins__": {}}, {"spec": {"role": "multiscale_compare"}})
        == 2 * 2**30
    )
