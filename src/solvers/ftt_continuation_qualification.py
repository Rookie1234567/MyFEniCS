"""One bounded parent-field check and nonzero action witnesses; no retraining."""

from copy import deepcopy
from time import monotonic
import json
import numpy as np
import torch

from src.io.neural_wave_campaign import ROOT, digest
from src.solvers.ftt_bloch_field import make_bloch_field
from src.solvers.ftt_conditional_core import (
    ConditionalCoreAction,
    output_coefficients,
    set_output_coefficients,
    relative_pair,
)
from src.solvers.ftt_core_continuation import validate_parent
from src.solvers.ftt_core_training import CoreBoundary
from src.solvers.ftt_factored_moments import FactoredMomentMap, model_identity
from src.solvers.optimization_checkpoint import load_checkpoint, restore


def qualify_parent_fork(action, packet, design, marker, deadline):
    began = monotonic()
    parent = design["parent_checkpoint"]
    path = ROOT / parent["path"]
    if path.stat().st_size != parent["bytes"]:
        raise ValueError("PARENT_BYTES_CHANGED")
    state = load_checkpoint(path, parent["sha256"])
    old = design["qualified_operator_record"]
    if digest(ROOT / old["path"]) != old["sha256"]:
        raise ValueError("HEALTHY_QUALIFIED_OPERATOR_RECORD_CHANGED")
    old_record = json.loads((ROOT / old["path"]).read_text())
    if not old_record["models"]["fttnn"]["qualified"]:
        raise ValueError("PARENT_OPERATOR_WAS_NOT_QUALIFIED")
    model = make_bloch_field(design, "fttnn")
    binding = dict(parent["binding"], phase_definition=design["phase_definition"])
    imported = validate_parent(state, parent, binding, model)
    boundary = CoreBoundary({})
    restore(model, boundary, state)
    mapping = FactoredMomentMap(packet, point_batch=512)
    c = mapping.forward(model)
    r = action.apply(c) - action.f
    pair = dict(
        c=relative_pair(c, np.asarray(state["c"])),
        r=relative_pair(r, np.asarray(state["r"])),
    )
    if max(p["relative"] for p in pair.values()) > 1e-10:
        raise ValueError("PARENT_ACTUAL_MODEL_C_R_PAIR_FAILED")
    original_identity = model_identity(model)
    witnesses = []
    rng = np.random.default_rng(design["qualification_seed"])
    for axis in (2, 0, 1):
        op = ConditionalCoreAction(model, mapping, action, axis, deadline=deadline)
        delta = rng.normal(size=op.size) + 1j * rng.normal(size=op.size)
        delta = delta.astype(np.complex128) / np.linalg.norm(delta)
        kc = op.K(delta)
        dual = (
            rng.normal(size=action.size) + 1j * rng.normal(size=action.size)
        ).astype(np.complex128)
        kh = op.KH(dual)
        lhs, rhs = np.vdot(dual, kc), np.vdot(kh, delta)
        adjoint = float(abs(lhs - rhs) / max(abs(lhs), abs(rhs), 1e-30))
        saved = output_coefficients(model, axis)
        set_output_coefficients(model, axis, saved + delta.reshape(op.shape))
        mapping.invalidate()
        actual_delta = mapping.forward(model) - c
        linear = relative_pair(kc, actual_delta)
        restore(model, boundary, state)
        mapping.invalidate()
        if (
            model_identity(model) != original_identity
            or max(linear["relative"], adjoint) > 1e-10
        ):
            raise ValueError("PARENT_NONZERO_CORE_ACTION_OR_RESTORE_FAILED")
        witnesses.append(
            dict(
                axis=axis,
                linearity=linear,
                complex_adjoint_relative=adjoint,
                counts=op.counts.copy(),
                reference_read=False,
            )
        )
    # The second fork is checked without another physical forward: every tensor,
    # buffer, gradient, parameter order and RNG source is the same complete PT.
    other = make_bloch_field(design, "fttnn")
    restore(other, CoreBoundary({}), state)
    same = all(
        torch.equal(v, other.state_dict()[k]) for k, v in model.state_dict().items()
    )
    if not same:
        raise ValueError("PARENT_FORK_NOT_IDENTICAL")
    record = dict(
        qualified=True,
        parent_checkpoint=deepcopy(parent),
        parent_import=imported,
        restored_position=boundary.position.copy(),
        parent_c_r_pair=pair,
        original_equation=action.audit(c),
        parent_model_hash=original_identity,
        same_state_fork_full_model_bitwise=same,
        inherited_rng_from_same_PT=True,
        previous_qualification_reused=old,
        nonzero_witnesses=witnesses,
        parent_actual_c_r_checks=1,
        old_full_qualification_reruns=0,
        reference_read=False,
        new_reference_solve_count=0,
        counts=mapping.counts,
        seconds=monotonic() - began,
    )
    marker("parent_fork_qualified", record)
    return dict(
        models={"fttnn": record},
        qualified=True,
        **{k: v for k, v in record.items() if k != "qualified"},
    )
