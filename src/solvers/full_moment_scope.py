"""Review V42 V45 immutable scope; old windows are never resumed."""

import json
from pathlib import Path

from src.solvers.native_recovery_packets import sha
from src.solvers.neighborhood_late_error_scope import ActionBudget as BaseBudget
from src.solvers.neighborhood_late_error_scope import NeuralWindow

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "benchmarks/artifacts/task042/v45"
PLAN = ROOT / "input/task042_neural_coarse_inverse/full_moment_hierarchy_v45.json"
STAGES = (
    "SETUP",
    "DATA",
    "GRADIENT",
    "TRAIN_LH",
    "TRAIN_NL",
    "TRAIN_NH",
    "EVAL_R0",
    "EVAL_CL44",
    "EVAL_LH",
    "EVAL_NL",
    "EVAL_NH",
    "CHECK",
    "TIMING_NN",
    "TIMING_CONTROL",
    "DIAGNOSTIC",
)
CAPS = {"actions": 12000, "B_actions": 0}
window = NeuralWindow(
    ROOT / "tmp/task042/v45",
    label="V45",
    total=7200,
    component=5400,
    auxiliary=600,
    probe=90,
    reserve=180,
    bootstrap=0.0,
)
window.learning_stages = STAGES[:-1]


def plan_record():
    p = json.loads(PLAN.read_text())
    if p["review_commit"] != "2e5bfc593716d82ccbca4cc2061b50fe491186cd" or p[
        "stages"
    ] != list(STAGES):
        raise ValueError("V45 review/stage identity")
    if (
        p["new_storage_bytes"],
        p["task_storage_bytes"],
        p["evidence_reserve_bytes"],
    ) != (4 * 2**30, 24 * 2**30, 256 * 2**20):
        raise ValueError("V45 immutable storage plan must reach live watchdog")
    seeds = [s for v in p["split"].values() for s in v["seeds"]]
    if (
        len(seeds) != 28
        or len(set(seeds)) != 28
        or any(s in range(424801, 425009) for s in seeds)
    ):
        raise ValueError("V45 unique fresh split")
    for r in p["parents"].values():
        if sha(r["path"]) != r["sha256"]:
            raise ValueError("V45 immutable parent bytes")
    return p


def parent(name):
    row = plan_record()["parents"][name]
    return json.loads(Path(row["path"]).read_text())


def stage(name):
    pointer = json.loads((ARTIFACT / (name + ".json")).read_text())
    path = Path(pointer["path"]).resolve()
    if not path.is_relative_to(ARTIFACT) or sha(path) != pointer["sha256"]:
        raise ValueError("V45 committed stage identity")
    return json.loads(path.read_text()), path


def implementation_hashes():
    from src.solvers.neighborhood_late_error_scope import (
        implementation_hashes as legacy,
    )

    paths = list(legacy()) + [
        "src/solvers/full_moment_hierarchy.py",
        "src/solvers/full_moment_scope.py",
        "src/solvers/full_moment_study.py",
        "src/solvers/neighborhood_pilot_workflow.py",
        "src/test/test_full_moment_hierarchy.py",
        "benchmarks/qualify_full_moment.py",
        "benchmarks/check_full_moment.py",
        str(PLAN.relative_to(ROOT)),
    ]
    return {p: sha(ROOT / p) for p in paths}


class ActionBudget(BaseBudget):
    def __init__(self, folder):
        super().__init__(folder, campaign=window, caps=CAPS)
