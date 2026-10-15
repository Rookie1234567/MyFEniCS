"""Only new full-parameter tangent witnesses on the actual frozen M5 parent."""

from copy import deepcopy
import random
from time import monotonic
import numpy as np
import torch
from src.solvers.ftt_joint_io import load_joint_parent, verify_joint_boundary
from src.solvers.ftt_joint_tangent import (
    ParameterLayout,
    JointTangent,
    ModelTransaction,
)
from src.solvers.ftt_joint_training import independent_coefficients
from src.solvers.ftt_factored_moments import FactoredMomentMap, model_identity
from src.solvers.ftt_moments import StreamingMomentMap
from src.solvers.ftt_bloch_field import IndependentPointPhase
from src.solvers.ftt_conditional_core import (
    ConditionalCoreAction,
    output_coefficients,
    relative_pair,
)
from src.solvers.feinn_native import ResidualMetric
from src.solvers.joint_least_squares import power_scale, realify, JointLMState
from src.solvers.optimization_checkpoint import atomic_write, capture
from src.solvers.neural_wave_greedy import atomic_npz


def qualify_joint(action, packet, design, marker, deadline, artifact):
    began = monotonic()
    mapping = FactoredMomentMap(packet)
    model, view, context, parent, pairs = load_joint_parent(design, action, mapping)
    layout = ParameterLayout(model)
    theta = layout.theta()
    initial = deepcopy(model.state_dict())
    base_hash = context.base_hash
    raw = StreamingMomentMap(packet)
    rng = np.random.default_rng(4214701)
    directions = []
    timings = {}
    for kind in ("hidden", "output", "mixed"):
        v = rng.normal(size=layout.size)
        if kind == "hidden":
            v[~layout.hidden] = 0
        elif kind == "output":
            v[layout.hidden] = 0
        v /= np.linalg.norm(v)
        op = JointTangent(
            model, mapping, view, layout, deadline=deadline - 120, marker=marker
        )
        t = monotonic()
        dc = op.moment_jvp(v)
        jv = realify(view.apply(dc) / view.bnorm)
        timings["JVP"] = monotonic() - t
        if np.linalg.norm(dc) == 0:
            raise ValueError("JOINT_ACTUAL_PARENT_NONZERO_DIRECTION_DEAD")
        fd = []
        for eps in (1e-4, 1e-5):
            observed = []
            try:
                for sign in (1, -1):
                    layout.set_theta(theta + sign * eps * layout.expand(v))
                    mapping.invalidate()
                    observed.append(independent_coefficients(model, raw))
            finally:
                layout.set_theta(theta)
                mapping.invalidate()
            numeric = (observed[0] - observed[1]) / (2 * eps)
            fd.append(dict(epsilon=eps, **relative_pair(dc, numeric)))
        u = rng.normal(size=2 * action.size)
        t = monotonic()
        pulled = op.vjp(u)
        timings["VJP"] = monotonic() - t
        lhs = float(jv @ u)
        rhs = float(v @ pulled)
        adj = abs(lhs - rhs) / max(abs(lhs), abs(rhs), 1e-30)
        if min(x["relative"] for x in fd) > 1e-5 or adj > 1e-10:
            raise ValueError("JOINT_ACTUAL_OLD_POINT_FD_OR_REAL_ADJOINT_FAILED:" + kind)
        directions.append(
            dict(
                kind=kind,
                moment_direction_norm=float(np.linalg.norm(dc)),
                J_direction_norm=float(np.linalg.norm(jv)),
                FD=fd,
                real_adjoint_relative=adj,
                lhs_real_pairing=lhs,
                rhs_real_pairing=rhs,
            )
        )
        marker("joint_actual_direction_qualified", directions[-1])
    single = []
    for axis in range(3):
        full = np.zeros(layout.full_size)
        for name, p in layout.parameters:
            if name.startswith(f"cores.{axis}.4."):
                full[layout.slices[name]] = rng.normal(size=p.numel())
        full /= np.linalg.norm(full)
        v = full / layout.scales
        before = output_coefficients(model, axis)
        layout.set_theta(theta + full)
        after = output_coefficients(model, axis)
        layout.set_theta(theta)
        mapping.invalidate()
        op = JointTangent(model, mapping, view, layout, deadline=deadline - 120)
        old = ConditionalCoreAction(model, mapping, view, axis, deadline=deadline - 120)
        pair = relative_pair(op.moment_jvp(v), old.K(after - before))
        if pair["relative"] > 1e-10:
            raise ValueError("JOINT_SINGLE_OUTPUT_OLD_K_PAIR_FAILED")
        single.append(dict(axis=axis, **pair))
    metric = ResidualMetric(view)
    c = mapping.forward(model)
    loss, r, dual = metric.value(c, gradient=True)
    op = JointTangent(model, mapping, view, layout, deadline=deadline - 120)
    actual = op.vjp(realify(r / view.bnorm))
    point_model = IndependentPointPhase(model)
    original_gradient = raw.vjp(point_model, dual)
    gradient_pair = relative_pair(actual, layout.pullback(original_gradient))
    del point_model
    if gradient_pair["relative"] > 1e-9:
        raise ValueError("JOINT_OLD_COMPLETE_POINT_GRADIENT_PAIR_FAILED")
    model.zero_grad(set_to_none=True)
    h, spectrum = power_scale(op.operator())
    if not np.isfinite(h) or h <= 0:
        raise ValueError("JOINT_PARENT_TANGENT_INDEPENDENT_STAGNATION")
    atomic_npz(
        artifact / "parent_parameter_scales.npz", S=layout.scales, mask=layout.mask
    )
    state = capture(model, JointLMState(h), {})
    state.update(
        c=c.copy(),
        r=r.copy(),
        **context.checkpoint_fields(c, r),
        joint_layout=deepcopy(layout.binding),
        parameter_scales=layout.scales.copy(),
        parameter_mask=layout.mask.copy(),
        joint_h=h,
        joint_parent_sha256=design["parent_checkpoint"]["sha256"],
    )
    negatives = []
    for wrong in (
        "parameter_scales",
        "parameter_mask",
        "joint_h",
        "joint_parent_sha256",
        "g",
        "base_model",
        "model",
    ):
        bad = deepcopy(state)
        if wrong == "parameter_scales":
            bad[wrong][0] += 1
        elif wrong == "parameter_mask":
            bad[wrong][0] = False
        elif wrong == "joint_h":
            bad[wrong] *= 2
        elif wrong == "joint_parent_sha256":
            bad[wrong] = "wrong"
        elif wrong == "g":
            bad[wrong][0] += 0.1
        elif wrong == "base_model":
            bad[wrong]["center"][0] += 0.1
        elif wrong == "model":
            bad[wrong]["phase_wavevector"][0] += 0.1
        try:
            verify_joint_boundary(bad, context, layout, h, design["parent_checkpoint"])
        except ValueError:
            negatives.append(dict(kind=wrong, rejected=True))
        else:
            raise ValueError("JOINT_PARTIAL_RECOVERY_NEGATIVE_NOT_REJECTED:" + wrong)
    transaction = ModelTransaction(model, mapping)
    t = monotonic()
    try:
        layout.set_theta(theta + 1e-5 * layout.expand(v))
        mapping.invalidate()
        trial = mapping.forward(model)
        trial_r = view.apply(trial) - view.f
        point = independent_coefficients(model, raw)
        trial_pair = relative_pair(trial, point)
        if trial_pair["relative"] > 1e-10:
            raise ValueError("JOINT_NONLINEAR_TRIAL_ACTUAL_MAPPING_FAILED")
        timings["actual_trial"] = monotonic() - t
        t = monotonic()
        trial_state = capture(model, JointLMState(h), {})
        trial_state.update(
            c=trial, r=trial_r, **context.checkpoint_fields(trial, trial_r)
        )
        atomic_write(
            artifact / "qualification_trial.pt", lambda f: torch.save(trial_state, f)
        )
        timings["save"] = monotonic() - t
    finally:
        transaction.restore()
    if (
        model_identity(model) != design["parent_checkpoint"]["model_hash"]
        or model_identity(context.base) != base_hash
    ):
        raise ValueError("JOINT_PARENT_OR_BASE_NOT_RESTORED_AFTER_QUALIFICATION")
    if not all(v.equal(initial[k]) for k, v in model.state_dict().items()):
        raise ValueError("JOINT_PARENT_OR_PHASE_BUFFERS_CHANGED")
    context.check_base()
    torch.set_rng_state(parent["torch_rng"])
    np.random.set_state(parent["numpy_rng"])
    random.setstate(parent["python_rng"])
    return dict(
        qualified=True,
        models=dict(fttnn=dict(qualified=True)),
        parent=design["parent_checkpoint"],
        parent_restore_pairs=pairs,
        three_nonzero_directions=directions,
        single_axis_old_K=single,
        original_complete_point_gradient=gradient_pair,
        restore_negative_controls=negatives,
        h=h,
        power_estimate=spectrum,
        scales_sha256=layout.binding["scale_sha256"],
        scale_binding=layout.binding,
        timings=timings,
        representative_JVP_VJP_trial_save_sum_s=sum(timings.values()),
        complete_qualification_elapsed_s=monotonic() - began,
        actual_trial_independent_mapping=trial_pair,
        synthetic_trial_not_used_as_initial_state=True,
        whole_grid_AD_graph=False,
        explicit_J_or_normal_matrix=False,
        base_frozen=True,
        parent_restored_bitwise=True,
        reference_read=False,
        new_global_factors=0,
    )
