from __future__ import annotations

import numpy as np
import pytest

from src.solvers.hcurl_h2b_block_smoother import (
    build_h2b_constrained_block_smoother,
)
from src.solvers.hcurl_r2_constrained_local_block import (
    build_h2a_r2_cell_expansion,
)
from src.solvers.hcurl_r2_factor_store import (
    H2AR2CellReference,
    H2AR2ClassInput,
    build_h2a_r2_factor_store,
)


class _IndexMap:
    def local_to_global(self, rows):
        return np.asarray(rows, dtype=np.int64)


def _expansion(count: int):
    rows = tuple(range(count))
    return build_h2a_r2_cell_expansion(
        (),
        rows,
        _IndexMap(),
        index_map_bs=1,
        phase_x=1.0 + 0.0j,
        phase_y=1.0 + 0.0j,
    )


def _cell_blocks():
    cells = ((0, 1, 2), (2, 3, 4), (4, 5))
    three = np.asarray(
        ((4.0, 1.0, 0.0), (1.0, 4.0, 1.0), (0.0, 1.0, 4.0)),
        dtype=np.complex128,
    )
    two = np.asarray(((4.0, 1.0), (1.0, 4.0)), dtype=np.complex128)
    blocks = (three, three.copy(), two)
    matrix = np.zeros((8, 8), dtype=np.complex128)
    for rows, block in zip(cells, blocks, strict=True):
        matrix[np.ix_(rows, rows)] += block
    matrix[6:, 6:] = np.eye(2, dtype=np.complex128)
    return cells, blocks, matrix


def _store():
    cells, blocks, _matrix = _cell_blocks()
    expansion_three = _expansion(3)
    expansion_two = _expansion(2)
    classes = (
        H2AR2ClassInput(
            0,
            "a" * 64,
            "c" * 64,
            expansion_three.pattern_sha256,
            expansion_three,
            blocks[0],
        ),
        H2AR2ClassInput(
            1,
            "b" * 64,
            "d" * 64,
            expansion_three.pattern_sha256,
            expansion_three,
            blocks[1],
        ),
        H2AR2ClassInput(
            2,
            "e" * 64,
            "f" * 64,
            expansion_two.pattern_sha256,
            expansion_two,
            blocks[2],
        ),
    )
    cells = (
        H2AR2CellReference(0, np.asarray(cells[0], dtype=np.int64)),
        H2AR2CellReference(1, np.asarray(cells[1], dtype=np.int64)),
        H2AR2CellReference(2, np.asarray(cells[2], dtype=np.int64)),
    )
    return build_h2a_r2_factor_store(
        classes,
        cells,
        identity={
            "source_identity": {"commit": "a" * 40, "clean": True},
            "config_identity": {"degree": 6, "h_nm": 10.0, "mpi_size": 1},
            "form_identity": {"proxy": "B0"},
            "cache_identity": {"name": "h2b-test"},
        },
        task037_extra_h2a_r2=True,
    )


def _build_smoother(action):
    return build_h2b_constrained_block_smoother(
        _store(),
        global_row_count=8,
        owned_slave_identity_rows=np.asarray((6, 7), dtype=np.int64),
        action=action,
        task037_extra_h2b=True,
    )


def test_h2b_sweep_is_colored_weighted_and_identity_rows_are_exact():
    cells, blocks, matrix = _cell_blocks()
    assembled = np.zeros_like(matrix)
    for rows, block in zip(cells, blocks, strict=True):
        assembled[np.ix_(rows, rows)] += block
    assembled[6:, 6:] = np.eye(2, dtype=np.complex128)
    assert np.array_equal(assembled, matrix)
    actions = []

    def action(source, target):
        assert np.array_equal(source[[6, 7]], np.zeros(2, dtype=np.complex128))
        actions.append(np.array(source, dtype=np.complex128, copy=True))
        target[:] = matrix @ source

    smoother = _build_smoother(action)
    repeated = _build_smoother(
        lambda source, target: target.__setitem__(slice(None), matrix @ source)
    )
    rhs = np.asarray(
        (1.0 + 0.2j, -0.4 + 0.8j, 0.7 - 0.1j, 0.2 + 0.3j,
         -0.6 + 0.5j, 0.9 - 0.7j, 1.3 - 0.2j, -0.5 + 0.4j),
        dtype=np.complex128,
    )

    first = smoother.apply(rhs)
    second = smoother.apply(rhs)
    repeated_result = repeated.apply(rhs)
    audit = smoother.audit

    assert np.array_equal(first, second)
    assert np.array_equal(first, repeated_result)
    assert np.array_equal(first[6:], rhs[6:])
    independent_residual = rhs - matrix @ first
    residual_error = np.linalg.norm(
        smoother.last_residual - independent_residual
    ) / max(np.linalg.norm(rhs), 1.0)
    assert residual_error <= 1.0e-13
    assert np.all(np.isfinite(first))
    assert np.all(np.isfinite(smoother.last_residual))
    assert np.array_equal(smoother.color_of_cell, np.asarray((0, 1, 0)))
    assert audit["color_count"] == 2
    assert audit["expected_action_count"] == 4
    assert audit["action_count"] == 4
    assert len(actions) == 8
    assert audit["same_color_rows_disjoint"] is True
    assert np.array_equal(
        smoother.multiplicity,
        np.asarray((1, 1, 2, 1, 2, 1, 0, 0), dtype=np.int32),
    )
    assert audit["multiplicity_min"] == 1
    assert audit["multiplicity_max"] == 2
    assert audit["partition_of_unity_closure_error"] <= 1.0e-15
    assert audit["factor_count"] == 2
    assert audit["materialization_identity"]["per_cell_factor"] is False
    assert audit["materialization_identity"]["global_matrix_materialized"] is False
    assert audit["materialization_identity"]["schur_materialized"] is False
    assert audit["materialization_identity"]["slab_matrix_materialized"] is False
    assert audit["materialization_identity"]["ksp_created"] is False
    assert audit["materialization_identity"]["dtn_used"] is False
    assert audit["materialization_identity"]["pde_solve_called"] is False
    assert audit["factor_plus_work_bytes"] == (
        audit["factor_payload_bytes"]
        + audit["retained_work_bytes"]
        + audit["per_apply_transient_bound_bytes"]
    )
    assert audit["retained_work_bytes"] == sum(
        audit["retained_work_components"].values()
    )
    assert audit["factor_plus_work_bytes"] < 500_000_000


def test_h2b_coloring_digest_and_payload_are_deterministic():
    _cells, _blocks, matrix = _cell_blocks()

    def action(source, target):
        target[:] = matrix @ source

    first = _build_smoother(action)
    second = _build_smoother(action)
    assert first.audit["color_digest"] == second.audit["color_digest"]
    assert np.array_equal(first.color_offsets, second.color_offsets)
    assert np.array_equal(first.color_cells, second.color_cells)
    assert first.audit["factor_plus_work_bytes"] == second.audit[
        "factor_plus_work_bytes"
    ]


@pytest.mark.parametrize(
    ("slaves", "message"),
    ((np.asarray((7,), dtype=np.int64), "coverage"),),
)
def test_h2b_fails_closed_for_coverage(slaves, message):
    with pytest.raises(ValueError, match=message):
        build_h2b_constrained_block_smoother(
            _store(),
            global_row_count=8,
            owned_slave_identity_rows=slaves,
            action=lambda source, target: target.__setitem__(slice(None), source),
            task037_extra_h2b=True,
        )


def test_h2b_requires_explicit_opt_in():
    with pytest.raises(ValueError, match="explicit task037 opt-in"):
        build_h2b_constrained_block_smoother(
            _store(),
            global_row_count=8,
            owned_slave_identity_rows=np.asarray((6, 7), dtype=np.int64),
            action=lambda source, target: target.__setitem__(slice(None), source),
        )


@pytest.mark.parametrize(
    "rhs",
    (
        np.ones(8, dtype=np.float64),
        np.ones(16, dtype=np.complex128)[::2],
    ),
)
def test_h2b_rejects_non_complex128_or_noncontiguous_rhs(rhs):
    smoother = _build_smoother(
        lambda source, target: target.__setitem__(slice(None), source)
    )
    with pytest.raises((TypeError, ValueError), match="complex128|NumPy"):
        smoother.apply(rhs)
