"""Run Task006 M2 training-only grouped CV on train37."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from surrogate.task006.surrogate import run_training_cv  # noqa: E402


def main() -> int:
    result = run_training_cv(
        dataset_root=ROOT / "benchmarks/artifacts/cases/137_task006_train37_dataset/train37",
        outcomes=ROOT / "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes",
    )
    output = ROOT / "benchmarks/cases/138_task006_training_cv/records/case138_run.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
