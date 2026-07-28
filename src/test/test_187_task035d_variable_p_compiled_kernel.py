from __future__ import annotations

import unittest

import numpy as np
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from dolfinx.fem import petsc as fem_petsc
from mpi4py import MPI
from petsc4py import PETSc

from src.adaptivity.variable_p_entity_map import (
    build_variable_p_global_entity_map,
)
from src.adaptivity.variable_p_periodic_orbits import (
    build_variable_p_periodic_constraint_map,
)
from src.solvers.hcurl_variable_p_assembly import (
    build_variable_p_condensed_trace_system,
    build_variable_p_condensed_trace_system_from_compiled_form,
)


def _degree_array(msh, dimension: int, degree: int) -> np.ndarray:
    msh.topology.create_entities(dimension)
    index_map = msh.topology.index_map(dimension)
    return np.full(
        int(index_map.size_local + index_map.num_ghosts),
        int(degree),
        dtype=np.int32,
    )


class Task035dVariablePCompiledKernelTests(unittest.TestCase):
    def test_ffcx_p6_kernel_matches_standard_projection_and_preallocation(
        self,
    ) -> None:
        if MPI.COMM_WORLD.size != 1:
            self.skipTest("serial compiled-kernel identity")
        msh = mesh.create_unit_cube(
            MPI.COMM_SELF,
            1,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
        )
        cell_tags = mesh.meshtags(
            msh,
            msh.topology.dim,
            np.asarray([0], dtype=np.int32),
            np.asarray([1], dtype=np.int32),
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
        trial = ufl.TrialFunction(p6_space)
        test = ufl.TestFunction(p6_space)
        dx = ufl.Measure("dx", domain=msh, subdomain_data=cell_tags)
        compiled = fem.form(
            (
                ufl.inner(ufl.curl(trial), ufl.curl(test))
                + PETSc.ScalarType(2.5 - 0.2j)
                * ufl.inner(trial, test)
            )
            * dx(1)
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
        candidate = (
            build_variable_p_condensed_trace_system_from_compiled_form(
                compiled,
                p6_space,
                cell_tags,
                entity_map,
                periodic_constraints=constraints,
                appended_global_rows=2,
                appended_support_owned_cell_groups=(
                    np.asarray([0], dtype=np.int32),
                ),
                appended_support_group_by_row=(0, 0),
                defer_final_assembly=True,
            )
        )
        full = fem_petsc.assemble_matrix(compiled, bcs=[])
        full.assemble()
        full_dense_matrix = full.convert("dense")
        full_dense = full_dense_matrix.getDenseArray().copy()
        reference = build_variable_p_condensed_trace_system(
            entity_map,
            [full_dense],
            tensor_class_keys=("standard-p6-global",),
            periodic_constraints=constraints,
        )
        try:
            support = constraints.owned_cells[0].independent_rows
            for auxiliary in range(
                candidate.active_trace_rows,
                candidate.active_trace_rows + candidate.appended_rows,
            ):
                candidate.matrix.setValues(
                    np.asarray(support, dtype=PETSc.IntType),
                    np.asarray([auxiliary], dtype=PETSc.IntType),
                    np.ones(
                        (len(support), 1),
                        dtype=PETSc.ScalarType,
                    ),
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
                candidate.matrix.setValues(
                    np.asarray([auxiliary], dtype=PETSc.IntType),
                    np.asarray(support, dtype=PETSc.IntType),
                    np.ones(
                        (1, len(support)),
                        dtype=PETSc.ScalarType,
                    ),
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
                candidate.matrix.setValue(
                    auxiliary,
                    auxiliary,
                    PETSc.ScalarType(1.0),
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
            candidate.matrix.assemble()
            rows = np.arange(
                candidate.active_trace_rows,
                dtype=PETSc.IntType,
            )
            np.testing.assert_allclose(
                candidate.matrix.getValues(rows, rows),
                reference.matrix.getValues(rows, rows),
                rtol=2.0e-12,
                atol=2.0e-11,
            )
            info = candidate.matrix.getInfo(
                PETSc.Mat.InfoType.GLOBAL_SUM
            )
            self.assertEqual(info["mallocs"], 0.0)
            self.assertEqual(
                int(round(info["nz_used"])),
                candidate.build_audit["matrix_nnz_preallocated"],
            )
            self.assertTrue(
                candidate.build_audit["compiled_p6_tensor_builder"]
            )
            self.assertEqual(
                candidate.build_audit[
                    "raw_tensor_class_count_global_unique"
                ],
                1,
            )
            self.assertTrue(
                candidate.build_audit["final_assembly_deferred"]
            )
            self.assertFalse(
                candidate.build_audit[
                    "full_p6_global_matrix_constructed"
                ]
            )
        finally:
            reference.destroy()
            full_dense_matrix.destroy()
            full.destroy()
            candidate.destroy()


if __name__ == "__main__":
    unittest.main()
