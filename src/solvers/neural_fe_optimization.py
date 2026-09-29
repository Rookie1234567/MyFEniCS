"""Three frozen, independent single-solve routes; no teacher or inverse."""

import json
from pathlib import Path
from time import perf_counter

import numpy as np

from src.solvers.bounded_complex_lsqr import lsqr_steps
from src.solvers.neural_fe_action_packet import array_hash, file_hash


class RouteStop(Exception):
    pass


def optimize_route(design, action, moments, route, artifact, *, wall_seconds=7200):
    """One zero-scattered run, strict audits and exact work accounting."""
    began = perf_counter()
    artifact = Path(artifact)
    costs = dict(
        setup=0.0,
        network_forward=0.0,
        network_backward=0.0,
        parameter_gradient_assignment=0.0,
        optimizer_excluding_closures=0.0,
        io=0.0,
    )
    counts = dict(
        closures=0,
        optimizer_updates=0,
        adam_updates=0,
        lbfgs_updates=0,
        lsqr_iterations=0,
        network_forward=0,
        network_backward=0,
    )
    # Leave an explicit final-check/checkpoint reserve inside the 2h limit.
    deadline = began + wall_seconds - 60
    audits = []
    history = (artifact / "scalar_history.jsonl").open("w", buffering=1)
    current = np.zeros(action.size, dtype=np.complex128)
    stop_reason = "CLOSURE_BUDGET" if route != "FE-LSQR" else "ACTION_BUDGET"
    parameters = None
    model = None
    free = None
    port_parameters = None
    closure_seconds = 0.0

    def emit(row):
        start = perf_counter()
        history.write(json.dumps(row, allow_nan=False) + "\n")
        costs["io"] += perf_counter() - start

    def state_z():
        start = perf_counter()
        if route == "NEURAL-TRACE":
            z = np.r_[
                packet_forward(model, moments),
                port_parameters.detach().numpy()[0]
                + 1j * port_parameters.detach().numpy()[1],
            ]
            counts["network_forward"] += 1
            costs["network_forward"] += perf_counter() - start
            return z
        if route == "FREE-FE-OPT":
            values = free.detach().numpy()
            return values[0] + 1j * values[1]
        return current

    def save_checkpoint(z, *, final=False):
        start = perf_counter()
        data = dict(
            z=np.asarray(z),
            closures=np.array(counts["closures"]),
            optimizer_updates=np.array(counts["optimizer_updates"]),
        )
        if model is not None:
            from src.solvers.neural_trace_checks import parameters as model_parameters

            data["network_parameters"] = model_parameters(model)
            data["port_parameters"] = port_parameters.detach().numpy()
        elif free is not None:
            data["free_parameters"] = free.detach().numpy()
        path = artifact / ("frozen_state.npz" if final else "latest_checkpoint.npz")
        np.savez(path, **data)
        costs["io"] += perf_counter() - start
        return path

    def full_audit(z, tag):
        result = action.audit(z)
        audits.append(
            dict(
                tag=tag,
                closures=counts["closures"],
                updates=counts["optimizer_updates"],
                lsqr_iterations=counts["lsqr_iterations"],
                elapsed_seconds=perf_counter() - began,
                **result,
            )
        )
        emit(dict(kind="audit", **audits[-1]))
        save_checkpoint(z)
        print(
            json.dumps(
                dict(
                    route=route,
                    checkpoint=tag,
                    closures=counts["closures"],
                    iterations=counts["lsqr_iterations"],
                    schur=result["schur_relative"],
                    native=result["native_relative"],
                    strict_pass=result["strict_pass"],
                )
            ),
            flush=True,
        )
        return result["strict_pass"]

    try:
        setup_start = perf_counter()
        if route != "FE-LSQR":
            import torch

            if route == "NEURAL-TRACE":
                from src.solvers.neural_trace_torch import (
                    NeuralTrace,
                    packet_forward,
                    packet_vjp,
                )

                model = NeuralTrace(
                    design["geometry"]["bounds_nm"],
                    design["wavelength_nm"],
                    design["incidence"]["grazing_deg"],
                    design["network"]["seed"],
                )
                port_parameters = torch.nn.Parameter(
                    torch.zeros((2, action.np), dtype=torch.float64)
                )
                parameters = [*model.parameters(), port_parameters]
            elif route == "FREE-FE-OPT":
                free = torch.nn.Parameter(
                    torch.zeros((2, action.size), dtype=torch.float64)
                )
                parameters = [free]
            else:
                raise ValueError("unregistered frozen route")
        costs["setup"] = perf_counter() - setup_start
        current = state_z()
        if np.any(current):
            raise ValueError(
                "all routes must start at zero scattered trace and zero ports"
            )
        initial_z_sha256 = array_hash(current)
        if full_audit(current, "initial"):
            stop_reason = "STRICT_RESIDUAL_PASS"
            raise RouteStop
        if route != "FE-LSQR":
            adam = torch.optim.Adam(parameters, lr=0.001, weight_decay=0)

            def closure():
                nonlocal current, closure_seconds, stop_reason
                if counts["closures"] >= 2000 or perf_counter() >= deadline:
                    stop_reason = (
                        "WALL_BUDGET"
                        if perf_counter() >= deadline
                        else "CLOSURE_BUDGET"
                    )
                    raise RouteStop
                start = perf_counter()
                try:
                    current = state_z()
                    residual = action.a["b"] - action.apply(current)
                    loss = float(
                        np.vdot(residual, residual).real / (2 * action.bnorm**2)
                    )
                    gradient = -action.apply(residual, adjoint=True) / action.bnorm**2
                    counts["closures"] += 1
                    if not np.isfinite(loss) or not np.isfinite(gradient).all():
                        stop_reason = "NONFINITE"
                        raise RouteStop
                    grad_start = perf_counter()
                    if route == "NEURAL-TRACE":
                        network_gradient = packet_vjp(
                            model, moments, gradient[: action.nt]
                        )
                        counts["network_backward"] += 1
                        costs["network_backward"] += perf_counter() - grad_start
                        grad_start = perf_counter()
                        port_parameters.grad = torch.as_tensor(
                            np.stack(
                                (gradient[action.nt :].real, gradient[action.nt :].imag)
                            )
                        )
                        norm = float(
                            np.linalg.norm(
                                np.r_[
                                    network_gradient,
                                    port_parameters.grad.numpy().ravel(),
                                ]
                            )
                        )
                    else:
                        free.grad = torch.as_tensor(
                            np.stack((gradient.real, gradient.imag))
                        )
                        norm = float(np.linalg.norm(free.grad.numpy()))
                    costs["parameter_gradient_assignment"] += (
                        perf_counter() - grad_start
                    )
                    emit(
                        dict(
                            kind="closure",
                            closure=counts["closures"],
                            updates=counts["optimizer_updates"],
                            loss=loss,
                            gradient_norm=norm,
                            schur_relative=(2 * loss) ** 0.5,
                            S=action.counts["S"],
                            SH=action.counts["SH"],
                            elapsed_seconds=perf_counter() - began,
                        )
                    )
                    if counts["closures"] % 25 == 0 and full_audit(current, "closure"):
                        stop_reason = "STRICT_RESIDUAL_PASS"
                        raise RouteStop
                    return torch.tensor(loss, dtype=torch.float64)
                finally:
                    closure_seconds += perf_counter() - start

            for _ in range(500):
                closure()
                start = perf_counter()
                adam.step()
                costs["optimizer_excluding_closures"] += perf_counter() - start
                counts["optimizer_updates"] += 1
                counts["adam_updates"] += 1
            lbfgs = torch.optim.LBFGS(
                parameters,
                lr=1.0,
                history_size=20,
                line_search_fn="strong_wolfe",
                max_iter=20,
                max_eval=25,
                tolerance_grad=1e-7,
                tolerance_change=1e-9,
            )
            while counts["closures"] < 2000:
                start = perf_counter()
                old_closure_seconds = closure_seconds
                try:
                    lbfgs.step(closure)
                finally:
                    costs["optimizer_excluding_closures"] += max(
                        0.0,
                        perf_counter()
                        - start
                        - (closure_seconds - old_closure_seconds),
                    )
                counts["optimizer_updates"] += 1
                counts["lbfgs_updates"] += 1
        else:
            for iteration, z, estimated in lsqr_steps(
                action.apply, lambda x: action.apply(x, adjoint=True), action.a["b"]
            ):
                current = z
                counts["lsqr_iterations"] = iteration
                emit(
                    dict(
                        kind="lsqr",
                        iteration=iteration,
                        estimated_relative=estimated / action.bnorm,
                        S=action.counts["S"],
                        SH=action.counts["SH"],
                        elapsed_seconds=perf_counter() - began,
                    )
                )
                if iteration % 25 == 0 and full_audit(current, "lsqr"):
                    stop_reason = "STRICT_RESIDUAL_PASS"
                    break
                # Includes audits and initial S^H, leaving one final S audit.
                if (
                    max(action.counts["S"], action.counts["SH"]) >= 1998
                    or perf_counter() >= deadline
                ):
                    stop_reason = (
                        "WALL_BUDGET" if perf_counter() >= deadline else "ACTION_BUDGET"
                    )
                    break
            else:
                stop_reason = "BIDIAGONALIZATION_TERMINATED"
    except RouteStop:
        pass
    finally:
        current = state_z()
        final_pass = full_audit(current, "final")
        frozen = save_checkpoint(current, final=True)
        history.close()
    if final_pass:
        stop_reason = "STRICT_RESIDUAL_PASS"
    wall = perf_counter() - began
    costs.update(
        S_all=action.costs["S"],
        SH_all=action.costs["SH"],
        audit_excluding_S=action.costs["audit"],
    )
    costs["other_control"] = max(0.0, wall - sum(costs.values()))
    return dict(
        status="STRICT_EQUATION_PASS_PENDING_BLIND_REFERENCE"
        if final_pass
        else "CONTROLLED_NUMERICAL_NEGATIVE",
        route=route,
        stop_reason=stop_reason,
        counts=counts,
        action_counts=action.counts,
        initial_scattered_trace_and_ports_zero=True,
        initial_z_sha256=initial_z_sha256,
        final_audit=audits[-1],
        audits=audits,
        state=dict(
            path=str(frozen), sha256=file_hash(frozen), z_sha256=array_hash(current)
        ),
        history=dict(
            path=str(artifact / "scalar_history.jsonl"),
            sha256=file_hash(artifact / "scalar_history.jsonl"),
        ),
        costs_exclusive_seconds=costs,
        closure_wall_seconds_nested_not_additive=closure_seconds,
        route_wall_seconds=wall,
        wall_limit_seconds=7200,
        finalization_reserve_seconds=60,
        closure_limit=2000,
        paired_action_limit=2000 if route == "FE-LSQR" else None,
        full_complex_ports=action.np,
        independent_complex_trace=action.nt,
        global_FE_matrix=False,
        global_p4_factor=False,
        private_audit_CSR=False,
        inverse_in_loss=False,
        reference_loaded=False,
        warm_start_loaded=False,
        optimizer=dict(
            adam_updates=500,
            adam_lr=0.001,
            lbfgs_history=20,
            lbfgs_lr=1.0,
            line_search="strong_wolfe",
            lbfgs_max_iter=20,
            lbfgs_max_eval=25,
            tolerance_grad=1e-7,
            tolerance_change=1e-9,
            small_gradient_is_not_a_pass=True,
        ),
    )
