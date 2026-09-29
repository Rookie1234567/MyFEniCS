"""Bounded ML interface checks; synthetic S is never a physical Gate."""

import copy
import time

import numpy as np
import torch

from src.solvers.neural_trace import directional_check, residual_gradient
from src.solvers.neural_trace_torch import (
    NeuralTrace,
    packet_blocks,
    packet_forward,
    packet_vjp,
)


def subset(packet, count=2):
    result = {key: value for key, value in packet.items()}
    cells = np.flatnonzero(np.any(packet["owner_rows"] >= 0, axis=1))[:count]
    owners = np.array(packet["owner_rows"][cells], copy=True)
    owners[owners >= 0] = np.arange(np.count_nonzero(owners >= 0))
    result.update(
        owner_rows=owners,
        origins=packet["origins"][cells],
        jacobians=packet["jacobians"][cells],
        orientation_ids=packet["orientation_ids"][cells],
        active_rows=np.asarray(np.count_nonzero(owners >= 0)),
    )
    return result


def parameters(model):
    return (
        torch.nn.utils.parameters_to_vector(model.parameters()).detach().numpy().copy()
    )


def assign(model, vector):
    with torch.no_grad():
        offset = 0
        for param in model.parameters():
            param.copy_(
                torch.as_tensor(vector[offset : offset + param.numel()]).reshape(
                    param.shape
                )
            )
            offset += param.numel()


def check_packet_gradient(model, packet):
    """At nonzero theta/ports, test full complex loss and chunked gradients."""
    packet = subset(packet)
    count = int(packet["active_rows"])
    rng = np.random.default_rng(420907)
    matrix = (
        rng.standard_normal((count + 3, count + 3))
        + 1j * rng.standard_normal((count + 3, count + 3))
    ) / np.sqrt(count + 3)
    matrix += 2 * np.eye(count + 3)
    rhs = rng.standard_normal(count + 3) + 1j * rng.standard_normal(count + 3)
    port_parameters = rng.standard_normal(6) * 0.1
    initial = parameters(model)
    vector = np.concatenate((initial, port_parameters))
    nparam = len(initial)
    z = np.concatenate(
        (packet_forward(model, packet), port_parameters[:3] + 1j * port_parameters[3:])
    )
    loss, residual, dual = residual_gradient(
        lambda x: matrix @ x, lambda x: matrix.conj().T @ x, z, rhs
    )
    chunk_gradient = np.concatenate(
        (packet_vjp(model, packet, dual[:count]), dual[count:].real, dual[count:].imag)
    )

    model.zero_grad(set_to_none=True)
    reduced = torch.zeros(count, dtype=torch.complex128)
    for rows, values in packet_blocks(model, packet):
        reduced = reduced.index_copy(0, torch.as_tensor(rows), values)
    ports = torch.tensor(port_parameters, dtype=torch.float64, requires_grad=True)
    values = torch.cat((reduced, torch.complex(ports[:3], ports[3:])))
    r = torch.as_tensor(rhs) - torch.as_tensor(matrix) @ values
    monolithic_loss = torch.real(torch.vdot(r, r)) / (2 * np.vdot(rhs, rhs).real)
    monolithic_loss.backward()
    mono_gradient = np.concatenate(
        (
            torch.cat([p.grad.reshape(-1) for p in model.parameters()])
            .detach()
            .numpy(),
            ports.grad.numpy(),
        )
    )
    gradient_difference = float(
        np.linalg.norm(chunk_gradient - mono_gradient) / np.linalg.norm(mono_gradient)
    )
    updates_difference = float(
        np.linalg.norm(
            (vector - 1e-3 * chunk_gradient) - (vector - 1e-3 * mono_gradient)
        )
    )
    hidden_count = nparam - sum(p.numel() for p in model.envelopes[-1].parameters())
    directions = []
    for start, stop in (
        (0, hidden_count),
        (hidden_count, nparam),
        (nparam, len(vector)),
    ):
        direction = np.zeros_like(vector)
        direction[start:stop] = chunk_gradient[start:stop]
        if np.linalg.norm(direction) == 0:
            raise ValueError("nonzero gradient direction missing")
        directions.append(direction)
    evaluations = 0

    def loss_at(values):
        nonlocal evaluations
        evaluations += 1
        assign(model, values[:nparam])
        alpha = values[nparam : nparam + 3] + 1j * values[nparam + 3 :]
        candidate = np.concatenate((packet_forward(model, packet), alpha))
        r = rhs - matrix @ candidate
        return float(np.vdot(r, r).real / (2 * np.vdot(rhs, rhs).real))

    try:
        finite_difference = directional_check(
            loss_at, vector, chunk_gradient, directions
        )
    finally:
        assign(model, initial)
    adjoint_left = np.vdot(rhs, matrix @ z)
    adjoint_right = np.vdot(matrix.conj().T @ rhs, z)
    dot_difference = float(
        abs(adjoint_left - adjoint_right) / max(abs(adjoint_left), abs(adjoint_right))
    )
    passed = (
        gradient_difference <= 1e-10
        and dot_difference <= 1e-10
        and all(
            all(sample["passed"] for sample in item["samples"])
            for item in finite_difference
        )
    )
    return dict(
        status="PASS" if passed else "FAIL",
        identity="SYNTHETIC_NON_HERMITIAN_NOT_PHYSICAL_S",
        trace_rows=count,
        synthetic_nonzero_ports=3,
        physical_ports_known=False,
        matrix_nonhermitian_relative=float(
            np.linalg.norm(matrix - matrix.conj().T) / np.linalg.norm(matrix)
        ),
        adjoint_dot_relative=dot_difference,
        real_parameter_directions=finite_difference,
        chunk_monolithic_gradient_relative=gradient_difference,
        single_update_comparison_absolute=updates_difference,
        loss_numpy=loss,
        loss_autograd=float(monolithic_loss.detach()),
        residual_norm=float(np.linalg.norm(residual)),
        diagnostic_loss_evaluations=evaluations,
        optimizer_updates=0,
        target_S_calls=0,
        target_adjoint_calls=0,
        no_true_S_qualification_claim=True,
    )


def check_neural_interface(design, packets):
    began = time.perf_counter()
    model = NeuralTrace(design["geometry"]["bounds_nm"], design["wavelength_nm"])
    zero_initial = parameters(model)
    initial_field = model(torch.tensor([[0.11, 0.03, 0.4]], dtype=torch.float64))
    if torch.count_nonzero(initial_field) != 0:
        raise ValueError("initial scattered field must be exactly zero")
    # Only the N1 witness is nonzero; a fresh N2 candidate would retain zero init.
    witness = copy.deepcopy(model)
    generator = torch.Generator().manual_seed(420907)
    with torch.no_grad():
        for param in witness.envelopes[-1].parameters():
            param.copy_(
                torch.randn(param.shape, generator=generator, dtype=torch.float64)
                * 0.01
            )
    build_seconds = time.perf_counter() - began
    began = time.perf_counter()
    low = packet_forward(witness, packets[15])
    forward15_seconds = time.perf_counter() - began
    began = time.perf_counter()
    high = packet_forward(witness, packets[30])
    forward30_seconds = time.perf_counter() - began
    norm = float(np.linalg.norm(high))
    absolute = float(np.linalg.norm(low - high))
    relative = absolute / norm if norm > 1e-12 else None
    quadrature_pass = absolute <= 1e-12 if relative is None else relative <= 1e-8
    began = time.perf_counter()
    checks = check_packet_gradient(witness, packets[15])
    gradient_seconds = time.perf_counter() - began
    # Independent NumPy evaluation of the same frozen MLP checks the FE/ML packet.
    from src.solvers.neural_trace import moment_packet_values

    weights = [
        (layer.weight.detach().numpy(), layer.bias.detach().numpy())
        for layer in witness.envelopes
        if isinstance(layer, torch.nn.Linear)
    ]

    def numpy_network(points):
        value = (points - witness.center.numpy()) / witness.half_width.numpy()
        for index, (weight, bias) in enumerate(weights):
            value = value @ weight.T + bias
            if index < 3:
                value = np.tanh(value)
        envelopes = value.reshape(-1, 8, 3, 2)
        return np.sum(
            (envelopes[..., 0] + 1j * envelopes[..., 1])
            * np.exp(1j * (points @ witness.wavevectors.numpy().T))[:, :, None],
            axis=1,
        )

    began = time.perf_counter()
    independent = moment_packet_values(packets[15], numpy_network)
    numpy_seconds = time.perf_counter() - began
    packet_difference = float(
        np.linalg.norm(low - independent) / np.linalg.norm(independent)
    )
    return (
        dict(
            status="PASS"
            if checks["status"] == "PASS"
            and quadrature_pass
            and packet_difference <= 1e-10
            else "FAIL",
            architecture=design["network"],
            parameters=len(zero_initial),
            parameter_bytes=zero_initial.nbytes,
            initial_scattered_trace_zero=True,
            n1_nonzero_witness_seed=420907,
            witness_not_a_trained_candidate=True,
            active_trace_rows=int(packets[15]["active_rows"]),
            full_packet_network_norm=norm,
            numpy_torch_packet_relative=packet_difference,
            moment_quadrature=dict(
                selected=15 if quadrature_pass else None,
                comparison=30,
                norm=norm,
                absolute_difference=absolute,
                relative_difference=relative,
                tolerance=1e-8,
                passed=quadrature_pass,
                degree60="not_run; 15 passed"
                if quadrature_pass
                else "not_run material-blocked partial interface",
            ),
            gradient=checks,
            costs_exclusive_seconds=dict(
                network_initialization=build_seconds,
                network_moments_q15=forward15_seconds,
                higher_quadrature_witness_q30=forward30_seconds,
                synthetic_gradient_checks=gradient_seconds,
                independent_numpy_packet=numpy_seconds,
            ),
            training_updates=0,
            real_S_gate="NOT_RUN_MATERIAL_BLOCKED",
            real_port_gate="NOT_RUN_MATERIAL_BLOCKED",
        ),
        model.state_dict(),
        witness.state_dict(),
    )
