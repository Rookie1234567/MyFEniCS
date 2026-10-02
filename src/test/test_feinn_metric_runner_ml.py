"""A small PDE-only fork verifies the reused runner's new metric transaction."""

from time import perf_counter
import numpy as np
from scipy import sparse
from src.solvers import feinn_gn_training as training, feinn_metric_diagnostic
from src.solvers.feinn_phase import make_model
from src.solvers.feinn_phase_training import policy
from src.solvers.feinn_parameter_metric import ParameterMetric
from src.solvers.feinn_validation import assign, parameters
from src.solvers.optimization_checkpoint import capture, load_checkpoint, restore
from src.solvers.damped_gauss_newton import DampedGNState
from src.solvers.feinn_parameter_metric import MetricDampedGNState
from src.test.test_feinn_jvp_ml import fixture


def test_metric_fork_keeps_original_state_and_saves_matching_optimizer(
    tmp_path, monkeypatch
):
    design = dict(
        geometry=dict(bounds_nm=[[-5, 5], [-3.75, 3.75], [-1.25, 8.75]]),
        network=dict(seed=421001),
    )
    model = make_model(design, True)
    mapping = fixture()
    rng = np.random.default_rng(4211103)
    theta = parameters(model) + 0.01 * rng.normal(size=8966)
    assign(model, theta + 0.001 * rng.normal(size=8966))
    f = mapping.forward(model)
    assign(model, theta)
    anchor = mapping.forward(model)
    gn = DampedGNState(1000)
    gn.accepted = 75
    gn.mu = 8.3
    old = capture(
        model,
        gn,
        dict(
            logical_path_seconds=13.0,
            counts=dict(K=5),
            JVP_VJP_counts=dict(JVP=5, VJP=6),
            d_G=float(np.vdot(f, f).real),
            **policy(False),
        ),
    )
    old["complete_c"] = anchor
    monkeypatch.setattr(
        feinn_metric_diagnostic, "load_anchor", lambda *args: (model, anchor, old)
    )
    monkeypatch.setattr(training, "configure", lambda: None)
    monkeypatch.setattr(training, "install_data_guard", lambda *args, **kw: [])
    monkeypatch.setattr(training, "load_moments", lambda *args: {})
    monkeypatch.setattr(training, "CompleteMomentMap", lambda *args: fixture())

    class Packet:
        def __init__(self):
            self.f = f
            self.counts = dict(A=0, AH=0, audit=0)
            self.costs = {}

        def apply(self, c, adjoint=False):
            self.counts["AH" if adjoint else "A"] += 1
            return c.copy()

        def audit(self, c):
            self.counts["audit"] += 1
            value = float(np.linalg.norm(c - f) / np.linalg.norm(f))
            return dict(
                native_relative=value, augmented_relative=value, strict_pass=True
            )

    monkeypatch.setattr(training, "load_native", lambda *args: Packet())

    class Factor:
        def __init__(self, *args):
            self.record = {}
            self.solves = 0

        def solve(self, v):
            self.solves += 1
            return v.copy()

        def close(self):
            pass

    monkeypatch.setattr(training, "SparseRiesz", Factor)
    gp = tmp_path / "G.npz"
    sparse.save_npz(gp, sparse.eye(36, format="csr", dtype=complex))
    mp = tmp_path / "M.npz"
    metric = ParameterMetric(np.geomspace(0.1, 10, 8966))
    np.savez(mp, M=metric.diagonal)
    entry = {
        k: dict(path=str(tmp_path / k), sha256="toy")
        for k in ("checkpoint", "durable_final", "checkpoint_index")
    }
    entry["logical_prefix_seconds"] = 17.0
    native = dict(
        files=dict(
            native=dict(path="toy", sha256="toy"), gram=dict(path=str(gp), sha256="toy")
        )
    )
    qual = dict(files=dict(moments=dict(path="toy", sha256="toy")))
    pilot = dict(
        result=dict(C_start_signal=True, metric_sha256=metric.sha256),
        files=dict(metric=dict(path=str(mp))),
    )
    manifest = dict(
        stage="v11_phase_block_metric",
        source_sha="toy",
        input_sha256="toy",
        run_id="toy-v11",
        supervision_budget_origin_monotonic=perf_counter(),
        supervised_limit_seconds=600,
    )
    result, files = training.run(
        design,
        native,
        qual,
        dict(result=dict(passed=True)),
        tmp_path,
        lambda *_: None,
        manifest,
        phase=True,
        supervised=False,
        continuation=entry,
        metric_pilot=pilot,
    )
    import json

    assert json.loads(files["checkpoint_index"].read_text())["fault_resume_limit"] == 1
    assert result["failure"] is None and result["new_accepted_outer"] == 1
    assert result["inherited_accepted_outer"] == 75 and result["common_mu0"] == 8.3
    assert result["inherited_prefix_seconds"] == 17 and not result["PC_builds"]
    assert result["pde_only_solve"] and not result["reference_used_for_training"]
    saved = load_checkpoint(
        files["durable_final"], result["final_checkpoint"]["sha256"]
    )
    assert saved["optimizer_class"] == "MetricDampedGNState"
    other = make_model(design, True)
    optimizer = MetricDampedGNState(1, metric)
    restore(other, optimizer, saved)
    np.testing.assert_array_equal(fixture().forward(other), saved["complete_c"])
    assert optimizer.accepted == 76 and optimizer.metric.sha256 == metric.sha256
    assert saved["metadata"]["limits"] == dict(
        accepted=30, K=1200, JVP_VJP=2500, trial=128
    )
