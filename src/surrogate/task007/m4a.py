"""Task007 M4A robustness and independence audits.

This module adds companion evidence only.  It consumes the frozen Task006
Legendre-3 oracle and the immutable M3 records; it never calls a FEM runner
and never writes to Task006 artifacts.
"""

from __future__ import annotations

import hashlib
import json
import re
import warnings
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import differential_evolution, minimize

from ..models import ExactARDGP
from .continuous import (
    CONTRACTS,
    DOMAIN_MAX,
    DOMAIN_MIN,
    M3_EI_SWITCH_THRESHOLD,
    M3_MAX_ONLINE_QUERIES,
    M3_MAP_HEIGHT_TOLERANCE_NM,
    M3_MAP_WIDTH_TOLERANCE_NM,
    NOISE_CONFIG,
    NOISE_SCENARIOS,
    OFFGRID_TARGETS,
    Legendre3ResponseOracle,
    array_hash,
    file_sha256,
    initialization_sets,
    noise_sigma,
    objective_scalar,
    objective_values,
    scale_geometry,
    scale_to_domain,
    within_map_tolerance,
)


M4_DE_MAXITER = 120
M4_DE_POPSIZE = 10
M4_DE_TOL = 1.0e-9
M4_MAP_F_TOL = 1.0e-6
M4_MAP_H_TOL = 0.02
M4_MAP_W_TOL = 0.005
M4_RESPONSE_BLIND_MAX_QUERIES = 20
M4_RESPONSE_BLIND_EI_THRESHOLD = 1.0e-3
M4_RESPONSE_BLIND_IMPROVEMENT_THRESHOLD = 1.0e-3
M4_RESPONSE_BLIND_LOW_EI_CONSECUTIVE = 2
M4_RESPONSE_BLIND_STAGNANT_CONSECUTIVE = 3
M4_MC_REPLICATES = 10
M4_MC_SEED_BASE = {"N1": 910000, "N2": 920000}
M4_MAP_SEED_BASE = 610000
M4_WARNING_METHODS = ("P0_cold5", "P1_sobol12", "P2_sobol37", "P3_train37")


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _m3_targets(outcomes: Path) -> dict[tuple[int, str, str], dict[str, Any]]:
    data = json.loads((outcomes / "M3_TARGETS.json").read_text())
    rows: dict[tuple[int, str, str], dict[str, Any]] = {}
    for target in data["targets"]:
        index = int(target["target_index"])
        for contract in CONTRACTS:
            for scenario in NOISE_SCENARIOS:
                rows[(index, contract, scenario)] = target["scenarios"][contract][scenario]
    return rows


def _m3_maps(outcomes: Path) -> dict[tuple[int, str, str], dict[str, Any]]:
    rows = _m3_targets(outcomes)
    return {key: value["oracle_map"] for key, value in rows.items()}


def fixed_measurement(oracle: Legendre3ResponseOracle, point: np.ndarray,
                      contract: str, scenario: str, seed: int) -> dict[str, Any]:
    true_response = oracle.predict(np.asarray(point, dtype=np.float64).reshape(1, 2))[contract][0]
    sigma = noise_sigma(true_response, scenario)
    noise = np.random.default_rng(int(seed)).normal(0.0, sigma)
    measurement = true_response + noise
    return {
        "geometry": np.asarray(point, dtype=np.float64).tolist(),
        "true_response": np.asarray(true_response, dtype=np.float64).tolist(),
        "noise_sigma": np.asarray(sigma, dtype=np.float64).tolist(),
        "noise": np.asarray(noise, dtype=np.float64).tolist(),
        "measurement": np.asarray(measurement, dtype=np.float64).tolist(),
        "true_response_hash": array_hash(true_response),
        "measurement_hash": array_hash(measurement),
        "noise_seed": int(seed),
    }


def independent_map(oracle: Legendre3ResponseOracle, measurement: np.ndarray,
                    contract: str, scenario: str, seed: int) -> dict[str, Any]:
    """Independent global search used only for MAP stability evidence."""
    bounds = [(float(DOMAIN_MIN[0]), float(DOMAIN_MAX[0])),
              (float(DOMAIN_MIN[1]), float(DOMAIN_MAX[1]))]
    de = differential_evolution(
        lambda point: objective_scalar(oracle, point, measurement, contract, scenario),
        bounds=bounds, seed=int(seed), maxiter=M4_DE_MAXITER, popsize=M4_DE_POPSIZE,
        tol=M4_DE_TOL, polish=False, updating="immediate", workers=1,
    )
    polished = minimize(
        lambda point: objective_scalar(oracle, point, measurement, contract, scenario),
        np.asarray(de.x, dtype=np.float64), method="L-BFGS-B", bounds=bounds,
        options={"maxiter": 800, "ftol": 1.0e-14, "gtol": 1.0e-10},
    )
    if float(polished.fun) <= float(de.fun):
        selected = polished
        selected_method = "differential_evolution_bounded_LBFGSB_polish"
    else:
        selected = de
        selected_method = "differential_evolution"
    return {
        "method": selected_method,
        "seed": int(seed),
        "de_success": bool(de.success), "de_message": str(de.message),
        "de_nit": int(de.nit), "de_nfev": int(de.nfev), "de_geometry": np.asarray(de.x).tolist(),
        "de_F": float(de.fun),
        "polish_success": bool(polished.success), "polish_message": str(polished.message),
        "polish_nit": int(polished.nit), "polish_nfev": int(getattr(polished, "nfev", 0)),
        "map_geometry": np.asarray(selected.x, dtype=np.float64).tolist(),
        "map_F": float(selected.fun),
        "map_log10F": float(np.log10(float(selected.fun) + 1.0e-12)),
    }


def map_stability_rows(oracle: Legendre3ResponseOracle, outcomes: Path) -> list[dict[str, Any]]:
    old_maps = _m3_maps(outcomes)
    targets = _m3_targets(outcomes)
    rows: list[dict[str, Any]] = []
    for index in range(len(OFFGRID_TARGETS)):
        for contract_index, contract in enumerate(CONTRACTS):
            for scenario_index, scenario in enumerate(NOISE_SCENARIOS):
                old = old_maps[(index, contract, scenario)]
                measurement = np.asarray(targets[(index, contract, scenario)]["measurement"], dtype=np.float64)
                independent = independent_map(
                    oracle, measurement, contract, scenario,
                    M4_MAP_SEED_BASE + index * 100 + contract_index * 10 + scenario_index,
                )
                old_point = np.asarray(old["map_geometry"], dtype=np.float64)
                new_point = np.asarray(independent["map_geometry"], dtype=np.float64)
                f_diff = abs(float(independent["map_F"]) - float(old["map_F"]))
                h_diff, w_diff = np.abs(new_point - old_point)
                f_gate = f_diff <= M4_MAP_F_TOL * max(1.0, abs(float(old["map_F"])))
                coord_gate = bool(h_diff <= M4_MAP_H_TOL and w_diff <= M4_MAP_W_TOL)
                rows.append({
                    "target_index": index, "geometry": list(OFFGRID_TARGETS[index]),
                    "contract": contract, "noise_scenario": scenario,
                    "old_map_geometry": old_point.tolist(), "old_map_F": float(old["map_F"]),
                    "independent_map": independent,
                    "objective_abs_difference": float(f_diff),
                    "height_abs_difference_nm": float(h_diff),
                    "width_abs_difference_nm": float(w_diff),
                    "objective_gate": bool(f_gate), "coordinate_gate": coord_gate,
                    "objective_equivalent_coordinate_difference": bool(f_gate and not coord_gate),
                    "gate_pass": bool(f_gate and coord_gate),
                })
    return rows


class IndependentGP:
    """Standalone M4A GP fit, not the M3 ObjectiveGP/acquisition runner."""

    def __init__(self, seed: int):
        self.seed = int(seed)
        self.model: ExactARDGP | None = None
        self.selected_jitter: float | None = None
        self.candidates: list[dict[str, Any]] = []

    def fit(self, x: np.ndarray, y: np.ndarray) -> "IndependentGP":
        self.candidates = []
        best = None
        best_lml = -np.inf
        for jitter in (1.0e-10, 1.0e-8):
            model = ExactARDGP(jitter=jitter, optimizer_restarts=8,
                               random_state=self.seed, normalize_y=True)
            # ExactARDGP stores and re-emits warnings; capture the emission here
            # while retaining all warning rows in metadata.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model.fit(np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64))
            metadata = model.metadata()
            self.candidates.append({"jitter": jitter, "metadata": metadata})
            if best is None or float(model.log_marginal_likelihood_) > best_lml:
                best, best_lml = model, float(model.log_marginal_likelihood_)
                self.selected_jitter = float(jitter)
        self.model = best
        return self

    def predict(self, x: np.ndarray, *, return_std: bool = False):
        if self.model is None:
            raise RuntimeError("independent GP is not fitted")
        return self.model.predict(np.asarray(x, dtype=np.float64), return_std=return_std)

    def metadata(self) -> dict[str, Any]:
        if self.model is None:
            raise RuntimeError("independent GP is not fitted")
        return {
            "kernel": "Matern-5/2-ARD", "mean": "constant", "normalize_y": True,
            "optimizer_starts": 8, "jitter_candidates": [1.0e-10, 1.0e-8],
            "selected_jitter": self.selected_jitter,
            "selected": self.model.metadata(), "jitter_candidates_metadata": self.candidates,
        }


def independent_ei(mean: np.ndarray, std: np.ndarray, best: float) -> np.ndarray:
    from scipy.special import ndtr

    mu = np.asarray(mean, dtype=np.float64)
    sigma = np.asarray(std, dtype=np.float64)
    result = np.zeros_like(mu)
    active = sigma > 1.0e-14
    z = np.zeros_like(mu)
    z[active] = (float(best) - mu[active]) / sigma[active]
    result[active] = ((float(best) - mu[active]) * ndtr(z[active])
                      + sigma[active] * np.exp(-0.5 * z[active] ** 2) / np.sqrt(2.0 * np.pi))
    return np.maximum(result, 0.0)


def _independent_ei_scalar(gp: IndependentGP, point: np.ndarray, best: float) -> float:
    mean, std = gp.predict(np.asarray(point, dtype=np.float64).reshape(1, 2), return_std=True)
    return float(independent_ei(mean, std, best)[0])


def independent_acquisition(gp: IndependentGP, best_log10f: float, seed: int) -> dict[str, Any]:
    axis = np.linspace(-1.0, 1.0, 61)
    grid = np.asarray([(h, w) for h in axis for w in axis], dtype=np.float64)
    mean, std = gp.predict(grid, return_std=True)
    ei = independent_ei(mean, std, best_log10f)
    order = np.argsort(-ei, kind="mergesort")
    candidates: list[tuple[float, np.ndarray, str]] = []
    local_rows: list[dict[str, Any]] = []
    for index in order[:8]:
        start = grid[int(index)]
        result = minimize(
            lambda point: -_independent_ei_scalar(gp, point, best_log10f), start,
            method="L-BFGS-B", bounds=((-1.0, 1.0), (-1.0, 1.0)),
            options={"maxiter": 100, "ftol": 1.0e-12, "gtol": 1.0e-10},
        )
        point = np.asarray(result.x, dtype=np.float64)
        point_ei = _independent_ei_scalar(gp, point, best_log10f)
        candidates.append((point_ei, point, "continuous_EI"))
        local_rows.append({"start": start.tolist(), "x": point.tolist(), "ei": point_ei,
                           "success": bool(result.success), "status": int(result.status),
                           "message": str(result.message), "nit": int(result.nit)})
    grid_best = float(ei[int(order[0])])
    selected = max(candidates, key=lambda item: (item[0], -item[1][0], -item[1][1]))
    fallback = False
    fallback_rows: list[dict[str, Any]] = []
    if grid_best < M4_RESPONSE_BLIND_EI_THRESHOLD:
        fallback = True
        for index in np.argsort(mean, kind="mergesort")[:8]:
            start = grid[int(index)]
            result = minimize(
                lambda point: float(gp.predict(np.asarray(point, dtype=np.float64).reshape(1, 2))[0]),
                start, method="L-BFGS-B", bounds=((-1.0, 1.0), (-1.0, 1.0)),
                options={"maxiter": 150, "ftol": 1.0e-12, "gtol": 1.0e-10},
            )
            point = np.asarray(result.x, dtype=np.float64)
            posterior_mean = float(gp.predict(point.reshape(1, 2))[0])
            fallback_rows.append({"start": start.tolist(), "x": point.tolist(),
                                  "posterior_mean": posterior_mean,
                                  "success": bool(result.success), "status": int(result.status),
                                  "message": str(result.message), "nit": int(result.nit)})
        if fallback_rows:
            row = min(fallback_rows, key=lambda item: (item["posterior_mean"], item["x"][0], item["x"][1]))
            point = np.asarray(row["x"], dtype=np.float64)
            selected = (_independent_ei_scalar(gp, point, best_log10f), point,
                        "bounded_local_refinement")
    return {
        "grid_best_ei": grid_best, "ei_switch_threshold": M4_RESPONSE_BLIND_EI_THRESHOLD,
        "fallback_used": fallback, "local_ei_optimizers": local_rows,
        "fallback_local_refinement": fallback_rows,
        "selected_scaled": selected[1].tolist(), "selected_geometry": scale_to_domain(selected[1]).tolist(),
        "selected_ei": float(selected[0]), "selected_mode": selected[2],
        "candidate_order_hash": canonical_hash(order.tolist()), "acquisition_seed": int(seed),
    }


def deduplicate_scaled(point: np.ndarray, observed_scaled: np.ndarray) -> tuple[np.ndarray, bool]:
    candidate = np.asarray(point, dtype=np.float64)
    if len(observed_scaled) == 0 or np.min(np.linalg.norm(observed_scaled - candidate[None, :], axis=1)) > 1.0e-8:
        return candidate, False
    for axis in (0, 1):
        direction = 1.0 if candidate[axis] < 1.0 else -1.0
        shifted = candidate.copy()
        shifted[axis] = np.clip(shifted[axis] + direction * 1.0e-3, -1.0, 1.0)
        if np.min(np.linalg.norm(observed_scaled - shifted[None, :], axis=1)) > 1.0e-8:
            return shifted, True
    return candidate, True


def independent_bo(initial_points: np.ndarray, oracle: Legendre3ResponseOracle,
                   measurement: np.ndarray, contract: str, scenario: str, seed: int,
                   map_point: np.ndarray | None = None, map_f: float | None = None,
                   response_blind: bool = False, record_steps: bool = False) -> dict[str, Any]:
    initial = np.asarray(initial_points, dtype=np.float64).reshape(-1, 2)
    observed = initial.copy()
    values = objective_values(oracle, observed, measurement, contract, scenario)
    queries: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    low_ei_streak = 0
    stagnation_streak = 0
    improvements: list[float] = []
    stop_reason = "max_online_queries"
    for step in range(M4_RESPONSE_BLIND_MAX_QUERIES):
        gp = IndependentGP(seed=int(seed) + step * 31).fit(scale_geometry(observed), np.log10(values + 1.0e-12))
        metadata = gp.metadata()
        acquisition = independent_acquisition(gp, float(np.min(np.log10(values + 1.0e-12))), int(seed) + step)
        if acquisition["grid_best_ei"] < M4_RESPONSE_BLIND_EI_THRESHOLD:
            low_ei_streak += 1
        else:
            low_ei_streak = 0
        stop_row = {
            "step": step, "observed_count": len(observed),
            "grid_best_ei": acquisition["grid_best_ei"],
            "low_ei_streak": low_ei_streak, "stagnation_streak": stagnation_streak,
        }
        updates.append({"step": step, "observed_count": len(observed),
                        "observed_geometry_hash": array_hash(observed),
                        "acquisition": acquisition if record_steps else {
                            "grid_best_ei": acquisition["grid_best_ei"],
                            "selected_ei": acquisition["selected_ei"],
                            "selected_mode": acquisition["selected_mode"],
                            "fallback_used": acquisition["fallback_used"],
                        },
                        "gp_metadata": metadata if record_steps else {
                            "selected_jitter": metadata["selected_jitter"],
                            "selected_lml": metadata["selected"]["log_marginal_likelihood"],
                        }})
        if response_blind and low_ei_streak >= M4_RESPONSE_BLIND_LOW_EI_CONSECUTIVE and stagnation_streak >= M4_RESPONSE_BLIND_STAGNANT_CONSECUTIVE:
            stop_reason = "response_blind_ei_and_stagnation_rule"
            updates[-1]["response_blind_stop"] = stop_row
            break
        selected_scaled, duplicate = deduplicate_scaled(np.asarray(acquisition["selected_scaled"]), scale_geometry(observed))
        selected_geometry = scale_to_domain(selected_scaled)
        value = objective_scalar(oracle, selected_geometry, measurement, contract, scenario)
        observed = np.vstack((observed, selected_geometry))
        values = np.append(values, value)
        old_best_log = float(np.min(np.log10(values[:-1] + 1.0e-12)))
        new_best_log = float(np.min(np.log10(values + 1.0e-12)))
        improvement = max(0.0, old_best_log - new_best_log)
        improvements.append(improvement)
        stagnation_streak = stagnation_streak + 1 if improvement < M4_RESPONSE_BLIND_IMPROVEMENT_THRESHOLD else 0
        query = {
            "query_step": step, "geometry": selected_geometry.tolist(),
            "scaled_geometry": selected_scaled.tolist(), "objective_F": float(value),
            "objective_log10F": float(np.log10(value + 1.0e-12)),
            "duplicate_resolution": bool(duplicate), "best_log_improvement": float(improvement),
        }
        if record_steps:
            query["acquisition"] = acquisition
        queries.append(query)
        if map_point is not None and not response_blind:
            # M3's benchmark stop is based on the best actually evaluated point,
            # not necessarily the just-selected query.  Response-blind runs
            # never use this branch to decide whether to issue another query.
            best_now = int(np.argmin(values))
            if within_map_tolerance(observed[best_now], np.asarray(map_point)):
                stop_reason = "entered_MAP_tolerance"
                break
    map_hits = [row["query_step"] + 1 for row in queries
                if map_point is not None and within_map_tolerance(np.asarray(row["geometry"]), np.asarray(map_point))]
    best_index = int(np.argmin(values))
    result: dict[str, Any] = {
        "initial_count": int(len(initial)), "initial_points": initial.tolist(),
        "initial_objective_F": np.asarray(values[:len(initial)]).tolist(),
        "initial_geometry_hash": array_hash(initial), "initial_target_leakage": False,
        "seed": int(seed), "contract": contract, "noise_scenario": scenario,
        "queries": queries, "updates": updates, "online_query_count": len(queries),
        "queries_to_MAP": min(map_hits) if map_hits else None,
        "best_evaluated_geometry": observed[best_index].tolist(),
        "best_evaluated_F": float(values[best_index]),
        "best_evaluated_log10F": float(np.log10(values[best_index] + 1.0e-12)),
        "map_geometry": np.asarray(map_point).tolist() if map_point is not None else None,
        "map_F": float(map_f) if map_f is not None else None,
        "within_MAP_tolerance": bool(map_point is not None and within_map_tolerance(observed[best_index], np.asarray(map_point))),
        "stop_reason": stop_reason, "response_blind_stop_uses_hidden_map": False,
        "response_blind_rule": {
            "max_online_queries": M4_RESPONSE_BLIND_MAX_QUERIES,
            "ei_threshold": M4_RESPONSE_BLIND_EI_THRESHOLD,
            "low_ei_consecutive": M4_RESPONSE_BLIND_LOW_EI_CONSECUTIVE,
            "improvement_threshold": M4_RESPONSE_BLIND_IMPROVEMENT_THRESHOLD,
            "stagnant_consecutive": M4_RESPONSE_BLIND_STAGNANT_CONSECUTIVE,
        },
    }
    return result


def _warning_category(category: str, message: str) -> str:
    lower = message.lower()
    if "optimal value found" in lower and "bound" in lower:
        return "hyperparameter_boundary_convergence"
    if "converge" in lower:
        return "other_convergence_warning"
    return category


def _selected_kernel_summary(metadata: dict[str, Any]) -> dict[str, Any]:
    selected = metadata["selected"]
    fitted = selected["fitted_kernel"]
    constant = None
    length_scales: list[float] = []
    # ExactARDGP exposes the fitted sklearn model only internally; parse the
    # stable printed kernel to keep this audit independent of private fields.
    match = re.search(r"([0-9.eE+-]+)\*\*2 \* Matern\(length_scale=\[([^]]+)\]", fitted)
    if match:
        constant = float(match.group(1)) ** 2
        length_scales = [float(value.strip()) for value in match.group(2).split(",")]
    return {"fitted_kernel": fitted, "constant_value": constant,
            "length_scales": length_scales,
            "selected_jitter": metadata["selected_jitter"],
            "selected_lml": selected["log_marginal_likelihood"]}


def warning_taxonomy(oracle: Legendre3ResponseOracle, outcomes: Path) -> dict[str, Any]:
    replay = json.loads((outcomes / "M3_BO_REPLAY.json").read_text())
    groups: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    category_counts: Counter[str] = Counter()
    warning_rows: list[dict[str, Any]] = []
    for target in replay["targets"]:
        index = int(target["target_index"])
        for contract in CONTRACTS:
            for scenario in NOISE_SCENARIOS:
                block = target["scenarios"][contract][scenario]
                measurement = np.asarray(_m3_targets(outcomes)[(index, contract, scenario)]["measurement"], dtype=np.float64)
                for method in M4_WARNING_METHODS:
                    run = block[method]
                    observed = np.asarray(run["initial_points"], dtype=np.float64)
                    values = np.asarray(run["initial_objective_F"], dtype=np.float64)
                    for step, query in enumerate(run["queries"]):
                        gp = IndependentGP(seed=int(run["seed"]) + step * 31).fit(
                            scale_geometry(observed), np.log10(values + 1.0e-12))
                        metadata = gp.metadata()
                        selected = metadata["selected"]
                        warnings_here = [item for opt in selected["optimization_runs"] for item in opt["warnings"]]
                        categories = Counter(_warning_category(item["category"], item["message"]) for item in warnings_here)
                        for category, count in categories.items():
                            category_counts[category] += int(count)
                        collisions = [name for opt in selected["optimization_runs"] for name in opt["boundary_collisions"]]
                        key = (method, contract, scenario, len(observed))
                        group = groups.setdefault(key, {
                            "method": method, "contract": contract, "noise_scenario": scenario,
                            "observed_count": len(observed), "fit_count": 0, "warning_count": 0,
                            "boundary_collision_count": 0, "jitter_counts": Counter(),
                            "warning_categories": Counter(), "length_scales": [], "constant_values": [],
                            "lml_values": [], "representative": None,
                        })
                        group["fit_count"] += 1
                        group["warning_count"] += len(warnings_here)
                        group["boundary_collision_count"] += len(collisions)
                        group["jitter_counts"][str(metadata["selected_jitter"])] += 1
                        group["warning_categories"].update(categories)
                        kernel_summary = _selected_kernel_summary(metadata)
                        group["length_scales"].append(kernel_summary["length_scales"])
                        group["constant_values"].append(kernel_summary["constant_value"])
                        group["lml_values"].append(kernel_summary["selected_lml"])
                        if group["representative"] is None and warnings_here:
                            group["representative"] = {
                                "target_index": index, "step": step,
                                "observed_geometry_hash": array_hash(observed),
                                "warning_rows": warnings_here[:8], "boundary_collisions": collisions,
                                "kernel": kernel_summary,
                            }
                        warning_rows.append({
                            "target_index": index, "method": method, "contract": contract,
                            "noise_scenario": scenario, "step": step,
                            "observed_count": len(observed), "selected_jitter": metadata["selected_jitter"],
                            "warning_count": len(warnings_here), "boundary_collisions": collisions,
                            "warning_categories": dict(categories), "kernel": kernel_summary,
                        })
                        observed = np.vstack((observed, np.asarray(query["geometry"], dtype=np.float64)))
                        values = np.append(values, float(query["objective_F"]))
    def finite_stats(rows: list[list[float] | None]) -> dict[str, Any]:
        values = np.asarray([row for row in rows if row], dtype=np.float64)
        return {"median": np.median(values, axis=0).tolist() if len(values) else [],
                "min": np.min(values, axis=0).tolist() if len(values) else [],
                "max": np.max(values, axis=0).tolist() if len(values) else []}
    group_rows: list[dict[str, Any]] = []
    for key in sorted(groups):
        group = groups[key]
        group_rows.append({
            "method": group["method"], "contract": group["contract"],
            "noise_scenario": group["noise_scenario"], "observed_count": group["observed_count"],
            "fit_count": group["fit_count"], "warning_count": group["warning_count"],
            "boundary_collision_count": group["boundary_collision_count"],
            "selected_jitter_counts": dict(group["jitter_counts"]),
            "warning_categories": dict(group["warning_categories"]),
            "length_scale_stats": finite_stats(group["length_scales"]),
            "constant_value_stats": finite_stats([[x] if x is not None else [] for x in group["constant_values"]]),
            "lml_stats": finite_stats([[x] for x in group["lml_values"]]),
            "representative": group["representative"],
        })
    return {
        "schema_version": "task007.m4-gp-warning-taxonomy.v1", "status": "complete",
        "source_trace": "M3_BO_REPLAY.json",
        "fit_count": len(warning_rows), "warning_count": sum(row["warning_count"] for row in warning_rows),
        "boundary_collision_count": sum(len(row["boundary_collisions"]) for row in warning_rows),
        "warning_category_totals": dict(category_counts), "groups": group_rows,
    }


def unique_geometry_count(points: np.ndarray) -> int:
    return int(np.unique(np.round(np.asarray(points, dtype=np.float64), decimals=12), axis=0).shape[0])


def initialization_cost_study(oracle: Legendre3ResponseOracle, outcomes: Path,
                              map_rows: list[dict[str, Any]]) -> dict[str, Any]:
    sets = initialization_sets(oracle.geometry)
    sets.update({
        "train37_plus_sobol6": np.vstack((sets["train37"], sets["sobol37"][:6])),
        "train37_plus_sobol12": np.vstack((sets["train37"], sets["sobol37"][:12])),
    })
    m3_targets = _m3_targets(outcomes)
    map_by_key = {(row["target_index"], row["contract"], row["noise_scenario"]): row
                  for row in map_rows}
    result_rows: list[dict[str, Any]] = []
    for init_name in ("train37", "sobol12", "sobol37", "train37_plus_sobol6", "train37_plus_sobol12"):
        initial = sets[init_name]
        initial_count = unique_geometry_count(initial)
        new_geometry_count = sum(
            not np.any(np.all(np.isclose(point, oracle.geometry, atol=1.0e-12), axis=1))
            for point in np.unique(np.round(initial, decimals=12), axis=0)
        )
        for contract in CONTRACTS:
            for scenario in NOISE_SCENARIOS:
                runs: list[dict[str, Any]] = []
                for index in range(len(OFFGRID_TARGETS)):
                    row = m3_targets[(index, contract, scenario)]
                    measurement = np.asarray(row["measurement"], dtype=np.float64)
                    map_row = map_by_key[(index, contract, scenario)]
                    runs.append(independent_bo(
                        initial, oracle, measurement, contract, scenario,
                        seed=730000 + index * 100 + CONTRACTS.index(contract) * 10 + NOISE_SCENARIOS.index(scenario),
                        map_point=np.asarray(map_row["independent_map"]["map_geometry"]),
                        map_f=float(map_row["independent_map"]["map_F"]),
                    ))
                queries = np.asarray([run["online_query_count"] for run in runs], dtype=np.float64)
                hits = np.asarray([run["within_MAP_tolerance"] for run in runs], dtype=bool)
                for run_index, run in enumerate(runs):
                    result_rows.append({"initialization": init_name, "contract": contract,
                                        "noise_scenario": scenario, "target_index": run_index,
                                        "online_query_count": run["online_query_count"],
                                        "queries_to_MAP": run["queries_to_MAP"],
                                        "within_MAP_tolerance": run["within_MAP_tolerance"]})
                result_rows.append({
                    "initialization": init_name, "contract": contract, "noise_scenario": scenario,
                    "summary": True, "initial_count": initial_count,
                    "new_geometry_count_relative_train37": int(new_geometry_count),
                    "new_fem_runs_relative_train37": int(new_geometry_count * 3),
                    "median_online_queries": float(np.median(queries)),
                    "p90_online_queries": float(np.percentile(queries, 90)),
                    "max_online_queries": int(np.max(queries)),
                    "map_hit_fraction": float(np.mean(hits)),
                    "single_measurement_median_total_evaluations": float(initial_count + np.median(queries)),
                    "amortized_total_evaluations_1": float(initial_count + np.median(queries)),
                    "amortized_total_evaluations_10": float(initial_count + 10.0 * np.median(queries)),
                    "amortized_total_evaluations_100": float(initial_count + 100.0 * np.median(queries)),
                })
    return {
        "schema_version": "task007.m4-initialization-cost.v1", "status": "complete",
        "initialization_contract": {
            "I0": "existing train37", "I1": "Sobol12", "I2": "Sobol37",
            "I3": "train37 + Sobol6", "I4": "train37 + Sobol12",
            "new_physical_fem_runs": "new geometry count relative to existing train37 times 3 fixed illuminations",
        },
        "rows": result_rows,
    }
