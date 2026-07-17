from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np

from benchmarks.neural_pc.data_contract import load_dataset
from src.solvers.neural_local_pc import CHECKPOINT_SCHEMA, pack_complex, sha256_file


def _packed_rows(values: np.ndarray) -> np.ndarray:
    return np.stack([pack_complex(row) for row in values], axis=0).astype(np.float32)


def _require_torch():
    try:
        import torch
    except ImportError as error:
        raise RuntimeError("GPU training requires PyTorch in the WSL environment") from error
    return torch


def train(args: argparse.Namespace) -> dict[str, object]:
    torch = _require_torch()
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA training was requested but torch.cuda.is_available() is false")
    if args.device == "cpu" and not args.allow_cpu_training:
        raise RuntimeError("CPU training is disabled; pass --allow-cpu-training only for diagnostics")
    device = torch.device(args.device)
    operator, samples, dataset_manifest = load_dataset(Path(args.dataset))
    rhs_numpy = _packed_rows(samples["rhs"])
    target_numpy = _packed_rows(samples["target"])
    # Match FrozenNumpyMlp.predict exactly.  The local inverse is homogeneous,
    # and real Krylov residual norms span many orders of magnitude.
    rhs_scale = np.maximum(
        np.linalg.norm(rhs_numpy.astype(np.float64), axis=1), np.finfo(float).tiny
    ).astype(np.float32)
    rhs_numpy = rhs_numpy / rhs_scale[:, None]
    target_numpy = target_numpy / rhs_scale[:, None]
    split = samples["split"].astype(str)
    train_indices_numpy = np.flatnonzero(split == "train")
    validation_indices_numpy = np.flatnonzero(split == "validation")
    if not train_indices_numpy.size or not validation_indices_numpy.size:
        raise ValueError("dataset requires non-empty train and validation splits")

    if device.type == "cuda":
        torch.cuda.set_device(device)
        torch.cuda.reset_peak_memory_stats(device)
    rhs = torch.as_tensor(rhs_numpy, device=device)
    target = torch.as_tensor(target_numpy, device=device)
    train_indices = torch.as_tensor(train_indices_numpy, dtype=torch.long, device=device)
    validation_indices = torch.as_tensor(
        validation_indices_numpy, dtype=torch.long, device=device
    )
    torch.manual_seed(args.seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(args.seed)

    # POD construction is part of the GPU path; only frozen arrays return to CPU.
    _u, _s, vh = torch.linalg.svd(target.index_select(0, train_indices), full_matrices=False)
    output_rank = min(args.pod_rank, int(vh.shape[0]))
    output_energy_fraction = float(
        (torch.sum(_s[:output_rank].square()) / torch.sum(_s.square())).item()
    )
    output_basis = vh[:output_rank].T.contiguous()
    _u, _s, vh = torch.linalg.svd(rhs.index_select(0, train_indices), full_matrices=False)
    input_rank = min(args.pod_rank, int(vh.shape[0]))
    input_energy_fraction = float(
        (torch.sum(_s[:input_rank].square()) / torch.sum(_s.square())).item()
    )
    input_basis = vh[:input_rank].T.contiguous()
    inputs = rhs @ input_basis

    model = torch.nn.Sequential(
        torch.nn.Linear(input_rank, args.hidden_width),
        torch.nn.Tanh(),
        torch.nn.Linear(args.hidden_width, output_rank),
    ).to(device)
    optimizer = torch.optim.Adam(
        model.parameters(), lr=args.learning_rate, betas=(args.beta1, args.beta2)
    )
    row_ptr = torch.as_tensor(operator.indptr, dtype=torch.int64, device=device)
    column_indices = torch.as_tensor(operator.indices, dtype=torch.int64, device=device)
    csr_values = torch.as_tensor(operator.values, dtype=torch.complex64, device=device)
    sparse_operator = torch.sparse_csr_tensor(
        row_ptr,
        column_indices,
        csr_values,
        size=operator.shape,
        device=device,
    )

    def loss_for(indices) -> tuple[object, object, object]:
        batch_input = inputs.index_select(0, indices)
        batch_rhs = rhs.index_select(0, indices)
        batch_target = target.index_select(0, indices)
        output_coordinates = model(batch_input)
        predicted = output_coordinates @ output_basis.T
        correction_error = predicted - batch_target
        correction_denominator = torch.sum(batch_target.square(), dim=1) + args.delta
        correction_loss = torch.mean(
            torch.sum(correction_error.square(), dim=1) / correction_denominator
        )
        half = predicted.shape[1] // 2
        predicted_complex = torch.complex(predicted[:, :half], predicted[:, half:])
        rhs_complex = torch.complex(batch_rhs[:, :half], batch_rhs[:, half:])
        action = torch.sparse.mm(sparse_operator, predicted_complex.T).T
        residual = action - rhs_complex
        residual_denominator = torch.sum(torch.abs(rhs_complex).square(), dim=1) + args.delta
        residual_loss = torch.mean(
            torch.sum(torch.abs(residual).square(), dim=1) / residual_denominator
        )
        return (
            correction_loss + args.residual_weight * residual_loss,
            correction_loss,
            residual_loss,
        )

    started = time.perf_counter()
    history: list[dict[str, float | int]] = []
    generator = torch.Generator(device=device).manual_seed(args.seed)
    for epoch in range(1, args.epochs + 1):
        permutation = train_indices[
            torch.randperm(train_indices.numel(), generator=generator, device=device)
        ]
        model.train()
        for first in range(0, permutation.numel(), args.batch_size):
            batch = permutation[first : first + args.batch_size]
            optimizer.zero_grad(set_to_none=True)
            loss, _correction, _residual = loss_for(batch)
            loss.backward()
            optimizer.step()
        if epoch == 1 or epoch % args.report_stride == 0 or epoch == args.epochs:
            model.eval()
            with torch.no_grad():
                train_loss, train_correction, train_residual = loss_for(train_indices)
                validation_loss, validation_correction, validation_residual = loss_for(
                    validation_indices
                )
            history.append(
                {
                    "epoch": epoch,
                    "train_loss": float(train_loss.item()),
                    "train_correction_loss": float(train_correction.item()),
                    "train_residual_loss": float(train_residual.item()),
                    "validation_loss": float(validation_loss.item()),
                    "validation_correction_loss": float(validation_correction.item()),
                    "validation_residual_loss": float(validation_residual.item()),
                }
            )
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    training_s = time.perf_counter() - started
    layers = [layer for layer in model if isinstance(layer, torch.nn.Linear)]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    weights_path = output / "weights.npz"
    np.savez_compressed(
        weights_path,
        input_basis=input_basis.detach().cpu().numpy().astype(np.float64),
        output_basis=output_basis.detach().cpu().numpy().astype(np.float64),
        weight_1=layers[0].weight.detach().cpu().numpy().astype(np.float64),
        bias_1=layers[0].bias.detach().cpu().numpy().astype(np.float64),
        weight_2=layers[1].weight.detach().cpu().numpy().astype(np.float64),
        bias_2=layers[1].bias.detach().cpu().numpy().astype(np.float64),
    )
    checksum = sha256_file(weights_path)
    gpu = None
    if device.type == "cuda":
        gpu = {
            "device": str(device),
            "name": torch.cuda.get_device_name(device),
            "device_count": torch.cuda.device_count(),
            "peak_allocated_bytes": int(torch.cuda.max_memory_allocated(device)),
            "peak_reserved_bytes": int(torch.cuda.max_memory_reserved(device)),
        }
    manifest = {
        "schema": CHECKPOINT_SCHEMA,
        "backend": "pytorch_gpu_pod_mlp",
        "runtime_export": "numpy_cpu_or_gpu_batch_adapter",
        "offline_training_only": True,
        "operator_fingerprint": operator.fingerprint,
        "dataset_schema": dataset_manifest["schema"],
        "dataset_generation_seed": dataset_manifest.get("generation_seed"),
        "weights_sha256": checksum,
        "seed": args.seed,
        "input_pod_rank": input_rank,
        "output_pod_rank": output_rank,
        "input_pod_energy_fraction": input_energy_fraction,
        "output_pod_energy_fraction": output_energy_fraction,
        "hidden_width": args.hidden_width,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "residual_weight": args.residual_weight,
        "homogeneous_rhs_normalization": True,
        "training_s": training_s,
        "torch_version": torch.__version__,
        "gpu": gpu,
        "history": history,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return {
        "output": str(output),
        "weights_sha256": checksum,
        "training_s": training_s,
        "device": str(device),
        "gpu": gpu,
        "final": history[-1],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="GPU-train an offline POD-MLP local correction")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--allow-cpu-training", action="store_true")
    parser.add_argument("--pod-rank", type=int, default=128)
    parser.add_argument("--hidden-width", type=int, default=256)
    parser.add_argument("--epochs", type=int, default=500)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--learning-rate", type=float, default=2.0e-3)
    parser.add_argument("--residual-weight", type=float, default=1.0)
    parser.add_argument("--delta", type=float, default=1.0e-12)
    parser.add_argument("--beta1", type=float, default=0.9)
    parser.add_argument("--beta2", type=float, default=0.999)
    parser.add_argument("--report-stride", type=int, default=25)
    parser.add_argument("--seed", type=int, default=20260717)
    args = parser.parse_args()
    print(json.dumps(train(args), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
