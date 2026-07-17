from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
from scipy.special import erf

from benchmarks.neural_pc.screen_task005_linear import (
    TINY,
    _load_dataset,
    _normalized,
    _stats,
    _structured_synthetic,
)
from src.solvers.batched_reduced_smoother import FrozenLinearReducedMap
from src.solvers.local_slab_solver import ScipyCsrAction


SCHEMA = "myfenics.task005.p2_nonlinear_screen.v1"


def _torch():
    import torch

    return torch


def _activation(name: str):
    torch = _torch()
    return {
        "tanh": torch.nn.Tanh,
        "relu": torch.nn.ReLU,
        "gelu": torch.nn.GELU,
    }[name]()


def _build_mlp(size: int, hidden: int, depth: int, activation: str):
    torch = _torch()
    layers: list[Any] = []
    dimensions = [2 * size] + [hidden] * (depth - 1) + [2 * size]
    for index, (source, target) in enumerate(
        zip(dimensions[:-1], dimensions[1:], strict=True)
    ):
        layers.append(torch.nn.Linear(source, target))
        if index < len(dimensions) - 2:
            layers.append(_activation(activation))
    return torch.nn.Sequential(*layers)


def _pack_torch(values):
    torch = _torch()
    return torch.cat((values.real, values.imag), dim=1)


def _unpack_torch(values):
    torch = _torch()
    half = values.shape[1] // 2
    return torch.complex(values[:, :half], values[:, half:])


def _predict_coordinates(model, packed_input, base_map, map_kind: str):
    output = model(packed_input)
    if map_kind == "skip":
        input_complex = _unpack_torch(packed_input)
        base = input_complex @ base_map.T
        output = output + _pack_torch(base)
    return output


def _train_model(
    candidate: dict[str, Any],
    input_coordinates: np.ndarray,
    target_coordinates: np.ndarray,
    reduced_operator: np.ndarray,
    base_map: np.ndarray,
    *,
    device_name: str,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    residual_weight: float,
    seed: int,
) -> tuple[Any, dict[str, Any]]:
    torch = _torch()
    device = torch.device(device_name)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    model = _build_mlp(
        int(candidate["rank"]),
        int(candidate["hidden"]),
        int(candidate["depth"]),
        str(candidate["activation"]),
    ).to(device)
    x = torch.as_tensor(input_coordinates, dtype=torch.complex64, device=device)
    y = torch.as_tensor(target_coordinates, dtype=torch.complex64, device=device)
    packed_x = _pack_torch(x)
    packed_y = _pack_torch(y)
    operator = torch.as_tensor(
        reduced_operator, dtype=torch.complex64, device=device
    )
    base = torch.as_tensor(base_map, dtype=torch.complex64, device=device)
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    generator = torch.Generator(device=device).manual_seed(seed)
    history: list[dict[str, float | int]] = []
    started = time.perf_counter()
    for epoch in range(1, epochs + 1):
        permutation = torch.randperm(
            len(packed_x), generator=generator, device=device
        )
        model.train()
        for first in range(0, len(permutation), batch_size):
            selected = permutation[first : first + batch_size]
            batch_x = packed_x.index_select(0, selected)
            batch_y = packed_y.index_select(0, selected)
            optimizer.zero_grad(set_to_none=True)
            predicted_packed = _predict_coordinates(
                model, batch_x, base, str(candidate["map"])
            )
            predicted = _unpack_torch(predicted_packed)
            correction = torch.sum(
                torch.abs(predicted - _unpack_torch(batch_y)).square(), dim=1
            ) / torch.clamp(
                torch.sum(torch.abs(_unpack_torch(batch_y)).square(), dim=1),
                min=1.0e-12,
            )
            projected_action = predicted @ operator.T
            projected_residual = torch.sum(
                torch.abs(projected_action - _unpack_torch(batch_x)).square(),
                dim=1,
            ) / torch.clamp(
                torch.sum(torch.abs(_unpack_torch(batch_x)).square(), dim=1),
                min=1.0e-12,
            )
            loss = torch.mean(correction) + residual_weight * torch.mean(
                projected_residual
            )
            loss.backward()
            optimizer.step()
        if epoch in {1, epochs} or epoch % max(epochs // 5, 1) == 0:
            history.append({"epoch": epoch, "loss": float(loss.item())})
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    return model, {
        "training_s": time.perf_counter() - started,
        "history": history,
        "loss_contract": "reduced_correction_plus_projected_equation_residual",
    }


def _numpy_forward(
    model,
    packed_input: np.ndarray,
    *,
    activation: str,
    base: np.ndarray | None,
) -> np.ndarray:
    torch = _torch()
    output = packed_input
    for layer in model:
        if isinstance(layer, torch.nn.Linear):
            output = (
                output @ layer.weight.detach().cpu().numpy().T
                + layer.bias.detach().cpu().numpy()
            )
        elif activation == "tanh":
            output = np.tanh(output)
        elif activation == "relu":
            output = np.maximum(output, 0.0)
        elif activation == "gelu":
            output = 0.5 * output * (1.0 + erf(output / np.sqrt(2.0)))
        else:
            raise ValueError(f"unsupported activation {activation}")
    if base is not None:
        output = output + base
    return output


def _predict_numpy(
    model,
    rhs: np.ndarray,
    input_basis: np.ndarray,
    output_basis: np.ndarray,
    base_map: np.ndarray,
    candidate: dict[str, Any],
) -> np.ndarray:
    coordinates = rhs @ input_basis.conj()
    packed = np.concatenate((coordinates.real, coordinates.imag), axis=1).astype(
        np.float32
    )
    base = None
    if candidate["map"] == "skip":
        base_coordinates = coordinates @ base_map.T
        base = np.concatenate(
            (base_coordinates.real, base_coordinates.imag), axis=1
        ).astype(np.float32)
    output = _numpy_forward(
        model, packed, activation=str(candidate["activation"]), base=base
    )
    rank = int(candidate["rank"])
    output_coordinates = output[:, :rank] + 1j * output[:, rank:]
    return output_coordinates @ output_basis.T


def _quality(
    operator: Any,
    prediction: np.ndarray,
    rhs: np.ndarray,
    target: np.ndarray,
    ilu_rho: np.ndarray,
) -> dict[str, Any]:
    residual = rhs - ScipyCsrAction(operator).action_many(prediction)
    rho = np.linalg.norm(residual, axis=1) / np.maximum(
        np.linalg.norm(rhs, axis=1), TINY
    )
    correction_error = np.linalg.norm(prediction - target, axis=1) / np.maximum(
        np.linalg.norm(target, axis=1), TINY
    )
    learned = _stats(rho)
    ilu = _stats(ilu_rho)
    return {
        "all_finite": bool(np.all(np.isfinite(prediction))),
        "rho": learned,
        "ilu_rho": ilu,
        "median_ratio_to_ilu": learned["median"] / ilu["median"],
        "p95_ratio_to_ilu": learned["p95"] / ilu["p95"],
        "correction_error": _stats(correction_error),
        "catastrophic_count": int(np.count_nonzero(rho >= 2.0)),
        "admissible": bool(
            np.all(np.isfinite(prediction))
            and learned["median"] <= ilu["median"]
            and learned["p95"] <= 1.05 * ilu["p95"]
            and learned["p95"] < 0.95
            and np.all(rho < 2.0)
        ),
    }


def _time_numpy(
    model,
    rhs: np.ndarray,
    input_basis: np.ndarray,
    output_basis: np.ndarray,
    base_map: np.ndarray,
    candidate: dict[str, Any],
    repeats: int,
) -> dict[str, float]:
    elapsed = np.empty(repeats, dtype=np.float64)
    for index in range(repeats):
        sample = rhs[index % len(rhs) : index % len(rhs) + 1]
        started = time.perf_counter()
        _predict_numpy(
            model, sample, input_basis, output_basis, base_map, candidate
        )
        elapsed[index] = time.perf_counter() - started
    return _stats(elapsed)


def _time_torch(
    model,
    rhs: np.ndarray,
    input_basis: np.ndarray,
    output_basis: np.ndarray,
    base_map: np.ndarray,
    candidate: dict[str, Any],
    *,
    device_name: str,
    repeats: int,
) -> dict[str, float]:
    torch = _torch()
    device = torch.device(device_name)
    timed_model = copy.deepcopy(model).to(device).eval()
    source = torch.as_tensor(rhs, dtype=torch.complex64, device=device)
    input_tensor = torch.as_tensor(
        input_basis, dtype=torch.complex64, device=device
    )
    output_tensor = torch.as_tensor(
        output_basis, dtype=torch.complex64, device=device
    )
    base = torch.as_tensor(base_map, dtype=torch.complex64, device=device)
    elapsed = np.empty(repeats, dtype=np.float64)
    with torch.no_grad():
        for index in range(repeats + 3):
            sample = source[index % len(source) : index % len(source) + 1]
            if device.type == "cuda":
                torch.cuda.synchronize(device)
            started = time.perf_counter()
            coordinates = sample @ input_tensor.conj()
            packed = _pack_torch(coordinates)
            predicted = _predict_coordinates(
                timed_model, packed, base, str(candidate["map"])
            )
            decoded = _unpack_torch(predicted) @ output_tensor.T
            if device.type == "cuda":
                torch.cuda.synchronize(device)
            if index >= 3:
                elapsed[index - 3] = time.perf_counter() - started
            if not torch.all(torch.isfinite(decoded.real)):
                raise RuntimeError("non-finite Torch inference")
    return _stats(elapsed)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--ilu-root", required=True)
    parser.add_argument("--linear-root", required=True)
    parser.add_argument("--candidate-pool", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=2.0e-3)
    parser.add_argument("--residual-weight", type=float, default=1.0)
    parser.add_argument("--runtime-repeats", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20260718)
    parser.add_argument("--slabs")
    parser.add_argument("--candidate-ids")
    args = parser.parse_args()
    pool = json.loads(Path(args.candidate_pool).read_text(encoding="utf-8"))
    candidates = [row for row in pool["candidates"] if row["lane"] == "B"]
    if args.candidate_ids:
        selected_ids = set(args.candidate_ids.split(","))
        candidates = [row for row in candidates if row["id"] in selected_ids]
    slabs = list(pool["representative_slabs"])
    if args.slabs:
        slabs = [int(value) for value in args.slabs.split(",")]
    if not candidates or not slabs:
        raise ValueError("Task005 nonlinear screen selection is empty")
    output_root = Path(args.output_root)
    rows: list[dict[str, Any]] = []
    for slab in slabs:
        dataset_dir = Path(args.dataset_root) / f"slab_{slab:03d}"
        operator, samples = _load_dataset(dataset_dir)
        split = samples["split"].astype(str)
        real_rhs, real_target = _normalized(
            samples["rhs"][split == "train"],
            samples["target"][split == "train"],
        )
        holdout_rhs, holdout_target = _normalized(
            samples["rhs"][split == "holdout"],
            samples["target"][split == "holdout"],
        )
        synthetic_rhs, synthetic_target, family_counts = _structured_synthetic(
            operator,
            real_target,
            count=int(pool["synthetic_samples_per_slab"]),
            seed=args.seed + slab,
        )
        synthetic_rhs, synthetic_target = _normalized(
            synthetic_rhs, synthetic_target
        )
        with np.load(
            Path(args.ilu_root) / f"slab_{slab:03d}" / "holdout.npz",
            allow_pickle=False,
        ) as payload:
            ilu_rho = np.asarray(payload["rho"], dtype=np.float64)
        action = ScipyCsrAction(operator)
        for candidate_index, candidate in enumerate(candidates):
            recipe = str(candidate["recipe"])
            rank = int(candidate["rank"])
            linear_id = (
                f"A_D0_R{rank}" if recipe == "D0" else "A_D1_R96"
            )
            linear = FrozenLinearReducedMap.load(
                Path(args.linear_root)
                / linear_id
                / f"slab_{slab:03d}",
                expected_operator_fingerprint=operator.fingerprint,
            )
            input_basis = linear.input_basis[:, :rank]
            output_basis = linear.output_basis[:, :rank]
            base_map = linear.reduced_map[:rank, :rank]
            train_rhs = real_rhs
            train_target = real_target
            if recipe == "D1":
                train_rhs = np.concatenate((train_rhs, synthetic_rhs))
                train_target = np.concatenate((train_target, synthetic_target))
            input_coordinates = train_rhs @ input_basis.conj()
            target_coordinates = train_target @ output_basis.conj()
            reduced_operator = (
                input_basis.conj().T
                @ action.action_many(output_basis.T).T
            )
            model, training = _train_model(
                candidate,
                input_coordinates,
                target_coordinates,
                reduced_operator,
                base_map,
                device_name=args.device,
                epochs=args.epochs,
                batch_size=args.batch_size,
                learning_rate=args.learning_rate,
                residual_weight=args.residual_weight,
                seed=args.seed + 1000 * slab + candidate_index,
            )
            prediction = _predict_numpy(
                model,
                holdout_rhs,
                input_basis,
                output_basis,
                base_map,
                candidate,
            )
            repeated = _predict_numpy(
                model,
                holdout_rhs[:1],
                input_basis,
                output_basis,
                base_map,
                candidate,
            )
            determinism = np.linalg.norm(
                repeated
                - _predict_numpy(
                    model,
                    holdout_rhs[:1],
                    input_basis,
                    output_basis,
                    base_map,
                    candidate,
                )
            ) / max(float(np.linalg.norm(repeated)), TINY)
            parameter_bytes = sum(
                parameter.numel() * parameter.element_size()
                for parameter in model.parameters()
            )
            storage = (
                input_basis.nbytes
                + output_basis.nbytes
                + parameter_bytes
                + (base_map.nbytes if candidate["map"] == "skip" else 0)
            )
            result = {
                "schema": SCHEMA,
                "candidate": candidate,
                "slab": slab,
                "operator_fingerprint": operator.fingerprint,
                "training_samples": int(len(train_rhs)),
                "synthetic_family_counts": (
                    family_counts if recipe == "D1" else {}
                ),
                "training": training,
                "model_storage_bytes": int(storage),
                "determinism_relative_error": float(determinism),
                "quality": _quality(
                    operator,
                    prediction,
                    holdout_rhs,
                    holdout_target,
                    ilu_rho,
                ),
                "runtime": {
                    "numpy_cpu": _time_numpy(
                        model,
                        holdout_rhs,
                        input_basis,
                        output_basis,
                        base_map,
                        candidate,
                        args.runtime_repeats,
                    ),
                    "pytorch_cpu": _time_torch(
                        model,
                        holdout_rhs,
                        input_basis,
                        output_basis,
                        base_map,
                        candidate,
                        device_name="cpu",
                        repeats=args.runtime_repeats,
                    ),
                    "pytorch_cuda": _time_torch(
                        model,
                        holdout_rhs,
                        input_basis,
                        output_basis,
                        base_map,
                        candidate,
                        device_name=args.device,
                        repeats=args.runtime_repeats,
                    ),
                },
            }
            target = output_root / candidate["id"] / f"slab_{slab:03d}"
            target.mkdir(parents=True, exist_ok=True)
            _torch().save(model.state_dict(), target / "state.pt")
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
        "schema": "myfenics.task005.p2_nonlinear_screen.summary.v1",
        "candidate_pool_schema": pool["schema"],
        "representative_slabs": slabs,
        "epochs": args.epochs,
        "rows": rows,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
