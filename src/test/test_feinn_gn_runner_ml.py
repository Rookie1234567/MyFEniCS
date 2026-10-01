"""One small real runner transaction, distinct from the formal M5 campaign."""

from time import perf_counter
import numpy as np
from scipy import sparse

from src.solvers import feinn_gn_training as training
from src.solvers.feinn_phase import make_model
from src.solvers.feinn_validation import assign, parameters
from src.solvers.optimization_checkpoint import load_checkpoint
from src.test.test_feinn_jvp_ml import fixture


def test_real_fit_GN_runner_reconstructs_committed_model_and_optimizer(
    tmp_path, monkeypatch
):
    design = dict(
        geometry=dict(bounds_nm=[[-5, 5], [-3.75, 3.75], [-1.25, 8.75]]),
        network=dict(seed=421001),
    )
    model = make_model(design, True)
    p0 = parameters(model)
    rng = np.random.default_rng(421991)
    p0 = p0 + 0.01 * rng.normal(size=len(p0))
    assign(model, p0)
    mapping = fixture()
    anchor = mapping.forward(model)
    assign(model, p0 + 0.002 * rng.normal(size=len(p0)))
    ref = mapping.forward(model)
    assign(model, p0)
    entry = dict(
        path=str(tmp_path / "toy_Adam500.pt"),
        sha256="test-only",
        metadata=dict(elapsed_charged_seconds=11.0),
    )
    monkeypatch.setattr(training, "configure", lambda: None)
    monkeypatch.setattr(training, "prefix_entry", lambda *args: entry)
    monkeypatch.setattr(
        training, "load_boundary", lambda *args, **kw: (model, dict(complete_c=anchor))
    )
    monkeypatch.setattr(training, "install_data_guard", lambda *args, **kw: [])
    monkeypatch.setattr(training, "load_moments", lambda *args: {})
    monkeypatch.setattr(training, "CompleteMomentMap", lambda *args: fixture())

    class Packet:
        counts = {}
        costs = {}

        def audit(self, c):
            return dict(
                native_relative=float(np.linalg.norm(c - ref)), strict_pass=False
            )

    monkeypatch.setattr(training, "load_native", lambda *args: Packet())
    from src.solvers import feinn_error_geometry

    monkeypatch.setattr(
        feinn_error_geometry,
        "reference_label",
        lambda *args, **kw: (ref, dict(role="synthetic independent unit target")),
    )
    gp = tmp_path / "gram.npz"
    sparse.save_npz(gp, sparse.eye(len(ref), format="csr", dtype=complex))
    native = dict(
        files=dict(
            native=dict(path="test-only", sha256="test-only"),
            gram=dict(path=str(gp), sha256="test-only"),
        )
    )
    qual = dict(files=dict(moments=dict(path="test-only", sha256="test-only")))
    refs = dict(files=dict(reference=dict(path="test-only")))
    manifest = dict(
        source_sha="test-only",
        input_sha256="test-only",
        run_id="unit-gn",
        supervision_budget_origin_monotonic=perf_counter(),
        supervised_limit_seconds=600,
    )
    result, files = training.run(
        design,
        native,
        qual,
        dict(result=dict(status="GN_INTERFACE_PASS")),
        tmp_path,
        lambda *_: None,
        manifest,
        phase=True,
        supervised=True,
        reference=refs,
    )
    assert result["failure"] is None
    assert (
        result["new_Adam_updates"] == 0
        and result["inherited_committed_Adam_updates"] == 500
    )
    assert result["Gsolve_count"] == 0 and result["Gram_factor"] is None
    assert not result["official_candidate_results"] and not result["pde_only_solve"]
    saved = load_checkpoint(
        files["durable_final"], result["final_checkpoint"]["sha256"]
    )
    assert saved["optimizer_class"] == "DampedGNState"
    restored = make_model(design, True)
    restored.load_state_dict(saved["model"])
    np.testing.assert_array_equal(fixture().forward(restored), saved["complete_c"])
    with np.load(files["checkpoint"], allow_pickle=False) as row:
        np.testing.assert_array_equal(row["parameters"], parameters(restored))
        np.testing.assert_array_equal(row["c"], saved["complete_c"])
    assert (
        result["counts"]["K"] <= 1000 and sum(result["JVP_VJP_counts"].values()) <= 2500
    )
