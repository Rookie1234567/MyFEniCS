"""Complete real all-parameter derivative, independent point FD and masks."""

# ruff: noqa: E402 -- retain pure environment skip before ML imports.
from copy import deepcopy
import numpy as np
import pytest

torch = pytest.importorskip("torch")
from src.test.test_ftt_structure import fixture
from src.test.test_ftt_residual_ml import fields
from src.solvers.ftt_joint_tangent import (
    ParameterLayout,
    JointTangent,
    ModelTransaction,
)
from src.solvers.ftt_factored_moments import FactoredMomentMap
from src.solvers.ftt_moments import StreamingMomentMap
from src.solvers.ftt_bloch_field import IndependentPointPhase
from src.solvers.ftt_conditional_core import ConditionalCoreAction, output_coefficients
from src.solvers.joint_least_squares import complexify


class SmallComplexAction:
    def __init__(self):
        self.A = np.diag(np.arange(1, 7)).astype(complex)
        self.A[0, 2] = 0.8j
        self.A[3, 1] = 0.4 - 0.2j
        self.size = 6
        self.bnorm = 0.73

    def apply(self, c, *, adjoint=False):
        return (self.A.conj().T if adjoint else self.A) @ c


@pytest.mark.parametrize("geometry", ["box", "permuted", "skew", "raw"])
@pytest.mark.parametrize("kind", ["hidden", "output", "mixed"])
def test_all_parameter_jvp_old_full_moments_and_real_adjoint(geometry, kind):
    _, model = fields()
    model.nonzero_qualification_state()
    p = fixture(geometry == "permuted", geometry == "skew")
    if geometry == "raw":
        p["interpolation"][0] += 0.01 * np.sin(np.arange(p["interpolation"].shape[1]))
    mapping = FactoredMomentMap(p)
    raw = StreamingMomentMap(p)
    layout = ParameterLayout(model)
    theta = layout.theta()
    op = JointTangent(model, mapping, SmallComplexAction(), layout)
    rng = np.random.default_rng(18)
    v = rng.normal(size=layout.size)
    if kind != "mixed":
        v[~layout.hidden if kind == "hidden" else layout.hidden] = 0
    v /= np.linalg.norm(v)
    analytic = op.moment_jvp(v)
    assert np.linalg.norm(analytic) > 1e-8
    numeric = []
    for sign in (1, -1):
        layout.set_theta(theta + sign * 1e-5 * layout.expand(v))
        mapping.invalidate()
        numeric.append(raw.forward(IndependentPointPhase(model)))
    layout.set_theta(theta)
    mapping.invalidate()
    np.testing.assert_allclose(
        (numeric[0] - numeric[1]) / 2e-5, analytic, rtol=1e-6, atol=1e-10
    )
    u = rng.normal(size=12)
    lhs = op.jvp(v) @ u
    rhs = v @ op.vjp(u)
    assert abs(lhs - rhs) / max(abs(lhs), abs(rhs), 1e-30) < 1e-10
    assert all(p.grad is None for p in model.parameters())
    old = raw.vjp(
        IndependentPointPhase(model),
        op.action.apply(complexify(u), adjoint=True) / op.action.bnorm,
    )
    np.testing.assert_allclose(op.vjp(u), layout.pullback(old), rtol=1e-10, atol=1e-11)


@pytest.mark.parametrize("axis", [0, 1, 2])
def test_single_output_axis_degenerates_to_old_complex_K(axis):
    _, model = fields()
    model.nonzero_qualification_state()
    mapping = FactoredMomentMap(fixture())
    layout = ParameterLayout(model, output_only=True)
    theta = layout.theta()
    full = np.zeros(layout.full_size)
    rng = np.random.default_rng(axis)
    for n, p in layout.parameters:
        if n.startswith(f"cores.{axis}.4."):
            full[layout.slices[n]] = rng.normal(size=p.numel())
    v = full[layout.mask] / layout.scales[layout.mask]
    before = output_coefficients(model, axis)
    op = JointTangent(model, mapping, SmallComplexAction(), layout)
    layout.set_theta(theta + full)
    after = output_coefficients(model, axis)
    layout.set_theta(theta)
    mapping.invalidate()
    old = ConditionalCoreAction(model, mapping, op.action, axis)
    np.testing.assert_allclose(
        op.moment_jvp(v), old.K(after - before), rtol=1e-10, atol=1e-12
    )


def test_masks_frozen_scales_rejection_buffers_and_cache_identity():
    base, model = fields()
    model.nonzero_qualification_state()
    mapping = FactoredMomentMap(fixture())
    all_layout = ParameterLayout(model)
    output = ParameterLayout(model, scales=all_layout.scales, output_only=True)
    assert (
        all_layout.size == 19200
        and output.size == 15840
        and output.hidden.sum() == 3360
    )
    np.testing.assert_array_equal(output.scales, all_layout.scales)
    theta = output.theta()
    old = mapping.forward(model)
    old_base = deepcopy(base.state_dict())
    op = JointTangent(model, mapping, SmallComplexAction(), output)
    transaction = ModelTransaction(model, mapping)
    step = output.expand(np.ones(output.size) * 1e-4)
    assert not np.any(step[output.hidden])
    output.set_theta(theta + step)
    model.phase_wavevector[0] += 0.1
    with pytest.raises(ValueError, match="VERSION_CHANGED"):
        op.jvp(np.ones(output.size))
    transaction.restore()
    assert mapping.cache_key is None
    np.testing.assert_array_equal(output.theta(), theta)
    np.testing.assert_array_equal(mapping.forward(model), old)
    assert all(v.equal(old_base[k]) for k, v in base.state_dict().items())
    with pytest.raises(ValueError):
        ParameterLayout(model, scales=np.zeros(output.full_size))


def test_joint_probe_persists_actual_boundary_then_restores_parent(tmp_path):
    import random
    from time import monotonic
    from src.io.ftt_joint_campaign import joint_policy
    from src.solvers.ftt_joint_training import run_joint_training
    from src.solvers.ftt_residual_branch import (
        ResidualTrainingAction,
        ResidualBranchContext,
    )
    from src.solvers.ftt_factored_moments import model_identity
    from src.solvers.joint_least_squares import power_scale
    from src.solvers.optimization_checkpoint import load_checkpoint

    base, model = fields()
    model.nonzero_qualification_state()
    packet = fixture()
    mapping = FactoredMomentMap(packet)
    a = SmallComplexAction()
    a.nc, a.np = 2, 0
    a.counts, a.costs = {}, {}
    c_base = mapping.forward(base)
    c_delta = mapping.forward(model)
    a.f = a.apply(c_base + c_delta) + 1e-5 * np.arange(1, 7) * (1 + 0.3j)
    a.bnorm = float(np.linalg.norm(a.f))
    a.audit = lambda c: dict(
        native_relative=float(np.linalg.norm(a.apply(c) - a.f) / a.bnorm)
    )
    view = ResidualTrainingAction(a, c_base)
    context = ResidualBranchContext(base, view, dict(phase_sha256="b" * 64))
    context.base_RNG = dict(torch_rng=torch.get_rng_state().clone())
    parent = dict(
        model=deepcopy(model.state_dict()),
        torch_rng=torch.get_rng_state().clone(),
        numpy_rng=deepcopy(np.random.get_state()),
        python_rng=random.getstate(),
    )
    layout = ParameterLayout(model)
    h, _ = power_scale(JointTangent(model, mapping, view, layout).operator())
    parent_entry = dict(sha256="a" * 64, model_hash=model_identity(model))
    policy = joint_policy(True)
    policy.update(trial_limit=1, accepted_limit=1, total_lsmr=2)
    binding = dict(
        route="FTT_JOINT_STEP_PROBE",
        source_sha="c" * 40,
        input_sha256="d" * 64,
        design_sha256="e" * 64,
        route_origin_monotonic=monotonic(),
    )
    result = run_joint_training(
        view,
        packet,
        model,
        tmp_path,
        binding,
        monotonic() + 300,
        lambda *_: None,
        learned=True,
        residual_context=context,
        parent_state=parent,
        parent_pairs={},
        qualification=dict(
            h=h,
            scales_sha256=layout.binding["scale_sha256"],
            timings=dict(JVP=0.001, VJP=0.001),
        ),
        mapping=mapping,
        execution_policy=policy,
        parent_entry=parent_entry,
    )
    assert result["counts"]["trials"] == 1 and result["counts"]["LSMR_iterations"] <= 2
    assert result["parent_restored_bitwise_after_probe"]
    assert model_identity(model) == parent_entry["model_hash"]
    checkpoint = result["checkpoint"]
    saved = load_checkpoint(
        tmp_path / "checkpoints" / checkpoint["name"], checkpoint["sha256"]
    )
    np.testing.assert_array_equal(
        saved["c_combined"], saved["c_base"] + saved["c_delta"]
    )
    assert result["maximum_independent_actual_mapping_relative"] <= 1e-10
