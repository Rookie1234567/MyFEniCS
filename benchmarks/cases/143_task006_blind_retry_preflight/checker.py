"""Independent Case143 checker for Task006 M3R0.

It re-reads the original Case141 evidence and independently recomputes all
hashes and fixed identity checks.  It never launches a solver.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = ROOT / "benchmarks/artifacts/cases/141_task006_blind12_forward"
OUTCOMES = ROOT / "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes"
RETRY_ROOT = ROOT / "benchmarks/artifacts/cases/144_task006_blind_retry_requalification"
LOCK = OUTCOMES / "TASK006_MODEL_SELECTION_LOCK.json"
CAMPAIGN = ARTIFACT_ROOT / "BLIND12_CAMPAIGN.json"
FAILURE_REPORT = OUTCOMES / "TASK006_BLIND_FAILURE_REPORT.json"
TELEMETRY = OUTCOMES / "BLIND_FORWARD_FAILURE_TELEMETRY.json"
RETRY_PLAN = OUTCOMES / "BLIND_RETRY_PLAN.json"
TIE_AUDIT = OUTCOMES / "MODEL_SELECTION_TIE_AUDIT.json"
RECORD = Path(__file__).resolve().parent / "records/case143_check.json"

FORWARD_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"
OBSERVABLE = "task002.fixed-n0-orders.v3"
FAILED = ("117.5,17.25/A07", "117.5,17.25/A09")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def file_hashes(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): sha(path) for path in sorted(root.rglob("*")) if path.is_file()}


def main() -> int:
    errors: list[str] = []
    checks: dict[str, bool] = {}
    telemetry = read(TELEMETRY)
    plan = read(RETRY_PLAN)
    tie = read(TIE_AUDIT)
    campaign = read(CAMPAIGN)
    failure = read(FAILURE_REPORT)
    lock = read(LOCK)
    checks["required_outputs"] = all(path.is_file() for path in (TELEMETRY, RETRY_PLAN, TIE_AUDIT, LOCK, CAMPAIGN, FAILURE_REPORT))
    checks["generated_without_fem"] = telemetry.get("generated_without_fem") is True and plan.get("generated_without_fem") is True
    checks["failed_tuple_set_exact"] = tuple(telemetry.get("failed_tuples", {}).keys()) == FAILED and tuple(row.get("key") for row in plan.get("failed_tuples", [])) == FAILED
    checks["original_campaign_hash_unchanged"] = telemetry.get("original_evidence_hashes", {}).get("campaign") == sha(CAMPAIGN) == campaign.get("model_lock_sha256", "") or telemetry.get("original_evidence_hashes", {}).get("campaign") == sha(CAMPAIGN)
    checks["original_failure_report_hash_unchanged"] = telemetry.get("original_evidence_hashes", {}).get("failure_report") == sha(FAILURE_REPORT) == plan.get("original_failure_report_sha256")
    checks["original_lock_hash_consistent"] = telemetry.get("original_evidence_hashes", {}).get("lock") == sha(LOCK) == plan.get("model_lock_sha256")
    checks["lock_selected_unchanged"] = lock.get("selected_candidate") == "legendre_3" and lock.get("status") == "locked_for_blind" and lock.get("blind_fem_run") is False
    checks["campaign_failure_count_two"] = campaign.get("failure_count") == 2 and campaign.get("pass_count") == 34
    checks["failure_report_preserved"] = failure.get("qualification_status") == "controlled_negative" and failure.get("failure_count") == 2
    checks["identity_contract_frozen"] = plan.get("identity") == {
        "forward_solver_sha": FORWARD_SHA, "model_id": MODEL_ID,
        "solver_route_id": ROUTE_ID, "observable_schema_version": OBSERVABLE,
        "mesh": [6, 4, 14], "degree": 5, "h_nm": 10.0,
        "mpi_ranks": 2, "threads_per_rank": 1,
        "mumps_icntl_14": 40, "mumps_icntl_22": 0,
        "assembly_backend": "assembly_time_static_condensed",
        "output_profile": "compact_surrogate_record", "residual_gate": 1.0e-9,
        "same_config_and_observable": True,
    }
    checks["retry_contract_frozen"] = plan.get("max_retry_fem_count") == 4 and plan.get("retry_contract", {}).get("attempts_per_tuple") == 2 and plan.get("retry_contract", {}).get("no_gate_relaxation") is True and plan.get("retry_contract", {}).get("no_solver_change") is True
    checks["retry_attempts_not_started"] = all(attempt.get("status") == "not_run" for row in plan.get("failed_tuples", []) for attempt in row.get("attempts", [])) and not RETRY_ROOT.exists()
    checks["tie_audit_model_order"] = tie.get("candidate_order") == ["legendre_2", "legendre_3", "legendre_4", "local_rbf_k8", "matern52_ard_exact_gp", "degree2_trend_plus_matern52_residual"]
    checks["tie_audit_exact_group"] = tie.get("exact_score_ties") == [{"score": 1.0, "candidates": ["legendre_3", "matern52_ard_exact_gp", "degree2_trend_plus_matern52_residual"]}]
    checks["tie_audit_no_blind"] = tie.get("blind_response_used_for_tie_break") is False and tie.get("model_lock_modified") is False

    for key in FAILED:
        row = telemetry["failed_tuples"].get(key, {})
        angle = key.rsplit("/", 1)[1]
        run_root = ARTIFACT_ROOT / "blind/117.5_17.25" / angle
        formal = read(run_root / "results/task002_full3d_record.json")
        summary = read(run_root / "results/run_summary.json")
        checks[f"{key}_identity"] = row.get("source_identity", {}).get("forward_solver_sha") == FORWARD_SHA and row.get("source_identity", {}).get("model_id") == MODEL_ID and row.get("source_identity", {}).get("solver_route_id") == ROUTE_ID and row.get("source_identity", {}).get("actual_observable_schema_version") == OBSERVABLE
        checks[f"{key}_residual_replay"] = row.get("residual", {}).get("relative_residual") == formal.get("observables", {}).get("true_relative_residual") and row.get("residual", {}).get("absolute_residual_norm") == summary.get("linear_system_residual_norm") and row.get("residual", {}).get("rhs_norm_denominator") == summary.get("linear_system_rhs_norm") and row.get("residual", {}).get("gate_pass") is False
        checks[f"{key}_ksp_replay"] = row.get("ksp", {}).get("reason") == 4 and row.get("ksp", {}).get("reason_name") == "CONVERGED_ITS" and row.get("ksp", {}).get("iterations") == 1
        checks[f"{key}_mumps_replay"] = row.get("mumps", {}).get("icntl_14_requested_percent") == 40 and row.get("mumps", {}).get("icntl_14_observed_percent") == 40 and row.get("mumps", {}).get("workspace_relaxation_verified") is True
        checks[f"{key}_resource_replay"] = row.get("resource", {}).get("watchdog", {}).get("peak_swap_bytes") == 0 and row.get("resource", {}).get("watchdog", {}).get("peak_pss_bytes", 0) > 0 and row.get("resource", {}).get("preflight", {}).get("pass") is True
        checks[f"{key}_original_directory_hash"] = row.get("original_failure_directory_file_hashes") == file_hashes(run_root)
        checks[f"{key}_all_other_gates_true"] = all(value is True for name, value in formal.get("gates", {}).items() if name != "true_residual_le_1e-9")

    if not all(checks.values()):
        errors = [name for name, value in checks.items() if not value]
    result = {
        "schema_version": "task006.case143-m3r0-replay-check.v1",
        "status": "pass" if not errors else "failed",
        "checks": checks, "errors": errors,
        "generated_without_fem": True,
        "retry_authorized": not errors,
        "original_case141_preserved": not errors,
    }
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
