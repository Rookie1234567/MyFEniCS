"""Strict Review V19 opt-in input, isolated from the old M5/NN ledger."""

import hashlib
import json
from pathlib import Path

from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.geometry.fixed_phase_plan import physical_design

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "input/task042extra_feinn_5nm/design_v20.json"
STAGES = {
    "v20_control_checks": ("pure", 600, "implementation", None),
    "v20_phase_qualification": ("fe", 3600, "A", None),
    "v20_o3": ("fe", 7200, "B", "O3"),
    "v20_e3": ("fe", 7200, "B", "E3"),
    "v20_e4": ("fe", 7200, "B", "E4"),
    "v20_o6": ("fe", 7200, "B", "O6"),
    "v20_physical_compare": ("fe", 5400, "C", None),
    "v20_saved_checker": ("pure", 1800, "C", None),
}


def load(path, raw, config):
    item = config["task42extra"]
    required = {
        "stage",
        "run_id",
        "design_sha256",
        "research_fixed_phase",
        "neural_training_allowed",
    }
    if (
        set(item) != required
        or item["stage"] not in STAGES
        or item["research_fixed_phase"] is not True
        or item["neural_training_allowed"] is not False
    ):
        raise InputError("REVIEW_V19_EXPLICIT_FE_ONLY_STAGE_REQUIRED")
    if (
        not item["run_id"].startswith("task42extra_v20_")
        or Path(item["run_id"]).name != item["run_id"]
    ):
        raise InputError("V20_RUN_ID_REQUIRED")
    digest = hashlib.sha256(DESIGN.read_bytes()).hexdigest()
    if item["design_sha256"] != digest:
        raise InputError("V20_DESIGN_CHANGED")
    design = json.loads(DESIGN.read_text())
    for mesh in ("G0", "GX560"):
        if design["models"][mesh] != physical_design(mesh):
            raise InputError("FROZEN_PHYSICAL_DESIGN_CHANGED")
    mode, seconds, group, role = STAGES[item["stage"]]
    m = design["models"]["GX560" if role == "O6" else "G0"]
    discretization = dict(m["finite_element"])
    if role == "E4":
        # The frozen G0 geometry is shared, but the unrun E4 role is p4.
        discretization["degree"] = 4
    return RunSpecification(
        identity=dict(model_id="fixed_transverse_phase_0p7nm", run_id=item["run_id"]),
        geometry=m["geometry"],
        materials=m["materials"],
        incidence=m["incidence"],
        discretization=discretization,
        boundary=m["boundary"],
        method=dict(kind="research_fixed_phase_FE", stage=item["stage"]),
        solver=dict(preconditioner="none", role=role),
        execution=dict(
            mpi_size=1,
            math_threads=1,
            timeout_seconds=seconds,
            warning_memory_gib=1.75 if mode == "pure" else 12,
            terminate_memory_gib=2 if mode == "pure" else 16,
            require_zero_swap=True,
        ),
        output=dict(results_root="results/task42extra"),
        derived=dict(
            stage=item["stage"],
            environment_mode=mode,
            group=group,
            role=role,
            design_path=str(DESIGN),
            design_sha256=digest,
            neural_training_allowed=False,
        ),
        source_path=path,
        raw_input_bytes=raw,
        input_sha256=hashlib.sha256(raw).hexdigest(),
        physical_model_sha256=digest,
        expected_output_parent=ROOT / "results/task42extra",
    )
