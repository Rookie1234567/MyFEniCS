"""Frozen three-route optimizer with transactional strong-Wolfe boundaries."""

import json
from pathlib import Path
import signal
from time import perf_counter

import numpy as np
from scipy import sparse
import torch

from src.solvers.feinn_native import load_native, ResidualMetric
from src.solvers.feinn_riesz import SparseRiesz
from src.solvers.feinn_scaling import read_frozen_scale
from src.solvers.feinn_torch import CoordinateField, CompleteMomentMap
from src.solvers.feinn_validation import assign, parameters, load_moments
from src.solvers.neural_fe_action_packet import array_hash


class RouteStop(Exception):
    pass


def transactional_step(step, closure, read, restore):
    """A completed outer step is the only commit boundary, including exceptions."""
    before = read()
    try:
        result = step(closure)
    except BaseException:
        restore(before)
        raise
    return result


def run_route(route, design, operator_index, qualification, artifact, marker,
              *, scale_index=None, route_wall_seconds=None):
    began = perf_counter()
    if qualification["result"]["status"] != "INTERFACE_PASS_ONLY":
        raise RuntimeError("full actual interface prerequisite failed")
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    if (
        torch.version.cuda is not None
        or len(__import__("os").sched_getaffinity(0)) != 1
    ):
        raise RuntimeError("CPU-only one physical-core gate failed")
    artifact = Path(artifact)
    gram = None
    mapping = None
    model = None
    free = None
    scaling = None
    scaled = route == "FREE-FE-DUAL-GRAM-DIAG"
    if scaled and scale_index is None:
        raise ValueError("frozen Gram-diagonal scale index required")
    if scale_index is not None and not scaled:
        raise ValueError("scale is opt-in only for the single V2 FREE route")
    costs = dict(
        packet_and_model_setup=0.0,
        metric_setup_excluding_Gsolve=0.0,
        parameter_gradient_assignment=0.0,
        optimizer_excluding_closures=0.0,
        io=0.0,
    )
    counts = dict(
        closures=0,
        outer_attempts=0,
        committed_outer_steps=0,
        adam_updates=0,
        lbfgs_outer_steps=0,
        lbfgs_inner_iterations=0,
    )
    audits = []
    trial = None
    trial_c = None
    trial_loss = None
    stop_reason = "CLOSURE_BUDGET"
    closure_seconds = 0.0
    vjp_wall_total = 0.0
    deadline = (
        began
        + (route_wall_seconds or design["optimizer"]["route_wall_seconds"])
        - design["optimizer"]["final_reserve_seconds"]
    )
    t = perf_counter()
    packet = load_native(operator_index["files"]["native"]["path"])
    if scaled:
        G = sparse.load_npz(operator_index["files"]["gram"]["path"])
        scaling = read_frozen_scale(scale_index["files"]["scale"]["path"], G)
        if scaling.D.shape != (packet.size,):
            raise ValueError("scaling and native full-FE dimensions differ")
        del G
    if route in ("FREE-FE-DUAL", "FREE-FE-DUAL-GRAM-DIAG"):
        free = torch.nn.Parameter(torch.zeros((2, packet.size), dtype=torch.float64))
        optimizer_parameters = [free]

        def read():
            return free.detach().numpy().copy().ravel()

        def restore(values):
            with torch.no_grad():
                free.copy_(torch.as_tensor(values.reshape(2, packet.size)))

        def coefficients():
            v = free.detach().numpy()
            y = v[0] + 1j * v[1]
            return scaling.to_c(y) if scaled else y
    else:
        model = CoordinateField(
            design["geometry"]["bounds_nm"], design["network"]["seed"]
        )
        mapping = CompleteMomentMap(
            load_moments(qualification["files"]["moments"]["path"])
        )
        optimizer_parameters = list(model.parameters())

        def read():
            return parameters(model)

        def restore(values):
            assign(model, values)

        def coefficients():
            return mapping.forward(model)

    costs["packet_and_model_setup"] = perf_counter() - t
    initial_parameters = read()
    committed = initial_parameters.copy()
    initial = coefficients()
    if np.any(initial):
        raise ValueError("every route must start at exact zero full scattered FE state")
    history_path = artifact / "history.jsonl"
    history = history_path.open("w", buffering=1)

    def emit(value):
        t = perf_counter()
        history.write(json.dumps(value, allow_nan=False) + "\n")
        costs["io"] += perf_counter() - t

    def checkpoint(path, p, c, state_kind):
        t = perf_counter()
        np.savez(
            path,
            parameters=p,
            c=c,
            closures=np.asarray(counts["closures"]),
            committed_steps=np.asarray(counts["committed_outer_steps"]),
            state_kind=np.asarray(state_kind),
            parameter_only=np.asarray(True),
        )
        costs["io"] += perf_counter() - t

    def audit(c, tag):
        row = dict(
            tag=tag,
            closures=counts["closures"],
            committed_steps=counts["committed_outer_steps"],
            elapsed_seconds=perf_counter() - began,
            **packet.audit(c),
        )
        audits.append(row)
        emit(dict(kind="audit", **row))
        print(
            json.dumps(
                dict(
                    route=route,
                    tag=tag,
                    closures=counts["closures"],
                    native=row["native_relative"],
                    augmented=row["augmented_relative"],
                    strict_pass=row["strict_pass"],
                )
            ),
            flush=True,
        )
        return row["strict_pass"]

    def terminate(_signum, _frame):
        nonlocal stop_reason
        stop_reason = "OWN_WATCHDOG_STOP"
        raise RouteStop

    previous_signal = signal.signal(signal.SIGTERM, terminate)
    try:
        if route != "FEINN-EUC":
            gram = SparseRiesz(
                sparse.load_npz(operator_index["files"]["gram"]["path"]), design, marker
            )
        t = perf_counter()
        oldG = gram.solve_seconds if gram else 0.0
        metric = ResidualMetric(packet, gram)
        costs["metric_setup_excluding_Gsolve"] = (
            perf_counter() - t - ((gram.solve_seconds - oldG) if gram else 0)
        )
        initial_loss = metric.value(initial)[0]
        audit(initial, "initial_committed")

        def closure():
            nonlocal \
                trial, \
                trial_c, \
                trial_loss, \
                closure_seconds, \
                stop_reason, \
                vjp_wall_total
            if (
                counts["closures"] >= design["optimizer"]["total_closures_limit"]
                or perf_counter() >= deadline
            ):
                stop_reason = (
                    "WALL_BUDGET" if perf_counter() >= deadline else "CLOSURE_BUDGET"
                )
                raise RouteStop
            t = perf_counter()
            counts["closures"] += 1
            try:
                trial = read()
                trial_c = coefficients()
                trial_loss, _, gradient = metric.value(trial_c, gradient=True)
                if not np.isfinite(trial_loss) or not np.isfinite(gradient).all():
                    stop_reason = "NONFINITE"
                    raise RouteStop
                tgrad = perf_counter()
                if mapping is None:
                    actual_gradient = scaling.gradient(gradient) if scaled else gradient
                    free.grad = torch.as_tensor(
                        np.stack((actual_gradient.real, actual_gradient.imag))
                    ).clone()
                    parameter_gradient = free.grad.numpy().ravel()
                else:
                    tvjp = perf_counter()
                    parameter_gradient = mapping.vjp(model, gradient)
                    vjp_wall_total += perf_counter() - tvjp
                costs["parameter_gradient_assignment"] += perf_counter() - tgrad
                emit(
                    dict(
                        kind="closure",
                        closure=counts["closures"],
                        outer_attempt=counts["outer_attempts"],
                        committed_steps=counts["committed_outer_steps"],
                        loss=trial_loss,
                        parameter_gradient_norm=float(
                            np.linalg.norm(parameter_gradient)
                        ),
                        coefficient_gradient_norm=float(np.linalg.norm(gradient))
                        if scaled else None,
                        scaled_gradient_norm=float(np.linalg.norm(actual_gradient))
                        if scaled else None,
                        parameters_sha256=array_hash(trial),
                        A=packet.counts["A"],
                        AH=packet.counts["AH"],
                        Gsolve=gram.solves if gram else 0,
                        elapsed_seconds=perf_counter() - began,
                    )
                )
                if counts["closures"] % 25 == 0:
                    audit(
                        trial_c,
                        "line_search_trial"
                        if counts["adam_updates"] >= 500
                        else "adam_pre_update",
                    )
                    checkpoint(
                        artifact / "last_trial_checkpoint.npz",
                        trial,
                        trial_c,
                        "last_completed_closure_trial",
                    )
                return torch.tensor(trial_loss, dtype=torch.float64)
            finally:
                closure_seconds += perf_counter() - t

        adam = torch.optim.Adam(optimizer_parameters, lr=1e-3, weight_decay=0)
        for _ in range(500):
            counts["outer_attempts"] += 1
            closure()
            t = perf_counter()
            before = read()
            try:
                adam.step()
            except BaseException:
                restore(before)
                raise
            costs["optimizer_excluding_closures"] += perf_counter() - t
            counts["committed_outer_steps"] += 1
            counts["adam_updates"] += 1
            committed = read()
            if scaled:
                emit(dict(kind="committed_update", phase="Adam", closure=counts["closures"],
                          y_delta_norm=float(np.linalg.norm(committed-before)),
                          y_relative_delta=float(np.linalg.norm(committed-before)/max(np.linalg.norm(before), 1e-12)),
                          c_delta_norm=float(np.linalg.norm(coefficients()-scaling.to_c(before[:packet.size]+1j*before[packet.size:])))))
            if counts["adam_updates"] % 25 == 0:
                c = coefficients()
                checkpoint(
                    artifact / "last_committed_checkpoint.npz",
                    committed,
                    c,
                    "completed_outer_step",
                )
                if audit(c, "adam_committed"):
                    stop_reason = "STRICT_EQUATION_PASS"
                    raise RouteStop
        lbfgs = torch.optim.LBFGS(
            optimizer_parameters,
            lr=1,
            history_size=20,
            line_search_fn="strong_wolfe",
            max_iter=20,
            max_eval=25,
        )
        while counts["closures"] < 4000:
            counts["outer_attempts"] += 1
            t = perf_counter()
            closure_before = closure_seconds
            before = read()
            try:
                transactional_step(lbfgs.step, closure, read, restore)
            finally:
                costs["optimizer_excluding_closures"] += max(
                    0, perf_counter() - t - (closure_seconds - closure_before)
                )
            counts["committed_outer_steps"] += 1
            counts["lbfgs_outer_steps"] += 1
            counts["lbfgs_inner_iterations"] = int(
                lbfgs.state[optimizer_parameters[0]].get("n_iter", 0)
            )
            committed = read()
            if scaled:
                state = lbfgs.state[optimizer_parameters[0]]
                emit(dict(kind="committed_update", phase="LBFGS", closure=counts["closures"],
                          y_delta_norm=float(np.linalg.norm(committed-before)),
                          y_relative_delta=float(np.linalg.norm(committed-before)/max(np.linalg.norm(before), 1e-12)),
                          c_delta_norm=float(np.linalg.norm(coefficients()-scaling.to_c(before[:packet.size]+1j*before[packet.size:]))),
                          torch_last_inner_step_length=float(state["t"]) if "t" in state else None,
                          torch_last_inner_step_scope="last inner state only; not all accepted line-search steps"))
            c = coefficients()
            checkpoint(
                artifact / "last_committed_checkpoint.npz",
                committed,
                c,
                "completed_outer_step",
            )
            if audit(c, "lbfgs_committed"):
                stop_reason = "STRICT_EQUATION_PASS"
                break
            if np.array_equal(before, committed):
                stop_reason = "OPTIMIZER_STAGNATION"
                break
    except RouteStop:
        restore(committed)
    except (ValueError, RuntimeError) as error:
        restore(committed)
        stop_reason = (
            "RIESZ_RESOURCE_BLOCKED"
            if "RIESZ_RESOURCE_BLOCKED" in str(error)
            else "NUMERICAL_OR_BACKEND_FAILED: " + str(error)
        )
        emit(dict(kind="route_exception", reason=stop_reason))
    finally:
        restore(committed)
        final_c = coefficients()
        final_pass = audit(final_c, "final_committed")
        final_loss = metric.value(final_c)[0] if "metric" in locals() else None
        final_path = artifact / "frozen_checkpoint.npz"
        checkpoint(
            final_path, committed, final_c, "final_completed_outer_step_parameter_only"
        )
        trial_path = artifact / "last_trial.npz"
        checkpoint(
            trial_path,
            trial if trial is not None else committed,
            trial_c if trial_c is not None else final_c,
            "last_trial_never_used_as_final",
        )
        if gram:
            gram.close()
        signal.signal(signal.SIGTERM, previous_signal)
        history.close()
    costs.update(
        A=packet.costs["A"],
        AH=packet.costs["AH"],
        original_equation_audit=packet.costs["audit"],
        port_solve=packet.costs["port_solve"],
        Gram_setup=gram.setup_seconds if gram else 0.0,
        Gram_solve=gram.solve_seconds if gram else 0.0,
    )
    if mapping:
        # VJP recomputation/backward was timed inside parameter assignment; remove it there.
        # Forward outside VJP is not nested in assignment. Count its precise split by tracking below.
        costs["parameter_gradient_assignment"] = max(
            0, costs["parameter_gradient_assignment"] - vjp_wall_total
        )
        costs.update(mapping.costs)
    wall = perf_counter() - began
    costs["other_control"] = max(0, wall - sum(costs.values()))
    if sum(costs.values()) > wall * 1.01:
        raise RuntimeError("EXCLUSIVE_TIMER_ACCOUNTING_FAILED")
    result = dict(
        status="STRICT_EQUATION_PASS_PENDING_REFERENCE"
        if final_pass
        else "RIESZ_RESOURCE_BLOCKED"
        if stop_reason == "RIESZ_RESOURCE_BLOCKED"
        else "FEINN_OPTIMIZATION_NEGATIVE",
        route=route,
        stop_reason=stop_reason,
        counts=counts,
        action_counts=packet.counts,
        final_audit=audits[-1],
        audits=audits,
        initial_loss=initial_loss if "initial_loss" in locals() else None,
        final_loss=final_loss,
        last_trial_loss=trial_loss,
        initial_scattered_coefficients_zero=True,
        initialization_sha256=array_hash(initial_parameters),
        initial_c_sha256=array_hash(initial),
        final_c_sha256=array_hash(final_c),
        parameter_count=len(initial_parameters),
        full_independent_complex_FE=packet.size,
        full_internal_moments=packet.a["idofs"].size,
        full_ports=packet.np,
        parameter_only_checkpoint=True,
        consistent_optimizer_resume_supported=False,
        last_trial_is_final=False,
        coordinate_mapping=scaling.record() if scaling else None,
        frozen_scale_file_sha256=scale_index["files"]["scale"]["sha256"] if scaled else None,
        fixed_dual_denominator=metric.denominator if "metric" in locals() else None,
        saved_c_equals_Dy=bool(np.array_equal(final_c, scaling.to_c(committed[:packet.size]+1j*committed[packet.size:]))) if scaled else None,
        global_Maxwell_factor_created=False,
        global_Maxwell_CSR_created=False,
        target_reference_loaded=False,
        Gram_factor=gram.record if gram else None,
        Gram_assembly_cost_shared_preparation_seconds=operator_index["result"]["gram"][
            "assembly_seconds"
        ]
        if gram
        else 0,
        cache_payload_bytes=mapping.numeric_cache_bytes if mapping else 0,
        optimizer_history_payload_bytes=sum(
            v.nelement() * v.element_size()
            for state in lbfgs.state.values()
            for key, v in state.items()
            if isinstance(v, torch.Tensor)
        )
        + sum(
            v.nelement() * v.element_size()
            for state in lbfgs.state.values()
            for key, v in state.items()
            if isinstance(v, list)
            for v in v
            if isinstance(v, torch.Tensor)
        )
        if "lbfgs" in locals()
        else 0,
        costs_exclusive_seconds=costs,
        route_worker_wall_seconds=wall,
        closure_wall_seconds_nested_not_additive=closure_seconds,
        wall_limit_seconds=route_wall_seconds or 10800,
        closure_limit=4000,
        optimizer=dict(
            adam_updates=500,
            lr_adam=1e-3,
            lbfgs_lr=1,
            history=20,
            max_iter=20,
            max_eval=25,
            line_search="strong_wolfe",
            tolerance_grad=1e-7,
            tolerance_change=1e-9,
            stagnation_is_not_equation_pass=True,
        ),
    )
    return result, dict(
        checkpoint=final_path, last_trial=trial_path, history=history_path
    )
