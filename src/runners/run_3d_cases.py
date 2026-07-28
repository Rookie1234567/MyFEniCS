from __future__ import annotations

import argparse
import json
from pathlib import Path

from mpi4py import MPI

from ..common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND,
    EUV_REFERENCE_WAVELENGTH_NM,
    NUMERICAL_SANITY_ONLY,
    SimulationConfig3D,
    SI_GRATING_INDEX_EUV_13P5_NM,
    SI_GRATING_MATERIAL_LABEL,
    SI_SUBSTRATE_INDEX_EUV_13P5_NM,
    SI_SUBSTRATE_MATERIAL_LABEL,
    STANDARD_FULL_ASSEMBLY_BACKEND,
    normal_incidence_airbox_config,
    oblique_incidence_airbox_config,
    project_root,
)
from ..common.output_paths import unique_run_dir
from ..solvers.solve_maxwell_3d_stage_1_airbox import (
    STAGE1_CASES,
    run_stage1_airbox_3d_case,
)
from ..solvers.solve_maxwell_3d_stage_2a_floquet_airbox import (
    STAGE2A_CASES,
    run_stage2a_floquet_airbox_3d_case,
)
from ..solvers.solve_maxwell_3d_stage_2b_pml_airbox import (
    STAGE2B_CASES,
    run_stage2b_pml_airbox_3d_case,
)
from ..solvers.solve_maxwell_3d_stage_2c_fresnel_interface import (
    STAGE2C_CASES,
    run_stage2c_fresnel_interface_3d_case,
)
from ..solvers.solve_maxwell_3d_stage_4a_flat_layer_sanity import (
    STAGE4A_CASES,
    run_stage4a_flat_layer_sanity_3d_case,
)
from ..solvers.solve_maxwell_3d_stage_4b_block_grating import (
    STAGE4B_CASES,
    run_stage4b_block_grating_3d_case,
)
from ..solvers.solve_vector_maxwell import _json_default


def _number_tag(prefix: str, value: object) -> str:
    text = str(value).replace("-", "m").replace(".", "p")
    return f"{prefix}{text}"


def _parse_value(text: str) -> object:
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        if any(ch in text for ch in (".", "e", "E")):
            return float(text)
        return int(text)
    except ValueError:
        return text


def _parse_petsc_option_tokens(tokens: list[str]) -> dict[str, object]:
    """Parse trailing PETSc-style options accepted by parse_known_args.

    Examples:
      -ksp_view -log_view
      -pc_factor_mat_solver_type mumps
      -mat_mumps_icntl_22 1
    """

    options: dict[str, object] = {}
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if not token.startswith("-"):
            raise ValueError(
                f"Unexpected non-option token after PETSc options: {token!r}"
            )
        key = token.lstrip("-")
        if not key:
            raise ValueError("Empty PETSc option name.")
        if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
            options[key] = _parse_value(tokens[i + 1])
            i += 2
        else:
            options[key] = True
            i += 1
    return options


def _parse_petsc_extra_option(values: list[str] | None) -> dict[str, object]:
    options: dict[str, object] = {}
    for item in values or []:
        text = item.strip()
        if not text:
            continue
        if "=" in text:
            key, value = text.split("=", 1)
            options[key.lstrip("-")] = _parse_value(value)
        else:
            options[text.lstrip("-")] = True
    return options


def _run_stage_config(cfg: SimulationConfig3D, out_dir: Path) -> dict[str, object]:
    """Dispatch one 3D config to the stage-specific solver entry."""
    if cfg.stage_case in STAGE1_CASES:
        return run_stage1_airbox_3d_case(cfg, out_dir)
    if cfg.stage_case in STAGE2A_CASES:
        return run_stage2a_floquet_airbox_3d_case(cfg, out_dir)
    if cfg.stage_case in STAGE2B_CASES:
        return run_stage2b_pml_airbox_3d_case(cfg, out_dir)
    if cfg.stage_case in STAGE2C_CASES:
        return run_stage2c_fresnel_interface_3d_case(cfg, out_dir)
    if cfg.stage_case in STAGE4A_CASES:
        return run_stage4a_flat_layer_sanity_3d_case(cfg, out_dir)
    if cfg.stage_case in STAGE4B_CASES:
        return run_stage4b_block_grating_3d_case(cfg, out_dir)
    raise ValueError(f"Unsupported 3D stage_case={cfg.stage_case!r}.")


def _shared_run_dir(results_root: Path, base_name: str, unique_output: bool) -> Path:
    """Choose one output directory on rank0 and broadcast it to all MPI ranks."""
    comm = MPI.COMM_WORLD
    if comm.rank == 0:
        chosen = unique_run_dir(results_root, base_name, enabled=unique_output)
    else:
        chosen = None
    return Path(comm.bcast(str(chosen), root=0))


def _config_updates(args) -> dict[str, object]:
    updates: dict[str, object] = {}
    if args.stage_case is not None:
        updates["stage_case"] = args.stage_case
    if args.nedelec_degree is not None:
        updates["nedelec_degree"] = args.nedelec_degree
    if args.nedelec_trace_degree is not None:
        updates["nedelec_trace_degree"] = args.nedelec_trace_degree
    if args.nedelec_interior_degree is not None:
        updates["nedelec_interior_degree"] = args.nedelec_interior_degree
    if args.visualization_degree is not None:
        updates["visualization_degree"] = args.visualization_degree
    if args.mesh_target_size is not None:
        updates["mesh_target_size"] = args.mesh_target_size
    if args.mesh_cell_type is not None:
        updates["mesh_cell_type"] = args.mesh_cell_type
    if args.mesh_spacing_mode is not None:
        updates["mesh_spacing_mode"] = args.mesh_spacing_mode
    if args.mesh_refined_size is not None:
        updates["mesh_refined_size"] = args.mesh_refined_size
    if args.mesh_refinement_radius is not None:
        updates["mesh_refinement_radius"] = args.mesh_refinement_radius
    if args.floquet_constraint_mode is not None:
        updates["floquet_constraint_mode"] = args.floquet_constraint_mode
    if args.lambda0 is not None:
        updates["lambda0"] = args.lambda0
    if args.incident_theta_deg is not None:
        updates["incident_theta_deg"] = args.incident_theta_deg
    if args.incident_phi_deg is not None:
        updates["incident_phi_deg"] = args.incident_phi_deg
    if args.polarization_kind is not None:
        updates["polarization_kind"] = args.polarization_kind
        if args.polarization_kind != "custom":
            updates["custom_polarization"] = None
    if args.divergence_penalty is not None:
        updates["divergence_penalty"] = args.divergence_penalty
    if args.use_floquet_xy is not None:
        updates["use_floquet_xy"] = args.use_floquet_xy
    if args.use_pml is not None:
        updates["use_pml"] = args.use_pml
    if args.pml_top_thickness is not None:
        updates["pml_top_thickness"] = args.pml_top_thickness
    if args.pml_bottom_thickness is not None:
        updates["pml_bottom_thickness"] = args.pml_bottom_thickness
    if args.pml_alpha is not None:
        updates["pml_alpha"] = args.pml_alpha
    if args.n_substrate is not None:
        updates["n_substrate"] = complex(args.n_substrate)
    if args.n_grating is not None:
        updates["n_grating"] = complex(args.n_grating)
    if args.substrate_material_label is not None:
        updates["substrate_material_label"] = args.substrate_material_label
    if args.grating_material_label is not None:
        updates["grating_material_label"] = args.grating_material_label
    if args.validation_role is not None:
        updates["validation_role"] = args.validation_role
    if args.period_x is not None:
        updates["period_x"] = args.period_x
    if args.period_y is not None:
        updates["period_y"] = args.period_y
    if args.air_height is not None:
        updates["air_height"] = args.air_height
        updates["z_max"] = args.air_height
    if args.substrate_thickness is not None:
        updates["substrate_thickness"] = args.substrate_thickness
        updates["z_min"] = -args.substrate_thickness
    if args.grating_width_x is not None:
        updates["grating_width_x"] = args.grating_width_x
    if args.grating_width_y is not None:
        updates["grating_width_y"] = args.grating_width_y
    if args.grating_height is not None:
        updates["grating_height"] = args.grating_height
    if args.scattering_background is not None:
        updates["scattering_background"] = args.scattering_background
    if args.stage4_boundary_model is not None:
        updates["stage4_boundary_model"] = args.stage4_boundary_model
        if args.stage4_boundary_model in {"robin0", "dtn_port"}:
            updates["use_pml"] = False
            updates["pml_top_thickness"] = 0.0
            updates["pml_bottom_thickness"] = 0.0
        if args.stage4_boundary_model == "pml":
            updates["use_pml"] = True
    if args.stage4_dtn_order_policy is not None:
        updates["stage4_dtn_order_policy"] = args.stage4_dtn_order_policy
    if args.stage4_dtn_assembly is not None:
        updates["stage4_dtn_assembly"] = args.stage4_dtn_assembly
    if args.stage4_full3d_assembly_backend is not None:
        updates["stage4_full3d_assembly_backend"] = (
            args.stage4_full3d_assembly_backend
        )
    if args.stage4_variable_p_cell_degree_plan is not None:
        updates["stage4_variable_p_cell_degree_plan"] = (
            args.stage4_variable_p_cell_degree_plan
        )
    if args.stage4_local_h_refinement_plan is not None:
        updates["stage4_local_h_refinement_plan"] = (
            args.stage4_local_h_refinement_plan
        )
    if args.stage4_pml_outer_bc is not None:
        updates["stage4_pml_outer_bc"] = args.stage4_pml_outer_bc
    if args.diffraction_zero_order_only is not None:
        updates["diffraction_zero_order_only"] = args.diffraction_zero_order_only
    if args.diffraction_order_max_m is not None:
        updates["diffraction_order_max_m"] = args.diffraction_order_max_m
    if args.diffraction_order_max_n is not None:
        updates["diffraction_order_max_n"] = args.diffraction_order_max_n
    if args.diffraction_sample_count_x is not None:
        updates["diffraction_sample_count_x"] = args.diffraction_sample_count_x
    if args.diffraction_sample_count_y is not None:
        updates["diffraction_sample_count_y"] = args.diffraction_sample_count_y
    if args.diffraction_top_probe_z is not None:
        updates["diffraction_top_probe_z"] = args.diffraction_top_probe_z
    if args.diffraction_bottom_probe_z is not None:
        updates["diffraction_bottom_probe_z"] = args.diffraction_bottom_probe_z
    if args.diffraction_probe_fraction is not None:
        updates["diffraction_probe_fraction"] = args.diffraction_probe_fraction
    if args.diffraction_compute_modal_diagnostic is not None:
        updates["diffraction_compute_modal_diagnostic"] = (
            args.diffraction_compute_modal_diagnostic
        )
    if args.diffraction_rayleigh_tol is not None:
        updates["diffraction_rayleigh_tol"] = args.diffraction_rayleigh_tol
    if args.full3d_reference_export is not None:
        updates["full3d_reference_export"] = args.full3d_reference_export
    if args.full3d_reference_plane_z is not None:
        updates["full3d_reference_plane_z"] = tuple(args.full3d_reference_plane_z)
    if args.full3d_reference_sample_count_x is not None:
        updates["full3d_reference_sample_count_x"] = args.full3d_reference_sample_count_x
    if args.full3d_reference_sample_count_y is not None:
        updates["full3d_reference_sample_count_y"] = args.full3d_reference_sample_count_y
    if args.petsc_direct_solver_profile is not None:
        updates["petsc_direct_solver_profile"] = args.petsc_direct_solver_profile
    if args.petsc_ksp_view is not None:
        updates["petsc_ksp_view"] = args.petsc_ksp_view
    if args.petsc_log_view is not None:
        updates["petsc_log_view"] = args.petsc_log_view
    if args.matrix_diagnostics_assemble_unconstrained is not None:
        updates["matrix_diagnostics_assemble_unconstrained"] = (
            args.matrix_diagnostics_assemble_unconstrained
        )
    if args.matrix_diagnostics_assemble_only is not None:
        updates["matrix_diagnostics_assemble_only"] = (
            args.matrix_diagnostics_assemble_only
        )
    petsc_extra_options = {}
    petsc_extra_options.update(getattr(args, "petsc_unknown_options", {}))
    petsc_extra_options.update(_parse_petsc_extra_option(args.petsc_extra_option))
    if petsc_extra_options:
        updates["petsc_extra_options"] = petsc_extra_options
        if "ksp_view" in petsc_extra_options:
            updates["petsc_ksp_view"] = True
        if "log_view" in petsc_extra_options:
            updates["petsc_log_view"] = True
    return updates


def _stage_defaults(stage_case: str) -> dict[str, object]:
    """Apply the Stage-2 case switches without creating separate config classes."""
    if stage_case == "stage1_airbox":
        return {
            "stage_case": stage_case,
            "geometry_kind": "airbox",
            "use_floquet_xy": False,
            "use_pml": False,
        }
    if stage_case == "floquet_airbox":
        return {
            "stage_case": stage_case,
            "geometry_kind": "airbox",
            "use_floquet_xy": True,
            "use_pml": False,
        }
    if stage_case == "pml_airbox":
        return {
            "stage_case": stage_case,
            "geometry_kind": "airbox",
            "use_floquet_xy": True,
            "use_pml": True,
            "pml_top_thickness": 250.0,
            "pml_bottom_thickness": 250.0,
        }
    if stage_case == "fresnel_interface":
        return {
            "stage_case": stage_case,
            "geometry_kind": "fresnel_interface",
            "use_floquet_xy": True,
            "use_pml": True,
            "pml_top_thickness": 250.0,
            "pml_bottom_thickness": 250.0,
            "n_substrate": 1.45 + 0.0j,
            "polarization_kind": "s",
            "custom_polarization": None,
        }
    if stage_case == "stage4_block_grating":
        return {
            "stage_case": stage_case,
            "geometry_kind": "rectangular_block_grating",
            "scattering_background": "layered",
            "stage4_boundary_model": "dtn_port",
            "stage4_dtn_order_policy": "auto_propagating",
            "stage4_dtn_assembly": "auxiliary",
            "stage4_pml_outer_bc": "natural",
            "lambda0": EUV_REFERENCE_WAVELENGTH_NM,
            "period_x": 100.0,
            "period_y": 100.0,
            "air_height": 100.0,
            "substrate_thickness": 50.0,
            "z_min": -50.0,
            "z_max": 100.0,
            "interface_z": 0.0,
            "use_floquet_xy": True,
            "use_pml": False,
            "pml_top_thickness": 0.0,
            "pml_bottom_thickness": 0.0,
            "pml_alpha": 5.0,
            "n_substrate": SI_SUBSTRATE_INDEX_EUV_13P5_NM,
            "n_grating": SI_GRATING_INDEX_EUV_13P5_NM,
            "substrate_material_label": SI_SUBSTRATE_MATERIAL_LABEL,
            "grating_material_label": SI_GRATING_MATERIAL_LABEL,
            "validation_role": NUMERICAL_SANITY_ONLY,
            "grating_width_x": 50.0,
            "grating_width_y": 50.0,
            "grating_height": 50.0,
            "incident_phi_deg": 0.0,
            "polarization_kind": "s",
            "custom_polarization": None,
            "mesh_target_size": 5.0,
            "mesh_spacing_mode": "auto",
            "mesh_refined_size": None,
            "mesh_refinement_radius": None,
            "nedelec_degree": 1,
            "visualization_degree": 1,
            "mesh_cell_type": "auto",
            "floquet_constraint_mode": "auto",
            "diffraction_zero_order_only": False,
            "diffraction_sample_count_x": 32,
            "diffraction_sample_count_y": 32,
            "diffraction_probe_fraction": 0.75,
            "diffraction_compute_modal_diagnostic": False,
        }
    if stage_case == "stage4_flat_layer_sanity":
        values = _stage_defaults("stage4_block_grating")
        values.update(
            {
                "stage_case": stage_case,
                "grating_width_x": 0.0,
                "grating_width_y": 0.0,
                "grating_height": 0.0,
                "n_grating": 1.0 + 0.0j,
                "grating_material_label": None,
            }
        )
        return values
    raise ValueError("Unsupported 3D stage_case.")


def _case_configs(
    case: str, stage_case: str, updates: dict[str, object]
) -> list[SimulationConfig3D]:
    """Create exactly one SimulationConfig3D for one explicit stage/case pair."""
    if case == "normal":
        builder = normal_incidence_airbox_config
    elif case == "oblique":
        builder = oblique_incidence_airbox_config
    else:
        raise ValueError("case must be 'normal' or 'oblique'.")

    stage_updates = _stage_defaults(stage_case)
    stage_updates.update(updates)
    stage_updates["stage_case"] = stage_case
    cfg = builder(**stage_updates)
    cfg.case_name = f"{cfg.case_name}_{stage_case}"
    return [cfg]


def main(argv: list[str] | None = None):
    defaults = SimulationConfig3D()
    parser = argparse.ArgumentParser(
        description="Run one explicit staged 3D Maxwell case."
    )
    parser.add_argument(
        "--stage-case",
        choices=(
            "stage1_airbox",
            "floquet_airbox",
            "pml_airbox",
            "fresnel_interface",
            "stage4_flat_layer_sanity",
            "stage4_block_grating",
        ),
        default="stage1_airbox",
    )
    parser.add_argument("--case", choices=("normal", "oblique"), default="normal")
    parser.add_argument("--nedelec-degree", type=int, default=None)
    parser.add_argument("--nedelec-trace-degree", type=int, default=None)
    parser.add_argument("--nedelec-interior-degree", type=int, default=None)
    parser.add_argument("--visualization-degree", type=int, default=None)
    parser.add_argument(
        "--mesh-target-size", type=float, default=None, help="Target mesh size in nm."
    )
    parser.add_argument(
        "--mesh-cell-type",
        choices=("auto", "tetrahedron", "hexahedron"),
        default=None,
        help="3D cell type. auto uses hexahedron for Floquet cases and tetrahedron otherwise.",
    )
    parser.add_argument(
        "--mesh-spacing-mode",
        choices=("auto", "uniform_strict", "boundary_fitted", "local_refined"),
        default=None,
        help=(
            "Stage-4 hexa spacing. auto keeps uniform meshes when material planes align, "
            "otherwise inserts fitted material planes."
        ),
    )
    parser.add_argument(
        "--mesh-refined-size",
        type=float,
        default=None,
        help="Stage-4 local_refined target size near the grating and interface, in nm.",
    )
    parser.add_argument(
        "--mesh-refinement-radius",
        type=float,
        default=None,
        help="Stage-4 local_refined band radius around the grating/interface, in nm.",
    )
    parser.add_argument(
        "--floquet-constraint-mode",
        choices=("auto", "topological_edges", "sparse_facet", "topological_trace_p2"),
        default=None,
        help=(
            "3D Floquet builder. auto selects p=1 edge pairing or p=2 trace pairing; "
            "sparse_facet is kept as a legacy p=1 alias."
        ),
    )
    parser.add_argument("--lambda0", type=float, default=None)
    parser.add_argument(
        "--incident-theta-deg",
        type=float,
        default=None,
        help="3D polar incidence angle: tilt away from downward -z propagation.",
    )
    parser.add_argument(
        "--incident-phi-deg",
        type=float,
        default=None,
        help="3D azimuth angle in the x-y plane.",
    )
    parser.add_argument(
        "--polarization-kind",
        choices=("s", "p", "custom"),
        default=None,
        help="3D incident polarization. Stage-1 normal incidence uses custom Ex by default.",
    )
    parser.add_argument(
        "--divergence-penalty",
        type=float,
        default=None,
        help="Optional grad-div stabilization for experimental 3D H(curl) Maxwell diagnostics.",
    )
    parser.add_argument(
        "--unique-output",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Use timestamped results/3D_airbox_* directories.",
    )
    parser.add_argument(
        "--results-root",
        default=None,
        help=(
            "Output root override. The ordinary default remains <repository>/results; "
            "benchmark scripts use benchmarks/artifacts explicitly."
        ),
    )
    parser.add_argument(
        "--use-floquet-xy", action=argparse.BooleanOptionalAction, default=None
    )
    parser.add_argument(
        "--use-pml", action=argparse.BooleanOptionalAction, default=None
    )
    parser.add_argument(
        "--pml-top-thickness", type=float, default=None, help="Top PML thickness in nm."
    )
    parser.add_argument(
        "--pml-bottom-thickness",
        type=float,
        default=None,
        help="Bottom PML thickness in nm.",
    )
    parser.add_argument("--pml-alpha", type=float, default=None)
    parser.add_argument(
        "--n-substrate",
        default=None,
        help="Substrate refractive index for Fresnel stage.",
    )
    parser.add_argument(
        "--n-grating",
        default=None,
        help="Rectangular-block grating refractive index for Stage 4.",
    )
    parser.add_argument(
        "--substrate-material-label",
        default=None,
        help="Human-readable substrate material label.",
    )
    parser.add_argument(
        "--grating-material-label",
        default=None,
        help="Human-readable grating material label.",
    )
    parser.add_argument(
        "--validation-role",
        default=None,
        help="Validation role, e.g. numerical_sanity_only or physical_benchmark_candidate.",
    )
    parser.add_argument(
        "--period-x", type=float, default=None, help="3D periodic cell size in x, nm."
    )
    parser.add_argument(
        "--period-y", type=float, default=None, help="3D periodic cell size in y, nm."
    )
    parser.add_argument(
        "--air-height",
        type=float,
        default=None,
        help="Physical air height above z=0 in nm.",
    )
    parser.add_argument(
        "--substrate-thickness",
        type=float,
        default=None,
        help="Physical substrate thickness below z=0 in nm.",
    )
    parser.add_argument(
        "--grating-width-x",
        type=float,
        default=None,
        help="Stage-4 block width in x, nm.",
    )
    parser.add_argument(
        "--grating-width-y",
        type=float,
        default=None,
        help="Stage-4 block width in y, nm.",
    )
    parser.add_argument(
        "--grating-height",
        type=float,
        default=None,
        help="Stage-4 block height above interface z=0, nm.",
    )
    parser.add_argument(
        "--scattering-background",
        choices=("layered",),
        default=None,
        help="Stage-4 scattered-field background. The first version supports only layered Fresnel background.",
    )
    parser.add_argument(
        "--stage4-boundary-model",
        choices=("dtn_port", "pml", "robin0"),
        default=None,
        help=(
            "Stage-4 vertical truncation. 'dtn_port' is the total-field Fourier-DtN port; "
            "'pml' and 'robin0' are diagnostic legacy paths."
        ),
    )
    parser.add_argument(
        "--stage4-dtn-order-policy",
        choices=("auto_propagating", "zero_order", "manual"),
        default=None,
        help="Stage-4 DtN order selection. auto_propagating includes every propagating top/bottom order.",
    )
    parser.add_argument(
        "--stage4-dtn-assembly",
        choices=("auxiliary",),
        default=None,
        help="Stage-4 DtN assembly. 3D v1 supports only sparse auxiliary modal unknowns.",
    )
    parser.add_argument(
        "--stage4-full3d-assembly-backend",
        choices=(
            STANDARD_FULL_ASSEMBLY_BACKEND,
            ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
            ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND,
        ),
        default=None,
        help=(
            "Stage-4 Full3D assembly backend. The ordinary default is "
            "standard_full; assembly_time_static_condensed is qualified only "
            "for the fixed affine rectangular hexahedral target."
        ),
    )
    parser.add_argument(
        "--stage4-variable-p-cell-degree-plan",
        default=None,
        help=(
            "Task035d geometry-bound p4/p5/p6 cell-plan JSON. It is "
            "required only by assembly_time_variable_p_condensed."
        ),
    )
    parser.add_argument(
        "--stage4-local-h-refinement-plan",
        default=None,
        help=(
            "Task035d geometry-bound balanced local-h plan JSON. It is an "
            "explicit opt-in for assembly_time_variable_p_condensed."
        ),
    )
    parser.add_argument(
        "--stage4-pml-outer-bc",
        choices=("natural", "zero_tangential"),
        default=None,
        help="Outer z-face treatment for Stage-4 PML. Default natural leaves the PML truncation visible.",
    )
    parser.add_argument(
        "--diffraction-zero-order-only",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Use only the (0,0) order in Stage-4 diffraction postprocess.",
    )
    parser.add_argument("--diffraction-order-max-m", type=int, default=None)
    parser.add_argument("--diffraction-order-max-n", type=int, default=None)
    parser.add_argument("--diffraction-sample-count-x", type=int, default=None)
    parser.add_argument("--diffraction-sample-count-y", type=int, default=None)
    parser.add_argument("--diffraction-top-probe-z", type=float, default=None)
    parser.add_argument("--diffraction-bottom-probe-z", type=float, default=None)
    parser.add_argument("--diffraction-probe-fraction", type=float, default=None)
    parser.add_argument(
        "--diffraction-compute-modal-diagnostic",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Compute the old E/H modal-fit diagnostic. Default is off because EUV cells may have many orders.",
    )
    parser.add_argument("--diffraction-rayleigh-tol", type=float, default=None)
    parser.add_argument(
        "--full3d-reference-export",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Export small structured complex E/H samples for full-3D reference validation.",
    )
    parser.add_argument(
        "--full3d-reference-plane-z",
        type=float,
        nargs="+",
        default=None,
        help="Physical z planes in nm for the opt-in full-3D reference export.",
    )
    parser.add_argument("--full3d-reference-sample-count-x", type=int, default=None)
    parser.add_argument("--full3d-reference-sample-count-y", type=int, default=None)
    parser.add_argument(
        "--petsc-direct-solver-profile",
        choices=("default", "mumps_ooc", "mumps_blr"),
        default=None,
        help=(
            "Direct-factorization profile: default LU, MUMPS out-of-core LU, or "
            "MUMPS BLR compressed LU. BLR is not the qualified iterative runtime."
        ),
    )
    parser.add_argument(
        "--petsc-ksp-view", action=argparse.BooleanOptionalAction, default=None
    )
    parser.add_argument(
        "--petsc-log-view", action=argparse.BooleanOptionalAction, default=None
    )
    parser.add_argument(
        "--petsc-extra-option",
        action="append",
        default=None,
        help="Extra PETSc option as key=value or key. Also accepts trailing PETSc tokens such as -ksp_view -log_view.",
    )
    parser.add_argument(
        "--matrix-diagnostics-assemble-unconstrained",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Also assemble the pre-MPC matrix for nnz comparison. This increases peak memory.",
    )
    parser.add_argument(
        "--matrix-diagnostics-assemble-only",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Assemble the final linear system and write diagnostics, but skip LU factorization/solve.",
    )
    args, petsc_unknown = parser.parse_known_args(argv)
    args.petsc_unknown_options = _parse_petsc_option_tokens(petsc_unknown)

    unique_output = (
        defaults.unique_output if args.unique_output is None else args.unique_output
    )
    updates = _config_updates(args)
    updates["unique_output"] = bool(unique_output)
    configs = _case_configs(args.case, args.stage_case, updates)

    root = project_root()
    results_root = Path(args.results_root) if args.results_root else root / "results"
    if not results_root.is_absolute():
        results_root = root / results_root
    p = configs[0].nedelec_degree if configs else defaults.nedelec_degree
    h = configs[0].mesh_target_size if configs else defaults.mesh_target_size
    case_tag = args.case
    group_parts = ["3D", args.stage_case, case_tag, f"p{p}", _number_tag("h", h)]
    if MPI.COMM_WORLD.size > 1:
        group_parts.append(f"np{MPI.COMM_WORLD.size}")
    run_root = _shared_run_dir(results_root, "_".join(group_parts), unique_output)
    run_root.mkdir(parents=True, exist_ok=True)
    if MPI.COMM_WORLD.rank == 0:
        print(f"3D case output directory: {run_root}")

    summaries = []
    single_case_output = len(configs) == 1 and unique_output
    for cfg in configs:
        out_dir = run_root if single_case_output else run_root / cfg.case_name
        summaries.append(_run_stage_config(cfg, out_dir))

    if MPI.COMM_WORLD.rank == 0:
        summary_path = run_root / "all_run_summary.json"
        summary_path.write_text(
            json.dumps(summaries, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        print(f"3D case results: {run_root}")


if __name__ == "__main__":
    main()
