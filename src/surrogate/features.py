"""Deterministic Task003 input features and domain guards."""

from __future__ import annotations

import numpy as np


DOMAIN = {
    "height_nm": (115.0, 125.0),
    "width_x_nm": (16.0, 18.0),
    "grazing_deg": (0.5, 10.0),
    "azimuth_deg": (0.0, 90.0),
}

# M3S freezes the public production representation.  A/C remain available only
# to the explicitly training-only historical comparison in ``cv.py``.
FROZEN_FEATURE_CANDIDATE = "B"
FEATURE_CONTRACT_VERSION = "task003.feature-contract.v2"


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


def _base_features(values: np.ndarray) -> tuple[np.ndarray, ...]:
    height = 2.0 * (values[:, 0] - 120.0) / 10.0
    width = 2.0 * (values[:, 1] - 17.0) / 2.0
    grazing = np.deg2rad(values[:, 2])
    azimuth = np.deg2rad(values[:, 3])
    # grazing is measured from the sample surface, so the in-plane wave
    # number is cos(grazing), with the azimuth split into x/y components.
    in_plane = np.cos(grazing)
    kx = in_plane * np.cos(azimuth)
    ky = in_plane * np.sin(azimuth)
    kz = np.sin(grazing)
    grazing_scaled = 2.0 * (values[:, 2] - 5.25) / 9.5
    azimuth_scaled = 2.0 * values[:, 3] / 90.0 - 1.0
    return height, width, kx, ky, kz, grazing_scaled, azimuth_scaled


def transform_feature_candidate(points: np.ndarray, candidate: str = "A") -> np.ndarray:
    """Build one of the finite, training-frozen M3R feature candidates.

    A is the historical in-plane wavevector map, B is the direct angular map,
    and C adds the out-of-plane ``kz/k0`` coordinate.  All affine scalings use
    the declared production domain and never inspect frozen validation rows.
    """

    values = validate_domain(points)
    height, width, kx, ky, kz, grazing, azimuth = _base_features(values)
    key = str(candidate).upper()
    if key == "A":
        return np.column_stack((height, width, kx, ky))
    if key == "B":
        return np.column_stack((height, width, grazing, azimuth))
    if key == "C":
        return np.column_stack((height, width, kx, ky, kz))
    raise ValueError(f"unsupported Task003 feature candidate: {candidate}")


def transform_features(points: np.ndarray) -> np.ndarray:
    """Return the frozen production candidate B.

    Production callers cannot silently fall back to the historical wavevector
    candidate; comparison code must opt into ``transform_feature_candidate``.
    """

    return transform_feature_candidate(points, FROZEN_FEATURE_CANDIDATE)


def feature_contracts() -> dict[str, dict[str, object]]:
    """Return immutable metadata for the M3R candidate comparison."""

    return {
        "A": {"features": ["height_scaled", "width_scaled", "kx_over_k0", "ky_over_k0"],
              "dimension": 4, "scaling": "domain_height_width_and_physical_wavevector"},
        "B": {"features": ["height_scaled", "width_scaled", "grazing_scaled", "azimuth_scaled"],
              "dimension": 4, "scaling": "all four coordinates domain-affine"},
        "C": {"features": ["height_scaled", "width_scaled", "kx_over_k0", "ky_over_k0", "kz_over_k0"],
              "dimension": 5, "scaling": "domain_height_width_and_physical_wavevector"},
    }
