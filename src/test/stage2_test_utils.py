from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np

from src.common.config_3d import SimulationConfig3D, normal_incidence_airbox_config, oblique_incidence_airbox_config
from src.solvers.solve_airbox_maxwell_3d import run_airbox_3d_case


RUN_PDE_TESTS = os.environ.get("RUN_STAGE2_PDE_TESTS") == "1"


def assert_complex_close(testcase, actual: complex, expected: complex, tol: float, msg: str = "") -> None:
    testcase.assertLessEqual(abs(complex(actual) - complex(expected)), tol, msg or f"{actual!r} != {expected!r}")


def assert_vector_close(testcase, actual, expected, tol: float, msg: str = "") -> None:
    error = float(np.linalg.norm(np.asarray(actual) - np.asarray(expected)))
    testcase.assertLessEqual(error, tol, msg or f"vector error {error} > {tol}")


def temp_output_dir(prefix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=f"stage2_{prefix}_"))


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
        "solver_profile": "direct",
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
        "solver_profile": "direct",
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
        "solver_profile": "direct",
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
        "solver_profile": "direct",
    }
    values.update(updates)
    return normal_incidence_airbox_config(**values)
