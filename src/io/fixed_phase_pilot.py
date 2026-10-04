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
STAGES.update({
    "v21_control_checks": ("pure",600,"P01",None),
    "v21_joint_qualification": ("fe",9000,"P01",None),
    "v21_saved_p3_recovery": ("fe",3600,"P2",None),
    "v21_o3_repair": ("fe",3600,"P2","O3"),
    "v21_e3_repair": ("fe",3600,"P2","E3"),
    "v21_e4": ("fe",3600,"P2","E4"),
    "v21_o6": ("fe",9000,"P3","O6"),
    "v21_physical_compare": ("fe",5400,"P4",None),
    "v21_saved_checker": ("pure",1800,"P4",None),
})
STAGES.update({
    "v22_control_checks": ("pure",600,"P01",None),
    "v22_affine_saved": ("fe",3600,"P01",None),
    "v22_face_qualification": ("fe",9000,"P2",None),
    "v22_frozen_port_audit": ("fe",7200,"P3",None),
    "v22_e3_correction": ("fe",3600,"conditional","E3"),
    "v22_e4_correction": ("fe",3600,"conditional","E4"),
    "v22_corrected_compare": ("fe",5400,"conditional",None),
    "v22_target_local_face": ("fe",7200,"conditional",None),
    "v22_saved_checker": ("pure",1800,"D",None),
})
STAGES.update({
    "v23_admission_audit": ("pure", 1200, "P0", None),
    "v23_facet_qualification": ("fe", 3000, "P1", None),
    "v23_analytic_cold": ("fe", 1200, "P2", None),
    "v23_q60_cold": ("fe", 1200, "P2", None),
    "v23_saved_checker": ("pure", 1200, "D", None),
})


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
        not item["run_id"].startswith("task42extra_"+item["stage"].split("_",1)[0]+"_")
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
            warning_memory_gib=1.75 if mode == "pure" or item["stage"].startswith("v23_") else 12,
            terminate_memory_gib=2 if mode == "pure" or item["stage"].startswith("v23_") else 16,
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
            campaign_version=int(item["stage"][1:3]),
        ),
        source_path=path,
        raw_input_bytes=raw,
        input_sha256=hashlib.sha256(raw).hexdigest(),
        physical_model_sha256=digest,
        expected_output_parent=ROOT / "results/task42extra",
    )
