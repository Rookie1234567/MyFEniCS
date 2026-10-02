"""Small nonlinear objective: add a stable FD witness without replaying K."""

from types import SimpleNamespace
import numpy as np
from src.solvers import feinn_metric_diagnostic as diagnostic
from src.solvers.feinn_phase import make_model
from src.solvers.feinn_parameter_metric import ParameterMetric
from src.solvers.feinn_validation import parameters, assign


def test_fd_tail_is_one_witness_keeps_base_and_reuses_qualified_chains(
    tmp_path, monkeypatch
):
    design = dict(
        geometry=dict(bounds_nm=[[-5, 5], [-3.75, 3.75], [-1.25, 8.75]]),
        network=dict(seed=421001),
    )
    model = make_model(design, True)
    theta0 = parameters(model).copy()
    g = np.random.default_rng(4211104).normal(size=8966)
    metric = ParameterMetric(np.ones(8966))
    mp = tmp_path / "M.npz"
    np.savez(mp, M=metric.diagonal)
    rng = np.random.default_rng(4211102)
    rows = []
    for i in range(3):
        v = rng.normal(size=8966)
        v /= np.linalg.norm(v)
        expected = float(g @ v)
        steps = (1e-6, 1e-7) if i == 0 else (1e-7, 1e-8)
        values = [
            dict(
                epsilon=h,
                expected=expected,
                actual=expected + 1e8 * h * h * expected**3,
                relative=abs(1e8 * h * h * expected**2),
            )
            for h in steps
        ]
        rows.append(
            dict(
                direction=i,
                transformed_K_pair=dict(relative=0.0),
                finite_difference=values,
            )
        )
    calls = []

    def value(theta, restore_only=False):
        assign(model, theta)
        if restore_only:
            return None
        calls.append(theta.copy())
        z = float(g @ (theta - theta0))
        return z + 1e8 * z**3

    p = SimpleNamespace(
        model=model,
        value=value,
        value_gradient=lambda: (0.0, g, None),
        jac=SimpleNamespace(invalidate=lambda: None),
    )
    factor = SimpleNamespace(close=lambda: None)
    proof = dict(parameter_sha256="same", complete_c_sha256="same", d_G=1.0)
    monkeypatch.setattr(diagnostic, "setup", lambda *args: (p, factor, {}, proof))
    monkeypatch.setattr(diagnostic, "finish", lambda *args: dict(counts=dict(K=0)))
    old = dict(
        status="PARAMETER_METRIC_INTERFACE_FAILED",
        actual_g_y=dict(relative=0.0),
        identity_short_proposal={
            k: dict(relative=0.0) for k in ("step_pair", "pred_pair", "ared_pair")
        },
        identity=proof,
        directions=rows,
        real_K_actions_including_independent_chains=16,
        counts=dict(K=13),
    )
    result, _ = diagnostic.qualify_fd_tail(
        design,
        {},
        {},
        dict(files=dict(metric=dict(path=str(mp)))),
        dict(
            result=old,
            source_sha="original",
            files=dict(result=dict(path="original", sha256="original")),
        ),
        tmp_path,
        lambda *_: None,
        {},
    )
    assert result["passed"] and result["counts"]["K"] == 0
    assert result["real_K_actions_including_independent_chains"] == 16
    assert len(calls) == 2 and len(result["new_witnesses"]) == 1
    np.testing.assert_array_equal(parameters(model), theta0)
    assert result["metric_sha256"] == metric.sha256
