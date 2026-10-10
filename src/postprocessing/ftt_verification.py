"""FTT model reconstruction and original saved-field physics, separate roles."""

import json
from copy import deepcopy
import os
from pathlib import Path
from time import perf_counter
import numpy as np
from src.io.neural_wave_campaign import ROOT, digest
from src.solvers.neural_wave_greedy import atomic_json, atomic_npz

ART = ROOT / "benchmarks/artifacts/task42extra/v38"


def research_comparison_policy(comparisons):
    """Numerical qualification never grants production use to this pilot."""
    result = deepcopy(comparisons)
    for row in result.values():
        row["production_initialization_allowed"] = False
        row["official_candidate_results"] = False
    return result


def seal_saved_research_policy(directory, source_sha):
    """Correct only use metadata; preserve the original report and arrays."""
    path = directory / "verifier_result.json"
    result = json.loads(path.read_text())
    corrected = research_comparison_policy(result["comparisons"])
    if corrected == result["comparisons"]:
        return None
    original_sha = digest(path)
    for name in ("verifier_result.json", "saved_checker.json", "result.json"):
        source = directory / name
        saved = directory / (source.stem + "_before_research_policy.json")
        if source.exists() and not saved.exists():
            temporary = saved.with_suffix(".json.tmp")
            with temporary.open("wb") as stream:
                stream.write(source.read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, saved)
    result["comparisons"] = corrected
    result["research_use_policy_seal"] = dict(
        source_sha=source_sha,
        previous_report_sha256=original_sha,
        previous_report="verifier_result_before_research_policy.json",
        numerical_fields_and_raw_arrays_changed=False,
        old_wrong_use_flags_preserved=True,
        production_initialization_allowed=False,
        official_candidate_results=False,
    )
    atomic_json(path, result)
    return result["research_use_policy_seal"]


def gram_integral_pairing(G, samples, names, length_nm=5.0):
    """Pair original sparse G with independently saved complete FE integrals."""
    weights = np.asarray(samples["weights"])
    reference = np.asarray(samples["reference_c"])
    if (
        weights.ndim != 2
        or not np.isfinite(weights).all()
        or np.any(weights <= 0)
        or G.shape != (reference.size, reference.size)
    ):
        raise ValueError("FTT_G_INTEGRAL_LAYOUT_OR_WEIGHTS_INVALID")

    def integral(E, curl):
        return float(
            np.sum(
                weights
                * (
                    np.sum(abs(E) ** 2, axis=-1)
                    + length_nm**2 * np.sum(abs(curl) ** 2, axis=-1)
                )
            )
        )

    def quadratic(c):
        value = np.vdot(c, G @ c)
        if (
            not np.isfinite(value)
            or value.real < 0
            or abs(value.imag) > 1e-10 * max(value.real, 1e-30)
        ):
            raise ValueError("FTT_G_QUADRATIC_NOT_REAL_POSITIVE")
        return float(value.real)

    ref_g = quadratic(reference)
    ref_integral = integral(samples["REFERENCE_E"], samples["REFERENCE_curl"])
    if min(ref_g, ref_integral) <= 0:
        raise ValueError("FTT_REFERENCE_G_NORM_NONZERO_REQUIRED")
    ref_pair = abs(ref_g - ref_integral) / ref_g
    records = {}
    for name in names:
        error = samples[name + "_c"] - reference
        error_g = quadratic(error)
        error_integral = integral(
            samples[name + "_E"] - samples["REFERENCE_E"],
            samples[name + "_curl"] - samples["REFERENCE_curl"],
        )
        pair = abs(error_g - error_integral) / max(error_g, 1e-30)
        records[name] = dict(
            G_error_energy=error_g,
            independently_integrated_error_energy=error_integral,
            G_reference_energy=ref_g,
            independently_integrated_reference_energy=ref_integral,
            error_energy_pairing_relative=pair,
            reference_energy_pairing_relative=ref_pair,
            E_G=float(np.sqrt(error_g / ref_g)),
            identity_pass=bool(max(pair, ref_pair) <= 1e-8),
        )
    return dict(
        length_nm=length_nm,
        definition="integral |E|^2 + length_nm^2 |curl E|^2",
        G_matvec_count=1 + len(names),
        Gsolve_count=0,
        global_Gram_factor_count=0,
        records=records,
    )


def parameter_change_diagnostics(model, initial):
    """Post-freeze axis diagnostics; no rescaling or feedback to training."""
    import torch

    nodes = torch.as_tensor(np.polynomial.legendre.leggauss(33)[0], dtype=torch.float64)
    records = {}
    for axis, label in enumerate("xyz"):
        prefix = "cores." + str(axis)
        entries = [
            (name, p.detach().numpy().reshape(-1))
            for name, p in model.named_parameters()
            if name == prefix or name.startswith(prefix + ".")
        ]
        values = np.concatenate([p for _, p in entries])
        delta = np.concatenate([p - initial[name].reshape(-1) for name, p in entries])
        with torch.no_grad():
            core = model.core(axis, nodes).numpy()
        records[label] = dict(
            real_parameter_count=int(values.size),
            parameter_RMS=float(np.sqrt(np.mean(values**2))),
            parameter_delta_from_original_zero_seed_RMS=float(
                np.sqrt(np.mean(delta**2))
            ),
            changed_real_parameters=int(np.count_nonzero(delta)),
            kernel_element_RMS_at_fixed_33_nodes=float(
                np.sqrt(np.mean(abs(core) ** 2))
            ),
        )
    return records


def validate_checkpoint_identity(state, candidate, model, fit):
    from src.solvers.optimization_checkpoint import parameter_order

    for key in (
        "source_sha",
        "input_sha256",
        "design_sha256",
        "native_sha256",
        "moments_sha256",
        "reference_sha256",
        "model_kind",
        "metric_kind",
    ):
        if key not in state["metadata"] or state["metadata"][key] != candidate[key]:
            raise ValueError("FTT_CHECKPOINT_BINDING_MISMATCH:" + key)
    if (
        state["metadata"]["reference_used_for_training"] != fit
        or state["metadata"]["metric_kind"]
        != ("reference_fit_G" if fit else "native_euc")
        or state["metadata"]["production_initialization_allowed"]
        or state["parameter_order"] != parameter_order(model)
        or state["optimizer_class"] != candidate["checkpoint"]["optimizer_class"]
    ):
        raise ValueError("FTT_CHECKPOINT_PURPOSE_ORDER_OR_OPTIMIZER_MISMATCH")
    # Coordinate buffers are fixed identities, not extra optimization variables.
    for key in ("center", "half_width", "initial_core_scales"):
        if not np.array_equal(
            state["model"][key].numpy(), model.state_dict()[key].numpy()
        ):
            raise ValueError("FTT_CHECKPOINT_COORDINATE_BUFFER_CHANGED:" + key)


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


def reconstruct(
    design,
    action,
    packet,
    high,
    artifact,
    marker,
    fit=False,
    route_pairs=None,
    source_root=None,
):
    from src.solvers.ftt_field import FTTField
    from src.solvers.ftt_moments import StreamingMomentMap
    from src.solvers.optimization_checkpoint import load_checkpoint

    result = {}
    source_root = ART if source_root is None else source_root
    for stage, name in route_stages(fit) if route_pairs is None else route_pairs:
        candidate = json.loads((source_root / stage / "result.json").read_text())
        entry = candidate["checkpoint"]
        model = FTTField(
            design["model"]["geometry"]["bounds_nm"], candidate["model_kind"]
        )
        initial = {
            name: p.detach().numpy().copy() for name, p in model.named_parameters()
        }
        state = load_checkpoint(
            source_root / stage / "checkpoints" / entry["name"], entry["sha256"]
        )
        validate_checkpoint_identity(state, candidate, model, fit)
        producer_file = source_root / stage / "frozen_field.npz"
        with np.load(producer_file, allow_pickle=False) as data:
            if not np.array_equal(data["c"], state["c"]) or not np.array_equal(
                data["r"], state["r"]
            ):
                raise ValueError("FTT_FROZEN_PRODUCER_AND_COMMITTED_STATE_MISMATCH")
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
            producer_field_sha256=digest(producer_file),
            per_axis_parameter_and_kernel_diagnostics=parameter_change_diagnostics(
                model, initial
            ),
            checkpoint_identity_checked=True,
            reference_used_for_training=fit,
            pde_only_solve=not fit,
            production_initialization_allowed=False,
        )
        atomic_npz(artifact / (name + ".npz"), c30=c30, c60=c60, saved=saved)
        result[name] = record
        marker("independent_ftt_model_rebuilt", dict(name=name, **record))
    atomic_json(artifact / "reconstruction.json", result)
    return result


def compare(
    design, action, packet, rebuild_dir, artifact, marker, fit=False, route_pairs=None
):
    from src.solvers.feinn_fem import build_model
    from src.solvers.feinn_reference import field_physics, _region_field_errors
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )
    from src.postprocessing.neural_wave_audit import save_complete_field_samples

    reconstruction = json.loads((rebuild_dir / "reconstruction.json").read_text())
    states = {}
    for _, name in route_stages(fit) if route_pairs is None else route_pairs:
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
            comparisons=research_comparison_policy(comparisons),
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
    frozen = json.loads((directory / "verifier_result.json").read_text())
    raw = ROOT / frozen["raw_complete_fields"]["path"]
    gram_entry = design["gram"]
    gram_file = ROOT / gram_entry["path"]
    if digest(gram_file) != gram_entry["sha256"]:
        raise ValueError("FTT_ORIGINAL_G_SCORING_IDENTITY_CHANGED")
    from scipy.sparse import load_npz

    began = perf_counter()
    G = load_npz(gram_file)
    with np.load(raw, allow_pickle=False) as arrays:
        pairing = gram_integral_pairing(G, arrays, tuple(result["records"]))
    pairing["load_and_pairing_seconds"] = perf_counter() - began
    pairing["Gram_sha256"] = gram_entry["sha256"]
    result["G_and_independent_FE_integral_pairing"] = pairing
    del G
    for name, record in result["records"].items():
        record["m5_full_discrete_numerical_gate"] &= pairing["records"][name][
            "identity_pass"
        ]
        record.update(
            reference_used_for_training=labelled,
            features_reference_exposed=labelled,
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
        json.loads(
            (
                ROOT
                / (
                    sys.argv[3]
                    if len(sys.argv) == 4 and sys.argv[2] == "--design"
                    else "input/task042extra_feinn_5nm/design_v38.json"
                )
            ).read_text()
        ),
    )
