"""V36 preparation-only one-run inputs; no target solver dispatch exists."""

import hashlib
import json
import re
from pathlib import Path

import tomllib

from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.solvers.target_port_preparation import ROOT, geometry_contract, target_config

PLAN = ROOT / "input/task042_neural_coarse_inverse/port_preparation_v36.json"
ARTIFACT = ROOT / "benchmarks/artifacts/task042/v36"
STAGES = ("INVENTORY", "COMPONENT", "CHECK", "DEPLOY")


def load_preparation(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    if b"[task042_v36]" not in raw:
        return None
    try:
        value = tomllib.loads(raw.decode())
        item = value["task042_v36"]
        if (
            set(value) != {"schema_version", "task042_v36"}
            or value["schema_version"] != 1
            or set(item) != {"stage", "run_id"}
            or item["stage"] not in STAGES
            or not re.fullmatch("task042_v36_[a-z0-9_]+", item["run_id"])
        ):
            raise ValueError("V36 preparation-only explicit stage schema")
        cfg, material = target_config()
        contract = geometry_contract(cfg, material)
        plan = json.loads(PLAN.read_text())
        if (
            plan["review_commit"] != "cc5d9823a66fb5090618705114093998a647e40c"
            or plan["component_seeds"] != [423611, 423613]
            or plan["target_solve_authorized"] is not False
        ):
            raise ValueError("V36 immutable scope")
        design_path = ROOT / plan["micro_design_path"]
        if (
            hashlib.sha256(design_path.read_bytes()).hexdigest()
            != plan["micro_design_sha256"]
        ):
            raise ValueError("frozen micro design hash")
        design = json.loads(design_path.read_text())
    except (KeyError, ValueError, OSError) as exc:
        raise InputError("Task042 V36: " + str(exc)) from exc
    name = item["stage"]
    return RunSpecification(
        identity={
            "model_id": "task042_v36_preparation",
            "run_id": item["run_id"],
            "batch": "V36_TARGET_PORT_PREPARATION",
        },
        geometry=design["geometry"]
        if name == "COMPONENT"
        else contract["regular_geometry"],
        materials=material.provenance,
        incidence=design["incidence"] if name == "COMPONENT" else contract["incidence"],
        discretization=design["finite_element"]
        if name == "COMPONENT"
        else contract["capacity_scenario"],
        boundary=design["boundary"] if name == "COMPONENT" else contract["boundary"],
        method={"kind": "preparation_only_explicit_opt_in"},
        solver={"preconditioner": "task042_v36_" + name.lower()},
        execution={
            "mpi_size": 1,
            "timeout_seconds": 900 if name == "COMPONENT" else 300,
            "warning_memory_gib": 6 if name == "COMPONENT" else 1,
            "terminate_memory_gib": 8 if name == "COMPONENT" else 2,
            "require_zero_swap": True,
        },
        output={"results_root": "results/task042"},
        derived={
            "stage": name,
            "environment_mode": "fe" if name in ("INVENTORY", "COMPONENT") else "pure",
            "plan_sha256": hashlib.sha256(PLAN.read_bytes()).hexdigest(),
            "target_solve": False,
            "target_physical_contract_sha256": contract["physical_contract_sha256"],
            "micro_design_sha256": plan["micro_design_sha256"],
        },
        source_path=path,
        raw_input_bytes=raw,
        input_sha256=hashlib.sha256(raw).hexdigest(),
        physical_model_sha256=(
            plan["micro_physical_sha256"]
            if name == "COMPONENT"
            else contract["physical_contract_sha256"]
        ),
        expected_output_parent=ROOT / "results/task042",
    )


def read_stage(name):
    pointer = json.loads((ARTIFACT / (name + ".json")).read_text())
    path = Path(pointer["path"]).resolve()
    if (
        not path.is_relative_to(ARTIFACT)
        or hashlib.sha256(path.read_bytes()).hexdigest() != pointer["sha256"]
    ):
        raise ValueError("V36 stage source/path/content identity")
    return json.loads(path.read_text()), path
