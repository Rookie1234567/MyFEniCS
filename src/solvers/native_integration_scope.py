"""V39 finite-volume integration scope; old scopes are immutable parents."""

import hashlib
import json
from pathlib import Path

from src.runners.task042_shared import write_json
from src.solvers.port_preparation_window import PreparationWindow

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "input/task042_neural_coarse_inverse/native_integration_v39.json"
ARTIFACT = ROOT / "benchmarks/artifacts/task042/v39"
FE_ROLES = ("ADAPTER", "COUPLED")
NATIVE_COST_ROLES = (*FE_ROLES, "basis_audit")
COMPONENT_ROLES = ("EVIDENCE", "ADAPTER", "COUPLED", "CHECK", "DEPLOY")


class IntegrationWindow(PreparationWindow):
    def remaining(self, role):
        self.require_ready()
        native = sum(
            r["elapsed_seconds"]
            for r in self.ledger()["runs"]
            if r["role"] in NATIVE_COST_ROLES
        )
        components = sum(
            r["elapsed_seconds"]
            for r in self.ledger()["runs"]
            if r["role"] in COMPONENT_ROLES
        )
        return min(
            self.component - components if role in COMPONENT_ROLES else self.auxiliary,
            1200 - native if role in NATIVE_COST_ROLES else self.auxiliary,
            self.total - self.reserve - self.charged_wall(),
            self.snapshot()["heavy_remaining_seconds"],
        )


window = IntegrationWindow(
    ROOT / "tmp/task042/v39",
    label="V39",
    total=7200,
    component=5400,
    auxiliary=600,
    probe=60,
    reserve=180,
    bootstrap=3.0,
)


def plan_record():
    row = json.loads(PLAN.read_text())
    if (
        row["review_commit"] != "9430495d8a2cc6870ea1b79cfe4c60889ef5e3db"
        or row["target_solve_authorized"] is not False
        or (
            row["q_boundary"],
            row["q_volume"],
            row["selected_mode_count"],
            row["max_native_hex"],
            row["max_oracle_hex"],
            row["max_local_classes"],
            row["local_cache_bytes"],
        )
        != (30, 15, 12, 64, 8, 16, 256 * 2**20)
        or row["seeds"] != [423901, 423903]
    ):
        raise ValueError("V39 immutable finite-integration authorization")
    for r in row["parents"].values():
        if hashlib.sha256(Path(r["path"]).read_bytes()).hexdigest() != r["sha256"]:
            raise ValueError("V39 frozen parent pointer")
    return row


def parent_stage(name):
    pointer = json.loads(Path(plan_record()["parents"][name]["path"]).read_text())
    path = Path(pointer["path"]).resolve()
    if (
        not path.is_relative_to(ROOT / "benchmarks/artifacts/task042/v38")
        or hashlib.sha256(path.read_bytes()).hexdigest() != pointer["sha256"]
    ):
        raise ValueError("V39 V38 read-only parent result identity")
    return json.loads(path.read_text()), path


def read_stage(name):
    pointer = json.loads((ARTIFACT / (name + ".json")).read_text())
    path = Path(pointer["path"]).resolve()
    if (
        not path.is_relative_to(ARTIFACT)
        or hashlib.sha256(path.read_bytes()).hexdigest() != pointer["sha256"]
    ):
        raise ValueError("V39 phase identity")
    return json.loads(path.read_text()), path


def native_counter(n):
    file = window.TMP / "native_construct_count.json"
    used = json.loads(file.read_text())["count"] if file.exists() else 0
    if used + n > 64:
        raise RuntimeError("V39 cumulative native hex cap")
    write_json(file, {"count": used + n, "charged_before_construction": True})


def reserve_local_classes(maximum):
    """Failure-safe upper charge before the existing LU builder is called."""
    file = window.TMP / "local_class_attempts.json"
    record = (
        json.loads(file.read_text()) if file.exists() else {"upper": 0, "attempts": []}
    )
    if record["upper"] + maximum > 16:
        raise RuntimeError("V39 cumulative independent local LU class upper cap")
    record["upper"] += maximum
    record["attempts"].append(
        {
            "source_sha": __import__("os").environ["TASK042_RUN_SOURCE"],
            "reserved_upper": maximum,
            "actual": None,
        }
    )
    write_json(file, record)
    return len(record["attempts"]) - 1


def settle_local_classes(attempt, actual):
    file = window.TMP / "local_class_attempts.json"
    record = json.loads(file.read_text())
    if not 0 <= actual <= record["attempts"][attempt]["reserved_upper"]:
        raise ValueError("local class constructor exceeded prior bound")
    record["attempts"][attempt]["actual"] = actual
    write_json(file, record)


def implementation_hashes():
    names = [
        "src/solvers/" + n + ".py"
        for n in (
            "native_boundary_adapter",
            "native_integration_scope",
            "native_integration_study",
            "directional_boundary",
            "boundary_structure_study",
            "target_boundary_witness",
            "port_component_study",
            "port_preparation_window",
            "p6_cell_condensed_action",
            "hcurl_assembly_time_condensation",
            "hcurl_canonical_vector_dolfinx",
            "common_3d_forms",
            "target_port_preparation",
        )
    ]
    names += [
        "src/io/port_preparation.py",
        "src/runners/port_preparation.py",
        "scripts/run_case.py",
        "benchmarks/qualify_port_preparation.py",
        "benchmarks/check_boundary_structure.py",
        "benchmarks/check_native_integration.py",
        "src/test/test_native_integration.py",
        "src/test/test_boundary_structure.py",
        str(PLAN.relative_to(ROOT)),
    ]
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in names}
