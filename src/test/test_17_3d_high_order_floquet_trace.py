from __future__ import annotations

import inspect
import unittest

from basix.ufl import element
from dolfinx import default_real_type

from src.common.config_3d import normal_incidence_airbox_config
from src.constraints import floquet_3d
from src.test.stage2_test_utils import RUN_PDE_TESTS, floquet_smoke_config, run_small_3d_case, stage1_smoke_config


class Test3DHighOrderFloquetTrace(unittest.TestCase):
    def test_p2_hexa_n1curl_trace_dof_layout_is_edge_and_face_based(self):
        curl_el = element("N1curl", "hexahedron", 2, dtype=default_real_type).basix_element

        self.assertEqual([len(dofs) for dofs in curl_el.entity_dofs[1]], [2] * 12)
        self.assertEqual([len(dofs) for dofs in curl_el.entity_dofs[2]], [4] * 6)
        self.assertGreater(len(curl_el.entity_dofs[3][0]), 0)

    def test_auto_mode_selects_p1_edges_or_p2_trace(self):
        p1 = normal_incidence_airbox_config(
            stage_case="floquet_airbox",
            use_floquet_xy=True,
            nedelec_degree=1,
            floquet_constraint_mode="auto",
        )
        p2 = normal_incidence_airbox_config(
            stage_case="floquet_airbox",
            use_floquet_xy=True,
            nedelec_degree=2,
            floquet_constraint_mode="auto",
        )
        p3 = normal_incidence_airbox_config(
            stage_case="floquet_airbox",
            use_floquet_xy=True,
            nedelec_degree=3,
            floquet_constraint_mode="auto",
        )

        self.assertEqual(floquet_3d._resolve_constraint_mode(None, p1), "topological_edges_p1")
        self.assertEqual(floquet_3d._resolve_constraint_mode(None, p2), "topological_trace_p2")
        with self.assertRaises(NotImplementedError):
            floquet_3d._resolve_constraint_mode(None, p3)

    def test_p2_formal_path_has_no_probe_or_pinv_mapping(self):
        source = inspect.getsource(floquet_3d._build_double_floquet_mpc_p2_trace)
        self.assertIn("_build_p2_face_constraints_for_kind", source)
        self.assertIn("_build_p2_edge_constraints_for_kind", source)
        self.assertNotIn("_probe_values", source)
        self.assertNotIn("_transform(", source)
        self.assertNotIn("pinv", source.lower())

    def test_p2_is_limited_to_stage2a_for_now(self):
        source = inspect.getsource(floquet_3d._require_supported_topological_trace_p2)

        self.assertIn('cfg.stage_case != "floquet_airbox"', source)
        self.assertIn("Stage 2A", source)

    @unittest.skipUnless(RUN_PDE_TESTS, "Set RUN_STAGE2_PDE_TESTS=1 to run p=2 3D Floquet PDE tests.")
    def test_stage1_p2_airbox_smoke_does_not_use_floquet(self):
        summary = run_small_3d_case(stage1_smoke_config(nedelec_degree=2, visualization_degree=1), "level17_stage1_p2")
        self.assertFalse(summary["use_floquet_xy"])

    @unittest.skipUnless(RUN_PDE_TESTS, "Set RUN_STAGE2_PDE_TESTS=1 to run p=2 3D Floquet PDE tests.")
    def test_floquet_airbox_p2_reports_face_constraints(self):
        cfg = floquet_smoke_config(
            case="oblique",
            nedelec_degree=2,
            visualization_degree=1,
            mesh_target_size=300.0,
            floquet_constraint_mode="auto",
        )
        summary = run_small_3d_case(cfg, "level17_floquet_p2")

        self.assertEqual(summary["floquet_constraint_mode_resolved"], "topological_trace_p2")
        self.assertGreater(int(summary["floquet_num_edge_constraints"]), 0)
        self.assertGreater(int(summary["floquet_num_face_constraints"]), 0)
        self.assertGreater(int(summary["floquet_max_masters_per_slave"]), 0)


if __name__ == "__main__":
    unittest.main()
