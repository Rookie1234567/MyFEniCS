"""Independent decay maps/real adjoints, limits and actual atomic consumers."""

import ast
import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import linalg

from src.solvers.neural_wave_decay import (
    ComplexActivityMoments,
    block_parameters,
    coordinate_contract,
    decay_phase,
    physical_decay_seeds,
    support_distances,
)
from src.solvers.neural_wave_moments import Patch, WaveMoments
from src.test.test_neural_wave import tensor_fixture
from src.test.test_neural_wave_backfit import fixture


def test_saved_witness_gate_preserves_original_residual_denominator_and_rejects_damage():
    from src.solvers.neural_wave_decay_qualification import saved_witness_gate

    probe = dict(
        sign=1,
        independent_map=0.0,
        batch1_8=0.0,
        A_AH=0.0,
        original_MPC_expand_pullback=0.0,
        nonunit_original_Floquet_entries=3,
        quadrature_q30_q60=0.0,
        original_A_quadrature=0.0,
        full_VJP_FD_relative=0.0,
        families={
            k: dict(count=1, norm=1.0, full_map=0.0)
            for k in ("edge", "face", "interior")
        },
    )
    rows = [
        dict(
            block_id=i,
            kind="global" if i == 0 else "local",
            level=i - 1,
            actual_complete_trials=8,
            kappa_zero_regression=dict(columns=0.0),
            zero_pairs=dict(
                columns=0.0, c=2e-11, r=4.5e-10, r_original=7.1e-11, inserted_A=9.4e-11
            ),
            finite_differences=[
                dict(kind=k, relative_error=0.0)
                for k in ("q_only", "kappa_only", "mixed")
            ],
            decay_probes=[copy.deepcopy(probe), {**copy.deepcopy(probe), "sign": -1}],
            pass_all=False,  # a stored producer status does not decide the gate
        )
        for i in range(4)
    ]
    loop = dict(
        complete_trial_budget_not_exceeded=True,
        model_pair=1e-12,
        pair=dict(pair_relative=9e-11),
    )
    assert saved_witness_gate(rows, loop, True)
    for damage in ("original_residual", "nan", "interior", "duplicate", "gradient"):
        bad = copy.deepcopy(rows)
        if damage == "original_residual":
            bad[0]["zero_pairs"]["r_original"] = 1.01e-10
        elif damage == "nan":
            bad[0]["decay_probes"][0]["A_AH"] = float("nan")
        elif damage == "interior":
            bad[0]["decay_probes"][0]["families"]["interior"]["full_map"] = 1e-8
        elif damage == "duplicate":
            bad[1]["block_id"] = bad[0]["block_id"]
        else:
            bad[0]["finite_differences"][0]["relative_error"] = 1e-4
        assert not saved_witness_gate(bad, loop, True)
    assert not saved_witness_gate(rows, loop, False)


def independent(packet, patch, q, kappa, p):
    from src.solvers.neural_trace import moment_packet_values

    return moment_packet_values(
        packet,
        lambda x: patch.window(x)[:, None]
        * (np.exp((x - patch.center) @ (1j * q - kappa).T) @ p),
    )


@pytest.mark.parametrize(
    "kind,level", [("global", 0), ("local", 0), ("local", 1), ("local", 2)]
)
def test_all_moments_zero_and_decay_signs_and_three_real_derivatives(kind, level):
    rng, packet = tensor_fixture()
    patch = Patch((0.8, 0.5, 0.2), (2.0, 1.8, 1.5), level, kind)
    q = rng.normal(size=(2, 3))
    k = rng.normal(size=(2, 3)) * 0.14
    p = rng.normal(size=(2, 3)) + 1j * rng.normal(size=(2, 3))
    cot = rng.normal(size=288) + 1j * rng.normal(size=288)
    m, old = ComplexActivityMoments(packet, 8), WaveMoments(packet, 8)
    z0, z = np.c_[q, np.zeros_like(q)], np.c_[q, k]
    np.testing.assert_array_equal(m.columns(patch, z0), old.columns(patch, q))
    g0, p0 = m.vjp(patch, z0, p, cot)
    qo, po = old.vjp(patch, q, p, cot)
    np.testing.assert_allclose(g0[:, :3], qo, rtol=1e-12, atol=1e-12)
    np.testing.assert_array_equal(p0, po)
    for sign in (1, -1):
        trial = np.c_[q if sign == 1 else q * 0, sign * k]
        expected = independent(packet, patch, trial[:, :3], trial[:, 3:], p)
        np.testing.assert_allclose(
            m.columns(patch, trial) @ p.ravel(), expected, rtol=1e-10, atol=1e-10
        )
        np.testing.assert_array_equal(
            m.columns(patch, trial),
            ComplexActivityMoments(packet, 1).columns(patch, trial),
        )
    g, gp = m.vjp(patch, z, p, cot)
    for select in (slice(0, 3), slice(3, 6), slice(0, 6)):
        v = np.zeros_like(z)
        v[:, select] = rng.normal(size=v[:, select].shape)
        v /= np.linalg.norm(v)
        h = 1e-6
        dp, dm = (
            m.delta_columns(patch, z + h * v, z),
            m.delta_columns(patch, z - h * v, z),
        )
        fd = np.vdot(cot, (dp - dm) @ p.ravel()).real / (2 * h)
        exact = np.sum(g * v)
        assert abs(fd - exact) / max(abs(exact), 1e-14) <= 1e-5
    direction = rng.normal(size=p.shape) + 1j * rng.normal(size=p.shape)
    np.testing.assert_allclose(
        np.vdot(cot, m.columns(patch, z) @ direction.ravel()).real,
        np.vdot(gp, direction).real,
        rtol=1e-10,
        atol=1e-10,
    )


def test_support_true_global_extent_units_signed_seeds_and_exponent_limits():
    _, packet = tensor_fixture()
    m = ComplexActivityMoments(packet)
    block = dict(
        patch=Patch((0.8, 0.5, 0.2), (99.0, 99.0, 99.0), kind="global"),
        wave_q=np.ones((2, 3)),
    )
    R = support_distances(block["patch"], m)
    assert np.max(R) < 3 and np.all(R > 0)
    scale, bounds, _ = coordinate_contract(block, m, 2 * np.pi / 5)
    np.testing.assert_array_equal(scale[:, 3:], np.broadcast_to(1 / R, (2, 3)))
    assert bounds == ([(-4.0, 4.0)] * 3 + [(-8 / 3, 8 / 3)] * 3) * 2
    seeds, rec = physical_decay_seeds(block, m, 1, 0.2 + 10j)
    assert all(r["projected"] for r in rec)
    assert np.all(seeds[0][:, 5] > 0) and np.all(seeds[1][:, 5] < 0)
    d = np.array([[1.0, 1.0, 1.0], [1e12, 1e12, 1e12]])
    zeros = np.zeros((1, 3))
    value = decay_phase(d, np.array([1.0, 0.0]), zeros, np.array([[8 / 3] * 3]))
    assert value[1, 0] == 0  # exact zero support, not amplitude pruning
    with pytest.raises(ValueError, match="NO_CLIP"):
        decay_phase(d[:1], np.ones(1), zeros, np.array([[3.0, 3.0, 3.0]]))
    with pytest.raises(ValueError, match="NO_SILENT"):
        decay_phase(d[:1], np.ones(1), zeros.astype(complex) + 1j, zeros)


def test_decay_envelope_nonhermitian_against_independent_full_ls():
    from src.solvers.neural_wave_backfit import InactiveComplement

    action, U, Q, R = fixture(4213401)
    a0 = linalg.lstsq(action.A @ U, action.f, cond=1e-12)[0]
    F = InactiveComplement(action, U, Q, R, 2, 4, center=(a0, U @ a0))
    x = np.linspace(-1, 1, 14)

    def evaluate(kappa):
        C = U[:, 2:4] * np.exp(-x[:, None] * kappa)
        trial = F.solve_columns(np.array([[0, 0, 0, kappa, 0, 0]]), C, action.A @ C)
        matrix = U.copy()
        matrix[:, 2:4] = C
        amplitudes = linalg.lstsq(
            action.A @ matrix, action.f, cond=1e-12, lapack_driver="gelsd"
        )[0]
        np.testing.assert_allclose(trial.c, matrix @ amplitudes, rtol=1e-10, atol=1e-10)
        derivative = (
            -np.vdot(trial.r, action.apply(-x * (C @ trial.amplitudes[2:4]))).real
            / action.bnorm**2
        )
        return trial, derivative

    _, exact = evaluate(0.12)
    fd = (evaluate(0.120001)[0].objective - evaluate(0.119999)[0].objective) / 2e-6
    assert abs(fd - exact) / abs(exact) <= 1e-5


def test_actual_decay_writer_reopen_rollback_and_corrupted_consumer(
    tmp_path, monkeypatch
):
    from src.solvers.neural_wave_backfit import InactiveComplement
    from src.io.neural_wave_backfit_store import (
        BackfitStore,
        accept_and_save,
        check_boundary,
    )
    from src.solvers.neural_wave_greedy import atomic_npz, sha

    action, U, Q, R = fixture(4213401)
    a = linalg.lstsq(action.A @ U, action.f)[0]
    space = SimpleNamespace(
        action=action, U=U, Q=Q, R=R, a=a, c=U @ a, r=action.f - action.A @ U @ a, m=7
    )
    block = dict(
        start=0,
        stop=7,
        wave_q=np.zeros((3, 3)),
        decay_kappa=np.zeros((3, 3)),
        amplitude_map=np.ones((9, 7)),
        patch=Patch((0, 0, 0), (2, 2, 2)),
    )
    file = tmp_path / "anchor.npz"
    atomic_npz(
        file,
        u=U,
        wave_q=block["wave_q"],
        amplitude_map=block["amplitude_map"],
        center=np.zeros(3),
        radius=np.ones(3) * 2,
        patch_kind=np.array("local"),
    )
    anchor = dict(chunks=[dict(path=str(file), sha256=sha(file), start=0, stop=7)])
    store = BackfitStore(
        tmp_path,
        dict(source_sha="e" * 40, wave_representation="oscillation+decay.v1"),
        anchor,
    )
    state = dict(accepted=0, visits=0, boundary_count=0)
    store.save(space, [block], dict(kind="anchor", value=np.bool_(True)), state)
    check_boundary(tmp_path / "committed.json")
    F = InactiveComplement(action, U, Q, R, 0, 7)
    z = block_parameters(block)
    z[:, 5] = 0.1
    trial = F.solve_columns(z, U, action.A @ U)
    state.update(accepted=1, visits=1)
    accept_and_save(
        space, [block], 0, F, trial, store, dict(complex_event=1 + 2j), state
    )
    boundary = check_boundary(tmp_path / "committed.json")
    np.testing.assert_array_equal(block["decay_kappa"], z[:, 3:])
    entry = boundary["chunks"][0]
    with np.load(entry["path"]) as a:
        content = {k: np.array(a[k]) for k in a.files}
    content["decay_kappa"][0, 0] = np.nan
    atomic_npz(entry["path"], **content)
    entry["sha256"] = sha(entry["path"])
    (tmp_path / "committed.json").write_text(json.dumps(boundary))
    with pytest.raises(ValueError, match="PARAMETER_LAYOUT"):
        check_boundary(tmp_path / "committed.json")
    before = block["decay_kappa"].copy()
    monkeypatch.setattr(
        store, "save", lambda *a, **kw: (_ for _ in ()).throw(OSError("fsync"))
    )
    with pytest.raises(OSError):
        accept_and_save(space, [block], 0, F, trial, store, {}, state)
    np.testing.assert_array_equal(block["decay_kappa"], before)


def test_actual_nonzero_decay_network_reconstruction_and_complete_resume(tmp_path):
    from src.io.neural_wave_backfit_store import BackfitStore, accept_and_save
    from src.solvers.neural_wave_backfit import InactiveComplement
    from src.solvers.neural_wave_backfit_state import restore_backfit
    from src.solvers.neural_wave_block_reconstruction import (
        rebuild_stable,
        frozen_models,
    )
    from src.solvers.neural_wave_greedy import atomic_npz, sha
    from src.test.test_neural_wave_backfit import DenseAction

    rng, packet = tensor_fixture()
    patch = Patch((0.8, 0.5, 0.2), (2.0, 1.8, 1.5))
    q = rng.normal(size=(2, 3))
    z0 = np.c_[q, np.zeros_like(q)]
    z = np.c_[q, np.full_like(q, 0.12)]
    m = ComplexActivityMoments(packet)
    U = m.columns(patch, z0)
    C = m.columns(patch, z)
    matrix = np.diag(np.arange(1, 289) * (1 + 0.2j))
    f = matrix @ C @ (rng.normal(size=6) + 1j * rng.normal(size=6))
    action = DenseAction(matrix, f)
    Q, R = linalg.qr(matrix @ U, mode="economic")
    a = linalg.lstsq(matrix @ U, f, cond=1e-12)[0]
    space = SimpleNamespace(
        action=action, U=U.copy(), Q=Q, R=R, a=a, c=U @ a, r=f - matrix @ U @ a, m=6
    )
    block = dict(
        start=0,
        stop=6,
        wave_q=q.copy(),
        decay_kappa=np.zeros_like(q),
        amplitude_map=np.eye(6),
        patch=patch,
    )
    chunk = tmp_path / "anchor.npz"
    atomic_npz(
        chunk,
        u=U,
        wave_q=q,
        amplitude_map=np.eye(6),
        center=np.asarray(patch.center),
        radius=np.asarray(patch.radius),
        patch_kind=np.array(patch.kind),
    )
    anchor = dict(chunks=[dict(path=str(chunk), sha256=sha(chunk), start=0, stop=6)])
    binding = dict(
        source_sha="f" * 40,
        wave_representation="oscillation+decay.v1",
        route="PURE_FIXTURE",
        native_sha256="a" * 64,
        moments_sha256="b" * 64,
        design_sha256="c" * 64,
        anchor_sha256="d" * 64,
    )
    store = BackfitStore(tmp_path, binding, anchor)
    state = dict(accepted=0, visits=0, boundary_count=0)
    store.save(space, [block], dict(kind="zero_decay"), state)
    F = InactiveComplement(
        action, space.U, Q, R, 0, 6, center=(space.a, space.c), base_q=z0
    )
    trial = F.trial(m, patch, z, np.eye(6), gradient=True)
    state.update(accepted=1, visits=1)
    accept_and_save(
        space, [block], 0, F, trial, store, dict(kind="decay_accepted"), state
    )
    actual, producer, _ = rebuild_stable(tmp_path, packet)
    np.testing.assert_allclose(actual, producer, rtol=1e-10, atol=1e-10)
    with pytest.raises(ValueError, match="DECAY_AWARE"):
        frozen_models(tmp_path)
    # The complete boundary restores q/kappa, amplitudes and the exact QR
    # replay; the consumer never substitutes the stored producer field.
    space.Q, space.R = Q, R
    space.U[:] = U
    restored = restore_backfit(space, [block], tmp_path, binding)
    assert restored["committed"]
    np.testing.assert_array_equal(block["decay_kappa"], z[:, 3:])


def test_v34_stage_role_budget_and_actual_label_firewall():
    from src.io.neural_wave_campaign import ROOT, load_wave, profile_paths
    from src.io.complex_wave_campaign import DESIGN, STAGES, training_open_allowed
    from src.runners.neural_wave_campaign import stage_deadline

    design = json.loads(DESIGN.read_text())
    active = ROOT / "benchmarks/artifacts/task42extra/v34/v34_learned_complex_backfit"
    design["active_training_artifact"] = str(active)
    assert training_open_allowed(ROOT / design["files"]["native"]["path"], design)
    assert training_open_allowed(
        ROOT / design["anchor"]["bound_files"][1]["path"], design
    )
    for file in (
        active / "reference_state.npz",
        active / "teacher.pt",
        active.parent / "v34_complex_reconstruct/samples.npz",
        ROOT / "benchmarks/artifacts/task42extra/index_e3_reference.json",
    ):
        assert not training_open_allowed(file, design)
    for stage in STAGES:
        spec = load_wave(ROOT / f"input/task042extra_feinn_5nm/{stage}.dat")
        assert spec["campaign_version"] == 34
    assert profile_paths(dict(campaign_version=34))["reserve"] == 1800
    assert stage_deadline(
        dict(campaign_version=34, role="LEARNED_COMPLEX_WAVE_BACKFIT"),
        dict(deadline_monotonic=20000),
        dict(deadline_monotonic=50000),
    ) == (20000, 7200)
    tree = ast.parse((ROOT / "src/runners/neural_wave_campaign.py").read_text())
    expression = next(
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "hard" for t in n.targets)
    )
    for role in (
        "complex_wave_checks",
        "complex_wave_calibration",
        "complex_reconstruct",
        "LEARNED_COMPLEX_WAVE_BACKFIT",
    ):
        assert (
            eval(
                compile(ast.Expression(expression), "role", "eval"),
                {"__builtins__": {}},
                {"spec": dict(role=role)},
            )
            == 16 * 2**30
        )
    assert (
        eval(
            compile(ast.Expression(expression), "role", "eval"),
            {"__builtins__": {}},
            {"spec": dict(role="complex_compare")},
        )
        == 2 * 2**30
    )
