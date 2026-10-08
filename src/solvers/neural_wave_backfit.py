"""Opt-in fixed-capacity complex wave variable projection, never an FE inverse.

The inactive complement excludes the active block and is prepared once per
visit. The old raw-to-retained amplitude map is fixed throughout that visit.
"""

from dataclasses import dataclass
from time import perf_counter

import numpy as np
from scipy import linalg

from src.solvers.neural_wave_subspace import conjugate_product


class TrialRejected(ArithmeticError):
    pass


class CompleteTrialLimit(Exception):
    pass


class SmallSVDSolve:
    def __init__(self, matrix, rcond=1e-12):
        self.left, self.singular, self.right = linalg.svd(
            matrix, full_matrices=False, check_finite=True
        )
        self.keep = self.singular > (
            rcond * self.singular[0] if len(self.singular) else 0
        )
        self.rank = int(self.keep.sum())

    def solve(self, rhs):
        return self.right[self.keep].conj().T @ (
            (self.left[:, self.keep].conj().T @ rhs) / self.singular[self.keep]
        )

    def range_product(self, rhs):
        if self.rank == len(self.singular):
            return rhs
        left = self.left[:, self.keep]
        return left @ (left.conj().T @ rhs)


@dataclass
class BackfitTrial:
    q: np.ndarray
    columns: np.ndarray
    applied: np.ndarray
    amplitudes: np.ndarray
    c: np.ndarray
    r: np.ndarray
    objective: float
    gradient: np.ndarray | None
    pairing: float
    active_rank: int
    stationarity: float


class InactiveComplement:
    def __init__(self, action, U, Q, R, first, last, *, rcond=1e-12):
        if not 0 <= first < last <= U.shape[1] or U.shape != Q.shape:
            raise ValueError("ACTIVE_BLOCK_LAYOUT_REQUIRED")
        self.action, self.U, self.first, self.last = action, U, first, last
        self.rcond, self.m = rcond, U.shape[1]
        self.indices = np.r_[np.arange(first), np.arange(last, self.m)]
        started = perf_counter()
        # qr_delete works in original column order, not a pivoted block order.
        self.Q, self.R = linalg.qr_delete(
            np.array(Q, order="F", copy=True),
            np.array(R, order="F", copy=True),
            first,
            p=last - first,
            which="col",
            overwrite_qr=True,
            check_finite=True,
        )
        self.solver = SmallSVDSolve(self.R, rcond)
        self.r_F = self.project(action.f)
        self.setup_seconds = perf_counter() - started

    def project(self, values):
        result = np.array(values, dtype=np.complex128, copy=True)
        # Two passes; do not build an N by N projector or a second large Q_eff.
        for _ in range(2):
            result -= self.Q @ self.solver.range_product(
                conjugate_product(self.Q, result)
            )
        return result

    def trial(self, moments, patch, q, amplitude_map, *, gradient):
        raw = moments.columns(patch, q)
        columns = raw @ amplitude_map
        if columns.shape[1] != self.last - self.first:
            raise ValueError("FIXED_RETAINED_CAPACITY_VIOLATED")
        applied = np.column_stack(
            [self.action.apply(columns[:, j]) for j in range(columns.shape[1])]
        )
        return self.solve_columns(
            q, columns, applied, moments, patch, amplitude_map, gradient=gradient
        )

    def solve_columns(
        self,
        q,
        columns,
        applied,
        moments=None,
        patch=None,
        amplitude_map=None,
        *,
        gradient=False,
    ):
        Z = self.project(applied)
        zq, zr, pivot = linalg.qr(Z, mode="economic", pivoting=True)
        zs = SmallSVDSolve(zr, self.rcond)
        b = np.empty(Z.shape[1], np.complex128)
        b[pivot] = zs.solve(conjugate_product(zq, self.r_F))
        rhs = self.action.f - applied @ b
        a_F = self.solver.solve(conjugate_product(self.Q, rhs))
        amplitudes = np.empty(self.m, np.complex128)
        amplitudes[self.indices], amplitudes[self.first : self.last] = a_F, b
        # Retain original inactive order. Temporarily insert only the small
        # activity, never copy the full inactive U for each objective.
        c = np.zeros(self.action.size, np.complex128)
        correction = np.zeros_like(c)
        for first in range(0, self.m, 32):
            last = min(first + 32, self.m)
            section = self.U[:, first:last]
            if first < self.last and last > self.first:
                section = section.copy()
                lo, hi = max(first, self.first), min(last, self.last)
                section[:, lo - first : hi - first] = columns[
                    :, lo - self.first : hi - self.first
                ]
            value = section @ amplitudes[first:last]
            new = c + value
            correction += np.where(
                abs(c) >= abs(value), (c - new) + value, (value - new) + c
            )
            c = new
        c += correction
        r = self.action.f - self.action.apply(c)
        predicted = rhs - self.Q @ (self.R @ a_F)
        pairing = float(np.linalg.norm(r - predicted) / self.action.bnorm)
        stationarity = float(
            np.linalg.norm(conjugate_product(zq, self.r_F - Z @ b)) / self.action.bnorm
        )
        if not np.isfinite(r).all() or pairing > 1e-10:
            raise TrialRejected("REDUCED_COMPLETE_ORIGINAL_ACTION_PAIR_FAILED")
        grad = None
        if gradient:
            cotangent = -self.action.apply(r, adjoint=True) / self.action.bnorm**2
            grad, _ = moments.vjp(patch, q, amplitude_map @ b, cotangent)
        return BackfitTrial(
            np.array(q, copy=True),
            columns,
            applied,
            amplitudes,
            c,
            r,
            float(np.vdot(r, r).real / (2 * self.action.bnorm**2)),
            grad,
            pairing,
            zs.rank,
            stationarity,
        )


def insert_block_qr(complement, applied):
    """Insert in original slot order; no refactor of the inactive complement."""
    return linalg.qr_insert(
        np.array(complement.Q, order="F", copy=True),
        np.array(complement.R, order="F", copy=True),
        np.array(applied, order="F", copy=True),
        complement.first,
        which="col",
        rcond=1e-12,
        overwrite_qru=True,
        check_finite=True,
    )


def commit_replacement(space, block, complement, trial):
    """Build all trial-dependent objects before changing a committed state."""
    before = float(np.linalg.norm(space.r) / space.action.bnorm)
    after = float(np.linalg.norm(trial.r) / space.action.bnorm)
    if after > before + 1e-10 or trial.pairing > 1e-10:
        raise TrialRejected("COMPLETE_RESIDUAL_NONINCREASE_REQUIRED")
    q, r = insert_block_qr(complement, trial.applied)
    predicted = space.action.f - q @ (r @ trial.amplitudes)
    pair = float(np.linalg.norm(trial.r - predicted) / space.action.bnorm)
    if pair > 1e-10:
        raise TrialRejected("INSERTED_QR_COMPLETE_ACTION_PAIR_FAILED")
    # One transactional in-memory swap. Persistence must finish before the
    # corresponding committed event is emitted by the caller.
    space.U[:, block["start"] : block["stop"]] = trial.columns
    space.Q, space.R = q, r
    space.a, space.c, space.r = trial.amplitudes, trial.c, trial.r
    block["wave_q"] = trial.q.copy()
    return dict(before_native=before, after_native=after, pair_relative=pair)


def normalized_block_gradients(action, moments, space, blocks, k0):
    cotangent = -action.apply(space.r, adjoint=True) / action.bnorm**2
    values = []
    for block in blocks:
        p = block["amplitude_map"] @ space.a[block["start"] : block["stop"]]
        g, _ = moments.vjp(block["patch"], block["wave_q"], p, cotangent)
        values.append(float(np.linalg.norm(k0 * g) / np.sqrt(max(1, g.size))))
    return values


def select_active_round(scores, blocks, cursor):
    ordered = sorted(range(len(blocks)), key=lambda i: (-scores[i], i))
    selected = ordered[:8]
    rotation = sorted(
        range(len(blocks)),
        key=lambda i: (
            -1 if blocks[i]["patch"].kind == "global" else blocks[i]["patch"].level,
            i,
        ),
    )
    inspected = 0
    while len(selected) < min(16, len(blocks)):
        i = rotation[(cursor + inspected) % len(rotation)]
        if i not in selected:
            selected.append(i)
        inspected += 1
    return selected, (cursor + inspected) % len(rotation)


def optimize_active(
    evaluate,
    q0,
    k0,
    route,
    *,
    round_id,
    block_id,
    visit_id,
    max_evaluations=32,
    seed_trial=None,
):
    from scipy.optimize import minimize

    calls, best = [], [seed_trial]
    rank = seed_trial.active_rank if seed_trial is not None else None

    def objective(flat):
        if len(calls) >= max_evaluations:
            raise CompleteTrialLimit
        try:
            trial = evaluate(flat.reshape(q0.shape) * k0, route == "learned")
        except TrialRejected as error:
            calls.append(dict(complete=True, accepted=False, failure=str(error)))
            raise
        calls.append(
            dict(
                objective=trial.objective,
                gradient_norm=float(np.linalg.norm(trial.gradient * k0))
                if trial.gradient is not None
                else None,
                q=trial.q.tolist(),
                active_rank=trial.active_rank,
                pairing=trial.pairing,
            )
        )
        if rank is not None and trial.active_rank != rank:
            raise TrialRejected("ACTIVE_NUMERICAL_RANK_CHANGED")
        if best[0] is None or trial.objective < best[0].objective:
            best[0] = trial
        return trial.objective, (
            trial.gradient.ravel() * k0 if trial.gradient is not None else None
        )

    status, message, nit = -1, "ACTUAL_EVALUATION_LIMIT", 0
    try:
        if route == "learned":
            result = minimize(
                objective,
                q0.ravel() / k0,
                jac=True,
                method="L-BFGS-B",
                bounds=[(-4.0, 4.0)] * q0.size,
                options=dict(
                    maxiter=20,
                    maxfun=max_evaluations,
                    maxls=12,
                    maxcor=10,
                    ftol=1e-12,
                    gtol=1e-10,
                ),
            )
            status, message, nit = (
                int(result.status),
                str(result.message),
                int(result.nit),
            )
        else:
            delta = (1 / 8, 1 / 16, 1 / 32, 1 / 64)[min(round_id, 3)]
            for j in range(max_evaluations):
                flat = (best[0].q if best[0] is not None else q0).ravel() / k0
                axis = (block_id + visit_id + j // 2) % q0.size
                flat[axis] += (-1 if j % 2 == 0 else 1) * delta
                objective(np.clip(flat, -4, 4))
            status, message = 0, "FIXED_PATTERN_COMPLETE"
    except (CompleteTrialLimit, TrialRejected) as error:
        message = str(error) or type(error).__name__
    return best[0], dict(
        complete_trial_calls=len(calls),
        actual_evaluation_limit=max_evaluations,
        scipy_nit=nit,
        scipy_status=status,
        message=message,
        evaluated_trajectory=calls,
        extra_result_evaluations=0,
        seed_and_zero_audits_counted_separately=True,
    )
