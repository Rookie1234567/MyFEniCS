"""Bounded complex thin least squares and exact small port closure.

There is no global operator matrix, normal equation, or fallback inverse here.
SciPy is imported only in the already qualified non-ML environment.
"""

import time

import numpy as np

COND = 1e-12


def thin_capacity(rows, columns, trace_rows, head_columns, packet_bytes, cache_bytes):
    p_bytes = trace_rows * head_columns * 16
    w_bytes = rows * columns * 16
    # Include original P/W, LAPACK input/copies, divide-and-conquer workspace,
    # singular vectors/small work, both process runtimes and packet copies.
    upper = p_bytes + 6 * w_bytes + 8 * columns**2 * 16
    upper += 3 * packet_bytes + cache_bytes + 2 * 2**30
    if upper > 8 * 2**30:
        raise ValueError("thin LS conservative resident plan exceeds 8GiB")
    return {
        "P_payload_bytes": p_bytes,
        "W_payload_bytes": w_bytes,
        "conservative_resident_plan_bytes": upper,
        "resident_planning_cap_bytes": 8 * 2**30,
        "normal_matrix_constructed": False,
        "global_operator_constructed": False,
    }


def thin_lstsq(matrix, rhs):
    from scipy.linalg import lstsq
    from scipy.linalg.lapack import get_lapack_funcs

    if matrix.ndim != 2 or rhs.shape != (matrix.shape[0],):
        raise ValueError("one explicit thin LS inventory required")
    if not np.isfinite(matrix).all() or not np.isfinite(rhs).all():
        raise ValueError("nonfinite thin least squares input")
    # Query the installed LAPACK implementation BEFORE its main allocation.
    query = get_lapack_funcs("gelsd_lwork", (matrix,))
    work, rwork, iwork, info = query(*matrix.shape, 1, cond=COND)
    if info:
        raise ValueError("installed gelsd workspace query failed")
    workspace = int(work.real) * 16 + int(rwork) * 8 + int(iwork) * 4
    if workspace + 3 * matrix.nbytes > 6 * 2**30:
        raise ValueError("gelsd actual workspace exceeds reviewed thin plan")
    started = time.perf_counter()
    coefficients, _, rank, singular = lstsq(
        matrix,
        rhs,
        cond=COND,
        lapack_driver="gelsd",
        check_finite=False,
        overwrite_a=False,
        overwrite_b=False,
    )
    seconds = time.perf_counter() - started
    residual = rhs - matrix @ coefficients
    first_order = matrix.conj().T @ residual
    if not np.isfinite(coefficients).all():
        raise ValueError("nonfinite thin least squares output")
    kept, dropped = singular[:rank], singular[rank:]

    def extrema(values):
        return None if not len(values) else [float(values.min()), float(values.max())]

    return coefficients, {
        "lapack_driver": "gelsd",
        "fixed_cond": COND,
        "effective_rank": int(rank),
        "columns": matrix.shape[1],
        "rows": matrix.shape[0],
        "retained_singular_range": extrema(kept),
        "dropped_singular_range": extrema(dropped),
        "singular_max": float(singular[0]),
        "lapack_workspace_bytes": workspace,
        "least_squares_seconds": seconds,
        "coefficient_norm": float(np.linalg.norm(coefficients)),
        "explicit_residual_norm": float(np.linalg.norm(residual)),
        "full_untruncated_first_order_norm": float(np.linalg.norm(first_order)),
        "full_untruncated_first_order_relative": float(
            np.linalg.norm(first_order)
            / max(
                np.linalg.norm(matrix) * np.linalg.norm(residual), np.finfo(float).tiny
            )
        ),
        "exact_full_space_optimum_claimed": bool(rank == matrix.shape[1]),
        "residual_correction_count": 0,
        "normal_matrix_constructed": False,
        "coordinate_scaling": "none; identical B1/B0 physical coefficient coordinates",
        "zero_column_indices": np.flatnonzero(
            np.linalg.norm(matrix, axis=0) == 0
        ).tolist(),
    }


def port_closure_checks(H, apply, nt, rhs, seed=421010):
    if H.shape != (40, 40):
        raise ValueError("all original forty Hhat ports required")
    condition = float(np.linalg.cond(H))
    if not np.isfinite(condition) or condition > 1e10:
        return {"status": "PORT_BLOCK_UNSAFE", "condition_2": condition}, None
    rng = np.random.default_rng(seed)
    solve_errors = []
    for _ in range(3):
        value = rng.normal(size=40) + 1j * rng.normal(size=40)
        solution = np.linalg.solve(H, value)
        scale = np.linalg.norm(H) * np.linalg.norm(solution) + np.linalg.norm(value)
        solve_errors.append(float(np.linalg.norm(H @ solution - value) / scale))
    ports = np.zeros((nt + 40, 40), np.complex128)
    ports[nt:] = np.eye(40)
    columns = np.column_stack([apply(ports[:, j]) for j in range(40)])
    pair = float(np.linalg.norm(columns[nt:] - H) / max(np.linalg.norm(H), 1e-300))
    status = (
        "PASS" if max(solve_errors) <= 1e-12 and pair <= 1e-12 else "PORT_BLOCK_UNSAFE"
    )
    return {
        "status": status,
        "condition_2": condition,
        "small_solve_operation_errors": solve_errors,
        "Hhat_original_port_column_pair": pair,
        "Hp_used": False,
    }, columns


def construct_equation_head(
    packet, P, gamma, alpha, path, *, cached_ports=None, heartbeat=None
):
    """Original S columns in blocks of at most sixteen, then one fixed thin LS."""
    nt, np_ = packet.nt, packet.np
    if P.shape != (nt, 1560) or np_ != 40:
        raise ValueError("reviewed 1560 head and forty port columns required")
    W = np.lib.format.open_memmap(
        path,
        mode="w+",
        dtype=np.complex128,
        shape=(packet.size, 1600),
        fortran_order=True,
    )
    value = np.zeros(packet.size, np.complex128)
    for start in range(0, 1560, 16):
        stop = min(start + 16, 1560)
        for col in range(start, stop):
            value[:nt] = P[:, col]
            W[:, col] = packet.apply(value)
        if heartbeat is not None and (start % 128 == 0 or stop == 1560):
            heartbeat(
                "S_head_columns", completed=stop, total=1600, S_calls=packet.counts["S"]
            )
    if cached_ports is None:
        value[:] = 0
        for col in range(40):
            value[nt:] = 0
            value[nt + col] = 1
            W[:, 1560 + col] = packet.apply(value)
    else:
        if cached_ports.shape != (packet.size, 40):
            raise ValueError("cached forty original S columns shape differs")
        W[:, 1560:] = cached_ports
    W.flush()
    baseline = np.r_[P @ gamma, alpha]
    r0 = packet.a["b"] - packet.apply(baseline)
    if heartbeat is not None:
        heartbeat("thin_gelsd_start", shape=list(W.shape), S_calls=packet.counts["S"])
    delta, record = thin_lstsq(W, r0)
    eta = np.r_[gamma, alpha] + delta
    z = np.r_[P @ eta[:1560], eta[1560:]]
    residual = packet.a["b"] - packet.apply(z)
    old_loss = float(np.vdot(r0, r0).real / (2 * packet.bnorm**2))
    new_loss = float(np.vdot(residual, residual).real / (2 * packet.bnorm**2))
    status = (
        "HEAD_SOLVED"
        if new_loss <= old_loss + 1e-12 * max(1.0, old_loss)
        else "HEAD_LS_NO_DESCENT"
    )
    if status != "HEAD_SOLVED":
        eta, z, new_loss = np.r_[gamma, alpha], baseline, old_loss
    record.update(
        status=status,
        baseline_loss=old_loss,
        final_loss=new_loss,
        head_coefficients_norm=float(np.linalg.norm(eta[:1560])),
        port_coefficients_norm=float(np.linalg.norm(eta[1560:])),
        zero_increment_retained=status != "HEAD_SOLVED",
        column_equivalent_S_calls=1560 + (40 if cached_ports is None else 0),
    )
    return eta, z, record, W
