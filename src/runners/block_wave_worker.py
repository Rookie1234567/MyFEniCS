"""Opt-in V31 wiring; numerical work remains in reusable solver modules."""

import json
import sys

import numpy as np

from src.io.neural_wave_campaign import (
    ROOT,
    DESIGN as OLD_DESIGN,
    digest,
    load_training_files,
    profile_paths,
)


def saved_checker(action, frozen_file, design, marker):
    from src.postprocessing.neural_wave_audit import check_saved_arrays

    frozen = json.loads(frozen_file.read_text())
    raw = ROOT / frozen["raw_complete_fields"]["path"]
    if digest(raw) != frozen["raw_complete_fields"]["sha256"]:
        raise ValueError("FROZEN_COMPLETE_FIELD_ARRAY_HASH_FAILED")
    with np.load(raw, allow_pickle=False) as arrays:
        samples = {k: np.array(arrays[k]) for k in arrays.files}
    names = tuple(frozen["reconstruction"])
    result = check_saved_arrays(
        action,
        frozen["physics"],
        samples,
        frozen["reconstruction"],
        frozen["independent_MPC_recovery_checks"],
        dict(
            model=design["model"],
            mode_manifest_sha256=design["native_identity"]["mode_manifest_sha256"],
        ),
        names=names,
    )
    result.update(
        bound_verifier_result_sha256=digest(frozen_file),
        bound_verifier_result_path=str(frozen_file.relative_to(ROOT)),
        bound_complete_field_samples_sha256=digest(raw),
    )
    marker("independent_saved_array_gates", result)
    return result


def run_stage(manifest, artifact, marker):
    spec = manifest["spec"]
    profile = profile_paths(spec)
    if digest(profile["design"]) != manifest["design_sha256"]:
        raise ValueError("FROZEN_V31_DESIGN_CHANGED")
    design = json.loads(profile["design"].read_text())
    training = spec["role"] in ("FIXED_WAVE_BLOCK_GREEDY", "LEARNED_WAVE_BLOCK_GREEDY")
    if training:
        design["active_training_artifact"] = str(artifact)
        from src.io.neural_wave_campaign import training_open_allowed

        def firewall(event, arguments):
            if event == "open" and not training_open_allowed(arguments[0], design):
                raise PermissionError(
                    "UNLABELLED_TRAINING_FILE_ACCESS_REJECTED: " + str(arguments[0])
                )

        sys.addaudithook(firewall)
        marker(
            "training_label_firewall_installed",
            dict(
                reference_access_allowed=False,
                legacy_weights_allowed=False,
                Gram_packet_access_allowed=False,
            ),
        )
    files = load_training_files(design)
    from src.solvers.feinn_native import load_native

    action = load_native(files["native"])
    with np.load(files["moments_q30"], allow_pickle=False) as arrays:
        packet = {key: np.array(arrays[key]) for key in arrays.files}
    if action.size != 31968 or action.nc != 384 or action.np != 40:
        raise ValueError("ORIGINAL_M5_FULL_FE_IDENTITY_FAILED")
    if not np.array_equal(packet["master_native_rows"], action.a["masters"]):
        raise ValueError("COMPLETE_MOMENT_MASTER_ORDER_MISMATCH")
    if spec["role"] == "saved_field_audit":
        from src.runners.neural_wave_worker import verify

        result = verify(
            json.loads(OLD_DESIGN.read_text()),
            action,
            packet,
            artifact,
            marker,
            reuse_completed=True,
            include_producer=True,
        )
    elif spec["role"] in ("saved_field_check", "block_compare"):
        paired = (
            "v31_saved_field_audit"
            if spec["role"] == "saved_field_check"
            else "v31_block_reconstruct"
        )
        result = saved_checker(
            action, profile["artifacts"] / paired / "result.json", design, marker
        )
    elif spec["role"] == "block_checks":
        from src.solvers.neural_wave_block_qualification import CHAIN, qualify
        from src.io.neural_wave_campaign import ARTIFACTS as old_artifacts

        with np.load(
            old_artifacts / "v30_wave_checks/moments_q60.npz", allow_pickle=False
        ) as arrays:
            high = {k: np.array(arrays[k]) for k in arrays.files}
        result = qualify(
            action,
            packet,
            high,
            design,
            artifact,
            marker,
            dict(
                route="BLOCK_QUALIFICATION",
                source_sha=manifest["source_sha"],
                native_sha256=design["files"]["native"]["sha256"],
                moments_sha256=design["files"]["moments_q30"]["sha256"],
                design_sha256=manifest["design_sha256"],
            ),
        )
        result["bound_numerical_chain_sha256"] = {p: digest(ROOT / p) for p in CHAIN}
    elif spec["role"] == "reconstruction_stability":
        from src.solvers.neural_wave_block_reconstruction import (
            reconstruction_stability,
        )
        from src.io.neural_wave_campaign import ARTIFACTS as old_artifacts

        result = reconstruction_stability(
            action, packet, artifact, marker, old_artifacts
        )
    elif spec["role"] == "roundoff_witness":
        from src.postprocessing.neural_wave_roundoff import selected_entry_witness
        from src.io.neural_wave_campaign import ARTIFACTS as old_artifacts

        frozen = json.loads(
            (
                profile["artifacts"] / "v31_reconstruction_stability/result.json"
            ).read_text()
        )
        result = selected_entry_witness(packet, frozen, old_artifacts)
    elif spec["role"] == "block_reconstruct":
        from src.runners.neural_wave_worker import verify

        result = verify(
            design,
            action,
            packet,
            artifact,
            marker,
            stable_rebuild=True,
            include_producer=True,
            route_root=profile["artifacts"],
            routes=[
                ("v31_fixed_block_wave", "FIXED_WAVE_BLOCK_GREEDY"),
                ("v31_learned_block_wave", "LEARNED_WAVE_BLOCK_GREEDY"),
            ],
        )
    elif training:
        from src.solvers.neural_wave_block_qualification import CHAIN
        from src.solvers.neural_wave_greedy import run_greedy

        frozen_file = profile["artifacts"] / "v31_block_wave_checks/result.json"
        frozen = json.loads(frozen_file.read_text())
        if not frozen["implementation_qualified"] or frozen[
            "bound_numerical_chain_sha256"
        ] != {p: digest(ROOT / p) for p in CHAIN}:
            raise ValueError("BLOCK_REAL_IMPLEMENTATION_NOT_QUALIFIED")
        if any(
            frozen["actual_" + name + "_sha256"] != design["files"][key]["sha256"]
            for name, key in (("native", "native"), ("moments", "moments_q30"))
        ):
            raise ValueError("BLOCK_ORIGINAL_DATA_IDENTITY_CHANGED")
        design["strategy"]["native_target"] = spec["native_target"]
        binding = dict(
            route=spec["role"],
            source_sha=manifest["source_sha"],
            design_sha256=manifest["design_sha256"],
            native_sha256=design["files"]["native"]["sha256"],
            moments_sha256=design["files"]["moments_q30"]["sha256"],
            route_origin_monotonic=manifest["route_origin_monotonic"],
            exact_local_input_support_reuse=True,
            exact_two_pass_projection_reuse=True,
            block_qualification_sha256=digest(frozen_file),
        )
        result = run_greedy(
            action,
            packet,
            design,
            artifact,
            binding,
            manifest["worker_stop_monotonic"],
            marker,
        )
    else:
        raise ValueError("V31_STAGE_NOT_YET_QUALIFIED_OR_IMPLEMENTED: " + spec["role"])
    result.update(
        actual_native_sha256=design["files"]["native"]["sha256"],
        actual_moments_sha256=design["files"]["moments_q30"]["sha256"],
    )
    return result
