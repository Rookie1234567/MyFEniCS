from __future__ import annotations

import unittest
from dataclasses import replace

from src.common.config import SimulationConfig
from src.geometry.mesh_builder import material_tag_for_rect_2d, mesh_axis_coordinates_2d
from src.main import EUV_GRATING_2D, _pycharm_args_2d
from src.postprocessing.near_field_2d import near_field_reference_areas_2d, near_field_regions_2d


class Test2DEUVInputsAndMesh(unittest.TestCase):
    def test_euv_dataclass_is_translated_to_runner_args(self):
        args = _pycharm_args_2d()
        joined = " ".join(args)

        self.assertIn("--period-x 100.0", joined)
        self.assertIn("--lambda0 13.5", joined)
        self.assertIn("--n-substrate 1.1", joined)
        self.assertIn("--n-grating 1.2", joined)
        self.assertIn("--port-boundary-model dtn", joined)
        self.assertIn("--port-dtn-assembly auxiliary", joined)
        self.assertIn("--lock-near-field-template", args)
        self.assertEqual(EUV_GRATING_2D.polarization_type, "TM")

    def test_locked_near_mesh_keeps_template_planes_when_layers_are_thicker(self):
        cfg = SimulationConfig(
            period_x=100.0,
            air_height=150.0,
            substrate_thickness=100.0,
            grating_width=50.0,
            grating_height=50.0,
            mesh_lock_near_field_template=True,
        )
        x_coords, y_coords = mesh_axis_coordinates_2d(cfg)

        self.assertIn(-50.0, x_coords)
        self.assertIn(-25.0, x_coords)
        self.assertIn(25.0, x_coords)
        self.assertIn(50.0, x_coords)
        self.assertIn(-50.0, y_coords)
        self.assertIn(0.0, y_coords)
        self.assertIn(50.0, y_coords)
        self.assertIn(100.0, y_coords)

    def test_material_tag_uses_exact_subrectangles_not_midpoint_guess(self):
        cfg = SimulationConfig(
            period_x=100.0,
            air_height=100.0,
            substrate_thickness=50.0,
            grating_width=50.0,
            grating_height=50.0,
        )

        self.assertEqual(material_tag_for_rect_2d(cfg, -25.0, 25.0, 0.0, 50.0), cfg.tags.grating)
        self.assertEqual(material_tag_for_rect_2d(cfg, -50.0, -25.0, 0.0, 50.0), cfg.tags.air)
        self.assertEqual(material_tag_for_rect_2d(cfg, -50.0, 50.0, -50.0, 0.0), cfg.tags.substrate)

    def test_near_field_reference_areas_match_euv_definition(self):
        cfg = SimulationConfig(
            period_x=100.0,
            air_height=100.0,
            substrate_thickness=50.0,
            grating_width=50.0,
            grating_height=50.0,
            near_field_margin_x=25.0,
            near_field_air_top=100.0,
            near_field_sub_depth=50.0,
        )
        regions = near_field_regions_2d(cfg)
        areas = near_field_reference_areas_2d(cfg)

        self.assertEqual(regions["air_near"]["x_min"], -50.0)
        self.assertEqual(regions["air_near"]["x_max"], 50.0)
        self.assertAlmostEqual(areas["grating"], 2500.0)
        self.assertAlmostEqual(areas["air_near"], 7500.0)
        self.assertAlmostEqual(areas["sub_near"], 5000.0)

    def test_near_field_air_region_is_clipped_when_air_is_shorter_than_template(self):
        cfg = replace(
            SimulationConfig(
                period_x=100.0,
                air_height=60.0,
                substrate_thickness=50.0,
                grating_width=50.0,
                grating_height=50.0,
            ),
            mesh_lock_near_field_template=True,
        )
        regions = near_field_regions_2d(cfg)
        areas = near_field_reference_areas_2d(cfg)

        self.assertEqual(regions["air_near"]["y_max"], 60.0)
        self.assertAlmostEqual(areas["air_near"], 3500.0)


if __name__ == "__main__":
    unittest.main()
