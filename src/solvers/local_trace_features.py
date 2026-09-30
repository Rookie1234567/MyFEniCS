"""Reviewed fixed local functions, integrated over complete Nedelec entities.

Only the independent coefficient rows are localized.  No discontinuous mask
is multiplied into an integrand, and there is no trainable hidden layer here.
"""

from itertools import product
from time import perf_counter

import numpy as np

CUTS = np.array([0., 0., .525])
GEOMETRY_TOL = 1e-13


def patch_ids(centers, bounds):
    """Canonical periodic representatives determine support, not owners."""
    points = np.array(centers, dtype=float, copy=True)
    bounds = np.asarray(bounds, dtype=float)
    for axis in (0, 1):
        upper = np.abs(points[:, axis]-bounds[axis, 1]) <= GEOMETRY_TOL
        points[upper, axis] -= bounds[axis, 1]-bounds[axis, 0]
    sides = points > CUTS+GEOMETRY_TOL  # A cut itself belongs to the lower box.
    ids = sides.astype(np.int64) @ np.array([4, 2, 1])
    return ids, points


def boxes(bounds):
    bounds = np.asarray(bounds, float)
    result = []
    for side in product((0, 1), repeat=3):
        box = np.array([[bounds[j, 0], CUTS[j]] if not s else
                        [CUTS[j], bounds[j, 1]] for j, s in enumerate(side)])
        if np.any(box[:, 1] <= box[:, 0]):
            raise ValueError('invalid reviewed local box')
        result.append(box)
    return np.array(result)


def local_coordinates(points, box):
    box = np.asarray(box, float)
    return (np.asarray(points)-box.mean(axis=1))/((box[:, 1]-box[:, 0])/2)


def polynomial_features(xi):
    """Lexicographic (0..3)^3 plus the fixed L4(x), never a p4 FE space."""
    xi = np.asarray(xi, float)
    values = [np.polynomial.legendre.legvander(xi[..., j], 4) for j in range(3)]
    columns = [values[0][..., a]*values[1][..., b]*values[2][..., c]
               for a, b, c in product(range(4), repeat=3)]
    columns.append(values[0][..., 4])
    return np.stack(columns, axis=-1)


def numpy_hidden_features(xi, weights):
    """Independent forward witness for the fixed three tanh hidden layers."""
    value = np.asarray(xi, np.float64)
    for j in range(3):
        value = np.tanh(value @ weights['w'+str(j)].T + weights['b'+str(j)])
    return np.concatenate((np.ones(value.shape[:-1]+(1,)), value), axis=-1)


def extension_field(points, box, wavevector, coefficient, scalar_features):
    features = scalar_features(local_coordinates(points, box))
    value = features @ np.asarray(coefficient, complex).reshape(3, 65).T
    return np.exp(1j*(np.asarray(points) @ wavevector))[:, None]*value


def build_local_library(moments, grouping, wavevector, scalar_features,
                        heartbeat=lambda *a, **k: None):
    """Batch8 full original moments; row selection occurs after T^-T.

    ``scalar_features`` is either the fixed polynomial function or a no-grad
    Torch hidden forward.  No network point values are used as coefficients.
    """
    began = perf_counter()
    n = int(moments['active_rows'])
    ids = grouping['patch_id']
    interpolation = moments['interpolation'].reshape(144, 3, -1)
    reference = moments['reference_points']
    libraries, details = [], []
    for patch, box in enumerate(grouping['boxes']):
        rows = np.flatnonzero(ids == patch)
        lookup = np.full(n, -1, dtype=np.int64)
        lookup[rows] = np.arange(len(rows))
        owner_rows = moments['owner_rows']
        included = owner_rows >= 0
        on_patch = np.zeros_like(included)
        on_patch[included] = ids[owner_rows[included]] == patch
        cells = np.flatnonzero(on_patch.any(axis=1))
        matrix = np.empty((len(rows), 195), dtype=np.complex128, order='F')
        written = np.zeros(len(rows), dtype=bool)
        for start in range(0, len(cells), 8):
            batch = cells[start:start+8]
            coordinates = np.array([moments['origins'][cell] +
                reference @ moments['jacobians'][cell].T for cell in batch])
            # Full original point inventories, even when only one face is owned.
            xi = local_coordinates(coordinates, box)
            features = scalar_features(xi.reshape(-1, 3)).reshape(len(batch), len(reference), 65)
            phase = np.exp(1j*(coordinates @ wavevector))
            for i, cell in enumerate(batch):
                selected = np.flatnonzero(on_patch[cell])
                target = lookup[owner_rows[cell, selected]]
                if np.any(written[target]):
                    raise ValueError('duplicate original canonical owner')
                transform = moments['transforms'][moments['orientation_ids'][cell]][selected]
                J = moments['jacobians'][cell]
                for component in range(3):
                    functional = transform @ np.einsum('r,mrq->mq', J[component], interpolation)
                    matrix[target, component*65:(component+1)*65] = functional @ (phase[i, :, None]*features[i])
                written[target] = True
            heartbeat('local_moments', patch=patch, owner_cells_completed=min(start+8,len(cells)), owner_cells=len(cells))
        if not written.all() or not np.isfinite(matrix).all():
            raise ValueError('incomplete/nonfinite local moment library')
        libraries.append(matrix)
        details.append(dict(patch=patch, rows=len(rows), owner_cells=len(cells),
                            full_points_per_cell=len(reference), batch_size=8))
    return libraries, dict(seconds=perf_counter()-began, patches=details,
                           interpolation_then_row_selection=True,
                           integrand_mask=False, full_q15_moments=True,
                           global_extension_on_original_master_entities=True,
                           physical_phase_not_periodically_wrapped=True)
