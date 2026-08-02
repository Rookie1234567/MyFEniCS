"""Small dense algebra used to qualify the Task036 T0b transfer audit.

This module is deliberately limited to NumPy fixtures.  It does not assemble a
finite-element operator, form a production Hybrid solver, or run a forward PDE.
"""

from __future__ import annotations

import numpy as np


_TAIL_THRESHOLDS = (1.0e-6, 1.0e-8, 1.0e-10)
_RELATIVE_RANK_CUTOFF = 1.0e-10


def complex_gaussian_holdout_multiplier(
    delta_each: float, holdout_count: int
) -> float:
    """Return the frozen circular-complex Gaussian holdout multiplier."""

    delta_each = float(delta_each)
    holdout_count = int(holdout_count)
    if not 0.0 < delta_each < 1.0:
        raise ValueError("delta_each must lie strictly between zero and one")
    if holdout_count <= 0:
        raise ValueError("holdout_count must be positive")
    return float(
        1.0
        / np.sqrt(
            -np.log1p(-(delta_each ** (1.0 / holdout_count)))
        )
    )


def _transfer_blocks(
    system: np.ndarray,
    source: np.ndarray,
    output: np.ndarray,
    direct: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    system = np.asarray(system)
    source = np.asarray(source)
    output = np.asarray(output)
    direct = np.asarray(direct)
    if system.ndim != 2 or system.shape[0] != system.shape[1]:
        raise ValueError("system must be a square matrix")
    if source.ndim != 2 or source.shape[0] != system.shape[0]:
        raise ValueError("source rows must match the system dimension")
    if output.ndim != 2 or output.shape[1] != system.shape[0]:
        raise ValueError("output columns must match the system dimension")
    if direct.shape != (output.shape[0], source.shape[1]):
        raise ValueError("direct must map source coordinates to output coordinates")
    return system, source, output, direct


def _hpd_metric(metric: np.ndarray, dimension: int, name: str) -> np.ndarray:
    metric = np.asarray(metric)
    if metric.shape != (dimension, dimension):
        raise ValueError(f"{name} must have shape ({dimension}, {dimension})")
    if not np.allclose(metric, metric.conj().T, rtol=1.0e-12, atol=1.0e-14):
        raise ValueError(f"{name} must be Hermitian")
    try:
        np.linalg.cholesky(metric)
    except np.linalg.LinAlgError as exc:
        raise ValueError(f"{name} must be positive definite") from exc
    return metric


def _leading_dimension(values: np.ndarray, dimension: int, name: str) -> np.ndarray:
    values = np.asarray(values)
    if values.ndim not in (1, 2) or values.shape[0] != dimension:
        raise ValueError(f"{name} must have leading dimension {dimension}")
    return values


def joint_cauchy_pairing(
    electric_left: np.ndarray,
    traction_left: np.ndarray,
    electric_right: np.ndarray,
    traction_right: np.ndarray,
    mass: np.ndarray,
    *,
    k0: float,
    area: float,
    electric_reference: complex,
) -> complex:
    """Return the dimensionless electric/traction joint-Cauchy pairing."""

    electric_left = np.asarray(electric_left)
    if electric_left.ndim != 1:
        raise ValueError("electric_left must be a vector")
    dimension = electric_left.shape[0]
    traction_left = _leading_dimension(traction_left, dimension, "traction_left")
    electric_right = _leading_dimension(electric_right, dimension, "electric_right")
    traction_right = _leading_dimension(traction_right, dimension, "traction_right")
    if any(
        values.ndim != 1 for values in (traction_left, electric_right, traction_right)
    ):
        raise ValueError("joint-Cauchy coordinates must be vectors")
    mass = _hpd_metric(mass, dimension, "mass")
    k0 = float(k0)
    normalization = float(area) * abs(complex(electric_reference)) ** 2
    if k0 <= 0.0 or normalization <= 0.0:
        raise ValueError("k0, area, and electric_reference must be nonzero")
    riesz_traction_right = np.linalg.solve(mass, traction_right)
    return complex(
        (
            np.vdot(electric_left, mass @ electric_right)
            + k0**-2 * np.vdot(traction_left, riesz_traction_right)
        )
        / normalization
    )


def transfer_action(
    system: np.ndarray,
    source: np.ndarray,
    output: np.ndarray,
    direct: np.ndarray,
    source_coordinates: np.ndarray,
) -> np.ndarray:
    """Apply ``T = output @ solve(system, source) + direct``."""

    system, source, output, direct = _transfer_blocks(system, source, output, direct)
    source_coordinates = _leading_dimension(
        source_coordinates, source.shape[1], "source_coordinates"
    )
    state = np.linalg.solve(system, source @ source_coordinates)
    return output @ state + direct @ source_coordinates


def transfer_weighted_adjoint_action(
    system: np.ndarray,
    source: np.ndarray,
    output: np.ndarray,
    direct: np.ndarray,
    source_metric: np.ndarray,
    output_metric: np.ndarray,
    output_coordinates: np.ndarray,
) -> np.ndarray:
    """Apply the full Hermitian adjoint under the two SPD metrics."""

    system, source, output, direct = _transfer_blocks(system, source, output, direct)
    source_metric = _hpd_metric(source_metric, source.shape[1], "source_metric")
    output_metric = _hpd_metric(output_metric, output.shape[0], "output_metric")
    output_coordinates = _leading_dimension(
        output_coordinates, output.shape[0], "output_coordinates"
    )
    weighted_output = output_metric @ output_coordinates
    adjoint_state = np.linalg.solve(
        system.conj().T,
        output.conj().T @ weighted_output,
    )
    adjoint_load = source.conj().T @ adjoint_state + direct.conj().T @ weighted_output
    return np.linalg.solve(source_metric, adjoint_load)


def bilateral_whiten(
    right: np.ndarray,
    left: np.ndarray,
    metric: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Whiten a full-rank right/left pair so ``left^H G right = I``."""

    right = np.asarray(right)
    left = np.asarray(left)
    if right.ndim != 2 or left.ndim != 2 or right.shape != left.shape:
        raise ValueError("right and left must be matrices with the same shape")
    metric = _hpd_metric(metric, right.shape[0], "metric")
    pair = left.conj().T @ metric @ right
    u, singular_values, vh = np.linalg.svd(pair, full_matrices=False)
    rank_floor = _RELATIVE_RANK_CUTOFF * singular_values[0]
    if singular_values[-1] <= rank_floor:
        raise np.linalg.LinAlgError("right/left metric pairing is rank deficient")
    inverse_roots = singular_values**-0.5
    whitened_right = (right @ vh.conj().T) * inverse_roots
    whitened_left = (left @ u) * inverse_roots
    return whitened_right, whitened_left


def decoder(
    right: np.ndarray,
    left: np.ndarray,
    metric: np.ndarray,
) -> np.ndarray:
    """Return ``solve(left^H G right, left^H G)`` without an inverse."""

    right = np.asarray(right)
    left = np.asarray(left)
    if right.ndim != 2 or left.ndim != 2 or right.shape != left.shape:
        raise ValueError("right and left must be matrices with the same shape")
    metric = _hpd_metric(metric, left.shape[0], "metric")
    weighted_left = left.conj().T @ metric
    pair = weighted_left @ right
    singular_values = np.linalg.svd(pair, compute_uv=False)
    if singular_values[-1] <= _RELATIVE_RANK_CUTOFF * singular_values[0]:
        raise np.linalg.LinAlgError("right/left metric pairing is rank deficient")
    return np.linalg.solve(pair, weighted_left)


def core_projector_action(
    core: np.ndarray,
    metric: np.ndarray,
    values: np.ndarray,
) -> np.ndarray:
    """Apply the ``metric``-orthogonal projector onto ``span(core)``."""

    core = np.asarray(core)
    if core.ndim != 2:
        raise ValueError("core must be a matrix")
    metric = _hpd_metric(metric, core.shape[0], "metric")
    values = _leading_dimension(values, core.shape[0], "values")
    weighted_core = np.linalg.cholesky(metric).conj().T @ core
    core_singular_values = np.linalg.svd(weighted_core, compute_uv=False)
    if core_singular_values[-1] <= _RELATIVE_RANK_CUTOFF * core_singular_values[0]:
        raise np.linalg.LinAlgError("metric-weighted core basis is rank deficient")
    gram = core.conj().T @ metric @ core
    _hpd_metric(gram, core.shape[1], "core Gram matrix")
    coordinates = np.linalg.solve(gram, core.conj().T @ metric @ values)
    return core @ coordinates


def core_complement_action(
    core: np.ndarray,
    metric: np.ndarray,
    values: np.ndarray,
) -> np.ndarray:
    """Apply ``I - Pi_core`` in the joint-Cauchy metric."""

    values = np.asarray(values)
    return values - core_projector_action(core, metric, values)


def singular_tail_summary(singular_values: np.ndarray) -> dict[str, object]:
    """Summarize absolute/relative tails and captured energy by retained rank.

    Both returned arrays are indexed by retained rank from zero through the
    full rank.  Absolute tails retain the input scale; relative tails are
    explicitly divided by the leading singular value.  Captured energy is the
    fraction of squared singular values retained.
    """

    singular_values = np.asarray(singular_values, dtype=float)
    if singular_values.ndim != 1 or singular_values.size == 0:
        raise ValueError("singular_values must be a non-empty vector")
    if not np.all(np.isfinite(singular_values)) or np.any(singular_values < 0.0):
        raise ValueError("singular_values must be finite and nonnegative")
    if np.any(singular_values[1:] > singular_values[:-1]):
        raise ValueError("singular_values must be sorted in descending order")
    total_energy = float(np.sum(singular_values**2))
    if total_energy == 0.0:
        raise ValueError("captured energy is undefined for a zero spectrum")

    absolute_tail = np.concatenate((singular_values, np.zeros(1)))
    relative_tail = absolute_tail / singular_values[0]
    captured_energy = np.concatenate(
        (np.zeros(1), np.cumsum(singular_values**2) / total_energy)
    )
    minimum_absolute_rank = {
        threshold: int(np.count_nonzero(singular_values > threshold))
        for threshold in _TAIL_THRESHOLDS
    }
    relative_singular_values = singular_values / singular_values[0]
    minimum_relative_rank = {
        threshold: int(np.count_nonzero(relative_singular_values > threshold))
        for threshold in _TAIL_THRESHOLDS
    }
    return {
        "absolute_worst_case_tail_by_rank": absolute_tail,
        "relative_worst_case_tail_by_rank": relative_tail,
        "captured_energy_by_rank": captured_energy,
        "minimum_rank_by_absolute_tail": minimum_absolute_rank,
        "minimum_rank_by_relative_tail": minimum_relative_rank,
    }
