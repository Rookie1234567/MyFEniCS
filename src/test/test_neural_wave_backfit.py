"""Independent complete complex LS, envelope derivatives, and transactions."""

from types import SimpleNamespace

import numpy as np
import pytest
from scipy import linalg

from src.solvers.neural_wave_backfit import (
    InactiveComplement,
    insert_block_qr,
    optimize_active,
    select_active_round,
)
from src.solvers.neural_wave_moments import Patch


class DenseAction:
    def __init__(self, A, f):
        self.A, self.f = A, f
        self.size = len(f)
        self.bnorm = float(np.linalg.norm(f))

    def apply(self, c, adjoint=False):
        return (self.A.conj().T if adjoint else self.A) @ c


def test_complete_complex_cancellation_including_active_slot():
    from src.solvers.neural_wave_backfit import compensated_mixed_columns

    U = np.array([[1e16 + 1e16j, 1 + 2j, -1e16 - 1e16j]], complex)
    amplitude = np.ones(3, complex)
    np.testing.assert_array_equal(
        compensated_mixed_columns(U, amplitude), np.array([1 + 2j])
    )
    np.testing.assert_array_equal(
        compensated_mixed_columns(U, amplitude, 1, 2, np.array([[3 + 4j]])),
        np.array([3 + 4j]),
    )


@pytest.mark.parametrize("kind", ["local", "global"])
def test_stable_phase_difference_all_entity_moments_and_derivative(kind):
    from src.test.test_neural_wave import tensor_fixture, direct
    from src.solvers.neural_wave_moments import WaveMoments

    rng, packet = tensor_fixture()
    patch = Patch((0.8, 0.5, 0.2), (2.0, 1.8, 1.5), kind=kind)
    q = rng.normal(size=(2, 3))
    p = rng.normal(size=(2, 3)) + 1j * rng.normal(size=(2, 3))
    v = rng.normal(size=q.shape)
    cotangent = rng.normal(size=288) + 1j * rng.normal(size=288)
    m = WaveMoments(packet, 8)
    np.testing.assert_array_equal(m.delta_columns(patch, q, q), np.zeros((288, 6)))
    h = 1e-6
    dp = m.delta_columns(patch, q + h * v, q)
    dm = m.delta_columns(patch, q - h * v, q)
    np.testing.assert_allclose(
        dp, WaveMoments(packet, 1).delta_columns(patch, q + h * v, q), rtol=0, atol=0
    )
    np.testing.assert_allclose(
        m.forward(patch, q, p) + dp @ p.ravel(),
        direct(packet, patch, q + h * v, p),
        rtol=1e-10,
        atol=1e-10,
    )
    fd = np.vdot(cotangent, (dp - dm) @ p.ravel()).real / (2 * h)
    g, _ = m.vjp(patch, q, p, cotangent)
    assert abs(fd - np.sum(g * v)) / max(abs(fd), 1e-14) <= 1e-5


def fixture(seed=4213301):
    rng = np.random.default_rng(seed)
    A = rng.normal(size=(14, 14)) + 1j * rng.normal(size=(14, 14))
    U = rng.normal(size=(14, 7)) + 1j * rng.normal(size=(14, 7))
    f = rng.normal(size=14) + 1j * rng.normal(size=14)
    action = DenseAction(A, f)
    Q, R = linalg.qr(A @ U, mode="economic")
    return action, U, Q, R


@pytest.mark.parametrize("first,last", [(0, 2), (3, 5), (5, 7)])
@pytest.mark.parametrize("kind", ["complex", "permuted", "scaled", "duplicate"])
def test_deleted_complement_full_ls_and_insert(first, last, kind):
    action, U, Q, R = fixture()
    if kind == "permuted":
        U = U[:, [5, 0, 2, 6, 1, 4, 3]]
    if kind == "scaled":
        U = U * np.array([1e-3, 1e3, 1, 0.02, 3, 2, 1])
    if kind == "duplicate":
        U[:, last - 1] = U[:, first]
    Q, R = linalg.qr(action.A @ U, mode="economic")
    F = InactiveComplement(action, U, Q, R, first, last)
    C = U[:, first:last].copy()
    if kind != "duplicate":
        C += np.arange(14)[:, None] * (0.002 + 0.001j)
    trial = F.solve_columns(np.zeros((1, 3)), C, action.A @ C)
    allU = U.copy()
    allU[:, first:last] = C
    a = linalg.lstsq(action.A @ allU, action.f, cond=1e-12, lapack_driver="gelsd")[0]
    np.testing.assert_allclose(trial.c, allU @ a, rtol=1e-10, atol=1e-10)
    np.testing.assert_allclose(
        trial.r, action.f - action.A @ allU @ a, rtol=1e-10, atol=1e-10
    )
    if kind != "duplicate":
        q, r = insert_block_qr(F, action.A @ C)
        assert (
            np.linalg.norm(q @ r - action.A @ allU) / np.linalg.norm(action.A @ allU)
            < 1e-10
        )
    BF = action.A @ U[:, F.indices]
    qf, rf = linalg.qr(BF, mode="economic")
    assert np.linalg.norm(F.Q @ F.R - BF) / np.linalg.norm(BF) < 1e-10
    # Direct rank-revealing SVD, including the duplicate case's inactive span.
    left, s, _ = linalg.svd(BF, full_matrices=False)
    left = left[:, s > s[0] * 1e-12]
    z = action.f - left @ (left.conj().T @ action.f)
    assert np.linalg.norm(F.r_F - z) / action.bnorm < 1e-10


def test_full_Q_is_an_explicit_negative_control():
    action, U, Q, R = fixture()
    F = InactiveComplement(action, U, Q, R, 0, 2)
    old = action.A @ U[:, :2]
    wrong = old - Q @ (Q.conj().T @ old)
    assert np.linalg.norm(wrong) < 1e-12 * np.linalg.norm(old)
    assert np.linalg.norm(F.project(old)) > 0.1


def test_nonzero_complex_envelope_derivative_and_k0_chain():
    action, U, Q, R = fixture()
    F = InactiveComplement(action, U, Q, R, 2, 4)
    x = np.linspace(-1, 1, 14)
    raw = U[:, 2:4]
    q = 0.7

    def evaluate(q):
        C = raw * np.exp(1j * x[:, None] * q)
        t = F.solve_columns(np.full((1, 3), q), C, action.A @ C)
        dc = 1j * x * (C @ t.amplitudes[2:4])
        g = -np.vdot(t.r, action.apply(dc)).real / action.bnorm**2
        return t, g

    t, g = evaluate(q)
    assert abs(g) > 1e-5
    for h in (1e-4, 1e-5, 1e-6):
        fd = (evaluate(q + h)[0].objective - evaluate(q - h)[0].objective) / (2 * h)
        assert abs(fd - g) / abs(g) < 1e-5
    k0 = 2 * np.pi / 0.7
    fd = (
        evaluate(q + k0 * 1e-6)[0].objective - evaluate(q - k0 * 1e-6)[0].objective
    ) / 2e-6
    assert abs(fd - k0 * g) / abs(k0 * g) < 1e-5


def test_centered_full_ls_and_stable_original_loss_difference():
    action, U, Q, R = fixture()
    a0 = linalg.lstsq(action.A @ U, action.f, cond=1e-12)[0]
    c0 = U @ a0
    F = InactiveComplement(action, U, Q, R, 2, 4, center=(a0, c0))
    zero = F.solve_columns(np.zeros((1, 3)), U[:, 2:4], action.A @ U[:, 2:4])
    np.testing.assert_allclose(zero.c, c0, atol=1e-12, rtol=1e-12)
    h = 1e-5
    x = np.arange(14)[:, None]
    trials = []
    for sign in (1, -1):
        C = U[:, 2:4] * np.exp(sign * 1j * h * x)
        t = F.solve_columns(np.zeros((1, 3)), C, action.A @ C)
        allU = U.copy()
        allU[:, 2:4] = C
        a = linalg.lstsq(action.A @ allU, action.f, cond=1e-12)[0]
        np.testing.assert_allclose(t.c, allU @ a, atol=1e-10, rtol=1e-10)
        trials.append(t)
    plus, minus = trials
    stable = -np.vdot(
        plus.r + minus.r, action.apply(plus.centered_change - minus.centered_change)
    ).real / (4 * h * action.bnorm**2)
    naive = (plus.objective - minus.objective) / (2 * h)
    np.testing.assert_allclose(stable, naive, rtol=1e-8, atol=1e-10)


def test_trial_calls_are_actually_guarded_and_no_result_replay():
    count = []

    def evaluate(q, gradient):
        count.append(1)
        return SimpleNamespace(
            q=q.copy(),
            objective=float(np.sum(q * q)),
            gradient=2 * q if gradient else None,
            active_rank=2,
            pairing=0.0,
        )

    q0 = np.ones((3, 3))
    seed = evaluate(q0, True)
    for route in ("learned", "deterministic"):
        count.clear()
        best, rec = optimize_active(
            evaluate,
            q0,
            1,
            route,
            round_id=0,
            block_id=2,
            visit_id=0,
            max_evaluations=3,
            seed_trial=seed,
        )
        assert len(count) == rec["complete_trial_calls"] <= 3
        assert rec["extra_result_evaluations"] == 0 and best.objective <= seed.objective


def test_queue_uses_scores_and_persistent_all_scale_rotation():
    blocks = [
        dict(patch=Patch((0, 0, 0), (1, 1, 1), i % 3, "global" if i == 0 else "local"))
        for i in range(30)
    ]
    cursor = 0
    seen = set()
    for _ in range(10):
        selected, cursor = select_active_round(list(range(30)), blocks, cursor)
        assert len(selected) == len(set(selected)) == 16
        assert selected[:8] == list(range(29, 21, -1))
        seen.update(selected)
    assert len(seen) == 30


def test_complete_state_rolls_back_when_real_writer_fails(tmp_path, monkeypatch):
    from src.io.neural_wave_backfit_store import BackfitStore, accept_and_save

    action, U, Q, R = fixture()
    a = linalg.lstsq(action.A @ U, action.f)[0]
    space = SimpleNamespace(
        action=action, U=U, Q=Q, R=R, a=a, c=U @ a, r=action.f - action.A @ U @ a, m=7
    )
    block = dict(
        start=2,
        stop=4,
        wave_q=np.zeros((1, 3)),
        amplitude_map=np.ones((3, 2)),
        patch=Patch((0, 0, 0), (1, 1, 1)),
    )
    F = InactiveComplement(action, U, Q, R, 2, 4)
    trial = F.solve_columns(block["wave_q"], U[:, 2:4], action.A @ U[:, 2:4])
    old = [
        np.array(getattr(space, k), copy=True) for k in ("U", "Q", "R", "a", "c", "r")
    ]
    store = BackfitStore(tmp_path, {}, dict(chunks=[]))
    monkeypatch.setattr(
        store, "save", lambda *a, **k: (_ for _ in ()).throw(OSError("fsync"))
    )
    with pytest.raises(OSError):
        accept_and_save(
            space, [block], 0, F, trial, store, {}, dict(accepted=1, visits=1)
        )
    for k, x in zip(("U", "Q", "R", "a", "c", "r"), old, strict=True):
        np.testing.assert_array_equal(getattr(space, k), x)


def test_numeric_roles_and_new_clock_do_not_use_old_light_or_wait_cap():
    import ast
    from src.io.neural_wave_campaign import ROOT, profile_paths
    from src.runners.neural_wave_campaign import stage_deadline

    tree = ast.parse((ROOT / "src/runners/neural_wave_campaign.py").read_text())
    expression = next(
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "hard" for t in n.targets)
    )
    code = compile(ast.Expression(expression), "actual-role-cap", "eval")
    for role in (
        "backfit_anchor_checks",
        "backfit_math_checks",
        "LEARNED_VARPRO_BACKFIT",
    ):
        assert eval(code, {"__builtins__": {}}, {"spec": {"role": role}}) == 16 * 2**30
    assert (
        eval(code, {"__builtins__": {}}, {"spec": {"role": "backfit_compare"}})
        == 2 * 2**30
    )
    assert profile_paths({"campaign_version": 33})["reserve"] == 1800
    assert stage_deadline(
        dict(campaign_version=33, role="LEARNED_VARPRO_BACKFIT"),
        dict(deadline_monotonic=12000),
        dict(deadline_monotonic=50000),
    ) == (12000, 5400)


@pytest.mark.parametrize("wavelength", [5.0, 0.7])
def test_wave_component_bound_uses_actual_wavelength(wavelength):
    from src.solvers.neural_wave_multiscale import clip_wave_q

    k0 = 2 * np.pi / wavelength
    value = np.array([-8, -4, -3, 0, 3, 4, 8]) * k0
    np.testing.assert_array_equal(
        clip_wave_q(value, k0), np.clip(value, -4 * k0, 4 * k0)
    )
    if wavelength == 5:
        np.testing.assert_array_equal(
            clip_wave_q(value, k0), np.clip(value, -8 * np.pi / 5, 8 * np.pi / 5)
        )


def test_training_actual_whitelist_rejects_hidden_reference_and_other_route():
    import json
    from src.io.backfit_wave_campaign import training_open_allowed
    from src.io.neural_wave_campaign import ROOT, load_wave

    design = json.loads(
        (ROOT / "input/task042extra_feinn_5nm/design_v33.json").read_text()
    )
    active = ROOT / "benchmarks/artifacts/task42extra/v33/v33_learned_varpro_backfit"
    design["active_training_artifact"] = str(active)
    assert training_open_allowed(ROOT / design["files"]["native"]["path"], design)
    assert training_open_allowed(
        ROOT / design["anchor"]["bound_files"][1]["path"], design
    )
    assert not training_open_allowed(
        ROOT / "benchmarks/artifacts/task42extra/index_e3_reference.json", design
    )
    assert not training_open_allowed(active / "basis/reference_state.npz", design)
    assert not training_open_allowed(
        active.parent / "v33_backfit_reconstruct/a.npz", design
    )
    assert not training_open_allowed(
        active.parent / "v33_deterministic_backfit/basis/a.npz", design
    )
    assert (
        load_wave(ROOT / "input/task042extra_feinn_5nm/v33_learned_varpro_backfit.dat")[
            "campaign_version"
        ]
        == 33
    )


def test_real_writer_reopen_exact_qr_restore_and_corrupt_state(tmp_path, monkeypatch):
    import json
    from src.io.neural_wave_backfit_store import (
        BackfitStore,
        accept_and_save,
        check_boundary,
    )
    from src.solvers.neural_wave_backfit_state import restore_backfit
    from src.solvers.neural_wave_greedy import atomic_npz, atomic_json, sha

    action, U, Q, R = fixture()
    amp = linalg.lstsq(action.A @ U, action.f, cond=1e-12)[0]
    space = SimpleNamespace(
        action=action,
        m=7,
        U=U.copy(),
        Q=Q,
        R=R,
        a=amp,
        c=U @ amp,
        r=action.f - action.A @ U @ amp,
    )
    binding = dict(
        route="CONTROL",
        native_sha256="n",
        moments_sha256="m",
        design_sha256="d",
        anchor_sha256="s",
        source_sha="source",
    )
    blocks = []
    chunks = []
    for i, (first, last) in enumerate(((0, 2), (2, 5), (5, 7))):
        block = dict(
            start=first,
            stop=last,
            wave_q=np.zeros((1, 3)),
            amplitude_map=np.ones((3, last - first)),
            patch=Patch((0, 0, 0), (1, 1, 1)),
        )
        file = tmp_path / f"original_{i}.npz"
        atomic_npz(
            file,
            u=U[:, first:last],
            q=Q[:, first:last],
            R_columns=R[:last, first:last],
            wave_q=block["wave_q"],
            amplitude_map=block["amplitude_map"],
            center=np.zeros(3),
            radius=np.ones(3),
            patch_level=np.asarray(0),
            patch_kind=np.asarray("local"),
        )
        blocks.append(block)
        chunks.append(dict(path=str(file), start=first, stop=last, sha256=sha(file)))
    directory = tmp_path / "basis"
    store = BackfitStore(directory, binding, dict(chunks=chunks))
    state = dict(accepted=0, visits=0, boundary_count=0)
    store.save(space, blocks, dict(value=1 + 2j, boolean=np.bool_(True)), state)
    old = sha(directory / "committed.json")
    F = InactiveComplement(action, space.U, space.Q, space.R, 2, 5)
    trial = F.solve_columns(np.ones((1, 3)) * 0.1, U[:, 2:5], action.A @ U[:, 2:5])
    state.update(accepted=1, visits=1)

    # Actual writer failure after array fsync, before publishing the boundary.
    def fail_publish(path, value):
        if path.name == "committed.json":
            raise OSError("publish interruption")
        return atomic_json(path, value)

    monkeypatch.setattr("src.io.neural_wave_backfit_store.atomic_json", fail_publish)
    with pytest.raises(OSError):
        accept_and_save(space, blocks, 1, F, trial, store, {}, state)
    assert sha(directory / "committed.json") == old
    np.testing.assert_array_equal(space.U, U)
    monkeypatch.setattr("src.io.neural_wave_backfit_store.atomic_json", atomic_json)
    accept_and_save(space, blocks, 1, F, trial, store, dict(value=1 + 2j), state)
    final = check_boundary(directory / "committed.json")
    restored = SimpleNamespace(action=action, m=7, U=U.copy(), Q=Q.copy(), R=R.copy())
    copied = [dict(b, wave_q=np.zeros((1, 3))) for b in blocks]
    restore_backfit(restored, copied, directory, binding)
    for k in ("U", "Q", "R", "a", "c", "r"):
        np.testing.assert_allclose(
            getattr(restored, k), getattr(space, k), rtol=1e-10, atol=1e-10
        )
    saved = __import__("pathlib").Path(final["state"]["path"])
    saved.write_bytes(saved.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="MATCHED_STATE_HASH"):
        check_boundary(directory / "committed.json")
    parsed = json.loads((directory / "previous_committed.json").read_text())
    assert parsed["event"]["boolean"] is True


@pytest.mark.parametrize("damage", [None, "c", "chunks", "rng_state", "node", "hash"])
def test_scored_boundary_survives_only_exact_timed_metadata_update(tmp_path, damage):
    import json
    from src.solvers.neural_wave_backfit_run import validate_scalar_boundary
    from src.solvers.neural_wave_greedy import atomic_json, atomic_npz, sha

    arrays = dict(a=np.array([1 + 2j]), c=np.array([3 + 4j]),
                  r=np.array([5 + 6j]), R=np.array([[7 + 8j]]))
    old_state = tmp_path / "old.npz"
    new_state = tmp_path / "new.npz"
    atomic_npz(old_state, **arrays)
    if damage == "c":
        arrays["c"] = arrays["c"] + 1e-14
    atomic_npz(new_state, **arrays)
    algorithm = dict(visits=16, accepted=13, trials=458, nonzero_q_updates=13,
                     queue=[], cursor=16, round_id=1, rng_state={"state": 42},
                     validated_nodes=[])
    old = dict(binding={"source": "source", "native": "native"},
               chunks=[{"sha256": "model"}], qr_replay=[], columns=1377,
               iteration=16, algorithm_state=algorithm,
               state=dict(path=str(old_state), sha256=sha(old_state)),
               event=dict(kind="scalar_validation_boundary", node=1))
    previous = tmp_path / "previous_committed.json"
    atomic_json(previous, old)
    scalar = dict(boundary_sha256=sha(previous), node=1)
    now = json.loads(json.dumps(old))
    now["event"] = dict(kind="fixed_time_node", seconds=3600)
    now["state"] = dict(path=str(new_state), sha256=sha(new_state))
    # Time and paid action work may advance; optimization/model arrays may not.
    now["algorithm_state"]["remaining_seconds"] = 100
    if damage == "chunks":
        now["chunks"][0]["sha256"] = "different model"
    elif damage == "rng_state":
        now["algorithm_state"]["rng_state"]["state"] = 43
    elif damage == "node":
        scalar["node"] = 2
    elif damage == "hash":
        scalar["boundary_sha256"] = "not a saved scored boundary"
    current = tmp_path / "committed.json"
    atomic_json(current, now)
    events = []
    if damage is None:
        validate_scalar_boundary(scalar, current, lambda *v: events.append(v))
        assert events[0][1]["a_c_r_R_bitwise_equal"] is True
        assert sha(previous) == scalar["boundary_sha256"]
    else:
        with pytest.raises(ValueError, match="VALIDATION_"):
            validate_scalar_boundary(scalar, current, lambda *v: events.append(v))
        assert not events


def test_qualification_reuse_is_bound_to_every_actual_mathematical_dependency():
    from src.runners import backfit_wave_worker as worker

    receipt = dict(implementation_qualified=True, bound_numerical_chain={
        p: worker.digest(worker.ROOT / p) for p in worker.CHAIN
    })
    assert worker.receipt_matches(receipt, "implementation_qualified")
    for path in worker.MATHEMATICS_CHAIN:
        old = receipt["bound_numerical_chain"][path]
        receipt["bound_numerical_chain"][path] = "modified numerical source"
        assert not worker.receipt_matches(receipt, "implementation_qualified")
        receipt["bound_numerical_chain"][path] = old
    receipt["implementation_qualified"] = False
    assert not worker.receipt_matches(receipt, "implementation_qualified")
