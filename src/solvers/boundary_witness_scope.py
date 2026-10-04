"""V37 explicit boundary-only policy, independent of all closed ledgers."""

import hashlib
import json
from pathlib import Path

from src.solvers.port_preparation_window import PreparationWindow

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "input/task042_neural_coarse_inverse/boundary_witness_v37.json"
ARTIFACT = ROOT / "benchmarks/artifacts/task042/v37"
window = PreparationWindow(
    ROOT / "tmp/task042/v37",
    label="V37",
    total=3600,
    component=2400,
    auxiliary=600,
    probe=60,
    reserve=120,
    bootstrap=3.0,
)


def implementation_hashes():
    paths = [
        "src/solvers/bounded_port_provider.py",
        "src/solvers/tiled_port_action.py",
        "src/solvers/port_preparation_window.py",
        "src/solvers/boundary_witness_scope.py",
        "src/solvers/target_boundary_witness.py",
        "src/solvers/solver_consumer_contract.py",
        "src/io/port_preparation.py",
        "src/runners/port_preparation.py",
        "benchmarks/qualify_port_preparation.py",
        "benchmarks/check_boundary_witness.py",
        "benchmarks/archive_jit_cache.py",
        "src/test/test_boundary_witness.py",
        "src/test/tiled_port_mpi_fixture.py",
        "src/test/test_task042_v36_ports.py",
        "scripts/run_case.py",
        str(PLAN.relative_to(ROOT)),
    ]
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}


def read_stage(name):
    pointer = json.loads((ARTIFACT / (name + ".json")).read_text())
    path = Path(pointer["path"]).resolve()
    if (
        not path.is_relative_to(ARTIFACT)
        or hashlib.sha256(path.read_bytes()).hexdigest() != pointer["sha256"]
    ):
        raise ValueError("V37 stage content identity")
    return json.loads(path.read_text()), path
