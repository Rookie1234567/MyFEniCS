"""Width/refinement profile using the original trainer and independent audit."""

from src.io.neural_wave_campaign import ROOT
from src.io.ftt_width_campaign import DESIGN, routes
from src.runners.ftt_core_worker import CoreWorkerProfile, main
from src.runners.ftt_bloch_worker import (
    CHAIN as BLOCH_CHAIN,
    point_field,
    training_options as scalar_options,
)
from src.postprocessing.ftt_common_wall import compare_common_wall
from src.solvers.neural_wave_greedy import atomic_json
import json

ART = ROOT / "benchmarks/artifacts/task42extra/v44"
CHAIN = BLOCH_CHAIN + (
    "src/io/ftt_width_campaign.py",
    "src/solvers/ftt_width_extension.py",
    "src/solvers/ftt_width_qualification.py",
    "src/solvers/ftt_core_refinement.py",
    "src/solvers/ftt_core_continuation.py",
    "src/runners/ftt_width_worker.py",
    "src/runners/ftt_continuation_feedback.py",
    "src/runners/ftt_continuation_joint.py",
    "src/postprocessing/ftt_common_wall.py",
)


def model_factory(design, value):
    from src.solvers.ftt_bloch_field import BlochFTTField

    return BlochFTTField(
        design["model"]["geometry"]["bounds_nm"],
        "fttnn",
        design["phase_definition"],
        seed=design["seed"],
        hidden_width=value.get("hidden_width", 16),
    )


def qualification(action, packet, design, marker, deadline):
    from src.solvers.ftt_width_qualification import qualify_width

    return qualify_width(action, packet, design, marker, deadline)


def training_options(manifest, artifact, marker, directory, design):
    from src.solvers.ftt_width_extension import import_width_parent
    from src.runners.ftt_continuation_feedback import joint_callback

    options = scalar_options(
        manifest,
        artifact,
        marker,
        directory,
        design,
        design_path=DESIGN,
        scoring_root=ART,
    )
    learned = manifest["spec"]["role"] != "W32_REFINED_CORE_FROZEN"
    options.update(
        parent_checkpoint=design["parent_checkpoint"],
        execution_policy=design["execution_policies"][
            "learned" if learned else "freeze"
        ],
        parent_importer=import_width_parent,
        joint_validation_callback=joint_callback(
            manifest, artifact, directory, marker, ART, design_path=DESIGN
        ),
    )
    return options


def comparison_decision(manifest, artifact, marker, directory):
    from src.solvers.ftt_width_extension import strong_width_signal

    common = compare_common_wall(manifest, artifact, marker, directory)
    records = json.loads((artifact / "saved_checker.json").read_text())["records"]
    results = {
        role: json.loads((ART / stage / "result.json").read_text())
        for stage, role in routes()
    }

    def scalar(role):
        row = records[role]
        return dict(
            native_relative=max(
                row["equation_audit"]["native_relative"],
                row["equation_audit"]["augmented_relative"],
            ),
            scattered_E_relative=row["field_errors"]["scattered_E"]["relative"],
            scattered_H_relative=row["field_errors"]["scattered_H_code"]["relative"],
        )

    wide, narrow = "W32_REFINED_CORE_LEARNED", "W16_REFINED_CORE_LEARNED"
    decision = strong_width_signal(
        scalar(wide),
        scalar(narrow),
        all_three_complete=all(
            r["position"]["complete_rounds"] == 12 for r in results.values()
        ),
        joint_pass=bool(records[wide]["m5_full_discrete_numerical_gate"]),
    )
    decision.update(
        checker_path=str((artifact / "saved_checker.json").relative_to(ROOT)),
        checkpoints={role: r["checkpoint"]["sha256"] for role, r in results.items()},
        inherited_route_wall_not_reset=True,
        conditional_0p7_eligible=bool(records[wide]["m5_full_discrete_numerical_gate"]),
        default_round12_results_preserved=True,
    )
    atomic_json(artifact / "fixed_extra_round_decision.json", decision)
    marker("fixed_width_extra_round_decision", decision)
    return dict(common_wall=common, extra_round_decision=decision)


PROFILE = CoreWorkerProfile(
    design=DESIGN,
    artifacts=ART,
    route_pairs=routes,
    checks_stage="v44_width_and_inner_checks",
    checks_role="width_inner_checks",
    compare_role="width_independent_compare",
    worker_module="src.runners.ftt_width_worker",
    qualification=qualification,
    independent_field=point_field,
    training_options=training_options,
    route_model_factory=model_factory,
    reconstruction_model_factory=model_factory,
    learned_roles=("W16_REFINED_CORE_LEARNED", "W32_REFINED_CORE_LEARNED"),
    compare_postprocess=comparison_decision,
)

if __name__ == "__main__":
    main(PROFILE)
