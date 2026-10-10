"""Targeted actual-core qualification; finite witnesses never become initials."""

from copy import deepcopy
from time import monotonic
import numpy as np
import torch
from src.solvers.ftt_field import FTTField
from src.solvers.ftt_factored_moments import FactoredMomentMap, model_identity
from src.solvers.ftt_moments import StreamingMomentMap
from src.solvers.ftt_conditional_core import (
    ConditionalCoreAction,
    output_coefficients,
    set_output_coefficients,
    solve_core,
    verify_and_apply_core,
    relative_pair,
    hidden_parameters,
)


def actual_checks(action, packet, design, marker, deadline, *, model_factory=None, independent_field=None, work_persist=None):
    seed = design.get("qualification_seed", 4214101)
    rng = np.random.default_rng(seed)
    reports = {}
    for kind in ("fttnn", "chebtt"):
        model = FTTField(design["model"]["geometry"]["bounds_nm"], kind) if model_factory is None else model_factory(design, kind)
        model.nonzero_qualification_state(seed=seed)
        mapping = FactoredMomentMap(packet)
        old = StreamingMomentMap(packet)
        c = mapping.forward(model)
        base = deepcopy(model.state_dict())
        def point_field():
            return model if independent_field is None else independent_field(model)

        initial_pair = relative_pair(c, old.forward(point_field()))
        rows = []
        for axis in range(3):
            axis_began = monotonic()
            op = ConditionalCoreAction(
                model, mapping, action, axis, deadline=deadline - 120, marker=marker
            )
            d = (rng.normal(size=op.size) + 1j * rng.normal(size=op.size)).astype(
                np.complex128
            )
            d /= np.linalg.norm(d)
            v = (
                rng.normal(size=action.size) + 1j * rng.normal(size=action.size)
            ).astype(np.complex128)
            kd = op.K(d)
            kh = op.KH(v)
            lhs = np.vdot(kd, v)
            rhs = np.vdot(d, kh)
            adj = abs(lhs - rhs) / max(abs(lhs), abs(rhs), 1e-30)
            B = op.B(d)
            BH = op.BH(v)
            lhsB = np.vdot(B, v)
            rhsB = np.vdot(d, BH)
            badj = abs(lhsB - rhsB) / max(abs(lhsB), abs(rhsB), 1e-30)
            coeff = output_coefficients(model, axis)
            set_output_coefficients(model, axis, coeff + d.reshape(coeff.shape))
            mapping.invalidate()
            updated = mapping.forward(model)
            linear = relative_pair(c + kd, updated)
            independent = relative_pair(updated, old.forward(point_field()))
            model.load_state_dict(base)
            mapping.invalidate()
            pure = 1j * d.real
            kp = op.K(pure)
            set_output_coefficients(model, axis, coeff + pure.reshape(coeff.shape))
            mapping.invalidate()
            imaginary = relative_pair(c + kp, mapping.forward(model))
            model.load_state_dict(base)
            mapping.invalidate()
            bias = np.zeros(op.shape, dtype=np.complex128)
            bias[-1 if kind == "fttnn" else 0, :, :, :] = 0.001 + 0.002j
            kb = op.K(bias.ravel())
            set_output_coefficients(model, axis, coeff + bias)
            mapping.invalidate()
            biaspair = relative_pair(c + kb, mapping.forward(model))
            model.load_state_dict(base)
            mapping.invalidate()
            b = (action.f - action.apply(c)) / action.bnorm
            delta, inner = solve_core(op, b, maxiter=3)
            updated_c, updated_r, acceptance = verify_and_apply_core(
                model, mapping, action, op, delta, c
            )
            saved_work = None if work_persist is None else work_persist(kind, axis, model, updated_c, updated_r)
            model.load_state_dict(base)
            mapping.invalidate()
            row = dict(
                axis=axis,
                K_adjoint_relative=float(adj),
                B_adjoint_relative=float(badj),
                complex_linearity=linear,
                pure_imaginary_linearity=imaginary,
                bias_all_components_linearity=biaspair,
                independent_old_point_mapping=independent,
                short_inner=inner,
                short_acceptance=acceptance,
                restored_parameter_hash=model_identity(model),
                cache_bytes=op.cache_bytes,
                complete_axis_work_seconds=monotonic() - axis_began,
                complete_work_save=saved_work,
            )
            rows.append(row)
            marker(
                "actual_core_axis_qualified",
                dict(
                    kind=kind,
                    axis=axis,
                    K_adjoint=adj,
                    B_adjoint=badj,
                    linearity=linear["relative"],
                    old_points=independent["relative"],
                ),
            )
        hidden = []
        if kind == "fttnn":
            params = hidden_parameters(model)
            r = action.apply(c) - action.f
            full = mapping.vjp(model, action.apply(r, adjoint=True) / action.bnorm**2)
            slices = {}
            offset = 0
            for p in model.parameters():
                slices[id(p)] = slice(offset, offset + p.numel())
                offset += p.numel()
            g = np.concatenate([full[slices[id(p)]] for p in params])
            initial = [p.detach().clone() for p in params]
            for _ in range(3):
                d = rng.normal(size=g.size)
                d /= np.linalg.norm(d)
                dot = float(g @ d)
                est = []
                for h in (1e-4, 1e-5, 1e-6):
                    vals = []
                    for sign in (-1, 1):
                        start = 0
                        with torch.no_grad():
                            for p, value in zip(params, initial, strict=True):
                                p.copy_(
                                    value
                                    + sign
                                    * h
                                    * torch.from_numpy(
                                        d[start : start + p.numel()].reshape(p.shape)
                                    )
                                )
                                start += p.numel()
                        mapping.invalidate()
                        rr = action.apply(mapping.forward(model)) - action.f
                        vals.append(float(np.vdot(rr, rr).real / (2 * action.bnorm**2)))
                    fd = (vals[1] - vals[0]) / (2 * h)
                    est.append(
                        dict(
                            h=h,
                            FD=fd,
                            adjoint=dot,
                            relative=abs(fd - dot) / max(abs(fd), abs(dot), 1e-30),
                        )
                    )
                with torch.no_grad():
                    for p, value in zip(params, initial, strict=True):
                        p.copy_(value)
                mapping.invalidate()
                hidden.append(est)
        maxima = [initial_pair["relative"]]
        for row in rows:
            maxima += [row["K_adjoint_relative"], row["B_adjoint_relative"]]
            maxima += [
                row[k]["relative"]
                for k in (
                    "complex_linearity",
                    "pure_imaginary_linearity",
                    "bias_all_components_linearity",
                    "independent_old_point_mapping",
                )
            ]
        fdpass = all(min(v["relative"] for v in group) <= 1e-5 for group in hidden)
        reports[kind] = dict(
            initial_old_point_pair=initial_pair,
            axes=rows,
            hidden_FD=hidden,
            full_parameter_count=sum(p.numel() for p in model.parameters()),
            qualified=bool(max(maxima) <= 1e-10 and fdpass),
            qualification_not_used_as_formal_initialization=True,
        )
    return dict(
        models=reports,
        qualified=all(v["qualified"] for v in reports.values()),
        reference_used_for_training=False,
        reference_loaded=False,
    )
