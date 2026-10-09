"""Fixed neural-column feasibility, using only small coefficient factorizations.

This opt-in audit never changes waves, creates an FE inverse or solves G.
Reference data is an argument only to the explicitly labelled oracle.
"""

from time import perf_counter

import numpy as np
from scipy import linalg

from src.solvers.feinn_gqr import GramColumns, project, squared_norm
from src.solvers.neural_wave_backfit import SmallSVDSolve
from src.solvers.neural_wave_block import compensated_columns


def relative(x, y):
    return float(np.linalg.norm(x - y) / max(np.linalg.norm(y), 1e-300))


class StreamingGram(GramColumns):
    """Bound actual sparse action to eight columns, with complete accounting."""

    def __call__(self, x, role):
        if x.ndim == 1:
            return super().__call__(x, role)
        result = np.empty_like(x, dtype=np.complex128)
        for first in range(0, x.shape[1], 8):
            result[:, first : first + 8] = super().__call__(
                x[:, first : first + 8], role
            )
        return result


def original_readout(U, Q, R, f, apply):
    """SVD of the saved small R, independent original-A residual afterward."""
    if U.shape != Q.shape or R.shape != (U.shape[1], U.shape[1]):
        raise ValueError("FROZEN_COLUMN_QR_SHAPE")
    solver = SmallSVDSolve(R, 1e-12)
    a = solver.solve(Q.conj().T @ f)
    c = compensated_columns(U, a)
    r = f - apply(c)
    predicted = f - Q @ (R @ a)
    bnorm = float(np.linalg.norm(f))
    correlations = R.conj().T @ (Q.conj().T @ r)
    scales = np.linalg.norm(R, axis=0)
    normalized = correlations / np.where(scales > 0, scales, 1)
    orth = float(np.linalg.norm(Q.conj().T @ Q - np.eye(R.shape[0])))
    pair = float(np.linalg.norm(r - predicted) / bnorm)
    stationarity = float(np.linalg.norm(normalized) / bnorm)
    singular = solver.singular
    reliable = orth <= 1e-9 and pair <= 1e-10 and stationarity <= 1e-9
    return dict(a=a, c=c, r=r), dict(
        original_columns=U.shape[1],
        retained_rank=solver.rank,
        full_column_rank=solver.rank == U.shape[1],
        SVD_rcond=1e-12,
        singular_values=singular.tolist(),
        column_scales=scales.tolist(),
        QR_orthogonality_F=orth,
        original_small_action_pair_relative=pair,
        normalized_first_order_optimality=stationarity,
        native_relative=float(np.linalg.norm(r) / bnorm),
        coefficient_norm=float(np.linalg.norm(a)),
        coefficient_max=float(np.max(abs(a), initial=0)),
        floating_numerical_qualified=reliable,
        conclusion=(
            "FULL_SPACE_NUMERICAL_MINIMUM"
            if reliable and solver.rank == U.shape[1]
            else "RANK_OR_OPTIMALITY_UNRESOLVED"
        ),
        truncated_minimum_is_full_space_upper_bound=True,
        exact_interval_certificate=False,
        global_FE_inverse_count=0,
        Gram_inverse_count=0,
        nonlinear_training_count=0,
    )


def field_oracle(U, reference, G, *, deadline, heartbeat=lambda *_: None):
    """A single fixed G-QR/SVD projection; no label-selected basis or cutoff."""
    start = perf_counter()
    action = StreamingGram(G, limit=100000, deadline=deadline)
    arrays, stats = project(U, reference, reference, action, heartbeat, block_columns=8)
    a = arrays["delta_a"]
    c = compensated_columns(U, a)
    e = reference - c
    Ge = action(e, "actual_coefficient_field_error")
    dref = squared_norm(reference, action(reference, "reference_energy_final"))
    V = arrays["Q_eff"]
    GV = action(V, "small_M_qualification")
    M = V.conj().T @ GV
    rho = float(np.linalg.norm(M - np.eye(M.shape[0])))
    s = V.conj().T @ Ge
    energy = squared_norm(e, Ge)
    gap_bound = float(np.vdot(s, s).real / (1 - rho)) if rho < 1 else None
    gap_exact = (
        float(np.vdot(s, linalg.solve(M, s, assume_a="her")).real) if rho < 1 else None
    )
    ideal = arrays["delta_ideal"]
    map_pair = relative(c, ideal)
    rank = stats["retained_rank"]
    qualified = bool(
        rho <= 1e-9
        and map_pair <= 1e-10
        and stats["retained_optimality"] <= 1e-9
        and stats["normalized_QR_G_F_relative"] <= 1e-10
    )
    full = rank == U.shape[1] and not stats["QR_discarded_columns"]
    lower = (
        np.sqrt(max(0.0, energy - gap_bound) / dref) if gap_bound is not None else None
    )
    upper = float(np.sqrt(energy / dref))
    arrays.update(a=a, c=c, error=e, small_M=M, stationarity=s)
    stats.update(
        actual_E_G=upper,
        reference_G_energy=dref,
        actual_error_G_energy=energy,
        small_M_orthogonality_F=rho,
        actual_U_amplitude_pair_relative=map_pair,
        optimum_gap_G_energy_upper=gap_bound,
        optimum_gap_G_energy_small_M=gap_exact,
        numerical_optimum_E_G_lower=lower,
        numerical_optimum_E_G_upper=upper,
        full_column_space_retained=full,
        floating_numerical_qualified=qualified,
        exact_interval_certificate=False,
        field_precision_conclusion=(
            "FROZEN_FULL_SPACE_FIELD_THRESHOLD_EXCLUDED_NUMERICALLY"
            if full and qualified and lower is not None and lower > 1e-4 + 1e-8
            else "INCONCLUSIVE"
        ),
        G_columns=action.count,
        G_by_role=action.by_role,
        G_seconds_nested=action.seconds,
        wall_seconds=perf_counter() - start,
        streaming_columns_max=8,
        global_G_factor_count=0,
        Gsolve_count=0,
    )
    return arrays, stats
