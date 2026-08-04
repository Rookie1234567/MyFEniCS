"""Run Task006 M2R training-only CV with S0-authoritative S1."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from surrogate.task006.m2r import run_m2r  # noqa: E402


def main() -> int:
    result = run_m2r(
        dataset_root=ROOT / "benchmarks/artifacts/cases/137_task006_train37_dataset/train37",
        outcomes=ROOT / "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes",
    )
    output = ROOT / "benchmarks/cases/139_task006_m2r_contract_replay/records/case139_run.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") == "m2r_training_qualified_pending_lock" else 2


if __name__ == "__main__":
    raise SystemExit(main())
