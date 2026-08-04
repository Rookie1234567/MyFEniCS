"""Exploratory Fisher information calculations for the Task005 contracts."""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np

from .design import ANGLE_CANDIDATES, BASELINE_PAIR, FORWARD_SOLVER_SHA, MODEL_ID, ROUTE_ID, canonical_hash
from .sensitivity import CONTRACTS, NOISES, SCALE, noise_sigma


CONTRACT_ALIASES = {
    "M0_aggregate_RT": "M0",
    "M1_order_total_robust": "M1",
    "M2_order_total_extended": "M2",
}


def _jsonable_channels(channels: list[Any]) -> list[Any]:
    return [list(item) if isinstance(item, tuple) else item for item in channels]


def fisher_from_jacobian(jacobian: np.ndarray, nominal: np.ndarray,
                         scenario: str) -> tuple[np.ndarray, np.ndarray]:
    """Build diagonal-noise Fisher matrix and its sigma vector."""

    jacobian = np.asarray(jacobian, dtype=np.float64)
    nominal = np.asarray(nominal, dtype=np.float64)
    sigma = noise_sigma(nominal, scenario)
    # J_hw columns are physical nm derivatives; theta=(dh/5,dw/1), hence
    # each column is multiplied by the corresponding physical scale.
    scaled = jacobian.copy()
    # each column is multiplied by the corresponding physical scale.
    scaled[:, 0] *= SCALE["h"]
    scaled[:, 1] *= SCALE["w"]
    weighted = scaled / sigma[:, None]
    return weighted.T @ weighted, sigma


def matrix_metrics(matrix: np.ndarray, *, eigen_floor: float = 1.0e-14) -> dict[str, Any]:
    matrix = 0.5 * (np.asarray(matrix, dtype=np.float64) + np.asarray(matrix, dtype=np.float64).T)
    eigenvalues = np.linalg.eigvalsh(matrix)
    positive = eigenvalues > eigen_floor
    rank = int(np.count_nonzero(positive))
    full_rank = rank == 2 and bool(np.all(eigenvalues > eigen_floor))
    if full_rank:
        min_eig = float(eigenvalues[0])
        condition = float(eigenvalues[-1] / eigenvalues[0])
        logdet = float(np.log(eigenvalues).sum())
        inverse = np.linalg.inv(matrix)
        trace_inverse = float(np.trace(inverse))
        covariance = inverse.tolist()
        rho = float(inverse[0, 1] / np.sqrt(inverse[0, 0] * inverse[1, 1]))
        crlb = {
            "sigma_theta_h": float(np.sqrt(max(inverse[0, 0], 0.0))),
            "sigma_theta_w": float(np.sqrt(max(inverse[1, 1], 0.0))),
            "sigma_h_nm": float(5.0 * np.sqrt(max(inverse[0, 0], 0.0))),
            "sigma_w_nm": float(np.sqrt(max(inverse[1, 1], 0.0))),
        }
    else:
        min_eig = float(eigenvalues[0]) if len(eigenvalues) else 0.0
        # JSON has no infinity literal.  Keep undefined metrics explicit and
        # let the ranking code treat them as worst-case values.
        condition = None
        logdet = None
        trace_inverse = None
        covariance = None
        rho = None
        crlb = None
    return {
        "rank": rank, "full_rank": full_rank,
        "eigenvalues": eigenvalues.tolist(), "minimum_eigenvalue": min_eig,
        "condition_number": condition, "logdet": logdet,
        "condition_number_is_infinite": not full_rank,
        "logdet_defined": full_rank,
        "trace_inverse": trace_inverse, "covariance_scaled": covariance,
        "parameter_correlation_rho_hw": rho, "crlb": crlb,
        "regularization": {"eigen_floor": eigen_floor, "used_for_inversion": False},
    }


def _angle_payloads(dataset: dict[str, Any], contract: str) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for row in dataset["angles"]:
        values[row["angle_id"]] = row["contracts"][contract]
    return values


def _combo_metrics(dataset: dict[str, Any], combo: tuple[str, ...], contract: str,
                   noise: str) -> dict[str, Any]:
    payloads = _angle_payloads(dataset, contract)
    matrix = np.zeros((2, 2), dtype=np.float64)
    channel_counts = []
    for angle_id in combo:
        row = payloads[angle_id]
        jacobian = np.column_stack((np.asarray(row["derivatives"]["h"], dtype=np.float64),
                                    np.asarray(row["derivatives"]["w"], dtype=np.float64)))
        nominal = np.asarray(row["nominal"], dtype=np.float64)
        local, sigma = fisher_from_jacobian(jacobian, nominal, noise)
        matrix += local
        channel_counts.append(int(jacobian.shape[0]))
    result = matrix_metrics(matrix)
    result.update({"contract": CONTRACT_ALIASES[contract], "noise": noise,
                   "angle_ids": list(combo), "channel_counts": channel_counts,
                   "fisher_matrix": matrix.tolist()})
    return result


def _rank_key(row: dict[str, Any]) -> tuple[Any, ...]:
    # The robust score is only used after the explicit full-rank filters.  A
    # length tie-breaker keeps the preference for fewer illuminations visible.
    logdet = row["worst_case_logdet"]
    condition = row["worst_case_condition_number"]
    return (-float(row["worst_case_minimum_eigenvalue"]),
            -float(logdet) if logdet is not None else float("inf"),
            float(condition) if condition is not None else float("inf"), len(row["angle_ids"]),
            tuple(row["angle_ids"]))


def build_fisher_rankings(dataset: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Enumerate 1--4 angle combinations for M0/M1/M2 and N1/N2."""

    angle_ids = [row[0] for row in ANGLE_CANDIDATES]
    combinations: list[dict[str, Any]] = []
    by_size: dict[str, list[dict[str, Any]]] = {str(size): [] for size in range(1, 5)}
    for size in range(1, 5):
        for combo in itertools.combinations(angle_ids, size):
            scenario_results: dict[str, dict[str, Any]] = {}
            for contract in ("M0_aggregate_RT", "M1_order_total_robust", "M2_order_total_extended"):
                scenario_results[contract] = {
                    noise: _combo_metrics(dataset, combo, contract, noise) for noise in NOISES
                }
            robust_views = [scenario_results[contract][noise] for contract in
                            ("M0_aggregate_RT", "M1_order_total_robust") for noise in NOISES]
            row = {
                "angle_ids": list(combo), "size": size,
                "full_rank_M0_M1_N1_N2": bool(all(item["full_rank"] for item in robust_views)),
                "worst_case_minimum_eigenvalue": float(min(item["minimum_eigenvalue"] for item in robust_views)),
                "worst_case_logdet": (float(min(item["logdet"] for item in robust_views))
                                      if all(item["logdet"] is not None for item in robust_views) else None),
                "worst_case_condition_number": (float(max(item["condition_number"] for item in robust_views))
                                                if all(item["condition_number"] is not None for item in robust_views) else None),
                "scenario_results": scenario_results,
            }
            by_size[str(size)].append(row)
            combinations.append(row)
    robust = [row for row in combinations if row["full_rank_M0_M1_N1_N2"]]
    robust_sorted = sorted(robust, key=_rank_key)
    triples = [row for row in robust_sorted if row["size"] == 3]
    recommended = triples[0] if triples else None
    ranking = {
        "schema_version": "task005.fisher-combination-ranking.v1",
        "forward_solver_sha": FORWARD_SOLVER_SHA, "model_id": MODEL_ID,
        "solver_route_id": ROUTE_ID, "dataset_id": dataset.get("dataset_id"),
        "parameter_scaling": {"theta_h": "(h-h0)/5nm", "theta_w": "(w-w0)/1nm"},
        "noise_contracts": {
            "N1": "sqrt((0.01*y)^2+(1e-4)^2)",
            "N2": "sqrt((0.02*y)^2+(5e-4)^2)",
            "status": "provisional diagonal DOE scenarios; not experimental covariance",
        },
        "measurement_contracts": {
            "M0": "aggregate_RT=[R_total,T_total]; A_balance audit only",
            "M1": "active fixed-order total power threshold 1e-3; aggregate excluded",
            "M2": "active fixed-order total power threshold 1e-5; absolute noise floor",
        },
        "combination_counts": {str(size): len(by_size[str(size)]) for size in range(1, 5)},
        "ranked_by_size": {
            size: sorted(rows, key=_rank_key) for size, rows in by_size.items()
        },
        "robust_full_rank_count": len(robust_sorted),
        "recommended_triple": recommended,
        "selection_criteria": [
            "full rank for M0 and M1 under N1 and N2",
            "maximize worst-case minimum eigenvalue, then logdet, then minimize condition",
            "prefer fewer angles only within the declared 5 percent information tie",
        ],
        "formal_inversion": False,
    }
    baseline = next((row for row in combinations if tuple(row["angle_ids"]) == BASELINE_PAIR), None)
    comparison = {
        "schema_version": "task005.task001-baseline-pair-comparison.v1",
        "baseline_pair": list(BASELINE_PAIR), "baseline": baseline,
        "pair_rank_position_M0_M1": (
            1 + [row["angle_ids"] for row in sorted(
                [item for item in combinations if item["size"] == 2 and item["full_rank_M0_M1_N1_N2"]],
                key=_rank_key)].index(list(BASELINE_PAIR))
            if baseline and baseline["full_rank_M0_M1_N1_N2"] else None),
        "compared_against": "all Task005 pairs and the robust triple/quad candidate tables",
        "forward_solver_sha": FORWARD_SOLVER_SHA,
    }
    return ranking, comparison


def write_fisher_outputs(*, output_dir: Path, dataset: dict[str, Any]) -> dict[str, Any]:
    ranking, baseline = build_fisher_rankings(dataset)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "FISHER_COMBINATION_RANKING.json").write_text(
        json.dumps(ranking, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
    )
    (output_dir / "TASK001_BASELINE_PAIR_COMPARISON.json").write_text(
        json.dumps(baseline, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
    )
    singles = {
        "schema_version": "task005.fisher-single-angle.v1",
        "angles": [{"angle_id": row[0], "metrics": {
            contract: {noise: _combo_metrics(dataset, (row[0],), contract, noise)
                       for noise in NOISES}
            for contract in ("M0_aggregate_RT", "M1_order_total_robust", "M2_order_total_extended")
        }} for row in ANGLE_CANDIDATES],
        "forward_solver_sha": FORWARD_SOLVER_SHA,
    }
    (output_dir / "FISHER_SINGLE_ANGLE.json").write_text(
        json.dumps(singles, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
    )
    return {"ranking": ranking, "baseline": baseline, "singles": singles}
