from __future__ import annotations

import sys
from dataclasses import dataclass, fields, replace
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.common.config_3d import SimulationConfig3D, target_stage4_config  # noqa: E402


# =============================================================================
# PyCharm direct-run facade
# =============================================================================
# Run this file with no arguments in PyCharm. Only this name selects the case;
# every preset below is immutable, so editing an inactive preset has no effect.
# The default is deliberately the inexpensive 3D Stage-1 smoke case.
USE_PYCHARM_SETTINGS_WHEN_NO_ARGS = True
ACTIVE_PYCHARM_PRESET = "3d_stage1_airbox_smoke"


@dataclass(frozen=True)
class Inputs2D:
    """PyCharm-facing 2D inputs; lengths and wavelength are in nm."""

    calculation_method: str = "port"
    polarization_type: str = "TM"
    constraint_backend: str = "manual"
    scattering_background: str = "layered"
    port_boundary_model: str = "dtn"
    port_dtn_assembly: str = "auxiliary"
    port_use_diffraction_orders: bool = True
    period_x: float = 600.0
    air_height: float = 850.0
    substrate_thickness: float = 350.0
    grating_width: float = 300.0
    grating_height: float = 180.0
    lambda0: float = 633.0
    incident_angle_deg: float = 15.0
    n_air: complex = 1.0
    n_substrate: complex = 1.45
    n_grating: complex = 1.45
    pml_top_thickness: float = 300.0
    pml_bottom_thickness: float = 300.0
    pml_alpha: float = 5.0
    nedelec_degree: int = 2
    visualization_degree: int = 2
    mesh_target_size: float = 25.0
    mesh_cell_shape: str = "triangle"
    mesh_lock_near_field_template: bool = False
    near_field_margin_x: float = 25.0
    near_field_air_top: float = 100.0
    near_field_sub_depth: float = 50.0
    compute_power_metrics: bool = True
    diffraction_order_count: int | None = None
    power_probe_num_points: int | None = None
    port_use_pml: bool | None = None
    generate_png_plots: bool = False
    unique_output: bool = True
    results_root: str | None = None


@dataclass(frozen=True)
class EUVGratingInputs2D(Inputs2D):
    period_x: float = 100.0
    air_height: float = 100.0
    substrate_thickness: float = 50.0
    grating_width: float = 50.0
    grating_height: float = 50.0
    lambda0: float = 13.5
    incident_angle_deg: float = 0.0
    n_substrate: complex = 1.1
    n_grating: complex = 1.2
    pml_top_thickness: float = 25.0
    pml_bottom_thickness: float = 25.0
    mesh_target_size: float = 1.5
    mesh_cell_shape: str = "quadrilateral"
    mesh_lock_near_field_template: bool = True


EUV_GRATING_2D = EUVGratingInputs2D()
_TM_PML_2D = Inputs2D(
    calculation_method="scattered",
    constraint_backend="manual",
    mesh_target_size=80.0,
    nedelec_degree=1,
)
_TM_DTN_AUX_2D = replace(EUV_GRATING_2D, mesh_target_size=3.0)

PRESETS_2D: dict[str, Inputs2D] = {
    "2d_tm_pml_floquet_smoke": _TM_PML_2D,
    "2d_tm_dtn_auxiliary_smoke": _TM_DTN_AUX_2D,
    "2d_tm_dtn_explicit_smoke": replace(_TM_DTN_AUX_2D, port_dtn_assembly="explicit"),
    "2d_te_port_smoke": replace(
        _TM_DTN_AUX_2D,
        polarization_type="TE",
        port_boundary_model="robin",
        port_use_diffraction_orders=False,
    ),
    "2d_complex_absorption": replace(
        _TM_DTN_AUX_2D,
        n_substrate=0.999002304859 + 0.00182649365j,
        n_grating=0.999002304859 + 0.00182649365j,
    ),
    "2d_euv_grating_direct": EUV_GRATING_2D,
}

# Compatibility selectors for callers that explicitly request one dimension.
ACTIVE_2D_INPUT_GROUP = "2d_euv_grating_direct"


@dataclass(frozen=True)
class Stage1AirboxInputs3D:
    """Stage-1 air box; all lengths and wavelength are in nm."""

    stage_case: str = "stage1_airbox"
    case: str = "normal"
    incident_theta_deg: float | None = None
    incident_phi_deg: float | None = None
    polarization_kind: str | None = None
    nedelec_degree: int = 1
    visualization_degree: int = 1
    mesh_target_size: float = 5.0
    mesh_cell_type: str = "auto"
    mesh_spacing_mode: str = "auto"
    mesh_refined_size: float | None = None
    mesh_refinement_radius: float | None = None
    floquet_constraint_mode: str = "auto"
    lambda0: float = 633.0
    period_x: float = 10.0
    period_y: float = 10.0
    air_height: float = 5.0
    substrate_thickness: float = 5.0
    divergence_penalty: float = 0.0
    unique_output: bool = True
    results_root: str | None = None


@dataclass(frozen=True)
class Stage2NoGratingInputs3D:
    """Stage-2 air/PML/interface inputs without a grating."""

    stage_case: str = "floquet_airbox"
    case: str = "normal"
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
    n_substrate: complex = 1.45
    divergence_penalty: float = 0.0
    unique_output: bool = True
    results_root: str | None = None


@dataclass(frozen=True)
class Stage4GratingInputs3D:
    """Stage-4 flat-layer or block-grating direct-solve inputs."""

    stage_case: str = "stage4_block_grating"
    case: str = "normal"
    incident_theta_deg: float | None = None
    incident_phi_deg: float | None = None
    polarization_kind: str | None = None
    nedelec_degree: int = 2
    visualization_degree: int = 1
    mesh_target_size: float = 5.0
    mesh_cell_type: str = "auto"
    mesh_spacing_mode: str = "auto"
    mesh_refined_size: float | None = None
    mesh_refinement_radius: float | None = None
    floquet_constraint_mode: str = "auto"
    lambda0: float = 13.5
    use_floquet_xy: bool | None = True
    use_pml: bool | None = False
    pml_top_thickness: float = 25.0
    pml_bottom_thickness: float = 25.0
    pml_alpha: float = 5.0
    n_substrate: complex = 0.999002304859 + 0.00182649365j
    substrate_material_label: str = "Si / silicon"
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
    stage4_boundary_model: str = "dtn_port"
    stage4_dtn_order_policy: str = "zero_order"
    stage4_dtn_assembly: str = "auxiliary"
    stage4_pml_outer_bc: str = "natural"
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
    petsc_direct_solver_profile: str = "default"
    petsc_ksp_view: bool = False
    petsc_log_view: bool = False
    petsc_extra_options: tuple[tuple[str, object], ...] = ()
    matrix_diagnostics_assemble_unconstrained: bool = False
    matrix_diagnostics_assemble_only: bool = False
    unique_output: bool = True
    results_root: str | None = None

    @classmethod
    def from_simulation_config(
        cls,
        cfg: SimulationConfig3D,
        *,
        direct_solver_profile: str = "default",
    ) -> Stage4GratingInputs3D:
        """Translate the shared target config without copying physical values."""

        values: dict[str, object] = {}
        for item in fields(cls):
            if item.name == "case":
                values[item.name] = "oblique"
            elif item.name == "petsc_extra_options":
                values[item.name] = tuple(cfg.petsc_extra_options.items())
            elif item.name == "results_root":
                values[item.name] = None
            elif hasattr(cfg, item.name):
                values[item.name] = getattr(cfg, item.name)
        values["petsc_direct_solver_profile"] = direct_solver_profile
        # target_stage4_config is also used by the assembly-only workstation
        # runtime.  A direct preset must execute the solve instead.
        values["matrix_diagnostics_assemble_only"] = False
        return cls(**values)


STAGE1_AIRBOX_3D = Stage1AirboxInputs3D()
STAGE2_NO_GRATING_3D = Stage2NoGratingInputs3D()
STAGE4_GRATING_3D = Stage4GratingInputs3D()
_STAGE4_FLAT_3D = replace(
    STAGE4_GRATING_3D,
    stage_case="stage4_flat_layer_sanity",
    nedelec_degree=1,
    mesh_target_size=2.0,
    period_x=10.0,
    period_y=10.0,
    air_height=5.0,
    substrate_thickness=5.0,
    grating_width_x=0.0,
    grating_width_y=0.0,
    grating_height=0.0,
)
_TARGET_STAGE4_DIRECT_H5 = Stage4GratingInputs3D.from_simulation_config(
    target_stage4_config(degree=2, h_nm=5.0)
)
_TARGET_STAGE4_DIRECT_H3 = Stage4GratingInputs3D.from_simulation_config(
    target_stage4_config(degree=2, h_nm=3.0)
)

PRESETS_3D: dict[str, object] = {
    "3d_stage1_airbox_smoke": STAGE1_AIRBOX_3D,
    "3d_stage2a_floquet_smoke": replace(
        STAGE2_NO_GRATING_3D, stage_case="floquet_airbox"
    ),
    "3d_stage2b_pml_smoke": replace(
        STAGE2_NO_GRATING_3D, stage_case="pml_airbox", use_pml=True
    ),
    "3d_stage2c_fresnel_smoke": replace(
        STAGE2_NO_GRATING_3D,
        stage_case="fresnel_interface",
        use_floquet_xy=True,
        use_pml=True,
    ),
    "3d_stage4a_flat_layer_direct": _STAGE4_FLAT_3D,
    "3d_stage4b_demo_direct_h5": STAGE4_GRATING_3D,
    "3d_stage4b_demo_direct_h3": replace(STAGE4_GRATING_3D, mesh_target_size=3.0),
    "3d_stage4b_demo_mumps_ooc": replace(
        STAGE4_GRATING_3D,
        petsc_direct_solver_profile="mumps_ooc",
    ),
    "3d_stage4b_demo_mumps_blr": replace(
        STAGE4_GRATING_3D,
        petsc_direct_solver_profile="mumps_blr",
    ),
    "3d_target_grating_direct_h5": _TARGET_STAGE4_DIRECT_H5,
    "3d_target_grating_direct_h3": _TARGET_STAGE4_DIRECT_H3,
}

ACTIVE_3D_INPUT_GROUP = "3d_stage1_airbox_smoke"


@dataclass(frozen=True)
class PresetInfo:
    physical_geometry: str
    discretization: str
    resource_class: str
    evidence_status: str
    purpose: str


PRESET_INFO: dict[str, PresetInfo] = {
    "2d_tm_pml_floquet_smoke": PresetInfo(
        "600 nm periodic 2D layered cell with upper/lower PML",
        "TM N1curl p=1, h=80 nm",
        "lightweight",
        "experimental_path_smoke",
        "Exercise scattered-field PML and x-Floquet assembly.",
    ),
    "2d_tm_dtn_auxiliary_smoke": PresetInfo(
        "100 x 150 nm 2D EUV grating cell",
        "TM N1curl p=2, h=3 nm",
        "moderate",
        "test_backed",
        "Exercise the recommended auxiliary Fourier-DtN path.",
    ),
    "2d_tm_dtn_explicit_smoke": PresetInfo(
        "100 x 150 nm 2D EUV grating cell",
        "TM N1curl p=2, h=3 nm",
        "moderate",
        "reference_cross_check",
        "Exercise the explicit Q^H Y Q DtN reference path.",
    ),
    "2d_te_port_smoke": PresetInfo(
        "100 x 150 nm 2D EUV grating cell",
        "TE Lagrange p=2, h=3 nm",
        "moderate",
        "test_backed",
        "Exercise the scalar TE Robin-port path.",
    ),
    "2d_complex_absorption": PresetInfo(
        "100 x 150 nm lossy 2D EUV grating cell",
        "TM N1curl p=2, h=3 nm",
        "moderate",
        "canonical_case003",
        "Reproduce the canonical TM complex-material absorption case.",
    ),
    "2d_euv_grating_direct": PresetInfo(
        "100 x 150 nm 2D EUV grating cell",
        "TM N1curl p=2, h=1.5 nm",
        "moderate_to_heavy",
        "user_case_not_qualified_scan",
        "Run the finer ordinary 2D EUV direct case.",
    ),
    "3d_stage1_airbox_smoke": PresetInfo(
        "10 x 10 x 10 nm homogeneous air box",
        "N1curl p=1, h=5 nm",
        "lightweight",
        "validated_smoke",
        "Safe default for first PyCharm Run.",
    ),
    "3d_stage2a_floquet_smoke": PresetInfo(
        "600 x 500 x 900 nm homogeneous double-periodic box",
        "N1curl p=1, h=300 nm",
        "lightweight",
        "test_backed_smoke",
        "Exercise x/y Floquet pairing.",
    ),
    "3d_stage2b_pml_smoke": PresetInfo(
        "600 x 500 nm periodic box with z-PML",
        "N1curl p=1, h=300 nm",
        "lightweight",
        "experimental_not_accuracy_qualified",
        "Exercise the 3D PML code path only.",
    ),
    "3d_stage2c_fresnel_smoke": PresetInfo(
        "600 x 500 nm periodic flat interface with z-PML",
        "N1curl p=1, h=300 nm",
        "lightweight",
        "experimental_not_accuracy_qualified",
        "Exercise the Fresnel-interface code path only.",
    ),
    "3d_stage4a_flat_layer_direct": PresetInfo(
        "10 x 10 x 10 nm flat lossy layer cell",
        "N1curl p=1, h=2 nm",
        "lightweight",
        "energy_sanity",
        "Run the flat-layer DtN and absorption sanity case.",
    ),
    "3d_stage4b_demo_direct_h5": PresetInfo(
        "100 x 100 x 100 nm demo cell; 50 nm cubic block; normal incidence",
        "N1curl p=2, h=5 nm",
        "workstation_preview",
        "demo_not_canonical_target",
        "Run the Stage4 demo geometry with ordinary MUMPS.",
    ),
    "3d_stage4b_demo_direct_h3": PresetInfo(
        "100 x 100 x 100 nm demo cell; 50 nm cubic block; normal incidence",
        "N1curl p=2, h=3 nm",
        "resource_heavy",
        "demo_not_canonical_target",
        "Run a finer demo geometry; inspect memory before launch.",
    ),
    "3d_stage4b_demo_mumps_ooc": PresetInfo(
        "100 x 100 x 100 nm demo cell; 50 nm cubic block; normal incidence",
        "N1curl p=2, h=5 nm; MUMPS OOC",
        "workstation_plus_disk",
        "experimental_direct_fallback",
        "Exercise out-of-core direct factorization on the demo.",
    ),
    "3d_stage4b_demo_mumps_blr": PresetInfo(
        "100 x 100 x 100 nm demo cell; 50 nm cubic block; normal incidence",
        "N1curl p=2, h=5 nm; MUMPS BLR",
        "workstation_experimental",
        "experimental_compressed_direct",
        "Exercise compressed direct factorization on the demo.",
    ),
    "3d_target_grating_direct_h5": PresetInfo(
        "50 x 25 x 140 nm target; 17 x 25 x 120 nm Si block; 80 deg s",
        "N1curl p=2, h=5 nm",
        "about_2.3_gb_canonical",
        "canonical_case021",
        "Reproduce the Benchmark 021 target h=5 direct solve.",
    ),
    "3d_target_grating_direct_h3": PresetInfo(
        "50 x 25 x 140 nm target; 17 x 25 x 120 nm Si block; 80 deg s",
        "N1curl p=2, h=3 nm",
        "about_8.2_gb_canonical",
        "canonical_case021_resource_heavy",
        "Reproduce the Benchmark 021 target h=3 direct solve.",
    ),
}


def available_preset_names() -> tuple[str, ...]:
    """Return every public PyCharm preset in deterministic order."""

    return tuple(sorted((*PRESETS_2D, *PRESETS_3D)))


def preset_info(name: str) -> PresetInfo:
    try:
        return PRESET_INFO[name]
    except KeyError as exc:
        raise SystemExit(
            f"Unknown preset {name!r}. Available: {', '.join(available_preset_names())}"
        ) from exc


def format_preset_listing(*, verbose: bool = False) -> str:
    if not verbose:
        return "\n".join(available_preset_names())
    rows: list[str] = []
    for name in available_preset_names():
        info = preset_info(name)
        rows.append(
            " | ".join(
                (
                    name,
                    f"geometry={info.physical_geometry}",
                    f"discretization={info.discretization}",
                    f"resource={info.resource_class}",
                    f"status={info.evidence_status}",
                    f"purpose={info.purpose}",
                )
            )
        )
    return "\n".join(rows)


def _selected_2d_inputs(preset_name: str | None = None) -> Inputs2D:
    name = preset_name or ACTIVE_2D_INPUT_GROUP
    try:
        return PRESETS_2D[name]
    except KeyError as exc:
        raise SystemExit(
            f"Unknown 2D preset {name!r}. Available: {', '.join(PRESETS_2D)}"
        ) from exc


def _selected_3d_inputs(preset_name: str | None = None) -> object:
    name = preset_name or ACTIVE_3D_INPUT_GROUP
    try:
        return PRESETS_3D[name]
    except KeyError as exc:
        raise SystemExit(
            f"Unknown 3D preset {name!r}. Available: {', '.join(PRESETS_3D)}"
        ) from exc


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ensure_package_importable() -> None:
    # Support both layouts used by this project: the repository lives inside
    # a parent workspace, or the repository itself is mounted as /work.
    roots = (Path(__file__).resolve().parents[1], _workspace_root())
    for path in reversed(roots):
        root = str(path)
        if root not in sys.path:
            sys.path.insert(0, root)


def _add_value(args: list[str], flag: str, value: object | None) -> None:
    if value is not None:
        args.extend([flag, str(value)])


def _add_bool(args: list[str], positive_flag: str, value: bool | None) -> None:
    if value is None:
        return
    args.append(positive_flag if value else "--no-" + positive_flag.removeprefix("--"))


def _setting_value(settings: object, name: str) -> object | None:
    return getattr(settings, name, None)


def _pycharm_args_2d(preset_name: str | None = None) -> list[str]:
    settings = _selected_2d_inputs(preset_name)
    args: list[str] = [
        "--formulation",
        settings.calculation_method,
        "--constraint-backend",
        settings.constraint_backend,
        "--polarization-type",
        settings.polarization_type,
        "--scattering-background",
        settings.scattering_background,
        "--port-boundary-model",
        settings.port_boundary_model,
        "--port-dtn-assembly",
        settings.port_dtn_assembly,
    ]
    for flag, value in (
        ("--period-x", settings.period_x),
        ("--air-height", settings.air_height),
        ("--substrate-thickness", settings.substrate_thickness),
        ("--grating-width", settings.grating_width),
        ("--grating-height", settings.grating_height),
        ("--lambda0", settings.lambda0),
        ("--n-air", settings.n_air),
        ("--n-substrate", settings.n_substrate),
        ("--n-grating", settings.n_grating),
        ("--pml-top-thickness", settings.pml_top_thickness),
        ("--pml-bottom-thickness", settings.pml_bottom_thickness),
        ("--pml-alpha", settings.pml_alpha),
        ("--nedelec-degree", settings.nedelec_degree),
        ("--visualization-degree", settings.visualization_degree),
        ("--mesh-target-size", settings.mesh_target_size),
        ("--mesh-cell-shape", settings.mesh_cell_shape),
        ("--incident-angle-deg", settings.incident_angle_deg),
        ("--diffraction-order-count", settings.diffraction_order_count),
        ("--power-probe-num-points", settings.power_probe_num_points),
        ("--near-field-margin-x", settings.near_field_margin_x),
        ("--near-field-air-top", settings.near_field_air_top),
        ("--near-field-sub-depth", settings.near_field_sub_depth),
        ("--results-root", settings.results_root),
    ):
        _add_value(args, flag, value)
    for flag, value in (
        ("--compute-power-metrics", settings.compute_power_metrics),
        ("--port-use-diffraction-orders", settings.port_use_diffraction_orders),
        ("--lock-near-field-template", settings.mesh_lock_near_field_template),
        ("--generate-png-plots", settings.generate_png_plots),
        ("--unique-output", settings.unique_output),
        ("--port-use-pml", settings.port_use_pml),
    ):
        _add_bool(args, flag, value)
    return args


def _pycharm_args_3d(preset_name: str | None = None) -> list[str]:
    settings = _selected_3d_inputs(preset_name)
    args = [
        "--stage-case",
        str(_setting_value(settings, "stage_case")),
        "--case",
        str(_setting_value(settings, "case")),
    ]
    value_names = (
        "nedelec_degree",
        "visualization_degree",
        "mesh_target_size",
        "mesh_cell_type",
        "mesh_spacing_mode",
        "mesh_refined_size",
        "mesh_refinement_radius",
        "floquet_constraint_mode",
        "lambda0",
        "incident_theta_deg",
        "incident_phi_deg",
        "polarization_kind",
        "divergence_penalty",
        "pml_top_thickness",
        "pml_bottom_thickness",
        "pml_alpha",
        "n_substrate",
        "substrate_material_label",
        "period_x",
        "period_y",
        "air_height",
        "substrate_thickness",
        "n_grating",
        "grating_material_label",
        "validation_role",
        "grating_width_x",
        "grating_width_y",
        "grating_height",
        "scattering_background",
        "stage4_boundary_model",
        "stage4_dtn_order_policy",
        "stage4_dtn_assembly",
        "stage4_pml_outer_bc",
        "diffraction_order_max_m",
        "diffraction_order_max_n",
        "diffraction_sample_count_x",
        "diffraction_sample_count_y",
        "diffraction_top_probe_z",
        "diffraction_bottom_probe_z",
        "diffraction_probe_fraction",
        "diffraction_rayleigh_tol",
        "petsc_direct_solver_profile",
        "results_root",
    )
    for name in value_names:
        _add_value(args, "--" + name.replace("_", "-"), _setting_value(settings, name))
    bool_names = (
        "unique_output",
        "use_floquet_xy",
        "use_pml",
        "diffraction_zero_order_only",
        "diffraction_compute_modal_diagnostic",
        "petsc_ksp_view",
        "petsc_log_view",
        "matrix_diagnostics_assemble_unconstrained",
        "matrix_diagnostics_assemble_only",
    )
    for name in bool_names:
        _add_bool(args, "--" + name.replace("_", "-"), _setting_value(settings, name))
    for key, value in _setting_value(settings, "petsc_extra_options") or ():
        args.extend(["--petsc-extra-option", f"{key}={value}"])
    return args


def preset_cli_args(name: str) -> tuple[str, list[str]]:
    """Return (dimension, CLI args) without importing DOLFINx runners."""

    if name in PRESETS_2D:
        return "2d", _pycharm_args_2d(name)
    if name in PRESETS_3D:
        return "3d", _pycharm_args_3d(name)
    raise SystemExit(
        f"Unknown preset {name!r}. Available: {', '.join(available_preset_names())}"
    )


def main() -> None:
    _ensure_package_importable()
    from src.runners.run_3d_cases import main as run_3d_cases_main
    from src.runners.run_cases import main as run_cases_main

    def dispatch(dimension: str, runner_args: list[str]) -> None:
        (run_3d_cases_main if dimension == "3d" else run_cases_main)(runner_args)

    if len(sys.argv) > 1 and sys.argv[1] == "--list-presets":
        extra = sys.argv[2:]
        if extra not in ([], ["--verbose"]):
            raise SystemExit("--list-presets accepts only the optional --verbose flag")
        print(format_preset_listing(verbose=extra == ["--verbose"]))
        return
    if len(sys.argv) > 2 and sys.argv[1] == "--preset":
        dimension, preset_args = preset_cli_args(sys.argv[2])
        dispatch(dimension, preset_args + sys.argv[3:])
        return
    if USE_PYCHARM_SETTINGS_WHEN_NO_ARGS and len(sys.argv) == 1:
        dispatch(*preset_cli_args(ACTIVE_PYCHARM_PRESET))
        return
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("2d", "3d"):
        dispatch(sys.argv[1].lower(), sys.argv[2:])
        return
    run_cases_main(sys.argv[1:])


if __name__ == "__main__":
    main()
