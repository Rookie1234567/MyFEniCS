"""V8 fresh full-FE plain/phase optimization with durable transactions.

PDE loads only native/Gram/moments. Supervised representation is a separate
explicit entry and never supplies a state to the PDE routes.
"""

import copy
import json
import os
from pathlib import Path
import signal
import sys
from time import perf_counter

import numpy as np
from scipy import sparse
import torch

from src.solvers.feinn_phase import make_model, PhaseCoordinateField
from src.solvers.feinn_torch import CoordinateField, CompleteMomentMap
from src.solvers.feinn_validation import parameters, assign, load_moments, paired
from src.solvers.feinn_native import load_native, ResidualMetric
from src.solvers.feinn_riesz import SparseRiesz
from src.solvers.feinn_reference_fit import FitMetric
from src.solvers.feinn_optimization import RouteStop
from src.solvers.neural_fe_action_packet import array_hash
from src.solvers.optimization_checkpoint import (
    CheckpointStore,
    atomic_json,
    atomic_write,
    capture,
    optimizer_step,
)

LBFGS = dict(
    lr=1,
    history_size=20,
    max_iter=20,
    max_eval=25,
    line_search_fn="strong_wolfe",
    tolerance_grad=1e-7,
    tolerance_change=1e-9,
)


def policy(supervised):
    return dict(
        reference_used_for_training=supervised,
        features_reference_exposed=supervised,
        pde_only_solve=not supervised,
        benchmark_previously_seen=True,
        production_initialization_allowed=False,
        pde_only_solver_qualified=False,
        official_candidate_results=False,
    )


def configure():
    torch.set_num_threads(1)
    if torch.get_num_interop_threads() != 1:
        torch.set_num_interop_threads(1)
    if torch.version.cuda is not None or len(os.sched_getaffinity(0)) != 1:
        raise ValueError("CPU_ONLY_SINGLE_CORE_REQUIRED")


def qualify(design, native_index, prepared, artifact, marker, manifest):
    configure()
    if prepared["result"]["status"] != "PHASE_FE_MOMENTS_PASS":
        raise ValueError("PHASE_FE_MOMENTS_NOT_QUALIFIED")
    packet = load_native(native_index["files"]["native"]["path"])
    maps = {
        q: CompleteMomentMap(load_moments(prepared["files"][f"moments_q{q}"]["path"]))
        for q in (15, 30, 60)
    }
    initial = parameters(make_model(design, False))
    if not np.array_equal(initial, parameters(make_model(design, True))):
        raise ValueError("PLAIN_PHASE_INITIAL_PARAMETERS_DIFFER")
    rng = np.random.default_rng(421002)
    p = initial + 0.005 * rng.normal(size=len(initial))
    quadrature = {}
    for phase in (False, True):
        model = make_model(design, phase)
        assign(model, p)
        values = {q: maps[q].forward(model) for q in maps}
        quadrature["phase" if phase else "plain"] = dict(
            q15_q30=paired(values[15], values[30]),
            q30_q60=paired(values[30], values[60]),
        )
        marker(
            "phase_quadrature_pair",
            dict(phase=phase, **quadrature["phase" if phase else "plain"]),
        )
    if any(x["q30_q60"]["relative"] > 1e-8 for x in quadrature.values()):
        raise ValueError("NETWORK_MOMENT_QUADRATURE_UNRESOLVED")
    q = 15 if all(x["q15_q30"]["relative"] <= 1e-8 for x in quadrature.values()) else 30
    mapping = maps[q]
    zero_carrier = PhaseCoordinateField(
        design["geometry"]["bounds_nm"], k_inc=np.zeros(3)
    )
    plain = CoordinateField(design["geometry"]["bounds_nm"])
    assign(zero_carrier, p)
    assign(plain, p)
    k0 = paired(mapping.forward(zero_carrier), mapping.forward(plain))
    if k0["relative"] > 1e-10:
        raise ValueError("ZERO_PHASE_REGRESSION_FAILED")
    # q60 is released before the fresh Gram setup when q15 is qualified.
    del maps
    gram = SparseRiesz(
        sparse.load_npz(native_index["files"]["gram"]["path"]), design, marker
    )
    results = {}
    try:
        metric = ResidualMetric(packet, gram)
        for phase in (False, True):
            model = make_model(design, phase)
            assign(model, p)
            c8 = mapping.forward(model, 8)
            c1 = mapping.forward(model, 1)
            loss8, _, dual8 = metric.value(c8, gradient=True)
            g8 = mapping.vjp(model, dual8, 8)
            loss1, _, dual1 = metric.value(c1, gradient=True)
            g1 = mapping.vjp(model, dual1, 1)
            hidden = g8.copy()
            hidden[-390:] = 0
            last = g8.copy()
            last[:-390] = 0
            directions = [hidden, last, rng.normal(size=len(p))]
            differences = []
            for number, d in enumerate(directions):
                d /= np.linalg.norm(d)
                exact = float(g8 @ d)
                if abs(exact) <= 1e-10:
                    raise ValueError("NONZERO_PHASE_DERIVATIVE_REQUIRED")
                samples = []
                for h in (1e-4, 1e-5, 1e-6):
                    assign(model, p + h * d)
                    plus = metric.value(mapping.forward(model))[0]
                    assign(model, p - h * d)
                    minus = metric.value(mapping.forward(model))[0]
                    fd = (plus - minus) / (2 * h)
                    relative = abs(fd - exact) / abs(exact)
                    samples.append(
                        dict(h=h, analytic=exact, observed=fd, relative=relative)
                    )
                stable = any(
                    samples[i]["relative"] <= 1e-5
                    and samples[i + 1]["relative"] <= 1e-5
                    for i in (0, 1)
                )
                differences.append(
                    dict(
                        direction=("hidden", "last", "random")[number],
                        samples=samples,
                        two_consecutive_pass=stable,
                    )
                )
            assign(model, p)
            updates = []
            for gradient in (g1, g8):
                clone = copy.deepcopy(model)
                opt = torch.optim.Adam(clone.parameters(), lr=1e-3, weight_decay=0)
                offset = 0
                for par in clone.parameters():
                    par.grad = torch.tensor(
                        gradient[offset : offset + par.numel()].reshape(par.shape)
                    )
                    offset += par.numel()
                opt.step()
                updates.append(parameters(clone))
            batch = dict(
                c=paired(c1, c8),
                loss=paired(loss1, loss8),
                VJP=paired(g1, g8),
                clone_update=paired(updates[0], updates[1]),
            )
            passed = all(x["relative"] <= 1e-10 for x in batch.values()) and all(
                x["two_consecutive_pass"] for x in differences
            )
            results["phase" if phase else "plain"] = dict(
                batch=batch, directional_derivatives=differences, passed=passed
            )
            marker(
                "qualified_new_dual_gradient",
                dict(phase=phase, **results["phase" if phase else "plain"]),
            )
        if not all(x["passed"] for x in results.values()):
            raise ValueError("PHASE_GRADIENT_BATCH_NOT_QUALIFIED")
    finally:
        gram.close()
    return dict(
        status="PHASE_INTERFACE_PASS_ONLY",
        quadrature=quadrature,
        network_quadrature_degree=q,
        operator_quadrature_degree=15,
        k_zero=k0,
        gradients=results,
        initial_parameters_sha256=array_hash(initial),
        initial_zero_scattered=True,
        Gram_qualification_factor=gram.record,
        reference_loaded=False,
        max_graph_cells=8,
    ), dict(
        moments=Path(prepared["files"][f"moments_q{q}"]["path"]),
        moments_next=Path(
            prepared["files"][f"moments_q{30 if q == 15 else 60}"]["path"]
        ),
    )


def install_data_guard(allowed, artifact, *, supervised):
    """Audit every artifact read; imports/environment outside artifacts remain.

    Writes are restricted to this run by the filesystem/launcher. The data
    guard is supplementary, not a sandbox replacement.
    """
    from src.runners.feinn_resources import ARTIFACTS

    root = ARTIFACTS.resolve()
    allowed = {Path(p).resolve() for p in allowed}
    reads = []

    def guard(event, args):
        if event != "open" or not isinstance(args[0], (str, bytes, os.PathLike)):
            return
        path = Path(os.fsdecode(args[0])).resolve()
        if not path.is_relative_to(root):
            return
        mode, flags = args[1], args[2]
        write = (isinstance(mode, str) and any(x in mode for x in "wax+")) or (
            flags is not None and bool(flags & (os.O_WRONLY | os.O_RDWR))
        )
        if write or path.is_relative_to(Path(artifact).resolve()):
            return
        if path not in allowed:
            raise PermissionError("TRAINING_DATA_WHITELIST_REJECTED: " + str(path))
        if not supervised and "reference" in path.name.lower():
            raise PermissionError("PDE_REFERENCE_LABEL_FORBIDDEN")
        reads.append(str(path))

    sys.addaudithook(guard)
    return reads


def fit_gradient_checks(model, mapping, metric):
    """Nonzero fit directions, checked before this route starts from zero."""
    initial = parameters(model)
    rng = np.random.default_rng(421002)
    base = initial + 0.005 * rng.normal(size=len(initial))
    assign(model, base)
    c1, c8 = mapping.forward(model, 1), mapping.forward(model, 8)
    loss1, d1 = metric.value(c1, True)
    loss8, d8 = metric.value(c8, True)
    g1, g8 = mapping.vjp(model, d1, 1), mapping.vjp(model, d8, 8)
    batch = dict(c=paired(c1, c8), loss=paired(loss1, loss8), VJP=paired(g1, g8))
    hidden = g8.copy()
    hidden[-390:] = 0
    last = g8.copy()
    last[:-390] = 0
    rows = []
    try:
        for name, direction in zip(
            ("hidden", "last", "random"),
            (hidden, last, rng.normal(size=len(base))),
            strict=True,
        ):
            direction /= np.linalg.norm(direction)
            exact = float(g8 @ direction)
            if abs(exact) <= 1e-10:
                raise ValueError("NONZERO_FIT_DIRECTION_REQUIRED")
            samples = []
            for h in (1e-4, 1e-5, 1e-6):
                assign(model, base + h * direction)
                plus = metric.value(mapping.forward(model))[0]
                assign(model, base - h * direction)
                minus = metric.value(mapping.forward(model))[0]
                fd = (plus - minus) / (2 * h)
                samples.append(
                    dict(
                        h=h,
                        analytic=exact,
                        observed=fd,
                        relative=abs(fd - exact) / abs(exact),
                    )
                )
            rows.append(
                dict(
                    direction=name,
                    samples=samples,
                    passed=any(
                        samples[i]["relative"] <= 1e-5
                        and samples[i + 1]["relative"] <= 1e-5
                        for i in (0, 1)
                    ),
                )
            )
        if any(x["relative"] > 1e-10 for x in batch.values()) or not all(
            x["passed"] for x in rows
        ):
            raise ValueError("FIT_GRADIENT_BATCH_NOT_QUALIFIED")
        return dict(batch=batch, directions=rows, nonzero_real_gradient_pass=True)
    finally:
        assign(model, initial)
        model.zero_grad(set_to_none=True)


def run(
    design,
    native_index,
    qualification,
    artifact,
    marker,
    manifest,
    *,
    phase,
    supervised,
    reference_index=None,
):
    configure()
    started = perf_counter()
    artifact = Path(artifact)
    if qualification["result"]["status"] != "PHASE_INTERFACE_PASS_ONLY":
        raise ValueError("NEW_PHASE_INTERFACE_NOT_QUALIFIED")
    if supervised != (reference_index is not None):
        raise ValueError("EXPLICIT_LABEL_ROLE_REQUIRED")
    allowed = [native_index["files"][k]["path"] for k in ("native", "gram")] + [
        qualification["files"]["moments"]["path"]
    ]
    if supervised:
        allowed.append(reference_index["files"]["reference"]["path"])
    reads = install_data_guard(allowed, artifact, supervised=supervised)
    packet = load_native(native_index["files"]["native"]["path"])
    mapping = CompleteMomentMap(load_moments(qualification["files"]["moments"]["path"]))
    model = make_model(design, phase)
    initial = parameters(model)
    if array_hash(initial) != qualification["result"]["initial_parameters_sha256"]:
        raise ValueError("CANDIDATE_INITIALIZATION_CHANGED")
    gram = None
    labels = policy(supervised)
    G = sparse.load_npz(native_index["files"]["gram"]["path"])
    if supervised:
        from src.solvers.feinn_error_geometry import reference_label

        reference, label_identity = reference_label(
            native_index, reference_index, packet, used_for_training=True
        )
        metric = FitMetric(G, reference)
        fit_interface = fit_gradient_checks(model, mapping, metric)
        marker("fit_gradient_qualified", fit_interface)
    else:
        fit_interface = None
        label_identity = None
        gram = SparseRiesz(G, design, marker)
        metric = ResidualMetric(packet, gram)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=0)
    store = CheckpointStore(artifact / "durable_checkpoints")
    history_path = artifact / "history.jsonl"
    history = history_path.open("w", buffering=1)
    counts = dict(
        complete_closures=0,
        closure_attempts=0,
        committed_outer_steps=0,
        Adam_updates=0,
        LBFGS_outer_steps=0,
        LBFGS_inner_iterations=0,
        native_audits=0,
    )
    limit = 1500 if supervised else 4000
    # Thirty extra seconds allow a closure in flight to reach the mandated
    # 150-second watchdog cutoff; no candidate may consume the 120s reserve.
    cutoff = (
        float(manifest["supervision_budget_origin_monotonic"])
        + float(manifest["supervised_limit_seconds"])
        - 180
    )
    stage = "Adam"
    bound = 0
    last_audit = -1
    stop_requested = False
    failure = None
    stop_reason = "CLOSURE_BUDGET"
    audit_rows = []
    trial_p = initial.copy()
    trial_c = mapping.forward(model)
    trial_loss = metric.value(trial_c)[0]
    if np.any(trial_c):
        raise ValueError("CANDIDATE_MUST_START_ZERO_SCATTERED")
    costs = dict(checkpoint=0.0, closure_nested=0.0, optimizer_exclusive=0.0)
    route = ("V8-PHASE" if phase else "V8-PLAIN") + (
        "-REFERENCE-FIT" if supervised else "-DUAL"
    )

    def metadata(kind, proposed=None, update=None):
        return dict(
            state_kind=kind,
            route=route,
            stage=stage,
            source_sha=manifest["source_sha"],
            input_sha256=manifest["input_sha256"],
            run_id=manifest["run_id"],
            counts=dict(proposed or counts),
            committed_complete_closures=bound,
            initial_parameters_sha256=array_hash(initial),
            native_sha256=native_index["files"]["native"]["sha256"],
            Gram_sha256=native_index["files"]["gram"]["sha256"],
            moments_sha256=qualification["files"]["moments"]["sha256"],
            label_identity=label_identity,
            elapsed_charged_seconds=perf_counter()
            - manifest["supervision_budget_origin_monotonic"],
            closure_limit=limit,
            wall_limit_seconds=manifest["supervised_limit_seconds"],
            closure_cutoff_monotonic=cutoff,
            buffers_sha256={
                n: array_hash(b.detach().numpy()) for n, b in model.named_buffers()
            },
            **labels,
            **(update or {}),
        )

    def save(kind, c=None, pin=False, proposed=None, update=None):
        start = perf_counter()
        state = capture(model, optimizer, metadata(kind, proposed, update))
        if c is not None:
            state["complete_c"] = c.copy()
            state["metadata"]["complete_c_sha256"] = array_hash(c)
        rec = store.save(state, pin=pin)
        costs["checkpoint"] += perf_counter() - start
        return rec

    def emit(row):
        history.write(json.dumps(row, allow_nan=False) + "\n")
        history.flush()
        os.fsync(history.fileno())

    def audit(c, tag, checkpoint):
        nonlocal last_audit
        audit = packet.audit(c)
        counts["native_audits"] += 1
        last_audit = counts["complete_closures"]
        value = metric.value(c)[0]
        row = dict(
            tag=tag,
            complete_closures=counts["complete_closures"],
            committed_complete_closures=bound,
            checkpoint=checkpoint,
            loss=value,
            **audit,
        )
        if supervised:
            row["E_G"] = float(np.sqrt(2 * value))
        audit_rows.append(row)
        emit(dict(kind="durable_committed_audit", **row))
        print(
            json.dumps(
                dict(
                    kind="V8_audit",
                    route=route,
                    closures=counts["complete_closures"],
                    loss=value,
                    native=audit["native_relative"],
                    E_G=row.get("E_G"),
                )
            ),
            flush=True,
        )
        return row

    initial_record = save("zero", trial_c, True)
    audit(trial_c, "zero", initial_record)

    def closure():
        nonlocal trial_p, trial_c, trial_loss, stop_reason
        if (
            stop_requested
            or counts["complete_closures"] >= limit
            or perf_counter() >= cutoff
        ):
            stop_reason = (
                "OWN_WATCHDOG_STOP"
                if stop_requested
                else "WALL_BUDGET"
                if perf_counter() >= cutoff
                else "CLOSURE_BUDGET"
            )
            raise RouteStop
        start = perf_counter()
        counts["closure_attempts"] += 1
        trial_p = parameters(model)
        trial_c = mapping.forward(model)
        if supervised:
            trial_loss, dual = metric.value(trial_c, True)
        else:
            trial_loss, _, dual = metric.value(trial_c, gradient=True)
        gradient = mapping.vjp(model, dual)
        if not np.isfinite(trial_loss) or not np.isfinite(gradient).all():
            raise ValueError("NONFINITE_LOSS_OR_GRADIENT")
        counts["complete_closures"] += 1
        costs["closure_nested"] += perf_counter() - start
        if counts["complete_closures"] % 25 == 0:
            emit(
                dict(
                    kind="trial_closure",
                    closure=counts["complete_closures"],
                    stage=stage,
                    loss=trial_loss,
                    gradient_norm=float(np.linalg.norm(gradient)),
                    elapsed_seconds=perf_counter() - started,
                )
            )
        return torch.tensor(trial_loss, dtype=torch.float64)

    def terminate(_sig, _frame):
        nonlocal stop_requested
        stop_requested = True

    old_signal = signal.signal(signal.SIGTERM, terminate)
    try:
        while counts["complete_closures"] < limit:
            if stage == "Adam" and counts["Adam_updates"] >= 500:
                stage = "LBFGS"
                optimizer = torch.optim.LBFGS(model.parameters(), **LBFGS)
                boundary_c = mapping.forward(model)
                transition = save("Adam500_to_fresh_LBFGS", boundary_c, True)
                emit(
                    dict(
                        kind="stage_transition",
                        checkpoint=transition,
                        empty_history=True,
                    )
                )
            before = parameters(model)
            closure_before = costs["closure_nested"]
            checkpoint_before = costs["checkpoint"]
            persisted_forward_seconds = 0.0

            def persist(update):
                nonlocal bound, persisted_forward_seconds
                proposed = dict(counts)
                proposed["committed_outer_steps"] += 1
                proposed[
                    "Adam_updates" if stage == "Adam" else "LBFGS_outer_steps"
                ] += 1
                if stage == "LBFGS":
                    proposed["LBFGS_inner_iterations"] = int(
                        optimizer.state[list(model.parameters())[0]].get("n_iter", 0)
                    )
                previous = bound
                bound = counts["complete_closures"]
                need = (
                    bound // 100 > last_audit // 100
                    or stage == "Adam"
                    and proposed["Adam_updates"] == 500
                )
                try:
                    forward_start = perf_counter()
                    c = mapping.forward(model) if need else None
                    persisted_forward_seconds = perf_counter() - forward_start
                    record = save(
                        "Adam500"
                        if stage == "Adam" and proposed["Adam_updates"] == 500
                        else "complete_outer_step",
                        c,
                        need,
                        proposed,
                        update,
                    )
                except BaseException:
                    bound = previous
                    raise
                return record, c, proposed, update

            start = perf_counter()
            _, (record, c, proposed, update) = optimizer_step(
                model, optimizer, closure, persist
            )
            costs["optimizer_exclusive"] += max(
                0,
                perf_counter()
                - start
                - (costs["closure_nested"] - closure_before)
                - (costs["checkpoint"] - checkpoint_before)
                - persisted_forward_seconds,
            )
            counts.update(proposed)
            emit(dict(kind="durable_committed_step", checkpoint=record, **update))
            if c is not None:
                row = audit(c, "committed_outer", record)
                if not supervised and row["strict_pass"]:
                    stop_reason = "ORIGINAL_EQUATION_THRESHOLD_REACHED"
                    break
                if supervised and row["E_G"] <= 1e-3:
                    stop_reason = "FIT_THRESHOLD_REACHED"
                    break
            if np.array_equal(before, parameters(model)):
                stop_reason = "OPTIMIZER_STAGNATION"
                break
    except RouteStop:
        pass
    except BaseException as error:
        failure = dict(kind=type(error).__name__, reason=str(error))
        stop_reason = "ENGINEERING_FAILURE_RETAINED_BOUNDARY"
    finally:
        signal.signal(signal.SIGTERM, old_signal)
    final_c = mapping.forward(model)
    record = save(
        "final_committed" if failure is None else "retained_failure_boundary",
        final_c,
        True,
    )
    final_audit = audit(
        final_c,
        "final_committed" if failure is None else "retained_failure_boundary",
        record,
    )
    buffers = {n: b.detach().numpy().copy() for n, b in model.named_buffers()}
    frozen = artifact / "frozen_checkpoint.npz"
    atomic_write(
        frozen,
        lambda stream: np.savez(
            stream,
            parameters=parameters(model),
            c=final_c,
            source_sha=manifest["source_sha"],
            input_sha256=manifest["input_sha256"],
            state_kind="final_committed"
            if failure is None
            else "retained_failure_boundary",
            route=route,
            phase=phase,
            complete_closures=counts["complete_closures"],
            committed_complete_closures=bound,
            durable_checkpoint_sha256=record["sha256"],
            **buffers,
            **labels,
        ),
    )
    trial = artifact / "last_trial.npz"
    atomic_write(
        trial,
        lambda stream: np.savez(
            stream,
            parameters=trial_p,
            c=trial_c,
            loss=trial_loss,
            state_kind="not_committed_last_trial",
            route=route,
            phase=phase,
            **labels,
        ),
    )
    checkpoint_index = artifact / "checkpoint_index.json"
    atomic_json(
        checkpoint_index,
        dict(
            current=record,
            checkpoints=store.index(),
            optimizer_state_saved=True,
            fault_resume_limit=2,
            guarantee="last successful fsync boundary; no SIGKILL finally guarantee",
        ),
    )
    history.close()
    if gram is not None:
        gram.close()
    result = dict(
        status="V8_CANDIDATE_FROZEN"
        if failure is None
        else "V8_INTERRUPTED_RETAINED_BOUNDARY",
        route=route,
        phase=phase,
        supervised=supervised,
        stop_reason=stop_reason,
        failure=failure,
        counts=counts,
        final_audit=final_audit,
        audits=audit_rows,
        initial_parameters_sha256=array_hash(initial),
        final_c_sha256=array_hash(final_c),
        final_parameters_sha256=array_hash(parameters(model)),
        buffers_sha256={n: array_hash(v) for n, v in buffers.items()},
        final_checkpoint=record,
        consistent_optimizer_state_saved=True,
        training_data_read_whitelist=[str(Path(p).resolve()) for p in allowed],
        actual_artifact_reads=sorted(set(reads)),
        label_identity=label_identity,
        fit_interface=fit_interface,
        Gram_factor=gram.record if gram is not None else None,
        Gsolve_count=gram.solves if gram is not None else 0,
        G_matvec_count=metric.matvec_count if supervised else None,
        Maxwell_factor_created=False,
        global_Maxwell_matrix_created=False,
        native_action_counts=packet.counts,
        native_action_costs=packet.costs,
        moment_counts=mapping.counts,
        moment_costs=mapping.costs,
        timers=costs,
        timer_scope="closure/optimizer overlap nested; not additive with checkpoint",
        wall_seconds=perf_counter() - started,
        launcher_charged_seconds=perf_counter()
        - manifest["supervision_budget_origin_monotonic"],
        **labels,
    )
    marker(
        "new_route_frozen",
        dict(
            route=route,
            status=result["status"],
            stop_reason=stop_reason,
            closures=counts["complete_closures"],
            native=final_audit["native_relative"],
        ),
    )
    return result, dict(
        checkpoint=frozen,
        last_trial=trial,
        history=history_path,
        checkpoint_index=checkpoint_index,
        durable_final=store.directory / record["name"],
    )
