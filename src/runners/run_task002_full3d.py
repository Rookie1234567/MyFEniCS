"""MPI entry point for one formal Task002 fixed-topology Full3D solve."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from mpi4py import MPI

from src.forward_data.provenance import canonical_hash
from src.forward_data.task002_full3d import (
    TASK002_FULL3D_RECORD_SCHEMA,
    build_task002_full3d_config,
    extract_task002_full3d_orders,
    task002_full3d_config_identity,
    task002_full3d_topology_identity,
)
from src.forward_data.task002_schema import Task002ForwardParameters
from src.forward_data.task002_runtime_topology import (
    actual_runtime_mesh_identity, compare_planned_actual,
)
from src.runners.run_3d_cases import _run_stage_config


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parameters-json", type=Path, required=True)
    parser.add_argument("--baseline-sha", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--output-profile", choices=("ordinary", "compact_surrogate_record"),
        default="compact_surrogate_record",
    )
    args = parser.parse_args()
    parameters = Task002ForwardParameters.from_mapping(
        json.loads(args.parameters_json.read_text(encoding="utf-8"))
    )
    if len(args.baseline_sha) != 40:
        raise ValueError("formal Task002 Full3D source SHA must be full length")
    cfg = build_task002_full3d_config(parameters, output_profile=args.output_profile)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    runtime_identity: dict[str, object] = {}

    def observe_runtime(*, field, mesh_data, floquet_data, **_kwargs) -> None:
        actual = actual_runtime_mesh_identity(
            function_space=field.function_space, mesh_data=mesh_data,
            floquet_data=floquet_data,
        )
        runtime_identity.update(compare_planned_actual(parameters, actual))

    summary = _run_stage_config(
        cfg, args.output_dir, solution_observer=observe_runtime,
    )
    MPI.COMM_WORLD.barrier()
    if MPI.COMM_WORLD.rank == 0:
        port_path = args.output_dir / "dtn_port_power_metrics_3d.json"
        volume_path = args.output_dir / "volume_absorption.json"
        orders_path = args.output_dir / "dtn_port_diffraction_orders_3d.json"
        summary_path = args.output_dir / "run_summary.json"
        port = json.loads(port_path.read_text(encoding="utf-8"))
        volume = json.loads(volume_path.read_text(encoding="utf-8"))
        raw_orders = json.loads(orders_path.read_text(encoding="utf-8"))["orders"]
        mother = extract_task002_full3d_orders(
            raw_orders, parameters=parameters, port_power=port,
        )
        topology = task002_full3d_topology_identity(parameters, comm_size=2)
        if not runtime_identity:
            raise RuntimeError("Task002 production solve did not emit runtime topology identity")
        residual = float(summary["linear_system_relative_residual"])
        closure = float(port["energy_closure_error_dtn_port_modal_volume"])
        record = {
            "schema_version": TASK002_FULL3D_RECORD_SCHEMA,
            "source_sha": args.baseline_sha, "source_dirty": False,
            "parameters": parameters.as_dict(),
            "parameter_hash": canonical_hash(parameters.as_dict()),
            "solver_route_id": parameters.fidelity["solver_route_id"],
            "config_identity": task002_full3d_config_identity(
                parameters, output_profile=args.output_profile,
            ),
            "planned_topology_identity": topology,
            "actual_runtime_topology_identity": runtime_identity["actual"],
            "planned_vs_actual": runtime_identity,
            "element_identity": topology["element_identity"],
            "output_profile": args.output_profile,
            "observables": {
                "R_total": port["R_total"], "T_total": port["T_total"],
                "A_balance": port["A_balance"], "A_volume": volume["A_volume_total"],
                "true_relative_residual": residual,
                "energy_closure_error": closure,
                "mother_response": mother,
            },
            "artifact_hashes": {
                path.name: _sha(path) for path in
                (summary_path, port_path, volume_path, orders_path)
            },
            "gates": {
                "completed_direct_solve": summary["case_status"] == "completed",
                "true_residual_le_1e-9": residual <= 1.0e-9,
                "energy_closure_abs_le_1e-7": abs(closure) <= 1.0e-7,
                "fixed_order_schema_complete": len(mother["missing"]) == 0,
                "complete_n0_power_window": not mother["uncovered_power_carrying_n0"],
                "uniform_n1curl_identity": not topology["element_identity"]["nedelec_fixed_trace_enabled"],
                "fixed_topology_identity_present": bool(topology["topology_element_hash"]),
                "actual_runtime_topology_matches_plan": bool(runtime_identity["pass"]),
                "n_nonzero_total_power_le_1e-7": (
                    mother["leakage"]["n_nonzero_reflection_power_sum"]
                    + mother["leakage"]["n_nonzero_transmission_power_sum"]
                ) <= 1.0e-7,
                "n_nonzero_max_abs_amplitude_le_1e-4": (
                    mother["leakage"]["n_nonzero_max_abs_amplitude"] <= 1.0e-4
                ),
                "fixed_raw_reflection_ledger_abs_le_1e-12": abs(
                    mother["power_ledger"][
                        "raw_R_minus_fixed_n0_R_minus_n_nonzero_R"
                    ]
                ) <= 1.0e-12,
                "fixed_raw_transmission_ledger_abs_le_1e-12": abs(
                    mother["power_ledger"][
                        "raw_T_minus_fixed_n0_T_minus_n_nonzero_T"
                    ]
                ) <= 1.0e-12,
                "compact_output_identity": (
                    args.output_profile == "compact_surrogate_record"
                    and summary.get("field_visualization_written") is False
                    and not any(args.output_dir.glob("*.vtu"))
                    and not any(args.output_dir.glob("*.pvd"))
                ),
            },
        }
        (args.output_dir / "task002_full3d_record.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
        )
    MPI.COMM_WORLD.barrier()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
