from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np

from benchmarks.neural_pc.data_contract import load_dataset
from src.solvers.local_slab_solver import relative_local_residual
from src.solvers.neural_local_pc import FrozenNumpyMlp


def evaluate(args: argparse.Namespace) -> dict[str, object]:
    operator, samples, manifest = load_dataset(Path(args.dataset))
    model = FrozenNumpyMlp.load(
        Path(args.checkpoint), expected_operator_fingerprint=operator.fingerprint
    )
    split = samples["split"].astype(str)
    indices = np.flatnonzero(split == args.split)
    if not indices.size:
        raise ValueError(f"dataset split {args.split!r} is empty")
    ratios: list[float] = []
    correction_errors: list[float] = []
    elapsed: list[float] = []
    deterministic_error = 0.0
    kinds = samples["sample_kind"].astype(str)
    evaluated_kinds: list[str] = []
    for index in indices:
        rhs = samples["rhs"][index]
        target = samples["target"][index]
        started = time.perf_counter()
        prediction = model.predict(rhs)
        elapsed.append(time.perf_counter() - started)
        repeated = model.predict(rhs)
        deterministic_error = max(
            deterministic_error,
            float(np.linalg.norm(prediction - repeated) / max(np.linalg.norm(prediction), 1e-300)),
        )
        ratios.append(relative_local_residual(operator, rhs, prediction))
        correction_errors.append(
            float(np.linalg.norm(prediction - target) / max(np.linalg.norm(target), 1e-300))
        )
        evaluated_kinds.append(kinds[index])
    by_sample_kind = {}
    kind_array = np.asarray(evaluated_kinds)
    ratio_array = np.asarray(ratios)
    error_array = np.asarray(correction_errors)
    for kind in sorted(set(evaluated_kinds)):
        selected = kind_array == kind
        by_sample_kind[kind] = {
            "sample_count": int(np.count_nonzero(selected)),
            "rho_median": float(np.median(ratio_array[selected])),
            "rho_p95": float(np.quantile(ratio_array[selected], 0.95)),
            "correction_error_median": float(np.median(error_array[selected])),
        }
    result = {
        "identity": "local_action_evaluation",
        "qualification": manifest.get("qualification"),
        "split": args.split,
        "sample_count": int(indices.size),
        "rho_median": float(np.median(ratios)),
        "rho_p95": float(np.quantile(ratios, 0.95)),
        "correction_error_median": float(np.median(correction_errors)),
        "mean_inference_s": float(np.mean(elapsed)),
        "p95_inference_s": float(np.quantile(elapsed, 0.95)),
        "determinism_relative_error": deterministic_error,
        "by_sample_kind": by_sample_kind,
        "checkpoint_sha256": model.checkpoint_sha256,
        "local_feasibility_gate": bool(
            np.median(ratios) < 0.5
            and np.quantile(ratios, 0.95) < 0.95
            and deterministic_error <= 1.0e-13
        ),
        "global_acceleration_claim_allowed": False,
    }
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a frozen neural local checkpoint")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--split", default="validation")
    parser.add_argument("--output")
    args = parser.parse_args()
    print(json.dumps(evaluate(args), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
