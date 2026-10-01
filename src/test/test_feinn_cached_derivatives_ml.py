"""Independent complex-chain, transactional cache, and GN frontier witnesses."""

from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from src.solvers.damped_gauss_newton import DampedGNState, damped_cg
from src.solvers.feinn_cached_derivatives import CachedMomentJacobian
from src.solvers.feinn_parameter_jvp import MomentJacobian
from src.solvers.feinn_phase import PhaseCoordinateField
from src.solvers.feinn_torch import CompleteMomentMap
from src.solvers.feinn_validation import parameters, assign
from src.solvers.optimization_checkpoint import (
    capture,
    restore,
    CheckpointStore,
    load_checkpoint,
)
from src.solvers.feinn_gn_training import GNProblem

torch.set_num_threads(1)
if torch.get_num_interop_threads() != 1:
    torch.set_num_interop_threads(1)


def fixture():
    rng = np.random.default_rng(4211001)
    nc, nq, dim = 9, 5, 4
    rows = np.arange(nc * dim).reshape(nc, dim)
    rows[0, 0] = -1
    rows[rows >= 0] -= 1
    return CompleteMomentMap(
        dict(
            active_rows=np.asarray(nc * dim - 1),
            reference_points=rng.uniform(size=(nq, 3)),
            interpolation=rng.normal(size=(dim, 3 * nq)),
            transforms=np.array([np.eye(dim), np.diag([1, -1, 1j, np.exp(0.3j)])]),
            jacobians=rng.normal(size=(nc, 3, 3)),
            origins=rng.normal(size=(nc, 3)),
            orientation_ids=np.arange(nc) % 2,
            owner_rows=rows,
        )
    )


def model():
    m = PhaseCoordinateField([[-5, 5], [-3.75, 3.75], [-1.25, 8.75]])
    rng = np.random.default_rng(4211002)
    assign(m, parameters(m) + 0.03 * rng.normal(size=8966))
    return m


def test_complex_complete_chain_real_adjoint_batch_and_invalidation(tmp_path):
    m, mapping = model(), fixture()
    cached, old = CachedMomentJacobian(mapping), MomentJacobian(mapping)
    p = parameters(m)
    rng = np.random.default_rng(4211003)
    np.testing.assert_allclose(
        cached.forward(m), mapping.forward(m), rtol=1e-12, atol=1e-12
    )
    for kind in ("hidden", "last", "random"):
        v = rng.normal(size=8966)
        if kind == "hidden":
            v[-390:] = 0
        if kind == "last":
            v[:-390] = 0
        w = 1j * rng.normal(size=mapping.size)
        j, g = cached.jvp(m, v), cached.vjp(m, w)
        np.testing.assert_allclose(j, old.jvp(m, v), rtol=1e-11, atol=1e-11)
        np.testing.assert_allclose(g, old.vjp(m, w), rtol=1e-11, atol=1e-11)
        np.testing.assert_allclose(j, cached.jvp(m, v, 1), rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(g, cached.vjp(m, w, 1), rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(np.vdot(w, j).real, v @ g, rtol=1e-12, atol=1e-12)
    key, version = cached.key, cached.version
    assign(m, p + 1e-3 * v)
    mapping.forward(m)
    assign(m, p)
    cached.ensure(m)
    assert cached.key == key and cached.version == version
    assign(m, p + 1e-3 * v)
    cached.ensure(m)
    assert cached.key != key
    assign(m, p)
    cached.ensure(m)
    m.center.add_(0.1)
    cached.ensure(m)
    assert cached.key != key
    m.center.sub_(0.1)
    cached.ensure(m)
    opt = DampedGNState(2)
    state = capture(m, opt, {})
    store = CheckpointStore(tmp_path)
    record = store.save(state)
    assign(m, p + 0.2 * v)
    cached.ensure(m)
    loaded = load_checkpoint(tmp_path / record["name"], record["sha256"])
    restore(m, opt, loaded)
    np.testing.assert_allclose(
        cached.forward(m), mapping.forward(m), rtol=1e-12, atol=1e-12
    )
    tiny = CachedMomentJacobian(mapping, cache_limit=cached.static_bytes + 1)
    with pytest.raises(ValueError, match="BEFORE_ALLOCATION"):
        tiny.ensure(m)


def test_nonhermitian_gn_curvature_gradient_three_updates_and_rejections():
    mapping = fixture()
    m = model()
    rng = np.random.default_rng(4211004)
    A = rng.normal(size=(mapping.size, mapping.size)) + 1j * rng.normal(
        size=(mapping.size, mapping.size)
    )
    f = rng.normal(size=mapping.size) + 1j * rng.normal(size=mapping.size)
    packet = SimpleNamespace(
        apply=lambda c, adjoint=False: (A.conj().T if adjoint else A) @ c
    )

    class Metric:
        denominator = float(np.vdot(f, f).real)
        gram = SimpleNamespace(solve=lambda c: c)

        def value(self, c, gradient=False):
            r = A @ c - f
            loss = float(np.vdot(r, r).real / (2 * self.denominator))
            return (
                (loss, r, A.conj().T @ r / self.denominator) if gradient else (loss, r)
            )

    metrics = Metric()
    old = GNProblem(m, mapping, packet, metrics, supervised=False)
    new = GNProblem(m, mapping, packet, metrics, supervised=False)
    new.jac = CachedMomentJacobian(mapping)
    p = parameters(m)
    v = rng.normal(size=8966)
    np.testing.assert_allclose(old.K(v), new.K(v), rtol=1e-11, atol=1e-10)
    paths = []
    for problem in (old, new):
        assign(m, p)
        opt = DampedGNState(1000)
        trace = []
        for _ in range(3):
            theta = parameters(m)
            loss, g, _ = problem.value_gradient()
            first = True

            def evaluate(x, restore_only=False):
                nonlocal first
                result = problem.value(x, restore_only)
                if not restore_only and first:
                    first = False
                    return np.inf
                return result

            accepted, row = opt.propose(
                theta, loss, g, problem.K, evaluate, trace.append
            )
            assert accepted is not None
            assign(m, accepted)
        assert any(not row.get("accepted", True) for row in trace)
        paths.append(parameters(m))
    np.testing.assert_allclose(paths[0], paths[1], rtol=1e-8, atol=1e-9)


class Frontier:
    stop_exception = RuntimeError

    def __init__(self, max_k=100):
        self.max_k = max_k
        self.events = []

    def allow(self, *, K=0, trial=0):
        return K <= self.max_k

    def event(self, kind, phase, **facts):
        self.events.append((kind, phase))


def test_budget_defers_pc_but_commits_verified_direction_and_early_cg():
    rng = np.random.default_rng(4211005)
    d = np.logspace(0, 6, 100)
    g = rng.normal(size=100)
    opt = DampedGNState(10)
    opt.slow_streak = 2
    opt.accepted = 5
    theta = np.zeros(100)
    rows = []
    budget = Frontier(3)

    def evaluate(x, restore_only=False):
        return None if restore_only else float(g @ x + 0.5 * x @ (d * x))

    value, row = opt.propose(
        theta, 0, g, lambda x: d * x, evaluate, rows.append, budget=budget
    )
    assert (
        value is not None and row["g_dot_s"] < 0 and row["pred"] > 0 and row["ared"] > 0
    )
    assert any(r["kind"] == "PC_DEFERRED_BY_BUDGET" for r in rows)
    assert len(opt.pc_builds) == 0

    class Early(Frontier):
        def allow(self, **kw):
            return calls[0] < 2

    calls = [0]

    def K(v):
        calls[0] += 1
        return d * v

    s, cg = damped_cg(K, g, 1, budget=Early())
    assert cg["budget_frontier_early"] and cg["finite"]
    np.testing.assert_allclose(
        cg["true_relative"], np.linalg.norm(-g - d * s - s) / np.linalg.norm(g)
    )


def test_pc_interruption_keeps_old_basis_and_matching_atomic_state(tmp_path):
    rng = np.random.default_rng(9)
    d = np.logspace(0, 6, 100)
    g = rng.normal(size=100)
    opt = DampedGNState(10)
    opt.slow_streak = 2
    opt.accepted = 5
    old = deepcopy(opt.state_dict())
    phase = {"pc": False}
    budget = Frontier()

    def event(kind, state, **facts):
        if kind == "PC_K_OMEGA" and state == "begin":
            phase["pc"] = True

    budget.event = event

    def K(v):
        if phase["pc"]:
            raise RuntimeError("actual PC interruption")
        return d * v

    with pytest.raises(RuntimeError, match="actual PC"):
        opt.propose(np.zeros(100), 0, g, K, lambda *_: 0, budget=budget)
    assert (
        opt.V is old["V"]
        and opt.lam is old["lam"]
        and opt.pc_builds == old["pc_builds"]
    )
