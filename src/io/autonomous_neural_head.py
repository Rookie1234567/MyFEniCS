"""Explicit finite V10 paths over the unchanged, hash-qualified pilot."""

import json
from pathlib import Path

import tomllib

from src.io.input_loader import InputError
from src.io.neural_fe_calibration import frozen_plan
from src.io.run_specification import RunSpecification
from src.io.task042_profile import ROOT
from src.solvers.neural_fe_action_packet import file_hash

PLAN_PATH = ROOT / "input/task042_neural_coarse_inverse/autonomous_head_v10.json"
V10_ROOT = ROOT / "benchmarks/artifacts/task042/v10"
STAGES = {
    "A": ("fe", 900),
    "B1": ("ml", 3600),
    "B0": ("ml", 3600),
    "C": ("fe", 1800),
    "E1": ("ml", 2700),
    "E2": ("ml", 2700),
    "VERIFY": ("fe", 600),
    "D1": ("fe", 1200),
    "D2": ("fe", 1200),
    "P4": ("fe", 3600),
}


def plan_and_operator():
    plan = json.loads(PLAN_PATH.read_text())
    _, design, material, fe = frozen_plan()
    if (
        plan["action_packet_sha256"] != fe["packet"]["sha256"]
        or plan["physical_model_sha256"] != fe["physical"]["physical_model_sha256"]
        or plan["mode_manifest_sha256"] != fe["physical"]["mode_manifest_sha256"]
    ):
        raise ValueError("reviewed original pilot/operator identity changed")
    return plan, design, material, fe


def load_autonomous(path):
    path = Path(path).resolve()
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"[task042_v10]" not in raw:
        return None
    try:
        cfg = tomllib.loads(raw.decode())
        item = cfg["task042_v10"]
        if (
            set(cfg) != {"schema_version", "task042_v10"}
            or cfg["schema_version"] != 1
            or set(item) != {"stage", "candidate", "run_id", "material_table_id"}
            or item["stage"] not in STAGES
            or Path(item["run_id"]).name != item["run_id"]
            or not item["run_id"].startswith("task042_v10_")
        ):
            raise ValueError("one registered V10 path per dat required")
        if item["candidate"] not in {"A", "B1", "B0", "C", "E1", "E2", "NONE"}:
            raise ValueError("unregistered candidate inventory")
        if (
            item["stage"] in {"A", "B1", "B0", "C", "E1", "E2"}
            and item["candidate"] != item["stage"]
        ):
            raise ValueError("stage/candidate mismatch")
        plan, design, material, _ = plan_and_operator()
        if item["material_table_id"] != material.provenance["material_table_id"]:
            raise ValueError("canonical material id mismatch")
        mode, timeout = STAGES[item["stage"]]
    except (ValueError, OSError, KeyError, tomllib.TOMLDecodeError) as error:
        raise InputError(f"Task042 V10 identity/input error: {error}") from error
    return RunSpecification(
        identity={
            "model_id": "task042_v10_fixed_0p7nm_p3_micro",
            "run_id": item["run_id"],
            "batch": plan["batch"],
        },
        geometry=design["geometry"],
        materials=material.provenance,
        incidence=design["incidence"],
        discretization=design["finite_element"],
        boundary=design["boundary"],
        method={"kind": "autonomous_neural_head_research_explicit_opt_in"},
        solver={"preconditioner": "task042_v10_" + item["stage"].lower()},
        execution={
            "mpi_size": 1,
            "timeout_seconds": timeout,
            "warning_memory_gib": 12,
            "terminate_memory_gib": 16,
            "require_zero_swap": True,
        },
        output={"results_root": "results/task042"},
        derived={
            "stage": "V10-" + item["stage"],
            "environment_mode": mode,
            "plan_sha256": file_hash(PLAN_PATH),
            "physical_model_complete": True,
            "physical_operator_sha256": plan["physical_model_sha256"],
            "identity_hash_meaning": "unchanged canonical V7 operator; no reference in unlabelled solver",
            "candidate": item["candidate"],
        },
        source_path=path,
        raw_input_bytes=raw,
        input_sha256=file_hash(path),
        physical_model_sha256=plan["physical_model_sha256"],
        expected_output_parent=ROOT / "results/task042",
    )


def publish(name, path):
    V10_ROOT.mkdir(parents=True, exist_ok=True)
    entry = {"path": str(path), "sha256": file_hash(path)}
    # A later permitted minimal replay never overwrites its original result.
    # The append-only index history retains every publication.
    with (V10_ROOT / "index_history.jsonl").open("a") as stream:
        stream.write(json.dumps(dict(name=name, **entry)) + "\n")
    (V10_ROOT / (name + ".json")).write_text(json.dumps(entry, indent=2) + "\n")


def read_result(name):
    entry = json.loads((V10_ROOT / (name + ".json")).read_text())
    path = Path(entry["path"]).resolve()
    if not path.is_relative_to(V10_ROOT) or file_hash(path) != entry["sha256"]:
        raise ValueError("V10 artifact ownership/hash mismatch")
    value = json.loads(path.read_text())
    if value["plan_sha256"] != file_hash(PLAN_PATH):
        raise ValueError("V10 frozen plan identity changed")
    return value, path
