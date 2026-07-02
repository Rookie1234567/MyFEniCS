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
# The variables below are converted to runner options.  Use
# SIMULATION_DIMENSION="2d" for the 2D grating workflow.  Switch it to "3d" for
# the staged 3D Maxwell workflow.

USE_PYCHARM_SETTINGS_WHEN_NO_ARGS = True
SIMULATION_DIMENSION = "3d"  # "2d" or "3d"

# =============================================================================
# 2D grating settings
# =============================================================================
#
# Choose the active 2D input group here.  Only the selected dataclass is
# translated into CLI flags, so changing inactive examples will not change the
# current run.
ACTIVE_2D_INPUT_GROUP = "euv_grating"  # euv_grating


@dataclass(frozen=True)
class Inputs2D:
    # 计算方法："scattered" 散射场 / "port" 总场端口 / "all" 同时跑。
    calculation_method: str = "port"
    # 偏振："TM" 为 Ex/Ey 矢量模型；"TE" 为 Ez 标量模型。本研究固定 TM。
    polarization_type: str = "TM"
    # 约束后端：DtN 当前用 "manual"；Robin/MPI 可用 "mpc_official"。
    constraint_backend: str = "manual"
    # scattered 方法背景："air" 或 "layered"。DtN 主线中仅写入配置记录。
    scattering_background: str = "layered"
    # 端口边界："dtn" 推荐；"robin" 用于历史对比；"all" 串行对比。
    port_boundary_model: str = "dtn"
    # DtN 装配："auxiliary" 推荐；"explicit" 作为交叉检查。
    port_dtn_assembly: str = "auxiliary"
    # True 自动包含传播衍射级；False 只保留 0 级。
    port_use_diffraction_orders: bool = True
    # 几何、网格、波长单位均为 nm。
    period_x: float = 600.0
    air_height: float = 850.0
    substrate_thickness: float = 350.0
    grating_width: float = 300.0
    grating_height: float = 180.0
    lambda0: float = 633.0
    incident_angle_deg: float = 15.0
    n_air: float = 1.0
    n_substrate: float = 1.45
    n_grating: float = 1.45
    nedelec_degree: int = 2
    visualization_degree: int = 2
    mesh_target_size: float = 25.0
    # 网格单元："triangle" 三角形 / "quadrilateral" 四边形。
    mesh_cell_shape: str = "triangle"
    # 厚度扫描时锁定光栅附近网格模板，避免近场积分随远场厚度换网格。
    mesh_lock_near_field_template: bool = False
    near_field_margin_x: float = 25.0
    near_field_air_top: float = 100.0
    near_field_sub_depth: float = 50.0
    # R/T 和衍射级后处理。
    compute_power_metrics: bool = True
    diffraction_order_count: int | None = None
    power_probe_num_points: int | None = None
    # 端口法默认不使用 PML。
    port_use_pml: bool | None = None
    unique_output: bool = True


@dataclass(frozen=True)
class EUVGratingInputs2D(Inputs2D):
    period_x: float = 100.0
    air_height: float = 100.0
    substrate_thickness: float = 50.0
    grating_width: float = 50.0
    grating_height: float = 50.0
    lambda0: float = 13.5
    incident_angle_deg: float = 0.0
    n_substrate: float = 1.1
    n_grating: float = 1.2
    mesh_target_size: float = 1.5
    mesh_cell_shape: str = "quadrilateral"
    mesh_lock_near_field_template: bool = True


EUV_GRATING_2D = EUVGratingInputs2D()


def _selected_2d_inputs() -> Inputs2D:
    groups = {
        "euv_grating": EUV_GRATING_2D,
    }
    try:
        return groups[ACTIVE_2D_INPUT_GROUP]
    except KeyError as exc:
        raise SystemExit("ACTIVE_2D_INPUT_GROUP must be 'euv_grating'.") from exc

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
    mesh_target_size: float = 1.5
    mesh_cell_type: str = "auto"
    mesh_spacing_mode: str = "auto"  # auto / uniform_strict / boundary_fitted / local_refined
    mesh_refined_size: float | None = None
    mesh_refinement_radius: float | None = None
    floquet_constraint_mode: str = "auto"
    lambda0: float = 13.5
    use_floquet_xy: bool | None = True
    use_pml: bool | None = False
    pml_top_thickness: float = 25.0
    pml_bottom_thickness: float = 25.0
    pml_alpha: float = 5.0
    n_substrate: complex = 1.1 + 0.0j
    substrate_material_label: str = "placeholder_substrate_user_unspecified"
    divergence_penalty: float = 0.0
    period_x: float = 100.0
    period_y: float = 100.0
    air_height: float = 50.0
    substrate_thickness: float = 50.0
    n_grating: complex = 0.999002304859 + 0.00182649365j
    grating_material_label: str = "Si / silicon"
    validation_role: str = "numerical_sanity_only"
    grating_width_x: float = 50.0
    grating_width_y: float = 50.0
    grating_height: float = 50.0
    scattering_background: str = "layered"
    stage4_boundary_model: str = "dtn_port"  # dtn_port / pml / robin0
    stage4_dtn_order_policy: str = "zero_order"  # auto_propagating / zero_order / manual
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
    settings = _selected_2d_inputs()
    args: list[str] = [
        "--formulation",
        str(settings.calculation_method),
        "--constraint-backend",
        str(settings.constraint_backend),
        "--polarization-type",
        str(settings.polarization_type),
        "--scattering-background",
        str(settings.scattering_background),
        "--port-boundary-model",
        str(settings.port_boundary_model),
        "--port-dtn-assembly",
        str(settings.port_dtn_assembly),
    ]
    _add_value(args, "--period-x", settings.period_x)
    _add_value(args, "--air-height", settings.air_height)
    _add_value(args, "--substrate-thickness", settings.substrate_thickness)
    _add_value(args, "--grating-width", settings.grating_width)
    _add_value(args, "--grating-height", settings.grating_height)
    _add_value(args, "--lambda0", settings.lambda0)
    _add_value(args, "--n-air", settings.n_air)
    _add_value(args, "--n-substrate", settings.n_substrate)
    _add_value(args, "--n-grating", settings.n_grating)
    _add_value(args, "--nedelec-degree", settings.nedelec_degree)
    _add_value(args, "--visualization-degree", settings.visualization_degree)
    _add_value(args, "--mesh-target-size", settings.mesh_target_size)
    _add_value(args, "--mesh-cell-shape", settings.mesh_cell_shape)
    _add_value(args, "--incident-angle-deg", settings.incident_angle_deg)
    _add_value(args, "--diffraction-order-count", settings.diffraction_order_count)
    _add_value(args, "--power-probe-num-points", settings.power_probe_num_points)
    _add_value(args, "--near-field-margin-x", settings.near_field_margin_x)
    _add_value(args, "--near-field-air-top", settings.near_field_air_top)
    _add_value(args, "--near-field-sub-depth", settings.near_field_sub_depth)
    _add_bool(args, "--compute-power-metrics", settings.compute_power_metrics)
    _add_bool(args, "--port-use-diffraction-orders", settings.port_use_diffraction_orders)
    _add_bool(args, "--lock-near-field-template", settings.mesh_lock_near_field_template)
    _add_bool(args, "--unique-output", settings.unique_output)
    _add_bool(args, "--port-use-pml", settings.port_use_pml)
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
    _add_value(args, "--substrate-material-label", _setting_value(settings, "substrate_material_label"))
    _add_value(args, "--period-x", _setting_value(settings, "period_x"))
    _add_value(args, "--period-y", _setting_value(settings, "period_y"))
    _add_value(args, "--air-height", _setting_value(settings, "air_height"))
    _add_value(args, "--substrate-thickness", _setting_value(settings, "substrate_thickness"))
    _add_value(args, "--n-grating", _setting_value(settings, "n_grating"))
    _add_value(args, "--grating-material-label", _setting_value(settings, "grating_material_label"))
    _add_value(args, "--validation-role", _setting_value(settings, "validation_role"))
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
    from fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_cases import (
        main as run_3d_cases_main,
    )
    from fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_cases import main as run_cases_main

    if USE_PYCHARM_SETTINGS_WHEN_NO_ARGS and len(sys.argv) == 1:
        if SIMULATION_DIMENSION.lower() == "3d":
            run_3d_cases_main(_pycharm_args_3d())
        elif SIMULATION_DIMENSION.lower() == "2d":
            run_cases_main(_pycharm_args_2d())
        else:
            raise SystemExit('SIMULATION_DIMENSION must be "2d" or "3d".')
        return

    if len(sys.argv) > 1 and sys.argv[1].lower() in ("2d", "3d"):
        dimension = sys.argv[1].lower()
        runner_args = sys.argv[2:]
        if dimension == "3d":
            run_3d_cases_main(runner_args)
        else:
            run_cases_main(runner_args)
        return

    run_cases_main()


if __name__ == "__main__":
    main()
