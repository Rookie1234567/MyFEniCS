"""Independent, layerwise FP64 tangents through the unchanged Nedelec map.

No backward, autograd JVP, finite difference, or hidden Jacobian is used here.
The real parameter layout and complex output-head layout remain the originals.
"""

import numpy as np
import torch
import torch.nn.functional as functional


def parameter_direction(hidden, head=None):
    hidden = np.asarray(hidden)
    if np.iscomplexobj(hidden) or hidden.shape != (8576,) or not np.isfinite(hidden).all():
        raise ValueError("hidden tangent must contain 8576 finite REAL parameters")
    head = np.zeros(1560, np.complex128) if head is None else np.asarray(head, np.complex128)
    if head.shape != (1560,) or not np.isfinite(head).all():
        raise ValueError("complete finite complex head tangent required")
    head = head.reshape(8, 3, 65)
    weight = np.stack((head[:, :, 1:].real, head[:, :, 1:].imag), axis=2).reshape(48, 64)
    bias = np.stack((head[:, :, 0].real, head[:, :, 0].imag), axis=2).reshape(48)
    return np.r_[hidden.astype(np.float64), weight.ravel(), bias]


def layerwise_envelopes(model, coordinates, direction):
    """Three explicit tanh recurrences, followed by the linear complex head."""
    direction = torch.as_tensor(direction, dtype=torch.float64)
    if direction.shape != (11696,) or not torch.isfinite(direction).all():
        raise ValueError("original real parameter tangent inventory required")
    value = coordinates
    tangent = torch.zeros_like(value)
    offset = 0
    for index, layer in enumerate(model.envelopes):
        if isinstance(layer, torch.nn.Linear):
            n = layer.weight.numel()
            dw = direction[offset:offset+n].reshape_as(layer.weight)
            offset += n
            db = direction[offset:offset+layer.bias.numel()]
            offset += layer.bias.numel()
            change = functional.linear(value, dw, db) + functional.linear(tangent, layer.weight)
            value = functional.linear(value, layer.weight, layer.bias)
            tangent = change
        elif isinstance(layer, torch.nn.Tanh):
            value = torch.tanh(value)
            tangent = (1 - value.square()) * tangent
        else:
            raise ValueError(f"unreviewed neural layer {index}")
    if offset != 11696:
        raise ValueError("original parameter ordering changed")
    return value, tangent


def moment_tangent(model, cache, hidden, head=None):
    """Both value and tangent enter full q15 Piola/orientation/owner moments."""
    direction = parameter_direction(hidden, head)
    trace = np.empty(cache.active_rows, np.complex128)
    change = np.empty_like(trace)
    points = cache.normalized.shape[1]
    with torch.no_grad():
        for start in range(0, len(cache.cells), 8):
            stop = min(start+8, len(cache.cells))
            width = stop-start
            values, tangents = layerwise_envelopes(
                model, cache.normalized[start:stop].reshape(-1, 3), direction)
            mapped = []
            for envelopes in (values, tangents):
                envelopes = envelopes.reshape(width, points, 8, 3, 2)
                complex_values = torch.complex(envelopes[..., 0], envelopes[..., 1])
                physical = torch.sum(complex_values * cache.phases[start:stop, :, :, None], dim=2)
                pulled = torch.bmm(physical, cache.jacobians[start:stop])
                moments = pulled.transpose(1, 2).reshape(width, -1) @ cache.interpolation.T
                oriented = torch.bmm(cache.transforms[cache.orientation[start:stop]],
                                     moments[:, :, None])[:, :, 0]
                mapped.append(torch.cat([oriented[i, selected]
                              for i, (_, selected) in enumerate(cache.owners[start:stop])]).numpy())
            rows = np.concatenate([owner[0] for owner in cache.owners[start:stop]])
            trace[rows], change[rows] = mapped
    if not np.isfinite(trace).all() or not np.isfinite(change).all():
        raise ValueError("nonfinite layerwise Nedelec tangent")
    return trace, change


def dot_pair(dual, tangent, vjp, direction):
    left = float(np.vdot(dual, tangent).real)
    right = float(np.dot(vjp, direction))
    scale = max(float(np.linalg.norm(dual)*np.linalg.norm(tangent)),
                float(np.linalg.norm(vjp)*np.linalg.norm(direction)), 1e-300)
    terms = np.conj(dual)*tangent
    return dict(left=left, right=right, absolute_difference=abs(left-right),
                operation_scale=scale, operation_relative=abs(left-right)/scale,
                result_relative=abs(left-right)/max(abs(left), abs(right), 1e-300),
                complex_dot_absolute_term_sum=float(np.sum(np.abs(terms))),
                cancellation_ratio=abs(left)/max(float(np.sum(np.abs(terms))), 1e-300))
