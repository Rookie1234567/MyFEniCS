"""Function-preserving width migration and fixed V44 opt-in policies."""

from copy import deepcopy
import numpy as np
from src.solvers.ftt_core_continuation import validate_parent


def widen_field(old, *, seed=4214401):
    import torch
    from src.solvers.ftt_bloch_field import BlochFTTField

    if old.model_kind != "fttnn" or old.hidden_width != 16 or seed != 4214401:
        raise ValueError("WIDTH_EXTENSION_FIXED_16_TO_32_CONTRACT")
    bounds = torch.stack(
        (old.center - old.half_width, old.center + old.half_width), 1
    ).numpy()
    phase = dict(
        wavevector_nm_inverse=old.phase_wavevector.tolist(),
        origin_nm=old.phase_origin.tolist(),
        coordinate_unit="physical_nm",
        sign=1,
        unfolded_incident_wavevector=True,
        mode_manifest_sha256=bytes(map(int, old.phase_mode_identity)).hex(),
    )
    # Constructor randomness is not used for any migrated or new block.
    rng = torch.get_rng_state().clone()
    model = BlochFTTField(bounds, "fttnn", phase, hidden_width=32)
    torch.set_rng_state(rng)
    generator = torch.Generator(device="cpu").manual_seed(seed)
    with torch.no_grad():
        for target, source in zip(model.cores, old.cores, strict=True):
            target[0].weight[:16].copy_(source[0].weight)
            target[0].bias[:16].copy_(source[0].bias)
            torch.nn.init.xavier_uniform_(target[0].weight[16:], generator=generator)
            target[0].bias[16:].uniform_(-0.5, 0.5, generator=generator)
            target[2].weight[:16, :16].copy_(source[2].weight)
            target[2].weight[:16, 16:].zero_()
            target[2].bias[:16].copy_(source[2].bias)
            torch.nn.init.xavier_uniform_(target[2].weight[16:], generator=generator)
            target[2].bias[16:].uniform_(-0.5, 0.5, generator=generator)
            target[4].weight[:, :16].copy_(source[4].weight)
            target[4].weight[:, 16:].zero_()
            target[4].bias.copy_(source[4].bias)
        for name, buffer in old.named_buffers():
            dict(model.named_buffers())[name].copy_(buffer)
    return model


def width_policy(learned, *, extra=False):
    if extra and not learned:
        raise ValueError("WIDTH_EXTRA_ONLY_LEARNED")
    return dict(
        schema="ftt.width-refinement-policy.v1",
        inherited_rounds=8,
        total_round_limit=14 if extra else 12,
        new_round_limit=6 if extra else 4,
        new_visit_limit=18 if extra else 12,
        new_iteration_limit=21600 if extra else 14400,
        new_hidden_call_limit=(120 if extra else 80) if learned else 0,
        scalar_rounds=[10, 12, 14] if extra else [10, 12],
        disable_historical_slow_streak=True,
        native_target=1e-8,
        validation_feedback="scalars_only",
        inner_refinement=True,
    )


def width_trend(number, scalar, policy):
    keys = (
        "native_relative",
        "augmented_relative",
        "scattered_E_relative",
        "scattered_H_relative",
        "scattered_curl_relative",
    )
    if not all(np.isfinite(scalar[k]) and scalar[k] >= 0 for k in keys):
        return dict(allowed=False, reason="NONFINITE_OR_NEGATIVE_SCALAR")
    return dict(
        allowed=number < policy["total_round_limit"],
        reason="ROUND10_DIAGNOSTIC_ONLY"
        if number == 10
        else "AUTHORIZED_TOTAL_ROUND_LIMIT"
        if number >= policy["total_round_limit"]
        else "AUTHORIZED_EXTRA_EXPLORATION",
    )


def strong_width_signal(wide, narrow, *, all_three_complete, joint_pass):
    keys = ("native_relative", "scattered_E_relative", "scattered_H_relative")
    valid = all(np.isfinite(s[k]) and s[k] > 0 for s in (wide, narrow) for k in keys)
    allowed = bool(
        all_three_complete
        and not joint_pass
        and valid
        and all(wide[k] <= 0.5 * narrow[k] for k in keys)
        and wide[keys[0]] <= 1e-2
        and max(wide[k] for k in keys[1:]) <= 1e-2
    )
    return dict(
        allowed=allowed,
        all_three_complete=all_three_complete,
        reason="FIXED_STRONG_WIDTH_SIGNAL" if allowed else "NO_AUTHORIZED_EXTRA_SIGNAL",
        ratios={k: wide[k] / narrow[k] for k in keys} if valid else None,
        additional_wall_authorized=False,
    )


def import_width_parent(state, parent, binding, model, boundary):
    import torch
    from src.solvers.ftt_bloch_field import BlochFTTField
    from src.solvers.optimization_checkpoint import parameter_order, restore

    bounds = torch.stack(
        (model.center - model.half_width, model.center + model.half_width), 1
    ).numpy()
    old = BlochFTTField(bounds, "fttnn", binding["phase_definition"])
    inherited = validate_parent(state, parent, binding, old)
    restore(old, boundary, state)
    imported = deepcopy(state)
    if model.hidden_width == 32:
        expanded = widen_field(old)
        imported["model"] = deepcopy(expanded.state_dict())
        imported["parameter_order"] = parameter_order(expanded)
        imported["gradients"] = [None for _ in expanded.parameters()]
    restore(model, boundary, imported)
    inherited["width_extension"] = dict(
        old_width=16,
        new_width=model.hidden_width,
        seed=4214401 if model.hidden_width == 32 else None,
        optimizer_history_migrated=False,
        parent_boundary_and_RNG_restored=True,
    )
    return inherited
