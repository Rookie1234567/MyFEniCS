"""Bounded conditional-core cycles, full-state transactions and hidden ablation."""

from copy import deepcopy
import json
from pathlib import Path
from time import monotonic
import numpy as np
import torch

from src.solvers.ftt_conditional_core import (
    ConditionalCoreAction,
    CoreBudgetStop,
    hidden_parameters,
    solve_core,
    verify_and_apply_core,
    relative_pair,
)
from src.solvers.ftt_factored_moments import FactoredMomentMap, model_identity
from src.solvers.optimization_checkpoint import (
    CheckpointStore,
    atomic_json,
    capture,
    restore,
    load_checkpoint,
)
from src.solvers.neural_wave_greedy import atomic_npz


class CoreBoundary:
    """Cycle state, not a fictional resumable LSMR optimizer."""

    def __init__(self, position):
        self.position = position

    def state_dict(self):
        return deepcopy(self.position)

    def load_state_dict(self, state):
        self.position.clear()
        self.position.update(deepcopy(state))


def hidden_step(model, mapping, action, deadline, marker, *, call_limit=20):
    """Ordinary hidden gradient with fixed outputs and a fresh LBFGS history."""
    parameters = hidden_parameters(model)
    hidden_count = sum(p.numel() for p in parameters)
    expected = sum(core[0].weight.numel()+core[0].bias.numel()+core[2].weight.numel()+core[2].bias.numel() for core in model.cores)
    if hidden_count != expected or hidden_count not in (912, 3360):
        raise ValueError("FTT_ACTUAL_HIDDEN_PARAMETER_LAYOUT_REQUIRED")
    optimizer = torch.optim.LBFGS(
        parameters,
        lr=1,
        history_size=10,
        line_search_fn="strong_wolfe",
        max_iter=10,
        max_eval=20,
        tolerance_grad=1e-7,
        tolerance_change=1e-9,
    )
    before = capture(model, optimizer, {})
    theta = torch.cat([p.detach().ravel() for p in parameters]).clone()
    c0 = mapping.forward(model)
    r0 = action.apply(c0) - action.f
    loss0 = float(np.vdot(r0, r0).real / (2 * action.bnorm**2))
    calls, trials, began = 0, [], monotonic()

    def closure():
        nonlocal calls
        if calls >= call_limit or monotonic() >= deadline:
            raise CoreBudgetStop("HIDDEN_ACTUAL_CALL_OR_SAVE_RESERVE_REACHED")
        calls += 1
        c = mapping.forward(model)
        r = action.apply(c) - action.f
        loss = float(np.vdot(r, r).real / (2 * action.bnorm**2))
        dual = action.apply(r, adjoint=True) / (action.bnorm**2)
        mapping.vjp(model, dual)
        trials.append(dict(call=calls, loss=loss, parameter_hash=model_identity(model)))
        marker("hidden_trial", trials[-1])
        return torch.tensor(loss, dtype=torch.float64)

    failure = None
    try:
        optimizer.step(closure)
        c1 = mapping.forward(model)
        r1 = action.apply(c1) - action.f
        loss1 = float(np.vdot(r1, r1).real / (2 * action.bnorm**2))
        accepted = bool(np.isfinite(loss1) and loss1 <= loss0 + 1e-12 * max(1, loss0))
    except CoreBudgetStop as error:
        failure = str(error)
        loss1 = trials[-1]["loss"] if trials else loss0
        accepted = False
    except BaseException:
        restore(model, optimizer, before)
        mapping.invalidate()
        raise
    after = torch.cat([p.detach().ravel() for p in parameters])
    update = float(torch.linalg.vector_norm(after - theta))
    trial_state = capture(model, optimizer, {"committed": False, "calls": calls})
    if not accepted:
        restore(model, optimizer, before)
        mapping.invalidate()
        c1, r1 = c0, r0
    record = dict(
        calls=calls,
        actual_call_limit=call_limit,
        accepted=accepted,
        effective_decrease=bool(accepted and loss0 - loss1 > 1e-12 * max(1, loss0)),
        old_loss=loss0,
        trial_loss=loss1,
        accepted_update_norm=update if accepted else 0.0,
        trial_update_norm=update,
        stop_reason=failure,
        seconds=monotonic() - began,
        gradient_kind="ordinary_hidden_gradient_fixed_output_not_reduced_VarPro",
        hidden_real_parameters=hidden_count,
        fresh_history=True,
        trials=trials,
    )
    return c1, r1, record, optimizer.state_dict(), trial_state


def run_core_training(
    action,
    packet,
    model,
    artifact,
    binding,
    deadline,
    marker,
    *,
    learned,
    validation_callback=None,
    parent_checkpoint=None,
    execution_policy=None,
    joint_validation_callback=None,
    parent_importer=None,
):
    from src.solvers.ftt_core_continuation import (
        policy_for,
        identity,
        new_counts,
        charged_iterations,
        axis_order,
        trend_decision,
        scalar_pending,
        validate_parent,
    )

    continuation = execution_policy is not None
    width_run = continuation and execution_policy.get("schema") == "ftt.width-refinement-policy.v1"
    if width_run:
        from src.solvers.ftt_width_extension import width_policy
        expected_policy = width_policy(learned, extra=execution_policy["total_round_limit"] == 14)
    else:
        expected_policy = policy_for(learned)
    if continuation and (execution_policy != expected_policy or parent_checkpoint is None):
        raise ValueError("CORE_EXPLICIT_CONTINUATION_CONTRACT_REQUIRED")
    if parent_checkpoint is not None and not continuation:
        raise ValueError("CORE_PARENT_FORK_REQUIRES_OPT_IN_POLICY")
    binding = dict(binding)
    inherited = {}
    if continuation:
        binding.update(
            parent_checkpoint_sha256=parent_checkpoint["sha256"],
            execution_policy_sha256=identity(execution_policy),
        )
    artifact = Path(artifact)
    artifact.mkdir(parents=True, exist_ok=True)
    mapping = FactoredMomentMap(packet, point_batch=512)
    position = dict(
        round=0,
        axis_index=0,
        phase="core",
        complete_rounds=0,
        slow_streak=0,
        round_start_native=1.0,
    )
    boundary = CoreBoundary(position)
    counts = dict(
        core_visits=0,
        LSMR_iterations=0,
        LSMR_unretained_iterations_upper_bound=0,
        accepted_core_updates=0,
        effective_core_updates=0,
        accepted_hidden_updates=0,
        effective_hidden_updates=0,
        hidden_actual_calls=0,
        K=0,
        KH=0,
        B=0,
        BH=0,
        round_audits=0,
        uncommitted_K=0,
        uncommitted_KH=0,
    )
    costs = dict(
        core_solve_and_check=0.0,
        real_acceptance=0.0,
        hidden=0.0,
        persistence=0.0,
        audit=0.0,
    )
    history = []
    rounds = []
    last_hidden_optimizer = None
    resume_first = None
    checkpoint_dir = artifact / "checkpoints"
    pointer = checkpoint_dir / "current.json"
    pending_path = artifact / "pending_work.json"
    if pointer.exists():
        p = json.loads(pointer.read_text())
        latest = p["current"]
        state = load_checkpoint(checkpoint_dir / latest["name"], latest["sha256"])
        for key in (
            "input_sha256",
            "design_sha256",
            "native_sha256",
            "moments_sha256",
            "model_kind",
            "route",
            "metric_kind",
        ):
            if state["metadata"][key] != binding[key]:
                raise ValueError("CORE_RESUME_IDENTITY_CHANGED:" + key)
        if state["metadata"].get("phase_sha256") != binding.get("phase_sha256"):
            raise ValueError("CORE_RESUME_PHASE_IDENTITY_CHANGED")
        if continuation:
            for key in (
                "source_sha",
                "parent_checkpoint_sha256",
                "execution_policy_sha256",
            ):
                if state["metadata"].get(key) != binding[key]:
                    raise ValueError("CORE_CONTINUATION_RESUME_IDENTITY_CHANGED:" + key)
            inherited = deepcopy(state["metadata"]["inherited_state"])
        if (
            state["metadata"]["reference_used_for_training"]
            or state["metadata"]["reference_sha256"] is not None
        ):
            raise ValueError("CORE_RESUME_LABEL_FORBIDDEN")
        restore(model, boundary, state)
        counts.update(state["metadata"]["counts"])
        costs.update(state["metadata"]["costs"])
        rounds = state["metadata"]["rounds"]
        last_hidden_optimizer = state.get("last_completed_hidden_optimizer")
        if pending_path.exists():
            pending = json.loads(pending_path.read_text())
            if pending["previous_checkpoint_sha256"] == latest["sha256"]:
                # An interrupted bidiagonalization has no resumable iteration state.
                # Its retained actions are charged, and its iteration allowance is
                # conservatively exhausted rather than granted again on recovery.
                for key in ("K", "KH", "B", "BH"):
                    counts[key] += pending.get("counts", {}).get(key, 0)
                if pending["kind"] == "core":
                    counts["core_visits"] += 1
                    if width_run and pending.get("first_segment"):
                        from src.io.neural_wave_campaign import digest
                        receipt = pending["first_segment"]
                        first_file = artifact / receipt["name"]
                        if digest(first_file) != receipt["sha256"] or receipt["base_model_hash"] != model_identity(model):
                            raise ValueError("CORE_RETAINED_FIRST_IDENTITY_MISMATCH")
                        with np.load(first_file, allow_pickle=False) as data:
                            resume_first = (data["delta"].copy(), receipt["record"])
                        counts["LSMR_iterations"] += receipt["record"]["iterations"]
                        counts["LSMR_unretained_iterations_upper_bound"] += pending.get("second_reserved_iterations", 0)
                    else:
                        counts["LSMR_unretained_iterations_upper_bound"] += pending["reserved_iterations"]
                    counts["uncommitted_K"] += pending.get("counts", {}).get("K", 0)
                    counts["uncommitted_KH"] += pending.get("counts", {}).get("KH", 0)
                    costs["core_solve_and_check"] += pending.get("elapsed_seconds", 0)
                else:
                    counts["hidden_actual_calls"] += pending.get("calls", 20)
                    costs["hidden"] += pending.get("elapsed_seconds", 0)
                marker("lost_work_conservatively_charged", pending)
        store = CheckpointStore.__new__(CheckpointStore)
        store.directory = checkpoint_dir
        store.pointer = pointer
        store.records = json.loads((artifact / "checkpoint_index.json").read_text())
        if latest["generation"] == len(store.records):
            # The atomic pointer may have committed before the companion index.
            # Recover that complete generation rather than overwriting its file.
            store.records.append(latest)
            atomic_json(artifact / "checkpoint_index.json", store.index())
        if not store.records or store.records[-1]["sha256"] != latest["sha256"]:
            raise ValueError("CORE_POINTER_AND_INDEX_INCONSISTENT")
        c = mapping.forward(model)
        r = action.apply(c) - action.f
        if (
            max(
                relative_pair(c, np.asarray(state["c"]))["relative"],
                relative_pair(r, np.asarray(state["r"]))["relative"],
            )
            > 1e-10
        ):
            raise ValueError("CORE_RESTORED_MODEL_FIELD_OR_RESIDUAL_MISMATCH")
        marker(
            "resumed_complete_core_boundary",
            dict(
                generation=latest["generation"],
                position=position.copy(),
                inherited_counts=counts.copy(),
            ),
        )
    else:
        store = CheckpointStore(checkpoint_dir)
        if continuation:
            from src.io.neural_wave_campaign import ROOT

            parent_path = ROOT / parent_checkpoint["path"]
            if parent_path.stat().st_size != parent_checkpoint["bytes"]:
                raise ValueError("CORE_PARENT_CHECKPOINT_SIZE_MISMATCH")
            state = load_checkpoint(parent_path, parent_checkpoint["sha256"])
            if parent_importer is None:
                inherited = validate_parent(state, parent_checkpoint, binding, model)
                restore(model, boundary, state)
            else:
                inherited = parent_importer(state, parent_checkpoint, binding, model, boundary)
            counts.update(state["metadata"]["counts"])
            costs.update(state["metadata"]["costs"])
            rounds = deepcopy(state["metadata"]["rounds"])
            last_hidden_optimizer = deepcopy(
                state.get("last_completed_hidden_optimizer")
            )
        c = mapping.forward(model)
        r = action.apply(c) - action.f
        if continuation:
            pair = dict(
                c=relative_pair(c, np.asarray(state["c"])),
                r=relative_pair(r, np.asarray(state["r"])),
            )
            if max(pair["c"]["relative"], pair["r"]["relative"]) > 1e-10:
                raise ValueError("CORE_IMPORTED_PARENT_FIELD_OR_RESIDUAL_MISMATCH")
            inherited["parent_field_pair"] = pair
            inherited["imported_model_parameter_hash"] = model_identity(model)
            atomic_json(artifact / "parent_import.json", inherited)
            marker("parent_complete_boundary_imported", inherited)
        elif np.any(c):
            raise ValueError("STRICT_ZERO_SCATTERED_CORE_INITIALIZATION_REQUIRED")
    frozen_hidden = (
        [p.detach().clone() for p in hidden_parameters(model)]
        if continuation and not learned
        else None
    )
    frozen_buffers = (
        {k: v.detach().clone() for k, v in model.named_buffers()}
        if continuation
        else None
    )

    def new_work():
        return (
            new_counts(counts, inherited["inherited_counts"])
            if continuation
            else counts
        )

    visit_limit = execution_policy["new_visit_limit"] if continuation else 18
    iteration_limit = execution_policy["new_iteration_limit"] if continuation else 5400
    round_limit = execution_policy["total_round_limit"] if continuation else 6
    stream = (artifact / "history.jsonl").open("a", buffering=1)
    stop = "ROUND_LIMIT"
    final = None

    def emit(row):
        row.update(
            source_sha=binding["source_sha"],
            elapsed_route_seconds=monotonic() - binding["route_origin_monotonic"],
        )
        stream.write(json.dumps(row, allow_nan=False) + "\n")
        stream.flush()
        history.append(row)
        marker("core_committed" if row.get("accepted") else "core_record", row)

    def save(tag, pin=True):
        nonlocal final
        began = monotonic()
        meta = dict(
            binding,
            phase="conditional_core",
            position=position.copy(),
            counts=counts.copy(),
            costs=costs.copy(),
            rounds=deepcopy(rounds),
            remaining_seconds=max(0, deadline - monotonic()),
            deadline_monotonic=deadline,
            optimizer_recoverable=True,
            parameters_only=False,
            LSMR_inner_state_retained=False,
            tag=tag,
            r_kind="original_native_residual",
        )
        if continuation:
            if frozen_hidden is not None and any(
                not p.detach().equal(q)
                for p, q in zip(hidden_parameters(model), frozen_hidden, strict=True)
            ):
                raise ValueError("FROZEN_PARENT_HIDDEN_PARAMETERS_CHANGED")
            if any(
                not v.detach().equal(frozen_buffers[k])
                for k, v in model.named_buffers()
            ):
                raise ValueError("CONTINUATION_IMMUTABLE_BUFFERS_CHANGED")
            meta.update(
                inherited_state=deepcopy(inherited),
                new_counts=new_work(),
                new_complete_rounds=position["complete_rounds"] - inherited["inherited_rounds"],
                execution_policy=deepcopy(execution_policy),
                new_costs={
                    k: v - inherited["inherited_costs"].get(k, 0)
                    for k, v in costs.items()
                },
            )
        state = capture(model, boundary, meta)
        state.update(
            c=c.copy(),
            r=r.copy(),
            last_completed_hidden_optimizer=deepcopy(last_hidden_optimizer),
        )
        final = store.save(state, pin=pin)
        atomic_json(artifact / "checkpoint_index.json", store.index())
        costs["persistence"] += monotonic() - began
        return final

    if not pointer.exists():
        save("parent_fork_before_first_update" if continuation else "zero")
    elif final is None:
        final = store.records[-1]
    longest_pair = 0.0
    round_start_native = position["round_start_native"]

    def validate_round():
        nonlocal stop
        from src.solvers.ftt_bloch_field import scalar_continuation

        began = monotonic()
        number = position["complete_rounds"]
        scalar = validation_callback(number, final, c, r)
        costs["scalar_validation"] = (
            costs.get("scalar_validation", 0.0) + monotonic() - began
        )
        rounds[-1]["isolated_validation_scalars"] = scalar
        if continuation:
            previous = (
                rounds[-3].get("isolated_validation_scalars")
                if len(rounds) >= 3
                else None
            )
            if width_run:
                from src.solvers.ftt_width_extension import width_trend
                decision = width_trend(number, scalar, execution_policy)
            else:
                decision = trend_decision(number, scalar, previous, execution_policy, learned=learned)
            rounds[-1]["continuation_policy_decision"] = decision
            allowed = decision["allowed"]
        else:
            previous = rounds[-3]["native"] if len(rounds) >= 3 else None
            allowed = scalar_continuation(
                number,
                rounds[-1]["native"],
                scalar["scattered_E_relative"],
                scalar["scattered_H_relative"],
                previous,
            )
        rounds[-1]["predeclared_continuation_allowed"] = allowed
        persisted = save("complete_round_with_scalar_validation")
        emit(
            dict(
                kind="validation",
                round=number,
                scalars=scalar,
                continuation_allowed=allowed,
                committed_checkpoint_sha256=persisted["sha256"],
            )
        )
        if not allowed:
            stop = (
                decision["reason"]
                if continuation
                else "EARLY_NO_FIELD_PROGRESS"
                if number == 2
                else "ROUND4_FIELD_PROGRESS_NOT_QUALIFIED"
            )
            if continuation and decision.get("zero_metric_requires_joint_verification"):
                verify_native_target()
        return allowed

    def verify_native_target():
        """Only scalar verdicts cross the reference boundary; direction is unchanged."""
        nonlocal stop
        if not continuation or joint_validation_callback is None:
            stop = "NATIVE_TARGET_REACHED_REQUIRES_JOINT_VERIFICATION"
            return
        position["joint_verification_pending"] = True
        save("native_target_pending_joint_verification")
        began = monotonic()
        verdict = joint_validation_callback(final, c, r)
        costs["joint_validation"] = (
            costs.get("joint_validation", 0.0) + monotonic() - began
        )
        position["joint_verification_pending"] = False
        position["joint_verification_attempts"] = (
            position.get("joint_verification_attempts", 0) + 1
        )
        position["last_joint_verdict"] = verdict
        if verdict["joint_pass"]:
            stop = "M5_JOINT_GATE_PASS"
        elif (
            verdict["mapping_and_quadrature_pass"]
            and position["joint_verification_attempts"] == 1
        ):
            position["native_target"] = 1e-10
            stop = "JOINT_FIELD_GATE_NOT_REACHED_FINITE_RESIDUAL_REFINEMENT"
        else:
            stop = "JOINT_GATE_NOT_REACHED_REFINEMENT_ENDED"
        persisted = save("joint_verification_scalar_verdict")
        emit(
            dict(
                kind="joint_verification",
                verdict=verdict,
                stop=stop,
                committed_checkpoint_sha256=persisted["sha256"],
            )
        )

    def at_native_target():
        target = position.get("native_target", 1e-8)
        if np.linalg.norm(r) / action.bnorm > target:
            return False
        audit = action.audit(c)
        return max(audit["native_relative"], audit["augmented_relative"]) <= target

    try:
        if continuation and position.get("joint_verification_pending"):
            verify_native_target()
        if validation_callback is not None and stop not in (
            "M5_JOINT_GATE_PASS",
            "JOINT_GATE_NOT_REACHED_REFINEMENT_ENDED",
        ):
            from src.solvers.ftt_bloch_field import scalar_checkpoint_pending

            if (
                scalar_pending(position, rounds, execution_policy)
                if continuation
                else scalar_checkpoint_pending(position, rounds)
            ):
                validate_round()
        while position["round"] < round_limit:
            if stop in (
                "EARLY_NO_FIELD_PROGRESS",
                "ROUND4_FIELD_PROGRESS_NOT_QUALIFIED",
                "NO_CONTINUED_JOINT_PROGRESS",
                "AUTHORIZED_TOTAL_ROUND_LIMIT",
                "ZERO_METRIC_REQUIRES_FULL_JOINT_VERIFICATION",
                "NONFINITE_OR_NEGATIVE_SCALAR",
                "M5_JOINT_GATE_PASS",
                "JOINT_GATE_NOT_REACHED_REFINEMENT_ENDED",
            ):
                break
            if monotonic() >= deadline - 20:
                stop = "ROUTE_SAVE_RESERVE"
                break
            order = axis_order(position["round"])
            if position["phase"] == "core":
                axis = order[position["axis_index"]]
                charged = charged_iterations(new_work())
                if (
                    new_work()["core_visits"] >= visit_limit
                    or charged >= iteration_limit
                ):
                    stop = "CORE_WORK_LIMIT"
                    break
                if longest_pair and deadline - monotonic() < max(
                    60, 300 * longest_pair + 20
                ):
                    stop = "INSUFFICIENT_FULL_CORE_CHECK_AND_SAVE_WINDOW"
                    break
                op = ConditionalCoreAction(
                    model, mapping, action, axis, deadline=deadline - 20, marker=marker
                )
                b = -r / action.bnorm
                counts["core_visits"] += 1
                began = monotonic()
                pending = dict(
                    kind="core",
                    axis=axis,
                    round=position["round"],
                    previous_checkpoint_sha256=final["sha256"],
                    source_sha=binding["source_sha"],
                    started_monotonic=began,
                    reserved_iterations=min(1200 if width_run else 300, iteration_limit - charged),
                    completed_iterations="NOT_RETAINED",
                    counts={},
                    status="STARTED_NOT_COMMITTED",
                )
                atomic_json(pending_path, pending)
                marker("core_solve_begin", pending)
                charged_counts = {key: 0 for key in op.counts}
                inner_completed = False
                try:
                    if width_run:
                        from src.solvers.ftt_core_refinement import solve_refined
                        from src.io.neural_wave_campaign import digest

                        def persist_first(d, record, residual):
                            name = f"first_segment_r{position['round']}_a{axis}_{final['generation']}.npz"
                            atomic_npz(artifact/name, delta=d, residual=residual, b=b)
                            pending["first_segment"] = dict(name=name, sha256=digest(artifact/name),
                                base_model_hash=op.identity, axis=axis, record=record)
                            pending["counts"] = op.counts.copy()
                            pending["second_reserved_iterations"] = 900
                            atomic_json(pending_path, pending)
                            marker("first_segment_increment_persisted_model_not_updated", pending)

                        delta, inner = solve_refined(op, b,
                            iteration_allowance=pending["reserved_iterations"],
                            persist_first=persist_first, resume_first=resume_first,
                            seconds_per_iteration=longest_pair)
                        resume_first = None
                        counts["LSMR_unretained_iterations_upper_bound"] += inner["charged_unretained_iterations"]
                    else:
                        delta, inner = solve_core(op, b, maxiter=pending["reserved_iterations"])
                    inner_completed = True
                    pending["completed_iterations"] = inner["iterations"]
                    costs["core_solve_and_check"] += monotonic() - began
                    counts["LSMR_iterations"] += inner["iterations"]
                    for k in ("K", "KH", "B", "BH"):
                        counts[k] += op.counts[k]
                    charged_counts = op.counts.copy()
                    longest_pair = max(
                        longest_pair,
                        (monotonic() - began) / max(1, inner["iterations"]),
                    )
                    before_check_counts = op.counts.copy()
                    began = monotonic()
                    c, r, accepted = verify_and_apply_core(
                        model, mapping, action, op, delta, c
                    )
                    if width_run and not accepted["accepted"] and inner["chosen_increment"] == "merged":
                        with np.load(artifact/pending["first_segment"]["name"], allow_pickle=False) as retained:
                            c, r, accepted = verify_and_apply_core(model, mapping, action, op, retained["delta"], c)
                        inner["real_merged_writeback_rejected_first_fallback"] = True
                    costs["real_acceptance"] += monotonic() - began
                    for k in ("K", "KH", "B", "BH"):
                        counts[k] += op.counts[k] - before_check_counts[k]
                except CoreBudgetStop as error:
                    for k in ("K", "KH", "B", "BH"):
                        counts[k] += op.counts[k] - charged_counts[k]
                    if not inner_completed:
                        counts["LSMR_unretained_iterations_upper_bound"] += pending[
                            "reserved_iterations"
                        ]
                    counts["uncommitted_K"] += op.counts["K"]
                    counts["uncommitted_KH"] += op.counts["KH"]
                    costs["core_solve_and_check"] += monotonic() - began
                    emit(
                        dict(
                            kind="uncommitted_core",
                            axis=axis,
                            round=position["round"],
                            reason=str(error),
                            counts=op.counts,
                            LSMR_completed_iterations="NOT_RETAINED",
                        )
                    )
                    stop = "CORE_INTERRUPTED_AT_SAVE_RESERVE"
                    break
                finally:
                    pending.update(
                        elapsed_seconds=monotonic() - pending["started_monotonic"],
                        counts=op.counts.copy(),
                        status="RETURNED_NOT_YET_COMMITTED",
                    )
                    atomic_json(pending_path, pending)
                counts["accepted_core_updates"] += int(accepted["accepted"])
                counts["effective_core_updates"] += int(accepted["effective_decrease"])
                position["axis_index"] += 1
                if position["axis_index"] == 3:
                    position["phase"] = "hidden" if learned else "audit"
                persisted = save("complete_core")
                emit(
                    dict(
                        kind="core",
                        axis=axis,
                        round=position["round"],
                        inner=inner,
                        **accepted,
                        committed_checkpoint_sha256=persisted["sha256"],
                        next_position=position.copy(),
                    )
                )
                if at_native_target():
                    verify_native_target()
                    if (
                        stop
                        != "JOINT_FIELD_GATE_NOT_REACHED_FINITE_RESIDUAL_REFINEMENT"
                    ):
                        break
            if position["phase"] == "hidden":
                calls_left = (
                    execution_policy["new_hidden_call_limit"]
                    - new_work()["hidden_actual_calls"]
                    if continuation
                    else 20
                )
                if calls_left <= 0:
                    stop = "HIDDEN_WORK_LIMIT"
                    break
                pending = dict(
                    kind="hidden",
                    round=position["round"],
                    previous_checkpoint_sha256=final["sha256"],
                    source_sha=binding["source_sha"],
                    started_monotonic=monotonic(),
                    calls=min(20, calls_left),
                    status="STARTED_NOT_COMMITTED",
                )
                atomic_json(pending_path, pending)
                try:
                    c, r, h, last_hidden_optimizer, trial = hidden_step(
                        model,
                        mapping,
                        action,
                        deadline - 20,
                        marker,
                        call_limit=min(20, calls_left),
                    )
                    pending["calls"] = h["calls"]
                finally:
                    pending.update(
                        elapsed_seconds=monotonic() - pending["started_monotonic"],
                        status="RETURNED_NOT_YET_COMMITTED",
                    )
                    atomic_json(pending_path, pending)
                counts["hidden_actual_calls"] += h["calls"]
                costs["hidden"] += h["seconds"]
                counts["accepted_hidden_updates"] += int(h["accepted"])
                counts["effective_hidden_updates"] += int(h["effective_decrease"])
                from src.solvers.optimization_checkpoint import atomic_write

                atomic_write(
                    artifact / "last_hidden_trial.pt", lambda f: torch.save(trial, f)
                )
                position["phase"] = "audit"
                persisted = save("complete_hidden")
                emit(
                    dict(
                        kind="hidden",
                        round=position["round"],
                        **h,
                        committed_checkpoint_sha256=persisted["sha256"],
                    )
                )
                if continuation and at_native_target():
                    verify_native_target()
                    if (
                        stop
                        != "JOINT_FIELD_GATE_NOT_REACHED_FINITE_RESIDUAL_REFINEMENT"
                    ):
                        break
            if position["phase"] == "audit":
                began = monotonic()
                a = action.audit(c)
                costs["audit"] += monotonic() - began
                counts["round_audits"] += 1
                native = float(np.linalg.norm(r) / action.bnorm)
                decrease = (round_start_native - native) / max(
                    round_start_native, 1e-30
                )
                position["slow_streak"] = (
                    position["slow_streak"] + 1 if decrease < 1e-3 else 0
                )
                rounds.append(
                    dict(
                        round=position["round"],
                        native=native,
                        start_native=round_start_native,
                        relative_native_improvement=decrease,
                        original_equation=a,
                        counts=counts.copy(),
                    )
                )
                position.update(
                    round=position["round"] + 1,
                    axis_index=0,
                    phase="core",
                    complete_rounds=position["complete_rounds"] + 1,
                )
                round_start_native = native
                position["round_start_native"] = native
                persisted = save("complete_round")
                if validation_callback is not None and position["complete_rounds"] in (
                    execution_policy["scalar_rounds"] if continuation else (2, 4)
                ):
                    validate_round()
                    persisted = final
                emit(
                    dict(
                        kind="round",
                        **rounds[-1],
                        committed_checkpoint_sha256=persisted["sha256"],
                    )
                )
                if stop in (
                    "EARLY_NO_FIELD_PROGRESS",
                    "ROUND4_FIELD_PROGRESS_NOT_QUALIFIED",
                    "NO_CONTINUED_JOINT_PROGRESS",
                    "AUTHORIZED_TOTAL_ROUND_LIMIT",
                    "ZERO_METRIC_REQUIRES_FULL_JOINT_VERIFICATION",
                    "NONFINITE_OR_NEGATIVE_SCALAR",
                ):
                    break
                if (
                    not continuation
                    and position["complete_rounds"] >= 2
                    and position["slow_streak"] >= 2
                    and native > 1e-2
                ):
                    stop = "BLOCK_ALTERNATION_STAGNATION"
                    break
    finally:
        # SIGKILL cannot execute this block. The guarantee is the previous fsync boundary.
        stream.close()
    final = save("final_committed")
    atomic_npz(artifact / "frozen_field.npz", c=c, r=r)
    return dict(
        binding,
        status=stop,
        stop_reason=stop,
        counts=counts,
        costs=costs,
        rounds=rounds,
        checkpoint=final,
        original_equation=action.audit(c),
        native=float(np.linalg.norm(r) / action.bnorm),
        model_parameter_hash=model_identity(model),
        position=position,
        learned_hidden_enabled=learned,
        mapping_counts=mapping.counts,
        mapping_costs=mapping.costs,
        native_action_counts=action.counts,
        native_action_costs=action.costs,
        cache_planned_bytes=mapping.static_bytes + 2 * mapping.dynamic_bytes,
        LSMR_internal_state_recoverable=False,
        global_Gram_factor_count=0,
        Gsolve_count=0,
        global_Maxwell_factor_count=0,
        full_FE_Krylov_count=0,
        output_coefficients_in_checkpoint=True,
        actual_field_not_yet_independently_verified=True,
        **(
            dict(
                inherited_state=inherited,
                new_counts=new_work(),
                new_complete_rounds=position["complete_rounds"] - inherited["inherited_rounds"],
                execution_policy=execution_policy,
                new_costs={
                    k: v - inherited["inherited_costs"].get(k, 0)
                    for k, v in costs.items()
                },
                freeze_hidden_bitwise_unchanged=frozen_hidden is not None,
            )
            if continuation
            else {}
        ),
    )
