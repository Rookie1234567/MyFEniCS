from __future__ import annotations

import numpy as np
import pytest
from mpi4py import MPI

from src.solvers.hcurl_assembly_time_condensation import (
    _cell_trace_expansion,
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.static_fullspace_slab_oracle import (
    FullSpaceSlabCellRecord,
    measure_fullspace_slab_identity,
)
from src.test.test_224_task037_static_local_schur_action import _build_fixture


def _fixed_vectors(size: int) -> tuple[np.ndarray, ...]:
    indices = np.arange(size, dtype=np.float64)
    return tuple(
        np.sin((index + 1.0) * 0.17 * indices + 0.11 * index)
        + 1j * np.cos((index + 1.0) * 0.13 * indices - 0.07 * index)
        for index in range(3)
    )


def test_retain_one_oriented_fullspace_block_per_class_and_verify_identity():
    _mesh, cell_tags, function_space, compiled = _build_fixture(MPI.COMM_SELF)
    default = build_unconstrained_assembly_time_condensation(
        compiled,
        function_space,
        cell_tags,
    )
    assert default.retained_fullspace_slab_blocks_by_class is None
    assert default.build_audit["retained_fullspace_slab_blocks_enabled"] is False
    assert default.build_audit["retained_fullspace_slab_blocks_class_count_local"] == 0
    assert default.build_audit["retained_fullspace_slab_blocks_class_count_sum"] == 0
    assert default.build_audit["retained_fullspace_slab_blocks_bytes_local"] == 0
    assert default.build_audit["retained_fullspace_slab_blocks_bytes_sum"] == 0
    default.destroy()

    with pytest.raises(ValueError, match="cannot retain fullspace slab blocks"):
        build_unconstrained_assembly_time_condensation(
            compiled,
            function_space,
            cell_tags,
            retained_p4_core_research=True,
            retain_fullspace_slab_blocks_for_research=True,
        )

    retained = build_unconstrained_assembly_time_condensation(
        compiled,
        function_space,
        cell_tags,
        retain_local_schur_for_matrix_free=True,
        retain_fullspace_slab_blocks_for_research=True,
    )
    try:
        blocks = retained.retained_fullspace_slab_blocks_by_class
        schurs = retained.retained_local_schur_by_class
        assert blocks is not None
        assert schurs is not None
        class_keys = {cell.class_key for cell in retained.cell_recovery_maps}
        assert set(blocks) == class_keys
        assert set(schurs) == class_keys
        assert len(blocks) == len(class_keys)
        assert retained.build_audit[
            "retained_fullspace_slab_blocks_class_count_local"
        ] == len(blocks)
        assert retained.build_audit[
            "retained_fullspace_slab_blocks_class_count_sum"
        ] == retained.build_audit[
            "retained_fullspace_slab_blocks_class_count_local"
        ]
        assert retained.build_audit[
            "retained_fullspace_slab_blocks_bytes_local"
        ] == sum(
            int(array.nbytes)
            for block in blocks.values()
            for array in (
                block.a_ii,
                block.a_it,
                block.a_ti,
                block.a_tt,
                block.schur,
            )
        )
        assert retained.build_audit[
            "retained_fullspace_slab_blocks_bytes_sum"
        ] == retained.build_audit["retained_fullspace_slab_blocks_bytes_local"]
        for key, block in blocks.items():
            np.testing.assert_allclose(block.schur, schurs[key], rtol=0.0, atol=0.0)
            assert all(
                not array.flags.writeable
                for array in (
                    block.a_ii,
                    block.a_it,
                    block.a_ti,
                    block.a_tt,
                    block.schur,
                )
            )

        cell = retained.cell_recovery_maps[0]
        active_ids, expansion, _identity = _cell_trace_expansion(
            cell.trace_original_dofs,
            retained.trace_constraints,
        )
        oracle_cell = FullSpaceSlabCellRecord(
            block=blocks[cell.class_key],
            trace_expansion=expansion.toarray(),
            active_positions=np.arange(
                len(active_ids),
                dtype=np.int64,
            ),
        )
        result = measure_fullspace_slab_identity(
            (oracle_cell,),
            _fixed_vectors(len(active_ids)),
            active_size=len(active_ids),
        )
        assert result["vector_count"] == 3
        assert result["finite"] is True
        assert result["deterministic"] is True
        assert result["max_relative_error"] <= 1.0e-10
    finally:
        retained.destroy()
