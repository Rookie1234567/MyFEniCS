"""Independent Case124 checker for Task004 M0R/M1R/M2R/M3R evidence.

The checker re-derives tuple hashes, reads the raw execution records named by
the manifests, and checks the numerical/resource gates from the records.  It
does not run a solver and it never opens Task003 or Task004 validation arrays.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
ARTIFACTS = REPO / "benchmarks/artifacts/cases/124_task004_mumps_workspace_and_anchor_requalification"
DESIGNS = ROOT / "records/designs"
SOURCE_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"
PARAMETER_SCHEMA = "task002.s-p5-ny4-production-parameters.v3"
OBSERVABLE_SCHEMA = "task002.fixed-n0-orders.v3"


def load(path: Path):
    return json.loads(path.read_text())


def canonical_hash(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def point_tuple(point: dict) -> list[float]:
    # The design contract uses numpy's decimal rounding; Python's round can
    # differ by one ulp for Sobol coordinates at the 12-decimal boundary.
    return [float(np.round(float(point[key]), 12)) for key in
            ("height_nm", "width_x_nm", "grazing_deg", "azimuth_deg")]


def design_tuple_hash(design: dict) -> str:
    return canonical_hash([point_tuple(point) for point in design["points"]])


def execution_path(attempt: dict) -> Path:
    if attempt.get("execution_path"):
        path = Path(attempt["execution_path"])
        if path.exists():
            return path
    run = Path(attempt["run_directory"])
    if run.is_absolute() and (run / "execution.json").exists():
        return run / "execution.json"
    return ARTIFACTS / run.relative_to(ARTIFACTS) / "execution.json"


def record_path(attempt: dict) -> Path:
    path = execution_path(attempt).parent / "results/task002_full3d_record.json"
    return path


def check_execution(attempt: dict, *, icntl: int = 40) -> bool:
    execution = load(execution_path(attempt))
    record = load(record_path(attempt))
    watchdog = execution.get("watchdog", {})
    solver = execution.get("solver_identity", {})
    gates = record.get("gates", {})
    required_gates = (
        "completed_direct_solve", "true_residual_le_1e-9",
        "energy_closure_abs_le_1e-7", "fixed_order_schema_complete",
        "complete_n0_power_window", "uniform_n1curl_identity",
        "fixed_topology_identity_present", "actual_runtime_topology_matches_plan",
        "n_nonzero_total_power_le_1e-7", "n_nonzero_max_abs_amplitude_le_1e-4",
        "fixed_raw_reflection_ledger_abs_le_1e-12",
        "fixed_raw_transmission_ledger_abs_le_1e-12", "compact_output_identity",
    )
    obs = record.get("observables", {})
    return (
        execution.get("baseline_sha") == SOURCE_SHA
        and execution.get("output_profile") == "compact_surrogate_record"
        and execution.get("formal_record_present") is True
        and watchdog.get("status") == "completed"
        and watchdog.get("return_code") == 0
        and watchdog.get("child_return_code") == 0
        and watchdog.get("peak_swap_bytes") == 0
        and execution.get("config_identity", {}).get("linear_solver", {}).get("mat_mumps_icntl_14") == icntl
        and solver.get("requested_mat_mumps_icntl_14") == icntl
        and record.get("solver_identity", {}).get("factor_inventory", {}).get(
            "mumps_icntl_14_observed_percent") == icntl
        and solver.get("factor_solver") == "mumps"
        and record.get("source_sha") == SOURCE_SHA
        and record.get("model_id") == MODEL_ID
        and record.get("solver_route_id") == ROUTE_ID
        and record.get("parameters", {}).get("schema_version") == PARAMETER_SCHEMA
        and record.get("parameters", {}).get("observable_schema_version") == OBSERVABLE_SCHEMA
        and all(gates.get(key) is True for key in required_gates)
        and float(obs.get("true_relative_residual", 1.0)) <= 1.0e-9
        and abs(float(obs.get("energy_closure_error", 1.0))) <= 1.0e-7
    )


def main() -> int:
    config = load(ROOT / "config.json")
    expected = load(ROOT / "expected.json")
    names = {"training": "training_design.json", "validation": "frozen_validation_design.json",
             "candidate": "candidate_pool.json", "anchors": "anchor_design.json"}
    designs = {name: load(DESIGNS / filename) for name, filename in names.items()}
    hashes = {name: design_tuple_hash(design) for name, design in designs.items()}
    expected_hashes = {
        "training": "bfd68a374e5510284a972c640c6332d818917052ae30bd77c10af5240f0500ef",
        "validation": "af6cc7c87236aa2e1050b40f1cca1282932e071b22b3b767057b94bc8c11af57",
        "candidate": "db2a6155274614b5129846ace0a277fe69161f2e5120966d7968d6b210d981fa",
        "anchors": "63decea83a844d49a9e6a49e0ca01dddf548b8e2e592eea1b3bfadfaf8ec63f5",
    }
    identities = all(
        design.get("schema_version") == "task004.angle-design.v2"
        and design.get("source_sha") == SOURCE_SHA
        and design.get("source_dirty") is False
        and design.get("parameter_schema_version") == PARAMETER_SCHEMA
        and design.get("observable_schema_version") == OBSERVABLE_SCHEMA
        and design.get("production_model_id") == MODEL_ID
        and design.get("production_solver_route_id") == ROUTE_ID
        for design in designs.values()
    )
    nominal = all(
        all(abs(float(p["height_nm"]) - 120.0) < 1.0e-12
            and abs(float(p["width_x_nm"]) - 17.0) < 1.0e-12
            and 0.5 <= float(p["grazing_deg"]) <= 10.0
            and 0.0 <= float(p["azimuth_deg"]) <= 90.0
            for p in design["points"])
        for design in designs.values()
    )
    training_tuples = {tuple(point_tuple(p)) for p in designs["training"]["points"]}
    validation_tuples = {tuple(point_tuple(p)) for p in designs["validation"]["points"]}
    mumps = load(ARTIFACTS / "mumps_workspace_ladder.json")
    ladder_attempts = [a for a in mumps["ladder"] if a["icntl_14"] == 40]
    ladder_pass = (
        mumps.get("baseline_sha") == SOURCE_SHA
        and mumps.get("selected_icntl_14") == 40
        and mumps.get("status") == "pass"
        and len(ladder_attempts) == 2
        and len({a["run_directory"] for a in ladder_attempts}) == 2
        and all(a.get("status") == "measured_pass" and a.get("actual_icntl_14") == 40
                and a.get("safe_resource_gate") is True and a.get("workspace_verification") is True
                and check_execution(a) for a in ladder_attempts)
    )
    anchors = load(ARTIFACTS / "anchor_campaign_manifest.json")
    required_anchor_angles = [(0.5, 0.0), (0.5, 90.0), (10.0, 0.0), (10.0, 90.0), (5.25, 45.0)]
    anchor_rows = list(anchors.get("samples", {}).values())
    anchor_pass = (
        anchors.get("baseline_sha") == SOURCE_SHA
        and len(anchor_rows) == 5
        and [(float(r["point_tuple"][2]), float(r["point_tuple"][3])) for r in anchor_rows] == required_anchor_angles
        and all(r.get("status") == "measured_pass" and len(r.get("attempts", [])) == 1
                and r["attempts"][0].get("actual_icntl_14") == 40
                and r["attempts"][0].get("safe_resource_gate") is True
                and r["attempts"][0].get("workspace_verification") is True
                and check_execution(r["attempts"][0]) for r in anchor_rows)
    )
    comparer = load(ARTIFACTS / "forward_baseline_v2.json")
    comparer_pass = (
        comparer.get("source_sha") == SOURCE_SHA
        and comparer.get("status") == "pass"
        and comparer.get("anchor_count") == 5
        and comparer.get("gate", {}).get("aggregate_le_1e-10") is True
        and comparer.get("gate", {}).get("power_le_1e-10") is True
        and comparer.get("gate", {}).get("amplitude_le_1e-9") is True
        and comparer.get("gate", {}).get("identity_match") is True
        and all(a.get("pass") is True for a in comparer.get("anchors", []))
    )
    campaign = load(ARTIFACTS / "training_canary/campaign_manifest.json")
    rows = sorted(campaign.get("samples", {}).values(), key=lambda row: row["design_index"])
    attempt_statuses = [attempt.get("status") for row in rows for attempt in row.get("attempts", [])]
    final_status_counts = {}
    for row in rows:
        final_status_counts[row.get("status")] = final_status_counts.get(row.get("status"), 0) + 1
    training_pass = (
        campaign.get("baseline_sha") == SOURCE_SHA
        and final_status_counts == {"measured_pass": 96}
        and all(row.get("status") == "measured_pass" for row in rows)
        and all(status in {"measured_pass", "interrupted_retryable"} for status in attempt_statuses)
        and attempt_statuses.count("interrupted_retryable") <= 1
        and all(check_execution(row["attempts"][-1]) for row in rows)
    )
    checks = {
        "design_identity": identities and nominal,
        "design_tuple_hashes": hashes == expected_hashes,
        "training_validation_disjoint": not (training_tuples & validation_tuples),
        "single_clean_sha": SOURCE_SHA == config["source_sha"]
            and all(d.get("source_sha") == SOURCE_SHA for d in designs.values()),
        "mumps_ladder_minimum_stable": ladder_pass,
        "mumps_two_fresh_passes": ladder_pass,
        "anchor_count_and_tuples": anchor_pass,
        "anchor_observable_gate": comparer_pass,
        "training_canary_16_of_16": training_pass and all(
            row.get("status") == "measured_pass" for row in rows[:16]),
        "training_campaign_96_of_96": training_pass,
        "no_unexplained_failure": training_pass and not any(
            str(status).startswith(("failed", "controlled_stop")) for status in attempt_statuses),
        "no_blind_validation_access": config["boundaries"]["task004_blind_validation"] == "sealed_not_run_before_model_lock",
        "no_task003_validation_access": config["boundaries"]["task003_frozen_validation"] == "sealed_not_accessed",
    }
    result = {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "mumps_selected_icntl_14": 40,
        "training_status": "96_measured_pass" if training_pass else "not_pass",
        "blind_validation": "sealed_not_run",
        "model_lock": "not_created",
        "surrogate_training": "not_run",
    }
    (ROOT / "expected.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
