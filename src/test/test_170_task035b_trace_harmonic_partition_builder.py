"""Strict serial/MPI qualification for the trace-harmonic partition builder."""

from __future__ import annotations

from dataclasses import replace

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest

from src.solvers.condensed_trace_harmonic_partition import (
    build_production_trace_harmonic_partition,
    estimate_h15_exact_dense_trace_harmonic_storage,
)
from src.solvers.condensed_trace_harmonic_pc import TraceHarmonicPartition
from src.solvers.hcurl_assembly_time_condensation import (
    AssemblyTimeCondensedSystem,
    CellRecoveryMap,
    TraceConstraintMap,
)


_CELL_DATA = (
    (0.15, (100, 101, 110)),
    (0.35, (105, 106, 102)),
    (0.65, (103, 104, 102)),
    (0.85, (108, 109, 102)),
)


def _expansion(
    *,
    orphan_active_row: bool = False,
) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    active_by_original: dict[int, tuple[int, ...]] = {
        100: (0,),
        101: (1,),
        110: (0, 5),
        105: (5,),
        106: (6,),
        102: (4,),
        103: (2,),
        104: (3,),
        108: ((2,) if orphan_active_row else (7,)),
        109: (2,),
    }
    result = {}
    for original, rows in active_by_original.items():
        result[original] = (
            np.asarray(rows, dtype=PETSc.IntType),
            np.asarray(
                [
                    np.exp(1j * 0.07 * (original + offset))
                    for offset, _row in enumerate(rows)
                ],
                dtype=np.complex128,
            ),
        )
    return result


def _global_active_hyperedges(
    expansion: dict[int, tuple[np.ndarray, np.ndarray]],
) -> tuple[np.ndarray, ...]:
    return tuple(
        np.unique(
            np.concatenate([expansion[original][0] for original in originals])
        ).astype(PETSc.IntType, copy=False)
        for _z, originals in _CELL_DATA
    )


def _matrix(
    *,
    expansion: dict[int, tuple[np.ndarray, np.ndarray]],
    cross_block_pattern: bool,
) -> PETSc.Mat:
    comm = MPI.COMM_WORLD
    rows = 10
    pattern = [set([row]) for row in range(rows)]
    for edge in _global_active_hyperedges(expansion):
        for row in edge:
            pattern[int(row)].update(int(column) for column in edge)
    for appended, support in ((8, (0, 1, 4)), (9, (2, 3, 4))):
        pattern[appended].update((*support, appended))
        for row in support:
            pattern[row].add(appended)
    if cross_block_pattern:
        pattern[0].add(2)

    matrix = PETSc.Mat().createAIJ(
        [rows, rows],
        nnz=rows,
        comm=comm,
    )
    start, end = map(int, matrix.getOwnershipRange())
    for row in range(start, end):
        columns = np.asarray(sorted(pattern[row]), dtype=PETSc.IntType)
        matrix.setValues(
            row,
            columns,
            np.asarray(
                [
                    3.0 + 0.01j * (row + 1)
                    if column == row
                    else 0.1 + 0.003j * (column + 1)
                    for column in columns
                ],
                dtype=PETSc.ScalarType,
            ),
        )
    matrix.assemble()
    return matrix


def _system(
    *,
    reverse_local_cells: bool = False,
    missing_expansion_support: bool = False,
    orphan_active_row: bool = False,
    cross_block_pattern: bool = False,
) -> tuple[AssemblyTimeCondensedSystem, np.ndarray]:
    comm = MPI.COMM_WORLD
    expansion = _expansion(orphan_active_row=orphan_active_row)
    matrix = _matrix(
        expansion=expansion,
        cross_block_pattern=cross_block_pattern,
    )
    owned_global_cells = [
        cell for cell in range(len(_CELL_DATA)) if cell % comm.size == comm.rank
    ]
    if reverse_local_cells:
        owned_global_cells.reverse()
    recovery_maps = []
    midpoint_z = []
    for global_cell in owned_global_cells:
        z, originals = _CELL_DATA[global_cell]
        original_rows = np.asarray(originals, dtype=PETSc.IntType)
        if missing_expansion_support and global_cell == 0:
            original_rows = original_rows.copy()
            original_rows[0] = 999
        recovery_maps.append(
            CellRecoveryMap(
                interior_original_dofs=np.asarray(
                    [200 + global_cell],
                    dtype=PETSc.IntType,
                ),
                trace_original_dofs=original_rows,
                cell_local_dofs=np.asarray(
                    [global_cell],
                    dtype=np.int32,
                ),
                raw_key=("synthetic", global_cell),
                cell_permutation=0,
                interior_policy="high",
                class_key=("synthetic", global_cell, "high"),
            )
        )
        midpoint_z.append(z)

    constraints = TraceConstraintMap(
        owned_active_original_dofs=np.empty(0, dtype=PETSc.IntType),
        original_to_active={},
        expansion_by_original=expansion,
        full_trace_rows=len(expansion),
        active_rows=8,
        slave_rows=2,
        build_audit={
            "schema_version": "task035b.test-trace-expansion.v1",
            "status": "synthetic_periodic_expansion",
        },
        owned_active_rows=None,
        active_coordinates_are_original_trace_dofs=False,
    )
    system = AssemblyTimeCondensedSystem(
        matrix=matrix,
        owned_trace_original_dofs=np.empty(0, dtype=PETSc.IntType),
        original_to_trace={},
        trace_constraints=constraints,
        cell_recovery_maps=tuple(recovery_maps),
        interior_from_trace_by_class={},
        interior_lu_by_class={},
        interior_rhs_projection_by_class={},
        interior_solution_embedding_by_class={},
        dual_interior_from_trace_by_class={},
        appended_dual_interior_by_cell=tuple({} for _ in recovery_maps),
        appended_dual_rows_registered=set(),
        interior_residual_projection_by_class={},
        full_rows=14,
        trace_rows=len(expansion),
        active_rows=8,
        appended_rows=2,
        interior_rows=4,
        active_interior_rows=4,
        build_audit={
            "schema_version": "task035b.test-condensed-system.v1",
            "owned_cell_count_global": len(_CELL_DATA),
        },
    )
    return system, np.asarray(midpoint_z, dtype=np.float64)


def _build(system: AssemblyTimeCondensedSystem, midpoint_z: np.ndarray):
    return build_production_trace_harmonic_partition(
        system,
        owned_cell_midpoint_z=midpoint_z,
        region_z_edges=np.asarray([0.0, 0.5, 1.0]),
    )


def test_actual_cell_support_builds_periodic_closed_partition_and_hashes() -> None:
    system, midpoint_z = _system()
    reordered, reordered_z = _system(reverse_local_cells=True)
    try:
        result = _build(system, midpoint_z)
        reordered_result = _build(reordered, reordered_z)

        assert [
            block.tolist() for block in result.partition.local_blocks
        ] == [[0, 1, 5, 6], [2, 3, 7]]
        assert result.partition.interface_rows.tolist() == [4, 8, 9]
        assert result.audit["periodic_closed_hyperedges"] is True
        assert result.audit["all_active_rows_have_cell_support"] is True
        assert result.audit["all_appended_rows_are_interface"] is True
        assert (
            result.audit["cross_local_block_structural_zero_proven"] is True
        )
        matrix_audit = result.audit["assembled_matrix_pattern_audit"]
        assert matrix_audit[
            "cross_local_block_structural_entry_count"
        ] == 0
        assert matrix_audit["appended_rows_with_active_support"] == 2
        assert result.audit["production_execution_enabled"] is False
        assert result.audit["candidate_promotion"] is False

        hashes = result.audit["canonical_hashes"]
        assert set(hashes) == {
            "trace_expansion_sha256",
            "cell_hypergraph_sha256",
            "partition_sha256",
            "matrix_pattern_sha256",
            "foundation_bundle_sha256",
        }
        assert all(
            len(value) == 64
            and set(value) <= set("0123456789abcdef")
            for value in hashes.values()
        )
        assert (
            reordered_result.audit["canonical_hashes"]
            == result.audit["canonical_hashes"]
        )
        gathered = MPI.COMM_WORLD.allgather(dict(hashes))
        assert all(packet == gathered[0] for packet in gathered)
    finally:
        reordered.destroy()
        system.destroy()


@pytest.mark.parametrize(
    ("keyword", "message"),
    [
        ("missing_expansion_support", "absent from the complete periodic"),
        ("orphan_active_row", "orphan rows"),
    ],
)
def test_missing_cell_support_and_orphan_active_rows_fail_closed(
    keyword: str,
    message: str,
) -> None:
    kwargs = {keyword: True}
    system, midpoint_z = _system(**kwargs)
    try:
        with pytest.raises((ValueError, RuntimeError), match=message):
            _build(system, midpoint_z)
    finally:
        system.destroy()


def test_cross_local_block_petsc_pattern_fails_even_for_one_stored_entry() -> None:
    system, midpoint_z = _system(cross_block_pattern=True)
    try:
        with pytest.raises(
            RuntimeError,
            match="forbidden structural entry",
        ):
            _build(system, midpoint_z)
    finally:
        system.destroy()


def test_h15_dense_exact_storage_is_derived_controlled_negative() -> None:
    partition = TraceHarmonicPartition(
        local_blocks=(
            np.arange(0, 4_000, dtype=PETSc.IntType),
            np.arange(4_000, 8_000, dtype=PETSc.IntType),
            np.arange(8_000, 12_000, dtype=PETSc.IntType),
            np.arange(12_000, 16_000, dtype=PETSc.IntType),
        ),
        interface_rows=np.arange(16_000, 16_880, dtype=PETSc.IntType),
    )
    estimate = estimate_h15_exact_dense_trace_harmonic_storage(
        partition,
        mpi_size=8,
    )
    storage = estimate["retained_storage_bytes"]

    assert estimate["classification"] == "controlled_negative"
    assert estimate["production_execution_enabled"] is False
    assert estimate["candidate_promotion"] is False
    assert estimate["strictly_factorless"] is False
    assert estimate["measured_process_memory"] is False
    assert estimate["h15_authority"] == {
        "active_trace_rows": 16_800,
        "appended_dtn_rows": 80,
        "matrix_rows": 16_880,
    }
    assert storage["local_dense_lu_values_total"] == 4 * 4_000**2 * 16
    assert storage["local_dense_lu_pivots_total"] == 16_000 * 4
    assert (
        storage["stored_harmonic_extensions_total"]
        == 16_000 * 880 * 16
    )
    assert storage["stored_lower_couplings_total"] == (
        storage["stored_harmonic_extensions_total"]
    )
    assert storage["replicated_interface_lu_per_rank"] == (
        880**2 * 16 + 880 * 4
    )
    assert storage["retained_rank_sum_total"] > (
        storage["local_dense_lu_values_total"]
    )

    invalid = replace(
        partition,
        interface_rows=np.arange(16_000, 16_879, dtype=PETSc.IntType),
    )
    with pytest.raises(ValueError, match="cover every matrix row"):
        estimate_h15_exact_dense_trace_harmonic_storage(invalid)
