"""Small opt-in tests; actual M5 qualifications are a separate one-run stage."""

from copy import deepcopy
import numpy as np
import pytest
import torch

from src.solvers.ftt_field import FTTField
from src.solvers.ftt_moments import StreamingMomentMap
from src.solvers.feinn_torch import CompleteMomentMap
from src.solvers.ftt_optimization import make_metric
from src.solvers.optimization_checkpoint import (
    capture,
    restore,
    optimizer_step,
    atomic_write,
    load_checkpoint,
    digest,
)

BOX = [[-1.0, 1.0], [-1.0, 1.0], [-1.0, 1.0]]


@pytest.mark.parametrize("kind,n", [("fttnn", 9072), ("chebtt", 9120)])
def test_complex_chain_and_zero(kind, n):
    model = FTTField(BOX, kind)
    x = torch.randn(11, 3, dtype=torch.float64)
    assert sum(p.numel() for p in model.parameters()) == n
    assert torch.count_nonzero(model(x)) == 0
    model.nonzero_qualification_state()
    a, b, c = [model.core(i, x[:, i]) for i in range(3)]
    independent = torch.stack(
        [a[j, s] @ b[j, s] @ c[j, s] for j in range(11) for s in range(3)]
    ).reshape(11, 3)
    torch.testing.assert_close(model(x), independent, rtol=1e-13, atol=1e-13)
    assert not torch.allclose(
        model(x), torch.einsum("nsij,nskj,nskl->nsil", a, b, c)[:, :, 0, 0]
    )
    assert not torch.allclose(model(x), model(x).conj())


def fixture():
    rng = np.random.default_rng(42)
    return dict(
        active_rows=np.array(9),
        owner_rows=np.array([[0, 1, 2], [3, 4, 5], [6, 7, 8]]),
        reference_points=rng.normal(size=(17, 3)),
        origins=rng.normal(size=(3, 3)),
        jacobians=np.tile(np.diag([0.7, 1.1, 0.9]), (3, 1, 1)),
        interpolation=rng.normal(size=(3, 51)) + 1j * rng.normal(size=(3, 51)),
        transforms=np.array(
            [np.eye(3), np.diag(np.exp(1j * np.array([0.31, -0.73, 0.62])))]
        ),
        orientation_ids=np.array([0, 1, 1]),
    )


@pytest.mark.parametrize("kind", ["fttnn", "chebtt"])
def test_streaming_map_real_adjoint(kind):
    model = FTTField(BOX, kind)
    model.nonzero_qualification_state()
    packet = fixture()
    small = StreamingMomentMap(packet, 128)
    old = CompleteMomentMap(packet)
    np.testing.assert_allclose(
        small.forward(model, 1), old.forward(model, 1), rtol=1e-11, atol=1e-11
    )
    d = np.linspace(0.1, 0.9, 9).astype(np.complex128) * (1 + 0.3j)
    np.testing.assert_allclose(
        small.vjp(model, d), old.vjp(model, d, 1), rtol=1e-10, atol=1e-8
    )


def test_native_explicit_metric_forbids_reference_or_gram():
    class Action:
        f = np.array([1 + 1j], dtype=np.complex128)

        def apply(self, c, adjoint=False):
            return (2 - 1j if adjoint else 2 + 1j) * c

    metric = make_metric(Action(), "native_euc")
    assert metric.gram is None
    assert metric.value(np.zeros(1, dtype=np.complex128))[0] == 0.5
    for key in ("G", "reference"):
        with pytest.raises(ValueError):
            make_metric(Action(), "native_euc", **{key: np.ones(1)})


@pytest.mark.parametrize("opt", ["Adam", "LBFGS"])
def test_actual_optimizer_transaction_and_atomic_reopen(tmp_path, opt):
    model = FTTField(BOX, "fttnn")
    optimizer = (
        torch.optim.Adam(model.parameters(), lr=1e-3)
        if opt == "Adam"
        else torch.optim.LBFGS(
            model.parameters(), line_search_fn="strong_wolfe", max_iter=2
        )
    )
    x = torch.tensor([[0.1, 0.2, 0.3]], dtype=torch.float64)
    before = capture(model, optimizer, {"test": True})

    def closure():
        optimizer.zero_grad()
        loss = abs(model(x) - (0.5 + 0.2j)).square().sum()
        loss.backward()
        return loss

    def persist(update):
        state = capture(model, optimizer, update)
        path = tmp_path / "state.pt"
        atomic_write(path, lambda f: torch.save(state, f))
        loaded = load_checkpoint(path, digest(path))
        restore(model, optimizer, loaded)
        return update

    _, update = optimizer_step(model, optimizer, closure, persist)
    assert update["accepted_update_norm"] > 0
    saved = deepcopy(model.state_dict())
    calls = 0

    def failing():
        nonlocal calls
        calls += 1
        loss = closure()
        if calls >= 2 or opt == "Adam":
            raise RuntimeError("actual trial exception")
        return loss

    with pytest.raises(RuntimeError):
        optimizer_step(model, optimizer, failing, persist)
    for key, value in saved.items():
        assert torch.equal(model.state_dict()[key], value)
    restore(model, optimizer, before)


def test_atomic_interrupt_keeps_previous(tmp_path):
    p = tmp_path / "a"
    atomic_write(p, lambda f: f.write(b"old"))

    def abort(_):
        raise RuntimeError("incomplete replacement")

    with pytest.raises(RuntimeError):
        atomic_write(p, lambda f: f.write(b"new"), before_replace=abort)
    assert p.read_bytes() == b"old"


def test_label_and_old_model_file_isolation(tmp_path):
    from src.io.neural_wave_campaign import ROOT
    from src.runners.ftt_worker import training_allowed

    design = dict(
        files={
            "native": dict(path="benchmarks/artifacts/task42extra/original/native.npz")
        },
        reference=dict(
            path="benchmarks/artifacts/task42extra/original/reference_state.npz"
        ),
        gram=dict(path="benchmarks/artifacts/task42extra/original/gram.npz"),
    )
    active = ROOT / "benchmarks/artifacts/task42extra/v38/v38_fttnn_native"
    assert training_allowed(
        ROOT / design["files"]["native"]["path"], design, active, False
    )
    assert not training_allowed(
        ROOT / design["reference"]["path"], design, active, False
    )
    assert not training_allowed(ROOT / design["gram"]["path"], design, active, False)
    assert not training_allowed(
        ROOT / "benchmarks/artifacts/task42extra/v36/old.pt", design, active, False
    )
    assert training_allowed(active / "checkpoints/new.pt", design, active, False)
    assert training_allowed(ROOT / design["reference"]["path"], design, active, True)


def test_new_stages_validate_without_loading_numerical_data():
    from src.io.ftt_campaign import STAGES
    from src.io.neural_wave_campaign import ROOT, load_wave, profile_paths

    for name in STAGES:
        spec = load_wave(ROOT / "input/task042extra_feinn_5nm" / (name + ".dat"))
        assert spec["campaign_version"] == 38
        assert profile_paths(spec)["artifacts"].name == "v38"
