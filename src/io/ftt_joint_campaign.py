"""Explicit bounded joint-tangent decision; no change to original physics."""

import hashlib
import json
from pathlib import Path
from src.io.input_loader import InputError
from src.io.neural_wave_campaign import ROOT, digest

DESIGN = ROOT / "input/task042extra_feinn_5nm/design_v47.json"
ART = ROOT / "benchmarks/artifacts/task42extra/v47"
STAGES = {
    "v47_joint_tangent_checks": ("ml", 3600, "joint_tangent_checks", None),
    "v47_joint_step_probe": ("ml", 900, "FTT_JOINT_STEP_PROBE", "fttnn"),
    "v47_joint_all": ("ml", 5400, "FTT_JOINT_LM_ALL", "fttnn"),
    "v47_joint_output_only": ("ml", 5400, "FTT_JOINT_LM_OUTPUT_ONLY", "fttnn"),
    "v47_joint_compare": ("pure", 3600, "joint_tangent_compare", None),
}


def joint_policy(probe=False):
    return dict(
        lsmr_atol=1e-6,
        lsmr_btol=1e-6,
        lsmr_conlim=1e12,
        lsmr_maxiter=200,
        total_lsmr=400 if probe else 4800,
        trial_limit=3 if probe else 32,
        accepted_limit=3 if probe else 16,
        rejection_streak_limit=8,
        h_seed=4214701,
        h_power_iterations=4,
        initial_lambda_h=1e-3,
        minimum_lambda_h=1e-12,
        maximum_lambda_h=1e8,
        acceptance_rho=0.1,
        native_target=1e-8,
        final_save_reserve_s=120,
        cauchy_fallbacks_per_invalid_lsmr_prediction=1,
    )


def validate_design(d):
    old = json.loads(
        (ROOT / "input/task042extra_feinn_5nm/design_v46.json").read_text()
    )
    for k in (
        "model",
        "native_identity",
        "files",
        "reference",
        "gram",
        "network_quadrature",
        "volume_DtN_degree",
        "phase_definition",
        "seed",
        "ranks",
        "hidden_width",
        "point_batch",
        "cell_batch",
        "base_checkpoint",
        "prepared_branch",
    ):
        if d[k] != old[k]:
            raise InputError("JOINT_ORIGINAL_PHYSICS_OR_BASE_CHANGED:" + k)
    p = d["parent_checkpoint"]
    if (
        d["campaign"] != "V47_FTT_JOINT_TANGENT_DECISION"
        or d["campaign_version"] != 47
        or p["sha256"]
        != "3bfe977c9235ea4305a1eb4049401b098c30dce87bfce76f635e5c88e3bf8c58"
        or p["bytes"] != 6513249
        or p["model_hash"]
        != "68960e7a840f84ef901edf1492946eff0f4a3918b638d5ba7025dac4b29d0a36"
        or d["base_model_hash"]
        != "4d46260fe9668557393133dc9c93f737955ef4fda0a8f2562dcbf437f49c70f9"
        or p["binding"]["route"] != "RESIDUAL_FTT_R8_LEARNED"
        or d["execution_policies"]
        != dict(probe=joint_policy(True), formal=joint_policy())
        or d["limits"]
        != dict(total_seconds=28800, final_reserve_seconds=1800, route_seconds=5400)
        or d["probe_result"]
        != str((ART / "v47_joint_step_probe/result.json").relative_to(ROOT))
        or d["production_initialization_allowed"]
        or d["training"]["reference_used_for_training"]
    ):
        raise InputError("JOINT_PARENT_POLICY_OR_PURPOSE_CHANGED")


def load_joint(path, data, raw):
    if set(data) != {"schema_version", "neural_wave"} or data["schema_version"] != 17:
        raise InputError("JOINT_EXPLICIT_SCHEMA_REQUIRED")
    item = data["neural_wave"]
    if set(item) != {"stage", "design_sha256"} or item["stage"] not in STAGES:
        raise InputError("JOINT_UNKNOWN_STAGE_OR_LABEL")
    if item["design_sha256"] != digest(DESIGN):
        raise InputError("JOINT_FROZEN_DESIGN_CHANGED")
    validate_design(json.loads(DESIGN.read_text()))
    mode, seconds, role, kind = STAGES[item["stage"]]
    return dict(
        stage=item["stage"],
        mode=mode,
        max_seconds=seconds,
        role=role,
        model_kind=kind,
        hidden_width=32,
        metric_kind="native_euc",
        mapping_kind="factored_exact_moments",
        input=str(Path(path).resolve().relative_to(ROOT)),
        input_sha256=hashlib.sha256(raw).hexdigest(),
        design_sha256=item["design_sha256"],
        campaign_version=47,
        case="M5",
        schema="ftt.joint-tangent-one-run.v1",
    )


def routes():
    formal = [
        (s, STAGES[s][2])
        for s in ("v47_joint_all", "v47_joint_output_only")
        if (ART / s / "result.json").exists()
    ]
    return formal or [("v47_joint_step_probe", "FTT_JOINT_STEP_PROBE")]
