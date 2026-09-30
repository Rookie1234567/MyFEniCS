"""Explicit V14 decoder/profile/verification inventory and reference barrier."""

import json
import tomllib
from pathlib import Path

from src.io.autonomous_neural_head import plan_and_operator
from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.io.task042_profile import ROOT
from src.solvers.neural_fe_action_packet import array_hash, file_hash

V14_ROOT = ROOT / "benchmarks/artifacts/task042/v14"
PLAN_PATH = ROOT / "input/task042_neural_coarse_inverse/orthonormal_trace_reprofile_v14.json"
STAGES = {"DECODER": ("ml", 1800), "PROFILE": ("ml", 10000), "VERIFY": ("fe", 900)}


def load_orthonormal_trace(path):
    path = Path(path).resolve()
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"[task042_v14]" not in raw:
        return None
    try:
        cfg = tomllib.loads(raw.decode()); item = cfg["task042_v14"]
        if set(cfg) != {"schema_version", "task042_v14"} or cfg["schema_version"] != 1:
            raise ValueError("V14 explicit opt-in required")
        if set(item) != {"stage", "run_id", "material_table_id", "decoder_family"}:
            raise ValueError("V14 keys differ")
        if item["stage"] not in STAGES or item["run_id"] != "task042_v14_"+item["stage"].lower():
            raise ValueError("unregistered V14 one-run stage")
        if item["decoder_family"] != "ORTHONORMAL_NEURAL_FE_BASIS":
            raise ValueError("raw MLP cannot be loaded as the new decoder family")
        plan, design, material, fe = plan_and_operator()
        own = json.loads(PLAN_PATH.read_text())
        if own["action_sha256"] != fe["packet"]["sha256"] or own["physical_sha256"] != plan["physical_model_sha256"]:
            raise ValueError("V14 frozen action/physics differs")
        if item["material_table_id"] != material.provenance["material_table_id"]:
            raise ValueError("canonical material differs")
        if item["stage"] != "VERIFY" and (V14_ROOT/"VERIFY.json").exists():
            raise ValueError("V14 reference barrier: solver queue is already closed")
        mode, timeout = STAGES[item["stage"]]
    except (OSError, ValueError, KeyError, tomllib.TOMLDecodeError) as error:
        raise InputError(f"Task042 V14 input/identity error: {error}") from error
    return RunSpecification(
        identity={"model_id": "task042_v14_fixed_0p7nm_p3_micro", "run_id": item["run_id"],
                  "batch": "V14_ORTHONORMAL_TRACE_REPROFILE"},
        geometry=design["geometry"], materials=material.provenance, incidence=design["incidence"],
        discretization=design["finite_element"], boundary=design["boundary"],
        method={"kind": "orthonormal_neural_FE_basis_explicit_opt_in"},
        solver={"preconditioner": "task042_v14_"+item["stage"].lower()},
        execution={"mpi_size": 1, "timeout_seconds": timeout, "warning_memory_gib": 12,
                   "terminate_memory_gib": 16, "require_zero_swap": True},
        output={"results_root": "results/task042"},
        derived={"stage": "V14-"+item["stage"], "environment_mode": mode,
                 "plan_sha256": file_hash(PLAN_PATH), "physical_model_complete": True,
                 "physical_operator_sha256": plan["physical_model_sha256"],
                 "decoder_family": item["decoder_family"],
                 "identity_hash_meaning": "original V7 physical action/RHS; direct Qc decoder; REF7 only after queue freeze"},
        source_path=path, raw_input_bytes=raw, input_sha256=file_hash(path),
        physical_model_sha256=plan["physical_model_sha256"], expected_output_parent=ROOT/"results/task042")


def read_frozen_state(record, allowed_root):
    import numpy as np
    path = Path(record["path"]).resolve()
    if not path.is_relative_to(allowed_root) or file_hash(path) != record["sha256"]:
        raise ValueError("frozen state path/hash differs")
    with np.load(path, allow_pickle=False) as saved:
        result = {key: np.array(saved[key]) for key in saved.files}
    for key, value in result.items():
        expected = record.get(key+"_sha256") or record.get("arrays", {}).get(key, {}).get("sha256")
        if expected and array_hash(value) != expected:
            raise ValueError("frozen "+key+" array hash differs")
    return result


def publish(name, path):
    from src.runners.task042_shared import write_json
    entry = dict(path=str(path), sha256=file_hash(path))
    with (V14_ROOT/"index_history.jsonl").open("a") as stream:
        stream.write(json.dumps(dict(name=name, **entry))+"\n")
    write_json(V14_ROOT/(name+".json"), entry)


def read_result(name):
    entry = json.loads((V14_ROOT/(name+".json")).read_text())
    path = Path(entry["path"]).resolve()
    if not path.is_relative_to(V14_ROOT) or file_hash(path) != entry["sha256"]:
        raise ValueError("V14 result path/hash differs")
    result = json.loads(path.read_text())
    if result["plan_sha256"] != file_hash(PLAN_PATH) or (result["reference_arrays_read"] and name != "VERIFY"):
        raise ValueError("V14 plan/reference barrier differs")
    return result, path
