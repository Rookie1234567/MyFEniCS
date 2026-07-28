from __future__ import annotations

import os
from types import SimpleNamespace
from unittest import mock

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest

from src.solvers import hcurl_variable_p_assembly as variable_p_assembly


def _balanced_counts(total: int, size: int) -> tuple[int, ...]:
    quotient, remainder = divmod(total, size)
    return tuple(
        quotient + int(rank < remainder)
        for rank in range(size)
    )


def _distributed_vector(comm: MPI.Comm, values: np.ndarray) -> PETSc.Vec:
    values = np.asarray(values, dtype=np.complex128)
    counts = _balanced_counts(len(values), comm.size)
    vector = PETSc.Vec().createMPI(
        (counts[comm.rank], len(values)),
        comm=comm,
    )
    start, end = map(int, vector.getOwnershipRange())
    if end > start:
        vector.setValues(
            np.arange(start, end, dtype=PETSc.IntType),
            np.asarray(values[start:end], dtype=PETSc.ScalarType),
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
    vector.assemble()
    return vector


def _global_values(vector: PETSc.Vec) -> np.ndarray:
    local = np.asarray(
        vector.getArray(readonly=True),
        dtype=np.complex128,
    ).copy()
    return np.concatenate(vector.comm.tompi4py().allgather(local))


def _replace_global_values(vector: PETSc.Vec, values: np.ndarray) -> None:
    rows = np.arange(len(values), dtype=PETSc.IntType)
    vector.set(PETSc.ScalarType(0.0))
    vector.setValues(
        rows,
        np.asarray(values, dtype=PETSc.ScalarType),
        addv=PETSc.InsertMode.INSERT_VALUES,
    )
    vector.assemble()


def _matrix(comm: MPI.Comm, rows: int) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(
        size=(rows, rows),
        nnz=1,
        comm=comm,
    )
    matrix.assemble()
    return matrix


def _owner_of_row(
    ranges: tuple[tuple[int, int], ...],
    row: int,
) -> int:
    return next(
        rank
        for rank, (start, end) in enumerate(ranges)
        if start <= row < end
    )


def _balanced_ranges(
    total: int,
    size: int,
) -> tuple[tuple[int, int], ...]:
    counts = _balanced_counts(total, size)
    start = 0
    ranges = []
    for count in counts:
        ranges.append((start, start + count))
        start += count
    return tuple(ranges)


def _constrained_fixture(
    comm: MPI.Comm,
) -> tuple[SimpleNamespace, PETSc.Vec, dict[str, object]]:
    active_values = np.asarray(
        [
            1.0 + 0.2j,
            -0.3 + 0.4j,
            0.8 - 0.1j,
            -1.2 + 0.5j,
            0.7 + 0.3j,
            -0.9 - 0.2j,
            0.25 + 0.5j,
            -0.4 + 0.1j,
            0.6 - 0.3j,
            -0.2 - 0.7j,
        ],
        dtype=np.complex128,
    )
    active = _distributed_vector(comm, active_values)
    ranges = tuple(comm.allgather(active.getOwnershipRange()))
    trace_work_ranges = _balanced_ranges(6, comm.size)
    expansions = (
        np.asarray(
            [
                [1.0 + 0.0j, 0.0 + 0.0j],
                [0.0 + 0.0j, 1.0 + 0.0j],
                [0.5 + 0.2j, 0.0 - 0.25j],
            ],
            dtype=np.complex128,
        ),
        np.asarray(
            [
                [0.75 + 0.1j, 0.0 + 0.0j],
                [0.0 + 0.0j, 0.5 - 0.2j],
                [-0.2 + 0.1j, 1.0 + 0.0j],
            ],
            dtype=np.complex128,
        ),
    )
    blocks = []
    for block_index, expansion in enumerate(expansions):
        full_rows = np.arange(
            3 * block_index,
            3 * block_index + 3,
            dtype=np.int64,
        )
        blocks.append(
            SimpleNamespace(
                full_rows=full_rows,
                independent_rows=np.asarray([0, 1], dtype=np.int64),
                full_from_independent=expansion,
                active_vector_work_owner_rank=_owner_of_row(
                    trace_work_ranges,
                    int(full_rows[0]),
                ),
            )
        )
    work_blocks = tuple(
        block
        for block in blocks
        if block.active_vector_work_owner_rank == comm.rank
    )
    right_maps = {
        "cell0": np.asarray(
            [
                [0.3 + 0.1j, -0.2 + 0.0j],
                [0.1 - 0.1j, 0.4 + 0.2j],
                [-0.25 + 0.3j, 0.2 - 0.1j],
            ],
            dtype=np.complex128,
        ),
        "cell1": np.asarray(
            [
                [0.2 - 0.2j, 0.1 + 0.0j],
                [-0.3 + 0.1j, 0.25 + 0.2j],
                [0.4 + 0.0j, -0.1 + 0.3j],
            ],
            dtype=np.complex128,
        ),
    }
    left_source_maps = {
        "cell0": np.asarray(
            [
                [0.1 + 0.2j, 0.3 + 0.0j, -0.2 + 0.1j],
                [0.4 - 0.1j, -0.1 + 0.2j, 0.25 + 0.0j],
            ],
            dtype=np.complex128,
        ),
        "cell1": np.asarray(
            [
                [0.2 + 0.0j, -0.25 + 0.1j, 0.3 - 0.2j],
                [-0.1 + 0.3j, 0.4 + 0.0j, 0.15 + 0.1j],
            ],
            dtype=np.complex128,
        ),
    }
    cell_specs = (
        ("cell0", 0, np.asarray([6, 7], dtype=np.int64), blocks[0]),
        ("cell1", 1, np.asarray([8, 9], dtype=np.int64), blocks[1]),
    )
    local_recoveries = []
    local_constraint_cells = []
    for class_key, global_cell, interior_rows, block in cell_specs:
        owner = _owner_of_row(ranges, int(interior_rows[0]))
        if owner != comm.rank:
            continue
        local_recoveries.append(
            SimpleNamespace(
                class_key=class_key,
                cell=SimpleNamespace(
                    global_cell=global_cell,
                    interior_rows=interior_rows,
                    trace_rows=block.full_rows,
                ),
            )
        )
        local_constraint_cells.append(
            SimpleNamespace(
                global_cell=global_cell,
                independent_rows=block.independent_rows,
                full_trace_from_independent=block.full_from_independent,
            )
        )
    constraints = SimpleNamespace(
        independent_trace_rows=2,
        entity_blocks={
            index: block for index, block in enumerate(blocks)
        },
        work_owned_entity_blocks=work_blocks,
        owned_cells=tuple(local_constraint_cells),
    )
    system = SimpleNamespace(
        matrix=_matrix(comm, 2),
        entity_map=SimpleNamespace(
            mesh=SimpleNamespace(comm=comm),
            active_rows=10,
            active_trace_rows=6,
        ),
        trace_constraints=constraints,
        active_trace_rows=2,
        appended_rows=0,
        cell_recovery=tuple(local_recoveries),
        trace_from_interior_rhs_by_class=right_maps,
        interior_from_trace_by_class=left_source_maps,
        build_audit={},
    )
    reference = {
        "active_values": active_values,
        "blocks": tuple(blocks),
        "cell_specs": cell_specs,
        "right_maps": right_maps,
        "left_source_maps": left_source_maps,
    }
    return system, active, reference


def _unconstrained_fixture(
    comm: MPI.Comm,
) -> tuple[SimpleNamespace, PETSc.Vec, dict[str, object]]:
    active_values = np.asarray(
        [
            1.0 + 0.2j,
            -0.3 + 0.4j,
            0.8 - 0.1j,
            -1.2 + 0.5j,
            0.25 + 0.5j,
            -0.4 + 0.1j,
            0.6 - 0.3j,
            -0.2 - 0.7j,
        ],
        dtype=np.complex128,
    )
    active = _distributed_vector(comm, active_values)
    ranges = tuple(comm.allgather(active.getOwnershipRange()))
    right_maps = {
        "cell0": np.asarray(
            [[0.3 + 0.1j, -0.2], [0.1 - 0.1j, 0.4 + 0.2j]],
            dtype=np.complex128,
        ),
        "cell1": np.asarray(
            [[0.2 - 0.2j, 0.1], [-0.3 + 0.1j, 0.25 + 0.2j]],
            dtype=np.complex128,
        ),
    }
    left_source_maps = {
        "cell0": np.asarray(
            [[0.1 + 0.2j, 0.3], [0.4 - 0.1j, -0.1 + 0.2j]],
            dtype=np.complex128,
        ),
        "cell1": np.asarray(
            [[0.2, -0.25 + 0.1j], [-0.1 + 0.3j, 0.4]],
            dtype=np.complex128,
        ),
    }
    cell_specs = (
        (
            "cell0",
            0,
            np.asarray([4, 5], dtype=np.int64),
            np.asarray([0, 1], dtype=np.int64),
        ),
        (
            "cell1",
            1,
            np.asarray([6, 7], dtype=np.int64),
            np.asarray([2, 3], dtype=np.int64),
        ),
    )
    local_recoveries = []
    for class_key, global_cell, interior_rows, trace_rows in cell_specs:
        if _owner_of_row(ranges, int(interior_rows[0])) != comm.rank:
            continue
        local_recoveries.append(
            SimpleNamespace(
                class_key=class_key,
                cell=SimpleNamespace(
                    global_cell=global_cell,
                    interior_rows=interior_rows,
                    trace_rows=trace_rows,
                ),
            )
        )
    system = SimpleNamespace(
        matrix=_matrix(comm, 4),
        entity_map=SimpleNamespace(
            mesh=SimpleNamespace(comm=comm),
            active_rows=8,
            active_trace_rows=4,
        ),
        trace_constraints=None,
        active_trace_rows=4,
        appended_rows=0,
        cell_recovery=tuple(local_recoveries),
        trace_from_interior_rhs_by_class=right_maps,
        interior_from_trace_by_class=left_source_maps,
        build_audit={},
    )
    reference = {
        "active_values": active_values,
        "cell_specs": cell_specs,
        "right_maps": right_maps,
        "left_source_maps": left_source_maps,
    }
    return system, active, reference


def _dense_reference(
    reference: dict[str, object],
    *,
    side: str,
    constrained: bool,
) -> np.ndarray:
    active = np.asarray(reference["active_values"], dtype=np.complex128)
    target = np.zeros(2 if constrained else 4, dtype=np.complex128)
    cutoff = max(1.0e-30, 1.0e-14 * float(np.max(np.abs(active))))
    if constrained:
        for block in reference["blocks"]:
            projected = (
                block.full_from_independent.conj().T
                @ active[block.full_rows]
            )
            retained = np.abs(projected) > cutoff
            target[block.independent_rows[retained]] += projected[retained]
    else:
        retained = np.abs(active[:4]) > cutoff
        target[np.flatnonzero(retained)] += active[:4][retained]
    for class_key, _global_cell, interior_rows, trace_authority in reference[
        "cell_specs"
    ]:
        interior = active[interior_rows]
        if side == "right":
            correction = reference["right_maps"][class_key] @ interior
        else:
            correction = (
                reference["left_source_maps"][class_key].conj().T
                @ interior
            )
        if constrained:
            block = trace_authority
            correction = (
                block.full_from_independent.conj().T @ correction
            )
            rows = block.independent_rows
        else:
            rows = trace_authority
        retained = np.abs(correction) > cutoff
        target[rows[retained]] += correction[retained]
    return target


@pytest.mark.parametrize("side", ("right", "left"))
def test_serial_constrained_matches_old_dense_reference(side: str) -> None:
    system, active, reference = _constrained_fixture(MPI.COMM_SELF)
    with mock.patch.object(
        variable_p_assembly,
        "_global_active_vector_values",
        side_effect=AssertionError("dual condensation used full allgather"),
    ):
        reduced = (
            variable_p_assembly
            .condense_variable_p_active_vector_to_trace(
                system,
                active,
                side=side,
            )
        )
    try:
        np.testing.assert_allclose(
            _global_values(reduced),
            _dense_reference(
                reference,
                side=side,
                constrained=True,
            ),
            rtol=2.0e-14,
            atol=2.0e-14,
        )
        audit = system.build_audit["last_active_dual_condensation"]
        assert audit["python_full_vector_allgather_used"] is False
        assert audit["constraint_blocks_processed_exactly_once"] is True
        assert audit["independent_row_coverage_min"] == 2
        assert audit[
            "overlapping_independent_rows_accumulated_with_add"
        ] is True
        assert audit["side"] == side
    finally:
        reduced.destroy()
        active.destroy()
        system.matrix.destroy()


@pytest.mark.parametrize("side", ("right", "left"))
def test_serial_unconstrained_matches_old_dense_reference(side: str) -> None:
    system, active, reference = _unconstrained_fixture(MPI.COMM_SELF)
    reduced = (
        variable_p_assembly.condense_variable_p_active_vector_to_trace(
            system,
            active,
            side=side,
        )
    )
    try:
        np.testing.assert_allclose(
            _global_values(reduced),
            _dense_reference(
                reference,
                side=side,
                constrained=False,
            ),
            rtol=2.0e-14,
            atol=2.0e-14,
        )
        audit = system.build_audit["last_active_dual_condensation"]
        assert audit["constraint_mode"] == (
            "unconstrained_direct_owned_trace"
        )
        assert audit["active_selected_rows"][
            "full_vector_allgather_used"
        ] is False
    finally:
        reduced.destroy()
        active.destroy()
        system.matrix.destroy()


def test_default_exact_path_preserves_accumulated_tiny_trace_terms() -> None:
    system, active, reference = _constrained_fixture(MPI.COMM_SELF)
    values = np.zeros(10, dtype=np.complex128)
    values[0] = 4.0e-15
    values[3] = 4.0e-15
    values[9] = 1.0
    _replace_global_values(active, values)
    for matrix in reference["right_maps"].values():
        matrix.fill(0.0)
    expected = np.zeros(2, dtype=np.complex128)
    for block in reference["blocks"]:
        expected[block.independent_rows] += (
            block.full_from_independent.conj().T
            @ values[block.full_rows]
        )
    reduced = (
        variable_p_assembly.condense_variable_p_active_vector_to_trace(
            system,
            active,
            side="right",
        )
    )
    try:
        np.testing.assert_allclose(
            _global_values(reduced),
            expected,
            rtol=2.0e-14,
            atol=1.0e-29,
        )
        assert np.linalg.norm(expected) > 0.0
        assert system.build_audit["last_active_dual_condensation"][
            "default_exact_zero_only_filter"
        ] is True
    finally:
        reduced.destroy()
        active.destroy()
        system.matrix.destroy()


def test_default_exact_path_applies_operator_before_any_filter() -> None:
    system, active, reference = _unconstrained_fixture(MPI.COMM_SELF)
    values = np.zeros(8, dtype=np.complex128)
    values[0] = 1.0
    values[4] = 1.0e-16
    _replace_global_values(active, values)
    for matrix in reference["right_maps"].values():
        matrix.fill(0.0)
    reference["right_maps"]["cell0"][1, 0] = 2.0e7
    reduced = (
        variable_p_assembly.condense_variable_p_active_vector_to_trace(
            system,
            active,
            side="right",
        )
    )
    try:
        np.testing.assert_allclose(
            _global_values(reduced),
            np.asarray([1.0, 2.0e-9, 0.0, 0.0]),
            rtol=2.0e-14,
            atol=1.0e-24,
        )
    finally:
        reduced.destroy()
        active.destroy()
        system.matrix.destroy()


def test_missing_owned_cell_recovery_fails_interior_coverage() -> None:
    system, active, _reference = _unconstrained_fixture(MPI.COMM_SELF)
    system.cell_recovery = system.cell_recovery[:-1]
    try:
        with pytest.raises(
            RuntimeError,
            match="raw/interior row exactly once",
        ):
            variable_p_assembly.condense_variable_p_active_vector_to_trace(
                system,
                active,
                side="right",
            )
    finally:
        active.destroy()
        system.matrix.destroy()


@pytest.mark.skipif(
    os.environ.get(
        "MYFENICS_RUN_TASK035E_DUAL_CONDENSATION_MPI8_FIXTURE"
    )
    != "1",
    reason="Task035e MPI8 dual-condensation fixture is explicit opt-in",
)
def test_mpi8_opt_in_matches_old_dense_reference() -> None:
    comm = MPI.COMM_WORLD
    if comm.size != 8:
        pytest.skip("formal distributed dual-condensation fixture requires MPI8")
    for side in ("right", "left"):
        system, active, reference = _constrained_fixture(comm)
        input_ranges = tuple(comm.allgather(active.getOwnershipRange()))
        assert any(
            block.active_vector_work_owner_rank
            != _owner_of_row(input_ranges, int(block.full_rows[0]))
            for block in reference["blocks"]
        )
        with mock.patch.object(
            variable_p_assembly,
            "_global_active_vector_values",
            side_effect=AssertionError(
                "distributed dual condensation used full allgather"
            ),
        ):
            reduced = (
                variable_p_assembly
                .condense_variable_p_active_vector_to_trace(
                    system,
                    active,
                    side=side,
                )
            )
        try:
            np.testing.assert_allclose(
                _global_values(reduced),
                _dense_reference(
                    reference,
                    side=side,
                    constrained=True,
                ),
                rtol=2.0e-14,
                atol=2.0e-14,
            )
            audit = system.build_audit[
                "last_active_dual_condensation"
            ]
            assert audit["python_full_vector_allgather_used"] is False
            assert audit["constraint_blocks_processed_exactly_once"] is True
            assert audit["active_selected_rows"][
                "selected_unique_row_count_local"
            ] < system.entity_map.active_rows
        finally:
            reduced.destroy()
            active.destroy()
            system.matrix.destroy()
