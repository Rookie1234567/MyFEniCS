"""Explicit model/metric opt-ins and synchronous full-state FTT transactions."""

import json
from pathlib import Path
from time import monotonic

import numpy as np
import torch
from scipy import sparse

from src.solvers.ftt_field import FTTField
from src.solvers.ftt_moments import StreamingMomentMap
from src.solvers.feinn_native import ResidualMetric
from src.solvers.optimization_checkpoint import (
    CheckpointStore,
    atomic_write,
    atomic_json,
    capture,
    optimizer_step,
    restore,
)


class StopFTT(Exception):
    pass


def make_model(bounds, model_kind, seed=4213701):
    return FTTField(bounds, model_kind, seed)


class FieldMetric:
    """Reference-exposed isolated fit; only sparse G multiplication."""

    def __init__(self, G, reference):
        self.G = sparse.csr_matrix(G)
        self.reference = np.asarray(reference, dtype=np.complex128)
        self.denominator = float(np.vdot(self.reference, self.G @ self.reference).real)
        if self.denominator <= 0:
            raise ValueError("NONZERO_REFERENCE_NORM_REQUIRED")
        self.count = 1

    def value(self, c, *, gradient=False):
        e = c - self.reference
        Ge = self.G @ e
        self.count += 1
        dot = np.vdot(e, Ge)
        if dot.real < -1e-14 or abs(dot.imag) > 1e-10 * max(abs(dot.real), 1e-30):
            raise ValueError("INVALID_FTT_FIT_QUADRATIC")
        return (
            float(dot.real / (2 * self.denominator)),
            e,
            (Ge / self.denominator if gradient else None),
        )


def make_metric(action, metric_kind, *, G=None, reference=None):
    if metric_kind == "native_euc":
        if G is not None or reference is not None:
            raise ValueError("NATIVE_TRAINING_LABEL_OR_GRAM_FORBIDDEN")
        return ResidualMetric(action, gram=None)
    if metric_kind == "reference_fit_G" and G is not None and reference is not None:
        return FieldMetric(G, reference)
    raise ValueError("EXPLICIT_FTT_METRIC_KIND_REQUIRED")


def run_training(
    action,
    packet,
    model,
    metric,
    artifact,
    binding,
    deadline,
    marker,
    *,
    call_limit,
    adam_steps,
    mapping=None,
    resume_state=None,
    resume_identity=None,
):
    artifact = Path(artifact)
    mapping = StreamingMomentMap(packet) if mapping is None else mapping
    params = list(model.parameters())
    optimizer = torch.optim.Adam(params, lr=1e-3, weight_decay=0)
    store = CheckpointStore(artifact / "checkpoints")
    counts = dict(
        attempted_calls=0,
        complete_loss_gradient_calls=0,
        committed_steps=0,
        Adam_updates=0,
        LBFGS_outer_steps=0,
        native_audits=0,
    )
    costs = dict(closures=0.0, optimizer_and_commit=0.0, persistence=0.0, audit=0.0)
    phase = "Adam"
    inherited_counts = counts.copy()
    if resume_state is not None:
        from src.postprocessing.ftt_verification import validate_checkpoint_identity

        if resume_identity is None:
            raise ValueError("FULL_FTT_RESUME_IDENTITY_REQUIRED")
        validate_checkpoint_identity(
            resume_state, resume_identity, model, isinstance(metric, FieldMetric)
        )
        phase = resume_state["metadata"]["phase"]
        if phase == "L-BFGS":
            optimizer = torch.optim.LBFGS(
                params,
                lr=1,
                history_size=20,
                line_search_fn="strong_wolfe",
                max_iter=20,
                max_eval=25,
                tolerance_grad=1e-7,
                tolerance_change=1e-9,
            )
        elif phase != "Adam":
            raise ValueError("FTT_RESUME_PHASE_UNKNOWN")
        restore(model, optimizer, resume_state)
        counts = resume_state["metadata"]["counts"].copy()
        published_counts = resume_identity.get("counts", counts)
        # The original final audit occurs after the final model save. Charge
        # that saved, hash-bound published work too; never replay it for logs.
        if any(
            counts[k] != published_counts[k] for k in counts if k != "native_audits"
        ):
            raise ValueError("FTT_PARENT_PUBLISHED_WORK_STATE_MISMATCH")
        if published_counts["native_audits"] < counts["native_audits"]:
            raise ValueError("FTT_PARENT_PUBLISHED_AUDIT_COUNT_REGRESSED")
        counts = published_counts.copy()
        inherited_counts = counts.copy()
        if (
            counts["attempted_calls"] >= call_limit
            or counts["Adam_updates"] > adam_steps
        ):
            raise ValueError("FTT_INHERITED_WORK_LIMIT_EXHAUSTED")
        if phase == "Adam" and any(
            int(s["step"]) != counts["Adam_updates"] for s in optimizer.state.values()
        ):
            raise ValueError("FTT_ADAM_MOMENT_STEP_IDENTITY_MISMATCH")
    labelled = isinstance(metric, FieldMetric)
    c = mapping.forward(model)
    if resume_state is None and np.any(c):
        raise ValueError("STRICT_ZERO_SCATTERED_INITIALIZATION_REQUIRED")
    resume_pairing = None
    if resume_state is not None:
        saved = np.asarray(resume_state["c"])
        numerator = float(np.linalg.norm(c - saved))
        denominator = float(np.linalg.norm(saved))
        if denominator == 0 or numerator / denominator > 1e-10:
            raise ValueError("FTT_RESUME_FULL_COEFFICIENT_PAIRING_FAILED")
        residual = (
            c - metric.reference
            if isinstance(metric, FieldMetric)
            else action.apply(c) - action.f
        )
        old_r = np.asarray(resume_state["r"])
        r_num = float(np.linalg.norm(residual - old_r))
        r_den = float(np.linalg.norm(old_r))
        if r_den == 0 or r_num / r_den > 1e-10:
            raise ValueError("FTT_RESUME_RESIDUAL_PAIRING_FAILED")
        resume_pairing = dict(
            c_numerator=numerator,
            c_denominator=denominator,
            c_relative=numerator / denominator,
            r_numerator=r_num,
            r_denominator=r_den,
            r_relative=r_num / r_den,
        )
    audit_rows = []
    history = (artifact / "history.jsonl").open("a", buffering=1)
    last_audit = counts["complete_loss_gradient_calls"]
    stop_reason = "CALL_LIMIT"
    trial = None
    longest_closure_seconds = 0.0
    longest_save_seconds = 0.0

    def emit(row):
        history.write(json.dumps(row, allow_nan=False) + "\n")

    def save(update=None, pin=False):
        nonlocal c, longest_save_seconds
        whole_save_began = monotonic()
        c = mapping.forward(model)
        r = c - metric.reference if labelled else action.apply(c) - action.f
        metadata = dict(
            binding,
            phase=phase,
            counts=counts.copy(),
            deadline_monotonic=deadline,
            remaining_seconds=max(0, deadline - monotonic()),
            update=update,
            parameters_only=False,
            optimizer_recoverable=True,
            inherited_counts=inherited_counts,
            parent_checkpoint_sha256=(
                resume_identity["checkpoint"]["sha256"] if resume_identity else None
            ),
            r_kind="reference_coefficient_error"
            if labelled
            else "original_native_residual",
        )
        state = capture(model, optimizer, metadata)
        state.update(c=c, r=r)
        began = monotonic()
        record = store.save(state, pin=pin)
        costs["persistence"] += monotonic() - began
        longest_save_seconds = max(longest_save_seconds, monotonic() - whole_save_began)
        return record

    def audit(tag):
        nonlocal last_audit
        began = monotonic()
        row = dict(
            tag=tag, calls=counts["complete_loss_gradient_calls"], **action.audit(c)
        )
        counts["native_audits"] += 1
        last_audit = counts["complete_loss_gradient_calls"]
        audit_rows.append(row)
        costs["audit"] += monotonic() - began
        emit(dict(kind="persisted_committed_audit", **row))
        marker("committed_audit", row)
        return row

    zero = save(pin=True)
    audit("inherited_complete_boundary" if resume_state is not None else "zero")

    def closure():
        nonlocal trial, longest_closure_seconds
        # Finish the current complete update before the launcher soft cutoff;
        # the separate 150-second window remains available for the final save.
        projected_finish_seconds = 1.5 * longest_closure_seconds + longest_save_seconds
        if deadline - monotonic() <= projected_finish_seconds:
            raise StopFTT("TIME_LIMIT_WITH_SAVE_RESERVE")
        if counts["attempted_calls"] >= call_limit:
            raise StopFTT("CALL_LIMIT")
        counts["attempted_calls"] += 1
        began = monotonic()
        actual = mapping.forward(model)
        loss, residual, dual = metric.value(actual, gradient=True)
        gradient = mapping.vjp(model, dual)
        counts["complete_loss_gradient_calls"] += 1
        closure_seconds = monotonic() - began
        costs["closures"] += closure_seconds
        longest_closure_seconds = max(longest_closure_seconds, closure_seconds)
        if counts["complete_loss_gradient_calls"] <= 3:
            axis_gradients = {}
            for axis in range(3):
                group = [
                    p.grad.ravel()
                    for name, p in model.named_parameters()
                    if name.startswith(f"cores.{axis}.") or name == f"cores.{axis}"
                ]
                joined = torch.cat(group)
                axis_gradients[str(axis)] = float(
                    torch.sqrt(torch.mean(joined.square()))
                )
            emit(
                dict(
                    kind="initial_parameter_chain",
                    calls=counts["complete_loss_gradient_calls"],
                    axis_gradient_RMS=axis_gradients,
                )
            )
        trial = dict(
            parameters=torch.cat([p.detach().ravel() for p in params]).numpy().copy(),
            c=actual,
            residual=residual,
            loss=np.asarray(loss),
            committed=np.asarray(False),
            complete_calls=np.asarray(counts["complete_loss_gradient_calls"]),
        )
        emit(
            dict(
                kind="trial",
                calls=counts["complete_loss_gradient_calls"],
                loss=loss,
                gradient_norm=float(np.linalg.norm(gradient)),
                elapsed=closure_seconds,
            )
        )
        return torch.tensor(loss, dtype=torch.float64)

    try:
        while counts["attempted_calls"] < call_limit and monotonic() < deadline:
            if phase == "Adam" and counts["Adam_updates"] == adam_steps:
                save(pin=True)
                del optimizer
                optimizer = torch.optim.LBFGS(
                    params,
                    lr=1,
                    history_size=20,
                    line_search_fn="strong_wolfe",
                    max_iter=20,
                    max_eval=25,
                    tolerance_grad=1e-7,
                    tolerance_change=1e-9,
                )
                phase = "L-BFGS"
                save(pin=True)
            began = monotonic()
            committed_before = counts.copy()

            def persist(update):
                counts["committed_steps"] += 1
                counts["Adam_updates" if phase == "Adam" else "LBFGS_outer_steps"] += 1
                return save(update)

            try:
                _, record = optimizer_step(model, optimizer, closure, persist)
            except BaseException:
                # Work counters are never rolled back. Accepted updates are.
                for k in ("committed_steps", "Adam_updates", "LBFGS_outer_steps"):
                    counts[k] = committed_before[k]
                raise
            costs["optimizer_and_commit"] += monotonic() - began
            emit(
                dict(
                    kind="committed",
                    generation=record["generation"],
                    sha256=record["sha256"],
                    phase=phase,
                    calls=counts["complete_loss_gradient_calls"],
                    **record["metadata"]["update"],
                )
            )
            if (
                not labelled
                and counts["complete_loss_gradient_calls"] - last_audit >= 25
            ):
                row = audit("periodic_next_boundary")
                if (
                    max(
                        row[k]
                        for k in (
                            "native_relative",
                            "augmented_relative",
                            "original_total_augmented_relative",
                        )
                    )
                    <= 1e-8
                ):
                    stop_reason = "ORIGINAL_RESIDUAL_FREEZE_FOR_JOINT_VALIDATION"
                    break
            if record["metadata"]["update"]["accepted_update_norm"] == 0:
                stop_reason = "OPTIMIZER_NO_UPDATE"
                break
        if stop_reason == "CALL_LIMIT" and counts["attempted_calls"] < call_limit:
            stop_reason = "TIME_LIMIT_WITH_SAVE_RESERVE"
    except StopFTT as error:
        stop_reason = str(error)
        emit(
            dict(
                kind="rolled_back_incomplete_outer_step",
                reason=stop_reason,
                charged_calls=counts["complete_loss_gradient_calls"],
            )
        )
    finally:
        final_record = save(pin=True)
        audit("final")
        if trial is not None:
            atomic_write(
                artifact / "last_trial.npz", lambda stream: np.savez(stream, **trial)
            )
        residual = c - metric.reference if labelled else action.apply(c) - action.f
        atomic_write(
            artifact / "frozen_field.npz",
            lambda stream: np.savez(stream, c=c, r=residual),
        )
        atomic_json(artifact / "checkpoint_index.json", store.index())
        history.close()
    final_objective = metric.value(c)[0]
    return dict(
        status="FROZEN_NUMERICAL_CANDIDATE",
        stop_reason=stop_reason,
        final_objective=final_objective,
        final_E_G=float(np.sqrt(2 * final_objective)) if labelled else None,
        checkpoint=final_record,
        zero_checkpoint=zero,
        counts=counts,
        inherited_counts=inherited_counts,
        new_counts={k: counts[k] - inherited_counts[k] for k in counts},
        resume_pairing=resume_pairing,
        parent_checkpoint_sha256=(
            resume_identity["checkpoint"]["sha256"] if resume_identity else None
        ),
        costs=costs,
        mapping_costs=mapping.costs,
        mapping_counts=mapping.counts,
        core_costs=model.costs,
        budget_finish_guard=dict(
            longest_complete_closure_seconds=longest_closure_seconds,
            longest_complete_save_seconds=longest_save_seconds,
            next_closure_multiplier=1.5,
            launcher_soft_cutoff_monotonic=deadline,
        ),
        action_counts=action.counts,
        action_costs=action.costs,
        audits=audit_rows,
        Gsolve=0,
        global_Gram_factor=0,
        global_Maxwell_factor=0,
        G_matvec=getattr(metric, "count", 0),
        **binding,
    )
