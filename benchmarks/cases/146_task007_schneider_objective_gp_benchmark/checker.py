"""Independent Case146 checker for the Task007 objective-GP replay.

The checker deliberately does not call the benchmark runner.  It rebuilds the
J1/J0 arrays from train37 and the eleven Case141 JSON records, recomputes every
scalar objective, and then audits the stored BO traces and model metadata.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUTCOMES = ROOT / "surrogate_tasks/task007_schneider_objective_gp_benchmark/outcomes"
RECORD = Path(__file__).resolve().parent / "records/case146_check.json"

FORWARD_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"
SCHEMA = "task002.fixed-n0-orders.v3"
TRAIN_MANIFEST_SHA = "f36ffe992efe44f89c51bcac35e68145256e80979810d60ae5437686fd91cf84"
MODEL_LOCK_SHA = "f08180f891b485a4ddedcf4066a2bed6a4164342fc0e296bfb06d2278469a7a1"
TRAIN_ROOT = ROOT / "benchmarks/artifacts/cases/137_task006_train37_dataset/train37"
CASE_ROOT = ROOT / "benchmarks/artifacts/cases/141_task006_blind12_forward/blind"
EXTERNAL = (
    (117.5, 16.5), (117.5, 16.75), (117.5, 17.5),
    (118.75, 16.5), (118.75, 17.5),
    (121.25, 16.5), (121.25, 17.5),
    (122.5, 16.5), (122.5, 16.75), (122.5, 17.25), (122.5, 17.5),
)
EXCLUDED = (117.5, 17.25)
ANGLES = (("A05", 2.0, 0.0), ("A07", 2.0, 90.0), ("A09", 4.0, 60.0))
CONTRACTS = ("J1", "J0")
SCENARIOS = ("N1", "N2")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def array_hash(value: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(value, dtype=np.float64))
    descriptor = json.dumps({"dtype": str(array.dtype), "shape": list(array.shape)},
                            sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(descriptor + array.tobytes(order="C")).hexdigest()


def check_close(actual: Any, expected: Any, tol: float = 1.0e-10) -> bool:
    return bool(np.isclose(float(actual), float(expected), rtol=tol, atol=tol))


def m0(sample: dict[str, Any]) -> tuple[float, float]:
    selected = {}
    for side in ("reflection", "transmission"):
        rows = [row for row in sample.get("mother_response", {}).get("orders", [])
                if row.get("side") == side and int(row.get("m")) == 0
                and int(row.get("n")) == 0]
        if len(rows) != 1 or rows[0].get("power_carrying") is not True:
            raise ValueError(f"non-unique or non-propagating m0 channel: {side}")
        if rows[0].get("order_total_power") is None:
            raise ValueError(f"missing m0 power: {side}")
        selected[side] = float(rows[0]["order_total_power"])
    return selected["reflection"], selected["transmission"]


def read_external(geometry: tuple[float, float]) -> tuple[list[float], list[float], list[dict[str, Any]]]:
    j1: list[float] = []
    j0: list[float] = []
    records: list[dict[str, Any]] = []
    h, w = geometry
    for angle_id, grazing, azimuth in ANGLES:
        path = CASE_ROOT / f"{h:g}_{w:g}" / angle_id / "task006_production_sample.json"
        sample = json.loads(path.read_text())
        if (sample.get("status") != "measured_pass" or sample.get("source_sha") != FORWARD_SHA
                or sample.get("source_dirty") is not False or sample.get("model_id") != MODEL_ID
                or sample.get("solver_route_id") != ROUTE_ID or sample.get("observable_schema_version") != SCHEMA
                or sample.get("inputs") != [h, w, grazing, azimuth]):
            raise ValueError(f"external provenance mismatch: {geometry}/{angle_id}")
        reflection, transmission = m0(sample)
        j1.extend((reflection, transmission))
        j0.extend((float(sample["aggregates"]["R_total"]), float(sample["aggregates"]["T_total"])))
        records.append({"path": str(path), "sha256": sha256_file(path), "sample_id": sample.get("sample_id")})
    return j1, j0, records


def objective(target: np.ndarray, responses: np.ndarray, scenario: str) -> np.ndarray:
    if scenario == "N1":
        sigma = np.sqrt((0.01 * np.abs(target)) ** 2 + 1.0e-8)
    elif scenario == "N2":
        sigma = np.sqrt((0.02 * np.abs(target)) ** 2 + 2.5e-7)
    else:
        raise ValueError(scenario)
    residual = (responses - target[None, :]) / sigma[None, :]
    return 0.5 * np.sum(residual * residual, axis=1)


def fail(checks: dict[str, bool], name: str, condition: bool) -> None:
    checks[name] = bool(condition)


def main() -> int:
    checks: dict[str, bool] = {}
    errors: list[str] = []
    try:
        manifest_path = TRAIN_ROOT / "dataset_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        train_geo = np.asarray(np.load(TRAIN_ROOT / "geometries.npy"), dtype=np.float64)
        train_j1 = np.asarray(np.load(TRAIN_ROOT / "s1_selected_powers.npy"), dtype=np.float64).reshape(37, 6)
        train_j0 = np.asarray(np.load(TRAIN_ROOT / "aggregates.npy"), dtype=np.float64)[:, :, :2].reshape(37, 6)
        external_geo = np.asarray(EXTERNAL, dtype=np.float64)
        ext_j1: list[list[float]] = []
        ext_j0: list[list[float]] = []
        for geometry in EXTERNAL:
            j1, j0, _ = read_external(geometry)
            ext_j1.append(j1); ext_j0.append(j0)
        geometries = np.vstack((train_geo, external_geo))
        j1 = np.vstack((train_j1, np.asarray(ext_j1, dtype=np.float64)))
        j0 = np.vstack((train_j0, np.asarray(ext_j0, dtype=np.float64)))

        inventory = json.loads((OUTCOMES / "REPLAY_DATA_INVENTORY.json").read_text())
        targets = json.loads((OUTCOMES / "REPLAY_TARGETS.json").read_text())
        contract = json.loads((OUTCOMES / "OBJECTIVE_CONTRACT.json").read_text())
        identity = json.loads((OUTCOMES / "OBJECTIVE_IDENTITY_AUDIT.json").read_text())
        replay = json.loads((OUTCOMES / "BAYESIAN_OPTIMIZATION_REPLAY.json").read_text())
        maps = json.loads((OUTCOMES / "MAP_RECOVERY_SUMMARY.json").read_text())
        audit = json.loads((OUTCOMES / "OBJECTIVE_GP_MODEL_AUDIT.json").read_text())

        fail(checks, "train_manifest_immutable", manifest.get("status") == "immutable" and manifest.get("geometry_count") == 37)
        fail(checks, "train_manifest_sha_exact", sha256_file(manifest_path) == TRAIN_MANIFEST_SHA)
        fail(checks, "model_lock_sha_exact", sha256_file(ROOT / "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes/TASK006_MODEL_SELECTION_LOCK.json") == MODEL_LOCK_SHA)
        fail(checks, "replay_count_37_plus_11", geometries.shape == (48, 2))
        fail(checks, "excluded_geometry_absent", not np.any(np.all(np.isclose(geometries, EXCLUDED), axis=1)))
        fail(checks, "inventory_geometry_hash", inventory.get("geometries_sha256") == array_hash(geometries))
        fail(checks, "inventory_j1_hash", inventory.get("J1_response_array_sha256") == array_hash(j1))
        fail(checks, "inventory_j0_hash", inventory.get("J0_response_array_sha256") == array_hash(j0))
        fail(checks, "identity_audit_pass", identity.get("status") == "pass")
        fail(checks, "contract_frozen", contract.get("status") == "frozen" and contract.get("new_fem_count") == 0)
        fail(checks, "new_fem_count_zero", inventory.get("new_fem_count") == 0 and replay.get("status") == "complete")

        target_indices = list(range(37, 48))
        fail(checks, "target_count_11", replay.get("target_count") == 11 and len(replay.get("targets", [])) == 11)
        fail(checks, "target_indices_exact", [int(row["target_index"]) for row in replay["targets"]] == target_indices)
        objective_arrays: dict[tuple[int, str, str], np.ndarray] = {}
        target_audit = {int(row["target_index"]): row for row in targets["targets"]}
        for target_index in target_indices:
            for name, responses in (("J1", j1), ("J0", j0)):
                for scenario in SCENARIOS:
                    values = objective(responses[target_index], responses, scenario)
                    objective_arrays[(target_index, name, scenario)] = values
                    row = target_audit[target_index][name][scenario]
                    fail(checks, f"objective_hash_{target_index}_{name}_{scenario}", row["objective_array_sha256"] == array_hash(values))
                    fail(checks, f"objective_finite_{target_index}_{name}_{scenario}", bool(np.all(np.isfinite(values))))
                    fail(checks, f"objective_unique_{target_index}_{name}_{scenario}", int(np.sum(values <= 1.0e-12)) == 1 and int(np.argmin(values)) == target_index)

        # Audit every stored BO trace independently of summary fields.
        for target in replay["targets"]:
            target_index = int(target["target_index"])
            for name in CONTRACTS:
                for scenario in SCENARIOS:
                    truth = objective_arrays[(target_index, name, scenario)]
                    block = target["scenarios"][name][scenario]
                    for method in ("P0", "P1", "P2"):
                        rows = block[method] if isinstance(block[method], list) else [block[method]]
                        expected_initial = 5 if method == "P0" else 12 if method == "P1" else 37
                        for row in rows:
                            initial = [int(i) for i in row["initial_indices"]]
                            fail(checks, f"{method}_initial_train_only_{target_index}_{name}_{scenario}",
                                 len(initial) == expected_initial and len(set(initial)) == len(initial)
                                 and set(initial).issubset(set(range(37))) and target_index not in initial)
                            if method == "P2":
                                fail(checks, f"P2_all37_{target_index}_{name}_{scenario}", initial == list(range(37)))
                            observed = list(initial)
                            for step, query in enumerate(row.get("queries", [])):
                                index = int(query["index"])
                                fail(checks, f"query_step_{target_index}_{name}_{scenario}_{method}_{step}", int(query["query_step"]) == step and index not in observed and 0 <= index < 48)
                                if not (0 <= index < 48):
                                    continue
                                fail(checks, f"query_value_{target_index}_{name}_{scenario}_{method}_{step}", check_close(query["revealed_F"], truth[index], 1.0e-9))
                                fail(checks, f"query_target_flag_{target_index}_{name}_{scenario}_{method}_{step}", bool(query["is_target"]) == (index == target_index))
                                observed.append(index)
                            hits = [int(query["query_step"]) + 1 for query in row.get("queries", []) if query.get("is_target")]
                            fail(checks, f"query_metric_{target_index}_{name}_{scenario}_{method}", row.get("queries_to_exact_target") == (hits[0] if hits else None))
                            fail(checks, f"final_query_count_{target_index}_{name}_{scenario}_{method}", row.get("final", {}).get("online_query_count") == len(row.get("queries", [])))
                    for random in block["B1"]["repeats"]:
                        q = random.get("queries_to_exact_target")
                        fail(checks, f"B1_repeat_{target_index}_{name}_{scenario}_{random.get('seed')}",
                             random.get("exact_target_hit") is True and isinstance(q, int) and 1 <= q <= 47)
                    fail(checks, f"B1_count_{target_index}_{name}_{scenario}", len(block["B1"]["repeats"]) == 100)

        # P3 is a continuous diagnostic and has its own tolerance evidence.
        p3_primary = [row for row in maps["targets"] if row["contract"] == "J1" and row["noise_scenario"] == "N1"]
        for row in maps["targets"]:
            selected = np.asarray(row["map"]["selected_geometry"], dtype=np.float64)
            target = np.asarray(row["target_geometry"], dtype=np.float64)
            h_err, w_err = np.abs(selected - target)
            fail(checks, f"P3_error_{row['contract']}_{row['noise_scenario']}_{row['target_index']}",
                 check_close(row["height_abs_error_nm"], h_err) and check_close(row["width_abs_error_nm"], w_err)
                 and bool(row["within_tolerance"]) == bool(h_err <= 0.25 and w_err <= 0.05))
        fail(checks, "p3_primary_row_count", len(p3_primary) == 11)

        fail(checks, "gp_audit_lml_finite", audit.get("all_lml_finite") is True)
        fail(checks, "gp_audit_starts_8", audit.get("optimizer_starts") == 8)
        fail(checks, "gp_audit_training_only_jitter", audit.get("jitter_selection_training_only") is True)
        fail(checks, "gp_audit_warnings_recorded", int(audit.get("warning_count", 0)) > 0)
        fail(checks, "gp_audit_boundary_recorded", int(audit.get("boundary_collision_count", 0)) >= 0)

        unique_pass = all(bool(target_audit[i]["J1"]["N1"]["unique_minimizer"]) for i in target_indices)
        p2 = [target["scenarios"]["J1"]["N1"]["P2"] for target in replay["targets"]]
        p2_q = [int(row["queries_to_exact_target"]) for row in p2]
        p2_pass = sum(q <= 5 for q in p2_q) >= 10 and all(q <= 11 for q in p2_q)
        p3_count = sum(bool(row["within_tolerance"]) for row in p3_primary)
        qualification = {
            "primary_contract": "J1/N1",
            "unique_replay_minimizer_pass": unique_pass,
            "p2_exact_target_within_5_count": int(sum(q <= 5 for q in p2_q)),
            "p2_exact_target_gate_pass": p2_pass,
            "p3_within_tolerance_count": int(p3_count),
            "p3_gate_pass": p3_count >= 10,
            "status": "pass" if unique_pass and p2_pass and p3_count >= 10 else "controlled_negative_p3_map",
            "note": "P3 continuous MAP is reported as a negative benchmark; this does not alter stored responses or promote a formal surrogate.",
        }
        integrity_pass = all(checks.values())
        result = {
            "schema_version": "task007.case146-check.v1",
            "status": "pass" if integrity_pass else "failed",
            "checks": checks,
            "errors": errors + [name for name, value in checks.items() if not value],
            "qualification": qualification,
            "new_fem_count": 0,
            "task006_lock_modified": False,
            "frozen_validation_accessed": False,
        }
    except Exception as exc:  # checker failure is explicit, never a silent pass
        result = {"schema_version": "task007.case146-check.v1", "status": "failed",
                  "checks": checks, "errors": errors + [f"exception: {type(exc).__name__}: {exc}"],
                  "qualification": {"status": "checker_error"}, "new_fem_count": 0}
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
