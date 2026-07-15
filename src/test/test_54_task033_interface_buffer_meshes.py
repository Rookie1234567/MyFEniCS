from __future__ import annotations

import unittest

import numpy as np
from basix.ufl import element
from dolfinx import default_real_type, fem

from src.common.config_3d import target_stage4_config
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.hybrid_local_mesh import build_hybrid_local_mesh


class Task033InterfaceBufferMeshTests(unittest.TestCase):
    def test_symmetric_buffer_candidates_keep_matching_periodic_interfaces(self) -> None:
        cfg = target_stage4_config(degree=2, h_nm=5.0)
        previous_local_cells = None
        for buffer_nm in (10.0, 7.5, 5.0, 2.5):
            with self.subTest(buffer_nm=buffer_nm):
                bottom = build_hybrid_local_mesh(
                    cfg,
                    "bottom",
                    bottom_interface_z_nm=buffer_nm,
                    top_interface_z_nm=120.0 - buffer_nm,
                )
                top = build_hybrid_local_mesh(
                    cfg,
                    "top",
                    bottom_interface_z_nm=buffer_nm,
                    top_interface_z_nm=120.0 - buffer_nm,
                )
                self.assertAlmostEqual(bottom.interface_z_nm, buffer_nm)
                self.assertAlmostEqual(top.interface_z_nm, 120.0 - buffer_nm)
                self.assertAlmostEqual(
                    bottom.interface_z_nm - bottom.external_z_nm,
                    10.0 + buffer_nm,
                )
                self.assertAlmostEqual(
                    top.external_z_nm - top.interface_z_nm,
                    10.0 + buffer_nm,
                )
                self.assertEqual(bottom.mesh_cells[:2], top.mesh_cells[:2])
                self.assertEqual(
                    bottom.global_interface_facet_count,
                    top.global_interface_facet_count,
                )
                np.testing.assert_allclose(
                    bottom.mesh.geometry.x[:, :2].min(axis=0),
                    top.mesh.geometry.x[:, :2].min(axis=0),
                )
                np.testing.assert_allclose(
                    bottom.mesh.geometry.x[:, :2].max(axis=0),
                    top.mesh.geometry.x[:, :2].max(axis=0),
                )
                local_cells = bottom.mesh_cells[2] + top.mesh_cells[2]
                if previous_local_cells is not None:
                    self.assertLessEqual(local_cells, previous_local_cells)
                previous_local_cells = local_cells

    def test_extreme_buffer_keeps_sparse_double_floquet_constraints(self) -> None:
        cfg = target_stage4_config(degree=2, h_nm=5.0)
        for side in ("bottom", "top"):
            with self.subTest(side=side):
                local = build_hybrid_local_mesh(
                    cfg,
                    side,
                    bottom_interface_z_nm=2.5,
                    top_interface_z_nm=117.5,
                )
                space = fem.functionspace(
                    local.mesh,
                    element(
                        "N1curl",
                        local.mesh.basix_cell(),
                        2,
                        dtype=default_real_type,
                    ),
                )
                floquet = build_double_floquet_mpc(
                    space, local.mesh_data, cfg
                )
                self.assertGreater(floquet.num_constraints, 0)
                self.assertEqual(floquet.constraint_mode_resolved, "topological_trace_p2")
                # A reversed p2 edge may use its bounded 2x2 Basix entity
                # transform.  The contract is degree-local sparsity, not an
                # accidental one-master orientation on one particular mesh.
                self.assertLessEqual(floquet.max_masters_per_slave, 2)
                self.assertLessEqual(
                    floquet.raw_map_nnz, 2 * floquet.num_constraints
                )
                self.assertFalse(floquet.used_full_boundary_gather)
                self.assertFalse(floquet.created_dense_boundary_square)


if __name__ == "__main__":
    unittest.main()
