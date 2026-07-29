"""Independent lightweight checker for Task002 Case112 contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from src.forward_data.provenance import canonical_hash
from src.forward_data.task002_dataset import verify_compact_dataset
from src.forward_data.task002_design import (
    audit_order_window, cutoff_diagnostics, fixed_hf_angle_pilot, lf_angle_pilot,
)
from src.forward_data.task002_schema import Task002ForwardParameters


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks" / "cases" / "112_s_continuous_illumination_multifidelity_surrogate"
M2_RECORD = CASE / "records" / "m2_controlled_stop.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_scaffold_record() -> dict[str, Any]:
    lf = lf_angle_pilot()
    hf = fixed_hf_angle_pilot()
    audit = audit_order_window()
    return {
        "schema_version": "task002.case112-scaffold-record.v1",
        "lf_angle_pilot_count": len(lf),
        "fixed_hf_angle_pilot_count": len(hf),
        "lf_angle_design_hash": canonical_hash(lf),
        "fixed_hf_angle_design_hash": canonical_hash(hf),
        "order_window_audit": audit,
        "gates": {
            "lf_count_49": len(lf) == 49,
            "hf_count_9": len(hf) == 9,
            "order_window_complete": bool(audit["coverage_pass"]),
        },
    }


def check_scaffold(*, check_records: bool) -> dict[str, Any]:
    config = json.loads((CASE / "config.json").read_text())
    expected = json.loads((CASE / "expected.json").read_text())
    if config["polarization"] != "S" or config["wavelength_nm"] != 13.5:
        raise ValueError("Case112 fixed physics mismatch")
    if expected["bulk_generation_allowed_before_m2_gate"]:
        raise ValueError("Case112 must fail closed before the M2 gate")
    record = build_scaffold_record()
    if not all(record["gates"].values()):
        raise ValueError(f"Case112 scaffold gate failed: {record['gates']}")
    if check_records:
        tracked = json.loads((CASE / "records" / "m1_scaffold.json").read_text())
        if tracked != record:
            raise ValueError("Case112 tracked M1 scaffold record is stale")
    return record


def build_m2_record(artifact_root: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text())
    baseline = manifest["baseline_sha"]
    rows = []
    for key, item in manifest["samples"].items():
        run_dir = artifact_root / key[:16]
        execution_path = run_dir / "execution.json"
        solver_path = run_dir / "solver_record.json"
        execution = json.loads(execution_path.read_text())
        solver = json.loads(solver_path.read_text())
        if execution["baseline_sha"] != baseline:
            raise ValueError("M2 record mixes baseline SHA values")
        parameters = execution["parameters"]
        configuration = parameters["configuration"]
        geometry = parameters["geometry"]
        task_parameters = Task002ForwardParameters(
            height_nm=geometry["height_nm"], width_x_nm=geometry["width_x_nm"],
            grazing_deg=configuration["grazing_deg"],
            azimuth_deg=configuration["azimuth_deg"],
            model_id=parameters["fidelity"]["model_id"],
        )
        physical = solver["physical_field_reconstruction"]
        assembled = physical["assembled_interface_continuity"]
        absorption = physical["volume_absorption"]
        port = solver["validation"]["port_power"]
        rows.append({
            "sample_key": key, "artifact_id": key[:16],
            "model_id": task_parameters.model_id,
            "grazing_deg": task_parameters.grazing_deg,
            "azimuth_deg": task_parameters.azimuth_deg,
            "classification": item["status"], "solver_status": solver["status"],
            "execution_sha256": _sha256(execution_path),
            "solver_record_sha256": _sha256(solver_path),
            "true_relative_residual": solver["solve"]["true_relative_residual"],
            "assembled_interface_e_max": max(
                assembled[side]["electric_tangential"]["relative_l2"]
                for side in ("bottom", "top")
            ),
            "exact_traction_dual_max": max(
                assembled[side]["traction_hcurl_dual"]["relative_dual"]
                for side in ("bottom", "top")
            ),
            "energy_closure_error": absorption["energy_closure_error"],
            "R_total": port["R_total"], "T_total": port["T_total"],
            "A_balance": port["A_balance"], "A_volume": absorption["A_volume_total"],
            "cutoff_metric": cutoff_diagnostics(task_parameters)["cutoff_metric"],
            "near_cutoff": cutoff_diagnostics(task_parameters)["near_cutoff"],
            "failed_formal_gates": [name for name, value in solver["gates"].items() if not value],
            "failed_diagnostic_gates": [
                name for name, value in solver.get("diagnostic_gates", {}).items() if not value
            ],
            "wall_seconds": execution["watchdog"]["elapsed_seconds"],
            "peak_rss_bytes": execution["watchdog"]["peak_rss_bytes"],
            "peak_swap_bytes": execution["watchdog"]["peak_swap_bytes"],
            "cleanup_complete": execution["watchdog"]["cleanup_complete"],
        })
    rows.sort(key=lambda row: (row["model_id"], row["grazing_deg"], row["azimuth_deg"]))
    pass_count = sum(row["classification"] == "measured_pass" for row in rows)
    failed_count = len(rows) - pass_count
    return {
        "schema_version": "task002.case112-m2-controlled-stop.v1",
        "dataset_source_sha": baseline,
        "campaign_manifest_sha256": _sha256(manifest_path),
        "sample_count": len(rows), "measured_pass_count": pass_count,
        "failed_numerical_gate_count": failed_count,
        "four_center_anchor_fidelity_runs_completed": 8,
        "lf_angle_pilot_completed_unique_count": 5,
        "lf_angle_pilot_required_count": 49,
        "hf_angle_pilot_completed_count": 4,
        "m2_gate_pass": False,
        "bulk_generation_allowed": False,
        "controlled_stop_reason": (
            "LF 0.5deg grazing / 15deg azimuth / S failed the unchanged "
            "1e-5 volume-energy closure gate at -2.6061279233213774e-5 "
            "with cutoff_metric 0.00872653549837168"
        ),
        "all_zero_swap": all(row["peak_swap_bytes"] == 0 for row in rows),
        "all_cleanup_complete": all(row["cleanup_complete"] for row in rows),
        "samples": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-records", action="store_true")
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--m2-artifacts", type=Path)
    parser.add_argument("--m2-manifest", type=Path)
    parser.add_argument("--write-m2-record", action="store_true")
    parser.add_argument("--check-m2-record", action="store_true")
    args = parser.parse_args()
    result = check_scaffold(check_records=args.check_records)
    if args.dataset is not None:
        result["dataset"] = verify_compact_dataset(args.dataset)
    if args.m2_artifacts is not None or args.m2_manifest is not None:
        if args.m2_artifacts is None or args.m2_manifest is None:
            parser.error("M2 artifact root and manifest must be supplied together")
        m2 = build_m2_record(args.m2_artifacts, args.m2_manifest)
        if args.write_m2_record:
            M2_RECORD.write_text(json.dumps(m2, indent=2, ensure_ascii=False) + "\n")
        if args.check_m2_record:
            if json.loads(M2_RECORD.read_text()) != m2:
                raise ValueError("Case112 tracked M2 controlled-stop record is stale")
        result["m2"] = m2
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
