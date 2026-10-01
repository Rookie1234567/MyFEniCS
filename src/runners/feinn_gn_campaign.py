"""Explicit Review V8/V9 stage inventory, data boundaries and independent budget."""

from pathlib import Path

REVIEW_SHA = "678a1ef5ed5aba9334f05569a6dec04c80e21be4"
OLD_SECONDS = 74341.02060587064
LIMITS = dict(A=7200, B=3600, C=21600, D=7200, E=3600)
STAGES = {
    "v9_p5_checks": ("fe", 1800, "A"),
    "v9_p5_reference": ("fe", 3600, "A"),
    "v9_p_ladder_compare": ("fe", 1800, "A"),
    "v9_gn_checks": ("ml", 3600, "B"),
    "v9_plain_gn": ("ml", 10800 - 1097.6413081260398, "C"),
    "v9_phase_gn": ("ml", 10800 - 1144.848724030, "C"),
    "v9_gn_reconstruct": ("ml", 900, "E"),
    "v9_gn_compare": ("fe", 900, "E"),
    "v9_plain_fit_gn": ("ml", 3600 - 989.7006693100557, "D"),
    "v9_phase_fit_gn": ("ml", 3600 - 1019.1045315240044, "D"),
    "v9_fit_gn_reconstruct": ("ml", 900, "E"),
    "v9_fit_gn_compare": ("fe", 900, "E"),
}
AUTHORITY = {s for s, entry in STAGES.items() if entry[2] == "A"}
SUPERVISED = {s for s in STAGES if "fit_gn" in s}
DEPENDENCIES = {
    "v9_p5_checks": [
        "e1_fe",
        "e3_reference",
        "v7_p_transfer_checks",
        "v8_p4_reference_recovery",
    ],
    "v9_p5_reference": ["e1_fe", "e3_reference", "v9_p5_checks"],
    "v9_p_ladder_compare": [
        "e1_fe",
        "v7_p_transfer_checks",
        "v8_p4_reference_recovery",
        "v9_p5_checks",
        "v9_p5_reference",
    ],
    "v9_gn_checks": [
        "e1_fe",
        "v8_phase_checks",
        "v8_plain_dual",
        "v8_phase_dual",
        "v8_plain_reference_fit",
        "v8_phase_reference_fit",
    ],
    "v9_plain_gn": ["e1_fe", "v8_phase_checks", "v9_gn_checks", "v8_plain_dual"],
    "v9_phase_gn": ["e1_fe", "v8_phase_checks", "v9_gn_checks", "v8_phase_dual"],
    "v9_gn_reconstruct": [
        "e1_fe",
        "v8_phase_checks",
        "v9_plain_gn",
        "v9_phase_gn",
        "v8_plain_dual",
        "v8_phase_dual",
    ],
    "v9_gn_compare": [
        "e1_fe",
        "e3_reference",
        "v8_phase_checks",
        "v9_plain_gn",
        "v9_phase_gn",
        "v9_gn_reconstruct",
    ],
    "v9_plain_fit_gn": [
        "e1_fe",
        "e3_reference",
        "v8_phase_checks",
        "v9_gn_checks",
        "v9_gn_compare",
        "v8_plain_reference_fit",
    ],
    "v9_phase_fit_gn": [
        "e1_fe",
        "e3_reference",
        "v8_phase_checks",
        "v9_gn_checks",
        "v9_gn_compare",
        "v8_phase_reference_fit",
    ],
    "v9_fit_gn_reconstruct": [
        "e1_fe",
        "v8_phase_checks",
        "v9_plain_fit_gn",
        "v9_phase_fit_gn",
        "v8_plain_reference_fit",
        "v8_phase_reference_fit",
    ],
    "v9_fit_gn_compare": [
        "e1_fe",
        "e3_reference",
        "v8_phase_checks",
        "v9_plain_fit_gn",
        "v9_phase_fit_gn",
        "v9_fit_gn_reconstruct",
    ],
}


def campaign_budget(entries):
    chosen = [
        r
        for r in entries
        if "/task42extra_v9_" in r["path"] or "/checks/v9_" in r["path"]
    ]
    groups = dict.fromkeys(LIMITS, 0.0)
    for row in chosen:
        name = Path(row["path"]).parent.name
        for stage, (_, _, group) in STAGES.items():
            if name.startswith("task42extra_" + stage + "_"):
                break
        else:
            group = name[3:4].upper() if name.startswith("v9_") else "E"
        groups[group if group in LIMITS else "E"] += row["seconds"]
    used = sum(r["seconds"] for r in chosen)
    return dict(
        old_V1_V8_conservative_seconds=OLD_SECONDS,
        new_limit_seconds=43200,
        new_used_seconds=used,
        new_remaining_seconds=43200 - used - 120,
        cumulative_seconds=OLD_SECONDS + used,
        groups_used_seconds=groups,
        groups_remaining_seconds={k: LIMITS[k] - groups[k] for k in LIMITS},
        entries=chosen,
        historical_prefix_charged_again_to_project=False,
        old_interruption_and_replay_costs_preserved=True,
        tail_allowance_seconds=120,
    )


def dispatch(stage, design, artifact, marker, manifest, load_index):
    if stage in AUTHORITY:
        from src.solvers import feinn_p_ladder as ladder

        if stage == "v9_p5_checks":
            return ladder.checks(
                design,
                load_index("e1_fe"),
                load_index("e3_reference"),
                artifact,
                marker,
                manifest,
            )
        if stage == "v9_p5_reference":
            return ladder.reference(
                design,
                load_index("e1_fe"),
                load_index("e3_reference"),
                load_index("v9_p5_checks"),
                artifact,
                marker,
                manifest,
            )
        return ladder.compare(
            design,
            load_index("v7_p_transfer_checks"),
            load_index("v8_p4_reference_recovery"),
            load_index("v9_p5_checks"),
            load_index("v9_p5_reference"),
            artifact,
            marker,
            manifest,
        )
    if stage in ("v9_gn_compare", "v9_fit_gn_compare"):
        from src.solvers.feinn_phase_compare import compare

        supervised = "fit_gn" in stage
        names = (
            ("v9_plain_fit_gn", "v9_phase_fit_gn")
            if supervised
            else ("v9_plain_gn", "v9_phase_gn")
        )
        return compare(
            design,
            load_index("e1_fe"),
            load_index("e3_reference"),
            {name: load_index(name) for name in names},
            load_index("v9_fit_gn_reconstruct" if supervised else "v9_gn_reconstruct"),
            artifact,
            marker,
            manifest,
            supervised=supervised,
        )
    from src.solvers import feinn_gn_training as gn

    return gn.dispatch(stage, design, artifact, marker, manifest, load_index)
