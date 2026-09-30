"""Fixed-complex-head partial derivative and bounded hidden-only descent.

This is deliberately not a variable-projection/envelope derivative.  Every
function value uses the original action and exact 40-port closure; the head is
reassigned after each hidden assignment because set_hidden zeros it.
"""

from __future__ import annotations

import numpy as np

from src.solvers.neural_fe_action_packet import array_hash


def actual_loss(packet, ports, trace, rhs):
    """Return original reduced loss and its exact closed trace/port state."""
    z, action_t = ports.closed(trace, rhs)
    alpha = z[packet.nt:]
    full_action = action_t + ports.columns @ alpha
    residual = rhs - full_action
    bar_r = ports.reduced_rhs(rhs) - (action_t[:packet.nt] - ports.C @
                                           np.linalg.solve(ports.H, action_t[packet.nt:]))
    scale = float(np.linalg.norm(rhs))
    if scale == 0 or not np.isfinite(residual).all() or not np.isfinite(bar_r).all():
        raise ValueError("nonfinite or zero-RHS actual fixed-head evaluation")
    loss = float(np.vdot(bar_r, bar_r).real / (2 * scale**2))
    return dict(loss=loss, z=z, trace=trace, bar_residual=bar_r,
                full_residual_relative=float(np.linalg.norm(residual) / scale),
                port_relative=float(np.linalg.norm(residual[packet.nt:]) / scale),
                port_absolute=float(np.linalg.norm(residual[packet.nt:])),
                port_coefficients=alpha)


class FixedHeadObjective:
    """Actual Torch/Nedelec forward with a head frozen throughout a block."""

    def __init__(self, packet, ports, model, cache, rhs):
        self.packet, self.ports, self.model, self.cache = packet, ports, model, cache
        self.rhs = np.asarray(rhs, np.complex128)
        if self.rhs.shape != (packet.size,) or np.linalg.norm(self.rhs) == 0:
            raise ValueError("complete nonzero original RHS required")
        self.bnorm = float(np.linalg.norm(self.rhs))

    def assign(self, hidden, gamma):
        from src.solvers.neural_linear_head_torch import assign_head, head_coefficients
        from src.solvers.stable_head_varpro_torch import set_hidden

        gamma = np.asarray(gamma, np.complex128)
        if gamma.shape != (1560,) or not np.isfinite(gamma).all():
            raise ValueError("complete finite frozen head required")
        before = array_hash(gamma)
        set_hidden(self.model, hidden)
        assign_head(self.model, gamma)
        actual = head_coefficients(self.model)
        if array_hash(actual) != before:
            raise ValueError("fixed gamma changed after hidden assignment")
        return before

    def evaluate(self, hidden, gamma):
        head_hash = self.assign(hidden, gamma)
        trace = self.cache.forward(self.model)
        result = actual_loss(self.packet, self.ports, trace, self.rhs)
        result["hidden_hash"] = array_hash(np.asarray(hidden, np.float64))
        result["gamma_hash"] = head_hash
        return result

    def gradient(self, result):
        """Ordinary partial gradient for fixed gamma, including Hhat^H chain."""
        dual = self.ports.adjoint(result["bar_residual"])
        full = -self.cache.vjp(self.model, dual) / self.bnorm**2
        if full.shape != (11696,) or not np.isfinite(full).all():
            raise ValueError("nonfinite fixed-head VJP")
        return full[:8576].copy(), dict(
            derivative_kind="FIXED_HEAD_PARTIAL_GRADIENT",
            head_partial_norm=float(np.linalg.norm(full[8576:])),
            hidden_norm=float(np.linalg.norm(full[:8576])),
            adjoint_trace_norm=float(np.linalg.norm(dual)),
            Hhat_conjugate_transpose_chain_included=True,
            QR_SVD_autograd_graph=False,
        )


def resolution(losses):
    values = [float(value) for value in losses]
    return max(max(values) - min(values),
               100 * np.finfo(np.float64).eps * max(1.0, max(map(abs, values))))


def trial_steps(hidden, direction):
    size = float(np.linalg.norm(direction))
    if size == 0 or not np.isfinite(size):
        raise ValueError("finite nonzero hidden descent direction required")
    first = min(1.0, 1e-4 * max(1.0, np.linalg.norm(hidden)) / size)
    return [first * 4.0 ** -j for j in range(8)]


def armijo_accept(current, trial, alpha, directional_derivative, delta_eval):
    margin = max(1e-12, 20 * delta_eval)
    return (np.isfinite(trial) and directional_derivative < 0 and
            trial <= current + 1e-4 * alpha * directional_derivative - margin)


def qualified_audit(audit):
    """Identity/closure of an accepted trial; equation convergence is separate."""
    keys = ("recovery_relative", "schur_original_identity_operation_relative",
            "port_full_rhs_relative", "port_operation_relative")
    return (all(np.isfinite(audit[key]) for key in keys)
            and audit["recovery_relative"] <= 1e-10
            and audit["schur_original_identity_operation_relative"] <= 1e-10
            and audit["port_full_rhs_relative"] <= 1e-6
            and audit["port_operation_relative"] <= 1e-6
            and audit["slave_storage_max"] == 0)
