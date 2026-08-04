"""Independent derived-only checker for the Task005 M5R final lock."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


FORWARD_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
DATASET_ID = "task005_discrete_angle_hw_sensitivity_p5_ny4_v1"
SUPPLEMENT_ID = "task005_discrete_angle_hw_sensitivity_p5_ny4_derived_contract_v1"
MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"
OBSERVABLE = "task002.fixed-n0-orders.v3"
BASELINE = ("A14", "A15")
SELECTED = {
    1: ("A05",), 2: ("A05", "A07"),
    3: ("A05", "A07", "A09"), 4: ("A05", "A06", "A07", "A09"),
}
ANGLES = (
    ("A00", 0.5, 0.0), ("A01", 0.5, 45.0), ("A02", 0.5, 90.0),
    ("A03", 1.0, 15.0), ("A04", 1.0, 60.0),
    ("A05", 2.0, 0.0), ("A06", 2.0, 45.0), ("A07", 2.0, 90.0),
    ("A08", 4.0, 15.0), ("A09", 4.0, 60.0), ("A10", 4.0, 90.0),
    ("A11", 6.0, 30.0), ("A12", 6.0, 75.0),
    ("A13", 8.0, 45.0), ("A14", 10.0, 0.0), ("A15", 10.0, 90.0),
)
STATES = ("H-", "H+", "W-", "W+")
RAW_HASHES = {
    "angles.npy": "26598a16dfee4c564132f2f6fcefb49c7ab9d1ef1e5907bac76228b608981b5d",
    "derivatives.json": "5c7e5111128e6e89a173763c61a2cca29e1359285b960ee5bcbf19110a22b5e9",
    "nominal_aggregates.npy": "44656759ff51019fe43f9317e0287ed198a7e6767e53bc577eb15245d90e4e1f",
    "nominal_inputs.npy": "d9e874d041448df78de7711abb6c864e7edf6c5b375a239d57c6a548403c7c8a",
    "nominal_order_mask.npy": "4c8364c2f4e0b272eddbbd0a5f771625fb3872bef4423d4738966b9ec2592e18",
    "nominal_order_powers.npy": "442ffe762c56b37443e6755b86a04c677b577ef2208bea51e0932e8bb21a166c",
    "order_identity.json": "25269154b988586145b582dd579686919b3c1dd7abcb838c393939705b5d91d9",
    "perturbed_aggregates.npy": "0fcf2a5c3846e4f2bc24ac4e7947a9602cc9714c1b749dc70d88c21ba5c89159",
    "perturbed_order_mask.npy": "ecbf4604950f0248cce9efefa49ec2e2c61f8747cff13583fb4fb57c367e0c72",
    "perturbed_order_powers.npy": "98210a61717ca9ec5041d383e598ebf5ab04d63a09a3b3fe215a26b1d33fb5fd",
    "record_identity.json": "b469eb661b02e3866641959d867fd68b376476b9f3e1a816afd0751026f744c9",
}
V1_LOCK_SHA = "4509404694c9182a9eeaa1da6efc6f3f9e2f5de63e4eaa025d375936861f4ad7"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def close(a: Any, b: Any, atol: float = 1e-12) -> bool:
    try:
        return bool(np.allclose(np.asarray(a), np.asarray(b), rtol=0.0, atol=atol))
    except (TypeError, ValueError):
        return a == b


def rank_key(row: dict[str, Any], *, m2: bool = False, noise: str | None = None) -> tuple[Any, ...]:
    if not m2:
        full = bool(row["full_rank_M0_M1_N1_N2"])
        minimum = row["worst_case_minimum_eigenvalue"]
        logdet = row["worst_case_logdet"]
        condition = row["worst_case_condition_number"]
    else:
        selected_noise = (noise,) if noise else ("N1", "N2")
        scenarios = [row["scenario_results"]["M2_order_total_extended"][item]
                     for item in selected_noise]
        full = all(bool(item["full_rank"]) for item in scenarios)
        minimum = min(float(item["minimum_eigenvalue"]) for item in scenarios)
        logdet = min(float(item["logdet"]) for item in scenarios)
        condition = max(float(item["condition_number"]) for item in scenarios)
    return (0 if full else 1, -float(minimum),
            -float(logdet) if logdet is not None else math.inf,
            float(condition) if condition is not None else math.inf,
            tuple(row["angle_ids"]))


def ranked(rows: list[dict[str, Any]], *, m2: bool = False,
           noise: str | None = None) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: rank_key(row, m2=m2, noise=noise))


def recompute_rank_fields(ranking: dict[str, Any], audit: dict[str, Any],
                          ranking_path: Path) -> bool:
    okay = True
    for size in range(1, 5):
        rows = list(ranking["ranked_by_size"][str(size)])
        robust = ranked(rows)
        m2_worst = ranked(rows, m2=True)
        m2_by_noise = {noise: ranked(rows, m2=True, noise=noise) for noise in ("N1", "N2")}
        target = audit["sizes"][str(size)]
        okay &= target["robust_reference"]["best"]["angle_ids"] == robust[0]["angle_ids"]
        okay &= target["m2_worst_case"]["best"]["angle_ids"] == m2_worst[0]["angle_ids"]
        for noise in ("N1", "N2"):
            okay &= target["m2_by_noise"][noise]["best"]["angle_ids"] == m2_by_noise[noise][0]["angle_ids"]
        common = sorted({tuple(row["angle_ids"]) for row in robust if row["full_rank_M0_M1_N1_N2"]}
                        & {tuple(row["angle_ids"]) for row in m2_worst
                           if all(item["full_rank"] for item in (
                               row["scenario_results"]["M2_order_total_extended"]["N1"],
                               row["scenario_results"]["M2_order_total_extended"]["N2"]))})
        robust_common = [row for row in robust if tuple(row["angle_ids"]) in common]
        m2_common = [row for row in m2_worst if tuple(row["angle_ids"]) in common]
        robust_pos = {tuple(row["angle_ids"]): i for i, row in enumerate(robust_common, 1)}
        m2_pos = {tuple(row["angle_ids"]): i for i, row in enumerate(m2_common, 1)}
        okay &= target["common_full_rank"]["count"] == len(common)
        for top in (10, 20):
            left = {tuple(row["angle_ids"]) for row in robust_common[:top]}
            right = {tuple(row["angle_ids"]) for row in m2_common[:top]}
            expected = target["common_full_rank"][f"top_{top}_overlap"]
            okay &= expected["count"] == len(left & right)
            okay &= expected["denominator"] == min(top, len(common))
        if len(common) >= 2:
            a = np.asarray([robust_pos[item] for item in common], dtype=float)
            b = np.asarray([m2_pos[item] for item in common], dtype=float)
            a -= a.mean(); b -= b.mean()
            rho = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
            okay &= abs(float(target["common_full_rank"]["spearman_rank_correlation"]) - rho) < 1e-10
        selected = SELECTED[size]
        def pos(order: list[dict[str, Any]]) -> int:
            return next(i for i, row in enumerate(order, 1) if tuple(row["angle_ids"]) == selected)
        okay &= target["selected_set"]["robust_rank"] == pos(robust)
        okay &= target["selected_set"]["m2_worst_case_rank"] == pos(m2_worst)
        okay &= target["selected_set"]["m2_N1_rank"] == pos(m2_by_noise["N1"])
        okay &= target["selected_set"]["m2_N2_rank"] == pos(m2_by_noise["N2"])
    okay &= audit["m2_diagnostic_only"] is True
    okay &= audit["source_ranking_sha256"] == digest(ranking_path)
    return bool(okay)


def recompute_weak(derivatives: list[dict[str, Any]]) -> dict[str, Any]:
    powers = []
    sigmas = {"N1": [], "N2": []}
    count = 0
    angle_count = 0
    per_angle = {}
    for row in derivatives:
        m1 = row["contracts"]["M1_order_total_robust"]
        m2 = row["contracts"]["M2_order_total_extended"]
        m1_channels = {tuple(value) for value in m1["channels"]}
        weak = []
        for i, channel in enumerate(m2["channels"]):
            if tuple(channel) in m1_channels:
                continue
            count += 1; powers.append(float(m2["nominal"][i]))
            for noise in sigmas:
                sigmas[noise].append(float(m2["noise_sigma"][noise][i]))
            weak.append(channel)
        angle_count += bool(weak)
        per_angle[row["angle_id"]] = len(weak)
    return {
        "total_weak_channel_observations": count,
        "angles_with_weak_channels": angle_count,
        "nominal_power_range": [min(powers), max(powers)],
        "sigma_range": {noise: [min(values), max(values)] for noise, values in sigmas.items()},
        "per_angle_counts": per_angle,
    }


def check_raw(root: Path, errors: list[str]) -> bool:
    dataset = root / "benchmarks/artifacts/cases/132_task005_sensitivity_dataset/dataset"
    outcomes = root / "surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/outcomes"
    manifest_path = dataset / "dataset_manifest.json"
    tracked_path = outcomes / "M2_DATASET_MANIFEST.json"
    if not manifest_path.is_file() or not tracked_path.is_file():
        errors.append("raw manifest missing"); return False
    manifest = json.loads(manifest_path.read_text())
    tracked = json.loads(tracked_path.read_text())
    okay = manifest == tracked
    okay &= manifest.get("dataset_id") == DATASET_ID
    okay &= manifest.get("forward_solver_sha") == FORWARD_SHA
    okay &= manifest.get("model_id") == MODEL_ID and manifest.get("solver_route_id") == ROUTE_ID
    okay &= manifest.get("observable_schema_version") == OBSERVABLE
    okay &= manifest.get("new_fem_count") == 44 and manifest.get("m1_reused_count") == 20
    okay &= manifest.get("validation_target_accessed") is False and manifest.get("formal_inversion") is False
    actual = {path.name: digest(path) for path in sorted(dataset.iterdir())
              if path.is_file() and path.name != "dataset_manifest.json"}
    okay &= actual == RAW_HASHES == manifest.get("file_hashes")
    if not okay: errors.append("raw immutable package/hash identity mismatch")
    v1 = outcomes / "DISCRETE_ILLUMINATION_FISHER_DOE_LOCK.json"
    okay &= v1.is_file() and digest(v1) == V1_LOCK_SHA
    if not okay: errors.append("historical v1 lock was changed or missing")
    return bool(okay)


def check_supplement(root: Path, raw: dict[str, Any], errors: list[str]) -> bool:
    supplement = root / "benchmarks/artifacts/cases/132_task005_sensitivity_dataset/derived_contract_v1"
    if not supplement.is_dir(): errors.append("derived supplement missing"); return False
    manifest_path = supplement / "DERIVED_SUPPLEMENT_MANIFEST.json"
    if not manifest_path.is_file(): errors.append("supplement manifest missing"); return False
    manifest = json.loads(manifest_path.read_text())
    okay = manifest.get("dataset_id") == SUPPLEMENT_ID
    okay &= manifest.get("source_raw_dataset_id") == DATASET_ID
    okay &= manifest.get("forward_solver_sha") == FORWARD_SHA
    okay &= manifest.get("source_raw_package_modified") is False
    okay &= manifest.get("generated_without_fem") is True and manifest.get("new_fem_count") == 0
    files = {path.name: digest(path) for path in supplement.iterdir()
             if path.is_file() and path.name != manifest_path.name}
    okay &= {name: item["sha256"] for name, item in manifest.get("files", {}).items()} == files
    arrays = raw["arrays"]
    perturbed_inputs = np.load(supplement / "perturbed_inputs.npy", allow_pickle=False)
    okay &= perturbed_inputs.shape == (16, 4, 4)
    record_identity = raw["record_identity"]
    for i, row in enumerate(raw["derivatives"]):
        for j, state in enumerate(STATES):
            sample = json.loads(Path(record_identity[f"{row['angle_id']}/{state}"]["sample_path"]).read_text())
            okay &= close(perturbed_inputs[i, j], sample["inputs"], atol=0.0)
    okay &= close(np.load(supplement / "M0_Dh.npy", allow_pickle=False), np.asarray([
        row["contracts"]["M0_aggregate_RT"]["derivatives"]["h"] for row in raw["derivatives"]
    ]), atol=1e-13)
    okay &= close(np.load(supplement / "M0_Dw.npy", allow_pickle=False), np.asarray([
        row["contracts"]["M0_aggregate_RT"]["derivatives"]["w"] for row in raw["derivatives"]
    ]), atol=1e-13)
    for noise in ("N1", "N2"):
        expected = np.asarray([
            row["contracts"]["M0_aggregate_RT"]["noise_sigma"][noise]
            for row in raw["derivatives"]
        ], dtype=np.float64)
        okay &= close(np.load(supplement / f"M0_noise_sigma_{noise}.npy", allow_pickle=False),
                      expected, atol=1e-13)
    for contract in ("M1_order_total_robust", "M2_order_total_extended"):
        prefix = contract[:2]
        h_values = []
        w_values = []
        nominal_values = []
        offsets = [0]
        for row in raw["derivatives"]:
            h_values.extend(row["contracts"][contract]["derivatives"]["h"])
            w_values.extend(row["contracts"][contract]["derivatives"]["w"])
            nominal_values.extend(row["contracts"][contract]["nominal"])
            offsets.append(len(h_values))
        npz = np.load(supplement / f"{prefix}_derivatives.npz", allow_pickle=False)
        okay &= close(npz["h_values"], h_values, atol=1e-13)
        okay &= close(npz["w_values"], w_values, atol=1e-13)
        okay &= close(npz["nominal_values"], nominal_values, atol=1e-13)
        okay &= np.array_equal(npz["offsets"], np.asarray(offsets, dtype=np.int64))
        channel_contracts = json.loads((supplement / "channel_contracts.json").read_text())
        for row in raw["derivatives"]:
            expected_channels = row["contracts"][contract]["channels"]
            actual_channels = channel_contracts["contracts"][contract]["per_angle"][row["angle_id"]]["channels"]
            okay &= actual_channels == expected_channels
        for noise in ("N1", "N2"):
            sigma = []
            sigma_offsets = [0]
            for row in raw["derivatives"]:
                sigma.extend(row["contracts"][contract]["noise_sigma"][noise])
                sigma_offsets.append(len(sigma))
            snpz = np.load(supplement / f"{prefix}_noise_sigma_{noise}.npz", allow_pickle=False)
            okay &= close(snpz["values"], sigma, atol=1e-13)
            okay &= np.array_equal(snpz["offsets"], np.asarray(sigma_offsets, dtype=np.int64))
    source_ids = json.loads((supplement / "source_record_ids.json").read_text())
    for key, identity in raw["record_identity"].items():
        derived = source_ids["perturbation_records"].get(key, {})
        okay &= derived.get("formal_record_sha256") == identity.get("formal_record_sha256")
        okay &= derived.get("execution_sha256") == identity.get("execution_sha256")
        okay &= derived.get("status") == identity.get("status")
        okay &= derived.get("new_fem") == identity.get("new_fem")
    if not okay: errors.append("derived supplement cannot be rebuilt from raw records")
    return bool(okay)


def check_lock(root: Path, rank_ok: bool, tradeoff_ok: bool,
               supplement_ok: bool, errors: list[str]) -> bool:
    outcomes = root / "surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/outcomes"
    lock_path = outcomes / "DISCRETE_ILLUMINATION_FISHER_DOE_LOCK_V2.json"
    if not lock_path.is_file(): errors.append("V2 lock missing"); return False
    lock = json.loads(lock_path.read_text())
    okay = lock.get("schema_version") == "task005.discrete-illumination-fisher-doe-lock.v2"
    okay &= lock.get("status") == "review_ready" and lock.get("derived_only") is True
    okay &= lock.get("new_fem_count") == 0
    okay &= lock.get("forward_solver_sha") == FORWARD_SHA
    okay &= lock.get("raw_sensitivity_dataset", {}).get("immutable") is True
    okay &= lock.get("raw_sensitivity_dataset", {}).get("manifest_sha256") == digest(
        root / "benchmarks/artifacts/cases/132_task005_sensitivity_dataset/dataset/dataset_manifest.json")
    okay &= lock.get("derived_supplement", {}).get("manifest_sha256") == digest(
        root / "benchmarks/artifacts/cases/132_task005_sensitivity_dataset/derived_contract_v1/DERIVED_SUPPLEMENT_MANIFEST.json")
    okay &= lock.get("m2_ranking_stability", {}).get("audit_sha256") == digest(outcomes / "M2_RANK_STABILITY_AUDIT.json")
    okay &= lock.get("illumination_count_tradeoff", {}).get("audit_sha256") == digest(outcomes / "ILLUMINATION_COUNT_TRADEOFF.json")
    okay &= lock.get("design", {}).get("design_file_sha256") == digest(outcomes / "DISCRETE_ANGLE_DESIGN.json")
    okay &= lock.get("step_lock", {}).get("lock_file_sha256") == digest(outcomes / "PRODUCTION_STEP_LOCK.json")
    okay &= lock.get("fisher", {}).get("ranking_file_sha256") == digest(outcomes / "FISHER_COMBINATION_RANKING.json")
    okay &= lock.get("fisher", {}).get("task001_baseline_pair_file_sha256") == digest(outcomes / "TASK001_BASELINE_PAIR_COMPARISON.json")
    okay &= lock.get("task001_baseline_interpretation", {}).get("file_sha256") == digest(outcomes / "TASK001_BASELINE_INTERPRETATION_ADDENDUM.md")
    okay &= lock.get("recovery", {}).get("result_file_sha256") == digest(outcomes / "OFF_CENTRE_RECOVERY.json")
    okay &= lock.get("historical_v1_lock", {}).get("file_sha256") == V1_LOCK_SHA
    okay &= lock.get("historical_v1_lock", {}).get("preserved_unchanged") is True
    okay &= lock.get("scope_boundary", {}).get("formal_inversion") is False
    okay &= lock.get("scope_boundary", {}).get("task006_authorized") is False
    okay &= lock.get("scope_boundary", {}).get("task004_blind24_run") is False
    okay &= rank_ok and tradeoff_ok and supplement_ok
    if not okay: errors.append("V2 lock identity/derived gates failed")
    return bool(okay)


def check(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    outcomes = root / "surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/outcomes"
    dataset = root / "benchmarks/artifacts/cases/132_task005_sensitivity_dataset/dataset"
    raw_ok = check_raw(root, errors)
    raw = {
        "arrays": {name: np.load(dataset / name, allow_pickle=False) for name in (
            "angles.npy", "nominal_aggregates.npy", "perturbed_aggregates.npy",
            "nominal_order_powers.npy", "perturbed_order_powers.npy")},
        "derivatives": json.loads((dataset / "derivatives.json").read_text()),
        "record_identity": json.loads((dataset / "record_identity.json").read_text()),
    }
    ranking = json.loads((outcomes / "FISHER_COMBINATION_RANKING.json").read_text())
    audit = json.loads((outcomes / "M2_RANK_STABILITY_AUDIT.json").read_text()) if (outcomes / "M2_RANK_STABILITY_AUDIT.json").is_file() else {}
    ranking_path = outcomes / "FISHER_COMBINATION_RANKING.json"
    rank_ok = bool(audit) and recompute_rank_fields(ranking, audit, ranking_path)
    if not rank_ok: errors.append("M2 ranking audit does not rebuild independently")
    weak = recompute_weak(raw["derivatives"])
    rank_ok &= close(audit.get("weak_channel_summary", {}).get("nominal_power_range"), weak["nominal_power_range"], atol=1e-15)
    rank_ok &= audit.get("weak_channel_summary", {}).get("total_weak_channel_observations") == weak["total_weak_channel_observations"]
    if not rank_ok: errors.append("weak-channel summary mismatch")
    tradeoff_path = outcomes / "ILLUMINATION_COUNT_TRADEOFF.json"
    tradeoff_ok = tradeoff_path.is_file()
    if tradeoff_ok:
        tradeoff = json.loads(tradeoff_path.read_text())
        for size in range(1, 5):
            row = ranked(list(ranking["ranked_by_size"][str(size)]))[0]
            key = ("best_single", "best_pair", "best_triple", "best_quad")[size - 1]
            tradeoff_ok &= tradeoff[key]["angle_ids"] == row["angle_ids"]
        tradeoff_ok &= tradeoff["information_global_best"]["angle_ids"] == ["A05", "A06", "A07", "A09"]
        tradeoff_ok &= tradeoff["m4_nonlinearly_validated_set"]["angle_ids"] == ["A05", "A07", "A09"]
        tradeoff_ok &= tradeoff["recommended_operational_set_for_next_task"]["angle_ids"] == ["A05", "A07", "A09"]
        tradeoff_ok &= all(not item["within_5_percent_tie"] for item in tradeoff["five_percent_rule"]["adjacent_comparisons"])
    if not tradeoff_ok: errors.append("illumination-count 5% tradeoff mismatch")
    supplement_ok = check_supplement(root, raw, errors)
    lock_ok = check_lock(root, rank_ok, tradeoff_ok, supplement_ok, errors)
    checks = {
        "raw_v1_package_hashes_unchanged": raw_ok,
        "v1_lock_preserved": raw_ok and digest(outcomes / "DISCRETE_ILLUMINATION_FISHER_DOE_LOCK.json") == V1_LOCK_SHA,
        "m2_rank_audit_rebuild": rank_ok,
        "illumination_count_tradeoff_rebuild": tradeoff_ok,
        "derived_supplement_rebuild": supplement_ok,
        "lock_v2_identity": lock_ok,
        "no_new_fem": lock_ok and json.loads((outcomes / "DISCRETE_ILLUMINATION_FISHER_DOE_LOCK_V2.json").read_text()).get("new_fem_count") == 0,
        "no_task004_blind_or_validation": lock_ok,
        "formal_inversion_false": lock_ok,
    }
    return {
        "schema_version": "task005.case134-final-lock-review.v1",
        "status": "pass" if all(checks.values()) and not errors else "failed",
        "checks": checks, "errors": errors,
        "new_fem_count": 0, "task004_blind24_run": False,
        "validation_target_accessed": False, "formal_inversion": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path(
        "benchmarks/cases/134_task005_final_lock_review/records/case134_check.json"))
    args = parser.parse_args()
    result = check(args.root.resolve())
    output = args.output if args.output.is_absolute() else args.root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
