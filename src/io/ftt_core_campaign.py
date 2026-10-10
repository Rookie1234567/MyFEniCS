"""Explicit V41 conditional-core inputs; no ordinary solver default changes."""

import hashlib
import json
from pathlib import Path
from src.io.input_loader import InputError
from src.io.neural_wave_campaign import ROOT, digest

DESIGN = ROOT / "input/task042extra_feinn_5nm/design_v41.json"
STAGES = {
    "v41_core_linear_checks": ("ml", 5400, "ftt_core_checks", None),
    "v41_fttnn_core_learned": ("ml", 7200, "FTTNN_CONDITIONAL_CORE_LEARNED", "fttnn"),
    "v41_fttnn_core_frozen": ("ml", 7200, "FTTNN_CONDITIONAL_CORE_FROZEN", "fttnn"),
    "v41_chebtt_core_control": (
        "ml",
        7200,
        "CHEBTT_CONDITIONAL_CORE_CONTROL",
        "chebtt",
    ),
    "v41_core_independent_compare": ("pure", 3600, "ftt_core_compare", None),
}


def load_core(path, data, raw):
    if set(data) != {"schema_version", "neural_wave"} or data["schema_version"] != 11:
        raise InputError("FTT_CORE_EXPLICIT_SCHEMA_REQUIRED")
    item = data["neural_wave"]
    if set(item) != {"stage", "design_sha256"} or item["stage"] not in STAGES:
        raise InputError("FTT_CORE_UNKNOWN_STAGE_OR_LABEL")
    if item["design_sha256"] != digest(DESIGN):
        raise InputError("FTT_CORE_FROZEN_DESIGN_CHANGED")
    d = json.loads(DESIGN.read_text())
    if (
        d["campaign"] != "V41_FTT_CONDITIONAL_CORE_SOLVE"
        or d["seed"] != 4213701
        or d["ranks"] != [1, 8, 8, 1]
        or d["point_batch"] != 512
        or set(d["files"]) != {"native", "moments_q30", "moments_q60"}
        or d["core_solver"]
        != dict(method="LSMR", damp=0, atol=1e-8, btol=1e-8, conlim=1e12, maxiter=300)
        or d["limits"]
        != dict(
            rounds=6,
            visits=18,
            LSMR_iterations=5400,
            route_seconds=7200,
            total_seconds=43200,
            final_reserve_seconds=1800,
        )
    ):
        raise InputError("FTT_CORE_FIXED_CONTRACT_OR_TRAINING_WHITELIST_CHANGED")
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
        campaign_version=41,
        case="M5",
        schema="ftt.core-one-run.v1",
    )


def routes():
    return [
        (stage, STAGES[stage][2]) for stage in STAGES if STAGES[stage][3] is not None
    ]
