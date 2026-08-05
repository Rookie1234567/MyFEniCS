from __future__ import annotations

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.physical_slab_two_level import (
    _route_owner_slab_cells,
    build_owner_local_slab_plan,
)
from src.solvers.static_p2_slab_pc import build_owner_local_p2_slab_factors
from src.solvers.static_trace_auxiliary import build_p2_to_p6_active_trace_transfer
from src.test.test_234_task037_p2_trace_transfer import _spaces
from src.test.test_235_task037_p2_galerkin_auxiliary import (
    _retained_p6_fixture,
)
from src.test.test_236_task037_p2_auxiliary_pc import _assembly_time_fixture


def _reference_slab_matrix(condensed, plan, factor):
    routed_cells = []

    def consume(_cell_index, active_ids, block):
        routed_cells.append((active_ids.copy(), block.copy()))

    _route_owner_slab_cells(condensed, plan, factor.slab, consume)
    if plan.comm.rank != factor.owner:
        return None
    row_positions = {
        int(row): index for index, row in enumerate(factor.p6_row_global_ids)
    }
    row_entries = [
        tuple(
            zip(
                factor.p2_column_ids[
                    int(factor.p6_row_offsets[index]) : int(
                        factor.p6_row_offsets[index + 1]
                    )
                ],
                factor.p2_values[
                    int(factor.p6_row_offsets[index]) : int(
                        factor.p6_row_offsets[index + 1]
                    )
                ],
                strict=True,
            )
        )
        for index in range(factor.p6_row_global_ids.size)
    ]
    reference = np.zeros(
        (factor.p2_column_global_ids.size, factor.p2_column_global_ids.size),
        dtype=PETSc.ScalarType,
    )
    for active_ids, block in routed_cells:
        selected = [
            index for index, row in enumerate(active_ids) if int(row) in row_positions
        ]
        positions = [row_positions[int(active_ids[index])] for index in selected]
        transfer = np.zeros(
            (len(positions), factor.p2_column_global_ids.size),
            dtype=PETSc.ScalarType,
        )
        for local_row, position in enumerate(positions):
            for column, value in row_entries[position]:
                transfer[local_row, int(column)] = value
        selected_block = block[np.ix_(selected, selected)]
        reference += transfer.conjugate().T @ selected_block @ transfer
    return reference


def _global_values(vector):
    start, end = map(int, vector.getOwnershipRange())
    packets = (
        vector.getComm()
        .tompi4py()
        .allgather((start, end, np.asarray(vector.getArray(readonly=True)).copy()))
    )
    result = np.empty(int(vector.getSize()), dtype=PETSc.ScalarType)
    for packet_start, packet_end, values in packets:
        result[packet_start:packet_end] = values
    return result


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2, 4),
    reason="R2 local slab identity gate uses serial/MPI2/MPI4",
)
def test_p2_local_slab_transfer_projection_and_ilu0():
    comm = MPI.COMM_WORLD
    mesh, (V2, V6), (C2, C6) = _spaces(comm)
    fine_seed, _schurs = _retained_p6_fixture(V6, C6)
    fine_condensed = _assembly_time_fixture(C6, fine_seed, comm)
    fake_matrix = PETSc.Mat().createAIJ(size=(1, 1), comm=PETSc.COMM_SELF)
    fake_matrix.assemble()
    fine_condensed.matrix = fake_matrix
    with pytest.raises(ValueError, match="action-only"):
        build_owner_local_p2_slab_factors(
            fine_condensed,
            None,
            None,
        )
    fine_condensed.matrix = None
    fake_matrix.destroy()
    transfer = build_p2_to_p6_active_trace_transfer(V2, V6, C2, C6)
    plan = build_owner_local_slab_plan(
        fine_condensed,
        mesh,
        domain_z=(0.0, 1.0),
        num_slabs=2,
        overlap_fraction=0.125,
    )
    factors, audit = build_owner_local_p2_slab_factors(
        fine_condensed,
        transfer,
        plan,
    )

    assert audit["num_slabs"] == 2
    assert audit["p2_slab_matrix_assembled_count"] == 2
    assert audit["p2_slab_matrix_retained_count"] == 0
    assert len(audit["slab_ledger"]) == 2
    assert {item["slab"] for item in audit["slab_ledger"]} == {0, 1}
    for item in audit["slab_ledger"]:
        assert item["matrix_assembled"] is True
        assert item["matrix_retained"] is False
        assert item["p6_rows"] > 0
        assert item["p6_transfer_nnz"] > 0
        assert item["p2_rows"] > 0
        assert item["p2_matrix_nnz"] > 0
        assert item["p2_factor_nnz"] > 0
        assert item["factor_payload_lower_bound_bytes"] > 0
        assert item["cell_count"] > 0
        assert item["operator_fingerprint"]
    assert audit["p2_factor_count"] == 2
    assert audit["p2_matrix_nnz"] > 0
    assert audit["p2_factor_nnz"] > 0
    assert audit["factor_payload_lower_bound_bytes"] > 0
    assert audit["p6_slab_matrix_count"] == 0
    assert audit["p6_factor_count"] == 0
    assert audit["p6_factor_nnz"] == 0
    assert audit["global_p6_matrix_materialized"] is False
    assert audit["global_p6_factor_materialized"] is False
    assert audit["solver_type"] == "preonly_ilu0"
    assert audit["shift_mode"] == "none_unshifted_a6_j"
    assert audit["operator_kind"] == "unshifted_PjH_R6_A6_R6T_Pj"
    assert audit["shift_included"] is False
    assert audit["transfer_support_mode"].startswith("actual_entity_orientation")
    default_repeat_error = 0.0
    for factor in factors:
        if factor.owner == comm.rank:
            assert factor.matrix is None
            assert factor.factor_matrix is not None
            assert factor.rhs is not None
            assert factor.solution is not None
            rhs = np.sin(
                0.19 * np.arange(factor.p2_column_global_ids.size)
            ) + 1j * np.cos(0.23 * np.arange(factor.p2_column_global_ids.size))
            first = factor.solve(rhs)
            second = factor.solve(rhs)
            assert np.all(np.isfinite(first))
            assert np.all(np.isfinite(second))
            default_repeat_error = max(
                default_repeat_error,
                float(np.max(np.abs(first - second), initial=0.0)),
            )
        else:
            assert factor.matrix is None
            assert factor.factor_matrix is None
            assert factor.rhs is None
            assert factor.solution is None
    default_repeat_error = float(comm.allreduce(default_repeat_error, op=MPI.MAX))
    assert default_repeat_error <= 1.0e-12
    for factor in factors:
        factor.destroy()
    factors, oracle_audit = build_owner_local_p2_slab_factors(
        fine_condensed,
        transfer,
        plan,
        retain_operator=True,
    )
    assert oracle_audit["p2_slab_matrix_retained_count"] == 2

    q2 = PETSc.Vec().createMPI(
        (len(C2.owned_active_original_dofs), C2.active_rows),
        comm=comm,
    )
    y6 = PETSc.Vec().createMPI(
        (len(C6.owned_active_original_dofs), C6.active_rows),
        comm=comm,
    )
    start, end = map(int, q2.getOwnershipRange())
    q2.getArray()[:] = np.sin(0.17 * np.arange(start, end)) + 1j * np.cos(
        0.11 * np.arange(start, end)
    )
    q2.assemble()
    start, end = map(int, y6.getOwnershipRange())
    y6.getArray()[:] = np.cos(0.07 * np.arange(start, end)) + 1j * np.sin(
        0.13 * np.arange(start, end)
    )
    y6.assemble()
    projected_q2 = q2.duplicate()
    projected_q6 = y6.duplicate()
    transfer.apply(q2, projected_q6)
    transfer.apply_adjoint(y6, projected_q2)
    adjoint_error = abs(y6.dot(projected_q6) - projected_q2.dot(q2))
    assert float(comm.allreduce(adjoint_error, op=MPI.MAX)) <= 1.0e-11

    global_q2 = _global_values(q2)
    global_q6 = _global_values(projected_q6)
    local_operator_error = 0.0
    local_action_relative = 0.0
    local_adjoint_relative = 0.0
    local_transfer_error = 0.0
    for factor in factors:
        reference = _reference_slab_matrix(fine_condensed, plan, factor)
        if factor.matrix is None:
            assert reference is None
            continue
        assert reference is not None
        actual = np.asarray(
            factor.matrix.getValues(
                np.arange(reference.shape[0], dtype=PETSc.IntType),
                np.arange(reference.shape[1], dtype=PETSc.IntType),
            ),
            dtype=PETSc.ScalarType,
        )
        local_operator_error = max(
            local_operator_error,
            float(np.max(np.abs(actual - reference), initial=0.0)),
        )
        rhs = np.sin(0.19 * np.arange(reference.shape[0]) + factor.slab) + 1j * np.cos(
            0.23 * np.arange(reference.shape[0]) - factor.slab
        )
        action = factor.action(rhs)
        assert np.all(np.isfinite(action))
        expected_action = reference @ rhs
        local_action_relative = max(
            local_action_relative,
            float(
                np.linalg.norm(action - expected_action)
                / max(np.linalg.norm(expected_action), np.finfo(float).tiny)
            ),
        )
        local_y = np.cos(
            0.31 * np.arange(factor.p6_row_global_ids.size) + factor.slab
        ) + 1j * np.sin(0.27 * np.arange(factor.p6_row_global_ids.size) - factor.slab)
        local_p6 = factor.prolong(rhs)
        local_p2 = factor.restrict_adjoint(local_y)
        lhs = np.vdot(local_p6, local_y)
        rhs_inner = np.vdot(rhs, local_p2)
        local_adjoint_relative = max(
            local_adjoint_relative,
            float(abs(lhs - rhs_inner) / max(abs(lhs), abs(rhs_inner), 1.0e-30)),
        )
        expected_transfer = global_q6[factor.p6_row_global_ids]
        local_transfer_error = max(
            local_transfer_error,
            float(
                np.max(
                    np.abs(
                        factor.prolong(global_q2[factor.p2_column_global_ids])
                        - expected_transfer
                    ),
                    initial=0.0,
                )
            ),
        )
    assert float(comm.allreduce(local_operator_error, op=MPI.MAX)) <= 1.0e-11
    max_action_relative = float(comm.allreduce(local_action_relative, op=MPI.MAX))
    max_adjoint_relative = float(comm.allreduce(local_adjoint_relative, op=MPI.MAX))
    max_transfer_error = float(comm.allreduce(local_transfer_error, op=MPI.MAX))
    assert max_action_relative <= 1.0e-11
    assert max_adjoint_relative <= 1.0e-11
    assert max_transfer_error <= 1.0e-11

    if comm.rank == 0:
        print(
            "R2_LOCAL_P2_SLAB_AUDIT",
            {
                "default_slab_ledger": audit["slab_ledger"],
                "default_factor_only_max_repeat_error": default_repeat_error,
                "max_action_relative": max_action_relative,
                "max_local_adjoint_relative": max_adjoint_relative,
                "max_local_vs_global_transfer_error": max_transfer_error,
            },
        )

    projected_q2.destroy()
    projected_q6.destroy()
    y6.destroy()
    q2.destroy()
    for factor in factors:
        factor.destroy()
    transfer.destroy()
    fine_condensed.destroy()
