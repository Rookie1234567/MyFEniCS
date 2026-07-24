from __future__ import annotations

import unittest

import basix
import numpy as np
import ufl
from mpi4py import MPI

from dolfinx import fem, mesh

from src.adaptivity.hcurl_regionwise_p import (
    create_reduced_trace_hcurl_element,
    reduced_trace_hcurl_ufl_element,
    regionwise_interior_p_dof_budget,
)
from src.common.config_3d import SimulationConfig3D
from src.solvers.common_3d_solve import _create_nedelec_space


class Task035bRegionwisePTests(unittest.TestCase):
    def test_p4_trace_p6_interior_custom_element_contains_p4(self) -> None:
        reduced = create_reduced_trace_hcurl_element(4, 6)
        audit = reduced.audit
        self.assertTrue(audit["pass"])
        self.assertEqual(audit["custom_dimension"], 642)
        self.assertEqual(audit["trace_dimension"], 192)
        self.assertEqual(audit["low_interior_dimension"], 108)
        self.assertEqual(audit["high_interior_dimension"], 450)
        self.assertEqual(audit["low_space_embedding_rank"], 300)
        self.assertEqual(audit["low_interior_embedding_rank"], 108)
        self.assertLess(audit["low_interior_trace_leakage_max"], 1.0e-11)
        self.assertEqual(
            audit["entity_dofs"],
            [
                [0] * 8,
                [4] * 12,
                [24] * 6,
                [450],
            ],
        )

        standard_p4 = basix.ufl.element(
            "N1curl", "hexahedron", 4
        ).basix_element
        points = np.asarray(
            (
                (0.13, 0.22, 0.31),
                (0.61, 0.47, 0.72),
                (0.89, 0.18, 0.54),
            ),
            dtype=np.float64,
        )
        rng = np.random.default_rng(20260724)
        coefficients = rng.standard_normal(standard_p4.dim)
        reduced_coefficients = reduced.low_to_reduced @ coefficients
        p4_values = np.einsum(
            "qiv,i->qv",
            standard_p4.tabulate(0, points)[0],
            coefficients,
        )
        reduced_values = np.einsum(
            "qiv,i->qv",
            reduced.element.tabulate(0, points)[0],
            reduced_coefficients,
        )
        np.testing.assert_allclose(
            reduced_values,
            p4_values,
            rtol=2.0e-12,
            atol=2.0e-12,
        )

    def test_two_cell_space_has_one_shared_conforming_p4_trace(self) -> None:
        comm = MPI.COMM_WORLD
        msh = mesh.create_box(
            comm,
            ((0.0, 0.0, 0.0), (2.0, 1.0, 1.0)),
            (2, 1, 1),
            cell_type=mesh.CellType.hexahedron,
        )
        reduced_element = reduced_trace_hcurl_ufl_element(4, 6)
        space = fem.functionspace(msh, reduced_element)
        standard_p6 = fem.functionspace(
            msh,
            basix.ufl.element("N1curl", "hexahedron", 6),
        )
        for dimension in (1, 2):
            msh.topology.create_entities(dimension)
        edges = int(msh.topology.index_map(1).size_global)
        faces = int(msh.topology.index_map(2).size_global)
        cells = int(msh.topology.index_map(3).size_global)
        expected = edges * 4 + faces * 24 + cells * 450
        actual = int(space.dofmap.index_map.size_global)
        self.assertEqual(actual, expected)
        self.assertEqual(cells, 2)
        self.assertEqual(actual, 1244)
        self.assertLess(actual, int(standard_p6.dofmap.index_map.size_global))
        self.assertEqual(
            2 * 642 - actual,
            4 * 4 + 24,
            "the two cells must share exactly one p4 face trace",
        )

        field = fem.Function(space)
        field.interpolate(
            lambda x: np.vstack(
                (
                    x[1] ** 2 + x[2],
                    x[0] * x[2],
                    x[0] ** 2 - x[1],
                )
            )
        )
        coordinate = ufl.SpatialCoordinate(msh)
        exact = ufl.as_vector(
            (
                coordinate[1] ** 2 + coordinate[2],
                coordinate[0] * coordinate[2],
                coordinate[0] ** 2 - coordinate[1],
            )
        )
        local_error = fem.assemble_scalar(
            fem.form(ufl.inner(field - exact, field - exact) * ufl.dx)
        )
        error = float(comm.allreduce(float(np.real(local_error)), op=MPI.SUM))
        self.assertLess(error, 1.0e-20)

    def test_config_opt_in_creates_reduced_trace_space(self) -> None:
        cfg = SimulationConfig3D(
            nedelec_degree=6,
            nedelec_trace_degree=4,
            nedelec_interior_degree=6,
        )
        self.assertTrue(cfg.nedelec_reduced_trace_enabled)
        self.assertEqual(cfg.nedelec_trace_degree_resolved, 4)
        self.assertEqual(cfg.nedelec_interior_degree_resolved, 6)
        snapshot = cfg.as_jsonable()
        self.assertEqual(snapshot["nedelec_trace_degree_resolved"], 4)
        self.assertEqual(snapshot["nedelec_interior_degree_resolved"], 6)
        self.assertTrue(snapshot["nedelec_reduced_trace_enabled"])

        msh = mesh.create_box(
            MPI.COMM_WORLD,
            ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)),
            (1, 1, 1),
            cell_type=mesh.CellType.hexahedron,
        )
        space = _create_nedelec_space(msh, cfg)
        self.assertEqual(space.element.space_dimension, 642)
        self.assertEqual(
            [len(dofs) for dofs in space.element.basix_element.entity_dofs[1]],
            [4] * 12,
        )
        self.assertEqual(
            [len(dofs) for dofs in space.element.basix_element.entity_dofs[2]],
            [24] * 6,
        )

    def test_classifier_lane_hits_task035b_90k_active_dof_gate(self) -> None:
        budget = regionwise_interior_p_dof_budget(
            global_edges=1067,
            global_faces=900,
            global_cells=252,
            high_interior_cells=105,
            trace_degree=4,
            low_interior_degree=4,
            high_interior_degree=6,
        )
        self.assertTrue(budget["pass"])
        self.assertEqual(budget["active_trace_dofs"], 25868)
        self.assertEqual(budget["active_cell_interior_dofs"], 63126)
        self.assertEqual(budget["active_full3d_equivalent_dofs"], 88994)
        self.assertFalse(budget["inactive_max_p_rows_retained_in_matrix"])


if __name__ == "__main__":
    unittest.main()
