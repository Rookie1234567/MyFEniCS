"""MPI entry point for one Task002 M4D y-alias diagnostic solve."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mpi4py import MPI

from src.forward_data.task002_m4d import (
    alias_kinematics,
    build_m4d_solution_diagnostics,
    build_task002_m4d_config,
    m4d_config_identity,
    write_json,
)
from src.forward_data.task002_runtime_topology import actual_runtime_mesh_identity
from src.forward_data.task002_schema import Task002ForwardParameters
from src.runners.run_3d_cases import _run_stage_config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parameters-json", type=Path, required=True)
    parser.add_argument("--baseline-sha", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--y-cells", type=int, required=True)
    parser.add_argument("--surface-quadrature-degree", type=int)
    args = parser.parse_args()
    if len(args.baseline_sha) != 40:
        raise ValueError("M4D baseline SHA must be full length")
    parameters = Task002ForwardParameters.from_mapping(
        json.loads(args.parameters_json.read_text(encoding="utf-8"))
    )
    cfg = build_task002_m4d_config(
        parameters,
        y_cells=args.y_cells,
        surface_quadrature_degree=args.surface_quadrature_degree,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    observed = {}

    def observer(*, field, mesh_data, floquet_data, dtn_result, **_kwargs):
        observed["runtime_topology"] = actual_runtime_mesh_identity(
            function_space=field.function_space,
            mesh_data=mesh_data,
            floquet_data=floquet_data,
        )
        observed["diagnostics"] = build_m4d_solution_diagnostics(
            field=field,
            mesh_data=mesh_data,
            config=cfg,
            floquet_data=floquet_data,
            dtn_result=dtn_result,
            parameters=parameters,
        )

    summary = _run_stage_config(cfg, args.output_dir, solution_observer=observer)
    MPI.COMM_WORLD.barrier()
    if MPI.COMM_WORLD.rank == 0:
        if not observed:
            raise RuntimeError("M4D observer did not run")
        payload = {
            "schema_version": "task002.m4d-formal-record.v1",
            "source_sha": args.baseline_sha,
            "source_dirty": False,
            "parameters": parameters.as_dict(),
            "kinematics": alias_kinematics(parameters),
            "config_identity": m4d_config_identity(
                parameters,
                y_cells=args.y_cells,
                surface_quadrature_degree=args.surface_quadrature_degree,
            ),
            "runtime_topology": observed["runtime_topology"],
            "diagnostics": observed["diagnostics"],
            "summary": {
                key: summary.get(key) for key in (
                    "case_status", "linear_system_relative_residual",
                    "R_total", "T_total", "A_balance", "A_volume_total",
                    "stage4_energy_balance_error",
                    "stage4_dtn_surface_quadrature_degree",
                )
            },
        }
        write_json(args.output_dir / "task002_m4d_record.json", payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
