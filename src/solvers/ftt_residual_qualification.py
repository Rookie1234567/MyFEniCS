"""Bounded nonzero residual-branch witnesses on the real M5, without labels."""

from copy import deepcopy
from time import monotonic
import numpy as np
import torch

from src.solvers.ftt_residual_branch import (
    ResidualTrainingAction,
    frozen_base_and_zero_correction,
    independent_sum_field,
)
from src.solvers.ftt_residual_io import read_base, save_prepared
from src.solvers.ftt_factored_moments import FactoredMomentMap, model_identity
from src.solvers.ftt_moments import StreamingMomentMap
from src.solvers.ftt_conditional_core import (
    ConditionalCoreAction,
    DirectionField,
    relative_pair,
)


def qualify_residual(action, packet, design, marker, deadline, artifact):
    began = monotonic()
    base, old, prefix = read_base(design)
    mapping = FactoredMomentMap(packet, point_batch=512)
    c_base = mapping.forward(base)
    view = ResidualTrainingAction(action, c_base)
    pair = dict(c=relative_pair(c_base, old["c"]), r=relative_pair(-view.f, old["r"]))
    if max(v["relative"] for v in pair.values()) > 1e-10:
        raise ValueError("RESIDUAL_BASE_OLD_FIELD_OR_R_PAIR_FAILED")
    correction = frozen_base_and_zero_correction(base)
    zero = mapping.forward(correction)
    if np.any(zero):
        raise ValueError("RESIDUAL_INITIAL_CORRECTION_NOT_STRICT_ZERO")
    zero_cache_key = mapping.cache_key
    cache_base = mapping.forward(base)
    cache_base_pair = relative_pair(cache_base, c_base)
    mapping.forward(correction)
    cache_bound = (
        zero_cache_key == model_identity(correction)
        and zero_cache_key != model_identity(base)
        and mapping.cache_key == zero_cache_key
        and cache_base_pair["relative"] <= 1e-10
    )
    if not cache_bound:
        raise ValueError("RESIDUAL_BASE_AND_CORRECTION_CACHE_BINDING_FAILED")
    initial, base_hash = deepcopy(correction.state_dict()), model_identity(base)
    raw = StreamingMomentMap(packet)
    summed = raw.forward(independent_sum_field(base, correction))
    initial_pair = relative_pair(summed, c_base)
    if initial_pair["relative"] > 1e-10:
        raise ValueError("RESIDUAL_INITIAL_INDEPENDENT_TWO_POINT_FIELDS_FAILED")
    rng = np.random.default_rng(design["qualification_seed"])
    op = ConditionalCoreAction(correction, mapping, view, 2, deadline=deadline)
    direction = (rng.normal(size=op.shape) + 1j * rng.normal(size=op.shape)).astype(
        np.complex128
    )
    direction /= np.linalg.norm(direction)
    z_direction = op.K(direction)
    if np.linalg.norm(z_direction) == 0:
        raise ValueError("RESIDUAL_ZERO_START_FIRST_Z_DIRECTION_DEAD")
    correction.nonzero_qualification_state(seed=4214602)
    mapping.invalidate()
    saved = deepcopy(correction.state_dict())
    c_delta = mapping.forward(correction)
    fields = view.fields(c_delta, view.apply(c_delta) - view.f)
    together = raw.forward(independent_sum_field(base, correction))
    together_pair = relative_pair(together, fields["c_combined"])
    if together_pair["relative"] > 1e-10:
        raise ValueError("RESIDUAL_NONZERO_INDEPENDENT_POINT_SUM_FAILED")
    norm_identity = abs(
        np.linalg.norm(fields["r_original"]) / action.bnorm
        - view.bnorm
        / action.bnorm
        * np.linalg.norm(view.apply(c_delta) - view.f)
        / view.bnorm
    )
    alpha = action.alpha(fields["c_combined"])
    linear_alpha = action.alpha(c_base) + action.port_solve(action.D(c_delta))
    port_pair = relative_pair(alpha, linear_alpha)
    duplicated = relative_pair(
        action.a["background_alpha"] + alpha,
        2 * action.a["background_alpha"] + action.alpha(c_base) + action.alpha(c_delta),
    )
    if (
        norm_identity > 1e-10
        or port_pair["relative"] > 1e-10
        or duplicated["relative"] < 1e-10
    ):
        raise ValueError(
            "RESIDUAL_NORM_OR_NONZERO_BACKGROUND_PORT_NEGATIVE_CONTROL_FAILED"
        )
    witnesses = []
    for axis in range(3):
        op = ConditionalCoreAction(correction, mapping, view, axis, deadline=deadline)
        for kind in (
            "complex_three_components",
            "pure_imaginary",
            "bias_three_components",
        ):
            d = (rng.normal(size=op.shape) + 1j * rng.normal(size=op.shape)).astype(
                np.complex128
            )
            if kind == "pure_imaginary":
                d = 1j * d.imag
            if kind == "bias_three_components":
                d[:-1] = 0
            d /= np.linalg.norm(d)
            dual = (
                rng.normal(size=action.size) + 1j * rng.normal(size=action.size)
            ).astype(np.complex128)
            k = op.K(d)
            kh = op.KH(dual)
            lhs, rhs = np.vdot(k, dual), np.vdot(d.ravel(), kh)
            adj = abs(lhs - rhs) / max(abs(lhs), abs(rhs), 1e-30)
            point = raw.forward(DirectionField(correction, axis, d))
            point_pair = relative_pair(k, point)
            action_pair = relative_pair(action.apply(k), action.apply(point))
            mpc_pair = relative_pair(action.expand(k), action.expand(point))
            if (
                max(
                    adj,
                    point_pair["relative"],
                    action_pair["relative"],
                    mpc_pair["relative"],
                )
                > 1e-10
            ):
                raise ValueError(
                    "RESIDUAL_REAL_THREE_AXIS_COMPLEX_ADJOINT_OR_POINT_K_FAILED"
                )
            witnesses.append(
                dict(
                    axis=axis,
                    kind=kind,
                    adjoint_relative=float(adj),
                    point_pair=point_pair,
                    original_action_pair=action_pair,
                    original_MPC_expansion_pair=mpc_pair,
                )
            )
    r = view.apply(c_delta) - view.f
    mapping.vjp(correction, view.apply(r, adjoint=True) / view.bnorm**2)
    fd = []
    for axis in range(3):
        p = correction.cores[axis][0].bias
        direction = torch.from_numpy(rng.normal(size=p.shape))
        direction /= torch.linalg.vector_norm(direction)
        analytic = float(torch.dot(p.grad, direction))
        steps = []
        for h in (1e-4, 1e-5, 1e-6):
            values = []
            for sign in (1, -1):
                correction.load_state_dict(saved)
                with torch.no_grad():
                    p.add_(sign * h * direction)
                mapping.invalidate()
                trial = view.apply(mapping.forward(correction)) - view.f
                values.append(float(np.vdot(trial, trial).real / (2 * view.bnorm**2)))
            numeric = (values[0] - values[1]) / (2 * h)
            steps.append(
                dict(
                    h=h,
                    analytic=analytic,
                    numeric=numeric,
                    relative=abs(analytic - numeric)
                    / max(abs(analytic), abs(numeric), 1e-30),
                )
            )
        if analytic == 0 or min(v["relative"] for v in steps) > 1e-5:
            raise ValueError("RESIDUAL_NONZERO_NEW_HIDDEN_LOSS_FD_FAILED")
        fd.append(dict(axis=axis, steps=steps))
    correction.load_state_dict(initial)
    mapping.invalidate()
    if model_identity(base) != base_hash or np.any(mapping.forward(correction)):
        raise ValueError("RESIDUAL_QUALIFICATION_ZERO_RESTORE_OR_BASE_POLLUTED")
    import random

    torch.set_rng_state(old["torch_rng"])
    np.random.set_state(old["numpy_rng"])
    random.setstate(old["python_rng"])
    prepared = save_prepared(design, artifact, base, correction, view, prefix, old)
    record = dict(
        qualified=True,
        models={"fttnn": dict(qualified=True)},
        base_field_pair=pair,
        prepared_branch=prepared,
        initial_sum_pair=initial_pair,
        nonzero_sum_pair=together_pair,
        first_z_direction_norm=float(np.linalg.norm(z_direction)),
        norm_identity_absolute=float(norm_identity),
        branch_parameter_cache_bound=cache_bound,
        base_cache_pair=cache_base_pair,
        port_affine_pair=port_pair,
        duplicate_background_port_negative_control=duplicated,
        actual_complex_three_axis_witnesses=witnesses,
        nonzero_hidden_FD=fd,
        original_base_equation=action.audit(c_base),
        native_action_counts=action.counts,
        seconds=monotonic() - began,
        reference_read=False,
        new_training_calls=0,
        global_Maxwell_factor_count=0,
        global_Gram_factor_count=0,
        Gsolve_count=0,
    )
    marker("residual_branch_actual_qualified", record)
    return record
