"""Strict one-run V49 descriptor reader; ordinary defaults are unchanged."""
import hashlib
import re
import tomllib
from pathlib import Path

from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.solvers.scattering_anchor_scope import ROOT, STAGES, plan_record, PLAN


def load_scattering_anchor(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    value = tomllib.loads(raw.decode())
    item = value.get("task042_v49", {})
    if set(value) != {"schema_version", "task042_v49"} or value["schema_version"] != 1 or set(item) != {"stage", "run_id"} or item.get("stage") not in STAGES or not re.fullmatch("task042_v49_[a-z0-9_]+", item.get("run_id", "")):
        raise InputError("V49 explicit one-run schema/stage")
    p = plan_record()
    physical = p["physical_descriptor"]
    return RunSpecification(
        identity={"model_id":"task042_v49_complete_scattering", "run_id":item["run_id"], "batch":p["batch"]},
        geometry=physical["geometry"], materials=physical["materials"], incidence=physical["incidence"],
        discretization=physical["discretization"], boundary=physical["boundary"],
        method={"kind":"bounded_complete_scattering_anchor_opt_in"},
        solver={"degree":5 if item["stage"] == "REFERENCE_NOTCH_P5" else 4},
        execution={"mpi_size":1, "timeout_seconds":3600, "warning_memory_gib":12,
                   "terminate_memory_gib":16, "require_zero_swap":True},
        output={"results_root":"results/task042"},
        derived={"stage":item["stage"], "preparation_scope":"v49", "environment_mode":"fe",
                 "storage_limits":{k:p[k] for k in ("new_storage_bytes", "task_storage_bytes", "free_bytes", "evidence_reserve_bytes")},
                 "plan_sha256":hashlib.sha256(PLAN.read_bytes()).hexdigest()},
        source_path=path, raw_input_bytes=raw, input_sha256=hashlib.sha256(raw).hexdigest(),
        physical_model_sha256=hashlib.sha256(__import__('json').dumps(physical,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        expected_output_parent=ROOT / "results/task042")
