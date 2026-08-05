from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from basix.ufl import element
from dolfinx import default_real_type, fem
from mpi4py import MPI

from src.constraints.floquet_3d import build_double_floquet_mpc
from src.solvers import static_condensed_iterative as core
from src.solvers.condensed_dtn import create_matrix_free_condensed_operator
from src.solvers.dtn_port_3d import Stage4NeverMaterializedLinearSolverRequest
from src.solvers.static_local_schur_action import create_static_local_schur_action
from src.solvers.static_p2_auxiliary_pc import build_p2_auxiliary_setup
from src.test.test_222_task037_assembled_fgmres_core import _build_request
from src.test.test_234_task037_p2_trace_transfer import (
    _constraint_map,
    _fixed_target_fixture,
)
from src.test.test_235_task037_p2_galerkin_auxiliary import (
    _distributed_dtn_blocks,
    _retained_p6_fixture,
    _vector,
)
from src.test.test_236_task037_p2_auxiliary_pc import _assembly_time_fixture


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="serial builder gate")
def test_real_p2_factor_free_builder_routes_full_and_schur_actions():
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
    fine_condensed = _assembly_time_fixture(C6, fine_condensed, MPI.COMM_SELF)
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
        fine_schur_action=fine_action,
    )
    source = _vector(fine_shell.createVecRight(), 239)
    target = fine_shell.createVecLeft()
    pc.apply(None, source, target)
    audit = pc.diagnostics
    patch = audit["factor_free_slab_patch"]

    assert np.isfinite(target.norm())
    assert setup_audit["profile"] == (
        "never_materialized_p2_factor_free_slab_auxiliary"
    )
    assert setup_audit["fine_operator_kind"] == "borrowed_p6_condensed_dtn_action"
    assert setup_audit["fine_schur_action_kind"] == (
        "borrowed_p6_static_local_schur_action"
    )
    assert pc.fine_operator is fine_shell
    assert pc._fine_patch.fine_operator is fine_action
    assert pc.fine_operator is not pc._fine_patch.fine_operator
    assert patch["num_slabs"] == 16
    assert setup_audit["factor_free_slab_patch"]["overlap_fraction"] == 0.125
    assert patch["partition_weight_sum_error"] <= 1.0e-12
    assert patch["local_krylov_steps"] == 2
    assert patch["local_inner_preconditioner"] == "none"
    assert patch["outer_requires_fgmres"] is True
    assert patch["p6_slab_matrix_materialized"] is False
    assert patch["p6_slab_matrix_count"] == 0
    assert patch["p6_factor_count"] == 0
    assert patch["p6_factor_nnz"] == 0
    assert patch["global_A_materialized_by_pc"] is False
    assert audit["profile"] == "never_materialized_p2_factor_free_slab_auxiliary"
    assert audit["p2_factor_count"] == 1
    assert audit["global_p6_matrix_materialized"] is False
    assert audit["global_p6_factor_count"] == 0
    assert audit["p6_slab_matrix_count"] == 0
    assert audit["p2_unshifted_matrix_retained"] is False
    assert patch["apply_count"] == 2

    target.destroy()
    source.destroy()
    pc.destroy()
    assert pc._fine_patch._destroyed
    fine_diagonal.destroy()
    transfer.destroy()
    fine_shell_context.destroy(fine_shell)
    fine_shell.destroy()
    fine_action_context.destroy(fine_action)
    fine_action.destroy()
    fine_blocks.destroy()


def test_factor_free_wrapper_routes_action_only_request(monkeypatch):
    A, b, ordinary_request = _build_request(monkeypatch)
    blocks = core.extract_petsc_condensed_blocks(A, b, n_fe=4, n_aux=1)
    fine_action = blocks.require_f().copy()
    blocks.release_f()
    action_request = Stage4NeverMaterializedLinearSolverRequest(
        operator=A,
        b=b,
        n_fe=4,
        n_aux=1,
        static_condensed_system=ordinary_request.static_condensed_system,
        fine_operator=fine_action,
        blocks=blocks,
        function_space=ordinary_request.function_space,
        config=ordinary_request.config,
        floquet_data=ordinary_request.floquet_data,
        mesh_data=SimpleNamespace(),
    )
    captured = {}

    class _Owned:
        def destroy(self):
            captured["destroyed"] = captured.get("destroyed", 0) + 1

    class _FakeP2Pc(_Owned):
        diagnostics = {
            "profile": "never_materialized_p2_factor_free_slab_auxiliary",
            "fine_operator_kind": "borrowed_p6_condensed_dtn_action",
            "global_p6_matrix_materialized": False,
            "global_p6_factor_count": 0,
            "p6_slab_matrix_count": 0,
            "p6_factor_only_storage": False,
            "p2_rows": 4,
            "p2_factor_nnz_used": 10,
            "p2_factor_payload_lower_bound_bytes": 100,
            "factor_free_slab_patch": {
                "num_slabs": 16,
                "overlap_fraction": 0.125,
                "interpolation": "partition",
                "partition_weight_sum_error": 0.0,
                "partition_weight_min": 0.5,
                "partition_weight_max": 1.0,
                "local_krylov_steps": 2,
                "local_inner_preconditioner": "none",
                "outer_requires_fgmres": True,
                "p6_slab_matrix_materialized": False,
                "p6_slab_matrix_count": 0,
                "p6_factor_count": 0,
                "p6_factor_nnz": 0,
                "global_A_materialized_by_pc": False,
            },
            "p2_factor_count": 1,
            "p2_unshifted_matrix_retained": False,
            "modal": {"response_bytes": 0},
            "work_vectors_owned": 7,
            "work_vector_bytes_local": 0,
            "work_vector_bytes_global": 0,
            "transfer_owner_local_stencil_nbytes_local": 1,
            "transfer_owner_local_stencil_nbytes_global": 1,
            "transfer_source_staging_nbytes_local": 1,
            "transfer_source_staging_nbytes_global": 1,
            "transfer_communication_index_nbytes_local": 1,
            "transfer_communication_index_nbytes_global": 1,
            "apply_count": 0,
        }

        def solve(self, source, target):
            target.set(0.0)

    def fake_builder(**kwargs):
        captured.update(kwargs)
        captured["fine_operator_is_distinct"] = (
            kwargs["fine_operator"] is not kwargs["fine_schur_action"]
        )
        captured["fine_operator_type"] = kwargs["fine_operator"].getType()
        captured["fine_schur_action_is_request"] = (
            kwargs["fine_schur_action"] is fine_action
        )
        return (
            _FakeP2Pc(),
            _Owned(),
            fine_action.createVecRight(),
            {
                "profile": "never_materialized_p2_factor_free_slab_auxiliary",
                "factor_free_slab_patch": _FakeP2Pc.diagnostics[
                    "factor_free_slab_patch"
                ],
            },
        )

    monkeypatch.setattr(core, "build_p2_auxiliary_setup", fake_builder)
    snapshot, audit = (
        core.solve_never_materialized_p2_factor_free_slab_auxiliary_fgmres(
            action_request,
            screen_iterations=20,
        )
    )
    try:
        assert captured["fine_schur_action_is_request"]
        assert captured["fine_operator_is_distinct"]
        assert captured["fine_operator_type"] == "python"
        assert snapshot.solver_profile == (
            "never_materialized_p2_factor_free_slab_auxiliary"
        )
        assert audit["candidate"]["restart"] == 90
        assert audit["candidate"]["pc_side"] == "right"
        assert audit["candidate"]["outer_requires_fgmres"] is True
        assert audit["candidate"]["local_krylov_steps"] == 2
        assert audit["no_global_factor_inventory"]["p6_factor_count"] == 0
        assert audit["no_global_factor_inventory"]["p6_factor_nnz"] == 0
        assert audit["partition_audit"]["num_slabs"] == 16
        assert audit["partition_audit"]["overlap_fraction"] == 0.125
        assert audit["partition_audit"]["global_A_materialized_by_pc"] is False
        assert captured["destroyed"] >= 2
    finally:
        snapshot.x.destroy()
        blocks.destroy()
        fine_action.destroy()
        b.destroy()
        A.destroy()
