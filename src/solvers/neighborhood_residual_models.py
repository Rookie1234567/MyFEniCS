"""CPU FP64 shared neighborhood models and the original finite action VJP.

No PETSc/MPI imports. Matrix bytes are supplied by a separately qualified FE
packet. The sparse matrix and its conjugate data are explicitly resident.
"""

import hashlib

import numpy as np
import torch
from torch import nn


def configure_threads():
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    if torch.get_num_threads() != 1 or torch.get_num_interop_threads() != 1:
        raise RuntimeError("actual Torch single-thread gate")


def sparse_tensor(matrix):
    a = matrix.tocoo()
    ids = np.vstack((a.row, a.col)).astype(np.int64)
    return torch.sparse_coo_tensor(
        torch.from_numpy(ids),
        torch.from_numpy(a.data.copy()),
        size=a.shape,
        dtype=torch.complex128,
    ).coalesce()


class NeighborhoodCorrector(nn.Module):
    def __init__(self, bridge, graph, scale, *, linear=False, seed=424301, width=32):
        super().__init__()
        torch.manual_seed(seed)
        self.linear = linear
        dtype = torch.complex128 if linear else torch.float64
        sizes = np.asarray(graph["sizes"])
        self.groups = [
            (int(m), int(np.count_nonzero(sizes == m))) for m in (6, 60, 450)
        ]
        if sum(m * n for m, n in self.groups) != bridge.shape[1]:
            raise ValueError("type-contiguous complete-moment inventory")
        channel = 1 if linear else 2
        self.encoder = nn.ModuleList(
            [
                nn.Linear(channel * m, width, bias=False, dtype=dtype)
                for m, _ in self.groups
            ]
        )
        self.message_self = nn.ModuleList(
            [nn.Linear(width, width, bias=False, dtype=dtype) for _ in range(2)]
        )
        self.message_neighbor = nn.ModuleList(
            [nn.Linear(width, width, bias=False, dtype=dtype) for _ in range(2)]
        )
        self.decoder = nn.ModuleList(
            [
                nn.Linear(width, channel * m, bias=False, dtype=dtype)
                for m, _ in self.groups
            ]
        )
        self.register_buffer("bridge", sparse_tensor(bridge))
        self.register_buffer("dual", sparse_tensor(bridge.conjugate().T))
        self.register_buffer("scale", torch.from_numpy(np.asarray(scale).copy()))
        self.register_buffer("src", torch.from_numpy(np.asarray(graph["src"]).copy()))
        self.register_buffer("dst", torch.from_numpy(np.asarray(graph["dst"]).copy()))
        self.register_buffer(
            "degree", torch.from_numpy(np.asarray(graph["degree"], np.float64).copy())
        )
        self.real_parameters = sum(
            p.numel() * (2 if p.is_complex() else 1) for p in self.parameters()
        )
        if self.real_parameters > 100000:
            raise MemoryError("fixed architecture real parameter cap")

    def forward(self, rhs):
        if rhs.ndim == 1:
            rhs = rhs[None, :]
        norm = torch.linalg.vector_norm(rhs, dim=1)
        divisor = torch.where(norm == 0, torch.ones_like(norm), norm)
        canonical = torch.sparse.mm(self.dual, (rhs / divisor[:, None]).T).T
        pieces, offset = [], 0
        for i, (m, n) in enumerate(self.groups):
            part = canonical[:, offset : offset + m * n].reshape(len(rhs), n, m)
            if not self.linear:
                part = torch.cat((part.real, part.imag), dim=-1)
            encoded = self.encoder[i](part)
            pieces.append(encoded if self.linear else torch.tanh(encoded))
            offset += m * n
        hidden = torch.cat(pieces, dim=1)
        for s, neighbor in zip(self.message_self, self.message_neighbor, strict=True):
            average = torch.zeros_like(hidden)
            average.index_add_(1, self.dst, hidden[:, self.src, :])
            average = average / self.degree[None, :, None]
            hidden = s(hidden) + neighbor(average)
            if not self.linear:
                hidden = torch.tanh(hidden)
        pieces, offset = [], 0
        for i, (m, n) in enumerate(self.groups):
            out = self.decoder[i](hidden[:, offset : offset + n])
            if not self.linear:
                out = torch.complex(out[..., :m], out[..., m:])
            pieces.append(out.reshape(len(rhs), m * n))
            offset += n
        canonical_out = torch.cat(pieces, dim=1)
        native = torch.sparse.mm(self.bridge, canonical_out.T).T
        return norm[:, None] * self.scale[None, :] * native


class _OriginalAction(torch.autograd.Function):
    @staticmethod
    def forward(ctx, values, action):
        ctx.action = action
        out = action.apply(values.detach().cpu().numpy().T).T
        return torch.from_numpy(np.ascontiguousarray(out))

    @staticmethod
    def backward(ctx, gradient):
        out = ctx.action.apply(gradient.detach().cpu().numpy().T, adjoint=True).T
        return torch.from_numpy(np.ascontiguousarray(out)), None


def original_loss(model, rhs, action):
    delta = model(rhs)
    error = rhs - _OriginalAction.apply(delta, action)
    den = torch.sum(rhs.abs() ** 2, dim=1)
    if bool(torch.any(den == 0)):
        raise ValueError("zero RHS handled outside the nonzero training loss")
    loss_per_rhs = torch.sum(error.abs() ** 2, dim=1) / (2 * den)
    return loss_per_rhs.mean(), delta, loss_per_rhs


def parameters_hash(model):
    h = hashlib.sha256()
    for name, p in model.named_parameters():
        h.update(name.encode())
        h.update(p.detach().cpu().numpy().tobytes())
    return h.hexdigest()


def group_changes(model, initial):
    out = {}
    for group in ("encoder", "message", "decoder"):
        items = [(n, p) for n, p in model.named_parameters() if n.startswith(group)]
        out[group] = float(
            np.sqrt(
                sum(
                    float(torch.sum(abs(p.detach() - initial[n]) ** 2))
                    for n, p in items
                )
            )
        )
    return out
