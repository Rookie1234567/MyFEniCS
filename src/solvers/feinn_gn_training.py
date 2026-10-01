"""Review V8: full-parameter GN qualification and bounded C/D orchestration.

PDE data loading is explicit and excludes reference/D/p4/p5/Phi/Q. Labels are
read only in the separately named FIT diagnostic or frozen compare process.
"""

from copy import deepcopy
import json
from pathlib import Path
import signal
from time import perf_counter

import numpy as np
from scipy import sparse
import torch

from src.solvers.damped_gauss_newton import DampedGNState
from src.solvers.feinn_parameter_jvp import MomentJacobian
from src.solvers.feinn_phase import make_model
from src.solvers.feinn_phase_training import configure, policy, install_data_guard
from src.solvers.feinn_torch import CompleteMomentMap
from src.solvers.feinn_validation import assign, parameters, load_moments, paired
from src.solvers.feinn_native import load_native, ResidualMetric
from src.solvers.feinn_riesz import SparseRiesz
from src.solvers.feinn_reference_fit import FitMetric
from src.solvers.neural_fe_action_packet import array_hash
from src.solvers.optimization_checkpoint import (
    CheckpointStore,
    atomic_write,
    atomic_json,
    capture,
    restore,
    load_checkpoint,
    parameter_order,
)

ROOT = Path(__file__).resolve().parents[2]


class GNStop(RuntimeError):
    pass


def prefix_entry(phase, supervised):
    name = ("phase" if phase else "plain") + (
        "_reference_fit" if supervised else "_dual"
    )
    rows = json.loads(
        (
            ROOT
            / "docs/task042extra_feinn_5nm/outcomes/records/prefix_identity_v9.json"
        ).read_text()
    )["checkpoints"]
    entry = rows[name]
    from src.runners.feinn_workflow import sha

    if sha(entry["path"]) != entry["sha256"]:
        raise ValueError("V8_ADAM500_PREFIX_BYTES_MISSING_OR_CHANGED")
    return entry


def load_boundary(design, entry, *, phase, supervised):
    state = load_checkpoint(entry["path"], entry["sha256"])
    model = make_model(design, phase)
    meta = state["metadata"]
    if (
        state["parameter_order"] != parameter_order(model)
        or meta["stage"] != "Adam"
        or meta["state_kind"] != "Adam500"
    ):
        raise ValueError("PREFIX_PARAMETER_ORDER_OR_STAGE_CHANGED")
    if (
        meta["source_sha"] != "bc052a3744528277f00a7a9a5566aa4a6d7393ed"
        or meta["counts"]["Adam_updates"] != 500
        or meta["counts"]["LBFGS_outer_steps"] != 0
    ):
        raise ValueError("PREFIX_NOT_EXACT_V8_ADAM500_BOUNDARY")
    for name, value in policy(supervised).items():
        if meta[name] is not value:
            raise ValueError("C_D_PREFIX_LABEL_IDENTITY_CHANGED")
    for name, buffer in model.named_buffers():
        if not torch.equal(buffer, state["model"][name]):
            raise ValueError("PREFIX_FIXED_BUFFER_CHANGED")
    model.load_state_dict(state["model"], strict=True)
    if array_hash(state["complete_c"]) != meta["complete_c_sha256"]:
        raise ValueError("PREFIX_COMPLETE_C_HASH_CHANGED")
    return model, state


class GNProblem:
    def __init__(
        self, model, mapping, packet, metric, *, supervised, guard=lambda *_: None
    ):
        self.model, self.mapping, self.packet, self.metric = (
            model,
            mapping,
            packet,
            metric,
        )
        self.jac = MomentJacobian(mapping)
        self.supervised = supervised
        self.guard = guard
        self.counts = dict(K=0, full_loss_gradient=0, trial_loss=0, G_matvec=0)
        self.costs = dict(K=0.0, gradient=0.0, trial_loss=0.0)

    def value_gradient(self):
        self.guard("gradient")
        start = perf_counter()
        c = self.mapping.forward(self.model)
        if self.supervised:
            loss, dual = self.metric.value(c, True)
        else:
            loss, _, dual = self.metric.value(c, gradient=True)
        g = self.jac.vjp(self.model, dual)
        self.counts["full_loss_gradient"] += 1
        self.costs["gradient"] += perf_counter() - start
        return loss, g, c

    def value(self, theta, restore_only=False):
        assign(self.model, theta)
        if restore_only:
            return None
        self.guard("trial")
        start = perf_counter()
        c = self.mapping.forward(self.model)
        loss = self.metric.value(c)[0]
        self.counts["trial_loss"] += 1
        self.costs["trial_loss"] += perf_counter() - start
        self.last_trial = (parameters(self.model), c.copy(), loss)
        return loss

    def K(self, v):
        self.guard("K")
        start = perf_counter()
        j = self.jac.jvp(self.model, v)
        if self.supervised:
            dual = self.metric.G @ j / self.metric.denominator
            self.counts["G_matvec"] += 1
        else:
            Aj = self.packet.apply(j)
            dual = (
                self.packet.apply(self.metric.gram.solve(Aj), adjoint=True)
                / self.metric.denominator
            )
        out = self.jac.vjp(self.model, dual)
        self.counts["K"] += 1
        self.costs["K"] += perf_counter() - start
        return out


def qualify(design, native, qualification, artifact, marker, manifest):
    configure()
    if qualification["result"]["status"] != "PHASE_INTERFACE_PASS_ONLY":
        raise ValueError("V8_COMPLETE_INTERFACE_NOT_QUALIFIED")
    packet = load_native(native["files"]["native"]["path"])
    mapping = CompleteMomentMap(load_moments(qualification["files"]["moments"]["path"]))
    G = sparse.load_npz(native["files"]["gram"]["path"])
    factor = SparseRiesz(G, design, marker)
    metric = ResidualMetric(packet, factor)
    rows = {}
    try:
        for phase in (False, True):
            entry = prefix_entry(phase, False)
            model, saved = load_boundary(design, entry, phase=phase, supervised=False)
            p0 = parameters(model)
            buffers = {n: b.detach().clone() for n, b in model.named_buffers()}
            jac = MomentJacobian(mapping)
            c = mapping.forward(model)
            loss = metric.value(c)[0]
            audit = packet.audit(c)
            label = "phase" if phase else "plain"
            expected_loss = 0.365338941649 if phase else 0.448518766103
            expected_native = 1.11442009288 if phase else 1.50462435428
            identity = paired(c, saved["complete_c"])
            if (
                identity["relative"] > 1e-10
                or abs(loss - expected_loss) > 1e-10
                or abs(audit["native_relative"] - expected_native) > 1e-9
            ):
                raise ValueError("REAL_C_ADAM500_BOUNDARY_NOT_QUALIFIED")
            rng = np.random.default_rng(421903)
            directions = []
            for kind in ("hidden", "last", "random"):
                v = rng.normal(size=len(p0))
                if kind == "hidden":
                    v[-390:] = 0
                if kind == "last":
                    v[:-390] = 0
                v /= np.linalg.norm(v)
                j = jac.jvp(model, v)
                analytic = paired(j, jac.jvp(model, v, analytic=True))
                fd = []
                for h in (1e-4, 1e-5, 1e-6):
                    assign(model, p0 + h * v)
                    plus = mapping.forward(model)
                    assign(model, p0 - h * v)
                    minus = mapping.forward(model)
                    fd.append(dict(h=h, **paired((plus - minus) / (2 * h), j)))
                assign(model, p0)
                good = [x["relative"] <= 1e-5 for x in fd]
                if (
                    not any(a and b for a, b in zip(good[:-1], good[1:]))
                    or analytic["relative"] > 1e-10
                ):
                    raise ValueError("REAL_COMPLETE_JVP_NOT_QUALIFIED")
                w = rng.normal(size=packet.size) + 1j * rng.normal(size=packet.size)
                g = jac.vjp(model, w)
                left = float(np.vdot(w, j).real)
                right = float(v @ g)
                scale = np.linalg.norm(w) * np.linalg.norm(j) + np.linalg.norm(
                    v
                ) * np.linalg.norm(g)
                adjoint = float(abs(left - right) / max(scale, 1e-30))
                if adjoint > 1e-10:
                    raise ValueError("REAL_JVP_VJP_ADJOINT_FAILED")
                directions.append(
                    dict(
                        kind=kind,
                        difference=fd,
                        analytic_tangent=analytic,
                        real_adjoint=adjoint,
                        direction=v,
                    )
                )
            batch_c = paired(mapping.forward(model, 1), c)
            v = directions[-1]["direction"]
            w = rng.normal(size=packet.size) + 1j * rng.normal(size=packet.size)
            batch_j = paired(jac.jvp(model, v, 1), jac.jvp(model, v, 8))
            batch_v = paired(jac.vjp(model, w, 1), jac.vjp(model, w, 8))
            batch_loss = abs(metric.value(mapping.forward(model, 1))[0] - loss) / max(
                loss, 1e-30
            )
            if (
                max(
                    batch_c["relative"],
                    batch_j["relative"],
                    batch_v["relative"],
                    batch_loss,
                )
                > 1e-10
            ):
                raise ValueError("REAL_GN_BATCH_NOT_QUALIFIED")
            problem = GNProblem(model, mapping, packet, metric, supervised=False)
            kvpairs = []
            for _ in range(3):
                v = rng.normal(size=len(p0))
                v /= np.linalg.norm(v)
                w = rng.normal(size=len(p0))
                w /= np.linalg.norm(w)
                Kv, Kw = problem.K(v), problem.K(w)
                symmetry = float(
                    abs(v @ Kw - w @ Kv)
                    / max(
                        np.linalg.norm(v) * np.linalg.norm(Kw)
                        + np.linalg.norm(w) * np.linalg.norm(Kv),
                        1e-30,
                    )
                )
                jv = jac.jvp(model, v)
                Av = packet.apply(jv)
                energy = float(np.vdot(Av, factor.solve(Av)).real / metric.denominator)
                quadratic = float(v @ Kv)
                positive_pair = abs(quadratic - energy) / max(
                    abs(quadratic), abs(energy), 1e-30
                )
                if symmetry > 1e-8 or positive_pair > 1e-8 or quadratic < 0:
                    raise ValueError("REAL_GN_CURVATURE_NOT_QUALIFIED")
                kvpairs.append(
                    dict(
                        symmetry=symmetry,
                        quadratic=quadratic,
                        independent_quadratic=energy,
                        positive_energy_pair=positive_pair,
                    )
                )
            if not np.array_equal(parameters(model), p0) or any(
                not torch.equal(b, buffers[n]) for n, b in model.named_buffers()
            ):
                raise ValueError("QUALIFICATION_CHANGED_REAL_BOUNDARY")
            for row in directions:
                row.pop("direction")
            rows[label] = dict(
                prefix=entry,
                coefficient_identity=identity,
                loss=loss,
                native=audit["native_relative"],
                direction_checks=directions,
                K_checks=kvpairs,
                batch_c=batch_c,
                batch_JVP=batch_j,
                batch_VJP=batch_v,
                batch_loss_relative=batch_loss,
                input_frozen=True,
                JVP_implementation=jac.implementation,
                JVP_VJP_counts=jac.counts,
                K_counts=problem.counts,
            )
            marker(
                "GN_real_boundary_qualified",
                dict(
                    route=label,
                    loss=loss,
                    native=audit["native_relative"],
                    d_G=metric.denominator,
                ),
            )
    finally:
        factor.close()
    return dict(
        status="GN_INTERFACE_PASS",
        routes=rows,
        d_G=metric.denominator,
        Gram_factor=factor.record,
        original_A_f_G_unchanged=True,
        max_graph_cells=8,
        parameter_JVP_not_spatial_derivative=True,
        K_is_Gauss_Newton_not_full_Hessian=True,
        Maxwell_factor_count=0,
        reference_loaded=False,
        supervised_training_state_loaded=False,
    ), {}


def run(
    design,
    native,
    qualification,
    checks,
    artifact,
    marker,
    manifest,
    *,
    phase,
    supervised,
    reference=None,
):
    configure()
    if checks["result"]["status"] != "GN_INTERFACE_PASS":
        raise ValueError("COMMON_GN_INTERFACE_NOT_QUALIFIED")
    entry = prefix_entry(phase, supervised)
    allowed = [native["files"][k]["path"] for k in ("native", "gram")] + [
        qualification["files"]["moments"]["path"],
        entry["path"],
    ]
    if supervised:
        allowed.append(reference["files"]["reference"]["path"])
    reads = install_data_guard(allowed, artifact, supervised=supervised)
    model, old = load_boundary(design, entry, phase=phase, supervised=supervised)
    initial = parameters(model)
    packet = load_native(native["files"]["native"]["path"])
    mapping = CompleteMomentMap(load_moments(qualification["files"]["moments"]["path"]))
    G = sparse.load_npz(native["files"]["gram"]["path"])
    factor = None
    label = None
    if supervised:
        from src.solvers.feinn_error_geometry import reference_label

        ref, label = reference_label(native, reference, packet, used_for_training=True)
        metric = FitMetric(G, ref)
    else:
        factor = SparseRiesz(G, design, marker)
        metric = ResidualMetric(packet, factor)
    cutoff = (
        float(manifest["supervision_budget_origin_monotonic"])
        + float(manifest["supervised_limit_seconds"])
        - 180
    )
    caps = dict(
        accepted=60 if supervised else 120,
        K=1000 if supervised else 4000,
        JVP_VJP=2500 if supervised else 8000,
        trial=256 if supervised else 512,
    )
    requested = False

    def stop_signal(*_):
        nonlocal requested
        requested = True

    old_signal = signal.signal(signal.SIGTERM, stop_signal)
    problem = None

    def guard(kind):
        if requested or perf_counter() >= cutoff:
            raise GNStop("WALL_BUDGET_SAVE_RESERVE")
        if problem is not None:
            j = sum(problem.jac.counts.values())
            if kind == "K" and (
                problem.counts["K"] >= caps["K"] or j + 2 > caps["JVP_VJP"]
            ):
                raise GNStop("K_OR_JVP_VJP_BUDGET")
            if kind == "gradient" and j + 1 > caps["JVP_VJP"]:
                raise GNStop("JVP_VJP_BUDGET")
            if kind == "trial" and problem.counts["trial_loss"] >= caps["trial"]:
                raise GNStop("TRIAL_LOSS_BUDGET")

    problem = GNProblem(
        model, mapping, packet, metric, supervised=supervised, guard=guard
    )
    anchor_c = mapping.forward(model)
    if paired(anchor_c, old["complete_c"])["relative"] > 1e-10:
        raise ValueError("OWN_ADAM500_BOUNDARY_RECONSTRUCTION_FAILED")
    initial_loss = metric.value(anchor_c)[0]
    route = ("V9-PHASE" if phase else "V9-PLAIN") + (
        "-FIT-GN-DIAGNOSTIC" if supervised else "-DAMPED-GN"
    )
    history_path = artifact / "history.jsonl"
    history = history_path.open("w", buffering=1)
    audits = []
    accepted_rows = []
    pc_rows = []

    def emit(row):
        value = dict(
            row,
            elapsed_charged_seconds=perf_counter()
            - manifest["supervision_budget_origin_monotonic"],
            logical_path_seconds=entry["metadata"]["elapsed_charged_seconds"]
            + perf_counter()
            - manifest["supervision_budget_origin_monotonic"],
            counts=deepcopy(problem.counts),
            JVP_VJP_counts=deepcopy(problem.jac.counts),
        )
        history.write(json.dumps(value, allow_nan=False) + "\n")
        if row["kind"] == "PC_BUILD":
            pc_rows.append(value)

    # Scale belongs to this new optimizer and is not recovered from old history.
    rng = np.random.default_rng(421901)
    v = rng.normal(size=len(initial))
    v /= np.linalg.norm(v)
    scale_trace = []
    for _ in range(6):
        Kv = problem.K(v)
        h0 = float(np.linalg.norm(Kv))
        if not np.isfinite(h0) or h0 <= 0:
            raise ValueError("INITIAL_GN_SCALE_UNRESOLVED")
        scale_trace.append(dict(norm=h0, quadratic=float(v @ Kv)))
        v = Kv / h0
    optimizer = DampedGNState(h0, pc_max_builds=1 if supervised else 2)
    store = CheckpointStore(artifact / "durable_checkpoints")
    flags = policy(supervised)
    frozen_buffers = {
        n: array_hash(b.detach().numpy()) for n, b in model.named_buffers()
    }
    prefix_seconds = entry["metadata"]["elapsed_charged_seconds"]

    def save(tag, c, pin, update=None):
        meta = dict(
            state_kind=tag,
            route=route,
            stage="DAMPED_GN",
            source_sha=manifest["source_sha"],
            input_sha256=manifest["input_sha256"],
            run_id=manifest["run_id"],
            counts=deepcopy(problem.counts),
            JVP_VJP_counts=deepcopy(problem.jac.counts),
            accepted_outer=optimizer.accepted,
            inherited_Adam_updates=500,
            new_Adam_updates=0,
            initialization_kind="REFERENCE_FIT_ADAM500_PREFIX_REUSE"
            if supervised
            else "PDE_ONLY_ADAM500_PREFIX_REUSE",
            prefix_sha256=entry["sha256"],
            inherited_prefix_seconds=prefix_seconds,
            elapsed_charged_seconds=perf_counter()
            - manifest["supervision_budget_origin_monotonic"],
            logical_path_seconds=prefix_seconds
            + perf_counter()
            - manifest["supervision_budget_origin_monotonic"],
            native_sha256=native["files"]["native"]["sha256"],
            Gram_sha256=native["files"]["gram"]["sha256"],
            moments_sha256=qualification["files"]["moments"]["sha256"],
            complete_c_sha256=array_hash(c),
            parameter_sha256=array_hash(parameters(model)),
            label_identity=label,
            mu=optimizer.mu,
            h0=h0,
            d_ref=metric.denominator if supervised else None,
            d_G=None if supervised else metric.denominator,
            buffers_sha256=frozen_buffers,
            limits=caps,
            PC_provenance=optimizer.pc_builds,
            **flags,
            **(update or {}),
        )
        state = capture(model, optimizer, meta)
        state["complete_c"] = c.copy()
        return store.save(state, pin=pin)

    def audit(c, tag, record):
        value = packet.audit(c)
        value.update(
            tag=tag,
            accepted_outer=optimizer.accepted,
            checkpoint=record,
            elapsed_charged_seconds=perf_counter()
            - manifest["supervision_budget_origin_monotonic"],
            loss=metric.value(c)[0],
            complete_closures=problem.counts["full_loss_gradient"],
        )
        if supervised:
            value["E_G"] = float(np.sqrt(2 * value["loss"]))
        audits.append(value)
        marker(
            "GN_committed_original_audit",
            dict(
                route=route,
                outer=optimizer.accepted,
                native=value["native_relative"],
                mu=optimizer.mu,
            ),
        )
        return value

    record = save("GN_initial_Adam500_boundary", anchor_c, True)
    initial_audit = audit(anchor_c, "GN_initial_Adam500_boundary", record)
    problem.last_trial = (initial.copy(), anchor_c.copy(), initial_loss)
    failure = None
    stop_reason = "ACCEPTED_OUTER_BUDGET"
    try:
        while optimizer.accepted < caps["accepted"]:
            guard("gradient")
            committed = capture(model, optimizer, {})
            theta = parameters(model)
            published = False
            try:
                loss, g, c = problem.value_gradient()
                proposed, row = optimizer.propose(
                    theta, loss, g, problem.K, problem.value, emit
                )
                if proposed is None:
                    stop_reason = "GN_MODEL_STAGNATION"
                    emit(dict(kind="STAGNATION", **row))
                    break
                assign(model, proposed)
                after = parameters(model)
                delta = after - theta
                update = dict(
                    accepted_update_norm=float(np.linalg.norm(delta)),
                    accepted_relative_update=float(
                        np.linalg.norm(delta) / max(np.linalg.norm(theta), 1e-30)
                    ),
                )
                c = mapping.forward(model)
                record = save("accepted_outer", c, optimizer.accepted % 5 == 0, update)
                published = True
                accepted_rows.append(
                    dict(
                        row,
                        accepted_outer=optimizer.accepted,
                        checkpoint=record,
                        **update,
                    )
                )
                emit(
                    dict(
                        kind="DURABLE_ACCEPTED",
                        accepted_outer=optimizer.accepted,
                        checkpoint_sha256=record["sha256"],
                        **update,
                    )
                )
            except BaseException:
                # Restore matching theta/optimizer/RNG; spent action counters are
                # external and remain charged, including interrupted proposals.
                if not published:
                    restore(model, optimizer, committed)
                raise
            if optimizer.accepted % 5 == 0:
                actual = audit(c, "accepted_outer", record)
                if (supervised and actual["E_G"] <= 1e-3) or (
                    not supervised and actual["strict_pass"]
                ):
                    stop_reason = (
                        "FIT_THRESHOLD_REACHED"
                        if supervised
                        else "ORIGINAL_EQUATION_THRESHOLD_REACHED"
                    )
                    break
    except GNStop as error:
        stop_reason = str(error)
    except BaseException as error:
        failure = dict(kind=type(error).__name__, reason=str(error))
        stop_reason = "ENGINEERING_FAILURE_RETAINED_BOUNDARY"
    finally:
        signal.signal(signal.SIGTERM, old_signal)
    final_c = mapping.forward(model)
    if any(
        array_hash(b.detach().numpy()) != frozen_buffers[n]
        for n, b in model.named_buffers()
    ):
        raise ValueError("FIXED_BUFFER_CHANGED_DURING_GN")
    record = save(
        "final_committed" if failure is None else "retained_failure_boundary",
        final_c,
        True,
    )
    final_audit = audit(final_c, "final_committed", record)
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
            durable_checkpoint_sha256=record["sha256"],
            **buffers,
            **flags,
        ),
    )
    trial = artifact / "last_trial.npz"
    tp, tc, tl = problem.last_trial
    atomic_write(
        trial,
        lambda stream: np.savez(
            stream,
            parameters=tp,
            c=tc,
            loss=tl,
            state_kind="not_committed_last_trial",
            route=route,
            phase=phase,
            **flags,
        ),
    )
    idx = artifact / "checkpoint_index.json"
    atomic_json(
        idx,
        dict(
            current=record,
            checkpoints=store.index(),
            optimizer_state_saved=True,
            fault_resume_limit=2,
            guarantee="last successfully fsynced complete boundary; no SIGKILL finally promise",
        ),
    )
    history.close()
    if factor is not None:
        factor.close()
    result = dict(
        status="V9_GN_CANDIDATE_FROZEN"
        if failure is None
        else "V9_GN_RETAINED_FAILURE",
        route=route,
        phase=phase,
        supervised=supervised,
        stop_reason=stop_reason,
        failure=failure,
        counts=problem.counts,
        JVP_VJP_counts=problem.jac.counts,
        inner_solver_history=str(history_path),
        accepted_history=accepted_rows,
        PC_builds=pc_rows,
        h0=h0,
        mu_final=optimizer.mu,
        scale_probe=scale_trace,
        d_G=None if supervised else metric.denominator,
        d_ref=metric.denominator if supervised else None,
        initial_audit=initial_audit,
        final_audit=final_audit,
        audits=audits,
        final_checkpoint=record,
        inherited_committed_Adam_updates=500,
        new_Adam_updates=0,
        inherited_prefix_seconds=prefix_seconds,
        initialization_kind="REFERENCE_FIT_ADAM500_PREFIX_REUSE"
        if supervised
        else "PDE_ONLY_ADAM500_PREFIX_REUSE",
        prefix_identity=entry,
        old_optimizer_history_loaded=False,
        consistent_optimizer_state_saved=True,
        final_c_sha256=array_hash(final_c),
        final_parameters_sha256=array_hash(parameters(model)),
        buffers_sha256=frozen_buffers,
        native_action_counts=packet.counts,
        native_action_costs=packet.costs,
        moment_counts=mapping.counts,
        moment_costs=mapping.costs,
        JVP_VJP_costs=problem.jac.costs,
        nested_timers=problem.costs,
        Gram_factor=factor.record if factor is not None else None,
        Gsolve_count=factor.solves if factor is not None else 0,
        G_matvec_count=problem.counts["G_matvec"]
        + (metric.matvec_count if supervised else 0),
        Maxwell_factor_created=False,
        global_Maxwell_matrix_created=False,
        label_identity=label,
        training_data_read_whitelist=allowed,
        actual_artifact_reads=sorted(set(reads)),
        launcher_charged_seconds=perf_counter()
        - manifest["supervision_budget_origin_monotonic"],
        logical_path_seconds=prefix_seconds
        + perf_counter()
        - manifest["supervision_budget_origin_monotonic"],
        **flags,
    )
    marker(
        "GN_route_frozen",
        dict(
            route=route,
            stop_reason=stop_reason,
            accepted=optimizer.accepted,
            native=final_audit["native_relative"],
        ),
    )
    return result, dict(
        checkpoint=frozen,
        last_trial=trial,
        history=history_path,
        checkpoint_index=idx,
        durable_final=store.directory / record["name"],
    )


def dispatch(stage, design, artifact, marker, manifest, load_index):
    qualification = load_index("v8_phase_checks")
    if stage == "v9_gn_checks":
        return qualify(
            design, load_index("e1_fe"), qualification, artifact, marker, manifest
        )
    if stage in ("v9_plain_gn", "v9_phase_gn", "v9_plain_fit_gn", "v9_phase_fit_gn"):
        supervised = "fit_gn" in stage
        if (
            supervised
            and load_index("v9_gn_compare")["result"]["phase_strict_qualified"]
        ):
            raise ValueError("CONDITIONAL_D_NOT_AUTHORIZED_AFTER_PHASE_PASS")
        return run(
            design,
            load_index("e1_fe"),
            qualification,
            load_index("v9_gn_checks"),
            artifact,
            marker,
            manifest,
            phase=stage.startswith("v9_phase"),
            supervised=supervised,
            reference=load_index("e3_reference") if supervised else None,
        )
    supervised = "fit_gn" in stage
    route_names = (
        ("v9_plain_fit_gn", "v9_phase_fit_gn")
        if supervised
        else ("v9_plain_gn", "v9_phase_gn")
    )
    routes = {name: load_index(name) for name in route_names}
    if stage.endswith("reconstruct"):
        from src.solvers.feinn_phase_verification import reconstruct

        return reconstruct(design, qualification, routes, artifact, marker, manifest)
    from src.solvers.feinn_phase_compare import compare

    return compare(
        design,
        load_index("e1_fe"),
        load_index("e3_reference"),
        routes,
        load_index("v9_fit_gn_reconstruct" if supervised else "v9_gn_reconstruct"),
        artifact,
        marker,
        manifest,
        supervised=supervised,
    )
