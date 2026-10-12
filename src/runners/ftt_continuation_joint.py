"""Isolated complete boundary audit; only booleans and identity return to training."""

import argparse
import json
from src.io.neural_wave_campaign import ROOT, digest
from src.solvers.neural_wave_greedy import atomic_json


def run(request_path, isolated, phase):
    request = json.loads(request_path.read_text())
    isolated.mkdir(parents=True, exist_ok=True)
    receipt = isolated / "joint_request_identity.json"
    if receipt.exists():
        if json.loads(receipt.read_text()) != request:
            raise ValueError("JOINT_SAVED_AUDIT_REQUEST_CHANGED")
    else:
        atomic_json(receipt, request)
    healthy = {
        "reconstruct": "reconstruction.json",
        "compare": "verifier_result.json",
    }.get(phase)
    if healthy is not None and (isolated / healthy).exists():
        return
    from src.io.ftt_continuation_campaign import DESIGN
    if request.get("design_path") == "input/task042extra_feinn_5nm/design_v44.json":
        from src.io.ftt_width_campaign import DESIGN
    elif request.get("design_path") == "input/task042extra_feinn_5nm/design_v45.json":
        from src.io.ftt_coordinate_campaign import DESIGN
    elif request.get("design_path") == "input/task042extra_feinn_5nm/design_v46.json":
        from src.io.ftt_residual_campaign import DESIGN
    elif request.get("design_path") is not None:
        raise ValueError("JOINT_UNREGISTERED_DESIGN_PROFILE")

    if digest(DESIGN) != request["design_sha256"]:
        raise ValueError("JOINT_BOUNDARY_DESIGN_CHANGED")
    design = json.loads(DESIGN.read_text())
    from src.io.ftt_campaign import load_files
    from src.runners.ftt_worker import load_arrays, ftt_abi
    from src.solvers.feinn_native import load_native

    files = load_files(design)
    action = load_native(files["native"])
    packet = load_arrays(files["moments_q30"])
    atomic_json(
        isolated / (phase + "_abi.json"),
        ftt_abi(
            "ml" if phase == "reconstruct" else "fe" if phase == "compare" else "pure"
        ),
    )
    from src.postprocessing.ftt_verification import reconstruct, compare, saved_check

    pairs = [("BOUNDARY", request["route"])]
    if phase == "reconstruct":
        from src.runners.ftt_bloch_worker import field_factory, point_field

        reconstruct(
            design,
            action,
            packet,
            load_arrays(files["moments_q60"]),
            isolated,
            lambda *_: None,
            route_pairs=pairs,
            source_root=ROOT / request["snapshot_root"],
            model_factory=field_factory,
            independent_field=point_field,
            candidate_model_factory=(__import__("src.runners.ftt_residual_worker", fromlist=["model_factory"]).model_factory if design["campaign_version"]==46 else __import__("src.runners.ftt_width_worker", fromlist=["model_factory"]).model_factory if design["campaign_version"] in (44,45) else None),
            checkpoint_field_factory=(__import__("src.runners.ftt_residual_worker",fromlist=["checkpoint_points"]).checkpoint_points if design["campaign_version"]==46 else None),
        )
    elif phase == "compare":
        compare(
            design,
            action,
            packet,
            isolated,
            isolated,
            lambda *_: None,
            route_pairs=pairs,
        )
    elif phase == "check":
        saved = saved_check(isolated, design)
        rows = [
            saved["records"][request["route"] + suffix] for suffix in ("", "_PRODUCER")
        ]
        verdict = {
            key: request[key]
            for key in (
                "source_sha",
                "input_sha256",
                "design_sha256",
                "boundary_sha256",
            )
        }
        verdict.update(
            schema="ftt.joint-boundary.scalar-verdict.v1",
            joint_pass=all(row["m5_full_discrete_numerical_gate"] for row in rows),
            mapping_and_quadrature_pass=all(
                row["model_rebuild_pass"]
                and row["quadrature_pass"]
                and row["MPC_relative"] <= 1e-10
                and row["port_recovery_relative"] <= 1e-10
                for row in rows
            ),
            reference_feedback="booleans_and_identity_only",
            production_initialization_allowed=False,
        )
        atomic_json(ROOT / request["feedback_path"], verdict)
    else:
        raise ValueError("UNKNOWN_JOINT_BOUNDARY_PHASE")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("request")
    parser.add_argument("isolated")
    parser.add_argument("phase", choices=("reconstruct", "compare", "check"))
    args = parser.parse_args()
    run(ROOT / args.request, ROOT / args.isolated, args.phase)
