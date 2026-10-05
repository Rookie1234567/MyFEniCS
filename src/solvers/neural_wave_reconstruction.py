"""Independent frozen-model rebuild using point values and original matrices.

The producer builds amplitude columns with oriented sparse maps. This checker
instead sums the actual network point values first, then applies the original
Piola, interpolation, orientation and owner maps, once per cell.
"""

import json
from pathlib import Path

import numpy as np
from scipy import sparse

from src.solvers.neural_wave_greedy import sha
from src.solvers.neural_wave_moments import Patch


def rebuild(directory, packet, marker=lambda *_: None):
    directory = Path(directory)
    boundary = json.loads((directory / "committed.json").read_text())
    state = directory / boundary["state"]["path"]
    if sha(state) != boundary["state"]["sha256"]:
        raise ValueError("FROZEN_COEFFICIENT_STATE_HASH_FAILED")
    with np.load(state, allow_pickle=False) as arrays:
        a = np.array(arrays["a"])
        saved = np.array(arrays["c"])
    models = []
    for i, entry in enumerate(boundary["chunks"]):
        file = directory / entry["path"]
        if sha(file) != entry["sha256"]:
            raise ValueError("FROZEN_NETWORK_CHUNK_HASH_FAILED")
        with np.load(file, allow_pickle=False) as arrays:
            models.append(
                (
                    Patch(tuple(arrays["center"]), tuple(arrays["radius"])),
                    np.array(arrays["wave_q"]),
                    (np.array(arrays["amplitude_real"]) + 1j * arrays["amplitude_imag"])
                    * a[i]
                    / float(arrays["scale"]),
                )
            )
    if len(models) != boundary["columns"] or len(a) != len(models):
        raise ValueError("FROZEN_NETWORK_COVERAGE_FAILED")
    interpolation = sparse.csr_matrix(packet["interpolation"])
    c = np.zeros(int(packet["active_rows"]), np.complex128)
    for cell, jac in enumerate(packet["jacobians"]):
        x = packet["origins"][cell] + packet["reference_points"] @ jac.T
        raw = np.zeros_like(x, dtype=np.complex128)
        lo, hi = x.min(0), x.max(0)
        for patch, q, p in models:
            center, radius = np.array(patch.center), np.array(patch.radius)
            if np.any(hi < center - radius) or np.any(lo > center + radius):
                continue
            raw += patch.window(x)[:, None] * (np.exp(1j * (x - center) @ q.T) @ p)
        moments = interpolation @ (raw @ jac).T.ravel()
        local = packet["transforms"][packet["orientation_ids"][cell]] @ moments
        rows = packet["owner_rows"][cell]
        c[rows[rows >= 0]] = local[rows >= 0]
        if cell % 32 == 0:
            marker(
                "frozen_network_rebuild",
                dict(
                    cell=cell,
                    cells=len(packet["origins"]),
                    columns=len(models),
                    quadrature=int(packet["quadrature_degree"]),
                ),
            )
    return c, saved, boundary
