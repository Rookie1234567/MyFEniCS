"""Explicit Bloch FTT campaign; ordinary and historical input schemas stay strict."""

import hashlib
import json
from pathlib import Path
from src.io.input_loader import InputError
from src.io.neural_wave_campaign import ROOT, digest

DESIGN = ROOT / "input/task042extra_feinn_5nm/design_v42.json"
STAGES = {
    "v42_bloch_ftt_checks": ("ml", 5400, "bloch_ftt_checks", None),
    "v42_bloch_fttnn_learned": ("ml", 5400, "BLOCH_FTTNN_CORE_LEARNED", "fttnn"),
    "v42_bloch_fttnn_frozen": ("ml", 5400, "BLOCH_FTTNN_CORE_FROZEN", "fttnn"),
    "v42_bloch_chebtt_control": ("ml", 5400, "BLOCH_CHEBTT_CORE_CONTROL", "chebtt"),
    "v42_bloch_independent_compare": ("pure", 3600, "bloch_ftt_compare", None),
}


def load_bloch(path, data, raw):
    if set(data) != {"schema_version", "neural_wave"} or data["schema_version"] != 12:
        raise InputError("BLOCH_EXPLICIT_SCHEMA_REQUIRED")
    item = data["neural_wave"]
    if set(item) != {"stage", "design_sha256"} or item["stage"] not in STAGES:
        raise InputError("BLOCH_UNKNOWN_STAGE_OR_LABEL")
    if item["design_sha256"] != digest(DESIGN):
        raise InputError("BLOCH_FROZEN_DESIGN_CHANGED")
    d = json.loads(DESIGN.read_text())
    from src.common.ftt_bloch_phase import phase_definition

    if (
        d["campaign"] != "V42_BLOCH_ENVELOPE_FTT"
        or d["seed"] != 4213701 or d["ranks"] != [1, 8, 8, 1]
        or d["point_batch"] != 512 or d["cell_batch"] != 8
        or set(d["files"]) != {"native", "moments_q30", "moments_q60"}
        or d["phase_definition"] != phase_definition(d)
        or d["core_solver"] != dict(method="LSMR", damp=0, atol=1e-8, btol=1e-8, conlim=1e12, maxiter=300)
        or d["limits"] != dict(rounds=6, visits=18, LSMR_iterations=5400, route_seconds=5400,
                               total_seconds=28800, final_reserve_seconds=1800)
        or not d["validation_used_for_stopping"]
        or d["production_initialization_allowed"]
    ):
        raise InputError("BLOCH_FIXED_CONTRACT_OR_TRAINING_WHITELIST_CHANGED")
    mode, seconds, role, kind = STAGES[item["stage"]]
    return dict(stage=item["stage"], mode=mode, max_seconds=seconds, role=role,
                model_kind=kind, metric_kind="native_euc", mapping_kind="factored_exact_moments",
                input=str(Path(path).resolve().relative_to(ROOT)),
                input_sha256=hashlib.sha256(raw).hexdigest(), design_sha256=item["design_sha256"],
                campaign_version=42, case="M5", schema="ftt.bloch-one-run.v1")


def routes():
    return [(stage, item[2]) for stage, item in STAGES.items() if item[3] is not None]
