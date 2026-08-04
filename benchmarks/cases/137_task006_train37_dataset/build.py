"""Build the Task006 immutable train37 package after M1 passes."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from surrogate.task006.dataset import DATASET_ROOT, build_dataset  # noqa: E402


def main() -> int:
    manifest = build_dataset(
        manifest_path=ROOT / "benchmarks/artifacts/cases/136_task006_train37_forward/M1_TRAIN37_CAMPAIGN.json",
        output_root=ROOT / DATASET_ROOT,
    )
    result = {
        "schema_version": "task006.case137-dataset-build.v1",
        "status": "pass",
        "dataset_id": manifest["dataset_id"],
        "dataset_root": str((ROOT / DATASET_ROOT).resolve()),
        "record_count": manifest["record_count"],
        "reuse_record_count": manifest["reuse_record_count"],
        "new_fem_record_count": manifest["new_fem_record_count"],
        "blind_response_accessed": False,
    }
    output = ROOT / "benchmarks/cases/137_task006_train37_dataset/records/case137_build.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
