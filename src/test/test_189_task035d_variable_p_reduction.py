from __future__ import annotations

import unittest

import numpy as np
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from scipy.linalg import lu_factor

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
        finally:
            recovered.active_full_solution.destroy()
            recovered.active_full_rhs.destroy()
            reduced_solution.destroy()
            reduced_rhs.destroy()
            dense_matrix.destroy()
            reduction.destroy()


if __name__ == "__main__":
    unittest.main()
