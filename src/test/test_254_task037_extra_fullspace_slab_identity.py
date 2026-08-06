from __future__ import annotations

from dataclasses import replace

import numpy as np
import scipy.sparse as sparse

from src.solvers.static_fullspace_slab_oracle import (
    FullSpaceSlabBlockRecord,
    FullSpaceSlabCellRecord,
    measure_fullspace_slab_identity,
)


def _make_block(seed: float) -> FullSpaceSlabBlockRecord:
    a_ii = np.asarray(
        [
            [2.1 + 0.2j + seed, 0.3 - 0.1j],
            [0.1 + 0.4j, 1.7 - 0.2j + 0.5 * seed],
        ],
        dtype=np.complex128,
    )
    a_it = np.asarray(
        [
            [0.4 + 0.2j, -0.3 + 0.1j, 0.2 - 0.2j],
            [0.1 - 0.3j, 0.5 + 0.2j, -0.4 + 0.1j],
        ],
        dtype=np.complex128,
    )
    a_ti = np.asarray(
        [
            [0.2 + 0.5j, -0.1 + 0.2j],
            [0.6 - 0.1j, 0.3 + 0.4j],
            [-0.2 + 0.3j, 0.4 - 0.2j],
        ],
        dtype=np.complex128,
    )
    a_tt = np.asarray(
        [
            [3.0 + 0.1j, 0.2 - 0.3j, -0.4 + 0.2j],
            [0.5 + 0.2j, 2.4 - 0.2j, 0.1 + 0.5j],
            [-0.3 + 0.1j, 0.6 - 0.4j, 2.8 + 0.3j],
        ],
        dtype=np.complex128,
    )
    recovery = np.linalg.solve(a_ii, -a_it)
    # This is intentionally formed in the fixture, independently of the
    # oracle's full-space action path.
    schur = a_tt + a_ti @ recovery
    return FullSpaceSlabBlockRecord(
        a_ii=a_ii,
        a_it=a_it,
        a_ti=a_ti,
        a_tt=a_tt,
        schur=schur,
    )


def _make_cell(
    block: FullSpaceSlabBlockRecord,
    canonical_cell_id: int,
    active_positions: list[int],
    trace_expansion: np.ndarray,
) -> FullSpaceSlabCellRecord:
    return FullSpaceSlabCellRecord(
        block=block,
        canonical_cell_id=canonical_cell_id,
        trace_expansion=trace_expansion,
        active_positions=np.asarray(active_positions, dtype=np.int64),
    )


def _vectors() -> tuple[np.ndarray, ...]:
    return (
        np.asarray([1.0 + 0.2j, -0.4 + 0.7j, 0.3 - 0.5j, 0.8 + 0.1j]),
        np.asarray([-0.2 + 0.9j, 0.6 - 0.3j, -0.7 + 0.4j, 0.5 - 0.8j]),
        np.asarray(
            [
                np.sin(0.17) + 1j * np.cos(0.23),
                np.sin(0.31) + 1j * np.cos(0.41),
                np.sin(0.53) + 1j * np.cos(0.67),
                np.sin(0.79) + 1j * np.cos(0.89),
            ]
        ),
    )


def test_single_and_overlapping_cells_match_independent_schur_with_and_without_shift():
    block = _make_block(0.0)
    identity_expansion = np.eye(3, dtype=np.complex128)
    single = (_make_cell(block, 0, [0, 1, 2], identity_expansion),)
    assert sparse.isspmatrix_csr(single[0].trace_expansion)
    single_result = measure_fullspace_slab_identity(
        single,
        _vectors(),
        active_size=4,
    )
    assert single_result["cell_count"] == 1
    assert single_result["finite"] is True
    assert single_result["deterministic"] is True
    assert single_result["max_relative_error"] <= 1.0e-12

    phase = np.exp(0.37j)
    phase_expansion = np.asarray(
        [[0.0, 1.0], [phase, 0.0], [0.2 + 0.1j, 0.0]],
        dtype=np.complex128,
    )
    cells = (
        _make_cell(block, 0, [0, 1, 2], identity_expansion),
        _make_cell(block, 1, [1, 3], phase_expansion),
    )
    assert all(sparse.isspmatrix_csr(cell.trace_expansion) for cell in cells)
    for shift in (
        None,
        np.asarray([-0.1j, 0.03 - 0.02j, 0.05j, -0.04j]),
    ):
        result = measure_fullspace_slab_identity(
            cells,
            _vectors(),
            active_size=4,
            trace_shift=shift,
        )
        assert result["cell_count"] == 2
        assert result["vector_count"] == 3
        assert result["finite"] is True
        assert result["deterministic"] is True
        assert result["max_relative_error"] <= 1.0e-12
        assert result["max_determinism_relative_error"] == 0.0


def test_modified_schur_cannot_pass_identity():
    block = _make_block(0.0)
    cell = _make_cell(
        block,
        0,
        [0, 1, 2],
        np.eye(3, dtype=np.complex128),
    )
    bad_schur = block.schur.copy()
    bad_schur[0, 0] += 0.25 - 0.1j
    result = measure_fullspace_slab_identity(
        (replace(cell, block=replace(block, schur=bad_schur)),),
        _vectors(),
        active_size=4,
    )
    assert result["finite"] is True
    assert result["max_relative_error"] > 1.0e-12
