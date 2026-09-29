"""Pure complex residual/VJP contract; no inverse, preconditioner or teacher."""

import numpy as np


def residual_gradient(action, adjoint_action, z, rhs):
    rhs = np.asarray(rhs, dtype=np.complex128)
    if not np.isfinite(rhs).all() or np.linalg.norm(rhs) == 0:
        raise ValueError(
            "nonzero finite RHS required; analytic zero handled separately"
        )
    residual = rhs - np.asarray(action(z), dtype=np.complex128)
    scale = float(np.vdot(rhs, rhs).real)
    loss = float(np.vdot(residual, residual).real / (2 * scale))
    gradient = -np.asarray(adjoint_action(residual), dtype=np.complex128) / scale
    if not np.isfinite(residual).all() or not np.isfinite(gradient).all():
        raise ValueError("nonfinite original residual/gradient")
    return loss, residual, gradient


def directional_check(loss, parameters, gradient, directions, steps=(1e-4, 1e-5, 1e-6)):
    """Real parameter derivatives, explicit near-zero absolute tolerance."""
    result = []
    for index, direction in enumerate(directions):
        direction = np.asarray(direction, dtype=np.float64)
        direction = direction / np.linalg.norm(direction)
        exact = float(np.dot(gradient, direction))
        samples = []
        for step in steps:
            observed = (
                loss(parameters + step * direction)
                - loss(parameters - step * direction)
            ) / (2 * step)
            error = abs(observed - exact)
            relative = error / abs(exact) if abs(exact) > 1e-10 else None
            samples.append(
                dict(
                    h=step,
                    finite_difference=observed,
                    absolute_error=error,
                    relative_error=relative,
                    passed=error <= 1e-10 if relative is None else relative <= 1e-5,
                )
            )
        result.append(dict(direction=index, analytic=exact, samples=samples))
    return result


def moment_packet_values(packet, field):
    """Unique master coefficients: Piola pullback -> full moments -> T^-T.

    Shared entities have one native owner. This maps only independent masters;
    the original MPC expands slaves later, without multiplying phases here.
    """
    result = np.empty(int(packet["active_rows"]), dtype=np.complex128)
    reference = packet["reference_points"]
    for cell, rows in enumerate(packet["owner_rows"]):
        selected = rows >= 0
        if not selected.any():
            continue
        jacobian = packet["jacobians"][cell]
        points = packet["origins"][cell] + reference @ jacobian.T
        values = np.asarray(field(points), dtype=np.complex128)
        pulled = values @ jacobian
        moments = packet["interpolation"] @ pulled.T.reshape(-1)
        oriented = packet["transforms"][packet["orientation_ids"][cell]] @ moments
        result[rows[selected]] = oriented[selected]
    return result
