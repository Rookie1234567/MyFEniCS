from __future__ import annotations

import numpy as np
import pytest
from petsc4py import PETSc

from src.solvers import static_condensed_iterative as core
from src.solvers.static_fullspace_slab_factor_oracle import (
    FullSpaceSlabFactorOracle,
    assemble_fullspace_slab_matrix,
)
from src.solvers.static_fullspace_slab_oracle import (
    FullSpaceSlabBlockRecord,
    FullSpaceSlabCellRecord,
    apply_fullspace_slab_schur_action,
)


def _make_block(seed: float) -> FullSpaceSlabBlockRecord:
    if seed == 0.0:
        a_ii = np.asarray([[2.0 + 0.2j]])
        a_it = np.asarray([[0.3 - 0.1j, -0.2 + 0.15j, 0.1 + 0.05j]])
        a_ti = np.asarray(
            [[0.4 + 0.1j], [-0.15 + 0.25j], [0.2 - 0.05j]]
        )
        a_tt = np.asarray(
            [
                [3.0 + 0.1j, 0.2 - 0.1j, -0.1 + 0.05j],
                [0.4 + 0.05j, 2.5 - 0.2j, 0.15 + 0.1j],
                [-0.2 + 0.1j, 0.3 - 0.05j, 2.8 + 0.15j],
            ]
        )
    else:
        a_ii = np.asarray(
            [
                [1.8 + 0.1j, 0.2 - 0.15j],
                [-0.1 + 0.05j, 2.2 - 0.2j],
            ]
        )
        a_it = np.asarray(
            [
                [0.2 + 0.1j, -0.1 + 0.2j, 0.3 - 0.05j],
                [0.15 - 0.1j, 0.25 + 0.05j, -0.2 + 0.1j],
            ]
        )
        a_ti = np.asarray(
            [
                [0.3 + 0.1j, -0.15 + 0.05j],
                [0.2 - 0.1j, 0.35 + 0.15j],
                [-0.1 + 0.2j, 0.25 - 0.05j],
            ]
        )
        a_tt = np.asarray(
            [
                [2.7 + 0.2j, -0.1 + 0.05j, 0.2 - 0.1j],
                [0.3 + 0.1j, 3.1 - 0.15j, -0.2 + 0.05j],
                [0.15 - 0.05j, 0.25 + 0.1j, 2.4 + 0.1j],
            ]
        )
    recovery = np.linalg.solve(a_ii, -a_it)
    schur = a_tt + a_ti @ recovery
    return FullSpaceSlabBlockRecord(
        a_ii=a_ii,
        a_it=a_it,
        a_ti=a_ti,
        a_tt=a_tt,
        schur=schur,
    )


def _make_cells() -> tuple[FullSpaceSlabCellRecord, ...]:
    first = _make_block(0.0)
    second = _make_block(1.0)
    return (
        FullSpaceSlabCellRecord(
            block=first,
            canonical_cell_id=0,
            trace_expansion=np.asarray(
                [
                    [1.0, 0.0],
                    [0.2 + 0.1j, 0.0],
                    [0.0, np.exp(0.37j)],
                ]
            ),
            active_positions=np.asarray([0, 1]),
        ),
        FullSpaceSlabCellRecord(
            block=second,
            canonical_cell_id=1,
            trace_expansion=np.asarray(
                [
                    [0.0, 0.5],
                    [np.exp(-0.21j), 0.0],
                    [0.1 + 0.2j, 0.3 - 0.1j],
                ]
            ),
            active_positions=np.asarray([1, 3]),
        ),
    )


def _dense_reference(
    cells: tuple[FullSpaceSlabCellRecord, ...],
    shift: np.ndarray | None,
) -> tuple[np.ndarray, np.ndarray]:
    interior_counts = [cell.block.a_ii.shape[0] for cell in cells]
    trace_offset = sum(interior_counts)
    full_rows = trace_offset + 4
    full = np.zeros((full_rows, full_rows), dtype=np.complex128)
    schur = np.zeros((4, 4), dtype=np.complex128)
    interior_offset = 0
    for cell in cells:
        block = cell.block
        count = block.a_ii.shape[0]
        positions = trace_offset + cell.active_positions
        expansion = cell.trace_expansion.toarray()
        full[
            interior_offset : interior_offset + count,
            interior_offset : interior_offset + count,
        ] += block.a_ii
        full[
            interior_offset : interior_offset + count,
            positions,
        ] += block.a_it @ expansion
        full[
            positions,
            interior_offset : interior_offset + count,
        ] += expansion.conj().T @ block.a_ti
        full[np.ix_(positions, positions)] += (
            expansion.conj().T @ block.a_tt @ expansion
        )
        schur[np.ix_(cell.active_positions, cell.active_positions)] += (
            expansion.conj().T @ block.schur @ expansion
        )
        interior_offset += count
    if shift is not None:
        full[trace_offset:, trace_offset:] += np.diag(shift)
        schur += np.diag(shift)
    return full, schur


def _assert_matrix_action(matrix: PETSc.Mat, expected: np.ndarray) -> None:
    for column in range(expected.shape[1]):
        source, target = matrix.createVecs()
        source.set(0.0)
        source.getArray()[column] = 1.0
        matrix.mult(source, target)
        np.testing.assert_allclose(
            target.getArray(readonly=True),
            expected[:, column],
            rtol=0.0,
            atol=2.0e-13,
        )
        source.destroy()
        target.destroy()


def test_streamed_matrix_matches_independent_cell_formula_and_layout():
    cells = _make_cells()
    shift = np.asarray([0.07j, -0.03 + 0.02j, 0.04, -0.02j])
    expected, _ = _dense_reference(cells, shift)
    matrix, audit = assemble_fullspace_slab_matrix(
        cells,
        active_size=4,
        trace_shift=shift,
    )
    repeated_matrix, repeated_audit = assemble_fullspace_slab_matrix(
        tuple(reversed(cells)),
        active_size=4,
        trace_shift=shift,
    )
    try:
        assert matrix.getType() == "seqaij"
        assert audit["full_rows"] == 7
        assert audit["interior_rows"] == 3
        assert audit["trace_rows"] == 4
        assert audit["trace_offset"] == 3
        assert audit["cell_canonical_ids"] == [0, 1]
        assert audit["cell_interior_offsets"] == [0, 1]
        assert audit["trace_shift_applied"] is True
        assert audit["matrix_nnz"] > 0
        assert audit["matrix_csr_payload_bytes"] > 0
        assert repeated_audit["cell_canonical_ids"] == [0, 1]
        assert repeated_audit["cell_interior_offsets"] == [0, 1]
        assert audit["matrix_fingerprint"] == repeated_audit["matrix_fingerprint"]
        _assert_matrix_action(matrix, expected)
        _assert_matrix_action(repeated_matrix, expected)
    finally:
        repeated_matrix.destroy()
        matrix.destroy()


def test_exact_lu_trace_correction_matches_independent_schur_and_ilu_inventory():
    cells = _make_cells()
    shift = np.asarray([0.07j, -0.03 + 0.02j, 0.04, -0.02j])
    _, expected_schur = _dense_reference(cells, shift)
    rhs = np.asarray(
        [0.8 + 0.1j, -0.3 + 0.6j, 0.2 - 0.4j, 0.5 + 0.2j]
    )

    matrix, audit = assemble_fullspace_slab_matrix(
        cells,
        active_size=4,
        trace_shift=shift,
    )
    exact = FullSpaceSlabFactorOracle(matrix, audit, solver="lu")
    try:
        expected = np.linalg.solve(expected_schur, rhs)
        first = exact.apply_trace_rhs(rhs)
        second = exact.apply_trace_rhs(rhs)
        np.testing.assert_allclose(first, expected, rtol=0.0, atol=2.0e-12)
        assert np.array_equal(first, second)
        inventory = exact.inventory
        assert inventory["solver"] == "lu"
        assert inventory["factor_ordering"] == "rcm"
        assert inventory["ilu_level"] is None
        assert inventory["factor_nnz"] > 0
        assert inventory["factor_csr_payload_bytes"] > 0
        assert inventory["setup_seconds"] >= 0.0
        assert inventory["apply_count"] == 2
        assert inventory["apply_seconds"] >= 0.0
        assert inventory["setup_matrix_lifetime"] == "released after factor extraction"
    finally:
        exact.destroy()
        exact.destroy()

    ilu_matrix, ilu_audit = assemble_fullspace_slab_matrix(
        cells,
        active_size=4,
        trace_shift=shift,
    )
    ilu = FullSpaceSlabFactorOracle(ilu_matrix, ilu_audit, solver="ilu")
    try:
        first = ilu.apply_trace_rhs(rhs)
        second = ilu.apply_trace_rhs(rhs)
        assert np.isfinite(first).all()
        assert np.array_equal(first, second)
        inventory = ilu.inventory
        assert inventory["solver"] == "ilu"
        assert inventory["factor_ordering"] == "rcm"
        assert inventory["ilu_level"] == 0
        assert inventory["factor_nnz"] > 0
        assert inventory["factor_csr_payload_bytes"] > 0
        assert inventory["work_vector_payload_bytes"] == 2 * 7 * np.dtype(
            PETSc.ScalarType
        ).itemsize
        assert inventory["retained_payload_lower_bound_bytes"] == (
            inventory["factor_csr_payload_bytes"]
            + inventory["work_vector_payload_bytes"]
        )
        assert inventory["apply_count"] == 2
    finally:
        ilu.destroy()
        ilu.destroy()


def test_shifted_schur_contractions_payload_route_and_missing_iter20():
    cells = _make_cells()
    shift = np.asarray([0.07j, -0.03 + 0.02j, 0.04, -0.02j])
    residual = np.asarray(
        [0.8 + 0.1j, -0.3 + 0.6j, 0.2 - 0.4j, 0.5 + 0.2j]
    )
    current_correction = 0.25 * residual
    fullspace_correction = 0.4 * residual
    current_action = apply_fullspace_slab_schur_action(
        cells,
        current_correction,
        active_size=4,
        trace_shift=shift,
    )
    fullspace_action = apply_fullspace_slab_schur_action(
        cells,
        fullspace_correction,
        active_size=4,
        trace_shift=shift,
    )
    current_measurement = core._task037_g2_local_schur_contraction(
        residual,
        residual - current_action,
    )
    fullspace_measurement = core._task037_g2_local_schur_contraction(
        residual,
        residual - fullspace_action,
    )
    assert current_measurement["finite"] is True
    assert fullspace_measurement["finite"] is True
    assert current_measurement["input_norm"] == fullspace_measurement["input_norm"]
    assert np.isfinite(current_measurement["rho"])
    assert np.isfinite(fullspace_measurement["rho"])

    passing_route = core._task037_g2_factor_payload_route(
        {"retained_payload_lower_bound_bytes": 1000},
        {"retained_payload_lower_bound_bytes": 750},
    )
    assert passing_route["gate_pass"] is True
    assert passing_route["status"] == "pass_fullspace_ilu_only_route"
    closing_route = core._task037_g2_factor_payload_route(
        {"retained_payload_lower_bound_bytes": 1000},
        {"retained_payload_lower_bound_bytes": 751},
    )
    assert closing_route["gate_pass"] is False
    assert closing_route["status"] == "close_fullspace_ilu_only_route"
    factor_measurement = {
        "trace_rhs": {"finite": True, "trace_rhs_exact": True},
        "current_trace_ilu": {"finite": True},
        "fullspace_ilu": {
            "finite": True,
            "correction_finite": True,
            "deterministic": True,
        },
    }
    assert core._task037_g2_factor_status(
        passing_route,
        factor_measurement,
    )["status"] == "pass_fullspace_ilu_only_route"
    factor_measurement["fullspace_ilu"]["correction_finite"] = False
    assert core._task037_g2_factor_status(
        passing_route,
        factor_measurement,
    )["status"] == "close_fullspace_ilu_only_route"
    missing = core._task037_g2_factor_status(passing_route, None)
    assert missing == {
        "status": "missing_iter20",
        "iter20_gate_pass": False,
        "missing_iterations": [20],
    }


def test_factor_inventory_flag_requires_g2_identity_and_m3a_profile():
    with pytest.raises(ValueError, match="requires slab14 identity"):
        core._solve_static_condensed_fgmres_core(
            object(),
            screen_iterations=20,
            task037_extra_g2_slab14_factor_inventory=True,
            solver_profile="assembled",
        )
    with pytest.raises(ValueError, match="requires the M3a action-only profile"):
        core._solve_static_condensed_fgmres_core(
            object(),
            screen_iterations=20,
            task037_extra_g2_slab14_identity=True,
            task037_extra_g2_slab14_factor_inventory=True,
            solver_profile="assembled",
        )
