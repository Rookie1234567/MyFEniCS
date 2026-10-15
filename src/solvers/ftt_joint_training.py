"""Bounded joint nonlinear FTT steps using the original durable checkpoints."""

from copy import deepcopy
import json
import random
from time import monotonic
import numpy as np
import torch
from src.solvers.ftt_joint_tangent import (
    ParameterLayout,
    JointTangent,
    ModelTransaction,
    TangentBudgetStop,
)
from src.solvers.joint_least_squares import (
    JointLMState,
    solve_augmented,
    prediction,
    cauchy_step,
    realify,
)
from src.solvers.ftt_joint_io import verify_joint_boundary
from src.solvers.ftt_conditional_core import relative_pair
from src.solvers.ftt_bloch_field import IndependentPointPhase
from src.solvers.ftt_moments import StreamingMomentMap
from src.solvers.ftt_factored_moments import model_identity
from src.solvers.neural_wave_greedy import atomic_json, atomic_npz
from src.solvers.optimization_checkpoint import (
    CheckpointStore,
    capture,
    restore,
    load_checkpoint,
)


def independent_coefficients(model, raw):
    """Old pointwise evaluation; no shared AD graph, preserve optimizer RNG."""
    rng = (
        torch.get_rng_state().clone(),
        deepcopy(np.random.get_state()),
        random.getstate(),
    )
    try:
        return raw.forward(IndependentPointPhase(model))
    finally:
        torch.set_rng_state(rng[0])
        np.random.set_state(rng[1])
        random.setstate(rng[2])


def run_joint_training(
    action,
    packet,
    model,
    artifact,
    binding,
    deadline,
    marker,
    *,
    learned,
    residual_context,
    parent_state,
    parent_pairs,
    qualification,
    mapping,
    execution_policy,
    parent_entry,
    validation_callback=None,
    joint_validation_callback=None,
):
    policy = execution_policy
    probe = binding["route"] == "FTT_JOINT_STEP_PROBE"
    layout = ParameterLayout(model, output_only=not learned)
    if layout.binding["scale_sha256"] != qualification["scales_sha256"]:
        raise ValueError("JOINT_BATCH_FROZEN_PARENT_SCALES_CHANGED")
    h = qualification["h"]
    controller = JointLMState(h)
    raw = StreamingMomentMap(packet)
    initial_theta = layout.theta()
    initial_hidden = initial_theta[layout.hidden].copy()
    initial_buffers = deepcopy(dict(model.named_buffers()))
    c = mapping.forward(model)
    r = action.apply(c) - action.f
    initial_native = action.original_relative(r)
    repeat_native = []
    if probe:
        for _ in range(2):
            point_c = independent_coefficients(model, raw)
            point_r = action.apply(point_c) - action.f
            repeat_native.append(action.original_relative(point_r))
            if relative_pair(c, point_c)["relative"] > 1e-10:
                raise ValueError("JOINT_PARENT_OLD_POINT_MAPPING_FAILED")
    repeat_drift = max([abs(x - initial_native) for x in repeat_native] + [0.0])
    costs = dict(inner=0.0, trial=0.0, persistence=0.0, scalar_validation=0.0)
    total_actions = dict(JVP=0, VJP=0)
    origin = binding["route_origin_monotonic"]
    trace = artifact / "history.jsonl"
    scales_binding = deepcopy(layout.binding)
    point_pairs = []
    joint_verdicts = []
    store_dir = artifact / "checkpoints"
    pointer = store_dir / "current.json"
    last = None
    resumed = []

    def emit(row):
        row.update(
            source_sha=binding["source_sha"], elapsed_route_seconds=monotonic() - origin
        )
        with trace.open("a") as stream:
            stream.write(json.dumps(row, allow_nan=False) + "\n")
            stream.flush()
        marker("joint_" + row["kind"], row)

    if pointer.exists():
        entry = json.loads(pointer.read_text())["current"]
        state = load_checkpoint(store_dir / entry["name"], entry["sha256"])
        for k in (
            "input_sha256",
            "design_sha256",
            "native_sha256",
            "moments_sha256",
            "route",
            "phase_sha256",
        ):
            if state["metadata"][k] != binding[k]:
                raise ValueError("JOINT_RESUME_BINDING_CHANGED:" + k)
        verify_joint_boundary(state, residual_context, layout, h, parent_entry)
        restore(model, controller, state)
        resumed = list(state["metadata"].get("source_ancestry", []))
        resumed.append(state["metadata"]["source_sha"])
        controller.recover_lost_inner()
        c = mapping.forward(model)
        r = action.apply(c) - action.f
        if (
            max(
                relative_pair(c, state["c"])["relative"],
                relative_pair(r, state["r"])["relative"],
            )
            > 1e-10
        ):
            raise ValueError("JOINT_REOPEN_ACTUAL_C_R_CHANGED")
        store = CheckpointStore.__new__(CheckpointStore)
        store.directory = store_dir
        store.records = json.loads((artifact / "checkpoint_index.json").read_text())
        if store.records[-1]["sha256"] != entry["sha256"]:
            raise ValueError("JOINT_POINTER_INDEX_CHANGED")
        last = entry
    else:
        store = CheckpointStore(store_dir)

    def persist(tag, *, pin=False):
        nonlocal last
        began = monotonic()
        residual_context.check_base()
        if any(not v.equal(initial_buffers[n]) for n, v in model.named_buffers()):
            raise ValueError("JOINT_IMMUTABLE_PHASE_OR_COORDINATE_BUFFER_CHANGED")
        if not learned and not np.array_equal(
            layout.theta()[layout.hidden], initial_hidden
        ):
            raise ValueError("JOINT_OUTPUT_CONTROL_HIDDEN_CHANGED")
        counts = dict(
            trials=controller.trials,
            accepted=controller.accepted,
            rejected=controller.rejected,
            LSMR_iterations=controller.lsmr_iterations,
            lost_iterations_upper_bound=controller.lost_iterations_upper_bound,
            lost_trial_upper_bound=controller.lost_trial_upper_bound,
            **total_actions,
        )
        meta = dict(
            binding,
            tag=tag,
            counts=counts,
            source_ancestry=sorted(set(resumed)),
            residual_branch=deepcopy(residual_context.binding),
            c_kind="correction_coefficients",
            r_kind="A_delta_minus_fixed_g",
        )
        state = capture(model, controller, meta)
        state.update(
            c=c.copy(),
            r=r.copy(),
            **residual_context.checkpoint_fields(c, r),
            joint_layout=deepcopy(scales_binding),
            parameter_scales=layout.scales.copy(),
            parameter_mask=layout.mask.copy(),
            joint_h=h,
            joint_parent_sha256=parent_entry["sha256"],
        )
        last = store.save(state, pin=pin)
        atomic_json(artifact / "checkpoint_index.json", store.index())
        costs["persistence"] += monotonic() - began
        return last

    if last is None:
        persist("same_parent_before_first_joint_step", pin=True)
    longest_inner_iteration = (
        qualification["timings"]["JVP"] + qualification["timings"]["VJP"]
    )
    stop = "NOT_STARTED"
    try:
        while True:
            if monotonic() >= deadline - policy["final_save_reserve_s"]:
                stop = "ROUTE_WALL_SAVE_RESERVE"
                break
            if controller.trials >= policy["trial_limit"]:
                stop = "TRIAL_LIMIT"
                break
            if controller.accepted >= policy["accepted_limit"]:
                stop = "ACCEPTED_LIMIT"
                break
            if controller.lsmr_iterations >= policy["total_lsmr"]:
                stop = "LSMR_LIMIT"
                break
            if controller.rejection_streak >= policy["rejection_streak_limit"]:
                stop = "EIGHT_CONSECUTIVE_REJECTIONS"
                break
            if controller.mu >= 1e8 * h and controller.rejection_streak:
                stop = "DAMPING_UPPER_BOUND_NO_DESCENT"
                break
            if (
                probe
                and controller.accepted
                and (initial_native - action.original_relative(r)) / initial_native
                >= 1e-3
                and initial_native - action.original_relative(r) > 10 * repeat_drift
            ):
                stop = "PROBE_INVESTMENT_GATE_PASSED"
                break
            maxiter = min(200, policy["total_lsmr"] - controller.lsmr_iterations)
            remaining = deadline - monotonic() - policy["final_save_reserve_s"]
            if longest_inner_iteration:
                maxiter = min(
                    maxiter,
                    int(max(0.0, remaining - 30) / (1.5 * longest_inner_iteration)),
                )
            if maxiter < 1:
                stop = "INNER_TIME_SAVE_RESERVE"
                break
            tangent = JointTangent(
                model,
                mapping,
                action,
                layout,
                deadline=deadline - policy["final_save_reserve_s"],
                marker=marker,
            )
            J = tangent.operator()
            e = realify(r / action.bnorm)
            loss = float(e @ e / 2)
            theta = layout.theta()
            transaction = ModelTransaction(model, mapping)
            controller.pending_inner = maxiter
            persist("before_nonresumable_lsmr")
            began = monotonic()
            v, jv, inner = solve_augmented(J, e, controller.mu, maxiter=maxiter)
            elapsed_inner = monotonic() - began
            costs["inner"] += elapsed_inner
            longest_inner_iteration = max(
                longest_inner_iteration, elapsed_inner / max(1, inner["iterations"])
            )
            controller.pending_inner = None
            controller.lsmr_iterations += inner["iterations"]
            pred = prediction(e, jv)
            step_kind = "AUGMENTED_LSMR"
            if not np.isfinite(pred) or pred <= 0:
                v, jv = cauchy_step(J, e, controller.mu)
                step_kind = "ONE_CAUCHY_SAME_DAMPING"
                if v is None:
                    stop = "INDEPENDENTLY_QUALIFIED_ZERO_GRADIENT_STAGNATION"
                    break
                pred = prediction(e, jv)
            total_actions = {
                k: total_actions[k] + tangent.counts[k] for k in total_actions
            }
            controller.pending_trial = True
            persist("before_actual_nonlinear_trial")
            began = monotonic()
            accepted = False
            trial_c, trial_r = c, r
            actual_pair = None
            try:
                layout.set_theta(theta + layout.expand(v))
                mapping.invalidate()
                trial_c = mapping.forward(model)
                trial_r = action.apply(trial_c) - action.f
                independent_c = independent_coefficients(model, raw)
                actual_pair = relative_pair(trial_c, independent_c)
                if actual_pair["relative"] > 1e-10:
                    raise ValueError("JOINT_NONLINEAR_ACTUAL_OLD_POINT_MAPPING_FAILED")
                trial_loss = float(
                    np.vdot(trial_r, trial_r).real / (2 * action.bnorm**2)
                )
                row = controller.decide(loss, trial_loss, pred)
                controller.pending_trial = False
                accepted = row["accepted"]
                point_pairs.append(actual_pair["relative"])
            finally:
                if not accepted:
                    transaction.restore()
            costs["trial"] += monotonic() - began
            diagnostics = None
            if accepted:
                c, r = trial_c, trial_r
                if controller.accepted <= 3:
                    accepted_theta = layout.theta()
                    diagnostics = {}
                    try:
                        for label, mask in [
                            ("hidden_only", layout.hidden),
                            ("output_only", ~layout.hidden),
                        ]:
                            separate = theta.copy()
                            separate[mask] = accepted_theta[mask]
                            layout.set_theta(separate)
                            mapping.invalidate()
                            dc = mapping.forward(model)
                            dr = action.apply(dc) - action.f
                            diagnostics[label] = dict(
                                training_loss=float(
                                    np.vdot(dr, dr).real / (2 * action.bnorm**2)
                                ),
                                original_native=action.original_relative(dr),
                            )
                    finally:
                        layout.set_theta(accepted_theta)
                        mapping.invalidate()
            update = layout.expand(v)
            row.update(
                kind="trial",
                trial=controller.trials,
                accepted_count=controller.accepted,
                step_kind=step_kind,
                inner=inner,
                original_native=action.original_relative(r),
                training_native=float(np.linalg.norm(r) / action.bnorm),
                step_full_real_norm=float(np.linalg.norm(update)),
                step_hidden_norm=float(np.linalg.norm(update[layout.hidden])),
                step_output_norm=float(np.linalg.norm(update[~layout.hidden])),
                independent_actual_mapping=actual_pair,
                partial_update_diagnostics=diagnostics,
                nonlinear_trial_not_required_to_equal_linear_prediction=True,
            )
            persist("accepted" if accepted else "rejected_restored", pin=accepted)
            row["checkpoint_sha256"] = last["sha256"]
            emit(row)
            if (
                accepted
                and not probe
                and (
                    controller.accepted % 4 == 0 or action.original_relative(r) <= 1e-8
                )
            ):
                began = monotonic()
                fields = action.fields(c, r)
                scalar = validation_callback(
                    controller.accepted,
                    last,
                    fields["c_combined"],
                    fields["r_original"],
                )
                emit(
                    dict(
                        kind="validation",
                        accepted_count=controller.accepted,
                        scalars=scalar,
                    )
                )
                costs["scalar_validation"] += monotonic() - began
            if accepted and not probe and action.original_relative(r) <= 1e-8:
                fields = action.fields(c, r)
                verdict = joint_validation_callback(
                    last, fields["c_combined"], fields["r_original"]
                )
                joint_verdicts.append(verdict)
                if verdict["joint_pass"]:
                    stop = "M5_JOINT_GATE_PASSED"
                    break
            if accepted and np.linalg.norm(update) <= 1e-14 * max(
                1.0, np.linalg.norm(theta)
            ):
                stop = "ACTUAL_PARAMETER_STEP_STAGNATION"
                break
    except TangentBudgetStop:
        stop = "ROUTE_WALL_SAVE_RESERVE"
        controller.recover_lost_inner()
        mapping.invalidate()
        c = mapping.forward(model)
        r = action.apply(c) - action.f
    persist("terminal_" + stop, pin=True)
    fields = action.fields(c, r)
    if not probe and validation_callback is not None and monotonic() < deadline - 30:
        scalar = validation_callback(
            controller.accepted, last, fields["c_combined"], fields["r_original"]
        )
        emit(
            dict(
                kind="terminal_validation",
                accepted_count=controller.accepted,
                scalars=scalar,
            )
        )
    atomic_npz(
        artifact / "frozen_field.npz", c=fields["c_combined"], r=fields["r_original"]
    )
    theta = layout.theta()
    native = action.original_relative(r)
    gain = (initial_native - native) / initial_native
    qualified = bool(
        probe
        and controller.accepted
        and gain >= 1e-3
        and initial_native - native > 10 * repeat_drift
    )
    result = dict(
        binding,
        status=stop,
        stop_reason=stop,
        checkpoint=last,
        qualified=qualified if probe else False,
        probe_gate_pass=qualified if probe else None,
        initial_native=initial_native,
        native=native,
        training_native=float(np.linalg.norm(r) / action.bnorm),
        original_equation=action.audit(c),
        cumulative_original_native_relative_decrease=gain,
        independent_repeated_native=repeat_native,
        independent_repeat_drift=repeat_drift,
        hidden_total_update_norm=float(
            np.linalg.norm((theta - initial_theta)[layout.hidden])
        ),
        output_total_update_norm=float(
            np.linalg.norm((theta - initial_theta)[~layout.hidden])
        ),
        counts=dict(
            trials=controller.trials,
            accepted=controller.accepted,
            rejected=controller.rejected,
            LSMR_iterations=controller.lsmr_iterations,
            lost_iterations_upper_bound=controller.lost_iterations_upper_bound,
            lost_trial_upper_bound=controller.lost_trial_upper_bound,
            **total_actions,
        ),
        costs=costs,
        damping=controller.mu,
        h=h,
        joint_layout=scales_binding,
        parent_checkpoint=parent_entry,
        parent_restore_pairs=parent_pairs,
        model_parameter_hash=model_identity(model),
        maximum_independent_actual_mapping_relative=max(point_pairs, default=0.0),
        joint_verdicts=joint_verdicts,
        LSMR_internal_state_recoverable=False,
        probe_state_not_used_as_formal_start=True,
        base_bitwise_unchanged=True,
        global_Gram_factor_count=0,
        global_Maxwell_factor_count=0,
        Gsolve_count=0,
    )
    if probe:
        model.load_state_dict(parent_state["model"], strict=True)
        model.zero_grad(set_to_none=True)
        mapping.invalidate()
        torch.set_rng_state(parent_state["torch_rng"])
        np.random.set_state(parent_state["numpy_rng"])
        random.setstate(parent_state["python_rng"])
        if model_identity(model) != parent_entry["model_hash"]:
            raise ValueError("JOINT_PROBE_DID_NOT_RESTORE_PARENT")
        result["parent_restored_bitwise_after_probe"] = True
    return result
