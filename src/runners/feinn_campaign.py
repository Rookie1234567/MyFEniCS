"""Explicit V8 scope and charged campaign budget, without FE/ML imports."""

from pathlib import Path

STAGES = {
    "v8_authority_assembly_checks": ("fe", 1200, "A"),
    "v8_p4_reference_recovery": ("fe", 3600, "A"),
    "v8_p3_p4_compare": ("fe", 1200, "A"),
}
DEPENDENCIES = {
    "v8_authority_assembly_checks": ["e1_fe", "e3_reference", "v7_p_transfer_checks"],
    "v8_p4_reference_recovery": [
        "e1_fe",
        "e3_reference",
        "v7_p_transfer_checks",
        "v8_authority_assembly_checks",
    ],
    "v8_p3_p4_compare": [
        "e1_fe",
        "e3_reference",
        "v7_p_transfer_checks",
        "v8_p4_reference_recovery",
    ],
}
AUTHORITY = set(STAGES)
LIMITS = dict(A=7200, B=3600, C=21600, D=7200, E=3600)
OLD_SECONDS = 49007.27663535159
REVIEW_SHA = "cee68ef5e8219858e3a9b733ffe454334683836b"


def campaign_budget(entries):
    selected = [
        row
        for row in entries
        if "/task42extra_v8_" in row["path"] or "/checks/v8_" in row["path"]
    ]
    used = sum(row["seconds"] for row in selected)
    groups = dict.fromkeys(LIMITS, 0.0)
    for row in selected:
        name = Path(row["path"]).parent.name
        for stage, (_, _, group) in STAGES.items():
            if name.startswith("task42extra_" + stage + "_"):
                groups[group] += row["seconds"]
                break
        else:
            # Light tests identify allocation by v8_a_, v8_b_, etc.
            group = name[3:4].upper() if name.startswith("v8_") else "E"
            groups[group if group in LIMITS else "E"] += row["seconds"]
    return dict(
        old_V1_V7_conservative_seconds=OLD_SECONDS,
        new_limit_seconds=43200,
        new_used_seconds=used,
        new_remaining_seconds=43200 - used - 120,
        cumulative_seconds=OLD_SECONDS + used,
        cumulative_limit_seconds=OLD_SECONDS + 43200,
        groups_used_seconds=groups,
        groups_remaining_seconds={k: LIMITS[k] - groups[k] for k in LIMITS},
        entries=selected,
        tail_allowance_seconds=120,
        old_interruption_and_replay_costs_preserved=True,
    )


def dispatch(stage, design, artifact, marker, manifest, load_index):
    from src.solvers import feinn_authority_assembly as authority
    from src.solvers.feinn_discretization_audit import compare

    args = (
        design,
        load_index("e1_fe"),
        load_index("e3_reference"),
        load_index("v7_p_transfer_checks"),
    )
    if stage == "v8_authority_assembly_checks":
        return authority.checks(*args, artifact, marker, manifest)
    if stage == "v8_p4_reference_recovery":
        return authority.recover(
            *args,
            load_index("v8_authority_assembly_checks"),
            artifact,
            marker,
            manifest,
        )
    if stage == "v8_p3_p4_compare":
        return compare(
            *args, load_index("v8_p4_reference_recovery"), artifact, marker, manifest
        )
    raise ValueError("UNKNOWN_V8_STAGE")
