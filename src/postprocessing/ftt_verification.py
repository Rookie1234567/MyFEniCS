"""FTT model reconstruction and original saved-field physics, separate roles."""

import json
from pathlib import Path
import numpy as np
from src.io.neural_wave_campaign import ROOT, digest
from src.solvers.neural_wave_greedy import atomic_json, atomic_npz

ART = ROOT / "benchmarks/artifacts/task42extra/v38"


def route_stages(fit=False):
    return [
        (
            "v38_fttnn_reference_fit" if fit else "v38_fttnn_native",
            "FTTNN_R8_FIT_G" if fit else "FTTNN_R8_NATIVE_EUC",
        ),
        (
            "v38_chebtt_reference_fit" if fit else "v38_chebtt_native",
            "CHEB_TT_R8_FIT_G" if fit else "CHEB_TT_R8_NATIVE_EUC",
        ),
    ]


def reconstruct(design, action, packet, high, artifact, marker, fit=False):
    from src.solvers.ftt_field import FTTField
    from src.solvers.ftt_moments import StreamingMomentMap
    from src.solvers.optimization_checkpoint import load_checkpoint

    result = {}
    for stage, name in route_stages(fit):
        candidate = json.loads((ART / stage / "result.json").read_text())
        entry = candidate["checkpoint"]
        model = FTTField(
            design["model"]["geometry"]["bounds_nm"], candidate["model_kind"]
        )
        state = load_checkpoint(
            ART / stage / "checkpoints" / entry["name"], entry["sha256"]
        )
        if state["metadata"]["reference_used_for_training"] != fit or state["metadata"][
            "metric_kind"
        ] != ("reference_fit_G" if fit else "native_euc"):
            raise ValueError("FTT_CHECKPOINT_LABEL_SCOPE_MISMATCH")
        model.load_state_dict(state["model"], strict=True)
        c30 = StreamingMomentMap(packet).forward(model)
        c60 = StreamingMomentMap(high).forward(model)
        saved = np.asarray(state["c"], dtype=np.complex128)
        same = float(np.linalg.norm(c30 - saved) / max(np.linalg.norm(saved), 1e-30))
        drift = float(np.linalg.norm(c60 - c30) / max(np.linalg.norm(c30), 1e-30))
        adrift = float(np.linalg.norm(action.apply(c60 - c30)) / action.bnorm)
        record = dict(
            complete_model_mapping_relative=same,
            coefficient_q30_q60_relative=drift,
            original_action_q30_q60_load_relative=adrift,
            model_reconstruction_pass=bool(same <= 1e-10),
            quadrature_pass=bool(max(drift, adrift) <= 1e-8),
            candidate_source_sha=candidate["source_sha"],
            committed_boundary_sha256=entry["sha256"],
            reference_used_for_training=fit,
            pde_only_solve=not fit,
            production_initialization_allowed=False,
        )
        atomic_npz(artifact / (name + ".npz"), c30=c30, c60=c60, saved=saved)
        result[name] = record
        marker("independent_ftt_model_rebuilt", dict(name=name, **record))
    atomic_json(artifact / "reconstruction.json", result)
    return result


def compare(design, action, packet, rebuild_dir, artifact, marker, fit=False):
    from src.solvers.feinn_fem import build_model
    from src.solvers.feinn_reference import field_physics, _region_field_errors
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )
    from src.postprocessing.neural_wave_audit import save_complete_field_samples

    reconstruction = json.loads((rebuild_dir / "reconstruction.json").read_text())
    states = {}
    for _, name in route_stages(fit):
        with np.load(rebuild_dir / (name + ".npz"), allow_pickle=False) as data:
            states[name] = np.array(data["c30"])
            states[name + "_PRODUCER"] = np.array(data["saved"])
        reconstruction[name + "_PRODUCER"] = dict(reconstruction[name])
    entry = design["reference"]
    path = ROOT / entry["path"]
    if digest(path) != entry["sha256"]:
        raise ValueError("FTT_SAME_P3_REFERENCE_HASH_CHANGED")
    with np.load(path, allow_pickle=False) as data:
        reference = np.array(data["c"])
        alpha = np.array(data["alpha"])
    if np.linalg.norm(action.alpha(reference) - alpha) / np.linalg.norm(alpha) > 1e-10:
        raise ValueError("FTT_REFERENCE_PORT_IDENTITY")
    model = build_model(design["model"], marker=marker)
    try:
        for key, value in design["native_identity"].items():
            if model["record"][key] != value:
                raise ValueError("FTT_ORIGINAL_PHYSICAL_IDENTITY_CHANGED:" + key)
        physics, comparisons = field_physics(
            model, action, reference, states, artifact, marker, diagnostic_only=fit
        )
        raw, mpc = save_complete_field_samples(
            model, action, packet, reference, states, artifact, marker
        )
        modes = model["bundle"]["modes"]
        physics.update(
            ordered_mode_sides=[m.side for m in modes],
            original_mode_manifest=dict(
                schema="fullspace-dtn.mode-manifest.v1",
                profile="full3d_scalable_v1",
                mode_count=len(modes),
                modes=model["record"]["modes"],
            ),
            ordered_mode_k_vectors=np.asarray([m.k_vector for m in modes]),
            ordered_mode_e_vectors=np.asarray([m.e_vector for m in modes]),
            port_area_nm2=(model["cfg"].x_max - model["cfg"].x_min)
            * (model["cfg"].y_max - model["cfg"].y_min),
        )
        high_physics, _ = field_physics(
            model,
            action,
            reference,
            states,
            artifact / "norm_q30",
            marker,
            norm_quadrature_degree=30,
            diagnostic_only=fit,
        )
        for name in states:
            normal = np.r_[
                physics["records"][name]["total_L2_scaled_curl_norms"],
                physics["records"][name]["scattered_L2_scaled_curl_norms"],
            ]
            highnormal = np.r_[
                high_physics["records"][name]["total_L2_scaled_curl_norms"],
                high_physics["records"][name]["scattered_L2_scaled_curl_norms"],
            ]
            drift = float(
                np.linalg.norm(normal - highnormal) / max(np.linalg.norm(normal), 1e-30)
            )
            reconstruction[name]["FE_norm_q15_q30_relative"] = drift
            reconstruction[name]["quadrature_pass"] &= drift <= 1e-8
        result = dict(
            verification_complete=True,
            same_p3_reference_sha256=entry["sha256"],
            reference_solve_count=0,
            global_Maxwell_factor_count=0,
            global_Gram_factor_count=0,
            reference_loaded_only_by_verifier=True,
            reference_pass=physics["reference_pass"],
            reconstruction=reconstruction,
            raw_complete_fields=dict(
                path=str(raw.relative_to(ROOT)), sha256=digest(raw)
            ),
            independent_MPC_recovery_checks=mpc,
            physics=physics,
            comparisons=comparisons,
            region_errors={
                name: _region_field_errors(model, action, reference, c)
                for name, c in states.items()
            },
            reference_used_for_training=fit,
            pde_only_solve=not fit,
            production_initialization_allowed=False,
            pde_only_solver_qualified=False,
            official_candidate_results=False,
        )
        atomic_json(artifact / "verifier_result.json", result)
        return result
    finally:
        destroy_same_mesh_physical_action(model["bundle"])


def saved_check(directory, design):
    from src.solvers.feinn_native import load_native
    from src.runners.block_wave_worker import saved_checker

    action = load_native(ROOT / design["files"]["native"]["path"])
    result = saved_checker(
        action, directory / "verifier_result.json", design, lambda *_: None
    )
    labelled = bool(
        json.loads((directory / "verifier_result.json").read_text())[
            "reference_used_for_training"
        ]
    )
    for record in result["records"].values():
        record.update(
            reference_used_for_training=labelled,
            pde_only_solve=not labelled,
            pde_only_solver_qualified=False
            if labelled
            else record["m5_full_discrete_numerical_gate"],
            official_candidate_results=False,
            production_initialization_allowed=False,
        )
    atomic_json(directory / "saved_checker.json", result)
    return result


if __name__ == "__main__":
    import sys

    saved_check(
        ROOT / Path(sys.argv[1]),
        json.loads((ROOT / "input/task042extra_feinn_5nm/design_v38.json").read_text()),
    )
