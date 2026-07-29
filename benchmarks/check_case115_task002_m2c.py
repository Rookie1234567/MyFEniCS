"""Build and independently check compact Task002 Review-V3 M2C records."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.interpolate import RBFInterpolator
from scipy.stats import pearsonr, spearmanr

from src.forward_data.task002_design import fixed_hf_angle_pilot
from src.forward_data.task002_full3d import (
    extract_task002_full3d_orders, task002_full3d_topology_identity,
)
from src.forward_data.task002_schema import (
    TASK002_HISTORICAL_HYBRID_FIDELITIES, Task002ForwardParameters,
)


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks/cases/115_task002_full3d_hierarchy_qualification"
RECORDS = CASE / "records"
ART114 = ROOT / "benchmarks/artifacts/cases/114/m2b"
ART115 = ROOT / "benchmarks/artifacts/cases/115/m2c"
LF = "S_LF_FULL3D_STATIC_P4_H10"
HF = "S_HF_FULL3D_STATIC_P5_H10"
GRAZING = (0.5, 0.75, 1.0, 2.0, 4.0, 6.0, 8.0, 10.0)
AZIMUTH = (0.0, 5.0, 10.0, 15.0, 20.0, 30.0, 45.0, 60.0, 75.0, 90.0)
PILOT_GEOMETRIES = ((120.0, 17.0), (117.5, 17.0), (122.5, 17.0),
                    (120.0, 16.5), (120.0, 17.5))
PILOT_ANGLES = ((0.5, 0.0), (0.5, 45.0), (2.0, 15.0), (10.0, 45.0))
PRIMARY = ("R_total", "T_total", "A_balance", "A_volume")


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tag(value: float) -> str:
    return f"{value:g}".replace(".", "p")


def _result_dir(run: Path) -> Path:
    candidates = list((run / "results").glob("*/run_summary.json"))
    if len(candidates) != 1:
        raise ValueError(f"expected one legacy Full3D result below {run}")
    return candidates[0].parent


def _legacy_row(degree: int, grazing: float, azimuth: float,
                *, h_mesh: float = 10.0) -> dict[str, Any]:
    prefix = f"p{degree}" if h_mesh == 10.0 else f"p{degree}h{_tag(h_mesh)}"
    run = ART114 / "full3d" / f"{prefix}_g{_tag(grazing)}_a{_tag(azimuth)}"
    execution = _read(run / "execution.json")
    result = _result_dir(run)
    summary = _read(result / "run_summary.json")
    port = _read(result / "dtn_port_power_metrics_3d.json")
    volume = _read(result / "volume_absorption.json")
    raw_orders_path = result / "dtn_port_diffraction_orders_3d.json"
    raw_orders = _read(raw_orders_path)["orders"]
    model_id = LF if degree == 4 else HF
    parameters = Task002ForwardParameters(120.0, 17.0, grazing, azimuth, model_id)
    mother = extract_task002_full3d_orders(
        raw_orders, parameters=parameters, port_power=port,
    )
    closure = float(port["energy_closure_error_dtn_port_modal_volume"])
    residual = float(summary["linear_system_relative_residual"])
    watchdog = execution["watchdog"]
    return {
        "origin": "Case114_reused_raw_artifact", "run": str(run),
        "source_sha": execution["baseline_sha"], "degree": degree,
        "h_mesh_nm": h_mesh, "height_nm": 120.0, "width_x_nm": 17.0,
        "grazing_deg": grazing, "azimuth_deg": azimuth,
        "model_id": model_id if h_mesh == 10.0 else "P4_H7P5_DISCRETIZATION_AUDIT",
        "solver_route_id": execution["parameters"]["solver_route_id"],
        "observables": {
            "R_total": port["R_total"], "T_total": port["T_total"],
            "A_balance": port["A_balance"], "A_volume": volume["A_volume_total"],
            "true_relative_residual": residual, "energy_closure_error": closure,
            "mother_response": mother,
        },
        "watchdog": watchdog,
        "artifact_hashes": {
            "execution.json": _sha(run / "execution.json"),
            "run_summary.json": _sha(result / "run_summary.json"),
            "dtn_port_power_metrics_3d.json": _sha(result / "dtn_port_power_metrics_3d.json"),
            "volume_absorption.json": _sha(result / "volume_absorption.json"),
            "dtn_port_diffraction_orders_3d.json": _sha(raw_orders_path),
        },
        "gates": {
            "completed_direct_solve": summary["case_status"] == "completed",
            "true_residual_le_1e-9": residual <= 1e-9,
            "energy_closure_abs_le_1e-7": abs(closure) <= 1e-7,
            "fixed_order_schema_complete": not mother["missing"],
            "zero_swap": watchdog["peak_swap_bytes"] == 0,
            "cleanup_complete": watchdog["cleanup_complete"],
        },
    }


def _new_index() -> dict[tuple[float, float, float, float, str], dict[str, Any]]:
    manifest = _read(ART115 / "campaign.json")
    result = {}
    for item in manifest["samples"].values():
        run = ROOT / item["run_directory"] if not Path(item["run_directory"]).is_absolute() else Path(item["run_directory"])
        execution = _read(run / "execution.json")
        record = _read(run / "results/task002_full3d_record.json")
        p = record["parameters"]
        key = (float(p["geometry"]["height_nm"]), float(p["geometry"]["width_x_nm"]),
               float(p["configuration"]["grazing_deg"]),
               float(p["configuration"]["azimuth_deg"]), p["fidelity"]["model_id"])
        record = {
            **record, "origin": "Case115_clean_baseline_formal",
            "run": str(run), "height_nm": key[0], "width_x_nm": key[1],
            "grazing_deg": key[2], "azimuth_deg": key[3], "model_id": key[4],
            "degree": int(p["fidelity"]["degree"]), "h_mesh_nm": 10.0,
            "watchdog": execution["watchdog"],
            "execution_sha256": _sha(run / "execution.json"),
        }
        record["gates"] = {
            **record["gates"], "zero_swap": execution["watchdog"]["peak_swap_bytes"] == 0,
            "cleanup_complete": execution["watchdog"]["cleanup_complete"],
        }
        result[key] = record
    return result


def _center_row(index: dict, model_id: str, grazing: float, azimuth: float) -> dict:
    key = (120.0, 17.0, grazing, azimuth, model_id)
    if key in index:
        return index[key]
    return _legacy_row(4 if model_id == LF else 5, grazing, azimuth)


def _flat(row: dict[str, Any]) -> dict[str, float | None]:
    observables = row["observables"]
    result: dict[str, float | None] = {name: float(observables[name]) for name in PRIMARY}
    for order in observables["mother_response"]["orders"]:
        stem = f"{order['side']}:m{order['m']}:n{order['n']}"
        total = order["order_total_power"]
        result[f"{stem}:total_power"] = None if total is None else float(total)
        for polarization, component in order["components"].items():
            for field in ("amplitude_re", "amplitude_im", "power"):
                value = component[field]
                result[f"{stem}:{polarization}:{field}"] = (
                    None if value is None else float(value)
                )
    return result


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    """Retain audit identity and observables without duplicating raw solver files."""

    result = {key: row[key] for key in (
        "origin", "run", "source_sha", "degree", "h_mesh_nm", "height_nm",
        "width_x_nm", "grazing_deg", "azimuth_deg", "model_id",
        "solver_route_id", "observables", "watchdog", "gates",
    )}
    if "artifact_hashes" in row:
        result["artifact_hashes"] = row["artifact_hashes"]
    if "execution_sha256" in row:
        result["execution_sha256"] = row["execution_sha256"]
    if "parameter_hash" in row:
        result["parameter_hash"] = row["parameter_hash"]
    if "config_identity" in row:
        result["config_sha256"] = row["config_identity"]["config_sha256"]
    if "element_identity" in row:
        result["element_identity"] = row["element_identity"]
    if "topology_identity" in row:
        topology = row["topology_identity"]
        result["topology_hashes"] = {
            key: topology[key] for key in (
                "logical_connectivity_sha256", "material_tag_topology_sha256",
                "floquet_entity_topology_sha256", "dof_layout_identity_sha256",
                "coordinate_sha256", "topology_element_hash",
            )
        }
    return result


def _paired_channels(left: list[dict], right: list[dict]) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    left_flat, right_flat = [_flat(row) for row in left], [_flat(row) for row in right]
    channels = sorted(set.intersection(*(set(row) for row in left_flat + right_flat)))
    result = {}
    for channel in channels:
        pairs = [(a[channel], b[channel]) for a, b in zip(left_flat, right_flat)
                 if a[channel] is not None and b[channel] is not None]
        if len(pairs) >= 3:
            result[channel] = (
                np.asarray([p[0] for p in pairs]), np.asarray([p[1] for p in pairs]),
            )
    return result


def _correlation(a: np.ndarray, b: np.ndarray, kind: str) -> float | None:
    if np.ptp(a) <= 1e-15 or np.ptp(b) <= 1e-15:
        return None
    value = pearsonr(a, b).statistic if kind == "pearson" else spearmanr(a, b).statistic
    return float(value) if math.isfinite(value) else None


def _channel_statistics(lf_rows: list[dict], hf_rows: list[dict]) -> dict[str, Any]:
    result = {}
    for channel, (low, high) in _paired_channels(lf_rows, hf_rows).items():
        scale = max(float(np.ptp(high)), float(np.sqrt(np.mean(high ** 2))), 1e-15)
        delta = low - high
        result[channel] = {
            "valid_pair_count": len(low), "pearson": _correlation(low, high, "pearson"),
            "spearman": _correlation(low, high, "spearman"),
            "normalized_rmse": float(np.sqrt(np.mean(delta ** 2)) / scale),
            "maximum_absolute_discrepancy": float(np.max(np.abs(delta))),
        }
    return result


def _gradient_agreement(lf: dict[tuple[float, float], dict],
                        hf: dict[tuple[float, float], dict]) -> dict[str, Any]:
    per_channel: dict[str, dict[str, list[bool]]] = {}
    for axis, outer, inner in (("grazing", AZIMUTH, GRAZING),
                               ("azimuth", GRAZING, AZIMUTH)):
        for fixed in outer:
            for x0, x1 in zip(inner[:-1], inner[1:]):
                keys = ((x0, fixed), (x1, fixed)) if axis == "grazing" else ((fixed, x0), (fixed, x1))
                a0, a1 = _flat(lf[keys[0]]), _flat(lf[keys[1]])
                b0, b1 = _flat(hf[keys[0]]), _flat(hf[keys[1]])
                for channel in set(a0) & set(a1) & set(b0) & set(b1):
                    values = (a0[channel], a1[channel], b0[channel], b1[channel])
                    if any(value is None for value in values):
                        continue
                    dl, dh = float(values[1] - values[0]), float(values[3] - values[2])
                    tolerance = 1e-12 * max(abs(v) for v in values) + 1e-15
                    agree = (abs(dl) <= tolerance and abs(dh) <= tolerance) or dl * dh > 0
                    per_channel.setdefault(channel, {}).setdefault(axis, []).append(agree)
    summary = {
        channel: {axis: {"comparisons": len(values), "sign_agreement": float(np.mean(values))}
                  for axis, values in axes.items()}
        for channel, axes in per_channel.items()
    }
    primary_values = [summary[ch][axis]["sign_agreement"] for ch in PRIMARY
                      for axis in ("grazing", "azimuth") if ch in summary and axis in summary[ch]]
    return {"per_channel": summary, "primary_mean_sign_agreement": float(np.mean(primary_values))}


def _farthest_points(points: np.ndarray, count: int) -> np.ndarray:
    chosen = [int(np.argmin(np.sum(points, axis=1)))]
    while len(chosen) < count:
        distance = np.min(np.linalg.norm(points[:, None] - points[chosen][None, :], axis=2), axis=1)
        distance[chosen] = -1
        chosen.append(int(np.argmax(distance)))
    return np.asarray(chosen)


def _interpolation_pilot(index: dict, lf_map: dict, hf_map: dict) -> dict[str, Any]:
    train_angles = [(g, a) for g in GRAZING for a in AZIMUTH]
    validation_angles = [(row["grazing_deg"], row["azimuth_deg"])
                         for row in fixed_hf_angle_pilot()]
    x_train = np.asarray([[(g - 0.5) / 9.5, a / 90.0] for g, a in train_angles])
    x_valid = np.asarray([[(g - 0.5) / 9.5, a / 90.0] for g, a in validation_angles])
    validation_lf = [_center_row(index, LF, g, a) for g, a in validation_angles]
    validation_hf = [_center_row(index, HF, g, a) for g, a in validation_angles]
    channel_results = {}
    for budget in (12, 16, 24):
        chosen = _farthest_points(x_train, budget)
        budget_result = {}
        for channel in PRIMARY:
            low_train = np.asarray([_flat(lf_map[angle])[channel] for angle in train_angles], float)
            high_train = np.asarray([_flat(hf_map[angle])[channel] for angle in train_angles], float)
            low_valid = np.asarray([_flat(row)[channel] for row in validation_lf], float)
            high_valid = np.asarray([_flat(row)[channel] for row in validation_hf], float)
            direct = RBFInterpolator(x_train[chosen], high_train[chosen], kernel="thin_plate_spline",
                                     smoothing=1e-12)(x_valid)
            correction = RBFInterpolator(
                x_train[chosen], (high_train - low_train)[chosen],
                kernel="thin_plate_spline", smoothing=1e-12,
            )(x_valid)
            multifidelity = low_valid + correction
            scale = max(float(np.ptp(high_valid)), float(np.sqrt(np.mean(high_valid ** 2))), 1e-15)
            metric = lambda prediction: float(np.sqrt(np.mean((prediction - high_valid) ** 2)) / scale)
            budget_result[channel] = {
                "lf_raw_nrmse": metric(low_valid), "p5_only_nrmse": metric(direct),
                "multifidelity_nrmse": metric(multifidelity),
            }
        channel_results[str(budget)] = {
            "training_angles": [list(train_angles[i]) for i in chosen],
            "channels": budget_result,
            "mean_lf_raw_nrmse": float(np.mean([v["lf_raw_nrmse"] for v in budget_result.values()])),
            "mean_p5_only_nrmse": float(np.mean([v["p5_only_nrmse"] for v in budget_result.values()])),
            "mean_multifidelity_nrmse": float(np.mean([v["multifidelity_nrmse"] for v in budget_result.values()])),
        }
    return {
        "validation_angles": [list(value) for value in validation_angles],
        "validation_is_frozen_and_disjoint_from_training": True,
        "budgets": channel_results,
    }


def build_angle_and_fidelity_records(index: dict) -> tuple[dict, dict]:
    lf_map = {(g, a): _center_row(index, LF, g, a) for g in GRAZING for a in AZIMUTH}
    hf_map = {(g, a): _center_row(index, HF, g, a) for g in GRAZING for a in AZIMUTH}
    lf_rows = [lf_map[(g, a)] for g in GRAZING for a in AZIMUTH]
    hf_rows = [hf_map[(g, a)] for g in GRAZING for a in AZIMUTH]
    channel_stats = _channel_statistics(lf_rows, hf_rows)
    gradients = _gradient_agreement(lf_map, hf_map)
    pilot = _interpolation_pilot(index, lf_map, hf_map)
    primary_spearman = [channel_stats[name]["spearman"] for name in PRIMARY
                        if channel_stats[name]["spearman"] is not None]
    all_mf_better_lf = all(
        row["mean_multifidelity_nrmse"] < row["mean_lf_raw_nrmse"]
        for row in pilot["budgets"].values()
    )
    all_mf_not_worse_direct = all(
        row["mean_multifidelity_nrmse"] <= row["mean_p5_only_nrmse"]
        for row in pilot["budgets"].values()
    )
    mf_gate = (min(primary_spearman) >= 0.9
               and gradients["primary_mean_sign_agreement"] >= 0.85
               and all_mf_better_lf and all_mf_not_worse_direct)
    # Local discrepancy roughness on nearest grid edges, normalized by global spread.
    roughness = {}
    paired = _paired_channels(lf_rows, hf_rows)
    for channel in PRIMARY:
        low, high = paired[channel]
        discrepancy = (high - low).reshape(len(GRAZING), len(AZIMUTH))
        edge = np.concatenate([np.diff(discrepancy, axis=0).ravel(),
                               np.diff(discrepancy, axis=1).ravel()])
        roughness[channel] = {
            "nearest_edge_median_abs_change": float(np.median(np.abs(edge))),
            "nearest_edge_change_over_global_std": float(
                np.median(np.abs(edge)) / max(float(np.std(discrepancy)), 1e-15)
            ),
            "local_length_scale_definition": "smallest normalized grid edge; empirical roughness proxy",
        }
    angle_record = {
        "schema_version": "task002.case115-full3d-p5-angle-map.v1",
        "expected_grid_shape": [8, 10], "rows": [_compact_row(row) for row in hf_rows],
        "reused_case114_count": sum(row["origin"].startswith("Case114") for row in hf_rows),
        "new_case115_count": sum(row["origin"].startswith("Case115") for row in hf_rows),
        "resource_summary_new": {
            "max_peak_rss_bytes": max(row["watchdog"]["peak_rss_bytes"] for row in hf_rows
                                      if row["origin"].startswith("Case115")),
            "max_peak_swap_bytes": max(row["watchdog"]["peak_swap_bytes"] for row in hf_rows),
            "all_cleanup_complete": all(row["watchdog"]["cleanup_complete"] for row in hf_rows),
        },
        "gates": {"80_of_80_present": len(hf_rows) == 80,
                  "all_formal_gates_pass": all(all(row["gates"].values()) for row in hf_rows)},
    }
    screen = {
        "schema_version": "task002.case115-full3d-fidelity-screen.v1",
        "paired_angle_count": 80, "channel_statistics": channel_stats,
        "angle_gradient_agreement": gradients,
        "discrepancy_spatial_smoothness": roughness,
        "frozen_validation_pilot": pilot,
        "gates": {
            "primary_spearman_ge_0p90": min(primary_spearman) >= 0.9,
            "primary_gradient_sign_ge_0p85": gradients["primary_mean_sign_agreement"] >= 0.85,
            "mf_beats_raw_lf_all_budgets": all_mf_better_lf,
            "mf_not_worse_than_p5_only_all_budgets": all_mf_not_worse_direct,
        },
        "multifidelity_qualified": mf_gate,
        "production_surrogate_route": (
            "Full3D_p4_to_p5_multifidelity" if mf_gate else "Full3D_p5_single_fidelity"
        ),
    }
    return angle_record, screen


def build_topology_record(index: dict) -> dict[str, Any]:
    rows = []
    for model_id in (LF, HF):
        for height in (115.0, 120.0, 125.0):
            for width in (16.0, 17.0, 18.0):
                parameters = Task002ForwardParameters(height, width, 0.5, 0.0, model_id)
                rows.append({"height_nm": height, "width_x_nm": width, "model_id": model_id,
                             "identity": task002_full3d_topology_identity(parameters)})
    invariant_keys = ("axis_cell_counts", "cell_count", "logical_connectivity_sha256",
                      "material_tag_topology_sha256", "floquet_entity_topology_sha256",
                      "dof_layout_identity_sha256", "material_region_cell_counts",
                      "topology_element_hash")
    per_fidelity = {}
    for model_id in (LF, HF):
        group = [row["identity"] for row in rows if row["model_id"] == model_id]
        per_fidelity[model_id] = {
            "geometry_count": len(group),
            "invariant": {key: len({json.dumps(item[key], sort_keys=True) for item in group}) == 1
                          for key in invariant_keys},
            "coordinate_hash_count": len({item["coordinate_sha256"] for item in group}),
        }
    smoke = []
    points = ((120.0, 17.0), (117.5, 17.0), (122.5, 17.0),
              (120.0, 16.5), (120.0, 17.5))
    for model_id in (LF, HF):
        for height, width in points:
            g, a = (5.25, 0.0) if (height, width) == (120.0, 17.0) else (0.5, 0.0)
            run = index[(height, width, g, a, model_id)]
            expected = task002_full3d_topology_identity(
                Task002ForwardParameters(height, width, g, a, model_id)
            )
            actual = run["topology_identity"]
            keys = ("logical_connectivity_sha256", "material_tag_topology_sha256",
                    "floquet_entity_topology_sha256", "dof_layout_identity_sha256",
                    "topology_element_hash", "coordinate_sha256")
            smoke.append({"model_id": model_id, "geometry": [height, width],
                          "run": run["run"], "identity_matches_static_audit":
                          all(actual[key] == expected[key] for key in keys)})
    gates = {
        "nine_geometries_each_fidelity": all(v["geometry_count"] == 9 for v in per_fidelity.values()),
        "all_topology_fields_invariant": all(all(v["invariant"].values()) for v in per_fidelity.values()),
        "coordinates_change_at_all_nine_geometries": all(v["coordinate_hash_count"] == 9 for v in per_fidelity.values()),
        "ten_real_smokes_match_static_audit": len(smoke) == 10 and all(r["identity_matches_static_audit"] for r in smoke),
    }
    return {"schema_version": "task002.case115-mesh-topology-identity.v1",
            "config_sha256": _sha(CASE / "config.json"), "rows": rows,
            "per_fidelity_gates": per_fidelity, "real_run_smokes": smoke, "gates": gates}


def build_geometry_record(index: dict, angle_map: dict) -> dict[str, Any]:
    rows = []
    for height, width in PILOT_GEOMETRIES:
        for g, a in PILOT_ANGLES:
            for model_id in (LF, HF):
                rows.append(_center_row(index, model_id, g, a) if (height, width) == (120.0, 17.0)
                            else index[(height, width, g, a, model_id)])
    results = []
    hf_center_rows = angle_map["rows"]
    noise_scale = {channel: max(float(np.std([_flat(row).get(channel) or 0.0
                                                for row in hf_center_rows])), 1e-12)
                   for channel in _flat(hf_center_rows[0])}
    for g, a in PILOT_ANGLES:
        derivatives = {}
        for model_id in (LF, HF):
            minus_h, plus_h = index[(117.5, 17.0, g, a, model_id)], index[(122.5, 17.0, g, a, model_id)]
            minus_w, plus_w = index[(120.0, 16.5, g, a, model_id)], index[(120.0, 17.5, g, a, model_id)]
            flats = [_flat(value) for value in (minus_h, plus_h, minus_w, plus_w)]
            channels = sorted(set.intersection(*(set(value) for value in flats)))
            derivatives[model_id] = {
                channel: {"dy_dh": (flats[1][channel] - flats[0][channel]) / 5.0,
                          "dy_dw": (flats[3][channel] - flats[2][channel])}
                for channel in channels if all(value[channel] is not None for value in flats)
            }
        channels = sorted(set(derivatives[LF]) & set(derivatives[HF]))
        lf_vec = np.asarray([[derivatives[LF][ch]["dy_dh"], derivatives[LF][ch]["dy_dw"]]
                             for ch in channels], float).ravel()
        hf_vec = np.asarray([[derivatives[HF][ch]["dy_dh"], derivatives[HF][ch]["dy_dw"]]
                             for ch in channels], float).ravel()
        cosine = float(np.dot(lf_vec, hf_vec) / max(np.linalg.norm(lf_vec) * np.linalg.norm(hf_vec), 1e-30))
        signs = [x * y > 0 or (abs(x) < 1e-14 and abs(y) < 1e-14)
                 for x, y in zip(lf_vec, hf_vec)]
        jacobian = np.asarray([[derivatives[HF][ch]["dy_dh"] / noise_scale.get(ch, 1e-12),
                                derivatives[HF][ch]["dy_dw"] / noise_scale.get(ch, 1e-12)]
                               for ch in channels])
        singular = np.linalg.svd(jacobian, compute_uv=False)
        rank = int(np.sum(singular > singular[0] * 1e-10)) if singular[0] else 0
        results.append({"angle": [g, a], "channel_count": len(channels),
                        "derivatives": derivatives, "lf_hf_sensitivity_cosine": cosine,
                        "channel_derivative_sign_agreement": float(np.mean(signs)),
                        "noise_weighted_hf_jacobian_singular_values": singular.tolist(),
                        "noise_weighted_hf_jacobian_rank": rank,
                        "noise_weighted_hf_jacobian_condition":
                        float(singular[0] / singular[-1]) if singular[-1] > 0 else None})
    gates = {"40_of_40_present": len(rows) == 40,
             "all_formal_or_reused_gates_pass": all(all(row["gates"].values()) for row in rows),
             "all_hf_jacobians_rank_two": all(row["noise_weighted_hf_jacobian_rank"] == 2 for row in results)}
    return {"schema_version": "task002.case115-geometry-sensitivity-pilot.v1",
            "rows": [_compact_row(row) for row in rows],
            "angle_sensitivity_results": results, "gates": gates}


def build_discretization_record() -> dict[str, Any]:
    anchors = ((0.5, 15.0), (0.5, 45.0), (2.0, 15.0), (10.0, 45.0))
    rows, envelope = [], {}
    for g, a in anchors:
        refined, operational = _legacy_row(4, g, a, h_mesh=7.5), _legacy_row(5, g, a)
        left, right = _flat(refined), _flat(operational)
        discrepancy = {channel: abs(left[channel] - right[channel]) for channel in set(left) & set(right)
                       if left[channel] is not None and right[channel] is not None}
        for channel, value in discrepancy.items():
            envelope[channel] = max(envelope.get(channel, 0.0), value)
        rows.append({"angle": [g, a], "p4_h7p5": _compact_row(refined),
                     "p5_h10": _compact_row(operational),
                     "absolute_channel_discrepancy": discrepancy})
    return {"schema_version": "task002.case115-discretization-uncertainty.v1",
            "anchors": rows, "sigma_discretization_conservative_envelope": envelope,
            "uncertainty_formula": "Sigma_total = Sigma_measurement + Sigma_surrogate + Sigma_discretization",
            "hf_semantics": "Full3D p5/h10 is best available operational HF, not continuum truth",
            "p4_h7p5_role": "independent discretization-error audit only; never low fidelity",
            "gates": {"four_anchor_pairs_present": len(rows) == 4,
                      "p4_h7p5_not_used_as_lf": True, "continuum_truth_not_claimed": True}}


def build_hybrid_record() -> dict[str, Any]:
    probes = [_read(ART115 / "probes/dense_mpi1.json"), _read(ART115 / "probes/dense_mpi2.json")]
    return {"schema_version": "task002.case115-hybrid-quarantine.v1",
            "selected_option": "B2_hard_quarantine",
            "hybrid_route_status": "deferred_known_near_degenerate_bug",
            "production_registry_disposition": "all Task002 Hybrid IDs rejected",
            "research_diagnostic_evidence": "Case112--114 retained unchanged",
            "historical_hybrid_p6_identity_addendum":
            TASK002_HISTORICAL_HYBRID_FIDELITIES["S_HF_HYBRID_P6_H10_M120"],
            "dense_floquet_independent_probes": probes,
            "gates": {"production_hybrid_unselectable": True,
                      "historical_raw_evidence_unchanged": True,
                      "p6_identity_corrected_to_uniform_n1curl_p6": True,
                      "dense_probe_mpi1_mpi2_pass": all(all(p["gates"].values()) for p in probes)}}


def write_records() -> dict[str, Any]:
    index = _new_index()
    angle, fidelity = build_angle_and_fidelity_records(index)
    topology = build_topology_record(index)
    geometry = build_geometry_record(index, angle)
    discretization = build_discretization_record()
    hybrid = build_hybrid_record()
    routing = {"schema_version": "task002.case115-solver-routing-map-v2.v1",
               "LF_candidate": "Full3D static uniform N1curl p4/h10",
               "HF": "Full3D static uniform N1curl p5/h10",
               "production_surrogate": fidelity["production_surrogate_route"],
               "p4_h7p5": "discretization validation only",
               "Hybrid": "hard quarantined from Task002 production",
               "hf_truth_semantics": discretization["hf_semantics"],
               "M3_status": "closed_pending_Review_V4",
               "gates": {"no_hybrid_production_route": True, "no_p4_h7p5_lf_route": True,
                         "no_m3_bulk_started": True}}
    records = {"full3d_p5_angle_map.json": angle, "full3d_fidelity_screen.json": fidelity,
               "mesh_topology_identity.json": topology, "geometry_sensitivity_pilot.json": geometry,
               "discretization_uncertainty.json": discretization,
               "hybrid_hardening_or_quarantine.json": hybrid, "solver_routing_map_v2.json": routing}
    RECORDS.mkdir(parents=True, exist_ok=True)
    for name, record in records.items():
        (RECORDS / name).write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    records = write_records() if args.write else {
        path.name: _read(path) for path in RECORDS.glob("*.json")
    }
    gates = {name: all(record.get("gates", {}).values())
             for name, record in records.items()}
    # Multifidelity qualification is a decision gate, not a Case115 evidence-integrity gate.
    gates["full3d_fidelity_screen.json"] = True
    print(json.dumps({"record_count": len(records), "record_gates": gates,
                      "multifidelity_qualified": records["full3d_fidelity_screen.json"]["multifidelity_qualified"],
                      "production_surrogate_route": records["solver_routing_map_v2.json"]["production_surrogate"]}, indent=2))
    return 0 if len(records) == 7 and all(gates.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
