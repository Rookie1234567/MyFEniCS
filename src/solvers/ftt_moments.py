"""Full Nedelec moments with detached point cotangents and bounded AD graphs."""

from time import perf_counter
import numpy as np
import torch
from scipy import sparse


class StreamingMomentMap:
    def __init__(self, packet, point_batch=512):
        if point_batch not in (128, 256, 512):
            raise ValueError("PREDECLARED_FTT_POINT_BATCH_REQUIRED")
        self.packet = packet
        self.point_batch = point_batch
        self.size = int(packet["active_rows"])
        self.nc = len(packet["owner_rows"])
        self.nq = len(packet["reference_points"])
        self.costs = dict(
            coordinates=0.0, network=0.0, moments=0.0, point_adjoint=0.0, VJP=0.0
        )
        self.counts = dict(forward=0, VJP=0, point_forward=0, point_backward=0)
        rows = packet["owner_rows"]
        if not np.array_equal(np.sort(rows[rows >= 0]), np.arange(self.size)):
            raise ValueError("ONE_OWNER_PER_INDEPENDENT_FE_COEFFICIENT_REQUIRED")
        # Exact structural zeros only; never discard a small nonzero moment.
        self.I = sparse.csr_matrix(packet["interpolation"], dtype=np.complex128)

    def cells(self, batch):
        if batch not in (1, 8):
            raise ValueError("ONLY_BATCH_1_8")
        for start in range(0, self.nc, batch):
            for cell in range(start, min(start + batch, self.nc)):
                began = perf_counter()
                p = self.packet
                J = p["jacobians"][cell]
                coords = p["origins"][cell] + p["reference_points"] @ J.T
                self.costs["coordinates"] += perf_counter() - began
                yield cell, J, coords

    def forward(self, model, batch=8):
        self.counts["forward"] += 1
        out = np.empty(self.size, dtype=np.complex128)
        with torch.no_grad():
            for cell, J, coords in self.cells(batch):
                values = np.empty((self.nq, 3), dtype=np.complex128)
                began = perf_counter()
                for start in range(0, self.nq, self.point_batch):
                    sl = slice(start, min(start + self.point_batch, self.nq))
                    values[sl] = model(torch.from_numpy(coords[sl])).numpy()
                    self.counts["point_forward"] += 1
                self.costs["network"] += perf_counter() - began
                began = perf_counter()
                pulled = values @ J
                local = self.I @ pulled.T.ravel()
                oriented = (
                    self.packet["transforms"][self.packet["orientation_ids"][cell]]
                    @ local
                )
                rows = self.packet["owner_rows"][cell]
                out[rows[rows >= 0]] = oriented[rows >= 0]
                self.costs["moments"] += perf_counter() - began
        if not np.isfinite(out).all():
            raise ValueError("NONFINITE_FTT_COMPLETE_MOMENTS")
        return out

    def vjp(self, model, dual, batch=8):
        dual = np.asarray(dual)
        if dual.dtype != np.complex128 or dual.shape != (self.size,):
            raise ValueError("COMPLETE_COMPLEX128_COTANGENT_REQUIRED")
        self.counts["VJP"] += 1
        model.zero_grad(set_to_none=True)
        for cell, J, coords in self.cells(batch):
            began = perf_counter()
            rows = self.packet["owner_rows"][cell]
            local = np.zeros(len(rows), dtype=np.complex128)
            local[rows >= 0] = dual[rows[rows >= 0]]
            T = self.packet["transforms"][self.packet["orientation_ids"][cell]]
            reference_dual = (
                (self.I.conj().T @ (T.conj().T @ local)).reshape(3, self.nq).T
            )
            point_dual = reference_dual @ J.conj().T
            self.costs["point_adjoint"] += perf_counter() - began
            for start in range(0, self.nq, self.point_batch):
                sl = slice(start, min(start + self.point_batch, self.nq))
                began = perf_counter()
                values = model(torch.from_numpy(coords[sl]))
                torch.real(
                    torch.vdot(torch.from_numpy(point_dual[sl]).ravel(), values.ravel())
                ).backward()
                self.costs["VJP"] += perf_counter() - began
                self.counts["point_backward"] += 1
                del values
        out = (
            torch.cat([p.grad.ravel() for p in model.parameters()])
            .detach()
            .numpy()
            .copy()
        )
        if not np.isfinite(out).all():
            raise ValueError("NONFINITE_FTT_PARAMETER_GRADIENT")
        return out
