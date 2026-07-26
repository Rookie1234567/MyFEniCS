from __future__ import annotations

import unittest

import numpy as np
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI

from src.adaptivity.variable_p_entity_map import (
    build_variable_p_global_entity_map,
    structural_sparsity_audit,
)
from src.adaptivity.variable_p_periodic_orbits import (
    audit_variable_p_periodic_orbits,
    build_variable_p_periodic_constraint_map,
)


def _degree_array(msh, dimension: int, degree: int) -> np.ndarray:
    msh.topology.create_entities(dimension)
    index_map = msh.topology.index_map(dimension)
    return np.full(
        int(index_map.size_local + index_map.num_ghosts),
        int(degree),
        dtype=np.int32,
    )


def _fixture(nx: int, ny: int, nz: int):
    return mesh.create_unit_cube(
        MPI.COMM_WORLD,
        nx,
        ny,
        nz,
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )


class Task035dGlobalEntityNumberingTests(unittest.TestCase):
    def test_single_cell_and_two_shared_cell_counts(self) -> None:
        if MPI.COMM_WORLD.size != 1:
            self.skipTest("serial topology-count fixture")
        expected = {
            (1, 1, 1): {
                "entities": {"1": 12, "2": 6, "3": 1},
                "active": 738,
                "trace": 288,
                "p6": 882,
            },
            (2, 1, 1): {
                "entities": {"1": 20, "2": 11, "3": 2},
                "active": 1420,
                "trace": 520,
                "p6": 1680,
            },
        }
        for cells, authority in expected.items():
            with self.subTest(cells=cells):
                msh = _fixture(*cells)
                entity_map = build_variable_p_global_entity_map(
                    msh,
                    edge_degrees=_degree_array(msh, 1, 4),
                    face_degrees=_degree_array(msh, 2, 5),
                    cell_degrees=_degree_array(msh, 3, 6),
                )
                self.assertTrue(entity_map.audit["pass"])
                self.assertEqual(
                    entity_map.audit["global_entity_counts"],
                    authority["entities"],
                )
                self.assertEqual(entity_map.active_rows, authority["active"])
                self.assertEqual(
                    entity_map.active_trace_rows,
                    authority["trace"],
                )
                self.assertEqual(
                    entity_map.uniform_p6_rows,
                    authority["p6"],
                )
                self.assertFalse(
                    entity_map.audit["inactive_modes_globally_numbered"]
                )
                for cell in entity_map.owned_cells:
                    self.assertEqual(len(cell.active_rows), 738)
                    self.assertEqual(len(cell.trace_rows), 288)
                    self.assertEqual(len(cell.interior_rows), 450)

    def test_2x2x2_numbering_and_sparsity_are_mpi_consistent(self) -> None:
        if MPI.COMM_WORLD.size not in {1, 2}:
            self.skipTest("Task035d A4 qualifies serial and MPI2")
        msh = _fixture(2, 2, 2)
        variable = build_variable_p_global_entity_map(
            msh,
            edge_degrees=_degree_array(msh, 1, 4),
            face_degrees=_degree_array(msh, 2, 5),
            cell_degrees=_degree_array(msh, 3, 6),
        )
        control = build_variable_p_global_entity_map(
            msh,
            edge_degrees=_degree_array(msh, 1, 6),
            face_degrees=_degree_array(msh, 2, 6),
            cell_degrees=_degree_array(msh, 3, 6),
        )
        self.assertEqual(
            variable.audit["global_entity_counts"],
            {"1": 54, "2": 36, "3": 8},
        )
        self.assertEqual(variable.active_rows, 5256)
        self.assertEqual(variable.active_trace_rows, 1656)
        self.assertEqual(control.active_rows, 6084)
        self.assertEqual(control.active_trace_rows, 2484)
        self.assertEqual(variable.uniform_p6_rows, control.active_rows)
        self.assertEqual(
            variable.uniform_p6_trace_rows,
            control.active_trace_rows,
        )
        self.assertEqual(variable.audit["inactive_p6_rows"], 828)
        self.assertEqual(variable.audit["inactive_p6_trace_rows"], 828)

        p6_space = fem.functionspace(
            msh,
            element(
                "N1curl",
                msh.basix_cell(),
                6,
                dtype=default_real_type,
            ),
        )
        self.assertEqual(
            int(p6_space.dofmap.index_map.size_global),
            control.active_rows,
        )

        variable_sparsity = structural_sparsity_audit(
            variable,
            condensed_trace=True,
        )
        control_sparsity = structural_sparsity_audit(
            control,
            condensed_trace=True,
        )
        self.assertTrue(variable_sparsity["pass"])
        self.assertTrue(control_sparsity["pass"])
        self.assertEqual(variable_sparsity["rows"], 1656)
        self.assertEqual(control_sparsity["rows"], 2484)
        self.assertLess(
            variable_sparsity["structural_nnz"],
            control_sparsity["structural_nnz"],
        )
        self.assertFalse(
            variable_sparsity["inactive_p6_rows_globally_numbered"]
        )

        identity = variable.audit["canonical_degree_map_sha256"]
        identities = MPI.COMM_WORLD.allgather(identity)
        self.assertEqual(len(set(identities)), 1)
        local_cell_count = len(variable.owned_cells)
        self.assertEqual(
            MPI.COMM_WORLD.allreduce(local_cell_count, op=MPI.SUM),
            8,
        )

        phase_x = np.exp(0.2j)
        phase_y = np.exp(-0.3j)
        periodic_x = audit_variable_p_periodic_orbits(
            variable,
            axes=("x",),
            phase_x=phase_x,
            phase_y=phase_y,
        )
        periodic_y = audit_variable_p_periodic_orbits(
            variable,
            axes=("y",),
            phase_x=phase_x,
            phase_y=phase_y,
        )
        periodic_xy = audit_variable_p_periodic_orbits(
            variable,
            axes=("x", "y"),
            phase_x=phase_x,
            phase_y=phase_y,
        )
        for audit in (periodic_x, periodic_y, periodic_xy):
            self.assertTrue(audit["pass"])
            self.assertLessEqual(
                audit["cycle_closure_error_max"],
                2.0e-11,
            )
            self.assertFalse(
                audit["inactive_p6_rows_globally_numbered"]
            )
        self.assertEqual(periodic_x["relation_count"], 16)
        self.assertEqual(periodic_y["relation_count"], 16)
        self.assertEqual(periodic_x["periodic_slave_rows"], 208)
        self.assertEqual(periodic_y["periodic_slave_rows"], 208)
        self.assertEqual(periodic_xy["relation_count"], 32)
        self.assertEqual(periodic_xy["maximum_orbit_size"], 4)
        self.assertEqual(periodic_xy["periodic_slave_rows"], 408)
        self.assertEqual(
            periodic_xy["independent_periodic_trace_rows"],
            1248,
        )
        constraints = build_variable_p_periodic_constraint_map(
            variable,
            axes=("x", "y"),
            phase_x=phase_x,
            phase_y=phase_y,
        )
        self.assertTrue(constraints.audit["pass"])
        self.assertEqual(constraints.independent_trace_rows, 1248)
        self.assertEqual(constraints.audit["periodic_slave_rows"], 408)
        self.assertFalse(
            constraints.audit["full_global_constraint_matrix_allocated"]
        )
        self.assertFalse(
            constraints.audit["chained_slave_rows_retained"]
        )
        for cell in constraints.owned_cells:
            expansion = cell.full_trace_from_independent
            self.assertEqual(expansion.shape[0], 288)
            self.assertEqual(
                np.linalg.matrix_rank(expansion),
                expansion.shape[1],
            )
        for relation in constraints.relations:
            master = constraints.entity_blocks[
                (relation.dimension, relation.master_entity)
            ]
            slave = constraints.entity_blocks[
                (relation.dimension, relation.slave_entity)
            ]
            np.testing.assert_allclose(
                slave.full_from_independent,
                relation.coefficient_transform
                @ master.full_from_independent,
                rtol=2.0e-12,
                atol=2.0e-12,
            )


if __name__ == "__main__":
    unittest.main()
