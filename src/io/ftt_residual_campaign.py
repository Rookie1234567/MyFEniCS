"""Explicit one-branch residual schema with fixed physics, initialization and limits."""

import hashlib
import json
from pathlib import Path
from src.io.input_loader import InputError
from src.io.neural_wave_campaign import ROOT, digest
from src.solvers.ftt_residual_branch import residual_policy

DESIGN = ROOT / "input/task042extra_feinn_5nm/design_v46.json"
STAGES = {
    "v46_residual_branch_checks": ("ml", 3600, "residual_branch_checks", None),
    "v46_residual_branch_prepare": ("ml", 600, "residual_branch_prepare", None),
    "v46_residual_branch_learned": ("ml", 10800, "RESIDUAL_FTT_R8_LEARNED", "fttnn"),
    "v46_residual_branch_frozen": ("ml", 10800, "RESIDUAL_FTT_R8_FROZEN", "fttnn"),
    "v46_residual_branch_compare": ("pure", 3600, "residual_branch_compare", None),
}


def validate_design(d):
    old = json.loads(
        (ROOT / "input/task042extra_feinn_5nm/design_v45.json").read_text()
    )
    for key in (
        "model",
        "native_identity",
        "files",
        "reference",
        "gram",
        "hidden_solver",
        "core_solver",
        "axis_orders",
        "network_quadrature",
        "volume_DtN_degree",
        "phase_definition",
        "seed",
        "ranks",
        "core_refinement",
    ):
        if d[key] != old[key]:
            raise InputError("RESIDUAL_ORIGINAL_PHYSICS_CHANGED:" + key)
    base = d["base_checkpoint"]
    if (
        d["campaign"] != "V46_FTT_ONE_RESIDUAL_BRANCH"
        or d["campaign_version"] != 46
        or base["sha256"]
        != "0121d04be3ae7c8fdaed1fefe23462c378dc81fa841ee0751040c7800d2b4978"
        or base["bytes"] != 2029380
        or base["inherited_rounds"] != 14
        or base["binding"]["route"] != "W32_R12_IDENTITY_FROZEN"
        or base["inherited_counts"]["core_visits"] != 42
        or base["inherited_counts"]["LSMR_iterations"] != 25758
        or base["inherited_counts"]["hidden_actual_calls"] != 137
        or d["execution_policies"]
        != {"learned": residual_policy(True), "freeze": residual_policy(False)}
        or d["limits"]
        != dict(total_seconds=43200, final_reserve_seconds=3600, route_seconds=10800)
        or d["hidden_width"] != 32
        or d["point_batch"] != 512
        or d["cell_batch"] != 8
        or d["branch_rule"]
        != dict(
            fixed_base=True,
            new_correction_branches=1,
            zero_output_axis=2,
            copy_hidden_and_xy_outputs=True,
            training_rhs="f_minus_A_cbase",
            coordinate_transform="identity",
            training_denominator="norm_g",
            official_denominator="norm_f",
            sum_points_before_independent_interpolation=True,
        )
        or d["training"]["reference_used_for_training"]
        or d["production_initialization_allowed"]
    ):
        raise InputError("RESIDUAL_BASE_BRANCH_POLICY_OR_PURPOSE_CHANGED")


def load_residual(path, data, raw):
    if set(data) != {"schema_version", "neural_wave"} or data["schema_version"] != 16:
        raise InputError("RESIDUAL_BRANCH_EXPLICIT_SCHEMA_REQUIRED")
    item = data["neural_wave"]
    if set(item) != {"stage", "design_sha256"} or item["stage"] not in STAGES:
        raise InputError("RESIDUAL_BRANCH_UNKNOWN_STAGE_OR_LABEL")
    if item["design_sha256"] != digest(DESIGN):
        raise InputError("RESIDUAL_FROZEN_DESIGN_CHANGED")
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
        campaign_version=46,
        case="M5",
        schema="ftt.one-residual-one-run.v1",
    )


def routes():
    return [(stage, v[2]) for stage, v in STAGES.items() if v[3] is not None]
