"""Single-purpose V11 input and frozen physical identity; old inputs are unchanged."""

import json
import tomllib
from pathlib import Path

from src.io.autonomous_neural_head import plan_and_operator
from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.io.task042_profile import ROOT
from src.solvers.neural_fe_action_packet import file_hash

V11_ROOT = ROOT / "benchmarks/artifacts/task042/v11"
PLAN_PATH = ROOT / "input/task042_neural_coarse_inverse/stable_head_varpro_v11.json"
STAGES = {"MAIN": ("ml", 13500), "REPLAY": ("ml", 13500), "VERIFY": ("fe", 900)}


def load_stable_head(path):
    path = Path(path).resolve()
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"[task042_v11]" not in raw:
        return None
    try:
        cfg = tomllib.loads(raw.decode())
        item = cfg["task042_v11"]
        if set(cfg) != {"schema_version", "task042_v11"} or cfg["schema_version"] != 1:
            raise ValueError("V11 explicit input required")
        if set(item) != {"stage", "run_id", "material_table_id"}:
            raise ValueError("V11 stage identity keys mismatch")
        if item["stage"] not in STAGES or item["run_id"] != "task042_v11_" + item["stage"].lower():
            raise ValueError("unregistered V11 one-run inventory")
        plan, design, material, fe = plan_and_operator()
        own_plan = json.loads(PLAN_PATH.read_text())
        if own_plan["original_action_sha256"] != fe["packet"]["sha256"]:
            raise ValueError("original action hash mismatch")
        if own_plan["physical_model_sha256"] != plan["physical_model_sha256"]:
            raise ValueError("physical model hash mismatch")
        if item["material_table_id"] != material.provenance["material_table_id"]:
            raise ValueError("canonical material mismatch")
        mode, timeout = STAGES[item["stage"]]
    except (ValueError, KeyError, OSError, tomllib.TOMLDecodeError) as exc:
        raise InputError(f"Task042 V11 input/identity error: {exc}") from exc
    return RunSpecification(
        identity={"model_id": "task042_v11_fixed_0p7nm_p3_micro", "run_id": item["run_id"], "batch": plan["batch"]},
        geometry=design["geometry"], materials=material.provenance,
        incidence=design["incidence"], discretization=design["finite_element"],
        boundary=design["boundary"],
        method={"kind": "stable_head_varpro_explicit_opt_in"},
        solver={"preconditioner": "task042_v11_" + item["stage"].lower()},
        execution={"mpi_size": 1, "timeout_seconds": timeout, "warning_memory_gib": 12,
                   "terminate_memory_gib": 16, "require_zero_swap": True},
        output={"results_root": "results/task042"},
        derived={"stage": "V11-" + item["stage"], "environment_mode": mode,
                 "plan_sha256": file_hash(PLAN_PATH), "physical_model_complete": True,
                 "physical_operator_sha256": plan["physical_model_sha256"],
                 "identity_hash_meaning": "unchanged canonical V7 action; physical RHS and reference separated"},
        source_path=path, raw_input_bytes=raw, input_sha256=file_hash(path),
        physical_model_sha256=plan["physical_model_sha256"],
        expected_output_parent=ROOT / "results/task042",
    )


def publish(name, result_path):
    V11_ROOT.mkdir(parents=True, exist_ok=True)
    entry = {"path": str(result_path), "sha256": file_hash(result_path)}
    with (V11_ROOT / "index_history.jsonl").open("a") as stream:
        stream.write(json.dumps(dict(name=name, **entry)) + "\n")
    (V11_ROOT / f"{name}.json").write_text(json.dumps(entry, indent=2) + "\n")
    return entry


def read_result(name):
    entry = json.loads((V11_ROOT / f"{name}.json").read_text())
    path = Path(entry["path"]).resolve()
    if not path.is_relative_to(V11_ROOT) or file_hash(path) != entry["sha256"]:
        raise ValueError("V11 result path/hash mismatch")
    value = json.loads(path.read_text())
    if value["plan_sha256"] != file_hash(PLAN_PATH):
        raise ValueError("V11 plan identity changed")
    return value, path
