"""Independent checker for the Task006 79-solve M1 campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


FORWARD_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"
OBSERVABLE = "task002.fixed-n0-orders.v3"


def check(path: Path) -> tuple[dict[str, bool], list[str]]:
    data = json.loads(path.read_text())
    rows = list(data.get("records", {}).values())
    errors: list[str] = []
    checks = {
        "campaign_identity": bool(data.get("schema_version") == "task006.m1-train37-campaign.v1"
                                   and data.get("campaign_id") == "task006_fixed_A05_A07_A09_hw_train37_p5_ny4_v1"
                                   and data.get("forward_solver_sha") == FORWARD_SHA
                                   and data.get("model_id") == MODEL_ID and data.get("solver_route_id") == ROUTE_ID
                                   and data.get("observable_schema_version") == OBSERVABLE),
        "exact_budget": bool(data.get("status") == "pass" and data.get("new_fem_count") == 79
                              and data.get("expected_new_fem_count") == 79
                              and data.get("record_count") == 111 and len(rows) == 111),
        "reuse_and_new_counts": bool(data.get("reuse_count") == 32
                                      and sum(bool(row.get("reuse")) for row in rows) == 32
                                      and sum(not bool(row.get("reuse")) for row in rows) == 79),
        "no_blind_or_validation": bool(data.get("blind_response_accessed") is False
                                        and data.get("validation_target_accessed") is False),
        "all_new_pass": bool(all(row.get("reuse") or (row.get("status") == "measured_pass"
                                                        and row.get("return_code") == 0
                                                        and row.get("source_sha") == FORWARD_SHA
                                                        and Path(row.get("sample_path", "")).is_file())
                                 for row in rows)),
        "all_reuse_sources_present": bool(all(not row.get("reuse") or Path(row.get("source_path", "")).is_file()
                                               for row in rows)),
        "single_process_identity": bool(data.get("max_parallel_forward_solves") == 1
                                         and data.get("mpi_ranks") == 2 and data.get("threads_per_rank") == 1
                                         and data.get("mumps_icntl_14") == 40),
    }
    if not all(checks.values()):
        errors.extend(f"failed:{key}" for key, value in checks.items() if not value)
    return checks, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", type=Path, default=Path("benchmarks/artifacts/cases/136_task006_train37_forward/M1_TRAIN37_CAMPAIGN.json"))
    parser.add_argument("--output", type=Path, default=Path("benchmarks/cases/136_task006_train37_forward/records/case136_check.json"))
    args = parser.parse_args()
    checks, errors = check(args.campaign.resolve())
    result = {"schema_version": "task006.case136-m1-check.v1", "status": "pass" if all(checks.values()) else "failed", "checks": checks, "errors": errors, "new_fem_count": 79, "blind_response_accessed": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
