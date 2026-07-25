from __future__ import annotations

import hashlib

from mpi4py import MPI
import numpy as np
import pytest

from src.geometry.mesh_builder_3d import (
    _rank_cell_ids,
    _structured_hexa_mesh,
)


def _owned_cell_centers(msh) -> np.ndarray:
    tdim = msh.topology.dim
    owned = int(msh.topology.index_map(tdim).size_local)
    geometry_dofs = np.asarray(msh.geometry.dofmap[:owned], dtype=np.int64)
    centers = np.asarray(
        [
            np.mean(msh.geometry.x[dofs], axis=0)
            for dofs in geometry_dofs
        ],
        dtype=np.float64,
    )
    order = np.lexsort((centers[:, 2], centers[:, 1], centers[:, 0]))
    return centers[order]


def _expected_owned_centers(
    x_values: np.ndarray,
    y_values: np.ndarray,
    z_values: np.ndarray,
    *,
    rank: int,
    size: int,
) -> np.ndarray:
    nx = len(x_values) - 1
    ny = len(y_values) - 1
    nz = len(z_values) - 1
    centers = []
    for cell_id in _rank_cell_ids(nx * ny * nz, rank, size):
        cells_per_layer = nx * ny
        k = int(cell_id) // cells_per_layer
        layer_cell = int(cell_id) - k * cells_per_layer
        j = layer_cell // nx
        i = layer_cell - j * nx
        centers.append(
            (
                0.5 * (x_values[i] + x_values[i + 1]),
                0.5 * (y_values[j] + y_values[j + 1]),
                0.5 * (z_values[k] + z_values[k + 1]),
            )
        )
    result = np.asarray(centers, dtype=np.float64)
    order = np.lexsort((result[:, 2], result[:, 1], result[:, 0]))
    return result[order]


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in {1, 2, 4},
    reason="serial/MPI2/MPI4 deterministic partition qualification",
)
def test_input_preserving_partition_is_repeatable_and_owner_exact() -> None:
    comm = MPI.COMM_WORLD
    x_values = np.asarray([0.0, 0.2, 0.55, 0.8, 1.0])
    y_values = np.asarray([0.0, 0.45, 1.0])
    z_values = np.asarray([0.0, 0.25, 0.6, 1.0])
    meshes = tuple(
        _structured_hexa_mesh(
            comm,
            x_values,
            y_values,
            z_values,
            preserve_input_partition=True,
        )
        for _ in range(2)
    )
    permutation_hashes = []
    for msh in meshes:
        tdim = msh.topology.dim
        owned = int(msh.topology.index_map(tdim).size_local)
        assert owned == len(
            _rank_cell_ids(
                (len(x_values) - 1)
                * (len(y_values) - 1)
                * (len(z_values) - 1),
                comm.rank,
                comm.size,
            )
        )
        np.testing.assert_allclose(
            _owned_cell_centers(msh),
            _expected_owned_centers(
                x_values,
                y_values,
                z_values,
                rank=comm.rank,
                size=comm.size,
            ),
            rtol=0.0,
            atol=2.0e-15,
        )
        msh.topology.create_entity_permutations()
        permutations = np.asarray(
            msh.topology.get_cell_permutation_info(),
            dtype=np.uint32,
        )[:owned]
        permutation_hashes.append(
            hashlib.sha256(permutations.tobytes()).hexdigest()
        )
    assert permutation_hashes[0] == permutation_hashes[1]
    packets = comm.allgather(tuple(permutation_hashes))
    assert all(first == second for first, second in packets)
