"""Residual-branch profile: reuse the existing trainer, supervision and FE audits."""

import json
from src.io.neural_wave_campaign import ROOT
from src.io.ftt_residual_campaign import DESIGN, routes
from src.runners.ftt_core_worker import CoreWorkerProfile, main
from src.runners.ftt_width_worker import CHAIN as WIDTH_CHAIN
from src.runners.ftt_bloch_worker import training_options as scalar_options
from src.solvers.neural_wave_greedy import atomic_json

ART = ROOT / "benchmarks/artifacts/task42extra/v46"
CHAIN = WIDTH_CHAIN + (
    "src/io/ftt_residual_campaign.py",
    "src/runners/ftt_residual_worker.py",
    "src/solvers/ftt_residual_branch.py",
    "src/solvers/ftt_residual_io.py",
    "src/solvers/ftt_residual_qualification.py",
)


def qualification(action, packet, design, marker, deadline):
    from src.solvers.ftt_residual_qualification import qualify_residual

    return qualify_residual(
        action, packet, design, marker, deadline, ART / "v46_residual_branch_checks"
    )


def prepare(action, packet, design, marker, directory, artifact, qualified):
    from src.solvers.ftt_residual_io import preparation

    return preparation(artifact, design, qualified)


def options(manifest, artifact, marker, directory, design, *, qualification=None):
    from src.runners.ftt_continuation_feedback import joint_callback
    from src.solvers.ftt_residual_branch import residual_policy

    value = scalar_options(
        manifest,
        artifact,
        marker,
        directory,
        design,
        design_path=DESIGN,
        scoring_root=ART,
        reuse_saved_feedback=True,
    )
    learned = manifest["spec"]["role"] == "RESIDUAL_FTT_R8_LEARNED"
    value.update(
        execution_policy=residual_policy(learned),
        joint_validation_callback=joint_callback(
            manifest, artifact, directory, marker, ART, design_path=DESIGN
        ),
    )
    return value


def adapt(action, packet, model, binding, options, design, qualification):
    from src.solvers.ftt_residual_io import prepared_context

    correction, view, context = prepared_context(design, action, qualification)
    for name in ("validation_callback", "joint_validation_callback"):
        original = options[name]
        if name == "validation_callback":

            def validate(number, checkpoint, c, r, callback=original):
                fields = view.fields(c, r)
                return callback(
                    number, checkpoint, fields["c_combined"], fields["r_original"]
                )

            options[name] = validate
        else:

            def verify(checkpoint, c, r, callback=original):
                fields = view.fields(c, r)
                return callback(checkpoint, fields["c_combined"], fields["r_original"])

            options[name] = verify
    options["residual_context"] = context
    return view, correction, dict(residual_branch=context.binding), options


def compare_record(manifest, artifact, marker, directory):
    checked = json.loads((artifact / "saved_checker.json").read_text())["records"]
    learned = "RESIDUAL_FTT_R8_LEARNED"
    decision = dict(
        learned_actual_and_producer_joint_pass=all(
            checked[learned + s]["m5_full_discrete_numerical_gate"]
            for s in ("", "_PRODUCER")
        ),
        control_verified="RESIDUAL_FTT_R8_FROZEN" in checked,
        conditional_0p7_requires_safe_resource_and_10800s_remaining=True,
        same_accuracy_NN_resource_gain_qualified=False,
        additional_correction_branch_authorized=False,
    )
    atomic_json(artifact / "residual_branch_decision.json", decision)
    return decision


def model_factory(design, candidate=None):
    from src.solvers.ftt_residual_io import model_factory as create

    return create(design, candidate)


def checkpoint_points(design, state, candidate, model):
    from src.solvers.ftt_residual_io import checkpoint_points as points

    return points(design, state, candidate, model)


PROFILE = CoreWorkerProfile(
    design=DESIGN,
    artifacts=ART,
    route_pairs=routes,
    checks_stage="v46_residual_branch_checks",
    checks_role="residual_branch_checks",
    compare_role="residual_branch_compare",
    prepare_role="residual_branch_prepare",
    prepare_stage="v46_residual_branch_prepare",
    preparation=prepare,
    worker_module="src.runners.ftt_residual_worker",
    qualification=qualification,
    route_model_factory=model_factory,
    reconstruction_model_factory=model_factory,
    training_options=options,
    training_adapter=adapt,
    checkpoint_field_factory=checkpoint_points,
    learned_roles=("RESIDUAL_FTT_R8_LEARNED",),
    pass_qualification_to_training=True,
    compare_postprocess=compare_record,
)

if __name__ == "__main__":
    main(PROFILE)
