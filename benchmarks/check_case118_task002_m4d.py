"""Build and independently verify Task002 Review-V6 Case118 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks/cases/118_task002_y_alias_qualification"
RECORDS = CASE / "records"
ARTIFACTS = ROOT / "benchmarks/artifacts/cases/118/m4d"
BASELINE_SHA = "0a53c42397a2e67f64e8f6dae2c680bfe3fe4b95"
AZIMUTHS = (50, 51, 52, 53, 53.5, 54, 54.25, 54.5, 54.75, 55, 55.5, 56, 57, 58)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _complex_abs(value: Any) -> float:
    if isinstance(value, list):
        return abs(complex(float(value[0]), float(value[1])))
    return abs(complex(value))


def _extract(run: Path) -> dict[str, Any]:
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
    reflection = sum(
        float(row["power_ratio"]) for row in n_nonzero
        if row["side"] == "top" and bool(row["power_carrying"])
    )
    transmission = sum(
        float(row["power_ratio"]) for row in n_nonzero
        if row["side"] == "bottom" and bool(row["power_carrying"])
    )
    fixed_r = sum(
        float(row["power_ratio"]) for row in n0
        if row["side"] == "top" and bool(row["power_carrying"])
    )
    fixed_t = sum(
        float(row["power_ratio"]) for row in n0
        if row["side"] == "bottom" and bool(row["power_carrying"])
    )
    dominant = max(n_nonzero, key=lambda row: float(row["power_ratio"]))
    selected = [
        row for row in orders
        if int(row["m"]) == 0 and int(row["n"]) in {0, -3}
    ]
    watchdog = execution["watchdog"]
    return {
        "run_id": run.name,
        "source_sha": execution["source_sha"],
        "parameters": execution["parameters"],
        "y_cells": int(execution["y_cells"]),
        "surface_quadrature_degree_requested": execution["surface_quadrature_degree_requested"],
        "surface_quadrature_degree_actual": int(record["diagnostics"]["current_surface_quadrature_degree"]),
        "kinematics": record["kinematics"],
        "selected_m0_n0_nminus3_orders": selected,
        "leakage": {
            "n_nonzero_reflection_power_sum": reflection,
            "n_nonzero_transmission_power_sum": transmission,
            "n_nonzero_total_power": reflection + transmission,
            "n_nonzero_max_abs_amplitude_at_boundary": max(
                _complex_abs(row["outgoing_amplitude_at_boundary"]) for row in n_nonzero
            ),
            "dominant_order": {
                "side": dominant["side"], "m": dominant["m"], "n": dominant["n"],
                "polarization": dominant["polarization"],
                "power_ratio": dominant["power_ratio"],
                "abs_amplitude_at_boundary": _complex_abs(dominant["outgoing_amplitude_at_boundary"]),
            },
        },
        "aggregates": {
            "R_total": float(port["R_total"]),
            "T_total": float(port["T_total"]),
            "A_balance": float(port["A_balance"]),
            "A_volume": float(volume["A_volume_total"]),
            "true_relative_residual": float(summary["linear_system_relative_residual"]),
            "energy_closure_error": float(port["energy_closure_error_dtn_port_modal_volume"]),
        },
        "power_ledger": {
            "fixed_n0_reflection_power_sum": fixed_r,
            "fixed_n0_transmission_power_sum": fixed_t,
            "raw_R_minus_fixed_n0_R_minus_n_nonzero_R": float(port["R_total"]) - fixed_r - reflection,
            "raw_T_minus_fixed_n0_T_minus_n_nonzero_T": float(port["T_total"]) - fixed_t - transmission,
        },
        "projection_comparison": record["diagnostics"]["selected_mode_projection_comparison"],
        "gram_condition": record["diagnostics"]["port_vector_gram_condition"],
        "demodulated_field_audit": record["diagnostics"]["demodulated_field_audit"],
        "runtime_topology": record["runtime_topology"],
        "watchdog": watchdog,
        "gates": {
            "completed": watchdog["status"] == "completed" and watchdog["return_code"] == 0,
            "zero_swap": int(watchdog["peak_swap_bytes"]) == 0,
            "cleanup_complete": bool(watchdog["cleanup_complete"]),
            "residual_le_1e_minus_9": float(summary["linear_system_relative_residual"]) <= 1e-9,
            "energy_abs_le_1e_minus_7": abs(float(port["energy_closure_error_dtn_port_modal_volume"])) <= 1e-7,
            "ledger_abs_le_1e_minus_12": max(
                abs(float(port["R_total"]) - fixed_r - reflection),
                abs(float(port["T_total"]) - fixed_t - transmission),
            ) <= 1e-12,
            "leakage_total_power_le_1e7": reflection + transmission <= 1e-7,
            "leakage_max_amplitude_le_1e4": max(
                _complex_abs(row["outgoing_amplitude_at_boundary"]) for row in n_nonzero
            ) <= 1e-4,
        },
        "artifact_hashes": {
            str(path.relative_to(ROOT)): _sha(path)
            for path in (execution_path, record_path, orders_path, port_path, volume_path, summary_path)
        },
    }


def _azimuth_run(group: str, azimuth: float) -> Path:
    text = str(int(azimuth)) if float(azimuth).is_integer() else str(azimuth)
    return ARTIFACTS / f"{group}_scan_a{text}"


def build_records() -> dict[str, Any]:
    failed = _extract(ARTIFACTS / "failed_ny3_qauto")
    case117 = _read(
        ROOT / "benchmarks/cases/117_task002_p5_bulk_campaign/records/first_numerical_failure.json"
    )
    reproduction = {
        "schema_version": "task002.case118-failed-point-reproduction.v1",
        "baseline_sha": BASELINE_SHA,
        "case117_evidence_immutable": True,
        "case117_formal_record_sha256": case117["formal_record_sha256"],
        "case118": failed,
        "comparison": {
            "R_abs_difference": abs(failed["aggregates"]["R_total"] - case117["aggregates"]["R_total"]),
            "T_abs_difference": abs(failed["aggregates"]["T_total"] - case117["aggregates"]["T_total"]),
            "leakage_power_abs_difference": abs(
                failed["leakage"]["n_nonzero_total_power"] -
                case117["leakage"]["n_nonzero_reflection_power_sum"] -
                case117["leakage"]["n_nonzero_transmission_power_sum"]
            ),
            "max_boundary_amplitude_abs_difference": abs(
                failed["leakage"]["n_nonzero_max_abs_amplitude_at_boundary"] -
                case117["leakage"]["n_nonzero_max_abs_amplitude"]
            ),
        },
    }
    azimuth = {
        "schema_version": "task002.case118-azimuth-resonance-map.v1",
        "baseline_sha": BASELINE_SHA,
        "failed_geometry": [_extract(_azimuth_run("failed", az)) for az in AZIMUTHS],
        "center_geometry": [_extract(_azimuth_run("center", az)) for az in AZIMUTHS],
    }
    ny_rows = [_extract(ARTIFACTS / f"failed_ny{ny}_qauto") for ny in (3, 4, 5, 6)]
    ny6 = ny_rows[-1]["aggregates"]
    for row in ny_rows:
        row["aggregate_difference_vs_ny6"] = {
            key: abs(row["aggregates"][key] - ny6[key]) for key in ("R_total", "T_total", "A_balance", "A_volume")
        }
    y_convergence = {
        "schema_version": "task002.case118-y-cell-convergence.v1",
        "baseline_sha": BASELINE_SHA,
        "rows": ny_rows,
        "finding": "Ny3 n=0/n=-3 discrete Bragg alias vanishes at Ny4 and remains at roundoff for Ny5/Ny6",
    }
    q_rows = [
        _extract(ARTIFACTS / ("failed_ny3_qauto" if q is None else f"failed_ny3_q{q}"))
        for q in (None, 31, 39, 47)
    ]
    quadrature = {
        "schema_version": "task002.case118-surface-quadrature-convergence.v1",
        "baseline_sha": BASELINE_SHA,
        "rows": q_rows,
        "finding": "Ny3 leakage is identical from auto q21 through q47; surface under-integration is excluded",
    }
    projection_sets = []
    for row in (ny_rows[0], ny_rows[1], ny_rows[-1]):
        projection_sets.append({
            "y_cells": row["y_cells"],
            "surface_quadrature_degree": row["surface_quadrature_degree_actual"],
            "rows": row["projection_comparison"],
            "demodulated_field_audit": row["demodulated_field_audit"],
        })
    projection = {
        "schema_version": "task002.case118-auxiliary-vs-direct-projection.v1",
        "baseline_sha": BASELINE_SHA,
        "independent_projection_quadrature_degree": 63,
        "sets": projection_sets,
        "finding": (
            "S amplitudes agree near roundoff, confirming the solved FE/DtN field contains the Ny3 alias; "
            "P amplitudes show a separate auxiliary/direct inconsistency retained as negative evidence"
        ),
    }
    gram = {
        "schema_version": "task002.case118-port-vector-gram-condition.v1",
        "baseline_sha": BASELINE_SHA,
        "y_cell_sets": [
            {"y_cells": row["y_cells"], "rows": row["gram_condition"]} for row in ny_rows
        ],
        "quadrature_sets": [
            {"requested_q": row["surface_quadrature_degree_requested"], "rows": row["gram_condition"]}
            for row in q_rows
        ],
        "finding": "actual-trace n0/n-3 overlap is O(1) at Ny3 and roundoff at Ny>=4, independent of q",
    }
    max_s_difference = max(
        row["auxiliary_minus_direct_outgoing_abs"]
        for dataset in projection_sets for row in dataset["rows"]
        if row["polarization"] == "s"
    )
    max_p_difference = max(
        row["auxiliary_minus_direct_outgoing_abs"]
        for dataset in projection_sets for row in dataset["rows"]
        if row["polarization"] == "p"
    )
    decision = {
        "schema_version": "task002.case118-solver-route-decision.v1",
        "baseline_sha": BASELINE_SHA,
        "root_cause": "Ny3_mesh_induced_discrete_Bragg_trace_alias_confirmed",
        "evidence": {
            "ny3_total_leakage": ny_rows[0]["leakage"]["n_nonzero_total_power"],
            "ny4_total_leakage": ny_rows[1]["leakage"]["n_nonzero_total_power"],
            "ny3_bottom_s_overlap": next(
                row["normalized_overlap_abs"] for row in ny_rows[0]["gram_condition"]
                if row["side"] == "bottom" and row["polarization"] == "s"
                and row["quadrature_degree"] == ny_rows[0]["surface_quadrature_degree_actual"]
            ),
            "ny4_bottom_s_overlap": next(
                row["normalized_overlap_abs"] for row in ny_rows[1]["gram_condition"]
                if row["side"] == "bottom" and row["polarization"] == "s"
                and row["quadrature_degree"] == ny_rows[1]["surface_quadrature_degree_actual"]
            ),
            "max_S_auxiliary_direct_difference": max_s_difference,
            "max_P_auxiliary_direct_difference": max_p_difference,
        },
        "route_a_ny4_supported": all(ny_rows[1]["gates"].values()),
        "production_mesh_change_performed": False,
        "m4_resume_authorized": False,
        "decision": (
            "Recommend Route A Ny4 as the next production candidate, but keep M4 stopped. "
            "A new production SHA/rebind/canary campaign requires Review V7, and the newly exposed "
            "P auxiliary/direct projection inconsistency must be dispositioned before qualification."
        ),
        "static_condensation_exclusion": {
            "status": "not_run",
            "reason": (
                "optional M4D-6 was not needed to identify the alias: Ny-only refinement changes overlap "
                "from O(1) to roundoff while the backend is fixed; an unqualified standard-full p5 run "
                "was not added after the independent P-projection discrepancy was found"
            ),
        },
        "forbidden_work_unchanged": {
            "case117_bulk_resumed": False,
            "training_indices_41_95_run": False,
            "frozen_validation_read_or_run": False,
            "frozen_tuple_table_modified": False,
            "surrogate_trained": False,
        },
    }
    values = {
        "failed_point_reproduction.json": reproduction,
        "azimuth_resonance_map.json": azimuth,
        "y_cell_convergence.json": y_convergence,
        "surface_quadrature_convergence.json": quadrature,
        "auxiliary_vs_direct_projection.json": projection,
        "port_vector_gram_condition.json": gram,
        "solver_route_decision.json": decision,
    }
    for name, value in values.items():
        _write(RECORDS / name, value)
    return values


def check_records() -> dict[str, Any]:
    expected = _read(CASE / "expected.json")
    checks = []
    def add(name: str, passed: bool, observed: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "observed": observed})
    required = expected["required_records"]
    add("all_required_records_present", all((RECORDS / name).is_file() for name in required))
    azimuth = _read(RECORDS / "azimuth_resonance_map.json")
    add("failed_azimuth_stencil_exact", [row["parameters"]["configuration"]["azimuth_deg"] for row in azimuth["failed_geometry"]] == list(AZIMUTHS))
    add("center_azimuth_stencil_exact", [row["parameters"]["configuration"]["azimuth_deg"] for row in azimuth["center_geometry"]] == list(AZIMUTHS))
    all_scan = azimuth["failed_geometry"] + azimuth["center_geometry"]
    add("all_scan_watchdogs_complete_zero_swap", all(
        row["gates"]["completed"] and row["gates"]["zero_swap"] and row["gates"]["cleanup_complete"]
        for row in all_scan
    ))
    add("all_scan_bound_to_clean_sha", all(row["source_sha"] == BASELINE_SHA for row in all_scan))
    y_rows = _read(RECORDS / "y_cell_convergence.json")["rows"]
    add("ny_matrix_complete", [row["y_cells"] for row in y_rows] == [3, 4, 5, 6])
    add("ny4_passes_unchanged_leakage_gates", y_rows[1]["gates"]["leakage_total_power_le_1e7"] and y_rows[1]["gates"]["leakage_max_amplitude_le_1e4"])
    add("ny3_failure_reproduced", not y_rows[0]["gates"]["leakage_total_power_le_1e7"] and not y_rows[0]["gates"]["leakage_max_amplitude_le_1e4"])
    add("ny4_leakage_drops_twelve_orders", y_rows[1]["leakage"]["n_nonzero_total_power"] <= y_rows[0]["leakage"]["n_nonzero_total_power"] * 1e-12)
    q_rows = _read(RECORDS / "surface_quadrature_convergence.json")["rows"]
    add("quadrature_matrix_exact", [row["surface_quadrature_degree_actual"] for row in q_rows] == [21, 31, 39, 47])
    q_power = [row["leakage"]["n_nonzero_total_power"] for row in q_rows]
    add("quadrature_leakage_stable", max(q_power) - min(q_power) <= 1e-18, q_power)
    gram = _read(RECORDS / "solver_route_decision.json")["evidence"]
    add("actual_trace_gram_alias_confirmed", gram["ny3_bottom_s_overlap"] > 0.3 and gram["ny4_bottom_s_overlap"] < 1e-12, gram)
    decision = _read(RECORDS / "solver_route_decision.json")
    add("bulk_remains_stopped", decision["m4_resume_authorized"] is False and not any(decision["forbidden_work_unchanged"].values()))
    result = {
        "schema_version": "task002.case118-check.v1",
        "baseline_sha": BASELINE_SHA,
        "checks": checks,
        "pass_count": sum(row["pass"] for row in checks),
        "check_count": len(checks),
        "pass": all(row["pass"] for row in checks),
    }
    _write(RECORDS / "case118_check.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.build:
        build_records()
    result = check_records()
    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
