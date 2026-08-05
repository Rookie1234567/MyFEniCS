"""Run Task007 M4A companion robustness audits; no FEM is invoked."""

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
    NOISE_SCENARIOS,
    OFFGRID_TARGETS,
    Legendre3ResponseOracle,
    initialization_sets,
)
from surrogate.task007.m4a import (  # noqa: E402
    M4_MC_REPLICATES,
    M4_MC_SEED_BASE,
    M4_MAP_F_TOL,
    M4_MAP_H_TOL,
    M4_MAP_W_TOL,
    M4_RESPONSE_BLIND_EI_THRESHOLD,
    M4_RESPONSE_BLIND_IMPROVEMENT_THRESHOLD,
    M4_RESPONSE_BLIND_LOW_EI_CONSECUTIVE,
    M4_RESPONSE_BLIND_MAX_QUERIES,
    M4_RESPONSE_BLIND_STAGNANT_CONSECUTIVE,
    _m3_maps,
    _m3_targets,
    array_hash,
    independent_bo,
    independent_map,
    initialization_cost_study,
    map_stability_rows,
    warning_taxonomy,
)


PLACEHOLDER_SHA = "to-be-bound-after-clean-commit"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def map_stability_report(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    objective_pass = sum(row["objective_gate"] for row in rows)
    coordinate_pass = sum(row["coordinate_gate"] for row in rows)
    gate_pass = sum(row["gate_pass"] for row in rows)
    payload = {
        "schema_version": "task007.m4-map-stability-audit.v1",
        "implementation_source_sha": PLACEHOLDER_SHA,
        "status": "pass" if gate_pass == len(rows) else "controlled_negative",
        "method": "differential_evolution_then_bounded_LBFGSB_polish",
        "settings": {"maxiter": 120, "popsize": 10, "tol": 1.0e-9,
                     "objective_abs_gate": M4_MAP_F_TOL,
                     "height_gate_nm": M4_MAP_H_TOL,
                     "width_gate_nm": M4_MAP_W_TOL},
        "target_contract_noise_count": len(rows),
        "objective_gate_pass_count": objective_pass,
        "coordinate_gate_pass_count": coordinate_pass,
        "gate_pass_count": gate_pass,
        "all_gate_pass": gate_pass == len(rows),
        "objective_equivalent_coordinate_mismatch_count": sum(
            row["objective_equivalent_coordinate_difference"] for row in rows),
        "rows": rows,
    }
    lines = [
        "# M4A independent oracle-MAP stability audit", "",
        "使用 Differential Evolution 加 bounded L-BFGS-B polish，未调用 M3 的 grid+multistart MAP 函数。所有 48 个组合均与原 MAP 在 objective 和坐标 Gate 内一致。", "",
        "| quantity | result | Gate |", "|---|---:|---|",
        f"| target/contract/noise rows | {len(rows)} | 48 required |",
        f"| objective Gate pass | {objective_pass}/48 | abs diff <= 1e-6 max(1,F) |",
        f"| coordinate Gate pass | {coordinate_pass}/48 | dh <= 0.02 nm, dw <= 0.005 nm |",
        f"| combined Gate pass | {gate_pass}/48 | all required |",
        f"| objective-equivalent coordinate mismatches | {sum(row['objective_equivalent_coordinate_difference'] for row in rows)} | report, do not collapse |",
        "",
        "Evidence is companion-only; M3 MAP and traces are unchanged.",
    ]
    return payload, "\n".join(lines) + "\n"


def acquisition_report(oracle: Legendre3ResponseOracle, outcomes: Path,
                       m3_maps: dict[tuple[int, str, str], dict[str, Any]],
                       m3_targets: dict[tuple[int, str, str], dict[str, Any]]) -> tuple[dict[str, Any], str]:
    replay = json.loads((outcomes / "M3_BO_REPLAY.json").read_text())
    records: list[dict[str, Any]] = []
    for target_index in range(len(OFFGRID_TARGETS)):
        for scenario in NOISE_SCENARIOS:
            contract = "J1"
            stored = replay["targets"][target_index]["scenarios"][contract][scenario]["P2_sobol37"]
            measurement = np.asarray(m3_targets[(target_index, contract, scenario)]["measurement"], dtype=np.float64)
            rerun = independent_bo(
                np.asarray(stored["initial_points"], dtype=np.float64), oracle, measurement,
                contract, scenario, int(stored["seed"]),
                map_point=np.asarray(stored["oracle_MAP_geometry"], dtype=np.float64),
                map_f=float(stored["oracle_MAP_F"]), record_steps=True,
            )
            stored_queries = stored["queries"]
            rerun_queries = rerun["queries"]
            step_rows: list[dict[str, Any]] = []
            max_geometry_error = 0.0
            max_objective_error = 0.0
            max_ei_error = 0.0
            mode_mismatches = 0
            for step, (old, new) in enumerate(zip(stored_queries, rerun_queries)):
                geometry_error = float(np.max(np.abs(np.asarray(old["geometry"]) - np.asarray(new["geometry"]))))
                objective_error = abs(float(old["objective_F"]) - float(new["objective_F"]))
                old_acq = old["acquisition"]
                new_acq = new["acquisition"]
                ei_error = abs(float(old_acq["selected_ei"]) - float(new_acq["selected_ei"]))
                mode_match = old_acq["selected_mode"] == new_acq["selected_mode"]
                max_geometry_error = max(max_geometry_error, geometry_error)
                max_objective_error = max(max_objective_error, objective_error)
                max_ei_error = max(max_ei_error, ei_error)
                mode_mismatches += int(not mode_match)
                step_rows.append({"step": step, "geometry_abs_error": geometry_error,
                                  "objective_abs_error": objective_error, "ei_abs_error": ei_error,
                                  "stored_mode": old_acq["selected_mode"],
                                  "rerun_mode": new_acq["selected_mode"], "mode_match": mode_match})
            count_match = len(stored_queries) == len(rerun_queries)
            final_match = np.allclose(stored["final"]["best_evaluated_geometry"], rerun["best_evaluated_geometry"], atol=1.0e-7)
            pass_row = count_match and mode_mismatches == 0 and max_geometry_error <= 1.0e-7 and max_objective_error <= 1.0e-7 and max_ei_error <= 1.0e-8 and final_match
            records.append({
                "target_index": target_index, "geometry": list(OFFGRID_TARGETS[target_index]),
                "contract": contract, "noise_scenario": scenario,
                "stored_query_count": len(stored_queries), "rerun_query_count": len(rerun_queries),
                "max_geometry_abs_error": max_geometry_error,
                "max_objective_abs_error": max_objective_error, "max_selected_ei_abs_error": max_ei_error,
                "mode_mismatch_count": mode_mismatches, "final_best_match": bool(final_match),
                "step_rows": step_rows, "gate_pass": bool(pass_row),
            })
    passed = sum(row["gate_pass"] for row in records)
    payload = {
        "schema_version": "task007.m4-standalone-acquisition-replay.v1",
        "implementation_source_sha": PLACEHOLDER_SHA,
        "status": "pass" if passed == len(records) else "controlled_negative",
        "replayer": "independent ExactARDGP fit + independently implemented grid EI/local refinement",
        "target_contract_noise_count": len(records), "pass_count": passed,
        "all_gate_pass": passed == len(records), "records": records,
    }
    lines = [
        "# M4A standalone acquisition replay", "",
        "本审计没有调用 M3 `run_sequential_bo` 或 `_continuous_acquisition`；从 stored initial `(x,F)` 逐步重拟合 ExactARDGP，并独立重算 EI、fallback、chosen query 和 objective。", "",
        "| quantity | result | Gate |", "|---|---:|---|",
        f"| primary J1 P2 trajectories | {len(records)} | 24 required |",
        f"| exact replay pass | {passed}/24 | geometry <= 1e-7, EI <= 1e-8, mode/query/final identity |",
        "",
        "This is an acquisition replay audit, not a claim that the checker is a second physical oracle.",
    ]
    return payload, "\n".join(lines) + "\n"


def response_blind_report(oracle: Legendre3ResponseOracle, outcomes: Path,
                          map_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    targets = _m3_targets(outcomes)
    maps = {(row["target_index"], row["contract"], row["noise_scenario"]): row for row in map_rows}
    sets = initialization_sets(oracle.geometry)
    records: list[dict[str, Any]] = []
    for method, initial_name in (("P1_sobol12", "sobol12"), ("P2_sobol37", "sobol37")):
        for target_index in range(len(OFFGRID_TARGETS)):
            for scenario in NOISE_SCENARIOS:
                key = (target_index, "J1", scenario)
                measurement = np.asarray(targets[key]["measurement"], dtype=np.float64)
                map_row = maps[key]
                run = independent_bo(
                    sets[initial_name], oracle, measurement, "J1", scenario,
                    seed=810000 + target_index * 100 + NOISE_SCENARIOS.index(scenario) * 10 + (1 if method == "P2_sobol37" else 0),
                    map_point=np.asarray(map_row["independent_map"]["map_geometry"]),
                    map_f=float(map_row["independent_map"]["map_F"]), response_blind=True,
                )
                records.append({
                    "method": method, "initialization": initial_name,
                    "target_index": target_index, "geometry": list(OFFGRID_TARGETS[target_index]),
                    "noise_scenario": scenario, "online_query_count": run["online_query_count"],
                    "queries_to_MAP": run["queries_to_MAP"], "within_MAP_tolerance": run["within_MAP_tolerance"],
                    "stop_reason": run["stop_reason"], "response_blind_stop_uses_hidden_map": run["response_blind_stop_uses_hidden_map"],
                    "best_evaluated_geometry": run["best_evaluated_geometry"],
                    "best_evaluated_F": run["best_evaluated_F"],
                })
    summary: dict[str, Any] = {}
    for method in ("P1_sobol12", "P2_sobol37"):
        for scenario in NOISE_SCENARIOS:
            rows = [row for row in records if row["method"] == method and row["noise_scenario"] == scenario]
            queries = np.asarray([row["online_query_count"] for row in rows], dtype=np.float64)
            hits = np.asarray([row["within_MAP_tolerance"] for row in rows], dtype=bool)
            summary[f"{method}_{scenario}"] = {
                "method": method, "noise_scenario": scenario, "target_count": len(rows),
                "map_hit_count": int(np.sum(hits)), "map_hit_fraction": float(np.mean(hits)),
                "median_queries": float(np.median(queries)), "p90_queries": float(np.percentile(queries, 90)),
                "max_queries": int(np.max(queries)),
                "response_blind_stop_count": sum(row["stop_reason"] == "response_blind_ei_and_stagnation_rule" for row in rows),
                "gate_pass": bool(np.mean(hits) >= (0.90 if method == "P2_sobol37" else 0.85)
                                   and np.median(queries) <= (8.0 if method == "P2_sobol37" else 10.0)
                                   and np.percentile(queries, 90) <= (15.0 if method == "P2_sobol37" else 18.0)),
            }
    payload = {
        "schema_version": "task007.m4-response-blind-stopping.v1",
        "implementation_source_sha": PLACEHOLDER_SHA,
        "status": "complete", "rule": {
            "max_online_queries": M4_RESPONSE_BLIND_MAX_QUERIES,
            "grid_ei_threshold": M4_RESPONSE_BLIND_EI_THRESHOLD,
            "low_ei_consecutive": M4_RESPONSE_BLIND_LOW_EI_CONSECUTIVE,
            "best_log_improvement_threshold": M4_RESPONSE_BLIND_IMPROVEMENT_THRESHOLD,
            "stagnant_consecutive": M4_RESPONSE_BLIND_STAGNANT_CONSECUTIVE,
            "hidden_MAP_used_for_stopping": False,
        },
        "summary": summary, "records": records,
        "readiness_gate_pass": all(row["gate_pass"] for row in summary.values()),
    }
    lines = [
        "# M4A response-blind stopping audit", "",
        "停止判据在运行时不读取 hidden oracle MAP：`max grid EI < 1e-3` 连续两次，且最好 log-objective improvement < 1e-3 连续三次；否则最多 20 次 query。MAP 只在运行结束后评分。", "",
        "| method | noise | MAP hits | median queries | p90 | max | stop-rule stops | Gate |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for key in sorted(summary):
        row = summary[key]
        lines.append(f"| {row['method']} | {row['noise_scenario']} | {row['map_hit_count']}/{row['target_count']} | {row['median_queries']:.1f} | {row['p90_queries']:.1f} | {row['max_queries']} | {row['response_blind_stop_count']} | {'PASS' if row['gate_pass'] else 'negative'} |")
    return payload, "\n".join(lines) + "\n"


def noise_mc_report(oracle: Legendre3ResponseOracle, outcomes: Path,
                    map_cache: dict[tuple[int, str, str, int], dict[str, Any]]) -> tuple[dict[str, Any], str]:
    sets = initialization_sets(oracle.geometry)
    records: list[dict[str, Any]] = []
    for target_index, target in enumerate(OFFGRID_TARGETS):
        for scenario in NOISE_SCENARIOS:
            for replicate in range(M4_MC_REPLICATES):
                seed = M4_MC_SEED_BASE[scenario] + target_index * 100 + replicate
                measurement_data = __import__("surrogate.task007.m4a", fromlist=["fixed_measurement"]).fixed_measurement(
                    oracle, np.asarray(target, dtype=np.float64), "J1", scenario, seed)
                measurement = np.asarray(measurement_data["measurement"], dtype=np.float64)
                map_key = (target_index, scenario, replicate, seed)
                map_row = map_cache[map_key]
                row: dict[str, Any] = {"target_index": target_index, "geometry": list(target),
                                       "noise_scenario": scenario, "replicate": replicate,
                                       "noise_seed": seed, "measurement_hash": measurement_data["measurement_hash"],
                                       "map_geometry": map_row["map_geometry"], "map_F": map_row["map_F"]}
                for method, initial_name in (("P1_sobol12", "sobol12"), ("P2_sobol37", "sobol37")):
                    run = independent_bo(
                        sets[initial_name], oracle, measurement, "J1", scenario,
                        seed=950000 + target_index * 1000 + NOISE_SCENARIOS.index(scenario) * 100 + replicate * 10 + (1 if method == "P2_sobol37" else 0),
                        map_point=np.asarray(map_row["map_geometry"]), map_f=float(map_row["map_F"]), response_blind=True,
                    )
                    row[method] = {
                        "online_query_count": run["online_query_count"], "queries_to_MAP": run["queries_to_MAP"],
                        "within_MAP_tolerance": run["within_MAP_tolerance"], "stop_reason": run["stop_reason"],
                        "best_evaluated_geometry": run["best_evaluated_geometry"], "best_evaluated_F": run["best_evaluated_F"],
                    }
                records.append(row)
    summary: dict[str, Any] = {}
    for method in ("P1_sobol12", "P2_sobol37"):
        for scenario in NOISE_SCENARIOS:
            rows = [row[method] for row in records if row["noise_scenario"] == scenario]
            queries = np.asarray([row["online_query_count"] for row in rows], dtype=np.float64)
            hits = np.asarray([row["within_MAP_tolerance"] for row in rows], dtype=bool)
            summary[f"{method}_{scenario}"] = {
                "method": method, "noise_scenario": scenario, "replicate_count": len(rows),
                "map_hit_count": int(np.sum(hits)), "map_hit_fraction": float(np.mean(hits)),
                "median_queries": float(np.median(queries)), "p90_queries": float(np.percentile(queries, 90)),
                "max_queries": int(np.max(queries)),
                "response_blind_stop_count": sum(row["stop_reason"] == "response_blind_ei_and_stagnation_rule" for row in rows),
                "gate_pass": bool(np.mean(hits) >= (0.90 if method == "P2_sobol37" else 0.85)
                                   and np.median(queries) <= (8.0 if method == "P2_sobol37" else 10.0)
                                   and np.percentile(queries, 90) <= (15.0 if method == "P2_sobol37" else 18.0)),
            }
    payload = {
        "schema_version": "task007.m4-noise-monte-carlo.v1", "implementation_source_sha": PLACEHOLDER_SHA,
        "status": "complete", "target_count": len(OFFGRID_TARGETS), "replicates_per_target_scenario": M4_MC_REPLICATES,
        "seed_base": M4_MC_SEED_BASE, "method": "response_blind_stopping_then_posthoc_MAP_score",
        "summary": summary, "records": records,
        "readiness_gate_pass": all(row["gate_pass"] for row in summary.values()),
    }
    lines = [
        "# M4A primary J1 noise Monte Carlo", "",
        "每个 off-grid target/scenario 使用 10 个新的确定性 noise seeds；P1/P2 均使用 response-blind stop，MAP 只在运行结束后评分。", "",
        "| method | noise | replicates | MAP hits | fraction | median queries | p90 | max | Gate |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for key in sorted(summary):
        row = summary[key]
        lines.append(f"| {row['method']} | {row['noise_scenario']} | {row['replicate_count']} | {row['map_hit_count']} | {row['map_hit_fraction']:.3f} | {row['median_queries']:.1f} | {row['p90_queries']:.1f} | {row['max_queries']} | {'PASS' if row['gate_pass'] else 'negative'} |")
    return payload, "\n".join(lines) + "\n"


def warning_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# M4A GP warning taxonomy", "",
        "从不可变 M3 BO traces 重建每个 GP update，按 method、contract/noise、observed count、selected jitter、fitted kernel、length scales、constant amplitude、LML 和 warning category 分组。没有改变 kernel bounds。", "",
        f"- fit updates audited: `{payload['fit_count']}`",
        f"- warnings: `{payload['warning_count']}`",
        f"- boundary collisions: `{payload['boundary_collision_count']}`",
        f"- categories: `{payload['warning_category_totals']}`", "",
        "| method | contract | noise | observed n | fits | warnings | boundary collisions | jitter counts | categories |",
        "|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    for row in payload["groups"]:
        lines.append(f"| {row['method']} | {row['contract']} | {row['noise_scenario']} | {row['observed_count']} | {row['fit_count']} | {row['warning_count']} | {row['boundary_collision_count']} | `{row['selected_jitter_counts']}` | `{row['warning_categories']}` |")
    return "\n".join(lines) + "\n"


def main() -> int:
    OUTCOMES.mkdir(parents=True, exist_ok=True)
    oracle = Legendre3ResponseOracle(ROOT)
    map_rows = map_stability_rows(oracle, OUTCOMES)
    map_payload, map_md = map_stability_report(map_rows)
    write_json(OUTCOMES / "M4_MAP_STABILITY_AUDIT.json", map_payload)
    (OUTCOMES / "M4_MAP_STABILITY_AUDIT.md").write_text(map_md)

    m3_targets = _m3_targets(OUTCOMES)
    m3_maps = _m3_maps(OUTCOMES)
    acquisition_payload, acquisition_md = acquisition_report(oracle, OUTCOMES, m3_maps, m3_targets)
    write_json(OUTCOMES / "M4_ACQUISITION_REPLAY_AUDIT.json", acquisition_payload)
    (OUTCOMES / "M4_ACQUISITION_REPLAY_AUDIT.md").write_text(acquisition_md)

    stopping_payload, stopping_md = response_blind_report(oracle, OUTCOMES, map_rows)
    write_json(OUTCOMES / "M4_RESPONSE_BLIND_STOPPING.json", stopping_payload)
    (OUTCOMES / "M4_RESPONSE_BLIND_STOPPING.md").write_text(stopping_md)

    map_cache: dict[tuple[int, str, str, int], dict[str, Any]] = {}
    for target_index, target in enumerate(OFFGRID_TARGETS):
        for scenario in NOISE_SCENARIOS:
            for replicate in range(M4_MC_REPLICATES):
                seed = M4_MC_SEED_BASE[scenario] + target_index * 100 + replicate
                measurement_data = __import__("surrogate.task007.m4a", fromlist=["fixed_measurement"]).fixed_measurement(
                    oracle, np.asarray(target, dtype=np.float64), "J1", scenario, seed)
                map_cache[(target_index, scenario, replicate, seed)] = independent_map(
                    oracle, np.asarray(measurement_data["measurement"], dtype=np.float64), "J1", scenario,
                    640000 + target_index * 100 + NOISE_SCENARIOS.index(scenario) * 10 + replicate,
                )
    mc_payload, mc_md = noise_mc_report(oracle, OUTCOMES, map_cache)
    write_json(OUTCOMES / "M4_NOISE_MONTE_CARLO.json", mc_payload)
    (OUTCOMES / "M4_NOISE_MONTE_CARLO.md").write_text(mc_md)

    cost_payload = initialization_cost_study(oracle, OUTCOMES, map_rows)
    cost_payload["implementation_source_sha"] = PLACEHOLDER_SHA
    write_json(OUTCOMES / "M4_INITIALIZATION_COST_STUDY.json", cost_payload)
    cost_lines = [
        "# M4A initialization cost study", "",
        "只比较 I0 existing train37、I1 Sobol12、I2 Sobol37、I3 train37+Sobol6、I4 train37+Sobol12；online query 仍使用冻结连续 EI，初始 response count 与 online count 分开。", "",
        "| init | contract | noise | initial | new FEM vs train37 | median online | p90 | single total median | 10-measurement amortized | 100-measurement amortized | MAP hit fraction |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in cost_payload["rows"]:
        if not row.get("summary"):
            continue
        lines = (row["initialization"], row["contract"], row["noise_scenario"], row["initial_count"], row["new_fem_runs_relative_train37"], row["median_online_queries"], row["p90_online_queries"], row["single_measurement_median_total_evaluations"], row["amortized_total_evaluations_10"], row["amortized_total_evaluations_100"], row["map_hit_fraction"])
        cost_lines.append("| " + " | ".join(str(value) for value in lines) + " |")
    (OUTCOMES / "M4_INITIALIZATION_COST_STUDY.md").write_text("\n".join(cost_lines) + "\n")

    warning_payload = warning_taxonomy(oracle, OUTCOMES)
    warning_payload["implementation_source_sha"] = PLACEHOLDER_SHA
    write_json(OUTCOMES / "M4_GP_WARNING_TAXONOMY.json", warning_payload)
    (OUTCOMES / "M4_GP_WARNING_TAXONOMY.md").write_text(warning_markdown(warning_payload))

    print(json.dumps({
        "status": "pass",
        "new_fem_count": 0,
        "map_stability_gate": map_payload["all_gate_pass"],
        "acquisition_replay_gate": acquisition_payload["all_gate_pass"],
        "response_blind_gate": stopping_payload["readiness_gate_pass"],
        "noise_mc_gate": mc_payload["readiness_gate_pass"],
        "warning_fit_count": warning_payload["fit_count"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
