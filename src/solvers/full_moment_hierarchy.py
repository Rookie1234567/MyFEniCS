"""Opt-in complete-moment residual decoder; no FE inverse or dense global basis.

All learned maps are shared by entity type. Buckets move contents, never FE
unknowns. Only the immutable, already qualified J and right diagonal are used.
"""

from time import perf_counter

import numpy as np
import torch
from torch import nn

from src.solvers.neighborhood_residual_models import sparse_tensor


class BucketLayout:
    """Canonical master inventory and exact entity-count-weighted hierarchy."""

    def __init__(self, graph):
        keys = np.asarray(graph["keys"], dtype=np.int64)
        sizes = np.asarray(graph["sizes"], dtype=np.int64)
        if keys.shape != (len(sizes), 5) or np.any(keys[:, 2:] < 0):
            raise ValueError("complete canonical entity keys")
        groups = np.where(keys[:, 0] == 3, 6, (keys[:, 0] - 1) * 3 + keys[:, 1])
        expected = np.choose(groups, [6, 6, 6, 60, 60, 60, 450])
        if (
            np.any(groups < 0)
            or np.any(groups > 6)
            or not np.array_equal(sizes, expected)
        ):
            raise ValueError("seven dimension/direction groups preserve all moments")
        offsets = np.asarray(graph["offsets"])
        if not np.array_equal(np.diff(offsets), sizes) or len(
            set(map(tuple, keys))
        ) != len(keys):
            raise ValueError("unique complete master entities and moment ordering")
        self.groups = groups
        self.indices = [np.flatnonzero(groups == g) for g in range(7)]
        self.moments = (6, 6, 6, 60, 60, 60, 450)
        self.levels, self.parents = [], []
        coordinates = keys[:, 2:] // 2
        while True:
            bucket_keys, ids = np.unique(coordinates, axis=0, return_inverse=True)
            counts = np.zeros((len(bucket_keys), 7), dtype=np.int64)
            np.add.at(counts, (ids, groups), 1)
            self.levels.append({"keys": bucket_keys, "ids": ids, "counts": counts})
            if len(bucket_keys) == 1:
                break
            coordinates = coordinates // 2
        for fine, coarse in zip(self.levels[:-1], self.levels[1:], strict=True):
            lookup = {tuple(k): i for i, k in enumerate(coarse["keys"])}
            parent = np.asarray([lookup[tuple(k // 2)] for k in fine["keys"]])
            aggregate = np.zeros_like(coarse["counts"])
            np.add.at(aggregate, parent, fine["counts"])
            if not np.array_equal(aggregate, coarse["counts"]):
                raise ValueError(
                    "parent uses actual entity counts, not equal child means"
                )
            self.parents.append(parent)
        self.offsets = offsets
        self.canonical_rows = int(offsets[-1])
        self.payload_bytes = sum(
            v.nbytes for l in self.levels for v in l.values()
        ) + sum(p.nbytes for p in self.parents)

    def arrays(self):
        values = {"entity_group": self.groups, "canonical_offsets": self.offsets}
        for i, level in enumerate(self.levels):
            values.update({f"level{i}_{key}": value for key, value in level.items()})
        values.update({f"parent{i}": value for i, value in enumerate(self.parents)})
        return values


class FullMomentCorrector(nn.Module):
    def __init__(
        self,
        bridge,
        graph,
        scale,
        *,
        seed,
        linear=False,
        local=False,
        zero_decoder=True,
    ):
        super().__init__()
        torch.manual_seed(seed)
        self.linear, self.local = linear, local
        self.layout = BucketLayout(graph)
        self.groups = [
            (m, int(np.count_nonzero(np.asarray(graph["sizes"]) == m)))
            for m in (6, 60, 450)
        ]
        self.encoder = nn.ModuleList(
            [
                nn.Linear(2 * m, 2 * m, bias=False, dtype=torch.float64)
                for m, _ in self.groups
            ]
        )
        self.message = nn.Sequential(
            nn.Linear(1296, 64, bias=False, dtype=torch.float64),
            nn.Identity() if linear else nn.Tanh(),
            nn.Linear(64, 1296, bias=False, dtype=torch.float64),
        )
        self.mix_local = nn.ParameterList(
            [
                nn.Parameter(torch.ones(2 * m, dtype=torch.float64))
                for m, _ in self.groups
            ]
        )
        self.mix_context = nn.ParameterList(
            [
                nn.Parameter(torch.ones(2 * m, dtype=torch.float64))
                for m, _ in self.groups
            ]
        )
        self.decoder = nn.ModuleList(
            [
                nn.Linear(2 * m, 2 * m, bias=False, dtype=torch.float64)
                for m, _ in self.groups
            ]
        )
        if zero_decoder:
            with torch.no_grad():
                for layer in self.decoder:
                    layer.weight.zero_()
        self.register_buffer("bridge", sparse_tensor(bridge))
        self.register_buffer("dual", sparse_tensor(bridge.conjugate().T))
        self.register_buffer("scale", torch.from_numpy(np.asarray(scale).copy()))
        self.node_indices = []
        for g, ids in enumerate(self.layout.indices):
            self.register_buffer(f"nodes_{g}", torch.from_numpy(ids.copy()))
            self.node_indices.append(f"nodes_{g}")
            for level, value in enumerate(self.layout.levels):
                self.register_buffer(
                    f"ids_{g}_{level}", torch.from_numpy(value["ids"][ids].copy())
                )
                self.register_buffer(
                    f"counts_{g}_{level}",
                    torch.from_numpy(value["counts"][:, g].astype(float)),
                )
        self.real_parameters = sum(p.numel() for p in self.parameters())
        if self.real_parameters != 1817040 or self.real_parameters > 2000000:
            raise MemoryError("frozen full-moment architecture parameter inventory")
        self.activation_records = []
        self.record_activations = False
        self.phase_seconds = {}
        self.phase_calls = {}

    def account(self, name, began):
        self.phase_seconds[name] = (
            self.phase_seconds.get(name, 0.0) + perf_counter() - began
        )
        self.phase_calls[name] = self.phase_calls.get(name, 0) + 1

    def phi(self, values, name):
        if self.record_activations:
            with torch.no_grad():
                derivative = (
                    torch.ones_like(values)
                    if self.linear
                    else 1 - torch.tanh(values) ** 2
                )
                self.activation_records.append(
                    {
                        "name": name,
                        "input_RMS": float(torch.sqrt(torch.mean(values**2))),
                        "derivative_min": float(derivative.min()),
                        "derivative_mean": float(derivative.mean()),
                        "derivative_max": float(derivative.max()),
                        "saturation_fraction_derivative_lt_0p01": float(
                            torch.mean((derivative < 0.01).double())
                        ),
                        "samples": values.numel(),
                    }
                )
        return values if self.linear else torch.tanh(values)

    def aggregate(self, values, group, level):
        """Entity mean. Its transpose broadcasts divided by the true count."""
        began = perf_counter()
        ids = getattr(self, f"ids_{group}_{level}")
        counts = getattr(self, f"counts_{group}_{level}")
        summed = torch.zeros(
            (values.shape[0], len(counts), values.shape[-1]), dtype=values.dtype
        )
        summed.index_add_(1, ids, values)
        result = (
            summed
            / torch.where(counts == 0, torch.ones_like(counts), counts)[None, :, None]
        )
        self.account("bucket_mean", began)
        return result

    def aggregate_transpose(self, values, group, level):
        ids = getattr(self, f"ids_{group}_{level}")
        counts = getattr(self, f"counts_{group}_{level}")
        return values[:, ids, :] / counts[ids][None, :, None]

    def broadcast(self, values, group, level):
        began = perf_counter()
        result = values[:, getattr(self, f"ids_{group}_{level}"), :]
        self.account("bucket_broadcast_copy", began)
        return result

    def broadcast_transpose(self, values, group, level):
        ids = getattr(self, f"ids_{group}_{level}")
        counts = getattr(self, f"counts_{group}_{level}")
        summed = torch.zeros(
            (values.shape[0], len(counts), values.shape[-1]), dtype=values.dtype
        )
        summed.index_add_(1, ids, values)
        return summed

    def canonical(self, values, *, fixed_gamma=None):
        """Full canonical complex output. Fixed gamma is for mechanism witnesses."""
        if values.ndim == 1:
            values = values[None, :]
        gamma = (
            torch.linalg.vector_norm(values, dim=1)
            / np.sqrt(self.layout.canonical_rows)
            if fixed_gamma is None
            else torch.full((len(values),), fixed_gamma, dtype=torch.float64)
        )
        divisor = torch.where(gamma == 0, torch.ones_like(gamma), gamma)
        inputs = values / divisor[:, None]
        hidden, offset = [], 0
        for i, (m, n) in enumerate(self.groups):
            x = inputs[:, offset : offset + n * m].reshape(len(values), n, m)
            began = perf_counter()
            hidden.append(
                self.phi(
                    self.encoder[i](torch.cat((x.real, x.imag), dim=-1)), f"encoder_{m}"
                )
            )
            self.account("encoder_phi", began)
            offset += n * m
        split = [
            hidden[g // 3][
                :,
                getattr(self, self.node_indices[g])
                - sum(n for _, n in self.groups[: g // 3]),
                :,
            ]
            if g < 6
            else hidden[2]
            for g in range(7)
        ]
        # Group-local indices are derived from canonical node IDs, not owner cells.
        contexts = [torch.zeros_like(h) for h in split]
        levels = [0] if self.local else list(range(len(self.layout.levels)))
        message_level = 0 if self.local else len(self.layout.levels) - 1
        exchange = None
        for level in levels:
            means = [self.aggregate(h, g, level) for g, h in enumerate(split)]
            for g, mean in enumerate(means):
                contexts[g] = contexts[g] + self.broadcast(mean, g, level) / len(levels)
            if level == message_level:
                began = perf_counter()
                joined = torch.cat(means, dim=-1)
                first = self.message[0](joined)
                exchange = self.message[2](self.phi(first, "cross_type_64"))
                self.account("cross_type_phi", began)
        outputs, channel = [], 0
        for g, h in enumerate(split):
            typ = 0 if g < 3 else 1 if g < 6 else 2
            width = h.shape[-1]
            u = self.broadcast(
                exchange[:, :, channel : channel + width], g, message_level
            )
            began = perf_counter()
            h2 = self.phi(
                self.mix_local[typ] * h + self.mix_context[typ] * contexts[g] + u,
                f"combine_{g}",
            )
            outputs.append(self.decoder[typ](h2))
            self.account("combine_phi_decoder", began)
            channel += width
        began = perf_counter()
        ordered = []
        for typ, (m, n) in enumerate(self.groups):
            out = torch.zeros((len(values), n, 2 * m), dtype=torch.float64)
            base = sum(c for _, c in self.groups[:typ])
            for g in range(7):
                if (0 if g < 3 else 1 if g < 6 else 2) == typ:
                    out.index_copy_(
                        1, getattr(self, self.node_indices[g]) - base, outputs[g]
                    )
            ordered.append(
                torch.complex(out[..., :m], out[..., m:]).reshape(len(values), n * m)
            )
        result = gamma[:, None] * torch.cat(ordered, dim=-1)
        self.account("canonical_output_copy", began)
        return result

    def forward(self, rhs):
        if rhs.ndim == 1:
            rhs = rhs[None, :]
        began = perf_counter()
        canonical = torch.sparse.mm(self.dual, rhs.T).T
        self.account("JH_input_copy", began)
        out = self.canonical(canonical)
        began = perf_counter()
        result = self.scale[None, :] * torch.sparse.mm(self.bridge, out.T).T
        self.account("DJ_output_copy", began)
        return result
