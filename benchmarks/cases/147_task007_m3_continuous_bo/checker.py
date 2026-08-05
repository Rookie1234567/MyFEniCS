"""Independent Case147 checker for M3 Level-A continuous BO replay."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUTCOMES = ROOT / "surrogate_tasks/task007_schneider_objective_gp_benchmark/outcomes"
RECORD = Path(__file__).resolve().parent / "records/case147_check.json"
IDENTITY = OUTCOMES / "M3_IMPLEMENTATION_IDENTITY.json"
sys.path.insert(0, str(ROOT / "src"))

from surrogate.task007.continuous import (  # noqa: E402
    CONTRACTS,
    DOMAIN_MAX,
    DOMAIN_MIN,
    M3_MAX_ONLINE_QUERIES,
    M3_MAP_HEIGHT_TOLERANCE_NM,
    M3_MAP_WIDTH_TOLERANCE_NM,
    NOISE_CONFIG,
    NOISE_SCENARIOS,
    OFFGRID_TARGETS,
    TASK006_LOCK_SHA256,
    TASK006_MANIFEST_SHA256,
    Legendre3ResponseOracle,
    array_hash,
    file_sha256,
    initialization_sets,
    noise_sigma,
    objective_scalar,
    objective_values,
    within_map_tolerance,
)


def close(actual: Any, expected: Any, atol: float = 1.0e-8) -> bool:
    return bool(np.isclose(float(actual), float(expected), rtol=1.0e-7, atol=atol))


def add(checks: dict[str, bool], name: str, value: bool) -> None:
    checks[name] = bool(value)


def main() -> int:
    checks: dict[str, bool] = {}
    implementation_source_sha = "unbound"
    try:
        identity = json.loads(IDENTITY.read_text())
        implementation_source_sha = str(identity["implementation_source_sha"])
        add(checks, "implementation_identity_present", bool(implementation_source_sha) and implementation_source_sha != "unbound")
        for relative_path, expected_hash in identity.get("source_files", {}).items():
            add(checks, f"source_hash_{relative_path}", file_sha256(ROOT / relative_path) == expected_hash)
        oracle = Legendre3ResponseOracle(ROOT)
        contract = json.loads((OUTCOMES / "M3_LEVEL_A_CONTRACT.json").read_text())
        targets = json.loads((OUTCOMES / "M3_TARGETS.json").read_text())
        maps = json.loads((OUTCOMES / "M3_MAP_AUDIT.json").read_text())
        replay = json.loads((OUTCOMES / "M3_BO_REPLAY.json").read_text())
        gp_audit = json.loads((OUTCOMES / "M3_GP_AUDIT.json").read_text())
        sets = initialization_sets(oracle.geometry)

        for name, artifact in (("contract", contract), ("targets", targets), ("maps", maps),
                               ("replay", replay), ("gp_audit", gp_audit)):
            add(checks, f"{name}_implementation_sha", artifact.get("implementation_source_sha") == implementation_source_sha)

        add(checks, "task006_lock_hash_unchanged", oracle.lock_sha256 == TASK006_LOCK_SHA256)
        add(checks, "task006_manifest_hash_unchanged", oracle.metadata()["dataset_manifest_sha256"] == TASK006_MANIFEST_SHA256)
        add(checks, "task006_candidate_legendre3", oracle.metadata()["candidate"] == "legendre_3")
        add(checks, "new_fem_zero", contract.get("new_fem_count") == 0 and replay.get("new_fem_count") == 0)
        add(checks, "task006_lock_not_modified", contract.get("task006_lock_modified") is False and oracle.metadata()["task006_lock_modified"] is False)
        add(checks, "target_count_12", len(targets.get("targets", [])) == 12 and replay.get("target_count") == 12)
        add(checks, "target_tuple_exact", [row["geometry"] for row in targets["targets"]] == [list(row) for row in OFFGRID_TARGETS])
        add(checks, "target_offgrid", all(not np.any(np.all(np.isclose(oracle.geometry, row), axis=1)) for row in OFFGRID_TARGETS))
        add(checks, "all_map_objectives_positive", maps.get("map_objective_positive_count") == 48)

        for target_index, target in enumerate(targets["targets"]):
            point = np.asarray(target["geometry"], dtype=np.float64)
            for contract_name in CONTRACTS:
                true_response = oracle.predict(point.reshape(1, 2))[contract_name][0]
                for scenario in NOISE_SCENARIOS:
                    row = target["scenarios"][contract_name][scenario]
                    seed = NOISE_CONFIG[scenario]["seed_base"] + target_index * 100 + CONTRACTS.index(contract_name) * 10
                    sigma = noise_sigma(true_response, scenario)
                    noise = np.random.default_rng(seed).normal(0.0, sigma)
                    measurement = true_response + noise
                    prefix = f"target_{target_index}_{contract_name}_{scenario}"
                    add(checks, f"{prefix}_true_hash", row["true_response_hash"] == array_hash(true_response))
                    add(checks, f"{prefix}_measurement_hash", row["measurement_hash"] == array_hash(measurement))
                    add(checks, f"{prefix}_seed", int(row["noise_seed"]) == seed)
                    map_row = row["oracle_map"]
                    map_point = np.asarray(map_row["map_geometry"], dtype=np.float64)
                    map_f = objective_scalar(oracle, map_point, measurement, contract_name, scenario)
                    add(checks, f"{prefix}_map_objective_recomputed", close(map_f, map_row["map_F"], atol=1.0e-7))
                    add(checks, f"{prefix}_map_in_domain", bool(np.all(map_point >= DOMAIN_MIN) and np.all(map_point <= DOMAIN_MAX)))
                    add(checks, f"{prefix}_map_positive", map_f > 1.0e-14)

                    block = replay["targets"][target_index]["scenarios"][contract_name][scenario]
                    for method in ("P0_cold5", "P1_sobol12", "P2_sobol37", "P3_train37"):
                        run = block[method]
                        initial = np.asarray(run["initial_points"], dtype=np.float64)
                        expected_initial = sets[run["initialization_name"]]
                        add(checks, f"{prefix}_{method}_initial_identity", initial.shape == expected_initial.shape and np.allclose(initial, expected_initial))
                        add(checks, f"{prefix}_{method}_target_not_initial", not np.any(np.all(np.isclose(initial, point), axis=1)))
                        initial_truth = objective_values(oracle, initial, measurement, contract_name, scenario)
                        add(checks, f"{prefix}_{method}_initial_objective", np.allclose(initial_truth, np.asarray(run["initial_objective_F"]), rtol=1.0e-8, atol=1.0e-10))
                        observed = initial.copy()
                        values = initial_truth.copy()
                        query_rows = run.get("queries", [])
                        add(checks, f"{prefix}_{method}_query_budget", len(query_rows) <= M3_MAX_ONLINE_QUERIES)
                        for step, query in enumerate(query_rows):
                            qpoint = np.asarray(query["geometry"], dtype=np.float64)
                            qvalue = objective_scalar(oracle, qpoint, measurement, contract_name, scenario)
                            add(checks, f"{prefix}_{method}_query_{step}_step", int(query["query_step"]) == step)
                            add(checks, f"{prefix}_{method}_query_{step}_domain", bool(np.all(qpoint >= DOMAIN_MIN) and np.all(qpoint <= DOMAIN_MAX)))
                            add(checks, f"{prefix}_{method}_query_{step}_value", close(qvalue, query["objective_F"], atol=1.0e-7))
                            observed = np.vstack((observed, qpoint))
                            values = np.append(values, qvalue)
                        best_index = int(np.argmin(values))
                        final = run["final"]
                        add(checks, f"{prefix}_{method}_final_best", np.allclose(observed[best_index], final["best_evaluated_geometry"], atol=1.0e-7) and close(values[best_index], final["best_evaluated_F"], atol=1.0e-7))
                        hit_steps = [int(row["online_query_count"]) for row in run["history"] if row["within_MAP_tolerance"]]
                        expected_q = hit_steps[0] if hit_steps else None
                        add(checks, f"{prefix}_{method}_query_to_map", run.get("queries_to_MAP") == expected_q)
                        add(checks, f"{prefix}_{method}_history_length", len(run["history"]) == len(query_rows) + 1)
                        add(checks, f"{prefix}_{method}_gp_update_count", len(run.get("gp_updates", [])) == len(query_rows))
                        for gp_update in run.get("gp_updates", []):
                            meta = gp_update["metadata"]
                            add(checks, f"{prefix}_{method}_gp_{gp_update['query_step']}_starts", meta.get("optimizer_starts") == 8)
                            add(checks, f"{prefix}_{method}_gp_{gp_update['query_step']}_lml", all(item.get("lml") is not None and np.isfinite(float(item["lml"])) for item in meta.get("candidate_lml", [])))
                    for baseline_name in ("B0_random", "B1_local"):
                        baseline = block[baseline_name]
                        baseline_f = baseline.get("best_evaluated_F", baseline.get("optimizer_selected_F"))
                        add(checks, f"{prefix}_{baseline_name}_finite", baseline_f is not None and np.isfinite(float(baseline_f)))
                        if baseline_name == "B1_local":
                            evaluations = baseline["evaluations"]
                            add(checks, f"{prefix}_{baseline_name}_query_count", int(baseline["oracle_query_count"]) == len(evaluations))
                            for eval_index, eval_row in enumerate(evaluations):
                                eval_point = np.asarray(eval_row[:2], dtype=np.float64)
                                eval_value = objective_scalar(oracle, eval_point, measurement, contract_name, scenario)
                                add(checks, f"{prefix}_{baseline_name}_value_{eval_index}", close(eval_value, eval_row[2], atol=1.0e-7))

        add(checks, "gp_audit_lml_finite", gp_audit.get("all_candidate_lml_finite") is True)
        add(checks, "gp_audit_training_only_jitter", gp_audit.get("jitter_selection_training_only") is True)
        add(checks, "gp_audit_warning_count_present", int(gp_audit.get("warning_count_selected_runs", 0)) > 0)
        primary = replay["summary"]["J1_N1_P2_sobol37"]
        add(checks, "primary_gate_matches_contract", primary.get("map_hit_count") >= 11 and primary.get("median_queries_to_MAP") <= 8.0 and primary.get("all_hits_within_20") is True)
        qualification = {
            "primary_contract": "J1",
            "N1": replay["summary"]["J1_N1_P2_sobol37"],
            "N2": replay["summary"]["J1_N2_P2_sobol37"],
            "train37_vs_sobol37": {
                "J1_N1": {"train37": replay["summary"]["J1_N1_P3_train37"], "sobol37": replay["summary"]["J1_N1_P2_sobol37"]},
                "J1_N2": {"train37": replay["summary"]["J1_N2_P3_train37"], "sobol37": replay["summary"]["J1_N2_P2_sobol37"]},
            },
            "status": "pass" if checks.get("primary_gate_matches_contract") else "controlled_negative",
            "note": "This is an algorithm-oracle qualification only; it cannot qualify a physical FEM surrogate or overturn Task007 V1 P3 evidence.",
        }
        result = {
            "schema_version": "task007.case147-m3-check.v1", "status": "pass" if all(checks.values()) else "failed",
            "implementation_source_sha": implementation_source_sha,
            "checks": checks, "errors": [name for name, value in checks.items() if not value],
            "qualification": qualification, "new_fem_count": 0,
            "task006_lock_modified": False, "task006_failed_points_retried": False,
        }
    except Exception as exc:
        result = {"schema_version": "task007.case147-m3-check.v1", "status": "failed",
                  "implementation_source_sha": implementation_source_sha,
                  "checks": checks, "errors": [f"exception: {type(exc).__name__}: {exc}"],
                  "qualification": {"status": "checker_error"}, "new_fem_count": 0}
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
