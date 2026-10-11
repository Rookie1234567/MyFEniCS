"""Explicit V45 feature-coordinate inputs; old campaign schemas unchanged."""

import hashlib
import json
from pathlib import Path
from src.io.input_loader import InputError
from src.io.neural_wave_campaign import ROOT, digest

DESIGN = ROOT / "input/task042extra_feinn_5nm/design_v45.json"
STAGES = {
    "v45_feature_coordinates_checks": ("ml", 3600, "feature_coordinates_checks", None),
    "v45_identity_frozen": ("ml", 7200, "W32_R12_IDENTITY_FROZEN", "fttnn"),
    "v45_feature_scaled_frozen": ("ml", 7200, "W32_R12_FEATURE_SCALED_FROZEN", "fttnn"),
    "v45_feature_scaled_learned": ("ml", 7200, "W32_R12_FEATURE_SCALED_LEARNED", "fttnn"),
    "v45_feature_coordinates_compare": ("pure", 3600, "feature_coordinates_compare", None),
}


def validate_design(d):
    from src.solvers.ftt_feature_coordinates import coordinate_policy
    old = json.loads((ROOT / "input/task042extra_feinn_5nm/design_v44.json").read_text())
    for key in ("model", "native_identity", "files", "reference", "gram", "hidden_solver",
                "network_quadrature", "volume_DtN_degree", "phase_definition", "seed", "ranks", "core_refinement"):
        if d[key] != old[key]:
            raise InputError("FEATURE_COORDINATE_ORIGINAL_PHYSICS_CHANGED:" + key)
    parent = d["parent_checkpoint"]
    if (d["campaign"] != "V45_FTT_FEATURE_COORDINATE_SOLVE" or d["campaign_version"] != 45
        or parent["sha256"] != "02109f3e8d8f5361bc1d7f3b16633e1d257017fd1cf3b808bba6aad4fa57708f"
        or parent["bytes"] != 2020100 or parent["inherited_rounds"] != 12
        or parent["binding"]["route"] != "W32_REFINED_CORE_LEARNED"
        or parent["inherited_counts"]["core_visits"] != 36
        or parent["inherited_counts"]["LSMR_iterations"] != 19830
        or parent["inherited_counts"]["hidden_actual_calls"] != 137
        or d["execution_policies"] != {"learned": coordinate_policy(True), "freeze": coordinate_policy(False)}
        or d["coordinate_rule"] != dict(tau=1e-6, stability_only_fallback_tau=1e-4,
            feature_dimension=33, directions_removed=0, node_rule="all_exact_unique_factored_nodes_sorted",
            residual_left_weight_changed=False, actual_delta="P_y", adjoint="P_conjugate_transpose_BH")
        or d["limits"] != dict(total_seconds=43200, final_reserve_seconds=3600, route_seconds=7200)
        or d["hidden_width"] != 32 or d["point_batch"] != 512 or d["cell_batch"] != 8
        or d["training"]["reference_used_for_training"] or d["production_initialization_allowed"]):
        raise InputError("FEATURE_COORDINATE_PARENT_POLICY_OR_USE_CHANGED")


def load_coordinates(path, data, raw):
    if set(data) != {"schema_version", "neural_wave"} or data["schema_version"] != 15:
        raise InputError("FEATURE_COORDINATES_EXPLICIT_SCHEMA_REQUIRED")
    item = data["neural_wave"]
    if set(item) != {"stage", "design_sha256"} or item["stage"] not in STAGES:
        raise InputError("FEATURE_COORDINATES_UNKNOWN_STAGE_OR_LABEL")
    if item["design_sha256"] != digest(DESIGN):
        raise InputError("FEATURE_COORDINATES_FROZEN_DESIGN_CHANGED")
    validate_design(json.loads(DESIGN.read_text()))
    mode, seconds, role, kind = STAGES[item["stage"]]
    return dict(stage=item["stage"], mode=mode, max_seconds=seconds, role=role, model_kind=kind,
        hidden_width=32, metric_kind="native_euc", mapping_kind="factored_exact_moments",
        input=str(Path(path).resolve().relative_to(ROOT)), input_sha256=hashlib.sha256(raw).hexdigest(),
        design_sha256=item["design_sha256"], campaign_version=45, case="M5",
        schema="ftt.feature-coordinates-one-run.v1")


def routes():
    return [(stage, value[2]) for stage, value in STAGES.items() if value[3] is not None]
