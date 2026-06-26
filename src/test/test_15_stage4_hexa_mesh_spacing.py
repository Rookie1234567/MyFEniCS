from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.geometry.mesh_builder_3d import _stage4_axis_plan, build_airbox_mesh_3d
from src.test.stage2_test_utils import stage4_block_config


def _max_spacing_inside(values: np.ndarray, low: float, high: float) -> float:
    widths = np.diff(values)
    mids = 0.5 * (values[:-1] + values[1:])
    selected = widths[(mids >= low) & (mids <= high)]
    if len(selected) == 0:
        raise AssertionError(f"No mesh intervals were found inside [{low}, {high}].")
    return float(np.max(selected))


class Stage4HexaMeshSpacingTests(unittest.TestCase):
    def test_auto_keeps_uniform_when_material_planes_align(self):
        cfg = stage4_block_config(
            use_pml=False,
            pml_top_thickness=0.0,
            pml_bottom_thickness=0.0,
            mesh_target_size=5.0,
            mesh_spacing_mode="auto",
        )
        plan = _stage4_axis_plan(cfg, comm_size=1)

        self.assertEqual(plan.mesh_spacing_mode_resolved, "uniform_strict")
        self.assertTrue(plan.material_plane_alignment["all_aligned"])
        self.assertEqual(plan.mesh_cells_resolved, (20, 20, 30))
        self.assertAlmostEqual(plan.axis_cell_stats["x"]["min"], 5.0)
        self.assertAlmostEqual(plan.axis_cell_stats["x"]["max"], 5.0)

    def test_auto_fits_material_planes_when_target_does_not_align(self):
        cfg = stage4_block_config(
            use_pml=False,
            pml_top_thickness=0.0,
            pml_bottom_thickness=0.0,
            mesh_target_size=6.0,
            mesh_spacing_mode="auto",
        )
        plan = _stage4_axis_plan(cfg, comm_size=1)

        self.assertEqual(plan.mesh_spacing_mode_resolved, "boundary_fitted")
        self.assertTrue(plan.material_plane_alignment["all_aligned"])
        for value in (cfg.grating_x_min, cfg.grating_x_max):
            self.assertTrue(np.any(np.isclose(plan.x_values, value)))
        for value in (cfg.grating_y_min, cfg.grating_y_max):
            self.assertTrue(np.any(np.isclose(plan.y_values, value)))
        for value in (cfg.interface_z, cfg.grating_z_max):
            self.assertTrue(np.any(np.isclose(plan.z_values, value)))

    def test_uniform_strict_still_rejects_nonaligned_material_planes(self):
        cfg = stage4_block_config(
            use_pml=False,
            pml_top_thickness=0.0,
            pml_bottom_thickness=0.0,
            mesh_target_size=6.0,
            mesh_spacing_mode="uniform_strict",
        )

        with self.assertRaisesRegex(ValueError, "uniform_strict"):
            _stage4_axis_plan(cfg, comm_size=1)

    def test_local_refined_uses_small_cells_near_grating_and_coarse_cells_away(self):
        cfg = stage4_block_config(
            use_pml=False,
            pml_top_thickness=0.0,
            pml_bottom_thickness=0.0,
            mesh_target_size=20.0,
            mesh_spacing_mode="local_refined",
            mesh_refined_size=2.5,
            mesh_refinement_radius=5.0,
        )
        plan = _stage4_axis_plan(cfg, comm_size=1)

        self.assertEqual(plan.mesh_spacing_mode_resolved, "local_refined")
        self.assertTrue(plan.material_plane_alignment["all_aligned"])
        x_region = plan.local_refinement_regions["x"][0]
        y_region = plan.local_refinement_regions["y"][0]
        z_region = plan.local_refinement_regions["z"][0]
        self.assertLessEqual(_max_spacing_inside(plan.x_values, *x_region), 2.5 + 1.0e-12)
        self.assertLessEqual(_max_spacing_inside(plan.y_values, *y_region), 2.5 + 1.0e-12)
        self.assertLessEqual(_max_spacing_inside(plan.z_values, *z_region), 2.5 + 1.0e-12)
        self.assertGreaterEqual(plan.axis_cell_stats["x"]["max"], 10.0)

    def test_boundary_fitted_plan_builds_a_dolfinx_hexa_mesh(self):
        cfg = stage4_block_config(
            use_pml=False,
            pml_top_thickness=0.0,
            pml_bottom_thickness=0.0,
            mesh_target_size=30.0,
            mesh_spacing_mode="auto",
        )
        mesh_data = build_airbox_mesh_3d(cfg, Path(tempfile.mkdtemp(prefix="stage4_mesh_spacing_")))

        self.assertEqual(mesh_data.mesh_spacing_mode_resolved, "boundary_fitted")
        self.assertTrue(mesh_data.material_plane_alignment["all_aligned"])
        self.assertEqual(mesh_data.mesh_cell_type_resolved, "hexahedron")
        self.assertIn("hexahedron", str(mesh_data.mesh.basix_cell()).lower())


if __name__ == "__main__":
    unittest.main()
