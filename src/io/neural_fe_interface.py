"""Narrow material-blocked interface inputs, not ordinary physical inputs.

The ordinary schema correctly requires optical constants for a Si PDE. This
separate explicit opt-in accepts no replacement index and dispatches only the
two material-independent interface checks. No optimizer/PDE stage is exposed.
"""

import hashlib
import json
from pathlib import Path

import tomllib

from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.io.task042_profile import ROOT

DESIGN_PATH = ROOT / "input/task042_neural_coarse_inverse/neural_fe_design_v6.json"
PROFILES = {
    "geometry_trace_interface": (
        "task042_v6_geometry_trace_interface",
        "V6-FE-INTERFACE",
    ),
    "neural_packet_vjp": ("task042_v6_neural_packet_vjp", "V6-ML-INTERFACE"),
}


def load_interface(path):
    path = Path(path).resolve()
    try:
        raw = path.read_bytes()
    except OSError:
        return None  # Ordinary input loader retains its original error reporting.
    if b"[task042_v6_interface]" not in raw:
        return None
    try:
        config = tomllib.loads(raw.decode())
    except (tomllib.TOMLDecodeError, UnicodeError) as exc:
        raise InputError(f"Invalid V6 interface input: {exc}") from exc
    if "task042_v6_interface" not in config:
        return None
    if (
        set(config) != {"schema_version", "task042_v6_interface"}
        or config["schema_version"] != 1
    ):
        raise InputError("V6 interface input permits only its explicit stage identity")
    item = config["task042_v6_interface"]
    if (
        set(item) != {"stage", "run_id", "material_status"}
        or item["stage"] not in PROFILES
    ):
        raise InputError("V6 interface stage inventory mismatch")
    if item["material_status"] != "MATERIAL_0P7NM_BLOCKED":
        raise InputError("This opt-in is not a material-qualified PDE route")
    if (
        not str(item["run_id"]).startswith("task042_v6_")
        or Path(item["run_id"]).name != item["run_id"]
    ):
        raise InputError("V6 run_id must be a local Task042 filename")
    design = json.loads(DESIGN_PATH.read_text())
    if (
        design["materials"]["si_n"] is not None
        or design["materials"]["status"] != item["material_status"]
    ):
        raise InputError("Material identity changed; obtain a reviewed physical route")
    identity_hash = hashlib.sha256(DESIGN_PATH.read_bytes()).hexdigest()
    profile, stage = PROFILES[item["stage"]]
    return RunSpecification(
        identity=dict(
            model_id="task042_v6_material_blocked_micro",
            run_id=item["run_id"],
            batch=design["batch"],
        ),
        geometry=design["geometry"],
        materials=design["materials"],
        incidence=design["incidence"],
        discretization=design["finite_element"],
        boundary=design["boundary"],
        method=dict(kind="material_independent_interface_only"),
        solver=dict(preconditioner=profile),
        execution=dict(
            mpi_size=1,
            timeout_seconds=600,
            warning_memory_gib=12,
            terminate_memory_gib=16,
            require_zero_swap=True,
        ),
        output=dict(results_root="results/task042"),
        derived=dict(
            stage=stage,
            design_path=str(DESIGN_PATH),
            design_sha256=identity_hash,
            physical_model_complete=False,
            physical_operator_sha256=None,
            identity_hash_meaning="unresolved design, not a material-qualified physical operator",
        ),
        source_path=path,
        raw_input_bytes=raw,
        input_sha256=hashlib.sha256(raw).hexdigest(),
        physical_model_sha256=identity_hash,
        expected_output_parent=ROOT / "results/task042",
    )
