from __future__ import annotations

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.physical_slab_two_level import (
    assemble_owner_local_slab_matrix,
    build_owner_local_slab_diagonal,
    build_owner_local_slab_plan,
    extract_owner_local_slab_diagonal,
)
from src.solvers.static_factor_free_slab_pc import FactorFreeLocalSlabKrylovPc
from src.solvers.static_local_schur_action import create_static_local_schur_action
from src.solvers.static_p2_slab_pc import build_owner_local_p2_slab_factors
from src.solvers.static_trace_auxiliary import build_p2_to_p6_active_trace_transfer
from src.test.test_234_task037_p2_trace_transfer import _spaces
from src.test.test_235_task037_p2_galerkin_auxiliary import _retained_p6_fixture
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


def _transfer_dense(factor):
    result = np.zeros(
        (factor.p6_row_global_ids.size, factor.p2_column_global_ids.size),
        dtype=PETSc.ScalarType,
    )
    for row in range(factor.p6_row_global_ids.size):
        start = int(factor.p6_row_offsets[row])
        end = int(factor.p6_row_offsets[row + 1])
        result[row, factor.p2_column_ids[start:end]] = factor.p2_values[start:end]
    return result


def _relative(left, right):
    return float(np.linalg.norm(left - right)) / max(
        float(np.linalg.norm(right)), 1.0e-30
    )


def _local_residual_ratio(patch, slab, rhs, matrix, comm):
    correction, _happy_breakdown = patch._fixed_step_gmres(slab, rhs)
    if comm.rank == patch.plan.slab_owners[slab]:
        residual = rhs - matrix @ correction
        local_ratio = float(np.linalg.norm(residual)) / max(
            float(np.linalg.norm(rhs)), 1.0e-30
        )
    else:
        local_ratio = float("inf")
    return float(comm.allreduce(local_ratio, op=MPI.MIN)), correction


@pytest.mark.skipif(MPI.COMM_WORLD.size not in (1, 2, 4), reason="D0 MPI gate")
def test_candidate_d_same_shift_and_flexible_local_p2_oracle():
    comm = MPI.COMM_WORLD
    mesh_3d, (V2, V6), (C2, C6) = _spaces(comm, nx=1, ny=1, nz=1)
    fine_condensed, _schurs = _retained_p6_fixture(V6, C6)
    fine_condensed = _assembly_time_fixture(C6, fine_condensed, comm)
    fine_action, fine_action_context = create_static_local_schur_action(fine_condensed)
    diagonal, diagonal_audit = build_owner_local_slab_diagonal(fine_condensed)
    shifted = _shifted_diagonal(
        diagonal,
        diagonal_audit["global_diagonal_max_abs"],
    )
    transfer = build_p2_to_p6_active_trace_transfer(V2, V6, C2, C6)
    plan = build_owner_local_slab_plan(
        fine_condensed,
        mesh_3d,
        domain_z=(0.0, 1.0),
        num_slabs=2,
        overlap_fraction=0.125,
    )

    oracle_factors, oracle_audit = build_owner_local_p2_slab_factors(
        fine_condensed,
        transfer,
        plan,
        retain_operator=True,
        shifted_diagonal=shifted,
    )
    slab_data = [None for _ in plan.slab_owners]
    same_shift_error = 0.0
    no_shift_error = 0.0
    for slab in range(len(plan.slab_owners)):
        p6_matrix, _matrix_audit = assemble_owner_local_slab_matrix(
            fine_condensed,
            plan,
            slab,
        )
        shift_values, _shift_audit = extract_owner_local_slab_diagonal(
            shifted,
            plan,
            slab,
        )
        factor = oracle_factors[slab]
        if comm.rank == plan.slab_owners[slab]:
            assert p6_matrix is not None
            assert shift_values is not None
            transfer_dense = _transfer_dense(factor)
            rows = np.arange(factor.p6_row_global_ids.size, dtype=PETSc.IntType)
            p6_dense = np.asarray(
                p6_matrix.getValues(rows, rows), dtype=PETSc.ScalarType
            )
            shifted_dense = p6_dense + np.diag(shift_values)
            projected_shifted = transfer_dense.conj().T @ shifted_dense @ transfer_dense
            projected_unshifted = transfer_dense.conj().T @ p6_dense @ transfer_dense
            rhs = np.sin(
                0.17 * np.arange(factor.p2_column_global_ids.size)
            ) + 1j * np.cos(0.23 * np.arange(factor.p2_column_global_ids.size))
            actual = factor.action(rhs)
            same_shift_error = max(
                same_shift_error,
                _relative(actual, projected_shifted @ rhs),
            )
            no_shift_error = max(
                no_shift_error,
                _relative(actual, projected_unshifted @ rhs),
            )
            slab_data[slab] = (transfer_dense, shifted_dense)
            p6_matrix.destroy()
        else:
            assert p6_matrix is None
            assert shift_values is None
    same_shift_error = float(comm.allreduce(same_shift_error, op=MPI.MAX))
    no_shift_error = float(comm.allreduce(no_shift_error, op=MPI.MAX))
    assert same_shift_error <= 1.0e-11
    assert no_shift_error > 1.0e-10
    assert oracle_audit["operator_kind"] == "projected_same_shift_PjH_R6_(A6+S6)_R6T_Pj"
    assert oracle_audit["shift_included"] is True

    for factor in oracle_factors:
        factor.destroy()
    d_factors, d_audit = build_owner_local_p2_slab_factors(
        fine_condensed,
        transfer,
        plan,
        retain_operator=False,
        shifted_diagonal=shifted,
    )
    assert d_audit["p2_slab_matrix_assembled_count"] == 2
    assert d_audit["p2_slab_matrix_retained_count"] == 0
    assert d_audit["p2_factor_count"] == 2
    assert len(d_audit["slab_ledger"]) == 2
    assert all(record["matrix_retained"] is False for record in d_audit["slab_ledger"])
    assert d_audit["operator_kind"] == "projected_same_shift_PjH_R6_(A6+S6)_R6T_Pj"

    factor_only_repeat_error = 0.0
    for factor in d_factors:
        if comm.rank == factor.owner:
            rhs = np.sin(
                0.19 * np.arange(factor.p2_column_global_ids.size)
            ) + 1j * np.cos(0.23 * np.arange(factor.p2_column_global_ids.size))
            first = factor.solve(rhs)
            second = factor.solve(rhs)
            assert np.all(np.isfinite(first))
            assert np.all(np.isfinite(second))
            factor_only_repeat_error = max(
                factor_only_repeat_error,
                float(np.max(np.abs(first - second), initial=0.0)),
            )
    factor_only_repeat_error = float(
        comm.allreduce(factor_only_repeat_error, op=MPI.MAX)
    )
    assert factor_only_repeat_error <= 1.0e-12

    b4 = FactorFreeLocalSlabKrylovPc(
        fine_action,
        plan,
        shifted,
        local_krylov_steps=4,
    )
    candidate_d = FactorFreeLocalSlabKrylovPc(
        fine_action,
        plan,
        shifted,
        local_krylov_steps=4,
        p2_factors=d_factors,
        fine_diagonal=diagonal,
    )
    slab = 0
    data = slab_data[slab]
    if comm.rank == plan.slab_owners[slab]:
        transfer_dense, shifted_dense = data
        q_range, _r = np.linalg.qr(transfer_dense, mode="reduced")
        p2_seed = np.sin(0.13 * np.arange(transfer_dense.shape[1])) + 1j * np.cos(
            0.17 * np.arange(transfer_dense.shape[1])
        )
        low = transfer_dense @ p2_seed
        low /= np.linalg.norm(low)
        p6_seed = np.cos(0.07 * np.arange(transfer_dense.shape[0])) + 1j * np.sin(
            0.11 * np.arange(transfer_dense.shape[0])
        )
        high = p6_seed - q_range @ (q_range.conj().T @ p6_seed)
        assert np.linalg.norm(high) > 1.0e-12
        high /= np.linalg.norm(high)
        assert np.linalg.norm(transfer_dense.conj().T @ high) <= 1.0e-11
        mixed = low + high
        mixed /= np.linalg.norm(mixed)
        sources = {"low": low, "high": high, "mixed": mixed}
    else:
        sources = {
            name: np.empty(0, dtype=PETSc.ScalarType)
            for name in ("low", "high", "mixed")
        }
        shifted_dense = np.empty((0, 0), dtype=PETSc.ScalarType)
    metrics = {}
    for name, source in sources.items():
        rho_b4, _b4_correction = _local_residual_ratio(
            b4,
            slab,
            source,
            shifted_dense,
            comm,
        )
        rho_d, first_d = _local_residual_ratio(
            candidate_d,
            slab,
            source,
            shifted_dense,
            comm,
        )
        rho_d_repeat, second_d = _local_residual_ratio(
            candidate_d,
            slab,
            source,
            shifted_dense,
            comm,
        )
        if comm.rank == plan.slab_owners[slab]:
            assert np.all(np.isfinite(first_d))
            assert np.all(np.isfinite(second_d))
            assert np.max(np.abs(first_d - second_d), initial=0.0) <= 1.0e-12
        assert np.isfinite(rho_b4) and np.isfinite(rho_d)
        assert np.isfinite(rho_d_repeat)
        assert abs(rho_d_repeat - rho_d) <= 1.0e-12
        metrics[name] = (rho_b4, rho_d, rho_b4 / rho_d)

    diagnostics = candidate_d.diagnostics
    assert diagnostics["profile"] == "candidate_d_factor_free_local_p2_fgmres"
    assert diagnostics["local_krylov_type"] == "fgmres"
    assert diagnostics["right_preconditioned"] is True
    assert diagnostics["local_krylov_steps"] == 4
    assert diagnostics["p6_slab_matrix_count"] == 0
    assert diagnostics["p6_factor_count"] == 0
    assert diagnostics["p6_factor_nnz"] == 0
    assert diagnostics["p2_slab_factor_count"] == 2
    assert diagnostics["p2_slab_factor_nnz"] > 0
    assert diagnostics["restricted_action_calls"] > 0
    assert diagnostics["p2_factor_solve_calls"] > 0
    print(
        "CANDIDATE_D0_AUDIT",
        {
            "same_shift_error": same_shift_error,
            "no_shift_error": no_shift_error,
            "factor_only_repeat_error": factor_only_repeat_error,
            "metrics": metrics,
            "p2_factor_count": diagnostics["p2_slab_factor_count"],
            "p2_factor_nnz": diagnostics["p2_slab_factor_nnz"],
            "p6_factor_count": diagnostics["p6_factor_count"],
            "p6_factor_nnz": diagnostics["p6_factor_nnz"],
        },
    )
    if metrics["high"][2] < 1.5 or metrics["mixed"][2] < 1.5:
        pytest.xfail(
            "V3 D0 controlled negative: high improvement="
            f"{metrics['high'][2]:.16g}, mixed improvement="
            f"{metrics['mixed'][2]:.16g}"
        )

    candidate_d.destroy()
    b4.destroy()
    shifted.destroy()
    diagonal.destroy()
    transfer.destroy()
    fine_action_context.destroy(fine_action)
    fine_action.destroy()
    fine_condensed.destroy()
