"""Opt-in continuation policy; historical core policies and physics are unchanged."""

from copy import deepcopy
import hashlib
import json
import math


def policy_for(learned):
    return dict(
        schema="ftt.r4-continuation-policy.v1",
        inherited_rounds=4,
        total_round_limit=12 if learned else 8,
        new_round_limit=8 if learned else 4,
        new_visit_limit=24 if learned else 12,
        new_iteration_limit=7200 if learned else 3600,
        new_hidden_call_limit=160 if learned else 0,
        scalar_rounds=[6, 8, 10, 12] if learned else [6, 8],
        ordinary_ratio=0.9,
        refinement_R=1e-5,
        refinement_field=1e-3,
        refinement_worsening_ratio=1.05,
        refinement_improvement_ratio=0.99,
        disable_historical_slow_streak=True,
        native_target=1e-8,
        validation_feedback="scalars_only",
    )


def identity(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def axis_order(round_index):
    return [2, 0, 1] if round_index % 2 == 0 else [1, 0, 2]


def new_counts(counts, inherited):
    result = {key: value - inherited.get(key, 0) for key, value in counts.items()}
    if min(result.values()) < 0:
        raise ValueError("CONTINUATION_COUNTER_REGRESSION")
    return result


def charged_iterations(counts):
    return counts["LSMR_iterations"] + counts["LSMR_unretained_iterations_upper_bound"]


def trend_decision(number, scalar, previous, policy, *, learned):
    keys = (
        "native_relative",
        "augmented_relative",
        "scattered_E_relative",
        "scattered_H_relative",
        "scattered_curl_relative",
    )
    values = [scalar[k] for k in keys]
    if not all(math.isfinite(v) and v >= 0 for v in values):
        return dict(allowed=False, reason="NONFINITE_OR_NEGATIVE_SCALAR")
    if number == 6:
        return dict(allowed=True, reason="ROUND6_DIAGNOSTIC_ONLY")
    if not learned or number >= policy["total_round_limit"]:
        return dict(allowed=False, reason="AUTHORIZED_TOTAL_ROUND_LIMIT")
    if previous is None:
        raise ValueError("CONTINUATION_PREVIOUS_TWO_ROUND_SCALARS_NOT_RETAINED")
    if not all(math.isfinite(previous[k]) and previous[k] >= 0 for k in keys):
        raise ValueError("CONTINUATION_PREVIOUS_SCALARS_INVALID")
    current = [max(scalar[keys[0]], scalar[keys[1]]), scalar[keys[2]], scalar[keys[3]]]
    prior = [
        max(previous[keys[0]], previous[keys[1]]),
        previous[keys[2]],
        previous[keys[3]],
    ]
    if any(v == 0 for v in current + prior):
        return dict(
            allowed=False,
            reason="ZERO_METRIC_REQUIRES_FULL_JOINT_VERIFICATION",
            zero_metric_requires_joint_verification=True,
        )
    ratios = [c / p for c, p in zip(current, prior, strict=True)]
    ordinary = max(ratios) <= policy["ordinary_ratio"]
    near = (
        current[0] <= policy["refinement_R"]
        and max(values[2:]) <= policy["refinement_field"]
        and max(ratios) <= policy["refinement_worsening_ratio"]
        and (
            ratios[0] <= policy["refinement_improvement_ratio"]
            or max(ratios[1:]) <= policy["refinement_improvement_ratio"]
        )
    )
    return dict(
        allowed=ordinary or near,
        reason=(
            "CONTINUATION_POLICY_ELIGIBLE_ORDINARY"
            if ordinary
            else "CONTINUATION_POLICY_ELIGIBLE_REFINEMENT"
            if near
            else "NO_CONTINUED_JOINT_PROGRESS"
        ),
        ratios_R_E_H=ratios,
        ordinary=ordinary,
        refinement=near,
    )


def scalar_pending(position, rounds, policy):
    return bool(
        position["complete_rounds"] in policy["scalar_rounds"]
        and rounds
        and rounds[-1].get("round") == position["complete_rounds"] - 1
        and "isolated_validation_scalars" not in rounds[-1]
    )


def validate_parent(state, parent, binding, model):
    """Read-only import of one exact complete boundary, never a generic warm start."""
    meta = state["metadata"]
    for key, expected in parent["binding"].items():
        if meta.get(key) != expected:
            raise ValueError("PARENT_BINDING_MISMATCH:" + key)
    for key in (
        "native_sha256",
        "moments_sha256",
        "model_kind",
        "metric_kind",
        "phase_sha256",
    ):
        if meta[key] != binding[key]:
            raise ValueError("PARENT_PHYSICAL_OR_MODEL_IDENTITY_CHANGED:" + key)
    if meta.get("phase_definition") != binding["phase_definition"]:
        raise ValueError("PARENT_PHASE_DEFINITION_CHANGED")
    inherited_rounds = parent.get("inherited_rounds", 4)
    if (
        meta.get("reference_used_for_training")
        or meta.get("features_reference_exposed")
        or meta.get("reference_sha256") is not None
        or not meta.get("pde_only_solve")
        or meta.get("production_initialization_allowed")
        or meta.get("official_candidate_results")
        or meta.get("pde_only_solver_qualified")
    ):
        raise ValueError("PARENT_LABEL_OR_PRODUCTION_USE_FORBIDDEN")
    pos = state["optimizer"]
    if (
        state.get("optimizer_class") != "CoreBoundary"
        or pos != meta["position"]
        or pos["round"] != inherited_rounds
        or pos["complete_rounds"] != inherited_rounds
        or pos["axis_index"] != 0
        or pos["phase"] != "core"
    ):
        raise ValueError("PARENT_NOT_COMPLETE_ROUND4_BOUNDARY")
    for key, expected in parent["inherited_counts"].items():
        if meta["counts"][key] != expected:
            raise ValueError("PARENT_COUNTER_MISMATCH:" + key)
    if len(meta["rounds"]) != inherited_rounds or "c" not in state or "r" not in state:
        raise ValueError("PARENT_PARTIAL_STATE_FORBIDDEN")
    from src.solvers.optimization_checkpoint import parameter_order

    if state["parameter_order"] != parameter_order(model):
        raise ValueError("PARENT_PARAMETER_ORDER_MISMATCH")
    initial = model.state_dict()
    for key in initial:
        if key.startswith("phase_") and not initial[key].equal(state["model"][key]):
            raise ValueError("PARENT_PHASE_BUFFER_MISMATCH:" + key)
    return dict(
        parent_checkpoint=deepcopy(parent),
        parent_result_status=parent.get("parent_result_status", "ROUND4_FIELD_PROGRESS_NOT_QUALIFIED"),
        historical_round4_validation_preserved=True,
        allowed_import_identity_differences=[
            "source_sha",
            "input_sha256",
            "design_sha256",
            "route",
            "route_origin_monotonic",
        ],
        inherited_counts=deepcopy(meta["counts"]),
        inherited_costs=deepcopy(meta["costs"]),
        inherited_rounds=inherited_rounds,
    )
