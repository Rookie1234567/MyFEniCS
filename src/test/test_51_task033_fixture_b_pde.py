from __future__ import annotations

import math
import os
import unittest

from src.common.config_3d import (
    NUMERICAL_SANITY_ONLY,
    SI_GRATING_INDEX_EUV_13P5_NM,
    SI_GRATING_MATERIAL_LABEL,
    SI_SUBSTRATE_INDEX_EUV_13P5_NM,
    SI_SUBSTRATE_MATERIAL_LABEL,
    normal_incidence_airbox_config,
)
from src.solvers.solve_maxwell_3d_stage_4a_flat_layer_sanity import (
    run_stage4a_flat_layer_sanity_3d_case,
)
from src.test.stage2_test_utils import temp_output_dir


RUN_TASK033_PDE = os.environ.get("RUN_TASK033_PDE_TESTS") == "1"


def _fixture_b_config(
    *, degree: int, h_nm: float, polarization: str, grazing_deg: float
):
    return normal_incidence_airbox_config(
        case_name=(
            f"task033_fixture_b_g{grazing_deg:g}_p{degree}_h{h_nm:g}_"
            f"{polarization}"
        ).replace(".", "p"),
        stage_case="stage4_flat_layer_sanity",
        geometry_kind="rectangular_block_grating",
        scattering_background="layered",
        stage4_boundary_model="dtn_port",
        stage4_dtn_order_policy="zero_order",
        stage4_dtn_assembly="auxiliary",
        stage4_pml_outer_bc="natural",
        lambda0=13.5,
        period_x=10.0,
        period_y=10.0,
        air_height=5.0,
        substrate_thickness=5.0,
        z_min=-5.0,
        z_max=5.0,
        interface_z=0.0,
        use_floquet_xy=True,
        use_pml=False,
        n_substrate=SI_SUBSTRATE_INDEX_EUV_13P5_NM,
        n_grating=SI_GRATING_INDEX_EUV_13P5_NM,
        substrate_material_label=SI_SUBSTRATE_MATERIAL_LABEL,
        grating_material_label=SI_GRATING_MATERIAL_LABEL,
        validation_role=NUMERICAL_SANITY_ONLY,
        grating_width_x=0.0,
        grating_width_y=0.0,
        grating_height=0.0,
        incident_theta_deg=90.0 - float(grazing_deg),
        incident_phi_deg=0.0,
        polarization_kind=polarization,
        custom_polarization=None,
        nedelec_degree=int(degree),
        visualization_degree=1,
        mesh_target_size=float(h_nm),
        mesh_cell_type="hexahedron",
        floquet_constraint_mode="auto",
        diffraction_zero_order_only=False,
        diffraction_sample_count_x=16,
        diffraction_sample_count_y=16,
        diffraction_probe_fraction=0.5,
        diffraction_compute_modal_diagnostic=False,
        unique_output=True,
    )


def _run_and_check(testcase: unittest.TestCase, cfg) -> dict[str, object]:
    summary = run_stage4a_flat_layer_sanity_3d_case(
        cfg, temp_output_dir(cfg.case_name)
    )
    testcase.assertEqual(summary["case_status"], "completed")
    expected_mode = (
        "topological_edges_p1"
        if cfg.nedelec_degree == 1
        else f"topological_trace_p{cfg.nedelec_degree}"
    )
    testcase.assertEqual(summary["floquet_constraint_mode_resolved"], expected_mode)
    testcase.assertFalse(summary["floquet_used_full_boundary_gather"])
    testcase.assertFalse(summary["floquet_created_dense_boundary_square"])
    testcase.assertLessEqual(
        float(summary["linear_system_relative_residual"]), 1.0e-10
    )
    for key in ("R_total", "T_total", "R_plus_T"):
        testcase.assertTrue(math.isfinite(float(summary[key])))
    consistency = summary["power_consistency"]
    for key in (
        "R_port_minus_R_ref",
        "T_port_minus_T_ref",
        "closure_error_port_volume",
    ):
        testcase.assertTrue(math.isfinite(float(consistency[key])))
    return summary


@unittest.skipUnless(
    RUN_TASK033_PDE,
    "Set RUN_TASK033_PDE_TESTS=1 to run Task033 Fixture B PDE gates.",
)
class Task033FixtureBPDETests(unittest.TestCase):
    def test_primary_p1_p2(self) -> None:
        for degree in (1, 2):
            for h_nm in (5.0, 2.5):
                for polarization in ("s", "p"):
                    with self.subTest(degree=degree, h_nm=h_nm, pol=polarization):
                        _run_and_check(
                            self,
                            _fixture_b_config(
                                degree=degree,
                                h_nm=h_nm,
                                polarization=polarization,
                                grazing_deg=10.0,
                            ),
                        )

    def test_primary_p3_p4(self) -> None:
        for degree in (3, 4):
            for h_nm in (5.0, 2.5):
                for polarization in ("s", "p"):
                    with self.subTest(degree=degree, h_nm=h_nm, pol=polarization):
                        _run_and_check(
                            self,
                            _fixture_b_config(
                                degree=degree,
                                h_nm=h_nm,
                                polarization=polarization,
                                grazing_deg=10.0,
                            ),
                        )

    def test_one_and_five_degree_smoke(self) -> None:
        for grazing_deg in (1.0, 5.0):
            for degree in (1, 2, 3, 4):
                for polarization in ("s", "p"):
                    with self.subTest(
                        grazing_deg=grazing_deg,
                        degree=degree,
                        pol=polarization,
                    ):
                        _run_and_check(
                            self,
                            _fixture_b_config(
                                degree=degree,
                                h_nm=5.0,
                                polarization=polarization,
                                grazing_deg=grazing_deg,
                            ),
                        )


if __name__ == "__main__":
    unittest.main()
