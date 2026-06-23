from __future__ import annotations

import sys
from pathlib import Path


# =============================================================================
# PyCharm direct-run settings
# =============================================================================
#
# In PyCharm, run this file directly:
#
#   fenics_vector_maxwell_floquet_demo_v2_parallel/src/main.py
#
# The variables below are converted to runner options.  Keep
# SIMULATION_DIMENSION="2d" for the original grating workflow.  Switch it to
# "3d" for the staged 3D Maxwell air-box workflow.

USE_PYCHARM_SETTINGS_WHEN_NO_ARGS = True
SIMULATION_DIMENSION = "3d"  # "2d" or "3d"

# Main physics switch:
#   "scattered"  = background-field scattering formulation
#   "port"       = total-field port formulation
#   "all"        = run scattered and port formulations
CALCULATION_METHOD = "all"

# Polarization model:
#   "TM" = current in-plane vector E=(Ex,Ey), Nedelec H(curl) element
#   "TE" = scalar Ez model, Lagrange element
POLARIZATION_TYPE = "TM"

# Floquet constraint backend:
#   "mpc_official" = dolfinx_mpc low-level constraints, MPI-ready
#   "manual"       = serial matrix-elimination checker
#   "both"         = serial comparison of mpc_official and manual
CONSTRAINT_BACKEND = "manual"

# Scattering background for CALCULATION_METHOD="scattered".
SCATTERING_BACKGROUND = "layered"

# Port boundary model for CALCULATION_METHOD="port" or "all".
#   "robin" = current MPI-ready fundamental-mode port
#   "dtn"   = serial Fourier DtN port
#   "all"   = run both where supported
PORT_BOUNDARY_MODEL = "dtn"

# Fourier DtN port implementation:
#   "auxiliary" = sparse auxiliary modal-amplitude unknowns, recommended
#   "explicit"  = old Q^*YQ outer-product reference/debug implementation
PORT_DTN_ASSEMBLY = "explicit"

# False = only order 0; True = automatically include clearly propagating
# diffraction orders on the top and bottom ports.
PORT_USE_DIFFRACTION_ORDERS = True

# Common numerical choices.  None means "use src/common/config.py".
NEDELEC_DEGREE = 2
VISUALIZATION_DEGREE = 3
MESH_TARGET_SIZE = 25.0
INCIDENT_ANGLE_DEG = 30.0

# R/T postprocessing.  Keep this enabled if you want power_metrics.json,
# diffraction_orders.csv, and R_total/T_total in run_summary.json.
COMPUTE_POWER_METRICS = True
DIFFRACTION_ORDER_COUNT = None
POWER_PROBE_NUM_POINTS = None

# Output management.
UNIQUE_OUTPUT = True

# Port-only option.
PORT_USE_PML = None

# =============================================================================
# 3D staged air-box / Floquet / PML settings
# =============================================================================

# The variables below are converted into the same CLI flags used by
# src/runners/run_3d_airbox.py, so PyCharm and command-line runs exercise the
# same code path.
STAGE_CASE_3D = "stage4_block_grating"  # stage1_airbox, floquet_airbox, pml_airbox, fresnel_interface, stage2_all, stage4_block_grating
AIRBOX3D_CASE = "normal"  # "normal", "oblique", or "both"
INCIDENT_THETA_DEG_3D = None  # None keeps the selected case default.
INCIDENT_PHI_DEG_3D = None
POLARIZATION_KIND_3D = None  # None keeps case default; otherwise "s", "p", or "custom".
NEDELEC_DEGREE_3D = 1
VISUALIZATION_DEGREE_3D = 1
# Stage 4 hexa meshes require material/block planes to land on grid planes.
# For the default 350 x 300 nm period and 150 x 100 x 150 nm block, h=50 nm
# and h=25 nm align; h=30 nm does not.
MESH_TARGET_SIZE_3D = 50.0
MESH_CELL_TYPE_3D = "auto"  # auto / tetrahedron / hexahedron
FLOQUET_CONSTRAINT_MODE_3D = "auto"  # auto / topological_edges / sparse_facet legacy alias
LAMBDA0_3D = 633
USE_FLOQUET_XY_3D = None  # None lets STAGE_CASE_3D choose the default.
USE_PML_3D = True
PML_TOP_THICKNESS_3D = 250.0
PML_BOTTOM_THICKNESS_3D = 250.0
PML_ALPHA_3D = 5.0
N_SUBSTRATE_3D = 1.45
SOLVER_PROFILE_3D = "direct"
SOLVER_RTOL_3D = 1.0e-8
SOLVER_ATOL_3D = 1.0e-12
SOLVER_MAX_IT_3D = 1000
SOLVER_MONITOR_3D = False
DIVERGENCE_PENALTY_3D = 0.0

# Stage 4 rectangular block grating settings.  These are ignored by Stage 1/2
# cases unless their matching CLI flags are consumed by the selected runner.
PERIOD_X_3D = 350.0
PERIOD_Y_3D = 300.0
N_GRATING_3D = 2.0
GRATING_WIDTH_X_3D = 150.0
GRATING_WIDTH_Y_3D = 100.0
GRATING_HEIGHT_3D = 150.0
SCATTERING_BACKGROUND_3D = "layered"
DIFFRACTION_ZERO_ORDER_ONLY_3D = True
DIFFRACTION_ORDER_MAX_M_3D = None
DIFFRACTION_ORDER_MAX_N_3D = None
DIFFRACTION_SAMPLE_COUNT_X_3D = 24
DIFFRACTION_SAMPLE_COUNT_Y_3D = 24
DIFFRACTION_TOP_PROBE_Z_3D = None
DIFFRACTION_BOTTOM_PROBE_Z_3D = None
DIFFRACTION_RAYLEIGH_TOL_3D = None


def _workspace_root() -> Path:
    """Return the folder that contains this demo package."""
    return Path(__file__).resolve().parents[2]


def _ensure_package_importable() -> None:
    """Make direct script execution work in PyCharm and Docker alike."""
    root = str(_workspace_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def _add_value(args: list[str], flag: str, value: object | None) -> None:
    if value is not None:
        args.extend([flag, str(value)])


def _add_bool(args: list[str], positive_flag: str, value: bool | None) -> None:
    if value is None:
        return
    if value:
        args.append(positive_flag)
    else:
        args.append("--no-" + positive_flag.removeprefix("--"))


def _pycharm_args_2d() -> list[str]:
    args: list[str] = [
        "--formulation",
        CALCULATION_METHOD,
        "--constraint-backend",
        CONSTRAINT_BACKEND,
        "--polarization-type",
        POLARIZATION_TYPE,
        "--scattering-background",
        SCATTERING_BACKGROUND,
        "--port-boundary-model",
        PORT_BOUNDARY_MODEL,
        "--port-dtn-assembly",
        PORT_DTN_ASSEMBLY,
    ]
    _add_value(args, "--nedelec-degree", NEDELEC_DEGREE)
    _add_value(args, "--visualization-degree", VISUALIZATION_DEGREE)
    _add_value(args, "--mesh-target-size", MESH_TARGET_SIZE)
    _add_value(args, "--incident-angle-deg", INCIDENT_ANGLE_DEG)
    _add_value(args, "--diffraction-order-count", DIFFRACTION_ORDER_COUNT)
    _add_value(args, "--power-probe-num-points", POWER_PROBE_NUM_POINTS)
    _add_bool(args, "--compute-power-metrics", COMPUTE_POWER_METRICS)
    _add_bool(args, "--port-use-diffraction-orders", PORT_USE_DIFFRACTION_ORDERS)
    _add_bool(args, "--unique-output", UNIQUE_OUTPUT)
    _add_bool(args, "--port-use-pml", PORT_USE_PML)
    return args


def _pycharm_args_3d() -> list[str]:
    """Translate the editable 3D variables above into runner CLI arguments."""
    args = ["--stage-case", STAGE_CASE_3D, "--case", AIRBOX3D_CASE]
    _add_value(args, "--nedelec-degree", NEDELEC_DEGREE_3D)
    _add_value(args, "--visualization-degree", VISUALIZATION_DEGREE_3D)
    _add_value(args, "--mesh-target-size", MESH_TARGET_SIZE_3D)
    _add_value(args, "--mesh-cell-type", MESH_CELL_TYPE_3D)
    _add_value(args, "--floquet-constraint-mode", FLOQUET_CONSTRAINT_MODE_3D)
    _add_value(args, "--lambda0", LAMBDA0_3D)
    _add_value(args, "--incident-theta-deg", INCIDENT_THETA_DEG_3D)
    _add_value(args, "--incident-phi-deg", INCIDENT_PHI_DEG_3D)
    _add_value(args, "--polarization-kind", POLARIZATION_KIND_3D)
    _add_value(args, "--solver-profile", SOLVER_PROFILE_3D)
    _add_value(args, "--solver-rtol", SOLVER_RTOL_3D)
    _add_value(args, "--solver-atol", SOLVER_ATOL_3D)
    _add_value(args, "--solver-max-it", SOLVER_MAX_IT_3D)
    _add_bool(args, "--solver-monitor", SOLVER_MONITOR_3D)
    _add_value(args, "--divergence-penalty", DIVERGENCE_PENALTY_3D)
    _add_bool(args, "--unique-output", UNIQUE_OUTPUT)
    _add_bool(args, "--use-floquet-xy", USE_FLOQUET_XY_3D)
    _add_bool(args, "--use-pml", USE_PML_3D)
    _add_value(args, "--pml-top-thickness", PML_TOP_THICKNESS_3D)
    _add_value(args, "--pml-bottom-thickness", PML_BOTTOM_THICKNESS_3D)
    _add_value(args, "--pml-alpha", PML_ALPHA_3D)
    _add_value(args, "--n-substrate", N_SUBSTRATE_3D)
    _add_value(args, "--period-x", PERIOD_X_3D)
    _add_value(args, "--period-y", PERIOD_Y_3D)
    _add_value(args, "--n-grating", N_GRATING_3D)
    _add_value(args, "--grating-width-x", GRATING_WIDTH_X_3D)
    _add_value(args, "--grating-width-y", GRATING_WIDTH_Y_3D)
    _add_value(args, "--grating-height", GRATING_HEIGHT_3D)
    _add_value(args, "--scattering-background", SCATTERING_BACKGROUND_3D)
    _add_bool(args, "--diffraction-zero-order-only", DIFFRACTION_ZERO_ORDER_ONLY_3D)
    _add_value(args, "--diffraction-order-max-m", DIFFRACTION_ORDER_MAX_M_3D)
    _add_value(args, "--diffraction-order-max-n", DIFFRACTION_ORDER_MAX_N_3D)
    _add_value(args, "--diffraction-sample-count-x", DIFFRACTION_SAMPLE_COUNT_X_3D)
    _add_value(args, "--diffraction-sample-count-y", DIFFRACTION_SAMPLE_COUNT_Y_3D)
    _add_value(args, "--diffraction-top-probe-z", DIFFRACTION_TOP_PROBE_Z_3D)
    _add_value(args, "--diffraction-bottom-probe-z", DIFFRACTION_BOTTOM_PROBE_Z_3D)
    _add_value(args, "--diffraction-rayleigh-tol", DIFFRACTION_RAYLEIGH_TOL_3D)
    return args


def main() -> None:
    _ensure_package_importable()
    from fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox import (
        main as run_3d_airbox_main,
    )
    from fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_cases import main as run_cases_main

    if USE_PYCHARM_SETTINGS_WHEN_NO_ARGS and len(sys.argv) == 1:
        if SIMULATION_DIMENSION.lower() == "3d":
            run_3d_airbox_main(_pycharm_args_3d())
        elif SIMULATION_DIMENSION.lower() == "2d":
            run_cases_main(_pycharm_args_2d())
        else:
            raise SystemExit('SIMULATION_DIMENSION must be "2d" or "3d".')
        return

    if len(sys.argv) > 1 and sys.argv[1].lower() in ("2d", "3d"):
        dimension = sys.argv[1].lower()
        runner_args = sys.argv[2:]
        if dimension == "3d":
            run_3d_airbox_main(runner_args)
        else:
            run_cases_main(runner_args)
        return

    run_cases_main()


if __name__ == "__main__":
    main()
