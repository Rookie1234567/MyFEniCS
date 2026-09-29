"""ML-only tests use finite moment packets and no FE runtime imports."""

import numpy as np
import torch

from src.solvers.neural_trace_checks import check_packet_gradient
from src.solvers.neural_trace_torch import NeuralTrace, packet_forward


def model():
    return NeuralTrace([[-0.7, 0.7], [-0.525, 0.525], [-0.175, 1.225]], 0.7)


def packet():
    return dict(
        reference_points=np.array([[0.1, 0.2, 0.3], [0.6, 0.7, 0.8]]),
        interpolation=np.arange(24, dtype=float).reshape(4, 6) / 23,
        transforms=np.array(
            [
                np.eye(4),
                np.array([[0, -1, 0, 0], [-1, 0, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]),
            ]
        ),
        owner_rows=np.array([[0, 1, -1, -1], [-1, -1, 2, 3]]),
        orientation_ids=np.array([0, 1]),
        jacobians=np.array([np.diag([0.175] * 3)] * 2),
        origins=np.array([[0.1, 0.1, 0.1], [0.1, 0.1, 0.4]]),
        active_rows=np.array(4),
    )


def test_fixed_network_zero_start_carriers_and_parameter_count():
    net = model()
    assert sum(p.numel() for p in net.parameters()) == 11696
    assert all(p.dtype == torch.float64 for p in net.parameters())
    assert torch.count_nonzero(net(torch.rand(7, 3, dtype=torch.float64))) == 0
    assert torch.count_nonzero(net.envelopes[0].weight) > 0
    assert net.wavevectors.shape == (8, 3)
    assert np.allclose(
        torch.linalg.norm(net.wavevectors, dim=1).numpy(), 2 * np.pi / 0.7
    )
    assert np.count_nonzero(packet_forward(net, packet())) == 0


def test_nonzero_real_gradient_chunk_and_monolithic_with_ports():
    net = model()
    generator = torch.Generator().manual_seed(420907)
    with torch.no_grad():
        for parameter in net.envelopes[-1].parameters():
            parameter.copy_(
                torch.randn(parameter.shape, generator=generator, dtype=torch.float64)
                * 0.01
            )
    record = check_packet_gradient(net, packet())
    assert record["status"] == "PASS"
    assert len(record["real_parameter_directions"]) == 3
    assert (
        record["optimizer_updates"]
        == record["target_S_calls"]
        == record["target_adjoint_calls"]
        == 0
    )
    assert record["synthetic_nonzero_ports"] == 3 and not record["physical_ports_known"]
