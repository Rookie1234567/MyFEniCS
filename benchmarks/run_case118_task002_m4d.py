"""Run one isolated Case118 Task002 M4D diagnostic with the formal watchdog."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path

from src.forward_data.task002_campaign import formal_preflight
from src.forward_data.task002_m4d import write_json
from src.forward_data.task002_schema import Task002ForwardParameters
from src.forward_data.watchdog import run_with_watchdog


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--baseline-sha", required=True)
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--height-nm", type=float, required=True)
    parser.add_argument("--width-nm", type=float, required=True)
    parser.add_argument("--grazing-deg", type=float, required=True)
    parser.add_argument("--azimuth-deg", type=float, required=True)
    parser.add_argument("--y-cells", type=int, required=True)
    parser.add_argument("--surface-quadrature-degree", type=int)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    root = args.root.resolve()
    preflight = formal_preflight(root, args.baseline_sha)
    parameters = Task002ForwardParameters(
        height_nm=args.height_nm,
        width_x_nm=args.width_nm,
        grazing_deg=args.grazing_deg,
        azimuth_deg=args.azimuth_deg,
        model_id="S_PROD_FULL3D_STATIC_P5_H10",
    )
    parameters.validate()
    run_dir = args.run_directory.resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    parameters_path = run_dir / "parameters.json"
    write_json(parameters_path, asdict(parameters))
    command = [
        "mpiexec", "-n", "2", str(root / ".venv/bin/python"),
        "-m", "src.runners.run_task002_m4d",
        "--parameters-json", str(parameters_path),
        "--baseline-sha", args.baseline_sha,
        "--output-dir", str(run_dir / "results"),
        "--y-cells", str(args.y_cells),
    ]
    if args.surface_quadrature_degree is not None:
        command.extend([
            "--surface-quadrature-degree", str(args.surface_quadrature_degree),
        ])
    env = {
        **os.environ,
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
    }
    watchdog = run_with_watchdog(
        command,
        cwd=root,
        env=env,
        output_dir=run_dir / "watchdog",
        timeout_seconds=args.timeout_seconds,
        memory_limit_bytes=preflight["resources"]["hard_ceiling_bytes"],
    )
    write_json(run_dir / "execution.json", {
        "schema_version": "task002.case118-execution.v1",
        "source_sha": args.baseline_sha,
        "parameters": parameters.as_dict(),
        "y_cells": args.y_cells,
        "surface_quadrature_degree_requested": args.surface_quadrature_degree,
        "command": command,
        "preflight": preflight,
        "watchdog": asdict(watchdog),
        "formal_record_present": (run_dir / "results/task002_m4d_record.json").is_file(),
    })
    return 0 if watchdog.status == "completed" and watchdog.return_code == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
