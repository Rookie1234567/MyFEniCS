"""Review V9 opt-in continuation inventory; FE branches never import Torch."""

from pathlib import Path

REVIEW_SHA = "47317bb648d5e2237657f8b6c75c239ab5bf55c5"
OLD_SECONDS = 99864.4864455976
LIMITS = dict(A=150, B=10650, C=21600, D=7200, E=3600)
AUTHORITY = set()
STAGES = {
    "v10_state_and_work_audit": ("ml", 1800, "A"),
    "v10_derivative_checks": ("ml", 6000, "B"),
    "v10_derivative_checks_repair": ("ml", 6000, "B"),
    "v10_derivative_benchmark": ("ml", 9000, "B"),
    "v10_plain_cached_gn": ("ml", 10800, "C"),
    "v10_phase_cached_gn": ("ml", 10800, "C"),
    "v10_gn_reconstruct": ("ml", 900, "E"),
    "v10_gn_compare": ("fe", 900, "E"),
    "v10_plain_cached_fit_gn": ("ml", 3600, "D"),
    "v10_phase_cached_fit_gn": ("ml", 3600, "D"),
    "v10_fit_reconstruct": ("ml", 900, "E"),
    "v10_fit_compare": ("fe", 900, "E"),
}
SUPERVISED = {s for s in STAGES if "fit" in s}
BASE = ["e1_fe", "v8_phase_checks"]
OLD = ["v9_" + p + s for s in ("_gn", "_fit_gn") for p in ("plain", "phase")]
DEPENDENCIES = {s: BASE.copy() for s in STAGES}
DEPENDENCIES["v10_state_and_work_audit"] += OLD
DEPENDENCIES["v10_derivative_checks"] += OLD + [
    "e3_reference",
    "v10_state_and_work_audit",
]
DEPENDENCIES["v10_derivative_benchmark"] += OLD + [
    "e3_reference",
    "v10_derivative_checks_repair",
]
DEPENDENCIES["v10_derivative_checks_repair"] = DEPENDENCIES["v10_derivative_checks"] + [
    "v10_derivative_checks"
]
for name in (
    "v10_plain_cached_gn",
    "v10_phase_cached_gn",
    "v10_plain_cached_fit_gn",
    "v10_phase_cached_fit_gn",
):
    key = ("phase" if "phase" in name else "plain") + (
        "_fit_gn" if "fit" in name else "_gn"
    )
    DEPENDENCIES[name] += ["v9_" + key, "v10_derivative_benchmark"]
    if "fit" in name:
        DEPENDENCIES[name] += ["e3_reference", "v10_gn_compare"]
for kind in ("gn", "fit"):
    for method in ("reconstruct", "compare"):
        stage = "v10_" + kind + "_" + method
        DEPENDENCIES[stage] += ["v10_derivative_benchmark"] + [
            "v9_" + p + ("_fit_gn" if kind == "fit" else "_gn")
            for p in ("plain", "phase")
        ]
        if method == "compare":
            DEPENDENCIES[stage] += ["e3_reference", "v10_" + kind + "_reconstruct"]


def campaign_budget(entries):
    chosen = [
        r
        for r in entries
        if "/task42extra_v10_" in r["path"] or "/checks/v10_" in r["path"]
    ]
    groups = dict.fromkeys(LIMITS, 0.0)
    for row in chosen:
        name = Path(row["path"]).parent.name
        matched = next(
            (
                entry[2]
                for stage, entry in STAGES.items()
                if name.startswith("task42extra_" + stage + "_")
            ),
            None,
        )
        group = matched or (name[4:5].upper() if name.startswith("v10_") else "E")
        groups[group if group in LIMITS else "E"] += row["seconds"]
    used = sum(r["seconds"] for r in chosen)
    return dict(
        old_V1_V9_conservative_seconds=OLD_SECONDS,
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


def selected_routes(load_index, *, supervised, include_old=False):
    gates = load_index("v10_derivative_benchmark")["result"]["states"]
    routes = {}
    for p in ("plain", "phase"):
        old = "v9_" + p + ("_fit_gn" if supervised else "_gn")
        new = "v10_" + p + ("_cached_fit_gn" if supervised else "_cached_gn")
        key = p + ("_fit_gn" if supervised else "_gn")
        stage = new if gates[key]["passed"] else old
        routes[stage] = load_index(stage)
    if include_old:
        for p in ("plain", "phase"):
            old = "v9_" + p + ("_fit_gn" if supervised else "_gn")
            routes[old] = load_index(old)
    return routes


def dispatch(stage, design, artifact, marker, manifest, load_index):
    if stage in ("v10_gn_compare", "v10_fit_compare"):
        from src.solvers.feinn_phase_compare import compare

        supervised = "fit" in stage
        result, files = compare(
            design,
            load_index("e1_fe"),
            load_index("e3_reference"),
            selected_routes(load_index, supervised=supervised, include_old=True),
            load_index("v10_fit_reconstruct" if supervised else "v10_gn_reconstruct"),
            artifact,
            marker,
            manifest,
            supervised=supervised,
        )
        result["status"] = (
            "V10_FIT_COMPARE_ONLY_COMPLETE"
            if supervised
            else "V10_GN_COMPARE_ONLY_COMPLETE"
        )
        return result, files
    if stage in ("v10_gn_reconstruct", "v10_fit_reconstruct"):
        from src.solvers.feinn_phase_verification import reconstruct

        return reconstruct(
            design,
            load_index("v8_phase_checks"),
            selected_routes(load_index, supervised="fit" in stage, include_old=True),
            artifact,
            marker,
            manifest,
            retain_initial=False,
        )
    from src.solvers import feinn_derivative_reuse as reuse

    if stage == "v10_state_and_work_audit":
        return reuse.audit(
            design,
            load_index("e1_fe"),
            load_index("v8_phase_checks"),
            artifact,
            marker,
            manifest,
            load_index,
        )
    if stage in ("v10_derivative_checks", "v10_derivative_checks_repair"):
        return reuse.checks(
            design,
            load_index("e1_fe"),
            load_index("v8_phase_checks"),
            load_index("e3_reference"),
            artifact,
            marker,
            manifest,
        )
    if stage == "v10_derivative_benchmark":
        return reuse.benchmark(
            design,
            load_index("e1_fe"),
            load_index("v8_phase_checks"),
            load_index("e3_reference"),
            load_index("v10_derivative_checks_repair"),
            artifact,
            marker,
            manifest,
        )
    from src.solvers.feinn_gn_training import run

    supervised = "fit" in stage
    if supervised and load_index("v10_gn_compare")["result"]["phase_strict_qualified"]:
        raise ValueError("D_NOT_AUTHORIZED_AFTER_PHASE_PDE_PASS")
    phase = "phase" in stage
    key = ("phase" if phase else "plain") + ("_fit_gn" if supervised else "_gn")
    return run(
        design,
        load_index("e1_fe"),
        load_index("v8_phase_checks"),
        load_index("v10_derivative_benchmark"),
        artifact,
        marker,
        manifest,
        phase=phase,
        supervised=supervised,
        reference=load_index("e3_reference") if supervised else None,
        continuation=reuse.frozen_entries()[key],
    )
