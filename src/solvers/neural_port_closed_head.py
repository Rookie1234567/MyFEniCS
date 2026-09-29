"""Exact forty-port elimination restricted to a frozen neural trace space."""

import time

import numpy as np

from src.solvers.neural_linear_head import thin_lstsq


def safe_Hhat(H):
    condition = float(np.linalg.cond(H))
    if not np.isfinite(condition) or condition > 1e10:
        return {
            "status": "PORT_BLOCK_UNSAFE",
            "condition_2": condition if np.isfinite(condition) else None,
        }
    rng = np.random.default_rng(421020)
    errors = []
    for _ in range(3):
        b = rng.normal(size=40) + 1j * rng.normal(size=40)
        x = np.linalg.solve(H, b)
        errors.append(
            float(
                np.linalg.norm(H @ x - b)
                / (np.linalg.norm(H) * np.linalg.norm(x) + np.linalg.norm(b))
            )
        )
    return {
        "status": "PASS" if max(errors) <= 1e-12 else "PORT_BLOCK_UNSAFE",
        "condition_2": condition,
        "small_solve_operation_errors": errors,
        "Hp_used": False,
        "Hhat_size": 40,
        "shift_or_damping": False,
    }


def close_ports(packet, trace):
    zero = np.zeros(40, np.complex128)
    action = packet.apply(np.r_[trace, zero])
    began = time.perf_counter()
    alpha = np.linalg.solve(
        packet.a["Hhat"], packet.a["b"][packet.nt :] - action[packet.nt :]
    )
    return np.r_[trace, alpha], time.perf_counter() - began


def closed_trace_gradient(packet, z):
    from src.solvers.neural_trace import residual_gradient

    loss, residual, gradient = residual_gradient(
        packet.apply, lambda x: packet.apply(x, adjoint=True), z, packet.a["b"]
    )
    began = time.perf_counter()
    dual = np.linalg.solve(packet.a["Hhat"].conj().T, gradient[packet.nt :])
    small_seconds = time.perf_counter() - began
    # Original F^H, retaining its actual negative extraction sign.
    correction = packet.apply(
        np.r_[np.zeros(packet.nt, np.complex128), dual], adjoint=True
    )[: packet.nt]
    return loss, residual, gradient[: packet.nt] - correction, small_seconds


def real_port_algebra(packet, columns):
    nt = packet.nt
    H = packet.a["Hhat"]
    columns[:nt]
    checks = safe_Hhat(H)
    if checks["status"] != "PASS":
        return checks
    rng = np.random.default_rng(421021)
    pairs = []
    for _ in range(3):
        trace = rng.normal(size=nt) + 1j * rng.normal(size=nt)
        alpha = rng.normal(size=40) + 1j * rng.normal(size=40)
        local = packet.apply(np.r_[trace, np.zeros(40, np.complex128)])
        full = packet.apply(np.r_[trace, alpha])
        predicted = local + columns @ alpha
        pairs.append(
            float(
                np.linalg.norm(full - predicted)
                / (np.linalg.norm(local) + np.linalg.norm(columns @ alpha))
            )
        )
    pair_H = float(np.linalg.norm(columns[nt:] - H) / np.linalg.norm(H))
    # Nonzero closed state and nonzero trace direction, all original rows.
    trace = 0.001 * (rng.normal(size=nt) + 1j * rng.normal(size=nt))
    z, _ = close_ports(packet, trace)
    loss, _, gradient, _ = closed_trace_gradient(packet, z)
    differences = []
    for direction_id in range(3):
        direction = rng.normal(size=nt) + 1j * rng.normal(size=nt)
        direction /= np.linalg.norm(direction)
        exact = float(np.vdot(gradient, direction).real)
        for h in (1e-4, 1e-5, 1e-6):
            losses = []
            for sign in (1, -1):
                trial, _ = close_ports(packet, trace + sign * h * direction)
                r = packet.a["b"] - packet.apply(trial)
                losses.append(float(np.vdot(r, r).real / (2 * packet.bnorm**2)))
            observed = (losses[0] - losses[1]) / (2 * h)
            error = abs(observed - exact)
            passed = (
                error <= 1e-10 if abs(exact) <= 1e-10 else error / abs(exact) <= 1e-5
            )
            differences.append(
                {
                    "direction_id": direction_id,
                    "h": h,
                    "analytic": exact,
                    "finite_difference": observed,
                    "absolute_error": error,
                    "relative_error": None
                    if abs(exact) <= 1e-10
                    else error / abs(exact),
                    "passed": passed,
                }
            )
    good = (
        max(pairs) <= 1e-10
        and pair_H <= 1e-10
        and all(
            any(
                item["passed"]
                for item in differences
                if item["direction_id"] == direction_id
            )
            for direction_id in range(3)
        )
    )
    checks.update(
        status="PASS" if good else "PORT_ALGEBRA_OR_GRADIENT_FAILED",
        full_S_reassembly_operation_errors=pairs,
        Hhat_port_column_pair=pair_H,
        gradient_nonzero_norm=float(np.linalg.norm(gradient)),
        true_original_gradient_fd=differences,
        initial_loss=loss,
        gradient_uses_F_adjoint_with_original_sign=True,
    )
    return checks


def solve_closed_head(packet, P, W, gamma0, *, heartbeat=None):
    nt = packet.nt
    H = packet.a["Hhat"]
    head = P.shape[1]
    C = W[:nt, head:]
    F_P = W[nt:, :head]
    began = time.perf_counter()
    H_F = np.linalg.solve(H, F_P)
    H_b = np.linalg.solve(H, packet.a["b"][nt:])
    small_seconds = time.perf_counter() - began
    barW = np.array(W[:nt, :head], order="F", copy=True)
    barW -= C @ H_F
    barb = packet.a["b"][:nt] - C @ H_b
    r0 = barb - barW @ gamma0
    if heartbeat is not None:
        heartbeat("closed_head_gelsd", shape=list(barW.shape))
    delta, ls = thin_lstsq(barW, r0)
    gamma = gamma0 + delta
    residual = barb - barW @ gamma
    if np.linalg.norm(residual) > np.linalg.norm(r0) + 1e-12 * max(
        np.linalg.norm(r0), 1
    ):
        gamma = gamma0.copy()
        ls.update(status="HEAD_LS_NO_DESCENT", zero_increment_retained=True)
    else:
        ls.update(status="HEAD_SOLVED", zero_increment_retained=False)
    trace = P @ gamma
    # Use the actual original action for final port closure, independently of
    # the cached F P expression used in the thin solve.
    z, extra_seconds = close_ports(packet, trace)
    ls.update(
        port_small_solve_seconds=small_seconds + extra_seconds,
        port_block="original condensed Hhat, not Hp",
        all_ports_retained=40,
        exact_port_elimination=True,
        full_K_minus_C_Hinv_F_constructed=False,
        closed_baseline_loss=float(np.vdot(r0, r0).real / (2 * packet.bnorm**2)),
    )
    del barW, H_F
    return gamma, z, ls
