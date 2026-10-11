"""Parent-fork profile only; reuse the original conditional-core trainer."""

from src.io.neural_wave_campaign import ROOT
from src.io.ftt_continuation_campaign import DESIGN, routes
from src.runners.ftt_core_worker import CoreWorkerProfile, main
from src.runners.ftt_bloch_worker import (
    CHAIN as BLOCH_CHAIN,
    field_factory,
    point_field,
    training_options as scalar_options,
)
from src.postprocessing.ftt_common_wall import compare_common_wall

ART = ROOT / "benchmarks/artifacts/task42extra/v43"
CHAIN = BLOCH_CHAIN + (
    "src/io/ftt_continuation_campaign.py",
    "src/solvers/ftt_core_continuation.py",
    "src/solvers/ftt_continuation_qualification.py",
    "src/runners/ftt_continuation_worker.py",
    "src/runners/ftt_continuation_joint.py",
    "src/runners/ftt_continuation_feedback.py",
    "src/postprocessing/ftt_common_wall.py",
)


def qualification(action, packet, design, marker, deadline):
    from src.solvers.ftt_continuation_qualification import qualify_parent_fork

    return qualify_parent_fork(action, packet, design, marker, deadline)


def training_options(manifest, artifact, marker, directory, design):
    options = scalar_options(
        manifest,
        artifact,
        marker,
        directory,
        design,
        design_path=DESIGN,
        scoring_root=ART,
    )
    learned = manifest["spec"]["role"] == "BLOCH_FTTNN_R4_LEARNED_CONTINUE"
    options.update(
        parent_checkpoint=design["parent_checkpoint"],
        execution_policy=design["execution_policies"][
            "learned" if learned else "freeze"
        ],
    )
    from src.runners.ftt_continuation_feedback import joint_callback

    options["joint_validation_callback"] = joint_callback(
        manifest, artifact, directory, marker, ART
    )
    return options


PROFILE = CoreWorkerProfile(
    design=DESIGN,
    artifacts=ART,
    route_pairs=routes,
    checks_stage="v43_bloch_resume_checks",
    checks_role="bloch_resume_checks",
    compare_role="bloch_continuation_compare",
    learned_role="BLOCH_FTTNN_R4_LEARNED_CONTINUE",
    worker_module="src.runners.ftt_continuation_worker",
    model_factory=field_factory,
    qualification=qualification,
    independent_field=point_field,
    training_options=training_options,
    compare_postprocess=compare_common_wall,
)


if __name__ == "__main__":
    main(PROFILE)
