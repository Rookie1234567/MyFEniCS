"""Explicit diagnostic-only FTT capacity inputs; no training/solve route."""

import hashlib
import json
from pathlib import Path
from src.io.input_loader import InputError
from src.io.neural_wave_campaign import ROOT, digest

DESIGN = ROOT / "input/task042extra_feinn_5nm/design_v40.json"
STAGES = {
    "v40_capacity_checks": ("fe", 1800, "ftt_capacity_checks"),
    "v40_interior_moment_tensor": ("fe", 1800, "ftt_interior_tensor"),
    "v40_rank_and_feature_bounds": ("ml", 1800, "ftt_capacity_bounds"),
    "v40_capacity_decision": ("pure", 1800, "ftt_capacity_decision"),
}


def load_capacity(path, data, raw):
    if set(data) != {"schema_version", "neural_wave"} or data["schema_version"] != 10:
        raise InputError("FTT_CAPACITY_EXPLICIT_SCHEMA_REQUIRED")
    item = data["neural_wave"]
    if set(item) != {"stage", "design_sha256"} or item["stage"] not in STAGES:
        raise InputError("FTT_CAPACITY_DIAGNOSTIC_STAGES_ONLY")
    if item["design_sha256"] != digest(DESIGN):
        raise InputError("FTT_CAPACITY_FROZEN_DESIGN_CHANGED")
    design = json.loads(DESIGN.read_text())
    if (design["campaign"] != "V40_FTT_CAPACITY_DECISION"
        or design["ranks"] != [1,8,8,1] or design["model"]["geometry"]["cells"] != [8,6,8]
        or design["reference"]["sha256"] != "0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7"
        or design["new_PDE_or_training_authorized"]):
        raise InputError("FTT_CAPACITY_FIXED_REFERENCE_OR_SCOPE_CHANGED")
    mode, seconds, role = STAGES[item["stage"]]
    return dict(stage=item["stage"], mode=mode, max_seconds=seconds, role=role,
                input=str(Path(path).resolve().relative_to(ROOT)),
                input_sha256=hashlib.sha256(raw).hexdigest(), design_sha256=item["design_sha256"],
                campaign_version=40, case="M5", schema="ftt.capacity-one-run.v1",
                result_kind="DIAGNOSTIC", pde_only_solve=False)


def checked_file(entry):
    path = (ROOT / entry["path"]).resolve()
    if not path.is_relative_to(ROOT / "benchmarks/artifacts/task42extra") or digest(path) != entry["sha256"]:
        raise ValueError("FTT_CAPACITY_DECLARED_INPUT_IDENTITY_FAILED:"+entry["path"])
    return path
