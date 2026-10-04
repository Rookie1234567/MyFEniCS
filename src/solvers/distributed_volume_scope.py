"""Review V39 scope: finite witnesses and conditional, exclusive target action."""

import json
from pathlib import Path

from src.runners.task042_shared import write_json
from src.solvers.native_recovery_packets import sha
from src.solvers.port_preparation_window import PreparationWindow

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "input/task042_neural_coarse_inverse/distributed_volume_v42.json"
ARTIFACT = ROOT / "benchmarks/artifacts/task042/v42"
STAGES = (
    "ENVELOPE",
    "CLASSES",
    "ORACLE",
    "VOLUME1",
    "VOLUME2",
    "VOLUME4",
    "RECOVERY2",
    "RECOVERY4",
    "CHECK",
    "TARGET_GATE",
    "TARGET_FORWARD",
    "TARGET_ADJOINT",
    "TARGET_CHECK",
    "DEPLOY",
    "CAPACITY",
)
FINITE = (
    "CLASSES",
    "ORACLE",
    "VOLUME1",
    "VOLUME2",
    "VOLUME4",
    "RECOVERY2",
    "RECOVERY4",
    "CHECK",
    "DEPLOY",
)
TARGET = ("TARGET_GATE", "TARGET_FORWARD", "TARGET_ADJOINT", "TARGET_CHECK")
NATIVE = FINITE + TARGET


class VolumeWindow(PreparationWindow):
    def remaining(self, role):
        self.require_ready()
        runs = self.ledger()["runs"]
        finite = sum(
            r["elapsed_seconds"]
            for r in runs
            if r["role"] in FINITE or r["role"] == "pre"
        )
        target = sum(r["elapsed_seconds"] for r in runs if r["role"] in TARGET)
        return min(
            6000 - finite
            if role in FINITE
            else (7200 if role in TARGET else self.auxiliary),
            7200 - target if role in TARGET else self.total,
            self.total - self.reserve - self.charged_wall(),
            self.snapshot()["heavy_remaining_seconds"],
        )


window = VolumeWindow(
    ROOT / "tmp/task042/v42",
    label="V42",
    total=14400,
    component=6000,
    auxiliary=600,
    probe=90,
    reserve=180,
    bootstrap=0.0,
)


def plan_record():
    p = json.loads(PLAN.read_text())
    if (
        p["review_commit"] != "31774b6282f61280fe33c162f9f48bf4ea526ce6"
        or p["stages"] != list(STAGES)
        or p["target_cells"] != 530856
        or p["target_native_p6_space"]
        or p["target_LU"]
        or p["maximum_new_local_LU"] != 6
    ):
        raise ValueError("V42 frozen authorization")
    for item in p["parents"].values():
        if sha(item["path"]) != item["sha256"]:
            raise ValueError("V42 immutable upstream pointer")
    return p


def stage(name):
    ptr = json.loads((ARTIFACT / (name + ".json")).read_text())
    path = Path(ptr["path"]).resolve()
    if not path.is_relative_to(ARTIFACT) or sha(path) != ptr["sha256"]:
        raise ValueError("V42 stage pointer")
    return json.loads(path.read_text()), path


def reserve_mesh(n):
    path = window.TMP / "mesh_inventory.json"
    r = (
        json.loads(path.read_text())
        if path.exists()
        else {"hex_upper": 0, "attempts": []}
    )
    if n not in (8, 64) or r["hex_upper"] + n > 512:
        raise RuntimeError("V42 native mesh inventory cap")
    r["hex_upper"] += n
    r["attempts"].append({"hex": n, "clock": window.snapshot()})
    write_json(path, r)


def implementation_hashes():
    from src.solvers.native_entity_scope import implementation_hashes as old

    paths = set(old())
    paths.update(
        "src/solvers/" + n + ".py"
        for n in (
            "distributed_volume_scope",
            "distributed_volume_study",
            "distributed_entity_volume",
            "native_entity_qualification",
            "hcurl_affine_isotropic_tensor",
            "native_witness_csr",
            "distributed_saved_recovery",
            "distributed_recovery_study",
        )
    )
    paths.update(
        (
            "benchmarks/check_distributed_volume.py",
            "benchmarks/qualify_distributed_volume.py",
            "src/test/test_distributed_volume.py",
            str(PLAN.relative_to(ROOT)),
        )
    )
    return {p: sha(ROOT / p) for p in sorted(paths)}
