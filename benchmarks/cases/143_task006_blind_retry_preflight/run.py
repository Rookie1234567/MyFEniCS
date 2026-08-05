"""Build the Task006 M3R0 telemetry, tie audit, and frozen retry plan.

This command is metadata-only.  It reads the two immutable Case141 failure
directories and writes compact, hash-bound evidence.  It never launches a
solver and never touches the original campaign directories.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = ROOT / "benchmarks/artifacts/cases/141_task006_blind12_forward"
RETRY_ARTIFACT_ROOT = ROOT / "benchmarks/artifacts/cases/144_task006_blind_retry_requalification"
OUTCOMES = ROOT / "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes"
LOCK = OUTCOMES / "TASK006_MODEL_SELECTION_LOCK.json"
CAMPAIGN = ARTIFACT_ROOT / "BLIND12_CAMPAIGN.json"
FAILURE_REPORT = OUTCOMES / "TASK006_BLIND_FAILURE_REPORT.json"

FORWARD_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"
OBSERVABLE = "task002.fixed-n0-orders.v3"
CAMPAIGN_ID = "task006_fixed_A05_A07_A09_hw_blind12_v1"

FAILED = (
    {"key": "117.5,17.25/A07", "angle_id": "A07", "grazing_deg": 2.0,
     "azimuth_deg": 90.0, "design_index": 7},
    {"key": "117.5,17.25/A09", "angle_id": "A09", "grazing_deg": 4.0,
     "azimuth_deg": 60.0, "design_index": 8},
)
CANDIDATE_ORDER = (
    "legendre_2", "legendre_3", "legendre_4", "local_rbf_k8",
    "matern52_ard_exact_gp", "degree2_trend_plus_matern52_residual",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def _file_hashes(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): _sha(path)
            for path in sorted(root.rglob("*")) if path.is_file()}


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _extract_one(item: dict[str, Any]) -> dict[str, Any]:
    run_root = ARTIFACT_ROOT / "blind/117.5_17.25" / item["angle_id"]
    formal_path = run_root / "results/task002_full3d_record.json"
    execution_path = run_root / "execution.json"
    summary_path = run_root / "results/run_summary.json"
    driver_path = run_root / "task005_driver_summary.json"
    solver_log = run_root / "results/solver_log.txt"
    progress_path = run_root / "results/progress_3d.jsonl"
    timeline_path = run_root / "watchdog/resource_timeline.jsonl"
    formal = _read(formal_path)
    execution = _read(execution_path)
    summary = _read(summary_path)
    driver = _read(driver_path)
    factor = formal["solver_identity"]["factor_inventory"]
    watchdog = execution["watchdog"]
    preflight = execution["preflight"]
    matrix = summary.get("matrix_stats", {})
    rows = [json.loads(line) for line in progress_path.read_text().splitlines() if line.strip()]
    peak = max(rows, key=lambda row: float(row.get("total_peak_rss_mb") or 0.0))
    after_residual = next((row for row in rows if row.get("stage") == "after_true_residual"), {})
    files = {
        "formal_record": str(formal_path), "execution": str(execution_path),
        "run_summary": str(summary_path), "driver_summary": str(driver_path),
        "solver_log": str(solver_log), "progress": str(progress_path),
        "resource_timeline": str(timeline_path),
    }
    file_hashes = {name: _sha(Path(path)) for name, path in files.items()}
    residual = {
        "relative_residual": formal["observables"]["true_relative_residual"],
        "absolute_residual_norm": summary.get("linear_system_residual_norm"),
        "rhs_norm_denominator": summary.get("linear_system_rhs_norm"),
        "numerator_denominator_semantics": "linear_system_residual_norm / max(linear_system_rhs_norm, 1e-30)",
        "residual_numerator_recorded": summary.get("linear_system_residual_norm") is not None,
        "residual_denominator_recorded": summary.get("linear_system_rhs_norm") is not None,
        "reduced_trace_residual_norm": summary.get("reduced_trace_dtn_residual_norm"),
        "eliminated_cell_interior_residual_norm": summary.get("eliminated_cell_interior_residual_norm"),
        "eliminated_cell_interior_max_abs_residual": summary.get("eliminated_cell_interior_max_abs_residual"),
        "full_operator_residual_method": summary.get("full_operator_residual_method"),
        "gate_limit": 1.0e-9,
        "gate_pass": formal["gates"].get("true_residual_le_1e-9"),
    }
    telemetry = {
        "key": item["key"], "geometry_nm": [117.5, 17.25],
        "illumination": {"angle_id": item["angle_id"], "grazing_deg": item["grazing_deg"],
                         "azimuth_deg": item["azimuth_deg"], "solver_theta_deg": formal["parameters"]["configuration"]["solver_theta_deg"],
                         "solver_phi_deg": formal["parameters"]["configuration"]["solver_phi_deg"]},
        "source_identity": {"forward_solver_sha": formal["source_sha"],
                             "model_id": formal["model_id"], "solver_route_id": formal["solver_route_id"],
                             "observable_schema_version": formal["output_profile"],
                             "actual_observable_schema_version": OBSERVABLE,
                             "source_dirty": formal["source_dirty"]},
        "formal_record_sha256": _sha(formal_path),
        "execution_sha256": _sha(execution_path),
        "driver_summary_sha256": _sha(driver_path),
        "evidence_file_hashes": file_hashes,
        "original_failure_directory_file_hashes": _file_hashes(run_root),
        "residual": residual,
        "ksp": {"actual_ksp_type": summary.get("actual_ksp_type"),
                "pc_factor_solver_type": summary.get("actual_pc_factor_solver_type"),
                "converged": summary.get("ksp_converged"),
                "reason": summary.get("ksp_converged_reason"),
                "reason_name": summary.get("ksp_converged_reason_name"),
                "iterations": summary.get("ksp_iterations"),
                "solver_residual_norm": summary.get("solver_residual_norm")},
        "matrix": {"system_matrix": matrix,
                   "factor_inventory_matrix": factor.get("matrix_stats", {}),
                   "factor_mumps_infog": factor.get("mumps_raw_infog"),
                   "factor_mumps_rinfog": factor.get("mumps_raw_rinfog")},
        "mumps": {"factor_solver": factor.get("factor_solver_type"),
                  "icntl_14_requested_percent": factor.get("mumps_icntl_14_requested_percent"),
                  "icntl_14_observed_percent": factor.get("mumps_icntl_14_observed_percent"),
                  "workspace_relaxation_verified": factor.get("mumps_workspace_relaxation_verified"),
                  "ooc_runtime": summary.get("mumps_ooc_runtime"),
                  "raw_info_semantics": "raw INFOG/RINFOG retained by index; no inferred field names"},
        "resource": {
            "preflight": preflight.get("resources"),
            "watchdog": watchdog,
            "progress_peak": {"stage": peak.get("stage"), "total_peak_rss_mb": peak.get("total_peak_rss_mb"),
                              "total_peak_rss_gb": peak.get("total_peak_rss_gb"),
                              "semantics": peak.get("total_peak_rss_semantics"),
                              "max_rank_historical_peak_rss_mb": peak.get("max_rank_historical_peak_rss_mb"),
                              "swap_used_mb": peak.get("swap_used_mb")},
            "after_true_residual": {"total_peak_rss_mb": after_residual.get("total_peak_rss_mb"),
                                    "max_rank_historical_peak_rss_mb": after_residual.get("max_rank_historical_peak_rss_mb"),
                                    "swap_used_mb": after_residual.get("swap_used_mb")},
            "resource_timeline_samples": len(timeline_path.read_text().splitlines()),
            "peak_rss_pss_uss_source": "watchdog process-tree telemetry",
        },
        "configuration": {
            "mesh_axis_counts": formal["parameters"]["fidelity"]["axis_counts"],
            "degree": formal["parameters"]["fidelity"]["degree"],
            "h_nm": formal["parameters"]["fidelity"]["h_nm"],
            "mpi_ranks": formal["parameters"]["execution"]["mpi_ranks"],
            "threads_per_rank": formal["parameters"]["execution"]["threads_per_rank"],
            "assembly_backend": formal["config_identity"]["assembly_backend"],
            "linear_solver": formal["solver_identity"],
            "petsc_options": formal["solver_identity"].get("requested_petsc_options"),
            "thread_environment": {"OMP_NUM_THREADS": "not_recorded", "OPENBLAS_NUM_THREADS": "not_recorded",
                                    "MKL_NUM_THREADS": "not_recorded", "NUMEXPR_NUM_THREADS": "not_recorded",
                                    "contract_threads_per_rank": 1},
        },
        "gates": formal["gates"],
        "driver_status": driver.get("status"),
    }
    return telemetry


def main() -> int:
    campaign = _read(CAMPAIGN)
    lock = _read(LOCK)
    selection = _read(OUTCOMES / "TRAINING_MODEL_SELECTION_CANDIDATE_V2.json")
    comparison = _read(OUTCOMES / "TRAIN37_MODEL_COMPARISON_V2.json")
    scores = {candidate: comparison["candidates"][candidate]["selection_score"]
              for candidate in CANDIDATE_ORDER}
    tied = [candidate for candidate in CANDIDATE_ORDER if scores[candidate] == 1.0]
    telemetry = {item["key"]: _extract_one(item) for item in FAILED}
    original_hashes = {"campaign": _sha(CAMPAIGN), "failure_report": _sha(FAILURE_REPORT),
                       "lock": _sha(LOCK)}
    telemetry_payload = {
        "schema_version": "task006.blind-forward-failure-telemetry.v1",
        "status": "frozen_read_only",
        "generated_without_fem": True,
        "original_case141_preserved": True,
        "original_evidence_hashes": original_hashes,
        "failed_tuples": telemetry,
        "blind_campaign_status": {"campaign_id": campaign.get("campaign_id"),
                                   "record_count": campaign.get("record_count"),
                                   "pass_count": campaign.get("pass_count"),
                                   "failure_count": campaign.get("failure_count")},
    }
    _write(OUTCOMES / "BLIND_FORWARD_FAILURE_TELEMETRY.json", telemetry_payload)
    tie_payload = {
        "schema_version": "task006.model-selection-tie-audit.v1",
        "status": "frozen_historical_semantics",
        "candidate_order": list(CANDIDATE_ORDER),
        "selection_scores": scores,
        "exact_score_ties": [{"score": 1.0, "candidates": tied}],
        "historical_selected_candidate": selection.get("selected_candidate"),
        "lock_selected_candidate": lock.get("selected_candidate"),
        "selection_basis": selection.get("selection_basis"),
        "tie_break_semantics": "minimum score with fixed candidate order; stable first candidate selected before blind",
        "model_lock_sha256": original_hashes["lock"],
        "blind_response_used_for_tie_break": False,
        "model_lock_modified": False,
    }
    _write(OUTCOMES / "MODEL_SELECTION_TIE_AUDIT.json", tie_payload)
    retry_rows = []
    for item in FAILED:
        attempts = []
        for attempt in (2, 3):
            attempts.append({"attempt": attempt, "status": "not_run",
                             "run_directory": str((RETRY_ARTIFACT_ROOT / "blind_retry" / "117.5_17.25" /
                                                    item["angle_id"] / f"attempt_{attempt}").resolve()),
                             "canonical": attempt == 2, "formal_record_sha256": None,
                             "execution_sha256": None, "sample_path": None})
        retry_rows.append({"key": item["key"], "angle_id": item["angle_id"],
                           "geometry_nm": [117.5, 17.25], "grazing_deg": item["grazing_deg"],
                           "azimuth_deg": item["azimuth_deg"], "original_design_index": item["design_index"],
                           "attempts": attempts})
    retry_payload = {
        "schema_version": "task006.blind-retry-plan.v1",
        "status": "frozen_pending_case143",
        "generated_without_fem": True,
        "failed_tuple_count": 2, "max_retry_fem_count": 4,
        "failed_tuples": retry_rows,
        "original_campaign_sha256": original_hashes["campaign"],
        "original_failure_report_sha256": original_hashes["failure_report"],
        "model_lock_sha256": original_hashes["lock"],
        "identity": {"forward_solver_sha": FORWARD_SHA, "model_id": MODEL_ID,
                      "solver_route_id": ROUTE_ID, "observable_schema_version": OBSERVABLE,
                      "mesh": [6, 4, 14], "degree": 5, "h_nm": 10.0,
                      "mpi_ranks": 2, "threads_per_rank": 1,
                      "mumps_icntl_14": 40, "mumps_icntl_22": 0,
                      "assembly_backend": "assembly_time_static_condensed",
                      "output_profile": "compact_surrogate_record",
                      "residual_gate": 1.0e-9,
                      "same_config_and_observable": True},
        "retry_contract": {"fresh_process": True, "attempts_per_tuple": 2,
                            "no_retry_of_original_directory": True,
                            "no_gate_relaxation": True, "no_solver_change": True,
                            "no_model_change": True, "no_training_or_active_learning": True,
                            "canonical_rule": "first passing repeat (attempt_2) only after both repeats pass; attempt_3 is reproducibility evidence"},
    }
    _write(OUTCOMES / "BLIND_RETRY_PLAN.json", retry_payload)
    telemetry_md = ["# Task006 M3R0 failure telemetry", "", "本文件由原 Case141 失败目录只读提取，未运行 FEM。", "",
                    "| tuple | relative residual | absolute residual norm | RHS denominator | KSP | peak PSS | swap |", "|---|---:|---:|---:|---|---:|---:|"]
    for item in FAILED:
        row = telemetry[item["key"]]
        telemetry_md.append(f"| `{item['key']}` | {row['residual']['relative_residual']:.16e} | {row['residual']['absolute_residual_norm']:.16e} | {row['residual']['rhs_norm_denominator']:.16e} | {row['ksp']['reason_name']} / {row['ksp']['iterations']} | {row['resource']['watchdog']['peak_pss_bytes']/2**30:.3f} GiB | {row['resource']['watchdog']['peak_swap_bytes']} B |")
    telemetry_md += ["", "残差分子/分母和 full-operator residual method 均来自 run_summary；MUMPS INFOG/RINFOG 只按 raw index 保存，未推断字段含义。未记录的 PETSc/thread 环境变量明确标为 `not_recorded`。", ""]
    (OUTCOMES / "BLIND_FORWARD_FAILURE_TELEMETRY.md").write_text("\n".join(telemetry_md))
    tie_md = ["# Task006 model-selection tie audit", "", "模型锁未修改；该审计只记录 blind 前已完成的 training-only 选择语义。", "", "| candidate | training selection score |", "|---|---:|"]
    tie_md += [f"| `{candidate}` | {scores[candidate]:.15g} |" for candidate in CANDIDATE_ORDER]
    tie_md += ["", f"精确并列组：`{', '.join(tied)}`，score=1.0。固定顺序中的首项 `legendre_3` 是历史 selected candidate；不得因盲点响应改变。"]
    (OUTCOMES / "MODEL_SELECTION_TIE_AUDIT.md").write_text("\n".join(tie_md) + "\n")
    print(json.dumps({"status": "m3r0_outputs_written", "failed_tuples": [item["key"] for item in FAILED],
                      "original_campaign_sha256": original_hashes["campaign"],
                      "model_lock_sha256": original_hashes["lock"], "generated_without_fem": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
