"""Independent frozen-network evaluation retaining every nonzero window value.

The only saving is omitting exponentials multiplied by an exactly zero C1
window. Coefficients still come from the original full pointwise interpolation
and orientation/owner maps, rather than the producer's amplitude columns.
"""

import json
from pathlib import Path

import numpy as np

from src.solvers.neural_wave_greedy import sha
from src.solvers.neural_wave_moments import Patch
from src.solvers.neural_wave_reconstruction import pointwise_moments


def frozen_point_values(models, points, counts=None):
    """Sum all committed modules in order, with no magnitude cutoff."""
    points = np.asarray(points, dtype=np.float64)
    values = np.zeros(points.shape, dtype=np.complex128)
    lo, hi = points.min(0), points.max(0)
    for patch, q, amplitude in models:
        center, radius = np.asarray(patch.center), np.asarray(patch.radius)
        # Same strict support exclusion as the original independent rebuild.
        # Touching supports still compute the window before excluding zeros.
        if np.any(hi < center - radius) or np.any(lo > center + radius):
            if counts is not None:
                counts["bbox_skipped_models"] += 1
            continue
        window = patch.window(points)
        active = window != 0.0
        if counts is not None:
            counts["exact_zero_point_neurons_omitted"] += int(
                (len(points) - np.count_nonzero(active)) * len(q)
            )
            counts["nonzero_point_neurons_evaluated"] += int(
                np.count_nonzero(active) * len(q)
            )
        if not np.any(active):
            continue
        displacement = points[active] - center
        values[active] += window[active, None] * (
            np.exp(1j * displacement @ q.T) @ amplitude
        )
    return values


def rebuild_frozen_field(directory, packet, marker=lambda *_: None):
    """Read hash-bound model state, evaluate points, then all original moments."""
    directory = Path(directory)
    boundary = json.loads((directory / "committed.json").read_text())
    state = directory / boundary["state"]["path"]
    if sha(state) != boundary["state"]["sha256"]:
        raise ValueError("FROZEN_COEFFICIENT_STATE_HASH_FAILED")
    with np.load(state, allow_pickle=False) as arrays:
        a = np.array(arrays["a"], dtype=np.complex128)
        saved = np.array(arrays["c"], dtype=np.complex128)
    if a.shape != (boundary["columns"],) or saved.shape != (
        int(packet["active_rows"]),
    ):
        raise ValueError("FROZEN_NETWORK_COVERAGE_FAILED")
    if not np.isfinite(a).all() or not np.isfinite(saved).all():
        raise ValueError("FROZEN_NETWORK_NONFINITE_STATE")
    models = []
    for i, entry in enumerate(boundary["chunks"]):
        file = directory / entry["path"]
        if sha(file) != entry["sha256"]:
            raise ValueError("FROZEN_NETWORK_CHUNK_HASH_FAILED")
        with np.load(file, allow_pickle=False) as arrays:
            patch = Patch(tuple(arrays["center"]), tuple(arrays["radius"]))
            q = np.array(arrays["wave_q"], dtype=np.float64)
            amplitude = np.array(arrays["amplitude_real"], dtype=np.float64) + 1j * np.array(
                arrays["amplitude_imag"], dtype=np.float64
            )
            scale = float(arrays["scale"])
        if (
            len(patch.center) != 3
            or len(patch.radius) != 3
            or q.ndim != 2
            or q.shape[1] != 3
            or amplitude.shape != q.shape
            or not np.isfinite(np.r_[patch.center, patch.radius]).all()
            or np.any(np.asarray(patch.radius) <= 0)
            or not np.isfinite(q).all()
            or not np.isfinite(amplitude).all()
            or not np.isfinite(scale)
            or scale <= 0
        ):
            raise ValueError("FROZEN_NETWORK_INVALID_MODULE")
        models.append((patch, q, amplitude * a[i] / scale))
    if len(models) != boundary["columns"]:
        raise ValueError("FROZEN_NETWORK_COVERAGE_FAILED")
    counts = dict(
        cells=0,
        bbox_skipped_models=0,
        exact_zero_point_neurons_omitted=0,
        nonzero_point_neurons_evaluated=0,
    )

    def field(points):
        result = frozen_point_values(models, points, counts)
        cell = counts["cells"]
        counts["cells"] += 1
        if cell % 32 == 0:
            marker(
                "frozen_network_pointwise_rebuild",
                dict(
                    cell=cell,
                    cells=len(packet["origins"]),
                    columns=len(models),
                    quadrature=int(packet["quadrature_degree"]),
                ),
            )
        return result

    c = pointwise_moments(packet, field)
    marker("frozen_network_exact_zero_work", counts)
    return c, saved, boundary
