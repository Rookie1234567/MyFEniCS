from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np

from src.common.config_3d import SimulationConfig3D, normal_incidence_airbox_config, oblique_incidence_airbox_config
from src.solvers.solve_maxwell_3d_stage_1_airbox import run_stage1_airbox_3d_case
from src.solvers.solve_maxwell_3d_stage_2a_floquet_airbox import run_stage2a_floquet_airbox_3d_case
from src.solvers.solve_maxwell_3d_stage_2b_pml_airbox import run_stage2b_pml_airbox_3d_case
from src.solvers.solve_maxwell_3d_stage_2c_fresnel_interface import run_stage2c_fresnel_interface_3d_case


RUN_PDE_TESTS = os.environ.get("RUN_STAGE2_PDE_TESTS") == "1"


def assert_complex_close(testcase, actual: complex, expected: complex, tol: float, msg: str = "") -> None:
    testcase.assertLessEqual(abs(complex(actual) - complex(expected)), tol, msg or f"{actual!r} != {expected!r}")


def assert_vector_close(testcase, actual, expected, tol: float, msg: str = "") -> None:
    error = float(np.linalg.norm(np.asarray(actual) - np.asarray(expected)))
    testcase.assertLessEqual(error, tol, msg or f"vector error {error} > {tol}")


def temp_output_dir(prefix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=f"stage2_{prefix}_"))


def run_airbox_3d_case(cfg: SimulationConfig3D, out_dir: Path) -> dict[str, object]:
    if cfg.stage_case == "stage1_airbox":
        return run_stage1_airbox_3d_case(cfg, out_dir)
    if cfg.stage_case == "floquet_airbox":
        return run_stage2a_floquet_airbox_3d_case(cfg, out_dir)
    if cfg.stage_case == "pml_airbox":
        return run_stage2b_pml_airbox_3d_case(cfg, out_dir)
    if cfg.stage_case == "fresnel_interface":
        return run_stage2c_fresnel_interface_3d_case(cfg, out_dir)
    raise ValueError(f"Unsupported Stage 2 test case: {cfg.stage_case!r}")


def run_small_3d_case(cfg: SimulationConfig3D, prefix: str) -> dict[str, object]:
    summary = run_airbox_3d_case(cfg, temp_output_dir(prefix))
    if summary.get("case_status") != "completed":
        raise AssertionError(f"3D case did not complete: {summary.get('case_status')}")
    return summary


def stage1_smoke_config(**updates) -> SimulationConfig3D:
    values = {
        "stage_case": "stage1_airbox",
        "geometry_kind": "airbox",
        "use_floquet_xy": False,
        "use_pml": False,
        "nedelec_degree": 2,
        "visualization_degree": 2,
        "mesh_target_size": 300.0,
    }
    values.update(updates)
    return normal_incidence_airbox_config(**values)


def floquet_smoke_config(case: str = "normal", **updates) -> SimulationConfig3D:
    values = {
        "stage_case": "floquet_airbox",
        "geometry_kind": "airbox",
        "use_floquet_xy": True,
        "use_pml": False,
        "nedelec_degree": 2,
        "visualization_degree": 2,
        "mesh_target_size": 300.0,
    }
    values.update(updates)
    builder = normal_incidence_airbox_config if case == "normal" else oblique_incidence_airbox_config
    return builder(**values)


def pml_smoke_config(**updates) -> SimulationConfig3D:
    values = {
        "stage_case": "pml_airbox",
        "geometry_kind": "airbox",
        "use_floquet_xy": True,
        "use_pml": True,
        "pml_top_thickness": 250.0,
        "pml_bottom_thickness": 250.0,
        "nedelec_degree": 2,
        "visualization_degree": 2,
        "mesh_target_size": 300.0,
    }
    values.update(updates)
    return normal_incidence_airbox_config(**values)


def fresnel_smoke_config(**updates) -> SimulationConfig3D:
    values = {
        "stage_case": "fresnel_interface",
        "geometry_kind": "fresnel_interface",
        "use_floquet_xy": True,
        "use_pml": True,
        "pml_top_thickness": 250.0,
        "pml_bottom_thickness": 250.0,
        "n_substrate": 1.45 + 0.0j,
        "polarization_kind": "s",
        "custom_polarization": None,
        "nedelec_degree": 2,
        "visualization_degree": 2,
        "mesh_target_size": 300.0,
    }
    values.update(updates)
    return normal_incidence_airbox_config(**values)


def stage4_block_config(**updates) -> SimulationConfig3D:
    values = {
        "stage_case": "stage4_block_grating",
        "geometry_kind": "rectangular_block_grating",
        "scattering_background": "layered",
        "stage4_pml_outer_bc": "natural",
        "lambda0": 13.5,
        "period_x": 100.0,
        "period_y": 100.0,
        "air_height": 100.0,
        "substrate_thickness": 50.0,
        "z_min": -50.0,
        "z_max": 100.0,
        "interface_z": 0.0,
        "use_floquet_xy": True,
        "use_pml": True,
        "pml_top_thickness": 25.0,
        "pml_bottom_thickness": 25.0,
        "pml_alpha": 5.0,
        "n_substrate": 1.45 + 0.0j,
        "n_grating": 2.0 + 0.0j,
        "grating_width_x": 50.0,
        "grating_width_y": 50.0,
        "grating_height": 50.0,
        "incident_phi_deg": 0.0,
        "polarization_kind": "s",
        "custom_polarization": None,
        "nedelec_degree": 1,
        "visualization_degree": 1,
        "mesh_target_size": 5.0,
        "diffraction_zero_order_only": False,
        "diffraction_sample_count_x": 32,
        "diffraction_sample_count_y": 32,
        "diffraction_probe_fraction": 0.75,
        "diffraction_compute_modal_diagnostic": False,
    }
    values.update(updates)
    return normal_incidence_airbox_config(**values)
