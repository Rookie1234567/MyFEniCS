"""Case133 integrity checker for the frozen nine-state recovery campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


FORWARD_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
ANGLES = ["A05", "A07", "A09"]
GEOMETRIES = ["G1", "G2", "G3"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outcomes", type=Path, default=Path("surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/outcomes"))
    parser.add_argument("--artifact-root", type=Path, default=Path("benchmarks/artifacts/cases/133_task005_off_centre_recovery"))
    parser.add_argument("--output", type=Path, default=Path("benchmarks/cases/133_task005_off_centre_recovery/records/case133_check.json"))
    args = parser.parse_args()
    out = args.outcomes.resolve(); artifacts = args.artifact_root.resolve()
    checks: dict[str, bool] = {}; errors: list[str] = []
    try:
        design = json.loads((out / "OFF_CENTRE_RECOVERY_DESIGN.json").read_text())
        result = json.loads((out / "OFF_CENTRE_RECOVERY.json").read_text())
        campaign = json.loads((out / "M4_RECOVERY_CAMPAIGN.json").read_text())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"schema_version": "task005.case133-check.v1", "status": "failed"}
        checks["required_outputs"] = False; errors.append(str(exc))
    else:
        checks["required_outputs"] = True
        checks["design_identity"] = bool(
            design.get("status") == "frozen" and design.get("selected_angle_ids") == ANGLES
            and set(design.get("test_geometries", {})) == set(GEOMETRIES)
            and design.get("forward_solver_sha") == FORWARD_SHA
        )
        checks["campaign_identity"] = bool(
            campaign.get("status") == "pass" and campaign.get("new_fem_count") == 9
            and campaign.get("validation_target_accessed") is False
            and len(campaign.get("records", {})) == 9
            and all(row.get("status") == "measured_pass" for row in campaign["records"].values())
        )
        checks["recovery_gate"] = bool(
            result.get("status") == "pass" and result.get("primary_gate_all_geometries") is True
            and set(result.get("geometries", {})) == set(GEOMETRIES)
            and all(result["geometries"][gid]["primary_gate"] for gid in GEOMETRIES)
        )
        checks["error_bounds"] = bool(all(
            result["geometries"][gid]["contracts"]["M1_order_total_robust"]["N1"]["absolute_height_error_nm"] <= 0.5
            and result["geometries"][gid]["contracts"]["M1_order_total_robust"]["N1"]["absolute_width_error_nm"] <= 0.1
            for gid in GEOMETRIES
        ))
        if not all(checks.values()):
            errors.extend(f"failed:{key}" for key, value in checks.items() if not value)
    payload = {"schema_version": "task005.case133-check.v1", "status": "pass" if all(checks.values()) else "failed", "checks": checks, "errors": errors, "new_fem_count": 9, "validation_target_accessed": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
