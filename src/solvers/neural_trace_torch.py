"""CPU FP64 coordinate envelopes and bounded recomputation VJP.

Only imported in the isolated ML environment. No FE/MPI/PETSc imports here.
"""

import ctypes
from itertools import pairwise
from pathlib import Path

import numpy as np
import torch


def qualify_threads():
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    if torch.cuda.is_initialized() or torch.version.cuda is not None:
        raise RuntimeError("CPU-only PyTorch required")
    pools = []
    for path in sorted(
        {
            line.split()[-1]
            for line in Path("/proc/self/maps").read_text().splitlines()
            if "openblas" in line and line.split()[-1].startswith("/")
        }
    ):
        library = ctypes.CDLL(path)
        for name in (
            "openblas_get_num_threads",
            "openblas_get_num_threads64_",
            "scipy_openblas_get_num_threads",
            "scipy_openblas_get_num_threads64_",
        ):
            if hasattr(library, name):
                function = getattr(library, name)
                function.restype = ctypes.c_int
                count = function()
                if count != 1:
                    raise RuntimeError(
                        "Actual ML NumPy BLAS pool is not single-threaded"
                    )
                pools.append(dict(path=path, function=name, threads=count))
                break
        else:
            raise RuntimeError("Actual ML BLAS thread probe unavailable")
    if not pools:
        raise RuntimeError("ML BLAS pool not found")
    return dict(
        intraop=torch.get_num_threads(),
        interop=torch.get_num_interop_threads(),
        cuda_build=torch.version.cuda,
        data_loader_workers=0,
        actual_blas_pools=pools,
    )


class NeuralTrace(torch.nn.Module):
    def __init__(self, bounds, wavelength, grazing_deg=1.0, seed=420906):
        super().__init__()
        torch.manual_seed(seed)
        layers = []
        sizes = [3, 64, 64, 64, 48]
        for index, (source, target) in enumerate(pairwise(sizes)):
            layer = torch.nn.Linear(source, target, dtype=torch.float64)
            layers.append(layer)
            if index < 3:
                layers.append(torch.nn.Tanh())
        self.envelopes = torch.nn.Sequential(*layers)
        torch.nn.init.zeros_(layers[-1].weight)
        torch.nn.init.zeros_(layers[-1].bias)
        bounds = torch.as_tensor(bounds, dtype=torch.float64)
        self.register_buffer("center", bounds.mean(dim=1))
        self.register_buffer("half_width", (bounds[:, 1] - bounds[:, 0]) / 2)
        angle = np.deg2rad(grazing_deg)
        directions = np.vstack(
            (
                np.eye(3),
                -np.eye(3),
                [np.cos(angle), 0, -np.sin(angle)],
                [np.cos(angle), 0, np.sin(angle)],
            )
        )
        self.register_buffer(
            "wavevectors",
            torch.as_tensor(directions * (2 * np.pi / wavelength), dtype=torch.float64),
        )

    def forward(self, coordinates):
        values = self.envelopes((coordinates - self.center) / self.half_width)
        envelopes = values.reshape(-1, 8, 3, 2)
        complex_envelopes = torch.complex(envelopes[..., 0], envelopes[..., 1])
        phases = torch.exp(1j * (coordinates @ self.wavevectors.T))
        return torch.sum(complex_envelopes * phases[:, :, None], dim=1)


def packet_blocks(model, packet, cells=None):
    """One affine cell per graph; only owner rows enter the reduced vector."""
    reference = torch.as_tensor(packet["reference_points"], dtype=torch.float64)
    interpolation = torch.as_tensor(packet["interpolation"], dtype=torch.float64)
    cells = range(len(packet["owner_rows"])) if cells is None else cells
    for cell in cells:
        rows = packet["owner_rows"][cell]
        selected = rows >= 0
        if not selected.any():
            continue
        jacobian = torch.as_tensor(packet["jacobians"][cell], dtype=torch.float64)
        origin = torch.as_tensor(packet["origins"][cell], dtype=torch.float64)
        values = model(origin + reference @ jacobian.T) @ jacobian.to(torch.complex128)
        moments = interpolation.to(torch.complex128) @ values.T.reshape(-1)
        transform = torch.as_tensor(
            packet["transforms"][packet["orientation_ids"][cell]],
            dtype=torch.complex128,
        )
        oriented = transform @ moments
        yield rows[selected], oriented[torch.as_tensor(selected)]


def packet_forward(model, packet):
    result = np.empty(int(packet["active_rows"]), dtype=np.complex128)
    with torch.no_grad():
        for rows, values in packet_blocks(model, packet):
            result[rows] = values.numpy()
    return result


def packet_vjp(model, packet, gradient):
    """Frozen weights recomputed cellwise; caller steps only after completion."""
    model.zero_grad(set_to_none=True)
    for rows, values in packet_blocks(model, packet):
        dual = torch.as_tensor(gradient[rows], dtype=torch.complex128)
        torch.real(torch.vdot(dual, values)).backward()
    return torch.cat([p.grad.reshape(-1) for p in model.parameters()]).detach().numpy()
