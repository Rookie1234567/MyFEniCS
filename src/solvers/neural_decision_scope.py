"""V46 scalar-only decisions: zero numerical quota and independent closed ledger."""

import hashlib
import json
from pathlib import Path

from src.solvers.neural_engine_contract import read_metadata
from src.solvers.port_preparation_window import PreparationWindow

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "input/task042_neural_coarse_inverse/neural_deployment_v46.json"
ARTIFACT = ROOT / "benchmarks/artifacts/task042/v46"
window = PreparationWindow(
    ROOT / "tmp/task042/v46",
    label="V46",
    total=900,
    component=0,
    auxiliary=900,
    probe=60,
    reserve=60,
    bootstrap=0,
)


def plan_record():
    plan = json.loads(PLAN.read_text())
    if (
        plan["review_commit"] != "0217f004a38f109a6253923f83a9a24b19d85362"
        or plan["numeric_actions"] != 0
    ):
        raise ValueError("V46 immutable authority/numeric quota")
    if [
        plan[k]
        for k in (
            "new_storage_bytes",
            "task_storage_bytes",
            "free_bytes",
            "evidence_reserve_bytes",
        )
    ] != [64 * 2**20, 24 * 2**30, 50 * 2**30, 256 * 2**20]:
        raise ValueError("V46 storage must match frozen/live plan")
    return plan


def parent(name):
    return read_metadata(plan_record()["parents"][name], ROOT)


def implementation_hashes():
    names = (
        "src/solvers/neural_deployment_cost.py",
        "src/solvers/neural_engine_contract.py",
        "src/solvers/neural_decision_scope.py",
        "src/solvers/full_moment_study.py",
        "src/solvers/full_moment_scope.py",
        "src/runners/port_preparation.py",
        "benchmarks/neural_deployment_decision.py",
        "src/test/test_neural_deployment_decision.py",
        "benchmarks/qualify_neural_deployment.py",
        str(PLAN.relative_to(ROOT)),
    )
    return {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names
    }
