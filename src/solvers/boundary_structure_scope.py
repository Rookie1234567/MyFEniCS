"""V38 boundary-only deadlines, complete scope and hash-bound parents."""

import hashlib
import json
from pathlib import Path

from src.solvers.port_preparation_window import PreparationWindow

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "input/task042_neural_coarse_inverse/boundary_structure_v38.json"
ARTIFACT = ROOT / "benchmarks/artifacts/task042/v38"
FE_ROLES = ("BRIDGE", "LAYOUT", "COMPONENT", "ORACLE")


class StructureWindow(PreparationWindow):
    def remaining(self, role):
        self.require_ready()
        runs = self.ledger()["runs"]
        used = sum(r["elapsed_seconds"] for r in runs if r["role"] in FE_ROLES)
        amount = self.component - used if role in FE_ROLES else self.auxiliary
        if role == "ORACLE":
            amount = min(
                amount,
                1200
                - sum(
                    r["elapsed_seconds"]
                    for r in runs
                    if r["role"] in ("BRIDGE", "ORACLE")
                ),
            )
        return min(
            amount,
            self.total - self.reserve - self.charged_wall(),
            self.snapshot()["heavy_remaining_seconds"],
        )


window = StructureWindow(
    ROOT / "tmp/task042/v38",
    label="V38",
    total=7200,
    component=5400,
    auxiliary=600,
    probe=60,
    reserve=180,
    bootstrap=3.0,
)


def plan_record():
    plan = json.loads(PLAN.read_text())
    if (
        plan["review_commit"] != "cf0896e57f9f16970e5af6b55ad14920ab4c7815"
        or plan["target_solve_authorized"] is not False
        or plan["q"] != [30, 60]
        or plan["component_seeds"] != [423801, 423803]
        or plan["cost_ladder"] != [64, 1024, 32060]
    ):
        raise ValueError("V38 immutable authorization")
    for key in ("parent_identity", "parent_capacity"):
        p = Path(plan[key]["path"])
        if hashlib.sha256(p.read_bytes()).hexdigest() != plan[key]["sha256"]:
            raise ValueError("V38 frozen parent identity")
    return plan


def read_stage(name):
    pointer = json.loads((ARTIFACT / (name + ".json")).read_text())
    path = Path(pointer["path"]).resolve()
    if (
        not path.is_relative_to(ARTIFACT)
        or hashlib.sha256(path.read_bytes()).hexdigest() != pointer["sha256"]
    ):
        raise ValueError("V38 stage identity")
    return json.loads(path.read_text()), path


def implementation_hashes():
    files = [
        "src/solvers/" + n + ".py"
        for n in (
            "boundary_structure_scope",
            "boundary_structure_study",
            "directional_boundary",
            "target_boundary_witness",
            "tiled_port_action",
            "port_preparation_window",
        )
    ]
    files += [
        "src/solvers/port_component_study.py",
        "src/io/port_preparation.py",
        "src/runners/port_preparation.py",
        "scripts/run_case.py",
        "benchmarks/qualify_port_preparation.py",
        "benchmarks/check_boundary_witness.py",
        "benchmarks/check_boundary_structure.py",
        "benchmarks/archive_jit_cache.py",
        "src/test/test_boundary_structure.py",
        "src/test/test_boundary_witness.py",
        "src/test/tiled_port_mpi_fixture.py",
        str(PLAN.relative_to(ROOT)),
    ]
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in files}
