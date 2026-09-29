"""Full-step equivalence and three fixed-parameter paired microbenchmarks."""

from time import perf_counter

import numpy as np
import torch

from src.solvers.neural_fe_action_packet import array_hash, file_hash
from src.solvers.neural_trace import directional_check, residual_gradient
from src.solvers.neural_trace_batched import BatchedMoments
from src.solvers.neural_trace_checks import assign, parameters
from src.solvers.neural_trace_torch import NeuralTrace, packet_forward, packet_vjp


def new_model(design):
    return NeuralTrace(
        design["geometry"]["bounds_nm"],
        design["wavelength_nm"],
        design["incidence"]["grazing_deg"],
        design["network"]["seed"],
    )


def evaluate(model, packet, moments, ports, cache=None):
    began = perf_counter()
    start = perf_counter()
    trace = packet_forward(model, moments) if cache is None else cache.forward(model)
    forward = perf_counter() - start
    z = np.r_[trace, ports[: packet.np] + 1j * ports[packet.np :]]
    action_before = dict(packet.costs)
    loss, residual, dual = residual_gradient(
        packet.apply, lambda v: packet.apply(v, adjoint=True), z, packet.a["b"]
    )
    start = perf_counter()
    gradient = (
        packet_vjp(model, moments, dual[: packet.nt])
        if cache is None
        else cache.vjp(model, dual[: packet.nt])
    )
    gradient = np.r_[gradient, dual[packet.nt :].real, dual[packet.nt :].imag]
    backward = perf_counter() - start
    return dict(
        trace=trace,
        loss=loss,
        gradient=gradient,
        residual_norm=float(np.linalg.norm(residual)),
        wall_seconds=perf_counter() - began,
        exclusive_seconds=dict(
            network_and_moment_forward=forward,
            S=packet.costs["S"] - action_before["S"],
            SH=packet.costs["SH"] - action_before["SH"],
            network_and_moment_VJP=backward,
        ),
        S_calls=1,
        SH_calls=1,
    )


def difference(left, right):
    absolute = float(np.linalg.norm(np.asarray(left) - np.asarray(right)))
    scale = float(np.linalg.norm(right))
    return dict(
        absolute=absolute,
        reference_norm=scale,
        relative=absolute / scale if scale > 1e-12 else None,
        passed=absolute <= (1e-10 * scale if scale > 1e-12 else 1e-12),
    )


def adam_clone(design, theta, ports, gradient):
    model = new_model(design)
    assign(model, theta)
    alpha = torch.nn.Parameter(torch.as_tensor(ports.copy(), dtype=torch.float64))
    tensors = [*model.parameters(), alpha]
    optimizer = torch.optim.Adam(tensors, lr=0.001)
    offset = 0
    for p in tensors:
        p.grad = torch.as_tensor(gradient[offset : offset + p.numel()].copy()).reshape(
            p.shape
        )
        offset += p.numel()
    optimizer.step()
    return np.r_[parameters(model), alpha.detach().numpy()]


def equivalence(design, packet, moments, frozen_path, plan, *, sample=None):
    began = perf_counter()
    model = new_model(design)
    zero = parameters(model)
    cache = BatchedMoments(model, moments, resource_sample=sample() if sample else None)
    rng = np.random.default_rng(plan["fallback_nonzero_seed"])
    witness = zero + rng.standard_normal(zero.shape) * plan["fallback_scale"]
    ports = (
        np.random.default_rng(plan["nonzero_port_seed"]).standard_normal(2 * packet.np)
        * plan["nonzero_port_scale"]
    )
    with np.load(frozen_path, allow_pickle=False) as state:
        old_theta, old_ports = (
            state["network_parameters"].copy(),
            state["port_parameters"].copy().reshape(-1),
        )
    rows = []
    for name, theta, alpha in (
        ("ZERO_INITIALIZATION", zero, ports),
        ("REGISTERED_NONZERO_INTERFACE_FALLBACK", witness, ports),
        ("V7_FROZEN_NEURAL", old_theta, old_ports),
    ):
        assign(model, theta)
        baseline = evaluate(model, packet, moments, alpha)
        candidate = evaluate(model, packet, moments, alpha, cache)
        first_update = adam_clone(design, theta, alpha, baseline["gradient"])
        second_update = adam_clone(design, theta, alpha, candidate["gradient"])
        comparisons = {
            key: difference(candidate[key], baseline[key])
            for key in ("trace", "loss", "gradient")
        }
        comparisons["one_clone_Adam_update"] = difference(second_update, first_update)
        ntheta = len(theta)
        hidden = ntheta - sum(p.numel() for p in model.envelopes[-1].parameters())
        norms = dict(
            hidden=float(np.linalg.norm(candidate["gradient"][:hidden])),
            output=float(np.linalg.norm(candidate["gradient"][hidden:ntheta])),
            ports=float(np.linalg.norm(candidate["gradient"][ntheta:])),
        )
        fd = None
        if name == "REGISTERED_NONZERO_INTERFACE_FALLBACK":
            vector = np.r_[theta, alpha]
            directions = []
            direction_rng = np.random.default_rng(plan["FD_direction_seed"])
            for start, stop in ((0, hidden), (hidden, ntheta), (ntheta, len(vector))):
                direction = np.zeros(len(vector))
                g = candidate["gradient"][start:stop]
                random = direction_rng.standard_normal(len(g))
                direction[start:stop] = g + 0.01 * np.linalg.norm(
                    g
                ) * random / np.linalg.norm(random)
                directions.append(direction)

            def loss_at(values, ntheta=ntheta):
                assign(model, values[:ntheta])
                tr = cache.forward(model)
                z = np.r_[
                    tr,
                    values[ntheta : ntheta + packet.np]
                    + 1j * values[ntheta + packet.np :],
                ]
                r = packet.a["b"] - packet.apply(z)
                return float(np.vdot(r, r).real / (2 * packet.bnorm**2))

            fd = directional_check(
                loss_at,
                vector,
                candidate["gradient"],
                directions,
                steps=tuple(plan["FD_steps"]),
            )
            assign(model, theta)
        passed = all(item["passed"] for item in comparisons.values())
        if name != "ZERO_INITIALIZATION":
            passed &= (
                all(value > 0 for value in norms.values()) and np.linalg.norm(alpha) > 0
            )
        if fd is not None:
            passed &= all(
                any(
                    samples[i]["relative_error"] is not None
                    and samples[i + 1]["relative_error"] is not None
                    and samples[i]["relative_error"] <= 1e-5
                    and samples[i + 1]["relative_error"] <= 1e-5
                    for i in (0, 1)
                )
                for row in fd
                for samples in [row["samples"]]
            )
        rows.append(
            dict(
                state=name,
                status="PASS" if passed else "FAIL",
                parameter_sha256=array_hash(theta),
                ports_sha256=array_hash(alpha),
                comparisons=comparisons,
                gradient_block_norms=norms,
                finite_difference=fd,
                baseline_loss=baseline["loss"],
                candidate_loss=candidate["loss"],
                old_parameters_used_only_for_equivalence=True,
                parameter_training_updates=0,
            )
        )
    return dict(
        status="PASS"
        if all(r["status"] == "PASS" for r in rows)
        else "BATCH_EQUIVALENCE_FAILED",
        states=rows,
        cache=cache.identity(),
        frozen_parameter_input=dict(
            path=str(frozen_path), sha256=file_hash(frozen_path)
        ),
        fallback_reason="V6 interface did not persist a parameter artifact",
        reference_loaded=False,
        accurate_solution_loaded=False,
        action_counts=dict(packet.counts),
        calibration_wall_seconds=perf_counter() - began,
    )


def microbenchmark(design, packet, moments, frozen_path, plan, batch, *, sample=None):
    began = perf_counter()
    model = new_model(design)
    with np.load(frozen_path, allow_pickle=False) as state:
        theta, alpha = (
            state["network_parameters"].copy(),
            state["port_parameters"].copy().reshape(-1),
        )
    assign(model, theta)
    setup = perf_counter()
    cache = (
        BatchedMoments(model, moments, resource_sample=sample() if sample else None)
        if batch == 8
        else None
    )
    cold_setup = perf_counter() - setup
    warm = []
    samples = []
    for index in range(plan["warmups"] + plan["measured_closures"]):
        record = evaluate(model, packet, moments, alpha, cache)
        for key in ("trace", "gradient"):
            record[key + "_sha256"] = array_hash(record.pop(key))
        record["index"] = index
        (warm if index < plan["warmups"] else samples).append(record)
    if array_hash(parameters(model)) != array_hash(theta):
        raise RuntimeError("fixed benchmark parameters changed")
    return dict(
        status="COMPLETED",
        batch_size=batch,
        warmups=warm,
        samples=samples,
        median_full_step_seconds=float(np.median([r["wall_seconds"] for r in samples])),
        cache=cache.identity()
        if cache
        else dict(new_persistent_cache_bytes=0, batch_size=1),
        cold_setup_seconds=cold_setup,
        benchmark_wall_seconds=perf_counter() - began,
        parameter_sha256=array_hash(theta),
        ports_sha256=array_hash(alpha),
        frozen_parameter_input=dict(
            path=str(frozen_path), sha256=file_hash(frozen_path)
        ),
        optimizer_updates=0,
        reference_loaded=False,
        action_counts=dict(packet.counts),
        full_network_moments_S_SH_VJP_included=True,
        shared_workstation=True,
    )
