"""Explicit V8 scope and charged campaign budget, without FE/ML imports."""

from pathlib import Path

STAGES = {
    "v8_authority_profile": ("fe", 600, "A"),
    "v8_authority_assembly_checks": ("fe", 1200, "A"),
    "v8_p4_reference_recovery": ("fe", 3600, "A"),
    "v8_p3_p4_compare": ("fe", 1200, "A"),
    "v8_phase_moment_checks": ("fe", 1800, "B"),
    "v8_phase_checks": ("ml", 1800, "B"),
    "v8_plain_dual": ("ml", 10800, "C"),
    "v8_phase_dual": ("ml", 10800, "C"),
    "v8_pde_reconstruct": ("ml", 900, "E"),
    "v8_pde_compare": ("fe", 900, "E"),
    "v8_plain_reference_fit": ("ml", 3600, "D"),
    "v8_phase_reference_fit": ("ml", 3600, "D"),
    "v8_representation_reconstruct": ("ml", 900, "E"),
    "v8_representation_compare": ("fe", 900, "E"),
}
DEPENDENCIES = {
    "v8_authority_profile": [
        "e1_fe",
        "v7_p_transfer_checks",
        "v8_authority_assembly_checks",
    ],
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
    "v8_phase_moment_checks": ["e1_fe"],
    "v8_phase_checks": ["e1_fe", "v8_phase_moment_checks"],
    "v8_plain_dual": ["e1_fe", "v8_phase_checks"],
    "v8_phase_dual": ["e1_fe", "v8_phase_checks"],
    "v8_pde_reconstruct": [
        "e1_fe",
        "v8_phase_checks",
        "v8_plain_dual",
        "v8_phase_dual",
    ],
    "v8_pde_compare": [
        "e1_fe",
        "e3_reference",
        "v8_phase_checks",
        "v8_plain_dual",
        "v8_phase_dual",
        "v8_pde_reconstruct",
    ],
    "v8_plain_reference_fit": [
        "e1_fe",
        "e3_reference",
        "v8_phase_checks",
        "v8_pde_compare",
    ],
    "v8_phase_reference_fit": [
        "e1_fe",
        "e3_reference",
        "v8_phase_checks",
        "v8_pde_compare",
    ],
    "v8_representation_reconstruct": [
        "e1_fe",
        "v8_phase_checks",
        "v8_plain_reference_fit",
        "v8_phase_reference_fit",
    ],
    "v8_representation_compare": [
        "e1_fe",
        "e3_reference",
        "v8_phase_checks",
        "v8_plain_reference_fit",
        "v8_phase_reference_fit",
        "v8_representation_reconstruct",
    ],
}
AUTHORITY = {name for name, entry in STAGES.items() if entry[2] == "A"}
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
    if stage == "v8_phase_moment_checks":
        from src.solvers.feinn_phase_moments import prepare

        return prepare(design, load_index("e1_fe"), artifact, marker, manifest)
    if stage == "v8_phase_checks":
        from src.solvers.feinn_phase_training import qualify

        return qualify(
            design,
            load_index("e1_fe"),
            load_index("v8_phase_moment_checks"),
            artifact,
            marker,
            manifest,
        )
    if stage in (
        "v8_plain_dual",
        "v8_phase_dual",
        "v8_plain_reference_fit",
        "v8_phase_reference_fit",
    ):
        from src.solvers.feinn_phase_training import run

        supervised = stage.endswith("reference_fit")
        if supervised:
            comparison = load_index("v8_pde_compare")
            if comparison["result"]["phase_strict_qualified"]:
                raise ValueError("CONDITIONAL_D_NOT_AUTHORIZED_AFTER_PHASE_PASS")
        return run(
            design,
            load_index("e1_fe"),
            load_index("v8_phase_checks"),
            artifact,
            marker,
            manifest,
            phase=stage.startswith("v8_phase_"),
            supervised=supervised,
            reference_index=load_index("e3_reference") if supervised else None,
        )
    if stage in ("v8_pde_reconstruct", "v8_representation_reconstruct"):
        from src.solvers.feinn_phase_verification import reconstruct

        return reconstruct(
            design,
            load_index("v8_phase_checks"),
            {
                name: load_index(name)
                for name in DEPENDENCIES[stage]
                if name.startswith(
                    ("v8_plain_", "v8_phase_dual", "v8_phase_reference_fit")
                )
            },
            artifact,
            marker,
            manifest,
        )
    if stage in ("v8_pde_compare", "v8_representation_compare"):
        from src.solvers.feinn_phase_compare import compare

        supervised = stage == "v8_representation_compare"
        names = (
            ["v8_plain_reference_fit", "v8_phase_reference_fit"]
            if supervised
            else ["v8_plain_dual", "v8_phase_dual"]
        )
        return compare(
            design,
            load_index("e1_fe"),
            load_index("e3_reference"),
            {n: load_index(n) for n in names},
            load_index(
                "v8_representation_reconstruct" if supervised else "v8_pde_reconstruct"
            ),
            artifact,
            marker,
            manifest,
            supervised=supervised,
        )
    from src.solvers import feinn_authority_assembly as authority
    from src.solvers.feinn_discretization_audit import compare

    if stage == "v8_authority_profile":
        return authority.profile_checks(artifact, marker)
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
