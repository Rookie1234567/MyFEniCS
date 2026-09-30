"""Review V3 only: Adam500 -> fresh L-BFGS, supervised full-FE fit.

No Adam updates, reference solve, G inverse, or PDE loss enters this route.
"""

import ast
import json
import os
from pathlib import Path
import signal
import subprocess
from time import perf_counter

import numpy as np
import torch

from src.solvers.feinn_reference_fit import LABELS, FitMetric, load_problem, _relative
from src.solvers.feinn_optimization import RouteStop
from src.solvers.feinn_validation import assign, parameters
from src.solvers.neural_fe_action_packet import array_hash
from src.solvers.optimization_checkpoint import (
    CheckpointStore,
    atomic_json,
    atomic_write,
    capture,
    optimizer_step,
)
from src.runners.feinn_workflow import ROOT, sha

ROUTE = "FEINN-REFERENCE-FIT-G-ADAM500-REPLAY"
ADAM_SHA = "4e818a16b876ffd0776e74438654ca7de5632b1e17269a38e87749b5b3ad6a97"
OLD_SOURCE = "d9e5a7d00a1cac82390b058384e0cd9193b472d4"
LBFGS = dict(
    lr=1,
    history_size=20,
    max_iter=20,
    max_eval=25,
    line_search_fn="strong_wolfe",
    tolerance_grad=1e-7,
    tolerance_change=1e-9,
)
POLICY = dict(LABELS, pde_only_solver_qualified=False, official_candidate_results=False)


def _frozen_definition(relative, name):
    old = subprocess.check_output(
        ["git", "show", f"{OLD_SOURCE}:{relative}"], cwd=ROOT, text=True
    )
    current = (ROOT / relative).read_text()

    def definition(text):
        return ast.dump(
            next(x for x in ast.parse(text).body if getattr(x, "name", None) == name),
            include_attributes=False,
        )

    if definition(old) != definition(current):
        raise ValueError("FROZEN_NUMERICAL_DEFINITION_CHANGED: " + name)
    return sha(ROOT / relative)


def _load_adam(retained_index, model, label):
    entry = retained_index["files"]["checkpoint"]
    if entry["sha256"] != ADAM_SHA or sha(entry["path"]) != ADAM_SHA:
        raise ValueError("BOUNDARY_REPLAY_NOT_QUALIFIED_ADAM_HASH")
    with np.load(entry["path"], allow_pickle=False) as item:
        if (
            str(item["state_kind"]) != "adam500_parameter_only"
            or int(item["closures"]) != 500
            or int(item["committed_steps"]) != 500
            or str(item["reference_c_sha256"]) != label["reference_c_sha256"]
            or not bool(item["reference_used_for_training"])
            or bool(item["pde_only_solve"])
            or bool(item["production_initialization_allowed"])
        ):
            raise ValueError("BOUNDARY_REPLAY_NOT_QUALIFIED_STATE")
        p, c = np.array(item["parameters"]), np.array(item["c"])
    if p.shape != (8966,) or c.shape != (31968,):
        raise ValueError("BOUNDARY_REPLAY_NOT_QUALIFIED_SHAPE")
    assign(model, p)
    return p, c, entry


def boundary_checks(
    design, native_index, grad_index, reference_index, retained_index, artifact, marker
):
    proof = (
        ROOT / "docs/task042extra_feinn_5nm/outcomes/records/durability_checks_v4.json"
    )
    durability = json.loads(proof.read_text())
    if durability["status"] != "R0_SYNTHETIC_DURABILITY_PASS":
        raise ValueError("DURABILITY_TESTS_NOT_QUALIFIED")
    for record in durability["raw_evidence"]:
        if sha(record["path"]) != record["sha256"]:
            raise ValueError("DURABILITY_RAW_EVIDENCE_CHANGED")
    if (
        sha(ROOT / "input/materials/si_optical_constants_v1.json")
        != "55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2"
    ):
        raise ValueError("FROZEN_MATERIAL_HASH_CHANGED")
    definitions = dict(
        CoordinateField=_frozen_definition(
            "src/solvers/feinn_torch.py", "CoordinateField"
        ),
        CompleteMomentMap=_frozen_definition(
            "src/solvers/feinn_torch.py", "CompleteMomentMap"
        ),
        FitMetric=_frozen_definition("src/solvers/feinn_reference_fit.py", "FitMetric"),
    )
    old_fit = subprocess.check_output(
        ["git", "show", f"{OLD_SOURCE}:src/solvers/feinn_reference_fit.py"],
        cwd=ROOT,
        text=True,
    )
    if old_fit.index('artifact / "adam500_checkpoint.npz"') >= old_fit.index(
        "lbfgs = torch.optim.LBFGS"
    ):
        raise ValueError("ADAM500_NOT_BEFORE_FRESH_LBFGS")
    packet, metric, mapping, model, label = load_problem(
        design, native_index, grad_index, reference_index
    )
    p, saved, entry = _load_adam(retained_index, model, label)
    actual = mapping.forward(model, 8)
    loss, gc = metric.value(actual, True)
    gradient = mapping.vjp(model, gc, 8)
    old_metric = FitMetric(metric.G, metric.reference)
    old_loss, old_gc = old_metric.value(mapping.forward(model, 8), True)
    old_gradient = mapping.vjp(model, old_gc, 8)
    pairing = dict(
        c_relative=_relative(actual, saved),
        loss_relative=abs(loss - old_loss) / max(abs(old_loss), 1e-30),
        gradient_relative=_relative(gradient, old_gradient),
    )
    audit = packet.audit(actual)
    E_G = float(np.sqrt(2 * loss))
    if (
        max(pairing.values()) > 1e-10
        or pairing["c_relative"] > 1e-12
        or abs(E_G - 0.20082113406866917) > 1e-10
        or abs(audit["native_relative"] - 14.263463207213235) > 1e-8
    ):
        raise ValueError("BOUNDARY_REPLAY_NOT_QUALIFIED_PAIRING")
    optimizer = torch.optim.LBFGS(model.parameters(), **LBFGS)
    if optimizer.state:
        raise ValueError("FRESH_LBFGS_HISTORY_NOT_EMPTY")
    buffers = {
        name: buffer.detach().numpy().copy() for name, buffer in model.named_buffers()
    }
    if set(buffers) != {"center", "half_width"}:
        raise ValueError("UNEXPECTED_MODEL_BUFFERS")
    # Old NPZ omitted these deterministic geometry buffers. Their constructor
    # AST, frozen design, q15 c and gradient pairing qualify reconstruction.
    path = Path(artifact) / "qualified_adam500_boundary.npz"
    atomic_write(
        path,
        lambda stream: np.savez(stream, parameters=p, c=actual, **buffers, **POLICY),
    )
    result = dict(
        status="ADAM500_BOUNDARY_REPLAY_QUALIFIED",
        durability_checks_sha256=sha(proof),
        transition="ADAM500_TO_FRESH_LBFGS_BOUNDARY_REPLAY",
        original_Adam500_checkpoint=entry,
        inherited_committed_Adam_updates=500,
        real_M5_complete_loss_gradient_evaluations=2,
        boundary_E_G=E_G,
        native_audit=audit,
        pairing=pairing,
        definitions_unchanged_from=OLD_SOURCE,
        definition_hashes=definitions,
        buffer_policy="center and half_width deterministically reconstructed from frozen geometry; absent in old parameter-only NPZ",
        buffers_sha256={k: array_hash(v) for k, v in buffers.items()},
        fresh_LBFGS_state_empty=True,
        optimizer=LBFGS,
        no_Adam_updates=True,
        no_Gsolve=True,
        no_Gram_factor=True,
        **POLICY,
    )
    marker(
        "adam500_boundary_qualification",
        dict(E_G=E_G, native=audit["native_relative"], pairing=pairing),
    )
    return result, dict(boundary=path)


def run_replay(
    design,
    native_index,
    grad_index,
    reference_index,
    retained_index,
    checks_index,
    artifact,
    marker,
    wall_seconds,
    manifest,
):
    began = perf_counter()
    if checks_index["result"][
        "status"
    ] != "ADAM500_BOUNDARY_REPLAY_QUALIFIED" or not os.environ.get(
        "TASK42EXTRA_PARENT_DEATH_GUARD"
    ):
        raise ValueError("BOUNDARY_OR_PARENT_GUARD_NOT_QUALIFIED")
    packet, metric, mapping, model, label = load_problem(
        design, native_index, grad_index, reference_index
    )
    initial, saved, entry = _load_adam(retained_index, model, label)
    with np.load(
        checks_index["files"]["boundary"]["path"], allow_pickle=False
    ) as qualified:
        for name, buffer in model.named_buffers():
            value = np.array(qualified[name])
            if array_hash(value) != checks_index["result"]["buffers_sha256"][name]:
                raise ValueError("QUALIFIED_BUFFER_IDENTITY_CHANGED")
            buffer.copy_(torch.from_numpy(value))
    actual = mapping.forward(model, 8)
    if _relative(actual, saved) > 1e-12:
        raise ValueError("REPLAY_BOUNDARY_COEFFICIENTS_CHANGED")
    optimizer = torch.optim.LBFGS(model.parameters(), **LBFGS)
    if optimizer.state:
        raise ValueError("REPLAY_MUST_START_WITH_EMPTY_LBFGS")
    artifact = Path(artifact)
    store = CheckpointStore(artifact / "durable_checkpoints")
    history_path = artifact / "history.jsonl"
    history = history_path.open("w", buffering=1)
    counts = dict(
        new_complete_fit_closures=0,
        closure_attempts=0,
        outer_attempts=0,
        committed_outer_steps=0,
        LBFGS_inner_iterations=0,
        native_audits=0,
        inherited_committed_Adam_updates=500,
    )
    bound_count = 0
    stop_reason = "NEW_CLOSURE_BUDGET"
    audits, last_audit_count = [], -1
    trial_p, trial_c = initial.copy(), actual.copy()
    trial_loss = metric.value(actual)[0]
    closure_wall = 0.0
    deadline = began + min(10800, wall_seconds) - 120
    checkpoint_seconds = 0.0
    failure = None
    stop_requested = False

    def metadata(kind, proposed=None, update=None):
        return dict(
            state_kind=kind,
            run_id=manifest["run_id"],
            stage=ROUTE,
            source_sha=manifest["source_sha"],
            input_sha256=manifest["input_sha256"],
            label_state_sha256=label["reference_state"]["sha256"],
            reference_c_sha256=label["reference_c_sha256"],
            native_sha256=label["native_sha256"],
            Gram_sha256=label["gram_sha256"],
            moments_sha256=label["moments_sha256"],
            buffers_sha256=checks_index["result"]["buffers_sha256"],
            original_Adam500_checkpoint_sha256=entry["sha256"],
            counts=dict(proposed or counts),
            logical_path_closures=500 + counts["new_complete_fit_closures"],
            committed_complete_fit_closures=bound_count,
            elapsed_seconds=perf_counter() - began,
            wall_limit_seconds=min(10800, wall_seconds),
            final_reserve_seconds=120,
            closure_limit=3500,
            RNG_policy="torch, numpy and Python RNG state captured; no stochastic operations in fit/line search",
            **(update or {}),
            **POLICY,
        )

    def save(kind, *, c=None, pin=False, proposed=None, update=None):
        nonlocal checkpoint_seconds
        t = perf_counter()
        state = capture(model, optimizer, metadata(kind, proposed, update))
        if c is not None:
            state["complete_c"] = np.array(c)
            state["metadata"]["complete_c_sha256"] = array_hash(c)
        record = store.save(state, pin=pin)
        checkpoint_seconds += perf_counter() - t
        return record

    def emit(row, sync=False):
        history.write(json.dumps(row, allow_nan=False) + "\n")
        if sync:
            history.flush()
            os.fsync(history.fileno())

    def audit(c, tag, checkpoint):
        nonlocal last_audit_count
        if counts["native_audits"] >= 40:
            raise ValueError("REPLAY_NATIVE_AUDIT_LIMIT")
        loss = metric.value(c)[0]
        row = dict(
            tag=tag,
            new_complete_fit_closures=counts["new_complete_fit_closures"],
            committed_complete_fit_closures=bound_count,
            logical_path_closures=500 + counts["new_complete_fit_closures"],
            checkpoint=checkpoint,
            fit_loss=loss,
            E_G=float(np.sqrt(2 * loss)),
            **packet.audit(c),
        )
        counts["native_audits"] += 1
        last_audit_count = counts["new_complete_fit_closures"]
        audits.append(row)
        emit(dict(kind="durable_committed_audit", **row), sync=True)
        print(
            json.dumps(
                dict(
                    kind="durable_fit_audit",
                    new_closures=row["new_complete_fit_closures"],
                    E_G=row["E_G"],
                    native=row["native_relative"],
                    checkpoint=checkpoint["name"],
                )
            ),
            flush=True,
        )
        return row

    anchor = save("adam500_to_fresh_lbfgs_boundary", c=actual, pin=True)
    audit(actual, "inherited_adam500", anchor)

    def closure():
        nonlocal trial_p, trial_c, trial_loss, stop_reason, closure_wall
        if (
            stop_requested
            or counts["new_complete_fit_closures"] >= 3500
            or perf_counter() >= deadline
        ):
            stop_reason = (
                "OWN_WATCHDOG_STOP"
                if stop_requested
                else "WALL_BUDGET"
                if perf_counter() >= deadline
                else "NEW_CLOSURE_BUDGET"
            )
            raise RouteStop
        t = perf_counter()
        counts["closure_attempts"] += 1
        trial_p = parameters(model)
        trial_c = mapping.forward(model, 8)
        trial_loss, gc = metric.value(trial_c, True)
        gradient = mapping.vjp(model, gc, 8)
        if not np.isfinite(trial_loss) or not np.isfinite(gradient).all():
            stop_reason = "NONFINITE"
            raise RouteStop
        counts["new_complete_fit_closures"] += 1
        closure_wall += perf_counter() - t
        if counts["new_complete_fit_closures"] % 25 == 0:
            emit(
                dict(
                    kind="trial_closure",
                    new_complete_fit_closures=counts["new_complete_fit_closures"],
                    logical_path_closures=500 + counts["new_complete_fit_closures"],
                    loss=trial_loss,
                    E_G=float(np.sqrt(2 * trial_loss)),
                    parameter_gradient_norm=float(np.linalg.norm(gradient)),
                    trial_displacement_from_outer_start=float(
                        np.linalg.norm(trial_p - before)
                    ),
                    elapsed_seconds=perf_counter() - began,
                )
            )
        return torch.tensor(trial_loss, dtype=torch.float64)

    def terminate(_sig, _frame):
        nonlocal stop_requested
        # Never interrupt an in-flight durable publication halfway through its
        # commit protocol. SIGKILL still has no finally guarantee.
        stop_requested = True

    old_signal = signal.signal(signal.SIGTERM, terminate)
    try:
        while counts["new_complete_fit_closures"] < 3500:
            counts["outer_attempts"] += 1
            before = parameters(model)

            def persist(update):
                nonlocal bound_count
                proposed = dict(counts)
                proposed["committed_outer_steps"] += 1
                proposed["LBFGS_inner_iterations"] = int(
                    optimizer.state[list(model.parameters())[0]].get("n_iter", 0)
                )
                new_count = counts["new_complete_fit_closures"]
                previous_count = bound_count
                bound_count = new_count
                needs_audit = new_count // 100 > last_audit_count // 100
                try:
                    c = mapping.forward(model, 8) if needs_audit else None
                    record = save(
                        "complete_LBFGS_outer_step",
                        c=c,
                        pin=needs_audit,
                        proposed=proposed,
                        update=update,
                    )
                except BaseException:
                    bound_count = previous_count
                    raise
                return record, c, proposed, update

            _, (record, c, proposed, update) = optimizer_step(
                model, optimizer, closure, persist
            )
            counts.update(proposed)
            emit(
                dict(kind="durable_committed_step", checkpoint=record, **update),
                sync=True,
            )
            if (
                c is not None
                and audit(c, "lbfgs_complete_outer", record)["E_G"] <= 1e-3
            ):
                stop_reason = "FIT_THRESHOLD_REACHED"
                break
            if np.array_equal(before, parameters(model)):
                stop_reason = "OPTIMIZER_STAGNATION"
                break
    except RouteStop:
        pass
    except BaseException as error:
        failure = dict(kind=type(error).__name__, reason=str(error))
        stop_reason = "UNEXPECTED_FAILURE_SAVED_BOUNDARY"
    finally:
        signal.signal(signal.SIGTERM, old_signal)
    # optimizer_step restored matching parameters/history if its closure failed.
    final_c = mapping.forward(model, 8)
    final_record = save(
        "final_committed" if failure is None else "unexpected_exit_retained_boundary",
        c=final_c,
        pin=True,
    )
    audit(
        final_c,
        "final_committed" if failure is None else "retained_after_failure",
        final_record,
    )
    frozen = artifact / "frozen_checkpoint.npz"
    buffers = {
        name: value.detach().numpy().copy() for name, value in model.named_buffers()
    }
    atomic_write(
        frozen,
        lambda stream: np.savez(
            stream,
            parameters=parameters(model),
            c=final_c,
            state_kind="final_committed" if failure is None else "unexpected_exit_retained_boundary",
            source_sha=manifest["source_sha"],
            input_sha256=manifest["input_sha256"],
            run_id=manifest["run_id"],
            durable_checkpoint_sha256=final_record["sha256"],
            reference_state_sha256=label["reference_state"]["sha256"],
            reference_c_sha256=label["reference_c_sha256"],
            new_complete_fit_closures=counts["new_complete_fit_closures"],
            committed_complete_fit_closures=bound_count,
            **buffers,
            **POLICY,
        ),
    )
    trial_path = artifact / "last_trial.npz"
    atomic_write(
        trial_path,
        lambda stream: np.savez(
            stream,
            parameters=trial_p,
            c=trial_c,
            loss=trial_loss,
            state_kind="not_committed_last_trial",
            **POLICY,
        ),
    )
    checkpoint_index = artifact / "checkpoint_index.json"
    atomic_json(
        checkpoint_index,
        dict(
            schema="task42extra.checkpoint-index.v4",
            guarantee="only successfully fsynced complete boundary survives SIGKILL; no finally guarantee",
            current=final_record,
            checkpoints=store.index(),
            optimizer_state_saved=True,
            resumability_qualified_by_small_problem_tests=True,
            automatic_resume_authorized=False,
        ),
    )
    history.close()
    result = dict(
        status="DURABLE_BOUNDARY_REPLAY_COMPLETE"
        if failure is None
        else "INTERRUPTED_REPLAY_RETAINED_BOUNDARY",
        route=ROUTE,
        transition="ADAM500_TO_FRESH_LBFGS_BOUNDARY_REPLAY",
        stop_reason=stop_reason,
        failure=failure,
        counts=counts,
        inherited_committed_Adam_updates=500,
        new_complete_fit_closures=counts["new_complete_fit_closures"],
        logical_path_closures=500 + counts["new_complete_fit_closures"],
        committed_complete_fit_closures=bound_count,
        final_checkpoint=final_record,
        final_audit=audits[-1],
        audits=audits,
        final_fit_parameters_retained=failure is None,
        consistent_optimizer_state_retained=True,
        no_Adam_updates=True,
        original_Adam500_checkpoint=entry,
        labels=label,
        checkpoint_seconds=checkpoint_seconds,
        checkpoint_payload_bytes_retained=sum(
            x["bytes"] for x in store.index() if x["retained"]
        ),
        Gsolve_count=0,
        Gram_factor_created=False,
        G_matvec_count=metric.matvec_count,
        G_matvec_seconds=metric.matvec_seconds,
        native_action_counts=packet.counts,
        moment_counts=mapping.counts,
        moment_costs=mapping.costs,
        wall_seconds=perf_counter() - began,
        closure_wall_seconds_nested=closure_wall,
        pde_only_solver_qualified=False,
        official_candidate_results=False,
        **LABELS,
    )
    marker(
        "durable_replay_frozen",
        dict(
            status=result["status"],
            stop_reason=stop_reason,
            new_closures=counts["new_complete_fit_closures"],
            E_G=audits[-1]["E_G"],
        ),
    )
    return result, dict(
        checkpoint=frozen,
        last_trial=trial_path,
        history=history_path,
        checkpoint_index=checkpoint_index,
        durable_final=store.directory / final_record["name"],
    )
