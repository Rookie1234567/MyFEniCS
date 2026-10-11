"""Explicit width/refinement schema; historical schemas retain their guards."""

import hashlib
import json
from pathlib import Path
from src.io.input_loader import InputError
from src.io.neural_wave_campaign import ROOT, digest
from src.solvers.ftt_width_extension import width_policy

DESIGN = ROOT / "input/task042extra_feinn_5nm/design_v44.json"
STAGES = {
    "v44_width_and_inner_checks": ("ml", 3600, "width_inner_checks", None, 16),
    "v44_w16_refined_learned": ("ml", 10800, "W16_REFINED_CORE_LEARNED", "fttnn", 16),
    "v44_w32_refined_learned": ("ml", 10800, "W32_REFINED_CORE_LEARNED", "fttnn", 32),
    "v44_w32_refined_frozen": ("ml", 10800, "W32_REFINED_CORE_FROZEN", "fttnn", 32),
    "v44_width_independent_compare": (
        "pure",
        3600,
        "width_independent_compare",
        None,
        16,
    ),
}


def validate_design(d):
    old = json.loads(
        (ROOT / "input/task042extra_feinn_5nm/design_v43.json").read_text()
    )
    for key in (
        "model",
        "native_identity",
        "files",
        "reference",
        "gram",
        "hidden_solver",
        "network_quadrature",
        "volume_DtN_degree",
        "phase_definition",
        "seed",
        "ranks",
    ):
        if d[key] != old[key]:
            raise InputError("WIDTH_ORIGINAL_PHYSICS_CHANGED:" + key)
    parent = d["parent_checkpoint"]
    if (
        d["campaign"] != "V44_FTT_WIDTH_VS_OPTIMIZATION"
        or d["campaign_version"] != 44
        or d["extension_seed"] != 4214401
        or d["point_batch"] != 512
        or d["cell_batch"] != 8
        or parent["sha256"]
        != "ba2523341b7d1fa1cc339ea1b9544a7468e9fe7faa9dd2f93a8c000cad68e9f8"
        or parent["bytes"] != 1895143
        or parent["inherited_rounds"] != 8
        or parent["input_kind"] != "unlabelled_complete_round8_boundary"
        or parent["binding"]["route"] != "BLOCH_FTTNN_R4_LEARNED_CONTINUE"
        or parent["inherited_counts"]["core_visits"] != 24
        or parent["inherited_counts"]["LSMR_iterations"] != 6905
        or parent["inherited_counts"]["hidden_actual_calls"] != 109
        or d["execution_policies"]
        != {"learned": width_policy(True), "freeze": width_policy(False)}
        or d["limits"]
        != dict(total_seconds=57600, final_reserve_seconds=3600, route_seconds=10800)
        or d["width_models"]
        != {
            "16": dict(real_parameters=9072, hidden_parameters=912),
            "32": dict(real_parameters=19200, hidden_parameters=3360),
        }
        or d["core_refinement"]
        != dict(
            first=dict(atol=1e-8, btol=1e-8, maxiter=300),
            second=dict(atol=1e-10, btol=1e-10, maxiter=900),
            trigger_adjoint_ratio=1e-3,
            max_segments=2,
            damp=0,
            conlim=1e12,
        )
        or d["training"]["from_zero"]
        or d["training"]["reference_used_for_training"]
        or d["production_initialization_allowed"]
    ):
        raise InputError("WIDTH_FROZEN_ARCHITECTURE_PARENT_OR_POLICY_CHANGED")


def load_width(path, data, raw):
    if set(data) != {"schema_version", "neural_wave"} or data["schema_version"] != 14:
        raise InputError("WIDTH_EXPLICIT_SCHEMA_REQUIRED")
    item = data["neural_wave"]
    if set(item) != {"stage", "design_sha256"} or item["stage"] not in STAGES:
        raise InputError("WIDTH_UNKNOWN_STAGE_OR_LABEL")
    if item["design_sha256"] != digest(DESIGN):
        raise InputError("WIDTH_FROZEN_DESIGN_CHANGED")
    validate_design(json.loads(DESIGN.read_text()))
    mode, seconds, role, kind, width = STAGES[item["stage"]]
    return dict(
        stage=item["stage"],
        mode=mode,
        max_seconds=seconds,
        role=role,
        model_kind=kind,
        hidden_width=width,
        metric_kind="native_euc",
        mapping_kind="factored_exact_moments",
        input=str(Path(path).resolve().relative_to(ROOT)),
        input_sha256=hashlib.sha256(raw).hexdigest(),
        design_sha256=item["design_sha256"],
        campaign_version=44,
        case="M5",
        schema="ftt.width-refinement-one-run.v1",
    )


def routes():
    return [(stage, v[2]) for stage, v in STAGES.items() if v[3] is not None]
