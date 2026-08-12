from __future__ import annotations

import sys
from dataclasses import dataclass, fields, replace
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.common.config_3d import SimulationConfig3D, target_stage4_config  # noqa: E402
from src.io.preset_migration import MIGRATED_PRESET_DATS  # noqa: E402


@dataclass(frozen=True)
class Stage4GratingInputs3D:
    """Stage-4 flat-layer or block-grating direct-solve inputs."""

    stage_case: str = "stage4_block_grating"
    case: str = "normal"
    incident_theta_deg: float | None = None
    incident_phi_deg: float | None = None
    polarization_kind: str | None = None
    nedelec_degree: int = 2
    nedelec_trace_degree: int | None = None
    nedelec_interior_degree: int | None = None
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
    stage4_full3d_assembly_backend: str = "standard_full"
    stage4_variable_p_cell_degree_plan: str | None = None
    stage4_local_h_refinement_plan: str | None = None
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


STAGE4_GRATING_3D = Stage4GratingInputs3D()
_TARGET_STAGE4_DIRECT_H5 = Stage4GratingInputs3D.from_simulation_config(
    target_stage4_config(degree=2, h_nm=5.0)
)
_TARGET_STAGE4_DIRECT_H3 = Stage4GratingInputs3D.from_simulation_config(
    target_stage4_config(degree=2, h_nm=3.0)
)

PRESETS_3D: dict[str, object] = {
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


@dataclass(frozen=True)
class PresetInfo:
    physical_geometry: str
    discretization: str
    resource_class: str
    evidence_status: str
    purpose: str


PRESET_INFO: dict[str, PresetInfo] = {
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
    """Return migrated aliases and retained research presets in order."""

    return tuple(sorted((*MIGRATED_PRESET_DATS, *PRESETS_3D)))


def preset_info(name: str) -> PresetInfo:
    if name in MIGRATED_PRESET_DATS:
        raise SystemExit(
            f"Preset {name!r} is a .dat alias; inspect {MIGRATED_PRESET_DATS[name]}"
        )
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
        if name in MIGRATED_PRESET_DATS:
            rows.append(
                " | ".join(
                    (
                        name,
                        f"dat={MIGRATED_PRESET_DATS[name]}",
                        "status=migrated_to_dat",
                    )
                )
            )
            continue
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


def _selected_3d_inputs(preset_name: str) -> object:
    name = preset_name
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


def _pycharm_args_3d(preset_name: str) -> list[str]:
    settings = _selected_3d_inputs(preset_name)
    args = [
        "--stage-case",
        str(_setting_value(settings, "stage_case")),
        "--case",
        str(_setting_value(settings, "case")),
    ]
    value_names = (
        "nedelec_degree",
        "nedelec_trace_degree",
        "nedelec_interior_degree",
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
        "stage4_full3d_assembly_backend",
        "stage4_variable_p_cell_degree_plan",
        "stage4_local_h_refinement_plan",
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
    """Return a dat alias or retained 3D runner argv without importing runners."""

    if name in MIGRATED_PRESET_DATS:
        return "dat", [MIGRATED_PRESET_DATS[name]]
    if name in PRESETS_3D:
        return "3d", _pycharm_args_3d(name)
    raise SystemExit(
        f"Unknown preset {name!r}. Available: {', '.join(available_preset_names())}"
    )


def _run_migrated_alias(name: str, extra: list[str]) -> int:
    if extra not in ([], ["--validate-only"], ["--dry-run"]):
        print(
            f"--preset {name} accepts only --validate-only or --dry-run; "
            "use scripts/run_case.py for a normal run",
            file=sys.stderr,
        )
        return 2
    from scripts.run_case import main as run_case_main

    input_path = _PROJECT_ROOT / MIGRATED_PRESET_DATS[name]
    return run_case_main([str(input_path), *extra])


def main(argv: list[str] | None = None) -> int:
    _ensure_package_importable()
    args = list(sys.argv[1:] if argv is None else argv)

    if not args:
        print(
            "Usage: python scripts/run_case.py <case.dat> [--validate-only|--dry-run]",
            file=sys.stderr,
        )
        print(
            "src.main no longer selects an implicit preset; use an explicit .dat input.",
            file=sys.stderr,
        )
        return 2

    if args[0] == "--list-presets":
        extra = args[1:]
        if extra not in ([], ["--verbose"]):
            print(
                "--list-presets accepts only the optional --verbose flag",
                file=sys.stderr,
            )
            return 2
        print(format_preset_listing(verbose=extra == ["--verbose"]))
        return 0

    if args[0] == "--preset":
        if len(args) < 2:
            print("--preset requires a preset name", file=sys.stderr)
            return 2
        name = args[1]
        if name in MIGRATED_PRESET_DATS:
            return _run_migrated_alias(name, args[2:])
        dimension, preset_args = preset_cli_args(name)
        if dimension != "3d":
            return 2
        from src.runners.run_3d_cases import main as run_3d_cases_main

        run_3d_cases_main(preset_args + args[2:])
        return 0

    if args[0].lower() in ("2d", "3d"):
        from src.runners.run_cases import main as run_cases_main
        from src.runners.run_3d_cases import main as run_3d_cases_main

        (run_3d_cases_main if args[0].lower() == "3d" else run_cases_main)(args[1:])
        return 0

    from src.runners.run_cases import main as run_cases_main

    run_cases_main(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
