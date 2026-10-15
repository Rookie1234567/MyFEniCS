"""Hash-bound whole dual-network parent and nonlinear boundary recovery."""

from copy import deepcopy
import random
import numpy as np
import torch
from src.io.neural_wave_campaign import ROOT, digest
from src.solvers.ftt_residual_io import model_factory
from src.solvers.ftt_residual_branch import (
    ResidualTrainingAction,
    ResidualBranchContext,
)
from src.solvers.ftt_factored_moments import model_identity
from src.solvers.ftt_conditional_core import relative_pair
from src.solvers.neural_fe_action_packet import array_hash
from src.solvers.optimization_checkpoint import load_checkpoint


def load_joint_parent(design, physical, mapping, correction=None):
    entry = design["parent_checkpoint"]
    p = ROOT / entry["path"]
    if p.stat().st_size != entry["bytes"]:
        raise ValueError("JOINT_PARENT_PT_BYTES_CHANGED")
    state = load_checkpoint(p, entry["sha256"])
    meta = state["metadata"]
    for name, value in entry["binding"].items():
        if meta.get(name) != value:
            raise ValueError("JOINT_PARENT_METADATA_CHANGED:" + name)
    if meta["new_complete_rounds"] != 6 or any(
        meta["new_counts"][k] != v
        for k, v in dict(
            core_visits=18, LSMR_iterations=21354, hidden_actual_calls=35
        ).items()
    ):
        raise ValueError("JOINT_NOT_V46_COMPLETE_LEARNED_ROUND6")
    correction = model_factory(design) if correction is None else correction
    base = model_factory(design)
    correction.load_state_dict(state["model"], strict=True)
    base.load_state_dict(state["base_model"], strict=True)
    base.requires_grad_(False)
    correction.requires_grad_(True)
    if (
        model_identity(correction) != entry["model_hash"]
        or model_identity(base) != design["base_model_hash"]
    ):
        raise ValueError("JOINT_PARENT_MODEL_OR_BASE_HASH_CHANGED")
    if meta["phase_definition"] != design["phase_definition"]:
        raise ValueError("JOINT_PARENT_PHASE_CHANGED")
    base_entry = design["base_checkpoint"]
    old = ROOT / base_entry["path"]
    if old.stat().st_size != base_entry["bytes"] or digest(old) != base_entry["sha256"]:
        raise ValueError("JOINT_ORIGINAL_BASE_PT_CHANGED")
    view = ResidualTrainingAction(
        physical, state["c_base"], state["g"], expected=design["residual_identity"]
    )
    binding = dict(state["residual_branch_identity"])
    binding.update(
        v46_zero_initial_hash=binding["initial_correction_hash"],
        initial_correction_hash=model_identity(correction),
        joint_parent_checkpoint_sha256=entry["sha256"],
    )
    context = ResidualBranchContext(base, view, binding)
    context.base_RNG = deepcopy(state["base_RNG"])
    # Verify the saved fields against their old identity before assigning the
    # new joint-run identity; no teacher, base retraining or RHS regeneration.
    original_binding = context.binding
    context.binding = deepcopy(state["residual_branch_identity"])
    context.verify_saved(state)
    context.binding = original_binding
    c = mapping.forward(correction)
    r = view.apply(c) - view.f
    pairs = dict(c=relative_pair(c, state["c"]), r=relative_pair(r, state["r"]))
    if max(x["relative"] for x in pairs.values()) > 1e-10:
        raise ValueError("JOINT_PARENT_ACTUAL_C_OR_R_RESTORE_FAILED")
    fields = view.fields(c, r)
    if array_hash(fields["g"]) != design["residual_identity"]["training_rhs_sha256"]:
        raise ValueError("JOINT_FIXED_G_CHANGED")
    for p in correction.parameters():
        p.grad = None
    torch.set_rng_state(state["torch_rng"])
    np.random.set_state(state["numpy_rng"])
    random.setstate(state["python_rng"])
    return correction, view, context, state, pairs


def verify_joint_boundary(state, context, layout, h, parent):
    context.verify_saved(state)
    if (
        state.get("joint_layout") != layout.binding
        or not np.array_equal(state.get("parameter_scales"), layout.scales)
        or not np.array_equal(state.get("parameter_mask"), layout.mask)
        or state.get("joint_h") != h
        or state.get("joint_parent_sha256") != parent["sha256"]
    ):
        raise ValueError("JOINT_RESTORE_MASK_SCALE_H_OR_PARENT_CHANGED")
