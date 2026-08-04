from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

from basix.ufl import element
import numpy as np
import pytest
from dolfinx import default_real_type, fem
from mpi4py import MPI
from petsc4py import PETSc

from src.constraints.floquet_3d import build_double_floquet_mpc
from src.solvers.condensed_dtn import (
    create_matrix_free_condensed_operator,
    project_condensed_blocks_to_coarse,
)
from src.solvers.hcurl_assembly_time_condensation import AssemblyTimeCondensedSystem
from src.solvers.physical_slab_two_level import build_owner_local_slab_diagonal
from src.solvers.static_p2_auxiliary_pc import (
    P2AuxiliaryDiagonalModalPc,
    build_p2_auxiliary_setup,
)
from src.solvers.static_local_schur_action import create_static_local_schur_action
from src.test.test_235_task037_p2_galerkin_auxiliary import (
    _distributed_dtn_blocks,
    _max_relative,
    _retained_p6_fixture,
    _spaces,
    _vector,
)
from src.test.test_234_task037_p2_trace_transfer import (
    _constraint_map,
    _fixed_target_fixture,
)
from src.solvers.static_trace_auxiliary import (
    build_p2_galerkin_fine_matrix,
    build_p2_to_p6_active_trace_transfer,
)


def _assembly_time_fixture(C6, fine_condensed, comm):
    return AssemblyTimeCondensedSystem(
        matrix=None,
        owned_trace_original_dofs=np.asarray(
            C6.owned_active_original_dofs, dtype=np.int64
        ),
        original_to_trace=dict(C6.original_to_active),
        trace_constraints=C6,
        cell_recovery_maps=fine_condensed.cell_recovery_maps,
        interior_from_trace_by_class={},
        interior_lu_by_class={},
        interior_rhs_projection_by_class={},
        interior_solution_embedding_by_class={},
        trace_from_interior_rhs_by_class={},
        interior_residual_projection_by_class={},
        full_rows=int(C6.full_trace_rows),
        trace_rows=int(C6.full_trace_rows),
        active_rows=int(C6.active_rows),
        appended_rows=0,
        interior_rows=0,
        active_interior_rows=0,
        build_audit={"test_only": True},
        comm=comm,
        owned_active_rows=len(C6.owned_active_original_dofs),
        owned_appended_rows=0,
        retained_local_schur_by_class=MappingProxyType(
            dict(fine_condensed.retained_local_schur_by_class)
        ),
    )


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="serial builder cleanup gate")
def test_p2_auxiliary_setup_builder_apply_cleanup():
    config, mesh_data, _V2 = _fixed_target_fixture(2, h_nm=50.0)
    V6 = fem.functionspace(
        mesh_data.mesh,
        element(
            "N1curl",
            mesh_data.mesh.basix_cell(),
            6,
            dtype=default_real_type,
        ),
    )
    config6 = replace(
        config,
        nedelec_degree=6,
        nedelec_trace_degree=None,
        nedelec_interior_degree=None,
    )
    floquet6 = build_double_floquet_mpc(V6, mesh_data, config6)
    C6 = _constraint_map(V6, floquet6.mpc)
    fine_condensed, _schurs = _retained_p6_fixture(V6, C6)
    fine_condensed = _assembly_time_fixture(C6, fine_condensed, mesh_data.mesh.comm)
    fine_action, fine_action_context = create_static_local_schur_action(fine_condensed)
    fine_layout = fine_action.createVecRight()
    fine_blocks, _dtn_audit = _distributed_dtn_blocks(fine_layout)
    fine_layout.destroy()
    fine_shell, fine_shell_context = create_matrix_free_condensed_operator(
        fine_blocks,
        fine_operator=fine_action,
    )
    pc, transfer, fine_diagonal, setup_audit = build_p2_auxiliary_setup(
        fine_space=V6,
        fine_condensed=fine_condensed,
        fine_operator=fine_shell,
        fine_blocks=fine_blocks,
        mesh_data=mesh_data,
        config=config6,
    )
    source = _vector(fine_shell.createVecRight(), 236)
    target = fine_shell.createVecLeft()
    pc.apply(None, source, target)
    pc_audit = pc.diagnostics
    assert np.isfinite(target.norm())
    assert setup_audit["global_p6_matrix_materialized"] is False
    assert pc_audit["p2_factor_count"] == 1
    assert pc_audit["p6_slab_matrix_count"] == 0

    target.destroy()
    source.destroy()
    pc.destroy()
    fine_diagonal.destroy()
    transfer.destroy()
    fine_shell_context.destroy(fine_shell)
    fine_shell.destroy()
    fine_action_context.destroy(fine_action)
    fine_action.destroy()
    fine_blocks.destroy()


@pytest.mark.skipif(MPI.COMM_WORLD.size not in (1, 2), reason="requires serial or MPI2")
def test_p2_auxiliary_diagonal_modal_composition():
    mesh_3d, (V2, V6), (C2, C6) = _spaces(MPI.COMM_WORLD)
    transfer = build_p2_to_p6_active_trace_transfer(V2, V6, C2, C6)
    fine_condensed, _schurs = _retained_p6_fixture(V6, C6)
    F2, f2_audit = build_p2_galerkin_fine_matrix(
        fine_condensed,
        V2,
        V6,
        C2,
    )
    fine_condensed = _assembly_time_fixture(C6, fine_condensed, mesh_3d.comm)
    fine_action, fine_action_context = create_static_local_schur_action(fine_condensed)
    fine_layout = fine_action.createVecRight()
    fine_blocks, _dtn_audit = _distributed_dtn_blocks(fine_layout)
    fine_layout.destroy()
    coarse_blocks, block_audit = project_condensed_blocks_to_coarse(
        fine_blocks,
        transfer,
        F2,
    )
    fine_shell, fine_shell_context = create_matrix_free_condensed_operator(
        fine_blocks,
        fine_operator=fine_action,
    )
    fine_diagonal, diagonal_audit = build_owner_local_slab_diagonal(fine_condensed)

    pc = P2AuxiliaryDiagonalModalPc(
        fine_operator=fine_shell,
        transfer=transfer,
        coarse_blocks=coarse_blocks,
        fine_diagonal=fine_diagonal,
    )
    assert f2_audit["global_p6_matrix_materialized"] is False
    assert block_audit["global_p6_transfer_materialized"] is False
    assert coarse_blocks.C.getSize()[0] == C2.active_rows
    assert coarse_blocks.D.getSize()[1] == C2.active_rows
    assert coarse_blocks.H.getSize() == (coarse_blocks.n_aux, coarse_blocks.n_aux)
    aux_ids = np.arange(coarse_blocks.n_aux, dtype=PETSc.IntType)
    if mesh_3d.comm.size == 1:
        assert (
            np.max(
                np.abs(
                    np.asarray(coarse_blocks.H.getValues(aux_ids, aux_ids))
                    - np.eye(coarse_blocks.n_aux)
                )
            )
            > 1.0e-8
        )

    max_repeat_absolute = 0.0
    max_repeat_relative = 0.0
    outputs = []
    for seed in (0, 1, 2, 235):
        source = _vector(fine_shell.createVecRight(), seed)
        first = fine_shell.createVecLeft()
        second = fine_shell.createVecLeft()
        pc.apply(None, source, first)
        pc.apply(None, source, second)
        absolute, relative = _max_relative(first, second)
        max_repeat_absolute = max(max_repeat_absolute, absolute)
        max_repeat_relative = max(max_repeat_relative, relative)
        assert absolute <= 1.0e-11
        assert relative <= 1.0e-11
        assert np.isfinite(first.norm())
        outputs.append((source, first))
        second.destroy()

    audit = pc.diagnostics
    assert audit["profile"] == "never_materialized_p2_auxiliary"
    assert audit["fine_operator_kind"] == "borrowed_p6_condensed_dtn_action"
    assert audit["p2_factor_solver_type"] == "mumps"
    assert audit["p2_factor_count"] == 1
    assert audit["p2_factor_nnz_used"] > 0
    assert audit["p2_factor_payload_lower_bound_bytes"] > 0
    assert audit["p2_factor_petsc_memory_bytes"] >= 0
    assert audit["p2_factor_petsc_memory_available"] == (
        audit["p2_factor_petsc_memory_bytes"] > 0
    )
    assert audit["p2_unshifted_matrix_retained"] is False
    assert audit["work_vector_bytes_global"] > 0
    assert audit["transfer_owner_local_stencil_nbytes_global"] > 0
    assert audit["transfer_source_staging_nbytes_global"] > 0
    assert audit["transfer_communication_index_nbytes_global"] > 0
    assert audit["global_p6_matrix_materialized"] is False
    assert audit["global_p6_transfer_materialized"] is False
    assert audit["global_p6_factor_count"] == 0
    assert audit["p6_slab_matrix_count"] == 0
    assert audit["p6_factor_only_storage"] is False
    assert audit["diagonal_patch"]["pre_post"] is True
    assert audit["diagonal_patch"]["inverse_bytes_global"] > 0
    if mesh_3d.comm.size == 2:
        assert (
            mesh_3d.comm.allreduce(
                transfer.audit["remote_coarse_columns_local"], op=MPI.SUM
            )
            > 0
        )

    sum_source = outputs[0][0].copy()
    sum_source.axpy(1.0, outputs[1][0])
    sum_output = fine_shell.createVecLeft()
    pc.apply(None, sum_source, sum_output)
    expected_sum = outputs[0][1].copy()
    expected_sum.axpy(1.0, outputs[1][1])
    linear_absolute, linear_relative = _max_relative(sum_output, expected_sum)
    assert linear_absolute <= 1.0e-11
    assert linear_relative <= 1.0e-11
    assert np.isfinite(fine_diagonal.norm())
    assert diagonal_audit["global_diagonal_max_abs"] > 0.0
    print(
        "M4C_SERIAL_AUDIT",
        {
            "max_repeat_absolute": max_repeat_absolute,
            "max_repeat_relative": max_repeat_relative,
            "linearity_absolute": linear_absolute,
            "linearity_relative": linear_relative,
            "p2_rows": audit["p2_rows"],
            "p2_nnz": audit["p2_matrix_nnz_used"],
            "p2_factor_solver_type": audit["p2_factor_solver_type"],
            "p2_factor_nnz": audit["p2_factor_nnz_used"],
            "p2_factor_petsc_memory_bytes": audit["p2_factor_petsc_memory_bytes"],
            "p2_factor_payload_lower_bound_bytes": audit[
                "p2_factor_payload_lower_bound_bytes"
            ],
            "work_vector_bytes_global": audit["work_vector_bytes_global"],
            "modal_response_bytes": audit["modal"]["response_storage_bytes"],
            "diagonal_inverse_bytes": audit["diagonal_patch"]["inverse_bytes_global"],
            "transfer_stencil_nbytes_local": audit[
                "transfer_owner_local_stencil_nbytes_local"
            ],
            "transfer_stencil_nbytes_global": audit[
                "transfer_owner_local_stencil_nbytes_global"
            ],
            "transfer_source_staging_nbytes_local": audit[
                "transfer_source_staging_nbytes_local"
            ],
            "transfer_source_staging_nbytes_global": audit[
                "transfer_source_staging_nbytes_global"
            ],
            "transfer_communication_index_nbytes_local": audit[
                "transfer_communication_index_nbytes_local"
            ],
            "transfer_communication_index_nbytes_global": audit[
                "transfer_communication_index_nbytes_global"
            ],
            "no_p6_factor": audit["global_p6_factor_count"] == 0,
        },
    )

    expected_sum.destroy()
    sum_output.destroy()
    sum_source.destroy()
    for source, output in outputs:
        output.destroy()
        source.destroy()
    pc.destroy()
    fine_diagonal.destroy()
    fine_shell_context.destroy(fine_shell)
    fine_shell.destroy()
    fine_action_context.destroy(fine_action)
    fine_action.destroy()
    fine_blocks.destroy()
    transfer.destroy()
