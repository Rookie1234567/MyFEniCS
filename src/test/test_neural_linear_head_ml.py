"""Small original-moment/output-head identity with nontrivial orientations."""

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from src.solvers.neural_linear_head_torch import (
    assign_head,
    build_head_mapping,
    head_coefficients,
)
from src.solvers.neural_trace_batched import BatchedMoments
from src.solvers.neural_trace_torch import NeuralTrace, packet_forward, qualify_threads


def check():
    rng = np.random.default_rng(421010)
    model = NeuralTrace([[-1, 1]] * 3, 0.7)
    owners = np.arange(60).reshape(10, 6)
    owners[:, 1] = -1
    owners[owners >= 0] = np.arange(np.count_nonzero(owners >= 0))
    packet = {
        "reference_points": rng.random((7, 3)),
        "interpolation": rng.standard_normal((6, 21)),
        "transforms": np.array([np.eye(6), rng.standard_normal((6, 6))]),
        "orientation_ids": np.arange(10) % 2,
        "jacobians": np.array(
            [
                np.array([[0.1, 0.02, 0], [0, 0.15, 0.03], [0.01, 0, 0.12]])
                for _ in range(10)
            ]
        ),
        "origins": rng.random((10, 3)) - 0.5,
        "owner_rows": owners,
        "active_rows": np.array(50),
    }
    cache = BatchedMoments(model, packet)
    errors = []
    with TemporaryDirectory(dir=Path("tmp/task042/v10")) as directory:
        P, _ = build_head_mapping(model, cache, Path(directory) / "P.npy")
        for _ in range(3):
            gamma = 0.01 * (rng.normal(size=1560) + 1j * rng.normal(size=1560))
            assign_head(model, gamma)
            assert np.array_equal(gamma, head_coefficients(model))
            actual = packet_forward(model, packet)
            errors.append(
                float(np.linalg.norm(actual - P @ gamma) / np.linalg.norm(actual))
            )
        assert max(errors) < 1e-10
    return {
        "status": "PASS",
        "tests": 3,
        "head_original_moment_relative_errors": errors,
        "nontrivial_orientation": True,
        "non_diagonal_piola": True,
        "partial_batch": True,
        "owner_filter": True,
        "real_imag_coefficient_order_checked": True,
    }


if __name__ == "__main__":
    threads = qualify_threads()
    report = check()
    report["threads"] = threads
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
