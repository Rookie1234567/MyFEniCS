"""Thin Bloch opt-in profile; reuse the conditional trainer and durable chain."""

import shlex

from src.io.neural_wave_campaign import ROOT, digest
from src.io.ftt_bloch_campaign import DESIGN, routes
from src.runners.ftt_core_worker import CoreWorkerProfile, CHAIN as CORE_CHAIN, main
from src.solvers.neural_wave_greedy import atomic_json, atomic_npz

ART = ROOT / "benchmarks/artifacts/task42extra/v42"
CHAIN = CORE_CHAIN + (
    "src/common/ftt_bloch_phase.py", "src/solvers/ftt_bloch_field.py", "src/solvers/ftt_bloch_qualification.py",
    "src/io/ftt_bloch_campaign.py", "src/runners/ftt_bloch_worker.py",
    "src/postprocessing/ftt_bloch_scalars.py", "src/postprocessing/ftt_verification.py",
    "src/runners/saved_field_supervision.py",
)


def field_factory(design, kind):
    from src.solvers.ftt_bloch_field import make_bloch_field
    return make_bloch_field(design, kind)


def point_field(model):
    from src.solvers.ftt_bloch_field import IndependentPointPhase
    return IndependentPointPhase(model)


def qualification(action, packet, design, marker, deadline):
    from src.solvers.ftt_bloch_qualification import actual_bloch_checks
    return actual_bloch_checks(action, packet, design, marker, deadline)


def training_options(manifest, artifact, marker, directory, design):
    """Only strict scalar JSON crosses the separate reference-scoring boundary."""
    from src.runners.saved_field_supervision import run_checker
    from src.postprocessing.ftt_bloch_scalars import read_scalars

    def validate(number, checkpoint, c, r):
        key = f"{manifest['spec']['stage']}_round{number}_{checkpoint['generation']}"
        request_dir = directory / key
        request_dir.mkdir(parents=True, exist_ok=False)
        field = artifact / (key + "_unlabelled_field.npz")
        atomic_npz(field, c=c, r=r)
        request = dict(round=number, field_path=str(field.relative_to(ROOT)), field_sha256=digest(field),
            boundary_sha256=checkpoint["sha256"], source_sha=manifest["source_sha"],
            design_sha256=manifest["design_sha256"], production_initialization_allowed=False)
        atomic_json(request_dir / "request.json", request)
        # Scoring arrays stay outside the training artifact and are denied by
        # the installed training firewall. Only this fixed-shape JSON is read.
        isolated = ART / "isolated_reference_scoring" / key
        command = ["bash", "-lc", "source scripts/activate_task42extra.sh fe && exec python -m src.postprocessing.ftt_bloch_scalars "
                   + shlex.quote(str((request_dir / "request.json").relative_to(ROOT))) + " "
                   + shlex.quote(str(isolated.relative_to(ROOT))) + " "
                   + shlex.quote(str((request_dir / "scalars.json").relative_to(ROOT)))]
        summary = run_checker(command, request_dir / "supervision", manifest["worker_stop_monotonic"], manifest["source_sha"])
        scalar = read_scalars(request_dir / "scalars.json", request)
        scalar["checker_peak_bytes"] = summary["sampled_process_tree_rss_peak_bytes"]
        marker("isolated_reference_scalar_feedback", scalar)
        return scalar

    return dict(validation_callback=validate)


PROFILE = CoreWorkerProfile(design=DESIGN, artifacts=ART, route_pairs=routes,
    checks_stage="v42_bloch_ftt_checks", checks_role="bloch_ftt_checks",
    compare_role="bloch_ftt_compare", learned_role="BLOCH_FTTNN_CORE_LEARNED",
    worker_module="src.runners.ftt_bloch_worker", model_factory=field_factory,
    qualification=qualification, independent_field=point_field, training_options=training_options)


if __name__ == "__main__":
    main(PROFILE)
