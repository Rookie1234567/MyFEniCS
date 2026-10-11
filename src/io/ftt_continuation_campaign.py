"""Strict opt-in parent-fork schema; no weakening of historical input guards."""

import hashlib
import json
from pathlib import Path
from src.io.input_loader import InputError
from src.io.neural_wave_campaign import ROOT, digest
from src.solvers.ftt_core_continuation import policy_for

DESIGN = ROOT / "input/task042extra_feinn_5nm/design_v43.json"
STAGES = {
    "v43_bloch_resume_checks": ("ml", 1800, "bloch_resume_checks", None),
    "v43_bloch_learned_continue": (
        "ml",
        10800,
        "BLOCH_FTTNN_R4_LEARNED_CONTINUE",
        "fttnn",
    ),
    "v43_bloch_same_state_freeze": (
        "ml",
        5400,
        "BLOCH_FTTNN_R4_FREEZE_ABLATION",
        "fttnn",
    ),
    "v43_bloch_independent_compare": ("pure", 3600, "bloch_continuation_compare", None),
}
PARENT_SHA = "820482a3ff75c87203f301e628b5874be2e387b0627b8765a96e1a8ae6076c2f"


def validate_design(d):
    from src.common.ftt_bloch_phase import phase_definition

    p = d["parent_checkpoint"]
    old = json.loads(
        (ROOT / "input/task042extra_feinn_5nm/design_v42.json").read_text()
    )
    for key in (
        "model",
        "native_identity",
        "files",
        "reference",
        "gram",
        "real_parameters",
        "hidden_solver",
        "network_quadrature",
        "volume_DtN_degree",
        "phase_definition",
    ):
        if d[key] != old[key]:
            raise InputError("CONTINUATION_INHERITED_PHYSICS_CHANGED:" + key)
    if (
        d["campaign"] != "V43_BLOCH_FTT_TREND_CONTINUATION"
        or d["campaign_version"] != 43
        or d["seed"] != 4213701
        or d["ranks"] != [1, 8, 8, 1]
        or d["point_batch"] != 512
        or d["cell_batch"] != 8
        or set(d["files"]) != {"native", "moments_q30", "moments_q60"}
        or d["phase_definition"] != phase_definition(d)
        or d["core_solver"]
        != dict(method="LSMR", damp=0, atol=1e-8, btol=1e-8, conlim=1e12, maxiter=300)
        or d["execution_policies"]
        != {"learned": policy_for(True), "freeze": policy_for(False)}
        or p["sha256"] != PARENT_SHA
        or p["bytes"] != 1887719
        or p["input_kind"] != "unlabelled_complete_round4_boundary"
        or p["binding"]["route"] != "BLOCH_FTTNN_CORE_LEARNED"
        or d["training"]["from_zero"]
        or not d["validation_used_for_stopping"]
        or d["production_initialization_allowed"]
    ):
        raise InputError("CONTINUATION_FROZEN_PARENT_POLICY_OR_PHYSICS_CHANGED")


def load_continuation(path, data, raw):
    if set(data) != {"schema_version", "neural_wave"} or data["schema_version"] != 13:
        raise InputError("CONTINUATION_EXPLICIT_SCHEMA_REQUIRED")
    item = data["neural_wave"]
    if set(item) != {"stage", "design_sha256"} or item["stage"] not in STAGES:
        raise InputError("CONTINUATION_UNKNOWN_STAGE_OR_LABEL")
    if item["design_sha256"] != digest(DESIGN):
        raise InputError("CONTINUATION_FROZEN_DESIGN_CHANGED")
    validate_design(json.loads(DESIGN.read_text()))
    mode, seconds, role, kind = STAGES[item["stage"]]
    return dict(
        stage=item["stage"],
        mode=mode,
        max_seconds=seconds,
        role=role,
        model_kind=kind,
        metric_kind="native_euc",
        mapping_kind="factored_exact_moments",
        input=str(Path(path).resolve().relative_to(ROOT)),
        input_sha256=hashlib.sha256(raw).hexdigest(),
        design_sha256=item["design_sha256"],
        campaign_version=43,
        case="M5",
        schema="ftt.parent-fork-one-run.v1",
    )


def routes():
    return [(stage, item[2]) for stage, item in STAGES.items() if item[3] is not None]
