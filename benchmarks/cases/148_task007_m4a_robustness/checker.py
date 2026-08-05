"""Independent Case148 checker for Task007 M4A companion evidence."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUTCOMES = ROOT / "surrogate_tasks/task007_schneider_objective_gp_benchmark/outcomes"
IDENTITY = OUTCOMES / "M4_IMPLEMENTATION_IDENTITY.json"
RECORD = Path(__file__).resolve().parent / "records/case148_check.json"
sys.path.insert(0, str(ROOT / "src"))

from surrogate.task007.continuous import (  # noqa: E402
    CONTRACTS,
    DOMAIN_MAX,
    DOMAIN_MIN,
    NOISE_CONFIG,
    NOISE_SCENARIOS,
    OFFGRID_TARGETS,
    Legendre3ResponseOracle,
    TASK006_MANIFEST_SHA256,
    TASK006_LOCK_SHA256,
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def array_hash(value: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(value, dtype=np.float64))
    descriptor = json.dumps({"dtype": str(array.dtype), "shape": list(array.shape)},
                            sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(descriptor + array.tobytes(order="C")).hexdigest()


def noise_sigma(values: np.ndarray, scenario: str) -> np.ndarray:
    config = NOISE_CONFIG[scenario]
    return np.sqrt((config["relative"] * np.abs(values)) ** 2 + config["floor"] ** 2)


def add(checks: dict[str, bool], name: str, value: bool) -> None:
    checks[name] = bool(value)


def close(actual: float, expected: float, atol: float = 1.0e-10) -> bool:
    return bool(np.isclose(float(actual), float(expected), rtol=1.0e-7, atol=atol))


def recompute_summary(records: list[dict[str, Any]], method: str, scenario: str) -> dict[str, Any]:
    rows = [row[method] for row in records if row["noise_scenario"] == scenario]
    queries = np.asarray([row["online_query_count"] for row in rows], dtype=np.float64)
    hits = np.asarray([row["within_MAP_tolerance"] for row in rows], dtype=bool)
    return {
        "replicate_count": len(rows), "map_hit_count": int(np.sum(hits)),
        "map_hit_fraction": float(np.mean(hits)), "median_queries": float(np.median(queries)),
        "p90_queries": float(np.percentile(queries, 90)), "max_queries": int(np.max(queries)),
        "response_blind_stop_count": sum(row["stop_reason"] == "response_blind_ei_and_stagnation_rule" for row in rows),
    }


def recompute_stopping_summary(records: list[dict[str, Any]], method: str, scenario: str) -> dict[str, Any]:
    rows = [row for row in records if row["method"] == method and row["noise_scenario"] == scenario]
    queries = np.asarray([row["online_query_count"] for row in rows], dtype=np.float64)
    hits = np.asarray([row["within_MAP_tolerance"] for row in rows], dtype=bool)
    return {
        "target_count": len(rows), "map_hit_count": int(np.sum(hits)),
        "map_hit_fraction": float(np.mean(hits)), "median_queries": float(np.median(queries)),
        "p90_queries": float(np.percentile(queries, 90)), "max_queries": int(np.max(queries)),
        "response_blind_stop_count": sum(row["stop_reason"] == "response_blind_ei_and_stagnation_rule" for row in rows),
    }


def main() -> int:
    checks: dict[str, bool] = {}
    implementation_source_sha = "unbound"
    try:
        identity = json.loads(IDENTITY.read_text())
        implementation_source_sha = str(identity["implementation_source_sha"])
        add(checks, "implementation_identity_present", implementation_source_sha not in ("", "unbound", "to-be-bound-after-clean-commit"))
        for relative, expected in identity.get("source_files", {}).items():
            add(checks, f"source_hash_{relative}", file_sha256(ROOT / relative) == expected)
        oracle = Legendre3ResponseOracle(ROOT)
        add(checks, "task006_lock_hash_unchanged", oracle.lock_sha256 == TASK006_LOCK_SHA256)
        add(checks, "task006_manifest_hash_unchanged", oracle.metadata()["dataset_manifest_sha256"] == TASK006_MANIFEST_SHA256)
        add(checks, "new_fem_zero", identity.get("new_fem_count") == 0)
        add(checks, "task006_lock_not_modified", identity.get("task006_lock_modified") is False)

        names = ["M4_MAP_STABILITY_AUDIT", "M4_ACQUISITION_REPLAY_AUDIT", "M4_RESPONSE_BLIND_STOPPING",
                 "M4_NOISE_MONTE_CARLO", "M4_INITIALIZATION_COST_STUDY", "M4_GP_WARNING_TAXONOMY"]
        artifacts = {name: json.loads((OUTCOMES / f"{name}.json").read_text()) for name in names}
        for name, artifact in artifacts.items():
            add(checks, f"{name}_implementation_sha", artifact.get("implementation_source_sha") == implementation_source_sha)

        # The M3 identity/response artifacts are hash-bound and must remain frozen.
        for relative, expected in identity.get("frozen_m3_artifacts", {}).items():
            add(checks, f"frozen_m3_{relative}", file_sha256(ROOT / relative) == expected)

        maps = artifacts["M4_MAP_STABILITY_AUDIT"]
        add(checks, "map_row_count_48", len(maps.get("rows", [])) == 48)
        add(checks, "map_all_gate_pass", maps.get("all_gate_pass") is True and maps.get("gate_pass_count") == 48)
        add(checks, "map_domain", all(np.all(np.asarray(row["independent_map"]["map_geometry"]) >= DOMAIN_MIN)
                                       and np.all(np.asarray(row["independent_map"]["map_geometry"]) <= DOMAIN_MAX)
                                       for row in maps["rows"]))

        acquisition = artifacts["M4_ACQUISITION_REPLAY_AUDIT"]
        add(checks, "acquisition_row_count_24", len(acquisition.get("records", [])) == 24)
        add(checks, "acquisition_all_gate_pass", acquisition.get("all_gate_pass") is True and acquisition.get("pass_count") == 24)
        add(checks, "acquisition_target_coverage", sorted((row["target_index"], row["noise_scenario"]) for row in acquisition["records"]) == sorted((i, s) for i in range(12) for s in NOISE_SCENARIOS))

        stopping = artifacts["M4_RESPONSE_BLIND_STOPPING"]
        stop_records = stopping["records"]
        add(checks, "response_blind_record_count_48", len(stop_records) == 48)
        add(checks, "response_blind_no_hidden_map", all(row["response_blind_stop_uses_hidden_map"] is False for row in stop_records)
            and stopping["rule"]["hidden_MAP_used_for_stopping"] is False)
        add(checks, "response_blind_query_budget", all(0 <= int(row["online_query_count"]) <= 20 for row in stop_records))
        for method in ("P1_sobol12", "P2_sobol37"):
            for scenario in NOISE_SCENARIOS:
                key = f"{method}_{scenario}"
                recomputed = recompute_stopping_summary(stop_records, method, scenario)
                reported = stopping["summary"][key]
                for metric, value in recomputed.items():
                    add(checks, f"stopping_{key}_{metric}", close(reported[metric], value))

        mc = artifacts["M4_NOISE_MONTE_CARLO"]
        mc_records = mc["records"]
        add(checks, "noise_mc_record_count_240", len(mc_records) == 240)
        for row in mc_records:
            expected_seed = NOISE_CONFIG[row["noise_scenario"]]["seed_base"]  # identity field is checked below by exact formula
            expected_seed = (910000 if row["noise_scenario"] == "N1" else 920000) + row["target_index"] * 100 + row["replicate"]
            add(checks, f"mc_seed_{row['target_index']}_{row['noise_scenario']}_{row['replicate']}", int(row["noise_seed"]) == expected_seed)
            target = np.asarray(OFFGRID_TARGETS[row["target_index"]], dtype=np.float64)
            true_response = oracle.predict(target.reshape(1, 2))["J1"][0]
            sigma = noise_sigma(true_response, row["noise_scenario"])
            noise = np.random.default_rng(expected_seed).normal(0.0, sigma)
            measurement = true_response + noise
            add(checks, f"mc_measurement_hash_{row['target_index']}_{row['noise_scenario']}_{row['replicate']}", row["measurement_hash"] == array_hash(measurement))
            point = np.asarray(row["map_geometry"], dtype=np.float64)
            add(checks, f"mc_map_domain_{row['target_index']}_{row['noise_scenario']}_{row['replicate']}", np.all(point >= DOMAIN_MIN) and np.all(point <= DOMAIN_MAX))
            for method in ("P1_sobol12", "P2_sobol37"):
                method_row = row[method]
                add(checks, f"mc_budget_{method}_{row['target_index']}_{row['noise_scenario']}_{row['replicate']}", 0 <= int(method_row["online_query_count"]) <= 20)
                add(checks, f"mc_no_hidden_stop_{method}_{row['target_index']}_{row['noise_scenario']}_{row['replicate']}", method_row["stop_reason"] in ("max_online_queries", "response_blind_ei_and_stagnation_rule"))
        for method in ("P1_sobol12", "P2_sobol37"):
            for scenario in NOISE_SCENARIOS:
                key = f"{method}_{scenario}"
                recomputed = recompute_summary(mc_records, method, scenario)
                reported = mc["summary"][key]
                for metric, value in recomputed.items():
                    add(checks, f"mc_{key}_{metric}", close(reported[metric], value))

        cost = artifacts["M4_INITIALIZATION_COST_STUDY"]
        cost_summary = [row for row in cost["rows"] if row.get("summary")]
        add(checks, "cost_summary_count_20", len(cost_summary) == 20)
        expected_new = {"train37": 0, "sobol12": 12, "sobol37": 37,
                        "train37_plus_sobol6": 6, "train37_plus_sobol12": 12}
        for row in cost_summary:
            add(checks, f"cost_new_count_{row['initialization']}_{row['contract']}_{row['noise_scenario']}", row["new_geometry_count_relative_train37"] == expected_new[row["initialization"]])
            add(checks, f"cost_fem_count_{row['initialization']}_{row['contract']}_{row['noise_scenario']}", row["new_fem_runs_relative_train37"] == expected_new[row["initialization"]] * 3)
            add(checks, f"cost_amortized_order_{row['initialization']}_{row['contract']}_{row['noise_scenario']}", row["amortized_total_evaluations_1"] <= row["amortized_total_evaluations_10"] <= row["amortized_total_evaluations_100"])

        taxonomy = artifacts["M4_GP_WARNING_TAXONOMY"]
        add(checks, "warning_taxonomy_fit_count", taxonomy.get("fit_count") == 1361)
        add(checks, "warning_taxonomy_categories_present", sum(taxonomy.get("warning_category_totals", {}).values()) == taxonomy.get("warning_count"))
        add(checks, "warning_taxonomy_groups_present", len(taxonomy.get("groups", [])) > 0)
        add(checks, "warning_taxonomy_no_bound_change", taxonomy.get("source_trace") == "M3_BO_REPLAY.json")

        result = {
            "schema_version": "task007.case148-m4a-check.v1",
            "status": "pass" if all(checks.values()) else "failed",
            "implementation_source_sha": implementation_source_sha,
            "checks": checks,
            "errors": [name for name, value in checks.items() if not value],
            "qualification": {
                "map_stability": maps.get("status"), "standalone_acquisition": acquisition.get("status"),
                "response_blind_readiness": stopping.get("readiness_gate_pass"),
                "noise_mc_readiness": mc.get("readiness_gate_pass"),
                "controlled_negative_is_preserved": True,
                "note": "M4A is surrogate-oracle robustness evidence; it does not authorize physical FEM BO or inversion.",
            },
            "new_fem_count": 0, "task006_lock_modified": False,
        }
    except Exception as exc:
        result = {
            "schema_version": "task007.case148-m4a-check.v1", "status": "failed",
            "implementation_source_sha": implementation_source_sha,
            "checks": checks, "errors": [f"exception: {type(exc).__name__}: {exc}"],
            "qualification": {"status": "checker_error"}, "new_fem_count": 0,
        }
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
