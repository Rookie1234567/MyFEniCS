"""Review V11: saved-state diagnostics only, never a training dispatcher."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVIEW_SHA = "bafc9570110bbdcd28de455e9cd4552f3cd80215"
OLD_SECONDS = 154319.25454592914
DESIGN_RECORD = (
    ROOT / "docs/task042extra_feinn_5nm/outcomes/records/diagnostic_design_v12.json"
)
LIMITS = dict(A=900, B=5400, C1=3600, C2=1500, D=3600, E=2400, REPAIR=2400)
STAGES = {
    "v12_saved_state_freeze": ("ml", 900, "A"),
    "v12_saved_field_attribution": ("ml", 4200, "B"),
    "v12_saved_field_integrals": ("fe", 1200, "B"),
    "v12_local_parameter_diagnostic": ("ml", 3600, "C1"),
    "v12_test_space_witness": ("fe", 1500, "C2"),
}
AUTHORITY, SUPERVISED = set(), set()
DIAGNOSTIC_POLICY = dict(
    reference_used_for_training=False,
    reference_used_for_diagnostic=True,
    features_reference_exposed=True,
    pde_only_solve=False,
    benchmark_previously_seen=True,
    production_initialization_allowed=False,
    pde_only_solver_qualified=False,
    official_candidate_results=False,
    diagnostic_only=True,
)
DEPENDENCIES = {s: [] for s in STAGES}
DEPENDENCIES["v12_saved_field_attribution"] = [
    "e1_fe",
    "e3_reference",
    "v12_saved_state_freeze",
    "v11_phase_block_metric",
]

# Hash only the actual read whitelist; the original immutable index is retained.
FILE_KEYS = {
    "e1_fe": ("native", "gram"),
    "e3_reference": ("reference",),
    "v8_phase_checks": ("moments",),
    "v7_p_transfer_checks": ("native",),
    "v8_p4_reference_recovery": ("reference",),
    "v11_phase_block_metric": ("result",),
    "v12_saved_state_freeze": ("fields",),
    "v12_saved_field_attribution": ("vectors", "result"),
}


def selected_index(stage):
    from src.runners.feinn_workflow import load_index

    return load_index(stage, file_keys=FILE_KEYS.get(stage, ("result",)))


DEPENDENCIES["v12_saved_field_integrals"] = [
    "e1_fe",
    "e3_reference",
    "v12_saved_state_freeze",
    "v12_saved_field_attribution",
]
DEPENDENCIES["v12_local_parameter_diagnostic"] = [
    "e1_fe",
    "e3_reference",
    "v8_phase_checks",
    "v12_saved_state_freeze",
    "v12_saved_field_attribution",
]
DEPENDENCIES["v12_test_space_witness"] = [
    "e1_fe",
    "e3_reference",
    "v7_p_transfer_checks",
    "v8_p4_reference_recovery",
    "v12_saved_state_freeze",
    "v12_saved_field_attribution",
]


def campaign_budget(entries):
    chosen = [
        r
        for r in entries
        if "/task42extra_v12_" in r["path"] or "/checks/v12_" in r["path"]
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
        group = group or (name.split("_")[1] if name.startswith("v12_") else "E")
        groups[group if group in groups else "E"] += row["seconds"]
    used = sum(groups.values())
    return dict(
        old_conservative_seconds=OLD_SECONDS,
        new_limit_seconds=21600,
        new_used_seconds=used,
        new_remaining_seconds=21600 - used - 1800,
        cumulative_seconds=OLD_SECONDS + used,
        groups_used_seconds=groups,
        groups_remaining_seconds={k: LIMITS[k] - groups[k] for k in LIMITS},
        entries=chosen,
        saving_and_clearance_reserve_seconds=1800,
        historical_prefix_charged_again_to_project=False,
    )


def dispatch(stage, design, artifact, marker, manifest, load_index):
    pre = json.loads(DESIGN_RECORD.read_text())
    if stage == "v12_saved_state_freeze":
        from src.solvers.feinn_saved_state import freeze

        return freeze(design, pre, artifact, marker, manifest)
    if stage == "v12_saved_field_attribution":
        from src.solvers.feinn_saved_attribution import run
    elif stage == "v12_local_parameter_diagnostic":
        from src.solvers.feinn_local_reachability import run
    else:
        from src.solvers.feinn_saved_field_diagnostics import run
    return run(stage, design, pre, artifact, marker, manifest, selected_index)
