"""Run the Task007 stored-response objective-GP replay benchmark.

The runner is deliberately FEM-free.  All oracle values come from the
immutable Task006 train37 compact arrays or the eleven complete Case141
external replay samples.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUTCOMES = ROOT / "surrogate_tasks/task007_schneider_objective_gp_benchmark/outcomes"
sys.path.insert(0, str(ROOT / "src"))

from surrogate.task007.objective import (  # noqa: E402
    CONTRACTS,
    EXCLUDED_GEOMETRY,
    EXTERNAL_GEOMETRIES,
    FORWARD_SOLVER_SHA,
    MODEL_ID,
    NOISE_SCENARIOS,
    OBSERVABLE_SCHEMA,
    ROUTE_ID,
    ObjectiveGP,
    array_hash,
    canonical_hash,
    choose_ei,
    continuous_map,
    initial_sets,
    load_replay_data,
    log_objective,
    objective_values,
    scale_geometry,
)

EXPECTED_TRAIN_MANIFEST_SHA = "f36ffe992efe44f89c51bcac35e68145256e80979810d60ae5437686fd91cf84"
EXPECTED_MODEL_LOCK_SHA = "f08180f891b485a4ddedcf4066a2bed6a4164342fc0e296bfb06d2278469a7a1"
RANDOM_REPEATS = 100
INITIAL_SET_COUNT = 6


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def _float(value: Any) -> float:
    return float(np.asarray(value, dtype=np.float64))


def _initial_payload(data, sets5: list[np.ndarray], sets12: list[np.ndarray]) -> dict[str, Any]:
    def rows(sets: list[np.ndarray]) -> list[dict[str, Any]]:
        return [{"set_id": i, "indices": values.tolist(),
                 "geometries": data.geometries[values].tolist(),
                 "tuple_sha256": canonical_hash(data.geometries[values].tolist())}
                for i, values in enumerate(sets)]
    return {
        "P0_cold5": rows(sets5), "P1_trained12": rows(sets12),
        "P2_trained37": {"indices": data.train_indices, "geometries": data.geometries[data.train_indices].tolist(),
                          "tuple_sha256": canonical_hash(data.geometries[data.train_indices].tolist())},
    }


def build_m0(data, sets5: list[np.ndarray], sets12: list[np.ndarray]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    inventory = {
        "schema_version": "task007.replay-data-inventory.v1",
        "status": "immutable_replay_inventory",
        "new_fem_count": 0,
        "train_count": data.train_count,
        "external_replay_target_count": len(data.external_indices),
        "complete_replay_universe_count": len(data.geometries),
        "excluded_geometry": list(EXCLUDED_GEOMETRY),
        "excluded_geometry_present": any(np.all(data.geometries == EXCLUDED_GEOMETRY, axis=1)),
        "forward_solver_sha": FORWARD_SOLVER_SHA,
        "model_id": MODEL_ID,
        "solver_route_id": ROUTE_ID,
        "observable_schema_version": OBSERVABLE_SCHEMA,
        "train_manifest_sha256": data.train_manifest_sha256,
        "model_lock_sha256": data.model_lock_sha256,
        "geometries_sha256": array_hash(data.geometries),
        "J1_response_array_sha256": array_hash(data.j1),
        "J0_response_array_sha256": array_hash(data.j0),
        "records": data.inventory,
    }
    target_rows: list[dict[str, Any]] = []
    objective_audit_rows: list[dict[str, Any]] = []
    for target_index in data.external_indices:
        row = {"target_index": target_index, "geometry": data.geometries[target_index].tolist(),
               "label": "external_replay_target_not_task006_blind_pass"}
        audit_row = {"target_index": target_index, "geometry": row["geometry"]}
        for contract, responses in data.responses.items():
            row[contract] = {}
            audit_row[contract] = {}
            for scenario in NOISE_SCENARIOS:
                truth = objective_values(responses[target_index], responses, scenario)
                raw_min_count = int(np.sum(truth <= 1.0e-12))
                row[contract][scenario] = {
                    "self_F_before_log_floor": _float(truth[target_index]),
                    "self_log10F": _float(log_objective(truth[target_index])),
                    "unique_minimizer_count": raw_min_count,
                    "unique_minimizer": raw_min_count == 1,
                    "objective_array_sha256": array_hash(truth),
                }
                audit_row[contract][scenario] = {"finite": bool(np.all(np.isfinite(truth))),
                                                  "self_zero": bool(truth[target_index] <= 1.0e-12),
                                                  "unique": raw_min_count == 1,
                                                  "min_value": _float(np.min(truth))}
        target_rows.append(row); objective_audit_rows.append(audit_row)
    targets = {
        "schema_version": "task007.replay-targets.v1",
        "status": "frozen_external_replay_targets",
        "target_count": len(target_rows),
        "target_geometries": [row["geometry"] for row in target_rows],
        "excluded_geometry_absent": not inventory["excluded_geometry_present"],
        "targets": target_rows,
        "initial_sets_train_only": _initial_payload(data, sets5, sets12),
    }
    contract = {
        "schema_version": "task007.objective-contract.v1",
        "status": "frozen",
        "new_fem_count": 0,
        "forward_identity": {"forward_solver_sha": FORWARD_SOLVER_SHA, "model_id": MODEL_ID,
                              "solver_route_id": ROUTE_ID, "observable_schema_version": OBSERVABLE_SCHEMA},
        "geometry_domain_nm": {"height": [115.0, 125.0], "width": [16.0, 18.0]},
        "angles": [{"angle_id": aid, "grazing_deg": g, "azimuth_deg": a} for aid, g, a in (("A05", 2.0, 0.0), ("A07", 2.0, 90.0), ("A09", 4.0, 60.0))],
        "J1": {"name": "fixed-order-m0-total-power", "channels": [
            ["A05", "reflection", 0, 0], ["A05", "transmission", 0, 0],
            ["A07", "reflection", 0, 0], ["A07", "transmission", 0, 0],
            ["A09", "reflection", 0, 0], ["A09", "transmission", 0, 0]],
            "observable": "order_total_power=S+P", "flattening": "angle-major then reflection/transmission"},
        "J0": {"name": "aggregate-side-totals", "channels": [
            ["A05", "R_total"], ["A05", "T_total"], ["A07", "R_total"],
            ["A07", "T_total"], ["A09", "R_total"], ["A09", "T_total"]],
            "observable": "aggregate R_total,T_total", "not_combined_with_J1": True},
        "noise": {"N1": "sqrt((0.01*abs(y_M))^2+(1e-4)^2)",
                   "N2": "sqrt((0.02*abs(y_M))^2+(5e-4)^2)",
                   "semantics": "synthetic diagonal benchmark weight, sigma uses target measurement"},
        "objective": {"formula": "0.5*sum(((y_M-y(x))/sigma(y_M))^2)+Phi_prior",
                       "prior": "bounded_uniform_zero_inside_domain_plus_infinity_outside",
                       "epsilon_F": 1.0e-12, "gp_target": "log10(F+epsilon_F)"},
        "gp": {"kernel": "Matern-5/2-ARD", "mean": "constant", "input_scaling": "[-1,1]^2",
               "jitter_candidates": [1.0e-10, 1.0e-8], "optimizer_starts": 8,
               "normalize_y": True, "training_only_jitter_selection": True},
        "methods": {"B0": "nearest_offline_objective", "B1": "random_replay_search",
                    "P0": "cold_start_Bayesian_optimization_initial5", "P1": "partially_trained_Bayesian_optimization_initial12",
                    "P2": "fully_offline_trained_Bayesian_optimization_initial37", "P3": "posterior_mean_continuous_MAP"},
        "random": {"repeats_per_target": RANDOM_REPEATS, "seed_formula": "100000 + target_offset*1000 + contract_offset*100 + noise_offset*10 + repeat"},
        "initial_sets": _initial_payload(data, sets5, sets12),
        "initial_set_hashes": {"P0": canonical_hash([values.tolist() for values in sets5]),
                               "P1": canonical_hash([values.tolist() for values in sets12])},
    }
    checks = {
        "replay_count_37_plus_11": len(data.geometries) == 48,
        "train_count_37": data.train_count == 37,
        "external_count_11": len(data.external_indices) == 11,
        "excluded_incomplete_geometry_absent": not inventory["excluded_geometry_present"],
        "all_source_sha_exact": all(row.get("source_sha") == FORWARD_SOLVER_SHA for row in data.inventory),
        "all_schema_exact": all(row.get("observable_schema_version") == OBSERVABLE_SCHEMA for row in data.inventory),
        "all_arrays_finite": bool(np.all(np.isfinite(data.j1)) and np.all(np.isfinite(data.j0))),
        "all_external_self_objective_zero": all(item[contract][scenario]["self_zero"] for item in objective_audit_rows for contract in CONTRACTS for scenario in NOISE_SCENARIOS),
        "all_external_unique_minimizer": all(item[contract][scenario]["unique"] for item in objective_audit_rows for contract in CONTRACTS for scenario in NOISE_SCENARIOS),
        "initial_P0_train_only": all(set(values.tolist()).issubset(set(data.train_indices)) for values in sets5),
        "initial_P1_train_only": all(set(values.tolist()).issubset(set(data.train_indices)) for values in sets12),
        "lock_hash_expected": data.model_lock_sha256 == EXPECTED_MODEL_LOCK_SHA,
        "train_manifest_hash_expected": data.train_manifest_sha256 == EXPECTED_TRAIN_MANIFEST_SHA,
    }
    audit = {"schema_version": "task007.objective-identity-audit.v1", "status": "pass" if all(checks.values()) else "failed",
             "checks": checks, "errors": [key for key, value in checks.items() if not value],
             "objective_identity_rows": objective_audit_rows,
             "target_objective_not_in_initial_gp": True,
             "task006_lock_modified": False, "new_fem_count": 0}
    return inventory, targets, contract, audit


def _best_record(data, truth, observed: list[int]) -> dict[str, Any]:
    best = min(observed, key=lambda index: (float(truth[index]), int(index)))
    return {"best_index": int(best), "best_geometry": data.geometries[best].tolist(),
            "best_F": _float(truth[best]), "best_log10F": _float(log_objective(truth[best])),
            "online_query_count": 0}


def run_bo(data, target_index: int, contract: str, scenario: str, initial: np.ndarray,
           method: str, seed: int) -> dict[str, Any]:
    responses = data.responses[contract]
    measurement = responses[target_index]
    truth = objective_values(measurement, responses, scenario)
    log_truth = log_objective(truth)
    observed = [int(index) for index in initial.tolist()]
    if target_index in observed:
        raise ValueError("external target leaked into initial observations")
    history = [_best_record(data, truth, observed)]
    history[0]["online_query_count"] = 0
    queries: list[dict[str, Any]] = []
    fit_metadata: list[dict[str, Any]] = []
    acquisition_metadata: list[dict[str, Any]] = []
    while target_index not in observed:
        gp = ObjectiveGP(seed=seed + len(queries) * 31)
        gp.fit(scale_geometry(data.geometries[observed]), log_truth[observed])
        fit_metadata.append({"query_step": len(queries), "observed_indices": list(observed), "metadata": gp.metadata()})
        available = [index for index in range(len(data.geometries)) if index not in observed]
        best = min(float(log_truth[index]) for index in observed)
        chosen, acquisition = choose_ei(gp, data.geometries, available, best)
        acquisition_metadata.append({
            "query_step": len(queries), "candidate_order": acquisition["candidate_indices"],
            "chosen_index": chosen, "chosen_geometry": data.geometries[chosen].tolist(),
            "chosen_ei": acquisition["chosen_ei"],
            "candidate_scores_sha256": canonical_hash({"indices": acquisition["candidate_indices"],
                                                         "mean": acquisition["mean"], "std": acquisition["std"],
                                                         "ei": acquisition["expected_improvement"]}),
        })
        observed.append(chosen)
        queries.append({"query_step": len(queries), "index": chosen, "geometry": data.geometries[chosen].tolist(),
                        "is_target": bool(chosen == target_index), "revealed_F": _float(truth[chosen]),
                        "revealed_log10F": _float(log_truth[chosen])})
        best_row = _best_record(data, truth, observed)
        best_row["online_query_count"] = len(queries)
        history.append(best_row)
        if len(queries) >= len(data.geometries):
            break
    hit = target_index in observed
    return {"method": method, "target_index": target_index, "target_geometry": data.geometries[target_index].tolist(),
            "contract": contract, "noise_scenario": scenario, "initial_indices": initial.tolist(),
            "initial_geometries": data.geometries[initial].tolist(), "initial_target_leakage": False,
            "seed": int(seed), "queries": queries, "acquisition": acquisition_metadata,
            "fit_metadata": fit_metadata, "history": history, "exact_target_hit": hit,
            # query_step is zero based for the acquisition trace; the public
            # metric is an online-query count and therefore starts at one.
            "queries_to_exact_target": next((int(row["query_step"]) + 1 for row in queries if row["is_target"]), None),
            "final": history[-1]}


def run_random(data, target_index: int, contract: str, scenario: str, initial: np.ndarray,
               seed: int) -> dict[str, Any]:
    truth = objective_values(data.responses[contract][target_index], data.responses[contract], scenario)
    rng = np.random.default_rng(seed)
    observed = [int(index) for index in initial.tolist()]
    remaining = [index for index in rng.permutation(len(data.geometries)).tolist() if index not in observed]
    q_to_target = None; best_f = float(np.min(truth[observed])); best_index = min(observed, key=lambda i: (truth[i], i))
    for step, index in enumerate(remaining, start=1):
        observed.append(int(index))
        if truth[index] < best_f:
            best_f = float(truth[index]); best_index = int(index)
        if index == target_index:
            q_to_target = step; break
    return {"seed": int(seed), "exact_target_hit": q_to_target is not None,
            "queries_to_exact_target": q_to_target, "best_F_at_stop": best_f,
            "best_index_at_stop": best_index, "best_geometry_at_stop": data.geometries[best_index].tolist()}


def run_p3(data, target_index: int, contract: str, scenario: str, seed: int) -> dict[str, Any]:
    truth = objective_values(data.responses[contract][target_index], data.responses[contract], scenario)
    gp = ObjectiveGP(seed=seed).fit(scale_geometry(data.geometries[data.train_indices]),
                                     log_objective(truth[data.train_indices]))
    mapping = continuous_map(gp)
    selected = np.asarray(mapping["selected_geometry"], dtype=np.float64)
    error = np.abs(selected - data.geometries[target_index])
    return {"method": "P3", "target_index": target_index, "target_geometry": data.geometries[target_index].tolist(),
            "contract": contract, "noise_scenario": scenario, "seed": int(seed),
            "fit_metadata": gp.metadata(), "map": mapping,
            "height_abs_error_nm": _float(error[0]), "width_abs_error_nm": _float(error[1]),
            "within_tolerance": bool(error[0] <= 0.25 and error[1] <= 0.05)}


def summarize_random(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [row["queries_to_exact_target"] for row in rows if row["queries_to_exact_target"] is not None]
    return {"repeats": len(rows), "hit_count": len(values), "hit_fraction": len(values) / len(rows),
            "median_queries": float(np.median(values)) if values else None,
            "p90_queries": float(np.percentile(values, 90)) if values else None,
            "max_queries": int(max(values)) if values else None,
            "seed_hash": canonical_hash([row["seed"] for row in rows])}


def collect_model_audit(results: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if "jitter_candidates_metadata" in value and "selected_jitter" in value:
                rows.append(value)
            for child in value.values(): visit(child)
        elif isinstance(value, list):
            for child in value: visit(child)
    visit(results)
    selected = [row["selected_jitter"] for row in rows]
    warning_count = 0; collision_count = 0; finite = True
    for row in rows:
        for candidate in row.get("jitter_candidates_metadata", []):
            metadata = candidate.get("metadata", {})
            warning_count += sum(int(run.get("warning_count", 0)) for run in metadata.get("optimization_runs", []))
            collision_count += sum(len(run.get("boundary_collisions", [])) for run in metadata.get("optimization_runs", []))
            finite = finite and all(np.isfinite(float(run.get("log_marginal_likelihood", 0.0))) for run in metadata.get("optimization_runs", []))
    return {"schema_version": "task007.objective-gp-model-audit.v1", "status": "pass" if finite else "failed",
            "fit_count": len(rows), "selected_jitter_counts": {str(value): selected.count(value) for value in sorted(set(selected))},
            "warning_count": warning_count, "boundary_collision_count": collision_count,
            "all_lml_finite": finite, "kernel": "Matern-5/2-ARD", "optimizer_starts": 8,
            "jitter_selection_training_only": True}


def markdown_report(bo: dict[str, Any], maps: dict[str, Any], audit: dict[str, Any]) -> str:
    lines = ["# Task007 method comparison", "", "本报告只使用 stored-response replay；没有运行 FEM。在线查询数不包括初始训练点，首次查询计为 1。", "",
             "## B0 nearest offline objective", "", "| contract | noise | targets | exact target hits | median best F | p90 best F |", "|---|---|---:|---:|---:|---:|"]
    for key in sorted(f"{contract}_{scenario}_B0" for contract in CONTRACTS for scenario in NOISE_SCENARIOS):
        row = bo["summary"].get(key)
        if row is not None:
            lines.append(f"| {row['contract']} | {row['noise_scenario']} | {row['target_count']} | {row['exact_target_hit_count']} | {row['median_best_F']:.6g} | {row['p90_best_F']:.6g} |")
    lines.extend(["", "## B1/P0/P1/P2 discrete replay", "",
             "| contract | noise | method | targets | replay/BO runs | hit fraction | median queries | p90 queries |", "|---|---|---|---:|---:|---:|---:|---:|"]
    )
    # Only the aggregate rows are reported here.  Per-target rows remain in
    # BAYESIAN_OPTIMIZATION_REPLAY.json for the independent checker.
    aggregate_keys = {f"{contract}_{scenario}_{method}"
                      for contract in CONTRACTS for scenario in NOISE_SCENARIOS
                      for method in ("B1", "P0", "P1", "P2")}
    for key in sorted(aggregate_keys):
        row = bo["summary"].get(key)
        if row is None:
            continue
        runs = int(row.get("run_count", row.get("repeat_count", row.get("target_count", 0))))
        label = "B1 random replay" if row["method"] == "B1" else row["method"]
        lines.append(f"| {row['contract']} | {row['noise_scenario']} | {label} | {row.get('target_count', 11)} | {runs} | {row['hit_fraction']:.3f} | {row['median_queries']:.3f} | {row['p90_queries']:.3f} |")
    lines.extend(["", "## P3 continuous MAP", "", "| contract | noise | within tolerance | p90 height error (nm) | p90 width error (nm) |", "|---|---|---:|---:|---:|"])
    for key, row in maps["summary"].items():
        lines.append(f"| {row['contract']} | {row['noise_scenario']} | {row['success_fraction']:.3f} | {row['p90_height_error_nm']:.6f} | {row['p90_width_error_nm']:.6f} |")
    lines.extend(["", "## GP audit", "", f"- fit count: `{audit['fit_count']}`", f"- optimizer warnings recorded: `{audit['warning_count']}`", f"- boundary collisions recorded: `{audit['boundary_collision_count']}`", "- external target objective values were never used before query.", "- This is a synthetic replay benchmark, not formal experimental inversion."])
    return "\n".join(lines) + "\n"


def main() -> int:
    OUTCOMES.mkdir(parents=True, exist_ok=True)
    data = load_replay_data(ROOT)
    sets5 = initial_sets(data.geometries[data.train_indices], 5, INITIAL_SET_COUNT)
    sets12 = initial_sets(data.geometries[data.train_indices], 12, INITIAL_SET_COUNT)
    inventory, targets, contract, audit = build_m0(data, sets5, sets12)
    write_json(OUTCOMES / "REPLAY_DATA_INVENTORY.json", inventory)
    write_json(OUTCOMES / "REPLAY_TARGETS.json", targets)
    write_json(OUTCOMES / "OBJECTIVE_CONTRACT.json", contract)
    write_json(OUTCOMES / "OBJECTIVE_IDENTITY_AUDIT.json", audit)
    if audit["status"] != "pass":
        raise SystemExit("Task007 M0 objective identity audit failed; stopped before GP benchmark")

    all_results: dict[str, Any] = {"schema_version": "task007.bayesian-optimization-replay.v1", "status": "complete",
                                   "target_count": len(data.external_indices), "summary": {}, "targets": []}
    map_results: dict[str, Any] = {"schema_version": "task007.map-recovery-summary.v1", "status": "complete", "summary": {}, "targets": []}
    p0_sets = [values for values in sets5]
    p1_sets = [values for values in sets12]
    for target_offset, target_index in enumerate(data.external_indices):
        target_block: dict[str, Any] = {"target_index": target_index, "geometry": data.geometries[target_index].tolist(), "scenarios": {}}
        for contract_index, measurement_contract in enumerate(CONTRACTS):
            responses = data.responses[measurement_contract]
            target_block["scenarios"][measurement_contract] = {}
            for noise_index, scenario in enumerate(NOISE_SCENARIOS):
                truth = objective_values(responses[target_index], responses, scenario)
                offline = data.train_indices
                best_offline = min(offline, key=lambda index: (float(truth[index]), int(index)))
                b0 = {"method": "B0", "target_index": target_index, "contract": measurement_contract, "noise_scenario": scenario,
                      "online_query_count": 0, "best_index": int(best_offline), "best_geometry": data.geometries[best_offline].tolist(),
                      "best_F": _float(truth[best_offline]), "exact_target_hit": False, "queries_to_exact_target": None}
                random_rows = [run_random(data, target_index, measurement_contract, scenario, p0_sets[0],
                                          100000 + target_offset * 1000 + contract_index * 100 + noise_index * 10 + repeat)
                               for repeat in range(RANDOM_REPEATS)]
                b1 = {"method": "B1", "target_index": target_index, "contract": measurement_contract,
                      "noise_scenario": scenario, "initial_indices": p0_sets[0].tolist(),
                      "summary": summarize_random(random_rows), "repeats": random_rows}
                p0 = [run_bo(data, target_index, measurement_contract, scenario, values, "P0", 1100 + target_offset * 100 + set_id * 13 + contract_index * 3 + noise_index)
                      for set_id, values in enumerate(p0_sets)]
                p1 = [run_bo(data, target_index, measurement_contract, scenario, values, "P1", 2100 + target_offset * 100 + set_id * 13 + contract_index * 3 + noise_index)
                      for set_id, values in enumerate(p1_sets)]
                p2 = [run_bo(data, target_index, measurement_contract, scenario, np.asarray(data.train_indices), "P2", 3100 + target_offset * 100 + contract_index * 3 + noise_index)][0]
                def bo_summary(method: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
                    q = [row["queries_to_exact_target"] for row in rows if row["queries_to_exact_target"] is not None]
                    return {"method": method, "contract": measurement_contract, "noise_scenario": scenario,
                            "target_count": len(rows), "hit_count": len(q), "hit_fraction": len(q) / len(rows),
                            "median_queries": float(np.median(q)) if q else None,
                            "p90_queries": float(np.percentile(q, 90)) if q else None,
                            "max_queries": int(max(q)) if q else None}
                for method, rows in (("P0", p0), ("P1", p1), ("P2", [p2])):
                    key = f"{measurement_contract}_{scenario}_{method}_{target_index}"
                    all_results["summary"][key] = bo_summary(method, rows)
                target_block["scenarios"][measurement_contract][scenario] = {"B0": b0, "B1": b1, "P0": p0, "P1": p1, "P2": p2}
                p3 = run_p3(data, target_index, measurement_contract, scenario,
                             4100 + target_offset * 100 + contract_index * 3 + noise_index)
                map_results["targets"].append(p3)
        all_results["targets"].append(target_block)
    for contract_name in CONTRACTS:
        for scenario in NOISE_SCENARIOS:
            rows = [row for row in map_results["targets"] if row["contract"] == contract_name and row["noise_scenario"] == scenario]
            heights = [row["height_abs_error_nm"] for row in rows]; widths = [row["width_abs_error_nm"] for row in rows]
            map_results["summary"][f"{contract_name}_{scenario}"] = {
                "contract": contract_name, "noise_scenario": scenario, "target_count": len(rows),
                "success_count": int(sum(row["within_tolerance"] for row in rows)),
                "success_fraction": float(np.mean([row["within_tolerance"] for row in rows])),
                "p90_height_error_nm": float(np.percentile(heights, 90)),
                "p90_width_error_nm": float(np.percentile(widths, 90)),
                "max_height_error_nm": float(np.max(heights)), "max_width_error_nm": float(np.max(widths)),
            }
    audit_gp = collect_model_audit({"bo": all_results, "maps": map_results})
    for contract_name in CONTRACTS:
        for scenario in NOISE_SCENARIOS:
            b0_rows = [target["scenarios"][contract_name][scenario]["B0"] for target in all_results["targets"]]
            b0_values = [float(row["best_F"]) for row in b0_rows]
            all_results["summary"][f"{contract_name}_{scenario}_B0"] = {
                "method": "B0", "contract": contract_name, "noise_scenario": scenario,
                "target_count": len(b0_rows), "exact_target_hit_count": int(sum(row["exact_target_hit"] for row in b0_rows)),
                "median_best_F": float(np.median(b0_values)), "p90_best_F": float(np.percentile(b0_values, 90)),
                "max_best_F": float(np.max(b0_values)),
            }
            # Aggregate the raw replay rows, rather than taking a median of
            # per-target medians.  This keeps the public query metrics tied to
            # the actual stored traces and makes the 11-target denominator
            # explicit.
            random_rows = []
            for target_block in all_results["targets"]:
                random_rows.extend(target_block["scenarios"][contract_name][scenario]["B1"]["repeats"])
            random_summary = summarize_random(random_rows)
            all_results["summary"][f"{contract_name}_{scenario}_B1"] = {
                "method": "B1", "contract": contract_name, "noise_scenario": scenario,
                "target_count": len(all_results["targets"]), "repeat_count": len(random_rows),
                "run_count": len(random_rows), **random_summary,
            }
            for method in ("P0", "P1", "P2"):
                rows = [row for key, row in all_results["summary"].items()
                        if key.endswith(f"_{method}") is False
                        and row["contract"] == contract_name
                        and row["noise_scenario"] == scenario
                        and row["method"] == method]
                # The target rows contain six P0/P1 starts and one P2 fit;
                # flatten their counts and query statistics from the nested
                # traces so no statistic is reconstructed from rounded rows.
                raw_runs = []
                for target_block in all_results["targets"]:
                    value = target_block["scenarios"][contract_name][scenario][method]
                    raw_runs.extend(value if isinstance(value, list) else [value])
                q = [int(row["queries_to_exact_target"]) for row in raw_runs
                     if row["queries_to_exact_target"] is not None]
                all_results["summary"][f"{contract_name}_{scenario}_{method}"] = {
                    "method": method, "contract": contract_name, "noise_scenario": scenario,
                    "target_count": len(all_results["targets"]), "run_count": len(raw_runs),
                    "hit_count": len(q), "hit_fraction": float(len(q) / max(len(raw_runs), 1)),
                    "median_queries": float(np.median(q)) if q else None,
                    "p90_queries": float(np.percentile(q, 90)) if q else None,
                    "max_queries": int(max(q)) if q else None,
                }
    write_json(OUTCOMES / "BAYESIAN_OPTIMIZATION_REPLAY.json", all_results)
    write_json(OUTCOMES / "MAP_RECOVERY_SUMMARY.json", map_results)
    write_json(OUTCOMES / "OBJECTIVE_GP_MODEL_AUDIT.json", audit_gp)
    (OUTCOMES / "METHOD_COMPARISON.md").write_text(markdown_report(all_results, map_results, audit_gp))
    (OUTCOMES / "SCHNEIDER_METHOD_TRANSLATION.md").write_text(
        "# Schneider-style objective-GP method translation\n\n"
        "本任务将每个给定 synthetic measurement 转换为二维 `(h,w)` 上的标量 negative-log-posterior objective。GP 学习的是 `log10(F+1e-12)`，而不是完整 Maxwell response；expected improvement 在 stored-response replay universe 中选择下一次 oracle query。\n\n"
        "本版本没有 objective derivative observations，也没有运行新 FEM；P0/P1/P2 使用固定 8-start Matérn-5/2 ARD exact GP，P3 在连续二维域上做 posterior-mean MAP。Case141 的 11 个完整点仅作为 external replay targets，不能改写为 Task006 formal blind pass。\n"
    )
    (OUTCOMES / "test_summary_v1.md").write_text(
        "# Task007 test summary v1\n\n"
        "- M0 objective identity audit: pass\n"
        "- Case146 independent checker: run after benchmark generation\n"
        "- New FEM: 0\n"
        "- Task006 model lock/data mutation: false\n"
        "- frozen validation / formal inversion: not accessed / not run\n"
    )
    print(json.dumps({"status": "pass", "outcomes": str(OUTCOMES), "gp_audit": audit_gp}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
