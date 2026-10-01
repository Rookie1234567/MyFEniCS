"""Bounded real-parameter JVP through Torch network and complete FE moments.

Only the torch chain is differentiated; no numpy/no_grad forward is used as
a differentiation target. Physical coordinates and phase buffers stay fixed.
"""

from time import perf_counter
import numpy as np
import torch


def direction_dict(model, vector):
    vector = np.asarray(vector, np.float64)
    offset, result = 0, {}
    for name, parameter in model.named_parameters():
        result[name] = torch.as_tensor(
            vector[offset : offset + parameter.numel()].reshape(parameter.shape)
        )
        offset += parameter.numel()
    if offset != vector.size or not np.isfinite(vector).all():
        raise ValueError("FINITE_REAL_PARAMETER_DIRECTION_REQUIRED")
    return result


def analytic_tangent(model, coordinates, direction):
    """Independent explicit MLP chain-rule witness, including fixed phase."""
    x = (coordinates - model.center) / model.half_width
    dx = torch.zeros_like(x)
    for index in (0, 2, 4, 6):
        layer = model.envelopes[index]
        prefix = f"envelopes.{index}."
        dz = (
            dx @ layer.weight.T
            + x @ direction[prefix + "weight"].T
            + direction[prefix + "bias"]
        )
        z = x @ layer.weight.T + layer.bias
        if index != 6:
            x = torch.tanh(z)
            dx = (1 - x * x) * dz
        else:
            x, dx = z, dz
    dx = dx.reshape(-1, 3, 2)
    tangent = torch.complex(dx[..., 0], dx[..., 1])
    if hasattr(model, "phase_k_inc"):
        argument = (coordinates - model.phase_origin) @ model.phase_k_inc
        tangent = (
            torch.complex(torch.cos(argument), torch.sin(argument))[:, None] * tangent
        )
    return tangent


class MomentJacobian:
    def __init__(self, mapping):
        self.mapping = mapping
        self.counts = dict(JVP=0, VJP=0)
        self.costs = dict(JVP=0.0, VJP=0.0)
        self.implementation = "torch.func.jvp/functional_call; <=8 cell blocks"

    def jvp(self, model, vector, batch=8, *, analytic=False):
        if batch not in (1, 8):
            raise ValueError("ONLY_QUALIFIED_BATCH1_8")
        started = perf_counter()
        self.counts["JVP"] += 1
        mapping = self.mapping
        tangents = direction_dict(model, vector)
        base = {n: p.detach() for n, p in model.named_parameters()}
        buffers = {n: b.detach() for n, b in model.named_buffers()}
        out = np.empty(mapping.size, np.complex128)
        for first in range(0, mapping.nc, batch):
            stop = min(first + batch, mapping.nc)
            coordinates = mapping.coordinates[first:stop].reshape(-1, 3)
            if analytic:
                with torch.no_grad():
                    tangent = analytic_tangent(model, coordinates, tangents)
            else:

                def network(parameters):
                    return torch.func.functional_call(
                        model, (parameters, buffers), (coordinates,), strict=True
                    )

                _, tangent = torch.func.jvp(network, (base,), (tangents,))
            values = tangent.reshape(stop - first, -1, 3)
            pulled = torch.einsum("cqa,cab->cqb", values, mapping.jacobians[first:stop])
            moments = (
                pulled.transpose(1, 2).reshape(stop - first, -1)
                @ mapping.interpolation.T
            )
            ids = mapping.packet["orientation_ids"][first:stop]
            oriented = torch.bmm(mapping.transforms[ids], moments[:, :, None])[:, :, 0]
            rows = mapping.packet["owner_rows"][first:stop]
            selected = rows >= 0
            out[rows[selected]] = oriented[torch.as_tensor(selected)].detach().numpy()
        self.costs["JVP"] += perf_counter() - started
        if not np.isfinite(out).all():
            raise ValueError("NONFINITE_COMPLETE_JVP")
        return out

    def vjp(self, model, dual, batch=8):
        start = perf_counter()
        self.counts["VJP"] += 1
        result = self.mapping.vjp(model, dual, batch)
        self.costs["VJP"] += perf_counter() - start
        return result
