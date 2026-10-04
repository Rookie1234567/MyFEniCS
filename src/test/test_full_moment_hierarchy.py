"""Small complete-channel/transaction/live-guard tests; never reads real A or e."""

import json
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from scipy.sparse import eye

from benchmarks.check_full_moment import require_inventory
from src.solvers.full_moment_hierarchy import BucketLayout, FullMomentCorrector
from src.solvers.neighborhood_residual_models import parameters_hash


def fixture():
    keys, sizes = [], []
    for d, directions, m in ((1, range(3), 6), (2, range(3), 60), (3, [3], 450)):
        for direction in directions:
            for i in (0, 1, 4):
                keys.append((d, direction, i, 0, 0))
                sizes.append(m)
    graph = {
        "keys": np.array(keys),
        "sizes": np.array(sizes),
        "offsets": np.r_[0, np.cumsum(sizes)],
    }
    n = sum(sizes)
    return graph, eye(n, dtype=complex, format="csr"), np.ones(n, dtype=complex)


def test_exact_full_inventory_count_weighted_parents_and_real_transposes():
    graph, b, d = fixture()
    model = FullMomentCorrector(b, graph, d, seed=3)
    assert model.real_parameters == 1817040
    layout = model.layout
    assert sum(layout.levels[0]["counts"].ravel()) == len(graph["keys"])
    rng = np.random.default_rng(19)
    for g, m in enumerate(layout.moments):
        a = torch.from_numpy(rng.normal(size=(2, len(layout.indices[g]), 2 * m)))
        for lev, row in enumerate(layout.levels):
            v = torch.from_numpy(rng.normal(size=(2, len(row["keys"]), 2 * m)))
            assert torch.allclose(
                (model.aggregate(a, g, lev) * v).sum(),
                (a * model.aggregate_transpose(v, g, lev)).sum(),
                atol=1e-10,
            )
            assert torch.allclose(
                (model.broadcast(v, g, lev) * a).sum(),
                (v * model.broadcast_transpose(a, g, lev)).sum(),
                atol=1e-10,
            )
        mean = model.aggregate(a, g, 0).numpy()[0]
        parent = layout.parents[0]
        weights = layout.levels[0]["counts"][:, g]
        sums = np.zeros((len(layout.levels[1]["keys"]), 2 * m))
        np.add.at(sums, parent, mean * weights[:, None])
        counts = layout.levels[1]["counts"][:, g]
        expected = sums / np.where(counts == 0, 1, counts)[:, None]
        assert np.allclose(expected, model.aggregate(a, g, 1).numpy()[0])
    bad = dict(graph, offsets=graph["offsets"] + np.arange(len(graph["offsets"])))
    with pytest.raises(ValueError, match="moment ordering"):
        BucketLayout(bad)


def test_three_identical_initializations_full_channel_identity_and_zero_bypass():
    graph, b, d = fixture()
    values = torch.randn(2, b.shape[0], dtype=torch.complex128)
    hashes = []
    for code in ("NH", "NL", "LH"):
        model = FullMomentCorrector(
            b, graph, d, seed=5, linear=code == "LH", local=code == "NL"
        )
        hashes.append(parameters_hash(model))
        assert torch.count_nonzero(model(values)) == 0
        assert torch.count_nonzero(model(torch.zeros_like(values))) == 0
    assert len(set(hashes)) == 1
    model = FullMomentCorrector(b, graph, d, seed=5, linear=True)
    with torch.no_grad():
        for en, de, c in zip(model.encoder, model.decoder, model.mix_context):
            en.weight.copy_(torch.eye(en.weight.shape[0]))
            de.weight.copy_(torch.eye(de.weight.shape[0]))
            c.zero_()
        for p in model.message.parameters():
            p.zero_()
    assert torch.allclose(model(values), values, atol=1e-12, rtol=1e-12)
    assert model.decoder[-1].weight.shape == (900, 900)


def test_fixed_gamma_remote_content_and_deployed_real_linearity():
    graph, b, d = fixture()
    v = torch.zeros(1, b.shape[0], dtype=torch.complex128)
    src = len(graph["sizes"]) - 3
    target = src + 2
    v[:, graph["offsets"][src] : graph["offsets"][src + 1]] = 0.2 + 0.1j
    for code in ("NH", "NL", "LH"):
        model = FullMomentCorrector(
            b,
            graph,
            d,
            seed=17,
            linear=code == "LH",
            local=code == "NL",
            zero_decoder=False,
        )
        with torch.no_grad():
            out = model.canonical(v, fixed_gamma=1.0)[
                :, graph["offsets"][target] : graph["offsets"][target + 1]
            ]
        assert (
            float(torch.linalg.vector_norm(out)) == 0
            if code == "NL"
            else float(torch.linalg.vector_norm(out)) > 1e-12
        )
    a = torch.randn_like(v)
    z = torch.randn_like(v)
    model = FullMomentCorrector(b, graph, d, seed=17, linear=True, zero_decoder=False)
    with torch.no_grad():
        assert torch.allclose(
            model(0.3 * a - 0.7 * z),
            0.3 * model(a) - 0.7 * model(z),
            atol=1e-12,
            rtol=1e-12,
        )


def test_nonzero_remote_parameter_gradient_full_channel_finite_difference():
    graph, b, d = fixture()
    model = FullMomentCorrector(b, graph, d, seed=23, zero_decoder=False)
    x = torch.randn(2, b.shape[0], dtype=torch.complex128)
    target = torch.randn_like(x)
    loss = torch.mean(torch.abs(model(x) - target) ** 2)
    loss.backward()
    p = model.message[0].weight
    direction = torch.randn_like(p)
    direction /= torch.linalg.vector_norm(direction)
    derivative = float((p.grad * direction).sum())
    base = p.detach().clone()
    vals = []
    for sign in (1, -1):
        with torch.no_grad():
            p.copy_(base + sign * 1e-5 * direction)
        vals.append(float(torch.mean(torch.abs(model(x) - target) ** 2).detach()))
    assert abs((vals[0] - vals[1]) / 2e-5 - derivative) < 1e-8
    assert abs(derivative) > 0


def test_late_adam_boundary_restores_consistent_state_and_rejects_parameter_only(
    tmp_path,
):
    from src.solvers.neighborhood_residual_study import save_model
    from src.solvers.neighborhood_training_transaction import restore_complete

    model = torch.nn.Linear(2, 2, dtype=torch.float64, bias=False)
    opt = torch.optim.Adam(model.parameters())
    for _ in range(64):
        opt.zero_grad()
        model(torch.ones(1, 2, dtype=torch.float64)).square().sum().backward()
        opt.step()
    receipt = save_model(tmp_path, "late", model, opt, {"update": 64})
    record = {
        "checkpoint": receipt,
        "completed_update": 64,
        "last_parameter_hash": parameters_hash(model),
    }
    restored = torch.nn.Linear(2, 2, dtype=torch.float64, bias=False)
    op = torch.optim.Adam(restored.parameters())
    assert restore_complete(restored, op, record, maximum=128) == 64
    for m, o in ((model, opt), (restored, op)):
        o.zero_grad()
        m(torch.ones(1, 2, dtype=torch.float64)).square().sum().backward()
        o.step()
    assert parameters_hash(model) == parameters_hash(restored)
    parameter_only = save_model(tmp_path, "invalid", model, None, {"update": 65})
    with pytest.raises(ValueError, match="parameters alone"):
        restore_complete(
            restored,
            op,
            {
                "checkpoint": parameter_only,
                "completed_update": 65,
                "last_parameter_hash": parameters_hash(model),
            },
            maximum=128,
        )


def test_complete_new_five_route_inventory_and_old_closed_window_untouched():
    rows = [
        {"sample": i, "split": "heldout", "route": r}
        for i in range(8)
        for r in ("R0", "CL44", "LIN-H", "NN-L", "NN-H")
    ]
    assert require_inventory(rows)
    for bad in (
        rows[:-1],
        rows[:-1] + [rows[0]],
        [dict(r, route="NN-E") for r in rows],
    ):
        with pytest.raises(ValueError):
            require_inventory(bad)
    from src.solvers.full_moment_scope import window

    assert window.label == "V45" and str(window.TMP).endswith("/v45")


def test_actual_scoped_execute_dispatch_uses_instance_handler(monkeypatch, tmp_path):
    from src.solvers import neighborhood_residual_models
    from src.solvers.neighborhood_pilot_workflow import LateErrorStudy

    campaign = SimpleNamespace(label="fixture", guard_worker_parent=lambda: None)
    ctx = SimpleNamespace(
        window=campaign,
        ActionBudget=lambda p: SimpleNamespace(counts={"completed": {"actions": 0}}),
        implementation_hashes=lambda: {"fixture": "test"},
    )
    study = LateErrorStudy(ctx)
    monkeypatch.setattr(neighborhood_residual_models, "configure_threads", lambda: None)
    monkeypatch.setenv("TASK042_V36_AUX_DIRECTORY", str(tmp_path))
    called = []

    def handler(folder, budget):
        called.append(folder)
        return {"status": "fixture_ready"}

    study.setup = handler
    result = study.execute("SETUP", tmp_path, {})
    assert called == [tmp_path] and result["status"] == "fixture_ready"


def test_real_new_dat_registration_live_limits_and_wrong_plan_rejected(
    monkeypatch, tmp_path
):
    from src.io.port_preparation import load_preparation
    from src.runners.port_preparation import PreparationHealth, storage_limits
    from src.solvers import full_moment_scope as scope

    limits = storage_limits("v45")
    assert limits["task_storage_bytes"] == 24 * 2**30
    for p in (scope.ROOT / "input/task042_neural_coarse_inverse").glob("v45_*.dat"):
        spec = load_preparation(p)
        assert spec.derived["preparation_scope"] == "v45"
        assert dict(spec.derived["storage_limits"]) == limits
    health = PreparationHealth(tmp_path, [], "v45", limits=limits)
    assert health.shared.artifact_limit_bytes == 24 * 2**30
    with pytest.raises(ValueError, match="identical frozen plan"):
        PreparationHealth(
            tmp_path, [], "v45", limits=dict(limits, task_storage_bytes=20 * 2**30)
        )
    plan = json.loads(scope.PLAN.read_text())
    plan["task_storage_bytes"] = 20 * 2**30
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps(plan))
    monkeypatch.setattr(scope, "PLAN", path)
    with pytest.raises(ValueError, match="immutable storage"):
        scope.plan_record()


def test_shared_workflow_real_end_to_end_pipeline_without_forming_new_action(
    tmp_path, monkeypatch
):
    from scipy.sparse import csr_matrix

    from src.solvers import neighborhood_pilot_workflow as workflow
    from src.solvers.full_moment_study import FullMomentStudy
    from src.solvers.neighborhood_residual_core import OriginalCSR

    graph = {
        "sizes": np.array([6, 60, 450]),
        "offsets": np.array([0, 6, 66, 516]),
        "shape": np.array([516, 516]),
        "independent": np.arange(516),
        "slaves": np.array([], int),
    }
    a = csr_matrix(np.eye(516) * (2 + 0.3j))
    a += csr_matrix(
        (np.full(515, 0.7 + 0.2j), (np.arange(515), np.arange(1, 516))), shape=a.shape
    )
    original = OriginalCSR(
        {"data": a.data, "indices": a.indices, "indptr": a.indptr, "shape": a.shape}
    )
    records = {"SETUP": {"passed": True}, "GRADIENT": {"passed": True}}
    plan = {
        "split": {
            s: {"seeds": list(range(n, n + c)), "families": ["local", "cross"]}
            for s, n, c in [("train", 1, 16), ("validation", 20, 4), ("heldout", 30, 8)]
        }
    }
    scope = SimpleNamespace(
        window=SimpleNamespace(label="synthetic"),
        stage=lambda n: (records[n], None),
        plan_record=lambda: plan,
    )

    class Tiny(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.decoder = torch.nn.Linear(2, 2, bias=False, dtype=torch.float64)
            with torch.no_grad():
                self.decoder.weight.zero_()
            self.real_parameters = 4
            self.activation_records = []
            self.record_activations = False

        def forward(self, x):
            if x.ndim == 1:
                x = x[None, :]
            part = self.decoder(torch.stack((x.real, x.imag), dim=-1))
            return torch.complex(part[..., 0], part[..., 1])

    class Synthetic(FullMomentStudy):
        def graph_packet(self):
            return eye(516, format="csr", dtype=complex), graph, {}

        def load_action(self, budget):
            original.load_seconds = 0.0
            return original

        def model_for(self, code, action, **kwargs):
            return Tiny()

        def commit_update(self, *args):
            pass

        def frozen_models(self):
            return {c: records["TRAIN_LH"] for c in ("LH", "NL", "NH", "CL44")}

    study = Synthetic(scope)
    # The real shared DATA/Adam/evaluate/CHECK workflows run; the only mock is a
    # deterministic small manufacturing family, with no access to real labels.
    monkeypatch.setattr(
        workflow,
        "manufactured",
        lambda graph, family, seed: (
            np.random.default_rng(seed).normal(size=516)
            + 1j * np.random.default_rng(seed + 100).normal(size=516)
        ),
    )

    def folder(name):
        p = tmp_path / name
        p.mkdir()
        return p

    records["DATA"] = study.data(folder("data"), None)
    assert records["DATA"]["passed"]
    records["TRAIN_LH"] = study.train(folder("train"), None, "LH")
    assert records["TRAIN_LH"]["training_updates"] == 128
    for code in study.routes:
        records["EVAL_" + code] = study.evaluate(folder("eval_" + code), None, code)
    result = study.check(folder("check"), None)
    assert result["frozen_count"] == 40 and len(result["rows"]) == 40
    assert all(row["saved_residual_identity"]["passed"] for row in result["rows"])
    assert set(result["full_pass_by_route"]) == {"R0", "CL44", "LIN-H", "NN-L", "NN-H"}
