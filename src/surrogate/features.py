"""Deterministic Task003 input features and domain guards."""

from __future__ import annotations

import numpy as np


DOMAIN = {
    "height_nm": (115.0, 125.0),
    "width_x_nm": (16.0, 18.0),
    "grazing_deg": (0.5, 10.0),
    "azimuth_deg": (0.0, 90.0),
}


def _as_points(points: np.ndarray) -> np.ndarray:
    values = np.asarray(points, dtype=np.float64)
    if values.ndim == 1:
        values = values[None, :]
    if values.ndim != 2 or values.shape[1] != 4:
        raise ValueError("Task003 inputs must have shape (n, 4)")
    if not np.all(np.isfinite(values)):
        raise ValueError("Task003 inputs contain non-finite values")
    return values


def validate_domain(points: np.ndarray) -> np.ndarray:
    values = _as_points(points)
    lower = np.array([DOMAIN[k][0] for k in DOMAIN])
    upper = np.array([DOMAIN[k][1] for k in DOMAIN])
    if np.any(values[:, 2] <= 0.0):
        raise ValueError("grazing_deg=0 is fail-closed and is not a Task003 input")
    if np.any(values < lower) or np.any(values > upper):
        raise ValueError("input lies outside the Task003 production domain")
    return values


def transform_features(points: np.ndarray) -> np.ndarray:
    """Return ``[height_scaled, width_scaled, kx/k0, ky/k0]``."""

    values = validate_domain(points)
    height = 2.0 * (values[:, 0] - 120.0) / 10.0
    width = 2.0 * (values[:, 1] - 17.0) / 2.0
    grazing = np.deg2rad(values[:, 2])
    azimuth = np.deg2rad(values[:, 3])
    # grazing is measured from the sample surface, so the in-plane wave
    # number is cos(grazing), with the azimuth split into x/y components.
    in_plane = np.cos(grazing)
    return np.column_stack((height, width, in_plane * np.cos(azimuth),
                            in_plane * np.sin(azimuth)))

