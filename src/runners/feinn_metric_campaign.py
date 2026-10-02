"""Review V10 fixed-parameter-metric pilot inventory; no FE Torch import."""

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
REVIEW_SHA = "13ca73756a4c74bd24ad5241d97a810bfcce6971"
OLD_SECONDS = 137403.03555569297
LIMITS = dict(A=1800, B=5400, C=10800, E=3600)
STAGES = {
    "v11_parameter_scale_diagnostic": ("ml", 1200, "A"),
    "v11_parameter_metric_checks": ("ml", 2400, "B"),
    "v11_parameter_metric_checks_repair": ("ml", 900, "B"),
    "v11_parameter_metric_checks_stability": ("ml", 900, "B"),
    "v11_phase_identity_metric": ("ml", 5400, "C"),
    "v11_phase_block_metric": ("ml", 5400, "C"),
    "v11_metric_reconstruct": ("ml", 900, "E"),
    "v11_metric_compare": ("fe", 1200, "E"),
}
AUTHORITY, SUPERVISED = set(), set()
BASE = ["e1_fe", "v8_phase_checks", "v10_phase_resource_freeze"]
DEPENDENCIES = {stage: BASE.copy() for stage in STAGES}
DEPENDENCIES["v11_parameter_metric_checks"] += ["v11_parameter_scale_diagnostic"]
DEPENDENCIES["v11_parameter_metric_checks_repair"] += [
    "v11_parameter_scale_diagnostic",
    "v11_parameter_metric_checks",
]
DEPENDENCIES["v11_parameter_metric_checks_stability"] += [
    "v11_parameter_scale_diagnostic",
    "v11_parameter_metric_checks_repair",
]
for stage in ("v11_phase_identity_metric", "v11_phase_block_metric"):
    DEPENDENCIES[stage] += [
        "v11_parameter_scale_diagnostic",
        "v11_parameter_metric_checks",
    ]
DEPENDENCIES["v11_metric_compare"] += ["e3_reference", "v11_metric_reconstruct"]


def anchor():
    record = json.loads(
        (
            ROOT
            / "docs/task042extra_feinn_5nm/outcomes/records/campaign_design_v11.json"
        ).read_text()
    )
    return record["frozen_phase75"]


def campaign_budget(entries):
    chosen = [
        r
        for r in entries
        if "/task42extra_v11_" in r["path"] or "/checks/v11_" in r["path"]
    ]
    groups = dict.fromkeys(LIMITS, 0.0)
    for row in chosen:
        name = Path(row["path"]).parent.name
        group = next(
            (
                e[2]
                for s, e in STAGES.items()
                if name.startswith("task42extra_" + s + "_")
            ),
            None,
        )
        group = group or (name[4:5].upper() if name.startswith("v11_") else "E")
        groups[group if group in LIMITS else "E"] += row["seconds"]
    used = sum(groups.values())
    return dict(
        old_V1_V10_conservative_seconds=OLD_SECONDS,
        new_limit_seconds=21600,
        new_used_seconds=used,
        new_remaining_seconds=21600 - used - 1200,
        cumulative_seconds=OLD_SECONDS + used,
        groups_used_seconds=groups,
        groups_remaining_seconds={k: LIMITS[k] - groups[k] for k in LIMITS},
        entries=chosen,
        E_reserved_seconds=1200,
        historical_prefix_charged_again_to_project=False,
        old_interruption_and_replay_costs_preserved=True,
    )


def selected_routes(load_index):
    from src.runners.feinn_workflow import index_path

    routes = {"v10_phase_resource_freeze": load_index("v10_phase_resource_freeze")}
    for stage in ("v11_phase_identity_metric", "v11_phase_block_metric"):
        if index_path(stage).exists():
            routes[stage] = load_index(stage)
    return routes


def qualified_checks_stage():
    from src.runners.feinn_workflow import index_path

    repair = "v11_parameter_metric_checks_repair"
    stable = "v11_parameter_metric_checks_stability"
    if index_path(stable).exists():
        return stable
    return repair if index_path(repair).exists() else "v11_parameter_metric_checks"


def dispatch(stage, design, artifact, marker, manifest, load_index):
    if stage == "v11_metric_reconstruct":
        from src.solvers.feinn_phase_verification import reconstruct
        from src.solvers.feinn_metric_verification import time_routes

        routes, time_index = time_routes(design, selected_routes(load_index), artifact)
        result, files = reconstruct(
            design,
            load_index("v8_phase_checks"),
            routes,
            artifact,
            marker,
            manifest,
            retain_initial=False,
        )
        files["time_route_index"] = time_index
        return result, files
    if stage == "v11_metric_compare":
        from src.solvers.feinn_phase_compare import compare

        reconstructed = load_index("v11_metric_reconstruct")
        routes = json.loads(
            Path(reconstructed["files"]["time_route_index"]["path"]).read_text()
        )
        result, files = compare(
            design,
            load_index("e1_fe"),
            load_index("e3_reference"),
            routes,
            reconstructed,
            artifact,
            marker,
            manifest,
            supervised=False,
        )
        result.update(
            status="V11_METRIC_COMPARE_ONLY_COMPLETE",
            conditional_D_required=False,
            D_authorized_in_this_batch=False,
            phase_strict_qualified=any(
                r["pde_only_solver_qualified"]
                for name, r in result["routes"].items()
                if name.startswith("V11-PHASE-")
            ),
        )
        return result, files
    from src.solvers import feinn_metric_diagnostic as diagnostic

    if stage == "v11_parameter_scale_diagnostic":
        return diagnostic.diagnose(
            design,
            load_index("e1_fe"),
            load_index("v8_phase_checks"),
            artifact,
            marker,
            manifest,
        )
    if stage == "v11_parameter_metric_checks":
        return diagnostic.qualify(
            design,
            load_index("e1_fe"),
            load_index("v8_phase_checks"),
            load_index("v11_parameter_scale_diagnostic"),
            artifact,
            marker,
            manifest,
        )
    if stage == "v11_parameter_metric_checks_repair":
        return diagnostic.qualify_fd_tail(
            design,
            load_index("e1_fe"),
            load_index("v8_phase_checks"),
            load_index("v11_parameter_scale_diagnostic"),
            load_index("v11_parameter_metric_checks"),
            artifact,
            marker,
            manifest,
        )
    if stage == "v11_parameter_metric_checks_stability":
        return diagnostic.qualify_fd_tail(
            design,
            load_index("e1_fe"),
            load_index("v8_phase_checks"),
            load_index("v11_parameter_scale_diagnostic"),
            load_index("v11_parameter_metric_checks_repair"),
            artifact,
            marker,
            manifest,
            epsilon=3e-7,
        )
    from src.solvers.feinn_gn_training import run

    return run(
        design,
        load_index("e1_fe"),
        load_index("v8_phase_checks"),
        load_index(qualified_checks_stage()),
        artifact,
        marker,
        manifest,
        phase=True,
        supervised=False,
        continuation=anchor(),
        metric_pilot=load_index("v11_parameter_scale_diagnostic"),
        recovery=manifest.get("V11_fault_recovery"),
    )
