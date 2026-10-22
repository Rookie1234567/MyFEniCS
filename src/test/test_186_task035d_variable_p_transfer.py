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
    extract_active_full_from_p6_field,
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
    def test_parent_p4_field_primal_transfers_to_candidate_p5_and_recovers(self) -> None:
        if MPI.COMM_WORLD.size != 1:
            self.skipTest("parent-to-candidate primal extraction is serial-only")
        msh = mesh.create_unit_cube(
            MPI.COMM_WORLD,
            2,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
            ghost_mode=mesh.GhostMode.shared_facet,
        )
        parent_map = build_variable_p_global_entity_map(
            msh,
            edge_degrees=_degree_array(msh, 1, 4),
            face_degrees=_degree_array(msh, 2, 4),
            cell_degrees=_degree_array(msh, 3, 4),
        )
        candidate_map = build_variable_p_global_entity_map(
            msh,
            edge_degrees=_degree_array(msh, 1, 5),
            face_degrees=_degree_array(msh, 2, 5),
            cell_degrees=_degree_array(msh, 3, 5),
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
        parent_transfer = build_variable_p_global_transfer(
            parent_map,
            p6_space,
        )
        candidate_transfer = build_variable_p_global_transfer(
            candidate_map,
            p6_space,
        )
        parent_rows = np.arange(parent_map.active_rows, dtype=np.float64)
        parent_active = np.sin(0.011 * parent_rows) + 1j * np.cos(
            0.017 * parent_rows
        )
        parent_field, _parent_recovery = recover_active_full_to_p6_field(
            parent_transfer,
            parent_active,
        )

        candidate_active, extraction = extract_active_full_from_p6_field(
            candidate_transfer,
            parent_field,
        )
        candidate_field, recovery = recover_active_full_to_p6_field(
            candidate_transfer,
            candidate_active,
        )
        self.assertTrue(extraction["pass"])
        self.assertEqual(extraction["unique_cell_degree_maps"], 1)
        self.assertLessEqual(
            extraction["maximum_shared_active_row_relative_error"],
            5.0e-10,
        )
        self.assertTrue(recovery["pass"])
        old_values = np.asarray(parent_field.x.array, dtype=np.complex128)
        new_values = np.asarray(candidate_field.x.array, dtype=np.complex128)
        relative_error = float(
            np.max(np.abs(old_values - new_values), initial=0.0)
            / max(1.0, float(np.max(np.abs(old_values), initial=0.0)))
        )
        self.assertLessEqual(relative_error, 5.0e-10)

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
