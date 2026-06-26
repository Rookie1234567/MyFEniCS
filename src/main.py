from __future__ import annotations

import sys
from dataclasses import dataclass
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
# 3D staged settings
# =============================================================================
#
# Choose the active 3D input group here.  Only the selected dataclass below is
# translated into CLI flags, so changing an inactive case does not affect the
# current run.
ACTIVE_3D_INPUT_GROUP = "stage4_grating"  # stage1_airbox / stage2_no_grating / stage4_grating


@dataclass(frozen=True)
class Stage1AirboxInputs3D:
    stage_case: str = "stage1_airbox"
    case: str = "normal"  # normal / oblique / both
    incident_theta_deg: float | None = None
    incident_phi_deg: float | None = None
    polarization_kind: str | None = None
    nedelec_degree: int = 2
    visualization_degree: int = 2
    mesh_target_size: float = 140.0
    mesh_cell_type: str = "auto"
    mesh_spacing_mode: str = "auto"
    mesh_refined_size: float | None = None
    mesh_refinement_radius: float | None = None
    floquet_constraint_mode: str = "auto"
    lambda0: float = 633.0
    divergence_penalty: float = 0.0
    unique_output: bool = True


@dataclass(frozen=True)
class Stage2NoGratingInputs3D:
    stage_case: str = "floquet_airbox"  # floquet_airbox / pml_airbox / fresnel_interface / stage2_all
    case: str = "normal"  # normal / oblique / both
    incident_theta_deg: float | None = None
    incident_phi_deg: float | None = None
    polarization_kind: str | None = None
    nedelec_degree: int = 1
    visualization_degree: int = 1
    mesh_target_size: float = 300.0
    mesh_cell_type: str = "auto"
    mesh_spacing_mode: str = "auto"
    mesh_refined_size: float | None = None
    mesh_refinement_radius: float | None = None
    floquet_constraint_mode: str = "auto"
    lambda0: float = 633.0
    use_floquet_xy: bool | None = None
    use_pml: bool | None = None
    pml_top_thickness: float = 250.0
    pml_bottom_thickness: float = 250.0
    pml_alpha: float = 5.0
    n_substrate: float = 1.45
    divergence_penalty: float = 0.0
    unique_output: bool = True


@dataclass(frozen=True)
class Stage4GratingInputs3D:
    stage_case: str = "stage4_block_grating"  # stage4_block_grating / stage4_flat_layer_sanity / stage4_all
    case: str = "normal"  # normal / oblique / both
    incident_theta_deg: float | None = None
    incident_phi_deg: float | None = None
    polarization_kind: str | None = None
    nedelec_degree: int = 1
    visualization_degree: int = 1
    # Stage-4 hexa meshes now support fitted nonuniform axis spacing.  With
    # mesh_spacing_mode="auto", a divisible target keeps the old uniform mesh;
    # a non-divisible target inserts material planes automatically.
    mesh_target_size: float = 1.25
    mesh_cell_type: str = "auto"
    mesh_spacing_mode: str = "auto"  # auto / uniform_strict / boundary_fitted / local_refined
    mesh_refined_size: float | None = None
    mesh_refinement_radius: float | None = None
    floquet_constraint_mode: str = "auto"
    lambda0: float = 13.5
    use_floquet_xy: bool | None = True
    use_pml: bool | None = True
    pml_top_thickness: float = 25.0
    pml_bottom_thickness: float = 25.0
    pml_alpha: float = 5.0
    n_substrate: float = 1.45
    divergence_penalty: float = 0.0
    period_x: float = 100.0
    period_y: float = 100.0
    air_height: float = 100.0
    substrate_thickness: float = 50.0
    n_grating: float = 2.0
    grating_width_x: float = 50.0
    grating_width_y: float = 50.0
    grating_height: float = 50.0
    scattering_background: str = "layered"
    stage4_boundary_model: str = "dtn_port"  # dtn_port / pml / robin0
    stage4_dtn_order_policy: str = "auto_propagating"  # auto_propagating / zero_order / manual
    stage4_dtn_assembly: str = "auxiliary"
    stage4_pml_outer_bc: str = "natural"  # natural / zero_tangential
    diffraction_zero_order_only: bool = False
    diffraction_order_max_m: int | None = 2
    diffraction_order_max_n: int | None = 2
    diffraction_sample_count_x: int = 32
    diffraction_sample_count_y: int = 32
    diffraction_top_probe_z: float | None = None
    diffraction_bottom_probe_z: float | None = None
    diffraction_probe_fraction: float = 0.75
    diffraction_compute_modal_diagnostic: bool = False
    diffraction_rayleigh_tol: float | None = None
    unique_output: bool = True


STAGE1_AIRBOX_3D = Stage1AirboxInputs3D()
STAGE2_NO_GRATING_3D = Stage2NoGratingInputs3D()
STAGE4_GRATING_3D = Stage4GratingInputs3D()


def _selected_3d_inputs() -> object:
    groups = {
        "stage1_airbox": STAGE1_AIRBOX_3D,
        "stage2_no_grating": STAGE2_NO_GRATING_3D,
        "stage4_grating": STAGE4_GRATING_3D,
    }
    try:
        return groups[ACTIVE_3D_INPUT_GROUP]
    except KeyError as exc:
        raise SystemExit(
            "ACTIVE_3D_INPUT_GROUP must be 'stage1_airbox', 'stage2_no_grating', or 'stage4_grating'."
        ) from exc


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


def _setting_value(settings: object, name: str) -> object | None:
    return getattr(settings, name, None)


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
    """Translate only the active 3D dataclass into runner CLI arguments."""
    settings = _selected_3d_inputs()
    args = ["--stage-case", str(_setting_value(settings, "stage_case")), "--case", str(_setting_value(settings, "case"))]
    _add_value(args, "--nedelec-degree", _setting_value(settings, "nedelec_degree"))
    _add_value(args, "--visualization-degree", _setting_value(settings, "visualization_degree"))
    _add_value(args, "--mesh-target-size", _setting_value(settings, "mesh_target_size"))
    _add_value(args, "--mesh-cell-type", _setting_value(settings, "mesh_cell_type"))
    _add_value(args, "--mesh-spacing-mode", _setting_value(settings, "mesh_spacing_mode"))
    _add_value(args, "--mesh-refined-size", _setting_value(settings, "mesh_refined_size"))
    _add_value(args, "--mesh-refinement-radius", _setting_value(settings, "mesh_refinement_radius"))
    _add_value(args, "--floquet-constraint-mode", _setting_value(settings, "floquet_constraint_mode"))
    _add_value(args, "--lambda0", _setting_value(settings, "lambda0"))
    _add_value(args, "--incident-theta-deg", _setting_value(settings, "incident_theta_deg"))
    _add_value(args, "--incident-phi-deg", _setting_value(settings, "incident_phi_deg"))
    _add_value(args, "--polarization-kind", _setting_value(settings, "polarization_kind"))
    _add_value(args, "--divergence-penalty", _setting_value(settings, "divergence_penalty"))
    _add_bool(args, "--unique-output", _setting_value(settings, "unique_output"))
    _add_bool(args, "--use-floquet-xy", _setting_value(settings, "use_floquet_xy"))
    _add_bool(args, "--use-pml", _setting_value(settings, "use_pml"))
    _add_value(args, "--pml-top-thickness", _setting_value(settings, "pml_top_thickness"))
    _add_value(args, "--pml-bottom-thickness", _setting_value(settings, "pml_bottom_thickness"))
    _add_value(args, "--pml-alpha", _setting_value(settings, "pml_alpha"))
    _add_value(args, "--n-substrate", _setting_value(settings, "n_substrate"))
    _add_value(args, "--period-x", _setting_value(settings, "period_x"))
    _add_value(args, "--period-y", _setting_value(settings, "period_y"))
    _add_value(args, "--air-height", _setting_value(settings, "air_height"))
    _add_value(args, "--substrate-thickness", _setting_value(settings, "substrate_thickness"))
    _add_value(args, "--n-grating", _setting_value(settings, "n_grating"))
    _add_value(args, "--grating-width-x", _setting_value(settings, "grating_width_x"))
    _add_value(args, "--grating-width-y", _setting_value(settings, "grating_width_y"))
    _add_value(args, "--grating-height", _setting_value(settings, "grating_height"))
    _add_value(args, "--scattering-background", _setting_value(settings, "scattering_background"))
    _add_value(args, "--stage4-boundary-model", _setting_value(settings, "stage4_boundary_model"))
    _add_value(args, "--stage4-dtn-order-policy", _setting_value(settings, "stage4_dtn_order_policy"))
    _add_value(args, "--stage4-dtn-assembly", _setting_value(settings, "stage4_dtn_assembly"))
    _add_value(args, "--stage4-pml-outer-bc", _setting_value(settings, "stage4_pml_outer_bc"))
    _add_bool(args, "--diffraction-zero-order-only", _setting_value(settings, "diffraction_zero_order_only"))
    _add_value(args, "--diffraction-order-max-m", _setting_value(settings, "diffraction_order_max_m"))
    _add_value(args, "--diffraction-order-max-n", _setting_value(settings, "diffraction_order_max_n"))
    _add_value(args, "--diffraction-sample-count-x", _setting_value(settings, "diffraction_sample_count_x"))
    _add_value(args, "--diffraction-sample-count-y", _setting_value(settings, "diffraction_sample_count_y"))
    _add_value(args, "--diffraction-top-probe-z", _setting_value(settings, "diffraction_top_probe_z"))
    _add_value(args, "--diffraction-bottom-probe-z", _setting_value(settings, "diffraction_bottom_probe_z"))
    _add_value(args, "--diffraction-probe-fraction", _setting_value(settings, "diffraction_probe_fraction"))
    _add_bool(
        args,
        "--diffraction-compute-modal-diagnostic",
        _setting_value(settings, "diffraction_compute_modal_diagnostic"),
    )
    _add_value(args, "--diffraction-rayleigh-tol", _setting_value(settings, "diffraction_rayleigh_tol"))
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
