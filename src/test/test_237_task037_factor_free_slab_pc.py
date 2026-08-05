from __future__ import annotations

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.physical_slab_two_level import (
    build_owner_local_slab_diagonal,
    build_owner_local_slab_plan,
)
from src.solvers.static_factor_free_slab_pc import FactorFreeLocalSlabKrylovPc
from src.solvers.static_local_schur_action import create_static_local_schur_action
from src.test.test_234_task037_p2_trace_transfer import _spaces
from src.test.test_235_task037_p2_galerkin_auxiliary import (
    _assemble_fine_reference,
    _max_relative,
    _retained_p6_fixture,
    _vector,
)
from src.test.test_236_task037_p2_auxiliary_pc import _assembly_time_fixture


def _shifted_diagonal(diagonal, scale):
    shifted = diagonal.duplicate()
    shifted.getArray()[:] = (
        -1j
        * 0.1
        * np.maximum(np.abs(diagonal.getArray(readonly=True)), 1.0e-12 * scale)
    )
    shifted.assemble()
    return shifted


def _reference_restricted_action(
    reference,
    scatter,
    local_result,
    slab,
    plan,
    union,
    trial,
    result,
    values,
):
    trial.set(0.0)
    if plan.comm.rank == plan.slab_owners[slab]:
        trial.setValues(plan.owner_rows[slab], values)
    trial.assemble()
    reference.mult(trial, result)
    scatter.scatter(
        result,
        local_result,
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    if plan.comm.rank != plan.slab_owners[slab]:
        return np.empty(0, dtype=PETSc.ScalarType)
    positions = np.searchsorted(union, plan.owner_rows[slab])
    return np.asarray(
        local_result.getArray(readonly=True)[positions],
        dtype=PETSc.ScalarType,
    ).copy()


@pytest.mark.skipif(MPI.COMM_WORLD.size not in (1, 2), reason="requires serial or MPI2")
def test_factor_free_local_slab_action_and_two_step_krylov():
    comm = MPI.COMM_WORLD
    mesh_3d, (_V2, V6), (_C2, C6) = _spaces(comm)
    fine_condensed, schurs = _retained_p6_fixture(V6, C6)
    fine_condensed = _assembly_time_fixture(C6, fine_condensed, comm)
    fine_action, fine_action_context = create_static_local_schur_action(fine_condensed)
    reference = _assemble_fine_reference(V6, C6, schurs)
    diagonal, diagonal_audit = build_owner_local_slab_diagonal(fine_condensed)
    shifted = _shifted_diagonal(diagonal, diagonal_audit["global_diagonal_max_abs"])
    reference_diagonal = reference.createVecLeft()
    reference.getDiagonal(reference_diagonal)
    reference_diagonal.axpy(1.0, shifted)
    reference.setDiagonal(reference_diagonal)
    reference.assemble()

    plan = build_owner_local_slab_plan(
        fine_condensed,
        mesh_3d,
        domain_z=(0.0, 1.0),
        num_slabs=2,
        overlap_fraction=0.125,
    )
    pc = FactorFreeLocalSlabKrylovPc(fine_action, plan, shifted)

    template = reference.createVecRight()
    local_union = pc._union_indices
    local_result = PETSc.Vec().createSeq(local_union.size, comm=PETSc.COMM_SELF)
    global_is = PETSc.IS().createGeneral(local_union, comm=PETSc.COMM_SELF)
    local_is = PETSc.IS().createStride(
        local_union.size, first=0, step=1, comm=PETSc.COMM_SELF
    )
    reference_scatter = PETSc.Scatter().create(
        template, global_is, local_result, local_is
    )
    template.destroy()
    local_is.destroy()
    global_is.destroy()
    trial = reference.createVecRight()
    result = reference.createVecLeft()

    for slab in range(len(plan.slab_owners)):
        rows = plan.owner_rows[slab]
        values = np.asarray(
            np.sin(0.17 * np.arange(rows.size) + slab)
            + 1j * np.cos(0.11 * np.arange(rows.size) - slab),
            dtype=PETSc.ScalarType,
        )
        actual = pc._restricted_action(
            slab,
            values if comm.rank == plan.slab_owners[slab] else np.empty(0),
        )
        expected = _reference_restricted_action(
            reference,
            reference_scatter,
            local_result,
            slab,
            plan,
            local_union,
            trial,
            result,
            values,
        )
        if comm.rank == plan.slab_owners[slab]:
            absolute = float(np.max(np.abs(actual - expected), initial=0.0))
            relative = absolute / max(
                float(np.max(np.abs(expected), initial=0.0)), 1.0e-30
            )
            assert absolute <= 1.0e-11
            assert relative <= 1.0e-11

    action_calls_before_apply = pc._action_calls
    source = _vector(reference.createVecRight(), 237)
    first = reference.createVecLeft()
    second = reference.createVecLeft()
    pc.apply(source, first)
    pc.apply(source, second)
    repeat_absolute, repeat_relative = _max_relative(first, second)
    assert repeat_absolute <= 1.0e-11
    assert repeat_relative <= 1.0e-11
    audit = pc.diagnostics
    assert audit["local_krylov_steps"] == 2
    assert audit["outer_requires_fgmres"] is True
    assert audit["p6_slab_matrix_count"] == 0
    assert audit["p6_factor_count"] == 0
    assert audit["p6_factor_nnz"] == 0
    assert audit["global_A_materialized_by_pc"] is False
    assert audit["partition_weight_sum_error"] <= 1.0e-12
    assert 0.0 < audit["partition_weight_min"] <= 1.0
    assert 0.0 < audit["partition_weight_max"] <= 1.0
    assert (
        audit["restricted_action_calls"] - action_calls_before_apply
        == audit["expected_action_calls"]
    )
    assert np.isfinite(first.norm())

    reference.mult(first, result)
    result.axpy(-1.0, source)
    assert result.norm() < source.norm()

    pc._scatter.scatter(
        source,
        pc._local_source,
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    local_residual_ratio = float("inf")
    for slab in range(2):
        if comm.rank == plan.slab_owners[slab]:
            positions = pc._positions_by_slab[slab]
            rhs = pc._local_source.getArray(readonly=True)[positions].copy()
        else:
            rhs = np.empty(0, dtype=PETSc.ScalarType)
        correction, _happy_breakdown = pc._two_step_gmres(slab, rhs)
        residual = pc._restricted_action(
            slab,
            correction if comm.rank == plan.slab_owners[slab] else np.empty(0),
        )
        if comm.rank == plan.slab_owners[slab]:
            local_residual_ratio = float(np.linalg.norm(rhs - residual)) / max(
                float(np.linalg.norm(rhs)), 1.0e-30
            )
    local_residual_ratio = comm.allreduce(local_residual_ratio, op=MPI.MIN)
    assert local_residual_ratio < 1.0

    if comm.size == 2:
        ranges = tuple(comm.allgather(tuple(map(int, source.getOwnershipRange()))))
        remote_rows = 0
        for slab, owner in enumerate(plan.slab_owners):
            if comm.rank == owner:
                start, end = ranges[owner]
                remote_rows += int(
                    np.count_nonzero(
                        (plan.owner_rows[slab] < start) | (plan.owner_rows[slab] >= end)
                    )
                )
        assert comm.allreduce(remote_rows, op=MPI.SUM) > 0

    print(
        "FACTOR_FREE_SLAB_AUDIT",
        {
            "repeat_absolute": repeat_absolute,
            "repeat_relative": repeat_relative,
            "local_residual_ratio": local_residual_ratio,
            "partition_weight_sum_error": audit["partition_weight_sum_error"],
            "restricted_action_calls": audit["restricted_action_calls"],
            "p6_slab_matrix_count": audit["p6_slab_matrix_count"],
            "p6_factor_count": audit["p6_factor_count"],
        },
    )

    result.destroy()
    trial.destroy()
    reference_scatter.destroy()
    local_result.destroy()
    source.destroy()
    first.destroy()
    second.destroy()
    pc.destroy()
    reference_diagonal.destroy()
    shifted.destroy()
    diagonal.destroy()
    fine_action_context.destroy(fine_action)
    fine_action.destroy()
    reference.destroy()
