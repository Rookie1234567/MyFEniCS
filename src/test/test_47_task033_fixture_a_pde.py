from __future__ import annotations

import math
import os
import unittest

from src.common.config_3d import oblique_incidence_airbox_config
from src.test.stage2_test_utils import run_small_3d_case


RUN_TASK033_PDE = os.environ.get("RUN_TASK033_PDE_TESTS") == "1"


def _fixture_a_config(*, degree: int, h_nm: float, polarization: str):
    return oblique_incidence_airbox_config(
        case_name=(f"task033_fixture_a_p{degree}_h{h_nm:g}_{polarization}").replace(
            ".", "p"
        ),
        stage_case="floquet_airbox",
        geometry_kind="airbox",
        lambda0=13.5,
        period_x=10.0,
        period_y=10.0,
        z_min=-5.0,
        z_max=5.0,
        use_floquet_xy=True,
        use_pml=False,
        incident_theta_deg=80.0,
        incident_phi_deg=0.0,
        polarization_kind=polarization,
        custom_polarization=None,
        nedelec_degree=int(degree),
        visualization_degree=1,
        mesh_target_size=float(h_nm),
        mesh_cell_type="hexahedron",
        floquet_constraint_mode="auto",
        unique_output=True,
    )


@unittest.skipUnless(
    RUN_TASK033_PDE,
    "Set RUN_TASK033_PDE_TESTS=1 to run Task033 Fixture A PDE gates.",
)
class Task033FixtureAPDETests(unittest.TestCase):
    def _run_two_meshes_s_and_p(self, degrees: tuple[int, ...]) -> None:
        for degree in degrees:
            for h_nm in (5.0, 2.5):
                for polarization in ("s", "p"):
                    with self.subTest(
                        degree=degree,
                        h_nm=h_nm,
                        polarization=polarization,
                    ):
                        cfg = _fixture_a_config(
                            degree=degree,
                            h_nm=h_nm,
                            polarization=polarization,
                        )
                        summary = run_small_3d_case(
                            cfg,
                            (
                                f"task033_fixture_a_p{degree}_h{h_nm:g}_"
                                f"{polarization}_mpi{cfg.nedelec_degree}"
                            ).replace(".", "p"),
                        )
                        self.assertEqual(
                            summary["floquet_constraint_mode_resolved"],
                            (
                                "topological_edges_p1"
                                if degree == 1
                                else f"topological_trace_p{degree}"
                            ),
                        )
                        self.assertFalse(summary["floquet_used_full_boundary_gather"])
                        self.assertFalse(
                            summary["floquet_created_dense_boundary_square"]
                        )
                        self.assertLessEqual(
                            float(summary["linear_system_relative_residual"]),
                            1.0e-10,
                        )
                        self.assertLessEqual(
                            float(summary["floquet_x_face_mismatch"]), 1.0e-10
                        )
                        self.assertLessEqual(
                            float(summary["floquet_y_face_mismatch"]), 1.0e-10
                        )
                        self.assertLessEqual(
                            float(summary["floquet_edge_corner_mismatch"]),
                            1.0e-10,
                        )
                        self.assertTrue(
                            math.isfinite(float(summary["relative_max_abs_E_error"]))
                        )
                        self.assertTrue(
                            math.isfinite(float(summary["relative_max_abs_H_error"]))
                        )

    def test_p1_p2_two_meshes_s_and_p(self) -> None:
        self._run_two_meshes_s_and_p((1, 2))

    def test_p3_p4_two_meshes_s_and_p(self) -> None:
        self._run_two_meshes_s_and_p((3, 4))


if __name__ == "__main__":
    unittest.main()
