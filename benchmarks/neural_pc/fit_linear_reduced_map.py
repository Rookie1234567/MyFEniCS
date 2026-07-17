from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from benchmarks.neural_pc.data_contract import load_dataset
from src.solvers.batched_reduced_smoother import FrozenLinearReducedMap


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--rank", type=int, default=128)
    parser.add_argument("--ridge", type=float, default=1e-10)
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()
    operator, samples, manifest = load_dataset(Path(args.dataset))
    selected = (samples["split"].astype(str) == "train") & (samples["sample_kind"].astype(str) == "ilu_residual")
    x = samples["rhs"][selected]
    y = samples["target"][selected]
    scale = np.maximum(np.linalg.norm(x, axis=1), np.finfo(float).tiny)
    xn, yn = x / scale[:, None], y / scale[:, None]
    import torch

    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested for reduced-map construction but is unavailable")
    device = torch.device(args.device)
    xt = torch.as_tensor(xn.T, dtype=torch.complex128, device=device)
    yt = torch.as_tensor(yn.T, dtype=torch.complex128, device=device)
    ux_t, sx_t, _ = torch.linalg.svd(xt, full_matrices=False)
    uy_t, sy_t, _ = torch.linalg.svd(yt, full_matrices=False)
    ux, sx = ux_t.cpu().numpy(), sx_t.cpu().numpy()
    uy, sy = uy_t.cpu().numpy(), sy_t.cpu().numpy()
    rank = min(args.rank, len(sx), len(sy))
    input_basis, output_basis = ux[:, :rank], uy[:, :rank]
    coordinates = xn @ input_basis.conj()
    targets = yn @ output_basis.conj()
    gram = coordinates.conj().T @ coordinates + args.ridge * np.eye(rank)
    gram_t = torch.as_tensor(gram, dtype=torch.complex128, device=device)
    rhs_t = torch.as_tensor(coordinates.conj().T @ targets, dtype=torch.complex128, device=device)
    reduced_map_t = torch.linalg.solve(gram_t, rhs_t).cpu().numpy()
    model = FrozenLinearReducedMap(input_basis, reduced_map_t.T, output_basis, operator.fingerprint)
    model.save(Path(args.output), backend="complex_pod_ridge", rank=rank, ridge=args.ridge, training_samples=int(selected.sum()), dataset_schema=manifest["schema"], nonlinear_activation=False, construction_device=str(device), torch_version=torch.__version__)
    print(json.dumps({"rank": rank, "storage_bytes": model.storage_bytes, "output": args.output, "device": str(device)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
