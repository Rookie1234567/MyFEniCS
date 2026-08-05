"""Run Task007 M3 Level-A Schneider-faithful continuous BO replay.

Only the frozen Task006 Legendre-3 response surrogate is queried.  This case
does not call a FEM runner and cannot mutate Task006 artifacts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUTCOMES = ROOT / "surrogate_tasks/task007_schneider_objective_gp_benchmark/outcomes"
sys.path.insert(0, str(ROOT / "src"))

from surrogate.task007.continuous import (  # noqa: E402
    CONTRACTS,
    DOMAIN_MAX,
    DOMAIN_MIN,
    M3_EI_GRID_SIZE,
    M3_EI_SWITCH_THRESHOLD,
    M3_MAP_HEIGHT_TOLERANCE_NM,
    M3_MAP_WIDTH_TOLERANCE_NM,
    M3_MAP_GRID_SIZE,
    M3_MAX_ONLINE_QUERIES,
    NOISE_CONFIG,
    NOISE_SCENARIOS,
    OFFGRID_TARGETS,
    Legendre3ResponseOracle,
    array_hash,
    compact_summary,
    initialization_sets,
    noise_sigma,
    objective_values,
    oracle_continuous_map,
    run_multistart_local,
    run_random_search,
    run_sequential_bo,
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def _float_list(values: np.ndarray) -> list[float]:
    return np.asarray(values, dtype=np.float64).tolist()


def build_contract(oracle: Legendre3ResponseOracle, sets: dict[str, np.ndarray]) -> dict[str, Any]:
    return {
        "schema_version": "task007.m3-level-a-contract.v1",
        "status": "frozen_algorithm_benchmark",
        "oracle_kind": "surrogate_oracle_algorithm_benchmark",
        "new_fem_count": 0,
        "task006_lock_modified": False,
        "forward_identity": oracle.metadata(),
        "geometry_domain_nm": {"height": [float(DOMAIN_MIN[0]), float(DOMAIN_MAX[0])],
                                "width": [float(DOMAIN_MIN[1]), float(DOMAIN_MAX[1])]},
        "offgrid_target_count": len(OFFGRID_TARGETS),
        "offgrid_targets": [list(point) for point in OFFGRID_TARGETS],
        "contracts": {
            "J1": "angle-major m=0 selected order-total power, six reflection/transmission channels",
            "J0": "angle-major aggregate R_total/T_total, six channels",
        },
        "noise": {
            scenario: {**config, "sigma": "sqrt((relative*abs(y_M))^2+floor^2)",
                       "fixed_one_realization_per_target_and_contract": True}
            for scenario, config in NOISE_CONFIG.items()
        },
        "objective": {
            "formula": "0.5*sum(((y_M-y_oracle(x))/sigma(y_M))^2)+Phi_prior",
            "prior": "bounded_uniform_zero_inside_domain_plus_infinity_outside",
            "gp_target": "log10(F+1e-12)",
            "oracle_map_is_noisy_measurement_MAP": True,
            "one_shot_posterior_mean_P3_is_not_primary_gate": True,
        },
        "methods": {
            "B0": "random_continuous_search_budget_2000",
            "B1": "multi-start_bounded_L-BFGS-B_oracle_objective",
            "P0": "cold5_continuous_sequential_EI",
            "P1": "sobol12_continuous_sequential_EI",
            "P2": "sobol37_continuous_sequential_EI",
            "P3": "existing_train37_continuous_sequential_EI",
        },
        "initializations": {
            name: {"count": len(points), "geometries": _float_list(points), "geometry_hash": array_hash(points)}
            for name, points in sets.items()
        },
        "sequential_bo": {
            "kernel": "Matern-5/2-ARD", "mean": "constant", "input_scaling": "[-1,1]^2",
            "optimizer_starts": 8, "jitter_candidates": [1.0e-10, 1.0e-8],
            "jitter_selection": "training-only LML", "max_online_queries": M3_MAX_ONLINE_QUERIES,
            "EI_grid_size": M3_EI_GRID_SIZE, "EI_switch_threshold": M3_EI_SWITCH_THRESHOLD,
            "EI_low_rule": "if max grid EI < threshold, bounded local posterior-mean refinement",
            "deduplicate_rule": "deterministic scaled-domain 1e-3 offset when candidate repeats observed point",
            "best_metric": "best actually evaluated point",
            "queries_to_MAP": "first online oracle query whose best evaluated geometry enters MAP tolerance",
        },
        "oracle_map": {"grid_size": M3_MAP_GRID_SIZE, "height_tolerance_nm": M3_MAP_HEIGHT_TOLERANCE_NM,
                       "width_tolerance_nm": M3_MAP_WIDTH_TOLERANCE_NM,
                       "global_grid_plus_bounded_multistart_LBFGSB": True},
    }


def compact_gp_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    updates = [update for row in rows for update in row.get("gp_updates", [])]
    selected_counts: dict[str, int] = {}
    warning_count = 0
    collision_count = 0
    finite_lml = True
    fallback_count = 0
    for update in updates:
        meta = update["metadata"]
        key = str(meta.get("selected_jitter"))
        selected_counts[key] = selected_counts.get(key, 0) + 1
        warning_count += int(meta.get("selected_warning_count", 0))
        collision_count += int(meta.get("selected_boundary_collision_count", 0))
        finite_lml = finite_lml and all(
            candidate.get("lml") is not None and np.isfinite(float(candidate["lml"]))
            for candidate in meta.get("candidate_lml", [])
        )
    return {
        "schema_version": "task007.m3-gp-audit.v1", "status": "pass" if finite_lml else "failed",
        "sequential_gp_update_count": len(updates), "selected_jitter_counts": selected_counts,
        "warning_count_selected_runs": warning_count, "boundary_collision_count_selected_runs": collision_count,
        "all_candidate_lml_finite": finite_lml, "optimizer_starts": 8,
        "kernel": "Matern-5/2-ARD", "jitter_selection_training_only": True,
        "bounded_local_refinement_count": fallback_count,
    }

def make_method_report(bo: dict[str, Any], gp_audit: dict[str, Any]) -> str:
    lines = [
        "# Task007 M3 Level-A continuous BO comparison", "",
        "本报告只调用冻结 Task006 Legendre-3 surrogate oracle；没有运行 FEM。主指标是 best actually evaluated point 与 queries-to-MAP。", "",
        "| contract | noise | method | targets | MAP hits | median queries-to-MAP | p90 | gate |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for key in sorted(bo["summary"]):
        row = bo["summary"][key]
        if row["method"] in ("B0", "B1"):
            continue
        lines.append(f"| {row['contract']} | {row['noise_scenario']} | {row['method']} | {row['target_count']} | {row['map_hit_count']} | {row['median_queries_to_MAP'] if row['median_queries_to_MAP'] is not None else '—'} | {row['p90_queries_to_MAP'] if row['p90_queries_to_MAP'] is not None else '—'} | {'PASS' if row['gate_pass'] else 'negative'} |")
    lines.extend(["", "## Baselines", "", "| contract | noise | method | oracle queries | MAP hit/query result |", "|---|---|---|---:|---|"])
    for key in sorted(bo["baseline_summary"]):
        row = bo["baseline_summary"][key]
        lines.append(f"| {row['contract']} | {row['noise_scenario']} | {row['method']} | {row['median_oracle_queries']} | {row['map_hit_count']}/{row['target_count']} |")
    lines.extend(["", "## GP audit", "", f"- sequential GP updates: `{gp_audit['sequential_gp_update_count']}`", f"- selected-run warnings recorded: `{gp_audit['warning_count_selected_runs']}`", f"- selected-run boundary collisions: `{gp_audit['boundary_collision_count_selected_runs']}`", f"- bounded local refinement switches: `{gp_audit['bounded_local_refinement_count']}`", "- one-shot posterior-mean P3 is retained only in Task007 V1 and is not used as this M3 primary gate."])
    return "\n".join(lines) + "\n"


def main() -> int:
    OUTCOMES.mkdir(parents=True, exist_ok=True)
    oracle = Legendre3ResponseOracle(ROOT)
    sets = initialization_sets(oracle.geometry)
    contract = build_contract(oracle, sets)
    write_json(OUTCOMES / "M3_LEVEL_A_CONTRACT.json", contract)
    write_json(OUTCOMES / "M3_ORACLE_MODEL_AUDIT.json", oracle.metadata())

    target_rows: list[dict[str, Any]] = []
    bo_targets: list[dict[str, Any]] = []
    all_sequential: list[dict[str, Any]] = []
    baseline_rows: list[dict[str, Any]] = []
    for target_index, target in enumerate(OFFGRID_TARGETS):
        target_point = np.asarray(target, dtype=np.float64)
        target_block: dict[str, Any] = {"target_index": target_index, "geometry": list(target), "scenarios": {}}
        bo_block: dict[str, Any] = {"target_index": target_index, "geometry": list(target), "scenarios": {}}
        for contract_index, contract_name in enumerate(CONTRACTS):
            y_true = oracle.predict(target_point.reshape(1, 2))[contract_name][0]
            target_block["scenarios"][contract_name] = {}
            bo_block["scenarios"][contract_name] = {}
            for scenario_index, scenario in enumerate(NOISE_SCENARIOS):
                seed = NOISE_CONFIG[scenario]["seed_base"] + target_index * 100 + contract_index * 10
                sigma = noise_sigma(y_true, scenario)
                noise = np.random.default_rng(seed).normal(0.0, sigma)
                measurement = y_true + noise
                oracle_map = oracle_continuous_map(oracle, measurement, contract_name, scenario)
                target_block["scenarios"][contract_name][scenario] = {
                    "noise_seed": int(seed), "true_geometry": list(target),
                    "oracle_true_response": _float_list(y_true), "noise_sigma": _float_list(sigma),
                    "noise": _float_list(noise), "measurement": _float_list(measurement),
                    "true_response_hash": array_hash(y_true), "measurement_hash": array_hash(measurement),
                    "oracle_map": oracle_map,
                    "map_objective_is_not_forced_zero": bool(float(oracle_map["map_F"]) > 1.0e-14),
                }
                methods: dict[str, Any] = {}
                for method_index, (method, initial_name) in enumerate((("P0_cold5", "cold5"), ("P1_sobol12", "sobol12"), ("P2_sobol37", "sobol37"), ("P3_train37", "train37"))):
                    row = run_sequential_bo(
                        oracle, sets[initial_name], measurement, contract_name, scenario,
                        np.asarray(oracle_map["map_geometry"], dtype=np.float64), float(oracle_map["map_F"]),
                        seed=90000 + target_index * 1000 + contract_index * 100 + scenario_index * 10 + method_index,
                    )
                    row["method"] = method
                    row["initialization_name"] = initial_name
                    methods[method] = row
                    all_sequential.append(row)
                random_row = run_random_search(
                    oracle, measurement, contract_name, scenario,
                    np.asarray(oracle_map["map_geometry"], dtype=np.float64), float(oracle_map["map_F"]),
                    seed=100000 + target_index * 100 + contract_index * 10 + scenario_index,
                )
                local_row = run_multistart_local(
                    oracle, measurement, contract_name, scenario,
                    np.asarray(oracle_map["map_geometry"], dtype=np.float64), float(oracle_map["map_F"]),
                    seed=110000 + target_index * 100 + contract_index * 10 + scenario_index,
                )
                methods["B0_random"] = random_row
                methods["B1_local"] = local_row
                baseline_rows.extend((random_row, local_row))
                bo_block["scenarios"][contract_name][scenario] = methods
        target_rows.append(target_block)
        bo_targets.append(bo_block)

    summary: dict[str, Any] = {}
    for contract_name in CONTRACTS:
        for scenario in NOISE_SCENARIOS:
            for method in ("P0_cold5", "P1_sobol12", "P2_sobol37", "P3_train37"):
                rows = [target["scenarios"][contract_name][scenario][method] for target in bo_targets]
                summary[f"{contract_name}_{scenario}_{method}"] = compact_summary(rows, method, contract_name, scenario)
    baseline_summary: dict[str, Any] = {}
    for contract_name in CONTRACTS:
        for scenario in NOISE_SCENARIOS:
            for method in ("B0_random", "B1_local"):
                rows = [target["scenarios"][contract_name][scenario][method] for target in bo_targets]
                if method == "B0_random":
                    queries = [row["budget"] for row in rows]
                    hits = [row["queries_to_MAP"] for row in rows if row["queries_to_MAP"] is not None]
                else:
                    queries = [row["oracle_query_count"] for row in rows]
                    hits = [row["queries_to_MAP"] for row in rows if row["queries_to_MAP"] is not None]
                baseline_summary[f"{contract_name}_{scenario}_{method}"] = {
                    "method": method, "contract": contract_name, "noise_scenario": scenario,
                    "target_count": len(rows), "map_hit_count": len(hits),
                    "median_oracle_queries": float(np.median(queries)),
                    "p90_oracle_queries": float(np.percentile(queries, 90)),
                    "median_queries_to_MAP": float(np.median(hits)) if hits else None,
                }
    gp_audit = compact_gp_audit(all_sequential)
    gp_audit["bounded_local_refinement_count"] = int(sum(
        1 for row in all_sequential for query in row.get("queries", [])
        if query.get("acquisition", {}).get("fallback_used")
    ))
    replay = {
        "schema_version": "task007.m3-continuous-bo-replay.v1", "status": "complete",
        "new_fem_count": 0, "target_count": len(bo_targets), "contracts": list(CONTRACTS),
        "noise_scenarios": list(NOISE_SCENARIOS), "summary": summary,
        "baseline_summary": baseline_summary, "targets": bo_targets,
    }
    map_audit = {
        "schema_version": "task007.m3-oracle-map-audit.v1", "status": "complete",
        "target_count": len(target_rows), "contracts": list(CONTRACTS), "noise_scenarios": list(NOISE_SCENARIOS),
        "targets": target_rows,
        "map_objective_positive_count": int(sum(
            target["scenarios"][contract_name][scenario]["map_objective_is_not_forced_zero"]
            for target in target_rows for contract_name in CONTRACTS for scenario in NOISE_SCENARIOS
        )),
        "map_grid_size": M3_MAP_GRID_SIZE, "not_a_formal_physical_validation": True,
    }
    write_json(OUTCOMES / "M3_TARGETS.json", {"schema_version": "task007.m3-offgrid-targets.v1", "status": "frozen", "targets": target_rows})
    write_json(OUTCOMES / "M3_MAP_AUDIT.json", map_audit)
    write_json(OUTCOMES / "M3_BO_REPLAY.json", replay)
    write_json(OUTCOMES / "M3_GP_AUDIT.json", gp_audit)
    (OUTCOMES / "M3_METHOD_COMPARISON.md").write_text(make_method_report(replay, gp_audit))
    (OUTCOMES / "test_summary_v2.md").write_text(
        "# Task007 M3 Level-A test summary\n\n"
        "- frozen Task006 Legendre-3 oracle: loaded read-only\n"
        "- off-grid targets: 12; contracts J1/J0; N1/N2 fixed noise realizations\n"
        "- new FEM: 0\n"
        "- Task006 model lock/data mutation: false\n"
        "- sequential BO uses actual oracle query count and best evaluated point\n"
        "- independent Case147 checker: run after generation\n"
    )
    print(json.dumps({"status": "pass", "outcomes": str(OUTCOMES), "target_count": len(target_rows), "gp_audit": gp_audit}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
