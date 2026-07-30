"""Design-bound Task002 M4 identities and formal-record adapter."""

from __future__ import annotations

import json
import copy
from pathlib import Path
from typing import Any, Mapping

from .provenance import canonical_hash, file_hash
from .task002_m3r_design import point_tuple
from .task002_schema import (
    TASK002_OBSERVABLE_SCHEMA_VERSION, TASK002_PARAMETER_SCHEMA_VERSION,
    Task002ForwardParameters,
)


PRODUCTION_MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10"
PRODUCTION_ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10"
DESIGN_SCHEMA = "task002.m3r-design.v1"


def load_frozen_design(path: Path, *, baseline_sha: str, split: str) -> dict[str, Any]:
    design = json.loads(path.read_text(encoding="utf-8"))
    if design.get("schema_version") != DESIGN_SCHEMA:
        raise ValueError("Task002 M4 design schema mismatch")
    if design.get("source_sha") != baseline_sha or design.get("source_dirty") is not False:
        raise ValueError("Task002 M4 design is not bound to the clean baseline SHA")
    if design.get("production_model_id") != PRODUCTION_MODEL_ID:
        raise ValueError("Task002 M4 design is not p5-only")
    if design.get("production_solver_route_id") != PRODUCTION_ROUTE_ID:
        raise ValueError("Task002 M4 design route mismatch")
    if design.get("observable_schema_version") != TASK002_OBSERVABLE_SCHEMA_VERSION:
        raise ValueError("Task002 M4 observable schema mismatch")
    if design.get("parameter_schema_version") != TASK002_PARAMETER_SCHEMA_VERSION:
        raise ValueError("Task002 M4 parameter schema mismatch")
    tuples = [list(point_tuple(point)) for point in design.get("points", [])]
    if len(tuples) != int(design.get("point_count", -1)):
        raise ValueError("Task002 M4 design point count mismatch")
    if canonical_hash(tuples) != design.get("point_tuple_sha256"):
        raise ValueError("Task002 M4 design tuple hash mismatch")
    if split not in {"train", "frozen_validation"}:
        raise ValueError("Task002 M4 split must be train or frozen_validation")
    expected_fragment = "training" if split == "train" else "frozen_validation"
    if expected_fragment not in str(design.get("design_id")):
        raise ValueError("Task002 M4 split/design identity mismatch")
    return design


def parameters_from_design_point(point: Mapping[str, Any]) -> Task002ForwardParameters:
    parameters = Task002ForwardParameters(
        height_nm=float(point["height_nm"]), width_x_nm=float(point["width_x_nm"]),
        grazing_deg=float(point["grazing_deg"]), azimuth_deg=float(point["azimuth_deg"]),
        model_id=str(point["model_id"]),
    )
    parameters.validate()
    if str(point.get("solver_route_id")) != PRODUCTION_ROUTE_ID:
        raise ValueError("design point route is not Task002 p5 production")
    return parameters


def design_point_hash(*, design_id: str, design_index: int,
                      point: Mapping[str, Any]) -> str:
    return canonical_hash({
        "design_id": design_id, "design_index": int(design_index),
        "point_tuple": list(point_tuple(dict(point))),
    })


def formal_record_to_production_sample(
    *, manifest_row: Mapping[str, Any], formal_record_path: Path,
    execution_path: Path,
) -> dict[str, Any]:
    """Convert one measured formal record without inferring design metadata."""

    if manifest_row.get("status") != "measured_pass":
        raise ValueError("only measured_pass manifest rows can become samples")
    record = json.loads(formal_record_path.read_text(encoding="utf-8"))
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    gates = dict(record.get("gates", {}))
    watchdog = execution.get("watchdog", {})
    if not gates or not all(gates.values()):
        raise ValueError("formal numerical/production gates did not all pass")
    if watchdog.get("status") != "completed" or watchdog.get("return_code") != 0:
        raise ValueError("formal execution did not complete")
    if watchdog.get("peak_swap_bytes") != 0 or not watchdog.get("cleanup_complete"):
        raise ValueError("formal execution resource gates did not pass")
    if record.get("output_profile") != "compact_surrogate_record":
        raise ValueError("production sample requires compact output profile")
    if record.get("solver_route_id") != PRODUCTION_ROUTE_ID:
        raise ValueError("formal record is not p5 production")
    if record.get("source_sha") != manifest_row.get("source_sha"):
        raise ValueError("formal/manifest source SHA mismatch")
    geometry = record["parameters"]["geometry"]
    configuration = record["parameters"]["configuration"]
    inputs = [
        float(geometry["height_nm"]), float(geometry["width_x_nm"]),
        float(configuration["grazing_deg"]), float(configuration["azimuth_deg"]),
    ]
    if inputs != [float(value) for value in manifest_row["point_tuple"]]:
        raise ValueError("formal record tuple does not match frozen design row")
    sample_identity = {
        "design_id": manifest_row["design_id"],
        "design_index": int(manifest_row["design_index"]),
        "point_hash": manifest_row["point_hash"],
        "source_sha": record["source_sha"],
    }
    return {
        "schema_version": "task002.production-sample.v2",
        "sample_id": canonical_hash(sample_identity), **sample_identity,
        "split": manifest_row["split"], "inputs": inputs,
        "status": "measured_pass", "source_dirty": False,
        "solver_route_id": record["solver_route_id"],
        "aggregates": {
            name: record["observables"][name]
            for name in ("R_total", "T_total", "A_balance", "A_volume")
        },
        "mother_response": record["observables"]["mother_response"],
        "parameter_hash": record["parameter_hash"],
        "config_hash": record["config_identity"]["config_sha256"],
        "topology_hash": record["planned_topology_identity"]["topology_element_hash"],
        "actual_runtime_topology_hash": canonical_hash(
            record["actual_runtime_topology_identity"]
        ),
        "artifact_hashes": record["artifact_hashes"],
        "formal_record_sha256": file_hash(formal_record_path),
        "execution_sha256": file_hash(execution_path),
        "numerical_gates": gates,
        "resource_gates": {
            "completed": watchdog["status"] == "completed",
            "return_code_zero": watchdog["return_code"] == 0,
            "zero_swap": watchdog["peak_swap_bytes"] == 0,
            "cleanup_complete": bool(watchdog["cleanup_complete"]),
        },
    }


def audit_rebind(old: Mapping[str, Any], new: Mapping[str, Any]) -> dict[str, Any]:
    names = (
        "training_design.json", "frozen_validation_design.json",
        "candidate_pool.json", "discretization_audit_design.json",
    )
    unchanged = {
        name: old[name]["point_tuple_sha256"] == new[name]["point_tuple_sha256"]
        and [point_tuple(p) for p in old[name]["points"]]
        == [point_tuple(p) for p in new[name]["points"]]
        for name in names
    }
    return {"tuple_tables_unchanged": unchanged, "pass": all(unchanged.values())}


def rebind_frozen_designs(*, source_dir: Path, output_dir: Path,
                          baseline_sha: str) -> dict[str, Any]:
    """Copy the frozen tuple tables while changing source metadata only."""

    if len(baseline_sha) != 40:
        raise ValueError("design rebind requires a full clean implementation SHA")
    names = (
        "training_design.json", "frozen_validation_design.json",
        "candidate_pool.json", "discretization_audit_design.json",
    )
    old = {name: json.loads((source_dir / name).read_text(encoding="utf-8"))
           for name in names}
    new: dict[str, Any] = {}
    for name in names:
        value = copy.deepcopy(old[name])
        value["source_sha"] = baseline_sha
        value["source_dirty"] = False
        new[name] = value
    old_split = json.loads((source_dir / "split_hashes.json").read_text(encoding="utf-8"))
    split = copy.deepcopy(old_split)
    split["source_sha"] = baseline_sha
    split["combined_design_sha256"] = canonical_hash({
        "training": split["training_sha256"],
        "validation": split["frozen_validation_sha256"],
        "candidates": split["candidate_pool_sha256"],
        "audit": split["discretization_audit_sha256"],
        "source_sha": baseline_sha,
    })
    new["split_hashes.json"] = split
    audit = audit_rebind(old, new)
    if not audit["pass"]:
        raise RuntimeError("M4 rebind changed a frozen point tuple table")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in new.items():
        (output_dir / name).write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
        )
    return {
        "schema_version": "task002.m4-design-rebind.v1",
        "old_source_sha": old["training_design.json"]["source_sha"],
        "new_source_sha": baseline_sha,
        "old_point_tuple_hashes": {
            name: old[name]["point_tuple_sha256"] for name in names
        },
        "new_point_tuple_hashes": {
            name: new[name]["point_tuple_sha256"] for name in names
        },
        "combined_design_sha256": split["combined_design_sha256"],
        **audit,
    }
