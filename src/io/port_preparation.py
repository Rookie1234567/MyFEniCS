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
    if b"[task042_v42]" in raw:
        return load_distributed_volume(path)
    if b"[task042_v41]" in raw:
        return load_native_entities(path)
    if b"[task042_v40]" in raw:
        return load_native_recovery(path)
    if b"[task042_v39]" in raw:
        return load_native_integration(path)
    if b"[task042_v38]" in raw:
        return load_boundary_structure(path)
    if b"[task042_v37]" in raw:
        return load_boundary_witness(path)
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


def load_boundary_witness(path):
    from src.solvers.boundary_witness_scope import PLAN

    path = Path(path).resolve()
    raw = path.read_bytes()
    value = tomllib.loads(raw.decode())
    item = value.get("task042_v37", {})
    stages = ("IDENTITY", "PATCH", "CAPACITY", "CHECK", "DEPLOY")
    if (
        set(value) != {"schema_version", "task042_v37"}
        or value["schema_version"] != 1
        or set(item) != {"stage", "run_id"}
        or item.get("stage") not in stages
        or not re.fullmatch("task042_v37_[a-z0-9_]+", item.get("run_id", ""))
    ):
        raise InputError("V37 boundary-only explicit stage schema")
    plan = json.loads(PLAN.read_text())
    if (
        plan["review_commit"] != "02fe5f860562f6a7ef689f9d53b061cfaf30a43b"
        or plan["target_solve_authorized"] is not False
    ):
        raise InputError("V37 immutable authorization")
    pointer = json.loads(
        (ROOT / "benchmarks/artifacts/task042/v36/INVENTORY.json").read_text()
    )
    parent = Path(pointer["path"])
    if (
        hashlib.sha256(parent.read_bytes()).hexdigest() != pointer["sha256"]
        or pointer != plan["inventory_parent"]
    ):
        raise InputError("V37 frozen V36 inventory parent")
    contract = json.loads(parent.read_text())["contract"]
    stage = item["stage"]
    return RunSpecification(
        identity={
            "model_id": "task042_v37_boundary_witness",
            "run_id": item["run_id"],
            "batch": "V37_TARGET_P6_BOUNDARY_WITNESS",
        },
        geometry=contract["regular_geometry"],
        materials=contract["materials"],
        incidence=contract["incidence"],
        discretization={
            "degree": 6,
            "quadrature_degrees": [15, 30, 60],
            "max_native_hex": 32,
            "max_classes": 4,
            "max_modes": 24,
        },
        boundary=contract["boundary"],
        method={"kind": "boundary_witness_only_opt_in"},
        solver={"preconditioner": "none", "target_solve": False},
        execution={
            "mpi_size": 1,
            "timeout_seconds": 2400 if stage in ("PATCH", "CAPACITY") else 600,
            "warning_memory_gib": 6 if stage in ("PATCH", "CAPACITY") else 1,
            "terminate_memory_gib": 8 if stage in ("PATCH", "CAPACITY") else 2,
            "require_zero_swap": True,
        },
        output={"results_root": "results/task042"},
        derived={
            "stage": stage,
            "preparation_scope": "v37",
            "environment_mode": "fe" if stage in ("PATCH", "CAPACITY") else "pure",
            "plan_sha256": hashlib.sha256(PLAN.read_bytes()).hexdigest(),
            "target_solve": False,
        },
        source_path=path,
        raw_input_bytes=raw,
        input_sha256=hashlib.sha256(raw).hexdigest(),
        physical_model_sha256=contract["physical_contract_sha256"],
        expected_output_parent=ROOT / "results/task042",
    )


def load_boundary_structure(path):
    from dataclasses import replace

    from src.solvers.boundary_structure_scope import PLAN, plan_record

    path = Path(path).resolve()
    raw = path.read_bytes()
    value = tomllib.loads(raw.decode())
    item = value.get("task042_v38", {})
    stages = ("BRIDGE", "LAYOUT", "COMPONENT", "ORACLE", "CHECK", "DEPLOY")
    if (
        set(value) != {"schema_version", "task042_v38"}
        or value["schema_version"] != 1
        or set(item) != {"stage", "run_id"}
        or item.get("stage") not in stages
        or not re.fullmatch("task042_v38_[a-z0-9_]+", item.get("run_id", ""))
    ):
        raise InputError("V38 boundary structure explicit stage schema")
    plan_record()
    # Reuse the qualified physical specification; new namespace and budgets
    # are explicit and never inherit V37 ledger/deadline.
    old = load_boundary_witness(
        ROOT / "input/task042_neural_coarse_inverse/v37_identity.dat"
    )
    stage = item["stage"]
    fe = stage in ("BRIDGE", "LAYOUT", "COMPONENT", "ORACLE")
    return replace(
        old,
        identity={
            "model_id": "task042_v38_boundary_structure",
            "run_id": item["run_id"],
            "batch": "V38_TARGET_BOUNDARY_STRUCTURE",
        },
        method={"kind": "same_quadrature_directional_boundary_opt_in"},
        execution={
            "mpi_size": 1,
            "timeout_seconds": 1200 if stage == "ORACLE" else 5400 if fe else 600,
            "warning_memory_gib": 6 if fe else 1,
            "terminate_memory_gib": 8 if fe else 2,
            "require_zero_swap": True,
        },
        derived={
            "stage": stage,
            "preparation_scope": "v38",
            "environment_mode": "fe" if fe else "pure",
            "plan_sha256": hashlib.sha256(PLAN.read_bytes()).hexdigest(),
            "target_solve": False,
        },
        source_path=path,
        raw_input_bytes=raw,
        input_sha256=hashlib.sha256(raw).hexdigest(),
    )


def load_native_integration(path):
    from dataclasses import replace

    from src.solvers.native_integration_scope import PLAN, plan_record

    path = Path(path).resolve()
    raw = path.read_bytes()
    value = tomllib.loads(raw.decode())
    item = value.get("task042_v39", {})
    if (
        set(value) != {"schema_version", "task042_v39"}
        or value["schema_version"] != 1
        or set(item) != {"stage", "run_id"}
        or item.get("stage")
        not in ("EVIDENCE", "ADAPTER", "COUPLED", "CHECK", "DEPLOY")
        or not re.fullmatch("task042_v39_[a-z0-9_]+", item.get("run_id", ""))
    ):
        raise InputError("V39 finite native integration explicit stage schema")
    plan_record()
    old = load_boundary_structure(
        ROOT / "input/task042_neural_coarse_inverse/v38_bridge.dat"
    )
    stage = item["stage"]
    fe = stage in ("ADAPTER", "COUPLED")
    return replace(
        old,
        identity={
            "model_id": "task042_v39_native_integration",
            "run_id": item["run_id"],
            "batch": "V39_NATIVE_BOUNDARY_VOLUME_INTEGRATION",
        },
        method={"kind": "native_boundary_volume_callback_opt_in"},
        execution={
            "mpi_size": 1,
            "timeout_seconds": 1200 if fe else 600,
            "warning_memory_gib": 6 if fe else 1,
            "terminate_memory_gib": 8 if fe else 2,
            "require_zero_swap": True,
        },
        derived={
            "stage": stage,
            "preparation_scope": "v39",
            "environment_mode": "fe" if fe else "pure",
            "plan_sha256": hashlib.sha256(PLAN.read_bytes()).hexdigest(),
            "target_solve": False,
        },
        source_path=path,
        raw_input_bytes=raw,
        input_sha256=hashlib.sha256(raw).hexdigest(),
    )


def load_native_recovery(path):
    from dataclasses import replace

    from src.solvers.native_recovery_scope import COMPONENT_ROLES, PLAN, plan_record

    path = Path(path).resolve()
    raw = path.read_bytes()
    value = tomllib.loads(raw.decode())
    item = value.get("task042_v40", {})
    if (
        set(value) != {"schema_version", "task042_v40"}
        or value["schema_version"] != 1
        or set(item) != {"stage", "run_id"}
        or item.get("stage") not in COMPONENT_ROLES
        or not re.fullmatch("task042_v40_[a-z0-9_]+", item.get("run_id", ""))
    ):
        raise InputError("V40 native recovery explicit stage schema")
    plan_record()
    old = load_boundary_structure(
        ROOT / "input/task042_neural_coarse_inverse/v38_bridge.dat"
    )
    stage = item["stage"]
    return replace(
        old,
        identity={
            "model_id": "task042_v40_native_recovery",
            "run_id": item["run_id"],
            "batch": "V40_PERSISTENT_NATIVE_RECOVERY",
        },
        method={"kind": "persistent_native_volume_recovery_opt_in"},
        execution={
            "mpi_size": 1,
            "timeout_seconds": 2400 if stage in ("BUILD", "RECOVER") else 600,
            "warning_memory_gib": 6,
            "terminate_memory_gib": 8,
            "require_zero_swap": True,
        },
        derived={
            "stage": stage,
            "preparation_scope": "v40",
            "environment_mode": "fe",
            "plan_sha256": hashlib.sha256(PLAN.read_bytes()).hexdigest(),
            "target_solve": False,
        },
        source_path=path,
        raw_input_bytes=raw,
        input_sha256=hashlib.sha256(raw).hexdigest(),
    )


def load_distributed_volume(path):
    from dataclasses import replace

    from src.solvers.distributed_volume_scope import NATIVE, PLAN, STAGES, plan_record

    path = Path(path).resolve()
    raw = path.read_bytes()
    value = tomllib.loads(raw.decode())
    item = value.get("task042_v42", {})
    if (
        set(value) != {"schema_version", "task042_v42"}
        or value["schema_version"] != 1
        or set(item) != {"stage", "run_id"}
        or item.get("stage") not in STAGES
        or not re.fullmatch("task042_v42_[a-z0-9_]+", item.get("run_id", ""))
    ):
        raise InputError("V42 volume explicit stage schema")
    plan_record()
    old = load_boundary_structure(
        ROOT / "input/task042_neural_coarse_inverse/v38_bridge.dat"
    )
    stage = item["stage"]
    ranks = {
        "VOLUME2": 2,
        "VOLUME4": 4,
        "RECOVERY2": 2,
        "RECOVERY4": 4,
        "TARGET_FORWARD": 2,
        "TARGET_ADJOINT": 2,
    }.get(stage, 1)
    return replace(
        old,
        identity={
            "model_id": "task042_v42_distributed_volume",
            "run_id": item["run_id"],
            "batch": "V42_DISTRIBUTED_VOLUME_AND_RECOVERY",
        },
        method={"kind": "distributed_volume_explicit_opt_in"},
        execution={
            "mpi_size": ranks,
            "timeout_seconds": 2400 if stage in ("CLASSES", "ORACLE") else 600,
            "warning_memory_gib": 6 if stage in NATIVE else 1,
            "terminate_memory_gib": 8 if stage in NATIVE else 2,
            "require_zero_swap": True,
        },
        derived={
            "stage": stage,
            "preparation_scope": "v42",
            "environment_mode": "fe",
            "plan_sha256": hashlib.sha256(PLAN.read_bytes()).hexdigest(),
            "target_solve": False,
        },
        source_path=path,
        raw_input_bytes=raw,
        input_sha256=hashlib.sha256(raw).hexdigest(),
    )


def load_native_entities(path):
    from dataclasses import replace

    from src.solvers.native_entity_scope import NATIVE, PLAN, STAGES, plan_record

    path = Path(path).resolve()
    raw = path.read_bytes()
    value = tomllib.loads(raw.decode())
    item = value.get("task042_v41", {})
    if (
        set(value) != {"schema_version", "task042_v41"}
        or value["schema_version"] != 1
        or set(item) != {"stage", "run_id"}
        or item.get("stage") not in STAGES
        or not re.fullmatch("task042_v41_[a-z0-9_]+", item.get("run_id", ""))
    ):
        raise InputError("V41 entity-only explicit stage schema")
    plan_record()
    old = load_boundary_structure(
        ROOT / "input/task042_neural_coarse_inverse/v38_bridge.dat"
    )
    stage = item["stage"]
    ranks = {"BRIDGE2": 2, "BRIDGE4": 4, "TOPOLOGY": 2, "ROUTING": 2, "DEPLOY": 2}.get(
        stage, 1
    )
    return replace(
        old,
        identity={
            "model_id": "task042_v41_native_entities",
            "run_id": item["run_id"],
            "batch": "V41_NATIVE_ENTITY_TOPOLOGY_AND_OWNER",
        },
        method={"kind": "native_entity_topology_only_explicit_opt_in"},
        discretization={
            "degree": 6,
            "q_volume": 15,
            "q_boundary": 30,
            "q_audit": 17,
            "fixture_hex": 64,
            "target_p6_function_space": "NOT_AUTHORIZED",
        },
        execution={
            "mpi_size": ranks,
            "timeout_seconds": 2400 if stage == "TOPOLOGY" else 600,
            "warning_memory_gib": 6 if stage in NATIVE else 1,
            "terminate_memory_gib": 8 if stage in NATIVE else 2,
            "require_zero_swap": True,
        },
        derived={
            "stage": stage,
            "preparation_scope": "v41",
            "environment_mode": "fe",
            "plan_sha256": hashlib.sha256(PLAN.read_bytes()).hexdigest(),
            "target_solve": False,
        },
        source_path=path,
        raw_input_bytes=raw,
        input_sha256=hashlib.sha256(raw).hexdigest(),
    )
