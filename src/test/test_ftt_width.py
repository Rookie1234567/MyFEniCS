"""Opt-in width and two-stage LSMR fixtures, including actual old-map checks."""

from copy import deepcopy
from time import monotonic
import json
import numpy as np
import pytest
import torch
from scipy.sparse.linalg import LinearOperator
from src.solvers.ftt_bloch_field import BlochFTTField, IndependentPointPhase
from src.solvers.ftt_width_extension import (
    widen_field,
    width_policy,
    width_trend,
    strong_width_signal,
)
from src.solvers.ftt_core_refinement import solve_refined
from src.solvers.ftt_conditional_core import (
    ConditionalCoreAction,
    output_coefficients,
    set_output_coefficients,
    hidden_parameters,
    relative_pair,
)
from src.solvers.ftt_factored_moments import FactoredMomentMap, model_identity
from src.solvers.ftt_moments import StreamingMomentMap
from src.solvers.optimization_checkpoint import (
    capture,
    restore,
    atomic_write,
    load_checkpoint,
    digest,
)
from src.solvers.ftt_core_training import CoreBoundary
from src.test.test_ftt_bloch import phase
from src.test.test_ftt_structure import BOX, fixture
from src.test.test_ftt_conditional_core import TinyAction


def pair():
    old = BlochFTTField(BOX, "fttnn", phase())
    old.nonzero_qualification_state()
    return old, widen_field(old)


def test_function_preserving_width_and_rng():
    old, wide = pair()
    same = widen_field(old)
    assert sum(p.numel() for p in old.parameters()) == 9072
    assert sum(p.numel() for p in wide.parameters()) == 19200
    assert sum(p.numel() for p in hidden_parameters(wide)) == 3360
    assert all(v.equal(same.state_dict()[k]) for k, v in wide.state_dict().items())
    x = torch.randn(51, 3, dtype=torch.float64)
    assert (
        torch.linalg.vector_norm(old(x) - wide(x)) / torch.linalg.vector_norm(old(x))
        < 1e-12
    )
    for source, target in zip(old.cores, wide.cores, strict=True):
        assert source[0].weight.equal(target[0].weight[:16])
        assert source[2].weight.equal(target[2].weight[:16, :16])
        assert source[4].weight.equal(target[4].weight[:, :16])
        assert torch.count_nonzero(target[2].weight[:16, 16:]) == 0
        assert torch.count_nonzero(target[4].weight[:, 16:]) == 0


@pytest.mark.parametrize("axis", [0, 1, 2])
@pytest.mark.parametrize("direction", ["complex", "imaginary", "bias"])
def test_wide_complete_three_family_moments_and_adjoint(axis, direction):
    old, wide = pair()
    p = fixture(True, False)
    raw = StreamingMomentMap(p)
    mapping = FactoredMomentMap(p)
    c = mapping.forward(wide)
    assert (
        relative_pair(c, raw.forward(IndependentPointPhase(wide)))["relative"] < 1e-10
    )
    assert relative_pair(c, mapping.forward(old))["relative"] < 1e-10
    op = ConditionalCoreAction(
        wide, mapping, TinyAction(np.eye(6, dtype=complex)), axis
    )
    rng = np.random.default_rng(4231)
    d = (rng.normal(size=op.shape) + 1j * rng.normal(size=op.shape)).astype(complex)
    if direction == "imaginary":
        d = 1j * d.imag
    if direction == "bias":
        d[:-1] = 0
    d /= np.linalg.norm(d)
    v = (rng.normal(size=6) + 1j * rng.normal(size=6)).astype(complex)
    kd, kh = op.K(d.ravel()), op.KH(v)
    assert abs(np.vdot(kd, v) - np.vdot(d.ravel(), kh)) < 1e-10 * max(
        1, abs(np.vdot(kd, v))
    )
    coeff = output_coefficients(wide, axis)
    set_output_coefficients(wide, axis, coeff + d)
    assert (
        relative_pair(raw.forward(IndependentPointPhase(wide)), c + kd)["relative"]
        < 1e-10
    )
    with pytest.raises(ValueError, match="VERSION_CHANGED"):
        op.K(d.ravel())
    set_output_coefficients(wide, axis, coeff)
    mapping.invalidate()
    assert output_coefficients(wide, axis).shape[0] == 33


def test_new_output_direction_activates_hidden_and_restore(tmp_path):
    _, wide = pair()
    p = fixture()
    m = FactoredMomentMap(p)
    base = deepcopy(wide.state_dict())
    position = {"round": 8, "phase": "core"}
    boundary = CoreBoundary(position)
    state = capture(wide, boundary, {"reference_used_for_training": False})
    identity = model_identity(wide)
    rng = np.random.default_rng(4)
    for axis in range(3):
        op = ConditionalCoreAction(wide, m, TinyAction(np.eye(6, dtype=complex)), axis)
        d = np.zeros(op.shape, complex)
        d[16:32] = rng.normal(size=d[16:32].shape) + 1j * rng.normal(
            size=d[16:32].shape
        )
        assert np.linalg.norm(op.K(d.ravel())) > 0
        coeff = output_coefficients(wide, axis)
        set_output_coefficients(wide, axis, coeff + 1e-3 * d)
    m.vjp(wide, np.ones(6, complex))
    assert sum(float((p.grad[16:] ** 2).sum()) for p in hidden_parameters(wide)) > 0
    path = tmp_path / "state.pt"
    atomic_write(path, lambda f: torch.save(state, f))
    restore(wide, boundary, load_checkpoint(path, digest(path)))
    assert model_identity(wide) == identity and all(
        v.equal(wide.state_dict()[k]) for k, v in base.items()
    )
    m.invalidate()
    m.forward(wide)


class MatrixOperator:
    def __init__(self, B):
        self.matrix = B
        self.size = B.shape[1]
        self.deadline = monotonic() + 300
        self.counts = {"B": 0, "BH": 0}
        self.costs = {"B": 0.0, "BH": 0.0}

    def B(self, x):
        self.counts["B"] += 1
        return self.matrix @ x

    def BH(self, x):
        self.counts["BH"] += 1
        return self.matrix.conj().T @ x

    def operator(self):
        return LinearOperator(
            self.matrix.shape, matvec=self.B, rmatvec=self.BH, dtype=complex
        )


@pytest.mark.parametrize("case", ["complex", "duplicate", "pureimag", "scaled"])
def test_two_stage_matches_independent_small_svd(case):
    rng = np.random.default_rng(77)
    B = rng.normal(size=(17, 6)) + 1j * rng.normal(size=(17, 6))
    if case == "duplicate":
        B[:, -1] = B[:, 0]
    if case == "pureimag":
        B = 1j * B.real
    if case == "scaled":
        B *= np.logspace(-2, 2, 6)
    b = rng.normal(size=17) + 1j * rng.normal(size=17)
    op = MatrixOperator(B)
    saved = []
    x, record = solve_refined(
        op, b, iteration_allowance=1200, persist_first=lambda *args: saved.append(args)
    )
    exact = np.linalg.lstsq(B, b, rcond=1e-12)[0]
    # Prescribed finite LSMR tolerances do not guarantee coefficient equality
    # on differently scaled columns. Pair the actual LS objective with SVD,
    # and independently bound the forward discrepancy by the true adjoint.
    residual = b - B @ x
    exact_residual = b - B @ exact
    assert (
        abs(np.linalg.norm(residual) - np.linalg.norm(exact_residual))
        / np.linalg.norm(b)
        < 1e-10
    )
    singular = np.linalg.svd(B, compute_uv=False)
    sigma = min(v for v in singular if v > singular[0] * 1e-12)
    assert (
        np.linalg.norm(B @ x - B @ exact)
        <= np.linalg.norm(B.conj().T @ residual) / sigma + 1e-10
    )
    assert len(saved) == 1 and record["iterations"] <= 1200
    # Reopen a saved first increment, then apply once to the original base.
    d, first, _ = saved[0]
    y, reopened = solve_refined(
        MatrixOperator(B),
        b,
        iteration_allowance=1200,
        persist_first=lambda *_: pytest.fail("replayed first"),
        resume_first=(d, first),
    )
    assert (
        abs(np.linalg.norm(b - B @ y) - np.linalg.norm(exact_residual))
        / np.linalg.norm(b)
        < 1e-10
    )
    assert reopened["first_segment_reused"]
    with pytest.raises(ValueError, match="BASE_MISMATCH"):
        solve_refined(
            MatrixOperator(B),
            b + 2,
            iteration_allowance=1200,
            persist_first=lambda *_: None,
            resume_first=(d, first),
        )


def test_refinement_stationarity_budget_and_interrupt(monkeypatch):
    import src.solvers.ftt_core_refinement as module
    from src.solvers.ftt_conditional_core import CoreBudgetStop

    op = MatrixOperator(np.eye(3, dtype=complex))
    b = np.zeros(3, complex)
    x, row = solve_refined(
        op, b, iteration_allowance=1200, persist_first=lambda *_: None
    )
    assert (
        row["initial_adjoint_strict_zero"]
        and row["true_adjoint_residual_relative"] is None
    )
    original = module.segment
    calls = []

    def segment(op, b, limit, tol):
        calls.append(limit)
        if len(calls) == 2:
            raise CoreBudgetStop("injected second segment interruption")
        delta, row, residual = original(op, b, limit, tol)
        row["stop_code"] = 7
        return delta, row, residual

    monkeypatch.setattr(module, "segment", segment)
    x, row = solve_refined(
        MatrixOperator(np.eye(3, dtype=complex)),
        np.ones(3, complex),
        iteration_allowance=1200,
        persist_first=lambda *_: None,
    )
    assert (
        row["charged_unretained_iterations"] == 900
        and row["chosen_increment"] == "first"
    )
    assert np.linalg.norm(x - np.ones(3)) < 1e-10
    op = MatrixOperator(np.eye(3, dtype=complex))
    op.deadline = monotonic() + 10
    calls.clear()
    x, row = solve_refined(
        op, np.ones(3, complex), iteration_allowance=1200, persist_first=lambda *_: None
    )
    assert (
        row["refinement_reason"] == "REFINEMENT_DEFERRED_BY_BUDGET" and len(calls) == 1
    )


def test_width_policy_does_not_early_stop_and_extra_is_fixed():
    from src.test.test_ftt_core_continuation import scalar

    p = width_policy(True)
    assert width_trend(10, scalar(0.4, 0.12), p)["allowed"]
    assert not width_trend(12, scalar(0.4, 0.12), p)["allowed"]
    assert not strong_width_signal(
        scalar(0.3, 0.1), scalar(0.4, 0.12), all_three_complete=True, joint_pass=False
    )["allowed"]
    assert strong_width_signal(
        scalar(0.005, 0.005),
        scalar(0.4, 0.12),
        all_three_complete=True,
        joint_pass=False,
    )["allowed"]
    assert not strong_width_signal(
        scalar(0.005, 0.005),
        scalar(0.4, 0.12),
        all_three_complete=False,
        joint_pass=False,
    )["allowed"]


def test_width_schema_and_label_firewall(tmp_path, monkeypatch):
    from src.io import ftt_width_campaign as io
    from src.io.input_loader import InputError
    from src.runners.ftt_worker import training_allowed

    d = json.loads(io.DESIGN.read_text())
    p = tmp_path / "design.json"
    p.write_text(json.dumps(d))
    monkeypatch.setattr(io, "DESIGN", p)
    path = io.ROOT / "input/task042extra_feinn_5nm/v44_width_and_inner_checks.dat"
    data = dict(
        schema_version=14,
        neural_wave=dict(stage="v44_width_and_inner_checks", design_sha256=digest(p)),
    )
    assert io.load_width(path, data, b"fixture")["campaign_version"] == 44
    data["neural_wave"]["reference_state"] = "bad"
    with pytest.raises(InputError, match="LABEL"):
        io.load_width(path, data, b"fixture")
    del data["neural_wave"]["reference_state"]
    d["core_refinement"]["second"]["maxiter"] = 901
    p.write_text(json.dumps(d))
    data["neural_wave"]["design_sha256"] = digest(p)
    with pytest.raises(InputError, match="POLICY"):
        io.load_width(path, data, b"fixture")
    active = io.ROOT / "benchmarks/artifacts/task42extra/v44/test"
    assert training_allowed(io.ROOT / d["parent_checkpoint"]["path"], d, active, False)
    assert not training_allowed(io.ROOT / d["reference"]["path"], d, active, False)


def test_saved_comparison_uses_all_three_and_preserves_original_wall(
    tmp_path, monkeypatch
):
    import src.runners.ftt_width_worker as worker
    from src.io.ftt_width_campaign import routes

    monkeypatch.setattr(worker, "ROOT", tmp_path)
    monkeypatch.setattr(worker, "ART", tmp_path / "source")
    monkeypatch.setattr(
        worker, "compare_common_wall", lambda *_: dict(selection_uses_reference=False)
    )
    artifact = tmp_path / "compare"
    artifact.mkdir()
    records = {}
    for stage, role in routes():
        folder = tmp_path / "source" / stage
        folder.mkdir(parents=True)
        (folder / "result.json").write_text(
            json.dumps(
                dict(position=dict(complete_rounds=12), checkpoint=dict(sha256=role))
            )
        )
        records[role] = dict(
            equation_audit=dict(native_relative=0.4, augmented_relative=0.4),
            field_errors=dict(
                scattered_E=dict(relative=0.12), scattered_H_code=dict(relative=0.12)
            ),
            m5_full_discrete_numerical_gate=False,
        )
    (artifact / "saved_checker.json").write_text(json.dumps(dict(records=records)))
    result = worker.comparison_decision({}, artifact, lambda *_: None, tmp_path)
    assert not result["extra_round_decision"]["allowed"]
    assert result["extra_round_decision"]["inherited_route_wall_not_reset"]
    assert len(result["extra_round_decision"]["checkpoints"]) == 3


def test_saved_width_participation_uses_actual_masks_and_retained_gradient():
    from src.postprocessing.ftt_common_wall import saved_width_participation

    _, wide = pair()
    hidden_ids = {id(p) for p in hidden_parameters(wide)}
    keys = [name for name, p in wide.named_parameters() if id(p) in hidden_ids]
    initial = capture(wide, CoreBoundary({}), {})
    final = deepcopy(initial)
    final["model"]["cores.0.4.weight"][:, 16:] = 1e-3
    final["model"]["cores.0.2.weight"][0, 16] += 2e-3
    final["model"]["cores.0.2.weight"][0, 0] += 3e-3
    final["gradients"] = [torch.zeros_like(p) for p in wide.parameters()]
    names = [row["name"] for row in final["parameter_order"]]
    final["gradients"][names.index("cores.0.2.weight")][0, 16] = 4e-3
    row = saved_width_participation(initial, final, keys)
    assert row["old_hidden_real_parameters"] == 912
    assert row["new_hidden_real_parameters"] == 2448
    x = row["axes"]["x"]
    assert x["new_hidden_real_parameters"] == 816
    assert x["new_output_weight_change_norm"] > 0
    assert x["new_hidden_change_norm"] == pytest.approx(2e-3)
    assert x["old_hidden_change_norm"] == pytest.approx(3e-3)
    assert x["retained_new_hidden_gradient_norm"] == pytest.approx(4e-3)
    final["gradients"] = [None] * len(names)
    assert saved_width_participation(initial, final, keys)["axes"]["x"][
        "gradient_status"
    ] == "NOT_RETAINED"
    final["parameter_order"] = final["parameter_order"][::-1]
    with pytest.raises(ValueError, match="PARAMETER_ORDER"):
        saved_width_participation(initial, final, keys)


def test_saved_fork_inventory_and_bitwise_claims(tmp_path, monkeypatch):
    from src.postprocessing import ftt_common_wall as audit
    from src.runners import ftt_bloch_worker
    from src.io.ftt_width_campaign import routes

    old, _ = pair()
    design = dict(campaign_version=44, parent_checkpoint={})
    parent = capture(old, CoreBoundary({}), {})
    parent.update(c=np.ones(6, complex), r=np.ones(6, complex))
    parent_path = tmp_path / "parent.pt"
    atomic_write(parent_path, lambda stream: torch.save(parent, stream))
    design["parent_checkpoint"] = dict(path="parent.pt", sha256=digest(parent_path))
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    monkeypatch.setattr(
        ftt_bloch_worker,
        "field_factory",
        lambda *_: BlochFTTField(BOX, "fttnn", phase()),
    )
    root = tmp_path / "source"
    for stage, route in routes():
        model = old if route.startswith("W16") else widen_field(old)
        initial = capture(model, CoreBoundary({}), {})
        for key in ("torch_rng", "numpy_rng", "python_rng"):
            initial[key] = deepcopy(parent[key])
        initial.update(c=parent["c"].copy(), r=parent["r"].copy())
        initial["c"][0] += 1e-13
        initial["metadata"].update(
            hidden_width=model.hidden_width,
            hidden_real_parameters=sum(p.numel() for p in hidden_parameters(model)),
            inherited_state=dict(inherited_counts={}),
            new_counts={},
        )
        folder = root / stage / "checkpoints"
        folder.mkdir(parents=True)
        entries = []
        for name in ("initial.pt", "final.pt"):
            path = folder / name
            atomic_write(path, lambda stream: torch.save(initial, stream))
            entries.append(dict(name=name, sha256=digest(path)))
        (folder.parent / "checkpoint_index.json").write_text(json.dumps(entries))
        (folder.parent / "result.json").write_text(
            json.dumps(dict(checkpoint=entries[-1]))
        )
    output = audit.initialize_output(tmp_path / "audit")
    audit.audit_saved_forks(output, root, design)
    record = json.loads((output / "initial_and_final_forks.json").read_text())
    assert set(record["hidden_real_parameter_counts"].values()) == {912, 3360}
    for route, row in record["records"].items():
        assert row["all_initial_model_buffers_equal_function_preserving_import"]
        assert not row["initial_c_r_bitwise_equal_parent"]
        assert row["initial_c_r_pair"]["c"]["relative"] < 1e-10
        if route.startswith("W32"):
            assert row["actual_real_parameter_count"] == 19200
            assert not row["initial_architecture_equals_parent"]
            assert row["expanded_parameter_participation"]["new_hidden_real_parameters"] == 2448
    frozen = root / "v44_w32_refined_frozen" / "checkpoints" / "final.pt"
    state = load_checkpoint(frozen, digest(frozen))
    state["model"]["cores.0.0.weight"][20, 0] += 1e-3
    atomic_write(frozen, lambda stream: torch.save(state, stream))
    rfile = frozen.parent.parent / "result.json"
    result = json.loads(rfile.read_text())
    result["checkpoint"]["sha256"] = digest(frozen)
    rfile.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="FREEZE_HIDDEN_CHANGED"):
        audit.audit_saved_forks(output, root, design)
