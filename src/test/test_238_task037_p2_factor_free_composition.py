from __future__ import annotations

import numpy as np
import pytest
from mpi4py import MPI

from src.solvers.condensed_dtn import (
    create_matrix_free_condensed_operator,
    project_condensed_blocks_to_coarse,
)
from src.solvers.physical_slab_two_level import (
    build_owner_local_slab_diagonal,
    build_owner_local_slab_plan,
)
from src.solvers.static_factor_free_slab_pc import FactorFreeLocalSlabKrylovPc
from src.solvers.static_local_schur_action import create_static_local_schur_action
from src.solvers.static_p2_auxiliary_pc import P2AuxiliaryDiagonalModalPc
from src.solvers.static_trace_auxiliary import (
    build_p2_galerkin_fine_matrix,
    build_p2_to_p6_active_trace_transfer,
)
from src.test.test_234_task037_p2_trace_transfer import _spaces
from src.test.test_235_task037_p2_galerkin_auxiliary import (
    _distributed_dtn_blocks,
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


@pytest.mark.skipif(MPI.COMM_WORLD.size not in (1, 2), reason="requires serial or MPI2")
def test_p2_factor_free_patch_composition():
    comm = MPI.COMM_WORLD
    mesh_3d, (V2, V6), (C2, C6) = _spaces(comm)
    fine_condensed, _schurs = _retained_p6_fixture(V6, C6)
    fine_condensed = _assembly_time_fixture(C6, fine_condensed, comm)
    fine_action, fine_action_context = create_static_local_schur_action(fine_condensed)
    fine_layout = fine_action.createVecRight()
    fine_blocks, _dtn_audit = _distributed_dtn_blocks(fine_layout)
    fine_layout.destroy()
    F2, _f2_audit = build_p2_galerkin_fine_matrix(
        fine_condensed,
        V2,
        V6,
        C2,
    )
    transfer = build_p2_to_p6_active_trace_transfer(V2, V6, C2, C6)
    coarse_blocks, _block_audit = project_condensed_blocks_to_coarse(
        fine_blocks,
        transfer,
        F2,
    )
    fine_shell, fine_shell_context = create_matrix_free_condensed_operator(
        fine_blocks,
        fine_operator=fine_action,
    )
    fine_diagonal, diagonal_audit = build_owner_local_slab_diagonal(fine_condensed)
    shifted = _shifted_diagonal(
        fine_diagonal,
        diagonal_audit["global_diagonal_max_abs"],
    )
    plan = build_owner_local_slab_plan(
        fine_condensed,
        mesh_3d,
        domain_z=(0.0, 1.0),
        num_slabs=2,
        overlap_fraction=0.125,
    )
    patch = FactorFreeLocalSlabKrylovPc(fine_action, plan, shifted)
    pc = P2AuxiliaryDiagonalModalPc(
        fine_operator=fine_shell,
        transfer=transfer,
        coarse_blocks=coarse_blocks,
        fine_diagonal=fine_diagonal,
        fine_patch=patch,
    )

    source = _vector(fine_shell.createVecRight(), 238)
    first = fine_shell.createVecLeft()
    second = fine_shell.createVecLeft()
    pc.apply(None, source, first)
    first_audit = pc.diagnostics
    patch_audit = first_audit["factor_free_slab_patch"]
    assert first_audit["profile"] == "never_materialized_p2_factor_free_slab_auxiliary"
    assert first_audit["high_order_patch_kind"] == "factor_free_local_slab_krylov"
    assert first_audit["outer_requires_fgmres"] is True
    assert first_audit["p2_factor_count"] == 1
    assert first_audit["p6_factor_only_storage"] is False
    assert first_audit["p6_slab_matrix_count"] == 0
    assert patch_audit["p6_slab_matrix_count"] == 0
    assert patch_audit["p6_factor_count"] == 0
    assert patch_audit["partition_weight_sum_error"] <= 1.0e-12
    assert patch_audit["local_krylov_steps"] == 2
    assert patch_audit["outer_requires_fgmres"] is True
    assert patch_audit["apply_count"] == 2
    assert np.isfinite(first.norm())

    pc.apply(None, source, second)
    repeat_absolute, repeat_relative = _max_relative(first, second)
    assert repeat_absolute <= 1.0e-11
    assert repeat_relative <= 1.0e-11
    second_audit = pc.diagnostics
    assert second_audit["factor_free_slab_patch"]["apply_count"] == 4

    work = fine_shell.createVecLeft()
    fine_shell.mult(first, work)
    work.axpy(-1.0, source)
    residual_ratio = work.norm() / max(source.norm(), 1.0e-30)
    assert np.isfinite(residual_ratio)
    assert residual_ratio < 1.0

    print(
        "P2_FACTOR_FREE_COMPOSITION_AUDIT",
        {
            "residual_ratio": residual_ratio,
            "repeat_absolute": repeat_absolute,
            "repeat_relative": repeat_relative,
            "p2_factor_count": second_audit["p2_factor_count"],
            "p6_factor_count": second_audit["factor_free_slab_patch"][
                "p6_factor_count"
            ],
            "p6_slab_matrix_count": second_audit["factor_free_slab_patch"][
                "p6_slab_matrix_count"
            ],
            "partition_weight_sum_error": second_audit["factor_free_slab_patch"][
                "partition_weight_sum_error"
            ],
        },
    )

    work.destroy()
    second.destroy()
    first.destroy()
    source.destroy()
    pc.destroy()
    assert patch._destroyed
    shifted.destroy()
    fine_diagonal.destroy()
    fine_shell_context.destroy(fine_shell)
    fine_shell.destroy()
    fine_blocks.destroy()
    fine_action_context.destroy(fine_action)
    fine_action.destroy()
    transfer.destroy()
