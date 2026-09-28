"""Task042 isolated CPU FP64 residual MLP; no FE/native imports."""

import hashlib
import math
import os
import time
from pathlib import Path

import numpy as np


def pack(values):
    return np.concatenate([values.real, values.imag], axis=-1).astype(np.float64)


def numpy_prediction(values, weights):
    def gelu(x):
        return (
            0.5
            * x
            * (1.0 + np.vectorize(math.erf, otypes=[np.float64])(x / np.sqrt(2.0)))
        )

    h1 = gelu(values @ weights["hidden1_weight"].T + weights["hidden1_bias"])
    h2 = gelu(h1 @ weights["hidden2_weight"].T + weights["hidden2_bias"])
    return (
        values @ weights["skip_weight"].T
        + weights["skip_bias"]
        + h2 @ weights["output_weight"].T
        + weights["output_bias"]
    )


def train(features, directory, source_sha, write_json):
    started = time.perf_counter()
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset

    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.set_default_dtype(torch.float64)
    torch.manual_seed(420500)
    if (
        torch.version.cuda is not None
        or torch.cuda.is_initialized()
        or len(os.sched_getaffinity(0)) != 1
    ):
        raise RuntimeError("CPU-only/single-core training qualification failed")
    directory = Path(directory)
    rank = features["train_encoded"].shape[1]
    if (
        rank > 128
        or features["train_encoded"].shape[0] > 256
        or features["validation_encoded"].shape[0] > 64
    ):
        raise ValueError("registered train/validation/rank capacity exceeded")

    class ResidualMLP(nn.Module):
        def __init__(self):
            super().__init__()
            self.skip = nn.Linear(2 * rank, 2 * rank)
            self.hidden1 = nn.Linear(2 * rank, 64)
            self.hidden2 = nn.Linear(64, 64)
            self.output = nn.Linear(64, 2 * rank)
            with torch.no_grad():
                self.skip.weight.copy_(
                    torch.from_numpy(features["initial_skip_weight"])
                )
                self.skip.bias.zero_()
                self.output.weight.zero_()
                self.output.bias.zero_()

        def forward(self, values):
            return self.skip(values) + self.output(
                torch.nn.functional.gelu(
                    self.hidden2(torch.nn.functional.gelu(self.hidden1(values)))
                )
            )

    model = ResidualMLP().double().cpu()
    gram = torch.from_numpy(features["native_gram"])

    def tensors(split):
        names = (
            "encoded",
            "target",
            "native_cross",
            "native_constant",
            "native_denominator",
        )
        values = [features[f"{split}_{key}"] for key in names]
        values[0] = pack(values[0])
        return tuple(torch.from_numpy(a) for a in values)

    training = TensorDataset(*tensors("train"))
    validation = tensors("validation")
    loader = DataLoader(
        training,
        batch_size=32,
        shuffle=True,
        num_workers=0,
        generator=torch.Generator().manual_seed(420500),
    )
    if (
        loader.num_workers != 0
        or torch.get_num_threads() != 1
        or torch.get_num_interop_threads() != 1
    ):
        raise RuntimeError("actual training thread/data-loader policy failed")
    optimizer = torch.optim.Adam(model.parameters(), lr=1.0e-3, weight_decay=1.0e-6)

    def losses(batch):
        encoded, target, cross, constant, denominator = batch
        prediction = model(encoded)
        c = torch.complex(prediction[:, :rank], prediction[:, rank:])
        difference = c - target
        correction = torch.sum(torch.abs(difference) ** 2, dim=1) / torch.clamp(
            torch.sum(torch.abs(target) ** 2, dim=1), min=1.0e-30
        )
        native = (
            torch.einsum("bi,ij,bj->b", c.conj(), gram, c).real
            - 2.0 * torch.sum(c.conj() * cross, dim=1).real
            + constant
        )
        # Gram compression roundoff is diagnostic, not a strict residual Gate.
        native = torch.clamp(native, min=0.0) / torch.clamp(denominator, min=1.0e-30)
        return correction.mean() + native.mean(), correction.mean(), native.mean()

    def checkpoint(path, epoch, metrics):
        torch.save(
            {
                "schema": "task042.cpu-fp64-residual-mlp.v1",
                "source_sha": source_sha,
                "epoch": epoch,
                "rank": rank,
                "width": 64,
                "dtype": "float64",
                "seed": 420500,
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "metrics": metrics,
                "loaded_seconds": time.perf_counter() - started,
            },
            path,
        )

    model.eval()
    with torch.no_grad():
        initial = [float(v) for v in losses(validation)]
    best = initial[0]
    checkpoint(directory / "best.pt", 0, initial)
    history = [
        {
            "epoch": 0,
            "validation_loss": best,
            "correction_loss": initial[1],
            "native_equation_loss": initial[2],
        }
    ]
    epochs = 0
    status = "TRAINING_COMPLETED"
    checkpoint(directory / "latest.pt", 0, initial)
    for epoch in range(1, 301):
        if time.perf_counter() - started >= 7200:
            status = "TRAINING_BUDGET_REACHED"
            break
        model.train()
        for batch_index, batch in enumerate(loader):
            if time.perf_counter() - started >= 7200:
                status = "TRAINING_BUDGET_REACHED"
                checkpoint(
                    directory / "latest.pt",
                    epoch - 1,
                    {"partial_epoch": epoch, "completed_batches": batch_index},
                )
                break
            optimizer.zero_grad(set_to_none=True)
            loss, _, _ = losses(batch)
            if not torch.isfinite(loss):
                status = "TRAINING_NONFINITE"
                break
            loss.backward()
            optimizer.step()
        if status in ("TRAINING_NONFINITE", "TRAINING_BUDGET_REACHED"):
            break
        model.eval()
        with torch.no_grad():
            measured = [float(v) for v in losses(validation)]
        epochs = epoch
        history.append(
            {
                "epoch": epoch,
                "validation_loss": measured[0],
                "correction_loss": measured[1],
                "native_equation_loss": measured[2],
                "loaded_seconds": time.perf_counter() - started,
            }
        )
        checkpoint(directory / "latest.pt", epoch, measured)
        if measured[0] < best:
            best = measured[0]
            checkpoint(directory / "best.pt", epoch, measured)
        write_json(directory / "training_history.json", history)
    saved = torch.load(directory / "best.pt", map_location="cpu", weights_only=True)
    model.load_state_dict(saved["model"])
    model.eval()
    weights = {
        key.replace(".", "_"): value.detach().cpu().numpy().copy()
        for key, value in model.state_dict().items()
    }
    np.savez(directory / "frozen_model.npz", **weights)
    probe = pack(features["validation_encoded"][:16])
    with torch.no_grad():
        expected = model(torch.from_numpy(probe)).numpy()
    observed = numpy_prediction(probe, weights)
    difference = float(
        np.linalg.norm(expected - observed)
        / max(np.linalg.norm(expected), np.finfo(float).tiny)
    )
    np.savez(directory / "inference_probe.npz", input=probe, output=expected)
    if difference > 1.0e-12:
        raise ValueError("NumPy frozen inference differs from Torch FP64")
    summary = {
        "status": status,
        "source_sha": source_sha,
        "epochs": epochs,
        "selected_epoch": saved["epoch"],
        "rank": rank,
        "width": 64,
        "hidden_layers": 2,
        "dtype": "float64 real/imag",
        "seed": 420500,
        "batch_size": 32,
        "data_loader_workers": loader.num_workers,
        "intra_threads": torch.get_num_threads(),
        "interop_threads": torch.get_num_interop_threads(),
        "parameter_count": sum(p.numel() for p in model.parameters()),
        "device": "cpu",
        "cuda_build": torch.version.cuda,
        "vram_bytes": None,
        "loaded_training_seconds": time.perf_counter() - started,
        "best_validation_loss": best,
        "frozen_torch_numpy_relative_difference": difference,
        "weight_payload_bytes": sum(a.nbytes for a in weights.values()),
        "torch_version": torch.__version__,
        "actual_default_dtype": str(torch.get_default_dtype()),
        "inference_probe_path": str(directory / "inference_probe.npz"),
        "inference_probe_sha256": hashlib.sha256(
            (directory / "inference_probe.npz").read_bytes()
        ).hexdigest(),
        "best_checkpoint_sha256": hashlib.sha256(
            (directory / "best.pt").read_bytes()
        ).hexdigest(),
        "frozen_model_sha256": hashlib.sha256(
            (directory / "frozen_model.npz").read_bytes()
        ).hexdigest(),
        "heldout_read": False,
        "shared_workstation": True,
    }
    write_json(directory / "training_summary.json", summary)
    return summary
