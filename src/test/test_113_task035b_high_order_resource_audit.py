from __future__ import annotations

from dataclasses import replace
import json
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

ROOT = Path(__file__).resolve().parents[2]


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

    def test_p6_periodic_independent_trace_inventory_is_physical(self) -> None:
        V = self._space(6)
        audit = hcurl_entity_dof_inventory(
            V,
            num_auxiliary_dofs=80,
            floquet_num_constraints=9210,
            active_matrix_rows=51272,
            cell_static_condensation=True,
            floquet_slave_elimination=True,
        )
        self.assertTrue(audit["pass"])
        self.assertEqual(
            audit["theoretical_static_condensed_augmented_rows"],
            60482,
        )
        self.assertEqual(
            audit[
                "theoretical_static_condensed_periodic_independent_rows"
            ],
            51272,
        )
        self.assertTrue(audit["cell_static_condensation_active"])
        self.assertTrue(audit["floquet_slave_elimination_active"])
        self.assertIn(
            "Floquet-slave elimination",
            audit["static_condensation_projection_semantics"],
        )

    def test_formal_mpi8_p6_condensation_record_is_full_system_qualified(
        self,
    ) -> None:
        records = (
            ROOT
            / "benchmarks/cases/095_high_order_local_hp_resource_envelope"
            / "records"
        )
        control = json.loads(
            (records / "global_hexa_p5_p6_h10_mpi8.json").read_text(
                encoding="utf-8"
            )
        )
        condensed = json.loads(
            (
                records
                / "global_hexa_p5_p6_h10_p6_condensed_mpi8.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(condensed["status"], "actual_global_r5_pass")
        self.assertTrue(condensed["qualification"]["pass"])
        self.assertEqual(
            condensed["source"]["commit_sha"],
            "0f4b786d618c37e1c572a4f596a9235e53d73161",
        )
        self.assertTrue(condensed["source"]["stable_and_clean_after"])
        p6 = condensed["enriched"]
        p6_control = control["enriched"]
        self.assertEqual(p6["mpi_size"], 8)
        self.assertEqual(p6["num_nedelec_dofs"], 173802)
        self.assertEqual(p6["matrix_stats"]["matrix_rows"], 60482)
        self.assertEqual(p6["matrix_stats"]["matrix_nnz_used"], 52058162.0)
        self.assertLessEqual(p6["linear_system_relative_residual"], 1.0e-9)
        self.assertTrue(p6["stage4_cell_static_condensation"])
        audit = p6["cell_static_condensation"]
        self.assertEqual(audit["full_rows"], 173882)
        self.assertEqual(audit["interior_rows"], 113400)
        self.assertEqual(audit["trace_rows"], 60482)
        self.assertFalse(audit["all_cell_dense_factor_cache_retained"])
        self.assertLessEqual(
            audit["full_explicit_true_residual"][
                "linear_system_relative_residual"
            ],
            1.0e-9,
        )
        for observable in ("R_total", "T_total", "A_volume_total"):
            self.assertLess(
                abs(p6[observable] - p6_control[observable]),
                1.0e-12,
                observable,
            )
        self.assertLess(
            condensed["resource_authority"]["memory_authority_gib"],
            control["resource_authority"]["memory_authority_gib"],
        )


if __name__ == "__main__":
    unittest.main()
