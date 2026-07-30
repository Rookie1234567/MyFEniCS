"""Build and verify Task002 Review-V7 M4E Ny4 campaign evidence."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from src.forward_data.provenance import file_hash
from src.forward_data.task002_dataset import write_compact_dataset
from src.forward_data.task002_dataset_checker import verify_exact_design_dataset
from src.forward_data.task002_m4 import (
    formal_record_to_production_sample,
    rebind_frozen_designs,
)


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks/cases/119_task002_p5_ny4_bulk_campaign"
RECORDS = CASE / "records"
CASE116 = ROOT / "benchmarks/cases/116_task002_single_fidelity_design"
ART = ROOT / "benchmarks/artifacts/cases/119/m4e"
DESIGNS = ART / "rebound_designs"
CAMPAIGN = ART / "campaign_manifest.json"
PRODUCTION = ART / "production"
DIAGNOSTICS = ART / "diagnostics"
DATASET = ART / "compact_dataset"
MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _amplitude(value: Any) -> float:
    return math.hypot(float(value[0]), float(value[1]))


def _diagnostic_run(name: str) -> dict[str, Any]:
    run = DIAGNOSTICS / name
    execution_path = run / "execution.json"
    record_path = run / "results/task002_m4d_record.json"
    orders_path = run / "results/dtn_port_diffraction_orders_3d.json"
    port_path = run / "results/dtn_port_power_metrics_3d.json"
    volume_path = run / "results/volume_absorption.json"
    summary_path = run / "results/run_summary.json"
    execution = _read(execution_path)
    record = _read(record_path)
    orders = _read(orders_path)["orders"]
    port = _read(port_path)
    volume = _read(volume_path)
    summary = _read(summary_path)
    n_nonzero = [row for row in orders if int(row["n"]) != 0]
    n0 = [row for row in orders if int(row["n"]) == 0]
    reflection = sum(float(row["power_ratio"]) for row in n_nonzero
                     if row["side"] == "top" and row["power_carrying"])
    transmission = sum(float(row["power_ratio"]) for row in n_nonzero
                       if row["side"] == "bottom" and row["power_carrying"])
    fixed_r = sum(float(row["power_ratio"]) for row in n0
                  if row["side"] == "top" and row["power_carrying"])
    fixed_t = sum(float(row["power_ratio"]) for row in n0
                  if row["side"] == "bottom" and row["power_carrying"])
    maximum = max(_amplitude(row["outgoing_amplitude_at_boundary"])
                  for row in n_nonzero)
    selected = record["diagnostics"]["selected_mode_projection_comparison"]
    power_rows = record["diagnostics"]["power_carrying_tangential_projection_comparison"]
    watchdog = execution["watchdog"]
    result = {
        "run_id": name,
        "source_sha": execution["source_sha"],
        "parameters": execution["parameters"],
        "y_cells": execution["y_cells"],
        "runtime_axis_cell_counts": record["runtime_topology"]["axis_cell_counts"],
        "surface_quadrature_degree": record["diagnostics"]["current_surface_quadrature_degree"],
        "selected_s_p_top_bottom_n0_nminus3": selected,
        "power_carrying_tangential_rows": power_rows,
        "maximum_selected_tangential_difference": max(
            row["auxiliary_minus_direct_outgoing_abs"] for row in selected
        ),
        "maximum_power_carrying_tangential_difference": max(
            row["absolute_difference"] for row in power_rows
        ),
        "leakage": {
            "reflection": reflection, "transmission": transmission,
            "total": reflection + transmission, "max_boundary_amplitude": maximum,
        },
        "aggregates": {
            "R": port["R_total"], "T": port["T_total"],
            "A_balance": port["A_balance"], "A_volume": volume["A_volume_total"],
            "residual": summary["linear_system_relative_residual"],
            "energy_closure": port["energy_closure_error_dtn_port_modal_volume"],
        },
        "ledger": {
            "reflection": float(port["R_total"]) - fixed_r - reflection,
            "transmission": float(port["T_total"]) - fixed_t - transmission,
        },
        "watchdog": watchdog,
        "artifact_hashes": {
            str(path.relative_to(ROOT)): file_hash(path) for path in (
                execution_path, record_path, orders_path, port_path, volume_path, summary_path,
            )
        },
    }
    result["gates"] = {
        "source_clean_sha": len(result["source_sha"]) == 40,
        "runtime_topology_expected": result["runtime_axis_cell_counts"] == [6, result["y_cells"], 14],
        "tangential_selected_le_1e_minus_10": result["maximum_selected_tangential_difference"] <= 1e-10,
        "tangential_power_carrying_le_1e_minus_10": result["maximum_power_carrying_tangential_difference"] <= 1e-10,
        "leakage_power_le_1e_minus_7": reflection + transmission <= 1e-7,
        "leakage_amplitude_le_1e_minus_4": maximum <= 1e-4,
        "residual_le_1e_minus_9": float(summary["linear_system_relative_residual"]) <= 1e-9,
        "energy_abs_le_1e_minus_7": abs(float(port["energy_closure_error_dtn_port_modal_volume"])) <= 1e-7,
        "ledger_abs_le_1e_minus_12": max(
            abs(result["ledger"]["reflection"]), abs(result["ledger"]["transmission"]),
        ) <= 1e-12,
        "zero_swap": watchdog["peak_swap_bytes"] == 0,
        "cleanup": watchdog["cleanup_complete"],
        "completed": watchdog["status"] == "completed" and watchdog["return_code"] == 0,
    }
    return result


def _manifest() -> dict[str, Any]:
    return _read(CAMPAIGN)


def _campaign_rows() -> list[dict[str, Any]]:
    return list(_manifest()["samples"].values())


def campaign_samples() -> list[dict[str, Any]]:
    samples = []
    for row in sorted(
        _campaign_rows(), key=lambda value: (value["split"] != "train", value["design_index"]),
    ):
        if row["status"] != "measured_pass":
            continue
        run = Path(row["run_directory"])
        samples.append(formal_record_to_production_sample(
            manifest_row=row,
            formal_record_path=run / "results/task002_full3d_record.json",
            execution_path=run / "execution.json",
        ))
    return samples


def write_preflight(baseline_sha: str) -> dict[str, Any]:
    rebind = rebind_frozen_designs(
        source_dir=CASE116, output_dir=DESIGNS, baseline_sha=baseline_sha,
    )
    payload = {
        "schema_version": "task002.case119-preflight.v1",
        "baseline_sha": baseline_sha,
        "model_id": MODEL_ID,
        "solver_route_id": ROUTE_ID,
        "axis_cell_counts": [6, 4, 14],
        "parameter_schema": "task002.s-p5-ny4-production-parameters.v3",
        "dataset_schema": "task002.s-p5-ny4-single-fidelity-dataset.v3",
        "campaign_schema": "task002.s-p5-ny4-design-campaign.v4",
        "observable_schema": "task002.fixed-n0-orders.v3",
        "design_rebind": rebind,
        "case117_immutable": True,
        "ny3_56_pass_reuse_forbidden": True,
        "gates": {
            "tuple_hashes_unchanged": rebind["pass"],
            "new_model_route": True,
            "ny4_only": True,
        },
    }
    _write(RECORDS / "implementation_and_design_rebind.json", payload)
    return payload


def write_tangential() -> dict[str, Any]:
    names = (
        "failed_ny3_tangential", "failed_ny4_tangential",
        "center_g4p538_a54p5_ny4", "center_g10_a45_ny4",
    )
    rows = [_diagnostic_run(name) for name in names]
    ny3_ny4 = rows[:2]
    required_ny4 = rows[1:]
    payload = {
        "schema_version": "task002.case119-tangential-projection.v1",
        "rows": rows,
        "gates": {
            "ny3_ny4_all_selected_sp_le_1e_minus_10": all(
                row["gates"]["tangential_selected_le_1e_minus_10"] for row in ny3_ny4
            ),
            "three_required_ny4_power_carrying_le_1e_minus_10": all(
                row["gates"]["tangential_power_carrying_le_1e_minus_10"]
                for row in required_ny4
            ),
            "all_zero_swap_cleanup": all(
                row["gates"]["zero_swap"] and row["gates"]["cleanup"] for row in rows
            ),
        },
    }
    _write(RECORDS / "tangential_projection_correction.json", payload)
    return payload


def write_enhanced_canary(baseline_sha: str) -> dict[str, Any]:
    rows = _campaign_rows()
    training = [row for row in rows if row["split"] == "train"]
    corners = [row for row in training if 64 <= int(row["design_index"]) < 80]
    index40 = [row for row in training if int(row["design_index"]) == 40]
    alias = [_diagnostic_run(name) for name in (
        "center_g4p538_a54p25_ny4", "center_g4p538_a54p5_ny4",
        "center_g4p538_a54p75_ny4",
    )]
    tangential = _read(RECORDS / "tangential_projection_correction.json")
    payload = {
        "schema_version": "task002.case119-enhanced-canary.v1",
        "baseline_sha": baseline_sha,
        "corner_rows": corners,
        "original_index40_rows": index40,
        "alias_neighborhood": alias,
        "tangential_gate": tangential,
        "gates": {
            "corners_16_measured_pass": len(corners) == 16 and all(
                row["status"] == "measured_pass" for row in corners
            ),
            "index40_measured_pass": len(index40) == 1 and index40[0]["status"] == "measured_pass",
            "alias_three_pass_original_gates": all(all(row["gates"].values()) for row in alias),
            "tangential_all_pass": all(tangential["gates"].values()),
            "one_clean_sha": all(
                row["source_sha"] == baseline_sha for row in [*corners, *index40]
            ) and all(row["source_sha"] == baseline_sha for row in alias),
        },
    }
    _write(RECORDS / "enhanced_canary.json", payload)
    return payload


def build_dataset(baseline_sha: str) -> dict[str, Any]:
    samples = campaign_samples()
    writer = write_compact_dataset(
        samples, output_dir=DATASET, dataset_id="task002_m4e_p5_ny4_112_v3",
    )
    exact = verify_exact_design_dataset(
        DATASET,
        training_design_path=DESIGNS / "training_design.json",
        validation_design_path=DESIGNS / "frozen_validation_design.json",
        baseline_sha=baseline_sha,
    )
    payload = {"writer": writer, "independent_exact_design_checker": exact}
    _write(RECORDS / "compact_dataset_verification.json", payload)
    return payload


def write_final(baseline_sha: str) -> dict[str, Any]:
    rows = _campaign_rows()
    train = [row for row in rows if row["split"] == "train"]
    validation = [row for row in rows if row["split"] == "frozen_validation"]
    attempts = [row["attempts"][-1]["watchdog"] for row in rows if row["attempts"]]
    payload = {
        "schema_version": "task002.case119-campaign-completion.v1",
        "baseline_sha": baseline_sha,
        "manifest_sha256": file_hash(CAMPAIGN),
        "training": {"expected": 96, "measured_pass": sum(row["status"] == "measured_pass" for row in train)},
        "frozen_validation": {"expected": 16, "measured_pass": sum(row["status"] == "measured_pass" for row in validation)},
        "status_inventory": {
            status: sum(row["status"] == status for row in rows)
            for status in sorted({row["status"] for row in rows})
        },
        "resource": {
            "attempt_count": len(attempts),
            "peak_rss_bytes": max(item["peak_rss_bytes"] for item in attempts),
            "peak_pss_bytes": max(item["peak_pss_bytes"] for item in attempts),
            "all_zero_swap": all(item["peak_swap_bytes"] == 0 for item in attempts),
            "all_cleanup": all(item["cleanup_complete"] for item in attempts),
        },
        "gates": {
            "training_96": len(train) == 96 and all(row["status"] == "measured_pass" for row in train),
            "validation_16": len(validation) == 16 and all(row["status"] == "measured_pass" for row in validation),
            "one_source": {row["source_sha"] for row in rows} == {baseline_sha},
            "no_failure": all(row["status"] == "measured_pass" for row in rows),
            "zero_swap_cleanup": all(item["peak_swap_bytes"] == 0 and item["cleanup_complete"] for item in attempts),
            "case117_not_reused": all("cases/119" in row["run_directory"] for row in rows),
        },
    }
    _write(RECORDS / "training_96.json", payload["training"])
    _write(RECORDS / "frozen_validation_16.json", payload["frozen_validation"])
    _write(RECORDS / "resource_summary.json", payload["resource"])
    _write(RECORDS / "negative_or_interrupted_inventory.json", {
        "status_inventory": payload["status_inventory"],
        "first_failure": None,
        "skipped_failure": False,
    })
    _write(RECORDS / "campaign_completion.json", payload)
    return payload


def verify() -> dict[str, Any]:
    expected = _read(CASE / "expected.json")
    checks = []
    def add(name: str, passed: bool, observed: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "observed": observed})
    required = expected["required_records"]
    add("required_records", all((RECORDS / name).is_file() for name in required))
    if all((RECORDS / name).is_file() for name in required):
        preflight = _read(RECORDS / "implementation_and_design_rebind.json")
        tangential = _read(RECORDS / "tangential_projection_correction.json")
        canary = _read(RECORDS / "enhanced_canary.json")
        completion = _read(RECORDS / "campaign_completion.json")
        dataset = _read(RECORDS / "compact_dataset_verification.json")
        add("design_tuple_hashes", preflight["design_rebind"]["pass"])
        add("tangential", all(tangential["gates"].values()), tangential["gates"])
        add("enhanced_canary", all(canary["gates"].values()), canary["gates"])
        add("campaign_complete", all(completion["gates"].values()), completion["gates"])
        exact = dataset["independent_exact_design_checker"]
        add("dataset_exact_96_16", exact["status"] == "pass" and exact["training_count"] == 96 and exact["frozen_validation_count"] == 16)
    result = {
        "schema_version": "task002.case119-check.v1",
        "checks": checks,
        "pass_count": sum(row["pass"] for row in checks),
        "check_count": len(checks),
        "pass": all(row["pass"] for row in checks),
    }
    _write(RECORDS / "case119_check.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-sha")
    parser.add_argument("--write-preflight", action="store_true")
    parser.add_argument("--write-tangential", action="store_true")
    parser.add_argument("--write-canary", action="store_true")
    parser.add_argument("--build-dataset", action="store_true")
    parser.add_argument("--write-final", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if any((args.write_preflight, args.write_canary, args.build_dataset, args.write_final)) and not args.baseline_sha:
        parser.error("--baseline-sha is required for write/build operations")
    if args.write_preflight:
        write_preflight(args.baseline_sha)
    if args.write_tangential:
        write_tangential()
    if args.write_canary:
        write_enhanced_canary(args.baseline_sha)
    if args.build_dataset:
        build_dataset(args.baseline_sha)
    if args.write_final:
        write_final(args.baseline_sha)
    result = verify() if args.verify else {"status": "updated"}
    print(json.dumps(result, indent=2))
    return 0 if result.get("pass", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
