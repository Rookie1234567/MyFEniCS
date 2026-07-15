from __future__ import annotations

import inspect
import unittest

from basix.ufl import element
from dolfinx import default_real_type

from src.common.config_3d import normal_incidence_airbox_config
from src.constraints import floquet_3d
from src.test.stage2_test_utils import (
    RUN_PDE_TESTS,
    floquet_smoke_config,
    run_small_3d_case,
    stage1_smoke_config,
)


class Test3DHighOrderFloquetTrace(unittest.TestCase):
    def test_p2_hexa_n1curl_trace_dof_layout_is_edge_and_face_based(self):
        curl_el = element(
            "N1curl", "hexahedron", 2, dtype=default_real_type
        ).basix_element

        self.assertEqual([len(dofs) for dofs in curl_el.entity_dofs[1]], [2] * 12)
        self.assertEqual([len(dofs) for dofs in curl_el.entity_dofs[2]], [4] * 6)
        self.assertGreater(len(curl_el.entity_dofs[3][0]), 0)

    def test_auto_mode_selects_degree_qualified_trace_paths(self):
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
        p4 = normal_incidence_airbox_config(
            stage_case="floquet_airbox",
            use_floquet_xy=True,
            nedelec_degree=4,
            floquet_constraint_mode="auto",
        )
        p1_generic_trace = normal_incidence_airbox_config(
            stage_case="floquet_airbox",
            use_floquet_xy=True,
            nedelec_degree=1,
            floquet_constraint_mode="topological_trace",
        )

        self.assertEqual(
            floquet_3d._resolve_constraint_mode(None, p1), "topological_edges_p1"
        )
        self.assertEqual(
            floquet_3d._resolve_constraint_mode(None, p2), "topological_trace_p2"
        )
        self.assertEqual(
            floquet_3d._resolve_constraint_mode(None, p3), "topological_trace_p3"
        )
        self.assertEqual(
            floquet_3d._resolve_constraint_mode(None, p4), "topological_trace_p4"
        )
        self.assertEqual(
            floquet_3d._resolve_constraint_mode(None, p1_generic_trace),
            "topological_edges_p1",
        )

    def test_p2_formal_path_has_no_probe_or_pinv_mapping(self):
        dispatcher_source = inspect.getsource(floquet_3d.build_double_floquet_mpc)
        source = inspect.getsource(floquet_3d._build_double_floquet_mpc_high_order)
        self.assertIn("_build_double_floquet_mpc_high_order", dispatcher_source)
        self.assertNotIn("_build_double_floquet_mpc_p2_trace", dispatcher_source)
        self.assertNotIn("_build_double_floquet_mpc_p1_legacy", dispatcher_source)
        self.assertIn("build_high_order_constraint_data", source)
        self.assertNotIn("_probe_values", source)
        self.assertNotIn("_transform(", source)
        self.assertNotIn("pinv", source.lower())

    def test_p2_allows_stage2a_2b_2c_stage4a_and_stage4b(self):
        source = inspect.getsource(floquet_3d._build_double_floquet_mpc_high_order)

        self.assertIn('"floquet_airbox"', source)
        self.assertIn('"pml_airbox"', source)
        self.assertIn('"fresnel_interface"', source)
        self.assertIn('"stage4_flat_layer_sanity"', source)
        self.assertIn('"stage4_block_grating"', source)
        self.assertIn("p1--p4", source)

    @unittest.skipUnless(
        RUN_PDE_TESTS, "Set RUN_STAGE2_PDE_TESTS=1 to run p=2 3D Floquet PDE tests."
    )
    def test_stage1_p2_airbox_smoke_does_not_use_floquet(self):
        summary = run_small_3d_case(
            stage1_smoke_config(nedelec_degree=2, visualization_degree=1),
            "level17_stage1_p2",
        )
        self.assertFalse(summary["use_floquet_xy"])

    @unittest.skipUnless(
        RUN_PDE_TESTS, "Set RUN_STAGE2_PDE_TESTS=1 to run p=2 3D Floquet PDE tests."
    )
    def test_floquet_airbox_p1_p2_use_generalized_sparse_constraints(self):
        for degree in (1, 2):
            with self.subTest(degree=degree):
                cfg = floquet_smoke_config(
                    case="oblique",
                    nedelec_degree=degree,
                    visualization_degree=1,
                    mesh_target_size=300.0,
                    floquet_constraint_mode="auto",
                )
                summary = run_small_3d_case(cfg, f"level17_floquet_p{degree}")
                expected_mode = (
                    "topological_edges_p1"
                    if degree == 1
                    else "topological_trace_p2"
                )

                self.assertEqual(
                    summary["floquet_constraint_mode_resolved"], expected_mode
                )
                self.assertGreater(
                    int(summary["floquet_num_edge_constraints"]), 0
                )
                if degree == 1:
                    self.assertEqual(
                        int(summary["floquet_num_face_constraints"]), 0
                    )
                else:
                    self.assertGreater(
                        int(summary["floquet_num_face_constraints"]), 0
                    )
                self.assertGreater(
                    int(summary["floquet_max_masters_per_slave"]), 0
                )
                self.assertFalse(summary["floquet_used_full_boundary_gather"])
                self.assertFalse(summary["floquet_created_dense_boundary_square"])


if __name__ == "__main__":
    unittest.main()
