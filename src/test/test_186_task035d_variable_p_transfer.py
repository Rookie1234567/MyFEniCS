from __future__ import annotations

import unittest

import numpy as np
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.adaptivity.variable_p_entity_map import (
    build_variable_p_global_entity_map,
)
from src.adaptivity.variable_p_transfer import (
    build_variable_p_global_transfer,
    project_p6_dual_to_active_full,
    recover_active_full_to_p6_field,
)


def _degree_array(msh, dimension: int, degree: int) -> np.ndarray:
    msh.topology.create_entities(dimension)
    index_map = msh.topology.index_map(dimension)
    return np.full(
        int(index_map.size_local + index_map.num_ghosts),
        int(degree),
        dtype=np.int32,
    )


class Task035dVariablePTransferTests(unittest.TestCase):
    def test_matrix_free_transfer_is_conforming_and_adjoint(self) -> None:
        if MPI.COMM_WORLD.size not in {1, 2}:
            self.skipTest("Task035d A4 qualifies serial and MPI2")
        msh = mesh.create_unit_cube(
            MPI.COMM_WORLD,
            2,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
            ghost_mode=mesh.GhostMode.shared_facet,
        )
        entity_map = build_variable_p_global_entity_map(
            msh,
            edge_degrees=_degree_array(msh, 1, 4),
            face_degrees=_degree_array(msh, 2, 5),
            cell_degrees=_degree_array(msh, 3, 6),
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
            entity_map,
            p6_space,
        )
        self.assertTrue(transfer.audit["pass"])
        self.assertEqual(
            transfer.audit["p6_global_rows"],
            entity_map.uniform_p6_rows,
        )
        self.assertEqual(
            transfer.audit["active_global_rows"],
            entity_map.active_rows,
        )
        self.assertTrue(transfer.audit["designation_is_one_to_one"])
        self.assertTrue(
            transfer.audit[
                "entity_blocks_never_split_between_designating_cells"
            ]
        )
        self.assertFalse(
            transfer.audit["global_embedding_matrix_allocated"]
        )

        global_rows = np.arange(entity_map.active_rows, dtype=np.float64)
        active_values = (
            np.sin(0.013 * global_rows)
            + 1j * np.cos(0.017 * global_rows)
        )
        recovered, recovery_audit = recover_active_full_to_p6_field(
            transfer,
            active_values,
        )
        self.assertTrue(recovery_audit["pass"])
        self.assertLessEqual(
            recovery_audit["relative_shared_coefficient_error_max"],
            5.0e-10,
        )

        dual = fem.Function(p6_space)
        p6_index_map = p6_space.dofmap.index_map
        owned_p6 = int(p6_index_map.size_local)
        owned_global = np.asarray(
            p6_index_map.local_to_global(
                np.arange(owned_p6, dtype=np.int32)
            ),
            dtype=np.float64,
        )
        dual.x.array[:owned_p6] = (
            np.cos(0.019 * owned_global)
            + 1j * np.sin(0.023 * owned_global)
        )
        dual.x.scatter_forward()
        projected = project_p6_dual_to_active_full(
            transfer,
            dual.x.petsc_vec,
        )
        active_vector = PETSc.Vec().createMPI(
            (
                transfer.active_counts[MPI.COMM_WORLD.rank],
                entity_map.active_rows,
            ),
            comm=MPI.COMM_WORLD,
        )
        start, end = active_vector.getOwnershipRange()
        active_vector.getArray()[:] = active_values[start:end]
        active_vector.assemble()
        try:
            left = complex(
                dual.x.petsc_vec.dot(recovered.x.petsc_vec)
            )
            right = complex(projected.dot(active_vector))
            relative = abs(left - right) / max(abs(left), abs(right), 1.0)
            self.assertLessEqual(relative, 2.0e-11)
        finally:
            active_vector.destroy()
            projected.destroy()


if __name__ == "__main__":
    unittest.main()
