"""V47 immutable opt-in witness campaign; never reopens a historical ledger."""

import json
import time
from pathlib import Path

from src.runners.task042_shared import write_json
from src.solvers.bound_array_identity import file_hash, read_json
from src.solvers.neural_decision_scope import DecisionWindow

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "input/task042_neural_coarse_inverse/trace_selection_v47.json"
ARTIFACT = ROOT / "benchmarks/artifacts/task042/v47"
STAGES = ("DATA", "ORACLE", "GRADIENT", "TRAIN_NN", "TRAIN_AFFINE", "PREDICT", "CHECK", "ANALYSIS")
SCIENCE = STAGES[:-1]
CAPS = {"actions": 1200, "B_actions": 0}


class SelectionWindow(DecisionWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.CAPS = CAPS

    def launcher_overhead(self):
        probes = {}
        for path in self.TMP.glob("probe_*.json"):
            record = json.loads(path.read_text())
            key = str(Path(record["receipt_path"]).parent)
            probes[key] = probes.get(key, 0.0) + record["elapsed_seconds"]
        seconds = 0.0
        for run in self.ledger()["runs"]:
            folder = Path(run["folder"])
            path = folder / "run_summary.json"
            if not path.exists():
                path = folder / "summary.json"
            if path.exists():
                summary = json.loads(path.read_text())
                seconds += max(0.0, summary["launch_wall_seconds"]-run["elapsed_seconds"]-probes.get(str(folder),0.0))
        return seconds

    def remaining(self, role):
        self.require_ready()
        runs = self.ledger()["runs"]
        science = sum(r["elapsed_seconds"] for r in runs if r["role"] in SCIENCE)
        diagnosis = sum(r["elapsed_seconds"] for r in runs if r["role"] == "ANALYSIS")
        quota = 2400 - science if role in SCIENCE else 180 - diagnosis if role == "ANALYSIS" else self.auxiliary
        return min(quota, self.total - self.reserve - self.charged_wall(), self.snapshot()["heavy_remaining_seconds"])

    def settle(self, summary, folder):
        super().settle(summary, folder)
        book = self.ledger()
        path = folder / "counts.json"
        book["runs"][-1]["numerical_counts"] = json.loads(path.read_text()) if path.exists() else {
            "completed": dict.fromkeys(CAPS, 0), "upper": dict.fromkeys(CAPS, 0)
        }
        book["charged"] = {k: sum(r.get("numerical_counts", {}).get("upper", {}).get(k, 0) for r in book["runs"]) for k in CAPS}
        write_json(self.LEDGER_PATH, book)


window = SelectionWindow(ROOT / "tmp/task042/v47", label="V47", total=3600, component=2400,
                         auxiliary=900, probe=90, reserve=180, bootstrap=0)


def plan_record():
    p = json.loads(PLAN.read_text())
    if p["review_commit"] != "93326fd0e4edc078c51da9af71bdc6f870e93c61" or p["stages"] != list(STAGES):
        raise ValueError("V47 frozen authority/stage inventory")
    if [p[k] for k in ("new_storage_bytes", "task_storage_bytes", "free_bytes", "evidence_reserve_bytes")] != [2**30, 24*2**30, 50*2**30, 256*2**20]:
        raise ValueError("V47 frozen storage inventory")
    return p


def parent(name):
    return read_json(plan_record()["parents"][name], ROOT)


def stage(name):
    pointer = json.loads((ARTIFACT / (name + ".json")).read_text())
    path = Path(pointer["path"]).resolve()
    if not path.is_relative_to(ARTIFACT):
        raise ValueError("V47 stage path")
    return read_json(pointer, ROOT)


def implementation_hashes():
    names = ["scripts/run_case.py", "scripts/activate_task042.sh", "src/io/port_preparation.py",
             "src/runners/port_preparation.py", "src/runners/task042_shared.py",
             "benchmarks/subreaper_watchdog.py", "src/solvers/port_preparation_window.py",
             "src/solvers/neural_decision_scope.py", "src/solvers/trace_selection_scope.py",
             "src/solvers/bound_array_identity.py", "src/solvers/trace_subspace_selection.py",
             "src/solvers/trace_selection_study.py", "benchmarks/check_trace_selection.py",
             "benchmarks/qualify_trace_selection.py", "benchmarks/collect_trace_selection.py", "src/test/test_trace_selection.py",
             str(PLAN.relative_to(ROOT))]
    return {n: file_hash(ROOT / n) for n in names}


class ActionBudget:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.path = self.folder / "counts.json"
        self.counts = {key: dict.fromkeys(CAPS, 0) for key in ("completed", "upper")}
        self.used = {k: sum(r.get("numerical_counts", {}).get("upper", {}).get(k, 0) for r in window.ledger()["runs"]) for k in CAPS}
        write_json(self.path, self.counts)

    def call(self, function, x, *, kind="A"):
        n = 1 if x.ndim == 1 else x.shape[1]
        if self.used["actions"] + self.counts["upper"]["actions"] + n > CAPS["actions"]:
            raise RuntimeError("V47 original per-RHS action cap")
        window.require_live(margin=3600)
        self.counts["upper"]["actions"] += int(n)
        write_json(self.path, self.counts)
        began = time.perf_counter()
        out = function(x)
        self.counts["completed"]["actions"] += int(n)
        write_json(self.path, self.counts)
        with (self.folder / "action_calls.jsonl").open("a") as stream:
            stream.write(json.dumps({"kind": kind, "RHS": int(n), "seconds": time.perf_counter()-began}) + "\n")
        return out
