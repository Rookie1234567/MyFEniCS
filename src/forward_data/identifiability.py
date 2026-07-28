"""Task001 geometry-identifiability and configuration-DOE helpers."""

from __future__ import annotations

from itertools import combinations
import math
from typing import Any, Mapping, Sequence

import numpy as np


def central_geometry_jacobian(
    *,
    height_minus: Sequence[float],
    height_plus: Sequence[float],
    width_minus: Sequence[float],
    width_plus: Sequence[float],
    height_span_nm: float = 5.0,
    width_span_nm: float = 1.0,
) -> np.ndarray:
    """Return J=[dy/dh,dy/dw] for one fixed experiment configuration."""

    arrays = [
        np.asarray(value, dtype=float)
        for value in (height_minus, height_plus, width_minus, width_plus)
    ]
    if not arrays[0].ndim == 1 or any(value.shape != arrays[0].shape for value in arrays):
        raise ValueError("central-difference feature vectors must be same-length 1-D arrays")
    if height_span_nm <= 0.0 or width_span_nm <= 0.0:
        raise ValueError("central-difference spans must be positive")
    if not all(np.isfinite(value).all() for value in arrays):
        raise ValueError("central-difference feature vectors must be finite")
    return np.column_stack(
        (
            (arrays[1] - arrays[0]) / height_span_nm,
            (arrays[3] - arrays[2]) / width_span_nm,
        )
    )


def fisher_metrics(
    jacobian: Sequence[Sequence[float]],
    nominal_power: Sequence[float],
    *,
    relative_noise: float = 0.01,
    absolute_power_floor: float = 1.0e-8,
) -> dict[str, Any]:
    """Compute the noise-weighted two-geometry-parameter Fisher diagnostics."""

    jac = np.asarray(jacobian, dtype=float)
    power = np.asarray(nominal_power, dtype=float)
    if jac.ndim != 2 or jac.shape[1] != 2 or power.shape != (jac.shape[0],):
        raise ValueError("expected J shape (channels,2) and one nominal power per channel")
    if relative_noise <= 0.0 or absolute_power_floor <= 0.0:
        raise ValueError("noise assumptions must be positive")
    if not np.isfinite(jac).all() or not np.isfinite(power).all() or np.any(power < 0.0):
        raise ValueError("Jacobian and nominal powers must be finite; power must be nonnegative")
    sigma = np.sqrt((relative_noise * power) ** 2 + absolute_power_floor**2)
    weighted = jac / sigma[:, None]
    singular_values = np.linalg.svd(weighted, compute_uv=False)
    tolerance = (
        max(weighted.shape) * np.finfo(float).eps * singular_values[0]
        if singular_values.size and singular_values[0] > 0.0
        else 0.0
    )
    rank = int(np.count_nonzero(singular_values > tolerance))
    condition = (
        float(singular_values[0] / singular_values[-1])
        if rank == 2 and singular_values[-1] > 0.0
        else math.inf
    )
    fisher = weighted.T @ weighted
    sign, logdet = np.linalg.slogdet(fisher)
    covariance = np.linalg.inv(fisher) if rank == 2 else np.linalg.pinv(fisher)
    denominator = math.sqrt(max(covariance[0, 0] * covariance[1, 1], 0.0))
    rho = float(covariance[0, 1] / denominator) if rank == 2 and denominator else math.nan
    row_information = weighted**2
    totals = np.sum(row_information, axis=0)
    channel_contribution = np.divide(
        row_information,
        totals,
        out=np.zeros_like(row_information),
        where=totals > 0.0,
    )
    return {
        "rank": rank,
        "singular_values": singular_values.tolist(),
        "condition_number": condition,
        "fisher": fisher.tolist(),
        "log_det_fisher": float(logdet) if sign > 0 else -math.inf,
        "covariance": covariance.tolist(),
        "rho_hw": rho,
        "sigma_height_nm": float(math.sqrt(max(covariance[0, 0], 0.0))) if rank == 2 else math.inf,
        "sigma_width_nm": float(math.sqrt(max(covariance[1, 1], 0.0))) if rank == 2 else math.inf,
        "noise_sigma": sigma.tolist(),
        "weighted_jacobian": weighted.tolist(),
        "channel_contribution_height": channel_contribution[:, 0].tolist(),
        "channel_contribution_width": channel_contribution[:, 1].tolist(),
        "relative_noise": relative_noise,
        "absolute_power_floor": absolute_power_floor,
    }


def greedy_channel_indices(
    jacobian: Sequence[Sequence[float]],
    nominal_power: Sequence[float],
    *,
    max_channels: int = 8,
    relative_noise: float = 0.01,
    absolute_power_floor: float = 1.0e-8,
) -> list[int]:
    """Select stable channels by weighted Fisher gain, never by power alone."""

    jac = np.asarray(jacobian, dtype=float)
    power = np.asarray(nominal_power, dtype=float)
    if max_channels < 1 or jac.ndim != 2 or jac.shape[1] != 2 or power.shape != (jac.shape[0],):
        raise ValueError("invalid channel-selection inputs")
    sigma = np.sqrt((relative_noise * power) ** 2 + absolute_power_floor**2)
    weighted = jac / sigma[:, None]
    remaining = set(range(jac.shape[0]))
    selected: list[int] = []
    fisher = np.zeros((2, 2), dtype=float)
    scale = max(float(np.max(np.linalg.norm(weighted, axis=1))) ** 2, 1.0)
    regularizer = np.eye(2) * np.finfo(float).eps * scale
    while remaining and len(selected) < max_channels:
        def score(index: int) -> tuple[float, float, int]:
            candidate = fisher + np.outer(weighted[index], weighted[index])
            _, logdet = np.linalg.slogdet(candidate + regularizer)
            return float(logdet), float(np.trace(candidate)), -index

        best = max(remaining, key=score)
        selected.append(best)
        remaining.remove(best)
        fisher += np.outer(weighted[best], weighted[best])
    return selected


def rank_configuration_subsets(
    configurations: Mapping[str, Mapping[str, Sequence[Sequence[float]] | Sequence[float] | str]],
    *,
    max_configurations: int = 4,
    relative_noise: float = 0.01,
    absolute_power_floor: float = 1.0e-8,
    require_planar_and_conical: bool = True,
) -> list[dict[str, Any]]:
    """Enumerate minimal DOE configuration bundles and rank passing candidates."""

    if not configurations or max_configurations < 1:
        raise ValueError("configuration subset search requires candidates")
    names = sorted(configurations)
    ranked: list[dict[str, Any]] = []
    for count in range(1, min(max_configurations, len(names)) + 1):
        for subset in combinations(names, count):
            records = [configurations[name] for name in subset]
            classes = {str(record.get("azimuth_class", "")) for record in records}
            if require_planar_and_conical and not {"planar", "conical"}.issubset(classes):
                continue
            jac = np.vstack([np.asarray(record["jacobian"], dtype=float) for record in records])
            power = np.concatenate([np.asarray(record["nominal_power"], dtype=float) for record in records])
            metrics = fisher_metrics(
                jac,
                power,
                relative_noise=relative_noise,
                absolute_power_floor=absolute_power_floor,
            )
            passes = bool(
                metrics["rank"] == 2
                and abs(metrics["rho_hw"]) <= 0.90
                and metrics["condition_number"] <= 100.0
            )
            ranked.append({"configuration_subset": list(subset), "passes": passes, **metrics})
    return sorted(
        ranked,
        key=lambda row: (
            not row["passes"],
            len(row["configuration_subset"]),
            row["condition_number"],
            -row["log_det_fisher"],
        ),
    )


def local_linear_recovery(
    jacobian: Sequence[Sequence[float]],
    observed_minus_center: Sequence[float],
    nominal_power: Sequence[float],
    *,
    relative_noise: float = 0.01,
    absolute_power_floor: float = 1.0e-8,
) -> dict[str, Any]:
    """Recover [delta-height,delta-width] without claiming a surrogate model."""

    jac = np.asarray(jacobian, dtype=float)
    residual = np.asarray(observed_minus_center, dtype=float)
    power = np.asarray(nominal_power, dtype=float)
    if jac.ndim != 2 or jac.shape[1] != 2 or residual.shape != (jac.shape[0],):
        raise ValueError("local recovery inputs have incompatible shapes")
    sigma = np.sqrt((relative_noise * power) ** 2 + absolute_power_floor**2)
    estimate, _, rank, singular_values = np.linalg.lstsq(
        jac / sigma[:, None], residual / sigma, rcond=None
    )
    return {
        "delta_height_nm": float(estimate[0]),
        "delta_width_nm": float(estimate[1]),
        "rank": int(rank),
        "singular_values": singular_values.tolist(),
        "semantics": "local weighted linear sanity recovery; not a surrogate or formal inversion",
    }
