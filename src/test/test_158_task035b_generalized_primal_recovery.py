from __future__ import annotations

import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hcurl_assembly_time_condensation import (
    CallerTraceExpansion,
    build_unconstrained_assembly_time_condensation,
    gather_active_trace_values,
    generalized_reduced_primal_residual,
    recover_owned_cell_interiors,
    recover_owned_trace_values,
    validate_primal_recovery_mpc_backsubstitution,
)


def _problem(comm: MPI.Intracomm, nx: int):
    msh = mesh.create_unit_cube(
        comm,
        nx,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
    )
    tdim = msh.topology.dim
    owned_cells = int(msh.topology.index_map(tdim).size_local)
    tags = mesh.meshtags(
        msh,
        tdim,
        np.arange(owned_cells, dtype=np.int32),
        np.ones(owned_cells, dtype=np.int32),
    )
    function_space = fem.functionspace(
        msh,
        element(
            "N1curl",
            msh.basix_cell(),
            2,
            dtype=default_real_type,
        ),
    )
    trial = ufl.TrialFunction(function_space)
    test = ufl.TestFunction(function_space)
    dx = ufl.Measure("dx", domain=msh, subdomain_data=tags)
    compiled = fem.form(
        (
            ufl.inner(ufl.curl(trial), ufl.curl(test))
            + PETSc.ScalarType(2.1 - 0.13j)
            * ufl.inner(trial, test)
        )
        * dx(1)
    )
    return tags, function_space, compiled


def _qualification() -> dict[str, object]:
    return {
        "schema_version": (
            "task035b.test-generalized-primal-recovery.v1"
        ),
        "pass": True,
        "owner_aware_contiguous_petsc_rows": True,
        "inactive_modes_have_no_petsc_rows": True,
        "full_trace_matrix_constructed": False,
        "ordinary_default_changed": False,
        "actual_floquet_pullback_cycles_closed": True,
    }


def _generalized_system(
    comm: MPI.Intracomm,
    *,
    nx: int,
    active_rows: int,
    owner_counts: tuple[int, ...],
):
    tags, function_space, compiled = _problem(comm, nx)
    ordinary = build_unconstrained_assembly_time_condensation(
        compiled,
        function_space,
        tags,
    )
    trace_index = np.arange(
        ordinary.trace_rows,
        dtype=np.float64,
    )[:, None]
    active_index = np.arange(active_rows, dtype=np.float64)[None, :]
    expansion_matrix = (
        0.5
        + 0.007 * (trace_index + 1.0) * (active_index + 1.0)
    ) * np.exp(
        1j
        * (
            0.023 * (trace_index + 1.0)
            + 0.11 * (active_index + 1.0)
        )
    )
    expansion_matrix /= np.linalg.norm(
        expansion_matrix,
        axis=0,
    )[None, :]
    active_ids = np.arange(active_rows, dtype=PETSc.IntType)
    expansion = {
        int(original): (
            active_ids.copy(),
            np.asarray(
                expansion_matrix[int(trace_row)],
                dtype=np.complex128,
            ).copy(),
        )
        for original, trace_row in ordinary.original_to_trace.items()
    }
    owner_start = int(sum(owner_counts[: comm.rank]))
    owner_stop = owner_start + int(owner_counts[comm.rank])
    generalized = build_unconstrained_assembly_time_condensation(
        compiled,
        function_space,
        tags,
        caller_trace_expansion=CallerTraceExpansion(
            owned_active_rows=np.arange(
                owner_start,
                owner_stop,
                dtype=PETSc.IntType,
            ),
            expansion_by_original=expansion,
            full_trace_rows=ordinary.trace_rows,
            active_rows=active_rows,
            qualification_audit=_qualification(),
        ),
    )
    return ordinary, generalized, expansion_matrix


def _distributed_vector(
    matrix: PETSc.Mat,
    owned_rows: np.ndarray,
    global_values: np.ndarray,
) -> PETSc.Vec:
    vector = matrix.createVecRight()
    vector.set(PETSc.ScalarType(0.0))
    if len(owned_rows):
        vector.setValues(
            owned_rows,
            np.asarray(global_values[owned_rows], dtype=PETSc.ScalarType),
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
    vector.assemble()
    return vector


def _assert_storage_trace_is_cq(
    generalized,
    expansion_matrix: np.ndarray,
    q: np.ndarray,
    q_vector: PETSc.Vec,
) -> None:
    np.testing.assert_allclose(
        gather_active_trace_values(generalized, q_vector),
        q,
        rtol=0.0,
        atol=0.0,
    )
    owned_original, owned_values = recover_owned_trace_values(
        generalized,
        q_vector,
    )
    expected = np.asarray(
        [
            expansion_matrix[
                generalized.original_to_trace[int(original)]
            ]
            @ q
            for original in owned_original
        ],
        dtype=np.complex128,
    )
    np.testing.assert_allclose(
        owned_values,
        expected,
        rtol=3.0e-14,
        atol=3.0e-14,
    )


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial generalized recovery algebra test",
)
def test_generalized_primal_recovery_and_residual_are_independent() -> None:
    ordinary, generalized, expansion_matrix = _generalized_system(
        MPI.COMM_SELF,
        nx=1,
        active_rows=4,
        owner_counts=(4,),
    )
    q = np.asarray(
        [0.3 + 0.2j, -0.6 + 0.1j, 0.4 - 0.8j, 1.1 + 0.05j],
        dtype=np.complex128,
    )
    owned_active = np.asarray(
        generalized.trace_constraints.owned_active_rows,
        dtype=PETSc.IntType,
    )
    q_vector = _distributed_vector(
        generalized.matrix,
        owned_active,
        q,
    )
    rhs = generalized.matrix.createVecLeft()
    generalized.matrix.mult(q_vector, rhs)
    perturbed = None
    manual_residual = None
    try:
        _assert_storage_trace_is_cq(
            generalized,
            expansion_matrix,
            q,
            q_vector,
        )
        from_vector = recover_owned_cell_interiors(
            generalized,
            q_vector,
        )
        from_array = recover_owned_cell_interiors(generalized, q)
        assert len(from_vector) == len(from_array)
        for (rows_a, values_a), (rows_b, values_b) in zip(
            from_vector,
            from_array,
            strict=True,
        ):
            np.testing.assert_array_equal(rows_a, rows_b)
            np.testing.assert_allclose(
                values_a,
                values_b,
                rtol=0.0,
                atol=0.0,
            )

        policy = validate_primal_recovery_mpc_backsubstitution(
            generalized,
            requested=False,
        )
        assert (
            generalized.trace_constraints.build_audit[
                "complete_storage_trace_pullback"
            ]
            is True
        )
        assert (
            generalized.trace_constraints.build_audit[
                "post_recovery_mpc_backsubstitution_forbidden"
            ]
            is True
        )
        assert policy["mpc_backsubstitution_permitted"] is False
        assert (
            policy[
                "caller_expansion_already_contains_complete_pullback"
            ]
            is True
        )
        with pytest.raises(
            RuntimeError,
            match="duplicate MPC backsubstitution is forbidden",
        ):
            validate_primal_recovery_mpc_backsubstitution(
                generalized,
                requested=True,
            )

        exact = generalized_reduced_primal_residual(
            generalized,
            rhs,
            q_vector,
        )
        assert exact["caller_owned_active_rows_used"] is True
        assert exact["fresh_explicit_petsc_matmult"] is True
        assert exact["full_recovered_true_residual"] is False
        assert exact["linear_system_residual_norm"] <= 1.0e-13

        perturbed = q_vector.copy()
        perturbed.setValue(
            2,
            PETSc.ScalarType(0.07 - 0.03j),
            addv=PETSc.InsertMode.ADD_VALUES,
        )
        perturbed.assemble()
        measured = generalized_reduced_primal_residual(
            generalized,
            rhs,
            perturbed,
        )
        manual_residual = rhs.duplicate()
        generalized.matrix.mult(perturbed, manual_residual)
        manual_residual.axpy(PETSc.ScalarType(-1.0), rhs)
        np.testing.assert_allclose(
            measured["linear_system_residual_norm"],
            manual_residual.norm(),
            rtol=2.0e-14,
            atol=2.0e-14,
        )
        np.testing.assert_allclose(
            measured["active_trace_residual_norm"],
            manual_residual.norm(),
            rtol=2.0e-14,
            atol=2.0e-14,
        )
        assert measured["appended_row_residual_norm"] == 0.0
    finally:
        if manual_residual is not None:
            manual_residual.destroy()
        if perturbed is not None:
            perturbed.destroy()
        rhs.destroy()
        q_vector.destroy()
        generalized.destroy()
        ordinary.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial ordinary-path compatibility test",
)
def test_ordinary_array_recovery_and_backsubstitution_policy_are_unchanged() -> None:
    tags, function_space, compiled = _problem(MPI.COMM_SELF, 1)
    ordinary = build_unconstrained_assembly_time_condensation(
        compiled,
        function_space,
        tags,
    )
    q = (
        np.arange(ordinary.active_rows, dtype=np.float64)
        + 1j * np.arange(ordinary.active_rows, dtype=np.float64)[::-1]
    ).astype(np.complex128)
    residual_rhs = ordinary.matrix.createVecLeft()
    residual_solution = ordinary.matrix.createVecRight()
    try:
        owned_original, owned_values = recover_owned_trace_values(
            ordinary,
            q,
        )
        expected = np.asarray(
            [
                q[
                    ordinary.trace_constraints.original_to_active[
                        int(original)
                    ]
                ]
                for original in owned_original
            ],
            dtype=np.complex128,
        )
        np.testing.assert_array_equal(owned_values, expected)
        policy = validate_primal_recovery_mpc_backsubstitution(
            ordinary,
            requested=True,
        )
        assert policy["generalized_caller_trace_expansion"] is False
        assert policy["mpc_backsubstitution_permitted"] is True
        assert policy["ordinary_default_changed"] is False
        with pytest.raises(
            ValueError,
            match="requires a caller trace expansion",
        ):
            generalized_reduced_primal_residual(
                ordinary,
                residual_rhs,
                residual_solution,
            )
    finally:
        residual_solution.destroy()
        residual_rhs.destroy()
        ordinary.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2,
    reason="MPI2 uneven caller-row ownership test",
)
def test_mpi2_uneven_caller_owned_rows_drive_recovery_and_residual() -> None:
    comm = MPI.COMM_WORLD
    owner_counts = (1, 2)
    ordinary, generalized, expansion_matrix = _generalized_system(
        comm,
        nx=2,
        active_rows=3,
        owner_counts=owner_counts,
    )
    owner_start = int(sum(owner_counts[: comm.rank]))
    owner_stop = owner_start + owner_counts[comm.rank]
    expected_owned = np.arange(
        owner_start,
        owner_stop,
        dtype=PETSc.IntType,
    )
    q = np.asarray(
        [0.45 - 0.2j, -0.35 + 0.7j, 0.9 + 0.15j],
        dtype=np.complex128,
    )
    q_vector = _distributed_vector(
        generalized.matrix,
        expected_owned,
        q,
    )
    rhs = generalized.matrix.createVecLeft()
    generalized.matrix.mult(q_vector, rhs)
    try:
        np.testing.assert_array_equal(
            generalized.trace_constraints.owned_active_rows,
            expected_owned,
        )
        assert tuple(map(int, generalized.matrix.getOwnershipRange())) == (
            owner_start,
            owner_stop,
        )
        _assert_storage_trace_is_cq(
            generalized,
            expansion_matrix,
            q,
            q_vector,
        )
        residual = generalized_reduced_primal_residual(
            generalized,
            rhs,
            q_vector,
        )
        assert residual["linear_system_residual_norm"] <= 2.0e-13
        assert residual["active_trace_residual_norm"] <= 2.0e-13
        assert residual["appended_row_residual_norm"] == 0.0
    finally:
        rhs.destroy()
        q_vector.destroy()
        generalized.destroy()
        ordinary.destroy()
