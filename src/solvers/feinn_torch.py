"""Frozen CPU FP64 coordinate network and bounded complete-moment VJP."""

from itertools import pairwise
from time import perf_counter

import numpy as np
import torch


class CoordinateField(torch.nn.Module):
    def __init__(self, bounds, seed=421001):
        super().__init__()
        torch.manual_seed(seed)
        layers = []
        for i, (n, m) in enumerate(pairwise((3, 64, 64, 64, 6))):
            layers.append(torch.nn.Linear(n, m, dtype=torch.float64))
            if i < 3:
                layers.append(torch.nn.Tanh())
        self.envelopes = torch.nn.Sequential(*layers)
        torch.nn.init.zeros_(layers[-1].weight)
        torch.nn.init.zeros_(layers[-1].bias)
        box = torch.as_tensor(bounds, dtype=torch.float64)
        self.register_buffer("center", box.mean(1))
        self.register_buffer("half_width", (box[:, 1] - box[:, 0]) / 2)
        if sum(p.numel() for p in self.parameters()) != 8966:
            raise ValueError("frozen architecture parameter inventory mismatch")

    def forward(self, coordinates):
        out = self.envelopes((coordinates - self.center) / self.half_width).reshape(
            -1, 3, 2
        )
        return torch.complex(out[..., 0], out[..., 1])


class CompleteMomentMap:
    def __init__(self, packet):
        self.packet = packet
        self.costs = dict(network_forward=0.0, moment_map=0.0, VJP_backward=0.0)
        self.counts = dict(forward=0, VJP=0)
        self.size = int(packet["active_rows"])
        self.nc = len(packet["owner_rows"])
        self.points = torch.as_tensor(
            np.array(packet["reference_points"]), dtype=torch.float64
        )
        self.interpolation = torch.as_tensor(
            np.array(packet["interpolation"]), dtype=torch.complex128
        )
        self.transforms = torch.as_tensor(
            np.array(packet["transforms"]), dtype=torch.complex128
        )
        self.jacobians = torch.as_tensor(
            np.array(packet["jacobians"]), dtype=torch.complex128
        )
        j = packet["jacobians"]
        coordinates = packet["origins"][:, None, :] + np.einsum(
            "qa,cba->cqb", packet["reference_points"], j
        )
        self.coordinates = torch.as_tensor(coordinates, dtype=torch.float64)
        self.numeric_cache_bytes = sum(
            x.nelement() * x.element_size()
            for x in (
                self.points,
                self.interpolation,
                self.transforms,
                self.jacobians,
                self.coordinates,
            )
        )
        owners = packet["owner_rows"].ravel()
        if not np.array_equal(np.sort(owners[owners >= 0]), np.arange(self.size)):
            raise ValueError(
                "complete moments require one owner per independent coefficient"
            )

    def blocks(self, model, batch=8):
        if batch not in (1, 8):
            raise ValueError("only predeclared batch1/8")
        for start in range(0, self.nc, batch):
            stop = min(start + batch, self.nc)
            coordinates = self.coordinates[start:stop]
            began = perf_counter()
            values = model(coordinates.reshape(-1, 3)).reshape(stop - start, -1, 3)
            self.costs["network_forward"] += perf_counter() - began
            began = perf_counter()
            pulled = torch.einsum("cqa,cab->cqb", values, self.jacobians[start:stop])
            moments = (
                pulled.transpose(1, 2).reshape(stop - start, -1) @ self.interpolation.T
            )
            ids = self.packet["orientation_ids"][start:stop]
            oriented = torch.bmm(self.transforms[ids], moments[:, :, None])[:, :, 0]
            rows = self.packet["owner_rows"][start:stop]
            selected = rows >= 0
            self.costs["moment_map"] += perf_counter() - began
            yield rows[selected], oriented[torch.as_tensor(selected)]

    def forward(self, model, batch=8):
        self.counts["forward"] += 1
        out = np.empty(self.size, dtype=np.complex128)
        with torch.no_grad():
            for rows, values in self.blocks(model, batch):
                out[rows] = values.numpy()
        if not np.isfinite(out).all():
            raise ValueError("nonfinite full moment coefficients")
        return out

    def vjp(self, model, dual, batch=8):
        self.counts["VJP"] += 1
        dual = np.asarray(dual)
        if dual.shape != (self.size,) or dual.dtype != np.complex128:
            raise ValueError("complex128 complete coefficient dual required")
        model.zero_grad(set_to_none=True)
        for rows, values in self.blocks(model, batch):
            began = perf_counter()
            torch.real(torch.vdot(torch.as_tensor(dual[rows]), values)).backward()
            self.costs["VJP_backward"] += perf_counter() - began
        out = (
            torch.cat([p.grad.ravel() for p in model.parameters()])
            .detach()
            .numpy()
            .copy()
        )
        if not np.isfinite(out).all():
            raise ValueError("nonfinite full real parameter VJP")
        return out
