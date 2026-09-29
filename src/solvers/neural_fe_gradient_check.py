"""Nonzero real-parameter derivatives of the full physical Maxwell loss."""

import numpy as np
import torch

from src.solvers.neural_trace import directional_check, residual_gradient
from src.solvers.neural_trace_checks import assign, parameters
from src.solvers.neural_trace_torch import (
    NeuralTrace,
    packet_blocks,
    packet_forward,
    packet_vjp,
)


def check_real_gradient(design, action, moments):
    model = NeuralTrace(
        design["geometry"]["bounds_nm"],
        design["wavelength_nm"],
        design["incidence"]["grazing_deg"],
        design["network"]["seed"],
    )
    zero_initial = parameters(model)
    if np.any(packet_forward(model, moments)):
        raise ValueError("frozen neural initial scattered trace is not zero")
    rng = np.random.default_rng(420907)
    with torch.no_grad():
        # Only a nonzero interface witness; never a training initialization.
        model.envelopes[-1].weight.copy_(
            torch.as_tensor(
                rng.standard_normal(model.envelopes[-1].weight.shape) * 0.01
            )
        )
        model.envelopes[-1].bias.copy_(
            torch.as_tensor(rng.standard_normal(model.envelopes[-1].bias.shape) * 0.01)
        )
    theta = parameters(model)
    ports = rng.standard_normal(2 * action.np) * 0.1
    vector = np.r_[theta, ports]
    ntheta = len(theta)
    z = np.r_[
        packet_forward(model, moments), ports[: action.np] + 1j * ports[action.np :]
    ]
    loss, residual, dual = residual_gradient(
        action.apply, lambda x: action.apply(x, adjoint=True), z, action.a["b"]
    )
    gradient = np.r_[
        packet_vjp(model, moments, dual[: action.nt]),
        dual[action.nt :].real,
        dual[action.nt :].imag,
    ]
    hidden = ntheta - sum(p.numel() for p in model.envelopes[-1].parameters())
    directions = []
    for start, stop in ((0, hidden), (hidden, ntheta), (ntheta, len(vector))):
        direction = np.zeros(len(vector))
        direction[start:stop] = gradient[start:stop]
        if np.linalg.norm(direction) == 0:
            raise ValueError("nonzero hidden/final/port gradient witness required")
        directions.append(direction)

    def loss_at(values):
        assign(model, values[:ntheta])
        alpha = values[ntheta : ntheta + action.np] + 1j * values[ntheta + action.np :]
        candidate = np.r_[packet_forward(model, moments), alpha]
        r = action.a["b"] - action.apply(candidate)
        return float(np.vdot(r, r).real / (2 * action.bnorm**2))

    finite_difference = directional_check(loss_at, vector, gradient, directions)
    assign(model, theta)
    # Small one-graph pairing with dual values from the REAL full S^H loss.
    selected = np.flatnonzero(np.any(moments["owner_rows"] >= 0, axis=1))[:2]
    model.zero_grad(set_to_none=True)
    for rows, values in packet_blocks(model, moments, cells=selected):
        torch.real(torch.vdot(torch.as_tensor(dual[rows]), values)).backward()
    separate = (
        torch.cat([p.grad.reshape(-1) for p in model.parameters()])
        .detach()
        .numpy()
        .copy()
    )
    model.zero_grad(set_to_none=True)
    functional = torch.zeros((), dtype=torch.float64)
    for rows, values in packet_blocks(model, moments, cells=selected):
        functional = functional + torch.real(
            torch.vdot(torch.as_tensor(dual[rows]), values)
        )
    functional.backward()
    mono = torch.cat([p.grad.reshape(-1) for p in model.parameters()]).detach().numpy()
    chunk_defect = float(np.linalg.norm(separate - mono) / np.linalg.norm(mono))
    stable = all(
        any(samples[i]["passed"] and samples[i + 1]["passed"] for i in (0, 1))
        for row in finite_difference
        for samples in [row["samples"]]
    )
    report = dict(
        status="PASS"
        if stable and chunk_defect <= 1e-10
        else "N1_REAL_GRADIENT_FAILED",
        physical_operator=True,
        synthetic_operator=False,
        nonzero_network_witness=True,
        physical_schur_loss=loss,
        residual_norm=float(np.linalg.norm(residual)),
        gradient_norm=float(np.linalg.norm(gradient)),
        network_parameters=ntheta,
        full_complex_ports=action.np,
        finite_difference=finite_difference,
        stable_zone_rule="at least two consecutive preregistered h values pass each direction",
        real_S_adjoint_actions=action.counts.copy(),
        chunk_real_dual_monolithic_relative=chunk_defect,
        zero_initial_sha256=__import__("hashlib")
        .sha256(zero_initial.tobytes())
        .hexdigest(),
        reference_loaded=False,
        target_solution_loaded=False,
        optimizer_updates=0,
    )
    return report
