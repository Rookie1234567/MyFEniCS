from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

import numpy as np

from benchmarks.neural_pc.data_contract import load_operator
from src.solvers.batched_reduced_smoother import FrozenLinearReducedMap
from src.solvers.local_slab_solver import ScipyCsrAction


SCHEMA = "myfenics.task005.p2_linear_screen.v1"
TINY = np.finfo(float).tiny


def _stats(values: np.ndarray) -> dict[str, float]:
    samples = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(np.mean(samples)),
        "median": float(np.median(samples)),
        "p95": float(np.quantile(samples, 0.95)),
        "max": float(np.max(samples)),
    }


def _load_dataset(directory: Path) -> tuple[Any, dict[str, np.ndarray]]:
    operator = load_operator(directory)
    manifest = json.loads((directory / "dataset.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "myfenics.lu_teacher_raw_local_inverse.dataset.v1":
        raise ValueError("Task005 screen requires the raw-RHS LU-teacher schema")
    if manifest.get("operator_fingerprint") != operator.fingerprint:
        raise ValueError("Task005 dataset/operator fingerprint mismatch")
    with np.load(directory / "samples.npz", allow_pickle=False) as payload:
        samples = {name: payload[name] for name in payload.files}
    if set(samples) != {"rhs", "target", "split", "capture_id", "apply_index"}:
        raise ValueError("Task005 dataset payload has unexpected fields")
    return operator, samples


def _normalized(
    rhs: np.ndarray, target: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    scale = np.maximum(np.linalg.norm(rhs, axis=1), TINY)
    return rhs / scale[:, None], target / scale[:, None]


def _structured_synthetic(
    operator: Any,
    real_target: np.ndarray,
    *,
    count: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    rng = np.random.default_rng(seed)
    size = operator.shape[0]
    coordinate = np.linspace(0.0, 1.0, size, endpoint=False)
    errors = np.empty((count, size), dtype=np.complex128)
    family_counts: dict[str, int] = {}
    families = (
        "smooth_low_frequency",
        "interface_localized",
        "boundary_localized",
        "high_frequency_randomized",
        "real_error_pod_combination",
    )
    normalized_real = real_target / np.maximum(
        np.linalg.norm(real_target, axis=1), TINY
    )[:, None]
    amplitude_scales = (1.0e-2, 1.0e-1, 1.0, 1.0e1)
    for index in range(count):
        family = families[index % len(families)]
        family_counts[family] = family_counts.get(family, 0) + 1
        phase = np.exp(1j * rng.uniform(-np.pi, np.pi))
        if family == "smooth_low_frequency":
            wave = 1 + index % 6
            error = np.sin(np.pi * wave * coordinate) + 0.5j * np.cos(
                np.pi * (wave + 1) * coordinate
            )
        elif family == "interface_localized":
            center = (1.0 / 3.0, 0.5, 2.0 / 3.0)[index % 3]
            width = (0.018, 0.035, 0.060)[index % 3]
            envelope = np.exp(-0.5 * ((coordinate - center) / width) ** 2)
            error = envelope * np.exp(2j * np.pi * (1 + index % 9) * coordinate)
        elif family == "boundary_localized":
            center = 0.0 if index % 2 == 0 else 1.0
            width = (0.012, 0.025, 0.050)[index % 3]
            error = np.exp(-0.5 * ((coordinate - center) / width) ** 2) * phase
        elif family == "high_frequency_randomized":
            carrier = np.exp(2j * np.pi * (16 + index % 48) * coordinate)
            blocks = rng.standard_normal(32) + 1j * rng.standard_normal(32)
            envelope = np.repeat(blocks, int(np.ceil(size / 32)))[:size]
            error = carrier * envelope
        else:
            selected = rng.choice(len(normalized_real), size=4, replace=False)
            weights = rng.standard_normal(4) + 1j * rng.standard_normal(4)
            error = weights @ normalized_real[selected]
        error /= max(float(np.linalg.norm(error)), TINY)
        errors[index] = (
            amplitude_scales[(index // len(families)) % len(amplitude_scales)]
            * phase
            * error
        )
    rhs = ScipyCsrAction(operator).action_many(errors)
    return rhs, errors, family_counts


def _pod_bases(
    rhs: np.ndarray,
    target: np.ndarray,
    *,
    rank: int,
    device_name: str,
) -> tuple[np.ndarray, np.ndarray, dict[str, float]]:
    import torch

    device = torch.device(device_name)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA POD construction requested but unavailable")
    started = time.perf_counter()
    x = torch.as_tensor(rhs.T, dtype=torch.complex64, device=device)
    y = torch.as_tensor(target.T, dtype=torch.complex64, device=device)
    ux, sx, _ = torch.linalg.svd(x, full_matrices=False)
    uy, sy, _ = torch.linalg.svd(y, full_matrices=False)
    input_basis = ux[:, :rank].cpu().numpy().astype(np.complex128)
    output_basis = uy[:, :rank].cpu().numpy().astype(np.complex128)
    metrics = {
        "construction_s": time.perf_counter() - started,
        "input_energy": float(
            (torch.sum(sx[:rank].square()) / torch.sum(sx.square())).item()
        ),
        "output_energy": float(
            (torch.sum(sy[:rank].square()) / torch.sum(sy.square())).item()
        ),
    }
    return input_basis, output_basis, metrics


def _fit(
    input_basis: np.ndarray,
    output_basis: np.ndarray,
    rhs: np.ndarray,
    target: np.ndarray,
    *,
    ridge: float,
    fingerprint: str,
) -> FrozenLinearReducedMap:
    coordinates = rhs @ input_basis.conj()
    targets = target @ output_basis.conj()
    gram = coordinates.conj().T @ coordinates
    gram += ridge * np.eye(gram.shape[0], dtype=np.complex128)
    reduced_map = np.linalg.solve(gram, coordinates.conj().T @ targets).T
    return FrozenLinearReducedMap(
        input_basis, reduced_map, output_basis, fingerprint
    )


def _quality(
    operator: Any,
    model: FrozenLinearReducedMap,
    rhs: np.ndarray,
    target: np.ndarray,
    ilu_rho: np.ndarray,
    *,
    seed: int,
) -> dict[str, Any]:
    action = ScipyCsrAction(operator)
    prediction = model.predict_many(rhs)
    residual = rhs - action.action_many(prediction)
    rho = np.linalg.norm(residual, axis=1) / np.maximum(
        np.linalg.norm(rhs, axis=1), TINY
    )
    correction_error = np.linalg.norm(prediction - target, axis=1) / np.maximum(
        np.linalg.norm(target, axis=1), TINY
    )
    rng = np.random.default_rng(seed)
    left, right = rhs[rng.choice(len(rhs), size=2, replace=False)]
    alpha, beta = 0.37 - 0.19j, -0.23 + 0.41j
    combined = model.predict(alpha * left + beta * right)
    linearity = np.linalg.norm(
        combined - alpha * model.predict(left) - beta * model.predict(right)
    ) / max(float(np.linalg.norm(combined)), TINY)
    independent = np.stack([model.predict(row) for row in rhs[:8]])
    batched = model.predict_many(rhs[:8])
    batch_error = np.linalg.norm(batched - independent) / max(
        float(np.linalg.norm(independent)), TINY
    )
    repeated = model.predict(left)
    determinism = np.linalg.norm(repeated - model.predict(left)) / max(
        float(np.linalg.norm(repeated)), TINY
    )
    learned_stats = _stats(rho)
    ilu_stats = _stats(ilu_rho)
    return {
        "all_finite": bool(np.all(np.isfinite(prediction))),
        "rho": learned_stats,
        "ilu_rho": ilu_stats,
        "median_ratio_to_ilu": learned_stats["median"] / ilu_stats["median"],
        "p95_ratio_to_ilu": learned_stats["p95"] / ilu_stats["p95"],
        "correction_error": _stats(correction_error),
        "linearity_relative_error": float(linearity),
        "determinism_relative_error": float(determinism),
        "batch_independent_relative_error": float(batch_error),
        "catastrophic_count": int(np.count_nonzero(rho >= 2.0)),
        "admissible": bool(
            np.all(np.isfinite(prediction))
            and linearity <= 1.0e-11
            and determinism <= 1.0e-13
            and batch_error <= 1.0e-12
            and learned_stats["median"] <= ilu_stats["median"]
            and learned_stats["p95"] <= 1.05 * ilu_stats["p95"]
            and learned_stats["p95"] < 0.95
            and np.all(rho < 2.0)
        ),
    }


def _runtime(
    model: FrozenLinearReducedMap, rhs: np.ndarray, *, repeats: int
) -> dict[str, Any]:
    sample = rhs[:1]
    model.predict_many(sample)
    elapsed = np.empty(repeats, dtype=np.float64)
    for index in range(repeats):
        started = time.perf_counter()
        model.predict_many(rhs[index % len(rhs) : index % len(rhs) + 1])
        elapsed[index] = time.perf_counter() - started
    return {"numpy_cpu_independent_s": _stats(elapsed)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--ilu-root", required=True)
    parser.add_argument("--candidate-pool", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--ridge", type=float, default=1.0e-10)
    parser.add_argument("--runtime-repeats", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260718)
    args = parser.parse_args()
    pool = json.loads(Path(args.candidate_pool).read_text(encoding="utf-8"))
    candidates = [row for row in pool["candidates"] if row["lane"] == "A"]
    maximum_rank = max(int(row["rank"]) for row in candidates)
    output_root = Path(args.output_root)
    rows: list[dict[str, Any]] = []
    for slab in pool["representative_slabs"]:
        dataset_dir = Path(args.dataset_root) / f"slab_{slab:03d}"
        operator, samples = _load_dataset(dataset_dir)
        split = samples["split"].astype(str)
        train_rhs = samples["rhs"][split == "train"]
        train_target = samples["target"][split == "train"]
        holdout_rhs = samples["rhs"][split == "holdout"]
        holdout_target = samples["target"][split == "holdout"]
        train_rhs, train_target = _normalized(train_rhs, train_target)
        synthetic_rhs, synthetic_target, family_counts = _structured_synthetic(
            operator,
            train_target,
            count=int(pool["synthetic_samples_per_slab"]),
            seed=args.seed + slab,
        )
        synthetic_rhs, synthetic_target = _normalized(
            synthetic_rhs, synthetic_target
        )
        recipes = {
            "D0": (train_rhs, train_target),
            "D1": (
                np.concatenate((train_rhs, synthetic_rhs)),
                np.concatenate((train_target, synthetic_target)),
            ),
        }
        holdout_rhs_normalized, holdout_target_normalized = _normalized(
            holdout_rhs, holdout_target
        )
        with np.load(
            Path(args.ilu_root) / f"slab_{slab:03d}" / "holdout.npz",
            allow_pickle=False,
        ) as payload:
            ilu_rho = np.asarray(payload["rho"], dtype=np.float64)
        bases: dict[str, tuple[np.ndarray, np.ndarray, dict[str, float]]] = {}
        for recipe in sorted({row["recipe"] for row in candidates}):
            bases[recipe] = _pod_bases(
                *recipes[recipe], rank=maximum_rank, device_name=args.device
            )
        for candidate in candidates:
            rank = int(candidate["rank"])
            recipe = str(candidate["recipe"])
            input_basis, output_basis, pod = bases[recipe]
            fit_started = time.perf_counter()
            model = _fit(
                input_basis[:, :rank],
                output_basis[:, :rank],
                *recipes[recipe],
                ridge=args.ridge,
                fingerprint=operator.fingerprint,
            )
            fit_s = time.perf_counter() - fit_started
            result = {
                "schema": SCHEMA,
                "candidate": candidate,
                "slab": slab,
                "operator_fingerprint": operator.fingerprint,
                "training_samples": int(recipes[recipe][0].shape[0]),
                "real_training_samples": 1024,
                "synthetic_training_samples": 0 if recipe == "D0" else 256,
                "synthetic_family_counts": (
                    {} if recipe == "D0" else family_counts
                ),
                "pod": pod,
                "fit_s": fit_s,
                "model_storage_bytes": model.storage_bytes,
                "quality": _quality(
                    operator,
                    model,
                    holdout_rhs_normalized,
                    holdout_target_normalized,
                    ilu_rho,
                    seed=args.seed + slab,
                ),
                "runtime": _runtime(
                    model,
                    holdout_rhs_normalized,
                    repeats=args.runtime_repeats,
                ),
            }
            target = output_root / candidate["id"] / f"slab_{slab:03d}"
            model.save(
                target,
                task="PARA-Task005",
                candidate=candidate,
                training_samples=result["training_samples"],
                construction_device=args.device,
            )
            (target / "screen.json").write_text(
                json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
            )
            rows.append(result)
            print(
                f"{candidate['id']} slab={slab}: "
                f"median_ratio={result['quality']['median_ratio_to_ilu']:.3f}, "
                f"p95_ratio={result['quality']['p95_ratio_to_ilu']:.3f}, "
                f"admissible={result['quality']['admissible']}",
                flush=True,
            )
    summary = {
        "schema": "myfenics.task005.p2_linear_screen.summary.v1",
        "candidate_pool_schema": pool["schema"],
        "representative_slabs": pool["representative_slabs"],
        "rows": rows,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
