from __future__ import annotations

import argparse
import json
from pathlib import Path

from mpi4py import MPI

from ..common.config_3d import (
    SimulationConfig3D,
    normal_incidence_airbox_config,
    oblique_incidence_airbox_config,
    project_root,
)
from ..common.output_paths import unique_run_dir
from ..solvers.solve_airbox_maxwell_3d import run_airbox_3d_case
from ..solvers.solve_vector_maxwell import _json_default


def _number_tag(prefix: str, value: object) -> str:
    text = str(value).replace("-", "m").replace(".", "p")
    return f"{prefix}{text}"


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
    if args.visualization_degree is not None:
        updates["visualization_degree"] = args.visualization_degree
    if args.mesh_target_size is not None:
        updates["mesh_target_size"] = args.mesh_target_size
    if args.mesh_cell_type is not None:
        updates["mesh_cell_type"] = args.mesh_cell_type
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
    if args.solver_profile is not None:
        updates["solver_profile"] = args.solver_profile
    if args.solver_rtol is not None:
        updates["solver_rtol"] = args.solver_rtol
    if args.solver_atol is not None:
        updates["solver_atol"] = args.solver_atol
    if args.solver_max_it is not None:
        updates["solver_max_it"] = args.solver_max_it
    if args.solver_monitor is not None:
        updates["solver_monitor"] = args.solver_monitor
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
    if args.period_x is not None:
        updates["period_x"] = args.period_x
    if args.period_y is not None:
        updates["period_y"] = args.period_y
    if args.grating_width_x is not None:
        updates["grating_width_x"] = args.grating_width_x
    if args.grating_width_y is not None:
        updates["grating_width_y"] = args.grating_width_y
    if args.grating_height is not None:
        updates["grating_height"] = args.grating_height
    if args.scattering_background is not None:
        updates["scattering_background"] = args.scattering_background
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
    if args.diffraction_rayleigh_tol is not None:
        updates["diffraction_rayleigh_tol"] = args.diffraction_rayleigh_tol
    return updates


def _stage_defaults(stage_case: str) -> dict[str, object]:
    """Apply the Stage-2 case switches without creating separate config classes."""
    if stage_case == "stage1_airbox":
        return {"stage_case": stage_case, "geometry_kind": "airbox", "use_floquet_xy": False, "use_pml": False}
    if stage_case == "floquet_airbox":
        return {"stage_case": stage_case, "geometry_kind": "airbox", "use_floquet_xy": True, "use_pml": False}
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
            "lambda0": 633.0,
            "period_x": 350.0,
            "period_y": 300.0,
            "z_min": -550.0,
            "z_max": 350.0,
            "interface_z": 0.0,
            "use_floquet_xy": True,
            "use_pml": True,
            "pml_top_thickness": 250.0,
            "pml_bottom_thickness": 250.0,
            "pml_alpha": 5.0,
            "n_substrate": 1.45 + 0.0j,
            "n_grating": 2.0 + 0.0j,
            "grating_width_x": 150.0,
            "grating_width_y": 100.0,
            "grating_height": 150.0,
            "incident_phi_deg": 90.0,
            "polarization_kind": "s",
            "custom_polarization": None,
            "mesh_target_size": 50.0,
            "nedelec_degree": 1,
            "visualization_degree": 1,
            "mesh_cell_type": "auto",
            "floquet_constraint_mode": "auto",
            "solver_profile": "direct",
            "diffraction_zero_order_only": True,
            "diffraction_sample_count_x": 24,
            "diffraction_sample_count_y": 24,
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
            }
        )
        return values
    raise ValueError("Unsupported 3D stage_case.")


def _stage_list(stage_case: str) -> list[str]:
    if stage_case == "stage2_all":
        return ["floquet_airbox", "pml_airbox", "fresnel_interface"]
    if stage_case == "stage4_all":
        return ["stage4_flat_layer_sanity", "stage4_block_grating"]
    return [stage_case]


def _case_configs(case: str, stage_case: str, updates: dict[str, object]) -> list[SimulationConfig3D]:
    """Expand one preset such as "both" into concrete SimulationConfig3D cases."""
    configs: list[SimulationConfig3D] = []
    if case == "normal":
        builders = [normal_incidence_airbox_config]
    elif case == "oblique":
        builders = [oblique_incidence_airbox_config]
    elif case == "both":
        builders = [normal_incidence_airbox_config, oblique_incidence_airbox_config]
    else:
        raise ValueError("case must be 'normal', 'oblique', or 'both'.")

    for stage in _stage_list(stage_case):
        stage_updates = _stage_defaults(stage)
        stage_updates.update(updates)
        stage_updates["stage_case"] = stage
        for builder in builders:
            cfg = builder(**stage_updates)
            cfg.case_name = f"{cfg.case_name}_{stage}"
            configs.append(cfg)
    return configs


def main(argv: list[str] | None = None):
    defaults = SimulationConfig3D()
    parser = argparse.ArgumentParser(description="Run staged 3D Maxwell airbox/Floquet/PML/Fresnel verification.")
    parser.add_argument(
        "--stage-case",
        choices=(
            "stage1_airbox",
            "floquet_airbox",
            "pml_airbox",
            "fresnel_interface",
            "stage2_all",
            "stage4_flat_layer_sanity",
            "stage4_block_grating",
            "stage4_all",
        ),
        default="stage1_airbox",
    )
    parser.add_argument("--case", choices=("normal", "oblique", "both"), default="both")
    parser.add_argument("--nedelec-degree", type=int, default=None)
    parser.add_argument("--visualization-degree", type=int, default=None)
    parser.add_argument("--mesh-target-size", type=float, default=None, help="Target mesh size in nm.")
    parser.add_argument(
        "--mesh-cell-type",
        choices=("auto", "tetrahedron", "hexahedron"),
        default=None,
        help="3D cell type. auto uses hexahedron for Floquet cases and tetrahedron otherwise.",
    )
    parser.add_argument(
        "--floquet-constraint-mode",
        choices=("auto", "topological_edges", "sparse_facet"),
        default=None,
        help=(
            "3D Floquet builder. auto/topological_edges use explicit degree=1 N1curl edge pairing; "
            "sparse_facet is kept as a legacy alias."
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
        "--solver-profile",
        choices=(
            "default",
            "direct",
            "direct_lu",
            "iterative_asm_lu",
            "iterative_asm_lu_overlap2",
            "iterative_asm_ilu",
            "iterative_bjacobi_ilu",
            "iterative_jacobi",
            "iterative_hypre",
        ),
        default=None,
        help="3D linear solver profile. direct is the reliable default benchmark.",
    )
    parser.add_argument("--solver-rtol", type=float, default=None, help="KSP relative tolerance for iterative profiles.")
    parser.add_argument("--solver-atol", type=float, default=None, help="KSP absolute tolerance for iterative profiles.")
    parser.add_argument("--solver-max-it", type=int, default=None, help="KSP maximum iterations for iterative profiles.")
    parser.add_argument(
        "--solver-monitor",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Print PETSc KSP residual monitoring for iterative profiles.",
    )
    parser.add_argument(
        "--unique-output",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Use timestamped results/3D_airbox_* directories.",
    )
    parser.add_argument("--use-floquet-xy", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--use-pml", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--pml-top-thickness", type=float, default=None, help="Top PML thickness in nm.")
    parser.add_argument("--pml-bottom-thickness", type=float, default=None, help="Bottom PML thickness in nm.")
    parser.add_argument("--pml-alpha", type=float, default=None)
    parser.add_argument("--n-substrate", default=None, help="Substrate refractive index for Fresnel stage.")
    parser.add_argument("--n-grating", default=None, help="Rectangular-block grating refractive index for Stage 4.")
    parser.add_argument("--period-x", type=float, default=None, help="3D periodic cell size in x, nm.")
    parser.add_argument("--period-y", type=float, default=None, help="3D periodic cell size in y, nm.")
    parser.add_argument("--grating-width-x", type=float, default=None, help="Stage-4 block width in x, nm.")
    parser.add_argument("--grating-width-y", type=float, default=None, help="Stage-4 block width in y, nm.")
    parser.add_argument("--grating-height", type=float, default=None, help="Stage-4 block height above interface z=0, nm.")
    parser.add_argument(
        "--scattering-background",
        choices=("layered",),
        default=None,
        help="Stage-4 scattered-field background. The first version supports only layered Fresnel background.",
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
    parser.add_argument("--diffraction-rayleigh-tol", type=float, default=None)
    args = parser.parse_args(argv)

    unique_output = defaults.unique_output if args.unique_output is None else args.unique_output
    updates = _config_updates(args)
    configs = _case_configs(args.case, args.stage_case, updates)

    root = project_root()
    results_root = root / "results"
    p = configs[0].nedelec_degree if configs else defaults.nedelec_degree
    h = configs[0].mesh_target_size if configs else defaults.mesh_target_size
    case_tag = "normal_oblique" if args.case == "both" else args.case
    group_parts = ["3D", args.stage_case, case_tag, f"p{p}", _number_tag("h", h)]
    if MPI.COMM_WORLD.size > 1:
        group_parts.append(f"np{MPI.COMM_WORLD.size}")
    run_root = _shared_run_dir(results_root, "_".join(group_parts), unique_output)
    run_root.mkdir(parents=True, exist_ok=True)

    summaries = []
    single_case_output = len(configs) == 1 and unique_output
    for cfg in configs:
        out_dir = run_root if single_case_output else run_root / cfg.case_name
        summaries.append(run_airbox_3d_case(cfg, out_dir))

    if MPI.COMM_WORLD.rank == 0:
        summary_path = run_root / "all_run_summary.json"
        summary_path.write_text(
            json.dumps(summaries, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        print(f"3D airbox results: {run_root}")


if __name__ == "__main__":
    main()
