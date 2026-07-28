from __future__ import annotations

import os
from types import SimpleNamespace

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest

from src.solvers.hcurl_variable_p_assembly import (
    extract_variable_p_active_primal_to_reduced,
)
from src.solvers.hcurl_variable_p_reduction import (
    VariablePAssemblyTimeReduction,
)


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


def _matrix(comm: MPI.Comm, rows: int) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(
        size=(rows, rows),
        nnz=1,
        comm=comm,
    )
    matrix.assemble()
    return matrix


def _unconstrained_system(
    comm: MPI.Comm,
) -> tuple[SimpleNamespace, PETSc.Vec]:
    trace = np.asarray(
        [1.0 + 0.2j, -0.3 + 0.4j, 0.8 - 0.1j, -1.2 + 0.5j],
        dtype=np.complex128,
    )
    active = np.concatenate(
        (trace, np.asarray([7.0 + 1.0j, -3.0 + 2.0j]))
    )
    system = SimpleNamespace(
        matrix=_matrix(comm, 6),
        entity_map=SimpleNamespace(
            mesh=SimpleNamespace(comm=comm),
            active_rows=6,
            active_trace_rows=4,
        ),
        trace_constraints=None,
        active_trace_rows=4,
        appended_rows=2,
    )
    return system, _distributed_vector(comm, active)


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


def _constrained_system(
    comm: MPI.Comm,
) -> tuple[
    SimpleNamespace,
    PETSc.Vec,
    np.ndarray,
    np.ndarray,
]:
    independent = np.asarray(
        [1.0 + 0.2j, -0.3 + 0.4j, 0.8 - 0.1j, -1.2 + 0.5j],
        dtype=np.complex128,
    )
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
                [1.0 + 0.0j, 0.0 + 0.0j],
                [0.0 + 0.0j, 1.0 + 0.0j],
                [-0.2 + 0.1j, 0.75 + 0.0j],
            ],
            dtype=np.complex128,
        ),
    )
    full_trace = np.concatenate(
        (
            expansions[0] @ independent[:2],
            expansions[1] @ independent[2:],
        )
    )
    active_values = np.concatenate(
        (
            full_trace,
            np.asarray(
                [
                    7.0 + 1.0j,
                    -3.0 + 2.0j,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                ],
                dtype=np.complex128,
            ),
        )
    )
    active = _distributed_vector(comm, active_values)
    trace_work_ranges = _balanced_ranges(6, comm.size)
    blocks = []
    for block_index, expansion in enumerate(expansions):
        full_rows = np.arange(
            3 * block_index,
            3 * block_index + 3,
            dtype=np.int64,
        )
        independent_rows = np.arange(
            2 * block_index,
            2 * block_index + 2,
            dtype=np.int64,
        )
        blocks.append(
            SimpleNamespace(
                full_rows=full_rows,
                independent_rows=independent_rows,
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
    constraints = SimpleNamespace(
        independent_trace_rows=4,
        entity_blocks={
            index: block for index, block in enumerate(blocks)
        },
        work_owned_entity_blocks=work_blocks,
    )
    system = SimpleNamespace(
        matrix=_matrix(comm, 6),
        entity_map=SimpleNamespace(
            mesh=SimpleNamespace(comm=comm),
            active_rows=len(active_values),
            active_trace_rows=6,
        ),
        trace_constraints=constraints,
        active_trace_rows=4,
        appended_rows=2,
    )
    auxiliary = np.asarray([9.0 + 1.0j, 8.0 - 2.0j])
    return system, active, independent, auxiliary


def _wide_root_anchor_system(
    comm: MPI.Comm,
) -> tuple[
    SimpleNamespace,
    PETSc.Vec,
    np.ndarray,
    np.ndarray,
]:
    independent = np.asarray(
        [1.0 + 0.2j, -0.3 + 0.4j, 0.8 - 0.1j],
        dtype=np.complex128,
    )
    root_rows = ("root-0", "root-1", "root-2")
    root_transform = np.asarray(
        [
            [0.0 + 0.0j, 1.0j],
            [1.0 + 0.0j, 0.0 + 0.0j],
        ],
        dtype=np.complex128,
    )
    root_physical = np.eye(2, dtype=np.complex128)
    final_root_physical = np.ones((1, 1), dtype=np.complex128)
    slave_physical = np.asarray(
        [
            [0.5 + 0.2j, 0.0 - 0.25j, 0.4 + 0.1j],
            [-0.2 + 0.1j, 0.75 + 0.0j, -0.1 + 0.3j],
        ],
        dtype=np.complex128,
    )
    block_data = (
        (
            np.arange(0, 2, dtype=np.int64),
            np.arange(0, 2, dtype=np.int64),
            root_transform,
            root_physical,
            (root_rows[0], root_rows[1]),
        ),
        (
            np.arange(2, 3, dtype=np.int64),
            np.arange(2, 3, dtype=np.int64),
            np.eye(1, dtype=np.complex128),
            final_root_physical,
            (root_rows[2],),
        ),
        (
            np.arange(3, 5, dtype=np.int64),
            np.arange(0, 3, dtype=np.int64),
            np.eye(2, dtype=np.complex128),
            slave_physical,
            ("slave-0", "slave-1"),
        ),
    )
    trace_work_ranges = _balanced_ranges(5, comm.size)
    blocks = []
    full_values = []
    for (
        full_rows,
        independent_rows,
        transform,
        physical_expansion,
        physical_rows,
    ) in block_data:
        expansion = transform @ physical_expansion
        full_values.append(expansion @ independent[independent_rows])
        blocks.append(
            SimpleNamespace(
                full_rows=full_rows,
                independent_rows=independent_rows,
                full_from_independent=expansion,
                physical_from_independent=physical_expansion,
                canonical_to_dolfinx=transform,
                physical_entity=SimpleNamespace(rows=physical_rows),
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
    constraints = SimpleNamespace(
        independent_trace_rows=3,
        authority=SimpleNamespace(
            graph=SimpleNamespace(root_rows=root_rows)
        ),
        entity_blocks={
            index: block for index, block in enumerate(blocks)
        },
        work_owned_entity_blocks=work_blocks,
    )
    system = SimpleNamespace(
        matrix=_matrix(comm, 5),
        entity_map=SimpleNamespace(
            mesh=SimpleNamespace(comm=comm),
            active_rows=5,
            active_trace_rows=5,
        ),
        trace_constraints=constraints,
        active_trace_rows=3,
        appended_rows=2,
    )
    auxiliary = np.asarray([9.0 + 1.0j, 8.0 - 2.0j])
    return (
        system,
        _distributed_vector(comm, np.concatenate(full_values)),
        independent,
        auxiliary,
    )


def _reduction(system: SimpleNamespace) -> VariablePAssemblyTimeReduction:
    return VariablePAssemblyTimeReduction(
        system=system,
        transfer=SimpleNamespace(),
        degree_plan=SimpleNamespace(),
        build_audit={},
    )


def test_unconstrained_primal_trace_and_explicit_auxiliary_tail() -> None:
    system, active = _unconstrained_system(MPI.COMM_SELF)
    auxiliary = np.asarray([9.0 + 1.0j, 8.0 - 2.0j])
    reduced, audit = extract_variable_p_active_primal_to_reduced(
        system,
        active,
        auxiliary_reduced_values=auxiliary,
    )
    try:
        expected = np.concatenate(
            (
                _global_values(active)[:4],
                auxiliary,
            )
        )
        assert np.array_equal(_global_values(reduced), expected)
        assert audit["constraint_mode"] == "direct_owned_trace"
        assert audit["left_inverse_method"] == "not_required"
        assert audit["raw_trace_rows_exactly_once"] is True
        assert audit["independent_rows_exactly_once"] is True
        assert audit["full_vector_allgather_used"] is False
    finally:
        reduced.destroy()
        active.destroy()
        system.matrix.destroy()


def test_auxiliary_tail_length_and_finite_values_fail_closed() -> None:
    system, active = _unconstrained_system(MPI.COMM_SELF)
    try:
        with pytest.raises(ValueError, match="appended_rows"):
            extract_variable_p_active_primal_to_reduced(
                system,
                active,
                auxiliary_reduced_values=np.asarray([1.0 + 0.0j]),
            )
        with pytest.raises(ValueError, match="non-finite"):
            extract_variable_p_active_primal_to_reduced(
                system,
                active,
                auxiliary_reduced_values=np.asarray(
                    [np.nan + 0.0j, 1.0 + 0.0j]
                ),
            )
    finally:
        active.destroy()
        system.matrix.destroy()


def test_constrained_primal_uses_stable_left_inverse_and_roundtrip() -> None:
    system, active, independent, auxiliary = _constrained_system(
        MPI.COMM_SELF
    )
    reduced, audit = _reduction(system).extract_primal_to_reduced(
        active,
        auxiliary_reduced_values=auxiliary,
    )
    try:
        assert np.allclose(
            _global_values(reduced),
            np.concatenate((independent, auxiliary)),
            rtol=2.0e-14,
            atol=2.0e-14,
        )
        assert audit["constraint_mode"] == "owner_routed_entity_blocks"
        assert audit["left_inverse_block_count_global"] == 2
        assert audit["maximum_block_roundtrip_relative_l2"] <= 5.0e-10
        assert audit["global_roundtrip_relative_l2"] <= 5.0e-10
        assert audit["raw_trace_row_coverage_min"] == 1
        assert audit["raw_trace_row_coverage_max"] == 1
        assert audit["independent_row_coverage_min"] == 1
        assert audit["independent_row_coverage_max"] == 1
        assert audit["replicated_active_full_vector_bytes_per_rank"] == 0
        assert audit["active_selected_rows"]["full_vector_allgather_used"] is False
    finally:
        reduced.destroy()
        active.destroy()
        system.matrix.destroy()


def test_physical_root_anchors_support_wide_slave_block() -> None:
    system, active, independent, auxiliary = _wide_root_anchor_system(
        MPI.COMM_SELF
    )
    reduced, audit = _reduction(system).extract_primal_to_reduced(
        active,
        auxiliary_reduced_values=auxiliary,
    )
    try:
        assert np.allclose(
            _global_values(reduced),
            np.concatenate((independent, auxiliary)),
            rtol=2.0e-14,
            atol=2.0e-14,
        )
        assert audit["physical_root_anchor_mode"] is True
        assert audit["left_inverse_method"] == (
            "physical_root_anchor_plus_global_constraint_roundtrip"
        )
        assert audit["left_inverse_block_count_global"] == 0
        assert audit["physical_root_anchor_row_count_global"] == 3
        assert audit["wide_constraint_block_count_global"] == 1
        assert audit["slave_blocks_validated_by_global_roundtrip"] is True
        assert audit["independent_rows_exactly_once"] is True
        assert audit["global_roundtrip_relative_l2"] <= 5.0e-10
        assert audit["full_vector_allgather_used"] is False
    finally:
        reduced.destroy()
        active.destroy()
        system.matrix.destroy()


def test_physical_root_anchor_roundtrip_rejects_nonconforming_slave() -> None:
    system, active, _independent, auxiliary = _wide_root_anchor_system(
        MPI.COMM_SELF
    )
    active.setValue(
        4,
        active.getValue(4) + PETSc.ScalarType(0.25 - 0.1j),
        addv=PETSc.InsertMode.INSERT_VALUES,
    )
    active.assemble()
    try:
        with pytest.raises(
            RuntimeError,
            match="physical-root primal trace round trip failed",
        ):
            extract_variable_p_active_primal_to_reduced(
                system,
                active,
                auxiliary_reduced_values=auxiliary,
            )
    finally:
        active.destroy()
        system.matrix.destroy()


def test_nonconforming_primal_trace_fails_roundtrip_gate() -> None:
    system, active, _independent, auxiliary = _constrained_system(
        MPI.COMM_SELF
    )
    active.setValue(
        2,
        active.getValue(2) + PETSc.ScalarType(0.25 + 0.1j),
        addv=PETSc.InsertMode.INSERT_VALUES,
    )
    active.assemble()
    try:
        with pytest.raises(RuntimeError, match="not conforming"):
            extract_variable_p_active_primal_to_reduced(
                system,
                active,
                auxiliary_reduced_values=auxiliary,
            )
    finally:
        active.destroy()
        system.matrix.destroy()


def test_legacy_replicated_blocks_are_owner_filtered() -> None:
    system, active, independent, auxiliary = _constrained_system(
        MPI.COMM_SELF
    )
    system.trace_constraints.work_owned_entity_blocks = None
    reduced, audit = extract_variable_p_active_primal_to_reduced(
        system,
        active,
        auxiliary_reduced_values=auxiliary,
    )
    try:
        assert np.allclose(
            _global_values(reduced),
            np.concatenate((independent, auxiliary)),
            rtol=2.0e-14,
            atol=2.0e-14,
        )
        assert audit["constraint_mode"] == (
            "legacy_replicated_entity_blocks_owner_filtered"
        )
    finally:
        reduced.destroy()
        active.destroy()
        system.matrix.destroy()


@pytest.mark.skipif(
    os.environ.get(
        "MYFENICS_RUN_TASK035E_PRIMAL_TRACE_MPI8_FIXTURE"
    )
    != "1",
    reason="Task035e MPI8 primal-trace fixture is explicit opt-in",
)
def test_mpi8_opt_in_owner_routed_primal_trace_fixture() -> None:
    comm = MPI.COMM_WORLD
    if comm.size != 8:
        pytest.skip("formal owner-routed fixture requires MPI8")
    system, active, independent, auxiliary = _constrained_system(comm)
    input_ranges = tuple(comm.allgather(active.getOwnershipRange()))
    assert any(
        block.active_vector_work_owner_rank
        != _owner_of_row(input_ranges, int(block.full_rows[0]))
        for block in system.trace_constraints.entity_blocks.values()
    )
    reduced, audit = _reduction(system).extract_primal_to_reduced(
        active,
        auxiliary_reduced_values=auxiliary,
    )
    try:
        assert np.allclose(
            _global_values(reduced),
            np.concatenate((independent, auxiliary)),
            rtol=2.0e-14,
            atol=2.0e-14,
        )
        global_fields = {
            "pass": audit["pass"],
            "raw": audit["raw_trace_rows_exactly_once"],
            "independent": audit["independent_rows_exactly_once"],
            "relative": audit["global_roundtrip_relative_l2"],
            "no_allgather": audit["full_vector_allgather_used"],
        }
        packets = comm.allgather(global_fields)
        assert all(packet == packets[0] for packet in packets[1:])
        assert global_fields == {
            "pass": True,
            "raw": True,
            "independent": True,
            "relative": pytest.approx(0.0, abs=5.0e-15),
            "no_allgather": False,
        }
    finally:
        reduced.destroy()
        active.destroy()
        system.matrix.destroy()

    wide_system, wide_active, wide_independent, wide_auxiliary = (
        _wide_root_anchor_system(comm)
    )
    wide_reduced, wide_audit = _reduction(
        wide_system
    ).extract_primal_to_reduced(
        wide_active,
        auxiliary_reduced_values=wide_auxiliary,
    )
    try:
        assert np.allclose(
            _global_values(wide_reduced),
            np.concatenate((wide_independent, wide_auxiliary)),
            rtol=2.0e-14,
            atol=2.0e-14,
        )
        assert wide_audit["physical_root_anchor_mode"] is True
        assert wide_audit["wide_constraint_block_count_global"] == 1
        assert wide_audit["independent_rows_exactly_once"] is True
    finally:
        wide_reduced.destroy()
        wide_active.destroy()
        wide_system.matrix.destroy()
