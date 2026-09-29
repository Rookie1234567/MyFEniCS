"""CPU-only real hidden coordinates and scalar-envelope VJP for V11."""

import numpy as np

from src.solvers.neural_linear_head_torch import assign_head
from src.solvers.neural_trace_checks import assign, parameters

HIDDEN_REAL_PARAMETERS = 8576


def hidden_vector(model):
    vector = parameters(model)
    if vector.shape != (11696,):
        raise ValueError("frozen 3x64, eight-carrier real parameter inventory changed")
    return vector[:HIDDEN_REAL_PARAMETERS].copy()


def set_hidden(model, hidden):
    hidden = np.asarray(hidden, dtype=np.float64)
    if hidden.shape != (HIDDEN_REAL_PARAMETERS,) or not np.isfinite(hidden).all():
        raise ValueError("reviewed hidden-only real vector required")
    vector = parameters(model)
    vector[:HIDDEN_REAL_PARAMETERS] = hidden
    vector[HIDDEN_REAL_PARAMETERS:] = 0
    assign(model, vector)


def actual_trace(model, cache, gamma):
    assign_head(model, gamma)
    trace = cache.forward(model)
    if trace.dtype != np.complex128 or not np.isfinite(trace).all():
        raise ValueError("nonfinite actual complex128 neural trace")
    return trace


def envelope_gradient(cache, model, ports, bar_residual, bnorm):
    """At a stationary head, one exact bar-S adjoint and chunked Torch VJP."""
    dual = ports.adjoint(bar_residual)
    full = -cache.vjp(model, dual) / bnorm**2
    if full.shape != (11696,) or not np.isfinite(full).all():
        raise ValueError("nonfinite full network VJP")
    return full[:HIDDEN_REAL_PARAMETERS].copy(), {
        "head_partial_gradient_norm_diagnostic": float(np.linalg.norm(full[HIDDEN_REAL_PARAMETERS:])),
        "hidden_gradient_norm": float(np.linalg.norm(full[:HIDDEN_REAL_PARAMETERS])),
        "adjoint_trace_norm": float(np.linalg.norm(dual)),
        "scalar_envelope_only": True,
        "QR_SVD_autograd_graph": False,
        "Hhat_conjugate_transpose_chain_included": True,
    }


def fixed_directions(gradient):
    directions = []
    for seed in (421111, 421112):
        rng = np.random.default_rng(seed)
        value = rng.standard_normal(HIDDEN_REAL_PARAMETERS)
        value /= np.linalg.norm(value)
        directions.append((str(seed), value))
    if np.linalg.norm(gradient) > 1e-14:
        directions.append(("analytic_gradient", gradient / np.linalg.norm(gradient)))
    else:
        rng = np.random.default_rng(421113)
        value = rng.standard_normal(HIDDEN_REAL_PARAMETERS)
        value /= np.linalg.norm(value)
        directions.append(("421113_nearzero_fallback", value))
    return directions
