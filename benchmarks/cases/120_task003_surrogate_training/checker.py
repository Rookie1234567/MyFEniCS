"""Independent Case120 evidence checker."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("surrogate_tasks/task003_p5_ny4_single_fidelity_surrogate_training/outcomes")


def check() -> dict[str, object]:
    m0 = json.loads((ROOT / "M0L_report.json").read_text())
    status = json.loads((ROOT / "TRAINING_STAGE_STATUS.json").read_text())
    cv = json.loads((ROOT / "training_cv.json").read_text())
    oof = json.loads((ROOT / "training_cv_oof.json").read_text())
    assert m0["status"] == "pass"
    assert m0["dataset_verification"]["sample_count"] == 112
    assert m0["dataset_verification"]["training_count"] == 96
    assert m0["dataset_verification"]["frozen_validation_count"] == 16
    assert m0["smoke"]["reproducible"] is True
    assert m0["smoke"]["swap_clean"] is True
    assert m0["frozen_validation_access"]["status"] == "sealed"
    assert status["frozen_validation"] == "sealed_not_accessed"
    assert status["prohibited_work"]["fem_rerun"] is False
    assert cv["selected_candidate"] == "exact_gp:features=B"
    assert cv["validation_target_accessed"] is False
    assert oof["selected_candidate"] == cv["selected_candidate"]
    assert len(oof["records"]) == 2304
    return {"status": "pass", "case_id": "Case120", "training_only": True,
            "model_lock": status["model_selection_lock"]}


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
