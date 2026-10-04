"""V41 immutable clock, owner stages and mesh write-ahead inventory."""

import ctypes
import json
import os
import signal
from pathlib import Path

from src.runners.task042_shared import write_json
from src.solvers.native_recovery_packets import sha
from src.solvers.port_preparation_window import PreparationWindow

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "input/task042_neural_coarse_inverse/native_entities_v41.json"
ARTIFACT = ROOT / "benchmarks/artifacts/task042/v41"
STAGES = (
    "ENVELOPE",
    "BRIDGE1",
    "BRIDGE2",
    "BRIDGE4",
    "TOPOLOGY",
    "ORIENTATION",
    "ROUTING",
    "CHECK",
    "DEPLOY",
    "CAPACITY",
)
NATIVE = (
    "BRIDGE1",
    "BRIDGE2",
    "BRIDGE4",
    "TOPOLOGY",
    "ORIENTATION",
    "ROUTING",
    "DEPLOY",
)
TARGET = ("TOPOLOGY", "ORIENTATION", "ROUTING", "DEPLOY")


class EntityWindow(PreparationWindow):
    def remaining(self, role):
        self.require_ready()
        runs = self.ledger()["runs"]
        # Conservatively include all ABI/MPI owner-focused auxiliary checks
        # in the 4800s native subbudget, not only formal stage labels.
        used = sum(r["elapsed_seconds"] for r in runs if r["role"] != "archive")
        target = sum(r["elapsed_seconds"] for r in runs if r["role"] in TARGET)
        return min(
            4800 - used if role in NATIVE else self.auxiliary,
            2400 - target if role in TARGET else self.total,
            self.total - self.reserve - self.charged_wall(),
            self.snapshot()["heavy_remaining_seconds"],
        )


window = EntityWindow(
    ROOT / "tmp/task042/v41",
    label="V41",
    total=7200,
    component=4800,
    auxiliary=600,
    probe=90,
    reserve=180,
    bootstrap=3.0,
)


def guard_entity_worker(active_window=None):
    """MPI rank's immediate parent is not the supervision process."""
    (active_window or window).require_live(margin=1)
    pid = int(os.environ["TASK042_WATCHDOG_PARENT_PID"])
    os.kill(pid, 0)
    parent = os.getppid()
    ancestor = parent
    for _ in range(32):
        if ancestor == pid:
            break
        if ancestor <= 1:
            raise RuntimeError("V41 MPI rank is not a descendant of own supervisor")
        stat = Path(f"/proc/{ancestor}/stat").read_text().rsplit(")", 1)[1].split()
        ancestor = int(stat[1])
    else:
        raise RuntimeError("V41 supervisor ancestor chain exceeded")
    # Kernel parent-death plus the independent whole-tree supervisor. MPI's
    # own parent is monitored, without mistaking it for the launcher.
    if ctypes.CDLL(None).prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        raise RuntimeError("V41 parent-death guard failed")
    if os.getppid() != parent:
        raise RuntimeError("V41 MPI parent died during guard")
    rank = int(os.environ.get("OMPI_COMM_WORLD_RANK", "0"))
    cpus = list(map(int, os.environ["TASK042_RANK_CPUS"].split(",")))
    if rank >= len(cpus):
        raise RuntimeError("V41 rank has no admitted physical core")
    os.sched_setaffinity(0, {cpus[rank]})


def plan_record():
    p = json.loads(PLAN.read_text())
    if (
        p["review_commit"] != "718c42ef2be1ce375f940a5092ad503ab3729d5a"
        or p["target_p6_space_authorized"]
        or p["new_LU_authorized"]
        or p["fixture_hex"] != 64
        or p["max_mesh_hex"] != 512
        or p["target_cells"] != 530856
        or p["stages"] != list(STAGES)
    ):
        raise ValueError("V41 frozen authorization")
    for item in p["parents"].values():
        if sha(item["path"]) != item["sha256"]:
            raise ValueError("V41 immutable parent pointer")
    return p


def mesh_reservation(n, *, target=False):
    p = window.TMP / "mesh_inventory.json"
    r = (
        json.loads(p.read_text())
        if p.exists()
        else {"fixture_hex_upper": 0, "target_attempts": 0, "attempts": []}
    )
    if target:
        if n != 530856 or r["target_attempts"] >= 2:
            raise RuntimeError("V41 target construction cap")
        r["target_attempts"] += 1
    else:
        if n != 64 or r["fixture_hex_upper"] + n > 512:
            raise RuntimeError("V41 finite mesh cap")
        r["fixture_hex_upper"] += n
    r["attempts"].append({"hex": n, "target": target, "clock": window.snapshot()})
    write_json(p, r)


def stage(name):
    ptr = json.loads((ARTIFACT / (name + ".json")).read_text())
    path = Path(ptr["path"]).resolve()
    if not path.is_relative_to(ARTIFACT) or sha(path) != ptr["sha256"]:
        raise ValueError("V41 stage pointer")
    return json.loads(path.read_text()), path


def implementation_hashes():
    names = [
        "src/solvers/native_entity_" + n + ".py"
        for n in ("scope", "protocol", "dependencies", "study", "topology", "adapter")
    ]
    names += [
        "benchmarks/check_native_entities.py",
        "benchmarks/qualify_native_entities.py",
        "src/test/test_native_entities.py",
        "src/runners/port_preparation.py",
        "src/io/port_preparation.py",
        "scripts/run_case.py",
        "src/constraints/high_order_floquet_trace.py",
        "src/constraints/floquet_3d_high_order.py",
        "src/constraints/floquet_3d.py",
        "src/solvers/directional_boundary.py",
        "src/solvers/native_recovery_packets.py",
        "scripts/activate_task042.sh",
        str(PLAN.relative_to(ROOT)),
    ]
    return {p: sha(ROOT / p) for p in sorted(names)}
