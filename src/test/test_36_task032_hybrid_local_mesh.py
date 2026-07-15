from __future__ import annotations

import unittest

import numpy as np
from basix.ufl import element
from dolfinx import default_real_type, fem
from mpi4py import MPI

from src.common.config_3d import target_stage4_config
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.hybrid_local_mesh import build_hybrid_local_mesh
from src.geometry.mesh_builder_3d import _structured_hexa_mesh, stage4_axis_plan


class Task032HybridLocalMeshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = target_stage4_config(degree=2, h_nm=5.0)
        cls.plan = stage4_axis_plan(cls.cfg, MPI.COMM_WORLD.size)

    def test_terminal_meshes_remove_the_middle_volume_and_match_interfaces(self):
        bottom = build_hybrid_local_mesh(self.cfg, "bottom")
        top = build_hybrid_local_mesh(self.cfg, "top")
        nx = len(self.plan.x_values) - 1
        ny = len(self.plan.y_values) - 1
        full_nz = len(self.plan.z_values) - 1
        local_nz = bottom.mesh_cells[2] + top.mesh_cells[2]
        expected_interface_facets = nx * ny

        np.testing.assert_allclose(bottom.z_values[[0, -1]], [-10.0, 10.0])
        np.testing.assert_allclose(top.z_values[[0, -1]], [110.0, 130.0])
        self.assertEqual(bottom.global_interface_facet_count, expected_interface_facets)
        self.assertEqual(top.global_interface_facet_count, expected_interface_facets)
        self.assertEqual(bottom.global_external_facet_count, expected_interface_facets)
        self.assertEqual(top.global_external_facet_count, expected_interface_facets)
        self.assertLess(local_nz, full_nz)
        self.assertEqual(
            full_nz - local_nz,
            int(np.count_nonzero((self.plan.z_values[:-1] >= 10.0) & (self.plan.z_values[1:] <= 110.0))),
        )
        self.assertEqual(bottom.local_interface_outward_normal_sign, +1)
        self.assertEqual(top.local_interface_outward_normal_sign, -1)
        self.assertEqual(
            bottom.local_interface_outward_normal_sign,
            -bottom.modal_interface_outward_normal_sign,
        )
        self.assertEqual(
            top.local_interface_outward_normal_sign,
            -top.modal_interface_outward_normal_sign,
        )
        self.assertFalse(bottom.full_mesh_or_field_gathered)
        self.assertFalse(top.full_mesh_or_field_gathered)

    def test_local_p2_spaces_are_smaller_and_keep_double_floquet_constraints(self):
        local_dofs = []
        constraints = []
        for side in ("bottom", "top"):
            local = build_hybrid_local_mesh(self.cfg, side)
            V = fem.functionspace(
                local.mesh,
                element(
                    "N1curl",
                    local.mesh.basix_cell(),
                    2,
                    dtype=default_real_type,
                ),
            )
            floquet = build_double_floquet_mpc(V, local.mesh_data, self.cfg)
            local_dofs.append(
                int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs)
            )
            constraints.append(floquet)

        full_mesh = _structured_hexa_mesh(
            MPI.COMM_WORLD,
            self.plan.x_values,
            self.plan.y_values,
            self.plan.z_values,
        )
        full_space = fem.functionspace(
            full_mesh,
            element(
                "N1curl", full_mesh.basix_cell(), 2, dtype=default_real_type
            ),
        )
        full_dofs = int(
            full_space.dofmap.index_map.size_global
            * full_space.dofmap.index_map_bs
        )
        self.assertLess(sum(local_dofs), full_dofs)
        for floquet in constraints:
            self.assertGreater(floquet.num_constraints, 0)
            self.assertEqual(floquet.constraint_mode_resolved, "topological_trace_p2")
            self.assertLess(
                abs(floquet.phase_x - self.cfg.floquet_phase_x), 1.0e-12
            )
            self.assertLess(
                abs(floquet.phase_y - self.cfg.floquet_phase_y), 1.0e-12
            )
            self.assertEqual(floquet.max_masters_per_slave, 1)

    def test_material_tags_cover_expected_terminal_materials(self):
        bottom = build_hybrid_local_mesh(self.cfg, "bottom")
        top = build_hybrid_local_mesh(self.cfg, "top")

        def global_count(local, tag):
            count = len(local.mesh_data.cell_tags.find(tag))
            return int(MPI.COMM_WORLD.allreduce(count, op=MPI.SUM))

        self.assertGreater(global_count(bottom, self.cfg.tags.substrate), 0)
        self.assertGreater(global_count(bottom, self.cfg.tags.grating), 0)
        self.assertGreater(global_count(top, self.cfg.tags.grating), 0)
        self.assertGreater(global_count(top, self.cfg.tags.air), 0)
        self.assertEqual(global_count(top, self.cfg.tags.substrate), 0)

    def test_h3_inserts_the_frozen_exact_interface_planes(self):
        cfg = target_stage4_config(degree=2, h_nm=3.0)
        plan = stage4_axis_plan(cfg, MPI.COMM_WORLD.size)
        self.assertFalse(np.any(np.isclose(plan.z_values, 10.0)))
        self.assertFalse(np.any(np.isclose(plan.z_values, 110.0)))
        bottom = build_hybrid_local_mesh(cfg, "bottom")
        top = build_hybrid_local_mesh(cfg, "top")
        self.assertAlmostEqual(bottom.interface_z_nm, 10.0)
        self.assertAlmostEqual(top.interface_z_nm, 110.0)
        self.assertAlmostEqual(bottom.z_values[-1], 10.0)
        self.assertAlmostEqual(top.z_values[0], 110.0)
        self.assertLess(bottom.z_values[-2], 10.0)
        self.assertGreater(top.z_values[1], 110.0)


if __name__ == "__main__":
    unittest.main()
