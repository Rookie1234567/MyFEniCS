"""Lightweight exact-geometry/material inventory tests; no FE qualification."""
import itertools
import math
from pathlib import Path
import tempfile
import unittest

from src.geometry.sixlayer_block import REPRESENTATIVES, cell_material_at, sixlayer_plan
from src.io.sixlayer_input import GENERATOR, build_sixlayer_config, resolve_sixlayer_input
from src.common.material_regions_3d import grating_layers, material_regions


class SixlayerGeometryTests(unittest.TestCase):
    def _input(self, t, extra=""):
        text = (f'model="sixlayer_surrogate_0p7nm"\nsample_id="test"\n'
                f'generator_version="{GENERATOR}"\nthicknesses_nm={list(t)}\n'+extra)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"test.dat"
            path.write_text(text)
            return resolve_sixlayer_input(path)[1]

    def test_all_representatives_complete_interface_volumes(self):
        for t in REPRESENTATIVES.values():
            plan = sixlayer_plan(t)
            self.assertEqual(plan["cell_counts"], (3, 6, 8))
            self.assertEqual(plan["cells"], 144)
            self.assertGreater(plan["minimum_affine_jacobian_determinant"], 0)
            observed = {}
            spans = [list(zip(plan[f"{axis}_values"][:-1],plan[f"{axis}_values"][1:]))
                     for axis in "xyz"]
            for box in itertools.product(*spans):
                mid = [(a+b)/2 for a,b in box]
                name, tag = cell_material_at(*mid,plan)
                observed[name] = observed.get(name,0)+math.prod(b-a for a,b in box)
                self.assertIn(tag,(1,2,21,22,23,24,25,26))
            self.assertEqual(set(observed),set(plan["expected_region_volumes_nm3"]))
            for name, volume in observed.items():
                self.assertAlmostEqual(volume,plan["expected_region_volumes_nm3"][name],places=12)
            self.assertAlmostEqual(sum(observed.values()),plan["domain_volume_nm3"],places=12)

    def test_independent_sixth_thickness(self):
        a, b = sixlayer_plan((.6,)*6), sixlayer_plan((.6,)*5+(.7,))
        self.assertAlmostEqual(b["height_nm"]-a["height_nm"],.1)
        self.assertNotEqual(a["geometry_sha256"],b["geometry_sha256"])
        self.assertEqual(a["bottom_reference_z_nm"],b["bottom_reference_z_nm"])

    def test_refinements_preserve_geometry_volumes(self):
        p = sixlayer_plan(REPRESENTATIVES["D"],y_refinement=2,z_refinement=2)
        self.assertEqual(p["cells"],3*12*14)
        self.assertEqual(p["expected_region_volumes_nm3"],sixlayer_plan(REPRESENTATIVES["D"])["expected_region_volumes_nm3"])

    def test_native_configuration_inventory(self):
        r = self._input(REPRESENTATIVES["B"])
        c = build_sixlayer_config(r)
        self.assertEqual(c.nedelec_degree,6)
        self.assertEqual(c.lambda0,.7)
        self.assertEqual(c.incident_theta_deg,89)
        self.assertEqual(c.incident_phi_deg,90)
        self.assertEqual(c.mesh_axis_cell_counts,(3,6,8))
        self.assertEqual(tuple(x[2].tag for x in grating_layers(c)),tuple(range(21,27)))
        self.assertEqual(len(material_regions(c)),8)
        self.assertEqual((c.diffraction_order_max_m,c.diffraction_order_max_n),(5,9))
        self.assertEqual(c.dtn_phase_gauge,"boundary_plane")
        self.assertEqual(c.grating_layer_indices[0],c.n_substrate)
        self.assertNotEqual(c.grating_layer_indices[1],c.n_substrate)
        self.assertNotEqual(c.grating_layer_indices[5],c.n_substrate)
        self.assertEqual(c.as_jsonable()["material_identity_sha256"],r["physical_model"]["materials_identity_sha256"])

    def test_recipe_identity_shared_but_case_not_shared(self):
        a,b = (self._input(REPRESENTATIVES[name]) for name in ("A","C"))
        self.assertEqual(a["generator_identity_sha256"],b["generator_identity_sha256"])
        self.assertNotEqual(a["physical_model_sha256"],b["physical_model_sha256"])
        self.assertNotEqual(a["resolved_numerical_config_sha256"],b["resolved_numerical_config_sha256"])
        refined = self._input(REPRESENTATIVES["A"],'[mesh]\ny_refinement=2\n')
        self.assertEqual(a["physical_model_sha256"],refined["physical_model_sha256"])
        self.assertNotEqual(a["generator_identity_sha256"],refined["generator_identity_sha256"])

    def test_unknown_and_wrong_physics_rejected(self):
        for extra in ('lambda0=.84\n','p=4\n','[mesh]\ny_refinement=0\n',
                      '[dtn]\nevanescent_padding=0\n','[dtn]\nquadrature_degree=2\n'):
            with self.assertRaises(ValueError):
                self._input(REPRESENTATIVES["A"],extra)
        for t in ((.4,)*6,(1.1,)*6,(.5,)*5,(True,)*6):
            with self.assertRaises(ValueError):
                sixlayer_plan(t)


if __name__ == "__main__":
    unittest.main()
