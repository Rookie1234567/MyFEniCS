from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI

from src.constraints.floquet_3d_high_order import floquet_geometry_tolerance
from src.solvers.hcurl_exact_class_block_cache import (
    tabulate_task037_extra_h2a_cell_tensor,
)
from src.solvers.hcurl_r2_constrained_local_block import (
    H2AR2CellExpansion,
    build_h2a_r2_cell_expansion,
    build_h2a_r2_transformed_block,
)
from src.test.test_272_task037_extra_fullspace_mf_mpi import _build_case


class _OffsetIndexMap:
    def __init__(self, offset: int):
        self.offset = int(offset)

    def local_to_global(self, rows):
        return np.asarray(rows, dtype=np.int64) + self.offset


def _synthetic_blocks(local_shift: int = 0, global_shift: int = 0):
    def local(value):
        return int(value + local_shift)

    def global_row(value):
        return int(value + global_shift)

    return (
        SimpleNamespace(
            kind="x",
            slave_local_dofs=(local(20),),
            slave_global_dofs=(global_row(1020),),
            master_global_dofs=(global_row(1010), global_row(2020)),
            coefficient_transform=np.asarray(((1.0, 2.0),), dtype=np.complex128),
        ),
        SimpleNamespace(
            kind="y",
            slave_local_dofs=(local(30),),
            slave_global_dofs=(global_row(1030),),
            master_global_dofs=(global_row(2020), global_row(3030)),
            coefficient_transform=np.asarray(((1.0, -1.0),), dtype=np.complex128),
        ),
        SimpleNamespace(
            kind="corner",
            slave_local_dofs=(local(40),),
            slave_global_dofs=(global_row(1040),),
            master_global_dofs=(global_row(3030), global_row(4040)),
            coefficient_transform=np.asarray(((1.0, 0.0),), dtype=np.complex128),
        ),
    )


def test_r2_sparse_expansion_deduplicates_aliases_and_applies_corner_once():
    local_rows = (10, 20, 30, 40, 50)
    phase_x = 1.2 + 0.1j
    phase_y = 0.8 - 0.2j
    phase_corner = -0.4 + 0.7j
    expansion = build_h2a_r2_cell_expansion(
        _synthetic_blocks(),
        local_rows,
        _OffsetIndexMap(1000),
        index_map_bs=1,
        phase_x=phase_x,
        phase_y=phase_y,
        phase_corner=phase_corner,
    )
    dense = expansion.materialize_dense()
    assert expansion.nloc == 5
    assert expansion.independent_count == 4
    assert np.array_equal(
        expansion.independent_global_rows,
        np.asarray((1010, 2020, 3030, 1050), dtype=np.int64),
    )
    assert dense.shape == (5, 4)
    assert dense[1, 0] == phase_x
    assert dense[1, 1] == 2.0 * phase_x
    assert dense[2, 1] == phase_y
    assert dense[2, 2] == -phase_y
    assert dense[3, 2] == phase_corner
    assert np.array_equal(dense, expansion.materialize_dense())
    assert all(
        array.shape != (expansion.nloc, expansion.nloc)
        for array in (
            expansion.offsets,
            expansion.column_indices,
            expansion.coefficients,
            expansion.independent_global_rows,
        )
    )
    with pytest.raises(ValueError, match="pattern identity"):
        bad_identity = list(expansion.pattern_identity)
        bad_identity[3] = (
            "row_offsets",
            tuple(int(value) for value in expansion.offsets[:-1]) + (8,),
        )
        H2AR2CellExpansion(
            expansion.offsets,
            expansion.column_indices,
            expansion.coefficients,
            expansion.independent_global_rows,
            tuple(bad_identity),
            expansion.pattern_sha256,
        )

    tiny_block = SimpleNamespace(
        kind="x",
        slave_local_dofs=(20,),
        slave_global_dofs=(1020,),
        master_global_dofs=(1010,),
        coefficient_transform=np.asarray(((1.0e-15,),), dtype=np.complex128),
    )
    with pytest.raises(RuntimeError, match="no masters"):
        build_h2a_r2_cell_expansion(
            (tiny_block,),
            (10, 20),
            _OffsetIndexMap(1000),
            index_map_bs=1,
            phase_x=1.0 + 0.0j,
            phase_y=1.0 + 0.0j,
        )

    shifted = build_h2a_r2_cell_expansion(
        _synthetic_blocks(local_shift=100, global_shift=10000),
        tuple(value + 100 for value in local_rows),
        _OffsetIndexMap(10900),
        index_map_bs=1,
        phase_x=phase_x,
        phase_y=phase_y,
        phase_corner=phase_corner,
    )
    assert shifted.pattern_sha256 == expansion.pattern_sha256
    assert not np.array_equal(
        shifted.independent_global_rows, expansion.independent_global_rows
    )


def test_r2_transformed_proxy_matches_independent_expansion_action():
    expansion = build_h2a_r2_cell_expansion(
        _synthetic_blocks(),
        (10, 20, 30, 40, 50),
        _OffsetIndexMap(1000),
        index_map_bs=1,
        phase_x=1.1 + 0.2j,
        phase_y=0.9 - 0.1j,
        phase_corner=1.0 + 0.0j,
    )
    local_block = np.asarray(
        [
            [4.0 + 0.1j * (i + j) for j in range(5)]
            for i in range(5)
        ],
        dtype=np.complex128,
    )
    local_block += 5.0 * np.eye(5, dtype=np.complex128)
    transformed = build_h2a_r2_transformed_block(local_block, expansion)
    dense = expansion.materialize_dense()
    vector = np.asarray(
        [1.0 + 0.2j * index for index in range(expansion.independent_count)],
        dtype=np.complex128,
    )
    expected = dense.conj().T @ (local_block @ (dense @ vector))
    observed = transformed @ vector
    assert np.all(np.isfinite(transformed))
    assert np.linalg.norm(observed - expected) / np.linalg.norm(expected) <= 1.0e-11
    assert np.array_equal(
        transformed,
        build_h2a_r2_transformed_block(local_block, expansion),
    )


def _assert_expansion_row_matches_finalized_mpc(
    expansion, floquet, function_space, cell_dofs, local_slave: int
):
    coefficients, offsets = floquet.mpc.coefficients()
    row = int(local_slave)
    masters_local = np.asarray(floquet.mpc.masters.links(row), dtype=np.int32)
    start, stop = int(offsets[row]), int(offsets[row + 1])
    row_coefficients = np.asarray(coefficients[start:stop], dtype=np.complex128)
    assert masters_local.size == row_coefficients.size
    masters_global = np.asarray(
        function_space.dofmap.index_map.local_to_global(masters_local),
        dtype=np.int64,
    )
    actual: dict[int, complex] = {}
    for global_row, coefficient in zip(masters_global, row_coefficients, strict=True):
        actual[int(global_row)] = actual.get(int(global_row), 0.0 + 0.0j) + complex(
            coefficient
        )
    local_rows = tuple(int(value) for value in cell_dofs)
    local_ordinal = local_rows.index(row)
    expansion_start = int(expansion.offsets[local_ordinal])
    expansion_stop = int(expansion.offsets[local_ordinal + 1])
    observed: dict[int, complex] = {}
    for column, coefficient in zip(
        expansion.column_indices[expansion_start:expansion_stop],
        expansion.coefficients[expansion_start:expansion_stop],
        strict=True,
    ):
        global_row = int(expansion.independent_global_rows[int(column)])
        observed[global_row] = observed.get(global_row, 0.0 + 0.0j) + complex(
            coefficient
        )
    assert actual.keys() == observed.keys()
    for global_row in actual:
        assert abs(actual[global_row] - observed[global_row]) <= 1.0e-14


@pytest.mark.parametrize("degree", (2, 3))
def test_r2_real_p2_p3_cells_use_oriented_local_blocks(degree: int):
    cfg, _mesh_data, function_space, cell_tags, _tags, floquet, form = _build_case(
        degree,
        MPI.COMM_SELF,
    )
    try:
        topology = floquet.phase_independent_topology
        assert topology is not None
        blocks = tuple(topology.blocks)
        cell_count = int(function_space.mesh.topology.index_map(3).size_local)
        chosen: dict[str, tuple[int, tuple[object, ...]]] = {}
        for cell in range(cell_count):
            cell_dofs = np.asarray(
                function_space.dofmap.cell_dofs(cell), dtype=np.int64
            )
            cell_rows = set(int(value) for value in cell_dofs)
            selected = tuple(
                block
                for block in blocks
                if block.slave_local_dofs
                and all(int(row) in cell_rows for row in block.slave_local_dofs)
            )
            kinds = {str(block.kind) for block in selected}
            if not selected and "interior" not in chosen:
                chosen["interior"] = (cell, selected)
            elif "corner" in kinds and "corner" not in chosen:
                chosen["corner"] = (cell, selected)
            elif kinds.intersection({"x", "y"}) and "periodic" not in chosen:
                chosen["periodic"] = (cell, selected)
        assert set(chosen) == {"interior", "periodic", "corner"}

        for cell, selected in chosen.values():
            cell_dofs = np.asarray(
                function_space.dofmap.cell_dofs(cell), dtype=np.int64
            )
            expansion = build_h2a_r2_cell_expansion(
                selected,
                cell_dofs,
                function_space.dofmap.index_map,
                index_map_bs=function_space.dofmap.index_map_bs,
                phase_x=floquet.phase_x,
                phase_y=floquet.phase_y,
                phase_corner=floquet.phase_corner,
            )
            local_block, _widths, _orientation = tabulate_task037_extra_h2a_cell_tensor(
                form,
                function_space,
                cell_tags,
                cell,
                geometry_tolerance=floquet_geometry_tolerance(cfg),
            )
            transformed = build_h2a_r2_transformed_block(local_block, expansion)
            dense = expansion.materialize_dense()
            for block in selected:
                for local_slave in block.slave_local_dofs:
                    _assert_expansion_row_matches_finalized_mpc(
                        expansion,
                        floquet,
                        function_space,
                        cell_dofs,
                        int(local_slave),
                    )
            vector = np.asarray(
                [
                    1.0 + 0.03 * index + 0.01j * (index + 1)
                    for index in range(expansion.independent_count)
                ],
                dtype=np.complex128,
            )
            expected = dense.conj().T @ (local_block @ (dense @ vector))
            observed = transformed @ vector
            assert np.all(np.isfinite(observed))
            assert np.linalg.norm(observed - expected) / np.linalg.norm(expected) <= 1.0e-11
            assert np.array_equal(
                expansion.coefficients,
                build_h2a_r2_cell_expansion(
                    selected,
                    cell_dofs,
                    function_space.dofmap.index_map,
                    index_map_bs=function_space.dofmap.index_map_bs,
                    phase_x=floquet.phase_x,
                    phase_y=floquet.phase_y,
                    phase_corner=floquet.phase_corner,
                ).coefficients,
            )
    finally:
        del floquet
