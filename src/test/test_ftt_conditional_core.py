"""Small complex fixtures for the opt-in conditional output operator."""

from copy import deepcopy
import json
import numpy as np
import pytest
import torch
from scipy.sparse.linalg import LinearOperator, lsmr

from src.solvers.ftt_field import FTTField
from src.solvers.ftt_conditional_core import (
    ConditionalCoreAction,
    output_coefficients,
    set_output_coefficients,
    hidden_parameters,
    relative_pair,
    verify_and_apply_core,
)
from src.solvers.ftt_factored_moments import model_identity
from src.solvers.optimization_checkpoint import (
    capture,
    restore,
    CheckpointStore,
    load_checkpoint,
)
from src.solvers.ftt_core_training import CoreBoundary, hidden_step


class PointFixture:
    def __init__(self, coordinates, matrix):
        self.x, self.matrix = coordinates, matrix
        self.nodes = [np.unique(coordinates[:, a]) for a in range(3)]
        self.static_bytes = self.dynamic_bytes = 0

    def _cores(self, model):
        with torch.no_grad():
            return [
                model.core(
                    a, (torch.from_numpy(n) - model.center[a]) / model.half_width[a]
                ).numpy()
                for a, n in enumerate(self.nodes)
            ]

    def forward(self, model):
        with torch.no_grad():
            return self.matrix @ model(torch.from_numpy(self.x)).numpy().ravel()

    def forward_with_core_values(self, model, values):
        with torch.no_grad():
            return self.matrix @ model(torch.from_numpy(self.x)).numpy().ravel()

    def vjp(self, model, dual):
        model.zero_grad(set_to_none=True)
        v = model(torch.from_numpy(self.x)).ravel()
        y = torch.from_numpy(self.matrix) @ v
        torch.real(torch.vdot(torch.from_numpy(dual), y)).backward()
        return np.concatenate(
            [p.grad.detach().numpy().ravel() for p in model.parameters()]
        )

    def invalidate(self):
        pass


class TinyAction:
    def __init__(self, matrix):
        self.matrix = matrix
        self.size = len(matrix)
        self.f = np.ones(self.size, dtype=np.complex128)
        self.bnorm = np.linalg.norm(self.f)

    def apply(self, c, adjoint=False):
        return (self.matrix.conj().T if adjoint else self.matrix) @ c


@pytest.mark.parametrize("kind", ["fttnn", "chebtt"])
@pytest.mark.parametrize("axis", [0, 1, 2])
def test_complex_linear_adjoint_layout(kind, axis):
    rng = np.random.default_rng(4214101)
    m = FTTField([[-1, 1]] * 3, kind)
    m.nonzero_qualification_state()
    x = rng.uniform(-1, 1, (7, 3))
    M = (rng.normal(size=(9, 21)) + 1j * rng.normal(size=(9, 21))).astype(np.complex128)
    A = (rng.normal(size=(9, 9)) + 1j * rng.normal(size=(9, 9))).astype(np.complex128)
    mapping = PointFixture(x, M)
    a = TinyAction(A)
    op = ConditionalCoreAction(m, mapping, a, axis)
    base = deepcopy(m.state_dict())
    c = mapping.forward(m)
    d = (rng.normal(size=op.size) + 1j * rng.normal(size=op.size)).astype(np.complex128)
    v = (rng.normal(size=9) + 1j * rng.normal(size=9)).astype(np.complex128)
    Kd = op.K(d)
    assert model_identity(m) == op.identity
    assert abs(np.vdot(Kd, v) - np.vdot(d, op.KH(v))) < 1e-10 * max(
        1, abs(np.vdot(Kd, v))
    )
    assert abs(np.vdot(op.B(d), v) - np.vdot(d, op.BH(v))) < 1e-10 * max(
        1, abs(np.vdot(op.B(d), v))
    )
    w = output_coefficients(m, axis)
    set_output_coefficients(m, axis, w + d.reshape(w.shape))
    assert relative_pair(mapping.forward(m), c + Kd)["relative"] < 1e-10
    m.load_state_dict(base)
    set_output_coefficients(m, axis, w)
    assert all(torch.equal(m.state_dict()[k], base[k]) for k in base)


@pytest.mark.parametrize("case", ["full", "duplicate", "scales", "nonhermitian"])
def test_lsmr_small_complex_svd(case):
    rng = np.random.default_rng(21)
    B = (rng.normal(size=(13, 5)) + 1j * rng.normal(size=(13, 5))).astype(np.complex128)
    if case == "duplicate":
        B[:, 4] = B[:, 0]
    if case == "scales":
        B[:, 0] *= 1e-2
        B[:, 4] *= 1e2
    b = (rng.normal(size=13) + 1j * rng.normal(size=13)).astype(np.complex128)
    op = LinearOperator(
        B.shape,
        matvec=lambda x: B @ x,
        rmatvec=lambda x: B.conj().T @ x,
        dtype=np.complex128,
    )
    x = lsmr(op, b, atol=1e-12, btol=1e-12, conlim=1e12, maxiter=100)[0]
    exact = np.linalg.lstsq(B, b, rcond=1e-12)[0]
    assert np.linalg.norm(B @ x - B @ exact) < 1e-9


def test_only_hidden_parameters_and_zero_initialization():
    first = FTTField([[-1, 1]] * 3, "fttnn")
    second = FTTField([[-1, 1]] * 3, "fttnn")
    assert model_identity(first) == model_identity(second)
    assert sum(p.numel() for p in hidden_parameters(first)) == 912
    x = torch.tensor([[0.2, 0.3, -0.1]], dtype=torch.float64)
    assert torch.count_nonzero(first(x)) == 0
    assert torch.count_nonzero(first.core(0, x[:, 0])) and torch.count_nonzero(
        first.core(1, x[:, 1])
    )


def test_atomic_core_position_restore_and_reopen(tmp_path):
    model = FTTField([[-1, 1]] * 3, "fttnn")
    pos = dict(round=1, axis_index=2, phase="core")
    b = CoreBoundary(pos)
    state = capture(model, b, {"reference_used_for_training": False})
    state.update(c=np.zeros(5, complex), r=np.ones(5, complex))
    store = CheckpointStore(tmp_path / "checkpoints")
    entry = store.save(state, pin=True)
    loaded = load_checkpoint(tmp_path / "checkpoints" / entry["name"], entry["sha256"])
    original = model_identity(model)
    with torch.no_grad():
        model.cores[0][0].bias.add_(0.1)
    pos["round"] = 4
    restore(model, b, loaded)
    assert model_identity(model) == original and pos == dict(
        round=1, axis_index=2, phase="core"
    )
    pointer = json.loads((tmp_path / "checkpoints/current.json").read_text())
    assert pointer["current"]["sha256"] == entry["sha256"]


def test_stale_base_rejected():
    m = FTTField([[-1, 1]] * 3, "fttnn")
    p = PointFixture(np.array([[0.2, 0.3, 0.4]]), np.eye(3, dtype=complex))
    a = TinyAction(np.eye(3, dtype=complex))
    op = ConditionalCoreAction(m, p, a, 2)
    with torch.no_grad():
        m.cores[0][0].bias.add_(0.01)
    with pytest.raises(ValueError, match="VERSION_CHANGED"):
        op.K(np.zeros(op.size, complex))


def test_rejected_full_model_step_rolls_back():
    rng = np.random.default_rng(4)
    m = FTTField([[-1, 1]] * 3, "fttnn")
    x = rng.uniform(-1, 1, (5, 3))
    p = PointFixture(x, np.eye(15, dtype=complex))
    a = TinyAction(np.eye(15, dtype=complex))
    op = ConditionalCoreAction(m, p, a, 2)
    before = model_identity(m)
    c = p.forward(m)
    d = (rng.normal(size=op.size) + 1j * rng.normal(size=op.size)) * 1e6
    _, _, record = verify_and_apply_core(m, p, a, op, d.astype(complex), c)
    assert not record["accepted"] and model_identity(m) == before


@pytest.mark.parametrize("kind", ["fttnn", "chebtt"])
@pytest.mark.parametrize("geometry", ["box", "permuted", "skew"])
def test_complete_original_moment_conditional_action_and_fallback(kind, geometry):
    from src.test.test_ftt_structure import fixture, BOX
    from src.solvers.ftt_factored_moments import FactoredMomentMap
    from src.solvers.ftt_moments import StreamingMomentMap

    packet = fixture(geometry == "permuted", geometry == "skew")
    model = FTTField(BOX, kind)
    model.nonzero_qualification_state()
    mapping = FactoredMomentMap(packet)
    old = StreamingMomentMap(packet)
    action = TinyAction(np.eye(6, dtype=np.complex128) * (1 + 0.3j))
    c = mapping.forward(model)
    rng = np.random.default_rng(91)
    for axis in range(3):
        op = ConditionalCoreAction(model, mapping, action, axis)
        d = (rng.normal(size=op.size) + 1j * rng.normal(size=op.size)).astype(
            np.complex128
        )
        d /= np.linalg.norm(d)
        dual = (rng.normal(size=6) + 1j * rng.normal(size=6)).astype(np.complex128)
        kd = op.K(d)
        kh = op.KH(dual)
        assert abs(np.vdot(kd, dual) - np.vdot(d, kh)) < 1e-10 * max(
            1, abs(np.vdot(kd, dual))
        )
        coeff = output_coefficients(model, axis)
        set_output_coefficients(model, axis, coeff + d.reshape(coeff.shape))
        assert relative_pair(old.forward(model), c + kd)["relative"] < 1e-10
        set_output_coefficients(model, axis, coeff)
        mapping.invalidate()


def test_schema_labels_and_modified_solver_rejected(tmp_path, monkeypatch):
    from src.io import ftt_core_campaign as io
    from src.io.input_loader import InputError
    from src.io.neural_wave_campaign import ROOT, digest
    from src.runners.ftt_worker import training_allowed

    design = json.loads(io.DESIGN.read_text())
    p = tmp_path / "design.json"
    p.write_text(json.dumps(design))
    monkeypatch.setattr(io, "DESIGN", p)
    path = ROOT / "input/task042extra_feinn_5nm/v41_core_linear_checks.dat"
    data = dict(
        schema_version=11,
        neural_wave=dict(stage="v41_core_linear_checks", design_sha256=digest(p)),
    )
    assert io.load_core(path, data, b"fixture")["campaign_version"] == 41
    data["neural_wave"]["reference_state"] = "forbidden"
    with pytest.raises(InputError, match="LABEL"):
        io.load_core(path, data, b"fixture")
    del data["neural_wave"]["reference_state"]
    design["core_solver"]["damp"] = 0.01
    p.write_text(json.dumps(design))
    data["neural_wave"]["design_sha256"] = digest(p)
    with pytest.raises(InputError, match="CONTRACT"):
        io.load_core(path, data, b"fixture")
    active = ROOT / "benchmarks/artifacts/task42extra/v41/test"
    for entry in [design["reference"], design["gram"]]:
        assert not training_allowed(ROOT / entry["path"], design, active, False)
    assert not training_allowed(
        ROOT
        / "benchmarks/artifacts/task42extra/v40/v40_interior_moment_tensor/interior_tensor.npz",
        design,
        active,
        False,
    )


@pytest.mark.parametrize("mode", ["accept", "reject", "exception", "call_limit"])
def test_actual_hidden_transaction_and_fixed_outputs(mode, monkeypatch, tmp_path):
    from time import monotonic

    rng = np.random.default_rng(141)
    model = FTTField([[-1, 1]] * 3, "fttnn")
    model.nonzero_qualification_state()
    x = rng.uniform(-1, 1, (5, 3))
    mapping = PointFixture(x, np.eye(15, dtype=np.complex128))
    action = TinyAction(np.eye(15, dtype=np.complex128))
    before = deepcopy(model.state_dict())
    outputs = [output_coefficients(model, a).copy() for a in range(3)]
    calls = []

    if mode != "accept":

        def forced_step(optimizer, closure):
            closure()
            with torch.no_grad():
                hidden_parameters(model)[0].add_(0.1)
            if mode == "exception":
                raise RuntimeError("ACTUAL_LINE_SEARCH_FAILURE_FIXTURE")
            if mode == "reject":
                # Force a nonfinite trial, exercising the actual post-step check.
                with torch.no_grad():
                    hidden_parameters(model)[0].fill_(float("nan"))
            else:
                for _ in range(20):
                    closure()

        monkeypatch.setattr(torch.optim.LBFGS, "step", forced_step)
    if mode == "exception":
        with pytest.raises(RuntimeError, match="LINE_SEARCH_FAILURE"):
            hidden_step(
                model,
                mapping,
                action,
                monotonic() + 30,
                lambda event, row: calls.append((event, row)),
            )
    else:
        c, r, record, optimizer_state, trial = hidden_step(
            model,
            mapping,
            action,
            monotonic() + 30,
            lambda event, row: calls.append((event, row)),
        )
        assert np.all(np.isfinite(c)) and np.all(np.isfinite(r))
        assert record["calls"] <= 20
        if mode == "accept":
            assert record["accepted"] and record["trial_loss"] <= record["old_loss"]
            assert record["accepted_update_norm"] > 0
        else:
            assert not record["accepted"] and record["accepted_update_norm"] == 0
        if mode == "call_limit":
            assert record["calls"] == 20
            assert record["stop_reason"] == "HIDDEN_ACTUAL_CALL_OR_SAVE_RESERVE_REACHED"
        optimizer = torch.optim.LBFGS(hidden_parameters(model))
        optimizer.load_state_dict(optimizer_state)
        state = capture(model, optimizer, {"committed": True})
        store = CheckpointStore(tmp_path / "hidden")
        entry = store.save(state, pin=True)
        loaded = load_checkpoint(tmp_path / "hidden" / entry["name"], entry["sha256"])
        restored = FTTField([[-1, 1]] * 3, "fttnn")
        restore(restored, torch.optim.LBFGS(hidden_parameters(restored)), loaded)
        assert model_identity(restored) == model_identity(model)
        assert not trial["metadata"]["committed"]
    if mode != "accept":
        assert all(torch.equal(model.state_dict()[k], before[k]) for k in before)
    for axis in range(3):
        assert np.array_equal(output_coefficients(model, axis), outputs[axis])
