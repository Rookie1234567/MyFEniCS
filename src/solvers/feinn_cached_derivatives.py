"""Exact detached MLP linearization and its real adjoint, in <=8-cell blocks.

No graph/J/K is retained. Only structural zeros of the *oriented* complete
moment map are removed. The independent Torch/AD implementation stays intact.
"""

import hashlib
from time import perf_counter

import numpy as np
from scipy import sparse
import torch

from src.solvers.feinn_parameter_jvp import direction_dict


def model_key(model):
    value = hashlib.sha256()
    for name, tensor in model.state_dict().items():
        a = tensor.detach().cpu().numpy()
        value.update(name.encode())
        value.update(str((a.shape, a.dtype)).encode())
        value.update(a.tobytes())
    return value.hexdigest()


class CachedMomentJacobian:
    """Fixed-point numerical cache; trials use the original independent forward."""

    def __init__(self, mapping, *, cache_limit=2 * 2**30):
        self.mapping = mapping
        self.cache_limit = cache_limit
        self.counts = dict(JVP=0, VJP=0)
        self.costs = dict(JVP=0.0, VJP=0.0, build=0.0, release=0.0)
        self.version = 0
        self.key = None
        self.blocks = []
        self.weights = []
        self.bytes = 0
        self.builds = 0
        self.implementation = (
            "candidate2: detached FP64 analytic tangent/real adjoint; "
            "canonical Torch linear/Piola/interpolation/orientation order"
        )
        h = hashlib.sha256()
        for name in sorted(mapping.packet):
            a = np.asarray(mapping.packet[name])
            h.update(name.encode())
            h.update(str((a.shape, a.dtype)).encode())
            h.update(a.tobytes())
        self.static_key = h.hexdigest()
        # Compose orientation before deleting exact zero entries. No threshold.
        interpolation_csr = sparse.csr_matrix(mapping.interpolation.numpy())
        self.operators = []
        self.adjoints = []
        for t in mapping.transforms.numpy():
            oriented = (sparse.csr_matrix(t) @ interpolation_csr).tocsr()
            oriented.eliminate_zeros()
            self.operators.append(oriented)
            self.adjoints.append(oriented.conjugate().T.tocsr())
        self.static_bytes = sum(
            a.data.nbytes + a.indices.nbytes + a.indptr.nbytes
            for a in self.operators + self.adjoints
        )
        if self.static_bytes > self.cache_limit:
            raise ValueError("STATIC_CACHE_CAPACITY_EXCEEDED")

    def invalidate(self):
        started = perf_counter()
        self.blocks.clear()
        self.weights.clear()
        self.key = None
        self.bytes = self.static_bytes
        self.version += 1
        self.costs["release"] += perf_counter() - started

    def ensure(self, model):
        key = model_key(model)
        if key == self.key:
            return
        self.invalidate()
        started = perf_counter()
        nq = self.mapping.coordinates.shape[1]
        # X0, three H, three tanh derivatives, phase, and detached layer weights.
        predicted = (
            self.static_bytes
            + self.mapping.nc * nq * ((3 + 6 * 64) * 8 + 16)
            + sum(p.numel() * p.element_size() for p in model.parameters())
        )
        if predicted > self.cache_limit:
            raise ValueError("DETACHED_CACHE_CAPACITY_EXCEEDED_BEFORE_ALLOCATION")
        with torch.no_grad():
            self.weights = [
                (
                    model.envelopes[i].weight.detach().clone(),
                    model.envelopes[i].bias.detach().clone(),
                )
                for i in (0, 2, 4, 6)
            ]
            for first in range(0, self.mapping.nc, 8):
                stop = min(first + 8, self.mapping.nc)
                coords = self.mapping.coordinates[first:stop].reshape(-1, 3)
                x = (coords - model.center) / model.half_width
                xs, ds = [x], []
                for w, b in self.weights[:-1]:
                    x = torch.tanh(torch.nn.functional.linear(x, w, b))
                    xs.append(x)
                    ds.append(1 - x * x)
                phase = None
                if hasattr(model, "phase_k_inc"):
                    arg = (coords - model.phase_origin) @ model.phase_k_inc
                    phase = torch.complex(torch.cos(arg), torch.sin(arg))
                self.blocks.append((first, stop, xs, ds, phase))
        tensors = [
            t
            for _, _, xs, ds, phase in self.blocks
            for t in xs + ds + ([] if phase is None else [phase])
        ]
        tensors += [t for wb in self.weights for t in wb]
        self.bytes = self.static_bytes + sum(
            t.numel() * t.element_size() for t in tensors
        )
        if self.bytes > self.cache_limit or any(t.requires_grad for t in tensors):
            self.invalidate()
            raise ValueError("CACHE_CAPACITY_OR_DETACH_CONTRACT_FAILED")
        self.predicted_bytes = predicted
        self.key = key
        self.builds += 1
        self.costs["build"] += perf_counter() - started

    def chunks(self, model, batch):
        if batch not in (1, 8):
            raise ValueError("ONLY_QUALIFIED_BATCH1_8")
        self.ensure(model)
        nq = self.mapping.coordinates.shape[1]
        for first, stop, xs, ds, phase in self.blocks:
            for begin in range(first, stop, batch):
                end = min(begin + batch, stop)
                sl = slice((begin - first) * nq, (end - first) * nq)
                yield (
                    begin,
                    end,
                    [x[sl] for x in xs],
                    [d[sl] for d in ds],
                    None if phase is None else phase[sl],
                )

    def moments(self, values, first, stop):
        m = self.mapping
        values = torch.as_tensor(values)
        pulled = torch.einsum("cqa,cab->cqb", values, m.jacobians[first:stop])
        flat = pulled.transpose(1, 2).reshape(stop - first, -1)
        moments = flat @ m.interpolation.T
        ids = m.packet["orientation_ids"][first:stop]
        return torch.bmm(m.transforms[ids], moments[:, :, None])[:, :, 0].numpy()

    def point_dual(self, dual, first, stop):
        m = self.mapping
        rows = m.packet["owner_rows"][first:stop]
        selected = rows >= 0
        full = torch.zeros(rows.shape, dtype=torch.complex128)
        full[torch.as_tensor(selected)] = torch.as_tensor(dual[rows[selected]])
        ids = m.packet["orientation_ids"][first:stop]
        moments = torch.bmm(m.transforms[ids].conj().transpose(1, 2), full[:, :, None])[
            :, :, 0
        ]
        flat = moments @ m.interpolation.conj()
        pulled = flat.reshape(stop - first, 3, -1).transpose(1, 2)
        return (
            torch.einsum("cqb,cab->cqa", pulled, m.jacobians[first:stop].conj())
            .reshape(-1, 3)
            .numpy()
        )

    def forward(self, model, batch=8):
        out = np.empty(self.mapping.size, np.complex128)
        with torch.no_grad():
            for first, stop, xs, _, phase in self.chunks(model, batch):
                w, b = self.weights[-1]
                value = torch.nn.functional.linear(xs[-1], w, b).reshape(-1, 3, 2)
                value = torch.complex(value[..., 0], value[..., 1])
                if phase is not None:
                    value *= phase[:, None]
                self.store(
                    out,
                    self.moments(
                        value.numpy().reshape(stop - first, -1, 3), first, stop
                    ),
                    first,
                    stop,
                )
        return out

    def store(self, out, moments, first, stop):
        rows = self.mapping.packet["owner_rows"][first:stop]
        selected = rows >= 0
        out[rows[selected]] = moments[selected]

    def jvp(self, model, vector, batch=8):
        started = perf_counter()
        direction = direction_dict(model, vector)
        out = np.empty(self.mapping.size, np.complex128)
        with torch.no_grad():
            for first, stop, xs, ds, phase in self.chunks(model, batch):
                dx = torch.zeros_like(xs[0])
                for k, index in enumerate((0, 2, 4, 6)):
                    prefix = f"envelopes.{index}."
                    dx = torch.nn.functional.linear(
                        dx, self.weights[k][0], None
                    ) + torch.nn.functional.linear(
                        xs[k], direction[prefix + "weight"], direction[prefix + "bias"]
                    )
                    if k != 3:
                        dx = torch.ops.aten.tanh_backward(dx, xs[k + 1])
                dx = dx.reshape(-1, 3, 2)
                value = torch.complex(dx[..., 0], dx[..., 1])
                if phase is not None:
                    value *= phase[:, None]
                self.store(
                    out,
                    self.moments(
                        value.numpy().reshape(stop - first, -1, 3), first, stop
                    ),
                    first,
                    stop,
                )
        self.counts["JVP"] += 1
        self.costs["JVP"] += perf_counter() - started
        if not np.isfinite(out).all():
            raise ValueError("NONFINITE_CACHED_JVP")
        return out

    def vjp(self, model, dual, batch=8):
        started = perf_counter()
        dual = np.asarray(dual)
        if dual.shape != (self.mapping.size,) or dual.dtype != np.complex128:
            raise ValueError("COMPLEX128_COMPLETE_DUAL_REQUIRED")
        with torch.no_grad():
            grads = (
                [(torch.zeros_like(w), torch.zeros_like(b)) for w, b in self.weights]
                if self.key == model_key(model)
                else None
            )
            self.ensure(model)
            if grads is None:
                grads = [
                    (torch.zeros_like(w), torch.zeros_like(b)) for w, b in self.weights
                ]
            for first, stop, xs, ds, phase in self.chunks(model, batch):
                point = self.point_dual(dual, first, stop)
                if phase is not None:
                    point *= phase.numpy().conjugate()[:, None]
                dy = torch.as_tensor(
                    np.stack((point.real, point.imag), -1).reshape(-1, 6)
                )
                for k in (3, 2, 1, 0):
                    grads[k][0].add_(dy.T @ xs[k])
                    grads[k][1].add_(dy.sum(0))
                    if k:
                        dy = torch.ops.aten.tanh_backward(
                            dy @ self.weights[k][0], xs[k]
                        )
            out = torch.cat([a.ravel() for pair in grads for a in pair]).numpy().copy()
        self.counts["VJP"] += 1
        self.costs["VJP"] += perf_counter() - started
        if not np.isfinite(out).all():
            raise ValueError("NONFINITE_CACHED_VJP")
        return out

    def record(self):
        return dict(
            implementation=self.implementation,
            static_key=self.static_key,
            parameter_buffer_key=self.key,
            version=self.version,
            builds=self.builds,
            resident_bytes=self.bytes,
            cap_bytes=self.cache_limit,
            counts=self.counts.copy(),
            costs=self.costs.copy(),
        )
