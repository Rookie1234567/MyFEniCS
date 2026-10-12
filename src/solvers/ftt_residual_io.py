"""Hash-bound frozen base, prepared zero branch and independent dual-network reads."""

from copy import deepcopy
import json
import random
import numpy as np
import torch

from src.io.neural_wave_campaign import ROOT, digest
from src.solvers.ftt_bloch_field import BlochFTTField
from src.solvers.ftt_core_training import CoreBoundary
from src.solvers.ftt_core_continuation import validate_parent
from src.solvers.optimization_checkpoint import load_checkpoint, restore, atomic_write
from src.solvers.ftt_factored_moments import model_identity
from src.solvers.ftt_residual_branch import (
    ResidualTrainingAction,
    ResidualBranchContext,
    independent_sum_field,
    same_saved_state,
)
from src.solvers.neural_wave_greedy import atomic_json, atomic_npz


def model_factory(design, _candidate=None):
    return BlochFTTField(
        design["model"]["geometry"]["bounds_nm"],
        "fttnn",
        design["phase_definition"],
        seed=design["seed"],
        hidden_width=32,
    )


def read_base(design):
    entry = design["base_checkpoint"]
    path = ROOT / entry["path"]
    if path.stat().st_size != entry["bytes"]:
        raise ValueError("RESIDUAL_BASE_CHECKPOINT_BYTES_CHANGED")
    state = load_checkpoint(path, entry["sha256"])
    base = model_factory(design)
    prefix = validate_parent(
        state,
        entry,
        dict(entry["binding"], phase_definition=design["phase_definition"]),
        base,
    )
    restore(base, CoreBoundary({}), state)
    base.requires_grad_(False)
    for p in base.parameters():
        p.grad = None
    return base, state, prefix


def save_prepared(design, artifact, base, correction, view, prefix, old_state):
    fields, models = artifact / "fixed_residual_rhs.npz", artifact / "zero_branch.pt"
    if fields.exists() or models.exists():
        raise ValueError("RESIDUAL_PREPARED_HEALTHY_STATE_ALREADY_EXISTS")
    atomic_npz(fields, c_base=view.c_base, g=view.f)
    state = dict(
        base_model=deepcopy(base.state_dict()),
        model=deepcopy(correction.state_dict()),
        base_RNG={
            k: deepcopy(old_state[k]) for k in ("torch_rng", "numpy_rng", "python_rng")
        },
        RNG=torch.get_rng_state().clone(),
        numpy_rng=deepcopy(np.random.get_state()),
        python_rng=random.getstate(),
        base_model_hash=model_identity(base),
        correction_model_hash=model_identity(correction),
        fixed_fields_identity=view.identity,
        phase_definition=deepcopy(design["phase_definition"]),
        base_prefix=prefix,
        base_checkpoint_sha256=design["base_checkpoint"]["sha256"],
    )
    atomic_write(models, lambda f: torch.save(state, f))
    return dict(
        files={
            key: dict(
                path=str(path.relative_to(ROOT)),
                sha256=digest(path),
                bytes=path.stat().st_size,
            )
            for key, path in (("fields", fields), ("models", models))
        },
        fixed_fields_identity=view.identity,
        base_model_hash=state["base_model_hash"],
        correction_model_hash=state["correction_model_hash"],
        base_prefix=prefix,
        g_generated_once=True,
        original_action_f_unchanged=True,
    )


def preparation(artifact, design, qualification):
    receipt = qualification["prepared_branch"]
    for entry in receipt["files"].values():
        p = ROOT / entry["path"]
        if p.stat().st_size != entry["bytes"] or digest(p) != entry["sha256"]:
            raise ValueError("RESIDUAL_QUALIFIED_PREPARATION_CHANGED")
    atomic_json(artifact / "prepared_branch.json", receipt)
    return dict(
        qualified=True,
        prepared_branch=receipt,
        healthy_qualification_base_and_g_reused=True,
        new_g_generation_count=0,
        reference_used_for_training=False,
    )


def prepared_context(design, physical, qualification):
    receipt = qualification["preparation"]["prepared_branch"]
    for key, entry in receipt["files"].items():
        if entry["path"] != design["prepared_branch"]["files"][key]:
            raise ValueError("RESIDUAL_UNREGISTERED_PREPARED_FILE")
        p = ROOT / entry["path"]
        if p.stat().st_size != entry["bytes"] or digest(p) != entry["sha256"]:
            raise ValueError("RESIDUAL_PREPARED_BINDING_CHANGED")
    state = torch.load(
        ROOT / receipt["files"]["models"]["path"],
        map_location="cpu",
        weights_only=False,
    )
    base, correction = model_factory(design), model_factory(design)
    base.load_state_dict(state["base_model"], strict=True)
    base.requires_grad_(False)
    correction.load_state_dict(state["model"], strict=True)
    if (
        state["phase_definition"] != design["phase_definition"]
        or state["base_checkpoint_sha256"] != design["base_checkpoint"]["sha256"]
    ):
        raise ValueError("RESIDUAL_PREPARED_PHASE_OR_BASE_CHANGED")
    if (model_identity(base), model_identity(correction)) != (
        receipt["base_model_hash"],
        receipt["correction_model_hash"],
    ):
        raise ValueError("RESIDUAL_PREPARED_MODELS_CHANGED")
    with np.load(ROOT / receipt["files"]["fields"]["path"], allow_pickle=False) as data:
        view = ResidualTrainingAction(
            physical,
            data["c_base"],
            data["g"],
            expected=receipt["fixed_fields_identity"],
        )
    torch.set_rng_state(state["RNG"])
    np.random.set_state(state["numpy_rng"])
    random.setstate(state["python_rng"])
    binding = dict(
        view.identity,
        base_checkpoint_sha256=design["base_checkpoint"]["sha256"],
        base_model_hash=model_identity(base),
        initial_correction_hash=model_identity(correction),
        prepared_files=receipt["files"],
        phase_sha256=design["phase_definition"]["sha256"],
        frozen_base_rounds=14,
        frozen_base_core_visits=42,
        frozen_base_LSMR_iterations=25758,
        frozen_base_hidden_calls=137,
        fixed_g_not_reference_error=True,
        total_held_real_parameters=38400,
        trainable_correction_real_parameters=19200,
    )
    context = ResidualBranchContext(base, view, binding)
    context.base_RNG = deepcopy(state["base_RNG"])
    return correction, view, context


def checkpoint_points(design, state, candidate, correction):
    receipt = json.loads(
        (ROOT / design["prepared_branch"]["prepare_result"]).read_text()
    )["prepared_branch"]
    base = model_factory(design)
    base.load_state_dict(state["base_model"], strict=True)
    base.requires_grad_(False)
    models_entry = receipt["files"]["models"]
    models_path = ROOT / models_entry["path"]
    if digest(models_path) != models_entry["sha256"]:
        raise ValueError("RESIDUAL_INDEPENDENT_PREPARED_MODEL_CHANGED")
    initial = torch.load(models_path, map_location="cpu", weights_only=False)
    if not same_saved_state(state["base_RNG"], initial["base_RNG"]):
        raise ValueError("RESIDUAL_INDEPENDENT_FROZEN_BASE_RNG_CHANGED")
    if (
        model_identity(base) != receipt["base_model_hash"]
        or state["base_model_hash"] != receipt["base_model_hash"]
    ):
        raise ValueError("RESIDUAL_INDEPENDENT_SAVED_BASE_CHANGED")
    from src.solvers.neural_fe_action_packet import array_hash

    identity = receipt["fixed_fields_identity"]
    if (
        array_hash(state["g"]) != identity["training_rhs_sha256"]
        or array_hash(state["c_base"]) != identity["c_base_sha256"]
        or state["residual_branch_identity"]["phase_sha256"]
        != design["phase_definition"]["sha256"]
        or state["residual_branch_identity"]["base_checkpoint_sha256"]
        != design["base_checkpoint"]["sha256"]
        or not np.array_equal(state["c_delta"], state["c"])
        or not np.array_equal(state["c_combined"], state["c_base"] + state["c_delta"])
    ):
        raise ValueError("RESIDUAL_INDEPENDENT_PARTIAL_OR_DOUBLE_REBUILD")
    return (
        independent_sum_field(base, correction),
        state["c_combined"],
        state["r_original"],
    )
