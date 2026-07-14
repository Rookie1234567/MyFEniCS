from __future__ import annotations

import unittest

import numpy as np
from basix.ufl import element
from dolfinx import default_real_type, fem
from mpi4py import MPI

from src.common.config_3d import target_stage4_config
from src.geometry.mesh_builder_3d import _structured_hexa_mesh, stage4_axis_plan
from src.solvers.hybrid_local_dtn import assemble_hybrid_local_dtn_system


class Task032HybridLocalDtnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = target_stage4_config(degree=2, h_nm=10.0)
        cls.bottom = assemble_hybrid_local_dtn_system(cls.cfg, "bottom")
        cls.top = assemble_hybrid_local_dtn_system(cls.cfg, "top")
        plan = stage4_axis_plan(cls.cfg, MPI.COMM_WORLD.size)
        full_mesh = _structured_hexa_mesh(
            MPI.COMM_WORLD, plan.x_values, plan.y_values, plan.z_values
        )
        full_space = fem.functionspace(
            full_mesh,
            element(
                "N1curl",
                full_mesh.basix_cell(),
                2,
                dtype=default_real_type,
            ),
        )
        cls.full_fe_dofs = int(
            full_space.dofmap.index_map.size_global
            * full_space.dofmap.index_map_bs
        )

    @classmethod
    def tearDownClass(cls):
        for system in (cls.bottom, cls.top):
            system.A.destroy()
            system.b.destroy()

    def test_each_terminal_keeps_exactly_one_external_port(self):
        for system in (self.bottom, self.top):
            self.assertEqual(system.n_external_aux, 40)
            self.assertEqual(system.global_size, system.A.getSize()[0])
            self.assertEqual(system.A.getSize(), (system.global_size, system.global_size))
            self.assertTrue(all(mode.side == system.side for mode in system.external_modes))
            self.assertEqual(
                system.coupling_stats["external_facet_tag"],
                system.local_mesh.external_facet_tag,
            )
            self.assertEqual(
                system.coupling_stats["internal_interface_facet_tag"],
                system.local_mesh.interface_facet_tag,
            )
            self.assertFalse(
                system.coupling_stats["internal_interface_dtn_coupling_inserted"]
            )
            self.assertFalse(system.coupling_stats["dtn_auxiliary_block_is_dense"])
            self.assertGreater(
                system.coupling_stats["external_traction_rows_total"], 0
            )
            self.assertGreater(
                system.coupling_stats["external_projection_cols_total"], 0
            )

    def test_auxiliary_diagonal_is_identity_on_every_owner(self):
        for system in (self.bottom, self.top):
            diagonal = system.A.getDiagonal()
            try:
                start, end = diagonal.getOwnershipRange()
                values = np.asarray(diagonal.getArray(readonly=True))
                first = max(system.n_fe, start)
                local_error = 0.0
                if first < end:
                    local_error = float(
                        np.max(np.abs(values[first - start : end - start] - 1.0))
                    )
                error = MPI.COMM_WORLD.allreduce(local_error, op=MPI.MAX)
                self.assertLess(error, 1.0e-14)
            finally:
                diagonal.destroy()

    def test_only_top_terminal_contains_the_incident_source(self):
        bottom_norm = float(self.bottom.b.norm())
        top_norm = float(self.top.b.norm())
        self.assertLess(bottom_norm, 1.0e-30)
        self.assertGreater(top_norm, 0.0)
        self.assertTrue(np.allclose(self.bottom.incident_projections, 0.0))
        self.assertGreater(
            int(np.count_nonzero(np.abs(self.top.incident_projections) > 0.0)), 0
        )

    def test_terminal_fe_sizes_remove_the_middle_volume(self):
        self.assertLess(self.bottom.n_fe + self.top.n_fe, self.full_fe_dofs)
        self.assertEqual(
            self.bottom.n_external_aux + self.top.n_external_aux,
            80,
        )


if __name__ == "__main__":
    unittest.main()
