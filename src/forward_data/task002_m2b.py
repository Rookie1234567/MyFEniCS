"""Fail-closed execution helpers for Task002 Review-V2 M2B qualification."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
from typing import Any

from .provenance import canonical_hash
from .schema import Task001ForwardParameters
from .task001_campaign import task001_hybrid_command
from .task001_config import task001_config_identity
from .task002_campaign import formal_preflight
from .watchdog import run_with_watchdog


GRAZING_DEG = (0.5, 0.75, 1.0, 2.0, 4.0, 6.0, 8.0, 10.0)
AZIMUTH_DEG = (0.0, 5.0, 10.0, 15.0, 20.0, 30.0, 45.0, 60.0, 75.0, 90.0)
P_REFERENCE_POINTS = ((0.5, 15.0), (0.5, 45.0), (2.0, 15.0), (10.0, 45.0))
MODEL_BY_DEGREE = {4: "LF4", 5: "LF5", 6: "HF10"}
AXIAL_ROUTES = {
    "continuous": ("continuous_beta", "continuous_qep_beta"),
    "discrete": ("full3d_uniform_cg", "scalar_cg_discrete_derivative"),
}


def _is_frozen_angle(grazing: float, azimuth: float) -> bool:
    return grazing in GRAZING_DEG and azimuth in AZIMUTH_DEG


def hybrid_command(
    *, root: Path, baseline_sha: str, degree: int, grazing: float,
    azimuth: float, route: str, output: Path, memory_stages: Path,
) -> tuple[Task001ForwardParameters, list[str]]:
    if degree not in MODEL_BY_DEGREE or not _is_frozen_angle(grazing, azimuth):
        raise ValueError("Hybrid request is outside the frozen M2B solver domain")
    if route not in AXIAL_ROUTES:
        raise ValueError(f"unsupported M2B axial route: {route}")
    parameters = Task001ForwardParameters(
        height_nm=120.0, width_x_nm=17.0, grazing_deg=grazing,
        azimuth_deg=azimuth, incident_polarization="S",
        model_id=MODEL_BY_DEGREE[degree], mpi_ranks=2, threads_per_rank=1,
    )
    command = task001_hybrid_command(
        parameters, root=root, baseline_sha=baseline_sha,
        output_record=output, memory_stages=memory_stages,
    )
    command[command.index("--task001-surrogate-pilot-gate")] = (
        "--task002-m2b-diagnostic-gate"
    )
    propagation, traction = AXIAL_ROUTES[route]
    command[command.index("--internal-propagation-model") + 1] = propagation
    command[command.index("--internal-traction-model") + 1] = traction
    command.extend(["--task002-m2b-mode-archive", str(output.with_suffix(".modes.npz"))])
    return parameters, command


def full3d_command(
    *, root: Path, result_root: Path, degree: int, grazing: float, azimuth: float,
    h_nm: float = 10.0,
) -> list[str]:
    if degree not in (3, 4, 5):
        raise ValueError("M2B Full3D degree must be p3, p4 or p5")
    if not _is_frozen_angle(grazing, azimuth):
        raise ValueError("Full3D request is outside the frozen M2B angle matrix")
    return [
        "mpiexec", "-n", "2", str(root / ".venv" / "bin" / "python"),
        "-m", "src.runners.run_3d_cases", "--stage-case", "stage4_block_grating",
        "--case", "oblique", "--nedelec-degree", str(degree),
        "--visualization-degree", "2", "--mesh-target-size", f"{h_nm:g}",
        "--mesh-cell-type", "hexahedron", "--mesh-spacing-mode", "boundary_fitted",
        "--lambda0", "13.5", "--incident-theta-deg", f"{90.0-grazing:g}",
        "--incident-phi-deg", f"{azimuth:g}", "--polarization-kind", "s",
        "--period-x", "50", "--period-y", "25", "--air-height", "130",
        "--substrate-thickness", "10", "--grating-width-x", "17",
        "--grating-width-y", "25", "--grating-height", "120",
        "--stage4-boundary-model", "dtn_port", "--stage4-dtn-order-policy",
        "auto_propagating", "--stage4-dtn-assembly", "auxiliary",
        "--stage4-full3d-assembly-backend", "assembly_time_static_condensed",
        "--no-unique-output", "--results-root", str(result_root),
    ]


def p5_resource_projection(reference_execution: Path, hard_ceiling: int) -> dict[str, Any]:
    reference = json.loads(reference_execution.read_text(encoding="utf-8"))
    p4_peak = int(reference["watchdog"]["peak_rss_bytes"])
    dof_ratio = (5.0 * 6.0**2) / (4.0 * 5.0**2)
    factor_memory_ratio = dof_ratio**2
    projected = int(p4_peak * factor_memory_ratio * 1.25)
    return {
        "schema_version": "task002.m2b-p5-resource-projection.v1",
        "reference_execution": str(reference_execution),
        "reference_p4_peak_rss_bytes": p4_peak,
        "hexa_n1curl_dof_ratio_p5_over_p4": dof_ratio,
        "conservative_factor_memory_ratio": factor_memory_ratio,
        "safety_multiplier": 1.25,
        "projected_p5_peak_rss_bytes": projected,
        "hard_ceiling_bytes": int(hard_ceiling),
        "swap_or_ooc_allowed": False,
        "pass": projected < hard_ceiling,
    }


def _run(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    preflight = formal_preflight(root, args.baseline_sha)
    run_directory = args.run_directory.resolve()
    run_directory.mkdir(parents=True, exist_ok=False)
    memory_stages = run_directory / "memory_stages.jsonl"
    projection = None
    if args.kind == "hybrid":
        parameters, command = hybrid_command(
            root=root, baseline_sha=args.baseline_sha, degree=args.degree,
            grazing=args.grazing_deg, azimuth=args.azimuth_deg, route=args.route,
            output=run_directory / "solver_record.json", memory_stages=memory_stages,
        )
        parameter_record: dict[str, Any] = {
            **parameters.as_dict(), "diagnostic_requested_modes": 120,
            "solver_route_id": f"hybrid_{args.route}_p{args.degree}_h10_m120",
        }
        identity = task001_config_identity(parameters)
    else:
        if args.degree == 5:
            if args.projection_reference is None:
                raise RuntimeError("Full3D p5 requires an explicit p4 projection reference")
            projection = p5_resource_projection(
                args.projection_reference.resolve(),
                preflight["resources"]["hard_ceiling_bytes"],
            )
            if not projection["pass"]:
                raise RuntimeError(f"Full3D p5 resource projection failed: {projection}")
        command = full3d_command(
            root=root, result_root=run_directory / "results", degree=args.degree,
            grazing=args.grazing_deg, azimuth=args.azimuth_deg, h_nm=args.h_nm,
        )
        parameter_record = {
            "height_nm": 120.0, "width_x_nm": 17.0,
            "grazing_deg": args.grazing_deg, "azimuth_deg": args.azimuth_deg,
            "polarization": "S", "degree": args.degree, "h_nm": args.h_nm,
            "assembly_backend": "assembly_time_static_condensed",
            "solver_route_id": f"full3d_static_p{args.degree}_h{args.h_nm:g}",
        }
        identity = dict(parameter_record)
    env = {
        **os.environ, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
    }
    result = run_with_watchdog(
        command, cwd=root, env=env, output_dir=run_directory / "watchdog",
        timeout_seconds=args.timeout_seconds,
        memory_limit_bytes=preflight["resources"]["hard_ceiling_bytes"],
        stage_file=memory_stages if args.kind == "hybrid" else None,
    )
    execution = {
        "schema_version": "task002.m2b-execution.v1", "kind": args.kind,
        "baseline_sha": args.baseline_sha, "parameters": parameter_record,
        "parameter_hash": canonical_hash(parameter_record), "identity": identity,
        "resource_projection": projection, "preflight": preflight,
        "command": command, "watchdog": asdict(result),
    }
    (run_directory / "execution.json").write_text(
        json.dumps(execution, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    print(json.dumps({"run_directory": str(run_directory), **execution}, indent=2))
    solver_complete = (run_directory / "solver_record.json").is_file()
    expected_gate_exit = args.kind == "hybrid" and solver_complete and result.return_code == 2
    return 0 if (result.status == "completed" and result.return_code == 0) or expected_gate_exit else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("hybrid", "full3d"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--baseline-sha", required=True)
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--degree", type=int, required=True)
    parser.add_argument("--h-nm", type=float, default=10.0)
    parser.add_argument("--grazing-deg", type=float, required=True)
    parser.add_argument("--azimuth-deg", type=float, required=True)
    parser.add_argument("--route", choices=tuple(AXIAL_ROUTES), default="discrete")
    parser.add_argument("--projection-reference", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    return parser


def main() -> int:
    return _run(_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
