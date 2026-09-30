"""Targeted data-boundary and full durable stage-switch regression."""

import ast
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy import sparse
import torch

from src.solvers import feinn_phase_training as training
from src.solvers.feinn_phase import make_model
from src.solvers.feinn_validation import parameters
from src.solvers.optimization_checkpoint import load_checkpoint
from src.solvers.neural_fe_action_packet import array_hash


def test_FE_compare_does_not_import_Torch():
    root = Path(__file__).resolve().parents[2]
    module = ast.parse((root / "src/solvers/feinn_phase_compare.py").read_text())
    imports = [
        node.module for node in ast.walk(module) if isinstance(node, ast.ImportFrom)
    ]
    assert "src.solvers.feinn_validation" not in imports
    assert "src.solvers.feinn_phase_training" not in imports
    assert "torch" not in imports


def test_full_fit_loop_preserves_Adam500_and_fresh_LBFGS(tmp_path, monkeypatch):
    """Run the real outer-loop/transactions with a tiny full-network map."""
    bounds = [[-5, 5], [-3.75, 3.75], [-1.25, 8.75]]
    design = dict(geometry=dict(bounds_nm=bounds), network=dict(seed=421001))
    ref = np.array([0.3 + 0.2j, -0.1 + 0.15j])
    x = torch.tensor([[0.8, -0.2, 4.0], [-0.5, 0.4, 3.2]], dtype=torch.float64)

    class Map:
        def __init__(self, _):
            self.counts = {}
            self.costs = {}

        def forward(self, model, batch=8):
            return np.array([complex(model(x)[0, 0].detach()), 0j])

        def vjp(self, model, dual, batch=8):
            model.zero_grad(set_to_none=True)
            torch.real(torch.tensor(dual[0]).conj() * model(x)[0, 0]).backward()
            return (
                torch.cat([p.grad.ravel() for p in model.parameters()])
                .detach()
                .numpy()
                .copy()
            )

    class Packet:
        counts = {}
        costs = {}

        def audit(self, c):
            return dict(
                native_relative=float(np.linalg.norm(c - ref)), strict_pass=False
            )

    monkeypatch.setattr(training, "configure", lambda: None)
    monkeypatch.setattr(
        training, "fit_gradient_checks", lambda *args: dict(test_only=True)
    )
    monkeypatch.setattr(training, "load_native", lambda _: Packet())
    monkeypatch.setattr(training, "load_moments", lambda _: {})
    monkeypatch.setattr(training, "CompleteMomentMap", Map)
    from src.solvers import feinn_error_geometry

    monkeypatch.setattr(
        feinn_error_geometry,
        "reference_label",
        lambda *args, **kw: (ref, dict(test_only=True)),
    )
    gp = tmp_path / "gram.npz"
    sparse.save_npz(gp, sparse.eye(2, format="csr", dtype=np.complex128))
    native = dict(
        files=dict(
            native=dict(path=str(tmp_path / "native.npz"), sha256="toy"),
            gram=dict(path=str(gp), sha256="toy"),
        )
    )
    qual = dict(
        result=dict(
            status="PHASE_INTERFACE_PASS_ONLY",
            initial_parameters_sha256=array_hash(parameters(make_model(design, True))),
        ),
        files=dict(moments=dict(path=str(tmp_path / "moments.npz"), sha256="toy")),
    )
    reference = dict(files=dict(reference=dict(path=str(tmp_path / "reference.npz"))))
    manifest = dict(
        source_sha="toy-unit-source",
        input_sha256="toy",
        run_id="toy-unit-fit",
        supervision_budget_origin_monotonic=perf_counter(),
        supervised_limit_seconds=600,
    )
    monkeypatch.setattr(training, "install_data_guard", lambda *args, **kw: [])
    result, files = training.run(
        design,
        native,
        qual,
        tmp_path,
        lambda *_: None,
        manifest,
        phase=True,
        supervised=True,
        reference_index=reference,
    )
    assert result["failure"] is None
    assert result["counts"]["Adam_updates"] == 500
    assert result["Gsolve_count"] == 0
    assert not result["official_candidate_results"]
    record = result["final_checkpoint"]
    durable = load_checkpoint(files["durable_final"], record["sha256"])
    assert durable["optimizer_class"] == "LBFGS"
    assert result["counts"]["complete_closures"] <= 1500
    adam = [a for a in result["audits"] if a["complete_closures"] == 500]
    assert adam
    assert adam[0]["checkpoint"]["metadata"]["stage"] == "Adam"
    assert any(
        c["metadata"]["state_kind"] == "Adam500_to_fresh_LBFGS"
        for c in __import__("json").loads(files["checkpoint_index"].read_text())[
            "checkpoints"
        ]
    )
    with np.load(files["checkpoint"], allow_pickle=False) as saved:
        p = torch.cat(
            [
                v.ravel()
                for k, v in durable["model"].items()
                if k.startswith("envelopes.")
            ]
        ).numpy()
        np.testing.assert_array_equal(saved["parameters"], p)
        np.testing.assert_array_equal(saved["c"], durable["complete_c"])


def test_artifact_audit_guard_rejects_PDE_labels_and_other_weights(
    tmp_path, monkeypatch
):
    from src.runners import feinn_resources

    root = tmp_path / "artifact_root"
    root.mkdir()
    monkeypatch.setattr(feinn_resources, "ARTIFACTS", root)
    hooks = []
    monkeypatch.setattr(training.sys, "addaudithook", hooks.append)
    native = root / "native.npz"
    reference = root / "reference_state.npz"
    reads = training.install_data_guard(
        [native, reference], root / "own_run", supervised=False
    )
    hooks[0]("open", (str(native), "r", 0))
    assert reads == [str(native)]
    for path in (reference, root / "old_supervised_weights.npz"):
        import pytest

        with pytest.raises(PermissionError):
            hooks[0]("open", (str(path), "r", 0))
