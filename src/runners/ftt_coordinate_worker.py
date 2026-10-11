"""Opt-in right-coordinate profile using the existing conditional trainer."""

import json
from src.io.neural_wave_campaign import ROOT, digest
from src.io.ftt_coordinate_campaign import DESIGN, routes
from src.runners.ftt_core_worker import CoreWorkerProfile, main
from src.runners.ftt_width_worker import CHAIN as WIDTH_CHAIN, model_factory
from src.runners.ftt_bloch_worker import point_field, training_options as scalar_options
from src.postprocessing.ftt_common_wall import compare_common_wall
from src.solvers.neural_wave_greedy import atomic_json, atomic_npz

ART = ROOT / "benchmarks/artifacts/task42extra/v45"
CHAIN = WIDTH_CHAIN + ("src/io/ftt_coordinate_campaign.py", "src/runners/ftt_coordinate_worker.py",
    "src/solvers/ftt_feature_coordinates.py", "src/solvers/ftt_coordinate_qualification.py")


def qualification(action, packet, design, marker, deadline):
    from src.solvers.ftt_coordinate_qualification import qualify_coordinates
    return qualify_coordinates(action, packet, design, marker, deadline)


def training_options(manifest, artifact, marker, directory, design):
    from src.solvers.ftt_feature_coordinates import FeatureCoordinateCache
    from src.runners.ftt_continuation_feedback import joint_callback
    options = scalar_options(manifest, artifact, marker, directory, design,
                             design_path=DESIGN, scoring_root=ART, reuse_saved_feedback=True)
    learned = manifest["spec"]["role"] == "W32_R12_FEATURE_SCALED_LEARNED"
    identity = manifest["spec"]["role"] == "W32_R12_IDENTITY_FROZEN"
    qualified = json.loads((ART / "v45_feature_coordinates_checks/result.json").read_text())
    cache = FeatureCoordinateCache(qualified["selected_tau"], identity=identity)
    folder = artifact / "feature_coordinates"
    folder.mkdir(parents=True, exist_ok=True)

    def factory(model, mapping, op):
        coordinates = cache.get(model, mapping, op.axis, op.shape)
        path = folder / (coordinates.sha256 + ".npz")
        if not path.exists():
            atomic_npz(path, P=coordinates.matrix, inverse_P=coordinates.inverse_matrix,
                       Vh=coordinates.vh, gains=coordinates.gains)
        receipt = dict(coordinates.record, path=str(path.relative_to(ROOT)), artifact_sha256=digest(path))
        atomic_json(folder / (coordinates.sha256 + ".json"), receipt)
        return coordinates, receipt

    options.update(parent_checkpoint=design["parent_checkpoint"],
        execution_policy=design["execution_policies"]["learned" if learned else "freeze"],
        coordinate_transform_factory=factory,
        joint_validation_callback=joint_callback(manifest, artifact, directory, marker, ART, design_path=DESIGN))
    return options


def comparison_record(manifest, artifact, marker, directory):
    common = compare_common_wall(manifest, artifact, marker, directory)
    results = {role: json.loads((ART/stage/"result.json").read_text()) for stage, role in routes()}
    checked = json.loads((artifact/"saved_checker.json").read_text())["records"]
    learned = "W32_R12_FEATURE_SCALED_LEARNED"
    decision = dict(default_round14_results_preserved=True,
        actual_complete_rounds={role: r["position"]["complete_rounds"] for role, r in results.items()},
        learned_actual_and_producer_joint_pass=all(checked[learned+suffix]["m5_full_discrete_numerical_gate"] for suffix in ("","_PRODUCER")),
        conditional_0p7_numerical_gate=all(checked[learned+suffix]["m5_full_discrete_numerical_gate"] for suffix in ("","_PRODUCER")),
        conditional_0p7_requires_separate_safe_admission_and_10800s_remaining=True,
        same_accuracy_resource_gain_qualified=False, original_route_wall_not_reset=True)
    atomic_json(artifact/"fixed_coordinate_decision.json", decision)
    return dict(common_wall=common, coordinate_decision=decision)


PROFILE = CoreWorkerProfile(design=DESIGN, artifacts=ART, route_pairs=routes,
    checks_stage="v45_feature_coordinates_checks", checks_role="feature_coordinates_checks",
    compare_role="feature_coordinates_compare", worker_module="src.runners.ftt_coordinate_worker",
    qualification=qualification, independent_field=point_field, training_options=training_options,
    route_model_factory=model_factory, reconstruction_model_factory=model_factory,
    learned_roles=("W32_R12_FEATURE_SCALED_LEARNED",), compare_postprocess=comparison_record)

if __name__ == "__main__":
    main(PROFILE)
