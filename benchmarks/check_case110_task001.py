"""Recompute Task001 conclusions and write compact, hash-bound Case110 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from src.forward_data.identifiability import (
    central_geometry_jacobian,
    fisher_metrics,
    greedy_channel_indices,
    local_linear_recovery,
    rank_configuration_subsets,
)
from src.forward_data.orders import extract_task001_orders
from src.forward_data.resource_policy import GIB, predict_p6_h7p5
from src.forward_data.schema import (
    TASK001_OBSERVABLE_SCHEMA_VERSION,
    Task001ForwardParameters,
)


BASELINE_SHA = "68f4f9bc92de6cd7ec2896755ef210fb182280a1"
ACTIVE_POWER_FLOOR = 1.0e-8
GEOMETRY = {
    "g00": (120.0, 17.0), "ghm": (117.5, 17.0), "ghp": (122.5, 17.0),
    "gwm": (120.0, 16.5), "gwp": (120.0, 17.5),
    "cmm": (115.0, 16.0), "cmp": (115.0, 18.0),
    "cpm": (125.0, 16.0), "cpp": (125.0, 18.0),
}
STENCIL = ("g00", "ghm", "ghp", "gwm", "gwp")
CONFIGURATIONS = {
    "g10_a0_s": {"grazing_deg": 10.0, "azimuth_deg": 0.0, "polarization": "S"},
    "g0p5_a90_s": {"grazing_deg": 0.5, "azimuth_deg": 90.0, "polarization": "S"},
    "g10_a90_s": {"grazing_deg": 10.0, "azimuth_deg": 90.0, "polarization": "S"},
}
LF_RUNS = {
    "g10_a0_s": {
        "g00": "m2_lf4_g00_g10_a0_s_68f4f9b",
        **{key: f"m4_lf4_{key}_g10_a0_s_68f4f9b" for key in STENCIL[1:]},
        **{key: f"m5_lf4_{key}_g10_a0_s_68f4f9b" for key in GEOMETRY if key.startswith("c")},
    },
    "g0p5_a90_s": {
        key: f"m5_lf4_{key}_g0p5_a90_s_68f4f9b" for key in GEOMETRY
    },
    "g10_a90_s": {
        key: f"m5_lf4_{key}_g10_a90_s_68f4f9b" for key in GEOMETRY
    },
}
HF_RUNS = {
    "g10_a0_s": {
        "g00": "m3_hf10_g00_g10_a0_s_68f4f9b",
        **{key: f"m4_hf10_{key}_g10_a0_s_68f4f9b" for key in STENCIL[1:]},
    },
    "g10_a90_s": {
        key: f"m6_hf10_{key}_g10_a90_s_68f4f9b" for key in STENCIL
    },
}


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parameters(execution: Mapping[str, Any]) -> Task001ForwardParameters:
    value = execution["parameters"]
    illumination = value["configuration"]["illumination"]
    return Task001ForwardParameters(
        height_nm=value["geometry"]["height_nm"],
        width_x_nm=value["geometry"]["width_x_nm"],
        grazing_deg=illumination["grazing_deg"],
        azimuth_deg=illumination["azimuth_deg"],
        incident_polarization=illumination["incident_polarization"],
        model_id=value["fidelity"]["model_id"],
        mpi_ranks=value["execution"]["mpi_ranks"],
        threads_per_rank=value["execution"]["threads_per_rank"],
    )


def _interface_max(record: Mapping[str, Any], field: str) -> float:
    continuity = record["physical_field_reconstruction"]["interface_continuity"]
    return max(float(continuity[side][field]["relative_l2"]) for side in ("bottom", "top"))


def _run_summary(root: Path, run_dir: Path) -> dict[str, Any]:
    execution_path = run_dir / "execution.json"
    execution = _read(execution_path)
    watchdog = execution["watchdog"]
    result: dict[str, Any] = {
        "run_id": run_dir.name,
        "artifact_directory": str(run_dir.relative_to(root)),
        "execution_sha256": _sha256(execution_path),
        "baseline_sha": execution["baseline_sha"],
        "parameter_hash": execution["parameter_hash"],
        "parameters": execution["parameters"],
        "raw_observable_schema_version": execution["parameters"]["observables"]["order_schema_id"],
        "compact_observable_schema_version": TASK001_OBSERVABLE_SCHEMA_VERSION,
        "watchdog_status": watchdog["status"],
        "child_return_code": watchdog["child_return_code"],
        "wall_seconds": watchdog["elapsed_seconds"],
        "peak_rss_bytes": watchdog["peak_rss_bytes"],
        "peak_swap_bytes": watchdog["peak_swap_bytes"],
        "cleanup_complete": watchdog["cleanup_complete"],
        "solver_record_present": execution["solver_record_present"],
    }
    if execution["baseline_sha"] != BASELINE_SHA:
        raise ValueError(f"mixed formal source in {run_dir}")
    solver_path = run_dir / "solver_record.json"
    if not solver_path.is_file():
        result["classification"] = "failed"
        stderr_path = run_dir / "watchdog/stderr.log"
        if stderr_path.is_file():
            lines = [line.strip() for line in stderr_path.read_text().splitlines() if "Error:" in line]
            result["stderr_sha256"] = _sha256(stderr_path)
            result["failure_message"] = lines[-1] if lines else "child exited before solver record"
        return result
    record = _read(solver_path)
    gates = {key: bool(value) for key, value in record["gates"].items()}
    volume = record["physical_field_reconstruction"]["volume_absorption"]
    port = record["validation"]["port_power"]
    bottom = record["hybrid_system"]["bottom_matrix_stats"]
    factor_inventory = record["object_payload_ledger"]["local_or_augmented_factor_inventory"]
    result.update({
        "solver_record_sha256": _sha256(solver_path),
        "classification": "measured_pass" if all(gates.values()) else "failed_physics_gate",
        "all_solver_gates_pass": all(gates.values()),
        "true_relative_residual": record["solve"]["true_relative_residual"],
        "max_interface_e_relative_l2": _interface_max(record, "electric_tangential"),
        "max_interface_h_relative_l2": _interface_max(record, "magnetic_tangential"),
        "energy_closure_error": volume["energy_closure_error"],
        "R_total": port["R_total"], "T_total": port["T_total"],
        "A_balance": port["A_balance"], "A_volume_total": volume["A_volume_total"],
        "local_matrix_rows_per_side": bottom["matrix_rows"],
        "local_matrix_nnz_per_side": int(bottom["matrix_nnz_used"]),
        "factor_nnz_bottom": int(factor_inventory["bottom"]["matrix_stats"]["matrix_nnz_used"]),
        "factor_nnz_top": int(factor_inventory["top"]["matrix_stats"]["matrix_nnz_used"]),
        "solver_total_seconds_max_rank": record["timing_seconds_max_rank"]["total"],
    })
    return result


def _order_vectors(root: Path, artifacts: Path, run_name: str) -> tuple[list[str], np.ndarray]:
    run_dir = artifacts / run_name
    execution = _read(run_dir / "execution.json")
    record = _read(run_dir / "solver_record.json")
    extracted = extract_task001_orders(
        record["validation"]["external_diffraction_orders"],
        parameters=_parameters(execution), port_power=record["validation"]["port_power"],
    )
    if extracted["missing"] or not all(extracted["port_power_consistency"][key] for key in ("r_matches", "t_matches")):
        raise ValueError(f"fixed order extraction failed for {run_name}")
    labels = []
    powers = []
    for row in extracted["orders"]:
        for polarization in ("s", "p"):
            labels.append(f"{row['port_side']}:m{row['m']}:{polarization}")
            powers.append(float(row["components"][polarization]["power"] or 0.0))
    powers = np.asarray(powers)
    return labels, powers


def _compact_response(root: Path, artifacts: Path, run_name: str) -> dict[str, Any]:
    run_dir = artifacts / run_name
    execution_path = run_dir / "execution.json"
    solver_path = run_dir / "solver_record.json"
    execution = _read(execution_path)
    record = _read(solver_path)
    extracted = extract_task001_orders(
        record["validation"]["external_diffraction_orders"],
        parameters=_parameters(execution), port_power=record["validation"]["port_power"],
    )
    if extracted["missing"]:
        raise ValueError(f"compact response has missing fixed identities: {run_name}")
    for order in extracted["orders"]:
        component_powers = [
            order["components"][polarization]["power"]
            for polarization in ("s", "p")
            if order["components"][polarization]["power"] is not None
        ]
        expected_total = sum(component_powers) if component_powers else None
        if expected_total is None:
            if order["order_total_power"] is not None or order["power_carrying"]:
                raise ValueError(f"non-power-carrying order has numeric total: {run_name}")
        elif not math.isclose(
            float(order["order_total_power"]), expected_total,
            rel_tol=1.0e-13, abs_tol=1.0e-15,
        ):
            raise ValueError(f"S/P power sum mismatch: {run_name}")
        for key in ("kx", "ky", "kz"):
            if set(order[key]) != {"re", "im"}:
                raise ValueError(f"unstable wavevector JSON identity: {run_name}")
    leakage = extracted["leakage"]
    if set(leakage) != {
        "n_nonzero_reflection_power_sum",
        "n_nonzero_transmission_power_sum",
        "n_nonzero_max_abs_amplitude",
    }:
        raise ValueError(f"incomplete leakage diagnostics: {run_name}")
    consistency = extracted["port_power_consistency"]
    if not consistency["r_matches"] or not consistency["t_matches"]:
        raise ValueError(f"compact/raw R/T mismatch: {run_name}")
    return {
        "run_id": run_name,
        "numerical_source_sha": execution["baseline_sha"],
        "parameter_hash": execution["parameter_hash"],
        "raw_execution_sha256": _sha256(execution_path),
        "raw_solver_record_sha256": _sha256(solver_path),
        "raw_observable_schema_version": execution["parameters"]["observables"]["order_schema_id"],
        "compact_observable_schema_version": extracted["schema_version"],
        "parameters": execution["parameters"],
        "compact_diffraction_response": extracted,
    }


def _configuration_data(
    root: Path, artifacts: Path, runs: Mapping[str, str], *, observation: str,
) -> dict[str, Any]:
    labels: list[str] | None = None
    values: dict[str, np.ndarray] = {}
    for geometry, run_name in runs.items():
        current_labels, powers = _order_vectors(root, artifacts, run_name)
        if labels is None:
            labels = current_labels
        elif labels != current_labels:
            raise ValueError("order identity changed across geometry stencil")
        values[geometry] = powers
    assert labels is not None
    candidate = np.asarray([
        observation == "reflection_and_transmission" or label.startswith("top:")
        for label in labels
    ])
    active = np.max(np.vstack([values[key] for key in STENCIL]), axis=0) >= ACTIVE_POWER_FLOOR
    indices = np.flatnonzero(candidate & active)
    jacobian = central_geometry_jacobian(
        height_minus=values["ghm"][indices], height_plus=values["ghp"][indices],
        width_minus=values["gwm"][indices], width_plus=values["gwp"][indices],
    )
    local_selected = greedy_channel_indices(jacobian, values["g00"][indices], max_channels=8)
    selected = indices[np.asarray(local_selected)]
    return {
        "labels": labels,
        "values": values,
        "active_indices": indices,
        "selected_indices": selected,
        "selected_labels": [labels[index] for index in selected],
        "jacobian": central_geometry_jacobian(
            height_minus=values["ghm"][selected], height_plus=values["ghp"][selected],
            width_minus=values["gwm"][selected], width_plus=values["gwp"][selected],
        ),
        "nominal_power": values["g00"][selected],
    }


def _metric_view(metrics: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "rank", "singular_values", "condition_number", "log_det_fisher", "rho_hw",
        "sigma_height_nm", "sigma_width_nm", "relative_noise", "absolute_power_floor",
    )
    return {key: metrics[key] for key in keys}


def _m5_analysis(root: Path, artifacts: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    analyses: dict[str, dict[str, Any]] = {}
    output: dict[str, Any] = {
        "schema_version": "task001.case110-identifiability.v1",
        "numerical_source_sha": BASELINE_SHA,
        "feature_semantics": "independent outgoing S/P component powers; active floor 1e-8",
        "noise_semantics": "provisional DOE assumptions, not measured instrument uncertainty",
        "observations": {},
    }
    for observation in ("reflection_only", "reflection_and_transmission"):
        candidates: dict[str, Any] = {}
        per_configuration: dict[str, Any] = {}
        for name, runs in LF_RUNS.items():
            data = _configuration_data(root, artifacts, runs, observation=observation)
            analyses[f"{observation}:{name}"] = data
            metrics = fisher_metrics(data["jacobian"], data["nominal_power"])
            per_configuration[name] = {
                "configuration": CONFIGURATIONS[name],
                "active_channel_count": int(len(data["active_indices"])),
                "selected_channels": data["selected_labels"],
                **_metric_view(metrics),
            }
            candidates[name] = {
                "jacobian": data["jacobian"], "nominal_power": data["nominal_power"],
                "azimuth_class": "planar" if CONFIGURATIONS[name]["azimuth_deg"] == 0 else "conical",
            }
        ranked = rank_configuration_subsets(candidates)
        passing = next(row for row in ranked if row["passes"])
        selected_names = passing["configuration_subset"]
        stability = []
        for noise in (0.005, 0.01, 0.02):
            jac = np.vstack([candidates[name]["jacobian"] for name in selected_names])
            power = np.concatenate([candidates[name]["nominal_power"] for name in selected_names])
            stability.append(_metric_view(fisher_metrics(jac, power, relative_noise=noise)))
        output["observations"][observation] = {
            "per_configuration": per_configuration,
            "selected_configuration_subset": selected_names,
            "selected_subset_metrics_1pct": _metric_view(passing),
            "noise_stability": stability,
        }
    output["selected_configuration_subset"] = output["observations"]["reflection_and_transmission"]["selected_configuration_subset"]
    if output["selected_configuration_subset"] != ["g10_a0_s", "g10_a90_s"]:
        raise ValueError("unexpected Task001 selected configuration bundle")
    corner_checks: dict[str, Any] = {}
    for name in CONFIGURATIONS:
        data = analyses[f"reflection_and_transmission:{name}"]
        selected = data["active_indices"]
        center = data["values"]["g00"][selected]
        jac = central_geometry_jacobian(
            height_minus=data["values"]["ghm"][selected], height_plus=data["values"]["ghp"][selected],
            width_minus=data["values"]["gwm"][selected], width_plus=data["values"]["gwp"][selected],
        )
        errors = []
        for key in ("cmm", "cmp", "cpm", "cpp"):
            height, width = GEOMETRY[key]
            predicted = center + jac @ np.asarray([height - 120.0, width - 17.0])
            actual_delta = data["values"][key][selected] - center
            errors.append(float(np.linalg.norm(data["values"][key][selected] - predicted) / max(np.linalg.norm(actual_delta), 1e-12)))
        corner_checks[name] = {"relative_local_linear_errors": errors, "maximum": max(errors)}
    output["corner_nonlinearity"] = corner_checks
    return output, analyses


def _hf_analysis(
    root: Path, artifacts: Path, lf_analyses: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "task001.case110-high-fidelity-identifiability.v1",
        "numerical_source_sha": BASELINE_SHA,
        "selected_configuration_subset": ["g10_a0_s", "g10_a90_s"],
        "observations": {},
    }
    rt_bundle: tuple[np.ndarray, np.ndarray] | None = None
    for observation in ("reflection_only", "reflection_and_transmission"):
        jacobians = []
        powers = []
        channels = []
        for name in result["selected_configuration_subset"]:
            hf = _configuration_data(root, artifacts, HF_RUNS[name], observation=observation)
            lf = lf_analyses[f"{observation}:{name}"]
            selected_labels = lf["selected_labels"]
            hf_label_to_index = {label: index for index, label in enumerate(hf["labels"])}
            selected = np.asarray([hf_label_to_index[label] for label in selected_labels])
            values = hf["values"]
            jac = central_geometry_jacobian(
                height_minus=values["ghm"][selected], height_plus=values["ghp"][selected],
                width_minus=values["gwm"][selected], width_plus=values["gwp"][selected],
            )
            jacobians.append(jac)
            powers.append(values["g00"][selected])
            channels.extend([f"{name}:{label}" for label in selected_labels])
        bundle_jac = np.vstack(jacobians)
        bundle_power = np.concatenate(powers)
        metrics = fisher_metrics(bundle_jac, bundle_power)
        simultaneous = max(
            min(height, width) for height, width in zip(
                metrics["channel_contribution_height"], metrics["channel_contribution_width"]
            )
        )
        result["observations"][observation] = {
            "selected_channels": channels,
            **_metric_view(metrics),
            "maximum_single_channel_min_fraction_of_height_and_width_information": simultaneous,
            "no_single_channel_dominates_both": simultaneous < 0.90,
        }
        if observation == "reflection_and_transmission":
            rt_bundle = bundle_jac, bundle_power
    assert rt_bundle is not None
    jacobian, nominal_power = rt_bundle
    result["synthetic_local_recovery"] = _synthetic_recovery(jacobian, nominal_power)
    if result["observations"]["reflection_and_transmission"]["rank"] != 2:
        raise ValueError("high-fidelity selected bundle is not rank two")
    return result


def _synthetic_recovery(jacobian: np.ndarray, nominal_power: np.ndarray) -> dict[str, Any]:
    rng = np.random.default_rng(20260728)
    sigma = np.sqrt((0.01 * nominal_power) ** 2 + 1.0e-8**2)
    targets = ([0.5, 0.1], [-0.5, -0.1])
    output = {
        "semantics": "local weighted linear sanity recovery; not surrogate training or formal inversion",
        "center_self_recovery": local_linear_recovery(jacobian, np.zeros(len(jacobian)), nominal_power),
        "targets": [], "noise_draw_count": 2000, "rng_seed": 20260728,
    }
    for target in targets:
        exact_delta = jacobian @ np.asarray(target)
        exact = local_linear_recovery(jacobian, exact_delta, nominal_power)
        estimates = np.empty((2000, 2))
        for index in range(len(estimates)):
            noisy = exact_delta + rng.normal(0.0, sigma)
            recovered = local_linear_recovery(jacobian, noisy, nominal_power)
            estimates[index] = [recovered["delta_height_nm"], recovered["delta_width_nm"]]
        mean = np.mean(estimates, axis=0)
        spread = np.std(estimates, axis=0, ddof=1)
        output["targets"].append({
            "true_delta_height_nm": target[0], "true_delta_width_nm": target[1],
            "noise_free_recovery": exact,
            "noise_1pct_mean_delta_height_nm": float(mean[0]),
            "noise_1pct_mean_delta_width_nm": float(mean[1]),
            "noise_1pct_bias_height_nm": float(mean[0] - target[0]),
            "noise_1pct_bias_width_nm": float(mean[1] - target[1]),
            "noise_1pct_std_height_nm": float(spread[0]),
            "noise_1pct_std_width_nm": float(spread[1]),
            "noise_1pct_empirical_correlation": float(np.corrcoef(estimates.T)[0, 1]),
        })
    return output


def _case096_comparison(root: Path, artifacts: Path) -> dict[str, Any]:
    reference_path = root / "benchmarks/cases/095_high_order_local_hp_resource_envelope/records/significant_channel_reference_v1.json"
    reference = _read(reference_path)
    record = _read(artifacts / HF_RUNS["g10_a0_s"]["g00"] / "solver_record.json")
    rows = {
        (row["side"], int(row["m"]), int(row["n"]), row["polarization"]): row
        for row in record["validation"]["external_diffraction_orders"]
    }
    comparisons = []
    for channel in reference["channels"]:
        identity = channel["channel"]
        key = (identity["side"], identity["m"], identity["n"], identity["polarization"])
        current = rows[key]
        expected = channel["reference_center"]
        amplitude_error = float(np.linalg.norm(
            np.asarray(current["outgoing_amplitude_at_boundary"]) - np.asarray(expected["complex_amplitude"])
        ))
        comparisons.append({
            "label": identity["label"],
            "power_absolute_error": abs(float(current["power_ratio"]) - float(expected["power"])),
            "complex_amplitude_absolute_error": amplitude_error,
        })
    return {
        "reference_path": str(reference_path.relative_to(root)),
        "reference_sha256": _sha256(reference_path),
        "channel_count": len(comparisons),
        "maximum_power_absolute_error": max(row["power_absolute_error"] for row in comparisons),
        "maximum_complex_amplitude_absolute_error": max(row["complex_amplitude_absolute_error"] for row in comparisons),
        "comparisons": comparisons,
    }


def _lf_hf_comparison(
    root: Path, artifacts: Path, campaign_by_name: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    lf_values = []
    hf_values = []
    for geometry in STENCIL:
        lf_labels, lf_power = _order_vectors(root, artifacts, LF_RUNS["g10_a0_s"][geometry])
        hf_labels, hf_power = _order_vectors(root, artifacts, HF_RUNS["g10_a0_s"][geometry])
        if lf_labels != hf_labels:
            raise ValueError("LF/HF order identity mismatch")
        lf_values.append(lf_power)
        hf_values.append(hf_power)
    lf_array = np.vstack(lf_values)
    hf_array = np.vstack(hf_values)
    active = np.max(hf_array, axis=0) >= ACTIVE_POWER_FLOOR
    lf_jac = central_geometry_jacobian(
        height_minus=lf_array[1, active], height_plus=lf_array[2, active],
        width_minus=lf_array[3, active], width_plus=lf_array[4, active],
    )
    hf_jac = central_geometry_jacobian(
        height_minus=hf_array[1, active], height_plus=hf_array[2, active],
        width_minus=hf_array[3, active], width_plus=hf_array[4, active],
    )
    cosine = []
    sign_pass = []
    for column in range(2):
        cosine.append(float(np.dot(lf_jac[:, column], hf_jac[:, column]) / (
            np.linalg.norm(lf_jac[:, column]) * np.linalg.norm(hf_jac[:, column])
        )))
        information = hf_jac[:, column] ** 2
        ranked = np.argsort(information)[::-1]
        cumulative = np.cumsum(information[ranked])
        cutoff = np.searchsorted(cumulative, 0.8 * cumulative[-1], side="left") + 1
        important = ranked[:cutoff]
        sign_pass.append(bool(np.all(lf_jac[important, column] * hf_jac[important, column] >= 0.0)))
    lf_runs = [campaign_by_name[LF_RUNS["g10_a0_s"][geometry]] for geometry in STENCIL]
    hf_runs = [campaign_by_name[HF_RUNS["g10_a0_s"][geometry]] for geometry in STENCIL]
    discrepancies = {}
    for field in ("R_total", "T_total", "A_balance", "A_volume_total"):
        values = [abs(float(lf[field]) - float(hf[field])) for lf, hf in zip(lf_runs, hf_runs)]
        discrepancies[field] = {"maximum_absolute": max(values), "mean_absolute": float(np.mean(values))}
    return {
        "illumination": CONFIGURATIONS["g10_a0_s"],
        "geometry_stencil": list(STENCIL),
        "active_channel_count": int(np.count_nonzero(active)),
        "cosine_dy_dh": cosine[0], "cosine_dy_dw": cosine[1],
        "top_80pct_fisher_sign_consistency_height": sign_pass[0],
        "top_80pct_fisher_sign_consistency_width": sign_pass[1],
        "mean_lf_to_hf_wall_time_ratio": float(np.mean([
            lf["wall_seconds"] / hf["wall_seconds"] for lf, hf in zip(lf_runs, hf_runs)
        ])),
        "mean_lf_to_hf_peak_rss_ratio": float(np.mean([
            lf["peak_rss_bytes"] / hf["peak_rss_bytes"] for lf, hf in zip(lf_runs, hf_runs)
        ])),
        "aggregate_discrepancies": discrepancies,
        "passes": bool(min(cosine) >= 0.85 and all(sign_pass)),
        "selected_low_fidelity": "LF4",
        "lf5_status": "not_run_lf4_passed",
    }


def build_records(root: Path) -> dict[str, dict[str, Any]]:
    artifacts = root / "benchmarks/artifacts/cases/110"
    run_dirs = sorted(artifacts.glob("*_68f4f9b"))
    campaign = [_run_summary(root, run_dir) for run_dir in run_dirs]
    if len(campaign) != 42:
        raise ValueError(f"expected 42 Task001 artifact directories, found {len(campaign)}")
    successful = [row for row in campaign if row["classification"] == "measured_pass"]
    failed = [row for row in campaign if row["classification"] != "measured_pass"]
    if len(successful) != 37 or len(failed) != 5:
        raise ValueError("unexpected Task001 pass/fail artifact count")
    m3 = next(row for row in campaign if row["run_id"] == HF_RUNS["g10_a0_s"]["g00"])
    campaign_by_name = {row["run_id"]: row for row in campaign}
    prediction = predict_p6_h7p5(measured_h10_peak_bytes=m3["peak_rss_bytes"])
    prediction.update({
        "hard_ceiling_bytes": int(10.5 * GIB),
        "launch_projection_ceiling_bytes": int(0.9 * 10.5 * GIB),
        "central_within_launch_ceiling": prediction["central_estimate_bytes"] <= int(0.9 * 10.5 * GIB),
        "conservative_within_hard_ceiling": prediction["conservative_estimate_bytes"] <= int(10.5 * GIB),
        "decision": "controlled_stop_resource_projection",
        "pde_launched": False,
    })
    m5, analyses = _m5_analysis(root, artifacts)
    hf = _hf_analysis(root, artifacts, analyses)
    compact_responses = [
        _compact_response(root, artifacts, row["run_id"])
        for row in successful
    ]
    lossy_response = next(
        row for row in compact_responses
        if row["run_id"] == "m5_lf4_g00_g0p5_a90_s_68f4f9b"
    )
    lossy_order = next(
        row for row in lossy_response["compact_diffraction_response"]["orders"]
        if row["port_side"] == "bottom" and row["m"] == 0
    )
    if lossy_order["dispersion_propagating"] or not lossy_order["power_carrying"]:
        raise ValueError("real lossy record lost separated dispersion/power semantics")
    lossy_audit = {
        "run_id": lossy_response["run_id"],
        "identity": {"side": "transmission", "m": 0, "n": 0},
        "dispersion_propagating": lossy_order["dispersion_propagating"],
        "power_carrying": lossy_order["power_carrying"],
        "s_power": lossy_order["components"]["s"]["power"],
        "p_power": lossy_order["components"]["p"]["power"],
        "order_total_power": lossy_order["order_total_power"],
    }
    manifest = {
        "schema_version": "task001.case110-campaign-manifest.v1",
        "numerical_source_sha": BASELINE_SHA,
        "postprocessing_semantics": "positive outward power is power-carrying; raw dispersion flag preserved separately",
        "raw_observable_schema_version": "task001.fixed-n0-orders.v1",
        "compact_observable_schema_version": TASK001_OBSERVABLE_SCHEMA_VERSION,
        "artifact_count": len(campaign), "measured_pass_count": len(successful),
        "failed_count": len(failed), "runs": campaign,
        "aggregate_pass_gates": {
            "all_measured_records_same_source": all(row["baseline_sha"] == BASELINE_SHA for row in successful),
            "all_measured_solver_gates_pass": all(row["all_solver_gates_pass"] for row in successful),
            "all_measured_zero_swap": all(row["peak_swap_bytes"] == 0 for row in successful),
            "all_watchdogs_cleaned": all(row["cleanup_complete"] for row in campaign),
        },
    }
    fidelity = {
        "schema_version": "task001.case110-fidelity-qualification.v1",
        "numerical_source_sha": BASELINE_SHA,
        "selected_high_fidelity": "HF10",
        "selected_low_fidelity": "LF4",
        "formal_mpi_ranks": 2, "threads_per_rank": 1, "modes": 120,
        "hf7p5": prediction,
        "m160_status": "not_run_optional_identity_frozen_at_m120",
        "case096_significant_channel_comparison": _case096_comparison(root, artifacts),
        "hf10_nominal": m3,
        "lf4_vs_hf10": _lf_hf_comparison(root, artifacts, campaign_by_name),
    }
    return {
        "campaign_manifest.json": manifest,
        "fidelity_qualification.json": fidelity,
        "illumination_identifiability.json": m5,
        "high_fidelity_identifiability.json": hf,
        "compact_diffraction_responses.json": {
            "schema_version": "task001.case110-compact-diffraction-responses.v2",
            "numerical_source_sha": BASELINE_SHA,
            "raw_observable_schema_version": "task001.fixed-n0-orders.v1",
            "compact_observable_schema_version": TASK001_OBSERVABLE_SCHEMA_VERSION,
            "response_count": len(compact_responses),
            "real_lossy_record_semantics_audit": lossy_audit,
            "responses": compact_responses,
        },
    }


def _serialized(value: Mapping[str, Any]) -> str:
    def safe(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: safe(current) for key, current in item.items()}
        if isinstance(item, (list, tuple)):
            return [safe(current) for current in item]
        if isinstance(item, (float, np.floating)) and not math.isfinite(float(item)):
            if math.isnan(float(item)):
                return "nan"
            return "inf" if float(item) > 0 else "-inf"
        return item

    return json.dumps(safe(value), indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-records", action="store_true")
    parser.add_argument("--check-records", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    records = build_records(root)
    record_dir = root / "benchmarks/cases/110_surrogate_two_parameter_pilot/records"
    if args.write_records:
        record_dir.mkdir(parents=True, exist_ok=True)
        for name, value in records.items():
            (record_dir / name).write_text(_serialized(value))
    if args.check_records:
        for name, value in records.items():
            path = record_dir / name
            if not path.is_file() or path.read_text() != _serialized(value):
                raise SystemExit(f"stale or missing compact record: {path}")
    summary = {
        "records": sorted(records),
        "selected_configuration_subset": records["illumination_identifiability.json"]["selected_configuration_subset"],
        "hf_rank": records["high_fidelity_identifiability.json"]["observations"]["reflection_and_transmission"]["rank"],
        "hf_rho": records["high_fidelity_identifiability.json"]["observations"]["reflection_and_transmission"]["rho_hw"],
        "hf_condition": records["high_fidelity_identifiability.json"]["observations"]["reflection_and_transmission"]["condition_number"],
        "compact_response_count": records["compact_diffraction_responses.json"]["response_count"],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
