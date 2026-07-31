"""Deterministic physical reconstruction for surrogate predictions."""

from __future__ import annotations

import numpy as np


def analytic_power_mask(points: np.ndarray, *, m_values=range(-7, 4),
                        wavelength_nm: float = 13.5,
                        period_x_nm: float = 50.0,
                        period_y_nm: float = 25.0) -> np.ndarray:
    """Return an analytic ``(sample, 22, 2)`` power-carrying mask.

    The same air-side propagation test was independently checked against every
    Case119 training mask row.  The two sides and S/P components share the
    propagation identity; structural nulls remain null rather than zero.
    """

    points = np.asarray(points, dtype=np.float64)
    if points.ndim == 1:
        points = points[None, :]
    if points.ndim != 2 or points.shape[1] != 4:
        raise ValueError("points must have shape (n,4)")
    grazing = np.deg2rad(points[:, 2])
    azimuth = np.deg2rad(points[:, 3])
    kx = np.cos(grazing) * np.cos(azimuth)
    ky = np.cos(grazing) * np.sin(azimuth)
    result = np.zeros((len(points), 2 * len(tuple(m_values)), 2), dtype=bool)
    for i, m in enumerate(m_values):
        propagating = ((kx + float(m) * wavelength_nm / period_x_nm) ** 2
                       + (ky + 0.0 * wavelength_nm / period_y_nm) ** 2 <= 1.0 + 1.0e-12)
        result[:, i, :] = propagating[:, None]
        result[:, i + len(tuple(m_values)), :] = propagating[:, None]
    return result


def reconstruct_aggregates(raw: np.ndarray, *, epsilon: float = 1.0e-8) -> np.ndarray:
    """Project raw R/T/A predictions to a conservation-respecting composition."""

    values = np.asarray(raw, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] < 3:
        raise ValueError("raw aggregate predictions require three columns")
    logits = np.log(np.maximum(values[:, :3], epsilon))
    logits -= np.max(logits, axis=1, keepdims=True)
    weights = np.exp(logits)
    weights /= np.sum(weights, axis=1, keepdims=True)
    return np.column_stack((weights, weights[:, 2]))


def reconstruct_powers(raw: np.ndarray, mask: np.ndarray, aggregates: np.ndarray,
                       *, sidewise_renormalize: bool = True) -> np.ndarray:
    """Apply non-negativity, analytic nulls, and optional side ledgers."""

    values = np.maximum(np.asarray(raw, dtype=np.float64), 0.0)
    active = np.asarray(mask, dtype=bool)
    if values.shape != active.shape:
        raise ValueError("power/mask shapes disagree")
    output = np.full(values.shape, np.nan, dtype=np.float64)
    output[active] = values[active]
    if not sidewise_renormalize:
        return output
    aggregates = np.asarray(aggregates, dtype=np.float64)
    for side, sl in ((0, slice(0, 11)), (1, slice(11, 22))):
        carrying = active[:, sl, :]
        current = np.nansum(np.where(carrying, output[:, sl, :], 0.0), axis=(1, 2))
        desired = aggregates[:, side]
        scale = np.divide(desired, current, out=np.ones_like(desired), where=current > 0.0)
        block = output[:, sl, :]
        block[carrying] *= np.repeat(scale, block.shape[1] * block.shape[2])[carrying.ravel()]
        output[:, sl, :] = block
    return output


def physics_audit(aggregates: np.ndarray, powers: np.ndarray,
                  mask: np.ndarray) -> dict[str, float | int]:
    output = np.asarray(powers)
    active = np.asarray(mask, dtype=bool)
    inactive_nonnull = int(np.count_nonzero(~active & np.isfinite(output)))
    negative = int(np.count_nonzero(output[active] < 0.0))
    r_ledger = np.nansum(np.where(active[:, :11, :], output[:, :11, :], 0.0), axis=(1, 2))
    t_ledger = np.nansum(np.where(active[:, 11:, :], output[:, 11:, :], 0.0), axis=(1, 2))
    return {
        "negative_power_count": negative,
        "inactive_channel_nonnull_count": inactive_nonnull,
        "max_reflection_ledger_error": float(np.max(np.abs(r_ledger - aggregates[:, 0]))),
        "max_transmission_ledger_error": float(np.max(np.abs(t_ledger - aggregates[:, 1]))),
    }

