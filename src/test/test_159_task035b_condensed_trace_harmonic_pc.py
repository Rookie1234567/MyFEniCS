"""Analytic and MPI qualification for the opt-in trace-harmonic PC."""

from __future__ import annotations

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest

from src.solvers.condensed_trace_harmonic_pc import (
    DenseTraceHarmonicBlockSchur,
    PetscTraceHarmonicBlockSchurPc,
    TraceHarmonicPartition,
    configure_trace_harmonic_block_schur_ksp,
    trace_harmonic_block_schur_contract,
)


def _values() -> np.ndarray:
    values = np.zeros((8, 8), dtype=np.complex128)
    values[:3, :3] = np.asarray(
        [
            [4.5 + 0.2j, -0.4, 0.15j],
            [0.2 - 0.1j, 3.8 + 0.3j, -0.35],
            [0.1, -0.25j, 4.1 - 0.15j],
        ]
    )
    values[3:6, 3:6] = np.asarray(
        [
            [3.6 - 0.1j, 0.25, -0.1j],
            [-0.3 + 0.05j, 4.2 + 0.2j, 0.4],
            [0.2j, -0.15, 3.9 + 0.1j],
        ]
    )
    values[:3, 6:] = np.asarray(
        [
            [0.45 + 0.1j, -0.2],
            [0.15j, 0.35 - 0.05j],
            [-0.3, 0.12 + 0.08j],
        ]
    )
    values[3:6, 6:] = np.asarray(
        [
            [-0.25j, 0.3],
            [0.22 - 0.1j, -0.18],
            [0.11, 0.27 + 0.06j],
        ]
    )
    values[6:, :3] = np.asarray(
        [
            [0.31 - 0.02j, -0.17, 0.26j],
            [0.14, 0.28 + 0.04j, -0.22],
        ]
    )
    values[6:, 3:6] = np.asarray(
        [
            [0.19, -0.24j, 0.16 + 0.03j],
            [-0.21 + 0.02j, 0.13, 0.29],
        ]
    )
    values[6:, 6:] = np.asarray(
        [
            [2.4 + 0.2j, -0.18 + 0.04j],
            [0.12 - 0.03j, 2.1 - 0.1j],
        ]
    )
    return values


def _partition(*, explicit_owners: bool = False) -> TraceHarmonicPartition:
    owners = None
    if explicit_owners:
        owners = (0, min(1, MPI.COMM_WORLD.size - 1))
    return TraceHarmonicPartition(
        local_blocks=(
            np.asarray([0, 1, 2], dtype=PETSc.IntType),
            np.asarray([3, 4, 5], dtype=PETSc.IntType),
        ),
        interface_rows=np.asarray([6, 7], dtype=PETSc.IntType),
        block_owners=owners,
    )


def _matrix(comm: MPI.Comm = MPI.COMM_WORLD) -> PETSc.Mat:
    values = _values()
    matrix = PETSc.Mat().createAIJ([8, 8], nnz=(8, 8), comm=comm)
    start, end = matrix.getOwnershipRange()
    columns = np.arange(8, dtype=PETSc.IntType)
    for row in range(start, end):
        matrix.setValues(row, columns, values[row, :])
    matrix.assemble()
    return matrix


def _rhs(matrix: PETSc.Mat) -> PETSc.Vec:
    rhs = matrix.createVecRight()
    start, end = rhs.getOwnershipRange()
    indices = np.arange(start, end, dtype=np.float64)
    rhs.getArray()[:] = (
        np.sin(0.31 * (indices + 1.0))
        + 1j * np.cos(0.17 * (indices + 2.0))
    )
    return rhs


def _gather(vector: PETSc.Vec) -> np.ndarray:
    comm = vector.getComm().tompi4py()
    start, end = vector.getOwnershipRange()
    packet = (
        int(start),
        int(end),
        np.asarray(
            vector.getArray(readonly=True), dtype=np.complex128
        ).copy(),
    )
    result = np.empty(vector.getSize(), dtype=np.complex128)
    for packet_start, packet_end, values in comm.allgather(packet):
        result[packet_start:packet_end] = values
    return result


def test_dense_block_ldu_matches_direct_solve_and_harmonic_identity() -> None:
    values = _values()
    partition = _partition()
    preconditioner = DenseTraceHarmonicBlockSchur(values, partition)
    rhs = np.asarray(
        [0.4 + 0.1j, -0.2j, 0.7, 0.3, -0.4 + 0.2j, 0.1j, 1.0, -0.5],
        dtype=np.complex128,
    )

    actual = preconditioner.solve(rhs)
    expected = np.linalg.solve(values, rhs)
    np.testing.assert_allclose(actual, expected, rtol=2.0e-13, atol=2.0e-13)
    assert preconditioner.explicit_relative_residual(rhs) < 2.0e-13

    gamma = partition.interface_rows
    manual_schur = values[np.ix_(gamma, gamma)].copy()
    for block, harmonic in zip(
        partition.local_blocks,
        preconditioner.harmonic_extensions,
        strict=True,
    ):
        np.testing.assert_allclose(
            values[np.ix_(block, block)] @ harmonic
            + values[np.ix_(block, gamma)],
            0.0,
            rtol=2.0e-13,
            atol=2.0e-13,
        )
        manual_schur += values[np.ix_(gamma, block)] @ harmonic
    np.testing.assert_allclose(
        preconditioner.coarse_matrix,
        manual_schur,
        rtol=2.0e-13,
        atol=2.0e-13,
    )


def test_partition_and_cross_block_coupling_fail_closed() -> None:
    with pytest.raises(ValueError, match="disjoint"):
        TraceHarmonicPartition(
            local_blocks=(
                np.asarray([0, 1]),
                np.asarray([1, 2]),
            ),
            interface_rows=np.asarray([3]),
        )

    incomplete = TraceHarmonicPartition(
        local_blocks=(np.asarray([0, 1]),),
        interface_rows=np.asarray([3]),
    )
    with pytest.raises(ValueError, match="cover every matrix row"):
        incomplete.validate_cover(4)

    coupled = _values()
    coupled[1, 4] = 1.0e-3
    with pytest.raises(RuntimeError, match="zero direct coupling"):
        DenseTraceHarmonicBlockSchur(coupled, _partition())


def test_petsc_action_is_exact_and_factor_inventory_is_complete() -> None:
    matrix = _matrix()
    rhs = _rhs(matrix)
    solution = matrix.createVecRight()
    context = PetscTraceHarmonicBlockSchurPc(
        matrix,
        _partition(explicit_owners=True),
    )
    try:
        context.apply(None, rhs, solution)
        np.testing.assert_allclose(
            _gather(solution),
            np.linalg.solve(_values(), _gather(rhs)),
            rtol=3.0e-13,
            atol=3.0e-13,
        )
        certificate = context.certify_explicit_residual(
            rhs, tolerance=1.0e-11
        )
        assert certificate["pass"] is True
        assert certificate["relative_residual"] < 3.0e-13

        diagnostics = context.diagnostics
        assert diagnostics["cross_block_coupling_gate"]["gate_pass"] is True
        assert diagnostics["local_dense_factor_count"] == 2
        assert sum(diagnostics["local_dense_factor_count_by_rank"]) == 2
        assert diagnostics["coarse_dimension"] == 2
        assert diagnostics["coarse_dense_lu_replica_count"] == MPI.COMM_WORLD.size
        assert diagnostics["global_sparse_direct_factor_count"] == 0
        assert diagnostics["global_sparse_direct_factor_nnz"] == 0
        assert diagnostics["global_fine_sparse_factor_nnz"] == 0
        assert diagnostics["mumps_symbolic_or_numeric_created"] is False
        assert diagnostics["global_fine_factor_free"] is True
        assert diagnostics["strictly_factorless"] is False
        assert diagnostics["all_factor_storage_disclosed"] is True
        assert diagnostics["replicated_full_vector_workspace"] is True
        assert diagnostics["formal_pde_status"] == "not_run"
        assert diagnostics["explicit_residual_reports"][-1]["pass"] is True
    finally:
        context.destroy()
        solution.destroy()
        rhs.destroy()
        matrix.destroy()


def test_programmatic_fgmres_ksp_converges_without_raw_options() -> None:
    matrix = _matrix()
    rhs = _rhs(matrix)
    solution = matrix.createVecRight()
    action = matrix.createVecLeft()
    ksp = PETSc.KSP().create(comm=matrix.getComm())
    context = configure_trace_harmonic_block_schur_ksp(
        ksp,
        matrix,
        _partition(explicit_owners=True),
        relative_tolerance=1.0e-12,
        absolute_tolerance=1.0e-14,
        maximum_iterations=20,
    )
    try:
        ksp.solve(rhs, solution)
        assert int(ksp.getConvergedReason()) > 0
        assert int(ksp.getIterationNumber()) <= 2
        matrix.mult(solution, action)
        action.axpy(PETSc.ScalarType(-1.0), rhs)
        relative_residual = float(action.norm()) / float(rhs.norm())
        assert relative_residual < 2.0e-12
        diagnostics = context.diagnostics
        assert diagnostics["global_sparse_direct_factor_count"] == 0
        assert diagnostics["mumps_symbolic_or_numeric_created"] is False
    finally:
        ksp.destroy()
        action.destroy()
        solution.destroy()
        rhs.destroy()
        matrix.destroy()


def test_typed_contract_is_opt_in_and_does_not_promote_a_pde_result() -> None:
    contract = trace_harmonic_block_schur_contract()
    assert contract["configured_programmatically"] is True
    assert contract["raw_petsc_options_accepted"] is False
    assert contract["ordinary_default_changed"] is False
    assert contract["opt_in_only"] is True
    assert contract["formal_pde_status"] == "not_run"
    assert contract["candidate_promotion"] is False
    assert contract["heavy_pde_rerun"] is False
    assert contract["global_sparse_direct_factor_nnz"] == 0
    assert contract["strictly_factorless"] is False
    assert "physical_z_slab_ilu" in contract[
        "fundamentally_distinct_from_closed_lanes"
    ]
