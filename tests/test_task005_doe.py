"""Pure-Python guards for the completed Task005 compact evidence."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/outcomes"


def test_task005_frozen_design_and_step_lock():
    design = json.loads((OUT / "DISCRETE_ANGLE_DESIGN.json").read_text())
    lock = json.loads((OUT / "PRODUCTION_STEP_LOCK.json").read_text())
    assert design["status"] == "frozen"
    assert design["new_fem_count"] == 0
    assert len(design["points"]) == 16
    assert lock["status"] == "frozen"
    assert lock["selected_steps"] == {"h": "half", "w": "half"}


def test_task005_fisher_exhaustive_counts_and_recommendation():
    ranking = json.loads((OUT / "FISHER_COMBINATION_RANKING.json").read_text())
    assert ranking["combination_counts"] == {"1": 16, "2": 120, "3": 560, "4": 1820}
    assert ranking["recommended_triple"]["angle_ids"] == ["A05", "A07", "A09"]


def test_task005_recovery_gate_and_scope_boundary():
    result = json.loads((OUT / "OFF_CENTRE_RECOVERY.json").read_text())
    lock = json.loads((OUT / "DISCRETE_ILLUMINATION_FISHER_DOE_LOCK.json").read_text())
    assert result["status"] == "pass"
    assert result["primary_gate_all_geometries"] is True
    assert lock["scope_boundary"]["formal_inversion"] is False
    assert lock["scope_boundary"]["task004_blind24_run"] is False
