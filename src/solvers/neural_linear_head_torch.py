"""Actual complex output coefficients mapped through original Nedelec moments."""

import time

import numpy as np
import torch


def head_coefficients(model):
    layer = model.envelopes[-1]
    weight = layer.weight.detach().numpy().reshape(8, 3, 2, 64)
    bias = layer.bias.detach().numpy().reshape(8, 3, 2)
    complex_weight = weight[:, :, 0] + 1j * weight[:, :, 1]
    complex_bias = bias[:, :, 0] + 1j * bias[:, :, 1]
    return np.concatenate((complex_bias[:, :, None], complex_weight), axis=2).reshape(
        -1
    )


def assign_head(model, gamma):
    gamma = np.asarray(gamma, dtype=np.complex128).reshape(8, 3, 65)
    layer = model.envelopes[-1]
    weight = np.stack((gamma[:, :, 1:].real, gamma[:, :, 1:].imag), axis=2).reshape(
        48, 64
    )
    bias = np.stack((gamma[:, :, 0].real, gamma[:, :, 0].imag), axis=2).reshape(48)
    with torch.no_grad():
        layer.weight.copy_(torch.from_numpy(weight))
        layer.bias.copy_(torch.from_numpy(bias))


def build_head_mapping(model, cache, path, heartbeat=None):
    """1560 columns from one batch8 hidden forward per owner block, no AD."""
    began = time.perf_counter()
    matrix = np.lib.format.open_memmap(
        path,
        mode="w+",
        dtype=np.complex128,
        shape=(cache.active_rows, 1560),
        fortran_order=True,
    )
    matrix[:] = 0
    interpolation = cache.interpolation.numpy().reshape(
        cache.interpolation.shape[0], 3, -1
    )
    transforms = cache.transforms.numpy()
    points = cache.normalized.shape[1]
    hidden = model.envelopes[:-1]
    with torch.no_grad():
        for start in range(0, len(cache.cells), 8):
            stop = min(start + 8, len(cache.cells))
            features = hidden(cache.normalized[start:stop].reshape(-1, 3)).reshape(
                stop - start, points, 64
            )
            features = torch.cat(
                (torch.ones((stop - start, points, 1), dtype=torch.float64), features),
                dim=2,
            ).numpy()
            for offset, cell in enumerate(range(start, stop)):
                rows, selected = cache.owners[cell]
                transform = transforms[int(cache.orientation[cell])][selected.numpy()]
                jacobian = cache.jacobians[cell].numpy()
                phase = cache.phases[cell].numpy()
                for component in range(3):
                    mapping = transform @ np.einsum(
                        "r,mrq->mq", jacobian[component], interpolation
                    )
                    for carrier in range(8):
                        col = carrier * 195 + component * 65
                        matrix[rows, col : col + 65] = mapping @ (
                            phase[:, carrier, None] * features[offset]
                        )
            if heartbeat is not None and (start % 64 == 0 or stop == len(cache.cells)):
                heartbeat(
                    "head_mapping",
                    owner_cells_completed=stop,
                    owner_cells_total=len(cache.cells),
                )
    matrix.flush()
    return matrix, {
        "shape": list(matrix.shape),
        "payload_bytes": matrix.nbytes,
        "seconds": time.perf_counter() - began,
        "batch_size": 8,
        "coefficient_order": "carrier(8), physical vector component(3), bias+hidden(65)",
        "canonical_owner_orientation_MPC": "unchanged original q15 packet",
        "separate_1560_MLP_passes": False,
        "automatic_differentiation_used": False,
    }
