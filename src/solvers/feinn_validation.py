"""Nonzero complete-network derivative, quadrature and batch qualification."""

import copy
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy import sparse
import torch

from src.solvers.feinn_native import load_native, ResidualMetric
from src.solvers.feinn_riesz import SparseRiesz
from src.solvers.feinn_torch import CoordinateField, CompleteMomentMap
from src.solvers.neural_fe_action_packet import array_hash


def parameters(model):
    return (
        torch.nn.utils.parameters_to_vector(model.parameters()).detach().numpy().copy()
    )


def assign(model, values):
    values = np.asarray(values, dtype=np.float64)
    with torch.no_grad():
        offset = 0
        for p in model.parameters():
            p.copy_(
                torch.as_tensor(values[offset : offset + p.numel()].reshape(p.shape))
            )
            offset += p.numel()
    if offset != len(values):
        raise ValueError("parameter inventory mismatch")


def load_moments(path):
    with np.load(path, allow_pickle=False) as data:
        return {k: np.array(data[k]) for k in data.files}


def paired(left, right):
    left, right = np.asarray(left), np.asarray(right)
    absolute = float(np.linalg.norm(left - right))
    denominator = float(max(np.linalg.norm(right), 1e-12))
    return dict(
        absolute=absolute, denominator=denominator, relative=absolute / denominator
    )


def qualify(design, index, artifact, marker):
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    if (
        torch.cuda.is_available()
        or torch.get_num_threads() != 1
        or torch.get_num_interop_threads() != 1
    ):
        raise RuntimeError("CPU-only Torch one-thread gate failed")
    start = perf_counter()
    paths = {k: Path(v["path"]) for k, v in index["files"].items()}
    packet = load_native(paths["native"])
    mapping = CompleteMomentMap(load_moments(paths["moments_q15"]))
    model = CoordinateField(design["geometry"]["bounds_nm"])
    zero_parameters = parameters(model)
    zero = mapping.forward(model)
    if np.max(abs(zero)) != 0:
        raise ValueError(
            "last-zero layer did not give exact zero scattered coefficients"
        )
    rng = np.random.default_rng(421002)
    p = zero_parameters + 0.005 * rng.standard_normal(len(zero_parameters))
    assign(model, p)
    c8 = mapping.forward(model, 8)
    c1 = mapping.forward(model, 1)
    higher = CompleteMomentMap(load_moments(paths["moments_q30"]))
    c30 = higher.forward(model, 8)
    quadrature = paired(c8, c30)
    marker("nonzero_quadrature_15_30", quadrature)
    if quadrature["relative"] > 1e-8:
        raise RuntimeError(
            "MOMENT_QUADRATURE_60_REQUIRED; bounded sequence, no training started"
        )
    del higher
    gram = SparseRiesz(sparse.load_npz(paths["gram"]), design, marker)
    try:
        solve_witnesses = []
        for _ in range(3):
            rhs = rng.standard_normal(packet.size) + 1j * rng.standard_normal(
                packet.size
            )
            q = gram.solve(rhs)
            solve_witnesses.append(
                float(np.linalg.norm(gram.G @ q - rhs) / np.linalg.norm(rhs))
            )
        results = {}
        for name, g in [("EUC", None), ("DUAL", gram)]:
            metric = ResidualMetric(packet, g)
            loss8, _, dual8 = metric.value(c8, gradient=True)
            grad8 = mapping.vjp(model, dual8, 8)
            loss1, _, dual1 = metric.value(c1, gradient=True)
            grad1 = mapping.vjp(model, dual1, 1)
            # Directions with derivatives well above the explicit near-zero floor.
            directions = []
            last_start = len(p) - (64 * 6 + 6)
            hidden = grad8.copy()
            hidden[last_start:] = 0
            final = grad8.copy()
            final[:last_start] = 0
            random = rng.standard_normal(len(p))
            directions.extend([hidden, final, random])
            fd_records = []
            for number, d in enumerate(directions):
                if not np.linalg.norm(d) > 0:
                    raise ValueError("NONZERO_GRADIENT_DIRECTION_MISSING")
                d /= np.linalg.norm(d)
                exact = float(np.dot(grad8, d))
                if abs(exact) <= 1e-10:
                    raise ValueError("NONZERO_DIRECTION_DERIVATIVE_TOO_SMALL")
                samples = []
                for h in (1e-4, 1e-5, 1e-6):
                    assign(model, p + h * d)
                    plus = metric.value(mapping.forward(model))[0]
                    assign(model, p - h * d)
                    minus = metric.value(mapping.forward(model))[0]
                    observed = (plus - minus) / (2 * h)
                    relative = abs(observed - exact) / abs(exact)
                    samples.append(
                        dict(
                            h=h,
                            finite_difference=observed,
                            absolute_error=abs(observed - exact),
                            relative_error=relative,
                            passed=relative <= 1e-5,
                        )
                    )
                stable = any(
                    samples[i]["passed"] and samples[i + 1]["passed"] for i in range(2)
                )
                fd_records.append(
                    dict(
                        direction=number,
                        kind=("hidden", "final", "random")[number],
                        analytic=exact,
                        samples=samples,
                        two_consecutive_pass=stable,
                    )
                )
            assign(model, p)
            updates = []
            for grad in (grad1, grad8):
                clone = copy.deepcopy(model)
                optimizer = torch.optim.Adam(
                    clone.parameters(), lr=1e-3, weight_decay=0
                )
                offset = 0
                for parameter in clone.parameters():
                    parameter.grad = torch.as_tensor(
                        grad[offset : offset + parameter.numel()].reshape(
                            parameter.shape
                        )
                    ).clone()
                    offset += parameter.numel()
                optimizer.step()
                updates.append(parameters(clone))
            batch = dict(
                coefficients=paired(c1, c8),
                loss=paired(loss1, loss8),
                VJP=paired(grad1, grad8),
                one_Adam_update=paired(*updates),
            )
            passed = all(v["relative"] <= 1e-10 for v in batch.values()) and all(
                x["two_consecutive_pass"] for x in fd_records
            )
            results[name] = dict(
                status="PASS" if passed else "GRADIENT_BATCH_FAILED",
                nonzero_coefficient_norm=float(np.linalg.norm(c8)),
                fixed_loss_denominator=metric.denominator,
                batch1_8=batch,
                directional_derivatives=fd_records,
            )
            marker("full_gradient_" + name, results[name])
        if any(v["status"] != "PASS" for v in results.values()):
            raise RuntimeError("FULL_GRADIENT_GATE_FAILED")
        path = artifact / "qualified_moments.npz"
        np.savez(path, **mapping.packet)
        result = dict(
            status="INTERFACE_PASS_ONLY",
            quadrature_15_30=quadrature,
            frozen_quadrature_degree=15,
            quadrature60="not_run: 15/30 qualified",
            gradients=results,
            Gram_solve_witnesses=solve_witnesses,
            Gram_factor=dict(gram.record),
            Gram_max_solve_relative=gram.max_relative,
            parameters=8966,
            initialization_sha256=array_hash(zero_parameters),
            witness_parameters_sha256=array_hash(p),
            candidate_initialization_is_witness=False,
            cache_payload_bytes=mapping.numeric_cache_bytes,
            max_graph_cells=8,
            reference_loaded=False,
            seconds=perf_counter() - start,
        )
    finally:
        gram.close()
    result["Gram_factor"] = gram.record
    return result, dict(moments=path)
