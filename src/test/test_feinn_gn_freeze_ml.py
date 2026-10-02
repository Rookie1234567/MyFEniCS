"""A resource-stop export preserves the complete original state and lineage."""

import json
from time import perf_counter

import numpy as np

from src.solvers import feinn_gn_freeze as freeze
from src.solvers.feinn_phase import make_model
from src.solvers.feinn_phase_training import policy
from src.solvers.feinn_validation import parameters, assign
from src.solvers.optimization_checkpoint import capture, CheckpointStore, digest
from src.solvers.damped_gauss_newton import DampedGNState
from src.solvers.neural_fe_action_packet import array_hash
from src.test.test_feinn_jvp_ml import fixture


def test_resource_export_is_not_a_new_training_or_factor(tmp_path, monkeypatch):
    design = dict(
        geometry=dict(bounds_nm=[[-5, 5], [-3.75, 3.75], [-1.25, 8.75]]),
        network=dict(seed=421001),
    )
    model = make_model(design, True)
    p = parameters(model)
    p[-390:] = np.random.default_rng(42).normal(size=390) * 0.001
    assign(model, p)
    c = fixture().forward(model)
    optimizer = DampedGNState(1000)
    optimizer.accepted = 7
    meta = dict(
        source_sha="actual-training-source",
        accepted_outer=7,
        input_sha256="original-input",
        route="V10-PHASE-CACHED-GN-CONTINUE",
        inherited_counts=dict(K=3, full_loss_gradient=2, trial_loss=1, G_matvec=0),
        inherited_JVP_VJP_counts=dict(JVP=3, VJP=5),
        inherited_accepted_outer=5,
        buffers_sha256={
            n: array_hash(b.detach().numpy()) for n, b in model.named_buffers()
        },
        h0=1000,
        mu=optimizer.mu,
        d_G=0.01,
        logical_path_seconds=19.0,
        derivative_cache=dict(costs=dict(JVP=3.0, VJP=4.0)),
        budget_frontier={},
    )
    state = capture(model, optimizer, meta)
    state["complete_c"] = c
    store = CheckpointStore(tmp_path / "old_checkpoints")
    record = store.save(state, pin=True)
    pt = store.directory / record["name"]
    original_hash = digest(pt)
    boundary = dict(
        checkpoint_pointer=dict(path=str(store.pointer)),
        durable_final=dict(path=str(pt), sha256=original_hash),
        history=dict(path=str(tmp_path / "old_history.jsonl")),
        prior_manifest=dict(path="old-manifest"),
        prior_summary=dict(path="old-summary"),
        original_V9_logical_prefix_seconds=11.0,
        selection="LATEST_OWN_DURABLE_NOT_BEST_OR_TRIAL",
        spent_counts_lower_bound=dict(
            K=11, full_loss_gradient=3, trial_loss=4, G_matvec=0
        ),
        spent_JVP_VJP_lower_bound=dict(JVP=11, VJP=14),
    )
    entry = {
        k: dict(path="immutable-old-" + k)
        for k in ("checkpoint", "durable_final", "checkpoint_index")
    }
    monkeypatch.setattr(freeze, "configure", lambda: None)
    monkeypatch.setattr(freeze, "frozen_entries", lambda: dict(phase_gn=entry))
    monkeypatch.setattr(freeze, "install_data_guard", lambda *a, **k: [])
    monkeypatch.setattr(freeze, "load_recovery", lambda *a: (model, c, state))
    monkeypatch.setattr(freeze, "load_moments", lambda *a: {})
    monkeypatch.setattr(freeze, "CompleteMomentMap", lambda *a: fixture())

    class Packet:
        counts = {"A": 1, "AH": 0}
        costs = {}

        def audit(self, c):
            return dict(native_relative=0.98, strict_pass=False)

    monkeypatch.setattr(freeze, "load_native", lambda *a: Packet())
    artifact = tmp_path / "export"
    artifact.mkdir()
    result, files = freeze.freeze_resource_boundary(
        design,
        dict(files=dict(native=dict(path="native"))),
        dict(files=dict(moments=dict(path="moments"))),
        artifact,
        lambda *a: None,
        dict(
            resource_boundary=boundary,
            source_sha="export-source",
            input_sha256="export-input",
            phase_training_attempt_seconds=17.0,
            supervision_budget_origin_monotonic=perf_counter(),
        ),
    )
    assert digest(pt) == original_hash and result["original_PT_unmodified"]
    assert (
        result["accepted_updates_this_attempt"] == 0
        and result["new_accepted_outer"] == 2
    )
    assert result["counts"]["K"] == 11 and result["inherited_prefix_seconds"] == 28.0
    assert result["Gram_factor"] is None and result["Gsolve_count"] is None
    assert result["retained_resource_export"] and not result["numerical_failure_claim"]
    with np.load(files["checkpoint"]) as row:
        np.testing.assert_array_equal(row["c"], c)
        np.testing.assert_array_equal(row["parameters"], parameters(model))
        assert (
            str(row["source_sha"]) == "actual-training-source"
            and str(row["export_source_sha"]) == "export-source"
        )
        for key, value in policy(False).items():
            assert bool(row[key]) is value
    assert (
        json.loads(files["history"].read_text())["kind"] == "RESOURCE_BOUNDARY_FROZEN"
    )
