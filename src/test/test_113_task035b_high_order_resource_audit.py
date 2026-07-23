from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from basix.ufl import element
from petsc4py import PETSc

from dolfinx import default_real_type, fem

from src.adaptivity.high_order_resource_audit import (
    hcurl_entity_dof_inventory,
    matrix_factor_resource_audit,
    partition_independent_linear_mesh_identity,
)
from src.common.config_3d import target_stage4_config
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.solvers.common_3d_solve import _petsc_matrix_stats
from src.solvers.hcurl_cell_static_condensation import (
    owned_hcurl_cell_interior_dofs,
)


class Task035bHighOrderResourceAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cfg = replace(
            target_stage4_config(degree=4, h_nm=10.0),
            mesh_cell_type="hexahedron",
            unique_output=False,
        )
        cls.mesh_data = build_airbox_mesh_3d(
            cls.cfg,
            Path(tempfile.mkdtemp(prefix="task035b_resource_audit_")),
        )

    def _space(self, degree: int):
        return fem.functionspace(
            self.mesh_data.mesh,
            element(
                "N1curl",
                self.mesh_data.mesh.basix_cell(),
                degree,
                dtype=default_real_type,
            ),
        )

    def test_actual_h10_mesh_identity_and_p4_p5_p6_entity_inventory(self) -> None:
        identity = partition_independent_linear_mesh_identity(self.mesh_data)
        self.assertEqual(identity["global_cell_count"], 252)
        self.assertEqual(identity["mesh_cells_resolved"], [6, 3, 14])
        self.assertTrue(identity["material_plane_alignment"]["all_aligned"])
        expected = {
            4: (4268, 21600, 27216, 53084, 25948),
            5: (5335, 36000, 60480, 101815, 41415),
            6: (6402, 54000, 113400, 173802, 60482),
        }
        for degree, values in expected.items():
            with self.subTest(degree=degree):
                V = self._space(degree)
                raw = int(V.dofmap.index_map.size_global)
                audit = hcurl_entity_dof_inventory(
                    V,
                    num_auxiliary_dofs=80,
                    floquet_num_constraints=None,
                    active_matrix_rows=raw + 80,
                )
                contributions = audit["global_dof_contributions"]
                self.assertEqual(
                    (
                        contributions["edge"],
                        contributions["face_interior"],
                        contributions["cell_interior"],
                        audit["actual_nedelec_dofs"],
                        audit["theoretical_static_condensed_augmented_rows"],
                    ),
                    values,
                )
                self.assertTrue(audit["pass"])
                self.assertIn(
                    "derived_not_measured",
                    audit["static_condensation_projection_semantics"],
                )
                owned_interiors = owned_hcurl_cell_interior_dofs(V)
                self.assertEqual(
                    sum(len(values) for values in owned_interiors),
                    self.mesh_data.mesh.topology.index_map(3).size_local
                    * audit["entity_dofs_per_entity"]["cell_interior"],
                )
                local_flat = [
                    int(value)
                    for cell_values in owned_interiors
                    for value in cell_values
                ]
                self.assertEqual(len(local_flat), len(set(local_flat)))

    def test_matrix_maximum_row_width_and_factor_fill_are_explicit(self) -> None:
        A = PETSc.Mat().createAIJ([3, 3], comm=PETSc.COMM_SELF)
        A.setValues([0], [0, 1], [1.0, 2.0])
        A.setValues([1], [0, 1, 2], [3.0, 4.0, 5.0])
        A.setValue(2, 2, 6.0)
        stats = _petsc_matrix_stats(A)
        self.assertEqual(stats["matrix_maximum_nnz_per_row"], 3)
        self.assertEqual(stats["matrix_nnz_used"], 6.0)
        summary = {
            "matrix_stats": stats,
            "stage4_dtn_factor_inventory": {
                "available": True,
                "factor_solver_type": "fixture",
                "matrix_stats": {
                    "matrix_nnz_used": 12.0,
                    "matrix_average_nnz_per_row": 4.0,
                    "matrix_maximum_nnz_per_row": 5,
                },
            },
        }
        audit = matrix_factor_resource_audit(summary)
        self.assertEqual(audit["matrix_maximum_row_width"], 3)
        self.assertEqual(audit["factor_maximum_row_width"], 5)
        self.assertEqual(audit["factor_fill_ratio"], 2.0)
        A.destroy()


if __name__ == "__main__":
    unittest.main()
