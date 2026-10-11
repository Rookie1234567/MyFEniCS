"""One exact R8 import, width migration and bounded original-FE witnesses."""

from copy import deepcopy
from time import monotonic
import numpy as np
import torch
from src.io.neural_wave_campaign import ROOT, digest
from src.solvers.ftt_bloch_field import IndependentPointPhase
from src.solvers.ftt_width_extension import import_width_parent, widen_field
from src.solvers.ftt_core_training import CoreBoundary
from src.solvers.ftt_conditional_core import (
    ConditionalCoreAction,
    output_coefficients,
    set_output_coefficients,
    hidden_parameters,
    relative_pair,
)
from src.solvers.ftt_factored_moments import FactoredMomentMap, model_identity
from src.solvers.ftt_moments import StreamingMomentMap
from src.solvers.optimization_checkpoint import load_checkpoint


def qualify_width(action, packet, design, marker, deadline):
    from src.runners.ftt_width_worker import model_factory
    from src.runners.ftt_worker import load_arrays

    began = monotonic()
    parent = design["parent_checkpoint"]
    path = ROOT / parent["path"]
    if path.stat().st_size != parent["bytes"]:
        raise ValueError("WIDTH_PARENT_BYTES_CHANGED")
    state = load_checkpoint(path, parent["sha256"])
    old = model_factory(design, dict(hidden_width=16))
    imported = import_width_parent(
        state,
        parent,
        dict(parent["binding"], phase_definition=design["phase_definition"]),
        old,
        CoreBoundary({}),
    )
    mapping = FactoredMomentMap(packet)
    c0 = mapping.forward(old)
    r0 = action.apply(c0) - action.f
    parent_pair = dict(c=relative_pair(c0, state["c"]), r=relative_pair(r0, state["r"]))
    wide, other = widen_field(old), widen_field(old)
    same = all(v.equal(other.state_dict()[k]) for k, v in wide.state_dict().items())
    c = mapping.forward(wide)
    expanded = dict(
        c=relative_pair(c, c0), Ac=relative_pair(action.apply(c), action.apply(c0))
    )
    if (
        not same
        or max(p["relative"] for p in [*parent_pair.values(), *expanded.values()])
        > 1e-10
    ):
        raise ValueError("WIDTH_INITIAL_PHYSICAL_FIELD_CHANGED")
    inventory = {
        str(m.hidden_width): dict(
            real_parameters=sum(p.numel() for p in m.parameters()),
            hidden_parameters=sum(p.numel() for p in hidden_parameters(m)),
        )
        for m in (old, wide)
    }
    if inventory != design["width_models"]:
        raise ValueError("WIDTH_ACTUAL_PARAMETER_INVENTORY")
    saved = deepcopy(wide.state_dict())
    rng = np.random.default_rng(design["qualification_seed"])
    witnesses = []
    for axis in (2, 0, 1):
        op = ConditionalCoreAction(wide, mapping, action, axis, deadline=deadline)
        d = (rng.normal(size=op.size) + 1j * rng.normal(size=op.size)).astype(
            np.complex128
        )
        d /= np.linalg.norm(d)
        dual = (
            rng.normal(size=action.size) + 1j * rng.normal(size=action.size)
        ).astype(np.complex128)
        kd, kh = op.K(d), op.KH(dual)
        lhs, rhs = np.vdot(kd, dual), np.vdot(d, kh)
        adj = abs(lhs - rhs) / max(abs(lhs), abs(rhs), 1e-30)
        coeff = output_coefficients(wide, axis)
        set_output_coefficients(wide, axis, coeff + d.reshape(op.shape))
        mapping.invalidate()
        linear = relative_pair(mapping.forward(wide), c + kd)
        wide.load_state_dict(saved)
        mapping.invalidate()
        new = np.zeros(op.shape, dtype=np.complex128)
        new[16:32] = d.reshape(op.shape)[16:32]
        reachable = float(np.linalg.norm(op.K(new.ravel())))
        if max(adj, linear["relative"]) > 1e-10 or reachable == 0:
            raise ValueError("WIDTH_REAL_CORE_ADJOINT_OR_NEW_DIRECTION_FAILED")
        witnesses.append(
            dict(
                axis=axis,
                complex_adjoint_relative=float(adj),
                linearity=linear,
                new_output_direction_norm=reachable,
                counts=op.counts.copy(),
            )
        )
    # Activate new outputs for derivative qualification only; never a candidate seed.
    for axis in range(3):
        coeff = output_coefficients(wide, axis)
        coeff[16:32] = 1e-3 * (
            rng.normal(size=coeff[16:32].shape)
            + 1j * rng.normal(size=coeff[16:32].shape)
        )
        set_output_coefficients(wide, axis, coeff)
    activated = deepcopy(wide.state_dict())
    mapping.invalidate()
    dual = (rng.normal(size=action.size) + 1j * rng.normal(size=action.size)).astype(
        np.complex128
    )
    mapping.vjp(wide, dual)
    params = hidden_parameters(wide)
    gradients = [p.grad.detach().clone() for p in params]
    new_gradient = float(sum((g[16:] ** 2).sum() for g in gradients)) ** 0.5
    if new_gradient == 0:
        raise ValueError("WIDTH_NEW_HIDDEN_PATH_NOT_ACTIVATED")
    fd = []
    for axis in range(3):
        parameter = wide.cores[axis][0].bias
        index = next(i for i, p in enumerate(params) if p is parameter)
        direction = torch.zeros_like(parameter)
        direction[16:] = torch.from_numpy(rng.normal(size=16))
        direction /= torch.linalg.vector_norm(direction)
        analytic = float(torch.dot(gradients[index], direction))
        rows = []
        for h in (1e-4, 1e-5, 1e-6):
            values = []
            for sign in (1, -1):
                wide.load_state_dict(activated)
                with torch.no_grad():
                    parameter.add_(sign * h * direction)
                mapping.invalidate()
                values.append(float(np.vdot(dual, mapping.forward(wide)).real))
            numeric = (values[0] - values[1]) / (2 * h)
            rows.append(
                dict(
                    h=h,
                    analytic=analytic,
                    numeric=numeric,
                    relative=abs(numeric - analytic)
                    / max(abs(numeric), abs(analytic), 1e-30),
                )
            )
        if min(r["relative"] for r in rows) > 1e-5 or analytic == 0:
            raise ValueError("WIDTH_NONZERO_HIDDEN_FD_FAILED")
        fd.append(dict(axis=axis, rows=rows))
    wide.load_state_dict(saved)
    mapping.invalidate()
    # Independent general-width point MLP then explicit chi and the retained raw
    # StreamingMomentMap; this does not call the factored core contraction.
    point = IndependentPointPhase(wide)
    started = monotonic()
    raw = StreamingMomentMap(packet)
    c30 = raw.forward(point)
    high_entry = design["files"]["moments_q60"]
    if digest(ROOT / high_entry["path"]) != high_entry["sha256"]:
        raise ValueError("WIDTH_Q60_HASH")
    high = load_arrays(ROOT / high_entry["path"])
    c60 = StreamingMomentMap(high).forward(point)
    point_pair = relative_pair(c30, c)
    quadrature = dict(
        coefficients=relative_pair(c30, c60),
        original_action=relative_pair(action.apply(c30), action.apply(c60)),
        seconds=monotonic() - started,
    )
    if (
        point_pair["relative"] > 1e-10
        or max(quadrature[k]["relative"] for k in ("coefficients", "original_action"))
        > 1e-8
    ):
        raise ValueError("WIDTH_INDEPENDENT_POINT_OR_Q_PAIR_FAILED")
    evidence = dict(
        qualified=True,
        parent_checkpoint=parent,
        parent_import=imported,
        parent_c_r_pair=parent_pair,
        initial_width_field_pair=expanded,
        two_wide_initial_models_bitwise_equal=same,
        inventory=inventory,
        nonzero_core_witnesses=witnesses,
        new_hidden_gradient_after_output_activation=new_gradient,
        hidden_direction_FD=fd,
        independent_point_complete_matrix_pair=point_pair,
        quadrature=quadrature,
        initial_model_hashes=dict(w16=model_identity(old), w32=model_identity(wide)),
        reference_read=False,
        global_Maxwell_factor_count=0,
        global_Gram_factor_count=0,
        Gsolve_count=0,
        original_equation=action.audit(c),
        seconds=monotonic() - began,
    )
    marker("width_and_inner_actual_qualified", evidence)
    return dict(evidence, models={"fttnn": dict(qualified=True, inventory=inventory)})
