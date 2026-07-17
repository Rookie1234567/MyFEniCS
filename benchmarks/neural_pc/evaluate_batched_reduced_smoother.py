from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from benchmarks.neural_pc.data_contract import load_dataset
from src.solvers.batched_reduced_smoother import FrozenLinearReducedMap, FusedLinearReducedAction
from src.solvers.neural_local_pc import FrozenNumpyMlp


def _stats(values: list[float]) -> dict[str, float]:
    array = np.asarray(values)
    return {"mean_s": float(array.mean()), "median_s": float(np.median(array)), "p95_s": float(np.quantile(array, .95))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repeats", type=int, default=100)
    parser.add_argument("--task001-checkpoint")
    args = parser.parse_args()
    operator, samples, _ = load_dataset(Path(args.dataset))
    model = FrozenLinearReducedMap.load(Path(args.checkpoint), expected_operator_fingerprint=operator.fingerprint)
    selected = (samples["split"].astype(str) == "validation") & (samples["sample_kind"].astype(str) == "ilu_residual")
    rhs = samples["rhs"][selected]
    fused = FusedLinearReducedAction(operator, model)
    prediction, ratios = fused.predict_and_audit_many(rhs)
    independent = np.stack([model.predict(row) for row in rhs])
    batch_error = float(np.linalg.norm(prediction - independent) / max(np.linalg.norm(independent), 1e-300))
    rng = np.random.default_rng(20260717)
    x, y = rhs[rng.integers(len(rhs), size=2)]
    alpha, beta = .37-.19j, -.23+.41j
    linearity = float(np.linalg.norm(model.predict(alpha*x+beta*y) - alpha*model.predict(x)-beta*model.predict(y)) / max(np.linalg.norm(model.predict(alpha*x+beta*y)), 1e-300))
    determinism = float(np.linalg.norm(model.predict(x)-model.predict(x)) / max(np.linalg.norm(model.predict(x)), 1e-300))
    timings: list[float] = []
    for index in range(args.repeats):
        batch = rhs[index % len(rhs):(index % len(rhs))+1]
        started = time.perf_counter()
        fused.predict_and_audit_many(batch)
        timings.append(time.perf_counter()-started)
    matrix = sp.csr_matrix((operator.values, operator.indices, operator.indptr), shape=operator.shape).tocsc()
    ilu_started = time.perf_counter()
    ilu = spla.spilu(matrix, fill_factor=1.0, drop_tol=0.0, permc_spec="NATURAL")
    ilu_setup = time.perf_counter()-ilu_started
    ilu_timings = []
    for index in range(args.repeats):
        started = time.perf_counter()
        ilu.solve(rhs[index % len(rhs)])
        ilu_timings.append(time.perf_counter() - started)
    timing = _stats(timings)
    reference_mean = 111.55923823 / 5082.0
    task001_p95 = None
    if args.task001_checkpoint:
        legacy = FrozenNumpyMlp.load(
            Path(args.task001_checkpoint),
            expected_operator_fingerprint=operator.fingerprint,
        )
        legacy_timings = []
        for index in range(args.repeats):
            sample = rhs[index % len(rhs)]
            started = time.perf_counter()
            legacy_prediction = legacy.predict(sample)
            operator.action(legacy_prediction)
            legacy_timings.append(time.perf_counter() - started)
        task001_p95 = _stats(legacy_timings)["p95_s"]
    result = {
        "identity": "para091_linear_reduced_local_gate",
        "sample_count": int(len(rhs)),
        "rho_median": float(np.median(ratios)), "rho_p95": float(np.quantile(ratios,.95)),
        "linearity_relative_error": linearity, "determinism_relative_error": determinism,
        "batch_independent_relative_error": batch_error, "all_finite": bool(np.all(np.isfinite(prediction))),
        "model_storage_bytes": model.storage_bytes,
        "inference_plus_fused_audit": timing,
        "task001_inference_plus_audit_mean_s": reference_mean,
        "mean_ratio_to_task001": timing["mean_s"]/reference_mean,
        "task001_measured_p95_s": task001_p95,
        "p95_ratio_to_task001": (
            timing["p95_s"] / task001_p95 if task001_p95 is not None else None
        ),
        "ilu_local_solve": {**_stats(ilu_timings), "setup_s": ilu_setup},
    }
    result["local_gate_pass"] = bool(linearity <= 1e-11 and determinism <= 1e-13 and batch_error <= 1e-12 and np.median(ratios) <= .60 and np.quantile(ratios,.95) <= .85 and result["mean_ratio_to_task001"] <= .25 and (result["p95_ratio_to_task001"] is None or result["p95_ratio_to_task001"] <= .35))
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
