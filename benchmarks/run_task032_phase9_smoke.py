from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
H5_ANGLES = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
H3_ANGLES = (1, 3, 5, 7, 10)


def _finite(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return number == number and abs(number) != float("inf")


def _smoke_gates(
    record: dict[str, Any],
    *,
    h_nm: float,
    grazing_deg: int,
    polarization: str,
    requested_modes: int,
) -> dict[str, bool]:
    case = record.get("case", {})
    metadata = record.get("metadata", {})
    qep = record.get("qep", {})
    gates = record.get("gates", {})
    validation = record.get("validation", {})
    power = validation.get("port_power", {})
    orders = validation.get("external_diffraction_orders", [])
    positive = qep.get("positive_directional_selection", {})
    negative = qep.get("negative_directional_selection", {})
    return {
        "parameter_round_trip": (
            abs(float(case.get("h_nm", -1.0)) - h_nm) <= 1.0e-12
            and abs(float(case.get("incident_grazing_deg", -1.0)) - grazing_deg)
            <= 1.0e-12
            and str(case.get("polarization_kind")) == polarization
        ),
        "complex128_no_full_gather": (
            str(metadata.get("scalar_dtype")) == "complex128"
            and metadata.get("full_field_or_mode_vector_gather") is False
        ),
        "requested_modes_recomputed_and_classified": (
            int(positive.get("selected_modes", -1)) == requested_modes
            and int(negative.get("selected_modes", -1)) == requested_modes
            and positive.get("desired_direction") == "forward"
            and negative.get("desired_direction") == "backward"
        ),
        "qep_and_passive_propagation_gates": all(
            bool(gates.get(name))
            for name in (
                "exact_requested_mode_count_delivered",
                "requested_forward_and_backward_passive_bases",
                "right_and_left_qep_residuals_le_1e-8",
                "stable_propagation_no_growing_factor",
            )
        ),
        "hybrid_algebra_gates": all(
            bool(gates.get(name))
            for name in (
                "primary_direct_true_relative_residual_le_1e-9",
                "interface_e_projection_relative_residual_le_1e-8",
                "fe_modal_traction_equilibrium_relative_residual_le_1e-8",
            )
        ),
        "finite_rta_and_diffraction_output": (
            all(_finite(power.get(name)) for name in ("R_total", "T_total", "A_balance"))
            and bool(orders)
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Task32 Phase9 fixed angle/polarization parameter-entry smoke."
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--summary-output",
        type=Path,
        help="Optional lightweight tracked copy of summary.json.",
    )
    parser.add_argument("--requested-modes", type=int, default=4)
    parser.add_argument("--candidate-modes", type=int, default=8)
    parser.add_argument("--mpi-size", type=int, default=4)
    parser.add_argument("--verified-clean-sha")
    parser.add_argument("--allow-dirty-research", action="store_true")
    args = parser.parse_args(argv)
    output_root = (
        args.output_root
        if args.output_root.is_absolute()
        else (ROOT / args.output_root)
    ).resolve()
    output_root.mkdir(parents=True, exist_ok=False)
    runs = []
    source_metadata = []
    for h_nm, angles in ((5.0, H5_ANGLES), (3.0, H3_ANGLES)):
        for grazing_deg in angles:
            for polarization in ("s", "p"):
                label = f"h{h_nm:g}_a{grazing_deg:02d}_{polarization}"
                record_path = output_root / f"{label}.json"
                stdout_path = output_root / f"{label}.log"
                command = [
                    "mpiexec",
                    "-n",
                    str(args.mpi_size),
                    sys.executable,
                    "-m",
                    "benchmarks.run_task032_phase6_augmented",
                    "--h-nm",
                    str(h_nm),
                    "--incident-grazing-deg",
                    str(grazing_deg),
                    "--polarization-kind",
                    polarization,
                    "--requested-modes",
                    str(args.requested_modes),
                    "--candidate-modes",
                    str(args.candidate_modes),
                    "--output",
                    str(record_path),
                ]
                if args.verified_clean_sha:
                    command.extend(("--verified-clean-sha", args.verified_clean_sha))
                elif args.allow_dirty_research:
                    command.append("--allow-dirty-research")
                with stdout_path.open("w", encoding="utf-8") as stdout:
                    completed = subprocess.run(
                        command,
                        cwd=ROOT,
                        stdout=stdout,
                        stderr=subprocess.STDOUT,
                        text=True,
                        check=False,
                    )
                record = (
                    json.loads(record_path.read_text(encoding="utf-8"))
                    if record_path.is_file()
                    else {}
                )
                gates = _smoke_gates(
                    record,
                    h_nm=h_nm,
                    grazing_deg=grazing_deg,
                    polarization=polarization,
                    requested_modes=args.requested_modes,
                )
                source_metadata.append(record.get("metadata", {}))
                runs.append(
                    {
                        "label": label,
                        "h_nm": h_nm,
                        "incident_grazing_deg": grazing_deg,
                        "polarization_kind": polarization,
                        "return_code": completed.returncode,
                        "record": str(record_path.relative_to(ROOT)),
                        "record_status": record.get("status"),
                        "algebraic_smoke_pass": all(gates.values()),
                        "gates": gates,
                        "R_total": record.get("validation", {})
                        .get("port_power", {})
                        .get("R_total"),
                        "T_total": record.get("validation", {})
                        .get("port_power", {})
                        .get("T_total"),
                        "A_balance": record.get("validation", {})
                        .get("port_power", {})
                        .get("A_balance"),
                    }
                )
                print(
                    f"Task32 Phase9 smoke {label}: "
                    f"{'pass' if all(gates.values()) else 'failed'}",
                    flush=True,
                )
    source_fields = (
        "commit_sha",
        "branch",
        "git_dirty",
        "tracked_source_dirty",
        "verification",
        "verified_clean_sha",
        "mpi_size",
        "container_image",
        "container_digest",
        "host_environment_id",
        "scalar_dtype",
        "full_field_or_mode_vector_gather",
    )
    source_signatures = {
        tuple(metadata.get(field) for field in source_fields)
        for metadata in source_metadata
    }
    source = {
        field: source_metadata[0].get(field) if source_metadata else None
        for field in source_fields
    }
    source.update(
        {
            "run_metadata_count": len(source_metadata),
            "all_run_metadata_consistent": (
                len(source_metadata) == len(runs) and len(source_signatures) == 1
            ),
        }
    )
    summary = {
        "schema_version": 1,
        "benchmark_id": "task032_phase9_angle_polarization_smoke",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": (
            "parameter_smoke_pass"
            if all(run["algebraic_smoke_pass"] for run in runs)
            and source["all_run_metadata_consistent"]
            else "parameter_smoke_failed"
        ),
        "source": source,
        "scope": {
            "h5_angles_deg": list(H5_ANGLES),
            "h3_angles_deg": list(H3_ANGLES),
            "polarizations": ["s", "p"],
            "requested_modes_per_direction": args.requested_modes,
            "candidate_modes_per_target_branch": args.candidate_modes,
            "claim_boundary": (
                "Parameter-entry/mode-recompute/classification/output smoke only; "
                "not a production qualification of the entire angle range."
            ),
        },
        "run_count": len(runs),
        "pass_count": sum(run["algebraic_smoke_pass"] for run in runs),
        "runs": runs,
    }
    summary_path = output_root / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.summary_output is not None:
        promoted = (
            args.summary_output
            if args.summary_output.is_absolute()
            else ROOT / args.summary_output
        )
        promoted.parent.mkdir(parents=True, exist_ok=True)
        promoted.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0 if summary["status"] == "parameter_smoke_pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
