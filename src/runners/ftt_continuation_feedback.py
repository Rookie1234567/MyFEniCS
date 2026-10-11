"""Bounded joint-audit wiring, never reference vectors in the trainer."""

import json
import shlex
from src.io.neural_wave_campaign import ROOT, digest
from src.solvers.neural_wave_greedy import atomic_json, atomic_npz


VERDICT_FIELDS = {
    "schema",
    "source_sha",
    "input_sha256",
    "design_sha256",
    "boundary_sha256",
    "joint_pass",
    "mapping_and_quadrature_pass",
    "reference_feedback",
    "production_initialization_allowed",
}


def read_verdict(path, request):
    value = json.loads(path.read_text())
    if (
        set(value) != VERDICT_FIELDS
        or value["schema"] != "ftt.joint-boundary.scalar-verdict.v1"
    ):
        raise ValueError("JOINT_NONSCALAR_OR_UNREGISTERED_FEEDBACK")
    for key in ("source_sha", "input_sha256", "design_sha256", "boundary_sha256"):
        if value[key] != request[key]:
            raise ValueError("JOINT_VERDICT_IDENTITY_MISMATCH:" + key)
    if (
        value["reference_feedback"] != "booleans_and_identity_only"
        or value["production_initialization_allowed"]
        or type(value["joint_pass"]) is not bool
        or type(value["mapping_and_quadrature_pass"]) is not bool
    ):
        raise ValueError("JOINT_VERDICT_FLAGS_INVALID")
    return value


def joint_callback(manifest, artifact, directory, marker, scoring_root):
    from src.runners.saved_field_supervision import run_checker
    from src.solvers.optimization_checkpoint import atomic_write

    def verify(checkpoint, c, r):
        key = f"{manifest['spec']['stage']}_joint_{checkpoint['generation']}"
        snapshot = artifact / key
        source = snapshot / "source" / "BOUNDARY"
        source.mkdir(parents=True, exist_ok=True)
        pt = artifact / "checkpoints" / checkpoint["name"]
        if digest(pt) != checkpoint["sha256"]:
            raise ValueError("JOINT_COMMITTED_CHECKPOINT_CHANGED")
        target = source / "checkpoints" / checkpoint["name"]
        if not target.exists():
            atomic_write(target, lambda f: f.write(pt.read_bytes()))
        candidate = dict(
            checkpoint["metadata"],
            checkpoint=checkpoint,
            status="COMMITTED_BOUNDARY_DIAGNOSTIC",
        )
        atomic_json(source / "result.json", candidate)
        atomic_npz(source / "frozen_field.npz", c=c, r=r)
        feedback = snapshot / "scalar_verdict.json"
        request = {
            k: manifest[k] for k in ("source_sha", "input_sha256", "design_sha256")
        }
        request.update(
            boundary_sha256=checkpoint["sha256"],
            route=manifest["spec"]["role"],
            snapshot_root=str((snapshot / "source").relative_to(ROOT)),
            feedback_path=str(feedback.relative_to(ROOT)),
        )
        request_path = snapshot / "request.json"
        atomic_json(request_path, request)
        if feedback.exists():
            return read_verdict(feedback, request)
        isolated = scoring_root / "isolated_joint_verification" / key
        for phase, mode in (
            ("reconstruct", "ml"),
            ("compare", "fe"),
            ("check", "pure"),
        ):
            # Reuse completed upstream audit phases after a pure writer/checker failure.
            # Only separate-process booleans are reopened in this training process.
            command = [
                "bash",
                "-lc",
                "source scripts/activate_task42extra.sh "
                + mode
                + " && exec python -m src.runners.ftt_continuation_joint "
                + " ".join(
                    shlex.quote(x)
                    for x in (
                        str(request_path.relative_to(ROOT)),
                        str(isolated.relative_to(ROOT)),
                        phase,
                    )
                ),
            ]
            run_checker(
                command,
                snapshot / (phase + "_supervision_" + directory.name),
                manifest["worker_stop_monotonic"],
                manifest["source_sha"],
            )
        value = read_verdict(feedback, request)
        marker("joint_boundary_scalar_verdict", value)
        return value

    return verify
