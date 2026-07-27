from __future__ import annotations

import unittest

import numpy as np
from dolfinx import mesh
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lu_factor, lu_solve
from scipy import sparse

from src.adaptivity.exact_sequence_variable_p import (
    HexaEntityDegreeMap,
    build_variable_p_reference_space,
)
from src.adaptivity.variable_p_entity_map import (
    build_variable_p_global_entity_map,
    structural_sparsity_audit,
)
from src.adaptivity.variable_p_periodic_orbits import (
    build_variable_p_periodic_constraint_map,
)
from src.solvers.hcurl_variable_p_assembly import (
    build_variable_p_condensed_trace_system,
    condense_variable_p_active_vector_to_trace,
    recover_variable_p_active_full_vector,
    retained_variable_p_owned_cell_schur_actions,
    variable_p_cell_interior_schur_bilinear,
)
from src.solvers.hcurl_variable_p_local import project_p6_local_tensor


def _degree_array(msh, dimension: int, degree: int) -> np.ndarray:
    msh.topology.create_entities(dimension)
    index_map = msh.topology.index_map(dimension)
    return np.full(
        int(index_map.size_local + index_map.num_ghosts),
        int(degree),
        dtype=np.int32,
    )


def _entity_map(msh, edge: int, face: int, cell: int):
    return build_variable_p_global_entity_map(
        msh,
        edge_degrees=_degree_array(msh, 1, edge),
        face_degrees=_degree_array(msh, 2, face),
        cell_degrees=_degree_array(msh, 3, cell),
    )


def _dense_p6_tensor() -> np.ndarray:
    values = np.linspace(0.1, 1.0, 882)
    return np.diag(2.0 + values) + 0.01 * np.outer(values, values)


def _periodic_structural_nnz(constraints) -> int:
    local_rows = [
        np.repeat(cell.independent_rows, len(cell.independent_rows))
        for cell in constraints.owned_cells
    ]
    local_columns = [
        np.tile(cell.independent_rows, len(cell.independent_rows))
        for cell in constraints.owned_cells
    ]
    packet = (
        np.concatenate(local_rows)
        if local_rows
        else np.empty(0, dtype=np.int64),
        np.concatenate(local_columns)
        if local_columns
        else np.empty(0, dtype=np.int64),
    )
    packets = MPI.COMM_WORLD.allgather(packet)
    rows = np.concatenate([values[0] for values in packets])
    columns = np.concatenate([values[1] for values in packets])
    graph = sparse.coo_matrix(
        (
            np.ones(len(rows), dtype=np.int8),
            (rows, columns),
        ),
        shape=(
            constraints.independent_trace_rows,
            constraints.independent_trace_rows,
        ),
    ).tocsr()
    graph.data[:] = 1
    return int(graph.nnz)


def _relative_hermitian_action_error(matrix: PETSc.Mat) -> float:
    left_vector = matrix.createVecRight()
    right_vector = matrix.createVecRight()
    applied_left = matrix.createVecLeft()
    applied_right = matrix.createVecLeft()
    start, end = left_vector.getOwnershipRange()
    rows = np.arange(start, end, dtype=np.float64)
    left_vector.getArray()[:] = (
        np.sin(0.017 * rows) + 1j * np.cos(0.013 * rows)
    )
    right_vector.getArray()[:] = (
        np.cos(0.019 * rows) + 1j * np.sin(0.023 * rows)
    )
    left_vector.assemble()
    right_vector.assemble()
    matrix.mult(left_vector, applied_left)
    matrix.mult(right_vector, applied_right)
    left = complex(left_vector.dot(applied_right))
    right = complex(applied_left.dot(right_vector))
    relative = abs(left - right) / max(abs(left), abs(right), 1.0)
    for vector in (
        left_vector,
        right_vector,
        applied_left,
        applied_right,
    ):
        vector.destroy()
    return relative


class Task035dVariablePPETScAssemblyTests(unittest.TestCase):
    def test_single_cell_uniform_p6_degenerates_to_direct_schur(self) -> None:
        if MPI.COMM_WORLD.size != 1:
            self.skipTest("serial single-cell matrix identity")
        msh = mesh.create_unit_cube(
            MPI.COMM_SELF,
            1,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
        )
        entity_map = _entity_map(msh, 6, 6, 6)
        p6_tensor = _dense_p6_tensor()
        system = build_variable_p_condensed_trace_system(
            entity_map,
            [p6_tensor],
            tensor_class_keys=("uniform-p6",),
        )
        try:
            space = build_variable_p_reference_space(
                HexaEntityDegreeMap.uniform(6)
            )
            oriented = space.orient_hcurl_tensor(
                p6_tensor,
                cell_info=entity_map.owned_cells[0].cell_info,
            )
            trace = space.trace_dofs
            interior = space.interior_dofs
            A_tt = oriented[np.ix_(trace, trace)]
            A_ti = oriented[np.ix_(trace, interior)]
            A_it = oriented[np.ix_(interior, trace)]
            A_ii = oriented[np.ix_(interior, interior)]
            direct = A_tt - A_ti @ lu_solve(lu_factor(A_ii), A_it)
            rows = np.arange(len(trace), dtype=np.int32)
            observed = np.asarray(system.matrix.getValues(rows, rows))
            np.testing.assert_allclose(
                observed,
                direct,
                rtol=2.0e-12,
                atol=2.0e-12,
            )
            self.assertEqual(system.build_audit["matrix_rows"], 432)
            self.assertEqual(system.build_audit["matrix_nnz"], 432**2)
            self.assertEqual(system.build_audit["matrix_mallocs"], 0)
            self.assertIsNone(
                system.retained_local_schur_by_class
            )
            retention = system.build_audit[
                "research_local_schur_retention"
            ]
            self.assertFalse(retention["enabled"])
            self.assertEqual(
                retention["numpy_payload_bytes_local"],
                0,
            )
        finally:
            system.destroy()

    def test_2x2x2_variable_p_assembles_real_smaller_petsc_matrix(
        self,
    ) -> None:
        if MPI.COMM_WORLD.size not in {1, 2}:
            self.skipTest("Task035d A4 qualifies serial and MPI2")
        msh = mesh.create_unit_cube(
            MPI.COMM_WORLD,
            2,
            2,
            2,
            cell_type=mesh.CellType.hexahedron,
            ghost_mode=mesh.GhostMode.shared_facet,
        )
        entity_map = _entity_map(msh, 4, 5, 6)
        p6_tensor = _dense_p6_tensor().astype(np.complex128)
        tensors = [p6_tensor] * len(entity_map.owned_cells)
        system = build_variable_p_condensed_trace_system(
            entity_map,
            tensors,
            tensor_class_keys=("shared-p6-tensor",) * len(tensors),
        )
        try:
            structural = structural_sparsity_audit(
                entity_map,
                condensed_trace=True,
            )
            audit = system.build_audit
            self.assertTrue(audit["pass"])
            self.assertEqual(audit["active_full3d_rows_before_condensation"], 5256)
            self.assertEqual(audit["active_trace_rows"], 1656)
            self.assertEqual(audit["uniform_p6_full3d_rows"], 6084)
            self.assertEqual(audit["uniform_p6_trace_rows"], 2484)
            self.assertEqual(audit["inactive_p6_full_rows"], 828)
            self.assertEqual(audit["inactive_p6_trace_rows"], 828)
            self.assertEqual(audit["matrix_rows"], 1656)
            self.assertEqual(
                audit["matrix_nnz"],
                structural["structural_nnz"],
            )
            self.assertEqual(audit["matrix_mallocs"], 0)
            self.assertFalse(audit["full_p6_global_matrix_constructed"])
            self.assertFalse(audit["inactive_p6_rows_globally_numbered"])
            self.assertLessEqual(
                _relative_hermitian_action_error(system.matrix),
                2.0e-12,
            )

            rng = np.random.default_rng(35185)
            trace_values = (
                rng.standard_normal(entity_map.active_trace_rows)
                + 1j * rng.standard_normal(entity_map.active_trace_rows)
            )
            recovered = system.recover_owned_active_cells(trace_values)
            for cell, active in recovered:
                space = build_variable_p_reference_space(cell.degree_map)
                local_tensor = project_p6_local_tensor(space, p6_tensor)
                oriented = space.orient_hcurl_tensor(
                    local_tensor,
                    cell_info=cell.cell_info,
                )
                residual = oriented @ active
                self.assertLessEqual(
                    float(
                        np.max(
                            np.abs(residual[space.interior_dofs]),
                            initial=0.0,
                        )
                    ),
                    2.0e-9,
                )
        finally:
            system.destroy()

        constraints = build_variable_p_periodic_constraint_map(
            entity_map,
            axes=("x", "y"),
            phase_x=np.exp(0.2j),
            phase_y=np.exp(-0.3j),
        )
        periodic_system = build_variable_p_condensed_trace_system(
            entity_map,
            tensors,
            tensor_class_keys=("shared-p6-tensor",) * len(tensors),
            periodic_constraints=constraints,
            retain_local_schur_for_research=True,
        )
        try:
            audit = periodic_system.build_audit
            self.assertEqual(
                audit["active_trace_rows_before_periodic_elimination"],
                1656,
            )
            self.assertEqual(audit["active_trace_rows"], 1248)
            self.assertEqual(audit["periodic_slave_rows"], 408)
            self.assertEqual(audit["matrix_rows"], 1248)
            self.assertEqual(
                audit["matrix_nnz"],
                _periodic_structural_nnz(constraints),
            )
            self.assertEqual(audit["matrix_mallocs"], 0)
            self.assertTrue(
                audit["floquet_elimination_applied_before_insertion"]
            )
            self.assertFalse(
                audit["periodic_slave_rows_globally_numbered"]
            )
            self.assertLessEqual(
                _relative_hermitian_action_error(
                    periodic_system.matrix
                ),
                2.0e-12,
            )

            rng = np.random.default_rng(3518502)
            independent_trace = (
                rng.standard_normal(constraints.independent_trace_rows)
                + 1j
                * rng.standard_normal(constraints.independent_trace_rows)
            )
            retained = periodic_system.retained_local_schur_by_class
            self.assertIsNotNone(retained)
            self.assertEqual(
                set(retained),
                {
                    recovery.class_key
                    for recovery in periodic_system.cell_recovery
                },
            )
            with self.assertRaises(TypeError):
                retained[("forbidden",)] = np.eye(1)
            retained_bytes = int(
                sum(value.nbytes for value in retained.values())
            )
            retention = periodic_system.build_audit[
                "research_local_schur_retention"
            ]
            self.assertTrue(retention["enabled"])
            self.assertTrue(retention["readonly"])
            self.assertEqual(
                retention["numpy_payload_bytes_local"],
                retained_bytes,
            )
            self.assertEqual(retention["new_array_copy_bytes"], 0)
            for value in retained.values():
                self.assertFalse(value.flags.writeable)
                with self.assertRaises(ValueError):
                    value.flat[0] = 0.0
            actions, action_audit = (
                retained_variable_p_owned_cell_schur_actions(
                    periodic_system,
                    reduced_trace_values=independent_trace,
                )
            )
            self.assertTrue(action_audit["pass"])
            self.assertEqual(
                action_audit["owned_cell_count_local"],
                len(entity_map.owned_cells),
            )
            recovery_by_global_cell = {
                recovery.cell.global_cell: recovery
                for recovery in periodic_system.cell_recovery
            }
            constraint_by_global_cell = {
                cell.global_cell: cell
                for cell in constraints.owned_cells
            }
            for action in actions:
                recovery = recovery_by_global_cell[
                    action.global_cell
                ]
                constrained = constraint_by_global_cell[
                    action.global_cell
                ]
                expected_local_trace = (
                    constrained.full_trace_from_independent
                    @ independent_trace[constrained.independent_rows]
                )
                np.testing.assert_allclose(
                    action.local_trace_values,
                    expected_local_trace,
                    rtol=2.0e-13,
                    atol=2.0e-13,
                )
                np.testing.assert_allclose(
                    action.local_condensed_action,
                    retained[recovery.class_key]
                    @ expected_local_trace,
                    rtol=2.0e-13,
                    atol=2.0e-13,
                )
            replayed, replay_audit = (
                retained_variable_p_owned_cell_schur_actions(
                    periodic_system,
                    local_trace_values_by_global_cell={
                        action.global_cell: action.local_trace_values
                        for action in actions
                    },
                )
            )
            self.assertEqual(
                replay_audit["trace_source"],
                "hash_qualified_per_global_cell_snapshot",
            )
            for original, replay in zip(
                actions,
                replayed,
                strict=True,
            ):
                self.assertEqual(
                    replay.global_cell,
                    original.global_cell,
                )
                np.testing.assert_array_equal(
                    replay.trace_rows,
                    original.trace_rows,
                )
                np.testing.assert_allclose(
                    replay.local_condensed_action,
                    original.local_condensed_action,
                    rtol=2.0e-13,
                    atol=2.0e-13,
                )
            release = periodic_system.release_retained_local_schur()
            self.assertTrue(release["pass"])
            self.assertEqual(
                release["local_bytes_released"],
                retained_bytes,
            )
            self.assertIsNone(
                periodic_system.retained_local_schur_by_class
            )
            with self.assertRaisesRegex(
                RuntimeError,
                "explicit research retention",
            ):
                retained_variable_p_owned_cell_schur_actions(
                    periodic_system,
                    reduced_trace_values=independent_trace,
                )
            recovered = periodic_system.recover_owned_active_cells(
                independent_trace
            )
            for cell, active in recovered:
                space = build_variable_p_reference_space(cell.degree_map)
                local_tensor = project_p6_local_tensor(space, p6_tensor)
                oriented = space.orient_hcurl_tensor(
                    local_tensor,
                    cell_info=cell.cell_info,
                )
                residual = oriented @ active
                self.assertLessEqual(
                    float(
                        np.max(
                            np.abs(residual[space.interior_dofs]),
                            initial=0.0,
                        )
                    ),
                    2.0e-9,
                )
        finally:
            periodic_system.destroy()

    def test_periodic_rhs_schur_bilinear_and_full_recovery_are_exact(
        self,
    ) -> None:
        if MPI.COMM_WORLD.size != 1:
            self.skipTest("serial dense variable-p Schur identity")
        msh = mesh.create_unit_cube(
            MPI.COMM_SELF,
            1,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
        )
        entity_map = _entity_map(msh, 4, 5, 6)
        constraints = build_variable_p_periodic_constraint_map(
            entity_map,
            axes=("x", "y"),
            phase_x=np.exp(0.2j),
            phase_y=np.exp(-0.3j),
        )
        p6_tensor = _dense_p6_tensor().astype(np.complex128)
        system = build_variable_p_condensed_trace_system(
            entity_map,
            [p6_tensor],
            tensor_class_keys=("one-cell-p6",),
            periodic_constraints=constraints,
        )
        try:
            cell = entity_map.owned_cells[0]
            space = build_variable_p_reference_space(cell.degree_map)
            active_tensor = project_p6_local_tensor(space, p6_tensor)
            oriented = space.orient_hcurl_tensor(
                active_tensor,
                cell_info=cell.cell_info,
            )
            periodic_cell = constraints.owned_cells[0]
            rng = np.random.default_rng(3518503)
            expected_trace = (
                rng.standard_normal(constraints.independent_trace_rows)
                + 1j
                * rng.standard_normal(
                    constraints.independent_trace_rows
                )
            )
            expected_active = np.zeros(
                space.hcurl_dimension,
                dtype=np.complex128,
            )
            expected_active[space.trace_dofs] = (
                periodic_cell.full_trace_from_independent
                @ expected_trace
            )
            expected_active[space.interior_dofs] = (
                rng.standard_normal(len(space.interior_dofs))
                + 1j * rng.standard_normal(len(space.interior_dofs))
            )
            active_rhs_values = oriented @ expected_active
            active_rhs = PETSc.Vec().createSeq(entity_map.active_rows)
            active_rhs.getArray()[:] = active_rhs_values
            active_rhs.assemble()

            reduced = condense_variable_p_active_vector_to_trace(
                system,
                active_rhs,
                side="right",
            )
            matrix_dense = np.asarray(
                system.matrix.convert("dense").getDenseArray()
            ).copy()
            np.testing.assert_allclose(
                reduced.getArray(readonly=True),
                matrix_dense @ expected_trace,
                rtol=2.0e-11,
                atol=2.0e-9,
            )
            solved_trace = np.linalg.solve(
                matrix_dense,
                reduced.getArray(readonly=True),
            )
            recovered = recover_variable_p_active_full_vector(
                system,
                solved_trace,
                active_full_rhs=active_rhs,
            )
            np.testing.assert_allclose(
                recovered.getArray(readonly=True),
                expected_active,
                rtol=2.0e-9,
                atol=2.0e-8,
            )

            left = PETSc.Vec().createSeq(entity_map.active_rows)
            right = PETSc.Vec().createSeq(entity_map.active_rows)
            left_values = (
                rng.standard_normal(entity_map.active_rows)
                + 1j * rng.standard_normal(entity_map.active_rows)
            )
            right_values = (
                rng.standard_normal(entity_map.active_rows)
                + 1j * rng.standard_normal(entity_map.active_rows)
            )
            left.getArray()[:] = left_values
            right.getArray()[:] = right_values
            left.assemble()
            right.assemble()
            expected_bilinear = np.vdot(
                left_values[cell.interior_rows],
                np.linalg.solve(
                    oriented[
                        np.ix_(
                            space.interior_dofs,
                            space.interior_dofs,
                        )
                    ],
                    right_values[cell.interior_rows],
                ),
            )
            self.assertAlmostEqual(
                variable_p_cell_interior_schur_bilinear(
                    system,
                    left,
                    right,
                ),
                expected_bilinear,
                places=10,
            )
        finally:
            for name in ("left", "right", "recovered", "reduced", "active_rhs"):
                value = locals().get(name)
                if value is not None:
                    value.destroy()
            system.destroy()


if __name__ == "__main__":
    unittest.main()
