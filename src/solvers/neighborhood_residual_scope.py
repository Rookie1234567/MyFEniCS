"""Review V40: immutable V43 neural pilot, with original-action accounting."""

import json
import os
import time
from pathlib import Path

from src.runners.task042_shared import write_json
from src.solvers.native_recovery_packets import sha
from src.solvers.port_preparation_window import PreparationWindow

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "benchmarks/artifacts/task042/v43"
PLAN = ROOT / "input/task042_neural_coarse_inverse/neighborhood_residual_v43.json"
STAGES = (
    "SETUP",
    "RECOVERY",
    "DATA",
    "GRADIENT",
    "TRAIN_NN",
    "TRAIN_LIN",
    "EVALUATE",
    "CHECK",
)
LEARNING = ("SETUP", "DATA", "GRADIENT", "TRAIN_NN", "TRAIN_LIN", "EVALUATE")
CAPS = {"actions": 6000, "B_actions": 24}


class NeuralWindow(PreparationWindow):
    def remaining(self, role):
        self.require_ready()
        runs = self.ledger()["runs"]
        learn = sum(r["elapsed_seconds"] for r in runs if r["role"] in LEARNING)
        recovery = sum(r["elapsed_seconds"] for r in runs if r["role"] == "RECOVERY")
        return min(
            5400 - learn
            if role in LEARNING
            else (180 - recovery if role == "RECOVERY" else self.auxiliary),
            self.total - self.reserve - self.charged_wall(),
            self.snapshot()["heavy_remaining_seconds"],
        )

    def worker_learning_remaining(self):
        """Forecast inside the active worker without admitting a second actor."""
        self.guard_worker_parent()
        book = self.ledger()
        active = book.get("active")
        if (
            not active
            or Path(active["folder"]).resolve()
            != Path(os.environ["TASK042_V36_AUX_DIRECTORY"]).resolve()
        ):
            raise RuntimeError("V43 forecast must belong to its active worker")
        elapsed = time.monotonic() - active["before_clock"]["observed_monotonic"]
        learn = sum(r["elapsed_seconds"] for r in book["runs"] if r["role"] in LEARNING)
        if active["role"] in LEARNING:
            learn += elapsed
        return min(
            5400 - learn,
            self.total - self.reserve - self.charged_wall() - elapsed,
            self.snapshot()["heavy_remaining_seconds"],
        )

    def settle(self, summary, folder):
        super().settle(summary, folder)
        p = folder / "counts.json"
        counts = (
            json.loads(p.read_text())
            if p.exists()
            else {"completed": dict.fromkeys(CAPS, 0), "upper": dict.fromkeys(CAPS, 0)}
        )
        book = self.ledger()
        book["runs"][-1]["numerical_counts"] = counts
        write_json(self.LEDGER_PATH, book)


window = NeuralWindow(
    ROOT / "tmp/task042/v43",
    label="V43",
    total=7200,
    component=5400,
    auxiliary=600,
    probe=90,
    reserve=180,
    bootstrap=0.0,
)


def plan_record():
    p = json.loads(PLAN.read_text())
    if p["review_commit"] != "84c38b882795c56fead54d75cd56389262c86e31" or p[
        "stages"
    ] != list(STAGES):
        raise ValueError("V43 authorization identity")
    for item in p["parents"].values():
        if sha(item["path"]) != item["sha256"]:
            raise ValueError("immutable neural pilot parent")
    return p


def parent(name):
    p = plan_record()["parents"][name]
    return json.loads(Path(p["path"]).read_text())


def stage(name):
    ptr = json.loads((ARTIFACT / (name + ".json")).read_text())
    path = Path(ptr["path"]).resolve()
    if not path.is_relative_to(ARTIFACT) or sha(path) != ptr["sha256"]:
        raise ValueError("V43 committed stage identity")
    return json.loads(path.read_text()), path


def implementation_hashes():
    paths = [
        "scripts/run_case.py",
        "scripts/activate_task042.sh",
        "src/io/port_preparation.py",
        "src/runners/port_preparation.py",
        "src/runners/task042_shared.py",
        "src/solvers/port_preparation_window.py",
        "src/solvers/neighborhood_residual_scope.py",
        "src/solvers/neighborhood_residual_core.py",
        "src/solvers/neighborhood_residual_study.py",
        "src/solvers/neighborhood_residual_models.py",
        "src/solvers/isolated_ml_sparse.py",
        "src/solvers/distributed_entity_volume.py",
        "src/solvers/neighborhood_port_gradient.py",
        "src/solvers/neighborhood_recovery_diagnostic.py",
        "src/solvers/native_entity_adapter.py",
        "src/solvers/native_recovery_packets.py",
        "benchmarks/check_neighborhood_residual.py",
        "src/test/test_neighborhood_residual.py",
        "benchmarks/qualify_neighborhood_residual.py",
        "benchmarks/qualified_ml_pytest.py",
        str(PLAN.relative_to(ROOT)),
    ]
    return {p: sha(ROOT / p) for p in paths}


class ActionBudget:
    """Write ahead before each *RHS* action, including rejected and failed calls."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self.path = self.folder / "counts.json"
        self.counts = {
            "completed": dict.fromkeys(CAPS, 0),
            "upper": dict.fromkeys(CAPS, 0),
        }
        self.used = {
            k: sum(
                r.get("numerical_counts", {}).get("upper", {}).get(k, 0)
                for r in window.ledger()["runs"]
            )
            for k in CAPS
        }
        write_json(self.path, self.counts)

    def call(self, function, x, *, kind="A", key="actions"):
        n = 1 if x.ndim == 1 else x.shape[1]
        if self.used[key] + self.counts["upper"][key] + n > CAPS[key]:
            raise RuntimeError("V43 immutable original action cap")
        window.require_live(margin=180)
        self.counts["upper"][key] += int(n)
        write_json(self.path, self.counts)
        began = time.perf_counter()
        out = function(x)
        self.counts["completed"][key] += int(n)
        write_json(self.path, self.counts)
        with (self.folder / "action_calls.jsonl").open("a") as f:
            f.write(
                json.dumps(
                    {
                        "kind": kind,
                        "RHS": int(n),
                        "seconds": time.perf_counter() - began,
                        "completed": dict(self.counts["completed"]),
                    }
                )
                + "\n"
            )
        return out
