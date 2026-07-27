from __future__ import annotations

import unittest

import numpy as np
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lu_factor, lu_solve

from src.adaptivity.variable_p_degree_plan import (
    build_variable_p_cell_degree_plan,
    cell_box_catalog,
)
from src.adaptivity.variable_p_periodic_orbits import (
    build_variable_p_periodic_constraint_map,
)
from src.adaptivity.variable_p_transfer import (
    build_variable_p_global_transfer,
)
from src.solvers.hcurl_variable_p_assembly import (
    _iteratively_refined_lu_solve,
    build_variable_p_condensed_trace_system,
)
from src.solvers.hcurl_variable_p_reduction import (
    VariablePAssemblyTimeReduction,
    _lu_factor_matrix_action,
)


def _dense_p6_tensor() -> np.ndarray:
    values = np.linspace(0.1, 1.0, 882)
    return (
        np.diag(3.0 + values)
        + 0.005 * np.outer(values, values)
    ).astype(np.complex128)


def _nonhermitian_p6_tensor() -> np.ndarray:
    values = np.linspace(0.1, 1.0, 882)
    reverse = values[::-1] * (1.0 + 0.07j)
    return (
        np.diag(4.0 + values + 0.03j * values)
        + 0.003 * np.outer(values, reverse)
    ).astype(np.complex128)


class Task035dVariablePReductionTests(unittest.TestCase):
    def test_lu_factor_action_reconstructs_pivoted_complex_matrix(
        self,
    ) -> None:
        matrix = np.asarray(
            [
                [0.0, 2.0 + 0.5j, -1.0],
                [4.0 - 0.2j, 1.0, 0.3j],
                [1.5, -0.7j, 3.0 + 0.4j],
            ],
            dtype=np.complex128,
        )
        values = np.asarray(
            [0.2 + 0.1j, -0.4 + 0.7j, 1.2 - 0.3j],
            dtype=np.complex128,
        )
        np.testing.assert_allclose(
            _lu_factor_matrix_action(lu_factor(matrix), values),
            matrix @ values,
            rtol=2.0e-15,
            atol=2.0e-15,
        )

    def test_lu_interior_recovery_refinement_never_worsens_residual(
        self,
    ) -> None:
        rng = np.random.default_rng(350189)
        left, _ = np.linalg.qr(
            rng.standard_normal((24, 24))
            + 1j * rng.standard_normal((24, 24))
        )
        right, _ = np.linalg.qr(
            rng.standard_normal((24, 24))
            + 1j * rng.standard_normal((24, 24))
        )
        matrix = (
            left
            @ np.diag(np.geomspace(1.0, 1.0e-10, 24))
            @ right.conj().T
        )
        rhs = (
            rng.standard_normal(24)
            + 1j * rng.standard_normal(24)
        )
        factor = lu_factor(matrix)
        raw = lu_solve(factor, rhs)
        refined = _iteratively_refined_lu_solve(factor, rhs)
        raw_residual = np.linalg.norm(
            _lu_factor_matrix_action(factor, raw) - rhs
        )
        refined_residual = np.linalg.norm(
            _lu_factor_matrix_action(factor, refined) - rhs
        )

        self.assertTrue(np.all(np.isfinite(refined)))
        self.assertLessEqual(refined_residual, raw_residual)

    def test_adapter_reduces_recovers_and_audits_true_active_system(
        self,
    ) -> None:
        if MPI.COMM_WORLD.size != 1:
            self.skipTest("serial variable-p adapter identity")
        msh = mesh.create_unit_cube(
            MPI.COMM_SELF,
            1,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
        )
        boxes = cell_box_catalog(msh)
        degree_plan = build_variable_p_cell_degree_plan(
            msh,
            {box: 5 for box in boxes},
        )
        periodic = build_variable_p_periodic_constraint_map(
            degree_plan.entity_map,
            axes=("x", "y"),
            phase_x=np.exp(0.2j),
            phase_y=np.exp(-0.3j),
        )
        p6_space = fem.functionspace(
            msh,
            element(
                "N1curl",
                msh.basix_cell(),
                6,
                dtype=default_real_type,
            ),
        )
        transfer = build_variable_p_global_transfer(
            degree_plan.entity_map,
            p6_space,
        )
        system = build_variable_p_condensed_trace_system(
            degree_plan.entity_map,
            [_dense_p6_tensor()],
            tensor_class_keys=("uniform-p5-in-p6",),
            periodic_constraints=periodic,
        )
        reduction = VariablePAssemblyTimeReduction(
            system=system,
            transfer=transfer,
            degree_plan=degree_plan,
            build_audit={"pass": True},
        )
        p6_rhs = fem.Function(p6_space)
        rows = np.arange(len(p6_rhs.x.array), dtype=np.float64)
        p6_rhs.x.array[:] = (
            np.sin(0.013 * rows)
            + 1j * np.cos(0.017 * rows)
        )
        p6_rhs.x.scatter_forward()
        reduced_rhs = reduction.reduce_p6_vector(
            p6_rhs.x.petsc_vec,
            side="right",
        )
        dense_matrix = system.matrix.convert("dense")
        reduced_solution = system.matrix.createVecRight()
        reduced_solution.getArray()[:] = np.linalg.solve(
            dense_matrix.getDenseArray(),
            reduced_rhs.getArray(readonly=True),
        )
        reduced_solution.assemble()
        recovered = reduction.recover(
            reduced_solution,
            p6_rhs.x.petsc_vec,
        )
        try:
            residual = reduction.full_active_residual(
                system.matrix,
                reduced_rhs,
                reduced_solution,
                recovered,
            )
            self.assertLessEqual(
                residual["linear_system_relative_residual"],
                2.0e-12,
            )
            self.assertLessEqual(
                residual[
                    "eliminated_cell_interior_max_abs_residual"
                ],
                2.0e-10,
            )
            self.assertTrue(recovered.audit["pass"])
            self.assertEqual(
                recovered.audit["active_full_rows"],
                degree_plan.entity_map.active_rows,
            )
            self.assertFalse(
                recovered.audit["full_p6_global_matrix_allocated"]
            )
            self.assertEqual(
                recovered.audit["interior_trace_source"],
                "assembled_global_active_trace",
            )
            self.assertTrue(
                recovered.audit[
                    "trace_vector_assembled_before_interior_recovery"
                ]
            )
        finally:
            recovered.active_full_solution.destroy()
            recovered.active_full_rhs.destroy()
            if recovered.active_auxiliary_interior_action is not None:
                recovered.active_auxiliary_interior_action.destroy()
            reduced_solution.destroy()
            reduced_rhs.destroy()
            dense_matrix.destroy()
            reduction.destroy()

    def test_auxiliary_right_column_recovery_and_residual_are_exact(
        self,
    ) -> None:
        if MPI.COMM_WORLD.size != 1:
            self.skipTest("serial non-Hermitian auxiliary identity")
        msh = mesh.create_unit_cube(
            MPI.COMM_SELF,
            1,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
        )
        degree_plan = build_variable_p_cell_degree_plan(
            msh,
            {box: 5 for box in cell_box_catalog(msh)},
        )
        periodic = build_variable_p_periodic_constraint_map(
            degree_plan.entity_map,
            axes=("x", "y"),
            phase_x=np.exp(0.31j),
            phase_y=np.exp(-0.27j),
        )
        p6_space = fem.functionspace(
            msh,
            element(
                "N1curl",
                msh.basix_cell(),
                6,
                dtype=default_real_type,
            ),
        )
        transfer = build_variable_p_global_transfer(
            degree_plan.entity_map,
            p6_space,
        )
        system = build_variable_p_condensed_trace_system(
            degree_plan.entity_map,
            [_nonhermitian_p6_tensor()],
            tensor_class_keys=("nonhermitian-p5-in-p6",),
            periodic_constraints=periodic,
            appended_global_rows=1,
            appended_support_owned_cell_groups=(
                np.asarray([0], dtype=np.int32),
            ),
            appended_support_group_by_row=(0,),
            defer_final_assembly=True,
        )
        system.matrix.setValue(
            system.active_trace_rows,
            system.active_trace_rows,
            PETSc.ScalarType(1.0),
            addv=PETSc.InsertMode.ADD_VALUES,
        )
        system.matrix.assemble()
        reduction = VariablePAssemblyTimeReduction(
            system=system,
            transfer=transfer,
            degree_plan=degree_plan,
            build_audit={"pass": True},
        )
        rng = np.random.default_rng(3518902)
        reduced_solution = system.matrix.createVecRight()
        reduced_values = (
            rng.standard_normal(system.active_trace_rows + 1)
            + 1j
            * rng.standard_normal(system.active_trace_rows + 1)
        )
        reduced_solution.getArray()[:] = reduced_values
        reduced_solution.assemble()
        reduced_rhs = system.matrix.createVecLeft()
        system.matrix.mult(reduced_solution, reduced_rhs)

        cell_recovery = system.cell_recovery[0]
        cell = cell_recovery.cell
        trace = np.zeros(
            degree_plan.entity_map.active_trace_rows,
            dtype=np.complex128,
        )
        for block in periodic.entity_blocks.values():
            trace[block.full_rows] = (
                block.full_from_independent
                @ reduced_values[block.independent_rows]
            )
        homogeneous = (
            system.interior_from_trace_by_class[
                cell_recovery.class_key
            ]
            @ trace[cell.trace_rows]
        )
        expected_interior = (
            rng.standard_normal(len(cell.interior_rows))
            + 1j * rng.standard_normal(len(cell.interior_rows))
        )
        traction_interior = (
            rng.standard_normal(len(cell.interior_rows))
            + 1j * rng.standard_normal(len(cell.interior_rows))
        )
        auxiliary_value = reduced_values[-1]
        raw_interior_rhs = _lu_factor_matrix_action(
            system.interior_lu_by_class[cell_recovery.class_key],
            expected_interior - homogeneous,
        ) - traction_interior * auxiliary_value
        active_rhs = PETSc.Vec().createSeq(
            degree_plan.entity_map.active_rows
        )
        active_rhs.set(PETSc.ScalarType(0.0))
        active_rhs.setValues(
            np.asarray(cell.interior_rows, dtype=PETSc.IntType),
            np.asarray(raw_interior_rhs, dtype=PETSc.ScalarType),
        )
        active_rhs.assemble()

        recovered = reduction.recover(
            reduced_solution,
            None,
            active_full_rhs_override=active_rhs,
            auxiliary_interior_columns_local=(
                traction_interior.reshape((-1, 1))
            ),
            auxiliary_values=np.asarray([auxiliary_value]),
        )
        try:
            observed = np.asarray(
                recovered.active_full_solution.getArray(readonly=True)
            )
            np.testing.assert_allclose(
                observed[cell.interior_rows],
                expected_interior,
                rtol=3.0e-12,
                atol=3.0e-12,
            )
            residual = reduction.full_active_residual(
                system.matrix,
                reduced_rhs,
                reduced_solution,
                recovered,
            )
            self.assertLessEqual(
                residual["linear_system_relative_residual"],
                3.0e-12,
            )
            self.assertLessEqual(
                residual[
                    "eliminated_cell_interior_max_abs_residual"
                ],
                3.0e-11,
            )
            self.assertTrue(
                residual["auxiliary_interior_action_included"]
            )
            self.assertEqual(
                recovered.audit["active_full_rhs_source"],
                "preprojected_active_full_rhs",
            )
        finally:
            recovered.active_full_solution.destroy()
            recovered.active_full_rhs.destroy()
            self.assertIsNotNone(
                recovered.active_auxiliary_interior_action
            )
            recovered.active_auxiliary_interior_action.destroy()
            active_rhs.destroy()
            reduced_rhs.destroy()
            reduced_solution.destroy()
            reduction.destroy()

    def test_trace_only_functional_gate_is_fail_closed(self) -> None:
        if MPI.COMM_WORLD.size != 1:
            self.skipTest("serial trace-only functional gate")
        msh = mesh.create_unit_cube(
            MPI.COMM_SELF,
            1,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
        )
        degree_plan = build_variable_p_cell_degree_plan(
            msh,
            {box: 5 for box in cell_box_catalog(msh)},
        )
        periodic = build_variable_p_periodic_constraint_map(
            degree_plan.entity_map,
            axes=("x", "y"),
            phase_x=np.exp(0.1j),
            phase_y=np.exp(-0.2j),
        )
        p6_space = fem.functionspace(
            msh,
            element(
                "N1curl",
                msh.basix_cell(),
                6,
                dtype=default_real_type,
            ),
        )
        system = build_variable_p_condensed_trace_system(
            degree_plan.entity_map,
            [_dense_p6_tensor()],
            tensor_class_keys=("trace-only-gate",),
            periodic_constraints=periodic,
        )
        reduction = VariablePAssemblyTimeReduction(
            system=system,
            transfer=build_variable_p_global_transfer(
                degree_plan.entity_map,
                p6_space,
            ),
            degree_plan=degree_plan,
            build_audit={"pass": True},
        )
        functional = PETSc.Vec().createSeq(
            degree_plan.entity_map.active_rows
        )
        functional.set(PETSc.ScalarType(0.0))
        functional.setValue(0, PETSc.ScalarType(1.0))
        functional.setValue(
            degree_plan.entity_map.active_trace_rows,
            PETSc.ScalarType(1.0e-14),
        )
        functional.assemble()
        audit = reduction.enforce_trace_only_active_functional(
            functional,
            role="roundoff-positive-control",
        )
        self.assertTrue(audit["pass"])
        self.assertEqual(
            functional.getValue(
                degree_plan.entity_map.active_trace_rows
            ),
            0.0,
        )
        functional.setValue(
            degree_plan.entity_map.active_trace_rows,
            PETSc.ScalarType(1.0e-4),
        )
        functional.assemble()
        with self.assertRaisesRegex(
            RuntimeError,
            "not a trace-only N1curl functional",
        ):
            reduction.enforce_trace_only_active_functional(
                functional,
                role="fault-injection",
            )
        functional.destroy()
        reduction.destroy()


if __name__ == "__main__":
    unittest.main()
