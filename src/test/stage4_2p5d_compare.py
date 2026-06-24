from __future__ import annotations

import argparse
import json
from pathlib import Path

from mpi4py import MPI

from ..common.config import SimulationConfig
from ..common.config_3d import SimulationConfig3D, project_root
from ..common.output_paths import unique_run_dir
from ..solvers.solve_maxwell_3d_stage_4_grating import run_stage4_grating_3d_case
from ..solvers.solve_vector_maxwell import _json_default, run_case as run_2d_tm_case


def _shared_run_dir(base_name: str, unique_output: bool) -> Path:
    comm = MPI.COMM_WORLD
    if comm.rank == 0:
        chosen = unique_run_dir(project_root() / "results", base_name, enabled=unique_output)
    else:
        chosen = None
    return Path(comm.bcast(str(chosen), root=0))


def build_2d_reference_config(mesh_target_size: float, nedelec_degree: int) -> SimulationConfig:
    """Return the 2D TM scattered benchmark matching the 3D y-extruded cell."""

    return SimulationConfig(
        case_name="stage4_2p5d_reference_2d_tm",
        calculation_method="scattered",
        constraint_backend="mpc_official",
        scattering_background="layered",
        polarization_type="TM",
        period_x=350.0,
        air_height=350.0,
        substrate_thickness=550.0,
        pml_top_thickness=250.0,
        pml_bottom_thickness=250.0,
        grating_width=150.0,
        grating_height=150.0,
        lambda0=633.0,
        incident_angle_deg=0.0,
        n_air=1.0 + 0.0j,
        n_substrate=1.45 + 0.0j,
        n_grating=2.0 + 0.0j,
        use_pml=True,
        nedelec_degree=nedelec_degree,
        visualization_degree=1,
        mesh_target_size=mesh_target_size,
        pml_alpha=5.0,
        diffraction_order_count=0,
        power_probe_num_points=256,
        unique_output=True,
    )


def build_3d_extruded_config(
    mesh_target_size: float,
    nedelec_degree: int,
    stage4_boundary_model: str = "pml",
) -> SimulationConfig3D:
    """Return a Stage-4 cell that is invariant in y and should match the 2D TM case."""
    use_pml = stage4_boundary_model == "pml"

    return SimulationConfig3D(
        case_name="stage4_2p5d_extruded_3d",
        stage_case="stage4_block_grating",
        geometry_kind="rectangular_block_grating",
        scattering_background="layered",
        lambda0=633.0,
        period_x=350.0,
        period_y=100.0,
        z_min=-550.0,
        z_max=350.0,
        interface_z=0.0,
        use_floquet_xy=True,
        use_pml=use_pml,
        pml_top_thickness=250.0 if use_pml else 0.0,
        pml_bottom_thickness=250.0 if use_pml else 0.0,
        pml_alpha=5.0,
        stage4_boundary_model=stage4_boundary_model,
        n_air=1.0 + 0.0j,
        n_substrate=1.45 + 0.0j,
        n_grating=2.0 + 0.0j,
        grating_width_x=150.0,
        grating_width_y=100.0,
        grating_height=150.0,
        incident_theta_deg=0.0,
        incident_phi_deg=90.0,
        polarization_kind="s",
        custom_polarization=None,
        mesh_target_size=mesh_target_size,
        nedelec_degree=nedelec_degree,
        visualization_degree=1,
        mesh_cell_type="auto",
        floquet_constraint_mode="auto",
        diffraction_zero_order_only=True,
        diffraction_sample_count_x=24,
        diffraction_sample_count_y=8,
        unique_output=True,
    )


def _rt_from_2d(summary: dict[str, object]) -> tuple[float | None, float | None, float | None]:
    metrics = summary.get("power_metrics", {})
    if not isinstance(metrics, dict):
        return None, None, None
    return metrics.get("R_total"), metrics.get("T_total"), metrics.get("R_plus_T")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Compare Stage-4 y-extruded 3D cell against the 2D TM solver.")
    parser.add_argument("--mesh-target-size", type=float, default=50.0)
    parser.add_argument("--nedelec-degree", type=int, default=1)
    parser.add_argument(
        "--stage4-boundary-model",
        choices=("pml", "robin0"),
        default="pml",
        help="3D Stage-4 boundary model. 'pml' is the official 2D-like path; 'robin0' is diagnostic.",
    )
    parser.add_argument("--unique-output", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args(argv)

    comm = MPI.COMM_WORLD
    out_dir = _shared_run_dir(
        f"stage4_2p5d_compare_h{str(args.mesh_target_size).replace('.', 'p')}_p{args.nedelec_degree}_np{comm.size}",
        args.unique_output,
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg_2d = build_2d_reference_config(args.mesh_target_size, args.nedelec_degree)
    cfg_3d = build_3d_extruded_config(
        args.mesh_target_size,
        args.nedelec_degree,
        args.stage4_boundary_model,
    )

    summary_2d = run_2d_tm_case(cfg_2d, out_dir / "reference_2d_tm", constraint_backend="mpc_official")
    summary_3d = run_stage4_grating_3d_case(cfg_3d, out_dir / "extruded_3d_stage4")

    r2d, t2d, rt2d = _rt_from_2d(summary_2d)
    r3d = summary_3d.get("R_total")
    t3d = summary_3d.get("T_total")
    rt3d = summary_3d.get("R_plus_T")
    comparison = {
        "mesh_target_size": args.mesh_target_size,
        "nedelec_degree": args.nedelec_degree,
        "mpi_size": comm.size,
        "stage4_boundary_model": args.stage4_boundary_model,
        "stage4_boundary_model_note": (
            "pml is comparable to the 2D scattered PML flow; robin0 is a 3D diagnostic and is not expected to match the 2D PML reference exactly."
        ),
        "reference_2d_dir": str(out_dir / "reference_2d_tm"),
        "extruded_3d_dir": str(out_dir / "extruded_3d_stage4"),
        "R_2d": r2d,
        "T_2d": t2d,
        "R_plus_T_2d": rt2d,
        "R_3d": r3d,
        "T_3d": t3d,
        "R_plus_T_3d": rt3d,
        "R_3d_minus_2d": None if r2d is None or r3d is None else float(r3d - r2d),
        "T_3d_minus_2d": None if t2d is None or t3d is None else float(t3d - t2d),
        "R_plus_T_3d_minus_2d": None if rt2d is None or rt3d is None else float(rt3d - rt2d),
        "stage4_official_result": summary_3d.get("official_result"),
        "stage4_case_status": summary_3d.get("case_status"),
        "stage4_energy_balance_pass": summary_3d.get("stage4_energy_balance_pass"),
        "stage4_energy_balance_excess": summary_3d.get("stage4_energy_balance_excess"),
        "stage4_max_abs_Ey": summary_3d.get("max_abs_Ey"),
        "stage4_max_abs_E_sca_Ey": summary_3d.get("max_abs_E_sca_Ey"),
        "stage4_max_abs_Ex": summary_3d.get("max_abs_Ex"),
        "stage4_max_abs_Ez": summary_3d.get("max_abs_Ez"),
        "stage4_strong_z_boundary_dirichlet_enabled": summary_3d.get("strong_z_boundary_dirichlet_enabled"),
        "stage4_outer_pml_zero_tangential_e_bc": summary_3d.get("stage4_outer_pml_zero_tangential_e_bc"),
        "stage4_background_zeroed_in_pml_for_output": summary_3d.get("background_zeroed_in_pml_for_stage4_output"),
        "stage4_pml_metric_field": summary_3d.get("pml_metric_field"),
        "stage4_pml_scattered_decay_ratio_top": summary_3d.get("pml_scattered_decay_ratio_top"),
        "stage4_pml_scattered_decay_ratio_bottom": summary_3d.get("pml_scattered_decay_ratio_bottom"),
    }
    if comm.rank == 0:
        (out_dir / "stage4_2p5d_comparison.json").write_text(
            json.dumps(comparison, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        print(json.dumps(comparison, ensure_ascii=False, indent=2, default=_json_default))


if __name__ == "__main__":
    main()
