"""Fixed physical phase, parameter identity and nonzero real VJP checks."""

import numpy as np
import torch

from src.solvers.feinn_phase import PhaseCoordinateField, K_INC, XC
from src.solvers.feinn_torch import CoordinateField
from src.solvers.feinn_validation import assign, parameters
from src.solvers.optimization_checkpoint import optimizer_step, capture, restore

torch.set_num_threads(1)
torch.set_num_interop_threads(1)

BOUNDS = [[-5, 5], [-3.75, 3.75], [-1.25, 8.75]]


def test_fixed_phase_has_identical_initial_parameters_and_zero_field():
    plain = CoordinateField(BOUNDS)
    phase = PhaseCoordinateField(BOUNDS)
    np.testing.assert_array_equal(parameters(plain), parameters(phase))
    assert sum(p.numel() for p in phase.parameters()) == 8966
    x = torch.tensor([[1.2, -0.7, 4.1]], dtype=torch.float64)
    assert torch.count_nonzero(phase(x)) == 0
    assert set(dict(phase.named_buffers())) == {
        "center",
        "half_width",
        "phase_k_inc",
        "phase_origin",
    }


def test_nonzero_phase_point_values_and_zero_carrier_regression():
    plain = CoordinateField(BOUNDS)
    rng = np.random.default_rng(421002)
    p = parameters(plain) + 0.005 * rng.normal(size=8966)
    assign(plain, p)
    phase = PhaseCoordinateField(BOUNDS)
    assign(phase, p)
    zero = PhaseCoordinateField(BOUNDS, k_inc=np.zeros(3))
    assign(zero, p)
    x = torch.tensor(
        rng.uniform([-5, -3.75, -1.25], [5, 3.75, 8.75], size=(27, 3)),
        dtype=torch.float64,
    )
    np.testing.assert_array_equal(zero(x).detach(), plain(x).detach())
    expected = (
        np.exp(1j * ((x.numpy() - XC) @ K_INC))[:, None] * plain(x).detach().numpy()
    )
    np.testing.assert_allclose(
        phase(x).detach().numpy(), expected, rtol=1e-14, atol=1e-15
    )


def test_nonzero_real_phase_gradient_and_real_line_search_rollback():
    model = PhaseCoordinateField(BOUNDS)
    rng = np.random.default_rng(421003)
    p = parameters(model) + 0.01 * rng.normal(size=8966)
    assign(model, p)
    x = torch.tensor(rng.normal(size=(8, 3)), dtype=torch.float64)
    dual = torch.tensor(
        rng.normal(size=(8, 3)) + 1j * rng.normal(size=(8, 3)), dtype=torch.complex128
    )

    def value():
        return torch.real(torch.sum(dual.conj() * model(x)))

    value().backward()
    g = torch.cat([p.grad.flatten() for p in model.parameters()]).numpy()
    d = g / np.linalg.norm(g)
    analytic = np.dot(g, d)
    for h in (1e-4, 1e-5, 1e-6):
        assign(model, p + h * d)
        plus = float(value().detach())
        assign(model, p - h * d)
        minus = float(value().detach())
        assert abs((plus - minus) / (2 * h) - analytic) / abs(analytic) < 1e-5
    assign(model, p)
    opt = torch.optim.LBFGS(
        model.parameters(),
        lr=1,
        history_size=20,
        max_iter=20,
        max_eval=25,
        line_search_fn="strong_wolfe",
    )
    original = capture(model, opt, {})
    calls = 0

    def closure():
        nonlocal calls
        calls += 1
        opt.zero_grad()
        loss = torch.sum(abs(model(x) - dual) ** 2).real
        loss.backward()
        if calls == 2:
            raise RuntimeError("actual trial failure")
        return loss

    try:
        optimizer_step(model, opt, closure, lambda _: None)
    except RuntimeError as error:
        assert str(error) == "actual trial failure"
    assert calls == 2
    np.testing.assert_array_equal(parameters(model), p)
    assert opt.state_dict()["state"] == original["optimizer"]["state"]
    restore(model, opt, original)
