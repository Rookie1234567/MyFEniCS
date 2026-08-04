"""Independent checker for Task006 M2 training-only outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def check(root: Path) -> tuple[dict[str, bool], list[str]]:
    outcomes = root / "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes"
    errors: list[str] = []
    checks: dict[str, bool] = {}
    try:
        comparison = _read(outcomes / "TRAIN37_MODEL_COMPARISON.json")
        oof = _read(outcomes / "TRAIN37_OOF_PREDICTIONS.json")
        recovery = _read(outcomes / "TRAIN37_SYNTHETIC_RECOVERY.json")
        uncertainty = _read(outcomes / "TRAIN37_UNCERTAINTY.json")
        selection = _read(outcomes / "TRAINING_MODEL_SELECTION_CANDIDATE.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"required_outputs": False}, [f"read failed: {exc}"]
    checks["required_outputs"] = True
    candidates = comparison.get("candidates", {})
    checks["finite_candidate_set"] = bool(set(candidates) >= {"legendre_2", "legendre_3", "legendre_4", "local_rbf_k8", "matern52_ard_exact_gp", "degree2_trend_plus_matern52_residual"})
    checks["selected_from_training_cv"] = bool(selection.get("status") == "training_candidate_review_pending" and selection.get("training_only") is True and selection.get("selected_candidate") in candidates and selection.get("selection_basis"))
    selected_name = selection.get("selected_candidate")
    checks["selected_candidate_cv_gate"] = bool(selected_name in candidates and candidates[selected_name].get("hard_gate") is True)
    checks["oof_grouped_and_complete"] = bool(oof.get("training_only") is True and len(oof.get("records", [])) == 37 * 3 * 5)
    checks["uncertainty_cross_fitted"] = bool(uncertainty.get("cross_fitted") is True and uncertainty.get("training_only") is True)
    checks["recovery_complete"] = bool(recovery.get("training_only") is True and len(recovery.get("records", [])) == 37 and "summary" in recovery and "hard_gate" in recovery)
    checks["synthetic_recovery_gate"] = bool(recovery.get("hard_gate") is True and recovery.get("summary", {}).get("rejected_count") == 0)
    checks["physics_gate_reported"] = bool(all("physics" in value and "hard_gate" in value and "selection_score" in value for value in candidates.values()))
    checks["no_validation_or_blind"] = bool(selection.get("blind_response_accessed") is False and comparison.get("training_only") is True and recovery.get("blind_response_accessed") is False)
    if not all(checks.values()):
        errors.extend(f"failed:{key}" for key, value in checks.items() if not value)
    return checks, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "records/case138_check.json")
    args = parser.parse_args()
    checks, errors = check(args.root.resolve())
    result = {"schema_version": "task006.case138-m2-check.v1", "status": "pass" if all(checks.values()) else "failed", "checks": checks, "errors": errors, "training_only": True, "blind_response_accessed": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
