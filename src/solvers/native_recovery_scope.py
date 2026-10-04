"""V40 independent window and write-ahead bounded native inventory."""

import json
import time
from pathlib import Path

from src.runners.task042_shared import write_json
from src.solvers.native_recovery_packets import sha
from src.solvers.port_preparation_window import PreparationWindow

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "input/task042_neural_coarse_inverse/native_recovery_v40.json"
ARTIFACT = ROOT / "benchmarks/artifacts/task042/v40"
COMPONENT_ROLES = ("PREFLIGHT", "BUILD", "RECOVER", "CHECK", "DEPLOY", "CAPACITY")
NATIVE_ROLES = ("PREFLIGHT", "BUILD", "RECOVER")


class RecoveryWindow(PreparationWindow):
    def native_remaining_inside_worker(self):
        """Debit the live worker too; require_ready intentionally rejects it."""
        self.guard_worker_parent()
        book = self.ledger()
        active = book["active"]
        if active is None or active["role"] != "BUILD":
            raise RuntimeError("native build worker ownership")
        elapsed = time.monotonic() - active["before_clock"]["observed_monotonic"]
        used = sum(
            r["elapsed_seconds"] for r in book["runs"] if r["role"] in NATIVE_ROLES
        )
        return min(2400 - used - elapsed, self.snapshot()["heavy_remaining_seconds"])

    def remaining(self, role):
        self.require_ready()
        runs = self.ledger()["runs"]
        native = sum(r["elapsed_seconds"] for r in runs if r["role"] in NATIVE_ROLES)
        components = sum(
            r["elapsed_seconds"] for r in runs if r["role"] in COMPONENT_ROLES
        )
        return min(
            self.component - components if role in COMPONENT_ROLES else self.auxiliary,
            2400 - native if role in NATIVE_ROLES else self.auxiliary,
            self.total - self.reserve - self.charged_wall(),
            self.snapshot()["heavy_remaining_seconds"],
        )


window = RecoveryWindow(
    ROOT / "tmp/task042/v40",
    label="V40",
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
        row["review_commit"] != "f3bf7942f62e725057c3ae44820bc1ca1794ee59"
        or row["target_solve_authorized"] is not False
        or (
            row["q_boundary"],
            row["q_volume"],
            row["selected_mode_count"],
            row["max_native_hex"],
            row["max_local_classes"],
            row["local_cache_bytes"],
        )
        != (30, 15, 12, 16, 8, 256 * 2**20)
    ):
        raise ValueError("V40 frozen scope")
    for item in row["parents"].values():
        if sha(item["path"]) != item["sha256"]:
            raise ValueError("V40 read-only parent pointer hash")
    return row


def parent_adapter():
    pointer = json.loads(Path(plan_record()["parents"]["ADAPTER"]["path"]).read_text())
    if sha(pointer["path"]) != pointer["sha256"]:
        raise ValueError("V39 adapter result hash")
    return json.loads(Path(pointer["path"]).read_text())


def read_stage(name):
    pointer = json.loads((ARTIFACT / (name + ".json")).read_text())
    p = Path(pointer["path"]).resolve()
    if not p.is_relative_to(ARTIFACT) or sha(p) != pointer["sha256"]:
        raise ValueError("V40 stage pointer identity")
    return json.loads(p.read_text()), p


def charge_native(n):
    p = window.TMP / "native_inventory.json"
    row = json.loads(p.read_text()) if p.exists() else {"hex": 0, "attempts": 0}
    if row["hex"] + n > 16 or row["attempts"] >= 2:
        raise RuntimeError("V40 native/rebuild cap")
    row["hex"] += n
    row["attempts"] += 1
    write_json(p, row)


def reserve_classes(n):
    p = window.TMP / "class_inventory.json"
    row = json.loads(p.read_text()) if p.exists() else {"upper": 0, "attempts": []}
    if row["upper"] + n > 8:
        raise RuntimeError("V40 cumulative local LU cap")
    row["upper"] += n
    row["attempts"].append({"reserved": n, "completed": 0, "settled": False})
    write_json(p, row)
    return len(row["attempts"]) - 1


def settle_class(i, *, complete=False):
    p = window.TMP / "class_inventory.json"
    row = json.loads(p.read_text())
    a = row["attempts"][i]
    if complete:
        row["upper"] -= a["reserved"] - a["completed"]
        a["settled"] = True
    else:
        a["completed"] += 1
        if a["completed"] > a["reserved"]:
            raise RuntimeError("V40 actual class count exceeded bound")
    write_json(p, row)


def implementation_hashes():
    from src.solvers.native_integration_scope import implementation_hashes as old

    names = set(old())
    names.update(
        [
            "src/solvers/native_recovery_" + n + ".py"
            for n in ("scope", "packets", "study")
        ]
    )
    names.update(
        (
            "benchmarks/check_native_recovery.py",
            "benchmarks/archive_native_fixtures.py",
            "src/test/test_native_recovery.py",
            str(PLAN.relative_to(ROOT)),
        )
    )
    return {p: sha(ROOT / p) for p in sorted(names)}
