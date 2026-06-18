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
    comm = MPI.COMM_WORLD
    if comm.rank == 0:
        chosen = unique_run_dir(results_root, base_name, enabled=unique_output)
    else:
        chosen = None
    return Path(comm.bcast(str(chosen), root=0))


def _config_updates(args) -> dict[str, object]:
    updates: dict[str, object] = {}
    if args.nedelec_degree is not None:
        updates["nedelec_degree"] = args.nedelec_degree
    if args.visualization_degree is not None:
        updates["visualization_degree"] = args.visualization_degree
    if args.mesh_target_size is not None:
        updates["mesh_target_size"] = args.mesh_target_size
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
    return updates


def _case_configs(case: str, updates: dict[str, object]) -> list[SimulationConfig3D]:
    if case == "normal":
        return [normal_incidence_airbox_config(**updates)]
    if case == "oblique":
        return [oblique_incidence_airbox_config(**updates)]
    if case == "both":
        return [normal_incidence_airbox_config(**updates), oblique_incidence_airbox_config(**updates)]
    raise ValueError("case must be 'normal', 'oblique', or 'both'.")


def main(argv: list[str] | None = None):
    defaults = SimulationConfig3D()
    parser = argparse.ArgumentParser(description="Run stage-1 3D Maxwell uniform-air-box verification.")
    parser.add_argument("--case", choices=("normal", "oblique", "both"), default="both")
    parser.add_argument("--nedelec-degree", type=int, default=None)
    parser.add_argument("--visualization-degree", type=int, default=None)
    parser.add_argument("--mesh-target-size", type=float, default=None, help="Target mesh size in nm.")
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
            "direct_lu",
            "iterative_asm_ilu",
            "iterative_bjacobi_ilu",
            "iterative_jacobi",
            "iterative_hypre",
        ),
        default=None,
        help="3D linear solver profile. default keeps the original direct LU solve.",
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
    args = parser.parse_args(argv)

    unique_output = defaults.unique_output if args.unique_output is None else args.unique_output
    updates = _config_updates(args)
    configs = _case_configs(args.case, updates)

    root = project_root()
    results_root = root / "results"
    p = args.nedelec_degree if args.nedelec_degree is not None else defaults.nedelec_degree
    h = args.mesh_target_size if args.mesh_target_size is not None else defaults.mesh_target_size
    case_tag = "normal_oblique" if args.case == "both" else args.case
    group_parts = ["3D_airbox_stage1", case_tag, f"p{p}", _number_tag("h", h)]
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
