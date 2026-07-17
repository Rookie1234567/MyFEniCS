from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any, Callable

import numpy as np

from benchmarks.neural_pc.screen_task005_linear import _normalized, _stats
from benchmarks.neural_pc.screen_task005_nonlinear import (
    _activation,
    _build_mlp,
)
from src.solvers.batched_reduced_smoother import FrozenLinearReducedMap


SCHEMA = "myfenics.task005.p2_owner_batch_runtime.v1"


def _torch():
    import torch

    return torch


def _load_holdout(dataset_root: Path, slabs: list[int]) -> list[np.ndarray]:
    rows = []
    for slab in slabs:
        with np.load(
            dataset_root / f"slab_{slab:03d}" / "samples.npz",
            allow_pickle=False,
        ) as payload:
            selected = payload["split"].astype(str) == "holdout"
            rhs, _target = _normalized(
                payload["rhs"][selected], payload["target"][selected]
            )
        rows.append(rhs)
    return rows


def _time(
    action: Callable[[int], list[np.ndarray]],
    *,
    repeats: int,
) -> tuple[dict[str, float], list[np.ndarray]]:
    for index in range(3):
        output = action(index)
    elapsed = np.empty(repeats, dtype=np.float64)
    for index in range(repeats):
        started = time.perf_counter()
        output = action(index)
        elapsed[index] = time.perf_counter() - started
    return _stats(elapsed), output


def _linear_numpy(
    models: list[FrozenLinearReducedMap],
    rhs: list[np.ndarray],
    *,
    grouped: bool,
) -> Callable[[int], list[np.ndarray]]:
    maps = np.stack([model.reduced_map for model in models])

    def action(index: int) -> list[np.ndarray]:
        samples = [
            values[index % len(values) : index % len(values) + 1]
            for values in rhs
        ]
        if not grouped:
            return [
                model.predict_many(sample)
                for model, sample in zip(models, samples, strict=True)
            ]
        coordinates = np.stack(
            [
                sample @ model.input_basis.conj()
                for model, sample in zip(models, samples, strict=True)
            ]
        )
        reduced = np.matmul(coordinates, maps.transpose(0, 2, 1))
        return [
            reduced[row] @ models[row].output_basis.T
            for row in range(len(models))
        ]

    return action


def _linear_torch(
    models: list[FrozenLinearReducedMap],
    rhs: list[np.ndarray],
    *,
    device_name: str,
    grouped: bool,
) -> Callable[[int], list[np.ndarray]]:
    torch = _torch()
    device = torch.device(device_name)
    sources = [
        torch.as_tensor(values, dtype=torch.complex128, device=device)
        for values in rhs
    ]
    inputs = [
        torch.as_tensor(
            model.input_basis, dtype=torch.complex128, device=device
        )
        for model in models
    ]
    outputs = [
        torch.as_tensor(
            model.output_basis, dtype=torch.complex128, device=device
        )
        for model in models
    ]
    maps = torch.stack(
        [
            torch.as_tensor(
                model.reduced_map, dtype=torch.complex128, device=device
            )
            for model in models
        ]
    )

    def action(index: int) -> list[np.ndarray]:
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        with torch.no_grad():
            coordinates = [
                source[index % len(source) : index % len(source) + 1]
                @ basis.conj()
                for source, basis in zip(sources, inputs, strict=True)
            ]
            if grouped:
                packed = torch.stack(coordinates)
                reduced = torch.matmul(packed, maps.transpose(1, 2))
            else:
                reduced = [
                    coordinate @ maps[row].T
                    for row, coordinate in enumerate(coordinates)
                ]
            decoded = [
                reduced[row] @ outputs[row].T for row in range(len(outputs))
            ]
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        return [value.detach().cpu().numpy() for value in decoded]

    return action


def _load_nonlinear_models(
    root: Path,
    candidate: dict[str, Any],
    slabs: list[int],
) -> list[Any]:
    torch = _torch()
    models = []
    for slab in slabs:
        model = _build_mlp(
            int(candidate["rank"]),
            int(candidate["hidden"]),
            int(candidate["depth"]),
            str(candidate["activation"]),
        )
        state = torch.load(
            root / candidate["id"] / f"slab_{slab:03d}" / "state.pt",
            map_location="cpu",
            weights_only=True,
        )
        model.load_state_dict(state)
        models.append(model.eval())
    return models


def _nonlinear_torch(
    models: list[Any],
    linear: list[FrozenLinearReducedMap],
    rhs: list[np.ndarray],
    candidate: dict[str, Any],
    *,
    device_name: str,
    grouped: bool,
) -> Callable[[int], list[np.ndarray]]:
    torch = _torch()
    device = torch.device(device_name)
    models = [model.to(device) for model in models]
    sources = [
        torch.as_tensor(values, dtype=torch.complex64, device=device)
        for values in rhs
    ]
    inputs = [
        torch.as_tensor(
            model.input_basis, dtype=torch.complex64, device=device
        )
        for model in linear
    ]
    outputs = [
        torch.as_tensor(
            model.output_basis, dtype=torch.complex64, device=device
        )
        for model in linear
    ]
    base_maps = torch.stack(
        [
            torch.as_tensor(
                model.reduced_map, dtype=torch.complex64, device=device
            )
            for model in linear
        ]
    )
    linear_layers = [
        [layer for layer in model if isinstance(layer, torch.nn.Linear)]
        for model in models
    ]
    grouped_weights = [
        torch.stack([layers[index].weight for layers in linear_layers])
        for index in range(len(linear_layers[0]))
    ]
    grouped_biases = [
        torch.stack([layers[index].bias for layers in linear_layers])
        for index in range(len(linear_layers[0]))
    ]

    def run_group(packed):
        values = packed
        for index, (weights, biases) in enumerate(
            zip(grouped_weights, grouped_biases, strict=True)
        ):
            values = torch.bmm(weights, values.unsqueeze(-1)).squeeze(-1)
            values = values + biases
            if index < len(grouped_weights) - 1:
                values = _activation(str(candidate["activation"]))(values)
        return values

    def action(index: int) -> list[np.ndarray]:
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        with torch.no_grad():
            coordinates = [
                source[index % len(source) : index % len(source) + 1]
                @ basis.conj()
                for source, basis in zip(sources, inputs, strict=True)
            ]
            packed = [
                torch.cat((coordinate.real, coordinate.imag), dim=1)
                for coordinate in coordinates
            ]
            if grouped:
                prediction = run_group(torch.cat(packed, dim=0))
            else:
                prediction = torch.cat(
                    [
                        model(value)
                        for model, value in zip(models, packed, strict=True)
                    ],
                    dim=0,
                )
            if candidate["map"] == "skip":
                coordinate_stack = torch.cat(coordinates, dim=0).unsqueeze(1)
                base = torch.bmm(
                    coordinate_stack, base_maps.transpose(1, 2)
                ).squeeze(1)
                prediction = prediction + torch.cat(
                    (base.real, base.imag), dim=1
                )
            rank = int(candidate["rank"])
            complex_prediction = torch.complex(
                prediction[:, :rank], prediction[:, rank:]
            )
            decoded = [
                complex_prediction[row : row + 1] @ outputs[row].T
                for row in range(len(outputs))
            ]
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        return [value.detach().cpu().numpy() for value in decoded]

    return action


def _relative_error(
    reference: list[np.ndarray], candidate: list[np.ndarray]
) -> float:
    numerator = np.sqrt(
        sum(
            np.linalg.norm(left - right) ** 2
            for left, right in zip(reference, candidate, strict=True)
        )
    )
    denominator = np.sqrt(sum(np.linalg.norm(value) ** 2 for value in reference))
    return float(numerator / max(float(denominator), np.finfo(float).tiny))


def _benchmark_pair(
    independent: Callable[[int], list[np.ndarray]],
    grouped: Callable[[int], list[np.ndarray]],
    *,
    repeats: int,
    tolerance: float,
) -> dict[str, Any]:
    independent_stats, reference = _time(independent, repeats=repeats)
    grouped_stats, candidate = _time(grouped, repeats=repeats)
    error = _relative_error(reference, candidate)
    return {
        "independent_four_slab_envelope_s": independent_stats,
        "owner_grouped_four_slab_s": grouped_stats,
        "grouped_vs_independent_relative_error": error,
        "equivalence_tolerance": tolerance,
        "equivalence_pass": bool(error <= tolerance),
        "owner_model_budget_pass": bool(grouped_stats["mean"] <= 0.0072),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--linear-root", required=True)
    parser.add_argument("--nonlinear-root", required=True)
    parser.add_argument("--candidate-pool", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--linear-candidate", default="A_D0_R64")
    parser.add_argument(
        "--nonlinear-candidate", default="B_D0_R64_W128_D3_GELU_SKIP"
    )
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--repeats", type=int, default=100)
    args = parser.parse_args()
    pool = json.loads(Path(args.candidate_pool).read_text(encoding="utf-8"))
    slabs = list(pool["representative_slabs"])
    candidates = {row["id"]: row for row in pool["candidates"]}
    linear_candidate = candidates[args.linear_candidate]
    nonlinear_candidate = candidates[args.nonlinear_candidate]
    rhs = _load_holdout(Path(args.dataset_root), slabs)
    linear_models = [
        FrozenLinearReducedMap.load(
            Path(args.linear_root)
            / linear_candidate["id"]
            / f"slab_{slab:03d}"
        )
        for slab in slabs
    ]
    nonlinear_linear_models = [
        FrozenLinearReducedMap.load(
            Path(args.linear_root)
            / f"A_D0_R{nonlinear_candidate['rank']}"
            / f"slab_{slab:03d}"
        )
        for slab in slabs
    ]
    nonlinear_models = _load_nonlinear_models(
        Path(args.nonlinear_root), nonlinear_candidate, slabs
    )
    rows = {
        "linear_numpy_cpu": _benchmark_pair(
            _linear_numpy(linear_models, rhs, grouped=False),
            _linear_numpy(linear_models, rhs, grouped=True),
            repeats=args.repeats,
            tolerance=1.0e-12,
        ),
        "linear_pytorch_cpu": _benchmark_pair(
            _linear_torch(
                linear_models, rhs, device_name="cpu", grouped=False
            ),
            _linear_torch(
                linear_models, rhs, device_name="cpu", grouped=True
            ),
            repeats=args.repeats,
            tolerance=1.0e-12,
        ),
        "linear_pytorch_cuda": _benchmark_pair(
            _linear_torch(
                linear_models,
                rhs,
                device_name=args.device,
                grouped=False,
            ),
            _linear_torch(
                linear_models,
                rhs,
                device_name=args.device,
                grouped=True,
            ),
            repeats=args.repeats,
            tolerance=1.0e-12,
        ),
        "nonlinear_pytorch_cpu": _benchmark_pair(
            _nonlinear_torch(
                nonlinear_models,
                nonlinear_linear_models,
                rhs,
                nonlinear_candidate,
                device_name="cpu",
                grouped=False,
            ),
            _nonlinear_torch(
                nonlinear_models,
                nonlinear_linear_models,
                rhs,
                nonlinear_candidate,
                device_name="cpu",
                grouped=True,
            ),
            repeats=args.repeats,
            tolerance=2.0e-6,
        ),
        "nonlinear_pytorch_cuda": _benchmark_pair(
            _nonlinear_torch(
                nonlinear_models,
                nonlinear_linear_models,
                rhs,
                nonlinear_candidate,
                device_name=args.device,
                grouped=False,
            ),
            _nonlinear_torch(
                nonlinear_models,
                nonlinear_linear_models,
                rhs,
                nonlinear_candidate,
                device_name=args.device,
                grouped=True,
            ),
            repeats=args.repeats,
            tolerance=2.0e-6,
        ),
    }
    result = {
        "schema": SCHEMA,
        "slabs": slabs,
        "linear_candidate": linear_candidate,
        "nonlinear_candidate": nonlinear_candidate,
        "persistent_inputs_and_models": True,
        "complete_global_vector_transferred": False,
        "rows": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
