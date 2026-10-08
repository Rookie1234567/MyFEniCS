"""V32 thin opt-in wiring: separate unlabelled producer and reference scoring."""

import json
import sys

import numpy as np

from src.io.neural_wave_campaign import ROOT, profile_paths, digest, load_training_files
from src.solvers.neural_wave_greedy import atomic_json, run_greedy

CHAIN = (
    "src/solvers/neural_wave_moments.py",
    "src/solvers/neural_wave_greedy.py",
    "src/solvers/neural_wave_block.py",
    "src/solvers/neural_wave_block_reconstruction.py",
    "src/solvers/neural_wave_reconstruction.py",
    "src/solvers/neural_wave_multiscale.py",
    "src/solvers/neural_wave_local_action.py",
    "src/solvers/neural_wave_projection.py",
    "src/solvers/neural_wave_multiscale_validation.py",
    "src/solvers/neural_wave_multiscale_qualification.py",
    "src/solvers/neural_wave_qr_refresh.py",
    "src/runners/multiscale_wave_worker.py",
)
ROUTES = [
    ("v32_fixed_multiscale_wave", "FIXED_MULTISCALE_WAVE_BLOCK"),
    ("v32_learned_multiscale_wave", "LEARNED_MULTISCALE_WAVE_BLOCK"),
]


def early_validate(action, packet, design, artifact, spec, root, marker, source):
    from src.solvers.neural_wave_block_reconstruction import rebuild_stable
    from src.solvers.feinn_fem import build_model
    from src.postprocessing.neural_wave_audit import (
        save_complete_field_samples,
        relative_error,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )

    route = "learned" if "learned" in spec["stage"] else "fixed"
    node = int(spec["stage"][-1])
    directory = root / f"v32_{route}_multiscale_wave"
    if not (directory / f"validation_requested_{node}.json").exists():
        raise ValueError("NO_FROZEN_VALIDATION_REQUEST")
    boundary = directory / "basis/committed.json"
    boundary_hash = digest(boundary)
    c, producer, _ = rebuild_stable(directory / "basis", packet, marker)
    index = json.loads(
        (ROOT / "benchmarks/artifacts/task42extra/index_e3_reference.json").read_text()
    )
    entry = index["files"]["reference"]
    if digest(entry["path"]) != entry["sha256"]:
        raise ValueError("SAME_P3_REFERENCE_HASH_FAILED")
    with np.load(entry["path"], allow_pickle=False) as z:
        ref = np.array(z["c"])
    model = build_model(design["model"], marker=marker)
    try:
        for key, value in design["native_identity"].items():
            if model["record"][key] != value:
                raise ValueError("INDEPENDENT_PHYSICAL_IDENTITY_CHANGED")
        raw, _ = save_complete_field_samples(
            model, action, packet, ref, {"CANDIDATE": c}, artifact, marker
        )
        with np.load(raw, allow_pickle=False) as z:
            w = z["weights"]
            errors = {
                k: relative_error(
                    z["CANDIDATE_" + k] - z["REFERENCE_" + k],
                    z["REFERENCE_" + k],
                    weights=w,
                )
                for k in ("E", "curl")
            }
        audit = action.audit(c)
        ineffective = max(
            audit["native_relative"], audit["augmented_relative"]
        ) > 1e-2 and all(errors[k]["relative"] > 0.5 for k in errors)
        result = dict(
            node=node,
            boundary_sha256=boundary_hash,
            audit=audit,
            scattered_errors=errors,
            reference_sha256=entry["sha256"],
            model_reconstruction_relative=float(
                np.linalg.norm(c - producer) / max(np.linalg.norm(c), 1e-30)
            ),
            raw_samples=dict(path=str(raw.relative_to(ROOT)), sha256=digest(raw)),
            ineffective=ineffective,
            continuation_allowed=not ineffective or node == 1,
            reference_feedback="scalars only",
            reference_solve_count=0,
            source_sha=source,
        )
        atomic_json(artifact / "scoring_record.json", result)
        scalar = dict(
            schema="multiscale.validation.scalars.v1",
            node=node,
            boundary_sha256=boundary_hash,
            native_relative=audit["native_relative"],
            augmented_relative=audit["augmented_relative"],
            scattered_E_relative=errors["E"]["relative"],
            scattered_curl_relative=errors["curl"]["relative"],
            source_sha=source,
            scoring_result_sha256=digest(artifact / "scoring_record.json"),
            **{"continue": result["continuation_allowed"]},
        )
        atomic_json(directory / f"validation_scalars_{node}.json", scalar)
        return result
    finally:
        destroy_same_mesh_physical_action(model["bundle"])


def run_stage(manifest, artifact, marker):
    spec = manifest["spec"]
    profile = profile_paths(spec)
    if digest(profile["design"]) != manifest["design_sha256"]:
        raise ValueError("FROZEN_V32_DESIGN_CHANGED")
    design = json.loads(profile["design"].read_text())
    training = spec["role"] in [v[1] for v in ROUTES]
    if training:
        from src.io.neural_wave_campaign import training_open_allowed

        design["active_training_artifact"] = str(artifact)

        def firewall(event, args):
            if event == "open" and not training_open_allowed(args[0], design):
                raise PermissionError(
                    "UNLABELLED_TRAINING_ACCESS_REJECTED: " + str(args[0])
                )

        sys.addaudithook(firewall)
        marker(
            "unlabelled_training_firewall",
            dict(reference_vectors_allowed=False, validation_scalars_allowed=True),
        )
    files = load_training_files(design)
    from src.solvers.feinn_native import load_native

    action = load_native(files["native"])
    with np.load(files["moments_q30"], allow_pickle=False) as z:
        packet = {k: np.array(z[k]) for k in z.files}
    if (action.size, action.nc, action.np) != (31968, 384, 40) or not np.array_equal(
        packet["master_native_rows"], action.a["masters"]
    ):
        raise ValueError("ORIGINAL_COMPLETE_M5_IDENTITY_FAILED")
    role = spec["role"]
    if role == "support_audit":
        from src.postprocessing.neural_wave_support_audit import audit_support

        return audit_support(action, packet, design, artifact, marker)
    if role == "support_bound":
        from src.postprocessing.neural_wave_support_audit import (
            reference_zero_cell_bound,
        )

        old = json.loads(
            (profile["artifacts"] / "v32_saved_support_audit/result.json").read_text()
        )
        return reference_zero_cell_bound(old, design)
    if role == "support_witness":
        from src.postprocessing.neural_wave_support_audit import direction_witness

        return direction_witness(action, packet, design, artifact, marker)
    if role in ("multiscale_checks", "readout_repair_checks"):
        from src.solvers.neural_wave_multiscale_qualification import qualify

        result = qualify(action, packet, design, artifact, marker)
        if role == "readout_repair_checks":
            from src.solvers.neural_wave_qr_refresh import repair_saved_readout

            route = "learned" if "learned" in spec["stage"] else "fixed"
            result["saved_readout_refresh"] = repair_saved_readout(
                action, packet, design,
                profile["artifacts"] / f"v32_{route}_multiscale_wave/basis",
                artifact, manifest["source_sha"], manifest["design_sha256"],
                manifest["worker_stop_monotonic"], marker,
            )
        result["bound_numerical_chain_sha256"] = {p: digest(ROOT / p) for p in CHAIN}
        return result
    if role == "early_validate":
        return early_validate(
            action,
            packet,
            design,
            artifact,
            spec,
            profile["artifacts"],
            marker,
            manifest["source_sha"],
        )
    if role == "multiscale_reconstruct":
        from src.runners.neural_wave_worker import verify

        return verify(
            design,
            action,
            packet,
            artifact,
            marker,
            stable_rebuild=True,
            include_producer=True,
            route_root=profile["artifacts"],
            routes=ROUTES,
        )
    if role == "multiscale_compare":
        from src.runners.block_wave_worker import saved_checker

        return saved_checker(
            action,
            profile["artifacts"] / "v32_multiscale_reconstruct/result.json",
            design,
            marker,
        )
    if training:
        expected_chain = {p: digest(ROOT / p) for p in CHAIN}
        checkfile = None
        for stage in ("v32_learned_original_qr_checks", "v32_fixed_original_qr_checks",
                      "v32_multiscale_wave_checks"):
            file = profile["artifacts"] / stage / "result.json"
            if file.exists():
                receipt = json.loads(file.read_text())
                if receipt.get("implementation_qualified") and receipt.get(
                    "bound_numerical_chain_sha256"
                ) == expected_chain:
                    checkfile = file
                    break
        if checkfile is None:
            raise ValueError("MULTISCALE_IMPLEMENTATION_NOT_QUALIFIED")
        # Only a filtered numerical qualification receipt, never a field label.
        # The path is explicitly whitelisted for unlabelled training.
        check = json.loads(checkfile.read_text())
        if not check["implementation_qualified"] or check[
            "bound_numerical_chain_sha256"
        ] != {p: digest(ROOT / p) for p in CHAIN}:
            raise ValueError("MULTISCALE_IMPLEMENTATION_NOT_QUALIFIED")
        design["strategy"]["native_target"] = spec["native_target"]
        binding = dict(
            route=role,
            source_sha=manifest["source_sha"],
            design_sha256=manifest["design_sha256"],
            native_sha256=design["files"]["native"]["sha256"],
            moments_sha256=design["files"]["moments_q30"]["sha256"],
            route_origin_monotonic=manifest["route_origin_monotonic"],
            exact_local_input_support_reuse=True,
            exact_two_pass_projection_reuse=True,
            block_qualification_sha256=digest(checkfile),
        )
        return run_greedy(
            action,
            packet,
            design,
            artifact,
            binding,
            manifest["worker_stop_monotonic"],
            marker,
        )
    raise ValueError("UNIMPLEMENTED_V32_ROLE")
