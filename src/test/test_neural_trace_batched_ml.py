"""Bounded affine Piola/orientation/owner and parameter-VJP equivalence."""

import json
from pathlib import Path

import numpy as np
import torch

from src.solvers.neural_trace_batched import BatchedMoments
from src.solvers.neural_trace_torch import (
    NeuralTrace,
    packet_forward,
    packet_vjp,
    qualify_threads,
)


def check():
    rng = np.random.default_rng(420915)
    model = NeuralTrace([[-1, 1], [-1, 1], [-1, 1]], 0.7)
    with torch.no_grad():
        model.envelopes[-1].weight.copy_(
            torch.as_tensor(
                rng.standard_normal(model.envelopes[-1].weight.shape) * 0.01
            )
        )
    jacobians = np.array([np.diag([0.1, 0.15, 0.12]) for _ in range(10)])
    owners = np.arange(60).reshape(10, 6)
    owners[:, 1] = -1
    # Compress canonical owner rows, retaining the ignored local moments.
    owners[owners >= 0] = np.arange((owners >= 0).sum())
    packet = dict(
        reference_points=rng.random((7, 3)),
        interpolation=rng.standard_normal((6, 21)),
        transforms=np.array([np.eye(6), rng.standard_normal((6, 6))]),
        orientation_ids=np.arange(10) % 2,
        jacobians=jacobians,
        origins=rng.random((10, 3)) - 0.5,
        owner_rows=owners,
        active_rows=np.array(50),
    )
    cache = BatchedMoments(model, packet)
    expected, actual = packet_forward(model, packet), cache.forward(model)
    dual = rng.standard_normal(50) + 1j * rng.standard_normal(50)
    original, new = packet_vjp(model, packet, dual), cache.vjp(model, dual)
    trace_error = float(np.linalg.norm(expected - actual) / np.linalg.norm(expected))
    gradient_error = float(np.linalg.norm(original - new) / np.linalg.norm(original))
    assert trace_error <= 1e-10 and gradient_error <= 1e-10
    assert cache.cache_bytes <= cache.cache_upper_bytes
    try:
        BatchedMoments(model, packet, cache_limit=1)
    except ValueError:
        pass
    else:
        raise AssertionError("cache must be rejected before allocation")
    return dict(
        status="PASS",
        trace_relative=trace_error,
        gradient_relative=gradient_error,
        nonzero_gradient_norm=float(np.linalg.norm(new)),
        cache=cache.identity(),
        tests=2,
        partial_final_batch=True,
        nontrivial_orientation=True,
        owner_filter=True,
    )


if __name__ == "__main__":
    import sys

    threads = qualify_threads()
    report = check()
    report["threads"] = threads
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
