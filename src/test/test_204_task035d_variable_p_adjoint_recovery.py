from __future__ import annotations

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest
from scipy import sparse
from scipy.linalg import lu_factor
from dolfinx import mesh

from src.adaptivity.exact_sequence_variable_p import (
    build_variable_p_reference_space,
)
from src.adaptivity.variable_p_entity_map import (
    build_variable_p_global_entity_map,
)
from src.adaptivity.variable_p_periodic_orbits import (
    build_variable_p_periodic_constraint_map,
)
from src.solvers.hcurl_variable_p_assembly import (
    _iteratively_refined_lu_solve,
    _lu_factor_matrix_action,
    audit_variable_p_active_full_adjoint_recovery,
    build_variable_p_condensed_trace_system,
    condense_variable_p_active_vector_to_trace,
    recover_variable_p_active_full_adjoint_vector,
    recover_variable_p_active_full_vector,
)
from src.solvers.hcurl_variable_p_local import project_p6_local_tensor
from src.solvers.hcurl_variable_p_reduction import (
    VariablePAssemblyTimeReduction,
)
from src.test.test_201_task035d_broken_cell_trace import (
    _global_trace_expansion,
    _global_vector_values,
    _periodic_corner_fixture,
)


def _degree_array(msh, dimension: int, degree: int) -> np.ndarray:
    msh.topology.create_entities(dimension)
    index_map = msh.topology.index_map(dimension)
    return np.full(
        int(index_map.size_local + index_map.num_ghosts),
        int(degree),
        dtype=np.int32,
    )


def _nonhermitian_p6_tensor() -> np.ndarray:
    rows = np.arange(882, dtype=np.float64)
    left = np.sin(0.013 * rows) + 1j * np.cos(0.017 * rows)
    right = np.cos(0.019 * rows) - 0.7j * np.sin(0.023 * rows)
    tensor = np.diag(4.0 + 0.002 * rows).astype(np.complex128)
    tensor += 0.0015 * np.outer(left, right)
    tensor += 0.0007j * np.outer(right.conj(), left)
    return np.ascontiguousarray(tensor)


def _dense_trace_expansion(constraints) -> np.ndarray:
    expansion = np.zeros(
        (
            constraints.entity_map.active_trace_rows,
            constraints.independent_trace_rows,
        ),
        dtype=np.complex128,
    )
    covered = np.zeros(
        constraints.entity_map.active_trace_rows,
        dtype=np.int8,
    )
    for block in constraints.entity_blocks.values():
        expansion[
            np.ix_(block.full_rows, block.independent_rows)
        ] = block.full_from_independent
        covered[block.full_rows] += 1
    np.testing.assert_array_equal(covered, np.ones_like(covered))
    return expansion


def test_complex_hermitian_lu_action_and_refinement_force_row_pivots() -> None:
    permutation = np.eye(6)[[3, 5, 1, 4, 0, 2]]
    base = np.asarray(
        [
            [7.0 + 0.2j, 0.3 - 0.1j, 0.0, 0.2j, 0.0, 0.1],
            [0.4j, 8.0 - 0.1j, 0.2, 0.0, 0.3j, 0.0],
            [0.1, 0.0, 9.0 + 0.4j, 0.5j, 0.0, 0.2],
            [0.0, 0.3, 0.2j, 10.0 - 0.3j, 0.4, 0.0],
            [0.2j, 0.0, 0.1, 0.0, 11.0 + 0.1j, 0.6],
            [0.0, 0.2, 0.0, 0.4j, 0.1, 12.0 - 0.2j],
        ],
        dtype=np.complex128,
    )
    matrix = permutation @ base
    factor = lu_factor(matrix)
    assert np.count_nonzero(factor[1] != np.arange(6)) >= 2
    rhs = np.asarray(
        [
            [0.2 + 0.1j, -0.3j],
            [0.4 - 0.2j, 0.7],
            [-0.5j, 0.1 + 0.3j],
            [0.6, -0.2 + 0.1j],
            [0.2j, 0.9 - 0.4j],
            [-0.3 + 0.5j, 0.8j],
        ],
        dtype=np.complex128,
    )
    np.testing.assert_allclose(
        _lu_factor_matrix_action(factor, rhs, trans=2),
        matrix.conj().T @ rhs,
        rtol=2.0e-15,
        atol=2.0e-15,
    )
    np.testing.assert_allclose(
        _iteratively_refined_lu_solve(factor, rhs, trans=2),
        np.linalg.solve(matrix.conj().T, rhs),
        rtol=2.0e-15,
        atol=2.0e-15,
    )


def test_nonhermitian_adjoint_recovery_matches_explicit_constrained_block() -> None:
    if MPI.COMM_WORLD.size != 1:
        pytest.skip("serial explicit constrained-block adjoint oracle")
    msh = mesh.create_unit_cube(
        MPI.COMM_SELF,
        1,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
    )
    entity_map = build_variable_p_global_entity_map(
        msh,
        edge_degrees=_degree_array(msh, 1, 4),
        face_degrees=_degree_array(msh, 2, 5),
        cell_degrees=_degree_array(msh, 3, 6),
    )
    constraints = build_variable_p_periodic_constraint_map(
        entity_map,
        axes=("x", "y"),
        phase_x=np.exp(0.2j),
        phase_y=np.exp(-0.3j),
    )
    tensor = _nonhermitian_p6_tensor()
    system = build_variable_p_condensed_trace_system(
        entity_map,
        [tensor],
        tensor_class_keys=("nonhermitian-p6",),
        periodic_constraints=constraints,
    )
    reduced_goal = None
    active_goal = None
    recovered = None
    wrong = None
    dense_matrix = None
    try:
        cell = entity_map.owned_cells[0]
        space = build_variable_p_reference_space(cell.degree_map)
        oriented = space.orient_hcurl_tensor(
            project_p6_local_tensor(space, tensor),
            cell_info=cell.cell_info,
        )
        active_matrix = np.zeros(
            (entity_map.active_rows, entity_map.active_rows),
            dtype=np.complex128,
        )
        active_matrix[np.ix_(cell.active_rows, cell.active_rows)] = oriented
        trace_expansion = _dense_trace_expansion(constraints)
        independent_rows = constraints.independent_trace_rows
        interior_rows = (
            entity_map.active_rows - entity_map.active_trace_rows
        )
        full_expansion = np.zeros(
            (
                entity_map.active_rows,
                independent_rows + interior_rows,
            ),
            dtype=np.complex128,
        )
        full_expansion[
            : entity_map.active_trace_rows,
            :independent_rows,
        ] = trace_expansion
        full_expansion[
            entity_map.active_trace_rows :,
            independent_rows:,
        ] = np.eye(interior_rows)

        indices = np.arange(entity_map.active_rows, dtype=np.float64)
        goal_values = (
            np.sin(0.011 * indices)
            + 0.6j * np.cos(0.007 * indices)
        )
        active_goal = PETSc.Vec().createSeq(entity_map.active_rows)
        active_goal.getArray()[:] = goal_values
        active_goal.assemble()
        reduced_goal = condense_variable_p_active_vector_to_trace(
            system,
            active_goal,
            side="left",
        )
        dense_matrix = system.matrix.convert("dense")
        schur = np.asarray(dense_matrix.getDenseArray()).copy()
        reduced_adjoint = np.linalg.solve(
            schur.conj().T,
            reduced_goal.getArray(readonly=True),
        )
        recovered = recover_variable_p_active_full_adjoint_vector(
            system,
            reduced_adjoint,
            active_full_goal=active_goal,
        )
        audit = audit_variable_p_active_full_adjoint_recovery(
            system,
            recovered,
            active_full_goal=active_goal,
        )
        assert audit["pass"] is True
        assert audit["uses_primal_recovery_operator"] is False

        constrained_matrix = (
            full_expansion.conj().T
            @ active_matrix
            @ full_expansion
        )
        constrained_goal = full_expansion.conj().T @ goal_values
        explicit = np.linalg.solve(
            constrained_matrix.conj().T,
            constrained_goal,
        )
        expected_active = full_expansion @ explicit
        np.testing.assert_allclose(
            recovered.getArray(readonly=True),
            expected_active,
            rtol=5.0e-10,
            atol=5.0e-9,
        )
        np.testing.assert_allclose(
            reduced_adjoint,
            explicit[:independent_rows],
            rtol=5.0e-10,
            atol=5.0e-9,
        )

        wrong = recover_variable_p_active_full_vector(
            system,
            reduced_adjoint,
            active_full_rhs=active_goal,
        )
        wrong_values = np.asarray(
            wrong.getArray(readonly=True),
            dtype=np.complex128,
        )
        wrong_residual = (
            full_expansion.conj().T
            @ (active_matrix.conj().T @ wrong_values - goal_values)
        )
        correct_residual = (
            full_expansion.conj().T
            @ (
                active_matrix.conj().T @ expected_active
                - goal_values
            )
        )
        assert np.linalg.norm(correct_residual) <= 5.0e-8
        assert np.linalg.norm(wrong_residual) >= 1.0e-3
    finally:
        for value in (wrong, recovered, reduced_goal, active_goal):
            if value is not None:
                value.destroy()
        if dense_matrix is not None:
            dense_matrix.destroy()
        system.destroy()


def test_hanging_floquet_adjoint_recovery_closes_on_owned_cells() -> None:
    if MPI.COMM_WORLD.size not in {1, 2}:
        pytest.skip("Task035d adjoint recovery qualifies serial/MPI2")
    entity_map, _, constraints = _periodic_corner_fixture()
    tensor = _nonhermitian_p6_tensor()
    system = build_variable_p_condensed_trace_system(
        entity_map,
        [tensor] * len(entity_map.owned_cells),
        tensor_class_keys=("nonhermitian-p4",)
        * len(entity_map.owned_cells),
        trace_constraints=constraints,
    )
    goal = None
    reduced_adjoint_vector = None
    recovered_adjoint = None
    adjoint = None
    primal = None
    reduced_goal = None
    try:
        reduced_rows = np.arange(
            constraints.independent_trace_rows,
            dtype=np.float64,
        )
        root = (
            np.sin(0.017 * reduced_rows)
            + 1j * np.cos(0.013 * reduced_rows)
        )
        quotient, remainder = divmod(
            entity_map.active_rows,
            MPI.COMM_WORLD.size,
        )
        local_count = quotient + (
            1 if MPI.COMM_WORLD.rank < remainder else 0
        )
        goal = PETSc.Vec().createMPI(
            (local_count, entity_map.active_rows),
            comm=MPI.COMM_WORLD,
        )
        start, stop = goal.getOwnershipRange()
        active_rows = np.arange(start, stop, dtype=np.float64)
        goal_values = (
            np.sin(0.009 * active_rows)
            - 0.4j * np.cos(0.015 * active_rows)
        )
        goal_values[
            active_rows < entity_map.active_trace_rows
        ] = 0.0
        goal.getArray()[:] = goal_values
        goal.assemble()

        reduced_adjoint_vector = system.matrix.createVecRight()
        reduced_start, reduced_stop = (
            reduced_adjoint_vector.getOwnershipRange()
        )
        reduced_adjoint_vector.getArray()[:] = root[
            reduced_start:reduced_stop
        ]
        reduced_adjoint_vector.assemble()
        reduction = VariablePAssemblyTimeReduction(
            system=system,
            transfer=None,  # type: ignore[arg-type]
            degree_plan=None,  # type: ignore[arg-type]
            build_audit={"pass": True},
        )
        recovered_adjoint = reduction.recover_adjoint(
            reduced_adjoint_vector,
            None,
            active_full_goal_override=goal,
        )
        adjoint = recovered_adjoint.active_full_adjoint
        assert recovered_adjoint.audit["status"] == (
            "variable_p_adjoint_interior_constraint_recovery_pass"
        )
        assert (
            recovered_adjoint.audit[
                "reduced_adjoint_equation_checked"
            ]
            is False
        )
        assert recovered_adjoint.audit["full_adjoint_solve_pass"] is False
        audit = recovered_adjoint.audit["interior_recovery"]
        assert audit["pass"] is True
        assert audit["eliminated_cell_interior_equations"] == (
            entity_map.active_rows - entity_map.active_trace_rows
        )
        assert audit["relative_residual"] <= 5.0e-11

        global_adjoint = _global_vector_values(adjoint)
        expected_trace = _global_trace_expansion(constraints) @ root
        np.testing.assert_allclose(
            global_adjoint[: entity_map.active_trace_rows],
            expected_trace,
            rtol=3.0e-12,
            atol=3.0e-12,
        )
        global_goal = _global_vector_values(goal)
        local_maximum = 0.0
        for recovery in system.cell_recovery:
            cell = recovery.cell
            space = recovery.space
            oriented = space.orient_hcurl_tensor(
                project_p6_local_tensor(space, tensor),
                cell_info=cell.cell_info,
            )
            trace = space.trace_dofs
            interior = space.interior_dofs
            local_adjoint = global_adjoint[cell.active_rows]
            residual = (
                oriented[np.ix_(interior, interior)].conj().T
                @ local_adjoint[interior]
                + oriented[np.ix_(trace, interior)].conj().T
                @ local_adjoint[trace]
                - global_goal[cell.interior_rows]
            )
            local_maximum = max(
                local_maximum,
                float(np.max(np.abs(residual), initial=0.0)),
            )
        maximum = MPI.COMM_WORLD.allreduce(local_maximum, op=MPI.MAX)
        assert maximum <= 5.0e-9

        reduced_goal = condense_variable_p_active_vector_to_trace(
            system,
            goal,
            side="left",
        )
        primal = recover_variable_p_active_full_vector(system, root)
        left = np.vdot(global_goal, _global_vector_values(primal))
        right = np.vdot(_global_vector_values(reduced_goal), root)
        assert abs(left - right) / max(abs(left), abs(right), 1.0) <= 5.0e-11
        assert sparse.issparse(constraints.component_gram)

        system.appended_rows = 1
        with pytest.raises(
            RuntimeError,
            match="trace-only interior-coupling qualification",
        ):
            reduction.recover_adjoint(
                reduced_adjoint_vector,
                None,
                active_full_goal_override=goal,
            )
        system.appended_rows = 0

        if MPI.COMM_WORLD.size == 2:
            wrong_communicator = PETSc.Vec().createSeq(
                constraints.independent_trace_rows,
                comm=PETSc.COMM_SELF,
            )
            try:
                with pytest.raises(
                    ValueError,
                    match="different MPI communicator",
                ):
                    recover_variable_p_active_full_adjoint_vector(
                        system,
                        wrong_communicator,
                        active_full_goal=goal,
                    )
            finally:
                wrong_communicator.destroy()
    finally:
        if recovered_adjoint is not None:
            recovered_adjoint.destroy()
            recovered_adjoint.destroy()
            adjoint = None
        system.appended_rows = 0
        for value in (
            reduced_goal,
            primal,
            adjoint,
            reduced_adjoint_vector,
            goal,
        ):
            if value is not None:
                value.destroy()
        system.destroy()
