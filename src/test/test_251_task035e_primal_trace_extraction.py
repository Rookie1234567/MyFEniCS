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
            np.asarray([7.0 + 1.0j, -3.0 + 2.0j]),
        )
    )
    active = _distributed_vector(comm, active_values)
    ranges = tuple(comm.allgather(active.getOwnershipRange()))
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
                    ranges,
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
            active_rows=8,
            active_trace_rows=6,
        ),
        trace_constraints=constraints,
        active_trace_rows=4,
        appended_rows=2,
    )
    auxiliary = np.asarray([9.0 + 1.0j, 8.0 - 2.0j])
    return system, active, independent, auxiliary


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
