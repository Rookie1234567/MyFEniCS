"""Independent finite sums and full-state/cache negative controls."""

from copy import deepcopy
from itertools import product
import numpy as np
import pytest
import torch
from src.solvers.ftt_field import FTTField
from src.solvers.ftt_moments import StreamingMomentMap
from src.solvers.ftt_factored_moments import (
    FactoredMomentMap,
    core_product,
    core_product_adjoint,
)
from src.solvers.optimization_checkpoint import capture, restore, optimizer_step

BOX = [[-2, 2], [-2, 2], [-2, 2]]


def fixture(permuted=False, skew=False):
    nodes, w = np.polynomial.legendre.leggauss(4)
    nodes = (nodes + 1) / 2
    w = w / 2
    ids = np.array(list(product(range(4), repeat=3)))
    pts = nodes[ids]
    weights = np.prod(w[ids], axis=1)
    interpolation = np.zeros((3, 3, len(pts)))
    interpolation[0, 0] = weights * (1 + pts[:, 0] + pts[:, 1] * pts[:, 2])
    interpolation[1, 1] = weights * (pts[:, 0] ** 2 - 0.3 * pts[:, 2])
    interpolation[2, 2] = weights * (1 + pts[:, 1] ** 2)
    interpolation[0, 2] = 1e-20 * weights  # a small nonzero is not a structural zero
    J = np.diag([0.7, 1.1, 0.9])
    if permuted:
        J = np.roll(J, 1, axis=0)
    if skew:
        J[0, 1] += 0.2
    return dict(
        active_rows=np.array(6),
        owner_rows=np.arange(6).reshape(2, 3),
        reference_points=pts,
        interpolation=interpolation.reshape(3, -1),
        origins=np.array([[-0.8, -0.7, -0.5], [0.1, 0.2, 0.3]]),
        jacobians=np.tile(J, (2, 1, 1)),
        transforms=np.array(
            [np.eye(3), np.diag(np.exp(1j * np.array([0.3, -0.7, 0.4])))]
        ),
        orientation_ids=np.array([0, 1]),
    )


@pytest.mark.parametrize("kind", ["fttnn", "chebtt"])
@pytest.mark.parametrize("geometry", ["box", "permuted", "skew"])
def test_complete_finite_sum_real_adjoint_and_fallback(kind, geometry):
    p = fixture(geometry == "permuted", geometry == "skew")
    model = FTTField(BOX, kind)
    model.nonzero_qualification_state()
    old = StreamingMomentMap(p, 128)
    new = FactoredMomentMap(p, 512)
    dual = np.arange(1, 7).astype(complex) * (0.7 + 0.2j)
    np.testing.assert_allclose(
        new.forward(model, 8), old.forward(model, 1), rtol=1e-12, atol=1e-14
    )
    np.testing.assert_allclose(
        new.vjp(model, dual, 8), old.vjp(model, dual, 1), rtol=1e-11, atol=1e-13
    )
    if geometry == "skew":
        assert all(not r["aligned"] for r in new.geometry_records)
    else:
        assert max(r["relative"] for r in new.interpolation_errors) <= 1e-12
    # The tiny component survives polynomial recovery (no magnitude mask).
    if geometry != "skew":
        assert np.any(new.plans[0]["coefficients"][:, 2] != 0)


def test_noncommuting_complex_chain_direction_and_wrong_conjugate():
    rng = np.random.default_rng(4213901)
    shapes = [(2, 3, 1, 8), (3, 3, 8, 8), (2, 3, 8, 1)]
    cores = [rng.normal(size=s) + 1j * rng.normal(size=s) for s in shapes]
    direction = [rng.normal(size=s) + 1j * rng.normal(size=s) for s in shapes]
    dual = rng.normal(size=(2, 3, 2, 3)) + 1j * rng.normal(size=(2, 3, 2, 3))
    gs = core_product_adjoint(cores, dual)
    exact = sum(np.vdot(g, d).real for g, d in zip(gs, direction))
    h = 1e-6
    observed = (
        np.vdot(dual, core_product([c + h * d for c, d in zip(cores, direction)])).real
        - np.vdot(
            dual, core_product([c - h * d for c, d in zip(cores, direction)])
        ).real
    ) / (2 * h)
    assert abs(observed - exact) / abs(exact) < 1e-8
    wrong = sum(np.sum(g * d).real for g, d in zip(gs, direction))
    assert abs(wrong - exact) > 1e-3


def test_cache_parameter_buffer_trial_restore_and_scatter_repeated_nodes():
    p = fixture()
    p["origins"][1] = p["origins"][0]
    model = FTTField(BOX, "fttnn")
    model.nonzero_qualification_state()
    mapping = FactoredMomentMap(p)
    old = StreamingMomentMap(p)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    snap = capture(model, optimizer, {})
    c = mapping.forward(model)
    dual = np.ones(6, dtype=complex) * (1 + 0.8j)
    np.testing.assert_allclose(
        mapping.vjp(model, dual), old.vjp(model, dual), rtol=1e-11, atol=1e-13
    )
    key = mapping.cache_key
    with torch.no_grad():
        model.cores[2][-1].bias.add_(0.01)
    assert not np.allclose(c, mapping.forward(model))
    assert mapping.cache_key != key
    restore(model, optimizer, snap)
    np.testing.assert_allclose(mapping.forward(model), c, rtol=0, atol=0)
    assert mapping.cache_key == key
    with torch.no_grad():
        model.center[0].add_(0.02)
    mapping.forward(model)
    assert mapping.cache_key != key
    restore(model, optimizer, snap)
    mapping.forward(model)
    before = deepcopy(model.state_dict())

    def failing():
        with torch.no_grad():
            model.cores[2][-1].bias.add_(0.01)
        mapping.forward(model)
        raise RuntimeError("trial interrupted")

    with pytest.raises(RuntimeError):
        optimizer_step(model, optimizer, failing, lambda _: None)
    assert all(torch.equal(before[k], model.state_dict()[k]) for k in before)
    np.testing.assert_allclose(mapping.forward(model), c, rtol=0, atol=0)


def test_structure_schema_isolation_and_parent_binding():
    from src.io.ftt_structure_campaign import STAGES, parent, DESIGN
    from src.io.neural_wave_campaign import ROOT, load_wave, profile_paths
    import json

    for name in STAGES:
        spec = load_wave(ROOT / "input/task042extra_feinn_5nm" / (name + ".dat"))
        assert (
            spec["campaign_version"] == 39 and profile_paths(spec)["root"].name == "v39"
        )
    d = json.loads(DESIGN.read_text())
    bad = deepcopy(d)
    bad["parents"]["fttnn_native"]["checkpoint"]["sha256"] = "0" * 64
    with pytest.raises(ValueError):
        parent(bad, "fttnn", False)


def test_v39_admission_never_spends_expired_v30_observation_pool(monkeypatch):
    from src.io.neural_wave_campaign import ROOT
    from src.runners import block_wave_admission, neural_wave_dependencies

    calls = []
    expected = {"cpu": 17, "fresh_sample": True}

    def approved(directory, hard, *, scope=None, prefix="admission"):
        calls.append((directory, hard, scope, prefix))
        return expected

    def expired_pool(*_):
        pytest.fail("V39 must not consult the exhausted V30 observation pool")

    monkeypatch.setattr(block_wave_admission, "fresh_admission", approved)
    monkeypatch.setattr(neural_wave_dependencies, "resource_observation_cost", expired_pool)
    directory = ROOT / "tmp/task42extra/v39/durable/checks_attempt2"
    result = neural_wave_dependencies.fresh_admission(
        directory, 16 * 2**30, scope={17, 18}, prefix="outer", reserve_s=64
    )
    assert result is expected
    assert calls == [(directory, 16 * 2**30, {17, 18}, "outer")]
    assert block_wave_admission.pool(directory).parent.name == "v39"
    assert block_wave_admission.wait_limit(directory) == 900


def test_inherited_full_Adam_to_fresh_LBFGS_budget_and_atomic_state(tmp_path):
    from src.solvers.ftt_optimization import make_metric, run_training
    from src.solvers.optimization_checkpoint import load_checkpoint
    from time import monotonic

    class Action:
        f = np.ones(6, dtype=np.complex128)
        counts = {"A": 0, "AH": 0}
        costs = {"A": 0.0, "AH": 0.0}

        def apply(self, c, adjoint=False):
            self.counts["AH" if adjoint else "A"] += 1
            return c.copy()

        def audit(self, c):
            r = float(np.linalg.norm(c - self.f) / np.linalg.norm(self.f))
            return dict(
                native_relative=r,
                augmented_relative=r,
                original_total_augmented_relative=r,
            )

    action = Action()
    packet = fixture()
    model = FTTField(BOX, "fttnn")
    mapping = FactoredMomentMap(packet)
    metric = make_metric(action, "native_euc")
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    c = mapping.forward(model)
    _, _, dual = metric.value(c, gradient=True)
    mapping.vjp(model, dual)
    opt.step()
    c = mapping.forward(model)
    binding = dict(
        source_sha="c" * 40,
        input_sha256="d" * 64,
        design_sha256="e" * 64,
        native_sha256="a" * 64,
        moments_sha256="b" * 64,
        reference_sha256=None,
        model_kind="fttnn",
        metric_kind="native_euc",
        reference_used_for_training=False,
        production_initialization_allowed=False,
    )
    counts = dict(
        attempted_calls=1,
        complete_loss_gradient_calls=1,
        committed_steps=1,
        Adam_updates=1,
        LBFGS_outer_steps=0,
        native_audits=0,
    )
    state = capture(model, opt, dict(binding, counts=counts, phase="Adam"))
    state.update(c=c, r=c - action.f)
    candidate = dict(binding, checkpoint=dict(sha256="f" * 64, optimizer_class="Adam"))
    outcome = run_training(
        action,
        packet,
        model,
        metric,
        tmp_path,
        binding,
        monotonic() + 30,
        lambda *_: None,
        call_limit=4,
        adam_steps=2,
        mapping=mapping,
        resume_state=state,
        resume_identity=candidate,
    )
    assert outcome["inherited_counts"]["Adam_updates"] == 1
    assert outcome["counts"]["Adam_updates"] == 2
    assert outcome["counts"]["attempted_calls"] == 4
    frozen = load_checkpoint(
        tmp_path / "checkpoints" / outcome["checkpoint"]["name"],
        outcome["checkpoint"]["sha256"],
    )
    assert (
        frozen["optimizer_class"] == "LBFGS" and frozen["metadata"]["phase"] == "L-BFGS"
    )
    np.testing.assert_allclose(frozen["c"], mapping.forward(model), rtol=0, atol=0)
    assert outcome["resume_pairing"]["c_relative"] == 0
    assert outcome["stop_reason"] == "CALL_LIMIT"


def test_structural_float64_and_original_timebase_do_not_reset():
    from src.runners.neural_wave_campaign import stage_deadline, worker_stop_time

    model = FTTField(BOX, "fttnn")
    model.float()
    with pytest.raises(ValueError, match="FLOAT64"):
        FactoredMomentMap(fixture()).forward(model)
    spec = dict(campaign_version=39, role="ftt_train")
    end, reserve = stage_deadline(
        spec, dict(deadline_monotonic=10000.0), dict(deadline_monotonic=11000.0)
    )
    assert end == 9200 and reserve == 1800
    assert worker_stop_time(spec, end) == end - 150


def test_full_constraint_chain_has_two_nonunit_phases_once():
    from src.solvers.feinn_native import FullNativePacket

    model = FTTField(BOX, "fttnn")
    model.nonzero_qualification_state()
    mapping = FactoredMomentMap(fixture())
    c = mapping.forward(model)
    px, py = np.exp(0.73j), np.exp(-0.41j)
    C = np.vstack(
        [np.eye(6), np.eye(6)[0] * px, np.eye(6)[1] * py, np.eye(6)[2] * px * py]
    )
    action = FullNativePacket.__new__(FullNativePacket)
    action.size, action.nc, action.dim = 6, 3, 3
    action.a = dict(
        erows=np.arange(9),
        eids=np.array([0, 1, 2, 3, 4, 5, 0, 1, 2]),
        evals=np.array([1, 1, 1, 1, 1, 1, px, py, px * py]),
    )
    expanded = action.expand(c).ravel()
    np.testing.assert_allclose(expanded, C @ c, rtol=1e-13, atol=1e-14)
    d = (np.arange(9) + 1j * np.arange(9, 0, -1)).reshape(3, 3)
    pulled = action.pullback(d)
    np.testing.assert_allclose(pulled, C.conj().T @ d.ravel(), rtol=1e-13)
    assert not np.allclose(pulled, C.T @ d.ravel())
    np.testing.assert_allclose(
        mapping.vjp(model, pulled),
        StreamingMomentMap(fixture()).vjp(model, pulled),
        rtol=1e-11,
        atol=1e-13,
    )
