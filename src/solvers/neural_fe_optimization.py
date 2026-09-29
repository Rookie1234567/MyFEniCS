"""Three frozen, independent single-solve routes; no teacher or inverse."""

import json
from pathlib import Path
from time import perf_counter

import numpy as np

from src.solvers.bounded_complex_lsqr import lsqr_steps
from src.solvers.neural_fe_action_packet import array_hash, file_hash
from src.solvers.optimizer_step_transaction import OptimizerTransaction


class RouteStop(Exception):
    pass


def optimize_route(
    design, action, moments, route, artifact, *, wall_seconds=7200, column_scale=None
):
    """One zero-scattered run, strict audits and exact work accounting."""
    began = perf_counter()
    pre_route_action_costs = dict(action.costs)
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
        closure_calls=0,
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
    is_lsqr = route in ("FE-LSQR", "FE-LSQR-COLUMN-SCALED")
    if (route == "FE-LSQR-COLUMN-SCALED") != (column_scale is not None):
        raise ValueError("column scale is an explicit reviewed LSQR opt-in")
    scaled_operator = None
    scaled_y = None
    if column_scale is not None:
        from src.solvers.neural_fe_column_scaling import ColumnScaledOperator

        scaled_operator = ColumnScaledOperator(action, column_scale)
    stop_reason = "ACTION_BUDGET" if is_lsqr else "CLOSURE_BUDGET"
    parameters = None
    model = None
    free = None
    port_parameters = None
    closure_seconds = 0.0
    transaction = None

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

    def save_checkpoint(z, *, final=False, state_kind="LAST_COMPLETED_OUTER_STEP"):
        start = perf_counter()
        data = dict(
            z=np.asarray(z),
            closures=np.array(counts["closures"]),
            optimizer_updates=np.array(counts["optimizer_updates"]),
            state_kind=np.array(state_kind),
            closure_count_meaning=np.array("CONSUMED_NOT_PARAMETER_BOUNDARY"),
            checkpoint_qualification=np.array(
                "PARAMETER_ONLY_CHECKPOINT_NOT_RESUMABLE"
            ),
        )
        if model is not None:
            from src.solvers.neural_trace_checks import parameters as model_parameters

            data["network_parameters"] = model_parameters(model)
            data["port_parameters"] = port_parameters.detach().numpy()
        elif free is not None:
            data["free_parameters"] = free.detach().numpy()
        if scaled_y is not None:
            data["scaled_y"] = scaled_y
        path = artifact / (
            "frozen_state.npz"
            if final
            else "latest_trial_checkpoint.npz"
            if state_kind == "TRIAL_CLOSURE_OBSERVATION"
            else "latest_checkpoint.npz"
        )
        np.savez(path, **data)
        costs["io"] += perf_counter() - start
        return path

    def full_audit(z, tag, state_kind="LAST_COMPLETED_OUTER_STEP"):
        result = action.audit(z)
        audits.append(
            dict(
                tag=tag,
                state_kind=state_kind,
                outer_id=transaction.attempts if transaction else 0,
                acceptance="UNKNOWN_NOT_COMMITTED"
                if state_kind == "TRIAL_CLOSURE_OBSERVATION"
                else "DECLARED_BOUNDARY",
                closures=counts["closures"],
                updates=counts["optimizer_updates"],
                lsqr_iterations=counts["lsqr_iterations"],
                elapsed_seconds=perf_counter() - began,
                **result,
            )
        )
        emit(dict(kind="audit", **audits[-1]))
        save_checkpoint(z, state_kind=state_kind)
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
        if not is_lsqr:
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
        if full_audit(current, "initial", "INITIAL_COMMITTED_STATE"):
            stop_reason = "STRICT_RESIDUAL_PASS"
            raise RouteStop
        if not is_lsqr:
            adam = torch.optim.Adam(parameters, lr=0.001, weight_decay=0)
            transaction = OptimizerTransaction(parameters)

            def closure():
                nonlocal current, closure_seconds, stop_reason
                counts["closure_calls"] += 1
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
                            state_kind="TRIAL_CLOSURE_OBSERVATION",
                            outer_id=transaction.attempts,
                            acceptance="UNKNOWN_NOT_COMMITTED",
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
                    if counts["closures"] % 25 == 0 and full_audit(
                        current, "closure", "TRIAL_CLOSURE_OBSERVATION"
                    ):
                        stop_reason = "STRICT_RESIDUAL_PASS"
                        raise RouteStop
                    return torch.tensor(loss, dtype=torch.float64)
                finally:
                    closure_seconds += perf_counter() - start

            def adam_operation():
                closure()
                adam.step()
                counts["optimizer_updates"] += 1
                counts["adam_updates"] += 1

            for _ in range(500):
                start = perf_counter()
                old_closure_seconds = closure_seconds
                try:
                    transaction.step(
                        adam, adam_operation, phase="ADAM", counts=lambda: counts
                    )
                finally:
                    costs["optimizer_excluding_closures"] += max(
                        0.0,
                        perf_counter()
                        - start
                        - (closure_seconds - old_closure_seconds),
                    )
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

            def lbfgs_operation():
                value = lbfgs.step(closure)
                counts["optimizer_updates"] += 1
                counts["lbfgs_updates"] += 1
                return value

            while counts["closures"] < 2000:
                start = perf_counter()
                old_closure_seconds = closure_seconds
                try:
                    transaction.step(
                        lbfgs, lbfgs_operation, phase="LBFGS", counts=lambda: counts
                    )
                finally:
                    costs["optimizer_excluding_closures"] += max(
                        0.0,
                        perf_counter()
                        - start
                        - (closure_seconds - old_closure_seconds),
                    )
        else:
            forward = scaled_operator.apply if scaled_operator else action.apply
            adjoint = (
                scaled_operator.adjoint
                if scaled_operator
                else lambda x: action.apply(x, adjoint=True)
            )
            for iteration, z, estimated in lsqr_steps(forward, adjoint, action.a["b"]):
                scaled_y = z if scaled_operator else None
                current = scaled_operator.recover(z) if scaled_operator else z
                counts["lsqr_iterations"] = iteration
                emit(
                    dict(
                        kind="lsqr",
                        state_kind="LSQR_ITERATE",
                        outer_id=0,
                        closure_id=None,
                        acceptance="RECURRENCE_COMPLETED",
                        iteration=iteration,
                        estimated_relative=estimated / action.bnorm,
                        S=action.counts["S"],
                        SH=action.counts["SH"],
                        elapsed_seconds=perf_counter() - began,
                    )
                )
                if iteration % 25 == 0 and full_audit(current, "lsqr", "LSQR_ITERATE"):
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
        final_kind = (
            "LSQR_ITERATE"
            if is_lsqr
            else transaction.committed["state_kind"]
            if transaction and transaction.committed
            else "INITIAL_COMMITTED_STATE"
        )
        final_pass = full_audit(current, "final", final_kind)
        frozen = save_checkpoint(current, final=True, state_kind=final_kind)
        start_io = perf_counter()
        optimizer_states = transaction.save(artifact) if transaction else None
        costs["io"] += perf_counter() - start_io
        history.close()
    if final_pass:
        stop_reason = "STRICT_RESIDUAL_PASS"
    elif stop_reason == "STRICT_RESIDUAL_PASS":
        stop_reason = "STRICT_TRIAL_OBSERVED_COMMITTED_STATE_NOT_QUALIFIED"
    wall = perf_counter() - began
    costs.update(
        S_all=action.costs["S"] - pre_route_action_costs["S"],
        SH_all=action.costs["SH"] - pre_route_action_costs["SH"],
        audit_excluding_S=action.costs["audit"] - pre_route_action_costs["audit"],
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
        state_kind=final_kind,
        optimizer_states=optimizer_states,
        stopped_trial_never_promoted_to_committed=True,
        V7_acceptance_semantics="V7_ACCEPTANCE_STATE_UNKNOWN; old vectors and audits unchanged",
        costs_exclusive_seconds=costs,
        closure_wall_seconds_nested_not_additive=closure_seconds,
        route_wall_seconds=wall,
        wall_limit_seconds=7200,
        finalization_reserve_seconds=60,
        closure_limit=2000,
        paired_action_limit=2000 if is_lsqr else None,
        column_scaling=column_scale is not None,
        pre_route_action_costs_seconds=pre_route_action_costs,
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
