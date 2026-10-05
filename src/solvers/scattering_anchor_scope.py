"""V49 complete finite scattering anchor, separate from all closed ledgers."""
import hashlib
import json
from pathlib import Path

from src.solvers.neural_decision_scope import DecisionWindow

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "input/task042_neural_coarse_inverse/scattering_anchor_v49.json"
ARTIFACT = ROOT / "benchmarks/artifacts/task042/v49"
STAGES = ("PREFLIGHT", "REFERENCE_REGULAR", "REFERENCE_NOTCH", "ENGINE_REGULAR",
          "ENGINE_NOTCH", "VERIFY_P4", "REFERENCE_NOTCH_P5", "COST")


class AnchorWindow(DecisionWindow):
    def remaining(self, role):
        self.require_ready()
        # Actual supervised runtime, rejected probes, tests and replays all paid.
        return min(3600 if role in STAGES else 900,
                   self.total - self.charged_wall(),
                   self.snapshot()["heavy_remaining_seconds"])


window = AnchorWindow(ROOT / "tmp/task042/v49", label="V49", total=18000,
                      component=18000, auxiliary=18000, probe=120,
                      reserve=600, bootstrap=0)


def plan_record():
    p = json.loads(PLAN.read_text())
    if p["review_commit"] != "0b0e6b236aa1a7205f453841a0a41e209656ed98" or p["stages"] != list(STAGES):
        raise ValueError("V49 authority/stage inventory")
    if [p[k] for k in ("new_storage_bytes", "task_storage_bytes", "free_bytes", "evidence_reserve_bytes")] != [4*2**30, 28*2**30, 50*2**30, 256*2**20]:
        raise ValueError("V49 frozen storage/live limits")
    return p


def implementation_hashes():
    paths = ["scripts/run_case.py", "scripts/activate_task042.sh", "src/io/scattering_anchor.py",
             "src/runners/port_preparation.py", "src/runners/task042_shared.py",
             "src/solvers/scattering_anchor_scope.py", "src/solvers/scattering_anchor.py",
             "src/solvers/scattering_y_orbit_reuse.py", "src/solvers/scattering_anchor_two_cell.py", "src/solvers/scattering_anchor_checks.py", "src/solvers/scattering_anchor_reporting.py", "benchmarks/subreaper_watchdog.py",
             "benchmarks/qualify_scattering_anchor.py", "src/test/test_scattering_anchor.py", str(PLAN.relative_to(ROOT)),
             "input/materials/si_optical_constants_v1.json"]
    # Bind the complete local public FE/PETSc code used by this new anchor.
    p = plan_record()
    paths += p["local_numeric_closure"]
    return {n: hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(paths))}


def stage(name):
    pointer = json.loads((ARTIFACT / (name + ".json")).read_text())
    path = Path(pointer["path"])
    if not path.resolve().is_relative_to(ARTIFACT) or hashlib.sha256(path.read_bytes()).hexdigest() != pointer["sha256"]:
        raise ValueError("V49 stage pointer path/hash")
    return json.loads(path.read_text())
