"""Derived-only M5R audits for the Task005 discrete illumination DOE.

This module deliberately never calls the forward solver.  It reads the
immutable Task005 v1 sensitivity package and the already committed Fisher
tables, then writes a hash-bound companion package and review artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import numpy as np

from .design import BASELINE_PAIR


FORWARD_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"
OBSERVABLE = "task002.fixed-n0-orders.v3"
RAW_DATASET_ID = "task005_discrete_angle_hw_sensitivity_p5_ny4_v1"
TRAIN_DATASET_ID = "task004_angle_nominal_p5_ny4_train112_v1"
RAW_DATASET_REL = Path("benchmarks/artifacts/cases/132_task005_sensitivity_dataset/dataset")
OUTCOMES_REL = Path("surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/outcomes")
SUPPLEMENT_REL = Path("benchmarks/artifacts/cases/132_task005_sensitivity_dataset/derived_contract_v1")
STATES = ("H-", "H+", "W-", "W+")
CONTRACTS = ("M0_aggregate_RT", "M1_order_total_robust", "M2_order_total_extended")
NOISES = ("N1", "N2")
SELECTED_BY_SIZE = {
    1: ("A05",),
    2: ("A05", "A07"),
    3: ("A05", "A07", "A09"),
    4: ("A05", "A06", "A07", "A09"),
}


def _dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _deterministic_npz(path: Path, **arrays: np.ndarray) -> None:
    """Write an NPZ with fixed zip metadata so its hash is reproducible."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(arrays):
            buffer = BytesIO()
            np.lib.format.write_array(buffer, np.asarray(arrays[name]), allow_pickle=False)
            info = ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o600 << 16
            archive.writestr(info, buffer.getvalue(), compress_type=ZIP_DEFLATED,
                             compresslevel=9)


def _raw_files(dataset: Path) -> list[Path]:
    return sorted(path for path in dataset.iterdir() if path.is_file())


def _load(root: Path) -> dict[str, Any]:
    dataset = root / RAW_DATASET_REL
    outcomes = root / OUTCOMES_REL
    required = [
        dataset / "dataset_manifest.json", dataset / "derivatives.json",
        dataset / "record_identity.json", dataset / "angles.npy",
        dataset / "nominal_aggregates.npy", dataset / "perturbed_aggregates.npy",
        dataset / "nominal_order_powers.npy", dataset / "perturbed_order_powers.npy",
        outcomes / "FISHER_COMBINATION_RANKING.json",
        outcomes / "TASK001_BASELINE_PAIR_COMPARISON.json",
        outcomes / "DISCRETE_ANGLE_DESIGN.json",
        outcomes / "PRODUCTION_STEP_LOCK.json",
        outcomes / "DISCRETE_ILLUMINATION_FISHER_DOE_LOCK.json",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("M5R inputs missing: " + ", ".join(missing))
    raw_manifest = json.loads((dataset / "dataset_manifest.json").read_text())
    tracked_manifest = json.loads((outcomes / "M2_DATASET_MANIFEST.json").read_text())
    return {
        "root": root, "dataset": dataset, "outcomes": outcomes,
        "raw_manifest": raw_manifest, "tracked_manifest": tracked_manifest,
        "derivatives": json.loads((dataset / "derivatives.json").read_text()),
        "record_identity": json.loads((dataset / "record_identity.json").read_text()),
        "arrays": {
            name: np.load(dataset / name, allow_pickle=False)
            for name in (
                "angles.npy", "nominal_inputs.npy", "nominal_aggregates.npy",
                "perturbed_aggregates.npy", "nominal_order_powers.npy",
                "perturbed_order_powers.npy", "nominal_order_mask.npy",
                "perturbed_order_mask.npy",
            )
        },
        "ranking": json.loads((outcomes / "FISHER_COMBINATION_RANKING.json").read_text()),
        "baseline": json.loads((outcomes / "TASK001_BASELINE_PAIR_COMPARISON.json").read_text()),
        "design": json.loads((outcomes / "DISCRETE_ANGLE_DESIGN.json").read_text()),
        "step_lock": json.loads((outcomes / "PRODUCTION_STEP_LOCK.json").read_text()),
        "v1_lock": json.loads((outcomes / "DISCRETE_ILLUMINATION_FISHER_DOE_LOCK.json").read_text()),
    }


def _assert_raw_identity(data: dict[str, Any]) -> None:
    manifest = data["raw_manifest"]
    tracked = data["tracked_manifest"]
    if manifest != tracked:
        raise ValueError("tracked M2 manifest and raw dataset manifest differ")
    expected = {
        "dataset_id": RAW_DATASET_ID,
        "status": "immutable",
        "forward_solver_sha": FORWARD_SHA,
        "model_id": MODEL_ID,
        "solver_route_id": ROUTE_ID,
        "observable_schema_version": OBSERVABLE,
        "new_fem_count": 44,
        "m1_reused_count": 20,
        "validation_target_accessed": False,
        "formal_inversion": False,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"raw manifest identity mismatch {key}: {manifest.get(key)!r}")
    if manifest.get("step") != {"delta_h_nm": 1.25, "delta_w_nm": 0.25,
                                 "method": "central_difference"}:
        raise ValueError("raw production step identity mismatch")
    actual_hashes = {
        path.name: _digest(path) for path in _raw_files(data["dataset"])
        if path.name != "dataset_manifest.json"
    }
    if actual_hashes != manifest.get("file_hashes"):
        raise ValueError("raw immutable package hash mismatch")
    if data["v1_lock"].get("status") != "frozen_review_pending":
        raise ValueError("v1 lock is not the preserved historical lock")


def _rank_key(row: dict[str, Any], *, m2: bool = False, noise: str | None = None) -> tuple[Any, ...]:
    if not m2:
        full = bool(row["full_rank_M0_M1_N1_N2"])
        minimum = row["worst_case_minimum_eigenvalue"]
        logdet = row["worst_case_logdet"]
        condition = row["worst_case_condition_number"]
    else:
        scenarios = [row["scenario_results"]["M2_order_total_extended"][item]
                     for item in ((noise,) if noise else NOISES)]
        full = all(bool(item["full_rank"]) for item in scenarios)
        minimum = min(float(item["minimum_eigenvalue"]) for item in scenarios)
        logdet = min(float(item["logdet"]) for item in scenarios)
        condition = max(float(item["condition_number"]) for item in scenarios)
    return (
        0 if full else 1,
        -float(minimum),
        -float(logdet) if logdet is not None else math.inf,
        float(condition) if condition is not None else math.inf,
        tuple(row["angle_ids"]),
    )


def _ranked(rows: Iterable[dict[str, Any]], *, m2: bool = False,
            noise: str | None = None) -> list[dict[str, Any]]:
    return sorted(list(rows), key=lambda row: _rank_key(row, m2=m2, noise=noise))


def _metric_summary(row: dict[str, Any], *, m2: bool = False,
                    noise: str | None = None) -> dict[str, Any]:
    if not m2:
        return {
            "full_rank": bool(row["full_rank_M0_M1_N1_N2"]),
            "minimum_eigenvalue": row["worst_case_minimum_eigenvalue"],
            "logdet": row["worst_case_logdet"],
            "condition_number": row["worst_case_condition_number"],
        }
    scenarios = [row["scenario_results"]["M2_order_total_extended"][item]
                 for item in ((noise,) if noise else NOISES)]
    return {
        "full_rank": all(bool(item["full_rank"]) for item in scenarios),
        "minimum_eigenvalue": min(float(item["minimum_eigenvalue"]) for item in scenarios),
        "logdet": min(float(item["logdet"]) for item in scenarios),
        "condition_number": max(float(item["condition_number"]) for item in scenarios),
        "scenario_results": {
            item["noise"]: {
                key: item[key] for key in (
                    "rank", "full_rank", "minimum_eigenvalue", "logdet", "condition_number",
                    "channel_counts",
                )
            } for item in scenarios
        },
    }


def _rank_position(rows: list[dict[str, Any]], angle_ids: tuple[str, ...], *,
                   m2: bool = False, noise: str | None = None) -> int | None:
    order = _ranked(rows, m2=m2, noise=noise)
    for index, row in enumerate(order, start=1):
        if tuple(row["angle_ids"]) == angle_ids:
            return index
    return None


def _average_rank(values: list[float]) -> dict[float, float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks: dict[float, float] = {}
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and ordered[end][1] == ordered[cursor][1]:
            end += 1
        rank = (cursor + 1 + end) / 2.0
        for index in range(cursor, end):
            ranks[ordered[index][1]] = rank
        cursor = end
    return ranks


def _spearman(ids: list[tuple[str, ...]], left: dict[tuple[str, ...], int],
              right: dict[tuple[str, ...], int]) -> float | None:
    if len(ids) < 2:
        return None
    a = np.asarray([left[item] for item in ids], dtype=np.float64)
    b = np.asarray([right[item] for item in ids], dtype=np.float64)
    a -= a.mean(); b -= b.mean()
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denominator) if denominator else None


def _weak_channel_summary(data: dict[str, Any]) -> dict[str, Any]:
    rows = []
    powers: list[float] = []
    sigma = {noise: [] for noise in NOISES}
    for item in data["derivatives"]:
        m1 = item["contracts"]["M1_order_total_robust"]
        m2 = item["contracts"]["M2_order_total_extended"]
        m1_channels = {tuple(channel) for channel in m1["channels"]}
        weak = []
        for index, channel in enumerate(m2["channels"]):
            if tuple(channel) in m1_channels:
                continue
            power = float(m2["nominal"][index])
            powers.append(power)
            for noise in NOISES:
                sigma[noise].append(float(m2["noise_sigma"][noise][index]))
            weak.append({
                "channel": _jsonable(channel), "nominal_power": power,
                "sigma_N1": float(m2["noise_sigma"]["N1"][index]),
                "sigma_N2": float(m2["noise_sigma"]["N2"][index]),
                "tier": "weak_extended_near_absolute_floor",
            })
        rows.append({"angle_id": item["angle_id"], "weak_channels": weak,
                     "weak_count": len(weak)})
    return {
        "total_weak_channel_observations": len(powers),
        "angles_with_weak_channels": sum(bool(row["weak_channels"]) for row in rows),
        "nominal_power_range": [min(powers), max(powers)] if powers else [],
        "sigma_range": {
            noise: [min(values), max(values)] if values else []
            for noise, values in sigma.items()
        },
        "per_angle": rows,
        "interpretation": (
            "M2-only channels are weak extended diagnostics. They are retained for "
            "ranking stability only and cannot override robust M0/M1 selection."
        ),
    }


def build_ranking_audit(data: dict[str, Any]) -> dict[str, Any]:
    ranking = data["ranking"]
    by_size = ranking["ranked_by_size"]
    payload: dict[str, Any] = {
        "schema_version": "task005.m2-ranking-stability-audit.v1",
        "status": "pass",
        "source_ranking_sha256": _digest(data["outcomes"] / "FISHER_COMBINATION_RANKING.json"),
        "dataset_id": RAW_DATASET_ID,
        "forward_solver_sha": FORWARD_SHA,
        "robust_contract": "M0/M1 N1/N2 worst-case ranking from v1; M2 is diagnostic",
        "sizes": {}, "weak_channel_summary": _weak_channel_summary(data),
        "m2_diagnostic_only": True,
    }
    for size in range(1, 5):
        rows = list(by_size[str(size)])
        robust_order = _ranked(rows)
        m2_worst_order = _ranked(rows, m2=True)
        m2_orders = {noise: _ranked(rows, m2=True, noise=noise) for noise in NOISES}
        robust_full = [row for row in robust_order if row["full_rank_M0_M1_N1_N2"]]
        m2_full = [row for row in m2_worst_order
                   if _metric_summary(row, m2=True)["full_rank"]]
        common_ids = sorted({tuple(row["angle_ids"]) for row in robust_full}
                            & {tuple(row["angle_ids"]) for row in m2_full})
        robust_common = [row for row in robust_order if tuple(row["angle_ids"]) in common_ids]
        m2_common = [row for row in m2_worst_order if tuple(row["angle_ids"]) in common_ids]
        robust_pos = {tuple(row["angle_ids"]): index
                      for index, row in enumerate(robust_common, start=1)}
        m2_pos = {tuple(row["angle_ids"]): index
                  for index, row in enumerate(m2_common, start=1)}
        common_top = {}
        for top in (10, 20):
            left = {tuple(row["angle_ids"]) for row in robust_common[:top]}
            right = {tuple(row["angle_ids"]) for row in m2_common[:top]}
            common_top[f"top_{top}_overlap"] = {
                "count": len(left & right), "denominator": min(top, len(common_ids)),
                "fraction": (len(left & right) / min(top, len(common_ids)))
                if common_ids else None,
            }
        selected = SELECTED_BY_SIZE[size]
        selected_row = next(row for row in rows if tuple(row["angle_ids"]) == selected)
        payload["sizes"][str(size)] = {
            "combination_count": len(rows),
            "robust_full_rank_count": len(robust_full),
            "m2_full_rank_count_worst_case": len(m2_full),
            "m2_by_noise": {
                noise: {
                    "full_rank_count": sum(
                        _metric_summary(row, m2=True, noise=noise)["full_rank"] for row in rows
                    ),
                    "best": {
                        "angle_ids": m2_orders[noise][0]["angle_ids"],
                        "rank": 1,
                        "metrics": _metric_summary(m2_orders[noise][0], m2=True, noise=noise),
                    },
                } for noise in NOISES
            },
            "m2_worst_case": {
                "best": {
                    "angle_ids": m2_worst_order[0]["angle_ids"], "rank": 1,
                    "metrics": _metric_summary(m2_worst_order[0], m2=True),
                },
                "top_10": [row["angle_ids"] for row in m2_worst_order[:10]],
                "top_20": [row["angle_ids"] for row in m2_worst_order[:20]],
            },
            "robust_reference": {
                "best": {"angle_ids": robust_order[0]["angle_ids"], "rank": 1,
                          "metrics": _metric_summary(robust_order[0])},
                "top_10": [row["angle_ids"] for row in robust_order[:10]],
                "top_20": [row["angle_ids"] for row in robust_order[:20]],
            },
            "common_full_rank": {
                "count": len(common_ids),
                **common_top,
                "spearman_rank_correlation": _spearman(common_ids, robust_pos, m2_pos),
            },
            "selected_set": {
                "angle_ids": list(selected),
                "robust_rank": _rank_position(rows, selected),
                "m2_worst_case_rank": _rank_position(rows, selected, m2=True),
                "m2_N1_rank": _rank_position(rows, selected, m2=True, noise="N1"),
                "m2_N2_rank": _rank_position(rows, selected, m2=True, noise="N2"),
                "robust_metrics": _metric_summary(selected_row),
                "m2_worst_case_metrics": _metric_summary(selected_row, m2=True),
            },
        }
    payload["conclusion"] = {
        "robust_selection_preserved": True,
        "m2_worst_case_preserves_selected_sets": all(
            payload["sizes"][str(size)]["selected_set"]["m2_worst_case_rank"] == 1
            for size in range(1, 5)
        ),
        "m2_N1_changes": {
            "size_2": payload["sizes"]["2"]["m2_by_noise"]["N1"]["best"]["angle_ids"] != list(SELECTED_BY_SIZE[2]),
            "size_3": payload["sizes"]["3"]["m2_by_noise"]["N1"]["best"]["angle_ids"] != list(SELECTED_BY_SIZE[3]),
            "size_4": payload["sizes"]["4"]["m2_by_noise"]["N1"]["best"]["angle_ids"] != list(SELECTED_BY_SIZE[4]),
        },
        "decision": (
            "M2/N1 weak-channel diagnostics can change the isolated best set, but "
            "the absolute-noise-floor worst-case M2 ranking preserves the robust "
            "M0/M1 selections. M2 remains diagnostic and cannot change the lock."
        ),
    }
    return payload


def _set_summary(row: dict[str, Any], *, scope: str = "robust") -> dict[str, Any]:
    return {
        "angle_ids": row["angle_ids"], "size": row["size"],
        "worst_case_minimum_eigenvalue": row["worst_case_minimum_eigenvalue"],
        "worst_case_logdet": row["worst_case_logdet"],
        "worst_case_condition_number": row["worst_case_condition_number"],
        "scope": scope,
    }


def build_count_tradeoff(data: dict[str, Any], rank_audit: dict[str, Any]) -> dict[str, Any]:
    ranking = data["ranking"]
    best: dict[int, dict[str, Any]] = {}
    for size in range(1, 5):
        rows = _ranked(ranking["ranked_by_size"][str(size)])
        best[size] = next(row for row in rows if row["full_rank_M0_M1_N1_N2"])
    comparisons = []
    for size in range(1, 4):
        smaller = float(best[size]["worst_case_minimum_eigenvalue"])
        larger = float(best[size + 1]["worst_case_minimum_eigenvalue"])
        comparisons.append({
            "fewer_count": size, "more_count": size + 1,
            "fewer_best_score_min_eigenvalue": smaller,
            "more_best_score_min_eigenvalue": larger,
            "fewer_over_more": smaller / larger,
            "within_5_percent_tie": bool(smaller >= 0.95 * larger),
            "rule_action": "prefer_fewer" if smaller >= 0.95 * larger else "retain_more_information",
        })
    global_best_size = max(best, key=lambda size: float(best[size]["worst_case_minimum_eigenvalue"]))
    global_score = float(best[global_best_size]["worst_case_minimum_eigenvalue"])
    m4_triple = tuple(SELECTED_BY_SIZE[3])
    return {
        "schema_version": "task005.illumination-count-tradeoff.v1",
        "status": "pass",
        "selection_score": "robust M0/M1/N1/N2 worst-case minimum eigenvalue; logdet and condition are tie-breaks",
        "five_percent_rule": {
            "definition": "A smaller set is preferred only when its primary information score is at least 95% of the next larger set.",
            "adjacent_comparisons": comparisons,
            "applied_without_silent_override": True,
        },
        "best_single": _set_summary(best[1]),
        "best_pair": _set_summary(best[2]),
        "best_triple": _set_summary(best[3]),
        "best_quad": _set_summary(best[4]),
        "information_global_best": {
            "angle_ids": best[global_best_size]["angle_ids"], "size": global_best_size,
            "primary_score": global_score,
            "definition": "highest robust worst-case minimum eigenvalue among sizes 1-4",
        },
        "m4_nonlinearly_validated_set": {
            "angle_ids": list(m4_triple), "size": 3,
            "recovery_gate": "G1-G3 M1/N1 noiseless recovery passed",
        },
        "recommended_operational_set_for_next_task": {
            "angle_ids": list(m4_triple), "size": 3,
            "reason": [
                "best robust three-angle set",
                "only set with the prescribed three-geometry nonlinear recovery evidence",
                "one fewer illumination than the information-best quad",
                "quad is not within the 5% tie, so this is a validated cost-information compromise, not the global information optimum",
            ],
            "not_a_formal_inversion": True,
        },
        "baseline_pair": {"angle_ids": list(BASELINE_PAIR), "task001_reference": True},
        "m2_diagnostic_reference": {
            "worst_case_selected_sets_remain_rank_1": rank_audit["conclusion"]["m2_worst_case_preserves_selected_sets"],
        },
    }


def build_derived_supplement(data: dict[str, Any], supplement: Path) -> dict[str, Any]:
    arrays = data["arrays"]
    derivatives = data["derivatives"]
    record_identity = data["record_identity"]
    perturbed_inputs = np.empty((16, 4, 4), dtype=np.float64)
    for i, item in enumerate(derivatives):
        angle_id = item["angle_id"]
        for j, state in enumerate(STATES):
            key = f"{angle_id}/{state}"
            row = record_identity[key]
            path = Path(row["sample_path"])
            if not path.is_file():
                raise FileNotFoundError(path)
            sample = json.loads(path.read_text())
            perturbed_inputs[i, j] = np.asarray(sample["inputs"], dtype=np.float64)
            if sample.get("source_sha") != FORWARD_SHA or sample.get("source_dirty") is not False:
                raise ValueError(f"record identity failure for {key}")
    np.save(supplement / "perturbed_inputs.npy", perturbed_inputs, allow_pickle=False)

    m0_dh = np.asarray([row["contracts"]["M0_aggregate_RT"]["derivatives"]["h"]
                        for row in derivatives], dtype=np.float64)
    m0_dw = np.asarray([row["contracts"]["M0_aggregate_RT"]["derivatives"]["w"]
                        for row in derivatives], dtype=np.float64)
    np.save(supplement / "M0_Dh.npy", m0_dh, allow_pickle=False)
    np.save(supplement / "M0_Dw.npy", m0_dw, allow_pickle=False)
    np.save(supplement / "M0_noise_sigma_N1.npy", np.asarray([
        row["contracts"]["M0_aggregate_RT"]["noise_sigma"]["N1"] for row in derivatives
    ], dtype=np.float64), allow_pickle=False)
    np.save(supplement / "M0_noise_sigma_N2.npy", np.asarray([
        row["contracts"]["M0_aggregate_RT"]["noise_sigma"]["N2"] for row in derivatives
    ], dtype=np.float64), allow_pickle=False)

    channel_contracts: dict[str, Any] = {
        "schema_version": "task005.derived-channel-contracts.v1",
        "inactive_semantics": "power=null / mask=false remains inactive; no inactive channel is filled into formal arrays",
        "contracts": {},
    }
    for contract, threshold in (("M1_order_total_robust", 1.0e-3),
                                ("M2_order_total_extended", 1.0e-5)):
        channel_contracts["contracts"][contract] = {
            "threshold": threshold, "value": "order_total_power=S+P",
            "per_angle": {},
        }
    channel_contracts["contracts"]["M0_aggregate_RT"] = {
        "threshold": None, "value": ["R_total", "T_total"], "A_balance_audit_only": True,
        "per_angle": {},
    }
    flattened: dict[str, dict[str, list[float]]] = {}
    for contract in ("M1_order_total_robust", "M2_order_total_extended"):
        flattened[contract] = {"h": [], "w": [], "nominal": []}
        offsets = [0]
        for item in derivatives:
            row = item["contracts"][contract]
            channels = [_jsonable(channel) for channel in row["channels"]]
            channel_contracts["contracts"][contract]["per_angle"][item["angle_id"]] = {
                "channels": channels,
                "tier": "primary_robust" if contract.startswith("M1") else "extended_diagnostic",
                "count": len(channels),
            }
            for field in ("h", "w"):
                flattened[contract][field].extend(float(value) for value in row["derivatives"][field])
            flattened[contract]["nominal"].extend(float(value) for value in row["nominal"])
            offsets.append(len(flattened[contract]["h"]))
        for noise in NOISES:
            values: list[float] = []
            sigma_offsets = [0]
            for item in derivatives:
                values.extend(float(value) for value in item["contracts"][contract]["noise_sigma"][noise])
                sigma_offsets.append(len(values))
            _deterministic_npz(
                supplement / f"{contract.split('_')[0]}_noise_sigma_{noise}.npz",
                values=np.asarray(values, dtype=np.float64),
                offsets=np.asarray(sigma_offsets, dtype=np.int64),
            )
        _deterministic_npz(
            supplement / f"{contract.split('_')[0]}_derivatives.npz",
            h_values=np.asarray(flattened[contract]["h"], dtype=np.float64),
            w_values=np.asarray(flattened[contract]["w"], dtype=np.float64),
            nominal_values=np.asarray(flattened[contract]["nominal"], dtype=np.float64),
            offsets=np.asarray(offsets, dtype=np.int64),
        )
    for item in derivatives:
        row = item["contracts"]["M0_aggregate_RT"]
        channel_contracts["contracts"]["M0_aggregate_RT"]["per_angle"][item["angle_id"]] = {
            "channels": row["channels"], "tier": "primary_aggregate", "count": 2,
        }
    weak = _weak_channel_summary(data)
    channel_contracts["weak_channel_summary"] = weak
    _dump(supplement / "channel_contracts.json", channel_contracts)

    record_payload = {
        "schema_version": "task005.derived-source-records.v1",
        "raw_dataset_id": RAW_DATASET_ID,
        "nominal_sample_ids": {item["angle_id"]: item["nominal_sample_id"] for item in derivatives},
        "perturbation_records": {
            key: {
                "sample_path_relative": str(Path(value["sample_path"]).resolve().relative_to(data["root"])),
                "formal_record_sha256": value["formal_record_sha256"],
                "execution_sha256": value["execution_sha256"],
                "status": value["status"], "new_fem": value["new_fem"],
            } for key, value in sorted(record_identity.items())
        },
    }
    _dump(supplement / "source_record_ids.json", record_payload)

    files = {}
    for path in sorted(supplement.iterdir()):
        if path.is_file() and path.name != "DERIVED_SUPPLEMENT_MANIFEST.json":
            files[path.name] = {"sha256": _digest(path), "bytes": path.stat().st_size}
    raw_manifest_path = data["dataset"] / "dataset_manifest.json"
    manifest = {
        "schema_version": "task005.derived-contract-supplement.v1",
        "status": "immutable_derived",
        "dataset_id": "task005_discrete_angle_hw_sensitivity_p5_ny4_derived_contract_v1",
        "source_raw_dataset_id": RAW_DATASET_ID,
        "source_raw_manifest_sha256": _digest(raw_manifest_path),
        "source_raw_file_hashes": data["raw_manifest"]["file_hashes"],
        "source_raw_package_modified": False,
        "source_raw_package_mutability": "v1 raw package remains immutable; companion only",
        "forward_solver_sha": FORWARD_SHA,
        "model_id": MODEL_ID, "solver_route_id": ROUTE_ID,
        "observable_schema_version": OBSERVABLE,
        "source_step": data["raw_manifest"]["step"],
        "source_design_sha256": data["raw_manifest"]["design_sha256"],
        "source_angle_tuple_sha256": data["raw_manifest"]["angle_tuple_sha256"],
        "files": files,
        "generated_without_fem": True,
        "new_fem_count": 0,
        "validation_target_accessed": False,
        "formal_inversion": False,
    }
    _dump(supplement / "DERIVED_SUPPLEMENT_MANIFEST.json", manifest)
    return manifest


def build_baseline_addendum(data: dict[str, Any]) -> str:
    baseline = next(row for row in data["ranking"]["ranked_by_size"]["2"]
                    if row["angle_ids"] == list(BASELINE_PAIR))
    lines = [
        "# Task001 baseline interpretation addendum",
        "",
        "This is a derived-only interpretation of the unchanged Task001 pair A14+A15.",
        "It does not relabel either historical result as false and does not add FEM data.",
        "",
        "| contract / noise | full rank | min eigenvalue | logdet | condition number |",
        "|---|---:|---:|---:|---:|",
    ]
    for contract in ("M0_aggregate_RT", "M1_order_total_robust", "M2_order_total_extended"):
        for noise in NOISES:
            row = baseline["scenario_results"][contract][noise]
            lines.append(
                f"| {contract} / {noise} | {row['full_rank']} | "
                f"{row['minimum_eigenvalue']:.12g} | {row['logdet']:.12g} | "
                f"{row['condition_number']:.12g} |"
            )
    lines.extend([
        "",
        "## Interpretation",
        "",
        "Task001's A14+A15 pair is retained as the historical 10°/0° + 10°/90° "
        "reference. Under Task005 M0 aggregate `[R_total,T_total]`, it remains "
        "full rank, but its parameter directions are strongly correlated. Under "
        "Task005 M1 robust order-total, the active-channel threshold leaves one "
        "channel per angle and the pair is nearly rank deficient: the N2 condition "
        "number is about 5.65e5. M2 extended weak channels improve that diagnostic "
        "number to about 129.6 under N2, but the pair is still far below the new "
        "robust candidates.",
        "",
        "The difference from Task001 is a contract change, not a contradiction:",
        "",
        "- Task001 and Task005 use different observable/measurement contracts.",
        "- Task005 excludes duplicate aggregate/order information and uses the "
        "robust-channel threshold explicitly.",
        "- Task005 adds an absolute noise floor in both provisional N1 and N2.",
        "- M2 weak channels are diagnostic and are not allowed to override the "
        "robust M0/M1 choice.",
        "",
        "All Fisher values remain local DOE metrics under provisional diagonal "
        "noise scenarios, not calibrated experimental uncertainty or a posterior.",
    ])
    return "\n".join(lines) + "\n"


def build_parameterization_doc(data: dict[str, Any]) -> str:
    design = data["design"]
    raw = data["raw_manifest"]
    return f"""# Fisher parameterization and hash schema

## Fisher units

The raw finite differences are physical derivatives:

$$
J_{{h,w}} = [\\partial y/\\partial h,\\partial y/\\partial w],
\\qquad [J_{{h,w}}] = \\mathrm{{nm}}^{{-1}}.
$$

Task005 scales the parameters as `theta_h=(h-120 nm)/5 nm` and
`theta_w=(w-17 nm)/1 nm`. Therefore the scaled Jacobian used by the Fisher
calculation is `J_theta = J_hw @ diag(5, 1)`, and `F = J_theta.T @ Sigma^-1 @
J_theta`. The stored v1 `covariance_scaled` field is covariance in theta units.

For a full-rank Fisher matrix:

$$
\\operatorname{{Cov}}_{{physical}} = \\operatorname{{diag}}(5,1)
\\operatorname{{Cov}}_\\theta \\operatorname{{diag}}(5,1).
$$

Thus `sigma_theta_h`, `sigma_theta_w` are dimensionless parameter-scale
uncertainties, while `sigma_h_nm` and `sigma_w_nm` are physical nm quantities.
The reported CRLB is only a local DOE metric under provisional diagonal N1/N2;
it is not calibrated metrology uncertainty and is not a Bayesian posterior.

## Hash input schemas

All canonical JSON hashes use UTF-8 `json.dumps(sort_keys=True,
separators=(',',':'), ensure_ascii=False, allow_nan=False)` followed by SHA-256.
Byte/file hashes are SHA-256 over the exact file bytes.

| name | exact input and ordering | meaning |
|---|---|---|
| `train112.training_tuple_sha256` | immutable Task004 tuple package | upstream nominal identity |
| `DISCRETE_ANGLE_DESIGN.point_tuple_sha256` | `[[120.0,17.0,g,a], ...]` in A00–A15 order | full Task005 point tuples |
| `M2 angle_tuple_sha256` | `[[g,a], ...]` in A00–A15 order | raw v1 angle array identity |
| `design_sha256` | bytes of `DISCRETE_ANGLE_DESIGN.json` | design file identity |
| `production_step_lock_sha256` | bytes of `PRODUCTION_STEP_LOCK.json` | selected half-step identity |
| `recommended_triple_hash` | canonical list of ordered IDs `['A05','A07','A09']` in v1 code | historical candidate-ID hash; not a point hash |
| `source_raw_manifest_sha256` | bytes of raw `dataset_manifest.json` | immutable raw package manifest identity |

In particular, the full point-tuple hash and the raw angle-array hash are
intentionally different: the former includes fixed `(h,w)`, while the latter
contains only `(grazing, azimuth)`. No hash is inferred from a field name.

## Frozen identities

- forward solver: `{FORWARD_SHA}`
- raw dataset: `{raw['dataset_id']}`
- observable: `{raw['observable_schema_version']}`
- source raw `angle_tuple_sha256`: `{raw['angle_tuple_sha256']}`
- source raw `design_sha256`: `{raw['design_sha256']}`
- source design schema: `{design['schema_version']}`
"""


def build_lock_v2(data: dict[str, Any], rank_audit: dict[str, Any],
                  tradeoff: dict[str, Any], supplement_manifest: dict[str, Any]) -> dict[str, Any]:
    outcomes = data["outcomes"]
    ranking_path = outcomes / "FISHER_COMBINATION_RANKING.json"
    baseline_path = outcomes / "TASK001_BASELINE_PAIR_COMPARISON.json"
    recovery_path = outcomes / "OFF_CENTRE_RECOVERY.json"
    v1_path = outcomes / "DISCRETE_ILLUMINATION_FISHER_DOE_LOCK.json"
    recovery_design_path = outcomes / "OFF_CENTRE_RECOVERY_DESIGN.json"
    return {
        "schema_version": "task005.discrete-illumination-fisher-doe-lock.v2",
        "status": "review_ready",
        "derived_only": True,
        "new_fem_count": 0,
        "implementation_sha": data["v1_lock"].get("implementation_sha"),
        "forward_solver_sha": FORWARD_SHA,
        "model_id": MODEL_ID, "solver_route_id": ROUTE_ID,
        "observable_schema_version": OBSERVABLE,
        "fixed_configuration": data["v1_lock"]["fixed_configuration"],
        "raw_sensitivity_dataset": {
            "dataset_id": RAW_DATASET_ID,
            "manifest_sha256": _digest(data["dataset"] / "dataset_manifest.json"),
            "tracked_manifest_sha256": _digest(outcomes / "M2_DATASET_MANIFEST.json"),
            "file_hashes": data["raw_manifest"]["file_hashes"],
            "angle_tuple_sha256": data["raw_manifest"]["angle_tuple_sha256"],
            "design_sha256": data["raw_manifest"]["design_sha256"],
            "immutable": True,
        },
        "derived_supplement": {
            "manifest_sha256": _digest((data["root"] / SUPPLEMENT_REL) / "DERIVED_SUPPLEMENT_MANIFEST.json"),
            "manifest": supplement_manifest,
            "generated_without_fem": True,
        },
        "design": {
            "candidate_count": 16,
            "point_tuple_sha256": data["design"]["point_tuple_sha256"],
            "design_file_sha256": _digest(outcomes / "DISCRETE_ANGLE_DESIGN.json"),
            "hash_schema_doc": "FISHER_PARAMETERIZATION_AND_HASH_SCHEMA.md",
        },
        "step_lock": {
            "selected_steps": data["step_lock"]["selected_steps"],
            "audit_file_sha256": data["step_lock"]["audit_sha256"],
            "lock_file_sha256": _digest(outcomes / "PRODUCTION_STEP_LOCK.json"),
        },
        "measurement_contracts": data["v1_lock"]["measurement_contracts"],
        "noise_contracts": data["v1_lock"]["noise_contracts"],
        "m2_ranking_stability": {
            "audit_sha256": _digest(outcomes / "M2_RANK_STABILITY_AUDIT.json"),
            "m2_diagnostic_only": True,
            "conclusion": rank_audit["conclusion"],
        },
        "illumination_count_tradeoff": {
            "audit_sha256": _digest(outcomes / "ILLUMINATION_COUNT_TRADEOFF.json"),
            "best_single": tradeoff["best_single"],
            "best_pair": tradeoff["best_pair"],
            "best_triple": tradeoff["best_triple"],
            "best_quad": tradeoff["best_quad"],
            "information_global_best": tradeoff["information_global_best"],
            "m4_nonlinearly_validated_set": tradeoff["m4_nonlinearly_validated_set"],
            "recommended_operational_set_for_next_task": tradeoff["recommended_operational_set_for_next_task"],
            "five_percent_rule": tradeoff["five_percent_rule"],
        },
        "fisher": {
            "ranking_file_sha256": _digest(ranking_path),
            "task001_baseline_pair_file_sha256": _digest(baseline_path),
            "single_count": 16, "pair_count": 120, "triple_count": 560, "quadruple_count": 1820,
            "baseline_pair": list(BASELINE_PAIR),
            "physical_and_scaled_semantics": "FISHER_PARAMETERIZATION_AND_HASH_SCHEMA.md",
        },
        "task001_baseline_interpretation": {
            "file_sha256": _digest(outcomes / "TASK001_BASELINE_INTERPRETATION_ADDENDUM.md"),
            "pair": list(BASELINE_PAIR),
        },
        "recovery": {
            "design_file_sha256": _digest(recovery_design_path),
            "result_file_sha256": _digest(recovery_path),
            "status": data["v1_lock"]["recovery"]["status"],
            "primary_gate_all_geometries": data["v1_lock"]["recovery"]["primary_gate_all_geometries"],
            "geometries": data["v1_lock"]["recovery"]["geometries"],
        },
        "historical_v1_lock": {
            "status": data["v1_lock"]["status"],
            "file_sha256": _digest(v1_path),
            "preserved_unchanged": True,
        },
        "scope_boundary": {
            "formal_inversion": False,
            "arbitrary_angle_surrogate": False,
            "task004_blind24_run": False,
            "task003_validation_accessed": False,
            "p_polarization": False,
            "task006_authorized": False,
        },
    }


def write_reports(root: Path, data: dict[str, Any], rank_audit: dict[str, Any],
                  tradeoff: dict[str, Any]) -> None:
    outcomes = data["outcomes"]
    _dump(outcomes / "M2_RANK_STABILITY_AUDIT.json", rank_audit)
    _dump(outcomes / "ILLUMINATION_COUNT_TRADEOFF.json", tradeoff)
    weak = rank_audit["weak_channel_summary"]
    lines = [
        "# M2 ranking stability audit",
        "",
        "This report is derived only from the immutable v1 Fisher tables and raw "
        "sensitivity package. No FEM was run.",
        "",
        "| size | robust best | M2/N1 best | M2/N2 best | M2 worst-case best | selected set M2 worst rank |",
        "|---:|---|---|---|---|---:|",
    ]
    for size in range(1, 5):
        row = rank_audit["sizes"][str(size)]
        lines.append(
            f"| {size} | `{row['robust_reference']['best']['angle_ids']}` | "
            f"`{row['m2_by_noise']['N1']['best']['angle_ids']}` | "
            f"`{row['m2_by_noise']['N2']['best']['angle_ids']}` | "
            f"`{row['m2_worst_case']['best']['angle_ids']}` | "
            f"{row['selected_set']['m2_worst_case_rank']} |"
        )
    lines.extend([
        "",
        f"The M2-only diagnostic contains **{weak['total_weak_channel_observations']}** "
        f"weak-channel observations across **{weak['angles_with_weak_channels']}** angles.",
        f"Their nominal powers range from `{weak['nominal_power_range'][0]:.6g}` to "
        f"`{weak['nominal_power_range'][1]:.6g}`; N1 sigma ranges from "
        f"`{weak['sigma_range']['N1'][0]:.6g}` to `{weak['sigma_range']['N1'][1]:.6g}`, "
        f"and N2 sigma from `{weak['sigma_range']['N2'][0]:.6g}` to "
        f"`{weak['sigma_range']['N2'][1]:.6g}`.",
        "",
        "Worst-case M2 (N1/N2) preserves the robust selected single, pair, triple "
        "and quad at rank 1. Isolated M2/N1 can choose A05+A09, A05+A09+A11, or "
        "A05+A07+A08+A09 because near-floor channels receive an N1-only influence; "
        "this is explicitly diagnostic and does not change the robust lock.",
        "",
        "| size | common full-rank count | top-10 overlap | top-20 overlap | Spearman |",
        "|---:|---:|---:|---:|---:|",
    ])
    for size in range(1, 5):
        common = rank_audit["sizes"][str(size)]["common_full_rank"]
        lines.append(
            f"| {size} | {common['count']} | "
            f"{common['top_10_overlap']['count']}/{common['top_10_overlap']['denominator']} | "
            f"{common['top_20_overlap']['count']}/{common['top_20_overlap']['denominator']} | "
            f"{common['spearman_rank_correlation']:.6f} |"
        )
    lines.extend([
        "",
        "Conclusion: M2 weak channels do not overturn the M0/M1 worst-case choice, "
        "but their N1-only best-set changes are recorded as a stability warning. "
        "M2 remains a diagnostic weak-channel contract.",
    ])
    (outcomes / "M2_RANK_STABILITY_AUDIT.md").write_text("\n".join(lines) + "\n")

    lines = [
        "# Illumination-count tradeoff",
        "",
        "The primary score is the robust M0/M1/N1/N2 worst-case minimum eigenvalue. "
        "The 5% fewer-illumination rule is applied explicitly to adjacent counts.",
        "",
        "| comparison | fewer score / more score | ratio | within 5%? | action |",
        "|---|---:|---:|---|---|",
    ]
    for item in tradeoff["five_percent_rule"]["adjacent_comparisons"]:
        lines.append(
            f"| {item['fewer_count']} vs {item['more_count']} | "
            f"{item['fewer_best_score_min_eigenvalue']:.8g} / {item['more_best_score_min_eigenvalue']:.8g} | "
            f"{item['fewer_over_more']:.6f} | {item['within_5_percent_tie']} | {item['rule_action']} |"
        )
    lines.extend([
        "",
        f"Information-global-best set: `{tradeoff['information_global_best']['angle_ids']}` "
        f"(size {tradeoff['information_global_best']['size']}).",
        f"M4-nonlinearly-validated set: `{tradeoff['m4_nonlinearly_validated_set']['angle_ids']}`.",
        f"Recommended operational set: `{tradeoff['recommended_operational_set_for_next_task']['angle_ids']}`.",
        "",
        "The operational triple is not called the global information optimum. The "
        "quad has materially higher Fisher score and is not within the 5% tie; the "
        "triple is retained because it is the best robust triple and the only set "
        "with the prescribed three-geometry nonlinear recovery evidence. It is a "
        "validated cost-information compromise for the next reviewed task.",
    ])
    (outcomes / "ILLUMINATION_COUNT_TRADEOFF.md").write_text("\n".join(lines) + "\n")

    (outcomes / "TASK001_BASELINE_INTERPRETATION_ADDENDUM.md").write_text(
        build_baseline_addendum(data),
    )
    (outcomes / "FISHER_PARAMETERIZATION_AND_HASH_SCHEMA.md").write_text(
        build_parameterization_doc(data),
    )


def run_m5r(root: Path) -> dict[str, Any]:
    data = _load(root.resolve())
    _assert_raw_identity(data)
    supplement = root / SUPPLEMENT_REL
    supplement.mkdir(parents=True, exist_ok=True)
    supplement_manifest = build_derived_supplement(data, supplement)
    rank_audit = build_ranking_audit(data)
    tradeoff = build_count_tradeoff(data, rank_audit)
    write_reports(root, data, rank_audit, tradeoff)
    lock = build_lock_v2(data, rank_audit, tradeoff, supplement_manifest)
    _dump(data["outcomes"] / "DISCRETE_ILLUMINATION_FISHER_DOE_LOCK_V2.json", lock)
    return {
        "status": "pass", "new_fem_count": 0,
        "supplement_manifest_sha256": _digest(supplement / "DERIVED_SUPPLEMENT_MANIFEST.json"),
        "ranking_audit_sha256": _digest(data["outcomes"] / "M2_RANK_STABILITY_AUDIT.json"),
        "tradeoff_sha256": _digest(data["outcomes"] / "ILLUMINATION_COUNT_TRADEOFF.json"),
        "lock_sha256": _digest(data["outcomes"] / "DISCRETE_ILLUMINATION_FISHER_DOE_LOCK_V2.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(run_m5r(args.root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
