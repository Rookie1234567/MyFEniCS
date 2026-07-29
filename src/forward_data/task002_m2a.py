"""Fail-closed execution helpers for Task002 Review-V1 M2A diagnostics."""

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


MATRIX = {(4, 80), (4, 120), (4, 160), (4, 240), (5, 120), (6, 120)}
STENCIL = {
    (0.5, 0.0), (0.5, 5.0), (0.5, 10.0), (0.5, 15.0),
    (0.5, 20.0), (0.5, 30.0), (0.5, 45.0), (0.5, 60.0),
    (0.5, 75.0), (0.5, 90.0), (0.75, 15.0), (1.0, 15.0),
    (2.0, 15.0),
}
MODEL_BY_DEGREE = {4: "LF4", 5: "LF5", 6: "HF10"}


def validate_hybrid_scope(*, degree: int, modes: int, grazing: float, azimuth: float) -> None:
    matrix = (degree, modes) in MATRIX and (grazing, azimuth) == (0.5, 15.0)
    stencil = degree in (4, 6) and modes == 120 and (grazing, azimuth) in STENCIL
    if not (matrix or stencil):
        raise ValueError("requested Hybrid run is outside the reviewed M2A matrix/stencil")


def hybrid_command(
    *, root: Path, baseline_sha: str, degree: int, modes: int,
    grazing: float, azimuth: float, output: Path, memory_stages: Path,
) -> tuple[Task001ForwardParameters, list[str]]:
    validate_hybrid_scope(
        degree=degree, modes=modes, grazing=grazing, azimuth=azimuth,
    )
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
        "--task002-m2a-diagnostic-gate"
    )
    requested_index = command.index("--requested-modes") + 1
    candidate_index = command.index("--candidate-modes") + 1
    command[requested_index] = str(modes)
    command[candidate_index] = str(2 * modes)
    return parameters, command


def full3d_command(*, root: Path, result_root: Path) -> list[str]:
    return [
        "mpiexec", "-n", "2", str(root / ".venv" / "bin" / "python"),
        "-m", "src.runners.run_3d_cases", "--stage-case", "stage4_block_grating",
        "--case", "oblique", "--nedelec-degree", "4",
        "--visualization-degree", "2", "--mesh-target-size", "10",
        "--mesh-cell-type", "hexahedron", "--mesh-spacing-mode", "boundary_fitted",
        "--lambda0", "13.5", "--incident-theta-deg", "89.5",
        "--incident-phi-deg", "15", "--polarization-kind", "s",
        "--period-x", "50", "--period-y", "25", "--air-height", "130",
        "--substrate-thickness", "10", "--grating-width-x", "17",
        "--grating-width-y", "25", "--grating-height", "120",
        "--stage4-boundary-model", "dtn_port", "--stage4-dtn-order-policy",
        "auto_propagating", "--stage4-dtn-assembly", "auxiliary",
        "--stage4-full3d-assembly-backend", "assembly_time_static_condensed",
        "--no-unique-output", "--results-root", str(result_root),
    ]


def _run(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    preflight = formal_preflight(root, args.baseline_sha)
    run_directory = args.run_directory.resolve()
    run_directory.mkdir(parents=True, exist_ok=False)
    memory_stages = run_directory / "memory_stages.jsonl"
    if args.kind == "hybrid":
        parameters, command = hybrid_command(
            root=root, baseline_sha=args.baseline_sha, degree=args.degree,
            modes=args.modes, grazing=args.grazing_deg, azimuth=args.azimuth_deg,
            output=run_directory / "solver_record.json", memory_stages=memory_stages,
        )
        parameter_record: dict[str, Any] = {
            **parameters.as_dict(), "diagnostic_requested_modes": args.modes,
        }
        identity = task001_config_identity(parameters)
    else:
        command = full3d_command(root=root, result_root=run_directory / "results")
        parameter_record = {
            "height_nm": 120.0, "width_x_nm": 17.0, "grazing_deg": 0.5,
            "azimuth_deg": 15.0, "polarization": "S", "degree": 4,
            "h_nm": 10.0, "assembly_backend": "assembly_time_static_condensed",
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
        "schema_version": "task002.m2a-execution.v1", "kind": args.kind,
        "baseline_sha": args.baseline_sha, "parameters": parameter_record,
        "parameter_hash": canonical_hash(parameter_record), "identity": identity,
        "preflight": preflight, "command": command, "watchdog": asdict(result),
    }
    (run_directory / "execution.json").write_text(
        json.dumps(execution, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    print(json.dumps({"run_directory": str(run_directory), **execution}, indent=2))
    return 0 if result.status == "completed" and result.return_code == 0 else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("hybrid", "full3d"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--baseline-sha", required=True)
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--degree", type=int, default=4)
    parser.add_argument("--modes", type=int, default=120)
    parser.add_argument("--grazing-deg", type=float, default=0.5)
    parser.add_argument("--azimuth-deg", type=float, default=15.0)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.kind == "full3d" and (
        args.degree != 4 or args.modes != 120
        or args.grazing_deg != 0.5 or args.azimuth_deg != 15.0
    ):
        raise SystemExit("Full3D M2A reference is fixed at p4/h10, 0.5deg/15deg")
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
