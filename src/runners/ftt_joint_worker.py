"""Joint-tangent opt-in profile on the original common durable worker."""

import json
from src.io.neural_wave_campaign import ROOT
from src.io.ftt_joint_campaign import DESIGN, ART, routes, joint_policy
from src.runners.ftt_core_worker import CoreWorkerProfile, main
from src.runners.ftt_residual_worker import CHAIN as RESIDUAL_CHAIN

CHAIN = RESIDUAL_CHAIN + (
    "src/solvers/joint_least_squares.py",
    "src/solvers/ftt_joint_tangent.py",
    "src/solvers/ftt_joint_io.py",
    "src/solvers/ftt_joint_training.py",
    "src/solvers/ftt_joint_qualification.py",
    "src/io/ftt_joint_campaign.py",
    "src/runners/ftt_joint_worker.py",
    "src/solvers/damped_gauss_newton.py",
)


def qualification(action, packet, design, marker, deadline):
    from src.runners.ftt_core_worker import install_unlabelled_firewall
    from src.solvers.ftt_joint_qualification import qualify_joint

    checks = install_unlabelled_firewall(design, ART / "v47_joint_tangent_checks")
    result = qualify_joint(
        action, packet, design, marker, deadline, ART / "v47_joint_tangent_checks"
    )
    result["actual_label_open_negatives"] = checks
    return result


def model_factory(design, candidate=None):
    from src.solvers.ftt_residual_io import model_factory as factory

    return factory(design, candidate)


def options(manifest, artifact, marker, directory, design, *, qualification=None):
    from src.runners.ftt_bloch_worker import training_options
    from src.runners.ftt_continuation_feedback import joint_callback

    probe = manifest["spec"]["role"] == "FTT_JOINT_STEP_PROBE"
    if not probe:
        p = json.loads((ROOT / design["probe_result"]).read_text())
        if (
            not p["qualified"]
            or p["parent_checkpoint"] != design["parent_checkpoint"]
            or p["h"] != qualification["h"]
        ):
            raise ValueError("JOINT_SHORT_PROBE_NOT_ADMITTED_FROM_FIXED_PARENT")
    value = training_options(
        manifest,
        artifact,
        marker,
        directory,
        design,
        design_path=DESIGN,
        scoring_root=ART,
        reuse_saved_feedback=True,
    )
    value.update(
        qualification=qualification,
        execution_policy=joint_policy(probe),
        parent_entry=design["parent_checkpoint"],
        joint_validation_callback=joint_callback(
            manifest, artifact, directory, marker, ART, design_path=DESIGN
        ),
    )
    return value


def adapt(action, packet, model, binding, options, design, qualification):
    from src.solvers.ftt_factored_moments import FactoredMomentMap
    from src.solvers.ftt_joint_io import load_joint_parent

    mapping = FactoredMomentMap(packet)
    correction, view, context, parent, pairs = load_joint_parent(
        design, action, mapping, model
    )
    options.update(
        mapping=mapping,
        residual_context=context,
        parent_state=parent,
        parent_pairs=pairs,
    )
    return (
        view,
        correction,
        dict(
            residual_branch=context.binding,
            parent_checkpoint_sha256=design["parent_checkpoint"]["sha256"],
        ),
        options,
    )


def train(*args, **kwargs):
    from src.solvers.ftt_joint_training import run_joint_training

    return run_joint_training(*args, **kwargs)


def checkpoint_points(design, state, candidate, model):
    from src.solvers.ftt_residual_io import checkpoint_points as points

    return points(design, state, candidate, model)


PROFILE = CoreWorkerProfile(
    design=DESIGN,
    artifacts=ART,
    route_pairs=routes,
    checks_stage="v47_joint_tangent_checks",
    checks_role="joint_tangent_checks",
    compare_role="joint_tangent_compare",
    worker_module="src.runners.ftt_joint_worker",
    qualification=qualification,
    route_model_factory=model_factory,
    reconstruction_model_factory=model_factory,
    training_options=options,
    training_adapter=adapt,
    trainer=train,
    checkpoint_field_factory=checkpoint_points,
    learned_roles=("FTT_JOINT_LM_ALL", "FTT_JOINT_STEP_PROBE"),
    pass_qualification_to_training=True,
)

if __name__ == "__main__":
    main(PROFILE)
