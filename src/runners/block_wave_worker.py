"""Opt-in V31 wiring; numerical work remains in reusable solver modules."""
import json
import sys

import numpy as np

from src.io.neural_wave_campaign import ROOT, DESIGN as OLD_DESIGN, digest, load_training_files, profile_paths


def saved_checker(action, frozen_file, design, marker):
    from src.postprocessing.neural_wave_audit import check_saved_arrays
    frozen = json.loads(frozen_file.read_text())
    raw = ROOT / frozen["raw_complete_fields"]["path"]
    if digest(raw) != frozen["raw_complete_fields"]["sha256"]:
        raise ValueError("FROZEN_COMPLETE_FIELD_ARRAY_HASH_FAILED")
    with np.load(raw, allow_pickle=False) as arrays:
        samples = {k: np.array(arrays[k]) for k in arrays.files}
    names = tuple(frozen["reconstruction"])
    result = check_saved_arrays(action, frozen["physics"], samples,
        frozen["reconstruction"], frozen["independent_MPC_recovery_checks"],
        dict(model=design["model"],mode_manifest_sha256=design["native_identity"]["mode_manifest_sha256"]),
        names=names)
    result.update(bound_verifier_result_sha256=digest(frozen_file),
        bound_verifier_result_path=str(frozen_file.relative_to(ROOT)),
        bound_complete_field_samples_sha256=digest(raw))
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
        from src.io.neural_wave_campaign import training_open_allowed
        def firewall(event, arguments):
            if event == "open" and not training_open_allowed(arguments[0], design):
                raise PermissionError("UNLABELLED_TRAINING_FILE_ACCESS_REJECTED: " + str(arguments[0]))
        sys.addaudithook(firewall)
        marker("training_label_firewall_installed",dict(reference_access_allowed=False,
            legacy_weights_allowed=False,Gram_packet_access_allowed=False))
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
        result = verify(json.loads(OLD_DESIGN.read_text()), action, packet, artifact, marker,
            reuse_completed=True,include_producer=True)
    elif spec["role"] in ("saved_field_check", "block_compare"):
        paired = "v31_saved_field_audit" if spec["role"] == "saved_field_check" else "v31_block_reconstruct"
        result = saved_checker(action, profile["artifacts"]/paired/"result.json",design,marker)
    else:
        raise ValueError("V31_STAGE_NOT_YET_QUALIFIED_OR_IMPLEMENTED: " + spec["role"])
    result.update(actual_native_sha256=design["files"]["native"]["sha256"],
        actual_moments_sha256=design["files"]["moments_q30"]["sha256"])
    return result
