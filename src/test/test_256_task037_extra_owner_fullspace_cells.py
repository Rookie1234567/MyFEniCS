from __future__ import annotations

import hashlib

import numpy as np
import pytest
import scipy.sparse as sparse
from mpi4py import MPI

from src.geometry.tetra_mesh_audit import canonical_owned_cell_ids
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.physical_slab_two_level import (
    build_owner_local_slab_plan,
    collect_owner_local_fullspace_slab_cells,
    extract_owner_local_slab_vector,
)
from src.solvers.static_condensed_iterative import (
    _task037_g2_owner_vector_sha256,
)
from src.solvers.static_factor_reuse import _canonical_global_row_ids_fingerprint
from src.solvers.static_fullspace_slab_oracle import (
    measure_fullspace_slab_identity,
)
from src.test.test_224_task037_static_local_schur_action import _build_fixture


_CELL_ID_HASH_ALGORITHM = (
    "task037.fullspace-slab-cell-ids-order.v1|dtype=<i8|order=C|count=u64"
)


def _cell_id_sequence_sha256(values) -> str:
    canonical = np.asarray(values, dtype="<i8")
    digest = hashlib.sha256()
    digest.update(_CELL_ID_HASH_ALGORITHM.encode("ascii"))
    digest.update(b"\0")
    digest.update(np.asarray([canonical.size], dtype="<u8").tobytes())
    digest.update(canonical.tobytes(order="C"))
    return digest.hexdigest()


def _fixed_vectors(owner_rows: np.ndarray) -> tuple[np.ndarray, ...]:
    indices = np.asarray(owner_rows, dtype=np.float64)
    scale = max(float(indices.size), 1.0)
    phase = (indices + 1.0) / scale
    return tuple(
        np.sin((index + 1.0) * 0.19 * phase + 0.07 * index)
        + 1j * np.cos((index + 1.0) * 0.11 * phase - 0.13 * index)
        for index in range(3)
    )


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="G2.2C fixture supports serial and MPI2",
)
def test_collect_owner_local_fullspace_cells_serial_or_mpi2():
    comm = MPI.COMM_WORLD
    mesh, cell_tags, function_space, compiled = _build_fixture(comm)
    condensed = build_unconstrained_assembly_time_condensation(
        compiled,
        function_space,
        cell_tags,
        materialize_global_matrix=False,
        retain_local_schur_for_matrix_free=True,
        retain_fullspace_slab_blocks_for_research=True,
    )
    try:
        plan = build_owner_local_slab_plan(
            condensed,
            mesh,
            domain_z=(0.0, 1.0),
            num_slabs=3,
            overlap_fraction=0.0,
        )
        slab = 0
        owner = int(plan.slab_owners[slab])
        canonical_ids, _records, _ordered_keys = canonical_owned_cell_ids(mesh)
        local_ids = [
            int(canonical_ids[cell_index])
            for cell_index in plan.local_cell_indices_by_slab[slab]
        ]
        expected_ids = sorted(
            cell_id
            for packet in comm.allgather(local_ids)
            for cell_id in packet
        )
        local_classes = {
            condensed.cell_recovery_maps[cell_index].class_key
            for cell_index in plan.local_cell_indices_by_slab[slab]
        }
        expected_classes = set()
        for packet in comm.allgather(tuple(local_classes)):
            expected_classes.update(packet)

        cells, audit = collect_owner_local_fullspace_slab_cells(
            condensed,
            plan,
            mesh,
            slab,
        )
        assert all(packet == audit for packet in comm.allgather(audit))
        assert audit["slab"] == slab
        assert audit["owner"] == owner
        assert audit["global_cell_count"] == len(expected_ids)
        assert audit["owner_cell_count"] == len(expected_ids)
        assert [cell.canonical_cell_id for cell in cells] == (
            expected_ids if comm.rank == owner else []
        )
        assert audit["cell_canonical_id_hash"] == _cell_id_sequence_sha256(
            expected_ids
        )
        assert audit["cell_canonical_id_hash_algorithm"] == (
            _CELL_ID_HASH_ALGORITHM
        )
        assert audit["unique_block_count"] == len(expected_classes)
        assert audit["condensed_trace_matrix_materialized"] is False

        owner_rows = (
            np.asarray(plan.owner_rows[slab], dtype=np.int64)
            if comm.rank == owner
            else None
        )
        owner_rows = comm.bcast(owner_rows, root=owner)
        assert audit["owner_active_row_count"] == int(owner_rows.size)
        assert audit["owner_active_row_hash"] == (
            _canonical_global_row_ids_fingerprint(owner_rows)
        )
        residual = condensed.create_active_vector()
        residual_start, residual_end = residual.getOwnershipRange()
        residual_rows = np.arange(residual_start, residual_end, dtype=np.float64)
        residual.getArray()[:] = (
            0.75
            + 0.125 * residual_rows
            + 1j * (0.5 - 0.0625 * residual_rows)
        )
        residual.assemble()
        routed_residual, route_audit = extract_owner_local_slab_vector(
            residual,
            plan,
            slab,
        )
        assert all(packet == route_audit for packet in comm.allgather(route_audit))
        assert route_audit["owner_rank"] == owner
        assert route_audit["owner_local_row_count"] == int(owner_rows.size)
        if comm.rank == owner:
            assert len(cells) == len(expected_ids)
            assert len({id(cell.block) for cell in cells}) == len(expected_classes)
            assert all(
                sparse.isspmatrix_csr(cell.trace_expansion) for cell in cells
            )
            nnz = sum(int(cell.trace_expansion.nnz) for cell in cells)
            bytes_used = sum(
                int(cell.trace_expansion.data.nbytes)
                + int(cell.trace_expansion.indices.nbytes)
                + int(cell.trace_expansion.indptr.nbytes)
                for cell in cells
            )
            assert audit["sparse_expansion_nnz"] == nnz
            assert audit["sparse_expansion_bytes"] == bytes_used
            expected_residual = (
                0.75
                + 0.125 * owner_rows.astype(np.float64)
                + 1j * (0.5 - 0.0625 * owner_rows.astype(np.float64))
            )
            assert routed_residual is not None
            np.testing.assert_allclose(routed_residual, expected_residual)
            residual_hash = _task037_g2_owner_vector_sha256(
                owner_rows,
                routed_residual,
                domain="task037.g2.iter20-real-residual.v1",
            )
            changed_rows = owner_rows.copy()
            changed_rows[0] += 1
            assert residual_hash != _task037_g2_owner_vector_sha256(
                changed_rows,
                routed_residual,
                domain="task037.g2.iter20-real-residual.v1",
            )
            changed_values = routed_residual.copy()
            changed_values[0] += 1.0 + 2.0j
            assert residual_hash != _task037_g2_owner_vector_sha256(
                owner_rows,
                changed_values,
                domain="task037.g2.iter20-real-residual.v1",
            )
            assert residual_hash != _task037_g2_owner_vector_sha256(
                owner_rows,
                routed_residual,
                domain="task037.g2.current-local-shift.v1",
            )
            result = measure_fullspace_slab_identity(
                cells,
                (*_fixed_vectors(owner_rows), routed_residual),
                active_size=int(owner_rows.size),
            )
            assert result["vector_count"] == 4
            assert result["finite"] is True
            assert result["deterministic"] is True
            local_error = float(result["max_relative_error"])
        else:
            assert cells == ()
            assert routed_residual is None
            local_error = 0.0
        assert comm.allreduce(local_error, op=MPI.MAX) <= 1.0e-10
        residual.destroy()
    finally:
        condensed.destroy()
